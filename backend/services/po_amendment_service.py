"""Phase 7.2 — PO Amendment / Version History (logic extracted from router).

Diekstrak dari `routers/purchase_orders.py` untuk menjaga batas ukuran file router
(≤800 baris) dan memisahkan domain logic amandemen.

Keputusan owner:
  - 1.c : boleh ubah item/supplier/gudang/tanggal/catatan.
  - 2.a : SELALU re-approval dari awal (rantai approval dibangun ulang dari nilai baru).
  - 3.b : boleh saat partial receiving — qty tak boleh < qty diterima; item ber-penerimaan
          tak bisa dihapus; gudang tak bisa diganti bila sudah ada penerimaan.
  - 4.a : simpan snapshot penuh sebelum amend + diff tiap versi (version increment).
  - 5.a : alasan WAJIB + audit.

Catatan integrasi (dipertahankan agar tidak regress):
  - Inbound task creation & notifikasi dilakukan oleh ROUTER (hindari circular import
    dengan `_create_inbound_tasks_for_po`). Service mengembalikan `needs_approval` + PO
    terbaru, lalu router memutuskan buat task / kirim notifikasi.
  - Vendor Bill tetap SSOT AP — amandemen TIDAK menyentuh pembayaran/hutang.
"""
from typing import Any, Dict, List

from fastapi import HTTPException

from db import db
from core_utils import now_iso, safe_doc, DEFAULT_ENTITY_ID, timeline_entry
from services.config_service import build_approval_chain, compute_order_pricing, get_effective_settings

AMENDABLE_STATUSES = {"waiting_approval", "pending", "receiving", "partial"}


