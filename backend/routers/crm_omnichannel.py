"""CRM Omnichannel router — Lead pipeline + timeline interaksi (MVP manual).

Akses: modul `customer` (view untuk baca; create/update untuk tulis).
Row-level: sales hanya melihat/ubah data miliknya. Scoping per-entitas.
Respons OBJEK/ARRAY telanjang (kontrak KN3).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel

from dependencies import require_permission, audit
from entity_scope import entity_ctx
from core_utils import DEFAULT_ENTITY_ID
from services import crm_omnichannel_service as oc

router = APIRouter(prefix="/api")


# ── Payloads ────────────────────────────────────────────────────────────────
class LeadCreate(BaseModel):
    name: str
    company: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    source: Optional[str] = "other"
    stage: Optional[str] = "new"
    est_value: Optional[float] = 0
    owner_id: Optional[str] = None
    notes: Optional[str] = ""
    entity_id: Optional[str] = None


class LeadPatch(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    stage: Optional[str] = None
    est_value: Optional[float] = None
    owner_id: Optional[str] = None
    notes: Optional[str] = None
    lost_reason: Optional[str] = None


class LeadConvert(BaseModel):
    customer_id: Optional[str] = None  # link ke customer existing; kosong = buat baru


class InteractionCreate(BaseModel):
    channel: str
    direction: Optional[str] = "outbound"
    subject: Optional[str] = ""
    notes: Optional[str] = ""
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    occurred_at: Optional[str] = None
    follow_up_date: Optional[str] = None
    entity_id: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _read_scope(request: Request, entity_id: Optional[str], actor: Dict[str, Any],
                      owner_field: Optional[str] = None) -> Dict[str, Any]:
    """Bangun filter query: entitas + row-scope sales."""
    ctx = await entity_ctx(request)
    q: Dict[str, Any] = {}
    if entity_id and entity_id != "all":
        if entity_id not in ctx.allowed_entity_ids:
            raise HTTPException(status_code=403, detail="Tidak memiliki akses ke entitas ini.")
        q["entity_id"] = entity_id
    else:
        q["entity_id"] = {"$in": list(ctx.allowed_entity_ids)}
    if actor.get("role") == "sales" and owner_field:
        q[owner_field] = actor["id"]
    return q


async def _resolve_entity(request: Request, entity_id: Optional[str]) -> str:
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id
    if not eid or eid == "all":
        eid = ctx.allowed_entity_ids[0] if ctx.allowed_entity_ids else DEFAULT_ENTITY_ID
    return eid


# ═══════════════════════════════════════════════════════════════════════════
#  LEADS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/crm/leads")
async def list_leads(request: Request, stage: Optional[str] = Query(None),
                     owner_id: Optional[str] = Query(None),
                     entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    actor = await require_permission(request, "customer", "view")
    scope = await _read_scope(request, entity_id, actor, owner_field="owner_id")
    return await oc.list_leads(scope, stage=stage, owner_id=owner_id)


@router.get("/crm/leads/board")
async def leads_board(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "view")
    scope = await _read_scope(request, entity_id, actor, owner_field="owner_id")
    return await oc.board(scope)


@router.get("/crm/pipeline-stats")
async def pipeline_stats(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "view")
    scope = await _read_scope(request, entity_id, actor, owner_field="owner_id")
    return await oc.pipeline_stats(scope)


@router.post("/crm/leads")
async def create_lead(payload: LeadCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "create")
    if not (payload.name or "").strip():
        raise HTTPException(status_code=400, detail="Nama lead wajib diisi.")
    eid = await _resolve_entity(request, payload.entity_id)
    lead = await oc.create_lead(payload.model_dump(), actor, eid)
    await audit(actor["name"], "lead_created", "crm_lead", lead["id"], {"name": lead["name"], "stage": lead["stage"]})
    return lead


async def _guard_lead_owner(request: Request, lead_id: str, actor: Dict[str, Any]):
    lead = await oc.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan.")
    if actor.get("role") == "sales" and lead.get("owner_id") != actor["id"]:
        raise HTTPException(status_code=403, detail="Lead ini bukan milik Anda.")
    return lead


@router.patch("/crm/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "update")
    await _guard_lead_owner(request, lead_id, actor)
    try:
        updated = await oc.update_lead(lead_id, {k: v for k, v in payload.model_dump().items() if v is not None})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Lead tidak ditemukan.")
    await audit(actor["name"], "lead_updated", "crm_lead", lead_id, {"stage": updated.get("stage")})
    return updated


@router.post("/crm/leads/{lead_id}/convert")
async def convert_lead(lead_id: str, payload: LeadConvert, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "create")
    await _guard_lead_owner(request, lead_id, actor)
    result, err = await oc.convert_lead(lead_id, actor, payload.customer_id)
    if err:
        raise HTTPException(status_code=400, detail=err)
    await audit(actor["name"], "lead_converted", "crm_lead", lead_id, {"customer_id": result["customer_id"]})
    return result


@router.delete("/crm/leads/{lead_id}")
async def delete_lead(lead_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "update")
    await _guard_lead_owner(request, lead_id, actor)
    ok = await oc.delete_lead(lead_id)
    await audit(actor["name"], "lead_deleted", "crm_lead", lead_id, {})
    return {"deleted": ok}


# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIONS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/crm/interactions")
async def list_interactions(request: Request, customer_id: Optional[str] = Query(None),
                            lead_id: Optional[str] = Query(None), channel: Optional[str] = Query(None),
                            entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    actor = await require_permission(request, "customer", "view")
    scope = await _read_scope(request, entity_id, actor, owner_field="created_by_id")
    return await oc.list_interactions(scope, customer_id=customer_id, lead_id=lead_id, channel=channel)


@router.post("/crm/interactions")
async def create_interaction(payload: InteractionCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "create")
    if not (payload.subject or "").strip() and not (payload.notes or "").strip():
        raise HTTPException(status_code=400, detail="Isi subjek atau catatan interaksi.")
    eid = await _resolve_entity(request, payload.entity_id)
    intx = await oc.create_interaction(payload.model_dump(), actor, eid)
    await audit(actor["name"], "interaction_logged", "crm_interaction", intx["id"],
                {"channel": intx["channel"], "customer_id": intx.get("customer_id")})
    return intx


@router.delete("/crm/interactions/{intx_id}")
async def delete_interaction(intx_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "update")
    intx = await oc.get_interaction(intx_id)
    if not intx:
        raise HTTPException(status_code=404, detail="Interaksi tidak ditemukan.")
    if actor.get("role") == "sales" and intx.get("created_by_id") != actor["id"]:
        raise HTTPException(status_code=403, detail="Interaksi ini bukan milik Anda.")
    ok = await oc.delete_interaction(intx_id)
    await audit(actor["name"], "interaction_deleted", "crm_interaction", intx_id, {})
    return {"deleted": ok}
