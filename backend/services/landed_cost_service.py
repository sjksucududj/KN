"""Landed Cost service (Fase 5.4 — P0-5).

Mengalokasikan biaya tambahan impor/angkut (freight, bea masuk, asuransi,
handling) ke HPP per ROLL (`inventory_rolls.unit_cost`). Roll = SSOT fisik
(KN_15) sehingga HPP melekat di roll, bukan di balance proyeksi.

Model HPP (additive, mendukung banyak voucher):
  unit_cost(final) = base_unit_cost + Σ(landed_per_unit dari tiap voucher)
  landed_cost_total(roll) = Σ(alloc_amount per voucher)

Basis alokasi:
  - value    : bobot = base_unit_cost × length_initial (nilai roll)  [default 1a]
  - quantity : bobot = length_initial (panjang)
Fallback aman: bila Σbobot value = 0 (roll belum punya base cost) → pakai
basis quantity; bila masih 0 → bagi rata.

Lifecycle voucher: draft → pending_approval → applied (→ paid) | cancelled.
Aplikasi ke HPP HANYA terjadi saat APPROVE (idempotent: status 'applied'
tidak bisa di-apply ulang). Pembuat ≠ approver (SoD).
"""
from typing import Any, Dict, List
from db import db
from core_utils import now_iso

ACTIVE_VOUCHER_STATUSES = {"draft", "pending_approval", "applied", "paid"}
PAYABLE_VOUCHER_STATUSES = {"applied", "paid"}
COST_CATEGORIES = {"freight", "duty", "insurance", "handling", "other"}


