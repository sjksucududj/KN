"""Purchasing / Procurement request schemas (di-reexport oleh `schemas.py`).

Dipisah dari `schemas.py` untuk menjaga batas ukuran file (compliance ≤800 baris).
Mencakup: Purchase Order + Amend, Blanket/Contract PO + Call-off, Supplier +
Supplier Price-List, Cash Transaction, PO Payment/Close, Vendor Bill (3-way),
Landed Cost, Input Tax (Faktur Masukan), RFQ, QC 4-point, Purchase Return,
Goods Receipt (GR/roll). Kontrak field TIDAK berubah (kode menang)."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from core_utils import MoneyDecimal, OptQtyDecimal, QtyDecimal


# ─── R0 — Return Policy Engine (per-supplier, extensible) ────────────────────

# Mode refund kanonik untuk RETUR BELI (KN → supplier).
SUPPLIER_REFUND_MODES = ("cash", "ap_credit", "none")
# Klasifikasi asal barang (memengaruhi kebijakan retur — impor sering tak bisa diretur).
ORIGIN_TYPES = ("local", "import")


class ReturnPolicyInput(BaseModel):
    """Kebijakan retur ke supplier (R0). Semua field punya default aman;
    `custom_fields` bersifat extensible sehingga user dapat menambah aturan sendiri
    tanpa perubahan skema (keputusan owner #6)."""
    window_days: int = Field(30, ge=0, le=3650)             # batas hari retur (0 = tanpa batas eksplisit)
    refund_modes: List[str] = ["ap_credit"]                 # subset dari SUPPLIER_REFUND_MODES
    returnable_to_supplier: bool = True                     # False → impor sulit diretur → arahkan regrade + jual lokal
    rma_required: bool = False                              # wajib nomor RMA sebelum kirim balik
    restocking_fee_pct: float = Field(0.0, ge=0, le=100)    # biaya restocking (%)
    condition_requirements: str = ""                        # syarat kondisi barang (mis. kemasan asli, belum dipotong)
    custom_fields: Dict[str, Any] = {}                      # extensible — aturan tambahan buatan user
    valid_from: str = ""
    valid_until: str = ""
    notes: str = ""


# ─── Purchase Order Schemas ──────────────────────────────────────────────────

class POItemCreate(BaseModel):
    product_id: str
    quantity: QtyDecimal = Field(..., ge=0)                # PS-15/R5 — terima "10,5" & "10.5"
    unit: str = "meter"
    price: MoneyDecimal = Field(0.0, ge=0)
    discount_percent: MoneyDecimal = Field(0, ge=0, le=100)  # P0-1 — diskon per item dari supplier (0–100%)
    # Fase A · PS-09/D-19 — grade yang diharapkan WAJIB dipilih (tidak ada default).
    expected_grade: str = ""
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)
    # Keputusan pemilik 2026-08-19: panjang 1 PANEL berbeda PER PESANAN, jadi
    # faktornya ditulis di BARIS dokumen — hanya sah untuk satuan yang masternya
    # ber-`factor_per_document=true` (mis. PANEL); dijaga `uom_service.line_factor`.
    unit_factor: Optional[float] = Field(None, gt=0)
    unit_factor_to: str = ""


class PurchaseOrderCreate(BaseModel):
    supplier_id: str = ""             # Fase 3 — FK ke suppliers (opsional; fallback manual)
    supplier_name: str = ""           # snapshot/manual (backward compat bila tanpa supplier_id)
    supplier_contact: str = ""
    warehouse_id: str
    items: List[POItemCreate]
    expected_delivery_date: str = ""
    notes: str = ""
    created_by: str = "Admin"
    entity_id: str = ""
    order_discount_percent: float = Field(0, ge=0, le=100)  # P0-1 — diskon level order (0–100%)
    tax_mode: str = ""                # P0-1 — "" = ikut config | "ppn" (PPN Masukan) | "non_ppn"
    import_flag: Optional[bool] = None  # R0 — override asal barang: None=ikut supplier.origin_type, True=impor, False=lokal
    # R6.3 — Budget Control: tag anggaran PO (opsional). Default = akun Persediaan (1-1300).
    budget_dimension: Optional[str] = ""   # "account" | "category"
    budget_key: Optional[str] = ""         # kode akun COA | kode kategori beban


