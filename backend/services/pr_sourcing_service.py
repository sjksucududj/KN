"""FASE E — SOURCING PR: routing `purchase|makloon` + realisasi PR → PO / Order Makloon.

Masalah nyata: satu Purchase Requisition sering **campur** — sebagian barang dibeli jadi
(beli-putus ke supplier), sebagian lagi diproduksi lewat **makloon** (kirim bahan ke mitra).
Sebelum Fase E, PR hanya bisa dikonversi 1× menjadi 1 PO untuk SEMUA baris, sehingga tim
purchasing memecah PR manual & jejak kebutuhan → realisasi hilang.

Yang disediakan modul ini:
  * `fulfillment_mode` per BARIS PR (`purchase` | `makloon`), default `purchase`
    (backward-compatible untuk data lama).
  * **Realisasi parsial**: `realize_to_po` (pilih baris) & `realize_to_makloon` (per baris),
    keduanya **idempotent-aman** (baris yang sudah penuh terealisasi ditolak).
  * Status realisasi **turunan** (tidak pernah disimpan ganda):
    `open` → `partially_realized` → `realized` (PR.status jadi `converted` saat penuh).
  * PO hasil realisasi membawa **jejak sourcing**: `contract_id` (kontrak pembelian),
    `supplier_item_id` + `supplier_sku` + nama versi supplier, dan `expected_grade`.
  * `makloon_prefill` — 1 klik dari PR: menurunkan bahan/mitra/kontrak dari **resep proses**
    (reverse lookup output → input) sehingga Wizard Makloon terbuka sudah terisi.

Invarian (verify_data_integrity L4-SRC): INV-SRC-01..05.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from core_utils import (DEFAULT_ENTITY_ID, new_id, next_doc_number, now_iso, parse_decimal,
                        rupiah, safe_doc, timeline_entry)
from db import db
from services import contract_service as cs
from services import supplier_item_service as sis
from services.config_service import compute_order_pricing, evaluate_approval

FULFILLMENT_MODES = ("purchase", "makloon")
REALIZATION_STATUSES = ("open", "partially_realized", "realized")
EPS = 0.001


class SourcingError(ValueError):
    """Pelanggaran aturan sourcing PR (dipetakan ke HTTP 400/409 di router).

    Turunan `ValueError` agar jalur lama (`convert_to_po` / router yang menangkap
    `ValueError`) tetap mengembalikan **400 yang bisa ditindak**, bukan 500."""


# ═══════════════════════════════════════════════════════════════════════════
# 1. NORMALISASI & STATUS TURUNAN
# ═══════════════════════════════════════════════════════════════════════════
def normalize_mode(value: Any) -> str:
    mode = (str(value or "purchase")).strip().lower()
    if mode in ("beli", "buy", "pembelian"):
        mode = "purchase"
    if mode in ("maklon", "subcon", "subkontrak"):
        mode = "makloon"
    if mode not in FULFILLMENT_MODES:
        raise SourcingError(
            f"Mode pemenuhan '{value}' tidak dikenal. Pilihan: {', '.join(FULFILLMENT_MODES)}.")
    return mode


def ensure_line_shape(pr: Dict[str, Any]) -> bool:
    """Isi `line_no` / `fulfillment_mode` / `realized_qty` untuk PR lama (in-place).

    Return True bila ada perubahan (pemanggil yang menyimpan)."""
    changed = False
    for idx, it in enumerate(pr.get("items") or [], start=1):
        if not it.get("line_no"):
            it["line_no"] = idx
            changed = True
        if not it.get("fulfillment_mode"):
            it["fulfillment_mode"] = "purchase"
            changed = True
        if it.get("realized_qty") is None:
            it["realized_qty"] = 0.0
            changed = True
        if it.get("realizations") is None:
            it["realizations"] = []
            changed = True
    return changed


def compute_realization(pr: Dict[str, Any]) -> Dict[str, Any]:
    """Ringkas realisasi PR — SSOT turunan dari `items[].realized_qty`."""
    items = pr.get("items") or []
    total_qty = round(sum(float(it.get("quantity") or 0) for it in items), 3)
    done_qty = round(sum(min(float(it.get("realized_qty") or 0),
                            float(it.get("quantity") or 0)) for it in items), 3)
    lines_done = sum(1 for it in items
                     if float(it.get("realized_qty") or 0) >= float(it.get("quantity") or 0) - EPS
                     and float(it.get("quantity") or 0) > 0)
    if not items or done_qty <= EPS:
        status = "open"
    elif lines_done >= len([i for i in items if float(i.get("quantity") or 0) > 0]):
        status = "realized"
    else:
        status = "partially_realized"
    return {
        "realization_status": status,
        "realized_lines": lines_done, "total_lines": len(items),
        "realized_qty": done_qty, "total_qty": total_qty,
        "realized_pct": round((done_qty / total_qty * 100), 2) if total_qty else 0.0,
        "purchase_lines": sum(1 for it in items if it.get("fulfillment_mode") == "purchase"),
        "makloon_lines": sum(1 for it in items if it.get("fulfillment_mode") == "makloon"),
    }


async def _save_realization(pr: Dict[str, Any], *, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    summary = compute_realization(pr)
    sets: Dict[str, Any] = {
        "items": pr["items"],
        "realization": summary,
        "realization_status": summary["realization_status"],
        "po_ids": sorted({r["ref_id"] for it in pr["items"] for r in (it.get("realizations") or [])
                          if r.get("type") == "purchase_order"}),
        "makloon_order_ids": sorted({r["ref_id"] for it in pr["items"] for r in (it.get("realizations") or [])
                                     if r.get("type") == "makloon_order"}),
        "timeline": pr.get("timeline") or [],
        "updated_at": now_iso(),
    }
    if summary["realization_status"] == "realized":
        sets["status"] = "converted"
        sets["converted_at"] = pr.get("converted_at") or now_iso()
    if extra:
        sets.update(extra)
    await db.purchase_requisitions.update_one({"id": pr["id"]}, {"$set": sets})
    return safe_doc(await db.purchase_requisitions.find_one({"id": pr["id"]}, {"_id": 0}))


async def _load_pr(pr_id: str) -> Dict[str, Any]:
    pr = await db.purchase_requisitions.find_one({"id": pr_id}, {"_id": 0})
    if not pr:
        raise SourcingError("PR tidak ditemukan.")
    ensure_line_shape(pr)
    return pr


def _open_lines(pr: Dict[str, Any], mode: str, line_nos: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    want = {int(n) for n in (line_nos or [])}
    out = []
    for it in pr.get("items") or []:
        if it.get("fulfillment_mode") != mode:
            continue
        remaining = float(it.get("quantity") or 0) - float(it.get("realized_qty") or 0)
        if remaining <= EPS:
            continue
        if want and int(it.get("line_no") or 0) not in want:
            continue
        out.append(it)
    return out


def _record(it: Dict[str, Any], *, kind: str, ref_id: str, ref_number: str,
            qty: float, actor: str) -> None:
    it.setdefault("realizations", []).append({
        "type": kind, "ref_id": ref_id, "ref_number": ref_number,
        "qty": round(float(qty), 3), "at": now_iso(), "by": actor,
    })
    it["realized_qty"] = round(float(it.get("realized_qty") or 0) + float(qty), 3)


# ═══════════════════════════════════════════════════════════════════════════
# 2. REALISASI → PURCHASE ORDER (baris `purchase`)
# ═══════════════════════════════════════════════════════════════════════════
async def resolve_line_sourcing(*, supplier_id: str, product_id: str, qty: float,
                                entity_id: str, est_price: float = 0.0,
                                unit: str = "") -> Dict[str, Any]:
    """Gabungkan kontrak pembelian + barang supplier → harga, satuan, nama & grade.

    Prioritas harga: **kontrak pembelian** → est_price PR → barang supplier (`last_price`)
    → price-list supplier → harga produk. Semua langkah dicatat di `explain[]` agar auditable.
    """
    explain: List[str] = []
    out: Dict[str, Any] = {"price": 0.0, "unit": unit or "", "source": "",
                           "contract_id": "", "contract_number": "",
                           "supplier_item_id": "", "supplier_sku": "",
                           "supplier_item_name": "", "supplier_uom": "",
                           "supplier_conv_factor": 0, "expected_grade": "", "explain": explain}
    contract = await cs.resolve_active(partner_id=supplier_id, contract_type="purchase",
                                       product_id=product_id, entity_id=entity_id)
    sup_item = await sis.resolve_for_product(supplier_id=supplier_id, product_id=product_id,
                                            entity_id=entity_id)
    if sup_item:
        out.update({"supplier_item_id": sup_item["id"], "supplier_sku": sup_item["supplier_sku"],
                    "supplier_item_name": sup_item.get("supplier_item_name", ""),
                    # FASE F-1 — satuan & faktor versi supplier diteruskan ke baris PO
                    # supaya penerimaan bisa menerima qty dalam satuan supplier.
                    "supplier_uom": sup_item.get("supplier_uom", ""),
                    "supplier_conv_factor": sup_item.get("conv_factor", 0)})
        if sup_item.get("expected_grade"):
            out["expected_grade"] = sup_item["expected_grade"]
        explain.append(f"Barang supplier: {sup_item['supplier_sku']} — "
                       f"{sup_item.get('supplier_item_name') or '-'} "
                       f"(1 {sup_item.get('supplier_uom')} = {sup_item.get('conv_factor')} "
                       f"{sup_item.get('base_unit')})")
    if contract:
        rate = parse_decimal(contract.get("tariff_rate"), 2)
        out.update({"contract_id": contract["id"], "contract_number": contract.get("contract_number", "")})
        if contract.get("expected_grade"):
            out["expected_grade"] = contract["expected_grade"]
        if rate > 0:
            out.update({"price": rate, "source": "contract",
                        "unit": contract.get("tariff_basis") or out["unit"]})
            explain.append(f"Harga dari kontrak {contract.get('contract_number')}: "
                           f"{rupiah(rate)} / {contract.get('tariff_basis')}")
        moq = parse_decimal(contract.get("moq"))
        if moq > 0 and qty < moq:
            explain.append(f"⚠️ Qty {qty:g} di bawah MOQ kontrak {moq:g} — konfirmasi ke supplier.")
            out["below_moq"] = True
    if out["price"] <= 0 and est_price > 0:
        out.update({"price": round(est_price, 2), "source": "pr_estimate"})
        explain.append(f"Harga memakai estimasi PR: {rupiah(est_price)}")
    if out["price"] <= 0 and sup_item and parse_decimal(sup_item.get("last_price"), 2) > 0:
        out.update({"price": parse_decimal(sup_item["last_price"], 2), "source": "supplier_item",
                    "unit": sup_item.get("supplier_uom") or out["unit"]})
        explain.append(f"Harga terakhir barang supplier: {rupiah(out['price'])} / {out['unit']}")
    if out["price"] <= 0:
        from services.supplier_service import resolve_price
        resolved = await resolve_price(supplier_id, product_id, qty)
        if float(resolved.get("price", 0) or 0) > 0:
            out.update({"price": round(float(resolved["price"]), 2), "source": "price_list"})
            if resolved.get("unit"):
                out["unit"] = resolved["unit"]
            explain.append(f"Harga dari price-list supplier: {rupiah(out['price'])}")
    if out["price"] <= 0:
        prod = await db.products.find_one({"id": product_id}, {"_id": 0, "price": 1, "harga_pokok": 1})
        fallback = float((prod or {}).get("harga_pokok") or 0) or float((prod or {}).get("price") or 0)
        out.update({"price": round(fallback, 2), "source": "product_master"})
        explain.append(f"Harga dari master produk: {rupiah(fallback)}")
    return out


async def realize_to_po(pr_id: str, *, supplier_id: str, actor: Dict[str, Any],
                        warehouse_id: str = "", line_nos: Optional[List[int]] = None,
                        expected_delivery_date: str = "", notes: str = "") -> Dict[str, Any]:
    """Realisasikan baris PR ber-mode `purchase` menjadi **satu PO**.

    Baris `makloon` DIABAIKAN (dipenuhi via Order Makloon) sehingga PR campur tidak
    lagi harus dipecah manual. PR menjadi `converted` hanya bila SEMUA baris terealisasi.
    """
    from routers.purchase_orders import _create_inbound_tasks_for_po
    from services import grade_service
    from services.supplier_service import assess_price_deviation
    from services.config_service import get_effective_settings

    pr = await _load_pr(pr_id)
    if pr.get("status") not in ("approved", "converted"):
        raise SourcingError(
            f"Hanya PR 'approved' yang bisa direalisasikan (status sekarang: {pr.get('status')}).")
    lines = _open_lines(pr, "purchase", line_nos)
    if not lines:
        raise SourcingError("Tidak ada baris PEMBELIAN yang masih perlu direalisasikan "
                            "(sudah terealisasi atau semua baris ber-mode makloon).")
    non_catalog = [it for it in lines if not it.get("product_id")]
    if non_catalog:
        raise SourcingError("Ada baris non-katalog. Buat produk dulu — tidak bisa auto-realisasi ke PO.")

    supplier_id = supplier_id or pr.get("preferred_supplier_id", "")
    if not supplier_id:
        raise SourcingError("Supplier wajib dipilih untuk realisasi ke PO.")
    supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0})
    if not supplier:
        raise SourcingError("Supplier tidak ditemukan.")
    # FASE E-7 (E7.2) — KEBOCORAN yang terbukti sesi 2026-08-11: `POST /purchase-orders`
    # sudah dipagari, tetapi PR → `convert-to-po`/`realize-po` memanggil fungsi INI
    # langsung sehingga PO biasa ke badan usaha grup tetap lahir (bukti: KSC/PO-00013).
    # Pagar dipasang di lapis service supaya SEMUA pintu (router PR, convert, realisasi
    # per-baris) ikut terjaga — bukan ditambal satu-satu di setiap router.
    # HTTPException 409 SENGAJA (bukan SourcingError) supaya kalimat menuntunnya utuh
    # sampai ke pengguna; router hanya menangkap SourcingError.
    from services import group_partner_service as _grp
    await _grp.assert_supplier_not_group_entity(
        supplier, doc_label="Pesanan Pembelian (PO) hasil realisasi PR")
    warehouse_id = warehouse_id or pr.get("warehouse_id", "")
    warehouse = await db.warehouses.find_one({"id": warehouse_id}, {"_id": 0}) if warehouse_id else None
    if not warehouse:
        raise SourcingError("Gudang wajib dipilih untuk realisasi ke PO.")

    entity_id = pr.get("entity_id") or DEFAULT_ENTITY_ID
    raw_items: List[Dict[str, Any]] = []
    used_contracts: set = set()
    used_items: List[tuple] = []
    for it in lines:
        prod = await db.products.find_one({"id": it["product_id"]}, {"_id": 0})
        if not prod:
            raise SourcingError(f"Produk {it['product_id']} tidak ditemukan.")
        qty = round(float(it["quantity"]) - float(it.get("realized_qty") or 0), 3)
        src = await resolve_line_sourcing(
            supplier_id=supplier_id, product_id=prod["id"], qty=qty, entity_id=entity_id,
            est_price=float(it.get("est_price") or 0), unit=it.get("unit") or prod.get("base_unit", "meter"))
        row = {
            "product_id": prod["id"], "sku": prod["sku"], "product_name": prod["name"],
            "quantity": qty, "unit": src["unit"] or it.get("unit") or "meter",
            "price": src["price"], "discount_percent": 0, "received_qty": 0.0,
            # FASE E — jejak sourcing pada baris PO
            "contract_id": src["contract_id"], "contract_number": src["contract_number"],
            "supplier_item_id": src["supplier_item_id"], "supplier_sku": src["supplier_sku"],
            "supplier_item_name": src["supplier_item_name"],
            "supplier_uom": src.get("supplier_uom", ""),
            "supplier_conv_factor": src.get("supplier_conv_factor", 0),
            "price_source": src["source"], "sourcing_explain": src["explain"],
            "pr_line_no": it.get("line_no"),
        }
        if src["expected_grade"]:
            row["expected_grade"] = src["expected_grade"]
            row["expected_grade_source"] = "supplier_contract" if src["contract_id"] else "supplier_item"
        raw_items.append(row)
        if src["contract_id"]:
            used_contracts.add(src["contract_id"])
        if src["supplier_item_id"]:
            used_items.append((src["supplier_item_id"], src["price"]))

    pricing = await compute_order_pricing(raw_items, entity_id, 0.0, cfg_section="purchasing")
    items = pricing["items"]
    total_amount = pricing["total_amount"]
    grand_total = pricing["grand_total"]

    appr = await evaluate_approval("purchase_order", total_amount, entity_id)
    needs_approval = appr["requires_approval"]
    required_role = appr["required_role"]
    approval_reason = "amount_threshold" if needs_approval else ""
    settings = await get_effective_settings(entity_id)
    threshold = float(settings.get("purchasing", {}).get("price_deviation_approval_percent", 10.0) or 10.0)
    price_deviation = await assess_price_deviation(supplier_id, items, threshold)
    if price_deviation["flagged"]:
        needs_approval = True
        required_role = required_role or "manager"
        approval_reason = "price_deviation" if not approval_reason else "amount_threshold+price_deviation"

    sup_contact = " | ".join([x for x in [supplier.get("pic_name", ""), supplier.get("phone", "")] if x])
    now = now_iso()
    actor_name = actor.get("name", "Admin")
    po = {
        "id": new_id("po"),
        "po_number": await next_doc_number("purchase_orders", "po_number", "PO-", entity_id=entity_id),
        "supplier_id": supplier_id, "supplier_name": supplier.get("name", ""),
        "supplier_contact": sup_contact, "supplier_npwp": supplier.get("npwp", ""),
        "warehouse_id": warehouse_id, "warehouse_name": warehouse["name"],
        "warehouse_city": warehouse.get("city", ""),
        "items": items, "total_amount": total_amount, "entity_id": entity_id,
        "items_discount_total": pricing["items_discount_total"],
        "order_discount_percent": pricing["order_discount_percent"],
        "order_discount_amount": pricing["order_discount_amount"],
        "discount_total": pricing["discount_total"],
        "net_subtotal": pricing["net_subtotal"],
        "dpp": pricing["dpp"], "ppn_rate": pricing["ppn_rate"],
        "ppn_mode": pricing["ppn_mode"], "is_pkp": pricing["is_pkp"],
        "ppn_amount": pricing["ppn_amount"], "grand_total": grand_total, "tax_mode": "",
        "expected_delivery_date": expected_delivery_date or pr.get("needed_by_date", ""),
        "notes": notes or f"Dari {pr['number']}",
        "status": "waiting_approval" if needs_approval else "pending",
        "approval_required": needs_approval, "required_approval_role": required_role,
        "approval_status": "pending" if needs_approval else "not_required",
        "approval_amount": total_amount,
        "approval_reason": approval_reason, "price_deviation": price_deviation,
        "amount_paid": 0.0, "returned_amount": 0.0, "outstanding": round(grand_total, 2),
        "payment_status": "unpaid", "payments": [],
        "source_pr_id": pr_id, "source_pr_number": pr["number"],
        "source_pr_line_nos": [it.get("line_no") for it in lines],
        "contract_ids": sorted(used_contracts),
        # R6.3 — Budget Control: tag anggaran (default akun Persediaan bila tak di-tag)
        "budget_dimension": "", "budget_key": "",
        "version": 1, "amendments": [],
        "timeline": (
            [timeline_entry("created", f"PO dibuat dari {pr['number']}", actor_name,
                            f"{len(items)} item · {rupiah(total_amount)}")]
            + ([timeline_entry("submitted_for_approval", f"Menunggu persetujuan {required_role}",
                               actor_name,
                               f"deviasi harga +{price_deviation['max_deviation_pct']}%"
                               if price_deviation["flagged"] else "nilai melebihi batas")]
               if needs_approval else [])
        ),
        "created_by": actor_name, "created_by_id": actor.get("id", ""),
        "created_at": now, "updated_at": now,
    }
    # Fase A · PS-09/D-19 — grade: hormati grade dari kontrak/barang supplier, sisanya diturunkan.
    await grade_service.stamp_expected_grade(po["items"], allow_derive=True, context="PO dari PR")
    # R6.3 — Budget Control: PO hasil realisasi PR WAJIB tunduk aturan anggaran yang sama
    #        dengan PO manual (mode off/warn/block per entitas).
    from services import budget_service
    try:
        budget_check = await budget_service.enforce_po_budget(po, "po_create", actor)
    except ValueError as exc:
        raise SourcingError(str(exc)) from exc
    po["budget_check"] = budget_check
    if budget_check.get("warnings"):
        po["timeline"].append(timeline_entry(
            "budget_warning", "Peringatan anggaran", actor_name,
            " · ".join(budget_check["warnings"])[:400]))
    from services import line_scope as _lines            # FASE L
    await _lines.stamp_doc(db, po)
    await db.purchase_orders.insert_one(dict(po))
    # FASE G-4 — PO hasil realisasi PR menaut ke PR-nya (dua arah).
    from services import doc_refs_service as _refs
    await _refs.safe_link(("purchase_order", po["id"]),
                          ("purchase_requisition", pr["id"]), "parent",
                          note="realisasi permintaan pembelian")
    if not needs_approval:
        await _create_inbound_tasks_for_po(po)
    else:
        from services.notification_service import notify_po_awaiting_approval
        await notify_po_awaiting_approval(po)

    for cid in used_contracts:
        await cs.mark_used(cid)
    for sid, price in used_items:
        await sis.mark_used(sid, price)

    for it in lines:
        _record(it, kind="purchase_order", ref_id=po["id"], ref_number=po["po_number"],
                qty=float(it["quantity"]) - float(it.get("realized_qty") or 0), actor=actor_name)
    pr.setdefault("timeline", []).append(timeline_entry(
        "realized_po", f"{len(lines)} baris direalisasi ke {po['po_number']}", actor_name,
        f"{rupiah(total_amount)}"))
    updated = await _save_realization(pr, extra={
        "po_id": pr.get("po_id") or po["id"],
        "po_number": pr.get("po_number") or po["po_number"],
        "converted_by": actor_name,
    })
    return {"pr": updated, "po": safe_doc(po)}


# ═══════════════════════════════════════════════════════════════════════════
# 3. REALISASI → ORDER MAKLOON (baris `makloon`)
# ═══════════════════════════════════════════════════════════════════════════
async def makloon_prefill(pr_id: str, line_no: int) -> Dict[str, Any]:
    """Turunkan payload Wizard Makloon dari baris PR (1 klik dari PR).

    Cara kerja: baris PR menyebut **produk yang dibutuhkan** (output). Resep proses
    di-cari terbalik (`output_product_id == produk baris`) untuk mendapat bahan input,
    jenis proses, mitra default & yield → qty bahan dihitung dari target output.
    """
    pr = await _load_pr(pr_id)
    line = next((it for it in pr["items"] if int(it.get("line_no") or 0) == int(line_no)), None)
    if not line:
        raise SourcingError(f"Baris {line_no} tidak ada pada {pr['number']}.")
    if line.get("fulfillment_mode") != "makloon":
        raise SourcingError(f"Baris {line_no} ber-mode '{line.get('fulfillment_mode')}' — "
                            "prefill makloon hanya untuk baris ber-mode 'makloon'.")
    if not line.get("product_id"):
        raise SourcingError("Baris non-katalog tidak bisa diprefill — tentukan produk output dulu.")
    remaining = round(float(line["quantity"]) - float(line.get("realized_qty") or 0), 3)
    if remaining <= EPS:
        raise SourcingError(f"Baris {line_no} sudah terealisasi penuh.")

    entity_id = pr.get("entity_id") or DEFAULT_ENTITY_ID
    out_prod = await db.products.find_one({"id": line["product_id"]}, {"_id": 0}) or {}
    explain: List[str] = [f"Kebutuhan {pr['number']} baris {line_no}: "
                          f"{remaining:g} {line.get('unit') or out_prod.get('base_unit')} "
                          f"{out_prod.get('name')}"]
    recipe = await db.process_recipes.find_one(
        {"output_product_id": line["product_id"], "status": "active",
         "entity_id": {"$in": [entity_id, "", None]}}, {"_id": 0})
    if not recipe:
        recipe = await db.process_recipes.find_one(
            {"output_product_id": line["product_id"]}, {"_id": 0})
    if not recipe:
        return {
            "pr_id": pr_id, "pr_number": pr["number"], "line_no": line_no,
            "ready": False,
            "reason": (f"Belum ada Resep Proses yang menghasilkan '{out_prod.get('name')}'. "
                       "Buat resep dulu (Pembelian → Master Pembelian → Resep Proses) "
                       "agar bahan, mitra & yield bisa dihitung otomatis."),
            "target_output_qty": remaining, "output_product_id": line["product_id"],
            "explain": explain,
        }

    yield_factor = parse_decimal(recipe.get("yield_factor")) or 1.0
    waste_pct = parse_decimal(recipe.get("waste_pct"))
    effective = yield_factor * (1 - waste_pct / 100.0)
    if effective <= 0:
        effective = yield_factor or 1.0
    material_qty = round(remaining / effective, 2)
    material_qty = round(math.ceil(material_qty * 100) / 100, 2)     # bulatkan ke atas 2 desimal
    explain.append(f"Resep '{recipe.get('name')}': yield {yield_factor:g} × susut {waste_pct:g}% "
                   f"→ faktor efektif {effective:.4f}")
    explain.append(f"Bahan dibutuhkan ≈ {remaining:g} ÷ {effective:.4f} = {material_qty:g}")

    in_prod = await db.products.find_one({"id": recipe.get("input_product_id")}, {"_id": 0}) or {}
    makloon_id = recipe.get("default_makloon_id") or ""
    process_type = recipe.get("process_type") or ""
    contract = await cs.resolve_active(partner_id=makloon_id, contract_type="makloon",
                                       process_type=process_type,
                                       product_id=line["product_id"],
                                       input_product_id=recipe.get("input_product_id") or "",
                                       entity_id=entity_id) if makloon_id else None
    if contract:
        explain.append(f"Kontrak aktif {contract.get('contract_number')} — tarif "
                       f"{contract.get('tariff_basis')} @ {rupiah(parse_decimal(contract.get('tariff_rate')))}"
                       f" · susut {parse_decimal(contract.get('shrinkage_pct')):g}%")
    else:
        explain.append("Belum ada kontrak aktif untuk mitra default — tarif/susut memakai resep/kebijakan.")

    makloon_name = ""
    if makloon_id:
        mk = await db.makloons.find_one({"id": makloon_id}, {"_id": 0, "name": 1})
        makloon_name = (mk or {}).get("name", "")
    byp_prod: Dict[str, Any] = {}
    if recipe.get("byproduct_product_id"):
        byp_prod = await db.products.find_one(
            {"id": recipe.get("byproduct_product_id")}, {"_id": 0, "name": 1}) or {}
    return {
        "pr_id": pr_id, "pr_number": pr["number"], "line_no": line_no, "ready": True,
        "target_output_qty": remaining,
        "recipe": {"id": recipe.get("id"), "name": recipe.get("name"),
                   "process_type": process_type, "yield_factor": yield_factor,
                   "waste_pct": waste_pct},
        "contract": {"id": (contract or {}).get("id", ""),
                     "number": (contract or {}).get("contract_number", ""),
                     "tariff_basis": (contract or {}).get("tariff_basis", ""),
                     "tariff_rate": parse_decimal((contract or {}).get("tariff_rate"), 2)} if contract
        else {"id": "", "number": ""},
        "explain": explain,
        # Payload siap kirim ke POST /api/makloon-orders (bisa diedit user di wizard)
        "payload": {
            "mode": "process_only",
            "material_product_id": recipe.get("input_product_id") or "",
            "material_sku": in_prod.get("sku", ""),
            "material_name": in_prod.get("name", ""),
            "material_qty": material_qty,
            "material_unit": in_prod.get("base_unit", ""),
            "from_warehouse_id": pr.get("warehouse_id") or "",
            "target_warehouse_id": pr.get("warehouse_id") or "",
            "entity_id": entity_id,
            "pr_id": pr_id, "pr_number": pr["number"], "pr_line_no": line_no,
            "notes": f"Realisasi {pr['number']} baris {line_no} — {out_prod.get('name')}",
            "steps": [{
                "process_type": process_type,
                "makloon_id": makloon_id, "makloon_name": makloon_name,
                "recipe_id": recipe.get("id") or "",
                "contract_id": (contract or {}).get("id", ""),
                "input_product_id": recipe.get("input_product_id") or "",
                # Nama/satuan disertakan agar Wizard Makloon bisa MENAMPILKAN produk
                # hasil yang sudah ter-prefill (tanpa ini kolom "Produk Hasil" tampak
                # kosong & ringkasan rantai menampilkan "?" walau data sudah benar).
                "input_name": in_prod.get("name", ""),
                "input_sku": in_prod.get("sku", ""),
                "input_unit": in_prod.get("base_unit", ""),
                "output_product_id": line["product_id"],
                "output_name": out_prod.get("name", ""),
                "output_sku": out_prod.get("sku", ""),
                "output_unit": out_prod.get("base_unit") or line.get("unit") or "",
                "byproduct_product_id": recipe.get("byproduct_product_id") or "",
                "byproduct_name": byp_prod.get("name", ""),
            }],
        },
    }


async def realize_to_makloon(pr_id: str, line_no: int, payload: Dict[str, Any],
                             actor: Dict[str, Any]) -> Dict[str, Any]:
    """Buat Order Makloon dari baris PR ber-mode `makloon` & catat realisasinya."""
    from services.makloon_order_service import create_makloon_order

    pr = await _load_pr(pr_id)
    if pr.get("status") not in ("approved", "converted"):
        raise SourcingError(
            f"Hanya PR 'approved' yang bisa direalisasikan (status sekarang: {pr.get('status')}).")
    line = next((it for it in pr["items"] if int(it.get("line_no") or 0) == int(line_no)), None)
    if not line:
        raise SourcingError(f"Baris {line_no} tidak ada pada {pr['number']}.")
    if line.get("fulfillment_mode") != "makloon":
        raise SourcingError(f"Baris {line_no} ber-mode '{line.get('fulfillment_mode')}' — "
                            "pakai realisasi ke PO untuk baris pembelian.")
    remaining = round(float(line["quantity"]) - float(line.get("realized_qty") or 0), 3)
    if remaining <= EPS:
        raise SourcingError(f"Baris {line_no} sudah terealisasi penuh.")

    body = dict(payload or {})
    if not body.get("steps"):
        pre = await makloon_prefill(pr_id, line_no)
        if not pre.get("ready"):
            raise SourcingError(pre.get("reason") or "Prefill makloon tidak tersedia.")
        body = dict(pre["payload"])
    entity_id = body.get("entity_id") or pr.get("entity_id") or DEFAULT_ENTITY_ID
    body.update({"pr_id": pr_id, "pr_number": pr["number"], "pr_line_no": line_no})
    # Output akhir rantai WAJIB = produk baris PR (jejak kebutuhan → realisasi tak putus).
    last_out = (body["steps"][-1] or {}).get("output_product_id")
    if last_out and last_out != line.get("product_id"):
        raise SourcingError(
            "Output langkah terakhir harus sama dengan produk yang diminta PR "
            f"(baris {line_no}: {line.get('product_name')}).")
    order = await create_makloon_order(body, entity_id=entity_id,
                                       actor_name=actor.get("name", "Admin"))
    expected = parse_decimal((order.get("forecast") or {}).get("expected_finished_qty"), 3)
    covered = min(remaining, expected) if expected > 0 else remaining
    _record(line, kind="makloon_order", ref_id=order["id"], ref_number=order.get("mko_number", ""),
            qty=covered, actor=actor.get("name", "Admin"))
    pr.setdefault("timeline", []).append(timeline_entry(
        "realized_makloon", f"Baris {line_no} direalisasi ke {order.get('mko_number')}",
        actor.get("name", "Admin"),
        f"estimasi {expected:g} {order.get('final_output_unit') or ''}"))
    updated = await _save_realization(pr, extra={"converted_by": actor.get("name", "Admin")})
    return {"pr": updated, "makloon_order": order,
            "covered_qty": covered, "expected_output_qty": expected}


# ═══════════════════════════════════════════════════════════════════════════
# 4. RINGKASAN UNTUK UI
# ═══════════════════════════════════════════════════════════════════════════
async def sourcing_view(pr_id: str) -> Dict[str, Any]:
    """Ringkasan realisasi + aksi yang tersedia per baris (dipakai panel detail PR)."""
    pr = await _load_pr(pr_id)
    lines = []
    for it in pr["items"]:
        remaining = round(float(it.get("quantity") or 0) - float(it.get("realized_qty") or 0), 3)
        lines.append({
            "line_no": it.get("line_no"), "product_id": it.get("product_id"),
            "sku": it.get("sku"), "product_name": it.get("product_name"),
            "quantity": float(it.get("quantity") or 0), "unit": it.get("unit"),
            "fulfillment_mode": it.get("fulfillment_mode") or "purchase",
            "realized_qty": float(it.get("realized_qty") or 0),
            "remaining_qty": max(remaining, 0.0),
            "realizations": it.get("realizations") or [],
            "can_realize": remaining > EPS and pr.get("status") in ("approved", "converted"),
        })
    return {"pr_id": pr_id, "number": pr.get("number"), "status": pr.get("status"),
            "summary": compute_realization(pr), "lines": lines}
