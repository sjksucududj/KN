"""HRD schemas (FASE H0) — Employee Master, Org Units, HR Settings.

Di-re-export via `schemas.py` (pola sama schemas_crm/finance/purchasing).
Semua koleksi HR entity-scoped. Lihat ENTITY_REGISTRY.md (hr_employees, hr_org_units).
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HrOrgUnitCreate(BaseModel):
    """Unit organisasi: department | position (hierarki Company(entitas) > dept > position)."""
    name: str
    unit_type: str = "department"      # department | position
    code: str = ""
    parent_id: str = ""                # position -> department.id ; department -> ""
    head_employee_id: str = ""
    description: str = ""
    entity_id: str = ""


class AllowanceInput(BaseModel):
    name: str = ""
    amount: float = Field(0, ge=0)


class HrEmployeeCreate(BaseModel):
    """Master karyawan HR. user_id opsional (link akun login)."""
    name: str
    nik: str = ""
    user_id: str = ""                  # FK users.id (opsional; sales/manager/warehouse/admin)
    dob: str = ""
    gender: str = ""                   # L | P
    phone: str = ""
    email: str = ""
    address: str = ""
    department_id: str = ""            # FK hr_org_units (unit_type=department)
    position_id: str = ""              # FK hr_org_units (unit_type=position)
    shift_id: str = ""                 # FK hr_shifts (H1; kosong → shift default entitas)
    device_user_id: str = ""           # ID enroll mesin fingerprint (H1 import/ingest)
    employment_type: str = "tetap"     # tetap | kontrak | harian | borongan
    join_date: str = ""
    status: str = "active"             # active | inactive | resigned
    # --- PII-sensitive (redacted tanpa hr.view_pii; ESS lihat data sendiri penuh) ---
    npwp: str = ""
    ptkp_status: str = "TK0"           # TK0..TK3 | K0..K3
    bpjs_kes_enabled: bool = False
    bpjs_kes_no: str = ""
    bpjs_tk_enabled: bool = False
    bpjs_tk_no: str = ""
    jkk_risk_class: str = ""           # I..V (kelas risiko JKK)
    bank_name: str = ""
    bank_acc_no: str = ""
    bank_acc_name: str = ""
    base_salary: float = Field(0, ge=0)
    allowances: List[AllowanceInput] = []
    photo_url: str = ""
    entity_id: str = ""
    created_by: str = "HRD"


class HrSettingsUpdate(BaseModel):
    """Config HR/Payroll (system_settings scope='hr'). Semua opsional (partial update)."""
    bpjs: Optional[Dict[str, Any]] = None
    jkk_classes: Optional[List[Dict[str, Any]]] = None
    ptkp_table: Optional[Dict[str, Any]] = None
    ter_enabled: Optional[bool] = None
    feature_toggles: Optional[Dict[str, Any]] = None
    employment_types: Optional[List[str]] = None
    payroll_commission_mode: Optional[str] = None
