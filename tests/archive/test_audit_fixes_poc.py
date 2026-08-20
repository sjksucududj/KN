"""POC test — verifikasi fix audit EPIC2-4 (P0-1, P1-2, P2-3..P2-6, P3-7, P3-8).

Dijalankan terhadap backend live (localhost:8001). Jalankan
`bash scripts/seed_reset.sh` lebih dulu untuk baseline bersih.
"""
import sys
import requests

BASE = "http://localhost:8001/api"
PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}")


def login(email, pw="demo12345"):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def section(t):
    print(f"\n=== {t} ===")


def open_orders(ah, cid):
    return requests.get(f"{BASE}/ar-receipts/open-orders", headers=ah, params={"customer_id": cid}).json()


def deposit(ah, cid):
    return requests.get(f"{BASE}/ar-receipts/deposit", headers=ah, params={"customer_id": cid}).json()["deposit_balance"]


def main():
    admin = login("admin@kainnusantara.id")
    sales = login("sales@kainnusantara.id")
    ah = H(admin)

    custs = requests.get(f"{BASE}/customers", headers=ah).json()
    # Pool customer dgn open AR order (urut byk order dulu) → alokasikan per skenario.
    pool = []
    for c in custs:
        oo = open_orders(ah, c["id"])
        if oo:
            pool.append((c, oo))
    pool.sort(key=lambda t: len(t[1]), reverse=True)
    ok(len(pool) >= 3, f"Ada >=3 customer dgn open AR untuk uji ({len(pool)})")

    c_p01 = pool[0][0]
    c_p25 = pool[1][0]
    c_p26 = pool[2][0]

    # ─── P0-1: AR receipt → cash_transactions ───────────────────────────────
    section("P0-1 — AR receipt posting ke cash_transactions + routing")
    o0 = open_orders(ah, c_p01["id"])[0]
    pay = round(o0["outstanding"] * 0.4, 2)
    rec = requests.post(f"{BASE}/ar-receipts", headers=ah, json={
        "customer_id": c_p01["id"], "amount": pay, "method": "transfer",
        "allocations": [{"order_id": o0["order_id"], "amount": pay}]}).json()
    ok(rec.get("applied_total") == pay, f"applied_total == amount ({rec.get('applied_total')})")
    cash = requests.get(f"{BASE}/cash-transactions", headers=ah).json()
    arc = [x for x in cash if x.get("ref_type") == "ar_receipt" and x.get("ref_id") == rec["id"]]
    ok(len(arc) == 1, "AR receipt → 1 cash_transaction (P0-1)")
    if arc:
        ok(abs(arc[0]["amount"] - pay) < 1, f"cash amount == receipt ({arc[0]['amount']})")
        ok(arc[0]["direction"] == "in", "direction == in")
        ok(arc[0]["cash_type"] == "kas_besar", f"transfer → kas_besar ({arc[0]['cash_type']})")
    rec_cash = requests.post(f"{BASE}/ar-receipts", headers=ah, json={
        "customer_id": c_p01["id"], "amount": 100000, "method": "cash"}).json()
    cash = requests.get(f"{BASE}/cash-transactions", headers=ah).json()
    arc2 = [x for x in cash if x.get("ref_id") == rec_cash.get("id")]
    ok(bool(arc2) and arc2[0]["cash_type"] == "kas_kecil",
       f"tunai → kas_kecil ({arc2[0]['cash_type'] if arc2 else 'N/A'})")

    # ─── P2-5: deposit (overpayment + use_deposit) ─────────────────────────
    section("P2-5 — deposit dari overpayment + pemakaian deposit")
    oo = open_orders(ah, c_p25["id"])
    o = oo[0]
    dep0 = deposit(ah, c_p25["id"])
    over = round(o["outstanding"] + 500000, 2)
    rec3 = requests.post(f"{BASE}/ar-receipts", headers=ah, json={
        "customer_id": c_p25["id"], "amount": over, "method": "transfer",
        "allocations": [{"order_id": o["order_id"], "amount": o["outstanding"]}]}).json()
    ok(abs(rec3.get("unapplied_amount", 0) - 500000) < 1,
       f"overpayment unapplied == 500000 ({rec3.get('unapplied_amount')})")
    dep1 = deposit(ah, c_p25["id"])
    ok(abs(dep1 - (dep0 + 500000)) < 1, f"deposit +500000 ({dep0}→{dep1})")
    oo2 = open_orders(ah, c_p25["id"])
    if oo2:
        o2 = oo2[0]
        use = min(dep1, o2["outstanding"])
        rec4 = requests.post(f"{BASE}/ar-receipts", headers=ah, json={
            "customer_id": c_p25["id"], "amount": 0, "use_deposit_amount": use, "method": "transfer",
            "allocations": [{"order_id": o2["order_id"], "amount": use}]})
        ok(rec4.status_code == 200, f"bayar pakai deposit (amount=0) → {rec4.status_code}")
        dep2 = deposit(ah, c_p25["id"])
        ok(abs(dep2 - (dep1 - use)) < 1, f"deposit -pemakaian ({dep1}→{dep2})")
        cash = requests.get(f"{BASE}/cash-transactions", headers=ah).json()
        ok(not any(x.get("ref_id") == rec4.json().get("id") for x in cash),
           "amount=0 (deposit) → tidak ada cash baru")
    else:
        print("  [skip] customer P2-5 tak punya order kedua untuk uji pakai-deposit")
    bad = requests.post(f"{BASE}/ar-receipts", headers=ah, json={
        "customer_id": c_p25["id"], "amount": 0, "use_deposit_amount": 9_999_999_999})
    ok(bad.status_code == 400, f"pakai deposit > saldo → 400 ({bad.status_code})")

    # ─── P2-6: void/reversal ───────────────────────────────────────────────
    section("P2-6 — void/reversal AR receipt")
    ov = open_orders(ah, c_p26["id"])[0]
    before_out = ov["outstanding"]
    payv = round(before_out * 0.5, 2)
    recv = requests.post(f"{BASE}/ar-receipts", headers=ah, json={
        "customer_id": c_p26["id"], "amount": payv, "method": "transfer",
        "allocations": [{"order_id": ov["order_id"], "amount": payv}]}).json()
    oo_mid = open_orders(ah, c_p26["id"])
    mid = next((x for x in oo_mid if x["order_id"] == ov["order_id"]), None)
    ok(mid is None or abs(mid["outstanding"] - (before_out - payv)) < 1,
       "outstanding turun setelah bayar (pra-void)")
    vr = requests.post(f"{BASE}/ar-receipts/{recv['id']}/void", headers=ah)
    ok(vr.status_code == 200 and vr.json().get("status") == "void", f"void → status void ({vr.status_code})")
    oo_after = open_orders(ah, c_p26["id"])
    aft = next((x for x in oo_after if x["order_id"] == ov["order_id"]), None)
    ok(aft is not None and abs(aft["outstanding"] - before_out) < 1,
       f"outstanding kembali setelah void ({aft['outstanding'] if aft else 'N/A'} ~ {before_out})")
    cashv = requests.get(f"{BASE}/cash-transactions", headers=ah).json()
    ok(not any(x.get("ref_id") == recv["id"] for x in cashv), "cash ter-void (hilang dari daftar aktif)")
    ok(requests.post(f"{BASE}/ar-receipts/{recv['id']}/void", headers=ah).status_code == 409,
       "double void → 409")
    ok(requests.post(f"{BASE}/ar-receipts/{recv['id']}/void", headers=H(sales)).status_code == 403,
       "sales void → 403")

    # ─── P2-3: cost-at-sale snapshot di SO line ─────────────────────────────
    section("P2-3 — snapshot unit_cost di SO line")
    orders = requests.get(f"{BASE}/sales-orders", headers=ah).json()
    orders = orders if isinstance(orders, list) else orders.get("items", [])
    lines = [it for o in orders for it in (o.get("items") or [])]
    with_cost = [it for it in lines if "unit_cost" in it]
    ok(len(lines) > 0 and len(with_cost) == len(lines),
       f"semua SO line punya unit_cost ({len(with_cost)}/{len(lines)})")
    ok(all(float(it.get("unit_cost", 0) or 0) >= 0 for it in with_cost), "unit_cost numerik & >=0")

    # ─── P3-8 / commission sanity ───────────────────────────────────────────
    section("P3-8 — komisi per-SKU dihitung tanpa error (margin base-unit)")
    sh = requests.get(f"{BASE}/home/sales", headers=H(sales))
    ok(sh.status_code == 200, f"/home/sales 200 ({sh.status_code})")
    bd = (sh.json().get("commission") or {}).get("breakdown") or []
    ok(isinstance(bd, list), "commission breakdown list")
    ok(len([b for b in bd if b.get("cost_missing")]) == 0,
       "tidak ada line cost_missing (harga_pokok tersedia)")

    # ─── P3-7: konsistensi NON_AR (collection worklist) ─────────────────────
    section("P3-7 — deteksi metode konsisten (collection worklist)")
    cw = requests.get(f"{BASE}/collection-reminders", headers=ah, params={"days_ahead": 3650})
    ok(cw.status_code == 200, f"/collection-reminders 200 ({cw.status_code})")
    nonar = {"kontan", "tunai", "cash", "cod"}
    bad_rows = []
    for row in cw.json():
        od = next((o for o in orders if o.get("id") == row.get("order_id")), None)
        if od:
            m = str((od.get("payment_profile_method") or od.get("payment_term_code") or "")).lower()
            if m in nonar:
                bad_rows.append(row.get("order_number"))
    ok(len(bad_rows) == 0, f"tak ada order NON_AR di worklist ({bad_rows})")

    # ─── P1-2: AR lintas >=3 sales ──────────────────────────────────────────
    section("P1-2 — AR receipt seed lintas >=3 sales")
    receipts = requests.get(f"{BASE}/ar-receipts", headers=ah).json()
    cust_sales = {c["id"]: c.get("assigned_sales_id") for c in custs}
    s = {cust_sales.get(r["customer_id"]) for r in receipts
         if r.get("status") != "void" and r.get("created_by") == "seed"}
    s.discard(None)
    ok(len(s) >= 3, f"AR seed tersebar ke >=3 sales ({len(s)})")

    print(f"\n{'='*56}\n  HASIL: PASS {PASS} | FAIL {FAIL}\n{'='*56}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
