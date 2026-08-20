"""EPIC3 POC — Costing (WAC) + AR Receipt / Payment Application.

Single script, all cases:
  A. WAC: GET /api/costing/wac returns per-product wac/margin; sales BLOCKED (403);
     WAC math = weighted avg of roll cost; margin = price - wac.
  B. AR Receipt: list open orders; create receipt (auto-FIFO) -> SO payments[]/paid_total/
     payment_status updated; AR outstanding (credit gate) reduces by paid amount;
     explicit allocation; over-allocation rejected (400); RBAC view/create.
Run: python /app/test_epic3_costing_ar_poc.py
"""
import os, sys, asyncio, requests

BASE = "http://localhost:8001/api"
PASS = "demo12345"
res = {"pass": 0, "fail": 0}


def check(name, cond, extra=""):
    if cond:
        res["pass"] += 1; print(f"  [PASS] {name}")
    else:
        res["fail"] += 1; print(f"  [FAIL] {name} — {extra}")
    return cond


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PASS}); r.raise_for_status()
    return r.json()["token"]


def H(t): return {"Authorization": f"Bearer {t}"}


async def db_wac_expectation(product_id):
    sys.path.insert(0, "/app/backend")
    from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = cli[os.environ["DB_NAME"]]
    live = {"available", "reserved", "committed", "picked", "packed", "quarantine"}
    rolls = await db.inventory_rolls.find({"product_id": product_id}, {"_id": 0}).to_list(5000)
    tot_len = tot_val = 0.0
    for r in rolls:
        if r.get("status") not in live: continue
        ln = float(r.get("length_remaining", 0) or 0)
        cost = r.get("unit_cost") or r.get("base_unit_cost") or 0
        if ln > 0 and cost: tot_len += ln; tot_val += float(cost) * ln
    cli.close()
    return round(tot_val / tot_len, 2) if tot_len else 0.0


