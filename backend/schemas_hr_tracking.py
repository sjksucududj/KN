"""HRD H2 schemas — Live Field Tracking + Visits.

Re-exported via schemas.py. Koleksi: hr_field_tracks (trk_), hr_visits (visit_).
Lihat memory/PLAN_HRD.md §FASE H2.
"""
from typing import Optional
from pydantic import BaseModel


class PositionInput(BaseModel):
    """Push posisi GPS (REST fallback bila WS terblok ingress)."""
    lat: float
    lon: float
    accuracy: float = 0
    battery: Optional[float] = None


class VisitCheckIn(BaseModel):
    """Sales check-in di lokasi customer (GPS + foto + catatan)."""
    customer_id: str = ""
    customer_name: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    photo_url: str = ""
    notes: str = ""


class VisitCheckOut(BaseModel):
    """Sales check-out: tutup kunjungan + hasil."""
    lat: Optional[float] = None
    lon: Optional[float] = None
    notes: str = ""
    outcome: str = ""          # order | followup | no_order | other
    linked_so_id: str = ""
