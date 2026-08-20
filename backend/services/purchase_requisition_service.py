"""Depth #2 — Purchase Requisition (PR) service + Reorder/Replenishment.

Hulu procurement: kebutuhan beli diajukan sebagai PR → approval → konversi ke PO.
Sumber PR: manual | reorder (saran replenishment) | special_order (jembatan OD).

Koleksi kanonik: `purchase_requisitions` (prefix pr_).
Status: draft → pending_approval → approved → converted | rejected | cancelled.

Invarian (verify_data_integrity L4-PR):
  - item.subtotal == est_price × quantity
  - total_est_amount == Σ item.subtotal
  - status 'converted' ⟹ po_id terisi
"""
import re
from typing import Any, Dict, List, Optional
from db import db
from core_utils import now_iso, new_id, DEFAULT_ENTITY_ID, safe_doc, timeline_entry, next_doc_number
from services.config_service import evaluate_approval, role_satisfies, compute_order_pricing
from services import line_scope as _lines      # FASE L — satu pintu normalisasi lini
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)

# Status PO yang dianggap "pipeline terbuka" → menambah on_order (incoming) produk.
OPEN_PO_STATUSES = {"waiting_approval", "pending", "receiving", "partial"}
PR_TERMINAL = {"converted", "rejected", "cancelled"}
# R1-05 — Status PR yang dianggap "permintaan terbuka" (sudah diajukan, BELUM jadi PO).
#   Dihitung dalam proyeksi reorder agar item yang sudah punya PR tak muncul lagi
#   (mencegah PR ganda). Selaras dgn PR_TERMINAL (kebalikannya).
OPEN_PR_STATUSES = {"draft", "pending_approval", "approved"}


async def next_pr_number() -> str:
    last = await db.purchase_requisitions.find_one(
        {"number": {"$regex": r"^PR-"}}, sort=[("number", -1)])
    n = (int(re.search(r"(\d+)$", last["number"]).group(1)) + 1) if (last and last.get("number")) else 1
    return f"PR-{n:05d}"


async def _wh_name(warehouse_id: str) -> str:
    if not warehouse_id:
        return ""
    wh = await db.warehouses.find_one({"id": warehouse_id}, {"_id": 0, "name": 1})
    return (wh or {}).get("name", "")


async def _enrich_items(raw_items: List[Any]) -> (List[Dict[str, Any]], float):
    """Bangun baris PR + subtotal. product_id opsional (non-katalog/special order).

    FASE B (D-07) — setiap baris berkatalog WAJIB membawa **jejak konversi**
    (`uom_trail`) + qty dalam satuan dasar produk (`base_unit`/`quantity_base`)
    agar perencanaan & laporan tidak pecah karena campur satuan.
    """
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(2000)}
    from services import uom_rules_service as uomr
    from services.pr_sourcing_service import normalize_mode
    engine = await uomr.load_engine()
    items: List[Dict[str, Any]] = []
    total = 0.0
    for idx, it in enumerate(raw_items, start=1):
        pid = (getattr(it, "product_id", "") or "").strip()
        est_price = round(float(getattr(it, "est_price", 0) or 0), 2)
        qty = float(getattr(it, "quantity", 0) or 0)
        if qty <= 0:
            raise ValueError("Quantity item harus > 0")
        sku = ""
        name = (getattr(it, "description", "") or "").strip()
        prod: Dict[str, Any] = {}
        if pid:
            prod = products.get(pid)
            if not prod:
                raise ValueError(f"Produk {pid} tidak ditemukan")
            sku = prod.get("sku", "")
            name = name or prod.get("name", "")
            if est_price <= 0:
                est_price = float(prod.get("harga_pokok", 0) or prod.get("price", 0) or 0)
        if not name:
            raise ValueError("Deskripsi item wajib diisi untuk item non-katalog")
        # FASE E — routing pemenuhan per baris (purchase | makloon).
        mode = normalize_mode(getattr(it, "fulfillment_mode", "purchase") or "purchase")
        if mode == "makloon" and not pid:
            raise ValueError(f"Baris {idx}: mode 'makloon' butuh produk katalog "
                             "(output makloon harus SKU KN yang jelas).")
        subtotal = round(est_price * qty, 2)
        total += subtotal
        unit = getattr(it, "unit", "meter") or "meter"
        row = {
            "line_no": idx,
            "product_id": pid, "sku": sku, "product_name": name,
            "description": name, "quantity": qty,
            "unit": unit,
            "est_price": est_price, "subtotal": subtotal,
            "note": getattr(it, "note", "") or "",
            "fulfillment_mode": mode,
            # FASE L — snapshot lini kerja MD. Baris non-katalog tidak punya lini
            # (kosong = terlihat semua akun) — jangan menebak, karena tebakan di baris
            # non-katalog akan mengunci pekerjaan yang belum ada produknya.
            "line_code": _lines.norm((prod or {}).get("line_code")),
            "realized_qty": 0.0, "realizations": [],
        }
        # FASE U — dua satuan (jumlah roll + ukuran). PR = RENCANA, jadi jumlah rollnya
        # DIKETIK; faktor per dokumen (mis. panjang 1 panel pesanan ini) hanya sah untuk
        # satuan bertanda `factor_per_document` di master.
        row.update(await _dual.stamp(it))
        if prod:
            base_unit = prod.get("base_unit", "meter")
            row["base_unit"] = base_unit
            try:
                trail = await uomr.convert_with_trail(
                    prod, qty, unit, base_unit, engine=engine, context="purchase_requisition")
                row["uom_trail"] = trail
                row["quantity_base"] = trail["base_qty"]
            except uomr.UomRuleError as exc:
                # Tidak menebak faktor: PR ditolak dengan pesan yang bisa ditindak user.
                raise ValueError(str(exc)) from exc
        items.append(row)
    # FASE F (PS-12) — barang yang BELUM sah (masih konsep/labdip/proofing/dihentikan)
    # tidak boleh masuk rencana pengadaan. Data lama (tanpa lifecycle) tetap lolos.
    from services import rnd_gate
    await rnd_gate.assert_orderable(
        [products[i["product_id"]] for i in items
         if i.get("product_id") and i["product_id"] in products],
        where="Purchase Requisition")
    return items, round(total, 2)


