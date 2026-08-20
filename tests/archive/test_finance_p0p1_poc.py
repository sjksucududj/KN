"""POC — Finance P0/P1 endpoints (cash-flow, profitability, forecast, tower, budgets)."""
import requests

BASE = "http://localhost:8001/api"
ENT = "ent_ksc"
P, F = 0, 0


def ok(cond, label):
    global P, F
    if cond:
        P += 1; print(f"  [PASS] {label}")
    else:
        F += 1; print(f"  [FAIL] {label}")


def login():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@kainnusantara.id", "password": "demo12345"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def main():
    H = login()

    print("== R1: Cash Flow Statement ==")
    r = requests.get(f"{BASE}/finance/cash-flow", params={"entity_id": ENT}, headers=H)
    ok(r.status_code == 200, f"GET cash-flow 200 (got {r.status_code})")
    d = r.json()
    ok("operating" in d and "investing" in d and "financing" in d, "3 sections present")
    ok("net_income" in d.get("operating", {}), "operating.net_income present")
    ok(d.get("reconciled") is True,
       f"reconciled TRUE (net_change={d.get('net_change')} end_cash={d.get('end_cash')} actual={d.get('end_cash_actual')})")

    print("== R2: Profitability (WAC) ==")
    r = requests.get(f"{BASE}/finance/profitability", params={"entity_id": ENT}, headers=H)
    ok(r.status_code == 200, f"GET profitability 200 (got {r.status_code})")
    d = r.json()
    ok(all(k in d for k in ("by_product", "by_category", "by_customer", "by_sales")), "4 dimensions present")
    ok(d.get("cost_basis") == "WAC", "cost_basis=WAC")
    tot = d.get("totals", {})
    ok(tot.get("revenue", 0) > 0, f"total revenue > 0 ({tot.get('revenue')})")
    ok(tot.get("margin") == round(tot.get("revenue", 0) - tot.get("cogs", 0), 2), "margin = revenue - cogs")
    ok(len(d.get("by_product", [])) > 0, f"by_product rows ({len(d.get('by_product', []))})")

    print("== R3: Cash Flow Forecast ==")
    r = requests.get(f"{BASE}/finance/cashflow-forecast", params={"entity_id": ENT}, headers=H)
    ok(r.status_code == 200, f"GET forecast 200 (got {r.status_code})")
    d = r.json()
    ok(len(d.get("buckets", [])) == 5, f"5 buckets ({len(d.get('buckets', []))})")
    ok("cash_now" in d and "projected_cash" in d, "cash_now + projected_cash present")
    ok(d.get("total_inflow", 0) > 0 or d.get("total_outflow", 0) > 0, "some AR/AP flow detected")

    print("== R4: Finance Control Tower ==")
    r = requests.get(f"{BASE}/finance/tower", params={"entity_id": ENT}, headers=H)
    ok(r.status_code == 200, f"GET tower 200 (got {r.status_code})")
    d = r.json()
    ok(all(k in d for k in ("cash", "ar", "ap", "pl", "monthly", "ratios")), "tower keys present")
    ok("mtd" in d.get("pl", {}) and "ytd" in d.get("pl", {}), "pl mtd+ytd present")
    ok(len(d.get("monthly", [])) == 12, f"12 monthly points ({len(d.get('monthly', []))})")

    print("== R5: Budget CRUD + vs-actual ==")
    payload = {"entity_id": ENT, "year": 2026, "month": 0,
               "account_code": "4-1000", "amount": 500000000, "note": "poc test"}
    r = requests.post(f"{BASE}/finance/budgets", json=payload, headers=H)
    ok(r.status_code == 200, f"POST budget 200 (got {r.status_code}) {r.text[:120]}")
    bid = r.json().get("id")
    ok(bool(bid), "budget id returned")
    r = requests.get(f"{BASE}/finance/budgets", params={"year": 2026, "entity_id": ENT}, headers=H)
    ok(r.status_code == 200 and any(b.get("id") == bid for b in r.json()), "budget appears in list")
    r = requests.get(f"{BASE}/finance/budget-vs-actual", params={"year": 2026, "entity_id": ENT}, headers=H)
    ok(r.status_code == 200, f"GET budget-vs-actual 200 (got {r.status_code})")
    d = r.json()
    row = next((x for x in d.get("rows", []) if x.get("id") == bid), None)
    ok(row is not None, "budgeted account in vs-actual rows")
    if row:
        ok(row.get("variance") == round(row.get("budget", 0) - row.get("actual", 0), 2), "variance = budget - actual")
    ok("commitment" in d.get("totals", {}), "commitment (PO) in totals")
    r = requests.patch(f"{BASE}/finance/budgets/{bid}", json={"amount": 600000000}, headers=H)
    ok(r.status_code == 200 and r.json().get("amount") == 600000000, "PATCH budget amount")
    r = requests.delete(f"{BASE}/finance/budgets/{bid}", headers=H)
    ok(r.status_code == 200, f"DELETE budget 200 (got {r.status_code})")

    print(f"\n{'='*54}\n  RESULT — PASS {P}  |  FAIL {F}\n{'='*54}")


if __name__ == "__main__":
    main()