def main():
    print("=" * 60); print("EPIC3 POC — Costing WAC + AR Receipt"); print("=" * 60)
    admin = login("admin@kainnusantara.id")
    sales = login("sales@kainnusantara.id")
    manager = login("manager@kainnusantara.id")

    print("\n[A] Costing WAC")
    r = requests.get(f"{BASE}/costing/wac", headers=H(admin))
    check("admin GET /costing/wac -> 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    wac_list = r.json() if r.status_code == 200 else []
    check("returns array of products", isinstance(wac_list, list) and len(wac_list) > 0, str(type(wac_list)))
    sample = next((w for w in wac_list if w.get("wac", 0) > 0), wac_list[0] if wac_list else {})
    check("WAC item has wac/price/margin_amount/margin_pct/source",
          all(k in sample for k in ("wac", "price", "margin_amount", "margin_pct", "source")), str(sample))
    if sample:
        exp = asyncio.run(db_wac_expectation(sample["product_id"]))
        check(f"WAC math matches roll weighted-avg ({sample['name'][:20]}: api={sample['wac']} exp={exp})",
              abs(sample["wac"] - exp) < 1.0, f"api={sample['wac']} exp={exp}")
        if sample.get("wac", 0) > 0:
            check("margin_amount == price - wac",
                  abs((sample["margin_amount"] or 0) - (sample["price"] - sample["wac"])) < 0.5, str(sample))

    check("manager GET /costing/wac -> 200 (allowed)", requests.get(f"{BASE}/costing/wac", headers=H(manager)).status_code == 200)
    sc = requests.get(f"{BASE}/costing/wac", headers=H(sales)).status_code
    check("sales GET /costing/wac -> 403 (HPP hidden)", sc == 403, f"got {sc}")

    print("\n[B] AR Receipt / Payment Application")
    # find a customer with open AR orders
    customers = requests.get(f"{BASE}/customers", headers=H(admin)).json()
    target = None; open_orders = []
    for c in customers:
        oo = requests.get(f"{BASE}/ar-receipts/open-orders", headers=H(admin), params={"customer_id": c["id"]}).json()
        if isinstance(oo, list) and oo:
            target = c; open_orders = oo; break
    check("found customer with open AR orders", target is not None and len(open_orders) > 0)
    if not target:
        print("\nRESULT:", res); sys.exit(1 if res["fail"] else 0)

    o0 = open_orders[0]
    out_before = o0["outstanding"]
    print(f"   customer={target['name']} order={o0['number']} outstanding={out_before}")

    # AR outstanding from credit gate BEFORE
    def credit_outstanding(cid):
        cr = requests.get(f"{BASE}/customers/{cid}/credit-status", headers=H(admin))
        if cr.status_code != 200:
            cr = requests.get(f"{BASE}/customers/{cid}", headers=H(admin))
        j = cr.json()
        return j.get("ar_outstanding", j.get("outstanding"))
    ar_before = credit_outstanding(target["id"])

    pay = round(out_before * 0.4, -2) or 100000
    # explicit allocation to o0
    r = requests.post(f"{BASE}/ar-receipts", headers=H(admin), json={
        "customer_id": target["id"], "amount": pay, "method": "transfer",
        "allocations": [{"order_id": o0["order_id"], "amount": pay}]})
    check("admin create receipt (explicit alloc) -> 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    receipt = r.json() if r.status_code == 200 else {}
    check("receipt punya nomor AR (opsional prefix entitas)", "AR-" in str(receipt.get("number", "")), str(receipt.get("number")))
    check("receipt applied_total == amount", abs(receipt.get("applied_total", -1) - pay) < 0.5, str(receipt.get("applied_total")))

    # order outstanding reduced
    oo2 = requests.get(f"{BASE}/ar-receipts/open-orders", headers=H(admin), params={"customer_id": target["id"]}).json()
    row = next((x for x in oo2 if x["order_id"] == o0["order_id"]), None)
    new_out = row["outstanding"] if row else 0.0
    check(f"order outstanding reduced by payment ({out_before} -> {new_out})",
          abs((out_before - pay) - new_out) < 1.0, f"expected {out_before - pay} got {new_out}")
    if row:
        check("order payment_status = partial", row["payment_status"] == "partial", str(row["payment_status"]))

    # credit gate AR reduced
    ar_after = credit_outstanding(target["id"])
    if ar_before is not None and ar_after is not None:
        check(f"credit gate AR outstanding reduced ({ar_before} -> {ar_after})",
              abs((ar_before - pay) - ar_after) < 2.0, f"expected {ar_before - pay} got {ar_after}")

    # over-allocation rejected
    r = requests.post(f"{BASE}/ar-receipts", headers=H(admin), json={
        "customer_id": target["id"], "amount": 10**12, "method": "transfer",
        "allocations": [{"order_id": o0["order_id"], "amount": 10**12}]})
    check("over-allocation -> 400", r.status_code == 400, f"got {r.status_code}")

    # RBAC: sales can view+create receipts; warehouse cannot create
    check("sales GET /ar-receipts -> 200", requests.get(f"{BASE}/ar-receipts", headers=H(sales)).status_code == 200)
    wh = login("warehouse@kainnusantara.id")
    sc = requests.post(f"{BASE}/ar-receipts", headers=H(wh), json={"customer_id": target["id"], "amount": 1000}).status_code
    check("warehouse create receipt -> 403", sc == 403, f"got {sc}")

    # list receipts contains our new one
    lst = requests.get(f"{BASE}/ar-receipts", headers=H(admin), params={"customer_id": target["id"]}).json()
    check("receipt appears in list", any(x.get("id") == receipt.get("id") for x in lst))

    print("\n" + "=" * 60)
    print(f"  RESULT: {res['pass']} PASS / {res['fail']} FAIL")
    print("=" * 60)
    sys.exit(0 if res["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
