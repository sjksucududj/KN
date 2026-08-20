"""Audit logs router.

FASE E-0 (E0.3) — dua cacat ditutup sekaligus:
  * **Gerbang izin salah**: dulu `require_permission(request, "product", "view")`
    sehingga **sales & gudang** bisa membaca jejak SELURUH grup. Sekarang memakai
    resource izin tersendiri `audit.view` (hanya `admin`).
  * **Tanpa cakupan entitas**: jejak sekarang disaring `scope_entity_id` = entitas
    aktif; baris lama tanpa stempel tetap terlihat sebagai jejak tingkat grup
    (`resolve_list_scope_inherit`) agar riwayat tidak hilang.
"""
from typing import Any

from fastapi import APIRouter, Query, Request

from core_utils import safe_doc
from db import db
from dependencies import require_permission
from entity_scope import entity_ctx, resolve_list_scope_inherit
from pagination import build_search, envelope, fetch_page, get_page_params, is_paged

router = APIRouter(prefix="/api")


@router.get("/audit-logs")
async def list_audit_logs(request: Request, entity_id: str = Query(None)) -> Any:
    await require_permission(request, "audit", "view")
    ctx = await entity_ctx(request)
    base = resolve_list_scope_inherit("audit_logs", {}, ctx, entity_id)
    # Label badan usaha supaya layar bisa membedakan "sumber daya" (entity_type/entity_id,
    # arti lama) dari "badan usaha" (scope_entity_id, FASE E-0).
    ent_names = {e["id"]: (e.get("short_name") or e.get("legal_name") or e["id"])
                 async for e in db.business_entities.find(
                     {}, {"_id": 0, "id": 1, "short_name": 1, "legal_name": 1})}

    def _label(row):
        row = safe_doc(row)
        sid = row.get("scope_entity_id")
        row["scope_entity_name"] = ent_names.get(sid, "Tingkat grup" if not sid else sid)
        return row

    if is_paged(request):
        page, page_size, q, _sort = get_page_params(request)
        query = base
        if q:
            search = build_search(q, ["action", "resource", "user_name", "resource_id",
                                      "actor", "entity_type"])
            query = {"$and": [base, search]}
        items, total = await fetch_page(db.audit_logs, query, page, page_size,
                                        sort_field="timestamp", sort_dir=-1)
        return envelope([_label(x) for x in items if x], total, page, page_size)
    logs = await db.audit_logs.find(base, {"_id": 0}).sort("timestamp", -1).to_list(500)
    return [_label(log) for log in logs if log]
