"""F0-B — Entity scoping core (Multi-Entity foundation).

Lapisan TERPUSAT agar semua modul (kini & nanti) sadar-entitas tanpa menulis
ulang logika. Berisi:
- **Scope Registry**: koleksi → nama field entitas (atau SHARED).
- **EntityContext** dependency: resolve entitas aktif dari user + header X-Entity-Id.
- **scope_query / stamp_entity**: helper query & tulis.

Pakai di endpoint:
    ctx = Depends(entity_ctx)                  # konteks entitas
    q = apply_entity_scope("sales_orders", {...}, ctx)  # filter otomatis
    doc = stamp_entity(doc, "sales_orders", ctx)  # stamp saat create
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import Request, HTTPException

from dependencies import current_user
from services.entity_context_service import (
    PRIMARY_ENTITY_ID, CROSS_ENTITY_ROLES, resolve_allowed_entities,
    all_active_entity_ids,
)

# ─── SCOPE REGISTRY ──────────────────────────────────────────────────────────
# Field entitas per koleksi. Nilai None = SHARED (tidak di-scope).
SHARED = None
SCOPE_FIELD: Dict[str, Optional[str]] = {
    # Inventory: pakai owner_entity_id (semantik kepemilikan, dukung konsinyasi)
    "inventory_rolls": "owner_entity_id",
    "inventory_balances": "owner_entity_id",
    "inventory_movements": "owner_entity_id",
    # Fase C — lot kelas satu: kepemilikan mengikuti roll (owner_entity_id)
    "inventory_lots": "owner_entity_id",
    # FASE E-0 (L15) — RFID mengikuti KEPEMILIKAN roll, jadi fieldnya `owner_entity_id`
    # (bukan `entity_id`). Tanpa ini registry salah field dan gate ikut salah menilai.
    "rfid_tags": "owner_entity_id",
    "rfid_reads": "owner_entity_id",
    # SHARED / global (tidak di-scope)
    "uoms": SHARED,
    # FASE E-4 (E4.1) — `warehouses` TETAP SHARED dengan sengaja. Pembatasan
    # pemakaiannya relasi BANYAK-KE-BANYAK (`sharing_mode` + `entity_ids`), bukan
    # satu kolom pemilik: satu gudang boleh dipakai 2 badan usaha tanpa dibuka
    # untuk semuanya. Aturan & pagarnya di `services/warehouse_scope_service.py`.
    "warehouses": SHARED,
    "products": SHARED,             # definisi SKU bersama (D1a) — kepemilikan via stok
    "product_templates": SHARED,    # F1b — template katalog (induk varian), SHARED lintas-entitas
    "color_library": SHARED,        # M0 — master warna Pantone-style, SHARED lintas-entitas
    "product_categories": SHARED,
    "business_entities": SHARED,
    "users": SHARED,
    "sessions": SHARED,
    "permission_settings": SHARED,
    "system_settings": SHARED,
    # ── FASE E-4 (E4.2/E4.3) — MASTER BERLAPIS: baris `entity_id="all"` = GLOBAL
    # (bawaan untuk semua badan usaha), baris ber-`entity_id` = OVERRIDE yang MENANG.
    # Dulu SHARED sehingga satu nilai memaksa seluruh grup: kop surat KSC terpakai
    # di dokumen CV Kanda Suka, dan syarat bayar badan usaha non-PKP tak bisa beda.
    # Mesinnya `services/entity_master_service.py`; daftar bacanya WAJIB memakai
    # `resolve_list_scope_inherit` supaya baris global tidak hilang dari layar.
    "payment_terms": "entity_id",
    "expense_categories": "entity_id",
    "document_templates": "entity_id",
    "sales_return_policies": "entity_id",
    # FASE L — master LINI PRODUK: berlapis global→badan usaha, sama seperti master
    # E-4 di atas. Baris `entity_id="all"` = lini yang berlaku untuk seluruh grup.
    "product_lines": "entity_id",
    # FASE T — master TAHAPAN PROSES: berlapis global→badan usaha, sama seperti lini.
    "process_stages": "entity_id",
    "number_sequences": SHARED,
    "counters": SHARED,
    "user_onboarding": SHARED,
    # FASE E-0 (L1) — notifikasi WAJIB per entitas. Baris ber-`entity_id: None`
    # = notifikasi sistem/global dan tetap terlihat di semua konteks
    # (dilayani `resolve_list_scope_inherit`, bukan `resolve_list_scope`).
    "notifications": "entity_id",
    # FASE E-0 (L7) — jejak audit. PERHATIAN: `audit_logs.entity_id` sudah lama
    # dipakai sebagai **id sumber daya** (resource id), bukan badan usaha. Karena itu
    # entitas bisnis disimpan pada field terpisah `scope_entity_id`.
    "audit_logs": "scope_entity_id",
    # R6.5 — Scheduler & kanal WhatsApp: infrastruktur sistem (lintas entitas).
    "sys_scheduler_runs": SHARED,
    "sys_wa_outbox": SHARED,
    # F0-E: Chart of Accounts = SHARED by-code (template bersama). Buku & saldo
    # terpisah per-PT hidup di `journal_entries.entity_id` (bukan di master CoA).
    "gl_accounts": SHARED,
}
DEFAULT_FIELD = "entity_id"

# Koleksi yang WAJIB ter-scope (untuk gate kepatuhan F0-C). Sisanya SHARED.
SCOPED_COLLECTIONS = {
    "sales_orders", "sales_returns", "special_orders", "price_approvals",
    "ar_receipts", "cash_transactions", "bank_accounts", "journal_entries",
    # FASE G-8 — mutasi bank & perkakasnya WAJIB ter-scope. Sebelum fase ini
    # `bank_statement_lines` tidak terdaftar sehingga user PT-A cukup mengirim
    # `bank_account_id` PT-B untuk membaca mutasinya (ditutup + POC bukti-merah).
    "bank_statement_lines", "bank_statement_formats", "bank_match_rules",
    # FASE G-9 — kasus keuangan menyangkut UANG satu PT (titipan, refund, settlement)
    # sehingga wajib ter-scope: kasus PT lain tidak boleh terlihat maupun ditutup.
    "finance_cases",
    # FASE E-0 (L16) — drift nama dibetulkan: koleksi NYATA faktur pajak MASUKAN
    # bernama `tax_invoices_in` (bukan `input_tax_invoices` yang tidak pernah ada di DB).
    "tax_invoices", "tax_invoices_in",
    "contra_bons",                    # FASE G-7 — kontrabon (siklus tukar faktur supplier)
    # FASE G-6 — antar-PT (jual-beli): dokumen kembar, saldo pasangan, settlement/netting.
    # FASE G-6b — retur antar-PT (dokumen kembar nota retur ↔ nota kredit).
    "interco_transactions", "interco_accounts", "interco_settlements",
    "interco_returns",
    "purchase_orders", "purchase_requisitions", "rfqs", "vendor_bills",
    # FASE E-0 (L16) — drift kedua: koleksi NYATA voucher landed cost bernama
    # `landed_cost_vouchers`; nama lama `landed_costs` dipertahankan sebagai alias
    # supaya `assert_entity_access("landed_costs", …)` yang sudah dipakai tetap sah.
    "landed_costs", "landed_cost_vouchers", "incentive_rates", "customers", "suppliers",
    "inventory_rolls", "inventory_balances", "inventory_movements",
    "inventory_lots",                 # Fase C — lot kelas satu (D-10/D-26)
    "wms_tasks", "shipments", "qc_inspections",
    "entity_prices",
    "customer_prices",                # F1b — harga langganan per pelanggan×produk (SCOPED)
    "hr_employees", "hr_org_units",
    "hr_shifts", "hr_geofences", "hr_attendance", "hr_devices",
    "hr_field_tracks", "hr_visits",
    "hr_payroll_runs", "hr_payslips",
    "hr_leave_requests", "hr_leave_balances", "hr_overtime",
    "hr_kpi", "design_gallery",
    "tax_pph_records",
    "makloons", "process_recipes",   # M1 — master mitra makloon + resep proses (SCOPED)
    "makloon_orders",                 # M3 — transaksi makloon/subkontrak (SCOPED)
    "supplier_contracts",             # Fase D/E — kontrak mitra & supplier (SCOPED)
    "doc_amendments",                 # FASE G-1 — amandemen dokumen finansial (SCOPED)
    "supplier_items",                 # Fase E — katalog barang versi supplier (SCOPED)
    "mfg_boms", "mfg_work_orders",    # R6.4 — Produksi in-house (BOM + Work Order) (SCOPED)
    "md_specs", "md_samples",         # FASE F — R&D: spesifikasi & permintaan sample (SCOPED)
    # Digitalisasi Formulir Sukacita (Cash Advance/Settlement + Kendaraan) — SCOPED
    "cash_advances", "cash_advance_settlements",
    "vehicles", "vehicle_usage_logs",
    # ── FASE E-0 (L15) — 18 koleksi ber-`entity_id` yang sebelumnya TIDAK
    # terdaftar (bukan SCOPED, bukan SHARED) sehingga lolos dari gate kepatuhan.
    # Keputusan per koleksi ditulis EKSPLISIT, tidak diam-diam.
    "notifications",                  # L1 — notifikasi milik entitas (global = entity_id None)
    "audit_logs",                     # L7 — jejak audit per entitas (field scope_entity_id)
    "payment_plans",                  # L2 — rencana bayar = uang satu entitas
    "payment_variance_decisions",     # L3 — keputusan selisih bayar
    "penalties",                      # L4 — nota denda
    "sales_targets", "sales_incentives",   # L5/L6 — target & insentif sales
    "warehouse_transfers",            # L13/L14 — transfer gudang (antar-entitas: lihat E0.8b)
    "purchase_returns",               # retur beli = dokumen entitas
    "credit_notes",                   # nota kredit = dokumen keuangan entitas
    "budgets", "fin_budget_rules",    # anggaran & aturannya per entitas
    "approval_rules",                 # aturan persetujuan (warisan global→entitas di E-4)
    "cycle_count_sessions",           # stock opname per entitas
    "supplier_price_lists",           # daftar harga supplier = data komersial entitas
    "rfid_tags", "rfid_reads",        # tag & pembacaan RFID mengikuti roll/entitas
    "rnd_person_divisions",           # penugasan orang R&D per entitas
    # ── FASE E-4 (E4.2/E4.3) — master berlapis (global → badan usaha). Terdaftar
    # SCOPED supaya gate kepatuhan ikut menjaga; baris global tetap sah dan dibaca
    # lewat `resolve_list_scope_inherit`/`entity_master_service`.
    "payment_terms", "expense_categories", "document_templates",
    "sales_return_policies",
    # FASE L — master lini produk (berlapis global→badan usaha). Terdaftar SCOPED
    # supaya gate kepatuhan F0-C ikut menjaga: lini khusus satu badan usaha tidak
    # boleh terbaca badan usaha lain, sementara baris global tetap terlihat semua
    # (dilayani `resolve_list_scope_inherit` / `entity_master_service`).
    "product_lines",
    # FASE T — master tahapan proses (berlapis global→badan usaha). Alasannya sama
    # dengan lini: tahap khusus satu badan usaha tidak boleh terbaca badan usaha
    # lain, sedangkan baris global tetap terlihat semua lewat
    # `resolve_list_scope_inherit`/`entity_master_service`.
    "process_stages",
    # FASE E-7 (E7d) — permintaan internal (sales minta barang dari badan usaha lain).
    # SCOPED pada badan usaha PEMINTA: PT lain tidak boleh membaca daftar permintaan
    # orang lain, dan sales hanya melihat permintaan miliknya (dijaga router).
    "internal_requests",
    # FASE E-7 (E7f) — pinjaman uang antar-PT: dokumen kembar, satu baris per badan
    # usaha (pemberi & penerima), jadi SCOPED seperti `interco_transactions`.
    "interco_loans",
    # FASE E-7 (E7g) — aset tetap & histori penyusutannya milik SATU badan usaha
    # (jalur pindah aset antar-PT membuatnya berpindah lewat dokumen, bukan lewat
    # mengganti `entity_id` diam-diam). Sebelum ini koleksinya kosong sehingga gate
    # kepatuhan diam; begitu ada aset, ia wajib terdaftar.
    "fin_fixed_assets", "fin_depreciation_entries",
    # FASE E-7 — `approval_matrix_log` (PS-20) ber-`entity_id` sejak lahir dan sudah
    # ditulis SCOPED di `ENTITY_REGISTRY.md`, tetapi belum pernah terdaftar DI SINI.
    # Selama koleksinya masih kosong gate diam; begitu ada satu keputusan persetujuan
    # tercatat, gate langsung memerah ("koleksi ber-entitas tidak terdaftar") — itulah
    # yang terjadi saat pagar E7.2 diuji. Didaftarkan supaya jejak keputusan satu PT
    # tidak pernah terbaca PT lain dan gate menjaga selamanya.
    "approval_matrix_log",
    # FASE E-9 — `store_credit_ledger` = UANG milik pelanggan pada SATU badan usaha
    # (saldo kredit dari retur/kelebihan bayar). Sama seperti `approval_matrix_log`,
    # koleksinya kosong di data demo sehingga gate diam bertahun-tahun; begitu ada
    # satu retur diselesaikan dengan "store credit" (rantai retur E-9), gate langsung
    # memerah: sales PT-B membaca saldo kredit pelanggan PT-A lewat
    # `/api/store-credit` & `/api/store-credit/ledger`.
    "store_credit_ledger",
}

# Koleksi yang punya baris GLOBAL sah (berlaku untuk semua entitas) dan karena itu
# WAJIB memakai `resolve_list_scope_inherit` alih-alih `resolve_list_scope`.
# Nilai = daftar nilai field entitas yang dianggap "global".
INHERITED_GLOBAL_VALUES: Dict[str, List[Any]] = {
    "notifications": [None, ""],          # notifikasi sistem tanpa entitas
    "audit_logs": [None, ""],             # jejak lama (pra-E0) belum ber-stempel
    "incentive_rates": ["all"],           # bawaan grup; override per entitas menang (E-4)
    "approval_rules": ["all"],            # idem
    # FASE E-7 (E7.4) — `cash_transactions` & `bank_accounts` SENGAJA TIDAK LAGI di sini:
    # keputusan pemilik 3a menghapus kas tingkat grup (setiap uang wajib milik satu badan
    # usaha). Dengan dicabut dari daftar ini, gate kepatuhan akan MEMERAH bila ada lagi
    # baris kas ber-`entity_id="all"` — itulah yang kita inginkan. Data lama dipetakan
    # lewat `scripts/migrate_e7_group_cash.py --report|--apply`.
    # FASE E-4 (E4.2/E4.3) — master berlapis. `""`/None ditoleransi karena baris
    # lama pernah ditulis tanpa stempel sebelum migrasi `migrate_e4_master_scoped.py`.
    "payment_terms": ["all", "", None],
    "expense_categories": ["all", "", None],
    "document_templates": ["all", "", None],
    "sales_return_policies": ["all", "", None],
    # FASE L — lini produk: baris global "all" WAJIB tetap terlihat di semua badan
    # usaha. Tanpa baris ini, layar Master → Lini Produk akan tampak kosong padahal
    # lininya sedang dipakai 12 layar lain.
    "product_lines": ["all", "", None],
    # FASE T — tahapan proses: baris global "all" WAJIB tetap terlihat di semua badan
    # usaha. Tanpa baris ini, pemilih langkah SPK & layar Master → Tahapan Proses
    # akan tampak KOSONG padahal tahapnya sedang dipakai SPK.
    "process_stages": ["all", "", None],
}


def field_for(collection: str) -> Optional[str]:
    """Field entitas untuk koleksi. None bila SHARED."""
    if collection in SCOPE_FIELD:
        return SCOPE_FIELD[collection]
    return DEFAULT_FIELD


# ─── EntityContext ───────────────────────────────────────────────────────────
@dataclass
class EntityContext:
    user: Dict[str, Any]
    active_entity_id: str
    allowed_entity_ids: List[str] = field(default_factory=list)
    view_all: bool = False  # cross-entity "Semua Entitas" mode (header X-Entity-Id: all)

    @property
    def is_cross_entity(self) -> bool:
        return self.user.get("role") in CROSS_ENTITY_ROLES

    @property
    def can_view_combined(self) -> bool:
        """Boleh melihat gabungan ("Semua Entitas")? — diukur dari PENUGASAN, bukan nama peran.

        FASE E-8 (cacat nyata yang ditemukan 2026-08-14): dulu mode gabungan hanya
        berlaku untuk peran lintas-entitas (`is_cross_entity`). Sejak keputusan pemilik
        E8.10b#1, `sales_admin` **boleh ditugaskan ke beberapa badan usaha** lewat
        `users.allowed_entity_ids` tanpa menjadi peran lintas-PT. Akibat aturan lama:
        Admin Sales bertugas di KSC + Kanda memilih "Semua Entitas" lalu layar
        **hanya** menampilkan 8 pesanan KSC — 1 pesanan Kanda hilang tanpa pesan apa
        pun (dia baru melihatnya setelah menukar konteks satu-satu). Lebih buruk lagi:
        karena `view_all` ikut FALSE, pagar tulis mode gabungan tidak menyala sehingga
        dokumen yang dibuat sambil "melihat gabungan" mendarat diam-diam di badan usaha
        HOME.

        Isolasi tetap utuh: yang dibuka hanya `allowed_entity_ids` — daftar penugasan
        itu sendirilah pagarnya (bukan nama peran).
        """
        return len(self.allowed_entity_ids) > 1

    def can_access(self, entity_id: str) -> bool:
        return entity_id in self.allowed_entity_ids


async def entity_ctx(request: Request) -> EntityContext:
    """FastAPI dependency: resolve badan usaha aktif untuk request.

    FASE E-1 (E1.5) — **berhenti jatuh diam-diam**. Dulu `X-Entity-Id` yang tidak
    diizinkan / sudah diarsipkan diabaikan begitu saja dan request dilayani atas
    nama badan usaha HOME. Akibatnya pengguna melihat angka badan usaha lain tanpa
    sadar (layar bilang "Kanda", datanya KSC) dan tulis bisa mendarat di badan
    usaha yang salah. Sekarang: **403 dengan pesan yang menjelaskan**.
    Nilai khusus `all` (mode gabungan) tetap ditangani terpisah.
    """
    user = await current_user(request)
    home = user.get("home_entity_id") or PRIMARY_ENTITY_ID
    role = user.get("role", "")
    if role in CROSS_ENTITY_ROLES:
        # admin/manager: akses dinamis ke SEMUA entitas aktif (termasuk yang baru dibuat).
        all_ids = await all_active_entity_ids()
        allowed = resolve_allowed_entities(role, home, all_ids)
    else:
        # FASE E-1 (E1.5) — buang badan usaha terarsip dari daftar yang boleh
        # dioperasikan (pakai cache status supaya tidak menambah query per request).
        stored = user.get("allowed_entity_ids") or [home]
        from services.entity_lifecycle_service import entity_status_map, WRITE_LOCKED_STATUSES
        smap = await entity_status_map()
        allowed = [e for e in stored
                   if smap.get(e, {}).get("status", "active") not in WRITE_LOCKED_STATUSES]
        if not allowed:
            allowed = [home]
    requested = (request.headers.get("X-Entity-Id") or "").strip()
    view_all = False
    if requested == "all":
        # FASE E-8 — mode gabungan ditentukan JUMLAH PENUGASAN, bukan nama peran:
        # baca = semua `allowed`, tulis tetap dipagari `entity_write_guard` (409).
        # Pengguna ber-satu-badan-usaha tidak berubah perilakunya (tak ada gabungan
        # untuk dilihat), jadi tulisnya tetap boleh seperti sebelumnya.
        view_all = len(allowed) > 1
        active = home if home in allowed else (allowed[0] if allowed else home)
    elif requested:
        if requested not in allowed:
            from services.entity_lifecycle_service import entity_denied_message
            raise HTTPException(
                status_code=403,
                detail=await entity_denied_message(requested, allowed))
        active = requested
    else:
        active = home if home in allowed else (allowed[0] if allowed else home)
    # FASE E-0 — konteks final (paling akurat) juga disimpan untuk stempel audit.
    try:
        from request_context import set_active_entity
        set_active_entity(active)
    except Exception:  # noqa: BLE001
        pass
    return EntityContext(user=user, active_entity_id=active,
                         allowed_entity_ids=allowed, view_all=view_all)
# CATATAN: pembangun pesan 403 dipindah ke `services/entity_lifecycle_service.
# entity_denied_message` supaya `dependencies.current_user` (choke point auth)
# bisa memakainya juga tanpa impor melingkar.

# ─── Helper query & tulis ────────────────────────────────────────────────────
def apply_entity_scope(collection: str, query: Optional[Dict[str, Any]], ctx: EntityContext,
                       mode: str = "active") -> Dict[str, Any]:
    """Suntik filter entitas ke query.

    mode="active"  → hanya entitas aktif (default; isolasi ketat).
    mode="allowed" → semua entitas yang diizinkan (dashboard lintas-PT).
    SHARED collection → query tidak disentuh.
    """
    q = dict(query or {})
    fld = field_for(collection)
    if fld is None:
        return q
    if mode == "allowed":
        q[fld] = {"$in": ctx.allowed_entity_ids}
    else:
        q[fld] = ctx.active_entity_id
    return q


def stamp_entity(doc: Dict[str, Any], collection: str, ctx: EntityContext) -> Dict[str, Any]:
    """Set field entitas saat create (jika belum ada)."""
    fld = field_for(collection)
    if fld is not None and not doc.get(fld):
        doc[fld] = ctx.active_entity_id
    return doc


def assert_entity_access(doc: Dict[str, Any], collection: str, ctx: EntityContext) -> None:
    """Cegah akses lintas-entitas (anti-IDOR) untuk GET/{id}."""
    fld = field_for(collection)
    if fld is None or not doc:
        return
    ent = doc.get(fld)
    if ent and ent not in ctx.allowed_entity_ids:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan untuk entitas ini")


def resolve_list_scope(collection: str, query: Optional[Dict[str, Any]], ctx: EntityContext,
                       entity_id_param: Optional[str] = None) -> Dict[str, Any]:
    """Logika scope LIST yang baku & backward-compatible.

    - entity_id_param == "all" & role lintas-entitas → semua entitas diizinkan.
    - entity_id_param eksplisit → harus ∈ allowed (else 403), filter ke entitas itu.
    - tidak ada param → scope ke entitas AKTIF (isolasi default).
    """
    q = dict(query or {})
    fld = field_for(collection)
    if fld is None:
        return q
    if entity_id_param == "all":
        # FASE E-8 — gabungan = SEMUA yang ditugaskan (dulu: hanya peran lintas-PT,
        # sehingga Admin Sales bertugas 2 badan usaha kehilangan data badan usaha
        # keduanya tanpa pesan). `allowed_entity_ids` adalah pagarnya.
        q[fld] = {"$in": ctx.allowed_entity_ids}
    elif entity_id_param:
        if entity_id_param not in ctx.allowed_entity_ids:
            raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas ini")
        q[fld] = entity_id_param
    else:
        if getattr(ctx, "view_all", False):
            q[fld] = {"$in": ctx.allowed_entity_ids}
        else:
            q[fld] = ctx.active_entity_id
    return q


def resolve_scope_ids(ctx: EntityContext, entity_id_param: Optional[str] = None) -> List[str]:
    """Daftar entity_id dalam cakupan baca. Dipakai koleksi yang punya record
    'all' (grup) yang harus selalu terlihat (mis. kas_besar / akun bank grup)."""
    if entity_id_param == "all":
        return list(ctx.allowed_entity_ids)   # FASE E-8 — lihat `can_view_combined`
    if entity_id_param:
        if entity_id_param not in ctx.allowed_entity_ids:
            raise HTTPException(status_code=403, detail="Tidak berwenang atas entitas ini")
        return [entity_id_param]
    if getattr(ctx, "view_all", False):
        return list(ctx.allowed_entity_ids)
    return [ctx.active_entity_id]


# ─── FASE E-0 — helper baru ──────────────────────────────────────────────────
def resolve_list_scope_inherit(collection: str, query: Optional[Dict[str, Any]],
                              ctx: EntityContext,
                              entity_id_param: Optional[str] = None,
                              global_values: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Seperti `resolve_list_scope`, tetapi baris **GLOBAL tetap terlihat**.

    Dipakai koleksi di `INHERITED_GLOBAL_VALUES`: notifikasi sistem (`entity_id`
    None), jejak audit lama, tarif insentif/aturan approval bawaan grup
    (`entity_id="all"`). Tanpa helper ini, memindahkan koleksi SHARED→SCOPED akan
    **menghilangkan** baris global dari layar (regresi diam-diam).
    """
    q = dict(query or {})
    fld = field_for(collection)
    if fld is None:
        return q
    ids = resolve_scope_ids(ctx, entity_id_param)
    if global_values is None:
        global_values = INHERITED_GLOBAL_VALUES.get(collection, [None, ""])
    ent_clause = {"$or": [{fld: {"$in": list(ids)}}, {fld: {"$in": list(global_values)}}]}
    if fld in q:
        # penelepon sudah memfilter field entitas sendiri → hormati, jangan tumpuk
        return q
    if "$and" in q:
        q["$and"] = list(q["$and"]) + [ent_clause]
        return q
    if "$or" in q:
        others = {k: v for k, v in q.items() if k != "$or"}
        return {**others, "$and": [{"$or": q["$or"]}, ent_clause]}
    return {**q, **ent_clause}