class PurchaseOrderAmend(BaseModel):
    """Phase 7.2 — amandemen PO (revisi item/supplier/tanggal/catatan) + re-approval.
    `items` opsional: bila None → item tidak diubah. `reason` WAJIB (jejak audit)."""
    reason: str                       # WAJIB — alasan amandemen (audit)
    items: Optional[List[POItemCreate]] = None
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_contact: Optional[str] = None
    warehouse_id: Optional[str] = None
    expected_delivery_date: Optional[str] = None
    notes: Optional[str] = None
    order_discount_percent: Optional[float] = Field(None, ge=0, le=100)
    tax_mode: Optional[str] = None
    amended_by: str = "Admin"


# ─── Blanket / Contract PO Schemas (P2 — call-off) ───────────────────────────

class BlanketPOItemCreate(BaseModel):
    product_id: str
    contract_qty: float = Field(..., ge=0)                # 1.c — komitmen kuantitas per item
    contract_price: float = Field(0.0, ge=0)        # harga sepakat (default call-off; 3.b boleh override)
    unit: str = ""                     # default = base_unit produk


class BlanketPOCreate(BaseModel):
    """P2 — kontrak Blanket/Contract PO. Tidak memicu penerimaan; call-off yang menariknya."""
    supplier_id: str = ""
    supplier_name: str = ""
    supplier_contact: str = ""
    warehouse_id: str                  # gudang default untuk call-off
    items: List[BlanketPOItemCreate]
    contract_value_cap: float = 0.0    # 1.c — plafon nilai GROSS (Rp); 0 = Σ qty×harga
    valid_from: str = ""
    valid_until: str = ""              # "" = open (tak kadaluarsa)
    notes: str = ""
    created_by: str = "Admin"
    entity_id: str = ""


class CallOffItemCreate(BaseModel):
    product_id: str
    quantity: float = Field(..., ge=0)
    unit: str = ""
    price: float = Field(0.0, ge=0)                 # 0 = pakai harga kontrak; >0 & beda = override (3.b)
    discount_percent: float = Field(0, ge=0, le=100)


class CallOffCreate(BaseModel):
    """P2 — call-off (release) terhadap Blanket PO → menjadi PO anak normal (2.a)."""
    items: List[CallOffItemCreate]
    warehouse_id: str = ""             # default ikut kontrak
    expected_delivery_date: str = ""
    notes: str = ""
    price_override_reason: str = ""    # WAJIB bila ada override harga (3.b)
    order_discount_percent: float = Field(0, ge=0, le=100)
    tax_mode: str = ""
    created_by: str = "Admin"


class BlanketCloseRequest(BaseModel):
    reason: str = ""


# ─── Procurement Schemas (Fase 3 — Supplier Master + Pengelolaan Kas) ─────────

class SupplierCreate(BaseModel):
    name: str
    npwp: str = ""
    pic_name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    goods_type: str = ""              # jenis barang yang dipasok (benang/kain/bahan printing)
    payment_term_code: str = ""
    lead_time_days: int = Field(0, ge=0)           # Depth #3 — estimasi lead time default supplier (hari)
    entity_id: str = ""
    notes: str = ""
    created_by: str = "Admin"
    # ── R0 — Origin (impor/lokal) + Return Policy Engine ──
    origin_type: str = "local"        # local | import (memengaruhi kebijakan retur)
    country: str = ""                 # negara asal (relevan untuk import)
    return_policy: Optional[ReturnPolicyInput] = None  # embedded; None = pakai default engine


# ─── Depth #3: Supplier Price-List (koleksi supplier_price_lists, prefix spl_) ─

class SupplierPriceListCreate(BaseModel):
    product_id: str
    price: float = Field(..., ge=0)                      # harga beli per `unit`
    unit: str = ""                    # UOM; kosong → base_unit produk (UOM engine 1.13)
    min_qty: float = Field(0, ge=0)                # MOQ agar harga ini berlaku (0 = tanpa minimum)
    lead_time_days: int = Field(0, ge=0)           # lead time khusus produk; 0 = pakai default supplier
    valid_from: str = ""              # ISO/tanggal mulai berlaku; "" = sejak sekarang
    valid_until: str = ""             # ISO/tanggal kadaluarsa; "" = tanpa kadaluarsa
    currency: str = "IDR"
    notes: str = ""
    created_by: str = "Admin"


