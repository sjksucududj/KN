"""HRD H3 schemas — Cuti, Izin & Lembur (Leave/Permit & Overtime).

Di-re-export via `schemas.py` (pola sama schemas_hr/attendance/tracking/payroll).
Semua koleksi H3 entity-scoped. Lihat ENTITY_REGISTRY.md (hr_leave_requests,
hr_leave_balances, hr_overtime) + memory/PLAN_HRD.md §6 FASE H3.
"""
from typing import Optional
from pydantic import BaseModel


class LeaveRequestInput(BaseModel):
    """Pengajuan cuti/izin/sakit. Tanggal ISO YYYY-MM-DD (rentang inklusif).
    `employee_id` opsional: diabaikan di endpoint ESS (/me), wajib di endpoint HRD."""
    leave_type: str = "cuti_tahunan"   # cuti_tahunan | cuti_besar | izin | sakit | unpaid
    date_from: str = ""
    date_to: str = ""
    reason: str = ""
    attachment_url: str = ""
    employee_id: str = ""              # hanya dipakai endpoint HRD (ajukan utk karyawan)


class OvertimeInput(BaseModel):
    """Pengajuan lembur. `hours` = jam (desimal). Approved → feed payroll periode."""
    date: str = ""                     # YYYY-MM-DD (WIB)
    hours: float = 0
    reason: str = ""
    rate_basis: str = "normal"         # informatif: normal | weekend | holiday
    employee_id: str = ""              # hanya dipakai endpoint HRD


class LeaveDecisionInput(BaseModel):
    """Alasan penolakan/pembatalan (opsional)."""
    reason: str = ""


class LeaveBalanceAdjust(BaseModel):
    """HRD set entitlement saldo cuti manual (mis. berdasar masa kerja)."""
    employee_id: str
    year: Optional[int] = None
    entitlement: int = 12
