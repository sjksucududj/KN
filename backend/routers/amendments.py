"""FASE G-1 — Router **Amandemen Dokumen** (koreksi ber-alasan, ber-dampak, ber-jejak).

  GET  /api/amendment-reasons          — label alasan yang boleh dipilih (configurable)
  PUT  /api/amendment-reasons          — tambah/ubah label alasan (admin)
  POST /api/amendments/preview         — dampak & kebijakan SEBELUM mengirim usulan
  POST /api/amendments                 — ajukan amandemen
  GET  /api/amendments                 — daftar (inbox persetujuan / riwayat)
  GET  /api/amendments/stats/summary   — ringkasan untuk badge & dashboard
  GET  /api/amendments/{id}            — detail satu amandemen
  POST /api/amendments/{id}/decision   — approve / reject
  GET  /api/amendments/doc/{type}/{id} — amandemen + nota milik satu dokumen

RBAC memakai modul izin baru `finance_amendment`:
  * `propose` — mengajukan koreksi (admin, manager, sales)
  * `approve` — memutus koreksi (admin, manager)
  * `admin`   — mengelola label alasan (admin)
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from dependencies import audit, require_permission
from entity_scope import entity_ctx, resolve_list_scope
from schemas_amendment import (AmendmentDecisionIn, AmendmentPreviewIn, AmendmentProposeIn,
                               AmendmentReasonIn)
from services import amendment_service as amd_svc

router = APIRouter(prefix="/api")


def _err(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _clean(row: Dict[str, Any]) -> Dict[str, Any]:
    """Buang payload internal (item hasil hitung ulang) dari respons publik."""
    return {k: v for k, v in (row or {}).items() if k != "payload"}


# ── Label alasan ─────────────────────────────────────────────────────────────
@router.get("/amendment-reasons")
async def list_reasons(request: Request, doc_type: str = "",
                       include_inactive: bool = False) -> List[Dict[str, Any]]:
    await require_permission(request, "finance_amendment", "propose")
    return await amd_svc.list_reasons(doc_type, include_inactive)


@router.put("/amendment-reasons")
async def upsert_reason(payload: AmendmentReasonIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_amendment", "admin")
    try:
        row = await amd_svc.upsert_reason(payload.model_dump(), actor.get("name", ""))
    except amd_svc.AmendmentError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "amendment_reason_saved", "amendment_reasons",
                row.get("id", ""), row)
    return row


# ── Pratinjau & usul ─────────────────────────────────────────────────────────
@router.post("/amendments/preview")
async def preview(payload: AmendmentPreviewIn, request: Request) -> Dict[str, Any]:
    await require_permission(request, "finance_amendment", "propose")
    try:
        out = await amd_svc.preview(
            payload.doc_type, payload.doc_id,
            [c.model_dump() for c in payload.changes],
            payload.reason_code, payload.order_discount_percent)
    except amd_svc.AmendmentError as exc:
        raise _err(exc) from exc
    return {k: v for k, v in out.items() if not k.startswith("_")}


@router.post("/amendments")
async def propose(payload: AmendmentProposeIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_amendment", "propose")
    try:
        row = await amd_svc.propose(
            payload.doc_type, payload.doc_id, payload.reason_code,
            [c.model_dump() for c in payload.changes], actor,
            note=payload.note, attachments=payload.attachments,
            order_discount_percent=payload.order_discount_percent)
    except amd_svc.AmendmentError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "amendment_proposed", "doc_amendments",
                row["id"], {"number": row["number"], "doc": row["doc_number"],
                            "reason": row["reason_code"], "impact": row["impact"],
                            "status": row["status"]}, reason=row.get("note", ""))
    return _clean(row)


# ── Daftar & detail ──────────────────────────────────────────────────────────
@router.get("/amendments")
async def list_amendments(request: Request, status: str = "", doc_type: str = "",
                          doc_id: str = "", entity_id: Optional[str] = None,
                          limit: int = 200) -> List[Dict[str, Any]]:
    await require_permission(request, "finance_amendment", "propose")
    ctx = await entity_ctx(request)
    flt: Dict[str, Any] = resolve_list_scope("doc_amendments", {}, ctx, entity_id)
    for key, val in (("status", status), ("doc_type", doc_type), ("doc_id", doc_id)):
        if val:
            flt[key] = val
    rows = await amd_svc.list_amendments(flt, limit)
    return [_clean(r) for r in rows]


@router.get("/amendments/stats/summary")
async def summary(request: Request, entity_id: Optional[str] = None) -> Dict[str, Any]:
    await require_permission(request, "finance_amendment", "propose")
    ctx = await entity_ctx(request)
    return await amd_svc.stats(resolve_list_scope("doc_amendments", {}, ctx, entity_id))


@router.get("/amendments/doc/{doc_type}/{doc_id}")
async def by_document(doc_type: str, doc_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "finance_amendment", "propose")
    rows = await amd_svc.list_amendments({"doc_type": doc_type, "doc_id": doc_id}, 200)
    return {"amendments": [_clean(r) for r in rows],
            "notes": await amd_svc.notes_for_order(doc_id)}


@router.get("/amendments/{amd_id}")
async def detail(amd_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "finance_amendment", "propose")
    row = await amd_svc.get_amendment(amd_id)
    if not row:
        raise HTTPException(status_code=404, detail="Amandemen tidak ditemukan")
    return _clean(row)


# ── Putusan ──────────────────────────────────────────────────────────────────
@router.post("/amendments/{amd_id}/decision")
async def decide(amd_id: str, payload: AmendmentDecisionIn,
                 request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "finance_amendment", "approve")
    try:
        row = await amd_svc.decide(amd_id, payload.action, actor, payload.note)
    except amd_svc.AmendmentError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), f"amendment_{payload.action}d", "doc_amendments",
                amd_id, {"number": row["number"], "status": row["status"],
                         "impact": row["impact"], "result_refs": row.get("result_refs")},
                reason=payload.note)
    return _clean(row)
