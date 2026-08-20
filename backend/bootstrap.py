"""Bootstrap seeders & backfills (idempotent) — dipanggil saat startup (lifespan).
Diekstrak dari server.py agar server.py tetap < 800 baris (KN compliance gate).
Semua fungsi aman dijalankan berulang (idempotent)."""
from db import db
from core_utils import hash_password, new_id, now_iso, next_doc_number, DEFAULT_ENTITY_ID, SESSION_TTL_HOURS
from permissions_config import DEFAULT_PERMISSIONS
from services.uom_service import UOM_SEED_ROWS


# ─── Seed helpers ────────────────────────────────────────────────────────────

async def seed_data() -> None:
    """Insert demo data only if collections are empty."""
    if await db.users.count_documents({}) == 0:
        await db.users.insert_many([
            {"id": "user_admin_01", "name": "Budi Santoso", "email": "admin@kainnusantara.id",
             "role": "admin", "password_hash": hash_password("demo12345"), "status": "active", "created_at": now_iso()},
            {"id": "user_sales_01", "name": "Ayu Marketing", "email": "sales@kainnusantara.id",
             "role": "sales", "password_hash": hash_password("demo12345"), "status": "active", "created_at": now_iso()},
            {"id": "user_manager_01", "name": "Dewi Manager", "email": "manager@kainnusantara.id",
             "role": "manager", "password_hash": hash_password("demo12345"), "status": "active", "created_at": now_iso()},
            {"id": "user_wh_01", "name": "Eko Warehouse", "email": "warehouse@kainnusantara.id",
             "role": "warehouse", "password_hash": hash_password("demo12345"), "status": "active", "created_at": now_iso()},
        ])

    if await db.uoms.count_documents({}) == 0:
        # FASE U — satu daftar benih (SSOT `services/uom_service.UOM_SEED_ROWS`).
        # Sebelum ini berkas ini menanam 6 baris sementara `seed_realistic` menanam 4
        # baris TANPA faktor, jadi jumlah baris master bergantung urutan restart vs
        # seed (K1). Sekarang dua-duanya membaca daftar yang sama.
        await db.uoms.insert_many([{**r, "status": "active", "created_at": now_iso()}
                                   for r in UOM_SEED_ROWS])

    if await db.warehouses.count_documents({}) == 0:
        await db.warehouses.insert_many([
            {
                "id": "wh_jakarta", "code": "WH-JKT", "name": "Gudang Jakarta Utara", "city": "Jakarta",
                "lat": -6.1751, "lng": 106.8650, "active": True, "created_at": now_iso(),
                "zones": [{"id": "zone_jkt_a", "name": "Zone A", "racks": [
                    {"id": "rack_jkt_a1", "name": "Rack A1", "bins": [
                        {"id": "bin_jkt_a1_01", "code": "A1-01", "capacity": 500},
                        {"id": "bin_jkt_a1_02", "code": "A1-02", "capacity": 500},
                    ]}
                ]}]
            },
            {
                "id": "wh_bandung", "code": "WH-BDG", "name": "Gudang Bandung Kopo", "city": "Bandung",
                "lat": -6.9175, "lng": 107.6191, "active": True, "created_at": now_iso(),
                "zones": [{"id": "zone_bdg_a", "name": "Zone A", "racks": [
                    {"id": "rack_bdg_a1", "name": "Rack A1", "bins": [
                        {"id": "bin_bdg_a1_01", "code": "A1-01", "capacity": 600},
                    ]}
                ]}]
            },
            {
                "id": "wh_surabaya", "code": "WH-SBY", "name": "Gudang Surabaya Rungkut", "city": "Surabaya",
                "lat": -7.2504, "lng": 112.7688, "active": True, "created_at": now_iso(),
                "zones": [{"id": "zone_sby_a", "name": "Zone A", "racks": [
                    {"id": "rack_sby_a1", "name": "Rack A1", "bins": [
                        {"id": "bin_sby_a1_01", "code": "A1-01", "capacity": 400},
                    ]}
                ]}]
            },
        ])

    if await db.products.count_documents({}) == 0:
        _seed_products = [
            {
                "id": "prod_batik_mega", "sku": "BTK-MEGA-001",
                "name": "Batik Mega Mendung Premium", "category": "Batik", "variant": "Premium",
                "color": "Biru-Merah", "motif": "Mega Mendung", "grade": "A",
                "supplier": "Cirebon Craft", "base_unit": "yard", "price": 185000,
                "image": "https://images.unsplash.com/photo-1582142839970-2b9e04b60f65?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85",
                "status": "active", "uom_conversions": [], "batch_lot_rolls": [], "created_at": now_iso(), "updated_at": now_iso()
            },
            {
                "id": "prod_tenun_ikat", "sku": "TNI-GRGD-001",
                "name": "Tenun Ikat Garuda Premium", "category": "Tenun", "variant": "Premium",
                "color": "Emas-Coklat", "motif": "Garuda", "grade": "A",
                "supplier": "NTT Weaving Co", "base_unit": "yard", "price": 225000,
                "image": "https://images.unsplash.com/photo-1613771404784-3a5686aa2be3?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85",
                "status": "active", "uom_conversions": [], "batch_lot_rolls": [], "created_at": now_iso(), "updated_at": now_iso()
            },
            {
                "id": "prod_lurik_classic", "sku": "LRK-CLSC-001",
                "name": "Lurik Klasik Solo", "category": "Lurik", "variant": "Klasik",
                "color": "Hitam-Putih", "motif": "Garis Vertikal", "grade": "A",
                "supplier": "Solo Weave", "base_unit": "yard", "price": 95000,
                "image": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85",
                "status": "active", "uom_conversions": [], "batch_lot_rolls": [], "created_at": now_iso(), "updated_at": now_iso()
            },
            {
                "id": "prod_songket_palembang", "sku": "SGK-PLB-001",
                "name": "Songket Palembang Benang Emas", "category": "Songket", "variant": "Premium",
                "color": "Merah-Emas", "motif": "Bunga Cengkeh", "grade": "A+",
                "supplier": "Palembang Silk House", "base_unit": "yard", "price": 450000,
                "image": "https://images.unsplash.com/photo-1619855544858-e8e275c3b31a?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85",
                "status": "active", "uom_conversions": [], "batch_lot_rolls": [], "created_at": now_iso(), "updated_at": now_iso()
            },
            {
                "id": "prod_ulos_batak", "sku": "ULS-BTK-001",
                "name": "Ulos Batak Ragidup", "category": "Ulos", "variant": "Tradisional",
                "color": "Merah-Hitam-Putih", "motif": "Ragidup", "grade": "A",
                "supplier": "Toba Craft", "base_unit": "yard", "price": 320000,
                "image": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85",
                "status": "active", "uom_conversions": [], "batch_lot_rolls": [], "created_at": now_iso(), "updated_at": now_iso()
            },
        ]
        # Fase A (PS-01/02/03 · D-02/D-20/D-22) — seed WAJIB patuh domain tekstil:
        # stage & fabric_type terisi, grade nilai enum, kelengkapan GSM/lebar terpenuhi.
        await db.products.insert_many(_stamp_domain_defaults(_seed_products))

    if await db.inventory_balances.count_documents({}) == 0:
        await db.inventory_balances.insert_many([
            {"id": new_id("bal"), "product_id": "prod_batik_mega", "warehouse_id": "wh_jakarta",
             "on_hand_qty": 350, "reserved_qty": 0, "available_qty": 350, "blocked_qty": 0, "picked_qty": 0, "in_transit_qty": 0, "updated_at": now_iso()},
            {"id": new_id("bal"), "product_id": "prod_batik_mega", "warehouse_id": "wh_bandung",
             "on_hand_qty": 200, "reserved_qty": 0, "available_qty": 200, "blocked_qty": 0, "picked_qty": 0, "in_transit_qty": 0, "updated_at": now_iso()},
            {"id": new_id("bal"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_jakarta",
             "on_hand_qty": 150, "reserved_qty": 0, "available_qty": 150, "blocked_qty": 0, "picked_qty": 0, "in_transit_qty": 0, "updated_at": now_iso()},
            {"id": new_id("bal"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_surabaya",
             "on_hand_qty": 120, "reserved_qty": 0, "available_qty": 120, "blocked_qty": 0, "picked_qty": 0, "in_transit_qty": 0, "updated_at": now_iso()},
            {"id": new_id("bal"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_bandung",
             "on_hand_qty": 500, "reserved_qty": 0, "available_qty": 500, "blocked_qty": 0, "picked_qty": 0, "in_transit_qty": 0, "updated_at": now_iso()},
            {"id": new_id("bal"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_surabaya",
             "on_hand_qty": 300, "reserved_qty": 0, "available_qty": 300, "blocked_qty": 0, "picked_qty": 0, "in_transit_qty": 0, "updated_at": now_iso()},
            {"id": new_id("bal"), "product_id": "prod_songket_palembang", "warehouse_id": "wh_jakarta",
             "on_hand_qty": 80, "reserved_qty": 0, "available_qty": 80, "blocked_qty": 0, "picked_qty": 0, "in_transit_qty": 0, "updated_at": now_iso()},
            {"id": new_id("bal"), "product_id": "prod_ulos_batak", "warehouse_id": "wh_surabaya",
             "on_hand_qty": 60, "reserved_qty": 0, "available_qty": 60, "blocked_qty": 0, "picked_qty": 0, "in_transit_qty": 0, "updated_at": now_iso()},
        ])
        # Also seed initial movement records
        import asyncio
        movements = [
            {"id": new_id("mov"), "product_id": "prod_batik_mega", "warehouse_id": "wh_jakarta",
             "movement_type": "initial_stock", "quantity": 350, "unit": "yard",
             "batch": "BTK-2024-001", "lot": "LOT-001", "roll_id": "ROLL-001",
             "source_document": "seed", "timestamp": now_iso()},
            {"id": new_id("mov"), "product_id": "prod_batik_mega", "warehouse_id": "wh_bandung",
             "movement_type": "initial_stock", "quantity": 200, "unit": "yard",
             "batch": "BTK-2024-001", "lot": "LOT-001", "roll_id": "ROLL-002",
             "source_document": "seed", "timestamp": now_iso()},
            {"id": new_id("mov"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_jakarta",
             "movement_type": "initial_stock", "quantity": 150, "unit": "yard",
             "batch": "TNI-2024-001", "lot": "LOT-001", "roll_id": "ROLL-003",
             "source_document": "seed", "timestamp": now_iso()},
            {"id": new_id("mov"), "product_id": "prod_tenun_ikat", "warehouse_id": "wh_surabaya",
             "movement_type": "initial_stock", "quantity": 120, "unit": "yard",
             "batch": "TNI-2024-001", "lot": "LOT-002", "roll_id": "ROLL-004",
             "source_document": "seed", "timestamp": now_iso()},
            {"id": new_id("mov"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_bandung",
             "movement_type": "initial_stock", "quantity": 500, "unit": "yard",
             "batch": "LRK-2024-001", "lot": "LOT-001", "roll_id": "ROLL-005",
             "source_document": "seed", "timestamp": now_iso()},
            {"id": new_id("mov"), "product_id": "prod_lurik_classic", "warehouse_id": "wh_surabaya",
             "movement_type": "initial_stock", "quantity": 300, "unit": "yard",
             "batch": "LRK-2024-001", "lot": "LOT-002", "roll_id": "ROLL-006",
             "source_document": "seed", "timestamp": now_iso()},
            {"id": new_id("mov"), "product_id": "prod_songket_palembang", "warehouse_id": "wh_jakarta",
             "movement_type": "initial_stock", "quantity": 80, "unit": "yard",
             "batch": "SGK-2024-001", "lot": "LOT-001", "roll_id": "ROLL-007",
             "source_document": "seed", "timestamp": now_iso()},
            {"id": new_id("mov"), "product_id": "prod_ulos_batak", "warehouse_id": "wh_surabaya",
             "movement_type": "initial_stock", "quantity": 60, "unit": "yard",
             "batch": "ULS-2024-001", "lot": "LOT-001", "roll_id": "ROLL-008",
             "source_document": "seed", "timestamp": now_iso()},
        ]
        await db.inventory_movements.insert_many(movements)

    if await db.customers.count_documents({}) == 0:
        await db.customers.insert_many([
            {
                "id": "cust_toko_kain", "code": "CUST-0001", "name": "Toko Kain Sejahtera",
                "pic_name": "Pak Hendra", "phone": "081234567890", "email": "hendra@tokokain.id",
                "type": "Retailer", "city": "Jakarta", "status": "active", "created_by": "seed", "created_at": now_iso(),
                "addresses": [{"id": "addr_001", "label": "Toko Utama", "recipient_name": "Pak Hendra",
                               "phone": "081234567890", "city": "Jakarta",
                               "address": "Jl. Mangga Besar Raya No. 45", "is_primary": True}]
            },
            {
                "id": "cust_butik_bali", "code": "CUST-0002", "name": "Butik Bali Indah",
                "pic_name": "Ibu Komang", "phone": "082345678901", "email": "komang@butikbali.id",
                "type": "Boutique", "city": "Denpasar", "status": "active", "created_by": "seed", "created_at": now_iso(),
                "addresses": [{"id": "addr_002", "label": "Butik Seminyak", "recipient_name": "Ibu Komang",
                               "phone": "082345678901", "city": "Denpasar",
                               "address": "Jl. Seminyak No. 88", "is_primary": True}]
            },
            {
                "id": "cust_moda_surabaya", "code": "CUST-0003", "name": "Moda Surabaya Fashion",
                "pic_name": "Bapak Andi", "phone": "083456789012", "email": "andi@modasby.id",
                "type": "Wholesaler", "city": "Surabaya", "status": "active", "created_by": "seed", "created_at": now_iso(),
                "addresses": [{"id": "addr_003", "label": "Gudang Pusat", "recipient_name": "Bapak Andi",
                               "phone": "083456789012", "city": "Surabaya",
                               "address": "Jl. Rungkut Industri No. 22", "is_primary": True}]
            },
        ])

    if await db.document_templates.count_documents({}) == 0:
        await db.document_templates.insert_many([
            {
                "id": "tmpl_sj_default", "document_type": "surat_jalan", "name": "Template SJ Standard",
                "header": "KAIN NUSANTARA — Enterprise Textile Warehouse",
                "footer": "Barang diterima dalam kondisi baik. Tanda tangan sebagai bukti penerimaan.",
                "columns": ["sku", "name", "qty", "unit", "batch", "lot"],
                "logo_url": "", "paper_size": "A4", "orientation": "portrait", "margin_mm": 12,
                "signature_left": "Disiapkan Oleh", "signature_right": "Diterima Oleh",
                "section_order": ["header", "customer", "items", "allocation", "signature", "footer"],
                "status": "active", "created_by": "seed", "created_at": now_iso()
            },
            {
                "id": "tmpl_inv_default", "document_type": "invoice", "name": "Template Invoice Standard",
                "header": "KAIN NUSANTARA — Invoice",
                "footer": "Pembayaran dalam 30 hari. Terima kasih atas kepercayaan Anda.",
                "columns": ["sku", "name", "qty", "unit", "price", "subtotal"],
                "logo_url": "", "paper_size": "A4", "orientation": "portrait", "margin_mm": 12,
                "signature_left": "Dibuat Oleh", "signature_right": "Disetujui Oleh",
                "section_order": ["header", "customer", "items", "signature", "footer"],
                "status": "active", "created_by": "seed", "created_at": now_iso()
            },
        ])

    if await db.permission_settings.count_documents({}) == 0:
        await db.permission_settings.insert_one(
            {"id": "default", "matrix": DEFAULT_PERMISSIONS, "updated_at": now_iso()}
        )


# ─── Fase 0: Multi-Entity + Notification Center ──────────────────────────────

PRIMARY_ENTITY_ID = "ent_ksc"
ENTITY_SCOPED_COLLECTIONS = ["sales_orders", "invoices", "purchase_orders", "customers"]


async def seed_entities() -> None:
    """Seed entitas legal grup Kain Nusantara (idempotent)."""
    if await db.business_entities.count_documents({}) == 0:
        await db.business_entities.insert_many([
            {"id": "ent_ksc", "legal_name": "PT Kain Suka Cita", "short_name": "KSC",
             "type": "PT", "npwp": "01.234.567.8-901.000",
             "address": "Jl. Soekarno Hatta No. 100", "city": "Bandung",
             "default_tax_mode": "ppn", "doc_prefix": "KSC", "logo_url": "",
             "currency": "IDR", "parent_entity_id": "", "is_group": False,
             "coa_template": "id_standard", "fiscal_year_start": "01-01",
             "incentive_payer": "sales_entity", "numbering_scheme": "per_entity_prefix",
             "status": "active", "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso()},
            {"id": "ent_kanda", "legal_name": "CV Kanda Suka", "short_name": "Kanda",
             "type": "CV", "npwp": "02.345.678.9-012.000",
             "address": "Jl. Mangga Dua Raya No. 22", "city": "Jakarta",
             "default_tax_mode": "non_ppn", "doc_prefix": "KANDA", "logo_url": "",
             "currency": "IDR", "parent_entity_id": "", "is_group": False,
             "coa_template": "id_standard", "fiscal_year_start": "01-01",
             "incentive_payer": "sales_entity", "numbering_scheme": "per_entity_prefix",
             "status": "active", "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso()},
        ])


async def backfill_entity_id() -> None:
    """Pastikan semua data transaksi lama punya entity_id (default entitas utama)."""
    for col in ENTITY_SCOPED_COLLECTIONS:
        await db[col].update_many({"entity_id": {"$exists": False}}, {"$set": {"entity_id": PRIMARY_ENTITY_ID}})
        await db[col].update_many({"entity_id": None}, {"$set": {"entity_id": PRIMARY_ENTITY_ID}})


async def sync_permission_modules() -> None:
    """Merge MODUL & AKSI permission baru dari DEFAULT_PERMISSIONS ke matrix
    tersimpan, non-destruktif (hanya MENAMBAH; pencabutan ditangani
    `sync_permission_revocations` yang berjalan setelah ini).

    Catatan (iter_55 RCA): versi lama hanya menambah MODUL baru, sehingga AKSI
    baru pada modul yang SUDAH ADA (mis. `inventory.update`) tidak ikut → matrix
    bisa STALE & RBAC menolak aksi yang sah (warehouse/manager gagal hold/WIP).
    Kini aksi default yang hilang ikut di-merge agar fitur jalan di DB mana pun
    (tanpa perlu re-seed)."""
    record = await db.permission_settings.find_one({"id": "default"})
    if not record:
        return
    matrix = record.get("matrix", {})
    changed = False
    for role, modules in DEFAULT_PERMISSIONS.items():
        matrix.setdefault(role, {})
        for module, actions in modules.items():
            if module not in matrix[role]:
                matrix[role][module] = list(actions)
                changed = True
            else:
                existing = matrix[role][module]
                if isinstance(existing, list):
                    missing = [a for a in actions if a not in existing]
                    if missing:
                        matrix[role][module] = existing + missing
                        changed = True
    if changed:
        await db.permission_settings.update_one(
            {"id": "default"}, {"$set": {"matrix": matrix, "updated_at": now_iso()}}
        )


async def sync_permission_revocations() -> None:
    """EPIC 1 — cabut modul biaya/back-office dari role 'sales' & re-scope (idempotent).

    FASE E-8 (E8.2) — ikut menegakkan PEMISAHAN TUGAS. Penting: matriks izin TERSIMPAN
    di basis data (`permission_settings`), jadi mengubah `DEFAULT_PERMISSIONS` saja
    TIDAK mencabut apa pun di instalasi yang sudah jalan — `sync_permission_modules`
    hanya MENAMBAH yang kurang, tidak pernah mengurangi. Tanpa blok di bawah, sales
    akan tetap bisa menerbitkan faktur pajak & mencatat uang masuk selamanya.
    """
    REVOKE = {
        "sales": ["purchase_order", "purchase_requisition", "vendor_bill",
                  "landed_cost", "input_tax", "rfq"],
    }
    RESCOPE = {
        "sales": {
            "price_approval": ["view", "create", "update"],  # hapus 'delete'
            # E8.2 — uang masuk & pajak keluaran pindah ke peran `finance`;
            # keputusan selisih bayar juga. Sales tetap boleh MELIHAT.
            "tax_invoice": ["view"],
            "ar_receipt": ["view"],
            "payment_variance": ["view"],
            "payment_plan": ["view"],
        },
        # E8.10b#3 — menandai pesanan TERKIRIM: boleh gudang MAUPUN Admin Sales.
        "warehouse": {"order": ["view", "deliver"]},
        # FASE F-6 (2026-08-17) — `approval.approve` DICABUT untuk admin & manajer.
        # Satu-satunya endpoint yang memeriksanya (`POST /approval-requests/{id}/
        # approve|reject`) dipensiunkan bersama mesin persetujuan generik yang tak pernah
        # punya produsen (`create_approval_request()` nol pemanggil). Tanpa blok ini izin
        # itu HIDUP TERUS di instalasi yang sudah jalan — kelas cacat yang sama dengan
        # E8.2 di atas: matriks tersimpan di basis data, mengubah `DEFAULT_PERMISSIONS`
        # saja tidak mencabut apa pun. Membaca antrean (`approval.view`) tetap ada:
        # yang dicabut hanya wewenang memutuskan lewat pintu yang sudah tidak ada.
        "admin": {"approval": ["view"]},
        "manager": {"approval": ["view"]},
    }
    record = await db.permission_settings.find_one({"id": "default"})
    if not record:
        return
    matrix = record.get("matrix", {})
    changed = False
    for role, mods in REVOKE.items():
        rm = matrix.get(role, {})
        for m in mods:
            if m in rm:
                del rm[m]
                changed = True
    for role, mp in RESCOPE.items():
        rm = matrix.get(role, {})
        for m, actions in mp.items():
            if m in rm and rm[m] != actions:
                rm[m] = actions
                changed = True
    if changed:
        await db.permission_settings.update_one(
            {"id": "default"}, {"$set": {"matrix": matrix, "updated_at": now_iso()}}
        )


async def sync_uom_factors() -> None:
    """Selaraskan master satuan dengan daftar benih (idempotent) — FASE U.

    Dulu fungsi ini hanya menambal `factor_to_base` untuk satuan panjang dan
    menyisipkan `CM`/`INCH` bila hilang. Sekarang ia menjadi **satu jalur
    penyelarasan** untuk seluruh `UOM_SEED_ROWS`:
      * baris benih yang belum ada → dibuat (mis. `KG`, `PANEL`);
      * `aliases` yang belum ada → ditambahkan (inilah yang menyambungkan kata
        satuan di dokumen — `yard`, `kg`, `meter` — ke baris master `YRD`/`KG`/`MTR`);
      * `factor_to_base` yang hilang → diisi fisika benih;
      * `RLL` yang masih ber-`base_type="volume"` → dirapikan ke `count`
        (roll adalah HITUNGAN; `volume` tak dipakai mesin konversi mana pun).
    Nilai yang SUDAH diisi pemilik TIDAK ditimpa (master menang atas benih) —
    kecuali `base_type` `RLL` yang memang salah sejak awal.
    """
    for row in UOM_SEED_ROWS:
        code = row["code"]
        cur = await db.uoms.find_one({"code": code}, {"_id": 0})
        if not cur:
            await db.uoms.insert_one({**row, "status": "active", "created_at": now_iso()})
            continue
        patch: dict = {}
        if not cur.get("aliases"):
            patch["aliases"] = row.get("aliases", [])
        if cur.get("factor_to_base") in (None, 0):
            patch["factor_to_base"] = row.get("factor_to_base", 1.0)
        if code == "RLL" and cur.get("base_type") == "volume":
            patch["base_type"] = "count"
        if row.get("factor_per_document") and not cur.get("factor_per_document"):
            patch["factor_per_document"] = True
        if patch:
            patch["updated_at"] = now_iso()
            await db.uoms.update_one({"code": code}, {"$set": patch})


async def sync_product_uom_examples() -> None:
    """Sub-fase 1.13 — contoh konversi VARIABLE + catch-weight per produk (idempotent, demo)."""
    await db.products.update_one(
        {"id": "prod_batik_mega", "$or": [{"uom_conversions": {"$exists": False}}, {"uom_conversions": []}]},
        {"$set": {"uom_conversions": [{"from_unit": "roll", "to_unit": "yard", "factor": 50}],
                  "updated_at": now_iso()}},
    )
    # Contoh catch-weight: gramasi & lebar agar unit "kg" tersedia (kg/m = 200×1.5/1000 = 0.3).
    await db.products.update_one(
        {"id": "prod_batik_mega", "$or": [{"gramasi": {"$in": [None, 0]}}, {"lebar": {"$in": [None, 0]}}]},
        {"$set": {"gramasi": 200, "lebar": 1.5, "updated_at": now_iso()}},
    )


async def seed_initial_notifications() -> None:
    """Generate notifikasi awal dari kondisi REAL (stok menipis / reservasi)."""
    if await db.notifications.count_documents({}) == 0:
        from services.notification_service import generate_system_notifications
        await generate_system_notifications()


# ─── Fase 0.5: Roll-as-SSOT Inventory Ownership ─────────────────────────────

async def backfill_inventory_owner() -> None:
    """Pastikan balances & movements lama punya owner_entity_id (default entitas utama)."""
    await db.inventory_balances.update_many(
        {"owner_entity_id": {"$exists": False}}, {"$set": {"owner_entity_id": PRIMARY_ENTITY_ID}}
    )
    await db.inventory_balances.update_many(
        {"owner_entity_id": None}, {"$set": {"owner_entity_id": PRIMARY_ENTITY_ID}}
    )
    await db.inventory_movements.update_many(
        {"owner_entity_id": {"$exists": False}}, {"$set": {"owner_entity_id": PRIMARY_ENTITY_ID}}
    )


async def backfill_roll_dye_lot() -> None:
    """P0-4 — pastikan roll lama punya `dye_lot` (default = `lot`), `grade` (default A),
    dan `defects` (default []). Invarian roll lama tetap valid (lot tetap terisi)."""
    await db.inventory_rolls.update_many(
        {"dye_lot": {"$exists": False}}, [{"$set": {"dye_lot": "$lot"}}]
    )
    await db.inventory_rolls.update_many(
        {"$or": [{"dye_lot": None}, {"dye_lot": ""}]}, [{"$set": {"dye_lot": "$lot"}}]
    )
    await db.inventory_rolls.update_many(
        {"grade": {"$exists": False}}, {"$set": {"grade": "A"}}
    )
    await db.inventory_rolls.update_many(
        {"defects": {"$exists": False}}, {"$set": {"defects": []}}
    )
    # P0-5 — default field landed cost untuk roll lama (HPP additive)
    await db.inventory_rolls.update_many(
        {"landed_cost_total": {"$exists": False}}, {"$set": {"landed_cost_total": 0.0}}
    )
    await db.inventory_rolls.update_many(
        {"landed_cost_refs": {"$exists": False}}, {"$set": {"landed_cost_refs": []}}
    )
    await db.inventory_rolls.update_many(
        {"base_unit_cost": {"$exists": False}}, [{"$set": {"base_unit_cost": "$unit_cost"}}]
    )
    # P0-3 — default field Faktur Pajak Masukan untuk vendor_bills lama
    await db.vendor_bills.update_many(
        {"input_faktur_status": {"$exists": False}}, {"$set": {"input_faktur_status": "none"}}
    )


async def ensure_inventory_rolls() -> None:
    """Generate inventory_rolls sintetis dari balances (idempotent — KN_15 §11)."""
    from services.roll_service import generate_rolls_from_balances
    await generate_rolls_from_balances(created_by="seed")


async def ensure_config_defaults() -> None:
    """Seed pengaturan default (settings/payment_terms/approval_rules) — Fase 1A, idempotent."""
    from services.config_service import seed_config_defaults
    await seed_config_defaults()


# ─── EPIC2: Master Kategori Produk + Snapshot SO ─────────────────────────────

CATEGORY_BASE_UNIT = {
    "Batik": "yard", "Tenun": "yard", "Lurik": "yard", "Songket": "yard",
    "Ulos": "yard", "Jumputan": "yard", "Endek": "yard",
}


async def seed_product_categories() -> None:
    """Master kategori produk (EPIC2) — idempotent.

    Bila koleksi kosong, derivasi dari kategori distinct yang sudah dipakai produk
    (free-text historis), plus daftar baku 7 kategori kain Nusantara. base_unit
    diambil dari produk perwakilan; sort_order mengikuti urutan stabil.
    """
    if await db.product_categories.count_documents({}) > 0:
        return
    distinct = [c for c in await db.products.distinct("category") if c]
    names = sorted(set(distinct) | set(CATEGORY_BASE_UNIT.keys()))
    docs = []
    for idx, name in enumerate(names):
        rep = await db.products.find_one({"category": name}, {"_id": 0, "base_unit": 1})
        base_unit = (rep or {}).get("base_unit") or CATEGORY_BASE_UNIT.get(name, "yard")
        docs.append({
            "id": new_id("cat"),
            "code": name.upper()[:24],
            "name": name,
            "base_unit": base_unit,
            "description": f"Kategori kain {name}",
            "sort_order": idx,
            "status": "active",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
    if docs:
        await db.product_categories.insert_many(docs)


async def backfill_so_line_category() -> None:
    """Backfill snapshot kategori (+base_unit/base_quantity) ke SO line — idempotent.

    Order historis (mis. hasil seed) belum punya `category` per item. Isi dari
    produk terkait. Hanya menyentuh order yang punya minimal satu line tanpa
    `category` agar aman dijalankan berulang.
    """
    products = {p["id"]: p for p in await db.products.find(
        {}, {"_id": 0, "id": 1, "category": 1, "base_unit": 1}).to_list(2000)}
    cursor = db.sales_orders.find(
        {"items.category": {"$exists": False}}, {"_id": 0, "id": 1, "items": 1})
    async for order in cursor:
        items = order.get("items") or []
        changed = False
        for it in items:
            if "category" in it:
                continue
            prod = products.get(it.get("product_id"), {})
            it["category"] = prod.get("category", "")
            it.setdefault("base_unit", prod.get("base_unit", "yard"))
            it.setdefault("base_quantity", float(it.get("quantity", 0) or 0))
            changed = True
        if changed:
            await db.sales_orders.update_one({"id": order["id"]}, {"$set": {"items": items}})


# Rasio HPP per kategori (proxy biaya bila harga_pokok belum diisi). Margin realistis.
_HPP_RATIO = {"Batik": 0.66, "Tenun": 0.70, "Lurik": 0.62, "Songket": 0.72,
              "Ulos": 0.68, "Jumputan": 0.60, "Endek": 0.69}


async def backfill_costing_data() -> None:
    """EPIC3A — pastikan ada data cost untuk WAC (idempotent).

    1) products.harga_pokok kosong → isi = price × rasio kategori (proxy HPP).
    2) inventory_rolls.base_unit_cost kosong → isi dari products.harga_pokok;
       unit_cost = base_unit_cost + landed_cost_total (default 0).
    Hanya menyentuh dokumen yang field-nya belum terisi.
    """
    prods = await db.products.find({}, {"_id": 0}).to_list(2000)
    pmap = {}
    for p in prods:
        hpp = float(p.get("harga_pokok") or 0)
        if hpp <= 0:
            ratio = _HPP_RATIO.get(p.get("category"), 0.66)
            hpp = round(float(p.get("price", 0) or 0) * ratio, -2)  # bulat ratusan
            if hpp > 0:
                await db.products.update_one({"id": p["id"]}, {"$set": {"harga_pokok": hpp}})
        pmap[p["id"]] = hpp

    cursor = db.inventory_rolls.find(
        {"$or": [{"base_unit_cost": {"$in": [None, 0]}}, {"base_unit_cost": {"$exists": False}}]},
        {"_id": 0, "id": 1, "product_id": 1, "landed_cost_total": 1})
    async for r in cursor:
        base = round(pmap.get(r.get("product_id"), 0.0), 4)
        if base <= 0:
            continue
        landed = float(r.get("landed_cost_total") or 0)
        await db.inventory_rolls.update_one(
            {"id": r["id"]},
            {"$set": {"base_unit_cost": base, "unit_cost": round(base + landed, 4)}})


# Rate insentif default per kategori (Rp per meter) — EPIC4.
_INCENTIVE_DEFAULT = {"Batik": 3000, "Tenun": 3500, "Lurik": 2000, "Songket": 6000,
                      "Ulos": 4500, "Jumputan": 2500, "Endek": 4000}


async def backfill_so_line_cost() -> None:
    """P2-3 — snapshot `unit_cost` (cost-at-sale) ke SO line yang belum punya. Idempotent.

    Cost-at-sale membuat margin insentif STABIL walau WAC/stok berubah kemudian.
    Prioritas: WAC saat ini (per entitas) → products.harga_pokok.
    """
    from services import costing_service
    products = {p["id"]: p for p in await db.products.find({}, {"_id": 0}).to_list(2000)}
    cost_cache: dict = {}
    cursor = db.sales_orders.find(
        {"items.unit_cost": {"$exists": False}}, {"_id": 0, "id": 1, "items": 1, "entity_id": 1})
    async for order in cursor:
        items = order.get("items") or []
        ent = order.get("entity_id")
        changed = False
        for it in items:
            if "unit_cost" in it:
                continue
            pid = it.get("product_id")
            key = (pid, ent)
            if key not in cost_cache:
                try:
                    w = await costing_service.wac_for_product(pid, entity_id=ent, product=products.get(pid))
                    c = float(w.get("wac") or 0)
                except Exception:
                    c = 0.0
                if c <= 0:
                    c = float((products.get(pid) or {}).get("harga_pokok") or 0)
                cost_cache[key] = round(c, 2)
            it["unit_cost"] = cost_cache[key]
            changed = True
        if changed:
            await db.sales_orders.update_one({"id": order["id"]}, {"$set": {"items": items}})


async def backfill_ar_cash_postings() -> None:
    """P0-1 — pastikan tiap AR receipt (posted, kas baru>0) punya cash_transaction in.

    Idempotent: lewati bila sudah ada cash_transaction ref_type=ar_receipt utk receipt.
    Routing: tunai→kas_kecil(entitas), transfer/giro/qris→kas_besar(bank gabungan).
    """
    from services.ar_receipt_service import _cash_routing
    receipts = await db.ar_receipts.find(
        {"status": {"$ne": "void"}}, {"_id": 0}).to_list(5000)
    for r in receipts:
        amt = round(float(r.get("amount", 0) or 0), 2)
        if amt <= 0.01:
            continue
        exists = await db.cash_transactions.count_documents(
            {"ref_type": "ar_receipt", "ref_id": r["id"], "status": {"$ne": "void"}})
        if exists:
            continue
        cash_type, force_all = _cash_routing(r.get("method", ""))
        # FASE E-7 (E7.4) — backfill ikut aturan baru: kas selalu milik satu badan usaha.
        entity_id = r.get("entity_id") or DEFAULT_ENTITY_ID
        if entity_id in ("all", "", None):
            entity_id = DEFAULT_ENTITY_ID
        # FASE E-1 (E1.7) — nomor kas per badan usaha (kas grup "all" tetap deret bersama).
        number = await next_doc_number("cash_transactions", "number", "CASH-",
                                       entity_id=(None if entity_id == "all" else entity_id))
        await db.cash_transactions.insert_one({
            "id": new_id("cash"), "number": number, "cash_type": cash_type,
            "direction": "in", "amount": amt, "category": "penagihan",
            "description": f"Penerimaan {r.get('number')} — {r.get('customer_name', '')}",
            "entity_id": entity_id, "ref_type": "ar_receipt", "ref_id": r["id"],
            "txn_date": r.get("receipt_date") or now_iso(), "status": "posted",
            "created_by": "system-backfill", "created_at": now_iso(), "updated_at": now_iso(),
        })


async def backfill_epic6_pr_po_links() -> None:
    """EPIC6 — link PR→PO (`purchase_requisitions.po_id`) untuk PR yang belum ter-link.

    Idempotent + KONSERVATIF: cocokkan PR↔PO pada (entity_id, supplier, warehouse) DAN
    overlap product_id; pilih PO dgn overlap terbaik yang BELUM diklaim PR lain (1:1).
    Hanya set po_id/po_number (tidak mengubah status PR) agar tanpa efek samping.
    Memungkinkan rantai PR→PO→GRN tampil di Document Hub (EPIC6).
    """
    claimed = set()
    async for pr in db.purchase_requisitions.find({"po_id": {"$nin": ["", None]}}, {"_id": 0, "po_id": 1}):
        if pr.get("po_id"):
            claimed.add(pr["po_id"])
    pos = await db.purchase_orders.find({}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    unlinked = await db.purchase_requisitions.find(
        {"$or": [{"po_id": {"$in": ["", None]}}, {"po_id": {"$exists": False}}]}, {"_id": 0}
    ).to_list(2000)
    for pr in unlinked:
        pr_prods = {i.get("product_id") for i in pr.get("items", []) if i.get("product_id")}
        sup = pr.get("preferred_supplier_id")
        best, best_overlap = None, 0
        for po in pos:
            if po["id"] in claimed:
                continue
            if po.get("entity_id") != pr.get("entity_id"):
                continue
            if sup and po.get("supplier_id") != sup:
                continue
            if po.get("warehouse_id") != pr.get("warehouse_id"):
                continue
            po_prods = {i.get("product_id") for i in po.get("items", []) if i.get("product_id")}
            overlap = len(pr_prods & po_prods)
            if overlap > best_overlap:
                best_overlap, best = overlap, po
        if best and best_overlap > 0:
            await db.purchase_requisitions.update_one(
                {"id": pr["id"]},
                {"$set": {"po_id": best["id"], "po_number": best.get("po_number"), "updated_at": now_iso()}},
            )
            claimed.add(best["id"])



async def seed_incentive_rates() -> None:
    """EPIC4 — rate insentif default (entity 'all' × kategori). Idempotent."""
    if await db.incentive_rates.count_documents({}) > 0:
        return
    cats = [c for c in await db.products.distinct("category") if c]
    docs = []
    for cat in sorted(set(cats) | set(_INCENTIVE_DEFAULT)):
        docs.append({
            "id": new_id("irate"), "entity_id": "all", "category": cat,
            "incentive_unit": "yard", "per_unit_amount": float(_INCENTIVE_DEFAULT.get(cat, 2500)),
            "discount_threshold_type": "pct", "discount_threshold": 10.0,
            "discount_mechanic": "tier_factor", "discount_factor": 0.5,
            "discount_potong_rp": 0.0, "margin_cap_pct": 50.0,
            "status": "active", "created_at": now_iso(), "updated_at": now_iso(),
        })
    if docs:
        await db.incentive_rates.insert_many(docs)




# ─── Fase 3: Procurement (Supplier Master + Pengelolaan Kas) ─────────────────

async def seed_procurement() -> None:
    """Seed master supplier + contoh transaksi kas (idempotent). Backfill PO.supplier_id."""
    if await db.suppliers.count_documents({}) == 0:
        base = [
            {"name": "Cirebon Craft", "npwp": "21.111.222.3-401.000", "pic_name": "Pak Wahyu",
             "phone": "081234500001", "city": "Cirebon", "goods_type": "Batik & Kain Cap", "entity_id": "ent_ksc"},
            {"name": "NTT Weaving Co", "npwp": "22.222.333.4-402.000", "pic_name": "Ibu Agnes",
             "phone": "082345600002", "city": "Kupang", "goods_type": "Tenun Ikat", "entity_id": "ent_ksc"},
            {"name": "Solo Weave", "npwp": "23.333.444.5-403.000", "pic_name": "Pak Joko",
             "phone": "085012300003", "city": "Solo", "goods_type": "Lurik & Benang", "entity_id": "ent_ksc"},
            {"name": "Palembang Silk House", "npwp": "24.444.555.6-404.000", "pic_name": "Ibu Sri",
             "phone": "081299900004", "city": "Palembang", "goods_type": "Songket & Benang Emas", "entity_id": "ent_ksc"},
            {"name": "Toba Craft", "npwp": "", "pic_name": "Pak Sahat",
             "phone": "081377700005", "city": "Medan", "goods_type": "Ulos", "entity_id": "ent_kanda"},
        ]
        docs = []
        for i, s in enumerate(base, start=1):
            docs.append({
                "id": new_id("sup"), "code": f"SUP-{i:05d}", "name": s["name"],
                "npwp": s["npwp"], "pic_name": s["pic_name"], "phone": s["phone"],
                "email": "", "address": "", "city": s["city"], "goods_type": s["goods_type"],
                "payment_term_code": "NET30", "entity_id": s["entity_id"], "notes": "",
                "status": "active", "created_by": "seed",
                "created_at": now_iso(), "updated_at": now_iso(),
            })
        await db.suppliers.insert_many(docs)

    # Backfill purchase_orders.supplier_id by name match (idempotent)
    sup_by_name = {s["name"]: s["id"] for s in await db.suppliers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
    async for po in db.purchase_orders.find({"$or": [{"supplier_id": {"$exists": False}}, {"supplier_id": ""}]}, {"_id": 0, "id": 1, "supplier_name": 1}):
        sid = sup_by_name.get(po.get("supplier_name", ""))
        if sid:
            await db.purchase_orders.update_one({"id": po["id"]}, {"$set": {"supplier_id": sid}})

    if await db.cash_transactions.count_documents({}) == 0:
        examples = [
            {"cash_type": "kas_besar", "direction": "in",  "amount": 100000000, "category": "modal",
             "description": "Setoran modal awal (rekening bank badan usaha)", "entity_id": "ent_ksc"},
            {"cash_type": "kas_kecil", "direction": "in",  "amount": 10000000,  "category": "transfer",
             "description": "Top-up kas kecil PT Kain Suka Cita", "entity_id": "ent_ksc"},
            {"cash_type": "kas_kecil", "direction": "out", "amount": 1500000,   "category": "operasional",
             "description": "Biaya operasional gudang", "entity_id": "ent_ksc"},
            {"cash_type": "kas_kecil", "direction": "out", "amount": 750000,    "category": "pembelian",
             "description": "Pembelian bahan printing", "entity_id": "ent_ksc"},
            {"cash_type": "kas_kecil", "direction": "in",  "amount": 5000000,   "category": "transfer",
             "description": "Top-up kas kecil CV Kanda Suka", "entity_id": "ent_kanda"},
        ]
        docs = []
        for i, e in enumerate(examples, start=1):
            docs.append({
                "id": new_id("cash"), "number": f"CASH-{i:05d}", **e,
                "ref_type": "manual", "ref_id": "", "txn_date": now_iso(),
                "status": "posted", "created_by": "seed",
                "created_at": now_iso(), "updated_at": now_iso(),
            })
        await db.cash_transactions.insert_many(docs)

    # Depth #2b — set reorder_point/reorder_qty default pada produk (idempotent)
    await db.products.update_many(
        {"reorder_point": {"$exists": False}},
        {"$set": {"reorder_point": 300.0, "reorder_qty": 500.0}})

    # Depth #2a — contoh Purchase Requisition (idempotent)
    if await db.purchase_requisitions.count_documents({}) == 0:
        prods = await db.products.find({"status": "active"}, {"_id": 0}).sort("sku", 1).to_list(5)
        wh = await db.warehouses.find_one({}, {"_id": 0, "id": 1, "name": 1})
        sup = await db.suppliers.find_one({}, {"_id": 0, "id": 1, "name": 1})
        if prods and wh:
            now = now_iso()
            def _mk(num, items, status, total, source="manual", appr=False):
                return {
                    "id": new_id("pr"), "number": num, "entity_id": "ent_ksc",
                    "warehouse_id": wh["id"], "warehouse_name": wh["name"],
                    "items": items, "total_est_amount": round(total, 2),
                    "source": source, "source_ref_id": "",
                    "preferred_supplier_id": (sup or {}).get("id", ""),
                    "preferred_supplier_name": (sup or {}).get("name", ""),
                    "reason": "Restock kebutuhan produksi", "needed_by_date": "",
                    "notes": "Contoh seed", "status": status,
                    "approval_required": appr,
                    "required_approval_role": "manager" if appr else None,
                    "approval_status": "approved" if status == "approved" else ("pending" if status == "pending_approval" else "not_submitted"),
                    "po_id": "", "po_number": "",
                    "created_by": "seed",
                    "approved_by": "seed (auto)" if status == "approved" else None,
                    "approved_at": now if status == "approved" else None,
                    "rejected_by": None, "rejected_at": None, "reject_reason": None,
                    "created_at": now, "updated_at": now,
                }
            def _items(plist):
                out = []
                tot = 0.0
                for p in plist:
                    price = float(p.get("harga_pokok", 0) or p.get("price", 0) or 0)
                    qty = 500.0
                    sub = round(price * qty, 2)
                    tot += sub
                    out.append({"product_id": p["id"], "sku": p.get("sku", ""),
                                "product_name": p.get("name", ""), "description": p.get("name", ""),
                                "quantity": qty, "unit": p.get("base_unit", "yard"),
                                "est_price": price, "subtotal": sub, "note": ""})
                return out, round(tot, 2)
            it1, t1 = _items(prods[:2])
            it2, t2 = _items(prods[2:4] if len(prods) >= 4 else prods[:1])
            await db.purchase_requisitions.insert_many([
                _mk("PR-00001", it1, "approved", t1, source="reorder", appr=False),
                _mk("PR-00002", it2, "pending_approval", t2, source="manual", appr=True),
            ])



# ─── FASE H0: HRD Foundation (Employee Master + Org Units + HR Settings) ─────

# Struktur org baku per entitas: (dept_key, dept_name, [(pos_key, pos_name)...])
HR_DEPARTMENTS = [
    ("manajemen", "Manajemen", [("direktur", "Direktur"), ("manajer", "Manajer")]),
    ("penjualan", "Penjualan", [("sales_exec", "Sales Executive"), ("sales_spv", "Sales Supervisor")]),
    ("gudang", "Gudang & Operasional", [("staf_gudang", "Staf Gudang"), ("kepala_gudang", "Kepala Gudang")]),
    ("keuangan", "Keuangan & Admin", [("staf_admin", "Staf Admin"), ("akunting", "Akunting")]),
]
# Pemetaan role akun login → (dept_key, pos_key) untuk backfill karyawan.
ROLE_TO_ORG = {
    "admin": ("manajemen", "direktur"),
    "manager": ("manajemen", "manajer"),
    "sales": ("penjualan", "sales_exec"),
    "warehouse": ("gudang", "staf_gudang"),
}
_HR_DEFAULT_SALARY = {"admin": 15000000, "manager": 12000000, "sales": 6000000, "warehouse": 4500000}


async def seed_hr_foundation() -> None:
    """FASE H0 — seed config HR + struktur org per entitas + backfill karyawan (idempotent)."""
    from services.hr_service import DEFAULT_HR_SETTINGS

    # 1) Config HR/Payroll (system_settings scope='hr')
    if not await db.system_settings.find_one({"scope": "hr"}):
        await db.system_settings.insert_one({
            "id": new_id("set"), "scope": "hr",
            **{k: v for k, v in DEFAULT_HR_SETTINGS.items()},
            "created_at": now_iso(), "updated_at": now_iso(),
        })

    # 2) Org units per entitas (idempotent per entitas: hanya bila entitas belum punya unit)
    entities = await db.business_entities.find(
        {"status": "active"}, {"_id": 0, "id": 1}).to_list(50)
    for ent in entities:
        eid = ent["id"]
        if await db.hr_org_units.count_documents({"entity_id": eid}):
            continue
        units = []
        for di, (dkey, dname, positions) in enumerate(HR_DEPARTMENTS, start=1):
            dept_id = f"orgu_{eid}_{dkey}"
            units.append({
                "id": dept_id, "code": f"DEPT-{di:03d}", "name": dname,
                "unit_type": "department", "parent_id": "", "head_employee_id": "",
                "description": f"Departemen {dname}", "entity_id": eid, "status": "active",
                "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso(),
            })
            for pi, (pkey, pname) in enumerate(positions, start=1):
                units.append({
                    "id": f"orgu_{eid}_{dkey}_{pkey}", "code": f"POS-{di:02d}{pi:02d}",
                    "name": pname, "unit_type": "position", "parent_id": dept_id,
                    "head_employee_id": "", "description": f"Jabatan {pname}",
                    "entity_id": eid, "status": "active", "created_by": "seed",
                    "created_at": now_iso(), "updated_at": now_iso(),
                })
        if units:
            await db.hr_org_units.insert_many(units)

    # 3) Backfill hr_employees dari users (link user_id, idempotent)
    # FASE E-2 (E2.6) — hanya akun AKTIF yang dibuatkan karyawan. Dulu akun yang sudah
    # dinonaktifkan tetap dibuatkan baris karyawan baru setiap bootstrap, sehingga
    # daftar karyawan HR menggelembung dengan orang yang sudah tidak ada.
    linked = set()
    async for e in db.hr_employees.find({"user_id": {"$nin": ["", None]}}, {"_id": 0, "user_id": 1}):
        linked.add(e["user_id"])
    code_n = await db.hr_employees.count_documents({})
    new_emps = []
    for u in await db.users.find({"status": "active"}, {"_id": 0}).to_list(500):
        if u["id"] in linked:
            continue
        eid = u.get("home_entity_id") or PRIMARY_ENTITY_ID
        dkey, pkey = ROLE_TO_ORG.get(u.get("role", ""), ("manajemen", "manajer"))
        dept_id, pos_id = f"orgu_{eid}_{dkey}", f"orgu_{eid}_{dkey}_{pkey}"
        if not await db.hr_org_units.find_one({"id": dept_id}, {"_id": 0, "id": 1}):
            dept_id, pos_id = "", ""
        code_n += 1
        new_emps.append({
            "id": new_id("emp"), "code": f"EMP-{code_n:05d}", "name": u.get("name", ""),
            "nik": "", "user_id": u["id"], "dob": "", "gender": "", "phone": "",
            "email": u.get("email", ""), "address": "", "department_id": dept_id,
            "position_id": pos_id, "employment_type": "tetap", "join_date": "2023-01-15",
            "status": "active", "npwp": "", "ptkp_status": "TK0",
            "bpjs_kes_enabled": True, "bpjs_kes_no": "", "bpjs_tk_enabled": True,
            "bpjs_tk_no": "", "jkk_risk_class": "II", "bank_name": "Bank BCA",
            "bank_acc_no": "", "bank_acc_name": u.get("name", ""),
            "base_salary": float(_HR_DEFAULT_SALARY.get(u.get("role", ""), 5000000)),
            "allowances": [], "photo_url": "", "entity_id": eid, "created_by": "seed",
            "created_at": now_iso(), "updated_at": now_iso(),
        })
    if new_emps:
        await db.hr_employees.insert_many(new_emps)

    # 4) Karyawan non-sistem (driver/security) untuk entitas utama (idempotent)
    if await db.hr_employees.count_documents({"user_id": ""}) == 0:
        eid = PRIMARY_ENTITY_ID
        dept_id = f"orgu_{eid}_gudang"
        if await db.hr_org_units.find_one({"id": dept_id}, {"_id": 0, "id": 1}):
            base = [
                {"name": "Slamet Riyadi", "pos": "staf_gudang", "type": "harian",
                 "salary": 4000000, "phone": "081255500011"},
                {"name": "Agus Setiawan", "pos": "staf_gudang", "type": "kontrak",
                 "salary": 3800000, "phone": "081255500022"},
            ]
            extras = []
            for s in base:
                code_n += 1
                extras.append({
                    "id": new_id("emp"), "code": f"EMP-{code_n:05d}", "name": s["name"],
                    "nik": "", "user_id": "", "dob": "", "gender": "L", "phone": s["phone"],
                    "email": "", "address": "", "department_id": dept_id,
                    "position_id": f"orgu_{eid}_gudang_staf_gudang", "employment_type": s["type"],
                    "join_date": "2024-03-01", "status": "active", "npwp": "", "ptkp_status": "TK0",
                    "bpjs_kes_enabled": True, "bpjs_kes_no": "", "bpjs_tk_enabled": True,
                    "bpjs_tk_no": "", "jkk_risk_class": "III", "bank_name": "Bank BRI",
                    "bank_acc_no": "", "bank_acc_name": s["name"], "base_salary": float(s["salary"]),
                    "allowances": [], "photo_url": "", "entity_id": eid, "created_by": "seed",
                    "created_at": now_iso(), "updated_at": now_iso(),
                })
            if extras:
                await db.hr_employees.insert_many(extras)


# ─── FASE H1: HRD Absensi (Shift + Geofence + Device + sample kehadiran) ─────

async def seed_hr_attendance_foundation() -> None:
    """FASE H1 — seed shift + geofence per entitas, device_user_id + contoh kehadiran (idempotent)."""
    from services import hr_attendance_service as att
    from datetime import timedelta

    entities = await db.business_entities.find(
        {"status": "active"}, {"_id": 0, "id": 1}).to_list(50)

    # 1) Default shift + geofence per entitas
    for ent in entities:
        eid = ent["id"]
        if not await db.hr_shifts.count_documents({"entity_id": eid}):
            await db.hr_shifts.insert_one({
                "id": new_id("shift"), "code": "SHIFT-001", "name": "Shift Reguler",
                "jam_in": "08:00", "jam_out": "17:00", "grace_late_min": 10, "break_min": 60,
                "work_days": [1, 2, 3, 4, 5], "status": "active", "entity_id": eid,
                "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso(),
            })
        if not await db.hr_geofences.count_documents({"entity_id": eid}):
            await db.hr_geofences.insert_one({
                "id": new_id("geo"), "name": "Kantor Pusat", "lat": -6.917464, "lon": 107.619123,
                "radius_m": 150, "address": "Jl. Tamansari, Bandung", "status": "active",
                "entity_id": eid, "created_by": "seed",
                "created_at": now_iso(), "updated_at": now_iso(),
            })

    # 2) device_user_id + shift_id backfill ke karyawan (per entitas, enroll mulai 1001)
    for ent in entities:
        eid = ent["id"]
        shift = await db.hr_shifts.find_one(
            {"entity_id": eid, "status": "active"}, {"_id": 0, "id": 1})
        sid = shift["id"] if shift else ""
        n = 1000
        async for e in db.hr_employees.find(
                {"entity_id": eid, "device_user_id": {"$nin": ["", None]}},
                {"_id": 0, "device_user_id": 1}):
            try:
                n = max(n, int(str(e["device_user_id"])))
            except (ValueError, TypeError):
                pass
        async for e in db.hr_employees.find(
                {"entity_id": eid}, {"_id": 0, "id": 1, "device_user_id": 1, "shift_id": 1}):
            updates = {}
            if not e.get("device_user_id"):
                n += 1
                updates["device_user_id"] = str(n)
            if not e.get("shift_id") and sid:
                updates["shift_id"] = sid
            if updates:
                await db.hr_employees.update_one({"id": e["id"]}, {"$set": updates})

    # 3) Registry device fingerprint utk entitas utama (idempotent)
    if not await db.hr_devices.count_documents({"entity_id": PRIMARY_ENTITY_ID}):
        await db.hr_devices.insert_one({
            "id": new_id("dev"), "name": "ZKTeco K40 — Pintu Utama", "code": "ZK-K40-001",
            "location": "Lobby Kantor Pusat", "device_token": new_id("devtok"),
            "last_sync": "", "status": "active", "entity_id": PRIMARY_ENTITY_ID,
            "created_by": "seed", "created_at": now_iso(), "updated_at": now_iso(),
        })

    # 4) Contoh kehadiran (hanya bila koleksi kosong) — 5 hari kerja terakhir, 4 karyawan
    if await db.hr_attendance.count_documents({}) == 0:
        emps = await db.hr_employees.find(
            {"entity_id": PRIMARY_ENTITY_ID, "status": "active"},
            {"_id": 0}).sort("created_at", 1).to_list(4)
        today = att.wib_now().date()
        days, d = [], today
        while len(days) < 5:
            if d.weekday() < 5:
                days.append(d)
            d = d - timedelta(days=1)
        plan = [("08:02", "17:10"), ("08:00", "17:05"), ("08:25", "17:40"),
                ("07:58", "17:02"), ("08:15", "17:20")]
        for i, emp in enumerate(emps):
            for j, dd in enumerate(days):
                ci_t, co_t = plan[(i + j) % len(plan)]
                ds = dd.isoformat()
                method = "fingerprint" if (i % 2 == 0) else "geo"
                await att.upsert_attendance(
                    emp, ds, f"{ds}T{ci_t}:00+07:00", f"{ds}T{co_t}:00+07:00",
                    method, PRIMARY_ENTITY_ID)


# ─── FASE H2: HRD Live Tracking + Visits (seed posisi terkini + kunjungan) ───

async def seed_hr_tracking_foundation() -> None:
    """FASE H2 — seed jejak GPS terkini + contoh kunjungan (idempotent)."""
    from datetime import timedelta, datetime, timezone
    WIB = timezone(timedelta(hours=7))
    now = datetime.now(WIB)

    sales_users = [u["id"] async for u in db.users.find(
        {"role": "sales", "status": "active"}, {"_id": 0, "id": 1})]
    field_emps = await db.hr_employees.find(
        {"entity_id": PRIMARY_ENTITY_ID, "status": "active",
         "user_id": {"$in": sales_users}}, {"_id": 0}).to_list(10)
    if not field_emps:
        field_emps = await db.hr_employees.find(
            {"entity_id": PRIMARY_ENTITY_ID, "status": "active"},
            {"_id": 0}).sort("created_at", 1).to_list(2)
    if not field_emps:
        return

    base = (-6.91747, 107.61912)  # Bandung
    # 1) Field tracks (breadcrumb) — hanya bila kosong
    if await db.hr_field_tracks.count_documents({}) == 0:
        docs = []
        for ei, emp in enumerate(field_emps[:3]):
            for k in range(6):  # 6 titik, terbaru ~1 menit lalu
                ts = now - timedelta(minutes=(6 - k) + ei)
                docs.append({
                    "id": new_id("trk"), "employee_id": emp["id"],
                    "employee_name": emp.get("name", ""),
                    "lat": round(base[0] + 0.004 * ei + 0.0012 * k, 6),
                    "lon": round(base[1] + 0.004 * ei + 0.0015 * k, 6),
                    "accuracy": 12, "battery": 80 - k * 2, "ts": ts.isoformat(),
                    "entity_id": PRIMARY_ENTITY_ID, "source": "seed",
                    "created_at": now_iso(),
                })
        if docs:
            await db.hr_field_tracks.insert_many(docs)

    # 2) Visits (kunjungan) — hanya bila kosong
    if await db.hr_visits.count_documents({}) == 0:
        custs = await db.customers.find(
            {}, {"_id": 0, "id": 1, "name": 1}).to_list(4)
        if custs:
            visits = []
            for ei, emp in enumerate(field_emps[:2]):
                for vi in range(2):
                    cust = custs[(ei * 2 + vi) % len(custs)]
                    ci = now - timedelta(hours=3 - vi, minutes=10 * vi)
                    co = ci + timedelta(minutes=35 + vi * 10)
                    visits.append({
                        "id": new_id("visit"), "employee_id": emp["id"],
                        "employee_name": emp.get("name", ""),
                        "customer_id": cust["id"], "customer_name": cust.get("name", ""),
                        "date": now.date().isoformat(),
                        "check_in": {"ts": ci.isoformat(), "lat": base[0] + 0.003 * vi,
                                     "lon": base[1] + 0.003 * vi, "photo_url": ""},
                        "check_out": {"ts": co.isoformat(), "lat": base[0], "lon": base[1]},
                        "notes": "Kunjungan rutin penawaran kain.",
                        "outcome": "order" if vi == 0 else "followup", "linked_so_id": "",
                        "status": "done",
                        "duration_min": int((co - ci).total_seconds() // 60),
                        "entity_id": PRIMARY_ENTITY_ID,
                        "created_at": now_iso(), "updated_at": now_iso(),
                    })
            if visits:
                await db.hr_visits.insert_many(visits)


async def seed_hr_leave_foundation() -> None:
    """FASE H3 — seed saldo cuti + contoh pengajuan cuti & lembur (idempotent)."""
    from datetime import datetime, timedelta, timezone
    from services import hr_leave_service as lv
    WIB = timezone(timedelta(hours=7))
    entity_id = PRIMARY_ENTITY_ID
    emps = await db.hr_employees.find(
        {"entity_id": entity_id, "status": "active"}, {"_id": 0}).sort("name", 1).to_list(200)
    if not emps:
        return
    year = datetime.now(WIB).year
    # 1) Saldo cuti untuk semua karyawan aktif (idempotent)
    for e in emps:
        if not await db.hr_leave_balances.find_one({"employee_id": e["id"], "year": year}):
            await lv.recompute_balance(e["id"], entity_id, year)
    # 2) Contoh pengajuan cuti (hanya bila belum ada sama sekali di entitas ini)
    if await db.hr_leave_requests.count_documents({"entity_id": entity_id}) == 0 and len(emps) >= 2:
        today = datetime.now(WIB).date()
        monday = today - timedelta(days=today.weekday())  # Senin minggu ini
        try:
            lvdoc = await lv.submit_leave(
                emps[0], {"leave_type": "cuti_tahunan", "date_from": monday.isoformat(),
                          "date_to": (monday + timedelta(days=1)).isoformat(),
                          "reason": "Acara keluarga"}, "system-seed")
            await lv.approve_leave(lvdoc["id"], {"name": "system-seed"})
        except Exception as e:  # pragma: no cover
            print(f"[seed_hr_leave] approved cuti skip: {e}")
        try:
            nm = monday + timedelta(days=7)  # Senin minggu depan
            await lv.submit_leave(
                emps[1], {"leave_type": "izin", "date_from": nm.isoformat(),
                          "date_to": nm.isoformat(), "reason": "Keperluan pribadi"}, "system-seed")
        except Exception as e:  # pragma: no cover
            print(f"[seed_hr_leave] pending izin skip: {e}")
    # 3) Contoh lembur approved (periode berjalan) untuk emps[0]
    if await db.hr_overtime.count_documents({"entity_id": entity_id}) == 0:
        ot_date = datetime.now(WIB).date()
        while ot_date.weekday() >= 5:  # mundur ke Jumat bila weekend
            ot_date -= timedelta(days=1)
        try:
            otdoc = await lv.submit_overtime(
                emps[0], {"date": ot_date.isoformat(), "hours": 2, "reason": "Lembur kejar pesanan"},
                "system-seed")
            await lv.approve_overtime(otdoc["id"], {"name": "system-seed"})
        except Exception as e:  # pragma: no cover
            print(f"[seed_hr_leave] overtime skip: {e}")


async def seed_hr_kpi_foundation() -> None:
    """FASE H5 — seed contoh KPI desain (idempotent) untuk 1-2 karyawan periode berjalan."""
    from datetime import datetime, timedelta, timezone
    from services import hr_kpi_service as kpi
    WIB = timezone(timedelta(hours=7))
    entity_id = PRIMARY_ENTITY_ID
    if await db.hr_kpi.count_documents({"entity_id": entity_id}) > 0:
        return
    emps = await db.hr_employees.find(
        {"entity_id": entity_id, "status": "active"}, {"_id": 0}).sort("name", 1).to_list(50)
    if not emps:
        return
    period = datetime.now(WIB).strftime("%Y-%m")
    samples = [
        {"metric": "Jumlah Desain Baru", "target": 10, "actual": 12, "weight": 2,
         "note": "Motif batik & tenun"},
        {"metric": "Kualitas Desain (skala 100)", "target": 90, "actual": 85, "weight": 1,
         "note": "Penilaian reviewer"},
        {"metric": "Produktivitas (ketepatan waktu)", "target": 100, "actual": 95, "weight": 1,
         "note": ""},
    ]
    target_emps = emps[:2] if len(emps) >= 2 else emps[:1]
    for e in target_emps:
        for s in samples:
            try:
                await kpi.submit_kpi(e, {**s, "period": period}, "system-seed")
            except Exception as ex:  # pragma: no cover
                print(f"[seed_hr_kpi] skip: {ex}")


async def seed_design_gallery_foundation() -> None:
    """FASE H5 — seed contoh motif kain (tanpa file; tags manual; ai_meta nonaktif)."""
    from services import design_gallery_service as gal
    entity_id = PRIMARY_ENTITY_ID
    # Dua contoh dasar hanya dibuat sekali; contoh "menunggu pengesahan" di bawah
    # dijaga idempotennya SENDIRI supaya ia tetap terbentuk pada basis data yang
    # galerinya sudah berisi (kalau tidak, data demo lama tak akan pernah punya satu
    # pun desain di antrean pengesahan dan langkah baru F-6.7 tak bisa dilihat).
    if await db.design_gallery.count_documents({"entity_id": entity_id}) == 0:
        await _seed_design_samples(gal, entity_id)
    await _seed_design_pending_example(gal, entity_id)


async def _seed_design_samples(gal, entity_id: str) -> None:
    samples = [
        {"title": "Batik Parang Klasik", "story": "Motif parang melambangkan kesinambungan & semangat pantang menyerah.",
         "tags": ["batik", "parang", "klasik", "cokelat"]},
        {"title": "Tenun Ikat Sumba", "story": "Tenun ikat khas Sumba dengan ragam motif kuda dan satwa.",
         "tags": ["tenun", "ikat", "sumba", "etnik"]},
    ]
    for s in samples:
        try:
            await gal.create_gallery(s, "system-seed", entity_id)
        except Exception as ex:  # pragma: no cover
            print(f"[seed_design_gallery] skip: {ex}")

async def _seed_design_pending_example(gal, entity_id: str) -> None:
    """UTANG ALUR F-6.7 — satu desain yang SUDAH DIAJUKAN.

    Supaya langkah baru "Ajukan → Sahkan/Kembalikan" bisa dilihat bekerja dan antrean
    `design_gallery` tidak kosong di data demo. Kode & BERKAS-nya nyata (PNG 1×1 asli
    lewat jalur unggah produksi) — bukan entri palsu yang membuat gambar gagal dimuat.
    """
    try:
        if await db.design_gallery.count_documents(
                {"entity_id": entity_id, "status": "pending_approval"}) == 0:
            doc = await gal.create_gallery(
                {"title": "Parang Kontemporer (menunggu pengesahan)",
                 "story": "Revisi motif parang untuk koleksi ritel — menunggu pengesahan.",
                 "tags": ["parang", "kontemporer"], "code": "DSG-PARANG-02",
                 "design_type": "motif"}, "Desainer Demo", entity_id)
            await gal.add_file(doc["id"], "parang-02.png", "image/png",
                               _demo_motif_png())
            await gal.submit_design(doc["id"], "Desainer Demo")
    except Exception as ex:  # pragma: no cover
        print(f"[seed_design_gallery] contoh 'diajukan' dilewati: {ex}")


def _demo_motif_png() -> bytes:
    """Gambar motif contoh (parang miring) yang DIBUAT, bukan diambil dari mana pun.

    Sengaja digambar 480×360 dengan pola diagonal berulang: satu piksel yang
    diperbesar kartu galeri akan tampak seperti blok warna penuh — terlihat seperti
    gambar rusak, dan pemilik akan menyimpulkan pengunggahannya gagal.
    """
    from io import BytesIO  # noqa: PLC0415
    from PIL import Image, ImageDraw  # noqa: PLC0415
    w, h = 480, 360
    img = Image.new("RGB", (w, h), (247, 243, 235))
    d = ImageDraw.Draw(img)
    for i in range(-h, w, 48):                      # sapuan diagonal (motif parang)
        d.line([(i, h), (i + h, 0)], fill=(122, 74, 48), width=14)
        d.line([(i + 22, h), (i + 22 + h, 0)], fill=(203, 168, 121), width=5)
    for gy in range(24, h, 72):                     # titik isen-isen
        for gx in range(24, w, 72):
            d.ellipse([gx - 4, gy - 4, gx + 4, gy + 4], fill=(60, 43, 33))
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def seed_hr_payroll_foundation() -> None:
    """FASE H4 — contoh payroll run (idempotent) agar UI berisi data.

    DUA run dengan sengaja, sejak UTANG ALUR F-6.7 dibayar (2026-08-18):
      · bulan LALU → `approved` (slip muncul di ESS + tombol Posting GL/Bayar bisa dicoba);
      · dua bulan LALU → `pending_approval` (sudah DIAJUKAN, belum disahkan) supaya
        langkah baru "Ajukan → Sahkan/Kembalikan" bisa dilihat bekerja, dan supaya
        antrean `hr_payroll` di Pusat Persetujuan & KPI beranda tidak kosong di data demo.
    Periode BULAN INI sengaja dibiarkan kosong agar pemilik tetap bisa mencoba
    "Buat / Hitung Run" sendiri tanpa bentrok "periode sudah ada".
    """
    from datetime import datetime, timezone, timedelta
    WIB = timezone(timedelta(hours=7))
    now = datetime.now(WIB)
    first_this = now.replace(day=1)
    period = (first_this - timedelta(days=1)).strftime("%Y-%m")           # bulan lalu
    period_prev = (first_this - timedelta(days=1)).replace(day=1)
    period_prev = (period_prev - timedelta(days=1)).strftime("%Y-%m")      # dua bulan lalu
    entity_id = PRIMARY_ENTITY_ID
    if await db.hr_employees.count_documents({"entity_id": entity_id, "status": "active"}) == 0:
        return
    from services import hr_payroll_service as pay
    # (a) bulan lalu — disahkan penuh (lewat langkah "ajukan" yang kini wajib).
    if await db.hr_payroll_runs.count_documents({"entity_id": entity_id, "period": period}) == 0:
        try:
            run = await pay.create_run(entity_id, period, {"name": "system-seed"})
            await pay.submit_run(run["id"], {"name": "system-seed"})
            await pay.approve_run(run["id"], {"name": "system-seed"})
        except Exception as e:  # pragma: no cover
            print(f"[seed_hr_payroll] skip {period}: {e}")
    # (b) dua bulan lalu — berhenti di `pending_approval` (menunggu keputusan orang).
    if await db.hr_payroll_runs.count_documents({"entity_id": entity_id,
                                                 "period": period_prev}) == 0:
        try:
            run2 = await pay.create_run(entity_id, period_prev, {"name": "system-seed"})
            await pay.submit_run(run2["id"], {"name": "HR Payroll"})
        except Exception as e:  # pragma: no cover
            print(f"[seed_hr_payroll] skip {period_prev}: {e}")


async def seed_sales_extras_foundation() -> None:
    """Seed contoh Special Order (OD) & Sales Return (idempotent) agar UI tidak kosong."""
    from services.special_order_service import generate_special_order_number, APPROVAL_THRESHOLD
    from services.return_service import next_return_number
    entity_id = PRIMARY_ENTITY_ID
    now = now_iso()
    # --- Special Orders (OD) ---
    if await db.special_orders.count_documents({"entity_id": entity_id}) == 0:
        cust = await db.customers.find_one({"entity_id": entity_id}, {"_id": 0}) or await db.customers.find_one({}, {"_id": 0})
        if cust:
            addr = (cust.get("addresses") or [{}])[0]
            samples = [
                {"desc": "Kain jacquard custom motif logo perusahaan", "qty": 500, "unit": "yard", "price": 85000, "status": "draft"},
                {"desc": "Sutra dobby warna Pantone khusus (indent 6 minggu)", "qty": 300, "unit": "yard", "price": 145000, "status": "pending_approval"},
                {"desc": "Katun premium bordir custom seragam", "qty": 1200, "unit": "yard", "price": 42000, "status": "in_production"},
            ]
            for s in samples:
                total = s["qty"] * s["price"]
                number = await generate_special_order_number()
                await db.special_orders.insert_one({
                    "id": new_id("sord"), "number": number, "status": s["status"],
                    "type": "special_order", "customer_id": cust["id"], "customer_name": cust["name"],
                    "customer_email": cust.get("email", ""), "customer_phone": cust.get("phone", ""),
                    "shipping_address": addr,
                    "custom_item": {"description": s["desc"], "specifications": {"warna": "custom", "lebar": "1.5m"},
                                    "quantity": s["qty"], "unit": s["unit"], "target_price": s["price"], "notes": ""},
                    "total_amount": total, "requires_approval": total > APPROVAL_THRESHOLD,
                    "approval_threshold": APPROVAL_THRESHOLD, "expected_delivery": "",
                    "entity_id": entity_id, "notes": "Contoh data demo",
                    "status_history": [{"status": s["status"], "timestamp": now, "user": "system-seed"}],
                    "created_at": now, "created_by": "system-seed", "updated_at": now,
                })
    # --- Sales Returns ---
    if await db.sales_returns.count_documents({"entity_id": entity_id}) == 0:
        order = await db.sales_orders.find_one(
            {"entity_id": entity_id, "status": {"$in": ["shipped", "done", "confirmed"]}}, {"_id": 0}
        ) or await db.sales_orders.find_one({"entity_id": entity_id}, {"_id": 0})
        if order:
            it = (order.get("items") or [{}])[0]
            base_item = {"product_id": it.get("product_id", ""), "product_name": it.get("product_name", "Produk"),
                         "quantity_returned": 10, "unit": it.get("unit", "yard"),
                         "reason": "Cacat kain / salah warna (demo)", "condition": "rusak"}
            samples = [("retur", "draft"), ("bs", "pending_approval"), ("penggantian", "approved")]
            for rt, st in samples:
                number = await next_return_number()
                await db.sales_returns.insert_one({
                    "id": new_id("sret"), "number": number, "order_id": order["id"],
                    "order_number": order.get("number", ""), "customer_id": order.get("customer_id"),
                    "customer_name": order.get("customer_name", ""), "entity_id": entity_id,
                    "return_type": rt, "status": st, "items": [base_item], "notes": "Contoh data demo",
                    "attachments": [], "stock_adjusted": False, "created_by": "system-seed",
                    "approved_by": ("system-seed" if st == "approved" else None),
                    "approved_at": (now if st == "approved" else None),
                    "rejected_by": None, "rejected_at": None, "reject_reason": None,
                    "created_at": now, "updated_at": now,
                })


async def ensure_auth_indexes() -> None:
    """SEC-2 — TTL index sessions + index login_attempts + backfill expires_at (idempotent)."""
    from datetime import datetime, timedelta, timezone
    await db.sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.sessions.create_index("token")
    await db.login_attempts.create_index("identifier")
    await db.sessions.update_many(
        {"expires_at": {"$exists": False}},
        {"$set": {"expires_at": datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)}})


# ─── Fase A — util domain untuk data seed (PS-01/02/03) ──────────────────────
_SEED_GSM_BY_CATEGORY = {   # DEPRECATED — SSOT pindah ke domain_registry.DEFAULT_GSM_BY_CATEGORY
    "Batik": (120, 1.15), "Tenun": (210, 1.20), "Lurik": (170, 1.10),
    "Songket": (280, 1.05), "Ulos": (230, 0.90), "Jumputan": (150, 1.15),
    "Endek": (195, 1.15), "Denim": (340, 1.50),
}


def _stamp_domain_defaults(products):
    """Lengkapi field domain wajib (stage/fabric_type/grade/GSM/lebar) pada data seed.

    Delegasi ke `domain_registry.stamp_many` (SSOT R7) — seed WAJIB `strict=True`
    agar data demo tidak pernah lahir cacat domain (invarian INV-DOMAIN tetap hijau).
    """
    import domain_registry as dr
    return dr.stamp_many(products, strict=True, fill_measurements=True, source="seed")


async def run_bootstrap() -> None:
    """Jalankan seluruh seeder/backfill startup sesuai urutan (idempotent)."""
    await seed_data()
    await seed_entities()
    await backfill_entity_id()
    # F0-A — enrich entitas + assign user ke entitas (idempotent)
    from services.entity_context_service import ensure_entity_defaults, ensure_user_entities
    await ensure_entity_defaults()
    await ensure_user_entities()
    await sync_permission_modules()
    await sync_permission_revocations()
    await sync_uom_factors()
    await sync_product_uom_examples()
    await backfill_inventory_owner()
    await ensure_inventory_rolls()
    await backfill_roll_dye_lot()
    await ensure_config_defaults()
    # FASE B (D-06/D-07) — registry konversi satuan GLOBAL + kebijakan toleransi (idempoten)
    try:
        from services import uom_rules_service as _uomr
        await _uomr.ensure_defaults(actor="bootstrap")
    except Exception as exc:  # noqa: BLE001 — jangan gagalkan startup
        import logging
        logging.getLogger("bootstrap").warning("[uom] seed aturan konversi dilewati: %s", exc)
    # FASE C (D-10/D-26/D-27) — lot kelas satu: pengaturan penegakan + backfill lot
    # untuk SEMUA roll yang belum bertaut (idempoten; string lot lama dipertahankan).
    try:
        from services import lot_migration as _lotm
        _lres = await _lotm.run_all(actor="bootstrap")
        if _lres.get("changed"):
            import logging
            logging.getLogger("bootstrap").info(
                "[lot] backfill Fase C: %s lot dibentuk, %s roll ditaut, %s movement",
                _lres.get("lots_created"), _lres.get("rolls_linked"),
                _lres.get("movements_linked"))
    except Exception as exc:  # noqa: BLE001 — jangan gagalkan startup
        import logging
        logging.getLogger("bootstrap").warning("[lot] backfill Fase C dilewati: %s", exc)
    # FASE D (D-05/D-07/D-09) — kebijakan makloon (toleransi selisih, susut default,
    # mode kontrak, peran penyetuju klaim) — idempoten, tanpa deploy untuk mengubah.
    try:
        from services import contract_service as _cs
        await _cs.ensure_defaults(actor="bootstrap")
    except Exception as exc:  # noqa: BLE001 — jangan gagalkan startup
        import logging
        logging.getLogger("bootstrap").warning("[makloon] kebijakan default dilewati: %s", exc)
    # FASE F-1 — kebijakan input SATUAN SUPPLIER saat penerimaan (idempoten, tanpa deploy).
    try:
        from services import receiving_uom_service as _rus
        await _rus.ensure_defaults(actor="bootstrap")
    except Exception as exc:  # noqa: BLE001 — jangan gagalkan startup
        import logging
        logging.getLogger("bootstrap").warning("[receiving] kebijakan satuan dilewati: %s", exc)
    await seed_procurement()
    await seed_product_categories()
    await backfill_so_line_category()
    await backfill_costing_data()
    await backfill_so_line_cost()
    await backfill_ar_cash_postings()
    await backfill_epic6_pr_po_links()
    await seed_incentive_rates()
    await seed_initial_notifications()
    # FASE H0 — HRD foundation (config HR + struktur org + backfill karyawan)
    await seed_hr_foundation()
    # FASE H1 — HRD Absensi (shift + geofence + device + contoh kehadiran)
    await seed_hr_attendance_foundation()
    # FASE H2 — HRD Live Tracking + Visits (jejak GPS + kunjungan)
    await seed_hr_tracking_foundation()
    # FASE H3 — HRD Cuti/Izin + Lembur (saldo cuti + contoh pengajuan; sebelum payroll seed)
    await seed_hr_leave_foundation()
    # EPIC7-C — bagan akun baku + auto-posting jurnal (idempotent)
    from services import gl_service
    await gl_service.seed_default_coa()
    await gl_service.backfill_journals()
    # Digitalisasi Formulir Sukacita — kategori pengeluaran petty cash → akun COA
    from services import cash_advance_service
    await cash_advance_service.seed_expense_categories()
    # FASE H4 — HRD Payroll (contoh run periode lalu; perlu COA sudah ter-seed)
    await seed_hr_payroll_foundation()
    # FASE H5 — HRD KPI Design + Design Gallery (contoh data; AI nonaktif by default)
    await seed_hr_kpi_foundation()
    await seed_design_gallery_foundation()
    # Contoh Special Order (OD) + Sales Return agar UI tidak kosong
    await seed_sales_extras_foundation()
    await ensure_indexes()
    # FASE F — lifecycle produk dibuat eksplisit (idempoten, tanpa mengubah perilaku)
    await backfill_product_lifecycle()
    # SEC-2 — TTL session + lockout index
    await ensure_auth_indexes()
    # P1 — index performa koleksi terpanas (non-fatal, idempotent)
    try:
        from indexes import ensure_performance_indexes
        await ensure_performance_indexes()
    except Exception as exc:  # noqa: BLE001
        print(f"[bootstrap] ensure_performance_indexes skip: {exc}")
    # F-10 — migrasi rezim PPN 12% / DPP Nilai Lain 11/12 (Coretax)
    from services.config_service import migrate_tax_regime
    await migrate_tax_regime()
    # R5.2 — jaring pengaman: pastikan CN store_credit lama punya entri ledger saldo
    try:
        from services import store_credit_service
        n = await store_credit_service.backfill_from_credit_notes()
        if n:
            print(f"[bootstrap] store_credit backfill: {n} entri issue dibuat")
    except Exception as exc:  # noqa: BLE001
        print(f"[bootstrap] store_credit backfill skip: {exc}")
    # FASE E-7 (E7.2/E7.7) — setiap badan usaha melihat badan usaha grup LAIN sebagai
    # pemasok bertipe "Entitas grup" (jangkar navigasi + dasar pagar PO/SO). Idempotent.
    try:
        from services import group_partner_service as _grp
        _gres = await _grp.sync_group_entity_suppliers(actor_name="bootstrap")
        if any(_gres.values()):
            print(f"[bootstrap] E-7 pemasok entitas grup: {_gres}")
    except Exception as exc:  # noqa: BLE001 — jangan gagalkan startup
        print(f"[bootstrap] sync_group_entity_suppliers skip: {exc}")
    # FASE E-7 (E7.6) — dokumen retur antar-PT lama dilengkapi `pair_id` + `qty_total`.
    try:
        from services import interco_return_service as _icr
        _n = await _icr.backfill_pair_aliases()
        if _n:
            print(f"[bootstrap] E-7 alias pair_id/qty_total retur antar-PT: {_n} dokumen")
    except Exception as exc:  # noqa: BLE001
        print(f"[bootstrap] backfill_pair_aliases skip: {exc}")


async def ensure_indexes() -> None:
    """Index integritas (idempotent). F1b: cegah duplikasi SKU produk."""
    try:
        await db.products.create_index("sku", unique=True, name="uniq_sku")
    except Exception as exc:  # noqa: BLE001 — index sudah ada / data konflik
        print(f"[bootstrap] ensure_indexes products.sku skip: {exc}")


async def backfill_product_lifecycle() -> None:
    """FASE F (PS-12) — stempel `lifecycle` pada produk lama (IDEMPOTEN).

    Kenapa `produksi`: seluruh produk yang sudah dipakai transaksi memang SUDAH sah
    dijual/dibeli. `services/rnd_gate.py` juga memperlakukan lifecycle kosong sebagai
    `produksi`, jadi backfill ini hanya membuat datanya EKSPLISIT — tidak mengubah
    perilaku satu pun alur yang sudah berjalan (pagar #2 KN_31 §1).
    """
    try:
        res = await db.products.update_many(
            {"$or": [{"lifecycle": {"$exists": False}}, {"lifecycle": ""}, {"lifecycle": None}]},
            {"$set": {"lifecycle": "produksi"}})
        if getattr(res, "modified_count", 0):
            print(f"[bootstrap] FASE F lifecycle backfill: {res.modified_count} produk "
                  "distempel 'produksi'")
    except Exception as exc:  # noqa: BLE001 — jangan gagalkan startup
        print(f"[bootstrap] backfill_product_lifecycle skip: {exc}")
