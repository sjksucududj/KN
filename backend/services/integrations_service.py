"""H5 service — Integrasi pihak ketiga (config runtime di system_settings).

Scope `integrations` di koleksi `system_settings`. Saat ini: Anthropic Claude
(untuk Design Gallery auto-tag). Pola deep-merge anti data-loss (cermin H4 `bpjs`).

KEAMANAN: `get_integrations_public()` MEMASK api_key → FE hanya menerima `has_key`.
Hanya `get_integrations()` (internal/service) yang membaca key plaintext.
"""
from typing import Any, Dict

from db import db
from core_utils import new_id, now_iso
from services.hr_service import deep_merge

SCOPE = "integrations"

# Model Claude vision yang didukung (2026). Default = sonnet (daily driver).
ANTHROPIC_MODELS = ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"]
DEFAULT_MODEL = "claude-sonnet-4-6"

DEFAULT_INTEGRATIONS: Dict[str, Any] = {
    "anthropic": {"api_key": "", "model": DEFAULT_MODEL, "enabled": False},
}


async def get_integrations() -> Dict[str, Any]:
    """Config penuh (TERMASUK api_key) — hanya untuk service internal (AI call)."""
    rec = await db.system_settings.find_one({"scope": SCOPE}, {"_id": 0})
    stored = {k: v for k, v in (rec or {}).items()
              if k not in ("scope", "id", "created_at", "updated_at")}
    return deep_merge(DEFAULT_INTEGRATIONS, stored)


async def get_integrations_public() -> Dict[str, Any]:
    """Config ter-mask untuk FE: api_key → has_key(bool). TIDAK pernah bocorkan key."""
    cfg = await get_integrations()
    ant = cfg.get("anthropic", {})
    return {
        "anthropic": {
            "has_key": bool(ant.get("api_key")),
            "model": ant.get("model") or DEFAULT_MODEL,
            "enabled": bool(ant.get("enabled")),
            "models_available": ANTHROPIC_MODELS,
        }
    }


async def update_integrations(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Update parsial config Anthropic (deep-merge; aturan key di schema).
    Mengembalikan config PUBLIC (ter-mask)."""
    current = await get_integrations()
    ant = dict(current.get("anthropic", {}))
    if patch.get("anthropic_clear_key"):
        ant["api_key"] = ""
    elif patch.get("anthropic_api_key"):
        ant["api_key"] = str(patch["anthropic_api_key"]).strip()
    if patch.get("anthropic_model") is not None:
        model = str(patch["anthropic_model"]).strip() or DEFAULT_MODEL
        ant["model"] = model
    if patch.get("anthropic_enabled") is not None:
        ant["enabled"] = bool(patch["anthropic_enabled"])
    to_set = {"anthropic": ant, "updated_at": now_iso()}
    existing = await db.system_settings.find_one({"scope": SCOPE}, {"_id": 0})
    if existing:
        await db.system_settings.update_one({"scope": SCOPE}, {"$set": to_set})
    else:
        await db.system_settings.insert_one(
            {"id": new_id("set"), "scope": SCOPE, "created_at": now_iso(), **to_set})
    return await get_integrations_public()
