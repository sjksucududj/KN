"""F1b (D-14) — Router **Daftar Harga per Pelanggan**.

  GET    /api/customer-prices?customer_id=&search=       — grid per produk (global·PT·pelanggan·khusus·efektif)
  GET    /api/customer-prices/records?customer_id=&product_id=&status=  — histori record
  GET    /api/customer-prices/quote?customer_id=&product_ids=&quantity= — harga efektif massal (POS/keranjang)
  GET    /api/customer-prices/floor?product_id=&price=                  — batas bawah + apakah butuh persetujuan
  GET    /api/customer-prices/export?customer_id=              — unduh CSV (BOM UTF-8)
  POST   /api/customer-prices                                  — tetapkan harga
  POST   /api/customer-prices/import                           — impor massal (rows / csv_text)
  PATCH  /api/customer-prices/{price_id}                       — ubah harga/masa berlaku
  DELETE /api/customer-prices/{price_id}                       — nonaktifkan (histori tetap)

Akses: permission `pricelist` — admin/manager `manage`, sales `view` (sales perlu tahu
harga langganan pelanggannya, tetapi tidak boleh mengubahnya).

Penjagaan harga: harga di bawah batas bawah (harga PT/HPP) TIDAK langsung berlaku —
router hanya menyimpan record `pending_approval`; keputusannya diambil di layar
**Persetujuan Harga** yang sudah ada (`/api/price-approvals/{id}/approve`).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from dependencies import audit, require_permission
from entity_scope import assert_entity_access, entity_ctx, resolve_list_scope
from schemas_customer_price import (CustomerPriceCreate, CustomerPriceImportIn,
                                    CustomerPricePatch)
from services import customer_price_service as svc
from services import price_guard_service as guard

router = APIRouter(prefix="/api")


def _eid(entity_id: Optional[str], ctx) -> str:
    return entity_id if entity_id and entity_id != "all" else ctx.active_entity_id


def _assert_entity(eid: str, ctx) -> None:
    if eid not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas ini")


@router.get("/customer-prices")
async def customer_price_grid(request: Request, customer_id: str = Query(...),
                              entity_id: Optional[str] = Query(None),
                              search: str = "") -> Dict[str, Any]:
    await require_permission(request, "pricelist", "view")
    ctx = await entity_ctx(request)
    eid = _eid(entity_id, ctx)
    _assert_entity(eid, ctx)
    try:
        return await svc.grid(eid, customer_id, search=search)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/customer-prices/records")
async def customer_price_records(request: Request, customer_id: Optional[str] = Query(None),
                                 product_id: Optional[str] = Query(None),
                                 status: Optional[str] = Query(None),
                                 entity_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "pricelist", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("customer_prices", {}, ctx, entity_id)
    return await svc.list_records(scope, customer_id=customer_id, product_id=product_id,
                                  status=status)


@router.get("/customer-prices/quote")
async def customer_price_quote(request: Request, customer_id: str = Query(...),
                               product_ids: str = Query(""),
                               quantity: Optional[float] = Query(None),
                               include_special: bool = Query(True),
                               entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Harga efektif (harga khusus → pelanggan → PT → global) untuk banyak produk.

    Dipakai POS/keranjang dalam SATU panggilan (dulu satu panggilan per produk ke
    `/price-approvals/effective`) supaya harga di layar SAMA dengan harga yang
    disimpan pesanan.
    """
    await require_permission(request, "pricelist", "view")
    ctx = await entity_ctx(request)
    eid = _eid(entity_id, ctx)
    ids = [p.strip() for p in (product_ids or "").split(",") if p.strip()]
    if not ids:
        return {"customer_id": customer_id, "entity_id": eid, "prices": {}, "count": 0,
                "special_count": 0}
    from db import db
    prods = await db.products.find({"id": {"$in": ids}}, {"_id": 0}).to_list(len(ids) + 1)
    pmap = {p["id"]: p for p in prods}
    prices = await svc.resolve_many(eid, customer_id, ids, pmap,
                                    include_special=include_special,
                                    quantity=quantity)
    return {"customer_id": customer_id, "entity_id": eid, "prices": prices,
            "count": sum(1 for v in prices.values() if v.get("source") == "customer"),
            "special_count": sum(1 for v in prices.values()
                                 if v.get("source") == "special_approval")}