async def create_requisition(payload, created_by: str, created_by_id: str = "") -> Dict[str, Any]:
    """Buat PR (draft/pending). Approval dievaluasi dari total_est (matriks)."""
    entity_id = payload.entity_id or DEFAULT_ENTITY_ID
    warehouse_id = payload.warehouse_id or ""
    if warehouse_id and not await db.warehouses.find_one({"id": warehouse_id}, {"_id": 0}):
        raise ValueError("Gudang tidak ditemukan")

    items, total = await _enrich_items(payload.items)
    if not items:
        raise ValueError("Minimal satu item kebutuhan")

    # Supplier preferensi (opsional)
    pref_sup_id = getattr(payload, "preferred_supplier_id", "") or ""
    pref_sup_name = ""
    if pref_sup_id:
        sup = await db.suppliers.find_one({"id": pref_sup_id}, {"_id": 0})
        if not sup:
            raise ValueError("Supplier preferensi tidak ditemukan")
        # FASE E-7 (E7.2) — pagar dipasang SEJAK di hulu (PR), bukan hanya di PO.
        # Kalau PR sudah menunjuk badan usaha grup sebagai pemasok preferensi, orang
        # akan menyetujuinya lalu baru ditolak saat realisasi ke PO — pekerjaan yang
        # sudah lewat persetujuan jadi mubazir. Lebih jujur menolak di sini.
        from services import group_partner_service as _grp
        await _grp.assert_supplier_not_group_entity(
            sup, doc_label="Permintaan Pembelian (PR)")
        pref_sup_name = sup.get("name", "")

    appr = await evaluate_approval("purchase_requisition", total, entity_id)
    needs = appr["requires_approval"]
    submit_now = bool(getattr(payload, "submit_now", False))
    status = "pending_approval" if (needs and submit_now) else ("pending_approval" if submit_now else "draft")
    # Jika tak butuh approval & submit_now → langsung 'approved' (siap konversi)
    if submit_now and not needs:
        status = "approved"

    now = now_iso()
    doc = {
        "id": new_id("pr"), "number": await next_pr_number(),
        "entity_id": entity_id,
        "warehouse_id": warehouse_id, "warehouse_name": await _wh_name(warehouse_id),
        "items": items, "total_est_amount": total,
        # FASE L — turunan baris; dipakai chip penyaring lini di layar PR & papan PO.
        "line_codes": _lines.codes_from_items(items),
        "source": getattr(payload, "source", "manual") or "manual",
        "source_ref_id": getattr(payload, "source_ref_id", "") or "",
        "preferred_supplier_id": pref_sup_id, "preferred_supplier_name": pref_sup_name,
        "reason": getattr(payload, "reason", "") or "",
        "needed_by_date": getattr(payload, "needed_by_date", "") or "",
        "notes": getattr(payload, "notes", "") or "",
        "status": status,
        "approval_required": needs,
        "required_approval_role": appr["required_role"],
        "approval_status": "approved" if status == "approved" else ("pending" if status == "pending_approval" else "not_submitted"),
        "po_id": "", "po_number": "",
        # FASE E — realisasi (turunan dari items[].realized_qty; disimpan utk query cepat)
        "realization_status": "open",
        "realization": {"realization_status": "open", "realized_lines": 0,
                        "total_lines": len(items), "realized_qty": 0.0,
                        "total_qty": round(sum(float(i["quantity"]) for i in items), 3),
                        "realized_pct": 0.0,
                        "purchase_lines": sum(1 for i in items if i.get("fulfillment_mode") == "purchase"),
                        "makloon_lines": sum(1 for i in items if i.get("fulfillment_mode") == "makloon")},
        "po_ids": [], "makloon_order_ids": [], "timeline": [],
        "created_by": created_by, "created_by_id": created_by_id,
        "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None, "reject_reason": None,
        "created_at": now, "updated_at": now,
    }
    await db.purchase_requisitions.insert_one(dict(doc))
    return safe_doc(doc)


