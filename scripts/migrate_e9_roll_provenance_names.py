#!/usr/bin/env python3
"""MIGRASI — jejak perolehan roll menyimpan NAMA badan usaha, bukan id teknis
(KN-E9-PROV-ENTITY-ID-LEAK)

MASALAH YANG DIPERBAIKI
-----------------------
FASE E-9 mulai menyimpan riwayat perolehan roll (`inventory_rolls.acquired_history[]`)
supaya jejak "kain ini dulu masuk lewat GRN/PO mana" tidak hilang saat kepemilikan
berpindah antar badan usaha. Sayangnya tiap langkah riwayat ikut membawa
**id teknis pemilik sebelumnya** (`owner_entity_id: "ent_kanda"`).

Roll dikembalikan oleh banyak layar biasa (`GET /api/inventory/rolls`,
`GET /api/pegging/rolls`, kartu riwayat produk, kandidat retur, …). Akibatnya
sales PT-A membaca id badan usaha PT-B di dalam dokumen roll-nya sendiri —
persis kelas kebocoran yang ditutup FASE E-5 (E5.3: **lawan hanya boleh muncul
sebagai NAMA SINGKAT**). Terbukti memerah oleh gate:

    audit_entity_isolation → KEBOCORAN 4
      · /api/inventory/rolls  [sales PT-A] melihat ['ent_kanda']
      · /api/pegging/rolls    [sales PT-B] melihat ['ent_ksc']

APA YANG DILAKUKAN SKRIP INI
----------------------------
Untuk setiap langkah `acquired_history[]` yang masih menyimpan `owner_entity_id`:
menggantinya dengan `owner_entity_name` (nama singkat badan usaha, mis. "Kanda").
Id presisinya TIDAK hilang dari sistem — `inventory_movements` tetap menyimpan
`from_owner_entity_id`/`to_owner_entity_id`, dan koleksi itu sudah ter-scope serta
ter-redaksi oleh `movement_label_service` (E5.3).

Sifatnya **idempotent** (baris yang sudah bersih dilewati) dan punya **--dry-run**.

    python scripts/migrate_e9_roll_provenance_names.py --dry-run
    python scripts/migrate_e9_roll_provenance_names.py
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
    from services import movement_label_service as mlabel  # noqa: PLC0415

    rolls = await db.inventory_rolls.find(
        {"acquired_history.owner_entity_id": {"$exists": True}},
        {"_id": 0, "id": 1, "acquired_history": 1}).to_list(100000)

    print(f"{B}MIGRASI jejak perolehan roll → nama badan usaha (KN-E9-PROV-ENTITY-ID-LEAK){X}")
    print(f"  roll yang masih menyimpan id teknis di riwayat: {len(rolls)}")
    if not rolls:
        print(f"{G}  Tidak ada yang perlu dimigrasi (sudah bersih).{X}")
        return 0

    ids = {str(h.get("owner_entity_id")) for r in rolls
           for h in (r.get("acquired_history") or []) if h.get("owner_entity_id")}
    names = {i: await mlabel.short_name_of(i) for i in sorted(ids)}
    print(f"  badan usaha yang muncul: {len(ids)} → "
          + ", ".join(f"{i}={names[i]}" for i in sorted(ids)))

    if args.dry_run:
        print(f"{Y}  --dry-run: tidak ada yang ditulis.{X}")
        return 0

    changed = 0
    for r in rolls:
        hist = []
        for h in (r.get("acquired_history") or []):
            ent = h.get("owner_entity_id")
            if not ent:
                hist.append(h)
                continue
            clean = {k: v for k, v in h.items() if k != "owner_entity_id"}
            clean["owner_entity_name"] = (h.get("owner_entity_name")
                                          or names.get(str(ent)) or "")
            hist.append(clean)
        await db.inventory_rolls.update_one({"id": r["id"]},
                                            {"$set": {"acquired_history": hist}})
        changed += 1

    left = await db.inventory_rolls.count_documents(
        {"acquired_history.owner_entity_id": {"$exists": True}})
    print(f"  roll diperbarui      : {changed}")
    print(f"  sisa id teknis       : {left}")
    if left:
        print(f"{R}  GAGAL: masih ada {left} roll yang menyimpan id teknis.{X}")
        return 1
    print(f"{G}  SELESAI: riwayat perolehan kini menyebut NAMA badan usaha, bukan idnya.{X}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
