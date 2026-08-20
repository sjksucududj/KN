"""Purchase Orders router: simplified PO management for inbound receiving."""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from dependencies import require_permission, audit, current_user
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID, timeline_entry, next_doc_number, rupiah
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from pagination import is_paged, get_page_params, build_search, merge_query, fetch_page, envelope
from schemas import PurchaseOrderCreate, PurchaseOrderAmend
from services.config_service import build_approval_chain, current_pending_level, role_satisfies, get_effective_settings, compute_order_pricing
from services.po_amendment_service import amend_po as amend_po_service
from services import blanket_po_service
from services import grade_service          # Fase A · PS-09/D-19
from services import line_scope             # FASE L — pagar & penyaring lini produk
# FASE E/F-1 — katalog barang supplier (nama/kode + satuan supplier) untuk baris PO
from services import supplier_item_service as _sis
from domain_registry import DomainValidationError

router = APIRouter(prefix="/api")

# Status PO yang dianggap "barang sudah/akan diterima" → menimbulkan hutang (AP)
AP_LIABILITY_STATUSES = {"pending", "receiving", "partial", "completed", "closed_short"}
TERMINAL_PO_STATUSES = {"cancelled", "rejected", "closed_short", "completed"}


def _po_financials(po: Dict[str, Any]) -> Dict[str, Any]:
    """Hitung nilai keuangan PO: diterima, retur, dibayar, outstanding (AP).

    P0-1 — basis tagihan/hutang = grand_total (incl PPN & setelah diskon) bila ada,
    fallback ke total_amount (GROSS) untuk PO lama tanpa breakdown."""
    ordered_value = 0.0
    received_value = 0.0
    for it in po.get("items", []):
        price = float(it.get("price", 0) or 0)
        ordered_value += float(it.get("quantity", 0) or 0) * price
        received_value += float(it.get("received_qty", 0) or 0) * price
    gross_total = float(po.get("total_amount", 0) or 0)
    if gross_total <= 0.0:  # fallback PO lama tanpa total_amount tersimpan
        gross_total = ordered_value
    # Basis tagihan ke supplier: grand_total (incl PPN) bila tersedia, else gross.
    grand = float(po.get("grand_total", 0) or 0)
    base = grand if grand > 0.0 else gross_total
    amount_paid = float(po.get("amount_paid", 0) or 0)
    returned_amount = float(po.get("returned_amount", 0) or 0)
    billable = max(base - returned_amount, 0.0)
    outstanding = round(max(billable - amount_paid, 0.0), 2)
    if amount_paid <= 0.01:
        pay_status = "unpaid"
    elif outstanding <= 0.01:
        pay_status = "paid"
    else:
        pay_status = "partial"
    return {
        "total_amount": round(base, 2),         # base tagihan (incl PPN bila ada) — dipakai UI/payables
        "gross_total": round(gross_total, 2),   # Σ subtotal (sebelum diskon & pajak)
        "discount_total": round(float(po.get("discount_total", 0) or 0), 2),
        "net_subtotal": round(float(po.get("net_subtotal", 0) or 0), 2),
        "dpp": round(float(po.get("dpp", 0) or 0), 2),
        "ppn_rate": float(po.get("ppn_rate", 0) or 0),
        "ppn_amount": round(float(po.get("ppn_amount", 0) or 0), 2),
        "grand_total": round(base, 2),
        "received_value": round(received_value, 2),
        "returned_amount": round(returned_amount, 2),
        "amount_paid": round(amount_paid, 2),
        "outstanding": outstanding,
        "payment_status": pay_status,
    }


async def recompute_po_status(po_id: str) -> None:
    """Depth 1A — hitung status PO dari received_qty tiap item.
    Tidak menimpa status terminal (cancelled/rejected/closed_short/completed)."""
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po or po.get("status") in TERMINAL_PO_STATUSES:
        return
    items = po.get("items", [])
    if not items:
        return
    settings = await get_effective_settings(po.get("entity_id"))
    tol = float((settings.get("purchasing", {}) or {}).get("receive_tolerance_percent", 2.0) or 0)
    total_received = sum(float(it.get("received_qty", 0) or 0) for it in items)
    # Item dianggap lengkap bila received >= ordered*(1 - toleransi)
    all_complete = all(
        float(it.get("received_qty", 0) or 0) + 1e-6 >= float(it.get("quantity", 0) or 0) * (1 - tol / 100.0)
        for it in items
    )
    if all_complete and total_received > 0:
        new_status = "completed"
    elif total_received > 0:
        new_status = "partial"
    else:
        new_status = po.get("status", "pending")
    if new_status != po.get("status"):
        update_ops: Dict[str, Any] = {"$set": {"status": new_status, "updated_at": now_iso()}}
        if new_status == "completed":
            update_ops["$push"] = {"timeline": timeline_entry(
                "completed", "Penerimaan barang selesai", "Sistem",
                f"Total diterima {total_received:g}")}
        elif new_status == "partial":
            update_ops["$push"] = {"timeline": timeline_entry(
                "received", "Barang diterima sebagian", "Sistem",
                f"Diterima {total_received:g}")}
        await db.purchase_orders.update_one({"id": po_id}, update_ops)


