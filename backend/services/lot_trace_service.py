"""FASE C — Silsilah (genealogi), Recall, dan Label lot.

Dipisah dari `lot_service` agar file tetap kecil & satu tanggung jawab:
  * `genealogy()` — graph parent/child siap render (nodes + edges + rantai stage).
  * `recall()`    — dampak hilir sebuah lot: roll → SO/pengiriman → pelanggan
                    (keputusan pemilik 5d) + dokumen asal (PO/GR/makloon/WO).
  * `label()`     — payload label/QR memakai `label_printer_service` yang SUDAH ADA
                    (keputusan pemilik 5c — bukan mesin label kedua).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core_utils import safe_doc
from db import db
from services import lot_service as ls
from services.label_printer_service import generate_label

ROLLS = "inventory_rolls"
COLL = ls.COLL


def _node(lot: Dict[str, Any], relation: str, depth: int) -> Dict[str, Any]:
    return {
        "id": lot["id"], "lot_number": lot.get("lot_number", ""),
        "relation": relation, "depth": depth,
        "product_id": lot.get("product_id", ""), "sku": lot.get("sku", ""),
        "product_name": lot.get("product_name", ""),
        "stage": lot.get("stage", ""), "fabric_type": lot.get("fabric_type", ""),
        "source": lot.get("source", ""), "source_label": ls.SOURCE_LABELS.get(lot.get("source", ""), ""),
        "source_ref": lot.get("source_ref") or {},
        "lot_status": lot.get("lot_status", ""),
        "dye_lot": lot.get("dye_lot", ""), "supplier_lot": lot.get("supplier_lot", ""),
        "process": lot.get("process") or {},
        "roll_count": lot.get("roll_count", 0),
        "qty_remaining": lot.get("qty_remaining", 0), "unit": lot.get("unit", ""),
        "created_at": lot.get("created_at", ""),
        "parent_lot_ids": lot.get("parent_lot_ids") or [],
        "child_lot_ids": lot.get("child_lot_ids") or [],
    }


async def _walk(start: str, key: str, max_depth: int) -> Dict[str, int]:
    """BFS satu arah → {lot_id: depth} (tanpa lot awal)."""
    out: Dict[str, int] = {}
    frontier = [start]
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        nxt: List[str] = []
        docs = await db[COLL].find({"id": {"$in": frontier}},
                                  {"_id": 0, "id": 1, key: 1}).to_list(2000)
        for d in docs:
            for rel in d.get(key) or []:
                if rel != start and rel not in out:
                    out[rel] = depth
                    nxt.append(rel)
        frontier = nxt
    return out


async def genealogy(lot_id: str, max_depth: int = 6) -> Dict[str, Any]:
    """Silsilah lengkap: leluhur (hulu) + turunan (hilir) + dokumen pembentuk."""
    lot = await ls.get_lot(lot_id)
    ups = await _walk(lot["id"], "parent_lot_ids", max_depth)
    downs = await _walk(lot["id"], "child_lot_ids", max_depth)
    ids = set(ups) | set(downs)
    docs = {d["id"]: d for d in await db[COLL].find({"id": {"$in": list(ids)}},
                                                   {"_id": 0}).to_list(2000)}
    nodes = [_node(lot, "self", 0)]
    for lid, depth in sorted(ups.items(), key=lambda kv: kv[1]):
        if lid in docs:
            nodes.append(_node(docs[lid], "ancestor", -depth))
    for lid, depth in sorted(downs.items(), key=lambda kv: kv[1]):
        if lid in docs:
            nodes.append(_node(docs[lid], "descendant", depth))
    known = {n["id"] for n in nodes}
    edges = []
    for n in nodes:
        for pid in n["parent_lot_ids"]:
            if pid in known:
                edges.append({"from": pid, "to": n["id"]})
    # rantai stage (benang → grey → PFD/PFP → finished) untuk ringkasan naratif
    chain = []
    for n in sorted(nodes, key=lambda x: (x["depth"], x["created_at"])):
        label = n["stage"] or "?"
        if not chain or chain[-1]["stage"] != label:
            chain.append({"stage": label, "lots": [n["lot_number"]],
                          "process": (n["process"] or {}).get("process_type", "")})
        else:
            chain[-1]["lots"].append(n["lot_number"])
    return {"lot": lot, "nodes": nodes, "edges": edges, "chain": chain,
            "ancestor_count": len(ups), "descendant_count": len(downs),
            "documents": await source_documents(nodes)}


async def source_documents(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dokumen pembentuk tiap lot pada graph (PO/GR, order makloon, work order)."""
    out: List[Dict[str, Any]] = []
    for n in nodes:
        ref = n.get("source_ref") or {}
        rtype, rid = ref.get("type", ""), ref.get("id", "")
        item = {"lot_number": n["lot_number"], "source": n["source"],
                "source_label": n.get("source_label", ""), "ref_type": rtype,
                "ref_id": rid, "ref_number": ref.get("number", ""), "detail": {}}
        if rtype == "wms_task" and rid:
            task = await db.wms_tasks.find_one({"id": rid},
                                              {"_id": 0, "po_number": 1, "po_id": 1,
                                               "supplier_name": 1, "completed_at": 1,
                                               "type": 1}) or {}
            item["detail"] = safe_doc(task)
        elif rtype == "purchase_order" and rid:
            po = await db.purchase_orders.find_one({"id": rid},
                                                  {"_id": 0, "po_number": 1,
                                                   "supplier_name": 1, "status": 1}) or {}
            item["detail"] = safe_doc(po)
        elif rtype == "makloon_order" and rid:
            mko = await db.makloon_orders.find_one({"id": rid},
                                                  {"_id": 0, "mko_number": 1, "status": 1,
                                                   "makloon_name": 1, "process_type": 1}) or {}
            item["detail"] = safe_doc(mko)
        elif rtype == "work_order" and rid:
            wo = await db.mfg_work_orders.find_one({"id": rid},
                                                   {"_id": 0, "wo_number": 1, "status": 1,
                                                    "product_name": 1}) or {}
            item["detail"] = safe_doc(wo)
        out.append(item)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# RECALL — dampak hilir lot (keputusan pemilik 5d)
