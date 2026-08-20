#!/usr/bin/env python3
"""migrate_e4_master_scoped.py — FASE E-4 (E4b): stempel master lama menjadi GLOBAL.

KENAPA WAJIB. `payment_terms`, `expense_categories`, `document_templates`, dan
`sales_return_policies` baru saja pindah dari SHARED → SCOPED (berlapis global →
badan usaha). Baris lama TIDAK punya `entity_id`. Tanpa migrasi ini baris tersebut
akan lolos dari semua filter dan **hilang dari layar** — 6 syarat pembayaran, 8
kategori biaya, dan 2 template kop surat mendadak "tidak ada", padahal nilainya
sedang dipakai dokumen yang sudah terbit.

SIFAT: idempotent (boleh dijalankan berulang kali) + melaporkan jumlah baris
SEBELUM dan SESUDAH, sesuai aturan "setiap migrasi disertai hitung baris" di
`plan.md` §6.

Pakai:  python scripts/migrate_e4_master_scoped.py [--dry-run]
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv                                    # noqa: E402
load_dotenv(Path(__file__).resolve().parents[1] / "backend" / ".env")

from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

GLOBAL_ID = "all"
COLLECTIONS = (
    ("payment_terms", "Syarat Pembayaran"),
    ("expense_categories", "Kategori Biaya"),
    ("document_templates", "Template Dokumen & Kop Surat"),
    ("sales_return_policies", "Kebijakan Retur Jual"),
)


async def main(dry_run: bool = False) -> int:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    print("=" * 78)
    print("  MIGRASI E4b — master berlapis: baris lama distempel GLOBAL (entity_id='all')")
    print("=" * 78)
    total_changed = 0
    for coll, label in COLLECTIONS:
        before_total = await db[coll].count_documents({})
        # Baris yang belum punya stempel sah: field tidak ada, None, atau string kosong.
        missing_q = {"$or": [{"entity_id": {"$exists": False}},
                             {"entity_id": None},
                             {"entity_id": ""}]}
        missing = await db[coll].count_documents(missing_q)
        stamped_global = await db[coll].count_documents({"entity_id": GLOBAL_ID})
        per_entity = before_total - missing - stamped_global
        print(f"\n{label} ({coll})")
        print(f"  sebelum : total={before_total} · tanpa stempel={missing} · "
              f"global={stamped_global} · per badan usaha={per_entity}")
        if missing and not dry_run:
            res = await db[coll].update_many(missing_q, {"$set": {"entity_id": GLOBAL_ID}})
            total_changed += res.modified_count
            print(f"  distempel GLOBAL: {res.modified_count} baris")
        elif missing:
            print(f"  [dry-run] akan distempel GLOBAL: {missing} baris")
        after_total = await db[coll].count_documents({})
        after_missing = await db[coll].count_documents(missing_q)
        after_global = await db[coll].count_documents({"entity_id": GLOBAL_ID})
        print(f"  sesudah : total={after_total} · tanpa stempel={after_missing} · "
              f"global={after_global}")
        if after_total != before_total:
            print("  !! JUMLAH BARIS BERUBAH — migrasi ini seharusnya tidak "
                  "menambah/menghapus baris")
            return 1
        if not dry_run and after_missing != 0:
            print("  !! MASIH ADA baris tanpa stempel — periksa manual")
            return 1
    print(f"\nSELESAI · {total_changed} baris distempel GLOBAL "
          f"({'dry-run, tidak ada perubahan' if dry_run else 'tersimpan'})")
    print("Catatan: baris GLOBAL tetap berlaku untuk SEMUA badan usaha. Override per "
          "badan usaha dibuat lewat tombol 'Buat khusus' di layar Master per Badan Usaha.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--dry-run" in sys.argv)))
