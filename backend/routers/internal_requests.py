"""FASE E-7 (E7d) — **PERMINTAAN INTERNAL** (`/api/internal-requests`).

Jalur yang hilang untuk sales: papan stok memberi isyarat “tersedia di badan usaha
lain”, tetapi seluruh menu Antar Entitas 403 untuk sales. Router ini membuka satu
pintu sempit & tercatat: sales **mengajukan**, admin/manajer **menindak**
(menjadikannya transaksi antar-PT G-6 atau menolak dengan alasan).

Pembagian izin (modul `internal_request`):
  * `view`    — admin · manajer · sales (sales: hanya permintaan miliknya sendiri)
  * `create`  — admin · manajer · sales
  * `cancel`  — pengaju (atau admin/manajer)
  * `reject`  — admin · manajer
  * `convert` — admin · manajer  (di FASE E-8 pindah ke peran `sales_admin`)
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from db import db
from dependencies import audit, current_user, require_permission
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas_internal_request import (
    InternalRequestConvert, InternalRequestCreate, InternalRequestDecision,
)
from services import internal_request_service as svc

router = APIRouter(prefix="/api")

CROSS_ENTITY_ROLES = ("admin", "manager")
DECIDER_ROLES = ("admin", "manager")


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _is_cross(actor: Dict[str, Any]) -> bool:
    return (actor or {}).get("role") in CROSS_ENTITY_ROLES


def _shape(doc: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    """E5.1 — rincian stok per badan usaha lain hanya untuk peran lintas-entitas."""
    return doc if _is_cross(actor) else svc.strip_entity_details(doc)


@router.get("/internal-requests/meta")
async def meta(request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "internal_request", "view")
    return {
        "statuses": [{"id": k, "label": v} for k, v in svc.STATUS_LABEL.items()],
        "can_decide": (actor or {}).get("role") in DECIDER_ROLES,
        "can_pick_source": _is_cross(actor),
        "open_statuses": list(svc.OPEN_STATUSES),
    }


@router.get("/internal-requests")
async def list_requests(request: Request,
                        status: Optional[str] = Query(None),
                        mine: bool = Query(False),
                        entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    actor = await require_permission(request, "internal_request", "view")
    ctx = await entity_ctx(request)
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    q = resolve_list_scope(svc.COLL, q, ctx, entity_id)
    # Sales melihat permintaan MILIKNYA saja (kepemilikan data — pola E8.4).
    if not _is_cross(actor) or mine:
        q["requested_by_id"] = actor.get("id", "")
    rows = await svc.list_requests(q)
    return {"items": [_shape(r, actor) for r in rows], "total": len(rows),
            "summary": await svc.summary(q)}


@router.post("/internal-requests")
async def create_request(payload: InternalRequestCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "internal_request", "create")
    ctx = await entity_ctx(request)
    try:
        doc = await svc.create(payload.model_dump(), actor,
                              requester_entity_id=ctx.active_entity_id,
                              cross_entity=_is_cross(actor))
    except svc.InternalRequestError as exc:
        raise _fail(exc) from exc
    await audit(actor.get("name", ""), "internal_request_created", "internal_request",
                doc["id"], {"number": doc["number"], "items": len(doc["items"]),
                            "est_value": doc["est_value"]})
    return _shape(doc, actor)


@router.get("/internal-requests/{req_id}")
async def get_request(req_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "internal_request", "view")
    ctx = await entity_ctx(request)
    doc = await svc.get_one(req_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Permintaan internal tidak ditemukan.")
    assert_entity_access(doc, svc.COLL, ctx)
    if not _is_cross(actor) and doc.get("requested_by_id") != actor.get("id", ""):
        raise HTTPException(status_code=403,
                            detail="Anda hanya bisa membuka permintaan internal milik sendiri.")
    return _shape(doc, actor)


@router.get("/internal-requests/{req_id}/sources")
async def request_sources(req_id: str, request: Request) -> Dict[str, Any]:
    """Kandidat badan usaha sumber + stok & kesiapan harga internalnya.

    Hanya peran lintas-entitas: isinya rincian stok badan usaha LAIN (E5.1).
    """
    actor = await require_permission(request, "internal_request", "view")
    if not _is_cross(actor):
        raise HTTPException(
            status_code=403,
            detail=("Rincian stok badan usaha lain bukan wewenang peran Anda. "
                    "Ajukan permintaannya saja — admin/manajer yang memilih badan "
                    "usaha sumber."))
    ctx = await entity_ctx(request)
    doc = await svc.get_one(req_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Permintaan internal tidak ditemukan.")
    assert_entity_access(doc, svc.COLL, ctx)
    try:
        return await svc.sources(req_id)
    except svc.InternalRequestError as exc:
        raise _fail(exc) from exc


@router.post("/internal-requests/{req_id}/cancel")
async def cancel_request(req_id: str, request: Request,
                         payload: InternalRequestDecision = InternalRequestDecision()
                         ) -> Dict[str, Any]:
    actor = await require_permission(request, "internal_request", "cancel")
    ctx = await entity_ctx(request)
    doc = await svc.get_one(req_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Permintaan internal tidak ditemukan.")
    assert_entity_access(doc, svc.COLL, ctx)
    if not _is_cross(actor) and doc.get("requested_by_id") != actor.get("id", ""):
        raise HTTPException(status_code=403,
                            detail="Hanya pengaju (atau admin/manajer) yang bisa membatalkan.")
    try:
        res = await svc.cancel(req_id, actor, payload.reason)
    except svc.InternalRequestError as exc:
        raise _fail(exc) from exc
    await audit(actor.get("name", ""), "internal_request_cancelled", "internal_request",
                req_id, {"number": doc["number"], "reason": payload.reason})
    return _shape(res, actor)


@router.post("/internal-requests/{req_id}/reject")
async def reject_request(req_id: str, request: Request,
                         payload: InternalRequestDecision = InternalRequestDecision()
                         ) -> Dict[str, Any]:
    actor = await require_permission(request, "internal_request", "reject")
    ctx = await entity_ctx(request)
    doc = await svc.get_one(req_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Permintaan internal tidak ditemukan.")
    assert_entity_access(doc, svc.COLL, ctx)
    try:
        res = await svc.reject(req_id, actor, payload.reason)
    except svc.InternalRequestError as exc:
        raise _fail(exc) from exc
    await audit(actor.get("name", ""), "internal_request_rejected", "internal_request",
                req_id, {"number": doc["number"]}, reason=payload.reason)
    return _shape(res, actor)


@router.post("/internal-requests/{req_id}/convert")
async def convert_request(req_id: str, payload: InternalRequestConvert,
                          request: Request) -> Dict[str, Any]:
    """Jadikan permintaan → transaksi antar-PT (mesin G-6, dokumen kembar)."""
    actor = await require_permission(request, "internal_request", "convert")
    ctx = await entity_ctx(request)
    doc = await svc.get_one(req_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Permintaan internal tidak ditemukan.")
    assert_entity_access(doc, svc.COLL, ctx)
    seller = (payload.source_entity_id or doc.get("source_entity_id") or "").strip()
    if seller and seller not in ctx.allowed_entity_ids:
        raise HTTPException(
            status_code=403,
            detail=("Anda tidak berwenang menerbitkan dokumen untuk badan usaha penjual "
                    "itu. Minta admin/manajer yang ditugaskan di sana."))
    try:
        res = await svc.convert(
            req_id, actor, source_entity_id=seller,
            pricing_mode=payload.pricing_mode or "", ppn_mode=payload.ppn_mode or "",
            submit_now=payload.submit_now, notes=payload.notes)
    except svc.InternalRequestError as exc:
        raise _fail(exc) from exc
    await audit(actor.get("name", ""), "internal_request_converted", "internal_request",
                req_id, {"number": doc["number"],
                         "interco_pair_id": res["interco"].get("pair_id", ""),
                         "source_entity_id": seller})
    return res


@router.get("/internal-requests-availability/{product_id}")
async def product_availability(product_id: str, request: Request) -> Dict[str, Any]:
    """Isyarat stok satu barang untuk tombol “Minta dari badan usaha lain”.

    Sales menerima ANGKA GABUNGAN saja (E5.1); admin/manajer menerima rinciannya.
    """
    actor = await require_permission(request, "internal_request", "view")
    ctx = await entity_ctx(request)
    if ctx.active_entity_id in ("", "all"):
        raise HTTPException(
            status_code=409,
            detail=("Pilih badan usaha Anda dulu — isyarat “tersedia di badan usaha lain” "
                    "selalu diukur dari sudut satu badan usaha."))
    prod = await db.products.find_one({"id": product_id},
                                      {"_id": 0, "id": 1, "sku": 1, "name": 1, "base_unit": 1})
    if not prod:
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan.")
    av = await svc.availability(product_id, ctx.active_entity_id)
    if not _is_cross(actor):
        av.pop("by_entity", None)
    return {"product": prod, **av}
