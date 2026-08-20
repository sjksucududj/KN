"""FASE G-3 — Router **Selisih Pembayaran** (lebih & kurang bayar).

Satu pintu untuk: menakar selisih sebelum kwitansi disimpan (dialog), memutuskan
selisih (sisa piutang / ubah jadwal / hapus sisa · deposit / alokasi ke pesanan lain /
kembalikan dana), melihat antrean selisih yang belum diputus, dan riwayat keputusan.

RBAC: `payment_variance` (view/decide). Keputusan sensitif (hapus sisa & pengembalian
dana) masih dijaga lagi oleh kebijakan `payment.variance_writeoff_*` di dalam layanan,
sehingga wewenangnya tidak bisa dilangkahi lewat endpoint.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from dependencies import audit, require_permission
from entity_scope import assert_entity_access, entity_ctx, scope_value
from services import payment_variance_service as pvs

router = APIRouter(prefix="/api")


class AssessBody(BaseModel):
    customer_id: str
    amount: float = 0.0
    use_deposit_amount: float = 0.0
    allocations: List[Dict[str, Any]] = Field(default_factory=list)
    as_of: Optional[str] = ""


class DecideBody(BaseModel):
    kind: str
    reason_code: str
    note: Optional[str] = ""
    amount: Optional[float] = None
    due_date: Optional[str] = ""
    order_id: Optional[str] = ""
    method: Optional[str] = ""
    allocations: List[Dict[str, Any]] = Field(default_factory=list)


class ReverseBody(BaseModel):
    reason: str = Field(..., min_length=3)


def _err(exc: Exception, code: int = 400) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/payment-variances/meta")
async def variance_meta(request: Request, entity_id: str = Query(""),
                        customer_id: str = Query("")) -> Dict[str, Any]:
    """Kebijakan berlaku + label alasan + kosakata pilihan (untuk dialog & layar)."""
    await require_permission(request, "payment_variance", "view")
    return {
        "policy": await pvs.variance_policy(entity_id, customer_id),
        "reasons": await pvs.reasons(),
        "kinds": [{"value": k, "label": v} for k, v in pvs.KIND_LABEL.items()],
        "under_kinds": list(pvs.AR_UNDER_KINDS),
        "over_kinds": list(pvs.AR_OVER_KINDS),
    }


@router.post("/payment-variances/assess")
async def assess(body: AssessBody, request: Request) -> Dict[str, Any]:
    """Takar selisih SEBELUM kwitansi disimpan — sumber angka dialog Selisih Pembayaran."""
    await require_permission(request, "payment_variance", "view")
    funds = round(float(body.amount or 0) + float(body.use_deposit_amount or 0), 2)
    try:
        return await pvs.pre_assess(body.customer_id, funds,
                                    body.allocations or None, as_of=body.as_of or "",
                                    entity_id=entity_of(request))
    except pvs.VarianceError as exc:
        raise _err(exc) from exc


def entity_of(request: Request) -> str:
    """Entitas aktif dari header (kalau ada) — dipakai membaca kebijakan berlapis."""
    eid = request.headers.get("X-Entity-Id", "") or ""
    return "" if eid == "all" else eid


@router.get("/payment-variances")
async def list_decisions(request: Request, entity_id: str = Query(""),
                         side: str = Query(""), kind: str = Query(""),
                         direction: str = Query(""), q: str = Query(""),
                         limit: int = Query(200, ge=1, le=500)) -> Dict[str, Any]:
    # FASE E-0 (L3) — dulu tanpa cakupan: sales Kanda melihat 4/4 keputusan selisih KSC.
    await require_permission(request, "payment_variance", "view")
    ctx = await entity_ctx(request)
    scope = scope_value(ctx, entity_id or None)
    rows = await pvs.list_decisions(entity_id=scope, side=side, kind=kind,
                                    direction=direction, q=q, limit=limit)
    return {"count": len(rows), "items": rows, "entity_id": ctx.active_entity_id,
            "pending": await pvs.pending(scope),
            "stats": await pvs.stats(scope)}


@router.get("/payment-variances/pending")
async def list_pending(request: Request, entity_id: str = Query("")) -> Dict[str, Any]:
    """Antrean kwitansi yang selisihnya belum diputus (tidak ada yang senyap)."""
    await require_permission(request, "payment_variance", "view")
    ctx = await entity_ctx(request)
    rows = await pvs.pending(scope_value(ctx, entity_id or None))
    return {"count": len(rows), "items": rows, "entity_id": ctx.active_entity_id}


@router.get("/payment-variances/receipt/{receipt_id}")
async def by_receipt(receipt_id: str, request: Request) -> Dict[str, Any]:
    """Catatan selisih + keputusan (kalau ada) untuk satu kwitansi."""
    await require_permission(request, "payment_variance", "view")
    from db import db
    from core_utils import safe_doc
    r = await db.ar_receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Kwitansi tidak ditemukan")
    assert_entity_access(r, "ar_receipts", await entity_ctx(request))   # FASE E-0 (L3/L17)
    r = safe_doc(r)
    v = r.get("variance") or {}
    decision = await pvs.get(v.get("decision_id")) if v.get("decision_id") else None
    assessment = None
    if v.get("needs_decision") and not v.get("decision_id"):
        # Takar ulang memakai angka kwitansi supaya dialog "putus belakangan" punya
        # pilihan & dampak yang sama dengan saat kwitansi dibuat.
        assessment = await pvs.pre_assess(
            r.get("customer_id", ""), round(float(v.get("funds") or 0), 2),
            [{"order_id": oid} for oid in (v.get("target_order_ids") or [])] or None,
            as_of=str(r.get("receipt_date") or "")[:10], entity_id=r.get("entity_id", ""))
        assessment["expected"] = round(float(v.get("expected") or 0), 2)
        assessment["delta"] = round(float(v.get("delta") or 0), 2)
        assessment["direction"] = v.get("direction") or assessment["direction"]
        assessment["options"] = pvs._options(  # noqa: SLF001 — pilihan dihitung dari arah tersimpan
            assessment["direction"], assessment["delta"], assessment["policy"],
            {"has_plan": any(t.get("plan_id") for t in assessment.get("targets") or []),
             "others_total": assessment.get("others_total", 0),
             "plan_total": assessment.get("capacity", 0),
             "suggested_due_date": assessment.get("suggested_due_date", "")})
    return {"receipt": r, "variance": v, "decision": decision, "assessment": assessment}


@router.post("/payment-variances/receipt/{receipt_id}/decide")
async def decide(receipt_id: str, body: DecideBody, request: Request) -> Dict[str, Any]:
    """Putuskan selisih satu kwitansi (bisa saat dibuat, bisa belakangan dari antrean)."""
    actor = await require_permission(request, "payment_variance", "decide")
    try:
        row = await pvs.decide_receipt(receipt_id, body.model_dump(), actor)
    except pvs.VarianceError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "payment_variance_decided",
                "payment_variance_decisions", row["id"],
                {"number": row["number"], "kind": row["kind"], "amount": row["amount"],
                 "receipt": row.get("receipt_number"), "reason": row.get("reason_label")},
                reason=body.note or "")
    return row


@router.get("/payment-variances/{decision_id}")
async def get_decision(decision_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "payment_variance", "view")
    row = await pvs.get(decision_id)
    if not row:
        raise HTTPException(status_code=404, detail="Keputusan selisih tidak ditemukan")
    assert_entity_access(row, "payment_variance_decisions", await entity_ctx(request))
    return row


@router.post("/payment-variances/{decision_id}/reverse")
async def reverse(decision_id: str, body: ReverseBody, request: Request) -> Dict[str, Any]:
    """Anulir keputusan (efek dibalik lewat jurnal pembalik; jejaknya tetap ada)."""
    actor = await require_permission(request, "payment_variance", "decide")
    try:
        row = await pvs.reverse_decision(decision_id, body.reason, actor)
    except pvs.VarianceError as exc:
        raise _err(exc) from exc
    await audit(actor.get("name", ""), "payment_variance_reversed",
                "payment_variance_decisions", decision_id,
                {"number": row.get("number"), "kind": row.get("kind")},
                reason=body.reason)
    return row
