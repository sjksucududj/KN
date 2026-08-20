"""Finance schemas (EPIC7) — Kas & Bank (7B), dipisah agar schemas.py < 800 baris.
Di-reexport oleh schemas.py."""
from typing import List, Optional
from pydantic import BaseModel, Field


# ─── EPIC7-B: Kas & Bank (multi-akun + rekonsiliasi) ─────────────────────────

class BankAccountCreate(BaseModel):
    name: str                          # nama tampilan, mis. "BCA Operasional"
    account_type: str = "bank"         # bank | cash
    bank_name: str = ""                # nama bank (kosong utk cash)
    account_number: str = ""           # no rekening
    entity_id: str = ""                # pemilik akun; kosong = DEFAULT
    opening_balance: float = Field(0.0, ge=0)       # saldo awal
    currency: str = "IDR"
    note: str = ""


class BankAccountUpdate(BaseModel):
    name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    opening_balance: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None
    note: Optional[str] = None


class ReconcilePayload(BaseModel):
    reconciled: bool = True


# ─── EPIC7-C: Chart of Accounts + General Ledger ─────────────────────────────

class GLAccountCreate(BaseModel):
    code: str                          # kode akun, mis. "6-5000"
    name: str
    type: str                          # asset | liability | equity | income | expense
    parent_code: str = ""
    is_postable: Optional[bool] = True
    currency: str = "IDR"
    description: str = ""


class GLAccountUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_code: Optional[str] = None
    is_active: Optional[bool] = None
    is_postable: Optional[bool] = None


class JournalLineIn(BaseModel):
    account_code: str
    debit: float = 0.0
    credit: float = 0.0
    description: str = ""
    # Digitalisasi Sukacita (Voucher) — metadata opsional per baris jurnal
    job: Optional[str] = None       # kode job/proyek (analitik)
    memo: Optional[str] = None      # catatan tambahan per baris
    tax_code: Optional[str] = None  # kode pajak (mis. PPN/PPh) untuk voucher


class JournalEntryCreate(BaseModel):
    date: str = ""
    description: str = ""
    entity_id: str = ""
    lines: List[JournalLineIn] = []


# ─── Gelombang 3 F-8: reklasifikasi saldo Suspense (1-9999) ──────────────────

class SuspenseReclassInput(BaseModel):
    amount: float = Field(..., ge=0)                      # nominal yang direklasifikasi (> 0)
    side: str                          # posisi saldo suspense saat ini: "debit" | "credit"
    target_account: str                # akun tujuan reklasifikasi (bukan 1-9999)
    note: str = ""
    entity_id: Optional[str] = None    # entitas spesifik (default: entitas aktif)


# ─── EPIC7 — Pusat Pajak (PPh manual record) ─────────────────────────────────

class PphRecordInput(BaseModel):
    entity_id: str                     # entitas spesifik (wajib, bukan 'all')
    period: str                        # YYYY-MM
    code: str                          # kode butir PPh, mis. "pph23"
    name: str = ""                     # label butir (opsional; ambil dari config)
    rate: float = 0.0                  # % tarif efektif butir
    dpp: float = Field(0.0, ge=0)                   # Dasar Pengenaan Pajak (bruto)
    note: str = ""



# ─── P1-4: Anggaran (Budget) ─────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    entity_id: Optional[str] = None       # default: entitas aktif konteks
    year: int
    month: int = 0                         # 0 = anggaran tahunan; 1-12 = bulanan
    dimension: str = "account"             # R6.3 — "account" (akun COA) | "category" (kategori beban)
    key: Optional[str] = None              # R6.3 — kode akun / kode kategori (fallback: account_code)
    account_code: Optional[str] = ""       # kode akun GL (revenue/expense) — legacy/back-compat
    category_code: Optional[str] = ""      # R6.3 — kode kategori beban (alias key)
    amount: float = Field(0.0, ge=0)
    note: str = ""


class BudgetUpdate(BaseModel):
    amount: Optional[float] = Field(None, ge=0)
    month: Optional[int] = None
    year: Optional[int] = None
    note: Optional[str] = None


