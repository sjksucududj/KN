"""
Sub-fase 1.11 — Returns & Barang Sisa
Router prefix: /api/sales-returns
"""
from fastapi import APIRouter, Request, File, UploadFile, HTTPException, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from db import db
from dependencies import require_permission, require_any_permission, audit
from core_utils import now_iso, new_id, strip_cost_fields
from entity_scope import (entity_ctx, resolve_list_scope, assert_entity_access,
                          resolve_scope_ids)
from schemas import (SalesReturnCreate, SalesReturnDecision,
                     ReturnInspectComplete, SalesReturnSettle, QuarantineReleaseInput,
                     RollOwnershipTransferInput, SalesToPurchaseReturnInput)
from services import return_service, storage_service as storage
from services import line_scope                # FASE L — pagar & penyaring lini produk
from services import return_state as st
from pagination import is_paged, get_page_params, build_search, merge_query, fetch_page, envelope

router = APIRouter(prefix="/api")


# ─── LIST ────────────────────────────────────────────────────────────────────

@router.get("/sales-returns")
async def list_returns(
    request: Request,
    status: Optional[str] = Query(None),
    order_id: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    return_type: Optional[str] = Query(None),
    line: str = Query("", description="FASE L — penyaring lini (koma untuk multi)"),
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "view")
    ctx = await entity_ctx(request)
    q: Dict = {}
    if status:      q["status"]      = status
    if order_id:    q["order_id"]    = order_id
    if return_type: q["return_type"] = return_type
    q = resolve_list_scope("sales_returns", q, ctx, entity_id)
    q = line_scope.narrow(q, user, line, field=line_scope.LINES_FIELD)   # FASE L

    def _clean(docs):
        for d in docs:
            d.pop("_id", None)
            d["attachments"] = [a for a in (d.get("attachments") or []) if not a.get("is_deleted")]
        return docs

    if is_paged(request):
        page, page_size, qs, _sort = get_page_params(request)
        if qs:
            q = merge_query(q, build_search(qs, ["number", "customer_name", "order_number"]))
        items, total = await fetch_page(db.sales_returns, q, page, page_size, sort_field="created_at", sort_dir=-1)
        return envelope(_clean(items), total, page, page_size)

    docs = await db.sales_returns.find(q, sort=[("created_at", -1)]).to_list(500)
    _clean(docs)
    return {"items": docs, "total": len(docs)}


