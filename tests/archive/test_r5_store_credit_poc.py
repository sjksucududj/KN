"""R5.2 — Store Credit (Saldo Kredit Pelanggan) ledger — POC.

Membuktikan:
  1. Settle retur outcome=store_credit → GL Credit Note kredit ke **2-1450** (bukan Piutang 1-1200),
     dan entri ledger `issue` (+amount) terbentuk; saldo pelanggan = amount.
  2. Idempotent: settle ulang tidak menggandakan entri issue.
  3. Redeem: POST /api/store-credit/redeem meng-apply saldo ke order AR terbuka →
     GL **Dr 2-1450 / Cr 1-1200**, saldo turun, outstanding order turun (payments[].method=store_credit).
  4. Saldo tidak bisa over-redeem (>saldo → 400).
  5. Rekonsiliasi kewajiban: GL 2-1450 (kredit-debit) == Σ saldo ledger (per entitas).

Jalankan: python test_r5_store_credit_poc.py
"""
import os
import sys

import requests
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

API = f"{os.environ.get('R5_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
_MC = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DBS = _MC[os.environ.get("DB_NAME", "test_database")]
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \u2705 {name}")
    else:
        FAIL += 1
        print(f"  \u274c {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def gl_acct_balance(entity_id, acc):
    """(debit-credit) untuk akun tertentu di entitas."""
    total = 0.0
    for je in DBS.journal_entries.find({"entity_id": entity_id, "status": {"$ne": "void"}}, {"_id": 0}):
        for l in je.get("lines", []):
            if l.get("account_code") == acc:
                total += float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0)
    return round(total, 2)


def je_for(source_type, source_id):
    return DBS.journal_entries.find_one(
        {"source_type": source_type, "source_id": source_id, "status": {"$ne": "void"}}, {"_id": 0})


def ledger_count(customer_id, kind, ref_id):
    return DBS.store_credit_ledger.count_documents(
        {"customer_id": customer_id, "type": kind, "ref_id": ref_id, "status": {"$ne": "void"}})


