# Development Plan — Lanjutan Repo `kamasakanaaba/DA`

## 1) Objectives
- Menindaklanjuti titik henti: **PS-17 sudah selesai & hijau** (iter 205). Fokus baru (D-14):
  1) **Menegakkan** matriks persetujuan divisi (bukan sekadar rujukan), lengkap **Antrean “Persetujuan Saya”** + audit trail.
  2) Membangun 4 menu **“Segera Hadir”**: **Daftar Harga per Pelanggan**, **BOM Printing**, **BI Sales**, **BI Stok**.
- Seluruh perubahan tetap **config-driven** via **Pusat Pengaturan** (config registry), multi-entitas, RBAC, audit_logs.
- Setiap fase wajib: **POC script terisolasi → fix sampai hijau → implement BE+FE (data-testid) → rebuild FE** → panggil **testing_agent_v3** → update `plan.md` + `SESSION_HANDOFF.md`.

## 2) Implementation Steps

### Phase 1 — Penegakan Matriks Persetujuan Divisi + “Persetujuan Saya”
User stories:
1. Sebagai manager, saya hanya bisa melakukan ACC Desain/ACC Sample/ACC PR sesuai aturan, dan tindakan user lain ditolak jelas.
2. Sebagai admin (Direksi), saya bisa menyetujui **level-2 PO Custom** bila melewati ambang nilai.
3. Sebagai approver, saya melihat semua permintaan persetujuan saya dalam satu inbox dengan filter jenis + status.
4. Sebagai pembuat dokumen, saya melihat status persetujuan berjenjang (level 1/level 2) dan siapa yang sudah menyetujui.
5. Sebagai admin, saya bisa mengubah kebijakan retroaktif: default **berlaku untuk semua termasuk pending**, bisa diubah ke **hanya dokumen baru** tanpa deploy.

POC (isolated, `/app/test_core_ps17_enforcement.py`):
- Seed minimal: buat 1 RND spec + 1 sample + 1 PR + 1 special-order/PO-custom yang butuh 2 level.
- Verifikasi:
  - Rule enforcement per stage (design_acc, sample_acc, purchase_request, po_custom) → role salah = 403.
  - Multi-level approval: manager approve level-1 → status tetap waiting_approval, admin approve level-2 → final approved.
  - Retroactivity setting: mode “all_pending” vs “new_only” memengaruhi dokumen pending.
  - Audit log tercatat untuk setiap approve/reject.

Backend:
- Tambah entri config registry (Pusat Pengaturan): `rnd.approval_enforcement_mode` (enum: `all_pending` default, `new_only`).
- Buat service enforcement terpadu (mis. `services/rnd_approval_enforcement.py`) yang:
  - Memetakan stage → doc_type/aksi → role chain.
  - Menggunakan `config_service.build_approval_chain` + `role_satisfies` untuk level-2 (Direksi=admin).
  - Menghormati switch retroaktif.
- Integrasikan ke endpoint yang relevan:
  - `routers/rnd.py` approve/reject spec dan decide sample (design_acc, sample_acc).
  - `routers/purchase_requisitions.py` approve/reject (purchase_request) + SoD bila diperlukan.
  - `routers/special_orders.py` approve/reject: ubah ke pola approval_chain seperti PO (po_custom).
- Notifikasi/inbox:
  - Reuse `approval_requests` framework **atau** samakan ke pola notifikasi action (yang sudah dipakai PO) agar muncul di “Pusat Persetujuan”.
  - Pastikan `GET /api/approval-requests` menampilkan item baru (RND/spec/sample/PR/special-order) beserta deep-link target.
- Update `ENTITY_REGISTRY.md` bila ada koleksi baru.

Frontend:
- Perluas **Pusat Persetujuan** (hub `approval-inbox`) untuk menampilkan tipe baru: ACC Desain, ACC Sample, PR, PO Custom.
- Di halaman terkait (Spec/Sample/PR/Special Order/PO) tampilkan:
  - badge status persetujuan, level saat ini, dan histori approval_chain.
- Tambah kontrol pengaturan baru di Pusat Pengaturan (R&D & Desain) untuk mode retroaktif.
- Rebuild FE (`bash /app/scripts/rebuild_frontend.sh`).

Testing:
- Update `test_result.md` (yaml) untuk Phase 1.
- Panggil `testing_agent_v3` untuk E2E: RBAC, inbox, chain 2-level, regresi PO approval.

---

