# MULTI-ENTITY ARCHITECTURE — Dokumen Acuan Kritikal (F-0 Foundation)

> Status: **CRITICAL — fondasi wajib sebelum fitur sales lanjutan.**
> Tujuan: mengubah sistem dari *single-entity + tempelan `entity_id`* menjadi
> **multi-entity sejati** di mana setiap entitas legal (PT) memiliki staff,
> produk/kepemilikan, pembukuan (GL), pajak, penomoran, konfigurasi insentif,
> dan payroll **yang unik**, namun tetap berbagi platform yang sama dan bisa
> ber-transaksi lintas-entitas (intercompany) bila perlu.
> Referensi kematangan: **NetSuite OneWorld**, **SAP Company Code**, **Odoo
> multi-company + intercompany rules**.

> ### 📌 STATUS IMPLEMENTASI
> - ✅ **F0-A — Entity master & identity (SELESAI 21 Jun 2026)**: `business_entities`
>   di-enrich; `users.home_entity_id`+`allowed_entity_ids`; `services/entity_context_service.py`
>   (`build_entity_context`, `ensure_entity_defaults`, `ensure_user_entities`);
>   `/api/auth/login|me|context` mengembalikan `entity_context` + hormati `X-Entity-Id`
>   dgn isolasi (Model 1). POC 27/0 · gate 119/0/0 · testing_agent 42/42 (iter_50).
> - ✅ **F0-B — Context propagation & data isolation (SELESAI 21 Jun 2026)**:
>   `entity_scope.py` lengkap (`entity_ctx` + `view_all` via header `X-Entity-Id: all`,
>   `resolve_list_scope`, `resolve_scope_ids` utk kas/bank record 'all', `assert_entity_access`).
>   Backend list/GET dokumen komersial ter-scope by-default: purchase_orders, vendor_bills,
>   suppliers, rfqs, purchase_requisitions, sales_returns, special_orders, price_approvals,
>   tax_invoices, input_tax_invoices, ar_receipts, cash_transactions, bank_accounts
>   (+ create stamping entitas aktif, anti-IDOR GET/{id}). FE: `apiClient.setActiveEntity`
>   menyuntik header `X-Entity-Id`, **Entity Switcher** (allowed-only + locked utk single-entity)
>   + sanitasi entitas terpilih saat login. testing_agent 91/91 (iter_51).
>   ⚠️ SENGAJA DITUNDA ke F0-C/F0-E (belum/parsial ter-stamp): wms_tasks, shipments, inventory_*
>   (operasional → F0-C migrasi+gate) & gl_accounts, journal_entries (→ F0-E).
> - ✅ **F0-C — Migrasi + Gate + scoping operasional (SELESAI 22 Jun 2026)**:
>   `scripts/migrate_entity_scoping.py` (backfill idempotent, derive wms←PO/shipments←SO,
>   gl_accounts/audit→ent_ksc, catch-all PRIMARY; auto-run di akhir seed) +
>   `scripts/verify_entity_scoping.py` (GATE: DB-check 0 dok tanpa entitas + STATIC-check router
>   list pakai entity_scope, dgn exemptions terdokumentasi). Scoping operasional: wms_tasks
>   (wms.py, inbound_receiving.py), shipments (outbound_picking.py),
>   inventory_rolls/balances/movements (inventory.py) + create-stamping. GATE LULUS 0 FAIL.
> - ✅ **F0-D — Penomoran per-entitas (SELESAI 22 Jun 2026)**: `next_doc_number(entity_id, scheme)`
>   mode `per_entity_prefix` → sequence atomik per (entity,doc_type) di koleksi `number_sequences`,
>   format `CODE/PREFIX-NNNNN` (KSC/SO-00001, KANDA/PO-00003); seed lazy dari nomor tertinggi
>   existing; `entity_id=None|'all'` → legacy. Diterapkan: SO, PO (semua jalur), AR, FKT, CASH, SJ, JE.
> - ✅ **F0-E — Buku finansial terpisah per-entitas (SELESAI & TERVERIFIKASI 22 Jun 2026)**:
>   GL trial-balance/journal/ledger/summary ter-scope `journal_entries.entity_id` (buku &
>   saldo terpisah per PT, masing-masing seimbang, 'all'=jumlah). **CoA SHARED by-code** —
>   `gl_accounts` direklasifikasi **SHARED** di `entity_scope.py` (keluar dari `SCOPED_COLLECTIONS`,
>   `SCOPE_FIELD["gl_accounts"]=SHARED`); migrate tak lagi stamp gl_accounts; gate `verify_entity_scoping`
>   DB-CHECK HIJAU tanpa false-fail. **Reporting per-entitas** (`routers/reporting.py`): 6 endpoint pakai
>   `entity_ctx`+`resolve_list_scope` (sales_orders→entity_id, inventory→owner_entity_id) — invarian
>   aditif **ksc+kanda==all** terbukti; exemption gate `→ F0-E` dihapus. **Insentif→GL (Model 1)**:
>   akun `6-5000 Beban Insentif Penjualan` + `2-1500 Hutang Insentif Penjualan`;
>   `gl_service.post_incentive_accrual(entity,period)` idempotent (Dr Beban / Cr Hutang di buku
>   entitas SO) + `incentive_accrual_status`; `POST /api/crm/sales/incentive/post-gl` &
>   `GET /api/crm/sales/incentive/gl-status` (RBAC manager/admin; sales 403; 'all' 400);
>   FE panel `sf-incentive-gl` di `SalesForceDashboard.jsx`. PKP per-entitas via `config_service`
>   (ent_ksc PPN 11%, ent_kanda non-PKP 0%). JE ter-stamp & ber-nomor per entitas (KSC/JE-…, KANDA/JE-…).
>   Bukti: seed_reset 4/4 HIJAU · health_check 0 FAIL · sweep 0×5xx · testing_agent iter_63 BE 38/39
>   (1 = path typo test-script, bukan bug) + FE 0 console error.
> - ✅ **F0-F — Provisioning entitas baru (SELESAI 22 Jun 2026)**:
>   `services/entity_provisioning_service.py` (validasi short_name/doc_prefix unik, auto-slug
>   doc_prefix, default config, CoA shared idempotent) via `POST /api/entities` (UI: Admin→Entities).
>   Entitas baru langsung switchable (allowed dinamis utk role cross-entity).
>   testing_agent F0-C/D/E/F **64/64 PASS** (iter_52).
>
> 🎉 **FASE F0 (MULTI-ENTITY FOUNDATION) SELESAI 100%** — siap lanjut ke F1+.
> Enhancement: **EntityBadge** (pill berwarna per PT) di list Orders/Suppliers/Vendor-Bills.
>
> ### 📌 F1a + KONSOLIDASI (22 Jun 2026)
> - ✅ **F1a Pricelist per-Entitas**: koleksi `entity_prices` (SCOPED via `entity_id`), harga jual
>   per-PT dengan **histori & tanggal efektif** (`valid_from`/`valid_until`). `services/pricelist_service.py`
>   (`resolve_sell_price`/`resolve_many` = ambil record aktif valid_from terbesar, fallback `products.price`).
>   Router `/api/pricelist` (grid/records/CRUD). Integrasi: `sales_orders.create_order` (harga item ikut
>   entitas penjual) & `products.list_products` (`global_price`+`price_source`). RBAC modul `pricelist`.
>   UI `features/sales/PricelistView.jsx`. testing_agent iter_53 16/16.
> - ➕ **Dashboard Konsolidasi Grup vs Per-PT**: `gl_service.consolidation()` + `GET /api/gl/consolidation`
>   (cakupan = `ctx.allowed_entity_ids`; baris 'Grup/Kas Bersama' utk jurnal entity_id='all'). UI
>   `features/finance/ConsolidationDashboard.jsx` (toggle Gabungan vs Per-PT). Cleanup: 3 entitas uji
>   F0-F kosong dihapus.

