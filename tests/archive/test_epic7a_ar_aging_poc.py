"""POC EPIC7-A — AR / Piutang Aging report + denda estimate + RBAC + drill-down."""
import requests

BASE = "http://localhost:8001/api"
P, F = 0, 0
BUCKETS = ["current", "b1_30", "b31_60", "b61_90", "b90_plus"]


def ok(c, m):
    global P, F
    P += 1 if c else 0
    F += 0 if c else 1
    print(f"  [{'PASS' if c else 'FAIL'}] {m}")


def login(e):
    return requests.post(f"{BASE}/auth/login", json={"email": e, "password": "demo12345"}).json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def approx(a, b, eps=1.0):
    return abs(float(a) - float(b)) <= eps


def main():
    admin = login("admin@kainnusantara.id")
    manager = login("manager@kainnusantara.id")
    sales = login("sales@kainnusantara.id")

    print("=== AR AGING summary (admin) ===")
    r = requests.get(f"{BASE}/ar/aging", headers=H(admin))
    ok(r.status_code == 200, f"GET /ar/aging 200 ({r.status_code})")
    d = r.json()
    totals = d.get("totals", {})
    ok(all(k in totals for k in BUCKETS), f"totals punya semua bucket ({list(totals.keys())})")
    bucket_sum = round(sum(totals.get(k, 0) for k in BUCKETS), 2)
    ok(approx(bucket_sum, totals.get("total", -1)), f"Σbucket == total ({bucket_sum} vs {totals.get('total')})")
    ok(totals.get("total", 0) > 0, f"ada total AR ({totals.get('total')})")
    ok(totals.get("customers", 0) >= 1 and totals.get("orders", 0) >= 1,
       f"counts customers/orders ({totals.get('customers')}/{totals.get('orders')})")

    rows = d.get("customers", [])
    ok(len(rows) == totals.get("customers"), f"jumlah baris customer == totals.customers ({len(rows)})")
    # invarian per-customer: Σbucket == outstanding
    inv_ok = all(approx(round(sum(c.get(k, 0) for k in BUCKETS), 2), c.get("outstanding", -1)) for c in rows)
    ok(inv_ok, "per-customer: Σbucket == outstanding")
    # sorted desc by outstanding
    sorted_ok = all(rows[i]["outstanding"] >= rows[i + 1]["outstanding"] for i in range(len(rows) - 1))
    ok(sorted_ok, "baris customer urut outstanding desc")
    # cross-check: Σ outstanding customer == totals.total
    cust_sum = round(sum(c.get("outstanding", 0) for c in rows), 2)
    ok(approx(cust_sum, totals.get("total", -1)), f"Σcustomer.outstanding == total ({cust_sum})")
    # credit_status valid
    ok(all(c.get("credit_status") in ("active", "warning", "blocked") for c in rows), "credit_status valid")

    print("\n=== DENDA estimate (config 2%/bln) ===")
    cfg = d.get("config", {})
    ok(cfg.get("denda_rate_pct_per_month", 0) > 0, f"denda rate aktif ({cfg.get('denda_rate_pct_per_month')}%/bln)")
    # denda hanya pada saldo overdue (current => denda 0)
    denda_consistent = all((c.get("denda", 0) == 0) for c in rows if c.get("overdue", 0) <= 0.01)
    ok(denda_consistent, "customer tanpa overdue => denda 0")
    ok(totals.get("denda", 0) >= 0, f"total denda terhitung ({totals.get('denda')})")

    print("\n=== DRILL-DOWN per customer ===")
    if rows:
        cid = rows[0]["customer_id"]
        r2 = requests.get(f"{BASE}/ar/aging/{cid}", headers=H(admin))
        ok(r2.status_code == 200, f"GET /ar/aging/{{id}} 200 ({r2.status_code})")
        dd = r2.json()
        ok(dd.get("customer_id") == cid, "detail customer_id cocok")
        items = dd.get("items", [])
        ok(len(items) >= 1, f"ada item order ({len(items)})")
        ok(all("due_date" in it and "bucket" in it and "days_late" in it for it in items),
           "tiap item punya due_date/bucket/days_late")
        # outstanding detail == ringkasan baris
        det_sum = round(sum(it.get("outstanding", 0) for it in items), 2)
        ok(approx(det_sum, rows[0]["outstanding"]), f"Σitem.outstanding == ringkasan ({det_sum} vs {rows[0]['outstanding']})")

    print("\n=== RBAC & edge ===")
    ok(requests.get(f"{BASE}/ar/aging", headers=H(manager)).status_code == 200, "manager -> /ar/aging 200")
    ok(requests.get(f"{BASE}/ar/aging", headers=H(sales)).status_code == 403, "sales -> /ar/aging 403")
    ok(requests.get(f"{BASE}/ar/aging/nope", headers=H(admin)).status_code == 404, "customer tak dikenal -> 404")
    # entity filter tidak melebihi total global
    rall = requests.get(f"{BASE}/ar/aging", headers=H(admin)).json()["totals"]["total"]
    rent = requests.get(f"{BASE}/ar/aging?entity_id=ent_ksc", headers=H(admin)).json()["totals"]["total"]
    ok(rent <= rall + 1, f"filter entitas <= total global ({rent} <= {rall})")

    print("\n" + "=" * 48)
    print(f"  HASIL: PASS {P} | FAIL {F}")
    print("=" * 48)
    return 0 if F == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
