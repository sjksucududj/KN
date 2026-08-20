"""Depth #1 — Retur Beli (Purchase Return / Nota Debit).

Kebalikan dari Goods Receipt: barang dikembalikan ke supplier →
- KURANGI `inventory_rolls` available (FIFO owner-scoped, split bila parsial)
- catat movement `return_out` (keluar)
- terbitkan Nota Debit (DN-NNNNN) → mengurangi hutang (AP) PO terkait
- rebuild_balance segmen terdampak

Koleksi kanonik: `purchase_returns` (prefix pret_).
Status: draft → pending_approval → approved | rejected.
"""
import re
from typing import Any, Dict, List
from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from core_utils import now_iso, new_id, DEFAULT_ENTITY_ID, safe_doc
from services.roll_service import rebuild_balance
from services import purchase_return_state as prs
from request_context import active_entity_or
from services import line_scope as _lines      # FASE L — satu pintu normalisasi lini

RETURNED_STATUS = "returned_supplier"  # status terminal roll (tidak masuk bucket manapun)


async def next_return_number() -> str:
    last = await db.purchase_returns.find_one({"number": {"$regex": r"^PRET-"}}, sort=[("number", -1)])
    n = (int(re.search(r"(\d+)$", last["number"]).group(1)) + 1) if (last and last.get("number")) else 1
    return f"PRET-{n:05d}"


async def next_debit_note_number() -> str:
    last = await db.purchase_returns.find_one(
        {"debit_note_number": {"$regex": r"^DN-"}}, sort=[("debit_note_number", -1)])
    n = (int(re.search(r"(\d+)$", last["debit_note_number"]).group(1)) + 1) if (last and last.get("debit_note_number")) else 1
    return f"DN-{n:05d}"


