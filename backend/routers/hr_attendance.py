"""HRD H1 router — Absensi (attendance): shift, geofence, device, clock-in/out,
import CSV ZKTeco, ingest (bridge), rekap, manual & approve.

Koleksi kanonik (entity-scoped): hr_shifts (shift_), hr_geofences (geo_),
hr_attendance (att_), hr_devices (dev_). Lihat ENTITY_REGISTRY.md + memory/PLAN_HRD.md §6 H1.

RBAC: read = hr.view · CRUD shift/geofence/device + manual/approve/import = hr.manage_attendance.
ESS clock-in/out + /me = autentikasi + karyawan ter-link (lihat data SENDIRI).
Ingest (agen jembatan on-prem) = auth device_token (tanpa sesi).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, current_user, audit
from core_utils import new_id, now_iso, safe_doc
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import GenericPatch
from schemas_hr_attendance import (
    HrShiftCreate, HrGeofenceCreate, HrDeviceCreate,
    ClockInInput, ClockOutInput, ManualAttendanceInput,
    AttendanceImportInput, AttendanceIngestInput,
)
from services import hr_attendance_service as att
from services import hr_service

router = APIRouter(prefix="/api")

SHIFT_FIELDS = {"name", "code", "jam_in", "jam_out", "grace_late_min", "break_min",
                "work_days", "status", "entity_id"}
GEO_FIELDS = {"name", "lat", "lon", "radius_m", "address", "status", "entity_id"}
DEVICE_FIELDS = {"name", "code", "location", "status", "entity_id"}
ATT_PATCH_FIELDS = {"status", "note", "approved", "clock_in", "clock_out"}


async def _emp_for_user(request: Request) -> Dict[str, Any]:
    user = await current_user(request)
    emp = safe_doc(await db.hr_employees.find_one({"user_id": user["id"]}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Profil karyawan belum tersedia untuk akun Anda")
    return emp


def _geo_block(lat, lon, accuracy, fence, dist, inside) -> Dict[str, Any]:
    return {
        "lat": lat, "lon": lon, "accuracy": accuracy,
        "geofence_id": (fence or {}).get("id", ""),
        "geofence_name": (fence or {}).get("name", ""),
        "distance_m": dist, "inside": bool(inside),
    }


async def _active_geofences(entity_id: str) -> List[Dict[str, Any]]:
    return await db.hr_geofences.find(
        {"entity_id": entity_id, "status": "active"}, {"_id": 0}).to_list(200)


# ════════════════════════════ SHIFTS ════════════════════════════════════════
@router.get("/hr/shifts")
async def list_shifts(request: Request, entity_id: str = None) -> List[Dict[str, Any]]:
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    q = resolve_list_scope("hr_shifts", {}, ctx, entity_id)
    return await db.hr_shifts.find(q, {"_id": 0}).sort("jam_in", 1).to_list(500)


@router.post("/hr/shifts")
async def create_shift(payload: HrShiftCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama shift wajib diisi")
    n = await db.hr_shifts.count_documents({})
    doc = {
        "id": new_id("shift"), "code": payload.code.strip() or f"SHIFT-{n + 1:03d}",
        "name": payload.name.strip(), "jam_in": payload.jam_in, "jam_out": payload.jam_out,
        "grace_late_min": int(payload.grace_late_min or 0), "break_min": int(payload.break_min or 0),
        "work_days": payload.work_days or [1, 2, 3, 4, 5], "status": "active",
        "entity_id": payload.entity_id or ctx.active_entity_id,
        "created_by": actor["name"], "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.hr_shifts.insert_one(doc)
    await audit(actor["name"], "hr_shift_created", "hr_shift", doc["id"], {"name": doc["name"]})
    return safe_doc(doc)


@router.patch("/hr/shifts/{shift_id}")
async def update_shift(shift_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    cur = safe_doc(await db.hr_shifts.find_one({"id": shift_id}, {"_id": 0}))
    if not cur:
        raise HTTPException(status_code=404, detail="Shift tidak ditemukan")
    assert_entity_access(cur, "hr_shifts", ctx)
    updates = {k: v for k, v in (payload.data or {}).items() if k in SHIFT_FIELDS}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    updates["updated_at"] = now_iso()
    updated = await db.hr_shifts.find_one_and_update(
        {"id": shift_id}, {"$set": updates}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_shift_updated", "hr_shift", shift_id, updates)
    return safe_doc(updated)


@router.delete("/hr/shifts/{shift_id}")
async def deactivate_shift(shift_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    cur = safe_doc(await db.hr_shifts.find_one({"id": shift_id}, {"_id": 0}))
    if not cur:
        raise HTTPException(status_code=404, detail="Shift tidak ditemukan")
    assert_entity_access(cur, "hr_shifts", ctx)
    updated = await db.hr_shifts.find_one_and_update(
        {"id": shift_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_shift_deactivated", "hr_shift", shift_id, {})
    return safe_doc(updated)


# ════════════════════════════ GEOFENCES ═════════════════════════════════════
@router.get("/hr/geofences")
async def list_geofences(request: Request, entity_id: str = None) -> List[Dict[str, Any]]:
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    q = resolve_list_scope("hr_geofences", {}, ctx, entity_id)
    return await db.hr_geofences.find(q, {"_id": 0}).sort("name", 1).to_list(500)


@router.post("/hr/geofences")
async def create_geofence(payload: HrGeofenceCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama lokasi wajib diisi")
    doc = {
        "id": new_id("geo"), "name": payload.name.strip(),
        "lat": float(payload.lat or 0), "lon": float(payload.lon or 0),
        "radius_m": int(payload.radius_m or 150), "address": payload.address or "",
        "status": "active", "entity_id": payload.entity_id or ctx.active_entity_id,
        "created_by": actor["name"], "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.hr_geofences.insert_one(doc)
    await audit(actor["name"], "hr_geofence_created", "hr_geofence", doc["id"], {"name": doc["name"]})
    return safe_doc(doc)


@router.patch("/hr/geofences/{geo_id}")
async def update_geofence(geo_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    cur = safe_doc(await db.hr_geofences.find_one({"id": geo_id}, {"_id": 0}))
    if not cur:
        raise HTTPException(status_code=404, detail="Geofence tidak ditemukan")
    assert_entity_access(cur, "hr_geofences", ctx)
    updates = {k: v for k, v in (payload.data or {}).items() if k in GEO_FIELDS}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    for nf in ("lat", "lon"):
        if nf in updates:
            updates[nf] = float(updates[nf] or 0)
    if "radius_m" in updates:
        updates["radius_m"] = int(updates["radius_m"] or 150)
    updates["updated_at"] = now_iso()
    updated = await db.hr_geofences.find_one_and_update(
        {"id": geo_id}, {"$set": updates}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_geofence_updated", "hr_geofence", geo_id, updates)
    return safe_doc(updated)


@router.delete("/hr/geofences/{geo_id}")
async def deactivate_geofence(geo_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    cur = safe_doc(await db.hr_geofences.find_one({"id": geo_id}, {"_id": 0}))
    if not cur:
        raise HTTPException(status_code=404, detail="Geofence tidak ditemukan")
    assert_entity_access(cur, "hr_geofences", ctx)
    updated = await db.hr_geofences.find_one_and_update(
        {"id": geo_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_geofence_deactivated", "hr_geofence", geo_id, {})
    return safe_doc(updated)


# ════════════════════════════ DEVICES ═══════════════════════════════════════
@router.get("/hr/devices")
async def list_devices(request: Request, entity_id: str = None) -> List[Dict[str, Any]]:
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    q = resolve_list_scope("hr_devices", {}, ctx, entity_id)
    rows = await db.hr_devices.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    return rows


@router.post("/hr/devices")
async def create_device(payload: HrDeviceCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama perangkat wajib diisi")
    doc = {
        "id": new_id("dev"), "name": payload.name.strip(), "code": payload.code.strip(),
        "location": payload.location or "", "device_token": new_id("devtok"),
        "last_sync": "", "status": "active",
        "entity_id": payload.entity_id or ctx.active_entity_id,
        "created_by": actor["name"], "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.hr_devices.insert_one(doc)
    await audit(actor["name"], "hr_device_created", "hr_device", doc["id"], {"name": doc["name"]})
    return safe_doc(doc)


@router.patch("/hr/devices/{dev_id}")
async def update_device(dev_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    cur = safe_doc(await db.hr_devices.find_one({"id": dev_id}, {"_id": 0}))
    if not cur:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan")
    assert_entity_access(cur, "hr_devices", ctx)
    updates = {k: v for k, v in (payload.data or {}).items() if k in DEVICE_FIELDS}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    updates["updated_at"] = now_iso()
    updated = await db.hr_devices.find_one_and_update(
        {"id": dev_id}, {"$set": updates}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_device_updated", "hr_device", dev_id, updates)
    return safe_doc(updated)


@router.delete("/hr/devices/{dev_id}")
async def deactivate_device(dev_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    cur = safe_doc(await db.hr_devices.find_one({"id": dev_id}, {"_id": 0}))
    if not cur:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan")
    assert_entity_access(cur, "hr_devices", ctx)
    updated = await db.hr_devices.find_one_and_update(
        {"id": dev_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_device_deactivated", "hr_device", dev_id, {})
    return safe_doc(updated)


# ════════════════════════════ ATTENDANCE (read) ═════════════════════════════
@router.get("/hr/attendance")
async def list_attendance(request: Request, entity_id: str = None, date_from: str = None,
                          date_to: str = None, employee_id: str = None,
                          status: str = None) -> List[Dict[str, Any]]:
    """Kehadiran harian (scoped). Default: hari ini bila tanpa rentang tanggal."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    q: Dict[str, Any] = {}
    if employee_id:
        q["employee_id"] = employee_id
    if status:
        q["status"] = status
    if date_from or date_to:
        rng: Dict[str, Any] = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["date"] = rng
    else:
        q["date"] = att.wib_today()
    q = resolve_list_scope("hr_attendance", q, ctx, entity_id)
    rows = await db.hr_attendance.find(q, {"_id": 0}).sort([("date", -1), ("clock_in", 1)]).to_list(3000)
    return rows


