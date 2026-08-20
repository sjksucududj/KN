"""app_url — SATU sumber kebenaran **URL publik aplikasi** (untuk QR & tautan cetak).

MASALAH NYATA YANG DIPERBAIKI (FASE G-4)
----------------------------------------
QR pada dokumen cetak harus berisi URL yang bisa dibuka orang yang memegang KERTAS.
Sebelumnya URL itu hanya diambil dari header `Origin`/`Referer` permintaan. Akibatnya
setiap render yang BUKAN dari browser — cetak batch, penjadwal, kiriman WhatsApp,
skrip, atau panggilan API integrasi — menghasilkan QR kosong/relatif seperti
`/jejak-dokumen/...` yang **tidak bisa dibuka** dari HP pemegang surat.

Urutan penentuan (paling dipercaya lebih dulu):
  1. `Origin` / `Referer` permintaan  → persis host yang sedang dipakai user;
  2. `PUBLIC_APP_URL`                 → override eksplisit operator (mis. domain resmi);
  3. `APP_URL`                        → disediakan platform/supervisor;
  4. `REACT_APP_BACKEND_URL`          → env backend bila disetel;
  5. `frontend/.env`                  → sumber kebenaran alamat aplikasi di stack ini.

Tidak ada URL yang di-hardcode di dalam kode.
"""
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

_FRONTEND_ENV = Path("/app/frontend/.env")


def _clean(url: str) -> str:
    return (url or "").strip().strip('"').strip("'").rstrip("/")


def _origin_of(value: str) -> str:
    """Ambil `scheme://host` saja dari sebuah URL/Referer."""
    v = _clean(value)
    if not v:
        return ""
    try:
        from urllib.parse import urlparse
        p = urlparse(v)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:  # noqa: BLE001
        pass
    return v


@lru_cache(maxsize=1)
def _from_frontend_env() -> str:
    """Alamat aplikasi menurut `frontend/.env` (REACT_APP_BACKEND_URL)."""
    try:
        text = _FRONTEND_ENV.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    m = re.search(r"^REACT_APP_BACKEND_URL\s*=\s*(.+)$", text, re.M)
    return _origin_of(m.group(1)) if m else ""


def configured_app_url() -> str:
    """URL publik aplikasi TANPA konteks permintaan (dipakai job/penjadwal/WA)."""
    for env_key in ("PUBLIC_APP_URL", "APP_URL", "REACT_APP_BACKEND_URL", "BACKEND_URL"):
        val = _origin_of(os.environ.get(env_key, ""))
        if val:
            return val
    return _from_frontend_env()


def public_app_url(request: Optional[Any] = None) -> str:
    """URL publik aplikasi; utamakan host yang sedang dipakai pemanggil."""
    if request is not None:
        try:
            headers = request.headers
            hinted = headers.get("origin") or headers.get("referer") or ""
            origin = _origin_of(hinted)
            if origin:
                return origin
        except Exception:  # noqa: BLE001 — objek request tak standar → lanjut ke env
            pass
    return configured_app_url()
