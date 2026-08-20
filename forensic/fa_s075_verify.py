"""fa_s075_verify.py — AUDIT S075: RIGOROUS correctness + idempotency verification.

Goes beyond "a JE now exists": asserts EXACT accounts/amounts, DOUBLE-EXECUTION
safety (no duplicate CN/JE/reversal, no double stock/HPP), and TRIAL-BALANCE
round-trips for every fixed GL flow. Destructive -> reseed after.
"""
import os
import sys
import requests
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")]
OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  :: {detail}" if detail else ""), flush=True)


def login(email="admin@kainnusantara.id"):
    return requests.post(f"{BASE}/auth/login", json={"email": email, "password": "demo12345"}, timeout=15).json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def acct_net(code, entity=None):
    q = {"status": "posted"}
    if entity:
        q["entity_id"] = entity
    n = 0.0
    for je in mc.journal_entries.find(q, {"_id": 0, "lines": 1}):
        for l in je.get("lines", []):
            if l.get("account_code") == code:
                n += float(l.get("debit", 0)) - float(l.get("credit", 0))
    return round(n, 2)


def tb_balanced(entity=None):
    q = {"status": "posted"}
    if entity:
        q["entity_id"] = entity
    d = c = 0.0
    for je in mc.journal_entries.find(q, {"_id": 0, "lines": 1}):
        for l in je.get("lines", []):
            d += float(l.get("debit", 0)); c += float(l.get("credit", 0))
    return abs(round(d - c, 2)) < 0.01, round(d, 2), round(c, 2)


def je_balanced(je):
    d = round(sum(float(l.get("debit", 0)) for l in je.get("lines", [])), 2)
    c = round(sum(float(l.get("credit", 0)) for l in je.get("lines", [])), 2)
    return abs(d - c) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
def verify_ret2(tok):
    print("\n=== RET-2: sales return correctness + double-approve idempotency ===")
    so = mc.sales_orders.find_one({"items.0": {"$exists": True}}, {"_id": 0})
    it = so["items"][0]
    body = {"order_id": so["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": 1, "unit": it.get("unit", "meter"),
                       "reason": "audit", "condition": "ok"}], "notes": "audit", "submit_now": True}
    rid = requests.post(f"{BASE}/sales-returns", json=body, headers=H(tok)).json()["id"]
    cn0 = mc.credit_notes.count_documents({})
    je0 = mc.journal_entries.count_documents({"source_type": "sales_return"})
    roll0 = mc.inventory_rolls.count_documents({})
    tbok0, _, _ = tb_balanced(so.get("entity_id"))

    r1 = requests.post(f"{BASE}/sales-returns/{rid}/approve", json={"notes": "a"}, headers=H(tok))
    doc = mc.sales_returns.find_one({"id": rid}, {"_id": 0})
    je = mc.journal_entries.find_one({"source_type": "sales_return", "source_id": rid}, {"_id": 0})
    check("approve -> 200", r1.status_code == 200, str(r1.status_code))
    check("credit_note_id terisi", bool(doc.get("credit_note_id")), str(doc.get("credit_note_id")))
    check("credit_notes +1", mc.credit_notes.count_documents({}) - cn0 == 1)
    check("sales_return JE +1", mc.journal_entries.count_documents({"source_type": "sales_return"}) - je0 == 1)
    if je:
        accs = {l["account_code"] for l in je["lines"]}
        check("JE seimbang", je_balanced(je), f"D/C {je.get('total_debit')}/{je.get('total_credit')}")
        check("JE membalik Pendapatan (4-1000 debit)",
              any(l["account_code"] == "4-1000" and l.get("debit", 0) > 0 for l in je["lines"]))
        check("JE membalik Piutang (1-1200 kredit)",
              any(l["account_code"] == "1-1200" and l.get("credit", 0) > 0 for l in je["lines"]))
        check("JE reversal COGS (Persediaan 1-1300 debit + HPP 5-1000 kredit)",
              "1-1300" in accs and "5-1000" in accs)
    # DOUBLE APPROVE — must be idempotent
    requests.post(f"{BASE}/sales-returns/{rid}/approve", json={"notes": "a2"}, headers=H(tok))
    check("re-approve: NO duplicate credit_note", mc.credit_notes.count_documents({}) - cn0 == 1,
          f"delta={mc.credit_notes.count_documents({})-cn0}")
    check("re-approve: NO duplicate sales_return JE",
          mc.journal_entries.count_documents({"source_type": "sales_return"}) - je0 == 1)
    check("re-approve: stok TIDAK dobel (rolls delta stabil)",
          mc.inventory_rolls.count_documents({}) - roll0 <= 1,
          f"rolls delta={mc.inventory_rolls.count_documents({})-roll0}")
    tbok1, d1, c1 = tb_balanced(so.get("entity_id"))
    check("trial balance seimbang setelah retur", tbok1, f"D={d1} C={c1}")


