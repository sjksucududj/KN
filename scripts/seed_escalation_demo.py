#!/usr/bin/env python3
"""seed_escalation_demo.py — Data demo untuk fitur ESKALASI BERTINGKAT (R6.6).

MENGAPA SCRIPT INI ADA
Eskalasi adalah fitur BERBASIS WAKTU: alert baru dinaikkan ke atasan setelah
`after_hours` (default 8 jam) belum dibaca. Pada database demo yang baru di-seed,
semua alert baru berumur beberapa menit sehingga rantai eskalasi TIDAK akan pernah
terlihat di UI tanpa menunggu berjam-jam.

YANG DILAKUKAN (transparan, TIDAK ada data palsu):
- Mengambil beberapa alert **NYATA** yang sudah ada (hasil job dari data bisnis nyata:
  piutang jatuh tempo, tugas gudang tertunda, dll) milik peran non-admin.
- **Menggeser `created_at`-nya ke masa lalu** (default 20 jam) — sama seperti
  `seed_realistic.py` menggeser tanggal order/PO agar data demo realistis.
  `dedupe_key` ikut disesuaikan supaya invarian SCH-2 tetap valid.
- Menjalankan job eskalasi sekali agar rantai (sales/gudang → manager → admin) terbentuk.

Isi notifikasi TIDAK diubah/dipalsukan — hanya umurnya digeser.

Jalankan: cd /app && python scripts/seed_escalation_demo.py [jumlah_alert] [umur_jam]
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from db import db                                    # noqa: E402
from services.escalation_service import job_escalation_scan  # noqa: E402

JUMLAH_DEFAULT = 2
UMUR_JAM_DEFAULT = 20
SEVERITY_TARGET = ("warning", "critical")
ROLE_TARGET = ("sales", "warehouse", "manager", "all")
# Utamakan alert milik peran BAWAH agar rantai lengkap terlihat (sales/gudang → manager → admin).
ROLE_PRIORITAS = {"sales": 0, "warehouse": 0, "manager": 1, "all": 2}


def _prioritas(n):
    return (ROLE_PRIORITAS.get(n.get("recipient_role"), 3), n.get("created_at") or "")


async def main(jumlah: int, umur_jam: int) -> int:
    kandidat = await db.notifications.find({
        "read": False,
        "type": {"$ne": "escalation"},
        "severity": {"$in": list(SEVERITY_TARGET)},
        "recipient_role": {"$in": list(ROLE_TARGET)},
        "$or": [{"escalation_level": {"$exists": False}}, {"escalation_level": 0}],
    }, {"_id": 0}).sort("created_at", 1).to_list(200)

    if not kandidat:
        print("Tidak ada alert yang memenuhi syarat. Jalankan dulu: "
              "POST /api/scheduler/jobs/all/run (atau tunggu jadwal).")
        return 1

    dipilih = sorted(kandidat, key=_prioritas)[:jumlah]
    baru = (datetime.now(timezone.utc) - timedelta(hours=umur_jam)).isoformat()
    for n in dipilih:
        dedupe = n.get("dedupe_key") or ""
        if n.get("ref"):
            dedupe = f"{n.get('type')}:{n['ref']}:{baru[:10]}"
        await db.notifications.update_one({"id": n["id"]}, {"$set": {
            "created_at": baru, "dedupe_key": dedupe,
        }, "$unset": {"escalation_level": "", "escalated_to": "",
                      "escalated_at": "", "escalation_notif_id": ""}})
        print(f"  · umur digeser {umur_jam} jam: [{n.get('recipient_role')}] "
              f"{n.get('title', '')[:60]}")

    res = await job_escalation_scan()
    print(f"\nJob eskalasi: {res.get('created')} alert dinaikkan · {res.get('detail')}")

    escals = await db.notifications.find(
        {"type": "escalation"}, {"_id": 0, "title": 1, "recipient_role": 1,
                                 "escalation_depth": 1}).to_list(50)
    for e in escals:
        print(f"  → level {e.get('escalation_depth')} ke {e.get('recipient_role')}: "
              f"{e.get('title', '')[:70]}")
    print(f"\nTotal notifikasi eskalasi di sistem: {len(escals)}")
    return 0


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else JUMLAH_DEFAULT
    j = int(sys.argv[2]) if len(sys.argv) > 2 else UMUR_JAM_DEFAULT
    sys.exit(asyncio.run(main(n, j)))
