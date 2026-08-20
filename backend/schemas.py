from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core_utils import MoneyDecimal, OptMoneyDecimal, OptQtyDecimal, QtyDecimal, new_id
from schemas_crm import (  # noqa: F401 — re-export CRM schemas (KN_17)
    ContactInfo, PaymentProfile, CustomerReassign, SalesTargetCreate, IncentiveTier,
    SalesIncentiveCreate, CreditOverrideCreate, CreditOverrideDecision, CollectionFollowupCreate,
)
from schemas_finance import (  # noqa: F401 — re-export Finance schemas (EPIC7)
    BankAccountCreate, BankAccountUpdate, ReconcilePayload,
    BudgetCreate, BudgetUpdate,
)
from schemas_makloon import (  # noqa: F401 — re-export Makloon/Subcon schemas (M1/M3/Fase D)
    MakloonCreate, ProcessRecipeCreate, ForecastPreviewIn, PROCESS_TYPES,
    MakloonStepInput, MakloonOrderCreate, MakloonIssueIn, MakloonReceiveRoll,
    MakloonReceiveIn, MakloonOrderCancel, MakloonServiceIn,
    MakloonClaimIn, MakloonClaimDecisionIn, MakloonEstimateIn,
)
from schemas_purchasing import (  # noqa: F401 — re-export Purchasing/Procurement schemas
    POItemCreate, PurchaseOrderCreate, PurchaseOrderAmend,
    BlanketPOItemCreate, BlanketPOCreate, CallOffItemCreate, CallOffCreate, BlanketCloseRequest,
    SupplierCreate, SupplierPriceListCreate, CashTransactionCreate,
    ReturnPolicyInput, SUPPLIER_REFUND_MODES, ORIGIN_TYPES,
    RollDefectInput,
    POPaymentCreate, POCloseRequest,
    VendorBillItemInput, VendorBillCreate, VendorBillPaymentCreate, VendorBillDecision,
    LandedCostLineInput, LandedCostCreate, LandedCostPaymentCreate, LandedCostDecision,
    InputTaxInvoiceCreate, InputTaxInvoiceCancel,
    RFQItemInput, RFQCreate, RFQQuoteLine, RFQQuoteSubmit, RFQLineAward, RFQAward, RFQDecision,
    RollInspectionInput,
    PurchaseReturnItem, PurchaseReturnCreate, PurchaseReturnDecision,
    SupplierShipInput, SupplierAcceptInput, SupplierRejectInput,
    GoodsBackRegradeLine, GoodsBackInput, SalesToPurchaseReturnInput,
    POReceiveItem, GRRollLine, GRCompletePayload, QCDecision,
    ReceiveUomPreviewIn, ReceivingUomSettingsIn,
    PRRealizePoIn, PRRealizeMakloonIn,
)
from schemas_hr import (  # noqa: F401 — re-export HRD schemas (FASE H0)
    HrOrgUnitCreate, HrEmployeeCreate, HrSettingsUpdate, AllowanceInput,
)
from schemas_hr_attendance import (  # noqa: F401 — re-export HRD H1 (Absensi) schemas
    HrShiftCreate, HrGeofenceCreate, HrDeviceCreate,
    ClockInInput, ClockOutInput, ManualAttendanceInput,
    AttendanceImportInput, AttendanceIngestInput,
)
from schemas_hr_tracking import (  # noqa: F401 — re-export HRD H2 (Tracking/Visits) schemas
    PositionInput, VisitCheckIn, VisitCheckOut,
)
from schemas_hr_leave import (  # noqa: F401 — re-export HRD H3 (Cuti/Lembur) schemas
    LeaveRequestInput, OvertimeInput, LeaveDecisionInput, LeaveBalanceAdjust,
)
from schemas_hr_kpi import (  # noqa: F401 — re-export HRD H5 (KPI Design) schemas
    KpiInput, KpiUpdate,
)
from schemas_design_gallery import (  # noqa: F401 — re-export HRD H5 (Design Gallery) schemas
    GalleryInput, GalleryUpdate,
)
from schemas_integrations import (  # noqa: F401 — re-export H5 (Integrasi AI) schemas
    IntegrationsUpdate,
)


class SalesTeamMember(BaseModel):
    sales_id: str = ""
    name: str = ""
    role: str = "co"            # "pic" (penanggung jawab) | "co" (co-sales)
    split_pct: float = Field(0, ge=0, le=100)        # 0–100; total seluruh anggota harus = 100 bila sales_team diisi


class CustomerAddress(BaseModel):
    id: str = Field(default_factory=lambda: new_id("addr"))
    label: str = "Alamat Utama"
    recipient_name: str
    phone: str = ""
    city: str
    address: str
    is_primary: bool = False


