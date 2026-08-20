"""Sales orders router: create + get/update SO.

Endpoint read/preview/stats & lifecycle-action (submit/approve/confirm/cancel/…)
dipindah ke `routers/sales_orders_extra.py` agar file di bawah batas guardrail.
`create_order` sengaja tetap di sini karena di-import oleh `routers/special_orders.py`.
"""
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from services import dual_qty_service as _dual  # FASE U — dua satuan (roll + ukuran)
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID, next_doc_number, strip_cost_fields, rupiah
from schemas import GenericPatch, SalesOrderCreate
from services.roll_service import (
    allocate_and_reserve_rolls, release_order_rolls,
    preview_line_allocation, _release_rolls_by_ref_id,
)
from services.config_service import (
    compute_order_pricing, evaluate_approval, get_allocation_policy, get_effective_settings,
)
from services import so_approvals
from routers.price_approvals import get_effective_special_price
from services.uom_service import to_base, load_fixed_factors
from services.customer_service import evaluate_credit_gate, resolve_customer_sales_team
from entity_scope import entity_ctx, assert_entity_access
from services import costing_service
from services import pricelist_service
from services import customer_price_service  # F1b — harga langganan per pelanggan
from services import product_exclusivity as pexcl
from services import line_scope
from services import sales_ownership          # FASE E-8 (E8.4/US11) — "Pesanan Saya"
from services.sales_order_helpers import (
    reserve_roll_mode_item as _reserve_roll_mode_item,
    norm_backorder as _norm_backorder,
    normalize_sales_team,
)
from services.so_status import stage_fields
from request_context import active_entity_or

router = APIRouter(prefix="/api")


async def _validate_min_cut(items: List[Dict[str, Any]], entity_id: str) -> None:
    """FASE G-0 — tegakkan `inventory.min_cut_qty` (dulu tombol palsu tanpa consumer).

    Aturan bisnis: kain tidak boleh dipotong lebih pendek dari batas minimum, karena
    sisa roll yang terlalu pendek praktis tidak terjual. Batas ini CONFIGURABLE per
    entitas dari Pusat Pengaturan → Stok, Satuan & Alokasi.
    """
    from services.config_resolver import value_of
    try:
        min_cut = float(await value_of("inventory.min_cut_qty", {"entity_id": entity_id}) or 0)
    except (TypeError, ValueError):
        min_cut = 0.0
    if min_cut <= 0:
        return
    for it in items:
        qty = float(it.get("base_quantity") or it.get("quantity") or 0)
        if 0 < qty < min_cut:
            raise HTTPException(
                status_code=400,
                detail=(f"{it.get('product_name') or it.get('product_id')}: qty {qty:g} "
                        f"{it.get('base_unit', '')} di bawah minimum potong {min_cut:g}. "
                        f"Naikkan qty atau ubah 'Minimum panjang potong kain' di Pengaturan."))


