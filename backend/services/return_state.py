"""R1 — State machine retur jual (Sales Return).

Alur (RETURNS_ANALYSIS.md §R1):
  draft → pending_approval → approved(manager) → inspecting → inspected
        → [refund_settled | credit_settled | nego_settled | rejected]

Empat OUTCOME saat settle: refund / store_credit / nego / reject.
Outcome & qty bisa **per item/roll** (partial); item yang di-`reject` dikecualikan
dari penyelesaian finansial (sisa bisa dikirim-ulang untuk penggantian).

Modul murni (tanpa I/O) — mudah diuji & dipakai guard di service/router.
"""
from typing import Dict, Set

# ── States ────────────────────────────────────────────────────────────────
DRAFT = "draft"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"
INSPECTING = "inspecting"
INSPECTED = "inspected"
REFUND_SETTLED = "refund_settled"
CREDIT_SETTLED = "credit_settled"
NEGO_SETTLED = "nego_settled"
REJECTED = "rejected"
CANCELLED = "cancelled"

SALES_RETURN_STATES = [
    DRAFT, PENDING_APPROVAL, APPROVED, INSPECTING, INSPECTED,
    REFUND_SETTLED, CREDIT_SETTLED, NEGO_SETTLED, REJECTED, CANCELLED,
]

SETTLED_STATES: Set[str] = {REFUND_SETTLED, CREDIT_SETTLED, NEGO_SETTLED}
TERMINAL_STATES: Set[str] = SETTLED_STATES | {REJECTED, CANCELLED}

# ── Outcomes ─────────────────────────────────────────────────────────────
OUTCOME_REFUND = "refund"
OUTCOME_STORE_CREDIT = "store_credit"
OUTCOME_NEGO = "nego"
OUTCOME_REJECT = "reject"
VALID_OUTCOMES: Set[str] = {OUTCOME_REFUND, OUTCOME_STORE_CREDIT, OUTCOME_NEGO, OUTCOME_REJECT}
# Outcome yang menyelesaikan retur secara finansial (settle) — reject ditangani terpisah.
SETTLE_OUTCOMES: Set[str] = {OUTCOME_REFUND, OUTCOME_STORE_CREDIT, OUTCOME_NEGO}

OUTCOME_TO_STATE: Dict[str, str] = {
    OUTCOME_REFUND: REFUND_SETTLED,
    OUTCOME_STORE_CREDIT: CREDIT_SETTLED,
    OUTCOME_NEGO: NEGO_SETTLED,
    OUTCOME_REJECT: REJECTED,
}

OUTCOME_LABEL: Dict[str, str] = {
    OUTCOME_REFUND: "Refund",
    OUTCOME_STORE_CREDIT: "Store Credit (potong bon)",
    OUTCOME_NEGO: "Nego (diskon)",
    OUTCOME_REJECT: "Tolak",
}

# ── Transitions ──────────────────────────────────────────────────────────
TRANSITIONS: Dict[str, Set[str]] = {
    DRAFT:            {PENDING_APPROVAL, CANCELLED},
    PENDING_APPROVAL: {APPROVED, REJECTED, DRAFT, CANCELLED},
    APPROVED:         {INSPECTING, REJECTED, CANCELLED},
    INSPECTING:       {INSPECTED, REJECTED},
    INSPECTED:        {REFUND_SETTLED, CREDIT_SETTLED, NEGO_SETTLED, REJECTED},
    # R5.4 — reversal/koreksi: state settled boleh dibatalkan (→ cancelled) via reverse_settlement.
    REFUND_SETTLED:   {CANCELLED},
    CREDIT_SETTLED:   {CANCELLED},
    NEGO_SETTLED:     {CANCELLED},
    REJECTED:         set(),
    CANCELLED:        set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def assert_transition(current: str, target: str) -> None:
    """Raise ValueError bila transisi tidak diizinkan oleh state machine."""
    if not can_transition(current, target):
        allowed = ", ".join(sorted(TRANSITIONS.get(current, set()))) or "(tidak ada)"
        raise ValueError(
            f"Transisi status tidak valid: '{current}' → '{target}'. "
            f"Dari '{current}' hanya boleh ke: {allowed}.")


def state_for_outcome(outcome: str) -> str:
    """Terminal state untuk sebuah outcome. Raise ValueError bila outcome invalid."""
    if outcome not in OUTCOME_TO_STATE:
        raise ValueError(
            f"Outcome tidak valid: '{outcome}'. Pilihan: {', '.join(sorted(VALID_OUTCOMES))}.")
    return OUTCOME_TO_STATE[outcome]


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATES
