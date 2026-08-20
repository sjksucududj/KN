"""FINANCE — Analitik lanjutan: Profitabilitas, Proyeksi Kas, Control Tower.

Akses: permission module "accounting" (admin/manager). Respons OBJEK telanjang
(kontrak KN3). Semua ter-scope per entitas (buku terpisah per PT, F0-E).

Endpoint:
- GET /api/finance/profitability      → margin per produk/kategori/pelanggan/sales (WAC)
- GET /api/finance/cashflow-forecast  → proyeksi likuiditas (AR/AP jatuh tempo)
- GET /api/finance/tower              → dashboard keuangan terpadu (Control Tower)
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Query

from dependencies import require_permission
from entity_scope import entity_ctx, resolve_list_scope
from services import profitability_service as prof
from services import cashflow_forecast_service as fc
from services import finance_tower_service as tower

router = APIRouter(prefix="/api")


async def _scope(request: Request, collection: str, entity_id: Optional[str]) -> Dict[str, Any]:
    ctx = await entity_ctx(request)
    return resolve_list_scope(collection, {}, ctx, entity_id)


@router.get("/finance/profitability")
async def get_profitability(
    request: Request,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Analisis profitabilitas/margin (WAC) per 4 dimensi + tren bulanan."""
    await require_permission(request, "accounting", "view")
    scope = await _scope(request, "sales_orders", entity_id)
    ent = entity_id if entity_id and entity_id != "all" else None
    return await prof.profitability(start=start, end=end, scope=scope, entity_id=ent)


@router.get("/finance/cashflow-forecast")
async def get_cashflow_forecast(
    request: Request,
    entity_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Proyeksi arus kas ke depan dari piutang & hutang jatuh tempo."""
    await require_permission(request, "accounting", "view")
    scope = await _scope(request, "sales_orders", entity_id)
    ent = entity_id if entity_id and entity_id != "all" else None
    return await fc.cashflow_forecast(scope=scope, entity_id=ent)


@router.get("/finance/tower")
async def get_finance_tower(
    request: Request,
    entity_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Dashboard Keuangan terpadu (Control Tower)."""
    await require_permission(request, "accounting", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("journal_entries", {}, ctx, entity_id)
    ent = entity_id if entity_id and entity_id != "all" else None
    comp_ids = [entity_id] if ent else list(ctx.allowed_entity_ids)
    return await tower.finance_tower(scope=scope, entity_id=ent, entity_ids=comp_ids)