---

## 0. RINGKASAN TEMUAN (grounded — hasil audit kode/DB, 21 Jun 2026)

| Aspek | Kondisi sekarang | Implikasi |
|---|---|---|
| `business_entities` (master) | **2 record STUB**: `ent_ksc`, `ent_kanda` — `name=null`, `is_pkp=null` | 🔴 PPN per-entitas tak valid (PPN ikut PKP entitas) |
| `users` | **TIDAK punya `entity_id`** | 🔴 Insentif/payroll/achievement per-entitas mustahil |
| Penomoran dok | `next_doc_number` **global per-prefix** (tak sadar entitas) | SO-/PO-/JE- nomor dipakai bersama lintas-PT |
| Config | `system_settings` **1 dok global**, `permission_settings` **1 matrix** | Tak ada override per-entitas (tax/insentif/approval) |
| GL/Buku | `gl_accounts` **tanpa entity_id**; trial-balance **agregasi semua entitas** | 🔴 Bukan buku terpisah per-PT (wajib untuk legal) |
| Konvensi scope | **3 macam**: `entity_id`, `owner_entity_id` (inventory), none | Inkonsistensi → query rawan bocor lintas-entitas |
| Drift | `purchase_orders` 6/11, `audit_logs` 4/10 ter-stamp | Sebagian transaksi tak ber-entitas |
| Master belum scoped | products, product_categories, warehouses, payment_terms, uoms, wms_tasks, shipments, gl_accounts | Ambiguitas kepemilikan & isolasi |