def main():
    h = login()
    orders = requests.get(f"{API}/sales-orders", headers=h, timeout=30).json()
    orders = orders if isinstance(orders, list) else orders.get("items", [])
    ok = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    elig = [x for x in orders if x.get("status") in ok
            and any(float(it.get("quantity", 0) or 0) >= 5 for it in (x.get("items") or []))]
    print(f"== R5.2 STORE CREDIT POC == (eligible orders={len(elig)})")

    whs = requests.get(f"{API}/warehouses", headers=h, timeout=30).json()
    whs = whs if isinstance(whs, list) else whs.get("items", [])
    dest = whs[-1]["id"] if whs else ""

    # Pilih order yang customer-nya punya order AR terbuka (utk uji redeem).
    picked = None
    for o in elig:
        cid = o.get("customer_id")
        if not cid:
            continue
        opens = requests.get(f"{API}/store-credit/open-orders", headers=h,
                             params={"customer_id": cid}, timeout=30).json()
        if not (isinstance(opens, list) and any(float(x.get("outstanding", 0) or 0) > 1000 for x in opens)):
            continue
        it = next((it for it in o["items"] if float(it.get("quantity", 0) or 0) >= 2), None)
        if not it:
            continue
        # Coba buat retur di sini — lewati bila qty sudah habis diretur (data POC berulang).
        rr = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
            "order_id": o["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": 2, "unit": it.get("unit", "meter"),
                       "reason": "R5.2", "condition": "ok"}], "notes": "R5.2 store credit"})
        if rr.status_code == 200:
            picked = (o, it, cid, opens, rr.json())
            break
    check("ada order+customer dgn AR terbuka + retur bisa dibuat", bool(picked),
          "tidak ada; seed AR/returnable habis")
    if not picked:
        print(f"\n=== HASIL R5.2: PASS={PASS} FAIL={FAIL} ===")
        sys.exit(1 if FAIL else 0)
    order, item, cid, opens, ret_created = picked

    # Saldo awal (bisa > 0 karena backfill CN lama) — pakai DELTA.
    bal0 = float(requests.get(f"{API}/store-credit/balance", headers=h,
                 params={"customer_id": cid, "entity_id": order.get("entity_id", "")}, timeout=30).json().get("balance", 0))

    # ── 1. Retur (sudah dibuat) → settle store_credit ──
    print("\n[1] Retur → settle store_credit → GL Cr 2-1450 + ledger issue")
    check("buat retur → 200", True)
    rid = ret_created["id"]
    requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                  json={"inspections": [{"index": 0, "defects": [{"point_value": 1, "count": 2}],
                                         "condition": "ok", "accepted_qty": 2}], "notes": "4pt"})
    s = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                      json={"outcome": "store_credit", "return_warehouse_id": dest})
    check("settle store_credit → 200", s.status_code == 200, f"{s.status_code} {s.text[:150]}")
    sj = s.json()
    entity = sj.get("entity_id")
    issued = round(float((sj.get("settlement") or {}).get("store_credit_amount", 0) or 0), 2)
    check("settlement.store_credit_amount > 0", issued > 0, str(issued))

    je = je_for("sales_return", rid)
    check("JE retur ada", bool(je), "none")
    if je:
        cr_sc = round(sum(float(l.get("credit", 0) or 0) for l in je["lines"] if l.get("account_code") == "2-1450"), 2)
        cr_ar = round(sum(float(l.get("credit", 0) or 0) for l in je["lines"] if l.get("account_code") == "1-1200"), 2)
        check("JE kredit 2-1450 (store credit) == gross", abs(cr_sc - issued) < 0.5, f"2-1450 cr={cr_sc} vs {issued}")
        check("JE TIDAK kredit Piutang 1-1200 utk store credit", cr_ar < 0.01, f"1-1200 cr={cr_ar}")

    bal = requests.get(f"{API}/store-credit/balance", headers=h,
                       params={"customer_id": cid, "entity_id": entity}, timeout=30).json()
    bal1 = float(bal.get("balance", 0))
    check("saldo naik == issued (delta)", abs((bal1 - bal0) - issued) < 0.5, f"bal0={bal0} bal1={bal1} issued={issued}")
    check("ledger issue entry == 1", ledger_count(cid, "issue", rid) == 1, str(ledger_count(cid, "issue", rid)))

    # ── 2. Idempotensi issue ──
    print("\n[2] Idempotensi: settle store_credit ulang → tidak dobel issue")
    requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                  json={"outcome": "store_credit", "return_warehouse_id": dest})
    check("ledger issue tetap 1", ledger_count(cid, "issue", rid) == 1, str(ledger_count(cid, "issue", rid)))
    bal2 = float(requests.get(f"{API}/store-credit/balance", headers=h,
                 params={"customer_id": cid, "entity_id": entity}, timeout=30).json().get("balance", 0))
    check("saldo tidak berubah", abs(bal2 - bal1) < 0.5, f"bal1={bal1} bal2={bal2}")

    # ── 3. Redeem ke order AR terbuka ──
    print("\n[3] Redeem store credit → Dr 2-1450 / Cr 1-1200, outstanding turun")
    opens2 = requests.get(f"{API}/store-credit/open-orders", headers=h,
                          params={"customer_id": cid}, timeout=30).json()
    target = max(opens2, key=lambda x: float(x.get("outstanding", 0) or 0))
    redeem_amt = round(min(issued, float(target["outstanding"])), 2)
    out_before = float(target["outstanding"])
    gl_sc_before = gl_acct_balance(entity, "2-1450")
    red = requests.post(f"{API}/store-credit/redeem", headers=h, timeout=30, json={
        "customer_id": cid, "entity_id": entity, "amount": redeem_amt,
        "allocations": [{"order_id": target["order_id"], "amount": redeem_amt}]})
    check("redeem → 200", red.status_code == 200, f"{red.status_code} {red.text[:200]}")
    rj = red.json() if red.status_code == 200 else {}
    applied = round(float(rj.get("applied_amount", 0) or 0), 2)
    check("applied_amount == redeem_amt", abs(applied - redeem_amt) < 0.5, f"{applied} vs {redeem_amt}")

    jer = je_for("store_credit_redeem", rj.get("id"))
    check("JE redeem ada (source_type=store_credit_redeem)", bool(jer), "none")
    if jer:
        dr_sc = round(sum(float(l.get("debit", 0) or 0) for l in jer["lines"] if l.get("account_code") == "2-1450"), 2)
        cr_ar = round(sum(float(l.get("credit", 0) or 0) for l in jer["lines"] if l.get("account_code") == "1-1200"), 2)
        check("JE Dr 2-1450 == applied", abs(dr_sc - applied) < 0.5, f"dr={dr_sc}")
        check("JE Cr 1-1200 == applied", abs(cr_ar - applied) < 0.5, f"cr={cr_ar}")

    bal3 = float(requests.get(f"{API}/store-credit/balance", headers=h,
                 params={"customer_id": cid, "entity_id": entity}, timeout=30).json().get("balance", 0))
    check("saldo turun sebesar applied", abs((bal1 - applied) - bal3) < 0.5, f"bal1={bal1} applied={applied} bal3={bal3}")

    opens3 = requests.get(f"{API}/store-credit/open-orders", headers=h,
                          params={"customer_id": cid}, timeout=30).json()
    tgt3 = next((x for x in opens3 if x["order_id"] == target["order_id"]), None)
    out_after = float(tgt3["outstanding"]) if tgt3 else 0.0
    check("outstanding order turun == applied", abs((out_before - out_after) - applied) < 0.5,
          f"before={out_before} after={out_after}")

    # GL 2-1450 naik-debit sebesar applied (kewajiban turun)
    gl_sc_after = gl_acct_balance(entity, "2-1450")
    check("GL 2-1450 (debit-credit) naik == applied", abs((gl_sc_after - gl_sc_before) - applied) < 0.5,
          f"before={gl_sc_before} after={gl_sc_after}")

    # ── 4. Over-redeem ditolak ──
    print("\n[4] Over-redeem (>saldo) → 400")
    over = requests.post(f"{API}/store-credit/redeem", headers=h, timeout=30, json={
        "customer_id": cid, "entity_id": entity, "amount": 9_999_999_999})
    check("over-redeem ditolak (400)", over.status_code == 400, f"{over.status_code} {over.text[:120]}")

    # ── 5. Rekonsiliasi kewajiban 2-1450 == Σ saldo ledger (per entitas) ──
    print("\n[5] Rekonsiliasi: GL 2-1450 (kredit-debit) == Σ saldo ledger")
    ent_ids = [e["id"] for e in DBS.business_entities.find({}, {"_id": 0, "id": 1})]
    drift = []
    for eid in ent_ids:
        gl_liab = round(-gl_acct_balance(eid, "2-1450"), 2)   # kredit-debit
        led = 0.0
        for e in DBS.store_credit_ledger.find({"entity_id": eid, "status": {"$ne": "void"}}, {"_id": 0, "amount": 1}):
            led += float(e.get("amount", 0) or 0)
        led = round(led, 2)
        if abs(gl_liab - led) > 1.0:
            drift.append(f"{eid}: GL={gl_liab} ledger={led}")
    check("2-1450 GL == Σ ledger (semua entitas)", not drift, str(drift))

    print(f"\n=== HASIL R5.2: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
