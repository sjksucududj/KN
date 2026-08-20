"""Store Credit router (R5.2) — Saldo Kredit Pelanggan (store credit) ledger.

Akses (reuse resource 'ar_receipt'): admin/manager/sales view+redeem; admin/manager adjust (void).
Respons: ARRAY/OBJEK telanjang (kontrak KN3).

FASE E-9 — **PAGAR BADAN USAHA**. Saldo kredit adalah UANG pelanggan pada satu badan
usaha. Sebelum ini seluruh endpoint di sini memakai `entity_id` opsional dari query dan
tidak pernah membandingkannya dengan wewenang pemanggil, sehingga sales PT-B bisa
membaca — bahkan MENEBUS — saldo kredit pelanggan PT-A. Cacatnya tidak pernah
terlihat karena `store_credit_ledger` kosong di data demo; baris pertamanya lahir dari
rantai retur FASE E-9 (retur diselesaikan sebagai store credit) dan gate isolasi
langsung memerah. Sekarang: baca ter-scope, tulis wajib di dalam cakupan.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field

from dependencies import require_permission
from entity_scope import entity_ctx, resolve_scope_ids
from services import store_credit_service as sc
from services.ar_receipt_service import list_open_orders

router = APIRouter(prefix="/api")


class AllocationIn(BaseModel):
    order_id: str
    amount: float


class RedeemPayload(BaseModel):
    customer_id: str
    amount: float
    entity_id: Optional[str] = None
    note: str = ""
    allocations: List[AllocationIn] = Field(default_factory=list)


class AdjustPayload(BaseModel):
    customer_id: str
    amount: float               # bertanda: + tambah, - kurangi
    entity_id: Optional[str] = None
    note: str = ""


class ReversePayload(BaseModel):
    reason: str = ""


async def _scope(request: Request, entity_id: Optional[str] = None) -> List[str]:
    """Badan usaha yang boleh dibaca pemanggil (403 bila memaksa yang bukan haknya)."""
    ctx = await entity_ctx(request)
    return resolve_scope_ids(ctx, entity_id or None)


async def _write_entity(request: Request, entity_id: Optional[str]) -> str:
    """Badan usaha SASARAN untuk aksi tulis (tebus/koreksi) — wajib satu & dalam cakupan."""
    ctx = await entity_ctx(request)
    target = (entity_id or ctx.active_entity_id or "").strip()
    if not target or target == "all":
        raise HTTPException(
            status_code=400,
            detail=("Pilih dulu satu badan usaha untuk aksi ini — saldo kredit pelanggan "
                    "melekat pada badan usaha penerbitnya, bukan pada gabungan."))
    if target not in resolve_scope_ids(ctx, None) and target not in (ctx.allowed_entity_ids or []):
        raise HTTPException(status_code=403, detail="Tidak berwenang atas badan usaha ini")
    return target


@router.get("/store-credit")
async def list_summary(request: Request, entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Ringkasan saldo store credit per (pelanggan, entitas) yang != 0."""
    await require_permission(request, "ar_receipt", "view")
    return await sc.summary(entity_id, scope_ids=await _scope(request, entity_id))


@router.get("/store-credit/balance")
async def get_balance(request: Request, customer_id: str = Query(...),
                      entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "ar_receipt", "view")
    scope = await _scope(request, entity_id)
    bal = await sc.balance(customer_id, entity_id, scope_ids=scope)
    by_entity = await sc.balances_by_entity(customer_id, scope_ids=scope)
    return {"customer_id": customer_id, "entity_id": entity_id or "",
            "balance": bal, "by_entity": by_entity}


@router.get("/store-credit/ledger")
async def get_ledger(request: Request, customer_id: Optional[str] = Query(None),
                     entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "ar_receipt", "view")
    return await sc.ledger(customer_id, entity_id,
                           scope_ids=await _scope(request, entity_id))


@router.get("/store-credit/open-orders")
async def open_orders(request: Request, customer_id: str = Query(...)) -> List[Dict[str, Any]]:
    """Order AR terbuka customer (untuk alokasi redeem store credit)."""
    await require_permission(request, "ar_receipt", "view")
    return await list_open_orders(customer_id)


@router.post("/store-credit/redeem")
async def redeem(payload: RedeemPayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "ar_receipt", "create")
    body = payload.model_dump()
    target = await _write_entity(request, body.get("entity_id"))
    return await sc.redeem(
        customer_id=body["customer_id"], entity_id=target,
        amount=body["amount"], allocations=body.get("allocations") or [],
        note=body.get("note", ""), actor=actor)


@router.post("/store-credit/adjust")
async def adjust(payload: AdjustPayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "ar_receipt", "void")   # admin/manager only
    body = payload.model_dump()
    target = await _write_entity(request, body.get("entity_id"))
    return await sc.adjust(
        customer_id=body["customer_id"], entity_id=target,
        amount_signed=body["amount"], note=body.get("note", ""), actor=actor)


@router.post("/store-credit/entries/{entry_id}/reverse")
async def reverse_entry(entry_id: str, request: Request,
                        payload: ReversePayload = ReversePayload()) -> Dict[str, Any]:
    """R5.4 — Batalkan (reversal) satu baris ledger store credit: `adjust` atau `redeem`.
    Entri `issue` dibatalkan lewat reversal Retur sumbernya (GL-nya milik retur)."""
    actor = await require_permission(request, "ar_receipt", "void")   # admin/manager only
    entry = await sc.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Baris ledger tidak ditemukan")
    # IDOR-WRITE: baris milik badan usaha lain tidak boleh dibatalkan dari sini.
    if (entry.get("entity_id") or "") not in await _scope(request):
        raise HTTPException(status_code=403,
                            detail="Baris ini milik badan usaha lain")
    return await sc.reverse_ledger_entry(entry_id, reason=payload.reason, actor=actor)
