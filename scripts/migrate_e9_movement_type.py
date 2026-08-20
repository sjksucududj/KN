#!/usr/bin/env python3
"""MIGRASI — buku mutasi: `movement_type` untuk baris RETUR PELANGGAN
(KN-E9-MOV-TYPE-DRIFT)

MASALAH YANG DIPERBAIKI
-----------------------
Nama kanonik jenis mutasi di `inventory_movements` adalah **`movement_type`** — itulah
yang dibaca layar Mutasi (`inventoryConstants.jsx`), penyaring "Jenis Mutasi", laporan,
dan POC. Tiga baris yang lahir dari jalur RETUR PELANGGAN hanya menulis `type`:

    return_quarantine_in · quarantine_release / quarantine_scrap · return_reversal_out

Akibatnya mutasi itu muncul **tanpa jenis** (label kosong), dan apa pun yang mengurutkan
atau mengelompokkan jenis mutasi pecah begitu barisnya ada — terbukti saat data demo
FASE E-9 menerbitkan retur pelanggan pertama:

    POC FASE F US3/US11/US12 → TypeError: '<' not supported between 'NoneType' and 'str'

Sumbernya sudah diperbaiki di `services/return_service.py` (menulis KEDUA field, `type`
dipertahankan demi data lama). Skrip ini menambal baris LAMA.

Sifatnya **idempotent** (baris yang sudah punya `movement_type` dilewati) dan punya
**--dry-run**.

    python scripts/migrate_e9_movement_type.py --dry-run
    python scripts/migrate_e9_movement_type.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="hanya laporkan, jangan tulis apa pun")
    args = ap.parse_args()

    from db import db  # noqa: PLC0415

    rows = await db.inventory_movements.find(
        {"movement_type": {"$in": [None, ""]}, "type": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "type": 1}).to_list(200000)

    print(f"{B}MIGRASI buku mutasi → isi `movement_type` (KN-E9-MOV-TYPE-DRIFT){X}")
    print(f"  baris tanpa `movement_type`: {len(rows)}")
    if not rows:
        print(f"{G}  Tidak ada yang perlu dimigrasi (sudah bersih).{X}")
        return 0
    kinds: dict = {}
    for r in rows:
        kinds[r.get("type", "")] = kinds.get(r.get("type", ""), 0) + 1
    print("  jenis yang ditambal: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))

    if args.dry_run:
        print(f"{Y}  --dry-run: tidak ada yang ditulis.{X}")
        return 0

    changed = 0
    for kind, _n in kinds.items():
        res = await db.inventory_movements.update_many(
            {"movement_type": {"$in": [None, ""]}, "type": kind},
            {"$set": {"movement_type": kind}})
        changed += res.modified_count
    left = await db.inventory_movements.count_documents(
        {"movement_type": {"$in": [None, ""]}, "type": {"$nin": [None, ""]}})
    print(f"  baris diperbarui     : {changed}")
    print(f"  sisa tanpa jenis     : {left}")
    if left:
        print(f"{R}  GAGAL: masih ada {left} baris tanpa `movement_type`.{X}")
        return 1
    print(f"{G}  SELESAI: setiap mutasi punya jenis yang bisa dibaca layar & laporan.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
