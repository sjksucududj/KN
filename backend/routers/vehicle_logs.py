"""Router — Aset & GA: Master Kendaraan + Laporan Penggunaan & Biaya Kendaraan.

Koleksi: vehicles (veh_), vehicle_usage_logs (vlog_). SCOPED per entitas.
RBAC: modul `vehicle_log`. Tidak posting GL (record operasional; biaya bisa ditautkan ke PD).
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Request, Query, HTTPException
from pymongo import ReturnDocument

from db import db
from core_utils import new_id, now_iso, next_doc_number, safe_doc
from dependencies import require_permission, audit
from entity_scope import entity_ctx, resolve_list_scope, assert_entity_access
from schemas_cash_advance import (
    VehicleCreate, VehicleUpdate, VehicleUsageCreate, VehicleUsageUpdate,
)

router = APIRouter(prefix="/api")

VEH_COLL = "vehicles"
LOG_COLL = "vehicle_usage_logs"


def _r(v: Any) -> float:
    return round(float(v or 0), 2)


# ─── Master Kendaraan ─────────────────────────────────────────
@router.get("/vehicles")
async def list_vehicles(request: Request, entity_id: str = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "vehicle_log", "view")
    ctx = await entity_ctx(request)
    q = resolve_list_scope(VEH_COLL, {}, ctx, entity_id)
    return await db[VEH_COLL].find(q, {"_id": 0}).sort("no_polisi", 1).to_list(1000)


@router.post("/vehicles")
async def create_vehicle(payload: VehicleCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "vehicle_log", "create")
    ctx = await entity_ctx(request)
    entity_id = payload.entity_id or ctx.active_entity_id
    if entity_id not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas ini")
    no_pol = (payload.no_polisi or "").strip().upper()
    if not no_pol:
        raise HTTPException(status_code=400, detail="No. Polisi wajib diisi")
    if await db[VEH_COLL].find_one({"no_polisi": no_pol, "entity_id": entity_id}, {"_id": 0}):
        raise HTTPException(status_code=409, detail=f"Kendaraan {no_pol} sudah terdaftar")
    doc = {
        "id": new_id("veh"), "entity_id": entity_id, "no_polisi": no_pol,
        "nama": (payload.nama or "").strip(), "jenis": payload.jenis or "mobil",
        "active": bool(payload.active), "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db[VEH_COLL].insert_one(doc)
    await audit(actor.get("name", ""), "vehicle_created", "vehicle", doc["id"], {"no_polisi": no_pol})
    return safe_doc(doc)


@router.patch("/vehicles/{veh_id}")
async def update_vehicle(veh_id: str, payload: VehicleUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "vehicle_log", "update")
    ctx = await entity_ctx(request)
    doc = await db[VEH_COLL].find_one({"id": veh_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Kendaraan tidak ditemukan")
    assert_entity_access(doc, VEH_COLL, ctx)
    upd: Dict[str, Any] = {}
    for f in ["nama", "jenis"]:
        v = getattr(payload, f, None)
        if v is not None:
            upd[f] = v.strip() if isinstance(v, str) else v
    if payload.no_polisi is not None:
        upd["no_polisi"] = payload.no_polisi.strip().upper()
    if payload.active is not None:
        upd["active"] = bool(payload.active)
    upd["updated_at"] = now_iso()
    updated = await db[VEH_COLL].find_one_and_update(
        {"id": veh_id}, {"$set": upd}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor.get("name", ""), "vehicle_updated", "vehicle", veh_id, upd)
    return safe_doc(updated)


@router.delete("/vehicles/{veh_id}")
async def delete_vehicle(veh_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "vehicle_log", "delete")
    ctx = await entity_ctx(request)
    doc = await db[VEH_COLL].find_one({"id": veh_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Kendaraan tidak ditemukan")
    assert_entity_access(doc, VEH_COLL, ctx)
    used = await db[LOG_COLL].count_documents({"vehicle_id": veh_id})
    if used:
        # non-destruktif: nonaktifkan bila sudah dipakai log
        await db[VEH_COLL].update_one({"id": veh_id}, {"$set": {"active": False, "updated_at": now_iso()}})
        return {"deactivated": True, "used_in_logs": used}
    await db[VEH_COLL].delete_one({"id": veh_id})
    await audit(actor.get("name", ""), "vehicle_deleted", "vehicle", veh_id, {})
    return {"deleted": True}


# ─── Log Penggunaan & Biaya ────────────────────────────────────
def _build_log(payload, entity_id: str) -> Dict[str, Any]:
    bbm = _r(payload.bbm); tol = _r(payload.tol)
    parkir = _r(payload.parkir); lain = _r(payload.lain_lain)
    km_awal = _r(payload.km_awal); km_akhir = _r(payload.km_akhir)
    return {
        "entity_id": entity_id,
        "vehicle_id": (payload.vehicle_id or "").strip(),
        "no_polisi": (payload.no_polisi or "").strip().upper(),
        "tanggal": payload.tanggal or now_iso(),
        "km_awal": km_awal, "km_akhir": km_akhir,
        "jarak_tempuh": _r(max(0.0, km_akhir - km_awal)),
        "bbm": bbm, "tol": tol, "parkir": parkir, "lain_lain": lain,
        "total": _r(bbm + tol + parkir + lain),
        "tujuan": (payload.tujuan or "").strip(),
        "driver": (payload.driver or "").strip(),
        "pemakai": (payload.pemakai or "").strip(),
        "mengetahui": (payload.mengetahui or "").strip(),
        "cash_advance_id": (payload.cash_advance_id or "").strip(),
    }


@router.get("/vehicle-usage-logs")
async def list_vehicle_logs(request: Request, entity_id: str = Query(None),
                            vehicle_id: str = Query(None)) -> List[Dict[str, Any]]:
    await require_permission(request, "vehicle_log", "view")
    ctx = await entity_ctx(request)
    q = resolve_list_scope(LOG_COLL, {}, ctx, entity_id)
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    return await db[LOG_COLL].find(q, {"_id": 0}).sort("tanggal", -1).to_list(2000)


@router.get("/vehicle-usage-logs/summary")
async def vehicle_logs_summary(request: Request, entity_id: str = Query(None)) -> Dict[str, Any]:
    await require_permission(request, "vehicle_log", "view")
    ctx = await entity_ctx(request)
    q = resolve_list_scope(LOG_COLL, {}, ctx, entity_id)
    rows = await db[LOG_COLL].find(q, {"_id": 0}).to_list(5000)
    per_vehicle: Dict[str, Dict[str, Any]] = {}
    grand = 0.0
    for r in rows:
        key = r.get("no_polisi") or r.get("vehicle_id") or "-"
        pv = per_vehicle.setdefault(key, {"no_polisi": key, "total": 0.0, "jarak": 0.0, "count": 0})
        pv["total"] = _r(pv["total"] + _r(r.get("total")))
        pv["jarak"] = _r(pv["jarak"] + _r(r.get("jarak_tempuh")))
        pv["count"] += 1
        grand += _r(r.get("total"))
    return {"grand_total": _r(grand), "count": len(rows), "per_vehicle": list(per_vehicle.values())}


@router.post("/vehicle-usage-logs")
async def create_vehicle_log(payload: VehicleUsageCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "vehicle_log", "create")
    ctx = await entity_ctx(request)
    entity_id = payload.entity_id or ctx.active_entity_id
    if entity_id not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas ini")
    if not (payload.vehicle_id or payload.no_polisi):
        raise HTTPException(status_code=400, detail="Pilih kendaraan atau isi No. Polisi")
    number = await next_doc_number(LOG_COLL, "number", "VHL-", entity_id=entity_id)
    doc = {"id": new_id("vlog"), "number": number, **_build_log(payload, entity_id),
           "created_by": actor.get("name", ""), "created_at": now_iso(), "updated_at": now_iso()}
    # lengkapi no_polisi dari master bila hanya vehicle_id
    if doc["vehicle_id"] and not doc["no_polisi"]:
        veh = await db[VEH_COLL].find_one({"id": doc["vehicle_id"]}, {"_id": 0, "no_polisi": 1})
        if veh:
            doc["no_polisi"] = veh.get("no_polisi", "")
    await db[LOG_COLL].insert_one(doc)
    await audit(actor.get("name", ""), "vehicle_log_created", "vehicle_usage_log", doc["id"],
                {"number": number, "total": doc["total"]})
    return safe_doc(doc)


@router.patch("/vehicle-usage-logs/{log_id}")
async def update_vehicle_log(log_id: str, payload: VehicleUsageUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "vehicle_log", "update")
    ctx = await entity_ctx(request)
    doc = await db[LOG_COLL].find_one({"id": log_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Log tidak ditemukan")
    assert_entity_access(doc, LOG_COLL, ctx)
    upd: Dict[str, Any] = {}
    for f in ["tanggal", "tujuan", "driver", "pemakai", "mengetahui"]:
        v = getattr(payload, f, None)
        if v is not None:
            upd[f] = v.strip() if isinstance(v, str) else v
    for f in ["km_awal", "km_akhir", "bbm", "tol", "parkir", "lain_lain"]:
        v = getattr(payload, f, None)
        if v is not None:
            upd[f] = _r(v)
    merged = {**doc, **upd}
    upd["jarak_tempuh"] = _r(max(0.0, _r(merged.get("km_akhir")) - _r(merged.get("km_awal"))))
    upd["total"] = _r(_r(merged.get("bbm")) + _r(merged.get("tol")) +
                      _r(merged.get("parkir")) + _r(merged.get("lain_lain")))
    upd["updated_at"] = now_iso()
    updated = await db[LOG_COLL].find_one_and_update(
        {"id": log_id}, {"$set": upd}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor.get("name", ""), "vehicle_log_updated", "vehicle_usage_log", log_id, upd)
    return safe_doc(updated)


@router.delete("/vehicle-usage-logs/{log_id}")
async def delete_vehicle_log(log_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "vehicle_log", "delete")
    ctx = await entity_ctx(request)
    doc = await db[LOG_COLL].find_one({"id": log_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Log tidak ditemukan")
    assert_entity_access(doc, LOG_COLL, ctx)
    await db[LOG_COLL].delete_one({"id": log_id})
    await audit(actor.get("name", ""), "vehicle_log_deleted", "vehicle_usage_log", log_id, {})
    return {"deleted": True}
