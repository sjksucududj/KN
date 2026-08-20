"""Seed skenario UI R5.5: retur jual settled dgn roll karantina yang produknya ber-LANDED COST,
sehingga muncul label 'incl. landed' + basis WAC landed-inclusive. Cetak identifier.
"""
import os
import sys
import time
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


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def pick_order(h):
    o = requests.get(f"{API}/sales-orders", headers=h, timeout=30).json()
    o = o if isinstance(o, list) else o.get("items", [])
    ok = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    for x in o:
        for it in (x.get("items") or []):
            if float(it.get("quantity", 0) or 0) >= 2 and x.get("status") in ok:
                return x, it
    return None, None


async def apply_landed(product_id):
    from db import db
    from services import landed_cost_service, costing_service
    LIVE = ["available", "reserved", "committed", "picked", "packed", "quarantine"]
    rolls = await db.inventory_rolls.find(
        {"product_id": product_id, "status": {"$in": LIVE},
         "base_unit_cost": {"$gt": 0}, "length_initial": {"$gt": 0}}, {"_id": 0}).to_list(5000)
    if not rolls:
        print("  (no live costed rolls for product; landed skipped)")
        return 0
    base_value = sum(float(r.get("base_unit_cost", 0) or 0) * float(r.get("length_initial", 0) or 0)
                     for r in rolls)
    alloc = landed_cost_service.compute_allocation(rolls, round(0.20 * base_value, 2), basis="value")
    n = await landed_cost_service.apply_allocation_to_rolls("LCV-R55UI", alloc["allocations"])
    costing_service.invalidate_wac_cache()
    return n


def main():
    h = login()
    order, item = pick_order(h)
    if not order:
        print("no eligible order"); return
    pid = item["product_id"]
    print(f"order={order['number']} product={pid}")
    n = asyncio.run(apply_landed(pid))
    print(f"landed applied to {n} rolls of {pid}")
    # restart backend to clear server WAC cache, then continue
    os.system("sudo supervisorctl restart backend >/dev/null 2>&1")
    time.sleep(9)
    h = login()
    whs = requests.get(f"{API}/warehouses", headers=h, timeout=30).json()
    whs = whs if isinstance(whs, list) else whs.get("items", [])
    dest = whs[-1]["id"] if whs else ""
    cr = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
        "order_id": order["id"], "return_type": "retur",
        "items": [{"product_id": pid, "product_name": item.get("product_name", ""),
                   "quantity_returned": 2, "unit": item.get("unit", "meter"),
                   "reason": "R5", "condition": "ok"}], "notes": "R5.5 landed UI demo"})
    if cr.status_code != 200:
        print("create SR failed", cr.status_code, cr.text[:160]); return
    rid = cr.json()["id"]; num = cr.json().get("number")
    requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
    requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                  json={"inspections": [{"index": 0, "defects": [{"point_value": 1, "count": 2}],
                                         "condition": "ok", "accepted_qty": 2}], "notes": "4point"})
    requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                  json={"outcome": "refund", "return_warehouse_id": dest})
    q = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
    for r in (q or []):
        print(f"  quarantine roll {r.get('roll_number')}: unit_cost={r.get('unit_cost')} "
              f"base={r.get('base_unit_cost')} landed_per_unit={r.get('landed_per_unit')} "
              f"landed_included={r.get('landed_included')}")
    print(f"[R5.5 UI] sales-return={num} id={rid}  (buka Detail → panel Karantina utk lihat label 'incl. landed')")


if __name__ == "__main__":
    main()
