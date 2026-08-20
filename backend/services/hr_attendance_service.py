"""HRD H1 services — Absensi (attendance).

Logika murni + I/O Mongo (motor). Di-port dari `scripts/poc_hrd.py` (H-POC PASS):
- haversine + nearest_geofence (validasi radius lokasi).
- compute_metrics (work/late/early_leave/overtime menit) dari clock_in/out + shift.
- determine_status (hadir/telat/flagged).
- resolve_shift/default_shift (shift karyawan → fallback default entitas).
- parse_zkteco_csv (agregasi per emp+hari, multi-punch in=min/out=max) — idempotent.
- upsert_attendance (idempotent per emp+tanggal) dipakai import/ingest/manual.
- recap_for_month (rekap per karyawan).

Timestamp = WIB (UTC+7) eksplisit offset — simpan & tampil konsisten.
"""
import csv
import io
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso

WIB = timezone(timedelta(hours=7))


def wib_now() -> datetime:
    return datetime.now(WIB)


def wib_now_iso() -> str:
    return wib_now().isoformat()


def wib_today() -> str:
    return wib_now().date().isoformat()


# ─── Geofence (haversine) ─────────────────────────────────────────────────────
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_geofence(lat: float, lon: float, fences: List[Dict[str, Any]]):
    """Return (fence, distance_m, inside). Bila tak ada fence → (None, None, False)."""
    best, best_d = None, None
    for f in fences or []:
        try:
            d = haversine_m(float(lat), float(lon), float(f.get("lat", 0)), float(f.get("lon", 0)))
        except (TypeError, ValueError):
            continue
        if best_d is None or d < best_d:
            best, best_d = f, d
    if best is None:
        return None, None, False
    inside = best_d <= float(best.get("radius_m", 150) or 150)
    return best, round(best_d, 1), inside


# ─── Clock metrics ────────────────────────────────────────────────────────────
def _hhmm(s: str):
    try:
        parts = str(s).split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 8, 0


