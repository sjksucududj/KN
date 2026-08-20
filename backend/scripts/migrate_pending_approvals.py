#!/usr/bin/env python3
"""
migrate_pending_approvals.py — F5 (Unified Approval SSOT) sinkronisasi `pending_approvals`.

Mengisi SSOT `pending_approvals[]` pada `sales_orders` (ADDITIVE & idempotent):
- SO 'open' dengan `approval_required` tapi belum ada entri pending → buat 1 entri `nilai`
  (validasi admin) supaya muncul di Pusat Persetujuan.
- Pastikan field `pending_approvals` (list) & `credit_hold` (bool) selalu ada.
- Re-derive `stage`/`sub_status` agar konsisten.

Aman dijalankan berkali-kali di DB berisi (tanpa re-seed).
Self-verify: exit != 0 bila masih ada SO 'open' approval_required tanpa entri pending.

Jalankan:
  cd /app/backend && python scripts/migrate_pending_approvals.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _run() -> int:
    from services.so_approvals import backfill_pending_approvals
    from services.so_status import backfill_so_status
    from db import db

    res = await backfill_pending_approvals(db)
    rederive = await backfill_so_status(db)
    print(f"✅ pending_approvals disinkronkan ke {res['updated']}/{res['total']} SO "
          f"(re-derive stage {rederive['updated']}).")

    # Self-verify (GATE): SO open approval_required HARUS punya ≥1 entri pending.
    OPEN = ["reserved", "waiting_approval", "waiting_stock", "draft"]
    bad = 0
    query = {"$or": [{"status": "waiting_approval"},
                     {"status": {"$in": OPEN}, "approval_required": True}]}
    async for o in db.sales_orders.find(query, {"_id": 0, "number": 1, "pending_approvals": 1}):
        if not any(p.get("status") == "pending" for p in (o.get("pending_approvals") or [])):
            bad += 1
            print(f"   ❌ {o.get('number')} approval_required tapi tanpa pending entry")
    if bad:
        print(f"❌ MIGRASI BELUM BERSIH — {bad} SO tanpa entri pending.")
        return 1
    print("✅ MIGRASI BERSIH — semua SO open yang butuh approval punya entri pending.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
