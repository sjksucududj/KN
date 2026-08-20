"""Schemas FASE G-0 — Pusat Pengaturan (config registry & resolver)."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConfigContext(BaseModel):
    """Konteks penilaian nilai efektif (lapisan mana yang ikut dihitung)."""
    entity_id: str = ""
    customer_id: str = ""
    supplier_id: str = ""
    product_id: str = ""
    document_id: str = ""


class ConfigValueIn(BaseModel):
    key: str
    value: Any = None
    scope_type: str = "global"
    scope_id: str = ""
    reason: str = ""
    effective_from: str = ""          # kosong = berlaku sekarang
    ctx: Optional[ConfigContext] = None


class ConfigBulkValuesIn(BaseModel):
    items: List[ConfigValueIn] = Field(default_factory=list)


class ConfigSimulateIn(BaseModel):
    simulator: str = ""
    key: str = ""                     # dipakai bila simulator tidak disebut eksplisit
    sample: Dict[str, Any] = Field(default_factory=dict)
    overrides: Dict[str, Any] = Field(default_factory=dict)   # nilai hipotetis per kunci
    ctx: Optional[ConfigContext] = None


class ImpactPreviewIn(BaseModel):
    product_id: str
    new_price: float = Field(..., gt=0)
    current_doc_id: str = ""
    entity_id: str = ""


class ImpactApplyIn(BaseModel):
    product_id: str
    new_price: float = Field(..., gt=0)
    doc_ids: List[str] = Field(default_factory=list)
    reason: str = ""
    entity_id: str = ""
    update_master: bool = True
