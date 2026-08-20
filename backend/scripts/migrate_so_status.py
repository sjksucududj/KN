#!/usr/bin/env python3
"""
migrate_so_status.py — F4 (Status SO 2-level SSOT) backfill `stage` + `sub_status`.

Mengisi field turunan `stage` (induk linear) + `sub_status` (anak kontekstual) pada
SEMUA `sales_orders`, DIHITUNG dari `status` + konteks (backorder, approval) lewat
`services.so_status.derive_stage_substatus`. Additive + idempotent — TIDAK menyentuh
`status` lama. Aman dijalankan berkali-kali di DB berisi (tanpa re-seed).

Self-verify: exit != 0 bila masih ada SO tanpa stage / stage invalid setelah backfill.

Jalankan:
  cd /app/backend && python scripts/migrate_so_status.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _run() -> int:
    from services.so_status import backfill_so_status, VALID_STAGES
    from db import db

    stats = await backfill_so_status(db)
    print(f"✅ stage/sub_status backfilled ke {stats['updated']}/{stats['total']} SO "
          f"(invalid={stats['invalid']}).")

    # Distribusi stage (ringkas, untuk inspeksi cepat)
    dist: dict = {}
    sample = await db.sales_orders.find(
        {}, {"_id": 0, "number": 1, "status": 1, "stage": 1, "sub_status": 1}
    ).to_list(100000)
    for o in sample:
        dist[o.get("stage")] = dist.get(o.get("stage"), 0) + 1
    print(f"   distribusi stage: {dist}")

    # Self-verify (GATE): tidak boleh ada SO tanpa stage / stage di luar VALID_STAGES.
    missing = await db.sales_orders.count_documents({"stage": {"$exists": False}})
    invalid_stored = sum(1 for o in sample if o.get("stage") not in VALID_STAGES)
    print(f"   SO tanpa stage: {missing} (harus 0) | SO stage invalid (stored): {invalid_stored} (harus 0)")

    if missing != 0 or invalid_stored != 0 or stats["invalid"] != 0:
        print("❌ MIGRASI BELUM BERSIH — ada SO tanpa stage / stage invalid.")
        return 1
    print("✅ MIGRASI BERSIH — semua SO punya stage valid.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
