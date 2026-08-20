"""F2 — Multi-bucket Stock router (WIP & Hold/Pending SO).

Papan bucket per produk + operasi Hold/Release & WIP Start/Complete.
Akses: permission "inventory" (view = baca; update = operasi). SCOPED owner_entity_id.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Query

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope
from schemas import StockHoldIn, StockWipIn
from services import stock_bucket_service as svc

router = APIRouter(prefix="/api")


@router.get("/stock/buckets")
async def stock_buckets(request: Request, product_id: Optional[str] = Query(None),
                        owner_entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("inventory_balances", {}, ctx, owner_entity_id)
    return await svc.bucket_board(scope, product_id=product_id)


@router.get("/stock/holds")
async def list_holds(request: Request, owner_entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("inventory_rolls", {}, ctx, owner_entity_id)
    return await svc.list_rolls_in_bucket(scope, "hold")


@router.get("/stock/wip")
async def list_wip(request: Request, owner_entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("inventory_rolls", {}, ctx, owner_entity_id)
    return await svc.list_rolls_in_bucket(scope, "wip")


@router.get("/stock/pending-so")
async def pending_so(request: Request, owner_entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """F2b — Papan Pending SO: backorder aktif + pencocokan ke incoming PO (promise date)."""
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("sales_orders", {}, ctx, owner_entity_id)
    return await svc.pending_so_board(scope)


@router.get("/stock/atp")
async def stock_atp(request: Request, product_id: str = Query(...),
                    owner_entity_id: Optional[str] = Query(None),
                    horizon_days: int = Query(svc.DEFAULT_ATP_HORIZON_DAYS)) -> Dict[str, Any]:
    """F2b — Detail ATP future-aware satu produk: available + incoming(horizon) − pending."""
    await require_permission(request, "inventory", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("inventory_balances", {}, ctx, owner_entity_id)
    owner = owner_entity_id if (owner_entity_id and owner_entity_id != "all") else ctx.active_entity_id
    return await svc.atp_detail(scope, product_id, owner_entity_id=owner, horizon_days=horizon_days)


def _assert_owner(ctx, owner_entity_id: str):
    if owner_entity_id not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas pemilik stok ini")


@router.post("/stock/hold")
async def create_hold(payload: StockHoldIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    ctx = await entity_ctx(request)
    _assert_owner(ctx, payload.owner_entity_id)
    res = await svc.hold_stock(payload.model_dump(), actor.get("name", ""))
    await audit(actor.get("name", ""), "stock_hold_created", "inventory", payload.product_id,
                {"qty": res["moved"], "hold_id": res["hold_id"], "owner": payload.owner_entity_id,
                 "reason": payload.reason})
    return res


@router.post("/stock/hold/{hold_id}/release")
async def release_hold(hold_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    res = await svc.release_hold(hold_id)
    await audit(actor.get("name", ""), "stock_hold_released", "inventory", hold_id, res)
    return res


@router.post("/stock/wip/start")
async def start_wip(payload: StockWipIn, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    ctx = await entity_ctx(request)
    _assert_owner(ctx, payload.owner_entity_id)
    res = await svc.start_wip(payload.model_dump(), actor.get("name", ""))
    await audit(actor.get("name", ""), "stock_wip_started", "inventory", payload.product_id,
                {"qty": res["moved"], "wip_id": res["wip_id"], "owner": payload.owner_entity_id})
    return res


@router.post("/stock/wip/{wip_id}/complete")
async def complete_wip(wip_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "update")
    res = await svc.complete_wip(wip_id)
    await audit(actor.get("name", ""), "stock_wip_completed", "inventory", wip_id, res)
    return res
