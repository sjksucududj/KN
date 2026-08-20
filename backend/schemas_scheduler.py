"""R6.5 schemas — Penjadwal (Scheduler) & Notifikasi + kanal WhatsApp.

Kredensial WhatsApp disimpan di `system_settings` scope='alerts' dan TIDAK PERNAH
dikembalikan plaintext oleh endpoint GET (hanya penanda `has_access_token` /
`has_fonnte_token`).
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class JobConfig(BaseModel):
    """Konfigurasi 1 job. `hour`/`minute` untuk jadwal harian (zona Asia/Jakarta),
    `interval_hours` untuk job berulang."""
    enabled: Optional[bool] = None
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    minute: Optional[int] = Field(default=None, ge=0, le=59)
    interval_hours: Optional[int] = Field(default=None, ge=1, le=24)


class WaConfig(BaseModel):
    """Aturan kredensial:
    - `access_token` / `fonnte_token` None  → JANGAN ubah nilai tersimpan.
    - non-empty → set nilai baru.  `clear_tokens=True` → hapus keduanya.
    """
    enabled: Optional[bool] = None
    provider: Optional[str] = None            # simulated | meta_cloud | fonnte
    access_token: Optional[str] = None        # Meta Cloud (System User token)
    phone_number_id: Optional[str] = None     # Meta Cloud
    template_name: Optional[str] = None       # Meta Cloud (template UTILITY disetujui)
    template_lang: Optional[str] = None
    fonnte_token: Optional[str] = None        # Fonnte
    sender: Optional[str] = None
    pic_number: Optional[str] = None          # nomor PIC tunggal (override/tambahan)
    send_to_roles: Optional[bool] = None      # kirim ke nomor user sesuai role
    min_severity: Optional[str] = None        # info | warning | critical
    delivery_mode: Optional[str] = None       # R6.6: instant | digest
    critical_bypass: Optional[bool] = None    # R6.6: critical tetap dikirim seketika
    clear_tokens: bool = False


class EscalationConfig(BaseModel):
    """R6.6 — kebijakan eskalasi alert yang belum ditindak (lintas kanal)."""
    enabled: Optional[bool] = None
    after_hours: Optional[int] = None         # 1..72 jam
    min_severity: Optional[str] = None        # info | warning | critical
    max_level: Optional[int] = None           # 1..3 tingkat rantai


class SchedulerSettingsUpdate(BaseModel):
    jobs: Optional[Dict[str, JobConfig]] = None
    wa: Optional[WaConfig] = None
    escalation: Optional[EscalationConfig] = None


class WaTestRequest(BaseModel):
    phone: str
    text: Optional[str] = None


class RunJobRequest(BaseModel):
    reason: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
