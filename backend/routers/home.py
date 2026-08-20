"""EPIC 1 — Home/landing endpoints per role."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Query

from dependencies import current_user, require_role
from services import home_service

router = APIRouter(prefix="/api/home")


@router.get("/sales")
async def home_sales(request: Request, entity_id: Optional[str] = Query(None),
                     sales_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Performa Saya. Sales melihat dirinya sendiri; admin/manager boleh pilih sales_id."""
    user = await current_user(request)
    target = sales_id if (sales_id and user["role"] in ("admin", "manager")) else user["id"]
    return await home_service.sales_home(target, entity_id)


@router.get("/admin")
async def home_admin(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Control Tower. admin (auto) + manager."""
    await require_role(request, ["manager"])
    return await home_service.admin_home(entity_id)


@router.get("/manager")
async def home_manager(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Manager Home. admin (auto) + manager."""
    await require_role(request, ["manager"])
    return await home_service.manager_home(None, entity_id)
