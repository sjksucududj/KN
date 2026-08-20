# RENCANA EKSEKUSI — "MD ERP" **v2**
### lini · tahapan proses · dua satuan · sampling · inspeksi/QC · papan PO · permintaan desain · notifikasi · makloon

> **Revisi 2 — 2026-08-18 (sesi sore).** v1 (sesi pagi) diarsipkan apa adanya di
> `docs/arsip/RENCANA_EKSEKUSI_MD_ERP_v1_2026-08-18.md`.
>
> **Kenapa ada v2:** pemilik meminta *"cek kondisi sekarang, tambahkan apa yang harus
> diedit, pastikan UI/UX tidak berubah, pastikan aturan entitas terimplementasi dengan
> benar terutama soal dokumen, recheck & double-check, dan pastikan agen berikutnya
> paham konteksnya."* Seluruh angka di v1 ditulis sebagai **prosa** — dan prosa tidak
> bisa memerah. Saat diukur ulang ke kode & basis data, **7 klaim v1 ternyata salah**
> dan **5 ketidakkonsistenan (DRIFT) baru ketemu** yang akan meledak di tengah fase
> kalau tidak dicatat sekarang (§2).
>
> Sumber kebutuhan (tidak berubah): `docs/sumber/ERP_per_divisi_2026-08-18.xlsx`,
> `docs/sumber/FORMAT_GSHEET_MD_ERP_2026-08-18.xlsx`, penjelasan alur pemilik sesi
> 2026-08-18, analisis `ANALISIS_FLOW_DIVISI.md`.

---

# 0. UNTUK AGEN BERIKUTNYA — KONTEKS DALAM DUA MENIT

**Baca §0 sampai habis sebelum menyentuh satu baris kode.** Bagian ini ada karena
sesi sebelumnya kehilangan waktu untuk menemukan ulang hal yang sudah diketahui.

### 0.1 Aplikasi apa ini, dan di fase mana kita
ERP tekstil multi-badan-usaha (grup: PT Kain Suka Cita "KSC", CV Kanda Suka, dst.)
untuk perusahaan kain: penjualan (SO), pembelian (PR→PO→terima), gudang ber-roll
(satu roll = satu identitas), makloon/subkontrak, keuangan lengkap (AR/AP, kas/bank,
GL, pajak, kontrabon, antar-PT), HR, R&D (spesifikasi & sample).
Riwayat pekerjaannya ada di **`plan.md`** (1.683 baris, dari FASE E-0 sampai P7) dan
**`SESSION_HANDOFF.md`**. Yang **belum** ada adalah lapisan kerja **MD** (merchandiser):
lini produk, tahapan proses sebagai master, dua satuan (roll + yard/kg/panel),
sampling multi-jenis, inspeksi/QC sebagai dokumen ber-SPK, papan PO per lini,
permintaan desain, dan pengalamatan notifikasi. **Itulah isi dokumen ini.**

### 0.2 Menyalakan lingkungan (repo baru di-clone / pod baru)
```bash
bash /app/.restore_env.sh      # pip + yarn + restart backend + seed_realistic + build FE (~4 menit)
sudo supervisorctl status      # backend & frontend RUNNING
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/api/     # 200
```
Akun uji: `memory/test_credentials.md` (admin `admin@kainnusantara.id` / `demo12345`;
ada juga sales, manager, warehouse, finance, sales_admin).
**Jangan** menyentuh `backend/.env` (MONGO_URL, DB_NAME) & `frontend/.env`
(REACT_APP_BACKEND_URL).

### 0.3 Cara mengukur keadaan — **jangan percaya prosa, jalankan alat**
```bash
python scripts/audit_md_erp_readiness.py            # 96 fakta, per fase (BARU di v2)
python scripts/audit_md_erp_readiness.py --fase LTU # hanya fase tertentu
python scripts/audit_md_erp_readiness.py --strict   # exit 1 bila ada DRIFT
bash   scripts/gate.sh --quick                      # ~7 s, gate statik
bash   scripts/gate.sh --full                       # ~95 s + seluruh POC fase
python scripts/validate_compliance.py               # 22 CHECK (termasuk CHECK 8 registry)
cd backend && python -m scripts.verify_entity_scoping   # gate isolasi antar-PT
```
`audit_md_erp_readiness.py` (96 fakta) membedakan **SELESAI / BELUM / DRIFT** dengan sengaja:
"BELUM" bukan kesalahan (itu peta pekerjaan), **"DRIFT" adalah kesalahan hari ini**.
Baseline sesi ini (2026-08-18 sore): **SELESAI 16 · BELUM 73 · DRIFT 7**.

### 0.4 Arti "selesai" di repo ini (tiga-tiganya wajib, bukan pilihan)
1. **POC yang bisa dijalankan** (`backend/test_core_*_poc.py`) → hijau, terdaftar di `scripts/gate.sh`.
2. **Gate/invarian yang bisa MEMERAH** (`scripts/guardrails/verify_*.py` ber-`--self-test`).
   Self-test wajib membuktikan penjaganya menangkap pelanggaran **buatan** — penjaga yang
   tak pernah bisa merah = dekorasi.
3. **Uji lewat layar** (agen uji UI) memakai user story fase itu + `plan.md` diperbarui.
Plus: `gate.sh --full` hijau **dan** nol residu (`INV-GATE-01`).

### 0.5 Sumber kebenaran (SSOT) yang WAJIB dipakai, bukan ditulis ulang
| Urusan | SSOT | Catatan |
|---|---|---|
| Koleksi & field per entitas | `backend/entity_scope.py` + `ENTITY_REGISTRY.md` | §3 |
| Nomor dokumen per badan usaha | `core_utils.next_doc_number(..., entity_id=…)` | `KSC/INS-00001` |
| Relasi antar dokumen | `services/doc_refs_service.py` (`DOC_TYPES`, `REL_INVERSE`) | dua arah |
| Enum domain | `backend/domain_registry.py` → `GET /api/enums` → `hooks/useDomainEnums.js` | FE dilarang hardcode |
| Master berlapis (global→PT) | `services/entity_master_service.py` (`MasterSpec`) | §3.3 |
| Grade roll | `services/grade_service.set_roll_grade()` | satu-satunya pintu |
| Poin cacat & ambang grade | `services/qc_inspection_service.py` | jangan hitung ulang |
| Antrean keputusan | `services/approval_backlog_service.QUEUES` + `INV-APPR-01` | pintu baru wajib terdaftar |
| Notifikasi | `services/notification_service.py`, `alert_ops_service.py` | §7 FASE N |
| Navigasi & judul layar | `frontend/src/config/navStructure.js`, `navMeta.js`, `AppViewRouter.jsx` | §4 |
| Bahasa antarmuka | `docs/KN_32_GLOSARIUM_BAHASA_ANTARMUKA.md` + `scripts/audit_i18n_id.py` | Indonesia |
| Standar tampilan | `docs/KN_08_UI_UX_STANDARDS.md`, `design_guidelines.md` | §4 |

### 0.6 Kesepakatan kerja dengan pemilik
* Fase **L → T → U** boleh dikerjakan **tanpa menunggu jawaban apa pun**.
* Fase **S** & **I** menunggu **5 keputusan pemilik** (§12). Kalau jawabannya belum
  datang saat L/T/U selesai, kerjakan **D** (permintaan desain) dan **P-0**
  (tautan PO→PR, §7 FASE P) yang juga tidak butuh keputusan.
* Setiap fase ditutup dengan laporan: apa yang diukur sebelum, apa yang berubah, dan
  bukti (POC + gate + user story).

---

# 1. PRINSIP (supaya tidak lahir duplikat)

1. **Satu fakta = satu tempat.** Angka turunan (berapa yang sudah diterima, tanggal
   masuk, jumlah roll) **dihitung** dari dokumen sumbernya; tidak diketik ulang.
2. **Pakai mesin yang sudah ada** (§5). Menambah pintu kedua untuk fakta yang sama
   adalah kelas bug termahal di repo ini — riwayatnya: tiga angka berbeda untuk satu
   pertanyaan *"berapa yang menunggu persetujuan"* (ditutup di FASE F-6).
3. **Master, bukan hardcode.** Semua daftar yang bisa bertambah (lini, tahapan, jenis
   sampling, alasan komplain) memakai `MasterSpec` → dapat API generik + layar generik
   (**dengan catatan penting di §3.3: kolom layarnya TIDAK otomatis**).
4. **Tiap fase ditutup bukti** (§0.4).
5. **Tidak setengah jalan.** Tiap fase punya "titik yang WAJIB ikut berubah"; fase
   selesai hanya bila seluruh daftar hijau.
6. **UI/UX tidak berubah** (§4). Fase-fase ini menambah *kolom, chip penyaring, dan
   layar baru* — bukan gaya visual baru.

---

# 2. KEADAAN TERUKUR 2026-08-18 — DAN 7 KOREKSI ATAS v1

Diukur pada `DB_NAME=test_database` sesudah `seed_realistic.py`, 104 koleksi.

### 2.1 Koreksi klaim v1 (semua sudah diverifikasi ulang)

| # | Klaim v1 | Kenyataan terukur | Akibat kalau tidak dikoreksi |
|---|---|---|---|
| K1 | `uoms` berisi **MTR·YRD·RLL·PCS·CM·INCH** | **4 baris**: `MTR, PCS, RLL, YRD`. `CM`/`INCH` hanya ditambahkan `bootstrap.sync_uom_factors()` **bila belum ada**, dan `seed_realistic.seed_uoms()` menimpanya kembali jadi 4 → jumlahnya bergantung urutan restart vs seed | Rencana "tambah 2 satuan" jadi salah hitung; POC U3 mengukur hal yang tidak stabil |
| K2 | Satuan yang hilang hanya **KG** & **PANEL** | Dokumen memakai `kg`, `meter`, `yard`; **tak satu pun** cocok dengan `code` master (`MTR/YRD`). Konversi tetap benar karena `uom_service.CANON`/`WEIGHT_CANON` menormalkan huruf kecil — jadi **masternya memang tidak dipakai sebagai kosakata dokumen** | Menambah baris `KG` ke master **tidak akan mengubah apa pun** di layar; harus ada keputusan kosakata (§7 FASE U langkah A) |
| K3 | `color_library.system` baru `"KN"`, "siap menampung Pantone" | Sudah ada **`KN`, `TCX`, `TPX`** (28 warna) — TCX/TPX **adalah** sistem Pantone | Pekerjaan FASE S bagian C sebagian besar **sudah selesai**; sisanya hanya penyaring sistem di pemilih warna |
| K4 | `qc_inspections` = koleksi inspeksi yang sudah ada | Koleksi **tidak pernah dibuat** (0 dokumen) dan namanya **hanya muncul di `entity_scope.py`**. Hasil inspeksi hari ini disimpan di **`inventory_rolls.inspection`** + `inventory_rolls.defects` | Rencana bisa membuat pintu ke-3; dan registry entitas terus berbohong (§2.2 D2) |
| K5 | Pembaca `sample_type` = 5 berkas | **9 berkas backend** (`domain_registry.py`, `schemas_rnd.py`, `indexes.py`, `routers/rnd.py`, `services/rnd_sample_service.py`, `rnd_spec_service.py`, `rnd_kpi_service.py`, `rnd_sla_service.py`, `approval_matrix_service.py`) + **8 berkas frontend** | Migrasi `sample_type → sample_types[]` akan meninggalkan pembaca yatim (KPI & SLA diam-diam salah) |
| K6 | `approval_backlog_service` perlu diubah karena label antrean memakai `sample_type` | Antrean `rnd_sample` memakai **`status` + `decision.supplier_id`**, tidak menyentuh `sample_type` | Perubahan yang tidak perlu di berkas paling sensitif (KPI beranda) |
| K7 | `sales_name` PO bisa dirunut lewat PR (`source="so_repeat"`) | Rantainya **putus**: `purchase_orders` **tidak punya** `pr_id`/`source`/`refs→purchase_requisition` (0 dari 14 PO). PR→PO ada satu arah (`po_ids`, terisi 1 dari 5). `PR.source` di data demo hanya `manual`/`reorder`; `so_repeat` ada di **kode** (`restock_service.PR_SOURCE`) tetapi belum pernah terpakai | FASE P akan "menampilkan Nama Sales" yang selamanya kosong |

### 2.2 Tujuh DRIFT hari ini (bukan bagian rencana — tapi wajib diputuskan di fasenya)

| ID | DRIFT | Ukuran | Dibetulkan di |
|---|---|---|---|
| **D1** | Kosakata satuan dokumen ≠ kode master `uoms` | dipakai `kg, meter, yard`; master `MTR, PCS, RLL, YRD` | FASE U langkah A |
| **D2** | `qc_inspections` terdaftar SCOPED tapi tak pernah ada | 0 dokumen, 0 penulis | FASE I langkah A (dicabut/diganti) |
| **D3** | PO tidak menaut PR (jejak PO→PR→SO putus) | 0/14 PO ber-`pr_id`; 1/5 PR ber-`po_ids` | FASE P langkah **P-0** |
| **D4** | `design_gallery.code` kosong | 2 dari 4 artwork tanpa kode | FASE D langkah A (+ seed) |
| **D5** | Notifikasi ber-alamat "semua peran" | 11 dokumen: `low_stock`×9, `order_approval`×1, `internal_request_decided`×1 | FASE N |
| **D6** | `REL_LABEL` punya label untuk relasi `applied_to` yang **tidak ada** di `REL_INVERSE` → `doc_refs_service.link(..., rel="applied_to")` akan **melempar** `RefsError`. Tidak pernah terpakai (grep: 0 pemakaian sebagai relasi), jadi cacatnya tertidur — dan tepat jenis inilah yang menjebak agen berikutnya yang membaca `REL_LABEL` sebagai daftar pilihan | 16 nilai di `REL_INVERSE` (8 pasangan) vs 17 label di `REL_LABEL` | FASE I langkah B (saat menaut acuan sample) |
| **D7** | **Nomor dokumen demo tidak mengikuti skema — dan ADA YANG KEMBAR.** `scripts/seed_rnd_kpi_demo.py` (dipanggil `seed_realistic.py:5940`) menulis `number` dengan f-string `f"KSC/SMP-H{back}{designer[:2].upper()}"` alih-alih `core_utils.next_doc_number()`; dua desainer ber-awalan huruf sama menghasilkan **nomor dokumen ganda** | 20 dari 28 `md_samples.number` menyimpang pola `KSC/SMP-00001`; **5 nomor kembar** (`KSC/SMP-H1DE`, `H2DE`, `H3DE`, `H4DE`, `H5DE`) | FASE S (perbaiki seeder + POC S7 menuntut pola & keunikan) |

