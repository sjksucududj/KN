"""
Kain Nusantara — Realistic Seed Data Script
Populates database with realistic historical data including:
- Purchase orders with completed receiving history
- Sales orders in various stages
- Inbound & outbound tasks (completed + in-progress)
- Inventory movements

Dapat dipakai sebagai:
1) Standalone CLI:   `python seed_realistic.py`
2) Imported module:  `from seed_realistic import seed_all; await seed_all(db_instance)`
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent / "backend"
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
from core_utils import hash_password, new_id, now_iso, next_doc_number
from permissions_config import DEFAULT_PERMISSIONS
from datetime import datetime, timedelta, timezone
import random

# `db` is a module-level placeholder; it will be set by `init_with_db()`
# or by `main()` when running as a standalone script. Seed functions reference
# `db` by name at call-time, so replacing this value works correctly.
db = None


def init_with_db(db_instance):
    """Inject an external Motor DB instance (for use from FastAPI endpoint)."""
    global db
    db = db_instance


def ago(days=0, hours=0, minutes=0) -> str:
    """Return ISO string for a datetime in the past."""
    dt = datetime.now(timezone.utc) - timedelta(days=days, hours=hours, minutes=minutes)
    return dt.isoformat()


async def clear_collections():
    """Drop operational data — keep nothing (fresh realistic seed)."""
    cols = [
        "users", "uoms", "warehouses", "products", "customers",
        "inventory_balances", "inventory_movements", "inventory_rolls", "sales_orders",
        # FASE C/D — lot kelas satu & kontrak mitra ikut direset agar tidak ada
        # lot/kontrak yatim yang menunjuk produk/mitra yang sudah dihapus
        # (INV-LOT-01 & INV-MKO-06 tetap hijau pada DB yang baru di-seed).
        "inventory_lots", "supplier_contracts",
        # FASE E — barang supplier (peta SKU/nama versi supplier) ikut direset agar tidak
        # ada peta yatim ke produk/supplier yang sudah dihapus (INV-SRC-05 tetap hijau).
        "supplier_items",
        "wms_tasks", "purchase_orders", "document_templates",
        "permission_settings", "audit_logs", "onboarding_checklists",
        "cycle_counts", "transfers", "escalations",
        "warehouse_transfers", "cycle_count_sessions",
        "business_entities", "notifications",
        "system_settings", "payment_terms", "approval_rules",
        "price_approvals", "customer_prices", "shipments", "tax_invoices",
        "suppliers", "cash_transactions", "purchase_returns", "bank_accounts",
        # R5 — retur jual & dokumen finansial terkait (fresh seed: hindari orphan tanpa JE)
        "sales_returns", "credit_notes", "store_credit_ledger", "store_credit_redemptions",
        "purchase_requisitions", "supplier_price_lists",
        "vendor_bills",
        "landed_cost_vouchers",
        # FASE P8 — RFQ demo (dulu koleksi ini tak pernah di-seed MAUPUN dibersihkan,
        # sehingga layar Permintaan Penawaran selalu kosong di data demo).
        "rfqs",
        "sales_targets", "sales_incentives", "collection_followups", "credit_overrides",
        "product_categories", "ar_receipts", "incentive_rates",
        "color_library",
        "makloons", "process_recipes", "makloon_orders",
        "gl_accounts", "journal_entries",
        "rfid_tags", "rfid_devices", "rfid_reads",
        "budgets",
        # R6.1/R6.2 — Bank Reconciliation + Fixed Assets (fresh seed: hindari orphan tanpa JE)
        "bank_statement_lines", "fin_fixed_assets", "fin_depreciation_entries",
        # R6.3 — Budget Control: kebijakan over-budget per entitas
        "fin_budget_rules",
        # R6.4 — Produksi In-House: resep (BOM) + Work Order (fresh seed: hindari WO orphan)
        "mfg_boms", "mfg_work_orders",
        # R6.5 — Scheduler & kanal WhatsApp: histori job + outbox pesan
        "sys_scheduler_runs", "sys_wa_outbox",
        # FASE G-1 — amandemen dokumen ikut direset bersama `credit_notes` yang
        # diterbitkannya. Kalau tidak, seed baru meninggalkan amandemen yatim yang
        # menunjuk sales_order & nota yang sudah tidak ada (jejak audit palsu).
        # `amendment_reasons` SENGAJA tidak dihapus: itu taksonomi (master), bukan
        # transaksi, dan sudah idempotent lewat `ensure_reasons()`.
        "doc_amendments",
        # FASE G-3 — keputusan selisih pembayaran menempel pada kwitansi & pesanan yang
        # ikut direset; kalau dibiarkan hidup jejaknya menunjuk dokumen yang tak ada lagi.
        "payment_variance_decisions",
        # FASE F — spesifikasi & permintaan sample R&D menempel pada produk, supplier,
        # roll, dan kontrak yang SEMUANYA ikut direset. Kalau dibiarkan hidup, INV-RND-*
        # benar-benar memerah karena dokumennya jadi yatim (pernah terjadi di gate).
        # `design_gallery` SENGAJA tidak dihapus: itu MASTER desain (kode + versi +
        # artwork), bukan transaksi — `seed_rnd()` memakai ulang kode yang sudah ada.
        "md_specs", "md_samples",
        # FASE G-9 — kasus keuangan menempel pada mutasi bank, kwitansi, dan pesanan yang
        # SEMUANYA ikut direset. Kalau dibiarkan hidup, kasusnya jadi yatim (menunjuk
        # dokumen yang sudah tidak ada) dan INV-CASE-01 memerah karena jejaknya palsu.
        "finance_cases",
        # FASE E-7 (E7d) — permintaan internal menempel pada produk, badan usaha, dan
        # transaksi antar-PT yang SEMUANYA ikut direset. Kalau dibiarkan hidup, layar
        # Permintaan Internal menunjuk transaksi yang sudah tidak ada.
        "internal_requests",
        # FASE G-7 — kontrabon memegang `vendor_bills` (ikut direset di atas) dan
        # transaksi kas pembayarannya. Kalau dibiarkan hidup ia menunjuk faktur yang
        # sudah tidak ada → INV-CB-01/02 memerah dan layar Kontrabon menampilkan
        # tanda terima atas faktur hantu.
        "contra_bons",
        # FASE G-6 — transaksi antar-PT memegang produk, roll & jurnal yang SEMUANYA
        # ikut direset. Dibiarkan hidup = dokumen kembar menunjuk barang hantu,
        # saldo antar-PT drift (INV-IC-04), dan entri eliminasi konsolidasi
        # menghapus pendapatan yang tidak pernah ada (INV-IC-03).
        "interco_transactions", "interco_accounts", "interco_settlements",
        # FASE G-6b — retur antar-PT + faktur pajak MASUKAN (pasangan faktur internal).
        # Tanpa ini, retur/faktur masukan demo menjadi yatim setelah seed ulang dan
        # INV-IC-07/08 memerah karena menunjuk transaksi yang sudah dihapus.
        "interco_returns", "tax_invoices_in",
        "intercompany_eliminations",
        # FASE L — master LINI PRODUK. Ikut direset supaya seed selalu deterministik:
        # tanpa ini, `seed_product_lines()` akan menambah baris kembar setiap seed ulang
        # dan `_assert_key_free` menolak lini keempat yang dibuat pemilik lewat layar.
        # Override per badan usaha (kalau ada) juga ikut, karena produk yang dirujuknya
        # direset di atas.
        "product_lines",
        # FASE T — master TAHAPAN PROSES. Alasan reset sama dengan lini di atas:
        # tanpa ini `seed_process_stages()` menambah baris kembar setiap seed ulang,
        # dan `_assert_key_free` akan menolak tahap baru (mis. "Sanforize") yang
        # dibuat pemilik lewat layar karena kodenya dianggap sudah terpakai.
        "process_stages",
    ]
    for col in cols:
        await db[col].delete_many({})
    # Nomor dokumen per-entitas dijaga sebagai sequence atomik di `number_sequences`.
    # Kalau counter TIDAK direset bersama transaksinya, seed ulang menghasilkan nomor
    # yang melompat (mis. KSC/SCT-00032 padahal hanya ada 7 kontrak) sehingga data demo
    # tidak deterministik dan dokumen/uji yang menyebut nomor jadi salah. Semua dokumen
    # pemilik nomor ikut dihapus di atas, jadi reset ini AMAN (tidak ada nomor kembar).
    await db.number_sequences.delete_many({})
    print("✅ Cleared all collections")


async def seed_users():
    ALL = ["ent_ksc", "ent_kanda"]
    await db.users.insert_many([
        {
            "id": "user_admin_01", "name": "Budi Santoso", "email": "admin@kainnusantara.id", "phone": "081200000001",
            "role": "admin", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ALL,
            "created_at": ago(days=180)
        },
        {
            "id": "user_sales_01", "name": "Ayu Permatasari", "email": "sales@kainnusantara.id", "phone": "081200000002",
            "role": "sales", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ["ent_ksc"],
            "created_at": ago(days=180)
        },
        {
            "id": "user_manager_01", "name": "Dewi Rahayu", "email": "manager@kainnusantara.id", "phone": "081200000003",
            "role": "manager", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ALL,
            "created_at": ago(days=180)
        },
        {
            "id": "user_wh_01", "name": "Eko Prasetyo", "email": "warehouse@kainnusantara.id", "phone": "081200000004",
            "role": "warehouse", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ["ent_ksc"],
            "created_at": ago(days=180)
        },
        {
            "id": "user_wh_02", "name": "Fitri Handayani", "email": "warehouse2@kainnusantara.id", "phone": "081200000005",
            "role": "warehouse", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ["ent_ksc"],
            "created_at": ago(days=90)
        },
        {
            "id": "user_sales_02", "name": "Bima Saputra", "email": "sales2@kainnusantara.id", "phone": "081200000006",
            "role": "sales", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ["ent_ksc"],
            "created_at": ago(days=150)
        },
        {
            "id": "user_sales_03", "name": "Citra Lestari", "email": "sales3@kainnusantara.id", "phone": "081200000007",
            "role": "sales", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_kanda", "allowed_entity_ids": ["ent_kanda"],
            "created_at": ago(days=120)
        },
        # ── FASE E-8 (E8.1) — DUA PERAN BARU (keputusan pemilik: akun demo BARU,
        # `manager@` TETAP manajer). Sebelum ini orang yang mengurus keseluruhan
        # pesanan harus dijadikan `sales` (tak bisa Konfirmasi SO) atau `manager`
        # (ikut dapat kuasa tutup buku & payroll).
        {
            "id": "user_sales_admin_01", "name": "Rina Kusumawati",
            "email": "salesadmin@kainnusantara.id", "phone": "081200000008",
            "role": "sales_admin", "password_hash": hash_password("demo12345"), "status": "active",
            # Admin Sales berbasis PENUGASAN (E8.10b#1): di demo ini ditugaskan ke
            # DUA badan usaha supaya mekanisme multi-penugasan peran non-lintas
            # benar-benar terpakai (bukan hanya ada di kode).
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ALL,
            "created_at": ago(days=100)
        },
        {
            "id": "user_finance_01", "name": "Hendra Wijaya",
            "email": "finance@kainnusantara.id", "phone": "081200000009",
            "role": "finance", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ["ent_ksc"],
            "created_at": ago(days=100)
        },
        # ── UTANG MIGRASI (ii) — AKUN WARISAN SEBELUM FASE E-8 ──────────────────
        # Ini persis keadaan yang dikeluhkan pemilik: orang ini pekerjaannya
        # **Admin Sales** (verifikasi pesanan · memproses retur · menagihkan
        # transaksi antar-PT), tetapi perannya `manager` karena sampai FASE E-7
        # hanya `manager` yang bisa Konfirmasi SO. Akibatnya ia ikut memegang kuasa
        # tutup buku, payroll, dan bayar tagihan supplier yang tidak pernah ia pakai.
        # Layar "Cek Peran" (`?view=entities-access`, tab Cek Peran) menemukan akun
        # seperti ini DARI JEJAKNYA dan menawarkan penurunan peran yang tercatat.
        # Jejak kegiatannya dibuat di `seed_legacy_role_footprint()`.
        {
            "id": "user_manager_02", "name": "Rudi Hartono",
            "email": "adminsales.lama@kainnusantara.id", "phone": "081200000010",
            "role": "manager", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ALL,
            "created_at": ago(days=170)
        },
        # ── FASE L (2026-08-18) — AKUN BERPAGAR LINI. Pemilik: "woven/knit/printing
        # dikerjakan staf berbeda, pembedanya pagar keras tapi bisa dikonfigurasi."
        # Akun ini SENGAJA ada di data demo supaya pagarnya bisa diuji LEWAT LAYAR
        # (bukan hanya lewat POC): daftar produk/pesanan/roll-nya hanya lini printing,
        # dan menambahkan kain woven ke pesanan ditolak 403 ber-kalimat Indonesia.
        # Akun lain SENGAJA ber-`allowed_line_codes: []` = SEMUA lini (bawaan) supaya
        # kehadiran fase ini tidak mengubah apa pun bagi mereka.
        {
            "id": "user_sales_04", "name": "Dewi Anggraini",
            "email": "dewi.printing@kainnusantara.id", "phone": "081200000011",
            "role": "sales", "password_hash": hash_password("demo12345"), "status": "active",
            "home_entity_id": "ent_ksc", "allowed_entity_ids": ["ent_ksc"],
            "allowed_line_codes": ["printing"],
            "created_at": ago(days=60)
        },
    ])
    # `allowed_line_codes` dibuat EKSPLISIT untuk semua akun lain (kosong = semua
    # lini). Eksplisit supaya layar "Akun & Akses" bisa membedakan "sengaja semua
    # lini" dari "field belum pernah ada" tanpa menebak.
    await db.users.update_many({"allowed_line_codes": {"$exists": False}},
                               {"$set": {"allowed_line_codes": []}})
    print("✅ Users seeded (with entity assignment) — 11 akun · 6 peran "
          "(admin · manager×2 · sales_admin · finance · sales×4 · warehouse×2) "
          "· 1 akun berpagar lini printing (FASE L)")


async def seed_uoms():
    # FASE U — satu daftar benih dipakai bersama `backend/bootstrap.py`
    # (`services/uom_service.UOM_SEED_ROWS`). Sebelum ini berkas ini menanam 4 baris
    # tanpa `factor_to_base`/`aliases` sementara bootstrap menanam 6 baris ber-faktor,
    # jadi isi master bergantung urutan "restart vs seed" (K1) dan satuan yang dipakai
    # dokumen (`yard`, `kg`, `meter`) tak pernah cocok dengan satu baris master pun (D1).
    from services.uom_service import UOM_SEED_ROWS
    await db.uoms.insert_many([{**r, "status": "active", "created_at": ago(days=180)}
                               for r in UOM_SEED_ROWS])
    print(f"✅ UOMs seeded ({len(UOM_SEED_ROWS)} satuan, ber-alias)")


async def seed_warehouses():
    """FASE E-4 (E4.1) — setiap gudang lahir dengan MODE PEMAKAIAN yang eksplisit.

    Keputusan pemilik (2026-08-10): Jakarta & Surabaya **bersama** (di dalamnya ada
    stok lebih dari satu badan usaha), Bandung **khusus PT Kain Suka Cita** (isinya
    memang seluruhnya KSC), Tangerang **khusus CV Kanda Suka** (gudang barunya).
    """
    await db.warehouses.insert_many([
        {
            "id": "wh_jakarta", "code": "WH-JKT", "name": "Gudang Jakarta Utara", "city": "Jakarta",
            "lat": -6.1751, "lng": 106.8650, "active": True, "created_at": ago(days=180),
            "sharing_mode": "shared", "entity_ids": [],
            "zones": [{"id": "zone_jkt_a", "name": "Zone A", "racks": [
                {"id": "rack_jkt_a1", "name": "Rack A1", "bins": [
                    {"id": "bin_jkt_a1_01", "code": "A1-01", "capacity": 500},
                    {"id": "bin_jkt_a1_02", "code": "A1-02", "capacity": 500},
                    {"id": "bin_jkt_a1_03", "code": "A1-03", "capacity": 500},
                ]},
                {"id": "rack_jkt_a2", "name": "Rack A2", "bins": [
                    {"id": "bin_jkt_a2_01", "code": "A2-01", "capacity": 400},
                    {"id": "bin_jkt_a2_02", "code": "A2-02", "capacity": 400},
                ]},
            ]},
            {"id": "zone_jkt_b", "name": "Zone B", "racks": [
                {"id": "rack_jkt_b1", "name": "Rack B1", "bins": [
                    {"id": "bin_jkt_b1_01", "code": "B1-01", "capacity": 600},
                    {"id": "bin_jkt_b1_02", "code": "B1-02", "capacity": 600},
                ]}
            ]}]
        },
        {
            "id": "wh_bandung", "code": "WH-BDG", "name": "Gudang Bandung Kopo", "city": "Bandung",
            "lat": -6.9175, "lng": 107.6191, "active": True, "created_at": ago(days=180),
            "sharing_mode": "dedicated", "entity_ids": ["ent_ksc"],
            "zones": [{"id": "zone_bdg_a", "name": "Zone A", "racks": [
                {"id": "rack_bdg_a1", "name": "Rack A1", "bins": [
                    {"id": "bin_bdg_a1_01", "code": "A1-01", "capacity": 600},
                    {"id": "bin_bdg_a1_02", "code": "A1-02", "capacity": 600},
                ]}
            ]}]
        },
        {
            "id": "wh_surabaya", "code": "WH-SBY", "name": "Gudang Surabaya Rungkut", "city": "Surabaya",
            "lat": -7.2504, "lng": 112.7688, "active": True, "created_at": ago(days=180),
            "sharing_mode": "shared", "entity_ids": [],
            "zones": [{"id": "zone_sby_a", "name": "Zone A", "racks": [
                {"id": "rack_sby_a1", "name": "Rack A1", "bins": [
                    {"id": "bin_sby_a1_01", "code": "A1-01", "capacity": 400},
                    {"id": "bin_sby_a1_02", "code": "A1-02", "capacity": 400},
                ]}
            ]}]
        },
        {
            # Gudang khusus CV Kanda Suka — bukti nyata "gudang khusus" di layar:
            # pengguna KSC tidak akan menemukan gudang ini di pemilih mana pun.
            "id": "wh_tangerang", "code": "WH-TGR", "name": "Gudang Tangerang Cikupa",
            "city": "Tangerang", "lat": -6.2088, "lng": 106.5306, "active": True,
            "created_at": ago(days=120),
            "sharing_mode": "dedicated", "entity_ids": ["ent_kanda"],
            "zones": [{"id": "zone_tgr_a", "name": "Zone A", "racks": [
                {"id": "rack_tgr_a1", "name": "Rack A1", "bins": [
                    {"id": "bin_tgr_a1_01", "code": "A1-01", "capacity": 500},
                    {"id": "bin_tgr_a1_02", "code": "A1-02", "capacity": 500},
                ]}
            ]}]
        },
    ])
    print("✅ Warehouses seeded (2 bersama · 2 khusus badan usaha)")


COLOR_LIBRARY_SEED = [
    # (code, name, hex, system, family)
    ("KN-WHT-01", "Putih Susu", "#F7F5EF", "KN", "Putih"),
    ("KN-WHT-02", "Putih Broken", "#ECEAE0", "KN", "Putih"),
    ("KN-NAT-01", "Natural", "#E8DFC8", "KN", "Netral"),
    ("KN-CRM-01", "Krem", "#E7D8B5", "KN", "Netral"),
    ("KN-BLK-01", "Hitam Pekat", "#1A1A1A", "KN", "Hitam"),
    ("KN-GRY-01", "Abu Muda", "#B7BBC0", "KN", "Abu"),
    ("KN-GRY-02", "Abu Tua", "#5A5F66", "KN", "Abu"),
    ("KN-RED-01", "Merah Marun", "#7B1E22", "KN", "Merah"),
    ("KN-RED-02", "Merah Cabai", "#C1272D", "KN", "Merah"),
    ("KN-PNK-01", "Merah Muda", "#E8A0B0", "KN", "Merah Muda"),
    ("KN-ORG-01", "Oranye Kunyit", "#E08A2E", "KN", "Oranye"),
    ("KN-YLW-01", "Kuning Emas", "#E4B429", "KN", "Kuning"),
    ("KN-GLD-01", "Emas Antik", "#B8912E", "KN", "Emas"),
    ("KN-GRN-01", "Hijau Botol", "#1F5E3A", "KN", "Hijau"),
    ("KN-GRN-02", "Hijau Daun", "#4E8A4E", "KN", "Hijau"),
    ("KN-GRN-03", "Hijau Toska", "#1C7C74", "KN", "Hijau"),
    ("KN-BLU-01", "Biru Indigo", "#26415E", "KN", "Biru"),
    ("KN-BLU-02", "Biru Navy", "#1B2A4A", "KN", "Biru"),
    ("KN-BLU-03", "Biru Langit", "#5B8FC7", "KN", "Biru"),
    ("KN-BRN-01", "Coklat Sogan", "#6B4423", "KN", "Coklat"),
    ("KN-BRN-02", "Coklat Tanah", "#8A5A2B", "KN", "Coklat"),
    ("KN-PUR-01", "Ungu Terong", "#5B2A6B", "KN", "Ungu"),
    ("TCX-19-4052", "Classic Blue", "#0F4C81", "TCX", "Biru"),
    ("TCX-18-1663", "Fiery Red", "#C41E3A", "TCX", "Merah"),
    ("TCX-15-0343", "Greenery", "#88B04B", "TCX", "Hijau"),
    ("TCX-13-0647", "Illuminating", "#F5DF4D", "TCX", "Kuning"),
    ("TCX-17-1462", "Flame Orange", "#E25822", "TCX", "Oranye"),
    ("TPX-11-0601", "Bright White", "#F4F5F0", "TPX", "Putih"),
]


async def seed_color_library():
    """M0 — master warna Pantone-style (SHARED). Dipakai lintas menu (produk/POS/makloon)."""
    docs = []
    for code, name, hexv, system, family in COLOR_LIBRARY_SEED:
        docs.append({
            "id": f"col_{code.lower().replace('-', '_')}",
            "code": code, "name": name, "hex": hexv, "system": system,
            "family": family, "status": "active",
            "created_by": "Seed", "created_at": ago(days=200), "updated_at": ago(days=200),
        })
    await db.color_library.insert_many(docs)
    print(f"✅ Color Library seeded ({len(docs)} warna Pantone-style)")


async def seed_products():
    products = [
        {
            "id": "prod_batik_mega", "sku": "BTK-MEGA-001",
            "name": "Batik Mega Mendung Premium", "category": "Batik", "variant": "Premium",
            "color": "Biru-Coklat", "motif": "Mega Mendung", "grade": "A",
            "supplier": "Cirebon Craft", "base_unit": "yard", "price": 185000,
            "gramasi": 120, "lebar": 1.15,
            "image": "https://images.unsplash.com/photo-1761516659766-c092d4b1209d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDQ2MzR8MHwxfHNlYXJjaHw0fHxiYXRpayUyMGluZG9uZXNpYSUyMGZhYnJpYyUyMHRyYWRpdGlvbmFsJTIwdGV4dGlsZSUyMHBhdHRlcm58ZW58MHx8fHwxNzc4NjkyMDU3fDA&ixlib=rb-4.1.0&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "template_id": "tpl_batik_mega", "variant_label": "Biru-Coklat · Grade A",
            "created_at": ago(days=180), "updated_at": ago(days=2)
        },
        {
            "id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
            "name": "Tenun Ikat Garuda Premium", "category": "Tenun", "variant": "Premium",
            "color": "Merah-Emas", "motif": "Garuda", "grade": "A",
            "supplier": "NTT Weaving Co", "base_unit": "yard", "price": 225000,
            "gramasi": 210, "lebar": 1.20,
            "image": "https://images.unsplash.com/photo-1748141951488-9c9fb9603daf?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzV8MHwxfHNlYXJjaHwyfHx0ZW51biUyMGlrYXQlMjBpbmRvbmVzaWFuJTIwd292ZW4lMjB0ZXh0aWxlJTIwdHJhZGl0aW9uYWwlMjBmYWJyaWN8ZW58MHx8fHwxNzc4NjkyMDY1fDA&ixlib=rb-4.1.0&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "created_at": ago(days=175), "updated_at": ago(days=5)
        },
        {
            "id": "prod_lurik_classic", "sku": "LRK-CLSC-001",
            "name": "Lurik Klasik Solo", "category": "Lurik", "variant": "Klasik",
            "color": "Coklat-Putih", "motif": "Garis Vertikal", "grade": "A",
            "supplier": "Solo Weave", "base_unit": "yard", "price": 95000,
            "gramasi": 170, "lebar": 1.10,
            "image": "https://images.unsplash.com/photo-1761516659491-bf9a672d64c1?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDQ2MzR8MHwxfHNlYXJjaHwzfHxiYXRpayUyMGluZG9uZXNpYSUyMGZhYnJpYyUyMHRyYWRpdGlvbmFsJTIwdGV4dGlsZSUyMHBhdHRlcm58ZW58MHx8fHwxNzc4NjkyMDU3fDA&ixlib=rb-4.1.0&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "created_at": ago(days=170), "updated_at": ago(days=1)
        },
        {
            "id": "prod_songket_palembang", "sku": "SGK-PLB-001",
            "name": "Songket Palembang Benang Emas", "category": "Songket", "variant": "Premium",
            "color": "Emas-Hitam", "motif": "Bunga Cengkeh", "grade": "A+",
            "supplier": "Palembang Silk House", "base_unit": "yard", "price": 450000,
            "gramasi": 280, "lebar": 1.05,
            "image": "https://images.unsplash.com/photo-1594100618558-978ea7266c0a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NDh8MHwxfHNlYXJjaHwzfHxzb25na2V0JTIwZmFicmljJTIwZ29sZCUyMHRocmVhZCUyMGluZG9uZXNpYW4lMjBzaWxrJTIwdGV4dGlsZXxlbnwwfHx8fDE3Nzg2OTIwNjV8MA&ixlib=rb-4.1.0&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "created_at": ago(days=160), "updated_at": ago(days=3)
        },
        {
            "id": "prod_ulos_batak", "sku": "ULS-BTK-001",
            "name": "Ulos Batak Ragidup", "category": "Ulos", "variant": "Tradisional",
            "color": "Biru-Oranye", "motif": "Ragidup", "grade": "A",
            "supplier": "Toba Craft", "base_unit": "yard", "price": 320000,
            "gramasi": 230, "lebar": 0.90,
            "image": "https://images.unsplash.com/photo-1749367288395-f874bb54bc8a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzV8MHwxfHNlYXJjaHw0fHx0ZW51biUyMGlrYXQlMjBpbmRvbmVzaWFuJTIwd292ZW4lMjB0ZXh0aWxlJTIwdHJhZGl0aW9uYWwlMjBmYWJyaWN8ZW58MHx8fHwxNzc4NjkyMDY1fDA&ixlib=rb-4.1.0&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "created_at": ago(days=155), "updated_at": ago(days=7)
        },
        {
            "id": "prod_jumputan_palembang", "sku": "JMP-PLB-001",
            "name": "Jumputan Palembang Pelangi", "category": "Jumputan", "variant": "Standard",
            "color": "Multicolor", "motif": "Pelangi Jumputan", "grade": "B",
            "supplier": "Palembang Silk House", "base_unit": "yard", "price": 145000,
            "gramasi": 150, "lebar": 1.15,
            "image": "https://images.unsplash.com/photo-1761515315375-1315503bb3ce?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDQ2MzR8MHwxfHNlYXJjaHwyfHxiYXRpayUyMGluZG9uZXNpYSUyMGZhYnJpYyUyMHRyYWRpdGlvbmFsJTIwdGV4dGlsZSUyMHBhdHRlcm58ZW58MHx8fHwxNzc4NjkyMDU3fDA&ixlib=rb-4.1.0&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "created_at": ago(days=120), "updated_at": ago(days=10)
        },
        {
            "id": "prod_endek_bali", "sku": "ENK-BALI-001",
            "name": "Endek Bali Rangrang", "category": "Endek", "variant": "Premium",
            "color": "Merah-Coklat", "motif": "Rangrang", "grade": "A",
            "supplier": "Bali Weave Studio", "base_unit": "yard", "price": 280000,
            "gramasi": 195, "lebar": 1.15,
            "image": "https://images.unsplash.com/photo-1749367288413-994ae375d2f6?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzV8MHwxfHNlYXJjaHwzfHx0ZW51biUyMGlrYXQlMjBpbmRvbmVzaWFuJTIwd292ZW4lMjB0ZXh0aWxlJTIwdHJhZGl0aW9uYWwlMjBmYWJyaWN8ZW58MHx8fHwxNzc4NjkyMDY1fDA&ixlib=rb-4.1.0&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "template_id": "tpl_endek_bali", "variant_label": "Merah-Coklat · Grade A",
            "created_at": ago(days=100), "updated_at": ago(days=4)
        },
        # ── F-UOM — produk contoh SATUAN NON-METER (agar unit yard & kg terlihat
        # di seluruh aplikasi: master data, pembelian, POS, WMS, dokumen). ──
        {
            "id": "prod_denim_selvedge", "sku": "DNM-BDG-001",
            "name": "Denim Selvedge Bandung", "category": "Denim", "variant": "Premium",
            "color": "Biru-Indigo", "motif": "Polos", "grade": "A",
            "supplier": "Bandung Denim Mills", "base_unit": "yard", "price": 165000,
            "gramasi": 340, "lebar": 1.50,
            "image": "https://images.unsplash.com/photo-1565084888279-aca607ecce0c?crop=entropy&cs=srgb&fm=jpg&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "created_at": ago(days=95), "updated_at": ago(days=3)
        },
        {
            "id": "prod_benang_katun", "sku": "BNG-KTN-001",
            "name": "Benang Katun Cone (per Kg)", "category": "Benang", "variant": "Standard",
            "color": "Putih", "motif": "-", "grade": "A",
            "supplier": "Solo Yarn Co", "base_unit": "kg", "price": 78000,
            "gramasi": 0, "lebar": 0,
            "image": "https://images.unsplash.com/photo-1528150177508-7cc0c36cda5c?crop=entropy&cs=srgb&fm=jpg&q=85",
            "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "created_at": ago(days=88), "updated_at": ago(days=6)
        },
    ]
    # ── EPIC-VAR — varian SKU (warna/grade) yang berbagi template_id ──────────
    # Prinsip: 1 varian = 1 SKU. Grouping HANYA di tampilan katalog POS.
    # WMS/inventory/receiving tetap per-SKU (tidak berubah).
    _batik_img = products[0]["image"]
    _endek_img = products[6]["image"]
    # F3 — gambar BERBEDA per varian dalam 1 template (popup ganti gambar saat ganti varian)
    _batik_img_merah = "https://images.unsplash.com/photo-1761516659491-bf9a672d64c1?crop=entropy&cs=srgb&fm=jpg&q=85"
    _batik_img_hijau = "https://images.unsplash.com/photo-1761515315375-1315503bb3ce?crop=entropy&cs=srgb&fm=jpg&q=85"
    _endek_img_biru = "https://images.unsplash.com/photo-1748141951488-9c9fb9603daf?crop=entropy&cs=srgb&fm=jpg&q=85"
    _endek_img_ungu = "https://images.unsplash.com/photo-1749367288395-f874bb54bc8a?crop=entropy&cs=srgb&fm=jpg&q=85"
    products += [
        {"id": "prod_batik_mega_merah", "sku": "BTK-MEGA-002",
         "name": "Batik Mega Mendung Premium", "category": "Batik", "variant": "Premium",
         "color": "Merah-Marun", "motif": "Mega Mendung", "grade": "A",
         "supplier": "Cirebon Craft", "base_unit": "yard", "price": 185000,
         "gramasi": 120, "lebar": 1.15, "image": _batik_img_merah,
         "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
         "template_id": "tpl_batik_mega", "variant_label": "Merah-Marun · Grade A",
         "created_at": ago(days=120), "updated_at": ago(days=2)},
        {"id": "prod_batik_mega_hijau", "sku": "BTK-MEGA-003",
         "name": "Batik Mega Mendung Premium", "category": "Batik", "variant": "Eksklusif",
         "color": "Hijau-Emas", "motif": "Mega Mendung", "grade": "A+",
         "supplier": "Cirebon Craft", "base_unit": "yard", "price": 215000,
         "gramasi": 125, "lebar": 1.15, "image": _batik_img_hijau,
         "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
         "template_id": "tpl_batik_mega", "variant_label": "Hijau-Emas · Grade A+",
         "created_at": ago(days=110), "updated_at": ago(days=2)},
        {"id": "prod_endek_bali_biru", "sku": "ENK-BALI-002",
         "name": "Endek Bali Rangrang", "category": "Endek", "variant": "Premium",
         "color": "Biru-Putih", "motif": "Rangrang", "grade": "A",
         "supplier": "Bali Weave Studio", "base_unit": "yard", "price": 280000,
         "gramasi": 195, "lebar": 1.15, "image": _endek_img_biru,
         "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
         "template_id": "tpl_endek_bali", "variant_label": "Biru-Putih · Grade A",
         "created_at": ago(days=95), "updated_at": ago(days=4)},
        {"id": "prod_endek_bali_ungu", "sku": "ENK-BALI-003",
         "name": "Endek Bali Rangrang", "category": "Endek", "variant": "Eksklusif",
         "color": "Ungu-Emas", "motif": "Rangrang", "grade": "A+",
         "supplier": "Bali Weave Studio", "base_unit": "yard", "price": 320000,
         "gramasi": 200, "lebar": 1.15, "image": _endek_img_ungu,
         "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
         "template_id": "tpl_endek_bali", "variant_label": "Ungu-Emas · Grade A+",
         "created_at": ago(days=90), "updated_at": ago(days=4)},
    ]
    # F3 — deskripsi produk per-varian (additive). Tampil di popup detail POS;
    # berbeda per varian (warna/grade) → ganti varian = deskripsi & gambar berubah.
    for p in products:
        if not p.get("description"):
            p["description"] = (
                f"{p['name']} — motif {p['motif']}, warna {p['color']}, grade {p['grade']}. "
                f"Kain {p['category']} {str(p.get('variant', '')).lower()} dari {p['supplier']}; "
                f"gramasi {int(p.get('gramasi', 0))} gsm, lebar {p.get('lebar', 0)} m. "
                f"Dijual per {p.get('base_unit', 'yard')} — panjang tiap roll bervariasi."
            )
    # M0 — tahap bahan (stage) + snapshot warna dari color_library (best-effort).
    stage_by_cat = {"Benang": "yarn", "Grey": "grey"}
    color_docs = await db.color_library.find({}, {"_id": 0}).to_list(1000)
    for p in products:
        p.setdefault("stage", stage_by_cat.get(p.get("category"), "finished"))
        if not p.get("color_code"):
            token = str(p.get("color", "")).split("-")[0].strip().lower()
            match = next((c for c in color_docs if token and token in c["name"].lower()), None)
            if match:
                p["color_code"] = match["code"]
                p["color_name"] = match["name"]
                p["color_hex"] = match["hex"]
            else:
                p.setdefault("color_code", "")
                p.setdefault("color_name", "")
                p.setdefault("color_hex", "")
    # ── Fase A (PS-01/02/03 · D-02/D-20/D-22) — domain tekstil WAJIB lengkap ──
    # stage sudah diisi di atas; di sini: fabric_type (woven default D-20),
    # atribut benang untuk stage yarn, GSM/lebar untuk stage >= grey, lalu validasi.
    import domain_registry as dr
    for p in products:
        p.setdefault("fabric_type", "woven")
        if p.get("stage") == "yarn":
            p.setdefault("yarn_count", "30s")
            p.setdefault("yarn_count_system", "Ne")
        else:
            if not float(p.get("gramasi") or 0):
                p["gramasi"] = 180
            if not float(p.get("lebar") or 0):
                p["lebar"] = 1.15
        dr.apply_normalization(p)
        _chk = dr.validate_product(p)
        p["needs_review"] = _chk["needs_review"]
        p["needs_review_reasons"] = _chk["needs_review_reasons"]
        if _chk["errors"]:
            raise RuntimeError(f"Seed produk {p.get('sku')} melanggar domain Fase A: "
                               + " ".join(_chk["errors"]))
    await db.products.insert_many(products)
    # Depth #2b — reorder point/qty (replenishment). Beberapa produk sengaja
    # diberi reorder_point tinggi agar muncul saran replenishment untuk demo.
    reorder_map = {
        "prod_songket_palembang": (400.0, 600.0),
        "prod_ulos_batak":        (350.0, 500.0),
        "prod_endek_bali":        (300.0, 500.0),
    }
    await db.products.update_many({}, {"$set": {"reorder_point": 250.0, "reorder_qty": 500.0}})
    for pid, (rop, roq) in reorder_map.items():
        await db.products.update_one({"id": pid}, {"$set": {"reorder_point": rop, "reorder_qty": roq}})
    # PS-20 — DEMO produk eksklusif per sales ("PO sendiri"): Endek Bali hanya milik
    # Ayu Permatasari (user_sales_01). Sales lain tidak melihat kodenya di katalog/POS,
    # dan hanya Ayu (atau admin/manajer) yang boleh membuat SO untuknya.
    await db.products.update_many({}, {"$set": {"exclusivity": "umum", "owner_sales_ids": []}})
    await db.products.update_one(
        {"id": "prod_endek_bali"},
        {"$set": {"exclusivity": "sales_tertentu", "owner_sales_ids": ["user_sales_01"]}},
    )
    # ── FASE L (2026-08-18) — LINI PRODUK di data demo ──────────────────────
    # Lini = pembagian kerja MD (siapa yang mengerjakan, papan mana), BUKAN fisika
    # kain (`fabric_type`). Data demo diberi lini yang MASUK AKAL secara bisnis,
    # bukan hasil tebakan mesin: kain bermotif TENUN tetap `woven`, kain yang
    # dikerjakan lewat cetak/celup-motif masuk `printing`, kain rajut `knit`.
    # `seed_product_lines()` sudah menyiapkan masternya; di sini hanya penugasannya.
    await db.products.update_many({}, {"$set": {"line_code": "woven"}})
    await db.products.update_many(
        {"fabric_type": "knit"}, {"$set": {"line_code": "knit"}})
    await db.products.update_many(
        {"id": {"$in": ["prod_batik_mega", "prod_batik_mega_merah", "prod_batik_mega_hijau",
                        "prod_jumputan_palembang", "prod_kombinasi_batik_lurik"]}},
        {"$set": {"line_code": "printing"}})
    n_line = {code: await db.products.count_documents({"line_code": code})
              for code in ("woven", "knit", "printing")}
    print("✅ Products seeded (11 products incl. variants) + reorder points + "
          f"1 produk eksklusif (PS-20) + lini FASE L {n_line}")


async def seed_product_lines():
    """FASE L — master LINI PRODUK (berlapis: baris GLOBAL `entity_id="all"`).

    Kenapa di-seed dan tidak hanya mengandalkan benih `domain_registry`: benih
    hanya cadangan agar instalasi baru tidak mati. Yang dipakai layar & pagar
    adalah KOLEKSI-nya — kalau kosong, chip lini tidak akan pernah muncul di 12
    layar dan pemilik tidak bisa menambah lini keempat lewat layar.
    Nilai di sini WAJIB sama dengan `scripts/migrate_lini_produk.py::SEED_LINES`
    (satu daftar, dua pintu masuk: seed data demo & migrasi basis data lama).
    """
    rows = [
        {"id": "pline_woven", "code": "woven", "name": "Woven (Tenun)", "sort": 1,
         "fabric_type_required": "woven", "measure_unit_default": "yard",
         "stage_sequence": ["yarn", "tenun", "celup", "inspect"],
         "sample_types_default": ["labdip"],
         "notes": "Kain tenun polos/bermotif tenun. Satuan kendali meter (fabric_type woven)."},
        {"id": "pline_knit", "code": "knit", "name": "Knit (Rajut)", "sort": 2,
         "fabric_type_required": "knit", "measure_unit_default": "kg",
         "stage_sequence": ["yarn", "rajut", "celup", "inspect"],
         "sample_types_default": ["labdip"],
         "notes": "Kain rajut. Satuan kendali kg (fabric_type knit)."},
        {"id": "pline_printing", "code": "printing", "name": "Printing", "sort": 3,
         # SENGAJA kosong: kain print bisa woven maupun knit (INV-LINE-02 tak mengikat).
         "fabric_type_required": "", "measure_unit_default": "yard",
         "stage_sequence": ["proofing", "pfp", "screen", "printing", "inspect"],
         "sample_types_default": ["proofing", "labdip"],
         "notes": "Kain cetak (screen/rotary/digital). Bisa woven maupun knit."},
    ]
    await db.product_lines.insert_many([
        {**r, "entity_id": "all", "active": True,
         "created_at": ago(days=200), "updated_at": ago(days=200)} for r in rows])
    print(f"✅ Product Lines seeded ({len(rows)} lini GLOBAL: woven · knit · printing) — FASE L")


# FASE T — field master tahapan (sama dengan `entity_master_service.MASTERS["process-stages"]`).
PROCESS_STAGE_FIELDS = (
    "code", "name", "kind", "applies_to_lines", "seq", "active", "notes",
    "needs_vendor", "process_type", "target_use",
    "changes_stage", "from_stage", "to_stage", "tariff_basis_default",
    "material_flow", "material_flow_default",
)


async def seed_process_stages():
    """FASE T — master TAHAPAN PROSES (berlapis: baris GLOBAL `entity_id="all"`).

    Nilainya diambil LANGSUNG dari benih `domain_registry.PROCESS_STAGES` — bukan
    disalin ke sini. Alasannya persis kelas bug yang FASE T tutup: begitu daftar
    tahapan hidup di dua tempat, keduanya akan berbeda dalam beberapa sesi dan tidak
    ada yang tahu mana yang benar (lihat `PROCESS_LABELS` hardcode di frontend).
    `scripts/migrate_process_stages.py` membaca sumber yang sama untuk basis data lama.
    """
    import domain_registry as _dr
    rows = []
    for seed in _dr.enum_items("process_stage"):
        code = str(seed.get("code") or seed.get("value") or "").strip().lower()
        row = {k: seed.get(k) for k in PROCESS_STAGE_FIELDS if k in seed}
        row["code"] = code
        row["name"] = seed.get("name") or seed.get("label") or code
        row.setdefault("applies_to_lines", [])
        row.setdefault("notes", seed.get("description", "") or "")
        rows.append({**row, "id": f"pstg_{code}", "entity_id": "all", "active": True,
                     "created_by": "Seed", "created_at": ago(days=200),
                     "updated_at": ago(days=200)})
    await db.process_stages.insert_many(rows)
    n_screen = sum(1 for r in rows if r["code"] == "screen")
    print(f"✅ Process Stages seeded ({len(rows)} tahap GLOBAL: "
          f"{' · '.join(r['code'] for r in rows)}) — FASE T"
          + (" · termasuk `screen` (kasa) yang TIDAK mengubah kain" if n_screen else ""))


async def seed_customers():
    await db.customers.insert_many([
        {
            "id": "cust_toko_kain", "code": "CUST-0001", "name": "Toko Kain Sejahtera",
            "pic_name": "Pak Hendra", "phone": "081234567890", "email": "hendra@tokokain.id",
            "type": "Retailer", "city": "Jakarta", "status": "active",
            "created_by": "user_admin_01", "created_at": ago(days=170),
            "addresses": [{"id": "addr_001", "label": "Toko Utama", "recipient_name": "Pak Hendra",
                           "phone": "081234567890", "city": "Jakarta",
                           "address": "Jl. Mangga Besar Raya No. 45", "is_primary": True}]
        },
        {
            "id": "cust_butik_bali", "code": "CUST-0002", "name": "Butik Bali Indah",
            "pic_name": "Ibu Komang", "phone": "082345678901", "email": "komang@butikbali.id",
            "type": "Boutique", "city": "Denpasar", "status": "active",
            "created_by": "user_admin_01", "created_at": ago(days=165),
            "addresses": [{"id": "addr_002", "label": "Butik Seminyak", "recipient_name": "Ibu Komang",
                           "phone": "082345678901", "city": "Denpasar",
                           "address": "Jl. Seminyak No. 88", "is_primary": True}]
        },
        {
            "id": "cust_moda_surabaya", "code": "CUST-0003", "name": "Moda Surabaya Fashion",
            "pic_name": "Bapak Andi", "phone": "083456789012", "email": "andi@modasby.id",
            "type": "Wholesaler", "city": "Surabaya", "status": "active",
            "created_by": "user_admin_01", "created_at": ago(days=160),
            "addresses": [{"id": "addr_003", "label": "Gudang Pusat", "recipient_name": "Bapak Andi",
                           "phone": "083456789012", "city": "Surabaya",
                           "address": "Jl. Rungkut Industri No. 22", "is_primary": True}]
        },
        {
            "id": "cust_fashion_bandung", "code": "CUST-0004", "name": "Fashion Bandung Kencana",
            "pic_name": "Ibu Sari", "phone": "085678901234", "email": "sari@fashionbdg.id",
            "type": "Boutique", "city": "Bandung", "status": "active",
            "created_by": "user_admin_01", "created_at": ago(days=120),
            "addresses": [{"id": "addr_004", "label": "Toko Dago", "recipient_name": "Ibu Sari",
                           "phone": "085678901234", "city": "Bandung",
                           "address": "Jl. Dago No. 112, Bandung", "is_primary": True}]
        },
        {
            "id": "cust_textile_medan", "code": "CUST-0005", "name": "Tekstil Medan Jaya",
            "pic_name": "Pak Robert", "phone": "081345678905", "email": "robert@tekstilmedan.id",
            "type": "Wholesaler", "city": "Medan", "status": "active",
            "created_by": "user_admin_01", "created_at": ago(days=90),
            "addresses": [{"id": "addr_005", "label": "Gudang Utama", "recipient_name": "Pak Robert",
                           "phone": "081345678905", "city": "Medan",
                           "address": "Jl. Asia No. 78, Medan", "is_primary": True}]
        },
    ])
    # CRM-lite enrichment (KN_17): assigned_sales, segment, payment_profile, credit_limit, contacts
    crm_map = {
        "cust_toko_kain":      ("user_sales_01", "Ayu Permatasari", "Retail",      50_000_000, ["langganan"]),
        "cust_butik_bali":     ("user_sales_02", "Bima Saputra",     "VIP",         30_000_000, ["premium", "bali"]),
        "cust_moda_surabaya":  ("user_sales_01", "Ayu Permatasari", "Wholesale",  200_000_000, ["grosir"]),
        "cust_fashion_bandung":("user_sales_03", "Citra Lestari",    "Retail",      40_000_000, ["butik"]),
        "cust_textile_medan":  ("user_sales_02", "Bima Saputra",     "Distributor",150_000_000, ["distributor"]),
    }
    for cid, (sid, sname, seg, limit, tags) in crm_map.items():
        cust = await db.customers.find_one({"id": cid}, {"_id": 0, "pic_name": 1, "phone": 1, "email": 1})
        await db.customers.update_one({"id": cid}, {"$set": {
            "entity_id": "ent_ksc",
            "assigned_sales_id": sid,
            "assigned_sales_name": sname,
            "sales_pic": sname,
            "segment": seg,
            "tags": tags,
            "credit_limit": limit,
            "customer_group_id": "",
            "contacts": [{"name": (cust or {}).get("pic_name", ""), "role": "PIC",
                          "phone": (cust or {}).get("phone", ""), "email": (cust or {}).get("email", ""),
                          "is_primary": True}],
            "payment_profile": {"allowed_methods": ["tunai", "tempo", "dp"], "default_method": "tempo",
                                "term_days": 30, "dp_percent": 30, "installment_count": 0,
                                "installment_interval_days": 30},
        }})
    print("✅ Customers seeded (5 customers, CRM-lite enriched)")


async def seed_crm():
    """Sales targets + incentive schemes (KN_17 §6) for current period — demo."""
    from datetime import datetime, timezone
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    default_tiers = [
        {"min_achievement": 0, "rate": 1.0},
        {"min_achievement": 80, "rate": 1.5},
        {"min_achievement": 100, "rate": 2.5},
        {"min_achievement": 120, "rate": 3.5},
    ]
    targets = [
        ("user_sales_01", "Ayu Permatasari", 250_000_000, 200_000_000, 2),
        ("user_sales_02", "Bima Saputra",    300_000_000, 240_000_000, 3),
        ("user_sales_03", "Citra Lestari",   150_000_000, 120_000_000, 1),
    ]
    # FASE E-0 (L12) — entitas target/insentif WAJIB mengikuti entitas HOME salesnya.
    # Bug lama: semua di-stempel "ent_ksc" sehingga target & insentif Citra Lestari
    # (sales CV Kanda Suka) tercatat sebagai beban PT Kain Suka Cita.
    home_of = {u["id"]: u.get("home_entity_id") or "ent_ksc"
               async for u in db.users.find({"role": "sales"},
                                            {"_id": 0, "id": 1, "home_entity_id": 1})}
    for sid, sname, tsales, tcoll, tnew in targets:
        sales_entity = home_of.get(sid, "ent_ksc")
        await db.sales_targets.insert_one({
            "id": f"starg_{sid}_{period}", "sales_id": sid, "sales_name": sname,
            "entity_id": sales_entity, "period_type": "month", "period": period,
            "target_sales_amount": tsales, "target_collection_amount": tcoll,
            "target_new_customers": tnew, "target_focus_products": [], "notes": "Target demo",
            "created_by": "Dewi Rahayu", "created_at": ago(days=5),
        })
        await db.sales_incentives.insert_one({
            "id": f"sinc_{sid}_{period}", "sales_id": sid, "sales_name": sname,
            "entity_id": sales_entity, "period": period, "basis": "collection",
            "tiers": default_tiers, "bonus_new_customer": 250_000, "bonus_focus_product": 0,
            "notes": "Skema komisi: pencairan + tiered (S36)", "status": "draft",
            "created_by": "Dewi Rahayu", "created_at": ago(days=5),
        })
    print(f"✅ CRM seeded (sales_targets + incentives for {period})")


async def seed_inventory_initial():
    """Seed initial inventory balances before receiving history."""
    balances = [
        # Jakarta
        {"id": new_id("bal"), "product_id": "prod_batik_mega", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 485, "reserved_qty": 50, "available_qty": 435, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(hours=2)},
        {"id": new_id("bal"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 320, "reserved_qty": 30, "available_qty": 290, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(hours=3)},
        {"id": new_id("bal"), "product_id": "prod_songket_palembang", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 155, "reserved_qty": 20, "available_qty": 135, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(hours=1)},
        {"id": new_id("bal"), "product_id": "prod_ulos_batak", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 95, "reserved_qty": 0, "available_qty": 95, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=1)},
        {"id": new_id("bal"), "product_id": "prod_endek_bali", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 180, "reserved_qty": 0, "available_qty": 180, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=2)},
        # Bandung
        {"id": new_id("bal"), "product_id": "prod_batik_mega", "warehouse_id": "wh_bandung",
         "on_hand_qty": 340, "reserved_qty": 20, "available_qty": 320, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(hours=5)},
        {"id": new_id("bal"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_bandung",
         "on_hand_qty": 620, "reserved_qty": 40, "available_qty": 580, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(hours=6)},
        {"id": new_id("bal"), "product_id": "prod_jumputan_palembang", "warehouse_id": "wh_bandung",
         "on_hand_qty": 210, "reserved_qty": 0, "available_qty": 210, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=3)},
        # Surabaya
        {"id": new_id("bal"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_surabaya",
         "on_hand_qty": 245, "reserved_qty": 35, "available_qty": 210, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(hours=4)},
        {"id": new_id("bal"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_surabaya",
         "on_hand_qty": 410, "reserved_qty": 25, "available_qty": 385, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(hours=8)},
        {"id": new_id("bal"), "product_id": "prod_ulos_batak", "warehouse_id": "wh_surabaya",
         "on_hand_qty": 140, "reserved_qty": 0, "available_qty": 140, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=2)},
        {"id": new_id("bal"), "product_id": "prod_endek_bali", "warehouse_id": "wh_surabaya",
         "on_hand_qty": 75, "reserved_qty": 0, "available_qty": 75, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=4)},
        # ── EPIC-VAR — stok awal SKU varian (Jakarta, available-only) ──
        {"id": new_id("bal"), "product_id": "prod_batik_mega_merah", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 240, "reserved_qty": 0, "available_qty": 240, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=2)},
        {"id": new_id("bal"), "product_id": "prod_batik_mega_hijau", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 160, "reserved_qty": 0, "available_qty": 160, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=2)},
        {"id": new_id("bal"), "product_id": "prod_endek_bali_biru", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 150, "reserved_qty": 0, "available_qty": 150, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=3)},
        {"id": new_id("bal"), "product_id": "prod_endek_bali_ungu", "warehouse_id": "wh_jakarta",
         "on_hand_qty": 110, "reserved_qty": 0, "available_qty": 110, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=3)},
        # ── F-UOM — stok awal produk non-meter (yard & kg) ──
        {"id": new_id("bal"), "product_id": "prod_denim_selvedge", "warehouse_id": "wh_bandung",
         "on_hand_qty": 300, "reserved_qty": 0, "available_qty": 300, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=2)},
        {"id": new_id("bal"), "product_id": "prod_benang_katun", "warehouse_id": "wh_surabaya",
         "on_hand_qty": 90, "reserved_qty": 0, "available_qty": 90, "blocked_qty": 0,
         "picked_qty": 0, "in_transit_qty": 0, "updated_at": ago(days=2)},
    ]
    await db.inventory_balances.insert_many(balances)
    print(f"✅ Inventory balances seeded ({len(balances)} records)")


async def seed_inventory_movements_initial():
    """Initial stock movements."""
    movements = [
        # Jakarta initial stocks (3 months ago)
        {"id": new_id("mov"), "product_id": "prod_batik_mega", "warehouse_id": "wh_jakarta",
         "movement_type": "initial_stock", "quantity": 300, "unit": "yard",
         "batch": "BTK-2025-001", "lot": "LOT-001", "roll_id": "ROLL-001",
         "source_document": "INIT-001", "notes": "Initial stock", "created_by": "user_admin_01",
         "timestamp": ago(days=180)},
        {"id": new_id("mov"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_jakarta",
         "movement_type": "initial_stock", "quantity": 200, "unit": "yard",
         "batch": "TNI-2025-001", "lot": "LOT-001", "roll_id": "ROLL-002",
         "source_document": "INIT-001", "notes": "Initial stock", "created_by": "user_admin_01",
         "timestamp": ago(days=180)},
        {"id": new_id("mov"), "product_id": "prod_songket_palembang", "warehouse_id": "wh_jakarta",
         "movement_type": "initial_stock", "quantity": 80, "unit": "yard",
         "batch": "SGK-2025-001", "lot": "LOT-001", "roll_id": "ROLL-003",
         "source_document": "INIT-001", "notes": "Initial stock", "created_by": "user_admin_01",
         "timestamp": ago(days=180)},
        # Bandung initial stocks
        {"id": new_id("mov"), "product_id": "prod_batik_mega", "warehouse_id": "wh_bandung",
         "movement_type": "initial_stock", "quantity": 250, "unit": "yard",
         "batch": "BTK-2025-001", "lot": "LOT-002", "roll_id": "ROLL-010",
         "source_document": "INIT-001", "notes": "Initial stock", "created_by": "user_admin_01",
         "timestamp": ago(days=180)},
        {"id": new_id("mov"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_bandung",
         "movement_type": "initial_stock", "quantity": 400, "unit": "yard",
         "batch": "LRK-2025-001", "lot": "LOT-001", "roll_id": "ROLL-011",
         "source_document": "INIT-001", "notes": "Initial stock", "created_by": "user_admin_01",
         "timestamp": ago(days=180)},
        # Surabaya initial stocks
        {"id": new_id("mov"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_surabaya",
         "movement_type": "initial_stock", "quantity": 150, "unit": "yard",
         "batch": "TNI-2025-001", "lot": "LOT-002", "roll_id": "ROLL-020",
         "source_document": "INIT-001", "notes": "Initial stock", "created_by": "user_admin_01",
         "timestamp": ago(days=180)},
        {"id": new_id("mov"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_surabaya",
         "movement_type": "initial_stock", "quantity": 300, "unit": "yard",
         "batch": "LRK-2025-001", "lot": "LOT-002", "roll_id": "ROLL-021",
         "source_document": "INIT-001", "notes": "Initial stock", "created_by": "user_admin_01",
         "timestamp": ago(days=180)},
        # ── EPIC-VAR — initial_stock SKU varian (memberi lot bermakna utk rolls) ──
        {"id": new_id("mov"), "product_id": "prod_batik_mega_merah", "warehouse_id": "wh_jakarta",
         "movement_type": "initial_stock", "quantity": 240, "unit": "yard",
         "batch": "BTK-V-001", "lot": "LOT-V01", "roll_id": "ROLL-V01",
         "source_document": "INIT-V", "notes": "Initial stock varian", "created_by": "user_admin_01",
         "timestamp": ago(days=120)},
        {"id": new_id("mov"), "product_id": "prod_batik_mega_hijau", "warehouse_id": "wh_jakarta",
         "movement_type": "initial_stock", "quantity": 160, "unit": "yard",
         "batch": "BTK-V-002", "lot": "LOT-V02", "roll_id": "ROLL-V02",
         "source_document": "INIT-V", "notes": "Initial stock varian", "created_by": "user_admin_01",
         "timestamp": ago(days=110)},
        {"id": new_id("mov"), "product_id": "prod_endek_bali_biru", "warehouse_id": "wh_jakarta",
         "movement_type": "initial_stock", "quantity": 150, "unit": "yard",
         "batch": "ENK-V-001", "lot": "LOT-V03", "roll_id": "ROLL-V03",
         "source_document": "INIT-V", "notes": "Initial stock varian", "created_by": "user_admin_01",
         "timestamp": ago(days=95)},
        {"id": new_id("mov"), "product_id": "prod_endek_bali_ungu", "warehouse_id": "wh_jakarta",
         "movement_type": "initial_stock", "quantity": 110, "unit": "yard",
         "batch": "ENK-V-002", "lot": "LOT-V04", "roll_id": "ROLL-V04",
         "source_document": "INIT-V", "notes": "Initial stock varian", "created_by": "user_admin_01",
         "timestamp": ago(days=95)},
        # ── F-UOM — initial_stock produk non-meter (unit mengikuti base_unit produk) ──
        {"id": new_id("mov"), "product_id": "prod_denim_selvedge", "warehouse_id": "wh_bandung",
         "movement_type": "initial_stock", "quantity": 300, "unit": "yard",
         "batch": "DNM-2025-001", "lot": "LOT-UOM01", "roll_id": "ROLL-UOM01",
         "source_document": "INIT-UOM", "notes": "Initial stock denim (yard)", "created_by": "user_admin_01",
         "timestamp": ago(days=95)},
        {"id": new_id("mov"), "product_id": "prod_benang_katun", "warehouse_id": "wh_surabaya",
         "movement_type": "initial_stock", "quantity": 90, "unit": "kg",
         "batch": "BNG-2025-001", "lot": "LOT-UOM02", "roll_id": "ROLL-UOM02",
         "source_document": "INIT-UOM", "notes": "Initial stock benang (kg)", "created_by": "user_admin_01",
         "timestamp": ago(days=88)},
    ]
    await db.inventory_movements.insert_many(movements)
    print(f"✅ Initial inventory movements seeded ({len(movements)})")


async def seed_purchase_orders():
    """Seed realistic POs with completed inbound receiving history."""

    # PO-00001 — Completed 45 days ago (Batik Mega Mendung from Cirebon Craft → Jakarta)
    po1_id = "po_001"
    task1a_id = new_id("wms")
    task1b_id = new_id("wms")
    await db.purchase_orders.insert_one({
        "id": po1_id, "po_number": "PO-00001",
        "supplier_name": "Cirebon Craft", "supplier_contact": "Pak Wahyu | 081234500001",
        "warehouse_id": "wh_jakarta",
        "status": "completed",
        "items": [
            {"product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
             "product_name": "Batik Mega Mendung Premium",
             "quantity": 150.0, "received_qty": 150.0, "unit": "yard", "price": 165000,
             "status": "completed", "inbound_task_id": task1a_id},
            {"product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
             "product_name": "Songket Palembang Benang Emas",
             "quantity": 60.0, "received_qty": 60.0, "unit": "yard", "price": 420000,
             "status": "completed", "inbound_task_id": task1b_id},
        ],
        "expected_delivery_date": ago(days=46),
        "notes": "Pengiriman pertama batch 2025 Q1",
        "created_by": "Budi Santoso", "created_at": ago(days=50),
        "completed_at": ago(days=44),
    })
    # WMS tasks for PO-00001
    await db.wms_tasks.insert_many([
        {
            "id": task1a_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po1_id, "po_number": "PO-00001",
            "product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
            "product_name": "Batik Mega Mendung Premium",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
            "expected_qty": 150.0, "received_qty": 150.0, "quantity": 150.0,
            "unit": "yard", "status": "completed",
            "supplier_name": "Cirebon Craft",
            "bin_id": "A1-01", "batch": "BTK-2025-003", "lot": "LOT-003",
            "scan_log": [
                {"scan_time": ago(days=45, hours=2), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 75.0, "batch": "BTK-2025-003", "lot": "LOT-003",
                 "roll_id": "ROLL-031", "bin_id": "A1-01"},
                {"scan_time": ago(days=45, hours=1), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 75.0, "batch": "BTK-2025-003", "lot": "LOT-003",
                 "roll_id": "ROLL-032", "bin_id": "A1-01"},
            ],
            "escalation": None,
            "created_at": ago(days=50), "updated_at": ago(days=44),
            "completed_at": ago(days=44),
        },
        {
            "id": task1b_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po1_id, "po_number": "PO-00001",
            "product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
            "product_name": "Songket Palembang Benang Emas",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
            "expected_qty": 60.0, "received_qty": 60.0, "quantity": 60.0,
            "unit": "yard", "status": "completed",
            "supplier_name": "Cirebon Craft",
            "bin_id": "A2-01", "batch": "SGK-2025-002", "lot": "LOT-002",
            "scan_log": [
                {"scan_time": ago(days=45, hours=1, minutes=30), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 60.0, "batch": "SGK-2025-002", "lot": "LOT-002",
                 "roll_id": "ROLL-033", "bin_id": "A2-01"},
            ],
            "escalation": None,
            "created_at": ago(days=50), "updated_at": ago(days=44),
            "completed_at": ago(days=44),
        },
    ])
    # Inventory movements from PO-00001 receiving
    await db.inventory_movements.insert_many([
        {"id": new_id("mov"), "product_id": "prod_batik_mega", "warehouse_id": "wh_jakarta",
         "movement_type": "inbound_receiving", "quantity": 150.0, "unit": "yard",
         "batch": "BTK-2025-003", "lot": "LOT-003", "roll_id": "ROLL-031/032",
         "source_document": "PO-00001", "notes": "Receiving completed by Eko Prasetyo",
         "created_by": "user_wh_01", "timestamp": ago(days=44)},
        {"id": new_id("mov"), "product_id": "prod_songket_palembang", "warehouse_id": "wh_jakarta",
         "movement_type": "inbound_receiving", "quantity": 60.0, "unit": "yard",
         "batch": "SGK-2025-002", "lot": "LOT-002", "roll_id": "ROLL-033",
         "source_document": "PO-00001", "notes": "Receiving completed by Eko Prasetyo",
         "created_by": "user_wh_01", "timestamp": ago(days=44)},
    ])

    # PO-00002 — Completed 30 days ago (Tenun Ikat & Lurik from NTT/Solo → Bandung + Surabaya)
    po2_id = "po_002"
    task2a_id = new_id("wms")
    task2b_id = new_id("wms")
    await db.purchase_orders.insert_one({
        "id": po2_id, "po_number": "PO-00002",
        "supplier_name": "NTT Weaving Co", "supplier_contact": "Ibu Agnes | 082345600002",
        "warehouse_id": "wh_surabaya",
        "status": "completed",
        "items": [
            {"product_id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
             "product_name": "Tenun Ikat Garuda Premium",
             "quantity": 100.0, "received_qty": 100.0, "unit": "yard", "price": 200000,
             "status": "completed", "inbound_task_id": task2a_id},
            {"product_id": "prod_ulos_batak", "sku": "ULS-BTK-001",
             "product_name": "Ulos Batak Ragidup",
             "quantity": 80.0, "received_qty": 80.0, "unit": "yard", "price": 295000,
             "status": "completed", "inbound_task_id": task2b_id},
        ],
        "expected_delivery_date": ago(days=31),
        "notes": "Pengiriman batch 2025 Q1 - NTT Collection",
        "created_by": "Budi Santoso", "created_at": ago(days=35),
        "completed_at": ago(days=29),
    })
    await db.wms_tasks.insert_many([
        {
            "id": task2a_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po2_id, "po_number": "PO-00002",
            "product_id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
            "product_name": "Tenun Ikat Garuda Premium",
            "warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
            "expected_qty": 100.0, "received_qty": 100.0, "quantity": 100.0,
            "unit": "yard", "status": "completed",
            "supplier_name": "NTT Weaving Co",
            "bin_id": "A1-01", "batch": "TNI-2025-002", "lot": "LOT-002",
            "scan_log": [
                {"scan_time": ago(days=30, hours=3), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 50.0, "batch": "TNI-2025-002", "lot": "LOT-002",
                 "roll_id": "ROLL-041", "bin_id": "A1-01"},
                {"scan_time": ago(days=30, hours=2), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 50.0, "batch": "TNI-2025-002", "lot": "LOT-002",
                 "roll_id": "ROLL-042", "bin_id": "A1-01"},
            ],
            "escalation": None,
            "created_at": ago(days=35), "updated_at": ago(days=29),
            "completed_at": ago(days=29),
        },
        {
            "id": task2b_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po2_id, "po_number": "PO-00002",
            "product_id": "prod_ulos_batak", "sku": "ULS-BTK-001",
            "product_name": "Ulos Batak Ragidup",
            "warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
            "expected_qty": 80.0, "received_qty": 80.0, "quantity": 80.0,
            "unit": "yard", "status": "completed",
            "supplier_name": "NTT Weaving Co",
            "bin_id": "A1-02", "batch": "ULS-2025-001", "lot": "LOT-001",
            "scan_log": [
                {"scan_time": ago(days=30, hours=1, minutes=30), "scanned_by": "Fitri Handayani",
                 "actual_qty": 80.0, "batch": "ULS-2025-001", "lot": "LOT-001",
                 "roll_id": "ROLL-043", "bin_id": "A1-02"},
            ],
            "escalation": None,
            "created_at": ago(days=35), "updated_at": ago(days=29),
            "completed_at": ago(days=29),
        },
    ])
    await db.inventory_movements.insert_many([
        {"id": new_id("mov"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_surabaya",
         "movement_type": "inbound_receiving", "quantity": 100.0, "unit": "yard",
         "batch": "TNI-2025-002", "lot": "LOT-002", "roll_id": "ROLL-041/042",
         "source_document": "PO-00002", "notes": "Receiving completed by Eko Prasetyo",
         "created_by": "user_wh_01", "timestamp": ago(days=29)},
        {"id": new_id("mov"), "product_id": "prod_ulos_batak", "warehouse_id": "wh_surabaya",
         "movement_type": "inbound_receiving", "quantity": 80.0, "unit": "yard",
         "batch": "ULS-2025-001", "lot": "LOT-001", "roll_id": "ROLL-043",
         "source_document": "PO-00002", "notes": "Receiving completed by Fitri Handayani",
         "created_by": "user_wh_02", "timestamp": ago(days=29)},
    ])

    # PO-00003 — Completed 15 days ago (Lurik & Endek → Bandung, with escalation history)
    po3_id = "po_003"
    task3a_id = new_id("wms")
    task3b_id = new_id("wms")
    await db.purchase_orders.insert_one({
        "id": po3_id, "po_number": "PO-00003",
        "supplier_name": "Solo Weave", "supplier_contact": "Pak Joko | 085012300003",
        "warehouse_id": "wh_bandung",
        "status": "completed",
        "items": [
            {"product_id": "prod_lurik_classic", "sku": "LRK-CLSC-001",
             "product_name": "Lurik Klasik Solo",
             "quantity": 200.0, "received_qty": 180.0, "unit": "yard", "price": 88000,
             "status": "completed", "inbound_task_id": task3a_id,
             "escalation_note": "Supplier kirim 180m, bukan 200m. Manager adjust qty."},
            {"product_id": "prod_endek_bali", "sku": "ENK-BALI-001",
             "product_name": "Endek Bali Rangrang",
             "quantity": 100.0, "received_qty": 100.0, "unit": "yard", "price": 255000,
             "status": "completed", "inbound_task_id": task3b_id},
        ],
        "expected_delivery_date": ago(days=16),
        "notes": "Batch 2025 Q1 - Lurik & Endek Bali",
        "created_by": "Budi Santoso", "created_at": ago(days=20),
        "completed_at": ago(days=14),
    })
    await db.wms_tasks.insert_many([
        {
            "id": task3a_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po3_id, "po_number": "PO-00003",
            "product_id": "prod_lurik_classic", "sku": "LRK-CLSC-001",
            "product_name": "Lurik Klasik Solo",
            "warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo",
            "expected_qty": 180.0, "received_qty": 180.0, "quantity": 180.0,
            "unit": "yard", "status": "completed",
            "supplier_name": "Solo Weave",
            "bin_id": "A1-01", "batch": "LRK-2025-002", "lot": "LOT-002",
            "scan_log": [
                {"scan_time": ago(days=15, hours=4), "scanned_by": "Fitri Handayani",
                 "actual_qty": 90.0, "batch": "LRK-2025-002", "lot": "LOT-002",
                 "roll_id": "ROLL-051", "bin_id": "A1-01"},
                {"scan_time": ago(days=15, hours=3, minutes=30), "scanned_by": "Fitri Handayani",
                 "actual_qty": 90.0, "batch": "LRK-2025-002", "lot": "LOT-002",
                 "roll_id": "ROLL-052", "bin_id": "A1-01"},
            ],
            "escalation": {
                "escalated_at": ago(days=15, hours=5),
                "escalated_by": "Fitri Handayani",
                "reason": "Supplier hanya mengirim 180m dari 200m yang dipesan. Fisik sudah dihitung ulang.",
                "status": "resolved",
                "resolved_at": ago(days=15, hours=2),
                "resolved_by": "Dewi Rahayu",
                "resolution_notes": "Dikonfirmasi supplier kekurangan material. Adjust expected qty ke 180m dan proceed complete.",
                "adjusted_qty": 180.0,
            },
            "created_at": ago(days=20), "updated_at": ago(days=14),
            "completed_at": ago(days=14),
        },
        {
            "id": task3b_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po3_id, "po_number": "PO-00003",
            "product_id": "prod_endek_bali", "sku": "ENK-BALI-001",
            "product_name": "Endek Bali Rangrang",
            "warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo",
            "expected_qty": 100.0, "received_qty": 100.0, "quantity": 100.0,
            "unit": "yard", "status": "completed",
            "supplier_name": "Solo Weave",
            "bin_id": "A1-02", "batch": "ENK-2025-001", "lot": "LOT-001",
            "scan_log": [
                {"scan_time": ago(days=15, hours=2, minutes=45), "scanned_by": "Fitri Handayani",
                 "actual_qty": 100.0, "batch": "ENK-2025-001", "lot": "LOT-001",
                 "roll_id": "ROLL-053", "bin_id": "A1-02"},
            ],
            "escalation": None,
            "created_at": ago(days=20), "updated_at": ago(days=14),
            "completed_at": ago(days=14),
        },
    ])
    await db.inventory_movements.insert_many([
        {"id": new_id("mov"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_bandung",
         "movement_type": "inbound_receiving", "quantity": 180.0, "unit": "yard",
         "batch": "LRK-2025-002", "lot": "LOT-002", "roll_id": "ROLL-051/052",
         "source_document": "PO-00003", "notes": "Receiving completed (escalated & resolved) by Fitri Handayani",
         "created_by": "user_wh_02", "timestamp": ago(days=14)},
        {"id": new_id("mov"), "product_id": "prod_endek_bali", "warehouse_id": "wh_bandung",
         "movement_type": "inbound_receiving", "quantity": 100.0, "unit": "yard",
         "batch": "ENK-2025-001", "lot": "LOT-001", "roll_id": "ROLL-053",
         "source_document": "PO-00003", "notes": "Receiving completed by Fitri Handayani",
         "created_by": "user_wh_02", "timestamp": ago(days=14)},
    ])

    # PO-00004 — Currently in receiving (started 3 days ago, partially scanned)
    po4_id = "po_004"
    task4a_id = new_id("wms")
    task4b_id = new_id("wms")
    await db.purchase_orders.insert_one({
        "id": po4_id, "po_number": "PO-00004",
        "supplier_name": "Palembang Silk House", "supplier_contact": "Ibu Ratna | 081278900004",
        "warehouse_id": "wh_jakarta",
        "status": "receiving",
        "items": [
            {"product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
             "product_name": "Songket Palembang Benang Emas",
             "quantity": 75.0, "received_qty": 40.0, "unit": "yard", "price": 430000,
             "status": "receiving", "inbound_task_id": task4a_id},
            {"product_id": "prod_jumputan_palembang", "sku": "JMP-PLB-001",
             "product_name": "Jumputan Palembang Pelangi",
             "quantity": 120.0, "received_qty": 0.0, "unit": "yard", "price": 130000,
             "status": "waiting_goods", "inbound_task_id": task4b_id},
        ],
        "expected_delivery_date": ago(days=2),
        "notes": "Batch 2025 Q2 - Palembang Collection. Pengiriman dalam 2 tahap.",
        "created_by": "Budi Santoso", "created_at": ago(days=7),
    })
    await db.wms_tasks.insert_many([
        {
            "id": task4a_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po4_id, "po_number": "PO-00004",
            "product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
            "product_name": "Songket Palembang Benang Emas",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
            "expected_qty": 75.0, "received_qty": 40.0, "quantity": 0.0,
            "unit": "yard", "status": "receiving",
            "supplier_name": "Palembang Silk House",
            "bin_id": "B1-01", "batch": "SGK-2025-003", "lot": "LOT-003",
            "scan_log": [
                {"scan_time": ago(days=3, hours=2), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 40.0, "batch": "SGK-2025-003", "lot": "LOT-003",
                 "roll_id": "ROLL-061", "bin_id": "B1-01"},
            ],
            "escalation": None,
            "created_at": ago(days=7), "updated_at": ago(days=3),
        },
        {
            "id": task4b_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po4_id, "po_number": "PO-00004",
            "product_id": "prod_jumputan_palembang", "sku": "JMP-PLB-001",
            "product_name": "Jumputan Palembang Pelangi",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
            "expected_qty": 120.0, "received_qty": 0.0, "quantity": 0.0,
            "unit": "yard", "status": "waiting_goods",
            "supplier_name": "Palembang Silk House",
            "scan_log": [],
            "escalation": None,
            "created_at": ago(days=7), "updated_at": ago(days=7),
        },
    ])

    # PO-00005 — Pending (just created today, awaiting delivery — task siap untuk demo)
    po5_id = "po_005"
    task5a_id = new_id("wms")
    await db.purchase_orders.insert_one({
        "id": po5_id, "po_number": "PO-00005",
        "supplier_name": "Toba Craft", "supplier_contact": "Pak Maruli | 081156700005",
        "warehouse_id": "wh_surabaya",
        "status": "receiving",
        "items": [
            {"product_id": "prod_ulos_batak", "sku": "ULS-BTK-001",
             "product_name": "Ulos Batak Ragidup",
             "quantity": 100.0, "received_qty": 0.0, "unit": "yard", "price": 305000,
             "status": "receiving", "inbound_task_id": task5a_id},
        ],
        "expected_delivery_date": ago(hours=-12),
        "notes": "Restock Ulos untuk permintaan pernikahan adat Batak. Barang sudah sampai.",
        "created_by": "Budi Santoso", "created_at": ago(hours=18),
    })
    await db.wms_tasks.insert_one({
        "id": task5a_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
        "po_id": po5_id, "po_number": "PO-00005",
        "product_id": "prod_ulos_batak", "sku": "ULS-BTK-001",
        "product_name": "Ulos Batak Ragidup",
        "warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
        "expected_qty": 100.0, "received_qty": 0.0, "quantity": 0.0,
        "unit": "yard", "status": "created",
        "supplier_name": "Toba Craft",
        "scan_log": [],
        "escalation": None,
        "created_at": ago(hours=18), "updated_at": ago(hours=2),
    })

    # PO-00006 — Newly created with fresh receiving task (status: created, ready for demo)
    po6_id = "po_006"
    task6a_id = new_id("wms")
    await db.purchase_orders.insert_one({
        "id": po6_id, "po_number": "PO-00006",
        "supplier_name": "Bali Weave Studio", "supplier_contact": "Pak Gede | 081256700006",
        "warehouse_id": "wh_jakarta",
        "status": "receiving",
        "items": [
            {"product_id": "prod_endek_bali", "sku": "ENK-BALI-001",
             "product_name": "Endek Bali Rangrang",
             "quantity": 80.0, "received_qty": 0.0, "unit": "yard", "price": 270000,
             "status": "receiving", "inbound_task_id": task6a_id},
        ],
        "expected_delivery_date": ago(hours=-2),
        "notes": "Restock Endek Bali untuk koleksi musim semi. Barang baru tiba di gudang.",
        "created_by": "Budi Santoso", "created_at": ago(hours=8),
    })
    await db.wms_tasks.insert_one({
        "id": task6a_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
        "po_id": po6_id, "po_number": "PO-00006",
        "product_id": "prod_endek_bali", "sku": "ENK-BALI-001",
        "product_name": "Endek Bali Rangrang",
        "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
        "expected_qty": 80.0, "received_qty": 0.0, "quantity": 0.0,
        "unit": "yard", "status": "created",
        "supplier_name": "Bali Weave Studio",
        "scan_log": [],
        "escalation": None,
        "created_at": ago(hours=8), "updated_at": ago(hours=1),
    })

    print("✅ Purchase Orders seeded (PO-00001 to PO-00006 with inbound tasks)")


async def seed_sales_orders():
    """Seed realistic Sales Orders in various stages."""

    # SO-0001 — Dispatched 40 days ago (completed flow)
    so1_id = "so_001"
    ob1a_id = new_id("wms")
    await db.sales_orders.insert_one({
        "id": so1_id, "number": "SO-0001",
        "customer_id": "cust_toko_kain", "customer_name": "Toko Kain Sejahtera",
        "customer_city": "Jakarta",
        "shipping_address": {"city": "Jakarta", "address": "Jl. Mangga Besar Raya No. 45",
                              "recipient_name": "Pak Hendra", "phone": "081234567890"},
        "items": [
            {"product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
             "product_name": "Batik Mega Mendung Premium", "quantity": 30.0, "unit": "yard",
             "price": 185000, "subtotal": 5550000,
             "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara"},
            {"product_id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
             "product_name": "Tenun Ikat Garuda Premium", "quantity": 20.0, "unit": "yard",
             "price": 225000, "subtotal": 4500000,
             "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara"},
        ],
        "total_amount": 10050000, "tax": 0, "grand_total": 10050000,
        "status": "dispatched",
        "payment_status": "paid",
        "allocations": [
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_batik_mega", "quantity": 30.0},
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_tenun_ikat", "quantity": 20.0},
        ],
        "created_by": "user_sales_01", "created_at": ago(days=45),
        "approved_at": ago(days=44), "approved_by": "user_manager_01",
        "confirmed_at": ago(days=43), "confirmed_by": "user_manager_01",
        "dispatched_at": ago(days=40),
        "notes": "Order reguler bulanan - Toko Kain Sejahtera",
    })
    await db.wms_tasks.insert_one({
        "id": ob1a_id, "flow_type": "outbound", "source_type": "sales_order", "task_subtype": "picking",
        "order_id": so1_id, "order_number": "SO-0001",
        "customer_name": "Toko Kain Sejahtera",
        "product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
        "product_name": "Batik Mega Mendung Premium",
        "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
        "quantity": 30.0, "picked_qty": 30.0, "unit": "yard",
        "status": "dispatched",
        "batch": "BTK-2025-001", "lot": "LOT-001",
        "scan_log": [
            {"scan_time": ago(days=41, hours=3), "scanned_by": "Eko Prasetyo",
             "actual_qty": 30.0, "batch": "BTK-2025-001", "lot": "LOT-001",
             "roll_id": "ROLL-001", "bin_id": "A1-01"},
        ],
        "escalation": None,
        "created_at": ago(days=43), "updated_at": ago(days=40),
        "dispatched_at": ago(days=40),
    })
    await db.inventory_movements.insert_many([
        {"id": new_id("mov"), "product_id": "prod_batik_mega", "warehouse_id": "wh_jakarta",
         "movement_type": "outbound_dispatch", "quantity": -30.0, "unit": "yard",
         "batch": "BTK-2025-001", "lot": "LOT-001", "roll_id": "ROLL-001",
         "source_document": "SO-0001", "notes": "Dispatch ke Toko Kain Sejahtera",
         "created_by": "user_wh_01", "timestamp": ago(days=40)},
        {"id": new_id("mov"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_jakarta",
         "movement_type": "outbound_dispatch", "quantity": -20.0, "unit": "yard",
         "batch": "TNI-2025-001", "lot": "LOT-001", "roll_id": "ROLL-003",
         "source_document": "SO-0001", "notes": "Dispatch ke Toko Kain Sejahtera",
         "created_by": "user_wh_01", "timestamp": ago(days=40)},
    ])

    # SO-0002 — Dispatched 25 days ago, multi-warehouse split
    so2_id = "so_002"
    ob2a_id = new_id("wms")
    ob2b_id = new_id("wms")
    await db.sales_orders.insert_one({
        "id": so2_id, "number": "SO-0002",
        "customer_id": "cust_moda_surabaya", "customer_name": "Moda Surabaya Fashion",
        "customer_city": "Surabaya",
        "shipping_address": {"city": "Surabaya", "address": "Jl. Rungkut Industri No. 22",
                              "recipient_name": "Bapak Andi", "phone": "083456789012"},
        "items": [
            {"product_id": "prod_lurik_classic", "sku": "LRK-CLSC-001",
             "product_name": "Lurik Klasik Solo", "quantity": 100.0, "unit": "yard",
             "price": 95000, "subtotal": 9500000},
        ],
        "total_amount": 9500000, "tax": 0, "grand_total": 9500000,
        "status": "dispatched",
        "payment_status": "paid",
        "allocations": [
            {"warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo",
             "product_id": "prod_lurik_classic", "quantity": 60.0},
            {"warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
             "product_id": "prod_lurik_classic", "quantity": 40.0},
        ],
        "created_by": "user_sales_01", "created_at": ago(days=30),
        "approved_at": ago(days=29), "approved_by": "user_manager_01",
        "confirmed_at": ago(days=28), "confirmed_by": "user_manager_01",
        "dispatched_at": ago(days=25),
        "notes": "Order grosir - Lurik split dari 2 gudang",
    })
    await db.wms_tasks.insert_many([
        {
            "id": ob2a_id, "flow_type": "outbound", "source_type": "sales_order", "task_subtype": "picking",
            "order_id": so2_id, "order_number": "SO-0002",
            "customer_name": "Moda Surabaya Fashion",
            "product_id": "prod_lurik_classic", "sku": "LRK-CLSC-001",
            "product_name": "Lurik Klasik Solo",
            "warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo",
            "quantity": 60.0, "picked_qty": 60.0, "unit": "yard",
            "status": "dispatched",
            "batch": "LRK-2025-001", "lot": "LOT-001",
            "scan_log": [
                {"scan_time": ago(days=26, hours=4), "scanned_by": "Fitri Handayani",
                 "actual_qty": 60.0, "batch": "LRK-2025-001", "lot": "LOT-001",
                 "roll_id": "ROLL-011", "bin_id": "A1-01"},
            ],
            "escalation": None,
            "created_at": ago(days=28), "updated_at": ago(days=25),
            "dispatched_at": ago(days=25),
        },
        {
            "id": ob2b_id, "flow_type": "outbound", "source_type": "sales_order", "task_subtype": "picking",
            "order_id": so2_id, "order_number": "SO-0002",
            "customer_name": "Moda Surabaya Fashion",
            "product_id": "prod_lurik_classic", "sku": "LRK-CLSC-001",
            "product_name": "Lurik Klasik Solo",
            "warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
            "quantity": 40.0, "picked_qty": 40.0, "unit": "yard",
            "status": "dispatched",
            "batch": "LRK-2025-001", "lot": "LOT-002",
            "scan_log": [
                {"scan_time": ago(days=26, hours=2), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 40.0, "batch": "LRK-2025-001", "lot": "LOT-002",
                 "roll_id": "ROLL-021", "bin_id": "A1-01"},
            ],
            "escalation": None,
            "created_at": ago(days=28), "updated_at": ago(days=25),
            "dispatched_at": ago(days=25),
        },
    ])
    await db.inventory_movements.insert_many([
        {"id": new_id("mov"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_bandung",
         "movement_type": "outbound_dispatch", "quantity": -60.0, "unit": "yard",
         "batch": "LRK-2025-001", "lot": "LOT-001", "roll_id": "ROLL-011",
         "source_document": "SO-0002", "notes": "Dispatch (split) ke Moda Surabaya Fashion",
         "created_by": "user_wh_02", "timestamp": ago(days=25)},
        {"id": new_id("mov"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_surabaya",
         "movement_type": "outbound_dispatch", "quantity": -40.0, "unit": "yard",
         "batch": "LRK-2025-001", "lot": "LOT-002", "roll_id": "ROLL-021",
         "source_document": "SO-0002", "notes": "Dispatch (split) ke Moda Surabaya Fashion",
         "created_by": "user_wh_01", "timestamp": ago(days=25)},
    ])

    # SO-0003 — Dispatched 12 days ago (Songket + Ulos, with escalation resolved)
    so3_id = "so_003"
    ob3a_id = new_id("wms")
    ob3b_id = new_id("wms")
    await db.sales_orders.insert_one({
        "id": so3_id, "number": "SO-0003",
        "customer_id": "cust_butik_bali", "customer_name": "Butik Bali Indah",
        "customer_city": "Denpasar",
        "shipping_address": {"city": "Denpasar", "address": "Jl. Seminyak No. 88",
                              "recipient_name": "Ibu Komang", "phone": "082345678901"},
        "items": [
            {"product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
             "product_name": "Songket Palembang Benang Emas", "quantity": 25.0, "unit": "yard",
             "price": 450000, "subtotal": 11250000,
             "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara"},
            {"product_id": "prod_endek_bali", "sku": "ENK-BALI-001",
             "product_name": "Endek Bali Rangrang", "quantity": 40.0, "unit": "yard",
             "price": 280000, "subtotal": 11200000,
             "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara"},
        ],
        "total_amount": 22450000, "tax": 0, "grand_total": 22450000,
        "status": "dispatched",
        "payment_status": "pending",
        "allocations": [
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_songket_palembang", "quantity": 25.0},
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_endek_bali", "quantity": 40.0},
        ],
        "created_by": "user_sales_01", "created_at": ago(days=18),
        "approved_at": ago(days=17), "approved_by": "user_manager_01",
        "confirmed_at": ago(days=16), "confirmed_by": "user_manager_01",
        "dispatched_at": ago(days=12),
        "notes": "Premium order untuk koleksi butik Bali",
    })
    await db.wms_tasks.insert_many([
        {
            "id": ob3a_id, "flow_type": "outbound", "source_type": "sales_order", "task_subtype": "picking",
            "order_id": so3_id, "order_number": "SO-0003",
            "customer_name": "Butik Bali Indah",
            "product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
            "product_name": "Songket Palembang Benang Emas",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
            "quantity": 25.0, "picked_qty": 22.0, "unit": "yard",
            "status": "dispatched",
            "batch": "SGK-2025-001", "lot": "LOT-001",
            "scan_log": [
                {"scan_time": ago(days=13, hours=3), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 22.0, "batch": "SGK-2025-001", "lot": "LOT-001",
                 "roll_id": "ROLL-003", "bin_id": "A2-01"},
            ],
            "escalation": {
                "escalated_at": ago(days=13, hours=4),
                "escalated_by": "Eko Prasetyo",
                "reason": "Fisik di rak hanya 22m, sistem menunjukkan 25m. Kemungkinan selisih dari pemakaian sebelumnya.",
                "status": "resolved",
                "resolved_at": ago(days=13, hours=1),
                "resolved_by": "Dewi Rahayu",
                "resolution_notes": "Disetujui kirim 22m, balance 3m dikoreksi. Customer konfirmasi OK.",
                "adjusted_qty": 22.0,
            },
            "created_at": ago(days=16), "updated_at": ago(days=12),
            "dispatched_at": ago(days=12),
        },
        {
            "id": ob3b_id, "flow_type": "outbound", "source_type": "sales_order", "task_subtype": "picking",
            "order_id": so3_id, "order_number": "SO-0003",
            "customer_name": "Butik Bali Indah",
            "product_id": "prod_endek_bali", "sku": "ENK-BALI-001",
            "product_name": "Endek Bali Rangrang",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
            "quantity": 40.0, "picked_qty": 40.0, "unit": "yard",
            "status": "dispatched",
            "batch": "ENK-2025-001", "lot": "LOT-001",
            "scan_log": [
                {"scan_time": ago(days=13, hours=2), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 40.0, "batch": "ENK-2025-001", "lot": "LOT-001",
                 "roll_id": "ROLL-053", "bin_id": "A2-01"},
            ],
            "escalation": None,
            "created_at": ago(days=16), "updated_at": ago(days=12),
            "dispatched_at": ago(days=12),
        },
    ])
    await db.inventory_movements.insert_many([
        {"id": new_id("mov"), "product_id": "prod_songket_palembang", "warehouse_id": "wh_jakarta",
         "movement_type": "outbound_dispatch", "quantity": -22.0, "unit": "yard",
         "batch": "SGK-2025-001", "lot": "LOT-001",
         "source_document": "SO-0003", "notes": "Dispatch ke Butik Bali Indah (adjusted after escalation)",
         "created_by": "user_wh_01", "timestamp": ago(days=12)},
        {"id": new_id("mov"), "product_id": "prod_endek_bali", "warehouse_id": "wh_jakarta",
         "movement_type": "outbound_dispatch", "quantity": -40.0, "unit": "yard",
         "batch": "ENK-2025-001", "lot": "LOT-001",
         "source_document": "SO-0003", "notes": "Dispatch ke Butik Bali Indah",
         "created_by": "user_wh_01", "timestamp": ago(days=12)},
    ])

    # SO-0004 — Currently in picking (outbound tasks in progress)
    so4_id = "so_004"
    ob4a_id = new_id("wms")
    ob4b_id = new_id("wms")
    await db.sales_orders.insert_one({
        "id": so4_id, "number": "SO-0004",
        "customer_id": "cust_fashion_bandung", "customer_name": "Fashion Bandung Kencana",
        "customer_city": "Bandung",
        "shipping_address": {"city": "Bandung", "address": "Jl. Dago No. 112, Bandung",
                              "recipient_name": "Ibu Sari", "phone": "085678901234"},
        "items": [
            {"product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
             "product_name": "Batik Mega Mendung Premium", "quantity": 50.0, "unit": "yard",
             "price": 185000, "subtotal": 9250000},
        ],
        "total_amount": 9250000, "tax": 0, "grand_total": 9250000,
        "status": "confirmed",
        "payment_status": "pending",
        "allocations": [
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_batik_mega", "quantity": 50.0},
        ],
        "created_by": "user_sales_01", "created_at": ago(days=5),
        "approved_at": ago(days=4), "approved_by": "user_manager_01",
        "confirmed_at": ago(days=3), "confirmed_by": "user_manager_01",
        "notes": "Urgent order - fashion show upcoming",
    })
    await db.wms_tasks.insert_many([
        {
            "id": ob4a_id, "flow_type": "outbound", "source_type": "sales_order", "task_subtype": "picking",
            "order_id": so4_id, "order_number": "SO-0004",
            "customer_name": "Fashion Bandung Kencana",
            "product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
            "product_name": "Batik Mega Mendung Premium",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
            "quantity": 50.0, "picked_qty": 30.0, "unit": "yard",
            "status": "picking",
            "scan_log": [
                {"scan_time": ago(days=2, hours=5), "scanned_by": "Eko Prasetyo",
                 "actual_qty": 30.0, "batch": "BTK-2025-003", "lot": "LOT-003",
                 "roll_id": "ROLL-032", "bin_id": "A1-01"},
            ],
            "escalation": None,
            "created_at": ago(days=3), "updated_at": ago(days=2),
        },
    ])

    # SO-0005 — Approved, awaiting confirmation
    so5_id = "so_005"
    await db.sales_orders.insert_one({
        "id": so5_id, "number": "SO-0005",
        "customer_id": "cust_textile_medan", "customer_name": "Tekstil Medan Jaya",
        "customer_city": "Medan",
        "shipping_address": {"city": "Medan", "address": "Jl. Asia No. 78, Medan",
                              "recipient_name": "Pak Robert", "phone": "081345678905"},
        "items": [
            {"product_id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
             "product_name": "Tenun Ikat Garuda Premium", "quantity": 50.0, "unit": "yard",
             "price": 225000, "subtotal": 11250000,
             "warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut"},
            {"product_id": "prod_ulos_batak", "sku": "ULS-BTK-001",
             "product_name": "Ulos Batak Ragidup", "quantity": 30.0, "unit": "yard",
             "price": 320000, "subtotal": 9600000,
             "warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut"},
        ],
        "total_amount": 20850000, "tax": 0, "grand_total": 20850000,
        "status": "approved",
        "payment_status": "pending",
        "allocations": [
            {"warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
             "product_id": "prod_tenun_ikat", "quantity": 50.0},
            {"warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
             "product_id": "prod_ulos_batak", "quantity": 30.0},
        ],
        "created_by": "user_sales_01", "created_at": ago(days=2),
        "approved_at": ago(hours=10), "approved_by": "user_manager_01",
        "notes": "Order besar - Tekstil Medan, perlu konfirmasi segera",
    })

    # SO-0006 — Reserved (just submitted, masih bisa di-cancel/release reservation)
    so6_id = "so_006"
    await db.sales_orders.insert_one({
        "id": so6_id, "number": "SO-0006",
        "customer_id": "cust_toko_kain", "customer_name": "Toko Kain Sejahtera",
        "customer_city": "Jakarta",
        "shipping_address": {"city": "Jakarta", "address": "Jl. Mangga Besar Raya No. 45",
                              "recipient_name": "Pak Hendra", "phone": "081234567890"},
        "items": [
            {"product_id": "prod_lurik_classic", "sku": "LRK-CLSC-001",
             "product_name": "Lurik Klasik Solo", "quantity": 40.0, "unit": "yard",
             "price": 95000, "subtotal": 3800000,
             "warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo"},
            {"product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
             "product_name": "Songket Palembang Benang Emas", "quantity": 10.0, "unit": "yard",
             "price": 450000, "subtotal": 4500000,
             "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara"},
        ],
        "total_amount": 8300000, "tax": 0, "grand_total": 8300000,
        "status": "reserved",
        "payment_status": "pending",
        "reservation_expires_at": (datetime.now(timezone.utc) + timedelta(days=2, hours=18)).isoformat(),
        "allocations": [
            {"warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo",
             "product_id": "prod_lurik_classic", "quantity": 40.0},
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_songket_palembang", "quantity": 10.0},
        ],
        "created_by": "user_sales_01", "created_at": ago(hours=2),
        "notes": "Repeat order dari Pak Hendra - Toko Kain Sejahtera (reserved otomatis, demo release reservation)",
    })

    # SO-0007 — Waiting Approval (target tour 'Approve Order')
    so7_id = "so_007"
    await db.sales_orders.insert_one({
        "id": so7_id, "number": "SO-0007",
        "customer_id": "cust_fashion_bandung", "customer_name": "Fashion Bandung Kencana",
        "customer_city": "Bandung",
        "shipping_address": {"city": "Bandung", "address": "Jl. Dago No. 112, Bandung",
                              "recipient_name": "Ibu Sari", "phone": "085678901234"},
        "items": [
            {"product_id": "prod_endek_bali", "sku": "ENK-BALI-001",
             "product_name": "Endek Bali Rangrang", "quantity": 25.0, "unit": "yard",
             "price": 280000, "subtotal": 7000000,
             "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara"},
            {"product_id": "prod_jumputan_palembang", "sku": "JMP-PLB-001",
             "product_name": "Jumputan Palembang Pelangi", "quantity": 60.0, "unit": "yard",
             "price": 145000, "subtotal": 8700000,
             "warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo"},
        ],
        "total_amount": 15700000, "tax": 0, "grand_total": 15700000,
        "status": "waiting_approval",
        "payment_status": "pending",
        "reservation_expires_at": (datetime.now(timezone.utc) + timedelta(days=2, hours=22)).isoformat(),
        "allocations": [
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_endek_bali", "quantity": 25.0},
            {"warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo",
             "product_id": "prod_jumputan_palembang", "quantity": 60.0},
        ],
        "created_by": "user_sales_01", "created_at": ago(hours=1),
        "notes": "Order baru untuk koleksi musim semi - butuh approval manager",
    })

    # SO-0008 — Reserved + multi-product (target untuk demo release reservation)
    #
    # FASE E-8 (E8.4 · US11) — pemiliknya SENGAJA **Bima Saputra** (`user_sales_02`),
    # bukan Ayu. Alasannya: sebelum ini SELURUH 9 pesanan demo dibuat satu orang, jadi
    # aturan "sales hanya melihat pesanan miliknya" tidak bisa dibuktikan dua arah —
    # akun kedua hanya menampilkan daftar KOSONG, yang tak bisa dibedakan dari layar
    # rusak. Dengan satu pesanan milik Bima: Ayu melihat 7 (tanpa SO-0008) dan Bima
    # melihat 1 (hanya SO-0008). Pilihan Bima juga KONSISTEN dengan penugasan
    # pelanggan di atas — "Butik Bali Indah" memang pelanggan Bima.
    so8_id = "so_008"
    await db.sales_orders.insert_one({
        "id": so8_id, "number": "SO-0008",
        "customer_id": "cust_butik_bali", "customer_name": "Butik Bali Indah",
        "customer_city": "Denpasar",
        "shipping_address": {"city": "Denpasar", "address": "Jl. Seminyak No. 88",
                              "recipient_name": "Ibu Komang", "phone": "082345678901"},
        "items": [
            {"product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
             "product_name": "Batik Mega Mendung Premium", "quantity": 15.0, "unit": "yard",
             "price": 185000, "subtotal": 2775000,
             "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara"},
        ],
        "total_amount": 2775000, "tax": 0, "grand_total": 2775000,
        "status": "reserved",
        "payment_status": "pending",
        "reservation_expires_at": (datetime.now(timezone.utc) + timedelta(days=1, hours=12)).isoformat(),
        "allocations": [
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_batik_mega", "quantity": 15.0},
        ],
        "created_by": "user_sales_02", "created_at": ago(hours=8),
        "notes": "Reservasi sample untuk koleksi butik - akan dikonfirmasi",
    })

    # ===== SO-0009 — Pending SO (F2b): backorder menunggu incoming PO-00009 =====
    # Stok batik tak cukup saat order → 200m masuk backorder, dijanjikan dari PO
    # incoming (PO-00009, 800m, ETA ~5 hari). Tampil di papan Stok Multi-Bucket →
    # tab "Pending SO" dengan coverage "Terjamin" + promise date = ETA PO.
    so9_id = new_id("so")
    await db.sales_orders.insert_one({
        "id": so9_id, "number": "SO-0009",
        "customer_id": "cust_textile_medan", "customer_name": "Tekstil Medan Jaya",
        "customer_city": "Medan", "entity_id": "ent_ksc",
        "shipping_address": {"city": "Medan", "address": "Jl. Sisingamangaraja No. 21",
                              "recipient_name": "Bapak Sitorus", "phone": "081234567000"},
        "items": [], "allocations": [], "total_amount": 0.0, "tax": 0, "grand_total": 0.0,
        "status": "waiting_stock", "payment_status": "pending", "has_backorder": True,
        "backorders": [{
            "id": new_id("bo"), "product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
            "product_name": "Batik Mega Mendung Premium", "entity_id": "ent_ksc",
            "customer_city": "Medan", "requested_qty": 300.0, "reserved_qty": 100.0,
            "backorder_qty": 200.0, "status": "waiting_stock",
            "created_at": ago(hours=6), "updated_at": ago(hours=6),
        }],
        "created_by": "user_sales_01", "created_at": ago(hours=6),
        "notes": "Pending SO — 200m backorder, menunggu incoming PO-00009",
    })

    # ===== KANDA/SO-00001 — Pending SO milik CV KANDA SUKA (FASE E-8 · US16/US22) =====
    #
    # KENAPA PESANAN INI ADA (dan kenapa di Kanda, bukan KSC):
    # US16 menuntut ketiga tombol Keputusan Pemenuhan bisa DIPAKAI, bukan hanya
    # tampil. Pada SO-0009 (milik KSC) tombol "Ambil dari PT lain" memang MATI dan
    # itu benar — satu-satunya badan usaha lain, Kanda, hanya punya 7 yard Batik Mega
    # (angka yang dipakai user story 13), jauh di bawah kekurangan 200 yard. Kalau
    # data demo berhenti di situ, jalur antar-PT tidak pernah bisa dibuktikan
    # ujung-ke-ujung, dan "tombolnya ada" gampang disalahartikan sebagai "fiturnya jalan".
    #
    # Arahnya dibalik: pesanan KANDA yang kurang barang, sumbernya KSC (stok 788 yard).
    # Ini sekaligus persiapan skenario FASE E-9 (jual → beli internal → retur berantai)
    # dan memakai kontrak harga internal yang sudah ada (KSC/SCT-00008, Rp 159.100/yard),
    # sehingga transaksi antar-PT lahir dengan harga sah — bukan harga tebakan.
    #
    # Dibuat oleh CITRA (`user_sales_03`, satu-satunya sales ber-home Kanda) supaya
    # US11 (kepemilikan) & US12 (perjalanan pesanan) juga bisa diuji di badan usaha kedua.
    kanda_so_id = new_id("so")
    await db.sales_orders.insert_one({
        "id": kanda_so_id, "number": "KANDA/SO-00001",
        "customer_id": "cust_moda_surabaya", "customer_name": "Moda Surabaya Fashion",
        "customer_city": "Surabaya", "entity_id": "ent_kanda",
        "shipping_address": {"city": "Surabaya", "address": "Jl. Mayjend Sungkono No. 12",
                             "recipient_name": "Ibu Ratna", "phone": "081355512345"},
        "shipping_city": "Surabaya",
        "items": [
            {"product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
             "product_name": "Batik Mega Mendung Premium", "quantity": 150.0,
             "unit": "yard", "price": 172500, "subtotal": 25875000,
             "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara"},
        ],
        "allocations": [
            {"warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
             "product_id": "prod_batik_mega", "quantity": 30.0},
        ],
        "total_amount": 25875000.0, "net_subtotal": 25875000.0,
        "dpp": 23718750.0, "ppn_amount": 2846250.0, "ppn_rate": 12.0,
        "ppn_mode": "excluded", "is_pkp": True, "tax": 0,
        "grand_total": 28721250.0,
        "payment_term_code": "NET30", "payment_term_name": "Kredit NET 30 Hari",
        "status": "waiting_stock", "payment_status": "pending", "has_backorder": True,
        "backorders": [{
            "id": new_id("bo"), "product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
            "product_name": "Batik Mega Mendung Premium", "entity_id": "ent_kanda",
            "customer_city": "Surabaya", "requested_qty": 150.0, "reserved_qty": 30.0,
            "backorder_qty": 120.0, "status": "waiting_stock",
            "created_at": ago(hours=4), "updated_at": ago(hours=4),
        }],
        "created_by": "user_sales_03", "created_at": ago(hours=4),
        "notes": "Kurang 120 yard — kandidat 'Ambil dari PT lain' (KSC punya stok)",
    })
    # Task 1 — SO-0005 outbound (status created, fresh ready to pick)
    ob5a_id = new_id("wms")
    ob5b_id = new_id("wms")
    await db.wms_tasks.insert_many([
        {
            "id": ob5a_id, "flow_type": "outbound", "source_type": "sales_order", "task_subtype": "picking",
            "order_id": so5_id, "order_number": "SO-0005",
            "customer_name": "Tekstil Medan Jaya",
            "product_id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
            "product_name": "Tenun Ikat Garuda Premium",
            "warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
            "quantity": 50.0, "picked_qty": 0.0, "unit": "yard",
            "status": "created",
            "scan_log": [], "escalation": None,
            "created_at": ago(hours=10), "updated_at": ago(hours=10),
        },
        {
            "id": ob5b_id, "flow_type": "outbound", "source_type": "sales_order", "task_subtype": "picking",
            "order_id": so5_id, "order_number": "SO-0005",
            "customer_name": "Tekstil Medan Jaya",
            "product_id": "prod_ulos_batak", "sku": "ULS-BTK-001",
            "product_name": "Ulos Batak Ragidup",
            "warehouse_id": "wh_surabaya", "warehouse_name": "Gudang Surabaya Rungkut",
            "quantity": 30.0, "picked_qty": 0.0, "unit": "yard",
            "status": "created",
            "scan_log": [], "escalation": None,
            "created_at": ago(hours=10), "updated_at": ago(hours=10),
        },
    ])

    print("✅ Sales Orders seeded (SO-0001 to SO-0008 with outbound tasks)")


async def seed_document_templates():
    await db.document_templates.insert_many([
        {
            # FASE E-4 (E4.2) — template lahir GLOBAL; kop surat khusus badan usaha
            # dibuat lewat "Buat khusus" di layar Master per Badan Usaha.
            "id": "tmpl_sj_default", "entity_id": "all",
            "document_type": "surat_jalan", "name": "Template SJ Standard",
            "header": "KAIN NUSANTARA — Enterprise Textile Warehouse",
            "footer": "Barang diterima dalam kondisi baik. Tanda tangan sebagai bukti penerimaan.",
            "columns": ["sku", "name", "qty", "unit", "batch", "lot"],
            "logo_url": "", "paper_size": "A4", "orientation": "portrait", "margin_mm": 12,
            "signature_left": "Disiapkan Oleh", "signature_right": "Diterima Oleh",
            "section_order": ["header", "customer", "items", "allocation", "signature", "footer"],
            "status": "active", "created_by": "seed", "created_at": ago(days=180)
        },
        {
            "id": "tmpl_inv_default", "entity_id": "all",
            "document_type": "invoice", "name": "Template Invoice Standard",
            "header": "KAIN NUSANTARA — Invoice",
            "footer": "Pembayaran dalam 30 hari. Terima kasih atas kepercayaan Anda.",
            "columns": ["sku", "name", "qty", "unit", "price", "subtotal"],
            "logo_url": "", "paper_size": "A4", "orientation": "portrait", "margin_mm": 12,
            "signature_left": "Dibuat Oleh", "signature_right": "Disetujui Oleh",
            "section_order": ["header", "customer", "items", "signature", "footer"],
            "status": "active", "created_by": "seed", "created_at": ago(days=180)
        },
    ])
    print("✅ Document templates seeded")


async def seed_permissions():
    if await db.permission_settings.count_documents({}) == 0:
        await db.permission_settings.insert_one(
            {"id": "default", "matrix": DEFAULT_PERMISSIONS, "updated_at": ago(days=30)}
        )
    print("✅ Permissions seeded")


async def seed_audit_logs():
    """Seed some realistic audit log entries."""
    logs = [
        {"id": new_id("audit"), "user_id": "user_admin_01", "user_name": "Budi Santoso",
         "action": "CREATE", "resource": "purchase_order", "resource_id": "po_001",
         "details": {"po_number": "PO-00001", "supplier": "Cirebon Craft"},
         "timestamp": ago(days=50)},
        {"id": new_id("audit"), "user_id": "user_wh_01", "user_name": "Eko Prasetyo",
         "action": "COMPLETE", "resource": "inbound_task", "resource_id": "completed",
         "details": {"po_number": "PO-00001", "product": "Batik Mega Mendung Premium", "quantity": 150},
         "timestamp": ago(days=44)},
        {"id": new_id("audit"), "user_id": "user_sales_01", "user_name": "Ayu Permatasari",
         "action": "CREATE", "resource": "sales_order", "resource_id": "so_001",
         "details": {"order_number": "SO-0001", "customer": "Toko Kain Sejahtera", "total": 10050000},
         "timestamp": ago(days=45)},
        {"id": new_id("audit"), "user_id": "user_manager_01", "user_name": "Dewi Rahayu",
         "action": "APPROVE", "resource": "sales_order", "resource_id": "so_001",
         "details": {"order_number": "SO-0001"},
         "timestamp": ago(days=44)},
        {"id": new_id("audit"), "user_id": "user_wh_02", "user_name": "Fitri Handayani",
         "action": "ESCALATE", "resource": "inbound_task", "resource_id": "escalated",
         "details": {"po_number": "PO-00003", "reason": "Qty kurang dari supplier"},
         "timestamp": ago(days=15, hours=5)},
        {"id": new_id("audit"), "user_id": "user_manager_01", "user_name": "Dewi Rahayu",
         "action": "RESOLVE_ESCALATION", "resource": "inbound_task", "resource_id": "resolved",
         "details": {"po_number": "PO-00003", "adjusted_qty": 180},
         "timestamp": ago(days=15, hours=2)},
    ]
    await db.audit_logs.insert_many(logs)
    print(f"✅ Audit logs seeded ({len(logs)} entries)")


async def backfill_order_snapshots():
    """Snapshot-completeness (kontrak FE↔BE): pastikan setiap sales_order punya
    `sales_name` (dari user pembuat) & `shipping_city` (dari customer/alamat).
    create_order menghasilkan field ini; seed harus mengikuti kontrak yang sama
    agar OrdersView tidak menampilkan label kosong (cegah RC-2/G1 drift)."""
    users_map = {u["id"]: u["name"]
                 for u in await db.users.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)}
    patched = 0
    for o in await db.sales_orders.find({}, {"_id": 0}).to_list(500):
        upd = {}
        if not o.get("sales_name"):
            upd["sales_name"] = users_map.get(o.get("created_by"), "Sales")
        if not o.get("shipping_city"):
            upd["shipping_city"] = (
                o.get("customer_city")
                or (o.get("shipping_address") or {}).get("city")
                or "-"
            )
        if upd:
            await db.sales_orders.update_one({"id": o["id"]}, {"$set": upd})
            patched += 1
    print(f"✅ Order snapshots backfilled (sales_name/shipping_city) → {patched} order")


async def finalize_epic2_categories():
    """EPIC2 — dijalankan di AKHIR pipeline (setelah backfill_order_pricing yang
    menulis ulang items). 1) seed master `product_categories`; 2) snapshot
    `category` (+base_unit/base_quantity) ke setiap SO line. Idempotent."""
    products_map = {p["id"]: p for p in await db.products.find(
        {}, {"_id": 0, "id": 1, "category": 1, "base_unit": 1}).to_list(2000)}

    # 1) Master kategori produk
    if await db.product_categories.count_documents({}) == 0:
        base_units = {"Batik": "yard", "Tenun": "yard", "Lurik": "yard", "Songket": "yard",
                      "Ulos": "yard", "Jumputan": "yard", "Endek": "yard"}
        names = sorted({c for c in await db.products.distinct("category") if c} | set(base_units))
        cat_docs = []
        for idx, name in enumerate(names):
            rep = next((p for p in products_map.values() if p.get("category") == name), {})
            cat_docs.append({
                "id": new_id("cat"), "code": name.upper()[:24], "name": name,
                "base_unit": rep.get("base_unit") or base_units.get(name, "yard"),
                "description": f"Kategori kain {name}", "sort_order": idx, "status": "active",
                "created_at": now_iso(), "updated_at": now_iso(),
            })
        if cat_docs:
            await db.product_categories.insert_many(cat_docs)
            print(f"✅ Product categories seeded → {len(cat_docs)} kategori")

    # 2) Snapshot kategori per SO line
    patched = 0
    for o in await db.sales_orders.find({}, {"_id": 0, "id": 1, "items": 1}).to_list(500):
        items = o.get("items") or []
        changed = False
        for it in items:
            if "category" not in it:
                prod = products_map.get(it.get("product_id"), {})
                it["category"] = prod.get("category", "")
                it.setdefault("base_unit", prod.get("base_unit", "yard"))
                it.setdefault("base_quantity", float(it.get("quantity", 0) or 0))
                changed = True
        if changed:
            await db.sales_orders.update_one({"id": o["id"]}, {"$set": {"items": items}})
            patched += 1
    print(f"✅ SO line category snapshot → {patched} order")


# EPIC3 — rasio HPP per kategori (proxy biaya bila harga_pokok belum diisi).
_HPP_RATIO_SEED = {"Batik": 0.66, "Tenun": 0.70, "Lurik": 0.62, "Songket": 0.72,
                   "Ulos": 0.68, "Jumputan": 0.60, "Endek": 0.69}


async def finalize_epic3_costing_and_ar():
    """EPIC3 — dijalankan di AKHIR pipeline. Idempotent.

    A) Costing: isi products.harga_pokok (proxy rasio kategori) bila kosong, lalu
       backfill inventory_rolls.base_unit_cost/unit_cost dari harga_pokok → WAC valid.
    B) AR Receipt: contoh penerimaan pembayaran (parsial) ke 2 order AR agar
       Collection Worklist & credit gate menampilkan paid/partial yang realistis.
    """
    # ── A) Costing data ──
    prods = await db.products.find({}, {"_id": 0}).to_list(2000)
    hpp_map = {}
    for p in prods:
        hpp = float(p.get("harga_pokok") or 0)
        if hpp <= 0:
            ratio = _HPP_RATIO_SEED.get(p.get("category"), 0.66)
            hpp = round(float(p.get("price", 0) or 0) * ratio, -2)
            if hpp > 0:
                await db.products.update_one({"id": p["id"]}, {"$set": {"harga_pokok": hpp}})
        hpp_map[p["id"]] = hpp
    roll_n = 0
    for r in await db.inventory_rolls.find({}, {"_id": 0, "id": 1, "product_id": 1,
                                               "base_unit_cost": 1, "landed_cost_total": 1}).to_list(10000):
        if r.get("base_unit_cost") not in (None, 0, 0.0):
            continue
        base = round(hpp_map.get(r.get("product_id"), 0.0), 4)
        if base <= 0:
            continue
        landed = float(r.get("landed_cost_total") or 0)
        await db.inventory_rolls.update_one(
            {"id": r["id"]}, {"$set": {"base_unit_cost": base, "unit_cost": round(base + landed, 4)}})
        roll_n += 1
    print(f"✅ EPIC3 costing → harga_pokok set, {roll_n} roll cost backfilled")

    # ── A.2) Snapshot unit_cost (cost-at-sale) ke SO line (P2-3) ──
    # Dilakukan di seed agar data konsisten tanpa perlu restart (backfill startup
    # tetap ada sbg jaring pengaman). Cost = harga_pokok produk (proxy WAC saat jual).
    so_fixed = 0
    async for o in db.sales_orders.find({}, {"_id": 0, "id": 1, "items": 1}):
        items = o.get("items") or []
        changed = False
        for it in items:
            if "unit_cost" in it:
                continue
            it["unit_cost"] = round(float(hpp_map.get(it.get("product_id"), 0.0)), 2)
            changed = True
        if changed:
            await db.sales_orders.update_one({"id": o["id"]}, {"$set": {"items": items}})
            so_fixed += 1
    print(f"✅ EPIC3 costing → unit_cost snapshot ke {so_fixed} SO (P2-3)")

    # ── B) AR Receipt examples (idempotent: skip bila sudah ada) ──
    if await db.ar_receipts.count_documents({}) > 0:
        return
    cash_methods = {"kontan", "tunai", "cash"}
    dead = {"cancelled", "draft", "expired", "rejected"}
    # P1-2 — distribusi AR LINTAS sales (bukan menumpuk di 1 sales).
    cust_sales = {c["id"]: c.get("assigned_sales_id", "") for c in
                  await db.customers.find({}, {"_id": 0, "id": 1, "assigned_sales_id": 1}).to_list(3000)}
    by_sales = {}
    for o in await db.sales_orders.find({}, {"_id": 0}).to_list(500):
        if o.get("status") in dead:
            continue
        method = str((o.get("payment_profile_method") or o.get("payment_term_code") or "")).lower()
        if method in cash_methods:
            continue
        gt = float(o.get("grand_total") or 0)
        if gt <= 0:
            continue
        sid = cust_sales.get(o.get("customer_id"), "")
        by_sales.setdefault(sid, []).append((o, gt))
    for sid in by_sales:
        by_sales[sid].sort(key=lambda t: str(t[0].get("created_at") or ""))

    sales_ids = list(by_sales.keys())
    # Rencana: tiap sales → receipt #1 parsial 50%; bila ada order ke-2 → lunas (sales pertama overpay→deposit).
    plans = []  # (order, gt, fraction, overpay)
    for idx, sid in enumerate(sales_ids):
        orders = by_sales[sid]
        if not orders:
            continue
        plans.append((orders[0][0], orders[0][1], 0.5, 0.0))
        if len(orders) > 1:
            overpay = round(orders[1][1] * 0.1, -3) if idx == 0 else 0.0
            plans.append((orders[1][0], orders[1][1], 1.0, overpay))

    seq = 0
    for o, gt, frac, overpay in plans:
        seq += 1
        applied = round(gt, 2) if frac >= 1.0 else round(gt * frac, -2)
        applied = min(applied, round(gt, 2))
        pay_amt = round(applied + overpay, 2)
        if pay_amt <= 0:
            continue
        rid = new_id("arc")
        number = f"AR-{seq:05d}"
        rdate = ago(days=5 * seq)
        unapplied = round(pay_amt - applied, 2)
        payments = list(o.get("payments") or [])
        payments.append({"id": new_id("pay"), "amount": applied, "receipt_id": rid,
                         "receipt_number": number, "method": "transfer", "date": rdate,
                         "created_at": rdate})
        paid_total = round(sum(float(p.get("amount", 0) or 0) for p in payments), 2)
        status = "paid" if paid_total >= gt - 0.01 else ("partial" if paid_total > 0.01 else "unpaid")
        await db.sales_orders.update_one(
            {"id": o["id"]}, {"$set": {"payments": payments, "paid_total": paid_total,
                                       "payment_status": status, "updated_at": now_iso()}})
        await db.ar_receipts.insert_one({
            "id": rid, "number": number, "customer_id": o.get("customer_id"),
            "customer_name": o.get("customer_name", ""), "entity_id": o.get("entity_id", "ent_ksc"),
            "receipt_date": rdate, "method": "transfer", "amount": pay_amt,
            "used_deposit": 0.0, "total_funds": pay_amt,
            "applied_total": applied, "unapplied_amount": unapplied, "deposit_delta": unapplied,
            "allocations": [{"order_id": o["id"], "order_number": o.get("number", o["id"]),
                             "applied": applied, "outstanding_after": round(gt - paid_total, 2),
                             "payment_status": status}],
            "notes": "Pembayaran (seed)" + (" — overpayment→deposit" if unapplied > 0 else ""),
            "status": "posted", "created_by": "seed", "created_by_name": "System Seed",
            "created_at": rdate, "updated_at": rdate})
        # P2-5 — overpayment → deposit customer.
        if unapplied > 0:
            await db.customers.update_one({"id": o.get("customer_id")},
                                          {"$inc": {"deposit_balance": unapplied}})
        # P0-1 — posting kas masuk (transfer → buku bank). FASE E-7 (E7.4): uangnya
        # tetap milik badan usaha pesanannya — tidak ada lagi kas tingkat grup.
        _cash_ent = o.get("entity_id") or "ent_ksc"
        cnum = await next_doc_number("cash_transactions", "number", "CASH-")
        await db.cash_transactions.insert_one({
            "id": new_id("cash"), "number": cnum, "cash_type": "kas_besar", "direction": "in",
            "amount": pay_amt, "category": "penagihan",
            "description": f"Penerimaan {number} — {o.get('customer_name', '')}",
            "entity_id": _cash_ent, "ref_type": "ar_receipt", "ref_id": rid,
            "txn_date": rdate, "status": "posted", "created_by": "seed",
            "created_at": rdate, "updated_at": rdate})
    print(f"✅ EPIC3 AR receipt → {seq} receipt (lintas {len(sales_ids)} sales) + cash posting + deposit (P0-1/P1-2/P2-5)")

    # ── C) EPIC4: rate insentif default (entity 'all' × kategori) ──
    if await db.incentive_rates.count_documents({}) == 0:
        rate_default = {"Batik": 3000, "Tenun": 3500, "Lurik": 2000, "Songket": 6000,
                        "Ulos": 4500, "Jumputan": 2500, "Endek": 4000}
        cats = [c for c in await db.products.distinct("category") if c]
        irate_docs = []
        for cat in sorted(set(cats) | set(rate_default)):
            irate_docs.append({
                "id": new_id("irate"), "entity_id": "all", "category": cat,
                "incentive_unit": "yard", "per_unit_amount": float(rate_default.get(cat, 2500)),
                "discount_threshold_type": "pct", "discount_threshold": 10.0,
                "discount_mechanic": "tier_factor", "discount_factor": 0.5,
                "discount_potong_rp": 0.0, "margin_cap_pct": 50.0,
                "status": "active", "created_at": now_iso(), "updated_at": now_iso(),
            })
        if irate_docs:
            await db.incentive_rates.insert_many(irate_docs)
            print(f"✅ EPIC4 incentive rates → {len(irate_docs)} kategori")



async def seed_entities_and_backfill():
    """Multi-Entity (Fase 0): seed entitas legal + tag entity_id ke data transaksi.

    Distribusi realistis: ~70% ke PT Kain Suka Cita, ~30% ke CV Kanda Suka,
    agar Entity Switcher punya data untuk difilter. Lalu generate notifikasi
    dari kondisi REAL (stok menipis / reservasi mendekati kedaluwarsa).
    """
    await db.business_entities.insert_many([
        {"id": "ent_ksc", "legal_name": "PT Kain Suka Cita", "short_name": "KSC",
         "type": "PT", "npwp": "01.234.567.8-901.000",
         "address": "Jl. Soekarno Hatta No. 100", "city": "Bandung",
         "default_tax_mode": "ppn", "doc_prefix": "KSC", "logo_url": "",
         "status": "active", "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso()},
        {"id": "ent_kanda", "legal_name": "CV Kanda Suka", "short_name": "Kanda",
         "type": "CV", "npwp": "02.345.678.9-012.000",
         "address": "Jl. Mangga Dua Raya No. 22", "city": "Jakarta",
         "default_tax_mode": "non_ppn", "doc_prefix": "KANDA", "logo_url": "",
         "status": "active", "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso()},
    ])
    tagged = 0
    # Multi-entity (F0): entity adalah properti CUSTOMER; sales_orders & invoices
    # MEWARISI entity customer-nya agar relasi customer↔SO↔invoice TIDAK terputus
    # lintas-entitas. (Bug lama: tagging acak per-dokumen membuat customer "yatim"
    # di entitas berbeda dari SO-nya → user sales tak bisa memilih customer sama sekali.)
    # Sebagian kecil customer ditaruh di CV Kanda untuk variasi Entity Switcher,
    # sisanya di PT Kain Suka Cita (entitas utama tim sales).
    KANDA_CUSTOMERS = {"cust_moda_surabaya"}
    cust_entity = {}
    for c in await db.customers.find({}, {"_id": 0, "id": 1}).to_list(2000):
        ent = "ent_kanda" if c["id"] in KANDA_CUSTOMERS else "ent_ksc"
        cust_entity[c["id"]] = ent
        await db.customers.update_one({"id": c["id"]}, {"$set": {"entity_id": ent}})
        tagged += 1
    # Sales orders mewarisi entity customer-nya; tanpa customer → ent_ksc.
    for o in await db.sales_orders.find(
        {}, {"_id": 0, "id": 1, "customer_id": 1, "has_backorder": 1}
    ).to_list(3000):
        ent = cust_entity.get(o.get("customer_id"), "ent_ksc")
        await db.sales_orders.update_one({"id": o["id"]}, {"$set": {"entity_id": ent}})
        # Sinkronkan entity baris backorder HANYA bila array-nya ada (hindari error path).
        if o.get("has_backorder"):
            await db.sales_orders.update_one(
                {"id": o["id"], "backorders.0": {"$exists": True}},
                {"$set": {"backorders.$[].entity_id": ent}})
        tagged += 1
    # Invoices mewarisi entity customer (atau dari SO bila customer tak terpetakan).
    for inv in await db.invoices.find(
        {}, {"_id": 0, "id": 1, "customer_id": 1, "order_id": 1, "sales_order_id": 1}
    ).to_list(3000):
        ent = cust_entity.get(inv.get("customer_id"))
        if not ent:
            oid = inv.get("order_id") or inv.get("sales_order_id")
            so = await db.sales_orders.find_one({"id": oid}, {"_id": 0, "entity_id": 1}) if oid else None
            ent = (so or {}).get("entity_id") or "ent_ksc"
        await db.invoices.update_one({"id": inv["id"]}, {"$set": {"entity_id": ent}})
        tagged += 1
    # Purchase orders: entitas PO ditetapkan BELAKANGAN oleh `seed_suppliers()` mengikuti
    # entitas supplier (deterministik) — lihat catatan bug KN-SEED-PO-ENTITY-RANDOM di sana.
    # Di sini hanya diberi nilai awal supaya tidak ada dokumen tanpa `entity_id` bila
    # supplier-nya belum terdaftar.
    for d in await db.purchase_orders.find({}, {"_id": 0, "id": 1}).to_list(2000):
        await db.purchase_orders.update_one({"id": d["id"]}, {"$set": {"entity_id": "ent_ksc"}})
        tagged += 1
    # F2b — pin demo Pending SO (SO-0009 → cust_textile_medan = ent_ksc) + PO incoming batik ke
    # entitas yang SAMA (ent_ksc) agar coverage Pending SO selalu "Terjamin".
    await db.sales_orders.update_one(
        {"number": "SO-0009"},
        {"$set": {"entity_id": "ent_ksc", "backorders.$[].entity_id": "ent_ksc"}})
    await db.purchase_orders.update_many(
        {"status": {"$in": ["pending", "created", "approved", "sent"]},
         "items.product_id": "prod_batik_mega"},
        {"$set": {"entity_id": "ent_ksc"}})
    # Notifikasi awal dari data nyata
    try:
        from services.notification_service import generate_system_notifications
        created = await generate_system_notifications()
    except Exception as e:  # pragma: no cover
        created = 0
        print(f"  (notif generate skipped: {e})")
    print(f"✅ Entities seeded (2) · entity_id tagged → {tagged} dok · {created} notifikasi")


async def backfill_order_pricing():
    """Fase 1B — hitung ulang breakdown harga (diskon item/order + PPN) untuk tiap
    sales_order memakai engine YANG SAMA dengan create_order, agar seed tidak drift
    dari aplikasi (PPN mengikuti PKP/non-PKP entitas; invarian total_amount tetap GROSS)."""
    from services.config_service import compute_order_pricing, evaluate_approval
    gs = await db.system_settings.find_one({"scope": "global"}, {"_id": 0}) or {}
    default_term = (gs.get("finance", {}) or {}).get("default_payment_term_code", "NET30")
    terms = {t["code"]: t for t in await db.payment_terms.find({}, {"_id": 0}).to_list(50)}
    patched = 0
    for o in await db.sales_orders.find({}, {"_id": 0}).to_list(500):
        raw_items = [{
            "product_id": it.get("product_id"), "sku": it.get("sku"),
            "product_name": it.get("product_name"), "quantity": it.get("quantity", 0),
            "unit": it.get("unit", "yard"), "price": it.get("price", 0),
            "discount_percent": it.get("discount_percent", 0) or 0,
        } for it in o.get("items", [])]
        pricing = await compute_order_pricing(
            raw_items, o.get("entity_id"), o.get("order_discount_percent", 0) or 0)
        term_code = o.get("payment_term_code") or default_term
        appr = await evaluate_approval("sales_order", pricing["grand_total"], o.get("entity_id"))
        await db.sales_orders.update_one({"id": o["id"]}, {"$set": {
            "items": pricing["items"], "total_amount": pricing["total_amount"],
            "items_discount_total": pricing["items_discount_total"],
            "order_discount_percent": pricing["order_discount_percent"],
            "order_discount_amount": pricing["order_discount_amount"],
            "discount_total": pricing["discount_total"],
            "net_subtotal": pricing["net_subtotal"], "dpp": pricing["dpp"],
            "ppn_rate": pricing["ppn_rate"], "ppn_mode": pricing["ppn_mode"],
            "is_pkp": pricing["is_pkp"], "ppn_amount": pricing["ppn_amount"],
            "grand_total": pricing["grand_total"],
            "payment_term_code": term_code,
            "payment_term_name": (terms.get(term_code) or {}).get("name", term_code),
            "approval_required": appr["requires_approval"],
            "required_approval_role": appr["required_role"],
            "approval_amount": pricing["grand_total"],
        }})
        patched += 1
    print(f"✅ Order pricing backfilled (diskon+PPN+approval, engine create_order) → {patched} order")

async def backfill_po_pricing():
    """P0-1 — hitung ulang breakdown harga PURCHASE ORDER (subtotal/line_total per item
    + net_subtotal/dpp/ppn/grand_total header) memakai engine YANG SAMA dengan
    `_create_po_core` (compute_order_pricing, cfg_section='purchasing'), agar seed PO
    TIDAK drift dari aplikasi dan tidak lagi menciptakan blindspot 'PO tanpa breakdown'
    yang membuat gate integritas false-PASS (verify_data_integrity INV-DB-PO).

    PO seed = legacy tanpa PPN Masukan → tax_override='non_ppn' agar ekonomi TETAP
    (grand_total == total_amount == GROSS, ppn=0): tidak mengubah AP/pembayaran/GL,
    hanya melengkapi field breakdown yang hilang. Idempotent (recompute dari price×qty).
    Field item lain (received_qty, status, inbound_task_id, quantity_base, ...) dijaga."""
    from services.config_service import compute_order_pricing
    patched = 0
    for o in await db.purchase_orders.find({}, {"_id": 0}).to_list(2000):
        items = o.get("items", [])
        if not items:
            continue
        # Pass item ASLI (bukan subset) agar semua field tracking tetap terjaga.
        pricing = await compute_order_pricing(
            items, o.get("entity_id"), o.get("order_discount_percent", 0) or 0,
            cfg_section="purchasing", tax_override="non_ppn")
        await db.purchase_orders.update_one({"id": o["id"]}, {"$set": {
            "items": pricing["items"],
            "total_amount": pricing["total_amount"],
            "items_discount_total": pricing["items_discount_total"],
            "order_discount_percent": pricing["order_discount_percent"],
            "order_discount_amount": pricing["order_discount_amount"],
            "discount_total": pricing["discount_total"],
            "net_subtotal": pricing["net_subtotal"], "dpp": pricing["dpp"],
            "ppn_rate": pricing["ppn_rate"], "ppn_mode": pricing["ppn_mode"],
            "is_pkp": pricing["is_pkp"], "ppn_amount": pricing["ppn_amount"],
            "grand_total": pricing["grand_total"],
        }})
        patched += 1
    print(f"✅ PO pricing backfilled (subtotal/line_total + net/dpp/ppn/grand, engine _create_po_core) → {patched} PO")




async def seed_price_approvals():
    """Sub-fase 1.7 — contoh special price (1 approved + 1 pending), idempotent."""
    if await db.price_approvals.count_documents({}) > 0:
        return 0
    custs = await db.customers.find({"status": "active"}, {"_id": 0}).sort("created_at", 1).to_list(5)
    prods = await db.products.find({"status": "active"}, {"_id": 0}).sort("created_at", 1).to_list(5)
    if not custs or not prods:
        return 0
    sales_user = await db.users.find_one({"role": "sales"}, {"_id": 0}) or {}
    mgr = await db.users.find_one({"role": "manager"}, {"_id": 0}) or {}
    future = (datetime.now(timezone.utc) + timedelta(days=120)).date().isoformat() + "T23:59:59+00:00"
    c0, p0 = custs[0], prods[0]
    c1 = custs[1] if len(custs) > 1 else custs[0]
    p1 = prods[1] if len(prods) > 1 else prods[0]
    docs = [
        {
            "id": new_id("pra"), "entity_id": c0.get("entity_id") or "ent_ksc",
            "customer_id": c0["id"], "customer_name": c0.get("name", ""),
            "product_id": p0["id"], "sku": p0.get("sku", ""), "product_name": p0.get("name", ""),
            "normal_price": round(float(p0.get("price", 0) or 0), 2),
            "requested_price": round(float(p0.get("price", 0) or 0) * 0.85, 2),
            "min_quantity": 20, "unit": p0.get("base_unit", "yard"),
            "reason": "Repeat order volume besar — nego harga grosir",
            "valid_from": now_iso(), "valid_until": future,
            "status": "approved", "attachments": [],
            "requested_by": sales_user.get("id"), "requested_by_name": sales_user.get("name", "Sales"),
            "approved_by": mgr.get("id"), "approved_by_name": mgr.get("name", "Manager"),
            "decision_notes": "Disetujui untuk pelanggan loyal", "decided_at": now_iso(),
            "created_at": now_iso(), "updated_at": now_iso(),
        },
        {
            "id": new_id("pra"), "entity_id": c1.get("entity_id") or "ent_ksc",
            "customer_id": c1["id"], "customer_name": c1.get("name", ""),
            "product_id": p1["id"], "sku": p1.get("sku", ""), "product_name": p1.get("name", ""),
            "normal_price": round(float(p1.get("price", 0) or 0), 2),
            "requested_price": round(float(p1.get("price", 0) or 0) * 0.90, 2),
            "min_quantity": 10, "unit": p1.get("base_unit", "yard"),
            "reason": "Permintaan diskon promo pameran",
            "valid_from": now_iso(), "valid_until": "",
            "status": "pending", "attachments": [],
            "requested_by": sales_user.get("id"), "requested_by_name": sales_user.get("name", "Sales"),
            "approved_by": None, "approved_by_name": None,
            "decision_notes": "", "decided_at": None,
            "created_at": now_iso(), "updated_at": now_iso(),
        },
    ]
    await db.price_approvals.insert_many(docs)
    print(f"✅ Price approvals seeded ({len(docs)})")
    return len(docs)


async def seed_entity_prices():
    """FASE E-4 (E4.7) — contoh **harga jual per badan usaha**, idempotent.

    Kenapa harus ada di data demo: keputusan pemilik #4 berbunyi "harga master
    global + override per badan usaha". Selama `entity_prices` KOSONG, jalur itu
    tidak pernah terbukti — layar POS/SO selalu menunjukkan harga global sehingga
    tidak ada yang tahu kalau lapisan harga badan usaha rusak.

    Cerita yang diperagakan (CV Kanda Suka melayani pasar berbeda dari KSC):
      · dua produk LEBIH MURAH (pasar grosir Jawa Tengah),
      · dua produk LEBIH MAHAL (dijual ritel dengan layanan potong),
      · satu harga TERJADWAL mulai 30 hari ke depan (agar status "Terjadwal" nyata),
      · satu override milik KSC (kontrak korporat) supaya dua badan usaha berbeda
        harga untuk produk yang sama — inti dari fitur ini.
    """
    if await db.entity_prices.count_documents({}) > 0:
        return 0
    admin = await db.users.find_one({"role": "admin"}, {"_id": 0}) or {}
    actor = admin.get("name", "System")
    # (entity_id, sku, harga, catatan, mulai_dalam_hari)
    plan = [
        ("ent_kanda", "BTK-MEGA-001", 172500, "Pasar grosir Jawa Tengah — harga Kanda", 0),
        ("ent_kanda", "LRK-CLSC-001", 89000, "Lurik volume besar pelanggan Kanda", 0),
        ("ent_kanda", "TNI-GRGD-001", 239000, "Dijual ritel + jasa potong (Kanda)", 0),
        ("ent_kanda", "SGK-PLB-001", 465000, "Songket ritel butik (Kanda)", 0),
        ("ent_kanda", "ENK-BALI-001", 295000, "Penyesuaian harga triwulan depan", 30),
        ("ent_ksc", "ULS-BTK-001", 335000, "Kontrak korporat KSC 2026", 0),
    ]
    made = 0
    for eid, sku, price, note, start_in in plan:
        ent = await db.business_entities.find_one({"id": eid}, {"_id": 0})
        prod = await db.products.find_one({"sku": sku}, {"_id": 0})
        if not ent or not prod:
            continue
        start = (datetime.now(timezone.utc) + timedelta(days=start_in)).isoformat() \
            if start_in else ago(days=45)
        await db.entity_prices.insert_one({
            "id": new_id("epr"), "entity_id": eid, "product_id": prod["id"],
            "sku": prod.get("sku", ""), "product_name": prod.get("name", ""),
            "sell_price": float(price), "currency": "IDR",
            "valid_from": start, "valid_until": "",
            "is_listed": True, "status": "active", "note": note,
            "created_by": actor, "created_at": ago(days=45 if not start_in else 1),
            "updated_at": now_iso(),
        })
        made += 1
    print(f"✅ Entity prices seeded ({made} harga per badan usaha)")
    return made


async def seed_customer_prices():
    """F1b — contoh **Daftar Harga per Pelanggan** (harga langganan), idempotent.

    Dua keadaan yang ingin diperagakan tanpa setup manual:
      1. harga kontrak yang SUDAH disetujui manajer → langsung dipakai SO/POS;
      2. satu usulan yang MASIH menunggu keputusan → terlihat di Persetujuan Harga.

    Record aktif SELALU punya pasangan `price_approvals` berstatus approved supaya data
    demo tidak melanggar aturannya sendiri ("di bawah batas wajib disetujui").
    """
    if await db.customer_prices.count_documents({}) > 0:
        return 0
    cust = await db.customers.find_one({"status": "active"}, {"_id": 0},
                                       sort=[("created_at", 1)])
    prods = await db.products.find({"status": "active", "price": {"$gt": 0}},
                                   {"_id": 0}).sort("created_at", 1).to_list(6)
    if not cust or len(prods) < 3:
        return 0
    admin = await db.users.find_one({"role": "admin"}, {"_id": 0}) or {}
    mgr = await db.users.find_one({"role": "manager"}, {"_id": 0}) or {}
    eid = cust.get("entity_id") or "ent_ksc"
    plan = [
        (prods[0], 0.92, "approved", "Harga kontrak reseller 2026"),
        (prods[1], 0.95, "approved", "Harga kontrak reseller 2026"),
        (prods[2], 0.80, "pending", "Usulan diskon volume — menunggu manajer"),
    ]
    made = 0
    for prod, ratio, decision, note in plan:
        listed = round(float(prod.get("price") or 0), 2)
        hpp = round(float(prod.get("harga_pokok") or 0), 2)
        price = round(listed * ratio, 2)
        cp_id = new_id("cpr")
        pra_id = new_id("pra")
        reasons = [f"{price:,.0f} di bawah harga acuan {listed:,.0f}"]
        guard = {"floor": max(listed, hpp), "floor_from": "entity_price" if listed >= hpp else "hpp",
                 "threshold": max(listed, hpp), "basis": "both",
                 "basis_label": "harga PT & HPP (dipakai yang lebih tinggi)",
                 "entity_reference": listed, "has_entity_price": False, "hpp": hpp,
                 "global_price": listed, "below_floor": True,
                 "gap": round(max(listed, hpp) - price, 2), "reasons": reasons,
                 "summary": "Harga di bawah batas — perlu persetujuan manajer sebelum berlaku.",
                 "tolerance_pct": 0.0, "guard_on": True}
        await db.customer_prices.insert_one({
            "id": cp_id, "entity_id": eid,
            "customer_id": cust["id"], "customer_name": cust.get("name", ""),
            "product_id": prod["id"], "sku": prod.get("sku", ""),
            "product_name": prod.get("name", ""),
            "base_unit": prod.get("base_unit", "yard"),
            "sell_price": price, "currency": "IDR",
            "valid_from": now_iso(), "valid_until": "", "is_listed": True,
            "status": "active" if decision == "approved" else "pending_approval",
            "note": note, "price_approval_id": pra_id, "guard": guard,
            "created_by": admin.get("name", "Admin"), "created_by_id": admin.get("id", ""),
            "approved_by": mgr.get("name", "Manager") if decision == "approved" else None,
            "approved_at": now_iso() if decision == "approved" else None,
            "created_at": now_iso(), "updated_at": now_iso(),
        })
        await db.price_approvals.insert_one({
            "id": pra_id, "entity_id": eid,
            "customer_id": cust["id"], "customer_name": cust.get("name", ""),
            "product_id": prod["id"], "sku": prod.get("sku", ""),
            "product_name": prod.get("name", ""),
            "normal_price": guard["floor"], "requested_price": price,
            "min_quantity": 0, "unit": prod.get("base_unit", "yard"),
            "reason": f"Harga langganan pelanggan. {note}",
            "valid_from": now_iso(), "valid_until": "",
            "status": decision, "scope": "standing", "source": "customer_pricelist",
            "customer_price_id": cp_id, "guard": guard, "so_id": "", "is_override": False,
            "attachments": [],
            "requested_by": admin.get("id"), "requested_by_name": admin.get("name", "Admin"),
            "approved_by": mgr.get("id") if decision == "approved" else None,
            "approved_by_name": mgr.get("name", "Manager") if decision == "approved" else None,
            "decision_notes": "Disetujui sesuai kesepakatan kontrak" if decision == "approved" else "",
            "decided_at": now_iso() if decision == "approved" else None,
            "created_at": now_iso(), "updated_at": now_iso(),
        })
        made += 1
    print(f"✅ Harga per pelanggan (F1b): {made} record demo "
          f"({cust.get('name','')} · 2 berlaku + 1 menunggu persetujuan)")
    return made


async def seed_pegging_examples():
    """Sub-fase 1.7 — contoh pegging/earmark (soft hold roll ke customer), idempotent.
    Invarian (verify_data_integrity): earmarked_for terisi ⟹ status 'available'."""
    if await db.inventory_rolls.count_documents({"earmarked_for": {"$ne": None}}) > 0:
        return 0
    admin = await db.users.find_one({"role": "admin"}, {"_id": 0}) or {}
    by_name = admin.get("name", "System Seed")
    rolls = await db.inventory_rolls.find(
        {"status": "available", "length_remaining": {"$gt": 0}}, {"_id": 0}
    ).sort("created_at", 1).to_list(5000)
    cust_by_entity = {}
    notes = ["Hold untuk repeat order bulanan", "Earmark menunggu PO customer"]
    pegged = 0
    for r in rolls:
        if pegged >= 2:
            break
        owner = r.get("owner_entity_id")
        if owner not in cust_by_entity:
            cust_by_entity[owner] = await db.customers.find_one(
                {"entity_id": owner, "status": "active"}, {"_id": 0}
            )
        cu = cust_by_entity.get(owner)
        if not cu:
            continue
        ear = {"type": "customer", "id": cu["id"], "name": cu.get("name", cu["id"]),
               "note": notes[pegged], "by": by_name, "at": now_iso()}
        await db.inventory_rolls.update_one(
            {"id": r["id"]}, {"$set": {"earmarked_for": ear, "updated_at": now_iso()}})
        pegged += 1
    print(f"✅ Pegging examples seeded ({pegged} roll di-earmark)")
    return pegged


async def seed_shipment_examples():
    """Sub-fase 1.8 — normalisasi SO lama berstatus 'dispatched' ke vocabulary baru
    (shipped/done/partially_shipped) + buat record `shipments` (No. Surat Jalan). Idempotent.
    Invarian: shipped_qty≤quantity; Σshipments.qty==Σtask.shipped_qty; status SO⟺progres task."""
    if await db.shipments.count_documents({}) > 0:
        return 0
    sos = await db.sales_orders.find({"status": "dispatched"}, {"_id": 0}).sort("created_at", 1).to_list(100)
    seq = 0
    total_ship = 0

    def _mk(o, t, qty, partial):
        nonlocal seq
        seq += 1
        return {
            "id": new_id("shp"), "shipment_no": f"SJ-{seq:05d}",
            "order_id": o["id"], "order_number": o.get("number", ""), "task_id": t["id"],
            "allocation_id": t.get("allocation_id"), "warehouse_id": t.get("warehouse_id"),
            "warehouse_name": t.get("warehouse_name", ""), "warehouse_city": t.get("warehouse_city", ""),
            "product_id": t.get("product_id"), "product_name": t.get("product_name", ""),
            "sku": t.get("sku", ""), "qty": round(qty, 2), "unit": t.get("unit", "yard"),
            "rolls": [], "is_partial": partial, "status": "dispatched",
            "created_by": "System Seed", "created_at": o.get("created_at", now_iso()),
        }

    for idx, o in enumerate(sos):
        tasks = await db.wms_tasks.find(
            {"order_id": o["id"], "flow_type": "outbound"}, {"_id": 0}
        ).sort("created_at", 1).to_list(100)
        if not tasks:
            await db.sales_orders.update_one({"id": o["id"]}, {"$set": {"status": "confirmed"}})
            continue
        make_partial = (idx == len(sos) - 1 and len(sos) >= 3)
        if make_partial:
            t0 = tasks[0]
            q0 = float(t0.get("quantity", 0) or 0)
            half = round(max(1.0, int(q0 / 2)), 2)
            await db.wms_tasks.update_one({"id": t0["id"]}, {"$set": {
                "picked_qty": q0, "shipped_qty": half, "status": "partially_shipped", "updated_at": now_iso()}})
            await db.shipments.insert_one(_mk(o, t0, half, True)); total_ship += 1
            for t in tasks[1:]:
                q = float(t.get("quantity", 0) or 0)
                await db.wms_tasks.update_one({"id": t["id"]}, {"$set": {
                    "picked_qty": q, "shipped_qty": 0, "status": "packing", "updated_at": now_iso()}})
            await db.sales_orders.update_one({"id": o["id"]}, {"$set": {
                "status": "partially_shipped", "updated_at": now_iso()}})
        else:
            for t in tasks:
                q = float(t.get("quantity", 0) or 0)
                await db.wms_tasks.update_one({"id": t["id"]}, {"$set": {
                    "picked_qty": q, "shipped_qty": q, "status": "dispatched", "updated_at": now_iso()}})
                await db.shipments.insert_one(_mk(o, t, q, False)); total_ship += 1
            await db.sales_orders.update_one({"id": o["id"]}, {"$set": {
                "status": ("done" if idx == 0 else "shipped"), "updated_at": now_iso()}})
    print(f"✅ Shipment examples seeded ({total_ship} shipment, {len(sos)} SO dinormalisasi)")
    return total_ship


async def seed_tax_invoice_examples():
    """Sub-fase 1.9 — contoh Faktur Pajak Jual (tax_invoices), idempotent.
    Pilih 1 SO entitas PKP (default_tax_mode=ppn) dgn ppn_amount>0 & status terkonfirmasi ke atas.
    Invarian: PPN==DPP×rate; Grand==DPP+PPN; ref order valid; is_pkp & ppn>0; nomor unik."""
    if await db.tax_invoices.count_documents({}) > 0:
        return 0
    admin = await db.users.find_one({"role": "admin"}, {"_id": 0}) or {}
    by_name = admin.get("name", "System Seed")
    pkp_entities = {e["id"]: e for e in await db.business_entities.find(
        {"default_tax_mode": "ppn"}, {"_id": 0}).to_list(50)}
    eligible_status = {"confirmed", "partially_picked", "picked",
                       "partially_shipped", "shipped", "done"}
    orders = await db.sales_orders.find(
        {"status": {"$in": list(eligible_status)}}, {"_id": 0}).sort("created_at", 1).to_list(200)
    seq = 0
    made = 0
    for o in orders:
        if made >= 2:
            break
        entity = pkp_entities.get(o.get("entity_id"))
        if not entity or float(o.get("ppn_amount", 0) or 0) <= 0:
            continue
        customer = await db.customers.find_one({"id": o.get("customer_id")}, {"_id": 0}) or {}
        addrs = customer.get("addresses", []) or []
        addr = next((a for a in addrs if a.get("is_primary")), addrs[0] if addrs else {})
        items = [{"product_name": it.get("product_name", ""), "sku": it.get("sku", ""),
                  "quantity": float(it.get("quantity", 0) or 0), "unit": it.get("unit", ""),
                  "price": float(it.get("price", 0) or 0), "subtotal": float(it.get("subtotal", 0) or 0),
                  "discount_amount": float(it.get("discount_amount", 0) or 0),
                  "line_total": float(it.get("line_total", it.get("subtotal", 0)) or 0)}
                 for it in o.get("items", [])]
        seq += 1
        fkt = {
            "id": new_id("fkt"), "number": f"FKT-{seq:05d}", "nsfp": "",
            "kode_transaksi": "01", "status": "normal",
            "replaces_id": None, "replaced_by_id": None, "cancel_reason": "",
            "faktur_date": now_iso(),
            "order_id": o["id"], "order_number": o.get("number", ""),
            "entity_id": entity["id"],
            "seller_name": entity.get("legal_name", "Kain Nusantara"),
            "seller_npwp": entity.get("npwp", ""),
            "seller_address": f"{entity.get('address','')}, {entity.get('city','')}".strip(", "),
            "customer_id": customer.get("id", o.get("customer_id")),
            "customer_name": o.get("customer_name", customer.get("name", "")),
            "customer_npwp": customer.get("npwp", ""),
            "customer_address": f"{addr.get('address','')}, {addr.get('city','')}".strip(", "),
            "has_customer_npwp": bool(customer.get("npwp")),
            "items": items,
            "total_amount": float(o.get("total_amount", 0) or 0),
            "discount_total": float(o.get("discount_total", 0) or 0),
            "net_subtotal": float(o.get("net_subtotal", 0) or 0),
            "dpp": float(o.get("dpp", 0) or 0),
            "ppn_rate": float(o.get("ppn_rate", 0) or 0),
            "ppn_mode": o.get("ppn_mode", "excluded"),
            "ppn_amount": float(o.get("ppn_amount", 0) or 0),
            "grand_total": float(o.get("grand_total", 0) or 0),
            "is_pkp": True,
            "created_by": by_name, "created_at": now_iso(), "updated_at": now_iso(),
        }
        await db.tax_invoices.insert_one(dict(fkt))
        made += 1
    print(f"✅ Tax invoice examples seeded ({made} Faktur Pajak)")
    return made


async def seed_sales_returns_examples():
    """Sub-fase 1.11 — contoh Returns & Barang Sisa (sales_returns), idempotent.
    Membuat 1 return retur (pending_approval) + 1 barang sisa/bs (draft) dari SO eligible."""
    if await db.sales_returns.count_documents({}) > 0:
        return 0

    allowed_statuses = {"confirmed", "partially_picked", "picked",
                        "partially_shipped", "shipped", "done"}
    orders = await db.sales_orders.find(
        {"status": {"$in": list(allowed_statuses)}}, {"_id": 0}
    ).sort("created_at", 1).to_list(20)

    if not orders:
        print("⚠️  seed_sales_returns: tidak ada SO eligible, skip.")
        return 0

    made = 0
    now = now_iso()

    # ── Return 1: retur (pending_approval) dari SO-0001 ───────────────────
    so1 = next((o for o in orders if o["status"] == "done"), orders[0])
    items_so1 = so1.get("items", [])[:2]
    return_items_1 = [
        {
            "product_id":        it.get("product_id", "prod_batik_tulis"),
            "product_name":      it.get("product_name", "Batik Tulis"),
            "quantity_returned": round(float(it.get("quantity", 10)) * 0.2, 1),
            "unit":              it.get("unit", "yard"),
            "reason":            "Cacat produksi — motif buram",
            "condition":         "damaged",
        }
        for it in items_so1
    ] or [{
        "product_id":        "prod_batik_tulis",
        "product_name":      "Batik Tulis Solo",
        "quantity_returned": 5.0,
        "unit":              "yard",
        "reason":            "Cacat produksi — motif buram",
        "condition":         "damaged",
    }]

    ret1_number = "SRET-00001"
    ret1 = {
        "id":           new_id("sret"),
        "number":       ret1_number,
        "order_id":     so1["id"],
        "order_number": so1.get("number", so1["id"]),
        "customer_id":  so1.get("customer_id", ""),
        "customer_name":so1.get("customer_name", ""),
        "entity_id":    so1.get("entity_id", "ent_ksc"),
        "return_type":  "retur",
        "status":       "pending_approval",
        "items":        return_items_1,
        "notes":        "Pelanggan komplain: 2 rol kain motif tidak sesuai pesanan.",
        "attachments":  [],
        "stock_adjusted": False,
        "created_by":   "sales@kainnusantara.id",
        "approved_by":  None, "approved_at": None,
        "rejected_by":  None, "rejected_at": None, "reject_reason": None,
        "created_at":   now, "updated_at": now,
    }
    await db.sales_returns.insert_one(ret1)
    made += 1

    # ── Return 2: bs/Barang Sisa (draft) dari SO-0002 ─────────────────────
    so2 = next(
        (o for o in orders if o["id"] != so1["id"] and o["status"] in {"shipped", "partially_shipped"}),
        next((o for o in orders if o["id"] != so1["id"]), None),
    )
    if so2:
        items_so2 = so2.get("items", [])[:1]
        return_items_2 = [
            {
                "product_id":        it.get("product_id", "prod_tenun_ikat"),
                "product_name":      it.get("product_name", "Tenun Ikat"),
                "quantity_returned": round(float(it.get("quantity", 8)) * 0.15, 1),
                "unit":              it.get("unit", "yard"),
                "reason":            "Sisa produksi — kain tidak habis terpakai",
                "condition":         "ok",
            }
            for it in items_so2
        ] or [{
            "product_id":        "prod_tenun_ikat",
            "product_name":      "Tenun Ikat NTT",
            "quantity_returned": 3.0,
            "unit":              "yard",
            "reason":            "Sisa produksi",
            "condition":         "ok",
        }]

        ret2_number = "SRET-00002"
        ret2 = {
            "id":           new_id("sret"),
            "number":       ret2_number,
            "order_id":     so2["id"],
            "order_number": so2.get("number", so2["id"]),
            "customer_id":  so2.get("customer_id", ""),
            "customer_name":so2.get("customer_name", ""),
            "entity_id":    so2.get("entity_id", "ent_ksc"),
            "return_type":  "bs",
            "status":       "draft",
            "items":        return_items_2,
            "notes":        "Kain sisa dari pengiriman terakhir dikembalikan ke gudang.",
            "attachments":  [],
            "stock_adjusted": False,
            "created_by":   "sales@kainnusantara.id",
            "approved_by":  None, "approved_at": None,
            "rejected_by":  None, "rejected_at": None, "reject_reason": None,
            "created_at":   now, "updated_at": now,
        }
        await db.sales_returns.insert_one(ret2)
        made += 1

    print(f"✅ Sales return examples seeded ({made} dokumen: retur + BS)")
    return made


async def seed_special_order_examples():
    """Sub-fase 1.12 — contoh Special Orders (special_orders), idempotent.
    Membuat 2 special order: 1 draft (budget rendah) + 1 confirmed (approved)."""
    if await db.special_orders.count_documents({}) > 0:
        return 0

    customers = {c["id"]: c for c in await db.customers.find({}, {"_id": 0}).to_list(10)}
    now = now_iso()

    cust1 = customers.get("cust_toko_kain", {})
    cust1_addr = (cust1.get("addresses") or [{}])[0]
    entity_id1 = "ent_ksc"

    cust2 = customers.get("cust_butik_bali", {})
    cust2_addr = (cust2.get("addresses") or [{}])[0]
    entity_id2 = "ent_kanda"

    made = 0

    # ── Special Order 1: Batik Motif Custom — draft (budget < threshold) ──
    sord1_id = new_id("sord")
    sord1 = {
        "id":            sord1_id,
        "number":        "SORD-260618-0001",
        "status":        "draft",
        "type":          "special_order",
        "customer_id":   cust1.get("id", "cust_toko_kain"),
        "customer_name": cust1.get("name", "Toko Kain Sejahtera"),
        "customer_email":cust1.get("email", ""),
        "customer_phone":cust1.get("phone", ""),
        "shipping_address": cust1_addr,
        "custom_item": {
            "description":    "Batik Tulis Motif Parang Rusak — edisi ulang tahun perusahaan",
            "specifications": {
                "motif":    "Parang Rusak Barong",
                "warna":    "Biru Indigo + Coklat Sogan",
                "panjang":  "12 yard per rol",
                "lebar":    "110 cm",
                "proses":   "Tulis tangan",
                "bahan":    "Primissima 100% katun",
            },
            "quantity":    20.0,
            "unit":        "yard",
            "target_price":350_000,
            "notes":       "Deadline: 45 hari kerja. Contoh motif sudah disetujui.",
        },
        "total_amount":    7_000_000.0,
        "requires_approval": False,
        "approval_threshold": 10_000_000,
        "expected_delivery": "2026-08-15",
        "entity_id":     entity_id1,
        "notes":         "Order khusus untuk acara HUT-25 pelanggan.",
        "status_history": [{"status": "draft", "timestamp": now, "user": "sales@kainnusantara.id"}],
        "created_at":    now, "created_by": "sales@kainnusantara.id",
        "updated_at":    now,
    }
    await db.special_orders.insert_one(sord1)
    made += 1

    # ── Special Order 2: Songket Premium — confirmed ────────────────────────
    sord2_id = new_id("sord")
    sord2 = {
        "id":            sord2_id,
        "number":        "SORD-260618-0002",
        "status":        "confirmed",
        "type":          "special_order",
        "customer_id":   cust2.get("id", "cust_butik_bali"),
        "customer_name": cust2.get("name", "Butik Bali Indah"),
        "customer_email":cust2.get("email", ""),
        "customer_phone":cust2.get("phone", ""),
        "shipping_address": cust2_addr,
        "custom_item": {
            "description":    "Kain Songket Bali Premium — untuk koleksi haute couture",
            "specifications": {
                "motif":    "Merak Ngigel",
                "benang":   "Emas 24K + Sutra ATBM",
                "lebar":    "115 cm",
                "berat":    "450 gr/m",
                "finishing":"Edging bordir manual",
            },
            "quantity":    8.0,
            "unit":        "yard",
            "target_price":850_000,
            "notes":       "Setiap yard dikerjakan 1 pengrajin. Estimasi 60 hari.",
        },
        "total_amount":    6_800_000.0,
        "requires_approval": False,
        "approval_threshold": 10_000_000,
        "expected_delivery": "2026-09-01",
        "entity_id":     entity_id2,
        "notes":         "Sudah down payment 30% (IDR 2.040.000).",
        "status_history": [
            {"status": "draft",     "timestamp": ago(days=5), "user": "sales@kainnusantara.id"},
            {"status": "confirmed", "timestamp": ago(days=3), "user": "admin@kainnusantara.id"},
        ],
        "confirmed_at":  ago(days=3),
        "created_at":    ago(days=5), "created_by": "sales@kainnusantara.id",
        "updated_at":    ago(days=3),
    }
    await db.special_orders.insert_one(sord2)
    made += 1

    print(f"✅ Special order examples seeded ({made} dokumen: draft + confirmed)")
    return made


async def seed_purchase_approval_examples():
    """Fase 3 — contoh PO untuk alur Approval Pembelian (waiting/approved/rejected).
    PO bernilai > Rp 100 jt → butuh approval role 'manager' (sesuai approval_rules)."""
    # PO-00007 — MENUNGGU approval (belum ada inbound task; task baru dibuat saat approve)
    await db.purchase_orders.insert_one({
        "id": "po_007", "po_number": "PO-00007",
        "supplier_name": "Palembang Silk House", "supplier_contact": "Ibu Sri | 081299900004",
        "supplier_npwp": "24.444.555.6-404.000",
        "warehouse_id": "wh_jakarta", "status": "waiting_approval",
        "approval_required": True, "required_approval_role": "manager", "approval_status": "pending",
        "items": [
            {"product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
             "product_name": "Songket Palembang Benang Emas",
             "quantity": 320.0, "received_qty": 0.0, "unit": "yard", "price": 420000, "status": "pending"},
        ],
        "warehouse_name": "Gudang Jakarta Utara", "warehouse_city": "Jakarta",
        "total_amount": 134400000.0,
        "expected_delivery_date": ago(days=-7),
        "notes": "Restock songket Q2 — menunggu persetujuan manajemen",
        "timeline": [
            {"event": "created", "label": "PO dibuat", "actor": "Admin",
             "at": ago(days=2), "note": "1 item · Rp 134.400.000"},
            {"event": "submitted_for_approval", "label": "Menunggu persetujuan manager",
             "actor": "Admin", "at": ago(days=2), "note": "nilai melebihi batas"},
        ],
        "created_by": "Admin", "created_at": ago(days=2), "updated_at": ago(days=2),
    })
    # PO-00008 — DITOLAK
    await db.purchase_orders.insert_one({
        "id": "po_008", "po_number": "PO-00008",
        "supplier_name": "Bali Weave Studio", "supplier_contact": "Ibu Kadek | 081388800006",
        "supplier_npwp": "26.666.777.8-406.000",
        "warehouse_id": "wh_surabaya", "status": "rejected",
        "approval_required": True, "required_approval_role": "manager", "approval_status": "rejected",
        "rejected_by": "Sari Dewi", "rejection_reason": "Harga di atas anggaran, negosiasi ulang.",
        "items": [
            {"product_id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
             "product_name": "Tenun Ikat Garuda Premium",
             "quantity": 700.0, "received_qty": 0.0, "unit": "yard", "price": 200000, "status": "cancelled"},
        ],
        "warehouse_name": "Gudang Surabaya Rungkut", "warehouse_city": "Surabaya",
        "total_amount": 140000000.0,
        "expected_delivery_date": ago(days=-10),
        "notes": "Permintaan tenun ikat partai besar",
        "timeline": [
            {"event": "created", "label": "PO dibuat", "actor": "Admin",
             "at": ago(days=5), "note": "1 item · Rp 140.000.000"},
            {"event": "submitted_for_approval", "label": "Menunggu persetujuan manager",
             "actor": "Admin", "at": ago(days=5), "note": "nilai melebihi batas"},
            {"event": "rejected", "label": "Ditolak", "actor": "Sari Dewi",
             "at": ago(days=4), "note": "Harga di atas anggaran, negosiasi ulang."},
        ],
        "created_by": "Admin", "created_at": ago(days=5), "updated_at": ago(days=4),
    })
    # PO-00009 — DISETUJUI (status pending, ada inbound task menunggu receiving)
    task9_id = new_id("wms")
    await db.purchase_orders.insert_one({
        "id": "po_009", "po_number": "PO-00009",
        "supplier_name": "Cirebon Craft", "supplier_contact": "Pak Wahyu | 081234500001",
        "supplier_npwp": "21.111.222.3-401.000",
        "warehouse_id": "wh_jakarta", "status": "pending",
        "approval_required": True, "required_approval_role": "manager", "approval_status": "approved",
        "approved_by": "Sari Dewi", "approved_at": ago(days=3),
        "items": [
            {"product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
             "product_name": "Batik Mega Mendung Premium",
             "quantity": 800.0, "received_qty": 0.0, "unit": "yard", "price": 165000,
             "status": "pending", "inbound_task_id": task9_id},
        ],
        "warehouse_name": "Gudang Jakarta Utara", "warehouse_city": "Jakarta",
        "total_amount": 132000000.0,
        "expected_delivery_date": ago(days=-5),
        "notes": "Disetujui manajemen — menunggu kedatangan barang",
        "timeline": [
            {"event": "created", "label": "PO dibuat", "actor": "Admin",
             "at": ago(days=4), "note": "1 item · Rp 132.000.000"},
            {"event": "submitted_for_approval", "label": "Menunggu persetujuan manager",
             "actor": "Admin", "at": ago(days=4), "note": "nilai melebihi batas"},
            {"event": "approved", "label": "Disetujui", "actor": "Sari Dewi",
             "at": ago(days=3), "note": "oleh role manager"},
        ],
        "created_by": "Admin", "created_at": ago(days=4), "updated_at": ago(days=3),
    })
    await db.wms_tasks.insert_one({
        "id": task9_id, "flow_type": "inbound", "source_type": "purchase_order", "task_subtype": "receiving",
        "po_id": "po_009", "po_number": "PO-00009",
        "product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
        "product_name": "Batik Mega Mendung Premium",
        "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara",
        "expected_qty": 800.0, "received_qty": 0.0, "quantity": 0.0,
        "unit": "yard", "status": "pending", "supplier_name": "Cirebon Craft",
        "bin_id": "", "batch": "", "lot": "", "scan_log": [], "escalation": None,
        "created_at": ago(days=3), "updated_at": ago(days=3),
    })
    # PO-00010 — MENUNGGU approval BERJENJANG (Fase 7.1): nilai ≥ Rp 500jt → 2 tingkat
    # (L1 Manager, L2 Direksi/admin). Keduanya masih PENDING (antri di tingkat 1).
    await db.purchase_orders.insert_one({
        "id": "po_010", "po_number": "PO-00010",
        "supplier_name": "Palembang Silk House", "supplier_contact": "Ibu Sri | 081299900004",
        "supplier_npwp": "24.444.555.6-404.000",
        "warehouse_id": "wh_jakarta", "status": "waiting_approval",
        "approval_required": True, "required_approval_role": "manager", "approval_status": "pending",
        "approval_chain": [
            {"level": 1, "required_role": "manager", "label": "Approval", "status": "pending",
             "approved_by": "", "approved_by_id": "", "approved_at": ""},
            {"level": 2, "required_role": "admin", "label": "Direksi", "status": "pending",
             "approved_by": "", "approved_by_id": "", "approved_at": ""},
        ],
        "approval_level_current": 1, "approval_levels_total": 2,
        "approval_amount": 588000000.0, "approval_reason": "amount_threshold",
        "price_deviation": {"flagged": False},
        "items": [
            {"product_id": "prod_songket_palembang", "sku": "SGK-PLB-001",
             "product_name": "Songket Palembang Benang Emas",
             "quantity": 1400.0, "received_qty": 0.0, "unit": "yard", "price": 420000, "status": "pending"},
        ],
        "warehouse_name": "Gudang Jakarta Utara", "warehouse_city": "Jakarta",
        "total_amount": 588000000.0,
        "expected_delivery_date": ago(days=-14),
        "notes": "Order besar songket — butuh persetujuan berjenjang (Manager → Direksi)",
        "timeline": [
            {"event": "created", "label": "PO dibuat", "actor": "Admin",
             "at": ago(days=1), "note": "1 item · Rp 588.000.000"},
            {"event": "submitted_for_approval", "label": "Menunggu persetujuan manager",
             "actor": "Admin", "at": ago(days=1), "note": "nilai ≥ Rp 500jt → 2 tingkat (Manager, Direksi)"},
        ],
        "created_by": "Admin", "created_at": ago(days=1), "updated_at": ago(days=1),
    })
    # PO-00011 — BERJENJANG, tingkat 1 (Manager) SUDAH disetujui, menunggu tingkat 2 (Direksi/admin).
    await db.purchase_orders.insert_one({
        "id": "po_011", "po_number": "PO-00011",
        "supplier_name": "Bali Weave Studio", "supplier_contact": "Ibu Kadek | 081388800006",
        "supplier_npwp": "26.666.777.8-406.000",
        "warehouse_id": "wh_surabaya", "status": "waiting_approval",
        "approval_required": True, "required_approval_role": "admin", "approval_status": "pending",
        "approval_chain": [
            {"level": 1, "required_role": "manager", "label": "Approval", "status": "approved",
             "approved_by": "Dewi Rahayu", "approved_by_id": "user_manager_01", "approved_at": ago(days=1)},
            {"level": 2, "required_role": "admin", "label": "Direksi", "status": "pending",
             "approved_by": "", "approved_by_id": "", "approved_at": ""},
        ],
        "approval_level_current": 2, "approval_levels_total": 2,
        "approval_amount": 520000000.0, "approval_reason": "amount_threshold",
        "price_deviation": {"flagged": False},
        "items": [
            {"product_id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
             "product_name": "Tenun Ikat Garuda Premium",
             "quantity": 2600.0, "received_qty": 0.0, "unit": "yard", "price": 200000, "status": "pending"},
        ],
        "warehouse_name": "Gudang Surabaya Rungkut", "warehouse_city": "Surabaya",
        "total_amount": 520000000.0,
        "expected_delivery_date": ago(days=-12),
        "notes": "Tenun ikat partai besar — Manager sudah setuju, menunggu persetujuan Direksi",
        "timeline": [
            {"event": "created", "label": "PO dibuat", "actor": "Admin",
             "at": ago(days=2), "note": "1 item · Rp 520.000.000"},
            {"event": "submitted_for_approval", "label": "Menunggu persetujuan manager",
             "actor": "Admin", "at": ago(days=2), "note": "nilai ≥ Rp 500jt → 2 tingkat"},
            {"event": "approved_level", "label": "Disetujui tingkat 1 (Approval)",
             "actor": "Dewi Rahayu", "at": ago(days=1), "note": "Lanjut ke Direksi"},
        ],
        "created_by": "Admin", "created_at": ago(days=2), "updated_at": ago(days=1),
    })
    print("✅ Purchase approval examples seeded (PO-00007 waiting, PO-00008 rejected, PO-00009 approved, PO-00010/00011 multi-level)")


async def seed_suppliers():
    """Fase 3 — master supplier (mencakup semua supplier_name di PO)."""
    suppliers = [
        {"name": "Cirebon Craft",        "npwp": "21.111.222.3-401.000", "pic_name": "Pak Wahyu",
         "phone": "081234500001", "city": "Cirebon",   "goods_type": "Batik & Kain Cap",        "entity_id": "ent_ksc",   "lead_time_days": 7},
        {"name": "NTT Weaving Co",        "npwp": "22.222.333.4-402.000", "pic_name": "Ibu Agnes",
         "phone": "082345600002", "city": "Kupang",    "goods_type": "Tenun Ikat",              "entity_id": "ent_ksc",   "lead_time_days": 21},
        {"name": "Solo Weave",            "npwp": "23.333.444.5-403.000", "pic_name": "Pak Joko",
         "phone": "085012300003", "city": "Solo",      "goods_type": "Lurik & Benang",          "entity_id": "ent_ksc",   "lead_time_days": 10},
        {"name": "Palembang Silk House",  "npwp": "24.444.555.6-404.000", "pic_name": "Ibu Sri",
         "phone": "081299900004", "city": "Palembang", "goods_type": "Songket & Benang Emas",   "entity_id": "ent_ksc",   "lead_time_days": 14},
        {"name": "Toba Craft",            "npwp": "",                     "pic_name": "Pak Sahat",
         "phone": "081377700005", "city": "Medan",     "goods_type": "Ulos",                    "entity_id": "ent_kanda", "lead_time_days": 18},
        {"name": "Bali Weave Studio",     "npwp": "26.666.777.8-406.000", "pic_name": "Ibu Kadek",
         "phone": "081388800006", "city": "Denpasar",  "goods_type": "Endek & Tenun Bali",      "entity_id": "ent_kanda", "lead_time_days": 12},
    ]
    docs = []
    for i, s in enumerate(suppliers, start=1):
        docs.append({
            "id": new_id("sup"), "code": f"SUP-{i:05d}", "name": s["name"],
            "npwp": s["npwp"], "pic_name": s["pic_name"], "phone": s["phone"],
            "email": f"sales@{s['name'].lower().replace(' ', '')}.co.id", "address": "",
            "city": s["city"], "goods_type": s["goods_type"], "payment_term_code": "NET30",
            "lead_time_days": s["lead_time_days"],
            "entity_id": s["entity_id"], "notes": "", "status": "active", "created_by": "seed",
            "created_at": ago(days=120), "updated_at": ago(days=120),
        })
    await db.suppliers.insert_many(docs)
    # Link existing PO supplier_name → supplier_id (FK)
    sup_by_name = {d["name"]: d["id"] for d in docs}
    ent_by_name = {d["name"]: d["entity_id"] for d in docs}
    for name, sid in sup_by_name.items():
        await db.purchase_orders.update_many({"supplier_name": name}, {"$set": {"supplier_id": sid}})
    # ── BUG NYATA `KN-SEED-PO-ENTITY-RANDOM` (ditemukan 2026-07-30, FASE G-7) ──────
    # `seed_entities()` menetapkan entitas PO dengan `random.random() < 0.3` (acak 70/30)
    # TANPA random.seed, sehingga:
    #   (a) data demo TIDAK deterministik — `po_003` bisa milik PT KSC hari ini dan
    #       CV Kanda besok. POC yang menyebut PO demo (mis. POC G-7 memakai `po_003`
    #       sebagai PO PT-A dan `po_006` sebagai PO PT-B) jadi FLAKY: hijau di satu
    #       jalan, merah di jalan berikutnya tanpa ada kode yang berubah. Ini yang
    #       menghentikan sesi sebelumnya;
    #   (b) datanya JANGGAL di layar: PO milik PT KSC ditujukan ke supplier yang
    #       terdaftar di CV Kanda — pembelian lintas-PT yang tidak pernah diniatkan.
    # Aturan domainnya jelas: satu PO dibuat oleh PT yang memang punya hubungan dengan
    # supplier itu, jadi entitas PO MENGIKUTI entitas supplier (deterministik, dan
    # sebaran dua PT tetap ada karena 2 dari 6 supplier milik CV Kanda).
    for name, ent in ent_by_name.items():
        if ent:
            await db.purchase_orders.update_many({"supplier_name": name},
                                                 {"$set": {"entity_id": ent}})
    print(f"✅ Suppliers seeded ({len(docs)}) + PO supplier_id & entitas PO = entitas supplier")


async def seed_supplier_sourcing():
    """FASE E — seed KONTRAK PEMBELIAN (`supplier_contracts` contract_type=purchase) +
    BARANG SUPPLIER (`supplier_items`).

    Kenyataan lapangan: supplier menyebut barang dengan kode & nama sendiri, dan sering
    memakai satuan sendiri (cone/roll/lembar). Peta ini membuat PO & penerimaan memakai
    nama KN dan nama supplier berdampingan, serta harga PO diambil dari kontrak.
    Dipanggil SETELAH `seed_suppliers()`. Idempotent: dilewati bila sudah ada data.
    """
    if await db.supplier_items.count_documents({}) > 0:
        print("ℹ️  supplier_items sudah ada — seed sourcing supplier dilewati")
        return 0
    import sys as _sys
    _sys.path.insert(0, "/app/backend")
    from services import contract_service as _cs
    from services import supplier_item_service as _sis

    ent = "ent_ksc"
    vf = ago(days=100)[:10]
    vt = (datetime.now(timezone.utc) + timedelta(days=265)).isoformat()[:10]

    async def sup_id(name):
        doc = await db.suppliers.find_one({"name": name}, {"_id": 0, "id": 1})
        return (doc or {}).get("id", "")

    # (nama supplier, SKU KN, kode supplier, nama versi supplier, satuan supplier, faktor, harga, MOQ, lead, grade)
    items = [
        ("Solo Weave",           "BNG-KTN-001",  "SLW-YARN-30S",   "Cotton Combed 30s Cone 1,89 Kg", "cone", 1.89,   97335, 20, 10, "A"),
        ("Solo Weave",           "LRK-CLSC-001", "SLW-LRK-40",     "Lurik Solo Roll 40 Yard",        "roll", 40.0, 2280000,  2, 10, "A"),
        ("Cirebon Craft",        "BTK-MEGA-001", "CBN-MEGA-PREM",  "Batik Cap Mega Mendung Premium", "roll", 45.0, 5265000,  1,  7, "A"),
        ("Bali Weave Studio",    "ENK-BALI-001", "BWS-RANGRANG-01", "Endek Rangrang Bali (per Meter)", "meter", 1.09, 205000, 50, 14, "A"),
        ("Palembang Silk House", "SGK-PLB-001",  "PSH-SGK-GOLD",   "Songket Benang Emas Lembaran",   "lembar", 2.5, 810000,  4, 30, "A"),
        ("Toba Craft",           "ULS-BTK-001",  "TBC-ULOS-RGD",   "Ulos Ragidup Tenun Tangan",      "lembar", 2.2, 478720,  2, 21, "A"),
        ("NTT Weaving Co",       "TNI-GRGD-001", "NTT-IKAT-GRD",   "Tenun Ikat Motif Garuda",        "roll", 30.0, 4725000,  1, 21, "A"),
    ]
    made_items = 0
    for name, sku, code, sup_name, uom, conv, price, moq, lead, grade in items:
        sid = await sup_id(name)
        if not sid:
            continue
        try:
            await _sis.create_item({
                "supplier_id": sid, "sku": sku, "supplier_sku": code,
                "supplier_item_name": sup_name, "supplier_uom": uom, "conv_factor": conv,
                "last_price": price, "moq": moq, "lead_time_days": lead,
                "expected_grade": grade,
                "notes": f"Harga per {uom} (1 {uom} = {conv:g} satuan dasar KN).",
            }, entity_id=ent, actor="Seed")
            made_items += 1
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] barang supplier {code} dilewati: {_e}")

    # Kontrak pembelian: harga per SATUAN DASAR KN (tariff_basis = satuan, rate = harga).
    contracts = [
        ("Solo Weave",    "prod_benang_katun",   "Kontrak Benang Katun 30s (tahunan)",     "kg",   50000, 100, 10),
        ("Solo Weave",    "prod_lurik_classic",  "Kontrak Lurik Klasik Solo",              "yard", 56000, 200, 10),
        ("Cirebon Craft", "prod_batik_mega",     "Kontrak Batik Cap Mega Mendung Premium", "yard", 117000, 90,  7),
    ]
    made_ct = 0
    for name, pid, title, basis, rate, moq, lead in contracts:
        sid = await sup_id(name)
        if not sid:
            continue
        try:
            c = await _cs.create_contract({
                "contract_type": "purchase", "partner_id": sid, "title": title,
                "product_id": pid, "tariff_basis": basis, "tariff_rate": rate,
                "tariff_qty_source": "input", "moq": moq, "lead_time_days": lead,
                "payment_term_code": "NET30", "valid_from": vf, "valid_to": vt,
                "notes": f"Harga terkunci Rp {rate:,.0f}/{basis} selama masa kontrak.",
            }, entity_id=ent, actor="Seed")
            made_ct += 1
            print(f"   · {c['contract_number']} — {c['partner_name']} · {basis} @ Rp {rate:,.0f}")
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] kontrak pembelian {name}/{pid} dilewati: {_e}")

    print(f"✅ Sourcing supplier seeded ({made_ct} kontrak pembelian · {made_items} barang supplier)")
    return made_items


async def seed_receiving_supplier_uom_demo():
    """FASE F-1 — demo PENERIMAAN BERBASIS SATUAN SUPPLIER (siap dicoba di layar Inbound).

    Kenyataan lapangan: surat jalan supplier memakai satuan supplier (cone/roll/lembar),
    sedangkan stok KN memakai kg/yard. Demo ini menyiapkan dua task inbound:

      1. **PO benang (kg, dijual per CONE)** — status `waiting_goods`, BELUM diterima.
         Operator bisa langsung mencoba: pilih satuan `cone`, ketik `25` → sistem
         menampilkan 47,25 kg lalu menyimpannya sebagai qty stok.
      2. **PO lurik (yard, dijual per ROLL 40 yard)** — sudah diterima SEBAGIAN
         (5 roll = 200 yard dari 400 yard) lengkap dengan **jejak konversi** supaya
         panel riwayat & audit langsung terlihat isinya.

    Jejak konversi dibuat lewat SSOT `receiving_uom_service.convert_doc_qty` (bukan
    mengarang angka). Task ke-2 sengaja BELUM di-complete sehingga tidak ada roll/GL —
    rekonsiliasi Persediaan 1-1300 tetap utuh. Idempotent: dilewati bila sudah ada.
    """
    import sys as _sys
    _sys.path.insert(0, "/app/backend")
    if await db.purchase_orders.count_documents({"notes": {"$regex": "FASE F-1"}}) > 0:
        print("ℹ️  demo penerimaan satuan supplier sudah ada — dilewati")
        return 0
    from services import receiving_uom_service as _rus

    ent = "ent_ksc"
    sup = await db.suppliers.find_one({"name": "Solo Weave"}, {"_id": 0, "id": 1, "name": 1})
    if not sup:
        print("  [warn] supplier Solo Weave tidak ada — demo F-1 dilewati")
        return 0
    wh = await db.warehouses.find_one({"id": "wh_jakarta"}, {"_id": 0, "id": 1, "name": 1, "city": 1})
    made = 0

    async def sit(sku):
        return await db.supplier_items.find_one(
            {"supplier_id": sup["id"], "sku": sku}, {"_id": 0})

    async def make_po(pid, sku, name, qty, unit, price, si, po_note, status, task_status):
        nonlocal made
        po_id = new_id("po")
        num = await next_doc_number("purchase_orders", "po_number", "PO-", entity_id=ent)
        item = {
            "product_id": pid, "sku": sku, "product_name": name,
            "quantity": qty, "received_qty": 0.0, "unit": unit, "base_unit": unit,
            "quantity_base": qty, "price": price, "discount_percent": 0,
            "expected_grade": "A", "expected_grade_source": "manual",
            "subtotal": qty * price, "status": "pending",
            "supplier_item_id": (si or {}).get("id", ""),
            "supplier_sku": (si or {}).get("supplier_sku", ""),
            "supplier_item_name": (si or {}).get("supplier_item_name", ""),
            "supplier_uom": (si or {}).get("supplier_uom", ""),
            "supplier_conv_factor": (si or {}).get("conv_factor", 0),
        }
        await db.purchase_orders.insert_one({
            "id": po_id, "po_number": num, "entity_id": ent,
            "supplier_id": sup["id"], "supplier_name": sup["name"],
            "supplier_contact": "Pak Joko | 085012300003",
            "warehouse_id": wh["id"], "warehouse_name": wh["name"],
            "status": status, "items": [item],
            "total_amount": qty * price, "grand_total": qty * price,
            "expected_delivery_date": ago(days=-3),
            "notes": po_note, "created_by": "Budi Santoso",
            "created_at": ago(days=4), "updated_at": ago(days=1),
        })
        task = {
            "id": new_id("wms"), "entity_id": ent, "flow_type": "inbound",
            "source_type": "purchase_order", "task_subtype": "receiving",
            "po_id": po_id, "po_number": num,
            "product_id": pid, "sku": sku, "product_name": name,
            "warehouse_id": wh["id"], "warehouse_name": wh["name"],
            "warehouse_city": wh.get("city", ""),
            "expected_qty": qty, "received_qty": 0.0, "quantity": 0.0, "unit": unit,
            "status": task_status, "stages": ["waiting_goods", "receiving", "qc_check",
                                              "put_away", "completed"],
            "supplier_name": sup["name"],
            "supplier_sku": item["supplier_sku"],
            "supplier_item_name": item["supplier_item_name"],
            "supplier_item_id": item["supplier_item_id"],
            "supplier_uom": item["supplier_uom"],
            "supplier_conv_factor": item["supplier_conv_factor"],
            "expected_grade": "A",
            "bin_id": "", "batch": "", "lot": "", "roll_id": "",
            "scan_log": [], "escalation": None,
            "created_by": "Budi Santoso",
            "created_at": ago(days=4), "updated_at": ago(days=4),
        }
        await db.wms_tasks.insert_one(task)
        made += 1
        return task, num

    # ── 1. Benang katun per CONE — belum diterima (silakan coba sendiri) ─────
    si_yarn = await sit("BNG-KTN-001")
    t1, n1 = await make_po("prod_benang_katun", "BNG-KTN-001", "Benang Katun Cone (per Kg)",
                           120.0, "kg", 50000,
                           si_yarn, "FASE F-1 — demo terima benang dalam satuan CONE",
                           "pending", "waiting_goods")
    print(f"   · {n1} · 120 kg benang — coba terima dalam satuan "
          f"'{(si_yarn or {}).get('supplier_uom', '-')}' di layar Inbound")

    # ── 2. Lurik per ROLL — sudah diterima 5 roll (200 yard) + JEJAK konversi ─
    si_lrk = await sit("LRK-CLSC-001")
    t2, n2 = await make_po("prod_lurik_classic", "LRK-CLSC-001", "Lurik Klasik Solo",
                           400.0, "yard", 56000,
                           si_lrk, "FASE F-1 — demo terima lurik dalam satuan ROLL",
                           "receiving", "receiving")
    if si_lrk:
        try:
            trail = await _rus.convert_doc_qty(t2, si_lrk["supplier_uom"], 5)
            scan = {
                "id": new_id("scan"), "scan_type": "receive",
                "actual_qty": trail["task_qty"], "batch": "LRK-2026-01",
                "lot": "LOT-LRK-2026-01", "roll_id": "", "bin_id": "A3-02",
                "actor": "Eko Prasetyo", "timestamp": ago(days=1),
                "uom_trail": trail,
            }
            await db.wms_tasks.update_one({"id": t2["id"]}, {
                "$set": {"received_qty": trail["task_qty"], "status": "receiving",
                         "batch": "LRK-2026-01", "lot": "LOT-LRK-2026-01",
                         "bin_id": "A3-02", "grade": "A",
                         "last_receive_doc_uom": trail["doc_uom"],
                         "receive_variance_percent": round(
                             (trail["task_qty"] - 400.0) / 400.0 * 100.0, 2),
                         "receive_within_tolerance": False,
                         "receive_tolerance_percent": 2.0,
                         "updated_at": ago(days=1)},
                "$push": {"scan_log": scan,
                          "receive_uom_trails": {**trail, "scan_id": scan["id"],
                                                 "actor": "Eko Prasetyo"}}})
            await db.purchase_orders.update_one(
                {"id": t2["po_id"]}, {"$set": {"items.0.received_qty": trail["task_qty"]}})
            print(f"   · {n2} · 5 {trail['doc_uom']} = {trail['task_qty']:g} yard diterima "
                  f"(faktor {trail['factor']:g} · sumber {trail['source']}) — jejak tersimpan")
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] jejak konversi demo lurik dilewati: {_e}")

    print(f"✅ Demo penerimaan satuan supplier (Fase F-1) seeded ({made} task inbound)")
    return made


async def seed_supplier_price_lists():
    """Depth #3 — daftar harga beli (price-list) per (supplier, product).
    Dipakai untuk auto-isi harga PO/PR. Harga = SNAPSHOT supplier (≈ harga_pokok),
    unit = base_unit produk (UOM engine). Beberapa entri pakai MOQ untuk demo tier.
    """
    suppliers = {s["name"]: s for s in await db.suppliers.find({}, {"_id": 0}).to_list(500)}
    products = await db.products.find({}, {"_id": 0}).to_list(500)
    # Map supplier_name produk → entri price-list (1 entri default + 1 tier MOQ tertentu).
    docs = []
    for p in products:
        sup = suppliers.get(p.get("supplier", ""))
        if not sup:
            continue
        base_unit = p.get("base_unit", "yard")
        base_price = float(p.get("harga_pokok", 0) or p.get("price", 0) or 0)
        if base_price <= 0:
            continue
        # Entri standar (tanpa MOQ)
        docs.append({
            "id": new_id("spl"), "supplier_id": sup["id"], "supplier_name": sup["name"],
            "product_id": p["id"], "sku": p.get("sku", ""), "product_name": p.get("name", ""),
            "price": round(base_price, 2), "unit": base_unit, "min_qty": 0.0,
            "lead_time_days": 0, "valid_from": "", "valid_until": "", "currency": "IDR",
            "entity_id": sup.get("entity_id", "ent_ksc"), "notes": "Harga standar (seed)",
            "status": "active", "created_by": "seed",
            "created_at": ago(days=90), "updated_at": ago(days=90),
        })
        # Entri tier diskon volume (MOQ 200) — 5% lebih murah
        docs.append({
            "id": new_id("spl"), "supplier_id": sup["id"], "supplier_name": sup["name"],
            "product_id": p["id"], "sku": p.get("sku", ""), "product_name": p.get("name", ""),
            "price": round(base_price * 0.95, 2), "unit": base_unit, "min_qty": 200.0,
            "lead_time_days": 0, "valid_from": "", "valid_until": "", "currency": "IDR",
            "entity_id": sup.get("entity_id", "ent_ksc"), "notes": "Tier volume ≥200 (seed)",
            "status": "active", "created_by": "seed",
            "created_at": ago(days=90), "updated_at": ago(days=90),
        })
    if docs:
        await db.supplier_price_lists.insert_many(docs)
    print(f"✅ Supplier price-lists seeded ({len(docs)})")


async def seed_cash_transactions():
    """Fase 3 — contoh transaksi kas. FASE E-7 (E7.4): TIDAK ADA LAGI kas tingkat grup —
    `kas_besar` berarti buku bank/transfer, tetapi uangnya tetap milik satu badan usaha."""
    examples = [
        {"cash_type": "kas_besar", "direction": "in",  "amount": 100000000, "category": "modal",
         "description": "Setoran modal awal PT Kain Suka Cita (rekening bank)",
         "entity_id": "ent_ksc",  "days": 60},
        {"cash_type": "kas_besar", "direction": "in",  "amount": 25000000, "category": "modal",
         "description": "Setoran modal awal CV Kanda Suka (rekening bank)",
         "entity_id": "ent_kanda", "days": 58},
        {"cash_type": "kas_kecil", "direction": "in",  "amount": 10000000,  "category": "transfer",
         "description": "Top-up kas kecil PT Kain Suka Cita", "entity_id": "ent_ksc",  "days": 45},
        {"cash_type": "kas_kecil", "direction": "out", "amount": 1500000,   "category": "operasional",
         "description": "Biaya operasional gudang Bandung",   "entity_id": "ent_ksc",  "days": 30},
        {"cash_type": "kas_kecil", "direction": "out", "amount": 750000,    "category": "pembelian",
         "description": "Pembelian bahan printing",           "entity_id": "ent_ksc",  "days": 20},
        {"cash_type": "kas_kecil", "direction": "in",  "amount": 5000000,   "category": "transfer",
         "description": "Top-up kas kecil CV Kanda Suka",     "entity_id": "ent_kanda","days": 15},
        {"cash_type": "kas_kecil", "direction": "out", "amount": 1200000,   "category": "operasional",
         "description": "Biaya kirim sample ke customer",     "entity_id": "ent_kanda","days": 7},
    ]
    docs = []
    for i, e in enumerate(examples, start=1):
        docs.append({
            "id": new_id("cash"), "number": f"CASH-{i:05d}",
            "cash_type": e["cash_type"], "direction": e["direction"], "amount": float(e["amount"]),
            "category": e["category"], "description": e["description"], "entity_id": e["entity_id"],
            "ref_type": "manual", "ref_id": "", "txn_date": ago(days=e["days"]),
            "status": "posted", "created_by": "seed",
            "created_at": ago(days=e["days"]), "updated_at": ago(days=e["days"]),
        })
    await db.cash_transactions.insert_many(docs)
    print(f"✅ Cash transactions seeded ({len(docs)})")


async def seed_bank_accounts():
    """EPIC7-B — akun kas/bank + tautkan transaksi kas (account_id) + rekonsiliasi."""
    accounts = [
        {"id": "bank_bca_ksc", "name": "BCA Operasional KSC", "account_type": "bank",
         "bank_name": "BCA", "account_number": "0123456789", "entity_id": "ent_ksc",
         "opening_balance": 50000000.0},
        {"id": "bank_kas_ksc", "name": "Kas Kecil KSC", "account_type": "cash",
         "bank_name": "", "account_number": "", "entity_id": "ent_ksc", "opening_balance": 2000000.0},
        {"id": "bank_kas_kanda", "name": "Kas Kecil Kanda", "account_type": "cash",
         "bank_name": "", "account_number": "", "entity_id": "ent_kanda", "opening_balance": 1000000.0},
        {"id": "bank_kas_besar_ksc", "name": "Kas Besar / Bank KSC", "account_type": "cash",
         "bank_name": "", "account_number": "", "entity_id": "ent_ksc", "opening_balance": 0.0},
        {"id": "bank_kas_besar_kanda", "name": "Kas Besar / Bank Kanda", "account_type": "cash",
         "bank_name": "", "account_number": "", "entity_id": "ent_kanda", "opening_balance": 0.0},
    ]
    docs = []
    for a in accounts:
        docs.append({**a, "currency": "IDR", "note": "", "is_active": True,
                     "created_at": ago(days=90), "updated_at": ago(days=90)})
    await db.bank_accounts.insert_many(docs)

    # Tautkan transaksi kas yang ada ke akun (by cash_type + entity).
    # FASE E-7 (E7.4) — tidak ada lagi rekening tingkat grup: setiap transaksi menunjuk
    # rekening milik badan usahanya sendiri.
    def _acc_for(t):
        ent = t.get("entity_id") or "ent_ksc"
        if t.get("cash_type") == "kas_besar":
            return "bank_kas_besar_ksc" if ent == "ent_ksc" else "bank_kas_besar_kanda"
        return "bank_kas_ksc" if ent == "ent_ksc" else "bank_kas_kanda"

    cash_txns = await db.cash_transactions.find({}, {"_id": 0, "id": 1, "cash_type": 1, "entity_id": 1, "direction": 1}).to_list(1000)
    for idx, t in enumerate(cash_txns):
        # ~setengah ditandai sudah terekonsiliasi (yang 'in' & indeks genap)
        reconciled = (t.get("direction") == "in") or (idx % 2 == 0)
        await db.cash_transactions.update_one(
            {"id": t["id"]},
            {"$set": {"account_id": _acc_for(t), "reconciled": bool(reconciled),
                      "reconciled_at": ago(days=5) if reconciled else ""}},
        )
    print(f"✅ Bank accounts seeded ({len(docs)}) + {len(cash_txns)} cash txns ditautkan")


async def seed_purchase_returns():
    """Depth #1 — contoh retur beli (pending_approval, belum sesuaikan stok)."""
    returns = [
        {"id": new_id("pret"), "number": "PRET-00001",
         "supplier_name": "NTT Weaving Co", "supplier_id": "",
         "po_id": "po_002", "po_number": "PO-00002", "warehouse_id": "wh_surabaya",
         "warehouse_name": "Gudang Surabaya Rungkut", "entity_id": "ent_ksc",
         "items": [{"product_id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
                    "product_name": "Tenun Ikat Garuda Premium", "quantity": 12.0, "unit": "yard",
                    "price": 200000, "subtotal": 2400000, "reason": "cacat", "condition": "damaged"}],
         "total_amount": 2400000.0, "reason": "Sebagian gulungan cacat tenun (belang warna)",
         "notes": "Foto sudah dikirim ke supplier via WA",
         "status": "pending_approval", "debit_note_number": "", "stock_adjusted": False,
         "created_by": "Eko Prasetyo", "approved_by": None, "approved_at": None,
         "rejected_by": None, "rejected_at": None, "reject_reason": None,
         "created_at": ago(days=6), "updated_at": ago(days=6)},
        {"id": new_id("pret"), "number": "PRET-00002",
         "supplier_name": "Cirebon Craft", "supplier_id": "",
         "po_id": "po_001", "po_number": "PO-00001", "warehouse_id": "wh_jakarta",
         "warehouse_name": "Gudang Jakarta Utara", "entity_id": "ent_ksc",
         "items": [{"product_id": "prod_batik_mega", "sku": "BTK-MEGA-001",
                    "product_name": "Batik Mega Mendung Premium", "quantity": 5.0, "unit": "yard",
                    "price": 165000, "subtotal": 825000, "reason": "salah_kirim", "condition": "ok"}],
         "total_amount": 825000.0, "reason": "Motif tidak sesuai PO",
         "notes": "", "status": "draft", "debit_note_number": "", "stock_adjusted": False,
         "created_by": "Admin", "approved_by": None, "approved_at": None,
         "rejected_by": None, "rejected_at": None, "reject_reason": None,
         "created_at": ago(days=2), "updated_at": ago(days=2)},
    ]
    # link supplier_id by name
    sup_map = {s["name"]: s["id"] for s in await db.suppliers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
    for r in returns:
        r["supplier_id"] = sup_map.get(r["supplier_name"], "")
    await db.purchase_returns.insert_many(returns)
    print(f"✅ Purchase returns seeded ({len(returns)})")


async def seed_po_payments():
    """Backfill field keuangan default untuk PO lama.

    P0-B (SSOT AP): pembayaran tidak lagi dicatat di level PO. Hutang & pembayaran
    supplier dikelola via Vendor Bill (menu "Tagihan Supplier"). Maka demo
    pembayaran PO-level lama DIHAPUS; PO-00002 tampil sebagai PO selesai yang
    siap ditagih lewat Vendor Bill.
    """
    await db.purchase_orders.update_many(
        {"amount_paid": {"$exists": False}},
        {"$set": {"amount_paid": 0.0, "returned_amount": 0.0, "payment_status": "unpaid", "payments": []}})
    print("✅ PO financial fields backfilled (pembayaran via Vendor Bill / SSOT)")


async def seed_requisitions():
    """Depth #2a — contoh Purchase Requisition (PR) hulu procurement."""
    sup_map = {s["name"]: s for s in await db.suppliers.find({}, {"_id": 0}).to_list(500)}
    wh = (await db.warehouses.find_one({"id": "wh_jakarta"}, {"_id": 0})
          or await db.warehouses.find_one({}, {"_id": 0}))
    prods = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(50)}

    def line(pid, qty, mode="purchase", line_no=1):
        p = prods.get(pid, {})
        price = float(p.get("harga_pokok", 0) or p.get("price", 0) or 0)
        return {"line_no": line_no,
                "product_id": pid, "sku": p.get("sku", ""), "product_name": p.get("name", ""),
                "description": p.get("name", ""), "quantity": float(qty),
                "unit": p.get("base_unit", "yard"), "est_price": price,
                "subtotal": round(price * qty, 2), "note": "",
                # FASE E — routing pemenuhan per baris (purchase = beli jadi, makloon = subkontrak)
                "fulfillment_mode": mode, "realized_qty": 0.0, "realizations": []}

    def mkdoc(num, items, status, source, supplier_name, appr, created_by, days):
        total = round(sum(i["subtotal"] for i in items), 2)
        sup = sup_map.get(supplier_name, {})
        for i, it in enumerate(items, start=1):
            it["line_no"] = i
        n_purchase = sum(1 for i in items if i.get("fulfillment_mode") == "purchase")
        n_makloon = sum(1 for i in items if i.get("fulfillment_mode") == "makloon")
        return {
            "id": new_id("pr"), "number": num, "entity_id": "ent_ksc",
            "warehouse_id": wh["id"], "warehouse_name": wh["name"],
            "items": items, "total_est_amount": total,
            "source": source, "source_ref_id": "",
            "preferred_supplier_id": sup.get("id", ""), "preferred_supplier_name": sup.get("name", supplier_name),
            "reason": "Restock kebutuhan produksi & penjualan", "needed_by_date": "",
            "notes": "", "status": status,
            "approval_required": appr,
            "required_approval_role": "manager" if appr else None,
            "approval_status": "approved" if status == "approved" else ("pending" if status == "pending_approval" else "not_submitted"),
            "po_id": "", "po_number": "",
            # FASE E — ringkasan realisasi (turunan; SSOT tetap items[].realized_qty)
            "realization_status": "open",
            "realization": {"realization_status": "open", "realized_lines": 0,
                            "total_lines": len(items), "realized_qty": 0.0,
                            "total_qty": round(sum(float(i["quantity"]) for i in items), 3),
                            "realized_pct": 0.0,
                            "purchase_lines": n_purchase, "makloon_lines": n_makloon},
            "po_ids": [], "makloon_order_ids": [], "timeline": [],
            "created_by": created_by,
            "approved_by": "Rina Manajer" if status == "approved" else None,
            "approved_at": ago(days=days) if status == "approved" else None,
            "rejected_by": None, "rejected_at": None, "reject_reason": None,
            "created_at": ago(days=days), "updated_at": ago(days=days),
        }

    prs = [
        mkdoc("PR-00001", [line("prod_songket_palembang", 600), line("prod_ulos_batak", 500)],
              "approved", "reorder", "Palembang Silk House", False, "Eko Prasetyo", 5),
        mkdoc("PR-00002", [line("prod_batik_mega", 800)],
              "pending_approval", "manual", "Cirebon Craft", True, "Eko Prasetyo", 2),
        mkdoc("PR-00003", [line("prod_endek_bali", 400)],
              "draft", "manual", "Bali Weave Studio", False, "Admin", 1),
        # FASE E — PR CAMPUR: benang & lurik DIBELI, kain grey DIPROSES via makloon.
        mkdoc("PR-00005", [line("prod_benang_katun", 120, "purchase"),
                           line("prod_lurik_classic", 300, "purchase"),
                           line("prod_grey_katun", 400, "makloon")],
              "approved", "manual", "Solo Weave", False, "Eko Prasetyo", 1),
    ]
    # PR-00004 — CONVERTED → PO-00009 (rantai PR→PO untuk EPIC6 Document Relations).
    # Profil item/supplier sengaja cocok dengan po_009 (Cirebon Craft, Batik Mega 800m).
    pr_converted = mkdoc("PR-00004", [line("prod_batik_mega", 800)],
                         "approved", "reorder", "Cirebon Craft", True, "Eko Prasetyo", 6)
    # FASE E — PR ini SUDAH terealisasi penuh ke PO-00009: jejak realisasi per baris
    # WAJIB terisi agar `realization_status` turunan konsisten (INV-SRC-02/03).
    for _it in pr_converted["items"]:
        _it["realized_qty"] = float(_it["quantity"])
        _it["realizations"] = [{"type": "purchase_order", "ref_id": "po_009",
                                "ref_number": "PO-00009", "qty": float(_it["quantity"]),
                                "at": ago(days=4), "by": "Admin"}]
    _tot = round(sum(float(i["quantity"]) for i in pr_converted["items"]), 3)
    pr_converted.update({
        "status": "converted", "approval_status": "approved",
        "po_id": "po_009", "po_number": "PO-00009",
        "po_ids": ["po_009"],
        "realization_status": "realized",
        "realization": {"realization_status": "realized",
                        "realized_lines": len(pr_converted["items"]),
                        "total_lines": len(pr_converted["items"]),
                        "realized_qty": _tot, "total_qty": _tot, "realized_pct": 100.0,
                        "purchase_lines": len(pr_converted["items"]), "makloon_lines": 0},
        "converted_by": "Admin", "converted_at": ago(days=4),
    })
    prs.append(pr_converted)
    await db.purchase_requisitions.insert_many(prs)
    print(f"✅ Purchase requisitions seeded ({len(prs)})")


async def seed_qc_quarantine_examples():
    """Depth #3a — contoh task inbound `qc_pending` + roll `quarantine` (demo inspeksi QC).
    Dipanggil SETELAH generate_rolls_from_balances agar rebuild_balance konsisten."""
    from services.roll_service import rebuild_balance
    # Pilih PO dengan item sebagai sumber demo (supplier ter-link untuk skenario retur)
    po = await db.purchase_orders.find_one(
        {"items.0": {"$exists": True}}, {"_id": 0}, sort=[("created_at", 1)])
    if not po or not po.get("items"):
        print("⚠️  QC demo dilewati (tidak ada PO berisi item).")
        return
    item = po["items"][0]
    pid = item["product_id"]
    wid = po.get("warehouse_id") or "wh_jakarta"
    owner = po.get("entity_id") or "ent_ksc"
    prod = await db.products.find_one({"id": pid}, {"_id": 0}) or {}
    wh = await db.warehouses.find_one({"id": wid}, {"_id": 0}) or {}
    qqty = 75.0
    lot = f"LOT-QC-{po.get('po_number', 'PO')}"
    task_id = new_id("wms")
    # INV-ROLL-01 — nomor dari pengalokasi bersama. Dulu `count_documents({})+1`:
    # setelah pengalokasi atomik dipakai pembuat lain, nomor hasil hitung-dokumen
    # ini MENABRAK nomor yang sudah terpakai (terukur: RL-00043 dipakai 2 roll —
    # ditangkap gate INV-ROLL-01 pada seed pertama sesudah perbaikan).
    from services.roll_service import next_roll_no as _next_roll_no
    # FASE C (D-10) — roll demo QC juga lahir dengan lot kelas satu (bukan string lepas)
    from services import lot_service as _lots
    _qc_lot = await _lots.resolve_or_create(
        product_id=pid, owner_entity_id=owner, warehouse_id=wid, lot_code=lot,
        source="receiving",
        source_ref={"type": "wms_task", "id": task_id, "number": po.get("po_number", "")},
        dye_lot=lot, supplier_name=po.get("supplier_name", ""),
        supplier_id=po.get("supplier_id", ""), status="karantina", actor="seed")
    await db.inventory_rolls.insert_one({
        "id": new_id("roll"), "product_id": pid, "owner_entity_id": owner,
        "ownership_type": "internal", "consignor_ref": None,
        "warehouse_id": wid, "bin_id": None, "lot": _qc_lot["lot_number"],
        "lot_id": _qc_lot["id"], "dye_lot": lot,
        "batch": lot.replace("LOT", "BATCH"), "roll_no": await _next_roll_no(),
        "length_initial": qqty, "length_remaining": qqty,
        "unit": prod.get("base_unit", "yard"), "grade": "A",
        # Fase A · PS-02 — snapshot domain produk (INV-DOMAIN-05)
        "stage": prod.get("stage") or "finished", "fabric_type": prod.get("fabric_type") or "woven",
        "status": "quarantine", "qc_task_id": task_id, "tracking_mode": "barcode",
        "earmarked_for": None, "location_type": "warehouse_bin", "reserved_ref": None,
        "unit_cost": None, "acquired": {"via": "inbound", "ref_id": po["id"], "date": now_iso()},
        "rfid_tag_id": None, "is_remnant": False,
        "created_at": now_iso(), "updated_at": now_iso(),
        "created_by": "seed", "created_by_name": "System Seed",
    })
    await db.wms_tasks.insert_one({
        "id": task_id, "flow_type": "inbound", "source_type": "purchase_order",
        "task_subtype": "receiving", "po_id": po["id"], "po_number": po.get("po_number", ""),
        "product_id": pid, "sku": prod.get("sku", ""), "product_name": prod.get("name", ""),
        "warehouse_id": wid, "warehouse_name": wh.get("name", ""),
        "expected_qty": qqty, "received_qty": qqty, "quantity": qqty, "quarantine_qty": qqty,
        "unit": prod.get("base_unit", "yard"), "status": "qc_pending", "qc_status": "pending",
        "supplier_name": po.get("supplier_name", ""), "lot": lot,
        "lot_ids": [_qc_lot["id"]], "lot_numbers": [_qc_lot["lot_number"]],
        "created_at": now_iso(), "updated_at": now_iso(), "created_by": "seed",
    })
    await rebuild_balance(pid, wid, owner)
    print(f"✅ QC demo: 1 task qc_pending + roll quarantine {qqty}m ({prod.get('name','')})")



async def seed_rfid():
    """Fase 5 — RFID Simulator demo: devices (gate/reader) + encode tag roll on-hand
    + beberapa pembacaan (fixed reader sweep + gate hijau/merah)."""
    from services import rfid_service as rfid
    all_ids = [e["id"] for e in await db.business_entities.find({}, {"_id": 0, "id": 1}).to_list(100)]
    dev_res = await rfid.seed_default_devices("System Seed")

    # Encode tag untuk roll fisik on-hand (per pemilik).
    rolls = await db.inventory_rolls.find(
        {"length_remaining": {"$gt": 0}, "status": {"$in": rfid.PHYSICAL_STATUSES},
         "$or": [{"rfid_tag_id": None}, {"rfid_tag_id": {"$exists": False}}]},
        {"_id": 0, "id": 1, "owner_entity_id": 1}).to_list(500)
    encoded = 0
    for r in rolls:
        try:
            await rfid.encode_tag(r["id"], [r.get("owner_entity_id")], actor_name="System Seed")
            encoded += 1
        except Exception:  # noqa: BLE001
            continue

    # Fixed reader sweep (inventory read) di tiap gudang.
    reads = 0
    for dev in dev_res.get("devices", []):
        if dev.get("type") == "fixed_reader":
            try:
                res = await rfid.reader_scan(dev["id"], all_ids)
                reads += res.get("scanned", 0)
            except Exception:  # noqa: BLE001
                continue

    # Gate demo: 1 HIJAU (roll reserved) + 1 MERAH (roll available) di gate keluar wh_jakarta.
    gate = await db.rfid_devices.find_one({"type": "gate", "direction": "out", "warehouse_id": "wh_jakarta"}, {"_id": 0})
    if gate:
        for st in ("reserved", "available"):
            roll = await db.inventory_rolls.find_one(
                {"warehouse_id": "wh_jakarta", "status": st, "rfid_tag_id": {"$ne": None}}, {"_id": 0, "id": 1})
            if roll:
                try:
                    await rfid.gate_simulate(gate["id"], roll["id"], all_ids)
                except Exception:  # noqa: BLE001
                    pass
    print(f"✅ RFID demo: {dev_res.get('created', 0)} device, {encoded} tag, {reads} read (sweep) + gate demo")


async def seed_budgets():
    """P1-4/R6.3 — Anggaran (Budget) per entitas: dimensi AKUN COA + KATEGORI BEBAN.

    Nilai anggaran akun diturunkan dari realisasi GL tahun berjalan (× 1.1, dibulatkan)
    agar Budget-vs-Actual bermakna (variance nyata). Anggaran kategori beban (petty cash)
    memakai pagu wajar per kategori. Ditambah kebijakan over-budget default per entitas
    (`fin_budget_rules`, mode=warn). Idempotent.
    """
    from services import budget_service as bs
    await db.budgets.delete_many({})
    await db.fin_budget_rules.delete_many({})
    year = datetime.now(timezone.utc).year
    amap = {a["code"]: a for a in await db.gl_accounts.find(
        {"type": {"$in": ["income", "expense"]}, "is_postable": True},
        {"_id": 0, "code": 1, "name": 1, "type": 1}).to_list(100)}
    cats = {c["code"]: c for c in await db.expense_categories.find(
        {}, {"_id": 0, "code": 1, "label": 1, "account_code": 1}).to_list(200)}
    # Pagu tahunan kategori beban petty cash (Rp) — dimensi "category".
    CATEGORY_BUDGETS = {
        "transportasi": 24_000_000, "atk": 6_000_000, "utilitas_kantor": 18_000_000,
        "lunch_snack_entertainment": 12_000_000, "petty_cash_lain": 9_000_000,
    }
    docs = []
    for ent in ["ent_ksc", "ent_kanda"]:
        actuals = await bs._actual_by_account({"entity_id": ent}, year)
        for code, acc in amap.items():
            act = round(sum(actuals.get(code, {}).values()), 2)
            if abs(act) < 1:
                continue  # hanya akun dengan aktivitas
            amount = max(round(abs(act) * 1.1 / 1000) * 1000, 1000)
            docs.append({
                "id": new_id("budget"), "entity_id": ent, "year": year, "month": 0,
                "dimension": "account", "key": code, "label": acc["name"],
                "account_code": code, "account_name": acc["name"], "account_type": acc["type"],
                "amount": float(amount), "note": "Anggaran tahunan (seed)",
                "created_at": now_iso(), "updated_at": now_iso(),
            })
        # R6.3 — anggaran belanja persediaan (target komitmen PO default 1-1300)
        inv_acc = await db.gl_accounts.find_one({"code": bs.DEFAULT_PO_BUDGET_ACCOUNT}, {"_id": 0})
        if inv_acc:
            docs.append({
                "id": new_id("budget"), "entity_id": ent, "year": year, "month": 0,
                "dimension": "account", "key": bs.DEFAULT_PO_BUDGET_ACCOUNT,
                "label": inv_acc.get("name", "Persediaan Barang"),
                "account_code": bs.DEFAULT_PO_BUDGET_ACCOUNT,
                "account_name": inv_acc.get("name", "Persediaan Barang"),
                "account_type": inv_acc.get("type", "asset"),
                "amount": 900_000_000.0 if ent == "ent_ksc" else 250_000_000.0,
                "note": "Anggaran belanja persediaan (seed) — target komitmen PO",
                "created_at": now_iso(), "updated_at": now_iso(),
            })
        for code, amount in CATEGORY_BUDGETS.items():
            cat = cats.get(code)
            if not cat:
                continue
            factor = 1.0 if ent == "ent_ksc" else 0.5
            docs.append({
                "id": new_id("budget"), "entity_id": ent, "year": year, "month": 0,
                "dimension": "category", "key": code, "label": cat.get("label", code),
                "account_code": cat.get("account_code", ""),
                "account_name": amap.get(cat.get("account_code", ""), {}).get("name", ""),
                "account_type": amap.get(cat.get("account_code", ""), {}).get("type", "expense"),
                "amount": float(round(amount * factor)), "note": "Pagu kategori petty cash (seed)",
                "created_at": now_iso(), "updated_at": now_iso(),
            })
        await db.fin_budget_rules.update_one(
            {"entity_id": ent},
            {"$set": {"entity_id": ent, "mode": "warn", "warn_threshold_pct": 85.0,
                      "unbudgeted_action": "allow", "enforce_po_create": True,
                      "enforce_po_approve": True, "updated_by": "seed", "updated_at": now_iso()},
             "$setOnInsert": {"id": new_id("bgrule")}}, upsert=True)
    if docs:
        await db.budgets.insert_many(docs)
    n_cat = sum(1 for d in docs if d["dimension"] == "category")
    print(f"✅ Budgets seeded ({len(docs)}: {len(docs) - n_cat} akun + {n_cat} kategori) + rules 2 entitas")


MAKLOON_SEED = [
    {"id": "mak_seed_tenun", "name": "PT Tenun Nusantara Jaya", "city": "Majalaya",
     "pic": "Bpk. Asep", "phone": "0812-2000-1001", "process_types": ["tenun"],
     "tariff": 3500, "tariff_unit": "output", "capacity": 50000, "cap_unit": "yard", "lead": 10,
     "note": "Spesialis tenun ATBM & mesin; kapasitas besar."},
    {"id": "mak_seed_celup", "name": "CV Celup Warna Abadi", "city": "Pekalongan",
     "pic": "Ibu Retno", "phone": "0812-2000-1002", "process_types": ["celup", "finishing"],
     "tariff": 2500, "tariff_unit": "output", "capacity": 40000, "cap_unit": "yard", "lead": 7,
     "note": "Pencelupan reaktif & pigmen; matching Pantone."},
    {"id": "mak_seed_finishing", "name": "UD Finishing Prima", "city": "Bandung",
     "pic": "Bpk. Deni", "phone": "0812-2000-1003", "process_types": ["finishing"],
     "tariff": 1500, "tariff_unit": "output", "capacity": 60000, "cap_unit": "yard", "lead": 5,
     "note": "Calendering, sanforize, coating."},
    # ── FASE T — mitra untuk tahapan yang SEBELUMNYA tidak punya satu pun mitra.
    # Gate INV-DOMAIN-06 (aturan E) memerah untuk `rajut`, `pre_treatment`, `screen`,
    # dan `printing`: tahapnya ada di master & papan, tetapi form SPK menuntut memilih
    # mitra dari daftar KOSONG — jalan buntu yang tidak pernah terlihat sebelum gate
    # ini dibuat. Empat mitra di bawah menutup keempatnya.
    {"id": "mak_seed_rajut", "name": "CV Rajut Sentosa Knit", "city": "Bandung",
     "pic": "Bpk. Iwan", "phone": "0812-2000-1004", "process_types": ["rajut"],
     "tariff": 9000, "tariff_unit": "output", "capacity": 25000, "cap_unit": "kg", "lead": 12,
     "note": "Rajut single/double knit; output dikendalikan kg."},
    {"id": "mak_seed_pretreat", "name": "PT Bleaching Pratama", "city": "Pekalongan",
     "pic": "Ibu Sari", "phone": "0812-2000-1005", "process_types": ["pre_treatment"],
     "tariff": 4500, "tariff_unit": "input", "capacity": 45000, "cap_unit": "kg", "lead": 6,
     "note": "Scouring & bleaching — hasil PFD (untuk celup) atau PFP (untuk printing)."},
    {"id": "mak_seed_screen", "name": "UD Kasa Mandiri Screen", "city": "Solo",
     "pic": "Bpk. Yudi", "phone": "0812-2000-1006", "process_types": ["screen"],
     "tariff": 750000, "tariff_unit": "output", "capacity": 400, "cap_unit": "roll", "lead": 3,
     "note": "Pembuatan KASA/SCREEN per warna motif. TIDAK menyentuh kain — yang "
             "dibayar jasa pembuatan kasanya (FASE T)."},
    {"id": "mak_seed_printing", "name": "PT Rotary Print Indah", "city": "Bandung",
     "pic": "Ibu Lia", "phone": "0812-2000-1007", "process_types": ["printing"],
     "tariff": 4200, "tariff_unit": "output", "capacity": 70000, "cap_unit": "yard", "lead": 8,
     "note": "Rotary & flat-bed printing; PFP → kain jadi bermotif."},
]


async def seed_makloon_masters():
    """M1 — seed master Makloon + Resep Proses (contoh generik) + produk Grey output."""
    ent = "ent_ksc"
    # 1) Produk Grey (output tenun) — SHARED, dibuat bila belum ada.
    grey = await db.products.find_one({"sku": "GREY-KTN-001"}, {"_id": 0})
    if not grey:
        grey = {
            "id": "prod_grey_katun", "sku": "GREY-KTN-001", "name": "Kain Grey Katun (per Yard)",
            "category": "Grey", "variant": "Standard", "color": "Putih",
            "color_code": "KN-WHT-02", "color_name": "Putih Broken", "color_hex": "#ECEAE0",
            "motif": "-", "grade": "A", "stage": "grey", "fabric_type": "woven",
            "supplier": "Makloon Tenun",
            "base_unit": "yard", "price": 0, "harga_pokok": 34000, "gramasi": 120, "lebar": 1.15,
            "image": "", "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "reorder_point": 500.0, "reorder_qty": 1000.0,
            "description": "Kain grey katun hasil tenun (WIP), belum dicelup — output resep Tenun.",
            "created_at": ago(days=180), "updated_at": ago(days=10),
        }
        await db.products.insert_one(grey)
    grey_id = grey["id"]
    # M3 — Produk BARANG SISA (leftover bahan input dari makloon) — master tersendiri.
    #   Tenun: sisa = benang (kg). Celup: sisa = grey (yard). Diterima saat receive makloon.
    sisa_defs = [
        {"id": "prod_benang_sisa", "sku": "BNG-KTN-SISA", "name": "Benang Katun Sisa (per Kg)",
         "category": "Barang Sisa", "stage": "yarn", "base_unit": "kg", "gramasi": 0, "lebar": 0,
         "yarn_count": "30s", "yarn_count_system": "Ne",
         "desc": "Sisa benang katun kembalian dari proses tenun makloon (reusable)."},
        {"id": "prod_grey_sisa", "sku": "GREY-KTN-SISA", "name": "Kain Grey Katun Sisa (per Yard)",
         "category": "Barang Sisa", "stage": "grey", "base_unit": "yard", "gramasi": 120, "lebar": 1.15,
         "yarn_count": "", "yarn_count_system": "",
         "desc": "Sisa kain grey kembalian dari proses celup makloon (reusable)."},
    ]
    for sd in sisa_defs:
        if not await db.products.find_one({"id": sd["id"]}, {"_id": 0}):
            await db.products.insert_one({
                "id": sd["id"], "sku": sd["sku"], "name": sd["name"], "category": sd["category"],
                "variant": "Sisa", "color": "-", "color_code": "", "color_name": "", "color_hex": "#D8D8D8",
                "motif": "-", "grade": "B", "stage": sd["stage"], "fabric_type": "woven",
                "yarn_count": sd["yarn_count"], "yarn_count_system": sd["yarn_count_system"],
                "supplier": "Makloon",
                "base_unit": sd["base_unit"], "price": 0, "harga_pokok": 0,
                "gramasi": sd["gramasi"], "lebar": sd["lebar"], "image": "", "status": "active",
                "uom_conversions": [], "batch_lot_rolls": [], "reorder_point": 0.0, "reorder_qty": 0.0,
                "is_remnant_master": True, "description": sd["desc"],
                "created_at": ago(days=180), "updated_at": ago(days=10),
            })
    benang = await db.products.find_one({"sku": "BNG-KTN-001"}, {"_id": 0})
    finished = await db.products.find_one({"sku": "BTK-MEGA-001"}, {"_id": 0})
    benang_id = benang["id"] if benang else ""
    finished_id = finished["id"] if finished else ""

    # FASE T — produk PFP (Prepared For Printing). Tanpa produk tahap `pfp`, jalur
    # printing tidak bisa dicontohkan sama sekali: pemilihan tahap `screen`/`printing`
    # ada di layar, tetapi tidak ada kain yang boleh masuk ke dalamnya. GSM & lebar
    # disamakan dengan grey supaya rumus estimasi (GSM × lebar) menghasilkan angka
    # yang wajar dan bisa dibaca manusia.
    if not await db.products.find_one({"id": "prod_pfp_katun"}, {"_id": 0}):
        await db.products.insert_one({
            "id": "prod_pfp_katun", "sku": "PFP-KTN-001",
            "name": "Kain PFP Katun (siap print, per Yard)",
            "category": "PFP", "variant": "Standard", "color": "Putih",
            "color_code": "KN-WHT-02", "color_name": "Putih Bleached", "color_hex": "#F7F6F2",
            "motif": "-", "grade": "A", "stage": "pfp", "fabric_type": "woven",
            "line_code": "printing", "supplier": "Makloon Pre-Treatment",
            "base_unit": "yard", "price": 0, "harga_pokok": 41000,
            "gramasi": 120, "lebar": 1.15,
            "image": "", "status": "active", "uom_conversions": [], "batch_lot_rolls": [],
            "reorder_point": 300.0, "reorder_qty": 800.0,
            "description": "Kain katun sudah pre-treatment (scouring/bleaching) dengan "
                           "tujuan PRINTING — output tahap PFP, input tahap Screen & Printing.",
            "created_at": ago(days=180), "updated_at": ago(days=10),
        })

    # 2) Makloons
    mdocs = []
    for i, m in enumerate(MAKLOON_SEED):
        mdocs.append({
            "id": m["id"], "code": f"MAK-{i + 1:05d}", "name": m["name"],
            "npwp": "", "pic_name": m["pic"], "phone": m["phone"], "email": "",
            "address": "", "city": m["city"], "process_types": m["process_types"],
            "capacity_note": m["note"], "capacity_per_month": float(m["capacity"]),
            "capacity_unit": m["cap_unit"], "default_tariff": float(m["tariff"]),
            "tariff_unit": m["tariff_unit"], "payment_term_code": "", "lead_time_days": m["lead"],
            "entity_id": ent, "notes": "", "status": "active", "created_by": "Seed",
            "created_at": ago(days=170), "updated_at": ago(days=10),
        })
    await db.makloons.insert_many(mdocs)

    # 3) Process recipes (contoh generik)
    rdocs = [
        {"id": "prcp_seed_tenun", "name": "Tenun: Benang Katun → Grey Katun",
         "process_type": "tenun", "input_product_id": benang_id, "input_stage": "yarn",
         "output_product_id": grey_id, "output_stage": "grey",
         "yield_factor": 3.8, "waste_pct": 4, "byproduct_pct": 2, "byproduct_product_id": "prod_benang_sisa",
         "default_makloon_id": "mak_seed_tenun", "default_tariff": 3500, "tariff_unit": "output",
         "aux_cost_default": 0, "formula": "", "notes": "Yield ± 3.8 yard grey per kg benang.",
         "entity_id": ent, "status": "active", "created_by": "Seed",
         "created_at": ago(days=160), "updated_at": ago(days=10)},
        {"id": "prcp_seed_celup", "name": "Celup: Grey Katun → Batik Mega (Finished)",
         "process_type": "celup", "input_product_id": grey_id, "input_stage": "grey",
         "output_product_id": finished_id, "output_stage": "finished", "byproduct_product_id": "prod_grey_sisa",
         "yield_factor": 0.95, "waste_pct": 5, "byproduct_pct": 3,
         "default_makloon_id": "mak_seed_celup", "default_tariff": 2500, "tariff_unit": "output",
         "aux_cost_default": 500, "formula": "", "notes": "Susut celup ± 5%, sisa ± 3%.",
         "entity_id": ent, "status": "active", "created_by": "Seed",
         "created_at": ago(days=150), "updated_at": ago(days=10)},
    ]
    await db.process_recipes.insert_many(rdocs)
    print(f"✅ Makloon masters seeded ({len(mdocs)} makloon, {len(rdocs)} resep, +1 produk Grey)")


async def seed_makloon_contracts():
    """FASE D — seed KONTRAK MITRA MAKLOON (`supplier_contracts`) untuk 3 mitra seed.

    Kontrak = SSOT tarif (D-07 basis bebas), susut standar (D-05) & toleransi selisih (D-09).
    Dipanggil SETELAH `seed_makloon_masters()` dan SEBELUM `seed_makloon_orders()` agar
    order makloon otomatis ter-resolve ke kontrak aktif (jejak `steps[].contract_id`).
    Idempotent: dilewati bila koleksi sudah berisi kontrak.
    """
    if await db.supplier_contracts.count_documents({"contract_type": "makloon"}) > 0:
        print("ℹ️  kontrak makloon sudah ada — seed kontrak makloon dilewati")
        return 0
    import sys as _sys
    _sys.path.insert(0, "/app/backend")
    from services import contract_service as _cs

    ent = "ent_ksc"
    vf = ago(days=120)[:10]
    vt = (datetime.now(timezone.utc) + timedelta(days=245)).isoformat()[:10]
    defs = [
        {   # Tenun — tarif per KG BAHAN MASUK (basis input): realistis untuk makloon tenun.
            "contract_type": "makloon", "partner_id": "mak_seed_tenun",
            "title": "Makloon Tenun Benang Katun 30s → Grey Katun",
            "process_type": "tenun",
            "product_id": "prod_grey_katun", "input_product_id": "prod_benang_katun",
            "tariff_basis": "kg", "tariff_rate": 13500, "tariff_qty_source": "input",
            "shrinkage_pct": 4, "tolerance_pct": 4, "yield_factor": 3.8, "byproduct_pct": 2,
            "min_charge": 500000, "moq": 10, "lead_time_days": 10,
            "payment_term_code": "NET30", "valid_from": vf, "valid_to": vt,
            "notes": "Ongkos tenun dihitung per kg benang masuk. Susut standar 4%, "
                     "toleransi selisih 4% sebelum klaim.",
        },
        {   # Celup — tarif per YARD OUTPUT + biaya screen/repeat (aux_fees).
            "contract_type": "makloon", "partner_id": "mak_seed_celup",
            "title": "Makloon Celup & Print Grey Katun → Batik Mega",
            "process_type": "celup",
            "product_id": "prod_batik_mega", "input_product_id": "prod_grey_katun",
            "tariff_basis": "yard", "tariff_rate": 2600, "tariff_qty_source": "output",
            "aux_fees": [
                {"code": "screen", "label": "Biaya screen per warna", "basis": "per_color", "amount": 120000},
                {"code": "repeat", "label": "Biaya repeat motif", "basis": "per_repeat", "amount": 65000},
            ],
            "shrinkage_pct": 5, "tolerance_pct": 3, "byproduct_pct": 3,
            "min_charge": 750000, "moq": 50, "lead_time_days": 7,
            "payment_term_code": "NET30", "valid_from": vf, "valid_to": vt,
            "notes": "Tarif per yard hasil celup + screen per warna & repeat motif. "
                     "Toleransi selisih 3% (pencelupan lebih presisi).",
        },
        {   # Finishing — lumpsum per batch (contoh basis lumpsum).
            "contract_type": "makloon", "partner_id": "mak_seed_finishing",
            "title": "Makloon Finishing (Calender & Sanforize) — Lumpsum per Batch",
            "process_type": "finishing",
            "tariff_basis": "lumpsum", "tariff_rate": 1850000, "tariff_qty_source": "output",
            "shrinkage_pct": 2, "tolerance_pct": 2.5,
            "moq": 0, "lead_time_days": 5,
            "payment_term_code": "NET14", "valid_from": vf, "valid_to": vt,
            "notes": "Borongan per batch finishing (maks 1 batch ≈ 2.000 yard).",
        },
        # ── FASE T — kontrak untuk jalur PRINTING (pre-treatment → screen → printing).
        # Tarif screen SENGAJA lumpsum: yang dibayar pembuatan kasanya (per set motif),
        # bukan panjang kain — kainnya bahkan tidak selalu dikirim.
        {
            "contract_type": "makloon", "partner_id": "mak_seed_pretreat",
            "title": "Makloon Pre-Treatment Grey → PFP (siap print)",
            "process_type": "pre_treatment",
            "product_id": "prod_pfp_katun", "input_product_id": "prod_grey_katun",
            "tariff_basis": "kg", "tariff_rate": 4500, "tariff_qty_source": "input",
            "shrinkage_pct": 2, "tolerance_pct": 3,
            "min_charge": 300000, "moq": 20, "lead_time_days": 6,
            "payment_term_code": "NET30", "valid_from": vf, "valid_to": vt,
            "notes": "Scouring & bleaching dengan tujuan printing (target_use=print → PFP). "
                     "Ongkos per kg kain masuk.",
        },
        {
            "contract_type": "makloon", "partner_id": "mak_seed_screen",
            "title": "Makloon Pembuatan KASA/SCREEN per Set Motif — Lumpsum",
            "process_type": "screen",
            "tariff_basis": "lumpsum", "tariff_rate": 750000, "tariff_qty_source": "output",
            "aux_fees": [
                {"code": "screen_color", "label": "Kasa tambahan per warna",
                 "basis": "per_color", "amount": 250000},
            ],
            # Susut & toleransi 0 BUKAN kelalaian: tahap ini tidak mengubah kain,
            # jadi tidak ada yang bisa susut dan tidak ada selisih yang bisa diklaim.
            "shrinkage_pct": 0, "tolerance_pct": 0,
            "moq": 0, "lead_time_days": 3,
            "payment_term_code": "NET14", "valid_from": vf, "valid_to": vt,
            "notes": "Borongan per set kasa + Rp 250.000 per warna tambahan. TIDAK "
                     "mengubah kain: qty keluar = qty masuk (FASE T).",
        },
        {
            "contract_type": "makloon", "partner_id": "mak_seed_printing",
            "title": "Makloon Printing PFP → Batik Mega (per yard)",
            "process_type": "printing",
            "product_id": "prod_batik_mega", "input_product_id": "prod_pfp_katun",
            "tariff_basis": "yard", "tariff_rate": 4200, "tariff_qty_source": "output",
            "aux_fees": [
                {"code": "repeat", "label": "Biaya repeat motif", "basis": "per_repeat",
                 "amount": 65000},
            ],
            "shrinkage_pct": 3, "tolerance_pct": 3,
            "min_charge": 500000, "moq": 30, "lead_time_days": 8,
            "payment_term_code": "NET30", "valid_from": vf, "valid_to": vt,
            "notes": "Rotary printing per yard hasil + repeat motif.",
        },
    ]
    made = 0
    for d in defs:
        try:
            c = await _cs.create_contract(d, entity_id=ent, actor="Seed")
            made += 1
            print(f"   · {c['contract_number']} — {c['partner_name']} · {d['process_type']} "
                  f"· {d['tariff_basis']} @ Rp {float(d['tariff_rate']):,.0f}")
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] kontrak {d.get('partner_id')} dilewati: {_e}")
    print(f"✅ Kontrak mitra makloon seeded ({made} kontrak · tarif/susut/toleransi terkunci per dokumen)")
    return made


async def seed_makloon_orders():
    """M3 — seed contoh Order Makloon: 1 SELESAI (isi scorecard/costing/tagihan) + 1 DIPROSES
    (tampilkan bucket 'Di Makloon / WIP-Vendor'). Pakai service SSOT agar GL & roll konsisten.
    Dipanggil PALING AKHIR (setelah GL opening-balance true-up) agar rekonsiliasi 1-1300 tetap utuh.
    Set env SKIP_SEED_MAKLOON_ORDERS=1 untuk melewati (mis. saat test isolasi butuh stok penuh)."""
    import os as _os
    if _os.environ.get("SKIP_SEED_MAKLOON_ORDERS"):
        print("  [skip] seed_makloon_orders dilewati (SKIP_SEED_MAKLOON_ORDERS set)")
        return 0
    benang = await db.products.find_one({"sku": "BNG-KTN-001"}, {"_id": 0})
    if not benang:
        print("  [warn] seed_makloon_orders dilewati: produk benang tak ada")
        return 0
    benang_id = benang["id"]
    avail = await db.inventory_balances.find_one(
        {"product_id": benang_id, "warehouse_id": "wh_surabaya", "owner_entity_id": "ent_ksc"},
        {"_id": 0, "available_qty": 1})
    if not avail or float(avail.get("available_qty", 0)) < 55:
        print(f"  [warn] seed_makloon_orders dilewati: stok benang wh_surabaya kurang ({(avail or {}).get('available_qty')})")
        return 0

    from services.makloon_order_service import create_makloon_order, issue_step, receive_step

    # PS-03 — yield 3.8 yard/kg di contoh ini adalah OVERRIDE sadar atas rumus GSM,
    # jadi ia WAJIB membawa alasan. Pagar `assert_yield_reason` kini berdiri di service
    # sehingga SEMUA penulis mematuhinya, termasuk seed ini — dulu pagar itu hanya ada
    # di router, jadi data demo lahir dengan override tanpa alasan dan **tidak bisa
    # dibuat ulang lewat API aplikasinya sendiri**. Alasannya menyebut kontrak yang
    # menjadi dasar angkanya supaya bisa ditelusuri, bukan kalimat hiasan.
    _ctr_tenun = await db.supplier_contracts.find_one(
        {"partner_id": "mak_seed_tenun", "process_type": "tenun", "status": "active"},
        {"_id": 0, "contract_number": 1})
    _yield_reason = (
        f"Kontrak {_ctr_tenun['contract_number']} menetapkan yield 3.8 yard/kg"
        if _ctr_tenun else
        "Riwayat produksi mitra tenun: 3.8 yard grey per kg benang")

    def _step(qty_out):
        return {"process_type": "tenun", "makloon_id": "mak_seed_tenun", "recipe_id": "prcp_seed_tenun",
                "input_product_id": benang_id, "output_product_id": "prod_grey_katun",
                "yield_factor": 3.8, "yield_override_reason": _yield_reason,
                "waste_pct": 4, "byproduct_pct": 2, "tariff": 3500}
    base = {"mode": "process_only", "material_product_id": benang_id, "material_unit": "kg",
            "from_warehouse_id": "wh_surabaya", "target_warehouse_id": "wh_surabaya"}

    # 1) Order SELESAI (30 kg → ~109 yard grey)
    o1 = await create_makloon_order({**base, "material_qty": 30, "steps": [_step(None)],
                                     "notes": "Contoh order makloon selesai (tenun)."},
                                    entity_id="ent_ksc", actor_name="Seed")
    await issue_step(o1["id"], 1, from_warehouse_id="wh_surabaya", actor_name="Seed")
    out_qty = 109.0
    await receive_step(o1["id"], 1, {
        "step_seq": 1, "actual_output_qty": out_qty, "actual_byproduct_qty": 1,
        "tariff": round(3500 * out_qty, 0), "aux_cost": 0, "ppn": 0,
        "output_warehouse_id": "wh_surabaya", "byproduct_lot": "SISA-MKO-S1",
        "rolls": [{"lot": "GREY-MKO-S1A", "length": 60, "grade": "A"},
                  {"lot": "GREY-MKO-S1B", "length": 49, "grade": "A"}],
    }, actor_name="Seed")

    # 2) Order DIPROSES (20 kg masih di makloon → bucket subcon)
    o2 = await create_makloon_order({**base, "material_qty": 20, "steps": [_step(None)],
                                     "notes": "Contoh order makloon sedang diproses (WIP di vendor)."},
                                    entity_id="ent_ksc", actor_name="Seed")
    await issue_step(o2["id"], 1, from_warehouse_id="wh_surabaya", actor_name="Seed")

    made = 2
    # 3) FASE D — Order RANTAI 2 LANGKAH (tenun → celup) memakai KONTRAK mitra, dengan
    #    langkah 1 diterima MELEBIHI TOLERANSI → klaim otomatis terbuka lalu DIAJUKAN
    #    (status `pending_approval`) agar layar persetujuan klaim punya data nyata.
    made += await _seed_makloon_chain_with_claim(benang_id, base, avail)
    # 4) FASE T — Order JALUR PRINTING 3 LANGKAH: pre-treatment → SCREEN → printing.
    made += await _seed_makloon_screen_printing()
    print(f"✅ Makloon orders seeded ({made} order: 1 selesai + 1 diproses"
          + (" + 1 rantai 2-langkah dgn klaim menunggu persetujuan" if made > 2 else "")
          + (" + 1 jalur printing ber-SCREEN (FASE T)" if made > 3 else "") + ")")
    return made


async def _seed_makloon_screen_printing():
    """FASE T — SPK jalur printing 3 langkah: pre-treatment → **SCREEN** → printing.

    Kenapa ini ada di data demo (dan bukan cukup dijelaskan di dokumen): tahap Screen
    berperilaku BERBEDA dari semua tahap lain — kainnya tidak berubah dan (di contoh
    ini) bahkan tidak bergerak. Satu-satunya cara pemilik bisa memeriksa bahwa
    perilakunya benar adalah melihat SPK sungguhan: qty langkah 2 keluar = masuk,
    tidak ada roll baru lahir, biaya kasanya menempel ke HPP kain cetak di langkah 3.

    Keadaan akhir: SELESAI, sehingga WIP 1-1350 kembali nol dan biaya kasa terlihat
    sebagai bagian HPP kain jadi (bukan beban yang menggantung).
    Return 1 bila berhasil, 0 bila prasyaratnya belum ada (tidak menggagalkan seed).
    """
    import sys as _sys
    _sys.path.insert(0, "/app/backend")
    from services.makloon_order_service import (
        create_makloon_order, issue_step, receive_step, record_service_step)

    grey = await db.products.find_one({"id": "prod_grey_katun"}, {"_id": 0})
    pfp = await db.products.find_one({"id": "prod_pfp_katun"}, {"_id": 0})
    if not grey or not pfp:
        print("  [info] SPK printing ber-screen dilewati: produk grey/PFP belum ada")
        return 0
    bal = await db.inventory_balances.find_one(
        {"product_id": "prod_grey_katun", "warehouse_id": "wh_surabaya",
         "owner_entity_id": "ent_ksc"}, {"_id": 0, "available_qty": 1})
    qty = 40.0
    avail_qty = float((bal or {}).get("available_qty", 0))
    if avail_qty < qty:
        print(f"  [info] SPK printing ber-screen dilewati: stok grey wh_surabaya "
              f"{avail_qty:g} yard < {qty:g} yard")
        return 0

    async def _ctr(pid, pt):
        return await db.supplier_contracts.find_one(
            {"partner_id": pid, "process_type": pt, "status": "active"}, {"_id": 0})

    c_pre = await _ctr("mak_seed_pretreat", "pre_treatment")
    c_scr = await _ctr("mak_seed_screen", "screen")
    c_prn = await _ctr("mak_seed_printing", "printing")
    if not (c_pre and c_scr and c_prn):
        print("  [info] SPK printing ber-screen dilewati: kontrak pre_treatment/screen/"
              "printing belum ada")
        return 0

    try:
        o = await create_makloon_order({
            "mode": "process_only", "material_product_id": "prod_grey_katun",
            "material_qty": qty, "material_unit": "yard",
            "from_warehouse_id": "wh_surabaya", "target_warehouse_id": "wh_surabaya",
            "notes": "FASE T — jalur printing: pre-treatment (grey→PFP) → pembuatan KASA "
                     "(jasa murni, kain tidak bergerak) → printing (PFP→kain jadi).",
            "steps": [
                {"stage_code": "pfp", "makloon_id": "mak_seed_pretreat",
                 "contract_id": c_pre["id"], "input_product_id": "prod_grey_katun",
                 "output_product_id": "prod_pfp_katun"},
                # Kain TIDAK dikirim: `material_flow="service_only"`. Produk output
                # sengaja tidak diisi — tahap ini tidak mengubah kain, jadi mesin
                # mengisinya sendiri dengan kain yang sama (dan mencatat alasannya).
                {"stage_code": "screen", "material_flow": "service_only",
                 "makloon_id": "mak_seed_screen", "contract_id": c_scr["id"],
                 "input_product_id": "prod_pfp_katun", "colors": 3},
                {"stage_code": "printing", "makloon_id": "mak_seed_printing",
                 "contract_id": c_prn["id"], "input_product_id": "prod_pfp_katun",
                 "output_product_id": "prod_batik_mega", "colors": 3, "repeats": 2},
            ],
        }, entity_id="ent_ksc", actor_name="Seed")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] SPK printing ber-screen gagal dibuat: {_e}")
        return 0

    try:
        # Langkah 1 — pre-treatment: kain DIKIRIM & kembali sebagai PFP.
        await issue_step(o["id"], 1, from_warehouse_id="wh_surabaya", actor_name="Seed")
        doc = await db.makloon_orders.find_one({"id": o["id"]}, {"_id": 0})
        exp1 = float((doc.get("steps") or [{}])[0].get("expected_output_qty") or qty * 0.98)
        act1 = round(exp1, 2)
        half1 = round(act1 / 2, 2)
        await receive_step(o["id"], 1, {
            "step_seq": 1, "actual_output_qty": act1, "actual_byproduct_qty": 0,
            "aux_cost": 0, "ppn": 0, "output_warehouse_id": "wh_surabaya",
            "supplier_invoice_no": "INV-BLP-2026-0091",
            "rolls": [{"lot": "PFP-BLP-A1", "length": half1, "grade": "A"},
                      {"lot": "PFP-BLP-A2", "length": round(act1 - half1, 2), "grade": "A"}],
        }, actor_name="Seed")

        # Langkah 2 — SCREEN: tidak ada issue, tidak ada roll. Hanya tagihan jasa.
        await record_service_step(o["id"], 2, {
            "step_seq": 2, "aux_cost": 0, "ppn": 0, "colors": 3,
            "supplier_invoice_no": "INV-KSM-2026-0043",
            "note": "3 kasa (1 set motif Mega Mendung, 3 warna). Kain tidak dikirim.",
        }, actor_name="Seed")

        # Langkah 3 — PRINTING: kain dikirim lagi; di sinilah biaya kasa TERSERAP.
        await issue_step(o["id"], 3, from_warehouse_id="wh_surabaya", actor_name="Seed")
        doc = await db.makloon_orders.find_one({"id": o["id"]}, {"_id": 0})
        step3 = next((s for s in doc.get("steps") or [] if int(s.get("seq")) == 3), {})
        exp3 = float(step3.get("expected_output_qty") or act1 * 0.97)
        act3 = round(exp3, 2)
        half3 = round(act3 / 2, 2)
        await receive_step(o["id"], 3, {
            "step_seq": 3, "actual_output_qty": act3, "actual_byproduct_qty": 0,
            "aux_cost": 0, "ppn": 0, "output_warehouse_id": "wh_surabaya",
            "supplier_invoice_no": "INV-RPI-2026-0177", "colors": 3, "repeats": 2,
            "rolls": [{"lot": "PRINT-RPI-B1", "length": half3, "grade": "A",
                       "dye_lot": "MEGA-2026-03"},
                      {"lot": "PRINT-RPI-B2", "length": round(act3 - half3, 2), "grade": "A",
                       "dye_lot": "MEGA-2026-03"}],
        }, actor_name="Seed")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] SPK printing ber-screen berhenti di tengah: {_e}")
        return 1

    final = await db.makloon_orders.find_one({"id": o["id"]}, {"_id": 0})
    scr = next((s for s in final.get("steps") or [] if int(s.get("seq")) == 2), {})
    prn = next((s for s in final.get("steps") or [] if int(s.get("seq")) == 3), {})
    print(f"   · {final.get('mko_number')} — pre-treatment → SCREEN → printing · "
          f"kasa Rp {float(scr.get('service_value') or 0):,.0f} "
          f"(qty {scr.get('input_qty')} → {scr.get('actual_output_qty')} yard, kain utuh) "
          f"→ terserap ke HPP printing Rp "
          f"{float(prn.get('absorbed_service_value') or 0):,.0f}")

    # ── SPK kedua: PRE-TREATMENT SAJA, hasilnya DIBIARKAN di gudang ──────────
    # Kenapa perlu: sesudah SPK di atas selesai, stok PFP habis terpakai printing.
    # Tanpa sisa PFP, pemilik TIDAK BISA mencoba sendiri tahap Screen/Printing dari
    # layar (form-nya ada, tetapi tidak ada kain yang boleh masuk) — dan itu persis
    # kelas "fitur ada tapi tak bisa dicoba" yang membuat orang menyimpulkan fiturnya
    # rusak. 25 yard grey disisihkan supaya jalur printing bisa dijalankan tangan.
    made = 1
    bal2 = await db.inventory_balances.find_one(
        {"product_id": "prod_grey_katun", "warehouse_id": "wh_surabaya",
         "owner_entity_id": "ent_ksc"}, {"_id": 0, "available_qty": 1})
    qty2 = 25.0
    if float((bal2 or {}).get("available_qty") or 0) < qty2:
        print(f"  [info] SPK 'PFP siap print' dilewati: sisa grey "
              f"{float((bal2 or {}).get('available_qty') or 0):g} yard < {qty2:g}")
        return made
    try:
        o2 = await create_makloon_order({
            "mode": "process_only", "material_product_id": "prod_grey_katun",
            "material_qty": qty2, "material_unit": "yard",
            "from_warehouse_id": "wh_surabaya", "target_warehouse_id": "wh_surabaya",
            "notes": "FASE T — stok PFP siap print. Buat SPK baru berisi tahap SCREEN "
                     "(pilih 'jasa murni' atau 'kain dikirim') lalu PRINTING untuk "
                     "mencoba jalurnya sendiri.",
            "steps": [{"stage_code": "pfp", "makloon_id": "mak_seed_pretreat",
                       "contract_id": c_pre["id"], "input_product_id": "prod_grey_katun",
                       "output_product_id": "prod_pfp_katun"}],
        }, entity_id="ent_ksc", actor_name="Seed")
        await issue_step(o2["id"], 1, from_warehouse_id="wh_surabaya", actor_name="Seed")
        d2 = await db.makloon_orders.find_one({"id": o2["id"]}, {"_id": 0})
        exp2 = float((d2.get("steps") or [{}])[0].get("expected_output_qty") or qty2 * 0.98)
        act2 = round(exp2, 2)
        await receive_step(o2["id"], 1, {
            "step_seq": 1, "actual_output_qty": act2, "actual_byproduct_qty": 0,
            "aux_cost": 0, "ppn": 0, "output_warehouse_id": "wh_surabaya",
            "supplier_invoice_no": "INV-BLP-2026-0092",
            "rolls": [{"lot": "PFP-BLP-B1", "length": act2, "grade": "A"}],
        }, actor_name="Seed")
        made = 2
        print(f"   · {d2.get('mko_number')} — pre-treatment saja → {act2:g} yard PFP "
              "TERSEDIA di gudang (bahan untuk mencoba Screen & Printing dari layar)")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] SPK 'PFP siap print' dilewati: {_e}")
    return made


async def _seed_makloon_chain_with_claim(benang_id, base, avail):
    """FASE D — order rantai tenun→celup berbasis kontrak + klaim `pending_approval`.

    Dipisah agar `seed_makloon_orders` tetap ramping & kegagalan di sini tidak
    membatalkan 2 order dasar. Return jumlah order yang berhasil dibuat (0/1).
    """
    import sys as _sys
    _sys.path.insert(0, "/app/backend")
    from services.makloon_order_service import create_makloon_order, issue_step, receive_step
    from services import makloon_claim_service as _mc

    left = float((avail or {}).get("available_qty", 0)) - 50.0   # sisa setelah order 1 & 2
    qty = 15.0
    if left < qty:
        print(f"  [info] order rantai makloon dilewati: sisa stok benang {left:g} kg < {qty:g} kg")
        return 0
    ctr_tenun = await db.supplier_contracts.find_one(
        {"partner_id": "mak_seed_tenun", "process_type": "tenun", "status": "active"}, {"_id": 0})
    ctr_celup = await db.supplier_contracts.find_one(
        {"partner_id": "mak_seed_celup", "process_type": "celup", "status": "active"}, {"_id": 0})
    if not ctr_tenun or not ctr_celup:
        print("  [info] order rantai makloon dilewati: kontrak mitra belum ada")
        return 0

    try:
        o3 = await create_makloon_order({
            **base, "material_qty": qty,
            "notes": "Rantai 2 langkah berbasis kontrak: tenun (per kg) → celup (per yard + screen).",
            "steps": [
                {"process_type": "tenun", "makloon_id": "mak_seed_tenun",
                 "recipe_id": "prcp_seed_tenun", "contract_id": ctr_tenun["id"],
                 "input_product_id": benang_id, "output_product_id": "prod_grey_katun",
                 "byproduct_product_id": "prod_benang_sisa"},
                {"process_type": "celup", "makloon_id": "mak_seed_celup",
                 "recipe_id": "prcp_seed_celup", "contract_id": ctr_celup["id"],
                 "input_product_id": "prod_grey_katun", "output_product_id": "prod_batik_mega",
                 "byproduct_product_id": "prod_grey_sisa", "colors": 3, "repeats": 2},
            ],
        }, entity_id="ent_ksc", actor_name="Seed")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] order rantai makloon gagal dibuat: {_e}")
        return 0

    await issue_step(o3["id"], 1, from_warehouse_id="wh_surabaya", actor_name="Seed")
    o3d = await db.makloon_orders.find_one({"id": o3["id"]}, {"_id": 0})
    step1 = (o3d.get("steps") or [{}])[0]
    expected = float(step1.get("expected_output_qty") or (qty * 3.8 * 0.96))
    # Hasil mitra 7% di bawah estimasi → LEWAT toleransi kontrak 4% → klaim terbuka.
    actual = round(expected * 0.93, 2)
    half = round(actual / 2, 2)
    await receive_step(o3["id"], 1, {
        "step_seq": 1, "actual_output_qty": actual, "actual_byproduct_qty": 0.4,
        "aux_cost": 0, "ppn": 0, "output_warehouse_id": "wh_surabaya",
        "byproduct_lot": "SISA-TENUN-C1", "supplier_invoice_no": "INV-TNJ-2026-0184",
        "rolls": [{"lot": "GREY-TNJ-C1A", "length": half, "grade": "A"},
                  {"lot": "GREY-TNJ-C1B", "length": round(actual - half, 2), "grade": "A2"}],
    }, actor_name="Seed")

    # Ajukan klaim POTONG BON (menunggu persetujuan manager/admin) — data nyata utk layar approval.
    try:
        await _mc.propose_claim(
            o3["id"], 1, action="potong_bon",
            reason=("Hasil tenun 7% di bawah estimasi kontrak (di luar toleransi 4%). "
                    "Diusulkan potong tagihan jasa mitra sesuai nilai kekurangan."),
            actor="Eko Prasetyo")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] pengajuan klaim seed dilewati: {_e}")
    return 1



async def seed_transfers():
    """Surat Jalan Transfer antar-gudang (intra-entity) — contoh berbagai status.

    Satuan mengikuti kebijakan yard (semua kain). Nomor pakai field `code` (TRF-xxxx).
    Idempotent: hanya seed bila koleksi kosong (aman untuk non-destructive re-seed).
    """
    if await db.warehouse_transfers.count_documents({}) > 0:
        print("ℹ️  warehouse_transfers sudah ada — seed transfer dilewati")
        return 0

    def _wh_name(wid):
        return {"wh_jakarta": "Gudang Jakarta Utara", "wh_bandung": "Gudang Bandung Kopo",
                "wh_surabaya": "Gudang Surabaya Rungkut"}.get(wid, wid)

    def _item(pid, sku, name, qty):
        return {"product_id": pid, "sku": sku, "product_name": name,
                "qty": float(qty), "quantity": float(qty), "unit": "yard",
                "owner_entity_id": "ent_ksc", "lots": [], "rolls": []}

    transfers = [
        {
            "id": "trn_seed_001", "code": "KSC/TRF-00001", "transfer_kind": "intra_entity",
            "entity_id": "ent_ksc",
            "source_warehouse_id": "wh_jakarta", "dest_warehouse_id": "wh_bandung",
            "source_warehouse_name": _wh_name("wh_jakarta"), "dest_warehouse_name": _wh_name("wh_bandung"),
            "status": "completed",
            "items": [_item("prod_batik_mega", "BTK-MEGA-001", "Batik Mega Mendung Premium", 120),
                      _item("prod_tenun_ikat", "TNI-GRGD-001", "Tenun Ikat Garuda Premium", 60)],
            "notes": "Relokasi stok batik & tenun ke Bandung untuk pameran.",
            "requested_by": "Eko Prasetyo", "approved_by": "Dewi Rahayu",
            "created_by": "Eko Prasetyo",
            "created_at": ago(days=20), "updated_at": ago(days=18), "completed_at": ago(days=18),
        },
        {
            "id": "trn_seed_002", "code": "KSC/TRF-00002", "transfer_kind": "intra_entity",
            "entity_id": "ent_ksc",
            "source_warehouse_id": "wh_surabaya", "dest_warehouse_id": "wh_jakarta",
            "source_warehouse_name": _wh_name("wh_surabaya"), "dest_warehouse_name": _wh_name("wh_jakarta"),
            "status": "dispatched",
            "items": [_item("prod_lurik_classic", "LRK-CLSC-001", "Lurik Klasik Solo", 200)],
            "notes": "Kirim lurik ke Jakarta (pesanan retail).",
            "requested_by": "Fitri Handayani", "approved_by": "Dewi Rahayu",
            "created_by": "Fitri Handayani",
            "created_at": ago(days=6), "updated_at": ago(days=4),
        },
        {
            "id": "trn_seed_003", "code": "KSC/TRF-00003", "transfer_kind": "intra_entity",
            "entity_id": "ent_ksc",
            "source_warehouse_id": "wh_jakarta", "dest_warehouse_id": "wh_surabaya",
            "source_warehouse_name": _wh_name("wh_jakarta"), "dest_warehouse_name": _wh_name("wh_surabaya"),
            "status": "waiting_approval",
            "items": [_item("prod_songket_palembang", "SGK-PLB-001", "Songket Palembang Benang Emas", 40),
                      _item("prod_endek_bali", "ENK-BALI-001", "Endek Bali Rangrang", 50)],
            "notes": "Permintaan transfer songket & endek ke Surabaya (menunggu approval manager).",
            "requested_by": "Eko Prasetyo", "approved_by": None,
            "created_by": "Eko Prasetyo",
            "created_at": ago(days=1), "updated_at": ago(days=1),
        },
    ]
    await db.warehouse_transfers.insert_many(transfers)
    print(f"✅ Warehouse transfers seeded ({len(transfers)} surat jalan transfer · yard)")
    return len(transfers)


async def seed_cycle_counts():
    """Sesi Cycle Count / Stock Opname — contoh (approved + submitted).

    Item pakai field expected_qty/actual_qty (sesuai router). Idempotent.
    """
    if await db.cycle_count_sessions.count_documents({}) > 0:
        print("ℹ️  cycle_count_sessions sudah ada — seed cycle count dilewati")
        return 0

    def _cci(cid, pid, sku, name, expected, actual, bin_id):
        diff = round(float(actual) - float(expected), 2)
        return {"id": cid, "product_id": pid, "sku": sku, "product_name": name,
                "bin_id": bin_id, "owner_entity_id": "ent_ksc",
                "expected_qty": float(expected), "actual_qty": float(actual),
                "status": "counted", "notes": "", "counted_at": ago(days=9),
                "counted_by": "Eko Prasetyo"}

    s1_items = [
        _cci("cci_s1_1", "prod_batik_mega", "BTK-MEGA-001", "Batik Mega Mendung Premium", 485, 480, "A1-01"),
        _cci("cci_s1_2", "prod_tenun_ikat", "TNI-GRGD-001", "Tenun Ikat Garuda Premium", 320, 322, "A2-03"),
        _cci("cci_s1_3", "prod_songket_palembang", "SGK-PLB-001", "Songket Palembang Benang Emas", 155, 150, "B1-02"),
    ]
    s1_disc = [{"item_id": it["id"], "product_name": it["product_name"], "sku": it["sku"],
                "expected_qty": it["expected_qty"], "actual_qty": it["actual_qty"],
                "difference": round(it["actual_qty"] - it["expected_qty"], 2)}
               for it in s1_items if abs(it["actual_qty"] - it["expected_qty"]) > 0.001]

    s2_items = [
        _cci("cci_s2_1", "prod_lurik_classic", "LRK-CLSC-001", "Lurik Klasik Solo", 620, 618, "C1-01"),
        _cci("cci_s2_2", "prod_batik_mega", "BTK-MEGA-001", "Batik Mega Mendung Premium", 340, 340, "C2-01"),
    ]

    sessions = [
        {
            "id": "cc_seed_001", "number": "SO-CC-00001",
            "warehouse_id": "wh_jakarta", "warehouse_name": "Gudang Jakarta Utara", "warehouse_city": "Jakarta",
            "entity_id": "ent_ksc",
            "name": "Opname Jakarta — Batch Q1", "notes": "Stock opname rutin gudang Jakarta.",
            "status": "approved", "items": s1_items, "discrepancies": s1_disc,
            "approval_reason": "Disetujui — selisih dalam toleransi, inventory disesuaikan.",
            "created_by": "Eko Prasetyo", "approved_by": "Dewi Rahayu",
            "created_at": ago(days=10), "updated_at": ago(days=9),
        },
        {
            "id": "cc_seed_002", "number": "SO-CC-00002",
            "warehouse_id": "wh_bandung", "warehouse_name": "Gudang Bandung Kopo", "warehouse_city": "Bandung",
            "entity_id": "ent_ksc",
            "name": "Opname Bandung — Spot Check", "notes": "Spot check gudang Bandung (menunggu review manager).",
            "status": "submitted", "items": s2_items, "discrepancies": [],
            "created_by": "Fitri Handayani",
            "created_at": ago(days=2), "updated_at": ago(days=2),
        },
    ]
    await db.cycle_count_sessions.insert_many(sessions)
    print(f"✅ Cycle count sessions seeded ({len(sessions)} sesi stock opname)")
    return len(sessions)



async def seed_amendments():
    """FASE G-1 — contoh **AMANDEMEN NYATA** untuk data demo.

    Penting: dokumen amandemen di sini TIDAK ditulis manual ke koleksi. Semuanya
    dibuat lewat `services/amendment_service.py` (mesin yang sama dengan UI), jadi
    ambang persetujuan, nomor dokumen, snapshot kebijakan, jejak `refs[]`, timeline
    dan nota koreksi lahir dari jalur produksi — bukan data palsu yang "kelihatan
    benar" tetapi tidak pernah melewati aturan.

    Empat kondisi yang sengaja dibuat supaya seluruh status terlihat di UI dan
    invarian INV-AMD-01..05 punya data nyata (bukan lulus karena 0 baris):

      1. SO-0008 · koreksi kecil (< ambang)      → `auto_applied` (dihitung ulang)
      2. SO-0006 · koreksi 8%                    → `pending_approval` (antre di manager)
      3. SO-0005 · dokumen SUDAH TERBIT (lunas)  → disetujui → terbit **Nota Kredit**
      4. SO-0003 · dokumen SUDAH TERBIT (faktur) → **ditolak** manager (tanpa efek)

    Dipanggil SEBELUM posting jurnal GL agar total order hasil perhitungan ulang
    ikut terbawa ke jurnal (tidak ada drift GL vs dokumen).
    """
    from services import amendment_service as amds

    async def _user(email: str):
        return await db.users.find_one({"email": email}, {"_id": 0})

    admin = await _user("admin@kainnusantara.id")
    sales = await _user("sales@kainnusantara.id")
    sales2 = await _user("sales2@kainnusantara.id")
    manager = await _user("manager@kainnusantara.id")
    if not (admin and sales and manager):
        print("  [warn] seed_amendments dilewati: user demo belum lengkap")
        return 0

    await amds.ensure_reasons()

    def actor(u):
        return {"id": u["id"], "name": u["name"], "role": u["role"]}

    async def _order_id(number: str):
        row = await db.sales_orders.find_one({"number": number}, {"_id": 0, "id": 1})
        return row["id"] if row else None

    created = 0

    # 1) Koreksi kecil pada pesanan yang BELUM terbit → langsung diterapkan,
    #    tetapi tetap sebagai dokumen amandemen bernomor + alasan (bukan edit senyap).
    oid = await _order_id("SO-0008")
    if oid:
        try:
            await amds.propose(
                "sales_order", oid, "price_correction",
                [{"product_id": "prod_batik_mega", "field": "price", "to": 180000}],
                actor(sales),
                note="Harga yang disepakati dengan pelanggan Rp 180.000/yard.")
            created += 1
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] amandemen SO-0008 dilewati: {_e}")

    # 2) Koreksi 8% → melewati ambang persen → ANTRE persetujuan manager
    #    (sengaja dibiarkan pending agar Pusat Persetujuan & lonceng punya isi nyata).
    oid = await _order_id("SO-0006")
    if oid:
        try:
            await amds.propose(
                "sales_order", oid, "customer_negotiation",
                [{"product_id": "prod_songket_palembang", "field": "price", "to": 380000}],
                actor(sales2 or sales),
                note="Pelanggan minta penyesuaian harga songket karena ambil 2 gulung "
                     "sekaligus; disetujui secara komersial oleh sales.")
            created += 1
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] amandemen SO-0006 dilewati: {_e}")

    # 3) Dokumen SUDAH TERBIT (lunas) → angka aslinya tidak boleh berubah.
    #    Diusulkan admin, diputus manager (kontrol ganda) → terbit NOTA KREDIT.
    oid = await _order_id("SO-0005")
    if oid:
        try:
            amd = await amds.propose(
                "sales_order", oid, "price_correction",
                [{"product_id": "prod_tenun_ikat", "field": "price", "to": 200000}],
                actor(admin),
                note="Harga kontrak tenun ikat Rp 200.000/meter; order terlanjur "
                     "memakai harga lama Rp 225.000/meter.")
            created += 1
            if amd.get("status") == "pending_approval":
                await amds.decide(amd["id"], "approve", actor(manager),
                                  note="Kontrak diverifikasi. Terbitkan nota kredit.")
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] amandemen SO-0005 dilewati: {_e}")

    # 4) Usulan yang DITOLAK — bukti bahwa penolakan tidak mengubah apa pun.
    oid = await _order_id("SO-0003")
    if oid:
        try:
            amd = await amds.propose(
                "sales_order", oid, "discount_grant",
                [{"product_id": "prod_endek_bali", "field": "price", "to": 240000}],
                actor(sales),
                note="Permintaan kompensasi keterlambatan kirim dari pelanggan.")
            created += 1
            if amd.get("status") == "pending_approval":
                await amds.decide(amd["id"], "reject", actor(manager),
                                  note="Keterlambatan bukan kesalahan kami — dokumen "
                                       "sudah difakturkan. Ditolak.")
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] amandemen SO-0003 dilewati: {_e}")

    notes = await db.credit_notes.count_documents({"source": "amendment"})
    pend = await db.doc_amendments.count_documents({"status": "pending_approval"})
    print(f"✅ Amandemen (Fase G-1): {created} dokumen amandemen · {notes} nota koreksi · "
          f"{pend} menunggu persetujuan")
    return created


async def seed_approval_notifications():
    """Notifikasi 'menunggu persetujuan' untuk PO yang MEMANG berstatus waiting_approval.

    Bukan data karangan: notifikasi dibentuk dari PO nyata lewat
    `notification_service.notify_po_awaiting_approval()` — jalur yang sama dengan
    saat PO dibuat dari aplikasi. Tanpa ini, aksi inline "Setujui" pada lonceng
    tidak pernah muncul di data demo sehingga fiturnya tak bisa dilihat/diuji.
    """
    from services.notification_service import notify_po_awaiting_approval
    made = 0
    async for po in db.purchase_orders.find({"status": "waiting_approval"}, {"_id": 0}):
        try:
            if await notify_po_awaiting_approval(po):
                made += 1
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] notifikasi PO {po.get('po_number')} dilewati: {_e}")
    print(f"✅ Notifikasi persetujuan PO: {made} permintaan menunggu (aksi inline di lonceng)")
    return made


async def seed_all(db_instance=None):
    """
    Run the complete seed pipeline. Can be called from an external module
    (e.g. FastAPI endpoint) by passing a Motor DB instance.

    Returns a summary dict with counts of inserted records.
    """
    if db_instance is not None:
        init_with_db(db_instance)
    if db is None:
        raise RuntimeError(
            "Seed pipeline requires a DB instance. "
            "Either call init_with_db(db) first or pass db_instance to seed_all()."
        )

    print("\n🚀 Starting Kain Nusantara Realistic Seed...\n")
    await clear_collections()
    await seed_users()
    await seed_uoms()
    await seed_warehouses()
    await seed_color_library()
    await seed_product_lines()          # FASE L — master lini (sebelum produk!)
    await seed_process_stages()         # FASE T — master tahapan proses (termasuk `screen`)
    await seed_products()
    await seed_customers()
    await seed_crm()
    await seed_inventory_initial()
    await seed_inventory_movements_initial()
    await seed_purchase_orders()
    await seed_sales_orders()
    await backfill_order_snapshots()
    await seed_document_templates()
    await seed_permissions()
    await seed_audit_logs()
    await seed_entities_and_backfill()
    # Fase 0.5 — Roll-as-SSOT: backfill owner + generate rolls + rebuild balances
    await db.inventory_balances.update_many(
        {"owner_entity_id": {"$exists": False}}, {"$set": {"owner_entity_id": "ent_ksc"}}
    )
    await db.inventory_movements.update_many(
        {"owner_entity_id": {"$exists": False}}, {"$set": {"owner_entity_id": "ent_ksc"}}
    )
    from services.roll_service import generate_rolls_from_balances
    roll_result = await generate_rolls_from_balances(created_by="seed")
    print(f"✅ Inventory rolls generated ({roll_result.get('rolls', 0)} rolls · {roll_result.get('segments', 0)} segmen)")
    # Fase 1A — Configuration Foundation defaults
    from services.config_service import seed_config_defaults
    cfg = await seed_config_defaults()
    print(f"✅ Config defaults seeded (settings {cfg.get('settings',0)} · payment_terms {cfg.get('payment_terms',0)} · approval_rules {cfg.get('approval_rules',0)})")
    # Sub-fase 1.7 — Special Price / Approval Harga (contoh)
    await seed_price_approvals()
    # F1b — Daftar Harga per Pelanggan (harga langganan + satu usulan menunggu)
    await seed_entity_prices()
    await seed_customer_prices()
    # Sub-fase 1.7 — Pegging/Earmark (contoh soft hold roll → customer)
    await seed_pegging_examples()
    # Fase 1B — backfill pricing (diskon+PPN) agar seed konsisten dgn create_order
    await backfill_order_pricing()
    # Sub-fase 1.8 — normalisasi SO terkirim → status baru + shipments (contoh)
    await seed_shipment_examples()
    # Sub-fase 1.9 — Faktur Pajak Jual (contoh)
    await seed_tax_invoice_examples()
    # Sub-fase 1.11 — Returns & Barang Sisa
    await seed_sales_returns_examples()
    # Sub-fase 1.12 — Special Orders
    await seed_special_order_examples()
    # Fase 3 — Procurement: master supplier (+ link PO) + pengelolaan kas
    await seed_purchase_approval_examples()
    await seed_suppliers()
    await seed_supplier_price_lists()
    try:
        await seed_supplier_sourcing()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_supplier_sourcing dilewati: {_e}")
    await seed_makloon_masters()
    try:
        await seed_makloon_contracts()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_makloon_contracts dilewati: {_e}")
    await seed_cash_transactions()
    await seed_bank_accounts()
    await seed_purchase_returns()
    await seed_po_payments()
    await seed_requisitions()
    # Depth #3a — QC Hold demo (task qc_pending + roll quarantine)
    await seed_qc_quarantine_examples()
    # FASE F-1 — demo penerimaan berbasis SATUAN SUPPLIER (task inbound siap dicoba)
    try:
        await seed_receiving_supplier_uom_demo()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_receiving_supplier_uom_demo dilewati: {_e}")
    # EPIC2 — master kategori + snapshot kategori SO line (AKHIR: setelah semua mutasi items)
    await finalize_epic2_categories()
    # EPIC3 — costing (harga_pokok + roll cost) + contoh AR receipt (parsial)
    await finalize_epic3_costing_and_ar()
    # FASE G-1 — contoh amandemen NYATA (lewat mesin amandemen). WAJIB sebelum posting
    # jurnal GL: order yang dihitung ulang harus sudah final saat jurnal dibentuk.
    try:
        await seed_amendments()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_amendments dilewati: {_e}")
    # P0-1 — backfill breakdown harga PO (subtotal/net/grand via engine _create_po_core,
    #   non-PPN → ekonomi tetap GROSS). WAJIB setelah SEMUA PO dibuat (termasuk PO-00007..11
    #   di seed_purchase_approval_examples) agar gate INV-DB-PO memvalidasi 11 PO (bukan 0).
    await backfill_po_pricing()
    # EPIC7-C — bagan akun baku + auto-posting jurnal dari SSOT (idempotent)
    from services import gl_service
    await gl_service.seed_default_coa()
    gl_result = await gl_service.backfill_journals()
    print(f"   [EPIC7-C] Journal posted: {gl_result}")
    # P1-4 — Anggaran (Budget) per entitas (SETELAH jurnal ter-posting agar realisasi tersedia)
    await seed_budgets()
    # F0-A — enrich entitas + pastikan user ber-entitas (idempotent, tahan timing)
    from services.entity_context_service import ensure_entity_defaults, ensure_user_entities
    en = await ensure_entity_defaults()
    un = await ensure_user_entities()
    print(f"   [F0-A] entity enrich: {en} | user entity ensured: {un}")
    # F0-C — backfill entity_id ke SEMUA koleksi SCOPED (PALING AKHIR: setelah CoA & shipment seed).
    #   wms_tasks←PO/SO · shipments←SO · gl_accounts→primary · catch-all→primary. Idempotent.
    #   Menjaga GATE `verify_entity_scoping.py` (DB CHECK) tetap HIJAU di clean-seed.
    from scripts.migrate_entity_scoping import run_full_migration
    f0c_ok = await run_full_migration()
    print(f"   [F0-C] entity scoping backfill: {'✅ LULUS' if f0c_ok else '❌ ADA SISA'}")
    # F2 (UoM SSOT) — backfill roll_count/on_hand_roll_count ke balances (PALING AKHIR: setelah semua mutasi roll/QC).
    from services.roll_service import backfill_roll_counts
    rc = await backfill_roll_counts()
    print(f"   [F2-UoM] roll_count backfilled ke {rc} balance")
    # F4 (Status SO 2-level) — backfill stage+sub_status ke SEMUA sales_orders (additive, idempotent).
    from services.so_status import backfill_so_status
    so_stat = await backfill_so_status(db)
    print(f"   [F4-Status] stage/sub_status backfilled ke {so_stat['updated']}/{so_stat['total']} SO "
          f"(invalid={so_stat['invalid']})")
    # F5 (Unified Approval) — sinkronkan pending_approvals SSOT (additive, idempotent).
    from services.so_approvals import backfill_pending_approvals
    f5 = await backfill_pending_approvals(db)
    # Re-derive stage/sub setelah pending_approvals dibuat agar sub-status konsisten.
    so_stat2 = await backfill_so_status(db)
    print(f"   [F5-Approval] pending_approvals disinkronkan ke {f5['updated']}/{f5['total']} SO "
          f"(re-derive {so_stat2['updated']})")
    # Fase 5 (RFID Simulator) — devices + encode tag on-hand + read demo (PALING AKHIR: roll final).
    await seed_rfid()
    # Phase 6 (Document Platform) — Surat Jalan Transfer + Stock Opname (yard) untuk demo dokumen.
    await seed_transfers()
    await seed_cycle_counts()
    # FASE B (D-06/D-07) — pastikan registry konversi satuan + kebijakan toleransi ada
    # setelah reset data demo (koleksi system_settings ikut dibersihkan di awal seed).
    try:
        from services import uom_rules_service as _uomr
        from bootstrap import sync_product_uom_examples as _sync_uom_examples
        _uom_seed = await _uomr.ensure_defaults(actor="seed")
        # contoh faktor per produk (1 roll = 50 yard) — dipakai demo & POC Fase B
        await _sync_uom_examples()
        print(f"✅ Konversi satuan (Fase B): {_uom_seed['rules_created']} aturan baru · "
              f"{_uom_seed['rules_existing']} sudah ada · faktor per produk contoh siap")
    except Exception as _exc:  # noqa: BLE001
        print(f"⚠️  Seed aturan konversi dilewati: {_exc}")
    # FASE C (D-10/D-26/D-27) — kebijakan penegakan lot + pastikan seluruh roll hasil
    # seed bertaut lot kelas satu (jalur yang sama dengan migrasi — tanpa logika ganda).
    try:
        from services import lot_migration as _lotm
        _lot_seed = await _lotm.run_all(actor="seed")
        print(f"✅ Lot kelas satu (Fase C): kebijakan lot "
              f"{'dibuat' if _lot_seed['settings_created'] else 'sudah ada'} · "
              f"{_lot_seed['lots_created']} lot dibentuk · {_lot_seed['rolls_linked']} roll ditaut")
    except Exception as _exc:  # noqa: BLE001
        print(f"⚠️  Seed lot Fase C dilewati: {_exc}")
    # FASE F — data demo R&D & Desain (spesifikasi → labdip/proofing → kontrak).
    # SEBELUM true-up GL persediaan karena pengambilan bahan sample mengurangi roll.
    try:
        await seed_rnd()
    except Exception as _exc:  # noqa: BLE001
        print(f"⚠️  Seed R&D (Fase F) dilewati: {_exc}")
    print("\n✅ All realistic seed data inserted successfully!")

    # Notifikasi persetujuan PO (PALING AKHIR: setelah status & harga PO final).
    try:
        await seed_approval_notifications()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_approval_notifications dilewati: {_e}")

    # Compute summary counts
    summary = {
        "users": await db.users.count_documents({}),
        "products": await db.products.count_documents({}),
        "customers": await db.customers.count_documents({}),
        "warehouses": await db.warehouses.count_documents({}),
        "purchase_orders": await db.purchase_orders.count_documents({}),
        "sales_orders": await db.sales_orders.count_documents({}),
        "inbound_tasks": await db.wms_tasks.count_documents({"flow_type": "inbound"}),
        "outbound_tasks": await db.wms_tasks.count_documents({"flow_type": "outbound"}),
        "inventory_balances": await db.inventory_balances.count_documents({}),
        "inventory_movements": await db.inventory_movements.count_documents({}),
        "inventory_rolls": await db.inventory_rolls.count_documents({}),
        "audit_logs": await db.audit_logs.count_documents({}),
        "price_approvals": await db.price_approvals.count_documents({}),
        "sales_returns": await db.sales_returns.count_documents({}),
        "special_orders": await db.special_orders.count_documents({}),
        "purchase_requisitions": await db.purchase_requisitions.count_documents({}),
        "bank_accounts": await db.bank_accounts.count_documents({}),
    }
    # S#074 (INV-GL-DRIFT): true-up saldo awal GL Persediaan agar == nilai subledger rolls.
    # Seed meng-insert rolls langsung (bypass GL); tanpa ini GL 1-1300 << nilai fisik.
    try:
        import sys as _sys
        _sys.path.insert(0, "/app/backend")
        from services import gl_service as _gl
        await _gl.seed_default_coa()
        _op = await _gl.post_inventory_opening_balance(actor_name="seed")
        summary["inventory_opening_je"] = _op.get("count", 0)
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] opening-balance true-up dilewati: {_e}")
    # M3 — seed contoh Order Makloon (PALING AKHIR: setelah GL true-up agar rekonsiliasi 1-1300 utuh)
    try:
        summary["makloon_orders"] = await seed_makloon_orders()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_makloon_orders dilewati: {_e}")
        summary["makloon_orders"] = 0
    # R6.4 — seed Produksi In-House (setelah makloon: butuh stok grey hasil tenun makloon)
    try:
        summary["work_orders"] = await seed_production()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_production dilewati: {_e}")
        summary["work_orders"] = 0
    # FASE G-2 — contoh RENCANA PEMBAYARAN + DENDA nyata (lewat layanan produksi).
    # Dijalankan sebelum backfill relasi supaya rencana & nota denda ikut tertaut.
    try:
        summary["payment_plans"] = await seed_payment_plans()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_payment_plans dilewati: {_e}")
        summary["payment_plans"] = 0
    # FASE G-3 — contoh KEPUTUSAN SELISIH PEMBAYARAN (lebih/kurang bayar) lewat layanan nyata.
    try:
        summary["payment_variances"] = await seed_payment_variances()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_payment_variances dilewati: {_e}")
        summary["payment_variances"] = 0
    # FASE G-7 — kontrabon demo (siklus tukar faktur supplier). DIJALANKAN SEBELUM
    # `seed_bank_statement()` supaya rekening koran demo bisa memuat satu baris dana
    # keluar yang belum dibukukan → bahan latihan "bayar kontrabon dari mutasi bank".
    try:
        summary["contra_bons"] = await seed_contra_bons()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_contra_bons dilewati: {_e}")
        summary["contra_bons"] = 0
    # FASE G-6 — transaksi antar entitas demo (jual-beli antar-PT + jembatan gudang).
    # SESUDAH kontrabon supaya nomor dokumen & jurnal supplier sudah mapan, SEBELUM
    # relasi dokumen di-backfill (tautan dua arah dokumen kembar ikut terbentuk).
    try:
        summary["interco_transactions"] = await seed_interco()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_interco dilewati: {_e}")
        summary["interco_transactions"] = 0
    # FASE E-7 (E7g) — aset tetap demo (prasyarat jalur pindah aset antar-PT).
    try:
        summary["fixed_assets"] = await seed_fixed_assets()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_fixed_assets dilewati: {_e}")
        summary["fixed_assets"] = 0
    # FASE E-7 (E7d) — Permintaan Internal demo: satu di antrean + satu sudah jadi
    # transaksi antar-PT, plus kontrak harga internal arah Kanda → KSC.
    try:
        summary["internal_requests"] = await seed_internal_requests()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_internal_requests dilewati: {_e}")
        summary["internal_requests"] = 0
    # FASE G-8 — mutasi bank demo (dibentuk dari transaksi kas NYATA + 1 dana tak dikenal).
    try:
        summary["bank_statement_lines"] = await seed_bank_statement()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_bank_statement dilewati: {_e}")
        summary["bank_statement_lines"] = 0
    # FASE G-9 — kasus keuangan demo (dari mutasi & pesanan NYATA, lewat layanan produksi).
    try:
        summary["finance_cases"] = await seed_finance_cases()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_finance_cases dilewati: {_e}")
        summary["finance_cases"] = 0
    # FASE P8 — BIAYA MASUK (landed cost) & PERMINTAAN PENAWARAN (RFQ) demo.
    # Dua layar ini punya pop-up rincian sejak P7 tetapi data demonya NOL, sehingga
    # keduanya hanya bisa diverifikasi lewat gate — tak pernah lewat klik nyata.
    try:
        summary["landed_cost_vouchers"] = await seed_landed_costs()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_landed_costs dilewati: {_e}")
        summary["landed_cost_vouchers"] = 0
    try:
        summary["rfqs"] = await seed_rfqs()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_rfqs dilewati: {_e}")
        summary["rfqs"] = 0
    # FASE G-4 — bentuk relasi dokumen (`refs[]` dua arah) dari kolom penghubung nyata.
    # PALING AKHIR: setelah SEMUA dokumen (termasuk makloon, produksi & kasus) terbentuk.
    try:
        from services import doc_refs_service as _refs
        _rb = await _refs.backfill(dry_run=False)
        summary["doc_refs_links"] = _rb.get("written", 0)
        print(f"✅ Relasi dokumen (Fase G-4): {_rb.get('written', 0)} tautan dua arah "
              f"dari {_rb.get('candidates', 0)} kandidat")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] backfill relasi dokumen dilewati: {_e}")
        summary["doc_refs_links"] = 0
    # FASE E-7 (E7.2/E7.7) — pemasok bertipe "Entitas grup" untuk setiap pasangan badan
    # usaha. Harus di SINI (sesudah `seed_entities_and_backfill` dan sesudah pemasok luar
    # dibuat) supaya nomor SUP-NNNNN tidak tabrakan, dan supaya seed ulang tidak
    # menghilangkan jangkar pemasok yang dipakai layar & pagar E7.2.
    try:
        from services import group_partner_service as _grp
        _gp = await _grp.sync_group_entity_suppliers(actor_name="seed")
        summary["group_entity_suppliers"] = _gp.get("created", 0) + _gp.get("updated", 0)
        print(f"✅ Pemasok 'Entitas grup' (Fase E-7): {_gp['created']} dibuat · "
              f"{_gp['updated']} disegarkan · {_gp['archived']} diarsipkan")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] sync pemasok entitas grup dilewati: {_e}")
        summary["group_entity_suppliers"] = 0
    # UTANG MIGRASI (ii) — jejak kegiatan akun WARISAN `manager` yang sebenarnya
    # Admin Sales. Harus PALING AKHIR: ia menunjuk dokumen nyata (SO, retur, antar-PT)
    # yang baru ada setelah semua koleksi di atas terbentuk.
    try:
        summary["legacy_role_footprint"] = await seed_legacy_role_footprint()
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed_legacy_role_footprint dilewati: {_e}")
        summary["legacy_role_footprint"] = 0
    # ── FASE L — stempel lini pada SELURUH dokumen demo. WAJIB paling akhir:
    # dokumen dibuat oleh puluhan fungsi seed yang menulis langsung ke Mongo
    # (bukan lewat API), jadi tidak satu pun melewati `line_scope.stamp_doc`.
    # Dipakai PINTU YANG SAMA dengan migrasi basis data lama supaya kedua basis
    # data punya arti identik — kalau tidak, gate INV-LINE-01 bisa hijau di satu
    # basis data dan merah di yang lain tanpa ada yang tahu mana yang benar.
    try:
        from backend.services import line_scope as _lines   # noqa: PLC0415
    except Exception:  # noqa: BLE001 — dijalankan dari /app dengan sys.path backend
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
        from services import line_scope as _lines           # noqa: PLC0415
    _rows = await _lines.backfill(db)
    summary["line_backfill"] = sum(t for _c, t, _n in _rows)
    print(f"✅ FASE L — lini distempel pada {summary['line_backfill']} dokumen demo "
          "(baris + turunan `line_codes[]`)")
    return summary


async def seed_legacy_role_footprint():
    """UTANG MIGRASI (ii) — jejak kerja akun warisan `manager` = Rudi Hartono.

    KENAPA ADA: layar **Cek Peran** menyimpulkan peran dari JEJAK NYATA. Tanpa jejak
    ia jujur berkata "tanpa jejak — peran tidak dinilai", jadi kalau data demo tidak
    punya satu pun akun bermasalah, fitur ini tak bisa dilihat bekerja oleh pemilik
    dan kelas bugnya tak bisa ditangkap agen uji.

    Jejaknya dipilih supaya **konsisten dengan dokumennya**: hanya tindakan yang
    TIDAK punya field pelaku di dokumen (verifikasi pesanan, langkah pemeriksaan
    retur, penagihan antar-PT), sehingga tidak ada dua orang yang mengaku
    melakukan hal yang sama pada satu dokumen.

    Izin yang dibutuhkan gabungan jejak ini: `order.verify` + `sales_return.update`
    + `interco.invoice` → peran TERENDAH yang memenuhinya = **Admin Sales**.
    Karena akunnya `manager` (peringkat 3 > 2), kesimpulannya `kuasa_berlebih`.
    """
    RUDI = {"user_id": "user_manager_02", "user_name": "Rudi Hartono"}
    orders = await db.sales_orders.find(
        {"entity_id": "ent_ksc"}, {"_id": 0, "id": 1, "number": 1}
    ).sort("number", 1).to_list(3)
    retur = await db.sales_returns.find_one({}, {"_id": 0, "id": 1, "number": 1})
    ic = await db.interco_transactions.find_one(
        {"entity_id": "ent_ksc"}, {"_id": 0, "id": 1, "number": 1})

    logs = []
    for i, o in enumerate(orders):
        logs.append({
            "id": new_id("audit"), **RUDI,
            "action": "order_verified", "resource": "sales_order", "resource_id": o["id"],
            "details": {"number": o["number"],
                        "checked": "alamat kirim · syarat bayar · NPWP"},
            "timestamp": ago(days=40 - i * 3), "scope_entity_id": "ent_ksc"})
    if retur:
        for act in ("sales_return_inspect_started", "sales_return_inspected"):
            logs.append({
                "id": new_id("audit"), **RUDI,
                "action": act, "resource": "sales_return", "resource_id": retur["id"],
                "details": {"number": retur["number"]},
                "timestamp": ago(days=20), "scope_entity_id": "ent_ksc"})
    if ic:
        logs.append({
            "id": new_id("audit"), **RUDI,
            "action": "interco_transaction_invoiced", "resource": "interco_transaction",
            "resource_id": ic["id"], "details": {"number": ic["number"]},
            "timestamp": ago(days=12), "scope_entity_id": "ent_ksc"})

    if logs:
        await db.audit_logs.insert_many(logs)
    print(f"✅ Jejak akun warisan (utang migrasi ii): {len(logs)} baris untuk "
          f"Rudi Hartono — `manager` yang pekerjaannya Admin Sales")
    return len(logs)


async def seed_fixed_assets():
    """FASE E-7 (E7g) — contoh **ASET TETAP** supaya jalur pindah aset antar-PT bisa
    dibuktikan (sebelum ini `fin_fixed_assets` NOL baris, jadi fitur pindah aset tidak
    pernah bisa dicoba siapa pun). Dibuat lewat layanan produksi agar jurnal perolehan
    & jadwal penyusutannya lahir dari aturan yang sama dengan aset yang dibuat pengguna.
    """
    if await db.fin_fixed_assets.count_documents({}) > 0:
        print("ℹ️  aset tetap demo sudah ada — dilewati")
        return 0
    sys.path.insert(0, "/app/backend")
    from services import fixed_asset_service as fas  # noqa: PLC0415

    actor = {"id": "user_admin_01", "name": "Budi Santoso", "role": "admin"}
    contoh = [
        {"name": "Mesin Potong Kain Otomatis", "category": "Peralatan & Mesin",
         "acquisition_cost": 185000000, "useful_life_months": 96, "salvage_value": 15000000,
         "entity_id": "ent_ksc", "days": 400,
         "notes": "Mesin potong utama gudang Jakarta."},
        {"name": "Kendaraan Box Pengiriman (L300)", "category": "Kendaraan",
         "acquisition_cost": 235000000, "useful_life_months": 120, "salvage_value": 35000000,
         "entity_id": "ent_ksc", "days": 300,
         "notes": "Pengiriman rutin Jakarta–Bandung."},
        {"name": "Genset 20 kVA", "category": "Peralatan & Mesin",
         "acquisition_cost": 78000000, "useful_life_months": 84, "salvage_value": 6000000,
         "entity_id": "ent_kanda", "days": 220,
         "notes": "Cadangan daya workshop Kanda."},
    ]
    made = 0
    for c in contoh:
        days = c.pop("days")
        try:
            await fas.create_asset({**c, "acquisition_date": ago(days=days)[:10]}, actor)
            made += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] aset '{c['name']}' dilewati: {exc}")
    # Jalankan penyusutan beberapa periode supaya NILAI BUKU-nya sudah bergerak —
    # pindah aset antar-PT baru bermakna kalau ada akumulasi penyusutan yang ikut dihapus.
    periods = sorted({ago(days=d)[:7] for d in (270, 240, 210, 180, 150, 120, 90, 60, 30)})
    for p in periods:
        try:
            await fas.run_depreciation(p, actor)
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] penyusutan periode {p} dilewati: {exc}")
    print(f"✅ Aset tetap seeded ({made} aset · penyusutan {len(periods)} periode) — "
          f"jalur pindah aset antar-PT (E7g) siap dicoba")
    return made


async def seed_internal_requests():
    """FASE E-7 (E7d) — **PERMINTAAN INTERNAL** demo (sales minta barang dari PT lain).

    Dibuat lewat ENDPOINT PRODUKSI supaya benar-benar melewati aturannya: nomor
    `<ENT>/PIN-#####`, pagar “sales tidak memilih PT sumber”, cuplikan bukti
    ketersediaan, dan konversi ke transaksi antar-PT (dokumen kembar G-6).

    Dua keadaan supaya layar tidak kosong:
      (1) satu permintaan **masih di antrean** (menunggu admin/manajer menindak), dan
      (2) satu permintaan **sudah jadi transaksi antar-PT** (jejak dua arah terbentuk).

    Ditambah **kontrak harga internal arah Kanda → KSC**: tanpa itu, konversi ditolak
    mesin antar-PT (dan layar hanya memperlihatkan kalimat “buat kontrak dulu”).
    """
    import httpx

    if await db.internal_requests.count_documents({}) > 0:
        print("ℹ️  permintaan internal demo sudah ada — dilewati")
        return 0

    sys.path.insert(0, "/app/backend")
    from server import app  # noqa: PLC0415

    REQUESTER, SOURCE = "ent_ksc", "ent_kanda"

    # Barang yang stoknya ADA di badan usaha sumber (kalau tidak, permintaannya
    # memang harus ditolak sistem — dan seed tidak boleh memaksa data bohong).
    async def avail_at(pid: str, ent: str) -> float:
        rows = await db.inventory_balances.find(
            {"product_id": pid, "owner_entity_id": ent},
            {"_id": 0, "available_qty": 1}).to_list(500)
        return round(sum(float(r.get("available_qty") or 0) for r in rows), 2)

    pid = ""
    qty = 0.0
    for p in await db.products.find({"status": "active"}, {"_id": 0, "id": 1}).to_list(200):
        have = await avail_at(p["id"], SOURCE)
        if have >= 2:
            pid, qty = p["id"], min(round(have / 2, 2), 5.0)
            break
    if not pid:
        print("  [warn] tidak ada barang berstok di badan usaha sumber — "
              "seed permintaan internal dilewati")
        return 0

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://asgi",
                                 timeout=120.0) as cs, \
            httpx.AsyncClient(transport=transport, base_url="http://asgi",
                              timeout=120.0) as ca:

        async def login(cl, email):
            r = await cl.post("/api/auth/login", json={"email": email,
                                                       "password": "demo12345"})
            r.raise_for_status()
            return r.json()["token"]

        sales = await login(cs, "sales@kainnusantara.id")     # sales PT Kain Suka Cita
        adm = await login(ca, "admin@kainnusantara.id")

        def H(tok, ent):
            return {"Authorization": f"Bearer {tok}", "X-Entity-Id": ent}

        # (0) Kontrak harga internal ARAH SEBALIKNYA (Kanda menjual ke KSC).
        exists = await db.supplier_contracts.find_one(
            {"entity_id": SOURCE, "partner_kind": "entity", "partner_id": REQUESTER,
             "product_id": pid, "status": "active"}, {"_id": 0, "id": 1})
        if not exists:
            from services.costing_service import wac_for_product  # noqa: PLC0415
            w = await wac_for_product(pid, entity_id=SOURCE, use_cache=False)
            rate = round(max(float(w.get("wac") or 0), 1000) * 1.3, -2) or 1300.0
            r = await ca.post("/api/supplier-contracts", headers=H(adm, SOURCE), json={
                "contract_type": "internal", "partner_id": REQUESTER,
                "partner_name": "PT Kain Suka Cita",
                "title": "Harga Internal Kanda → KSC (data demo E-7)",
                "product_id": pid, "tariff_basis": "lumpsum", "tariff_rate": rate,
                "tariff_qty_source": "output", "status": "active",
                "valid_from": ago(days=20)[:10],
                "notes": "Harga jual internal arah Kanda → KSC (dipakai Permintaan Internal)"})
            if r.status_code not in (200, 201):
                print(f"  [warn] kontrak internal Kanda→KSC gagal: {r.status_code} {r.text[:150]}")

        async def ajukan(q: float, alasan: str):
            r = await cs.post("/api/internal-requests", headers=H(sales, REQUESTER), json={
                "items": [{"product_id": pid, "quantity": q}],
                "reason": alasan, "needed_date": ago(days=-7)[:10]})
            if r.status_code != 200:
                raise RuntimeError(f"permintaan internal gagal: {r.status_code} {r.text[:200]}")
            return r.json()

        made = 0
        # (1) Antrean — menunggu admin/manajer menindak.
        await ajukan(min(qty, 3.0), "Stok kami habis, pesanan pelanggan menunggu kiriman")
        made += 1
        # (2) Sudah jadi transaksi antar-PT (draf) — supaya jejaknya terlihat.
        pin2 = await ajukan(min(qty, 2.0), "Kekurangan untuk pesanan retail bulan ini")
        r = await ca.post(f"/api/internal-requests/{pin2['id']}/convert",
                          headers=H(adm, REQUESTER),
                          json={"source_entity_id": SOURCE, "submit_now": False})
        if r.status_code == 200:
            made += 1
            print(f"✅ Permintaan internal (E-7): {pin2['number']} → "
                  f"{r.json()['request']['interco_number_buyer']} ⇄ "
                  f"{r.json()['request']['interco_number_seller']}")
        else:
            print(f"  [warn] konversi permintaan internal demo gagal: "
                  f"{r.status_code} {r.text[:160]}")
    print(f"✅ Permintaan Internal seeded ({made} dokumen: antrean + hasil konversi)")
    return made


async def seed_interco():
    """FASE G-6 — **TRANSAKSI ANTAR ENTITAS** demo (jual-beli antar-PT dalam grup).

    KENAPA LEWAT ENDPOINT PRODUKSI (ASGI in-process, tanpa jaringan): harga internal
    lahir dari kontrak (`supplier_contracts` ber-`partner_kind="entity"`), dokumen
    kembar + jurnal dua buku lahir di `services/interco_service.py`, perpindahan
    fisiknya lewat `warehouse_transfers` (jalur gudang yang sudah ada), dan eliminasi
    unrealized profit lahir di `services/consolidation_service.py`. Menyusun dokumen
    itu dengan tangan di seed = data yang "kelihatan benar" tetapi tidak pernah lewat
    aturannya (dan pasti melenceng saat aturannya berubah). Karena itu seed memanggil
    APLIKASI YANG SAMA.

    Empat keadaan supaya SELURUH layar Antar Entitas ada isinya:
      (1) **Sudah diterima** — barangnya benar-benar berpindah lewat tugas gudang
          (roll berganti pemilik + dinilai ulang ke harga beli internal, tanpa jurnal
          at-cost dobel). Ini contoh jembatan US8 yang bisa ditelusuri pengguna.
      (2) **Dikonfirmasi (belum lunas)** — mengisi saldo Antar-PT & kartu piutang.
      (3) **Lunas lewat settlement/netting** — satu dokumen ICS menutup transaksi.
      (4) **Draf** — menyisakan satu dokumen yang menunggu tombol "Konfirmasi".
    """
    import httpx

    if await db.interco_transactions.count_documents({}) > 0:
        print("ℹ️  transaksi antar-PT demo sudah ada — dilewati")
        return 0

    sys.path.insert(0, "/app/backend")
    from server import app  # noqa: PLC0415

    made = {"contracts": 0, "tx": 0, "tasks": 0, "settlements": 0}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://asgi",
                                 timeout=120.0) as ca, \
            httpx.AsyncClient(transport=transport, base_url="http://asgi",
                              timeout=120.0) as cm:

        async def login(cl, email):
            r = await cl.post("/api/auth/login", json={"email": email,
                                                       "password": "demo12345"})
            r.raise_for_status()
            return r.json()["token"]

        adm = await login(ca, "admin@kainnusantara.id")
        mgr = await login(cm, "manager@kainnusantara.id")

        def H(tok, ent="ent_ksc"):
            return {"Authorization": f"Bearer {tok}", "X-Entity-Id": ent}

        SELLER, BUYER = "ent_ksc", "ent_kanda"

        async def avail(product_id: str, entity_id: str) -> float:
            rows = await db.inventory_rolls.find(
                {"product_id": product_id, "owner_entity_id": entity_id,
                 "status": "available"}, {"_id": 0, "length_remaining": 1}).to_list(10000)
            return round(sum(float(r.get("length_remaining") or 0) for r in rows), 2)

        async def wac(product_id: str, entity_id: str) -> float:
            from services.costing_service import wac_for_product  # noqa: PLC0415
            w = await wac_for_product(product_id, entity_id=entity_id, use_cache=False)
            return round(float(w.get("wac") or 0), 2)

        # ── (1) Kontrak internal = SUMBER harga antar-PT (keputusan pemilik #1) ──
        async def contract(product_id: str, rate: float, title: str):
            r = await ca.post("/api/supplier-contracts", headers=H(adm, SELLER), json={
                "contract_type": "internal", "partner_id": BUYER,
                "partner_name": "CV Kanda Suka", "title": title,
                "product_id": product_id, "tariff_basis": "lumpsum",
                "tariff_rate": rate, "tariff_qty_source": "output",
                "status": "active", "valid_from": ago(days=30)[:10],
                "notes": "Harga jual internal antar-PT (data demo G-6)"})
            if r.status_code not in (200, 201):
                raise RuntimeError(f"kontrak internal gagal: {r.status_code} {r.text[:200]}")
            made["contracts"] += 1
            return r.json()

        async def tx(product_id: str, qty: float, submit: bool, note: str):
            r = await ca.post("/api/interco/transactions", headers=H(adm, SELLER), json={
                "seller_entity_id": SELLER, "buyer_entity_id": BUYER,
                "pricing_mode": "fixed_price",
                "items": [{"product_id": product_id, "quantity": qty}],
                "submit_now": submit, "notes": note})
            if r.status_code != 200:
                raise RuntimeError(f"transaksi antar-PT gagal: {r.status_code} {r.text[:200]}")
            made["tx"] += 1
            return r.json()

        # Barang yang dipakai: pilih yang stoknya cukup di PT penjual supaya
        # perpindahan fisiknya NYATA (bukan angka di atas kertas).
        kandidat = [("prod_batik_mega", 10.0), ("prod_tenun_ikat", 8.0),
                    ("prod_lurik_classic", 6.0)]
        dipakai = []
        for pid, need in kandidat:
            if await avail(pid, SELLER) >= need:
                dipakai.append((pid, need))
        if not dipakai:
            print("  [warn] stok PT penjual tidak cukup — seed antar-PT dilewati")
            return 0

        # Harga internal = HPP + ~35% margin (angka bisa diaudit: harga − HPP).
        harga = {}
        for pid, _need in dipakai:
            hpp = await wac(pid, SELLER)
            harga[pid] = round(max(hpp, 1000) * 1.35, -2) or 1000.0
            await contract(pid, harga[pid],
                           f"Harga Internal {pid.replace('prod_', '').replace('_', ' ').title()}")

        # ── (2) Transaksi #1: barangnya BENAR-BENAR berpindah (jembatan US8) ────
        p0, q0 = dipakai[0]
        t1 = await tx(p0, q0, True, "Penjualan internal ke CV Kanda (barang dikirim)")
        r = await ca.post(f"/api/interco/transactions/{t1['seller']['id']}/warehouse-task",
                          headers=H(adm, SELLER), json={"note": "Kirim lewat gudang Jakarta"})
        if r.status_code != 200:
            raise RuntimeError(f"tugas gudang gagal: {r.status_code} {r.text[:200]}")
        trf = r.json()
        made["tasks"] += 1
        # Pemisahan tugas: yang menyetujui perpindahan = MANAJER (bukan pembuatnya).
        ra = await cm.post(f"/api/transfers/{trf['id']}/approve", headers=H(mgr, SELLER),
                           json={"approved_by": "Siti Nurhaliza"})
        if ra.status_code != 200:
            raise RuntimeError(f"approve tugas gudang gagal: {ra.status_code} {ra.text[:200]}")
        je = ra.json().get("je_intercompany") or {}
        if je.get("posted"):
            raise RuntimeError("jurnal at-cost M-3 seharusnya DILEWATI untuk transaksi G-6")

        # ── (3) Transaksi #2: dikonfirmasi & akan DILUNASI lewat settlement ─────
        p1, q1 = dipakai[1] if len(dipakai) > 1 else dipakai[0]
        t2 = await tx(p1, q1, True, "Penjualan internal ke CV Kanda (menunggu pelunasan)")

        # ── (4) Transaksi #3: masih DRAF (menunggu konfirmasi) ─────────────────
        p2, q2 = dipakai[2] if len(dipakai) > 2 else dipakai[0]
        await tx(p2, max(q2 / 2, 1), False, "Draf penjualan internal — menunggu konfirmasi")

        # ── (4b) Transaksi #4: DIKONFIRMASI, barang BELUM dikirim ──────────────
        # Keadaan ini yang membuat tombol "Buat Tugas Gudang" & "Batalkan (ber-alasan)"
        # bisa dicoba pengguna: dokumen + utang sudah lahir (Dr 1-1310 Persediaan Dalam
        # Perjalanan di pembeli), tetapi barangnya masih di gudang penjual.
        await tx(dipakai[0][0], 3, True,
                 "Penjualan internal ke CV Kanda — menunggu pengiriman barang")

        # ── (5) Settlement/netting: satu dokumen menutup transaksi #2 ───────────
        rs = await cm.post("/api/interco/settlements", headers=H(mgr, BUYER), json={
            "payer_entity_id": BUYER, "payee_entity_id": SELLER,
            "transactions": [{"interco_id": t2["seller"]["id"]}],
            "method": "netting",
            "notes": "Netting berkala saldo antar-PT (data demo G-6)"})
        if rs.status_code != 200:
            raise RuntimeError(f"settlement gagal: {rs.status_code} {rs.text[:200]}")
        made["settlements"] += 1

        # ── (6) Pastikan eliminasi konsolidasi lengkap (idempotent) ────────────
        rc = await ca.post("/api/consolidation/sync-g6", headers=H(adm, SELLER))
        if rc.status_code != 200:
            raise RuntimeError(f"sync eliminasi G-6 gagal: {rc.status_code} {rc.text[:200]}")

        # ══ FASE G-6b ═══════════════════════════════════════════════════════
        # (7) Faktur internal + FAKTUR PAJAK INTERNAL untuk transaksi #1.
        #     Rekap PPN tiap PT (Pusat Pajak) baru jujur kalau PPN antar-PT punya
        #     dokumennya sendiri: keluaran di buku penjual, masukan di buku pembeli.
        t1_id = t1["seller"]["id"]
        ri = await ca.post(f"/api/interco/transactions/{t1_id}/invoice",
                           headers=H(adm, SELLER), json={"note": ""})
        if ri.status_code != 200:
            raise RuntimeError(f"faktur internal gagal: {ri.status_code} {ri.text[:200]}")
        rt = await ca.post(f"/api/interco/transactions/{t1_id}/tax-invoice",
                           headers=H(adm, SELLER),
                           json={"nsfp": "", "kode_transaksi": "01"})
        if rt.status_code != 200:
            raise RuntimeError(f"faktur pajak internal gagal: {rt.status_code} {rt.text[:200]}")
        made["tax_invoices"] = 1
        fkt_no = (rt.json().get("out") or {}).get("number", "")
        fpm_no = (rt.json().get("in") or {}).get("number", "")

        # (8) RETUR ANTAR-PT sebagian — barangnya benar-benar kembali lewat gudang.
        #     Dibuat admin, disetujui MANAJER (pembuat ≠ penyetuju), lalu tugas gudang
        #     arah balik disetujui sehingga roll dinilai ulang KEMBALI ke harga
        #     perolehan asli penjual. Sisa faktur pajaknya ditandai *perlu pengganti*
        #     supaya tombol "Faktur Pengganti" bisa dicoba pengguna.
        ret_qty = max(round(q0 * 0.3, 2), 1)
        rr = await ca.post("/api/interco/returns", headers=H(adm, BUYER), json={
            "interco_id": t1_id,
            "items": [{"product_id": p0, "quantity": ret_qty}],
            "reason": "Warna kain tidak sesuai contoh yang disetujui",
            "notes": "Data demo G-6b — retur sebagian sesudah barang berpindah"})
        if rr.status_code != 200:
            raise RuntimeError(f"retur antar-PT gagal: {rr.status_code} {rr.text[:200]}")
        ret = rr.json()["returner"]
        made["returns"] = 1
        rap = await cm.post(f"/api/interco/returns/{ret['id']}/approve",
                            headers=H(mgr, BUYER), json={"note": ""})
        if rap.status_code != 200:
            raise RuntimeError(f"approve retur gagal: {rap.status_code} {rap.text[:200]}")
        rwt = await ca.post(f"/api/interco/returns/{ret['id']}/warehouse-task",
                            headers=H(adm, BUYER), json={"note": "Kirim balik ke KSC"})
        if rwt.status_code != 200:
            raise RuntimeError(f"tugas gudang retur gagal: {rwt.status_code} {rwt.text[:200]}")
        rtrf = rwt.json()
        rap2 = await cm.post(f"/api/transfers/{rtrf['id']}/approve", headers=H(mgr, BUYER),
                             json={"approved_by": "Siti Nurhaliza"})
        if rap2.status_code != 200:
            raise RuntimeError(f"approve tugas retur gagal: {rap2.status_code} {rap2.text[:200]}")

        elim = await db.intercompany_eliminations.count_documents(
            {"source_g6_pair_id": {"$exists": True, "$ne": None}})

    print(f"✅ Transaksi antar-PT (Fase G-6): {made['tx']} transaksi "
          f"({made['contracts']} kontrak harga internal · 1 diterima lewat tugas gudang "
          f"{trf['code']} tanpa jurnal dobel · 1 lunas lewat netting · 1 dikonfirmasi "
          f"menunggu kirim · 1 draf) · {elim} eliminasi unrealized profit di konsolidasi")
    print(f"✅ Lanjutan G-6b: faktur pajak internal {fkt_no} ↔ {fpm_no} · retur "
          f"{ret['number']} {ret_qty} unit (barang sudah kembali lewat {rtrf['code']}, "
          f"faktur pajak ditandai perlu pengganti)")
    return made["tx"]


async def seed_finance_cases():
    """FASE G-9 — **KASUS KEUANGAN** demo (Pusat Kasus Keuangan).

    Dibuat lewat `services/finance_case_service.py` + playbook-nya (mesin yang sama dengan
    UI) supaya nomor kasus, label alasan, jurnal, dan dokumen turunannya lahir dari jalur
    produksi — bukan data karangan.

    Tiga kondisi supaya SELURUH keadaan terlihat di layar demo:
      (1) **Terbuka & terlambat** — dana masuk tak dikenal pada rekening koran demo
          benar-benar dititipkan (`Dr Bank / Cr 2-1950`) lalu jadi kasus. Ini sekaligus
          menunjukkan rantai FASE G-8 → G-9 dan mengisi tab *Dana Titipan* yang tadinya
          kosong.
      (2) **Selesai** — selisih receh karena biaya bank dibebankan ke 6-8000 (di bawah
          ambang `case.auto_bank_charge_max` sehingga selesai tanpa persetujuan, tetapi
          TETAP berlabel & berjurnal).
      (3) **Sedang ditangani (2 langkah)** — uang yang sempat masuk rekening pribadi
          karyawan: langkah 1 sudah diakui (`Dr 1-1280 / Cr 1-1200`), langkah 2 (setoran)
          sengaja DIBIARKAN supaya alur dua langkah terlihat di layar.
    """
    from services import bank_recon_service as _bank
    from services import finance_case_service as _fcs

    actor = {"id": "user_admin_01", "name": "Budi Santoso", "role": "admin"}
    ent = "ent_ksc"
    made = 0

    def _outstanding(o):
        gt = round(float(o.get("grand_total") or 0), 2)
        paid = round(sum(float(p.get("amount") or 0) for p in (o.get("payments") or [])), 2)
        return round(gt - paid, 2)

    async def _pick_order(min_out, skip=()):
        for o in await db.sales_orders.find(
                {"entity_id": ent, "payment_status": {"$in": ["pending", "partial"]}},
                {"_id": 0}).sort("number", 1).to_list(200):
            if o["id"] not in skip and _outstanding(o) >= min_out:
                return o
        return None

    # ── (1) dana masuk tak dikenal → titipan → kasus terbuka (dan terlambat)
    unknown = await db.bank_statement_lines.find_one(
        {"entity_id": ent, "status": "unmatched", "direction": "in",
         "description": {"$regex": "NONREF", "$options": "i"}},
        {"_id": 0}, sort=[("amount", -1)])
    if unknown:
        try:
            hl = await _bank.to_holding(
                unknown["id"], "Nama pengirim tidak terbaca di rekening koran",
                actor["name"], None, ent)
            case = await _fcs.create_case({
                "case_type": "dana_tak_dikenal",
                "title": f"Dana masuk tak dikenal Rp {float(unknown['amount']):,.0f}"
                         .replace(",", "."),
                "description": (f"Mutasi \"{unknown.get('description', '')}\" masuk tanpa "
                                "identitas pengirim. Perlu ditelusuri pemiliknya atau "
                                "dikembalikan."),
                "amount": round(float(hl.get("holding_remaining") or unknown["amount"]), 2),
                "entity_id": ent,
                "source": {"kind": "bank_holding", "id": unknown["id"],
                           "label": f"Mutasi {unknown.get('stmt_date', '')} · "
                                    f"{unknown.get('description', '')[:50]}"},
                "assignee": "Dewi Finance",
            }, actor, None, ent, auto="titipan menganggur")
            # Ditua-kan 2 hari supaya kartu "terlambat" & urutan antrean terlihat di demo.
            await db.finance_cases.update_one({"id": case["id"]}, {"$set": {
                "created_at": ago(days=2), "sla_due_at": ago(days=1),
                "status": "in_progress"}})
            made += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] kasus titipan demo dilewati: {e}")

    # ── (2) selisih biaya bank → SELESAI (berlabel + berjurnal, tanpa persetujuan)
    o_fee = await _pick_order(200000)
    if o_fee:
        try:
            case = await _fcs.create_case({
                "case_type": "selisih_biaya_bank", "amount": 6500.0, "entity_id": ent,
                "title": "Nominal kurang Rp 6.500 karena biaya transfer bank",
                "description": (f"Pelanggan mentransfer penuh untuk {o_fee.get('number')}, "
                                "tetapi bank memotong biaya kirim sehingga yang sampai "
                                "lebih kecil."),
                "customer_id": o_fee.get("customer_id", ""), "order_ids": [o_fee["id"]],
            }, actor, None, ent)
            await _fcs.resolve(case["id"], {
                "action": "bebankan_biaya_bank", "reason_code": "bank_charge",
                "amount": 6500.0, "order_id": o_fee["id"],
                "note": "Selisih di bawah ambang — dibebankan ke Beban Administrasi Bank.",
            }, actor, None)
            made += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] kasus biaya bank demo dilewati: {e}")

    # ── (3) rekening pribadi karyawan → SEDANG DITANGANI (langkah 1 dari 2)
    o_emp = await _pick_order(1000000, skip=(o_fee or {}).get("id", ""))
    if o_emp:
        try:
            case = await _fcs.create_case({
                "case_type": "rekening_pribadi_karyawan", "amount": 750000.0,
                "entity_id": ent,
                "title": "Pelanggan transfer ke rekening pribadi karyawan",
                "description": (f"Pembayaran {o_emp.get('number')} dikirim ke rekening "
                                "pribadi karyawan lapangan. Uang wajib diakui sebagai "
                                "piutang karyawan lalu disetorkan ke rekening perusahaan."),
                "customer_id": o_emp.get("customer_id", ""), "order_ids": [o_emp["id"]],
                "assignee": "Dewi Finance",
                "attachments": [{"name": "surat_pernyataan_karyawan.pdf",
                                 "path": "demo/surat_pernyataan_karyawan.pdf",
                                 "content_type": "application/pdf"}],
            }, actor, None, ent)
            await _fcs.resolve(case["id"], {
                "action": "akui_dipegang_karyawan", "reason_code": "case_employee_account",
                "amount": 750000.0, "order_id": o_emp["id"],
                "employee_name": "Sinta Wulandari",
                "note": "Karyawan mengakui menerima transfer & berjanji menyetor besok.",
            }, actor, None)
            made += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] kasus karyawan demo dilewati: {e}")

    print(f"✅ Kasus keuangan (Fase G-9): {made} kasus demo "
          "(1 terbuka/terlambat dari titipan dana · 1 selesai berjurnal · "
          "1 dua-langkah sedang ditangani)")
    return made


async def seed_contra_bons():
    """FASE G-7 — **KONTRABON** demo (siklus tukar faktur supplier).

    KENAPA LEWAT ENDPOINT PRODUKSI (ASGI in-process, tanpa jaringan):
    tagihan supplier lahir di `routers/vendor_bills.py` (3-way match, harga & PPN dari
    Pusat Pengaturan, jurnal AP), dan kontrabon lahir di `services/contra_bon_service.py`
    (nomor `<ENT>/CB-#####`, penjaga INV-CB-01..04, jurnal potongan). Menyusun ulang
    dokumen itu dengan tangan di seed = data demo yang "kelihatan benar" tetapi tidak
    pernah melewati aturannya, dan pasti melenceng begitu aturannya berubah. Karena itu
    seed memanggil **aplikasi yang sama** lewat `httpx.ASGITransport` — jalur produksi
    penuh, tetap satu proses, tetap deterministik, dan tidak butuh server hidup.

    Tiga kondisi supaya SELURUH keadaan layar terlihat pada data demo:
      (1) **Sudah dibayar** — 2 faktur satu supplier digabung, dipotong denda
          keterlambatan, lalu dilunasi SEKALI (satu transaksi kas untuk dua faktur).
      (2) **Dijadwalkan bayar** — sudah disetujui & dijadwalkan 3 hari ke depan, jadi
          kartu "Jatuh tempo ≤ 7 hari" berisi dan baris mutasi bank demo punya lawannya.
      (3) **Diajukan dengan selisih 3-way BELUM diputus** — harga faktur 4% di atas PO:
          lolos toleransi jalur AP (5%) tetapi melewati toleransi kontrabon (1%),
          sehingga tombol "Verifikasi" akan MENOLAK sampai selisihnya diputus berlabel.
          Inilah pelajaran INV-CB-03 yang bisa dicoba pengguna sendiri.

    Jadwal tukar faktur 3 supplier juga diisi supaya tab "Jadwal Tukar Faktur" dan
    pengingat H-1 punya bahan nyata.
    """
    import httpx

    if await db.contra_bons.count_documents({}) > 0:
        print("ℹ️  kontrabon demo sudah ada — dilewati")
        return 0

    sys.path.insert(0, "/app/backend")
    from server import app  # noqa: PLC0415

    made = {"cb": 0, "bills": 0, "schedules": 0}
    transport = httpx.ASGITransport(app=app)
    # DUA klien terpisah, satu per peran. WAJIB: login menaruh session cookie (SEC-2)
    # dan `require_permission` memakainya lebih dulu daripada header Authorization —
    # jadi satu klien untuk dua peran membuat SEMUA permintaan dikenali sebagai orang
    # yang sama, dan pemisahan tugas ("pembuat ≠ penyetuju") langsung menolak.
    async with httpx.AsyncClient(transport=transport, base_url="http://asgi",
                                 timeout=120.0) as ca, \
            httpx.AsyncClient(transport=transport, base_url="http://asgi",
                              timeout=120.0) as cm:

        async def login(cl, email):
            r = await cl.post("/api/auth/login", json={"email": email, "password": "demo12345"})
            r.raise_for_status()
            return r.json()["token"]

        adm = await login(ca, "admin@kainnusantara.id")
        mgr = await login(cm, "manager@kainnusantara.id")

        def H(tok, ent="ent_ksc"):
            return {"Authorization": f"Bearer {tok}", "X-Entity-Id": ent}

        async def supplier_by_name(name):
            return await db.suppliers.find_one({"name": name}, {"_id": 0})

        # ── (0) Jadwal tukar faktur per supplier (US1) ────────────────────────
        for name, sch in (
            ("Solo Weave", {"mode": "weekly", "weekday": 1, "pic_name": "Pak Joko",
                            "notes": "Datang pagi, bawa nota debit sekalian."}),
            ("Cirebon Craft", {"mode": "monthly", "day_of_month": 25,
                               "pic_name": "Bu Sri", "notes": "Tukar faktur akhir bulan."}),
            ("NTT Weaving Co", {"mode": "biweekly", "weekday": 3,
                                "pic_name": "Pak Yosef", "notes": "Dua pekan sekali, Kamis."}),
        ):
            sup = await supplier_by_name(name)
            if not sup:
                continue
            r = await ca.put(f"/api/suppliers/{sup['id']}/invoice-exchange", json=sch,
                             headers=H(adm, sup.get("entity_id") or "ent_ksc"))
            made["schedules"] += 1 if r.status_code == 200 else 0

        # ── helper: faktur supplier NYATA lewat endpoint produksi ─────────────
        async def bill(po_id, items, inv_no, ent="ent_ksc", days_ago=5):
            r = await ca.post("/api/vendor-bills", headers=H(adm, ent), json={
                "po_id": po_id, "supplier_invoice_no": inv_no, "match_mode": "received",
                "items": items, "bill_date": ago(days=days_ago), "due_date": ago(days=-25),
                "entity_id": ent, "submit_now": True,
                "notes": "Faktur supplier siklus tukar faktur (data demo)"})
            if r.status_code != 200:
                raise RuntimeError(f"faktur {inv_no} gagal: {r.status_code} {r.text[:160]}")
            b = r.json()
            if b.get("status") != "posted":
                raise RuntimeError(f"faktur {inv_no} tidak posted (status {b.get('status')})")
            made["bills"] += 1
            return b

        async def po_price(po_id, product_id):
            po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0, "items": 1})
            for it in (po or {}).get("items", []):
                if it.get("product_id") == product_id:
                    return float(it.get("price") or 0)
            return 0.0

        async def cb_post(path, who, ent="ent_ksc", **kw):
            cl, tok = (ca, adm) if who == "admin" else (cm, mgr)
            r = await cl.post(f"/api/contra-bons{path}", headers=H(tok, ent), **kw)
            if r.status_code != 200:
                raise RuntimeError(f"kontrabon {path} gagal: {r.status_code} {r.text[:200]}")
            return r.json()

        # ── (1) LUNAS — 2 faktur satu supplier + potongan denda, dibayar sekali
        cir = await supplier_by_name("Cirebon Craft")
        if cir:
            price = await po_price("po_001", "prod_songket_palembang")
            b1 = await bill("po_001", [{"product_id": "prod_songket_palembang",
                                        "billed_qty": 30, "price": price}], "INV-CRB-2601")
            b2 = await bill("po_001", [{"product_id": "prod_songket_palembang",
                                        "billed_qty": 30, "price": price}], "INV-CRB-2602",
                            days_ago=4)
            cb = await cb_post("", "manager", json={
                "supplier_id": cir["id"], "entity_id": "ent_ksc",
                "bills": [{"bill_id": b1["id"]}, {"bill_id": b2["id"]}],
                "cycle_date": ago(days=3)[:10], "supplier_pic": "Bu Sri",
                "notes": "Siklus tukar faktur akhir bulan — 2 faktur songket."})
            cb = await cb_post(f"/{cb['id']}/deductions", "manager", json={
                "kind": "supplier_penalty", "amount": 500000,
                "reason_code": "cb_supplier_late",
                "note": "Kiriman songket terlambat 4 hari dari kesepakatan."})
            await cb_post(f"/{cb['id']}/submit", "manager")
            await cb_post(f"/{cb['id']}/verify", "manager")
            await cb_post(f"/{cb['id']}/approve", "admin")      # pembuat ≠ penyetuju
            await cb_post(f"/{cb['id']}/schedule", "manager", json={
                "planned_payment_date": ago(days=1)[:10], "method": "transfer",
                "bank_account_id": "bank_bca_ksc",
                "notes": "Masuk batch transfer mingguan."})
            await cb_post(f"/{cb['id']}/pay", "admin", json={
                "method": "transfer", "cash_type": "kas_besar",
                "bank_account_id": "bank_bca_ksc", "paid_at": ago(days=1),
                "notes": "Transfer BCA, bukti dikirim ke WhatsApp supplier."})
            made["cb"] += 1

        # ── (2) DIJADWALKAN BAYAR — sudah disetujui, menunggu tanggal transfer
        plb = await supplier_by_name("Palembang Silk House")
        if plb:
            price = await po_price("po_004", "prod_songket_palembang")
            ent = plb.get("entity_id") or "ent_ksc"
            b3 = await bill("po_004", [{"product_id": "prod_songket_palembang",
                                        "billed_qty": 40, "price": price}], "INV-PLB-2610",
                            ent=ent, days_ago=2)
            cb2 = await cb_post("", "manager", ent, json={
                "supplier_id": plb["id"], "entity_id": ent,
                "bills": [{"bill_id": b3["id"]}],
                "cycle_date": ago(days=1)[:10], "supplier_pic": "Pak Rudi",
                "notes": "Tukar faktur songket batch Q2."})
            await cb_post(f"/{cb2['id']}/submit", "manager", ent)
            await cb_post(f"/{cb2['id']}/verify", "manager", ent)
            await cb_post(f"/{cb2['id']}/approve", "admin", ent)
            await cb_post(f"/{cb2['id']}/schedule", "manager", ent, json={
                "planned_payment_date": ago(days=-3)[:10], "method": "transfer",
                "bank_account_id": "bank_bca_ksc",
                "notes": "Dibayar Selasa depan bersama batch transfer."})
            made["cb"] += 1

        # ── (3) DIAJUKAN + selisih 3-way BELUM diputus (harga faktur 4% di atas PO)
        solo = await supplier_by_name("Solo Weave")
        if solo:
            price = await po_price("po_003", "prod_endek_bali")
            ent = solo.get("entity_id") or "ent_ksc"
            b4 = await bill("po_003", [{"product_id": "prod_endek_bali", "billed_qty": 60,
                                        "price": round(price * 1.04, 2)}], "INV-SLO-2615",
                            ent=ent, days_ago=1)
            cb3 = await cb_post("", "manager", ent, json={
                "supplier_id": solo["id"], "entity_id": ent,
                "bills": [{"bill_id": b4["id"]}],
                "cycle_date": ago(days=0)[:10], "supplier_pic": "Pak Joko",
                "notes": "Harga endek naik 4% — supplier bilang sudah disepakati lisan."})
            await cb_post(f"/{cb3['id']}/submit", "manager", ent)
            made["cb"] += 1

            # ── (4) SATU faktur DIBIARKAN BEBAS (belum masuk kontrabon mana pun).
            # Tanpa ini, seluruh faktur supplier demo terpakai di tiga kontrabon di atas
            # sehingga wizard "Kontrabon baru" kosong untuk SEMUA supplier — fiturnya ada
            # tapi tidak bisa dicoba siapa pun pada data demo (terukur saat uji layar).
            await bill("po_003", [{"product_id": "prod_endek_bali", "billed_qty": 20,
                                   "price": price}], "INV-SLO-2620", ent=ent, days_ago=0)

            # ── (5) UANG MUKA supplier (kelebihan bayar, jalur FASE G-3) supaya pemilih
            # "Potongan otomatis" di wizard punya dokumen NYATA untuk ditawarkan. Dipilih
            # uang muka, bukan retur beli, karena uang muka tidak menggeser stok demo.
            b5 = await bill("po_003", [{"product_id": "prod_endek_bali", "billed_qty": 10,
                                        "price": price}], "INV-SLO-2625", ent=ent, days_ago=6)
            r5 = await ca.post(f"/api/vendor-bills/{b5['id']}/pay", headers=H(adm, ent), json={
                "amount": round(float(b5["grand_total"]) + 500000, 2), "method": "transfer",
                "cash_type": "kas_besar",
                "notes": "Kelebihan bayar disepakati menjadi uang muka siklus berikutnya",
                "variance": {"kind": "ap_advance", "reason_code": "supplier_advance",
                             "note": "Uang muka supplier untuk tukar faktur berikutnya"}})
            if r5.status_code != 200:
                print(f"  [warn] uang muka demo dilewati: {r5.status_code} {r5.text[:120]}")

    print(f"✅ Kontrabon (Fase G-7): {made['cb']} kontrabon demo dari {made['bills']} faktur "
          f"supplier · {made['schedules']} jadwal tukar faktur "
          "(1 LUNAS berpotongan denda · 1 dijadwalkan bayar · 1 diajukan dengan selisih "
          "3-way menunggu keputusan · 1 faktur bebas + 1 uang muka supplier agar wizard & "
          "potongan otomatis bisa dicoba)")
    return made["cb"]


async def seed_bank_statement():
    """FASE G-8 — **MUTASI BANK DEMO** untuk layar Rekonsiliasi Bank.

    Sumber datanya JUJUR: baris statement dibentuk dari `cash_transactions` NYATA hasil
    penerimaan pelanggan (seperti rekening koran sungguhan yang mencerminkan buku), plus
    dua kejadian yang memang ada di dunia nyata:
      * satu **dana masuk tak dikenal** (tanpa nama/nomor) → bahan latihan fitur TITIPAN;
      * satu **biaya administrasi bank** → bahan latihan tombol "Abaikan".

    Semua baris dibiarkan berstatus `unmatched` supaya pengguna sendiri yang menekan
    "Cocokkan otomatis" dan melihat tiga pita bekerja:
      1. nominal + tanggal + nomor dokumen di berita transfer → **tercocok otomatis**;
      2. nominal sama tapi tanggal bergeser & hanya ada nama  → **usulan** (dikonfirmasi user);
      3. tanpa nama/nomor & tanggal bergeser                 → **manual**.
    """
    from services import bank_recon_service as brs

    acc = await db.bank_accounts.find_one({"id": "bank_bca_ksc"}, {"_id": 0})
    if not acc:
        return 0
    for ent in await db.business_entities.distinct("id"):
        await brs.ensure_builtin_formats(ent, "seed")

    ar_cash = await db.cash_transactions.find(
        {"direction": "in", "cash_type": "kas_besar", "ref_type": "ar_receipt",
         "status": {"$ne": "void"}}, {"_id": 0}).sort("txn_date", -1).to_list(20)
    if not ar_cash:
        return 0

    def d(iso: str, plus: int = 0) -> str:
        base = datetime.fromisoformat(str(iso)[:10])
        return (base + timedelta(days=plus)).date().isoformat()

    def who(desc: str) -> str:
        # "Penerimaan AR-00001 — Toko Kain Sejahtera" → ("AR-00001", "TOKO KAIN SEJAHTERA")
        num, name = "", desc
        if "—" in desc:
            head, name = desc.split("—", 1)
            parts = [p for p in head.replace("Penerimaan", "").strip().split() if p]
            num = parts[-1] if parts else ""
        return num.strip(), name.strip().upper()

    lines = []
    t0 = ar_cash[0]
    n0, name0 = who(t0.get("description", ""))
    lines.append({"stmt_date": d(t0.get("txn_date")), "amount": float(t0.get("amount") or 0),
                  "direction": "in", "ref": n0,
                  "description": f"TRSF E-BANKING CR {name0} {n0}".strip()})
    if len(ar_cash) > 1:
        t1 = ar_cash[1]
        _, name1 = who(t1.get("description", ""))
        lines.append({"stmt_date": d(t1.get("txn_date"), 2),
                      "amount": float(t1.get("amount") or 0), "direction": "in",
                      "description": f"TRSF E-BANKING CR {name1}"})
    if len(ar_cash) > 2:
        t2 = ar_cash[2]
        lines.append({"stmt_date": d(t2.get("txn_date"), 1),
                      "amount": float(t2.get("amount") or 0), "direction": "in",
                      "description": "SETORAN KLIRING 8891 NONREF"})
    lines.append({"stmt_date": d(t0.get("txn_date"), 1), "amount": 3750000.0, "direction": "in",
                  "description": "TRSF E-BANKING CR 8829911 NONREF"})
    lines.append({"stmt_date": d(t0.get("txn_date"), 1), "amount": 15000.0, "direction": "out",
                  "description": "BIAYA ADM"})
    # FASE G-7 US8 — satu dana KELUAR yang belum dibukukan: nominalnya PAS dengan sisa
    # kontrabon yang sudah disetujui & dijadwalkan. Tanpa baris ini, tombol "Bayar
    # kontrabon" di layar Rekonsiliasi Bank tidak punya bahan latihan sama sekali.
    _cb = await db.contra_bons.find_one({"status": "scheduled_payment"}, {"_id": 0})
    if _cb:
        _out = round(float((_cb.get("totals") or {}).get("outstanding") or 0), 2)
        if _out > 0:
            lines.append({
                "stmt_date": d(t0.get("txn_date"), 2), "amount": _out, "direction": "out",
                "description": f"TRSF E-BANKING DB {(_cb.get('supplier_name') or '').upper()}",
            })

    res = await brs.import_lines("bank_bca_ksc", acc.get("entity_id") or "ent_ksc", lines,
                                "seed", entity_ids=None)
    n_fmt = await db.bank_statement_formats.count_documents({"active": True})
    print(f"✅ Mutasi bank (Fase G-8): {res['imported']} baris statement di "
          f"{acc.get('name')} · {n_fmt} template parser bank "
          "(1 siap cocok otomatis · 1 usulan · 1 manual · 1 dana tak dikenal · 1 biaya bank"
          + (" · 1 dana keluar untuk kontrabon" if _cb else "") + ")")
    return res["imported"]


async def seed_payment_plans():
    """FASE G-2 — contoh **RENCANA PEMBAYARAN & DENDA NYATA** untuk data demo.

    Semuanya dibuat lewat `services/payment_plan_service.py` + `services/penalty_service.py`
    (mesin yang sama dengan UI), jadi nomor dokumen, validasi Σ baris, alokasi pembayaran,
    perhitungan denda, jurnal, dan jejak `refs[]` lahir dari jalur produksi — bukan data
    palsu yang "kelihatan benar" tetapi tak pernah melewati aturan.

    Tiga kondisi supaya seluruh status terlihat di UI dan invarian INV-PAY/INV-PEN punya
    data nyata: (1) DP + 3 cicilan dengan cicilan pertama TELAT → usulan denda `draft`;
    (2) milestone 30/40/30 yang masih rapi; (3) satu nota denda yang sudah DITERBITKAN.
    """
    from services import payment_plan_service as _plans
    from services import penalty_service as _pen

    actor = {"name": "Sistem Seed", "role": "admin"}
    made = 0
    # Seed membersihkan `journal_entries` di awal. Kalau rencana & nota denda demo
    # dibiarkan hidup, jurnal dendanya ikut hilang → INV-PEN-03 memerah. Jadi contoh
    # lama dihapus lalu dibentuk ulang lewat mesin yang sama (idempotent & konsisten GL).
    _old_plans = [x["id"] async for x in db.payment_plans.find({}, {"_id": 0, "id": 1})]
    _old_pen = [x["id"] async for x in db.penalties.find({}, {"_id": 0, "id": 1})]
    if _old_plans or _old_pen:
        for _coll in ("sales_orders", "payment_plans", "penalties"):
            await db[_coll].update_many(
                {}, {"$pull": {"refs": {"doc_id": {"$in": _old_plans + _old_pen}}}})
        await db.payment_plans.delete_many({"id": {"$in": _old_plans}})
        await db.penalties.delete_many({"id": {"$in": _old_pen}})
    orders = await db.sales_orders.find(
        {"status": {"$nin": ["cancelled", "draft"]}}, {"_id": 0, "id": 1, "number": 1,
                                                       "grand_total": 1, "created_at": 1,
                                                       "payments": 1, "entity_id": 1}
    ).sort("number", 1).to_list(30)
    # Pilih pesanan yang MASIH punya sisa tagihan — kalau sudah lunas, seluruh baris jadwal
    # otomatis berstatus lunas dan contoh denda tidak akan pernah muncul di layar demo.
    def _outstanding(o):
        paid = sum(float(p.get("amount") or 0) for p in (o.get("payments") or []))
        return round(float(o.get("grand_total") or 0) - paid, 2)

    kandidat = [o for o in orders
                if float(o.get("grand_total") or 0) > 0 and _outstanding(o) > 1000]
    if not kandidat:
        return 0

    # FASE E-8 — contoh denda WAJIB lahir di SETIAP badan usaha yang punya tagihan.
    #
    # Dulu blok ini mengambil "2 pesanan pertama menurut nomor". Begitu badan usaha
    # kedua punya pesanan (`KANDA/SO-00001`), nomornya berada di DEPAN `SO-0001`
    # secara alfabet — sehingga SELURUH contoh rencana bayar & nota denda pindah ke
    # CV Kanda Suka dan PT Kain Suka Cita tidak punya satu pun. Dua akibatnya:
    #   1. layar demo pincang (Meja Finance KSC: antrean denda selalu kosong);
    #   2. POC isolasi E-0 (L4) kehilangan data untuk membuktikan denda PT lain
    #      TIDAK bocor — bukti-merahnya jadi hampa dan gate memerah.
    # Urutan alfabet nomor dokumen bukan kriteria bisnis; "satu contoh per badan
    # usaha" adalah. Jadi pemilihannya sekarang dikelompokkan per badan usaha.
    per_entity = {}
    for o in kandidat:
        per_entity.setdefault(o.get("entity_id") or "", []).append(o)

    today = datetime.now(timezone.utc)

    async def _plan_dp_installment(o):
        """DP + 3 cicilan; cicilan pertama sengaja telat → usulan nota denda lahir."""
        total = round(float(o["grand_total"]), 2)
        paid = round(sum(float(x.get("amount") or 0) for x in (o.get("payments") or [])), 2)
        dp = paid if 0 < paid < total * 0.9 else round(total * 0.20, 2)
        sisa = round(total - dp, 2)
        cic = round(sisa / 3, 2)
        lines = [
            {"kind": "dp", "label": "Uang Muka (DP) 20%", "basis": "amount", "amount": dp,
             "due_rule": "fixed_date",
             "due_date": (today - timedelta(days=75)).date().isoformat()},
            {"kind": "installment", "label": "Cicilan 1/3", "basis": "amount", "amount": cic,
             "due_rule": "fixed_date",
             "due_date": (today - timedelta(days=40)).date().isoformat()},
            {"kind": "installment", "label": "Cicilan 2/3", "basis": "amount", "amount": cic,
             "due_rule": "fixed_date",
             "due_date": (today + timedelta(days=5)).date().isoformat()},
            {"kind": "installment", "label": "Cicilan 3/3", "basis": "amount",
             "amount": round(sisa - cic * 2, 2), "due_rule": "fixed_date",
             "due_date": (today + timedelta(days=35)).date().isoformat()},
        ]
        plan = await _plans.create_plan("sales_order", o["id"],
                                       {"mode": "dp_installment", "lines": lines,
                                        "note": "Kesepakatan DP + 3 cicilan"}, actor)
        # Usulan denda dari baris yang telat (draft — belum menyentuh buku besar).
        drafts = await _pen.accrue_plan(plan, actor_name="Sistem Seed")
        # Satu diterbitkan supaya status `issued` + jurnalnya terlihat di demo.
        if drafts:
            try:
                await _pen.issue(drafts[0]["id"], {"name": "Dewi Rahayu", "role": "manager"})
            except Exception:  # noqa: BLE001
                pass
        return plan

    async def _plan_milestone(o):
        """Milestone 30/40/30 — jadwal sehat, belum ada denda."""
        total = round(float(o["grand_total"]), 2)
        m1 = round(total * 0.30, 2)
        m2 = round(total * 0.40, 2)
        lines = [
            {"kind": "milestone", "label": "30% saat pesanan disetujui", "basis": "amount",
             "amount": m1, "due_rule": "fixed_date", "due_date": today.date().isoformat()},
            {"kind": "milestone", "label": "40% saat barang dikirim", "basis": "amount",
             "amount": m2, "due_rule": "fixed_date",
             "due_date": (today + timedelta(days=14)).date().isoformat()},
            {"kind": "milestone", "label": "30% saat barang diterima", "basis": "amount",
             "amount": round(total - m1 - m2, 2), "due_rule": "fixed_date",
             "due_date": (today + timedelta(days=30)).date().isoformat()},
        ]
        return await _plans.create_plan("sales_order", o["id"],
                                        {"mode": "milestone", "lines": lines,
                                         "note": "Pembayaran bertahap per milestone"}, actor)

    for ent_id in sorted(per_entity):
        milik = per_entity[ent_id]
        await _plan_dp_installment(milik[0])
        made += 1
        if len(milik) > 1:
            await _plan_milestone(milik[1])
            made += 1

    n_pen = await db.penalties.count_documents({})
    per_ent_pen = {}
    async for p in db.penalties.find({}, {"_id": 0, "entity_id": 1}):
        key = p.get("entity_id") or "-"
        per_ent_pen[key] = per_ent_pen.get(key, 0) + 1
    print(f"✅ Rencana pembayaran (Fase G-2): {made} rencana · {n_pen} nota denda "
          f"(usulan + terbit) · sebaran per badan usaha: "
          + " ".join(f"{k}={v}" for k, v in sorted(per_ent_pen.items())))
    return made


async def seed_payment_variances():
    """FASE G-3 — contoh **KEPUTUSAN SELISIH PEMBAYARAN** (lebih & kurang bayar).

    Dibuat lewat `services/ar_receipt_service.py` + `services/payment_variance_service.py`
    (mesin yang sama dengan UI) supaya nomor dokumen, wewenang, label alasan, jurnal, dan
    jejak `refs[]` lahir dari jalur produksi — bukan data karangan.

    Tiga kondisi supaya seluruh perlakuan terlihat di layar demo:
      (1) kurang bayar receh (di dalam toleransi) → **otomatis** lunas sebagai pembulatan;
      (2) kurang bayar besar → keputusan **sisa tetap piutang** dengan label alasan;
      (3) lebih bayar → keputusan **simpan sebagai deposit** pelanggan.

    Dua kehati-hatian yang membuat data demo tetap SEHAT:
      * hanya pesanan yang pendapatannya SUDAH dijurnal yang dibayar — kalau tidak, kredit
        Piutang tak punya debit pasangannya dan saldo AR jadi negatif (INV-AR-01 benar
        memperingatkan: itu uang muka, bukan pelunasan piutang);
      * contoh (2) & (3) memakai alokasi SEBAGIAN sehingga rencana pembayaran demo (FASE
        G-2) tetap aktif dan antrean denda tidak ikut berubah.

    Sengaja TIDAK meninggalkan selisih yang menggantung supaya antrean "Selisih Bayar"
    pada DB baru benar-benar kosong (dan INV-VAR-01 tetap hijau tanpa peringatan palsu).
    """
    if await db.payment_variance_decisions.count_documents({}) > 0:
        return 0
    from services import ar_receipt_service as _ars
    from services import payment_plan_service as _plans

    actor = {"id": "user_admin_01", "name": "Sistem Seed", "role": "admin"}
    dead = {"cancelled", "draft", "expired", "rejected"}
    plan_docs = [p["doc_id"] async for p in db.payment_plans.find({}, {"_id": 0, "doc_id": 1})]

    def _outstanding(o):
        paid = sum(float(p.get("amount") or 0) for p in (o.get("payments") or []))
        return round(float(o.get("grand_total") or 0) - paid, 2)

    async def _fresh(order_id):
        return await db.sales_orders.find_one({"id": order_id}, {"_id": 0}) or {}

    plain, planned = [], []          # tanpa rencana · dengan rencana (sisa besar)
    for o in await db.sales_orders.find({}, {"_id": 0}).sort("number", 1).to_list(200):
        if o.get("status") in dead:
            continue
        if str((o.get("payment_profile_method") or o.get("payment_term_code") or "")).lower() \
                in {"kontan", "tunai", "cash"}:
            continue
        out = _outstanding(o)
        if out <= 500000:
            continue
        if not await db.journal_entries.find_one(
                {"source_type": "sales_order", "source_id": o["id"], "status": {"$ne": "void"}},
                {"_id": 1}):
            continue
        (planned if o["id"] in plan_docs else plain).append((o, out))
    if not plain and not planned:
        return 0

    made = 0
    # (1) Kurang bayar receh → pembulatan otomatis (berjurnal beban selisih, berlabel).
    if plain:
        o1, out1 = plain[0]
        try:
            await _ars.create_receipt({
                "customer_id": o1["customer_id"], "amount": round(out1 - 2500, 2),
                "method": "transfer", "notes": "Pelunasan (dipotong biaya transfer) — seed",
                "allocations": [{"order_id": o1["id"], "amount": round(out1 - 2500, 2)}],
            }, actor)
            made += 1
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] contoh pembulatan selisih dilewati: {_e}")

    # Pesanan bersisa besar untuk contoh (2) & (3) — alokasi SEBAGIAN saja.
    pool = sorted(planned + plain[1:], key=lambda t: -t[1])
    if pool:
        o2 = pool[0][0]
        # (2) Kurang bayar dari yang jatuh tempo → sisa tetap jadi piutang.
        plan = await _plans.get_active("sales_order", o2["id"])
        due = _plans.due_now_amount(plan) if plan else _outstanding(await _fresh(o2["id"]))
        if due <= 0:
            due = _outstanding(await _fresh(o2["id"]))
        part = round(due * 0.5, -3)
        if part > 0:
            try:
                await _ars.create_receipt({
                    "customer_id": o2["customer_id"], "amount": part, "method": "transfer",
                    "notes": "Bayar sebagian sesuai kesepakatan — seed",
                    "allocations": [{"order_id": o2["id"], "amount": part}],
                    "variance": {"kind": "outstanding", "reason_code": "partial_payment_agreed",
                                 "note": "Pelanggan janji melunasi sisanya bulan depan"},
                }, actor)
                made += 1
            except Exception as _e:  # noqa: BLE001
                print(f"  [warn] contoh kurang bayar dilewati: {_e}")

        # (3) Lebih bayar → kelebihannya disimpan sebagai deposit pelanggan.
        left = _outstanding(await _fresh(o2["id"]))
        target = round(min(left, 3000000.0), -3)
        extra = 750000.0
        if target > 0:
            try:
                await _ars.create_receipt({
                    "customer_id": o2["customer_id"], "amount": round(target + extra, 2),
                    "method": "transfer", "notes": "Transfer melebihi tagihan — seed",
                    "allocations": [{"order_id": o2["id"], "amount": target}],
                    "variance": {"kind": "deposit", "reason_code": "customer_overtransfer",
                                 "note": "Kelebihan disimpan untuk pesanan berikutnya"},
                }, actor)
                made += 1
            except Exception as _e:  # noqa: BLE001
                print(f"  [warn] contoh lebih bayar dilewati: {_e}")

    n = await db.payment_variance_decisions.count_documents({})
    print(f"✅ Selisih pembayaran (Fase G-3): {made} kwitansi uji · {n} keputusan berlabel")
    return made


async def seed_production():
    """R6.4 — seed contoh Produksi In-House: 2 BOM (1-komponen & MULTI-komponen) + 3 Work Order
    (1 SELESAI -> HPP + roll barang jadi + JE overhead, 1 DIRILIS, 1 DRAFT).

    Dipanggil PALING AKHIR (setelah GL opening-balance true-up + order makloon) agar rekonsiliasi
    akun Persediaan 1-1300 tetap utuh. Memakai service SSOT `production_service` supaya roll,
    movement, dan jurnal identik dengan alur produksi nyata (tanpa insert manual).
    Set env SKIP_SEED_PRODUCTION=1 untuk melewati (mis. test isolasi butuh stok penuh).
    """
    import os as _os
    if _os.environ.get("SKIP_SEED_PRODUCTION"):
        print("  [skip] seed_production dilewati (SKIP_SEED_PRODUCTION set)")
        return 0
    from services import production_service as prod

    ent = "ent_ksc"
    scope = {"entity_id": ent}

    # 1) Produk output kombinasi (hasil produksi in-house) — dibuat bila belum ada.
    KMB_ID = "prod_kombinasi_batik_lurik"
    if not await db.products.find_one({"id": KMB_ID}, {"_id": 0}):
        await db.products.insert_one({
            "id": KMB_ID, "sku": "KMB-BTL-001", "name": "Kain Kombinasi Batik-Lurik (per Yard)",
            "category": "Kombinasi", "variant": "Seragam", "color": "Multi",
            "color_code": "KN-MIX-01", "color_name": "Kombinasi Batik-Lurik", "color_hex": "#7C5CBF",
            "motif": "Mega Mendung + Lurik", "grade": "A", "stage": "finished", "fabric_type": "woven",
            "supplier": "Produksi In-House", "base_unit": "yard", "price": 128000,
            "harga_pokok": 0, "gramasi": 135, "lebar": 1.15, "image": "", "status": "active",
            "uom_conversions": [], "batch_lot_rolls": [], "reorder_point": 100.0, "reorder_qty": 200.0,
            "description": "Kain kombinasi panel Batik Mega Mendung + Lurik Klasik, dijahit & "
                           "difinishing di gudang sendiri (output Work Order produksi in-house).",
            "created_at": ago(days=60), "updated_at": ago(days=5),
        })

    async def _avail(pid, wid):
        b = await db.inventory_balances.find_one(
            {"product_id": pid, "warehouse_id": wid, "owner_entity_id": ent},
            {"_id": 0, "available_qty": 1})
        return float((b or {}).get("available_qty", 0) or 0)

    boms_made, wos_made, completed = 0, 0, 0

    # 2) BOM A — 1 komponen + overhead: Celup & Finishing Grey -> Batik Mega Mendung Premium.
    bom_celup = await prod.create_bom({
        "name": "Celup & Finishing In-House: Grey Katun -> Batik Mega Mendung",
        "output_product_id": "prod_batik_mega",
        "overhead_per_unit": 3500,
        "components": [{"material_product_id": "prod_grey_katun", "qty_per_unit": 1.05}],
        "notes": "Susut celup +-5% (1,05 yard grey per 1 yard jadi). Overhead = listrik, obat celup, tenaga kerja.",
    }, ent, actor_name="Seed")
    boms_made += 1

    # 3) BOM B — MULTI komponen: panel Batik + panel Lurik -> Kain Kombinasi (jahit in-house).
    bom_kombinasi = await prod.create_bom({
        "name": "Jahit Kombinasi In-House: Batik + Lurik -> Kain Kombinasi",
        "output_product_id": KMB_ID,
        "overhead_per_unit": 4000,
        "components": [
            {"material_product_id": "prod_batik_mega", "qty_per_unit": 0.6},
            {"material_product_id": "prod_lurik_classic", "qty_per_unit": 0.5},
        ],
        "notes": "Panel 60% batik + 50% lurik (termasuk allowance jahit). Overhead = jahit, obras, packing.",
    }, ent, actor_name="Seed")
    boms_made += 1

    # 4) WO SELESAI — celup 40 yard di Gudang Surabaya (bahan grey tersedia dari hasil makloon).
    grey_avail = await _avail("prod_grey_katun", "wh_surabaya")
    qty_done = 40.0 if grey_avail >= 42.0 else float(int(max(0.0, (grey_avail - 2) / 1.05)))
    if qty_done >= 5:
        wo1 = await prod.create_work_order({
            "bom_id": bom_celup["id"], "planned_qty": qty_done, "warehouse_id": "wh_surabaya",
            "notes": "Batch celup mingguan — pesanan reguler retail Surabaya.",
        }, ent, actor_name="Eko Prasetyo")
        await prod.release_work_order(wo1["id"], scope, actor_name="Eko Prasetyo")
        await prod.complete_work_order(wo1["id"], scope, actor_name="Eko Prasetyo")
        wos_made += 1
        completed += 1
    else:
        print(f"  [warn] WO celup dilewati: stok grey wh_surabaya kurang ({grey_avail})")

    # 5) WO DIRILIS + WO DRAFT — kombinasi di Gudang Bandung (bahan batik & lurik tersedia).
    batik_b = await _avail("prod_batik_mega", "wh_bandung")
    lurik_b = await _avail("prod_lurik_classic", "wh_bandung")
    if batik_b >= 30 and lurik_b >= 25:
        wo2 = await prod.create_work_order({
            "bom_id": bom_kombinasi["id"], "planned_qty": 50, "warehouse_id": "wh_bandung",
            "notes": "Pesanan seragam korporat — menunggu operator jahit shift 2.",
        }, ent, actor_name="Eko Prasetyo")
        await prod.release_work_order(wo2["id"], scope, actor_name="Dewi Rahayu")
        wos_made += 1
        await prod.create_work_order({
            "bom_id": bom_kombinasi["id"], "planned_qty": 30, "warehouse_id": "wh_bandung",
            "notes": "Rencana produksi minggu depan (masih draft, belum dirilis).",
        }, ent, actor_name="Eko Prasetyo")
        wos_made += 1
    else:
        print(f"  [warn] WO kombinasi dilewati: stok bandung batik={batik_b} lurik={lurik_b}")

    print(f"OK Produksi in-house seeded ({boms_made} BOM, {wos_made} Work Order · {completed} selesai)")
    return wos_made


# 1×1 px PNG — dipakai sebagai berkas bukti/artwork contoh (kecil, tidak membebani repo).
_PNG_1PX = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
            b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
            b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


async def seed_rnd():
    """FASE F — data demo **R&D & Desain** lewat LAYANAN NYATA (bukan insert mentah).

    Yang dibentuk (semuanya melalui jalur produksi yang sama dengan UI, sehingga nomor
    dokumen, validasi, kontrak harga, mutasi stok & `refs[]` semuanya sah):
      * 1 master desain ber-kode + artwork + disahkan  → prasyarat proofing (PS-14)
      * 2 spesifikasi: 1 sudah **ACC** (produk lahir, BELUM boleh dijual) + 1 masih
        **menunggu ACC** (supaya antrean persetujuan tidak kosong)
      * 1 permintaan **labdip** ke **2 supplier** → round nyata (bukti + catatan + hasil
        ukur) → 1 ACC skor 92, 1 revisi lalu ACC skor 84 → **pemenang diputus** →
        kontrak harga + barang supplier terbentuk (menutup `sample_ref` Fase E)
      * 1 pengambilan bahan 3 meter dari roll → **stok gudang berkurang** (PS-19)
      * 1 permintaan **proofing** yang masih berjalan → papan SLA & antrean terisi

    Idempotent: dilewati bila `md_specs` sudah berisi data.
    """
    if await db.md_specs.count_documents({}) > 0:
        print("ℹ️  data R&D sudah ada — seed R&D dilewati")
        return 0
    import sys as _sys
    _sys.path.insert(0, "/app/backend")
    from services import design_gallery_service as _dg
    from services import rnd_sample_service as _smp
    from services import rnd_spec_service as _spec

    ent = "ent_ksc"
    ADMIN = {"name": "Andi Wijaya", "role": "admin"}
    RND = "Dewi Lestari"

    # ── 1. Master desain (prasyarat proofing) ────────────────────────────────
    # `design_gallery` adalah MASTER (tidak ikut direset), jadi pakai ulang bila ada.
    design_id = ""
    try:
        existing = await db.design_gallery.find_one({"code": "DSG-PARANG-01"},
                                                    {"_id": 0, "id": 1, "status": 1})
        if existing:
            design_id = existing["id"]
            if existing.get("status") != "approved":
                await _dg.approve_design(design_id, ADMIN["name"], "Disahkan ulang oleh seed")
            print("   · desain DSG-PARANG-01 sudah ada — dipakai ulang")
        else:
            dsg = await _dg.create_gallery({
                "title": "Parang Modern Monokrom", "code": "DSG-PARANG-01",
                "design_type": "motif", "repeat_cm": 32, "color_count": 3, "screen_count": 3,
                "story": "Motif parang disederhanakan untuk koleksi kantor.",
                "tags": ["parang", "monokrom", "klasik"],
            }, RND, ent)
            design_id = dsg["id"]
            await _dg.add_file(design_id, "artwork_parang.png", "image/png", _PNG_1PX)
            await _dg.approve_design(design_id, ADMIN["name"],
                                     "Artwork & repeat sudah diperiksa")
            print(f"   · desain {dsg['code']} v{dsg['version']} disahkan "
                  "(siap dipakai proofing)")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed desain R&D dilewati: {_e}")

    # ── 1b. Rating demo desain (bintang 1–5) supaya kartu "Rating Desain" terisi ──
    # Idempotent: `set_rating` meng-upsert 1 nilai per penilai, jadi re-run tidak
    # menggandakan. Dua penilai (admin + manager) agar rata-rata terlihat nyata.
    try:
        admin_u = await db.users.find_one({"email": "admin@kainnusantara.id"},
                                          {"_id": 0, "id": 1, "name": 1})
        mgr_u = await db.users.find_one({"email": "manager@kainnusantara.id"},
                                        {"_id": 0, "id": 1, "name": 1})
        raters = [(admin_u, [5, 4, 5]), (mgr_u, [4, 3, 5])]
        designs = await db.design_gallery.find(
            {"entity_id": ent}, {"_id": 0, "id": 1}).sort("created_at", 1).to_list(50)
        rated = 0
        for u, pattern in raters:
            if not u:
                continue
            for i, dsg in enumerate(designs):
                await _dg.set_rating(dsg["id"], u["id"], u.get("name", ""),
                                     pattern[i % len(pattern)])
                rated += 1
        print(f"   · rating demo desain: {rated} nilai pada {len(designs)} desain")
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed rating desain dilewati: {_e}")

    color = await db.color_library.find_one({"status": "active"}, {"_id": 0})
    color_id = (color or {}).get("id", "")

    # ── 2. Spesifikasi A — sampai ACC (produk lahir, belum boleh dijual) ─────
    spec_a = await _spec.create_spec({
        "title": "Katun Combed 150 gsm Warna Khusus",
        "category": "Katun", "base_unit": "meter", "sku_hint": "RND-KTN-150",
        "sample_type_hint": "labdip",
        "target": {"stage": "finished", "fabric_type": "knit", "gramasi": 150,
                   "lebar": 160, "grade": "A"},
        "color_target": {"color_id": color_id},
        "target_price": 48000,
        "notes": "Permintaan pelanggan korporat: warna harus konsisten antar batch (ΔE ≤ 1.5).",
    }, entity_id=ent, actor=RND)
    await _spec.submit_spec(spec_a["id"], RND)
    appr = await _spec.approve_spec(spec_a["id"], {
        "sku": "RND-KTN-150", "name": "Katun Combed 150 gsm Warna Khusus", "price": 52000,
        "note": "Target teknis jelas & terukur — lanjut cari supplier.",
    }, ADMIN)
    print(f"   · {spec_a['number']} ACC → produk {appr['product']['sku']} lahir "
          f"(tahap '{appr['product'].get('lifecycle')}' — belum boleh dijual)")

    # ── 3. Spesifikasi B — berhenti di "menunggu ACC" (antrean persetujuan) ──
    spec_b = await _spec.create_spec({
        "title": "Rayon Printing Motif Parang Monokrom",
        "category": "Rayon", "base_unit": "yard", "sku_hint": "RND-RYN-PRG",
        "sample_type_hint": "proofing",
        "target": {"stage": "finished", "fabric_type": "woven", "gramasi": 110,
                   "lebar": 145, "grade": "A"},
        "color_target": {"color_id": color_id},
        "design_id": design_id,
        "target_price": 39000,
        "notes": "Proofing printing — warna & repeat harus sama dengan artwork v1.",
    }, entity_id=ent, actor=RND)
    await _spec.submit_spec(spec_b["id"], RND)
    print(f"   · {spec_b['number']} diajukan (menunggu ACC manager)")

    # ── 4. Permintaan labdip ke 2 supplier + round nyata ────────────────────
    sups = await db.suppliers.find({"entity_id": ent, "status": "active"},
                                   {"_id": 0, "id": 1, "name": 1}).to_list(10)
    if len(sups) < 2:
        print("  [warn] supplier kurang dari 2 — seed round sample dilewati")
        return 2
    s1, s2 = sups[0], sups[1]

    smp1 = await _smp.create_sample({
        "spec_id": spec_a["id"], "sample_type": "labdip",
        "title": "Labdip Katun Combed 150 gsm — warna khusus",
        "brief": "Cocokkan warna target maksimal ΔE 1.5. Kirim swatch 3 meter + hasil ukur.",
        "color_target": {"color_id": color_id},
        "target_date": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()[:10],
        "qty_requested": 3, "unit": "meter",
    }, entity_id=ent, actor=RND)
    await _smp.send_sample(smp1["id"], [s1["id"], s2["id"]], note="Mohon kirim swatch 3 m",
                           actor=RND)
    cur = await _smp.get_sample(smp1["id"])

    async def _do_round(sample_id, supplier_id, note, meas, cost, result, score, assess_note):
        """Satu siklus round penuh: unggah bukti → setor hasil → dinilai."""
        doc = await _smp.get_sample(sample_id)
        mine = [r for r in (doc.get("rounds") or [])
                if r["supplier_id"] == supplier_id and r["status"] == "open"]
        rnd_row = max(mine, key=lambda r: int(r.get("round_no") or 0))
        await _smp.add_attachment(sample_id, rnd_row["id"], "hasil_labdip.png",
                                  "image/png", _PNG_1PX, RND)
        await _smp.submit_round(sample_id, rnd_row["id"],
                               {"note": note, "measurements": meas, "cost": cost}, RND)
        await _smp.assess_round(sample_id, rnd_row["id"],
                                {"result": result, "score": score, "note": assess_note}, ADMIN)
        return rnd_row

    await _do_round(smp1["id"], s1["id"],
                    "Warna sangat dekat dengan target, handfeel lembut.",
                    {"delta_e": 0.9, "gsm_actual": 151, "shrinkage_pct": 2,
                     "colorfastness_wash": 4, "colorfastness_rub": 4},
                    165000, "acc", 92, "ΔE 0.9 — paling presisi di antara peserta.")
    await _do_round(smp1["id"], s2["id"],
                    "Warna satu tingkat lebih tua dari target.",
                    {"delta_e": 2.4, "gsm_actual": 148, "shrinkage_pct": 3,
                     "colorfastness_wash": 3, "colorfastness_rub": 4},
                    140000, "revisi", 68, "Minta perbaikan: turunkan intensitas warna.")
    await _smp.open_round(smp1["id"], s2["id"], note="Perbaikan intensitas warna",
                          actor=ADMIN)
    await _do_round(smp1["id"], s2["id"],
                    "Sudah lebih muda, mendekati target.",
                    {"delta_e": 1.4, "gsm_actual": 149, "shrinkage_pct": 2,
                     "colorfastness_wash": 4, "colorfastness_rub": 4},
                    140000, "acc", 84, "Layak jadi cadangan kedua.")

    # ── 5. Ambil bahan 3 meter dari roll → stok gudang BERKURANG (PS-19) ─────
    roll = await db.inventory_rolls.find_one(
        {"status": "available", "length_remaining": {"$gte": 5}}, {"_id": 0})
    if roll:
        try:
            await _smp.issue_material(smp1["id"],
                                      {"roll_id": roll["id"], "qty": 3,
                                       "note": "Bahan pembanding untuk uji cuci"}, RND)
            print(f"   · ambil 3 {roll.get('unit', 'meter')} dari roll {roll.get('roll_no')} "
                  f"— stok gudang berkurang (mutasi sample_issue)")
        except Exception as _e:  # noqa: BLE001
            print(f"  [warn] pengambilan bahan sample dilewati: {_e}")

    # ── 6. Putuskan pemenang → kontrak harga + barang supplier (Fase E) ──────
    dec = await _smp.decide_sample(smp1["id"], {
        "supplier_id": s1["id"], "reason_code": "warna_paling_dekat",
        "note": "ΔE 0.9 & tahan cuci 4 — paling dekat dengan target pelanggan.",
        "price": 46500, "supplier_sku": "SUP-KTN-150", "supplier_uom": "meter",
        "moq": 100, "lead_time_days": 14,
    }, ADMIN)
    decision = (dec.get("sample") or dec).get("decision") or {}
    print(f"   · {smp1['number']} diputus → pemenang {s1['name']} · kontrak "
          f"{decision.get('contract_number') or '(otomatis mati)'}")

    # ── 7. Permintaan proofing yang MASIH BERJALAN (papan SLA tidak kosong) ──
    smp2 = await _smp.create_sample({
        "spec_id": spec_b["id"], "sample_type": "proofing",
        "title": "Proofing Rayon Motif Parang Monokrom",
        "brief": "Cetak sesuai artwork v1. Periksa repeat 32 cm & ketajaman garis.",
        "color_target": {"color_id": color_id}, "design_id": design_id,
        "target_date": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat()[:10],
        "qty_requested": 2, "unit": "yard",
    }, entity_id=ent, actor=RND)
    await _smp.send_sample(smp2["id"], [s1["id"]], note="Kirim hasil cetak 2 yard",
                           actor=RND)
    print(f"   · {smp2['number']} dikirim (round 1 berjalan — menunggu hasil supplier)")

    # ── 8. PS-18 — data demo KPI desainer & eskalasi SLA (idempotent) ─────────
    # Tanpa ini, laporan KPI hanya berisi SATU pelaksana dan papan eskalasi selalu
    # kosong, sehingga dua fitur PS-18 tidak terlihat sama sekali saat demo.
    try:
        _sys.path.insert(0, "/app/scripts")
        from seed_rnd_kpi_demo import seed as _seed_kpi_demo
        await _seed_kpi_demo(verbose=True)
    except Exception as _e:  # noqa: BLE001
        print(f"  [warn] seed demo KPI desainer dilewati: {_e}")

    print("OK Data demo R&D (Fase F) seeded: 2 spesifikasi · 2 permintaan sample · "
          "3 round dinilai · 1 keputusan → kontrak · 1 pengambilan bahan")
    return 2


def _seed_e9_chain_demo() -> None:
    """FASE E-9 — rantai retur demo (jual → beli internal antar-PT → retur berantai).

    Dijalankan sebagai proses terpisah karena rantainya dibuat lewat **HTTP nyata**
    (alur produksi, bukan suntikan dokumen mentah) supaya jurnal, pajak, saldo antar-PT,
    dan invarian tetap sah. Seed ini menghapus `interco_*` & dokumen retur, jadi tanpa
    pemanggilan di sini layar **Jejak Retur** dan "diambil dari PT lain" kembali KOSONG
    setiap kali data demo dipulihkan.

    Best-effort: kalau backend belum hidup, seed TIDAK boleh gagal — cukup beri tahu
    cara menjalankannya ulang.
    """
    import subprocess  # noqa: PLC0415
    import sys as _sys  # noqa: PLC0415
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "seed_e9_chain_demo.py")
    if not os.path.exists(script):
        return
    try:
        res = subprocess.run([_sys.executable, script, "--force"],
                             capture_output=True, text=True, timeout=420)
        tail = [ln for ln in (res.stdout or "").splitlines() if ln.strip()][-7:]
        if res.returncode == 0:
            print("✅ Rantai retur demo (FASE E-9) dibuat lewat alur nyata:")
            for ln in tail:
                print(f"   {ln}")
        else:
            print(f"  [warn] rantai retur demo E-9 dilewati (rc={res.returncode}). "
                  f"Jalankan manual: python seed_e9_chain_demo.py --force")
            for ln in tail:
                print(f"   {ln}")
    except Exception as exc:  # noqa: BLE001 — data demo pelengkap, bukan syarat seed
        print(f"  [warn] rantai retur demo E-9 dilewati: {exc}")


async def _finalize_line_codes(mongo_url: str) -> None:
    """FASE L — sapuan penutup: produk demo yang belum bergolong lini + stempel ulang.

    Dijalankan SESUDAH seluruh langkah seed (termasuk demo rantai E-9 yang membuat
    produk & dokumennya sendiri). Aturannya sengaja sempit dan bisa dijelaskan:
    `fabric_type == "knit"` → lini `knit`, sisanya lini `woven`. Tidak ada tebakan
    "printing" di sini — menebak lini printing untuk kain demo yang tidak punya
    motif/desain justru menaruh pekerjaan di papan yang salah.
    Sesudah produknya lengkap, dokumen distempel ulang lewat pintu yang sama
    (`line_scope.backfill`) supaya `line_codes[]` tidak tertinggal.
    """
    client = AsyncIOMotorClient(mongo_url)
    dbx = client[os.environ["DB_NAME"]]
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
        from services import line_scope as _lines            # noqa: PLC0415
        blank = {"$or": [{"line_code": {"$exists": False}}, {"line_code": ""},
                         {"line_code": None}]}
        n_knit = (await dbx.products.update_many(
            {**blank, "fabric_type": "knit"}, {"$set": {"line_code": "knit"}})).modified_count
        n_woven = (await dbx.products.update_many(
            blank, {"$set": {"line_code": "woven"}})).modified_count
        rows = await _lines.backfill(dbx)
        touched = sum(t for _c, t, _n in rows)
        if n_knit or n_woven or touched:
            print(f"✅ FASE L (penutup) — {n_knit + n_woven} produk demo diberi lini "
                  f"(knit {n_knit} · woven {n_woven}) · {touched} dokumen distempel ulang")
    finally:
        client.close()


async def _finalize_qty_rolls(mongo_url: str) -> None:
    """FASE U — sapuan penutup DUA SATUAN: isi `qty_rolls` data demo.

    Memakai **satu implementasi bersama** `services/dual_qty_service.backfill()` —
    persis alat yang dipakai `scripts/migrate_qty_rolls.py` untuk basis data
    sungguhan. Bedanya hanya `demo_plan=True`: baris RENCANA data demo (PO/PR/SO/
    RFQ/antar-PT/permintaan internal) ikut diberi perkiraan jumlah roll dari panjang
    roll RATA-RATA NYATA produknya, supaya data demo tidak "hijau tapi hampa"
    (risiko 11 rencana MD ERP) dan layar dua satuan bisa dilihat apa adanya.
    Pada basis data sungguhan tebakan itu TIDAK dipakai.
    """
    client = AsyncIOMotorClient(mongo_url)
    dbx = client[os.environ["DB_NAME"]]
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
        from services import dual_qty_service as _dual        # noqa: PLC0415
        stat = await _dual.backfill(dbx, demo_plan=True)
        if stat:
            rinci = " · ".join(f"{k} {v}" for k, v in sorted(stat.items()))
            print(f"✅ FASE U (penutup) — dua satuan diisi: {rinci}")
    finally:
        client.close()


async def main():
    """Standalone CLI entry point — creates its own DB connection."""
    mongo_url = os.environ["MONGO_URL"]
    client = AsyncIOMotorClient(mongo_url)
    db_instance = client[os.environ["DB_NAME"]]
    summary = await seed_all(db_instance)
    client.close()
    _seed_e9_chain_demo()
    # ── FASE L — sapuan terakhir SESUDAH demo rantai E-9 (yang membuat produk &
    # dokumen sendiri lewat alur nyata). Produk yang lahir di langkah itu belum
    # bergolong lini; menyisakannya kosong sah secara sistem (tetap terlihat semua
    # akun), tetapi data demo yang setengah bergolong membuat chip lini tampak
    # "kehilangan" barang tanpa sebab saat pemilik memeriksanya. Aturan sapuan
    # sengaja DETERMINISTIK & sempit: knit → lini knit, sisanya lini woven.
    await _finalize_line_codes(mongo_url)
    await _finalize_qty_rolls(mongo_url)
    print("\n📋 Summary:")
    print(f"  - {summary['users']} Users (admin, sales, manager, warehouse×2)")
    print(f"  - {summary['products']} Products (Batik, Tenun, Lurik, Songket, Ulos, Jumputan, Endek)")
    print(f"  - {summary['customers']} Customers")
    print(f"  - {summary['warehouses']} Warehouses (Jakarta, Bandung, Surabaya)")
    print(f"  - {summary['purchase_orders']} Purchase Orders (PO-00001 → PO-00006)")
    print(f"  - {summary['sales_orders']} Sales Orders (SO-0001 → SO-0009)")
    print(f"  - {summary['inbound_tasks']} Inbound tasks · {summary['outbound_tasks']} Outbound tasks")
    print(f"  - {summary['inventory_balances']} inventory balances · {summary['inventory_movements']} movements")
    print(f"  - {summary['inventory_rolls']} inventory rolls (Roll-as-SSOT)")
    print(f"  - {summary['audit_logs']} audit logs")
    print(f"  - {summary.get('work_orders', 0)} Work Order produksi in-house (BOM + HPP)")


# ─────────────────────────────────────────────────────────────────────────────
# FASE P8 — BIAYA MASUK (LANDED COST) & PERMINTAAN PENAWARAN (RFQ)
# ─────────────────────────────────────────────────────────────────────────────
# KENAPA ADA: sejak FASE P7 kesembilan panel rincian dijadikan pop-up, tetapi DUA di
# antaranya — Biaya Masuk & Permintaan Penawaran — tidak punya satu baris pun data
# demo. Akibatnya keduanya hanya bisa dibuktikan lewat gate statik, tak pernah lewat
# klik nyata; pemilik pun tak bisa melihat fiturnya bekerja. Koleksi
# `landed_cost_vouchers` bahkan sudah lama ada di daftar "dibersihkan" tanpa pernah ada
# yang mengisinya, dan `rfqs` tidak ada di kedua daftar.
#
# Dokumen dibentuk lewat FUNGSI LAYANAN yang sama dengan router-nya
# (`landed_cost_service` / `rfq_service`), bukan disuntik mentah, supaya bentuk & angka
# tak bisa melenceng dari yang dihasilkan API — termasuk alokasi biaya per roll dan
# jurnal kapitalisasi saat voucher disetujui.

async def seed_landed_costs():
    """Voucher biaya masuk demo: 1 draf · 1 menunggu ACC · 1 sudah dialokasikan.

    Voucher yang `applied` dibentuk lewat jalur produksi (alokasi ke HPP roll +
    `gl_service.post_landed_cost`) supaya nilai persediaan di GL tetap seimbang.
    """
    from services.landed_cost_service import (
        next_voucher_number, total_cost_of, resolve_target_rolls, compute_allocation,
        apply_allocation_to_rolls,
    )
    from services import gl_service
    from core_utils import timeline_entry

    # PO yang ROLL-nya sudah diterima — hanya itu yang bisa dibebani biaya masuk.
    # Definisi "roll dari PO ini" diambil dari layanan yang sama dengan router
    # (`acquired.ref_id`), BUKAN dari field `po_id`: versi pertama seed ini memakai
    # `po_id` dan langsung tersaring habis (0 PO) walau rollnya jelas ada — persis
    # kelas "dua definisi untuk satu hal" yang dijaga gate lain.
    po_ids = [r for r in await db.inventory_rolls.distinct("acquired.ref_id")
              if isinstance(r, str) and r.startswith("po_")]
    pos = await db.purchase_orders.find(
        {"id": {"$in": po_ids}}, {"_id": 0, "id": 1, "po_number": 1, "entity_id": 1,
                                  "supplier_name": 1}).to_list(100)
    if not pos:
        print("  [warn] Landed cost demo dilewati: belum ada PO dengan roll diterima")
        return 0
    pos.sort(key=lambda p: p.get("po_number") or "")

    specs = [
        # (PO index, penyedia, no. invoice, baris biaya, basis, status akhir, catatan)
        (0, "PT Jalur Laut Ekspres", "JLE/2026/0771",
         [("freight", "Ongkos angkut Semarang → Gudang Jakarta", 4750000.0),
          ("handling", "Bongkar muat & tenaga angkut", 850000.0)],
         "value", "applied",
         "Sudah dialokasikan ke HPP roll — dipakai contoh pembacaan alokasi per roll."),
        (0, "Bea Cukai & Forwarder Tanjung Priok", "FWD-2026-1188",
         [("duty", "Bea masuk kain impor 5%", 6200000.0),
          ("insurance", "Asuransi pengangkutan (all risk)", 1150000.0)],
         "quantity", "pending_approval",
         "Menunggu persetujuan manager — akan mengubah HPP roll saat disetujui."),
        # Draf memakai PO KEDUA bila ada (supaya voucher tersebar), tetapi pada data
        # demo saat ini hanya PO-00001 yang rollnya sudah diterima saat seed berjalan
        # (rantai E-9 baru dibuat SESUDAH seed_all), jadi indeks ini jatuh ke PO yang sama.
        (1, "PT Trans Nusantara Kargo", "",
         [("freight", "Ongkos angkut antar-pulau (estimasi awal)", 2300000.0)],
         "value", "draft",
         "Masih draf: menunggu invoice resmi dari penyedia jasa."),
    ]

    made = 0
    for po_idx, provider, inv_no, lines, basis, target_status, notes in specs:
        po = pos[min(po_idx, len(pos) - 1)]
        entity_id = po.get("entity_id") or "ent_ksc"
        rolls = await resolve_target_rolls([po["id"]], entity_id)
        if not rolls:
            continue
        cost_lines = [{"category": c, "description": d, "amount": a} for c, d, a in lines]
        total_cost = total_cost_of(cost_lines)
        preview = compute_allocation(rolls, total_cost, basis)
        vnum = await next_voucher_number()
        voucher = {
            "id": new_id("lcv"), "voucher_number": vnum,
            "provider_name": provider, "supplier_invoice_no": inv_no,
            "po_ids": [po["id"]], "po_numbers": [po.get("po_number", "")],
            "entity_id": entity_id, "basis": basis, "effective_basis": preview["basis"],
            "cost_lines": cost_lines, "total_cost": total_cost,
            "voucher_date": ago(days=9 - made * 3), "due_date": ago(days=-21 + made * 5),
            "target_roll_count": preview["roll_count"],
            "allocation_preview": preview["allocations"], "allocations": [],
            "status": "draft", "approval_required": True,
            "required_approval_role": "manager", "approval_status": "not_required",
            "approved_by": "", "approved_at": "", "applied_at": "",
            "amount_paid": 0.0, "payment_status": "n/a", "payments": [],
            "notes": notes,
            "timeline": [timeline_entry("created", "Landed Cost Voucher dibuat", "Sri Wahyuni",
                                        f"{len(cost_lines)} biaya · {preview['roll_count']} roll "
                                        f"· basis {preview['basis']}")],
            "created_by": "Sri Wahyuni", "created_by_id": "user_finance",
            "created_at": ago(days=9 - made * 3), "updated_at": ago(days=9 - made * 3),
        }
        await db.landed_cost_vouchers.insert_one(voucher)

        if target_status in ("pending_approval", "applied"):
            await db.landed_cost_vouchers.update_one({"id": voucher["id"]}, {
                "$set": {"status": "pending_approval", "approval_status": "pending",
                         "updated_at": ago(days=8 - made * 3)},
                "$push": {"timeline": timeline_entry(
                    "submitted_for_approval", "Menunggu persetujuan manager", "Sri Wahyuni",
                    "landed cost akan mengubah HPP roll saat disetujui")}})

        if target_status == "applied":
            alloc = compute_allocation(rolls, total_cost, basis)
            n_rolls = await apply_allocation_to_rolls(vnum, alloc["allocations"])
            await db.landed_cost_vouchers.update_one({"id": voucher["id"]}, {
                "$set": {"status": "applied", "approval_status": "approved",
                         "approved_by": "Rudi Hartono", "approved_at": ago(days=7),
                         "applied_at": ago(days=7), "effective_basis": alloc["basis"],
                         "allocations": alloc["allocations"],
                         "target_roll_count": alloc["roll_count"],
                         "payment_status": "unpaid", "updated_at": ago(days=7)},
                "$push": {"timeline": timeline_entry(
                    "applied", "Disetujui & dialokasikan ke HPP roll", "Rudi Hartono",
                    f"{n_rolls} roll · basis {alloc['basis']}")}})
            applied = await db.landed_cost_vouchers.find_one({"id": voucher["id"]}, {"_id": 0})
            await gl_service.post_landed_cost(applied, amount=alloc["allocated_total"],
                                              label=vnum)
        made += 1

    print(f"✅ Landed cost vouchers seeded ({made}: 1 applied · 1 menunggu ACC · 1 draf)")
    return made


async def seed_rfqs():
    """RFQ demo: 1 draf · 1 terbuka dengan 3 penawaran masuk · 1 sudah dimenangkan.

    Penawaran diisi lewat bentuk yang sama dengan endpoint `/rfqs/{id}/quote` supaya
    layar Perbandingan (matriks item × supplier, harga terendah per baris, rekomendasi)
    benar-benar punya sesuatu untuk dibandingkan.
    """
    from services.rfq_service import (
        next_rfq_number, build_items_from_products, build_suppliers, supplier_total,
    )
    from core_utils import timeline_entry

    sups = await db.suppliers.find(
        {"$or": [{"partner_type": {"$in": [None, "", "external"]}},
                 {"partner_type": {"$exists": False}}]},
        {"_id": 0, "id": 1, "name": 1}).to_list(50)
    sups = [s for s in sups if not str(s.get("name", "")).startswith(("PT Kain", "CV Kanda"))]
    prods = await db.products.find({}, {"_id": 0, "id": 1, "sku": 1, "name": 1}).to_list(50)
    wh = await db.warehouses.find_one({"id": "wh_jakarta"}, {"_id": 0, "id": 1, "name": 1}) \
        or await db.warehouses.find_one({}, {"_id": 0, "id": 1, "name": 1})
    if len(sups) < 3 or len(prods) < 2 or not wh:
        print("  [warn] RFQ demo dilewati: supplier/produk/gudang demo belum lengkap")
        return 0

    made = 0
    # ── RFQ #1 — TERBUKA, 3 supplier sudah menawar (layar perbandingan berisi) ──
    items = await build_items_from_products([
        {"product_id": prods[0]["id"], "quantity": 500, "note": "Untuk pesanan seragam korporat"},
        {"product_id": prods[1]["id"], "quantity": 300, "note": "Grade A, warna seragam"},
    ])
    suppliers = await build_suppliers([s["id"] for s in sups[:3]])
    harga = [
        [(items[0]["line_id"], 148000.0, True), (items[1]["line_id"], 192000.0, True)],
        [(items[0]["line_id"], 152500.0, True), (items[1]["line_id"], 185000.0, True)],
        [(items[0]["line_id"], 145000.0, True), (items[1]["line_id"], 0.0, False)],
    ]
    lead = [12, 9, 18]
    for i, sup in enumerate(suppliers):
        sup["lines"] = [{"line_id": lid, "price": p, "available": av,
                         "note": "" if av else "Stok warna ini sedang kosong"}
                        for lid, p, av in harga[i]]
        sup["quote_status"] = "quoted"
        sup["quoted_at"] = ago(days=4 - i)
        sup["valid_until"] = ago(days=-25)
        sup["lead_time_days"] = lead[i]
    rfq_open = {
        "id": new_id("rfq"), "rfq_number": await next_rfq_number(),
        "title": "Pengadaan kain seragam korporat Q3",
        "entity_id": "ent_ksc", "source": "manual", "pr_id": "", "pr_number": "",
        "warehouse_id": wh["id"], "warehouse_name": wh.get("name", ""),
        "status": "open", "items": items, "suppliers": suppliers,
        "needed_by_date": ago(days=-30), "due_date": ago(days=-3),
        "notes": "Bandingkan harga & lead time sebelum memutuskan pemenang.",
        "award": {},
        "timeline": [
            timeline_entry("created", "RFQ dibuat", "Eko Prasetyo",
                           f"{len(items)} item · {len(suppliers)} supplier diundang"),
            timeline_entry("open", "RFQ dikirim ke supplier", "Eko Prasetyo",
                           f"{len(suppliers)} supplier"),
        ],
        "created_by": "Eko Prasetyo", "created_by_id": "user_purchasing",
        "created_at": ago(days=6), "updated_at": ago(days=1),
    }
    for sup in rfq_open["suppliers"]:
        sup["total"] = supplier_total(rfq_open, sup)
    await db.rfqs.insert_one(rfq_open)
    made += 1

    # ── RFQ #2 — DRAF (belum dikirim) ───────────────────────────────────────────
    items2 = await build_items_from_products(
        [{"product_id": prods[min(2, len(prods) - 1)]["id"], "quantity": 250,
          "note": "Contoh warna menyusul"}])
    rfq_draft = {
        "id": new_id("rfq"), "rfq_number": await next_rfq_number(),
        "title": "Pengadaan kain lurik untuk koleksi Lebaran",
        "entity_id": "ent_ksc", "source": "manual", "pr_id": "", "pr_number": "",
        "warehouse_id": wh["id"], "warehouse_name": wh.get("name", ""),
        "status": "draft", "items": items2,
        "suppliers": await build_suppliers([s["id"] for s in sups[:2]]),
        "needed_by_date": ago(days=-45), "due_date": ago(days=-10),
        "notes": "Menunggu kepastian kuantitas dari tim desain sebelum dikirim.",
        "award": {},
        "timeline": [timeline_entry("created", "RFQ dibuat", "Eko Prasetyo",
                                    f"{len(items2)} item · 2 supplier diundang")],
        "created_by": "Eko Prasetyo", "created_by_id": "user_purchasing",
        "created_at": ago(days=2), "updated_at": ago(days=2),
    }
    await db.rfqs.insert_one(rfq_draft)
    made += 1

    # ── RFQ #3 — SUDAH DIMENANGKAN (arsip keputusan) ────────────────────────────
    items3 = await build_items_from_products(
        [{"product_id": prods[0]["id"], "quantity": 200, "note": ""}])
    sup3 = await build_suppliers([s["id"] for s in sups[:2]])
    for i, sup in enumerate(sup3):
        sup["lines"] = [{"line_id": items3[0]["line_id"],
                         "price": 151000.0 + i * 6500, "available": True, "note": ""}]
        sup["quote_status"] = "quoted"
        sup["quoted_at"] = ago(days=20 - i)
        sup["valid_until"] = ago(days=-5)
        sup["lead_time_days"] = 10 + i * 4
    winner = sup3[0]
    rfq_awarded = {
        "id": new_id("rfq"), "rfq_number": await next_rfq_number(),
        "title": "Pengadaan batik untuk pesanan ritel Bandung",
        "entity_id": "ent_ksc", "source": "manual", "pr_id": "", "pr_number": "",
        "warehouse_id": wh["id"], "warehouse_name": wh.get("name", ""),
        "status": "awarded", "items": items3, "suppliers": sup3,
        "needed_by_date": ago(days=-8), "due_date": ago(days=14),
        "notes": "Pemenang dipilih dari harga terendah dengan lead time yang masih cukup.",
        "award": {"mode": "full", "supplier_id": winner["supplier_id"],
                  "supplier_name": winner["supplier_name"],
                  "decided_by": "Eko Prasetyo", "decided_at": ago(days=12),
                  "reason": "Harga terendah & lead time 10 hari (masih memenuhi kebutuhan)"},
        "timeline": [
            timeline_entry("created", "RFQ dibuat", "Eko Prasetyo", "1 item · 2 supplier diundang"),
            timeline_entry("open", "RFQ dikirim ke supplier", "Eko Prasetyo", "2 supplier"),
            timeline_entry("awarded", f"Dimenangkan {winner['supplier_name']}", "Eko Prasetyo",
                           "harga terendah · lead time 10 hari"),
        ],
        "created_by": "Eko Prasetyo", "created_by_id": "user_purchasing",
        "created_at": ago(days=22), "updated_at": ago(days=12),
    }
    for sup in rfq_awarded["suppliers"]:
        sup["total"] = supplier_total(rfq_awarded, sup)
    await db.rfqs.insert_one(rfq_awarded)
    made += 1

    print(f"✅ RFQ seeded ({made}: 1 terbuka dengan 3 penawaran · 1 draf · 1 dimenangkan)")
    return made

if __name__ == "__main__":
    asyncio.run(main())
