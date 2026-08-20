"""H5 schemas — Integrasi AI (Anthropic Claude) config.

Key API disimpan di `system_settings` scope='integrations'. Dikelola admin via UI
Settings. Key TIDAK pernah dikembalikan plaintext ke FE (endpoint GET hanya
mengembalikan `has_key`). Lihat memory/PLAN_HRD.md §10b HR-Q5.
"""
from typing import Optional
from pydantic import BaseModel


class IntegrationsUpdate(BaseModel):
    """Patch config integrasi Anthropic. Aturan key:
    - `anthropic_api_key` None  → JANGAN ubah key tersimpan.
    - `anthropic_api_key` non-empty → set key baru.
    - `anthropic_clear_key` True → hapus key (kosongkan).
    """
    anthropic_api_key: Optional[str] = None
    anthropic_clear_key: bool = False
    anthropic_model: Optional[str] = None
    anthropic_enabled: Optional[bool] = None
