"""FASE E — Skema `supplier_items` (Barang Supplier / katalog versi supplier).

Rujukan: KN_18 §5.4 (nama koleksi final `supplier_items`, prefix `sit_`),
PS-06 (kontrak harga sebagai acuan PO), keputusan pemilik sesi 2026-07-26:
  * **E-01** — impor massal WAJIB didukung (CSV/XLSX), bukan hanya CRUD manual.
  * **E-02** — kunci logis unik **(supplier_id, supplier_sku)** → impor idempotent (upsert).
  * **E-03** — konversi satuan supplier → satuan dasar produk KN disimpan eksplisit
    (`supplier_uom` + `conv_factor`) agar qty PO tidak pernah ditebak.

Semua qty/uang memakai tipe desimal PS-15 (menerima "10,5" maupun "10.5").
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from core_utils import MoneyDecimal, QtyDecimal


class SupplierItemCreate(BaseModel):
    supplier_id: str
    product_id: str = ""              # boleh kosong bila `sku` diisi (di-resolve service)
    sku: str = ""                     # SKU KN — alternatif pengisian product_id
    supplier_sku: str                 # kode barang versi supplier (WAJIB · kunci logis)
    supplier_item_name: str = ""      # nama barang versi supplier
    supplier_uom: str = ""            # satuan supplier ("" = sama dengan base_unit produk)
    conv_factor: QtyDecimal = Field(1, gt=0)   # 1 supplier_uom = conv_factor × base_unit
    last_price: MoneyDecimal = Field(0, ge=0)  # harga terakhir per supplier_uom
    currency: str = "IDR"
    moq: QtyDecimal = Field(0, ge=0)
    lead_time_days: int = Field(0, ge=0)
    expected_grade: str = ""          # grade yang dijanjikan supplier (PS-09/D-19)
    barcode: str = ""
    notes: str = ""
    status: str = "active"            # active | inactive
    entity_id: str = ""


class SupplierItemPatch(BaseModel):
    product_id: Optional[str] = None
    sku: Optional[str] = None
    supplier_sku: Optional[str] = None
    supplier_item_name: Optional[str] = None
    supplier_uom: Optional[str] = None
    conv_factor: Optional[QtyDecimal] = None
    last_price: Optional[MoneyDecimal] = None
    currency: Optional[str] = None
    moq: Optional[QtyDecimal] = None
    lead_time_days: Optional[int] = None
    expected_grade: Optional[str] = None
    barcode: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class SupplierItemImportRow(BaseModel):
    """Satu baris impor (dipakai bila klien mengirim JSON, bukan file)."""
    supplier_sku: str = ""
    supplier_item_name: str = ""
    sku: str = ""
    product_id: str = ""
    supplier_uom: str = ""
    conv_factor: str = ""
    last_price: str = ""
    currency: str = ""
    moq: str = ""
    lead_time_days: str = ""
    expected_grade: str = ""
    barcode: str = ""
    notes: str = ""


class SupplierItemImportIn(BaseModel):
    """Impor massal via JSON (alternatif upload file multipart)."""
    supplier_id: str
    entity_id: str = ""
    rows: List[SupplierItemImportRow] = Field(default_factory=list)
    csv_text: str = ""                # alternatif: tempel isi CSV langsung
    dry_run: bool = True              # True = pratinjau (tidak menulis)