async def create_purchase_return(payload, created_by: str) -> Dict[str, Any]:
    """Buat dokumen retur beli (draft/pending)."""
    supplier_id = payload.supplier_id
    supplier_name = ""
    sup: Dict[str, Any] = {}
    if supplier_id:
        sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0}) or {}
        if not sup:
            raise ValueError("Supplier tidak ditemukan")
        supplier_name = sup.get("name", "")

    po = None
    warehouse_id = payload.warehouse_id
    # FASE E-1 (E1.10) — retur beli milik badan usaha konteks bila tak disebut.
    entity_id = payload.entity_id or active_entity_or(DEFAULT_ENTITY_ID)
    if payload.po_id:
        po = await db.purchase_orders.find_one({"id": payload.po_id}, {"_id": 0})
        if not po:
            raise ValueError("Purchase Order tidak ditemukan")
        supplier_id = supplier_id or po.get("supplier_id", "")
        supplier_name = supplier_name or po.get("supplier_name", "")
        warehouse_id = warehouse_id or po.get("warehouse_id", "")
        entity_id = (payload.entity_id or po.get("entity_id")
                     or active_entity_or(DEFAULT_ENTITY_ID))

    if not supplier_name:
        raise ValueError("Supplier wajib dipilih")
    if not warehouse_id:
        raise ValueError("Gudang wajib dipilih")

    # R4 (§J) — hormati kebijakan retur supplier & asal barang (impor vs lokal).
    if not sup and supplier_id:
        sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0}) or {}
    from services.return_policy_service import resolve_supplier_return_policy
    pol = resolve_supplier_return_policy(sup, po)
    if pol.get("recommend_regrade_local") and not getattr(payload, "bypass_import_policy", False):
        raise ValueError(
            f"Barang IMPOR dari '{supplier_name}' tidak dapat diretur ke supplier "
            f"(returnable_to_supplier=false). Rekomendasi: REGRADE + jual lokal "
            f"(gunakan release karantina dengan grade B/C atau transfer/regrade R3).")

    # Enrich items dengan nama produk + subtotal
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(2000)}
    items: List[Dict[str, Any]] = []
    total = 0.0
    for it in payload.items:
        prod = products.get(it.product_id)
        if not prod:
            raise ValueError(f"Produk {it.product_id} tidak ditemukan")
        # H4 — UOM otoritatif dari master produk (base_unit), bukan dari klien.
        unit = prod.get("base_unit") or (it.unit if it.unit else "") or "meter"
        roll_ids = list(getattr(it, "roll_ids", []) or [])
        roll_meta: List[Dict[str, Any]] = []
        qty = float(it.quantity or 0)
        price = it.price if it.price > 0 else 0.0
        if roll_ids:
            # Retur PRESISI: qty, lot & harga diturunkan dari roll asal yang dipilih.
            sel = await db.inventory_rolls.find(
                {"id": {"$in": roll_ids}, "product_id": it.product_id}, {"_id": 0}).to_list(1000)
            if not sel:
                raise ValueError(f"Roll asal untuk {prod.get('sku')} tidak ditemukan.")
            roll_qty = round(sum(float(r.get("length_remaining", 0) or 0) for r in sel), 2)
            qty = roll_qty if qty <= 0 else min(qty, roll_qty)
            if price <= 0:
                costs = [float(r.get("unit_cost") or r.get("base_unit_cost") or 0) for r in sel]
                costs = [c for c in costs if c > 0]
                price = round(sum(costs) / len(costs), 2) if costs else (_po_item_price(po, it.product_id) or float(prod.get("price", 0)))
            roll_meta = [{"roll_id": r["id"], "roll_no": r.get("roll_no", ""), "lot": r.get("lot", ""),
                          "length_remaining": float(r.get("length_remaining", 0) or 0),
                          "supplier_invoice_no": r.get("supplier_invoice_no", ""),
                          "po_number": r.get("po_number", "")} for r in sel]
        if price <= 0:
            price = _po_item_price(po, it.product_id) or float(prod.get("price", 0))
        subtotal = round(price * qty, 2)
        total += subtotal
        items.append({
            "product_id": it.product_id, "sku": prod.get("sku", ""),
            "product_name": prod.get("name", ""), "quantity": float(qty),
            "unit": unit, "price": price, "subtotal": subtotal,
            "reason": it.reason, "condition": it.condition,
            "roll_ids": roll_ids, "rolls": roll_meta,
            "lots": sorted({m["lot"] for m in roll_meta if m.get("lot")}),
            # FASE L — snapshot lini kerja MD (retur beli masuk papan lini yang sama
            # dengan pembeliannya).
            "line_code": _lines.norm(prod.get("line_code")),
            # FASE U — jumlah roll yang dikembalikan ke supplier = roll NYATA yang dipilih
            # (bukan diketik): `roll_ids` sudah ada sejak FASE E, sekarang ikut terbaca
            # sebagai satuan kedua di layar, PDF, dan CSV.
            "qty_rolls": (len(roll_meta) if roll_meta else None),
        })

    number = await next_return_number()
    now = now_iso()
    supplier_flow = bool(getattr(payload, "supplier_flow", False))
    doc = {
        "id": new_id("pret"), "number": number,
        "supplier_id": supplier_id, "supplier_name": supplier_name,
        "po_id": payload.po_id, "po_number": (po or {}).get("po_number", ""),
        "warehouse_id": warehouse_id,
        "warehouse_name": await _wh_name(warehouse_id),
        "entity_id": entity_id,
        "items": items, "total_amount": round(total, 2),
        # FASE L — turunan baris (chip penyaring lini di layar Retur Beli).
        "line_codes": _lines.codes_from_items(items),
        "reason": payload.reason, "notes": payload.notes,
        "status": "pending_approval" if payload.submit_now else "draft",
        "debit_note_number": "", "stock_adjusted": False,
        # R4 — supplier RMA lifecycle + link retur jual→beli + snapshot kebijakan (§J)
        "supplier_flow": supplier_flow,
        "supplier_status": prs.REQUESTED if supplier_flow else prs.SUP_NONE,
        "supplier_outcome": "",
        "origin_type": pol.get("origin_type", "local"),
        "origin_sales_return_id": getattr(payload, "origin_sales_return_id", "") or "",
        "origin_sales_return_number": "",
        "return_policy_snapshot": {
            "origin_type": pol.get("origin_type"),
            "returnable_to_supplier": pol.get("returnable_to_supplier"),
            "refund_modes": (pol.get("policy") or {}).get("refund_modes", []),
        },
        "shipped_at": None, "accepted_at": None, "goods_back_at": None,
        "created_by": created_by, "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None, "reject_reason": None,
        "created_at": now, "updated_at": now,
    }
    await db.purchase_returns.insert_one(doc)
    from services import doc_refs_service as _refs
    if doc.get("po_id"):
        await _refs.safe_link(("purchase_return", doc["id"]), ("purchase_order", doc["po_id"]),
                              "reverses", note="retur beli atas PO")
    # FASE E-9 (E9.6) — sambungan TERAKHIR rantai retur: kalau barang yang diretur ke
    # supplier ini datang kembali lewat RETUR ANTAR-PT, kedua dokumen harus saling
    # menunjuk. Tanpa ini rantai "retur pelanggan → retur antar-PT → retur beli" putus
    # di sambungan ketiga dan tidak ada layar yang bisa menjawab "kainnya ke mana?".
    await _link_interco_return_chain(doc)
    return safe_doc(doc)


async def _link_interco_return_chain(ret: Dict[str, Any]) -> None:
    """Tautkan retur beli ke RETUR ANTAR-PT yang mengembalikan barangnya (E9.6).

    Jejaknya dibaca dari roll: `acquired`/`acquired_history` menunjuk tugas gudang,
    dan tugas gudang retur antar-PT membawa `interco_return_pair_id`.
    """
    roll_ids = [rid for it in ret.get("items", []) for rid in (it.get("roll_ids") or [])]
    if not roll_ids:
        return
    try:
        rolls = await db.inventory_rolls.find(
            {"id": {"$in": roll_ids}},
            {"_id": 0, "acquired": 1, "acquired_history": 1}).to_list(500)
        refs = set()
        for r in rolls:
            for acq in [r.get("acquired") or {}] + list(r.get("acquired_history") or []):
                if acq.get("via") == "transfer" and acq.get("ref_id"):
                    refs.add(acq["ref_id"])
        if not refs:
            return
        trfs = await db.warehouse_transfers.find(
            {"id": {"$in": list(refs)}, "interco_return_pair_id": {"$nin": [None, ""]}},
            {"_id": 0, "interco_return_pair_id": 1}).to_list(200)
        pairs = {t["interco_return_pair_id"] for t in trfs if t.get("interco_return_pair_id")}
        if not pairs:
            return
        from services import doc_refs_service as _refs
        for pair in pairs:
            # Sisi PENERIMA barang (nota kredit) = badan usaha yang kini meretur ke supplier.
            icr = await db.interco_returns.find_one(
                {"return_pair_id": pair, "role": "receiver"},
                {"_id": 0, "id": 1, "number": 1}) or {}
            if not icr.get("id"):
                continue
            await _refs.safe_link(("interco_return", icr["id"]),
                                  ("purchase_return", ret["id"]), "child",
                                  note="Barang yang kembali dari badan usaha lain diteruskan ke supplier")
            await db.purchase_returns.update_one(
                {"id": ret["id"]},
                {"$set": {"origin_interco_return_id": icr["id"],
                          "origin_interco_return_number": icr.get("number", ""),
                          "updated_at": now_iso()}})
            # Dokumen yang dikembalikan ke pemanggil WAJIB ikut membawa tautannya —
            # kalau hanya Mongo yang diperbarui, layar yang baru saja membuat retur
            # ini tidak pernah menampilkan asal barangnya (harus muat-ulang dulu).
            ret["origin_interco_return_id"] = icr["id"]
            ret["origin_interco_return_number"] = icr.get("number", "")
    except Exception as exc:  # noqa: BLE001 — pelengkap jejak, bukan syarat sah dokumen
        print(f"[purchase_return] tautan rantai retur antar-PT gagal: {exc}")


