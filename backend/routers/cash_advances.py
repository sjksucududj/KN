"""Router — Form Pengajuan Dana (Cash Advance) + Pertanggungjawaban (Settlement).

Koleksi kanonik: cash_advances (ca_), cash_advance_settlements (stl_), expense_categories (excat_).
RBAC: modul `cash_advance` & `cash_settlement`. Rantai approval berjenjang (state-machine di service).
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Request, Query

from dependencies import require_permission
from entity_scope import entity_ctx
from schemas_cash_advance import (
    CashAdvanceCreate, CashAdvanceUpdate, ApprovalDecision, DisburseInput,
    SettlementCreate, SettlementUpdate, ExpenseCategoryUpdate,
)
from services import cash_advance_service as svc

router = APIRouter(prefix="/api")


# ─── Expense Categories (mapping kategori → akun) ────────────────────────
@router.get("/expense-categories")
async def list_expense_categories(request: Request, active_only: bool = Query(False)) -> List[Dict[str, Any]]:
    """FASE E-4 (E4.3) — kategori EFEKTIF badan usaha aktif: global + override, tanpa kembar."""
    await require_permission(request, "cash_settlement", "view")
    ctx = await entity_ctx(request)
    return await svc.list_expense_categories(active_only=active_only,
                                             entity_id=ctx.active_entity_id)


@router.patch("/expense-categories/{code}")
async def update_expense_category(code: str, payload: ExpenseCategoryUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_settlement", "manage")
    return await svc.update_expense_category(code, payload.model_dump(exclude_none=True), actor)


# ─── Cash Advance (Form PD) ──────────────────────────────────────
@router.get("/cash-advances")
async def list_cash_advances(request: Request, entity_id: str = Query(None),
                             status: str = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "cash_advance", "view")
    ctx = await entity_ctx(request)
    return await svc.list_cash_advances(ctx, entity_id=entity_id, status=status)


@router.post("/cash-advances")
async def create_cash_advance(payload: CashAdvanceCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_advance", "create")
    ctx = await entity_ctx(request)
    return await svc.create_cash_advance(payload, ctx, actor)


@router.get("/cash-advances/{ca_id}")
async def get_cash_advance(ca_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "cash_advance", "view")
    ctx = await entity_ctx(request)
    return await svc.get_cash_advance(ca_id, ctx)


@router.patch("/cash-advances/{ca_id}")
async def update_cash_advance(ca_id: str, payload: CashAdvanceUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_advance", "update")
    ctx = await entity_ctx(request)
    return await svc.update_cash_advance(ca_id, payload, ctx, actor)


@router.post("/cash-advances/{ca_id}/submit")
async def submit_cash_advance(ca_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_advance", "submit")
    ctx = await entity_ctx(request)
    return await svc.submit_cash_advance(ca_id, ctx, actor)


@router.post("/cash-advances/{ca_id}/approve")
async def approve_cash_advance(ca_id: str, payload: ApprovalDecision, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_advance", "approve")
    ctx = await entity_ctx(request)
    return await svc.approve_cash_advance(ca_id, payload.note, ctx, actor)


@router.post("/cash-advances/{ca_id}/reject")
async def reject_cash_advance(ca_id: str, payload: ApprovalDecision, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_advance", "reject")
    ctx = await entity_ctx(request)
    return await svc.reject_cash_advance(ca_id, payload.note, ctx, actor)


@router.post("/cash-advances/{ca_id}/disburse")
async def disburse_cash_advance(ca_id: str, payload: DisburseInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_advance", "disburse")
    ctx = await entity_ctx(request)
    return await svc.disburse_cash_advance(ca_id, payload, ctx, actor)


# ─── Settlement (Pertanggungjawaban) ────────────────────────────────
@router.get("/cash-advance-settlements")
async def list_settlements(request: Request, entity_id: str = Query(None),
                           cash_advance_id: str = Query(None),
                           status: str = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "cash_settlement", "view")
    ctx = await entity_ctx(request)
    return await svc.list_settlements(ctx, entity_id=entity_id,
                                      cash_advance_id=cash_advance_id, status=status)


@router.post("/cash-advance-settlements")
async def create_settlement(payload: SettlementCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_settlement", "create")
    ctx = await entity_ctx(request)
    return await svc.create_settlement(payload, ctx, actor)


@router.get("/cash-advance-settlements/{stl_id}")
async def get_settlement(stl_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "cash_settlement", "view")
    ctx = await entity_ctx(request)
    return await svc.get_settlement(stl_id, ctx)


@router.patch("/cash-advance-settlements/{stl_id}")
async def update_settlement(stl_id: str, payload: SettlementUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_settlement", "update")
    ctx = await entity_ctx(request)
    return await svc.update_settlement(stl_id, payload, ctx, actor)


@router.post("/cash-advance-settlements/{stl_id}/submit")
async def submit_settlement(stl_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_settlement", "submit")
    ctx = await entity_ctx(request)
    return await svc.submit_settlement(stl_id, ctx, actor)


@router.post("/cash-advance-settlements/{stl_id}/approve")
async def approve_settlement(stl_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_settlement", "approve")
    ctx = await entity_ctx(request)
    return await svc.approve_settlement(stl_id, ctx, actor)


@router.post("/cash-advance-settlements/{stl_id}/reject")
async def reject_settlement(stl_id: str, payload: ApprovalDecision, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "cash_settlement", "reject")
    ctx = await entity_ctx(request)
    return await svc.reject_settlement(stl_id, payload.note, ctx, actor)
