"""FASE C — Skema Lot kelas satu (`inventory_lots`) · D-10/D-26/D-27.

Semua qty memakai tipe desimal PS-15 (menerima "10,5" maupun "10.5").
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class LotCreateIn(BaseModel):
    """Buat lot manual (mis. stok awal / koreksi data lapangan)."""
    product_id: str
    owner_entity_id: str = ""
    warehouse_id: str = ""
    source: str = "manual"
    supplier_lot: str = ""
    dye_lot: str = ""
    shade_ref: str = ""
    supplier_id: str = ""
    supplier_name: str = ""
    lot_status: str = ""
    note: str = ""
    roll_ids: List[str] = Field(default_factory=list)
    parent_lot_ids: List[str] = Field(default_factory=list)


class LotPatchIn(BaseModel):
    supplier_lot: Optional[str] = None
    dye_lot: Optional[str] = None
    shade_ref: Optional[str] = None
    note: Optional[str] = None
    warehouse_id: Optional[str] = None
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None


class LotStatusIn(BaseModel):
    status: str
    reason: str = ""


class LotSplitIn(BaseModel):
    roll_ids: List[str] = Field(default_factory=list)
    reason: str = ""
    dye_lot: str = ""
    warehouse_id: str = ""


class LotMergeIn(BaseModel):
    lot_ids: List[str] = Field(default_factory=list)
    reason: str = ""
    dye_lot: str = ""
    warehouse_id: str = ""


class LotReworkIn(BaseModel):
    process_type: str
    roll_ids: List[str] = Field(default_factory=list)
    partner_id: str = ""
    partner_name: str = ""
    to_stage: str = ""
    dye_lot: str = ""
    reason: str = ""


class LotAttachRollsIn(BaseModel):
    roll_ids: List[str] = Field(default_factory=list)
    keep_lot_string: bool = False


class LotSettingsIn(BaseModel):
    """D-27 — penegakan lot bisa dikonfigurasi tanpa deploy."""
    enforcement_mode: Optional[str] = None       # warn | block
    require_supplier_lot: Optional[bool] = None
    require_dye_lot: Optional[bool] = None
    auto_create_on_receiving: Optional[bool] = None
    status_on_receipt: Optional[str] = None


class LotLabelIn(BaseModel):
    format: str = "zpl"                          # zpl | escpos
    qty: int = Field(1, ge=1, le=50)
    roll_id: str = ""
