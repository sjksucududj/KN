"""FASE G-2 — Router **Rencana Pembayaran & Denda**.

Satu pintu untuk: menyusun jadwal pembayaran per dokumen (DP/cicilan/milestone/bebas),
melihat antrean denda, dan memutuskan denda (terbitkan / bebaskan / ubah nominal / bayar).

RBAC: `payment_plan` (view/create/update/void) dan `penalty` (view/issue/waive/adjust/pay).
Seluruh aksi keuangan tercatat di audit log.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from dependencies import audit, require_permission
from entity_scope import assert_entity_access, entity_ctx, scope_value
from services import payment_plan_service as plans
from services import penalty_service as penalties

router = APIRouter(prefix="/api")


class PlanPreview(BaseModel):
    doc_type: str = "sales_order"
    doc_id: str
    mode: str = "dp_installment"
    dp_percent: Optional[float] = None
    installments: Optional[int] = None
    interval: Optional[str] = None
    net_days: Optional[int] = 30
    milestones: Optional[List[Dict[str, Any]]] = None


class PlanCreate(PlanPreview):
    lines: Optional[List[Dict[str, Any]]] = None
    penalty: Optional[Dict[str, Any]] = None
    note: Optional[str] = ""


class PlanUpdate(BaseModel):
    mode: Optional[str] = None
    lines: Optional[List[Dict[str, Any]]] = None
    penalty: Optional[Dict[str, Any]] = None
    note: Optional[str] = None


class VoidBody(BaseModel):
    reason: str = Field(..., min_length=3)


class WaiveBody(BaseModel):
    reason_code: str
    note: Optional[str] = ""


class AdjustBody(WaiveBody):
    amount: float


class PayBody(BaseModel):
    amount: float
    method: Optional[str] = "transfer"


def _err(exc: Exception, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


# ── Rencana pembayaran ────────────────────────────────────────────────
@router.get("/payment-plans/meta")
async def plan_meta(request: Request, entity_id: str = Query(""),
                    customer_id: str = Query("")) -> Dict[str, Any]:
    """Pilihan mode, label, kebijakan berlaku, dan label alasan denda (untuk UI)."""
    await require_permission(request, "payment_plan", "view")
    from db import db
    # FASE G-2 — label alasan denda memakai taksonomi FASE G-1 (bisa ditambah admin).
    from services.amendment_service import ensure_reasons
    await ensure_reasons()
    reasons = await db.amendment_reasons.find(
        {"$or": [{"applies_to": penalties.REASON_DOC_TYPE}, {"applies_to": []}],
         "status": {"$ne": "inactive"}}, {"_id": 0}).sort("label", 1).to_list(100)
    return {
        "modes": [{"value": m, "label": plans.MODE_LABEL[m]} for m in plans.MODES],
        "kinds": [{"value": k, "label": plans.KIND_LABEL[k]} for k in plans.KINDS],
        "due_rules": [
            {"value": "net_days", "label": "N hari dari tanggal dokumen"},
            {"value": "monthly", "label": "Bulanan"},
            {"value": "weekly", "label": "Mingguan"},
            {"value": "fixed_date", "label": "Tanggal tetap"},
        ],
        "plan_policy": await plans.plan_policy(entity_id, customer_id),
        "penalty_policy": await penalties.penalty_policy(entity_id, customer_id),
        "penalty_statuses": [{"value": s, "label": penalties.STATUS_LABEL[s]}
                             for s in penalties.STATUSES],
        "reasons": reasons,
    }


@router.post("/payment-plans/preview")
async def plan_preview(body: PlanPreview, request: Request) -> Dict[str, Any]:
    """Pratinjau jadwal dari template TANPA menyimpan (dipakai builder di UI)."""
    await require_permission(request, "payment_plan", "view")
    try:
        return await plans.preview(body.doc_type, body.doc_id, body.mode, body.model_dump())
    except plans.PlanError as exc:
        raise _err(exc) from exc


@router.get("/payment-plans")
async def list_plans(request: Request, entity_id: str = Query(""), status: str = Query(""),
                     q: str = Query(""), limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    """FASE E-0 (L2) — dulu tanpa cakupan entitas: sales CV Kanda Suka melihat 2/2
    rencana pembayaran milik PT Kain Suka Cita."""
    await require_permission(request, "payment_plan", "view")
    ctx = await entity_ctx(request)
    rows = await plans.list_plans(entity_id=scope_value(ctx, entity_id or None),
                                  status=status, q=q, limit=limit)
    return {"count": len(rows), "items": rows, "entity_id": ctx.active_entity_id}


@router.get("/payment-plans/by-doc/{doc_type}/{doc_id}")
async def plan_by_doc(doc_type: str, doc_id: str, request: Request) -> Dict[str, Any]:
    """Rencana aktif + ringkasan denda untuk satu dokumen (panel detail SO)."""
    await require_permission(request, "payment_plan", "view")
    ctx = await entity_ctx(request)
    plan = await plans.get_active(doc_type, doc_id)
    if plan:
        assert_entity_access(plan, "payment_plans", ctx)   # FASE E-0 (L2)
    if plan:
        plan = await plans.recompute_paid(plan["id"])
    rows = await penalties.list_penalties(doc_id=doc_id)
    return {"plan": plan, "penalties": rows,
            "next_due": plans.next_due(plan) if plan else None,
            "overdue": plans.overdue_lines(plan) if plan else []}


@router.post("/payment-plans")
async def create_plan(body: PlanCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "payment_plan", "create")
    try:
        plan = await plans.create_plan(body.doc_type, body.doc_id, body.model_dump(), actor)
    except plans.PlanError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "payment_plan_created", "payment_plans",
                plan["id"], {"number": plan["number"], "mode": plan["mode"],
                             "lines": len(plan.get("lines") or [])})
    return plan


@router.patch("/payment-plans/{plan_id}")
async def update_plan(plan_id: str, body: PlanUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "payment_plan", "update")
    try:
        plan = await plans.update_plan(plan_id, body.model_dump(exclude_none=True), actor)
    except plans.PlanError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "payment_plan_updated", "payment_plans", plan_id,
                {"lines": len(plan.get("lines") or [])})
    return plan


@router.post("/payment-plans/{plan_id}/void")
async def void_plan(plan_id: str, body: VoidBody, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "payment_plan", "void")
    try:
        plan = await plans.void_plan(plan_id, body.reason, actor)
    except plans.PlanError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "payment_plan_voided", "payment_plans", plan_id,
                {"reason": body.reason})
    return plan


@router.post("/payment-plans/{plan_id}/accrue")
async def accrue_now(plan_id: str, request: Request,
                     today: str = Query("")) -> Dict[str, Any]:
    """Hitung denda SEKARANG untuk rencana ini (tanpa menunggu job harian)."""
    actor = await require_permission(request, "penalty", "issue")
    plan = await plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Rencana pembayaran tidak ditemukan")
    assert_entity_access(plan, "payment_plans", await entity_ctx(request))
    rows = await penalties.accrue_plan(plan, today=today or None,
                                       actor_name=actor.get("name", ""))
    return {"plan_id": plan_id, "count": len(rows), "penalties": rows}


# ── Denda ─────────────────────────────────────────────────────────────
@router.get("/penalties")
async def list_penalties(request: Request, entity_id: str = Query(""), status: str = Query(""),
                        doc_id: str = Query(""), q: str = Query(""),
                        limit: int = Query(200, ge=1, le=500)) -> Dict[str, Any]:
    """FASE E-0 (L4) — dulu tanpa cakupan entitas: nota denda KSC terlihat oleh sales Kanda."""
    await require_permission(request, "penalty", "view")
    ctx = await entity_ctx(request)
    scope = scope_value(ctx, entity_id or None)
    rows = await penalties.list_penalties(entity_id=scope, status=status,
                                          doc_id=doc_id, q=q, limit=limit)
    return {"count": len(rows), "items": rows, "entity_id": ctx.active_entity_id,
            "stats": await penalties.stats(scope)}


@router.get("/penalties/{penalty_id}")
async def get_penalty(penalty_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "penalty", "view")
    ctx = await entity_ctx(request)
    row = await penalties.get(penalty_id)
    if not row:
        raise HTTPException(status_code=404, detail="Nota denda tidak ditemukan")
    assert_entity_access(row, "penalties", ctx)   # FASE E-0 (L4)
    return row


@router.post("/penalties/{penalty_id}/issue")
async def issue_penalty(penalty_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "penalty", "issue")
    try:
        row = await penalties.issue(penalty_id, actor)
    except penalties.PenaltyError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "penalty_issued", "penalties", penalty_id,
                {"number": row["number"], "amount": row["amount"], "je": row.get("je_number")})
    return row


@router.post("/penalties/{penalty_id}/waive")
async def waive_penalty(penalty_id: str, body: WaiveBody, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "penalty", "waive")
    try:
        row = await penalties.waive(penalty_id, body.reason_code, body.note or "", actor)
    except penalties.PenaltyError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "penalty_waived", "penalties", penalty_id,
                {"number": row["number"], "reason": row.get("reason_label")},
                reason=body.note or "")
    return row


@router.post("/penalties/{penalty_id}/adjust")
async def adjust_penalty(penalty_id: str, body: AdjustBody, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "penalty", "adjust")
    try:
        row = await penalties.adjust(penalty_id, body.amount, body.reason_code,
                                     body.note or "", actor)
    except penalties.PenaltyError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "penalty_adjusted", "penalties", penalty_id,
                {"number": row["number"], "amount": row["amount"],
                 "reason": row.get("reason_label")}, reason=body.note or "")
    return row


@router.post("/penalties/{penalty_id}/pay")
async def pay_penalty(penalty_id: str, body: PayBody, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "penalty", "pay")
    try:
        row = await penalties.pay(penalty_id, body.amount, body.method or "transfer", actor)
    except penalties.PenaltyError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "penalty_paid", "penalties", penalty_id,
                {"number": row["number"], "amount": body.amount})
    return row