async def submit_purchase_return(return_id: str, submitted_by: str = "") -> Dict[str, Any]:
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur tidak ditemukan")
    if ret["status"] != "draft":
        raise ValueError("Hanya draft yang bisa disubmit")
    await db.purchase_returns.update_one({"id": return_id},
        {"$set": {"status": "pending_approval", "submitted_at": now_iso(),
                  "submitted_by": submitted_by, "updated_at": now_iso()}})
    return safe_doc(await db.purchase_returns.find_one({"id": return_id}, {"_id": 0}))


async def approve_and_adjust_stock(return_id: str, approved_by: str, notes: str = "") -> Dict[str, Any]:
    """Approve retur beli.

    - DIRECT (supplier_flow=False): langsung konsumsi roll available → Nota Debit → kurangi AP → jurnal GL.
      (supplier_status di-set 'accepted_supplier', outcome default 'ap_credit'.)
    - RMA (supplier_flow=True): approve hanya GATE internal (status→approved); stok & DN & GL BELUM.
      Efek fisik/finansial menyusul via ship_to_supplier → supplier_accept/supplier_reject → goods_back.
    """
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur tidak ditemukan")
    if ret["status"] not in ("draft", "pending_approval"):
        raise ValueError(f"Retur {ret['number']} sudah {ret['status']}")

    now = now_iso()
    if ret.get("supplier_flow"):
        # RMA — approval internal saja. supplier_status tetap 'requested_supplier'.
        await db.purchase_returns.update_one({"id": return_id}, {"$set": {
            "status": "approved", "approved_by": approved_by, "approved_at": now,
            "decision_notes": notes, "updated_at": now,
            "supplier_status": ret.get("supplier_status") or prs.REQUESTED,
        }})
        return safe_doc(await db.purchase_returns.find_one({"id": return_id}, {"_id": 0}))

    # DIRECT — finalisasi penuh (stok + DN + AP + GL).
    return await _finalize_supplier_return_financials(
        ret, actor=approved_by, notes=notes, outcome=prs.OUTCOME_AP_CREDIT)


