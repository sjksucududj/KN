"""HRD router (FASE H0) — Employee Master, Org Units, HR Settings, ESS.

Koleksi kanonik: `hr_employees` (emp_), `hr_org_units` (orgu_) — entity-scoped.
Config statutory: `system_settings` scope='hr'. Lihat ENTITY_REGISTRY.md + memory/PLAN_HRD.md.

RBAC modul `hr`: view | create | update | delete | view_pii | manage_org | manage_settings.
ESS `/hr/employees/me` hanya butuh autentikasi (karyawan lihat data SENDIRI penuh).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, current_user, audit
from core_utils import new_id, now_iso, safe_doc
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import GenericPatch
from schemas_hr import HrOrgUnitCreate, HrEmployeeCreate, HrSettingsUpdate
from services import hr_service

router = APIRouter(prefix="/api")

EMP_UPDATE_FIELDS = {
    "name", "nik", "user_id", "dob", "gender", "phone", "email", "address",
    "department_id", "position_id", "shift_id", "device_user_id",
    "employment_type", "join_date", "status",
    "npwp", "ptkp_status", "bpjs_kes_enabled", "bpjs_kes_no", "bpjs_tk_enabled",
    "bpjs_tk_no", "jkk_risk_class", "bank_name", "bank_acc_no", "bank_acc_name",
    "base_salary", "allowances", "photo_url", "entity_id",
}
ORG_UPDATE_FIELDS = {"name", "code", "unit_type", "parent_id", "head_employee_id",
                     "description", "entity_id", "status"}


async def _can_view_pii(request: Request) -> bool:
    """True bila user punya permission hr.view_pii (tanpa raise)."""
    try:
        await require_permission(request, "hr", "view_pii")
        return True
    except HTTPException:
        return False


# ─── Org Units ───────────────────────────────────────────────────────────────

async def _next_org_code(unit_type: str) -> str:
    prefix = "DEPT-" if unit_type == "department" else "POS-"
    n = await db.hr_org_units.count_documents({"unit_type": unit_type})
    return f"{prefix}{n + 1:03d}"


@router.get("/hr/org-units")
async def list_org_units(request: Request, entity_id: str = None,
                         unit_type: str = None, status: str = None) -> List[Dict[str, Any]]:
    """Daftar unit organisasi (flat) — scoped entitas."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if unit_type:
        query["unit_type"] = unit_type
    if status:
        query["status"] = status
    query = resolve_list_scope("hr_org_units", query, ctx, entity_id)
    rows = await db.hr_org_units.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
    # enrich parent_name
    by_id = {u["id"]: u for u in rows}
    for u in rows:
        parent = by_id.get(u.get("parent_id"))
        u["parent_name"] = parent["name"] if parent else ""
    return rows


