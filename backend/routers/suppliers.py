"""Suppliers router (Fase 3 — Procurement / Master Pemasok).

Master supplier menggantikan supplier sebagai STRING di purchase_orders.
Koleksi kanonik: `suppliers` (prefix sup_). Lihat ENTITY_REGISTRY.md.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from pagination import is_paged, get_page_params, build_search, merge_query, fetch_page, envelope
from schemas import SupplierCreate, SupplierPriceListCreate, GenericPatch
from services.supplier_service import resolve_price, compute_scorecard, supplier_360
from services.return_policy_service import (
    normalize_supplier_policy, resolve_supplier_return_policy, ORIGIN_TYPES,
)

router = APIRouter(prefix="/api")


async def _next_supplier_code() -> str:
    """Number series SUP-NNNNN (cegah duplikat via max existing)."""
    last = await db.suppliers.find_one({}, {"_id": 0, "code": 1}, sort=[("code", -1)])
    n = 0
    if last and isinstance(last.get("code"), str) and last["code"].startswith("SUP-"):
        try:
            n = int(last["code"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.suppliers.count_documents({})
    else:
        n = await db.suppliers.count_documents({})
    return f"SUP-{n + 1:05d}"


@router.get("/suppliers")
async def list_suppliers(request: Request, entity_id: str = None, status: str = None) -> Any:
    """List supplier (optional filter entitas & status). Opt-in paginasi (?page/?page_size)."""
    await require_permission(request, "supplier", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    query = resolve_list_scope("suppliers", query, ctx, entity_id)
    if is_paged(request):
        page, page_size, q, _sort = get_page_params(request)
        if q:
            query = merge_query(query, build_search(q, ["name", "code", "pic_name", "city", "npwp", "goods_type"]))
        items, total = await fetch_page(db.suppliers, query, page, page_size, sort_field="created_at", sort_dir=-1)
        return envelope(items, total, page, page_size)
    rows = await db.suppliers.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.post("/suppliers")
async def create_supplier(payload: SupplierCreate, request: Request) -> Dict[str, Any]:
    """Buat master supplier baru."""
    actor = await require_permission(request, "supplier", "create")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama supplier wajib diisi")
    # FASE E-7 (E7.7) — pemasok bertipe "Entitas grup" DISIAPKAN OTOMATIS
    # (`services/group_partner_service.sync_group_entity_suppliers`). Membuat baris kedua
    # secara manual akan memecah hutang antar-PT menjadi dua dan membuat saldo pasangan
    # PT tidak lagi cocok — jadi ditolak dengan menunjuk baris yang benar.
    from services import group_partner_service as _grp
    await _grp.assert_new_supplier_allowed(
        payload.name, payload.npwp,
        host_entity_id=payload.entity_id or ctx.active_entity_id)

    code = await _next_supplier_code()
    origin_type = (payload.origin_type or "local").strip().lower()
    if origin_type not in ORIGIN_TYPES:
        origin_type = "local"
    return_policy = normalize_supplier_policy(
        payload.return_policy.dict() if payload.return_policy else None)
    doc = {
        "id": new_id("sup"),
        "code": code,
        "name": payload.name.strip(),
        "npwp": payload.npwp.strip(),
        "pic_name": payload.pic_name.strip(),
        "phone": payload.phone.strip(),
        "email": payload.email.strip(),
        "address": payload.address.strip(),
        "city": payload.city.strip(),
        "goods_type": payload.goods_type.strip(),
        "payment_term_code": payload.payment_term_code,
        "lead_time_days": int(payload.lead_time_days or 0),
        "entity_id": payload.entity_id or ctx.active_entity_id,
        "notes": payload.notes,
        "status": "active",
        # ── R0 — Origin + Return Policy ──
        "origin_type": origin_type,
        "country": (payload.country or "").strip(),
        "return_policy": return_policy,
        "created_by": payload.created_by,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.suppliers.insert_one(doc)
    await audit(actor["name"], "supplier_created", "supplier", doc["id"],
                {"code": code, "name": doc["name"], "npwp": doc["npwp"],
                 "origin_type": origin_type})
    return safe_doc(doc)


@router.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: str, request: Request) -> Dict[str, Any]:
    """Detail supplier + ringkasan PO terkait."""
    await require_permission(request, "supplier", "view")
    ctx = await entity_ctx(request)
    sup = safe_doc(await db.suppliers.find_one({"id": supplier_id}, {"_id": 0}))
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
    assert_entity_access(sup, "suppliers", ctx)
    pos = await db.purchase_orders.find(
        {"supplier_id": supplier_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    sup["purchase_orders"] = pos
    sup["po_count"] = len(pos)
    sup["po_total_value"] = round(sum(float(p.get("total_amount", 0) or 0) for p in pos), 2)
    return sup


@router.patch("/suppliers/{supplier_id}")
async def update_supplier(supplier_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    """Update field supplier (whitelist)."""
    actor = await require_permission(request, "supplier", "update")
    sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
    allowed = {"name", "npwp", "pic_name", "phone", "email", "address", "city",
               "goods_type", "payment_term_code", "lead_time_days", "entity_id", "notes", "status",
               "origin_type", "country", "return_policy"}
    updates = {k: v for k, v in (payload.data or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    if "lead_time_days" in updates:
        try:
            updates["lead_time_days"] = int(updates["lead_time_days"] or 0)
        except (ValueError, TypeError):
            updates["lead_time_days"] = 0
    if "origin_type" in updates:
        ot = str(updates["origin_type"] or "local").strip().lower()
        updates["origin_type"] = ot if ot in ORIGIN_TYPES else "local"
    if "return_policy" in updates:
        updates["return_policy"] = normalize_supplier_policy(updates.get("return_policy"))
    # FASE E-7 (E7.7) — dua pagar pada PATCH:
    #  (a) baris pemasok bertipe "Entitas grup" adalah CERMIN `business_entities`;
    #      identitasnya diubah dari layar Badan Usaha, bukan dari layar Pemasok
    #      (kalau tidak, cermin dan aslinya berbeda dan pagar PO ikut salah menilai);
    #  (b) pemasok biasa tidak boleh "berubah menjadi" badan usaha grup lewat rename.
    if sup.get("partner_kind") == "entity" or sup.get("group_entity_id"):
        blocked = {"name", "npwp", "entity_id"} & set(updates.keys())
        if blocked:
            raise HTTPException(
                status_code=409,
                detail=(f"“{sup.get('name', '')}” adalah cermin badan usaha grup, jadi "
                        f"{', '.join(sorted(blocked))} diubah dari menu Badan Usaha & Akses "
                        f"(bukan dari layar Pemasok) supaya identitasnya tidak pernah "
                        f"berbeda dengan aslinya."))
    elif "name" in updates or "npwp" in updates:
        from services import group_partner_service as _grp
        await _grp.assert_new_supplier_allowed(
            updates.get("name", sup.get("name", "")),
            updates.get("npwp", sup.get("npwp", "")),
            host_entity_id=sup.get("entity_id", ""))
    updates["updated_at"] = now_iso()
    updated = await db.suppliers.find_one_and_update(
        {"id": supplier_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(actor["name"], "supplier_updated", "supplier", supplier_id, updates)
    return safe_doc(updated)


@router.delete("/suppliers/{supplier_id}")
async def deactivate_supplier(supplier_id: str, request: Request) -> Dict[str, Any]:
    """Nonaktifkan supplier (soft delete → status inactive)."""
    actor = await require_permission(request, "supplier", "delete")
    sup = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
    # FASE E-7 (E7.7) — baris pemasok bertipe "Entitas grup" adalah CERMIN
    # `business_entities`. Menonaktifkannya dari layar Pemasok akan membuat cermin
    # berbeda dengan aslinya: badan usahanya masih hidup, tetapi hutang-piutang
    # antar-PT-nya hilang dari layar pembelian. Status baris ini hanya ikut status
    # badan usahanya (disinkronkan `sync_group_entity_suppliers`).
    if sup.get("partner_kind") == "entity" or sup.get("group_entity_id"):
        raise HTTPException(
            status_code=409,
            detail=(f"“{sup.get('name', '')}” adalah cermin badan usaha di dalam grup, "
                    f"jadi tidak dinonaktifkan dari layar Pemasok. Status barisnya "
                    f"mengikuti status badan usahanya — ubah di menu "
                    f"**Badan Usaha & Akses** bila badan usaha itu memang berhenti "
                    f"beroperasi."))
    updated = await db.suppliers.find_one_and_update(
        {"id": supplier_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(actor["name"], "supplier_deactivated", "supplier", supplier_id, {})
    return safe_doc(updated)


# ─── Depth #3 — Supplier Price-List (koleksi supplier_price_lists, prefix spl_) ─

@router.get("/suppliers/{supplier_id}/price-list")
async def list_supplier_price_list(supplier_id: str, request: Request,
                                   include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Daftar harga (price-list) milik supplier."""
    await require_permission(request, "supplier", "view")
    if not await db.suppliers.find_one({"id": supplier_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
    query: Dict[str, Any] = {"supplier_id": supplier_id}
    if not include_inactive:
        query["status"] = "active"
    rows = await db.supplier_price_lists.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.post("/suppliers/{supplier_id}/price-list")
async def create_supplier_price(supplier_id: str, payload: SupplierPriceListCreate,
                                request: Request) -> Dict[str, Any]:
    """Tambah entri harga beli untuk (supplier, product). Unit default = base_unit produk."""
    actor = await require_permission(request, "supplier", "update")
    supplier = safe_doc(await db.suppliers.find_one({"id": supplier_id}, {"_id": 0}))
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
    product = safe_doc(await db.products.find_one({"id": payload.product_id}, {"_id": 0}))
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    if float(payload.price or 0) <= 0:
        raise HTTPException(status_code=400, detail="Harga harus lebih dari 0")

    unit = (payload.unit or "").strip() or product.get("base_unit", "meter")
    doc = {
        "id": new_id("spl"),
        "supplier_id": supplier_id,
        "supplier_name": supplier.get("name", ""),
        "product_id": product["id"],
        "sku": product.get("sku", ""),
        "product_name": product.get("name", ""),
        "price": round(float(payload.price), 2),
        "unit": unit,
        "min_qty": round(float(payload.min_qty or 0), 2),
        "lead_time_days": int(payload.lead_time_days or 0),
        "valid_from": payload.valid_from or "",
        "valid_until": payload.valid_until or "",
        "currency": payload.currency or "IDR",
        "entity_id": supplier.get("entity_id", DEFAULT_ENTITY_ID),
        "notes": payload.notes or "",
        "status": "active",
        "created_by": payload.created_by or actor["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.supplier_price_lists.insert_one(doc)
    await audit(actor["name"], "supplier_price_created", "supplier", supplier_id,
                {"product": product.get("sku"), "price": doc["price"], "unit": unit})
    return safe_doc(doc)


@router.patch("/supplier-price-list/{entry_id}")
async def update_supplier_price(entry_id: str, payload: GenericPatch,
                                request: Request) -> Dict[str, Any]:
    """Update entri price-list (whitelist field)."""
    actor = await require_permission(request, "supplier", "update")
    entry = await db.supplier_price_lists.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entri price-list tidak ditemukan")
    allowed = {"price", "unit", "min_qty", "lead_time_days", "valid_from",
               "valid_until", "currency", "notes", "status"}
    updates = {k: v for k, v in (payload.data or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    if "price" in updates:
        updates["price"] = round(float(updates["price"] or 0), 2)
    if "min_qty" in updates:
        updates["min_qty"] = round(float(updates["min_qty"] or 0), 2)
    if "lead_time_days" in updates:
        try:
            updates["lead_time_days"] = int(updates["lead_time_days"] or 0)
        except (ValueError, TypeError):
            updates["lead_time_days"] = 0
    updates["updated_at"] = now_iso()
    updated = await db.supplier_price_lists.find_one_and_update(
        {"id": entry_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "supplier_price_updated", "supplier",
                entry.get("supplier_id", ""), {"entry_id": entry_id, **updates})
    return safe_doc(updated)


@router.delete("/supplier-price-list/{entry_id}")
async def deactivate_supplier_price(entry_id: str, request: Request) -> Dict[str, Any]:
    """Nonaktifkan entri price-list (soft delete → status inactive)."""
    actor = await require_permission(request, "supplier", "update")
    entry = await db.supplier_price_lists.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entri price-list tidak ditemukan")
    updated = await db.supplier_price_lists.find_one_and_update(
        {"id": entry_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "supplier_price_deactivated", "supplier",
                entry.get("supplier_id", ""), {"entry_id": entry_id})
    return safe_doc(updated)


@router.get("/supplier-price-list/resolve")
async def resolve_supplier_price(request: Request, supplier_id: str = "",
                                 product_id: str = "", qty: float = 0.0) -> Dict[str, Any]:
    """Resolusi harga beli terbaik (auto-isi PO/PR). UOM mengikuti entri/produk."""
    await require_permission(request, "supplier", "view")
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id wajib diisi")
    return await resolve_price(supplier_id, product_id, qty)


@router.get("/suppliers/{supplier_id}/scorecard")
async def get_supplier_scorecard(supplier_id: str, request: Request) -> Dict[str, Any]:
    """Scorecard supplier dari data nyata (PO + penerimaan + retur)."""
    await require_permission(request, "supplier", "view")
    card = await compute_scorecard(supplier_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
    return card


@router.get("/suppliers/{supplier_id}/360")
async def get_supplier_360(supplier_id: str, request: Request) -> Dict[str, Any]:
    """Supplier 360 — profil + PO + tagihan + retur + scorecard (data nyata)."""
    await require_permission(request, "supplier", "view")
    ctx = await entity_ctx(request)
    data = await supplier_360(supplier_id)
    if not data:
        raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
    assert_entity_access(data, "suppliers", ctx)
    return data


@router.get("/suppliers/{supplier_id}/return-policy")
async def get_supplier_return_policy(supplier_id: str, request: Request) -> Dict[str, Any]:
    """R0 — Kebijakan retur supplier efektif (origin + policy + rekomendasi regrade lokal)."""
    await require_permission(request, "supplier", "view")
    ctx = await entity_ctx(request)
    sup = safe_doc(await db.suppliers.find_one({"id": supplier_id}, {"_id": 0}))
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
    assert_entity_access(sup, "suppliers", ctx)
    return resolve_supplier_return_policy(sup)