async def _finalize_supplier_return_financials(ret: Dict[str, Any], actor: str, notes: str,
                                               outcome: str, refund_account_code: str = "") -> Dict[str, Any]:
    """Konsumsi roll (returned_supplier) + Nota Debit + kurangi AP PO + jurnal GL retur beli.
    Dipakai oleh alur DIRECT (approve) & RMA (supplier_accept). Idempotent via stock_adjusted."""
    return_id = ret["id"]
    now = now_iso()
    warehouse_id = ret["warehouse_id"]
    entity_id = ret["entity_id"]

    if not ret.get("stock_adjusted"):
        segments = set()
        for item in ret.get("items", []):
            qty = float(item.get("quantity", 0))
            if qty <= 0:
                continue
            if item.get("roll_ids"):
                consumed = await _consume_specific_rolls(item["roll_ids"], entity_id, qty, ret)
            else:
                consumed = await _consume_available_rolls(item["product_id"], warehouse_id, entity_id, qty, ret)
            if consumed + 0.01 < qty:
                raise ValueError(
                    f"Stok tak cukup untuk retur {item.get('sku')} "
                    f"(tersedia {round(consumed,2)} dari {qty}).")
            segments.add((item["product_id"], warehouse_id, entity_id))
        for (pid, wid, eid) in segments:
            await rebuild_balance(pid, wid, eid)

    debit_note = ret.get("debit_note_number") or await next_debit_note_number()
    await db.purchase_returns.update_one({"id": return_id}, {"$set": {
        "status": "approved", "stock_adjusted": True, "debit_note_number": debit_note,
        "approved_by": ret.get("approved_by") or actor,
        "approved_at": ret.get("approved_at") or now,
        "decision_notes": notes, "updated_at": now,
        "supplier_status": prs.ACCEPTED, "supplier_outcome": outcome,
        "accepted_at": now, "accepted_by": actor,
    }})

    is_refund = (outcome or "").lower() == prs.OUTCOME_REFUND
    # ap_credit → kurangi hutang (AP) pada PO terkait. refund → AP tak berubah (supplier bayar tunai).
    if ret.get("po_id") and not is_refund:
        await db.purchase_orders.update_one(
            {"id": ret["po_id"]},
            {"$inc": {"returned_amount": float(ret.get("total_amount", 0))},
             "$set": {"updated_at": now}})
        from routers.purchase_orders import recompute_po_payment_status
        await recompute_po_payment_status(ret["po_id"])

    # R5.3 (PRET-GL) — pemisahan GL by outcome:
    #   ap_credit → Dr Hutang/GR-IR / Cr Persediaan [+ reversal PPN]  (potong AP via Nota Debit)
    #   refund    → Dr Kas/Bank        / Cr Persediaan [+ reversal PPN]  (supplier kembalikan dana)
    fresh = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    from services import gl_service
    acc = refund_account_code or ret.get("refund_account_code") or "1-1100"
    je = await gl_service.post_purchase_return(
        fresh, amount=float(fresh.get("total_amount", 0) or 0),
        ppn=float(fresh.get("ppn_amount", 0) or fresh.get("ppn", 0) or 0), label=debit_note,
        outcome=outcome, cash_account_code=(acc if is_refund else ""))
    # refund tunai → catat kas MASUK (buku kas/bank).
    if is_refund:
        try:
            from services import cash_ledger
            ctxn = await cash_ledger.record_return_cash(
                direction="in", amount=float(fresh.get("total_amount", 0) or 0), account_code=acc,
                category="Refund Retur Beli (Supplier)",
                description=f"Refund tunai supplier — retur beli {debit_note} ({fresh.get('supplier_name', '')})",
                entity_id=entity_id, ref_type="purchase_return", ref_id=return_id,
                journal_entry_id=(je or {}).get("id", ""), created_by=actor)
            if ctxn:
                await db.purchase_returns.update_one({"id": return_id}, {"$set": {
                    "cash_txn_id": ctxn.get("id"), "cash_txn_number": ctxn.get("number"),
                    "refund_account_code": acc, "updated_at": now_iso()}})
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("cash.refund").exception(
                "Gagal catat kas refund retur beli %s: %s", return_id, e)
    fresh = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    return safe_doc(fresh)


# ─── R4 — Supplier RMA lifecycle ─────────────────────────────────────────────

async def ship_to_supplier(return_id: str, actor: str, notes: str = "",
                           carrier: str = "", tracking_no: str = "") -> Dict[str, Any]:
    """requested_supplier → shipped_supplier. Barang dikirim ke supplier.
    Akuntansi: roll TETAP milik KN (subledger persediaan tidak berubah). Bila roll masih
    'available', dikunci ke 'quarantine' (earmarked) agar tak terjual selama RMA."""
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur tidak ditemukan")
    if not ret.get("supplier_flow"):
        raise ValueError("Aksi RMA hanya untuk retur beli ber-alur supplier (supplier_flow).")
    if ret.get("status") != "approved":
        raise ValueError(f"Retur harus 'approved' dulu (status: {ret.get('status')}).")
    prs.assert_transition(ret.get("supplier_status") or prs.REQUESTED, prs.SHIPPED)

    now = now_iso()
    segments = set()
    for item in ret.get("items", []):
        for rid in (item.get("roll_ids") or []):
            roll = await db.inventory_rolls.find_one({"id": rid}, {"_id": 0})
            if not roll:
                continue
            if roll.get("status") == "available":
                await db.inventory_rolls.update_one({"id": rid}, {"$set": {
                    "status": "quarantine",
                    "supplier_return_ref": {"type": "purchase_return", "id": return_id},
                    "updated_at": now}})
                segments.add((roll.get("product_id"), roll.get("warehouse_id"), roll.get("owner_entity_id")))
    for (pid, wid, eid) in segments:
        if pid and wid and eid:
            await rebuild_balance(pid, wid, eid)

    await db.purchase_returns.update_one({"id": return_id}, {"$set": {
        "supplier_status": prs.SHIPPED, "shipped_at": now, "shipped_by": actor,
        "ship_notes": notes, "carrier": carrier, "tracking_no": tracking_no, "updated_at": now}})
    return safe_doc(await db.purchase_returns.find_one({"id": return_id}, {"_id": 0}))


async def supplier_accept(return_id: str, actor: str, outcome: str = prs.OUTCOME_AP_CREDIT,
                          notes: str = "", refund_account_code: str = "") -> Dict[str, Any]:
    """shipped_supplier → accepted_supplier. Supplier terima retur → finalisasi (stok + DN + AP + GL)."""
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur tidak ditemukan")
    if not ret.get("supplier_flow"):
        raise ValueError("Aksi RMA hanya untuk retur beli ber-alur supplier.")
    if outcome not in prs.SUPPLIER_OUTCOMES:
        raise ValueError(f"Outcome supplier tidak valid: '{outcome}'. Pilihan: {', '.join(sorted(prs.SUPPLIER_OUTCOMES))}.")
    prs.assert_transition(ret.get("supplier_status"), prs.ACCEPTED)
    return await _finalize_supplier_return_financials(
        ret, actor=actor, notes=notes, outcome=outcome, refund_account_code=refund_account_code)


