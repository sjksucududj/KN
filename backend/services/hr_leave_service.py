"""HRD H3 services — Cuti, Izin & Lembur (Leave/Permit & Overtime).

Logika murni + I/O Mongo (motor). Koleksi kanonik (entity-scoped):
`hr_leave_requests` (leave_), `hr_leave_balances` (lbal_), `hr_overtime` (ot_).

Aturan kunci:
- Hari kerja = Senin–Jumat dalam rentang (V1 tanpa kalender libur nasional).
- Saldo cuti tahunan berkurang HANYA untuk tipe yang `deduct=True` (cuti_tahunan/besar).
- Saat cuti di-APPROVE → `hr_attendance` hari terkait di-set status `cuti`/`izin`
  (method="leave") agar rekap absensi konsisten.
- Lembur APPROVED → dikonsumsi payroll (hr_payroll_service._period_filed_overtime_min).
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, next_doc_number, safe_doc
from services import hr_attendance_service as att

WIB = timezone(timedelta(hours=7))

# Tipe cuti: deduct = mengurangi saldo cuti tahunan; att_status = status absensi saat approve.
LEAVE_TYPES: Dict[str, Dict[str, Any]] = {
    "cuti_tahunan": {"label": "Cuti Tahunan", "deduct": True, "att_status": "cuti"},
    "cuti_besar":   {"label": "Cuti Besar", "deduct": True, "att_status": "cuti"},
    "izin":         {"label": "Izin", "deduct": False, "att_status": "izin"},
    "sakit":        {"label": "Sakit", "deduct": False, "att_status": "izin"},
    "unpaid":       {"label": "Cuti Tanpa Gaji", "deduct": False, "att_status": "izin"},
}
DEDUCT_TYPES = [k for k, v in LEAVE_TYPES.items() if v["deduct"]]
DEFAULT_ANNUAL_ENTITLEMENT = 12


def wib_now() -> datetime:
    return datetime.now(WIB)


def wib_today() -> str:
    return wib_now().date().isoformat()


def current_year() -> int:
    return wib_now().year


def _parse_date(s: str) -> Optional[date]:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except (ValueError, TypeError):
        return None


def working_days(date_from: str, date_to: str) -> List[str]:
    """Daftar tanggal kerja (Senin–Jumat) dalam rentang inklusif. V1 tanpa kalender libur."""
    d0 = _parse_date(date_from)
    d1 = _parse_date(date_to)
    if not d0 or not d1 or d1 < d0:
        return []
    out: List[str] = []
    cur = d0
    # batas aman 366 hari
    for _ in range(367):
        if cur > d1:
            break
        if cur.weekday() < 5:  # 0=Senin .. 4=Jumat
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def count_working_days(date_from: str, date_to: str) -> int:
    return len(working_days(date_from, date_to))


# ── Saldo cuti ─────────────────────────────────────────────────────────
async def _annual_entitlement(entity_id: str = "") -> int:
    # FASE E-4 (E4.5) — jatah cuti tahunan boleh berbeda per badan usaha.
    from services import hr_service
    cfg = await hr_service.get_hr_settings(entity_id)
    try:
        return int((cfg.get("leave") or {}).get("annual_entitlement") or DEFAULT_ANNUAL_ENTITLEMENT)
    except (TypeError, ValueError):
        return DEFAULT_ANNUAL_ENTITLEMENT


async def recompute_balance(employee_id: str, entity_id: str, year: int) -> Dict[str, Any]:
    """Hitung ulang & simpan saldo cuti tahunan: remaining = entitlement - used(approved)."""
    entitlement = await _annual_entitlement(entity_id)
    existing = await db.hr_leave_balances.find_one(
        {"employee_id": employee_id, "year": year}, {"_id": 0})
    if existing and existing.get("entitlement_override"):
        entitlement = int(existing.get("entitlement") or entitlement)
    used = 0
    pending = 0
    q = {"employee_id": employee_id, "leave_type": {"$in": DEDUCT_TYPES},
         "date_from": {"$regex": f"^{year:04d}"}}
    async for r in db.hr_leave_requests.find(q, {"_id": 0, "status": 1, "days": 1}):
        if r.get("status") == "approved":
            used += int(r.get("days") or 0)
        elif r.get("status") == "pending":
            pending += int(r.get("days") or 0)
    remaining = entitlement - used
    doc = {
        "employee_id": employee_id, "entity_id": entity_id, "year": year,
        "entitlement": entitlement, "used": used, "pending": pending,
        "remaining": remaining, "updated_at": now_iso(),
    }
    if existing:
        doc["id"] = existing["id"]
        doc["entitlement_override"] = bool(existing.get("entitlement_override"))
        await db.hr_leave_balances.update_one({"id": existing["id"]}, {"$set": doc})
    else:
        doc["id"] = new_id("lbal")
        doc["entitlement_override"] = False
        doc["created_at"] = now_iso()
        await db.hr_leave_balances.insert_one(dict(doc))
    return safe_doc(doc)


async def get_balance(employee_id: str, entity_id: str, year: Optional[int] = None) -> Dict[str, Any]:
    year = year or current_year()
    bal = await db.hr_leave_balances.find_one({"employee_id": employee_id, "year": year}, {"_id": 0})
    if not bal:
        return await recompute_balance(employee_id, entity_id, year)
    return safe_doc(bal)


async def set_entitlement(employee_id: str, entity_id: str, year: int, entitlement: int) -> Dict[str, Any]:
    bal = await recompute_balance(employee_id, entity_id, year)
    await db.hr_leave_balances.update_one(
        {"id": bal["id"]},
        {"$set": {"entitlement": int(entitlement), "entitlement_override": True,
                  "remaining": int(entitlement) - int(bal.get("used") or 0), "updated_at": now_iso()}})
    return await get_balance(employee_id, entity_id, year)


async def list_balances(scope: Dict[str, Any], year: Optional[int] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = dict(scope or {})
    if year:
        q["year"] = year
    rows = await db.hr_leave_balances.find(q, {"_id": 0}).to_list(5000)
    return [safe_doc(r) for r in rows]


# ── Pengajuan cuti ──────────────────────────────────────────────────
async def submit_leave(emp: Dict[str, Any], payload: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    ltype = payload.get("leave_type") or "cuti_tahunan"
    if ltype not in LEAVE_TYPES:
        raise ValueError("Tipe cuti tidak dikenal.")
    date_from = (payload.get("date_from") or "")[:10]
    date_to = (payload.get("date_to") or date_from)[:10]
    d0 = _parse_date(date_from)
    if not d0:
        raise ValueError("Tanggal mulai tidak valid (format YYYY-MM-DD).")
    days_list = working_days(date_from, date_to)
    if not days_list:
        raise ValueError("Rentang tanggal tidak valid (pastikan ada hari kerja Senin–Jumat).")
    days = len(days_list)
    entity_id = emp.get("entity_id", "")
    if LEAVE_TYPES[ltype]["deduct"]:
        bal = await get_balance(emp["id"], entity_id, d0.year)
        if days > int(bal.get("remaining") or 0):
            raise ValueError(
                f"Saldo cuti tidak cukup (sisa {bal.get('remaining')} hari, diminta {days} hari).")
    number = await next_doc_number("hr_leave_requests", "number", "LV-", entity_id=entity_id)
    doc = {
        "id": new_id("leave"), "number": number,
        "employee_id": emp["id"], "employee_name": emp.get("name", ""),
        "entity_id": entity_id, "leave_type": ltype, "leave_label": LEAVE_TYPES[ltype]["label"],
        "date_from": date_from, "date_to": date_to, "days": days, "work_dates": days_list,
        "reason": payload.get("reason", ""), "attachment_url": payload.get("attachment_url", ""),
        "status": "pending", "approver": "", "approved_at": "", "reject_reason": "",
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.hr_leave_requests.insert_one(doc)
    await recompute_balance(emp["id"], entity_id, d0.year)
    return safe_doc(doc)


async def _mark_attendance_for_leave(lv: Dict[str, Any]) -> None:
    emp = safe_doc(await db.hr_employees.find_one({"id": lv["employee_id"]}, {"_id": 0}))
    if not emp:
        return
    meta = LEAVE_TYPES.get(lv.get("leave_type"), {})
    att_status = meta.get("att_status", "izin")
    note = f"{lv.get('leave_label', 'Cuti')}·{lv.get('number', '')}: {lv.get('reason', '')}".strip()
    for d in (lv.get("work_dates") or working_days(lv["date_from"], lv["date_to"])):
        await att.upsert_attendance(
            emp, d, "", "", "leave", lv.get("entity_id", ""),
            status_override=att_status, note=note)


async def _clear_attendance_for_leave(lv: Dict[str, Any]) -> None:
    """Hapus rekaman absensi yang dibuat oleh cuti ini (method=leave) saat dibatalkan."""
    dates = lv.get("work_dates") or working_days(lv["date_from"], lv["date_to"])
    if not dates:
        return
    await db.hr_attendance.delete_many(
        {"employee_id": lv["employee_id"], "date": {"$in": dates}, "method": "leave"})


async def approve_leave(leave_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    lv = await db.hr_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not lv:
        raise ValueError("Pengajuan cuti tidak ditemukan.")
    if lv["status"] != "pending":
        raise ValueError(f"Status '{lv['status']}' tidak bisa di-approve.")
    await db.hr_leave_requests.update_one({"id": leave_id}, {"$set": {
        "status": "approved", "approver": actor.get("name", "system"),
        "approved_at": now_iso(), "updated_at": now_iso()}})
    await _mark_attendance_for_leave(lv)
    d0 = _parse_date(lv["date_from"])
    await recompute_balance(lv["employee_id"], lv.get("entity_id", ""), d0.year if d0 else current_year())
    return safe_doc(await db.hr_leave_requests.find_one({"id": leave_id}, {"_id": 0}))


async def reject_leave(leave_id: str, actor: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    lv = await db.hr_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not lv:
        raise ValueError("Pengajuan cuti tidak ditemukan.")
    if lv["status"] != "pending":
        raise ValueError(f"Status '{lv['status']}' tidak bisa ditolak.")
    await db.hr_leave_requests.update_one({"id": leave_id}, {"$set": {
        "status": "rejected", "approver": actor.get("name", "system"),
        "reject_reason": reason or "", "approved_at": now_iso(), "updated_at": now_iso()}})
    d0 = _parse_date(lv["date_from"])
    await recompute_balance(lv["employee_id"], lv.get("entity_id", ""), d0.year if d0 else current_year())
    return safe_doc(await db.hr_leave_requests.find_one({"id": leave_id}, {"_id": 0}))


async def cancel_leave(leave_id: str, actor: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    lv = await db.hr_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not lv:
        raise ValueError("Pengajuan cuti tidak ditemukan.")
    if lv["status"] in ("cancelled", "rejected"):
        raise ValueError(f"Status '{lv['status']}' sudah final.")
    was_approved = lv["status"] == "approved"
    await db.hr_leave_requests.update_one({"id": leave_id}, {"$set": {
        "status": "cancelled", "reject_reason": reason or "", "updated_at": now_iso()}})
    if was_approved:
        await _clear_attendance_for_leave(lv)
    d0 = _parse_date(lv["date_from"])
    await recompute_balance(lv["employee_id"], lv.get("entity_id", ""), d0.year if d0 else current_year())
    return safe_doc(await db.hr_leave_requests.find_one({"id": leave_id}, {"_id": 0}))


async def list_leaves(scope: Dict[str, Any], status: Optional[str] = None,
                      employee_id: Optional[str] = None, month: Optional[str] = None,
                      approved_only: bool = False) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = dict(scope or {})
    if status:
        q["status"] = status
    if approved_only:
        q["status"] = "approved"
    if employee_id:
        q["employee_id"] = employee_id
    if month:
        q["date_from"] = {"$regex": f"^{month}"}
    rows = await db.hr_leave_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return [safe_doc(r) for r in rows]


async def my_leaves(emp: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db.hr_leave_requests.find(
        {"employee_id": emp["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    bal = await get_balance(emp["id"], emp.get("entity_id", ""), current_year())
    return {"employee": {"id": emp["id"], "name": emp.get("name", "")},
            "balance": bal, "requests": [safe_doc(r) for r in rows],
            "leave_types": [{"value": k, "label": v["label"], "deduct": v["deduct"]}
                            for k, v in LEAVE_TYPES.items()]}


# ── Lembur ───────────────────────────────────────────────────────
async def submit_overtime(emp: Dict[str, Any], payload: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    d = (payload.get("date") or wib_today())[:10]
    if not _parse_date(d):
        raise ValueError("Tanggal lembur tidak valid (format YYYY-MM-DD).")
    hours = float(payload.get("hours") or 0)
    if hours <= 0 or hours > 12:
        raise ValueError("Jam lembur harus > 0 dan ≤ 12.")
    entity_id = emp.get("entity_id", "")
    number = await next_doc_number("hr_overtime", "number", "OT-", entity_id=entity_id)
    doc = {
        "id": new_id("ot"), "number": number,
        "employee_id": emp["id"], "employee_name": emp.get("name", ""),
        "entity_id": entity_id, "date": d, "period": d[:7],
        "hours": round(hours, 2), "minutes": int(round(hours * 60)),
        "reason": payload.get("reason", ""), "rate_basis": payload.get("rate_basis", "normal"),
        "status": "pending", "approver": "", "approved_at": "", "reject_reason": "",
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.hr_overtime.insert_one(doc)
    return safe_doc(doc)


async def approve_overtime(ot_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    ot = await db.hr_overtime.find_one({"id": ot_id}, {"_id": 0})
    if not ot:
        raise ValueError("Pengajuan lembur tidak ditemukan.")
    if ot["status"] != "pending":
        raise ValueError(f"Status '{ot['status']}' tidak bisa di-approve.")
    await db.hr_overtime.update_one({"id": ot_id}, {"$set": {
        "status": "approved", "approver": actor.get("name", "system"),
        "approved_at": now_iso(), "updated_at": now_iso()}})
    return safe_doc(await db.hr_overtime.find_one({"id": ot_id}, {"_id": 0}))


async def reject_overtime(ot_id: str, actor: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    ot = await db.hr_overtime.find_one({"id": ot_id}, {"_id": 0})
    if not ot:
        raise ValueError("Pengajuan lembur tidak ditemukan.")
    if ot["status"] != "pending":
        raise ValueError(f"Status '{ot['status']}' tidak bisa ditolak.")
    await db.hr_overtime.update_one({"id": ot_id}, {"$set": {
        "status": "rejected", "approver": actor.get("name", "system"),
        "reject_reason": reason or "", "approved_at": now_iso(), "updated_at": now_iso()}})
    return safe_doc(await db.hr_overtime.find_one({"id": ot_id}, {"_id": 0}))


async def list_overtime(scope: Dict[str, Any], status: Optional[str] = None,
                        employee_id: Optional[str] = None, month: Optional[str] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = dict(scope or {})
    if status:
        q["status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    if month:
        q["period"] = month
    rows = await db.hr_overtime.find(q, {"_id": 0}).sort("date", -1).to_list(2000)
    return [safe_doc(r) for r in rows]


async def my_overtime(emp: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db.hr_overtime.find(
        {"employee_id": emp["id"]}, {"_id": 0}).sort("date", -1).to_list(200)
    return {"employee": {"id": emp["id"], "name": emp.get("name", "")},
            "requests": [safe_doc(r) for r in rows]}