### Phase 2 — Daftar Harga per Pelanggan (Customer Pricelist)
User stories:
1. Sebagai admin/manager, saya membuat harga khusus untuk pelanggan tertentu per produk dengan tanggal efektif.
2. Sebagai admin/manager, saya melihat histori harga pelanggan dan harga efektif hari ini.
3. Sebagai sales, saat membuat SO/POS, sistem otomatis memakai urutan harga: **pelanggan → PT → global**.
4. Sebagai user, saya bisa ekspor & impor CSV harga pelanggan (UTF-8 BOM) untuk update massal.
5. Sebagai user, saya melihat badge “harga khusus pelanggan” pada baris item bila harga berasal dari customer pricelist.

POC (`/app/test_core_customer_pricelist.py`):
- Buat 1 customer, 1 produk, 2 harga (scheduled & current), pastikan resolving order bekerja.
- Uji import/export CSV roundtrip.

Backend:
- Tambah koleksi `customer_pricelist` (scoped `entity_id`), field: customer_id, product_id/sku, price, currency, effective_from/to, status.
- Endpoint CRUD + list/search + history + import/export CSV.
- Hook ke pricing engine: perluas `config_service.compute_order_pricing` agar bisa menerima `customer_id` dan lookup harga.

Frontend:
- Bangun view baru untuk nav id `cs-price-list` (mis. `CustomerPricelistView.jsx`) + wiring `hubTabs/navMeta/AppViewRouter`.
- UI: filter customer, search produk, tambah/edit harga, histori, tombol import/export.
- Integrasi badge di SO/POS line item saat sumber harga = customer.
- Rebuild FE.

Testing:
- Update `test_result.md` + panggil `testing_agent_v3` (SO/POS pricing, CSV, RBAC).

---

### Phase 3 — BOM Printing (Resep Cetak terhubung ke Desain, reuse WO)
User stories:
1. Sebagai admin produksi, saya membuat BOM Printing untuk sebuah desain/motif dan memilih kain dasar.
2. Sebagai admin, saya mengisi colorway (warna) dengan konsumsi pasta/pewarna dan biaya per meter.
3. Sebagai admin, saya menentukan parameter proses (screen/rotary, jumlah screen) dan melihat estimasi biaya.
4. Sebagai user, saya bisa mengubah BOM Printing dan histori tetap tercatat.
5. Sebagai user, saya bisa membuat Work Order dari BOM Printing tanpa alur baru yang terpisah.

POC (`/app/test_core_bom_printing.py`):
- Buat 1 design + 1 printing BOM bertipe `printing` yang tetap valid untuk WO flow.
- Buat 1 WO dari BOM tsb dan pastikan consumptions/summary tidak rusak.

Backend:
- Strategi data: **extend** `mfg_boms` dengan `kind: "printing"` + field printing-specific (colorways, screens, base_fabric_id, paste_components).
- Endpoint khusus list/filter printing BOM + create/update via `routers/production.py` atau router baru `printing_boms.py` (tetap reuse service).
- Pastikan WO tetap membaca komponen generik dari BOM (komponen printing diterjemahkan jadi components standar).

Frontend:
- Implement view baru nav id `cs-bom` (roles admin) untuk “BOM Printing”:
  - pilih desain (Design Gallery), kain dasar, colorways, komponen pasta, biaya.
  - tombol “Buat Work Order”.
- Reuse komponen tabel/validasi dari Production BOM bila memungkinkan.
- Rebuild FE.

Testing:
- `testing_agent_v3` fokus: create/edit BOM Printing, create WO, regresi produksi.

---

### Phase 4 — BI Sales + BI Stok
User stories:
1. Sebagai manager, saya melihat tren penjualan harian/bulanan per entitas dengan filter periode.
2. Sebagai manager, saya melihat breakdown per kategori/produk/sales/pelanggan dan pelanggan top/menurun.
3. Sebagai manager, saya melihat margin & kontribusi (bila data cost tersedia), dengan fallback bila tidak.
4. Sebagai manager, saya melihat BI stok: nilai persediaan, aging, slow-moving, turnover & DOS per gudang.
5. Sebagai user, saya bisa ekspor BI Sales/BI Stok ke Excel/PDF dengan format konsisten.

POC (`/app/test_core_bi_sales_stock.py`):
- Panggil endpoint agregasi utama untuk sales & stock (periode default) dan validasi shape + export bytes.

Backend:
- Reuse agregasi yang sudah ada (`routers/reporting.py`, `finance_bi.py`) dan lengkapi:
  - `/api/bi/sales/*` (trend + breakdown + top/declining)
  - `/api/bi/stock/*` (value + aging + turnover/DOS)