async def supplier_reject(return_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
    """shipped_supplier → rejected_supplier. Supplier tolak retur (barang akan dikembalikan ke KN)."""
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur tidak ditemukan")
    if not ret.get("supplier_flow"):
        raise ValueError("Aksi RMA hanya untuk retur beli ber-alur supplier.")
    prs.assert_transition(ret.get("supplier_status"), prs.REJECTED)
    now = now_iso()
    await db.purchase_returns.update_one({"id": return_id}, {"$set": {
        "supplier_status": prs.REJECTED, "supplier_rejected_at": now, "supplier_rejected_by": actor,
        "supplier_reject_reason": reason, "updated_at": now}})
    return safe_doc(await db.purchase_returns.find_one({"id": return_id}, {"_id": 0}))


async def goods_back(return_id: str, actor: str, regrade: List[Dict[str, Any]] = None,
                     warehouse_id: str = "", notes: str = "") -> Dict[str, Any]:
    """rejected_supplier → goods_back. Barang kembali ke KN → roll quarantine→available (+regrade).
    Tanpa jurnal GL (nilai persediaan tak berubah; roll tak pernah keluar subledger). Idempotent."""
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur tidak ditemukan")
    if not ret.get("supplier_flow"):
        raise ValueError("Aksi RMA hanya untuk retur beli ber-alur supplier.")
    prs.assert_transition(ret.get("supplier_status"), prs.GOODS_BACK)

    now = now_iso()
    grade_by_roll = {g.get("roll_id"): (g.get("grade") or "").upper()
                     for g in (regrade or []) if g.get("roll_id")}
    segments = set()
    regraded = 0
    for item in ret.get("items", []):
        for rid in (item.get("roll_ids") or []):
            roll = await db.inventory_rolls.find_one({"id": rid}, {"_id": 0})
            if not roll:
                continue
            dest_wh = warehouse_id or roll.get("warehouse_id")
            upd = {"status": "available", "warehouse_id": dest_wh,
                   "supplier_return_ref": None, "updated_at": now}
            new_grade = grade_by_roll.get(rid)
            if new_grade and new_grade != (roll.get("grade") or "A"):
                upd["grade"] = new_grade
                upd["regraded_from"] = roll.get("grade") or "A"
                regraded += 1
            await db.inventory_rolls.update_one({"id": rid}, {"$set": upd})
            await db.inventory_movements.insert_one({
                "id": new_id("mov"), "product_id": roll.get("product_id", ""),
                "warehouse_id": dest_wh, "owner_entity_id": roll.get("owner_entity_id", ""),
                "type": "goods_back", "movement_type": "goods_back", "direction": "in",
                "quantity": float(roll.get("length_remaining", 0) or 0), "unit": roll.get("unit", "meter"),
                "roll_id": rid,
                # FASE U — satu baris mutasi menunjuk SATU roll fisik.
                "qty_rolls": (1 if rid else None), "ref_type": "purchase_return", "ref_id": return_id,
                "source_document": ret["number"],
                "notes": f"Barang kembali (supplier tolak) {ret['number']}"
                         + (f" · regrade {upd.get('regraded_from')}→{new_grade}" if new_grade else ""),
                "timestamp": now})
            segments.add((roll.get("product_id"), dest_wh, roll.get("owner_entity_id")))
    for (pid, wid, eid) in segments:
        if pid and wid and eid:
            await rebuild_balance(pid, wid, eid)

    await db.purchase_returns.update_one({"id": return_id}, {"$set": {
        "supplier_status": prs.GOODS_BACK, "goods_back_at": now, "goods_back_by": actor,
        "goods_back_notes": notes, "goods_back_regraded": regraded, "updated_at": now}})
    return safe_doc(await db.purchase_returns.find_one({"id": return_id}, {"_id": 0}))


async def delete_purchase_return(return_id: str) -> Dict[str, Any]:
    """Hapus retur — HANYA status draft (belum ada dampak stok/AP)."""
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur tidak ditemukan")
    if ret.get("status") != "draft":
        raise ValueError(f"Hanya retur draft yang bisa dihapus (status saat ini: {ret.get('status')}).")
    await db.purchase_returns.delete_one({"id": return_id})
    return {"id": return_id, "number": ret.get("number", ""), "deleted": True}


async def reject_purchase_return(return_id: str, rejected_by: str, reason: str) -> Dict[str, Any]:
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur tidak ditemukan")
    if ret["status"] not in ("draft", "pending_approval"):
        raise ValueError(f"Retur {ret['number']} sudah {ret['status']}")
    now = now_iso()
    await db.purchase_returns.update_one({"id": return_id}, {"$set": {
        "status": "rejected", "rejected_by": rejected_by, "rejected_at": now,
        "reject_reason": reason, "updated_at": now,
    }})
    return safe_doc(await db.purchase_returns.find_one({"id": return_id}, {"_id": 0}))


# ─── R4 — Chain: buat Retur Beli dari Retur Jual ─────────────────────────────

async def create_from_sales_return(sales_return_id: str, actor: str,
                                   roll_ids: List[str] = None, supplier_id: str = "",
                                   warehouse_id: str = "", reason: str = "", notes: str = "",
                                   bypass_import_policy: bool = False) -> Dict[str, Any]:
    """Barang cacat dari customer (retur jual) diteruskan sebagai retur ke SUPPLIER.
    Sumber = roll karantina/available hasil retur jual. Menautkan kedua dokumen 2 arah.
    Menghormati kebijakan impor (§J) via create_purchase_return."""
    from schemas_purchasing import PurchaseReturnCreate, PurchaseReturnItem

    sr = await db.sales_returns.find_one({"id": sales_return_id}, {"_id": 0})
    if not sr:
        raise ValueError("Retur jual tidak ditemukan")
    if sr.get("linked_purchase_return_id"):
        raise ValueError(f"Retur jual {sr.get('number')} sudah tertaut retur beli "
                         f"{sr.get('linked_purchase_return_number') or sr.get('linked_purchase_return_id')}.")

    q: Dict[str, Any] = {"return_id": sales_return_id, "origin_type": "return",
                         "status": {"$in": ["quarantine", "available"]},
                         "length_remaining": {"$gt": 0}}
    if roll_ids:
        q["id"] = {"$in": list(roll_ids)}
    rolls = await db.inventory_rolls.find(q, {"_id": 0}).to_list(1000)
    if not rolls:
        raise ValueError("Tidak ada roll karantina/available dari retur jual ini untuk diretur ke supplier.")

    entity_id = sr.get("entity_id") or rolls[0].get("owner_entity_id") or DEFAULT_ENTITY_ID
    wh_id = warehouse_id or rolls[0].get("warehouse_id", "")

    # Resolusi supplier & PO asal (best-effort dari PO terakhir yang memuat produk).
    po_id = ""
    if not supplier_id:
        for pid in {r.get("product_id") for r in rolls}:
            po = await db.purchase_orders.find_one(
                {"items.product_id": pid, "supplier_id": {"$ne": ""}},
                {"_id": 0, "supplier_id": 1, "id": 1}, sort=[("created_at", -1)])
            if po and po.get("supplier_id"):
                supplier_id = po["supplier_id"]; po_id = po.get("id", "")
                break
    if not supplier_id:
        raise ValueError("Supplier asal tidak dapat ditentukan otomatis — pilih supplier secara manual.")

    # Grup per produk → item + roll_ids + qty + harga (WAC dari roll).
    by_prod: Dict[str, Dict[str, Any]] = {}
    for r in rolls:
        pid = r.get("product_id")
        g = by_prod.setdefault(pid, {"qty": 0.0, "roll_ids": [], "cost_sum": 0.0, "cost_n": 0})
        ln = float(r.get("length_remaining", 0) or 0)
        g["qty"] += ln
        g["roll_ids"].append(r["id"])
        c = float(r.get("unit_cost") or r.get("base_unit_cost") or 0)
        if c > 0:
            g["cost_sum"] += c; g["cost_n"] += 1
    items = [PurchaseReturnItem(
        product_id=pid, quantity=round(g["qty"], 2), unit="meter",
        price=round(g["cost_sum"] / g["cost_n"], 2) if g["cost_n"] else 0.0,
        reason=reason or "cacat", condition="damaged", roll_ids=g["roll_ids"],
    ) for pid, g in by_prod.items()]

    payload = PurchaseReturnCreate(
        supplier_id=supplier_id, po_id=po_id, warehouse_id=wh_id, items=items,
        reason=reason or "Retur ke supplier (barang cacat dari retur jual)", notes=notes,
        entity_id=entity_id, submit_now=True, created_by=actor,
        supplier_flow=True, origin_sales_return_id=sales_return_id,
        bypass_import_policy=bypass_import_policy,
    )
    pr = await create_purchase_return(payload, created_by=actor)

    # Tautkan 2 arah.
    await db.purchase_returns.update_one({"id": pr["id"]},
        {"$set": {"origin_sales_return_number": sr.get("number", ""), "updated_at": now_iso()}})
    await db.sales_returns.update_one({"id": sales_return_id},
        {"$set": {"linked_purchase_return_id": pr["id"],
                  "linked_purchase_return_number": pr["number"], "updated_at": now_iso()}})
    pr["origin_sales_return_number"] = sr.get("number", "")
    return pr


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _consume_available_rolls(product_id, warehouse_id, owner_entity_id, qty, ret) -> float:
    """Kurangi roll available (FIFO) sebesar qty → status returned_supplier / split.
    Catat movement return_out. Return total qty yang berhasil dikurangi."""
    rolls = await db.inventory_rolls.find(
        {"product_id": product_id, "warehouse_id": warehouse_id,
         "owner_entity_id": owner_entity_id, "status": "available",
         "length_remaining": {"$gt": 0}}, {"_id": 0}).to_list(10000)
    rolls.sort(key=lambda r: (r.get("created_at", ""), float(r.get("length_remaining", 0))))
    remaining = round(float(qty), 2)
    consumed = 0.0
    for roll in rolls:
        if remaining <= 0.01:
            break
        rlen = float(roll["length_remaining"])
        take = min(rlen, remaining)
        if take >= rlen - 0.01:
            await db.inventory_rolls.update_one(
                {"id": roll["id"]},
                {"$set": {"status": RETURNED_STATUS, "returned_ref": {"type": "purchase_return", "id": ret["id"]},
                          "updated_at": now_iso()}})
        else:
            await db.inventory_rolls.update_one(
                {"id": roll["id"]},
                {"$set": {"length_remaining": round(rlen - take, 2),
                          "length_initial": round(float(roll["length_initial"]) - take, 2),
                          "updated_at": now_iso()}})
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": product_id, "warehouse_id": warehouse_id,
            "owner_entity_id": owner_entity_id, "type": "return_out", "movement_type": "return_out",
            "direction": "out", "quantity": -round(take, 2), "unit": roll.get("unit", "meter"),
            "roll_id": roll["id"],
            # FASE U — satu baris mutasi menunjuk SATU roll fisik.
            "qty_rolls": (1 if roll["id"] else None), "ref_type": "purchase_return", "ref_id": ret["id"],
            "source_document": ret["number"], "lot": roll.get("lot", ""),
            "notes": f"Retur beli {ret['number']} ke {ret.get('supplier_name','')}",
            "timestamp": now_iso(),
        })
        consumed = round(consumed + take, 2)
        remaining = round(remaining - take, 2)
    return consumed