async def recompute_po_payment_status(po_id: str) -> None:
    """Depth 1C — sinkronkan payment_status & outstanding PO."""
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        return
    fin = _po_financials(po)
    await db.purchase_orders.update_one(
        {"id": po_id},
        {"$set": {"payment_status": fin["payment_status"], "outstanding": fin["outstanding"],
                  "updated_at": now_iso()}})


async def _create_inbound_tasks_for_po(po: Dict[str, Any]) -> None:
    """Buat inbound receiving task untuk tiap item PO (dipanggil saat PO siap
    diterima: langsung bila tak butuh approval, atau setelah di-approve)."""
    # Resolve warehouse name/city defensively (PO lama/seed mungkin tak menyimpannya).
    wh_name = po.get("warehouse_name", "")
    wh_city = po.get("warehouse_city", "")
    entity_id = po.get("entity_id") or ""  # F0-C/D: wms_tasks ter-stamp per entitas dari PO induk.
    if not wh_name and po.get("warehouse_id"):
        wh = await db.warehouses.find_one({"id": po["warehouse_id"]}, {"_id": 0, "name": 1, "city": 1})
        if wh:
            wh_name = wh.get("name", "")
            wh_city = wh.get("city", "") or wh_city
    for item in po.get("items", []):
        # Phase 7.2 — idempotent saat re-approval amendment: jangan duplikat task yg sudah ada.
        existing = await db.wms_tasks.find_one({
            "po_id": po["id"], "product_id": item["product_id"], "flow_type": "inbound",
            "status": {"$nin": ["cancelled", "completed"]},
        }, {"_id": 0, "id": 1, "expected_qty": 1})
        if existing:
            if abs(float(existing.get("expected_qty", 0) or 0) - float(item["quantity"] or 0)) > 0.001:
                await db.wms_tasks.update_one(
                    {"id": existing["id"]},
                    {"$set": {"expected_qty": item["quantity"], "unit": item.get("unit", "meter"),
                              "updated_at": now_iso()}})
            continue
        stages = ["waiting_goods", "receiving", "qc_check", "put_away", "completed"]
        task_id = new_id("wms")
        await db.wms_tasks.insert_one({
            "id": task_id,
            "entity_id": entity_id,
            "flow_type": "inbound",
            "source_type": "purchase_order",
            "po_id": po["id"],
            "po_number": po["po_number"],
            "product_id": item["product_id"],
            "product_name": item.get("product_name", ""),
            "sku": item.get("sku", ""),
            "expected_qty": item["quantity"],
            "received_qty": 0.0,
            "quantity": 0.0,
            "unit": item.get("unit", "meter"),
            # FASE U — dua satuan: RENCANA jumlah roll turun dari baris PO, sedangkan
            # `qty_rolls` (hasil) DIHITUNG saat penerimaan selesai dari roll yang lahir.
            "expected_rolls": item.get("qty_rolls"),
            "qty_rolls": None,
            "warehouse_id": po["warehouse_id"],
            "warehouse_name": wh_name,
            "warehouse_city": wh_city,
            "supplier_name": po.get("supplier_name", ""),
            # FASE E — nama & kode barang VERSI SUPPLIER ditampilkan berdampingan dengan
            # nama KN saat penerimaan, agar petugas gudang tidak salah barang.
            "supplier_sku": item.get("supplier_sku", ""),
            "supplier_item_name": item.get("supplier_item_name", ""),
            "supplier_item_id": item.get("supplier_item_id", ""),
            # FASE F-1 — satuan & faktor versi supplier ikut dibawa agar layar penerimaan
            # bisa langsung menawarkan input qty dalam SATUAN SUPPLIER (F1-01).
            "supplier_uom": item.get("supplier_uom", ""),
            "supplier_conv_factor": item.get("supplier_conv_factor", 0),
            "expected_grade": item.get("expected_grade", ""),
            "bin_id": "", "batch": "", "lot": "", "roll_id": "",
            "status": stages[0], "stages": stages, "scan_log": [],
            "escalation": None,
            "created_by": po.get("created_by", "system"),
            "created_at": now_iso(), "updated_at": now_iso(),
        })
        # FASE G-4 — tugas penerimaan (GRN) menaut ke PO induknya, dua arah.
        from services import doc_refs_service as _refs
        await _refs.safe_link(("grn", task_id), ("purchase_order", po["id"]),
                              "parent", note=f"penerimaan {item.get('product_name', '')}".strip())


