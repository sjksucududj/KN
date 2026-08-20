"""Provider Fonnte (gateway WhatsApp populer di Indonesia).

Keunggulan untuk alert internal: cukup 1 API token, boleh TEKS BEBAS (tanpa
template & tanpa aturan 24 jam seperti Meta Cloud API).

Aktivasi: isi `fonnte_token` di Pengaturan → Penjadwal & Notifikasi → WhatsApp.
Selama token kosong, provider mengembalikan status 'failed' dengan pesan jelas
(TIDAK melempar exception) agar alur alert tetap mulus.

Dokumen resmi: https://docs.fonnte.com (endpoint POST https://api.fonnte.com/send,
header Authorization: <token>, field: target, message).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import WhatsAppProvider

logger = logging.getLogger("alerts.whatsapp")
API_URL = "https://api.fonnte.com/send"


class FonnteWhatsAppProvider(WhatsAppProvider):
    name = "fonnte"

    def _token(self) -> str:
        return (self.settings.get("fonnte_token") or "").strip()

    def _ready(self) -> bool:
        return bool(self._token())

    async def _post(self, data: Dict[str, Any]) -> Dict[str, Any]:
        import httpx  # lazy import
        headers = {"Authorization": self._token()}
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(API_URL, headers=headers, data=data)
            r.raise_for_status()
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = bool(body.get("status", False))
        if not ok:
            return {"status": "failed", "provider": self.name,
                    "error": str(body.get("reason") or body or "Fonnte menolak permintaan")}
        mid = ""
        ids = body.get("id")
        if isinstance(ids, list) and ids:
            mid = str(ids[0])
        return {"status": "sent", "simulated": False, "provider": self.name,
                "message_id": mid, "to": data.get("target")}

    async def send_message(self, to: str, text: str) -> Dict[str, Any]:
        if not self._ready():
            return {"status": "failed", "provider": self.name,
                    "error": "Fonnte belum dikonfigurasi (fonnte_token kosong)."}
        try:
            payload = {"target": to, "message": text}
            if self.settings.get("sender"):
                payload["delay"] = "1"
            return await self._post(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[WA:fonnte] gagal kirim: %s", exc)
            return {"status": "failed", "provider": self.name, "error": str(exc)}

    async def send_template(self, to: str, template: str, params: List[str],
                            lang: str = "id") -> Dict[str, Any]:
        """Fonnte tidak memakai template resmi — gabungkan parameter menjadi teks."""
        return await self.send_message(to, "\n".join([p for p in params if p]))

    async def send_document(self, to: str, doc_meta: Dict[str, Any],
                            pdf_bytes: bytes, caption: str = "") -> Dict[str, Any]:
        text = (caption or doc_meta.get("label", "Dokumen")) + \
               f"\nLampiran: {doc_meta.get('filename')} ({doc_meta.get('size', 0)} bytes)"
        return await self.send_message(to, text)
