"""Seed 2 skenario UI R5.4b (dipakai screenshot & testing agent):
  1) Retur beli DIRECT ap_credit yang sudah difinalisasi (belum di-reversal) → uji tombol Reversal.
  2) Retur jual dgn 1 roll karantina di-SCRAP (write-off, belum dibatalkan) → uji tombol Un-scrap.
Cetak identifier agar mudah dinavigasi.
"""
import os
import sys
import requests
from pymongo import MongoClient

API = f"{os.environ.get('R5_BASE', 'http://localhost:8001')}/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
DBS = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
    os.environ.get("DB_NAME", "test_database")]


def login():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def scenario_pr(h):
    roll = DBS.inventory_rolls.find_one(
        {"status": "available", "unit_cost": {"$gt": 0}, "length_remaining": {"$gt": 0}}, {"_id": 0})
    sup = DBS.suppliers.find_one({}, {"_id": 0})
    body = {
        "supplier_id": sup["id"], "warehouse_id": roll["warehouse_id"],
        "entity_id": roll["owner_entity_id"],
        "items": [{"product_id": roll["product_id"], "quantity": 0, "unit": roll.get("unit", "meter"),
                   "reason": "cacat", "condition": "damaged", "roll_ids": [roll["id"]]}],
        "reason": "Skenario UI reversal", "notes": "R5.4b PR reversal demo",
        "submit_now": True, "bypass_import_policy": True,
    }
    cr = requests.post(f"{API}/purchase-returns", headers=h, json=body, timeout=30)
    cr.raise_for_status()
    pr = cr.json()
    ap = requests.post(f"{API}/purchase-returns/{pr['id']}/approve", headers=h, json={"notes": ""}, timeout=30)
    ap.raise_for_status()
    fin = ap.json()
    print(f"[PR] finalized purchase-return: {fin['number']}  id={fin['id']}  "
          f"stock_adjusted={fin.get('stock_adjusted')} supplier_status={fin.get('supplier_status')} "
          f"debit_note={fin.get('debit_note_number')}")
    return fin


def _eligible_orders(h):
    o = requests.get(f"{API}/sales-orders", headers=h, timeout=30).json()
    o = o if isinstance(o, list) else o.get("items", [])
    ok = {"confirmed", "shipped", "partially_shipped", "done", "picked", "partially_picked"}
    return [x for x in o if x.get("status") in ok and
            any(float(it.get("quantity", 0) or 0) >= 5 for it in (x.get("items") or []))]


def scenario_scrap(h):
    whs = requests.get(f"{API}/warehouses", headers=h, timeout=30).json()
    whs = whs if isinstance(whs, list) else whs.get("items", [])
    dest = whs[-1]["id"] if whs else ""
    for o in _eligible_orders(h):
        its = [it for it in o["items"] if float(it.get("quantity", 0) or 0) >= 2]
        if not its:
            continue
        it = its[0]
        cr = requests.post(f"{API}/sales-returns", headers=h, timeout=30, json={
            "order_id": o["id"], "return_type": "retur",
            "items": [{"product_id": it["product_id"], "product_name": it.get("product_name", ""),
                       "quantity_returned": 2, "unit": it.get("unit", "meter"),
                       "reason": "R5", "condition": "ok"}], "notes": "R5.4b unscrap demo"})
        if cr.status_code != 200:
            continue
        rid = cr.json()["id"]
        num = cr.json().get("number")
        requests.post(f"{API}/sales-returns/{rid}/submit", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/approve", headers=h, json={"notes": ""}, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/inspect/start", headers=h, timeout=30)
        requests.post(f"{API}/sales-returns/{rid}/inspect/complete", headers=h, timeout=30,
                      json={"inspections": [{"index": 0, "defects": [{"point_value": 1, "count": 2}],
                                             "condition": "ok", "accepted_qty": 2}], "notes": "4point"})
        requests.post(f"{API}/sales-returns/{rid}/settle", headers=h, timeout=30,
                      json={"outcome": "refund", "return_warehouse_id": dest})
        q = requests.get(f"{API}/sales-returns/{rid}/quarantine", headers=h, timeout=30).json()
        cand = next((x for x in (q or []) if float(x.get("unit_cost") or 0) > 0), None)
        if not cand:
            continue
        rel = requests.post(f"{API}/sales-returns/{rid}/quarantine/release", headers=h, timeout=30,
                            json={"decisions": [{"roll_id": cand["id"], "action": "scrap"}]})
        if rel.status_code == 200:
            print(f"[SR] sales-return with SCRAPPED roll: {num}  id={rid}  "
                  f"roll={cand.get('roll_number')} ({cand['id']})")
            return {"return_id": rid, "number": num, "roll_id": cand["id"]}
    print("[SR] gagal membuat skenario scrap (tak ada order eligible)")
    return None


def main():
    h = login()
    pr = scenario_pr(h)
    sr = scenario_scrap(h)
    print("\nDONE scenarios seeded.")
    return pr, sr


if __name__ == "__main__":
    main()
