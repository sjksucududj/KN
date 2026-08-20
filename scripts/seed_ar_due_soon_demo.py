#!/usr/bin/env python3
"""seed_ar_due_soon_demo.py — PS-21: buat kondisi piutang H-3 / H-1 / H / H+1 NYATA.

MASALAH: job `ar_due_soon` berbasis WAKTU. Pada data demo, tanggal order tidak
selalu jatuh tepat pada offset H-3/H-1/H/H+1 sehingga fitur tidak terlihat di UI
dan tidak bisa diuji tanpa menunggu berhari-hari.

CARA KERJA (tanpa memalsukan angka):
* Memilih order penjualan **NYATA** yang masih punya piutang terbuka
  (belum lunas, metode pembayaran termasuk AR, punya term pembayaran).
* Hanya **menggeser `created_at`** order tersebut sehingga tanggal jatuh temponya
  (created_at + term hari) mendarat tepat pada offset yang diminta.
  Nilai piutang, pelanggan, item, dan pembayaran TIDAK diubah.
* Menjalankan ulang job `ar_due_soon` (opsional, via flag `--run`).

Pemakaian:
    python scripts/seed_ar_due_soon_demo.py             # offset default -3,-1,0,1
    python scripts/seed_ar_due_soon_demo.py -3 0        # hanya H-3 & H
    python scripts/seed_ar_due_soon_demo.py --run       # + jalankan job-nya
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv                                    # noqa: E402
load_dotenv(ROOT / "backend" / ".env")

from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

DEFAULT_OFFSETS = [-3, -1, 0, 1]


async def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--run"]
    do_run = "--run" in sys.argv
    offsets = [int(a) for a in args] if args else DEFAULT_OFFSETS

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    sys.path.insert(0, str(ROOT / "backend"))
    from services.customer_service import (            # SSOT AR (tanpa duplikasi logika)
        _order_grand_total as grand_total, _order_paid as paid,
        order_payment_method, _term_days as term_days, DEAD_STATUSES, NON_AR_METHODS,
    )

    customers = {c["id"]: c for c in await db.customers.find(
        {}, {"_id": 0, "id": 1, "name": 1, "payment_profile": 1,
             "assigned_sales_id": 1}).to_list(5000)}
    orders = await db.sales_orders.find({}, {"_id": 0}).to_list(20000)

    kandidat = []
    for o in orders:
        if o.get("status") in DEAD_STATUSES or o.get("payment_status") == "paid":
            continue
        if order_payment_method(o) in NON_AR_METHODS:
            continue
        outstanding = round(grand_total(o) - paid(o), 2)
        if outstanding <= 0.01:
            continue
        cust = customers.get(o.get("customer_id"), {})
        days = int(term_days(cust, o) or 0)
        if days <= 0:
            continue
        kandidat.append((o, cust, days, outstanding))

    if not kandidat:
        print("❌ Tidak ada order dengan piutang terbuka + term pembayaran. "
              "Jalankan `python seed_realistic.py` lebih dulu.")
        return 1

    now = datetime.now(timezone.utc)
    print(f"Kandidat order berpiutang: {len(kandidat)} · offset diminta: {offsets}")
    changed = 0
    for i, offset in enumerate(offsets):
        if i >= len(kandidat):
            print(f"⚠️  Order tidak cukup untuk offset H{offset:+d} (dilewati)")
            continue
        o, cust, days, outstanding = kandidat[i]
        # due = created + term  →  created = (now - offset hari) - term
        target_created = now - timedelta(days=days + offset)
        await db.sales_orders.update_one(
            {"id": o["id"]},
            {"$set": {"created_at": target_created.isoformat(),
                      "ar_demo_offset": offset}})
        due = (target_created + timedelta(days=days)).date().isoformat()
        print(f"✅ {o.get('number')} · {cust.get('name', '')} · Rp {outstanding:,.0f} "
              f"· term {days} hari → jatuh tempo {due} (H{offset:+d})")
        changed += 1

    if do_run:
        from services import alert_ops_service as ops
        res = await ops.job_ar_due_soon()
        print(f"\n▶ job ar_due_soon: created={res['created']} · {res['detail']}")

    print(f"\nSelesai: {changed} order digeser. "
          "Buka bell notifikasi / Pengaturan → Penjadwal & Notifikasi → "
          "jalankan job 'Piutang Mendekati Jatuh Tempo'.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