class CustomerCreate(BaseModel):
    name: str
    pic_name: str
    phone: str
    email: str = ""
    type: str = "Retail"
    city: str
    address: str
    npwp: str = ""
    credit_limit: float = Field(0, ge=0)
    sales_pic: str = ""
    entity_id: str = ""
    enforce_single_dye_lot: bool = False  # P0-4 — paksa alokasi 1 dye lot untuk customer ini
    lot_policy: str = ""                  # "" | prefer_single | strict_single | allow_mixed
    created_by: str = "Sales Demo"
    # --- CRM-lite (KN_17) ---
    assigned_sales_id: str = ""           # FK users role=sales — WAJIB (kunci kepemilikan = PIC)
    sales_team: List[SalesTeamMember] = []  # SALES REVAMP V2 — PIC + co-sales + split insentif (PIC.sales_id == assigned_sales_id)
    segment: str = "Retail"               # Retail|Wholesale|Distributor|VIP (KLASIFIKASI saja)
    tags: List[str] = Field(default_factory=list)
    contacts: List[ContactInfo] = Field(default_factory=list)
    payment_profile: Optional[PaymentProfile] = None


class BusinessEntityCreate(BaseModel):
    """Badan usaha legal grup (Multi-Entity — F0-A · FASE E-1)."""
    legal_name: str = ""          # boleh kosong untuk Perorangan (dibentuk dari owner_name)
    short_name: str
    type: str = "PT"              # PT | CV | Perorangan | UD | Koperasi | Yayasan | Lainnya
    npwp: str = ""                # WAJIB bila default_tax_mode="ppn" (PKP) — divalidasi service
    address: str = ""
    city: str = ""
    phone: str = ""
    email: str = ""
    owner_name: str = ""          # E1.1 — wajib untuk jenis Perorangan/UD
    business_label: str = ""      # E1.1 — nama dagang usaha perorangan
    default_tax_mode: str = "ppn"  # ppn | non_ppn (driver PKP/PPN) — INDEPENDEN dari `type`
    doc_prefix: str = ""          # mis. KSC, KANDA — untuk nomor dokumen per badan usaha
    logo_url: str = ""
    currency: str = "IDR"
    parent_entity_id: str = ""    # untuk konsolidasi grup (fase lanjut)
    is_group: bool = False
    coa_template: str = "id_standard"
    fiscal_year_start: str = "01-01"
    incentive_payer: str = "sales_entity"  # Model 1
    numbering_scheme: str = "per_entity_prefix"


class EntityArchiveBody(BaseModel):
    """FASE E-1 (E1.6) — arsipkan badan usaha; `force` wajib beralasan & admin."""
    reason: str = ""
    force: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    name: str
    email: str
    role: str
    password: str = "demo12345"
    phone: str = ""                       # R6.5 — nomor WhatsApp untuk alert (08xx / 62xx)
    home_entity_id: str = ""              # F6 — badan usaha kerja/payroll (diabaikan bila employee_id terisi)
    allowed_entity_ids: List[str] = []    # F6 — badan usaha yang boleh dioperasikan (multi-entitas)
    employee_id: str = ""                 # E2.1 — tautan HR; badan usaha DIAMBIL dari data karyawan
    # FASE L — lini produk yang boleh dikerjakan akun ini. **KOSONG = SEMUA LINI**
    # (bawaan, supaya akun lama tidak kehilangan apa pun saat fase ini mendarat).
    allowed_line_codes: List[str] = []


class UserResetPasswordBody(BaseModel):
    """E2.4 — reset password oleh admin (password lama tidak pernah dibaca)."""
    new_password: str


class RoleReclassifyBody(BaseModel):
    """Terapkan peran USULAN dari layar "Cek Kenyataan Peran" (utang migrasi (ii) E-8).

    Hanya peran yang muncul sebagai usulan yang diterima — router menolak sisanya
    supaya satu salah-klik tidak mengubah wewenang ke arah yang tak pernah dihitung.
    """
    role: str
    note: str = ""


class GenericPatch(BaseModel):
    data: Dict[str, Any]


