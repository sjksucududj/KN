"""Products router: CRUD products + stock breakdown."""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
import domain_registry as dr
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, parse_decimal, safe_doc, strip_cost_fields
from schemas import GenericPatch, ProductPayload
from services.inventory_service import expire_old_reservations, product_summary
from services import pricelist_service
from services import rnd_gate
from services import product_exclusivity as pexcl
from services import line_scope
from entity_scope import entity_ctx

router = APIRouter(prefix="/api")


@router.get("/products")
async def list_products(request: Request, orderable_only: bool = False,
                        line: str = "") -> List[Dict[str, Any]]:
    # INV-AUTH-01 (KN-076-AUTH-MASTER-LEAK P1): katalog WAJIB login — auth di LUAR try/except.
    actor = await require_permission(request, "product", "view")
    await expire_old_reservations()
    # PS-20 — visibilitas eksklusif per sales DIPAKSA DI BACKEND (query Mongo), bukan di UI,
    # agar sales lain tidak bisa menembusnya lewat API.
    # FASE L — pagar lini ditambahkan pada query yang SAMA (bukan penyaringan di
    # memori) supaya `?line=` dari staf berpagar tidak bisa dipakai sebagai jalan
    # belakang, dan produk tanpa lini (data lama) tetap terlihat.
    query = line_scope.narrow(pexcl.visibility_query(actor), actor, line)
    products = await db.products.find(query, {"_id": 0}).to_list(500)
    # FASE F (PS-12) — katalog jual/beli hanya menampilkan produk yang SAH dipesan.
    # Dipakai POS/Sales Portal (`orderable_only=true`); Master Produk tetap melihat semua.
    if orderable_only:
        products = [p for p in products if rnd_gate.is_orderable(p)]
    # F1a — harga jual per-entitas: tampilkan harga efektif entitas aktif (fallback global).
    role = actor.get("role")
    try:
        ctx = await entity_ctx(request)
        active = ctx.active_entity_id
    except Exception:
        active = None
    pmap = {p["id"]: p for p in products}
    price_map = await pricelist_service.resolve_many(active, [p["id"] for p in products], pmap)
    for product in products:
        product.update(await product_summary(product["id"]))
        info = price_map.get(product["id"], {})
        product["global_price"] = float(product.get("price", 0) or 0)
        if info.get("source") == "entity":
            product["price"] = info["price"]
        product["price_source"] = info.get("source", "global")
    # S-10 — harga_pokok (HPP) hanya untuk admin/manager
    return strip_cost_fields(products, role)


