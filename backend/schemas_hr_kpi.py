"""HRD H5 schemas — KPI Design (input KPI manual per karyawan/periode).

Di-re-export via `schemas.py` (pola sama schemas_hr_leave). Koleksi `hr_kpi`
(entity-scoped). Lihat ENTITY_REGISTRY.md + memory/PLAN_HRD.md §H5 (keputusan 2a).
"""
from typing import Optional
from pydantic import BaseModel, Field


class KpiInput(BaseModel):
    """Input KPI manual. `score` opsional: bila kosong dihitung otomatis dari
    target & aktual (min(actual/target,1.5)*100). `employee_id` wajib di endpoint HRD."""
    employee_id: str = ""
    period: str = ""                 # YYYY-MM
    metric: str = ""                 # nama metrik bebas (mis. "Jumlah desain")
    target: float = 0
    actual: float = 0
    score: Optional[float] = None    # 0–150; kosong = auto-hitung
    weight: float = Field(1, ge=0)                # bobot (untuk rekap tertimbang)
    note: str = ""


class KpiUpdate(BaseModel):
    """Update parsial nilai KPI (field yang dikirim saja)."""
    metric: Optional[str] = None
    period: Optional[str] = None
    target: Optional[float] = None
    actual: Optional[float] = None
    score: Optional[float] = None
    weight: Optional[float] = Field(None, ge=0)
    note: Optional[str] = None