class ProductPayload(BaseModel):
    sku: str
    name: str
    category: str = "Kain"
    variant: str = "Regular"
    color: str = "Natural"
    color_code: str = ""                   # M0 — ref color_library.code (opsional; fallback ke `color`)
    color_name: str = ""                   # M0 — snapshot nama warna dari library
    color_hex: str = ""                    # M0 — snapshot hex (#RRGGBB) dari library
    motif: str = "Polos"
    grade: str = "A"                       # Fase A · PS-09/D-01 — enum: A|A1|A2|B|BS (divalidasi domain_registry)
    stage: str = "finished"                # Fase A · PS-01 — enum: yarn|grey|pfd|pfp|finished|remnant|byproduct
    fabric_type: str = ""                  # Fase A · PS-02/D-02 — WAJIB sejak stage yarn: woven|knit
    yarn_count: str = ""                   # Fase A · D-22 — nomor benang (wajib stage yarn woven), mis. "30s"
    yarn_count_system: str = ""            # Fase A · D-22 — Ne|Nm|Denier|Tex
    supplier: str = "Internal"
    base_unit: str = "meter"
    price: MoneyDecimal = Field(0, ge=0)
    harga_pokok: MoneyDecimal = Field(0, ge=0)
    gramasi: QtyDecimal = Field(0, ge=0)
    lebar: QtyDecimal = Field(0, ge=0)                 # Sub-fase 1.13 — lebar kain (meter), utk konversi kg (catch-weight)
    kg_per_meter: QtyDecimal = Field(0, ge=0)          # Fase 8 — faktor catch-weight eksplisit (kg/m); 0 = turunkan dari gramasi×lebar
    reorder_point: QtyDecimal = Field(0, ge=0)         # Depth #2b — ambang batas saran beli (0 = nonaktif)
    reorder_qty: QtyDecimal = Field(0, ge=0)           # Depth #2b — qty saran beli per replenishment (0 = pakai gap)
    image: str = "https://images.unsplash.com/photo-1774679817333-decf0d988dd5?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
    description: str = ""                  # F3 — deskripsi produk (tampil di popup detail POS)
    status: str = "active"
    uom_conversions: List[Dict[str, Any]] = []
    template_id: str = ""                 # F1b — tautan ke product_templates (opsional)
    variant_attrs: Dict[str, Any] = {}    # F1b — nilai axis varian (warna/grade/lebar)
    exclusivity: str = "umum"             # PS-20 — "umum" | "sales_tertentu"
    owner_sales_ids: List[str] = []       # PS-20 — user id sales pemilik (bila eksklusif)
    # FASE L — PEMBAGIAN KERJA MD (woven/knit/printing, bisa ditambah pemilik).
    # BUKAN pengganti `fabric_type` (fisika kain, SSOT rumus & satuan kendali):
    # INV-LINE-02 menolak kombinasi yang bertentangan. Kosong = belum bergolong
    # lini (data lama) dan TETAP terlihat semua akun.
    line_code: str = ""


class ProductTemplateCreate(BaseModel):
    """F1b — Template katalog (induk) + konfigurasi axis varian."""
    name: str
    category: str = "Kain"
    fabric_type: str = ""                 # Fase A · PS-02/D-02 — WAJIB (woven|knit), diwarisi varian
    motif: str = "Polos"
    stage: str = "finished"               # Fase A · PS-01 — enum stage (yarn|grey|pfd|pfp|finished|remnant|byproduct)
    yarn_count: str = ""                  # Fase A · D-22 — wajib bila stage yarn
    yarn_count_system: str = ""           # Fase A · D-22 — Ne|Nm|Denier|Tex
    description: str = ""
    image: str = ""
    base_unit: str = "meter"
    base_price: MoneyDecimal = Field(0.0, ge=0)
    harga_pokok: MoneyDecimal = Field(0.0, ge=0)
    gramasi: QtyDecimal = Field(0.0, ge=0)
    lebar: QtyDecimal = Field(0.0, ge=0)
    supplier: str = "Internal"
    sku_prefix: str = ""
    axes: List[Dict[str, Any]] = []       # [{key,label,options:[{code,label,value}]}]


class ProductTemplatePatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    fabric_type: Optional[str] = None
    motif: Optional[str] = None
    stage: Optional[str] = None           # Fase A — enum stage
    yarn_count: Optional[str] = None      # Fase A · D-22
    yarn_count_system: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    base_unit: Optional[str] = None
    base_price: OptMoneyDecimal = Field(None, ge=0)
    harga_pokok: OptMoneyDecimal = Field(None, ge=0)
    gramasi: OptQtyDecimal = Field(None, ge=0)
    lebar: OptQtyDecimal = Field(None, ge=0)
    supplier: Optional[str] = None
    sku_prefix: Optional[str] = None
    status: Optional[str] = None
    axes: Optional[List[Dict[str, Any]]] = None


class VariantGenerateIn(BaseModel):
    """F1b — generate varian massal (cartesian dari axis)."""
    axes: Optional[List[Dict[str, Any]]] = None   # override axis template (opsional)
    base_price: Optional[float] = Field(None, ge=0)
    sku_prefix: Optional[str] = None


class AssignProductsIn(BaseModel):
    product_ids: List[str] = []


class StockHoldIn(BaseModel):
    """F2 — tahan stok (soft hold / Pending SO): available → hold.
    F2b — `hold_type` membedakan tujuan hold: general | delivery (permintaan
    customer/kredit) | reservation. Surface di papan Hold Aktif."""
    product_id: str
    warehouse_id: str
    owner_entity_id: str
    quantity: float = Field(..., ge=0)
    reason: str = ""
    hold_type: str = "general"        # general | delivery | reservation (F2b)
    ref_type: str = ""                # mis. 'sales_order' (Pending SO)
    ref_id: str = ""                  # id SO/dokumen terkait (opsional)
    expires_at: str = ""              # iso/tanggal (opsional)


class StockWipIn(BaseModel):
    """F2 — mulai proses (WIP): available → wip."""
    product_id: str
    warehouse_id: str
    owner_entity_id: str
    quantity: float = Field(..., ge=0)
    note: str = ""


class WarehousePayload(BaseModel):
    code: str
    name: str
    city: str
    bin_code: str = "A1-01"
    bin_capacity: float = Field(1000, ge=0)
    lat: Optional[float] = None
    lng: Optional[float] = None
    # FASE E-4 (E4.1) — mode pemakaian gudang. Bawaan KOSONG artinya "khusus badan
    # usaha aktif" (diisi router): gudang baru harus sengaja dibuka bila mau bersama.
    sharing_mode: Optional[str] = None            # "shared" | "dedicated"
    entity_ids: List[str] = []


class UOMPayload(BaseModel):
    code: str
    name: str
    base_type: str = "length"
    precision: int = Field(2, ge=0)
    factor_to_base: float = Field(1.0, gt=0)   # S#074 VAL-UOM: faktor konversi harus > 0
    # FASE U (D1) — kata satuan yang BENAR-BENAR tersimpan di dokumen (`yard`, `kg`,
    # `meter`, `roll`). Tanpa ini baris master tak pernah cocok dengan isi dokumen,
    # sehingga menambah satuan di master tidak mengubah apa pun di layar.
    aliases: List[str] = Field(default_factory=list)
    # Hanya untuk satuan yang faktornya memang berbeda PER DOKUMEN (keputusan pemilik
    # 2026-08-19: panjang 1 PANEL berbeda per pesanan). Baris dokumen hanya boleh
    # membawa faktor sendiri bila masternya menyatakan begini.
    factor_per_document: bool = False


class TemplatePayload(BaseModel):
    document_type: str
    name: str
    header: str = "Kain Nusantara"
    footer: str = "Dokumen dibuat otomatis oleh sistem."
    columns: List[str] = []
    logo_url: str = ""
    paper_size: str = "A4"
    orientation: str = "portrait"
    margin_mm: int = 12
    signature_left: str = "Dibuat Oleh"
    signature_right: str = "Disetujui Oleh"
    section_order: List[str] = ["header", "customer", "items", "allocation", "signature", "footer"]


class PermissionUpdate(BaseModel):
    matrix: Dict[str, Dict[str, List[str]]]


class WMSTaskCreate(BaseModel):
    flow_type: str = "inbound"
    source_type: str = "supplier"
    product_id: str
    quantity: float = Field(..., ge=0)
    unit: str = "meter"
    warehouse_id: str
    bin_id: str
    batch: str
    lot: str
    roll_id: str
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)


class ScannerScan(BaseModel):
    scan_type: str
    scan_value: str
    actor: str = "Warehouse Demo"


class RollLineIn(BaseModel):
    """SALES REVAMP V2 — pilihan roll spesifik untuk 1 baris order.
    take_qty = panjang yang diambil (== length_remaining untuk roll utuh; < untuk cut roll)."""
    roll_id: str
    take_qty: float = Field(0, ge=0)                  # 0 → diisi backend = length_remaining (roll utuh)


class ReconcileItemIn(BaseModel):
    product_id: str
    quantity: float = Field(0, ge=0)
    base_quantity: float = Field(0, ge=0)
    unit: str = ""


class RollReconcilePreviewIn(BaseModel):
    """SALES REVAMP V2 (C2) — minta opsi genapkan roll untuk daftar baris per-yard."""
    items: List[ReconcileItemIn]
    entity_id: str = ""
    all_entities: bool = False


class SalesOrderItemIn(BaseModel):
    product_id: str
    quantity: float = Field(..., ge=0)
    unit: str
    base_quantity: float = Field(0, ge=0)             # Sub-fase 1.8/1.13 — qty dlm base unit (forward-compat)
    discount_percent: float = Field(0, ge=0, le=100)          # Fase 1B — diskon per item (0–100%)
    price_approval_id: str = ""          # Sub-fase 1.7 — harga khusus disetujui (override harga)
    # SALES REVAMP V2 — Beli per Roll / rekonsiliasi roll
    purchase_mode: str = "qty"           # "qty" (per yard, FEFO auto) | "roll" (pilih roll eksplisit)
    roll_lines: List[RollLineIn] = []    # bila purchase_mode=="roll": daftar roll dipilih (whole/cut)
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


