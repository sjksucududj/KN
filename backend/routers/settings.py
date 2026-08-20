"""Settings router (Fase 1A) — Configuration Foundation.

Mengelola pengaturan global/per-entitas, term pembayaran, dan matriks approval —
semua CONFIGURABLE (tidak hardcode). Konsumsi engine ada di services/config_service.py.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from db import db
from dependencies import require_permission, current_user, audit
from core_utils import new_id, now_iso, safe_doc
from schemas import SettingsUpdate, PaymentTermPayload, GenericPatch
from entity_scope import entity_ctx, resolve_requested_entity
from services.config_service import (
    get_global_settings, get_effective_settings, compute_tax, evaluate_approval, GLOBAL_SCOPE,
)

router = APIRouter(prefix="/api")
SETTINGS_SECTIONS = ["tax", "finance", "sales", "inventory", "allocation", "purchasing", "commission"]


# ── Settings (global + per-entity override) ─────────────────────────────────

@router.get("/settings")
async def read_settings(request: Request) -> Dict[str, Any]:
    await current_user(request)
    return await get_global_settings()


@router.get("/settings/effective")
async def read_effective_settings(request: Request, entity_id: Optional[str] = None) -> Dict[str, Any]:
    """Pengaturan EFEKTIF (global ← override entitas).

    FASE E-0 (L10) — dulu endpoint ini hanya membaca query `?entity_id=`, sehingga
    header `X-Entity-Id: ent_kanda` diabaikan dan CV Kanda (non-PKP) tetap menerima
    PPN 12% & `is_pkp=true`. Sekarang entitas diambil dari konteks bila param kosong.
    """
    ctx = await entity_ctx(request)
    resolved = resolve_requested_entity(ctx, entity_id) if entity_id else (
        None if ctx.view_all else ctx.active_entity_id)
    return await get_effective_settings(resolved)


@router.put("/settings")
async def update_settings(payload: SettingsUpdate, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "entity", "update")
    scope = payload.scope or GLOBAL_SCOPE
    data: Dict[str, Any] = {"updated_at": now_iso()}
    for sec in SETTINGS_SECTIONS:
        val = getattr(payload, sec, None)
        if val is not None:
            data[sec] = val
    existing = await db.system_settings.find_one({"scope": scope}, {"_id": 0})
    if existing:
        updated = await db.system_settings.find_one_and_update(
            {"scope": scope}, {"$set": data},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER,
        )
    else:
        doc = {"id": new_id("set"), "scope": scope, "created_at": now_iso(), **data}
        await db.system_settings.insert_one(doc)
        updated = safe_doc(doc)
    await audit(actor["name"], "settings_updated", "system_settings", scope, data)
    return updated


# ── Tax & Approval helper endpoints (dipakai FE Sales nanti) ─────────────────

@router.get("/settings/compute-tax")
async def compute_tax_endpoint(request: Request, subtotal: float, entity_id: Optional[str] = None) -> Dict[str, Any]:
    ctx = await entity_ctx(request)
    resolved = resolve_requested_entity(ctx, entity_id) if entity_id else ctx.active_entity_id
    return await compute_tax(subtotal, resolved)


@router.get("/settings/evaluate-approval")
async def evaluate_approval_endpoint(request: Request, doc_type: str, amount: float,
                                     entity_id: Optional[str] = None) -> Dict[str, Any]:
    ctx = await entity_ctx(request)
    resolved = resolve_requested_entity(ctx, entity_id) if entity_id else ctx.active_entity_id
    return await evaluate_approval(doc_type, amount, resolved)


# ── Payment Terms CRUD ───────────────────────────────────────────────────────

@router.get("/payment-terms")
async def list_payment_terms(request: Request,
                             layered: bool = False) -> List[Dict[str, Any]]:
    """Syarat pembayaran yang BERLAKU untuk badan usaha aktif (FASE E-4 · E4.3).

    Bawaan: baris EFEKTIF — override badan usaha menutupi baris global ber-kode sama,
    sehingga dropdown pesanan/POS tidak pernah menampilkan "NET30" dua kali.
    `layered=true` memperlihatkan kedua lapisan + lencana asalnya (dipakai layar
    Master per Badan Usaha).
    """
    await current_user(request)
    from services import entity_master_service as ems
    ctx = await entity_ctx(request)
    if layered:
        return (await ems.list_layered("payment-terms", ctx))["rows"]
    return await ems.effective_rows("payment-terms", ctx.active_entity_id)


@router.post("/payment-terms")
async def create_payment_term(payload: PaymentTermPayload, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "entity", "create")
    from services import entity_master_service as ems
    ctx = await entity_ctx(request)
    # Keunikan kode diperiksa PER LAPISAN: "NET30" global dan "NET30" khusus Kanda
    # adalah dua baris yang sah — yang kedua justru menimpa yang pertama.
    row = await ems.create("payment-terms", payload.model_dump(), ctx)
    await audit(actor["name"], "payment_term_created", "payment_terms", row["id"], row)
    return row


@router.patch("/payment-terms/{term_id}")
async def update_payment_term(term_id: str, payload: GenericPatch, request: Request) -> Dict[str, Any]:
    actor = await require_permission(request, "entity", "update")
    from services import entity_master_service as ems
    ctx = await entity_ctx(request)
    # Baris GLOBAL tidak boleh diubah dari konteks satu badan usaha (lihat
    # services/entity_master_service.py) — server menjawab 409 dengan kalimat menuntun.
    row = await ems.patch("payment-terms", term_id, dict(payload.data), ctx)
    await audit(actor["name"], "payment_term_updated", "payment_terms", term_id,
                dict(payload.data))
    return row


@router.post("/payment-terms/{term_id}/override")
async def override_payment_term(term_id: str, request: Request) -> Dict[str, Any]:
    """Buat salinan syarat bayar ini khusus badan usaha aktif (FASE E-4 · E4.3)."""
    actor = await require_permission(request, "entity", "create")
    from services import entity_master_service as ems
    ctx = await entity_ctx(request)
    row = await ems.override("payment-terms", term_id, ctx)
    await audit(actor["name"], "payment_term_overridden", "payment_terms", row["id"],
                {"source_id": term_id, "entity_id": row.get("entity_id")})
    return row


@router.delete("/payment-terms/{term_id}")
async def delete_payment_term(term_id: str, request: Request) -> Dict[str, Any]:
    """Nonaktifkan syarat bayar. Baris khusus badan usaha dilepas total (kembali global)."""
    actor = await require_permission(request, "entity", "delete")
    from services import entity_master_service as ems
    ctx = await entity_ctx(request)
    doc = await db.payment_terms.find_one({"id": term_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Term tidak ditemukan")
    if not ems.is_global(doc):
        res = await ems.revert("payment-terms", term_id, ctx)
        await audit(actor["name"], "payment_term_reverted", "payment_terms", term_id, res)
        return res
    updated = await db.payment_terms.find_one_and_update(
        {"id": term_id}, {"$set": {"active": False, "updated_at": now_iso()}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    await audit(actor["name"], "payment_term_deactivated", "payment_terms", term_id, {})
    return updated

# NOTE: Approval Rules CRUD telah dipindah ke routers/approval_rules.py
# Jangan duplikasi di sini — RC-11 (service contract drift + G2 duplicate route)
