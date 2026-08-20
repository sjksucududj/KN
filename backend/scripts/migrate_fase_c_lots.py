#!/usr/bin/env python3
"""migrate_fase_c_lots.py — MIGRASI IDEMPOTEN Fase C (lot kelas satu · D-10/D-26/D-27).

Yang dikerjakan (boleh dijalankan berulang, aman untuk produksi):
  1. **Pengaturan penegakan lot** (`system_settings` scope `lot`) dibuat bila belum ada
     — default `enforcement_mode=warn` sesuai keputusan pemilik (tidak memblokir gudang).
  2. **Backfill lot** — setiap string `inventory_rolls.lot` unik per (produk, pemilik,
     dye lot) menjadi dokumen `inventory_lots` bertanda `source="migration"`; roll
     mendapat `lot_id`. **String lot lama TETAP disimpan** di `roll.lot` (jejak) dan
     tercatat di `lot.legacy_lot_codes`.
  3. **Backfill `inventory_movements.lot_id`** dari roll terkait (ledger append-only:
     hanya menambah field jejak, tidak mengubah angka).
  4. **Recompute agregat lot** (roll_count/qty) — selalu turunan roll, tidak pernah $inc.

Pemakaian:
    python backend/scripts/migrate_fase_c_lots.py             # jalankan migrasi
    python backend/scripts/migrate_fase_c_lots.py --dry-run    # hanya laporan
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv                                     # noqa: E402
load_dotenv(ROOT / "backend" / ".env")

from services import lot_migration                                 # noqa: E402

DRY = "--dry-run" in sys.argv
G, Y, C, X = "\033[92m", "\033[93m", "\033[96m", "\033[0m"


async def main() -> int:
    print(f"{C}=== MIGRASI FASE C — LOT KELAS SATU ({'DRY-RUN' if DRY else 'EKSEKUSI'}) ==={X}")
    res = await lot_migration.run_all(actor="Migrasi Fase C", dry_run=DRY)
    print(f"  pengaturan lot dibuat      : {res['settings_created']}")
    print(f"  roll tanpa lot (ditemukan) : {res['rolls_without_lot']}")
    print(f"  lot dibentuk               : {res['lots_created']}")
    print(f"  roll ditautkan ke lot      : {res['rolls_linked']}")
    print(f"  movement diisi lot_id      : {res['movements_linked']}")
    if res.get("movements_orphan_roll"):
        print(f"{Y}  movement menunjuk roll yang sudah tidak ada (dibiarkan, tidak dikarang): "
              f"{res['movements_orphan_roll']}{X}")
    if res.get("orphan_products"):
        print(f"{Y}  roll menunjuk produk yang sudah tidak ada (dilewati, tidak dikarang): "
              f"{', '.join(res['orphan_products'][:5])}{X}")
    if not DRY:
        print(f"  lot di-recompute           : {res.get('lots_recomputed', 0)}")
    print(f"{G}  changed={res['changed']} — jalankan ulang untuk membuktikan idempotensi (changed=0).{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