@router.get("/hr/org-units/tree")
async def org_units_tree(request: Request, entity_id: str = None) -> List[Dict[str, Any]]:
    """Hierarki organisasi (department > position) untuk entitas."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    query = resolve_list_scope("hr_org_units", {"status": "active"}, ctx, entity_id)
    rows = await db.hr_org_units.find(query, {"_id": 0}).to_list(2000)
    # hitung jumlah karyawan per unit (department/position)
    emp_q = resolve_list_scope("hr_employees", {"status": {"$ne": "resigned"}}, ctx, entity_id)
    emps = await db.hr_employees.find(emp_q, {"_id": 0, "department_id": 1, "position_id": 1}).to_list(5000)
    counts: Dict[str, int] = {}
    for e in emps:
        for key in (e.get("department_id"), e.get("position_id")):
            if key:
                counts[key] = counts.get(key, 0) + 1
    for u in rows:
        u["employee_count"] = counts.get(u["id"], 0)
    return hr_service.build_org_tree(rows)


@router.post("/hr/org-units")
async def create_org_unit(payload: HrOrgUnitCreate, request: Request) -> Dict[str, Any]:
    """Buat unit organisasi (department/position)."""
    actor = await require_permission(request, "hr", "manage_org")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama unit wajib diisi")
    if payload.unit_type not in ("department", "position"):
        raise HTTPException(status_code=400, detail="unit_type harus department atau position")
    if payload.unit_type == "position" and not payload.parent_id:
        raise HTTPException(status_code=400, detail="Jabatan (position) wajib punya departemen induk")
    code = payload.code.strip() or await _next_org_code(payload.unit_type)
    doc = {
        "id": new_id("orgu"),
        "code": code,
        "name": payload.name.strip(),
        "unit_type": payload.unit_type,
        "parent_id": payload.parent_id or "",
        "head_employee_id": payload.head_employee_id or "",
        "description": payload.description or "",
        "status": "active",
        "created_by": actor["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    doc["entity_id"] = payload.entity_id or ctx.active_entity_id
    await db.hr_org_units.insert_one(doc)
    await audit(actor["name"], "hr_org_unit_created", "hr_org_unit", doc["id"],
                {"code": code, "name": doc["name"], "unit_type": doc["unit_type"]})
    return safe_doc(doc)


@router.patch("/hr/org-units/{unit_id}")
async def update_org_unit(unit_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    """Update unit organisasi (whitelist field)."""
    actor = await require_permission(request, "hr", "manage_org")
    ctx = await entity_ctx(request)
    unit = safe_doc(await db.hr_org_units.find_one({"id": unit_id}, {"_id": 0}))
    if not unit:
        raise HTTPException(status_code=404, detail="Unit organisasi tidak ditemukan")
    assert_entity_access(unit, "hr_org_units", ctx)
    updates = {k: v for k, v in (payload.data or {}).items() if k in ORG_UPDATE_FIELDS}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    updates["updated_at"] = now_iso()
    updated = await db.hr_org_units.find_one_and_update(
        {"id": unit_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_org_unit_updated", "hr_org_unit", unit_id, updates)
    return safe_doc(updated)


@router.delete("/hr/org-units/{unit_id}")
async def deactivate_org_unit(unit_id: str, request: Request) -> Dict[str, Any]:
    """Nonaktifkan unit organisasi (soft delete). Tolak bila masih punya anak/karyawan aktif."""
    actor = await require_permission(request, "hr", "manage_org")
    ctx = await entity_ctx(request)
    unit = safe_doc(await db.hr_org_units.find_one({"id": unit_id}, {"_id": 0}))
    if not unit:
        raise HTTPException(status_code=404, detail="Unit organisasi tidak ditemukan")
    assert_entity_access(unit, "hr_org_units", ctx)
    child = await db.hr_org_units.count_documents(
        {"parent_id": unit_id, "status": "active"})
    if child:
        raise HTTPException(status_code=400, detail="Unit masih memiliki sub-unit aktif. Pindahkan/nonaktifkan dulu.")
    emp = await db.hr_employees.count_documents(
        {"$or": [{"department_id": unit_id}, {"position_id": unit_id}], "status": {"$ne": "resigned"}})
    if emp:
        raise HTTPException(status_code=400, detail="Masih ada karyawan aktif pada unit ini.")
    updated = await db.hr_org_units.find_one_and_update(
        {"id": unit_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_org_unit_deactivated", "hr_org_unit", unit_id, {})
    return safe_doc(updated)


# ─── Employees ───────────────────────────────────────────────────────────────

@router.get("/hr/employees")
async def list_employees(request: Request, entity_id: str = None, department_id: str = None,
                         status: str = None, search: str = None) -> List[Dict[str, Any]]:
    """Daftar karyawan (scoped entitas). PII diredaksi tanpa hr.view_pii."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if department_id:
        query["department_id"] = department_id
    if status:
        query["status"] = status
    query = resolve_list_scope("hr_employees", query, ctx, entity_id)
    rows = await db.hr_employees.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    if search:
        q = search.lower()
        rows = [r for r in rows if any(
            (str(r.get(k, "")) or "").lower().find(q) >= 0
            for k in ("name", "code", "nik", "phone", "email"))]
    omap = await hr_service.org_unit_map(ctx.allowed_entity_ids)
    umap = await hr_service.user_map([r.get("user_id") for r in rows])
    can_pii = await _can_view_pii(request)
    out: List[Dict[str, Any]] = []
    for r in rows:
        e = hr_service.enrich_employee(r, omap, umap)
        if not can_pii:
            e = hr_service.redact_employee_pii(e)
        out.append(e)
    return out


