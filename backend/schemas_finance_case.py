"""FASE G-9 — Skema masukan **Pusat Kasus Keuangan**.

Semua nominal WAJIB punya batas bawah (`ge=0`) — `INV-NUM-01` memerahkan field uang
tanpa bound karena nominal negatif yang lolos skema bisa membalik arah jurnal.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CaseSource(BaseModel):
    """Dari mana kasus ini berasal (mutasi bank, kwitansi, tagihan, atau manual)."""
    kind: str = "manual"          # bank_holding | bank_line | ar_receipt | vendor_bill | manual
    id: str = ""
    label: str = ""


class CaseCreate(BaseModel):
    case_type: str
    title: str = ""
    description: str = ""
    amount: float = Field(0, ge=0)
    entity_id: str = ""
    customer_id: str = ""
    supplier_id: str = ""
    order_ids: List[str] = Field(default_factory=list)
    source: Optional[CaseSource] = None
    assignee: str = ""
    attachments: List[Dict[str, Any]] = Field(default_factory=list)


class CaseNoteInput(BaseModel):
    note: str = ""
    attachments: List[Dict[str, Any]] = Field(default_factory=list)


class CaseAssignInput(BaseModel):
    assignee: str = ""


class CaseAllocation(BaseModel):
    order_id: str
    amount: float = Field(0, ge=0)


class CaseResolveInput(BaseModel):
    action: str
    reason_code: str = ""
    note: str = ""
    amount: float = Field(0, ge=0)
    customer_id: str = ""
    supplier_id: str = ""
    order_id: str = ""
    from_order_id: str = ""
    to_order_id: str = ""
    allocations: List[CaseAllocation] = Field(default_factory=list)
    account_id: str = ""
    to_account_id: str = ""
    cash_type: str = "kas_besar"
    method: str = "transfer"
    employee_name: str = ""
    owner_entity_id: str = ""
    receipt_id: str = ""
    with_penalty: bool = False
    attachments: List[Dict[str, Any]] = Field(default_factory=list)


class CaseRejectInput(BaseModel):
    reason_code: str = ""
    note: str = ""