- Export: reuse pola `rnd_kpi_export.py` (single column definition → CSV/XLSX/PDF).

Frontend:
- Implement 2 view baru untuk `cs-bi-sales` dan `cs-bi-stock`:
  - grafik (Recharts) + tabel ringkas + filter periode/entitas/gudang.
  - tombol export.
- Rebuild FE.

Testing:
- `testing_agent_v3` regression: dashboards render, export ok, tidak bocor ke role non-allowed.

## 3) Next Actions
1. Phase 1: tulis **POC** `test_core_ps17_enforcement.py` dan pastikan hijau.
2. Implement BE enforcement + switch settings + integrasi endpoint (spec/sample/PR/special order) + inbox.
3. Implement FE inbox/chain UI + setting control, rebuild FE.
4. Panggil `testing_agent_v3` untuk Phase 1, perbaiki sampai hijau.
5. Lanjut Phase 2 → 3 → 4 dengan pola yang sama (POC → app → testing_agent).

## 4) Success Criteria
- Phase 1:
  - Persetujuan stage PS-17 **benar-benar mengikat** (403 untuk role salah), multi-level PO Custom berjalan (manager→admin), audit trail ada, inbox menampilkan item baru.
  - Switch retroaktif di Pusat Pengaturan bekerja dan default = berlaku untuk pending.
- Phase 2:
  - Harga pelanggan per produk bisa dikelola + histori + import/export CSV, dan resolving order customer→PT→global terpakai di SO/POS dengan badge sumber harga.
- Phase 3:
  - BOM Printing terhubung ke desain, bisa jadi Work Order tanpa memecah alur produksi, dan tidak merusak BOM/WO yang sudah ada.
- Phase 4:
  - BI Sales & BI Stok menampilkan grafik/tabel stabil (empty state aman), filter bekerja, export Excel/PDF konsisten.
- Setelah tiap fase: verifikasi `testing_agent_v3` 100% + update `plan.md` dan `SESSION_HANDOFF.md`.

---
# ARSIP — RIWAYAT PLAN SESI SEBELUMNYA (jangan dihapus: memori proyek)


---
# ARSIP — RIWAYAT PLAN SESI SEBELUMNYA (memori proyek: JANGAN dihapus)

# Plan — Kontrabon Seed Fix + Rating Desain + Tren KPI Desainer + Rapor Per-Desainer (PDF)

> **Context ringkas:** ERP/WMS besar (FastAPI + React + MongoDB). Frontend **STATIC bundle** (tidak ada hot reload) → setiap perubahan `frontend/src` wajib jalankan `bash /app/scripts/rebuild_frontend.sh`.
> 
> **Login demo:** semua user password `demo12345` (`admin@/manager@/sales@/warehouse@kainnusantara.id`).

## 1) Objectives
- ✅ **Phase A:** Perbaiki bug seeding Kontrabon (`date value out of range`) agar koleksi `contra_bons` terisi dan layar Kontrabon punya data demo.
- ✅ **Phase B:** Tambah **rating 1–5** untuk setiap desain (koleksi `design_gallery`) dengan konsep **1 rating per rater** (admin/manager). Tampilkan **rata-rata + jumlah penilai** dan dukung update rating.
- ✅ **Phase C:** Tambah **tren nilai desainer per bulan** (Recharts) pada layar KPI Desainer.
- ✅ **Phase D:** Tambah **Rapor per-desainer (PDF 1 halaman)** untuk lampiran evaluasi.
- ⛔ **PS-17** ditandai **BLOCKED** (butuh keputusan D-13) → tidak dibangun pada sesi ini.

## 2) Implementation Steps

### Phase 1 — Core POC (isolasi, wajib hijau sebelum UI besar)
> Fokus membuktikan alur inti masing-masing fitur berjalan stabil (seed ↔ API ↔ perhitungan ↔ export).

**A) POC Seed Kontrabon**
1. Buat skrip uji `test_kontrabon_seed_poc.py` yang memanggil fungsi seed Kontrabon (atau menjalankan bagian seed terkait) dan memastikan **tidak error**.
2. Validasi DB: `contra_bons.count_documents({}) > 0` dan semua tanggal valid ISO / rentang wajar.

**B) POC Rating Desain (API-only)**
1. Tambah field rating di dokumen `design_gallery` (migrasi ringan on-write):
   - `ratings: [{user_id, name, stars, note, at}]`
   - computed: `rating_avg`, `rating_count`