# ═══════════════════════════════════════════════════════════════════════════
async def recall(lot_id: str, *, include_descendants: bool = True) -> Dict[str, Any]:
    """Dari lot → semua roll → semua SO/pengiriman/pelanggan terdampak."""
    lot = await ls.get_lot(lot_id)
    lot_ids = [lot["id"]]
    if include_descendants:
        downs = await _walk(lot["id"], "child_lot_ids", 6)
        lot_ids.extend(downs.keys())
    lots = {d["id"]: d for d in await db[COLL].find({"id": {"$in": lot_ids}},
                                                   {"_id": 0}).to_list(2000)}
    rolls = await db[ROLLS].find({"lot_id": {"$in": lot_ids}}, {"_id": 0}).to_list(20000)
    roll_ids = [r["id"] for r in rolls]
    order_ids: set = set()
    for r in rolls:
        ref = r.get("reserved_ref") or {}
        if ref.get("type") == "sales_order" and ref.get("id"):
            order_ids.add(ref["id"])
        ear = r.get("earmarked_for") or {}
        if ear.get("type") in ("sales_order", "special_order") and ear.get("id"):
            order_ids.add(ear["id"])
    # jejak keluar barang (dispatch) — movement append-only menyimpan roll_id
    movs = await db.inventory_movements.find(
        {"roll_id": {"$in": roll_ids}},
        {"_id": 0, "movement_type": 1, "source_document": 1, "roll_id": 1,
         "quantity": 1, "timestamp": 1, "lot": 1}).sort("timestamp", -1).to_list(20000)
    dispatch_docs = {m.get("source_document") for m in movs
                     if m.get("movement_type") == "outbound_dispatch" and m.get("source_document")}
    shipments = await db.shipments.find(
        {"$or": [{"rolls": {"$in": roll_ids}}, {"order_id": {"$in": list(order_ids)}}]},
        {"_id": 0}).to_list(5000)
    order_ids.update({s.get("order_id") for s in shipments if s.get("order_id")})
    lot_numbers = [l.get("lot_number") for l in lots.values()]
    legacy_codes = [c for l in lots.values() for c in (l.get("legacy_lot_codes") or [])]
    by_alloc = await db.sales_orders.find(
        {"allocations.lots": {"$in": [*lot_numbers, *legacy_codes]}},
        {"_id": 0, "id": 1}).to_list(5000)
    order_ids.update({o["id"] for o in by_alloc})
    orders = await db.sales_orders.find(
        {"id": {"$in": list(order_ids)}},
        {"_id": 0, "id": 1, "number": 1, "customer_id": 1, "customer_name": 1,
         "customer_city": 1, "status": 1, "sub_status": 1, "grand_total": 1,
         "entity_id": 1, "created_at": 1, "dispatched_at": 1}).to_list(5000)
    customers: Dict[str, Dict[str, Any]] = {}
    for o in orders:
        cid = o.get("customer_id") or o.get("customer_name") or "?"
        cur = customers.setdefault(cid, {"customer_id": o.get("customer_id", ""),
                                         "customer_name": o.get("customer_name", ""),
                                         "city": o.get("customer_city", ""),
                                         "orders": [], "order_count": 0})
        cur["orders"].append(o.get("number", o.get("id")))
        cur["order_count"] += 1
    cust_ids = [c["customer_id"] for c in customers.values() if c.get("customer_id")]
    contacts = {c["id"]: c for c in await db.customers.find(
        {"id": {"$in": cust_ids}},
        {"_id": 0, "id": 1, "phone": 1, "contact_person": 1, "email": 1}).to_list(5000)}
    for c in customers.values():
        info = contacts.get(c.get("customer_id"), {})
        c["phone"] = info.get("phone", "")
        c["contact_person"] = info.get("contact_person", "")
        c["email"] = info.get("email", "")
    qty_out = sum(float(m.get("quantity") or 0) for m in movs
                  if m.get("movement_type") == "outbound_dispatch")
    return {
        "lot": lot,
        "scope_lots": [{"id": l["id"], "lot_number": l.get("lot_number"),
                        "relation": "self" if l["id"] == lot["id"] else "descendant",
                        "roll_count": l.get("roll_count", 0)} for l in lots.values()],
        "rolls": [safe_doc({k: r.get(k) for k in
                            ("id", "roll_no", "status", "grade", "length_initial",
                             "length_remaining", "unit", "warehouse_id", "lot_id",
                             "dye_lot", "reserved_ref")}) for r in rolls],
        "orders": [safe_doc(o) for o in orders],
        "shipments": [safe_doc(s) for s in shipments],
        "customers": list(customers.values()),
        "dispatch_documents": sorted([d for d in dispatch_docs if d]),
        "totals": {"lots": len(lots), "rolls": len(rolls), "orders": len(orders),
                   "shipments": len(shipments), "customers": len(customers),
                   "qty_dispatched": round(qty_out, 3),
                   "qty_remaining": round(sum(float(r.get("length_remaining") or 0)
                                              for r in rolls), 3)},
    }


