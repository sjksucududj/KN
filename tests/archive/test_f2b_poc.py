"""F2b POC — Future-aware ATP + Pending SO + Delivery Hold (ISOLATED).

Credit-guard memblok SO bernilai besar (batik 185k/m), jadi POC menyuntik 1 baris
backorder (Pending SO) langsung ke DB — meniru PERSIS struktur `backorders[]` yang
dihasilkan create_order — lalu menguji logika F2b via LIVE API, dan membersihkannya.

Membuktikan:
  1. GET /api/stock/atp → available + incoming(PO+ETA) + atp_now/atp_horizon.
  2. Pending SO (backorder) → muncul di GET /api/stock/pending-so, dicocokkan ke
     incoming PO (coverage + promise_date).
  3. ATP detail mencerminkan pending demand (atp_now turun, atp_horizon dihitung).
  4. Delivery hold (hold_type='delivery') via LIVE API → muncul di papan Hold.
  5. Cleanup: hapus SO uji + release hold (state kembali).
"""
import asyncio
import os
import sys

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _url():
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return "http://localhost:8001"


BASE = _url()
PROD = "prod_batik_mega"
ENT = "ent_ksc"
TEST_SO_ID = "so_f2b_poc_test"
BO_QTY = 200.0
PASS, FAIL = 0, 0


