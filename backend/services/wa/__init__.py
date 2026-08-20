"""Pluggable WhatsApp providers untuk pengiriman dokumen & notifikasi/alert.

Default = 'simulated' (log + outbox, tanpa kirim nyata) sesuai pilihan user.
- 'meta_cloud' (Meta WhatsApp Cloud API) — resmi; pesan OUTBOUND ke nomor yang tidak
  membalas dalam 24 jam WAJIB memakai template UTILITY yang disetujui Meta.
- 'fonnte' (gateway lokal Indonesia) — cukup 1 API token, teks bebas.
Semua provider tunduk pada antarmuka `WhatsAppProvider` sehingga pemanggil tidak
perlu berubah saat provider ditukar.
"""
from __future__ import annotations
from typing import Any, Dict, Type

from .base import WhatsAppProvider
from .simulated import SimulatedWhatsAppProvider
from .meta_cloud import MetaCloudWhatsAppProvider
from .fonnte import FonnteWhatsAppProvider

_PROVIDERS: Dict[str, Type[WhatsAppProvider]] = {
    "simulated": SimulatedWhatsAppProvider,
    "meta_cloud": MetaCloudWhatsAppProvider,
    "fonnte": FonnteWhatsAppProvider,
}


def get_wa_provider(name: str | None, settings: Dict[str, Any] | None = None) -> WhatsAppProvider:
    key = (name or "simulated").lower()
    cls = _PROVIDERS.get(key, SimulatedWhatsAppProvider)
    return cls(settings or {})


def available_providers():
    return list(_PROVIDERS.keys())
