"""R5.6 — Laporan Margin per-PT + pecahan Landed Cost — POC.

Membuktikan:
  A. /api/finance/profitability mengembalikan dimensi baru **by_entity** (per-PT).
  B. Setiap baris memiliki pecahan COGS: cogs_base + cogs_landed == cogs (Total COGS).
  C. Setelah landed cost diterapkan ke produk yang terjual, cogs_landed > 0 pada dimensi terkait
     (produk/PT) dan tercermin di totals (landed_included True).
  D. Konsistensi: Σ margin per-PT == totals.margin (dalam toleransi rounding).

Catatan: memodifikasi cost roll (landed) → seed ulang setelahnya.
"""
import os
import sys
import asyncio
import requests

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

API = f"{os.environ.get('R5_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  \u2705 {name}")
    else:
        FAIL += 1; print(f"  \u274c {name}  {extra}")


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def apply_landed_to_sold_product():
    """Terapkan landed ke satu produk yang muncul di SO 'sold', kembalikan (pid, entity)."""
    from db import db
    from services import landed_cost_service, costing_service
    SOLD = ["confirmed", "reserved", "partially_shipped", "shipped", "done"]
    orders = await db.sales_orders.find({"status": {"$in": SOLD}}, {"_id": 0}).to_list(50000)
    LIVE = ["available", "reserved", "committed", "picked", "packed", "quarantine"]
    for o in orders:
        ent = o.get("entity_id")
        for it in (o.get("items") or []):
            pid = it.get("product_id")
            if not pid:
                continue
            rolls = await db.inventory_rolls.find(
                {"product_id": pid, "status": {"$in": LIVE},
                 "base_unit_cost": {"$gt": 0}, "length_initial": {"$gt": 0}}, {"_id": 0}).to_list(5000)
            if rolls:
                base_value = sum(float(r.get("base_unit_cost", 0) or 0) * float(r.get("length_initial", 0) or 0)
                                 for r in rolls)
                alloc = landed_cost_service.compute_allocation(rolls, round(0.25 * base_value, 2), basis="value")
                await landed_cost_service.apply_allocation_to_rolls("LCV-R56POC", alloc["allocations"])
                costing_service.invalidate_wac_cache()
                return pid, ent
    return None, None


def main():
    h = login()
    print("== R5.6 MARGIN PER-PT + LANDED POC ==")
    pid, ent = asyncio.run(apply_landed_to_sold_product())
    check("prasyarat: produk terjual + roll ber-cost (untuk landed)", pid is not None, f"pid={pid} ent={ent}")
    # clear server WAC cache
    os.system("sudo supervisorctl restart backend >/dev/null 2>&1")
    import time; time.sleep(9)
    h = login()
    r = requests.get(f"{API}/finance/profitability", headers=h, timeout=60)
    check("GET /finance/profitability → 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    if r.status_code != 200:
        print(f"\n=== HASIL R5.6: PASS={PASS} FAIL={FAIL} ==="); sys.exit(1)
    data = r.json()

    # A) by_entity ada
    be = data.get("by_entity")
    check("A: dimensi by_entity (per-PT) ada & non-empty", isinstance(be, list) and len(be) > 0,
          f"type={type(be)} n={len(be) if isinstance(be,list) else 0}")

    # B) tiap baris: cogs_base + cogs_landed == cogs
    def rows_ok(rows):
        return all(abs((row.get("cogs_base", 0) + row.get("cogs_landed", 0)) - row.get("cogs", 0)) < 0.5
                   for row in rows)
    dims = {k: data.get(k, []) for k in ["by_product", "by_category", "by_customer", "by_sales", "by_entity"]}
    check("B: cogs_base + cogs_landed == cogs di SEMUA dimensi",
          all(rows_ok(v) for v in dims.values()),
          {k: [(x['name'], x.get('cogs_base'), x.get('cogs_landed'), x.get('cogs')) for x in v[:1]] for k, v in dims.items()})

    # C) cogs_landed > 0 di product pid & landed_included True di totals
    prod_rows = data.get("by_product", [])
    prow = next((x for x in prod_rows if x.get("key") == pid), None)
    check("C1: baris produk ber-landed punya cogs_landed > 0", bool(prow) and prow.get("cogs_landed", 0) > 0,
          f"prow={ {k:prow.get(k) for k in ('name','cogs_base','cogs_landed','cogs')} if prow else None }")
    tot = data.get("totals", {})
    check("C2: totals.landed_included == True & cogs_landed > 0",
          tot.get("landed_included") is True and tot.get("cogs_landed", 0) > 0,
          f"landed_included={tot.get('landed_included')} cogs_landed={tot.get('cogs_landed')}")

    # D) Σ per-PT == totals
    sum_rev = round(sum(x.get("revenue", 0) for x in be), 2)
    sum_cogs = round(sum(x.get("cogs", 0) for x in be), 2)
    sum_margin = round(sum(x.get("margin", 0) for x in be), 2)
    check("D1: Σ revenue per-PT == totals.revenue", abs(sum_rev - tot.get("revenue", 0)) < 1.0,
          f"sum={sum_rev} tot={tot.get('revenue')}")
    check("D2: Σ cogs per-PT == totals.cogs", abs(sum_cogs - tot.get("cogs", 0)) < 1.0,
          f"sum={sum_cogs} tot={tot.get('cogs')}")
    check("D3: Σ margin per-PT == totals.margin", abs(sum_margin - tot.get("margin", 0)) < 1.5,
          f"sum={sum_margin} tot={tot.get('margin')}")

    check("E: cost_basis menyebut landed", "landed" in str(data.get("cost_basis", "")).lower(),
          str(data.get("cost_basis")))

    print(f"\n=== HASIL R5.6: PASS={PASS} FAIL={FAIL} ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
