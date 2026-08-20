"""Bank/Cash Accounts router (EPIC7-B) — multi-akun kas & bank + rekonsiliasi.

Akses: permission module "cash" (admin/manager). Respons OBJEK/ARRAY telanjang.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Request, Query, HTTPException

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_scope_ids
from schemas import BankAccountCreate, BankAccountUpdate, ReconcilePayload
from services import bank_service

router = APIRouter(prefix="/api")


@router.get("/bank-accounts")
async def list_bank_accounts(request: Request, entity_id: str = Query(None)) -> List[Dict[str, Any]]:
    """Daftar akun kas/bank + saldo terhitung.

    FASE E-7 (E7.4): akun tingkat grup (`entity_id="all"`) sudah TIDAK sah lagi —
    setiap rekening wajib milik satu badan usaha. Akun grup LAMA masih ditampilkan
    (agar bisa dipetakan, bukan hilang diam-diam) tetapi hanya untuk peran
    lintas-entitas, dan layar Kas & Bank menegur agar dimigrasikan.
    """
    actor = await require_permission(request, "cash", "view")
    ctx = await entity_ctx(request)
    entities = resolve_scope_ids(ctx, entity_id)
    or_clauses: List[Dict[str, Any]] = [{"entity_id": {"$in": entities}}]
    if (actor or {}).get("role") in ("admin", "manager"):
        or_clauses.append({"entity_id": {"$in": ["all", "", None]}})
    scope = {"$or": or_clauses}
    return await bank_service.list_accounts(scope=scope)


@router.post("/bank-accounts")
async def create_bank_account(payload: BankAccountCreate, request: Request) -> Dict[str, Any]:
    """Buat akun kas/bank baru."""
    actor = await require_permission(request, "cash", "create")
    ctx = await entity_ctx(request)
    # FASE E-7 (E7.4) — rekening tingkat grup DIHAPUS: setiap rekening wajib milik
    # satu badan usaha, kalau tidak neraca & arus kas per PT tidak pernah utuh.
    from services.cash_entity_service import assert_owned
    payload.entity_id = assert_owned(payload.entity_id or ctx.active_entity_id,
                                     what="Rekening kas/bank")
    try:
        acc = await bank_service.create_account(payload, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "bank_account_created", "bank_account", acc["id"],
                {"name": acc["name"], "type": acc["account_type"]})
    return acc


@router.patch("/bank-accounts/{account_id}")
async def patch_bank_account(account_id: str, payload: BankAccountUpdate, request: Request) -> Dict[str, Any]:
    """Ubah / nonaktifkan akun kas/bank."""
    actor = await require_permission(request, "cash", "create")
    data = payload.model_dump()
    # E7.4 — jangan biarkan rekening "turun pangkat" menjadi milik grup lewat PATCH.
    if data.get("entity_id") is not None:
        from services.cash_entity_service import assert_owned
        data["entity_id"] = assert_owned(data.get("entity_id"), what="Rekening kas/bank")
    acc = await bank_service.update_account(account_id, data)
    if acc is None:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    await audit(actor["name"], "bank_account_updated", "bank_account", account_id, {})
    return acc


@router.get("/bank-accounts/{account_id}/ledger")
async def bank_account_ledger(account_id: str, request: Request) -> Dict[str, Any]:
    """Buku besar (ledger) akun: transaksi + running balance."""
    await require_permission(request, "cash", "view")
    led = await bank_service.account_ledger(account_id)
    if led is None:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return led


@router.post("/cash-transactions/{txn_id}/reconcile")
async def reconcile_cash_transaction(txn_id: str, payload: ReconcilePayload, request: Request) -> Dict[str, Any]:
    """Tandai transaksi kas sebagai terekonsiliasi / belum."""
    actor = await require_permission(request, "cash", "create")
    txn = await bank_service.reconcile_txn(txn_id, payload.reconciled)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    await audit(actor["name"], "cash_transaction_reconciled", "cash_transaction", txn_id,
                {"reconciled": payload.reconciled})
    return txn