def _apply_domain(data: Dict[str, Any], existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Fase A (PS-01/02/03/09) — normalisasi + validasi domain tekstil.

    Melempar HTTP 400 (pesan Indonesia) bila stage/fabric_type/grade tidak sah atau
    kelengkapan wajib per stage belum terpenuhi (GSM/lebar ≥ grey, yarn_count utk yarn).
    Mengembalikan hasil validasi (berisi `warnings` & `needs_review*`).
    """
    dr.apply_normalization(data)
    check = dr.validate_product(data, existing)
    if check["errors"]:
        raise HTTPException(status_code=400, detail=" ".join(check["errors"]))
    return check


@router.post("/products")
async def create_product(payload: ProductPayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "create")
    if await db.products.find_one({"sku": payload.sku}, {"_id": 0}):
        raise HTTPException(status_code=409, detail="SKU sudah digunakan")
    product = payload.model_dump()
    # FASE G-0 — `inventory.default_uom` DULU tidak dibaca kode mana pun. Sekarang benar-benar
    # menjadi satuan dasar bawaan produk baru bila pengguna tidak mengisinya.
    if not (product.get("base_unit") or "").strip():
        from services.config_resolver import value_of
        product["base_unit"] = str(await value_of("inventory.default_uom") or "meter")
    check = _apply_domain(product)
    # PS-20 — normalisasi + validasi eksklusivitas (owner wajib sales aktif bila eksklusif).
    await pexcl.normalize(db, product)
    # FASE L — lini divalidasi terhadap MASTER (bukan daftar hardcode) + INV-LINE-02.
    # Staf berpagar lini hanya boleh membuat produk di lininya sendiri, kalau tidak
    # pagar bacanya bisa dilewati hanya dengan membuat produk baru.
    ctx_l = None
    try:
        ctx_l = await entity_ctx(request)
    except Exception:                       # noqa: BLE001 — tanpa konteks = master global
        ctx_l = None
    await line_scope.normalize_product(
        product, entity_id=getattr(ctx_l, "active_entity_id", "") or "")
    line_scope.assert_can_order(actor, product)
    # FASE F (PS-12) — produk yang dibuat LANGSUNG dari Master Produk mengikuti kebijakan
    # `rnd.new_product_default_lifecycle` (bawaan `produksi` agar cara kerja lama tetap sama).
    if not (product.get("lifecycle") or "").strip():
        product["lifecycle"] = await rnd_gate.default_new_lifecycle()
    product.update({"id": new_id("prod"), "batch_lot_rolls": [],
                    "needs_review": check["needs_review"],
                    "needs_review_reasons": check["needs_review_reasons"],
                    "created_at": now_iso(), "updated_at": now_iso()})
    await db.products.insert_one(product)
    await audit(actor["name"], "product_created", "product", product["id"], product)
    out = safe_doc(product)
    out["domain_warnings"] = check["warnings"]
    return out


@router.patch("/products/{product_id}")
async def update_product(product_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "update")
    allowed = ["sku", "name", "category", "variant", "color", "motif", "supplier",
               "color_code", "color_name", "color_hex",
               "base_unit", "price", "image", "description", "status", "uom_conversions", "harga_pokok",
               "kg_per_meter", "reorder_point", "reorder_qty", "template_id", "variant_attrs",
               "lifecycle", "spec_id", "design_id", "design_version"] \
        + dr.PRODUCT_DOMAIN_FIELDS   # Fase A — stage/fabric_type/grade/gramasi/lebar/yarn_count*
    allowed += ["exclusivity", "owner_sales_ids"]   # PS-20 — kepemilikan/visibilitas produk
    allowed += ["line_code"]                        # FASE L — pembagian kerja MD
    data = {k: v for k, v in payload.data.items() if k in allowed}
    if "lifecycle" in data:
        lc = str(data["lifecycle"] or "").strip().lower()
        if lc and not dr.is_valid("lifecycle", lc):
            raise HTTPException(status_code=400, detail=(
                f"Tahap produk (lifecycle) '{lc}' tidak dikenal. "
                f"Pilihan: {', '.join(dr.values_of('lifecycle'))}."))
        data["lifecycle"] = lc
    existing = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    # PS-15/R5 — angka boleh dikirim sebagai teks berkoma ("10,5").
    for num_field in ("price", "harga_pokok", "gramasi", "lebar", "kg_per_meter",
                      "reorder_point", "reorder_qty"):
        if num_field in data:
            try:
                data[num_field] = parse_decimal(data[num_field])
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"{num_field}: {exc}")
    check = _apply_domain(data, existing)
    data["needs_review"] = check["needs_review"]
    data["needs_review_reasons"] = check["needs_review_reasons"]
    data["updated_at"] = now_iso()
    # PS-20 — normalisasi eksklusivitas bila field dikirim pada patch ini.
    await pexcl.normalize(db, data)
    # FASE L — pagar lini dua arah: staf berpagar tidak boleh menyentuh produk lini
    # lain, dan tidak boleh MEMINDAHKAN produk ke lini di luar aksesnya.
    line_scope.assert_can_touch(actor, existing, what=f"Produk '{existing.get('name', product_id)}'")
    try:
        ctx_l = await entity_ctx(request)
        active_eid = getattr(ctx_l, "active_entity_id", "") or ""
    except Exception:                       # noqa: BLE001
        active_eid = ""
    await line_scope.normalize_product(data, existing, entity_id=active_eid)
    if "line_code" in data:
        line_scope.assert_can_order(actor, {**existing, **data})
    product = await db.products.find_one_and_update(
        {"id": product_id}, {"$set": data},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    await audit(actor["name"], "product_updated", "product", product_id, product)
    product["domain_warnings"] = check["warnings"]
    return product


@router.get("/products/sales-owners")
async def list_sales_owners(request: Request) -> List[Dict[str, Any]]:
    """PS-20 — daftar user sales (id + nama) untuk memilih pemilik produk eksklusif.

    Dipakai form Master Produk. Digerbang izin `product:update` (yang punya hanya admin),
    jadi tidak membocorkan daftar user ke role lain.
    """
    await require_permission(request, "product", "update")
    users = await db.users.find(
        {"role": "sales", "status": "active"}, {"_id": 0, "id": 1, "name": 1, "email": 1}
    ).sort("name", 1).to_list(200)
    return users



@router.delete("/products/{product_id}")
async def delete_product(product_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "product", "delete")
    product = await db.products.find_one_and_update(
        {"id": product_id},
        {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    await audit(actor["name"], "product_deactivated", "product", product_id, product)
    return product


@router.get("/products/{product_id}/stock-breakdown")
async def stock_breakdown(product_id: str, request: Request) -> Dict[str, Any]:
    # INV-AUTH-01 (KN-076-AUTH-MASTER-LEAK P1): WAJIB login — auth di LUAR try/except.
    # S-10 — role penentu redaksi HPP (default teredaksi utk non admin/manager).
    actor = await require_permission(request, "product", "view")
    role = actor.get("role")
    product = safe_doc(await db.products.find_one({"id": product_id}, {"_id": 0}))
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    # FASE L — pagar lini juga berlaku pada BACA per dokumen. Kalau hanya daftarnya
    # disaring, alamat langsung `/products/{id}/stock-breakdown` tetap membocorkan
    # produk lini lain (kelas bug IDOR yang sama dengan pagar entitas).
    line_scope.assert_can_touch(actor, product,
                                what=f"Produk '{product.get('name', product_id)}'")
    balances_raw = await db.inventory_balances.find({"product_id": product_id}, {"_id": 0}).to_list(100)
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    entities = {e["id"]: e for e in await db.business_entities.find({}, {"_id": 0}).to_list(100)}
    reservations_raw = await db.sales_orders.find(
        {"allocations.product_id": product_id,
         "status": {"$in": ["reserved", "waiting_approval", "approved", "confirmed"]}},
        {"_id": 0}
    ).to_list(100)
    rolls_raw = await db.inventory_rolls.find({"product_id": product_id}, {"_id": 0}).to_list(5000)

    def _ent_name(eid):
        e = entities.get(eid, {})
        return e.get("short_name") or e.get("legal_name", eid)

    rows = []
    for balance in balances_raw:
        b = safe_doc(balance)
        warehouse = safe_doc(warehouses.get(b.get("warehouse_id"), {}))
        rows.append({**b, "warehouse_name": warehouse.get("name"), "warehouse_city": warehouse.get("city"),
                     "owner_entity_name": _ent_name(b.get("owner_entity_id"))})

    # Matriks (Owner × Gudang × Lot) — KN_15 §8 (K1)
    matrix: Dict[tuple, Dict[str, Any]] = {}
    rolls = []
    for r in rolls_raw:
        r = safe_doc(r)
        wh = warehouses.get(r.get("warehouse_id"), {})
        r["warehouse_name"] = wh.get("name", "")
        r["owner_entity_name"] = _ent_name(r.get("owner_entity_id"))
        rolls.append(r)
        key = (r.get("owner_entity_id"), r.get("warehouse_id"), r.get("lot"))
        cell = matrix.setdefault(key, {
            "owner_entity_id": r.get("owner_entity_id"), "owner_entity_name": _ent_name(r.get("owner_entity_id")),
            "warehouse_id": r.get("warehouse_id"), "warehouse_name": wh.get("name", ""),
            "warehouse_city": wh.get("city", ""), "lot": r.get("lot"), "grade": r.get("grade"),
            "available_qty": 0.0, "reserved_qty": 0.0, "committed_qty": 0.0, "on_hand_qty": 0.0,
            "roll_count": 0,
        })
        length = float(r.get("length_remaining", 0) or 0)
        status = r.get("status")
        if status == "available":
            cell["available_qty"] += length
        elif status == "reserved":
            cell["reserved_qty"] += length
        elif status == "committed":
            cell["committed_qty"] += length
        if status in ("available", "reserved", "committed", "picked", "packed", "quarantine", "blocked", "damaged"):
            cell["on_hand_qty"] += length
            cell["roll_count"] += 1
    matrix_list = []
    for cell in matrix.values():
        for k in ("available_qty", "reserved_qty", "committed_qty", "on_hand_qty"):
            cell[k] = round(cell[k], 2)
        matrix_list.append(cell)
    matrix_list.sort(key=lambda c: (c["owner_entity_name"], c["warehouse_name"], c["lot"] or ""))

    return strip_cost_fields({
        "product": product,
        "balances": rows,
        "ownership_matrix": matrix_list,
        "rolls": rolls,
        "reservations": [safe_doc(r) for r in reservations_raw if r]
    }, role)
