"""Provider Meta WhatsApp Cloud API — kerangka untuk aktivasi masa depan.

Catatan: mode default aplikasi = SIMULASI (pilihan user). Provider ini hanya
melakukan pengiriman nyata jika dikonfigurasi (access_token + phone_number_id)
DAN settings.simulate = False. Bila belum terkonfigurasi, mengembalikan status
'failed' dengan pesan yang jelas (tidak melempar exception agar UI tetap mulus).

Pengiriman DOKUMEN via Cloud API butuh upload media dulu lalu kirim pesan tipe
'document' — di sini dikirim sebagai pesan teks berisi tautan/caption (best-effort)
agar tetap aman tanpa storage publik.
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from .base import WhatsAppProvider

logger = logging.getLogger("delivery.whatsapp")


class MetaCloudWhatsAppProvider(WhatsAppProvider):
    name = "meta_cloud"

    def _ready(self) -> bool:
        return bool(self.settings.get("access_token") and self.settings.get("phone_number_id"))

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        import httpx  # lazy import
        pnid = self.settings["phone_number_id"]
        token = self.settings["access_token"]
        url = f"https://graph.facebook.com/v20.0/{pnid}/messages"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
            r.raise_for_status()
            data = r.json()
        mid = (data.get("messages") or [{}])[0].get("id")
        return {"status": "sent", "simulated": False, "provider": self.name, "message_id": mid, "to": payload.get("to")}

    async def send_document(self, to: str, doc_meta: Dict[str, Any],
                            pdf_bytes: bytes, caption: str = "") -> Dict[str, Any]:
        if not self._ready():
            return {"status": "failed", "simulated": False, "provider": self.name,
                    "error": "Meta WhatsApp Cloud belum dikonfigurasi (access_token/phone_number_id). Aktifkan mode simulasi."}
        try:
            body = (caption or doc_meta.get("label", "Dokumen")) + \
                   f"\nLampiran: {doc_meta.get('filename')} ({doc_meta.get('size', 0)} bytes)"
            return await self._post({"messaging_product": "whatsapp", "to": to,
                                     "type": "text", "text": {"body": body}})
        except Exception as exc:  # noqa: BLE001
            logger.warning("[WA:meta_cloud] gagal kirim: %s", exc)
            return {"status": "failed", "simulated": False, "provider": self.name, "error": str(exc)}

    async def send_message(self, to: str, text: str) -> Dict[str, Any]:
        if not self._ready():
            return {"status": "failed", "simulated": False, "provider": self.name,
                    "error": "Meta WhatsApp Cloud belum dikonfigurasi. Aktifkan mode simulasi."}
        try:
            return await self._post({"messaging_product": "whatsapp", "to": to,
                                     "type": "text", "text": {"body": text}})
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "simulated": False, "provider": self.name, "error": str(exc)}

    async def send_template(self, to: str, template: str, params: list,
                            lang: str = "id") -> Dict[str, Any]:
        """R6.5 — kirim TEMPLATE UTILITY yang sudah disetujui Meta.

        WAJIB dipakai untuk pesan OUTBOUND ke nomor yang tidak membalas dalam 24 jam
        terakhir (teks bebas akan ditolak error 131047). Jumlah `params` harus SAMA
        dengan jumlah variabel {{1}},{{2}}… pada body template (bila tidak → 132000).
        """
        if not self._ready():
            return {"status": "failed", "simulated": False, "provider": self.name,
                    "error": "Meta WhatsApp Cloud belum dikonfigurasi. Aktifkan mode simulasi."}
        if not template:
            return {"status": "failed", "simulated": False, "provider": self.name,
                    "error": "Nama template belum diisi di pengaturan WhatsApp."}
        try:
            return await self._post({
                "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": lang or "id"},
                    "components": [{
                        "type": "body",
                        "parameters": [{"type": "text", "text": str(p)[:900]}
                                       for p in (params or [])],
                    }],
                },
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("[WA:meta_cloud] template gagal: %s", exc)
            return {"status": "failed", "simulated": False, "provider": self.name, "error": str(exc)}
