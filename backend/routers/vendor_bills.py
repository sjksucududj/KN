"""Vendor Bills router (Fase 5.2 — P0-2): Vendor Bill + 3-Way Matching.

Koleksi kanonik: `vendor_bills` (prefix vbill_). AP berbasis bill *posted*.
Lifecycle: draft → pending_approval → posted → paid (+ cancelled).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, current_user, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID, timeline_entry, next_doc_number, rupiah
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from pagination import is_paged, get_page_params, build_search, merge_query, fetch_page, envelope
from schemas import VendorBillCreate, VendorBillPaymentCreate, VendorBillDecision
from services.config_service import compute_order_pricing, get_effective_settings, role_satisfies
from services import gl_service
from services.vendor_bill_service import (
    evaluate_match, bill_financials, next_bill_number, sync_po_billing,
    already_billed_map, build_billing_context, ACTIVE_BILL_STATUSES,
)
from request_context import active_entity_or

router = APIRouter(prefix="/api")

PAYABLE_BILL_STATUSES = {"posted", "paid"}


async def _tolerances(entity_id: str) -> Dict[str, float]:
    s = await get_effective_settings(entity_id)
    pur = s.get("purchasing", {}) or {}
    return {
        "qty": float(pur.get("bill_qty_tolerance_percent", 0.0) or 0.0),
        "price": float(pur.get("bill_price_tolerance_percent", 5.0) or 0.0),
    }


def _hydrate(bill: Dict[str, Any]) -> Dict[str, Any]:
    bill["financials"] = bill_financials(bill)
    return bill


# ── Billing context (pre-fill form) — STATIC sebelum route /{id} ──────────────

@router.get("/purchase-orders/{po_id}/billing-context")
async def po_billing_context(po_id: str, request: Request) -> Dict[str, Any]:
    """Konteks penagihan PO untuk membuat Vendor Bill (ordered/received/billed/billable)."""
    await require_permission(request, "vendor_bill", "view")
    po = safe_doc(await db.purchase_orders.find_one({"id": po_id}, {"_id": 0}))
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
    return await build_billing_context(po)


# ── Payables summary (AP berbasis bill) — STATIC sebelum route /{id} ──────────

@router.get("/vendor-bills/payables/summary")
async def vendor_bill_payables(request: Request, entity_id: str = None) -> Dict[str, Any]:
    """Ringkasan hutang (AP) berbasis Vendor Bill posted + aging per bill."""
    await require_permission(request, "vendor_bill", "view")
    from datetime import datetime, timezone
    ctx = await entity_ctx(request)
    q: Dict[str, Any] = {"status": {"$in": list(PAYABLE_BILL_STATUSES)}}
    q = resolve_list_scope("vendor_bills", q, ctx, entity_id)
    bills = await db.vendor_bills.find(q, {"_id": 0}).to_list(2000)
    now = datetime.now(timezone.utc)
    by_supplier: Dict[str, Dict[str, Any]] = {}
    aging = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, ">90": 0.0}
    total_outstanding = 0.0
    rows = []
    for b in bills:
        fin = bill_financials(b)
        out = fin["outstanding"]
        if out <= 0.01:
            continue
        total_outstanding += out
        ref_date = b.get("due_date") or b.get("bill_date") or b.get("created_at") or ""
        days = 0
        try:
            d = datetime.fromisoformat(str(ref_date).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            days = (now - d).days
        except Exception:  # noqa: BLE001
            days = 0
        bucket = "0-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else ">90"
        aging[bucket] += out
        sid = b.get("supplier_id") or b.get("supplier_name") or "—"
        sup = by_supplier.setdefault(sid, {
            "supplier_id": b.get("supplier_id", ""), "supplier_name": b.get("supplier_name", "—"),
            "outstanding": 0.0, "bill_count": 0})
        sup["outstanding"] = round(sup["outstanding"] + out, 2)
        sup["bill_count"] += 1
        rows.append({
            "bill_id": b["id"], "bill_number": b.get("bill_number"),
            "supplier_invoice_no": b.get("supplier_invoice_no", ""),
            "po_number": b.get("po_number", ""), "supplier_name": b.get("supplier_name"),
            "supplier_id": b.get("supplier_id", ""), "status": b.get("status"),
            "grand_total": fin["grand_total"], "amount_paid": fin["amount_paid"],
            "outstanding": out, "payment_status": fin["payment_status"],
            "days_outstanding": days, "aging_bucket": bucket,
            "due_date": b.get("due_date", ""), "match_status": b.get("match_status", ""),
        })
    rows.sort(key=lambda r: (-r["days_outstanding"], -r["outstanding"]))
    return {
        "total_outstanding": round(total_outstanding, 2),
        "aging": {k: round(v, 2) for k, v in aging.items()},
        "by_supplier": sorted(by_supplier.values(), key=lambda s: -s["outstanding"]),
        "bills": rows,
    }


# ── List & detail ─────────────────────────────────────────────────────────────

@router.get("/vendor-bills/status-counts")
async def vendor_bill_status_counts(request: Request, entity_id: str = None) -> Dict[str, int]:
    """Jumlah bill per status (untuk badge tab) — agregasi ringan, tak fetch dokumen."""
    await require_permission(request, "vendor_bill", "view")
    ctx = await entity_ctx(request)
    query = resolve_list_scope("vendor_bills", {}, ctx, entity_id)
    pipeline = [{"$match": query}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    agg = await db.vendor_bills.aggregate(pipeline).to_list(100)
    counts: Dict[str, int] = {row["_id"]: int(row["n"]) for row in agg if row.get("_id")}
    counts["all"] = sum(counts.values())
    return counts


@router.get("/vendor-bills")
async def list_vendor_bills(
    request: Request, entity_id: str = None, status: str = None, po_id: str = None
) -> Any:
    """Daftar Vendor Bill (filter entitas/status/PO). Opt-in paginasi (?page/?page_size)."""
    await require_permission(request, "vendor_bill", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if po_id:
        query["po_id"] = po_id
    query = resolve_list_scope("vendor_bills", query, ctx, entity_id)
    if is_paged(request):
        page, page_size, q, _sort = get_page_params(request)
        if q:
            query = merge_query(query, build_search(q, ["bill_number", "supplier_name", "po_number", "supplier_invoice_no"]))
        items, total = await fetch_page(db.vendor_bills, query, page, page_size, sort_field="created_at", sort_dir=-1)
        return envelope([_hydrate(b) for b in items], total, page, page_size)
    bills = await db.vendor_bills.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)
    return [_hydrate(b) for b in bills]


@router.get("/vendor-bills/{bill_id}")
async def get_vendor_bill(bill_id: str, request: Request) -> Dict[str, Any]:
    """Detail satu Vendor Bill + ringkasan keuangan."""
    await require_permission(request, "vendor_bill", "view")
    ctx = await entity_ctx(request)
    bill = safe_doc(await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0}))
    if not bill:
        raise HTTPException(status_code=404, detail="Vendor Bill tidak ditemukan")
    assert_entity_access(bill, "vendor_bills", ctx)
    return _hydrate(bill)


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/vendor-bills")
async def create_vendor_bill(payload: VendorBillCreate, request: Request) -> Dict[str, Any]:
    """Buat Vendor Bill dari PO + jalankan 3-way matching.
    submit_now=True → langsung submit (posted bila match bersih, atau pending_approval
    bila ada variance dalam toleransi). Over-billing di luar toleransi → ditolak."""
    actor = await require_permission(request, "vendor_bill", "create")
    po = safe_doc(await db.purchase_orders.find_one({"id": payload.po_id}, {"_id": 0}))
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
    if po.get("status") in ("waiting_approval", "rejected", "cancelled"):
        raise HTTPException(status_code=400,
                            detail=f"PO status '{po.get('status')}' belum bisa ditagih (perlu disetujui/diterima).")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Minimal 1 item untuk ditagih.")

    entity_id = (payload.entity_id or po.get("entity_id")
                 or active_entity_or(DEFAULT_ENTITY_ID))
    match_mode = payload.match_mode if payload.match_mode in ("received", "ordered") else "received"

    # FASE E-7 (E7.2) — tagihan dari badan usaha grup lahir sebagai FAKTUR INTERNAL di
    # menu Antar Entitas (berpasangan dengan faktur masukan di sisi pembeli), bukan
    # Vendor Bill biasa. PO lama yang sudah salah jalur pun tertahan di sini.
    if po.get("supplier_id"):
        _sup = await db.suppliers.find_one({"id": po["supplier_id"]}, {"_id": 0})
        if _sup:
            from services import group_partner_service as _grp
            await _grp.assert_supplier_not_group_entity(
                _sup, doc_label="Tagihan Supplier (Vendor Bill)")

    # Dedupe nomor invoice supplier (cegah double-billing eksternal).
    inv_no = (payload.supplier_invoice_no or "").strip()
    if inv_no:
        dup = await db.vendor_bills.find_one(
            {"supplier_id": po.get("supplier_id", ""), "supplier_invoice_no": inv_no,
             "status": {"$in": list(ACTIVE_BILL_STATUSES)}}, {"_id": 0, "bill_number": 1})
        if dup:
            raise HTTPException(status_code=409,
                                detail=f"No. invoice supplier '{inv_no}' sudah dipakai pada {dup.get('bill_number')}.")

    # Susun raw_items: quantity = billed_qty (agar subtotal=price×qty invarian).
    po_items = {it.get("product_id"): it for it in po.get("items", [])}
    raw_items: List[Dict[str, Any]] = []
    for line in payload.items:
        po_it = po_items.get(line.product_id)
        if not po_it:
            raise HTTPException(status_code=400,
                                detail=f"Produk {line.product_id} tidak ada di PO {po.get('po_number')}.")
        billed_qty = float(line.billed_qty or 0)
        if billed_qty <= 0:
            continue
        price = float(line.price) if line.price and line.price > 0 else float(po_it.get("price", 0) or 0)
        raw_items.append({
            "product_id": line.product_id,
            "sku": po_it.get("sku", ""),
            "product_name": po_it.get("product_name", ""),
            "quantity": billed_qty,
            "billed_qty": billed_qty,
            "unit": po_it.get("unit", "meter"),
            "price": price,
            "discount_percent": float(line.discount_percent or 0),
        })
    if not raw_items:
        raise HTTPException(status_code=400, detail="Tidak ada qty tagihan yang valid (> 0).")

    pricing = await compute_order_pricing(
        raw_items, entity_id, payload.order_discount_percent,
        cfg_section="purchasing", tax_override=payload.tax_mode or po.get("tax_mode", ""))

    tol = await _tolerances(entity_id)
    billed_so_far = await already_billed_map(po["id"])
    match = evaluate_match(po, pricing["items"], match_mode, billed_so_far, tol["qty"], tol["price"])

    bill_number = await next_bill_number()
    actor_name = payload.created_by or actor.get("name", "Admin")
    needs_approval = match["match_status"] == "warning"
    timeline = [timeline_entry("created", "Vendor Bill dibuat", actor_name,
                               f"{len(match['items'])} item · {rupiah(pricing['grand_total'])} · match: {match['match_status']}")]

    bill = {
        "id": new_id("vbill"),
        "bill_number": bill_number,
        "supplier_invoice_no": inv_no,
        "po_id": po["id"],
        "po_number": po.get("po_number", ""),
        "supplier_id": po.get("supplier_id", ""),
        "supplier_name": po.get("supplier_name", ""),
        "supplier_npwp": po.get("supplier_npwp", ""),
        "warehouse_id": po.get("warehouse_id", ""),
        "warehouse_name": po.get("warehouse_name", ""),
        "entity_id": entity_id,
        "bill_date": payload.bill_date or now_iso(),
        "due_date": payload.due_date or "",
        "match_mode": match_mode,
        "items": match["items"],
        # breakdown harga (invariant-safe, mirror PO P0-1)
        "total_amount": pricing["total_amount"],
        "items_discount_total": pricing["items_discount_total"],
        "order_discount_percent": pricing["order_discount_percent"],
        "order_discount_amount": pricing["order_discount_amount"],
        "discount_total": pricing["discount_total"],
        "net_subtotal": pricing["net_subtotal"],
        "dpp": pricing["dpp"],
        "ppn_rate": pricing["ppn_rate"],
        "ppn_mode": pricing["ppn_mode"],
        "is_pkp": pricing["is_pkp"],
        "ppn_amount": pricing["ppn_amount"],
        "grand_total": pricing["grand_total"],
        "tax_mode": payload.tax_mode or po.get("tax_mode", ""),
        # 3-way match
        "match_status": match["match_status"],
        "match_exceptions": match["exceptions"],
        "within_tolerance": match["within_tolerance"],
        # lifecycle
        "status": "draft",
        "approval_required": needs_approval,
        "required_approval_role": "manager" if needs_approval else "",
        "approval_status": "not_required",
        "approved_by": "", "approved_at": "",
        # AP
        "amount_paid": 0.0,
        "outstanding": round(pricing["grand_total"], 2),
        "payment_status": "unpaid",
        "payments": [],
        "notes": payload.notes,
        "timeline": timeline,
        "created_by": actor_name,
        "created_by_id": actor.get("id", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.vendor_bills.insert_one(bill)
    # FASE G-4 — tagihan supplier menaut ke PO-nya (dua arah) supaya 3-way match
    # bisa ditelusuri dari sisi mana pun.
    from services import doc_refs_service as _refs
    if bill.get("po_id"):
        await _refs.safe_link(("vendor_bill", bill["id"]), ("purchase_order", bill["po_id"]),
                              "parent", note="tagihan atas PO")
    await audit(actor["name"], "vendor_bill_created", "vendor_bill", bill["id"], {
        "bill_number": bill_number, "po_number": po.get("po_number"),
        "grand_total": pricing["grand_total"], "match_status": match["match_status"]})

    if payload.submit_now:
        return await _do_submit(bill["id"], actor)
    return _hydrate(safe_doc(bill))


# ── Submit / approve / reject ─────────────────────────────────────────────────

async def _do_submit(bill_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Vendor Bill tidak ditemukan")
    if bill.get("status") not in ("draft",):
        raise HTTPException(status_code=409, detail=f"Bill status '{bill.get('status')}' tidak bisa di-submit.")
    # Re-evaluasi 3-way match terhadap kondisi terkini (cegah race/over-billing antar draft).
    po = await db.purchase_orders.find_one({"id": bill["po_id"]}, {"_id": 0})
    if po:
        tol = await _tolerances(bill.get("entity_id"))
        billed_so_far = await already_billed_map(bill["po_id"], exclude_bill_id=bill_id)
        match = evaluate_match(po, bill.get("items", []), bill.get("match_mode", "received"),
                               billed_so_far, tol["qty"], tol["price"])
        needs_approval = match["match_status"] == "warning"
        await db.vendor_bills.update_one({"id": bill_id}, {"$set": {
            "items": match["items"], "match_status": match["match_status"],
            "match_exceptions": match["exceptions"], "within_tolerance": match["within_tolerance"],
            "approval_required": needs_approval,
            "required_approval_role": "manager" if needs_approval else "",
            "updated_at": now_iso()}})
        bill["match_status"] = match["match_status"]
        bill["approval_required"] = needs_approval
    if bill.get("match_status") == "blocked":
        raise HTTPException(status_code=400,
                            detail="3-way match GAGAL (over-billing di luar toleransi). Perbaiki qty tagihan dulu.")
    if bill.get("approval_required"):
        updated = await db.vendor_bills.find_one_and_update(
            {"id": bill_id},
            {"$set": {"status": "pending_approval", "approval_status": "pending", "updated_at": now_iso()},
             "$push": {"timeline": timeline_entry(
                 "submitted_for_approval", "Menunggu persetujuan manager", actor.get("name", ""),
                 "ada selisih qty/harga dalam toleransi")}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        await audit(actor["name"], "vendor_bill_submitted", "vendor_bill", bill_id,
                    {"bill_number": bill.get("bill_number"), "to": "pending_approval"})
        return _hydrate(safe_doc(updated))
    # tanpa approval → langsung posted
    return await _post_bill(bill_id, actor, note="auto-posted (match bersih)")


async def _post_bill(bill_id: str, actor: Dict[str, Any], note: str = "") -> Dict[str, Any]:
    updated = await db.vendor_bills.find_one_and_update(
        {"id": bill_id},
        {"$set": {"status": "posted", "approval_status": "approved" if note.startswith("disetujui") else "not_required",
                  "posted_by": actor.get("name", ""), "posted_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry("posted", "Bill di-posting (AP diakui)", actor.get("name", ""), note)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await sync_po_billing(updated["po_id"])
    # S#2026-07-21 — Traceability: tautkan invoice supplier ke roll asal PO ini
    # (untuk kartu asal produk + retur presisi). Best-effort, non-blocking.
    try:
        billed_pids = [it.get("product_id") for it in (updated.get("items") or []) if it.get("product_id")]
        if billed_pids:
            await db.inventory_rolls.update_many(
                {"$and": [
                    {"$or": [{"po_id": updated["po_id"]}, {"acquired.ref_id": updated["po_id"]}]},
                    {"product_id": {"$in": billed_pids}},
                    {"$or": [{"vendor_bill_id": {"$in": ["", None]}}, {"vendor_bill_id": {"$exists": False}}]},
                ]},
                {"$set": {"vendor_bill_id": updated["id"],
                          "supplier_invoice_no": updated.get("supplier_invoice_no", ""),
                          "updated_at": now_iso()}})
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("Gagal tautkan invoice ke roll (bill %s): %s", bill_id, exc)
    # Gelombang 1 F-5 — posting AP ke GL: Dr GR-IR + PPN Masukan / Cr Hutang (best-effort).
    try:
        await gl_service.post_vendor_bill(updated)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).error("Gagal posting GL vendor bill %s: %s", bill_id, exc)
    await audit(actor["name"], "vendor_bill_posted", "vendor_bill", bill_id,
                {"bill_number": updated.get("bill_number"), "grand_total": updated.get("grand_total")})
    return _hydrate(safe_doc(updated))


@router.post("/vendor-bills/{bill_id}/submit")
async def submit_vendor_bill(bill_id: str, request: Request) -> Dict[str, Any]:
    """Submit bill: posted (match bersih) atau pending_approval (ada variance)."""
    actor = await require_permission(request, "vendor_bill", "update")
    return await _do_submit(bill_id, actor)


@router.post("/vendor-bills/{bill_id}/approve")
async def approve_vendor_bill(bill_id: str, request: Request) -> Dict[str, Any]:
    """Approve bill yang menunggu persetujuan (role manager+). SoD: pembuat ≠ approver."""
    actor = await current_user(request)
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Vendor Bill tidak ditemukan")
    if bill.get("status") != "pending_approval":
        raise HTTPException(status_code=409, detail=f"Bill status '{bill.get('status')}' tidak menunggu approval.")
    required = bill.get("required_approval_role") or "manager"
    if not role_satisfies(actor.get("role"), required):
        raise HTTPException(status_code=403,
                            detail=f"Approval bill butuh role minimal '{required}'. Role Anda: '{actor.get('role')}'.")
    if bill.get("created_by_id") and bill["created_by_id"] == actor.get("id"):
        raise HTTPException(status_code=403,
                            detail="Pemisahan tugas (SoD): pembuat bill tidak boleh menyetujui bill sendiri.")
    await db.vendor_bills.update_one(
        {"id": bill_id},
        {"$set": {"approval_status": "approved", "approved_by": actor["name"], "approved_at": now_iso()}})
    return await _post_bill(bill_id, actor, note=f"disetujui oleh {actor.get('role')}")


@router.post("/vendor-bills/{bill_id}/reject")
async def reject_vendor_bill(bill_id: str, payload: VendorBillDecision, request: Request) -> Dict[str, Any]:
    """Tolak bill yang menunggu persetujuan → status cancelled."""
    actor = await current_user(request)
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Vendor Bill tidak ditemukan")
    if bill.get("status") != "pending_approval":
        raise HTTPException(status_code=409, detail=f"Bill status '{bill.get('status')}' tidak menunggu approval.")
    required = bill.get("required_approval_role") or "manager"
    if not role_satisfies(actor.get("role"), required):
        raise HTTPException(status_code=403, detail=f"Reject bill butuh role minimal '{required}'.")
    updated = await db.vendor_bills.find_one_and_update(
        {"id": bill_id},
        {"$set": {"status": "cancelled", "approval_status": "rejected",
                  "rejected_by": actor["name"], "rejection_reason": payload.notes,
                  "rejected_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry("rejected", "Bill ditolak", actor["name"], payload.notes or "")}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "vendor_bill_rejected", "vendor_bill", bill_id,
                {"bill_number": bill.get("bill_number"), "reason": payload.notes})
    return _hydrate(safe_doc(updated))


# ── Pay ───────────────────────────────────────────────────────────────────────

@router.post("/vendor-bills/{bill_id}/pay")
async def pay_vendor_bill(bill_id: str, payload: VendorBillPaymentCreate, request: Request) -> Dict[str, Any]:
    """Bayar Vendor Bill (kas keluar) → cash_transaction(out, ref_type=vendor_bill) + update AP.

    FASE G-3 — selisih pembayaran supplier ikut ditakar: kurang/lebih di dalam toleransi
    ditutup otomatis (berlabel), kelebihan yang disengaja menjadi **uang muka supplier**
    (`ap_advance`), dan sisa hutang bisa ditutup sebagai potongan supplier (`ap_writeoff`).
    """
    actor = await require_permission(request, "vendor_bill", "pay")
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Vendor Bill tidak ditemukan")
    if bill.get("status") not in ("posted",):
        raise HTTPException(status_code=400, detail=f"Bill status '{bill.get('status')}' belum bisa dibayar (harus posted).")
    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Nominal pembayaran harus > 0")
    fin = bill_financials(bill)
    grand_total = round(float(bill.get("grand_total", 0) or 0), 2)

    # ── FASE G-3 — takar selisih sebelum kas keluar ──────────────────────────
    from services import payment_variance_service as pvs
    vdecision = payload.variance or {}
    assessment = await pvs.assess_bill(bill, amount)
    over = round(max(0.0, amount - fin["outstanding"]), 2)
    if over > 0.01:
        kind_ok = str(vdecision.get("kind") or "") in ("ap_advance",)
        if assessment["direction"] != pvs.DIR_ROUNDING and not kind_ok:
            raise HTTPException(
                status_code=400,
                detail=(f"Pembayaran ({amount}) melebihi sisa hutang ({fin['outstanding']}). "
                        "Bila memang ingin membayar lebih, pilih keputusan "
                        "'Kelebihan jadi uang muka supplier' (selisih pembayaran)."))
    applied = round(min(amount, fin["outstanding"]), 2)

    cash_entity = "all" if payload.cash_type == "kas_besar" else (payload.entity_id or bill.get("entity_id") or DEFAULT_ENTITY_ID)
    # FASE E-7 (E7.4) — kas grup DIHAPUS: uang keluar tetap milik badan usaha tagihannya.
    from services.cash_entity_service import resolve_owner as _cash_owner
    cash_entity = _cash_owner(payload.entity_id, bill.get("entity_id"), DEFAULT_ENTITY_ID,
                              what="Kas keluar pembayaran tagihan supplier")
    cash_doc = {
        "id": new_id("cash"), "number": await next_doc_number("cash_transactions", "number", "CASH-", entity_id=cash_entity),
        "cash_type": payload.cash_type, "direction": "out", "amount": applied,
        "category": "pembelian",
        "description": f"Pembayaran {bill.get('bill_number')} — {bill.get('supplier_name','')} ({payload.method})",
        "entity_id": cash_entity, "ref_type": "vendor_bill", "ref_id": bill_id,
        "owner_entity_id": bill.get("entity_id") or DEFAULT_ENTITY_ID,
        "txn_date": payload.paid_at or now_iso(), "status": "posted",
        "created_by": actor["name"], "created_at": now_iso(), "updated_at": now_iso(),
    }
    payment = {
        "id": new_id("pay"), "amount": applied, "method": payload.method,
        "cash_txn_id": cash_doc["id"], "cash_txn_number": cash_doc["number"],
        "cash_type": payload.cash_type, "notes": payload.notes,
        "paid_by": actor["name"], "paid_at": payload.paid_at or now_iso(),
    }
    # INV-CONC-01 (KN-077-RACE-VBILL-PAY P0): guard ATOMIK anti-TOCTOU/overpayment.
    # $expr memastikan HANYA request yang menjaga (amount_paid + amount) <= grand_total yang
    # lolos; K pembayaran paralel → hanya yang muat yang sukses, sisanya 409. Match+update
    # ATOMIC pada satu dokumen sehingga read-stale tak bisa dobel-inc. Kas hanya masuk SETELAH
    # guard sukses → tak ada orphan cash_transaction saat 409.
    updated = await db.vendor_bills.find_one_and_update(
        {"id": bill_id, "status": "posted",
         "$expr": {"$lte": [{"$add": [{"$ifNull": ["$amount_paid", 0]}, applied]}, grand_total + 0.01]}},
        {"$inc": {"amount_paid": applied},
         "$set": {"updated_at": now_iso()},
         "$push": {"payments": payment, "timeline": timeline_entry(
             "paid", "Pembayaran dicatat", actor["name"],
             f"{rupiah(applied)} via {payload.method} ({payload.cash_type})")}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(
            status_code=409,
            detail="Pembayaran gagal — sisa hutang tidak cukup atau bill baru saja berubah "
                   "(kemungkinan pembayaran paralel). Muat ulang lalu coba lagi.")
    # Finalisasi status berdasar amount_paid ter-update (hasil $inc atomik).
    new_paid = round(float(updated.get("amount_paid", 0) or 0), 2)
    if new_paid + 0.01 >= grand_total and updated.get("status") != "paid":
        await db.vendor_bills.update_one({"id": bill_id}, {"$set": {"status": "paid"}})
        updated["status"] = "paid"
    # Kas keluar dicatat hanya SETELAH guard sukses.
    await db.cash_transactions.insert_one(cash_doc)
    await gl_service.post_cash_transaction(cash_doc)

    # ── FASE G-3 — kelebihan → uang muka supplier (kas keluar terpisah + jurnal) ──
    advance_cash = None
    if over > 0.01:
        advance_cash = {
            "id": new_id("cash"),
            "number": await next_doc_number("cash_transactions", "number", "CASH-",
                                            entity_id=cash_entity),
            "cash_type": payload.cash_type, "direction": "out", "amount": over,
            "category": "uang muka supplier",
            "description": (f"Kelebihan bayar {bill.get('bill_number')} — "
                            f"{bill.get('supplier_name','')} menjadi uang muka"),
            "entity_id": cash_entity, "ref_type": "ap_advance", "ref_id": bill_id,
            "owner_entity_id": bill.get("entity_id") or DEFAULT_ENTITY_ID,
            "txn_date": payload.paid_at or now_iso(), "status": "posted",
            "created_by": actor["name"], "created_at": now_iso(), "updated_at": now_iso(),
        }
        await db.cash_transactions.insert_one(advance_cash)
        await gl_service.post_cash_transaction(advance_cash)

    # Keputusan selisih (otomatis bila di dalam toleransi, eksplisit bila diminta).
    decision = None
    if assessment["direction"] != pvs.DIR_NONE and (
            assessment["direction"] == pvs.DIR_ROUNDING or vdecision.get("kind")):
        try:
            decision = await pvs.decide_bill(safe_doc(updated), assessment,
                                             vdecision or {}, actor,
                                             advance_cash=advance_cash)
        except pvs.VarianceError as exc:
            # Uang sudah keluar — keputusan yang gagal tidak boleh membatalkannya;
            # catat sebabnya di timeline supaya bisa ditindaklanjuti.
            await db.vendor_bills.update_one({"id": bill_id}, {"$push": {"timeline": timeline_entry(
                "variance_failed", "Keputusan selisih gagal", actor["name"], str(exc))}})
    updated = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0}) or updated
    await sync_po_billing(bill["po_id"])
    await audit(actor["name"], "vendor_bill_payment", "vendor_bill", bill_id,
                {"bill_number": bill.get("bill_number"), "amount": applied,
                 "advance": over, "cash": cash_doc["number"],
                 "variance": (decision or {}).get("kind", "")})
    out = _hydrate(safe_doc(updated))
    out["variance_assessment"] = assessment
    if decision:
        out["variance_decision"] = decision
    return out


@router.post("/vendor-bills/{bill_id}/cancel")
async def cancel_vendor_bill(bill_id: str, payload: VendorBillDecision, request: Request) -> Dict[str, Any]:
    """Batalkan bill (draft/pending_approval/posted yang belum dibayar)."""
    actor = await require_permission(request, "vendor_bill", "update")
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Vendor Bill tidak ditemukan")
    if float(bill.get("amount_paid", 0) or 0) > 0.01:
        raise HTTPException(status_code=400, detail="Bill yang sudah ada pembayaran tidak bisa dibatalkan.")
    if bill.get("status") in ("cancelled", "paid"):
        raise HTTPException(status_code=409, detail=f"Bill status '{bill.get('status')}' tidak bisa dibatalkan.")
    updated = await db.vendor_bills.find_one_and_update(
        {"id": bill_id},
        {"$set": {"status": "cancelled", "cancelled_by": actor["name"],
                  "cancel_reason": payload.notes, "cancelled_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry("cancelled", "Bill dibatalkan", actor["name"], payload.notes or "")}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    # S#074 (VB-CANCEL-GL): balik jurnal bila bill sudah posted (kembalikan saldo Hutang/GR-IR/PPN)
    if bill.get("status") == "posted":
        from services import gl_service
        await gl_service.reverse_vendor_bill(bill, reason=payload.notes or "", actor_name=actor["name"])
    await sync_po_billing(bill["po_id"])
    await audit(actor["name"], "vendor_bill_cancelled", "vendor_bill", bill_id,
                {"bill_number": bill.get("bill_number")})
    return _hydrate(safe_doc(updated))
