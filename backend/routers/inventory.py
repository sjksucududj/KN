"""Inventory router: balances (owner-aware), rolls (SSOT), movements, history."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, DEFAULT_ENTITY_ID, strip_cost_fields
from entity_scope import entity_ctx, resolve_list_scope, resolve_scope_ids
from pagination import is_paged, get_page_params, build_search, merge_query, fetch_page, envelope
from schemas import RollPayload
from services.roll_service import rebuild_balance
import services.roll_service as roll_service
from services.fulfillment_service import status_board as _status_board
from services.stock_analytics_service import compute_stock_analytics
from services.location_service import putaway_queue, putaway_roll
from services.movement_label_service import attach_source_labels, attach_counterparty_labels
import domain_registry as _dr        # Fase A · R7 — SSOT enum/snapshot domain
from request_context import active_entity_or

router = APIRouter(prefix="/api")


class PutawayPayload(BaseModel):
    roll_id: str
    bin_id: str


@router.get("/inventory/putaway/queue")
async def get_putaway_queue(request: Request, warehouse_id: Optional[str] = None, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Fase 5 — antrean putaway: roll fisik yang belum ditempatkan ke bin."""
    await require_permission(request, "product", "view")
    ctx = await entity_ctx(request)
    rolls = await putaway_queue(warehouse_id, ctx, entity_id)
    return {"count": len(rolls), "rolls": rolls}


@router.post("/inventory/putaway")
async def do_putaway(payload: PutawayPayload, request: Request) -> Dict[str, Any]:
    """Fase 5 — tempatkan/pindahkan roll ke bin (SSOT-safe: hanya ubah bin_id)."""
    actor = await require_permission(request, "warehouse", "update")
    return await putaway_roll(payload.roll_id, payload.bin_id, actor_name=actor["name"])


async def _entity_map() -> Dict[str, Dict[str, Any]]:
    return {e["id"]: e for e in await db.business_entities.find({}, {"_id": 0}).to_list(100)}


