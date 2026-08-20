"""POC — RFID Simulator (Fase 5). Verifikasi end-to-end semua flow + SSOT-safe.

Jalankan: cd /app && python test_rfid_poc.py
Exit 0 = semua lolos.
"""
import asyncio
import os
import sys

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
BASE = "https://warehouse-fase-b.preview.emergentagent.com"
MONGO = os.environ["MONGO_URL"]
DBN = os.environ["DB_NAME"]

passed, failed = [], []


def check(name, cond, extra=""):
    (passed if cond else failed).append(name)
    print(f"  {'✅' if cond else '❌'} {name}{(' — ' + extra) if extra else ''}")
    return cond


def login(email):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": "demo12345"}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def h(token, entity="ent_ksc"):
    return {"Authorization": f"Bearer {token}", "X-Entity-Id": entity}


async def rolls_by_status():
    c = AsyncIOMotorClient(MONGO)
    db = c[DBN]
    out = {}
    for st in ("reserved", "available", "quarantine"):
        r = await db.inventory_rolls.find_one(
            {"warehouse_id": "wh_jakarta", "status": st, "rfid_tag_id": {"$ne": None}}, {"_id": 0, "id": 1})
        out[st] = r["id"] if r else None
    # SSOT snapshot: total available_qty in balances + sum roll remaining
    bal = await db.inventory_balances.aggregate(
        [{"$group": {"_id": None, "s": {"$sum": "$available_qty"}}}]).to_list(1)
    rollsum = await db.inventory_rolls.aggregate(
        [{"$match": {"status": {"$in": ["available", "reserved"]}}},
         {"$group": {"_id": None, "s": {"$sum": "$length_remaining"}}}]).to_list(1)
    c.close()
    return out, (bal[0]["s"] if bal else 0), (rollsum[0]["s"] if rollsum else 0)


