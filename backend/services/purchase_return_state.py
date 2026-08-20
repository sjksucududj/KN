"""R4 — Supplier RMA lifecycle untuk Retur Beli (Purchase Return).

Field `supplier_status` MELENGKAPI `status` dokumen (draft→pending_approval→approved|rejected)
untuk melacak interaksi FISIK/negosiasi dengan supplier setelah approval internal:

    requested_supplier → shipped_supplier → accepted_supplier (outcome: refund|ap_credit)
                                          → rejected_supplier → goods_back (+regrade, barang kembali ke KN)

Prinsip akuntansi (anti INV-GL-DRIFT): selama RMA (requested/shipped/rejected) roll TETAP
milik KN dan tetap terhitung di subledger persediaan (status fisik `quarantine`, earmarked).
Konsumsi stok + Nota Debit + jurnal GL BARU terjadi saat `accepted_supplier` (finalisasi).
Bila `goods_back`, roll cukup dikembalikan quarantine→available (dengan regrade) tanpa jurnal.

Alur DIRECT (retur beli langsung, mis. dari receiving PO reject) tidak memakai lifecycle ini:
approve langsung konsumsi stok + DN + GL (supplier_status di-set 'accepted_supplier').
"""
from typing import Dict, Set

# ── supplier_status ─────────────────────────────────────────────────────────
SUP_NONE = ""                         # belum/tidak memakai lifecycle RMA
REQUESTED = "requested_supplier"
SHIPPED = "shipped_supplier"
ACCEPTED = "accepted_supplier"
REJECTED = "rejected_supplier"
GOODS_BACK = "goods_back"

SUPPLIER_STATES = [SUP_NONE, REQUESTED, SHIPPED, ACCEPTED, REJECTED, GOODS_BACK]
SUPPLIER_TERMINAL: Set[str] = {ACCEPTED, GOODS_BACK}

SUPPLIER_STATUS_LABEL: Dict[str, str] = {
    SUP_NONE: "—",
    REQUESTED: "Diajukan ke Supplier",
    SHIPPED: "Dikirim ke Supplier",
    ACCEPTED: "Diterima Supplier",
    REJECTED: "Ditolak Supplier",
    GOODS_BACK: "Barang Kembali (regrade)",
}

# ── outcome saat supplier menerima retur ────────────────────────────────────
OUTCOME_REFUND = "refund"             # supplier kembalikan dana (kas) — nuansa GL kas penuh di R5
OUTCOME_AP_CREDIT = "ap_credit"       # potong hutang (AP) via Nota Debit
SUPPLIER_OUTCOMES: Set[str] = {OUTCOME_REFUND, OUTCOME_AP_CREDIT}

TRANSITIONS: Dict[str, Set[str]] = {
    REQUESTED:  {SHIPPED},
    SHIPPED:    {ACCEPTED, REJECTED},
    REJECTED:   {GOODS_BACK},
    ACCEPTED:   set(),
    GOODS_BACK: set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        allowed = ", ".join(sorted(TRANSITIONS.get(current, set()))) or "(tidak ada)"
        raise ValueError(
            f"Transisi supplier RMA tidak valid: '{current or 'NONE'}' → '{target}'. "
            f"Dari '{current or 'NONE'}' hanya boleh ke: {allowed}.")


def is_terminal(supplier_status: str) -> bool:
    return supplier_status in SUPPLIER_TERMINAL