2. Buat skrip `test_design_rating_poc.py`:
   - login admin/manager → pilih 1 desain → set rating 5 → update ke 3 → pastikan entry per user tidak dobel
   - pastikan list/detail mengembalikan `rating_avg/rating_count/my_rating`.

**C) POC Tren KPI per bulan (API-only)**
1. Implement endpoint trend (mis. `GET /api/rnd/reports/designer-kpi/trend?period=&months=&entity_id=`).
2. Buat skrip `test_designer_kpi_trend_poc.py`:
   - minta 6–12 bulan → pastikan urutan bulan benar, nilai numeric, empty state stabil.

**D) POC Rapor per-desainer PDF**
1. Implement endpoint (mis. `GET /api/rnd/reports/designer-kpi/report?designer_id=&period=&format=pdf`).
2. Buat skrip `test_designer_report_pdf_poc.py`:
   - ambil 1 desainer → unduh PDF → cek `content-type`/bytes > minimal.

**Exit criteria Phase 1:** semua skrip POC PASS tanpa flakiness.

### Phase 2 — V1 App Development (integrasi penuh)

**Phase A — Fix Kontrabon Seed Bug (V1)**
User stories:
1. Sebagai admin, saya menjalankan `seed_realistic.py` tanpa warning Kontrabon.
2. Sebagai user, saya membuka layar Kontrabon dan melihat daftar data demo.
3. Sebagai user, saya dapat membuka detail Kontrabon (jika ada) tanpa error.
4. Sebagai developer, seed tetap idempotent (re-run tidak menggandakan data liar).
5. Sebagai QA, saya bisa memverifikasi jumlah `contra_bons` konsisten setelah re-seed.

Steps:
- Temukan sumber `date value out of range` di seeding Kontrabon, perbaiki generator tanggal (timezone/rentang/tahun).
- Pastikan kontrabon seeded mengacu pada dokumen valid (PO/GRN/bill yang sesuai jika diperlukan).
- Re-run `seed_realistic.py` dan verifikasi `contra_bons > 0`.

**Phase B — Rating per Desain (V1)**
User stories:
1. Sebagai manager, saya memberi rating bintang 1–5 pada sebuah desain.
2. Sebagai manager, saya bisa mengubah rating saya tanpa membuat duplikat.
3. Sebagai admin/manager, saya melihat rata-rata rating + jumlah penilai pada kartu desain.
4. Sebagai user non-privileged (sales/warehouse), saya hanya bisa melihat rating agregat (tanpa bisa menilai).
5. Sebagai admin, saya dapat melihat rating saya sendiri (`my_rating`) saat membuka detail desain.

Backend:
- Update schema & router `design-gallery`:
  - expose `rating_avg`, `rating_count`, `my_rating` pada list & detail.
  - endpoint set/update rating (RBAC admin/manager), validasi 1–5.

Frontend:
- `DesignGalleryView.jsx`:
  - tampilkan stars + count di `GalleryCard`.
  - di Manage/Detail modal tambahkan komponen rating (admin/manager bisa set/update).
- `RndDesignsView.jsx`:
  - tampilkan rating agregat pada card master desain.
  - di modal edit/version (atau tempat paling tepat) tampilkan rating + aksi set rating.
- Tambah `data-testid` untuk rating UI.

**Phase C — Tren nilai desainer per bulan (V1)**
User stories:
1. Sebagai manager, saya melihat grafik tren nilai desainer per bulan (12 bulan terakhir).
2. Sebagai manager, saya mengganti periode (month/30d/90d/all) dan grafik ikut berubah.
3. Sebagai manager, saya bisa menyalakan/mematikan garis per desainer (legend).
4. Sebagai manager, jika data kosong, saya melihat empty state yang jelas (bukan chart rusak).
5. Sebagai admin, saya bisa membandingkan tren antar desainer di entitas terpilih.

Backend:
- Endpoint trend mengembalikan `months[]` + `series[]` (per designer) atau `overall` + `per_designer`.

Frontend:
- Tambah panel chart di `DesignerKpiView.jsx` (Recharts Line/Area), konsisten dengan filter periode.

**Phase D — Rapor per-desainer (PDF 1 halaman) (V1)**
User stories:
1. Sebagai manager, saya klik “Unduh Rapor” pada satu desainer.
2. Sebagai manager, rapor PDF berisi ringkasan metrik + grade + highlight overdue/rework.
3. Sebagai manager, rapor tetap rapi walau desainer tidak punya data lengkap.
4. Sebagai admin, saya dapat memilih periode rapor (bulan ini/30/90/semua).
5. Sebagai user non-privileged, saya ditolak (403) saat mencoba unduh rapor orang.