**Kesimpulan:** sistem **belum** multi-entity sejati. Fondasi harus diperbaiki
lebih dulu, dengan **mekanisme terpusat** agar semua modul (sekarang & nanti)
otomatis sadar-entitas, dan dengan **3 script khusus** (migrasi, provisioning,
gate kepatuhan).

---

## 1. PRINSIP DESAIN

1. **Single database, discriminator `entity_id`** (pola "multi-company in one DB"
   ala Odoo/SAP) — bukan multi-tenant DB terpisah. Lebih sederhana, mendukung
   intercompany & konsolidasi, sesuai skala bisnis ini.
2. **Satu sumber kebenaran konteks entitas** — *active entity* di-resolve di SATU
   tempat (dependency backend + interceptor frontend), bukan diulang per-modul.
3. **Scope-by-default, share-by-exception** — semua dokumen transaksi entity-scoped
   secara default; hanya master tertentu yang sengaja dibagikan (lihat §3).
4. **Config = global default + entity override** (resolver merge; entitas menang).
5. **Provisioning otomatis** — menambah entitas = wizard yang menyiapkan seluruh
   footprint (CoA, sequence, config, staff, gudang, approval, insentif).
6. **Enforceable** — kepatuhan entitas dijaga **gate statis/dinamis** (anti-regresi),
   bukan sekadar konvensi.
7. **Backward-compatible & idempotent** — migrasi data lama aman diulang.

---

## 2. TAKSONOMI ENTITAS (model legal & relasi)

```
business_entities (entitas legal = unit pembukuan)
├── id, code (KSC/KND), name, legal_name, npwp, is_pkp, currency
├── parent_entity_id  (untuk grup/konsolidasi; "" = top)
├── is_group (bool)   (entitas "holding"/konsolidasi virtual)
├── status (active|inactive)
└── profil & default (lihat §4)
```

- **Entitas operasional** = PT nyata (punya buku, staff, transaksi).
- **Entitas grup (opsional)** = simpul konsolidasi (laporan gabungan, tidak
  bertransaksi). Disiapkan slot-nya sekarang, implementasi konsolidasi = fase lanjut.
- **Intercompany** = transaksi yang menyentuh 2 entitas (mis. transfer antar-PT,
  jual-beli internal) → menghasilkan **pasangan jurnal** di kedua buku.

---

## 3. KLASIFIKASI KOLEKSI (Scope Registry) — artefak paling penting

Setiap koleksi diklasifikasikan; ini menjadi **kontrak** yang dipakai helper
scoping & gate kepatuhan (§7, §8).

### 3.1 SCOPED — entity-owned, WAJIB `entity_id` + filter aktif
`sales_orders, sales_returns, sales_incentives, sales_targets, special_orders,
price_approvals, ar_receipts, cash_transactions, bank_accounts, journal_entries,
gl_accounts*, tax_invoices, purchase_orders, purchase_requisitions, purchase_returns,
supplier_price_lists, incentive_rates, customers, notifications, audit_logs,
shipments*, wms_tasks*`
(*) = saat ini belum/parsial ter-stamp → diperbaiki migrasi.

### 3.2 INVENTORY — scope via `owner_entity_id` (semantik kepemilikan, dukung konsinyasi)
`inventory_rolls, inventory_balances, inventory_movements`
→ Registry mencatat field scope-nya `owner_entity_id` (bukan `entity_id`). Helper
scoping membaca registry agar query tetap benar. `ownership_type` membedakan
milik-sendiri vs konsinyasi.

