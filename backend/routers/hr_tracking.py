"""HRD H2 router — Field Tracking + Visits (Kunjungan).

Koleksi kanonik (entity-scoped): hr_field_tracks (trk_), hr_visits (visit_).
RBAC: baca peta/kunjungan = hr.view (admin+manager). Push posisi + check-in/out =
autentikasi + karyawan ter-link (lihat/ubah data SENDIRI). Lihat memory/PLAN_HRD.md §H2.
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, current_user, audit
from core_utils import new_id, now_iso, safe_doc
from entity_scope import entity_ctx, resolve_list_scope
from schemas_hr_tracking import PositionInput, VisitCheckIn, VisitCheckOut
from services import tracking_service as trk

router = APIRouter(prefix="/api")
WIB = timezone(timedelta(hours=7))


def _wib_today() -> str:
    return datetime.now(WIB).date().isoformat()


async def _emp_for_user(request: Request) -> Dict[str, Any]:
    user = await current_user(request)
    emp = safe_doc(await db.hr_employees.find_one({"user_id": user["id"]}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Profil karyawan belum tersedia untuk akun Anda")
    return emp


# ════════════ FIELD TRACKS ═════════════════════════════════════════
async def _latest_positions(scope_q: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipeline = [
        {"$match": scope_q},
        {"$sort": {"ts": -1}},
        {"$group": {"_id": "$employee_id", "doc": {"$first": "$$ROOT"}}},
    ]
    out = []
    async for row in db.hr_field_tracks.aggregate(pipeline):
        d = safe_doc(row["doc"])
        d.pop("_id", None)
        d["online"] = trk.is_online(d.get("ts", ""))
        out.append(d)
    out.sort(key=lambda x: (not x["online"], x.get("employee_name", "")))
    return out


@router.get("/hr/field-tracks/latest")
async def latest_tracks(request: Request, entity_id: str = None) -> List[Dict[str, Any]]:
    """Posisi terkini per karyawan lapangan (Live Map manager + fallback polling)."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    scope_q = resolve_list_scope("hr_field_tracks", {}, ctx, entity_id)
    return await _latest_positions(scope_q)


@router.get("/hr/field-tracks")
async def track_history(request: Request, employee_id: str, date: str = None,
                        entity_id: str = None) -> List[Dict[str, Any]]:
    """Breadcrumb (jejak) seorang karyawan pada tanggal tertentu (default hari ini)."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    day = date or _wib_today()
    q = {"employee_id": employee_id, "ts": {"$gte": f"{day}T00:00:00", "$lte": f"{day}T23:59:59.999999+07:00"}}
    q = resolve_list_scope("hr_field_tracks", q, ctx, entity_id)
    rows = await db.hr_field_tracks.find(q, {"_id": 0}).sort("ts", 1).to_list(5000)
    return rows


@router.post("/hr/field-tracks")
async def push_track(payload: PositionInput, request: Request) -> Dict[str, Any]:
    """Push posisi via REST (fallback bila WS tak tersedia). Hanya untuk diri sendiri."""
    emp = await _emp_for_user(request)
    pos = await trk.store_track(emp, payload.lat, payload.lon,
                                payload.accuracy, payload.battery, source="rest")
    return pos


# ════════════ VISITS (KUNJUNGAN) ═══════════════════════════════════
@router.get("/hr/visits")
async def list_visits(request: Request, entity_id: str = None, date_from: str = None,
                      date_to: str = None, employee_id: str = None,
                      status: str = None) -> List[Dict[str, Any]]:
    """Daftar kunjungan (scoped). Default: hari ini bila tanpa rentang."""
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
            rng["$lte"] = date_to + "~"
        q["date"] = rng
    else:
        q["date"] = _wib_today()
    q = resolve_list_scope("hr_visits", q, ctx, entity_id)
    return await db.hr_visits.find(q, {"_id": 0}).sort("created_at", -1).to_list(3000)


@router.get("/hr/visits/summary")
async def visits_summary(request: Request, entity_id: str = None, month: str = None) -> Dict[str, Any]:
    """KPI kunjungan per sales untuk satu bulan (YYYY-MM)."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    month = month or datetime.now(WIB).strftime("%Y-%m")
    q = resolve_list_scope("hr_visits", {"date": {"$regex": f"^{month}"}}, ctx, entity_id)
    rows = await db.hr_visits.find(q, {"_id": 0}).to_list(20000)
    by_emp: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        e = by_emp.setdefault(r["employee_id"], {
            "employee_id": r["employee_id"], "employee_name": r.get("employee_name", ""),
            "total": 0, "done": 0, "with_order": 0, "total_minutes": 0})
        e["total"] += 1
        if r.get("status") == "done":
            e["done"] += 1
        if r.get("outcome") == "order" or r.get("linked_so_id"):
            e["with_order"] += 1
        e["total_minutes"] += int(r.get("duration_min", 0) or 0)
    rows_out = sorted(by_emp.values(), key=lambda x: -x["total"])
    totals = {"visits": len(rows), "with_order": sum(e["with_order"] for e in rows_out),
              "sales": len(rows_out)}
    return {"month": month, "totals": totals, "rows": rows_out}


@router.get("/hr/visits/me")
async def my_visits(request: Request) -> Dict[str, Any]:
    """ESS — kunjungan hari ini + kunjungan berjalan (ongoing) milik user login."""
    emp = await _emp_for_user(request)
    today = _wib_today()
    ongoing = safe_doc(await db.hr_visits.find_one(
        {"employee_id": emp["id"], "status": "ongoing"}, {"_id": 0}))
    todays = await db.hr_visits.find(
        {"employee_id": emp["id"], "date": today}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"employee": {"id": emp["id"], "name": emp.get("name", "")},
            "ongoing": ongoing, "today": todays, "count_today": len(todays)}


