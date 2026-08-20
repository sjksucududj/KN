"""F1b — Skema **Daftar Harga per Pelanggan** (dipisah dari `schemas.py` agar tidak
membengkak; aturan repo: skema baru ke modul sendiri)."""
from typing import List, Optional

from pydantic import BaseModel, Field


class CustomerPriceCreate(BaseModel):
    """Harga langganan satu pelanggan atas satu produk (per base unit)."""
    customer_id: str
    product_id: str
    sell_price: float = Field(..., ge=0)
    entity_id: str = ""          # kosong = entitas aktif
    valid_from: str = ""         # 'YYYY-MM-DD' / iso; kosong = mulai sekarang
    valid_until: str = ""        # kosong = tanpa kadaluarsa
    is_listed: bool = True
    note: str = ""


class CustomerPricePatch(BaseModel):
    sell_price: Optional[float] = Field(None, ge=0)
    valid_until: Optional[str] = None
    is_listed: Optional[bool] = None
    note: Optional[str] = None


class CustomerPriceImportRow(BaseModel):
    sku: str
    sell_price: float = Field(..., ge=0)
    valid_from: str = ""
    valid_until: str = ""
    note: str = "impor CSV"


class CustomerPriceImportIn(BaseModel):
    """Impor massal: kirim `rows` (sudah terurai) ATAU `csv_text` mentah."""
    customer_id: str
    entity_id: str = ""
    rows: List[CustomerPriceImportRow] = Field(default_factory=list)
    csv_text: str = ""
