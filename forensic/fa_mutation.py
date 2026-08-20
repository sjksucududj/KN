"""fa_mutation.py — AUDIT #073 F3: data-fault-injection mutation testing.

Injects invariant-violating corruptions into the DB, runs the CI gate that
*should* catch each, and records KILLED (gate FAILs = good) vs SURVIVED (gate
PASSes despite corruption = blind spot). Reverts every fault. Final reseed advised.

Measures REAL gate effectiveness — the meta-question: do the gates actually
protect against regressions, or give false green?
"""
import os
import re
import subprocess
import sys
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
from core_utils import now_iso, new_id  # noqa

db = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")]

INTEGRITY = ["python", "scripts/verify_data_integrity.py"]
ENTSCOPE = ["python", "backend/scripts/verify_entity_scoping.py"]
results = []


def run_gate(cmd):
    r = subprocess.run(cmd, cwd="/app", capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    m = re.search(r"FAIL\s+(\d+)", out)
    fail_n = int(m.group(1)) if m else (0 if r.returncode == 0 else -1)
    failed = (r.returncode != 0) or (fail_n and fail_n > 0)
    return failed, out.strip().splitlines()[-1] if out.strip() else "", r.returncode


def record(name, expect, killed, tail):
    verdict = "KILLED" if killed else "SURVIVED"
    match = "OK" if ((expect == "KILL") == killed) else "!!!"
    results.append((name, expect, verdict, match))
    print(f"[{verdict:8}] ({expect}-expected) {match}  {name}\n           gate: {tail[:90]}")


# ── F1: corrupt order total (expect KILL) ─────────────────────────────────────
def mut_order_total():
    o = db.sales_orders.find_one({"items.0": {"$exists": True}}, {"_id": 0, "id": 1, "total_amount": 1})
    if not o:
        print("[SKIP] no order"); return
    orig = o.get("total_amount", 0)
    db.sales_orders.update_one({"id": o["id"]}, {"$set": {"total_amount": float(orig) + 999999}})
    killed, tail, _ = run_gate(INTEGRITY)
    db.sales_orders.update_one({"id": o["id"]}, {"$set": {"total_amount": orig}})
    record("order.total_amount != Σsubtotal", "KILL", killed, tail)


# ── F2: corrupt inventory balance bucket (expect KILL) ────────────────────────
def mut_balance():
    b = db.inventory_balances.find_one({}, {"_id": 0, "id": 1, "on_hand_qty": 1})
    if not b:
        print("[SKIP] no balance"); return
    orig = b.get("on_hand_qty", 0)
    db.inventory_balances.update_one({"id": b["id"]}, {"$set": {"on_hand_qty": float(orig) + 500}})
    killed, tail, _ = run_gate(INTEGRITY)
    db.inventory_balances.update_one({"id": b["id"]}, {"$set": {"on_hand_qty": orig}})
    record("inventory_balance on_hand != Σbuckets", "KILL", killed, tail)


# ── F3: unbalanced journal entry (expect KILL ideally; measure) ───────────────
def mut_unbalanced_je():
    jid = "AUDIT_MUT_JE_UNBAL"
    db.journal_entries.delete_many({"id": jid})
    db.journal_entries.insert_one({
        "id": jid, "number": "AUDIT/JE-MUT", "date": now_iso(),
        "description": "AUDIT unbalanced", "source": "manual", "source_type": "manual",
        "source_id": jid, "entity_id": "ent_ksc", "status": "posted",
        "lines": [{"account_code": "1-1100", "debit": 1000, "credit": 0},
                  {"account_code": "4-1000", "debit": 0, "credit": 1}],  # 1000 != 1
        "total_debit": 1000, "total_credit": 1, "created_at": now_iso()})
    killed, tail, _ = run_gate(INTEGRITY)
    db.journal_entries.delete_many({"id": jid})
    record("journal_entry debit(1000) != credit(1)", "KILL", killed, tail)


# ── F4: approved sales_return WITHOUT credit note + GL (RET-2 outcome) ─────────
def mut_return_no_gl():
    r = db.sales_returns.find_one({}, {"_id": 0})
    created = False
    if not r:
        # create a minimal approved return with no credit note
        rid = "AUDIT_MUT_SRET"
        db.sales_returns.insert_one({
            "id": rid, "number": "SRET-AUDIT", "order_id": "so_001", "entity_id": "ent_ksc",
            "status": "approved", "items": [{"product_id": "x", "quantity_returned": 5}],
            "stock_adjusted": True, "credit_note_id": None, "created_at": now_iso()})
        created = True
        target = rid
        orig_status = None
    else:
        target = r["id"]; orig_status = r.get("status")
        db.sales_returns.update_one({"id": target},
            {"$set": {"status": "approved", "credit_note_id": None}})
    # ensure no credit note references it
    killed, tail, _ = run_gate(INTEGRITY)
    if created:
        db.sales_returns.delete_one({"id": target})
    else:
        db.sales_returns.update_one({"id": target}, {"$set": {"status": orig_status}})
    record("sales_return approved w/o credit-note/GL (RET-2 state)", "KILL", killed, tail)


# ── F5: scoped doc with NO entity_id (expect KILL by entity-scoping gate) ──────
def mut_missing_entity():
    oid = "AUDIT_MUT_NOENT"
    db.sales_orders.delete_many({"id": oid})
    db.sales_orders.insert_one({
        "id": oid, "number": "SO-AUDIT-NOENT", "status": "draft",
        "items": [{"product_id": "x", "quantity": 1, "price": 100, "subtotal": 100}],
        "total_amount": 100, "created_at": now_iso()})  # NO entity_id
    killed, tail, _ = run_gate(ENTSCOPE)
    db.sales_orders.delete_one({"id": oid})
    record("scoped sales_order missing entity_id", "KILL", killed, tail)


def main():
    print("=== MUTATION / FAULT-INJECTION TEST (gate effectiveness) ===\n")
    for fn in (mut_order_total, mut_balance, mut_unbalanced_je, mut_return_no_gl, mut_missing_entity):
        try:
            fn()
        except Exception as e:
            import traceback
            print(f"[EXC] {fn.__name__}: {e}\n{traceback.format_exc()[-400:]}")
    print("\n" + "=" * 70)
    killed = sum(1 for _, _, v, _ in results if v == "KILLED")
    survived = [r for r in results if r[2] == "SURVIVED"]
    print(f"MUTATIONS: {len(results)} | KILLED (caught)={killed} | SURVIVED (blind)={len(survived)}")
    print("\nGATE BLIND SPOTS (survived faults = corruption NOT detected by CI):")
    for name, expect, verdict, match in results:
        if verdict == "SURVIVED":
            print(f"  - {name}")
    print("\nUNEXPECTED (mismatch expectation):")
    for name, expect, verdict, match in results:
        if match == "!!!":
            print(f"  - {name}: expected {expect} got {verdict}")


if __name__ == "__main__":
    main()
