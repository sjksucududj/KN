"""POC — CRM / Sales Force (KN_17 CRM-lite).

Memvalidasi DERIVASI (kode menang) + endpoint CRM:
  1. compute_customer_credit  (AR/overdue/status active|warning|blocked)
  2. check_credit_for_order    (gate kredit saat SO)
  3. customer_360              (riwayat order/dokumen/special price + stats)
  4. Row-level scoping         (sales hanya customer miliknya) via API
  5. sales_kpi                 (penjualan/pencairan/collection_rate/AR/new)
  6. compute_commission        (pencairan + tiered)
  7. collection_worklist       (tagihan jatuh tempo)
  8. Endpoints: 360, reassign, credit-override request+decision, targets, kpi

Jalankan: python test_crm_poc.py
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


async def login(client, email, password="demo12345"):
    r = await client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"]


async def main():
    client_db = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client_db[os.environ["DB_NAME"]]

    # import services AFTER db env loaded (service uses backend.db singleton)
    from services.customer_service import (
        compute_customer_credit, check_credit_for_order, customer_360,
        scope_query, collection_worklist,
    )
    from services.sales_force_service import sales_kpi, compute_commission, leaderboard

    SBX_SALES = "user_poc_sales"
    SBX_CUST = "cust_poc_crm"
    sandbox_orders = ["so_poc_a", "so_poc_b", "so_poc_c"]

    print("\n── Setup sandbox ─────────────────────────────────────────")
    await db.users.delete_many({"id": SBX_SALES})
    await db.customers.delete_many({"id": SBX_CUST})
    await db.sales_orders.delete_many({"id": {"$in": sandbox_orders}})
    await db.credit_overrides.delete_many({"customer_id": SBX_CUST})

    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    await db.users.insert_one({
        "id": SBX_SALES, "name": "POC Sales", "email": "pocsales@kn.id", "role": "sales",
        "password_hash": pwd.hash("demo12345"), "status": "active", "created_at": iso_ago(120),
    })
    await db.customers.insert_one({
        "id": SBX_CUST, "code": "CUST-POC", "name": "POC Customer CRM", "pic_name": "Pak POC",
        "phone": "0811", "email": "poc@kn.id", "type": "Wholesale", "city": "Jakarta",
        "entity_id": "ent_ksc", "assigned_sales_id": SBX_SALES, "assigned_sales_name": "POC Sales",
        "segment": "Wholesale", "tags": ["poc"], "credit_limit": 100_000_000,
        "payment_profile": {"allowed_methods": ["tempo"], "default_method": "tempo", "term_days": 30},
        "status": "active", "created_at": iso_ago(100),
    })
    # SO-A: 40jt, 60 hari lalu, pending, term 30 -> overdue ~30 hari, outstanding 40jt
    await db.sales_orders.insert_one({
        "id": "so_poc_a", "number": "SO-POCA", "customer_id": SBX_CUST, "customer_name": "POC Customer CRM",
        "status": "confirmed", "payment_status": "pending", "grand_total": 40_000_000, "total_amount": 40_000_000,
        "payments": [], "created_at": iso_ago(60), "sales_name": "POC Sales", "entity_id": "ent_ksc",
    })
    # SO-B: 30jt, 5 hari lalu, pending, sudah bayar 10jt -> outstanding 20jt (belum overdue)
    await db.sales_orders.insert_one({
        "id": "so_poc_b", "number": "SO-POCB", "customer_id": SBX_CUST, "customer_name": "POC Customer CRM",
        "status": "confirmed", "payment_status": "paid_partial", "grand_total": 30_000_000, "total_amount": 30_000_000,
        "payments": [{"amount": 10_000_000, "created_at": iso_ago(3)}], "created_at": iso_ago(5),
        "sales_name": "POC Sales", "entity_id": "ent_ksc",
    })
    # SO-C: 20jt, lunas -> tidak dihitung AR
    await db.sales_orders.insert_one({
        "id": "so_poc_c", "number": "SO-POCC", "customer_id": SBX_CUST, "customer_name": "POC Customer CRM",
        "status": "done", "payment_status": "paid", "grand_total": 20_000_000, "total_amount": 20_000_000,
        "payments": [{"amount": 20_000_000, "created_at": iso_ago(40)}], "created_at": iso_ago(70),
        "entity_id": "ent_ksc",
    })

    cust = await db.customers.find_one({"id": SBX_CUST}, {"_id": 0})

    # ── 1. Credit derivation ──────────────────────────────────────
    print("\n── 1. compute_customer_credit ────────────────────────────")
    credit = await compute_customer_credit(cust)
    check("AR outstanding = 60jt (40 + 20)", abs(credit["ar_outstanding"] - 60_000_000) < 1, credit)
    check("overdue = 40jt (SO-A lewat jatuh tempo)", abs(credit["overdue_amount"] - 40_000_000) < 1, credit)
    check("max_overdue_days > 14", credit["max_overdue_days"] > 14, credit)
    check("status = blocked (overdue berat > 14 hari)", credit["status"] == "blocked", credit)
    check("available_credit = 40jt", abs((credit["available_credit"] or 0) - 40_000_000) < 1, credit)

    # Warning scenario: naikkan limit, hapus overdue (ubah SO-A jadi baru)
    await db.sales_orders.update_one({"id": "so_poc_a"}, {"$set": {"created_at": iso_ago(5)}})
    await db.customers.update_one({"id": SBX_CUST}, {"$set": {"credit_limit": 70_000_000}})
    cust2 = await db.customers.find_one({"id": SBX_CUST}, {"_id": 0})
    credit2 = await compute_customer_credit(cust2)
    check("tanpa overdue + ar(60jt) >= 80% limit(70jt) -> warning", credit2["status"] == "warning", credit2)

    # ── 2. check_credit_for_order ─────────────────────────────────
    print("\n── 2. check_credit_for_order (gate SO) ───────────────────")
    gate_ok = await check_credit_for_order(cust2, 5_000_000)     # 60+5=65 < 70 -> allowed (warning)
    check("order 5jt -> allowed (proyeksi < limit)", gate_ok["allowed"] is True, gate_ok["level"])
    gate_block = await check_credit_for_order(cust2, 30_000_000)  # 60+30=90 > 70 -> blocked
    check("order 30jt -> blocked (proyeksi > limit)", gate_block["allowed"] is False, gate_block["level"])
    check("blocked menyertakan alasan", len(gate_block["reasons"]) > 0, gate_block["reasons"])

    # ── 3. customer_360 ───────────────────────────────────────────
    print("\n── 3. customer_360 ───────────────────────────────────────")
    c360 = await customer_360(SBX_CUST)
    check("360 ada order_history 3", len(c360["order_history"]) == 3, len(c360["order_history"]))
    check("360 ada credit object", c360.get("credit", {}).get("status") in ("active", "warning", "blocked"))
    check("360 lifetime_value = 90jt", abs(c360["stats"]["lifetime_value"] - 90_000_000) < 1, c360["stats"])
    check("360 punya assigned_sales_name", c360.get("assigned_sales_name") == "POC Sales")

    # ── 4. Row-level scoping (API) ────────────────────────────────
    print("\n── 4. Row-level scoping (API) ────────────────────────────")
    sq = scope_query({"role": "sales", "id": SBX_SALES})
    check("scope_query sales -> filter assigned_sales_id", sq.get("assigned_sales_id") == SBX_SALES, sq)
    sq_admin = scope_query({"role": "admin", "id": "x"})
    check("scope_query admin -> tanpa filter sales", "assigned_sales_id" not in sq_admin, sq_admin)

    async with httpx.AsyncClient(timeout=40) as http:
        tok_admin = await login(http, "admin@kainnusantara.id")
        tok_ayu = await login(http, "sales@kainnusantara.id")     # user_sales_01
        tok_mgr = await login(http, "manager@kainnusantara.id")

        H_admin = {"Authorization": f"Bearer {tok_admin}"}
        H_ayu = {"Authorization": f"Bearer {tok_ayu}"}
        H_mgr = {"Authorization": f"Bearer {tok_mgr}"}

        all_cust = (await http.get(f"{BASE}/customers", headers=H_admin)).json()
        ayu_cust = (await http.get(f"{BASE}/customers", headers=H_ayu)).json()
        check("admin lihat >= 5 customer", len(all_cust) >= 5, len(all_cust))
        check("sales(Ayu) hanya lihat customer miliknya", len(ayu_cust) >= 1 and len(ayu_cust) < len(all_cust),
              f"ayu={len(ayu_cust)} all={len(all_cust)}")
        check("semua customer Ayu assigned ke user_sales_01",
              all(c.get("assigned_sales_id") == "user_sales_01" for c in ayu_cust), ayu_cust[:1])
        check("customer punya credit.status (enriched)",
              all("credit" in c for c in ayu_cust))

        # Ayu tak boleh akses 360 customer milik orang lain (POC customer milik SBX_SALES)
        r403 = await http.get(f"{BASE}/customers/{SBX_CUST}/360", headers=H_ayu)
        check("Ayu akses 360 customer bukan miliknya -> 403", r403.status_code == 403, r403.status_code)
        r200 = await http.get(f"{BASE}/customers/{SBX_CUST}/360", headers=H_admin)
        check("admin akses 360 -> 200", r200.status_code == 200, r200.status_code)

        # ── 5. sales_kpi ──────────────────────────────────────────
        print("\n── 5. sales_kpi (derived) ────────────────────────────")
        kpi = await sales_kpi("user_sales_01", entity_id=None)
        check("KPI punya total_sales & total_collected", "total_sales" in kpi and "total_collected" in kpi, kpi)
        check("KPI collection_rate 0..>=0", kpi["collection_rate"] >= 0, kpi["collection_rate"])
        check("KPI customers_count = 2 (Ayu)", kpi["customers_count"] == 2, kpi["customers_count"])

        # KPI via API (sales lihat dirinya)
        kpi_api = (await http.get(f"{BASE}/sales/kpi", headers=H_ayu)).json()
        check("API /sales/kpi (sales) -> sales_id dipaksa dirinya", kpi_api["sales_id"] == "user_sales_01", kpi_api.get("sales_id"))

        # ── 6. compute_commission ─────────────────────────────────
        print("\n── 6. compute_commission (pencairan + tiered) ────────")
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        comm = await compute_commission("user_sales_01", period)
        check("komisi basis = collection", comm["basis"] == "collection", comm["basis"])
        check("komisi punya achievement_pct & applied_rate", "achievement_pct" in comm and "applied_rate" in comm, comm)
        check("total_incentive >= 0", comm["total_incentive"] >= 0, comm["total_incentive"])

        # tiered: cek pick rate naik saat achievement naik
        from services.sales_force_service import pick_tier_rate, DEFAULT_TIERS
        check("tier rate@50% < rate@110%", pick_tier_rate(DEFAULT_TIERS, 50) < pick_tier_rate(DEFAULT_TIERS, 110))

        # ── 7. collection_worklist ────────────────────────────────
        print("\n── 7. collection_worklist ────────────────────────────")
        wl = await collection_worklist({"role": "sales", "id": SBX_SALES})
        check("worklist berisi tagihan POC customer", any(r["customer_id"] == SBX_CUST for r in wl), len(wl))
        check("worklist urut days_late desc", all(wl[i]["days_late"] >= wl[i+1]["days_late"] for i in range(len(wl)-1)) if len(wl) > 1 else True)

        # ── 8. Endpoints: reassign, credit-override, targets ──────
        print("\n── 8. CRM endpoints (reassign/override/targets) ──────")
        # reassign POC customer ke user_sales_01 (manager)
        rr = await http.post(f"{BASE}/customers/{SBX_CUST}/reassign", headers=H_mgr,
                             json={"assigned_sales_id": "user_sales_01", "reason": "poc"})
        check("reassign (manager) -> 200", rr.status_code == 200, rr.text[:120])
        check("reassign mengubah assigned_sales_id", rr.json().get("assigned_sales_id") == "user_sales_01")
        # balikkan
        await db.customers.update_one({"id": SBX_CUST}, {"$set": {"assigned_sales_id": SBX_SALES}})

        # credit override request (Ayu now owns? no — owned by SBX). Use admin request path via sales? 
        # Ayu owns toko_kain -> request override utk customer miliknya
        ayu_cid = next((c["id"] for c in ayu_cust if c.get("assigned_sales_id") == "user_sales_01"), None)
        co = await http.post(f"{BASE}/customers/{ayu_cid}/credit-override", headers=H_ayu,
                             json={"customer_id": ayu_cid, "amount": 5_000_000, "reason": "PO besar approved"})
        check("credit-override request (sales, customer sendiri) -> 200", co.status_code == 200, co.text[:120])
        ovr_id = co.json().get("id") if co.status_code == 200 else None
        if ovr_id:
            dec = await http.post(f"{BASE}/credit-overrides/{ovr_id}/decision", headers=H_mgr,
                                  json={"decision": "approve", "reason": "ok"})
            check("credit-override decision (manager) -> approved", dec.status_code == 200 and dec.json().get("status") == "approved", dec.text[:120])

        # sales target POST (manager) + GET
        tg = await http.post(f"{BASE}/sales-targets", headers=H_mgr,
                             json={"sales_id": "user_sales_01", "period": "2026-12",
                                   "target_sales_amount": 100_000_000, "target_collection_amount": 80_000_000})
        check("POST /sales-targets (manager) -> 200", tg.status_code == 200, tg.text[:120])
        tg_sales = await http.post(f"{BASE}/sales-targets", headers=H_ayu,
                                   json={"sales_id": "user_sales_01", "period": "2026-12", "target_sales_amount": 1})
        check("POST /sales-targets (sales) -> 403", tg_sales.status_code == 403, tg_sales.status_code)

        # leaderboard (manager)
        lb = await http.get(f"{BASE}/sales/leaderboard", headers=H_mgr)
        check("GET /sales/leaderboard (manager) -> list dgn rank", lb.status_code == 200 and isinstance(lb.json(), list) and len(lb.json()) >= 3, lb.status_code)
        lb_sales = await http.get(f"{BASE}/sales/leaderboard", headers=H_ayu)
        check("GET /sales/leaderboard (sales) -> 403", lb_sales.status_code == 403, lb_sales.status_code)

        # sales-users dropdown
        su = await http.get(f"{BASE}/sales-users", headers=H_admin)
        check("GET /sales-users -> >= 3 sales", su.status_code == 200 and len(su.json()) >= 3, su.status_code)

    # cleanup
    print("\n── Cleanup sandbox ───────────────────────────────────────")
    await db.users.delete_many({"id": SBX_SALES})
    await db.customers.delete_many({"id": SBX_CUST})
    await db.sales_orders.delete_many({"id": {"$in": sandbox_orders}})
    await db.credit_overrides.delete_many({"customer_id": SBX_CUST})
    await db.sales_targets.delete_many({"sales_id": "user_sales_01", "period": "2026-12"})
    print("  (sandbox dibersihkan)")
    client_db.close()

    print(f"\n  RESULT: {PASS} PASS / {FAIL} FAIL\n")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