async def _consume_specific_rolls(roll_ids, owner_entity_id, qty, ret) -> float:
    """Retur PRESISI — kurangi roll/lot SPESIFIK yang dipilih user (bukan FIFO).
    Menelusuri roll asal supplier/invoice tertentu. Return total qty yang dikurangi."""
    rolls = await db.inventory_rolls.find(
        {"id": {"$in": list(roll_ids)}, "length_remaining": {"$gt": 0}}, {"_id": 0}).to_list(10000)
    # jaga urutan sesuai pilihan user
    order = {rid: i for i, rid in enumerate(roll_ids)}
    rolls.sort(key=lambda r: order.get(r["id"], 9999))
    remaining = round(float(qty), 2)
    consumed = 0.0
    for roll in rolls:
        if remaining <= 0.01:
            break
        rlen = float(roll["length_remaining"])
        take = min(rlen, remaining)
        if take >= rlen - 0.01:
            await db.inventory_rolls.update_one(
                {"id": roll["id"]},
                {"$set": {"status": RETURNED_STATUS, "returned_ref": {"type": "purchase_return", "id": ret["id"]},
                          "updated_at": now_iso()}})
        else:
            await db.inventory_rolls.update_one(
                {"id": roll["id"]},
                {"$set": {"length_remaining": round(rlen - take, 2),
                          "length_initial": round(float(roll["length_initial"]) - take, 2),
                          "updated_at": now_iso()}})
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": roll.get("product_id", ""),
            "warehouse_id": roll.get("warehouse_id", ""), "owner_entity_id": owner_entity_id,
            "type": "return_out", "movement_type": "return_out", "direction": "out",
            "quantity": -round(take, 2), "unit": roll.get("unit", "meter"), "roll_id": roll["id"],
 # FASE U — satu baris mutasi menunjuk SATU roll fisik.
 "qty_rolls": (1 if roll["id"] else None),
            "ref_type": "purchase_return", "ref_id": ret["id"], "source_document": ret["number"],
            "lot": roll.get("lot", ""),
            "notes": f"Retur beli PRESISI {ret['number']} (roll {roll.get('roll_no','')}, lot {roll.get('lot','')}) "
                     f"→ {ret.get('supplier_name','')}",
            "timestamp": now_iso(),
        })
        consumed = round(consumed + take, 2)
        remaining = round(remaining - take, 2)
    return consumed


