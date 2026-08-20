"""FASE G-1 — Skema request amandemen dokumen (koreksi ber-alasan & ber-jejak)."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AmendmentChange(BaseModel):
    """Satu perubahan yang diusulkan pada baris dokumen.

    `product_id` mengidentifikasi baris; `field` = qty | price | discount_percent.
    Nilai tujuan tidak boleh negatif — koreksi ke angka minus bukan amandemen,
    melainkan pembatalan/retur (ditolak juga di lapis service).
    """
    product_id: str
    field: str
    to: float = Field(ge=0)


class AmendmentPreviewIn(BaseModel):
    doc_type: str = "sales_order"
    doc_id: str
    reason_code: str = ""
    changes: List[AmendmentChange] = Field(default_factory=list)
    # Persen harus benar-benar persen: 0–100. Tanpa batas ini, "diskon 900%"
    # akan lolos lapis skema dan baru meledak di mesin harga (INV-NUM-01).
    order_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)


class AmendmentProposeIn(AmendmentPreviewIn):
    note: str = ""
    attachments: List[Dict[str, Any]] = Field(default_factory=list)


class AmendmentDecisionIn(BaseModel):
    action: str                      # approve | reject
    note: str = ""


class AmendmentReasonIn(BaseModel):
    code: str
    label: str
    help: str = ""
    applies_to: List[str] = Field(default_factory=lambda: ["sales_order"])
    affects_master: bool = False
    status: str = "active"
