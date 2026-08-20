#!/usr/bin/env python3
"""
POC ISOLASI — P2: Multi-Level Sequential Approval (PO) — Phase 7.1
=================================================================
Manager (L1) → Direksi/Admin (L2). 2 tingkat tetap (≥500jt butuh L2), configurable.

  A. PO ≥500jt → approval_chain = [L1 manager, L2 admin]; status waiting_approval; level 1.
  B. SoD: pembuat PO tak boleh approve (403).
  C. Role gate L1: sales (rank<manager) approve → 403. Manager approve L1 → tetap
     waiting_approval, level 2, required_role=admin.
  D. Role gate L2: manager approve L2 (rank<admin) → 403. Admin approve L2 → status
     'pending', approval_status 'approved', inbound task dibuat.
  E. Same approver across levels diizinkan (admin bisa approve L1 lalu L2).
  F. Backward-compat: PO 100\u2013500jt → chain 1 level (manager) → manager approve → selesai.
  G. Reject di level berjalan → rejected.

Isolated: buat PO via API NYATA, patch created_by_id agar SoD tak menghalangi approver. Idempotent.
"""
import asyncio, os, sys, requests
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/"); API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]; DB_NAME = os.environ["DB_NAME"]
WH = "wh_jakarta"; PROD = "prod_batik_mega"; PRICE = 185000

PASS, FAIL = [], []
def ok(m): PASS.append(m); print(f"  \u2705 [PASS] {m}")
def bad(m): FAIL.append(m); print(f"  \u274c [FAIL] {m}")
def info(m): print(f"  \u2139  {m}")

S = {}
def login(role, email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "demo12345"}, timeout=30)
    r.raise_for_status(); s = requests.Session(); s.headers.update({"Authorization": f"Bearer {r.json()['token']}"}); S[role] = s


def create_po(qty, supplier_id, created_by="POC"):
    body = {"supplier_id": supplier_id, "warehouse_id": WH, "created_by": created_by,
            "entity_id": "ent_ksc", "items": [{"product_id": PROD, "quantity": qty, "unit": "meter", "price": PRICE}]}
    return S["admin"].post(f"{API}/purchase-orders", json=body, timeout=30)


async def set_creator(db, po_id, uid):
    await db.purchase_orders.update_one({"id": po_id}, {"$set": {"created_by_id": uid}})


async def cleanup(db):
    pos = await db.purchase_orders.find({"created_by": "POC"}, {"_id": 0, "id": 1}).to_list(50)
    ids = [p["id"] for p in pos]
    if ids:
        await db.purchase_orders.delete_many({"id": {"$in": ids}})
        await db.wms_tasks.delete_many({"po_id": {"$in": ids}})


