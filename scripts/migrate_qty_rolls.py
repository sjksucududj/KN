#!/usr/bin/env python3
"""FASE U — migrasi `qty_rolls` (dua satuan) untuk basis data yang SUDAH berjalan.

Skrip ini TIDAK menebak. Ia mengisi jumlah roll hanya di tempat yang angkanya bisa
DITURUNKAN dari roll yang benar-benar ada:

  · `inventory_movements` : baris yang menunjuk satu roll = 1 roll
  · `wms_tasks`           : jumlah roll yang lahir dari tugas penerimaan itu
  · `purchase_orders`     : `items[].received_rolls` dari roll ber-`po_id`
  · retur jual/beli/antar-PT + transfer gudang : dari `roll_ids`/`rolls[]` yang dipilih
  · `shipments`           : dari `rolls[]` yang keluar gudang
  · `makloon_orders`      : `steps[].qty_rolls_out` dari `lots[]` hasil terima
  · `inventory_rolls`     : `secondary_measures.kg` dari `weight_kg` yang sudah tercatat

Baris RENCANA (PO/PR/SO/RFQ) yang jumlah rollnya tidak pernah diketik siapa pun
**dibiarkan kosong** — di layar tampil "—". Menebak rencana orang lain lebih berbahaya
daripada mengaku tidak tahu (aturan yang sama dipakai FASE L untuk lini kosong).

Idempoten: menjalankan dua kali tidak mengubah apa pun pada putaran kedua.
`--dry-run` melaporkan hasil SUNGGUHAN tanpa menulis.

Pakai:
    python scripts/migrate_qty_rolls.py --dry-run
    python scripts/migrate_qty_rolls.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

G, Y, C, B, X = "\033[92m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"


async def main() -> int:
    dry = "--dry-run" in sys.argv
    demo = "--demo-plan" in sys.argv          # dipakai seed data demo, bukan produksi
    url = os.environ["MONGO_URL"].strip('"')
    name = os.environ.get("DB_NAME", "test_database").strip('"')
    client = AsyncIOMotorClient(url)
    dbx = client[name]
    try:
        from services import dual_qty_service as dual   # noqa: PLC0415
        print(f"{C}{B}== MIGRASI qty_rolls (FASE U) — basis data `{name}` "
              f"{'[DRY-RUN]' if dry else ''} =={X}")
        stat = await dual.backfill(dbx, demo_plan=demo, dry_run=dry)
        if not stat:
            print(f"{G}  Tidak ada yang perlu dimigrasikan (semua sudah punya jumlah roll "
                  f"atau tidak bisa diturunkan dari roll nyata).{X}")
        for k, v in sorted(stat.items()):
            print(f"  · {k:24s} {v} field diisi")
        total = sum(stat.values())
        print(f"{G}{B}  SELESAI — {total} field diisi{' (tidak ditulis: dry-run)' if dry else ''}.{X}")
        if not demo:
            print(f"{Y}  Catatan: baris RENCANA (PO/PR/SO/RFQ) yang jumlah rollnya tidak "
                  f"pernah diketik DIBIARKAN kosong — layar menampilkan “—”, bukan "
                  f"“0 roll”.{X}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