Backend:
- Tambah generator PDF 1 halaman per desainer (reuse `reportlab` + style payslip).
- Endpoint report per desainer (RBAC admin/manager), `format=pdf`.

Frontend:
- Tambahkan tombol “Unduh Rapor” per baris di `DesignerKpiTable.jsx` (atau menu aksi).
- Notifikasi sukses/gagal unduhan.

**Conclude Phase 2:** rebuild FE bundle + panggil `testing_agent` untuk E2E tiap phase (A–D) sesuai `test_result.md`.

### Phase 3 — Hardening + Regression Gates
User stories:
1. Sebagai developer, saya menjalankan gate script utama dan tidak ada error baru.
2. Sebagai QA, saya memastikan RBAC rating & export benar (admin/manager vs sales/warehouse).
3. Sebagai user, semua halaman terkait tetap cepat dan tidak ada layout pecah.
4. Sebagai admin, export/report konsisten dengan angka di tabel KPI.
5. Sebagai owner, demo data Kontrabon & rating terlihat tanpa setup manual.

Steps:
- Tambah seed kecil untuk rating demo (opsional) agar kartu rating tidak kosong.
- Jalankan subset gates relevan (nav map, api contract, health_check bila diperlukan).
- Dokumentasikan PS-17 sebagai **blocked** sampai D-13 tersedia.
- Panggil `testing_agent` untuk regression.

## 3) Next Actions
1. Implement **Phase A** (fix seed Kontrabon) + POC script → run seed → verifikasi DB.
2. Implement **Phase B** (rating desain) backend dahulu → FE UI → rebuild FE.
3. Implement **Phase C** (trend endpoint + chart).
4. Implement **Phase D** (PDF per-designer + tombol unduh).
5. Update `memory/test_credentials.md` bila ada perubahan user demo.
6. Update `test_result.md` sebelum memanggil `testing_agent` di setiap fase.

## 4) Success Criteria
- Seed: `seed_realistic.py` tidak lagi mengeluarkan warning Kontrabon dan `contra_bons > 0`; UI Kontrabon menampilkan data.
- Rating desain:
  - Admin/manager bisa set/update rating 1–5; tidak ada duplikat per user.
  - List/detail desain menampilkan `rating_avg` + `rating_count` + `my_rating`.
  - UI menampilkan rating pada **Design Gallery** dan **Master Desain**.
- Tren KPI desainer: grafik Recharts tampil stabil (termasuk empty state) dan sesuai filter periode.
- Rapor per-desainer: PDF 1 halaman dapat diunduh (RBAC benar) dan isi konsisten dengan KPI.
- Semua perubahan terverifikasi oleh **testing_agent** (E2E) sebelum dinyatakan selesai.

---
## SESI 2026-08-07 (lanjutan) — SELESAI ✅
Repo `kajwnahagabava/kn` dipulihkan penuh ke lingkungan (backend/DB/FE build). 4 item dikerjakan & diverifikasi testing agent:
- **Phase A — Fix seed Kontrabon**: bug OverflowError di `contra_bon_reminder.next_exchange_date` (loop biweekly tak berujung). Fix: selaraskan weekday acuan lalu geser maks 1 pekan. Seed kini bersih, `contra_bons`=3. (iter 201)
- **Phase B — Rating desain (1–5 bintang)**: per-penilai (admin/manager), kartu tampil rata-rata + jumlah. Endpoint POST/DELETE `/api/design-gallery/{id}/rating`; UI di Galeri Motif & Master Desain + modal Kelola. Seed demo rating idempotent. (iter 201 BE + verifikasi visual)
- **Phase C — Tren nilai desainer per bulan (Recharts)**: `GET /api/rnd/reports/designer-kpi/trend` (metric avg_score|grade, months 3/6/12) + chart di KPI Desainer + riwayat 5 bulan idempotent (`demo_batch=designer_trend_v1`, >30h → tak ubah tabel default). (iter 202, 100%)
- **Phase D — Rapor per-desainer (1 halaman PDF)**: `GET /api/rnd/reports/designer-kpi/report?designer=&period=&format=pdf` (reportlab) + tombol 'Rapor PDF' per baris tabel. (iter 202, 100%)
- **Regresi diperbaiki**: dekorator `@router.get("/rnd/sla/board")` sempat terhapus saat edit Phase D → 404; sudah dipulihkan (iter 203, 15/15 BE pass).

