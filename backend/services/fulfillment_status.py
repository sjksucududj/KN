"""Fulfillment status engine (Sub-fase 1.8).

- recompute_so_status: turunkan status SO dari progres task outbound (otomatis).
  confirmed → partially_picked → picked → partially_shipped → shipped (→ done manual).
- create_outbound_tasks_for_order: buat task outbound (idempotent) saat order confirmed.

Semua qty dalam BASE UNIT (konsisten Roll-as-SSOT & UOM-safe untuk Sub-fase 1.13).
"""
from typing import Any, Dict, List
from db import db
from core_utils import new_id, now_iso, safe_doc

EPS = 0.01
# Status SO yang TIDAK boleh di-override oleh recompute otomatis
TERMINAL_SO = {"done", "cancelled", "expired"}
# Status SO sebelum fase fulfillment (jangan di-recompute sampai confirmed)
PRE_FULFILL = {"draft", "reserved", "waiting_approval", "approved", "waiting_stock"}


def _task_picked(t: Dict[str, Any]) -> float:
    return min(float(t.get("picked_qty", 0) or 0), float(t.get("quantity", 0) or 0))


async def recompute_so_status(order_id: str) -> str:
    """Hitung ulang status SO dari task outbound. Return status final (atau lama bila tak berubah)."""
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        return ""
    cur = order.get("status")
    if cur in TERMINAL_SO or cur in PRE_FULFILL:
        return cur  # jangan ganggu pre-confirm / terminal

    tasks = await db.wms_tasks.find(
        {"order_id": order_id, "flow_type": "outbound"}, {"_id": 0}
    ).to_list(500)
    # abaikan task dibatalkan
    tasks = [t for t in tasks if t.get("status") != "cancelled"]
    total = round(sum(float(t.get("quantity", 0) or 0) for t in tasks), 2)
    picked = round(sum(_task_picked(t) for t in tasks), 2)
    shipped = round(sum(float(t.get("shipped_qty", 0) or 0) for t in tasks), 2)

    if total <= 0:
        new_status = "confirmed"
    elif shipped + EPS >= total:
        new_status = "shipped"
    elif shipped > EPS:
        new_status = "partially_shipped"
    elif picked + EPS >= total:
        new_status = "picked"
    elif picked > EPS:
        new_status = "partially_picked"
    else:
        new_status = "confirmed"

    fulfillment = {"total_qty": total, "picked_qty": picked, "shipped_qty": shipped,
                   "remaining_qty": round(max(total - shipped, 0), 2)}
    set_doc = {"fulfillment": fulfillment, "updated_at": now_iso()}
    if new_status != cur:
        set_doc["status"] = new_status
    # F4 — sinkronkan stage + sub_status (turunan dari status fulfillment final).
    from services.so_status import stage_fields
    set_doc.update(stage_fields({**order, **set_doc}))
    await db.sales_orders.update_one({"id": order_id}, {"$set": set_doc})
    return new_status


async def create_outbound_tasks_for_order(order_id: str, actor_name: str) -> List[Dict[str, Any]]:
    """Buat task outbound dari allocations order (idempotent: skip bila sudah ada)."""
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        return []
    existing = await db.wms_tasks.count_documents({"order_id": order_id, "flow_type": "outbound"})
    if existing > 0:
        return []
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(2000)}
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    stages = ["created", "picking", "packing", "staging", "dispatched"]
    # Order Pengambilan (pickup) terjadwal → HOLD task picking sampai pickup_date tiba.
    method = (order.get("fulfillment_method") or "kirim").strip().lower()
    pickup_date = (order.get("pickup_date") or "").strip()
    hold = False
    if method == "ambil" and pickup_date:
        from datetime import datetime, timezone
        try:
            hold = datetime.fromisoformat(pickup_date).date() > datetime.now(timezone.utc).date()
        except Exception:  # noqa: BLE001
            hold = False
    init_status = "scheduled" if hold else "created"
    created: List[Dict[str, Any]] = []
    for alloc in order.get("allocations", []):
        product = products.get(alloc["product_id"], {})
        warehouse = warehouses.get(alloc["warehouse_id"], {})
        item = next((i for i in order.get("items", []) if i["product_id"] == alloc["product_id"]), {})
        task = {
            "id": new_id("wms"), "entity_id": order.get("entity_id"),
            "flow_type": "outbound", "source_type": "sales_order",
            "order_id": order_id, "order_number": order["number"],
            "allocation_id": alloc.get("id"),
            "product_id": alloc["product_id"], "product_name": product.get("name", ""),
            "sku": product.get("sku", ""), "quantity": round(float(alloc["quantity"]), 2),
            "picked_qty": 0.0, "shipped_qty": 0.0,
            "unit": item.get("unit", product.get("base_unit", "meter")),
            "warehouse_id": alloc["warehouse_id"], "warehouse_name": warehouse.get("name", ""),
            "warehouse_city": warehouse.get("city", ""),
            "bin_id": "", "batch": "", "lot": "", "roll_id": "",
            "status": init_status, "stages": stages, "scan_log": [],
            "fulfillment_method": method, "hold_until": pickup_date if hold else "",
            "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
        }
        await db.wms_tasks.insert_one(task)
        # FASE G-4 — tugas pengambilan LAHIR dari SO → tautkan dua arah saat itu juga,
        # supaya penelusuran (dan Surat Jalan yang lahir dari tugas ini) tidak buntu.
        from services import doc_refs_service as _refs
        await _refs.safe_link(("picking_task", task["id"]), ("sales_order", order_id),
                              "parent", note="pengambilan untuk SO")
        created.append(safe_doc(task))
    return created
