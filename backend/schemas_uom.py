"""FASE B — Skema konversi satuan (D-06/D-07).

Semua qty/faktor memakai tipe desimal PS-15 (`"0,9144"` diterima).
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from core_utils import MoneyDecimal, QtyDecimal


class UomRuleIn(BaseModel):
    """Aturan konversi GLOBAL (berlaku untuk semua produk)."""
    from_unit: str
    to_unit: str
    kind: str = "fixed"                 # fixed | pack | formula
    factor: MoneyDecimal = Field(0.0, ge=0)    # wajib > 0 untuk fixed/pack
    formula: str = ""                   # gsm_width (kind=formula)
    dimension: str = ""                 # length | weight | count | area | cross
    label: str = ""
    note: str = ""
    status: str = "active"


class UomRulePatch(BaseModel):
    from_unit: Optional[str] = None
    to_unit: Optional[str] = None
    kind: Optional[str] = None
    factor: Optional[MoneyDecimal] = None
    formula: Optional[str] = None
    dimension: Optional[str] = None
    label: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None


class UomSettingsIn(BaseModel):
    """Kebijakan toleransi selisih konversi (keputusan pemilik: configurable)."""
    warn_pct: Optional[QtyDecimal] = None
    block_pct: Optional[QtyDecimal] = None
    allow_override: Optional[bool] = None
    require_trail: Optional[bool] = None
    precision: Optional[int] = Field(None, ge=0, le=6)


class UomConvertIn(BaseModel):
    product_id: str = ""
    qty: QtyDecimal = Field(..., ge=0)
    from_unit: str
    to_unit: str = ""                   # kosong = base unit produk
    gramasi: Optional[QtyDecimal] = None   # pratinjau produk baru (belum tersimpan)
    lebar: Optional[QtyDecimal] = None
    base_unit: str = ""


class UomVarianceIn(BaseModel):
    expected: QtyDecimal = Field(..., ge=0)
    actual: QtyDecimal = Field(..., ge=0)
    label: str = "hasil konversi"


class UomBulkPreviewIn(BaseModel):
    product_id: str
    from_unit: str
    quantities: List[QtyDecimal] = []
