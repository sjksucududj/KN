#!/usr/bin/env python3
"""
POC ISOLASI — P1: QC 4-Point Inspection + GSM/Lebar aktual — Phase 6.2
=====================================================================
  A. compute_points: total poin = Σ(point_value × count).
  B. Grade default: poin ≤20=A, 21\u201340=B, >40=C (+ boundary 20=A, 40=B).
  C. inspect_roll set roll.grade + simpan inspection + GSM/lebar aktual.
  D. rolls_for_task: list roll per qc_task_id (+ standar GSM/lebar produk).
  E. Validasi: point_value harus 1..4 → 400.
  F. Configurable: ubah ambang (a_max=5) → grade berubah; lalu restore.

Isolated: seed 1 roll (qc_task_id) via motor, eksekusi via API NYATA. Idempotent.
"""
import asyncio, os, sys, requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]; DB_NAME = os.environ["DB_NAME"]
TASK_ID = "task_qcpoc"; ROLL_ID = "roll_qcpoc"

PASS, FAIL = [], []
def ok(m): PASS.append(m); print(f"  \u2705 [PASS] {m}")
def bad(m): FAIL.append(m); print(f"  \u274c [FAIL] {m}")
def info(m): print(f"  \u2139  {m}")


def now_iso(): return datetime.now(timezone.utc).isoformat()
def login(): 
    r = requests.post(f"{API}/auth/login", json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=30)
    r.raise_for_status(); return r.json()["token"]


async def seed_roll(db):
    prod = await db.products.find_one({}, {"_id": 0, "id": 1})
    await db.inventory_rolls.delete_many({"id": ROLL_ID})
    await db.inventory_rolls.insert_one({
        "id": ROLL_ID, "roll_no": "RL-QCPOC", "product_id": prod["id"],
        "owner_entity_id": "ent_ksc", "warehouse_id": "wh_jakarta",
        "length_initial": 120.0, "length_remaining": 120.0, "unit": "meter",
        "grade": "", "defects": [], "status": "quarantine", "qc_task_id": TASK_ID,
        "acquired": {"via": "inbound", "ref_id": "po_x", "date": now_iso()},
        "created_at": now_iso(), "updated_at": now_iso()})
    await db.wms_tasks.delete_many({"id": TASK_ID})
    await db.wms_tasks.insert_one({"id": TASK_ID, "flow_type": "inbound", "status": "qc_pending",
        "product_id": prod["id"], "warehouse_id": "wh_jakarta", "created_at": now_iso()})


async def reset_threshold(db, a_max=20.0, b_max=40.0):
    await db.system_settings.update_one({"scope": "global"},
        {"$set": {"qc.grade_thresholds.a_max": a_max, "qc.grade_thresholds.b_max": b_max}})


def do_inspect(s, defects, gsm=None, width=None):
    body = {"defects": defects, "gsm_actual": gsm, "width_actual": width, "note": "poc"}
    return s.post(f"{API}/inbound/rolls/{ROLL_ID}/inspect", json=body, timeout=30)