@router.get("/hr/visits/mine")
async def my_visits_history(request: Request, month: str = None) -> Dict[str, Any]:
    """FASE E-8 (E8.3 · SD4) — **RIWAYAT kunjungan MILIK SENDIRI** + KPI ringkasnya.

    Menu "Kunjungan Sales" terlihat untuk sales, tetapi `/api/hr/visits` memakai izin
    `hr.view` yang TIDAK dimiliki sales — jadi layarnya selalu 403. Dua obat yang salah
    adalah (a) memberi sales `hr.view` (ikut membuka kunjungan seluruh karyawan) atau
    (b) menyembunyikan menunya (sales kehilangan catatan kerjanya sendiri).

    Endpoint ini obat yang benar: **hanya kunjungan milik akun yang login**, tanpa izin
    HR, tanpa data rekan. Pagarnya bukan filter opsional melainkan `employee_id` yang
    diambil dari sesi (`_emp_for_user`), sehingga tidak ada parameter yang bisa
    diputar untuk melihat orang lain.
    """
    emp = await _emp_for_user(request)
    bulan = month or datetime.now(WIB).strftime("%Y-%m")
    rows = await db.hr_visits.find(
        {"employee_id": emp["id"], "date": {"$regex": f"^{bulan}"}},
        {"_id": 0}).sort("created_at", -1).to_list(2000)
    rows = [safe_doc(r) for r in rows]
    selesai = [r for r in rows if r.get("status") == "done"]
    berbuah = [r for r in rows if r.get("outcome") == "order" or r.get("linked_so_id")]
    menit = sum(int(r.get("duration_min") or 0) for r in rows)
    return {
        "employee": {"id": emp["id"], "name": emp.get("name", "")},
        "month": bulan,
        "totals": {"total": len(rows), "done": len(selesai),
                   "with_order": len(berbuah), "total_minutes": menit,
                   "conversion_percent": (round(100.0 * len(berbuah) / len(rows), 1)
                                          if rows else 0.0)},
        "rows": rows,
    }


@router.post("/hr/visits/check-in")
async def visit_check_in(payload: VisitCheckIn, request: Request) -> Dict[str, Any]:
    """Sales check-in di customer (mulai kunjungan)."""
    emp = await _emp_for_user(request)
    existing = await db.hr_visits.find_one(
        {"employee_id": emp["id"], "status": "ongoing"}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="Selesaikan kunjungan yang sedang berjalan dulu.")
    cust_name = payload.customer_name
    if payload.customer_id and not cust_name:
        cust = await db.customers.find_one({"id": payload.customer_id}, {"_id": 0, "name": 1})
        cust_name = (cust or {}).get("name", "")
    now = datetime.now(WIB)
    doc = {
        "id": new_id("visit"), "employee_id": emp["id"], "employee_name": emp.get("name", ""),
        "customer_id": payload.customer_id or "", "customer_name": cust_name or "(tanpa customer)",
        "date": now.date().isoformat(),
        "check_in": {"ts": now.isoformat(), "lat": payload.lat, "lon": payload.lon,
                     "photo_url": payload.photo_url or ""},
        "check_out": None, "notes": payload.notes or "", "outcome": "", "linked_so_id": "",
        "status": "ongoing", "duration_min": 0, "entity_id": emp.get("entity_id", ""),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.hr_visits.insert_one(dict(doc))
    await audit(emp.get("name", ""), "hr_visit_checkin", "hr_visit", doc["id"],
                {"customer": cust_name})
    return safe_doc(doc)


@router.post("/hr/visits/{visit_id}/check-out")
async def visit_check_out(visit_id: str, payload: VisitCheckOut, request: Request) -> Dict[str, Any]:
    """Sales check-out (selesai kunjungan) + hasil."""
    emp = await _emp_for_user(request)
    cur = safe_doc(await db.hr_visits.find_one({"id": visit_id}, {"_id": 0}))
    if not cur:
        raise HTTPException(status_code=404, detail="Kunjungan tidak ditemukan")
    if cur["employee_id"] != emp["id"]:
        raise HTTPException(status_code=403, detail="Bukan kunjungan Anda")
    if cur.get("status") != "ongoing":
        raise HTTPException(status_code=409, detail="Kunjungan sudah selesai.")
    now = datetime.now(WIB)
    dur = 0
    try:
        ci = datetime.fromisoformat(cur["check_in"]["ts"])
        dur = max(0, int((now - ci).total_seconds() // 60))
    except (ValueError, KeyError, TypeError):
        pass
    updates = {
        "check_out": {"ts": now.isoformat(), "lat": payload.lat, "lon": payload.lon},
        "status": "done", "duration_min": dur, "outcome": payload.outcome or "other",
        "linked_so_id": payload.linked_so_id or "", "updated_at": now_iso(),
    }
    if payload.notes:
        updates["notes"] = (cur.get("notes", "") + "\n" + payload.notes).strip()
    updated = await db.hr_visits.find_one_and_update(
        {"id": visit_id}, {"$set": updates}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(emp.get("name", ""), "hr_visit_checkout", "hr_visit", visit_id,
                {"duration_min": dur, "outcome": updates["outcome"]})
    return safe_doc(updated)