@router.get("/hr/summary")
async def hr_summary(request: Request, entity_id: str = None) -> Dict[str, Any]:
    """Ringkasan SDM: headcount, status, tipe kerja, akun ter-link, jumlah unit org."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    q = resolve_list_scope("hr_employees", {}, ctx, entity_id)
    rows = await db.hr_employees.find(
        q, {"_id": 0, "status": 1, "employment_type": 1, "user_id": 1}).to_list(5000)
    by_status: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    linked = 0
    for r in rows:
        by_status[r.get("status", "")] = by_status.get(r.get("status", ""), 0) + 1
        by_type[r.get("employment_type", "")] = by_type.get(r.get("employment_type", ""), 0) + 1
        if r.get("user_id"):
            linked += 1
    org_q = resolve_list_scope("hr_org_units", {"status": "active"}, ctx, entity_id)
    org_count = await db.hr_org_units.count_documents(org_q)
    dept_count = await db.hr_org_units.count_documents({**org_q, "unit_type": "department"})
    return {
        "total_employees": len(rows),
        "active": by_status.get("active", 0),
        "by_status": by_status,
        "by_type": by_type,
        "linked_accounts": linked,
        "org_units": org_count,
        "departments": dept_count,
    }


@router.get("/hr/employees/me")
async def my_employee(request: Request) -> Dict[str, Any]:
    """ESS — profil karyawan milik user login (data SENDIRI penuh, tanpa redaksi)."""
    user = await current_user(request)
    emp = safe_doc(await db.hr_employees.find_one({"user_id": user["id"]}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Profil karyawan belum tersedia untuk akun Anda")
    omap = await hr_service.org_unit_map([emp.get("entity_id")])
    umap = {user["id"]: user}
    return hr_service.enrich_employee(emp, omap, umap)


@router.post("/hr/employees")
async def create_employee(payload: HrEmployeeCreate, request: Request) -> Dict[str, Any]:
    """Buat master karyawan baru."""
    actor = await require_permission(request, "hr", "create")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama karyawan wajib diisi")
    # 1 akun login hanya boleh ter-link ke 1 karyawan.
    if payload.user_id:
        dup = await db.hr_employees.find_one({"user_id": payload.user_id}, {"_id": 0, "id": 1})
        if dup:
            raise HTTPException(status_code=409, detail="Akun user ini sudah terhubung ke karyawan lain")
    code = await hr_service.next_employee_code()
    # FASE G-0 — `hr.feature_toggles.npwp_required` DULU tidak dibaca kode mana pun.
    # Sekarang benar-benar mewajibkan NPWP saat pendaftaran karyawan bila toggle aktif.
    from services.config_resolver import value_of as _cfg_value
    if bool(await _cfg_value("hr.feature_toggles.npwp_required")) and not (payload.npwp or "").strip():
        raise HTTPException(
            status_code=400,
            detail=("NPWP wajib diisi (Pengaturan → SDM & Penggajian → 'Wajibkan NPWP "
                    "karyawan' aktif)."))
    doc = {
        "id": new_id("emp"),
        "code": code,
        "name": payload.name.strip(),
        "nik": payload.nik.strip(),
        "user_id": payload.user_id or "",
        "dob": payload.dob or "",
        "gender": payload.gender or "",
        "phone": payload.phone or "",
        "email": payload.email or "",
        "address": payload.address or "",
        "department_id": payload.department_id or "",
        "position_id": payload.position_id or "",
        "shift_id": payload.shift_id or "",
        "device_user_id": (payload.device_user_id or "").strip(),
        "employment_type": payload.employment_type or "tetap",
        "join_date": payload.join_date or "",
        "status": payload.status or "active",
        "npwp": payload.npwp or "",
        "ptkp_status": payload.ptkp_status or "TK0",
        "bpjs_kes_enabled": bool(payload.bpjs_kes_enabled),
        "bpjs_kes_no": payload.bpjs_kes_no or "",
        "bpjs_tk_enabled": bool(payload.bpjs_tk_enabled),
        "bpjs_tk_no": payload.bpjs_tk_no or "",
        "jkk_risk_class": payload.jkk_risk_class or "",
        "bank_name": payload.bank_name or "",
        "bank_acc_no": payload.bank_acc_no or "",
        "bank_acc_name": payload.bank_acc_name or "",
        "base_salary": round(float(payload.base_salary or 0), 2),
        "allowances": [a.model_dump() for a in (payload.allowances or [])],
        "photo_url": payload.photo_url or "",
        "created_by": payload.created_by or actor["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    doc["entity_id"] = payload.entity_id or ctx.active_entity_id
    await db.hr_employees.insert_one(doc)
    await audit(actor["name"], "hr_employee_created", "hr_employee", doc["id"],
                {"code": code, "name": doc["name"]})
    return safe_doc(doc)


@router.get("/hr/employees/{employee_id}")
async def get_employee(employee_id: str, request: Request) -> Dict[str, Any]:
    """Detail karyawan. PII diredaksi tanpa hr.view_pii."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    emp = safe_doc(await db.hr_employees.find_one({"id": employee_id}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
    assert_entity_access(emp, "hr_employees", ctx)
    omap = await hr_service.org_unit_map([emp.get("entity_id")])
    umap = await hr_service.user_map([emp.get("user_id")])
    emp = hr_service.enrich_employee(emp, omap, umap)
    if not await _can_view_pii(request):
        emp = hr_service.redact_employee_pii(emp)
    return emp