@router.get("/sales-returns/status-counts")
async def sales_return_status_counts(request: Request,
                                     entity_id: Optional[str] = Query(None)) -> Dict[str, int]:
    """P2 — jumlah retur jual per status (untuk lencana tab), agregasi ringan.

    Kenapa endpoint sendiri: lencana tab dulu dihitung dari SELURUH daftar yang sudah
    ada di peramban. Begitu daftarnya dipaginasi, angka lencana akan diam-diam mengikuti
    isi HALAMAN, bukan isi sebenarnya — kelas bug "kartu bilang 12, daftar berisi 3".
    """
    await require_permission(request, "sales_return", "view")
    ctx = await entity_ctx(request)
    q = resolve_list_scope("sales_returns", {}, ctx, entity_id)
    pipeline = [{"$match": q}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    agg = await db.sales_returns.aggregate(pipeline).to_list(100)
    counts: Dict[str, int] = {row["_id"]: int(row["n"]) for row in agg if row.get("_id")}
    counts["all"] = sum(counts.values())
    return counts


# ─── CREDIT NOTES (F3 — Nota Kredit dari retur, posting GL) ──────────────────

@router.get("/credit-notes")
async def list_credit_notes(
    request: Request,
    customer_id: Optional[str] = Query(None),
    return_id: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    await require_permission(request, "sales_return", "view")
    ctx = await entity_ctx(request)
    q: Dict = {}
    if customer_id: q["customer_id"] = customer_id
    if return_id:   q["return_id"] = return_id
    q = resolve_list_scope("credit_notes", q, ctx, entity_id)
    docs = await db.credit_notes.find(q, sort=[("created_at", -1)]).to_list(500)
    for d in docs:
        d.pop("_id", None)
    total = round(sum(float(d.get("gross_amount", 0) or 0) for d in docs), 2)
    return {"items": strip_cost_fields(docs, ctx.user.get("role")), "total": len(docs), "total_amount": total}


@router.get("/credit-notes/{cn_id}")
async def get_credit_note(cn_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "sales_return", "view")
    ctx = await entity_ctx(request)
    doc = await db.credit_notes.find_one({"id": cn_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Credit Note tidak ditemukan")
    doc.pop("_id", None)
    assert_entity_access(doc, "credit_notes", ctx)
    return strip_cost_fields(doc, ctx.user.get("role"))


# ─── CREATE ──────────────────────────────────────────────────────────────────

@router.post("/sales-returns")
async def create_return(
    request: Request,
    payload: SalesReturnCreate,
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "create")

    order = await db.sales_orders.find_one({"id": payload.order_id})
    if not order:
        raise HTTPException(status_code=404, detail=f"Pesanan {payload.order_id} tidak ditemukan")

    allowed_statuses = {
        "confirmed", "partially_picked", "picked",
        "partially_shipped", "shipped", "done"
    }
    if order.get("status") not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Return hanya bisa dibuat dari pesanan yang sudah dikonfirmasi. Status: {order.get('status')}"
        )

    entity_id = payload.entity_id or order.get("entity_id", "")
    try:
        doc = await return_service.create_return(
            order_id=payload.order_id,
            return_type=payload.return_type,
            items=[item.dict() for item in payload.items],
            notes=payload.notes,
            entity_id=entity_id,
            created_by=user.get("name", user.get("email", "")),
            submit_now=payload.submit_now,
        )
    except ValueError as e:
        # R1-06 — retur melebihi batas / jenis tak valid → 400 dgn pesan jelas (bukan 500).
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_created", "sales_return", doc["id"],
                {"number": doc["number"], "order_id": payload.order_id, "type": payload.return_type})
    return doc


# ─── DETAIL ──────────────────────────────────────────────────────────────────

@router.get("/sales-returns/{return_id}")
async def get_return(return_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "view")
    ctx = await entity_ctx(request)
    doc = await db.sales_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    doc.pop("_id", None)
    assert_entity_access(doc, "sales_returns", ctx)
    doc["attachments"] = [a for a in (doc.get("attachments") or []) if not a.get("is_deleted")]
    return doc


# ─── SUBMIT (draft → pending_approval) ──────────────────────────────────────

@router.post("/sales-returns/{return_id}/submit")
async def submit_return(return_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "update")
    ctx = await entity_ctx(request)
    doc = await db.sales_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    doc.pop("_id", None)
    assert_entity_access(doc, "sales_returns", ctx)
    if doc["status"] != "draft":
        raise HTTPException(status_code=400, detail="Hanya draft yang bisa disubmit")
    await db.sales_returns.update_one(
        {"id": return_id},
        {"$set": {"status": "pending_approval",
                  "submitted_at": now_iso(),
                  "submitted_by": user.get("name", user.get("email", "")),
                  "updated_at": now_iso()}}
    )
    doc = await db.sales_returns.find_one({"id": return_id})
    doc.pop("_id", None)
    await audit(user.get("name", ""), "sales_return_submitted", "sales_return", return_id, {})
    return doc


# ─── APPROVE (manager) : pending_approval → approved ─────────────────────────

@router.post("/sales-returns/{return_id}/approve")
async def approve_return(
    return_id: str,
    request: Request,
    payload: SalesReturnDecision = SalesReturnDecision(),
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "approve")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    try:
        doc = await return_service.approve_return(
            return_id=return_id,
            approved_by=user.get("name", user.get("email", "")),
            notes=payload.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_approved", "sales_return", return_id,
                {"notes": payload.notes})
    return doc


# ─── INSPECT (WAJIB) : approved → inspecting → inspected ─────────────────────

@router.post("/sales-returns/{return_id}/inspect/start")
async def start_inspection(return_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "update")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    try:
        doc = await return_service.start_inspection(return_id, user.get("name", user.get("email", "")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_inspect_started", "sales_return", return_id, {})
    return doc


@router.post("/sales-returns/{return_id}/inspect/complete")
async def complete_inspection(
    return_id: str, request: Request, payload: ReturnInspectComplete = ReturnInspectComplete(),
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "update")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    try:
        doc = await return_service.complete_inspection(
            return_id, user.get("name", user.get("email", "")),
            inspections=[i.dict() for i in payload.inspections], notes=payload.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_inspected", "sales_return", return_id,
                {"items": len(payload.inspections)})
    return doc


# ─── SETTLE : inspected → refund/credit/nego settled (4 outcome, partial) ────

@router.post("/sales-returns/{return_id}/settle")
async def settle_return(
    return_id: str, request: Request, payload: SalesReturnSettle,
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "approve")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    if payload.return_warehouse_id:   # E4.1 — barang retur masuk ke gudang yang sah
        from services import warehouse_scope_service as whscope
        await whscope.assert_usable(payload.return_warehouse_id,
                                   existing.get("entity_id") or ctx.active_entity_id,
                                   action="menerima barang retur di sini",
                                   field_label="Gudang retur")
    try:
        doc = await return_service.settle_return(
            return_id, user.get("name", user.get("email", "")),
            outcome=payload.outcome,
            item_decisions=[d.dict() for d in payload.item_decisions],
            notes=payload.notes,
            return_warehouse_id=payload.return_warehouse_id,
            refund_account_code=payload.refund_account_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_settled", "sales_return", return_id,
                {"outcome": payload.outcome,
                 "return_warehouse_id": payload.return_warehouse_id})
    return doc


# ─── R5.4 — REVERSAL / KOREKSI settle (settled → cancelled, GL-safe) ─────────

@router.post("/sales-returns/{return_id}/reverse")
async def reverse_return_settlement(
    return_id: str, request: Request,
    payload: SalesReturnDecision = SalesReturnDecision(),
) -> Dict[str, Any]:
    """R5.4 — Batalkan/koreksi retur yang sudah settled: balik JE, hapus roll restock,
    void refund kas & entri store credit, void Credit Note; retur → cancelled (append-only)."""
    user = await require_permission(request, "sales_return", "approve")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    try:
        doc = await return_service.reverse_settlement(
            return_id, user.get("name", user.get("email", "")), reason=payload.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_reversed", "sales_return", return_id,
                {"reason": payload.notes,
                 "reversal_jes": (doc.get("_reversal_summary") or {}).get("reversal_jes", 0)})
    return doc


# ─── R5.4b — REVERSAL WRITE-OFF (un-scrap) roll retur karantina ──────────────

class WriteoffReversalInput(BaseModel):
    """Body reversal write-off: roll_ids opsional (kosong = semua roll scrap retur ini)."""
    roll_ids: Optional[List[str]] = None
    reason: Optional[str] = ""


@router.post("/sales-returns/{return_id}/reverse-writeoff")
async def reverse_return_writeoff(
    return_id: str, request: Request,
    payload: WriteoffReversalInput = WriteoffReversalInput(),
) -> Dict[str, Any]:
    """R5.4b — Batalkan write-off (scrap) roll retur & kembalikan roll fisik ke stok:
    balik jurnal write-off (Dr 1-1300/Cr 5-9500), roll damaged → available, rebuild balance.
    Hanya admin/manager (permission sales_return:approve). Append-only & idempotent."""
    user = await require_permission(request, "sales_return", "approve")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    try:
        doc = await return_service.reverse_writeoff(
            return_id, actor=user.get("name", user.get("email", "")),
            roll_ids=payload.roll_ids, reason=payload.reason or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_writeoff_reversed", "sales_return", return_id,
                {"reason": payload.reason,
                 "rolls": (doc.get("_writeoff_reversal_summary") or {}).get("rolls", 0),
                 "amount": (doc.get("_writeoff_reversal_summary") or {}).get("amount", 0)})
    return doc


# ─── QUARANTINE (R2) : list + release/approve roll retur ─────────────────────

@router.get("/sales-returns/{return_id}/quarantine")
async def list_quarantine_rolls(return_id: str, request: Request) -> List[Dict[str, Any]]:
    await require_permission(request, "sales_return", "view")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    return await return_service.get_return_quarantine_rolls(return_id)


@router.post("/sales-returns/{return_id}/quarantine/release")
async def release_quarantine(
    return_id: str, request: Request, payload: QuarantineReleaseInput = QuarantineReleaseInput(),
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "approve")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    try:
        doc = await return_service.release_quarantine(
            return_id, user.get("name", user.get("email", "")),
            decisions=[d.dict() for d in payload.decisions], notes=payload.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_quarantine_released", "sales_return", return_id,
                {"decisions": len(payload.decisions)})
    return doc


# ─── FASE E-9 (E9.6) — JEJAK RANTAI RETUR ────────────────────────────────────

@router.get("/returns/chain/{doc_id}")
async def return_chain(doc_id: str, request: Request) -> Dict[str, Any]:
    """Rantai retur utuh: retur pelanggan → retur antar-PT → retur beli / disimpan.

    Menerima id retur MANA PUN dari ketiganya (jadi tidak ada jalan buntu: dari
    dokumen apa pun pengguna melihat rantai yang sama).

    Izin sengaja "salah satu dari" tiga domain retur: pemegang retur BELI (gudang /
    pembelian) tidak punya `sales_return.view`, dan kalau izinnya dipaksa ke satu
    domain saja mereka justru 403 di rantai dokumennya sendiri. Isi yang bukan milik
    badan usaha pembaca diringkas oleh `return_chain_service` (aturan E5.3).
    """
    user = await require_any_permission(request, [("sales_return", "view"),
                                                 ("purchase_return", "view"),
                                                 ("interco", "view")])
    _ = user  # pemeriksaan izin saja; rantai bersifat read-only
    ctx = await entity_ctx(request)
    from services import return_chain_service as _chain
    try:
        return await _chain.chain(doc_id, viewer_entity_ids=resolve_scope_ids(ctx),
                                  cross_entity=bool(ctx.is_cross_entity))
    except _chain.ChainForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


# ─── R3 — CROSS-ENTITY: pindah kepemilikan roll retur (inter-entity, GL-safe) ─

@router.post("/sales-returns/{return_id}/rolls/{roll_id}/transfer-ownership")
async def transfer_roll_ownership(
    return_id: str, roll_id: str, request: Request,
    payload: RollOwnershipTransferInput = None,
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "approve")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    if payload is None or not payload.dest_entity_id:
        raise HTTPException(status_code=400, detail="Entitas tujuan (dest_entity_id) wajib diisi")
    try:
        result = await return_service.transfer_return_roll_ownership(
            return_id, roll_id, payload.dest_entity_id,
            user.get("name", user.get("email", "")), notes=payload.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "sales_return_roll_ownership_transferred", "sales_return", return_id,
                {"roll_id": roll_id, "to_entity": payload.dest_entity_id,
                 "transfer_id": result.get("transfer_id"), "je_posted": result.get("je", {}).get("posted")})
    return result


# ─── R4 — Chain: buat Retur Beli dari Retur Jual ─────────────────────────────

@router.post("/sales-returns/{return_id}/create-purchase-return")
async def create_purchase_return_from_sales_return(
    return_id: str, request: Request,
    payload: SalesToPurchaseReturnInput = SalesToPurchaseReturnInput(),
) -> Dict[str, Any]:
    """Teruskan barang cacat dari retur jual (roll karantina/available) sebagai retur ke SUPPLIER.
    Menghormati kebijakan impor (§J): impor & tak-returnable → 400 (rekomendasi regrade + jual lokal)."""
    user = await require_permission(request, "purchase_return", "create")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    from services import purchase_return_service as pr_svc
    if payload.warehouse_id:   # E4.1 — roll cacat keluar dari gudang yang sah
        from services import warehouse_scope_service as whscope
        await whscope.assert_usable(payload.warehouse_id,
                                   existing.get("entity_id") or ctx.active_entity_id,
                                   action="mengembalikan barang dari sini")
    try:
        pr = await pr_svc.create_from_sales_return(
            return_id, actor=user.get("name", user.get("email", "")),
            roll_ids=payload.roll_ids, supplier_id=payload.supplier_id,
            warehouse_id=payload.warehouse_id, reason=payload.reason, notes=payload.notes,
            bypass_import_policy=payload.bypass_import_policy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "purchase_return_created_from_sales_return", "purchase_return", pr["id"],
                {"sales_return_id": return_id, "purchase_return_number": pr.get("number"),
                 "supplier": pr.get("supplier_name")})
    return pr


# ─── REJECT ──────────────────────────────────────────────────────────────────

@router.post("/sales-returns/{return_id}/reject")
async def reject_return(
    return_id: str,
    request: Request,
    payload: SalesReturnDecision = SalesReturnDecision(),
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "reject")
    ctx = await entity_ctx(request)
    existing = await db.sales_returns.find_one({"id": return_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    existing.pop("_id", None)
    assert_entity_access(existing, "sales_returns", ctx)
    doc = await return_service.reject_return(
        return_id=return_id,
        rejected_by=user.get("name", user.get("email", "")),
        reason=payload.notes,
    )
    await audit(user.get("name", ""), "sales_return_rejected", "sales_return", return_id,
                {"reason": payload.notes})
    return doc


# ─── ATTACHMENTS ─────────────────────────────────────────────────────────────

@router.post("/sales-returns/{return_id}/attachments")
async def upload_attachment(
    return_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "update")
    doc = await db.sales_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    if doc["status"] in st.TERMINAL_STATES:
        raise HTTPException(status_code=400, detail="Return sudah selesai/ditolak, tidak bisa tambah lampiran")

    data = await file.read()
    content_type = storage.validate_upload(file.filename, file.content_type, len(data))
    path = f"sales_returns/{return_id}/{new_id('att')}-{file.filename}"
    result = await storage.put_object(path, data, content_type)

    att = {
        "id":          new_id("att"),
        "filename":    file.filename,
        "url":         result.get("url", ""),
        "path":        path,
        "size":        len(data),
        "content_type":content_type,
        "uploaded_by": user.get("name", ""),
        "uploaded_at": now_iso(),
        "is_deleted":  False,
    }
    await db.sales_returns.update_one(
        {"id": return_id},
        {"$push": {"attachments": att}, "$set": {"updated_at": now_iso()}}
    )
    await audit(user.get("name", ""), "sales_return_attachment_added", "sales_return", return_id,
                {"filename": file.filename})
    return att


@router.get("/sales-returns/{return_id}/attachments/{att_id}/download")
async def download_attachment(return_id: str, att_id: str, request: Request):
    await require_permission(request, "sales_return", "view")
    doc = await db.sales_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    att = next((a for a in (doc.get("attachments") or []) if a.get("id") == att_id and not a.get("is_deleted")), None)
    if not att:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    from fastapi.responses import Response
    obj = await storage.get_object(att["path"])
    return Response(
        content=obj["data"],
        media_type=att.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{att["filename"]}"'}
    )


@router.delete("/sales-returns/{return_id}/attachments/{att_id}")
async def delete_attachment(return_id: str, att_id: str, request: Request) -> Dict[str, Any]:
    user = await require_permission(request, "sales_return", "update")
    ctx = await entity_ctx(request)
    doc = await db.sales_returns.find_one({"id": return_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Return tidak ditemukan")
    doc.pop("_id", None)
    assert_entity_access(doc, "sales_returns", ctx)
    att = next((a for a in (doc.get("attachments") or [])
                if a.get("id") == att_id and not a.get("is_deleted")), None)
    if not att:
        raise HTTPException(status_code=404, detail="Lampiran tidak ditemukan")
    await db.sales_returns.update_one(
        {"id": return_id, "attachments.id": att_id},
        {"$set": {"attachments.$.is_deleted": True, "updated_at": now_iso()}}
    )
    await audit(user.get("name", ""), "sales_return_attachment_deleted", "sales_return", return_id,
                {"attachment_id": att_id})
    return {"ok": True}
