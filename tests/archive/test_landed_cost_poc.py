#!/usr/bin/env python3
"""
POC ISOLASI — P0-5: Landed Cost → alokasi HPP roll (Phase 5.4)
==============================================================
Membuktikan core SEBELUM frontend:

  A. GR set base HPP roll dari harga PO (base_unit_cost = unit_cost).
  B. Create voucher → preview alokasi value-basis benar (Σalloc == total_cost).
  C. Submit → pending_approval.
  D. SoD: pembuat (admin) TIDAK boleh approve voucher sendiri → 403.
  E. Approve oleh manager → applied; roll.unit_cost += per_unit (additive),
     landed_cost_total & landed_cost_refs terisi.
  F. Idempotent: approve ulang → 409 (status bukan pending_approval).
  G. Pay → cash_transaction(out, ref_type=landed_cost) + status paid.

Isolated: setup state via motor langsung, eksekusi via HTTP API NYATA, assert via DB.
Idempotent (cleanup di awal).
"""
import asyncio
import os
import sys
import requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
ENTITY = "ent_ksc"
WAREHOUSE = "wh_jakarta"

MARK = "LCPOC"
PROD_ID = f"prod_{MARK.lower()}"
PO_ID = f"po_{MARK.lower()}"
PO_NUMBER = f"PO-{MARK}"
PO_PRICE = 50000.0  # per meter

PASS, FAIL = [], []
def ok(m): PASS.append(m); print(f"  \u2705 [PASS] {m}")
def bad(m): FAIL.append(m); print(f"  \u274c [FAIL] {m}")
def info(m): print(f"  \u2139  {m}")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "demo12345"}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


async def cleanup(db):
    await db.wms_tasks.delete_many({"mark": MARK})
    await db.inventory_rolls.delete_many({"$or": [{"mark": MARK}, {"product_id": PROD_ID}]})
    await db.inventory_movements.delete_many({"product_id": PROD_ID})
    await db.products.delete_many({"id": PROD_ID})
    await db.purchase_orders.delete_many({"id": PO_ID})
    await db.landed_cost_vouchers.delete_many({"po_ids": PO_ID})
    await db.cash_transactions.delete_many({"ref_type": "landed_cost", "description": {"$regex": MARK}})


async def setup_master(db):
    await db.products.update_one({"id": PROD_ID}, {"$set": {
        "id": PROD_ID, "sku": "POC-LC", "name": "Kain POC Landed Cost",
        "category": "Kain", "base_unit": "meter", "price": 80000.0, "harga_pokok": 40000.0,
        "entity_id": ENTITY, "status": "active", "created_at": now_iso()}}, upsert=True)
    await db.purchase_orders.update_one({"id": PO_ID}, {"$set": {
        "id": PO_ID, "po_number": PO_NUMBER, "supplier_id": "sup_poc", "supplier_name": "Supplier POC",
        "warehouse_id": WAREHOUSE, "warehouse_name": "Gudang Jakarta Utara", "entity_id": ENTITY,
        "status": "received",
        "items": [{"product_id": PROD_ID, "sku": "POC-LC", "product_name": "Kain POC Landed Cost",
                   "quantity": 100, "unit": "meter", "price": PO_PRICE, "received_qty": 100}],
        "created_at": now_iso(), "updated_at": now_iso()}}, upsert=True)


