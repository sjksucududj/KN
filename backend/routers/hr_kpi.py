"""HRD H5 router — KPI Design (input KPI manual per karyawan/periode + rekap + ESS).

Koleksi kanonik (entity-scoped): hr_kpi (hkpi_). Keputusan owner 2a.
RBAC: read list/rekap = hr.view; create/update/delete = hr.manage_attendance (reuse).
ESS `/hr/kpi/me` = autentikasi + karyawan ter-link (semua role ber-employee).
Urutan route: literal `/me` didaftarkan SEBELUM pola `/{id}`.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Query

from db import db
from dependencies import require_permission, current_user, audit
from core_utils import safe_doc
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas_hr_kpi import KpiInput, KpiUpdate
from services import hr_kpi_service as kpi

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


async def _kpi_guard(kpi_id: str, ctx) -> Dict[str, Any]:
    doc = await db.hr_kpi.find_one({"id": kpi_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Data KPI tidak ditemukan.")
    assert_entity_access(doc, "hr_kpi", ctx)
    return doc


# ═══════════════ ESS (/me) ═══════════════
async def _my_kpi(request: Request) -> Dict[str, Any]:
    emp = await _emp_for_user(request)
    return await kpi.my_kpi(emp)


@router.get("/hr/kpi/me")
async def my_kpi_endpoint(request: Request) -> Dict[str, Any]:
    return await _my_kpi(request)


# ═══════════════ HRD ═══════════════
@router.get("/hr/kpi")
async def list_kpi(request: Request, entity_id: Optional[str] = Query(None),
                   employee_id: Optional[str] = Query(None),
                   period: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    scope = resolve_list_scope("hr_kpi", {}, ctx, entity_id)
    return await kpi.list_kpi(scope, employee_id, period)


@router.post("/hr/kpi")
async def create_kpi(payload: KpiInput, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    if not payload.employee_id:
        raise HTTPException(status_code=400, detail="employee_id wajib (catat KPI untuk karyawan).")
    emp = await _emp_by_id(payload.employee_id, ctx)
    try:
        doc = await kpi.submit_kpi(emp, payload.model_dump(), actor["name"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_kpi_create", "hr_kpi", doc["id"],
                {"employee": emp.get("name"), "metric": doc["metric"], "period": doc["period"]})
    return doc


@router.put("/hr/kpi/{kpi_id}")
async def update_kpi(kpi_id: str, payload: KpiUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    await _kpi_guard(kpi_id, ctx)
    patch = payload.model_dump(exclude_unset=True)
    try:
        doc = await kpi.update_kpi(kpi_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_kpi_update", "hr_kpi", kpi_id, patch)
    return doc


@router.delete("/hr/kpi/{kpi_id}")
async def delete_kpi(kpi_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "hr", "manage_attendance")
    ctx = await entity_ctx(request)
    await _kpi_guard(kpi_id, ctx)
    try:
        res = await kpi.delete_kpi(kpi_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit(actor["name"], "hr_kpi_delete", "hr_kpi", kpi_id, {})
    return res