### 3.3 CONFIG-OVERRIDE — global default + override per-entitas
`system_settings, permission_settings, payment_terms, approval_rules, number_sequences`
→ Pola: dokumen `scope:"global"` (default) + `scope:"entity", entity_id:X` (override).
Resolver: `resolve_config(section, entity_id)` = merge(global, entity).

### 3.4 SHARED MASTER (default global) — **KEPUTUSAN OWNER diperlukan**
`uoms, document_templates` → global.
`products, product_categories, warehouses, suppliers` → **rekomendasi hibrida** (§3.6).

### 3.5 IDENTITY
`users` → tambah `home_entity_id` (entitas tempat bernaung/payroll) +
`allowed_entity_ids[]` (entitas yang boleh ia operasikan).
`sessions` → simpan `active_entity_id`.

### 3.6 KEPUTUSAN KATALOG PRODUK (rekomendasi desain terbaik)
Bisnis kain sering punya **SKU yang sama dipakai beberapa PT**, tetapi
**stok, harga, listing, dan kepemilikan tetap per-PT**. Rekomendasi:

> **Definisi produk = master bersama (template + variant); kepemilikan/listing =
> per-entitas.**

Implementasi: `product_templates` (definisi: nama, kategori, atribut warna/motif/
grade/lebar/gramasi — lihat dokumen Variant) + `products` (variant ber-SKU) yang
**global definisinya**, lalu lapisan **`entity_products`** (listing per-entitas:
`entity_id, product_id, is_listed, sell_price, harga_pokok/WAC, reorder_point`).
Stok (`inventory_rolls`) tetap `owner_entity_id` → kepemilikan per-PT.

Alternatif sederhana (jika owner mau "produk benar-benar milik 1 entitas"):
tambahkan `entity_id` langsung di `products` (duplikasi SKU antar-PT bila perlu).

→ **KEPUTUSAN OWNER (D1):** (a) shared-definition + per-entity listing *(disarankan)*
atau (b) products fully per-entity.

---

## 4. SKEMA ENTITAS LENGKAP (`business_entities`)

```
id                 string  "ent_ksc"
code               string  "KSC"            (dipakai di nomor dokumen)
name               string  "PT Kain Suka Cita"
legal_name         string
npwp               string
is_pkp             bool                     (driver PPN)
ppn_rate           float   0.11
currency           string  "IDR"
address            object  {street,city,province,postal}
logo               string  (url/base64)
status             enum    active|inactive
parent_entity_id   string  ""               (konsolidasi)
is_group           bool    false
# default operasional (dipakai provisioning & resolver):
fiscal_year_start  string  "01-01"
default_payment_term_code  string  "NET30"
coa_template       string  "id_standard"    (template CoA saat provisioning)
numbering_scheme   enum    per_entity_prefix | shared   (lihat §5)
# insentif/payroll:
incentive_payer    enum    selling_entity | home_entity  (lihat §6.3)
commission_strategy object  (override commission section)
created_at/updated_at/created_by
```

---

## 5. PENOMORAN DOKUMEN PER-ENTITAS

**Masalah:** `next_doc_number` global → nomor tabrakan/ambiguitas antar-PT.

**Solusi:**
- Refactor → `next_doc_number(collection, field, prefix, entity_id=None, scheme=...)`.
- Koleksi SCOPED memakai **sequence per (entity_id, doc_type)** disimpan di koleksi
  baru **`number_sequences`** (`{entity_id, doc_type, prefix, last_no}`) — atomik
  via `find_one_and_update($inc)` (deterministik, anti-duplikat, hemat scan).
- Format nomor: **`{ENTITYCODE}/{PREFIX}{NNNNN}`** mis. `KSC/SO-00001`, `KND/SO-00001`
  (scheme `per_entity_prefix`, disarankan) — antar-PT tak tabrakan & mudah dibaca.
- Backward-compat: scheme `shared` mempertahankan perilaku lama untuk data legacy.

---

## 6. FINANCE, PAJAK, INSENTIF PER-ENTITAS

### 6.1 GL/Buku terpisah per entitas
- `gl_accounts` mendapat `entity_id` → **setiap entitas punya CoA sendiri**
  (di-seed dari `coa_template` saat provisioning).
- Endpoint GL (`trial-balance, journal, ledger, summary`) **WAJIB** menerima &
  memfilter `entity_id` (perbaiki gap EPIC7-C yang sekarang mengagregasi semua).
