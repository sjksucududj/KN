"""fa_coverage_gap.py — AUDIT Session #073 (READ-ONLY intent; destructive data cleaned by seed_reset).

Coverage-guided empirical probe of endpoints that the ENTIRE historical test
corpus NEVER executed (91 dark routes). Focus: financial reversal/GL flows +
auth/validation on untested CRUD. Verifies EMPIRICALLY (code wins over docs).

GL evidence via direct journal_entries reads (pymongo sync).
"""
import os
import sys
import requests
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN = os.environ.get("DB_NAME", "test_database")
mc = MongoClient(MONGO)[DBN]

ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
findings = []


def log(tag, msg):
    print(f"[{tag}] {msg}", flush=True)


def finding(fid, sev, title, evidence):
    findings.append({"id": fid, "sev": sev, "title": title, "evidence": evidence})
    log(sev, f"{fid}: {title}\n        -> {evidence}")


def login(cred):
    r = requests.post(f"{BASE}/auth/login", json=cred, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def acct_net(code, entity=None, source_type=None):
    """Net (debit-credit) for account_code across posted journal_entries."""
    q = {"status": "posted"}
    if entity:
        q["entity_id"] = entity
    if source_type:
        q["source_type"] = source_type
    net = 0.0
    for je in mc.journal_entries.find(q, {"_id": 0, "lines": 1}):
        for ln in je.get("lines", []):
            if ln.get("account_code") == code:
                net += float(ln.get("debit", 0)) - float(ln.get("credit", 0))
    return round(net, 2)


def je_ids():
    return {j["id"] for j in mc.journal_entries.find({}, {"_id": 0, "id": 1})}


def new_je_since(prev_ids):
    return [j for j in mc.journal_entries.find({}, {"_id": 0}) if j["id"] not in prev_ids]


# ══════════════════════════════════════════════════════════════════════════════
def test_purchase_return_gl(tok):
    log("T", "=== PRET-GL: purchase return approve -> GL reversal? ===")
    roll = mc.inventory_rolls.find_one(
        {"status": "available", "length_remaining": {"$gt": 1}},
        {"_id": 0, "product_id": 1, "warehouse_id": 1, "owner_entity_id": 1,
         "length_remaining": 1})
    if not roll:
        log("SKIP", "no available roll to return")
        return
    sup = mc.suppliers.find_one({}, {"_id": 0, "id": 1, "name": 1})
    pid, wid, eid = roll["product_id"], roll["warehouse_id"], roll["owner_entity_id"]
    qty = min(2.0, float(roll["length_remaining"]) - 0.5) or 1.0

    ap_before = acct_net("2-1100", eid)          # Hutang Usaha
    inv_before = acct_net("1-1300", eid)         # Persediaan
    pret_je_before = mc.journal_entries.count_documents({"source_type": "purchase_return"})
    prev = je_ids()

    payload = {"supplier_id": sup["id"], "warehouse_id": wid, "entity_id": eid,
               "items": [{"product_id": pid, "quantity": qty, "reason": "audit-test",
                          "condition": "damaged"}],
               "reason": "audit", "submit_now": True}
    r = requests.post(f"{BASE}/purchase-returns", json=payload, headers=H(tok), timeout=20)
    if r.status_code not in (200, 201):
        log("ERR", f"create purchase-return failed {r.status_code}: {r.text[:200]}")
        return
    ret = r.json()
    rid = ret["id"]
    ra = requests.post(f"{BASE}/purchase-returns/{rid}/approve", json={"notes": "audit"},
                       headers=H(tok), timeout=20)
    if ra.status_code != 200:
        log("ERR", f"approve failed {ra.status_code}: {ra.text[:200]}")
        return
    appr = ra.json()

    ap_after = acct_net("2-1100", eid)
    inv_after = acct_net("1-1300", eid)
    pret_je_after = mc.journal_entries.count_documents({"source_type": "purchase_return"})
    news = new_je_since(prev)

    dn = appr.get("debit_note_number")
    log("INFO", f"status={appr.get('status')} debit_note={dn} "
                f"AP Δ={round(ap_after-ap_before,2)} INV Δ={round(inv_after-inv_before,2)} "
                f"new_JE={len(news)} pret_JE {pret_je_before}->{pret_je_after}")
    if appr.get("status") == "approved" and pret_je_after == pret_je_before and not any(
            j.get("source_type") == "purchase_return" for j in news):
        finding("PRET-GL", "P1-HIGH",
                "Retur beli (approve) TIDAK posting GL reversal (Hutang/Persediaan/PPN)",
                f"Retur {appr.get('number')} approved + Nota Debit {dn} terbit + stok dikurangi, "
                f"tetapi 0 journal_entries source=purchase_return; GL Hutang(2-1100) Δ={round(ap_after-ap_before,2)}, "
                f"Persediaan(1-1300) Δ={round(inv_after-inv_before,2)}. gl_service tak punya fungsi retur-beli. "
                f"AP hanya dikurangi di field PO.returned_amount (dokumen), bukan di GL -> Neraca AP/Persediaan overstated.")
    else:
        log("OK", "purchase-return posted GL (no bug) OR unexpected state")


def test_vendor_bill_cancel_gl(tok):
    log("T", "=== VB-CANCEL-GL: cancel POSTED vendor bill -> GL reversal? ===")
    # find a billable completed PO without an active bill
    billed_pos = {b["po_id"] for b in mc.vendor_bills.find({}, {"_id": 0, "po_id": 1})}
    po = None
    for p in mc.purchase_orders.find({"status": {"$in": ["completed", "receiving", "active"]}},
                                     {"_id": 0}):
        if p["id"] in billed_pos:
            continue
        if p.get("items"):
            po = p
            break
    if not po:
        log("SKIP", "no billable PO without existing bill")
        return
    item = po["items"][0]
    eid = po.get("entity_id")
    body = {"po_id": po["id"], "match_mode": "ordered", "submit_now": True,
            "items": [{"product_id": item.get("product_id"),
                       "billed_qty": float(item.get("quantity", item.get("qty", 1)) or 1),
                       "price": float(item.get("price", 0) or 0)}]}
    r = requests.post(f"{BASE}/vendor-bills", json=body, headers=H(tok), timeout=20)
    if r.status_code not in (200, 201):
        log("ERR", f"create vendor-bill failed {r.status_code}: {r.text[:200]}")
        return
    bill = r.json()
    bid = bill["id"]
    status = bill.get("status")
    log("INFO", f"bill {bill.get('bill_number')} status={status} match={bill.get('match_status')}")
    if status != "posted":
        log("SKIP", f"bill not auto-posted (status={status}); needs approval path - skip cancel test")
        # cleanup: leave for seed_reset
        return
    ap_after_post = acct_net("2-1100", eid)
    gririr_after_post = acct_net("2-1150", eid)
    # now cancel the POSTED bill
    prev = je_ids()
    rc = requests.post(f"{BASE}/vendor-bills/{bid}/cancel", json={"notes": "audit-cancel"},
                       headers=H(tok), timeout=20)
    if rc.status_code != 200:
        log("INFO", f"cancel returned {rc.status_code}: {rc.text[:200]}")
        return
    cancelled = rc.json()
    ap_after_cancel = acct_net("2-1100", eid)
    gririr_after_cancel = acct_net("2-1150", eid)
    news = new_je_since(prev)
    log("INFO", f"after cancel: status={cancelled.get('status')} "
                f"AP {ap_after_post}->{ap_after_cancel} GR/IR {gririr_after_post}->{gririr_after_cancel} "
                f"new_JE={len(news)}")
    if cancelled.get("status") == "cancelled" and abs(ap_after_cancel - ap_after_post) < 0.01 and not news:
        finding("VB-CANCEL-GL", "P1-HIGH",
                "Cancel Vendor Bill yang SUDAH posted TIDAK membalik GL (Hutang/GR-IR/PPN tetap)",
                f"Bill {bill.get('bill_number')} posted -> GL Cr Hutang {ap_after_post}. Setelah cancel: "
                f"status=cancelled tapi GL Hutang(2-1100) TETAP {ap_after_cancel} (Δ=0), GR/IR TETAP, 0 jurnal reversal. "
                f"gl_service tak punya fungsi reversal vendor-bill -> Neraca AP/GR-IR overstated permanen setelah void.")
    else:
        log("OK", "cancel reversed GL (no bug) OR bill not posted")


def test_payroll_gl(tok):
    log("T", "=== PAYROLL-GL: dark payroll run -> post-gl + pay balanced? ===")
    entity = "ent_ksc"
    period = None
    for cand in ["2026-03", "2026-02", "2026-01", "2025-12"]:
        if not mc.hr_payroll_runs.find_one({"entity_id": entity, "period": cand}):
            period = cand
            break
    if not period:
        log("SKIP", "no free payroll period")
        return
    pv = requests.post(f"{BASE}/hr/payroll/runs/preview",
                       json={"entity_id": entity, "period": period}, headers=H(tok), timeout=25)
    log("INFO", f"preview status={pv.status_code} {str(pv.text)[:160]}")
    cr = requests.post(f"{BASE}/hr/payroll/runs",
                       json={"entity_id": entity, "period": period}, headers=H(tok), timeout=25)
    if cr.status_code != 200:
        log("ERR", f"create payroll run failed {cr.status_code}: {cr.text[:200]}")
        return
    run = cr.json()
    rid = run["id"]
    ap = requests.post(f"{BASE}/hr/payroll/runs/{rid}/approve", headers=H(tok), timeout=25)
    log("INFO", f"approve status={ap.status_code}")
    prev = je_ids()
    pg = requests.post(f"{BASE}/hr/payroll/runs/{rid}/post-gl", headers=H(tok), timeout=25)
    news = new_je_since(prev)
    if pg.status_code != 200:
        finding("PAYROLL-GL-ERR", "P2",
                "Payroll post-gl (endpoint dark) mengembalikan error",
                f"POST /hr/payroll/runs/{{id}}/post-gl -> {pg.status_code}: {pg.text[:200]}")
    else:
        bal_ok = all(abs(float(j.get("total_debit", 0)) - float(j.get("total_credit", 0))) < 0.01
                     for j in news)
        log("INFO", f"post-gl OK new_JE={len(news)} balanced={bal_ok} "
                    f"sources={[j.get('source_type') for j in news]}")
        if not news:
            finding("PAYROLL-GL-NOOP", "P2",
                    "Payroll post-gl sukses (200) tapi TIDAK membuat journal_entries",
                    f"run {run.get('period')} post-gl 200 tetapi 0 JE baru -> GL beban gaji tak tercatat.")
        elif not bal_ok:
            finding("PAYROLL-GL-UNBAL", "P0",
                    "Payroll GL journal TIDAK seimbang", f"new JE debit!=credit: {news}")
        else:
            log("OK", "payroll post-gl balanced")
    # pay
    prev2 = je_ids()
    py = requests.post(f"{BASE}/hr/payroll/runs/{rid}/pay", json={}, headers=H(tok), timeout=25)
    news2 = new_je_since(prev2)
    log("INFO", f"pay status={py.status_code} new_JE={len(news2)} "
                f"balanced={all(abs(float(j.get('total_debit',0))-float(j.get('total_credit',0)))<0.01 for j in news2)}")
    if py.status_code == 200 and not news2:
        finding("PAYROLL-PAY-NOOP", "P2",
                "Payroll PAY sukses (200) tapi tidak posting GL kas keluar",
                f"pay 200 tetapi 0 JE -> Kas/Hutang gaji tak berkurang di GL.")


def test_dark_auth(tok):
    log("T", "=== AUTH on dark endpoints (unauth must be 401/403) ===")
    checks = [
        ("POST", "/uoms", {"code": "AUD", "name": "x"}),
        ("POST", "/warehouses", {"name": "x"}),
        ("POST", "/payment-terms", {"name": "x", "days": 30}),
        ("POST", "/hr/employees", {"name": "x"}),
        ("POST", "/documents/generate", {"order_id": "so_001"}),
        ("POST", "/documents/barcode", {"data": "x"}),
        ("POST", "/labels/generate", {"product_id": "x"}),
        ("PUT", "/permissions", {}),
        ("POST", "/approval-rules", {}),
    ]
    for m, path, body in checks:
        try:
            r = requests.request(m, f"{BASE}{path}", json=body, timeout=10)  # NO auth
        except Exception as e:
            log("ERR", f"{m} {path} exc {e}")
            continue
        if r.status_code in (401, 403):
            log("OK", f"{m} {path} -> {r.status_code} (protected)")
        elif r.status_code == 422:
            finding("AUTH-ORDER", "P2",
                    f"{m} {path} validasi body SEBELUM auth (422 unauth)",
                    f"unauth -> 422 (bukan 401): pydantic jalan sebelum require_permission; "
                    f"membocorkan skema & memungkinkan probing tanpa login.")
        else:
            finding("DARK-UNAUTH", "P0",
                    f"{m} {path} DAPAT diakses TANPA auth ({r.status_code})",
                    f"unauth {m} {path} -> {r.status_code}: {r.text[:120]}")


def test_dark_validation(tok):
    log("T", "=== VALIDATION on dark CRUD (admin) ===")
    # negative UOM conversion
    r = requests.post(f"{BASE}/uoms", json={"code": "AUDX", "name": "AuditNeg",
                                            "conversion_to_base": -5, "base_unit": "meter"},
                      headers=H(tok), timeout=10)
    log("INFO", f"POST /uoms negative conversion -> {r.status_code}")
    if r.status_code in (200, 201):
        finding("VAL-UOM", "P2", "UOM menerima conversion_to_base negatif",
                f"POST /uoms conversion_to_base=-5 -> {r.status_code} (tak divalidasi > 0).")
    # payment-term negative days
    r2 = requests.post(f"{BASE}/payment-terms", json={"name": "AuditNeg", "days": -30},
                       headers=H(tok), timeout=10)
    log("INFO", f"POST /payment-terms days=-30 -> {r2.status_code}")
    if r2.status_code in (200, 201):
        finding("VAL-PAYTERM", "P3", "payment-terms menerima days negatif",
                f"POST /payment-terms days=-30 -> {r2.status_code}.")


def main():
    tok = login(ADMIN)
    log("AUTH", "admin logged in")
    for fn in (test_purchase_return_gl, test_vendor_bill_cancel_gl, test_payroll_gl,
               test_dark_auth, test_dark_validation):
        try:
            fn(tok)
        except Exception as e:
            import traceback
            log("EXC", f"{fn.__name__}: {e}\n{traceback.format_exc()[-500:]}")
    print("\n" + "=" * 70)
    print(f"COVERAGE-GAP PROBE: {len(findings)} finding(s)")
    for f in findings:
        print(f"  [{f['sev']}] {f['id']}: {f['title']}")


if __name__ == "__main__":
    main()