## PS-17 — DITUNDA (blocked)
Divisi sebagai aktor R&D menunggu keputusan pemilik **D-13** (daftar final divisi/jabatan + approver tiap tahap: ACC Desain, ACC Sample, PO custom, PR). Tidak dibangun sesi ini demi menjaga stabilitas RBAC aplikasi.

---
## SESI 2026-08-07 (lanjutan-2) — SELESAI ✅
- **Ringkasan Rapor**: tombol 'Rapor PDF' membuka modal catatan evaluasi bebas → param `note` (maks 1200) di endpoint report → kotak "Catatan Evaluasi" di PDF. Verified (BE 100% iter 204 + alur unduh UI: 200 application/pdf, modal tutup, notifikasi sukses).
- **Filter Rating**: kontrol rating minimal (Semua/3+/4+/4,5+) di Galeri Desain (`gallery-minrating`) & Master Desain (`rnd-designs-minrating`), saring sisi klien + empty-state reset. Verified (UI 3→2 kartu pada ★4+).
- PS-17 masih DITUNDA — menunggu D-13 dari pemilik (ditanyakan).

---
## SESI 2026-08-07 (lanjutan-3) — PS-17 SELESAI ✅
Divisi sebagai aktor R&D dibangun sesuai D-13 (1a daftar 7 divisi; 2a matriks approver; 3a R&D-only tanpa ubah RBAC global; 4a 1 orang=1 divisi, admin/manager super-role).
- Backend: `config_divisions.py`, `services/rnd_org_service.py`, `routers/rnd_org.py` (GET /api/rnd/divisions, GET/PUT /api/rnd/divisions/members) + KPI division-aware (`?division` filter + field). Penempatan disimpan per-NAMA di `rnd_person_divisions` (desainer sering bukan user), dicerminkan ke users.division bila cocok.
- Frontend: tab baru **Desainer › Divisi & Persetujuan** (kartu divisi + matriks approver + tabel anggota dgn dropdown penempatan) + kolom & filter DIVISI di tabel KPI. Nav terdaftar (hubTabs/navMeta/AppViewRouter).
- Seed menempatkan 5 orang (idempotent). Terverifikasi testing agent iter 205: BE 24/24, FE 100%, regresi 100%.

PS-17 tidak mengubah menu/izin global maupun penegakan persetujuan yang berjalan (sesuai 3a) — matriks bersifat rujukan resmi.

---
## SESI 2026-08-09 — FASE 1 (PS-20 / D-14) SELESAI ✅
**Matriks persetujuan divisi kini MENGIKAT** (sebelumnya rujukan tampilan saja).

- **Keputusan pemilik D-14**: (1) tegakkan 4 tahap; (2) retroaktif = SAKELAR di Pusat Pengaturan,
  bawaan "semua dokumen termasuk yang menunggu"; (3) **Direksi = peran admin** (tanpa peran baru);
  (4) urutan fase: penegakan → Harga per Pelanggan → BOM Printing → BI Sales + BI Stok.
- **Backend**: `config_divisions.py` (tiap tahap dapat `levels` + doc_type + view),
  `config_catalog_approval_matrix.py` (5 sakelar baru di grup "Persetujuan & Ambang"),
  `services/approval_matrix_service.py` (evaluate/guard/record/my_queue/matrix/log + `sod_blocked`
  sebagai SATU sumber SoD), `routers/approvals_matrix.py`
  (`GET /api/approvals/matrix`, `/my-queue`, `/matrix-log`). Penegakan disisipkan di endpoint
  ASLINYA: rnd specs approve/reject, sample decide, PR approve/reject, special-order approve/reject
  (kini **2 tingkat**: Manager → Direksi bila nilai ≥ `approval.po_custom_direksi_min`, bawaan Rp50jt;
  rantai dicap sejak pesanan dibuat). SoD hardcode lama di `purchase_requisition_service` diganti
  panggilan ke matriks supaya ikut Pusat Pengaturan (hilang dua sumber kebenaran).
- **Frontend**: tab baru **Pusat Persetujuan › Persetujuan Saya** (`MyApprovalsView.jsx`):
  pita status penegakan, 4 kartu tahap ber-hitungan (juga saringan), tabel antrean dengan
  Setujui/Tolak inline (+modal SKU untuk ACC Desain, alasan wajib untuk Tolak), **alasan blokir
  ditulis jujur** (peran salah / SoD / sample belum ada round ACC), dan panel **Jejak Persetujuan**.
  ACC Sample sengaja hanya "Buka" (butuh pemenang + harga). Divisi & Persetujuan dapat pita
  penegakan + kolom "Tingkat & peran yang mengikat". Detail Pesanan Khusus dapat panel rantai
  persetujuan (`special-order-approval-chain`) + timeline kini menampilkan catatan tingkat.
