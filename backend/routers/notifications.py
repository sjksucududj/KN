"""Notifications router (Notification Center — Fase 0).

Notifikasi in-app (polling). Sumber event REAL (bukan mock): stok menipis &
reservasi mendekati kedaluwarsa — di-generate dari data inventory & sales_orders.
WebSocket realtime menyusul di Fase 5 (lihat KN_14 §8.2).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import current_user, require_role
from core_utils import now_iso
from entity_scope import entity_ctx, resolve_scope_ids
from services.notification_service import generate_system_notifications

router = APIRouter(prefix="/api")


async def _scope_query(request: Request, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Notifikasi terlihat bila ditujukan ke role user, ke 'all', atau ke user spesifik
    **DAN** milik entitas yang boleh dilihat pengguna.

    FASE E-0 (L1) — sebelumnya `notifications` terdaftar SHARED sehingga penyaringan
    hanya per user/role: sales CV Kanda menerima notifikasi "SO-0007" milik
    PT Kain Suka Cita. Sekarang entitas ikut menyaring, tetapi notifikasi **sistem**
    (`entity_id` None/kosong) tetap tampil di semua konteks.
    """
    user = await current_user(request)
    ctx = await entity_ctx(request)
    ids = resolve_scope_ids(ctx, entity_id if entity_id and entity_id != "all" else None)
    # FASE E-8 — mode gabungan sudah ditangani `resolve_scope_ids` lewat `ctx.view_all`
    # (yang kini mengikuti JUMLAH PENUGASAN, bukan nama peran). Tidak perlu lagi
    # cabang khusus `is_cross_entity` di sini: Admin Sales bertugas 2 badan usaha
    # dulu kehilangan notifikasi badan usaha keduanya di mode "Semua Entitas".
    audience = {"$or": [
        {"recipient_role": {"$in": [user.get("role"), "all"]}},
        {"recipient_user": user.get("id")},
    ]}
    scope = {"$or": [{"entity_id": {"$in": list(ids)}},
                     {"entity_id": None}, {"entity_id": ""},
                     {"entity_id": {"$exists": False}}]}
    return {"$and": [audience, scope]}


@router.get("/notifications")
async def list_notifications(
    request: Request, entity_id: str = None, unread_only: bool = False
) -> List[Dict[str, Any]]:
    query = await _scope_query(request, entity_id)
    if unread_only:
        query = {"$and": [query, {"read": False}]}
    return await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/notifications/unread-count")
async def unread_count(request: Request, entity_id: str = None) -> Dict[str, int]:
    query = {"$and": [await _scope_query(request, entity_id), {"read": False}]}
    return {"count": await db.notifications.count_documents(query)}


@router.post("/notifications/read-all")
async def mark_all_read(request: Request, entity_id: str = None) -> Dict[str, Any]:
    query = {"$and": [await _scope_query(request, entity_id), {"read": False}]}
    result = await db.notifications.update_many(query, {"$set": {"read": True, "read_at": now_iso()}})
    return {"updated": result.modified_count}


@router.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: str, request: Request) -> Dict[str, Any]:
    """Tandai satu notifikasi terbaca — hanya bila notifikasi itu memang milik
    audiens & entitas pengguna (anti-IDOR: dulu `id` saja sudah cukup)."""
    scope = await _scope_query(request)
    notification = await db.notifications.find_one_and_update(
        {"$and": [{"id": notification_id}, scope]},
        {"$set": {"read": True, "read_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    return notification


@router.post("/notifications/generate")
async def generate(request: Request) -> Dict[str, Any]:
    """Pindai event sistem (stok menipis, reservasi kedaluwarsa) → buat notifikasi."""
    await require_role(request, ["manager"])  # admin auto-allowed di require_role
    created = await generate_system_notifications()
    return {"created": created}