async def submit_requisition(pr_id: str) -> Dict[str, Any]:
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise ValueError("PR tidak ditemukan")
    if pr["status"] != "draft":
        raise ValueError("Hanya draft yang bisa disubmit")
    # Jika tak butuh approval → langsung approved
    new_status = "pending_approval" if pr.get("approval_required") else "approved"
    appr_status = "pending" if new_status == "pending_approval" else "approved"
    sets = {"status": new_status, "approval_status": appr_status, "updated_at": now_iso()}
    if new_status == "approved":
        sets["approved_by"] = "system (auto)"
        sets["approved_at"] = now_iso()
    await db.purchase_requisitions.update_one({"id": pr_id}, {"$set": sets})
    return safe_doc(await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0}))


async def approve_requisition(pr_id: str, actor: Dict[str, Any], notes: str = "") -> Dict[str, Any]:
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise ValueError("PR tidak ditemukan")
    if pr["status"] not in ("draft", "pending_approval"):
        raise ValueError(f"PR {pr['number']} sudah {pr['status']}")
    required = pr.get("required_approval_role")
    if not role_satisfies(actor.get("role"), required):
        raise ValueError(f"Approval PR butuh role minimal '{required or 'manager'}'. Role Anda: '{actor.get('role')}'.")
    # H2 → PS-20: pemisahan tugas kini SATU SUMBER di matriks persetujuan sehingga
    # bisa diatur pemilik di Pusat Pengaturan (termasuk kebijakan dokumen lama).
    from services import approval_matrix_service as amx  # impor lokal: hindari siklus
    if await amx.sod_blocked(pr, actor):
        raise ValueError("Pemisahan tugas (SoD): pembuat PR tidak boleh menyetujui PR sendiri. "
                         "Minta approver lain — aturan ini dapat diubah di Pusat Pengaturan → "
                         "Persetujuan & Ambang.")
    now = now_iso()
    await db.purchase_requisitions.update_one({"id": pr_id}, {"$set": {
        "status": "approved", "approval_status": "approved",
        "approved_by": actor.get("name", "Admin"), "approved_at": now,
        "decision_notes": notes, "updated_at": now,
    }})
    return safe_doc(await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0}))


async def reject_requisition(pr_id: str, actor: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise ValueError("PR tidak ditemukan")
    if pr["status"] not in ("draft", "pending_approval"):
        raise ValueError(f"PR {pr['number']} sudah {pr['status']}")
    required = pr.get("required_approval_role")
    if not role_satisfies(actor.get("role"), required):
        raise ValueError(f"Reject PR butuh role minimal '{required or 'manager'}'. Role Anda: '{actor.get('role')}'.")
    now = now_iso()
    await db.purchase_requisitions.update_one({"id": pr_id}, {"$set": {
        "status": "rejected", "approval_status": "rejected",
        "rejected_by": actor.get("name", "Admin"), "rejected_at": now,
        "reject_reason": reason, "updated_at": now,
    }})
    return safe_doc(await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0}))


async def cancel_requisition(pr_id: str) -> Dict[str, Any]:
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise ValueError("PR tidak ditemukan")
    if pr["status"] in PR_TERMINAL:
        raise ValueError(f"PR {pr['number']} sudah {pr['status']}")
    await db.purchase_requisitions.update_one({"id": pr_id}, {"$set": {
        "status": "cancelled", "updated_at": now_iso()}})
    return safe_doc(await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0}))