class CashTransactionCreate(BaseModel):
    cash_type: str = "kas_kecil"      # kas_kecil (per entitas) | kas_besar (gabungan)
    direction: str = "out"            # in (masuk) | out (keluar)
    amount: float = Field(..., ge=0)
    category: str = ""                # pembelian | operasional | gaji | lain
    description: str = ""
    entity_id: str = ""               # untuk kas_kecil; kas_besar dipaksa "all"
    ref_type: str = ""                # purchase_order | manual | ...
    ref_id: str = ""
    txn_date: str = ""                # ISO; default = sekarang
    account_id: str = ""              # EPIC7B — akun kas/bank (opsional)
    created_by: str = "Admin"


# ─── Depth #1: PO Payment + Retur Beli (Purchase Return / Nota Debit) ─────────

class POPaymentCreate(BaseModel):
    amount: float = Field(..., ge=0)
    cash_type: str = "kas_besar"      # kas_kecil | kas_besar (sumber dana)
    entity_id: str = ""               # untuk kas_kecil
    method: str = "transfer"          # transfer | tunai | giro
    notes: str = ""
    paid_at: str = ""                 # ISO; default sekarang
    created_by: str = "Admin"


class POCloseRequest(BaseModel):
    reason: str = ""                  # alasan tutup kurang (short-close)
    created_by: str = "Admin"


# ─── Fase 5.2 (P0-2): Vendor Bill + 3-Way Matching ───────────────────────────

class VendorBillItemInput(BaseModel):
    product_id: str
    billed_qty: float = Field(..., ge=0)                 # qty yang ditagih supplier pada bill ini
    price: float = Field(0.0, ge=0)                # harga per unit (0 = ikut harga PO)
    discount_percent: float = Field(0, ge=0, le=100)       # diskon per item (0–100%)


class VendorBillCreate(BaseModel):
    po_id: str                        # PO referensi (wajib — 3-way match)
    supplier_invoice_no: str = ""     # nomor invoice asli supplier (dedupe)
    bill_date: str = ""               # ISO; default sekarang
    due_date: str = ""                # jatuh tempo (aging AP)
    match_mode: str = "received"      # received (3-way ketat) | ordered (longgar)
    items: List[VendorBillItemInput]
    order_discount_percent: float = Field(0, ge=0, le=100)
    tax_mode: str = ""                # "" ikut PO/config | "ppn" | "non_ppn"
    notes: str = ""
    entity_id: str = ""
    submit_now: bool = False          # True = langsung submit setelah dibuat
    created_by: str = "Admin"


class VendorBillPaymentCreate(BaseModel):
    amount: float = Field(..., ge=0)
    cash_type: str = "kas_besar"      # kas_kecil | kas_besar (sumber dana)
    entity_id: str = ""
    method: str = "transfer"          # transfer | tunai | giro
    notes: str = ""
    paid_at: str = ""
    created_by: str = "Admin"
    # FASE G-3 — keputusan selisih pembayaran supplier:
    #   {"kind": "ap_writeoff"|"ap_advance"|"ap_outstanding", "reason_code": "...", "note": "..."}
    variance: Optional[Dict[str, Any]] = None


class VendorBillDecision(BaseModel):
    notes: str = ""                   # alasan reject/cancel


# ── Fase 5.4 (P0-5): Landed Cost Voucher → alokasi HPP roll ────────────────────
class LandedCostLineInput(BaseModel):
    category: str = "freight"         # freight|duty|insurance|handling|other
    description: str = ""
    amount: float = Field(0.0, ge=0)               # nominal biaya (Rp)


