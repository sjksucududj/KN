#!/usr/bin/env python3
"""
H-POC — Modul HRD & Payroll (Kain Nusantara). PLANNING VALIDATION.

Membuktikan 5 titik berisiko dalam SATU skrip (lihat memory/PLAN_HRD.md §6 H-POC):
  1. Geo clock-in/out + geofence (haversine, status hadir/flag) + durasi & telat.
  2. Komisi Sales -> Payroll (accrue_then_settle): jurnal SEIMBANG, anti double-count.
  3. BPJS + PPh21 (TER bulanan, config-driven) -> payslip net + jurnal payroll SEIMBANG.
  4. WebSocket /api/ws/track lewat ingress publik (wss) -> handshake + echo.
  5. Parse CSV ZKTeco -> hr_attendance (idempotent, tanpa konek device).

Catatan: angka statutory = DEFAULT (akan dipindah ke system_settings.hr; owner koreksi).
Jalankan: python scripts/poc_hrd.py
"""
import asyncio
import csv
import io
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    mark = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{mark}] {name}" + (f"  -> {detail}" if detail else ""))


def section(t):
    print(f"\n=== {t} ===")


# ─────────────────────────────────────────────────────────────────────────────
# 1) GEO / GEOFENCE / CLOCK
# ─────────────────────────────────────────────────────────────────────────────
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def within_geofence(lat, lon, fence):
    d = haversine_m(lat, lon, fence["lat"], fence["lon"])
    return d <= fence["radius_m"], round(d, 1)