- **Bukti**: POC `/app/test_core_approval_matrix.py` **59/59**; `testing_agent_v3` iter 206
  backend 15/15 + frontend 100%; verifikasi mandiri di browser untuk alur 2 tingkat lintas login
  (manager L1 → baris tetap menunggu Direksi & tombol nonaktif ber-alasan → admin L2 → confirmed,
  panel rantai "✓1. Manager · Dewi Rahayu · ✓2. Direksi · Budi Santoso").
- **Gate**: `verify_api_contract` 0 ERROR/0 WARN · `check_nav_map` PASS ·
  `audit_config_wiring --strict` INV-CFG OK (5 kunci baru terbaca mesin & bisa diubah user) ·
  `verify_data_integrity` **233 PASS / 0 FAIL** — termasuk **perbaikan bug pra-ada**: seeder
  riwayat tren KPI (`scripts/seed_rnd_kpi_demo.py`) membuat round `proof_required=True` tanpa
  lampiran dan keputusan tanpa `reason_code`/`supplier_id` → INV-RND-01/02 GAGAL sejak sesi lalu;
  kini ditandai jujur (`proof_required=False`, alasan `mutu_terbaik`) dan gate hijau.
- **Registry**: `ENTITY_REGISTRY.md` mencatat koleksi baru `approval_matrix_log` **dan**
  `rnd_person_divisions` (PS-17 yang belum terdaftar).

### Berikutnya
Fase 2 Daftar Harga per Pelanggan → Fase 3 BOM Printing → Fase 4 BI Sales + BI Stok.

---
## SESI 2026-08-10 — FASE 2 (F1b / D-14) DAFTAR HARGA PER PELANGGAN — SELESAI ✅

**Titik henti sesi lalu**: bug parsing angka CSV (pemisah ribuan Indonesia vs titik
desimal). **Diperbaiki & dibuktikan**: `_parse_money` membaca DUA gaya sekaligus —
`"255.000"→255000` · `"255.000,50"→255000,5` · `"255000.75"→255000,75` ·
`"1.265.400"→1265400`. Dulu `.replace(".","")` membuat hasil ekspor sistem
(`126540.00`) terbaca **100× lebih besar**.

### Keputusan pemilik sesi ini
1. Harga pelanggan di bawah **harga PT/HPP** WAJIB persetujuan manajer, dan
   **logikanya harus SAMA dengan fitur Harga Khusus yang sudah ada — jangan duplikasi**.
2. **POS memakai harga langganan otomatis** begitu kasir memilih pelanggan; bawaan harga PT.
3. Hak akses: admin/manager kelola, **sales hanya lihat**.
4. Format CSV bawaan `sku;nama_produk;harga_pelanggan;berlaku_dari;berlaku_sampai;catatan`.

### Backend
- `services/price_guard_service.py` (BARU) — **SATU definisi batas bawah harga**
  (harga PT via `pricelist_service` + HPP via `costing_service.wac_for_product`,
  fallback `products.harga_pokok`). Dipakai **dua-duanya**: Daftar Harga per Pelanggan
  DAN layar Harga Khusus (yang dulu hanya membandingkan `products.price` dan tidak
  pernah melihat HPP). 3 kunci baru di Pusat Pengaturan grup "Harga, Diskon & Komisi":
  `pricelist.customer_price_approval` · `pricelist.customer_price_floor`
  (entity_price|hpp|both) · `pricelist.customer_price_tolerance_pct`.
- `services/price_approval_service.py` (BARU) — bagian BERSAMA alur `price_approvals`
  (bentuk dokumen, `norm_until`, `is_active`, `decorate`, notifikasi approver, resolusi
  aturan STANDING, efek lanjutan keputusan). Router `price_approvals.py` memakai modul
  ini (bukan menyalin logika) → satu sumber kebenaran.
- `services/customer_price_service.py` — harga di bawah batas → record
  `pending_approval` + pengajuan `price_approvals` (`source="customer_pricelist"`).
  Approve → record aktif & record lama ditutup **saat aktivasi** (bukan saat pengajuan,
  supaya harga lama tetap dipakai selama menunggu). Reject → `rejected`.
  `patch_price` menilai ulang batas bawah (tidak ada jalan pintas lewat tombol "ubah").
