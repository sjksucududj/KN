"""Cycle count / stock opname router."""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from db import db
from dependencies import require_permission, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID
from entity_scope import entity_ctx
from services import warehouse_scope_service as whscope
from services.roll_service import resolve_stock_owner, apply_cycle_count_adjustment

router = APIRouter(prefix="/api")


class CycleCountSessionCreate(BaseModel):
    warehouse_id: str
    name: str = ""
    notes: str = ""


class CycleCountItemCreate(BaseModel):
    product_id: str
    bin_id: str = ""
    notes: str = ""
    owner_entity_id: str = ""  # opsional: entitas pemilik stok (auto-resolve bila kosong)


class CycleCountItemUpdate(BaseModel):
    actual_qty: float
    notes: str = ""


class CycleCountApprove(BaseModel):
    reason: str = "Disetujui sesuai hasil cycle count"


class CycleCountReject(BaseModel):
    reason: str


@router.post("/cycle-count/sessions")
async def create_session(payload: CycleCountSessionCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "cycle_count")
    ctx = await entity_ctx(request)
    # E4.1 — stock opname di gudang khusus badan usaha lain = menghitung barang orang.
    warehouse = await whscope.assert_usable(payload.warehouse_id, ctx.active_entity_id,
                                           action="melakukan stock opname di sini")
    from datetime import datetime, timezone
    session = {
        "id": new_id("cc"),
        "warehouse_id": payload.warehouse_id,
        "warehouse_name": warehouse["name"],
        "warehouse_city": warehouse.get("city", ""),
        "name": payload.name or f"Count {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}",
        "notes": payload.notes,
        "status": "open",
        "items": [],
        "created_by": actor["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.cycle_count_sessions.insert_one(session)
    await audit(actor["name"], "cycle_count_created", "cycle_count", session["id"], session)
    return safe_doc(session)


@router.get("/cycle-count/sessions")
async def list_sessions(request: Request) -> List[Dict[str, Any]]:
    await require_permission(request, "inventory", "cycle_count")
    sessions = await db.cycle_count_sessions.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [safe_doc(s) for s in sessions if s]


@router.get("/cycle-count/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> Dict[str, Any]:
    await require_permission(request, "inventory", "cycle_count")
    session = safe_doc(await db.cycle_count_sessions.find_one({"id": session_id}, {"_id": 0}))
    if not session:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan")
    return session


@router.post("/cycle-count/sessions/{session_id}/items")
async def add_item(session_id: str, payload: CycleCountItemCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "cycle_count")
    session = safe_doc(await db.cycle_count_sessions.find_one({"id": session_id}, {"_id": 0}))
    if not session or session["status"] != "open":
        raise HTTPException(status_code=400, detail="Session tidak ditemukan atau tidak open")
    product = safe_doc(await db.products.find_one({"id": payload.product_id}, {"_id": 0}))
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    # Owner-aware (KN_15 §9): expected dari segmen (product × warehouse × owner).
    ctx = await entity_ctx(request)
    prefer = payload.owner_entity_id or ("" if getattr(ctx, "view_all", False) else (ctx.active_entity_id or ""))
    owner = await resolve_stock_owner(payload.product_id, session["warehouse_id"], prefer)
    balance = safe_doc(await db.inventory_balances.find_one(
        {"product_id": payload.product_id, "warehouse_id": session["warehouse_id"],
         "owner_entity_id": owner}, {"_id": 0}
    ))
    item = {
        "id": new_id("cci"),
        "product_id": payload.product_id,
        "sku": product["sku"],
        "product_name": product["name"],
        "bin_id": payload.bin_id,
        "owner_entity_id": owner,
        "expected_qty": float(balance.get("on_hand_qty", 0)) if balance else 0.0,
        "actual_qty": None,
        "status": "pending",
        "notes": payload.notes,
        "created_at": now_iso(),
    }
    await db.cycle_count_sessions.update_one(
        {"id": session_id},
        {"$push": {"items": item}, "$set": {"updated_at": now_iso()}}
    )
    return item


@router.patch("/cycle-count/sessions/{session_id}/items/{item_id}")
async def update_item(
    session_id: str, item_id: str, payload: CycleCountItemUpdate, request: Request
) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "cycle_count")
    session = safe_doc(await db.cycle_count_sessions.find_one({"id": session_id}, {"_id": 0}))
    if not session or session["status"] != "open":
        raise HTTPException(status_code=400, detail="Session tidak ditemukan atau tidak open")
    await db.cycle_count_sessions.update_one(
        {"id": session_id, "items.id": item_id},
        {"$set": {
            "items.$.actual_qty": payload.actual_qty,
            "items.$.notes": payload.notes,
            "items.$.status": "counted",
            "items.$.counted_at": now_iso(),
            "items.$.counted_by": actor["name"],
            "updated_at": now_iso(),
        }}
    )
    session = safe_doc(await db.cycle_count_sessions.find_one({"id": session_id}, {"_id": 0}))
    return session


@router.post("/cycle-count/sessions/{session_id}/submit")
async def submit_session(session_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "cycle_count")
    session = safe_doc(await db.cycle_count_sessions.find_one({"id": session_id}, {"_id": 0}))
    if not session or session["status"] != "open":
        raise HTTPException(status_code=400, detail="Session tidak ditemukan atau tidak open")
    uncounted = [item for item in session.get("items", []) if item.get("status") != "counted"]
    if uncounted:
        raise HTTPException(status_code=400, detail=f"{len(uncounted)} item belum dihitung")
    discrepancies = []
    for item in session.get("items", []):
        diff = float(item.get("actual_qty", 0) or 0) - float(item.get("expected_qty", 0) or 0)
        if abs(diff) > 0.001:
            discrepancies.append({
                "item_id": item["id"],
                "product_id": item["product_id"],
                "sku": item.get("sku", ""),
                "product_name": item.get("product_name", ""),
                "owner_entity_id": item.get("owner_entity_id", DEFAULT_ENTITY_ID),
                "expected_qty": item.get("expected_qty", 0),
                "actual_qty": item.get("actual_qty", 0),
                "difference": round(diff, 4),
            })
    from pymongo import ReturnDocument
    updated = await db.cycle_count_sessions.find_one_and_update(
        {"id": session_id},
        {"$set": {
            "status": "submitted",
            "discrepancies": discrepancies,
            "submitted_by": actor["name"],
            "submitted_at": now_iso(),
            "updated_at": now_iso(),
        }},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    await audit(actor["name"], "cycle_count_submitted", "cycle_count", session_id,
                {"discrepancies_count": len(discrepancies)})
    return safe_doc(updated)


@router.post("/cycle-count/sessions/{session_id}/approve")
async def approve_session(session_id: str, payload: CycleCountApprove, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "approve_count")
    session = safe_doc(await db.cycle_count_sessions.find_one({"id": session_id}, {"_id": 0}))
    if not session or session["status"] != "submitted":
        raise HTTPException(status_code=400, detail="Session belum disubmit")
    for discrepancy in session.get("discrepancies", []):
        diff = float(discrepancy["difference"])
        if abs(diff) < 0.001:
            continue
        # Roll-as-SSOT (KN_15 §9): terapkan selisih ke ROLLS (owner-aware) + rebuild balance.
        # TIDAK $inc balance (agar tak drift & tak dilanggar oleh rebuild berikutnya).
        owner = discrepancy.get("owner_entity_id") or DEFAULT_ENTITY_ID
        await apply_cycle_count_adjustment(
            discrepancy["product_id"], session["warehouse_id"], owner, diff, session_id,
            created_by=actor["name"],
        )
    from pymongo import ReturnDocument
    updated = await db.cycle_count_sessions.find_one_and_update(
        {"id": session_id},
        {"$set": {
            "status": "approved",
            "approved_by": actor["name"],
            "approved_at": now_iso(),
            "approval_reason": payload.reason,
            "updated_at": now_iso(),
        }},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    await audit(actor["name"], "cycle_count_approved", "cycle_count", session_id, {"reason": payload.reason})
    return safe_doc(updated)


@router.post("/cycle-count/sessions/{session_id}/reject")
async def reject_session(session_id: str, payload: CycleCountReject, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "inventory", "approve_count")
    session = safe_doc(await db.cycle_count_sessions.find_one({"id": session_id}, {"_id": 0}))
    if not session or session["status"] != "submitted":
        raise HTTPException(status_code=400, detail="Session belum disubmit")
    from pymongo import ReturnDocument
    updated = await db.cycle_count_sessions.find_one_and_update(
        {"id": session_id},
        {"$set": {
            "status": "rejected",
            "rejected_by": actor["name"],
            "rejected_at": now_iso(),
            "rejection_reason": payload.reason,
            "updated_at": now_iso(),
        }},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER
    )
    await audit(actor["name"], "cycle_count_rejected", "cycle_count", session_id, {"reason": payload.reason})
    return safe_doc(updated)
