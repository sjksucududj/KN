# RENCANA EKSEKUSI — FONDASI MULTI-ENTITAS (Pengaturan Entitas · Pemilihan · Akun · Isolasi Data)

> **Sesi ini = VERIFIKASI SAJA. TIDAK ADA KODE FITUR YANG DIUBAH.**
> Rencana ini ditulis agar agen sesi berikutnya bisa langsung eksekusi tanpa menelusuri ulang.
> Plan sebelumnya (D-14 / Daftar Harga per Pelanggan — sudah selesai) diarsipkan ke
> `.logs/plan_archive_pre_ENTITAS.md`.
>
> **Bukti & temuan:** `AUDIT_ISOLASI_ENTITAS.md` (isolasi data) · `AUDIT_ENTITAS_2026-08-10.md`
> (pengaturan entitas & akun). **Alat audit:** `scripts/entity_audit/` (5 skrip, lihat §7).
> **Kredensial uji:** `memory/test_credentials.md` (semua akun demo password `demo12345`).

---

## 0) KONTEKS BISNIS (dari pemilik, jangan ditafsir ulang)

Multi-entitas di sini **bukan** multi-tenant SaaS. Ini **satu perusahaan** dengan **proses bisnis
identik**, dipecah menjadi beberapa **badan usaha** karena:
- perhitungan keuangan berbeda (buku, pajak, PKP/non-PKP),
- harga jual berbeda,
- basis pelanggan berbeda.

Konsekuensi yang WAJIB dipegang:
1. **Karyawan** bisa ditugaskan ke 1 entitas (tidak boleh lihat entitas lain **sama sekali**)
   atau ke >1 entitas (boleh berpindah, tetapi data tidak boleh tercampur).
   **Entitas karyawan bersumber dari modul HR** (`hr_employees.entity_id`) — bukan diketik ulang.
2. **Master data bersama** (produk, kategori, UOM, warna) tetap satu.
   **Semua transaksi & keuangan terpisah** per entitas (SO, PO, faktur, kas, jurnal, piutang).
3. **Jenis entitas bukan hanya PT** — bisa CV, **perorangan**, UD, koperasi, yayasan.
   NPWP boleh kosong (perorangan), PKP menyusul status pajaknya sendiri.
4. Jumlah entitas **bisa bertambah sampai puluhan** → UI wajib skalabel (cari, filter, paging).
5. **Pengaturan/konfigurasi sistem harus per entitas** dan UI-nya harus jelas dari mana nilai
   berasal (global vs entitas) — tidak boleh menyesatkan.

### Keputusan pemilik (jawaban verifikasi, verbatim ringkas)
| # | Pertanyaan | Keputusan |
|---|---|---|
| 1 | Sales lihat stok PT lain? | Sales lihat **detail stok entitasnya sendiri** + **angka global (agregat)**. **Detail per-entitas hanya di sisi admin/admin-sales.** (Pembagian domain sales vs admin sales sudah dibahas & dikunci — lihat FASE E-8.) |
| 2 | Semua modul pinggir wajib per-entitas? | **Ya.** Jejak audit: **opsi (a)** → **hanya admin**, dan **hanya entitas yang sedang aktif**. |
| 3 | Gudang | **(c) Campur** — ada gudang bersama, ada gudang khusus entitas tertentu. |
| 4 | Harga | **(a)** Harga master global + **override per entitas**; UI override **harus jelas**, dan nilai yang berasal dari global **wajib berlabel**. |
| 5 | Nomor dokumen | **(a)** Semua dokumen **wajib ber-prefix entitas**. Dokumen demo lama **dihapus**; **seed disesuaikan**. |
| 6 | Master/konfigurasi yang masih bersama | **Semuanya harus per entitas.** |
| + | Karyawan lintas-entitas | Ikuti pendaftaran di **HR** (`hr_employees.entity_id`) — termasuk gaji/insentif. |
| + | Pelanggan sama di 2 entitas | Dibiarkan apa adanya (record terpisah). **Tanpa** perlakuan khusus. Database pelanggan **tidak** dibagi. |

### Peran & domain kerja (keputusan pemilik — dipakai FASE E-8)
Sistem sekarang hanya punya 4 peran; akan menjadi **6**:
`admin` · `manager` · **`sales_admin` (baru)** · **`finance` (baru)** · `sales` · `warehouse`.

| Peran | Domainnya |
|---|---|
| **Sales (lapangan)** | Jual barang · basis pelanggan sendiri · buat SO · **lihat perjalanan pesanan** · **hanya SO miliknya** · **mengajukan retur**. Tidak mengurus operasional/manajemen, tidak menyentuh uang & pajak |
| **Admin Sales** | Pemilik alur SO **end-to-end**: verifikasi kelengkapan → **keputusan pemenuhan** (stok sendiri · **ambil dari PT lain** · **reorder ke supplier** · pegging, **tanpa** persetujuan manajer) → **konfirmasi SO** → dokumen (SJ/Invoice) → **memproses retur** yang diajukan sales · boleh menandai barang diterima. **Berbasis penugasan entitas** (1 atau beberapa PT) |
| **Finance / Kasir** | **Uang masuk (kwitansi AR)** · **Faktur Pajak keluaran** · selisih bayar (dalam batas config) · terbitkan denda · rencana pembayaran. Tidak membuat/mengonfirmasi SO |
| **Manager** | **Keputusan**: harga khusus · kredit · SO bernilai besar · persetujuan retur · pembebasan denda · settlement antar-PT · target & insentif |
| **Gudang** | Picking · packing · kirim · terima barang (termasuk barang antar-PT) · boleh menandai barang diterima |
| **Admin sistem** | Entitas · pengguna · master data · konfigurasi · izin |

Hirarki wewenang: `sales:1 · warehouse:1 · sales_admin:2 · finance:2 · manager:3 · admin:4`.

---

## 1) KONDISI FAKTUAL SISTEM (hasil verifikasi, dengan bukti)

### 1.1 Yang sudah BENAR (jangan dirusak saat refactor)
- `backend/entity_scope.py` — lapisan scoping terpusat: registry `SCOPE_FIELD`/`SCOPED_COLLECTIONS`,
  dependency `entity_ctx`, `resolve_list_scope`, `stamp_entity`, `assert_entity_access`.
- `services/entity_context_service.py` — `build_entity_context` (home/allowed/active), role
  lintas-entitas `{admin, manager}`, resolusi dinamis untuk admin/manager.
- Isolasi TERBUKTI (sales KSC vs sales Kanda): pelanggan 4↔1 · supplier 4↔2 · SO 8↔1 · PO 9↔4 ·
  mutasi stok 41↔2 · neraca saldo Rp 981.324.092 ↔ Rp 46.599.692 · kas kecil Rp 7,75 jt ↔ Rp 3,8 jt ·
  omzet bulan Rp 79,25 jt ↔ Rp 0 · karyawan/makloon/kontrak/harga-pelanggan terisi ↔ 0.
- Anti-IDOR terbukti 403/404: `sales-orders/{id}`, `purchase-orders/{id}`, `ar-receipts/{id}`,
  `sales-returns/{id}`, `suppliers/{id}`, `products/{id}/purchase-history`,
  `purchase-returns/source-rolls`, `uom-conversions/usage`.
- `X-Entity-Id: all` dari sales/gudang **diabaikan** (tetap entitasnya).
- Bagan akun bersama by-code + buku besar terpisah per entitas → trial balance benar per entitas.
- POC lama `backend/test_f0c_scoping_leak_poc.py` → **28 PASS / 0 FAIL**.

### 1.2 CACAT yang harus ditutup (semua sudah dibuktikan)

**A. Kebocoran lintas-entitas**
| Kode | Endpoint / berkas | Bukti | Akar masalah |
|---|---|---|---|
| L1 | `GET /api/notifications` (`routers/notifications.py`) | sales Kanda menerima `ntf_9f2bdb658c61` "Order menunggu persetujuan: SO-0007" (`entity_id=ent_ksc`) | `notifications` = SHARED di registry; filter hanya per user/role |
| L2 | `GET /api/payment-plans` | sales Kanda melihat 2/2 rencana KSC | tanpa `resolve_list_scope` |
| L3 | `GET /api/payment-variances` | sales Kanda melihat 4/4 keputusan KSC | idem |
| L4 | `GET /api/penalties` | sales Kanda melihat `pnl_3bddc1591159` (KSC) | idem |
| L5 | `GET /api/sales-targets` | target lintas-entitas terlihat | idem |
| L6 | `GET /api/sales-incentives` | insentif lintas-entitas terlihat | idem |
| L7 | `GET /api/audit-logs` (`routers/audit.py:14`) | **sales & gudang** membaca 66 baris jejak SELURUH grup | gerbang salah `require_permission("product","view")` + tanpa scope |
| L8 | `GET /api/lots/{id}` (`routers/lots.py`) | sales KSC buka lot Kanda → **200** | daftar ter-scope, detail tidak (`assert_entity_access` tidak dipakai) |
| L9 | `GET /api/ar/aging` (`routers/ar_aging.py:22`) | `entity_id` selalu `"all"`; total identik Rp 20.260.900 untuk KSC/KANDA/ALL | `aging_report(entity_id=None)` — konteks header tidak dibaca |
| L10 | `GET /api/settings/effective` (`routers/settings.py:29` → `services/config_service.py:202`) | header `X-Entity-Id=ent_kanda` → PPN 12% & `is_pkp=true`; `?entity_id=ent_kanda` → PPN 0% & `is_pkp=false` | endpoint tidak membaca `entity_ctx` |
| L11 | `hr_org_units` | 12 baris menunjuk entitas **yang sudah dihapus** (`ent_f39d5cfe1728`) | bootstrap menanam divisi per entitas aktif; tak ada pembersihan saat entitas hilang |
| L12 | `sales_targets`/`sales_incentives` | milik **Citra Lestari (sales Kanda)** tapi `entity_id=ent_ksc` | stempel salah di `seed_realistic.py` |

**A-lanjutan. Kebocoran & drift yang ditemukan pada verifikasi ANTAR-ENTITAS (2026-08-10, sesi yang sama)**
> Rincian & bukti: `AUDIT_ANTAR_ENTITAS.md`. Semuanya masuk lingkup **FASE E-0**.

| Kode | Temuan | Bukti / berkas |
|---|---|---|
| L13 | **`/api/transfers*` tanpa scoping entitas sama sekali** (list, detail, approve, reject, status, delete) | `routers/transfers.py:39,289,313,409,453,522`; gudang KSC membuka `TRF-00003` dengan konteks Kanda → **200** |
| L14 | `warehouse_transfers` **tidak terdaftar** di `SCOPED_COLLECTIONS`; 2 dari 5 dokumen (yang antar-PT) **tanpa `entity_id`** | pemindaian registry↔DB |
| L15 | **18 koleksi ber-`entity_id` tidak terdaftar** di registry (bukan SCOPED, bukan SHARED): `approval_rules`, `audit_logs`, `budgets`, `credit_notes`, `cycle_count_sessions`, `fin_budget_rules`, `payment_plans`, `payment_variance_decisions`, `penalties`, `purchase_returns`, `rfid_reads`, `rfid_tags`, `rnd_person_divisions`, `sales_incentives`, `sales_targets`, `supplier_price_lists`, `tax_invoices_in`, `warehouse_transfers` | skrip statik |
| L16 | **Drift nama koleksi**: registry mendaftarkan `input_tax_invoices` (tak ada di DB); data nyata di **`tax_invoices_in`** → faktur pajak masukan tak dijaga registry | registry↔DB |
| L17 | Pemindaian 52 router: **6 TANPA scoping** (`admin.py`, `documents.py`, `incentive_rates.py`, `landed_cost.py`, `payment_variance.py`, `pegging.py`) + **5 PARSIAL** (`crm.py`, `cycle_count.py`, `products.py`, `return_policies.py`, `transfers.py`) | skrip statik |
| L18 | **Cetak dokumen lintas-entitas**: `GET /api/documents/preview/{order_id}` → sales Kanda mencetak Surat Jalan `SO-0007` milik KSC (200, HTML lengkap) | empiris |
| L19 | **Jejak dokumen lintas-entitas**: `GET /api/documents/trace/sales_order/{id}` → sales KSC melihat `SO-0002` Kanda + nama pelanggannya | empiris |
| L20 | **RBAC keuangan longgar**: role **gudang** membaca saldo antar-PT (`/interco/accounts`), pelunasan (`/interco/settlements`), dan **laporan margin** (`/interco/margin-report`) → 200 | empiris |

**B. Pengaturan entitas & akun**
| Kode | Masalah | Bukti |
|---|---|---|
| E1 | `PATCH /api/entities/{id}` tak cek keunikan `doc_prefix`/`short_name` | set prefix jadi `KSC` → **200**, dua entitas ber-prefix sama → nomor dokumen bisa kembar |
| E2 | `_ENTITY_CODE_CACHE` (`core_utils.py:69`) tak pernah dibersihkan | ganti prefix tak berlaku sampai backend restart |
| E3 | Entitas **nonaktif** tetap tampil di pemilih; bila dipilih → **diam-diam** jatuh ke entitas home | `X-Entity-Id=<nonaktif>` → `active_entity_id=ent_ksc`; `POST /customers` → `entity_id=ent_ksc` |
| E4 | Mode "Semua Entitas" **menulis diam-diam** ke entitas home | `POST /customers` header `all` → `entity_id=ent_ksc`, tanpa peringatan |
| E5 | Deaktivasi entitas tanpa pagar | entitas dengan user aktif tetap dimatikan; user-nya **tetap bisa login & bekerja**; admin kehilangan entitas itu dari switcher |
| E6 | `DELETE /api/users/{id}` **tidak ada** → tombol "Deactivate" di tab Users = **405** | terbukti |
| E7 | `PATCH /api/users` mengizinkan **email duplikat** | 2 akun ber-email `admin@kainnusantara.id` |
| E8 | Turun jabatan tak mencabut akses | admin→sales: `allowed_entity_ids` tetap semua entitas, `can_switch_entity=true` |
| E9 | Tak ada formulir **ubah** entitas & akun; tombol "Update" hanya PATCH status ke nilai sama tapi bilang "berhasil diupdate" | `AdminView.jsx:381` |
| E10 | Hasil `provisioning` dibuang; notifikasi "entities dibuat: **undefined**" | `useAppActions.js:401` membaca `data.name`, entitas hanya punya `legal_name` |
| E11 | Field entitas yang didukung backend tak ada di UI | `currency`, `fiscal_year_start`, `parent_entity_id`, `is_group`, `coa_template`, `incentive_payer`, `numbering_scheme` |
| E12 | Bentuk data tak konsisten: `/api/entities` mentah (`legal_name`) vs `/auth/context` ringkasan (`name`,`code`) | melahirkan tambalan `utils/entityLabel.js` + komentar bug di ≥6 berkas |
| E13 | `GET /users` abaikan `?entity_id`, batas 100, tanpa paging/filter/penanda entitas di baris | terbukti |
| E14 | Jenis entitas hanya `PT|CV` | `schemas.BusinessEntityCreate.type`; pemilik butuh **perorangan/UD/koperasi/yayasan** |
| E15 | Membuat akun **tidak** tertaut HR; employee HR dibuat otomatis oleh bootstrap dan **jadi yatim** saat user dihapus | 3 employee sisa dari akun probe yang sudah dihapus |

**C. Master data & konfigurasi yang masih bersama padahal harus per entitas**
| Objek | Kondisi | Bukti |
|---|---|---|
| Template dokumen / kop surat (`document_templates`) | `entity_id: null`, header hard-code "KAIN NUSANTARA" | 2 template dipakai kedua entitas |
| Branding PDF | **sudah per entitas** (`GET/PUT /api/pdf/branding/{entity_id}`) | tetapi tata letak `/api/pdf/templates/{doc_type}` masih global |
| Tarif insentif (`incentive_rates`) | 11 baris semua `entity_id="all"` | insentif = beban entitas masing-masing |
| Aturan persetujuan (`approval_rules`) | 9 baris semua `entity_id="all"` | limit approval bisa beda |
| Syarat pembayaran (`payment_terms`), kategori biaya (`expense_categories`), kebijakan retur (`sales_return_policies`) | SHARED | harus per entitas |
| Gudang (`warehouses`) | **tidak punya field entitas sama sekali** | perlu model kepemilikan (bersama vs khusus) |
| Bagan akun (`gl_accounts`) | shared by-code, `entity_id=null` | perlu **aktivasi/akun tambahan per entitas** (kode tetap bersama agar jurnal lama valid) |
| Pusat Pengaturan | 200 entri: 153 mendukung scope `entity`, **47 hanya `global`** | seluruh `hr.*` (BPJS/PPh21/lembur/PTKP), `uom.*`, `lot.*`, `receiving.*`, `makloon.*`, `ui.*`, `role_home.*` |
| Harga per entitas (`entity_prices`) | mesin ADA (`routers/pricelist.py`) tapi **0 baris** | semua entitas pakai `products.price` |

**D. Nomor dokumen**
- `core_utils.next_doc_number()` punya 2 mode: per-entitas (`KSC/PO-00012`) & grup (`PO-00012`).
  35 titik memakai per-entitas; **`warehouse_transfers` (TRF) masih mode grup**.
- Data demo memakai seri grup: `SO-0001…SO-0009`, `PO-00004…PO-00011` dipakai bercampur dua entitas
  (`PO-00005`=Kanda, `PO-00007`=KSC) → nomor tidak bisa membedakan entitas.
- Keputusan pemilik: **hapus dokumen demo lama, seed ulang dengan prefix**.

