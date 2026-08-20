"""FASE E-7 (E7f) — router **PINJAMAN UANG ANTAR-PT** (`/api/interco/loans`).

Izin memakai modul `interco` yang sudah ada (sisi UANG antar-PT = admin/manajer):
  * `interco.view`     — melihat daftar & detail
  * `interco.create`   — membuat draf pinjaman
  * `interco.approve`  — mencairkan (ambang `antar_entitas.approval_threshold_rupiah`)
  * `interco.settle`   — mencatat angsuran
  * `interco.cancel`   — membatalkan draf
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from dependencies import audit, require_permission
from entity_scope import assert_entity_access, entity_ctx, resolve_list_scope
from schemas_interco_loan import (
    IntercoLoanCreate, IntercoLoanDecision, IntercoLoanRepay,
)
from services import interco_loan_service as svc
from services import interco_money_service as money

router = APIRouter(prefix="/api")


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/interco/loans/meta")
async def loans_meta(request: Request) -> Dict[str, Any]:
    await require_permission(request, "interco", "view")
    return {"statuses": [{"id": k, "label": v} for k, v in svc.STATUS_LABEL.items()],
            "open_statuses": list(svc.OPEN_STATUSES)}


@router.get("/interco/loans")
async def list_loans(request: Request, status: Optional[str] = Query(None),
                     entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "interco", "view")
    ctx = await entity_ctx(request)
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    q = resolve_list_scope(svc.COLL, q, ctx, entity_id)
    rows = await svc.list_loans(q)
    return {"items": rows, "total": len(rows), "summary": await svc.summary(q)}


@router.post("/interco/loans")
async def create_loan(payload: IntercoLoanCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "interco", "create")
    ctx = await entity_ctx(request)
    if payload.lender_entity_id not in ctx.allowed_entity_ids and \
            payload.borrower_entity_id not in ctx.allowed_entity_ids:
        raise HTTPException(
            status_code=403,
            detail=("Anda tidak berwenang di kedua badan usaha itu — pinjaman antar-PT "
                    "hanya boleh dibuat oleh orang yang ditugaskan di salah satu sisinya."))
    try:
        res = await svc.create(payload.model_dump(), actor)
    except (svc.LoanError, money.IntercoMoneyError) as exc:
        raise _fail(exc) from exc
    await audit(actor.get("name", ""), "interco_loan_created", "interco_loan",
                res["pair_id"], {"principal": payload.principal,
                                 "lender": payload.lender_entity_id,
                                 "borrower": payload.borrower_entity_id})
    return res


@router.get("/interco/loans/{loan_id}")
async def get_loan(loan_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "interco", "view")
    ctx = await entity_ctx(request)
    res = await svc.get_one(loan_id)
    if not res:
        raise HTTPException(status_code=404, detail="Pinjaman antar-PT tidak ditemukan.")
    for side in ("lender", "borrower"):
        if res[side]["id"] == loan_id:
            assert_entity_access(res[side], svc.COLL, ctx)
    return res


@router.post("/interco/loans/{loan_id}/disburse")
async def disburse_loan(loan_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "interco", "approve")
    try:
        res = await svc.disburse(loan_id, actor)
    except (svc.LoanError, money.IntercoMoneyError) as exc:
        raise _fail(exc) from exc
    await audit(actor.get("name", ""), "interco_loan_disbursed", "interco_loan",
                res["pair_id"], {"amount": res["lender"]["principal"]})
    return res


@router.post("/interco/loans/{loan_id}/repay")
async def repay_loan(loan_id: str, payload: IntercoLoanRepay, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "interco", "settle")
    try:
        res = await svc.repay(loan_id, actor, float(payload.amount or 0), payload.note)
    except (svc.LoanError, money.IntercoMoneyError) as exc:
        raise _fail(exc) from exc
    await audit(actor.get("name", ""), "interco_loan_repaid", "interco_loan",
                res["pair_id"], {"amount": float(payload.amount or 0),
                                 "outstanding": res["lender"]["outstanding"]})
    return res


@router.post("/interco/loans/{loan_id}/cancel")
async def cancel_loan(loan_id: str, request: Request,
                      payload: IntercoLoanDecision = IntercoLoanDecision()) -> Dict[str, Any]:
    actor = await require_permission(request, "interco", "cancel")
    try:
        res = await svc.cancel(loan_id, actor, payload.reason)
    except (svc.LoanError, money.IntercoMoneyError) as exc:
        raise _fail(exc) from exc
    await audit(actor.get("name", ""), "interco_loan_cancelled", "interco_loan",
                res["pair_id"], {"reason": payload.reason})
    return res


@router.get("/interco/non-trade/{from_entity_id}/{to_entity_id}")
async def non_trade_balance(from_entity_id: str, to_entity_id: str,
                            request: Request) -> Dict[str, Any]:
    """Saldo NON-DAGANG satu arah pasangan PT (pinjaman + pindah aset tetap).

    Dipisah dari saldo jual-beli karena cara melunasinya berbeda — menggabungkannya
    membuat orang menekan tombol netting untuk pinjaman (yang tidak akan berhasil).
    """
    await require_permission(request, "interco_finance", "view")
    return await money.non_trade_outstanding(from_entity_id, to_entity_id)
