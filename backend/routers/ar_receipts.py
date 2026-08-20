"""AR Receipts router (EPIC3B) — penerimaan pembayaran customer.

Akses: admin/manager/sales (view+create), admin/manager (void).
Respons: ARRAY/OBJEK telanjang (kontrak KN3).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from services import ar_receipt_service

router = APIRouter(prefix="/api")


class AllocationIn(BaseModel):
    order_id: str
    amount: float
    # FASE G-3 — pembayaran boleh MENYEBUT baris jadwal tujuan ("ini untuk cicilan ke-3").
    plan_line_seq: int = 0


class ReceiptPayload(BaseModel):
    customer_id: str
    amount: float
    method: str = "transfer"
    receipt_date: Optional[str] = None
    entity_id: Optional[str] = None
    notes: str = ""
    use_deposit_amount: float = 0.0
    allocations: List[AllocationIn] = Field(default_factory=list)
    # FASE G-3 — keputusan selisih pembayaran yang dipilih petugas di dialog:
    #   {"kind": "outstanding|reschedule|writeoff|deposit|allocate|refund",
    #    "reason_code": "...", "note": "...", "due_date": "...", "amount": 0,
    #    "allocations": [{"order_id": "...", "amount": 0}], "method": "transfer"}
    variance: Optional[Dict[str, Any]] = None


@router.get("/ar-receipts/open-orders")
async def open_orders(request: Request, customer_id: str = Query(...)) -> List[Dict[str, Any]]:
    """Order AR terbuka customer (untuk alokasi pembayaran)."""
    await require_permission(request, "ar_receipt", "view")
    return await ar_receipt_service.list_open_orders(customer_id)


@router.get("/ar-receipts/deposit")
async def deposit_balance(request: Request, customer_id: str = Query(...)) -> Dict[str, Any]:
    """Saldo deposit/kelebihan bayar customer (P2-5)."""
    await require_permission(request, "ar_receipt", "view")
    bal = await ar_receipt_service.get_deposit_balance(customer_id)
    return {"customer_id": customer_id, "deposit_balance": bal}


@router.get("/ar-receipts")
async def list_receipts(request: Request, customer_id: Optional[str] = Query(None),
                        entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "ar_receipt", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("ar_receipts", {}, ctx, entity_id)
    return await ar_receipt_service.list_receipts(customer_id, scope=scope)


@router.post("/ar-receipts")
async def create_receipt(payload: ReceiptPayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "ar_receipt", "create")
    ctx = await entity_ctx(request)
    body = payload.model_dump()
    body["entity_id"] = body.get("entity_id") or ctx.active_entity_id
    body["allocations"] = [a for a in body.get("allocations", [])]
    receipt = await ar_receipt_service.create_receipt(body, actor)
    # Fase 5 — auto-kirim WhatsApp kwitansi bila ada aturan aktif (best-effort).
    try:
        from services import delivery_service as _ds
        _rid = receipt.get("id") if isinstance(receipt, dict) else None
        if _rid:
            await _ds.dispatch_event("ar_receipt", _rid, "created",
                                     body.get("entity_id"),
                                     actor.get("name") if isinstance(actor, dict) else str(actor))
    except Exception:  # noqa: BLE001
        pass
    return receipt


@router.post("/ar-receipts/{receipt_id}/void")
async def void_receipt(receipt_id: str, request: Request,
                       reason: str = Query("", max_length=500)) -> Dict[str, Any]:
    """Batalkan penerimaan AR — balik payments[], void kas, koreksi deposit (P2-6).

    FASE P5 — dua hal diperbaiki di sini:
      1. `reason` (opsional di API, WAJIB di layar) disimpan sebagai `voided_reason`:
         pembatalan kwitansi MEMBALIK uang yang sudah tercatat masuk (pembayaran pada
         order + kas + deposit), jadi sebabnya harus bisa dibaca ulang.
      2. **Jejak audit yang hilang** — pembatalan ini sebelumnya tidak menulis satu baris
         pun ke `audit_logs` (baik router maupun service), padahal ia membalik uang.
         Sekarang dicatat.
    """
    actor = await require_permission(request, "ar_receipt", "void")
    result = await ar_receipt_service.void_receipt(receipt_id, actor, reason=(reason or "").strip())
    await audit(actor["name"], "ar_receipt_voided", "ar_receipt", receipt_id,
                {"reason": (reason or "").strip(), "number": result.get("number", ""),
                 "amount": result.get("amount", 0)})
    return result


@router.get("/ar-receipts/{receipt_id}")
async def get_receipt(receipt_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "ar_receipt", "view")
    ctx = await entity_ctx(request)
    doc = await ar_receipt_service.get_receipt(receipt_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Receipt tidak ditemukan")
    assert_entity_access(doc, "ar_receipts", ctx)
    return doc
