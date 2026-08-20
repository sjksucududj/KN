"""FASE E-7 (E7d) — skema Permintaan Internal (`internal_requests`).

Dipisah dari `schemas_interco.py` supaya jelas bedanya: permintaan internal adalah
**surat permintaan** milik badan usaha peminta, bukan dokumen keuangan antar-PT.
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas import QtyDecimal


class InternalRequestItemIn(BaseModel):
    product_id: str
    quantity: QtyDecimal = Field(..., gt=0)      # PS-15/R5 — terima "10,5"
    notes: str = ""
    # FASE U — DUA SATUAN: jumlah gulungan (roll) di samping ukuran (`quantity`+`unit`).
    # `None` = dokumen/baris ini tidak menyebut jumlah roll (dokumen LAMA tampil "—",
    # BUKAN "0 roll" yang menyesatkan). Diisi manual saat memesan (rencana), atau
    # DIHITUNG dari roll nyata saat penerimaan/pengiriman/retur (lihat §U.D rencana).
    qty_rolls: Optional[int] = Field(None, ge=0)


class InternalRequestCreate(BaseModel):
    items: List[InternalRequestItemIn]
    reason: str = ""
    needed_date: str = ""
    notes: str = ""
    source_order_id: str = ""
    # Hanya boleh diisi peran lintas-entitas (admin/manajer). Sales TIDAK memilih
    # badan usaha sumber — lihat alasannya di `services/internal_request_service`.
    source_entity_id: str = ""


class InternalRequestDecision(BaseModel):
    reason: str = ""


class InternalRequestConvert(BaseModel):
    source_entity_id: str = ""
    pricing_mode: Optional[str] = ""
    ppn_mode: Optional[str] = ""
    submit_now: bool = False
    notes: str = ""
