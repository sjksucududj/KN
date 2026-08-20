"""FINANCE — Konsolidasi Grup + Eliminasi Intercompany router.

Akses: modul `accounting` (view untuk baca; manage untuk tulis eliminasi).
Respons OBJEK/ARRAY telanjang (kontrak KN3). Grup = semua entitas dalam cakupan
baca user (allowed_entity_ids).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel

from dependencies import require_permission, audit
from entity_scope import entity_ctx
from services import consolidation_service as cons

router = APIRouter(prefix="/api")


class ElimLine(BaseModel):
    account_code: str
    debit: Optional[float] = 0
    credit: Optional[float] = 0
    description: Optional[str] = ""


class ElimCreate(BaseModel):
    name: Optional[str] = "Eliminasi Intercompany"
    entity_from: Optional[str] = None
    entity_to: Optional[str] = None
    effective_date: Optional[str] = None
    note: Optional[str] = ""
    lines: List[ElimLine]


async def _entity_ids(request: Request) -> List[str]:
    ctx = await entity_ctx(request)
    return list(ctx.allowed_entity_ids)


@router.get("/finance/consolidation/summary")
async def consolidation_summary(
    request: Request,
    year: Optional[int] = Query(None),
    as_of: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Matriks Per-PT + Eliminasi + Konsolidasi (Laba-Rugi tahun & Neraca as_of)."""
    await require_permission(request, "accounting", "view")
    y = int(year) if year else datetime.now(timezone.utc).year
    ao = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ids = await _entity_ids(request)
    return await cons.summary(ids, y, ao)


@router.get("/finance/consolidation/eliminations")
async def list_eliminations(request: Request) -> List[Dict[str, Any]]:
    await require_permission(request, "accounting", "view")
    return await cons.list_eliminations()


@router.post("/finance/consolidation/eliminations")
async def create_elimination(payload: ElimCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "accounting", "manage")
    try:
        rec = await cons.create_elimination(payload.model_dump(), actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "ic_elimination_created", "ic_elimination", rec["id"],
                {"name": rec["name"], "balanced": rec["balanced"]})
    return rec


@router.delete("/finance/consolidation/eliminations/{elim_id}")
async def delete_elimination(elim_id: str, request: Request,
                             reason: str = Query("", max_length=500)) -> Dict[str, Any]:
    # FASE P5 — `reason` (opsional di API, WAJIB di layar): menghapus entri eliminasi
    # mengubah laporan konsolidasi grup, jadi alasannya harus bisa dibaca ulang di
    # Jejak Audit. Sebelumnya audit hanya mencatat "dihapus" tanpa sebab.
    actor = await require_permission(request, "accounting", "manage")
    ok = await cons.delete_elimination(elim_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Entri eliminasi tidak ditemukan.")
    await audit(actor["name"], "ic_elimination_deleted", "ic_elimination", elim_id,
                {"reason": (reason or "").strip()})
    return {"deleted": True}


@router.get("/finance/consolidation/ic-candidates")
async def ic_candidates(request: Request, as_of: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Auto-deteksi akun intercompany + saldo per-PT + usulan baris eliminasi."""
    await require_permission(request, "accounting", "view")
    ao = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ids = await _entity_ids(request)
    return await cons.ic_candidates(ids, ao)


@router.post("/finance/consolidation/eliminations/sync-from-pairs")
async def sync_ic_eliminations_from_pairs(
    request: Request, as_of: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """M-3 — Sinkronisasi entri eliminasi dari `intercompany_pair_id` JE (idempotent).

    Untuk setiap pasangan JE (source+dest) inter-company transfer yang belum
    memiliki entri eliminasi, buat auto-entry `intercompany_eliminations` dengan
    `auto_generated=True` dan `source_pair_id=<pair_id>`.
    """
    actor = await require_permission(request, "accounting", "manage")
    ao = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = await cons.sync_ic_eliminations_from_pairs(as_of=ao)
    await audit(actor["name"], "ic_elimination_auto_synced", "ic_elimination", "",
                {"created": result["created"], "skipped": result["skipped_existing"],
                 "pairs_seen": result["pairs_seen"]})
    return result


@router.post("/consolidation/sync-g6")
async def sync_g6_ic_eliminations(
    request: Request, as_of: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """FASE G-6 (US7) — Sinkronisasi eliminasi transaksi antar-PT (idempotent).

    Untuk setiap pair G-6 (`interco_transactions.pair_id`) yang belum tereliminasi,
    buat SATU entri seimbang yang mengeliminasi (a) pendapatan intra-grup +
    HPP + *unrealized profit* di persediaan pembeli, dan (b) sisa IC-AR/IC-AP.
    Idempotent lewat `source_g6_pair_id`.
    """
    actor = await require_permission(request, "accounting", "manage")
    ao = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = await cons.sync_g6_ic_eliminations(as_of=ao)
    await audit(actor["name"], "g6_ic_elimination_synced", "ic_elimination", "",
                {"created": result["created"], "skipped": result["skipped_existing"],
                 "pairs_seen": result["pairs_seen"]})
    return result
