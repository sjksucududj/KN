"""RFQ / Quotation service — Fase 6.1 (P1 Sourcing).

Tender pengadaan: undang beberapa supplier → kumpulkan penawaran (quote) → banding
harga (matriks per item × supplier) → award (penuh atau per-baris) → konversi ke PO,
sekaligus upsert Supplier Price-List dari harga pemenang.

Keputusan desain owner:
  - Sumber RFQ: dari PR approved (tarik item) ATAU standalone manual.
  - Quote: purchaser input manual harga per supplier yang diundang.
  - Award: dukung FULL (1 supplier → 1 PO) dan PER-LINE (split → beberapa PO).
  - Compare: matriks item×supplier + harga terendah + total per supplier + rekomendasi.
  - Award → upsert `supplier_price_lists` dari harga pemenang (source=rfq_award).

Koleksi kanonik: `rfqs` (prefix rfq_). Status: draft → open → awarded | cancelled.
"""
from typing import Any, Dict, List, Optional
from db import db
from core_utils import now_iso, new_id, DEFAULT_ENTITY_ID, safe_doc, timeline_entry, next_doc_number, rupiah
from services.config_service import evaluate_approval, compute_order_pricing, get_effective_settings

OPEN_STATUSES = {"draft", "open"}


async def next_rfq_number() -> str:
    last = await db.rfqs.find_one({}, {"_id": 0, "rfq_number": 1}, sort=[("rfq_number", -1)])
    n = 0
    if last and isinstance(last.get("rfq_number"), str) and last["rfq_number"].startswith("RFQ-"):
        try:
            n = int(last["rfq_number"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.rfqs.count_documents({})
    else:
        n = await db.rfqs.count_documents({})
    return f"RFQ-{n + 1:05d}"


async def build_items_from_products(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalisasi baris item RFQ (wajib product_id katalog)."""
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(2000)}
    items: List[Dict[str, Any]] = []
    for i, it in enumerate(raw_items):
        prod = products.get(it.get("product_id"))
        if not prod:
            raise ValueError(f"Produk {it.get('product_id')} tidak ditemukan di katalog")
        qty = float(it.get("quantity", 0) or 0)
        if qty <= 0:
            raise ValueError(f"Qty item {prod.get('sku')} harus > 0")
        items.append({
            "line_id": it.get("line_id") or f"L{i + 1}",
            "product_id": prod["id"], "sku": prod.get("sku", ""),
            "product_name": prod.get("name", ""),
            "quantity": qty,
            "unit": (it.get("unit") or prod.get("base_unit", "meter")),
            "note": it.get("note", ""),
            # FASE U — dua satuan (rencana jumlah roll saat meminta penawaran).
            "qty_rolls": (None if it.get("qty_rolls") in (None, "") else int(it["qty_rolls"])),
            **({"unit_factor": float(it["unit_factor"]),
                "unit_factor_to": it.get("unit_factor_to", "")} if it.get("unit_factor") else {}),
        })
    return items


async def build_suppliers(supplier_ids: List[str]) -> List[Dict[str, Any]]:
    """Bentuk daftar supplier yang diundang (quote_status=pending)."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for sid in supplier_ids:
        if not sid or sid in seen:
            continue
        seen.add(sid)
        sup = await db.suppliers.find_one({"id": sid}, {"_id": 0})
        if not sup:
            raise ValueError(f"Supplier {sid} tidak ditemukan")
        # FASE E-7 (E7.2) — RFQ adalah undangan menawar ke pemasok LUAR. Badan usaha
        # grup tidak menawar: harganya diatur kontrak internal. HTTPException di sini
        # SENGAJA (bukan ValueError) supaya kalimat menuntunnya sampai ke pengguna utuh.
        from services import group_partner_service as _grp
        await _grp.assert_supplier_not_group_entity(sup, doc_label="Permintaan Penawaran (RFQ)")
        out.append({
            "supplier_id": sid, "supplier_name": sup.get("name", ""),
            "quote_status": "pending", "quoted_at": "", "valid_until": "",
            "lead_time_days": 0, "note": "", "lines": [], "total": 0.0,
        })
    if not out:
        raise ValueError("Minimal 1 supplier diundang")
    return out


def supplier_total(rfq: Dict[str, Any], sup: Dict[str, Any]) -> float:
    """Total penawaran supplier = Σ (harga × qty) untuk baris available yang diisi."""
    qty_by_line = {it["line_id"]: float(it["quantity"]) for it in rfq.get("items", [])}
    total = 0.0
    for ln in sup.get("lines", []):
        if ln.get("available", True) and float(ln.get("price", 0) or 0) > 0:
            total += float(ln["price"]) * qty_by_line.get(ln["line_id"], 0.0)
    return round(total, 2)


def build_compare(rfq: Dict[str, Any]) -> Dict[str, Any]:
    """Matriks perbandingan item×supplier + harga terendah/line + total + rekomendasi.

    Rekomendasi FULL = supplier dgn total terendah yang mengisi SEMUA baris (lengkap);
    bila tak ada yang lengkap → total terendah di antara yang sudah quote.
    Rekomendasi PER-LINE = supplier harga termurah per baris.
    """
    items = rfq.get("items", [])
    line_ids = [it["line_id"] for it in items]
    quoted = [s for s in rfq.get("suppliers", []) if s.get("quote_status") == "quoted"]

    # peta harga per (supplier, line)
    price_map: Dict[str, Dict[str, Optional[float]]] = {}
    for s in quoted:
        pm: Dict[str, Optional[float]] = {}
        for ln in s.get("lines", []):
            if ln.get("available", True) and float(ln.get("price", 0) or 0) > 0:
                pm[ln["line_id"]] = float(ln["price"])
        price_map[s["supplier_id"]] = pm

    lowest_per_line: Dict[str, Dict[str, Any]] = {}
    line_awards: List[Dict[str, Any]] = []
    for lid in line_ids:
        best_sid, best_price = "", None
        for s in quoted:
            p = price_map.get(s["supplier_id"], {}).get(lid)
            if p is not None and (best_price is None or p < best_price):
                best_price, best_sid = p, s["supplier_id"]
        lowest_per_line[lid] = {"supplier_id": best_sid, "price": best_price}
        if best_sid:
            line_awards.append({"line_id": lid, "supplier_id": best_sid, "price": best_price})

    totals = []
    for s in quoted:
        complete = all(price_map.get(s["supplier_id"], {}).get(lid) is not None for lid in line_ids)
        totals.append({
            "supplier_id": s["supplier_id"], "supplier_name": s["supplier_name"],
            "total": supplier_total(rfq, s), "complete": complete,
            "lead_time_days": s.get("lead_time_days", 0), "valid_until": s.get("valid_until", ""),
        })

    complete_totals = [t for t in totals if t["complete"]]
    pool = complete_totals or totals
    recommended_full = min(pool, key=lambda t: t["total"])["supplier_id"] if pool else ""

    return {
        "items": items, "suppliers": totals, "price_map": price_map,
        "lowest_per_line": lowest_per_line,
        "recommended_full_supplier_id": recommended_full,
        "recommended_line_awards": line_awards,
    }


async def _upsert_price_list(supplier: Dict[str, Any], item: Dict[str, Any],
                             price: float, entity_id: str, actor_name: str) -> None:
    """Upsert harga pemenang ke supplier_price_lists (tier min_qty=0, source rfq_award)."""
    if float(price or 0) <= 0:
        return
    q = {"supplier_id": supplier["supplier_id"], "product_id": item["product_id"],
         "min_qty": 0.0, "status": "active"}
    existing = await db.supplier_price_lists.find_one(q, {"_id": 0, "id": 1})
    now = now_iso()
    if existing:
        await db.supplier_price_lists.update_one(
            {"id": existing["id"]},
            {"$set": {"price": round(float(price), 2), "unit": item.get("unit", "meter"),
                      "source": "rfq_award", "updated_at": now}})
    else:
        await db.supplier_price_lists.insert_one({
            "id": new_id("spl"), "supplier_id": supplier["supplier_id"],
            "supplier_name": supplier.get("supplier_name", ""),
            "product_id": item["product_id"], "sku": item.get("sku", ""),
            "product_name": item.get("product_name", ""),
            "price": round(float(price), 2), "unit": item.get("unit", "meter"),
            "min_qty": 0.0, "lead_time_days": int(supplier.get("lead_time_days", 0) or 0),
            "valid_from": "", "valid_until": supplier.get("valid_until", "") or "",
            "currency": "IDR", "entity_id": entity_id, "notes": "Auto dari RFQ award",
            "status": "active", "source": "rfq_award",
            "created_by": actor_name, "created_at": now, "updated_at": now})


async def _create_po_from_lines(supplier_id: str, lines: List[Dict[str, Any]],
                                entity_id: str, warehouse: Dict[str, Any], actor: Dict[str, Any],
                                rfq: Dict[str, Any]) -> Dict[str, Any]:
    """Buat 1 PO dari baris award (mirror PR→PO: pricing P0-1, approval, inbound tasks)."""
    from routers.purchase_orders import _create_inbound_tasks_for_po
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise ValueError(f"Supplier {supplier_id} tidak ditemukan")

    raw_items = [{
        "product_id": ln["product_id"], "sku": ln["sku"], "product_name": ln["product_name"],
        "quantity": float(ln["quantity"]), "unit": ln.get("unit", "meter"),
        "price": float(ln["price"]), "discount_percent": 0, "received_qty": 0.0,
    } for ln in lines]

    pricing = await compute_order_pricing(raw_items, entity_id, 0.0, cfg_section="purchasing")
    total_amount = pricing["total_amount"]
    grand_total = pricing["grand_total"]

    appr = await evaluate_approval("purchase_order", total_amount, entity_id)
    needs_approval = appr["requires_approval"]
    required_role = appr["required_role"]

    sup_contact = " | ".join([x for x in [supplier.get("pic_name", ""), supplier.get("phone", "")] if x])
    now = now_iso()
    po = {
        "id": new_id("po"), "po_number": await next_doc_number("purchase_orders", "po_number", "PO-", entity_id=entity_id),
        "supplier_id": supplier_id, "supplier_name": supplier.get("name", ""),
        "supplier_contact": sup_contact, "supplier_npwp": supplier.get("npwp", ""),
        "warehouse_id": warehouse["id"], "warehouse_name": warehouse.get("name", ""),
        "warehouse_city": warehouse.get("city", ""),
        "items": pricing["items"], "total_amount": total_amount, "entity_id": entity_id,
        "items_discount_total": pricing["items_discount_total"],
        "order_discount_percent": pricing["order_discount_percent"],
        "order_discount_amount": pricing["order_discount_amount"],
        "discount_total": pricing["discount_total"], "net_subtotal": pricing["net_subtotal"],
        "dpp": pricing["dpp"], "ppn_rate": pricing["ppn_rate"], "ppn_mode": pricing["ppn_mode"],
        "is_pkp": pricing["is_pkp"], "ppn_amount": pricing["ppn_amount"],
        "grand_total": grand_total, "tax_mode": "",
        "expected_delivery_date": rfq.get("needed_by_date", ""),
        "notes": f"Dari {rfq['rfq_number']}",
        "status": "waiting_approval" if needs_approval else "pending",
        "approval_required": needs_approval, "required_approval_role": required_role,
        "approval_status": "pending" if needs_approval else "not_required",
        "approval_amount": total_amount, "approval_reason": "amount_threshold" if needs_approval else "",
        "price_deviation": {"flagged": False},
        "amount_paid": 0.0, "returned_amount": 0.0, "outstanding": round(grand_total, 2),
        "payment_status": "unpaid", "payments": [],
        "source_rfq_id": rfq["id"], "source_rfq_number": rfq["rfq_number"],
        "source_pr_id": rfq.get("pr_id", ""), "source_pr_number": rfq.get("pr_number", ""),
        "timeline": [timeline_entry("created", f"PO dibuat dari {rfq['rfq_number']}",
                                    actor.get("name", "Admin"), f"{len(raw_items)} item · {rupiah(total_amount)}")],
        "created_by": actor.get("name", "Admin"), "created_by_id": actor.get("id", ""),
        "created_at": now, "updated_at": now,
    }
    # Fase A · PS-09/D-19 — PO hasil award RFQ: grade diturunkan dari master produk.
    from services import grade_service
    await grade_service.stamp_expected_grade(po["items"], allow_derive=True, context="PO dari RFQ")
    from services import line_scope as _lines            # FASE L
    await _lines.stamp_doc(db, po)
    await db.purchase_orders.insert_one(dict(po))
    if not needs_approval:
        await _create_inbound_tasks_for_po(po)
    else:
        try:
            from services.notification_service import notify_po_awaiting_approval
            await notify_po_awaiting_approval(po)
        except Exception:
            pass
    return safe_doc(po)


async def award_rfq(rfq: Dict[str, Any], mode: str, full_supplier_id: str,
                    line_awards: List[Dict[str, Any]], actor: Dict[str, Any]) -> Dict[str, Any]:
    """Award RFQ → buat PO (full: 1 PO; line: 1 PO per supplier) + upsert price-list."""
    entity_id = rfq.get("entity_id") or DEFAULT_ENTITY_ID
    warehouse = await db.warehouses.find_one({"id": rfq.get("warehouse_id")}, {"_id": 0})
    if not warehouse:
        raise ValueError("Gudang RFQ tidak valid — set gudang dulu")

    items_by_line = {it["line_id"]: it for it in rfq.get("items", [])}
    sup_by_id = {s["supplier_id"]: s for s in rfq.get("suppliers", [])}
    # kumpulan baris PO per supplier
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    def _price_of(sid: str, lid: str) -> float:
        s = sup_by_id.get(sid, {})
        for ln in s.get("lines", []):
            if ln["line_id"] == lid:
                return float(ln.get("price", 0) or 0)
        return 0.0

    if mode == "full":
        if not full_supplier_id or full_supplier_id not in sup_by_id:
            raise ValueError("Supplier pemenang (full) tidak valid")
        s = sup_by_id[full_supplier_id]
        if s.get("quote_status") != "quoted":
            raise ValueError("Supplier pemenang belum mengisi penawaran")
        for it in rfq["items"]:
            price = _price_of(full_supplier_id, it["line_id"])
            if price <= 0:
                raise ValueError(f"Supplier belum memberi harga untuk {it['sku']}")
            grouped.setdefault(full_supplier_id, []).append({**it, "price": price})
    elif mode == "line":
        if not line_awards:
            raise ValueError("line_awards wajib untuk award per-baris")
        awarded_lines = set()
        for la in line_awards:
            lid, sid = la.get("line_id"), la.get("supplier_id")
            if lid not in items_by_line:
                raise ValueError(f"line_id {lid} tidak ada di RFQ")
            if sid not in sup_by_id or sup_by_id[sid].get("quote_status") != "quoted":
                raise ValueError(f"Supplier {sid} belum quote untuk baris {lid}")
            price = float(la.get("price", 0) or 0) or _price_of(sid, lid)
            if price <= 0:
                raise ValueError(f"Harga 0 untuk baris {lid}")
            grouped.setdefault(sid, []).append({**items_by_line[lid], "price": price})
            awarded_lines.add(lid)
        if len(awarded_lines) != len(items_by_line):
            raise ValueError("Semua baris RFQ harus di-award ke supplier")
    else:
        raise ValueError("mode award harus 'full' atau 'line'")

    pos: List[Dict[str, Any]] = []
    for sid, lines in grouped.items():
        # FASE E-7 (E7.2) — undangan RFQ sudah dipagari, tetapi RFQ LAMA (dibuat sebelum
        # fase ini) bisa berisi badan usaha grup. Award-nya melahirkan PO biasa, jadi
        # pagarnya diulang tepat sebelum PO dibuat.
        from services import group_partner_service as _grp
        await _grp.assert_supplier_not_group_entity(
            await db.suppliers.find_one({"id": sid}, {"_id": 0}),
            doc_label="Pesanan Pembelian (PO) hasil award RFQ")
        po = await _create_po_from_lines(sid, lines, entity_id, warehouse, actor, rfq)
        pos.append(po)
        for ln in lines:
            await _upsert_price_list(sup_by_id[sid], ln, ln["price"], entity_id, actor.get("name", "Admin"))

    award = {
        "mode": mode, "awarded_by": actor.get("name", "Admin"), "awarded_at": now_iso(),
        "full_supplier_id": full_supplier_id if mode == "full" else "",
        "line_awards": line_awards if mode == "line" else
                       [{"line_id": it["line_id"], "supplier_id": full_supplier_id,
                         "price": _price_of(full_supplier_id, it["line_id"])} for it in rfq["items"]],
        "po_ids": [p["id"] for p in pos], "po_numbers": [p["po_number"] for p in pos],
    }
    await db.rfqs.update_one({"id": rfq["id"]}, {
        "$set": {"status": "awarded", "award": award, "updated_at": now_iso()},
        "$push": {"timeline": timeline_entry(
            "awarded", f"RFQ di-award ({mode}) → {len(pos)} PO",
            actor.get("name", "Admin"), ", ".join(award["po_numbers"]))}})

    # tautkan PR bila sumber dari PR
    if rfq.get("pr_id") and pos:
        pr = await db.purchase_requisitions.find_one({"id": rfq["pr_id"]}, {"_id": 0, "status": 1})
        if pr and pr.get("status") == "approved":
            await db.purchase_requisitions.update_one({"id": rfq["pr_id"]}, {"$set": {
                "status": "converted", "po_id": pos[0]["id"], "po_number": pos[0]["po_number"],
                "converted_by": actor.get("name", "Admin"), "converted_at": now_iso(),
                "updated_at": now_iso()}})

    return {"rfq": safe_doc(await db.rfqs.find_one({"id": rfq["id"]}, {"_id": 0})), "pos": pos}
