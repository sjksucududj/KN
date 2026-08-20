"""M1 — Makloons router (master mitra makloon/subkontraktor).

Koleksi kanonik `makloons` (prefix mak_), SCOPED per entitas (mirror suppliers).
Pola dari routers/suppliers.py. Respons ARRAY/OBJEK telanjang (kontrak KN).
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas import MakloonCreate, GenericPatch
from services.makloon_service import makloon_360, compute_makloon_scorecard

router = APIRouter(prefix="/api")

_ALLOWED = {"name", "npwp", "pic_name", "phone", "email", "address", "city",
            "process_types", "capacity_note", "capacity_per_month", "capacity_unit",
            "default_tariff", "tariff_unit", "payment_term_code", "lead_time_days",
            "entity_id", "notes", "status"}


async def _next_makloon_code() -> str:
    last = await db.makloons.find_one({}, {"_id": 0, "code": 1}, sort=[("code", -1)])
    n = 0
    if last and isinstance(last.get("code"), str) and last["code"].startswith("MAK-"):
        try:
            n = int(last["code"].split("-")[1])
        except (ValueError, IndexError):
            n = await db.makloons.count_documents({})
    else:
        n = await db.makloons.count_documents({})
    return f"MAK-{n + 1:05d}"


@router.get("/makloons")
async def list_makloons(request: Request, entity_id: str = None, status: str = None) -> List[Dict[str, Any]]:
    await require_permission(request, "makloon", "view")
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    query = resolve_list_scope("makloons", query, ctx, entity_id)
    return await db.makloons.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/makloons")
async def create_makloon(payload: MakloonCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon", "create")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama makloon wajib diisi")
    code = await _next_makloon_code()
    doc = {
        "id": new_id("mak"),
        "code": code,
        "name": payload.name.strip(),
        "npwp": payload.npwp.strip(),
        "pic_name": payload.pic_name.strip(),
        "phone": payload.phone.strip(),
        "email": payload.email.strip(),
        "address": payload.address.strip(),
        "city": payload.city.strip(),
        "process_types": [p.strip() for p in (payload.process_types or []) if p.strip()],
        "capacity_note": payload.capacity_note.strip(),
        "capacity_per_month": float(payload.capacity_per_month or 0),
        "capacity_unit": (payload.capacity_unit or "yard").strip(),
        "default_tariff": float(payload.default_tariff or 0),
        "tariff_unit": (payload.tariff_unit or "output").strip(),
        "payment_term_code": payload.payment_term_code,
        "lead_time_days": int(payload.lead_time_days or 0),
        "entity_id": payload.entity_id or ctx.active_entity_id,
        "notes": payload.notes,
        "status": "active",
        "created_by": payload.created_by or actor.get("name", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.makloons.insert_one(doc)
    await audit(actor.get("name", ""), "makloon_created", "makloon", doc["id"],
                {"code": code, "name": doc["name"]})
    return safe_doc(doc)


@router.get("/makloons/{makloon_id}")
async def get_makloon(makloon_id: str, request: Request) -> Dict[str, Any]:
    """Makloon 360 — profil + riwayat order + tagihan jasa + resep + scorecard."""
    await require_permission(request, "makloon", "view")
    ctx = await entity_ctx(request)
    data = await makloon_360(makloon_id)
    if not data:
        raise HTTPException(status_code=404, detail="Makloon tidak ditemukan")
    assert_entity_access(data, "makloons", ctx)
    return data


@router.patch("/makloons/{makloon_id}")
async def update_makloon(makloon_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon", "update")
    mk = await db.makloons.find_one({"id": makloon_id}, {"_id": 0})
    if not mk:
        raise HTTPException(status_code=404, detail="Makloon tidak ditemukan")
    updates = {k: v for k, v in (payload.data or {}).items() if k in _ALLOWED}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    if "lead_time_days" in updates:
        try:
            updates["lead_time_days"] = int(updates["lead_time_days"] or 0)
        except (ValueError, TypeError):
            updates["lead_time_days"] = 0
    for numf in ("capacity_per_month", "default_tariff"):
        if numf in updates:
            try:
                updates[numf] = float(updates[numf] or 0)
            except (ValueError, TypeError):
                updates[numf] = 0
    updates["updated_at"] = now_iso()
    updated = await db.makloons.find_one_and_update(
        {"id": makloon_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor.get("name", ""), "makloon_updated", "makloon", makloon_id, updates)
    return safe_doc(updated)


@router.delete("/makloons/{makloon_id}")
async def deactivate_makloon(makloon_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "makloon", "delete")
    mk = await db.makloons.find_one({"id": makloon_id}, {"_id": 0})
    if not mk:
        raise HTTPException(status_code=404, detail="Makloon tidak ditemukan")
    updated = await db.makloons.find_one_and_update(
        {"id": makloon_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor.get("name", ""), "makloon_deactivated", "makloon", makloon_id, {})
    return safe_doc(updated)


@router.get("/makloons/{makloon_id}/scorecard")
async def get_makloon_scorecard(makloon_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "makloon", "view")
    card = await compute_makloon_scorecard(makloon_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Makloon tidak ditemukan")
    return card