@router.get("/inventory/stock-analytics")
async def stock_analytics(
    request: Request,
    entity_id: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Fase 5 — Stock Analytics: klasifikasi Fast/Slow/Dead + aging + kecepatan jual.
    READ-ONLY, entity-scoped, ambang batas configurable (config_service)."""
    await require_permission(request, "product", "view")
    ctx = await entity_ctx(request)
    return await compute_stock_analytics(ctx, entity_id=entity_id, warehouse_id=warehouse_id, category=category)


@router.get("/inventory/status-board")
async def inventory_status_board(
    request: Request,
    product_id: Optional[str] = None,
    owner_entity_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Sub-fase 1.4 — Inventory Status Board.

    Ringkasan per produk: on_hand / available / reserved / incoming / ATP,
    di-breakdown per entitas pemilik & gudang, plus indikator peluang
    pemenuhan lintas-entitas (inter-company)."""
    await require_permission(request, "product", "view")
    # FASE E-0/E-5 (E5.1) — peran non-lintas hanya melihat rincian entitasnya sendiri
    # + angka grup sebagai agregat (`global_total`). Dulu papan ini membocorkan
    # rincian stok per gudang milik PT lain ke sales.
    ctx = await entity_ctx(request)
    ids = resolve_scope_ids(ctx, owner_entity_id)
    return await _status_board(
        product_id=product_id,
        owner_entity_id=owner_entity_id if ctx.is_cross_entity else None,
        visible_entity_ids=None if (ctx.is_cross_entity and not owner_entity_id) else ids,
        cross_entity_detail=ctx.is_cross_entity,
    )


@router.get("/inventory/balances")
async def list_balances(request: Request, owner_entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    await require_permission(request, "product", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = resolve_list_scope("inventory_balances", {}, ctx, owner_entity_id)
    balances = await db.inventory_balances.find(query, {"_id": 0}).to_list(2000)
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(1000)}
    entities = await _entity_map()
    result = []
    for b in balances:
        b["warehouse_name"] = warehouses.get(b["warehouse_id"], {}).get("name", "")
        b["warehouse_city"] = warehouses.get(b["warehouse_id"], {}).get("city", "")
        p = products.get(b["product_id"], {})
        b["sku"] = p.get("sku", "")
        b["product_name"] = p.get("name", "")
        b["base_unit"] = p.get("base_unit", "meter")  # F2 (UoM SSOT) — untuk tampilan "X roll / Y base_unit"
        owner = b.get("owner_entity_id", DEFAULT_ENTITY_ID)
        b["owner_entity_id"] = owner
        b["owner_entity_name"] = entities.get(owner, {}).get("short_name") or entities.get(owner, {}).get("legal_name", owner)
        result.append(b)
    return result


@router.get("/inventory/rolls")
async def list_rolls(
    request: Request,
    product_id: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    owner_entity_id: Optional[str] = None,
    status: Optional[str] = None,
    lot: Optional[str] = None,
    line: str = "",
) -> Any:
    """Daftar roll fisik (SSOT) dengan filter owner/lot/status/warehouse.

    OPT-IN paginasi: bila ?page/?page_size hadir → envelope {items,total,...};
    kalau tidak → array telanjang (kompatibel mundur)."""
    actor = await require_permission(request, "product", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if product_id:
        query["product_id"] = product_id
    if warehouse_id:
        query["warehouse_id"] = warehouse_id
    if status:
        query["status"] = status
    if lot:
        query["lot"] = lot
    query = resolve_list_scope("inventory_rolls", query, ctx, owner_entity_id)
    # FASE L — pagar lini di Daftar Roll. Roll lama tanpa lini TETAP terlihat, kalau
    # tidak layar gudang mendadak kosong bagi staf ber-lini (user story L.G #4).
    from services import line_scope as _lines
    query = _lines.narrow(query, actor, line)

    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(1000)}
    entities = await _entity_map()

    def _enrich(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for r in rows:
            wh = warehouses.get(r.get("warehouse_id"), {})
            p = products.get(r.get("product_id"), {})
            ent = entities.get(r.get("owner_entity_id"), {})
            r["warehouse_name"] = wh.get("name", "")
            r["warehouse_city"] = wh.get("city", "")
            r["sku"] = p.get("sku", "")
            r["product_name"] = p.get("name", "")
            r["owner_entity_name"] = ent.get("short_name") or ent.get("legal_name", r.get("owner_entity_id", ""))
        return rows

    if is_paged(request):
        page, page_size, q, _sort = get_page_params(request)
        if q:
            # Cari juga lewat nama/SKU produk (tak tersimpan di roll → resolusi product_id).
            ql = q.lower()
            match_pids = [pid for pid, p in products.items()
                          if ql in (p.get("name", "").lower()) or ql in (p.get("sku", "").lower())]
            search = build_search(q, ["roll_no", "lot", "dye_lot", "batch", "grade", "consignor_ref"])
            if match_pids:
                search = {"$or": search.get("$or", []) + [{"product_id": {"$in": match_pids}}]}
            query = merge_query(query, search)
        items, total = await fetch_page(db.inventory_rolls, query, page, page_size,
                                        sort_field="created_at", sort_dir=-1)
        _enrich(items)
        data = envelope(items, total, page, page_size)
        data["items"] = strip_cost_fields(data["items"], actor.get("role"))
        return data

    rolls = await db.inventory_rolls.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    _enrich(rolls)
    return strip_cost_fields(rolls, actor.get("role"))


@router.get("/inventory/rolls/available")
async def list_rolls_available(
    request: Request,
    product_id: str,
    entity_id: Optional[str] = None,     # entitas penjual (untuk tandai lintas-entitas)
    all_entities: bool = False,          # SALES REVAMP V2 — picker boleh lihat semua entitas
    sort: str = "fefo",
    skip: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """SALES REVAMP V2 — Picker 'Beli per Roll': daftar roll available (paginasi + FEFO).
    all_entities=True → lintas-entitas (tiap roll diberi badge entitas + flag is_cross_entity).
    Mengembalikan {items, total} (objek picker, bukan array telanjang)."""
    actor = await require_permission(request, "product", "view")
    ctx = await entity_ctx(request)
    selling_entity = (entity_id or getattr(ctx, "active_entity_id", "") or "").strip()
    owner_scope = "" if all_entities else (selling_entity or "")
    data = await roll_service.list_available_rolls(
        product_id=product_id, owner_entity_id=owner_scope, all_entities=all_entities,
        sort=sort, skip=max(0, skip), limit=max(0, limit),
    )
    for it in data["items"]:
        it["is_cross_entity"] = bool(selling_entity and it.get("owner_entity_id") != selling_entity)
    data["selling_entity_id"] = selling_entity
    return strip_cost_fields(data, actor.get("role"))


@router.get("/inventory/movements")
async def list_movements(request: Request, warehouse_id: Optional[str] = None,
                         product_id: Optional[str] = None,
                         movement_type: Optional[str] = None) -> Any:
    """Daftar mutasi stok. `movement_type` menyaring satu jenis mutasi.

    FASE F (US11) — gudang perlu menemukan **pengambilan bahan sample** (`sample_issue`)
    tanpa mengetik kode mentah; layar Mutasi memakai penyaring ini dengan label
    Bahasa Indonesia ("Ambil Bahan Sample (R&D)").

    FASE E-5 (E5.3) — mutasi **pindah-kepemilikan antar badan usaha** WAJIB tetap
    terlihat dari sisi pemiliknya masing-masing (jejak tidak boleh disembunyikan),
    tetapi badan usaha lawan hanya muncul sebagai **nama singkat**
    (`counterparty_entity_name`/`counterparty_label`). Untuk peran non-lintas, id
    teknis `from_owner_entity_id`/`to_owner_entity_id` dicabut dari respons.
    """
    actor = await require_permission(request, "product", "view")
    ctx = await entity_ctx(request)
    query = resolve_list_scope("inventory_movements", {}, ctx)
    if warehouse_id:
        query["warehouse_id"] = warehouse_id
    if product_id:
        query["product_id"] = product_id
    if movement_type:
        query["movement_type"] = movement_type
    if is_paged(request):
        page, page_size, q, _sort = get_page_params(request)
        if q:
            query = merge_query(query, build_search(q, ["source_document", "movement_type", "notes", "lot", "batch"]))
        items, total = await fetch_page(db.inventory_movements, query, page, page_size,
                                        sort_field="timestamp", sort_dir=-1)
        data = envelope(items, total, page, page_size)
        data["items"] = await attach_counterparty_labels(
            await attach_source_labels(strip_cost_fields(data["items"], actor.get("role"))),
            cross_entity=ctx.is_cross_entity)
        return data
    movements = await db.inventory_movements.find(query, {"_id": 0}).sort("timestamp", -1).to_list(500)
    return await attach_counterparty_labels(
        await attach_source_labels(strip_cost_fields(movements, actor.get("role"))),
        cross_entity=ctx.is_cross_entity)


@router.post("/inventory/initial-stock")
async def add_initial_stock(payload: RollPayload, request: Request) -> Dict[str, Any]:
    """Tambah stok awal sebagai ROLL fisik (KN_15) + movement, lalu rebuild balance."""
    actor = await require_permission(request, "product", "create")
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity harus > 0")
    # FASE E-1 (E1.10) — stok awal dimiliki badan usaha KONTEKS, bukan default global.
    owner = payload.owner_entity_id or active_entity_or(DEFAULT_ENTITY_ID)
    if not await db.products.find_one({"id": payload.product_id}, {"_id": 0}):
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    # E4.1 — stok awal tidak boleh mendarat di gudang khusus badan usaha lain.
    from services import warehouse_scope_service as whscope
    await whscope.assert_usable(payload.warehouse_id, owner,
                               action="menaruh stok awal di sini")
    lot = payload.lot or "LOT-MANUAL"
    _prod = await db.products.find_one({"id": payload.product_id}, {"_id": 0}) or {}
    # FASE C (D-10/D-26) — stok awal manual juga WAJIB punya lot kelas satu.
    from services import lot_service as _lots
    _lot_doc = await _lots.resolve_or_create(
        product_id=payload.product_id, owner_entity_id=owner,
        warehouse_id=payload.warehouse_id, lot_code=lot, source="manual",
        source_ref={"type": "manual", "id": "initial_stock", "number": lot},
        dye_lot=getattr(payload, "dye_lot", "") or lot, status="released",
        actor=actor.get("name", "System"))
    roll = {
        "id": new_id("roll"), "product_id": payload.product_id, "owner_entity_id": owner,
        "ownership_type": payload.ownership_type, "consignor_ref": None,
        "warehouse_id": payload.warehouse_id, "bin_id": payload.bin_id or None,
        "lot": _lot_doc["lot_number"], "lot_id": _lot_doc["id"],
        "batch": payload.batch or lot.replace("LOT", "BATCH"),
        "dye_lot": getattr(payload, "dye_lot", "") or lot, "defects": [],
        "roll_no": payload.roll_no or await roll_service.next_roll_no(),
        "length_initial": float(payload.quantity), "length_remaining": float(payload.quantity),
        "unit": payload.unit, "grade": payload.grade, "status": "available",
        # Fase A · PS-02 — snapshot domain produk (INV-DOMAIN-05)
        **_dr.roll_domain_snapshot(_prod),
        "tracking_mode": payload.tracking_mode, "earmarked_for": None,
        "location_type": "warehouse_bin", "reserved_ref": None,
        "unit_cost": None, "base_unit_cost": None, "landed_cost_total": 0.0, "landed_cost_refs": [],
        "acquired": {"via": "initial", "ref_id": "manual", "date": now_iso()},
        "rfid_tag_id": None, "is_remnant": False,
        "created_at": now_iso(), "updated_at": now_iso(),
        "created_by": actor.get("id", "system"), "created_by_name": actor.get("name", "System"),
    }
    await db.inventory_rolls.insert_one(roll)
    await db.inventory_movements.insert_one({
        "id": new_id("mov"), "product_id": payload.product_id, "warehouse_id": payload.warehouse_id,
        "owner_entity_id": owner, "movement_type": "initial_stock", "quantity": float(payload.quantity),
        "unit": payload.unit, "batch": roll["batch"], "lot": _lot_doc["lot_number"],
        "lot_id": _lot_doc["id"], "roll_id": roll["id"],
 # FASE U — satu baris mutasi menunjuk SATU roll fisik.
 "qty_rolls": (1 if roll["id"] else None),
        "source_document": "initial_stock", "timestamp": now_iso(),
    })
    await rebuild_balance(payload.product_id, payload.warehouse_id, owner)
    await audit(actor["name"], "initial_stock_added", "inventory", payload.product_id,
                {"roll_id": roll["id"], "qty": payload.quantity, "owner": owner,
                 "lot": _lot_doc["lot_number"], "lot_id": _lot_doc["id"]})
    return {"message": "Stok awal (roll) berhasil ditambahkan", "roll_id": roll["id"],
            "lot": _lot_doc["lot_number"], "lot_id": _lot_doc["id"],
            "lot_number": _lot_doc["lot_number"]}


@router.get("/history/{product_id}")
async def product_history(product_id: str, request: Request) -> List[Dict[str, Any]]:
    """Kartu riwayat satu produk. Ikut ber-`source_document_label` supaya kolom
    Dokumen tidak pernah menampilkan id teknis (`so_…`/`wo_…`/`mko_…`).

    FASE E-5 (E5.3) — **KEBOCORAN YANG DITUTUP DI SINI.** Endpoint ini dulu
    mengambil SELURUH mutasi sebuah produk tanpa scope entitas sama sekali:
    sales CV Kanda Suka mengklik satu produk dan ikut membaca mutasi milik
    PT Kain Suka Cita lengkap dengan nomor lot & gudangnya (terbukti empiris:
    9 baris, 2 di antaranya milik badan usaha lain). Itu bertentangan langsung
    dengan Keputusan #1 pemilik ("sales: detail stok entitas sendiri saja").
    Sekarang daftarnya ter-scope `owner_entity_id`; mutasi pindah-kepemilikan
    tetap tampil **dari sisi badan usaha sendiri** dengan nama singkat lawannya.
    """
    actor = await require_permission(request, "product", "view")
    ctx = await entity_ctx(request)
    query = resolve_list_scope("inventory_movements", {"product_id": product_id}, ctx)
    movements = await db.inventory_movements.find(
        query, {"_id": 0}
    ).sort("timestamp", -1).to_list(200)
    warehouses = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(100)}
    for m in movements:
        m["warehouse_name"] = warehouses.get(m.get("warehouse_id", ""), {}).get("name", "")
    return await attach_counterparty_labels(
        await attach_source_labels(strip_cost_fields(movements, actor.get("role"))),
        cross_entity=ctx.is_cross_entity)