def attendance_from_clock(clock_in_iso, clock_out_iso, shift):
    """Hitung durasi kerja, telat, lembur (menit) dari clock_in/out + shift."""
    ci = datetime.fromisoformat(clock_in_iso)
    co = datetime.fromisoformat(clock_out_iso)
    work_min = int((co - ci).total_seconds() // 60)
    # shift jam_in/jam_out "HH:MM" pada tanggal yg sama
    d = ci.date().isoformat()
    sin = datetime.fromisoformat(f"{d}T{shift['jam_in']}:00")
    sout = datetime.fromisoformat(f"{d}T{shift['jam_out']}:00")
    late_min = max(0, int((ci - sin).total_seconds() // 60) - shift.get("grace_min", 0))
    std_min = int((sout - sin).total_seconds() // 60)
    overtime_min = max(0, work_min - std_min)
    return {"work_min": work_min, "late_min": late_min, "overtime_min": overtime_min}


def test_geo():
    section("1. GEO CLOCK-IN/OUT + GEOFENCE")
    office = {"lat": -6.917464, "lon": 107.619123, "radius_m": 150}  # Bandung
    # titik dalam ~40m
    ok_in, d_in = within_geofence(-6.917300, 107.619000, office)
    check("Absen DALAM geofence -> hadir", ok_in and d_in <= 150, f"jarak {d_in} m")
    # titik luar ~2km
    ok_out, d_out = within_geofence(-6.900000, 107.610000, office)
    check("Absen LUAR geofence -> flagged", (not ok_out) and d_out > 150, f"jarak {d_out} m")
    # clock calc
    shift = {"jam_in": "08:00", "jam_out": "17:00", "grace_min": 15}
    a = attendance_from_clock("2026-06-10T08:25:00", "2026-06-10T17:40:00", shift)
    check("Durasi kerja terhitung (9j15m=555m)", a["work_min"] == 555, f"{a['work_min']} m")
    check("Telat terhitung (25m - grace15 = 10m)", a["late_min"] == 10, f"{a['late_min']} m")
    check("Lembur terhitung (555-540=15m)", a["overtime_min"] == 15, f"{a['overtime_min']} m")
    a2 = attendance_from_clock("2026-06-10T07:55:00", "2026-06-10T17:00:00", shift)
    check("Datang awal -> telat 0", a2["late_min"] == 0, f"{a2['late_min']} m")


# ─────────────────────────────────────────────────────────────────────────────
# 2 & 3) PAYROLL (BPJS, PPh21 TER) + JURNAL (komisi accrue_then_settle)
# ─────────────────────────────────────────────────────────────────────────────
# Config default (akan ke system_settings.hr) — owner boleh koreksi (HR-Q6).
HR_CFG = {
    "bpjs": {
        "kesehatan": {"emp": 0.01, "er": 0.04, "ceiling": 12_000_000},
        "jht": {"emp": 0.02, "er": 0.037, "ceiling": None},
        "jp": {"emp": 0.01, "er": 0.02, "ceiling": 10_547_400},
        "jkk_er": 0.0024,  # kelas risiko I
        "jkm_er": 0.0030,
    },
    # PPh21 TER bulanan (PMK 168/2023) — SAMPEL kategori A (TK/0, K/0) subset bracket.
    # Full table -> system_settings.hr.ter. Untuk POC cukup beberapa bracket determinstik.
    "ter_A": [
        (0, 5_400_000, 0.0),
        (5_400_000, 5_650_000, 0.0025),
        (5_650_000, 5_950_000, 0.005),
        (5_950_000, 6_300_000, 0.0075),
        (6_300_000, 6_750_000, 0.01),
        (6_750_000, 7_500_000, 0.0125),
        (7_500_000, 8_550_000, 0.015),
        (8_550_000, 9_650_000, 0.02),
        (9_650_000, 10_050_000, 0.025),
        (10_050_000, 10_350_000, 0.03),
        (10_350_000, 10_700_000, 0.035),
        (10_700_000, 11_050_000, 0.04),
        (11_050_000, 11_600_000, 0.05),
        (11_600_000, 12_500_000, 0.06),
        (12_500_000, 13_750_000, 0.07),
        (13_750_000, 15_100_000, 0.08),
        (15_100_000, 16_950_000, 0.09),
        (16_950_000, 19_750_000, 0.10),
        (19_750_000, 24_150_000, 0.11),
        (24_150_000, 26_450_000, 0.12),
        (26_450_000, 28_000_000, 0.13),
        (28_000_000, 30_050_000, 0.14),
        (30_050_000, 32_400_000, 0.15),
        (32_400_000, 10**12, 0.19),
    ],
}


def ter_rate_A(gross):
    for lo, hi, r in HR_CFG["ter_A"]:
        if lo <= gross < hi:
            return r
    return HR_CFG["ter_A"][-1][2]


def bpjs_breakdown(base):
    b = HR_CFG["bpjs"]
    kes_base = min(base, b["kesehatan"]["ceiling"])
    jp_base = min(base, b["jp"]["ceiling"])
    emp = {
        "kesehatan": round(kes_base * b["kesehatan"]["emp"], 2),
        "jht": round(base * b["jht"]["emp"], 2),
        "jp": round(jp_base * b["jp"]["emp"], 2),
    }
    er = {
        "kesehatan": round(kes_base * b["kesehatan"]["er"], 2),
        "jht": round(base * b["jht"]["er"], 2),
        "jp": round(jp_base * b["jp"]["er"], 2),
        "jkk": round(base * b["jkk_er"], 2),
        "jkm": round(base * b["jkm_er"], 2),
    }
    return emp, er, round(sum(emp.values()), 2), round(sum(er.values()), 2)


def build_payslip(base_salary, allowances, overtime, commission):
    salary_earnings = round(base_salary + allowances + overtime, 2)
    gross = round(salary_earnings + commission, 2)
    emp, er, emp_total, er_total = bpjs_breakdown(base_salary)
    pph21 = round(gross * ter_rate_A(gross), 2)
    net = round(gross - emp_total - pph21, 2)
    return {
        "salary_earnings": salary_earnings, "commission": round(commission, 2),
        "gross": gross, "bpjs_emp": emp, "bpjs_er": er,
        "bpjs_emp_total": emp_total, "bpjs_er_total": er_total,
        "pph21": pph21, "net": net,
    }


def build_payroll_journal(slip, mode="accrue_then_settle"):
    """Jurnal payroll run (lihat PLAN_HRD §4.3/§4.4). Return (lines, balanced)."""
    salary = slip["salary_earnings"]
    comm = slip["commission"]
    emp_total = slip["bpjs_emp_total"]
    er_total = slip["bpjs_er_total"]
    pph21 = slip["pph21"]
    net = slip["net"]
    lines = []
    # Debit
    lines.append({"acc": "6-6000 Beban Gaji & Upah", "dr": salary, "cr": 0})
    lines.append({"acc": "6-6100 Beban BPJS (Perusahaan)", "dr": er_total, "cr": 0})
    if mode == "accrue_then_settle" and comm > 0:
        # komisi sudah di-akrual via crm post-gl (Dr 6-5000/Cr 2-1500); payroll
        # MEMINDAHKAN liabilitas insentif ke hutang gaji (TIDAK re-expense).
        lines.append({"acc": "2-1500 Hutang Insentif", "dr": comm, "cr": 0})
    elif comm > 0:
        # mode expense_in_payroll: komisi jadi beban di payroll
        lines.append({"acc": "6-5000 Beban Insentif", "dr": comm, "cr": 0})
    # Credit
    lines.append({"acc": "2-1600 Hutang Gaji", "dr": 0, "cr": net})
    lines.append({"acc": "2-1700 Hutang BPJS", "dr": 0, "cr": round(emp_total + er_total, 2)})
    lines.append({"acc": "2-1800 Hutang PPh21", "dr": 0, "cr": pph21})
    tot_dr = round(sum(x["dr"] for x in lines), 2)
    tot_cr = round(sum(x["cr"] for x in lines), 2)
    return lines, abs(tot_dr - tot_cr) < 0.01, tot_dr, tot_cr


async def test_payroll(db):
    section("2. KOMISI SALES -> PAYROLL (accrue_then_settle, anti double-count)")
    from services.sales_force_service import compute_commission

    sales = await db.users.find({"role": "sales"}, {"_id": 0, "id": 1, "name": 1}).to_list(10)
    period = "2026-06"
    real_comm = None
    for s in sales:
        try:
            res = await compute_commission(s["id"], period, "ent_ksc")
            ti = res.get("total_incentive", 0)
            print(f"    komisi {s['name']} {period}: total_incentive=Rp {ti:,.0f} (strategy={res.get('strategy')})")
            if real_comm is None:
                real_comm = ti
            if ti and ti > 0:
                real_comm = ti
        except Exception as e:  # noqa: BLE001
            print(f"    compute_commission {s['id']} error: {e}")
    check("compute_commission terpanggil & return total_incentive", real_comm is not None,
          f"contoh Rp {(real_comm or 0):,.0f}")

    # Kasus A: pakai komisi NYATA dari engine (apa pun nilainya) + gaji sintetis
    slipA = build_payslip(base_salary=6_000_000, allowances=1_500_000, overtime=300_000,
                          commission=(real_comm or 0))
    jA, balA, drA, crA = build_payroll_journal(slipA)
    check("Jurnal payroll (komisi nyata) SEIMBANG", balA, f"Dr={drA:,.0f} Cr={crA:,.0f}")

    # Kasus B: komisi non-nol besar -> buktikan accrue_then_settle robust
    slipB = build_payslip(base_salary=8_000_000, allowances=2_000_000, overtime=0,
                          commission=5_000_000)
    jB, balB, drB, crB = build_payroll_journal(slipB)
    check("Jurnal payroll (komisi 5jt) SEIMBANG", balB, f"Dr={drB:,.0f} Cr={crB:,.0f}")
    # anti double-count: komisi TIDAK menambah Beban Gaji (6-6000)
    beban_gaji = next(x["dr"] for x in jB if x["acc"].startswith("6-6000"))
    check("Anti double-count: komisi tidak masuk Beban Gaji 6-6000", beban_gaji == slipB["salary_earnings"],
          f"Beban Gaji=Rp {beban_gaji:,.0f} (=earnings tanpa komisi)")
    has_settle = any(x["acc"].startswith("2-1500") and x["dr"] == 5_000_000 for x in jB)
    check("Komisi diselesaikan via Dr 2-1500 Hutang Insentif", has_settle, "settle liabilitas insentif")

    section("3. BPJS + PPh21 (TER) -> PAYSLIP + JURNAL")
    # Verifikasi BPJS karyawan untuk gaji 8jt: Kes1%+JHT2%+JP1% = 80k+160k+80k=320k
    empB = slipB["bpjs_emp"]
    check("BPJS Kesehatan emp 1% (8jt=80k)", empB["kesehatan"] == 80_000, f"Rp {empB['kesehatan']:,.0f}")
    check("BPJS JHT emp 2% (8jt=160k)", empB["jht"] == 160_000, f"Rp {empB['jht']:,.0f}")
    check("BPJS JP emp 1% (8jt=80k)", empB["jp"] == 80_000, f"Rp {empB['jp']:,.0f}")
    # PPh21 TER untuk gross slipB (=10jt + komisi5jt=15jt) -> bracket determinstik
    expect_rate = ter_rate_A(slipB["gross"])
    check("PPh21 TER terhitung (gross 15jt)", slipB["pph21"] == round(slipB["gross"] * expect_rate, 2),
          f"rate={expect_rate*100:.2f}% -> Rp {slipB['pph21']:,.0f}")
    # net = gross - emp_bpjs - pph21
    expect_net = round(slipB["gross"] - slipB["bpjs_emp_total"] - slipB["pph21"], 2)
    check("Net pay = gross - BPJS emp - PPh21", slipB["net"] == expect_net, f"Net=Rp {slipB['net']:,.0f}")
    check("Gross 0 -> PPh21 0 (di bawah threshold)", build_payslip(5_000_000, 0, 0, 0)["pph21"] == 0,
          "gaji 5jt < 5.4jt TER threshold")


# ─────────────────────────────────────────────────────────────────────────────
# 4) WEBSOCKET lewat ingress publik
# ─────────────────────────────────────────────────────────────────────────────
async def test_websocket():
    section("4. WEBSOCKET /api/ws/track LEWAT INGRESS (wss publik)")
    backend_url = None
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                backend_url = ln.split("=", 1)[1].strip()
    ws_url = backend_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws/track"
    print(f"    connect: {ws_url}")
    try:
        import websockets
        async with websockets.connect(ws_url, open_timeout=15, close_timeout=5) as ws:
            hello = await asyncio.wait_for(ws.recv(), timeout=10)
            await ws.send('{"lat":-6.9,"lon":107.6}')
            ack = await asyncio.wait_for(ws.recv(), timeout=10)
            check("WS handshake (upgrade lewat ingress) sukses", True, f"hello={hello[:40]}")
            check("WS echo/ack diterima", "ack" in ack, f"ack={ack[:60]}")
    except Exception as e:  # noqa: BLE001
        check("WS handshake lewat ingress", False, f"GAGAL: {type(e).__name__}: {e} -> FALLBACK POLLING")


# ─────────────────────────────────────────────────────────────────────────────
# 5) PARSE CSV ZKTeco -> hr_attendance (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
SAMPLE_ZK_CSV = """user_id,timestamp,status
1001,2026-06-10 08:01:12,0
1001,2026-06-10 17:05:44,1
1002,2026-06-10 07:58:00,0
1002,2026-06-10 12:00:00,1
1002,2026-06-10 12:45:00,0
1002,2026-06-10 17:30:00,1
1001,2026-06-11 08:10:00,0
1001,2026-06-11 17:00:00,1
"""

DEVICE_MAP = {"1001": "emp_poc_a", "1002": "emp_poc_b"}  # device enroll id -> employee


def parse_zkteco_csv(text, device_map):
    """Parse log mesin ZKTeco -> agregasi per (emp, tanggal): clock_in=min, clock_out=max."""
    rows = list(csv.DictReader(io.StringIO(text)))
    agg = {}
    for r in rows:
        emp = device_map.get(r["user_id"].strip())
        if not emp:
            continue
        ts = datetime.fromisoformat(r["timestamp"].strip())
        day = ts.date().isoformat()
        key = (emp, day)
        cur = agg.get(key)
        if not cur:
            agg[key] = {"emp_id": emp, "date": day, "clock_in": ts, "clock_out": ts,
                        "punches": 1, "method": "fingerprint"}
        else:
            cur["clock_in"] = min(cur["clock_in"], ts)
            cur["clock_out"] = max(cur["clock_out"], ts)
            cur["punches"] += 1
    out = []
    for v in agg.values():
        v["clock_in"] = v["clock_in"].isoformat()
        v["clock_out"] = v["clock_out"].isoformat()
        out.append(v)
    return out


async def upsert_attendance(db, recs):
    """Idempotent upsert per (emp_id, date) ke koleksi sementara POC."""
    coll = db["_poc_hr_attendance"]
    for r in recs:
        await coll.update_one({"emp_id": r["emp_id"], "date": r["date"]},
                              {"$set": r}, upsert=True)
    return await coll.count_documents({})


async def test_csv(db):
    section("5. PARSE CSV ZKTeco -> hr_attendance (IDEMPOTENT)")
    await db["_poc_hr_attendance"].delete_many({})
    recs = parse_zkteco_csv(SAMPLE_ZK_CSV, DEVICE_MAP)
    check("Parse CSV -> 3 baris kehadiran (2 emp x hari)", len(recs) == 3, f"{len(recs)} rec")
    # cek agregasi clock_in/out emp_poc_b 2026-06-10 (4 punch -> in 07:58, out 17:30)
    b = next((r for r in recs if r["emp_id"] == "emp_poc_b" and r["date"] == "2026-06-10"), None)
    check("Agregasi multi-punch benar (in=07:58, out=17:30, 4 punch)",
          bool(b) and b["clock_in"].endswith("07:58:00") and b["clock_out"].endswith("17:30:00") and b["punches"] == 4,
          f"in={b['clock_in'][-8:]} out={b['clock_out'][-8:]} punch={b['punches']}" if b else "tidak ada")
    c1 = await upsert_attendance(db, recs)
    c2 = await upsert_attendance(db, recs)  # jalankan lagi -> idempotent
    check("Idempotent: jalankan 2x -> jumlah doc stabil (3)", c1 == 3 and c2 == 3, f"run1={c1} run2={c2}")
    await db["_poc_hr_attendance"].delete_many({})  # cleanup


# ─────────────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 64)
    print("  H-POC — MODUL HRD & PAYROLL (Kain Nusantara)")
    print("=" * 64)
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    try:
        test_geo()
        await test_payroll(db)
        await test_websocket()
        await test_csv(db)
    finally:
        c.close()
    print("\n" + "=" * 64)
    print(f"  RESULT: {PASS} PASS / {FAIL} FAIL")
    print("=" * 64)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