def diff_po_items(old_items: List[Dict[str, Any]], new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Hitung perubahan item PO (tambah/hapus/ubah qty/harga/satuan)."""
    changes: List[Dict[str, Any]] = []
    old_by = {it["product_id"]: it for it in old_items}
    new_by = {it["product_id"]: it for it in new_items}
    for pid, nit in new_by.items():
        nm = nit.get("product_name") or nit.get("sku") or pid
        oit = old_by.get(pid)
        if not oit:
            changes.append({"field": "item_add", "label": f"Tambah item {nm}",
                            "from": "-", "to": f"{nit.get('quantity')} {nit.get('unit', '')} @ {nit.get('price', 0)}"})
            continue
        if abs(float(oit.get("quantity", 0) or 0) - float(nit.get("quantity", 0) or 0)) > 0.001:
            changes.append({"field": "item_qty", "label": f"Qty {nm}", "from": oit.get("quantity"), "to": nit.get("quantity")})
        if abs(float(oit.get("price", 0) or 0) - float(nit.get("price", 0) or 0)) > 0.001:
            changes.append({"field": "item_price", "label": f"Harga {nm}", "from": oit.get("price"), "to": nit.get("price")})
        if (oit.get("unit") or "") != (nit.get("unit") or ""):
            changes.append({"field": "item_unit", "label": f"Satuan {nm}", "from": oit.get("unit"), "to": nit.get("unit")})
    for pid, oit in old_by.items():
        if pid not in new_by:
            nm = oit.get("product_name") or oit.get("sku") or pid
            changes.append({"field": "item_remove", "label": f"Hapus item {nm}",
                            "from": f"{oit.get('quantity')} {oit.get('unit', '')}", "to": "-"})
    return changes


async def _resolve_supplier(po: Dict[str, Any], payload) -> Dict[str, Any]:
    """Resolve supplier baru (FK master / manual) — default = nilai PO lama."""
    sup = {
        "supplier_id": po.get("supplier_id", ""), "supplier_name": po.get("supplier_name", ""),
        "supplier_contact": po.get("supplier_contact", ""), "supplier_npwp": po.get("supplier_npwp", ""),
    }
    if payload.supplier_id:
        doc = safe_doc(await db.suppliers.find_one({"id": payload.supplier_id}, {"_id": 0}))
        if not doc:
            raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
        sup["supplier_id"] = doc["id"]
        sup["supplier_name"] = doc.get("name", "")
        sup["supplier_npwp"] = doc.get("npwp", "")
        sup["supplier_contact"] = " | ".join([x for x in [doc.get("pic_name", ""), doc.get("phone", "")] if x])
    elif payload.supplier_name is not None:
        sup["supplier_id"] = ""
        sup["supplier_name"] = payload.supplier_name.strip()
    if payload.supplier_contact is not None:
        sup["supplier_contact"] = payload.supplier_contact
    return sup


async def _resolve_warehouse(po: Dict[str, Any], payload, has_receipt: bool) -> Dict[str, Any]:
    """Resolve gudang baru. Dilarang ganti gudang bila sudah ada penerimaan (3.b)."""
    wh = {"id": po.get("warehouse_id"), "name": po.get("warehouse_name", ""), "city": po.get("warehouse_city", "")}
    if payload.warehouse_id and payload.warehouse_id != po.get("warehouse_id"):
        if has_receipt:
            raise HTTPException(status_code=400, detail="Tidak bisa ganti gudang: sudah ada barang diterima.")
        whx = safe_doc(await db.warehouses.find_one({"id": payload.warehouse_id}, {"_id": 0}))
        if not whx:
            raise HTTPException(status_code=404, detail="Warehouse tidak ditemukan")
        wh = {"id": whx["id"], "name": whx.get("name", ""), "city": whx.get("city", "")}
    return wh


async def _build_items(payload, old_items, received_map, supplier_id) -> List[Dict[str, Any]]:
    """Bangun daftar item baru + guard partial receiving (3.b)."""
    if payload.items is None:
        return [dict(it) for it in old_items]

    from services.uom_service import to_base, load_fixed_factors
    from services.supplier_service import resolve_price

    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(1000)}
    factors = await load_fixed_factors()
    new_pids = {it.product_id for it in payload.items}
    # Tidak boleh hapus item yang sudah diterima.
    for pid, rq in received_map.items():
        if rq > 0 and pid not in new_pids:
            nm = next((it.get("product_name") or it.get("sku") for it in old_items if it["product_id"] == pid), pid)
            raise HTTPException(status_code=400, detail=f"Item '{nm}' sudah diterima {rq:g}, tidak bisa dihapus.")
    raw_items: List[Dict[str, Any]] = []
    for item_in in payload.items:
        product = products.get(item_in.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Produk {item_in.product_id} tidak ditemukan")
        rq = received_map.get(item_in.product_id, 0)
        if float(item_in.quantity) < rq - 0.001:
            raise HTTPException(status_code=400, detail=(
                f"Qty {product['sku']} ({item_in.quantity:g}) tak boleh < qty diterima ({rq:g})."))
        price = float(item_in.price or 0)
        if price <= 0:
            resolved = await resolve_price(supplier_id, item_in.product_id, item_in.quantity)
            price = float(resolved.get("price", 0) or 0) or float(product.get("price", 0) or 0)
        base_unit = product.get("base_unit", "meter")
        order_unit = item_in.unit or base_unit
        if order_unit.strip().lower() == base_unit.strip().lower():
            qbase = round(float(item_in.quantity or 0), 2)
        else:
            try:
                qbase = to_base(product, float(item_in.quantity or 0), order_unit, factors)
            except HTTPException:
                qbase = round(float(item_in.quantity or 0), 2)
        raw_items.append({
            "product_id": product["id"], "sku": product["sku"], "product_name": product["name"],
            "quantity": item_in.quantity, "unit": item_in.unit, "base_unit": base_unit,
            "quantity_base": qbase, "price": price,
            "discount_percent": float(item_in.discount_percent or 0), "received_qty": rq,
        })
    return raw_items


async def _build_approval(entity_id, total_amount, supplier_id, items) -> Dict[str, Any]:
    """Bangun ulang rantai approval dari nilai baru (2.a) + cek deviasi harga."""
    from services.supplier_service import assess_price_deviation

    appr = await build_approval_chain("purchase_order", total_amount, entity_id)
    approval_chain = appr["approval_chain"]
    needs_approval = appr["requires_approval"]
    required_role = appr["required_role"]
    approval_reason = "amount_threshold" if needs_approval else ""

    settings = await get_effective_settings(entity_id)
    threshold = float(settings.get("purchasing", {}).get("price_deviation_approval_percent", 10.0) or 10.0)
    price_deviation = await assess_price_deviation(supplier_id, items, threshold) if supplier_id else \
        {"flagged": False, "threshold_pct": threshold, "max_deviation_pct": 0.0, "items": []}
    if price_deviation["flagged"]:
        if not approval_chain:
            appr = await build_approval_chain("purchase_order", total_amount, entity_id, force_level1_role="manager")
            approval_chain = appr["approval_chain"]
        needs_approval = True
        required_role = approval_chain[0]["required_role"] if approval_chain else "manager"
        approval_reason = "price_deviation" if approval_reason == "" else "amount_threshold+price_deviation"
    return {
        "approval_chain": approval_chain, "needs_approval": needs_approval,
        "required_role": required_role, "approval_reason": approval_reason, "price_deviation": price_deviation,
    }


async def amend_po(po_id: str, payload, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Amandemen PO + version history + re-approval penuh.

    Mengembalikan ``{"po": <PO terbaru>, "needs_approval": bool}``.
    Router bertanggung jawab membuat inbound task / mengirim notifikasi berdasar flag.
    """
    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Alasan amandemen wajib diisi.")
    po = safe_doc(await db.purchase_orders.find_one({"id": po_id}, {"_id": 0}))
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
    if po.get("status") not in AMENDABLE_STATUSES:
        raise HTTPException(status_code=400, detail=f"PO status '{po.get('status')}' tidak bisa diamandemen.")

    entity_id = po.get("entity_id") or DEFAULT_ENTITY_ID
    old_items = po.get("items", [])
    received_map = {it["product_id"]: float(it.get("received_qty", 0) or 0) for it in old_items}
    has_receipt = any(v > 0 for v in received_map.values())

    sup = await _resolve_supplier(po, payload)
    wh = await _resolve_warehouse(po, payload, has_receipt)
    raw_items = await _build_items(payload, old_items, received_map, sup["supplier_id"])

    # Recompute pricing (invariant-safe: total_amount tetap GROSS).
    order_disc = payload.order_discount_percent if payload.order_discount_percent is not None \
        else po.get("order_discount_percent", 0)
    tax_mode = payload.tax_mode if payload.tax_mode is not None else po.get("tax_mode", "")
    pricing = await compute_order_pricing(raw_items, entity_id, order_disc, cfg_section="purchasing", tax_override=tax_mode)
    items = pricing["items"]
    total_amount = pricing["total_amount"]
    grand_total = pricing["grand_total"]
    new_eta = payload.expected_delivery_date if payload.expected_delivery_date is not None \
        else po.get("expected_delivery_date", "")
    new_notes = payload.notes if payload.notes is not None else po.get("notes", "")

    appr = await _build_approval(entity_id, total_amount, sup["supplier_id"], items)
    needs_approval = appr["needs_approval"]
    approval_chain = appr["approval_chain"]

    # Diff + snapshot (4.a).
    changes = diff_po_items(old_items, items)

    def _addc(field, label, frm, to):
        if str(frm) != str(to):
            changes.append({"field": field, "label": label, "from": frm, "to": to})

    _addc("supplier", "Supplier", po.get("supplier_name", ""), sup["supplier_name"])
    _addc("warehouse", "Gudang", po.get("warehouse_name", ""), wh.get("name", ""))
    _addc("expected_delivery_date", "Tgl Kirim", po.get("expected_delivery_date", "") or "-", new_eta or "-")
    _addc("notes", "Catatan", po.get("notes", "") or "-", new_notes or "-")
    _addc("total", "Subtotal (GROSS)", po.get("total_amount", 0), total_amount)
    _addc("grand_total", "Grand Total", po.get("grand_total", 0), grand_total)

    new_version = int(po.get("version", 1) or 1) + 1
    snapshot_before = {
        "version": int(po.get("version", 1) or 1),
        "supplier_name": po.get("supplier_name", ""), "warehouse_name": po.get("warehouse_name", ""),
        "expected_delivery_date": po.get("expected_delivery_date", ""), "notes": po.get("notes", ""),
        "items": [{"sku": it.get("sku"), "product_name": it.get("product_name"), "quantity": it.get("quantity"),
                   "unit": it.get("unit"), "price": it.get("price"), "received_qty": it.get("received_qty", 0)}
                  for it in old_items],
        "total_amount": po.get("total_amount", 0), "grand_total": po.get("grand_total", 0),
        "status_before": po.get("status"),
    }
    amendment = {
        "version": new_version, "reason": reason, "changes": changes, "snapshot_before": snapshot_before,
        "amended_by": payload.amended_by or actor.get("name", "Admin"),
        "amended_by_id": actor.get("id", ""), "amended_at": now_iso(),
    }

    # Hapus inbound task 0-diterima (dibuat ulang saat re-approval/auto oleh router).
    await db.wms_tasks.delete_many({"po_id": po_id, "flow_type": "inbound",
                                    "received_qty": {"$lte": 0}, "status": {"$nin": ["completed", "cancelled"]}})

    paid = float(po.get("amount_paid", 0) or 0)
    returned = float(po.get("returned_amount", 0) or 0)
    update = {
        "supplier_id": sup["supplier_id"], "supplier_name": sup["supplier_name"],
        "supplier_contact": sup["supplier_contact"], "supplier_npwp": sup["supplier_npwp"],
        "warehouse_id": wh.get("id"), "warehouse_name": wh.get("name", ""), "warehouse_city": wh.get("city", ""),
        "items": items, "total_amount": total_amount,
        "items_discount_total": pricing["items_discount_total"], "order_discount_percent": pricing["order_discount_percent"],
        "order_discount_amount": pricing["order_discount_amount"], "discount_total": pricing["discount_total"],
        "net_subtotal": pricing["net_subtotal"], "dpp": pricing["dpp"], "ppn_rate": pricing["ppn_rate"],
        "ppn_mode": pricing["ppn_mode"], "is_pkp": pricing["is_pkp"], "ppn_amount": pricing["ppn_amount"],
        "grand_total": grand_total, "tax_mode": tax_mode, "expected_delivery_date": new_eta, "notes": new_notes,
        "status": "waiting_approval" if needs_approval else "pending",
        "approval_required": needs_approval, "required_approval_role": appr["required_role"],
        "approval_status": "pending" if needs_approval else "not_required", "approval_chain": approval_chain,
        "approval_level_current": (approval_chain[0]["level"] if (needs_approval and approval_chain) else 0),
        "approval_levels_total": len(approval_chain), "approval_amount": total_amount,
        "approval_reason": appr["approval_reason"], "price_deviation": appr["price_deviation"],
        "outstanding": round(max(grand_total - paid - returned, 0), 2),
        "version": new_version, "updated_at": now_iso(),
    }
    note = f"{reason} · {len(changes)} perubahan"
    tl = timeline_entry("amended", f"PO diamandemen → v{new_version}", amendment["amended_by"],
                        f"{note} · perlu re-approval" if needs_approval else note)
    await db.purchase_orders.update_one({"id": po_id}, {"$set": update,
                                         "$push": {"amendments": amendment, "timeline": tl}})

    from dependencies import audit
    await audit(actor["name"], "po_amended", "purchase_order", po_id, {
        "po_number": po.get("po_number"), "version": new_version, "reason": reason,
        "changes": len(changes), "new_total": total_amount, "re_approval": needs_approval})

    updated_full = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    return {"po": updated_full, "needs_approval": needs_approval}
