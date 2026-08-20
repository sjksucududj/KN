"""R0 demo seed — lengkapi data agar modul Return Policy tampil bermakna.

Idempotent: aman dijalankan berulang. TIDAK menghapus data.
- Set origin_type + return_policy pada supplier (1 dijadikan IMPORT non-returnable).
- Buat 2 kebijakan retur jual (global 30 hari + kategori Batik 45 hari) bila belum ada.

Jalankan: python seed_r0_demo.py
"""
import asyncio
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


LOCAL_POLICY = {
    "window_days": 30, "refund_modes": ["ap_credit", "cash"],
    "returnable_to_supplier": True, "rma_required": False,
    "restocking_fee_pct": 0.0, "condition_requirements": "Kondisi asli, sertakan bukti",
    "custom_fields": {}, "valid_from": "", "valid_until": "", "notes": "Kebijakan lokal standar",
}
IMPORT_POLICY = {
    "window_days": 90, "refund_modes": ["ap_credit"],
    "returnable_to_supplier": False, "rma_required": True,
    "restocking_fee_pct": 20.0,
    "condition_requirements": "Kemasan asli utuh; klaim dgn foto & video",
    "custom_fields": {"min_klaim_meter": "10", "butuh_video": "ya"},
    "valid_from": "", "valid_until": "", "notes": "Impor — retur ke LN tidak praktis; arahkan regrade + jual lokal",
}


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    suppliers = await db.suppliers.find({}, {"_id": 0, "id": 1, "name": 1, "origin_type": 1}).to_list(100)
    print(f"Suppliers: {len(suppliers)}")
    for i, s in enumerate(suppliers):
        # Supplier pertama → IMPORT (demo non-returnable), sisanya LOCAL.
        is_import = (i == 0)
        upd = {
            "origin_type": "import" if is_import else "local",
            "country": "China" if is_import else "",
            "return_policy": IMPORT_POLICY if is_import else LOCAL_POLICY,
            "updated_at": now_iso(),
        }
        await db.suppliers.update_one({"id": s["id"]}, {"$set": upd})
        print(f"  · {s['name']}: origin={upd['origin_type']}")

    # Sales return policies (global + kategori) — buat bila belum ada yang aktif.
    existing = await db.sales_return_policies.count_documents({"status": {"$ne": "inactive"}})
    if existing == 0:
        docs = [
            {
                "id": "srp_demo_global", "name": "Retur Standar 30 Hari", "scope": "global",
                "scope_ref": "", "window_days": 30,
                "allowed_return_types": ["retur", "bs", "penggantian", "komplain", "garansi"],
                "allowed_outcomes": ["refund", "store_credit", "nego", "reject"],
                "restocking_fee_pct": 0.0, "require_inspection": True,
                "enforce_window": False, "link_to_supplier_window": False,
                "condition_requirements": "Sertakan bukti foto kerusakan",
                "custom_fields": {}, "valid_from": "", "valid_until": "",
                "entity_id": "", "notes": "Kebijakan default seluruh transaksi",
                "status": "active", "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso(),
            },
            {
                "id": "srp_demo_batik", "name": "Batik — Retur 45 Hari (cek motif)", "scope": "category",
                "scope_ref": "Batik", "window_days": 45,
                "allowed_return_types": ["retur", "penggantian", "komplain", "garansi"],
                "allowed_outcomes": ["refund", "store_credit", "nego"],
                "restocking_fee_pct": 5.0, "require_inspection": True,
                "enforce_window": True, "link_to_supplier_window": False,
                "condition_requirements": "Motif & warna sesuai; label utuh",
                "custom_fields": {"catatan": "verifikasi motif oleh QC"},
                "valid_from": "", "valid_until": "",
                "entity_id": "", "notes": "Batik butuh verifikasi motif",
                "status": "active", "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso(),
            },
        ]
        await db.sales_return_policies.insert_many(docs)
        print(f"Sales return policies dibuat: {len(docs)}")
    else:
        print(f"Sales return policies aktif sudah ada: {existing} (skip)")

    print("R0 demo seed selesai.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