async def next_voucher_number() -> str:
    """Number series LCV-NNNNN (cegah duplikat via max existing)."""
    last = await db.landed_cost_vouchers.find_one(
        {}, {"_id": 0, "voucher_number": 1}, sort=[("voucher_number", -1)])
    n = 0
    if last and isinstance(last.get("voucher_number"), str) and last["voucher_number"].startswith("LCV-"):
        try:
            n = int(last["voucher_number"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.landed_cost_vouchers.count_documents({})
    else:
        n = await db.landed_cost_vouchers.count_documents({})
    return f"LCV-{n + 1:05d}"


def total_cost_of(cost_lines: List[Dict[str, Any]]) -> float:
    return round(sum(float(c.get("amount", 0) or 0) for c in (cost_lines or [])), 2)


def voucher_financials(v: Dict[str, Any]) -> Dict[str, Any]:
    total = round(float(v.get("total_cost", 0) or 0), 2)
    paid = round(float(v.get("amount_paid", 0) or 0), 2)
    outstanding = round(max(total - paid, 0.0), 2)
    if v.get("status") not in PAYABLE_VOUCHER_STATUSES:
        payment_status = "n/a"
    elif paid <= 0.01:
        payment_status = "unpaid"
    elif outstanding <= 0.01:
        payment_status = "paid"
    else:
        payment_status = "partial"
    return {"total_cost": total, "amount_paid": paid, "outstanding": outstanding,
            "payment_status": payment_status}


async def resolve_target_rolls(po_ids: List[str], entity_id: str = "") -> List[Dict[str, Any]]:
    """Roll yang diterima dari PO terkait (acquired.ref_id == po_id). HPP melekat
    di roll → semua roll dari PO ikut dialokasi, kecuali yang sudah scrapped."""
    if not po_ids:
        return []
    query: Dict[str, Any] = {"acquired.ref_id": {"$in": list(po_ids)},
                             "status": {"$nin": ["scrapped", "cancelled"]}}
    if entity_id and entity_id != "all":
        query["owner_entity_id"] = entity_id
    rolls = await db.inventory_rolls.find(query, {"_id": 0}).to_list(5000)
    # Dokumen roll TIDAK menyimpan nama produk (hanya `product_id`), sedangkan tabel
    # alokasi di layar menampilkan `product_name || product_id` → selama ini pemilik
    # membaca **`prod_batik_mega`** di kolom Produk, bukan "Batik Mega Mendung Premium".
    # Kelas bug yang sama dengan kebocoran `ent_ksc` yang ditutup FASE P7 (INV-UI-02):
    # id teknis tak boleh sampai ke mata pengguna. Namanya dilengkapi di SINI supaya
    # pratinjau alokasi maupun alokasi yang sudah diterapkan sama-sama benar.
    pids = {r.get("product_id") for r in rolls if r.get("product_id")}
    if pids:
        prods = {p["id"]: p for p in await db.products.find(
            {"id": {"$in": list(pids)}}, {"_id": 0, "id": 1, "name": 1, "sku": 1}).to_list(5000)}
        for r in rolls:
            p = prods.get(r.get("product_id")) or {}
            if not r.get("product_name"):
                r["product_name"] = p.get("name", "")
            if not r.get("sku"):
                r["sku"] = p.get("sku", "")
    return rolls


def _roll_base_unit_cost(r: Dict[str, Any]) -> float:
    """Base HPP per unit roll (sebelum landed cost). Fallback ke unit_cost-landed."""
    b = r.get("base_unit_cost")
    if b is not None:
        return float(b or 0)
    uc = r.get("unit_cost")
    return float(uc or 0)


def compute_allocation(rolls: List[Dict[str, Any]], total_cost: float, basis: str = "value") -> Dict[str, Any]:
    """Alokasikan total_cost ke daftar roll. Return {basis, allocations, total_weight}.
    Pembulatan: sisa selisih dibebankan ke roll terakhir agar Σalloc == total_cost."""
    total_cost = round(float(total_cost or 0), 2)
    rolls = [r for r in rolls if float(r.get("length_initial", 0) or 0) > 0]
    n = len(rolls)
    result_basis = basis if basis in ("value", "quantity") else "value"

    def weight_for(r: Dict[str, Any], b: str) -> float:
        ln = float(r.get("length_initial", 0) or 0)
        if b == "value":
            return _roll_base_unit_cost(r) * ln
        return ln  # quantity

    weights = [weight_for(r, result_basis) for r in rolls]
    tw = round(sum(weights), 6)
    if result_basis == "value" and tw <= 0:
        # roll belum punya base cost → fallback ke basis kuantitas
        result_basis = "quantity"
        weights = [weight_for(r, "quantity") for r in rolls]
        tw = round(sum(weights), 6)
    if tw <= 0:  # masih 0 → bagi rata
        weights = [1.0 for _ in rolls]
        tw = float(n) if n else 1.0

    allocations: List[Dict[str, Any]] = []
    running = 0.0
    for i, r in enumerate(rolls):
        ln = float(r.get("length_initial", 0) or 0)
        if i == n - 1:
            alloc = round(total_cost - running, 2)
        else:
            alloc = round(total_cost * (weights[i] / tw), 2)
            running = round(running + alloc, 2)
        per_unit = round(alloc / ln, 6) if ln > 0 else 0.0
        cur_uc = float(r.get("unit_cost") or 0)
        allocations.append({
            "roll_id": r["id"],
            "roll_no": r.get("roll_no", ""),
            "product_id": r.get("product_id", ""),
            "product_name": r.get("product_name", ""),
            "sku": r.get("sku", ""),
            "length": round(ln, 2),
            "weight": round(weights[i], 4),
            "base_unit_cost": round(_roll_base_unit_cost(r), 4),
            "current_unit_cost": round(cur_uc, 4),
            "alloc_amount": alloc,
            "per_unit": per_unit,
            "new_unit_cost": round(cur_uc + per_unit, 4),
        })
    return {"basis": result_basis, "allocations": allocations,
            "total_weight": round(tw, 4), "roll_count": n,
            "allocated_total": round(sum(a["alloc_amount"] for a in allocations), 2)}


async def apply_allocation_to_rolls(voucher_number: str, allocations: List[Dict[str, Any]]) -> int:
    """Terapkan alokasi ke roll (additive). $inc unit_cost(+per_unit) &
    landed_cost_total(+alloc), $push landed_cost_refs. Idempotensi dijaga di router
    (status voucher). Return jumlah roll terupdate."""
    updated = 0
    for a in allocations:
        res = await db.inventory_rolls.update_one(
            {"id": a["roll_id"]},
            {"$inc": {"unit_cost": a["per_unit"], "landed_cost_total": a["alloc_amount"]},
             "$set": {"updated_at": now_iso()},
             "$push": {"landed_cost_refs": voucher_number}})
        updated += res.modified_count
    return updated


async def attach_allocation_names(vouchers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Lengkapi nama produk pada baris alokasi voucher yang SUDAH tersimpan.

    Alokasi yang dibuat sebelum perbaikan ini hanya menyimpan `product_id`, dan layar
    dulu mencetak id itu apa adanya sebagai cadangan (`prod_batik_mega` di kolom
    Produk). Melengkapinya saat DIBACA membuat dokumen lama ikut tampil benar tanpa
    migrasi data, dan tidak ada satu pun tempat lain yang perlu tahu soal ini.
    """
    pids = {a.get("product_id") for v in vouchers
            for a in (v.get("allocations") or []) + (v.get("allocation_preview") or [])
            if a.get("product_id")}
    if not pids:
        return vouchers
    prods = {p["id"]: p for p in await db.products.find(
        {"id": {"$in": list(pids)}}, {"_id": 0, "id": 1, "name": 1, "sku": 1}).to_list(5000)}
    for v in vouchers:
        for key in ("allocations", "allocation_preview"):
            for a in (v.get(key) or []):
                prod = prods.get(a.get("product_id")) or {}
                if not a.get("product_name"):
                    a["product_name"] = prod.get("name", "")
                if not a.get("sku"):
                    a["sku"] = prod.get("sku", "")
    return vouchers


async def build_landed_cost_context(po: Dict[str, Any]) -> Dict[str, Any]:
    """Konteks untuk form: roll yang diterima dari PO + nilai dasar (base value)."""
    rolls = await resolve_target_rolls([po["id"]], po.get("entity_id", ""))
    rows = []
    total_base_value = 0.0
    total_length = 0.0
    for r in rolls:
        ln = float(r.get("length_initial", 0) or 0)
        buc = _roll_base_unit_cost(r)
        bv = round(buc * ln, 2)
        total_base_value += bv
        total_length += ln
        rows.append({
            "roll_id": r["id"], "roll_no": r.get("roll_no", ""),
            "product_id": r.get("product_id", ""), "product_name": r.get("product_name", ""),
            "sku": r.get("sku", ""), "length": round(ln, 2), "unit": r.get("unit", "meter"),
            "base_unit_cost": round(buc, 4), "base_value": bv,
            "current_unit_cost": round(float(r.get("unit_cost") or 0), 4),
            "dye_lot": r.get("dye_lot", ""), "status": r.get("status", ""),
        })
    return {
        "po_id": po["id"], "po_number": po.get("po_number", ""),
        "supplier_name": po.get("supplier_name", ""), "entity_id": po.get("entity_id", ""),
        "roll_count": len(rows), "total_length": round(total_length, 2),
        "total_base_value": round(total_base_value, 2), "rolls": rows,
    }
