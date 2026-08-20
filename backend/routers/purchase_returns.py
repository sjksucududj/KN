"""Depth #1 — Retur Beli (Purchase Return / Nota Debit) router."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from db import db
from dependencies import require_permission, audit
from core_utils import safe_doc
from entity_scope import EntityContext, entity_ctx
from schemas import (PurchaseReturnCreate, PurchaseReturnDecision,
                     SupplierShipInput, SupplierAcceptInput, SupplierRejectInput, GoodsBackInput)
from services import purchase_return_service as svc
from services import line_scope                 # FASE L — pagar & penyaring lini produk
from pagination import is_paged, get_page_params, build_search, merge_query, fetch_page, envelope

router = APIRouter(prefix="/api")


@router.get("/purchase-returns")
async def list_purchase_returns(
    request: Request,
    status: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    po_id: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    line: str = Query("", description="FASE L — penyaring lini (koma untuk multi)"),
) -> Dict[str, Any]:
    actor = await require_permission(request, "purchase_return", "view")
    q: Dict[str, Any] = {}
    if status:      q["status"] = status
    if supplier_id: q["supplier_id"] = supplier_id
    if po_id:       q["po_id"] = po_id
    if entity_id and entity_id != "all": q["entity_id"] = entity_id
    q = line_scope.narrow(q, actor, line, field=line_scope.LINES_FIELD)   # FASE L
    if is_paged(request):
        page, page_size, qs, _sort = get_page_params(request)
        if qs:
            q = merge_query(q, build_search(qs, ["number", "supplier_name", "po_number", "debit_note_number"]))
        items, total = await fetch_page(db.purchase_returns, q, page, page_size, sort_field="created_at", sort_dir=-1)
        return envelope(items, total, page, page_size)
    docs = await db.purchase_returns.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"items": docs, "total": len(docs)}


@router.get("/purchase-returns/status-counts")
async def purchase_return_status_counts(
    request: Request,
    entity_id: Optional[str] = Query(None),
) -> Dict[str, int]:
    """P2 — jumlah retur beli per status (untuk lencana tab), agregasi ringan.

    Alasan sama seperti retur jual: lencana yang dihitung dari isi HALAMAN akan
    diam-diam berbeda dari kenyataan begitu daftarnya dipaginasi.
    """
    await require_permission(request, "purchase_return", "view")
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    pipeline = [{"$match": q}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    agg = await db.purchase_returns.aggregate(pipeline).to_list(100)
    counts: Dict[str, int] = {row["_id"]: int(row["n"]) for row in agg if row.get("_id")}
    counts["all"] = sum(counts.values())
    return counts


@router.post("/purchase-returns")
async def create_purchase_return(payload: PurchaseReturnCreate, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "purchase_return", "create")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Minimal satu item retur")
    try:
        doc = await svc.create_purchase_return(payload, created_by=user.get("name", "Admin"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_created", "purchase_return", doc["id"],
                {"number": doc["number"], "supplier": doc["supplier_name"], "total": doc["total_amount"]})
    return doc


@router.get("/purchase-returns/source-rolls")
async def purchase_return_source_rolls(
    request: Request,
    product_id: str = Query(...),
    supplier_id: Optional[str] = Query(None),
    po_id: Optional[str] = Query(None),
    warehouse_id: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    ctx: EntityContext = Depends(entity_ctx),
) -> Dict[str, Any]:
    """Roll available yang bisa diretur, difilter asal (untuk retur PRESISI per roll/lot).
    Didefinisikan SEBELUM '/{return_id}' agar route statis menang atas path-param.

    F0-C: `ctx` diteruskan agar roll milik PT lain tidak pernah bisa dipilih.
    """
    await require_permission(request, "purchase_return", "view")
    from routers.product_traceability import build_returnable_rolls
    return await build_returnable_rolls(product_id, supplier_id, po_id, warehouse_id,
                                        entity_id, ctx=ctx)


@router.get("/purchase-returns/{return_id}")
async def get_purchase_return(return_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "purchase_return", "view")
    doc = safe_doc(await db.purchase_returns.find_one({"id": return_id}, {"_id": 0}))
    if not doc:
        raise HTTPException(status_code=404, detail="Retur tidak ditemukan")
    return doc


@router.post("/purchase-returns/{return_id}/submit")
async def submit_purchase_return(return_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "purchase_return", "update")
    try:
        doc = await svc.submit_purchase_return(return_id, submitted_by=user.get("name", user.get("email", "")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_submitted", "purchase_return", return_id, {})
    return doc


@router.post("/purchase-returns/{return_id}/approve")
async def approve_purchase_return(return_id: str, request: Request,
                                  payload: PurchaseReturnDecision = PurchaseReturnDecision()) -> Dict[str, Any]:
    user = await require_permission(request, "purchase_return", "approve")
    try:
        doc = await svc.approve_and_adjust_stock(return_id, approved_by=user.get("name", "Admin"), notes=payload.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_approved", "purchase_return", return_id,
                {"debit_note": doc.get("debit_note_number")})
    return doc


@router.post("/purchase-returns/{return_id}/reject")
async def reject_purchase_return(return_id: str, request: Request,
                                 payload: PurchaseReturnDecision = PurchaseReturnDecision()) -> Dict[str, Any]:
    user = await require_permission(request, "purchase_return", "reject")
    try:
        doc = await svc.reject_purchase_return(return_id, rejected_by=user.get("name", "Admin"), reason=payload.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_rejected", "purchase_return", return_id, {"reason": payload.notes})
    return doc


# ─── R4 — Supplier RMA lifecycle ─────────────────────────────────────────────

@router.post("/purchase-returns/{return_id}/ship-to-supplier")
async def ship_purchase_return_to_supplier(return_id: str, request: Request,
                                           payload: SupplierShipInput = SupplierShipInput()) -> Dict[str, Any]:
    user = await require_permission(request, "purchase_return", "approve")
    try:
        doc = await svc.ship_to_supplier(return_id, actor=user.get("name", "Admin"),
                                         notes=payload.notes, carrier=payload.carrier,
                                         tracking_no=payload.tracking_no)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_shipped_supplier", "purchase_return", return_id,
                {"carrier": payload.carrier, "tracking_no": payload.tracking_no})
    return doc


@router.post("/purchase-returns/{return_id}/supplier-accept")
async def supplier_accept_purchase_return(return_id: str, request: Request,
                                          payload: SupplierAcceptInput = SupplierAcceptInput()) -> Dict[str, Any]:
    user = await require_permission(request, "purchase_return", "approve")
    try:
        doc = await svc.supplier_accept(return_id, actor=user.get("name", "Admin"),
                                        outcome=payload.outcome, notes=payload.notes,
                                        refund_account_code=getattr(payload, "refund_account_code", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_supplier_accepted", "purchase_return", return_id,
                {"outcome": payload.outcome, "debit_note": doc.get("debit_note_number")})
    return doc


@router.post("/purchase-returns/{return_id}/supplier-reject")
async def supplier_reject_purchase_return(return_id: str, request: Request,
                                          payload: SupplierRejectInput = SupplierRejectInput()) -> Dict[str, Any]:
    user = await require_permission(request, "purchase_return", "approve")
    try:
        doc = await svc.supplier_reject(return_id, actor=user.get("name", "Admin"), reason=payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_supplier_rejected", "purchase_return", return_id,
                {"reason": payload.reason})
    return doc


@router.post("/purchase-returns/{return_id}/goods-back")
async def goods_back_purchase_return(return_id: str, request: Request,
                                     payload: GoodsBackInput = GoodsBackInput()) -> Dict[str, Any]:
    user = await require_permission(request, "purchase_return", "approve")
    regrade = [{"roll_id": g.roll_id, "grade": g.grade} for g in (payload.regrade or [])]
    if payload.warehouse_id:   # E4.1 — barang yang ditolak supplier kembali ke gudang sah
        from entity_scope import entity_ctx as _ctx
        from services import warehouse_scope_service as whscope
        await whscope.assert_usable(payload.warehouse_id, (await _ctx(request)).active_entity_id,
                                   action="menerima barang kembali di sini")
    try:
        doc = await svc.goods_back(return_id, actor=user.get("name", "Admin"), regrade=regrade,
                                   warehouse_id=payload.warehouse_id, notes=payload.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_goods_back", "purchase_return", return_id,
                {"regraded": doc.get("goods_back_regraded", 0)})
    return doc


# ─── R5.4b — REVERSAL / KOREKSI retur beli terfinalisasi (→ cancelled, GL-safe) ─

@router.post("/purchase-returns/{return_id}/reverse")
async def reverse_purchase_return(return_id: str, request: Request,
                                  payload: PurchaseReturnDecision = PurchaseReturnDecision()) -> Dict[str, Any]:
    """R5.4b — Batalkan/koreksi retur beli yang sudah difinalisasi: balik JE, kembalikan barang
    ke stok, pulihkan AP (ap_credit) / void refund kas, void Nota Debit; retur → cancelled.
    Hanya admin/manager (permission purchase_return:approve). Append-only & idempotent."""
    user = await require_permission(request, "purchase_return", "approve")
    try:
        doc = await svc.reverse_settlement(
            return_id, actor=user.get("name", user.get("email", "")), reason=payload.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_reversed", "purchase_return", return_id,
                {"reason": payload.notes,
                 "reversal_jes": (doc.get("_reversal_summary") or {}).get("reversal_jes", 0),
                 "rolls_restored": (doc.get("_reversal_summary") or {}).get("rolls_restored", 0)})
    return doc


@router.delete("/purchase-returns/{return_id}")
async def delete_purchase_return(return_id: str, request: Request) -> Dict[str, Any]:
    """Hapus retur draft (tidak berdampak stok/AP)."""
    user = await require_permission(request, "purchase_return", "update")
    try:
        res = await svc.delete_purchase_return(return_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_deleted", "purchase_return", return_id,
                {"number": res.get("number")})
    return res
