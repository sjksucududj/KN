"""Faktur Pajak Masukan (tax_invoices_in) router — Fase 5.5 / P0-3.

Koleksi kanonik: `tax_invoices_in` (prefix `fpm_`, nomor internal `FPM-NNNNN`).
Sumber: Vendor Bill ber-PPN (posted/paid). NSFP supplier disimpan + dedupe.
Rekap PPN Masukan vs Keluaran per periode → posisi kurang/lebih bayar.
Lifecycle: recorded → cancelled.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID, timeline_entry, rupiah
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import InputTaxInvoiceCreate, InputTaxInvoiceCancel
from services.input_tax_service import (
    next_input_number, normalize_nsfp, format_nsfp_display, period_of,
    find_active_duplicate_nsfp, snapshot_from_bill, eligible_vendor_bills, vat_summary,
    ELIGIBLE_BILL_STATUSES, ACTIVE_INPUT_STATUSES,
)

router = APIRouter(prefix="/api")


def _hydrate(d: Dict[str, Any]) -> Dict[str, Any]:
    d["nsfp_display"] = format_nsfp_display(d.get("nsfp", ""))
    return d


# ── STATIC routes (sebelum /{id}) ─────────────────────────────────────────────

@router.get("/input-tax-invoices/eligible-bills")
async def list_eligible_bills(request: Request, entity_id: str = None) -> List[Dict[str, Any]]:
    """Vendor Bill ber-PPN (posted/paid) yang belum punya Faktur Masukan aktif."""
    await require_permission(request, "input_tax", "view")
    ctx = await entity_ctx(request)
    eid = entity_id if entity_id else ("" if ctx.view_all else ctx.active_entity_id)
    return await eligible_vendor_bills(eid or "")


@router.get("/tax/vat-summary")
async def get_vat_summary(request: Request, period: str = None, entity_id: str = None) -> Dict[str, Any]:
    """Rekap PPN Masukan vs Keluaran per periode (YYYY-MM) → kurang/lebih bayar."""
    await require_permission(request, "input_tax", "view")
    ctx = await entity_ctx(request)
    eid = entity_id if entity_id else ("" if ctx.view_all else ctx.active_entity_id)
    return await vat_summary(period or "", eid or "")


# ── List & detail ─────────────────────────────────────────────────────────────

@router.get("/input-tax-invoices")
async def list_input_tax(
    request: Request, entity_id: str = None, status: str = None,
    period: str = None, supplier_id: str = None,
) -> List[Dict[str, Any]]:
    """Daftar Faktur Pajak Masukan (filter entitas/status/periode/supplier)."""
    await require_permission(request, "input_tax", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if period:
        query["period"] = period
    if supplier_id:
        query["supplier_id"] = supplier_id
    query = resolve_list_scope("tax_invoices_in", query, ctx, entity_id)
    docs = await db.tax_invoices_in.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [_hydrate(d) for d in docs]


@router.get("/input-tax-invoices/{fpm_id}")
async def get_input_tax(fpm_id: str, request: Request) -> Dict[str, Any]:
    """Detail satu Faktur Pajak Masukan."""
    await require_permission(request, "input_tax", "view")
    ctx = await entity_ctx(request)
    d = safe_doc(await db.tax_invoices_in.find_one({"id": fpm_id}, {"_id": 0}))
    if not d:
        raise HTTPException(status_code=404, detail="Faktur Pajak Masukan tidak ditemukan")
    assert_entity_access(d, "tax_invoices_in", ctx)
    return _hydrate(d)


# ── Create (dari Vendor Bill) ─────────────────────────────────────────────────

@router.post("/input-tax-invoices")
async def create_input_tax(payload: InputTaxInvoiceCreate, request: Request) -> Dict[str, Any]:
    """Catat Faktur Pajak Masukan dari Vendor Bill ber-PPN. NSFP wajib + dedupe."""
    actor = await require_permission(request, "input_tax", "create")
    bill = safe_doc(await db.vendor_bills.find_one({"id": payload.vendor_bill_id}, {"_id": 0}))
    if not bill:
        raise HTTPException(status_code=404, detail="Vendor Bill tidak ditemukan")
    if bill.get("status") not in ELIGIBLE_BILL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Vendor Bill harus posted/paid (status sekarang: {bill.get('status')}).")
    if float(bill.get("ppn_amount", 0) or 0) <= 0:
        raise HTTPException(status_code=400, detail="Vendor Bill tanpa PPN — tidak ada Faktur Masukan.")
    if bill.get("input_faktur_status") in ACTIVE_INPUT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Bill ini sudah punya Faktur Masukan aktif ({bill.get('input_faktur_number','')}).")

    nsfp_raw = (payload.nsfp or "").strip()
    nsfp_digits = normalize_nsfp(nsfp_raw)
    if len(nsfp_digits) < 1:
        raise HTTPException(status_code=400, detail="NSFP (Nomor Seri Faktur Pajak) supplier wajib diisi.")
    dup = await find_active_duplicate_nsfp(nsfp_digits)
    if dup:
        raise HTTPException(
            status_code=409,
            detail=f"NSFP '{nsfp_raw}' sudah dicatat pada {dup.get('number')}.")

    snap = snapshot_from_bill(bill)
    entity_id = snap.get("entity_id") or DEFAULT_ENTITY_ID
    faktur_date = payload.faktur_date or bill.get("bill_date") or now_iso()
    number = await next_input_number()
    actor_name = payload.created_by or actor.get("name", "Admin")

    doc = {
        "id": new_id("fpm"),
        "number": number,
        "nsfp": nsfp_raw,
        "nsfp_digits": nsfp_digits,
        "kode_transaksi": (payload.kode_transaksi or "01").strip(),
        "status": "recorded",
        "faktur_date": faktur_date,
        "period": period_of(faktur_date),
        **snap,
        "notes": payload.notes or "",
        "timeline": [timeline_entry(
            "recorded", "Faktur Pajak Masukan dicatat", actor_name,
            f"NSFP {nsfp_raw} · {snap.get('supplier_name','')} · PPN {rupiah(snap.get('ppn_amount',0))}")],
        "created_by": actor_name,
        "created_by_id": actor.get("id", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.tax_invoices_in.insert_one(doc)
    # Tandai bill agar tak dobel + tampil di UI.
    await db.vendor_bills.update_one(
        {"id": bill["id"]},
        {"$set": {"input_faktur_id": doc["id"], "input_faktur_number": number,
                  "input_faktur_status": "recorded", "input_faktur_nsfp": nsfp_raw,
                  "updated_at": now_iso()}})
    await audit(actor["name"], "input_tax_recorded", "input_tax", doc["id"],
                {"number": number, "nsfp": nsfp_raw, "bill": bill.get("bill_number"),
                 "ppn": snap.get("ppn_amount")})
    return _hydrate(safe_doc(doc))


# ── Cancel ────────────────────────────────────────────────────────────────────

@router.post("/input-tax-invoices/{fpm_id}/cancel")
async def cancel_input_tax(fpm_id: str, payload: InputTaxInvoiceCancel, request: Request) -> Dict[str, Any]:
    """Batalkan Faktur Pajak Masukan → status cancelled, NSFP bisa dipakai ulang,
    flag pada Vendor Bill dilepas (bill kembali eligible)."""
    actor = await require_permission(request, "input_tax", "cancel")
    d = await db.tax_invoices_in.find_one({"id": fpm_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Faktur Pajak Masukan tidak ditemukan")
    if d.get("status") == "cancelled":
        raise HTTPException(status_code=409, detail="Faktur Pajak Masukan sudah dibatalkan.")
    if not (payload.reason or "").strip():
        raise HTTPException(status_code=400, detail="Alasan pembatalan wajib diisi.")
    updated = await db.tax_invoices_in.find_one_and_update(
        {"id": fpm_id},
        {"$set": {"status": "cancelled", "cancel_reason": payload.reason.strip(),
                  "cancelled_by": actor["name"], "cancelled_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry("cancelled", "Faktur Masukan dibatalkan",
                                              actor["name"], payload.reason.strip())}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if d.get("vendor_bill_id"):
        await db.vendor_bills.update_one(
            {"id": d["vendor_bill_id"]},
            {"$set": {"input_faktur_status": "cancelled", "updated_at": now_iso()},
             "$unset": {"input_faktur_id": "", "input_faktur_number": "", "input_faktur_nsfp": ""}})
    await audit(actor["name"], "input_tax_cancelled", "input_tax", fpm_id,
                {"number": d.get("number"), "reason": payload.reason})
    return _hydrate(safe_doc(updated))