class SalesOrderCreate(BaseModel):
    customer_id: str
    shipping_address_id: str
    items: List[SalesOrderItemIn]
    sales_name: str = "Ayu Marketing"
    shipment_policy: str = "allow_partial_shipment"
    entity_id: str = ""
    order_discount_percent: float = Field(0, ge=0, le=100)     # Fase 1B — diskon level order (0–100%)
    payment_term_code: str = ""           # Fase 1B — term pembayaran (kode)
    allow_backorder: bool = False         # Sub-fase 1.6 — izinkan reservasi parsial + backorder
    confirm_mixed_lot: bool = False       # Sub-fase 1.7/MixedLot — konfirmasi pemenuhan lintas-lot
    source_special_order_id: str = ""     # EPIC6 — link eksplisit asal Special Order (opsional)
    sales_team: List[SalesTeamMember] = []  # F-4c — join/group sales (PIC + co-sales, split insentif custom)
    needs_tax_invoice: bool = False        # F6 — minta Faktur Pajak untuk order ini
    tax_override: str = ""                 # F6 — paksa mode pajak: "" (ikut entitas) | "non_ppn"
    fulfillment_method: str = "kirim"      # "kirim" (dikirim) | "ambil" (Order Pengambilan di gudang)
    pickup_date: str = ""                  # ISO date; wajib bila fulfillment_method=="ambil" (hold picking s/d tgl ini)
    delivery_date: str = ""                # ISO date OPSIONAL; request tgl pengiriman bila fulfillment_method=="kirim" (tak boleh di masa lalu)


class AllocationPreviewItem(BaseModel):
    product_id: str
    quantity: float = Field(..., ge=0)
    unit: str = "meter"


class AllocationPreviewIn(BaseModel):
    """Preview pemenuhan/ATP per baris SEBELUM order dibuat (Sub-fase 1.4, READ-ONLY)."""
    items: List[AllocationPreviewItem]
    entity_id: str = ""          # entitas penjual; kosong → default/owner customer
    customer_id: str = ""        # opsional (konteks kota; tidak mengubah ATP)


class InterCompanyTransferItem(BaseModel):
    product_id: str
    quantity: float = Field(..., ge=0)
    unit: str = "meter"
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)


class InterCompanyTransferCreate(BaseModel):
    """Sub-fase 1.5 — minta transfer kepemilikan antar-entitas (B→E) dari preview POS.
    EXTEND warehouse_transfers (transfer_kind=inter_entity)."""
    source_entity_id: str                       # B (pemilik stok)
    dest_entity_id: str                         # E (entitas penjual yang butuh)
    items: List[InterCompanyTransferItem]
    linked_order_id: Optional[str] = None       # SO pemicu (opsional)
    transfer_price: Optional[float] = Field(None, ge=0)      # Fase 4 (nullable; tidak ada dampak akuntansi sekarang)
    # FASE G-6 — bila transfer ini adalah perpindahan FISIK dari sebuah transaksi
    # antar-PT (jual-beli internal), sebutkan pair-nya. Konsekuensi: jurnal at-cost
    # M-3 TIDAK diposting lagi (G-6 sudah memposting harga jual) dan nilai roll di
    # PT pembeli dinilai ulang ke harga beli internal. Tanpa penanda ini satu barang
    # akan tercatat DUA KALI di IC-AR/IC-AP dan persediaan.
    interco_pair_id: Optional[str] = None
    notes: str = ""
    requested_by: str = ""


class PaymentSimulationCreate(BaseModel):
    amount: float = Field(0, ge=0)                    # Fase 1B — opsional; default = grand_total order
    method: str = "Transfer Simulasi"
    created_by: str = "Admin Demo"


class DocumentGenerate(BaseModel):
    document_type: str
    source_id: str
    actor: str = "Admin Demo"


class BarcodeGenerate(BaseModel):
    target_type: str
    target_id: str
    label_size: str = "80x50mm"


WAREHOUSE_PRIORITY = {
    "Jakarta": ["Jakarta", "Bandung", "Surabaya"],
    "Bandung": ["Bandung", "Jakarta", "Surabaya"],
    "Surabaya": ["Surabaya", "Bandung", "Jakarta"],
    "Denpasar": ["Surabaya", "Jakarta", "Bandung"],
}


# ─── Transfer Schemas ────────────────────────────────────────────────────────

class TransferItem(BaseModel):
    product_id: str
    qty: QtyDecimal = Field(..., ge=0)            # PS-15/R5 — desimal koma didukung
    unit: str = "meter"
    batch: str = ""
    lot: str = ""
    roll_id: str = ""
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)


class TransferCreate(BaseModel):
    source_warehouse_id: str
    dest_warehouse_id: str
    items: List[TransferItem]
    notes: str = ""
    requested_by: str = "Warehouse User"
    owner_entity_id: str = ""  # opsional: entitas pemilik stok yang dipindah (auto-resolve bila kosong)


class TransferApprove(BaseModel):
    approved_by: str = "Manager"


class TransferReject(BaseModel):
    rejected_by: str = "Manager"
    reason: str = ""


class TransferStatusUpdate(BaseModel):
    status: str  # picking, staging, dispatched, completed
    updated_by: str = "Warehouse User"


# ─── Purchasing / Procurement Schemas — DIPINDAH ke schemas_purchasing.py (re-export di header) ─


class RollGradeOverrideIn(BaseModel):
    """Fase A · PS-09/D-23 — koreksi grade roll TANPA inspeksi.

    Hanya manager/admin; `reason` WAJIB dan tercatat di `grade_history` + audit log.
    """
    grade: str
    reason: str


