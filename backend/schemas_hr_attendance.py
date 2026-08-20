"""HRD H1 schemas — Absensi (attendance): shift, geofence, device, clock, import.

Di-re-export via `schemas.py` (pola sama schemas_hr/crm/finance/purchasing).
Semua koleksi H1 entity-scoped. Lihat ENTITY_REGISTRY.md (hr_shifts/hr_geofences/
hr_attendance/hr_devices) + memory/PLAN_HRD.md §6 FASE H1.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class HrShiftCreate(BaseModel):
    """Definisi shift kerja (jam masuk/keluar + toleransi telat)."""
    name: str
    code: str = ""
    jam_in: str = "08:00"          # HH:MM (WIB)
    jam_out: str = "17:00"         # HH:MM (WIB)
    grace_late_min: int = 10       # toleransi telat (menit)
    break_min: int = 60            # istirahat (menit) — informatif (V1 tak dipotong)
    work_days: List[int] = [1, 2, 3, 4, 5]   # 1=Senin .. 7=Minggu
    entity_id: str = ""


class HrGeofenceCreate(BaseModel):
    """Lokasi sah absen (kantor/gudang) — radius meter (haversine)."""
    name: str
    lat: float = 0
    lon: float = 0
    radius_m: int = 150
    address: str = ""
    entity_id: str = ""


class HrDeviceCreate(BaseModel):
    """Registry mesin fingerprint ZKTeco (untuk agen jembatan on-prem + ingest)."""
    name: str
    code: str = ""                 # serial number device
    location: str = ""
    entity_id: str = ""


class ClockInInput(BaseModel):
    """ESS clock-in geo. lat/lon opsional (bila lokasi tak tersedia → flag no_location)."""
    lat: Optional[float] = None
    lon: Optional[float] = None
    accuracy: float = 0
    photo_url: str = ""
    note: str = ""


class ClockOutInput(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    accuracy: float = 0
    photo_url: str = ""
    note: str = ""


class ManualAttendanceInput(BaseModel):
    """Entry/edit manual oleh HR (mis. karyawan tanpa device)."""
    employee_id: str
    date: str                      # YYYY-MM-DD (WIB)
    clock_in: str = ""             # HH:MM
    clock_out: str = ""            # HH:MM
    status: str = "hadir"          # hadir | telat | izin | cuti | alpha | libur
    note: str = ""


class AttendanceImportInput(BaseModel):
    """Import log ZKTeco (CSV teks). Kolom: user_id,timestamp[,status]."""
    csv_text: str
    device_id: str = ""            # opsional (untuk catat last_sync)
    entity_id: str = ""


class AttendanceIngestInput(BaseModel):
    """Payload agen jembatan on-prem (auth device_token). records=[{user_id,timestamp}]."""
    device_token: str
    records: List[Dict[str, Any]] = []
