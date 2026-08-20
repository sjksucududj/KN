"""Bank/Cash Accounts service (EPIC7-B) — multi-akun kas & bank + rekonsiliasi.

Koleksi kanonik: `bank_accounts` (master akun). Mutasi tetap memakai
`cash_transactions` (SSOT kas) dengan field opsional `account_id` yang
menautkan transaksi ke akun. Saldo akun = opening_balance + Σ(in) − Σ(out)
transaksi posted (non-void) milik akun tsb.

Rekonsiliasi sederhana: field `reconciled` (bool) + `reconciled_at` pada
cash_transactions; saldo terekonsiliasi dihitung dari transaksi reconciled.
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID

VALID_ACCOUNT_TYPES = {"bank", "cash"}


def _posted(txn: Dict[str, Any]) -> bool:
    return txn.get("status") != "void"


async def _txns_for(account_id: str) -> List[Dict[str, Any]]:
    return await db.cash_transactions.find(
        {"account_id": account_id, "status": {"$ne": "void"}}, {"_id": 0}
    ).sort("txn_date", -1).to_list(5000)


def _balance(opening: float, txns: List[Dict[str, Any]], reconciled_only: bool = False) -> float:
    bal = float(opening or 0)
    for t in txns:
        if reconciled_only and not t.get("reconciled"):
            continue
        amt = float(t.get("amount", 0) or 0)
        bal += amt if t.get("direction") == "in" else -amt
    return round(bal, 2)


def _enrich(acc: Dict[str, Any], txns: List[Dict[str, Any]]) -> Dict[str, Any]:
    opening = float(acc.get("opening_balance", 0) or 0)
    inflow = round(sum(float(t.get("amount", 0) or 0) for t in txns if t.get("direction") == "in"), 2)
    outflow = round(sum(float(t.get("amount", 0) or 0) for t in txns if t.get("direction") == "out"), 2)
    reconciled = sum(1 for t in txns if t.get("reconciled"))
    return {
        **acc,
        "balance": _balance(opening, txns),
        "reconciled_balance": _balance(opening, txns, reconciled_only=True),
        "inflow": inflow,
        "outflow": outflow,
        "txn_count": len(txns),
        "unreconciled_count": len(txns) - reconciled,
    }


async def list_accounts(entity_id: Optional[str] = None,
                        scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = dict(scope) if scope is not None else {}
    if scope is None and entity_id and entity_id != "all":
        q["entity_id"] = entity_id
    accounts = await db.bank_accounts.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    out = []
    for acc in accounts:
        txns = await _txns_for(acc["id"])
        out.append(_enrich(acc, txns))
    return out


async def create_account(payload, actor: Dict[str, Any]) -> Dict[str, Any]:
    if payload.account_type not in VALID_ACCOUNT_TYPES:
        raise ValueError("account_type harus 'bank' atau 'cash'")
    doc = {
        "id": new_id("bank"),
        "name": payload.name.strip(),
        "account_type": payload.account_type,
        "bank_name": (payload.bank_name or "").strip(),
        "account_number": (payload.account_number or "").strip(),
        "entity_id": payload.entity_id or DEFAULT_ENTITY_ID,
        "opening_balance": round(float(payload.opening_balance or 0), 2),
        "currency": payload.currency or "IDR",
        "note": (payload.note or "").strip(),
        "is_active": True,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.bank_accounts.insert_one(doc)
    return _enrich(safe_doc(doc), [])


async def update_account(account_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    acc = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acc:
        return None
    upd = {k: v for k, v in patch.items() if v is not None}
    if "opening_balance" in upd:
        upd["opening_balance"] = round(float(upd["opening_balance"]), 2)
    if "name" in upd:
        upd["name"] = str(upd["name"]).strip()
    upd["updated_at"] = now_iso()
    await db.bank_accounts.update_one({"id": account_id}, {"$set": upd})
    acc = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    txns = await _txns_for(account_id)
    return _enrich(acc, txns)


async def account_ledger(account_id: str) -> Optional[Dict[str, Any]]:
    acc = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    if not acc:
        return None
    txns = await _txns_for(account_id)
    # running balance (kronologis menaik)
    chron = sorted(txns, key=lambda t: (t.get("txn_date") or "", t.get("number") or ""))
    running = float(acc.get("opening_balance", 0) or 0)
    for t in chron:
        amt = float(t.get("amount", 0) or 0)
        running += amt if t.get("direction") == "in" else -amt
        t["running_balance"] = round(running, 2)
    chron.reverse()  # tampilkan terbaru dulu
    return {**_enrich(acc, txns), "transactions": chron}


async def reconcile_txn(txn_id: str, reconciled: bool) -> Optional[Dict[str, Any]]:
    txn = await db.cash_transactions.find_one({"id": txn_id}, {"_id": 0})
    if not txn:
        return None
    await db.cash_transactions.update_one(
        {"id": txn_id},
        {"$set": {"reconciled": bool(reconciled),
                  "reconciled_at": now_iso() if reconciled else "",
                  "updated_at": now_iso()}},
    )
    return await db.cash_transactions.find_one({"id": txn_id}, {"_id": 0})
