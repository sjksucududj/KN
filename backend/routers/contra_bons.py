"""FASE G-7 — Router **KONTRABON** (siklus tukar faktur supplier).

Koleksi kanonik: `contra_bons` (prefix `cbn_`, nomor `<ENT>/CB-#####`) — **SCOPED**.
Router sengaja TIPIS: seluruh aturan uang ada di `services/contra_bon_service.py`
supaya bisa diuji tanpa HTTP dan tidak tersebar di dua tempat.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from core_utils import safe_doc
from db import db
from dependencies import audit, require_permission
from entity_scope import entity_ctx, resolve_scope_ids
from schemas_contrabon import (
    ContraBonCreate, ContraBonDecisionIn, ContraBonDeductionIn, ContraBonNoteIn,
    ContraBonPayIn, ContraBonScheduleIn, InvoiceExchangeIn,
)
from services import contra_bon_reminder as reminder
from services import contra_bon_service as cbs

router = APIRouter(prefix="/api")


async def _scope(request: Request, entity_id: Optional[str] = None) -> List[str]:
    ctx = await entity_ctx(request)
    return resolve_scope_ids(ctx, entity_id)


def _fail(exc: cbs.ContraBonError) -> HTTPException:
    """Kesalahan bisnis → 400 dengan kalimat yang SUDAH siap dibaca pengguna."""
    return HTTPException(status_code=400, detail=str(exc))


# ── Meta & bantuan layar (STATIS sebelum route /{id}) ─────────────────────────

@router.get("/contra-bons/meta")
async def contra_bon_meta(request: Request, entity_id: str = "") -> Dict[str, Any]:
    """Kamus siklus/potongan/aksi + label alasan + kebijakan berlaku (satu panggilan)."""
    await require_permission(request, "contra_bon", "view")
    return {
        "statuses": [{"value": s, "label": cbs.STATUS_LABEL[s]} for s in cbs.STATUSES],
        "deduction_kinds": list(cbs.DEDUCTION_KINDS),
        "exception_actions": list(cbs.EXCEPTION_ACTIONS),
        "reasons": await cbs.reasons(),
        "policy": await cbs.policy(entity_id),
        "schedule_modes": [{"value": m, "label": reminder.MODE_LABEL[m]} for m in reminder.MODES],
        "weekdays": [{"value": i, "label": reminder.WEEKDAY_LABEL[i]} for i in range(7)],
    }


@router.get("/contra-bons/summary")
async def contra_bon_summary(request: Request, entity_id: str = "") -> Dict[str, Any]:
    await require_permission(request, "contra_bon", "view")
    return await cbs.summary(await _scope(request, entity_id), entity_id)


@router.get("/contra-bons/status-counts")
async def contra_bon_status_counts(request: Request, entity_id: str = "") -> Dict[str, int]:
    await require_permission(request, "contra_bon", "view")
    return await cbs.status_counts(await _scope(request, entity_id), entity_id)


@router.get("/contra-bons/prepare")
async def contra_bon_prepare(request: Request, supplier_id: str, entity_id: str = "",
                             exclude_cb_id: str = "") -> Dict[str, Any]:
    """Rakit kandidat: tagihan siap dikontrabon + potongan tersedia + GR belum ditagih."""
    await require_permission(request, "contra_bon", "view")
    scope = await _scope(request, entity_id)
    ent = entity_id or (scope[0] if scope else "")
    try:
        return await cbs.prepare(supplier_id, ent, exclude_cb_id)
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc


@router.get("/contra-bons/unbilled-receipts")
async def contra_bon_unbilled(request: Request, entity_id: str = "",
                              supplier_id: str = "") -> Dict[str, Any]:
    """US3 — penerimaan barang yang belum ditagih supplier (jangan sampai terlewat)."""
    await require_permission(request, "contra_bon", "view")
    return await cbs.unbilled_receipts(await _scope(request, entity_id),
                                       supplier_id=supplier_id, entity_id=entity_id)


@router.get("/contra-bons/exchange-schedules")
async def contra_bon_schedules(request: Request, entity_id: str = "") -> Dict[str, Any]:
    """US1 — jadwal tukar faktur seluruh supplier + kesiapan siklus berikutnya."""
    await require_permission(request, "contra_bon", "view")
    return await reminder.schedules(await _scope(request, entity_id), entity_id)


@router.put("/suppliers/{supplier_id}/invoice-exchange")
async def set_invoice_exchange(supplier_id: str, payload: InvoiceExchangeIn,
                               request: Request) -> Dict[str, Any]:
    """Atur jadwal tukar faktur satu supplier (mis. setiap Selasa / tanggal 25)."""
    actor = await require_permission(request, "contra_bon", "update")
    try:
        res = await reminder.set_schedule(supplier_id, payload.model_dump(), actor)
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "supplier_invoice_exchange_set", "supplier", supplier_id,
                res["invoice_exchange"])
    return res


@router.get("/contra-bons/bank-line-candidates/{line_id}")
async def contra_bon_bank_candidates(line_id: str, request: Request,
                                     entity_id: str = "") -> Dict[str, Any]:
    """US8 — kontrabon yang pantas dilunasi oleh satu baris mutasi bank keluar."""
    await require_permission(request, "contra_bon", "view")
    try:
        return await cbs.bank_line_candidates(line_id, await _scope(request, entity_id))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc


@router.post("/contra-bons/run-reminder")
async def contra_bon_run_reminder(request: Request) -> Dict[str, Any]:
    """Jalankan pengingat siklus SEKARANG (tanpa menunggu jadwal) — untuk uji & operasional."""
    actor = await require_permission(request, "contra_bon", "update")
    res = await reminder.job_contra_bon_reminder()
    await audit(actor["name"], "contra_bon_reminder_run", "contra_bon", "", res)
    return res


# ── Daftar & detail ───────────────────────────────────────────────────────────

@router.get("/contra-bons")
async def list_contra_bons(request: Request, entity_id: str = "", status: str = "",
                           supplier_id: str = "", q: str = "") -> List[Dict[str, Any]]:
    await require_permission(request, "contra_bon", "view")
    return await cbs.list_contra_bons(await _scope(request, entity_id), entity_id,
                                       status=status, supplier_id=supplier_id, q=q)


@router.get("/contra-bons/{cb_id}")
async def get_contra_bon(cb_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "contra_bon", "view")
    try:
        cb = await cbs._get(cb_id, await _scope(request))
    except cbs.ContraBonError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await cbs.decorate(cb)


@router.get("/contra-bons/{cb_id}/receipt")
async def contra_bon_receipt(cb_id: str, request: Request) -> Dict[str, Any]:
    """US9 — data **Tanda Terima Kontrabon** (dipakai layar & mesin PDF)."""
    await require_permission(request, "contra_bon", "view")
    try:
        cb = await cbs._get(cb_id, await _scope(request))
    except cbs.ContraBonError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    dec = await cbs.decorate(cb)
    receipts: List[Dict[str, Any]] = []
    for b in dec.get("bills", []):
        if not b.get("po_id"):
            continue
        async for t in db.wms_tasks.find({"po_id": b["po_id"], "flow_type": "inbound"},
                                          {"_id": 0, "id": 1, "status": 1, "completed_at": 1}):
            receipts.append({"bill_number": b.get("bill_number", ""),
                             "po_number": b.get("po_number", ""),
                             "grn_task_id": t.get("id", ""), "status": t.get("status", ""),
                             "completed_at": t.get("completed_at", "")})
    return {"contra_bon": dec, "goods_receipts": receipts}


# ── Siklus ────────────────────────────────────────────────────────────────────

@router.post("/contra-bons")
async def create_contra_bon(payload: ContraBonCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "create")
    try:
        cb = await cbs.create(payload.model_dump(), actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_created", "contra_bon", cb["id"], {
        "number": cb.get("number"), "supplier": cb.get("supplier_name"),
        "bills": len(cb.get("bills") or []),
        "net_payable": (cb.get("totals") or {}).get("net_payable")})
    return cb


@router.post("/contra-bons/{cb_id}/deductions")
async def add_deduction(cb_id: str, payload: ContraBonDeductionIn,
                        request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "update")
    try:
        cb = await cbs.add_deduction(cb_id, payload.model_dump(), actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_deduction_added", "contra_bon", cb_id, {
        "kind": payload.kind, "amount": float(payload.amount or 0), "ref_id": payload.ref_id})
    return cb


@router.delete("/contra-bons/{cb_id}/deductions/{ded_id}")
async def remove_deduction(cb_id: str, ded_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "update")
    try:
        cb = await cbs.remove_deduction(cb_id, ded_id, actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_deduction_removed", "contra_bon", cb_id,
                {"deduction_id": ded_id})
    return cb


@router.post("/contra-bons/{cb_id}/decide")
async def decide_exception(cb_id: str, payload: ContraBonDecisionIn,
                           request: Request) -> Dict[str, Any]:
    """Keputusan BERLABEL atas satu selisih 3-way (INV-CB-03)."""
    actor = await require_permission(request, "contra_bon", "update")
    try:
        cb = await cbs.decide(cb_id, payload.model_dump(), actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_variance_decided", "contra_bon", cb_id, {
        "exception_key": payload.exception_key, "action": payload.action,
        "reason_code": payload.reason_code})
    return cb


@router.post("/contra-bons/{cb_id}/submit")
async def submit_contra_bon(cb_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "update")
    try:
        cb = await cbs.submit(cb_id, actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_submitted", "contra_bon", cb_id,
                {"number": cb.get("number")})
    return cb


@router.post("/contra-bons/{cb_id}/verify")
async def verify_contra_bon(cb_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "verify")
    try:
        cb = await cbs.verify(cb_id, actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_verified", "contra_bon", cb_id, {
        "number": cb.get("number"), "match": (cb.get("match_summary") or {}).get("status")})
    return cb


@router.post("/contra-bons/{cb_id}/approve")
async def approve_contra_bon(cb_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "approve")
    try:
        cb = await cbs.approve(cb_id, actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await audit(actor["name"], "contra_bon_approved", "contra_bon", cb_id, {
        "number": cb.get("number"),
        "net_payable": (cb.get("totals") or {}).get("net_payable")})
    return cb


@router.post("/contra-bons/{cb_id}/schedule")
async def schedule_contra_bon(cb_id: str, payload: ContraBonScheduleIn,
                              request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "update")
    try:
        cb = await cbs.schedule(cb_id, payload.model_dump(), actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_scheduled", "contra_bon", cb_id,
                {"planned": payload.planned_payment_date})
    return cb


@router.post("/contra-bons/{cb_id}/pay")
async def pay_contra_bon(cb_id: str, payload: ContraBonPayIn,
                         request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "pay")
    try:
        cb = await cbs.pay(cb_id, payload.model_dump(), actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_paid", "contra_bon", cb_id, {
        "number": cb.get("number"), "amount": float(payload.amount or 0),
        "status": cb.get("status")})
    return cb


@router.post("/contra-bons/{cb_id}/pay-from-bank-line/{line_id}")
async def pay_from_bank_line(cb_id: str, line_id: str, request: Request,
                             payload: Optional[ContraBonNoteIn] = None) -> Dict[str, Any]:
    """US8 — bayar kontrabon dari baris mutasi bank keluar lalu tautkan barisnya (G-8)."""
    actor = await require_permission(request, "contra_bon", "pay")
    try:
        cb = await cbs.pay_from_bank_line(cb_id, line_id, actor, await _scope(request),
                                           payload.model_dump() if payload else None)
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    except ValueError as exc:                     # dari bank_recon_service
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(actor["name"], "contra_bon_paid_from_bank_line", "contra_bon", cb_id,
                {"line_id": line_id, "number": cb.get("number")})
    return cb


@router.post("/contra-bons/{cb_id}/dispute")
async def dispute_contra_bon(cb_id: str, payload: ContraBonNoteIn,
                             request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "update")
    try:
        cb = await cbs.dispute(cb_id, payload.model_dump(), actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_disputed", "contra_bon", cb_id,
                {"reason_code": payload.reason_code})
    return cb


@router.post("/contra-bons/{cb_id}/cancel")
async def cancel_contra_bon(cb_id: str, payload: ContraBonNoteIn,
                            request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "contra_bon", "update")
    try:
        cb = await cbs.cancel(cb_id, payload.model_dump(), actor, await _scope(request))
    except cbs.ContraBonError as exc:
        raise _fail(exc) from exc
    await audit(actor["name"], "contra_bon_cancelled", "contra_bon", cb_id,
                {"note": payload.note})
    return safe_doc(cb)
