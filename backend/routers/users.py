"""Router AKUN PENGGUNA (FASE E-2 — akun tertaut badan usaha via HR).

Semua aturan hidup di `services/user_admin_service.py` supaya router tetap tipis
dan tidak ada dua tempat yang memutuskan hal sama (pelajaran dari FASE E-1).

Endpoint:
  GET    /api/users                      daftar + filter + paging + pengayaan (E2.5)
  GET    /api/users/{id}                 satu akun (dengan label badan usaha & HR)
  GET    /api/hr-employees-available     karyawan HR yang belum punya akun (E2.1)
  POST   /api/users                      buat akun (badan usaha dari HR bila tertaut)
  PATCH  /api/users/{id}                 ubah akun (role/entitas → cabut sesi)
  DELETE /api/users/{id}                 NONAKTIFKAN (soft) — bukan hapus
  POST   /api/users/{id}/reactivate      aktifkan kembali
  POST   /api/users/{id}/reset-password  reset password (audit, tanpa bocor)
  POST   /api/users/{id}/revoke-sessions cabut sesi (paksa login ulang)
"""
from typing import Any, Dict, List, Union

from fastapi import APIRouter, HTTPException, Query, Request

from db import db
from dependencies import require_permission, audit
from core_utils import safe_doc
from pagination import (build_search, envelope, fetch_page, get_page_params,
                       is_paged, merge_query)
from schemas import GenericPatch, UserCreate, UserResetPasswordBody
from services import user_admin_service as svc
from entity_scope import entity_ctx, resolve_list_scope

router = APIRouter(prefix="/api")