# ═══════════════════════════════════════════════════════════════════════════
# LABEL / QR (keputusan pemilik 5c — reuse label_printer_service)
# ═══════════════════════════════════════════════════════════════════════════
async def label(lot_id: str, *, fmt: str = "zpl", qty: int = 1,
                roll_id: str = "") -> Dict[str, Any]:
    lot = await ls.get_lot(lot_id)
    wh = await db.warehouses.find_one({"id": lot.get("warehouse_id")},
                                      {"_id": 0, "name": 1, "code": 1}) or {}
    roll: Optional[Dict[str, Any]] = None
    if roll_id:
        roll = await db[ROLLS].find_one({"id": roll_id, "lot_id": lot["id"]}, {"_id": 0})
        if not roll:
            raise ls.LotError("Roll tidak ditemukan pada lot ini.")
    barcode = roll["roll_no"] if roll else lot["lot_number"]
    name = f"{lot.get('product_name', '')} · {lot['lot_number']}"
    if roll:
        name = f"{lot.get('product_name', '')} · {roll.get('roll_no')} ({lot['lot_number']})"
    try:
        cmd = generate_label(fmt, lot.get("sku", ""), name[:60],
                             wh.get("name", "") or lot.get("warehouse_id", ""),
                             0, barcode, max(1, int(qty)))
    except ValueError as exc:
        raise ls.LotError(str(exc)) from exc
    cmd["lot"] = {
        "id": lot["id"], "lot_number": lot["lot_number"], "sku": lot.get("sku", ""),
        "product_name": lot.get("product_name", ""), "dye_lot": lot.get("dye_lot", ""),
        "supplier_lot": lot.get("supplier_lot", ""), "stage": lot.get("stage", ""),
        "grade_note": lot.get("note", ""), "lot_status": lot.get("lot_status", ""),
        "qty_remaining": lot.get("qty_remaining", 0), "unit": lot.get("unit", ""),
        "warehouse": wh.get("name", ""), "roll_no": (roll or {}).get("roll_no", ""),
        "qr_value": barcode,
    }
    return cmd
