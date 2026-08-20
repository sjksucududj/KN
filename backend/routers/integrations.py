"""H5 router — Integrasi AI (Anthropic Claude) config.

Scope `integrations` di system_settings. RBAC: admin only via hr.manage_settings
(manager TIDAK memilikinya). Key API TIDAK pernah dikembalikan plaintext — GET
hanya mengembalikan `has_key`. Lihat memory/PLAN_HRD.md §10b HR-Q5.
"""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request

from dependencies import require_permission, audit
from schemas_integrations import IntegrationsUpdate
from services import integrations_service as integ

router = APIRouter(prefix="/api")


@router.get("/admin/integrations")
async def get_integrations(request: Request) -> Dict[str, Any]:
    """Config integrasi ter-MASK (api_key → has_key). Admin only."""
    await require_permission(request, "hr", "manage_settings")
    return await integ.get_integrations_public()


@router.put("/admin/integrations")
async def update_integrations(payload: IntegrationsUpdate, request: Request) -> Dict[str, Any]:
    """Set/clear key + model + enabled. Admin only. Return config ter-mask."""
    actor = await require_permission(request, "hr", "manage_settings")
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan dikirim.")
    res = await integ.update_integrations(patch)
    # Audit TANPA membocorkan key (catat hanya status perubahan).
    await audit(actor["name"], "integrations_update", "system_settings", "integrations",
                {"key_changed": bool(patch.get("anthropic_api_key") or patch.get("anthropic_clear_key")),
                 "model": res["anthropic"]["model"], "enabled": res["anthropic"]["enabled"]})
    return res