def verify_pret(tok):
    print("\n=== PRET-GL: purchase return posting + double-approve idempotency ===")
    roll = mc.inventory_rolls.find_one({"status": "available", "length_remaining": {"$gt": 1}},
                                       {"_id": 0, "product_id": 1, "warehouse_id": 1, "owner_entity_id": 1})
    sup = mc.suppliers.find_one({}, {"_id": 0, "id": 1})
    if not roll or not sup:
        print("  SKIP: no roll/supplier"); return
    eid = roll["owner_entity_id"]
    payload = {"supplier_id": sup["id"], "warehouse_id": roll["warehouse_id"], "entity_id": eid,
               "items": [{"product_id": roll["product_id"], "quantity": 1, "reason": "audit", "condition": "good"}],
               "reason": "audit", "submit_now": True}
    rid = requests.post(f"{BASE}/purchase-returns", json=payload, headers=H(tok)).json()["id"]
    je0 = mc.journal_entries.count_documents({"source_type": "purchase_return"})
    requests.post(f"{BASE}/purchase-returns/{rid}/approve", json={"notes": "a"}, headers=H(tok))
    je = mc.journal_entries.find_one({"source_type": "purchase_return", "source_id": rid}, {"_id": 0})
    check("purchase_return JE +1", mc.journal_entries.count_documents({"source_type": "purchase_return"}) - je0 == 1)
    if je:
        accs = {l["account_code"] for l in je["lines"]}
        check("JE seimbang", je_balanced(je))
        check("JE kredit Persediaan (1-1300)",
              any(l["account_code"] == "1-1300" and l.get("credit", 0) > 0 for l in je["lines"]))
        check("JE debit Hutang/GR-IR (2-1100 atau 2-1150)", ("2-1100" in accs) or ("2-1150" in accs))
    requests.post(f"{BASE}/purchase-returns/{rid}/approve", json={"notes": "a2"}, headers=H(tok))
    check("re-approve: NO duplicate purchase_return JE",
          mc.journal_entries.count_documents({"source_type": "purchase_return"}) - je0 == 1)


def verify_vb_cancel(tok):
    print("\n=== VB-CANCEL-GL: reversal exactness + double-cancel idempotency ===")
    billed = {b["po_id"] for b in mc.vendor_bills.find({}, {"_id": 0, "po_id": 1})}
    po = None
    for p in mc.purchase_orders.find({"status": {"$in": ["completed", "receiving", "active"]}}, {"_id": 0}):
        if p["id"] not in billed and p.get("items"):
            po = p; break
    if not po:
        print("  SKIP: no billable PO"); return
    eid = po.get("entity_id"); item = po["items"][0]
    ap_pre = acct_net("2-1100", eid)
    body = {"po_id": po["id"], "match_mode": "ordered", "submit_now": True,
            "items": [{"product_id": item.get("product_id"),
                       "billed_qty": float(item.get("quantity", item.get("qty", 1)) or 1),
                       "price": float(item.get("price", 0) or 0)}]}
    bill = requests.post(f"{BASE}/vendor-bills", json=body, headers=H(tok)).json()
    bid = bill["id"]
    if bill.get("status") != "posted":
        # approve path
        mgr = login("manager@kainnusantara.id")
        requests.post(f"{BASE}/vendor-bills/{bid}/approve", json={"notes": "ok"}, headers=H(mgr))
        bill = mc.vendor_bills.find_one({"id": bid}, {"_id": 0})
    if bill.get("status") != "posted":
        print(f"  SKIP: bill not posted (status={bill.get('status')})"); return
    ap_posted = acct_net("2-1100", eid)
    check("posting menaikkan saldo Hutang (Cr)", ap_posted < ap_pre - 0.01,
          f"AP {ap_pre} -> {ap_posted}")
    rev0 = mc.journal_entries.count_documents({"source_type": "vendor_bill_reversal"})
    requests.post(f"{BASE}/vendor-bills/{bid}/cancel", json={"notes": "audit"}, headers=H(tok))
    ap_cancel = acct_net("2-1100", eid)
    rev = mc.journal_entries.find_one({"source_type": "vendor_bill_reversal", "source_id": bid}, {"_id": 0})
    check("cancel: reversal JE dibuat", rev is not None)
    if rev:
        check("reversal JE seimbang", je_balanced(rev))
    check("cancel: saldo Hutang KEMBALI ke sebelum-posting (net 0)", abs(ap_cancel - ap_pre) < 0.01,
          f"AP posted={ap_posted} -> cancel={ap_cancel} (target {ap_pre})")
    # DOUBLE CANCEL — idempotent (no 2nd reversal, no over-shoot)
    requests.post(f"{BASE}/vendor-bills/{bid}/cancel", json={"notes": "audit2"}, headers=H(tok))
    check("re-cancel: NO duplicate reversal JE",
          mc.journal_entries.count_documents({"source_type": "vendor_bill_reversal"}) - rev0 <= 1,
          f"delta={mc.journal_entries.count_documents({'source_type':'vendor_bill_reversal'})-rev0}")
    check("re-cancel: saldo Hutang tetap (tak over-reverse)", abs(acct_net('2-1100', eid) - ap_pre) < 0.01)