@router.get("/purchase-orders")
async def list_purchase_orders(request: Request, entity_id: str = None,
                               line: str = "") -> Any:
    """List all purchase orders. Opt-in paginasi (?page/?page_size)."""
    actor = await require_permission(request, "purchase_order", "view")
    ctx = await entity_ctx(request)
    query = {"po_type": {"$ne": "blanket"}}  # blanket punya daftar terpisah (GET /purchase-orders/blanket)
    query = resolve_list_scope("purchase_orders", query, ctx, entity_id)
    # FASE L — pagar lini + chip `?line=` (pemilik: "berlaku di semua tempat, bukan
    # hanya saat membuat PO").
    query = line_scope.narrow(query, actor, line, field=line_scope.LINES_FIELD)
    if is_paged(request):
        page, page_size, q, _sort = get_page_params(request)
        if q:
            query = merge_query(query, build_search(q, ["po_number", "supplier_name", "warehouse_name"]))
        items, total = await fetch_page(db.purchase_orders, query, page, page_size, sort_field="created_at", sort_dir=-1)
        return envelope(items, total, page, page_size)
    pos = await db.purchase_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)
    return pos


@router.post("/purchase-orders")
async def create_purchase_order(payload: PurchaseOrderCreate, request: Request) -> Dict[str, Any]:
    """Create a new purchase order (auto-create inbound task bila tak butuh approval)."""
    actor = await require_permission(request, "purchase_order", "create")
    ctx = await entity_ctx(request)
    return await _create_po_core(payload, actor, active_entity_id=ctx.active_entity_id)


@router.get("/purchase-orders/resolve-sourcing")
async def resolve_po_sourcing(request: Request, supplier_id: str = "", product_id: str = "",
                              qty: float = 0.0, unit: str = "",
                              entity_id: str = "") -> Dict[str, Any]:
    """FASE F-2 — pratinjau sumber harga PO manual untuk 1 baris (dipakai POCreateForm).

    Mengembalikan harga usulan + sumbernya (kontrak pembelian / harga terakhir barang
    supplier / master) + jejak `explain[]` + nomor kontrak & SKU supplier, sehingga form
    bisa mengisi harga otomatis dan menampilkan lencana asal harga.
    """
    await current_user(request)
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id wajib diisi.")
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id or DEFAULT_ENTITY_ID
    if eid == "all":
        eid = ctx.active_entity_id if ctx.active_entity_id not in ("", "all") else DEFAULT_ENTITY_ID
    from services.pr_sourcing_service import resolve_line_sourcing as _resolve_sourcing
    src = await _resolve_sourcing(supplier_id=supplier_id, product_id=product_id,
                                  qty=float(qty or 0), entity_id=eid,
                                  est_price=0.0, unit=unit or "")
    return {
        "price": src.get("price", 0),
        "unit": src.get("unit", "") or unit,
        "source": src.get("source", ""),
        "contract_id": src.get("contract_id", ""),
        "contract_number": src.get("contract_number", ""),
        "supplier_item_id": src.get("supplier_item_id", ""),
        "supplier_sku": src.get("supplier_sku", ""),
        "supplier_item_name": src.get("supplier_item_name", ""),
        "expected_grade": src.get("expected_grade", ""),
        "below_moq": src.get("below_moq", False),
        "explain": src.get("explain", []),
    }