- Auto-posting (sales_order, cash_transaction) memposting ke **buku entitas dokumen**.
- **Konsolidasi grup** (laporan gabungan + eliminasi intercompany) = fase lanjut,
  tapi struktur (parent_entity_id) sudah disiapkan.

### 6.2 Pajak
- `is_pkp` & `ppn_rate` **per-entitas** → pricing engine membaca dari entitas penjual
  pada SO (sudah ada hook `is_pkp`, tinggal sumber datanya dibuat valid).
- Faktur Pajak Jual/Masukan ter-scope entitas (sudah `entity_id`).

### 6.3 Insentif & Payroll — siapa membayar?
Dua peran berbeda:
- **home_entity** = entitas tempat sales dipekerjakan (payroll, kontrak kerja).
- **selling_entity** = entitas penjual pada SO (yang membukukan pendapatan).

**Aturan default (rekomendasi):** **biaya insentif ditanggung `selling_entity`**
(entitas yang menikmati penjualan) → jurnal di buku selling_entity:
`Dr Beban Insentif Penjualan, Cr Hutang Insentif/Kas`. **Payroll** (gaji pokok)
ditanggung **home_entity**. Ini menghindari subsidi silang antar-PT.
→ **KEPUTUSAN OWNER (D2):** `incentive_payer = selling_entity` *(disarankan)* atau `home_entity`.

`incentive_rates` sudah entity-scoped (entity × kategori, fallback "all") — cukup;
tambahkan resolusi payer + posting ke GL entitas terkait.

---

## 7. MEKANISME "SEMUA MODUL SADAR-ENTITAS" (inti pertanyaan Anda)

Agar modul **sekarang & masa depan** otomatis entity-aware **tanpa menulis ulang
logika di tiap router**, dibuat **lapisan terpusat**:

### 7.1 Backend — `EntityContext` dependency (resolusi 1 pintu)
```
async def entity_ctx(request) -> EntityContext:
    user = await current_user(request)
    requested = request.headers.get("X-Entity-Id")          # active entity dari FE
    allowed = user["allowed_entity_ids"] or [user["home_entity_id"]]
    active = requested if requested in allowed else (user.get("home_entity_id") or allowed[0])
    return EntityContext(active_entity_id=active, allowed_entity_ids=allowed, user=user)
```
- Admin/role tertentu boleh `allowed = SEMUA entitas` (super-scope) + mode "cross-entity".

### 7.2 Backend — helper scoping (membaca Scope Registry §3)
```
ENTITY_FIELD = {"inventory_rolls":"owner_entity_id", ... , "<default>":"entity_id"}

def scope_query(collection, base_query, ctx, mode="active"):
    field = ENTITY_FIELD.get(collection, "entity_id")
    if mode == "active":   base_query[field] = ctx.active_entity_id
    elif mode == "allowed": base_query[field] = {"$in": ctx.allowed_entity_ids}
    return base_query                                   # SHARED → tidak disentuh

def stamp_entity(doc, ctx, collection):
    field = ENTITY_FIELD.get(collection, "entity_id")
    doc.setdefault(field, ctx.active_entity_id); return doc
```
- **Semua endpoint list/read** memakai `scope_query`; **semua create** memakai
  `stamp_entity`. → modul baru cukup pakai helper = otomatis patuh.
- POS "cross-entity" memakai `mode="allowed"` + filter UI per entitas.

### 7.3 Frontend — active entity + switcher
- `EntityContext` (React) menyimpan `activeEntity` + `allowedEntities` (dari `/auth/me`).
- **apiClient interceptor** menyuntik header `X-Entity-Id: <activeEntity>` di tiap request.
- **Entity Switcher** di top-bar (untuk user multi-entitas). POS punya **filter entitas**
  (default active, bisa "semua yang diizinkan").
- Komponen menampilkan **badge entitas** pada dokumen (SO/PO/Invoice) agar tak keliru.

### 7.4 Config resolver
```
async def resolve_config(section, ctx):
    g = await db.system_settings.find_one({"scope":"global"})
    e = await db.system_settings.find_one({"scope":"entity","entity_id":ctx.active_entity_id})
    return deep_merge(g.get(section,{}), (e or {}).get(section,{}))   # entity menang
```

---

## 8. TIGA SCRIPT KHUSUS (jawaban "apakah perlu script khusus?" → YA)

