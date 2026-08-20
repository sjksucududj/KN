"""Invoices router: invoices and payment simulation."""
import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, next_doc_number, DEFAULT_ENTITY_ID
from schemas import PaymentSimulationCreate
from services import gl_service
from services.customer_service import order_payment_method, NON_AR_METHODS
from services.ar_receipt_service import _cash_routing
from entity_scope import entity_ctx, assert_entity_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/invoices")
async def list_invoices(request: Request) -> List[Dict[str, Any]]:
    await require_permission(request, "order", "view")
    return await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/sales-orders/{order_id}/invoices")
async def order_invoices(order_id: str, request: Request) -> List[Dict[str, Any]]:
    await require_permission(request, "order", "view")
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    # INV-ENTITY-01 (KN-076-IDOR-READ-SUBRES P0): cegah baca invoice SO lintas-entitas.
    assert_entity_access(order, "sales_orders", await entity_ctx(request))
    return await db.invoices.find({"order_id": order_id}, {"_id": 0}).to_list(20)


@router.post("/sales-orders/{order_id}/simulate-payment")
async def simulate_payment(order_id: str, payload: PaymentSimulationCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "update")
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    assert_entity_access(order, "sales_orders", await entity_ctx(request))  # S#074 IDOR-WRITE
    invoice_count = await db.invoices.count_documents({"order_id": order_id}) + 1
    # Fase 1B — invoice mengikuti breakdown pajak order (server-authoritative).
    grand_total = float(order.get("grand_total", order.get("total_amount", 0)) or 0)
    amount = float(payload.amount) if (payload.amount and float(payload.amount) > 0) else grand_total
    invoice = {
        "id": new_id("inv"),
        "number": f"INV-{order['number'].replace('SO-', '')}-{invoice_count:02d}",
        "order_id": order_id,
        "order_number": order["number"],
        "customer_id": order["customer_id"],
        "customer_name": order["customer_name"],
        "entity_id": order.get("entity_id"),
        "amount": amount,
        # Rincian pajak (untuk dokumen Faktur/Invoice)
        "total_amount": float(order.get("total_amount", 0) or 0),
        "discount_total": float(order.get("discount_total", 0) or 0),
        "net_subtotal": float(order.get("net_subtotal", grand_total) or 0),
        "dpp": float(order.get("dpp", 0) or 0),
        "ppn_rate": float(order.get("ppn_rate", 0) or 0),
        "ppn_mode": order.get("ppn_mode", "excluded"),
        "ppn_amount": float(order.get("ppn_amount", 0) or 0),
        "grand_total": grand_total,
        "payment_term_code": order.get("payment_term_code", ""),
        "payment_term_name": order.get("payment_term_name", ""),
        "method": payload.method,
        "status": "paid",
        "created_by": payload.created_by,
        "created_at": now_iso(),
    }
    await db.invoices.insert_one(dict(invoice))   # insert COPY → _id tak mencemari original
    # Status pembayaran: lunas bila menutup grand_total, jika tidak parsial
    total_paid = sum(float(p.get("amount", 0) or 0)
                     for p in order.get("payments", [])) + amount
    pay_status = "paid" if total_paid + 0.01 >= grand_total else "paid_partial"
    await db.sales_orders.update_one(
        {"id": order_id},
        {"$set": {"payment_status": pay_status, "updated_at": now_iso()},
         "$push": {"payments": invoice}}     # invoice masih bersih (tanpa _id)
    )
    await audit(actor["name"], "payment_simulated", "invoice", invoice["id"],
                {"amount": amount, "method": payload.method, "ppn_amount": invoice["ppn_amount"]})
    # F3 — Auto-posting penjualan → GL (idempotent per SO). Best-effort: kegagalan GL
    # tidak boleh menggagalkan pencatatan pembayaran.
    try:
        fresh = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0})) or order
        order_for_gl = {**fresh, "method": payload.method}
        await gl_service.post_sales_order(order_for_gl)
        await gl_service.post_order_cogs(order_for_gl)
        # Gelombang 1 F-4 — settlement pembayaran order AR: kas masuk (Dr Kas / Cr Piutang).
        # Order tunai (NON_AR) tidak perlu — jurnal pendapatannya sudah mendebit Kas.
        if order_payment_method(order_for_gl) not in NON_AR_METHODS:
            cash_type, force_all = _cash_routing(payload.method)
            # FASE E-7 (E7.4) — kas grup dihapus: uang masuk milik badan usaha pesanannya.
            from services.cash_entity_service import resolve_owner as _cash_owner
            cash_entity = _cash_owner(order.get("entity_id"), DEFAULT_ENTITY_ID,
                                      what="Kas masuk pembayaran faktur")
            cdoc = {
                "id": new_id("cash"),
                "number": await next_doc_number("cash_transactions", "number", "CASH-",
                                                entity_id=cash_entity),
                "cash_type": cash_type, "direction": "in", "amount": amount,
                "category": "penagihan",
                "description": f"Pembayaran {invoice['number']} — {order.get('customer_name', '')}",
                "entity_id": cash_entity, "ref_type": "ar_receipt", "ref_id": invoice["id"],
                "txn_date": now_iso(), "status": "posted",
                "created_by": payload.created_by or actor["name"],
                "created_at": now_iso(), "updated_at": now_iso(),
            }
            await db.cash_transactions.insert_one(dict(cdoc))
            await gl_service.post_cash_transaction(cdoc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Gagal posting GL penjualan utk order %s: %s", order_id, exc)
    return safe_doc(invoice)
