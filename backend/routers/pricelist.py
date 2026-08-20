"""F1a — Pricelist per-entitas router (harga jual per-PT, histori & tanggal efektif).

Akses: permission module "pricelist" (admin/manager: view+manage; sales: view).
Kontrak respons: list = ARRAY langsung (records), grid = objek {rows,...}.
Koleksi `entity_prices` SCOPED via entity_id (entity_scope).

FASE E-4 (E4.7) menambah: grid **tiga angka + asal harga**, tombol
**kembalikan ke harga global** (melepas override tanpa menghapus riwayat), serta
**ekspor/impor CSV** di server (bukan loop satu-satu dari layar).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Query, Response

from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import EntityPriceCreate, EntityPriceImportIn, EntityPricePatch
from services import pricelist_service as svc

router = APIRouter(prefix="/api")


def _assert_entity(eid: str, ctx) -> None:
    if eid not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas ini")


@router.get("/pricelist")
async def pricelist_grid(request: Request, entity_id: Optional[str] = Query(None),
                         search: str = "") -> Dict[str, Any]:
    """Grid pricelist: satu baris per produk (harga global + harga entitas + efektif)."""
    await require_permission(request, "pricelist", "view")
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id
    _assert_entity(eid, ctx)
    rows = await svc.pricelist_grid(eid, search=search)
    return {"entity_id": eid, "rows": rows, "count": len(rows),
            "summary": await svc.grid_summary(eid, rows)}


@router.get("/pricelist/records")
async def pricelist_records(request: Request, product_id: str = None,
                            entity_id: str = None) -> List[Dict[str, Any]]:
    """Histori harga (semua record) ter-scope entitas, filter opsional per produk."""
    await require_permission(request, "pricelist", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("entity_prices", {}, ctx, entity_id)
    return await svc.list_records(scope, product_id=product_id)


@router.get("/pricelist/export")
async def pricelist_export(request: Request, entity_id: Optional[str] = Query(None),
                           only_with_price: bool = Query(False)) -> Response:
    """Unduh CSV harga badan usaha (siap dibuka Excel, pemisah `;`)."""
    await require_permission(request, "pricelist", "view")
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id
    _assert_entity(eid, ctx)
    content, fname = await svc.export_csv(eid, only_with_price)
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/pricelist/import")
async def pricelist_import(payload: EntityPriceImportIn, request: Request) -> Dict[str, Any]:
    """Impor massal harga badan usaha dari CSV (atau baris terurai).

    Baris tanpa kolom harga DILEWATI (bukan dianggap nol) — supaya satu impor
    tidak diam-diam menghapus harga khusus ribuan produk.
    """
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    eid = (payload.entity_id or "").strip() or ctx.active_entity_id
    _assert_entity(eid, ctx)
    rows = [r.model_dump() for r in payload.rows]
    parse_errors: List[str] = []
    if not rows and payload.csv_text:
        rows, parse_errors = svc.parse_csv(payload.csv_text)
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="Tidak ada baris harga yang bisa diimpor. "
                   + (" ".join(parse_errors[:3]) if parse_errors else
                      "Isi kolom: sku;nama_produk;harga_global;harga_entitas;"
                      "berlaku_dari;berlaku_sampai;catatan"))
    res = await svc.import_rows(eid, rows, actor.get("name", ""))
    res["errors"] = (parse_errors + res.get("errors", []))[:50]
    await audit(actor.get("name", ""), "entity_price_imported", "entity_price", eid,
                {"applied": res["applied"], "rows": res["total_rows"], "entity_id": eid})
    return res


@router.delete("/pricelist/override/{product_id}")
async def revert_to_global(product_id: str, request: Request,
                           entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Kembalikan satu produk ke HARGA GLOBAL untuk badan usaha ini.

    Riwayat tidak dihapus (record dinonaktifkan) supaya angka pada pesanan lama
    tetap bisa dijelaskan.
    """
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id
    _assert_entity(eid, ctx)
    try:
        res = await svc.remove_override(eid, product_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "entity_price_reverted_to_global", "entity_price",
                product_id, {"entity_id": eid, "deactivated": res["deactivated"],
                             "product": res.get("product_name", "")})
    return res


@router.post("/pricelist")
async def create_price(payload: EntityPriceCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    eid = (payload.entity_id or "").strip() or ctx.active_entity_id
    _assert_entity(eid, ctx)
    try:
        rec = await svc.create_price(payload.model_dump(), eid, actor.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "entity_price_created", "entity_price", rec["id"], {
        "entity_id": eid, "product": rec.get("product_name"),
        "sell_price": rec.get("sell_price"), "valid_from": rec.get("valid_from"),
    })
    return rec


@router.patch("/pricelist/{price_id}")
async def patch_price(price_id: str, payload: EntityPricePatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    rec = await svc.get_record(price_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Harga tidak ditemukan")
    assert_entity_access(rec, "entity_prices", ctx)
    try:
        updated = await svc.patch_price(price_id, payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "entity_price_updated", "entity_price", price_id,
                payload.model_dump(exclude_none=True))
    return updated


@router.delete("/pricelist/{price_id}")
async def delete_price(price_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    rec = await svc.get_record(price_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Harga tidak ditemukan")
    assert_entity_access(rec, "entity_prices", ctx)
    try:
        res = await svc.deactivate_price(price_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "entity_price_deactivated", "entity_price", price_id,
                {"product": rec.get("product_name")})
    return res