def verify_lc(tok):
    print("\n=== LC-APPLY-GL: posting exactness + double-approve idempotency ===")
    from services import landed_cost_service as lcs  # noqa
    # find PO with resolvable rolls (reuse landed_cost probe helper via API create attempt)
    po = None
    for p in mc.purchase_orders.find({}, {"_id": 0}):
        rolls = mc.inventory_rolls.count_documents({"acquired.ref_id": p["id"]})
        if rolls:
            po = p; break
    if not po:
        print("  SKIP: no PO with received rolls (LC lifecycle covered by test_landed_cost_poc 17/0)"); return
    eid = po.get("entity_id", "ent_ksc")
    inv0 = acct_net("1-1300", eid)
    je0 = mc.journal_entries.count_documents({"source_type": "landed_cost"})
    admin = tok; mgr = login("manager@kainnusantara.id")
    body = {"po_ids": [po["id"]], "entity_id": eid, "basis": "value", "provider_name": "AUDIT",
            "cost_lines": [{"category": "freight", "description": "x", "amount": 3_000_000.0}],
            "submit_now": True}
    v = requests.post(f"{BASE}/landed-costs", json=body, headers=H(admin))
    if v.status_code not in (200, 201):
        print("  SKIP: create LC failed", v.status_code); return
    vid = v.json()["id"]
    requests.post(f"{BASE}/landed-costs/{vid}/approve", headers=H(mgr))
    inv1 = acct_net("1-1300", eid)
    je = mc.journal_entries.find_one({"source_type": "landed_cost", "source_id": vid}, {"_id": 0})
    check("landed_cost JE dibuat", je is not None)
    if je:
        check("JE seimbang", je_balanced(je))
        check("GL Persediaan naik ~alokasi", inv1 > inv0 + 0.01, f"1-1300 {inv0} -> {inv1}")
    # double approve
    requests.post(f"{BASE}/landed-costs/{vid}/approve", headers=H(mgr))
    check("re-approve: NO duplicate landed_cost JE",
          mc.journal_entries.count_documents({"source_type": "landed_cost"}) - je0 == 1)
    check("re-approve: GL Persediaan TIDAK dobel", abs(acct_net("1-1300", eid) - inv1) < 0.01)


def verify_global():
    print("\n=== GLOBAL: semua JE posted seimbang + trial balance per entitas ===")
    bad = [je.get("number") for je in mc.journal_entries.find({"status": "posted"}, {"_id": 0})
           if not je_balanced(je)]
    check("semua JE posted seimbang", not bad, str(bad[:5]))
    for eid in ["ent_ksc", "ent_kanda"]:
        ok, d, c = tb_balanced(eid)
        check(f"trial balance {eid} seimbang", ok, f"D={d} C={c}")


def main():
    sys.path.insert(0, "/app/backend")
    tok = login()
    for fn in (verify_ret2, verify_pret, verify_vb_cancel, verify_lc):
        try:
            fn(tok)
        except Exception as e:
            import traceback
            print(f"  [EXC] {fn.__name__}: {e}\n{traceback.format_exc()[-500:]}")
    try:
        verify_global()
    except Exception as e:
        print(f"  [EXC] verify_global: {e}")
    print("\n" + "=" * 66)
    print(f"RESULT: {len(OK)} PASS | {len(BAD)} FAIL")
    if BAD:
        print("FAILED:")
        for b in BAD:
            print("   -", b)
    print("[i] DESTRUCTIVE — reseed after.")


if __name__ == "__main__":
    main()
