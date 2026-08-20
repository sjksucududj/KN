"""Outbound Picking router: scan-based picking with multi-warehouse support & escalation."""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from core_utils import new_id, now_iso, safe_doc
from services.shipment_service import dispatch_task
from services.fulfillment_status import recompute_so_status

router = APIRouter(prefix="/api")


async def _auto_release_due_scheduled() -> int:
    """Order Pengambilan — rilis otomatis task picking terjadwal yang tanggal ambilnya
    sudah tiba (hold_until <= hari ini) → 'created' (masuk antrean aktif gudang)."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    res = await db.wms_tasks.update_many(
        {"flow_type": "outbound", "status": "scheduled", "hold_until": {"$lte": today, "$ne": ""}},
        {"$set": {"status": "created", "updated_at": now_iso()}})
    return res.modified_count


@router.get("/outbound/tasks")
async def list_outbound_tasks(request: Request, status: str = None, warehouse_id: str = None,
                              entity_id: str = None) -> List[Dict[str, Any]]:
    """List all outbound picking tasks, optionally filtered.

    W-1 (Gelombang 2) — ter-scope entitas aktif (X-Entity-Id / ?entity_id), konsisten
    dengan inbound. entity_id='all' utk role lintas-entitas."""
    await require_permission(request, "wms", "view")
    await _auto_release_due_scheduled()

    query = {"flow_type": "outbound", "source_type": "sales_order"}
    if status:
        query["status"] = status
    else:
        query["status"] = {"$ne": "scheduled"}  # hold pengambilan dikecualikan dari antrean aktif
    if warehouse_id:
        query["warehouse_id"] = warehouse_id
    ctx = await entity_ctx(request)
    query = resolve_list_scope("wms_tasks", query, ctx, entity_id)
    
    tasks = await db.wms_tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    
    # Enrich with SO info
    so_ids = list(set(t.get("order_id") for t in tasks if t.get("order_id")))
    orders = {o["id"]: o for o in await db.sales_orders.find({"id": {"$in": so_ids}}, {"_id": 0}).to_list(100)}
    
    for task in tasks:
        if task.get("order_id"):
            order = orders.get(task["order_id"], {})
            task["customer_name"] = order.get("customer_name", "")
            task["order_total"] = order.get("total_amount", 0)
    
    return tasks


@router.post("/outbound/tasks/{task_id}/release")
async def release_scheduled_task(task_id: str, request: Request) -> Dict[str, Any]:
    """Order Pengambilan — rilis manual task picking terjadwal (hold) → 'created'."""
    actor = await require_permission(request, "wms", "update")
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Outbound task tidak ditemukan")
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    if task.get("status") != "scheduled":
        raise HTTPException(status_code=400, detail="Task tidak dalam status terjadwal (hold).")
    updated = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {"$set": {"status": "created", "released_by": actor["name"],
                  "released_at": now_iso(), "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "outbound_task_released", "wms_task", task_id,
                {"order_number": task.get("order_number", "")})
    return safe_doc(updated)


@router.post("/outbound/tasks/{task_id}/scan-pick")
async def scan_pick_item(
    task_id: str,
    request: Request,
    actual_qty: float,
    batch: str = "",
    lot: str = "",
    roll_id: str = "",
    bin_id: str = ""
) -> Dict[str, Any]:
    """
    Scan and pick item for outbound task.
    
    Updates picked_qty. If picked_qty reaches expected qty, auto-advance.
    """
    actor = await require_permission(request, "wms", "update")
    
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Outbound task tidak ditemukan")
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    
    if task.get("flow_type") != "outbound":
        raise HTTPException(status_code=400, detail="Task ini bukan outbound task")
    
    if task["status"] == "scheduled":
        raise HTTPException(status_code=400, detail="Task pengambilan masih di-hold (terjadwal). Rilis dulu sebelum picking.")
    if task["status"] in ["dispatched", "cancelled"]:
        raise HTTPException(status_code=400, detail="Task sudah dispatched atau dibatalkan")
    
    # Update picked qty
    new_picked_qty = task.get("picked_qty", 0.0) + actual_qty
    expected_qty = task.get("quantity", 0.0)
    
    # Check if qty exceeds expected
    if new_picked_qty > expected_qty:
        raise HTTPException(
            status_code=400,
            detail=f"Qty picked ({new_picked_qty}) melebihi expected ({expected_qty})"
        )
    
    # Log scan entry
    scan_entry = {
        "id": new_id("scan"),
        "scan_type": "pick",
        "actual_qty": actual_qty,
        "batch": batch,
        "lot": lot,
        "roll_id": roll_id,
        "bin_id": bin_id,
        "actor": actor["name"],
        "timestamp": now_iso()
    }
    
    update_data = {
        "picked_qty": new_picked_qty,
        "batch": batch or task.get("batch", ""),
        "lot": lot or task.get("lot", ""),
        "roll_id": roll_id or task.get("roll_id", ""),
        "bin_id": bin_id or task.get("bin_id", ""),
        "updated_at": now_iso()
    }
    
    # If first pick, auto-advance to picking status
    if task["status"] == "created" and new_picked_qty > 0:
        update_data["status"] = "picking"
    
    # If fully picked, advance to packing
    if new_picked_qty >= expected_qty:
        update_data["status"] = "packing"
    
    updated_task = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {
            "$set": update_data,
            "$push": {"scan_log": scan_entry}
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "outbound_scan_pick", "wms_task", task_id, {
        "actual_qty": actual_qty,
        "picked_qty": new_picked_qty,
        "expected_qty": expected_qty
    })

    # Sub-fase 1.8 — status SO terderivasi otomatis dari progres pick
    if task.get("order_id"):
        await recompute_so_status(task["order_id"])

    return safe_doc(updated_task)


@router.post("/outbound/tasks/{task_id}/escalate")
async def escalate_outbound_task(
    task_id: str,
    request: Request,
    reason: str = "Stock fisik tidak sesuai dengan sistem"
) -> Dict[str, Any]:
    """
    Escalate outbound task to manager due to stock mismatch or other issues.
    
    Manager can then reorganize/adjust allocation.
    """
    actor = await require_permission(request, "wms", "update")
    
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Outbound task tidak ditemukan")
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    
    escalation = {
        "escalated_by": actor["name"],
        "escalated_at": now_iso(),
        "reason": reason,
        "status": "pending_review",
        "resolved_by": None,
        "resolved_at": None,
        "resolution_notes": ""
    }
    
    updated_task = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {
            "$set": {
                "escalation": escalation,
                "status": "escalated",
                "updated_at": now_iso()
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "outbound_escalated", "wms_task", task_id, {
        "reason": reason,
        "picked_qty": task.get("picked_qty", 0),
        "expected_qty": task.get("quantity", 0)
    })
    
    return safe_doc(updated_task)


@router.post("/outbound/tasks/{task_id}/resolve-escalation")
async def resolve_outbound_escalation(
    task_id: str,
    request: Request,
    adjusted_qty: float = None,
    resolution_notes: str = ""
) -> Dict[str, Any]:
    """
    Resolve escalated outbound task (manager only).
    
    Manager can adjust expected qty or reorganize allocation.
    """
    actor = await require_permission(request, "wms", "approve")  # Manager permission
    
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Outbound task tidak ditemukan")
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    
    if not task.get("escalation"):
        raise HTTPException(status_code=400, detail="Task tidak dalam status escalation")
    
    escalation = task["escalation"]
    escalation["status"] = "resolved"
    escalation["resolved_by"] = actor["name"]
    escalation["resolved_at"] = now_iso()
    escalation["resolution_notes"] = resolution_notes
    
    update_data = {
        "escalation": escalation,
        "status": "packing",  # Move to packing after resolution
        "updated_at": now_iso()
    }
    
    # S-6 (Gelombang 2) — penyesuaian qty oleh manager kini SINKRON penuh:
    # roll reservation dilepas parsial, allocation + item + pricing order dihitung ulang.
    if adjusted_qty is not None:
        original_qty = round(float(task.get("quantity", 0) or 0), 2)
        adjusted_qty = round(float(adjusted_qty), 2)
        picked = round(float(task.get("picked_qty", 0) or 0), 2)
        if adjusted_qty <= 0:
            raise HTTPException(status_code=400, detail="Qty penyesuaian harus > 0.")
        if adjusted_qty > original_qty + 0.01:
            raise HTTPException(
                status_code=400,
                detail="Qty tidak bisa DINAIKKAN dari eskalasi — amend SO / buat order tambahan.")
        if adjusted_qty + 0.01 < picked:
            raise HTTPException(
                status_code=400,
                detail=f"Qty penyesuaian ({adjusted_qty:g}) di bawah qty yang sudah di-pick ({picked:g}).")
        delta = round(original_qty - adjusted_qty, 2)
        update_data["quantity"] = adjusted_qty

        order = None
        if task.get("order_id"):
            order = safe_doc(await db.sales_orders.find_one({"id": task["order_id"]}, {"_id": 0}))
        if order and delta > 0.01:
            if order.get("payments"):
                raise HTTPException(
                    status_code=400,
                    detail="Order sudah memiliki pembayaran — penyesuaian qty harus lewat retur/credit note.")
            # 1) Lepas selisih reservasi roll (parsial, per produk+gudang task ini)
            from services.roll_service import release_order_rolls_partial
            released = await release_order_rolls_partial(
                order["id"], task["product_id"], task["warehouse_id"], delta)
            # 2) Allocation qty
            await db.sales_orders.update_one(
                {"id": order["id"], "allocations.id": task.get("allocation_id")},
                {"$set": {"allocations.$.quantity": adjusted_qty, "updated_at": now_iso()}})
            # 3) Item qty (base + unit jual proporsional) + repricing seluruh order
            items = [dict(i) for i in order.get("items", [])]
            for it in items:
                if it.get("product_id") != task.get("product_id"):
                    continue
                old_base = float(it.get("base_quantity", it.get("quantity", 0)) or 0)
                if old_base <= 0:
                    break
                new_base = max(round(old_base - delta, 2), 0.0)
                sell_per_base = float(it.get("quantity", 0) or 0) / old_base
                it["base_quantity"] = new_base
                it["quantity"] = round(new_base * sell_per_base, 2)
                if "reserved_qty" in it:  # invarian L4-BO: base_qty == reserved+backorder+interco
                    it["reserved_qty"] = max(
                        round(float(it.get("reserved_qty", 0) or 0) - delta, 2), 0.0)
                break
            from services.config_service import compute_order_pricing
            pricing = await compute_order_pricing(
                items, order.get("entity_id"), 0,
                tax_override=(order.get("tax_override") or "").strip().lower() or None)
            await db.sales_orders.update_one(
                {"id": order["id"]},
                {"$set": {
                    "items": pricing["items"],
                    "total_amount": pricing["total_amount"],
                    "items_discount_total": pricing["items_discount_total"],
                    "order_discount_amount": pricing["order_discount_amount"],
                    "discount_total": pricing["discount_total"],
                    "net_subtotal": pricing["net_subtotal"],
                    "dpp": pricing["dpp"], "dpp_nilai_lain": pricing.get("dpp_nilai_lain", False),
                    "effective_rate": pricing.get("effective_rate", pricing["ppn_rate"]),
                    "ppn_amount": pricing["ppn_amount"],
                    "grand_total": pricing["grand_total"],
                    "approval_amount": pricing["grand_total"],
                    "updated_at": now_iso(),
                },
                 "$push": {"timeline": {
                     "event": "qty_adjusted", "label": "Qty disesuaikan via eskalasi gudang",
                     "actor": actor["name"], "at": now_iso(),
                     "note": (f"{task.get('product_name', task.get('product_id'))}: "
                              f"{original_qty:g} → {adjusted_qty:g} (roll dilepas {released:g}). "
                              f"{resolution_notes}").strip(),
                 }}})
    
    updated_task = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {"$set": update_data},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    
    await audit(actor["name"], "outbound_escalation_resolved", "wms_task", task_id, {
        "adjusted_qty": adjusted_qty,
        "resolution_notes": resolution_notes
    })
    
    return safe_doc(updated_task)


@router.post("/outbound/tasks/{task_id}/dispatch")
async def dispatch_outbound(task_id: str, request: Request, ship_qty: float = None) -> Dict[str, Any]:
    """Sub-fase 1.8 — Dispatch task outbound (mendukung PENGIRIMAN PARSIAL).

    SSOT-safe: roll order committed→in_transit_sales (BUKAN $inc balance). Setiap dispatch
    mencatat 1 record `shipments` (No. Surat Jalan SJ-####). `ship_qty` opsional — default
    = sisa yang sudah di-pick & belum dikirim. Status SO terderivasi otomatis.
    """
    actor = await require_permission(request, "wms", "update")

    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Outbound task tidak ditemukan")
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))

    updated_task, shipment = await dispatch_task(task, ship_qty, actor["name"])

    await audit(actor["name"], "outbound_dispatched", "wms_task", task_id, {
        "ship_qty": shipment["qty"], "shipment_no": shipment["shipment_no"],
        "task_status": updated_task["status"],
    })

    return {"task": updated_task, "shipment": shipment}
