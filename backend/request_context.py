"""FASE E-0 (E0.3) — Konteks request ber-cakupan entitas (ContextVar).

Masalah yang diselesaikan: `dependencies.audit()` dipanggil dari **62+ titik** tanpa
membawa entitas, sehingga jejak audit tak bisa disaring per entitas (55 dari 62 baris
tanpa entitas → sales & gudang membaca jejak SELURUH grup, kebocoran **L7**).

Menambahkan parameter entitas ke 62 pemanggil = perubahan besar & mudah terlewat.
Alih-alih itu, entitas aktif disimpan di `ContextVar` yang **diisi otomatis** oleh
`dependencies.current_user()` (dipanggil oleh SETIAP endpoint terautentikasi) dan
oleh `entity_scope.entity_ctx()`. `audit()` cukup membacanya.

ContextVar aman untuk asyncio: nilainya per-task, tidak bocor antar request.
"""
from contextvars import ContextVar
from typing import Any, Dict, Optional

_active_entity: ContextVar[Optional[str]] = ContextVar("kn_active_entity", default=None)
_actor: ContextVar[Optional[Dict[str, Any]]] = ContextVar("kn_actor", default=None)


def set_active_entity(entity_id: Optional[str]) -> None:
    if entity_id:
        _active_entity.set(entity_id)


def get_active_entity() -> Optional[str]:
    return _active_entity.get()


def set_actor(user: Optional[Dict[str, Any]]) -> None:
    if user:
        _actor.set(user)


def get_actor() -> Optional[Dict[str, Any]]:
    return _actor.get()


def reset() -> None:
    """Dipakai skrip/test agar konteks tidak menular antar skenario."""
    _active_entity.set(None)
    _actor.set(None)


def resolve_from_user(user: Dict[str, Any], header_entity: str = "") -> Optional[str]:
    """Entitas efektif dari user + header `X-Entity-Id` (tanpa query DB tambahan).

    Aturan sama dengan `entity_scope.entity_ctx`: header dipakai HANYA bila termasuk
    entitas yang diizinkan; `all` berarti mode gabungan → jejak tetap distempel ke
    entitas home supaya tidak ada baris audit tanpa pemilik.
    """
    home = user.get("home_entity_id") or ""
    allowed = user.get("allowed_entity_ids") or ([home] if home else [])
    req = (header_entity or "").strip()
    if req and req != "all" and req in allowed:
        return req
    return home or None


def active_entity_or(default: str = "") -> str:
    """FASE E-1 (E1.10) — badan usaha AKTIF request ini, dengan cadangan.

    Dipakai service/router lapis bawah yang dulu jatuh ke `DEFAULT_ENTITY_ID`
    (selalu PT Kain Suka Cita) ketika payload tidak menyebut badan usaha.
    Akibat lama: sales CV Kanda Suka membuat pelanggan/pesanan, tetapi datanya
    **mendarat di PT Kain Suka Cita** — pelanggannya lalu hilang dari layarnya
    sendiri dan muncul di buku PT lain.

    ContextVar-nya diisi `dependencies.current_user()` pada SETIAP request
    terautentikasi, jadi helper ini tidak butuh perubahan tanda tangan fungsi.
    Di luar request (skrip/seed/job) nilainya kosong → cadangan dipakai.
    """
    return _active_entity.get() or default