Catatan jujur tambahan (tidak dihitung DRIFT karena tidak salah, tapi mudah menyesatkan):
* `inventory_rolls.inspection` **polimorfik**: bentuk 4-point
  (`points/grade/defects/gsm_actual/width_actual/thresholds/lot_*`) dari
  `qc_inspection_service`, dan bentuk retur (`condition/disposition/
  recommended_outcome/accepted_qty`) dari `return_service`. Keduanya sah, tetapi
  FASE I wajib memilih **satu** bentuk kanonik untuk dokumen inspeksi dan
  memperlakukan sisanya sebagai proyeksi.
* Roll hasil retur **lahir langsung ber-grade** (`grade: "B"`) tanpa `grade_history`
  — itu **bukan** pelanggaran `grade_service` (grade saat lahir ≠ perubahan grade),
  tetapi gate `INV-QC-02` (FASE I) wajib mengecualikannya secara **tertulis**, kalau
  tidak ia memerah palsu sejak hari pertama.
* `uoms` baris `RLL` ber-`base_type: "volume"` (semestinya `count`). Inert hari ini —
  hanya `base_type == "length"` yang dibaca `uom_service.load_fixed_factors()`.
  Dirapikan di FASE U (idempotent), bukan sekarang.
* `EntityMastersView.jsx` sudah **543 baris** (panduan 500, batas keras 1000).
  Menambah 4 jenis master ke dalamnya akan mendorongnya ke ±700 → **pindahkan
  definisi kolom/field ke berkas data terpisah** (§4.2).

### 2.3 Angka dasar yang dipakai rencana ini
`products` 19 · `users` 10 (admin·sales×3·manager×2·warehouse×2·finance·sales_admin) ·
`sales_orders` 11 · `purchase_orders` 14 · `purchase_requisitions` 5 ·
`inventory_rolls` 59 · `wms_tasks` 24 · `md_samples` 28 (`labdip`+`proofing`;
`bulk_sample` **0**) · `md_specs` 2 · `design_gallery` 4 · `makloon_orders` 3 ·
`supplier_contracts` 12 · `color_library` 28 · `notifications` 32 · `special_orders` 3.
Nomor dokumen: gaya **baru** per badan usaha sudah dipakai `md_samples` (`KSC/SMP-00001`),
`md_specs` (`KSC/SPEC-…`), `supplier_contracts` (`KSC/SCT-…`); gaya **lama** bersama
masih dipakai `purchase_orders` (`PO-00001`), `sales_orders` (`SO-0001`),
`makloon_orders` (`MKO-00001`), `sales_returns` (`SRET-00001`). **Rencana ini tidak
menomori ulang apa pun** — dokumen BARU wajib gaya baru.

---

# 3. KONTRAK PAGAR ENTITAS — WAJIB untuk setiap koleksi & dokumen baru

> Inilah bagian yang pemilik minta di-*double check*. Repo ini punya **6 lapis** pagar
> antar-badan-usaha yang sudah terbukti; melewatkan satu lapis menghasilkan kebocoran
> yang tidak terlihat sampai ada pengguna PT lain membuka layar.

### 3.1 Dua belas titik sambung (checklist per koleksi baru)

| # | Titik | Berkas / simbol | Kalau dilewatkan |
|---|---|---|---|
| 1 | Field entitas | `entity_scope.SCOPE_FIELD` (default `entity_id`; inventori pakai `owner_entity_id`) | gate menilai field yang salah |
| 2 | Daftar wajib ter-scope | `entity_scope.SCOPED_COLLECTIONS` | `verify_entity_scoping` tidak menjaga koleksi itu |
| 3 | Baris global sah | `entity_scope.INHERITED_GLOBAL_VALUES` (**hanya master berlapis**: `["all","",None]`) | baris global **hilang** dari layar |
| 4 | Query daftar | `resolve_list_scope()` — atau `resolve_list_scope_inherit()` untuk master berlapis | PT lain ikut terbaca |
| 5 | Stempel saat tulis | `stamp_entity()` / `assert_write_entity()` | dokumen masuk buku PT yang salah |
| 6 | Akses per dokumen | `assert_entity_access()` di semua endpoint by-id | IDOR (`verify_cross_entity` menangkap) |
| 7 | Mode "Semua Entitas" | `entity_write_guard`: rute akar koleksi ditolak **409**; rute ber-`{param}` boleh; master tingkat grup didaftarkan eksplisit | tulis diam-diam ke PT home |
| 8 | Nomor dokumen | `core_utils.next_doc_number(coll, field, "INS-", entity_id=ctx…)` → `KSC/INS-00001` | nomor tabrakan antar-PT |
| 9 | Relasi dokumen | `doc_refs_service.DOC_TYPES` (`_T(...)`) + `link_child()`; `rel` hanya dari `REL_INVERSE` | jejak dokumen berhenti; `INV-REF` merah |
| 10 | Index | `backend/indexes.py` (minimal `(entity_id, status)` + FK yang dipakai papan) | COLLSCAN di daftar terpanas |
| 11 | Dokumentasi registry | `ENTITY_REGISTRY.md` (heading `### nama_koleksi` + tabel field) | **CHECK 8 `validate_compliance.py` MEMERAH** |
| 12 | Gate residu | `scripts/gate_residue.py WATCH` (**dokumen transaksional**) | POC meninggalkan sampah permanen tak terlihat |

Tambahan wajib per **dokumen** (bukan master):
13. **Izin**: modul baru di `backend/permissions_config.py` (`DEFAULT_PERMISSIONS`) +
    dipakai lewat `dependencies.require_permission(request, "<modul>", "<aksi>")`.
14. **Antrean keputusan**: setiap endpoint `approve|reject|verify|decide` **wajib**
    punya baris di `approval_backlog_service.QUEUES` atau alasan tertulis di
    `scripts/guardrails/verify_approval_queues.DOOR_EXEMPT` — gate `INV-APPR-01`
    menemukan pintu baru lewat regex pada router, jadi **tidak bisa dilupakan**.
