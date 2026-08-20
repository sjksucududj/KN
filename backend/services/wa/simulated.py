"""Provider WhatsApp SIMULASI — mencatat ke log, tidak mengirim nyata.

Mengembalikan message_id palsu agar alur end-to-end bisa diuji tanpa kredensial.
"""
from __future__ import annotations
import logging
import uuid
from typing import Any, Dict

from .base import WhatsAppProvider

logger = logging.getLogger("delivery.whatsapp")


class SimulatedWhatsAppProvider(WhatsAppProvider):
    name = "simulated"

    async def send_document(self, to: str, doc_meta: Dict[str, Any],
                            pdf_bytes: bytes, caption: str = "") -> Dict[str, Any]:
        size = len(pdf_bytes or b"")
        logger.info("[WA:SIMULATED] doc to=%s file=%s size=%dB caption=%s",
                    to, doc_meta.get("filename"), size, caption)
        return {"status": "simulated", "simulated": True, "provider": self.name,
                "message_id": "wamid.sim_" + uuid.uuid4().hex[:16], "to": to}

    async def send_message(self, to: str, text: str) -> Dict[str, Any]:
        logger.info("[WA:SIMULATED] text to=%s: %s", to, text)
        return {"status": "simulated", "simulated": True, "provider": self.name,
                "message_id": "wamid.sim_" + uuid.uuid4().hex[:16], "to": to}
