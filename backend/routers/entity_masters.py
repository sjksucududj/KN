"""entity_masters router (FASE E-4 · E4a/E4d) — MASTER BERLAPIS global → badan usaha.

SATU pintu API untuk semua master yang punya lapisan (syarat pembayaran, kategori
biaya, template dokumen, kebijakan retur, tarif insentif, aturan persetujuan).
Kenapa generik: tanpa ini setiap master butuh 5 endpoint + 1 layar sendiri, dan
aturan "override menang / global tak boleh diubah dari konteks entitas" akan
ditulis ulang 6× dengan 6 versi bug yang berbeda.

Kontrak respons = ARRAY/OBJEK telanjang (kontrak KN3). PATCH pakai `{data:{...}}`.
Aturan lengkap ada di `services/entity_master_service.py`.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request

from dependencies import audit, require_permission
from entity_scope import entity_ctx
from services import entity_master_service as ems
from services import master_registry as mreg

router = APIRouter(prefix="/api")


@router.get("/entity-masters")
async def list_master_groups(request: Request) -> List[Dict[str, Any]]:
    """Ringkasan tiap kelompok master (untuk kartu pilihan di layar)."""
    await require_permission(request, "settings", "view")
    ctx = await entity_ctx(request)
    return await ems.groups_summary(ctx)


@router.get("/entity-masters/{kind}")
async def list_master_rows(kind: str, request: Request,
                           entity_id: Optional[str] = Query(None),
                           include_inactive: bool = Query(False)) -> Dict[str, Any]:
    """Baris yang BERLAKU untuk satu badan usaha: global + override-nya, berlencana asal."""
    await require_permission(request, "settings", "view")
    ctx = await entity_ctx(request)
    return await ems.list_layered(kind, ctx, entity_id, include_inactive)


@router.get("/entity-masters/{kind}/effective")
async def list_master_effective(kind: str, request: Request,
                                entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Baris EFEKTIF (tanpa kembar) — bentuk yang dipakai dropdown & laporan."""
    await require_permission(request, "settings", "view")
    ctx = await entity_ctx(request)
    target = entity_id or ctx.active_entity_id
    return await ems.effective_rows(kind, target)


@router.post("/entity-masters/{kind}")
async def create_master_row(kind: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "settings", "manage")
    ctx = await entity_ctx(request)
    row = await ems.create(kind, payload or {}, ctx)
    # FASE L — kosakata yang baru ditambah HARUS langsung terasa di `/api/enums`
    # & penyaring layar. Tanpa membuang cache, lini baru baru muncul setelah
    # backend restart (pelajaran FASE E-1 `invalidate_entity_code`).
    mreg.invalidate(kind)
    await audit(actor["name"], "entity_master_created", kind, row.get("id", ""),
                {"entity_id": row.get("entity_id"), "key": row.get(ems.spec(kind).key_field)})
    return row


@router.patch("/entity-masters/{kind}/{row_id}")
async def update_master_row(kind: str, row_id: str, payload: Dict[str, Any],
                            request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "settings", "manage")
    ctx = await entity_ctx(request)
    data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
    row = await ems.patch(kind, row_id, data or {}, ctx)
    mreg.invalidate(kind)
    await audit(actor["name"], "entity_master_updated", kind, row_id, data or {})
    return row


@router.post("/entity-masters/{kind}/{row_id}/override")
async def override_master_row(kind: str, row_id: str, request: Request) -> Dict[str, Any]:
    """Salin baris global menjadi baris khusus badan usaha aktif."""
    actor = await require_permission(request, "settings", "manage")
    ctx = await entity_ctx(request)
    row = await ems.override(kind, row_id, ctx)
    mreg.invalidate(kind)
    await audit(actor["name"], "entity_master_overridden", kind, row.get("id", ""),
                {"source_id": row_id, "entity_id": row.get("entity_id")})
    return row


@router.delete("/entity-masters/{kind}/{row_id}")
async def revert_master_row(kind: str, row_id: str, request: Request) -> Dict[str, Any]:
    """Lepas override badan usaha → nilai kembali mengikuti baris global."""
    actor = await require_permission(request, "settings", "manage")
    ctx = await entity_ctx(request)
    res = await ems.revert(kind, row_id, ctx)
    mreg.invalidate(kind)
    await audit(actor["name"], "entity_master_reverted", kind, row_id,
                {"key": res.get("key")})
    return res