class LandedCostCreate(BaseModel):
    po_ids: List[str]                 # PO referensi (≥1) sumber roll yang dibebani
    provider_name: str = ""           # penyedia jasa (forwarder/bea cukai/asuransi)
    supplier_invoice_no: str = ""     # nomor invoice penyedia (dedupe)
    basis: str = "value"              # value (proporsional nilai) | quantity (panjang)
    cost_lines: List[LandedCostLineInput]
    voucher_date: str = ""            # ISO; default sekarang
    due_date: str = ""                # jatuh tempo (AP landed cost)
    notes: str = ""
    entity_id: str = ""
    submit_now: bool = False          # True = langsung submit (pending_approval)
    created_by: str = "Admin"


class LandedCostPaymentCreate(BaseModel):
    amount: float = Field(..., ge=0)
    cash_type: str = "kas_besar"      # kas_kecil | kas_besar (sumber dana)
    entity_id: str = ""
    method: str = "transfer"          # transfer | tunai | giro
    notes: str = ""
    paid_at: str = ""
    created_by: str = "Admin"


class LandedCostDecision(BaseModel):
    notes: str = ""                   # alasan reject/cancel


# ── Fase 5.5 (P0-3): Faktur Pajak Masukan (Input VAT) dari Vendor Bill ─────────
class InputTaxInvoiceCreate(BaseModel):
    vendor_bill_id: str               # Vendor Bill sumber (posted/paid, ber-PPN)
    nsfp: str                         # Nomor Seri Faktur Pajak supplier (16-digit; dedupe)
    faktur_date: str = ""             # tanggal faktur pajak supplier (default = bill_date)
    kode_transaksi: str = "01"        # kode transaksi faktur (default 01)
    notes: str = ""
    created_by: str = "Admin"


class InputTaxInvoiceCancel(BaseModel):
    reason: str                       # alasan pembatalan (wajib)


# ── Fase 6.1 (P1): RFQ / Quotation ────────────────────────────────────────────
class RFQItemInput(BaseModel):
    product_id: str
    quantity: float = Field(..., ge=0)
    unit: str = "meter"
    note: str = ""
    line_id: str = ""
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)
    # Keputusan pemilik 2026-08-19: panjang 1 PANEL berbeda PER PESANAN, jadi
    # faktornya ditulis di BARIS dokumen — hanya sah untuk satuan yang masternya
    # ber-`factor_per_document=true` (mis. PANEL); dijaga `uom_service.line_factor`.
    unit_factor: Optional[float] = Field(None, gt=0)
    unit_factor_to: str = ""


class RFQCreate(BaseModel):
    source: str = "manual"            # "manual" | "pr"
    pr_id: str = ""                   # bila source=pr
    title: str = ""
    entity_id: str = ""
    warehouse_id: str
    items: List[RFQItemInput] = []    # diabaikan bila source=pr (ditarik dari PR)
    supplier_ids: List[str] = []      # supplier yang diundang
    needed_by_date: str = ""
    due_date: str = ""                # batas akhir penawaran
    notes: str = ""
    created_by: str = "Admin"


class RFQQuoteLine(BaseModel):
    line_id: str
    price: float = Field(0, ge=0)
    available: bool = True
    note: str = ""


class RFQQuoteSubmit(BaseModel):
    supplier_id: str
    lines: List[RFQQuoteLine] = []
    valid_until: str = ""
    lead_time_days: int = Field(0, ge=0)
    note: str = ""


class RFQLineAward(BaseModel):
    line_id: str
    supplier_id: str
    price: float = Field(0, ge=0)


class RFQAward(BaseModel):
    mode: str = "full"                # "full" | "line"
    full_supplier_id: str = ""        # bila mode=full
    line_awards: List[RFQLineAward] = []  # bila mode=line


class RFQDecision(BaseModel):
    reason: str = ""


# ── Fase 6.2 (P1): QC 4-Point Inspection per roll ─────────────────────────────
class RollDefectInput(BaseModel):
    point_value: int                  # 1..4 (severity 4-point)
    count: int = 0                    # jumlah defect pada nilai poin ini
    note: str = ""


class RollInspectionInput(BaseModel):
    defects: List[RollDefectInput] = []
    gsm_actual: OptQtyDecimal = None      # gramasi aktual (PS-15 — desimal koma didukung)
    width_actual: OptQtyDecimal = None    # lebar aktual (PS-15 — desimal koma didukung)
    note: str = ""
    # FASE C (D-10) — titik input LOT saat inspeksi: petugas QC melengkapi/memperbaiki
    # nomor lot supplier & dye lot/shade. Penegakan mengikuti pengaturan (warn/block).
    supplier_lot: str = ""
    dye_lot: str = ""
    shade_ref: str = ""


