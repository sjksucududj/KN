#!/usr/bin/env python3
"""MIGRASI — saldo antar-PT per ARAH DAGANG  (KN-G6-ICA-CLOBBER)

MASALAH YANG DIPERBAIKI
-----------------------
Baris `interco_accounts` dulu ber-id `ica_{X}_{Y}` **tanpa penanda peran**, jadi
satu dokumen dipakai bersama oleh:

    * piutang arah dagang  X → Y   (X penjual)
    * utang    arah dagang  Y → X   (X pembeli)

Begitu dua PT yang sama berdagang DUA ARAH — normal terjadi lewat Permintaan
Internal ("stok saya habis, kirim dari PT sebelah") — recompute arah kedua
MENIMPA saldo arah pertama, dan utang yang nyata **hilang dari layar tanpa satu
pun pesan**. Terukur pada data demo: utang CV Kanda Suka ke PT Kain Suka Cita
Rp 1.766.010 menjadi Rp 0 hanya karena Kanda menerbitkan transaksi arah balik.

APA YANG DILAKUKAN SKRIP INI
----------------------------
1. Menghitung ulang saldo untuk **setiap arah dagang** yang punya transaksi
   (memakai mesin produksi `interco_service._update_account_balance`, bukan
   rumus tiruan) → menghasilkan baris ber-id `..._ar` / `..._ap`.
2. Menghapus baris warisan tanpa penanda peran yang sudah tidak dipelihara.

Sifatnya **idempotent** (boleh dijalankan berulang) dan punya **--dry-run**.

    python scripts/migrate_g6b_ica_directional.py --dry-run
    python scripts/migrate_g6b_ica_directional.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
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

    from services import interco_service as ics  # noqa: PLC0415

    db = ics.db
    before = await db[ics.COLL_ICA].count_documents({})
    legacy = [d async for d in db[ics.COLL_ICA].find(
        {"id": {"$not": {"$regex": "_(ar|ap)$"}}}, {"_id": 0, "id": 1, "role": 1,
                                                    "outstanding": 1})]
    # Arah dagang = setiap pasangan (penjual, pembeli) yang pernah bertransaksi.
    dirs = set()
    async for t in db[ics.COLL_ICT].find({"role": "seller"},
                                         {"_id": 0, "seller_entity_id": 1,
                                          "buyer_entity_id": 1}):
        s, b = t.get("seller_entity_id"), t.get("buyer_entity_id")
        if s and b and s != b:
            dirs.add((s, b))

    print(f"{B}MIGRASI saldo antar-PT per arah dagang (KN-G6-ICA-CLOBBER){X}")
    print(f"  baris saldo saat ini : {before}")
    print(f"  baris warisan        : {len(legacy)}"
          + (f"  → {[d['id'] for d in legacy][:6]}" if legacy else ""))
    print(f"  arah dagang ditemukan: {len(dirs)}")

    if args.dry_run:
        print(f"{Y}  --dry-run: tidak ada yang ditulis.{X}")
        return 0

    for seller, buyer in sorted(dirs):
        await ics._update_account_balance(seller, buyer)  # noqa: SLF001
    removed = (await db[ics.COLL_ICA].delete_many(
        {"id": {"$not": {"$regex": "_(ar|ap)$"}}})).deleted_count

    after = await db[ics.COLL_ICA].count_documents({})
    missing = []
    for seller, buyer in sorted(dirs):
        for _id in (ics.ica_ar_id(seller, buyer), ics.ica_ap_id(buyer, seller)):
            if not await db[ics.COLL_ICA].find_one({"id": _id}, {"_id": 1}):
                missing.append(_id)
    print(f"  dihitung ulang       : {len(dirs) * 2} baris")
    print(f"  baris warisan dihapus: {removed}")
    print(f"  baris saldo sekarang : {after}")
    if missing:
        print(f"{R}  GAGAL: {len(missing)} baris tidak terbentuk → {missing[:6]}{X}")
        return 1
    print(f"{G}  SELESAI: setiap arah dagang punya baris piutang & utang sendiri.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
