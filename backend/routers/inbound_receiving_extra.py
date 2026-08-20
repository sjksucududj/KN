"""Inbound Receiving router (extra): QC inspection queue/decision + Goods-Received document.

Dipisah dari `routers/inbound_receiving.py` agar file router di bawah batas guardrail.
Semua endpoint memakai prefix /api yang sama; tidak ada konflik path dengan router utama.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from db import db
from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from core_utils import safe_doc
from schemas import QCDecision, ReceiveUomPreviewIn, ReceivingUomSettingsIn

router = APIRouter(prefix="/api")


# ═══════════════════════════════════════════════════════════════════════════
# FASE F-1 — PENERIMAAN BERBASIS SATUAN SUPPLIER (F1-04 · F1-05 · F1-08)
# ═══════════════════════════════════════════════════════════════════════════
async def _load_task_for_uom(task_id: str, request: Request) -> Dict[str, Any]:
    """Ambil inbound task + cegah akses lintas-entitas (INV-ENTITY-01)."""
    await require_permission(request, "wms", "view")
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Inbound task tidak ditemukan")
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    if task.get("flow_type") != "inbound":
        raise HTTPException(status_code=400, detail="Task ini bukan inbound task")
    return task


async def _receive_tolerance_pct(task: Dict[str, Any]) -> float:
    from services.config_service import get_effective_settings
    po = await db.purchase_orders.find_one({"id": task.get("po_id")}, {"_id": 0, "entity_id": 1})
    settings = await get_effective_settings((po or {}).get("entity_id"))
    return float((settings.get("purchasing", {}) or {}).get("receive_tolerance_percent", 2.0) or 0)


@router.get("/inbound/tasks/{task_id}/uom-options")
async def inbound_uom_options(task_id: str, request: Request) -> Dict[str, Any]:
    """F1-04 — satuan yang sah untuk penerimaan task ini + faktor + hint + sisa 2 satuan.

    Dipakai layar Inbound agar operator bisa memilih **satuan supplier** (mis. `cone`)
    dan mengetik qty apa adanya dari surat jalan.
    """
    from services import receiving_uom_service as rus
    task = await _load_task_for_uom(task_id, request)
    out = await rus.uom_options(task)
    out["receive_tolerance_percent"] = await _receive_tolerance_pct(task)
    return out


@router.post("/inbound/tasks/{task_id}/preview-uom")
async def inbound_preview_uom(task_id: str, payload: ReceiveUomPreviewIn,
                              request: Request) -> Dict[str, Any]:
    """F1-05 — pratinjau konversi + cek sisa/toleransi **tanpa menulis** apa pun."""
    from services import receiving_uom_service as rus
    task = await _load_task_for_uom(task_id, request)
    try:
        return await rus.preview(task, payload.doc_uom, payload.doc_qty,
                                 tolerance_pct=await _receive_tolerance_pct(task))
    except rus.ReceivingUomError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/receiving/uom-settings")
async def get_receiving_uom_settings(request: Request) -> Dict[str, Any]:
    """F1-08 — kebijakan input satuan supplier (configurable tanpa deploy)."""
    from services import receiving_uom_service as rus
    await require_permission(request, "wms", "view")
    ctx = await entity_ctx(request)
    return {**await rus.get_settings(ctx.active_entity_id), "modes": list(rus.INPUT_MODES)}


@router.put("/receiving/uom-settings")
async def update_receiving_uom_settings(payload: ReceivingUomSettingsIn,
                                       request: Request) -> Dict[str, Any]:
    from services import receiving_uom_service as rus
    actor = await require_permission(request, "settings", "manage")
    try:
        out = await rus.update_settings(payload.model_dump(exclude_none=True), actor["name"])
    except rus.ReceivingUomError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor, "update", "system_settings", "receiving",
                "Kebijakan satuan supplier saat penerimaan diubah")
    return {**out, "modes": list(rus.INPUT_MODES)}


@router.get("/inbound/qc/queue")
async def qc_inspection_queue(request: Request) -> List[Dict[str, Any]]:
    """Depth #3a — antrian inspeksi QC: task inbound berstatus `qc_pending`
    (barang di karantina menunggu keputusan terima/tolak)."""
    await require_permission(request, "wms", "view")
    from services.qc_service import quarantine_qty_for_task
    ctx = await entity_ctx(request)
    tasks = await db.wms_tasks.find(
        resolve_list_scope("wms_tasks", {"flow_type": "inbound", "status": "qc_pending"}, ctx), {"_id": 0},
    ).sort("updated_at", -1).to_list(200)
    po_ids = list({t.get("po_id") for t in tasks if t.get("po_id")})
    pos = {p["id"]: p for p in await db.purchase_orders.find(
        {"id": {"$in": po_ids}}, {"_id": 0}).to_list(100)}
    prod_ids = list({t.get("product_id") for t in tasks if t.get("product_id")})
    prods = {p["id"]: p for p in await db.products.find(
        {"id": {"$in": prod_ids}}, {"_id": 0}).to_list(500)}
    whs = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    out = []
    for t in tasks:
        po = pos.get(t.get("po_id"), {})
        prod = prods.get(t.get("product_id"), {})
        t["supplier_name"] = po.get("supplier_name", "")
        t["po_number"] = t.get("po_number") or po.get("po_number", "")
        t["product_name"] = t.get("product_name") or prod.get("name", "")
        t["sku"] = prod.get("sku", "")
        t["warehouse_name"] = whs.get(t.get("warehouse_id"), {}).get("name", "")
        t["quarantine_qty"] = await quarantine_qty_for_task(t["id"])
        out.append(safe_doc(t))
    return out


@router.post("/inbound/tasks/{task_id}/qc-decision")
async def qc_decision(task_id: str, payload: QCDecision, request: Request) -> Dict[str, Any]:
    """Depth #3a — keputusan inspeksi QC: terima (→available) &/atau tolak
    (→damaged / retur ke supplier dengan Nota Debit otomatis)."""
    actor = await require_permission(request, "wms", "update")
    task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))
    if not task:
        raise HTTPException(status_code=404, detail="Inbound task tidak ditemukan")
    # INV-ENTITY-01 (KN-076-IDOR-WRITE-INBOUND P1): cegah mutasi task lintas-entitas.
    assert_entity_access(task, "wms_tasks", await entity_ctx(request))
    if task.get("status") != "qc_pending":
        raise HTTPException(
            status_code=400,
            detail=f"Task harus berstatus qc_pending untuk inspeksi (current: {task.get('status')})")
    from services.qc_service import process_qc_decision
    try:
        result = await process_qc_decision(
            task, payload.accept_qty, payload.reject_qty,
            payload.reject_disposition, payload.reason, actor,
            accept_grade=payload.accept_grade, defects=payload.defects)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "qc_decision", "wms_task", task_id, result)
    return result


@router.get("/inbound/po/{po_id}/receiving-goods-document")
async def generate_receiving_goods_document(po_id: str, request: Request):
    """
    Generate Receiving Goods document (like surat jalan) for completed PO.

    Shows all received items with batch/lot/qty details.
    """
    from datetime import datetime, timezone

    await require_permission(request, "wms", "view")

    po = safe_doc(await db.purchase_orders.find_one({"id": po_id}, {"_id": 0}))
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")

    # Get all completed inbound tasks for this PO
    tasks = await db.wms_tasks.find({
        "po_id": po_id,
        "status": "completed"
    }, {"_id": 0}).to_list(100)

    if not tasks:
        raise HTTPException(status_code=400, detail="Belum ada inbound task yang completed untuk PO ini")

    # Build items table
    items_rows = ""
    for task in tasks:
        items_rows += f"""
        <tr>
            <td>{task.get('sku', '')}</td>
            <td>{task.get('product_name', '')}</td>
            <td>{task.get('quantity', 0.0)}</td>
            <td>{task.get('unit', '')}</td>
            <td>{task.get('batch', '-')}</td>
            <td>{task.get('lot', '-')}</td>
            <td>{task.get('bin_id', '-')}</td>
        </tr>
        """

    html = f"""
    <html>
    <head>
        <title>Surat Penerimaan Barang - {po['po_number']}</title>
        <style>
            @page {{size: A4 portrait; margin: 12mm}}
            body {{font-family: Arial, sans-serif; padding: 0; color: #111}}
            .header {{display: flex; justify-content: space-between; border-bottom: 2px solid #111; padding-bottom: 16px; margin-bottom: 20px}}
            h1 {{margin: 0; font-size: 24px}}
            h2 {{margin: 10px 0; font-size: 18px}}
            table {{width: 100%; border-collapse: collapse; margin-top: 18px}}
            td, th {{border: 1px solid #ddd; padding: 10px; text-align: left}}
            th {{background: #f5f5f5; font-weight: bold}}
            .info-section {{margin: 20px 0}}
            .signature {{display: flex; justify-content: space-between; margin-top: 60px}}
            .signature div {{text-align: center}}
            footer {{margin-top: 40px; border-top: 1px solid #ddd; padding-top: 12px; color: #555; font-size: 12px}}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <h1>Kain Nusantara</h1>
                <p style="color: #555; margin: 5px 0">Enterprise Textile Warehouse</p>
            </div>
            <div style="text-align: right">
                <h2>SURAT PENERIMAAN BARANG</h2>
                <p style="margin: 5px 0"><strong>{po['po_number']}</strong></p>
                <p style="margin: 5px 0">{datetime.now(timezone.utc).strftime('%d %b %Y')}</p>
            </div>
        </div>

        <div class="info-section">
            <h3>Informasi PO</h3>
            <p><strong>Supplier:</strong> {po['supplier_name']}</p>
            <p><strong>Kontak:</strong> {po.get('supplier_contact', '-')}</p>
            <p><strong>Gudang Tujuan:</strong> {po.get('warehouse_name', '-')} ({po.get('warehouse_city', '')})</p>
            <p><strong>Tanggal Expected:</strong> {po.get('expected_delivery_date', '-')}</p>
        </div>

        <h3>Barang yang Diterima</h3>
        <table>
            <thead>
                <tr>
                    <th>SKU</th>
                    <th>Nama Produk</th>
                    <th>Qty Diterima</th>
                    <th>Unit</th>
                    <th>Batch</th>
                    <th>Lot</th>
                    <th>Bin Location</th>
                </tr>
            </thead>
            <tbody>
                {items_rows}
            </tbody>
        </table>

        <div class="signature">
            <div>
                <p>Diterima Oleh</p>
                <br/><br/>
                <p><strong>_________________</strong></p>
                <p>Warehouse Staff</p>
            </div>
            <div>
                <p>Disetujui Oleh</p>
                <br/><br/>
                <p><strong>_________________</strong></p>
                <p>Warehouse Manager</p>
            </div>
        </div>

        <footer>
            <p>Dokumen ini dibuat secara otomatis oleh sistem Kain Nusantara WMS.</p>
            <p>Barang diterima dalam kondisi baik dan sesuai dengan spesifikasi PO.</p>
        </footer>
    </body>
    </html>
    """

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)
