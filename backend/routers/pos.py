"""F-4b — POS advanced recommendations router (best-seller, FBT, substitutes). Read-only."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request

from dependencies import require_permission
from services import pos_recommendation_service as pos_svc

router = APIRouter(prefix="/api")


@router.get("/pos/best-sellers")
async def get_best_sellers(
    request: Request,
    entity_id: Optional[str] = Query(None),
    limit: int = Query(8, ge=1, le=30),
) -> List[Dict[str, Any]]:
    # INV-AUTH-01 (KN-076-AUTH-MASTER-LEAK P1): analitik penjualan WAJIB login.
    await require_permission(request, "order", "view")
    return await pos_svc.best_sellers(entity_id=entity_id, limit=limit)


@router.get("/pos/frequently-bought-together")
async def get_frequently_bought_together(
    request: Request,
    product_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    limit: int = Query(6, ge=1, le=20),
) -> List[Dict[str, Any]]:
    # INV-AUTH-01 (KN-076-AUTH-MASTER-LEAK P1): analitik penjualan WAJIB login.
    await require_permission(request, "order", "view")
    return await pos_svc.frequently_bought_together(product_id, entity_id=entity_id, limit=limit)


@router.get("/pos/substitutes")
async def get_substitutes(
    request: Request,
    product_id: str = Query(...),
    entity_id: Optional[str] = Query(None),
    limit: int = Query(6, ge=1, le=20),
) -> List[Dict[str, Any]]:
    # INV-AUTH-01 (KN-076-AUTH-MASTER-LEAK P1): analitik penjualan WAJIB login.
    await require_permission(request, "order", "view")
    return await pos_svc.substitutes(product_id, entity_id=entity_id, limit=limit)