def compute_metrics(clock_in_iso: str, clock_out_iso: str, shift: Dict[str, Any]) -> Dict[str, int]:
    """Hitung work_min, late_min, early_leave_min, overtime_min, std_min dari shift."""
    res = {"work_min": 0, "late_min": 0, "early_leave_min": 0, "overtime_min": 0, "std_min": 0}
    if not clock_in_iso:
        return res
    try:
        ci = datetime.fromisoformat(clock_in_iso)
    except ValueError:
        return res
    hin, min_ = _hhmm(shift.get("jam_in", "08:00"))
    hout, mout = _hhmm(shift.get("jam_out", "17:00"))
    grace = int(shift.get("grace_late_min", 0) or 0)
    res["std_min"] = (hout * 60 + mout) - (hin * 60 + min_)
    sin = ci.replace(hour=hin, minute=min_, second=0, microsecond=0)
    res["late_min"] = max(0, int((ci - sin).total_seconds() // 60) - grace)
    if clock_out_iso:
        try:
            co = datetime.fromisoformat(clock_out_iso)
            work = int((co - ci).total_seconds() // 60)
            res["work_min"] = max(0, work)
            sout = ci.replace(hour=hout, minute=mout, second=0, microsecond=0)
            res["early_leave_min"] = max(0, int((sout - co).total_seconds() // 60))
            res["overtime_min"] = max(0, work - res["std_min"])
        except ValueError:
            pass
    return res


def determine_status(metrics: Dict[str, int], outside_geofence: bool, has_out: bool) -> str:
    if outside_geofence:
        return "flagged"
    if metrics.get("late_min", 0) > 0:
        return "telat"
    return "hadir"


# ─── Shift resolution ─────────────────────────────────────────────────────────
async def default_shift(entity_id: str) -> Dict[str, Any]:
    sh = await db.hr_shifts.find_one(
        {"entity_id": entity_id, "status": "active"}, {"_id": 0}, sort=[("created_at", 1)])
    return sh or {"id": "", "name": "Default", "jam_in": "08:00", "jam_out": "17:00",
                  "grace_late_min": 10}


async def resolve_shift(emp: Optional[Dict[str, Any]], entity_id: str) -> Dict[str, Any]:
    sid = (emp or {}).get("shift_id")
    if sid:
        sh = await db.hr_shifts.find_one({"id": sid}, {"_id": 0})
        if sh:
            return sh
    return await default_shift(entity_id)


# ─── CSV ZKTeco parse ─────────────────────────────────────────────────────────
def csv_to_rows(text: str) -> List[Dict[str, Any]]:
    """CSV teks → list dict baris (header otomatis via DictReader)."""
    return list(csv.DictReader(io.StringIO((text or "").strip())))


def _parse_ts(raw: str) -> Optional[datetime]:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.fromisoformat(raw) if fmt is None else datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_zkteco_rows(rows: List[Dict[str, Any]], device_map: Dict[str, str]):
    """Agregasi baris log mesin per (emp, tanggal): clock_in=min, clock_out=max.

    device_map: {device_user_id(str) -> employee_id}. Baris user tak terpetakan dilewati.
    Return (records, skipped_rows).
    """
    agg: Dict[tuple, Dict[str, Any]] = {}
    skipped = 0
    for r in rows or []:
        rid = str(r.get("user_id") or r.get("enroll_id") or r.get("pin")
                  or r.get("userid") or "").strip()
        emp = device_map.get(rid)
        if not emp:
            if rid:
                skipped += 1
            continue
        ts = _parse_ts(r.get("timestamp") or r.get("time") or r.get("datetime") or "")
        if ts is None:
            continue
        day = ts.date().isoformat()
        key = (emp, day)
        cur = agg.get(key)
        if not cur:
            agg[key] = {"employee_id": emp, "date": day, "ci": ts, "co": ts, "punches": 1}
        else:
            cur["ci"] = min(cur["ci"], ts)
            cur["co"] = max(cur["co"], ts)
            cur["punches"] += 1
    out = []
    for v in agg.values():
        out.append({
            "employee_id": v["employee_id"], "date": v["date"],
            "clock_in": v["ci"].isoformat(),
            "clock_out": v["co"].isoformat() if v["co"] != v["ci"] else "",
            "punches": v["punches"],
        })
    out.sort(key=lambda x: (x["date"], x["employee_id"]))
    return out, skipped


def parse_zkteco_csv(text: str, device_map: Dict[str, str]):
    """Convenience: CSV teks → records (lihat parse_zkteco_rows)."""
    return parse_zkteco_rows(csv_to_rows(text), device_map)


# ─── Upsert attendance (idempotent per emp+tanggal) ───────────────────────────
async def upsert_attendance(emp: Dict[str, Any], date: str, clock_in_iso: str, clock_out_iso: str,
                            method: str, entity_id: str, *, geo: Optional[Dict[str, Any]] = None,
                            photo_url: str = "", note: str = "", status_override: str = "",
                            outside_geofence: bool = False) -> Dict[str, Any]:
    """Buat/update kehadiran (idempotent). Hitung metrics + status, simpan."""
    shift = await resolve_shift(emp, entity_id)
    metrics = compute_metrics(clock_in_iso, clock_out_iso, shift)
    status = status_override or determine_status(metrics, outside_geofence, bool(clock_out_iso))
    existing = await db.hr_attendance.find_one(
        {"employee_id": emp["id"], "date": date}, {"_id": 0})
    doc = {
        "employee_id": emp["id"], "employee_name": emp.get("name", ""),
        "date": date, "shift_id": shift.get("id", ""), "shift_name": shift.get("name", ""),
        "clock_in": clock_in_iso or "", "clock_out": clock_out_iso or "",
        "method": method, "status": status, "outside_geofence": bool(outside_geofence),
        "geo": geo or {}, "photo_url": photo_url or "", "note": note or "",
        "work_min": metrics["work_min"], "late_min": metrics["late_min"],
        "early_leave_min": metrics["early_leave_min"], "overtime_min": metrics["overtime_min"],
        "std_min": metrics["std_min"], "entity_id": entity_id, "updated_at": now_iso(),
        "approved": status != "flagged",
    }
    if existing:
        doc["id"] = existing["id"]
        doc["created_at"] = existing.get("created_at", now_iso())
        await db.hr_attendance.update_one({"id": existing["id"]}, {"$set": doc})
    else:
        doc["id"] = new_id("att")
        doc["created_at"] = now_iso()
        await db.hr_attendance.insert_one(dict(doc))
    return doc


# ─── Recap ────────────────────────────────────────────────────────────────────
def month_range(month: str):
    """`YYYY-MM` → (start_inclusive, end_exclusive) string ISO date."""
    try:
        y, m = month.split("-")
        y, m = int(y), int(m)
    except (ValueError, AttributeError):
        n = wib_now()
        y, m = n.year, n.month
    start = f"{y:04d}-{m:02d}-01"
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return start, f"{ny:04d}-{nm:02d}-01"


def build_recap(rows: List[Dict[str, Any]], emp_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Agregasi kehadiran → rekap per karyawan."""
    by_emp: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        eid = r.get("employee_id")
        rec = by_emp.get(eid)
        if not rec:
            emp = emp_index.get(eid, {})
            rec = by_emp[eid] = {
                "employee_id": eid, "employee_name": r.get("employee_name") or emp.get("name", ""),
                "department_name": emp.get("department_name", ""), "code": emp.get("code", ""),
                "present_days": 0, "late_days": 0, "flagged_days": 0, "leave_days": 0,
                "total_late_min": 0, "total_overtime_min": 0, "total_work_min": 0,
            }
        status = r.get("status", "")
        if status in ("hadir", "telat", "flagged"):
            rec["present_days"] += 1
        if status == "telat":
            rec["late_days"] += 1
        if status == "flagged":
            rec["flagged_days"] += 1
        if status in ("izin", "cuti", "alpha"):
            rec["leave_days"] += 1
        rec["total_late_min"] += int(r.get("late_min", 0) or 0)
        rec["total_overtime_min"] += int(r.get("overtime_min", 0) or 0)
        rec["total_work_min"] += int(r.get("work_min", 0) or 0)
    return sorted(by_emp.values(), key=lambda x: x["employee_name"].lower())
