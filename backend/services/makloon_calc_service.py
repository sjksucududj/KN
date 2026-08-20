"""FASE D — ESTIMASI OUTPUT MAKLOON BERBASIS GSM (PS-03) + EVALUASI SELISIH (PS-11).

Rujukan rumus baku: KN_18 §3.3 (kg kain = meter × GSM × lebar ÷ 1000) · §3.2 (woven vs knit).

Keputusan pemilik:
  * **D-03/PS-03** — estimasi output WAJIB berasal dari **GSM + lebar + susut**, bukan
    `yield_factor` yang diketik tanpa dasar. `yield_factor` hanya **override sadar**
    yang WAJIB disertai alasan (dicatat di langkah + audit log).
  * **D-04** — output rajut boleh **kg saja atau kg + meter**: modul ini tidak memaksa
    satuan; ia memakai `base_unit` produk output dan mengonversi lewat `uom_service`
    (“konversi harus universal” — permintaan pemilik).
  * **D-05** — susut standar datang dari **kontrak mitra** (`supplier_contracts`),
    fallback kebijakan global; tidak pernah dikarang.

Semua hasil membawa `explain[]` (angka antara) supaya bisa **diaudit** di UI.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core_utils import parse_decimal, rupiah
from services import uom_service
from services import uom_rules_service as uomr


async def estimate_output(*, input_product: Dict[str, Any], output_product: Dict[str, Any],
                          input_qty: Any, shrinkage_pct: Any = 0,
                          shrinkage_source: str = "kebijakan",
                          yield_factor: Any = 0, yield_reason: str = "",
                          byproduct_pct: Any = 0, process_type: str = "",
                          engine: Optional[Dict[str, Any]] = None,
                          changes_stage: bool = True,
                          stage_code: str = "", stage_label: str = "",
                          material_flow: str = "moves",
                          material_flow_source: str = "") -> Dict[str, Any]:
    """Perkirakan output 1 langkah makloon + rincian angka antara (auditable).

    Metode:
      * `gsm`            — kg efektif ÷ (GSM × lebar ÷ 1000, disesuaikan base unit output)
      * `yield_override` — pengguna memaksa yield (wajib alasan)
      * `same_unit`      — satuan input == satuan output & data GSM tidak lengkap
      * `no_transform`   — **FASE T**: tahap tidak mengubah kain (`changes_stage=False`)

    FASE T — `changes_stage=False` (mis. pembuatan kasa/screen) dihitung LEBIH DULU
    dan memotong seluruh rumus GSM. Alasannya bukan efisiensi: kalau rumus GSM tetap
    dijalankan, susut & konversi berat akan mengecilkan "hasil" sebuah langkah yang
    sebenarnya tidak menyentuh kain, sehingga estimasi printing menanggung kerugian
    yang tidak pernah terjadi.
    """
    eng = engine or await uomr.load_engine()
    fixed = eng["fixed"]
    qty_in = parse_decimal(input_qty)
    shrink = max(0.0, min(parse_decimal(shrinkage_pct), 100.0))
    yf = parse_decimal(yield_factor)
    in_unit = uomr.normalize_unit(input_product.get("base_unit") or "meter")
    out_unit = uomr.normalize_unit(output_product.get("base_unit") or "meter")
    explain: List[str] = []
    warnings: List[str] = []
    flow = str(material_flow or "moves").strip().lower() or "moves"
    label = stage_label or stage_code or process_type or "tahap ini"

    # ── FASE T — tahap yang TIDAK mengubah kain (qty keluar = qty masuk) ──────
    if not changes_stage:
        expected = round(qty_in, 3)
        explain.append(
            f"Tahap {label} TIDAK mengubah kain — hanya biaya jasanya yang dibayar. "
            f"Susut dipaksa 0% dan yield 1, jadi qty keluar = qty masuk "
            f"({qty_in:g} {in_unit}).")
        if flow == "service_only":
            explain.append(
                "Aliran kain: JASA MURNI — tidak ada bahan yang keluar gudang"
                + (f" ({material_flow_source})" if material_flow_source else "") + ".")
        else:
            explain.append(
                "Aliran kain: kain dikirim ke mitra lalu kembali utuh"
                + (f" ({material_flow_source})" if material_flow_source else "") + ".")
        if yf > 0:
            warnings.append(
                f"Yield {yf:g} diisi pada tahap {label} yang tidak mengubah kain — "
                "diabaikan supaya qty keluar tetap sama dengan qty masuk.")
        if shrink > 0:
            warnings.append(
                f"Susut {shrink:g}% diisi pada tahap {label} yang tidak mengubah kain — "
                "diabaikan (kainnya tidak diproses).")
        if parse_decimal(byproduct_pct) > 0:
            warnings.append(
                f"Barang sisa {parse_decimal(byproduct_pct):g}% diabaikan: tahap {label} "
                "tidak memotong/memproses kain sehingga tidak melahirkan sisa.")
        return {
            "method": "no_transform", "process_type": process_type,
            "stage_code": stage_code, "changes_stage": False,
            "material_flow": flow, "material_flow_source": material_flow_source,
            "input_qty": qty_in, "input_unit": in_unit,
            "input_kg": 0.0, "kg_per_input_unit": 0.0,
            "shrinkage_pct": 0.0, "shrinkage_source": "tahap tidak mengubah kain",
            "kg_effective": 0.0, "kg_per_output_unit": 0.0,
            "gsm_output": parse_decimal(output_product.get("gramasi")),
            "width_output": parse_decimal(output_product.get("lebar")),
            "fabric_type": output_product.get("fabric_type") or input_product.get("fabric_type") or "",
            "yield_factor": 0.0, "yield_reason": yield_reason,
            "expected_output_qty": expected, "output_unit": out_unit or in_unit,
            "expected_byproduct_qty": 0.0,
            "explain": explain, "warnings": warnings,
        }

    # 1) Berat bahan masuk (kg) — dasar semua rumus tekstil (KN_18 §3.3)
    kg_per_in = 1.0 if in_unit == "kg" else uom_service.kg_per_base_unit(input_product, fixed)
    input_kg = round(qty_in * kg_per_in, 3) if kg_per_in > 0 else 0.0
    if in_unit == "kg":
        explain.append(f"Bahan masuk {qty_in:g} kg.")
    elif kg_per_in > 0:
        explain.append(f"Bahan masuk {qty_in:g} {in_unit} × {kg_per_in:g} kg/{in_unit} "
                       f"(GSM {parse_decimal(input_product.get('gramasi')):g} × lebar "
                       f"{parse_decimal(input_product.get('lebar')):g} m) = {input_kg:g} kg.")
    else:
        warnings.append(
            f"Produk bahan '{input_product.get('sku') or input_product.get('name') or '-'}' "
            "belum punya gramasi/lebar — berat bahan tidak bisa dihitung.")

    # 2) Susut proses (dari kontrak mitra — D-05)
    kg_eff = round(input_kg * (1 - shrink / 100.0), 3)
    if input_kg > 0:
        explain.append(f"Susut {shrink:g}% ({shrinkage_source}) → berat efektif {kg_eff:g} kg.")

    # 3) Konversi berat efektif → satuan output
    kg_per_out = 1.0 if out_unit == "kg" else uom_service.kg_per_base_unit(output_product, fixed)
    method = "gsm"
    expected = 0.0
    if yf > 0:
        method = "yield_override"
        expected = round(qty_in * yf * (1 - shrink / 100.0), 3)
        explain.append(f"OVERRIDE yield {yf:g} {out_unit}/{in_unit} dipakai → "
                       f"{qty_in:g} × {yf:g} − susut {shrink:g}% = {expected:g} {out_unit}"
                       + (f" · alasan: {yield_reason}" if yield_reason else ""))
        if not yield_reason:
            warnings.append("Override yield tanpa alasan — wajib diisi agar bisa diaudit (PS-03).")
    elif kg_per_out > 0 and kg_eff > 0:
        expected = round(kg_eff / kg_per_out, 3) if out_unit != "kg" else kg_eff
        if out_unit == "kg":
            explain.append(f"Output rajut/berat → {expected:g} kg (D-04: kg sebagai satuan dasar).")
        else:
            explain.append(
                f"Output {out_unit}: {kg_eff:g} kg ÷ {kg_per_out:g} kg/{out_unit} "
                f"(GSM {parse_decimal(output_product.get('gramasi')):g} × lebar "
                f"{parse_decimal(output_product.get('lebar')):g} m) = {expected:g} {out_unit}.")
    elif in_unit == out_unit:
        method = "same_unit"
        expected = round(qty_in * (1 - shrink / 100.0), 3)
        warnings.append("GSM/lebar produk belum lengkap — estimasi memakai satuan yang sama "
                        "dikurangi susut. Lengkapi gramasi & lebar agar akurat (PS-03).")
        explain.append(f"Estimasi satuan sama: {qty_in:g} {in_unit} − susut {shrink:g}% "
                       f"= {expected:g} {out_unit}.")
    else:
        method = "unknown"
        warnings.append(
            "Estimasi tidak dapat dihitung: produk output belum punya gramasi & lebar, "
            "dan satuan input≠output. Isi GSM/lebar produk atau pakai override yield + alasan.")

    byp = round(qty_in * parse_decimal(byproduct_pct) / 100.0, 3)
    if byp:
        explain.append(f"Barang sisa diperkirakan {byp:g} {in_unit} "
                       f"({parse_decimal(byproduct_pct):g}% dari bahan).")

    return {
        "method": method, "process_type": process_type,
        "input_qty": qty_in, "input_unit": in_unit,
        "input_kg": input_kg, "kg_per_input_unit": round(kg_per_in, 6),
        "shrinkage_pct": shrink, "shrinkage_source": shrinkage_source,
        "kg_effective": kg_eff,
        "kg_per_output_unit": round(kg_per_out, 6),
        "gsm_output": parse_decimal(output_product.get("gramasi")),
        "width_output": parse_decimal(output_product.get("lebar")),
        "fabric_type": output_product.get("fabric_type") or input_product.get("fabric_type") or "",
        "yield_factor": yf, "yield_reason": yield_reason,
        "expected_output_qty": expected, "output_unit": out_unit,
        "expected_byproduct_qty": byp,
        "explain": explain, "warnings": warnings,
    }


def evaluate_variance(*, expected_qty: Any, actual_qty: Any, tolerance_pct: Any,
                      unit: str = "", unit_value: Any = 0) -> Dict[str, Any]:
    """Bandingkan estimasi vs aktual + tentukan apakah klaim wajib (PS-11/D-09).

    Kekurangan (aktual < estimasi) di luar toleransi → `claim_required=True`.
    Kelebihan di luar toleransi → hanya `over_delivery` (peringatan, tidak menagih mitra).
    """
    exp = parse_decimal(expected_qty)
    act = parse_decimal(actual_qty)
    tol = max(parse_decimal(tolerance_pct), 0.0)
    diff = round(act - exp, 3)
    pct = round(diff / exp * 100.0, 3) if exp > 0 else None
    shortfall = round(max(exp - act, 0.0), 3)
    level, claim_required, over = "ok", False, False
    if pct is not None:
        if pct < -tol:
            level, claim_required = "shortfall", True
        elif pct > tol:
            level, over = "over_delivery", True
    value = round(shortfall * parse_decimal(unit_value), 2)
    msg = ""
    if level == "shortfall":
        msg = (f"Hasil kurang {abs(pct):.2f}% dari estimasi "
               f"({act:g} vs {exp:g} {unit}) — melewati toleransi {tol:g}%. "
               f"Kekurangan {shortfall:g} {unit} ≈ {rupiah(value)}.")
    elif level == "over_delivery":
        msg = (f"Hasil lebih {pct:.2f}% dari estimasi ({act:g} vs {exp:g} {unit}) — "
               f"periksa timbangan/ukuran atau perbarui standar susut kontrak.")
    return {
        "expected_qty": exp, "actual_qty": act, "unit": unit,
        "variance_qty": diff, "variance_pct": pct, "tolerance_pct": tol,
        "shortfall_qty": shortfall, "unit_value": parse_decimal(unit_value, 2),
        "shortfall_value": value, "level": level,
        "claim_required": claim_required, "over_delivery": over, "message": msg,
    }