- **Pemisahan tugas (SoD)** disambungkan ke `approval_matrix_service.sod_blocked`
  (ikut Pusat Pengaturan): pengaju tidak boleh menyetujui/menolak pengajuannya sendiri.
- **CELAH NYATA yang ditemukan agen uji & ditutup**: aturan harga khusus `standing`
  berstatus `approved` TIDAK BISA dihentikan (DELETE 409, PATCH hanya draf) sehingga
  harga lama menempel selamanya. Endpoint baru `POST /api/price-approvals/{id}/revoke`
  ("Akhiri Aturan"): alasan WAJIB, hanya approver, tidak bisa dua kali (409), pengaju
  dinotifikasi, dan record harga langganan penopangnya ikut dinonaktifkan.
- Jejak keputusan tidak menyamar jadi aturan: `price_approvals` ber-`customer_price_id`
  dikecualikan dari resolusi STANDING (dulu harga langganan dihitung dua kali dan
  dilabeli "Khusus").
- Seed demo idempotent: pelanggan "Toko Kain Sejahtera" 2 harga BERLAKU + 1 MENUNGGU.

### Frontend
- **Layar baru `Daftar Harga per Pelanggan`** (`cs-price-list`, sebelumnya "Segera
  Hadir"): grid per produk (umum · PT · pelanggan · khusus · **efektif + lencana
  sumber**), pilih entitas/pelanggan, cari, filter "hanya yang punya harga", pita
  kebijakan penjagaan, 4 KPI, modal Tetapkan Harga dengan **peringatan batas bawah
  hidup** dari `/customer-prices/floor`, modal Riwayat, modal Impor CSV (server yang
  mengurai angka), Ekspor CSV, tautan ke Persetujuan Harga.
- `hooks/useEffectivePrices.js` (BARU) — SATU panggilan `/customer-prices/quote`
  menggantikan **≤40 panggilan** `/price-approvals/effective` per render.
- **Bilah pilih pelanggan di POS** (`pos-customer-bar`): tanpa ini keputusan pemilik
  (#2) tak mungkin terpenuhi karena pemilih pelanggan hanya ada di dalam Checkout, dan
  Checkout baru bisa dibuka setelah keranjang berisi.
- **Konsistensi harga**: kartu produk, Produk Terlaris, Sering dibeli, popup produk,
  keranjang, Checkout langkah 1/2/3 semuanya memakai harga EFEKTIF (harga umum dicoret).
  Dulu kartu memasang lencana "Harga pelanggan" tetapi angkanya harga umum, dan
  ringkasan Checkout langkah-1 menampilkan total BERBEDA dari tombol keranjang.
- Detail SO: lencana `price_source` per baris. Kartu Persetujuan Harga: lencana asal
  "Daftar Harga Pelanggan", snapshot batas bawah/HPP, tombol **Akhiri Aturan**, dan
  status baru (Digantikan/Dibatalkan/Diakhiri).
- Bug hantu: `isComingSoonView()` menganggap semua view `cs-*` belum jadi → layar baru
  dirender BERSAMA kartu "Segera Hadir"; `cs-price-list` didaftarkan LIVE.

### Bukti
- POC `/app/test_core_customer_pricelist.py` **94/94**, **LULUS 3× berturut-turut tanpa
  seed ulang** (idempotensi — kegagalan jalan-ulang inilah yang membongkar celah revoke).
- `bash scripts/gate.sh` **HIJAU** · `verify_api_contract` **0 ERROR/0 WARN** ·
  `check_nav_map` PASS · `audit_i18n_id` 0 temuan (8 temuan pra-ada ikut dibereskan) ·
  build FE bersih.
- `testing_agent_v3` iter 207 (BE 39/39) · iter 208 (BE 46/46 termasuk 8 uji revoke) ·
  iter 209 (BE 99/99). Frontend iter 209 terhalang cara uji agen (navigasi hash — aplikasi
  ini memang berbasis state, bukan hash), sehingga **diverifikasi mandiri di browser**:
  navigasi dari state bersih, konsistensi harga 8 titik, alur persetujuan lintas login,
  SoD 403, impor CSV UI (285.000 → Rp 285.000), Akhiri Aturan (alasan wajib → "Diakhiri"),
  RBAC sales/gudang, dan **POS → Pesanan tersimpan**: KSC/SO-00013 Butik Bali Indah
  Rp 3.220.000 = 322.000 × 10 dengan `price_source="customer"`.

### Berikutnya
Fase 3 **BOM Printing** → Fase 4 **BI Sales + BI Stok**.