async def convert_to_po(pr_id: str, supplier_id: str, actor: Dict[str, Any],
                        warehouse_id: str = "", expected_delivery_date: str = "",
                        notes: str = "") -> Dict[str, Any]:
    """Konversi PR approved → Purchase Order.

    FASE E: sejak routing per-baris diperkenalkan, fungsi ini **mendelegasikan** ke
    `pr_sourcing_service.realize_to_po` (semua baris ber-mode `purchase` yang masih terbuka).
    Perilaku lama tetap: bila SEMUA baris ber-mode `purchase` (kasus data lama & default),
    hasilnya identik — PR menjadi `converted` dengan `po_id`/`po_number` terisi.
    Baris ber-mode `makloon` TIDAK ikut (dipenuhi via `realize_to_makloon`).
    """
    from services.pr_sourcing_service import SourcingError, realize_to_po
    try:
        return await realize_to_po(
            pr_id, supplier_id=supplier_id, actor=actor, warehouse_id=warehouse_id,
            expected_delivery_date=expected_delivery_date, notes=notes)
    except SourcingError as exc:
        raise ValueError(str(exc)) from exc



# ─── Reorder Point / Replenishment (Depth #2b) ───────────────────────────────

async def reorder_suggestions(entity_id: Optional[str] = None, ctx: Any = None) -> Dict[str, Any]:
    """Saran replenishment: produk dgn reorder_point>0 yang proyeksi stok
    (available + on_order + on_request) <= reorder_point. Menghindari double-order
    via on_order (PO terbuka) DAN double-request via on_request (PR terbuka belum
    jadi PO — R1-05). Baris menyertakan `on_request` & `existing_prs` untuk badge.
    Fase 5: +avg_daily_sold & suggested_rop (velocity×(lead+safety)) per baris, dan
    `rop_candidates` = produk bergerak yang BELUM punya ROP (usulan set ROP)."""
    products = await db.products.find({"status": "active"}, {"_id": 0}).to_list(2000)

    # available per produk (Σ available_qty balances, owner-scoped bila entity_id)
    bal_q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        bal_q["owner_entity_id"] = entity_id
    avail: Dict[str, float] = {}
    async for b in db.inventory_balances.find(bal_q, {"_id": 0, "product_id": 1, "available_qty": 1}):
        avail[b["product_id"]] = avail.get(b["product_id"], 0.0) + float(b.get("available_qty", 0) or 0)

    # on_order per produk (Σ qty-received pada PO terbuka), owner-scoped bila entity_id
    po_q: Dict[str, Any] = {"status": {"$in": list(OPEN_PO_STATUSES)}}
    if entity_id and entity_id != "all":
        po_q["entity_id"] = entity_id
    on_order: Dict[str, float] = {}
    async for po in db.purchase_orders.find(po_q, {"_id": 0, "items": 1}):
        for it in po.get("items", []):
            gap = float(it.get("quantity", 0) or 0) - float(it.get("received_qty", 0) or 0)
            if gap > 0:
                on_order[it["product_id"]] = on_order.get(it["product_id"], 0.0) + gap

    # R1-05 — on_request per produk (Σ qty PR TERBUKA yang belum dikonversi ke PO),
    #   owner-scoped bila entity_id. Tanpa ini, item yang SUDAH punya PR tetap muncul
    #   di saran reorder → risiko PR ganda (bug R1-05). Sekaligus kumpulkan nomor PR
    #   terbuka per produk (`existing_prs`) untuk badge transparan di UI.
    pr_q: Dict[str, Any] = {"status": {"$in": list(OPEN_PR_STATUSES)}}
    if entity_id and entity_id != "all":
        pr_q["entity_id"] = entity_id
    on_request: Dict[str, float] = {}
    existing_prs: Dict[str, List[str]] = {}
    async for pr in db.purchase_requisitions.find(pr_q, {"_id": 0, "number": 1, "items": 1}):
        for it in pr.get("items", []):
            pid = it.get("product_id")
            if not pid:
                continue
            on_request[pid] = on_request.get(pid, 0.0) + float(it.get("quantity", 0) or 0)
            lst = existing_prs.setdefault(pid, [])
            if pr.get("number") and pr["number"] not in lst:
                lst.append(pr["number"])

    # supplier preferensi via master (match nama supplier produk → suppliers)
    suppliers = await db.suppliers.find({}, {"_id": 0}).to_list(500)
    sup_by_name = {s["name"]: s for s in suppliers}

    from services.supplier_service import resolve_price
    from services.stock_analytics_service import product_sales_velocity
    from services.config_service import get_effective_settings
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone.utc).date()

    # Fase 5 — ROP dinamis berbasis kecepatan jual (window & safety configurable).
    rcfg = ((await get_effective_settings(entity_id if entity_id and entity_id != "all" else None))
            .get("inventory", {}) or {}).get("reorder", {}) or {}
    window = int(rcfg.get("velocity_window_days", 90))
    safety_days = int(rcfg.get("safety_days", 7))
    velocity = await product_sales_velocity(ctx, entity_id, window) if ctx is not None else {}

    async def _supplier_lead(p: Dict[str, Any], qty: float):
        pref = sup_by_name.get(p.get("supplier", ""), {})
        pref_id = pref.get("id", "")
        resolved = await resolve_price(pref_id, p["id"], qty) if pref_id else {}
        lead = int(resolved.get("lead_time_days", 0) or 0) or int(pref.get("lead_time_days", 0) or 0)
        return pref, pref_id, resolved, lead

    rows = []
    rop_candidates = []
    for p in products:
        pid = p["id"]
        vel = velocity.get(pid, {})
        avg_daily = float(vel.get("avg_daily", 0) or 0)
        av = round(avail.get(pid, 0.0), 2)
        oo = round(on_order.get(pid, 0.0), 2)
        orq = round(on_request.get(pid, 0.0), 2)  # R1-05 — PR terbuka (belum jadi PO)
        projected = round(av + oo + orq, 2)
        rop = float(p.get("reorder_point", 0) or 0)

        if rop > 0:
            if projected > rop:
                continue
            roq = float(p.get("reorder_qty", 0) or 0)
            suggested = roq if roq > 0 else round(rop - projected, 2)
            if suggested <= 0:
                suggested = round(max(rop - projected, 0.0), 2)
            pref, pref_id, resolved, lead = await _supplier_lead(p, suggested)
            est_price = float(resolved.get("price", 0) or 0) if resolved.get("price", 0) else \
                float(p.get("harga_pokok", 0) or p.get("price", 0) or 0)
            eta = (today + timedelta(days=lead)).isoformat() if lead > 0 else ""
            suggested_rop = round(avg_daily * (lead + safety_days), 2) if avg_daily > 0 else 0.0
            rows.append({
                "product_id": pid, "sku": p.get("sku", ""), "product_name": p.get("name", ""),
                "unit": resolved.get("unit") or p.get("base_unit", "meter"),
                "available": av, "on_order": oo, "on_request": orq, "projected": projected,
                "existing_prs": existing_prs.get(pid, []),  # R1-05 — badge "Sudah ada PR #…"
                "reorder_point": rop, "reorder_qty": roq, "suggested_qty": suggested,
                "est_price": round(est_price, 2),
                "price_source": resolved.get("source", "product_fallback"),
                "lead_time_days": lead, "expected_arrival_date": eta,
                "preferred_supplier_id": pref_id,
                "preferred_supplier_name": pref.get("name", p.get("supplier", "")),
                "avg_daily_sold": round(avg_daily, 3),
                "suggested_rop": suggested_rop,
                "rop_source": "manual",
            })
        elif avg_daily > 0:
            # Produk bergerak tapi BELUM punya ROP → sarankan ROP berbasis velocity.
            nominal_qty = max(round(avg_daily * safety_days, 2), 1.0)
            pref, pref_id, resolved, lead = await _supplier_lead(p, nominal_qty)
            suggested_rop = round(avg_daily * (lead + safety_days), 2)
            if suggested_rop <= 0:
                continue
            rop_candidates.append({
                "product_id": pid, "sku": p.get("sku", ""), "product_name": p.get("name", ""),
                "unit": p.get("base_unit", "meter"),
                "available": av, "on_order": oo, "on_request": orq, "projected": projected,
                "existing_prs": existing_prs.get(pid, []),  # R1-05 — transparansi PR terbuka
                "avg_daily_sold": round(avg_daily, 3), "lead_time_days": lead,
                "suggested_rop": suggested_rop,
                "suggested_qty": round(max(suggested_rop - projected, 0.0), 2),
                "preferred_supplier_id": pref_id,
                "preferred_supplier_name": pref.get("name", p.get("supplier", "")),
                "below_suggested": projected <= suggested_rop,
            })

    rows.sort(key=lambda r: (r["projected"] - r["reorder_point"]))
    rop_candidates.sort(key=lambda r: -r["avg_daily_sold"])
    return {"items": rows, "count": len(rows),
            "rop_candidates": rop_candidates, "rop_candidate_count": len(rop_candidates),
            "config": {"velocity_window_days": window, "safety_days": safety_days},
            "entity_id": entity_id or "all", "generated_at": now_iso()}
