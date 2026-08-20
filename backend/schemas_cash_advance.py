"""Schemas — Digitalisasi Formulir Sukacita (Cash Advance / PD, Settlement, Vehicle).

Di-import langsung oleh router/service terkait (bukan re-export schemas.py agar
schemas.py tetap < 800 baris).
"""
from typing import List, Optional
from pydantic import BaseModel, Field


# ─── Form Pengajuan Dana (Cash Advance) ────────────────────────────────
class CashAdvanceLine(BaseModel):
    description: str = ""
    qty: float = Field(0.0, ge=0)          # FIX BUG EXCEL: satu kuantitas AKTIF per baris
    satuan: str = "unit"                    # roll | yard | kg | meter | unit | paket
    unit_price: float = Field(0.0, ge=0)
    catatan: str = ""
    # kolom breakdown asli (display-only, TIDAK dipakai hitung → cegah amount Rp0)
    qty_roll: Optional[float] = Field(None, ge=0)
    yard: Optional[float] = Field(None, ge=0)
    kg: Optional[float] = Field(None, ge=0)


class BankDetail(BaseModel):
    account_label: str = ""   # rekening tujuan (transfer), mis. "BCA - 123456"
    nama: str = ""
    no_account: str = ""
    bank: str = ""
    cabang: str = ""
    alamat_bank: str = ""
    swift_iban: str = ""


class CashAdvanceCreate(BaseModel):
    entity_id: Optional[str] = None
    divisi: str = ""
    kegiatan: str = ""
    period_from: str = ""
    period_to: str = ""
    tanggal_pengajuan: str = ""
    account_label: str = ""          # rekening SUMBER (default per entitas)
    payment_method: str = "tunai"    # tunai | transfer
    bank_detail: Optional[BankDetail] = None
    lines: List[CashAdvanceLine] = []
    catatan: str = ""


class CashAdvanceUpdate(BaseModel):
    divisi: Optional[str] = None
    kegiatan: Optional[str] = None
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    tanggal_pengajuan: Optional[str] = None
    account_label: Optional[str] = None
    payment_method: Optional[str] = None
    bank_detail: Optional[BankDetail] = None
    lines: Optional[List[CashAdvanceLine]] = None
    catatan: Optional[str] = None


class ApprovalDecision(BaseModel):
    note: str = ""


class DisburseInput(BaseModel):
    cash_type: str = "kas_kecil"     # kas_kecil (per-entitas) | kas_besar (grup)
    txn_date: str = ""
    note: str = ""


# ─── Laporan Pertanggungjawaban (Settlement) ───────────────────────────
class SettlementLine(BaseModel):
    date: str = ""
    description: str = ""
    category: str = "petty_cash_lain"
    amount: float = Field(0.0, ge=0)


class SettlementCreate(BaseModel):
    cash_advance_id: str
    divisi: str = ""
    periode: str = ""
    expense_lines: List[SettlementLine] = []
    dibuat_oleh: str = ""
    catatan: str = ""


class SettlementUpdate(BaseModel):
    divisi: Optional[str] = None
    periode: Optional[str] = None
    expense_lines: Optional[List[SettlementLine]] = None
    catatan: Optional[str] = None


class ExpenseCategoryUpdate(BaseModel):
    label: Optional[str] = None
    account_code: Optional[str] = None
    active: Optional[bool] = None


# ─── Laporan Penggunaan & Biaya Kendaraan ───────────────────────────
class VehicleCreate(BaseModel):
    entity_id: Optional[str] = None
    no_polisi: str
    nama: str = ""        # merk/nama kendaraan
    jenis: str = "mobil"  # mobil | motor | truk | lainnya
    active: bool = True


class VehicleUpdate(BaseModel):
    no_polisi: Optional[str] = None
    nama: Optional[str] = None
    jenis: Optional[str] = None
    active: Optional[bool] = None


class VehicleUsageCreate(BaseModel):
    entity_id: Optional[str] = None
    vehicle_id: str = ""
    no_polisi: str = ""
    tanggal: str = ""
    km_awal: float = Field(0.0, ge=0)
    km_akhir: float = Field(0.0, ge=0)
    bbm: float = Field(0.0, ge=0)
    tol: float = Field(0.0, ge=0)
    parkir: float = Field(0.0, ge=0)
    lain_lain: float = Field(0.0, ge=0)
    tujuan: str = ""
    driver: str = ""
    pemakai: str = ""
    mengetahui: str = ""
    cash_advance_id: str = ""


class VehicleUsageUpdate(BaseModel):
    tanggal: Optional[str] = None
    km_awal: Optional[float] = Field(None, ge=0)
    km_akhir: Optional[float] = Field(None, ge=0)
    bbm: Optional[float] = Field(None, ge=0)
    tol: Optional[float] = Field(None, ge=0)
    parkir: Optional[float] = Field(None, ge=0)
    lain_lain: Optional[float] = Field(None, ge=0)
    tujuan: Optional[str] = None
    driver: Optional[str] = None
    pemakai: Optional[str] = None
    mengetahui: Optional[str] = None