@router.get("/hr/attendance/recap")
async def attendance_recap(request: Request, entity_id: str = None, month: str = None) -> Dict[str, Any]:
    """Rekap kehadiran per karyawan untuk satu bulan (YYYY-MM)."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    month = month or att.wib_now().strftime("%Y-%m")
    start, end = att.month_range(month)
    q = resolve_list_scope("hr_attendance", {"date": {"$gte": start, "$lt": end}}, ctx, entity_id)
    rows = await db.hr_attendance.find(q, {"_id": 0}).to_list(20000)
    # index karyawan (nama/kode/departemen) untuk enrich
    emp_q = resolve_list_scope("hr_employees", {}, ctx, entity_id)
    emps = await db.hr_employees.find(
        emp_q, {"_id": 0, "id": 1, "name": 1, "code": 1, "department_id": 1, "entity_id": 1}).to_list(5000)
    omap = await hr_service.org_unit_map(list({e.get("entity_id") for e in emps if e.get("entity_id")}))
    emp_index = {}
    for e in emps:
        dep = omap.get(e.get("department_id"))
        emp_index[e["id"]] = {"name": e.get("name", ""), "code": e.get("code", ""),
                              "department_name": dep["name"] if dep else ""}
    recap = att.build_recap(rows, emp_index)
    totals = {
        "employees": len(recap),
        "present_days": sum(r["present_days"] for r in recap),
        "late_days": sum(r["late_days"] for r in recap),
        "flagged_days": sum(r["flagged_days"] for r in recap),
        "total_overtime_min": sum(r["total_overtime_min"] for r in recap),
    }
    return {"month": month, "totals": totals, "rows": recap}


@router.get("/hr/attendance/me")
async def my_attendance(request: Request) -> Dict[str, Any]:
    """ESS — kehadiran hari ini + 14 rekaman terakhir milik user login."""
    emp = await _emp_for_user(request)
    today = att.wib_today()
    today_rec = safe_doc(await db.hr_attendance.find_one(
        {"employee_id": emp["id"], "date": today}, {"_id": 0}))
    recent = await db.hr_attendance.find(
        {"employee_id": emp["id"]}, {"_id": 0}).sort("date", -1).to_list(14)
    shift = await att.resolve_shift(emp, emp.get("entity_id", ""))
    return {"employee": {"id": emp["id"], "name": emp.get("name", ""), "code": emp.get("code", "")},
            "today": today_rec, "recent": recent,
            "shift": {"name": shift.get("name", ""), "jam_in": shift.get("jam_in", ""),
                      "jam_out": shift.get("jam_out", "")},
            "server_time": att.wib_now_iso()}


# ════════════════════════════ CLOCK-IN / CLOCK-OUT (ESS) ════════════════════
@router.post("/hr/attendance/clock-in")
async def clock_in(payload: ClockInInput, request: Request) -> Dict[str, Any]:
    emp = await _emp_for_user(request)
    entity_id = emp.get("entity_id", "")
    date = att.wib_today()
    existing = await db.hr_attendance.find_one({"employee_id": emp["id"], "date": date}, {"_id": 0})
    if existing and existing.get("clock_in"):
        raise HTTPException(status_code=409, detail="Anda sudah clock-in hari ini.")
    ci_iso = att.wib_now_iso()
    outside = False
    geo_block: Dict[str, Any] = {}
    fences = await _active_geofences(entity_id)
    if payload.lat is not None and payload.lon is not None:
        fence, dist, inside = att.nearest_geofence(payload.lat, payload.lon, fences)
        if fences:
            outside = not inside
        geo_block = _geo_block(payload.lat, payload.lon, payload.accuracy, fence, dist, inside)
    else:
        geo_block = {"lat": None, "lon": None, "no_location": True}
    shift = await att.resolve_shift(emp, entity_id)
    metrics = att.compute_metrics(ci_iso, "", shift)
    status = att.determine_status(metrics, outside, False)
    doc = {
        "id": (existing or {}).get("id") or new_id("att"),
        "employee_id": emp["id"], "employee_name": emp.get("name", ""), "date": date,
        "shift_id": shift.get("id", ""), "shift_name": shift.get("name", ""),
        "clock_in": ci_iso, "clock_out": "", "method": "geo", "status": status,
        "outside_geofence": outside, "geo": {"in": geo_block}, "photo_url": payload.photo_url or "",
        "note": payload.note or "", "work_min": 0, "late_min": metrics["late_min"],
        "early_leave_min": 0, "overtime_min": 0, "std_min": metrics["std_min"],
        "approved": status != "flagged", "entity_id": entity_id,
        "created_at": (existing or {}).get("created_at") or now_iso(), "updated_at": now_iso(),
    }
    if existing:
        await db.hr_attendance.update_one({"id": doc["id"]}, {"$set": doc})
    else:
        await db.hr_attendance.insert_one(dict(doc))
    await audit(emp.get("name", ""), "hr_clock_in", "hr_attendance", doc["id"],
                {"status": status, "outside": outside})
    return safe_doc(doc)


@router.post("/hr/attendance/clock-out")
async def clock_out(payload: ClockOutInput, request: Request) -> Dict[str, Any]:
    emp = await _emp_for_user(request)
    entity_id = emp.get("entity_id", "")
    date = att.wib_today()
    existing = safe_doc(await db.hr_attendance.find_one(
        {"employee_id": emp["id"], "date": date}, {"_id": 0}))
    if not existing or not existing.get("clock_in"):
        raise HTTPException(status_code=400, detail="Anda belum clock-in hari ini.")
    if existing.get("clock_out"):
        raise HTTPException(status_code=409, detail="Anda sudah clock-out hari ini.")
    co_iso = att.wib_now_iso()
    shift = await att.resolve_shift(emp, entity_id)
    metrics = att.compute_metrics(existing["clock_in"], co_iso, shift)
    was_outside = bool(existing.get("outside_geofence"))
    status = "flagged" if was_outside else att.determine_status(metrics, False, True)
    geo = dict(existing.get("geo") or {})
    if payload.lat is not None and payload.lon is not None:
        fences = await _active_geofences(entity_id)
        fence, dist, inside = att.nearest_geofence(payload.lat, payload.lon, fences)
        geo["out"] = _geo_block(payload.lat, payload.lon, payload.accuracy, fence, dist, inside)
    else:
        geo["out"] = {"lat": None, "lon": None, "no_location": True}
    updates = {
        "clock_out": co_iso, "status": status, "geo": geo,
        "work_min": metrics["work_min"], "late_min": metrics["late_min"],
        "early_leave_min": metrics["early_leave_min"], "overtime_min": metrics["overtime_min"],
        "updated_at": now_iso(),
    }
    if payload.note:
        updates["note"] = payload.note
    updated = await db.hr_attendance.find_one_and_update(
        {"id": existing["id"]}, {"$set": updates}, projection={"_id": 0},
        return_document=ReturnDocument.AFTER)
    await audit(emp.get("name", ""), "hr_clock_out", "hr_attendance", existing["id"],
                {"work_min": metrics["work_min"]})
    return safe_doc(updated)


# ════════════════════════════ MANUAL & APPROVE ══════════════════════════════
@router.post("/hr/attendance/manual")
async def manual_attendance(payload: ManualAttendanceInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    emp = safe_doc(await db.hr_employees.find_one({"id": payload.employee_id}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
    assert_entity_access(emp, "hr_employees", ctx)
    if not payload.date:
        raise HTTPException(status_code=400, detail="Tanggal wajib diisi")
    ci_iso = f"{payload.date}T{payload.clock_in}:00+07:00" if payload.clock_in else ""
    co_iso = f"{payload.date}T{payload.clock_out}:00+07:00" if payload.clock_out else ""
    doc = await att.upsert_attendance(
        emp, payload.date, ci_iso, co_iso, "manual", emp.get("entity_id", ""),
        note=payload.note, status_override=payload.status or "hadir")
    await audit(actor["name"], "hr_attendance_manual", "hr_attendance", doc["id"],
                {"employee": emp.get("name"), "date": payload.date, "status": doc["status"]})
    return safe_doc(doc)


@router.patch("/hr/attendance/{att_id}")
async def patch_attendance(att_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    """Adjust/approve kehadiran (mis. setujui flagged → set status & approved)."""
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    cur = safe_doc(await db.hr_attendance.find_one({"id": att_id}, {"_id": 0}))
    if not cur:
        raise HTTPException(status_code=404, detail="Rekaman absen tidak ditemukan")
    assert_entity_access(cur, "hr_attendance", ctx)
    updates = {k: v for k, v in (payload.data or {}).items() if k in ATT_PATCH_FIELDS}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    if "approved" in updates:
        updates["approved"] = bool(updates["approved"])
        if updates["approved"]:
            updates["outside_geofence"] = False
    updates["updated_at"] = now_iso()
    updated = await db.hr_attendance.find_one_and_update(
        {"id": att_id}, {"$set": updates}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_attendance_patched", "hr_attendance", att_id, updates)
    return safe_doc(updated)


# ════════════════════════════ IMPORT / INGEST (fingerprint) ═════════════════
async def _device_map(entity_id: str) -> Dict[str, str]:
    """{device_user_id -> employee_id} dari karyawan ber-device_user_id di entitas."""
    emps = await db.hr_employees.find(
        {"entity_id": entity_id, "device_user_id": {"$nin": ["", None]}},
        {"_id": 0, "id": 1, "device_user_id": 1}).to_list(5000)
    return {str(e["device_user_id"]).strip(): e["id"] for e in emps}


async def _ingest_records(rows: List[Dict[str, Any]], entity_id: str) -> Dict[str, Any]:
    device_map = await _device_map(entity_id)
    if not device_map:
        return {"imported": 0, "skipped_rows": 0, "unmapped": True, "records": [],
                "message": "Belum ada karyawan dengan ID Mesin (device_user_id) di entitas ini."}
    parsed, skipped = att.parse_zkteco_rows(rows, device_map)
    emp_cache: Dict[str, Dict[str, Any]] = {}
    out = []
    for rec in parsed:
        emp = emp_cache.get(rec["employee_id"])
        if emp is None:
            emp = safe_doc(await db.hr_employees.find_one({"id": rec["employee_id"]}, {"_id": 0})) or {}
            emp_cache[rec["employee_id"]] = emp
        if not emp:
            continue
        doc = await att.upsert_attendance(
            emp, rec["date"], rec["clock_in"], rec["clock_out"], "fingerprint", entity_id)
        out.append({"employee_name": emp.get("name", ""), "date": rec["date"],
                    "status": doc["status"], "punches": rec["punches"]})
    return {"imported": len(out), "skipped_rows": skipped, "records": out}


@router.post("/hr/attendance/import")
async def import_attendance(payload: AttendanceImportInput, request: Request) -> Dict[str, Any]:
    """Import CSV ZKTeco (teks). Kolom: user_id,timestamp[,status]. Idempotent."""
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    entity_id = payload.entity_id or ctx.active_entity_id
    if entity_id not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas ini")
    if not (payload.csv_text or "").strip():
        raise HTTPException(status_code=400, detail="File CSV kosong")
    rows = att.csv_to_rows(payload.csv_text)
    result = await _ingest_records(rows, entity_id)
    if payload.device_id:
        await db.hr_devices.update_one({"id": payload.device_id}, {"$set": {"last_sync": now_iso()}})
    await audit(actor["name"], "hr_attendance_import", "hr_attendance", entity_id,
                {"imported": result.get("imported", 0)})
    return result


@router.post("/hr/attendance/ingest")
async def ingest_attendance(payload: AttendanceIngestInput, request: Request) -> Dict[str, Any]:
    """Endpoint agen jembatan on-prem (ZKTeco pull). Auth: device_token (tanpa sesi)."""
    if not payload.device_token:
        raise HTTPException(status_code=401, detail="device_token diperlukan")
    device = await db.hr_devices.find_one(
        {"device_token": payload.device_token, "status": "active"}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=401, detail="device_token tidak valid")
    result = await _ingest_records(payload.records or [], device["entity_id"])
    await db.hr_devices.update_one({"id": device["id"]}, {"$set": {"last_sync": now_iso()}})
    return result