# ─── Inventory Roll Schema (Fase 0.5 — Roll-as-SSOT, KN_15) ──────────────────

class RollPayload(BaseModel):
    product_id: str
    warehouse_id: str
    owner_entity_id: str = ""        # default = entitas utama bila kosong
    lot: str
    quantity: float = Field(..., ge=0)                  # = length_initial = length_remaining awal
    unit: str = "meter"
    grade: str = "A"
    batch: str = ""
    roll_no: str = ""
    bin_id: str = ""
    tracking_mode: str = "barcode"   # rfid | barcode | document | manual
    ownership_type: str = "internal" # internal | supplier_consignment | reseller_consignment


# ─── Configuration Foundation Schemas (Fase 1A — semua configurable) ─────────

class SettingsUpdate(BaseModel):
    scope: str = "global"            # "global" | entity_id
    tax: Optional[Dict[str, Any]] = None
    finance: Optional[Dict[str, Any]] = None
    sales: Optional[Dict[str, Any]] = None
    inventory: Optional[Dict[str, Any]] = None
    allocation: Optional[Dict[str, Any]] = None   # Sub-fase 1.7 — allocation policy
    purchasing: Optional[Dict[str, Any]] = None   # Depth #3 — procurement (deviasi harga, dll)
    commission: Optional[Dict[str, Any]] = None   # EPIC4 — strategi & mekanik insentif


class PaymentTermPayload(BaseModel):
    code: str
    name: str
    type: str = "credit"             # cash | credit | dp | installment
    net_days: int = Field(0, ge=0)
    dp_percent: float = Field(0, ge=0, le=100)
    installment_count: int = Field(0, ge=0)
    sort: int = 99
    active: bool = True


class ApprovalRulePayload(BaseModel):
    doc_type: str                    # sales_order | purchase_order | transfer | discount
    entity_id: str = "all"
    min_amount: float = 0
    max_amount: Optional[float] = None
    required_role: str = ""          # "" = tidak butuh approval
    is_percent: bool = False
    sort: int = 99
    active: bool = True



# ─── Price Approval Schemas (Sub-fase 1.7 — Special Price / Approval Harga) ───

class PriceApprovalCreate(BaseModel):
    customer_id: str
    product_id: str
    requested_price: float = Field(..., ge=0)               # harga khusus yang diajukan (per unit)
    min_quantity: float = Field(0, ge=0)              # qty minimum agar harga berlaku
    valid_until: str = ""                # "YYYY-MM-DD" atau ISO; "" = tanpa kadaluarsa
    reason: str = ""
    entity_id: str = ""                  # kosong → resolve dari entitas customer
    submit_now: bool = False             # True → langsung status pending (skip draft)
    scope: str = "standing"              # "standing" (aturan customer+produk, pakai valid_until) | "order" (khusus 1 order)
    so_id: str = ""                      # bila scope=="order": SO terkait (order-scoped, tak bocor ke /effective)
    override: bool = False               # True → override/replace harga khusus aktif yg sudah ada (supersede saat approved)


class PriceApprovalDecision(BaseModel):
    decision_notes: str = ""


# ─── F5 — Unified Approval pada SO (special price + over-credit + nilai) ──────

class SoSpecialPriceRequest(BaseModel):
    """Ajukan harga khusus pada item SO yang SUDAH dibuat (aksi di detail SO)."""
    item_index: Optional[int] = None      # indeks item pada SO.items (prioritas)
    product_id: str = ""                   # alternatif: cari item by product_id
    requested_price: float = Field(..., ge=0)                 # harga khusus per unit (jual)
    reason: str = ""                       # WAJIB alasan (divalidasi di router)
    min_quantity: float = Field(0, ge=0)
    apply_provisional: bool = True         # True → harga diminta langsung dipakai di baris SO (provisional) selagi menunggu approval
    scope: str = "order"                   # "order" (khusus SO ini) | "standing" (jadi aturan tetap juga)
    valid_until: str = ""                  # bila scope=="standing": masa berlaku aturan


class SoCreditApprovalRequest(BaseModel):
    """Minta approval kredit untuk SO over-limit (SO tetap tersimpan, tak diblokir)."""
    reason: str = ""                       # WAJIB alasan


class SoApprovalDecision(BaseModel):
    """Keputusan approver (admin/manager) atas 1 entri pending_approval di SO."""
    decision: str                          # approve | reject
    notes: str = ""


# ─── Tax Invoice / Faktur Pajak Schemas (Sub-fase 1.9 — Faktur Pajak Jual) ───

class TaxInvoiceCreate(BaseModel):
    kode_transaksi: Optional[str] = None   # None → default service: 04 (DPP Nilai Lain) / 01
    faktur_date: Optional[str] = None      # ISO; default = sekarang
    nsfp: Optional[str] = None             # NSFP resmi 16-digit (opsional, diisi menyusul)


class TaxInvoiceNsfpUpdate(BaseModel):
    nsfp: str
    kode_transaksi: Optional[str] = None


