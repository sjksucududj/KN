"""FASE E-7 (E7f) — skema **Pinjaman Uang Antar-PT** (`interco_loans`)."""
from typing import Optional

from pydantic import BaseModel, Field

from core_utils import MoneyDecimal


class IntercoLoanCreate(BaseModel):
    lender_entity_id: str                     # PT pemberi (piutang antar-PT)
    borrower_entity_id: str                   # PT penerima (utang antar-PT)
    principal: MoneyDecimal = Field(..., gt=0)
    purpose: str = ""                         # WAJIB ≥5 huruf (dijaga service)
    interest_note: str = ""                   # kesepakatan bunga/biaya — TIDAK diakru sistem
    agreed_return_date: str = ""
    doc_date: str = ""
    notes: str = ""


class IntercoLoanRepay(BaseModel):
    amount: MoneyDecimal = Field(..., gt=0)
    note: str = ""


class IntercoLoanDecision(BaseModel):
    reason: str = ""


class FixedAssetTransferIn(BaseModel):
    """FASE E-7 (E7g) — pindah aset tetap antar-PT."""
    to_entity_id: str
    transfer_price: Optional[MoneyDecimal] = Field(None, ge=0)  # kosong = nilai buku
    transfer_date: str = ""
    reason: str = ""                          # WAJIB ≥5 huruf (dijaga service)
    notes: str = ""


class FixedAssetTransferSettleIn(BaseModel):
    note: str = ""
