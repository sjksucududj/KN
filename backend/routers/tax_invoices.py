"""Faktur Pajak Jual (tax_invoices) router — Sub-fase 1.9.

Manual issuance (opsional/tidak wajib) dari Sales Order; PKP-only.
Hybrid number (FKT-##### + NSFP resmi) + status normal/pengganti/batal + dokumen HTML.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from db import db
from dependencies import require_permission, audit
from core_utils import safe_doc
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import (
    TaxInvoiceCreate, TaxInvoiceNsfpUpdate, TaxInvoiceReplace, TaxInvoiceCancel,
)
from services.tax_invoice_service import (
    issue_tax_invoice, replace_tax_invoice, cancel_tax_invoice,
    set_nsfp, render_faktur_html,
)

router = APIRouter(prefix="/api")


@router.get("/tax-invoices")
async def list_tax_invoices(request: Request, order_id: str = None,
                           entity_id: str = None, status: str = None) -> List[Dict[str, Any]]:
    """Daftar Faktur Pajak — Sub-fase 1.9 (filter order_id/entity_id/status)."""
    await require_permission(request, "tax_invoice", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if order_id:
        query["order_id"] = order_id
    if status:
        query["status"] = status
    query = resolve_list_scope("tax_invoices", query, ctx, entity_id)
    return await db.tax_invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/tax-invoices/{fkt_id}")
async def get_tax_invoice(fkt_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "tax_invoice", "view")
    ctx = await entity_ctx(request)
    fkt = safe_doc(await db.tax_invoices.find_one({"id": fkt_id}, {"_id": 0}))
    if not fkt:
        raise HTTPException(status_code=404, detail="Faktur Pajak tidak ditemukan")
    assert_entity_access(fkt, "tax_invoices", ctx)
    return fkt


@router.post("/sales-orders/{order_id}/tax-invoice")
async def issue_for_order(order_id: str, payload: TaxInvoiceCreate, request: Request) -> Dict[str, Any]:
    """Terbitkan Faktur Pajak (MANUAL) untuk order. PKP-only, idempotent."""
    actor = await require_permission(request, "tax_invoice", "create")
    fkt = await issue_tax_invoice(order_id, payload.kode_transaksi,
                                  payload.faktur_date, payload.nsfp, actor["name"])
    await audit(actor["name"], "tax_invoice_issued", "tax_invoice", fkt["id"],
                {"number": fkt["number"], "order": fkt["order_number"]})
    return fkt


@router.patch("/tax-invoices/{fkt_id}/nsfp")
async def update_nsfp(fkt_id: str, payload: TaxInvoiceNsfpUpdate, request: Request) -> Dict[str, Any]:
    """Isi/ubah NSFP resmi 16-digit (menyusul dari e-Faktur/Coretax)."""
    actor = await require_permission(request, "tax_invoice", "update")
    fkt = await set_nsfp(fkt_id, payload.nsfp, payload.kode_transaksi)
    await audit(actor["name"], "tax_invoice_nsfp_set", "tax_invoice", fkt_id,
                {"nsfp": payload.nsfp})
    return fkt


@router.post("/tax-invoices/{fkt_id}/replace")
async def replace_faktur(fkt_id: str, payload: TaxInvoiceReplace, request: Request) -> Dict[str, Any]:
    """Terbitkan Faktur Pajak PENGGANTI (revisi)."""
    actor = await require_permission(request, "tax_invoice", "replace")
    fkt = await replace_tax_invoice(fkt_id, payload.reason, payload.kode_transaksi,
                                    payload.nsfp, actor["name"])
    await audit(actor["name"], "tax_invoice_replaced", "tax_invoice", fkt["id"],
                {"replaces": fkt_id, "number": fkt["number"]})
    return fkt


@router.post("/tax-invoices/{fkt_id}/cancel")
async def cancel_faktur(fkt_id: str, payload: TaxInvoiceCancel, request: Request) -> Dict[str, Any]:
    """Batalkan Faktur Pajak (wajib alasan)."""
    actor = await require_permission(request, "tax_invoice", "cancel")
    fkt = await cancel_tax_invoice(fkt_id, payload.reason, actor["name"])
    await audit(actor["name"], "tax_invoice_cancelled", "tax_invoice", fkt_id,
                {"reason": payload.reason})
    return fkt


@router.get("/tax-invoices/{fkt_id}/document")
async def faktur_document(fkt_id: str, request: Request):
    """Dokumen Faktur Pajak (HTML siap cetak)."""
    await require_permission(request, "tax_invoice", "view")
    html = await render_faktur_html(fkt_id)
    return HTMLResponse(content=html)
