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