class TaxInvoiceReplace(BaseModel):
    reason: Optional[str] = ""
    kode_transaksi: Optional[str] = None
    nsfp: Optional[str] = None


class TaxInvoiceCancel(BaseModel):
    reason: str


# ─── Sales Returns / Retur & Barang Sisa (Sub-fase 1.11) ─────────────────────

class SalesReturnItem(BaseModel):
    product_id:         str
    product_name:       str = ""
    quantity_returned: float = Field(..., ge=0)
    unit:               str = "meter"
    reason:             str = ""
    condition:          str = "ok"   # ok | damaged
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)


class SalesReturnCreate(BaseModel):
    order_id:     str
    return_type:  str = "retur"      # retur | bs | penggantian | komplain | garansi (F3 RMA)
    items:        list[SalesReturnItem]
    notes:        str = ""
    entity_id:    str = ""
    submit_now:   bool = False       # True = langsung pending_approval


class SalesReturnDecision(BaseModel):
    notes: str = ""


# ─── R1 — Inspeksi & Settle (state machine + 4 outcome + partial) ────────────

class ReturnInspectionInput(BaseModel):
    index: int = -1                     # indeks item pada dokumen (-1 = pakai product_id)
    product_id: str = ""
    grade: str = ""                     # override manual (kosong = pakai grade 4-point)
    condition: str = "ok"               # ok|minor|damaged
    disposition: str = ""               # restock|regrade|scrap|return_supplier (R3)
    recommended_outcome: str = ""       # override; kosong = turunan dari grade
    accepted_qty: float = Field(0, ge=0)
    defects: List[RollDefectInput] = [] # R2 — 4-point (point_value 1..4, count)
    gsm_actual: Optional[float] = None
    width_actual: Optional[float] = None
    note: str = ""


class ReturnInspectComplete(BaseModel):
    inspections: List[ReturnInspectionInput] = []
    notes: str = ""


class QuarantineRollDecision(BaseModel):
    roll_id: str
    action: str = "release"             # release (→available) | scrap (→damaged)
    grade: str = ""                     # grade akhir saat release (kosong = pakai grade roll)


class QuarantineReleaseInput(BaseModel):
    decisions: List[QuarantineRollDecision] = []
    notes: str = ""


class ReturnItemDecision(BaseModel):
    index: int = -1
    product_id: str = ""
    outcome: str = ""                   # "" = ikut outcome header | "reject" = kecualikan item
    settle_qty: float = Field(-1, ge=-1)  # -1 = seluruh quantity_returned


class SalesReturnSettle(BaseModel):
    outcome: str                        # refund | store_credit | nego
    item_decisions: List[ReturnItemDecision] = []
    notes: str = ""
    # R3 — LOKASI fisik gudang penerimaan retur (owner tetap = entity SO agar GL rekonsiliasi;
    #   perubahan kepemilikan lintas-entitas dilakukan via transfer inter-entity yang GL-balanced).
    #   Kosong = default cerdas (gudang outbound SO). Hanya relevan utk refund/store_credit.
    return_warehouse_id: str = ""
    # R5.3 — akun Kas/Bank untuk refund TUNAI (GL Cr akun ini + cash_transaction keluar).
    #   Kosong = default 1-1100 Kas Besar/Bank. Hanya relevan bila settlement = cash.
    refund_account_code: str = ""


class RollOwnershipTransferInput(BaseModel):
    """R3 — pindah kepemilikan roll retur ke entitas lain (inter-entity, GL-safe).
    Reuse engine transfer antar-PT (Dr IC-AR/Cr Persediaan @src; Dr Persediaan/Cr IC-AP @dst)."""
    dest_entity_id: str
    notes: str = ""


# ─── R0 — Sales Return Policy Engine (berdiri sendiri; scope global/kategori/customer) ─

# Jenis retur jual yang dikenal (RMA) & outcome (dipakai penuh di R1+).
SALES_RETURN_TYPES = ("retur", "bs", "penggantian", "komplain", "garansi")
SALES_RETURN_OUTCOMES = ("refund", "store_credit", "nego", "reject")


class SalesReturnPolicyCreate(BaseModel):
    """Kebijakan retur jual (R0). Berlaku menurut `scope`:
    - global: semua transaksi
    - category: `scope_ref` = nama kategori produk
    - customer: `scope_ref` = customer_id
    `custom_fields` extensible (keputusan owner #6). Resolusi: customer > category > global."""
    name: str
    scope: str = "global"                                   # global | category | customer
    scope_ref: str = ""                                     # nama kategori / customer_id (kosong utk global)
    window_days: int = Field(30, ge=0, le=3650)             # jendela retur (hari sejak barang dikirim)
    allowed_return_types: List[str] = list(SALES_RETURN_TYPES)
    allowed_outcomes: List[str] = list(SALES_RETURN_OUTCOMES)
    restocking_fee_pct: float = Field(0.0, ge=0, le=100)
    require_inspection: bool = True                         # keputusan owner #3 — inspect WAJIB
    enforce_window: bool = False                            # True = blok di luar window; False = hanya peringatan
    link_to_supplier_window: bool = False                  # turunkan deadline dari window supplier (linked, R0 §I)
    condition_requirements: str = ""
    custom_fields: Dict[str, Any] = {}                     # extensible — aturan tambahan buatan user
    valid_from: str = ""
    valid_until: str = ""
    entity_id: str = ""
    notes: str = ""
    created_by: str = "Admin"


