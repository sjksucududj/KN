"""EPIC7-C — Chart of Accounts + General Ledger router.

Akses: permission module "accounting" (admin/manager). Respons OBJEK/ARRAY
telanjang (kontrak KN3). Jurnal otomatis diturunkan dari SSOT (sales_orders,
cash_transactions) via /api/gl/sync — idempotent.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas_finance import (
    GLAccountCreate, GLAccountUpdate, JournalEntryCreate, SuspenseReclassInput,
)
from services import gl_service
from pagination import is_paged, get_page_params

router = APIRouter(prefix="/api")


async def _gl_scope(request: Request, entity_id: Optional[str]) -> Dict[str, Any]:
    """Fragmen filter entitas untuk buku/jurnal (default: entitas aktif)."""
    ctx = await entity_ctx(request)
    return resolve_list_scope("journal_entries", {}, ctx, entity_id)


# ─── Chart of Accounts ───────────────────────────────────────────────────────

@router.get("/gl/accounts")
async def list_gl_accounts(request: Request, active_only: bool = Query(False),
                           entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Daftar bagan akun (Chart of Accounts).

    - Tanpa `entity_id` → hanya template global (SHARED).
    - Dengan `entity_id` → effective view: override PT menang atas template per-code,
      plus akun khusus PT tersebut. Aman: posting JE tetap resolve by-code global.
    """
    await require_permission(request, "accounting", "view")
    return await gl_service.list_accounts(active_only=active_only, entity_id=entity_id)


@router.get("/gl/cash-accounts")
async def list_cash_accounts(request: Request) -> List[Dict[str, Any]]:
    """R5.3 — daftar akun Kas/Bank (kode 1-11xx, postable) untuk pemilih refund tunai.
    Dipakai modal settle retur jual & supplier-accept retur beli."""
    await require_permission(request, "sales_return", "view")
    accts = await gl_service.list_accounts(active_only=True)
    out = [
        {"code": a.get("code"), "name": a.get("name")}
        for a in accts
        if str(a.get("code", "")).startswith("1-11") and a.get("is_postable", True)
    ]
    return out or [{"code": "1-1100", "name": "Kas Besar / Bank"}, {"code": "1-1110", "name": "Kas Kecil"}]