async def main():
    client = AsyncIOMotorClient(MONGO_URL); db = client[DB_NAME]
    for r, e in [("admin", "admin@kainnusantara.id"), ("manager", "manager@kainnusantara.id"),
                 ("sales", "sales@kainnusantara.id")]:
        login(r, e)
    ok("Login admin/manager/sales")
    await cleanup(db)
    sup = (await db.suppliers.find_one({}, {"_id": 0, "id": 1}))["id"]

    # ── A. PO ≥500jt → chain 2 level ──────────────────────────────────────
    info("TEST A: PO 3000m × 185rb = 555jt → chain [manager, admin]")
    ra = create_po(3000, sup)
    if ra.status_code != 200:
        bad(f"create gagal: {ra.status_code} {ra.text[:200]}"); await _fin(client); return
    po = ra.json(); pid = po["id"]
    chain = po.get("approval_chain", [])
    roles = [c["required_role"] for c in chain]
    if roles == ["manager", "admin"] and po["status"] == "waiting_approval" and po.get("approval_level_current") == 1:
        ok("chain=[manager L1, admin/Direksi L2], waiting_approval, level 1")
    else:
        bad(f"chain salah: roles={roles} status={po['status']} level={po.get('approval_level_current')}")

    # patch creator → dummy (agar manager & admin boleh approve)
    await set_creator(db, pid, "user_dummy_creator")

    # ── B. SoD ────────────────────────────────────────────────────────────
    info("TEST B: SoD — pembuat tak boleh approve")
    rb = create_po(3000, sup, created_by="manager")
    pidb = rb.json()["id"]
    await set_creator(db, pidb, "user_manager_01")  # creator = manager
    sod = S["manager"].post(f"{API}/purchase-orders/{pidb}/approve", timeout=30)
    ok("Creator (manager) approve PO sendiri → 403") if sod.status_code == 403 else bad(f"SoD gagal: {sod.status_code}")

    # ── C. L1 gate + advance ──────────────────────────────────────────────
    info("TEST C: sales approve L1 → 403; manager approve L1 → lanjut L2")
    rc1 = S["sales"].post(f"{API}/purchase-orders/{pid}/approve", timeout=30)
    ok("sales approve L1 → 403") if rc1.status_code == 403 else bad(f"L1 role gate gagal: {rc1.status_code}")
    rc2 = S["manager"].post(f"{API}/purchase-orders/{pid}/approve", timeout=30)
    if rc2.status_code == 200:
        d = rc2.json()
        c1 = d["approval_chain"][0]
        if d["status"] == "waiting_approval" and d.get("approval_level_current") == 2 and d["required_approval_role"] == "admin" and c1["status"] == "approved":
            ok("Manager approve L1 → tetap waiting, level 2, required admin, L1 approved")
        else:
            bad(f"advance L1 salah: status={d['status']} level={d.get('approval_level_current')} req={d['required_approval_role']}")
    else:
        bad(f"manager approve L1 gagal: {rc2.status_code} {rc2.text[:150]}")

    # ── D. L2 gate + finalize ─────────────────────────────────────────────
    info("TEST D: manager approve L2 → 403; admin approve L2 → approved + inbound task")
    rd1 = S["manager"].post(f"{API}/purchase-orders/{pid}/approve", timeout=30)
    ok("manager approve L2 (butuh admin) → 403") if rd1.status_code == 403 else bad(f"L2 role gate gagal: {rd1.status_code}")
    rd2 = S["admin"].post(f"{API}/purchase-orders/{pid}/approve", timeout=30)
    if rd2.status_code == 200:
        d = rd2.json()
        tasks = await db.wms_tasks.count_documents({"po_id": pid})
        if d["status"] == "pending" and d["approval_status"] == "approved" and all(c["status"] == "approved" for c in d["approval_chain"]) and tasks > 0:
            ok("Admin approve L2 → pending/approved, semua level approved, inbound task dibuat")
        else:
            bad(f"finalize salah: status={d['status']} appr={d['approval_status']} tasks={tasks}")
    else:
        bad(f"admin approve L2 gagal: {rd2.status_code} {rd2.text[:150]}")

    # ── E. Same approver across levels ────────────────────────────────────
    info("TEST E: admin approve L1 lalu L2 (approver sama lintas tingkat diizinkan)")
    re = create_po(3000, sup); pide = re.json()["id"]
    await set_creator(db, pide, "user_dummy_creator")
    a1 = S["admin"].post(f"{API}/purchase-orders/{pide}/approve", timeout=30)   # admin satisfies manager L1
    a2 = S["admin"].post(f"{API}/purchase-orders/{pide}/approve", timeout=30)   # admin L2
    ok("Admin approve L1 lalu L2 → approved") if a2.status_code == 200 and a2.json()["status"] == "pending" else bad(f"same-approver gagal: a1={a1.status_code} a2={a2.status_code}")

    # ── F. Backward-compat single level ───────────────────────────────────
    info("TEST F: PO 1000m × 185rb = 185jt → chain 1 level (manager)")
    rf = create_po(1000, sup); pidf = rf.json()["id"]
    chainf = rf.json().get("approval_chain", [])
    ok("chain 1 level [manager]") if [c["required_role"] for c in chainf] == ["manager"] else bad(f"single-level chain salah: {[c['required_role'] for c in chainf]}")
    await set_creator(db, pidf, "user_dummy_creator")
    af = S["manager"].post(f"{API}/purchase-orders/{pidf}/approve", timeout=30)
    ok("Manager approve → langsung approved (1 level)") if af.status_code == 200 and af.json()["status"] == "pending" else bad(f"single-level approve gagal: {af.status_code}")

    # ── G. Reject ─────────────────────────────────────────────────────────
    info("TEST G: reject di level berjalan → rejected")
    rg = create_po(3000, sup); pidg = rg.json()["id"]
    await set_creator(db, pidg, "user_dummy_creator")
    rj = S["manager"].post(f"{API}/purchase-orders/{pidg}/reject", json={"reason": "POC reject"}, timeout=30)
    ok("Reject → rejected") if rj.status_code == 200 and rj.json()["status"] == "rejected" else bad(f"reject gagal: {rj.status_code}")

    await cleanup(db)
    await _fin(client)


async def _fin(client):
    client.close()
    print("\n" + "=" * 64)
    print(f"  SUMMARY: {len(PASS)} PASS | {len(FAIL)} FAIL")
    print("=" * 64)
    if FAIL:
        print("\n\u274c FAILED:");  [print(f"  - {f}") for f in FAIL]


if __name__ == "__main__":
    asyncio.run(main()); sys.exit(0 if not FAIL else 1)
