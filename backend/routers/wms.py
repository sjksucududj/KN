"""WMS router: tasks, scanning, stage advance."""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import ScannerScan, WMSTaskCreate
from services.shipment_service import dispatch_task
from services.roll_service import create_inbound_roll

router = APIRouter(prefix="/api")

FLOW_STAGES = {
    "inbound": ["created", "in_transit", "receiving", "qc_check", "put_away", "done"],
    "outbound": ["created", "picking", "packing", "staging", "dispatched"],
    "transfer": ["created", "picking", "in_transit", "receiving", "done"],
    "picking": ["created", "picking", "done"],
}

# KN-078-WMS-RESURRECTION (INV-STATE-01): status terminal WMS — advance/scan HARUS ditolak.
# Mencakup 'completed' (dipakai flow inbound) selain terminal FLOW_STAGES (done/dispatched) + cancelled.
TERMINAL_STATUSES = {"done", "dispatched", "completed", "cancelled"}


@router.get("/wms/tasks")
async def list_tasks(request: Request, line: str = "") -> List[Dict[str, Any]]:
    actor = await require_permission(request, "wms", "view")
    ctx = await entity_ctx(request)
    query = resolve_list_scope("wms_tasks", {}, ctx)
    # FASE L — tugas gudang ikut berpagar lini (penerimaan kain printing bukan
    # pekerjaan staf woven). Tugas lama tanpa lini tetap terlihat.
    from services import line_scope as _lines
    query = _lines.narrow(query, actor, line)
    tasks = await db.wms_tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(100)}
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    for task in tasks:
        prod = products.get(task.get("product_id"), {})
        wh = warehouses.get(task.get("warehouse_id"), {})
        task["product_name"] = prod.get("name", "")
        task["sku"] = prod.get("sku", "")
        task["warehouse_name"] = wh.get("name", "")
        task["warehouse_city"] = wh.get("city", "")
    return tasks


@router.post("/wms/tasks")
async def create_task(payload: WMSTaskCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "wms", "create")
    ctx = await entity_ctx(request)
    product = safe_doc(await db.products.find_one({"id": payload.product_id}, {"_id": 0}))
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    # E4.1 — tugas gudang (terima/kirim) hanya di gudang yang boleh dipakai.
    from services import warehouse_scope_service as whscope
    warehouse = await whscope.assert_usable(payload.warehouse_id, ctx.active_entity_id,
                                           action="membuat tugas gudang di sini")
    stages = FLOW_STAGES.get(payload.flow_type, ["created", "done"])
    task = {
        "id": new_id("wms"),
        "entity_id": ctx.active_entity_id,
        "flow_type": payload.flow_type,
        "source_type": payload.source_type,
        "product_id": payload.product_id,
        "product_name": product["name"],
        "sku": product["sku"],
        "line_code": str(product.get("line_code") or "").strip().lower(),   # FASE L
        "quantity": payload.quantity,
        "unit": payload.unit,
        "warehouse_id": payload.warehouse_id,
        "warehouse_name": warehouse["name"],
        "warehouse_city": warehouse["city"],
        "bin_id": payload.bin_id,
        "batch": payload.batch,
        "lot": payload.lot,
        "roll_id": payload.roll_id,
        "status": stages[0],
        "stages": stages,
        "scan_log": [],
        "created_by": actor["name"],
        "created_at": now_iso(), "updated_at": now_iso()
    }
    await db.wms_tasks.insert_one(task)
    if payload.flow_type == "inbound":
        # Roll-as-SSOT (KN_15 §10): inbound manual MEMBUAT roll available (bukan $inc balance),
        # sehingga stok punya backing roll nyata (bisa dialokasi & tak drift saat rebuild).
        owner = DEFAULT_ENTITY_ID if getattr(ctx, "view_all", False) else (ctx.active_entity_id or DEFAULT_ENTITY_ID)
        roll = await create_inbound_roll(
            payload.product_id, payload.warehouse_id, owner, payload.quantity,
            lot=payload.lot, batch=payload.batch, bin_id=payload.bin_id or None,
            unit=payload.unit, acquired_via="manual_inbound", ref_id=task["id"],
            created_by=actor["name"], roll_no=payload.roll_id or "",
        )
        await db.wms_tasks.update_one(
            {"id": task["id"]}, {"$set": {"roll_id": roll["id"], "owner_entity_id": owner}}
        )
        task["roll_id"] = roll["id"]
        task["owner_entity_id"] = owner
    await audit(actor["name"], "wms_task_created", "wms_task", task["id"],
                {"flow_type": payload.flow_type, "product": product["name"]})
    return safe_doc(task)


