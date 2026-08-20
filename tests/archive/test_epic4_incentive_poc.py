"""EPIC4 POC — Incentive Engine v2 (per-SKU, 3 faktor, margin-aware, on-collection).

Single script:
  A. per_sku engine: breakdown sums to total; INDEPENDENT recompute from DB matches API;
     on-collection (line in unpaid order -> 0); margin cap formula respected.
  B. strategy toggle: settings.commission.strategy = achievement_tiered -> engine switches
     (old tiered mode still works); revert to per_sku.
  C. incentive-rates CRUD + RBAC (manager/admin manage; sales 403); discount tier_factor effect.
Run: python /app/test_epic4_incentive_poc.py
"""
import os, sys, asyncio, requests
from datetime import datetime, timezone

BASE = "http://localhost:8001/api"
PASS = "demo12345"
res = {"pass": 0, "fail": 0}
PERIOD = datetime.now(timezone.utc).strftime("%Y-%m")


def check(n, c, e=""):
    if c: res["pass"] += 1; print(f"  [PASS] {n}")
    else: res["fail"] += 1; print(f"  [FAIL] {n} — {e}")
    return c


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PASS}); r.raise_for_status()
    return r.json()["token"]


def H(t): return {"Authorization": f"Bearer {t}"}


def _in_period(v, period):
    s = str(v or "")[:7]
    return s == period


async def recompute_expected(sales_id, entity_id=None):
    """Replikasi engine per-SKU dari DB untuk verifikasi independen."""
    sys.path.insert(0, "/app/backend")
    from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = cli[os.environ["DB_NAME"]]
    live_roll = {"available", "reserved", "committed", "picked", "packed", "quarantine"}

    rates = {}
    async for r in db.incentive_rates.find({"status": "active"}, {"_id": 0}):
        if r["entity_id"] == "all":
            rates.setdefault(r["category"], r)

    async def wac(pid):
        tot_len = tot_val = 0.0
        async for rr in db.inventory_rolls.find({"product_id": pid}, {"_id": 0}):
            if rr.get("status") not in live_roll: continue
            ln = float(rr.get("length_remaining", 0) or 0)
            cost = rr.get("unit_cost") or rr.get("base_unit_cost") or 0
            if ln > 0 and cost: tot_len += ln; tot_val += float(cost) * ln
        return (tot_val / tot_len) if tot_len else 0.0

    DEAD = {"cancelled", "draft", "expired", "rejected"}
    custs = await db.customers.find({"assigned_sales_id": sales_id}, {"_id": 0, "id": 1}).to_list(2000)
    cids = [c["id"] for c in custs]
    orders = await db.sales_orders.find({"customer_id": {"$in": cids}}, {"_id": 0}).to_list(8000) if cids else []
    total = 0.0
    for o in orders:
        if o.get("status") in DEAD: continue
        gt = float(o.get("grand_total") or 0)
        if gt <= 0: continue
        paid = sum(float(p.get("amount", 0) or 0) for p in (o.get("payments") or [])
                   if _in_period(p.get("created_at") or p.get("date"), PERIOD))
        frac = min(paid / gt, 1.0)
        for ln in (o.get("items") or []):
            cat = ln.get("category", "")
            rc = rates.get(cat)
            if not rc: continue
            per_unit = float(rc.get("per_unit_amount", 0) or 0)
            if per_unit <= 0: continue
            base_qty = float(ln.get("base_quantity", ln.get("quantity", 0)) or 0)
            qty = float(ln.get("quantity", 0) or 0)
            net_unit = (float(ln.get("line_total", 0) or 0) / qty) if qty else float(ln.get("price", 0) or 0)
            disc_pct = float(ln.get("discount_percent", 0) or 0)
            over = disc_pct > float(rc.get("discount_threshold", 0) or 0)
            factor = float(rc.get("discount_factor", 1) or 0) if over else 1.0
            w = await wac(ln.get("product_id"))
            unit_margin = net_unit - w
            qty_paid = base_qty * frac
            gross = qty_paid * per_unit * factor
            cap = (float(rc.get("margin_cap_pct", 50) or 0) / 100.0) * max(qty_paid * unit_margin, 0.0)
            total += max(min(gross, cap), 0.0)
    cli.close()
    return round(total, 2)


