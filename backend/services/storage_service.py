"""Local filesystem storage wrapper (FASE 5 — keputusan owner: storage LOKAL).

Helper upload/download attachment (bukti) yang dipakai ulang oleh banyak modul
(price_approvals, sales_returns, so_approvals). DB tetap source-of-truth referensi
file; penghapusan = soft-delete di DB (file fisik dibiarkan).

Sebelumnya wrapper ini memakai Emergent Object Storage (butuh EMERGENT_LLM_KEY).
Per keputusan owner, kini file disimpan di disk lokal di bawah `LOCAL_STORAGE_DIR`
(default `<backend>/uploads`). Interface (init_storage/put_object/get_object/
validate_upload/build_path/ext_of) DIPERTAHANKAN agar semua pemanggil tetap jalan.

Kontrak nyata: semua akses file lewat backend (tidak ada presigned URL).
"""
import asyncio
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger("storage_service")

APP_NAME = "kn7"

# Direktori penyimpanan lokal — bisa di-override via env (TIDAK hardcode rahasia).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.environ.get("LOCAL_STORAGE_DIR", str(_BACKEND_ROOT / "uploads")))

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf",
}
MIME_BY_EXT = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "gif": "image/gif", "pdf": "application/pdf",
}


# ─── Path helpers ────────────────────────────────────────────────────────────

def ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else "bin"


def build_path(scope: str, ext: str) -> str:
    """Path object relatif tanpa leading slash: kn7/{scope}/{uuid}.{ext}."""
    return f"{APP_NAME}/{scope}/{uuid.uuid4().hex}.{ext}"


def _abs_path(path: str) -> Path:
    """Resolve path object relatif → absolut di bawah STORAGE_DIR (anti path-traversal)."""
    rel = (path or "").lstrip("/")
    target = (STORAGE_DIR / rel).resolve()
    base = STORAGE_DIR.resolve()
    if base not in target.parents and target != base:
        raise ValueError("Path file tidak valid.")
    return target


def validate_upload(filename: str, content_type: str, size: int) -> str:
    """Validasi ekstensi/MIME/ukuran. Mengembalikan content_type ter-normalisasi
    atau melempar ValueError dengan pesan ramah."""
    ext = ext_of(filename)
    ct = (content_type or "").lower().split(";")[0].strip()
    if ct not in ALLOWED_MIME:
        ct = MIME_BY_EXT.get(ext, "")
    if ct not in ALLOWED_MIME:
        raise ValueError("Tipe file tidak didukung. Hanya JPG, PNG, WEBP, GIF, atau PDF.")
    if size > MAX_FILE_BYTES:
        raise ValueError("Ukuran file melebihi batas 10 MB.")
    if size <= 0:
        raise ValueError("File kosong.")
    return ct


# ─── Sync IO ─────────────────────────────────────────────────────────────────

def _put_sync(path: str, data: bytes, content_type: str) -> dict:
    target = _abs_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": path, "size": len(data), "content_type": content_type}


def _get_sync(path: str):
    target = _abs_path(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    data = target.read_bytes()
    ctype = MIME_BY_EXT.get(ext_of(path), "application/octet-stream")
    return data, ctype


# ─── Async API (dipertahankan agar pemanggil tidak berubah) ──────────────────

async def init_storage():
    """Pastikan direktori penyimpanan ada (best-effort)."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("[storage_service] local storage siap di %s", STORAGE_DIR)
    return str(STORAGE_DIR)


async def put_object(path: str, data: bytes, content_type: str) -> dict:
    return await asyncio.to_thread(_put_sync, path, data, content_type)


async def get_object(path: str):
    return await asyncio.to_thread(_get_sync, path)