@router.get("/hr/employees/{employee_id}/360")
async def get_employee_360(employee_id: str, request: Request) -> Dict[str, Any]:
    """Karyawan 360° — profil + ringkasan absensi + cuti + slip gaji + KPI + dokumen.
    PII (gaji/rekening) diredaksi tanpa hr.view_pii."""
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    emp = safe_doc(await db.hr_employees.find_one({"id": employee_id}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
    assert_entity_access(emp, "hr_employees", ctx)
    omap = await hr_service.org_unit_map([emp.get("entity_id")])
    umap = await hr_service.user_map([emp.get("user_id")])
    emp = hr_service.enrich_employee(emp, omap, umap)
    can_pii = await _can_view_pii(request)
    if not can_pii:
        emp = hr_service.redact_employee_pii(emp)

    attendance = await db.hr_attendance.find(
        {"employee_id": employee_id}, {"_id": 0}).sort("date", -1).to_list(120)
    leaves = await db.hr_leave_requests.find(
        {"employee_id": employee_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    payslips = await db.hr_payslips.find(
        {"employee_id": employee_id}, {"_id": 0}).sort("period", -1).to_list(60)
    # BUGFIX 2026-07-26: sebelumnya membaca `db.hr_kpi_entries` — koleksi yang
    # TIDAK PERNAH ditulis siapa pun (nol penulis di seluruh repo), sehingga panel
    # KPI di profil karyawan SELALU KOSONG. Koleksi sebenarnya = `hr_kpi`
    # (ditulis `services/hr_kpi_service.py:51`, field employee_id/period/score).
    kpis = await db.hr_kpi.find(
        {"employee_id": employee_id}, {"_id": 0}).sort("created_at", -1).to_list(60)

    recent = attendance[:30]
    summ = {"present": 0, "late": 0, "leave": 0, "absent": 0, "total": len(recent)}
    for a in recent:
        st = (a.get("status") or "").lower()
        if st in ("hadir", "present", "wfh", "dinas"):
            summ["present"] += 1
        elif st in ("cuti", "izin", "leave", "sakit"):
            summ["leave"] += 1
        elif st in ("alfa", "absent", "mangkir"):
            summ["absent"] += 1
        if (a.get("late_min") or 0) > 0:
            summ["late"] += 1

    _PAY_PII = {"net", "gross", "base_salary", "allowances", "pph21", "bpjs_emp",
                "bpjs_er", "bpjs_emp_total", "bpjs_er_total", "overtime", "commission",
                "salary_earnings", "bank"}
    if not can_pii:
        payslips = [{k: (None if k in _PAY_PII else v) for k, v in p.items()} for p in payslips]

    documents: List[Dict[str, Any]] = []
    for p in payslips:
        documents.append({
            "doc_type": "hr_payslip", "label": "Slip Gaji",
            "source_id": p.get("id"), "number": p.get("number") or p.get("period"),
            "date": p.get("created_at"), "status": p.get("status"),
            "amount": p.get("net"), "period": p.get("period"),
        })

    emp["attendance"] = attendance[:60]
    emp["attendance_summary"] = summ
    emp["leave_requests"] = leaves
    emp["payslips"] = payslips
    emp["kpi_entries"] = kpis
    emp["documents"] = documents
    emp["can_view_pii"] = can_pii
    return emp


@router.patch("/hr/employees/{employee_id}")
async def update_employee(employee_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    """Update field karyawan (whitelist)."""
    actor = await require_permission(request, "hr", "update")
    ctx = await entity_ctx(request)
    emp = safe_doc(await db.hr_employees.find_one({"id": employee_id}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
    assert_entity_access(emp, "hr_employees", ctx)
    updates = {k: v for k, v in (payload.data or {}).items() if k in EMP_UPDATE_FIELDS}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    if "user_id" in updates and updates["user_id"]:
        dup = await db.hr_employees.find_one(
            {"user_id": updates["user_id"], "id": {"$ne": employee_id}}, {"_id": 0, "id": 1})
        if dup:
            raise HTTPException(status_code=409, detail="Akun user ini sudah terhubung ke karyawan lain")
    if "base_salary" in updates:
        try:
            updates["base_salary"] = round(float(updates["base_salary"] or 0), 2)
        except (ValueError, TypeError):
            updates["base_salary"] = 0.0
    updates["updated_at"] = now_iso()
    updated = await db.hr_employees.find_one_and_update(
        {"id": employee_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_employee_updated", "hr_employee", employee_id,
                {k: v for k, v in updates.items() if k not in hr_service.PII_FIELDS})
    return safe_doc(updated)


@router.delete("/hr/employees/{employee_id}")
async def deactivate_employee(employee_id: str, request: Request) -> Dict[str, Any]:
    """Nonaktifkan karyawan (soft delete → status resigned)."""
    actor = await require_permission(request, "hr", "delete")
    ctx = await entity_ctx(request)
    emp = safe_doc(await db.hr_employees.find_one({"id": employee_id}, {"_id": 0}))
    if not emp:
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
    assert_entity_access(emp, "hr_employees", ctx)
    updated = await db.hr_employees.find_one_and_update(
        {"id": employee_id}, {"$set": {"status": "resigned", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "hr_employee_deactivated", "hr_employee", employee_id, {})
    return safe_doc(updated)


# ─── HR Settings (config statutory; system_settings scope='hr') ───────────────

@router.get("/hr/settings")
async def read_hr_settings(request: Request) -> Dict[str, Any]:
    """Baca config HR/Payroll YANG BERLAKU untuk badan usaha aktif.

    FASE E-4 (E4.5) — nilai global ditimpa override badan usaha bila ada; daftar
    kunci yang ditimpa dikembalikan pada `entity_overrides` supaya layar bisa
    menandai mana yang "Global" dan mana "Badan usaha ini".
    """
    await require_permission(request, "hr", "view")
    ctx = await entity_ctx(request)
    return await hr_service.get_hr_settings(ctx.active_entity_id)


@router.put("/hr/settings")
async def update_hr_settings(payload: HrSettingsUpdate, request: Request) -> Dict[str, Any]:
    """Update config HR (partial). Hanya hr.manage_settings (admin)."""
    actor = await require_permission(request, "hr", "manage_settings")
    data: Dict[str, Any] = {"updated_at": now_iso()}
    for field in ("bpjs", "jkk_classes", "ptkp_table", "ter_enabled",
                  "feature_toggles", "employment_types", "payroll_commission_mode"):
        val = getattr(payload, field, None)
        if val is not None:
            data[field] = val
    existing = await db.system_settings.find_one({"scope": "hr"}, {"_id": 0})
    if existing:
        await db.system_settings.find_one_and_update(
            {"scope": "hr"}, {"$set": data},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    else:
        doc = {"id": new_id("set"), "scope": "hr", "created_at": now_iso(), **data}
        await db.system_settings.insert_one(doc)
    await audit(actor["name"], "hr_settings_updated", "system_settings", "hr", data)
    return await hr_service.get_hr_settings()