async def _create_po_core(payload: PurchaseOrderCreate, actor: Dict[str, Any], *,
                          po_type: str = "standard", parent: Dict[str, Any] = None,
                          force_approval: bool = False, force_reason: str = "",
                          extra_note: str = "", active_entity_id: str = DEFAULT_ENTITY_ID) -> Dict[str, Any]:
    """Inti pembuatan PO — dipakai PO standar & call-off Blanket PO (2.a).

    `force_approval`/`force_reason` → paksa approval dari awal (mis. over-call 4.b).
    `parent` = dokumen Blanket PO (untuk linkage call-off). Auto-create inbound task
    bila TIDAK butuh approval (atau nanti setelah /approve).
    """
    # Validate warehouse
    # E4.1 — gudang penerimaan PO harus boleh dipakai badan usaha pembeli.
    from services import warehouse_scope_service as whscope
    warehouse = await whscope.assert_usable(payload.warehouse_id, active_entity_id,
                                           action="menerima barang di sini",
                                           field_label="Gudang penerimaan")

    # Fase 3 — resolve supplier master (FK) → snapshot. Fallback ke supplier_name manual.
    supplier_id = ""
    supplier_name = (payload.supplier_name or "").strip()
    supplier_contact = payload.supplier_contact
    supplier_npwp = ""
    if payload.supplier_id:
        supplier = safe_doc(await db.suppliers.find_one({"id": payload.supplier_id}, {"_id": 0}))
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier tidak ditemukan")
        # FASE E-7 (E7.2) — PAGAR "lawan transaksi ternyata PT sendiri". PO biasa ke
        # badan usaha grup melewati dokumen kembar, kontrak internal, faktur pajak
        # internal, DAN eliminasi margin → laba grup jadi kembung. Arahkan ke Antar Entitas.
        from services import group_partner_service as _grp
        await _grp.assert_supplier_not_group_entity(supplier, doc_label="Pesanan Pembelian (PO)")
        supplier_id = supplier["id"]
        supplier_name = supplier.get("name", "")
        supplier_npwp = supplier.get("npwp", "")
        if not supplier_contact:
            pic = supplier.get("pic_name", "")
            phone = supplier.get("phone", "")
            supplier_contact = " | ".join([x for x in [pic, phone] if x])
    if not supplier_name:
        raise HTTPException(status_code=400, detail="Supplier wajib dipilih atau diisi")
    if not supplier_id:
        # Nama bebas pun tidak boleh menjadi pintu belakang: kalau nama-nya ternyata
        # badan usaha grup, pagar yang sama berlaku.
        from services import group_partner_service as _grp2
        _ent_match = await _grp2.match_group_entity(name=supplier_name)
        if _ent_match:
            await _grp2.assert_supplier_not_group_entity(
                {"group_entity_id": _ent_match["id"], "partner_kind": "entity"},
                doc_label="Pesanan Pembelian (PO)")
    # FASE G-0 — `purchasing.require_supplier_master` DULU tombol palsu (0 consumer di kode).
    # Sekarang benar-benar mengikat: bila aktif, PO WAJIB memilih supplier dari master
    # (bukan nama bebas) supaya 3-way match, kontrabon, dan riwayat harga tetap rapi.
    if not supplier_id:
        from services.config_resolver import value_of as _cfg_value
        if bool(await _cfg_value("purchasing.require_supplier_master",
                                 {"entity_id": active_entity_id})):
            raise HTTPException(
                status_code=400,
                detail=("PO wajib memilih supplier master (Pengaturan → Pembelian & Tagihan "
                        "Supplier → 'PO wajib memilih supplier master' aktif). Daftarkan "
                        f"'{supplier_name}' di menu Pemasok terlebih dahulu."))
    
    # Validate products and calculate total
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(1000)}
    # FASE F (PS-12) — jangan membelanjakan uang untuk barang yang spesifikasinya
    # belum sah (konsep/labdip/proofing) atau sudah dihentikan.
    from services import rnd_gate
    await rnd_gate.assert_orderable(
        [products[it.product_id] for it in payload.items if it.product_id in products],
        where="Purchase Order")
    raw_items = []
    _used_contracts: set = set()   # FASE F-2 — kontrak pembelian yang dipakai (untuk mark_used)

    from services.supplier_service import resolve_price
    # Fase 8 (Catch-weight) — siapkan faktor konversi untuk quantity_base (meter-ekuivalen).
    # Fase B (D-06/D-07) — plus aturan konversi GLOBAL + jejak konversi wajib.
    from services.uom_service import load_fixed_factors
    from services import uom_rules_service as uomr
    _uom_factors = await load_fixed_factors()
    _uom_engine = await uomr.load_engine()

    for item_in in payload.items:
        product = products.get(item_in.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Produk {item_in.product_id} tidak ditemukan")

        # FASE F-2 — harga & JEJAK SUMBER dari resolver terpadu (kontrak pembelian →
        # estimasi → harga terakhir barang supplier → price-list → master), sama seperti
        # PO hasil realisasi PR. Dulu PO manual hanya melihat price-list (kontrak diabaikan).
        from services.pr_sourcing_service import resolve_line_sourcing as _resolve_sourcing
        _src = await _resolve_sourcing(
            supplier_id=supplier_id, product_id=item_in.product_id,
            qty=float(item_in.quantity or 0),
            entity_id=payload.entity_id or active_entity_id or "",
            est_price=0.0, unit=item_in.unit or "")
        _price_source = _src.get("source") or ""
        _sourcing_explain = list(_src.get("explain") or [])
        _typed = float(item_in.price or 0)
        if _typed > 0:
            # User mengetik harga → HORMATI sebagai override, tetapi tetap simpan jejak kontrak.
            price = _typed
            _contract_price = float(_src.get("price") or 0)
            if _src.get("source") == "contract" and _contract_price > 0 and abs(price - _contract_price) > 0.005:
                _sourcing_explain.append(
                    f"Harga diisi manual (override) {rupiah(price)} — kontrak "
                    f"{_src.get('contract_number')} menawarkan {rupiah(_contract_price)}.")
                _price_source = "manual_override"
            elif _src.get("source") == "contract" and _contract_price > 0 and abs(price - _contract_price) <= 0.005:
                pass  # persis harga kontrak → biarkan source = contract
            else:
                _sourcing_explain.append(f"Harga diisi manual: {rupiah(price)}")
                _price_source = "manual"
        else:
            price = float(_src.get("price") or 0)
        if price <= 0:
            price = float(product.get("price", 0) or 0)
            if not _price_source:
                _price_source = "product_master"

        # Fase 8 — qty dalam BASE unit (meter) untuk perencanaan stok (on_order/ATP).
        # Fase B (D-07) — konversi WAJIB berjejak: satuan dokumen → satuan dasar,
        # memakai aturan GLOBAL/produk/formula (tidak pernah diam-diam memakai 1).
        base_unit = product.get("base_unit", "meter")
        order_unit = item_in.unit or base_unit
        _trail = None
        try:
            _trail = await uomr.convert_with_trail(
                product, float(item_in.quantity or 0), order_unit, base_unit,
                engine=_uom_engine, context="purchase_order")
            quantity_base = _trail["base_qty"]
        except uomr.UomRuleError as exc:
            if (order_unit or "").strip().lower() == (base_unit or "meter").strip().lower():
                quantity_base = round(float(item_in.quantity or 0), 2)
            else:
                raise HTTPException(status_code=400,
                                    detail=f"Item {product.get('sku', '')}: {exc}") from exc

        # Fase A · PS-09/D-19 — grade yang diharapkan WAJIB dipilih user (tanpa default).
        # Jalur turunan sistem (call-off kontrak) boleh menurunkan dari master produk.
        try:
            _eg = grade_service.resolve_expected_grade(
                getattr(item_in, "expected_grade", ""), product,
                allow_derive=(po_type == "call_off"))
        except DomainValidationError as exc:
            raise HTTPException(status_code=400,
                                detail=f"Item {product['sku']}: {exc.message}")

        # FASE E/F-1 — katalog barang versi supplier + FASE F-2 — jejak sumber harga.
        # Keduanya dari `_src` (satu lookup) supaya PO manual membawa jejak yang SAMA
        # seperti PO hasil realisasi PR (kontrak/last-price/manual) → terlihat di PODetailPanel.
        _supplier_item_stamp: Dict[str, Any] = {
            "supplier_item_id": _src.get("supplier_item_id", ""),
            "supplier_sku": _src.get("supplier_sku", ""),
            "supplier_item_name": _src.get("supplier_item_name", ""),
            "supplier_uom": _src.get("supplier_uom", ""),
            "supplier_conv_factor": _src.get("supplier_conv_factor", 0),
            "contract_id": _src.get("contract_id", ""),
            "contract_number": _src.get("contract_number", ""),
            "price_source": _price_source,
            "sourcing_explain": _sourcing_explain,
        }
        if _src.get("contract_id"):
            _used_contracts.add(_src["contract_id"])

        raw_items.append({
            "product_id": product["id"],
            "sku": product["sku"],
            "product_name": product["name"],
            # FASE L — snapshot lini kerja MD (siapa yang mengerjakan pembelian ini).
            "line_code": str(product.get("line_code") or "").strip().lower(),
            "expected_grade": _eg["grade"],              # PS-09 — ekspektasi mutu di awal PO
            "expected_grade_source": _eg["source"],
            "quantity": item_in.quantity,
            "unit": item_in.unit,
            "base_unit": base_unit,                # Fase 8 — satuan stok produk
            "quantity_base": quantity_base,        # Fase 8 — qty meter-ekuivalen (planning)
            "uom_trail": _trail or {},             # Fase B/D-07 — jejak konversi satuan
            "price": price,
            "discount_percent": float(item_in.discount_percent or 0),  # P0-1 — diskon item supplier
            "received_qty": 0.0,  # Tracking actual received
            # FASE U — dua satuan: `qty_rolls` DIKETIK (memesan = rencana), sedangkan
            # `received_rolls` adalah TURUNAN yang diakumulasi dari penerimaan nyata.
            **(await _dual.stamp(item_in)),
            "received_rolls": None,
            # FASE E/F-1 — katalog barang versi supplier distempel di baris PO agar layar
            # penerimaan bisa (a) menampilkan penamaan supplier dan (b) menerima qty dalam
            # SATUAN SUPPLIER tanpa lookup ulang. Kosong bila belum terdaftar.
            **_supplier_item_stamp,
        })

    entity_id = payload.entity_id or active_entity_id
    # P0-1 — breakdown harga PO: diskon item/order + DPP + PPN (Faktur Pajak Masukan).
    # INVARIAN-SAFE: total_amount tetap GROSS (Σ subtotal), pajak/diskon di field terpisah.
    pricing = await compute_order_pricing(
        raw_items, entity_id, payload.order_discount_percent,
        cfg_section="purchasing", tax_override=payload.tax_mode)
    items = pricing["items"]
    total_amount = pricing["total_amount"]
    grand_total = pricing["grand_total"]

    # Generate PO number (deletion-safe / max-based — P0-A)
    po_number = await next_doc_number("purchase_orders", "po_number", "PO-", entity_id=entity_id)

    # Fase 7.1 — kebutuhan approval BERJENJANG (multi-level) dari approval_rules + extra_levels
    appr = await build_approval_chain("purchase_order", total_amount, entity_id)
    approval_chain = appr["approval_chain"]
    needs_approval = appr["requires_approval"]
    required_role = appr["required_role"]
    approval_reason = "amount_threshold" if needs_approval else ""

    # Depth #3 — guard penyimpangan harga vs price-list supplier → wajib approval.
    from services.supplier_service import assess_price_deviation
    from services.config_service import get_effective_settings
    settings = await get_effective_settings(entity_id)
    threshold = float(settings.get("purchasing", {}).get("price_deviation_approval_percent", 10.0) or 10.0)
    price_deviation = await assess_price_deviation(supplier_id, items, threshold) if supplier_id else \
        {"flagged": False, "threshold_pct": threshold, "max_deviation_pct": 0.0, "items": []}
    if price_deviation["flagged"]:
        if not approval_chain:
            appr = await build_approval_chain("purchase_order", total_amount, entity_id, force_level1_role="manager")
            approval_chain = appr["approval_chain"]
        needs_approval = True
        required_role = approval_chain[0]["required_role"] if approval_chain else "manager"
        approval_reason = "price_deviation" if approval_reason == "" else "amount_threshold+price_deviation"

    # 4.b — call-off over-call (atau pemicu lain) → PAKSA approval dari awal.
    if force_approval:
        if not approval_chain:
            appr = await build_approval_chain("purchase_order", total_amount, entity_id, force_level1_role="manager")
            approval_chain = appr["approval_chain"]
        needs_approval = True
        required_role = approval_chain[0]["required_role"] if approval_chain else "manager"
        approval_reason = force_reason if not approval_reason else f"{approval_reason}+{force_reason}"

    # Depth #3 — riwayat/timeline approval PO.
    actor_name = payload.created_by or "Admin"
    _created_label = "Call-off dibuat" if po_type == "call_off" else "PO dibuat"
    _created_detail = f"{len(items)} item · {rupiah(total_amount)}"
    if parent:
        _created_detail += f" · dari kontrak {parent.get('po_number', '')}"
    if extra_note:
        _created_detail += f" · {extra_note}"
    po_timeline = [timeline_entry("created", _created_label, actor_name, _created_detail)]
    if needs_approval:
        dev_note = f"deviasi harga +{price_deviation['max_deviation_pct']}%" if price_deviation["flagged"] else "nilai melebihi batas"
        po_timeline.append(timeline_entry(
            "submitted_for_approval", f"Menunggu persetujuan {required_role}", actor_name, dev_note))

    # Create PO document
    po = {
        "id": new_id("po"),
        "po_number": po_number,
        "po_type": po_type,
        "parent_po_id": (parent or {}).get("id", ""),
        "parent_po_number": (parent or {}).get("po_number", ""),
        "call_off_note": extra_note if po_type == "call_off" else "",
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "supplier_contact": supplier_contact,
        "supplier_npwp": supplier_npwp,
        "warehouse_id": payload.warehouse_id,
        "warehouse_name": warehouse["name"],
        "warehouse_city": warehouse.get("city", ""),
        "items": items,
        # FASE L — turunan baris untuk chip penyaring & papan PO per lini (FASE P).
        "line_codes": sorted({str(it.get("line_code") or "").strip().lower()
                              for it in items if (it.get("line_code") or "").strip()}),
        "total_amount": total_amount,
        # P0-1 — breakdown diskon + PPN (Faktur Pajak Masukan). Invariant-safe.
        "items_discount_total": pricing["items_discount_total"],
        "order_discount_percent": pricing["order_discount_percent"],
        "order_discount_amount": pricing["order_discount_amount"],
        "discount_total": pricing["discount_total"],
        "net_subtotal": pricing["net_subtotal"],
        "dpp": pricing["dpp"],
        "ppn_rate": pricing["ppn_rate"],
        "ppn_mode": pricing["ppn_mode"],
        "is_pkp": pricing["is_pkp"],
        "ppn_amount": pricing["ppn_amount"],
        "grand_total": grand_total,
        "tax_mode": payload.tax_mode or "",
        "import_flag": payload.import_flag,   # R0 — override asal barang (None=ikut supplier)
        "entity_id": entity_id,
        "expected_delivery_date": payload.expected_delivery_date,
        "notes": payload.notes,
        # waiting_approval → pending → receiving → completed / partial / cancelled
        "status": "waiting_approval" if needs_approval else "pending",
        "approval_required": needs_approval,
        "required_approval_role": required_role,
        "approval_status": "pending" if needs_approval else "not_required",
        "approval_chain": approval_chain,
        "approval_level_current": (approval_chain[0]["level"] if (needs_approval and approval_chain) else 0),
        "approval_levels_total": len(approval_chain),
        "approval_amount": total_amount,
        "approval_reason": approval_reason,
        "price_deviation": price_deviation,
        "timeline": po_timeline,
        # Depth 1C — pelacakan pembayaran / hutang (AP)
        "amount_paid": 0.0,
        "returned_amount": 0.0,
        "outstanding": round(grand_total, 2),
        "payment_status": "unpaid",
        "payments": [],
        # Phase 7.2 — Amendment / Version History
        "version": 1,
        "amendments": [],
        # R6.3 — Budget Control: tag anggaran PO (default akun Persediaan bila tak di-tag)
        "budget_dimension": (payload.budget_dimension or "").strip(),
        "budget_key": (payload.budget_key or "").strip(),
        "created_by": payload.created_by,
        "created_by_id": actor.get("id", ""),
        "created_at": now_iso(),
        "updated_at": now_iso()
    }

    # R6.3 — Budget Control: cek anggaran (mode off/warn/block configurable per entitas).
    from services import budget_service
    try:
        budget_check = await budget_service.enforce_po_budget(po, "po_create", actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    po["budget_check"] = budget_check
    if budget_check.get("warnings"):
        po["timeline"].append(timeline_entry(
            "budget_warning", "Peringatan anggaran", actor_name, " · ".join(budget_check["warnings"])[:400]))

    await db.purchase_orders.insert_one(po)

    # FASE F-2 — tandai kontrak pembelian yang dipakai (usage_count + last_used_at).
    if _used_contracts:
        from services import contract_service as _cs
        for _cid in _used_contracts:
            try:
                await _cs.mark_used(_cid)
            except Exception:  # noqa: BLE001 — best-effort, jangan gagalkan PO
                pass
    # Inbound task dibuat hanya bila PO TIDAK butuh approval (atau nanti setelah approve)
    if not needs_approval:
        await _create_inbound_tasks_for_po(po)

    await audit(actor["name"], "po_created", "purchase_order", po["id"], {
        "po_number": po_number,
        "supplier": supplier_name,
        "supplier_id": supplier_id,
        "total_amount": total_amount,
        "approval_required": needs_approval,
        "required_role": required_role,
        "approval_reason": approval_reason,
    })

    # Depth #3 — notifikasi ke role approver bila PO butuh persetujuan.
    if needs_approval:
        from services.notification_service import notify_po_awaiting_approval
        await notify_po_awaiting_approval(po)

    return safe_doc(po)


@router.post("/purchase-orders/{po_id}/amend")
async def amend_purchase_order(po_id: str, payload: PurchaseOrderAmend, request: Request) -> Dict[str, Any]:
    """Phase 7.2 — amandemen PO (item/supplier/tanggal/catatan) + version history + re-approval penuh.

    Aturan owner: ubah semua field (1.c); SELALU re-approval dari awal (2.a); boleh saat partial
    receiving — qty tak boleh < qty diterima & item ber-penerimaan tak bisa dihapus (3.b); simpan
    snapshot penuh + diff tiap versi (4.a); alasan + audit WAJIB (5.a).

    Domain logic diekstrak ke ``services/po_amendment_service.py`` (jaga batas ukuran router ≤800).
    Service mengembalikan ``{po, needs_approval}``; router memutuskan inbound task / notifikasi.
    """
    actor = await require_permission(request, "purchase_order", "update")
    result = await amend_po_service(po_id, payload, actor)
    updated = result["po"]
    if result["needs_approval"]:
        from services.notification_service import notify_po_awaiting_approval
        await notify_po_awaiting_approval(updated)
    else:
        await _create_inbound_tasks_for_po(updated)
    return safe_doc(await db.purchase_orders.find_one({"id": po_id}, {"_id": 0}))


@router.post("/purchase-orders/{po_id}/approve")
async def approve_purchase_order(po_id: str, request: Request) -> Dict[str, Any]:
    """Fase 1B — approve PO (role dinamis dari matriks). Setelah approve, PO
    masuk status 'pending' dan inbound receiving task otomatis dibuat."""
    actor = await current_user(request)
    po = safe_doc(await db.purchase_orders.find_one({"id": po_id}, {"_id": 0}))
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
    if po.get("status") != "waiting_approval":
        raise HTTPException(status_code=409, detail=f"PO status '{po.get('status')}' tidak menunggu approval")
    required = po.get("required_approval_role")
    if not role_satisfies(actor.get("role"), required):
        raise HTTPException(
            status_code=403,
            detail=f"Approval PO butuh role minimal '{required}'. Role Anda: '{actor.get('role')}'.")
    # H2 — Segregation of Duties: pembuat PO tidak boleh menyetujui PO-nya sendiri.
    creator_id = po.get("created_by_id")
    if creator_id and creator_id == actor.get("id"):
        raise HTTPException(
            status_code=403,
            detail="Pemisahan tugas (SoD): pembuat PO tidak boleh menyetujui PO sendiri. Minta approver lain.")

    # R6.3 — Budget Control: cek anggaran SEBELUM approval diproses (semua tingkat).
    # Komitmen PO ini sendiri dikecualikan agar tidak dihitung ganda.
    from services import budget_service
    try:
        budget_check = await budget_service.enforce_po_budget(po, "po_approve", actor, exclude_po_id=po_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Fase 7.1 — approval BERJENJANG: tandai level berjalan approved, lalu lanjut/selesai.
    chain = po.get("approval_chain") or [{"level": 1, "required_role": required, "status": "pending",
                                          "approved_by": "", "approved_by_id": "", "approved_at": ""}]
    pending = current_pending_level(chain)
    if pending is None:
        raise HTTPException(status_code=409, detail="Semua tingkat approval sudah disetujui.")
    pending["status"] = "approved"
    pending["approved_by"] = actor["name"]
    pending["approved_by_id"] = actor.get("id", "")
    pending["approved_at"] = now_iso()

    next_pending = current_pending_level(chain)
    if next_pending is not None:
        # Masih ada tingkat berikutnya → tetap menunggu approval tingkat selanjutnya.
        updated = await db.purchase_orders.find_one_and_update(
            {"id": po_id},
            {"$set": {"status": "waiting_approval", "approval_status": "pending",
                      "approval_chain": chain, "required_approval_role": next_pending["required_role"],
                      "approval_level_current": next_pending["level"], "budget_check": budget_check,
                      "updated_at": now_iso()},
             "$push": {"timeline": timeline_entry(
                 "approved_level", f"Disetujui tingkat {pending['level']} ({pending.get('label','')})",
                 actor["name"], f"Lanjut ke {next_pending.get('label', next_pending['required_role'])}")}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        try:
            from services.notification_service import (notify_po_awaiting_approval,
                                                       resolve_action)
            # Padamkan dulu permintaan tingkat sebelumnya, baru terbitkan permintaan
            # tingkat berikutnya — supaya lonceng tidak menampilkan dua permintaan
            # untuk PO yang sama.
            await resolve_action("po_approve", po_id,
                                 outcome=f"disetujui tingkat {pending['level']}",
                                 actor=actor["name"])
            await notify_po_awaiting_approval(updated)
        except Exception:  # noqa: BLE001
            pass
        await audit(actor["name"], "po_approved_level", "purchase_order", po_id,
                    {"po_number": po.get("po_number"), "level": pending["level"],
                     "next_role": next_pending["required_role"]})
        return safe_doc(updated)

    # Semua tingkat selesai → PO disetujui penuh.
    updated = await db.purchase_orders.find_one_and_update(
        {"id": po_id},
        {"$set": {"status": "pending", "approval_status": "approved", "approval_chain": chain,
                  "approval_level_current": 0, "budget_check": budget_check,
                  "approved_by": actor["name"], "approved_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry(
             "approved", f"Disetujui penuh ({len(chain)} tingkat)", actor["name"],
             " · ".join(budget_check.get("warnings") or [f"tingkat akhir oleh role {actor.get('role')}"])[:400])}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    # Buat inbound task setelah PO disetujui penuh
    await _create_inbound_tasks_for_po(updated)
    try:
        from services.notification_service import resolve_action
        await resolve_action("po_approve", po_id, outcome="disetujui penuh",
                             actor=actor["name"])
    except Exception:  # noqa: BLE001
        pass
    await audit(actor["name"], "po_approved", "purchase_order", po_id,
                {"po_number": po.get("po_number"), "total_amount": po.get("total_amount"),
                 "levels": len(chain)})
    return safe_doc(updated)


@router.post("/purchase-orders/{po_id}/reject")
async def reject_purchase_order(po_id: str, request: Request) -> Dict[str, Any]:
    """Fase 3 — tolak PO yang menunggu approval (role dinamis dari matriks).
    PO → status 'rejected'; tidak ada inbound task yang dibuat."""
    actor = await current_user(request)
    po = safe_doc(await db.purchase_orders.find_one({"id": po_id}, {"_id": 0}))
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
    if po.get("status") != "waiting_approval":
        raise HTTPException(status_code=409, detail=f"PO status '{po.get('status')}' tidak menunggu approval")
    required = po.get("required_approval_role")
    if not role_satisfies(actor.get("role"), required):
        raise HTTPException(
            status_code=403,
            detail=f"Reject PO butuh role minimal '{required}'. Role Anda: '{actor.get('role')}'.")
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    reason = (body or {}).get("reason", "")
    updated = await db.purchase_orders.find_one_and_update(
        {"id": po_id},
        {"$set": {"status": "rejected", "approval_status": "rejected",
                  "rejected_by": actor["name"], "rejection_reason": reason,
                  "rejected_at": now_iso(), "updated_at": now_iso()},
         "$push": {"timeline": timeline_entry("rejected", "Ditolak", actor["name"], reason)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    await audit(actor["name"], "po_rejected", "purchase_order", po_id,
                {"po_number": po.get("po_number"), "reason": reason})
    try:
        from services.notification_service import resolve_action
        await resolve_action("po_approve", po_id, outcome="ditolak", actor=actor["name"])
    except Exception:  # noqa: BLE001
        pass
    return safe_doc(updated)


@router.get("/purchase-orders/{po_id}")
async def get_purchase_order(po_id: str, request: Request) -> Dict[str, Any]:
    """Get purchase order detail."""
    await require_permission(request, "purchase_order", "view")
    ctx = await entity_ctx(request)
    po = safe_doc(await db.purchase_orders.find_one({"id": po_id}, {"_id": 0}))
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order tidak ditemukan")
    assert_entity_access(po, "purchase_orders", ctx)

    # P2 — Blanket PO: lampirkan drawdown (called/remaining + daftar call-off).
    if po.get("po_type") == "blanket":
        draw = await blanket_po_service.recompute_blanket_drawdown(po, persist=True)
        for k in ("contract_items", "value_called", "value_remaining", "contract_status",
                  "call_offs", "call_off_count"):
            po[k] = draw[k]
        return po

    # Get related inbound tasks
    tasks = await db.wms_tasks.find({"po_id": po_id}, {"_id": 0}).to_list(100)
    po["inbound_tasks"] = tasks
    # Depth 1C — ringkasan keuangan + retur terkait
    po["financials"] = _po_financials(po)
    rets = await db.purchase_returns.find({"po_id": po_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    po["returns"] = rets

    return po


