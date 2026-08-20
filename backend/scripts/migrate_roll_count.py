#!/usr/bin/env python3
"""
migrate_roll_count.py — F2 (UoM SSOT) backfill `roll_count`/`on_hand_roll_count`.

Mengisi field roll-count pada SEMUA `inventory_balances` DIHITUNG dari
`inventory_rolls` (SSOT), TANPA mengubah qty bucket. Additive + idempotent —
aman dijalankan berkali-kali di DB yang sudah berisi (tanpa re-seed).

Jalankan:
  cd /app/backend && python scripts/migrate_roll_count.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _run():
    from services.roll_service import backfill_roll_counts
    from db import db
    n = await backfill_roll_counts()
    # Verifikasi ringkas
    sample = await db.inventory_balances.find(
        {"roll_count": {"$exists": True}},
        {"_id": 0, "product_id": 1, "available_qty": 1, "roll_count": 1, "on_hand_roll_count": 1},
    ).to_list(8)
    print(f"✅ roll_count backfilled ke {n} balance.")
    for b in sample:
        print(f"   {b.get('product_id'):<28} avail={b.get('available_qty'):>8} "
              f"roll_count={b.get('roll_count')} on_hand_roll={b.get('on_hand_roll_count')}")
    miss = await db.inventory_balances.count_documents({"roll_count": {"$exists": False}})
    print(f"   balance tanpa roll_count: {miss} (harus 0)")
    return 0 if miss == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