@router.post("/gl/accounts")
async def create_gl_account(payload: GLAccountCreate, request: Request,
                            entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Buat akun baru. `entity_id` = None → akun template global; `entity_id=<id>`
    → akun khusus PT (bisa akun baru atau override akun template)."""
    actor = await require_permission(request, "accounting", "manage")
    try:
        acc = await gl_service.create_account(payload, entity_id=entity_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "gl_account_created", "gl_account", acc["code"],
                {"name": acc["name"], "type": acc["type"], "entity_id": entity_id})
    return acc


@router.patch("/gl/accounts/{code}")
async def update_gl_account(code: str, payload: GLAccountUpdate, request: Request,
                            entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Ubah / nonaktifkan akun. Dengan `entity_id` → target override PT (buat baru
    kalau belum ada). Tanpa `entity_id` → akun template global."""
    actor = await require_permission(request, "accounting", "manage")
    acc = await gl_service.update_account(code, payload.model_dump(), entity_id=entity_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    await audit(actor["name"], "gl_account_updated", "gl_account", code,
                {"entity_id": entity_id})
    return acc


@router.delete("/gl/accounts/{code}")
async def delete_gl_account(code: str, request: Request,
                            entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Hapus akun. Untuk override PT (`entity_id=<id>`), hanya menghapus override
    (template global tetap). Untuk akun template, cek unused."""
    actor = await require_permission(request, "accounting", "manage")
    try:
        await gl_service.delete_account(code, entity_id=entity_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "gl_account_deleted", "gl_account", code,
                {"entity_id": entity_id})
    return {"ok": True, "code": code, "entity_id": entity_id}


@router.get("/gl/accounts/{code}/ledger")
async def gl_account_ledger(code: str, request: Request, as_of: Optional[str] = Query(None),
                            entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Buku besar 1 akun (mutasi + running balance) — per entitas."""
    await require_permission(request, "accounting", "view")
    scope = await _gl_scope(request, entity_id)
    led = await gl_service.account_ledger(code, as_of=as_of, scope=scope)
    if led is None:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return led


# ─── Journal Entries ─────────────────────────────────────────────────────────

@router.get("/gl/journal")
async def list_journal(
    request: Request,
    source: Optional[str] = Query(None),
    account_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
) -> Any:
    """Daftar jurnal (filter sumber/akun/status) — ter-scope entitas.

    P2 — paginasi OPT-IN (?page/?page_size). Jurnal adalah koleksi yang tumbuh PALING
    cepat (tiap transaksi memposting entri), dan sebelum ini daftarnya dipotong keras di
    500 baris TANPA halaman berikutnya: entri ke-501 tidak bisa dijangkau dari layar sama
    sekali. Tanpa parameter halaman, bentuk responsnya tetap array telanjang.
    """
    await require_permission(request, "accounting", "view")
    scope = await _gl_scope(request, entity_id)
    if is_paged(request):
        page, page_size, q, _sort = get_page_params(request)
        return await gl_service.list_entries_paged(
            source=source, account_code=account_code, status=status, scope=scope,
            page=page, page_size=page_size, q=q)
    return await gl_service.list_entries(source=source, account_code=account_code,
                                         status=status, scope=scope)


@router.post("/gl/journal")
async def create_journal(payload: JournalEntryCreate, request: Request) -> Dict[str, Any]:
    """Buat jurnal manual (double-entry seimbang) — ter-stamp entitas aktif."""
    actor = await require_permission(request, "accounting", "create")
    ctx = await entity_ctx(request)
    # FASE G-5 — izin posting mundur ke periode tertutup (period.backdate).
    from dependencies import permission_matrix
    matrix = await permission_matrix()
    can_backdate = "backdate" in matrix.get(actor.get("role"), {}).get("period", [])
    try:
        je = await gl_service.create_manual_entry(payload, actor,
                                                  entity_id=ctx.active_entity_id,
                                                  can_backdate=can_backdate)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "journal_entry_created", "journal_entry", je["id"],
                {"number": je["number"], "total": je["total_debit"]})
    return je


@router.get("/gl/journal/{entry_id}")
async def get_journal(entry_id: str, request: Request) -> Dict[str, Any]:
    """Detail satu jurnal."""
    await require_permission(request, "accounting", "view")
    ctx = await entity_ctx(request)
    je = await gl_service.get_entry(entry_id)
    if je is None:
        raise HTTPException(status_code=404, detail="Jurnal tidak ditemukan")
    assert_entity_access(je, "journal_entries", ctx)
    return je


@router.post("/gl/journal/{entry_id}/void")
async def void_journal(entry_id: str, request: Request) -> Dict[str, Any]:
    """Void jurnal manual."""
    actor = await require_permission(request, "accounting", "void")
    try:
        je = await gl_service.void_entry(entry_id, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if je is None:
        raise HTTPException(status_code=404, detail="Jurnal tidak ditemukan")
    await audit(actor["name"], "journal_entry_voided", "journal_entry", entry_id, {})
    return je


# ─── Sync (auto-posting) & Reports ───────────────────────────────────────────

@router.post("/gl/sync")
async def sync_journals(request: Request) -> Dict[str, Any]:
    """Posting otomatis (idempotent) dari SSOT yang belum berjurnal."""
    actor = await require_permission(request, "accounting", "manage")
    result = await gl_service.backfill_journals()
    await audit(actor["name"], "gl_sync", "journal_entry", "batch", result)
    return result


@router.get("/gl/trial-balance")
async def trial_balance(request: Request, as_of: Optional[str] = Query(None),
                        entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Neraca saldo (trial balance) — buku terpisah per entitas."""
    await require_permission(request, "accounting", "view")
    scope = await _gl_scope(request, entity_id)
    return await gl_service.trial_balance(as_of=as_of, scope=scope)


@router.get("/gl/summary")
async def gl_summary(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """KPI ringkas GL (jumlah jurnal, total debit/kredit, seimbang?) — per entitas."""
    await require_permission(request, "accounting", "view")
    scope = await _gl_scope(request, entity_id)
    return await gl_service.gl_summary(scope=scope)


@router.get("/gl/consolidation")
async def gl_consolidation(request: Request, as_of: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Konsolidasi Grup vs Per-PT — ringkasan P&L + neraca tiap entitas + gabungan.

    Memakai buku terpisah per entitas (F0-E). Cakupan = entitas yang diizinkan
    user (admin/manager lintas-PT = semua entitas aktif)."""
    await require_permission(request, "accounting", "view")
    ctx = await entity_ctx(request)
    return await gl_service.consolidation(ctx.allowed_entity_ids, as_of=as_of)


@router.get("/gl/inventory-reconciliation")
async def gl_inventory_reconciliation(request: Request) -> Dict[str, Any]:
    """Gelombang 1 F-3 — nilai persediaan subledger (rolls) vs saldo GL per entitas."""
    await require_permission(request, "accounting", "view")
    return await gl_service.inventory_reconciliation()


@router.post("/gl/inventory-opening-balance")
async def gl_inventory_opening_balance(request: Request,
                                       reason: str = Query("", max_length=500)) -> Dict[str, Any]:
    """Gelombang 1 F-3 — posting saldo awal / true-up persediaan (per entitas, idempotent harian).

    FASE P5 — `reason` (opsional di API, WAJIB di layar): true-up menyamakan GL Persediaan
    dengan nilai fisik roll, artinya ia MENERBITKAN jurnal terhadap ekuitas saldo awal.
    Alasannya ikut tercatat di Jejak Audit supaya selisih yang di-posting bisa
    dipertanggungjawabkan saat tutup buku.
    """
    actor = await require_permission(request, "accounting", "manage")
    result = await gl_service.post_inventory_opening_balance(actor.get("name", "system"))
    await audit(actor["name"], "inventory_opening_posted", "journal_entry", "batch",
                {**result, "reason": (reason or "").strip()})
    return result


# ─── Gelombang 3 F-8 — Suspense (1-9999): laporan & reklasifikasi ────────────

@router.get("/gl/suspense")
async def gl_suspense(request: Request, entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Saldo & daftar jurnal yang menyentuh akun Suspense (wajib nol sebelum tutup buku)."""
    await require_permission(request, "accounting", "view")
    scope = await _gl_scope(request, entity_id)
    return await gl_service.suspense_report(scope=scope)


@router.post("/gl/suspense/reclass")
async def gl_suspense_reclass(payload: SuspenseReclassInput, request: Request) -> Dict[str, Any]:
    """Reklasifikasi saldo Suspense ke akun yang benar (JE seimbang, per entitas)."""
    actor = await require_permission(request, "accounting", "manage")
    ctx = await entity_ctx(request)
    eid = payload.entity_id or ctx.active_entity_id
    if not eid or eid == "all":
        raise HTTPException(status_code=400, detail="Pilih entitas (PT) spesifik untuk reklasifikasi suspense.")
    if eid not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke entitas ini.")
    try:
        je = await gl_service.reclass_suspense(
            amount=payload.amount, side=payload.side, target_account=payload.target_account,
            note=payload.note, entity_id=eid, actor_name=actor.get("name", "system"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "suspense_reclass", "journal_entry", je["id"],
                {"amount": payload.amount, "target": payload.target_account, "side": payload.side})
    return je
