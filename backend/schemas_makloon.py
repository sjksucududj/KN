"""M1 (Makloon/Subcon) — schemas untuk master Makloon + Resep Proses + Forecast.

Di-re-export dari schemas.py. Patch memakai GenericPatch (data dict) seperti supplier.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core_utils import MoneyDecimal, OptQtyDecimal, QtyDecimal
from domain_registry import values_of

# R7 — nilai enum TIDAK boleh hardcode: satu registry (Fase A · PS-01).
# `rajut` & `pre_treatment` ditambahkan di Fase A (D-02/D-03).
PROCESS_TYPES = values_of("process_type")


class MakloonCreate(BaseModel):
    name: str
    npwp: str = ""
    pic_name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    process_types: List[str] = Field(default_factory=list)   # tenun|celup|finishing|...
    capacity_note: str = ""
    capacity_per_month: float = Field(0, ge=0)               # kapasitas (unit output/bln)
    capacity_unit: str = "yard"
    default_tariff: float = Field(0, ge=0)                   # ongkos jasa default
    tariff_unit: str = "output"                              # output|input|roll
    payment_term_code: str = ""
    lead_time_days: int = Field(0, ge=0)
    entity_id: str = ""
    notes: str = ""
    created_by: str = ""


class ProcessRecipeCreate(BaseModel):
    name: str
    process_type: str = "tenun"
    input_product_id: str = ""
    input_stage: str = "yarn"
    output_product_id: str = ""
    output_stage: str = "grey"
    yield_factor: QtyDecimal = Field(1.0, ge=0)       # output_unit per input_unit (PS-15)
    waste_pct: QtyDecimal = Field(0, ge=0, le=100)    # susut proses (%) — PS-15
    byproduct_pct: QtyDecimal = Field(0, ge=0, le=100)  # barang sisa (%) kembali ke KN
    byproduct_product_id: str = ""
    default_makloon_id: str = ""
    default_tariff: MoneyDecimal = Field(0, ge=0)
    tariff_unit: str = "output"          # output|input|roll
    aux_cost_default: MoneyDecimal = Field(0, ge=0)   # bahan pembantu (obat celup)
    formula: str = ""                     # ekspresi bebas (opsional); var: input_qty, gramasi, lebar, yield_factor, waste_pct, byproduct_pct
    entity_id: str = ""
    notes: str = ""
    created_by: str = ""


class ForecastPreviewIn(BaseModel):
    recipe_id: str = ""                   # bila diisi → muat parameter resep sbg dasar
    input_qty: QtyDecimal = Field(0, ge=0)                  # PS-15/R5 — desimal koma
    yield_factor: OptQtyDecimal = Field(None, ge=0)
    waste_pct: OptQtyDecimal = Field(None, ge=0, le=100)
    byproduct_pct: OptQtyDecimal = Field(None, ge=0, le=100)
    formula: Optional[str] = None
    gramasi: QtyDecimal = Field(0, ge=0)
    lebar: QtyDecimal = Field(0, ge=0)


# ─── M3 (Makloon Orders) — transaksi makloon/subkontrak ──────────────────────

class MakloonStepInput(BaseModel):
    """Satu langkah proses dalam order makloon (rantai berlapis).

    FASE D — langkah membawa referensi **kontrak** (SSOT tarif/susut/toleransi),
    basis tarif bebas + formula custom, biaya tambahan (screen/repeat), serta
    override yield yang WAJIB disertai alasan (PS-03).
    """
    process_type: str = "tenun"
    # ── FASE T — TAHAP dari master `process_stages` (di SAMPING `process_type`).
    # Kosong = tahap dicari dari `process_type` (jalur SPK sebelum FASE T), sehingga
    # klien lama tidak berubah arti. Diisi = baris master itu yang menentukan
    # apakah kain berubah (`changes_stage`) & bergerak (`material_flow`).
    stage_code: str = ""
    # FASE T (keputusan 1c) — hanya berlaku bila master tahap membuka dua-duanya
    # (`material_flow="either"`): moves = kain dikirim & kembali · service_only =
    # jasa murni (kain tidak bergerak). Kosong = pakai bawaan master.
    material_flow: str = ""
    makloon_id: str = ""
    recipe_id: str = ""
    contract_id: str = ""                             # kontrak mitra (opsional; auto-resolve)
    input_product_id: str = ""
    output_product_id: str = ""
    byproduct_product_id: str = ""
    input_qty: QtyDecimal = Field(0, ge=0)            # step 1 = qty material; step>1 diisi otomatis (PS-15)
    yield_factor: QtyDecimal = Field(0, ge=0)         # 0 = pakai rumus GSM (PS-03); >0 = override sadar
    yield_override_reason: str = ""                   # WAJIB bila yield_factor diisi (PS-03)
    waste_pct: OptQtyDecimal = Field(None, ge=0, le=100)     # None = ambil dari kontrak/kebijakan (D-05)
    tolerance_pct: OptQtyDecimal = Field(None, ge=0, le=100)  # None = kontrak → kebijakan (D-09)
    byproduct_pct: QtyDecimal = Field(0, ge=0, le=100)
    formula: str = ""
    tariff: MoneyDecimal = Field(0, ge=0)             # ongkos jasa borongan (legacy/manual)
    aux_cost: MoneyDecimal = Field(0, ge=0)
    # Fase A · D-03 — tujuan pre_treatment: dye (→PFD) | print (→PFP)
    target_use: str = ""
    # Fase D · D-06/D-07 — basis tarif BEBAS per kontrak/mitra + formula custom
    tariff_basis: str = ""
    tariff_rate: MoneyDecimal = Field(0, ge=0)
    tariff_formula: str = ""
    min_charge: MoneyDecimal = Field(0, ge=0)
    ppi: QtyDecimal = Field(0, ge=0)                  # pick per inch (basis `pick`)
    aux_fees: List[Dict[str, Any]] = Field(default_factory=list)
    roll_count: int = Field(0, ge=0)                  # untuk basis per-roll & biaya per-roll
    colors: int = Field(0, ge=0)                      # printing — jumlah warna (biaya screen)
    repeats: int = Field(0, ge=0)                     # printing — jumlah repeat


class MakloonOrderCreate(BaseModel):
    mode: str = "process_only"            # process_only | buy_process
    material_product_id: str
    material_qty: QtyDecimal = Field(..., gt=0)        # PS-15/R5
    material_unit: str = ""
    from_warehouse_id: str = ""
    target_warehouse_id: str = ""
    # buy_process → PO bahan (opsional; dibuat sbg PO standar tertaut)
    supplier_id: str = ""
    supplier_name: str = ""
    material_price: float = Field(0, ge=0)
    expected_delivery_date: str = ""
    steps: List[MakloonStepInput] = Field(default_factory=list)
    notes: str = ""
    entity_id: str = ""
    created_by: str = ""


class MakloonIssueIn(BaseModel):
    step_seq: int = Field(..., ge=1)
    from_warehouse_id: str = ""           # override gudang sumber bahan (opsional)
    # FASE D (PS-08/D-07) — mitra memakai satuan sendiri: konversi + jejak tersimpan
    doc_uom: str = ""
    doc_qty: QtyDecimal = Field(0, ge=0)


class MakloonReceiveRoll(BaseModel):
    """Satu roll output fisik — LOT WAJIB manual (nomor lot dari makloon/supplier)."""
    lot: str
    length: QtyDecimal = Field(..., gt=0)             # PS-15/R5
    grade: str = "A"                                  # PS-09/D-01 — enum A|A1|A2|B|BS
    dye_lot: str = ""                                 # Fase C — batch warna (shade)


class MakloonReceiveIn(BaseModel):
    step_seq: int = Field(..., ge=1)
    actual_output_qty: QtyDecimal = Field(0, ge=0)     # PS-15/R5
    actual_byproduct_qty: QtyDecimal = Field(0, ge=0)
    tariff: MoneyDecimal = Field(0, ge=0)             # ongkos jasa aktual (0 = hitung dari kontrak)
    aux_cost: MoneyDecimal = Field(0, ge=0)           # bahan pembantu (obat celup) aktual
    ppn: MoneyDecimal = Field(0, ge=0)                # PPN atas jasa (opsional)
    output_warehouse_id: str = ""
    byproduct_lot: str = ""
    supplier_invoice_no: str = ""
    # FASE D — laporan mitra dalam satuan sendiri (kg/bale/roll) → konversi + jejak
    output_uom: str = ""
    output_doc_qty: QtyDecimal = Field(0, ge=0)
    colors: int = Field(0, ge=0)
    repeats: int = Field(0, ge=0)
    rolls: List[MakloonReceiveRoll] = Field(default_factory=list)  # LOT manual per roll output


class MakloonServiceIn(BaseModel):
    """FASE T — catat JASA langkah yang tidak memindahkan kain (mis. pembuatan kasa).

    Sengaja TIDAK punya `rolls`/`actual_output_qty`: tidak ada roll yang lahir dan qty
    kainnya tidak berubah (diambil dari `input_qty` langkah). Menyediakan field itu
    akan mengundang petugas "mengisi hasil" untuk pekerjaan yang tidak menghasilkan kain.
    """
    step_seq: int = Field(..., ge=1)
    tariff: MoneyDecimal = Field(0, ge=0)      # 0 = hitung dari kontrak/basis langkah
    aux_cost: MoneyDecimal = Field(0, ge=0)
    ppn: MoneyDecimal = Field(0, ge=0)
    supplier_invoice_no: str = ""
    colors: int = Field(0, ge=0)               # jumlah warna (kasa dibuat per warna)
    repeats: int = Field(0, ge=0)
    roll_count: int = Field(0, ge=0)
    note: str = ""


class MakloonClaimIn(BaseModel):
    """Ajukan tindakan klaim selisih (D-09) — eksekusi menunggu approval."""
    step_seq: int = Field(..., ge=1)
    action: str                                        # potong_bon | tagih_ganti | terima_catatan
    amount: MoneyDecimal = Field(0, ge=0)
    reason: str = ""


class MakloonClaimDecisionIn(BaseModel):
    step_seq: int = Field(..., ge=1)
    note: str = ""
    reason: str = ""


class MakloonEstimateIn(BaseModel):
    """Pratinjau wizard: estimasi GSM + tarif kontrak (tanpa menyimpan apa pun)."""
    input_product_id: str
    output_product_id: str = ""
    makloon_id: str = ""
    contract_id: str = ""
    process_type: str = ""
    # ── FASE T — tahap & aliran kain juga dipratinjau, supaya layar bisa
    # memperlihatkan `no_transform` (kain tidak berubah) SEBELUM disimpan. Tanpa dua
    # field ini, pratinjau wizard selalu memakai jalur "tahap tidak dikenal" dan
    # menampilkan angka yang berbeda dari yang akan tersimpan.
    stage_code: str = ""
    material_flow: str = ""
    input_qty: QtyDecimal = Field(0, ge=0)
    input_uom: str = ""
    waste_pct: OptQtyDecimal = Field(None, ge=0, le=100)
    tolerance_pct: OptQtyDecimal = Field(None, ge=0, le=100)
    yield_factor: QtyDecimal = Field(0, ge=0)
    yield_override_reason: str = ""
    byproduct_pct: QtyDecimal = Field(0, ge=0, le=100)
    tariff_basis: str = ""
    tariff_rate: OptQtyDecimal = Field(None, ge=0)
    tariff_formula: str = ""
    min_charge: OptQtyDecimal = Field(None, ge=0)
    ppi: OptQtyDecimal = Field(None, ge=0)
    aux_fees: List[Dict[str, Any]] = Field(default_factory=list)
    roll_count: int = Field(0, ge=0)
    colors: int = Field(0, ge=0)
    repeats: int = Field(0, ge=0)
    entity_id: str = ""


class MakloonOrderCancel(BaseModel):
    reason: str = ""
