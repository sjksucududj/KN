"""HRD H3 router — Cuti, Izin & Lembur (Leave/Permit & Overtime).

Koleksi kanonik (entity-scoped): hr_leave_requests (leave_), hr_leave_balances (lbal_),
hr_overtime (ot_). Lihat ENTITY_REGISTRY.md + memory/PLAN_HRD.md §6 H3.

RBAC:
- read list/balances/calendar = hr.view
- create-for-employee / approve / reject / cancel / set entitlement = hr.manage_attendance
- ESS (/me) submit + lihat milik sendiri = autentikasi + karyawan ter-link (sales/warehouse ikut)

Urutan route: literal `/me` didaftarkan SEBELUM pola `/{id}/...` (hindari bentrok path).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Query

from db import db
from dependencies import require_permission, current_user, audit
from core_utils import safe_doc
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas_hr_leave import LeaveRequestInput, OvertimeInput, LeaveDecisionInput, LeaveBalanceAdjust
from services import hr_leave_service as lv

router = APIRouter(prefix="/api")


async def _emp_for_user(request: Request) -> Dict[str, Any]:
    user = await current_user(request)
    emp = safe_doc(await db.hr_employees.find_one({"user_id": user["id"]}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Profil karyawan belum tersedia untuk akun Anda")
    return emp


async def _emp_by_id(employee_id: str, ctx) -> Dict[str, Any]:
    emp = safe_doc(await db.hr_employees.find_one({"id": employee_id}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
    assert_entity_access(emp, "hr_employees", ctx)
    return emp


# ═══════════════════ LEAVE — ESS (/me) ═════════════════════════════
@router.get("/hr/leave-requests/me")
async def my_leave_requests(request: Request) -> Dict[str, Any]:
    emp = await _emp_for_user(request)
    return await lv.my_leaves(emp)


@router.post("/hr/leave-requests/me")
async def submit_my_leave(payload: LeaveRequestInput, request: Request) -> Dict[str, Any]:
    emp = await _emp_for_user(request)
    try:
        doc = await lv.submit_leave(emp, payload.model_dump(), emp.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(emp.get("name", ""), "hr_leave_submit", "hr_leave_requests", doc["id"],
                {"type": doc["leave_type"], "days": doc["days"]})
    return doc


@router.get("/hr/leave-balance/me")
async def my_leave_balance(request: Request, year: Optional[int] = Query(None)) -> Dict[str, Any]:
    emp = await _emp_for_user(request)
    return await lv.get_balance(emp["id"], emp.get("entity_id", ""), year)


# ═══════════════════ LEAVE — HRD ════════════════════════════════
@router.get("/hr/leave-requests")
async def list_leave_requests(request: Request, entity_id: Optional[str] = Query(None),
                              status: Optional[str] = Query(None),
                              employee_id: Optional[str] = Query(None),
                              month: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("hr_leave_requests", {}, ctx, entity_id)
    return await lv.list_leaves(scope, status, employee_id, month)


@router.post("/hr/leave-requests")
async def create_leave_request(payload: LeaveRequestInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    if not payload.employee_id:
        raise HTTPException(status_code=400, detail="employee_id wajib (ajukan untuk karyawan).")
    emp = await _emp_by_id(payload.employee_id, ctx)
    try:
        doc = await lv.submit_leave(emp, payload.model_dump(), actor["name"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_leave_create", "hr_leave_requests", doc["id"],
                {"employee": emp.get("name"), "type": doc["leave_type"]})
    return doc


@router.get("/hr/leave-balances")
async def list_leave_balances(request: Request, entity_id: Optional[str] = Query(None),
                              year: Optional[int] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("hr_leave_balances", {}, ctx, entity_id)
    return await lv.list_balances(scope, year)


@router.post("/hr/leave-balances/set")
async def set_leave_entitlement(payload: LeaveBalanceAdjust, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    emp = await _emp_by_id(payload.employee_id, ctx)
    year = payload.year or lv.current_year()
    res = await lv.set_entitlement(emp["id"], emp.get("entity_id", ""), year, payload.entitlement)
    await audit(actor["name"], "hr_leave_set_entitlement", "hr_leave_balances", res.get("id", ""),
                {"employee": emp.get("name"), "entitlement": payload.entitlement})
    return res


@router.get("/hr/leave-calendar")
async def leave_calendar(request: Request, entity_id: Optional[str] = Query(None),
                         month: Optional[str] = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    month = month or lv.wib_now().strftime("%Y-%m")
    scope = resolve_list_scope("hr_leave_requests", {}, ctx, entity_id)
    rows = await lv.list_leaves(scope, None, None, month, approved_only=True)
    return {"month": month, "leaves": rows}


async def _get_leave_guard(leave_id: str, ctx) -> Dict[str, Any]:
    doc = await db.hr_leave_requests.find_one({"id": leave_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Pengajuan cuti tidak ditemukan.")
    assert_entity_access(doc, "hr_leave_requests", ctx)
    return doc


@router.post("/hr/leave-requests/{leave_id}/approve")
async def approve_leave_request(leave_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    await _get_leave_guard(leave_id, ctx)
    try:
        doc = await lv.approve_leave(leave_id, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_leave_approve", "hr_leave_requests", leave_id, {})
    return doc


@router.post("/hr/leave-requests/{leave_id}/reject")
async def reject_leave_request(leave_id: str, payload: LeaveDecisionInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    await _get_leave_guard(leave_id, ctx)
    try:
        doc = await lv.reject_leave(leave_id, actor, payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_leave_reject", "hr_leave_requests", leave_id, {"reason": payload.reason})
    return doc


@router.post("/hr/leave-requests/{leave_id}/cancel")
async def cancel_leave_request(leave_id: str, payload: LeaveDecisionInput, request: Request) -> Dict[str, Any]:
    """Pemilik (pengaju) boleh batalkan miliknya; HRD (manage_attendance) boleh batalkan apa pun."""
    user = await current_user(request)
    ctx = await entity_ctx(request)
    doc = await _get_leave_guard(leave_id, ctx)
    emp = safe_doc(await db.hr_employees.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1}))
    is_owner = emp and emp["id"] == doc.get("employee_id")
    if not is_owner:
        await require_permission(request, "hr", "manage_attendance")
    try:
        res = await lv.cancel_leave(leave_id, user, payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(user.get("name", ""), "hr_leave_cancel", "hr_leave_requests", leave_id, {})
    return res


# ═══════════════════ OVERTIME — ESS (/me) ═════════════════════════
@router.get("/hr/overtime/me")
async def my_overtime_requests(request: Request) -> Dict[str, Any]:
    emp = await _emp_for_user(request)
    return await lv.my_overtime(emp)


@router.post("/hr/overtime/me")
async def submit_my_overtime(payload: OvertimeInput, request: Request) -> Dict[str, Any]:
    emp = await _emp_for_user(request)
    try:
        doc = await lv.submit_overtime(emp, payload.model_dump(), emp.get("name", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(emp.get("name", ""), "hr_overtime_submit", "hr_overtime", doc["id"],
                {"date": doc["date"], "hours": doc["hours"]})
    return doc


# ═══════════════════ OVERTIME — HRD ═════════════════════════════
@router.get("/hr/overtime")
async def list_overtime_requests(request: Request, entity_id: Optional[str] = Query(None),
                                 status: Optional[str] = Query(None),
                                 employee_id: Optional[str] = Query(None),
                                 month: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("hr_overtime", {}, ctx, entity_id)
    return await lv.list_overtime(scope, status, employee_id, month)


@router.post("/hr/overtime")
async def create_overtime(payload: OvertimeInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    if not payload.employee_id:
        raise HTTPException(status_code=400, detail="employee_id wajib (ajukan untuk karyawan).")
    emp = await _emp_by_id(payload.employee_id, ctx)
    try:
        doc = await lv.submit_overtime(emp, payload.model_dump(), actor["name"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_overtime_create", "hr_overtime", doc["id"],
                {"employee": emp.get("name"), "date": doc["date"]})
    return doc


async def _get_ot_guard(ot_id: str, ctx) -> Dict[str, Any]:
    doc = await db.hr_overtime.find_one({"id": ot_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Pengajuan lembur tidak ditemukan.")
    assert_entity_access(doc, "hr_overtime", ctx)
    return doc


@router.post("/hr/overtime/{ot_id}/approve")
async def approve_overtime_request(ot_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    await _get_ot_guard(ot_id, ctx)
    try:
        doc = await lv.approve_overtime(ot_id, actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_overtime_approve", "hr_overtime", ot_id, {})
    return doc


@router.post("/hr/overtime/{ot_id}/reject")
async def reject_overtime_request(ot_id: str, payload: LeaveDecisionInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    await _get_ot_guard(ot_id, ctx)
    try:
        doc = await lv.reject_overtime(ot_id, actor, payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_overtime_reject", "hr_overtime", ot_id, {"reason": payload.reason})
    return doc
