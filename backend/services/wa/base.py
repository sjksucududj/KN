"""Abstraksi WhatsApp provider."""
from __future__ import annotations
from typing import Any, Dict, List


class WhatsAppProvider:
    name: str = "base"

    def __init__(self, settings: Dict[str, Any] | None = None):
        self.settings = settings or {}

    async def send_document(self, to: str, doc_meta: Dict[str, Any],
                            pdf_bytes: bytes, caption: str = "") -> Dict[str, Any]:
        raise NotImplementedError

    async def send_message(self, to: str, text: str) -> Dict[str, Any]:
        raise NotImplementedError

    async def send_template(self, to: str, template: str, params: List[str],
                            lang: str = "id") -> Dict[str, Any]:
        """R6.5 — kirim TEMPLATE (wajib untuk outbound Meta Cloud di luar jendela 24 jam).
        Provider yang tidak mengenal template boleh merangkai `params` menjadi teks."""
        return await self.send_message(to, "\n".join([p for p in params if p]))
