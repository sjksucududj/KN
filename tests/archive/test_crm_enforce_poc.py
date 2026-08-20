"""POC — CRM enforcement lanjutan (sesi #047).

1. Gate kredit di POST /sales-orders (1b blocked->409 ; override approved->bypass ; 2a warning->lolos)
2. GET /customers/{id}/credit-status (preview)
3. Collection reminders (GET /collection-reminders) + mark (POST /collection-reminders/mark)
4. Komisi multi-periode (bulan/kuartal/tahun) + GET /sales/commission-history

Jalankan: python test_crm_enforce_poc.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
load_dotenv(os.path.join(os.path.dirname(__file__), "backend", ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE = "http://localhost:8001/api"
PASS = 0
FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} {extra}")


def iso_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


async def login(c, email, pw="demo12345"):
    r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return r.json()["token"]


async def main():
    cdb = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cdb[os.environ["DB_NAME"]]
    from services.customer_service import evaluate_credit_gate, collection_reminders
    from services.sales_force_service import sales_kpi, compute_commission, commission_history, _in_period

    CUST = "cust_enf_poc"
    ORD = "so_enf_open"
    SALES = "user_sales_01"

    print("\n── Setup ─────────────────────────────────────────────────")
    await db.customers.delete_many({"id": CUST})
    await db.sales_orders.delete_many({"id": {"$in": [ORD]}})
    await db.credit_overrides.delete_many({"customer_id": CUST})
    await db.collection_followups.delete_many({"customer_id": CUST})

    products = await db.products.find({}, {"_id": 0, "id": 1, "base_unit": 1, "price": 1}).to_list(10)
    prod = products[0]

    # Customer dgn limit kecil + 1 order outstanding besar -> blocked (AR >= limit)
    await db.customers.insert_one({
        "id": CUST, "code": "CUST-ENF", "name": "Enforce POC Customer", "pic_name": "Pak Enf",
        "phone": "0811", "city": "Jakarta", "entity_id": "ent_ksc",
        "assigned_sales_id": SALES, "assigned_sales_name": "Ayu Permatasari", "segment": "Wholesale",
        "credit_limit": 5_000_000, "status": "active",
        "payment_profile": {"default_method": "tempo", "term_days": 30, "allowed_methods": ["tempo"]},
        "addresses": [{"id": "addr_enf", "recipient_name": "Pak Enf", "phone": "0811",
                       "city": "Jakarta", "address": "Jl. POC 1", "is_primary": True}],
        "created_at": iso_ago(40),
    })
    # order outstanding 20jt, 60 hari lalu (overdue) -> blocked
    await db.sales_orders.insert_one({
        "id": ORD, "number": "SO-ENF1", "customer_id": CUST, "customer_name": "Enforce POC Customer",
        "status": "confirmed", "payment_status": "pending", "grand_total": 20_000_000, "total_amount": 20_000_000,
        "payments": [], "created_at": iso_ago(60), "sales_name": "Ayu Permatasari", "entity_id": "ent_ksc",
    })
    cust = await db.customers.find_one({"id": CUST}, {"_id": 0})

    # ── 1. Gate kredit (service + API SO) ─────────────────────────
    print("\n── 1. Gate kredit di pembuatan SO ────────────────────────")
    gate = await evaluate_credit_gate(cust, 1_000_000)
    check("evaluate_credit_gate -> blocked", gate["blocked"] is True, gate["level"])
    check("blocked tanpa override -> override None", gate["override"] is None)

    async with httpx.AsyncClient(timeout=40) as http:
        tok_admin = await login(http, "admin@kainnusantara.id")
        tok_mgr = await login(http, "manager@kainnusantara.id")
        H = {"Authorization": f"Bearer {tok_admin}"}
        Hm = {"Authorization": f"Bearer {tok_mgr}"}

        so_body = {"customer_id": CUST, "shipping_address_id": "addr_enf",
                   "items": [{"product_id": prod["id"], "quantity": 1, "unit": prod.get("base_unit", "meter")}]}
        r = await http.post(f"{BASE}/sales-orders", headers=H, json=so_body)
        check("POST /sales-orders customer blocked -> 409", r.status_code == 409, r.status_code)
        det = (r.json() or {}).get("detail", {}) if r.status_code == 409 else {}
        code = det.get("code") if isinstance(det, dict) else None
        check("error code = CREDIT_BLOCKED", code == "CREDIT_BLOCKED", det)

        # credit-status preview
        cs = await http.get(f"{BASE}/customers/{CUST}/credit-status", headers=H, params={"amount": 1_000_000})
        check("GET /credit-status -> blocked True", cs.status_code == 200 and cs.json().get("blocked") is True, cs.text[:120])

        # ── override approved -> bypass ───────────────────────────
        print("\n── 1b. Override approved -> bypass blokir ────────────")
        co = await http.post(f"{BASE}/customers/{CUST}/credit-override", headers=H,
                             json={"customer_id": CUST, "amount": 0, "reason": "PO besar approved"})
        ovr_id = co.json()["id"]
        await http.post(f"{BASE}/credit-overrides/{ovr_id}/decision", headers=Hm, json={"decision": "approve", "reason": "ok"})
        gate2 = await evaluate_credit_gate(await db.customers.find_one({"id": CUST}, {"_id": 0}), 1_000_000)
        check("evaluate_credit_gate -> override ditemukan", gate2["override"] is not None)
        r2 = await http.post(f"{BASE}/sales-orders", headers=H, json=so_body)
        blocked_again = (r2.status_code == 409 and isinstance((r2.json() or {}).get("detail"), dict)
                         and r2.json()["detail"].get("code") == "CREDIT_BLOCKED")
        check("POST /sales-orders dgn override -> TIDAK CREDIT_BLOCKED", not blocked_again, r2.status_code)
        if r2.status_code in (200, 201):
            ov_after = await db.credit_overrides.find_one({"id": ovr_id}, {"_id": 0})
            check("override dikonsumsi setelah SO sukses", ov_after.get("consumed") is True, ov_after.get("consumed"))
            await db.sales_orders.delete_many({"customer_id": CUST, "id": {"$ne": ORD}})
        else:
            print(f"    (SO tidak tercipta penuh: {r2.status_code} — gate sudah lolos, cukup utk POC)")

        # ── warning -> lolos (2a) ─────────────────────────────────
        print("\n── 1c. Warning -> lolos dgn flag (2a) ────────────────")
        # naikkan limit -> AR(20jt) ~ < limit tapi overdue ada -> warning
        await db.customers.update_one({"id": CUST}, {"$set": {"credit_limit": 100_000_000}})
        await db.sales_orders.update_one({"id": ORD}, {"$set": {"created_at": iso_ago(5)}})  # hilangkan overdue
        gate3 = await evaluate_credit_gate(await db.customers.find_one({"id": CUST}, {"_id": 0}), 1_000_000)
        check("warning/ok -> tidak blocked", gate3["blocked"] is False, gate3["level"])

        # ── 3. Collection reminders + mark ────────────────────────
        print("\n── 3. Collection reminders + mark ────────────────────")
        await db.sales_orders.update_one({"id": ORD}, {"$set": {"created_at": iso_ago(60)}})  # overdue lagi
        rem = await http.get(f"{BASE}/collection-reminders", headers=Hm, params={"days_ahead": 7})
        rows = rem.json() if rem.status_code == 200 else []
        mine = [x for x in rows if x["customer_id"] == CUST]
        check("GET /collection-reminders memuat order overdue", len(mine) >= 1, len(rows))
        if mine:
            check("reminder punya flag reminded/overdue", "reminded" in mine[0] and "overdue" in mine[0], mine[0])
            mk = await http.post(f"{BASE}/collection-reminders/mark", headers=Hm,
                                 json={"customer_id": CUST, "order_id": ORD, "note": "diingatkan via telp"})
            check("POST /collection-reminders/mark -> 200", mk.status_code == 200, mk.text[:120])
            rem2 = await http.get(f"{BASE}/collection-reminders", headers=Hm, params={"days_ahead": 7})
            mine2 = [x for x in rem2.json() if x["customer_id"] == CUST]
            check("setelah mark -> reminded True", mine2 and mine2[0]["reminded"] is True, mine2[:1])

        # ── 4. Komisi multi-periode ───────────────────────────────
        print("\n── 4. Komisi multi-periode (bulan/kuartal/tahun) ─────")
        now = datetime.now(timezone.utc)
        month = now.strftime("%Y-%m")
        quarter = f"{now.year}-Q{(now.month - 1)//3 + 1}"
        year = now.strftime("%Y")
        check("_in_period bulan cocok", _in_period(now.isoformat(), month) is True)
        check("_in_period kuartal cocok", _in_period(now.isoformat(), quarter) is True, quarter)
        check("_in_period tahun cocok", _in_period(now.isoformat(), year) is True)
        check("_in_period bulan lain tidak cocok", _in_period("2020-01-01", month) is False)

        k_m = await sales_kpi(SALES, month)
        k_q = await sales_kpi(SALES, quarter)
        k_y = await sales_kpi(SALES, year)
        check("KPI tahun >= kuartal >= bulan (penjualan)", k_y["total_sales"] >= k_q["total_sales"] >= k_m["total_sales"],
              f"y={k_y['total_sales']} q={k_q['total_sales']} m={k_m['total_sales']}")

        comm_q = await compute_commission(SALES, quarter)
        check("komisi kuartal terhitung (achievement+rate)", "achievement_pct" in comm_q and comm_q["total_incentive"] >= 0, comm_q)

        hist = await http.get(f"{BASE}/sales/commission-history", headers=Hm,
                              params={"sales_id": SALES, "period_type": "month", "count": 4})
        hrows = hist.json() if hist.status_code == 200 else []
        check("GET /sales/commission-history -> 4 periode kronologis", len(hrows) == 4, len(hrows))
        check("history tiap baris punya total_incentive", all("total_incentive" in r for r in hrows) if hrows else False)
        hist_q = await http.get(f"{BASE}/sales/commission-history", headers=Hm,
                                params={"sales_id": SALES, "period_type": "quarter", "count": 3})
        check("history kuartal -> 3 periode", hist_q.status_code == 200 and len(hist_q.json()) == 3, hist_q.status_code)

    print("\n── Cleanup ───────────────────────────────────────────────")
    await db.customers.delete_many({"id": CUST})
    await db.sales_orders.delete_many({"id": {"$in": [ORD]}})
    await db.sales_orders.delete_many({"customer_id": CUST})
    await db.credit_overrides.delete_many({"customer_id": CUST})
    await db.collection_followups.delete_many({"customer_id": CUST})
    print("  (bersih)")
    cdb.close()
    print(f"\n  RESULT: {PASS} PASS / {FAIL} FAIL\n")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
