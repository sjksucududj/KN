"""FASE D/E — Skema `supplier_contracts` (kontrak mitra makloon & supplier).

Rujukan: KN_18 §5.1 (nama koleksi final `supplier_contracts`, prefix `sct_`),
PS-06 (kontrak harga sebagai acuan PO/Makloon), PS-11 (toleransi susut per kontrak),
keputusan pemilik sesi 2026-07-25:
  * **D-05** — susut standar ditentukan **per mitra/kontrak** (bukan default global).
  * **D-07** — basis tarif BEBAS (pick/kg/meter/yard/bale/cone/roll/lot/lumpsum) +
    **formula custom** per kontrak → "jangan terpaku pada satu variabel".
  * **D-09** — toleransi selisih & konsekuensi klaim diatur di kontrak.

Semua qty/uang memakai tipe desimal PS-15 (menerima "10,5" maupun "10.5").
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from core_utils import MoneyDecimal, OptQtyDecimal, QtyDecimal


class ContractAuxFee(BaseModel):
    """Biaya tambahan kontrak (mis. screen & repeat untuk printing)."""
    code: str = ""
    label: str = ""
    basis: str = "lumpsum"       # lumpsum|per_roll|per_color|per_repeat|per_kg|per_meter|per_output_unit
    amount: MoneyDecimal = Field(0, ge=0)


class SupplierContractCreate(BaseModel):
    contract_type: str = "makloon"        # makloon | purchase (Fase E)
    partner_id: str = ""                  # makloon_id (makloon) | supplier_id (purchase)
    partner_name: str = ""
    title: str = ""
    process_type: str = ""                # wajib untuk contract_type=makloon
    product_id: str = ""                  # "" = berlaku untuk semua produk
    input_product_id: str = ""            # "" = bebas
    # ── Tarif (D-07: basis bebas + formula custom) ──────────────────────────
    tariff_basis: str = "lumpsum"
    tariff_rate: MoneyDecimal = Field(0, ge=0)
    tariff_formula: str = ""              # opsional; var: qty_base, basis_qty, rate, gsm, lebar, ppi, roll_count, colors, repeats
    tariff_qty_source: str = "output"     # output | input — qty dasar perhitungan tarif
    ppi: QtyDecimal = Field(0, ge=0)      # pick per inch (basis `pick`) bila produk belum punya konstruksi
    aux_fees: List[ContractAuxFee] = Field(default_factory=list)
    min_charge: MoneyDecimal = Field(0, ge=0)
    currency: str = "IDR"
    # ── Standar proses (D-05) & toleransi selisih (D-09) ───────────────────
    shrinkage_pct: QtyDecimal = Field(0, ge=0, le=100)
    tolerance_pct: OptQtyDecimal = Field(None, ge=0, le=100)
    yield_factor: QtyDecimal = Field(0, ge=0)    # 0 = pakai rumus GSM (PS-03)
    byproduct_pct: QtyDecimal = Field(0, ge=0, le=100)
    # ── Komersial ──────────────────────────────────────────────────────────
    moq: QtyDecimal = Field(0, ge=0)
    lead_time_days: int = Field(0, ge=0)
    payment_term_code: str = ""
    valid_from: str = ""
    valid_to: str = ""
    status: str = "active"                # draft | active | expired | terminated
    sample_ref: str = ""                  # referensi labdip/proofing (Fase F)
    notes: str = ""
    entity_id: str = ""


class SupplierContractPatch(BaseModel):
    title: Optional[str] = None
    partner_name: Optional[str] = None
    process_type: Optional[str] = None
    product_id: Optional[str] = None
    input_product_id: Optional[str] = None
    tariff_basis: Optional[str] = None
    tariff_rate: Optional[MoneyDecimal] = None
    tariff_formula: Optional[str] = None
    tariff_qty_source: Optional[str] = None
    ppi: Optional[QtyDecimal] = None
    aux_fees: Optional[List[ContractAuxFee]] = None
    min_charge: Optional[MoneyDecimal] = None
    shrinkage_pct: Optional[QtyDecimal] = None
    tolerance_pct: Optional[QtyDecimal] = None
    yield_factor: Optional[QtyDecimal] = None
    byproduct_pct: Optional[QtyDecimal] = None
    moq: Optional[QtyDecimal] = None
    lead_time_days: Optional[int] = None
    payment_term_code: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    sample_ref: Optional[str] = None
    notes: Optional[str] = None


class ContractStatusIn(BaseModel):
    status: str
    reason: str = ""


class TariffPreviewIn(BaseModel):
    """Simulasi tarif — dipakai wizard makloon agar angka bisa diaudit sebelum simpan."""
    contract_id: str = ""
    partner_id: str = ""
    process_type: str = ""
    product_id: str = ""
    qty: QtyDecimal = Field(0, ge=0)
    unit: str = ""                      # default: base unit produk
    roll_count: int = Field(0, ge=0)
    colors: int = Field(0, ge=0)
    repeats: int = Field(0, ge=0)
    # override manual (menang atas kontrak) — kasus ad-hoc tanpa kontrak
    tariff_basis: str = ""
    tariff_rate: OptQtyDecimal = Field(None, ge=0)
    tariff_formula: str = ""
    min_charge: OptQtyDecimal = Field(None, ge=0)
    ppi: OptQtyDecimal = Field(None, ge=0)
    aux_fees: List[ContractAuxFee] = Field(default_factory=list)


class MakloonPolicyIn(BaseModel):
    """Kebijakan makloon (configurable tanpa deploy) — D-05/D-09."""
    variance_tolerance_pct: Optional[QtyDecimal] = Field(None, ge=0, le=100)
    default_shrinkage_pct: Optional[QtyDecimal] = Field(None, ge=0, le=100)
    contract_mode: Optional[str] = None       # off | warn | block
    auto_claim: Optional[bool] = None
    claim_approval_roles: Optional[List[str]] = None
    require_output_product: Optional[bool] = None
    require_yield_reason: Optional[bool] = None
