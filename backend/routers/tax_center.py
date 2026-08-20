"""EPIC 7 — Pusat Pajak (PPN + PPh) router.

Read-mostly, ENTITY-AWARE. Permission modul `accounting` (admin+manager; sales DITOLAK).
- GET  /api/tax/summary           → rekap PPN (SPT Masa) + PPh (configurable) per periode/entitas
- GET  /api/tax/pph-records       → daftar rekaman PPh manual
- POST /api/tax/pph-records       → rekam DPP PPh manual (butir basis=manual)
- DELETE /api/tax/pph-records/{id}→ hapus rekaman

Config pajak (tarif PPN, butir PPh) dikelola lewat GET/PUT /api/settings (config_service).
PKP/non-PKP mengikuti business_entities.default_tax_mode (via config_service).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request

from dependencies import require_permission, audit
from entity_scope import entity_ctx
from schemas_finance import PphRecordInput
from services import tax_center_service as svc

router = APIRouter(prefix="/api")


def _resolve_eid(entity_id: Optional[str], ctx) -> str:
    """entity_id eksplisit menang; else konteks (all → '' agar lintas-entitas)."""
    if entity_id:
        return entity_id
    return "" if ctx.view_all else ctx.active_entity_id


def _assert_eid_access(ctx, eid: str) -> None:
    """Anti-IDOR: pastikan entitas dalam cakupan user (skip utk 'all'/kosong = lintas)."""
    if eid and eid != "all" and not ctx.view_all and eid not in (ctx.allowed_entity_ids or []):
        raise HTTPException(status_code=404, detail="Data tidak ditemukan untuk entitas ini")


@router.get("/tax/summary")
async def get_tax_summary(request: Request, period: str = None,
                          entity_id: str = None) -> Dict[str, Any]:
    """Rekap Pusat Pajak: PPN (keluaran−masukan) + PPh (butir configurable)."""
    await require_permission(request, "accounting", "view")
    ctx = await entity_ctx(request)
    eid = _resolve_eid(entity_id, ctx)
    if eid and eid != "all":
        _assert_eid_access(ctx, eid)
    return await svc.tax_summary(eid or "all", period)


@router.get("/tax/pph-records")
async def list_pph_records(request: Request, period: str = None,
                           code: str = None, entity_id: str = None) -> List[Dict[str, Any]]:
    await require_permission(request, "accounting", "view")
    ctx = await entity_ctx(request)
    eid = _resolve_eid(entity_id, ctx)
    if eid and eid != "all":
        _assert_eid_access(ctx, eid)
    return await svc.list_pph_records(eid, period, code)


@router.post("/tax/pph-records")
async def create_pph_record(payload: PphRecordInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "accounting", "manage")
    ctx = await entity_ctx(request)
    _assert_eid_access(ctx, payload.entity_id)
    try:
        doc = await svc.record_pph(
            entity_id=payload.entity_id, period=payload.period, code=payload.code,
            name=payload.name, rate=payload.rate, dpp=payload.dpp, note=payload.note,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await audit(actor["name"], "pph_record_created", "tax_pph_records", doc["id"], doc)
    return doc


@router.delete("/tax/pph-records/{record_id}")
async def delete_pph_record(record_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "accounting", "manage")
    ok = await svc.delete_pph_record(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rekaman PPh tidak ditemukan")
    await audit(actor["name"], "pph_record_deleted", "tax_pph_records", record_id, {})
    return {"deleted": True, "id": record_id}