@router.post("/sales-orders")
async def create_order(payload: SalesOrderCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "create")
    # Diskon manual DIHAPUS untuk SEMUA role — potongan harga HANYA via "Ajukan Harga
    # Khusus" (special-price) yang disetujui manager/admin. Payload discount diabaikan.
    customer = safe_doc(await db.customers.find_one({"id": payload.customer_id}, {"_id": 0}))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    # FASE E-7 (E7.2/E7.7) — badan usaha grup diperlakukan sebagai PEMASOK di sisi
    # pembeli, BUKAN pelanggan. SO biasa ke badan usaha grup melewati dokumen kembar &
    # eliminasi margin, jadi laba grup akan terlihat lebih besar dari kenyataan.
    from services import group_partner_service as _grp
    await _grp.assert_customer_not_group_entity(customer, doc_label="Pesanan Penjualan (SO)")
    address = next(
        (a for a in customer.get("addresses", []) if a["id"] == payload.shipping_address_id),
        customer.get("addresses", [{}])[0]
    )
    # S-3 (Gelombang 2) — validasi Order Pengambilan di API (bukan hanya FE):
    # method 'ambil' WAJIB punya pickup_date valid (ISO, tidak di masa lalu).
    fulfillment_method = (getattr(payload, "fulfillment_method", "kirim") or "kirim").strip().lower()
    if fulfillment_method == "ambil":
        pd = (getattr(payload, "pickup_date", "") or "").strip()
        if not pd:
            raise HTTPException(status_code=400,
                                detail="Order Pengambilan membutuhkan tanggal ambil (pickup_date).")
        try:
            pickup_dt = datetime.fromisoformat(pd).date()
        except ValueError:
            raise HTTPException(status_code=400,
                                detail="Format tanggal ambil tidak valid (gunakan YYYY-MM-DD).")
        if pickup_dt < datetime.now(timezone.utc).date():
            raise HTTPException(status_code=400, detail="Tanggal ambil tidak boleh di masa lalu.")
    # F-SHIP (Gelombang 2+) — metode 'kirim' boleh punya request tanggal pengiriman OPSIONAL.
    # Bila diisi: format ISO valid & tidak di masa lalu (hanya hari ini ke depan).
    delivery_date = (getattr(payload, "delivery_date", "") or "").strip()
    if fulfillment_method == "kirim" and delivery_date:
        try:
            delivery_dt = datetime.fromisoformat(delivery_date).date()
        except ValueError:
            raise HTTPException(status_code=400,
                                detail="Format tanggal pengiriman tidak valid (gunakan YYYY-MM-DD).")
        if delivery_dt < datetime.now(timezone.utc).date():
            raise HTTPException(status_code=400, detail="Tanggal pengiriman tidak boleh di masa lalu.")
    # S-5 (Gelombang 2) — lookup produk TERARAH by id (bukan cap 100 pertama katalog).
    prod_ids = list({it.product_id for it in payload.items})
    products = {p["id"]: p for p in await db.products.find(
        {"id": {"$in": prod_ids}}, {"_id": 0}).to_list(len(prod_ids) + 1)}
    # FASE F (PS-12) — produk yang belum dirilis ke produksi tidak boleh dijual.
    # Produk lama tanpa `lifecycle` dianggap `produksi` → transaksi existing aman.
    from services import rnd_gate
    await rnd_gate.assert_orderable(list(products.values()), entity_id=payload.entity_id or "",
                                    where="Pesanan Penjualan")
    fixed_factors = await load_fixed_factors()   # Sub-fase 1.13 — peta faktor UOM (FIXED)
    # Resolusi entitas penjual lebih awal (dibutuhkan untuk validasi harga khusus)
    # FASE E-1 (E1.10) — badan usaha penjual: payload → pelanggan → KONTEKS AKTIF.
    # `DEFAULT_ENTITY_ID` hanya cadangan terakhir (skrip/seed di luar request).
    entity_id = (payload.entity_id or customer.get("entity_id")
                 or active_entity_or(DEFAULT_ENTITY_ID))
    # F1a/F1b — harga jual: harga langganan PELANGGAN → harga per-entitas (PT) →
    # harga global `products.price`. Harga khusus per-order (price_approvals) tetap
    # menang di bawah, karena itu keputusan sadar yang disetujui manajemen.
    entity_price_map = await customer_price_service.resolve_many(
        entity_id, customer["id"], [it.product_id for it in payload.items], products)
    raw_items = []
    special_count = 0
    for item_in in payload.items:
        product = products.get(item_in.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Produk {item_in.product_id} tidak ditemukan")
        # PS-20 — SO dari item eksklusif hanya boleh dibuat pemiliknya (atau role non-sales).
        pexcl.assert_can_order(actor, product)
        # FASE L — pagar lini: staf printing tidak boleh menjual kain woven. Ditolak 403
        # ber-kalimat Indonesia (bukan 500, bukan daftar kosong tanpa sebab — user story L.G #3).
        line_scope.assert_can_order(actor, product)
        # Sub-fase 1.13 — harga per BASE unit; saat jual di unit lain harga di-skala faktor.
        # (mis. price/meter × (meter per 1 yard) = price/yard) → subtotal konsisten ke base.
        # Faktor dihitung presisi tinggi (precision=6) agar harga tidak kehilangan akurasi;
        # base_quantity (inventori) tetap dibulatkan ke precision 2.
        sell_factor = to_base(product, 1.0, item_in.unit, fixed_factors, precision=6)
        base_sell_price = float((entity_price_map.get(product["id"]) or {}).get("price", product["price"]))
        unit_price = round(base_sell_price * sell_factor, 2)
        special_meta: Dict[str, Any] = {}
        appr_id = (getattr(item_in, "price_approval_id", "") or "").strip()
        if appr_id:
            # Sub-fase 1.7 — harga khusus: harus approved, berlaku, & qty >= min.
            appr = await get_effective_special_price(
                entity_id, customer["id"], product["id"], item_in.quantity, approval_id=appr_id,
            )
            if not appr:
                raise HTTPException(
                    status_code=400,
                    detail=f"Harga khusus untuk {product['name']} tidak berlaku (belum disetujui / kadaluarsa / qty di bawah minimum)",
                )
            unit_price = float(appr["requested_price"])
            special_count += 1
            special_meta = {
                "price_approval_id": appr["id"],
                "special_price": True,
                "normal_price": round(base_sell_price * sell_factor, 2),
            }
        raw_items.append({
            "product_id": product["id"], "sku": product["sku"], "product_name": product["name"],
            "quantity": item_in.quantity, "unit": item_in.unit, "price": unit_price,
            "discount_percent": 0,  # diskon manual dihapus — potongan hanya via Harga Khusus
            # FASE U — dua satuan. Mode "beli per roll" sudah memilih roll secara eksplisit,
            # jadi jumlah rollnya DIHITUNG dari pilihan itu (bukan diketik dua kali).
            **(await _dual.stamp(
                item_in,
                rolls=(len(item_in.roll_lines) if getattr(item_in, "purchase_mode", "qty") == "roll"
                       and getattr(item_in, "roll_lines", None) else None))),
            # F1b — SNAPSHOT asal harga (pelanggan / PT / global) supaya laporan & audit
            # bisa menjawab "harga ini dari mana" tanpa menebak.
            "price_source": ((entity_price_map.get(product["id"]) or {}).get("source", "global")
                             if not special_meta else "special_approval"),
            "price_record_id": (entity_price_map.get(product["id"]) or {}).get("record_id") or "",
            **special_meta,
        })
    number = await next_doc_number("sales_orders", "number", "SO-", entity_id=entity_id)
    customer_city = address.get("city", customer.get("city", ""))
    # Fase 1B — pricing engine (diskon item/order + PPN, ikut PKP entitas). INVARIAN-SAFE.
    pricing = await compute_order_pricing(raw_items, entity_id, 0, tax_override=(payload.tax_override or "").strip().lower() or None)
    items = pricing["items"]
    # Sub-fase 1.8 (UOM-safe, forward-compat 1.13): simpan base_unit + base_quantity per item.
    for it in items:
        prod = products.get(it.get("product_id"), {})
        it["base_unit"] = prod.get("base_unit", "meter")
        # Sub-fase 1.13 — base_quantity = qty dikonversi ke base unit (meter).
        it["base_quantity"] = to_base(prod, float(it.get("quantity", 0) or 0), it.get("unit", "meter"), fixed_factors)
        # EPIC2 — snapshot kategori produk ke SO line (basis laporan & insentif per kategori).
        it["category"] = prod.get("category", "")
        # FASE L — SNAPSHOT lini kerja. Sengaja disimpan di baris, bukan di-join ke
        # master saat dibaca: kalau lini produk dipindah besok, riwayat pesanan hari
        # ini tidak boleh ikut berpindah (POC L5).
        it["line_code"] = str(prod.get("line_code") or "").strip().lower()
        # P2-3 — snapshot cost-at-sale (per base unit) agar margin insentif STABIL
        # walau WAC/stok berubah kemudian. Prioritas: WAC saat ini → harga_pokok.
        try:
            w = await costing_service.wac_for_product(it["product_id"], entity_id=entity_id, product=prod)
            cost = float(w.get("wac") or 0)
        except Exception:
            cost = 0.0
        if cost <= 0:
            cost = float(prod.get("harga_pokok") or 0)
        it["unit_cost"] = round(cost, 2)
    # FASE G-0 — `inventory.min_cut_qty` DULU tombol palsu (0 consumer di kode). Sekarang
    # benar-benar menjaga: panjang potong di bawah minimum ditolak agar tidak lahir sisa
    # roll yang terlalu pendek untuk dijual.
    await _validate_min_cut(items, entity_id)
    # FASE G-0 — `sales.allow_partial_shipment` DULU tidak dibaca kode mana pun (hanya muncul
    # sebagai NILAI string `shipment_policy`). Sekarang benar-benar mengikat: bila kebijakan
    # kirim-sebagian dimatikan, pesanan dipaksa berkebijakan kirim penuh.
    from services.config_resolver import value_of as _cfg_value
    _shipment_policy = (payload.shipment_policy or "allow_partial_shipment").strip()
    if not bool(await _cfg_value("sales.allow_partial_shipment", {"entity_id": entity_id})):
        _shipment_policy = "require_full_shipment"
    total_amount = pricing["total_amount"]            # GROSS = Σ subtotal (invarian)
    # Term pembayaran: pilihan user → fallback default settings
    term_code = (payload.payment_term_code or "").strip()
    if not term_code:
        gs = await db.system_settings.find_one({"scope": "global"}, {"_id": 0}) or {}
        term_code = (gs.get("finance", {}) or {}).get("default_payment_term_code", "NET30")
    # FASE E-4 (E4.3) — syarat bayar BERLAPIS: override badan usaha menang atas global.
    # Tanpa ini pesanan CV Kanda Suka bisa memakai net_days milik baris global.
    from services import entity_master_service as _ems
    term = await _ems.resolve_row("payment-terms", term_code, entity_id)
    # Fase 1B — kebutuhan approval dinamis dari approval_rules (basis grand_total)
    appr = await evaluate_approval("sales_order", pricing["grand_total"], entity_id)
    # KN_17 §5.2 / S37 — Gate kredit. F5 (KEPUTUSAN OWNER §1c): TIDAK lagi blokir 409.
    # Bila over-limit & belum ada override approved → SO TETAP dibuat + dibuat entri
    # pending_approval `kredit` (tombol "Minta Approval Kredit" di detail SO).
    credit_gate = await evaluate_credit_gate(customer, pricing["grand_total"])
    credit_needs_approval = bool(credit_gate["blocked"] and not credit_gate["override"])
    order_id = new_id("so")
    # Sub-fase 1.7 — resolve allocation policy (system→customer→order override)
    alloc_policy = await get_allocation_policy(entity_id, customer)
    # SALES REVAMP V2 — peta item mode "Beli per Roll" (pilihan roll eksplisit) per produk.
    roll_mode_map: Dict[str, List[Dict[str, Any]]] = {}
    for it_in in payload.items:
        if getattr(it_in, "purchase_mode", "qty") == "roll" and getattr(it_in, "roll_lines", None):
            roll_mode_map[it_in.product_id] = [rl.model_dump() for rl in it_in.roll_lines]
    # Mixed-Lot Confirmation gate: bila kebijakan prefer_single tapi hasil lintas-lot,
    # tolak (409 terstruktur) kecuali user sudah konfirmasi (confirm_mixed_lot=true).
    # Item mode 'roll' DILEWATI (user sudah pilih roll/lot eksplisit).
    if not payload.confirm_mixed_lot:
        mixed_items: List[Dict[str, Any]] = []
        for item in items:
            if item["product_id"] in roll_mode_map:
                continue
            prev = await preview_line_allocation(
                item["product_id"], item["base_quantity"], customer_city, entity_id, alloc_policy,
                customer_id=payload.customer_id)
            if prev.get("requires_confirmation"):
                mixed_items.append({
                    "product_id": item["product_id"],
                    "product_name": item.get("product_name") or item.get("name", item["product_id"]),
                    "lots_used": prev.get("lots_used", []),
                    "reserved_qty": prev.get("reserved_qty", 0),
                    "backorder_qty": prev.get("backorder_qty", 0),
                    "explanation": prev.get("explanation", ""),
                })
        if mixed_items:
            raise HTTPException(status_code=409, detail={
                "code": "MIXED_LOT_CONFIRMATION_REQUIRED",
                "message": "Pesanan akan dipenuhi dari beberapa lot berbeda. Konfirmasi diperlukan.",
                "mixed_items": mixed_items,
            })
    # Multi-item reservation di LEVEL ROLL (owner-scoped = entitas penjual; KN_15)
    # Sub-fase 1.6 — bila allow_backorder: reservasi parsial + sisa jadi backorder.
    all_allocations: List[Dict[str, Any]] = []
    backorders: List[Dict[str, Any]] = []
    created_transfer_ids: List[str] = []   # SALES REVAMP V2 — transfer antar-entitas auto (1.b)
    total_pending_ic = 0.0                  # qty menunggu transfer antar-entitas (cross)
    is_split = False
    has_backorder = False
    has_mixed_lot = False
    warehouses_map = {w["id"]: w for w in await db.warehouses.find({}, {"_id": 0}).to_list(200)}
    try:
        for item in items:
            # ── SALES REVAMP V2 — Mode "Beli per Roll" (pilihan roll eksplisit) ──
            if item["product_id"] in roll_mode_map:
                rr = await _reserve_roll_mode_item(
                    order_id, item["product_id"], roll_mode_map[item["product_id"]],
                    entity_id, actor["name"], warehouses_map, products,
                )
                allocs = rr["allocations"]
                created_transfer_ids.extend(rr["transfer_ids"])
                reserved_qty = round(float(rr["reserved_qty"]), 2)
                pending_ic = round(float(rr["pending_qty"]), 2)
                total_pending_ic += pending_ic
                item["reserved_qty"] = reserved_qty
                item["purchase_mode"] = "roll"
                item["roll_lines"] = roll_mode_map[item["product_id"]]
                item["intercompany"] = rr["intercompany"]
                item["intercompany_pending_qty"] = pending_ic
                item["linked_transfer_ids"] = rr["transfer_ids"]
                backorder_qty = round(float(item["base_quantity"]) - reserved_qty - pending_ic, 2)
                if backorder_qty < 0.01:
                    backorder_qty = 0.0
                item["backorder_qty"] = backorder_qty
                if len(allocs) > 1:
                    is_split = True
                item_lots = {l for a in allocs for l in (a.get("lots") or []) if l}
                if len(item_lots) > 1:
                    has_mixed_lot = True
                all_allocations.extend(allocs)
                if backorder_qty > 0.01:
                    has_backorder = True
                    backorders.append({
                        "id": new_id("bo"), "product_id": item["product_id"], "sku": item.get("sku", ""),
                        "product_name": item.get("product_name", ""), "entity_id": entity_id,
                        "customer_city": customer_city, "requested_qty": round(float(item["base_quantity"]), 2),
                        "reserved_qty": reserved_qty, "backorder_qty": backorder_qty,
                        "status": "waiting_stock", "created_at": now_iso(), "updated_at": now_iso(),
                    })
                continue
            # ── Mode "qty" (per yard, FEFO auto) — perilaku lama ──
            allocs = await allocate_and_reserve_rolls(
                item["product_id"], item["base_quantity"], customer_city, entity_id, order_id,
                allow_partial=payload.allow_backorder, policy=alloc_policy, customer_id=payload.customer_id,
            )
            reserved_qty = round(sum(float(a.get("quantity", 0) or 0) for a in allocs), 2)
            backorder_qty = round(float(item["base_quantity"]) - reserved_qty, 2)
            if backorder_qty < 0.01:
                backorder_qty = 0.0
            # Anotasi fulfillment per baris (Sub-fase 1.6)
            item["reserved_qty"] = reserved_qty
            item["backorder_qty"] = backorder_qty
            if len(allocs) > 1:
                is_split = True
            item_lots = {l for a in allocs for l in (a.get("lots") or []) if l}
            if len(item_lots) > 1:
                has_mixed_lot = True
            all_allocations.extend(allocs)
            if backorder_qty > 0.01:
                has_backorder = True
                backorders.append({
                    "id": new_id("bo"),
                    "product_id": item["product_id"],
                    "sku": item.get("sku", ""),
                    "product_name": item.get("product_name", ""),
                    "entity_id": entity_id,
                    "customer_city": customer_city,
                    "requested_qty": round(float(item["base_quantity"]), 2),
                    "reserved_qty": reserved_qty,
                    "backorder_qty": backorder_qty,
                    "status": "waiting_stock",
                    "created_at": now_iso(), "updated_at": now_iso(),
                })
    except HTTPException:
        await release_order_rolls(order_id)
        for _tid in created_transfer_ids:
            await _release_rolls_by_ref_id(_tid)
        if created_transfer_ids:
            await db.warehouse_transfers.delete_many({"id": {"$in": created_transfer_ids}})
        raise
    except Exception as e:
        await release_order_rolls(order_id)
        for _tid in created_transfer_ids:
            await _release_rolls_by_ref_id(_tid)
        if created_transfer_ids:
            await db.warehouse_transfers.delete_many({"id": {"$in": created_transfer_ids}})
        raise HTTPException(status_code=500, detail=str(e))
    expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    # Status awal (Sub-fase 1.6.1 — decouple status & backorder):
    #   - reserved      : ada porsi ter-reservasi / menunggu transfer antar-entitas
    #   - waiting_stock : 0 reserved (pure backorder — menunggu stok masuk)
    #   - draft         : tidak ada apa-apa
    total_reserved = round(sum(float(it.get("reserved_qty", 0) or 0) for it in items), 2)
    if total_reserved > 0.01 or total_pending_ic > 0.01:
        initial_status = "reserved"
    elif has_backorder:
        initial_status = "waiting_stock"
    else:
        initial_status = "draft"
    # F5 — Unified Approval SSOT: kumpulkan pending_approvals (nilai + kredit) saat create.
    settings_eff = await get_effective_settings(entity_id)
    require_val = so_approvals.require_validation_default(settings_eff)
    pending_approvals: List[Dict[str, Any]] = []
    if appr["requires_approval"]:
        pending_approvals.append(so_approvals.make_approval(
            "nilai", required_role=appr["required_role"] or "manager",
            reason=f"Nilai order {rupiah(pricing['grand_total'])} memerlukan persetujuan.",
            requested_by=actor["name"], requested_by_id=actor["id"],
            amount=pricing["grand_total"],
        ))
    credit_override_doc_id = ""
    if credit_needs_approval:
        credit_override_doc_id = new_id("cro")
        pending_approvals.append(so_approvals.make_approval(
            "kredit", required_role="manager",
            reason="; ".join(credit_gate.get("reasons", []) or []) or "Melebihi limit kredit pelanggan.",
            requested_by=actor["name"], requested_by_id=actor["id"], ref_id=credit_override_doc_id,
            amount=pricing["grand_total"],
        ))
    _afields = so_approvals.approval_fields(
        {"pending_approvals": pending_approvals, "required_approval_role": appr["required_role"]},
        require_validation=require_val,
    )
    order = {
        "id": order_id, "number": number, "status": initial_status,
        "entity_id": entity_id,
        "customer_id": customer["id"], "customer_name": customer["name"],
        "customer_city": customer.get("city") or address.get("city"),
        "shipping_address": address, "shipping_address_id": payload.shipping_address_id,
        "shipping_city": address.get("city") or customer.get("city"),
        "items": items, "allocations": all_allocations, "total_amount": total_amount,
        # FASE L — turunan dari baris (bukan diketik): dipakai chip penyaring lini &
        # papan PO. Dihitung sekali di sini supaya daftar tidak perlu membongkar items.
        "line_codes": sorted({str(it.get("line_code") or "").strip().lower()
                              for it in items if (it.get("line_code") or "").strip()}),
        # Fase 1B — breakdown diskon + pajak (field terpisah; invarian total_amount tetap GROSS)
        "items_discount_total": pricing["items_discount_total"],
        "order_discount_percent": pricing["order_discount_percent"],
        "order_discount_amount": pricing["order_discount_amount"],
        "discount_total": pricing["discount_total"],
        "net_subtotal": pricing["net_subtotal"],
        "dpp": pricing["dpp"], "dpp_nilai_lain": pricing.get("dpp_nilai_lain", False),
        "effective_rate": pricing.get("effective_rate", pricing["ppn_rate"]),
        "ppn_rate": pricing["ppn_rate"], "ppn_mode": pricing["ppn_mode"],
        "is_pkp": pricing["is_pkp"], "ppn_amount": pricing["ppn_amount"],
        "grand_total": pricing["grand_total"],
        # F6 — Faktur Pajak per-order + mode pajak efektif (ikut entitas atau override)
        "needs_tax_invoice": bool(getattr(payload, "needs_tax_invoice", False)),
        "tax_override": (getattr(payload, "tax_override", "") or "").strip().lower(),
        "tax_mode": "non_ppn" if not pricing["is_pkp"] else "ppn",
        # Term pembayaran
        "payment_term_code": term_code,
        "payment_term_name": (term or {}).get("name", term_code),
        "payment_status": "pending",
        # KN_17 — snapshot kredit saat order + flag warning + override yang dipakai
        "credit_status_at_order": credit_gate["credit"]["status"],
        "credit_warning": credit_gate["level"] == "warning",
        "credit_hold": credit_needs_approval,
        "credit_override_id": (credit_gate["override"] or {}).get("id", ""),
        # F5 — Unified Approval SSOT (nilai | kredit | special_price)
        "pending_approvals": pending_approvals,
        # Approval (dinamis dari approval_rules + validasi admin wajib)
        "approval_required": _afields["approval_required"],
        "required_approval_role": _afields["required_approval_role"],
        "approval_amount": pricing["grand_total"],
        "is_split_warehouse": is_split, "sales_name": payload.sales_name,
        # SALES REVAMP V2 → REVISI: tim sales (PIC + co-sales + split) di-set PER ORDER dari
        # checkout (payload.sales_team, tervalidasi). Bila kosong → fallback WARISAN customer.
        "sales_team": normalize_sales_team(payload.sales_team) or resolve_customer_sales_team(customer),
        # EPIC6 — link eksplisit asal Special Order (bila order dikonversi dari OD).
        "source_special_order_id": (getattr(payload, "source_special_order_id", "") or "").strip() or None,
        "shipment_policy": _shipment_policy,
        # Order Pengambilan (pickup) — metode pemenuhan + tanggal ambil (hold picking s/d tgl).
        "fulfillment_method": (getattr(payload, "fulfillment_method", "kirim") or "kirim").strip().lower(),
        "pickup_date": (getattr(payload, "pickup_date", "") or "").strip(),
        # F-SHIP — request tanggal pengiriman (opsional; hanya relevan utk metode 'kirim').
        "delivery_date": delivery_date if fulfillment_method == "kirim" else "",
        "reservation_expires_at": expires,
        # Sub-fase 1.6 — backorder lifecycle
        "allow_backorder": payload.allow_backorder,
        "has_backorder": has_backorder,
        "backorders": backorders,
        # Sub-fase 1.7 — allocation policy snapshot + mixed-lot flag (CLARITY/audit)
        "allocation_policy": {
            "mode": alloc_policy.get("mode"),
            "lot_mode": alloc_policy.get("lot_mode"),
            "lot_selection": alloc_policy.get("lot_selection"),
            "location_pref": alloc_policy.get("location_pref"),
        },
        "has_mixed_lot": has_mixed_lot,
        # SALES REVAMP V2 — transfer antar-entitas auto (Beli per Roll lintas-entitas, 1.b)
        "linked_transfer_ids": created_transfer_ids,
        "intercompany_pending_qty": round(total_pending_ic, 2),
        "created_at": now_iso(), "updated_at": now_iso()
    }
    # F4 — derive stage + sub_status (SSOT 2-level) dari status awal + konteks backorder/approval.
    order.update(stage_fields(order))
    await db.sales_orders.insert_one(order)
    # FASE G-4 — pesanan yang lahir dari Special Order menaut ke sumbernya (dua arah).
    if order.get("source_special_order_id"):
        from services import doc_refs_service as _refs
        await _refs.safe_link(("sales_order", order_id),
                              ("special_order", order["source_special_order_id"]),
                              "parent", note="berasal dari Special Order")
    # F5 — buat dokumen detail credit_overrides (pending) yang ditautkan ke entri kredit di SSOT.
    if credit_needs_approval and credit_override_doc_id:
        await db.credit_overrides.insert_one({
            "id": credit_override_doc_id,
            "customer_id": customer["id"], "customer_name": customer["name"],
            "order_id": order_id, "order_number": number,
            "amount": pricing["grand_total"],
            "reason": "; ".join(credit_gate.get("reasons", []) or []) or "Over-limit saat pembuatan SO.",
            "evidence_url": "", "credit_snapshot": credit_gate["credit"],
            "entity_id": entity_id, "status": "pending",
            "requested_by": actor["name"], "requested_by_id": actor["id"],
            "created_at": now_iso(),
        })
    # Konsumsi override kredit bila dipakai untuk melewati blokir (sekali pakai)
    if credit_gate["override"]:
        await db.credit_overrides.update_one(
            {"id": credit_gate["override"]["id"]},
            {"$set": {"consumed": True, "consumed_order_id": order_id, "consumed_at": now_iso()}},
        )
    await audit(actor["name"], "order_created", "sales_order", order["id"], {
        "number": order["number"], "customer": customer["name"], "total_amount": total_amount,
        "grand_total": pricing["grand_total"], "ppn_amount": pricing["ppn_amount"],
        "discount_total": pricing["discount_total"], "payment_term": term_code,
        "approval_required": appr["requires_approval"], "required_role": appr["required_role"],
        "has_backorder": has_backorder,
        "backorder_lines": len(backorders),
        "special_price_lines": special_count,
    })
    return strip_cost_fields(safe_doc(order), actor.get("role"))


@router.get("/sales-orders/{order_id}")
async def get_order(order_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "view")
    order = safe_doc(await db.sales_orders.find_one({"id": order_id}, {"_id": 0}))
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    assert_entity_access(order, "sales_orders", await entity_ctx(request))  # S#074 IDOR
    # FASE E-8 (E8.4 · US11) — pagar PEMILIK. Tanpa ini pembatasan daftar hanya kosmetik:
    # nomor pesanan mudah diterka (`SO-0009`) dan detail pesanan rekan (termasuk harga
    # negosiasinya) tetap bisa dibuka langsung lewat URL/API.
    sales_ownership.assert_may_open(order, actor)
    doc = strip_cost_fields(_norm_backorder(order), actor.get("role"))
    # FASE E-9 (E9.2 · US24) — kalau kekurangannya diurus lewat pembelian internal,
    # layar pesanan HARUS menyebut dari PT mana & lewat dokumen apa. Sebelum ini
    # tidak ada jejaknya sama sekali, jadi Admin Sales tidak tahu barangnya sedang
    # di jalan dan bisa menerbitkan permintaan beli kedua.
    try:
        from services import interco_service as _ics
        doc["interco_supply"] = await _ics.supply_for_order(
            order_id, order.get("entity_id", ""))
    except Exception as exc:  # noqa: BLE001 — pelengkap jejak, bukan syarat buka pesanan
        logging.getLogger(__name__).warning(
            "E9.2 janji pasokan antar-PT gagal dimuat utk order %s: %s", order_id, exc)
        doc["interco_supply"] = []
    return doc


@router.patch("/sales-orders/{order_id}")
async def update_order(order_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "update")
    existing = await db.sales_orders.find_one(
        {"id": order_id},
        {"_id": 0, "entity_id": 1, "number": 1, "created_by": 1, "sales_id": 1, "sales_name": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    assert_entity_access(existing, "sales_orders", await entity_ctx(request))  # S#074 IDOR
    sales_ownership.assert_may_open(existing, actor)  # E8.4 — sales tak boleh sunting SO rekan
    allowed = ["sales_name", "shipment_policy", "notes"]
    data = {k: v for k, v in payload.data.items() if k in allowed}
    data["updated_at"] = now_iso()
    order = await db.sales_orders.find_one_and_update(
        {"id": order_id}, {"$set": data},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    await audit(actor["name"], "order_updated", "sales_order", order_id, data)
    return strip_cost_fields(order, actor.get("role"))