def check(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [PASS] {label}")
    else:
        FAIL += 1; print(f"  [FAIL] {label} {extra}")


async def seed_backorder(db):
    await db.sales_orders.delete_one({"id": TEST_SO_ID})
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.sales_orders.insert_one({
        "id": TEST_SO_ID, "number": "SO-F2BPOC", "status": "waiting_stock",
        "customer_id": "cust_textile_medan", "customer_name": "Tekstil Medan Jaya (POC)",
        "customer_city": "Medan", "entity_id": ENT, "items": [], "allocations": [],
        "total_amount": 0.0, "has_backorder": True,
        "backorders": [{
            "id": "bo_f2b_poc", "product_id": PROD, "sku": "BTK-MEGA-001",
            "product_name": "Batik Mega Mendung Premium", "entity_id": ENT,
            "customer_city": "Medan", "requested_qty": BO_QTY + 100, "reserved_qty": 100.0,
            "backorder_qty": BO_QTY, "status": "waiting_stock",
            "created_at": now, "updated_at": now,
        }],
        "created_at": now, "updated_at": now,
    })


async def cleanup(db):
    await db.sales_orders.delete_one({"id": TEST_SO_ID})


def hdr(token):
    return {"Authorization": f"Bearer {token}", "X-Entity-Id": ENT}


async def main():
    print(f"BASE = {BASE}")
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code}"
    token = r.json()["token"]
    H = hdr(token)

    # ── 1. ATP detail awal ───────────────────────────────────────────────────
    print("\n[1] ATP detail awal (tanpa pending)")
    await db.sales_orders.delete_one({"id": TEST_SO_ID})  # pastikan bersih
    r = requests.get(f"{BASE}/api/stock/atp", params={"product_id": PROD, "owner_entity_id": ENT}, headers=H, timeout=20)
    check(r.status_code == 200, "GET /stock/atp 200", r.text[:200])
    atp = r.json()
    avail = atp.get("available", 0)
    check(avail > 0, f"available > 0 (={avail})")
    check(atp.get("incoming_total", 0) > 0, f"incoming_total > 0 (={atp.get('incoming_total')})")
    check(any(i.get("po_number") and i.get("eta") for i in atp.get("incoming", [])),
          "incoming punya po_number + ETA")
    check(atp.get("atp_horizon") == round(avail + atp.get("incoming_in_horizon", 0) - atp.get("pending_total", 0), 2),
          "atp_horizon == available + incoming(horizon) − pending")
    print(f"      available={avail} incoming={atp.get('incoming_total')} horizon={atp.get('incoming_in_horizon')} "
          f"atp_now={atp.get('atp_now')} atp_horizon={atp.get('atp_horizon')}")

    # ── 2. Seed backorder + Pending SO board ─────────────────────────────────
    print("\n[2] Pending SO board (backorder dicocokkan ke incoming)")
    await seed_backorder(db)
    r = requests.get(f"{BASE}/api/stock/pending-so", params={"owner_entity_id": ENT}, headers=H, timeout=20)
    check(r.status_code == 200, "GET /stock/pending-so 200", r.text[:200])
    rows = r.json()
    mine = [x for x in rows if x.get("order_id") == TEST_SO_ID]
    check(len(mine) == 1, f"Pending SO muncul (n={len(mine)})", str(rows)[:200])
    if mine:
        row = mine[0]
        check(abs(row.get("backorder_qty", 0) - BO_QTY) < 0.01, f"backorder_qty == {BO_QTY} (={row.get('backorder_qty')})")
        check(row.get("coverage") == "covered", f"coverage == covered (incoming 800 ≥ {BO_QTY}) ({row.get('coverage')})")
        check(bool(row.get("promise_date")), f"promise_date == ETA PO ({row.get('promise_date')})")
        check(row.get("incoming_total", 0) >= BO_QTY, f"incoming_total ≥ backorder ({row.get('incoming_total')})")
        print(f"      qty={row.get('backorder_qty')} coverage={row.get('coverage')} "
              f"promise={row.get('promise_date')} incoming={row.get('incoming_total')}")

    # ── 3. ATP detail mencerminkan pending ───────────────────────────────────
    print("\n[3] ATP detail setelah pending demand")
    r = requests.get(f"{BASE}/api/stock/atp", params={"product_id": PROD, "owner_entity_id": ENT}, headers=H, timeout=20)
    atp2 = r.json()
    check(abs(atp2.get("pending_total", 0) - BO_QTY) < 0.01, f"pending_total == {BO_QTY} (={atp2.get('pending_total')})")
    check(abs(atp2.get("atp_now", 0) - round(avail - BO_QTY, 2)) < 0.01,
          f"atp_now == available − pending ({atp2.get('atp_now')})")
    check(len(atp2.get("pending_demand", [])) >= 1, "pending_demand list terisi")
    print(f"      pending_total={atp2.get('pending_total')} atp_now={atp2.get('atp_now')} atp_horizon={atp2.get('atp_horizon')}")

    # ── 4. Delivery hold via LIVE API ────────────────────────────────────────
    print("\n[4] Delivery hold (hold_type='delivery')")
    r = requests.post(f"{BASE}/api/stock/hold", headers=H, timeout=20, json={
        "product_id": PROD, "warehouse_id": "wh_jakarta", "owner_entity_id": ENT,
        "quantity": 10, "reason": "Tahan kirim — permintaan customer",
        "hold_type": "delivery", "ref_type": "sales_order", "ref_id": TEST_SO_ID})
    check(r.status_code == 200, f"POST /stock/hold delivery {r.status_code}", r.text[:200])
    hold = r.json() if r.status_code == 200 else {}
    hold_id = hold.get("hold_id")
    check(hold.get("ref", {}).get("hold_type") == "delivery", "ref.hold_type == delivery")
    r = requests.get(f"{BASE}/api/stock/holds", params={"owner_entity_id": ENT}, headers=H, timeout=20)
    dh = [x for x in r.json() if x.get("ref_id") == hold_id]
    check(len(dh) == 1 and dh[0].get("hold_type") == "delivery", "delivery hold di papan + hold_type", str(r.json())[:200])

    # ── 5. Cleanup ───────────────────────────────────────────────────────────
    print("\n[5] Cleanup")
    if hold_id:
        rr = requests.post(f"{BASE}/api/stock/hold/{hold_id}/release", headers=H, timeout=20)
        check(rr.status_code == 200, f"release delivery hold {rr.status_code}", rr.text[:150])
    await cleanup(db)
    r = requests.get(f"{BASE}/api/stock/pending-so", params={"owner_entity_id": ENT}, headers=H, timeout=20)
    check(not any(x.get("order_id") == TEST_SO_ID for x in r.json()), "Pending SO uji terhapus (state bersih)")

    print(f"\n================ F2b POC: PASS {PASS} | FAIL {FAIL} ================")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
