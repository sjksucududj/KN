"""
Demo Seed Service
=================

Wrapper module yang me-load `/app/seed_realistic.py` agar bisa dipanggil
dari FastAPI endpoint backend.

Path Resolution (SSOT, in order):
1. Env var `KN_SEED_SCRIPT_PATH` (jika di-set, harus absolute path).
2. Project root: `<repo>/seed_realistic.py` (parent.parent.parent dari file ini).
3. Backend folder fallback: `<repo>/backend/seed_realistic.py`.

Design:
- Import error tidak boleh hard-crash backend startup.
- Jika seed script tidak ketemu, modul tetap importable tapi `run_demo_seed()`
  akan mengembalikan error message saat dipanggil dari endpoint.

Penggunaan:
    from services.demo_seed_service import run_demo_seed
    summary = await run_demo_seed(db_instance)
"""
import importlib.util
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _resolve_seed_path() -> Optional[Path]:
    """Try several conventional locations and return the first one that exists."""
    candidates = []

    env_path = os.getenv("KN_SEED_SCRIPT_PATH")
    if env_path:
        candidates.append(Path(env_path))

    here = Path(__file__).resolve()
    candidates.append(here.parent.parent.parent / "seed_realistic.py")  # /app/seed_realistic.py
    candidates.append(here.parent.parent / "seed_realistic.py")          # /app/backend/seed_realistic.py

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


_SEED_PATH = _resolve_seed_path()
_seed_module = None
_load_error: Optional[str] = None

if _SEED_PATH is None:
    _load_error = (
        "Demo seed script tidak ditemukan. "
        "Cek lokasi `seed_realistic.py` di project root atau set env var "
        "`KN_SEED_SCRIPT_PATH` ke absolute path file tersebut."
    )
    logger.warning("[demo_seed_service] %s", _load_error)
else:
    try:
        _spec = importlib.util.spec_from_file_location("seed_realistic", _SEED_PATH)
        _seed_module = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_seed_module)
        logger.info("[demo_seed_service] Loaded seed script from %s", _SEED_PATH)
    except Exception as exc:  # noqa: BLE001 — defensive boot path
        _load_error = f"Gagal memuat seed script {_SEED_PATH}: {exc}"
        logger.exception("[demo_seed_service] %s", _load_error)


async def run_demo_seed(db_instance):
    """
    Reset database operasional dan isi ulang dengan demo data realistis.
    PERHATIAN: Operasi ini DESTRUCTIVE — semua koleksi operasional akan dihapus.

    Args:
        db_instance: Motor AsyncIOMotorDatabase instance.

    Returns:
        dict: Summary jumlah record per koleksi setelah seed.

    Raises:
        RuntimeError: Jika seed script tidak ter-load saat startup.
    """
    if _seed_module is None:
        raise RuntimeError(_load_error or "Seed script tidak tersedia.")
    summary = await _seed_module.seed_all(db_instance)
    # F0-C: pastikan seluruh koleksi SCOPED ter-stamp entity_id (idempotent),
    # turunkan dari dokumen sumber (wms←PO, shipments←SO) agar konsisten.
    try:
        from scripts.migrate_entity_scoping import run_full_migration
        ok = await run_full_migration()
        if not ok:
            logger.warning("[demo_seed_service] migrate_entity_scoping melaporkan dokumen tanpa entitas")
    except Exception as exc:  # noqa: BLE001 — seed tetap sukses walau migrasi gagal di-log
        logger.exception("[demo_seed_service] gagal menjalankan migrate_entity_scoping: %s", exc)
    return summary
