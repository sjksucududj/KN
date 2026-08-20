"""PS-17 — Router **Organisasi R&D** (divisi + matriks persetujuan + anggota).

Cakupan R&D-only (D-13 poin 3a): endpoint ini hanya untuk melihat/mengatur penempatan
divisi orang R&D dan menampilkan matriks approver. TIDAK menyentuh RBAC/menu global.
Akses: peran penilai (admin/manager). Penugasan divisi: admin/manager.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from dependencies import audit, require_permission
from entity_scope import entity_ctx, resolve_list_scope
from services import rnd_org_service as org

router = APIRouter(prefix="/api")

APPRAISAL_ROLES = ("admin", "manager")


def _assert_appraisal(actor: Dict[str, Any]) -> None:
    if (actor or {}).get("role") not in APPRAISAL_ROLES:
        raise HTTPException(status_code=403,
                            detail="Hanya admin/manager yang dapat mengelola divisi R&D.")


class MemberDivisionIn(BaseModel):
    name: str
    division: str = ""  # "" = lepas dari divisi


def _eid(entity_id: Optional[str], ctx) -> str:
    return entity_id if entity_id and entity_id != "all" else ctx.active_entity_id


@router.get("/rnd/divisions")
async def list_divisions(request: Request,
                         entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Daftar divisi + jumlah anggota + matriks persetujuan (D-13)."""
    actor = await require_permission(request, "rnd", "view")
    _assert_appraisal(actor)
    ctx = await entity_ctx(request)
    return await org.list_divisions(_eid(entity_id, ctx) or "")


@router.get("/rnd/divisions/members")
async def list_members(request: Request,
                       entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Orang R&D (desainer + user) beserta divisinya."""
    actor = await require_permission(request, "rnd", "view")
    _assert_appraisal(actor)
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("md_samples", {}, ctx, entity_id)
    return await org.list_members(scope, _eid(entity_id, ctx) or "")


@router.put("/rnd/divisions/members")
async def set_member_division(payload: MemberDivisionIn, request: Request,
                              entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Tetapkan/ubah divisi seseorang (1 orang = 1 divisi). Admin/manager."""
    actor = await require_permission(request, "rnd", "view")
    _assert_appraisal(actor)
    ctx = await entity_ctx(request)
    eid = _eid(entity_id, ctx) or ""
    try:
        res = await org.set_member_division(eid, payload.name, payload.division,
                                            actor.get("name", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await audit(actor.get("name", ""), "rnd_division_assigned", "rnd_person_divisions",
                payload.name, {"division": payload.division, "entity_id": eid})
    return res
