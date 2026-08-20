"""R6.4 — Produksi In-House (BOM + Work Order) router.

Akses: permission resource **"production"** (admin/manager penuh; warehouse view/create/release/complete).
Koleksi `mfg_boms` + `mfg_work_orders` SCOPED per entitas. Respons OBJEK telanjang (kontrak KN3).

Endpoint:
- GET    /api/production/boms                     → daftar BOM (filter status, output_product_id)
- POST   /api/production/boms                     → buat BOM (output + components + overhead)
- GET    /api/production/boms/{bom_id}            → detail BOM
- PATCH  /api/production/boms/{bom_id}            → ubah BOM
- DELETE /api/production/boms/{bom_id}            → hapus BOM (blok bila dipakai WO terbuka)
- GET    /api/production/work-orders              → daftar WO (filter status, bom_id)
- POST   /api/production/work-orders              → buat WO (draft) + rencana bahan + ketersediaan
- GET    /api/production/work-orders/{wo_id}      → detail WO (+refresh ketersediaan bila terbuka)
- POST   /api/production/work-orders/{wo_id}/release   → rilis WO (siap produksi)
- POST   /api/production/work-orders/{wo_id}/complete  → selesai: konsumsi bahan → produksi barang jadi
- POST   /api/production/work-orders/{wo_id}/cancel    → batalkan WO (draft/released)
- GET    /api/production/summary                  → ringkasan produksi (KPI)
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope
from services import production_service as prod

router = APIRouter(prefix="/api")


# ─── Schemas (inline; ringkas & self-contained) ──────────────────────────────
class BOMComponentIn(BaseModel):
    material_product_id: str
    qty_per_unit: float = Field(..., gt=0)


class BOMCreate(BaseModel):
    entity_id: Optional[str] = None
    name: str
    output_product_id: str
    components: List[BOMComponentIn]
    overhead_per_unit: float = 0
    notes: Optional[str] = ""


class BOMUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    overhead_per_unit: Optional[float] = None
    notes: Optional[str] = None
    components: Optional[List[BOMComponentIn]] = None


class WOCreate(BaseModel):
    entity_id: Optional[str] = None
    bom_id: str
    planned_qty: float = Field(..., gt=0)
    warehouse_id: str
    notes: Optional[str] = ""


class WOAction(BaseModel):
    reason: Optional[str] = ""


async def _scope(request: Request, entity_id: Optional[str]) -> Dict[str, Any]:
    ctx = await entity_ctx(request)
    return resolve_list_scope("mfg_work_orders", {}, ctx, entity_id)


async def _entity_or_active(request: Request, entity_id: Optional[str]) -> str:
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id or "ent_ksc"
    if eid == "all":
        eid = ctx.active_entity_id or "ent_ksc"
    if eid not in (ctx.allowed_entity_ids or [eid]):
        raise HTTPException(status_code=403, detail="Entitas di luar akses Anda.")
    return eid


# ═══ BOM ═════════════════════════════════════════════════════════════════════
@router.get("/production/boms")
async def list_boms(request: Request, status: Optional[str] = Query(None),
                    output_product_id: Optional[str] = Query(None),
                    entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "production", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("mfg_boms", {}, ctx, entity_id)
    return await prod.list_boms(scope, status, output_product_id)


@router.post("/production/boms")
async def create_bom(request: Request, payload: BOMCreate) -> Dict[str, Any]:
    actor = await require_permission(request, "production", "manage_bom")
    entity_id = await _entity_or_active(request, payload.entity_id)
    try:
        doc = await prod.create_bom(
            {**payload.model_dump(), "components": [c.model_dump() for c in payload.components]},
            entity_id, actor.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "bom_created", "production", doc["id"],
                {"name": doc["name"], "output": doc["output_product_id"]})
    return doc


@router.get("/production/boms/{bom_id}")
async def get_bom(request: Request, bom_id: str) -> Dict[str, Any]:
    await require_permission(request, "production", "view")
    scope = await _bom_scope(request)
    doc = await prod.get_bom(bom_id, scope)
    if not doc:
        raise HTTPException(status_code=404, detail="BOM tidak ditemukan.")
    return doc


@router.patch("/production/boms/{bom_id}")
async def update_bom(request: Request, bom_id: str, patch: BOMUpdate) -> Dict[str, Any]:
    actor = await require_permission(request, "production", "manage_bom")
    scope = await _bom_scope(request)
    body = patch.model_dump(exclude_none=True)
    if "components" in body:
        body["components"] = [c if isinstance(c, dict) else c.model_dump() for c in body["components"]]
    try:
        res = await prod.update_bom(bom_id, body, scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not res:
        raise HTTPException(status_code=404, detail="BOM tidak ditemukan.")
    await audit(actor.get("name", ""), "bom_updated", "production", bom_id, {})
    return res


@router.delete("/production/boms/{bom_id}")
async def delete_bom(request: Request, bom_id: str) -> Dict[str, Any]:
    actor = await require_permission(request, "production", "manage_bom")
    scope = await _bom_scope(request)
    try:
        ok = await prod.delete_bom(bom_id, scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="BOM tidak ditemukan.")
    await audit(actor.get("name", ""), "bom_deleted", "production", bom_id, {})
    return {"ok": True, "deleted": bom_id}


async def _bom_scope(request: Request) -> Dict[str, Any]:
    ctx = await entity_ctx(request)
    return resolve_list_scope("mfg_boms", {}, ctx, None)


# ═══ Work Order ══════════════════════════════════════════════════════════════
@router.get("/production/work-orders")
async def list_work_orders(request: Request, status: Optional[str] = Query(None),
                           bom_id: Optional[str] = Query(None),
                           entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "production", "view")
    scope = await _scope(request, entity_id)
    return await prod.list_work_orders(scope, status, bom_id)


@router.post("/production/work-orders")
async def create_work_order(request: Request, payload: WOCreate) -> Dict[str, Any]:
    actor = await require_permission(request, "production", "create")
    entity_id = await _entity_or_active(request, payload.entity_id)
    try:
        doc = await prod.create_work_order(payload.model_dump(), entity_id, actor.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "work_order_created", "production", doc["id"],
                {"wo_number": doc["wo_number"], "bom": doc["bom_id"], "qty": doc["planned_qty"]})
    return doc


@router.get("/production/work-orders/{wo_id}")
async def get_work_order(request: Request, wo_id: str) -> Dict[str, Any]:
    await require_permission(request, "production", "view")
    scope = await _scope(request, None)
    doc = await prod.get_work_order(wo_id, scope)
    if not doc:
        raise HTTPException(status_code=404, detail="Work Order tidak ditemukan.")
    return doc


@router.post("/production/work-orders/{wo_id}/release")
async def release_work_order(request: Request, wo_id: str) -> Dict[str, Any]:
    actor = await require_permission(request, "production", "release")
    scope = await _scope(request, None)
    try:
        res = await prod.release_work_order(wo_id, scope, actor.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "work_order_released", "production", wo_id, {})
    return res


@router.post("/production/work-orders/{wo_id}/complete")
async def complete_work_order(request: Request, wo_id: str) -> Dict[str, Any]:
    actor = await require_permission(request, "production", "complete")
    scope = await _scope(request, None)
    try:
        res = await prod.complete_work_order(wo_id, scope, actor.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "work_order_completed", "production", wo_id,
                {"produced_qty": res.get("produced_qty"), "total_cost": res.get("total_cost")})
    return res


@router.post("/production/work-orders/{wo_id}/cancel")
async def cancel_work_order(request: Request, wo_id: str, payload: WOAction) -> Dict[str, Any]:
    actor = await require_permission(request, "production", "cancel")
    scope = await _scope(request, None)
    try:
        res = await prod.cancel_work_order(wo_id, scope, actor.get("name", ""), payload.reason or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "work_order_cancelled", "production", wo_id, {})
    return res


@router.get("/production/summary")
async def production_summary(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "production", "view")
    scope = await _scope(request, entity_id)
    return await prod.summary(scope)
