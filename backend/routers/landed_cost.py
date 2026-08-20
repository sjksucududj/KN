"""Landed Cost router (Fase 5.4 — P0-5): voucher biaya tambahan → alokasi HPP roll.

Koleksi kanonik: `landed_cost_vouchers` (prefix `lcv_`, nomor `LCV-NNNNN`).
Lifecycle: draft → pending_approval → applied (→ paid) | cancelled.
Aplikasi ke HPP roll hanya saat APPROVE (manager+, SoD pembuat≠approver, idempotent).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, current_user, audit
from entity_scope import assert_entity_access, entity_ctx, resolve_list_scope
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID, timeline_entry, next_doc_number, rupiah
from schemas import LandedCostCreate, LandedCostPaymentCreate, LandedCostDecision
from services.config_service import role_satisfies
from services.landed_cost_service import (
    next_voucher_number, total_cost_of, voucher_financials, resolve_target_rolls,
    compute_allocation, apply_allocation_to_rolls, build_landed_cost_context,
    attach_allocation_names,
    ACTIVE_VOUCHER_STATUSES, PAYABLE_VOUCHER_STATUSES, COST_CATEGORIES,
)

router = APIRouter(prefix="/api")


def _hydrate(v: Dict[str, Any]) -> Dict[str, Any]:
    v["financials"] = voucher_financials(v)
    return v


# ── Landed cost context (pre-fill form) — STATIC sebelum route /{id} ───────────

@router.get("/purchase-orders/{po_id}/landed-cost-context")
async def po_landed_cost_context(po_id: str, request: Request) -> Dict[str, Any]:
    """Roll diterima dari PO + nilai dasar (untuk preview alokasi landed cost)."""
    await require_permission(request, "landed_cost", "view")
    po = safe_doc(await db.purchase_orders.find_one({"id": po_id}, {"_id": 0}))
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
    return await build_landed_cost_context(po)


# ── Payables summary (AP landed cost) — STATIC sebelum route /{id} ─────────────

@router.get("/landed-costs/payables/summary")
async def landed_cost_payables(request: Request, entity_id: str = None) -> Dict[str, Any]:
    """Ringkasan hutang biaya landed cost (voucher applied yang belum lunas)."""
    await require_permission(request, "landed_cost", "view")
    q: Dict[str, Any] = {"status": {"$in": list(PAYABLE_VOUCHER_STATUSES)}}
    if entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    vouchers = await db.landed_cost_vouchers.find(q, {"_id": 0}).to_list(2000)
    total_outstanding = 0.0
    total_applied = 0.0
    by_provider: Dict[str, Dict[str, Any]] = {}
    rows = []
    for v in vouchers:
        fin = voucher_financials(v)
        total_applied += fin["total_cost"]
        out = fin["outstanding"]
        if out > 0.01:
            total_outstanding += out
            pid = v.get("provider_name") or "—"
            prov = by_provider.setdefault(pid, {"provider_name": pid, "outstanding": 0.0, "voucher_count": 0})
            prov["outstanding"] = round(prov["outstanding"] + out, 2)
            prov["voucher_count"] += 1
        rows.append({
            "voucher_id": v["id"], "voucher_number": v.get("voucher_number"),
            "provider_name": v.get("provider_name", "—"), "po_numbers": v.get("po_numbers", []),
            "status": v.get("status"), "total_cost": fin["total_cost"],
            "amount_paid": fin["amount_paid"], "outstanding": out,
            "payment_status": fin["payment_status"], "basis": v.get("basis", "value"),
            "roll_count": v.get("target_roll_count", 0),
        })
    rows.sort(key=lambda r: -r["outstanding"])
    return {
        "total_outstanding": round(total_outstanding, 2),
        "total_applied": round(total_applied, 2),
        "by_provider": sorted(by_provider.values(), key=lambda s: -s["outstanding"]),
        "vouchers": rows,
    }


# ── List & detail ─────────────────────────────────────────────────────────────

@router.get("/landed-costs")
async def list_landed_costs(
    request: Request, entity_id: str = None, status: str = None, po_id: str = None
) -> List[Dict[str, Any]]:
    """Daftar Landed Cost Voucher (filter entitas/status/PO)."""
    await require_permission(request, "landed_cost", "view")
    # FASE E-0 (L17) — dulu tanpa lapisan scoping: `?entity_id=` kosong = semua PT.
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = resolve_list_scope("landed_costs", {}, ctx, entity_id)
    if status:
        query["status"] = status
    if po_id:
        query["po_ids"] = po_id
    vouchers = await db.landed_cost_vouchers.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)
    await attach_allocation_names(vouchers)      # INV-UI-02: nama produk, bukan `prod_*`
    return [_hydrate(v) for v in vouchers]


@router.get("/landed-costs/{voucher_id}")
async def get_landed_cost(voucher_id: str, request: Request) -> Dict[str, Any]:
    """Detail satu Landed Cost Voucher + ringkasan keuangan."""
    await require_permission(request, "landed_cost", "view")
    v = safe_doc(await db.landed_cost_vouchers.find_one({"id": voucher_id}, {"_id": 0}))
    if not v:
        raise HTTPException(status_code=404, detail="Landed Cost Voucher tidak ditemukan")
    assert_entity_access(v, "landed_costs", await entity_ctx(request))   # FASE E-0 (L17)
    await attach_allocation_names([v])           # INV-UI-02: nama produk, bukan `prod_*`
    return _hydrate(v)


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/landed-costs")
async def create_landed_cost(payload: LandedCostCreate, request: Request) -> Dict[str, Any]:
    """Buat voucher landed cost dari 1+ PO + baris biaya. Hitung preview alokasi.
    submit_now=True → langsung submit (pending_approval)."""
    actor = await require_permission(request, "landed_cost", "create")
    if not payload.po_ids:
        raise HTTPException(status_code=400, detail="Minimal 1 PO referensi.")
    cost_lines = [{"category": (c.category if c.category in COST_CATEGORIES else "other"),
                   "description": c.description, "amount": round(float(c.amount or 0), 2)}
                  for c in (payload.cost_lines or []) if float(c.amount or 0) > 0]
    if not cost_lines:
        raise HTTPException(status_code=400, detail="Minimal 1 baris biaya dengan nominal > 0.")
    total_cost = total_cost_of(cost_lines)

    pos = await db.purchase_orders.find({"id": {"$in": payload.po_ids}}, {"_id": 0}).to_list(100)
    if len(pos) != len(set(payload.po_ids)):
        raise HTTPException(status_code=404, detail="Sebagian PO tidak ditemukan.")
    entity_id = payload.entity_id or (pos[0].get("entity_id") if pos else "") or DEFAULT_ENTITY_ID
    po_numbers = [p.get("po_number", "") for p in pos]

    # Dedupe nomor invoice penyedia (cegah double voucher eksternal).
    inv_no = (payload.supplier_invoice_no or "").strip()
    if inv_no:
        dup = await db.landed_cost_vouchers.find_one(
            {"provider_name": payload.provider_name or "", "supplier_invoice_no": inv_no,
             "status": {"$in": list(ACTIVE_VOUCHER_STATUSES)}}, {"_id": 0, "voucher_number": 1})
        if dup:
            raise HTTPException(status_code=409,
                                detail=f"No. invoice '{inv_no}' sudah dipakai pada {dup.get('voucher_number')}.")

    basis = payload.basis if payload.basis in ("value", "quantity") else "value"
    rolls = await resolve_target_rolls(payload.po_ids, entity_id)
    if not rolls:
        raise HTTPException(status_code=400,
                            detail="PO terpilih belum memiliki roll diterima (GR). Selesaikan penerimaan dulu.")
    preview = compute_allocation(rolls, total_cost, basis)

    voucher_number = await next_voucher_number()
    actor_name = payload.created_by or actor.get("name", "Admin")
    timeline = [timeline_entry("created", "Landed Cost Voucher dibuat", actor_name,
                               f"{len(cost_lines)} biaya · {rupiah(total_cost)} · {preview['roll_count']} roll · basis {preview['basis']}")]
    voucher = {
        "id": new_id("lcv"),
        "voucher_number": voucher_number,
        "provider_name": payload.provider_name or "",
        "supplier_invoice_no": inv_no,
        "po_ids": list(payload.po_ids),
        "po_numbers": po_numbers,
        "entity_id": entity_id,
        "basis": basis,
        "effective_basis": preview["basis"],
        "cost_lines": cost_lines,
        "total_cost": total_cost,
        "voucher_date": payload.voucher_date or now_iso(),
        "due_date": payload.due_date or "",
        "target_roll_count": preview["roll_count"],
        "allocation_preview": preview["allocations"],
        "allocations": [],
        # lifecycle
        "status": "draft",
        "approval_required": True,
        "required_approval_role": "manager",
        "approval_status": "not_required",
        "approved_by": "", "approved_at": "", "applied_at": "",
        # AP
        "amount_paid": 0.0,
        "payment_status": "n/a",
        "payments": [],
        "notes": payload.notes,
        "timeline": timeline,
        "created_by": actor_name,
        "created_by_id": actor.get("id", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.landed_cost_vouchers.insert_one(voucher)
    # FASE G-4 — voucher biaya masuk menaut ke SEMUA PO yang dibebaninya.
    from services import doc_refs_service as _refs
    for _poid in voucher.get("po_ids") or []:
        await _refs.safe_link(("landed_cost", voucher["id"]), ("purchase_order", _poid),
                              "parent", note="biaya masuk untuk PO")
    await audit(actor["name"], "landed_cost_created", "landed_cost", voucher["id"], {
        "voucher_number": voucher_number, "po_numbers": po_numbers, "total_cost": total_cost})

    if payload.submit_now:
        return await _do_submit(voucher["id"], actor)
    return _hydrate(safe_doc(voucher))


# ── Submit / approve(apply) / reject ──────────────────────────────────────────

async def _do_submit(voucher_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    v = await db.landed_cost_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Landed Cost Voucher tidak ditemukan")
    if v.get("status") != "draft":
        raise HTTPException(status_code=409, detail=f"Voucher status '{v.get('status')}' tidak bisa di-submit.")
    updated = await db.landed_cost_vouchers.find_one_and_update(
        {"id": voucher_id},
        {"$set": {"status": "pending_approval", "approval_status": "pending", "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry(
             "submitted_for_approval", "Menunggu persetujuan manager", actor.get("name", ""),
             "landed cost akan mengubah HPP roll saat disetujui")}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "landed_cost_submitted", "landed_cost", voucher_id,
                {"voucher_number": v.get("voucher_number"), "to": "pending_approval"})
    return _hydrate(safe_doc(updated))


@router.post("/landed-costs/{voucher_id}/submit")
async def submit_landed_cost(voucher_id: str, request: Request) -> Dict[str, Any]:
    """Submit voucher → pending_approval (selalu butuh approval karena ubah HPP)."""
    actor = await require_permission(request, "landed_cost", "update")
    return await _do_submit(voucher_id, actor)


@router.post("/landed-costs/{voucher_id}/approve")
async def approve_landed_cost(voucher_id: str, request: Request) -> Dict[str, Any]:
    """Approve → ALOKASIKAN landed cost ke HPP roll (manager+, SoD, idempotent)."""
    actor = await current_user(request)
    v = await db.landed_cost_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Landed Cost Voucher tidak ditemukan")
    if v.get("status") != "pending_approval":
        raise HTTPException(status_code=409, detail=f"Voucher status '{v.get('status')}' tidak menunggu approval.")
    required = v.get("required_approval_role") or "manager"
    if not role_satisfies(actor.get("role"), required):
        raise HTTPException(status_code=403,
                            detail=f"Approval butuh role minimal '{required}'. Role Anda: '{actor.get('role')}'.")
    if v.get("created_by_id") and v["created_by_id"] == actor.get("id"):
        raise HTTPException(status_code=403,
                            detail="Pemisahan tugas (SoD): pembuat voucher tidak boleh menyetujui sendiri.")
    # Recompute alokasi terhadap kondisi roll TERKINI (anti-drift), lalu terapkan.
    rolls = await resolve_target_rolls(v.get("po_ids", []), v.get("entity_id", ""))
    if not rolls:
        raise HTTPException(status_code=400, detail="Tidak ada roll target untuk dialokasi (mungkin sudah dihapus).")
    alloc = compute_allocation(rolls, v.get("total_cost", 0), v.get("basis", "value"))
    applied_count = await apply_allocation_to_rolls(v["voucher_number"], alloc["allocations"])
    updated = await db.landed_cost_vouchers.find_one_and_update(
        {"id": voucher_id},
        {"$set": {"status": "applied", "approval_status": "approved",
                  "approved_by": actor["name"], "approved_at": now_iso(), "applied_at": now_iso(),
                  "effective_basis": alloc["basis"], "allocations": alloc["allocations"],
                  "target_roll_count": alloc["roll_count"],
                  "payment_status": "unpaid", "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry(
             "applied", "Disetujui & dialokasikan ke HPP roll", actor["name"],
             f"{applied_count} roll · {rupiah(alloc['allocated_total'])} · basis {alloc['basis']}")}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    # S#074 (LC-APPLY-GL): kapitalisasi landed cost ke GL (Dr Persediaan / Cr Hutang)
    from services import gl_service
    await gl_service.post_landed_cost(updated, amount=alloc["allocated_total"],
                                      label=v.get("voucher_number", voucher_id))
    await audit(actor["name"], "landed_cost_applied", "landed_cost", voucher_id, {
        "voucher_number": v.get("voucher_number"), "rolls": applied_count,
        "allocated": alloc["allocated_total"], "basis": alloc["basis"]})
    return _hydrate(safe_doc(updated))


@router.post("/landed-costs/{voucher_id}/reject")
async def reject_landed_cost(voucher_id: str, payload: LandedCostDecision, request: Request) -> Dict[str, Any]:
    """Tolak voucher yang menunggu persetujuan → cancelled (tidak ubah HPP)."""
    actor = await current_user(request)
    v = await db.landed_cost_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Landed Cost Voucher tidak ditemukan")
    if v.get("status") != "pending_approval":
        raise HTTPException(status_code=409, detail=f"Voucher status '{v.get('status')}' tidak menunggu approval.")
    required = v.get("required_approval_role") or "manager"
    if not role_satisfies(actor.get("role"), required):
        raise HTTPException(status_code=403, detail=f"Reject butuh role minimal '{required}'.")
    updated = await db.landed_cost_vouchers.find_one_and_update(
        {"id": voucher_id},
        {"$set": {"status": "cancelled", "approval_status": "rejected",
                  "rejected_by": actor["name"], "rejection_reason": payload.notes,
                  "rejected_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry("rejected", "Voucher ditolak", actor["name"], payload.notes or "")}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "landed_cost_rejected", "landed_cost", voucher_id,
                {"voucher_number": v.get("voucher_number"), "reason": payload.notes})
    return _hydrate(safe_doc(updated))


# ── Pay (opsional, setelah applied) ───────────────────────────────────────────

@router.post("/landed-costs/{voucher_id}/pay")
async def pay_landed_cost(voucher_id: str, payload: LandedCostPaymentCreate, request: Request) -> Dict[str, Any]:
    """Bayar voucher landed cost (kas keluar) → cash_transaction(out, ref_type=landed_cost)."""
    actor = await require_permission(request, "landed_cost", "pay")
    v = await db.landed_cost_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Landed Cost Voucher tidak ditemukan")
    if v.get("status") not in ("applied",):
        raise HTTPException(status_code=400, detail=f"Voucher status '{v.get('status')}' belum bisa dibayar (harus applied).")
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Nominal pembayaran harus > 0")
    fin = voucher_financials(v)
    if amount > fin["outstanding"] + 0.01:
        raise HTTPException(status_code=400,
                            detail=f"Pembayaran ({amount}) melebihi sisa ({fin['outstanding']}).")
    cash_entity = "all" if payload.cash_type == "kas_besar" else (payload.entity_id or v.get("entity_id") or DEFAULT_ENTITY_ID)
    cash_doc = {
        "id": new_id("cash"), "number": await next_doc_number("cash_transactions", "number", "CASH-", entity_id=cash_entity),
        "cash_type": payload.cash_type, "direction": "out", "amount": amount,
        "category": "pembelian",
        "description": f"Pembayaran {v.get('voucher_number')} — landed cost {v.get('provider_name','')} ({payload.method})",
        "entity_id": cash_entity, "ref_type": "landed_cost", "ref_id": voucher_id,
        "txn_date": payload.paid_at or now_iso(), "status": "posted",
        "created_by": actor["name"], "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.cash_transactions.insert_one(cash_doc)
    # S#074 (LC-PAY): posting GL inline (Dr Hutang / Cr Kas) — idempotent, tak menunggu backfill
    from services import gl_service
    await gl_service.post_cash_transaction(cash_doc)
    payment = {
        "id": new_id("pay"), "amount": amount, "method": payload.method,
        "cash_txn_id": cash_doc["id"], "cash_txn_number": cash_doc["number"],
        "cash_type": payload.cash_type, "notes": payload.notes,
        "paid_by": actor["name"], "paid_at": payload.paid_at or now_iso(),
    }
    new_paid = round(float(v.get("amount_paid", 0) or 0) + amount, 2)
    new_pay_status = "paid" if new_paid + 0.01 >= float(v.get("total_cost", 0) or 0) else "partial"
    new_status = "paid" if new_pay_status == "paid" else "applied"
    await db.landed_cost_vouchers.update_one(
        {"id": voucher_id},
        {"$inc": {"amount_paid": amount},
         "$set": {"status": new_status, "payment_status": new_pay_status, "updated_at": now_iso()},
         "$push": {"payments": payment, "timeline": timeline_entry(
             "paid", "Pembayaran dicatat", actor["name"],
             f"{rupiah(amount)} via {payload.method} ({payload.cash_type})")}})
    await audit(actor["name"], "landed_cost_payment", "landed_cost", voucher_id,
                {"voucher_number": v.get("voucher_number"), "amount": amount, "cash": cash_doc["number"]})
    updated = await db.landed_cost_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    return _hydrate(safe_doc(updated))


@router.post("/landed-costs/{voucher_id}/cancel")
async def cancel_landed_cost(voucher_id: str, payload: LandedCostDecision, request: Request) -> Dict[str, Any]:
    """Batalkan voucher (hanya draft/pending_approval; setelah applied tidak bisa)."""
    actor = await require_permission(request, "landed_cost", "update")
    v = await db.landed_cost_vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Landed Cost Voucher tidak ditemukan")
    if v.get("status") not in ("draft", "pending_approval"):
        raise HTTPException(status_code=409,
                            detail=f"Voucher status '{v.get('status')}' tidak bisa dibatalkan (HPP sudah dialokasi).")
    updated = await db.landed_cost_vouchers.find_one_and_update(
        {"id": voucher_id},
        {"$set": {"status": "cancelled", "cancelled_by": actor["name"],
                  "cancel_reason": payload.notes, "cancelled_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry("cancelled", "Voucher dibatalkan", actor["name"], payload.notes or "")}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "landed_cost_cancelled", "landed_cost", voucher_id,
                {"voucher_number": v.get("voucher_number")})
    return _hydrate(safe_doc(updated))