async def insert_inbound_task(db, qty):
    tid = f"wms_{MARK.lower()}_{int(datetime.now().timestamp()*1000)}"
    await db.wms_tasks.insert_one({
        "id": tid, "mark": MARK, "flow_type": "inbound", "source_type": "po",
        "po_id": PO_ID, "po_number": PO_NUMBER,
        "product_id": PROD_ID, "product_name": "Kain POC Landed Cost", "sku": "POC-LC",
        "expected_qty": qty, "received_qty": qty, "quantity": qty,
        "unit": "meter", "warehouse_id": WAREHOUSE, "warehouse_name": "Gudang Jakarta Utara",
        "warehouse_city": "Jakarta", "supplier_name": "Supplier POC",
        "bin_id": "", "batch": "", "lot": "", "roll_id": "", "dye_lot": "", "grade": "",
        "status": "qc_check", "stages": ["waiting_goods", "receiving", "qc_check", "put_away", "completed"],
        "scan_log": [], "escalation": None,
        "created_by": "poc", "created_at": now_iso(), "updated_at": now_iso()})
    return tid


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    sA = requests.Session()
    sA.headers.update({"Authorization": f"Bearer {login('admin@kainnusantara.id')}"})
    ok("Login admin")
    try:
        sM = requests.Session()
        sM.headers.update({"Authorization": f"Bearer {login('manager@kainnusantara.id')}"})
        ok("Login manager (untuk approve — SoD)")
    except Exception as e:
        bad(f"Login manager gagal: {e}"); sM = None

    await cleanup(db)
    await setup_master(db)

    # ── A. GR set base HPP roll dari harga PO ─────────────────────────────
    info("TEST A: GR → base HPP roll dari harga PO (multi-roll 60+40)")
    t1 = await insert_inbound_task(db, 100)
    r = sA.post(f"{API}/inbound/tasks/{t1}/complete",
                json={"rolls": [{"length": 60}, {"length": 40}]}, timeout=30)
    if r.status_code != 200:
        bad(f"complete GR gagal: {r.status_code} {r.text[:200]}")
    else:
        rolls = await db.inventory_rolls.find({"acquired.ref_id": PO_ID}, {"_id": 0}).to_list(50)
        if len(rolls) == 2 and all(abs(float(x.get("unit_cost") or 0) - PO_PRICE) < 0.01 for x in rolls):
            ok(f"2 roll, base HPP unit_cost == {PO_PRICE:.0f} (dari harga PO)")
        else:
            bad(f"base HPP salah: {[(x.get('roll_no'), x.get('unit_cost'), x.get('base_unit_cost')) for x in rolls]}")
        if all(float(x.get("landed_cost_total", -1)) == 0.0 for x in rolls):
            ok("landed_cost_total awal = 0")
        else:
            bad("landed_cost_total awal bukan 0")

    # ── B. Create voucher + preview alokasi value-basis ───────────────────
    info("TEST B: Buat voucher (freight 600k + duty 400k = 1.000.000) → preview alokasi")
    rc = sA.post(f"{API}/landed-costs", json={
        "po_ids": [PO_ID], "provider_name": "Forwarder POC", "basis": "value",
        "cost_lines": [{"category": "freight", "description": "Ongkos angkut", "amount": 600000},
                       {"category": "duty", "description": "Bea masuk", "amount": 400000}],
    }, timeout=30)
    if rc.status_code != 200:
        bad(f"create voucher gagal: {rc.status_code} {rc.text[:250]}")
        await _finish(client); return
    v = rc.json()
    vid = v["id"]
    ok(f"Voucher dibuat: {v['voucher_number']} (status {v['status']}, total {v['total_cost']:.0f})")
    prev = {p["length"]: p for p in v.get("allocation_preview", [])}
    p60, p40 = prev.get(60.0), prev.get(40.0)
    # value basis: roll 60 → 600k, roll 40 → 400k ; per_unit 10000 both
    if p60 and abs(p60["alloc_amount"] - 600000) < 1 and abs(p60["per_unit"] - 10000) < 0.01:
        ok("Preview roll-60: alloc 600.000, per_unit 10.000")
    else:
        bad(f"Preview roll-60 salah: {p60}")
    if p40 and abs(p40["alloc_amount"] - 400000) < 1 and abs(p40["new_unit_cost"] - 60000) < 0.01:
        ok("Preview roll-40: alloc 400.000, new_unit_cost 60.000")
    else:
        bad(f"Preview roll-40 salah: {p40}")
    alloc_sum = sum(p["alloc_amount"] for p in v.get("allocation_preview", []))
    if abs(alloc_sum - 1000000) < 0.5:
        ok("Σ alokasi preview == total_cost (1.000.000)")
    else:
        bad(f"Σ alokasi preview != total: {alloc_sum}")

    # ── C. Submit → pending_approval ──────────────────────────────────────
    info("TEST C: Submit voucher")
    rs = sA.post(f"{API}/landed-costs/{vid}/submit", timeout=30)
    if rs.status_code == 200 and rs.json().get("status") == "pending_approval":
        ok("Submit → pending_approval")
    else:
        bad(f"Submit salah: {rs.status_code} {rs.text[:150]}")

    # ── D. SoD: admin (pembuat) approve → 403 ─────────────────────────────
    info("TEST D: SoD — pembuat (admin) approve sendiri")
    rd = sA.post(f"{API}/landed-costs/{vid}/approve", timeout=30)
    if rd.status_code == 403:
        ok("SoD ditegakkan: admin (pembuat) tidak bisa approve sendiri → 403")
    else:
        bad(f"SoD GAGAL: harus 403, dapat {rd.status_code} {rd.text[:150]}")

    # ── E. Approve oleh manager → applied + HPP roll naik ─────────────────
    info("TEST E: Approve oleh manager → applied + alokasi ke HPP roll")
    if sM:
        re = sM.post(f"{API}/landed-costs/{vid}/approve", timeout=30)
        if re.status_code != 200:
            bad(f"approve manager gagal: {re.status_code} {re.text[:200]}")
        else:
            vv = re.json()
            if vv.get("status") == "applied" and len(vv.get("allocations", [])) == 2:
                ok("Voucher applied + 2 alokasi tersimpan")
            else:
                bad(f"approve hasil salah: status={vv.get('status')} allocs={len(vv.get('allocations', []))}")
            rolls = await db.inventory_rolls.find({"acquired.ref_id": PO_ID}, {"_id": 0}).to_list(50)
            if all(abs(float(x.get("unit_cost") or 0) - 60000) < 0.01 for x in rolls):
                ok("Roll unit_cost naik 50.000 → 60.000 (base + landed per_unit)")
            else:
                bad(f"unit_cost pasca-apply salah: {[(x.get('roll_no'), x.get('unit_cost')) for x in rolls]}")
            by_len = {round(float(x.get('length_initial', 0))): x for x in rolls}
            r60, r40 = by_len.get(60), by_len.get(40)
            if r60 and abs(float(r60.get("landed_cost_total", 0)) - 600000) < 1 and \
               r40 and abs(float(r40.get("landed_cost_total", 0)) - 400000) < 1:
                ok("landed_cost_total: roll-60=600k, roll-40=400k")
            else:
                bad(f"landed_cost_total salah: 60={r60 and r60.get('landed_cost_total')} 40={r40 and r40.get('landed_cost_total')}")
            if r60 and vv["voucher_number"] in (r60.get("landed_cost_refs") or []):
                ok(f"landed_cost_refs berisi {vv['voucher_number']}")
            else:
                bad("landed_cost_refs tidak terisi voucher")

        # ── F. Idempotent: approve ulang → 409 ────────────────────────────
        info("TEST F: Idempotent — approve ulang")
        rf = sM.post(f"{API}/landed-costs/{vid}/approve", timeout=30)
        if rf.status_code == 409:
            ok("Approve ulang ditolak → 409 (idempotent, HPP tidak dobel)")
        else:
            bad(f"Idempotensi GAGAL: harus 409, dapat {rf.status_code}")

    # ── G. Pay → cash_transaction(out) ────────────────────────────────────
    info("TEST G: Bayar voucher (kas keluar)")
    rg = sA.post(f"{API}/landed-costs/{vid}/pay",
                 json={"amount": 1000000, "cash_type": "kas_besar", "method": "transfer"}, timeout=30)
    if rg.status_code == 200 and rg.json().get("status") == "paid":
        ok("Pay → status paid")
        cash = await db.cash_transactions.find_one(
            {"ref_type": "landed_cost", "ref_id": vid}, {"_id": 0})
        if cash and cash.get("direction") == "out" and abs(float(cash.get("amount", 0)) - 1000000) < 1:
            ok("cash_transaction(out, ref_type=landed_cost, 1.000.000) tercatat")
        else:
            bad(f"cash_transaction salah: {cash}")
    else:
        bad(f"Pay salah: {rg.status_code} {rg.text[:150]}")

    await cleanup(db)
    await _finish(client)


async def _finish(client):
    client.close()
    print("\n" + "=" * 64)
    print(f"  SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("=" * 64)
    if FAIL:
        print("\n\u274c FAILED:")
        for f in FAIL:
            print(f"  - {f}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0 if not FAIL else 1)