### (A) `scripts/migrate_entity_scoping.py` — migrasi/backfill 1×, idempotent
- Stamp `entity_id` = `ent_ksc` (default legacy) pada koleksi NO-ENTITY/PARTIAL
  (products→entity_products bila pilih hibrida; gl_accounts, warehouses, wms_tasks,
  shipments, purchase_orders drift, audit_logs drift).
- Rekonsiliasi `owner_entity_id` ↔ registry (inventory).
- Validasi: setelah migrasi, **0 dokumen SCOPED tanpa field entitas**.
- Aman diulang (cek sebelum set), punya mode `--dry-run` & laporan.

### (B) `services/entity_provisioning_service.py` — "Add New Entity" (provisioning)
Dipakai oleh `POST /api/entities` (wizard) **dan** seed. Saat entitas dibuat,
otomatis menyiapkan footprint operasional (transaksional & idempotent):
1. **CoA** dari `coa_template` (mis. seed 35 akun standar untuk entitas itu).
2. **number_sequences** awal (SO/PO/JE/INV/…); set `numbering_scheme`.
3. **Config override** default (tax PKP, ppn_rate, default_payment_term, approval
   thresholds, commission/incentive strategy) — inherit global bila kosong.
4. **Permission matrix** (inherit global, boleh override).
5. **Gudang default** (opsional) + **payment_terms** (inherit).
6. **Assign staff awal**: admin memilih user → set `allowed_entity_ids`/`home_entity_id`.
7. **incentive_rates** default (inherit "all" atau template).
→ Output: entitas siap bertransaksi. Wizard UI multi-langkah memandu owner.

### (C) `scripts/verify_entity_scoping.py` — GATE kepatuhan (anti-regresi)
Gate baru (sejajar `verify_contract`/`verify_api_contract`) yang **meng-enforce**:
- Setiap koleksi SCOPED: **0 dokumen** tanpa field entitas (cek DB).
- Setiap router list/read pada koleksi SCOPED **memakai `scope_query`** (cek statis
  AST/grep pola) — modul yang tak patuh → FAIL.
- Tidak ada endpoint yang mengembalikan data lintas-entitas tanpa `mode="allowed"`.
- Scope Registry (§3) sinkron dengan koleksi nyata (anti-drift, mirip L0 EPIC7-C).
→ Dijalankan di `seed_reset`/CI tiap fase → **modul baru wajib lulus** = jaminan
semua modul tetap sadar-entitas selamanya.

---

## 9. STRATEGI MIGRASI DATA LAMA

1. Lengkapi 2 entitas stub (`ent_ksc`, `ent_kanda`) → isi name/npwp/is_pkp/currency.
2. Jalankan `migrate_entity_scoping.py` (default semua legacy → `ent_ksc`,
   kecuali yang sudah `ent_kanda`).
3. Set `home_entity_id` semua user (admin/manager → allowed semua; sales → 1 entitas).
4. Seed `number_sequences` dari nomor tertinggi existing per entitas (lanjutkan, tak reset).
5. `gl_accounts` di-clone per entitas dari template; re-post jurnal per entitas (idempotent).
6. Verifikasi via gate (C) → 0 FAIL.

---

## 10. KEAMANAN / ISOLASI

- **Row-level isolation**: read ⊆ `allowed_entity_ids`; tulis ter-stamp `active`.
- **Anti-IDOR lintas-entitas**: `GET /resource/{id}` memverifikasi entitas dokumen ∈ allowed.
- **Audit** mencatat `entity_id` + actor.
- **Super-scope** (admin grup) eksplisit & ter-audit.

---

## 11. ROADMAP IMPLEMENTASI (F-0 dipecah; tiap sub-fase = gate hijau + POC + testing_agent)

