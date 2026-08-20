"""M0 — Color Library router (master warna Pantone-style).

Koleksi `color_library` = SHARED (tak di-scope entitas), mirip products/uoms.
Endpoint auth wajib via require_permission resource "color".
Respons = ARRAY/OBJEK telanjang (kontrak KN, tanpa envelope).
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request, Query

from dependencies import require_permission, audit
from schemas import ColorCreate, ColorPatch
from services import color_service as svc

router = APIRouter(prefix="/api")


@router.get("/color-library")
async def list_color_library(
    request: Request,
    q: str = Query(""),
    family: str = Query(""),
    system: str = Query(""),
    status: str = Query("active"),
) -> List[Dict[str, Any]]:
    await require_permission(request, "color", "view")
    return await svc.list_colors(q=q, family=family, system=system, status=status)


@router.get("/color-library/nearest")
async def nearest_color(request: Request, hex: str = Query(...), limit: int = Query(8)) -> Dict[str, Any]:
    await require_permission(request, "color", "view")
    try:
        return await svc.nearest(hex, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/color-library")
async def create_color(payload: ColorCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "color", "create")
    try:
        color = await svc.create_color(payload.model_dump(), actor.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "color_created", "color", color["id"],
                {"code": color["code"], "name": color["name"]})
    return color


@router.patch("/color-library/{color_id}")
async def patch_color(color_id: str, payload: ColorPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "color", "update")
    try:
        color = await svc.update_color(color_id, payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if color is None:
        raise HTTPException(status_code=404, detail="Warna tidak ditemukan")
    await audit(actor.get("name", ""), "color_updated", "color", color_id, {})
    return color


@router.delete("/color-library/{color_id}")
async def delete_color(color_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "color", "delete")
    try:
        res = await svc.delete_color(color_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await audit(actor.get("name", ""), "color_deleted", "color", color_id, res)
    return res