@router.get("/users")
async def list_users(
    request: Request,
    entity_id: str = Query("", description="filter badan usaha (home ATAU diizinkan)"),
    role: str = Query(""),
    status: str = Query(""),
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """E2.5 — daftar akun dengan filter, paging, dan pengayaan.

    Tanpa param `page`/`page_size` tetap mengembalikan array telanjang supaya
    konsumen lama (AdminView, gate kontrak API) tidak patah.
    """
    await require_permission(request, "user", "view")
    page, page_size, q, _sort = get_page_params(request, default_size=25)
    query: Dict[str, Any] = {}
    if entity_id:
        query["$or"] = [{"home_entity_id": entity_id},
                        {"allowed_entity_ids": entity_id}]
    if role:
        query["role"] = role
    if status:
        query["status"] = status
    query = merge_query(query, build_search(q, ["name", "email", "phone"]))

    if is_paged(request):
        rows, total = await fetch_page(
            db.users, query, page, page_size, sort_field="created_at", sort_dir=-1,
            projection={"_id": 0, "password_hash": 0})
        return envelope(await svc.enrich_users(rows), total, page, page_size)
    rows = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort(
        "created_at", -1).to_list(200)
    return await svc.enrich_users(rows)


@router.get("/users/count")
async def count_users(request: Request, entity_id: str = Query(""),
                      status: str = Query("")) -> Dict[str, Any]:
    await require_permission(request, "user", "view")
    query: Dict[str, Any] = {}
    if entity_id:
        query["$or"] = [{"home_entity_id": entity_id}, {"allowed_entity_ids": entity_id}]
    if status:
        query["status"] = status
    return {"count": await db.users.count_documents(query)}


@router.get("/hr-employees-available")
async def available_employees(request: Request,
                              entity_id: str = Query(""),
                              q: str = Query(""),
                              limit: int = Query(50, ge=1, le=200)) -> List[Dict[str, Any]]:
    """E2.1 — karyawan HR yang BELUM punya akun (untuk pencarian di formulir akun).

    Dipakai supaya admin memilih karyawan, bukan mengetik ulang nama & badan
    usahanya (sumber utama data tidak sinkron antara HR dan akun).
    `hr_employees` adalah koleksi ter-scope, jadi daftar ini WAJIB lewat
    `resolve_list_scope` — kalau tidak, admin sales satu badan usaha bisa melihat
    daftar karyawan badan usaha lain lewat pintu formulir akun.
    """
    await require_permission(request, "user", "view")
    ctx = await entity_ctx(request)
    base: Dict[str, Any] = {"status": "active",
                            "$or": [{"user_id": ""}, {"user_id": None},
                                    {"user_id": {"$exists": False}}]}
    if q:
        base["name"] = {"$regex": q, "$options": "i"}
    query = resolve_list_scope("hr_employees", base, ctx,
                               entity_id_param=(entity_id or "all"))
    rows = await db.hr_employees.find(
        query, {"_id": 0, "id": 1, "code": 1, "name": 1, "email": 1, "phone": 1,
                "entity_id": 1, "department_id": 1, "position_id": 1}).sort(
        "name", 1).to_list(limit)
    ents = {e["id"]: e for e in await db.business_entities.find(
        {}, {"_id": 0, "id": 1, "legal_name": 1, "short_name": 1}).to_list(500)}
    for r in rows:
        e = ents.get(r.get("entity_id")) or {}
        r["entity_name"] = e.get("legal_name") or e.get("short_name") or r.get("entity_id", "")
    return [safe_doc(r) for r in rows]


@router.get("/users/{user_id}")
async def get_user(user_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "user", "view")
    user = await svc.get_user_or_404(user_id)
    enriched = await svc.enrich_users([user])
    return enriched[0]


@router.post("/users")
async def create_user(payload: UserCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "user", "create")
    user, info = await svc.create_user(payload.model_dump())
    await audit(actor["name"], "user_created", "user", user["id"],
                {**user, "home_from_hr": info.get("home_from_hr", False)},
                scope_entity_id=user.get("home_entity_id", ""))
    out = (await svc.enrich_users([user]))[0]
    out["home_from_hr"] = info.get("home_from_hr", False)
    return out


@router.patch("/users/{user_id}")
async def update_user(user_id: str, payload: GenericPatch,
                      request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "user", "update")
    # Status sengaja tidak lewat sini — pakai DELETE / reactivate supaya pagar
    # “admin terakhir” & pencabutan sesi tidak bisa dilewati dengan patch biasa.
    if "status" in (payload.data or {}):
        raise HTTPException(
            status_code=400,
            detail="Status akun diubah lewat tombol Nonaktifkan / Aktifkan kembali, "
                   "bukan lewat pembaruan biasa.")
    after = await svc.update_user(user_id, payload.data or {})
    await audit(actor["name"], "user_updated", "user", user_id,
                {"changed": after.get("changed_fields", []),
                 "home_entity_id": after.get("home_entity_id"),
                 "allowed_entity_ids": after.get("allowed_entity_ids"),
                 "role": after.get("role"),
                 "sessions_revoked": after.get("sessions_revoked", 0),
                 "revoke_reasons": after.get("revoke_reasons", [])},
                scope_entity_id=after.get("home_entity_id", ""))
    out = (await svc.enrich_users([after]))[0]
    out["sessions_revoked"] = after.get("sessions_revoked", 0)
    out["revoke_reasons"] = after.get("revoke_reasons", [])
    return out


@router.delete("/users/{user_id}")
async def deactivate_user(user_id: str, request: Request) -> Dict[str, Any]:
    """E2.4 — NONAKTIFKAN akun (soft). Baris tidak pernah dihapus."""
    actor = await require_permission(request, "user", "delete")
    user = await svc.set_status(user_id, "inactive")
    await audit(actor["name"], "user_deactivated", "user", user_id,
                {"status": "inactive",
                 "sessions_revoked": user.get("sessions_revoked", 0)},
                scope_entity_id=user.get("home_entity_id", ""))
    out = (await svc.enrich_users([user]))[0]
    out["sessions_revoked"] = user.get("sessions_revoked", 0)
    return out


@router.post("/users/{user_id}/reactivate")
async def reactivate_user(user_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "user", "update")
    user = await svc.set_status(user_id, "active")
    await audit(actor["name"], "user_reactivated", "user", user_id,
                {"status": "active"}, scope_entity_id=user.get("home_entity_id", ""))
    return (await svc.enrich_users([user]))[0]


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, body: UserResetPasswordBody,
                         request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "user", "update")
    user = await svc.get_user_or_404(user_id)
    result = await svc.reset_password(user_id, body.new_password)
    # Password TIDAK pernah masuk jejak audit — hanya faktanya.
    await audit(actor["name"], "user_password_reset", "user", user_id,
                {"sessions_revoked": result["sessions_revoked"]},
                scope_entity_id=user.get("home_entity_id", ""))
    return result


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_sessions(user_id: str, request: Request) -> Dict[str, Any]:
    """Paksa login ulang (mis. setelah penugasan badan usaha diubah manual di DB)."""
    actor = await require_permission(request, "user", "update")
    user = await svc.get_user_or_404(user_id)
    revoked = await svc.revoke_sessions(user_id, "dicabut admin")
    await audit(actor["name"], "user_sessions_revoked", "user", user_id,
                {"sessions_revoked": revoked},
                scope_entity_id=user.get("home_entity_id", ""))
    return {"user_id": user_id, "sessions_revoked": revoked,
            "message": f"{revoked} sesi dicabut — pengguna harus masuk lagi."}