@router.post("/wms/tasks/outbound-from-order/{order_id}")
async def create_outbound_from_order(order_id: str, request: Request) -> List[Dict[str, Any]]:
    actor = await require_permission(request, "wms", "create")
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    if order["status"] not in ["confirmed", "partially_picked", "picked", "partially_shipped"]:
        raise HTTPException(status_code=409, detail="Hanya order confirmed yang bisa dibuat outbound task")
    # Sub-fase 1.8 — idempotent via service (cegah duplikasi dgn auto-create saat confirm)
    from services.fulfillment_status import create_outbound_tasks_for_order, recompute_so_status
    created_tasks = await create_outbound_tasks_for_order(order_id, actor["name"])
    await recompute_so_status(order_id)
    await audit(actor["name"], "outbound_tasks_created", "wms_task", order_id,
                {"order_number": order["number"], "tasks_count": len(created_tasks)})
    return created_tasks


@router.post("/wms/tasks/{task_id}/scan")
async def scan_task(task_id: str, payload: ScannerScan, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "wms", "scan")
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))  # S#074 IDOR
    if task["status"] in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="Task terminal: scan baru diblokir")
    scan_entry = {
        "id": new_id("scan"), "scan_type": payload.scan_type, "scan_value": payload.scan_value,
        "actor": actor["name"], "timestamp": now_iso()
    }
    expected_map = {"sku": task["sku"], "batch": task["batch"], "lot": task["lot"],
                    "roll": task["roll_id"], "bin": task["bin_id"]}
    expected_value = expected_map.get(payload.scan_type, "")
    if expected_value and payload.scan_value != expected_value:
        scan_entry["match"] = False
        scan_entry["note"] = f"Tidak cocok: expected '{expected_value}', got '{payload.scan_value}'"
    else:
        scan_entry["match"] = True
    updated = await db.wms_tasks.find_one_and_update(
        {"id": task_id},
        {"$push": {"scan_log": scan_entry}, "$set": {"updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    await audit(actor["name"], "wms_scan", "wms_task", task_id, scan_entry)
    return safe_doc(updated)


@router.post("/wms/tasks/{task_id}/advance")
async def advance_task(task_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "wms", "update")
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))  # S#074 IDOR
    stages = task.get("stages", FLOW_STAGES.get(task["flow_type"], ["created", "done"]))
    status = task["status"]
    # KN-078-WMS-RESURRECTION (P2, INV-STATE-01): anti-resurrection.
    # (1) Task terminal TIDAK boleh di-advance (cegah double-proses/double-receipt).
    if status in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail=f"Task sudah terminal ('{status}') — tidak bisa di-advance.")
    # (2) Status di luar alur (vocab mismatch) → JANGAN reset current_idx ke 0 (itu akar bug).
    #     Tolak eksplisit; gunakan aksi alur yang sesuai (scan-receive/qc-decision/complete).
    if status not in stages:
        raise HTTPException(
            status_code=409,
            detail=f"Status '{status}' di luar alur {task['flow_type']}; gunakan aksi alur yang sesuai (scan/QC/complete).")
    current_idx = stages.index(status)
    if current_idx >= len(stages) - 1:
        raise HTTPException(status_code=409, detail="Task sudah di stage akhir")
    next_stage = stages[current_idx + 1]
    update_data = {"status": next_stage, "updated_at": now_iso()}
    # Sub-fase 1.8 — outbound mencapai 'dispatched': delegasi ke shipment_service
    # (SSOT-safe: roll committed→in_transit_sales + catat shipment, BUKAN $inc balance).
    if next_stage == "dispatched" and task["flow_type"] == "outbound":
        updated_task, shipment = await dispatch_task(task, None, actor["name"])
        await audit(actor["name"], "wms_task_advanced", "wms_task", task_id,
                    {"status": updated_task["status"], "shipment_no": shipment["shipment_no"]})
        return updated_task
    updated = await db.wms_tasks.find_one_and_update(
        {"id": task_id}, {"$set": update_data},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    await audit(actor["name"], "wms_task_advanced", "wms_task", task_id, {"status": next_stage})
    return safe_doc(updated)