| Sub-fase | Isi | DoD |
|---|---|---|
| **F0-A — Entity master & identity** | Lengkapi skema `business_entities` + CRUD kaya; `users.home_entity_id`+`allowed_entity_ids`; `/auth/me` mengembalikan entitas; seed 2 entitas valid + assign staff. | Entitas punya profil lengkap; tiap user ber-entitas. POC: login→me→entitas benar. |
| **F0-B — Context propagation** | `EntityContext` dependency + `scope_query`/`stamp_entity` + Scope Registry; FE `EntityContext`+interceptor `X-Entity-Id`+**Entity Switcher**+badge. | Semua list ter-scope; switcher berfungsi; cross-entity POS mode. |
| **F0-C — Migrasi + gate** | `migrate_entity_scoping.py` + `verify_entity_scoping.py` (gate); stamp semua koleksi SCOPED; perbaiki drift PO/audit. | Gate (C) 0 FAIL; 0 dokumen SCOPED tanpa entitas. |
| **F0-D — Numbering per-entitas** | `number_sequences` + refactor `next_doc_number(entity_id)`; format `CODE/PREFIX`. | Nomor unik per entitas; anti-duplikat. |
| **F0-E — Finance per-entitas** | `gl_accounts.entity_id` + GL endpoint filter entitas + auto-posting ke buku entitas + tax PKP per-entitas + insentif payer→GL. | Trial balance per-entitas seimbang; PPN ikut PKP entitas; insentif terbukukan di payer benar. |
| **F0-F — Provisioning "Add Entity"** | `entity_provisioning_service.py` + wizard UI multi-langkah (CoA, sequence, config, staff, gudang, insentif). | Owner bisa **tambah entitas baru** end-to-end & langsung bertransaksi. |

Setelah F-0 tuntas → lanjut F-1 (pricelist/diskon governance, varian), F-2 (stock
multi-bucket + pending SO), dst. (lihat `plan.md`).

---

## 12. KEPUTUSAN OWNER — TERKUNCI (✅ disetujui 21 Jun 2026)

- **D1 Katalog produk = SHARED definition + ownership per-entitas.** 1 SKU sama bisa
  dipakai banyak PT; **kepemilikan dilekatkan di STOK** via `owner_entity_id` yang
  **auto-distamp dari entitas pembeli saat purchasing/receiving**. WAC otomatis
  per-entitas (beli sendiri). **Harga jual per-entitas (D2a)** → pricelist per-entitas.
- **D-Model = MODEL 1 (silo selling).** Tiap sales **menjual untuk entitas-nya
  sendiri**; SO selalu dibukukan atas nama entitas sales. Stok PT lain **hanya** via
  **transfer antar-PT (intercompany)** lebih dulu, lalu dijual. → `selling_entity ==
  home_entity` SELALU. Konsekuensi besar: **tidak ada konflik penjual-vs-majikan**,
  intercompany **tidak terjadi di POS** (hanya di modul transfer/gudang).
- **D3 Insentif** = ditanggung **entitas tempat sales bekerja** (= entitas SO di
  Model 1) → jurnal **beban insentif di buku entitas itu**. Payroll juga per-entitas (HR per-PT).
- **D4 Penomoran** = **per-entitas dgn kode**, format `CODE/PREFIX-NNNNN` (mis. `KSC/SO-00001`).
- **D5 Laporan** = **buku per-PT terpisah + transfer antar-PT dulu**; **konsolidasi grup
  + eliminasi intercompany = sub-fase lanjut (F0-G/H)**, struktur (`parent_entity_id`) disiapkan sekarang.

### Implikasi Model 1 ke identitas & insentif (mengganti §3.5 & §6.3)
- **User identity:** setiap user punya `home_entity_id` (entitas kerja/payroll).
  - **sales & warehouse** → `allowed_entity_ids = [home]` (terkunci 1 entitas; active entity = home, tak bisa switch saat jualan).
  - **manager & admin** → `allowed_entity_ids = SEMUA` (oversight lintas-PT) + **entity switcher** untuk memilih konteks aktif (lihat/kelola), tapi tetap, **SO selalu atas entitas sales pembuatnya**.
- **Insentif payer** = `sales_order.entity_id` (= entitas sales). Tak perlu logika selling-vs-home (selalu sama). Jurnal: di buku entitas SO, `Dr Beban Insentif, Cr Hutang Insentif/Kas`.
- **Cross-entity HANYA di transfer/gudang** → butuh **intercompany transfer** (roll `owner_entity_id` A→B + sepasang jurnal) = sub-fase F0-G.

## 13. RISIKO & MITIGASI
- **Refactor luas** → mitigasi: helper terpusat + gate kepatuhan + migrasi idempotent + per sub-fase ada testing_agent.
- **Regresi data lama** → `--dry-run` + backup koleksi + gate 0 FAIL sebelum lanjut.
- **Kebocoran lintas-entitas** → row-level isolation + gate statis + uji negatif (user entitas A tak bisa baca dok entitas B).

---
*Dokumen ini = acuan tunggal pengembangan multi-entitas. Setiap PR fase F-0 wajib
merujuk & memperbarui dokumen ini bila ada perubahan keputusan/desain.*