class PurchaseReturnItem(BaseModel):
    product_id: str
    quantity: float = Field(..., ge=0)
    unit: str = "meter"
    price: float = Field(0.0, ge=0)
    reason: str = ""                  # cacat | salah_kirim | kelebihan | lain
    condition: str = "damaged"        # damaged | ok
    roll_ids: List[str] = []          # S#2026-07-21 — retur PRESISI per roll/lot (opsional)
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)


class PurchaseReturnCreate(BaseModel):
    supplier_id: str = ""
    po_id: str = ""                   # opsional — retur bisa tanpa PO referensi
    warehouse_id: str = ""
    items: List[PurchaseReturnItem]
    reason: str = ""
    notes: str = ""
    entity_id: str = ""
    submit_now: bool = False
    created_by: str = "Admin"
    # R4 — alur RMA lintas supplier (requested→shipped→accepted/rejected→goods_back).
    #   supplier_flow=False → alur DIRECT (approve langsung konsumsi stok + Nota Debit + GL).
    supplier_flow: bool = False
    origin_sales_return_id: str = ""  # link ke retur JUAL asal (chain retur jual→beli)
    bypass_import_policy: bool = False  # override guard §J (impor & tak-returnable) — audit-only


class PurchaseReturnDecision(BaseModel):
    notes: str = ""


# ── R4 — Supplier RMA lifecycle inputs ───────────────────────────────────────
class SupplierShipInput(BaseModel):
    notes: str = ""
    carrier: str = ""
    tracking_no: str = ""


class SupplierAcceptInput(BaseModel):
    outcome: str = "ap_credit"        # refund | ap_credit
    notes: str = ""
    # R5.3 — akun Kas/Bank untuk outcome 'refund' (supplier kembalikan dana tunai). Default 1-1100.
    refund_account_code: str = ""


class SupplierRejectInput(BaseModel):
    reason: str = ""


class GoodsBackRegradeLine(BaseModel):
    roll_id: str
    grade: str = ""                   # "" = pertahankan grade saat ini


class GoodsBackInput(BaseModel):
    regrade: List[GoodsBackRegradeLine] = []
    warehouse_id: str = ""            # "" = kembali ke gudang asal retur
    notes: str = ""


class SalesToPurchaseReturnInput(BaseModel):
    """R4 — buat Retur Beli dari Retur Jual (barang cacat dari customer diteruskan ke supplier)."""
    roll_ids: List[str] = []          # roll karantina/available dari retur jual (kosong = semua kandidat)
    supplier_id: str = ""             # kosong = resolve dari PO terakhir produk
    warehouse_id: str = ""
    reason: str = ""
    notes: str = ""
    bypass_import_policy: bool = False


class POReceiveItem(BaseModel):
    """Penerimaan 1 baris PO (scan receive).

    FASE F-1 (F1-01) — **satuan supplier**: bila `doc_uom` + `doc_qty` diisi, server
    mengonversi ke satuan task (`wms_tasks.unit`) dan `actual_qty` DIABAIKAN. Bila kosong,
    perilaku lama dipakai apa adanya (backward-compatible 100%).

    `doc_qty` tidak dipagari `gt=0` (hanya `ge=0`) supaya qty **0** — salah ketik yang wajar
    di gudang — dijawab **400 dengan pesan Indonesia yang actionable**, bukan 422 detail
    Pydantic. Nilai NEGATIF tetap ditolak lapis skema (INV-NUM-01).
    """
    product_id: str
    actual_qty: float = Field(0, ge=0)
    doc_uom: str = ""                     # F1-01 — satuan pada surat jalan supplier
    doc_qty: Optional[float] = Field(None, ge=0)   # F1-01 — qty apa adanya dari surat jalan
    variance_override_reason: str = ""    # F1-06 — lanjutkan walau di luar batas (tercatat audit)
    batch: str = ""
    lot: str = ""
    dye_lot: str = ""                     # P0-4 — dye lot aktual (warna/celup) per terima
    grade: str = ""                       # P0-4 — grade aktual saat terima ("" = default A)
    roll_id: str = ""
    bin_id: str = ""