15. **Seed**: `seed_realistic.py` wajib menghasilkan minimal 1 dokumen (fitur "hijau
    tapi hampa" adalah temuan berulang di repo ini) **melalui jalur servis yang sama**,
    bukan `insert_one` mentah (lihat pelajaran roll retur di §2.2).

### 3.2 Instansiasi untuk 5 koleksi baru + 1 master kecil

| Koleksi | Jenis | Field entitas | Nilai global? | DOC_TYPES | WATCH residu | Nomor | Izin modul |
|---|---|---|---|---|---|---|---|
| `product_lines` | master berlapis | `entity_id` | **ya** `["all","",None]` | – | – | – | lewat `settings` |
| `process_stages` | master berlapis | `entity_id` | **ya** | – | – | – | lewat `settings` |
| `sample_types` | master berlapis | `entity_id` | **ya** | – | – | – | lewat `settings` |
| `complaint_reasons` | master berlapis | `entity_id` | **ya** | – | – | – | lewat `settings` |
| `inspections` | **dokumen** | `entity_id` | tidak | `_T("inspection", "inspections", "number", "Inspeksi & QC", "inspections", order=26, needs_parent=True, source_fk=["ref_doc_id"])` | **ya** | `INS-` → `KSC/INS-00001` | **`inspection`** |
| `design_requests` | **dokumen** | `entity_id` | tidak | `_T("design_request", "design_requests", "number", "Permintaan Desain", "design-requests", order=1, source_fk=["so_id"])` | **ya** | `DSR-` → `KSC/DSR-00001` | **`design_request`** (atau perluas `rnd`) |

### 3.3 Tiga jebakan master berlapis (diverifikasi ke kode, bukan asumsi)

1. **Layar master TIDAK otomatis.** `entity_master_service.MASTERS` memberi API generik
   (`/api/entity-masters/{kind}` + `/effective` + `/override`), tetapi
   `frontend/src/features/settings/masters/EntityMastersView.jsx` memegang
   **`COLUMNS` dan `CREATE_FIELDS` per jenis secara hardcode** (baris 35–98). Jenis baru
   tanpa entri di situ akan muncul di daftar jenis dengan **tabel tanpa kolom**.
   → §4.2: definisi kolom/field dipindah ke `masters/masterFieldsConfig.js`.
2. **Baris global vs override.** `patch` baris global saat satu PT aktif **ditolak**
   (409, ber-kalimat menuntun); jalurnya tombol **"Buat khusus <PT>"** (`/override`),
   dan `revert` **menghapus** override. Perilaku ini sudah benar — jangan diubah,
   cukup ikuti.
3. **`POST /api/entity-masters/{kind}` lolos pagar mode gabungan** karena rutenya
   punya `{param}` — dan itu **memang disengaja**: di mode "Semua Entitas" baris baru
   lahir sebagai **GLOBAL**. Jadi master baru **tidak** perlu didaftarkan di
   `entity_write_guard.GROUP_LEVEL_EXACT`. Sebaliknya, **endpoint dokumen baru**
   (`POST /api/inspections`, `POST /api/design-requests`) **harus** ditolak 409 di mode
   gabungan — yaitu perilaku bawaan (rute akar koleksi), jadi **jangan** menambahkannya
   ke `GROUP_LEVEL_EXACT`. POC wajib membuktikan 409-nya.

### 3.4 Aturan dokumen inspeksi terhadap grade & cacat (anti pintu ke-3)

```
                     ┌─────────── SATU-SATUNYA PENGHITUNG ───────────┐
petugas isi cacat ──▶ qc_inspection_service.inspect_roll()             ──▶ inventory_rolls.inspection
   (dari layar        · compute_points()  · grade_from_points()            (SSOT per-roll: poin,
    inspeksi baru)    · grade_service.set_roll_grade(source=              cacat, gsm/lebar aktual,
                        "qc_inspection")                                   lot, warna & handfeel*)
                                    │                                              │
                                    │ mengembalikan hasil                          │ dibaca
                                    ▼                                              ▼
                     inspections.lines[]  =  RINGKASAN + keputusan  (bukan sumber angka)
                     · roll_id, roll_no, qty{rolls,measure,unit}
                     · points_snapshot, grade_before, grade_after   ← WAJIB == isi roll
                     · color_result, handfeel_result, decision, remark
```
`*` field `color_result`, `handfeel_result`, `handfeel_score`, `baseline_sample_id`
**ditambahkan ke dalam `inventory_rolls.inspection` yang sudah ada** (memperluas
`inspect_roll()`), **bukan** disimpan hanya di dokumen. Alasannya: pertanyaan "roll ini
warnanya beda dengan sample, boleh masuk gudang?" ditanyakan **di roll**, bukan di
dokumen — dan itulah tempat pagar putaway membacanya.

**Gate `INV-QC-02` (dua arah, dengan pengecualian tertulis):**
* setiap `inspections.lines[]` yang ber-`grade_after ≠ grade_before` **wajib** punya
  `inventory_rolls.grade_history[]` yang cocok (roll, `source="qc_inspection"`, waktu ±5 menit);
* setiap `grade_history[]` ber-`source="qc_inspection"` **wajib** punya baris dokumen inspeksi;
* `points_snapshot` di dokumen **wajib sama** dengan `inventory_rolls.inspection.points`;
* **DIKECUALIKAN (tertulis)**: grade saat roll **lahir** (retur karantina lewat
  `return_service`), `quarantine_release`, `manager_override`, `migration`.

---

# 4. KONTRAK UI/UX — **"TIDAK ADA YANG BERUBAH"**

> Permintaan pemilik: *"pastikan UI/UX tidak berubah."* Ditafsirkan tegas: **bahasa
> visual, tata letak, navigasi, dan perilaku layar yang sudah ada tidak boleh berubah.**
> Yang ditambah hanya: (a) **kolom** pada tabel yang sudah ada, (b) **chip penyaring
> lini** di bilah filter yang sudah ada, (c) **layar baru** yang memakai komponen &
> pola yang sudah ada.

### 4.1 Yang DILARANG berubah (dan cara membuktikannya)
| Dilarang | Bukti |
|---|---|
| Token warna/tipografi/spasi | `git diff --stat` **nol** untuk `frontend/src/App.css`, `index.css`, `tailwind.config.js` |
| Struktur navigasi & judul layar lama | `git diff` `config/navStructure.js`/`navMeta.js` **hanya penambahan** (baris baru), tanpa penghapusan/pengubahan `id`/`label`/`roles` yang sudah ada |
| Pola pop-up "Buat" & "Rincian" | gate `INV-UI-05` & `INV-UI-08` tetap hijau |
| Larangan `alert/confirm/prompt` | gate `INV-UI-06` |
| Error tak boleh senyap | gate `INV-UI-03` (`ErrorNotice`) |
| Id entitas teknis tak tampil (`ent_ksc`) | gate `INV-UI-02` (`utils/entityLabel.js`) |
| Bahasa Indonesia + angka gaya Indonesia | `scripts/audit_i18n_id.py`, glosarium `docs/KN_32_*` |
| Enum tak boleh hardcode di FE | `hooks/useDomainEnums.js` + gate `INV-DOMAIN-*` |
| Daftar berhalaman wajib bisa diunduh | gate `INV-UI-07` (`utils/csvExport.js`) |
| Keadaan muat/kosong/grafik | `scripts/ux_audit.py --strict` (`INV-UX-01`) |

Total **25 invarian** terdaftar di `scripts/gate.sh` (11 di antaranya khusus UI/UX/peran:
`INV-UI-01..08`, `INV-UX-01`, `INV-ROLE-01`, `INV-HOME-01`).

### 4.2 Komponen yang WAJIB dipakai ulang (jangan bikin baru)
| Kebutuhan fase ini | Pakai | Catatan |
|---|---|---|
| Form "Buat inspeksi / permintaan desain" | `components/FormModal.jsx` | pop-up, bukan panel inline |
| Panel rincian dokumen | `components/DetailModal.jsx` | `INV-UI-08` |
| Pesan gagal | `components/ErrorNotice.jsx` | wajib, `INV-UI-03` |
| Dropdown (lini, tahap, jenis sampling) | `components/KNSelect.jsx` | seragam P6 |
| Konfirmasi & alasan wajib | `components/ConfirmModal.jsx` + `ConfirmHost.jsx` | alasan **disimpan** (P5.3) |
| Daftar berhalaman + pencarian | `hooks/usePagedList.js` | kontrak `{items,total,page,page_size,has_more}` |
| Unduh CSV | `utils/csvExport.js` + `fetchAll()` | `;` + BOM + desimal koma |
| Enum & master ke layar | `hooks/useDomainEnums.js` | plus master lini lewat `/api/enums` |
| Nama badan usaha | `utils/entityLabel.js` | `INV-UI-02` |
| Chip penyaring lini | **BARU** `components/LineFilter.jsx` | satu komponen untuk 12 layar; **meniru** bilah filter yang ada di `features/orders/OrdersView.jsx` (jangan ciptakan gaya baru) |
| Dua satuan | **BARU** `components/QtyDual.jsx` | render "12 roll · 540,5 yard"; angka lewat `utils/formatters.js` |
| Kolom master baru | **BARU** `features/settings/masters/masterFieldsConfig.js` | pindahkan `COLUMNS`/`CREATE_FIELDS` ke sini (§2.2) agar `EntityMastersView.jsx` tidak melewati batas berkas |

### 4.3 Prosedur bukti "tampilan tidak berubah" (di setiap akhir fase)
1. `bash scripts/gate.sh --full` → hijau (termasuk 11 invarian UI/UX).
2. `python scripts/ux_audit.py --strict` & `python scripts/audit_i18n_id.py` → hijau.
3. `git diff --stat` disertakan di laporan; **wajib nol** untuk berkas gaya (§4.1).
4. Agen uji UI menjalankan user story fase itu **plus** 3 layar lama yang paling
   terdampak (Pesanan · Pesanan Pembelian · Daftar Roll) untuk memastikan tidak ada
   regresi tata letak.
5. Tangkapan layar sebelum/sesudah untuk 3 layar itu dilampirkan di laporan fase.

---

# 5. INVENTARIS MESIN YANG SUDAH ADA (terverifikasi ulang — **jangan dibuat ulang**)

| Kebutuhan | Sudah ada di | Bentuk / catatan v2 |
|---|---|---|
| Master berlapis global→PT + layar generik | `services/entity_master_service.py` (`MasterSpec`, 6 jenis) · `routers/entity_masters.py` · `features/settings/masters/EntityMastersView.jsx` | ⚠ kolom layar **hardcode per jenis** (§3.3) |
| Enum domain → frontend | `domain_registry.py` · `routers/enums.py` · `hooks/useDomainEnums.js` | `STAGES`(7) & `PROCESS_TYPES`(7) **dua kosakata berbeda** (§7 FASE T) |
| Relasi dokumen dua arah | `services/doc_refs_service.py` | **34** `DOC_TYPES` · **16** nilai `rel` (8 pasangan) di `REL_INVERSE` — ⚠ D6 |
| Satu pintu ubah grade + riwayat | `services/grade_service.set_roll_grade()` | sumber sah: `qc_inspection`·`quarantine_release`·`manager_override`·`migration` |
| Inspeksi 4-point per roll | `services/qc_inspection_service.py` · `routers/qc_inspection.py` · status tugas `qc_pending` | hasil disimpan di **`inventory_rolls.inspection`**, bukan koleksi tersendiri (K4) |
| Inspeksi retur (kondisi/disposisi) | `services/return_service.py` (`items[].inspection`, roll karantina) | bentuk **berbeda** dari 4-point (§2.2) |
| Sampling + iterasi ber-bukti | `md_samples.rounds[]` (`round_no`,`supplier_id`,`due_date`,`attachments`,`note`,`measurements`,`result`,`score`,`assessed_by`,`proof_required`) · `services/rnd_sample_service.py` | lampiran+catatan **wajib** saat menutup round (sudah jalan) |
| Sample ambil bahan dari roll | `POST /api/rnd/samples/{id}/issue-material` | roll berkurang + `inventory_movements` `sample_issue` |
| Spesifikasi → produk | `md_specs` + `POST /api/rnd/specs/{id}/release-product` | |
| Keputusan sample → kontrak otomatis | `rnd_sample_service` (`auto_contract_on_decide`, bawaan **True**) → `supplier_contracts` | |
| Kontrak makloon/supplier | `supplier_contracts` (37 field: `contract_type`,`partner_kind`,`process_type`,`tariff_*`,`yield_factor`,`shrinkage_pct`,`tolerance_pct`,`sample_ref`,`valid_from/to`) | 12 dokumen |
| Makloon berantai + mitra per tahap | `makloon_orders.steps[]` · `services/makloon_order_service.py` · `makloon_calc_service.estimate_output()` | rantai divalidasi **produk** (output N = input N+1), **bukan** `STAGE_TRANSITIONS` |
| Mitra per proses | `makloons.process_types[]` | terisi `celup·finishing·tenun` |
| Master satuan | `uoms` + `/api/uoms` · konversi `services/uom_service.py` (`CANON`,`WEIGHT_CANON`), `uom_rules_service`, `receiving_uom_service` | ⚠ D1 (§2.2) |
| Pustaka warna | `color_library` (`code`,`name`,`hex`,`system`,`family`) | sudah ada `TCX`/`TPX` (K3) |
| Galeri desain | `design_gallery` (`code`,`design_type`,`files[]`,`versions[]`,`status`,`ratings[]`,`repeat_cm`,`color_count`,`screen_count`) | ⚠ D4: 2/4 `code` kosong |
| Eksklusivitas produk per sales | `services/product_exclusivity.py` (`visibility_query`,`can_view`,`assert_can_order`,`filter_visible`,`normalize`) | **pola yang ditiru `line_scope`** |
| Antrean keputusan lintas modul | `services/approval_backlog_service.QUEUES` (**30** baris) + `INV-APPR-01` | pintu baru ditemukan otomatis lewat regex `approve|reject|verify|decide` di router |
| Izin per modul | `backend/permissions_config.DEFAULT_PERMISSIONS` (**61** modul) + `dependencies.require_permission` | modul baru wajib didaftarkan di sini |
| Notifikasi + dedupe + eskalasi | `services/notification_service.py` (`recipient_role`/`recipient_user`, dedupe `unread`/`day`), `alert_ops_service.py` (12+ job), `scheduler_service.JOBS` | **belum** ada alamat berbasis wewenang/divisi |
| Retur jual + karantina + pelepasan ber-grade | `services/return_service.py` (`release_quarantine`) | |
| Paginasi + CSV + pop-up | `hooks/usePagedList.js` · `utils/csvExport.js` · `FormModal`/`DetailModal` | §4.2 |

---

# 6. ALUR TARGET (bahasa pemilik → bentuk sistem)

```
              ┌─────────────────── JALUR A: BELI JADI ────────────────────┐
Pelanggan/ide ─▶ PERMINTAAN DESAIN ─▶ artwork (galeri) ─ACC─▶ SPESIFIKASI
  (SO / internal)  design_requests       design_gallery          md_specs
                        │  (FASE D)                                 │
                        └── parent: sales_orders (bila source=so)    │
                                                                     ▼
                                            SAMPLING KE SUPPLIER (FASE S)
                                            md_samples · sample_types[] =
                                            labdip &/atau handfeel &/atau proofing
                                            round 1..n per JENIS (lampiran+catatan wajib)
                                                     │ ACC
                                     ┌───────────────┴────────────────┐
                              MASTER PRODUK                    KONTRAK SUPPLIER
                              products                         supplier_contracts
                                     └───────────────┬────────────────┘
                                          PR ─▶ PO ─▶ TERIMA DI GUDANG
                              purchase_requisitions  purchase_orders  wms_tasks(GRN)
                                                     │        (FASE P: papan per lini)
                                          INSPEKSI & QC ber-SPK (FASE I)
                                          inspections(kind=po_receipt)
                                                     │  poin cacat → grade_service
                                                     ▼
                                    ┌────────────────┴─────────────────┐
                             SIMPAN DI GUDANG                  PEMENUHAN SO
                             inventory_rolls/lots               (alur yang sudah ada)

              └─────────────────── JALUR B: MAKLOON ─────────────────────┘
 Kontrak makloon ─▶ SPK Makloon (makloon_orders.steps: benang→tenun/rajut→celup /
                    proofing→pfp→screen→printing) ─▶ output ─▶ INSPEKSI & QC ─▶ GRADING
                    tiap tahap: mitra + tarif + hasil aktual (FASE T & M)
```
Dua jalur bertemu di titik yang **sama**: penerimaan → inspeksi/QC → grading →
gudang/pemenuhan. Karena itu dokumen inspeksi dibuat **satu koleksi** dengan pembeda
`kind`, bukan tiga koleksi.

---

# 7. FASE EKSEKUSI

Urutan berdasarkan **ketergantungan**: `L → T → U → (D, P-0) → S → I → P → N → M`.

---

## FASE L — LINI PRODUK (master + pagar keras yang bisa dikonfigurasi)

**Tujuan pemilik:** woven / knit / printing dikerjakan staf berbeda; harus **master
yang bisa bertambah**, pembedanya **pagar keras tapi bisa dikonfigurasi** (satu staf
boleh dapat lebih dari satu lini), dan berlaku **di semua tempat** — bukan hanya saat
membuat PO.

### L.A — Keputusan desain yang WAJIB dipatuhi (hasil double-check)
`fabric_type` (`woven|knit`, dengan `control_uom` meter/kg) **sudah ada** dan dipakai
mesin: `STAGE_TRANSITIONS`, `makloon_calc_service`, `STAGE_FIELD_RULES`,
`KNIT_RELAXED_FIELDS`. Kalau `line_code` dibiarkan menyimpan hal yang sama, dua kolom
akan saling bertentangan (produk ber-`line_code="knit"` tapi `fabric_type="woven"`).
Aturannya:

* **`fabric_type` = fisika kain** (menentukan rumus & satuan kendali) → **tetap SSOT**.
* **`line_code` = pembagian kerja/bisnis** (siapa yang mengerjakan, papan mana,
  penyaring mana) → **baru**, dan **tidak** dipakai rumus apa pun.
* **Invarian `INV-LINE-02`**: untuk lini yang `fabric_type_required` diisi
  (`woven`→woven, `knit`→knit), produk ber-lini itu **wajib** ber-`fabric_type` sama.
  Lini `printing` **tidak** mengikat `fabric_type` (kain print bisa woven maupun knit).
* `product_lines.measure_unit_default` **bukan** sumber satuan produk; ia hanya
  **usulan** saat membuat produk/PO. Satuan kendali tetap dari `fabric_type.control_uom`
  + `products.base_unit`. (Tanpa aturan ini, FASE U melahirkan sumber ketiga.)

### L.B — Master baru
`services/entity_master_service.py` → `MASTERS["product-lines"]`:
```python
"product-lines": MasterSpec(
    kind="product-lines", collection="product_lines", label="Lini Produk",
    key_field="code", name_field="name", id_prefix="pline",
    fields=("code", "name", "sort", "active", "notes",
            "fabric_type_required",      # "" | woven | knit   (INV-LINE-02)
            "measure_unit_default",      # usulan satuan: yard | kg | panel
            "stage_sequence",            # ["yarn","tenun","celup","inspect"] (kode master tahap)
            "sample_types_default"),     # ["labdip","handfeel"]  (usulan FASE S)
    sort=(("sort", 1), ("code", 1)),
    hint="Pembagian kerja MD: woven / knit / printing. Bisa ditambah tanpa ubah kode.")
```
Seed (idempotent, lewat migrasi): `woven` (fabric_type_required=woven, meas=yard,
stages `yarn→tenun→celup→inspect`) · `knit` (knit, kg, `yarn→rajut→celup→inspect`) ·
`printing` (kosong, yard, `proofing→pfp→screen→printing→inspect`).

### L.C — Field baru di dokumen (semua ber-index)
| Koleksi | Field | Aturan |
|---|---|---|
| `products` | `line_code: str` | wajib untuk produk baru; **kosong = data lama = tetap terlihat** |
| `users` | `allowed_line_codes: [str]` | **kosong = semua lini** (bawaan, tanpa regresi) |
| `sales_orders.items[]`, `purchase_requisitions.items[]`, `purchase_orders.items[]`, `warehouse_transfers.items[]`, `sales_returns.items[]`, `purchase_returns.items[]`, `interco_transactions.items[]` | `line_code` | **snapshot** dari produk saat baris dibuat (riwayat tidak berubah bila master produk diubah) |
| `sales_orders`, `purchase_orders`, `purchase_requisitions` | `line_codes: [str]` | turunan dari baris — untuk penyaring daftar & papan |
| `md_specs`, `md_samples`, `design_requests`, `makloon_orders`, `inspections`, `inventory_rolls`, `inventory_lots` | `line_code` | roll & lot ikut `_domain_snapshot` yang sudah ada |

### L.D — Berkas yang disentuh (peta edit)
**Backend — baru**
* `backend/services/line_scope.py` — meniru `product_exclusivity.py`:
  `visibility_query(actor, field="line_code")` → `{}` bila `allowed_line_codes` kosong,
  selain itu `{"$or":[{field:{"$in":allowed}},{field:{"$in":["",None]}},{field:{"$exists":False}}]}`;
  `assert_can_touch(actor, doc)` → **403** kalimat Indonesia; `filter_visible()`;
  `normalize(payload)`.
* `scripts/migrate_lini_produk.py` (idempotent · `--dry-run` · **laporan keputusan**).
* `scripts/guardrails/verify_line_scope.py` (`INV-LINE-01`, `INV-LINE-02`, ber-`--self-test`).
* `backend/test_core_lini_poc.py`.

**Backend — diubah**
| Berkas | Perubahan |
|---|---|
| `entity_scope.py` | `SCOPE_FIELD["product_lines"]="entity_id"` · `SCOPED_COLLECTIONS +=` · `INHERITED_GLOBAL_VALUES["product_lines"]=["all","",None]` |
| `services/entity_master_service.py` | `MASTERS["product-lines"]` |
| `indexes.py` | `product_lines`: `(entity_id,code)`, `(sort)` · `products`: `(line_code)` · `purchase_orders`/`sales_orders`/`purchase_requisitions`: `(line_codes)` · `inventory_rolls`: `(line_code)` |
| `domain_registry.py` | `ENUMS["product_line"]` (bentuk + **nilai benih**; nilai hidup dari master lewat FASE T) |
| `routers/enums.py` | sertakan `product_line` (dari `master_registry` bila ada, fallback benih) |
| `schemas.py` (Product), `routers/products.py` | terima/validasi `line_code`; daftar produk menyisipkan `line_scope.visibility_query` + `?line=` |
| `routers/users.py` | `PATCH /api/users/{id}` terima `allowed_line_codes` (validasi ⊆ master aktif) |
| `routers/sales_orders.py`, `sales_orders_extra.py`, `purchase_orders.py`, `purchase_orders_extra.py`, `purchase_requisitions.py`, `transfers.py`, `sales_returns.py`, `purchase_returns.py`, `inventory.py`, `lots.py`, `wms.py`, `rnd.py`, `admin.py` | daftar: sisipkan `line_scope.visibility_query(actor)` + terima `?line=` (multi, koma) · aksi tulis: `assert_can_touch` |
| `services/rnd_sample_service.py`, `rnd_spec_service.py`, `makloon_order_service.py` | daftar mereka dibangun di service → penyaring lini di situ |
| `ENTITY_REGISTRY.md` | entri `### product_lines` + field `products.line_code`, `users.allowed_line_codes` |
| `seed_realistic.py` | seed 3 lini + `line_code` semua produk + 1 akun ber-`allowed_line_codes=["printing"]` |
| `scripts/gate.sh` | daftarkan gate + POC baru |

**Frontend — baru**: `components/LineFilter.jsx` (chip **dari master**, pilihan
tersimpan per pengguna di `localStorage`, meniru bilah filter `OrdersView.jsx`).
**Frontend — diubah (12 layar + 2 pengaturan)**:
`features/admin/AdminView.jsx` (Master Produk, view `md-products`) ·
`features/orders/OrdersView.jsx` · `features/admin/PurchaseOrderManagement.jsx` ·
`features/purchasing/PurchaseRequisitions.jsx` · `features/rnd/RndSamplesView.jsx` ·
`features/rnd/RndSpecsView.jsx` · `features/rnd/RndDesignsView.jsx` ·
`features/wms/InventoryStockView.jsx` · `features/transfers/InterCompanyTransfers.jsx` ·
`features/sales/SalesReturns.jsx` · `features/purchasing/PurchaseReturns.jsx` ·
`features/purchasing/MakloonOrdersView.jsx` — plus
`features/settings/masters/EntityMastersView.jsx` + `masterFieldsConfig.js` (kolom master)
dan `features/settings/entities/EntitiesAccessView.jsx` (editor **Lini yang boleh diakses**).

### L.E — Migrasi `scripts/migrate_lini_produk.py`
1. Seed 3 baris master (global, `entity_id="all"`).
2. Isi `products.line_code` dari aturan **terukur** — dan tulis **alasan per produk**
   ke laporan:
   `fabric_type=="knit"` → `knit` · `fabric_type=="woven"` **dan** (`motif` tidak kosong
   **atau** `design_id` terisi) → `printing` · sisanya → `woven`.
   Ukuran hari ini: 19 produk (`knit` 1, `woven` 18; `motif` terisi 17, `design_id` 1)
   → perkiraan hasil: knit 1 · printing ~17 · woven ~1. **Angka ini pasti terasa
   janggal bagi pemilik** → laporan wajib berisi daftar produk + lini usulan, dan
   fase L ditutup hanya setelah pemilik/agen mengoreksi daftar itu lewat layar
   (bukan lewat skrip). *Ini bukan kelemahan migrasi; ini pengakuan bahwa data lama
   tidak menyimpan "lini" — jadi tebakan mesin harus bisa dikoreksi manusia.*
3. Backfill `line_code` ke baris dokumen dari `products`; `line_codes[]` di kepala dokumen.
4. `--dry-run` mencetak rencana tanpa menulis; dijalankan dua kali harus identik.

### L.F — POC `backend/test_core_lini_poc.py`
| # | Membuktikan |
|---|---|
| L1 | master bisa **ditambah** (lini ke-4 `denim`) lewat API tanpa satu baris kode diubah → muncul di `/api/enums` & penyaring layar |
| L2 | akun ber-`allowed_line_codes=["printing"]` **tidak** melihat produk woven di `/api/products`, dan **403** saat membuat SO berisi produk woven |
| L3 | akun tanpa `allowed_line_codes` melihat semua (tanpa regresi) |
| L4 | dokumen lama tanpa `line_code` **tetap terlihat** (tidak ada layar mendadak kosong) |
| L5 | snapshot: mengubah `line_code` produk **tidak** mengubah baris SO yang sudah ada |
| L6 | `INV-LINE-02`: produk `line_code="knit"` ber-`fabric_type="woven"` **ditolak** |
| L7 | pagar entitas tetap: master lini PT-A tak bocor ke PT-B; baris global terlihat keduanya |
| L8 | `POST /api/products` dengan header `X-Entity-Id: all` tetap berperilaku seperti sebelumnya (master SHARED — **tidak** berubah) |

### L.G — User story (acuan agen uji UI)
1. *Sebagai admin*, saya buka **Pengaturan → Master → Lini Produk**, menambah lini
   **Denim**, lalu chip **Denim** langsung muncul di layar Pesanan tanpa reload aplikasi.
2. *Sebagai admin*, di **Badan Usaha & Akses** saya beri Dewi hanya lini **Printing**;
   Dewi login dan daftar produknya hanya berisi produk printing.
3. *Sebagai Dewi (printing)*, saat mencoba menambahkan kain woven ke pesanan, saya
   mendapat pesan Indonesia yang jelas — bukan 500 dan bukan daftar kosong tanpa sebab.
4. *Sebagai manajer*, saya klik chip **Semua** dan seluruh baris lama (tanpa lini)
   tetap ada — tidak ada data yang "hilang" setelah pembaruan.

### L.H — Selesai bila
> **STATUS: SELESAI 2026-08-18** (sesi `jskskajaj/kn`). Bukti: `audit_md_erp_readiness.py --fase L`
> semua SELESAI · `gate.sh --full` HIJAU 85 gate · POC `backend/test_core_lini_poc.py` 40/40 ·
> `verify_line_scope.py --self-test` 15/15 · migrasi + laporan `docs/LAPORAN_MIGRASI_LINI_PRODUK.md` ·
> berkas gaya nol perubahan. Satu koreksi terhadap rencana (dicatat, bukan disembunyikan):
> aturan tebakan §L.E dipertajam — motif bernilai `Polos`/`-`/`None` TIDAK dihitung sebagai motif
> (kalau tidak, kain polos dikirim ke papan printing). Satu jalur tulis yang tidak ada di peta §L.D
> ikut wajib distempel: **Permintaan Internal** (`services/internal_request_service.py`) — ditemukan
> oleh gate barunya sendiri, bukan oleh manusia.


POC 8/8 · `INV-LINE-01`+`INV-LINE-02` hijau (self-test merah pada kode lama) ·
12 layar punya penyaring · laporan migrasi ditinjau & dikoreksi · `gate.sh --full`
hijau · `git diff --stat` nol untuk berkas gaya (§4.1) ·
`audit_md_erp_readiness.py --fase L` semua SELESAI.

---

## FASE T — MASTER TAHAPAN PROSES (termasuk **Screen**) + jembatan ke registry

> **STATUS: SELESAI 2026-08-19.** Bukti: POC `backend/test_core_tahapan_poc.py` **63/63**
> (nol residu stok) · `INV-DOMAIN-06` hijau + self-test 20 kasus · `gate.sh --full`
> **90 gate HIJAU / 0 FAIL** · `audit_md_erp_readiness.py --fase T` **SEMUA SELESAI** ·
> user story T.F diuji lewat peramban (SPK `MKO-00006` ber-tahap Screen: 25 yard → 25 yard,
> ongkos Rp 750.000, mitra diperingatkan saat kosong). Laporan lengkap: `plan.md` §STATUS T.
> Dua bug ikutan yang ditutup di sesi penutupan: **residu stok POC** (POC-RESIDU-01 kelas
> ulang) dan **`KN-UI-PICKER-REOPEN`** (pop-up pemilih terbuka kembali di dalam `<label>`
> → gate baru **`INV-UI-09`**).

**Tujuan pemilik:** *"screen merupakan salah satu proses di makloon (tahapan), maka
tahapan makloon juga dibuatkan masternya, lalu setiap tahapan itu memiliki pekerjaan
di makloon siapa."*

### T.A — Titik paling rawan: daftar pemilik MENCAMPUR dua kosakata
Hasil double-check ke `domain_registry.py`:
* **`STAGES`** = keadaan **kain**: `yarn · grey · pfd · pfp · finished · remnant · byproduct`.
* **`PROCESS_TYPES`** = **proses**: `tenun · rajut · pre_treatment · celup · printing · finishing · lainnya`.
* Daftar pemilik "benang · tenun · rajut · celup · pfp · **screen** · printing · inspect"
  mencampur keduanya (+1 aktivitas berdokumen).

Peta wajib (dipakai migrasi & seed — **jangan menebak lagi di kemudian hari**):

| Tahap pemilik | `kind` | `process_type` | `from_stage → to_stage` | `changes_stage` | `needs_vendor` |
|---|---|---|---|---|---|
| Benang | `material` | – | – → `yarn` | ya (masuk bahan) | tidak |
| Tenun | `makloon` | `tenun` | `yarn → grey` | ya | ya |
| Rajut | `makloon` | `rajut` | `yarn → grey` | ya | ya |
| PFP | `makloon` | `pre_treatment` (+`target_use="print"`) | `grey → pfp` | ya | ya |
| PFD (implisit) | `makloon` | `pre_treatment` (+`target_use="dye"`) | `grey → pfd` | ya | ya |
| Celup | `makloon` | `celup` | `pfd → finished` | ya | ya |
| **Screen** | `makloon` | **`screen` (BARU)** | `pfp → pfp` | **tidak** | ya |
| Printing | `makloon` | `printing` | `pfp → finished` | ya | ya |
| Proofing | `sampling` | – | – | tidak | ya (supplier/mitra) |
| Inspect | `inspection` | – | – | tidak | tidak (petugas internal, FASE I) |

### T.B — Master baru
```python
"process-stages": MasterSpec(
    kind="process-stages", collection="process_stages", label="Tahapan Proses",
    key_field="code", name_field="name", id_prefix="pstg",
    fields=("code", "name", "kind", "applies_to_lines", "seq", "active", "notes",
            "needs_vendor", "process_type", "target_use",
            "changes_stage", "from_stage", "to_stage", "tariff_basis_default"),
    sort=(("seq", 1), ("code", 1)),
    hint="Langkah kerja yang dipantau papan PO & SPK makloon. `process_type` "
         "menyambung ke mesin tarif/estimasi; `changes_stage=false` = tidak "
         "mengubah kain (mis. pembuatan screen).")
```

### T.C — Jembatan master ↔ `domain_registry` (satu pembaca)
`backend/services/master_registry.py` (**baru**):
* `async stages(entity_id) -> list[dict]` — baca `process_stages` **efektif**
  (override PT menang atas global) dengan cache 60 detik; **fallback ke nilai benih**
  `domain_registry` bila koleksi kosong (instalasi baru tidak mati).
* `async process_types(entity_id)` — `PROCESS_TYPES` benih **∪** `process_type` yang
  dipakai baris master aktif.
* `invalidate()` dipanggil dari `routers/entity_masters.py` sesudah create/patch/
  override/revert (pola yang sama dengan `core_utils.invalidate_entity_code`).
* `routers/enums.py` menyajikan hasil pembaca ini → layar tetap satu sumber.

**Gate `INV-DOMAIN-06`** (`scripts/guardrails/verify_master_stages.py`, ber-`--self-test`):
1. nilai benih ⊆ master aktif (master boleh **menambah**, tidak boleh **menghilangkan**
   nilai yang masih dipakai dokumen — dibuktikan dengan **menghitung** dokumen pemakai);
2. setiap `process_stages.process_type` ∈ `PROCESS_TYPES` hidup;
3. setiap `from_stage`/`to_stage` ∈ `STAGES`;
4. setiap baris `changes_stage=true` **wajib** punya pasangan di `STAGE_TRANSITIONS`
   (kalau tidak, papan mengatakan sesuatu yang mesin makloon tolak);
5. setiap baris `needs_vendor=true` **wajib** punya minimal 1 `makloons` ber-
   `process_types` memuat `process_type` itu (kalau tidak, form SPK jadi jalan buntu).

### T.D — Perubahan mesin makloon (minimal, dengan uji regresi)
| Berkas | Perubahan |
|---|---|
| `domain_registry.py` | `PROCESS_TYPES += screen` (`fabric_type=None`, deskripsi: pembuatan kasa/screen — tidak mengubah kain) · `STAGE_TRANSITIONS += {pfp --screen--> pfp}` (+`finished --screen--> finished` bila pemilik memerlukan re-screen) |
| `services/makloon_order_service.py` | `steps[]` + `stage_code` (dari master) **di samping** `process_type` (dipertahankan agar tarif/estimasi lama identik). Bila tahap `changes_stage=false`: paksa `shrink=0`, `yield=1`, `expected_output = input_qty`, dan `estimate.explain[]` mencatat *"Tahap Screen tidak mengubah kain — hanya biaya jasa"*. Mitra **wajib** bila `needs_vendor` |
| `services/makloon_calc_service.py` | terima `changes_stage: bool`; `method="no_transform"` bila false |
| `routers/makloon_orders.py` | pemilih tahap dari master; `GET /api/process-stages/for-line/{line_code}` |
| `scripts/migrate_process_stages.py` | seed 10 baris master (peta T.A) + `steps[].stage_code = process_type` untuk 3 SPK lama |
| `indexes.py`, `entity_scope.py`, `ENTITY_REGISTRY.md`, `seed_realistic.py`, `scripts/gate.sh` | §3.1 titik 1–3, 10–12 + seed 1 SPK printing ber-Screen |
| `features/purchasing/MakloonFormModal.jsx`, `MakloonOrdersView.jsx`, `ProcessRecipesView.jsx` | tahap dari master (bukan enum hardcode) |
| `features/settings/masters/masterFieldsConfig.js` | kolom & field master Tahapan Proses |

**Uji regresi wajib:** 3 SPK makloon lama dibuka & dihitung ulang → `estimate`
(`expected_output_qty`, `explain[]`, biaya) **identik byte-per-byte** dengan sebelum
fase. Bandingkan salinan JSON sebelum/sesudah di POC.

### T.E — POC `backend/test_core_tahapan_poc.py`
T1 tahap baru (`Sanforize`) lewat API master → muncul di form SPK & papan PO tanpa ubah kode ·
T2 tahap `screen` dipakai di SPK: mitra **wajib**, biaya masuk, **kain tidak berubah**,
`explain[]` menyebut alasannya · T3 menonaktifkan tahap yang masih dipakai dokumen
**ditolak** (`INV-DOMAIN-06`) · T4 regresi: 3 SPK lama identik · T5 override per PT:
`process_stages` PT-B tidak mengubah urutan PT-A · T6 `needs_vendor` tanpa mitra
terdaftar → gate merah (bukti-merah).

### T.F — User story
1. *Sebagai admin*, saya menambah tahap **Sanforize** untuk lini woven; besok tim
   makloon sudah bisa memilihnya di SPK tanpa menunggu programmer.
2. *Sebagai staf printing*, saya membuat SPK dengan tahap **Screen** → sistem menuntut
   saya memilih mitra pembuat screen, mencatat biayanya, dan **tidak** mengubah tahap
   kain saya.
3. *Sebagai manajer*, saya membuka SPK makloon lama; angkanya sama seperti sebelum
   pembaruan (tidak ada estimasi yang berubah diam-diam).

### T.G — Selesai bila
POC 6/6 · `INV-DOMAIN-06` hijau + self-test merah · regresi 3 SPK identik ·
`audit_md_erp_readiness.py --fase T` SELESAI · `gate.sh --full` hijau.

---

## FASE U — DUA SATUAN DI SEMUA DOKUMEN (jumlah roll + yard/kg/panel)

**Tujuan pemilik:** *"catat roll dan yard/kg dan panel — jadi ada 2 satuan yang
ditulis... dan ini seharusnya sudah ada di semuanya, di WMS, di sales, di SO dll."*

### U.A — Bereskan D1 DULU: satu kosakata satuan (kalau tidak, fase ini kosmetik)
Ukuran: dokumen memakai `kg`, `meter`, `yard`; master `uoms` berisi `MTR, PCS, RLL, YRD`.
Konversi tetap benar (`uom_service.CANON` menormalkan huruf kecil), tetapi
**tak satu pun kode master cocok dengan nilai yang tersimpan di dokumen** — jadi
menambahkan baris `KG` saja **tidak mengubah apa pun di layar**.

Keputusan yang dieksekusi (paling kecil, tanpa migrasi data dokumen):
1. `uoms` mendapat kolom **`aliases: [str]`** dan baris:
   `MTR aliases=["meter","m","mtr"]` · `YRD aliases=["yard","yd","yrd"]` ·
   `RLL aliases=["roll","rll"]` (`base_type` dirapikan `volume→count`, idempotent) ·
   `PCS aliases=["pcs","pc","piece"]` · **`KG`** (`base_type="weight"`,
   `factor_to_base=1.0`, `aliases=["kg","kilogram"]`) · **`PANEL`**
   (`base_type="count"`, `precision=0`, `aliases=["panel","pnl"]`, `factor_to_base=1.0`).
2. `services/uom_service.py` — `load_fixed_factors()` & `_norm()` juga membaca
   `aliases` (satu tempat, tetap satu sumber). `WEIGHT_CANON` diperluas dari master
   `base_type="weight"` (bukan lagi hardcode).
3. `routers/uoms.py` + `features/admin/uom/UomConversionView.jsx` — `aliases` bisa
   dilihat/diubah admin, dan pemilih satuan di layar memakai `/api/uoms` (bukan daftar
   ketikan).
4. `bootstrap.py` — `seed_uoms`/`sync_uom_factors` & `seed_realistic.seed_uoms()`
   disamakan (**satu daftar**, di satu berkas) supaya jumlah baris tidak lagi bergantung
   urutan restart vs seed (K1).
5. **Gate `INV-UOM-02`**: setiap nilai `unit` yang tersimpan di 8 koleksi dokumen
   **wajib** cocok dengan `code` atau `aliases` sebuah `uoms` aktif. Bukti-merah:
   masukkan `unit="hasta"` → merah.

### U.B — Bentuk data: satu field baru saja (tanpa field kembar)
Setiap baris dokumen yang menyebut jumlah kain mendapat **satu** field baru:
`qty_rolls: int` (jumlah gulungan). Angka kedua **memakai field yang sudah ada**
(`quantity` + `unit`). Ukuran alternatif pada roll (roll ber-yard yang juga ditimbang)
memakai field yang **sudah ada tapi belum pernah diisi**:
`inventory_rolls.secondary_measures` → `{"kg": 12.5}`.

**15 tempat wajib** (ukuran hari ini: **0/15**):
`purchase_orders.items[]` · `purchase_requisitions.items[]` · `sales_orders.items[]` ·
`sales_returns.items[]` · `purchase_returns.items[]` · `warehouse_transfers.items[]` ·
`interco_transactions.items[]` · `interco_returns.items[]` · `internal_requests.items[]` ·
`rfqs.items[]` · `wms_tasks` (root) · `shipments` (root) · `inventory_movements` (root) ·
`makloon_orders.steps[]` (input & output) · `inspections.lines[]` (FASE I).

### U.C — Satu helper, bukan 15 salinan
* Backend `core_utils.qty_dual(rolls, measure, unit) -> str` → `"12 roll · 540,5 yard"`
  (angka gaya Indonesia — `scripts/audit_i18n_id.py` aturan [7] menjaga).
  Dipakai `services/pdf_resolvers.py` (PDF) & ekspor CSV backend.
* Frontend `components/QtyDual.jsx` — dipakai **semua** tabel & panel.
* **Gate `INV-QTY-01`**: (a) 15 koleksi punya `qty_rolls`; (b) dilarang merangkai
  teks jumlah+satuan manual di FE (regex `\{[^}]*qty[^}]*\}\s*\{?['"]?\s*(roll|yard|kg|meter)`)
  — wajib lewat `<QtyDual/>`; (c) dokumen lama tanpa `qty_rolls` ditampilkan **"—"**,
  bukan **"0 roll"** (uji render).

### U.D — Dari mana `qty_rolls` diisi (dihitung, bukan diketik — kecuali rencana)
| Titik | Sumber |
|---|---|
| Penerimaan `POST /api/inbound/tasks/{id}/scan-receive` | **hasil hitung roll yang benar-benar dibuat** → `wms_tasks.qty_rolls`, diakumulasi ke `purchase_orders.items[].received_rolls` (turunan) |
| SO / pengiriman | dari `allocations`/`sales_orders.items[].roll_lines[]` (mode roll sudah ada) |
| PO / PR / RFQ | **diketik** (rencana — saat memesan jumlah roll memang perkiraan) |
| Retur | dari roll yang dikembalikan (`roll_ids[]` sudah ada di `PurchaseReturnItem`) |
| Makloon | roll masuk/keluar per langkah |

### U.E — Berkas yang disentuh
`backend/core_utils.py` · `schemas.py`, `schemas_makloon.py`, `schemas_rnd.py`,
`schemas_hr*.py`(tidak) — **hanya** schema 15 koleksi di U.B ·
`services/roll_service.py` (`secondary_measures` saat penerimaan) ·
`services/inbound_receiving*`/`routers/inbound_receiving.py` (hitung roll) ·
`services/pdf_resolvers.py` · `routers/*_export`/`utils/csvExport.js` ·
`scripts/migrate_qty_rolls.py` (backfill dari roll nyata bila ada, **bukan** menebak) ·
`scripts/guardrails/verify_qty_dual.py` (`INV-QTY-01`), `verify_uom_vocab.py` (`INV-UOM-02`) ·
`backend/test_core_dua_satuan_poc.py` · FE: `components/QtyDual.jsx` + tabel di
Pesanan · PO · PR · RFQ · Transfer · Retur×2 · WMS · Pengiriman · Mutasi · Makloon ·
Antar-PT · Permintaan Internal.

### U.F — POC `backend/test_core_dua_satuan_poc.py`
U1 PO 12 roll × 45 yard → terima 12 roll → **PO, GRN, kartu stok, papan PO, PDF, CSV**
semuanya menyebut "12 roll · 540 yard" (satu sumber, enam tampilan) ·
U2 retur 2 roll → semua angka turun serentak (12→10 roll, 540→450 yard) ·
U3 lini knit memakai **kg**, printing memakai **panel** (satuan dari master satuan +
usulan lini) · U4 dokumen lama tanpa `qty_rolls` tampil **"—"** (bukan "0 roll") ·
U5 `INV-UOM-02`: `unit="hasta"` ditolak · U6 roll ber-yard yang ditimbang menyimpan
`secondary_measures={"kg":…}` dan kartu roll menampilkan keduanya.

### U.G — User story
1. *Sebagai admin sales*, saya membuat pesanan **12 roll (±540 yard)**; nomor yang saya
   ketik muncul sama di surat jalan, faktur, dan CSV — tanpa saya hitung ulang.
2. *Sebagai petugas gudang*, saya menerima 12 roll; papan PO **berubah sendiri** jadi
   "12 roll · 540 yard diterima" tanpa saya mengetik tanggal atau jumlah.
3. *Sebagai staf knit*, satuan saya **kg**; layar tidak pernah memaksa saya mengisi yard.
4. *Sebagai manajer*, membuka dokumen tahun lalu tetap wajar — kolom roll berisi
   **"—"**, bukan "0 roll" yang menyesatkan.

### U.H — Selesai bila
POC 6/6 · `INV-QTY-01` & `INV-UOM-02` hijau (self-test merah) · 15/15 koleksi ·
`audit_md_erp_readiness.py --fase U` SELESAI **dan DRIFT D1 hilang** · `gate.sh --full` hijau.

---

## FASE S — SAMPLING SUPPLIER: labdip · handfeel · proofing (BOLEH LEBIH DARI SATU)
*(menunggu keputusan pemilik #1, #3, #4 — §12)*

**Tujuan pemilik:** *"daripada terlalu kaku, bisa dipilihkan lebih dari satu saja"* —
satu permintaan sampling boleh menempuh proofing **dan** labdip **dan** handfeel; tiap
iterasi punya QC sample dan riwayat.

### S.A — Master baru
```python
"sample-types": MasterSpec(
    kind="sample-types", collection="sample_types", label="Jenis Sampling",
    key_field="code", name_field="name", id_prefix="stype",
    fields=("code", "name", "applies_to_lines", "seq", "active", "notes",
            "requires_design",        # proofing → wajib kode desain (perilaku lama)
            "measurement_fields"),    # field pengukuran yang muncul di form round
    sort=(("seq", 1), ("code", 1)))
```
Seed: `labdip` (`delta_e`, `colorfastness_wash`, `colorfastness_rub`) ·
**`handfeel`** (`gsm_actual`, `lebar`, `shrinkage_pct`, `handfeel_score` 1–5) ·
`proofing` (`requires_design=true`, `delta_e`, `repeat_cm`, `register`) ·
`bulk_sample` (**0 dokumen** — dinonaktifkan bila pemilik setuju, keputusan #4).

### S.B — Perubahan `md_samples` (migrasi menyentuh 17 berkas — K5)
* `sample_types: [str]` **menggantikan** `sample_type: str`.
  `scripts/migrate_sample_types.py`: `sample_types=[sample_type]` lalu **hapus field
  lama** (bukan dibiarkan) supaya tidak ada dua sumber.
  **Pembaca yang WAJIB ikut diubah (terukur):** backend `domain_registry.py`,
  `schemas_rnd.py`, `indexes.py`, `routers/rnd.py`, `services/rnd_sample_service.py`,
  `rnd_spec_service.py`, `rnd_kpi_service.py`, `rnd_sla_service.py`,
  `approval_matrix_service.py`; frontend `RndSamplesView.jsx`, `SampleFormModal.jsx`,
  `SampleDetailPanel.jsx`, `SampleRoundList.jsx`, `RndReportsView.jsx`,
  `RndSpecsView.jsx`, `SpecFormModal.jsx`, `SpecDetailPanel.jsx`,
  `designer/DesignerSlaPanel.jsx`.
  **Catatan koreksi (K6):** `approval_backlog_service` **tidak** perlu diubah — antrean
  `rnd_sample` memakai `status` + `decision.supplier_id`, bukan `sample_type`.
* `rounds[]` + `type_code` → satu permintaan bisa punya round labdip #1,#2 dan round
  handfeel #1 **paralel & terpisah**.
* `rounds[].qc: {by, at, verdict}` — `verdict` memakai `result` yang **sudah ada**
  (`acc|revisi|tolak`); yang ditambah hanya siapa & kapan QC fisik sample.
* `line_code` (FASE L) · `so_id` & `customer_id` **dimunculkan di form + layar**
  (hari ini `so_id` ada di skema tetapi **terisi 0 dari 28**).
* Penanda selesai: `finished_at`, `delivered_at`, `delivered_to` (`customer`/`sales`).
* Validasi pengukuran **lahir dari master** (`measurement_fields`), bukan dari `if`.

### S.C — Pustaka warna (K3 — sebagian besar sudah ada)
`color_library.system` sudah memuat `KN`, `TCX`, `TPX`. Yang dikerjakan hanya:
penyaring **sistem warna** di pemilih warna (`features/sales/ColorLibraryView.jsx` +
pemilih di `SampleFormModal.jsx`) dan menampilkan `md_samples.color_target`
(`color_id/code/name/hex`) di panel sample. **Tidak** ada perubahan skema.

### S.D — Endpoint
`POST /api/rnd/samples` (terima `sample_types[]`, `line_code`, `so_id`, `customer_id`) ·
`POST /api/rnd/samples/{id}/rounds` (terima `type_code`) ·
`POST /api/rnd/samples/{id}/rounds/{rid}/submit` (validasi dinamis dari master) ·
**baru** `POST /api/rnd/samples/{id}/finish` · `POST /api/rnd/samples/{id}/deliver`
(tujuan **wajib**). Antrean: bila `deliver` butuh keputusan orang → daftarkan di
`QUEUES`; bila tidak → tulis alasan di `DOOR_EXEMPT` (gate `INV-APPR-01` menuntut salah satu).

### S.E — POC `backend/test_core_sampling_poc.py`
S1 satu permintaan **dua jenis** (proofing + handfeel) → dua rangkaian round berjalan
sendiri-sendiri, riwayat tidak tercampur · S2 round handfeel menuntut `handfeel_score`,
labdip menuntut `delta_e` (dari master) · S3 menutup round tetap **wajib lampiran +
catatan** (perilaku lama tidak rusak) · S4 ACC → produk lahir **dan** kontrak supplier
terbit; keduanya ber-`refs` dua arah ke sample · S5 sample tertaut SO muncul di jejak
dokumen SO · S6 "jadi" & "dikirim" tercatat dan terlihat · S7 migrasi idempotent:
28 dokumen lama punya `sample_types` dan **nol** sisa `sample_type` (grep + DB) ·
S8 KPI & SLA R&D tetap menghasilkan angka yang sama untuk data lama (regresi K5) ·
S9 **nomor dokumen sample**: seluruh `md_samples.number` mengikuti pola `KSC/SMP-00001`
dan **unik** — termasuk sesudah `seed_realistic.py` dijalankan ulang (memperbaiki **D7**:
`scripts/seed_rnd_kpi_demo.py` dialihkan memakai `core_utils.next_doc_number()`; hari ini
20 dari 28 menyimpang & **5 nomor kembar**).

### S.F — User story
1. *Sebagai MD*, saya minta sampling **proofing + handfeel** sekaligus untuk satu kain;
   dua iterasi berjalan sendiri-sendiri dan riwayatnya tidak tercampur.
2. *Sebagai MD*, saya tautkan permintaan ini ke **SO-0007**; dari layar pesanan itu
   saya bisa melihat sample-nya.
3. *Sebagai QC sample*, saat menutup iterasi saya **wajib** melampirkan foto + catatan;
   sistem menolak kalau saya lewatkan.
4. *Sebagai MD*, ketika sample sudah jadi & dikirim ke pelanggan, saya tandai
   **"Sample Jadi"** & **"Kirim"** dan tanggalnya tercatat.

---

## FASE I — INSPEKSI & QC SEBAGAI DOKUMEN (SPK Inspeksi)
*(menunggu keputusan pemilik #5 — §12; bergantung pada U & S)*

**Tujuan pemilik:** lembar `Inspect PO`, `Inspect Retur (per PT)`, `Inspect retur &
replacement` — dengan **SPK**, petugas, milestone, hasil warna & handfeel, keputusan.

### I.A — Bereskan D2: koleksi hantu `qc_inspections`
`qc_inspections` terdaftar di `entity_scope.SCOPED_COLLECTIONS` sejak lama, **0 dokumen**,
**tak ada penulis**. Keputusan: koleksi baru bernama **`inspections`** (karena
cakupannya bukan hanya QC: penerimaan PO, output makloon, retur, replacement), dan
`qc_inspections` **dicabut** dari registry pada commit yang sama, dengan komentar
alasan. *Membiarkan nama mati di registry membuat gate "menjaga" sesuatu yang tidak ada
— dan agen berikutnya percaya koleksinya ada (persis yang terjadi pada v1).*

### I.B — Koleksi baru `inspections` (SATU koleksi, pembeda `kind`)
```
inspections {
  id, number,                    # "KSC/INS-00001"  (next_doc_number + entity_id)
  entity_id, line_code,
  kind,                          # po_receipt | makloon_output | return_customer
                                 # | return_supplier | replacement
  ref_doc_type, ref_doc_id, ref_doc_number,     # PO / MKO / retur (+ refs[] dua arah)
  supplier_id/name | customer_id/name,
  spk_date, assigned_to, assigned_name, bagian, # "Bagian Inspect"
  started_at, finished_at, status,               # draft|assigned|in_progress|done|closed
  baseline_sample_id, baseline_sample_number,    # acuan labdip/handfeel yang ACC
  baseline_contract_id,
  summary { rolls, measure, unit, points_total, grade_after_counts{A:..,B:..} },
  decision,                      # terima | terima_sebagian | turun_grade | tolak
  remark, history[], refs[]
}
inspections.lines[] {
  id, roll_id, roll_no, lot, dye_lot, product_id, article, sku,
  color_id, color_code, qty { rolls, measure, unit },        # FASE U
  points_snapshot, grade_before, grade_after,                 # RINGKASAN (§3.4)
  gsm_actual, width_actual,                                   # ringkasan
  color_result,      # sesuai | beda_shade | tolak   (+ delta_e opsional)
  handfeel_result,   # sesuai | beda | tolak         (+ handfeel_score 1..5)
  decision, remark, inspected_by, inspected_at
}
```
Index: `(entity_id,status)` · `(kind,ref_doc_id)` · `(line_code)` ·
`(assigned_to,status)` · `lines.roll_id`.

### I.C — Aturan anti-duplikat (rinci di §3.4 — **wajib dibaca**)
1. **Angka cacat & grade tetap dihitung `qc_inspection_service`** dan **grade tetap
   hanya berubah lewat `grade_service.set_roll_grade(source="qc_inspection")`**.
   `inspections.lines[]` = ringkasan + keputusan.
2. **Warna & handfeel disimpan di `inventory_rolls.inspection`** (memperluas
   `inspect_roll()`), karena pagar putaway membacanya di roll.
3. Dokumen inspeksi **melengkapi**, bukan menggantikan, tugas `qc_pending`: saat tugas
   masuk `qc_pending`, dokumen `po_receipt` **lahir otomatis** dan layar QC lama
   (`features/wms/QCInspection.jsx`) **diarahkan ke dokumen itu** — bukan jadi pintu kedua.
4. **Retur**: SSOT hasil per barang tetap `sales_returns.items[].inspection`
   (`return_service`). Dokumen `inspections(kind=return_customer)` adalah **SPK +
   milestone + ringkasan**, ditulis oleh service yang sama dalam satu transaksi logis.
5. Gate `INV-QC-02` dua arah + pengecualian tertulis (§3.4).

### I.D — Warna & handfeel ikut menentukan keputusan
Grade **tetap** dari poin cacat (mesin lama tak diubah). Yang baru: `decision` per baris
& dokumen mempertimbangkan `color_result` + `handfeel_result`. Kebijakan di Pusat
Pengaturan: `qc.color_mismatch_action`, `qc.handfeel_mismatch_action` ∈
`abaikan|peringatkan|tahan`. Bila `tahan` → roll **tidak boleh putaway** sebelum ada
keputusan manusia (pagar di `services/roll_service.py`/putaway + pesan menuntun).
Katalog konfigurasi: `backend/config_catalog_ops.py` (+ layar `SettingsHub` otomatis).

### I.E — Endpoint & izin
```
POST   /api/inspections                       (dari PO/MKO/retur; kind + ref)
GET    /api/inspections?kind=&status=&line=&assigned_to=&q=&page=&page_size=   (+CSV)
GET    /api/inspections/{id}
POST   /api/inspections/{id}/assign           {assigned_to, bagian}
POST   /api/inspections/{id}/start
POST   /api/inspections/{id}/lines/{lid}/inspect
         {defects[], gsm_actual, width_actual, color_result, handfeel_result,
          handfeel_score, remark}              → memanggil qc_inspection_service
POST   /api/inspections/{id}/finish           {decision, remark}  (alasan wajib bila tolak)
POST   /api/inspections/{id}/reopen           {reason}            (alasan wajib)
GET    /api/inspections/{id}/pdf              (SPK + hasil — lewat platform dokumen G-4)
```
Izin baru `permissions_config.DEFAULT_PERMISSIONS` → resource **`inspection`**:
`admin`/`manager`: `view·create·assign·inspect·decide·reopen` · `warehouse`:
`view·inspect` · `sales_admin`: `view`. **`/finish` mengandung keputusan → wajib
terdaftar di `QUEUES`** (`inspection_decision`, status `in_progress`/`done` menunggu
keputusan) atau `DOOR_EXEMPT` ber-alasan (`INV-APPR-01`).

### I.F — Retur ikut lengkap (milestone dari lembar pemilik)
`sales_returns` + `shipped_to_store_at` (SJ Kirim Toko) · `shipped_to_customer_at`
(Kirim ke Cust) · `goods_arrived_at` (Barang Sampai) · `inspection_id` ·
`inspect_done_at` · `complaint_code` + `complaint_note` (master **`complaint-reasons`**)
· `qty_rolls` (FASE U). Layar retur menampilkan **garis waktu** milestone
(pakai pola timeline yang sudah ada di `features/orders/OrderJourneyPanel.jsx`).

### I.G — Layar baru (mengikuti §4)
`frontend/src/features/inspections/InspectionsView.jsx` (daftar berhalaman + CSV +
chip lini + chip `kind`) · `InspectionDetailModal.jsx` (`DetailModal`) ·
`InspectionFormModal.jsx` (`FormModal`) · `InspectLineModal.jsx` (isi cacat/warna/handfeel).
Registrasi: `config/navStructure.js` (di hub **Gudang & Operasi**, peran
admin/manager/warehouse), `config/navMeta.js` (judul + penjelasan), `AppViewRouter.jsx`
(lazy), `config/hubTabs.js` bila masuk tab hub.

### I.H — POC `backend/test_core_inspeksi_poc.py`
I1 PO diterima → dokumen `po_receipt` **lahir otomatis** berisi baris per roll ·
I2 status berjalan draft→assigned→in_progress→done · I3 baris ber-cacat 24 poin → grade
**B**, `grade_history` roll bertambah **tepat satu** ber-`source="qc_inspection"`, dan
`points_snapshot` dokumen == `inventory_rolls.inspection.points` (anti-duplikat) ·
I4 `color_result="beda_shade"` + kebijakan `tahan` → roll **tidak bisa** putaway, pesan
menuntun · I5 acuan sample terlihat ("acuan Labdip KSC/SMP-00003 · Pantone 19-4052") ·
I6 retur pelanggan → `return_customer` + milestone + qty dual, **tanpa** menduplikasi
`sales_returns.items[].inspection` · I7 tutup dengan `tolak` **wajib alasan**, alasan
tersimpan di dokumen (bukan hanya audit) · I8 **nol residu** (`gate_residue`) ·
I9 mode "Semua Entitas": `POST /api/inspections` **409** menuntun; `POST .../{id}/finish`
tetap boleh · I10 IDOR: user PT-B tidak bisa membaca/menutup inspeksi PT-A (403/404).

### I.I — User story
1. *Sebagai kepala gudang*, begitu barang PO diterima, **SPK Inspeksi otomatis ada** —
   saya hanya menugaskan petugas, tidak membuat dokumen dari nol.
2. *Sebagai petugas inspect*, saya mengisi cacat per roll, plus **hasil warna** dan
   **handfeel** dibanding sample yang di-ACC; grade muncul otomatis dari poin.
3. *Sebagai petugas gudang*, ketika warna beda dari sample, sistem **menahan** roll dan
   memberi tahu siapa yang harus memutuskan — bukan diam lalu masuk gudang.
4. *Sebagai manajer*, saya menolak satu inspeksi dan **wajib** menulis alasan; alasan
   itu terlihat di dokumen, bukan hanya di jejak audit.
5. *Sebagai admin*, dari dokumen inspeksi saya bisa melompat ke PO, GRN, roll, dan
   sample acuannya (jejak dua arah).

---

## FASE P — PAPAN PO PER LINI (progres tahap seperti kertas kerja MD)

### P.0 — **PRASYARAT (D3): sambungkan PO → PR → SO dulu**
Terukur: `purchase_orders` **tidak** menyimpan `pr_id`/`source`/`refs→purchase_requisition`
(0/14); `purchase_requisitions.po_ids` terisi 1/5; `PR.source` demo hanya
`manual|reorder`. Tanpa langkah ini, kolom **Nama Sales** di papan akan selamanya kosong.
1. `services/purchase_requisition_service`/`routers/purchase_requisitions.py`: saat PR
   menjadi PO, tulis **dua arah** — `purchase_orders.pr_id`, `pr_number`,
   `source="pr"`, `source_so_ids[]` **dan** `doc_refs_service.link_child(("purchase_requisition",pr_id), ("purchase_order",po_id))`.
2. `doc_refs_service.DOC_TYPES["purchase_order"].source_fk += ["pr_id"]` supaya
   `INV-REF-01` menjaga tautannya (dan tidak menuduh PO mandiri sebagai yatim).
3. `scripts/migrate_po_pr_link.py` — backfill dari `purchase_requisitions.po_ids`
   (idempotent, laporan; hari ini 1 pasangan).
4. `seed_realistic.py` — minimal 1 rantai **SO → PR (`so_repeat`) → PO** supaya papan
   punya contoh nyata (`restock_service.PR_SOURCE` sudah menulis `source="so_repeat"` +
   `source_ref_id=so_id`; yang belum ada hanya datanya).

### P.A — Field baru `purchase_orders`
| Field | Isi | Sumber |
|---|---|---|
| `line_code`, `line_codes[]` | lini | FASE L |
| `pr_id`, `pr_number`, `source_so_ids[]` | asal dokumen | **P.0** |
| `sales_user_id`, `sales_name` | pembuat SO asal | dirunut `PO→PR(so_repeat)→SO.created_by`; **kosong** bila PO bukan dari SO (jangan dipaksa) |
| `stage_progress[]` | `[{stage_code,status,at,by,note}]` | dibentuk dari `product_lines.stage_sequence`; **diinput manusia** kecuali `inspect` |
| `eta_ready` | Estimasi Ready | **pakai `expected_delivery_date` yang sudah ada** (jangan bikin field kedua) |
| `first_receipt_at`, `last_receipt_at` | Tanggal Masuk | **dihitung** dari GRN (`wms_tasks`) |
| `received_rolls`, `received_measure` | Qty terima | **dihitung** dari roll yang lahir (FASE U) |

Tahap `inspect` **tidak** diklik manusia: statusnya diturunkan dari dokumen inspeksi
(`draft/assigned/in_progress` → proses; `done/closed` → selesai). Ini mencegah papan
mengaku "sudah diinspeksi" tanpa dokumen.

### P.B — Endpoint & layar
```
GET   /api/purchase-orders/board?line=&status=&q=&page=&page_size=   (+CSV)
PATCH /api/purchase-orders/{po_id}/stage {stage_code,status,note}    (izin purchase_order.update)
```
`frontend/src/features/purchasing/PoBoardView.jsx` — kolom **persis kertas kerja MD**:
Nama Sales · No PO · Nama Item · Qty (**dual**) · Warna · Tanggal Order · Estimasi
Ready · **tahap berjalan** (chip urut sesuai lini) · Tanggal Masuk · Qty Terima (dual) ·
Keterangan. Tab per lini **dari master** (bukan 4 blok statis). Registrasi nav seperti §I.G.

### P.C — POC `backend/test_core_po_board_poc.py`
P1 PO lini woven menampilkan **tepat** `yarn→tenun→celup→inspect`; printing
`proofing→pfp→screen→printing→inspect` (dari master) · P2 `sales_name` terisi dari SO
asal lewat PR (bukan diketik) **dan** kosong-wajar untuk PO pembelian rutin ·
P3 tahap `inspect` **tidak bisa** ditandai selesai manual · P4 tanggal masuk & qty
terima **berubah sendiri** setelah penerimaan · P5 papan menghormati pagar lini ·
P6 papan menghormati pagar entitas (PO PT-B tidak muncul di papan PT-A) ·
P7 `INV-REF-01` tetap hijau sesudah P.0.

### P.D — User story
1. *Sebagai MD*, saya buka **Papan PO → Printing** dan melihat tiap PO ada di tahap
   mana — persis seperti kertas kerja saya, tanpa mengetik ulang apa pun.
2. *Sebagai MD*, saya klik "celup selesai"; kolom tahap berpindah dan tercatat siapa
   & kapan.
3. *Sebagai MD*, kolom **Tanggal Masuk** dan **Qty Terima** terisi sendiri saat gudang
   menerima barang.
4. *Sebagai MD printing*, saya tidak melihat PO woven (bukan urusan saya).

---

## FASE D — PERMINTAAN DESAIN ("Design PO") + rapor desainer
*(tidak butuh keputusan pemilik — bisa dikerjakan paralel dengan S)*

### D.A — Koleksi baru `design_requests`
```
design_requests {
  id, number,                 # KSC/DSR-00001
  entity_id, line_code,
  source,                     # so | customer | internal
  so_id, so_number, customer_id, customer_name,
  requested_by, requested_at,
  assigned_to, assigned_name, division,       # designer
  due_date, brief, target_type,               # motif | pattern | artwork
  color_targets[] {color_id, code, name, hex},
  status,                     # draft|submitted|assigned|in_progress|delivered
                              # |approved|revision|cancelled
  gallery_ids[],              # hasil kerja → design_gallery (1..n versi)
  decided_by, decided_at, reject_reason,
  history[], refs[]
}
```
`design_gallery` + `request_id` (tautan balik) **dan** perbaikan **D4**: `code` wajib
saat artwork dibuat (`DSG-<slug>-NN`, `next_doc_number` gaya bersama sudah cukup karena
kode desain bukan nomor dokumen legal) + migrasi mengisi 2 artwork lama.

**Batas tegas antar dokumen** (supaya tidak jadi dokumen ke-3 yang tumpang tindih):
* `design_requests` = **pekerjaan siapa & kapan** (penugasan, tenggat, status)
* `design_gallery` = **artwork-nya** (berkas, versi, kode, ACC, nilai bintang)
* `md_specs` = **angka tekniknya** (gramasi, lebar, konstruksi) → melahirkan produk

### D.B — Endpoint
```
POST /api/design-requests · GET (filter lini/status/assigned_to/so, berhalaman +CSV) · GET /{id}
POST /api/design-requests/{id}/submit | /assign {assigned_to,due_date} | /deliver {gallery_id}
POST /api/design-requests/{id}/approve | /reject {reason}      (alasan WAJIB)
GET  /api/design/reports/by-designer?period=&line=
     → per desainer: diminta · dikerjakan · diserahkan · ACC · revisi ·
       rata-rata hari kerja · rata-rata bintang (dari design_gallery.ratings)
```
**Antrean wajib**: `approval_backlog_service.QUEUES += ("design_request", "Permintaan
desain menunggu keputusan", "design-requests", "design_requests", {"status":"delivered"})`
— tanpa ini `INV-APPR-01` **merah** (gate menemukan `/approve` & `/reject` lewat regex).

### D.C — Layar
`features/design/DesignRequestsView.jsx` (papan kanban per status, tenggat menyala bila
lewat — pakai gaya badge yang sudah ada, **bukan** warna baru) ·
`DesignRequestDetailModal.jsx` · `DesignerReportView.jsx` (rapor) · tombol
**"Tugaskan"** di `features/rnd/RndDesignsView.jsx`. Registrasi nav seperti §I.G
(hub **R&D / Desain**, peran admin/manager + peran desainer bila ada).

### D.D — POC `backend/test_core_design_request_poc.py`
penugasan → tenggat → serah → ACC/revisi ber-alasan → rapor **cocok** dengan hitung
ulang mandiri dari MongoDB → muncul di antrean keputusan & KPI beranda (`INV-HOME-01`
tetap hijau) → jejak `refs` dua arah ke SO & galeri → 409 di mode gabungan → IDOR 403.

### D.E — User story
1. *Sebagai MD*, saya buat **Permintaan Desain** dari SO pelanggan, menugaskan Rina,
   tenggat 3 hari.
2. *Sebagai Rina*, saya unggah artwork; permintaan berpindah ke **Diserahkan** dan
   masuk antrean keputusan atasan.
3. *Sebagai manajer*, saya **minta revisi** dengan alasan; Rina melihat alasannya di
   dokumen.
4. *Sebagai manajer*, saya buka **Rapor Desainer**: berapa yang diminta, selesai,
   revisi, rata-rata hari kerja, rata-rata bintang.

---

## FASE N — NOTIFIKASI SAMPAI KE ORANG YANG BENAR

Terukur hari ini (D5): **11** notifikasi ber-`recipient_role="all"` → `low_stock` **9**,
`order_approval` 1, `internal_request_decided` 1. Artinya finance & sales melihat 9
pesan stok yang bukan urusannya. `ar_due_soon`: job ada
(`alert_ops_service.job_ar_due_soon`, harian 07:55), penerima = **sales pemegang akun +
manager**; **finance tidak termasuk**; di data demo 0 dokumen. `special_orders`: 3
dokumen, **0** notifikasi.

1. `ar_due_soon` → tambah penerima **finance**.
2. `low_stock` → berhenti `recipient_role="all"`; kirim ke pemegang wewenang beli
   (`purchase_order.create`) + **divisi MD** bila diisi.
3. **PO custom** (`special_orders`) → notifikasi saat diajukan.
4. Notifikasi baru: sampling menunggu QC · inspeksi ditugaskan ke saya · permintaan
   desain ditugaskan/lewat tenggat · tahap PO macet > N hari (ambang dari config, bukan
   angka di kode).
5. **Alamat berbasis wewenang & divisi** — `services/notification_audience.py` (baru):
   `create_notification(..., recipient_permission=("purchase_order","create"), recipient_division="md")`
   → satu penyelesai penerima, dedupe per orang. `notification_service.create_notification`
   diperluas (parameter baru, **bawaan lama tetap jalan**).
6. **Gate `INV-NOTIF-02`**: dilarang `recipient_role="all"` untuk peristiwa yang punya
   pemilik jelas (daftar peristiwa + alasan pengecualian tertulis, ber-`--self-test`).

POC `backend/test_core_notifikasi_alamat_poc.py`: N1 `low_stock` hanya ke pemegang
wewenang beli (finance **0**) · N2 `ar_due_soon` masuk kotak finance · N3 PO custom
memberi tahu · N4 dedupe per orang (job dua kali → tetap satu) · N5 notifikasi
ber-entitas: PT-A tidak melihat notifikasi PT-B (`INV-ENTITY` lama tetap hijau).

**User story:** *Sebagai finance*, kotak notifikasi saya berisi jatuh tempo piutang —
bukan 9 pesan stok kain. *Sebagai pembelian*, stok menipis masuk ke saya. *Sebagai
manajer*, PO custom yang diajukan sales langsung terlihat.

---

## FASE M — MAKLOON (jalur "buat sendiri") ikut lengkap

* `makloon_orders`: `line_code` (FASE L), `steps[].stage_code` (FASE T), **dual qty**
  (FASE U) pada input & output tiap langkah.
* Output makloon diterima → **dokumen inspeksi `makloon_output`** (FASE I) → grading →
  gudang → lanjut pemenuhan SO/PO.
* Papan SPK makloon per lini memakai urutan tahap dari master (sama seperti papan PO).
* Biaya per tahap tercatat (`steps[].tariff_plan`/`actual`) dan muncul di rekap SPK.
* POC `backend/test_core_makloon_lini_poc.py`: rantai `benang→tenun→celup` menghasilkan
  roll ber-grade **lewat dokumen inspeksi**, biaya per tahap tercatat, dan tahap
  `screen` di jalur printing menambah biaya **tanpa** mengubah tahap kain.

**User story:** *Sebagai MD*, SPK makloon printing saya berisi tahap Screen dengan
mitra & biayanya; hasil akhirnya masuk gudang hanya setelah **diinspeksi**.

---

# 8. PETA RELASI DOKUMEN (WAJIB lewat `doc_refs_service`)

```
design_requests ──child──▶ design_gallery ──child──▶ md_specs ──child──▶ md_samples
      │                                                    │                  │
      └── parent: sales_orders (bila source=so)             │                  ├─child─▶ supplier_contracts
                                                           └─child─▶ products │
supplier_contracts ──child──▶ purchase_requisitions ──child──▶ purchase_orders   ← FASE P.0
purchase_orders ──child──▶ wms_tasks(GRN) ──child──▶ inventory_rolls/lots
purchase_orders ──child──▶ inspections(kind=po_receipt) ──ref──▶ md_samples (baseline)
makloon_orders  ──child──▶ inspections(kind=makloon_output)
sales_returns   ──child──▶ inspections(kind=return_customer)
sales_orders    ──child──▶ (alur pemenuhan yang sudah ada)
```
Kosakata `rel` **hanya** dari `REL_INVERSE` — hari ini **16 nilai (8 pasangan)**:
`parent↔child` · `amends↔amended_by` · `corrects↔corrected_by` · `reverses↔reversed_by` ·
`settles↔settled_by` · `fulfills↔fulfilled_by` · `issued↔issued_by` · `replaces↔replaced_by`.

**Untuk "acuan sample" (inspeksi → sample yang di-ACC) JANGAN memakai `applied_to`.**
Label itu ada di `REL_LABEL` tetapi **tidak** ada di `REL_INVERSE`, jadi
`link(..., rel="applied_to")` melempar `RefsError` (**D6**). Dua pilihan sah:
1. (disarankan) tambah **satu pasangan baru** ke `REL_INVERSE` **dan** `REL_LABEL`:
   `references: "referenced_by"` ("Mengacu pada" / "Diacu oleh"), lalu hapus/lengkapi
   `applied_to` supaya label tak lagi menjanjikan relasi yang tidak ada;
2. pakai `parent`/`child` — tetapi itu menyatakan *lahir dari*, padahal inspeksi tidak
   lahir dari sample; ini akan membuat penelusuran silsilah menyesatkan.

Tiap jenis dokumen baru **wajib** masuk `DOC_TYPES` (§3.2) supaya Pusat Dokumen bisa
menelusuri & mencetaknya (`INV-REF` menjaga kelengkapan tautan lewat
`scripts/audit_doc_refs.py --strict`).

---

# 9. RINGKASAN PERUBAHAN PER LAPISAN (dikoreksi v2)

**Koleksi BARU (6):** `product_lines` · `process_stages` · `sample_types` ·
`complaint_reasons` · `inspections` · `design_requests`.
**Koleksi DIPERLUAS (18):** products · users · sales_orders · purchase_orders ·
purchase_requisitions · purchase_returns · sales_returns · warehouse_transfers ·
interco_transactions · interco_returns · internal_requests · rfqs · wms_tasks ·
shipments · inventory_movements · inventory_rolls · makloon_orders · **uoms** (aliases).
**Koleksi DICABUT dari registry (1):** `qc_inspections` (hantu — §I.A).
**Servis BARU (5):** `line_scope.py` · `master_registry.py` · `inspection_service.py` ·
`design_request_service.py` · `notification_audience.py`.
**Servis DIUBAH (12):** rnd_sample_service · rnd_spec_service · rnd_kpi_service ·
rnd_sla_service · qc_inspection_service (diperluas: warna/handfeel) · makloon_order_service ·
makloon_calc_service · uom_service · roll_service (`secondary_measures` + pagar putaway) ·
return_service (milestone + SPK) · notification_service · alert_ops_service.
**Migrasi (7, semuanya idempotent + `--dry-run` + laporan):** `migrate_lini_produk.py` ·
`migrate_process_stages.py` · `migrate_qty_rolls.py` · `migrate_uom_aliases.py` ·
`migrate_sample_types.py` · `migrate_po_pr_link.py` · `migrate_design_codes.py`.
**Gate BARU (8):** `INV-LINE-01` · `INV-LINE-02` · `INV-DOMAIN-06` · `INV-QTY-01` ·
`INV-UOM-02` · `INV-QC-02` · `INV-NOTIF-02` (+ perluasan `INV-APPR-01` untuk 2 antrean
baru: `design_request`, `inspection_decision`).
**POC BARU (9):** lini · tahapan · dua satuan · sampling · inspeksi · papan PO ·
permintaan desain · notifikasi · makloon-lini.
**Alat ukur BARU (1):** `scripts/audit_md_erp_readiness.py` (sudah ada, dipakai tiap fase).

---

# 10. URUTAN & KETERGANTUNGAN

| Urut | Fase | Bergantung | Butuh keputusan pemilik? | Kenapa urutannya begini |
|---|---|---|---|---|
| 1 | **L** Lini | — | tidak | fondasi penyaring & papan; menundanya = mengerjakan ulang 12 layar |
| 2 | **T** Tahapan | L | tidak (kecuali #2 Screen untuk *biaya*) | urutan tahap milik lini; "Screen" lahir di sini |
| 3 | **U** Dua satuan | — (paralel T) | #1 Panel (hanya untuk faktor konversi) | menyentuh 15 koleksi; makin lama makin mahal |
| 4 | **D** Desain + **P.0** tautan PO→PR | L | tidak | dikerjakan saat menunggu jawaban #1–#5 |
| 5 | **S** Sampling | L, U | **#1 #3 #4** | handfeel + multi-jenis + tautan SO |
| 6 | **I** Inspeksi/QC | U, S | **#5** | butuh baris dual-qty & acuan sample ACC |
| 7 | **P** Papan PO | L, T, I, P.0 | tidak | tahap `inspect` diturunkan dari dokumen inspeksi |
| 8 | **N** Notifikasi | D, I, P | tidak | sekalian mencakup peristiwa baru |
| 9 | **M** Makloon | T, U, I | #2 (biaya screen) | menutup jalur "buat sendiri" |

Tiap fase ditutup: POC hijau → `gate.sh --full` hijau → `audit_md_erp_readiness.py
--fase X` bersih → agen uji UI (user story fase) → `plan.md` diperbarui → laporan
(§4.3 poin 3–5).

---

# 11. RISIKO YANG SUDAH TERLIHAT (dan penangkalnya)

| # | Risiko | Penangkal |
|---|---|---|
| 1 | `process_type` hardcode dipakai validasi sinkron | jembatan `master_registry` + `INV-DOMAIN-06` (benih ⊆ master; nilai yang dipakai dokumen tak boleh hilang) |
| 2 | Tahap **Screen** tidak mengubah kain, tetapi mesin makloon menghitung dari GSM | `changes_stage=false` → `shrink=0`, `yield=1`, `method="no_transform"` + **uji regresi 3 SPK identik** |
| 3 | Grade punya dua calon sumber setelah dokumen inspeksi lahir | §3.4 + `INV-QC-02` dua arah **dengan pengecualian tertulis** (grade saat roll lahir) |
| 4 | Pagar lini membuat layar kosong bagi akun lama | `allowed_line_codes` kosong = semua lini; dokumen tanpa `line_code` selalu terlihat; POC L3 & L4 |
| 5 | `sample_type → sample_types[]` menyentuh KPI & SLA (17 berkas) | migrasi **menghapus** field lama + POC S7/S8 (regresi KPI/SLA) + grep sisa pembaca di gate |
| 6 | **BARU** `line_code` vs `fabric_type` jadi dua sumber untuk hal yang sama | §L.A + `INV-LINE-02`; `measure_unit_default` hanya **usulan** |
| 7 | **BARU** Master satuan tidak dipakai sebagai kosakata dokumen (D1) | `aliases[]` + `INV-UOM-02`; satu daftar seed di satu berkas |
| 8 | **BARU** Papan PO menjanjikan "Nama Sales" padahal rantai PO→PR putus (D3) | **P.0 dikerjakan lebih dulu**; POC P2 menguji dua-duanya (terisi & kosong-wajar) |
| 9 | **BARU** Layar master jenis baru tampil tanpa kolom (§3.3) | `masterFieldsConfig.js` + `audit_md_erp_readiness` memeriksa kolom FE per jenis |
| 10 | **BARU** Dokumen inspeksi jadi pintu ke-3 di samping `qc_inspection_service` & `return_service` | §I.C butir 1–4 + `INV-QC-02` + layar QC lama **diarahkan**, bukan dibiarkan |
| 11 | Data demo "hijau tapi hampa" | seed wajib: 3 lini + `line_code` semua produk · 1 SPK printing ber-Screen · 1 sampling multi-jenis · 1 inspeksi PO + 1 inspeksi retur · 1 permintaan desain · 1 rantai SO→PR→PO · PO di tiap lini · `qty_rolls` terisi |
| 12 | Gate baru "memerah palsu" lalu diabaikan orang | tiap gate wajib `--self-test` yang membuktikan merah pada pelanggaran buatan **dan** hijau pada kode sah |
| 14 | **BARU** Data demo memuat **nomor dokumen kembar** (D7) sehingga gate keunikan nomor apa pun akan memerah, dan papan/laporan menampilkan dua baris bernomor sama | FASE S: seeder KPI R&D dialihkan ke `next_doc_number()`; `audit_md_erp_readiness.py` mengukur pola + keunikan; POC S7 menuntut keduanya |
| 13 | **BARU** Agen berikutnya memakai `rel="applied_to"` (ada di `REL_LABEL`, tidak ada di `REL_INVERSE`) lalu penautan dokumen gagal saat runtime (D6) | §8: tambahkan pasangan `references↔referenced_by` secara resmi; `audit_md_erp_readiness.py` sekarang mengukur `REL_LABEL ⊆ REL_INVERSE` |

---

# 12. LIMA KEPUTUSAN PEMILIK YANG DITUNGGU

> **SUDAH DIJAWAB PEMILIK 2026-08-19** (sesi penutupan FASE T). Ringkasnya:
> * **#1 PANEL → BERBEDA PER PESANAN.** Faktor panjang panel disimpan **di baris dokumen**
>   (bukan di `products.uom_conversions`), karena satu pesanan bisa memakai panjang panel
>   yang lain. → FASE U wajib menyediakan tempat faktor per baris (`unit_factor` +
>   `unit_factor_to` pada baris, dengan `uom_service` sebagai satu-satunya penghitung) dan
>   TIDAK boleh menjadikan master produk sumber kedua.
> * **#2 SCREEN → dicatat penuh** (mitra + jumlah screen + biaya). Sudah dieksekusi di FASE T:
>   `steps[].screen_count`/`repeat_count` + tarif basis `per_screen`/lumpsum,
>   `changes_stage=false` (kain tidak berubah), `design_gallery.screen_count` tetap RENCANA.
> * **#3 & #4 SAMPLING** → bawaan woven/knit = `labdip` + `handfeel`; printing = `proofing`
>   (boleh pilih lebih dari satu, disimpan di `product_lines.sample_types_default`);
>   `bulk_sample` **dinonaktifkan** (`active=false`, TIDAK dihapus dari enum).
> * **#5 SELISIH WARNA/HANDFEEL** → warna beda = barang **DITAHAN**; handfeel beda =
>   **PERINGATAN**; keduanya tetap konfigurasi (`qc.color_mismatch_action`,
>   `qc.handfeel_mismatch_action`); yang berwenang **melepas tahanan = MANAJER**.
>
> Teks asli usulan dipertahankan di bawah sebagai konteks alasannya.

Ditulis ulang dengan **bukti ukuran** supaya bisa dijawab cepat. Tidak menghalangi
FASE L · T · U · D · P.0.

**#1 PANEL — satuan tetap atau bebas per pesanan?**
Ukuran: `uoms` belum punya `PANEL`; tak ada dokumen memakai satuan panel.
Usulan: `PANEL` = satuan **count** (`factor_to_base=1`), dan bila 1 panel punya
panjang tetap per produk, isi lewat mekanisme yang **sudah ada**
`products.uom_conversions[{from_unit:"panel", to_unit:"yard", factor:X}]` (mesin
konversi VARIABLE per produk sudah jalan). → **Tidak perlu skema baru.**
Jawaban yang dibutuhkan: apakah panjang panel **berbeda per pesanan**? Bila ya, kami
simpan faktornya di baris dokumen (bukan di master produk).

**#2 SCREEN — catat jumlah & biaya, atau cukup tanda "sudah/belum"?**
Ukuran: `design_gallery.screen_count` **sudah ada** (dan `color_count`, `repeat_cm`).
Usulan: tahap `screen` di SPK makloon mencatat **mitra + jumlah screen + biaya**
(`steps[].screen_count`, tarif basis `per_screen`), sementara `design_gallery.screen_count`
tetap **rencana** dari desain. Kalau pemilik hanya butuh tanda "sudah/belum", tahap
`screen` cukup `status` — lebih murah, dan bisa ditambah nanti tanpa migrasi.

**#3 JENIS SAMPLING BAWAAN PER LINI**
Usulan: woven/knit → `labdip` + `handfeel`; printing → `proofing` (+`labdip` bila perlu).
Tetap **boleh pilih lebih dari satu**; bawaan disimpan di
`product_lines.sample_types_default` (jadi pemilik bisa mengubahnya sendiri nanti).

**#4 `bulk_sample` — dipertahankan atau dinonaktifkan?**
Ukuran: **0 dokumen** memakainya (28 sample: `labdip` & `proofing`).
Usulan: **dinonaktifkan** (`active=false` di master, bukan dihapus dari enum) supaya
dokumen lama—kalau kelak ada—tetap terbaca.

**#5 KALAU WARNA/HANDFEEL BEDA DARI SAMPLE YANG DI-ACC**
Usulan: **warna beda = barang DITAHAN** (tidak boleh masuk gudang sebelum ada keputusan
orang) · **handfeel beda = PERINGATAN saja**. Keduanya jadi konfigurasi
(`qc.color_mismatch_action`, `qc.handfeel_mismatch_action` ∈ `abaikan|peringatkan|tahan`)
sehingga bisa diubah tanpa programmer. Butuh konfirmasi: siapa yang berwenang
melepas tahanan — **manajer** (usulan) atau kepala gudang?

---

# 13. DEFINISI SELESAI & CARA LAPOR (per fase)

Satu fase dinyatakan selesai **hanya** bila ke-7 baris ini bisa ditunjukkan:
1. `python backend/test_core_<fase>_poc.py` → semua centang hijau.
2. Gate baru fase itu hijau **dan** `--self-test`-nya membuktikan bisa merah.
3. `bash scripts/gate.sh --full` hijau (termasuk 11 invarian UI/UX & nol residu).
4. `python scripts/audit_md_erp_readiness.py --fase <X>` → tidak ada BELUM/DRIFT
   milik fase itu.
5. `python scripts/validate_compliance.py` → **0 FAIL** (CHECK 8 registry termasuk).
6. Agen uji UI menjalankan **user story fase itu** + 3 layar lama (Pesanan · PO ·
   Daftar Roll) tanpa regresi; tangkapan layar sebelum/sesudah dilampirkan.
7. `plan.md` diperbarui (bagian `§STATUS MD-ERP`) berisi: yang diukur sebelum, yang
   diubah, angka sesudah, dan **sisa yang belum** — supaya sesi berikutnya tidak
   menebak.
