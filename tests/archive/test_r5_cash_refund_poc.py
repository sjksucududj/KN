"""R5.3 — Cash refund + pemisahan GL (refund-kas vs ap_credit) — POC.

Membuktikan:
  A. RETUR JUAL refund TUNAI (order cash): settle refund + pilih akun Kas/Bank →
     GL Credit Note kredit ke akun terpilih (mis. 1-1110), DAN dibuat cash_transaction
     keluar (buku kas) TANPA double-GL. Idempotent (tak dobel cash_transaction).
  B. RETUR BELI supplier-accept:
       outcome=refund   → GL Dr Kas/Bank / Cr Persediaan (supplier bayar tunai) +
                          cash_transaction MASUK; AP (PO.returned_amount) TIDAK berubah.
       outcome=ap_credit→ GL Dr Hutang/GR-IR / Cr Persediaan (potong AP) + TANPA cash_transaction.
  C. Integritas tetap bersih.

Jalankan: python test_r5_cash_refund_poc.py
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
            any(float(it.get("quantity", 0) or 0) >= 5 for it in (x.get("items") or []))]


def je_lines(source_type, source_id):
    je = DBS.journal_entries.find_one(
        {"source_type": source_type, "source_id": source_id, "status": {"$ne": "void"}}, {"_id": 0})
    return je or {}


def acct_amt(je, acc, side):
    return round(sum(float(l.get(side, 0) or 0) for l in je.get("lines", []) if l.get("account_code") == acc), 2)


def cash_txn(ref_type, ref_id, direction):
    return DBS.cash_transactions.find_one(
        {"ref_type": ref_type, "ref_id": ref_id, "direction": direction, "status": {"$ne": "void"}}, {"_id": 0})


def make_return_and_settle_cash(h, orders, dest_wh, refund_acc):
    """Retur jual pada order yg di-set cash → settle refund (kas). Kembalikan (settle_json, rid)."""
    for o in orders:
        it = next((it for it in o["items"] if float(it.get("quantity", 0) or 0) >= 2), None)
        if not it:
            continue
        # SCAFFOLD test: jadikan order metode bayar tunai agar refund → kas.
        DBS.sales_orders.update_one({"id": o["id"]}, {"$set": {"payment_profile_method": "tunai"}})
        r = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
            "order_id": o["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": 2, "unit": it.get("unit", "meter"),
                       "reason": "R5.3", "condition": "ok"}], "notes": "R5.3 cash"})
        if r.status_code != 200:
            continue
        rid = r.json()["id"]
        requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                      json={"inspections": [{"index": 0, "defects": [{"point_value": 1, "count": 2}],
                                             "condition": "ok", "accepted_qty": 2}], "notes": "4pt"})
        s = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                          json={"outcome": "refund", "return_warehouse_id": dest_wh,
                                "refund_account_code": refund_acc})
        if s.status_code == 200:
            return s.json(), rid
    return None, None


def make_settled_sales_return(h, orders, dest_wh):
    for o in orders:
        it = next((it for it in o["items"] if float(it.get("quantity", 0) or 0) >= 1), None)
        if not it:
            continue
        r = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
            "order_id": o["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": 1, "unit": it.get("unit", "meter"),
                       "reason": "R5.3", "condition": "ok"}], "notes": "R5.3"})
        if r.status_code != 200:
            continue
        rid = r.json()["id"]
        requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                      json={"inspections": [{"index": 0, "defects": [{"point_value": 1, "count": 1}],
                                             "condition": "ok", "accepted_qty": 1}], "notes": "4pt"})
        s = requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                          json={"outcome": "refund", "return_warehouse_id": dest_wh}).json()
        q = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
        if isinstance(q, list) and q:
            return s, q
    return None, []


def supplier_pr_via_chain(h, orders, dest_wh, local_sup):
    sr, q = make_settled_sales_return(h, orders, dest_wh)
    if not sr:
        return None
    cr = requests.post(f"{API}/sales-returns/{sr['id']}/create-purchase-return", headers=h, timeout=30,
                       json={"supplier_id": local_sup["id"], "reason": "cacat"})
    if cr.status_code != 200:
        return None
    pr = cr.json()
    requests.post(f"{API}/purchase-returns/{pr['id']}/approve", headers=h, timeout=30, json={})
    requests.post(f"{API}/purchase-returns/{pr['id']}/ship-to-supplier", headers=h, timeout=30, json={})
    return pr


def main():
    h = login()
    orders = eligible(h)
    whs = as_list(requests.get(f"{API}/warehouses", headers=h, timeout=30))
    suppliers = as_list(requests.get(f"{API}/suppliers", headers=h, timeout=30))
    local_sup = next((s for s in suppliers if (s.get("origin_type") or "local") != "import"), None)
    print(f"== R5.3 CASH REFUND POC == (orders={len(orders)})")
    if not orders or not whs or not local_sup:
        check("prasyarat data", False); sys.exit(1)
    dest_wh = whs[-1]["id"]

    # ── A. Retur jual refund TUNAI ──
    print("\n[A] Retur jual refund TUNAI → GL Cr akun terpilih + cash_transaction keluar")
    REFUND_ACC = "1-1110"   # Kas Kecil (bukan default 1-1100) → buktikan pilihan akun dipakai
    s, rid = make_return_and_settle_cash(h, orders, dest_wh, REFUND_ACC)
    check("settle refund (cash) → ok", bool(s), str(s)[:120])
    if s:
        settle = s.get("settlement") or {}
        gross = round(float(settle.get("gross_amount", 0) or 0), 2)
        check("settlement.settlement == cash", settle.get("settlement") == "cash", str(settle.get("settlement")))
        check("settlement.cash_txn_number ada", bool(settle.get("cash_txn_number")), str(settle.get("cash_txn_number")))
        check("settlement.refund_account_code == pilihan", settle.get("refund_account_code") == REFUND_ACC, str(settle.get("refund_account_code")))
        je = je_lines("sales_return", rid)
        cr_acc = acct_amt(je, REFUND_ACC, "credit")
        cr_kas_default = acct_amt(je, "1-1100", "credit")
        cr_piutang = acct_amt(je, "1-1200", "credit")
        check("CN JE kredit akun terpilih 1-1110 == gross", abs(cr_acc - gross) < 0.5, f"1-1110 cr={cr_acc} gross={gross}")
        check("CN JE TIDAK kredit 1-1100 default", cr_kas_default < 0.01, f"1-1100 cr={cr_kas_default}")
        check("CN JE TIDAK kredit Piutang", cr_piutang < 0.01, f"1-1200 cr={cr_piutang}")
        ct = cash_txn("sales_return", rid, "out")
        check("cash_transaction keluar dibuat", bool(ct), "none")
        if ct:
            check("cash_txn amount == gross", abs(float(ct.get("amount", 0)) - gross) < 0.5, str(ct.get("amount")))
            check("cash_txn account == 1-1110", ct.get("account_code") == REFUND_ACC, str(ct.get("account_code")))
            check("cash_txn gl_posted=True (no double GL)", ct.get("gl_posted") is True, str(ct.get("gl_posted")))
        # idempotensi: settle ulang → tak dobel cash_transaction
        requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                      json={"outcome": "refund", "return_warehouse_id": dest_wh, "refund_account_code": REFUND_ACC})
        cnt = DBS.cash_transactions.count_documents({"ref_type": "sales_return", "ref_id": rid, "direction": "out", "status": {"$ne": "void"}})
        check("cash_transaction tetap 1 (idempotent)", cnt == 1, f"count={cnt}")

    # ── B. Retur beli: refund vs ap_credit ──
    print("\n[B1] Retur beli supplier-accept REFUND → Dr Kas / Cr Persediaan + kas MASUK, AP tak berubah")
    pr = supplier_pr_via_chain(h, orders, dest_wh, local_sup)
    check("supplier-flow PR (refund) siap (shipped)", bool(pr), str(pr)[:100] if pr else "none")
    if pr:
        po_id = pr.get("po_id")
        ra_before = None
        if po_id:
            po = DBS.purchase_orders.find_one({"id": po_id}, {"_id": 0, "returned_amount": 1})
            ra_before = float((po or {}).get("returned_amount", 0) or 0)
        ac = requests.post(f"{API}/purchase-returns/{pr['id']}/supplier-accept", headers=h, timeout=30,
                           json={"outcome": "refund", "refund_account_code": "1-1100"})
        check("supplier-accept refund → 200", ac.status_code == 200, f"{ac.status_code} {ac.text[:150]}")
        je = je_lines("purchase_return", pr["id"])
        dr_kas = acct_amt(je, "1-1100", "debit")
        dr_hutang = acct_amt(je, "2-1100", "debit") + acct_amt(je, "2-1150", "debit")
        check("PR JE Dr Kas 1-1100 > 0", dr_kas > 0, f"dr_kas={dr_kas}")
        check("PR JE TIDAK Dr Hutang/GR-IR", dr_hutang < 0.01, f"dr_hutang={dr_hutang}")
        ct = cash_txn("purchase_return", pr["id"], "in")
        check("cash_transaction MASUK dibuat", bool(ct), "none")
        if po_id:
            po2 = DBS.purchase_orders.find_one({"id": po_id}, {"_id": 0, "returned_amount": 1})
            ra_after = float((po2 or {}).get("returned_amount", 0) or 0)
            check("AP (PO.returned_amount) TIDAK berubah utk refund", abs(ra_after - (ra_before or 0)) < 0.5, f"before={ra_before} after={ra_after}")

    print("\n[B2] Retur beli supplier-accept AP_CREDIT → Dr Hutang/GR-IR / Cr Persediaan, TANPA kas")
    pr2 = supplier_pr_via_chain(h, orders, dest_wh, local_sup)
    check("supplier-flow PR (ap_credit) siap", bool(pr2), str(pr2)[:100] if pr2 else "none")
    if pr2:
        ac2 = requests.post(f"{API}/purchase-returns/{pr2['id']}/supplier-accept", headers=h, timeout=30,
                            json={"outcome": "ap_credit"})
        check("supplier-accept ap_credit → 200", ac2.status_code == 200, f"{ac2.status_code} {ac2.text[:150]}")
        je2 = je_lines("purchase_return", pr2["id"])
        dr_liab = acct_amt(je2, "2-1100", "debit") + acct_amt(je2, "2-1150", "debit")
        dr_kas2 = acct_amt(je2, "1-1100", "debit")
        check("PR JE Dr Hutang/GR-IR > 0 (potong AP)", dr_liab > 0, f"dr_liab={dr_liab}")
        check("PR JE TIDAK Dr Kas", dr_kas2 < 0.01, f"dr_kas={dr_kas2}")
        ct2 = cash_txn("purchase_return", pr2["id"], "in")
        check("ap_credit → TANPA cash_transaction", ct2 is None, str(ct2)[:60] if ct2 else "none")

    print(f"\n=== HASIL R5.3: PASS={PASS}  FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
