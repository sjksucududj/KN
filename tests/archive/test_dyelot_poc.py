#!/usr/bin/env python3
"""
POC ISOLASI — P0-4: Dye Lot + Grade aktual saat GR/QC (Phase 5.3)
==================================================================
Membuktikan core wiring SEBELUM frontend (lihat plan.md §5.3 item B):

  1. GR complete dengan dye_lot  → roll punya dye_lot + grade aktual.
  2. GR multi-roll breakdown     → N roll dengan length/dye_lot/grade/defects berbeda.
  3. QC accept dengan accept_grade + defects → roll available grade aktual + defects + qc_grade.
  4. Customer enforce_single_dye_lot=true → alokasi SO dipaksa 1 dye_lot
     (vs customer tanpa flag yang boleh mixed lintas dye_lot pada lot generik yang sama).

Isolated: setup state via motor langsung (wms_tasks / inventory_rolls / products),
eksekusi via HTTP API NYATA, assert via DB. Idempotent (cleanup di awal).
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

MARK = "DYELOTPOC"  # penanda artifact test agar idempotent
PROD_ID = f"prod_{MARK.lower()}"

PASS, FAIL = [], []
def ok(m): PASS.append(m); print(f"  \u2705 [PASS] {m}")
def bad(m): FAIL.append(m); print(f"  \u274c [FAIL] {m}")
def info(m): print(f"  \u2139  {m}")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def login():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


async def cleanup(db):
    """Hapus semua artifact test (idempotent)."""
    await db.wms_tasks.delete_many({"mark": MARK})
    await db.inventory_rolls.delete_many({"$or": [{"mark": MARK}, {"product_id": PROD_ID}]})
    await db.inventory_movements.delete_many({"product_id": PROD_ID})
    await db.products.delete_many({"id": PROD_ID})
    await db.customers.delete_many({"mark": MARK})
    await db.inventory_balances.delete_many({"product_id": PROD_ID})


async def insert_inbound_task(db, qty, unit="meter", product_id=None, dye_lot="", grade=""):
    """Buat wms_task inbound siap-complete (status qc_check)."""
    tid = f"wms_{MARK.lower()}_{int(datetime.now().timestamp()*1000)}"
    await db.wms_tasks.insert_one({
        "id": tid, "mark": MARK, "flow_type": "inbound", "source_type": "manual_poc",
        "po_id": "", "po_number": f"POC-{MARK}",
        "product_id": product_id or PROD_ID, "product_name": "Kain POC Dye Lot", "sku": "POC-DL",
        "expected_qty": qty, "received_qty": qty, "quantity": qty,
        "unit": unit, "warehouse_id": WAREHOUSE, "warehouse_name": "Gudang Jakarta Utara",
        "warehouse_city": "Jakarta", "supplier_name": "Supplier POC",
        "bin_id": "", "batch": "", "lot": "", "roll_id": "",
        "dye_lot": dye_lot, "grade": grade,
        "status": "qc_check", "stages": ["waiting_goods", "receiving", "qc_check", "put_away", "completed"],
        "scan_log": [], "escalation": None,
        "created_by": "poc", "created_at": now_iso(), "updated_at": now_iso(),
    })
    return tid


async def make_product(db):
    await db.products.update_one(
        {"id": PROD_ID},
        {"$set": {
            "id": PROD_ID, "sku": "POC-DL", "name": "Kain POC Dye Lot",
            "category": "Kain", "base_unit": "meter", "price": 50000.0,
            "entity_id": ENTITY, "status": "active", "created_at": now_iso(),
        }}, upsert=True)


async def insert_roll(db, dye_lot, lot, length, status="available"):
    rid = f"roll_{MARK.lower()}_{dye_lot}_{int(datetime.now().timestamp()*1000000)%1000000}"
    await db.inventory_rolls.insert_one({
        "id": rid, "mark": MARK, "product_id": PROD_ID, "owner_entity_id": ENTITY,
        "ownership_type": "internal", "consignor_ref": None,
        "warehouse_id": WAREHOUSE, "bin_id": None,
        "lot": lot, "dye_lot": dye_lot, "batch": lot,
        "roll_no": rid[-6:], "length_initial": length, "length_remaining": length,
        "unit": "meter", "grade": "A", "defects": [], "status": status,
        "tracking_mode": "barcode", "earmarked_for": None, "location_type": "warehouse_bin",
        "reserved_ref": None, "unit_cost": None,
        "acquired": {"via": "initial", "ref_id": "poc", "date": now_iso()},
        "rfid_tag_id": None, "is_remnant": False,
        "created_at": now_iso(), "updated_at": now_iso(), "created_by": "poc", "created_by_name": "POC",
    })
    return rid


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    s = requests.Session()
    token = login()
    s.headers.update({"Authorization": f"Bearer {token}"})
    ok("Login admin@kainnusantara.id")

    await cleanup(db)
    await make_product(db)

    # ─────────────────────────────────────────────────────────────────────
    # TEST 1 — GR complete dengan dye_lot (single roll)
    # ─────────────────────────────────────────────────────────────────────
    info("TEST 1: GR complete dengan dye_lot + grade (single roll)")
    t1 = await insert_inbound_task(db, 50)
    r = s.post(f"{API}/inbound/tasks/{t1}/complete",
               json={"dye_lot": "DL-RED-01", "grade": "B"}, timeout=30)
    if r.status_code != 200:
        bad(f"complete(dye_lot) gagal: {r.status_code} {r.text[:200]}")
    else:
        roll = await db.inventory_rolls.find_one({"qc_task_id": t1}, {"_id": 0})
        if not roll:
            bad("Roll tidak terbentuk dari GR complete")
        else:
            if roll.get("dye_lot") == "DL-RED-01":
                ok(f"Roll dye_lot tersimpan: {roll['dye_lot']}")
            else:
                bad(f"dye_lot salah: {roll.get('dye_lot')} (harap DL-RED-01)")
            if roll.get("grade") == "B":
                ok(f"Roll grade tersimpan: {roll['grade']}")
            else:
                bad(f"grade salah: {roll.get('grade')} (harap B)")
            if abs(float(roll.get("length_remaining", 0)) - 50) < 0.1:
                ok("Roll length=50 (single)")
            else:
                bad(f"length salah: {roll.get('length_remaining')}")

    # ─────────────────────────────────────────────────────────────────────
    # TEST 3 — QC accept dengan accept_grade + defects (chain dari T1)
    # (task t1 kini qc_pending; roll di quarantine)
    # ─────────────────────────────────────────────────────────────────────
    info("TEST 3: QC accept dengan accept_grade='C' + defects")
    task1 = await db.wms_tasks.find_one({"id": t1}, {"_id": 0})
    if (task1 or {}).get("status") != "qc_pending":
        info(f"   (qc_on_receipt non-aktif? status t1={task1.get('status')}) — skip QC grade test")
    else:
        r = s.post(f"{API}/inbound/tasks/{t1}/qc-decision",
                   json={"accept_qty": 50, "reject_qty": 0, "reject_disposition": "damaged",
                         "accept_grade": "C", "defects": ["noda", "belang"], "reason": "POC QC grade"},
                   timeout=30)
        if r.status_code != 200:
            bad(f"qc-decision gagal: {r.status_code} {r.text[:200]}")
        else:
            roll = await db.inventory_rolls.find_one(
                {"product_id": PROD_ID, "status": "available", "dye_lot": "DL-RED-01"}, {"_id": 0})
            if not roll:
                bad("Roll available pasca-QC tidak ditemukan")
            else:
                if roll.get("grade") == "C" and roll.get("qc_grade") == "C":
                    ok(f"Roll grade aktual pasca-QC: grade={roll['grade']} qc_grade={roll['qc_grade']}")
                else:
                    bad(f"grade pasca-QC salah: grade={roll.get('grade')} qc_grade={roll.get('qc_grade')}")
                if roll.get("defects") == ["noda", "belang"]:
                    ok(f"Roll defects tersimpan: {roll['defects']}")
                else:
                    bad(f"defects salah: {roll.get('defects')}")

    # ─────────────────────────────────────────────────────────────────────
    # TEST 2 — GR multi-roll breakdown (length/dye_lot/grade/defects per roll)
    # ─────────────────────────────────────────────────────────────────────
    info("TEST 2: GR multi-roll breakdown (2 roll, dye_lot/grade berbeda)")
    t2 = await insert_inbound_task(db, 100)
    r = s.post(f"{API}/inbound/tasks/{t2}/complete",
               json={"rolls": [
                   {"length": 60, "dye_lot": "DL-A", "grade": "A", "defects": []},
                   {"length": 40, "dye_lot": "DL-B", "grade": "B", "defects": ["sobek"]},
               ]}, timeout=30)
    if r.status_code != 200:
        bad(f"complete(multi-roll) gagal: {r.status_code} {r.text[:200]}")
    else:
        rolls = await db.inventory_rolls.find({"qc_task_id": t2}, {"_id": 0}).to_list(50)
        if len(rolls) != 2:
            bad(f"Multi-roll harus 2 roll, dapat {len(rolls)}")
        else:
            ok("Multi-roll: 2 roll terbentuk")
            by_dye = {x.get("dye_lot"): x for x in rolls}
            a, b = by_dye.get("DL-A"), by_dye.get("DL-B")
            if a and abs(float(a["length_remaining"]) - 60) < 0.1 and a.get("grade") == "A":
                ok("Roll DL-A: length=60 grade=A")
            else:
                bad(f"Roll DL-A salah: {a}")
            if b and abs(float(b["length_remaining"]) - 40) < 0.1 and b.get("grade") == "B" and b.get("defects") == ["sobek"]:
                ok("Roll DL-B: length=40 grade=B defects=['sobek']")
            else:
                bad(f"Roll DL-B salah: {b}")
            # roll_no unik (increment per roll)
            if a and b and a.get("roll_no") != b.get("roll_no"):
                ok(f"roll_no unik per roll: {a.get('roll_no')} != {b.get('roll_no')}")
            else:
                bad("roll_no tidak unik antar roll multi")

    # Multi-roll validasi: total length mismatch harus 400
    t2b = await insert_inbound_task(db, 100)
    r = s.post(f"{API}/inbound/tasks/{t2b}/complete",
               json={"rolls": [{"length": 30, "dye_lot": "DL-X", "grade": "A"}]}, timeout=30)
    if r.status_code == 400:
        ok("Validasi: Σ panjang roll \u2260 qty diterima → 400")
    else:
        bad(f"Validasi mismatch harus 400, dapat {r.status_code}")

    # ─────────────────────────────────────────────────────────────────────
    # TEST 4 — Customer enforce_single_dye_lot → alokasi dipaksa 1 dye_lot
    # Setup: 2 roll, lot generik SAMA "LOT-SHARED", dye_lot beda (DL-RED 60, DL-BLUE 60)
    # ─────────────────────────────────────────────────────────────────────
    info("TEST 4: enforce_single_dye_lot — alokasi 1 dye_lot vs mixed")
    await db.inventory_rolls.delete_many({"mark": MARK, "product_id": PROD_ID, "status": "available"})
    await insert_roll(db, "DL-RED", "LOT-SHARED", 60)
    await insert_roll(db, "DL-BLUE", "LOT-SHARED", 60)

    # Customer A — TANPA flag (boleh mixed). Customer B — DENGAN flag.
    rA = s.post(f"{API}/customers", json={
        "name": f"Cust POC Mixed {MARK}", "pic_name": "A", "phone": "0811", "city": "Jakarta",
        "address": "Jl A", "entity_id": ENTITY, "enforce_single_dye_lot": False}, timeout=30)
    rB = s.post(f"{API}/customers", json={
        "name": f"Cust POC Strict {MARK}", "pic_name": "B", "phone": "0822", "city": "Jakarta",
        "address": "Jl B", "entity_id": ENTITY, "enforce_single_dye_lot": True}, timeout=30)
    if rA.status_code != 200 or rB.status_code != 200:
        bad(f"Buat customer gagal: A={rA.status_code} B={rB.status_code} {rA.text[:120]}")
    else:
        custA, custB = rA.json(), rB.json()
        # tandai agar cleanup menemukan
        await db.customers.update_many({"id": {"$in": [custA["id"], custB["id"]]}}, {"$set": {"mark": MARK}})
        if custB.get("enforce_single_dye_lot") is True:
            ok("Customer B tersimpan enforce_single_dye_lot=True")
        else:
            bad(f"Customer B flag tidak tersimpan: {custB.get('enforce_single_dye_lot')}")

        def preview(cust_id):
            rr = s.post(f"{API}/sales-orders/preview-lots", json={
                "customer_id": cust_id, "entity_id": ENTITY,
                "items": [{"product_id": PROD_ID, "quantity": 100, "unit": "meter"}]}, timeout=30)
            rr.raise_for_status()
            return rr.json()["lines"][0]

        lineA = preview(custA["id"])
        lineB = preview(custB["id"])
        info(f"   A(mixed): reserved={lineA['reserved_qty']} backorder={lineA['backorder_qty']} strict={lineA.get('dye_lot_strict')}")
        info(f"   B(strict): reserved={lineB['reserved_qty']} backorder={lineB['backorder_qty']} strict={lineB.get('dye_lot_strict')}")

        # A: lot generik sama → boleh ambil penuh 100 (reserved 100, backorder 0)
        if abs(lineA["reserved_qty"] - 100) < 0.5 and lineA["backorder_qty"] < 0.5:
            ok("Customer A (tanpa flag): reserved 100, backorder 0 (lintas dye_lot OK)")
        else:
            bad(f"Customer A salah: reserved={lineA['reserved_qty']} backorder={lineA['backorder_qty']}")

        # B: dipaksa 1 dye_lot (maks 60) → reserved 60, backorder 40, dye_lot_strict True
        if lineB.get("dye_lot_strict") is True and abs(lineB["reserved_qty"] - 60) < 0.5 and abs(lineB["backorder_qty"] - 40) < 0.5:
            ok("Customer B (enforce_single_dye_lot): reserved 60 (1 dye_lot), backorder 40 \u2705")
        else:
            bad(f"Customer B salah: strict={lineB.get('dye_lot_strict')} reserved={lineB['reserved_qty']} backorder={lineB['backorder_qty']}")

    # ─────────────────────────────────────────────────────────────────────
    await cleanup(db)
    client.close()

    print("\n" + "=" * 64)
    print(f"  SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("=" * 64)
    if FAIL:
        print("\n\u274c FAILED:")
        for f in FAIL:
            print(f"  - {f}")
    return len(FAIL) == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
