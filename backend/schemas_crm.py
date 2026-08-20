"""CRM / Sales Force request schemas (KN_17 CRM-lite).

Dipisah dari schemas.py untuk menjaga batas ukuran file. Di-reekspor oleh
schemas.py agar `from schemas import ContactInfo, ...` tetap berfungsi.
"""
from typing import List
from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    """Multi-PIC kontak customer (KN_17 §2)."""
    name: str
    role: str = ""
    phone: str = ""
    email: str = ""
    is_primary: bool = False


class PaymentProfile(BaseModel):
    """Profil pembayaran default customer (KN_17 §5.1)."""
    allowed_methods: List[str] = Field(default_factory=lambda: ["tunai", "tempo"])
    default_method: str = "tempo"          # kontan|tunai|tempo|dp|bertahap
    term_days: int = Field(30, ge=0)                     # untuk 'tempo'
    dp_percent: float = Field(0, ge=0, le=100)                    # untuk 'dp'
    installment_count: int = Field(0, ge=0)               # untuk 'bertahap'
    installment_interval_days: int = Field(30, ge=0)


class CustomerReassign(BaseModel):
    """Reassign customer ke salesperson lain (Manager/Admin, teraudit) — KN_17 §3."""
    assigned_sales_id: str
    reason: str = ""


class SalesTargetCreate(BaseModel):
    """Target sales per periode (KN_17 §6.1)."""
    sales_id: str
    entity_id: str = ""
    period_type: str = "month"            # month|quarter|year
    period: str                            # mis. 2026-06
    target_sales_amount: float = Field(0, ge=0)
    target_collection_amount: float = Field(0, ge=0)
    target_new_customers: int = 0
    target_focus_products: List[str] = Field(default_factory=list)
    notes: str = ""


class IncentiveTier(BaseModel):
    min_achievement: float = 0             # % capaian minimum
    rate: float = 0                         # % komisi pada tier ini


class SalesIncentiveCreate(BaseModel):
    """Skema insentif/komisi (KN_17 §6.2) — DEFAULT pencairan + tiered (S36)."""
    sales_id: str
    entity_id: str = ""
    period: str
    basis: str = "collection"             # collection|sales|tiered
    tiers: List[IncentiveTier] = Field(default_factory=list)
    bonus_new_customer: float = 0          # bonus per customer baru
    bonus_focus_product: float = 0
    notes: str = ""


class CreditOverrideCreate(BaseModel):
    """Permohonan bypass blokir kredit (KN_17 §5.2 / S37)."""
    customer_id: str
    order_id: str = ""
    amount: float = Field(0, ge=0)
    reason: str
    evidence_url: str = ""


class CreditOverrideDecision(BaseModel):
    decision: str                          # approve|reject
    reason: str = ""


class CollectionFollowupCreate(BaseModel):
    """Jejak follow-up penagihan (KN_17 §7 / S39)."""
    customer_id: str
    order_id: str = ""
    note: str
    outcome: str = "contacted"            # contacted|promised|paid|no_response|escalated
    next_action_date: str = ""
