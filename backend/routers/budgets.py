"""FINANCE — Anggaran (Budget) vs Komitmen vs Realisasi + Budget Control (R6.3).

Akses: permission resource **"budget"** (admin: penuh; manager: view/create/update).
Koleksi `budgets` (+ `fin_budget_rules`) ter-scope per entitas. Respons OBJEK telanjang (kontrak KN3).

Endpoint:
- GET    /api/finance/budgets                  → daftar anggaran (filter year, dimension)
- POST   /api/finance/budgets                  → buat anggaran (dimension account|category)
- PATCH  /api/finance/budgets/{budget_id}      → ubah anggaran
- DELETE /api/finance/budgets/{budget_id}      → hapus anggaran
- GET    /api/finance/budget-vs-actual         → anggaran vs komitmen vs realisasi + alert + rules
- GET    /api/finance/budget-keys              → pilihan kunci (akun COA / kategori beban)
- GET    /api/finance/budget-rules             → kebijakan over-budget per entitas
- PUT    /api/finance/budget-rules             → set kebijakan (admin)
- POST   /api/finance/budget-check             → pratinjau sisa anggaran utk nominal tertentu
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope
from schemas import BudgetCreate, BudgetUpdate
from services import budget_service as budget
from services import cash_advance_service as ca_svc
from services import gl_service

router = APIRouter(prefix="/api")


class BudgetRulesIn(BaseModel):
    entity_id: Optional[str] = None
    mode: Optional[str] = None                     # off | warn | block
    warn_threshold_pct: Optional[float] = Field(None, ge=0, le=100)
    unbudgeted_action: Optional[str] = None        # allow | warn | block
    enforce_po_create: Optional[bool] = None
    enforce_po_approve: Optional[bool] = None


class BudgetCheckIn(BaseModel):
    entity_id: Optional[str] = None
    dimension: str = "account"
    key: str
    amount: float = 0
    date: Optional[str] = ""


async def _scope(request: Request, entity_id: Optional[str]) -> Dict[str, Any]:
    ctx = await entity_ctx(request)
    return resolve_list_scope("budgets", {}, ctx, entity_id)


async def _entity_or_active(request: Request, entity_id: Optional[str]) -> str:
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id or "ent_ksc"
    if eid == "all":
        eid = ctx.active_entity_id or "ent_ksc"
    if eid not in (ctx.allowed_entity_ids or [eid]):
        raise HTTPException(status_code=403, detail="Entitas di luar akses Anda.")
    return eid


@router.get("/finance/budgets")
async def list_budgets(
    request: Request,
    year: Optional[int] = Query(None),
    dimension: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    await require_permission(request, "budget", "view")
    scope = await _scope(request, entity_id)
    return await budget.list_budgets(scope, year, dimension)


@router.post("/finance/budgets")
async def create_budget(request: Request, payload: BudgetCreate) -> Dict[str, Any]:
    actor = await require_permission(request, "budget", "create")
    entity_id = await _entity_or_active(request, payload.entity_id)
    try:
        doc = await budget.create_budget(payload.model_dump(), entity_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "budget_created", "budget", doc["id"],
                {"dimension": doc["dimension"], "key": doc["key"], "amount": doc["amount"]})
    return doc


@router.patch("/finance/budgets/{budget_id}")
async def update_budget(request: Request, budget_id: str, patch: BudgetUpdate) -> Dict[str, Any]:
    actor = await require_permission(request, "budget", "update")
    scope = await _scope(request, None)
    try:
        res = await budget.update_budget(budget_id, patch.model_dump(exclude_none=True), scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not res:
        raise HTTPException(status_code=404, detail="Anggaran tidak ditemukan.")
    await audit(actor.get("name", ""), "budget_updated", "budget", budget_id, {})
    return res


@router.delete("/finance/budgets/{budget_id}")
async def delete_budget(request: Request, budget_id: str) -> Dict[str, Any]:
    actor = await require_permission(request, "budget", "delete")
    scope = await _scope(request, None)
    ok = await budget.delete_budget(budget_id, scope)
    if not ok:
        raise HTTPException(status_code=404, detail="Anggaran tidak ditemukan.")
    await audit(actor.get("name", ""), "budget_deleted", "budget", budget_id, {})
    return {"ok": True, "deleted": budget_id}


@router.get("/finance/budget-vs-actual")
async def budget_vs_actual(
    request: Request,
    year: int = Query(...),
    entity_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    await require_permission(request, "budget", "view")
    ctx = await entity_ctx(request)
    # Realisasi & komitmen diturunkan dari jurnal/PO/LPJ → scope dgn koleksi ber-entity_id.
    scope = resolve_list_scope("journal_entries", {}, ctx, entity_id)
    rules_entity = entity_id if (entity_id and entity_id != "all") else (ctx.active_entity_id or "")
    return await budget.budget_vs_actual(scope, year, entity_id_for_rules=rules_entity)


@router.get("/finance/budget-keys")
async def budget_keys(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Pilihan kunci anggaran: akun COA (income/expense/inventory) + kategori beban."""
    await require_permission(request, "budget", "view")
    await gl_service.seed_default_coa()
    accts = await gl_service.list_accounts(active_only=True, entity_id=entity_id or None)
    accounts = [{"code": a["code"], "name": a["name"], "type": a.get("type", "")}
                for a in accts if a.get("is_postable")
                and (a.get("type") in ("income", "expense") or a.get("code", "").startswith("1-13"))]
    accounts.sort(key=lambda x: x["code"])
    cats = await ca_svc.list_expense_categories(active_only=True, entity_id=entity_id or "")
    categories = [{"code": c.get("code", ""), "label": c.get("label", ""),
                   "account_code": c.get("account_code", "")} for c in cats]
    return {"accounts": accounts, "categories": categories,
            "default_po_account": budget.DEFAULT_PO_BUDGET_ACCOUNT}


@router.get("/finance/budget-rules")
async def get_budget_rules(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "budget", "view")
    eid = await _entity_or_active(request, entity_id)
    return await budget.get_rules(eid)


@router.put("/finance/budget-rules")
async def set_budget_rules(request: Request, payload: BudgetRulesIn) -> Dict[str, Any]:
    actor = await require_permission(request, "budget", "configure")
    eid = await _entity_or_active(request, payload.entity_id)
    try:
        res = await budget.set_rules(eid, payload.model_dump(exclude_none=True), actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "budget_rules_updated", "budget", eid,
                {"mode": res.get("mode"), "unbudgeted_action": res.get("unbudgeted_action")})
    return res


@router.post("/finance/budget-check")
async def check_budget(request: Request, payload: BudgetCheckIn) -> Dict[str, Any]:
    """Pratinjau kontrol anggaran (dipakai UI PO sebelum submit)."""
    await require_permission(request, "budget", "view")
    eid = await _entity_or_active(request, payload.entity_id)
    try:
        return await budget.check_budget(eid, payload.dimension, payload.key,
                                         payload.amount, date=payload.date or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
