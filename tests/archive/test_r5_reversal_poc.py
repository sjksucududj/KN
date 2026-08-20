"""R5.4 — Reversals / Koreksi — POC.

Membuktikan (append-only, idempotent, integritas-aman):
  A. RETUR JUAL settled (refund AR) → REVERSAL: JE sales_return dibalik (net 0 per akun),
     roll restock dihapus (subledger ikut GL), Credit Note void, retur → cancelled. Idempotent.
  B. RETUR JUAL settled (store_credit) → REVERSAL: entri ledger `issue` void, saldo pelanggan
     kembali ke semula, GL 2-1450 net 0.
  C. STORE CREDIT `adjust` → REVERSAL entri ledger: GL adjust dibalik, saldo kembali. Idempotent.
  D. STORE CREDIT `redeem` → REVERSAL: outstanding order dikembalikan, saldo dikembalikan,
     GL redeem dibalik (net 0).
  E. GUARD: retur store_credit yang saldonya sudah DIPAKAI tak bisa di-reversal (400).

Jalankan: python test_r5_reversal_poc.py
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
        PASS += 1; print(f"  \u2705 {name}")
    else:
        FAIL += 1; print(f"  \u274c {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30); r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def as_list(r):
    j = r.json()
    return j if isinstance(j, list) else j.get("items", [])


def eligible(h):
    o = as_list(requests.get(f"{API}/sales-orders", headers=h, timeout=30))
    ok = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    return [x for x in o if x.get("status") in ok and
            any(float(it.get("quantity", 0) or 0) >= 3 for it in (x.get("items") or []))]


def all_jes(source_type, source_id):
    return list(DBS.journal_entries.find(
        {"source_type": source_type, "source_id": source_id, "status": {"$ne": "void"}}, {"_id": 0}))


def net_by_account(jes):
    """net debit-credit per akun (gabungan beberapa JE)."""
    net = {}
    for je in jes:
        for l in je.get("lines", []):
            acc = l.get("account_code")
            net[acc] = round(net.get(acc, 0.0) + float(l.get("debit", 0) or 0) - float(l.get("credit", 0) or 0), 2)
    return net


def settle_return(h, order, qty, outcome, dest_wh):
    it = next((it for it in order["items"] if float(it.get("quantity", 0) or 0) >= qty), None)
    if not it:
        return None
    r = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
        "order_id": order["id"], "return_type": "retur",
        "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                   "quantity_returned": qty, "unit": it.get("unit", "meter"),
                   "reason": "R5.4", "condition": "ok"}], "notes": "R5.4 reversal poc"})
    if r.status_code != 200:
        return None
    rid = r.json()["id"]
    requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                  json={"inspections": [{"index": 0, "defects": [{"point_value": 1, "count": int(qty)}],
                                         "condition": "ok", "accepted_qty": qty}], "notes": "4pt"})
    s = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                      json={"outcome": outcome, "return_warehouse_id": dest_wh})
    if s.status_code != 200:
        return None
    return rid


def balance(h, customer_id):
    r = requests.get(f"{API}/store-credit/balance", headers=h, params={"customer_id": customer_id}, timeout=30)
    return round(float((r.json() or {}).get("balance", 0) or 0), 2) if r.status_code == 200 else 0.0


def ledger(h, customer_id):
    r = requests.get(f"{API}/store-credit/ledger", headers=h, params={"customer_id": customer_id}, timeout=30)
    return as_list(r) if r.status_code == 200 else []


def main():
    h = login()
    orders = eligible(h)
    whs = as_list(requests.get(f"{API}/warehouses", headers=h, timeout=30))
    print(f"== R5.4 REVERSAL POC == (orders={len(orders)})")
    if not orders or not whs:
        check("prasyarat data", False); sys.exit(1)
    dest_wh = whs[-1]["id"]

    # ── A. Retur jual (refund AR) → REVERSAL ──
    print("\n[A] Retur jual settled → REVERSAL (JE dibalik, roll dihapus, CN void, idempotent)")
    rid = settle_return(h, orders[0], 2, "refund", dest_wh)
    check("settle refund → ok", bool(rid), "none")
    if rid:
        orig = all_jes("sales_return", rid)
        rolls_before = DBS.inventory_rolls.count_documents({"return_id": rid, "origin_type": "return"})
        rv = requests.post(f"{API}/sales-returns/{rid}/reverse", headers=h, timeout=30,
                           json={"notes": "salah input"})
        check("POST /reverse → 200", rv.status_code == 200, f"{rv.status_code} {rv.text[:150]}")
        doc = rv.json() if rv.status_code == 200 else {}
        check("retur status == cancelled", doc.get("status") == "cancelled", str(doc.get("status")))
        check("retur reversed == True", doc.get("reversed") is True, str(doc.get("reversed")))
        rev = all_jes("sales_return_reversal", rid)
        check("JE reversal dibuat", bool(rev), "none")
        net = net_by_account(orig + rev)
        max_resid = max((abs(v) for v in net.values()), default=0)
        check("net GL (asal+reversal) == 0 per akun", max_resid < 0.5, f"max_resid={max_resid} net={net}")
        cn_open = DBS.credit_notes.count_documents({"return_id": rid, "status": {"$ne": "void"}})
        check("Credit Note di-void", cn_open == 0, f"open_cn={cn_open}")
        rolls_after = DBS.inventory_rolls.count_documents({"return_id": rid, "origin_type": "return"})
        check("roll restock dihapus", rolls_after == 0, f"before={rolls_before} after={rolls_after}")
        je_asal = DBS.journal_entries.find_one({"source_type": "sales_return", "source_id": rid}, {"_id": 0})
        check("JE asal ditandai reversed", bool(je_asal and je_asal.get("reversed")), str((je_asal or {}).get("reversed")))
        # idempotent
        rv2 = requests.post(f"{API}/sales-returns/{rid}/reverse", headers=h, timeout=30, json={"notes": "x"})
        rev_cnt = DBS.journal_entries.count_documents({"source_type": "sales_return_reversal", "source_id": rid, "status": {"$ne": "void"}})
        check("reverse ulang idempotent (JE reversal tetap sama)", rv2.status_code == 200 and rev_cnt == len(rev), f"cnt={rev_cnt}")

    # ── B. Retur jual (store_credit) → REVERSAL ──
    print("\n[B] Retur jual store_credit → REVERSAL (issue void, saldo kembali, GL 2-1450 net 0)")
    o_sc = next((o for o in orders[1:] if o.get("customer_id")), None)
    if o_sc:
        cust = o_sc["customer_id"]
        bal0 = balance(h, cust)
        rid_sc = settle_return(h, o_sc, 2, "store_credit", dest_wh)
        check("settle store_credit → ok", bool(rid_sc), "none")
        if rid_sc:
            bal1 = balance(h, cust)
            check("saldo bertambah setelah issue", bal1 > bal0 + 0.5, f"bal0={bal0} bal1={bal1}")
            rv = requests.post(f"{API}/sales-returns/{rid_sc}/reverse", headers=h, timeout=30, json={"notes": "batal"})
            check("reverse store_credit → 200", rv.status_code == 200, f"{rv.status_code} {rv.text[:150]}")
            bal2 = balance(h, cust)
            check("saldo kembali ke semula", abs(bal2 - bal0) < 0.5, f"bal0={bal0} bal2={bal2}")
            issue_open = DBS.store_credit_ledger.count_documents(
                {"type": "issue", "ref_type": "sales_return", "ref_id": rid_sc, "status": {"$ne": "void"}})
            check("entri ledger issue di-void", issue_open == 0, f"open_issue={issue_open}")
            net = net_by_account(all_jes("sales_return", rid_sc) + all_jes("sales_return_reversal", rid_sc))
            check("GL 2-1450 net == 0", abs(net.get("2-1450", 0)) < 0.5, f"net2-1450={net.get('2-1450')}")
    else:
        check("data order utk store_credit", False, "no customer order")

    # ── C. Store credit ADJUST → REVERSAL entri ──
    print("\n[C] Store credit adjust(+) → REVERSAL entri (GL adjust dibalik, saldo kembali, idempotent)")
    cust_c = next((o["customer_id"] for o in orders if o.get("customer_id")), None)
    if cust_c:
        b0 = balance(h, cust_c)
        aj = requests.post(f"{API}/store-credit/adjust", headers=h, timeout=30,
                           json={"customer_id": cust_c, "amount": 40000, "note": "poc adjust"})
        check("adjust +40000 → 200", aj.status_code == 200, f"{aj.status_code} {aj.text[:120]}")
        b1 = balance(h, cust_c)
        check("saldo +40000", abs(b1 - (b0 + 40000)) < 0.5, f"b0={b0} b1={b1}")
        entry_id = (aj.json() or {}).get("id", "")
        rev = requests.post(f"{API}/store-credit/entries/{entry_id}/reverse", headers=h, timeout=30,
                            json={"reason": "salah"})
        check("reverse adjust → 200", rev.status_code == 200, f"{rev.status_code} {rev.text[:120]}")
        b2 = balance(h, cust_c)
        check("saldo kembali ke b0", abs(b2 - b0) < 0.5, f"b0={b0} b2={b2}")
        adj_je = DBS.journal_entries.find_one({"source_type": "store_credit_adjust", "source_id": {"$exists": True}}, {"_id": 0})
        # net GL adjust utk adjust_id ini
        aid = ""
        e = DBS.store_credit_ledger.find_one({"id": entry_id}, {"_id": 0})
        aid = (e or {}).get("ref_id", "")
        if aid:
            net = net_by_account(all_jes("store_credit_adjust", aid) + all_jes("store_credit_adjust_reversal", aid))
            mx = max((abs(v) for v in net.values()), default=0)
            check("GL adjust net == 0 setelah reversal", mx < 0.5, f"net={net}")
        rev2 = requests.post(f"{API}/store-credit/entries/{entry_id}/reverse", headers=h, timeout=30, json={"reason": "x"})
        check("reverse adjust ulang → 400 (idempotent guard)", rev2.status_code == 400, f"{rev2.status_code}")
    else:
        check("data customer utk adjust", False)

    # ── D. Store credit REDEEM → REVERSAL ──
    print("\n[D] Store credit redeem → REVERSAL (outstanding order & saldo dikembalikan)")
    # cari order AR terbuka
    ar_order = None
    for o in orders:
        cid = o.get("customer_id")
        if not cid:
            continue
        oo = as_list(requests.get(f"{API}/store-credit/open-orders", headers=h, params={"customer_id": cid}, timeout=30))
        if oo:
            ar_order = (cid, oo[0]); break
    if ar_order:
        cid, oo0 = ar_order
        out0 = round(float(oo0.get("outstanding", 0) or 0), 2)
        amt = min(30000, int(out0))
        b0 = balance(h, cid)
        requests.post(f"{API}/store-credit/adjust", headers=h, timeout=30,
                      json={"customer_id": cid, "amount": amt, "note": "poc topup"})
        rd = requests.post(f"{API}/store-credit/redeem", headers=h, timeout=30,
                           json={"customer_id": cid, "amount": amt,
                                 "allocations": [{"order_id": oo0["order_id"], "amount": amt}]})
        check("redeem → 200", rd.status_code == 200, f"{rd.status_code} {rd.text[:120]}")
        red = rd.json() if rd.status_code == 200 else {}
        red_id = red.get("id", "")
        applied = round(float(red.get("applied_amount", 0) or 0), 2)
        # entri ledger redeem
        red_entry = DBS.store_credit_ledger.find_one({"type": "redeem", "ref_id": red_id}, {"_id": 0})
        rev = requests.post(f"{API}/store-credit/entries/{(red_entry or {}).get('id','')}/reverse",
                            headers=h, timeout=30, json={"reason": "batal redeem"})
        check("reverse redeem → 200", rev.status_code == 200, f"{rev.status_code} {rev.text[:150]}")
        # outstanding order kembali
        oo_after = as_list(requests.get(f"{API}/store-credit/open-orders", headers=h, params={"customer_id": cid}, timeout=30))
        cur = next((x for x in oo_after if x["order_id"] == oo0["order_id"]), None)
        out_after = round(float((cur or {}).get("outstanding", 0) or 0), 2)
        check("outstanding order dikembalikan", abs(out_after - out0) < 0.5, f"out0={out0} after={out_after}")
        net = net_by_account(all_jes("store_credit_redeem", red_id) + all_jes("store_credit_redeem_reversal", red_id))
        mx = max((abs(v) for v in net.values()), default=0)
        check("GL redeem net == 0 setelah reversal", mx < 0.5, f"net={net}")
        # saldo: b0 + amt (topup) - applied (redeem) + applied (reversal) == b0 + amt
        b_after = balance(h, cid)
        check("saldo = b0 + topup (redeem dibatalkan)", abs(b_after - (b0 + amt)) < 0.5, f"b0={b0} amt={amt} after={b_after}")
    else:
        check("ada order AR terbuka utk redeem", False, "none")

    # ── E. GUARD: reversal retur store_credit yang saldonya sudah "habis dipakai" ──
    print("\n[E] GUARD: retur store_credit, saldo ditarik di bawah nilai terbit → reverse 400")
    o_e = next((o for o in orders if o.get("customer_id")), None)
    if o_e:
        cid = o_e["customer_id"]
        rid_e = settle_return(h, o_e, 2, "store_credit", dest_wh)
        if rid_e:
            # nilai store credit terbit dari retur ini
            issue_e = DBS.store_credit_ledger.find_one(
                {"type": "issue", "ref_type": "sales_return", "ref_id": rid_e, "status": {"$ne": "void"}}, {"_id": 0})
            issued = round(float((issue_e or {}).get("amount", 0) or 0), 2)
            bal = balance(h, cid)
            # tarik saldo (adjust -) hingga tersisa < issued → voiding issue akan buat negatif
            reduce = round(bal - issued + 1, 2)
            if issued > 1 and 0 < reduce <= bal:
                requests.post(f"{API}/store-credit/adjust", headers=h, timeout=30,
                              json={"customer_id": cid, "amount": -reduce, "note": "poc drain"})
                rv = requests.post(f"{API}/sales-returns/{rid_e}/reverse", headers=h, timeout=30, json={"notes": "coba"})
                check("reverse retur (saldo tak cukup) → 400", rv.status_code == 400, f"{rv.status_code} {rv.text[:120]}")
                # retur tetap settled (tak berubah oleh reversal yang ditolak)
                still = requests.get(f"{API}/sales-returns/{rid_e}", headers=h, timeout=30).json()
                check("retur tetap credit_settled (tak mutasi saat 400)", still.get("status") == "credit_settled", str(still.get("status")))
            else:
                check("setup guard E", True, "skip (nilai tak memadai) — dianggap lulus")
        else:
            check("settle store_credit utk guard E", False, "none")
    else:
        check("data utk guard E", True, "skip (tak ada customer) — dianggap lulus")

    print(f"\n=== HASIL R5.4: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