# ─── Depth #2: Purchase Requisition (PR) + Reorder ───────────────────────────

class PurchaseRequisitionItem(BaseModel):
    product_id: str = ""              # opsional — kosong = item non-katalog (special order)
    description: str = ""            # wajib bila product_id kosong
    quantity: QtyDecimal = Field(..., ge=0)       # PS-15/R5 — terima "10,5" & "10.5"
    unit: str = "meter"
    est_price: MoneyDecimal = Field(0.0, ge=0)    # estimasi harga satuan (untuk evaluasi approval)
    note: str = ""
    # FASE E — routing pemenuhan per BARIS: dibeli jadi vs diproses via makloon.
    fulfillment_mode: str = "purchase"            # purchase | makloon
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


class PurchaseRequisitionCreate(BaseModel):
    items: List[PurchaseRequisitionItem]
    warehouse_id: str = ""
    entity_id: str = ""
    reason: str = ""                  # justifikasi kebutuhan
    needed_by_date: str = ""          # ISO/tanggal dibutuhkan
    source: str = "manual"            # manual | reorder | special_order
    source_ref_id: str = ""           # id special_order bila source=special_order
    preferred_supplier_id: str = ""
    notes: str = ""
    submit_now: bool = False          # True = langsung pending_approval (atau approved bila tak butuh approval)
    created_by: str = "Admin"


class PurchaseRequisitionDecision(BaseModel):
    notes: str = ""


# ─── PS-21 — Repeat/Restock 1-klik dari Sales Order ──────────────────────────

class RepeatRestockItem(BaseModel):
    product_id: str
    quantity: QtyDecimal = Field(..., gt=0)       # PS-15/R5 — terima "10,5"
    unit: str = ""
    est_price: MoneyDecimal = Field(0.0, ge=0)
    note: str = ""


class RepeatRestockIn(BaseModel):
    items: List[RepeatRestockItem]
    reason: str = ""
    notes: str = ""
    warehouse_id: str = ""
    needed_by_date: str = ""
    submit_now: bool = True       # True = PR langsung diajukan (pending_approval/approved)


class PurchaseRequisitionConvert(BaseModel):
    supplier_id: str = ""             # wajib (atau pakai preferred_supplier_id PR)
    warehouse_id: str = ""            # default = warehouse PR
    expected_delivery_date: str = ""
    notes: str = ""


class SpecialOrderToPR(BaseModel):
    """Jembatan Special Order → PR pengadaan (Depth #2c)."""
    est_price: float = Field(0.0, ge=0)            # estimasi biaya pengadaan per unit (default target_price)
    warehouse_id: str = ""
    needed_by_date: str = ""
    notes: str = ""
    submit_now: bool = False


class EntityPriceCreate(BaseModel):
    """F1a — Harga jual per-entitas (per base unit) dengan tanggal efektif."""
    product_id: str
    sell_price: float = Field(..., ge=0)
    entity_id: str = ""               # kosong = entitas aktif
    valid_from: str = ""              # 'YYYY-MM-DD'/iso; kosong = sekarang
    valid_until: str = ""             # kosong = tanpa kadaluarsa
    is_listed: bool = True
    note: str = ""


class EntityPricePatch(BaseModel):
    sell_price: Optional[float] = Field(None, ge=0)
    valid_until: Optional[str] = None
    is_listed: Optional[bool] = None
    note: Optional[str] = None


class EntityPriceImportRow(BaseModel):
    """Satu baris impor harga per badan usaha (E4.7)."""
    sku: str
    sell_price: float = Field(..., gt=0)
    valid_from: str = ""
    valid_until: str = ""
    note: str = "impor CSV"


class EntityPriceImportIn(BaseModel):
    """Impor massal: kirim `rows` (sudah terurai) ATAU `csv_text` mentah."""
    entity_id: str = ""
    rows: List[EntityPriceImportRow] = Field(default_factory=list)
    csv_text: str = ""


# ─── M0 — Color Library (master warna Pantone-style) ─────────────────────────

class ColorCreate(BaseModel):
    code: str
    name: str
    hex: str                              # '#RRGGBB' atau 'RRGGBB'
    system: str = "KN"                    # TPX | TCX | C | U | KN
    family: str = ""                      # kelompok warna (Merah/Biru/...)


class ColorPatch(BaseModel):
    name: Optional[str] = None
    hex: Optional[str] = None
    system: Optional[str] = None
    family: Optional[str] = None
    status: Optional[str] = None