def main():
    print("\n=== RFID Simulator POC ===")
    wh = login("warehouse@kainnusantara.id")
    ad = login("admin@kainnusantara.id")
    check("login warehouse+admin", bool(wh and ad))

    # 1) Summary
    s = requests.get(f"{BASE}/api/rfid/summary", headers=h(wh), timeout=15).json()
    check("summary: devices>0", s.get("devices_total", 0) > 0, f"devices={s.get('devices_total')}")
    check("summary: tags>0", s.get("tags_active", 0) > 0, f"tags={s.get('tags_active')}")
    check("summary: reads_today>0", s.get("reads_today", 0) > 0, f"reads={s.get('reads_today')}")

    # 2) Tags list
    tg = requests.get(f"{BASE}/api/rfid/tags", headers=h(wh), timeout=15).json()
    check("tags list returns items", tg.get("count", 0) > 0, f"count={tg.get('count')}")
    sample_tag = tg["tags"][0]
    check("tag has epc+roll_id", bool(sample_tag.get("epc") and sample_tag.get("roll_id")))

    # 3) Devices list + admin CRUD + RBAC
    dv = requests.get(f"{BASE}/api/rfid/devices", headers=h(wh), timeout=15).json()
    check("devices list", dv.get("count", 0) > 0, f"count={dv.get('count')}")
    # warehouse CANNOT create device (admin-only)
    rc = requests.post(f"{BASE}/api/rfid/devices", headers=h(wh),
                       json={"name": "X", "type": "gate", "warehouse_id": "wh_jakarta"}, timeout=15)
    check("RBAC: warehouse blocked from device create", rc.status_code == 403, f"status={rc.status_code}")
    # admin creates + patches + deletes
    cr = requests.post(f"{BASE}/api/rfid/devices", headers=h(ad),
                       json={"code": "POC-DEV-1", "name": "POC Reader", "type": "fixed_reader",
                             "warehouse_id": "wh_jakarta", "location": "Zone Test"}, timeout=15)
    check("admin create device", cr.status_code == 200, f"status={cr.status_code}")
    did = cr.json().get("id") if cr.status_code == 200 else None
    if did:
        pt = requests.patch(f"{BASE}/api/rfid/devices/{did}", headers=h(ad), json={"status": "offline"}, timeout=15)
        check("admin patch device offline", pt.status_code == 200 and pt.json().get("status") == "offline")
        dl = requests.delete(f"{BASE}/api/rfid/devices/{did}", headers=h(ad), timeout=15)
        check("admin delete device", dl.status_code == 200)

    # 4) Gate simulate green/red
    statuses, bal_before, roll_before = asyncio.run(rolls_by_status())
    gate = next((d for d in dv["devices"] if d["type"] == "gate" and d["direction"] == "out"), None)
    check("found gate-out device", gate is not None)
    if gate:
        if statuses["reserved"]:
            g = requests.post(f"{BASE}/api/rfid/gate/simulate", headers=h(wh),
                              json={"device_id": gate["id"], "roll_id": statuses["reserved"]}, timeout=15).json()
            check("gate reserved → GREEN", g.get("result") == "green", g.get("reason", ""))
        if statuses["available"]:
            g = requests.post(f"{BASE}/api/rfid/gate/simulate", headers=h(wh),
                              json={"device_id": gate["id"], "roll_id": statuses["available"]}, timeout=15).json()
            check("gate available → RED", g.get("result") == "red", g.get("reason", ""))
        if statuses["quarantine"]:
            g = requests.post(f"{BASE}/api/rfid/gate/simulate", headers=h(wh),
                              json={"device_id": gate["id"], "roll_id": statuses["quarantine"]}, timeout=15).json()
            check("gate quarantine → RED", g.get("result") == "red", g.get("reason", ""))

    # 5) Reader scan
    reader = next((d for d in dv["devices"] if d["type"] == "fixed_reader" and d["status"] == "online"), None)
    if reader:
        sc = requests.post(f"{BASE}/api/rfid/reader/scan", headers=h(wh),
                           json={"device_id": reader["id"]}, timeout=30).json()
        check("reader scan produces reads", sc.get("scanned", 0) > 0, f"scanned={sc.get('scanned')}")

    # 6) Reads log + alerts filter
    rd = requests.get(f"{BASE}/api/rfid/reads?result=red", headers=h(wh), timeout=15).json()
    check("reads filter result=red returns alerts", rd.get("count", 0) > 0, f"red={rd.get('count')}")

    # 7) Locations reconciliation
    loc = requests.get(f"{BASE}/api/rfid/locations", headers=h(wh), timeout=15).json()
    check("locations returns items", loc.get("count", 0) > 0, f"count={loc.get('count')}")
    if loc.get("items"):
        states = {i["state"] for i in loc["items"]}
        check("locations has state field", "state" in loc["items"][0], f"states={states}")

    # 8) SSOT: encoding/gate/scan did NOT change balances
    _, bal_after, roll_after = asyncio.run(rolls_by_status())
    check("SSOT: inventory_balances unchanged after RFID ops", abs(bal_before - bal_after) < 0.001,
          f"{bal_before} vs {bal_after}")
    check("SSOT: roll remaining unchanged after RFID ops", abs(roll_before - roll_after) < 0.001,
          f"{roll_before} vs {roll_after}")

    # 9) Encode flow: retire one tag → roll untagged → re-encode
    retire = requests.delete(f"{BASE}/api/rfid/tags/{sample_tag['id']}", headers=h(wh), timeout=15)
    check("retire tag", retire.status_code == 200)
    un = requests.get(f"{BASE}/api/rfid/untagged-rolls", headers=h(wh), timeout=15).json()
    check("untagged-rolls shows retired roll", any(r["id"] == sample_tag["roll_id"] for r in un.get("rolls", [])),
          f"untagged={un.get('count')}")
    enc = requests.post(f"{BASE}/api/rfid/tags/encode", headers=h(wh),
                        json={"roll_id": sample_tag["roll_id"]}, timeout=15)
    check("re-encode roll", enc.status_code == 200 and enc.json().get("epc"), f"status={enc.status_code}")

    print(f"\n=== RESULT: {len(passed)} passed, {len(failed)} failed ===")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("ALL RFID POC PASSED ✅")


if __name__ == "__main__":
    main()