def _po_item_price(po, product_id) -> float:
    if not po:
        return 0.0
    for it in po.get("items", []):
        if it.get("product_id") == product_id:
            return float(it.get("price", 0) or 0)
    return 0.0


async def _wh_name(warehouse_id) -> str:
    if not warehouse_id:
        return ""
    wh = await db.warehouses.find_one({"id": warehouse_id}, {"_id": 0, "name": 1})
    return (wh or {}).get("name", "")


# ─── R5.4b — REVERSAL / KOREKSI retur beli (Nota Debit) ──────────────────────

async def reverse_settlement(return_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
    """R5.4b — Batalkan/koreksi retur beli yang sudah DIFINALISASI (barang keluar + Nota Debit + GL),
    aman terhadap integritas (append-only, idempotent).

    Membalik (pola sama dgn reversal retur jual):
      a) JE `purchase_return` (Persediaan/Hutang-GRIR/Kas + reversal PPN) dibalik (Dr↔Cr → net 0).
      b) Barang DIKEMBALIKAN ke persediaan: roll `returned_supplier` → available (length utuh) atau
         length parsial dipulihkan; catat movement `return_out_reversal` + rebuild_balance.
      c) AP PO dipulihkan (bila ap_credit): `returned_amount` dikurangi + recompute status bayar PO.
      d) Refund kas di-void (bila refund).
      e) Nota Debit di-void (nomor disimpan utk audit) + status → `cancelled` + metadata reversal.

    Guard: hanya retur terfinalisasi (stock_adjusted & supplier ACCEPTED); belum di-reversal;
    roll retur (yg dikonsumsi penuh) masih `returned_supplier` & tak dipesan/dikomit transaksi lain.
    """
    ret = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise ValueError("Retur beli tidak ditemukan")
    # Idempotent — sudah dibatalkan/di-reversal.
    if ret.get("reversed") or ret.get("status") == "cancelled":
        return safe_doc(ret)
    if not ret.get("stock_adjusted") or ret.get("supplier_status") != prs.ACCEPTED:
        raise ValueError(
            "Hanya retur beli yang sudah difinalisasi (barang keluar + Nota Debit + jurnal GL) "
            f"yang bisa di-reversal. Status: '{ret.get('status')}' / supplier: "
            f"'{prs.SUPPLIER_STATUS_LABEL.get(ret.get('supplier_status') or '', '—')}'.")

    now = now_iso()
    outcome = (ret.get("supplier_outcome") or prs.OUTCOME_AP_CREDIT).lower()
    is_refund = outcome == prs.OUTCOME_REFUND

    # Kumpulkan movement konsumsi (return_out) sebagai SSOT roll yang dikeluarkan.
    movements = await db.inventory_movements.find(
        {"ref_type": "purchase_return", "ref_id": return_id, "type": "return_out"}, {"_id": 0}
    ).to_list(10000)
    rolls_by_id: Dict[str, Dict[str, Any]] = {}
    for rid in {m.get("roll_id") for m in movements if m.get("roll_id")}:
        r = await db.inventory_rolls.find_one({"id": rid}, {"_id": 0})
        if r:
            rolls_by_id[rid] = r

    # ── GUARDS ──────────────────────────────────────────────────────────────
    # Roll retur harus masih ada agar bisa dikembalikan. (Roll yang dikonsumsi PENUH
    # kini 'returned_supplier' = terminal/keluar ke supplier — aman dipulihkan; tak perlu
    # cek reservasi karena roll tidak mungkin dikomit selagi berstatus returned_supplier.)
    for m in movements:
        rid = m.get("roll_id")
        roll = rolls_by_id.get(rid)
        if not roll:
            raise ValueError(
                f"Roll sumber retur (id {rid}) sudah tidak ada. Reversal otomatis tidak aman — "
                "lakukan koreksi manual di jurnal.")

    # ── ACTIONS (idempotent) ─────────────────────────────────────────────────
    from services import gl_service
    # a) Balik JE retur beli.
    rev_jes = await gl_service.reverse_document(
        "purchase_return", return_id,
        reason=reason or "Pembatalan/koreksi retur beli", actor_name=actor)

    # b) Kembalikan barang ke persediaan (undo konsumsi roll).
    combos: set = set()
    restored = 0
    for m in movements:
        rid = m.get("roll_id")
        roll = rolls_by_id.get(rid)
        if not roll:
            continue
        qty = abs(round(float(m.get("quantity", 0) or 0), 2))
        if roll.get("status") == RETURNED_STATUS:
            # dikonsumsi PENUH → kembalikan status available (length masih utuh).
            await db.inventory_rolls.update_one({"id": rid}, {"$set": {
                "status": "available", "returned_ref": None,
                "unreturned_at": now, "unreturned_by": actor, "updated_at": now}})
        else:
            # dikonsumsi PARSIAL (length dikurangi) → tambahkan kembali length.
            await db.inventory_rolls.update_one({"id": rid}, {
                "$inc": {"length_remaining": qty, "length_initial": qty},
                "$set": {"updated_at": now}})
        await db.inventory_movements.insert_one({
            "id": new_id("mov"), "product_id": roll.get("product_id", ""),
            "warehouse_id": roll.get("warehouse_id", ""),
            "owner_entity_id": roll.get("owner_entity_id", ""),
            "type": "return_out_reversal", "movement_type": "return_out_reversal", "direction": "in",
            "quantity": qty, "unit": roll.get("unit", "meter"), "roll_id": rid,
 # FASE U — satu baris mutasi menunjuk SATU roll fisik.
 "qty_rolls": (1 if rid else None),
            "ref_type": "purchase_return", "ref_id": return_id,
            "source_document": ret.get("number", ""),
            "notes": f"Reversal retur beli {ret.get('number','')} — barang dikembalikan ke stok",
            "timestamp": now})
        restored += 1
        if roll.get("product_id") and roll.get("warehouse_id"):
            combos.add((roll["product_id"], roll["warehouse_id"], roll.get("owner_entity_id", "")))
    for (pid, wid, eid) in combos:
        await rebuild_balance(pid, wid, eid)

    # c) Pulihkan AP PO (ap_credit) — kembalikan returned_amount.
    if ret.get("po_id") and not is_refund:
        await db.purchase_orders.update_one(
            {"id": ret["po_id"]},
            {"$inc": {"returned_amount": -float(ret.get("total_amount", 0) or 0)},
             "$set": {"updated_at": now}})
        try:
            from routers.purchase_orders import recompute_po_payment_status
            await recompute_po_payment_status(ret["po_id"])
        except Exception:  # noqa: BLE001
            pass

    # d) Void refund kas (refund).
    if is_refund:
        await db.cash_transactions.update_many(
            {"ref_type": "purchase_return", "ref_id": return_id, "status": {"$ne": "void"}},
            {"$set": {"status": "void", "voided_by": actor, "void_reason": reason,
                      "updated_at": now}})

    # e) Void Nota Debit + status → cancelled + metadata reversal (append-only).
    await db.purchase_returns.update_one({"id": return_id}, {"$set": {
        "status": "cancelled", "reversed": True, "reversed_by": actor, "reversed_at": now,
        "reversal_reason": reason, "reversal_je_ids": [j.get("id") for j in rev_jes],
        "debit_note_voided": True, "stock_adjusted": False, "updated_at": now}})

    fresh = await db.purchase_returns.find_one({"id": return_id}, {"_id": 0})
    fresh = safe_doc(fresh)
    fresh["_reversal_summary"] = {"reversal_jes": len(rev_jes), "rolls_restored": restored,
                                  "outcome": outcome, "refund_voided": is_refund}
    return fresh
