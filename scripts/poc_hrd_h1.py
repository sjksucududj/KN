#!/usr/bin/env python3
"""H1 smoke test — Absensi (live API). Validasi end-to-end FASE H1.

Cakupan: login, seeded shift/geofence/device, CRUD shift/geofence/device,
import CSV ZKTeco (idempotent), kehadiran harian + rekap, manual entry,
clock-in/out (ESS), RBAC (sales tak bisa kelola).
Jalankan: python scripts/poc_hrd_h1.py
"""
import sys
import requests

BASE = "http://localhost:8001/api"
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    mark = "PASS" if cond else "FAIL"
    PASS += 1 if cond else 0
    FAIL += 0 if cond else 1
    print(f"  [{mark}] {name}" + (f"  -> {detail}" if detail else ""))


def login(email, pw="demo12345"):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    print("=" * 64)
    print("  H1 SMOKE — ABSENSI (live API)")
    print("=" * 64)
    admin = login("admin@kainnusantara.id")
    sales = login("sales@kainnusantara.id")

    print("\n=== 1. SEEDED MASTERS ===")
    shifts = requests.get(f"{BASE}/hr/shifts", headers=H(admin)).json()
    geos = requests.get(f"{BASE}/hr/geofences", headers=H(admin)).json()
    devs = requests.get(f"{BASE}/hr/devices", headers=H(admin)).json()
    check("Shift ter-seed >=1", isinstance(shifts, list) and len(shifts) >= 1, f"{len(shifts)} shift")
    check("Geofence ter-seed >=1", isinstance(geos, list) and len(geos) >= 1, f"{len(geos)} geofence")
    check("Device ter-seed >=1", isinstance(devs, list) and len(devs) >= 1, f"{len(devs)} device")

    print("\n=== 2. CRUD SHIFT ===")
    cr = requests.post(f"{BASE}/hr/shifts", headers=H(admin),
                       json={"name": "Shift Sore", "jam_in": "13:00", "jam_out": "21:00",
                             "grace_late_min": 5})
    check("Create shift 200", cr.status_code == 200, f"http {cr.status_code}")
    sid = cr.json().get("id") if cr.status_code == 200 else None
    if sid:
        pa = requests.patch(f"{BASE}/hr/shifts/{sid}", headers=H(admin),
                            json={"data": {"grace_late_min": 15}})
        check("Patch shift grace=15", pa.status_code == 200 and pa.json().get("grace_late_min") == 15)
        de = requests.delete(f"{BASE}/hr/shifts/{sid}", headers=H(admin))
        check("Delete (soft) shift", de.status_code == 200 and de.json().get("status") == "inactive")

    print("\n=== 3. CRUD GEOFENCE ===")
    cg = requests.post(f"{BASE}/hr/geofences", headers=H(admin),
                       json={"name": "Gudang Cikarang", "lat": -6.305, "lon": 107.158, "radius_m": 100})
    check("Create geofence 200", cg.status_code == 200, f"http {cg.status_code}")
    gid = cg.json().get("id") if cg.status_code == 200 else None
    if gid:
        de = requests.delete(f"{BASE}/hr/geofences/{gid}", headers=H(admin))
        check("Delete geofence", de.status_code == 200)

    print("\n=== 4. IMPORT CSV ZKTeco (idempotent) ===")
    emps = requests.get(f"{BASE}/hr/employees", headers=H(admin)).json()
    mapped = [e for e in emps if e.get("device_user_id")]
    check("Karyawan punya device_user_id (seed)", len(mapped) >= 2, f"{len(mapped)} ber-ID mesin")
    if len(mapped) >= 2:
        a, b = mapped[0]["device_user_id"], mapped[1]["device_user_id"]
        csv_text = (
            "user_id,timestamp,status\n"
            f"{a},2026-05-04 08:01:00,0\n{a},2026-05-04 17:06:00,1\n"
            f"{b},2026-05-04 07:55:00,0\n{b},2026-05-04 12:00:00,1\n"
            f"{b},2026-05-04 12:45:00,0\n{b},2026-05-04 17:31:00,1\n"
        )
        r1 = requests.post(f"{BASE}/hr/attendance/import", headers=H(admin),
                           json={"csv_text": csv_text})
        check("Import #1 → 2 kehadiran", r1.status_code == 200 and r1.json().get("imported") == 2,
              f"{r1.json()}")
        r2 = requests.post(f"{BASE}/hr/attendance/import", headers=H(admin),
                           json={"csv_text": csv_text})
        # idempotent: jumlah record tanggal itu tetap 2
        day = requests.get(f"{BASE}/hr/attendance", headers=H(admin),
                           params={"date_from": "2026-05-04", "date_to": "2026-05-04"}).json()
        check("Idempotent: re-import → tetap 2 record", isinstance(day, list) and len(day) == 2,
              f"{len(day)} record")
        brec = next((x for x in day if x["employee_id"] == mapped[1]["id"]), None)
        check("Multi-punch tergabung (work_min>0, method fingerprint)",
              bool(brec) and brec.get("work_min", 0) > 0 and brec.get("method") == "fingerprint",
              f"work_min={brec.get('work_min') if brec else '-'}")

    print("\n=== 5. MANUAL ENTRY ===")
    if emps:
        eid = emps[0]["id"]
        rm = requests.post(f"{BASE}/hr/attendance/manual", headers=H(admin),
                           json={"employee_id": eid, "date": "2026-05-05", "status": "izin",
                                 "note": "Izin keperluan keluarga"})
        check("Manual entry status izin", rm.status_code == 200 and rm.json().get("status") == "izin",
              f"http {rm.status_code}")

    print("\n=== 6. REKAP PERIODE ===")
    rc = requests.get(f"{BASE}/hr/attendance/recap", headers=H(admin), params={"month": "2026-05"})
    ok = rc.status_code == 200 and "rows" in rc.json() and "totals" in rc.json()
    check("Rekap Mei 2026 ada rows+totals", ok,
          f"present_days={rc.json().get('totals', {}).get('present_days') if ok else '-'}")

    print("\n=== 7. ESS CLOCK-IN/OUT (sales) ===")
    me = requests.get(f"{BASE}/hr/attendance/me", headers=H(sales))
    check("GET /hr/attendance/me (sales) 200", me.status_code == 200,
          f"http {me.status_code}")
    # clock-in dalam radius Bandung (geofence seed) — toleransi 409 bila sudah ter-seed hari ini
    ci = requests.post(f"{BASE}/hr/attendance/clock-in", headers=H(sales),
                       json={"lat": -6.917300, "lon": 107.619000, "accuracy": 12})
    if ci.status_code == 200:
        check("Clock-in (dalam fence) → hadir/telat", ci.json().get("status") in ("hadir", "telat"),
              f"status={ci.json().get('status')}")
        co = requests.post(f"{BASE}/hr/attendance/clock-out", headers=H(sales),
                           json={"lat": -6.917300, "lon": 107.619000})
        check("Clock-out → work_min>0", co.status_code == 200 and co.json().get("work_min", 0) > 0,
              f"work_min={co.json().get('work_min') if co.status_code == 200 else '-'}")
    else:
        check("Clock-in idempotent (sudah ada hari ini = 409)", ci.status_code == 409,
              f"http {ci.status_code} (seeded today)")

    print("\n=== 8. RBAC (sales tak boleh kelola absensi) ===")
    rb = requests.post(f"{BASE}/hr/shifts", headers=H(sales), json={"name": "X"})
    check("Sales POST /hr/shifts → 403", rb.status_code == 403, f"http {rb.status_code}")

    print("\n" + "=" * 64)
    print(f"  RESULT: {PASS} PASS / {FAIL} FAIL")
    print("=" * 64)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
