"""routers/deliveries.py — Pengiriman dokumen (WhatsApp, mode simulasi) + riwayat +
pengaturan integrasi WhatsApp.
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from dependencies import require_permission, audit
from services import delivery_service as ds

router = APIRouter(prefix="/api/deliveries", tags=["deliveries"])


class WASendBody(BaseModel):
    doc_type: str
    source_id: str
    entity_id: Optional[str] = None
    to: str
    caption: Optional[str] = ""
    message: Optional[str] = ""


class WASettingsBody(BaseModel):
    provider: Optional[str] = None
    simulate: Optional[bool] = None
    enabled: Optional[bool] = None
    phone_number_id: Optional[str] = None
    access_token: Optional[str] = None
    default_country_code: Optional[str] = None
    sender_label: Optional[str] = None


class WARuleBody(BaseModel):
    doc_type: Optional[str] = None
    event: Optional[str] = None
    recipient_mode: Optional[str] = None  # customer | supplier | fixed
    fixed_number: Optional[str] = None
    caption_template: Optional[str] = None
    enabled: Optional[bool] = None


@router.post("/whatsapp/send")
async def send_whatsapp(body: WASendBody, request: Request):
    user = await require_permission(request, "document_delivery", "send")
    actor = user.get("email") or user.get("name") or user.get("id")
    try:
        res = await ds.send_whatsapp(body.doc_type, body.source_id, body.entity_id,
                                     body.to, body.caption, body.message, actor)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await audit(actor, "delivery.whatsapp", body.doc_type, body.source_id, res, "")
    return res


@router.get("/whatsapp/settings")
async def get_wa_settings(request: Request):
    await require_permission(request, "document_delivery", "view")
    return await ds.get_settings()


@router.put("/whatsapp/settings")
async def put_wa_settings(body: WASettingsBody, request: Request):
    user = await require_permission(request, "document_delivery", "manage")
    actor = user.get("email") or user.get("name") or user.get("id")
    return await ds.save_settings(body.model_dump(exclude_none=True), actor)


@router.get("/whatsapp/recipient/{doc_type}/{source_id}")
async def wa_recipient(doc_type: str, source_id: str, request: Request,
                       entity_id: Optional[str] = None):
    """Saran nomor WA lawan-bicara (auto-fill di modal kirim)."""
    await require_permission(request, "document_delivery", "view")
    return await ds.resolve_recipient(doc_type, source_id, entity_id)


@router.get("/whatsapp/rules")
async def list_wa_rules(request: Request):
    await require_permission(request, "document_delivery", "view")
    return {"rules": await ds.list_rules()}


@router.post("/whatsapp/rules")
async def create_wa_rule(body: WARuleBody, request: Request):
    user = await require_permission(request, "document_delivery", "manage")
    actor = user.get("email") or user.get("name") or user.get("id")
    try:
        return await ds.create_rule(body.model_dump(exclude_none=True), actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/whatsapp/rules/{rule_id}")
async def update_wa_rule(rule_id: str, body: WARuleBody, request: Request):
    user = await require_permission(request, "document_delivery", "manage")
    actor = user.get("email") or user.get("name") or user.get("id")
    try:
        return await ds.update_rule(rule_id, body.model_dump(exclude_none=True), actor)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/whatsapp/rules/{rule_id}")
async def delete_wa_rule(rule_id: str, request: Request):
    await require_permission(request, "document_delivery", "manage")
    try:
        return await ds.delete_rule(rule_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{doc_type}/{source_id}")
async def list_deliveries(doc_type: str, source_id: str, request: Request):
    await require_permission(request, "document_delivery", "view")
    return {"deliveries": await ds.list_deliveries(doc_type, source_id)}
