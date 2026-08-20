"""HRD H6 router — HR Analytics (Dashboard BI SDM → menu cs-bi-hrd).

Read-only agregasi. RBAC: hr.view (admin+manager). Entity-scoped via entity_ctx.
"""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, Query

from dependencies import require_permission
from entity_scope import entity_ctx
from services import hr_analytics_service as analytics

router = APIRouter(prefix="/api")


@router.get("/hr/analytics/summary")
async def hr_analytics_summary(request: Request,
                               entity_id: Optional[str] = Query(None),
                               period: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Ringkasan analitik SDM: headcount, absensi, turnover, payroll cost,
    overtime trend, statutory (BPJS/PPh21) — per entitas & periode (YYYY-MM)."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    return await analytics.hr_summary(ctx, entity_id, period)