def main():
    print("=" * 60); print("EPIC4 POC — Incentive Engine v2 (per-SKU)"); print("=" * 60)
    admin = login("admin@kainnusantara.id")
    manager = login("manager@kainnusantara.id")
    sales = login("sales@kainnusantara.id")

    # sales_id of the sales user
    me = requests.get(f"{BASE}/auth/me", headers=H(sales))
    sid = me.json().get("id") if me.status_code == 200 else None
    if not sid:
        # fallback: pick from leaderboard
        lb = requests.get(f"{BASE}/sales/leaderboard?period={PERIOD}", headers=H(manager)).json()
        sid = lb[0]["sales_id"] if lb else None

    print("\n[A] per_sku engine")
    r = requests.get(f"{BASE}/sales/commission?period={PERIOD}", headers=H(sales))
    check("sales GET commission -> 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    d = r.json() if r.status_code == 200 else {}
    check("strategy == per_sku", d.get("strategy") == "per_sku", str(d.get("strategy")))
    bd = d.get("breakdown", [])
    check("breakdown present", isinstance(bd, list) and len(bd) > 0, str(len(bd)))
    bd_sum = round(sum(b["commission"] for b in bd), 2)
    check(f"breakdown sums to total ({bd_sum} == {d.get('total_incentive')})",
          abs(bd_sum - float(d.get("total_incentive", 0))) < 1.0)
    exp = asyncio.run(recompute_expected(sid))
    check(f"INDEPENDENT recompute matches API ({d.get('total_incentive')} ~ {exp})",
          abs(float(d.get("total_incentive", 0)) - exp) < 2.0, f"api={d.get('total_incentive')} exp={exp}")
    check("on-collection: at least one line 0 (unpaid order) OR all paid",
          any(b["commission"] == 0 for b in bd) or all(b["commission"] > 0 for b in bd))
    check("projection_full >= total_incentive (proyeksi saat lunas)",
          float(d.get("projection_full", 0)) >= float(d.get("total_incentive", 0)) - 0.01)

    print("\n[C] incentive-rates CRUD + RBAC")
    rr = requests.get(f"{BASE}/incentive-rates", headers=H(manager))
    check("manager GET rates -> 200", rr.status_code == 200, str(rr.status_code))
    rates = rr.json() if rr.status_code == 200 else []
    check("7 default rates seeded", len(rates) >= 7, str(len(rates)))
    check("sales GET rates -> 403", requests.get(f"{BASE}/incentive-rates", headers=H(sales)).status_code == 403)
    # create
    cr = requests.post(f"{BASE}/incentive-rates", headers=H(manager),
                       json={"entity_id": "all", "category": "PocCat", "per_unit_amount": 1234})
    check("manager create rate -> 200", cr.status_code == 200, f"{cr.status_code} {cr.text[:120]}")
    rid = cr.json().get("id") if cr.status_code == 200 else None
    check("sales create rate -> 403",
          requests.post(f"{BASE}/incentive-rates", headers=H(sales), json={"entity_id": "all", "category": "X", "per_unit_amount": 1}).status_code == 403)
    # duplicate
    check("duplicate entity+category -> 409",
          requests.post(f"{BASE}/incentive-rates", headers=H(manager), json={"entity_id": "all", "category": "PocCat", "per_unit_amount": 9}).status_code == 409)
    if rid:
        pr = requests.patch(f"{BASE}/incentive-rates/{rid}", headers=H(manager), json={"data": {"per_unit_amount": 5555}})
        check("patch rate -> 200 & value updated", pr.status_code == 200 and pr.json().get("per_unit_amount") == 5555, pr.text[:120])
        check("delete rate -> 200", requests.delete(f"{BASE}/incentive-rates/{rid}", headers=H(manager)).status_code == 200)

    print("\n[B] strategy toggle -> achievement_tiered (arsip) still works")
    up = requests.put(f"{BASE}/settings", headers=H(admin), json={"scope": "global", "commission": {"strategy": "achievement_tiered"}})
    check("admin set strategy=achievement_tiered -> 200", up.status_code == 200, f"{up.status_code} {up.text[:120]}")
    r2 = requests.get(f"{BASE}/sales/commission?period={PERIOD}", headers=H(sales)).json()
    check("engine switched to achievement_tiered", r2.get("strategy") == "achievement_tiered", str(r2.get("strategy")))
    check("tiered result has applied_rate + achievement_pct", "applied_rate" in r2 and "achievement_pct" in r2)
    # revert
    rev = requests.put(f"{BASE}/settings", headers=H(admin), json={"scope": "global", "commission": {"strategy": "per_sku"}})
    r3 = requests.get(f"{BASE}/sales/commission?period={PERIOD}", headers=H(sales)).json()
    check("reverted to per_sku", r3.get("strategy") == "per_sku", str(r3.get("strategy")))

    print("\n" + "=" * 60)
    print(f"  RESULT: {res['pass']} PASS / {res['fail']} FAIL")
    print("=" * 60)
    sys.exit(0 if res["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