def scope_value(ctx: EntityContext, entity_id_param: Optional[str] = None) -> Any:
    """Nilai siap-pakai untuk field entitas: `str` bila satu, `{"$in": [...]}` bila banyak.

    Dipakai service lapis bawah yang menerima "entity_id" apa adanya sehingga tidak
    perlu diubah tanda tangannya satu-satu.
    """
    ids = resolve_scope_ids(ctx, entity_id_param)
    return ids[0] if len(ids) == 1 else {"$in": ids}


def assert_write_entity(ctx: EntityContext, action: str = "membuat data") -> str:
    """Pagar mode "Semua Entitas": TULIS wajib memilih satu entitas (tutup E4).

    Mengembalikan `active_entity_id` bila konteks sah; melempar 409 dengan pesan
    menuntun bila pengguna sedang dalam mode gabungan.
    """
    if getattr(ctx, "view_all", False):
        raise HTTPException(
            status_code=409,
            detail=("Mode \u201cSemua Entitas\u201d hanya untuk melihat. Pilih satu entitas "
                    f"dulu untuk {action}."))
    return ctx.active_entity_id


def resolve_requested_entity(ctx: EntityContext, requested: Optional[str]) -> str:
    """Entitas efektif untuk PRATINJAU/TULIS bila pemanggil menyebut entitas di payload.

    FASE E-0 (L21) — akar masalah kritis: `preview-allocation`/`preview-lots`
    memakai `payload.entity_id` mentah lalu jatuh ke `DEFAULT_ENTITY_ID`, sehingga
    sales CV Kanda dijanjikan stok PT Kain Suka Cita. Aturan barunya:
      * `requested` kosong  → entitas AKTIF dari konteks (bukan default global).
      * `requested` terisi  → wajib ∈ `allowed_entity_ids`, kalau tidak **403**.
    """
    req = (requested or "").strip()
    if req and req != "all":
        if req not in ctx.allowed_entity_ids:
            raise HTTPException(status_code=403,
                                detail="Tidak berwenang atas entitas ini")
        return req
    if req == "all":
        # FASE E-8 — yang menentukan bukan nama peran, tetapi apakah orang ini memang
        # ditugaskan di lebih dari satu badan usaha.
        if not ctx.can_view_combined:
            raise HTTPException(
                status_code=403,
                detail=("Anda hanya ditugaskan di satu badan usaha — tidak ada gabungan "
                        "untuk dilihat."))
        return ctx.active_entity_id
    return ctx.active_entity_id