async def main():
    client = AsyncIOMotorClient(MONGO_URL); db = client[DB_NAME]
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {login()}"})
    ok("Login admin")
    await seed_roll(db)
    await reset_threshold(db)  # ensure 20/40

    # ── A+B. points + grade A (10 poin) ───────────────────────────────────
    info("TEST A/B: 5×1pt + 1×... → grade by points")
    # 10 poin: 2×(1) + 2×(4) = 2+8=10 → A
    r = do_inspect(s, [{"point_value": 1, "count": 2}, {"point_value": 4, "count": 2}], gsm=145, width=115)
    if r.status_code == 200:
        d = r.json()
        ok("points=10") if abs(d["points"] - 10) < 0.01 else bad(f"points salah: {d['points']}")
        ok("grade A (\u226420)") if d["grade"] == "A" else bad(f"grade salah: {d['grade']}")
        roll = await db.inventory_rolls.find_one({"id": ROLL_ID}, {"_id": 0})
        ok("roll.grade=A tersimpan") if roll["grade"] == "A" else bad(f"roll.grade: {roll['grade']}")
        insp = roll.get("inspection", {})
        ok("GSM/lebar aktual tersimpan") if insp.get("gsm_actual") == 145 and insp.get("width_actual") == 115 else bad(f"gsm/width: {insp.get('gsm_actual')}/{insp.get('width_actual')}")
    else:
        bad(f"inspect A gagal: {r.status_code} {r.text[:150]}")

    # grade B (30 poin): 10×3 = 30 → B
    rb = do_inspect(s, [{"point_value": 3, "count": 10}])
    ok("grade B (21\u201340) untuk 30 poin") if rb.status_code == 200 and rb.json()["grade"] == "B" and abs(rb.json()["points"] - 30) < 0.01 else bad(f"grade B salah: {rb.status_code} {rb.json() if rb.status_code==200 else rb.text[:120]}")

    # grade C (>40): 12×4 = 48 → C
    rc = do_inspect(s, [{"point_value": 4, "count": 12}])
    ok("grade C (>40) untuk 48 poin") if rc.status_code == 200 and rc.json()["grade"] == "C" else bad(f"grade C salah: {rc.status_code}")

    # boundary 20 → A ; 40 → B
    r20 = do_inspect(s, [{"point_value": 4, "count": 5}])   # 20 → A
    r40 = do_inspect(s, [{"point_value": 4, "count": 10}])  # 40 → B
    ok("boundary 20 poin → A") if r20.status_code == 200 and r20.json()["grade"] == "A" else bad(f"boundary20: {r20.json().get('grade')}")
    ok("boundary 40 poin → B") if r40.status_code == 200 and r40.json()["grade"] == "B" else bad(f"boundary40: {r40.json().get('grade')}")

    # ── D. rolls_for_task ─────────────────────────────────────────────────
    info("TEST D: list rolls untuk task (+ standar produk)")
    rd = s.get(f"{API}/inbound/qc/tasks/{TASK_ID}/rolls", timeout=30)
    if rd.status_code == 200 and any(x["id"] == ROLL_ID and x["inspected"] for x in rd.json()):
        row = next(x for x in rd.json() if x["id"] == ROLL_ID)
        ok("Roll muncul + inspected=True")
        ok("Field standar GSM/lebar tersedia") if "gsm_standard" in row and "width_standard" in row else bad("standar absent")
    else:
        bad(f"rolls_for_task gagal: {rd.status_code}")

    # ── E. Validasi point_value ───────────────────────────────────────────
    info("TEST E: point_value invalid (5) → 400")
    re = do_inspect(s, [{"point_value": 5, "count": 1}])
    ok("point_value=5 → 400") if re.status_code == 400 else bad(f"harus 400, dapat {re.status_code}")

    # ── F. Configurable thresholds ────────────────────────────────────────
    info("TEST F: ubah a_max=5 → 10 poin jadi B; lalu restore")
    await reset_threshold(db, a_max=5.0, b_max=40.0)
    rf = do_inspect(s, [{"point_value": 1, "count": 10}])  # 10 poin, a_max=5 → B
    ok("Thresholds configurable (10 poin → B saat a_max=5)") if rf.status_code == 200 and rf.json()["grade"] == "B" else bad(f"configurable gagal: {rf.json().get('grade') if rf.status_code==200 else rf.text[:120]}")
    await reset_threshold(db)  # restore 20/40

    # cleanup
    await db.inventory_rolls.delete_many({"id": ROLL_ID})
    await db.wms_tasks.delete_many({"id": TASK_ID})
    client.close()
    print("\n" + "=" * 64)
    print(f"  SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("=" * 64)
    if FAIL:
        print("\n\u274c FAILED:")
        for f in FAIL: print(f"  - {f}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0 if not FAIL else 1)