**E. Visibilitas stok (perlu perubahan perilaku sesuai keputusan #1)**
- `GET /api/inventory/status-board` mengirim `by_entity[]` lengkap **sampai rincian per gudang**
  ke semua role; respons sales KSC = sales Kanda (BTK-MEGA-001: KSC 933 unit/3 gudang, Kanda 7 unit)
  + `has_intercompany_opportunity: true`.
- `GET /api/pegging/rolls` menyertakan roll milik entitas lain (A lihat 1 roll Kanda, B lihat 3 roll KSC).

---

## 2) PRINSIP EKSEKUSI (wajib dipatuhi agen berikutnya)

> **LANGKAH PERTAMA SETIAP SESI BARU (wajib):** `frontend/build/` **hilang setiap pod
> restart** (folder di-gitignore & tidak ikut snapshot) sehingga preview jadi **503**.
> Jalankan `bash /app/scripts/rebuild_frontend.sh` (±40 detik) sebelum apa pun.
> Bila DB kosong: `python /app/seed_realistic.py` (wajib untuk uji dua-entitas — hanya
> seeder ini yang membuat `sales3@kainnusantara.id`, sales entitas `ent_kanda`).

1. **Satu sumber kebenaran**: semua penyaringan entitas lewat `entity_scope.py`. Dilarang menulis
   filter `entity_id` ad-hoc di router baru.
2. **Server penjaga terakhir**: UI boleh menuntun, tetapi penolakan wajib ada di server (403/404).
3. **Gagal berisik, bukan diam-diam**: konteks entitas tidak valid/nonaktif → **tolak dengan pesan**,
   jangan fallback diam-diam ke entitas home (akar E3/E4).
4. **Bahasa Indonesia** untuk seluruh UI & pesan galat (dijaga `scripts/audit_i18n_id.py`).
5. Setiap fase: **POC terisolasi → hijau 100% → BE+FE → `bash scripts/rebuild_frontend.sh` →
   `bash scripts/gate.sh` → `testing_agent_v3` → update `plan.md` + `SESSION_HANDOFF.md` +
   `ENTITY_REGISTRY.md` + `CODEBASE_MAP.md`**.
6. **POC wajib self-cleanup** (aturan `INV-GATE-01` di `scripts/gate_residue.py`).
7. Frontend TIDAK hot-reload (dilayani dari `frontend/build` oleh `static_server.js`) →
   **wajib** `bash /app/scripts/rebuild_frontend.sh` setelah mengubah `frontend/src`.
8. Setiap elemen interaktif baru wajib `data-testid`.
9. Jangan sentuh `backend/.env` & `frontend/.env`.

---

## 3) FASE EKSEKUSI

### FASE E-0 — TUTUP KEBOCORAN + PAGAR ANTI-REGRESI  *(prioritas tertinggi)*
**Tujuan:** klaim "karyawan 1 entitas tidak bisa melihat entitas lain" menjadi benar 100%.

Tugas backend:
- E0.1 `routers/notifications.py` — scope per entitas (`resolve_list_scope("notifications", …)`).
  Pindahkan `notifications` dari SHARED → SCOPED di `entity_scope.py`; tambahkan migrasi
  backfill `entity_id` untuk 9 notifikasi yang kosong.
- E0.2 `payment_plans`, `payment_variance`, `penalties` (cari router pemilik `/api/penalties`),
  `sales-targets`, `sales-incentives` (router CRM/incentive) — pasang `entity_ctx` +
  `resolve_list_scope` pada LIST dan `assert_entity_access` pada DETAIL/aksi.
- E0.3 `routers/audit.py` — ganti gerbang jadi `require_permission(request, "audit", "view")`
  (tambahkan resource `audit` ke `permissions_config.py`: admin `["view"]` saja) **dan** filter
  `entity_id` = entitas aktif. Tambahkan `entity_id` ke penulisan `audit()` di `dependencies.py`
  (sekarang 55 dari 62 baris tidak punya entitas → wajib di-stempel dari konteks).
- E0.4 `routers/lots.py` — `assert_entity_access` di semua endpoint by-id (lot detail, label, silsilah).
- E0.5 `routers/ar_aging.py` + `services/ar_aging_service.py` — resolusi entitas dari `entity_ctx`
  (param `entity_id` opsional; `all` hanya untuk admin/manager); kembalikan `entity_id` yang
  BENAR di respons; laporan wajib menyebut nama entitas.
- E0.6 `routers/settings.py:29` — `get_effective_settings` memakai `entity_ctx` bila param kosong.
  Audit semua pemanggil `get_effective_settings(None)` di service lain (grep) dan perbaiki.
- E0.7 Pembersihan data yatim: skrip `scripts/fix_orphan_entity_refs.py` — laporkan & rapikan
  dokumen ber-`entity_id` yang entitasnya tidak ada (mulai `hr_org_units` 12 baris).
- E0.8 `seed_realistic.py` — perbaiki stempel entitas `sales_targets`/`sales_incentives`
  (ikut `home_entity_id` sales), dan pastikan setiap dokumen demo ber-entitas benar.
- **E0.8b** `routers/transfers.py` (L13/L14) — pasang `entity_ctx` + `resolve_list_scope`
  pada LIST dan `assert_entity_access` pada detail/approve/reject/status/delete.
  Transfer **antar-entitas** perlu aturan khusus: terlihat oleh **kedua** entitas
  (`$or: [source_entity_id, dest_entity_id] ∈ allowed`) tetapi hanya **entitas asal**
  yang boleh menyetujui pengiriman dan **entitas tujuan** yang boleh menerima.
  Daftarkan `warehouse_transfers` ke `SCOPED_COLLECTIONS` + backfill `entity_id`.
- **E0.8c** `routers/documents.py` (L18/L19) — `documents/preview/{order_id}`,
  `documents/generate`, `documents/trace*`, `documents/refs*`, `documents/relations*`
  wajib memverifikasi entitas dokumen sumber (`assert_entity_access`). Cetak dokumen PT
  lain harus **404**.
- **E0.8d** Router sisa hasil pemindaian statik (L17): `admin.py`, `incentive_rates.py`,
  `landed_cost.py`, `payment_variance.py`, `pegging.py` (TANPA scoping) dan `crm.py`,
  `cycle_count.py`, `products.py`, `return_policies.py` (PARSIAL).
- **E0.8e** Registry (L15/L16) — daftarkan 18 koleksi ber-`entity_id` yang belum terdaftar
  sebagai SCOPED atau SHARED **secara eksplisit** (keputusan per koleksi, jangan diam-diam),
  dan perbaiki drift nama `input_tax_invoices` → **`tax_invoices_in`**.
- **E0.8f** RBAC keuangan (L20) — `permissions_config.py`: role **gudang** hanya
  `interco: [view, ship, receive]`; **cabut** akses ke `/interco/accounts`,
  `/interco/settlements`, `/interco/margin-report`, `/interco/reminders`.
- **E0.8g** **(L21 — KRITIS)** `routers/sales_orders_extra.py`: `preview-allocation`
  (baris 48-56) & `preview-lots` (baris 83-90) **mengabaikan `entity_ctx`** dan jatuh ke
  `DEFAULT_ENTITY_ID` → sales CV Kanda mendapat pratinjau ATP **milik KSC**
  (`own_available: 788`, lot `LOT-001`) dan boleh **memaksa** `entity_id=ent_ksc` (200).
  Perbaiki: entitas WAJIB dari `entity_ctx`; `payload.entity_id` divalidasi ∈ allowed;
  `preview-roll-reconcile` flag `all_entities` hanya untuk peran lintas-entitas
  (sekarang membocorkan nomor roll & kode lot PT lain: `RL-632A10`, `KSC/LOT-2608-0026`).
  **Dampak bisnis:** sales menjanjikan stok yang bukan milik entitasnya.

Pagar anti-regresi (WAJIB, ini yang mencegah masalah balik lagi):
- E0.9 Jadikan `scripts/entity_audit/audit_entity_isolation.py` sebagai gate resmi
  `scripts/audit_entity_isolation.py`: sapu SELURUH endpoint GET sebagai sales 2 entitas →
  **FAIL bila ada satu pun `ent_*` asing** (kecuali daftar putih lintas-entitas by design).
  Tambahkan ke `scripts/gate.sh`.
- E0.10 Gate statik: setiap koleksi di `SCOPED_COLLECTIONS` wajib punya router yang memakai
  `resolve_list_scope`/`apply_entity_scope`; laporkan router yang menyentuh koleksi ter-scope
  tanpa lapisan scoping (perluas `scripts/audit_collection_drift.py`).
- E0.11 Perluas `backend/test_f0c_scoping_leak_poc.py` dengan 12 kasus L1–L12 (bukti-merah:
  fixture di kedua entitas dulu, baru buktikan tidak terlihat).

**Kriteria selesai:** sapuan isolasi **0 kebocoran**; POC F0-C hijau (≥40 assert);
`gate.sh` hijau; sales/gudang **403** di `/api/audit-logs`.

---

### FASE E-1 — MODEL ENTITAS: JENIS BADAN USAHA, PAGAR SIKLUS HIDUP, NOMOR DOKUMEN
- E1.1 **Jenis entitas**: enum `PT | CV | Perorangan | UD | Koperasi | Yayasan | Lainnya`
  (daftarkan di `domain_registry.py` supaya bisa dipakai FE lewat `/api/enums`).
  Aturan: NPWP wajib hanya bila PKP; nama legal untuk perorangan = nama pemilik + label usaha;
  `default_tax_mode` **independen** dari jenis.
- E1.2 **Validasi & keunikan**: `PATCH /api/entities` memvalidasi `short_name` & `doc_prefix`
  unik (case-insensitive) — pindahkan validasi ke `entity_provisioning_service` agar satu jalur.
- E1.3 **Kunci prefix**: `doc_prefix` tidak boleh diubah bila entitas sudah menerbitkan dokumen
  (cek `number_sequences` / dokumen ber-entitas). Pesan: sebutkan dokumen pertama yang terbit.
- E1.4 **Cache**: `core_utils._ENTITY_CODE_CACHE` — invalidasi saat entitas dibuat/diubah
  (fungsi `invalidate_entity_code(entity_id)`); dipanggil dari router entities.
- E1.5 **Status entitas**: `GET /api/entities?status=` (default aktif saja untuk pemilih);
  `entity_ctx` **menolak** `X-Entity-Id` entitas nonaktif/tak diizinkan dengan **403 + pesan**
  (hentikan fallback diam-diam). `entity_summaries` hanya entitas aktif.
- E1.6 **Pagar deaktivasi** (`DELETE /api/entities/{id}`): hitung dampak (user aktif, dokumen
  terbuka, saldo, periode belum tutup) → **409 dengan rincian** bila masih terpakai; bila
  dipaksa (peran admin + alasan) → status `archived`: **kunci-tulis** (semua POST/PATCH ke
  entitas itu 409), data lama tetap terbaca oleh admin, pengguna yang home-nya entitas itu
  **diblokir masuk** dengan pesan jelas. Tambah `POST /api/entities/{id}/reactivate`.
- E1.7 **Nomor dokumen seragam**: semua pemanggil `next_doc_number` memakai mode per-entitas
  (termasuk `routers/transfers.py:121,200`). Tambah uji tabrakan: 2 entitas, 50 dokumen paralel
  → nol duplikat. Hapus dokumen demo lama ber-nomor grup; `seed_realistic.py` menerbitkan
  nomor ber-prefix (`KSC/SO-00001`, `KANDA/SO-00001`).
- E1.8 **Bentuk data entitas seragam**: `/api/entities` mengembalikan bentuk yang SAMA dengan
  `/auth/context` (`id, code, name, short_name, legal_name, type, is_pkp, currency, status,
  doc_prefix, logo_url, readiness`). Pensiunkan tambalan `utils/entityLabel.js` (biarkan
  re-export supaya impor lama tidak patah).
- E1.9 **Kesiapan entitas** (`GET /api/entities/{id}/readiness`): daftar periksa terhitung —
  pengguna, gudang yang boleh dipakai, rekening bank, harga jual, saldo awal, kop surat/branding,
  konfigurasi pajak, tahun fiskal. Dipakai UI Fase E-3.

---

### FASE E-2 — AKUN TERTAUT ENTITAS (via HR) & PENEGAKAN AKSES
- E2.1 **Sumber kebenaran entitas karyawan = HR.** `POST/PATCH /api/users` menerima
  `employee_id` (opsional saat migrasi): bila terisi → `home_entity_id` **diambil** dari
  `hr_employees.entity_id` dan tidak bisa berbeda. Bila akun dibuat tanpa employee, sediakan
  aksi "tautkan ke karyawan" + tampilkan peringatan di UI.
- E2.2 `allowed_entity_ids`: untuk role non-lintas (sales/gudang) hanya boleh berisi entitas
  yang **diizinkan pemilik** (home + penugasan tambahan eksplisit). **Ubah role → hitung ulang**
  daftar entitas (tutup E8) dan **cabut sesi** user tersebut.
- E2.3 `PATCH /api/users`: cek **email unik** (409), larang menonaktifkan admin terakhir,
  hapus sesi saat status→inactive / entitas dicabut / password diganti.
- E2.4 `DELETE /api/users/{id}` = **nonaktifkan** (soft) + `POST /api/users/{id}/reactivate`
  + `POST /api/users/{id}/reset-password` (audit, tanpa membocorkan password lama).
- E2.5 `GET /api/users`: filter `entity_id`, `role`, `status`, `q`, **paging** (pakai
  `pagination.py` yang sudah ada), setiap baris membawa `home_entity`, `allowed_entities`,
  `employee_id`, `last_login_at`.
- E2.6 **Rapikan sinkronisasi HR↔akun** di `bootstrap.py:833` — jangan membuat employee untuk
  akun yang sudah tidak ada; sediakan `scripts/fix_orphan_employees.py`.
- E2.7 Audit: setiap perubahan penugasan entitas/role/status tercatat dengan `entity_id`.

---

### FASE E-3 — LAYAR "ENTITAS & AKSES" (UI baru, skala puluhan entitas)
> Ganti tab `Entities`/`Users` di `AdminView.jsx` (tab lama **dihapus** agar tidak ada dua pintu).
> Lokasi: hub `settings-hub` → tab baru **"Entitas & Akses"** (`config/hubTabs.js`),
> view `entities-access`, komponen `features/settings/entities/`.

Struktur komponen (batas 500 baris/berkas):
- `EntitiesAccessView.jsx` — kerangka + tab: **Entitas** · **Akun & Akses** · **Kesiapan**.
- `EntityList.jsx` — tabel/kartu skalabel: pencarian, filter status & jenis, **paging**,
  kolom: nama legal · jenis · kode dokumen · PKP · mata uang · #pengguna · #gudang ·
  kesiapan (%) · status. Aksi baris: buka detail, nonaktifkan/aktifkan.
- `EntityWizard.jsx` — **4 langkah** (progres jelas, bisa mundur, ringkasan sebelum simpan):
  1. **Identitas** — jenis badan usaha (termasuk perorangan), nama legal, nama singkat,
     alamat/kota, NPWP (opsional), logo.
  2. **Pajak & Keuangan** — PKP/non-PKP (jelaskan akibatnya), mata uang, awal tahun fiskal,
     template CoA, penanggung insentif.
  3. **Penomoran & Dokumen** — kode dokumen (pratinjau langsung `KSC/SO-00001`), skema nomor,
     kop surat/branding (bisa "salin dari entitas lain").
  4. **Akses & Kesiapan** — pilih gudang yang boleh dipakai (bersama/khusus), **buat akun
     pertama (PIC) sekaligus** (opsional, tertaut HR), lalu tampilkan **daftar kesiapan**
     yang bisa diklik ke layar terkait.
  Setelah simpan: tampilkan hasil `provisioning` (prefix, PKP, CoA, config) — **bukan**
  notifikasi "undefined" (perbaiki `useAppActions.adminCreate` agar memakai
  `legal_name || name || code`).
- `EntityDetailDrawer.jsx` — **bisa diubah** (tutup E9): identitas, pajak, penomoran (prefix
  terkunci bila sudah ada dokumen — jelaskan alasannya), branding, gudang, harga, pengguna,
  riwayat perubahan (audit), tombol nonaktifkan dengan **pratinjau dampak**.
- `AccountList.jsx` + `AccountFormDrawer.jsx` — daftar akun dengan **lencana entitas**, filter
  per entitas/role/status, pencarian, paging; formulir: nama, email, telepon, role, **karyawan
  HR (pencarian)**, entitas utama (dari HR, hanya-baca bila tertaut), entitas tambahan
  (multi-pilih dengan penjelasan), status; aksi: reset password, nonaktifkan/aktifkan,
  cabut sesi.
- `EntityReadinessPanel.jsx` — daftar periksa per entitas dari E1.9, setiap baris punya
  tombol ke layar penyelesaiannya.

Pemilih entitas (`components/EntitySwitcher.jsx`):
- hanya entitas **aktif & diizinkan**; tandai **entitas utama (home)**; pencarian bila > 8 entitas;
- mode **"Semua Entitas" = HANYA-BACA**: tampilkan pita peringatan di layar dan **matikan
  tombol simpan/buat** dengan pesan "Pilih satu entitas dulu untuk membuat data" (tutup E4);
- entitas nonaktif/tak diizinkan → pesan galat, bukan fallback diam-diam.

Konsistensi lintas layar:
- Lencana entitas (`EntityBadge`) di **setiap** daftar dokumen & panel detail.
- Judul layar/PageMeta menyebut entitas aktif.
- Empty state menyebut entitas: "Belum ada pesanan untuk **CV Kanda Suka**".

#### STATUS E-3 — **SELESAI** (sesi 2026-08-10, lanjutan)
Bukti: `gate.sh` **SEMUA GATE HIJAU** (30 gate) · `POC FASE E-3` **26/26** (idempotent,
nol residu) · `guard:write_scope` self-test **17/17** · `POC FASE E-0` tetap hijau ·
POC antar-entitas `test_g6b_poc` tetap **15/15**.

Yang ditutup di sesi ini (sisa E-3):
1. **Tab lama benar-benar mati.** `AdminView.jsx` tak lagi menerima prop
   `users`/`entities`; cabang `tab === "users"` / `"entities"` yang menganggur dihapus.
   Rantai ternary yang **jatuh ke daftar pengguna** untuk tab tak dikenal (mis. tab
   "Integrasi AI" menampilkan daftar akun) diganti tabel eksplisit `RECORDS_BY_TAB`.
2. **Dua gate merah warisan sesi sebelumnya diperbaiki** — bukan diakali:
   `AccountFormDrawer.jsx` menampilkan `home_entity_id` teknis sebagai cadangan
   (INV-UI-02) → kini lewat `entityFull()`; label "Login terakhir" (audit_i18n_id)
   → "Terakhir masuk".
3. **Mode "Semua Entitas" = HANYA-LIHAT, ditegakkan di server** — cacat nyata yang
   dibuktikan sesi ini: `POST /api/customers` dengan `X-Entity-Id: all` menjawab
   **200** dan dokumennya mendarat di badan usaha HOME. Sekarang ada
   `backend/entity_write_guard.py` (middleware, **deny-by-default**, tabel rute
   tingkat grup ditulis eksplisit dengan alasan per baris). Aturannya satu kalimat:
   *membuat sesuatu yang baru butuh memilih satu badan usaha; menindak dokumen yang
   sudah ada tetap boleh karena dokumen itu sudah punya badan usahanya.*
   Master **bersama** (produk/satuan/kategori/template/gudang), layar **tingkat grup**
   (badan usaha, akun, konfigurasi), **antar-entitas** (interco), dan **pratinjau**
   tetap boleh — dibuktikan POC.
4. **FE mendukung aturan yang sama, bukan menebak**: pita `ScopeReadOnlyBanner`
   (dengan pilih-cepat badan usaha satu klik), `EntitySwitcher` menandai **⭐ Utama**,
   memberi label **"hanya lihat"** pada mode gabungan, menyaring badan usaha terarsip,
   dan memunculkan **pencarian bila > 8** badan usaha; tombol buat/simpan dimatikan
   (`useEntityScope()`); interseptor `apiClient` menjamin penolakan 409 **selalu**
   terlihat sebagai pesan yang menuntun di layar mana pun.
5. **Konsistensi lintas layar**: breadcrumb menyebut badan usaha aktif
   (`page-scope-label`), empty state memakai `scopeSuffix()`
   ("Belum ada pesanan aktif untuk CV Kanda Suka."), daftar badan usaha menambah
   kolom **mata uang** & **#gudang**.

Catatan untuk fase berikut: pagar tulis ini **sekaligus menutup cacat E4** "mode
Semua Entitas menulis diam-diam ke home". E-4 tinggal mengerjakan bagian
*master data & konfigurasi per entitas* (gudang `sharing_mode`, dst).

---

### FASE E-4 — MASTER DATA & KONFIGURASI PER ENTITAS
- E4.1 **Gudang (keputusan 3c)**: tambah `sharing_mode: "shared" | "dedicated"` +
  `entity_ids: []` pada `warehouses` (+`WarehousePayload`). Aturan: `shared` → boleh dipakai
  semua entitas; `dedicated` → hanya `entity_ids`. Terapkan penyaringan di semua pemilih gudang
  (penerimaan, kirim, transfer, stok, stock opname) dan **tolak di server** bila gudang tidak
  boleh dipakai entitas aktif. Migrasi: 3 gudang demo → `shared`.
- E4.2 **Template dokumen / kop surat**: `document_templates` menjadi SCOPED (`entity_id`),
  dengan warisan: template entitas → template global (label "diwarisi dari global").
  Satukan dengan branding PDF per entitas yang sudah ada (`/api/pdf/branding/{entity_id}`);
  tata letak `/api/pdf/templates/{doc_type}` diberi lapisan override per entitas.
- E4.3 **Per entitas**: `payment_terms`, `expense_categories`, `incentive_rates`,
  `approval_rules`, `sales_return_policies` → SCOPED dengan pola **warisan global→entitas**
  (baris `entity_id="all"` tetap berlaku sebagai bawaan, override per entitas menang).
  UI wajib menampilkan lencana asal (**Global** / **Entitas ini**).
- E4.4 **Bagan akun**: kode tetap bersama (jurnal lama valid), tambah per-entitas
  **aktivasi/nonaktifkan akun** + **akun khusus entitas**. Layar CoA menampilkan kolom
  "dipakai entitas ini".
- E4.5 **Pusat Pengaturan (47 entri global-only)**: tambahkan scope `entity` pada seluruh
  `hr.*` (BPJS/PPh21/PTKP/lembur/tipe kerja), `uom.*`, `lot.*`, `receiving.*`, `makloon.*`.
  `ui.*`/`role_home.*` boleh tetap global (jelaskan di UI: "berlaku untuk seluruh sistem").
  Pastikan `config_resolver` benar-benar membaca lapisan entitas untuk kunci baru
  (`scripts/audit_config_wiring.py` harus 0 temuan).
- E4.6 **UI Pusat Pengaturan anti-menyesatkan**: scope **default = entitas aktif** (bukan
  global); pita "Anda sedang mengubah **CV Kanda Suka**"; setiap kartu menampilkan
  **nilai efektif + asal lapisan** (sudah ada `source_label`, pastikan terisi untuk semua
  kunci) + tombol "Kembalikan ke global"; peringatan saat mengubah nilai global yang dipakai
  banyak entitas (pakai `ImpactPicker` yang sudah ada).
- E4.7 **Harga (keputusan 4a)**: layar Pricelist per entitas — grid produk dengan kolom
  **Harga global**, **Harga entitas ini**, **Harga efektif + lencana asal**
  (`Global` / `Entitas` / `Pelanggan`), tombol override & "hapus override", riwayat,
  impor/ekspor CSV. Seed contoh override untuk demo. Pastikan POS/SO memakai harga efektif
  per entitas (sekarang `entity_prices` kosong sehingga jalur ini belum pernah terbukti).

#### STATUS E-4 (diperbarui sesi 2026-08-11, repo `kauajaabsjasdas/kn`)
| Sub-fase | Status | Bukti |
|---|---|---|
| **E4.1 Gudang bersama/khusus** | **SELESAI** | backend 45/45 (iter 212) · frontend FE-1..FE-5 LULUS (iter 214) · gate `guard:warehouse_scope` hijau |
| **E4.7 Harga per badan usaha** | **SELESAI** | frontend FE-6..FE-9 LULUS (iter 214) · 6 `entity_prices` demo (Kanda 5 + KSC 1, 1 terjadwal) |
| **E4.2 Template dokumen per badan usaha** | **SELESAI** | POC §7: kop surat Kanda dipakai cetak Surat Jalan `so_002`, KSC tidak terpengaruh |
| **E4.3 Master per badan usaha** | **SELESAI** | POC 56/56 · syarat bayar · kategori biaya · kebijakan retur · (insentif & aturan persetujuan sudah sejak E-0) |
| **E4.4 Bagan akun per badan usaha** | **SELESAI** | mesin override per-PT sudah ada (F0-E) + lencana asal (`entity_scope`/`source_label`) + kolom "Dipakai <PT>" satu klik |
| **E4.5 Pusat Pengaturan: 47 entri hanya-global** | **SELESAI** | 41 entri `hr./uom./lot./receiving./makloon.` kini ber-scope `entity`; sisa 6 (`ui.*`, `role_home.*`) memang global & dijelaskan di UI |
| **E4.6 UI Pusat Pengaturan anti-menyesatkan** | **SELESAI** | scope bawaan = badan usaha aktif · pita konteks · lencana "nilai <PT>" / "diwarisi dari Global" · tombol **Kembalikan ke global** (`POST /config/values/clear`) |

**Bukti penutup E-4:** `bash scripts/gate.sh` **34 gate HIJAU** ·
`backend/test_core_e4_master_layers_poc.py` **56/56** (3× berturut-turut, nol residu,
memulihkan data demo) · `scripts/audit_config_wiring.py` **0 temuan** ·
`testing_agent_v3` iterasi **214: frontend 12/12 LULUS**.

**Penutupan uji frontend E-4 (sesi 2026-08-11).** Iterasi 213 gagal 70% dan sebabnya
BUKAN fitur: SPA ini tidak punya alamat per layar, dan agen uji memakai pemilih teks
`'PENJUALAN'` padahal teks sumbernya `'Penjualan'` (huruf besar hanya efek CSS).
Yang dikerjakan: **deep-link universal `?view=<viewId>[&tab=][&entity=]`**
(`hooks/useViewDeepLink.js` + `resolveDeepLinkTarget()`), divalidasi terhadap menu peran
sehingga bukan pintu belakang RBAC, dan alamat disegarkan `replaceState` saat berpindah
layar (layar jadi bisa di-bookmark & dibagikan; tombol "kembali" peramban tidak menumpuk).
Alamat juga menerima **id menu/hub** (mis. `?view=ledger` → tab pertama yang boleh dilihat).
Hasil: **iterasi 214 = 12/12 skenario LULUS (FE-1..FE-11), konsol tanpa error merah.**
Sekalian diperbaiki: Pricelist tidak lagi menampilkan **"Rp 0"** untuk 3 produk tanpa harga
(barang sisa/grey) — sekarang "belum ditetapkan" + lencana "Belum ada harga" + bilah
`pl-noprice-hint`, karena angka nol terbaca seolah harga jual yang sah.

#### YANG DIBANGUN UNTUK MENUTUP E4.2–E4.6 (sesi 2026-08-11)
- **Mesin master berlapis** `backend/services/entity_master_service.py` + router generik
  `backend/routers/entity_masters.py`: satu daftar `MASTERS` (6 master) dengan
  `list_layered` (baris + `entity_scope`/`source_label`/`is_overridden`),
  `effective_rows`/`effective_map`/`resolve_row` (baris badan usaha MENANG, dipakai
  semua dropdown), `create`, `patch`, `override`, `revert`.
  **Aturan yang disengaja**: mengubah baris **Global** dari konteks satu badan usaha
  DITOLAK 409 dengan kalimat menuntun (dulu admin bisa diam-diam mengubah aturan seluruh
  grup); `revert` MENGHAPUS baris override (override "nonaktif" tetap menutupi global);
  di mode "Semua Entitas" baris baru lahir **Global**.
- **Registry & migrasi**: `payment_terms`, `expense_categories`, `document_templates`,
  `sales_return_policies` pindah SHARED → SCOPED + terdaftar di
  `INHERITED_GLOBAL_VALUES` (`["all", "", None]`). Migrasi idempotent
  `scripts/migrate_e4_master_scoped.py` menstempel **16 baris** lama menjadi `all`
  (hitung baris sebelum/sesudah; menolak bila jumlah baris berubah). Seed ikut
  distempel supaya seed ulang tidak menghapus lapisan.
- **Konsumen sadar lapisan**: `sales_orders` (jatuh tempo SO), `contra_bon_service`,
  `alert_service` (jatuh tempo AP per badan usaha), `budget_service` +
  `cash_advance_service` (kategori biaya → akun), `inventory_service._resolve_template`
  (kop surat cetak), `return_policy_service` (kebijakan khusus badan usaha MENANG atas
  global pada tingkat cakupan yang sama).
- **Pusat Pengaturan berlapis (E4.5)**: `config_resolver.entity_overlay()` +
  `get_settings(entity_id)` pada `lot_service`, `uom_rules_service`,
  `receiving_uom_service`, `contract_service`, dan `hr_service.get_hr_settings(entity_id)`
  (payroll `preview_run` & jatah cuti ikut). `config_catalog_ops.G` menjadi
  `("global", "entity")` — jujur, karena mesinnya sudah menghormatinya.
- **"Kembalikan ke global" yang benar (E4.6)**: `config_resolver.clear_layer()` menulis
  baris **NISAN** (`cleared: True`, tetap append-only sesuai INV-CFG-03) dan mencabut
  proyeksi di `system_settings`, lalu `POST /api/config/values/clear`. Ini SENGAJA
  dibedakan dari `/values/reset` yang menulis nilai bawaan KODE — kalau disatukan,
  nilai global yang sudah disesuaikan pemilik akan ikut tertimpa angka bawaan.
- **Layar baru "Master per Badan Usaha"** (`?view=entity-masters`, tab di Pusat
  Pengaturan): 6 kelompok master dalam satu tempat, lencana **Global** /
  **Badan usaha ini**, baris global yang ditimpa diredupkan + keterangan "ditimpa",
  tombol **Buat khusus <PT>** dan **Kembalikan ke global**, form baris baru dengan
  saklar "Jadikan Global".
- **Layar CoA (E4.4)**: kolom **Dipakai <PT>** (satu klik menyala/mati, hanya untuk
  badan usaha itu) + lencana `global`/`override` + catatan lingkup yang menyebut
  bahwa kode akun tetap bersama sehingga jurnal lama tetap sah.

#### RENCANA PENUTUPAN E-4 (sisa: E4.2 · E4.3 · E4.4 · E4.5 · E4.6)
Prinsip yang dipakai ulang (jangan bikin mesin baru): **warisan global → badan usaha**
sudah ada di `entity_scope.INHERITED_GLOBAL_VALUES` + `resolve_list_scope_inherit`
(dipakai `incentive_rates`/`approval_rules` sejak E-0). Sisanya mengikuti pola itu.

- **E4a — mesin master berlapis** `backend/services/entity_master_service.py`: satu daftar
  spesifikasi (`MASTERS`) berisi koleksi, kunci keunikan, label, field yang boleh diubah.
  Menyediakan `list_layered` (baris + `entity_scope`/`source_label`), `effective_rows`
  (baris badan usaha MENANG atas global, dipakai semua dropdown), `create`, `patch`,
  `override` (salin baris global menjadi khusus badan usaha), `revert` (lepas override).
  Router generik `backend/routers/entity_masters.py` supaya 6 master tidak butuh 6 layar.
- **E4b — registry & migrasi**: `payment_terms`, `expense_categories`,
  `sales_return_policies`, `document_templates` menjadi SCOPED + terdaftar sebagai
  "punya baris global sah" (`["all", "", None]`). Migrasi idempotent
  `scripts/migrate_e4_master_scoped.py` menstempel baris lama menjadi `all` (global)
  supaya TIDAK ADA baris yang hilang dari layar.
- **E4c — konsumen ikut sadar lapisan**: daftar syarat pembayaran, kategori biaya,
  template dokumen, kebijakan retur yang dipakai dropdown/laporan memakai `effective_rows`
  (tanpa baris kembar) — termasuk `config_service`, `contra_bon_service`, `alert_service`,
  `budget_service`, `cash_advance_service`, `inventory_service`.
- **E4d — satu layar "Master per Badan Usaha"** (tab baru di Pusat Pengaturan):
  6 kelompok master dalam satu tempat, tiap baris berlencana **Global** / **Badan usaha ini**,
  tombol **"Buat khusus <badan usaha>"** dan **"Kembalikan ke global"**. Mengubah baris
  **Global** saat satu badan usaha aktif DITOLAK dengan kalimat menuntun (bukan diam-diam
  mengubah nilai semua badan usaha).
- **E4e — E4.4 bagan akun**: kode CoA tetap bersama (jurnal lama valid) + aktivasi/nonaktif
  per badan usaha + akun khusus badan usaha; kolom "dipakai badan usaha ini" di layar CoA.
- **E4f — E4.5/E4.6 Pusat Pengaturan**: scope `entity` untuk seluruh `hr.*`, `uom.*`,
  `lot.*`, `receiving.*`, `makloon.*`; scope **bawaan = badan usaha aktif**; tiap kartu
  menampilkan nilai efektif + asal lapisan + tombol "Kembalikan ke global";
  `scripts/audit_config_wiring.py` harus 0 temuan.
- **E4g — POC gabungan** `backend/test_core_e4_master_layers_poc.py` (satu skrip,
  self-cleanup): baris global terlihat dari konteks badan usaha · override badan usaha
  menang · override Kanda TIDAK terlihat oleh KSC · dropdown tidak kembar ·
  ubah baris global dari konteks badan usaha ditolak dengan pesan menuntun ·
  di mode "Semua Entitas" baris baru lahir sebagai global.

---

### FASE E-5 — VISIBILITAS STOK SESUAI KEPUTUSAN #1
- E5.1 `GET /api/inventory/status-board`: untuk role non-lintas → **hanya `by_entity` entitas
  sendiri** + `global_total` (agregat tanpa rincian entitas/gudang). Untuk admin/manager →
  rincian penuh seperti sekarang. Field `has_intercompany_opportunity` tetap boleh muncul
  (sebagai isyarat "tersedia di entitas lain") **tanpa** membocorkan angka per gudang.
- E5.2 `GET /api/pegging/rolls` + turunan: scope ke `owner_entity_id` entitas aktif.
- E5.3 Mutasi pindah-kepemilikan antar-entitas tetap terlihat (jejak wajib), tetapi label
  entitas lawan hanya nama singkat.
- E5.4 **Sudah dibahas & dikunci di FASE E-8** (dahulu diparkir): pembagian akses & UI/UX
  **sales vs admin sales vs finance** — lihat `ANALISIS_DOMAIN_SALES.md` §8.

#### STATUS E-5 — **SELESAI** (sesi 2026-08-11, repo `kikijujahasa/kn`)
| Sub-fase | Status | Bukti |
|---|---|---|
| **E5.1 Papan stok: detail sendiri + agregat grup** | **SELESAI** (sudah sejak E-0, **diverifikasi ulang empiris**) | sales KSC: `by_entity`=[`ent_ksc`] · `total_available` 965 = stok sendiri · `global_total.available` 990 = stok grup · `other_entities_available` 25 · `detail_scope="own_entity"` · `owner_entity_id=<PT lain>` → **403**. Admin: `detail_scope="group"` + rincian per gudang |
| **E5.2 Pegging ter-scope kepemilikan** | **SELESAI** (sudah sejak E-0, diverifikasi ulang) | fixture roll pegging di 2 badan usaha: sales hanya melihat rollnya; admin di konteks PT lain tetap melihatnya |
| **E5.3 Mutasi lintas-PT: lawan = nama singkat** | **SELESAI** (**BARU** sesi ini) | `services/movement_label_service.attach_counterparty_labels()` |
| **E5.3c Kartu Riwayat Produk ter-scope** | **SELESAI** (**kebocoran BARU yang ditemukan & ditutup sesi ini**) | `routers/inventory.product_history` |
| E5.4 | dipindah ke **FASE E-8** | keputusan pemilik sudah lengkap di E8.10/E8.10b |

**Bukti penutup E-5:** `backend/test_core_e5_visibility_poc.py` **52/52** — dan **terbukti bisa
MEMERAH** (scope disabotase sengaja → **7 FAIL**, dipulihkan → 52 PASS) ·
`bash scripts/gate.sh --ci` **HIJAU** dengan gate baru
`POC FASE E-5 (papan stok agregat · pegging · mutasi lintas-PT nama singkat · kartu riwayat)` ·
`testing_agent_v3` iterasi **216: frontend 23/23 LULUS, nol error konsol**.

#### TEMUAN BARU SESI INI (tidak ada di rencana lama) — `GET /api/history/{product_id}`
Verifikasi E5.3 membuka kebocoran yang **belum pernah tercatat**: Kartu Riwayat Produk
mengambil **seluruh** mutasi sebuah produk **tanpa scope entitas sama sekali**
(`{"product_id": product_id}` telanjang). Bukti empiris sebelum perbaikan: sales
PT Kain Suka Cita mengklik satu produk → **9 baris, 2 di antaranya milik CV Kanda Suka**,
lengkap dengan nomor lot `KANDA/LOT-2608-0001` dan nama gudangnya. Ini sekelas **L21**
dan bertentangan langsung dengan Keputusan #1. Sesudah `resolve_list_scope`: **7 baris,
semuanya milik badan usaha sendiri**, jumlahnya TEPAT sama dengan hitungan DB, dan mutasi
pindah-kepemilikan sisi sendiri **tetap tampil** (jejak tidak ikut terhapus).
*Pelajaran yang dipagari:* gate isolasi lama menyapu endpoint **daftar**; endpoint
"riwayat satu induk" seperti ini lolos karena parameternya `product_id`, bukan `entity_id`.
POC E-5 sekarang menjaganya.

#### YANG DIBANGUN UNTUK MENUTUP E5.3 (sesi 2026-08-11)
- **`services/movement_label_service.attach_counterparty_labels()`** — satu tempat untuk
  menamai badan usaha lawan pada mutasi pindah-kepemilikan. Field turunan (data tersimpan
  TIDAK diubah — ledger tetap append-only): `counterparty_entity_name` (**nama singkat**,
  mis. `Kanda`), `counterparty_direction` (`in`/`out`, ditentukan dari `owner_entity_id`
  baris supaya baris masuk & keluar tidak tertukar), `counterparty_label`
  (`"dari Kanda"` / `"ke Kanda"`). Nama diambil `short_name` → `doc_prefix` → kalimat
  netral; **tidak pernah** jatuh kembali ke id teknis.
  **Aturan yang disengaja:** untuk peran **non-lintas**, id teknis
  `from_owner_entity_id`/`to_owner_entity_id` **DICABUT** dari respons dan nama badan
  hukum tidak pernah dikirim (dulu `ent_kanda` dikirim mentah); peran **lintas-entitas**
  tetap menerima id teknis + `from_entity_name`/`to_entity_name` supaya layar admin &
  konsolidasi tidak kehilangan kemampuan.
- **`routers/inventory.py`** — label dipasang di **kedua** jalur `list_movements`
  (biasa & paginasi; layar Mutasi memakai yang paginasi, jadi kalau hanya satu jalur
  dipasang lencananya hilang di layar) dan di `product_history`.
- **Frontend `CounterpartyBadge`** (`features/wms/inventory/inventoryConstants.jsx`) dipakai
  bersama oleh layar **Mutasi** (`LedgerTable.jsx`) dan **Kartu Riwayat Produk**
  (`ProductHistoryPanel.jsx`): lencana biru "↙ dari Kanda" untuk masuk, jingga
  "↗ ke Kanda" untuk keluar, plus tooltip yang menyebut bahwa rincian stok badan usaha
  lawan memang tidak ditampilkan.
- **Kerapian repo**: **124 skrip uji lama** di akar repo (`backend_test_*.py`,
  `test_*_poc.py`, `vendor_bill_*.py`) dipindah ke `tests/archive/` + `README.md` yang
  menjelaskan mana yang masih aktif. Diperiksa lebih dulu: **nol** rujukan dari
  `scripts/`; gate tetap hijau sesudah pemindahan. Akar repo sekarang hanya berisi
  3 skrip seed.

*Catatan kegagalan yang layak dicatat:* dua `search_replace` **paralel pada berkas yang
sama** (`LedgerTable.jsx`) saling menimpa sehingga baris impor `CounterpartyBadge` hilang
→ layar blank dengan `PAGE ERROR: CounterpartyBadge is not defined`. Ditemukan lewat
screenshot + log konsol, bukan lewat gate (gate tidak menjalankan browser). **Edit paralel
hanya boleh untuk berkas yang berbeda.**

---

### FASE E-7 — ANTAR-ENTITAS (lanjutan) · **KEPUTUSAN PEMILIK LENGKAP**
> Verifikasi lengkap: `AUDIT_ANTAR_ENTITAS.md`. Fondasi G-6/G-6b **sudah kuat & terbukti**
> (POC 21/21, INV-IC-01..08 hijau): dokumen kembar, harga dari kontrak internal, PPN &
> faktur pajak internal berpasangan, saldo pasangan PT, netting, jembatan gudang dengan
> pindah kepemilikan roll, retur antar-PT, eliminasi margin otomatis di konsolidasi,
> laporan margin. **Yang perlu diputuskan pemilik sebelum dieksekusi:**

- **E7.1 Permintaan barang antar-PT oleh sales** (IC-G9). Sekarang sales **403** di seluruh
  menu antar-entitas, padahal papan stok memberi isyarat "tersedia di PT lain".
  Opsi: (a) buat **Permintaan Internal** (sales ajukan → admin/manager menjadikan transaksi
  antar-PT, ikut `approval_threshold_rupiah` yang sudah ada) · (b) cukup manual di luar sistem.
- **E7.2 Pagar "lawan transaksi ternyata PT sendiri"** (IC-G10). Tambah penanda entitas grup
  pada `customers`/`suppliers` + **tolak** SO/PO yang lawannya PT grup dengan kalimat
  menuntun ke layar Antar Entitas (mencegah laba grup kembung karena margin tak tereliminasi).
- **E7.3 HPP penjual wajib ada** (IC-G11). `margin-report` melaporkan `cost: 0` →
  `margin 100%`. Putuskan: tolak transaksi bila HPP belum terhitung, atau tandai
  "HPP taksiran" di laporan & eliminasi.
- **E7.4 Kas/rekening tingkat grup** (IC-G12). 13 dari 19 transaksi kas ber-`entity_id="all"`,
  termasuk penerimaan piutang KSC. Putuskan modelnya: (a) hapus kas grup — setiap uang wajib
  milik satu PT · (b) kas grup tetap ada tetapi **otomatis menimbulkan hutang/piutang
  antar-PT** · (c) biarkan (tidak disarankan: keuangan PT jadi tidak utuh).
- **E7.5 Jalur antar-PT yang belum ada** (§C `AUDIT_ANTAR_ENTITAS.md`): titip bayar,
  pinjaman antar-PT, alokasi biaya bersama, makloon/jasa internal, pindah aset tetap,
  penempatan karyawan lintas-PT, eliminasi IC-AR/IC-AP otomatis di neraca konsolidasi.
  Bangun hanya yang benar-benar terjadi di lapangan (menunggu daftar dari pemilik).
- **E7.6 Konsistensi kecil**: `interco_returns` mengembalikan `pair_id`/`qty_total`
  (sekarang null karena bernama `return_pair_id`) · nomor `TRF` ikut ber-prefix entitas
  (sudah tercakup E1.7).
- **E7.7 Keputusan pemilik (2026-08-10) yang sudah PASTI untuk fase ini:**
  - **Entitas lain diperlakukan seperti PEMASOK, bukan pelanggan.** Bila KSC membeli dari
    Kanda, maka Kanda muncul sebagai pemasok bertipe "Entitas grup" dengan logika yang sama
    (wajib kontrak internal dulu, dst). **JANGAN** membuat pelanggan untuk PT sendiri.
    Pembedanya tetap **menu Antar Entitas** (+ lencana di layar pembelian).
  - **Kas/rekening tingkat grup DIHAPUS** (jawaban 3a): setiap uang wajib milik satu entitas.
    Migrasi: 13 transaksi kas ber-`entity_id="all"` + rekening "Kas Besar Grup" harus
    dipetakan ke entitas pemiliknya (penerimaan `KSC/AR-*` → `ent_ksc`, dst) — **butuh
    langkah migrasi ber-laporan, bukan tebakan**; yang tidak bisa dipetakan → jadi kasus
    di Pusat Kasus Keuangan.
  - **HPP taksiran DIBOLEHKAN tapi WAJIB BERLABEL** (jawaban 4b): laporan margin & eliminasi
    menandai `cost_estimated` dengan jelas di UI, bukan angka telanjang.
  - **Jalur antar-PT yang dibangun: hanya (1) pinjaman uang antar-PT dan (2) pindah aset
    tetap antar-PT.** Titip bayar, alokasi biaya bersama, makloon internal, dan penempatan
    karyawan lintas-PT **TIDAK dibangun** (pemilik menyatakan tidak terjadi).

#### KEADAAN AWAL E-7 (diverifikasi empiris sesi 2026-08-11 — sebelum eksekusi)
| Item | Keadaan terbukti |
|---|---|
| E7.1 (IC-G9) | **belum ada**: nol rujukan `internal_request` di seluruh backend |
| E7.2/E7.7 (IC-G10) | **belum ada**: `routers/customers.py`, `routers/suppliers.py`, `schemas.py` **nol** rujukan ke `business_entities`; tidak ada `partner_kind` di supplier |
| E7.3 (IC-G11) | `cost_estimated` **hanya** ada di `services/interco_margin.py` jalur `margin-by-product`; `margin-report` & eliminasi belum berlabel |
| E7.4 (IC-G12) | rekening **"Kas Besar Grup"** (`bank_kas_besar`, `entity_id="all"`) masih ada; **13 dari 19** `cash_transactions` ber-`entity_id="all"`, termasuk `CASH-00013/14/15` "Penerimaan KSC/AR-0000x" (jelas milik KSC) dan `CASH-00016/17/18` pembayaran kontrabon/VB |
| E7.5 | koleksi `interco_loans` **tidak ada**; `fin_fixed_assets` **0 baris** (jadi jalur pindah aset belum pernah bisa dibuktikan — seed perlu ditambah) |
| E7.6 (IC-G13) | `interco_returns` menyimpan `return_pair_id` **tanpa** `pair_id`/`qty_total` |
| E7.6 (IC-G14) | `TRF-00001..3` (`intra_entity`) masih seri grup; yang `inter_entity` sudah ber-prefix (`KSC/TRF-00004`, `KANDA/TRF-00001`) → sisa **data demo lama** + seed |
| IC-G1..IC-G8 | **sudah ditutup di FASE E-0** (tidak diulang di sini) |

#### RENCANA EKSEKUSI E-7 — BERGELOMBANG
Prinsip: **jangan bangun mesin baru** kalau mesin G-6/G-6b sudah ada. Yang ditambah hanya
pagar, label, jalur permintaan, dan dua jalur uang/aset yang pemilik nyatakan memang terjadi.

**GELOMBANG 1 — kebenaran angka & pagar (tanpa butuh keputusan tambahan pemilik)**
- **E7a (E7.2 + E7.7) — "lawan transaksi ternyata PT sendiri".** Tambah
  `partner_kind: "external"|"entity"` + `group_entity_id` pada `suppliers`
  (dan `group_entity_id` pada `customers` **hanya sebagai pagar deteksi** — pelanggan untuk
  PT sendiri tetap TIDAK boleh dibuat). Provisioning entitas menyiapkan baris pemasok
  bertipe **Entitas grup** untuk setiap badan usaha lain. **TOLAK** `POST/PATCH`
  purchase-order/purchase-requisition yang pemasoknya entitas grup dan sales-order yang
  pelanggannya entitas grup, dengan kalimat menuntun ke layar **Antar Entitas**
  (pola `tax_invoice_service.py:195`). Lencana "Entitas grup" di layar pemasok & pembelian.
- **E7b (E7.6) — konsistensi kecil.** `interco_returns` ikut mengirim `pair_id`
  (alias `return_pair_id`) + `qty_total`; nomor `TRF` `intra_entity` ber-prefix entitas
  (perbaiki `next_doc_number` bila perlu + seed).
- **E7c (E7.3) — HPP taksiran WAJIB BERLABEL.** `margin-report` + eliminasi konsolidasi
  membawa `cost_estimated` (+ alasan taksiran); UI menandainya, **bukan angka telanjang**.

**GELOMBANG 2 — jalur yang hilang untuk sales (E7.1)**
- **E7d — Permintaan Internal** (`internal_requests`, SCOPED, nomor `<ENT>/PIN-#####`):
  sales mengajukan "minta barang dari PT lain" langsung dari isyarat papan stok →
  masuk antrean admin/manajer → **dijadikan transaksi Antar-PT** yang bertaut
  (`source_request_id` + relasi dua arah `doc_refs_service`). Ambang
  `antar_entitas.approval_threshold_rupiah` yang sudah ada tetap dihormati.
  Di **FASE E-8** antrean ini pindah ke Meja Admin Sales (E8.8) — mesinnya jangan diulang.

**GELOMBANG 3 — uang & aset (E7.4 + E7.5) · E7.4 BUTUH KONFIRMASI PEMILIK PER BARIS**
- **E7e (E7.4) — kas grup DIHAPUS.** `scripts/migrate_e7_group_cash.py` dua tahap:
  `--report` (usulan pemetaan + **bukti per baris**, tanpa menulis) lalu `--apply`.
  Baris yang tidak bisa dipetakan → **kasus** di Pusat Kasus Keuangan. Sesudah migrasi:
  pagar menolak pembuatan rekening/transaksi kas ber-`entity_id="all"`.
- **E7f (E7.5-1) — pinjaman uang antar-PT** (dokumen kembar: piutang pemberi ↔ hutang
  penerima, masuk `interco_accounts` supaya ikut netting & pengingat).
- **E7g (E7.5-2) — pindah aset tetap antar-PT** (nilai buku + akumulasi penyusutan ikut,
  eliminasi laba pindah). Seed perlu contoh aset tetap karena sekarang 0 baris.

**PENUTUP E-7**
- **E7h — POC gabungan** `backend/test_core_e7_interco_poc.py` (satu berkas, self-cleanup,
  bukti-merah) + daftarkan di `scripts/gate.sh` + frontend untuk seluruh jalur di atas +
  `testing_agent_v3`.

#### STATUS E-7 — **SELESAI** (sesi 2026-08-11 penutup, repo `ganakauaanabasa/KN`)
| Sub-fase | Status | Bukti |
|---|---|---|
| **E7a Pagar "lawan transaksi ternyata PT sendiri"** | **SELESAI** | `suppliers.partner_kind="entity"` + `group_entity_id`; provisioning membuat baris pemasok Entitas grup otomatis (seed: 2 dibuat); PO/PR ke entitas grup **DITOLAK** dengan kalimat menuntun; UI: pita `group-entity-notice` + tombol simpan mati + lencana "Entitas grup" di layar pemasok |
| **E7b Konsistensi kecil** | **SELESAI** | `interco_returns` mengirim `pair_id` + `qty_total`; `TRF` intra-entity ber-prefix badan usaha |
| **E7c HPP taksiran WAJIB berlabel** | **SELESAI** | `margin-report` membawa `cost_estimated` + alasan; UI: pita `interco-margin-estimated-warning` + sel `≈` "HPP taksiran (WAC)" — tidak ada lagi margin 100% telanjang |
| **E7d Permintaan Internal (PIN)** | **SELESAI** | `internal_requests` ter-scope, nomor `<ENT>/PIN-#####`; sales mengajukan dari papan stok, **sales DILARANG memilih sumber** (400 di API, panel `pin-sources` disembunyikan di UI); admin memilih kandidat → jadi transaksi antar-PT kembar + tautan dua arah G-4 |
| **E7e Kas tingkat grup DIHAPUS** | **SELESAI** | rekening & transaksi kas ber-`entity_id="all"` ditolak 409; data demo bersih (0 sisa); ringkasan kas melaporkan sisa secara jujur |
| **E7f Pinjaman uang antar-PT** | **SELESAI** | dokumen kembar `KSC/ICL-0000x ⇄ KANDA/ICL-0000x`; draf → **Cairkan** → saldo non-dagang naik → **Angsuran** → `Lunas`; angsuran > sisa ditolak |
| **E7g Pindah aset tetap antar-PT** | **SELESAI** | `KSC/FA-00001 → KANDA/FA-00003` (nilai buku + **masa manfaat SISA** ikut); utang antar-PT terbentuk; **Catat pembayaran** memindahkan uang di dua buku (`KANDA/CASH-00015 · KSC/CASH-00034`); pindah dua kali ditolak |
| **E7g-2 CACAT BARU (ditemukan lewat layar, ditutup sesi ini)** | **SELESAI** | ringkasan aset dulu menghitung aset yang **sudah pindah** sebagai milik sendiri (mengaku punya Rp 420 jt yang sudah bukan haknya) & pil status merender hijau **"Aktif"**. Kini `summary()` mengeluarkan `transferred`, menambah `transferred`/`transferred_book_value`/`transferred_unsettled`, pil status = **"Pindah PT"** (biru), KPI baru "Pindah ke PT Lain" |
| **E7h POC + verifikasi layar** | **SELESAI** | POC `backend/test_core_e7_interco_poc.py` **56/56** (naik dari 53 — 3 pemeriksaan baru untuk E7g-2) · `gate.sh --ci` **HIJAU (49 gate)** · `testing_agent_v3` iterasi **219: 8/10 user story LULUS, nol error konsol**; **US6 (pinjaman) & US8 (pindah aset) diverifikasi tangan oleh agen utama** karena agen uji hanya menguji separuh |

**Perbaikan sampingan sesi penutup:** layar `internal-requests` tidak punya entri `PAGE_META`
sehingga kepala halaman jatuh ke judul cadangan "Kain Nusantara"/kicker "Workspace" —
diperbaiki **dan** dipagari gate baru `check_nav_map.py` **CHECK 5** (setiap layar wajib
punya judul & kicker; 94 layar diperiksa).

**Jebakan yang mahal (BACA sebelum memanggil agen uji):** iterasi **218 melaporkan
"navigasi rusak, session reset" dan 0% pada 9 user story — itu LAPORAN PALSU.** Sebabnya
dua: (a) agen mengeklik `text=GUDANG` padahal wrapper `nav-group-*` bukan elemen klik
(yang bisa diklik `nav-group-toggle-*`), (b) skrip memakai sintaks Playwright **sync**
di lingkungan **async** sehingga `locator.count()` mengembalikan coroutine dan disimpulkan
sebagai layar kosong. **Resep yang benar: deep-link `?view=<viewId>&entity=<entityId>`**
(`hooks/useViewDeepLink.js`) — buka URL, login, aplikasi langsung mendarat di layar itu
dengan badan usaha terpilih; sesi bertahan antar `page.goto`. Iterasi 219 memakai resep ini
dan langsung 100% pada bagian yang diujinya.


### FASE E-8 — DOMAIN SALES · ADMIN SALES · FINANCE · **KEPUTUSAN PEMILIK LENGKAP**
> Analisis lengkap + bukti + usulan matriks izin & UI: **`ANALISIS_DOMAIN_SALES.md`**.
> Inti temuan: sistem hanya punya **4 peran** (admin/sales/manager/warehouse) — **tidak ada
> "admin sales"**, sehingga orang itu harus dijadikan `sales` (tak bisa Konfirmasi SO) atau
> `manager` (ikut dapat kuasa tutup buku, payroll, bayar tagihan supplier, hapus master).

- **E8.1** Tambah peran **`sales_admin`** dan **`finance`** + **registry peran**
  (`backend/role_registry.py`, `frontend/src/config/roles.js`) sebagai sumber tunggal:
  label, peringkat, beranda, lintas-entitas. Arahkan `role_satisfies` (peringkat hard-code)
  & ~63 literal BE / ~81 literal FE ke registry secara bertahap (yang menentukan wewenang
  lebih dulu). **6 peran** total: admin · manager · sales_admin · finance · sales · warehouse.
- **E8.2 Pemisahan tugas (SD2)**: **cabut** dari peran `sales` → `tax_invoice.create/print`,
  `ar_receipt.create`, `payment_variance.decide`, `payment_plan.create/update`, pegging/earmark;
  **uang masuk & faktur pajak → peran `finance`**, alur SO & pemenuhan → `sales_admin`.
  (Ini pertanyaan lama **G5** di `ROLE_UX_GAP_AUDIT.md` yang kini SUDAH diputuskan pemilik.)
- **E8.3 Tutup layar mati untuk sales**: menu "Operasi WMS" terlihat tetapi `/api/wms/tasks`
  **403** (SD3) → beri `wms.view` ringkas atau endpoint "status pengiriman pesanan saya";
  menu "Kunjungan Sales" **403** (SD4) → izin melihat kunjungannya sendiri.
- **E8.4 Kepemilikan data sales (SD5/SD8)**: daftar SO **default "Pesanan Saya"** (sekarang
  `sales2@` melihat 8 SO milik rekannya, nol miliknya); `reports/top-customers` ikut filter pemilik.
- **E8.5 Target/insentif (SD6/SD7)**: ter-scope entitas + perbaiki stempel `entity_id`
  (Citra, sales Kanda, ter-stempel `ent_ksc`); `/api/sales-users` ikut entitas.
- **E8.6 `mark-delivered` (SD9)**: dicabut dari `sales`; **boleh gudang MAUPUN Admin Sales**
  (keputusan pemilik 3).
- **E8.7 Meja Admin Sales berbasis ANTREAN** (9 antrean — lihat §5.2 analisis):
  layar baru `features/sales_admin/`, bukan sekadar menu tambahan.
- **E8.8 Permintaan internal dari sales (SD10)**: tombol "Minta dari PT lain" pada isyarat
  stok → masuk antrean Admin Sales → menjadi transaksi Antar Entitas
  (keputusan pemilik: **admin sales yang mengeklik**).
- **E8.9 Entitas grup sebagai PEMASOK** — sejalan E7.7 & pagar E7.2.
- **E8.10 Definisi domain dari pemilik (2026-08-10) — MENGIKAT:**
  - **Sales (lapangan)**: jual barang · basis pelanggan sendiri · buat SO · **lihat status
    lifecycle pesanan** · **hanya SO miliknya** · **mengajukan retur**. Tidak mengurus
    operasional/manajemen.
  - **Admin Sales**: mengelola **keseluruhan SO** — **validasi** → **keputusan pemenuhan**
    (stok sendiri · **ambil dari PT lain** · **reorder ke supplier**) → konfirmasi →
    dokumen → **memproses retur** yang diajukan sales.

- **E8.10b KEPUTUSAN PEMILIK atas 4 pertanyaan penutup (MENGIKAT):**
  1. **Admin Sales = berbasis penugasan**: bisa dikunci 1 entitas atau diberi beberapa
     entitas. → JANGAN masukkan `sales_admin` ke `CROSS_ENTITY_ROLES`; pakai
     `allowed_entity_ids` tersimpan (mekanisme yang sudah ada untuk peran non-lintas),
     dan UI penugasan entitas di E-3 harus mendukung multi-pilih untuk peran ini.
  2. **Kasir/Finance DIPISAH** → **dua peran baru sekaligus**: `sales_admin` **dan**
     `finance`. Yang **mencatat uang masuk (kwitansi AR)** dan **menerbitkan Faktur Pajak**
     adalah **`finance`**, bukan Admin Sales dan bukan sales.
  3. **`mark-delivered` boleh gudang MAUPUN Admin Sales** (dua-duanya), dicabut dari `sales`.
  4. **Admin Sales berkuasa penuh atas keputusan pemenuhan**: buat PR (reorder supplier),
     **ambil dari PT lain**, dan pegging — **tanpa** persetujuan manajer. Kunci config
     `antar_entitas.approval_threshold_rupiah` **tetap disediakan** (default: tidak
     mengunci Admin Sales) supaya pemilik bisa menyalakannya kapan pun tanpa deploy.

- **E8.1b Matriks izin dua peran baru (rancangan awal — kunci saat eksekusi):**
```
sales_admin  (Admin Sales — pemilik alur SO end-to-end, TANPA menyentuh uang & pajak)
  order:            view, create, update, confirm, print          (approve → manager)
  customer:         view, create, update
  document:         view, create, print
  sales_return:     view, create, update                          (approve → manager)
  price_approval:   view, create, update                          (approve → manager)
  purchase_requisition: view, create, update                      (approve → manager)
  interco:          view, create, update, invoice                 (settle/cancel → manager)
  transfer:         view, create                                  (approve → manager/gudang)
  inventory:        view                (+ pegging/earmark: dipindah dari sales)
  wms:              view                (pantau progres, tanpa aksi)
  special_order:    view, create, update
  pricelist/product/uom/warehouse/template: view
  finance_case:     view, create
  esign/document_delivery: view, sign/send
  payment_plan:     view, create, update    (usul; pembebasan/void → manager)
  penalty:          view
  reports:          view                (tanpa kolom biaya/HPP)
  TIDAK punya: tax_invoice.create · ar_receipt.create · payment_variance.decide

finance  (Kasir/Finance — sisi UANG MASUK & PAJAK KELUARAN)
  ar_receipt:       view, create                                  (void → manager)
  tax_invoice:      view, create, replace, print                  (cancel → manager)
  payment_variance: view, decide        (batas nominal tetap dijaga config payment.variance_*)
  penalty:          view, issue                                   (waive/adjust → manager)
  payment_plan:     view, update
  cash:             view, create
  accounting:       view
  order:            view, print          (tanpa create/update/confirm)
  customer:         view
  sales_return:     view
  finance_case:     view, create
  reports:          view
  document:         view, print
  CATATAN: sisi HUTANG (vendor_bill.pay, contra_bon, landed_cost) TETAP manager/admin
  sampai pemilik memutuskan sebaliknya — jangan diperluas sendiri.
```
  Dicabut dari `sales`: `tax_invoice.*` · `ar_receipt.create` · `payment_variance.decide` ·
  `payment_plan.create/update` · `order.update` untuk `mark-delivered` · pegging/earmark.
  Ditambah ke `sales`: melihat perjalanan pesanan & kunjungan sendiri (E8.3/E8.14).
  **Hirarki `role_satisfies`**: `sales:1 · warehouse:1 · sales_admin:2 · finance:2 ·
  manager:3 · admin:4` (pindahkan ke registry peran, jangan angka ajaib).

- **E8.11 Mesin pemenuhan yang SUDAH ADA (jangan dibangun ulang!)**:
  `POST /sales-orders/preview-allocation` (klasifikasi `from_stock/from_incoming/
  inter_company/backorder` + `cross_entity[]` + kalimat penjelas) · `GET /stock/pending-so`
  (papan pending + coverage + promise date) · `POST /sales-orders/{id}/repeat-restock`
  (SO→PR, jejak dua arah `source="so_repeat"`, notifikasi MD) · `GET /{id}/restock-state`
  (kandidat + `open_pr_number`) · `GET /stock/atp` · pegging `earmark` ·
  `backorder_service.auto_fulfill_backorders` · mesin Antar Entitas G-6.
  **Tugas E-8 = menyatukan semuanya di satu Meja Admin Sales + memberi peran & izin**,
  bukan menulis mesin baru.
- **E8.12 Tautan SO ↔ Antar Entitas (A8)**: tambah `source_order_id`/`demand_ref` pada
  `interco_transactions` (meniru `source_ref_id` pada PR) + jejak dua arah G-4 supaya
  "ambil dari PT lain untuk `SO-0009`" terlacak.
- **E8.13 Pisahkan verifikasi administratif dari persetujuan manajerial (A7)**: persetujuan
  `nilai` sekarang memaksa role manajer bahkan untuk validasi rutin. Buat tahap
  **`verified_by_sales_admin`** (kelengkapan alamat/syarat bayar/pajak/dokumen) terpisah
  dari persetujuan `nilai`/`kredit`/`special_price` milik manajer.
- **E8.14 Perjalanan pesanan untuk sales (A2)**: satu endpoint ringkas (mis.
  `GET /sales-orders/{id}/journey`) yang menggabungkan status SO + tugas gudang +
  pengiriman + faktur + pembayaran + **sumber pemenuhan** (PR/PO atau transaksi antar-PT),
  read-only, tanpa memberi akses layar gudang.

### FASE E-9 — RANTAI JUAL → BELI INTERNAL → RETUR BERANTAI (skenario pemilik)
> Analisis penuh + bukti per langkah: **`ANALISIS_FLOW_RETUR_BERANTAI.md`**.
> Skenario: Customer A beli lewat Sales A di **Entitas A** → stok kosong → **beli internal
> dari Entitas B** → barang ke Customer A → Customer A retur (Sales A yang mengajukan) →
> barang kembali ke A → **A retur ke B** → B **retur ke supplier atau simpan** →
> kepemilikan kembali ke B. **Kesimpulan verifikasi: rantai sudah didukung ±80%.**
>
> Yang sudah lengkap & terbukti: dokumen kembar antar-PT + kontrak harga internal + faktur
> pajak internal + jembatan gudang dengan pindah kepemilikan & re-home lot + saldo pasangan +
> netting + eliminasi margin · retur pelanggan (kebijakan retur, inspeksi per roll, 4 outcome
> partial, karantina, nota kredit) · retur antar-PT kembar (alasan wajib + dual-control) ·
> retur beli ke supplier (kebijakan impor, siklus kirim/terima supplier).

- **E9.1 (PUTUS #1)** Penerimaan barang antar-PT **tidak memicu** `auto_fulfill_backorders`
  (hanya dipanggil dari `inbound_receiving.py:585` & `qc_service.py:263`). SO tetap
  `waiting_stock` padahal barangnya sudah datang. → panggil dari
  `roll_service.execute_ownership_transfer` (atau `interco_service.receive`) + notifikasi
  ke Admin Sales.
- **E9.2 (PUTUS #2)** `interco_transactions` tanpa `source_order_id` → tak ada jejak "IC ini
  untuk SO-0009". Tiru pola `PR.source="so_repeat"`/`source_ref_id`. Tampilkan janji dari
  PT lain di **Papan Pending SO** (`stock_bucket_service.pending_so_board`). Sama dengan E8.12.
- **E9.3 (RISIKO #3 — DUA JALAN untuk satu peristiwa)** Untuk "A retur ke B" ada
  `POST /api/interco/returns` (benar: harga internal, PPN, IC-AR/AP, eliminasi margin,
  dual-control) **dan** `return_service.transfer_return_roll_ownership` (at-cost, tanpa PPN,
  **tanpa** memperbarui `returned_qty` transaksi asal, **tanpa** memperbarui eliminasi).
  → Bila roll berasal dari pembelian internal: **blokir jalur at-cost** & arahkan ke Retur
  Antar-PT dengan kalimat menuntun (pola yang sudah dipakai `tax_invoice_service.py:195`).
- **E9.4 (RISIKO #4)** Retur antar-PT memilih roll **FEFO per produk**
  (`reserve_rolls_for_transfer`) — bukan roll hasil retur pelanggan (lot `RTN-*`, sering
  grade B) → **roll bagus terkirim balik, roll cacat tinggal**. Tambah parameter `roll_ids`
  + utamakan roll `origin_type="return"` milik dokumen retur terkait.
  Sekaligus: `returnable()` beri peringatan bila barang belum benar-benar kembali.
- **E9.5 (PUTUS #5 — jejak asal hilang)** Roll hasil retur pelanggan dibuat **tanpa**
  `supplier_id`/`po_id`/`po_number`/`supplier_invoice_no`, dan `execute_ownership_transfer`
  **menimpa** `acquired` menjadi `{"via":"transfer"}`. Akibatnya Entitas B **tidak bisa**
  menemukan roll itu sebagai kandidat retur ke supplier (`build_returnable_rolls` menyaring
  `supplier_id`/`po_id`). → wariskan field asal di `_restock_returned_items`, simpan
  `acquired_history[]` saat pindah kepemilikan, dan longgarkan `build_returnable_rolls`
  agar bisa membaca silsilah lot sebagai cadangan.
- **E9.6 (PUTUS #6)** Ketiga retur **tidak saling tertaut**. Pasang relasi dua arah lewat
  `doc_refs_service` (mesin G-4 sudah ada, 79 tautan aktif di demo) + satu layar
  **"Jejak Retur"**: retur pelanggan → retur antar-PT → retur beli / simpan barang.
- **E9.7 Prasyarat**: **L21** (pratinjau alokasi mengabaikan entitas) wajib beres lebih dulu —
  keputusan "beli internal atau tidak" tidak boleh berangkat dari angka stok PT yang salah.
- **E9.8 POC wajib** `backend/test_core_rantai_retur_poc.py` — satu skrip self-cleanup yang
  menjalankan **seluruh skenario pemilik** ujung-ke-ujung dan memeriksa: SO terpenuhi
  otomatis setelah barang antar-PT masuk · saldo IC-AR/AP kembali NOL setelah retur
  antar-PT · PPN keluaran/masukan ikut dibalik · eliminasi margin ikut berkurang ·
  roll yang kembali ke B adalah roll cacat yang benar · roll itu **bisa** diretur ke
  supplier aslinya · ketiga retur saling menunjuk.


- E6.1 POC gabungan `backend/test_core_entitas_poc.py` — satu skrip, self-cleanup, mencakup:
  provisioning (termasuk perorangan) · keunikan prefix · kunci prefix · nomor per-entitas
  anti-tabrakan · pagar deaktivasi & kunci-tulis · akun tertaut HR · pencabutan akses saat
  role berubah · mode "Semua Entitas" hanya-baca · warisan konfigurasi & master per entitas ·
  harga efektif per entitas · **21 kasus kebocoran L1–L21**.
- E6.1b POC kedua `backend/test_core_peran_poc.py` (FASE E-8) — 6 peran × matriks izin:
  sales hanya SO miliknya · sales **403** di faktur pajak/kwitansi/selisih bayar/pegging ·
  `sales_admin` bisa verifikasi+konfirmasi SO & 3 jalur pemenuhan tanpa manajer ·
  `sales_admin` **403** di faktur pajak & kwitansi · `finance` bisa faktur pajak + kwitansi
  tetapi **403** membuat/mengonfirmasi SO · `mark-delivered` oleh gudang & admin sales,
  **403** untuk sales · penugasan multi-entitas untuk `sales_admin` benar-benar mengunci data.
- E6.2 `scripts/audit_entity_isolation.py` = **0 kebocoran**; `bash scripts/gate.sh` hijau;
  `verify_api_contract` 0 ERROR/0 WARN; `check_nav_map` PASS; `audit_i18n_id` 0 temuan.
- E6.3 `testing_agent_v3` — uji **user story** (22 story di §4) di browser dengan
  **6 akun berbeda peran**, bukan hanya API. **Jangan** minta agen uji melakukan
  drag-and-drop/kamera/suara.
- E6.3b Tambah akun demo untuk peran baru di `bootstrap.py`/`seed_realistic.py`
  (`adminsales@kainnusantara.id`, `finance@kainnusantara.id`, + satu Admin Sales yang
  ditugaskan ke 2 entitas) dan catat di `memory/test_credentials.md`.
- E6.4 Perbarui `ENTITY_REGISTRY.md` (business_entities lengkap + warehouses.sharing_mode +
  koleksi yang berubah SHARED→SCOPED), `CODEBASE_MAP.md` (berkas baru), `SESSION_HANDOFF.md`,
  dan `plan.md` (status fase).

#### STATUS E-6 — **SELESAI** (sesi 2026-08-15, repo `wauaualaja/kn`)

| Butir | Status | Bukti |
|---|---|---|
| E6.1 POC entitas gabungan | **SELESAI** (dipecah, bukan satu berkas) | `test_core_e0_isolation_poc.py` · `test_core_e1e2_poc.py` · `test_core_e3_write_guard_poc.py` · `test_core_e4_*` · `test_core_e5_visibility_poc.py` · `test_core_e7_interco_poc.py` — semua terdaftar di `gate.sh --full` |
| E6.1b POC peran (6 peran × matriks izin) | **SELESAI** | `test_core_e8_roles_poc.py` (G1) + `test_core_e8_desk_poc.py` (G2/G3) **97/97** |
| E6.2 audit isolasi 0 kebocoran + gate hijau | **SELESAI** | `audit_entity_isolation` 0 kebocoran · `verify_api_contract` 0/0 · `check_nav_map` PASS 94 layar · `audit_i18n_id` 0 temuan |
| E6.3 agen uji user story di browser | **SELESAI** | iterasi 221 · 222 · putaran-3 (**31/31**, 0 error konsol) |
| E6.3b akun demo peran baru | **SELESAI** | `salesadmin@` (2 entitas) · `finance@` · `sales2@` · `sales3@` — tercatat di `memory/test_credentials.md` |
| E6.4 dokumen diperbarui | **SELESAI** | `plan.md` §8 · `SESSION_HANDOFF.md` · `memory/SESSION_LOG.md` · `memory/HANDOFF.md` |

**Bukti penutup terukur:** `gate.sh --full` **57 gate HIJAU** (224s) ·
`verify_data_integrity` **236 PASS / 0 FAIL / 0 WARN** · POC E-8 G2/G3 **97/97** ·
POC E-9 **44/44** · agen uji putaran-3 **31/31**.

**Dua bug nyata yang ditutup di fase ini** (kelas "hanya terlihat di layar"):
`KN-E6-DASH-SALES-LEAK` (dasbor lupa `sales_ownership` → pesanan rekan bocor ke sales) dan
`KN-E6-DERIVED-FROM-LIST` (field turunan `interco_supply` dibaca dari respons DAFTAR →
pita "dipenuhi dari badan usaha lain" tak pernah tampil, tanpa error). Keduanya diberi
**pagar anti-regresi**: cek `sales_ownership` di POC E-8 + gate statik baru **`INV-UI-04`**
(`guard:derived_fields`).

**Pelajaran metodologis (jangan diulang):** kelas bug #2 lolos SEMUA gate API dan SEMUA POC
backend karena endpoint detailnya memang benar — yang salah adalah **sumber data di layar**.
Sejak sesi ini gate `INV-UI-04` memeriksa hal itu secara statik.

---

## 4) USER STORY (dipakai agen uji sebagai acuan)
1. Sebagai admin, saya menambah **usaha perorangan** "Toko Kain Berkah" lewat wizard 4 langkah,
   melihat pratinjau nomor `BERKAH/SO-00001`, dan mendapat daftar kesiapan yang bisa diklik.
2. Sebagai admin, saya **mengubah** alamat & kop surat entitas yang sudah jalan, tetapi
   **tidak bisa** mengubah kode dokumennya karena sudah menerbitkan faktur — dan sistem
   menjelaskan alasannya.
3. Sebagai admin, saya mencoba menonaktifkan entitas yang masih punya 3 pengguna & 12 dokumen
   terbuka → ditolak dengan rincian; setelah saya pindahkan penggunanya, entitas bisa
   diarsipkan dan **tidak bisa lagi menerima transaksi baru**.
4. Sebagai admin, saya membuat akun baru dengan memilih **karyawan dari HR**; entitasnya
   terisi otomatis dari HR dan tidak bisa saya ubah sembarangan.
5. Sebagai sales yang hanya ditugaskan di CV Kanda Suka, saya **tidak menemukan** satu pun data
   KSC di seluruh aplikasi — termasuk notifikasi, target & insentif saya, denda, piutang, lot,
   dan jejak audit (yang bahkan tidak boleh saya buka).
6. Sebagai sales yang ditugaskan di 2 entitas, saya berpindah entitas dan **seluruh layar**
   (pesanan, pelanggan, stok, harga, laporan) berganti isi — nomor dokumen barunya ber-prefix
   entitas yang sedang aktif.
7. Sebagai admin dalam mode **"Semua Entitas"**, saya bisa melihat gabungan tetapi **tidak
   bisa** membuat dokumen; sistem meminta saya memilih satu entitas dulu.
8. Sebagai admin, di Pusat Pengaturan saya melihat dengan jelas mana nilai **Global** dan mana
   **Entitas ini**, bisa menimpa PPN untuk satu entitas non-PKP, dan bisa mengembalikannya ke global.
9. Sebagai admin, saya menetapkan **harga khusus** satu produk untuk CV Kanda Suka; sales Kanda
   melihat harga itu, sales KSC tetap melihat harga global (dengan lencana asal harga).
10. Sebagai manajer, laporan piutang menampilkan angka **per entitas** dengan nama entitas
    tertulis, dan mode gabungan diberi label tegas.

### User story FASE E-8 (Sales vs Admin Sales)
11. Sebagai **sales lapangan**, saya membuka daftar pesanan dan **hanya melihat pesanan saya**;
    pesanan rekan tidak ada di layar saya.
12. Sebagai **sales**, saya membuka satu pesanan dan melihat **perjalanan barangnya**
    (dipesan → divalidasi → disiapkan → dikirim → diterima → ditagih → dibayar), termasuk
    keterangan "kekurangan 200 yard dipenuhi lewat `PO-00012`" atau "diambil dari
    PT Kain Suka Cita lewat `KANDA/IC-00005`" — **tanpa** bisa menyentuh layar gudang.
13. Sebagai **sales**, saya melihat stok **hanya milik entitas saya** (7 yard), bukan 788 yard
    milik PT lain; bila barang kurang saya menekan **"Minta dari PT lain"** dan permintaan
    itu masuk ke antrean Admin Sales.
14. Sebagai **sales**, saya **tidak lagi menemukan** tombol terbitkan Faktur Pajak, catat
    kwitansi, atau putuskan selisih bayar.
15. Sebagai **Admin Sales**, saya membuka **Meja Admin Sales** dan melihat antreannya dengan
    jumlah: perlu diverifikasi · siap dikonfirmasi · menunggu manajer · siap cetak Surat
    Jalan/Invoice · perlu dipenuhi (kurang stok) · jatuh tempo · retur · permintaan internal
    dari sales. (Faktur pajak & pencatatan uang masuk **bukan** di meja saya — itu Finance.)
16. Sebagai **Admin Sales**, pada `SO-0009` yang kurang 200 yard saya memilih salah satu dari
    **3 tombol**: *Ambil dari PT lain* (lahir transaksi antar-PT **bertaut SO ini**) ·
    *Reorder ke supplier* (lahir PR bertaut SO ini) · *Tahan untuk barang masuk* (pegging).
17. Sebagai **Admin Sales**, saya **memverifikasi** kelengkapan SO (alamat, syarat bayar,
    pajak, dokumen) lalu **mengonfirmasi** SO sehingga tugas gudang lahir — **tanpa**
    menunggu manajer, sementara harga khusus/kredit/nilai besar tetap keputusan manajer.
18. Sebagai **Admin Sales**, retur yang **diajukan sales** masuk ke antrean saya, saya proses
    dokumennya (barang kembali, nota kredit), dan persetujuan akhirnya tetap manajer.
19. Sebagai **manajer**, saya tidak lagi dibebani konfirmasi SO rutin; antrean saya hanya
    berisi keputusan (harga khusus, kredit, nilai besar, pembebasan denda, settlement).
20. Sebagai **Finance/Kasir**, meja saya berisi: **siap terbitkan Faktur Pajak** · **uang
    masuk perlu dicatat & dialokasikan ke invoice** · **selisih bayar** (dalam batas
    kewenangan saya) · **denda perlu diterbitkan** · **jatuh tempo**. Saya **tidak bisa**
    membuat atau mengonfirmasi SO.
21. Sebagai **admin sistem**, saya menugaskan satu Admin Sales ke **2 entitas** (KSC + Kanda)
    dan dia bisa berpindah konteks; Admin Sales lain saya kunci ke 1 entitas dan dia tidak
    menemukan data entitas lain sama sekali.
22. Sebagai **Admin Sales**, saya memutuskan "ambil dari PT lain" untuk `SO-0009`
    **tanpa menunggu persetujuan manajer**; bila pemilik menyalakan ambang rupiah di Pusat
    Pengaturan, transaksi di atas ambang otomatis meminta persetujuan tanpa perubahan kode.

### User story FASE E-9 (rantai jual → beli internal → retur berantai)
23. Sebagai **Admin Sales**, saat barang dari Entitas B **diterima**, pesanan Customer A yang
    tadinya "menunggu stok" **otomatis terpenuhi** dan saya diberi tahu — tanpa alokasi manual.
24. Sebagai **Admin Sales**, di layar pesanan saya melihat "kekurangan 200 yard **diambil dari
    PT Kain Suka Cita** lewat `KANDA/IC-00005`", dan di Papan Pending SO tanggal janjinya ikut
    tampil.
25. Sebagai **Admin Sales**, ketika memproses retur Customer A atas barang yang dulu dibeli
    internal, sistem **mengarahkan saya ke Retur Antar-PT** dan **menolak** jalur pindah
    kepemilikan at-cost, dengan alasan yang dijelaskan.
26. Sebagai **Admin Sales**, roll yang dikirim balik ke Entitas B adalah **roll cacat hasil
    retur pelanggan** (lot `RTN-*`), bukan roll bagus dari stok saya.
27. Sebagai **Finance**, setelah retur antar-PT selesai, **saldo IC-AR/IC-AP kembali nol**,
    PPN keluaran/masukan ikut dibalik, dan eliminasi margin di konsolidasi ikut berkurang.
28. Sebagai **Admin Pembelian Entitas B**, roll yang kembali dari Entitas A **masih bisa saya
    retur ke supplier aslinya** (`Toba Craft`, `PO-00005`) karena jejak asalnya tidak hilang;
    bila barang impor tidak boleh diretur, sistem menyarankan REGRADE + jual lokal.
29. Sebagai **manajer**, satu layar **Jejak Retur** menunjukkan rantainya utuh: retur Customer A
    → retur Entitas A ke Entitas B → retur Entitas B ke supplier (atau "disimpan B").

---

## 5) URUTAN KERJA YANG DISARANKAN
`E-0` → `E-1` → `E-2` → `E-3` → `E-4` → `E-5` → **`E-7`** → **`E-8`** → **`E-9`** → `E-6` (uji & bukti penutup).
E-0 wajib pertama (menutup lubang yang sudah terbukti, termasuk **L21** yang membuat sales
menjanjikan stok PT lain). E-3 (UI) sengaja setelah E-1/E-2
supaya UI dibangun di atas kontrak API yang sudah rapi (hindari bongkar-pasang).
E-7 menunggu keputusan pemilik; bagian pagar-nya (E7.2) boleh naik ke E-0 bila pemilik setuju.

## 6) RISIKO & CARA MENJAGA
| Risiko | Penjagaan |
|---|---|
| Refactor SHARED→SCOPED memutus data lama | Setiap perubahan disertai migrasi backfill idempotent + hitung baris sebelum/sesudah |
| Nomor dokumen kembar saat prefix diubah | Kunci prefix + invalidasi cache + uji tabrakan paralel |
| Regresi kebocoran di modul baru | `scripts/audit_entity_isolation.py` masuk `gate.sh` (fail = merah) |
| UI ambigu (nilai global disangka milik entitas) | Lencana asal wajib + pita entitas aktif + uji agen uji khusus |
| Skala puluhan entitas | Paging + pencarian di daftar entitas, akun, dan pemilih entitas |

## 7) ALAT VERIFIKASI YANG SUDAH ADA (jangan dibuat ulang)
| Berkas | Fungsi |
|---|---|
| `scripts/entity_audit/audit_entity_isolation.py` | Sapuan 300 endpoint GET × 4 identitas → kebocoran, "sama antar-PT", IDOR, sebaran `entity_id` di DB. Output `.logs/audit_isolation_report.md` |
| `scripts/entity_audit/verify_leaks.py` | Bukti baris-demi-baris 11 kandidat kebocoran |
| `scripts/entity_audit/verify_leaks2.py` | Endpoint agregat (papan stok, neraca, AR aging) + master data shared/terpisah + harga |
| `scripts/entity_audit/probe_entity_flow.py` | Siklus hidup entitas: provisioning, duplikat, PATCH, deaktivasi, RBAC |
| `scripts/entity_audit/probe_entity_flow2.py` | Cacat akun: DELETE 405, email duplikat, turun jabatan, entitas nonaktif |
| `scripts/entity_audit/verify_interco.py` | **Cakupan ANTAR-ENTITAS**: meta & 7 kunci konfigurasi, dokumen kembar, saldo pasangan PT, netting, kontrak harga internal, margin, faktur pajak internal, retur antar-PT, jembatan gudang, konsolidasi & eliminasi, RBAC, kas/bank tingkat grup |
| `backend/tests/test_g6_poc.py` | POC antar-entitas resmi (**21/21**, pytest, self-cleanup) |
| `scripts/verify_data_integrity.py` | 233 invarian termasuk **INV-IC-01..08** (antar-entitas) |
| `backend/test_f0c_scoping_leak_poc.py` | POC isolasi resmi (28 PASS) — perluas, jangan ganti |
| `scripts/gate.sh` | 14 gate statik+POC · `scripts/rebuild_frontend.sh` wajib setelah ubah FE |

## 8) STATUS
- [x] **Sesi verifikasi (2026-08-10)** — penelusuran kode + audit empiris + keputusan pemilik + rencana ini.
- [x] **FASE E-0** — 21 kebocoran ditutup + pagar anti-regresi (POC E-0 hijau di `gate.sh`).
- [x] **FASE E-1** — model badan usaha, pagar siklus hidup, kunci prefix, kesiapan, nomor per-entitas.
- [x] **FASE E-2** — akun tertaut HR + penegakan akses (`routers/users.py`).
- [x] **FASE E-3** — layar "Badan Usaha & Akses" + pemilih badan usaha + **mode gabungan
      hanya-lihat** (`backend/entity_write_guard.py`, POC 26/26). Rincian di §FASE E-3.
- [x] **FASE E-4** — master & konfigurasi per badan usaha SELESAI SELURUHNYA
      (E4.1 gudang · E4.2 kop surat · E4.3 master berlapis · E4.4 bagan akun ·
      E4.5/E4.6 Pusat Pengaturan per badan usaha · E4.7 harga). Bukti: gate 34 hijau ·
      POC master berlapis 56/56 · agen uji frontend 12/12. Rincian di §STATUS E-4.
- [x] **FASE E-5** — visibilitas stok SELESAI (E5.1 papan stok agregat · E5.2 pegging ·
      E5.3 mutasi lintas-PT hanya nama singkat · **E5.3c kebocoran BARU Kartu Riwayat Produk
      ditutup**). Bukti: POC E-5 **52/52** (terbukti bisa memerah: 7 FAIL saat disabotase) ·
      `gate.sh --ci` HIJAU dengan gate E-5 baru · agen uji iterasi **216: frontend 23/23**.
      E5.4 dipindah ke E-8. Rincian di §STATUS E-5.
- [x] **FASE E-7** — antar-entitas SELESAI SELURUHNYA (E7a pagar lawan-transaksi-PT-sendiri ·
      E7b konsistensi · E7c HPP taksiran berlabel · E7d Permintaan Internal PIN ·
      E7e kas tingkat grup dihapus · E7f pinjaman antar-PT · E7g pindah aset tetap +
      **E7g-2 cacat "mengaku punya aset yang sudah pindah" ditutup**). Bukti: POC E-7
      **56/56** · `gate.sh --ci` HIJAU · agen uji iterasi **219** + verifikasi tangan
      agen utama untuk pinjaman & pindah aset. Rincian di §STATUS E-7.
- [x] **Sesi 2026-08-14 — gate MERAH G-6b ditutup di akarnya (prasyarat E-9).**
      `POC FASE G-6b test_c1` merah di gate penuh ternyata membongkar cacat **P0
      `KN-G6-ICA-CLOBBER`**: id baris `interco_accounts` dulu tanpa penanda peran, jadi
      *piutang arah A→B* & *utang arah B→A* menempati SATU dokumen — begitu dua PT
      berdagang **dua arah** (Permintaan Internal / pinjaman / pindah aset antar-PT),
      utang **Rp 1.766.010** hilang dari layar tanpa pesan. Ikut ditutup: celah invarian
      **INV-IC-02/04** (dulu hanya memeriksa baris yang ADA → keadaan uang-hilang tetap
      *PASS 8 · FAIL 0*) dan celah residu **POC E-7d** (dokumen kembar `KANDA/IC-#####`
      menumpuk tiap gate; koleksi antar-PT belum dipantau `gate_residue.py`).
      Bukti: bukti-merah POC baru `test_c4_dua_arah_dagang_tidak_saling_menimpa_saldo` ·
      `gate.sh --full` **HIJAU 54/54 dua kali** · POC G-6b 16/16 · G-6 21/21 · E-7 57/57 ·
      integritas 229/0/0. Migrasi: `scripts/migrate_g6b_ica_directional.py`.
      **Catatan penting untuk E-9:** rantai E-9 memang menciptakan arah dagang dua arah
      pada pasangan PT yang sama, jadi tanpa perbaikan ini E-9 akan menghapus saldo sendiri.
- [x] **FASE E-8** — domain sales · admin sales · finance SELESAI (peran `sales_admin` &
      `finance` + registry peran · pemisahan tugas SD2 · kepemilikan data sales E8.4 ·
      Meja Admin Sales & Meja Finance berbasis antrean · tautan SO ↔ Antar Entitas ·
      tahap `verified_by_sales_admin` · perjalanan pesanan untuk sales). Bukti: POC E-8 G1
      hijau · **POC E-8 G2/G3 meja kerja 97/97** · agen uji iterasi 221/222.
- [x] **FASE E-9** — rantai jual → beli internal antar-PT → retur berantai SELESAI
      (pemenuhan otomatis saat barang masuk · pita "dipenuhi dari badan usaha lain" ·
      jalur at-cost DIBLOKIR & menuntun ke Retur Antar-PT · roll `RTN-*` yang dikirim balik ·
      IC-AR/IC-AP kembali nol · retur lanjutan ke supplier asli · layar **Jejak Retur**).
      Bukti: **POC E-9 rantai retur 44/44** · `seed_e9_chain_demo.py` (rantai bisa dibuka
      di layar) · agen uji iterasi 221/222/3.
- [x] **FASE E-6 — UJI & BUKTI PENUTUP SELESAI (sesi 2026-08-15, repo `wauaualaja/kn`).**
      E-6.1 lencana peran (titik `·` dipisah dari label) · E-6.2 POC meja kerja E-8 G2/G3
      didaftarkan sebagai gate + residu ditutup · E-6.4 `gate.sh --full` **57 gate HIJAU** ·
      E-6.5 agen uji putaran-1..3 **31/31** · E-6.7 dokumen diperbarui.
      **Dua BUG NYATA yang hanya bisa ditemukan lewat LAYAR — ditutup di akarnya:**
      1. **`KN-E6-DASH-SALES-LEAK` (US11)** — layar Pesanan tidak memakai `GET /sales-orders`
         melainkan `orders[]` dari `GET /dashboard`, dan dasbor itu hanya menyaring per badan
         usaha (lupa `sales_ownership`) → `sales@` melihat `SO-0008` milik `sales2@` dan KPI
         berbunyi 9. Ditutup: `sales_ownership.apply_scope()` dipasang pada `orders` +
         `active_orders` di `routers/dashboard.py`.
      2. **`KN-E6-DERIVED-FROM-LIST` (US23/US24)** — `interco_supply` adalah field **turunan**
         yang hanya dihitung `GET /sales-orders/{id}`, tetapi panel detail membacanya dari
         objek hasil DAFTAR → blok JSX-nya **selalu di-skip tanpa error**. Ditutup: komponen
         `OrderIntercoSupplyPanel.jsx` mengambil datanya sendiri + **gate baru `INV-UI-04`**
         (field turunan tak boleh dibaca dari respons daftar) supaya kelas bug ini tak lahir lagi.
      **Verifikasi tangan agen utama (bukan hanya laporan agen uji):** `sales@` **8** pesanan
      tanpa `SO-0008` (KPI 8) · `sales2@` **tepat 1** (`SO-0008`) · `salesadmin@` tetap melihat
      seluruh pesanan badan usahanya · panel interco tampil untuk `admin@`/`salesadmin@`/`sales@`
      dengan bunyi "diambil dari CV Kanda Suka lewat `KSC/IC-00006`" dan **nol id teknis `ent_*`** ·
      nol error konsol aplikasi. Rincian di §STATUS E-6.
- **Semua keputusan pemilik sudah terkumpul** (§0 + E7.7 + E8.10/E8.10b).
- [x] **Utang migrasi (i) — DITUTUP (sesi 2026-08-15, repo `skskududu/KN`).** Alat migrasinya
      (`scripts/migrate_e7_group_cash.py --report/--apply`) sudah ada tetapi **belum pernah
      dibuktikan bekerja**, dan data demo hari ini **nol** baris tingkat grup — menjalankannya
      di data bersih hanya mencetak "tidak ada yang perlu dimigrasikan" (kebetulan, bukan bukti).
      Ditutup dengan POC `backend/test_core_group_cash_migration_poc.py` (**38/38**) yang
      MEMBUAT ULANG keadaan warisan (1 rekening "Kas Besar Grup" + 13 transaksi · 4 lapis bukti
      + 2 baris tak terbuktikan), menjalankan alatnya sungguhan, memeriksa baris demi baris,
      lalu memulihkan semuanya (nol residu). **POC ini menemukan cacat nyata di alatnya:**
      baris yang pemiliknya diputuskan ORANG lewat kasus keuangan `salah_entitas` tetap
      menunjuk rekening **GRUP**, sehingga rekening itu tak pernah bisa dinonaktifkan dan uang
      yang sudah punya pemilik duduk di rekening yang konsepnya sudah dihapus → ditambah
      **sapuan kedua** (pindah `account_id` ke cermin badan usaha). Keputusan pemilik untuk
      2 baris tanpa bukti: *"anda atur saja, ini masih demo"* → ditetapkan milik KSC.
- [x] **Utang migrasi (ii) — DITUTUP.** Layar "Cek Peran" berbasis bukti + endpoint terap +
      POC `backend/test_core_role_reality_poc.py` sudah menjadi gate (dikerjakan sesi
      2026-08-15 gelombang pertama; diverifikasi ulang HIJAU di `gate.sh --full` sesi ini).
- [x] **Diparkir → DIKERJAKAN & DITUTUP (sesi 2026-08-15, repo `skskududu/KN`):** analisis
      akses & UI/UX **sales vs admin-sales**, diperluas ke **6 peran** atas bukti bahwa kelas
      cacatnya tidak eksklusif dua peran itu. Rincian di §STATUS F (di bawah).

---

## §STATUS F — SESI 2026-08-15 (repo `skskududu/KN`): AUDIT PERAN · KPI JUJUR · UTANG MIGRASI

> Titik henti sesi lalu: **tepat setelah** mendaftarkan `scripts/audit_sales_roles_ux.py`
> sebagai gate; `gate.sh --full` **MEMERAH di 2 gate**. Keduanya ditutup **di akarnya**
> lalu pekerjaan yang diparkir diselesaikan. Bukti penutup: `gate.sh --full`
> **65 gate HIJAU** (`memory/GATE_RECEIPT.md`) · agen uji frontend **8/8 user story**.

### F-0. Dua gate merah — akar & obatnya
| Gate merah | Akar sebenarnya | Obat |
|---|---|---|
| `guard:auth_coverage` menuduh `GET /sales-return-policies/{policy_id}` tanpa auth | **Tuduhan palsu.** Endpoint itu memakai `require_any_permission` (enforcer "salah satu dari", E-9), tetapi daftar enforcer keras di penjaga hanya mengenal `require_permission`/`require_role` — dan `"require_permission("` **bukan** substring `"require_any_permission("`. Bahaya dua arah: (a) gate merah pada kode benar → penjaganya dimatikan orang; (b) dulu endpoint yang HANYA memakai enforcer itu lolos **karena alasan salah** (kebetulan juga memanggil `entity_ctx`, enforcer LUNAK) → begitu `entity_ctx` dihapus, endpoint tanpa auth pun tetap lolos | `require_any_permission` masuk daftar KERAS + pencocokan **batas kata** (`\bnama\s*\(`) + **`--self-test` 8 kasus** (bukti-merah) yang mengunci kedua arah, didaftarkan sebagai gate baru |
| `INV-GATE-01` anti-residu: `audit_logs` +2 dok tiap gate | Audit baru mengetuk HTTP nyata; tiap `POST /auth/login` menulis satu baris jejak audit. Aturan repo untuk gate runtime: snapshot DB sebelum uji & pulihkan di `finally` | `audit_sales_roles_ux.py` dibungkus `run_with_restore(main)` (`scripts/guardrails/_common.py`); `--self-test` tetap murni statik. Terukur: `audit_logs` 101 → 101 |

### F-2. Audit peran diperluas — dan "panel mati" kini MEMERAH
Audit lama hanya menilai 2 peran dan menganggap **panel mati** (sebagian endpoint layar 403)
sebagai peringatan kuning. Di bawah warna kuning itu hidup **11 kasus nyata**. Sekarang:
- **6 peran** diaudit (`sales`, `sales_admin`, `finance`, `warehouse`, `manager`, + `admin`
  sebagai KONTROL karena berizin `*` — temuan pada admin berarti auditnya sendiri salah).
- **Panel mati = TEMUAN** (gate merah), bukan peringatan.
- Pembebasan "sudah dipagari di kode" kini berkunci **`(layar, path)`**, bukan `path` global —
  kunci global dulu memaafkan `/suppliers` di layar RFQ hanya karena wizard Kontrabon dipagari.
- **Izin yatim** (izin tulis tanpa pintu di layar) dihitung dari bukti: peta
  `(modul, aksi) → endpoint` dibaca statik dari `routers/*.py` (**prefix `APIRouter` ikut
  dibaca** — tanpa itu `/api/pdf/render/...` terbaca `/render/...` dan `document.print`
  selalu terlihat yatim) lalu dicocokkan dengan seluruh URL `${API}/…` di frontend dengan
  pencocokan **wildcard dua arah** (`*` satu segmen, `**` sisa path untuk aksi dinamis seperti
  `` `${API}/purchase-requisitions/${pr.id}${path}` ``). Hasil: **58 tuduhan palsu → 1 sinyal
  jujur** (`approval.approve` — mesin persetujuan generik memang belum punya pintu; lihat F-3).

**11 temuan & obatnya** (keputusan pemilik: *"beri izin baca supaya menunya berguna"*):
| Peran | Layar | 403 | Obat |
|---|---|---|---|
| finance | Aging Piutang | `GET /ar/aging`, `/ar/aging/{id}` | Gerbangnya **berbasis izin**, bukan pangkat peran: `accounting.view` ATAU `penalty.issue` (dulu `require_role(["manager"])` — finance punya menunya DAN izin `penalty.issue`, tetapi tak boleh melihat layarnya) |
| finance | Kasus Keuangan | `GET /suppliers` | `finance + supplier.view` (hanya BACA) **+** daftar opsional dikeluarkan dari `Promise.all`: satu 403 dulu mengosongkan playbook/alasan/kebijakan/pelanggan/rekening sekaligus |
| warehouse | Permintaan Pembelian · RFQ · Retur Beli · Kontrabon | `GET /suppliers` | `warehouse + supplier.view` (peran ini SUDAH punya `rfq.create` & `purchase_requisition.create` tetapi dropdown Supplier-nya kosong tanpa pesan) |
| manager | Karyawan | `GET /users` | `manager + user.view` (hanya BACA; kolom "akun tertaut" dulu selalu kosong → terbaca "belum punya akun") |
| manager | Master Produk/Kategori/UOM | `/products/sales-owners`, `/admin/integrations` | Dipagari **di kode** (jangan memanggil yang tak boleh dipakai): fetch pemilik-produk dikunci `can(product.update)`; `<IntegrationsPanel>` hanya dirender di tab `integrations` |
| warehouse | Retur Beli (detail) | `/gl/cash-accounts` | Fetch akun refund dikunci `canApprove` (pemilihnya pun hanya dirender untuk penyetuju) |
| warehouse | Papan Stok · Kontrabon | `/internal-requests*`, `/bank-accounts` | Sudah dipagari di kode → didaftarkan beserta **alamat pagarnya** di `TERGATED_DI_KODE` |

Ikut ditutup (**INV-ROLE-01**): `ARAgingView` memakai `["admin","manager"].includes(role)`
untuk tombol "Buat Nota Denda" → peran `finance` yang memegang `penalty.issue` melihat
layarnya tanpa tombolnya (server mengizinkan, layar melarang). Kini `can(perms,'penalty','issue')`.

### F-3. FASE BARU (dipilih dari BUKTI KODE, bukan dokumen): **"Pusat Persetujuan = satu pintu yang jujur"**
`MASTER_ROADMAP.md` EPIC 0–6 terbukti sudah dikerjakan (costing/WAC, incentive v2 `per_sku`,
POS, doc-trace, budget+komitmen ada di kode); sisa backlog EPIC 7 **multi-currency/FX**
**tidak** dipilih karena tak ada bukti kebutuhannya (semua supplier domestik, `currency` nol
di PO/supplier, `landed_costs` kosong) — membangunnya berarti menebak. Yang dipilih adalah
cacat yang **terukur** dan muncul dari audit di atas:

- **`KN-F3-KPI-LIES` (P1 senyap)** — KPI "Persetujuan Menunggu" **selalu 0** karena menghitung
  koleksi `approval_requests` yang **tak pernah diisi siapa pun** (`create_approval_request()`
  nol pemanggil), sementara daftar rincian di layar yang sama berbunyi **6** dan kenyataan
  **17**. Satu pertanyaan, tiga angka — dan yang di beranda paling salah.
- Obat: **satu sumber** `backend/services/approval_backlog_service.py` (`QUEUES` = 13 antrean
  nyata, tiap baris menunjuk layar yang ADA) dipakai KPI beranda, rincian beranda, **dan**
  endpoint baru `GET /api/approvals/backlog` (izin `approval.view` / `order.approve`).
- **Control Tower**: KPI jadi **17** (dari 0), berpenjelasan ("Terbanyak: Pesanan pembelian
  (3) · klik untuk buka"), **bisa diklik**, plus panel **"Antrean Persetujuan (17)"** berisi
  baris-baris yang bisa diklik ke tempat kerjanya.
- **Pusat Persetujuan**: ringkasan "Menunggu keputusan (semua jenis): N" + catatan jujur
  **"X di antaranya ditangani di layar lain"** + chip per antrean; chip yang di luar wewenang
  peran **nonaktif** (bukan tautan buntu — tujuan dinilai `resolveDeepLinkTarget`, sumber yang
  sama dengan Ctrl+K & deep-link).
- Ikut ketangkap saat KEDUA angka dipasang di satu layar: baris `amendment` menyebut koleksi
  `amendments` padahal namanya **`doc_amendments`** (`amendments` cuma nama route) → satu
  antrean hilang tanpa pesan. Kelas itu sekarang dijaga invarian **E** di penjaga baru.
- **Gate baru `INV-HOME-01`** (`scripts/guardrails/verify_home_kpi.py`, 6 invarian A–F +
  `--self-test`): KPI == rincian == hitung-ulang mandiri dari MongoDB; anti "angka mati";
  anti layar hantu; anti salah-nama-koleksi; antrean baru wajib punya opini kedua.

### F-4. Bukti penutup sesi ini
`gate.sh --full` **65 gate HIJAU** (dari 61 gate dengan 2 MERAH) · POC F-2 akses peran
**43/43** (termasuk bukti-merah: mencabut izin → POC memerah) · POC F-1b migrasi kas
**38/38** · `audit_sales_roles_ux` **nol layar & panel mati untuk 6 peran** ·
`verify_data_integrity` **236/0/0** · agen uji frontend **8/8 user story** (US-A…US-H) ·
verifikasi tangan agen utama di layar nyata (Control Tower 17 & Pusat Persetujuan
"6 ditangani di layar lain"). Angka antrean **tersaring badan usaha** dan bisa dijelaskan:
KSC **15** · Kanda **2** · gabungan **17**.

### F-5. Berikutnya (usulan berbasis bukti, untuk keputusan pemilik)
1. **Pintu untuk mesin persetujuan generik** — `approval.approve` masih satu-satunya "izin
   yatim" jujur: `POST /approval-requests/{id}/approve|reject` ada, produsennya tidak
   (`create_approval_request()` nol pemanggil). Pilih: hidupkan (aturan ambang → dokumen
   generik) **atau** cabut endpoint+izinnya supaya wewenang di kertas tidak menumpuk.
2. **Kirim dokumen via email (SMTP)** — satu-satunya backlog EPIC 7 yang benar-benar belum
   ada dan grounded (pelanggan/supplier sudah punya kolom `email`; pengiriman baru WhatsApp).
   Butuh kredensial SMTP pemilik.
3. **Ambang persetujuan antar-PT (US22) diuji di layar** — mekanismenya ADA
   (`antar_entitas.approval_threshold_rupiah` → status `waiting_approval`), sekarang antreannya
   sudah terhitung di KPI; belum pernah diuji lewat layar dari ujung ke ujung.

---

## §STATUS F-6 — SESI 2026-08-17 (repo `ndizucufjs/KN`): GATE MERAH DITUTUP · MESIN PERSETUJUAN GENERIK DIPENSIUNKAN · 14 ANTREAN NYATA MASUK HITUNGAN

> Titik henti sesi lalu (diverifikasi ulang, bukan dibaca): `gate.sh --full` **MEMERAH di 1 gate**
> — `INV-GATE-01` anti-residu: `audit_logs` **99 → 102 (+3)**. Pilihan pemilik sesi ini:
> **(1) tutup gate merah dulu**, lalu **(2) fase §F-5 no.1 — mesin persetujuan generik**.
> Bukti penutup: `gate.sh --full` **69 gate HIJAU / 0 FAIL** (`memory/GATE_RECEIPT.md`) ·
> POC F-6 **43/43** · POC pengingat **26/26** · POC F-2 **43/43** · agen uji BE **47/47**, FE **21/22**
> (1 timeout skrip uji, bukan cacat produk — diverifikasi tangan sebagai admin & manajer).

### F-6.0 Gate merah — akar & obatnya (BUKAN dijinakkan)
| Gate merah | Akar sebenarnya | Obat |
|---|---|---|
| `INV-GATE-01` anti-residu: `audit_logs` +3 dok tiap `gate --full` | POC baru sesi lalu (`backend/test_core_approval_reminder_poc.py`) mengambil **snapshot DB SETELAH tiga `POST /auth/login`**, sehingga 3 baris jejak audit (+3 sesi) yang ditulis login berada **DI LUAR jendela snapshot** → `restore()` mustahil menghapusnya. Dibuktikan terisolasi: POC itu dijalankan sendirian → tepat **+3 `audit_logs`** | Snapshot & sidik jari diambil **SEBELUM** login; `sessions` masuk daftar koleksi tersentuh |
| **Bonus temuan** — POC yang sama berbunyi *"G7 nol residu — PASS"* | Pemeriksaannya hanya `ok(True, …)`: **hijau abadi yang tidak mengukur apa pun** — dan tepat di bawahnya residu +3 itu bersembunyi | G7 kini **MENGUKUR** (jumlah dokumen sebelum vs sesudah) + **bukti-merah sentinel**: satu dokumen sengaja disangkutkan → pengukur wajib MEMERAH, lalu dibersihkan |

### F-6.1 Keputusan §F-5 no.1: mesin persetujuan generik **DICABUT** (dipilih dari bukti)
Pilihannya "hidupkan **atau** cabut". Yang menentukan bukan selera, tetapi 5 bukti terukur:
1. `create_approval_request()` **nol pemanggil** → koleksi `approval_requests` **0 dok** selamanya,
   sementara `POST /approval-requests/{id}/approve|reject` ADA & izin `approval.approve` dipegang
   admin+manajer → **wewenang di kertas tanpa dokumen**. (KPI 0-padahal-17 di F-3 lahir dari sini.)
2. **Nol pemakai di layar**: tak satu pun berkas `frontend/src` memanggil `/approval-requests`.
3. Menghidupkannya **melanggar arsitektur**: tiap persetujuan nyata diputuskan di endpoint
   dokumennya sendiri (Pusat Persetujuan sengaja read-only) → mesin generik menjadi **jalur
   penulisan status KEDUA** untuk dokumen yang sama.
4. Endpointnya **tak berscope PT**: `list` tanpa saringan entitas; pada `get` bahkan
   `resolve_scope_ids()` dihitung lalu **tidak dipakai** → pagar multi-PT bocor di fitur mati.
5. **Penilai ambang kembar**: `check_approval_required()` menilai `approval_rules` padahal jalur
   HIDUP-nya `config_service.evaluate_approval()`/`build_approval_chain()` (dipakai SO & PO).

Yang dicabut: `routers/approval_requests.py` (5 endpoint) · fungsi request/keputusan di
`services/approval_service.py` (CRUD **aturan** tetap) · izin `approval.approve` di
`permissions_config.py` **dan** lewat `bootstrap.sync_permission_revocations()` — wajib, karena
matriks izin **tersimpan di MongoDB**: mengubah kode saja tidak mencabut apa pun di instalasi yang
sudah jalan (kelas cacat yang sama dengan E8.2). `approval.view` TETAP (membaca ≠ memutuskan).

### F-6.2 Gantinya: **14 antrean keputusan NYATA** masuk hitungan (17 → 22)
Sapuan bukti (endpoint `approve|reject|verify|decide` di KODE + sapuan status di DATA) menemukan
pintu keputusan yang sudah lama hidup tanpa satu pun baris antrean yang menghitungnya:

| Antrean baru | Koleksi · keadaan menunggu | Layar keputusan |
|---|---|---|
| Transfer gudang | `warehouse_transfers.waiting_approval` | Operasi Gudang |
| Kontrabon: verifikasi / persetujuan / sengketa | `contra_bons.submitted` / `.verified` / `.disputed` | Kontrabon |
| Permintaan internal antar-PT | `internal_requests.submitted` | Permintaan Internal |
| Retur antar-PT | `interco_returns.draft` (dual control: pembuat ≠ penyetuju) | Antar Entitas |
| Tagihan supplier | `vendor_bills.pending_approval` | Tagihan Supplier |
| Voucher biaya masuk | `landed_cost_vouchers.pending_approval` | Landed Cost |
| Uang muka & pertanggungjawabannya | `cash_advances.pending_atasan/pimpinan/finance` · `cash_advance_settlements.submitted` | Pengajuan Dana |
| Klaim makloon | `makloon_orders.steps.claim.status=pending_approval` | Klaim Selisih Makloon |
| Buka periode | `period_unlock_requests.pending` | Buka Periode |
| Cuti · Lembur | `hr_leave_requests.pending` · `hr_overtime.pending` | Cuti & Izin · Lembur |

Karena satu sumber (`services/approval_backlog_service.QUEUES`, kini **26 baris**), KPI beranda,
rincian beranda, Pusat Persetujuan, dan **pengingat harian** ikut jujur otomatis: **22** (KSC 20 ·
gabungan 22), diverifikasi tiga sumber (KPI == backlog == hitung-ulang mandiri dari MongoDB).

### F-6.3 Penjaga baru **INV-APPR-01** (`scripts/guardrails/verify_approval_queues.py`)
Kelas bug ini **tumbuh sendiri**: tiap fase menambah endpoint `approve` baru dan tak ada apa pun
yang memaksa penambahnya mendaftarkan antreannya. 6 invarian + `--self-test` **15/15**:
**A** tiap pintu keputusan di kode (50 pintu ditemukan otomatis) wajib terklasifikasi — menunjuk
antrean yang ADA, atau dibebaskan **dengan alasan tertulis** (pembebasan tanpa alasan = merah;
klasifikasi basi = merah) · **B** tiap `(koleksi, status)` "menunggu" di DATA wajib tercakup/dibebaskan
· **C** **anti dobel-hitung** (kelas nyata: `customer_prices` pending sudah terhitung lewat
`price_approvals` tertaut — mendaftarkannya lagi membuat KPI melebih-lebihkan) · **D** tanpa layar
hantu · **E** nama koleksi benar · **F** anti-regresi: `approval_requests` tak boleh kembali tanpa produsen.

Ikut diperbaiki (penjaga yang **menuduh palsu** akan dimatikan orang): invarian "koleksi harus ADA di
database" di `verify_home_kpi.py` & `test_core_role_access_poc.py` diganti **"ada di database ATAU
disebut literal di kode backend"** — fitur yang belum pernah dipakai di data demo (uang muka, biaya
masuk, buka periode) belum punya koleksi walau kodenya benar; salah tulis (`amendments` vs
`doc_amendments`) tetap tertangkap.

### F-6.4 Layar: antrean lain berhenti jadi angka saja
`ApprovalInbox.jsx` (Pusat Persetujuan) kini memanggil `/approvals/backlog?oldest=15` dan menambah
panel **"Menunggu di layar lain — paling lama dulu"**: nomor dokumen + umur tunggu + tombol **"Buka
layarnya"** (nonaktif bila di luar wewenang peran, sumber penilaian sama dengan Ctrl+K).
Sebelumnya kalimat *"11 di antaranya ditangani di layar lain"* jujur tetapi **tak bisa dikerjakan**.

### F-6.5 Ikut ditutup: dua 403 senyap di konsol manajer
Keputusan F-2 memberi `manager + user.view`; efek sampingnya manajer ikut memanggil `/permissions`
(`permission.view`) & `/audit-logs` (`audit.view`) → **4×403 tiap beranda dimuat**, ditelan `.catch()`
menjadi "matriks izin kosong" & "tak ada jejak audit". Kini tiap panggilan dipagari **izinnya sendiri**
di `hooks/useAppActions.js`. Terukur: konsol manajer **4 → 0** error/403.

### F-6.6 Catatan lingkungan (agar sesi berikutnya tidak tertipu)
- **JANGAN jalankan dua `gate.sh` bersamaan** — yang satu men-seed & mengosongkan koleksi sementara
  yang lain memverifikasi → gate merah **palsu** massal ("koleksi KOSONG"). Pakai
  `bash /app/.logs/run_gate.sh --full /app/.logs/gate_run.log` (ber-`flock`).
- `POST /auth/login` **ber-rate-limit**: uji beruntun bisa memicu **429** dan membuat
  `seed_realistic.py` melewati `seed_contra_bons`/`seed_interco` (hanya `[warn]`, senyap).
  Obat: `db.login_attempts.delete_many({})` lalu seed ulang.

### F-6.7 Berikutnya (usulan berbasis bukti, menunggu keputusan pemilik)
1. **Utang alur yang sekarang TERCATAT di penjaga** (dibebaskan beralasan, bukan disembunyikan):
   payroll & desain diputuskan dari status `draft` (tak ada langkah "ajukan" → draf tak bisa
   dibedakan dari yang siap disetujui) · keputusan selisih pembayaran belum punya status dokumen ·
   verifikasi administratif SO belum punya baris antrean sendiri.
2. **Kirim dokumen via email/SMTP** (butuh kredensial pemilik) — satu-satunya backlog EPIC 7 grounded.
3. **Ambang persetujuan antar-PT (US22) diuji dari ujung ke ujung lewat layar.**

---

## §STATUS P4 — SESI 2026-08-17 (lanjutan): **TOMBOL "BUAT" JADI POP-UP YANG KONSISTEN**

> Permintaan pemilik: *"P4 — form Buat jadi modal (~15 layar masih form inline) lanjutkan ini"*.
> Bukti penutup: `gate.sh --full` **71 gate HIJAU / 0 FAIL` · agen uji frontend **10/10 user story,
> nol isu** · konsol browser **0 error**. Rincian teknis di `PERF_UX_AUDIT.md §P4`.

### P4.0 Angka "±15 layar" diperiksa dulu — ternyata **10**
Dokumen audit menyebut ~15 view inline. Alat ukur baru (`scripts/audit_create_modal.py`)
menghitung dari KODE: **inline 12 tombol di 10 layar** (sisanya sudah dikonversi sesi-sesi lalu),
**36 sudah pop-up**, **7 pindah halaman** (alur kompleks, keputusan pemilik), **0 tombol mati**.
Melapor "15" tanpa mengukur = memperbaiki hal yang sudah beres.

### P4.1 Satu standar: `components/FormModal.jsx`
Kepala menempel · badan scroll · kaki menempel · **Esc menutup** · scroll latar dikunci · fokus
otomatis ke isian pertama · **galat di dalam modal** · backdrop `overlayDismiss()` (INV-UI-01) ·
**tidak membungkus ulang** komponen yang sudah punya `<form>` sendiri (anti form-di-dalam-form).

### P4.2 Sepuluh layar dikonversi (logika form tidak diubah)
Supplier · Daftar Harga Supplier · Kebijakan Retur · Unit Organisasi (HRD) · Kas · Retur Beli ·
**Retur Jual** (dulu MENUKAR seluruh halaman sehingga daftar & ringkasan hilang) · Aturan
Persetujuan · Transfer Gudang · Master Data (AdminView, tombolnya dulu ikut hilang saat form buka).
Hasil terukur: **inline 12 → 0**.

### P4.3 Gate baru `INV-UI-05` — supaya tidak balik lagi
`scripts/audit_create_modal.py` (+`--self-test` 7 kasus bukti-merah) terdaftar di `gate.sh`:
create **inline baru**, **pindah halaman tanpa keputusan tercatat**, atau **tombol mati**
(state dinyalakan tapi tak pernah dirender) = **MERAH**; tiap pengecualian wajib ber-ALASAN.
Penjaganya sendiri sempat **menuduh palsu** dua kali saat dibuat (7 layar benar terbaca "inline";
`setForm({…})` dianggap membuka pintu) → detektornya diperbaiki lebih dulu sebelum dipakai menilai.

### P4.4 Sisa PERF/UX sesudah ini
**P5 (belum)**: `ux_audit` **22 ERROR / 37 WARN di 17 berkas** (loading/empty/chart baseline) +
`window.alert/confirm` **21×** → ganti `notice bar`/`ConfirmModal`.
**Sisa P2 (belum)**: paginasi Retur Jual · Retur Beli · Pesanan (OrdersView) · Jurnal GL.

---
## §STATUS P5 + SISA P2 — SESI 2026-08-17 (lanjutan): **DIALOG BAWAAN PERAMBAN DIHAPUS · PENJAGA UI DIBUAT JUJUR · PAGINASI 4 MODUL TERAKHIR**

> Permintaan pemilik: *"lanjutkan development dari repo ini"* → titik henti P4 diverifikasi
> sendiri lebih dulu (`gate.sh --full` **71 HIJAU**, dijalankan ulang dari nol). Pilihan
> pemilik: **P5 + sisa P2 sekaligus**, dengan pola **galat = bilah menempel · berhasil =
> toast**, dan **alasan wajib untuk aksi berdampak uang/stok**.
> Bukti penutup: `gate.sh --full` **75 gate HIJAU / 0 FAIL** · agen uji **backend 11/11 ·
> frontend 0 bug UI** · residu data uji **nol**. Rincian teknis: `PERF_UX_AUDIT.md §P5`.

### P5.1 Dua angka warisan diukur ulang, dua-duanya salah
- "alert 40× & confirm ~21×" → sebenarnya **alert 36 · confirm 21 · prompt 4 = 61** dialog
  di 21 berkas. `prompt()` tak pernah dihitung padahal satu di antaranya meminta **kata
  sandi baru sebagai teks terbuka** di kotak bawaan peramban (`AccountList`).
- Gate P4 bilang create-inline **0**; nyatanya **3** masih inline (Buat PO · Ajukan Harga
  Khusus · Tambah Stok Awal). Penjaganya buta pada form yang isiannya dipindah ke **berkas
  ANAK**. Detektor diperbaiki + 5 self-test baru, lalu ketiganya dikonversi jadi pop-up.

### P5.2 Satu standar pengganti (bukan 21 cara berbeda)
`services/confirmService.js` (`askConfirm`/`askReason`/`askText`) + satu `<ConfirmHost/>`
di root · `utils/feedback.notifySuccess()` · `ErrorNotice` yang menggeser dirinya ke dalam
pandangan · galat form/aksi tampil **di dalam pop-upnya sendiri**. Nilai kembali sengaja
beda tipe supaya "batal" & "lanjut tanpa alasan" mustahil tertukar. **Tidak ada**
`notifyFailure()` — jalan mudah melaporkan gagal lewat toast adalah kebiasaan yang justru
sedang dihapus.

### P5.3 Alasan yang ditanyakan BENAR-BENAR disimpan
5 endpoint diberi `reason` (opsional di API, wajib di layar) → tersimpan di dokumen &/atau
Jejak Audit: batal transfer · void kwitansi AR · hapus eliminasi konsolidasi · hapus tarif
insentif · posting true-up persediaan. **Temuan ikutan:** void kwitansi AR (membalik uang
masuk pada order + kas + deposit) sebelumnya **tidak menulis audit sama sekali**.

### P5.4 `ux_audit` dibuat jujur DULU, baru dipatuhi
Dari 22 "ERROR": **17 tuduhan palsu** (komponen penampil dituduh tanpa loading; penjaga
`length > 0` & pesan di komponen anak tak dikenali; kata dalam **kalimat JSX** dihitung
sebagai indikator; nama state berimbuhan tak dikenali; W1 kehilangan kata "kolom" dari
standarnya). Detektor dibuat sadar-rujukan + `--self-test` **16 kasus dua arah**, lalu
**5 gap NYATA** diperbaiki (semuanya "tidak ada data = halaman kosong tanpa satu kalimat")
→ **0 ERROR**. `ux_audit --strict` kini **gate**, bukan skrip manual.

### P5.5 Gate baru `INV-UI-06` (anti kambuh)
`alert/confirm/prompt` bawaan peramban = MERAH; `<ConfirmHost/>` wajib ter-mount (tanpa itu
penggantinya gagal SENYAP). Self-test **17 kasus** termasuk anti-tuduh-palsu untuk kata
"alert" **di dalam string** dan fungsi yang kebetulan bernama `confirm`. Bukti-merah pada
kode lama: **61 pelanggaran, exit 1**.

### P2 (sisa) — 4 modul terakhir dipaginasi
Retur Jual · Retur Beli (+2 endpoint `status-counts` agar lencana tidak menyusut mengikuti
halaman) · Pesanan (kartu ringkasan pindah ke `/sales-orders/stats/summary` +
`backorder_count`; tab Dasbor sengaja tetap memakai daftar penuh karena analitik satu
halaman bercerita salah) · Jurnal GL (dulu dipotong keras 500 baris **tanpa halaman
berikutnya**). Semua **OPT-IN** — tanpa `?page` bentuk respons tidak berubah.

### Sisa yang BELUM (untuk sesi berikutnya)
1. **9 WARN `ux_audit`**: `<select>` bawaan di 8 berkas → ganti komponen Select
   (`NotificationCenter`, `FixedAssetsView/Parts`, `StoreCreditView`,
   `AmendmentReasonsPanel`, `CaseDetailPanel`, `IntercoMarginPanel`, `ReturnDetailPanel`,
   `ReturnSettleModal`).
2. **Utang alur F-6.7**: payroll & desain diputuskan dari `draft` (butuh langkah "Ajukan") ·
   keputusan selisih pembayaran tanpa status dokumen · verifikasi administratif SO tanpa antrean.
3. **Kirim dokumen via email/SMTP** (butuh kredensial pemilik).
4. **Ambang persetujuan antar-PT (US22)** diuji ujung-ke-ujung lewat layar.
5. 3 layar masih "Segera Hadir": BOM Printing (`cs-bom`) · BI Sales · BI Stok.
6. **Widget mengapung "Bantuan & Panduan"** (kanan-bawah) bisa menutupi kontrol di dasar
   halaman panjang — terbukti menelan klik tombol paginasi pada uji otomatis. Belum diubah.

---

## §RENCANA P6 — SESI 2026-08-18: **DROPDOWN SERAGAM · UNDUH CSV PER DAFTAR BERHALAMAN**

> Titik henti P5 **diverifikasi ulang dari nol lebih dulu** (kontainer datang kosong → repo
> dipulihkan dari GitHub, `.env` platform tidak ditimpa): `gate.sh --full` **75 gate PASS /
> 0 FAIL / 0 SKIP**, `ux_audit --strict` **0 ERROR / 9 WARN**. Jadi fondasinya bersih.
>
> Pilihan pemilik untuk P6 (2 dari 6 usulan): **(a) Dropdown Seragam** + **(c) Unduh Per
> Halaman**. Keputusan detail dari pemilik:
>   · cakupan unduhan → **tanya pengguna saat menekan Unduh** ("Halaman ini" / "Semua hasil
>     filter"), bukan diputuskan diam-diam oleh program;
>   · format berkas → **pemisah `;` + BOM UTF-8** supaya klik-dua-kali langsung rapi di
>     Excel berwilayah Indonesia (dengan `,` semua kolom menumpuk jadi satu).

### P6.A Dropdown Seragam — angka warisan diukur ulang DULU (dan lagi-lagi salah)

`plan.md §STATUS P5` menulis "**9 WARN** `<select>` bawaan di **8 berkas**". Saya ukur ulang
dari kode: **13 dropdown bawaan di 9 berkas**. Sebabnya `ux_audit` melaporkan **satu WARN
per BERKAS**, bukan per dropdown — jadi "9 WARN" itu jumlah berkas, dan pekerjaan
sebenarnya **44% lebih banyak** dari yang tercatat. Peta tepatnya:

| Berkas | Dropdown |
|---|---|
| `components/NotificationCenter.jsx` | filter jenis notifikasi (1) |
| `features/finance/FixedAssetsParts.jsx` | kategori · akun GL aset · badan usaha (3) |
| `features/finance/FixedAssetsView.jsx` | tujuan pindah aset (1) |
| `features/finance/StoreCreditView.jsx` | pesanan untuk penukaran (1) |
| `features/finance/amendments/AmendmentReasonsPanel.jsx` | status alasan aktif/nonaktif (1) |
| `features/finance/cases/CaseDetailPanel.jsx` | alasan penolakan kasus (1) |
| `features/finance/interco/IntercoMarginPanel.jsx` | filter pasangan PT (1) |
| `features/purchasing/ReturnDetailPanel.jsx` | akun refund · grade barang kembali (2) |
| `features/sales/ReturnSettleModal.jsx` | gudang retur · akun refund (2) |

Penggantinya **bukan komponen baru**: `components/KNSelect.jsx` sudah dipakai **182 berkas**
— 9 berkas ini memang yang terakhir tertinggal. KNSelect sudah menangani hal yang mudah
terlewat (Radix melarang `value=""` → dipetakan ke sentinel; daftar ≥ 6 opsi otomatis
dapat kolom pencarian).

**Satu hal yang TIDAK boleh hilang saat konversi:** `NotificationCenter` memberi
`aria-label` pada `<select>`-nya. KNSelect belum meneruskan prop itu, jadi konversi naif
akan **menghapus label bagi pembaca layar**. Maka KNSelect ditambah pass-through
`aria-label` lebih dulu (aditif, aman untuk 182 pemakai lama).

**Penjaga anti-kambuh.** `ux_audit` sudah punya aturan W2 ("native `<select>`") dan sudah
menjadi gate sejak P5 — jadi rumah yang benar adalah **menaikkan W2 dari WARN ke ERROR**,
bukan menulis penjaga kedua yang memindai hal yang sama (dua tempat untuk satu aturan =
salah satunya akan basi). Tapi dinaikkan **hanya setelah detektornya dibuat jujur**:
sekarang W2 memindai **teks mentah**, sehingga kata `<select>` di dalam **komentar atau
string** pun akan dituduh. Diperbaiki ke sumber yang komentar/string-nya sudah dibuang
(`strip_comments_and_strings`, util yang sudah ada) + **self-test dua arah**.

### P6.B Unduh CSV — dipasang di SEAM yang sudah ada, bukan 11 salinan

Dua komponen bersama sudah ada dan dipakai semua daftar berhalaman:
`hooks/usePagedList.js` (fetch + filter + pencarian) dan `components/PaginationBar.jsx`
(kontrol halaman). Karena itu ekspor dipasang **di dua berkas itu saja**, lalu 11 pager
hanya menyetor definisi kolomnya.

**Kenapa CSV dibangun dari jalur data DAFTAR, bukan endpoint ekspor baru di backend.**
Pilihan lain adalah menulis ~11 endpoint `/export.csv` di backend. Itu ditolak karena
melahirkan **dua sumber kebenaran untuk satu filter**: begitu filter di layar berubah dan
query di endpoint ekspor tidak, berkas unduhan akan berisi jumlah baris yang **berbeda dari
yang dilihat pengguna** — dan tidak ada yang akan sadar sampai ada yang menyelisihkan
angkanya. Dengan menyusuri **endpoint daftar yang sama** memakai **params yang sama**,
paritas filter bukan sesuatu yang harus dijaga; ia **mustahil melenceng**. Kolomnya pun
didefinisikan di layar yang merender tabelnya, jadi isi berkas = isi yang terlihat.

- **B1 `utils/csvExport.js`** — pemisah `;`, **BOM UTF-8**, escaping RFC 4180 (tanda kutip
  digandakan; sel bermuatan `;`/kutip/baris-baru dibungkus), **desimal koma** untuk kolom
  angka (Excel ID), dan **penangkal CSV-injection**: sel yang dimulai `=`/`+`/`@`/tab/CR
  diawali kutip tunggal supaya Excel tidak mengeksekusinya sebagai formula.
- **B2 `askChoice()`** — dialog 3 keluaran (Halaman ini / Semua hasil filter / Batal).
  `askConfirm` cuma Ya/Batal dan `askReason` menuntut teks, jadi keduanya tidak cocok;
  ditambahkan ke standar P5 yang sama (`confirmService` + `ConfirmModal` + `ConfirmHost`)
  supaya **tidak ada cara ke-22** untuk bertanya kepada pengguna.
- **B3 `usePagedList.fetchAll()`** — menyusuri halaman dengan endpoint/params/pencarian
  **identik**, `page_size` = `MAX_PAGE_SIZE` (200) agar jumlah permintaan minimum, dengan
  laporan kemajuan, tombol batal, dan **batas aman** supaya daftar raksasa tidak
  menggantung peramban tanpa kabar.
- **B4 `PaginationBar`** — tombol **Unduh CSV** + status kemajuan, satu tempat untuk semua.
- **B5** 11 pager di 10 berkas menyetor kolom: Pelanggan · PO · Roll & Mutasi Persediaan ·
  Pesanan · Jurnal GL · Retur Jual · Retur Beli · Lot · Tagihan Supplier · Supplier.
- **B6 `AccountList`** punya pager **buatan sendiri** (bukan `PaginationBar`) → disatukan
  ke komponen bersama supaya ikut kebagian Unduh, dan supaya penjaga B7 tidak bolong.
- **B7 Gate baru `INV-UI-07`** — setiap `<PaginationBar>` **wajib** menyetor konfigurasi
  ekspor (pembebasan harus **beralasan tertulis**), dan util CSV wajib tetap `;` + BOM.
  Tanpa gate ini fitur ini hanya berlaku untuk 11 daftar hari ini dan **tidak akan ikut**
  ke daftar berhalaman berikutnya. Self-test dua arah + bukti-merah.

### Cerita pengguna yang harus lulus (bukan cuma kode jalan)
1. Sebagai **admin keuangan**, saya menyaring Jurnal GL lalu menekan **Unduh CSV** → saya
   ditanya "Halaman ini / Semua hasil filter", memilih *Semua*, dan berkasnya terbuka
   **rapi berkolom** di Excel saya (bukan menumpuk di kolom A).
2. Sebagai **admin keuangan**, saya mencari "Batik" di Pesanan lalu Unduh *Semua hasil
   filter* → jumlah baris berkas **sama** dengan angka "… dari N" di bilah paginasi.
3. Sebagai **pengguna pembaca layar**, filter jenis notifikasi tetap punya nama yang
   terbacakan setelah dropdown-nya diganti.
4. Sebagai **operator**, semua dropdown (gudang retur, akun refund, grade) terasa **sama**
   dengan dropdown di layar lain — termasuk bisa **mengetik untuk mencari** pada daftar
   panjang seperti akun kas & pesanan.
5. Sebagai **pemilik**, `gate.sh --full` tetap **0 FAIL**, dan `ux_audit` sekarang
   **0 ERROR & 0 WARN** — angka yang dicapai, bukan yang dikecualikan.

### Definisi selesai P6
`gate.sh --full` 0 FAIL (75 + gate baru) · `ux_audit --strict` **0 ERROR 0 WARN** ·
`<select` bawaan di `frontend/src` = **0** · 12 daftar berhalaman punya Unduh CSV ·
agen uji 0 bug · residu data uji **nol** (`INV-GATE-01`) · konsol peramban 0 error.


---

## §STATUS P6 — SELESAI (2026-08-18): **DROPDOWN SERAGAM · UNDUH CSV 12 DAFTAR · 2 BUG IKUTAN**

**Bukti penutup:** `gate.sh --full` **77 gate HIJAU / 0 FAIL / 0 SKIP** (dari 75; +2 gate
baru) · `ux_audit --strict` **0 ERROR 0 WARN** (dari 0 ERROR 9 WARN) · `<select` bawaan di
`frontend/src` = **0** · agen uji 2 ronde, ronde-2 **0 bug UI** · konsol peramban 0 error.
Rincian teknis: `PERF_UX_AUDIT.md §P6`.

### Yang dikerjakan
1. **13 dropdown bawaan → `KNSelect`** di 9 berkas (bukan "9 di 8 berkas" seperti catatan
   lama — `ux_audit` menghitung **per berkas**, bukan per dropdown). `KNSelect` lebih dulu
   diberi pass-through **`aria-label`**, karena tanpa itu konversi `NotificationCenter`
   akan **menghapus nama kontrol bagi pembaca layar** tanpa satu gate pun memerah.
2. **`ux_audit` W2 → E4/ERROR**, tapi detektornya diperbaiki DULU: versi teks-mentah
   **menuduh palsu `KNSelect.jsx` sendiri** (kata `<select>` di dalam komentarnya).
   +5 self-test (total 21).
3. **Unduh CSV di 12 daftar berhalaman**, dipasang di 2 berkas bersama
   (`usePagedList.fetchAll` + `PaginationBar`), bukan 12 salinan. Pengguna memilih cakupan
   lewat **`askChoice()`** (standar dialog P5, bukan cara ke-22); dialog **dilewati** bila
   kedua pilihan identik. Format: **pemisah `;` + BOM UTF-8**, desimal koma, escaping
   RFC 4180, penangkal CSV-injection (angka negatif sengaja tidak dirusak).
4. **`AccountList` disatukan ke `PaginationBar`** (dulu pagernya buatan sendiri — satu-satunya
   yang tak akan pernah kebagian tombol Unduh, dan lubang di penjaga baru).
5. **Gate baru `INV-UI-07`** — selain memeriksa setiap pager, ia **MENJALANKAN**
   `utils/csvExport.js` dengan Node (20 uji perilaku), karena semua kerusakan CSV bersifat
   perilaku dan SENYAP. Self-test 15 kasus termasuk bukti-merah lapis perilaku.
6. **2 bug nyata di luar permintaan:** (a) label Inggris "outstanding" di `StoreCreditView`
   yang selama ini lolos audit bahasa karena terpotong antar-ekspresi JSX; (b) **widget
   "Bantuan & Panduan" yang menelan klik** — `elementFromPoint` di tengah tombol
   "Berikutnya" mengembalikan `help-tours-button`, jadi laporan "paginasi rusak" sebenarnya
   **klik yang tertelan**. Diperbaiki dengan ruang aman `#main-content{padding-bottom:104px}`.
   Ini juga melindungi tombol **Unduh CSV** yang duduk di bilah yang sama.

### Paritas yang diuji (baris berkas == angka "… dari N" di bilah paginasi)
jurnal **105** · roll **59** · mutasi **52** · lot **32** · PO **14** · akun **10** ·
tagihan supplier **8** · pelanggan **5** · retur beli **3** — semuanya **persis sama**.

### Sisa yang BELUM (diperbarui — untuk sesi berikutnya)
1. ~~9 WARN `<select>` bawaan~~ → **SELESAI P6** (0 WARN, kini gate ERROR `E4`).
2. ~~Widget mengapung menutupi kontrol di dasar halaman~~ → **SELESAI P6**.
3. **Utang alur F-6.7**: payroll & desain masih diputuskan dari `draft` (butuh langkah
   "Ajukan") · keputusan selisih pembayaran tanpa status dokumen · verifikasi administratif
   SO tanpa antrean.
4. **Kirim dokumen via email/SMTP** — butuh kredensial pemilik (host/port/user/sandi/pengirim).
5. **Ambang persetujuan antar-PT (US22)** belum diuji ujung-ke-ujung lewat layar.
6. 3 layar masih "Segera Hadir": BOM Printing (`cs-bom`) · BI Sales · BI Stok.
7. **Riwayat alasan** (dari P5): alasan pembatalan/void belum tampil di dokumennya —
   masih harus dibuka lewat Jejak Audit.
8. Data demo: **1 dari 59 roll** tidak punya `roll_no` & `unit` (dibuat
   `seed_e9_chain_demo.py`). Bukan bug kode — CSV & layar sama-sama menampilkannya kosong,
   tetapi seed-nya sebaiknya dilengkapi supaya tidak terlihat seperti cacat ekspor.

### Jalur navigasi yang sempat menyesatkan agen uji (dicatat supaya tidak terulang)
- `AccountList` ada di `?view=entities-access` → **klik sub-tab "Akun & Akses"**.
- Tab Roll & Buku Besar persediaan ada di `?view=operations` → tab `wms-tab-stok` →
  `inventory-tab-rolls` / `inventory-tab-ledger` (BUKAN `?view=inventory-board`).

### Catatan alat ukur (supaya sesi berikutnya tidak mengejar hantu)
Menjalankan `python scripts/gate_residue.py --check` **secara manual sesudah**
`gate.sh --full` akan selalu melaporkan **3 `sales_order` "HILANG"**. Itu **bukan residu
data**: `gate.sh` menyimpan sidik jarinya di AWAL, lalu setelah pemeriksaannya sendiri ia
menjalankan FASE POC + `seed_realistic` untuk memulihkan data demo — dan
`seed_realistic` memberi **id acak** pada 3 dari 11 pesanan (`so_1b51fec7d7d0`, dst.),
sementara 8 lainnya ber-id tetap (`so_001`–`so_008`). Diverifikasi: jumlah pesanan
**11 sebelum & 11 sesudah** (tidak ada yang hilang), `verify_data_integrity`
**236 PASS / 0 FAIL / 0 WARN**. Pemeriksaan residu yang SAH adalah yang dijalankan
`gate.sh` sendiri di dalam rangkaiannya (dua-duanya PASS di `memory/GATE_RECEIPT.md`).
Bila ingin memeriksa manual, jalankan `--save` lebih dulu supaya baselinenya sezaman.

---

## §STATUS P7 — SELESAI (2026-08-18): **PANEL RINCIAN JADI POP-UP (9 LAYAR) + 7 KEBOCORAN ID ENTITAS**

**Pemicu:** keluhan pemilik yang sudah **berulang kali** disampaikan — klik baris di
`AR / Piutang & Umur` memunculkan rincian **di bawah tabel**, bukan pop-up, sehingga pada
tabel panjang pengguna bingung. Permintaan eksplisit: **periksa layar lain yang berpola
sama dan ubah semuanya**.

**Bukti penutup:** `gate.sh --full` **79 gate HIJAU / 0 FAIL / 0 SKIP** (dari 77) ·
agen uji **0 bug UI** (14/14) · `ent_` mentah di layar **0** · konsol **0 error**.
Rincian teknis: `PERF_UX_AUDIT.md §P7`.

### Kenapa ini lolos berkali-kali (akar masalahnya, bukan gejalanya)
FASE P4 mewajibkan pop-up **hanya untuk tombol "Buat/Ubah"** (`INV-UI-05`). Panel
**rincian** tidak dijaga siapa pun → tiap kali dilaporkan, diperbaiki satu layar, lalu
muncul lagi di layar lain. Yang hilang bukan perbaikannya, melainkan **penjaganya**.

### Yang dikerjakan
1. **9 layar** diubah jadi pop-up lewat shell baru `components/DetailModal.jsx`
   (AR/Piutang · Kas & Bank · Store Credit · Antar-PT · Landed Cost · RFQ · Tagihan
   Supplier · R&D Sample · R&D Spesifikasi). Shell sengaja **tanpa kepala sendiri** karena
   panelnya sudah punya judul + tombol aksi + tombol tutup → konversi = satu pembungkus.
2. **4 layar TIDAK diubah** karena memang master-detail 2 kolom (rincian di SAMPING daftar,
   tetap dalam pandangan): Pusat Kasus Keuangan · Kontrabon · Amandemen · Inbound Scan.
3. **Gate baru `INV-UI-08`** (19 self-test, sadar-berkas-anak & sadar-indentasi).
   Bukti-merah pada kode sebelum P7: **tepat 9 pelanggaran**.
4. **7 kebocoran `ent_ksc` ke layar diperbaiki** + pola `INV-UI-02` diperluas (dulu hanya
   menangkap `entity_id` sebagai CADANGAN, bukan yang dicetak LANGSUNG). Helper baru
   `entityShortFromCtx()`. Bukti-merah **7/7**.

### Catatan jujur tentang detektor saya sendiri
Angka sebaran berubah **5 → 3 → 13** sebelum benar. Dua kesalahan saya: (a) menuntut
`onClick` memanggil setter langsung — padahal umumnya lewat `openDetail(id)`, sehingga
**layar yang dilaporkan pemilik sendiri tidak terdeteksi**; (b) mencari nama kelas CSS di
sumber yang string-nya sudah dibuang. Keduanya kini jadi kasus self-test permanen.

### Sisa yang BELUM (diperbarui)
1. **Utang alur F-6.7**: payroll & desain masih diputuskan dari `draft` (butuh "Ajukan").
2. **Kirim dokumen via email/SMTP** — butuh kredensial pemilik.
3. **Ambang persetujuan antar-PT (US22)** belum diuji ujung-ke-ujung lewat layar.
4. 3 layar masih "Segera Hadir": BOM Printing · BI Sales · BI Stok.
5. **Riwayat alasan**: alasan pembatalan/void belum tampil di dokumennya.
6. Data demo: **1 dari 59 roll** tanpa `roll_no`/`unit`; **Landed Cost & RFQ kosong**
   sehingga 2 dari 9 pop-up hanya terverifikasi lewat gate, belum lewat klik nyata.

---

## §STATUS MD-ERP — SESI 2026-08-18 (sore): **RENCANA DIVERIFIKASI ULANG (v2) + ALAT UKUR KESIAPAN**

> **Tidak ada fitur yang dikerjakan di sesi ini — dan itu disengaja.** Permintaan pemilik:
> *"pada eksekusi kembali, saya tidak yakin sudah cukup jelas; coba satu iterasi lagi, cek
> kondisi sekarang, tambahkan apa yang harus diedit, pastikan UI/UX tidak berubah, pastikan
> rules entitas terimplementasi dengan benar terutama soal dokumen, recheck & double check,
> pastikan agen selanjutnya tahu konteksnya."*

### Yang dikerjakan
1. **Repo dipulihkan ke pod ini** dari `github.com/wasakalakaha/kn` (HEAD `cecb511`
   *"WIP: simpan progress saya"*) → `bash .restore_env.sh` (pip · yarn · restart backend ·
   `seed_realistic.py` · build FE) hijau. Backend `/api/` 200, frontend 200,
   `.env` (MONGO_URL, REACT_APP_BACKEND_URL) **tidak** disentuh.
2. **`RENCANA_EKSEKUSI_MD_ERP.md` ditulis ulang jadi v2** (1.276 baris). v1 diarsipkan di
   `docs/arsip/RENCANA_EKSEKUSI_MD_ERP_v1_2026-08-18.md`.
   Tambahan yang tidak ada di v1:
   * **§0 Konteks 2 menit untuk agen berikutnya** (cara nyalakan, SSOT, arti "selesai").
   * **§3 Kontrak pagar entitas — 12 titik sambung + 3 titik khusus dokumen**, plus tabel
     instansiasi untuk 6 koleksi baru (field entitas · baris global · `DOC_TYPES` ·
     `gate_residue.WATCH` · nomor per badan usaha · izin · antrean · index ·
     `ENTITY_REGISTRY.md`). **§3.4** menggambar aturan anti-pintu-ke-3 untuk grade & cacat.
   * **§4 Kontrak UI/UX "tidak ada yang berubah"**: daftar yang dilarang berubah + bukti
     gate-nya (11 invarian UI/UX dari 25 invarian di `gate.sh`) + tabel komponen yang wajib
     dipakai ulang + prosedur bukti akhir fase (`git diff --stat` nol untuk berkas gaya,
     tangkapan layar sebelum/sesudah 3 layar lama).
   * **Peta berkas yang disentuh per fase** (path + simbol), bukan lagi deskripsi umum.
   * **User story per fase** (acuan agen uji UI).
3. **Alat ukur baru `scripts/audit_md_erp_readiness.py`** — 96 fakta, per fase, tiga status
   (`SELESAI` / `BELUM` / `DRIFT`), `--fase`, `--strict` (exit 1 hanya untuk DRIFT).
   **Baseline hari ini: SELESAI 16 · BELUM 73 · DRIFT 7.**

### 7 klaim v1 yang ternyata SALAH (diukur, bukan diingat) — rincian di §2.1
K1 `uoms` 4 baris (bukan 6; `CM`/`INCH` hilang tergantung urutan restart vs seed) ·
K2 satuan dokumen (`kg`,`meter`,`yard`) **tak satu pun** cocok dengan kode master →
menambah `KG` saja tidak mengubah apa pun · K3 `color_library` **sudah** punya Pantone
`TCX`/`TPX` · K4 `qc_inspections` koleksi **hantu** (0 dokumen, 0 penulis); hasil inspeksi
hari ini tinggal di `inventory_rolls.inspection` · K5 pembaca `sample_type` = **9 berkas BE +
8 FE** (bukan 5) · K6 `approval_backlog_service` **tidak** memakai `sample_type` ·
K7 rantai PO→PR→SO **putus** (0/14 PO menyimpan `pr_id`) sehingga "Nama Sales" di papan PO
mustahil dirunut sebelum dibetulkan.

### 7 DRIFT hari ini (bukan bagian rencana — wajib diputuskan di fasenya)
D1 kosakata satuan dokumen ≠ master `uoms` → FASE U ·
D2 `qc_inspections` hantu di `entity_scope` → FASE I ·
D3 PO tidak menaut PR → **FASE P langkah P-0 (prasyarat)** ·
D4 `design_gallery.code` kosong (2 dari 4) → FASE D ·
D5 11 notifikasi ber-`recipient_role="all"` (`low_stock`×9) → FASE N ·
D6 `REL_LABEL` memuat `applied_to` yang **tidak ada** di `REL_INVERSE` → `link()` akan
melempar `RefsError`; betulkan saat menaut acuan sample (FASE I) dengan pasangan resmi
`references↔referenced_by` ·
D7 **nomor dokumen demo ada yang KEMBAR** (5 nomor ganda di `md_samples`, 20 dari 28 menyimpang pola) karena `scripts/seed_rnd_kpi_demo.py` menomori sendiri dengan f-string alih-alih `next_doc_number()` → FASE S.

Catatan tambahan yang mudah menyesatkan (bukan DRIFT): `inventory_rolls.inspection`
**polimorfik** (bentuk 4-point dari `qc_inspection_service` vs bentuk retur dari
`return_service`); roll retur **lahir** ber-grade tanpa `grade_history` (bukan pelanggaran
`grade_service`, tetapi gate `INV-QC-02` wajib mengecualikannya secara tertulis);
`EntityMastersView.jsx` sudah 543 baris dan **kolom master per jenis hardcode** → jenis
master baru wajib menambah entri di berkas data terpisah, kalau tidak tabelnya kosong.

### Keadaan gate saat serah-terima (diukur sesi ini)
`python scripts/validate_compliance.py` → **22 PASS · 0 FAIL · 16 WARN** (WARN = ukuran
berkas & impor tak terpakai warisan) · `cd backend && python -m scripts.verify_entity_scoping`
→ **DB CHECK LULUS · STATIC CHECK LULUS**.

### Berikutnya (urutan yang disarankan, sudah disepakati pemilik)
1. **FASE L (Lini)** → **T (Tahapan + Screen)** → **U (Dua satuan)** — tidak butuh jawaban apa pun.
2. Sambil menunggu 5 keputusan pemilik (§12 rencana): **FASE D (Permintaan Desain)** dan
   **P-0 (tautan PO→PR)**.
3. Sesudah keputusan turun: **S (Sampling)** → **I (Inspeksi/QC)** → **P (Papan PO)** →
   **N (Notifikasi)** → **M (Makloon)**.
Setiap fase ditutup: POC + gate ber-`--self-test` + `audit_md_erp_readiness.py --fase X`
bersih + agen uji UI (user story fase) + bagian ini diperbarui.

---
## §STATUS T — SELESAI (2026-08-19): **FASE T DITUTUP** — residu POC dihentikan · bug pemilih pop-up (P1) ditemukan & ditutup · INV-UI-09 lahir

> Permintaan pemilik: *"lanjutkan development dari repo ini, sebelumnya development
> berhenti di sini."* Keputusan pemilik sesi ini: **(1)** tutup T lalu kerjakan U ·
> **(2)** panjang **PANEL berbeda per pesanan** (faktornya disimpan di baris dokumen,
> bukan di master produk) · **(3)** sampling bawaan woven/knit = `labdip`+`handfeel`,
> printing = `proofing`, `bulk_sample` **dinonaktifkan** (bukan dihapus) · **(4)** warna
> beda dari sample ACC = barang **DITAHAN**, handfeel beda = **peringatan**; yang berwenang
> melepas tahanan = **MANAJER**. (2)–(4) dicatat untuk FASE U/S/I, belum dieksekusi di sini.

### 0. Pemulihan lingkungan (wajib tiap clone — kontainer datang KOSONG/template)
`git clone github.com/awawjahsada/kn → /tmp/knrepo` → `rsync` ke `/app` (**JANGAN** timpa
`backend/.env` & `frontend/.env`) → `bash /app/.restore_env.sh`. `memory/test_credentials.md`
di-.gitignore → **ditulis ulang** (9 akun demo, sandi `demo12345`). Catatan yang terbukti
lagi: `/tmp` dibersihkan pod di tengah sesi — klon di `/tmp/knrepo` sudah hilang saat
diperiksa 10 menit kemudian, sementara `/app` aman.

### 1. Titik henti diukur ulang lebih dulu — dan ternyata TIDAK bersih
Yang dilaporkan warisan: FASE L ditutup, FASE T "berikutnya". Yang **terukur** hari ini:
FASE T sudah terbangun (master `process_stages` 10 baris · `master_registry.py` ·
`screen` di `PROCESS_TYPES` · `steps[].stage_code` 5/5 SPK · FE wizard memakai master),
`audit_md_erp_readiness.py --fase T` **SEMUA SELESAI**, POC FASE T **62/62**.
**Tetapi `gate.sh --full` MERAH 3** — dan ketiganya satu akar:

| Gate merah | Penyebab sebenarnya |
|---|---|
| `INV-GATE-01` anti-residu | POC FASE T meninggalkan `inventory_movements` **+3** · `inventory_rolls` **+2** · `inventory_lots` **+1** (langkah T2b menjalankan alur kain sungguhan `Issue → Terima Hasil`) |
| POC `G-6b` | syaratnya sendiri "`FAIL 0` **dan** `WARN 0`" jatuh karena residu itu memunculkan WARN `drift persediaan subledger vs GL 1-1300 Δ750.000` |
| (tuduhan ke-3) | `dokumen_hantu_uji` di `audit_doc_refs --self-test` — **bukan** kegagalan: itu kasus bukti-merah yang MEMANG harus merah |

Pelajaran: **POC yang berakhir "0 FAIL" tidak membuktikan nol residu** kalau ia tidak
pernah memeriksanya. Kelas bug ini sudah pernah ditutup untuk POC G-0..G-3
(POC-RESIDU-01) tetapi POC baru tidak mewarisi pengamannya.

### 2. Perbaikan 1 — POC FASE T dibuat bebas residu (dan membuktikannya sendiri)
`backend/test_core_tahapan_poc.py` memakai `poc_stock_guard.snapshot_stock()` sebelum
menulis + `restore_stock()` di CLEANUP (pemulihan **EKSAK**; memotong/menerima roll tak
bisa dibalik per-dokumen), **plus pemeriksaan baru T9**: jumlah dokumen 4 koleksi stok
sebelum == sesudah. Jadi kalau kelak ada jalur tulis baru, **POC-nya sendiri** yang
memerah — bukan gate di ujung. Bukti: POC **63 PASS/0 FAIL**, "stok dipulihkan EKSAK
(195 dokumen, 4 koleksi)", `gate_residue --check` nol residu,
`verify_data_integrity` **237 PASS / 0 FAIL / 0 WARN**.

### 3. Perbaikan 2 — bug P1 yang ditemukan saat menjalankan sendiri user story FASE T
Agen uji UI berhenti dua kali dengan gejala kabur ("modal pemilih tidak menutup, alur
wizard tak bisa diselesaikan — sarannya: uji manual"). Direproduksi sendiri di peramban:
**memilih produk BERHASIL, tetapi pop-up pemilih terbuka kembali dengan kotak cari
kosong**, lalu lapisannya menutupi tombol **Lanjut** → alur berhenti. Nol galat, nol
jejak konsol, uji backend tetap hijau.

Akar: `ProductSelect` · `MakloonSelect` · `PantoneFinder` adalah **pemicu + pop-up dalam
satu komponen**, dan ketiganya dipakai di dalam `<Field>` yang merender **`<label>`**.
Aktivasi `<label>` **diteruskan peramban** ke kontrol yang dilabeli — tombol pemicunya
sendiri → `setOpen(true)` lagi. `e.stopPropagation()` di kartu pop-up **tidak menolong**
(React memasang pendengarnya di AKAR dokumen; `<label>` berada di antara target & akar,
dan aktivasi label adalah perilaku PERAMBAN). Terdampak **3 komponen × 9 tempat pakai**
(Wizard Makloon · Order Makloon · Resep Proses · Kontrak Mitra · Master Produk · Template
Produk · Buat PO · Buat Transfer · Harga Khusus).
Perbaikan: pop-up dirender lewat `createPortal(…, document.body)` — **nol perubahan gaya**.

### 4. Gate baru `INV-UI-09` (anti kambuh)
`scripts/guardrails/verify_picker_portal.py`: (A) berkas pemilih (punya `triggerTestId`
**dan** merender lapisan pop-up sendiri) WAJIB memakai `createPortal`; (B) lapisan pop-up
(`fixed inset-0` + `bg-black/`) tidak boleh berada di dalam blok `<label>`.
`--self-test` **16 kasus dua arah**. Dua pelajaran repo ini dipakai sejak awal:
* versi pertama penjaga memakai jendela 400 karakter → **menuduh tiga berkas yang sudah
  BENAR** (`{value ? valueName : label}` dianggap render pop-up). Diperbaiki: penilaian
  hanya pada elemen yang **persis** menyusul syaratnya.
* versi kedua menuduh **dirinya sendiri**: kata `<label>` di komentar dokumentasi dihitung
  sebagai elemen label. Karena penanda pop-up hidup **di dalam string** (`className`),
  `strip_comments_and_strings` tak bisa dipakai apa adanya → dibuat pembuang **komentar
  saja** (string dipertahankan), pola yang sama dengan `INV-ROLL-01`.

### 5. Bukti penutup FASE T
`python backend/test_core_tahapan_poc.py` → **63 PASS / 0 FAIL** (dua kali berturut, nol residu) ·
`python scripts/guardrails/verify_master_stages.py` (INV-DOMAIN-06) **HIJAU** ·
`verify_picker_portal.py --self-test` **16/16** · `bash scripts/gate.sh --full` →
**90 gate HIJAU / 0 FAIL (291 s)** · `audit_md_erp_readiness.py --fase T` **SEMUA SELESAI** ·
`verify_data_integrity` **237/0/0** ·
**uji lewat layar (dijalankan sendiri di peramban, bukan hanya oleh agen uji):**
T-US1 tahap dari master muncul di pemilih SPK (8 tahap sah: Tenun · Rajut · PFP · PFD ·
Celup · **Screen** · Printing · Proofing) · T-US2 SPK `MKO-00006` ber-tahap Screen dibuat
ujung-ke-ujung: **25 yard masuk → 25 yard keluar**, lencana "Tidak mengubah kain — hanya
biaya jasa", peringatan mitra muncul saat mitra kosong (keputusan **3b**) lalu hilang
setelah mitra dipilih, ongkos **Rp 750.000** dari kontrak `KSC/SCT-00008`, tombol lanjutan
**Catat Jasa** + kalimat "kain tidak dikeluarkan dari gudang, tidak ada roll baru" ·
T-US3 `MKO-00001` lama **EST. OUTPUT 109,44 identik** · regresi Pesanan · PO · Status Stok
tanpa galat. Dokumen uji `MKO-00006` **dibersihkan** (integritas 237/0/0 sesudahnya).
**Dua "temuan" agen uji terbukti TUDUHAN PALSU** dan diverifikasi sendiri: literal `NaN`
**0 kejadian** di ketiga layar (kata Indonesia ber-"nan" seperti "Pena**nan**ganan"
tertangkap pencarian case-insensitive), dan "sesi cepat kedaluwarsa" — TTL sesi 24 jam
dengan perpanjangan otomatis (`core_utils.SESSION_TTL_HOURS = 24`).

### 6. Jebakan untuk sesi berikutnya (BACA)
* **POC baru WAJIB memakai `poc_stock_guard`** kalau alurnya menyentuh roll/lot/mutasi,
  dan sebaiknya memeriksa sendiri "sebelum == sesudah" seperti T9 sekarang.
* **Komponen "pemicu + pop-up" baru WAJIB ber-portal** (INV-UI-09). Kalau tidak, ia akan
  mati diam-diam begitu dipakai di dalam `<Field>`/`<label>`.
* **Jangan percaya laporan agen uji UI tanpa reproduksi**: dua dari empat temuannya palsu,
  dan satu temuan nyata (P1) dilaporkan sebagai "kendala otomasi", bukan sebagai bug.
* Berikutnya: **FASE U (dua satuan)** dengan keputusan pemilik **PANEL berbeda per
  pesanan** → faktor konversi panel disimpan **di baris dokumen**, bukan di master produk
  (`products.uom_conversions` tetap untuk hal lain).
