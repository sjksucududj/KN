"""FASE G-7 — Skema `contra_bons` (kontrabon / siklus tukar faktur supplier).

Semua nominal memakai tipe desimal PS-15 (`MoneyDecimal` menerima "1.000,50" maupun
"1000.5") supaya angka dari layar Indonesia tidak pernah tertukar.
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from core_utils import MoneyDecimal


class ContraBonBillPick(BaseModel):
    """Satu tagihan supplier yang ditarik ke kontrabon."""
    bill_id: str
    applied_amount: Optional[MoneyDecimal] = Field(None, ge=0)   # None = seluruh sisa hutang


class ContraBonCreate(BaseModel):
    supplier_id: str
    entity_id: str = ""
    bills: List[ContraBonBillPick] = Field(default_factory=list)
    cycle_date: str = ""          # tanggal tukar faktur (default: hari ini)
    due_date: str = ""            # jatuh tempo bayar (default: dari termin supplier)
    supplier_pic: str = ""        # yang menyerahkan faktur dari pihak supplier
    notes: str = ""
    submit_now: bool = False


class ContraBonDeductionIn(BaseModel):
    kind: str                     # purchase_return|supplier_advance|supplier_penalty|match_variance|other_agreed
    ref_id: str = ""              # dokumen sumber (retur beli / transaksi uang muka)
    bill_id: str = ""             # wajib untuk match_variance
    exception_key: str = ""       # pengecualian 3-way yang ditutup oleh potongan ini
    amount: Optional[MoneyDecimal] = Field(None, ge=0)   # None = seluruh nilai dokumen sumber
    reason_code: str = ""
    note: str = ""


class ContraBonDecisionIn(BaseModel):
    """Keputusan BERLABEL atas satu pengecualian 3-way match (G-1: tak ada edit senyap)."""
    exception_key: str
    action: str                   # accept | deduct | dispute
    reason_code: str
    amount: Optional[MoneyDecimal] = Field(None, ge=0)
    note: str = ""


class ContraBonScheduleIn(BaseModel):
    planned_payment_date: str
    method: str = "transfer"
    bank_account_id: str = ""
    notes: str = ""


class ContraBonPayIn(BaseModel):
    amount: Optional[MoneyDecimal] = Field(None, ge=0)   # None = seluruh sisa bersih
    method: str = "transfer"
    cash_type: str = "kas_besar"
    bank_account_id: str = ""
    paid_at: str = ""
    bank_line_id: str = ""        # diisi bila pembayaran lahir dari baris mutasi bank (G-8)
    notes: str = ""


class ContraBonNoteIn(BaseModel):
    reason_code: str = ""
    note: str = ""


class InvoiceExchangeIn(BaseModel):
    """Jadwal tukar faktur per supplier (mis. setiap Selasa / tanggal 25)."""
    mode: str = "none"            # none | weekly | biweekly | monthly
    weekday: int = Field(1, ge=0, le=6)    # 0=Senin … 6=Minggu (dipakai weekly/biweekly)
    day_of_month: int = Field(25, ge=1, le=28)
    pic_name: str = ""
    notes: str = ""
