"""R5.3 — Cash ledger helper untuk refund retur (sales & purchase).

Mencatat mutasi kas-book (`cash_transactions`) TANPA memposting GL lagi — GL sisi kas
sudah diposting oleh CN/Nota-Debit (post_sales_return / post_purchase_return). Ini murni
buku kas/bank agar refund tunai tampil di kas ledger & rekonsiliasi bank.
Idempotent per (ref_type, ref_id, direction).
"""
from typing import Any, Dict, Optional

from db import db
from core_utils import new_id, now_iso

# Akun GL yang dianggap "kas kecil" — sisanya diperlakukan kas_besar/bank.
KAS_KECIL_CODE = "1-1110"


def cash_type_for(account_code: str) -> str:
    return "kas_kecil" if (account_code or "") == KAS_KECIL_CODE else "kas_besar"


async def _next_cash_number(entity_id: str = "") -> str:
    """Nomor kas ber-deret per badan usaha (E1.7) — kas grup sudah dihapus (E7.4)."""
    from core_utils import next_doc_number
    return await next_doc_number("cash_transactions", "number", "CASH-",
                                 entity_id=(entity_id or None))


async def record_return_cash(*, direction: str, amount: float, account_code: str,
                             category: str, description: str, entity_id: str,
                             ref_type: str, ref_id: str, journal_entry_id: str = "",
                             created_by: str = "system",
                             txn_date: str = "") -> Optional[Dict[str, Any]]:
    """Catat 1 mutasi kas untuk refund retur (in=supplier kembalikan dana; out=refund ke customer).
    Idempotent per (ref_type, ref_id, direction, non-void)."""
    amount = round(float(amount or 0), 2)
    if amount <= 0.01 or not ref_id:
        return None
    existing = await db.cash_transactions.find_one(
        {"ref_type": ref_type, "ref_id": ref_id, "direction": direction, "status": {"$ne": "void"}},
        {"_id": 0})
    if existing:
        return existing
    ctype = cash_type_for(account_code)
    # FASE E-7 (E7.4) — kas grup DIHAPUS: refund retur tetap uang badan usaha
    # dokumennya. `kas_besar` hanya menandakan buku bank, bukan kepemilikan grup.
    from services.cash_entity_service import resolve_owner
    txn_entity = resolve_owner(entity_id, what="Kas refund retur")
    now = now_iso()
    doc = {
        "id": new_id("cash"),
        "number": await _next_cash_number(txn_entity),
        "cash_type": ctype,
        "direction": direction,                 # in | out
        "amount": amount,
        "category": category,
        "description": description,
        "entity_id": txn_entity,
        "source_entity_id": entity_id or "",     # entitas asal dokumen (untuk telusur)
        "ref_type": ref_type,
        "ref_id": ref_id,
        "account_id": account_code or "",
        "account_code": account_code or "",
        "journal_entry_id": journal_entry_id or "",
        "gl_posted": True,                        # GL ditangani CN/Nota-Debit; jangan double-post
        "txn_date": txn_date or now,
        "reconciled": False,
        "status": "posted",
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    await db.cash_transactions.insert_one(dict(doc))
    return doc
