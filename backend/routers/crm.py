"""CRM / Sales Force router (KN_17 CRM-lite).

Customer 360, reassign, credit override, collection worklist/followups,
sales KPI/leaderboard/commission, sales targets & incentive schemes.
All derived data via services. Row-level scoping enforced (sales -> own customers).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request, Query
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, require_role, current_user, audit
from core_utils import new_id, now_iso, safe_doc, DEFAULT_ENTITY_ID
from schemas import (
    CustomerReassign, SalesTargetCreate, SalesIncentiveCreate,
    CreditOverrideCreate, CreditOverrideDecision, CollectionFollowupCreate,
)
from services.customer_service import (
    customer_360, compute_customer_credit, can_access_customer, collection_worklist,
    evaluate_credit_gate, collection_reminders,
)
from services.sales_force_service import sales_kpi, compute_commission, leaderboard, commission_history
from services import gl_service
from entity_scope import entity_ctx, resolve_list_scope

router = APIRouter(prefix="/api")


# ── Sales users (untuk dropdown assignment) ──────────────────────────────────
@router.get("/sales-users")
async def list_sales_users(request: Request, entity_id: str = None) -> List[Dict[str, Any]]:
    """Daftar sales untuk dropdown penugasan.

    FASE E-8 (E8.5) — IKUT BADAN USAHA. Sebelum ini endpoint mengembalikan SELURUH
    sales seluruh grup, sehingga dropdown "Sales penanggung jawab" di CV Kanda Suka
    menawarkan sales PT Kain Suka Cita — dan target/insentif bisa tertempel pada orang
    dari buku yang salah. Penyaringan memakai `allowed_entity_ids` (mekanisme penugasan
    yang sudah ada) supaya sales ber-penugasan 2 badan usaha tetap muncul di keduanya.
    """
    await current_user(request)
    ctx = await entity_ctx(request)
    ids = ([entity_id] if entity_id and entity_id != "all"
           else list(ctx.allowed_entity_ids) if (entity_id == "all"
                                                 or getattr(ctx, "view_all", False))
           else [ctx.active_entity_id])
    ids = [i for i in ids if i in ctx.allowed_entity_ids] or list(ctx.allowed_entity_ids)
    rows = await db.users.find(
        {"role": "sales", "status": "active",
         "$or": [{"allowed_entity_ids": {"$in": ids}},
                 {"home_entity_id": {"$in": ids}},
                 {"entity_id": {"$in": ids}}]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "home_entity_id": 1}
    ).sort("name", 1).to_list(100)
    return [safe_doc(r) for r in rows]


# ── Customer 360 ─────────────────────────────────────────────────────────────
@router.get("/customers/{customer_id}/360")
async def get_customer_360(customer_id: str, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "customer", "view")
    data = await customer_360(customer_id)
    if not data:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    if not await can_access_customer(actor, data):
        raise HTTPException(status_code=403, detail="Customer ini bukan milik Anda")
    return data


# ── Reassign salesperson (Manager/Admin, teraudit) ───────────────────────────
@router.post("/customers/{customer_id}/reassign")
async def reassign_customer(customer_id: str, payload: CustomerReassign, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["manager"])
    sales = await db.users.find_one({"id": payload.assigned_sales_id, "role": "sales", "status": "active"}, {"_id": 0})
    if not sales:
        raise HTTPException(status_code=400, detail="Salesperson tujuan tidak valid")
    before = safe_doc(await db.customers.find_one({"id": customer_id}, {"_id": 0, "assigned_sales_id": 1}))
    if not before:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    updated = await db.customers.find_one_and_update(
        {"id": customer_id},
        {"$set": {"assigned_sales_id": sales["id"], "assigned_sales_name": sales["name"],
                  "sales_pic": sales["name"], "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    await audit(actor["name"], "customer_reassigned", "customer", customer_id,
                {"from": before.get("assigned_sales_id"), "to": sales["id"], "reason": payload.reason})
    return safe_doc(updated)


# ── Credit override (KN_17 5.2 / S37) ────────────────────────────────────────
@router.post("/customers/{customer_id}/credit-override")
async def request_credit_override(customer_id: str, payload: CreditOverrideCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "create")
    customer = safe_doc(await db.customers.find_one({"id": customer_id}, {"_id": 0}))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    if not await can_access_customer(actor, customer):
        raise HTTPException(status_code=403, detail="Customer ini bukan milik Anda")
    credit = await compute_customer_credit(customer)
    doc = {
        "id": new_id("cro"),
        "customer_id": customer_id,
        "customer_name": customer.get("name", ""),
        "order_id": payload.order_id,
        "amount": float(payload.amount or 0),
        "reason": payload.reason,
        "evidence_url": payload.evidence_url,
        "credit_snapshot": credit,
        "entity_id": customer.get("entity_id", DEFAULT_ENTITY_ID),
        "status": "pending",
        "requested_by": actor["name"],
        "requested_by_id": actor["id"],
        "created_at": now_iso(),
    }
    await db.credit_overrides.insert_one(dict(doc))
    await audit(actor["name"], "credit_override_requested", "credit_override", doc["id"], doc)
    return safe_doc(doc)


@router.get("/credit-overrides")
async def list_credit_overrides(request: Request, status: str = None) -> List[Dict[str, Any]]:
    actor = await require_permission(request, "customer", "view")
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    if actor.get("role") == "sales":
        query["requested_by_id"] = actor["id"]
    return await db.credit_overrides.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/credit-overrides/{override_id}/decision")
async def decide_credit_override(override_id: str, payload: CreditOverrideDecision, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["manager"])
    if payload.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision harus approve|reject")
    new_status = "approved" if payload.decision == "approve" else "rejected"
    updated = await db.credit_overrides.find_one_and_update(
        {"id": override_id, "status": "pending"},
        {"$set": {"status": new_status, "decided_by": actor["name"], "decided_by_id": actor["id"],
                  "decision_reason": payload.reason, "decided_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Permohonan tidak ditemukan / sudah diputuskan")
    await audit(actor["name"], f"credit_override_{new_status}", "credit_override", override_id,
                {"reason": payload.reason})
    return safe_doc(updated)


# ── Collection worklist + follow-up (KN_17 7 / S39) ──────────────────────────
@router.get("/collection-worklist")
async def get_collection_worklist(request: Request, sales_id: str = None, entity_id: str = None) -> List[Dict[str, Any]]:
    actor = await require_permission(request, "order", "view")
    return await collection_worklist(actor, sales_id=sales_id, entity_id=entity_id)


@router.get("/customers/{customer_id}/credit-status")
async def get_credit_status(customer_id: str, request: Request, amount: float = 0) -> Dict[str, Any]:
    """Preview gate kredit (tanpa konsumsi override) untuk UI buat SO."""
    actor = await require_permission(request, "order", "view")
    customer = safe_doc(await db.customers.find_one({"id": customer_id}, {"_id": 0}))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    # INV-ENTITY-01 (KN-079-IDOR-CREDIT-STATUS P1): konsisten dgn /360 — cegah bocor kredit/AR lintas-PT.
    if not await can_access_customer(actor, customer):
        raise HTTPException(status_code=403, detail="Customer ini bukan milik Anda")
    gate = await evaluate_credit_gate(customer, float(amount or 0))
    return {
        "level": gate["level"], "blocked": gate["blocked"],
        "allowed_after_override": gate["allowed_after_override"],
        "reasons": gate["reasons"], "credit": gate["credit"], "projected_ar": gate["projected_ar"],
        "has_approved_override": bool(gate["override"]),
    }


# ── Collection reminders (KN_17 §7 / 4b) ─────────────────────────────────────
@router.get("/collection-reminders")
async def get_collection_reminders(request: Request, days_ahead: int = 7, sales_id: str = None, entity_id: str = None) -> List[Dict[str, Any]]:
    actor = await require_permission(request, "order", "view")
    return await collection_reminders(actor, days_ahead=days_ahead, sales_id=sales_id, entity_id=entity_id)


@router.post("/collection-reminders/mark")
async def mark_reminder(payload: CollectionFollowupCreate, request: Request) -> Dict[str, Any]:
    """Tandai 'sudah diingatkan' (mencatat follow-up outcome=reminded)."""
    actor = await require_permission(request, "order", "update")
    customer = safe_doc(await db.customers.find_one({"id": payload.customer_id}, {"_id": 0}))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    if not await can_access_customer(actor, customer):
        raise HTTPException(status_code=403, detail="Customer ini bukan milik Anda")
    doc = {
        "id": new_id("cfu"), "customer_id": payload.customer_id, "customer_name": customer.get("name", ""),
        "order_id": payload.order_id, "note": payload.note or "Pengingat penagihan dikirim",
        "outcome": "reminded", "next_action_date": payload.next_action_date,
        "entity_id": customer.get("entity_id", DEFAULT_ENTITY_ID),
        "created_by": actor["name"], "created_by_id": actor["id"], "created_at": now_iso(),
    }
    await db.collection_followups.insert_one(dict(doc))
    await audit(actor["name"], "collection_reminded", "collection_followup", doc["id"], doc)
    return safe_doc(doc)


@router.post("/customers/{customer_id}/followups")
async def add_followup(customer_id: str, payload: CollectionFollowupCreate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "order", "update")
    customer = safe_doc(await db.customers.find_one({"id": customer_id}, {"_id": 0}))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer tidak ditemukan")
    if not await can_access_customer(actor, customer):
        raise HTTPException(status_code=403, detail="Customer ini bukan milik Anda")
    doc = {
        "id": new_id("cfu"),
        "customer_id": customer_id,
        "customer_name": customer.get("name", ""),
        "order_id": payload.order_id,
        "note": payload.note,
        "outcome": payload.outcome,
        "next_action_date": payload.next_action_date,
        "entity_id": customer.get("entity_id", DEFAULT_ENTITY_ID),
        "created_by": actor["name"],
        "created_by_id": actor["id"],
        "created_at": now_iso(),
    }
    await db.collection_followups.insert_one(dict(doc))
    await audit(actor["name"], "collection_followup_added", "collection_followup", doc["id"], doc)
    return safe_doc(doc)


# ── Sales KPI / leaderboard / commission ─────────────────────────────────────
@router.get("/sales/kpi")
async def get_sales_kpi(request: Request, sales_id: str = None, period: str = None, entity_id: str = None) -> Dict[str, Any]:
    actor = await current_user(request)
    if actor.get("role") == "sales":
        sales_id = actor["id"]  # sales hanya boleh lihat dirinya
    if not sales_id:
        sales_id = actor["id"]
    return await sales_kpi(sales_id, period=period, entity_id=entity_id)


@router.get("/sales/leaderboard")
async def get_leaderboard(request: Request, period: str = None, entity_id: str = None) -> List[Dict[str, Any]]:
    await require_role(request, ["manager"])
    return await leaderboard(period=period, entity_id=entity_id)


@router.get("/sales/commission")
async def get_commission(request: Request, sales_id: str = None, period: str = Query(...), entity_id: str = None) -> Dict[str, Any]:
    actor = await current_user(request)
    if actor.get("role") == "sales":
        sales_id = actor["id"]
    if not sales_id:
        sales_id = actor["id"]
    return await compute_commission(sales_id, period, entity_id=entity_id)


@router.get("/sales/commission-history")
async def get_commission_history(request: Request, sales_id: str = None, period_type: str = "month",
                                 anchor: str = None, count: int = 6, entity_id: str = None) -> List[Dict[str, Any]]:
    actor = await current_user(request)
    if actor.get("role") == "sales":
        sales_id = actor["id"]
    if not sales_id:
        sales_id = actor["id"]
    count = max(1, min(int(count or 6), 12))
    return await commission_history(sales_id, period_type=period_type, anchor=anchor, count=count, entity_id=entity_id)


# ── Insentif → GL (F0-E: akrual beban insentif per-entitas, Model 1) ─────────
@router.get("/sales/incentive/gl-status")
async def get_incentive_gl_status(request: Request, period: str = Query(...),
                                  entity_id: str = None) -> Dict[str, Any]:
    """Status akrual insentif untuk (entitas aktif|param, periode)."""
    await require_role(request, ["manager"])
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id
    if eid == "all" or eid not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=400, detail="Pilih entitas spesifik untuk status akrual insentif.")
    return await gl_service.incentive_accrual_status(eid, period)


@router.post("/sales/incentive/post-gl")
async def post_incentive_gl(request: Request, period: str = Query(...),
                            entity_id: str = None) -> Dict[str, Any]:
    """Posting akrual beban insentif penjualan (entitas, periode) ke buku GL entitas.

    Dr Beban Insentif Penjualan / Cr Hutang Insentif Penjualan. Idempotent.
    """
    actor = await require_role(request, ["manager"])
    ctx = await entity_ctx(request)
    eid = entity_id or ctx.active_entity_id
    if eid == "all" or eid not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=400, detail="Pilih entitas spesifik (bukan 'Semua') untuk posting insentif ke GL.")
    try:
        entry = await gl_service.post_incentive_accrual(eid, period, created_by=actor.get("name", "system"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    status = await gl_service.incentive_accrual_status(eid, period)
    if entry:
        await audit(actor["name"], "incentive_accrual", "journal_entry",
                    status.get("journal_id", ""), status,
                    f"Insentif {period} entitas {eid} = {status.get('amount')}")
        return {"created": True, "message": f"Akrual insentif {period} diposting (JE {status.get('journal_number')}).", **status}
    # Sudah pernah diposting (idempotent) atau total 0
    if status.get("posted"):
        return {"created": False, "message": "Akrual insentif periode ini sudah pernah diposting.", **status}
    return {"created": False, "message": "Tidak ada insentif untuk diposting pada periode ini (total 0).", **status}


# ── Sales targets ────────────────────────────────────────────────────────────
@router.get("/sales-targets")
async def list_targets(request: Request, sales_id: str = None, period: str = None,
                       entity_id: str = None) -> List[Dict[str, Any]]:
    """FASE E-0 (L5) — target sales WAJIB ter-scope entitas: dulu target lintas-entitas
    terlihat karena penyaringan hanya per `sales_id`."""
    actor = await current_user(request)
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if actor.get("role") == "sales":
        query["sales_id"] = actor["id"]
    elif sales_id:
        query["sales_id"] = sales_id
    if period:
        query["period"] = period
    query = resolve_list_scope("sales_targets", query, ctx, entity_id)
    return await db.sales_targets.find(query, {"_id": 0}).sort("period", -1).to_list(200)


@router.post("/sales-targets")
async def create_target(payload: SalesTargetCreate, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["manager"])
    ctx = await entity_ctx(request)
    sales = await db.users.find_one({"id": payload.sales_id, "role": "sales"},
                                    {"_id": 0, "name": 1, "home_entity_id": 1})
    if not sales:
        raise HTTPException(status_code=400, detail="Salesperson tidak valid")
    doc = {
        "id": new_id("starg"),
        "sales_id": payload.sales_id,
        "sales_name": sales.get("name", ""),
        # FASE E-0 (L12) — entitas target = entitas HOME salesnya (bukan DEFAULT global).
        "entity_id": (sales.get("home_entity_id") or payload.entity_id
                      or ctx.active_entity_id or DEFAULT_ENTITY_ID),
        "period_type": payload.period_type,
        "period": payload.period,
        "target_sales_amount": float(payload.target_sales_amount or 0),
        "target_collection_amount": float(payload.target_collection_amount or 0),
        "target_new_customers": int(payload.target_new_customers or 0),
        "target_focus_products": payload.target_focus_products,
        "notes": payload.notes,
        "created_by": actor["name"],
        "created_at": now_iso(),
    }
    # upsert by sales_id + period (1 target per periode)
    await db.sales_targets.update_one(
        {"sales_id": payload.sales_id, "period": payload.period},
        {"$set": {k: v for k, v in doc.items() if k != "id"},
         "$setOnInsert": {"id": doc["id"]}},
        upsert=True,
    )
    saved = safe_doc(await db.sales_targets.find_one({"sales_id": payload.sales_id, "period": payload.period}, {"_id": 0}))
    await audit(actor["name"], "sales_target_set", "sales_target", saved["id"], saved)
    return saved


# ── Sales incentive schemes ──────────────────────────────────────────────────
@router.get("/sales-incentives")
async def list_incentives(request: Request, sales_id: str = None, period: str = None,
                          entity_id: str = None) -> List[Dict[str, Any]]:
    """FASE E-0 (L6) — insentif sales WAJIB ter-scope entitas (insentif = beban entitas)."""
    actor = await current_user(request)
    ctx = await entity_ctx(request)
    query: Dict[str, Any] = {}
    if actor.get("role") == "sales":
        query["sales_id"] = actor["id"]
    elif sales_id:
        query["sales_id"] = sales_id
    if period:
        query["period"] = period
    query = resolve_list_scope("sales_incentives", query, ctx, entity_id)
    return await db.sales_incentives.find(query, {"_id": 0}).sort("period", -1).to_list(200)


@router.post("/sales-incentives")
async def create_incentive(payload: SalesIncentiveCreate, request: Request) -> Dict[str, Any]:
    actor = await require_role(request, ["manager"])
    ctx = await entity_ctx(request)
    sales = await db.users.find_one({"id": payload.sales_id, "role": "sales"},
                                    {"_id": 0, "name": 1, "home_entity_id": 1})
    if not sales:
        raise HTTPException(status_code=400, detail="Salesperson tidak valid")
    doc = {
        "id": new_id("sinc"),
        "sales_id": payload.sales_id,
        "sales_name": sales.get("name", ""),
        # FASE E-0 (L12) — entitas insentif = entitas HOME salesnya.
        "entity_id": (sales.get("home_entity_id") or payload.entity_id
                      or ctx.active_entity_id or DEFAULT_ENTITY_ID),
        "period": payload.period,
        "basis": payload.basis,
        "tiers": [t.model_dump() for t in payload.tiers],
        "bonus_new_customer": float(payload.bonus_new_customer or 0),
        "bonus_focus_product": float(payload.bonus_focus_product or 0),
        "notes": payload.notes,
        "status": "draft",
        "created_by": actor["name"],
        "created_at": now_iso(),
    }
    await db.sales_incentives.update_one(
        {"sales_id": payload.sales_id, "period": payload.period},
        {"$set": {k: v for k, v in doc.items() if k != "id"},
         "$setOnInsert": {"id": doc["id"]}},
        upsert=True,
    )
    saved = safe_doc(await db.sales_incentives.find_one({"sales_id": payload.sales_id, "period": payload.period}, {"_id": 0}))
    await audit(actor["name"], "sales_incentive_set", "sales_incentive", saved["id"], saved)
    return saved
