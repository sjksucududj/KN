"""R0 — Sales Return Policy Engine router (prefix /api).

CRUD kebijakan retur jual (koleksi `sales_return_policies`, prefix `srp_`) dengan
scope global/kategori/customer + endpoint eligibility (deadline & kelayakan retur).

Kebijakan retur SUPPLIER berada embedded di master supplier (lihat suppliers.py:
`GET /suppliers/{id}/return-policy`). Router ini melengkapi sisi JUAL.

Guardrails: setiap endpoint menegakkan auth; respons = objek/array telanjang
(list pakai bare array); numeric bound via schema; koleksi SHARED (master data).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Query
from pymongo import ReturnDocument

from db import db
from dependencies import require_permission, require_any_permission, audit
from core_utils import new_id, now_iso, safe_doc
from entity_scope import entity_ctx
from schemas import SalesReturnPolicyCreate, GenericPatch, SALES_RETURN_TYPES, SALES_RETURN_OUTCOMES
from services import return_policy_service as rps

router = APIRouter(prefix="/api")

VALID_SCOPES = ("global", "category", "customer")


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc.pop("_id", None)
    return doc


# ─── LIST ────────────────────────────────────────────────────────────────────

@router.get("/sales-return-policies")
async def list_sales_return_policies(
    request: Request,
    scope: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    layered: bool = Query(True),
) -> List[Dict[str, Any]]:
    """Daftar kebijakan retur jual (master data — dilihat admin/manager).

    FASE E-4 (E4.3): kebijakan kini BERLAPIS. Baris global (`entity_id` kosong/"all")
    tetap tampil di semua badan usaha, baris khusus badan usaha hanya tampil di
    badan usahanya — masing-masing berlencana asal (`source_label`).
    """
    # MEMBACA kebijakan retur ≠ mengubah Pusat Pengaturan. Dulu gerbangnya
    # `settings.view` (izin master data), sehingga tab "Kebijakan Retur" yang SENGAJA
    # diberikan ke Admin Sales (`config/roles.js` — "perlu membaca kebijakan retur saat
    # memproses retur") selalu 403: tab ada, isinya dinding. Orang yang MEMPROSES retur
    # harus boleh membaca aturannya; MENGUBAHNYA tetap butuh izin pengaturan
    # (dijaga endpoint POST/PATCH/DELETE — tidak diubah).
    await require_any_permission(request, [("settings", "view"),
                                           ("sales_return", "view")])
    ctx = await entity_ctx(request)
    from services import entity_master_service as ems
    data = await ems.list_layered("sales-return-policies", ctx,
                                  include_inactive=include_inactive)
    rows = data["rows"]
    if scope:
        rows = [r for r in rows if r.get("scope") == scope]
    if not layered:
        rows = [r for r in rows if r.get("entity_scope") == "entity"]
    return rows


# ─── ELIGIBILITY (harus SEBELUM route /{policy_id}) ─────────────────────────

@router.get("/sales-return-policies/eligibility")
async def sales_return_eligibility(
    request: Request,
    order_id: str = Query(...),
    return_type: str = Query(""),
) -> Dict[str, Any]:
    """Evaluasi kelayakan & deadline retur jual untuk sebuah order (R0)."""
    await require_permission(request, "sales_return", "view")
    ctx = await entity_ctx(request)
    order = await db.sales_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    # Isolasi entitas: order harus dalam cakupan pengguna.
    ent = order.get("entity_id")
    if ent and ent not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan untuk entitas ini")
    return await rps.check_sales_return_eligibility(order, return_type=return_type)


# ─── CREATE ──────────────────────────────────────────────────────────────────

@router.post("/sales-return-policies")
async def create_sales_return_policy(payload: SalesReturnPolicyCreate,
                                     request: Request) -> Dict[str, Any]:
    """Buat kebijakan retur jual baru."""
    actor = await require_permission(request, "settings", "manage")
    ctx = await entity_ctx(request)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Nama kebijakan wajib diisi")
    scope = (payload.scope or "global").strip().lower()
    if scope not in VALID_SCOPES:
        raise HTTPException(status_code=400, detail=f"Scope tidak valid: {scope}")
    if scope in ("category", "customer") and not (payload.scope_ref or "").strip():
        raise HTTPException(status_code=400,
                            detail="scope_ref wajib diisi untuk scope kategori/customer")

    types = [t for t in (payload.allowed_return_types or []) if t in SALES_RETURN_TYPES] \
        or list(SALES_RETURN_TYPES)
    outcomes = [o for o in (payload.allowed_outcomes or []) if o in SALES_RETURN_OUTCOMES] \
        or list(SALES_RETURN_OUTCOMES)

    doc = {
        "id": new_id("srp"),
        "name": payload.name.strip(),
        "scope": scope,
        "scope_ref": (payload.scope_ref or "").strip(),
        "window_days": int(payload.window_days or 0),
        "allowed_return_types": types,
        "allowed_outcomes": outcomes,
        "restocking_fee_pct": round(float(payload.restocking_fee_pct or 0), 2),
        "require_inspection": bool(payload.require_inspection),
        "enforce_window": bool(payload.enforce_window),
        "link_to_supplier_window": bool(payload.link_to_supplier_window),
        "condition_requirements": payload.condition_requirements or "",
        "custom_fields": payload.custom_fields if isinstance(payload.custom_fields, dict) else {},
        "valid_from": payload.valid_from or "",
        "valid_until": payload.valid_until or "",
        "entity_id": payload.entity_id or "",   # "" = berlaku semua entitas (global master)
        "notes": payload.notes or "",
        "status": "active",
        "created_by": payload.created_by or actor.get("name", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.sales_return_policies.insert_one(doc)
    await audit(actor.get("name", ""), "sales_return_policy_created", "sales_return_policy",
                doc["id"], {"name": doc["name"], "scope": scope})
    return safe_doc(doc)


# ─── DETAIL ──────────────────────────────────────────────────────────────────

@router.get("/sales-return-policies/{policy_id}")
async def get_sales_return_policy(policy_id: str, request: Request) -> Dict[str, Any]:
    # Sama seperti daftarnya: MEMBACA satu kebijakan cukup dengan izin retur.
    await require_any_permission(request, [("settings", "view"),
                                           ("sales_return", "view")])
    doc = await db.sales_return_policies.find_one({"id": policy_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Kebijakan tidak ditemukan")
    return doc


# ─── UPDATE ──────────────────────────────────────────────────────────────────

@router.patch("/sales-return-policies/{policy_id}")
async def update_sales_return_policy(policy_id: str, payload: GenericPatch,
                                     request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "settings", "manage")
    existing = await db.sales_return_policies.find_one({"id": policy_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kebijakan tidak ditemukan")
    allowed = {"name", "scope", "scope_ref", "window_days", "allowed_return_types",
               "allowed_outcomes", "restocking_fee_pct", "require_inspection",
               "enforce_window", "link_to_supplier_window", "condition_requirements",
               "custom_fields", "valid_from", "valid_until", "entity_id", "notes", "status"}
    updates = {k: v for k, v in (payload.data or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field valid untuk diupdate")
    # Normalisasi & validasi numerik/enum
    if "scope" in updates:
        sc = str(updates["scope"] or "global").strip().lower()
        if sc not in VALID_SCOPES:
            raise HTTPException(status_code=400, detail=f"Scope tidak valid: {sc}")
        updates["scope"] = sc
    if "window_days" in updates:
        try:
            wd = int(updates["window_days"] or 0)
        except (ValueError, TypeError):
            wd = 0
        updates["window_days"] = max(0, min(wd, 3650))
    if "restocking_fee_pct" in updates:
        try:
            fee = float(updates["restocking_fee_pct"] or 0)
        except (ValueError, TypeError):
            fee = 0.0
        updates["restocking_fee_pct"] = round(max(0.0, min(fee, 100.0)), 2)
    if "allowed_return_types" in updates:
        updates["allowed_return_types"] = [t for t in (updates["allowed_return_types"] or [])
                                           if t in SALES_RETURN_TYPES] or list(SALES_RETURN_TYPES)
    if "allowed_outcomes" in updates:
        updates["allowed_outcomes"] = [o for o in (updates["allowed_outcomes"] or [])
                                       if o in SALES_RETURN_OUTCOMES] or list(SALES_RETURN_OUTCOMES)
    for b in ("require_inspection", "enforce_window", "link_to_supplier_window"):
        if b in updates:
            updates[b] = bool(updates[b])
    if "custom_fields" in updates and not isinstance(updates["custom_fields"], dict):
        updates["custom_fields"] = {}
    updates["updated_at"] = now_iso()
    updated = await db.sales_return_policies.find_one_and_update(
        {"id": policy_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor.get("name", ""), "sales_return_policy_updated", "sales_return_policy",
                policy_id, updates)
    return safe_doc(updated)


# ─── DELETE (soft) ───────────────────────────────────────────────────────────

@router.delete("/sales-return-policies/{policy_id}")
async def deactivate_sales_return_policy(policy_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "settings", "manage")
    existing = await db.sales_return_policies.find_one({"id": policy_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kebijakan tidak ditemukan")
    updated = await db.sales_return_policies.find_one_and_update(
        {"id": policy_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor.get("name", ""), "sales_return_policy_deactivated", "sales_return_policy",
                policy_id, {})
    return safe_doc(updated)