@router.get("/customer-prices/floor")
async def customer_price_floor(request: Request, product_id: str = Query(...),
                               price: Optional[float] = Query(None),
                               entity_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Batas bawah harga untuk satu produk + apakah nominal `price` butuh persetujuan.

    Dipakai form "Tetapkan Harga" agar peringatan yang dilihat user PERSIS sama
    dengan keputusan yang nanti diambil server (satu definisi: price_guard_service).
    """
    await require_permission(request, "pricelist", "view")
    ctx = await entity_ctx(request)
    eid = _eid(entity_id, ctx)
    _assert_entity(eid, ctx)
    from db import db
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    if price is None:
        return await guard.floor_for(eid, product)
    return await guard.evaluate(float(price), eid, product)


@router.get("/customer-prices/export")
async def customer_price_export(request: Request, customer_id: str = Query(...),
                                only_with_price: bool = Query(False),
                                entity_id: Optional[str] = Query(None)) -> Response:
    await require_permission(request, "pricelist", "view")
    ctx = await entity_ctx(request)
    eid = _eid(entity_id, ctx)
    try:
        content, fname = await svc.export_csv(eid, customer_id, only_with_price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/customer-prices")
async def create_customer_price(payload: CustomerPriceCreate,
                                request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    eid = (payload.entity_id or "").strip() or ctx.active_entity_id
    _assert_entity(eid, ctx)
    try:
        rec = await svc.create_price(payload.model_dump(), eid, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "customer_price_created", "customer_price", rec["id"],
                {"entity_id": eid, "customer": rec.get("customer_name"),
                 "product": rec.get("product_name"), "sell_price": rec.get("sell_price"),
                 "valid_from": rec.get("valid_from"),
                 "approval_required": rec.get("approval_required", False),
                 "price_approval_id": rec.get("price_approval_id", "")})
    return rec


@router.post("/customer-prices/import")
async def import_customer_prices(payload: CustomerPriceImportIn,
                                 request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    eid = (payload.entity_id or "").strip() or ctx.active_entity_id
    _assert_entity(eid, ctx)
    rows = [r.model_dump() for r in payload.rows]
    parse_errors: List[str] = []
    if not rows and payload.csv_text:
        rows, parse_errors = svc.parse_csv(payload.csv_text)
    if not rows:
        raise HTTPException(status_code=400,
                            detail="Tidak ada baris harga yang bisa diimpor. "
                                   + (" ".join(parse_errors[:3]) if parse_errors else
                                      "Isi kolom: sku;nama;harga;berlaku_dari;berlaku_sampai;catatan"))
    try:
        res = await svc.import_rows(eid, payload.customer_id, rows, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res["errors"] = (parse_errors + res.get("errors", []))[:50]
    await audit(actor.get("name", ""), "customer_price_imported", "customer_price",
                payload.customer_id, {"applied": res["applied"], "rows": res["total_rows"],
                                      "pending": res.get("pending", 0), "entity_id": eid})
    return res


@router.patch("/customer-prices/{price_id}")
async def patch_customer_price(price_id: str, payload: CustomerPricePatch,
                               request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    rec = await svc.get_record(price_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Harga pelanggan tidak ditemukan")
    assert_entity_access(rec, "customer_prices", ctx)
    try:
        updated = await svc.patch_price(price_id, payload.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "customer_price_updated", "customer_price", price_id,
                payload.model_dump(exclude_none=True))
    return updated


@router.delete("/customer-prices/{price_id}")
async def delete_customer_price(price_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "pricelist", "manage")
    ctx = await entity_ctx(request)
    rec = await svc.get_record(price_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Harga pelanggan tidak ditemukan")
    assert_entity_access(rec, "customer_prices", ctx)
    try:
        res = await svc.deactivate_price(price_id, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor.get("name", ""), "customer_price_deactivated", "customer_price",
                price_id, {"customer": rec.get("customer_name"),
                           "product": rec.get("product_name"),
                           "approval_cancelled": res.get("approval_cancelled", 0)})
    return res