class ReceiveUomPreviewIn(BaseModel):
    """FASE F-1 (F1-05) — pratinjau konversi satuan supplier (tidak menulis apa pun).

    `doc_qty` dipagari `ge=0` (bukan `gt=0`) supaya qty **0** dijawab **400 dengan pesan
    berbahasa Indonesia yang actionable** dari service — petugas gudang tidak bisa membaca
    422 detail Pydantic. Nilai NEGATIF tetap ditolak lapis skema (INV-NUM-01).
    """
    doc_uom: str = ""
    doc_qty: float = Field(0, ge=0)


class ReceivingUomSettingsIn(BaseModel):
    """FASE F-1 (F1-08) — kebijakan input satuan supplier saat penerimaan."""
    supplier_uom_input_mode: Optional[str] = None       # off | optional | prefer
    require_supplier_item_for_supplier_uom: Optional[bool] = None
    block_over_remaining: Optional[bool] = None


class GRRollLine(BaseModel):
    """P0-4 — satu roll fisik saat Goods Receipt (panjang + dye lot + grade per roll).
    Fase 8 (catch-weight): `weight` = berat aktual roll (kg, opsional). Untuk PO yang
    dibeli per kg, isi `weight`; `length` (meter aktual) opsional → diturunkan dari faktor."""
    length: float = 0                     # panjang roll (base/meter; utk PO per-panjang)
    weight: float = Field(0, ge=0)                     # berat roll (kg) — catch-weight aktual (opsional)
    dye_lot: str = ""
    grade: str = "A"
    defects: List[str] = []


class GRCompletePayload(BaseModel):
    """P0-4 — body opsional saat selesaikan GR. Bila `rolls` diisi → multi-roll
    dengan dye_lot/grade per roll; bila kosong → satu roll pakai dye_lot/grade default.
    FASE B (D-07): `variance_override_reason` dipakai bila selisih berat/panjang hasil
    konversi vs aktual melewati batas blokir dan user berwenang tetap melanjutkan."""
    dye_lot: str = ""
    grade: str = ""
    rolls: List[GRRollLine] = []
    variance_override_reason: str = ""
    # FASE C (D-10/D-26/D-27) — titik input LOT saat penerimaan.
    # `supplier_lot` = nomor lot versi supplier; `lot_number` opsional untuk
    # menempelkan penerimaan ini ke lot yang SUDAH ada (mis. sisa kiriman batch sama).
    supplier_lot: str = ""
    lot_number: str = ""
    shade_ref: str = ""


class QCDecision(BaseModel):
    """Depth #3a + P0-4 — keputusan inspeksi QC untuk 1 inbound task (qty dalam unit task)."""
    accept_qty: float = Field(0.0, ge=0)
    reject_qty: float = Field(0.0, ge=0)
    reject_disposition: str = "damaged"   # damaged | return
    accept_grade: str = "A"               # P0-4/Fase A — grade aktual (enum A|A1|A2|B|BS, divalidasi)
    defects: List[str] = []               # P0-4 — profil cacat (mis. ["belang", "noda"])
    reason: str = ""


# ─── FASE E — Sourcing PR: realisasi ke PO / Order Makloon ───────────────────

class PRRealizePoIn(BaseModel):
    """Realisasi baris PR ber-mode `purchase` menjadi SATU Purchase Order.

    `line_nos` kosong = semua baris `purchase` yang masih terbuka (perilaku
    kompatibel dengan `convert-to-po` lama)."""
    supplier_id: str = ""             # wajib (atau pakai preferred_supplier_id PR)
    warehouse_id: str = ""            # default = warehouse PR
    line_nos: List[int] = Field(default_factory=list)
    expected_delivery_date: str = ""
    notes: str = ""


class PRRealizeMakloonIn(BaseModel):
    """Realisasi SATU baris PR ber-mode `makloon` menjadi Order Makloon.

    `payload` kosong ⇒ server memakai prefill dari Resep Proses (1 klik dari PR)."""
    line_no: int = Field(..., ge=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
