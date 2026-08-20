# SESSION HANDOFF — Kain Nusantara (WMS/ERP)

> Diperbarui: **2026-08-19** (sesi lanjutan repo `awawjahsada/kn` — **FASE T DITUTUP**:
> residu POC dihentikan · bug P1 pemilih pop-up ditemukan & ditutup · gate baru `INV-UI-09`).
> Sebelumnya: 2026-08-18 (repo `jskskajaj/kn` — FASE L LINI PRODUK ditutup).
> Bahasa: Indonesia. Roadmap fase: `plan.md` (§STATUS T = laporan sesi ini) ·
> Rencana MD ERP: `RENCANA_EKSEKUSI_MD_ERP.md` · Peta koleksi: `ENTITY_REGISTRY.md`.

---
## SESI 2026-08-19 (lanjutan · repo `awawjahsada/kn`) — **FASE T DITUTUP**

**Titik henti warisan tidak bersih — itu temuan pertama sesi ini.** FASE T tampak selesai
(POC 62/62 · `audit_md_erp_readiness --fase T` SEMUA SELESAI), tetapi `gate.sh --full`
**MERAH 3** dan ketiganya satu akar: POC FASE T meninggalkan residu stok
(`inventory_movements` +3 · `inventory_rolls` +2 · `inventory_lots` +1) → memicu WARN
`drift persediaan vs GL 1-1300 Δ750.000` → menjatuhkan `INV-GATE-01` **dan** POC `G-6b`.

### Keputusan pemilik sesi ini
**(1)** tutup T lalu kerjakan **U** · **(2)** panjang **PANEL BERBEDA PER PESANAN**
(faktor disimpan di baris dokumen) · **(3)** sampling bawaan woven/knit=`labdip`+`handfeel`,
printing=`proofing`, `bulk_sample` **dinonaktifkan** · **(4)** warna beda = barang
**DITAHAN**, handfeel beda = **peringatan**, pelepas tahanan = **MANAJER**.

### Yang dikerjakan
1. **Pemulihan lingkungan** (`.restore_env.sh` hijau; `memory/test_credentials.md` ditulis
   ulang — 9 akun demo, sandi `demo12345`). `/tmp` memang dibersihkan pod di tengah sesi.
2. **POC FASE T dibuat bebas residu**: `poc_stock_guard.snapshot_stock/restore_stock` +
   pemeriksaan T9 "4 koleksi stok sebelum == sesudah" → POC **63/63**, integritas **237/0/0**.
3. **Bug P1 `KN-UI-PICKER-REOPEN` ditemukan dengan menjalankan sendiri user story di
   peramban**: `ProductSelect`/`MakloonSelect`/`PantoneFinder` = pemicu+pop-up dalam satu
   komponen, dipakai di dalam `<Field>` = `<label>`; aktivasi label **diteruskan peramban**
   ke tombol pemicu → pop-up terbuka kembali (kotak cari kosong) dan menutupi tombol
   **Lanjut**. 3 komponen × **9 layar**. Obatnya struktural: `createPortal` ke `document.body`
   (nol perubahan gaya). `e.stopPropagation()` tidak menolong — React mendengar di AKAR.
4. **Gate baru `INV-UI-09`** `scripts/guardrails/verify_picker_portal.py` (+`--self-test`
   16 kasus dua arah). Dua iterasi penjaga sempat **menuduh palsu** (jendela 400 karakter;
   lalu kata `<label>` di komentarnya sendiri) → diperketat ke elemen yang PERSIS menyusul
   syarat + pembuang **komentar saja** (string dipertahankan, karena penanda pop-up hidup
   di dalam `className`).

### Bukti
`gate.sh --full` **90 gate HIJAU / 0 FAIL (291 s)** · POC FASE T **63/63** ·
`INV-UI-09` self-test **16/16** · `INV-DOMAIN-06` hijau · `verify_data_integrity` **237/0/0** ·
uji layar sendiri: SPK **MKO-00006** ber-tahap **Screen** dibuat ujung-ke-ujung
(25 yard → **25 yard**, "Tidak mengubah kain", ongkos Rp 750.000 dari kontrak
`KSC/SCT-00008`, tombol **Catat Jasa**), `MKO-00001` lama **109,44 identik**, regresi
Pesanan/PO/Status Stok bersih; dokumen uji dibersihkan.
**Dua temuan agen uji terbukti palsu**: literal `NaN` **0** di 3 layar (kata ber-"nan"
Bahasa Indonesia tertangkap pencarian case-insensitive) & "sesi cepat habis" (TTL 24 jam
dengan perpanjangan otomatis).

### Jebakan untuk sesi berikutnya (BACA)
* POC baru yang menyentuh roll/lot/mutasi **WAJIB** `poc_stock_guard` + periksa sendiri
  "sebelum == sesudah" (pola T9). "0 FAIL" bukan bukti nol residu.
* Komponen **pemicu + pop-up** baru WAJIB ber-portal (`INV-UI-09`) — kalau tidak, ia mati
  diam-diam begitu dipakai di dalam `<Field>`/`<label>`.
* **Reproduksi dulu** temuan agen uji UI sebelum menurutinya: 2 dari 4 temuan sesi ini palsu,
  dan 1 bug P1 nyata dilaporkannya sebagai "kendala otomasi".
* **FASE U**: keputusan pemilik **PANEL berbeda per pesanan** → faktor konversi panel di
  **baris dokumen**, bukan master produk. Bereskan **D1** (kosakata satuan `aliases`) dulu,
  kalau tidak fase ini kosmetik.

### Berikutnya
**FASE U — dua satuan (roll + yard/kg/panel)** di 15 koleksi: `aliases[]` di master `uoms`
(+ `KG`, `PANEL`) dan `INV-UOM-02`, lalu `qty_rolls` + helper `qty_dual`/`<QtyDual/>` dan
`INV-QTY-01`, POC `backend/test_core_dua_satuan_poc.py`. Sesudahnya: **D** (permintaan
desain) & **P-0** (tautan PO→PR), lalu **S → I → P → N → M**.

---
# SESSION HANDOFF — Kain Nusantara (WMS/ERP)

> Diperbarui: **2026-08-18** (sesi lanjutan repo `jskskajaj/kn` — **FASE L LINI PRODUK DITUTUP**). Sebelumnya: 2026-08-17 (repo `sjsjdyc/kn` — **FASE P5 + SISA P2 DITUTUP**: 61 dialog bawaan peramban dihapus, dua penjaga UI dibuat jujur, paginasi 4 modul terakhir).
> Bahasa: Indonesia. Roadmap fase: `plan.md`. Peta koleksi: `ENTITY_REGISTRY.md`.
> **Daftar isi alat: `scripts/INDEX.md`** · **Daftar isi 151 skrip uji: `tests/INDEX.md`**

---

# SESSION HANDOFF — Kain Nusantara (WMS/ERP)

> Diperbarui: **2026-08-17** (sesi lanjutan repo `sjsjdyc/kn` — **FASE P5 + SISA P2 DITUTUP**: 61 dialog bawaan peramban dihapus, dua penjaga UI dibuat jujur, paginasi 4 modul terakhir).
> Bahasa: Indonesia. Roadmap fase: `plan.md`. Peta koleksi: `ENTITY_REGISTRY.md`.
> **Daftar isi alat: `scripts/INDEX.md`** · **Daftar isi 151 skrip uji: `tests/INDEX.md`**

---
---
## SESI 2026-08-18 (lanjutan · repo `jskskajaj/kn`) — **FASE L LINI PRODUK DITUTUP** (master bertambah · pagar keras · snapshot)

Titik henti yang diwariskan: sesi sebelumnya berhenti **di tengah** FASE L — `entity_scope.py`
baru saja menerima `product_lines`, dan `indexes.py` sedang dibuka. Diukur ulang lebih dulu
dengan alatnya sendiri (`audit_md_erp_readiness.py --fase L`): **SELESAI 22 · BELUM 67 · DRIFT 7**.
Pilihan pemilik sesi ini: **(1b)** FASE L lalu FASE T · **(2a)** migrasi memakai aturan rencana
+ laporan koreksi · **(3)** akun demo berpagar lini dibuat.

### 0. Pemulihan lingkungan (wajib tiap clone — kontainer datang KOSONG)
`git clone → /tmp/kn_repo` → `rsync` ke `/app` (**JANGAN** timpa `backend/.env` & `frontend/.env`)
→ `bash /app/.restore_env.sh`. `memory/test_credentials.md` di-.gitignore → ditulis ulang
(kini memuat akun FASE L `dewi.printing@kainnusantara.id`).

### 1. Yang dibangun (dan kenapa bentuknya begitu)
* **Master `product_lines`** (berlapis global→PT) + `services/master_registry.py` sebagai
  **satu pembaca** untuk dua sumber: `domain_registry` = bentuk + **benih**, koleksi master =
  **nilai hidup**. `/api/enums` & `/api/enums/{name}` di-overlay nilai hidup, cache dibuang
  saat master ditulis (`routers/entity_masters.py`) — lini yang baru ditambah pemilik langsung
  muncul di 12 layar **tanpa restart** (POC L1).
* **`services/line_scope.py`** — pagar dipaksa di **query Mongo**, bukan di UI: `narrow()`
  (pagar akun + chip `?line=`, dan `?line=` TIDAK bisa jadi jalan belakang), `assert_can_order`,
  `assert_can_touch`, `stamp_items/stamp_doc/backfill`. Dua aturan anti-layar-kosong:
  **`allowed_line_codes` kosong = SEMUA lini** dan **dokumen tanpa lini selalu terlihat**.
* **Snapshot, bukan join**: `items[].line_code` distempel saat dokumen lahir; `line_codes[]`
  di kepala dokumen adalah **turunan**. Mengubah lini master produk tidak menggeser riwayat (POC L5).
* **Batas tegas dengan `fabric_type`** (INV-LINE-02): lini = pembagian kerja, `fabric_type` =
  fisika kain (SSOT rumus & satuan). Lini `printing` sengaja tidak mengikat jenis kain.
* **12 layar** dapat `components/LineFilter.jsx` (chip **dari master**, pilihan diingat per
  layar di `localStorage`, akun berpagar hanya melihat lininya). Definisi kolom master pindah ke
  `features/settings/masters/masterFieldsConfig.js` — jenis master baru kini = satu entri data.

### 2. Temuan penting sesi ini (gate yang benar-benar memerah)
`gate.sh --full` yang pertama **MERAH di gate baru sendiri**: `internal_requests KSC/PIN-00003`
punya baris produk berlini tetapi `line_code` kosong — jalur **Permintaan Internal** tidak
memanggil `stamp_doc()`. Itu persis kelas bug yang dirancang untuk ditangkap (dokumen lahir
tanpa lini → tak muncul di chip mana pun → pekerjaan tak terlihat). Diperbaiki di
`services/internal_request_service.py`, lalu gate ke-2 **HIJAU**.
Pelajaran yang diulang: **jangan biarkan tiap jalur menstempel sendiri** — 11 jalur tulis kini
lewat satu pintu `line_scope.stamp_doc()`, dan gate menuntut hasilnya.

### 3. Alat ukur dibuat jujur dulu, baru dipatuhi
`audit_md_erp_readiness.py` menuduh **6 berkas** "literal lini di frontend" — enam-enamnya SAH
(kata "woven"/"knit" di sana berarti `fabric_type`). Detektornya dipersempit ke *nilai lini yang
dilekatkan pada field lini*; versi tengahnya masih menuduh `AdminView` (satu baris state panjang
memuat `fabric_type:"woven"` dan `line_code:""` sekaligus). Penjaga yang menuduh palsu akan
diabaikan, lalu berhenti menjaga apa pun (pelajaran `ux_audit` FASE P5).

### 4. Bukti
`python scripts/audit_md_erp_readiness.py --fase L` → **SEMUA SELESAI** (dari 22→32 SELESAI global) ·
`bash scripts/gate.sh --full` → **HIJAU 85 gate / 0 FAIL (275 s)** ·
POC `backend/test_core_lini_poc.py` **40/40** (dua kali berturut, **nol residu**) ·
`scripts/guardrails/verify_line_scope.py --self-test` **15/15 dua arah** ·
migrasi `scripts/migrate_lini_produk.py` idempotent (`--dry-run` = hasil sungguhan) + laporan
`docs/LAPORAN_MIGRASI_LINI_PRODUK.md` · agen uji UI **backend 17/17 · POC 40/40 · UI 95%**
(satu temuan "chip roll tidak ketemu" TERBUKTI salah alamat — chip memang hanya di tab **Roll**;
diverifikasi sendiri lewat peramban) · **berkas gaya NOL perubahan** (`App.css`, `index.css`,
`tailwind.config.js`, `navStructure.js`, `navMeta.js` identik dengan repo asal).

### 5. Jebakan untuk sesi berikutnya (BACA)
* **Kosong ≠ tidak boleh.** `allowed_line_codes: []` berarti SEMUA lini, dan dokumen tanpa
  `line_code` terlihat semua orang. Jangan "merapikan" ini menjadi wajib-isi tanpa migrasi —
  layar akan mendadak kosong bagi staf berpagar.
* **Endpoint daftar baru wajib memanggil `line_scope.narrow`**, endpoint tulis baru wajib
  `stamp_doc`. Gate `INV-LINE-01` memerah lewat daftar berkas di
  `scripts/guardrails/verify_line_scope.MUST_USE_LINE_SCOPE` — daftarkan berkas barunya.
* **`measure_unit_default` bukan sumber satuan.** Ia hanya usulan; satuan kendali tetap
  `fabric_type.control_uom` + `products.base_unit`. FASE U jangan menjadikannya sumber ketiga.
* Data demo: lini diisi **seed** (`seed_product_lines` + sapuan penutup `_finalize_line_codes`),
  bukan migrasi. Basis data lama tetap dilayani `scripts/migrate_lini_produk.py`.

### 6. Berikutnya
**FASE T — master TAHAPAN PROSES (termasuk `screen`)** + jembatan ke `domain_registry`
(rencana §7 FASE T), lalu **FASE U** (dua satuan).

## SESI 2026-08-17 (repo `sjsjdyc/kn`, lanjutan) — **61 DIALOG BAWAAN PERAMBAN DIHAPUS · DUA PENJAGA UI DIBUAT JUJUR · PAGINASI 4 MODUL TERAKHIR (FASE P5 + SISA P2)**

Permintaan pemilik: *"lanjutkan development dari repo ini, sebelumnya development terhenti
di sini"*. Titik henti P4 **diverifikasi sendiri lebih dulu**: `gate.sh --full` dijalankan
ulang dari nol → **71 HIJAU / 0 FAIL (272s)**, jadi titik hentinya memang bersih.
Pilihan pemilik: **(1c)** P5 + sisa P2 sekaligus · **(2c)** galat/gagal = bilah MENEMPEL,
berhasil = toast · **(3b)** aksi berdampak uang/stok WAJIB beralasan.

### 0. Pemulihan lingkungan (wajib tiap clone — kontainer datang KOSONG/template)
`git clone → /tmp/knrepo` → `rsync` ke `/app` (**JANGAN** timpa `backend/.env` &
`frontend/.env`) → `bash /app/.restore_env.sh` (pip · yarn · restart backend ·
`seed_realistic.py` · `scripts/rebuild_frontend.sh`). **Preview dilayani dari
`frontend/build/` yang di-gitignore → KOSONG sampai di-build.** Catatan: `/tmp` bisa
dibersihkan pod di tengah sesi — salinan repo untuk bukti-merah taruh di `/app/.logs/`.

### 1. Dua angka warisan diukur ulang — dua-duanya salah
- Dokumen menyebut `alert` **40×** & `confirm` **~21×**. Hitungan dari kode:
  **`alert` 36 · `confirm` 21 · `prompt` 4 = 61 dialog di 21 berkas.** `prompt()` tak
  pernah masuk daftar padahal `AccountList` memakainya untuk **kata sandi baru sebagai
  teks terbuka** (terlihat siapa pun di dekat layar, tak bisa divalidasi).
- Gate P4 melaporkan create-inline **0**. Nyatanya **3** (Buat PO · Ajukan Harga Khusus ·
  Tambah Stok Awal). Penjaganya buta pada form yang **isiannya dipindah ke berkas ANAK**:
  ia mencari `<input>` di berkas induk, sementara `<POCreateForm/>` menyimpan semuanya di
  berkasnya sendiri, dan namanya berakhiran "Form" (bukan "Modal") sehingga juga tidak
  dianggap pop-up. **Pelajaran (kelas bug yang sama dengan INV-IC-04):** penjaga yang
  hanya memeriksa permukaan tidak bisa memerah untuk hal yang disembunyikan satu lapis.

### 2. Standar pengganti — dibuat LEBIH MURAH daripada jalan pintasnya
`services/confirmService.js` + satu `<ConfirmHost/>` di root (pola identik `use-toast`
yang sudah dipakai repo, jadi tidak menambah cara baru): `askConfirm()` Ya/Batal ·
`askReason()` **menuntut alasan** · `askText({inputType:"password"})` menyamarkan karakter.
Perubahan di tiap pemanggil **hanya satu baris** — itu poin desainnya: standar hanya
dipatuhi kalau lebih murah daripada `window.confirm`. Nilai kembali dibuat **beda tipe**
(`boolean` vs `string|null`) supaya "batal" & "lanjut tanpa alasan" mustahil tertukar.
`utils/feedback.notifySuccess()` untuk kabar berhasil; **`notifyFailure()` sengaja TIDAK
disediakan** — menyediakan jalan mudah melaporkan gagal lewat toast yang hilang sendiri
berarti melestarikan kebiasaan yang sedang dihapus.
`ErrorNotice` kini **menggeser dirinya ke dalam pandangan** (`block:"nearest"`): bilah
menempel di atas halaman panjang tadinya "ada tapi tak terlihat" = sama saja senyap.
Galat form/aksi tampil **di dalam pop-upnya sendiri** (pop-up eskalasi gudang, modal
detail transfer, form Buat Transfer/Stok Awal) — kalau ditaruh di bilah halaman, ia
tertutup pop-up itu sendiri.

### 3. Alasan yang ditanyakan BENAR-BENAR disimpan
5 endpoint diberi `reason` (opsional di API supaya pemanggil lama tak berubah arti, **wajib
di layar**): batal transfer (`cancelled_reason`) · void kwitansi AR (`voided_reason`) ·
hapus entri eliminasi konsolidasi · hapus tarif insentif · posting true-up persediaan.
**Temuan ikutan:** void kwitansi AR — yang MEMBALIK uang masuk pada order + kas + deposit —
sebelumnya **tidak menulis satu baris pun ke `audit_logs`**, baik di router maupun service.

### 4. `ux_audit` dibuat JUJUR dulu, baru dipatuhi (17 dari 22 "ERROR" itu tuduhan palsu)
Sebelum fase ini audit itu **tidak punya `--self-test`** dan **tidak terdaftar di gate.sh**,
jadi angkanya tak pernah dibuktikan bisa memerah. Setelah diperiksa satu per satu:
- komponen **PENAMPIL** (data dari props, `axios` = 0) dituduh "tanpa loading" — padahal
  yang tahu "sedang memuat" memang induknya, dan induknya sudah punya skeleton;
- penjaga yang benar-benar dipakai repo tak dikenali: `length > 0`, `hasLines`, dan pesan
  kosong yang berada **di komponen anak** (`FinanceTowerParts` → `<EmptyState>`);
- kata **"posting"/"loading" di kalimat JSX** dihitung sebagai bukti adanya indikator →
  `PeriodUnlockCard` lolos padahal `return null` selama memuat (teks JSX bukan literal
  string, jadi pembersih string tidak menolong — obatnya: penanda wajib DIPAKAI dalam
  ekspresi);
- nama state **berimbuhan** (`loadingDaily`, `setLoadingDaily`) tak dikenali;
- W1 kehilangan kata **"kolom"** dari standarnya → 28 berkas ditandai hanya karena
  menyebut nominal **di dalam kalimat** ("Store Credit: Rp 250.000").
Detektor dibuat sadar-rujukan + `--self-test` **16 kasus dua arah**; pembersih
komentar/string dipindah ke `guardrails/_common.py` (satu implementasi — dua penjaga
berbeda sudah pernah tertipu teks yang bukan kode). Lalu **5 gap NYATA** diperbaiki:
Dasbor Keuangan & Perubahan Ekuitas (tabel **dan** grafik) yang merender **halaman kosong
tanpa satu kalimat** saat tak ada data · matriks izin kosong · kartu Buka Periode yang
melompat masuk tanpa kerangka. Hasil **0 ERROR**, dan `ux_audit --strict` kini **gate**.

### 5. Gate baru `INV-UI-06` — anti kambuh
`scripts/guardrails/verify_blocking_dialogs.py`: `alert(`/`confirm(`/`prompt(` bawaan
peramban = MERAH + `<ConfirmHost/>` wajib ter-mount di root (tanpa itu penggantinya gagal
**SENYAP** dan semua tombol hapus/batalkan tampak mati). `--self-test` **17 kasus**,
termasuk anti-tuduh-palsu untuk dua kasus NYATA di repo ini: label
`"1 pesan per alert (real-time)"` (kata di dalam string) & `async function confirm()`
(fungsi kebetulan senama). **Bukti-merah** dijalankan pada kode SEBELUM P5 (klon bersih di
`/app/.logs/_redproof`): **61 pelanggaran di 21 berkas + `<ConfirmHost/>` hilang, exit 1**.

### 6. Sisa P2 — 4 modul terakhir dipaginasi
Retur Jual · Retur Beli · Pesanan · Jurnal GL. Dua endpoint agregat BARU
(`/sales-returns/status-counts`, `/purchase-returns/status-counts`) + `backorder_count` di
`/sales-orders/stats/summary`: **lencana & kartu ringkasan tidak boleh dihitung dari isi
halaman** — kalau begitu, angkanya diam-diam menyusut mengikuti halaman ("kartu bilang 12,
daftar berisi 3"). Tab **Dasbor & Analitik** Pesanan SENGAJA tetap memakai daftar penuh:
analitik yang hanya melihat satu halaman bercerita salah. Aksi pada detail pesanan
dibungkus agar **halaman yang sedang dibuka** ikut dimuat ulang (induk hanya memperbarui
daftar dasbornya sendiri). Jurnal GL dulu dipotong keras **500 baris tanpa halaman
berikutnya** → entri ke-501 tak terjangkau, padahal koleksi ini tumbuh paling cepat.
Semua **OPT-IN**: tanpa `?page/?page_size`, bentuk respons tidak berubah.

### 7. Bukti penutup
`gate.sh --full` **75 gate HIJAU / 0 FAIL** (273s, dijalankan lagi SESUDAH seed ulang) ·
`INV-UI-06` self-test 17/17 · `ux_audit` self-test 16/16 & **0 ERROR** · `INV-UI-05`
self-test 12/12 & **inline 0 (kali ini terukur benar)** · agen uji **BE 11/11 · FE 0 bug
UI**, syarat kritis "tidak ada dialog peramban" **LULUS** · verifikasi tangan di peramban:
dialog alasan batal transfer muncul **di atas** modal detail, tombol konfirmasi **mati
sampai alasan diisi**, Esc & Batal menutup; Jurnal GL `Hal 1/6 → 2/6` mengirim
`?page=2&page_size=20`; pencarian Pesanan "Butik" → `1–3 dari 3`.

### 8. Jebakan untuk sesi berikutnya (BACA)
- **Penjaga yang menuduh palsu lebih berbahaya daripada tidak ada penjaga.** Dua penjaga
  di sesi ini (INV-UI-05 & ux_audit) sama-sama gagal karena **menilai KODE tetapi membaca
  TEKS**. Kalau menulis penjaga statik: buang komentar & string dulu
  (`_common.strip_comments_and_strings`), sadari **teks JSX bukan literal string**, dan
  wajibkan penanda **dipakai dalam ekspresi** — bukan sekadar disebut.
- **Sebelum menuruti tuduhan penjaga, periksa satu per satu.** 17 dari 22 "ERROR" di sini
  akan berubah menjadi belasan prop `loading` palsu kalau dituruti: kode bertambah, layar
  tidak berubah sedikit pun.
- **Lencana/kartu ringkasan wajib dari agregat SERVER** begitu daftarnya dipaginasi.
  Ini kelas bug tersendiri: angkanya tidak error, hanya diam-diam mengecil.
- **Widget mengapung "Bantuan & Panduan"** di kanan-bawah **menelan klik** tombol di dasar
  halaman panjang. Terbukti: klik `force=True` pada tombol paginasi → halaman TIDAK pindah
  & **nol request**; `dispatch_event("click")` → pindah benar. Jangan simpulkan "paginasi
  rusak" sebelum mencoba cara kedua. (Perbaikan tata letaknya belum dikerjakan.)
- **`?view=transfers` BUKAN deep-link yang sah.** Transfer gudang ada di dalam layar
  Operasi WMS: `?view=operations` → tab `wms-tab-transfer`. Agen uji sempat menyimpulkan
  "menu tidak ditemukan" karena ini.
- **Agen uji MENGUBAH data demo** (audit_logs +9: ESCALATE/RESOLVE/APPROVE/COMPLETE).
  Sudah dipulihkan: `login_attempts` dibersihkan → `seed_realistic.py` →
  `seed_e9_chain_demo.py` → `scripts/gate_residue.py --save`, lalu `--check` **nol residu**.
  Selalu periksa residu sesudah memanggil agen uji; jangan percaya laporan "100%" untuk
  urusan kebersihan data.

### 9. Berikutnya (menunggu keputusan pemilik) — rinci di `plan.md` §STATUS P5
9 WARN `ux_audit` (`<select>` bawaan di 8 berkas) · utang alur **F-6.7** · kirim dokumen
via email/SMTP (butuh kredensial) · ambang persetujuan antar-PT (US22) diuji lewat layar ·
3 layar "Segera Hadir" (BOM Printing · BI Sales · BI Stok) · tata letak widget mengapung.

---
## SESI 2026-08-17 (repo `ndizucufjs/KN`) — **GATE MERAH DITUTUP · MESIN PERSETUJUAN GENERIK DIPENSIUNKAN · 14 ANTREAN NYATA MASUK HITUNGAN (FASE F-6)**

Permintaan pemilik: *"lanjutkan development dari repo ini, sebelumnya development terhenti
di sini"* — titik henti persisnya **terbukti benar & direproduksi lebih dulu**: `gate.sh --full`
**64 HIJAU / 1 MERAH** pada `INV-GATE-01` anti-residu (`audit_logs` **99 → 102, +3 dok**).
Pilihan pemilik: **(1)** tutup gate merah dulu → **(2)** fase §F-5 no.1 (mesin persetujuan generik).

### 0. Pemulihan lingkungan (wajib tiap clone — kontainer datang KOSONG/template)
`git clone → /tmp/KN` → `rsync` ke `/app` (**JANGAN** timpa `backend/.env` & `frontend/.env`;
`.git`/`.emergent` kontainer dipertahankan) → `bash /app/.restore_env.sh` (pip minus
`emergentintegrations`/`litellm` · `yarn install` · restart backend · `seed_realistic.py` ·
`scripts/rebuild_frontend.sh` — **`frontend/build/` di-gitignore, preview KOSONG sampai di-build**).

### 1. Gate merah — ditutup di AKARNYA (bukan dijinakkan)
POC sesi lalu (`backend/test_core_approval_reminder_poc.py`) mengambil **snapshot DB SETELAH tiga
`POST /auth/login`**, jadi 3 baris `audit_logs` (+3 `sessions`) dari login berada **di luar jendela
snapshot** → `restore()` mustahil menghapusnya. Dibuktikan terisolasi: POC dijalankan sendirian →
tepat **+3**. Obat: snapshot & sidik jari **SEBELUM** login + `sessions` masuk daftar tersentuh.
**Bonus temuan:** pemeriksaan "G7 nol residu" di POC itu hanya `ok(True, …)` — **hijau abadi yang
tak mengukur apa pun**, dan justru di bawahnya residu itu bersembunyi. Kini G7 **mengukur** +
**bukti-merah sentinel** (satu dokumen sengaja disangkutkan → pengukur wajib memerah). POC **26/26**.

### 2. Keputusan §F-5 no.1 → **CABUT** (dipilih dari bukti kode, bukan selera)
`create_approval_request()` **nol pemanggil** (koleksi `approval_requests` 0 dok) padahal
`POST /approval-requests/{id}/approve|reject` ADA & izin `approval.approve` dipegang admin+manajer →
wewenang di kertas · **nol** pemakai di `frontend/src` · menghidupkannya menjadikannya **jalur
penulisan status KEDUA** (arsitektur repo: keputusan di endpoint dokumennya sendiri) · endpointnya
**tak berscope PT** (pada `get`, `resolve_scope_ids()` dihitung lalu tak dipakai) · penilai ambang
**kembar** dengan `config_service.evaluate_approval()` yang HIDUP. Router+fungsi dihapus; izin
dicabut di `permissions_config.py` **dan** `bootstrap.sync_permission_revocations()` — wajib karena
matriks izin **tersimpan di MongoDB** (mengubah kode saja tidak mencabut apa pun; kelas E8.2).

### 3. Gantinya — **14 antrean keputusan NYATA** (KPI 17 → 22, satu sumber)
Transfer gudang · kontrabon (verifikasi/persetujuan/sengketa) · permintaan internal · retur antar-PT ·
tagihan supplier · biaya masuk · uang muka + pertanggungjawaban · klaim makloon · buka periode ·
cuti · lembur → `services/approval_backlog_service.QUEUES` (kini **26 baris**). Angka diverifikasi
**tiga sumber**: KPI beranda == `/approvals/backlog` == hitung-ulang mandiri dari MongoDB.

### 4. Penjaga baru **INV-APPR-01** (`scripts/guardrails/verify_approval_queues.py`)
6 invarian + `--self-test` **15/15**: **A** 50 pintu keputusan ditemukan otomatis dari kode & wajib
terklasifikasi (pembebasan **wajib beralasan**; klasifikasi basi = merah) · **B** sapuan DATA (status
menunggu) · **C** **anti dobel-hitung** (`customer_prices` sudah terhitung lewat `price_approvals`) ·
**D** tanpa layar hantu · **E** nama koleksi benar · **F** anti-regresi pensiun mesin generik.
Ikut diperbaiki: invarian "koleksi harus ADA di DB" (di `verify_home_kpi.py` &
`test_core_role_access_poc.py`) → **"ada di DB ATAU disebut literal di kode"**, karena fitur yang
belum dipakai di data demo (uang muka/biaya masuk/buka periode) membuat penjaga **menuduh palsu**.

### 5. Layar & 403 senyap
`ApprovalInbox.jsx`: panel **"Menunggu di layar lain — paling lama dulu"** (nomor dokumen + umur
tunggu + "Buka layarnya", nonaktif bila di luar wewenang) — sebelumnya *"11 ditangani di layar lain"*
jujur tetapi tak bisa dikerjakan. `hooks/useAppActions.js`: `user.view` dulu menarik `/permissions` &
`/audit-logs` → **4×403 senyap** di konsol manajer; kini tiap panggilan dipagari izinnya sendiri
(terukur **4 → 0**).

### 6. Bukti penutup
`gate.sh --full` **69 gate HIJAU / 0 FAIL** (`memory/GATE_RECEIPT.md`, 265s) · POC F-6 **43/43**
(termasuk bukti-merah: suntik 1 transfer menunggu → KPI wajib bergerak 22→23, dihapus → kembali) ·
POC pengingat **26/26** · POC F-2 **43/43** · agen uji **BE 47/47 · FE 21/22** (1 timeout skrip,
diverifikasi tangan sebagai admin & manajer: total 22, 18 chip, 10 baris antrean-lain, deep-link
mendarat di dokumen yang benar) · konsol browser **0 error/403**.

### 7. Jebakan lingkungan (JANGAN terulang)
- **Dua `gate.sh` paralel = gate merah PALSU massal** ("koleksi KOSONG"): yang satu men-seed &
  mengosongkan koleksi sementara yang lain memverifikasi. Pakai pembungkus ber-`flock`:
  `bash /app/.logs/run_gate.sh --full /app/.logs/gate_run.log`.
- `POST /auth/login` **ber-rate-limit** → uji beruntun memicu **429**, lalu `seed_realistic.py`
  melewati `seed_contra_bons`/`seed_interco` hanya dengan `[warn]` senyap. Obat:
  `db.login_attempts.delete_many({})` → seed ulang → cek `grep -i warn`.

### 8. Berikutnya (menunggu keputusan pemilik) — rinci di `plan.md` §STATUS F-6.7

### 9. LANJUTAN SESI YANG SAMA — **FASE P4: tombol "Buat" jadi pop-up konsisten** (SELESAI)
Permintaan pemilik setelah laporan status: *"P4 — form Buat jadi modal, lanjutkan ini"*.
- Angka "±15 layar inline" **diukur ulang dari kode** → nyatanya **10 layar (12 tombol)**; 36 sudah
  pop-up; 7 sengaja tetap halaman (alur kompleks). Alat ukurnya: `scripts/audit_create_modal.py`.
- Standar baru **`components/FormModal.jsx`** (kepala/kaki menempel · Esc · scroll latar dikunci ·
  fokus isian pertama · galat di dalam modal · backdrop `overlayDismiss()` → INV-UI-01 tetap hijau ·
  tak membungkus ulang komponen ber-`<form>` sendiri).
- **10 layar dikonversi**: Supplier · Daftar Harga Supplier · Kebijakan Retur · Unit Organisasi ·
  Kas · Retur Beli · **Retur Jual** (dulu menukar seluruh halaman) · Aturan Persetujuan ·
  Transfer Gudang · Master Data (AdminView). Hasil: **inline 12 → 0 · tombol mati 0**.
- **Gate baru `INV-UI-05`** + `--self-test` 7 kasus: inline baru / pindah halaman tanpa keputusan
  tercatat / tombol mati = MERAH; pengecualian wajib beralasan. Penjaganya sempat **menuduh palsu**
  (7 layar benar terbaca "inline"; `setForm({…})` dianggap membuka pintu) → diperbaiki dulu.
- Bukti: `gate.sh --full` **71 gate HIJAU / 0 FAIL** · agen uji frontend **10/10 user story, nol
  isu** (termasuk: tabel tetap terlihat di belakang modal · galat validasi di dalam modal ·
  Esc/backdrop/X menutup · **memilih dropdown TIDAK menutup modal**) · konsol **0 error** ·
  `ux_audit` tidak bertambah buruk (22 ERROR/17 berkas = backlog P5).

### 10. Sisa yang BELUM (untuk sesi berikutnya)
1. **P5 UI/UX**: `ux_audit` 22 ERROR/37 WARN (loading/empty/chart) + `window.alert/confirm` **21×**.
2. **Sisa P2 paginasi**: Retur Jual · Retur Beli · Pesanan (OrdersView) · Jurnal GL.
3. **Utang alur F-6.7**: payroll & desain diputuskan dari `draft` (butuh langkah "Ajukan") ·
   keputusan selisih pembayaran tanpa status dokumen · verifikasi administratif SO tanpa antrean.
4. **Kirim dokumen via email/SMTP** (butuh kredensial pemilik).
5. **Ambang persetujuan antar-PT (US22)** diuji ujung-ke-ujung lewat layar.
6. 3 layar masih "Segera Hadir": BOM Printing (`cs-bom`) · BI Sales · BI Stok.

---


## SESI 2026-08-15 (repo `skskududu/KN`) — **2 GATE MERAH DITUTUP · AUDIT PERAN 6 PERAN · KPI BERANDA BERHENTI BERBOHONG**

Permintaan pemilik: *"lanjutkan development dari repo ini, sebelumnya development terhenti
di sini"* — titik henti persisnya **terbukti benar**: sesi lalu baru saja mendaftarkan
`scripts/audit_sales_roles_ux.py` sebagai gate, lalu `gate.sh --full` **MEMERAH di 2 gate**
(`guard:auth_coverage` INV-AUTH-01 · `INV-GATE-01` anti-residu). Direproduksi sendiri lebih
dulu: **59 PASS / 2 FAIL dari 61 gate**.

### 0. Pemulihan lingkungan (wajib tiap clone — kontainer datang KOSONG/template)
`git clone → /tmp/kn_repo` → `rsync` ke `/app` (**JANGAN** timpa `backend/.env` &
`frontend/.env`; `.git`/`.emergent` kontainer dipertahankan) → `bash /app/.restore_env.sh`
(pip minus `emergentintegrations`/`litellm` · `yarn install` · restart backend ·
`seed_realistic.py` · `scripts/rebuild_frontend.sh` — **`frontend/build/` di-gitignore,
preview KOSONG sampai di-build**). `memory/test_credentials.md` ikut repo & sudah benar.

### 1. Keputusan pemilik sesi ini
1. Urutan: pulihkan lingkungan → tutup 2 gate merah → selesaikan audit **sales vs Admin
   Sales** → gate penuh HIJAU + agen uji → dokumen. **Disetujui.**
2. Bila ada **layar mati** (menu terlihat, datanya 403): **BERI IZIN BACA** ke peran itu
   supaya menunya berguna (bukan sembunyikan menunya).
3. Utang migrasi Kas Besar Grup: *"anda atur saja, ini masih demo tidak masalah"*.
4. Fase baru: agen memilih **berdasar bukti kode**, lalu melaporkannya.

### 2. Dua gate merah — ditutup di akarnya (bukan dijinakkan)
- **`INV-AUTH-01` menuduh PALSU** `GET /sales-return-policies/{policy_id}`: endpoint itu
  memakai `require_any_permission` (enforcer "salah satu dari", E-9) tetapi daftar enforcer
  keras hanya mengenal `require_permission`/`require_role`, dan `"require_permission("`
  **bukan** substring `"require_any_permission("`. Dua arah bahayanya: gate merah pada kode
  benar (penjaganya akan dimatikan orang), **dan** dulu endpoint yang hanya memakai enforcer
  itu lolos karena alasan salah (kebetulan memanggil `entity_ctx`). Obat: masuk daftar KERAS
  + pencocokan **batas kata** + **`--self-test` 8 kasus** yang didaftarkan sebagai gate.
- **Residu `audit_logs` +2/gate**: audit baru mengetuk HTTP nyata (login 6 peran). Obat:
  `run_with_restore(main)` — terukur `audit_logs` 101 → 101.

### 3. Audit peran: dari "2 peran & peringatan kuning" → "6 peran & MERAH"
`panel mati` (sebagian endpoint layar 403) tadinya hanya kuning; di bawahnya hidup **11 kasus
nyata**. Yang paling mahal: peran `finance` membuka **Kasus Keuangan** (menu resminya) dan
SELURUH referensinya kosong + layar merah, hanya karena satu `GET /suppliers` 403 ikut di
dalam `Promise.all` yang sama. Obat sesuai keputusan pemilik: **3 izin BACA** baru
(`finance+supplier.view`, `warehouse+supplier.view`, `manager+user.view`), `/ar/aging`
digerbang **izin** (`accounting.view` ATAU `penalty.issue`) bukan pangkat peran, 4 panggilan
yang memang bukan wilayahnya **dipagari di kode**, dan tombol "Buat Nota Denda" kini lahir
dari izin `penalty.issue` (INV-ROLE-01) sehingga Finance akhirnya bisa memakainya.
Pembebasan audit sekarang berkunci **`(layar, path)`** + **izin yatim** berbasis bukti
(58 tuduhan palsu → 1 sinyal jujur).

### 4. Fase baru F-3 (dipilih dari bukti): **KPI beranda berhenti berbohong**
`KN-F3-KPI-LIES` — KPI "Persetujuan Menunggu" **selalu 0** karena menghitung koleksi
`approval_requests` yang **tak pernah diisi siapa pun** (`create_approval_request()` nol
pemanggil), sementara daftar rincian di layar yang sama berbunyi **6** dan kenyataan **17**.
Obat: satu sumber `services/approval_backlog_service.py` (13 antrean nyata) dipakai KPI
beranda + rincian + endpoint baru `GET /api/approvals/backlog`; Control Tower dapat panel
antrean yang bisa diklik; Pusat Persetujuan dapat ringkasan + catatan jujur *"X di antaranya
ditangani di layar lain"*. Gate baru **`INV-HOME-01`** (6 invarian + bukti-merah) menjaganya.
Saat kedua angka dipasang di satu layar, langsung ketangkap satu lagi: baris `amendment`
menyebut koleksi `amendments` padahal namanya **`doc_amendments`** → satu antrean hilang
tanpa pesan (kini dijaga invarian E).

### 5. Utang migrasi (i) ditutup dengan bukti — dan alatnya ternyata cacat
Data demo **nol** baris kas tingkat grup, jadi menjalankan `migrate_e7_group_cash.py` di data
bersih hanya mencetak "tidak ada yang perlu dimigrasikan" (kebetulan, bukan bukti). POC
`backend/test_core_group_cash_migration_poc.py` **38/38** membuat ULANG keadaan warisan
(1 rekening grup + 13 transaksi · 4 lapis bukti + 2 baris tak terbuktikan) dan menemukan:
baris yang pemiliknya diputuskan ORANG lewat kasus `salah_entitas` tetap menunjuk rekening
**GRUP** → rekening itu tak pernah bisa dinonaktifkan. Ditambah **sapuan kedua** (pindah
`account_id` ke cermin badan usaha).

### 6. Bukti penutup
`gate.sh --full` **65 gate HIJAU** (`memory/GATE_RECEIPT.md`) · POC F-2 **43/43** (dengan
bukti-merah) · POC F-1b **38/38** · `audit_sales_roles_ux` **nol layar & panel mati (6 peran)** ·
integritas **236/0/0** · agen uji frontend **8/8 user story** · verifikasi tangan di layar
nyata. Angka antrean tersaring badan usaha: KSC **15** · Kanda **2** · gabungan **17**.

### 7. Berikutnya (usulan, menunggu pemilih pemilik) — rinci di `plan.md` §STATUS F/F-5
1. Mesin persetujuan generik: hidupkan pintunya **atau** cabut endpoint+izinnya.
2. Kirim dokumen via **email/SMTP** (satu-satunya backlog EPIC 7 yang grounded; butuh kredensial).
3. Uji **ambang persetujuan antar-PT (US22)** dari ujung ke ujung lewat layar.

---


## SESI 2026-08-15 (repo `wauaualaja/kn`) — **FASE E-6 DITUTUP** (E-8 & E-9 ikut resmi tutup)

Permintaan pemilik: *"lanjutkan development dari repo ini, sebelumnya development terhenti
di …"* — titik henti persisnya: sesi lalu berhenti **tepat setelah memanggil agen uji
putaran-3** untuk menutup E-6; hasilnya (31/31 LULUS) kembali tetapi **tidak pernah dicatat
maupun ditutup**. `.emergent/emergent_todos.json` menunjukkan E-6.5 masih `in_progress`
dan E-6.7 (dokumen) masih `pending`.

### 0. Pemulihan lingkungan (wajib tiap clone — kontainer datang KOSONG/template)
`git clone → /tmp/kn_probe` → `rsync` ke `/app` (**JANGAN** timpa `backend/.env` &
`frontend/.env`; `.git`/`.emergent` kontainer dipertahankan) → `pip install -r requirements.txt`
(minus `emergentintegrations`/`litellm` yang sudah ada di base image) → `yarn install` →
`supervisorctl restart backend` → `python seed_realistic.py` →
`bash scripts/rebuild_frontend.sh` (**`frontend/build/` di-gitignore, jadi preview KOSONG
sampai di-build**; build 43s). `memory/test_credentials.md` ikut repo dan sudah benar.
Satu ganjalan: `reportlab` belum terpasang saat backend pertama kali di-restart →
`ModuleNotFoundError`, hilang sendiri setelah `pip install` selesai.

### 1. Verifikasi titik henti — SEMUA KLAIM TERBUKTI BENAR (diverifikasi ulang, bukan dibaca)
| Klaim sesi lalu | Hasil verifikasi empiris sesi ini |
|---|---|
| `gate.sh --full` 57 gate HIJAU | **BENAR** — HIJAU 224s, `memory/GATE_RECEIPT.md` 57 baris PASS, 0 non-PASS |
| POC E-8 meja kerja 97/97 | **BENAR** — `POC FASE E-8 G2/G3 … 97/97 PASS` |
| POC E-9 rantai retur 44/44 | **BENAR** — `HASIL: 44 PASS · 0 FAIL dari 44` |
| `verify_data_integrity` 236 PASS/0 FAIL | **BENAR** — 236/0/0 |
| Laporan agen uji putaran-3 "31/31 (100%)" | **BENAR** — diverifikasi TANGAN, lihat §2 |

### 2. Verifikasi TANGAN atas laporan agen uji (aturan repo: laporan "100%" wajib dicek ulang)
Handoff sesi E-7 mencatat pernah ada laporan agen uji **palsu** (iterasi 218 "0%"), jadi
laporan "100%" kali ini **tidak** diterima apa adanya. Diuji sendiri lewat Playwright di
preview nyata:
- **PERBAIKAN-1 `KN-E6-DASH-SALES-LEAK` (US11)** — `sales@` (Ayu): **8** kartu pesanan
  `[KSC/SO-00010, SO-0007, SO-0006, SO-0009, SO-0005, SO-0004, SO-0003, SO-0001]`,
  `SO-0008` **TIDAK ADA** di layar, KPI `orders-stat-total` = **8** (dulu 9).
  `sales2@` (Bima): **tepat 1** kartu = `SO-0008`, KPI = 1, nol pesanan Ayu.
  `admin@` mode "Semua Entitas": tetap **11** pesanan (termasuk `KANDA/SO-00001`, `SO-0002`).
- **PERBAIKAN-2 `KN-E6-DERIVED-FROM-LIST` (US23/US24)** — `KSC/SO-00010` →
  `[data-testid='order-interco-supply-panel']` **ADA** dan berbunyi
  *"DIPENUHI DARI BADAN USAHA LAIN · 37 yard Kain Demo Rantai Retur (E-9) · Barang sudah masuk ·
  diambil dari CV Kanda Suka lewat KSC/IC-00006 · janji 2026-08-15 · tugas gudang
  KANDA/TRF-00002"*. Tampil untuk `admin@` **dan** `sales@` (pemilik pesanan), dengan
  **nol id teknis `ent_*`** di layar.
- **Lencana peran** `entity-role-tag` berbunyi tepat `Admin` / `Sales` (tanpa titik).
- **Nol error konsol aplikasi** (yang muncul hanya telemetri platform `cdn-cgi/rum` &
  `posthog` — di luar aplikasi).

### 3. Akar kedua bug (untuk pelajaran, bukan sekadar catatan)
1. **`KN-E6-DASH-SALES-LEAK`** — layar Pesanan **tidak** memakai `GET /sales-orders`
   (yang sudah ber-`sales_ownership`) melainkan `orders[]` dari `GET /dashboard`, dan dasbor
   itu hanya menyaring **per badan usaha**. Jadi pagar kepemilikan sales yang sudah benar di
   satu endpoint **dilangkahi** oleh endpoint lain yang memberi data ke layar yang sama.
   Ditutup di `routers/dashboard.py` (`sales_ownership.apply_scope()` untuk `orders` +
   `active_orders`) + cek baru di POC E-8.
2. **`KN-E6-DERIVED-FROM-LIST`** — `interco_supply` adalah field **turunan** yang hanya
   dihitung `GET /sales-orders/{id}`. Panel detail membacanya dari objek hasil **DAFTAR**,
   jadi nilainya selalu `undefined` → blok JSX **di-skip tanpa error apa pun**. Kelas bug ini
   lolos semua gate API & semua POC backend karena endpoint detailnya memang benar.
   Ditutup dengan komponen `OrderIntercoSupplyPanel.jsx` (mengambil datanya sendiri) +
   **gate statik baru `INV-UI-04` (`guard:derived_fields`)** yang menolak field turunan
   dibaca dari respons daftar.

### 4. Bukti penutup
`gate.sh --full` **HIJAU 57/57** · `verify_data_integrity` **236/0/0** ·
POC E-8 G1 hijau · POC E-8 G2/G3 **97/97** · POC E-9 **44/44** ·
agen uji putaran-1/2/3 (**31/31**) · verifikasi tangan agen utama atas kedua perbaikan ·
`plan.md` §8 + §STATUS E-6 diperbarui.

### 5. Berikutnya (keputusan pemilik sesi ini — KETIGANYA dipilih)
1. **Utang migrasi (ii)** — akun ber-peran `manager` yang sebenarnya Admin Sales/Finance.
2. **Utang migrasi (i)** — pemetaan 13 transaksi "Kas Besar Grup" ke entitas pemiliknya
   (butuh konfirmasi per baris → agen menyiapkan daftarnya untuk pemilik).
3. **Item yang diparkir** — analisis + perbaikan akses & UI/UX **sales vs admin-sales**.
4. **Fase baru dari `MASTER_ROADMAP.md`** (dipilih berdasar bukti kode, bukan dokumen —
   banyak epik di dokumen itu sudah dikerjakan sejak ditulis).

---

## SESI 2026-08-11 (penutup · repo `ganakauaanabasa/KN`) — **FASE E-7 ANTAR-ENTITAS DITUTUP**

Permintaan pemilik: *"lanjutkan development dari repo ini, development sebelumnya terhenti
di sini"* — titik henti persisnya: sesi lalu berhenti **tepat saat memanggil agen uji**
untuk 9 user story frontend E-7; hasilnya tidak pernah kembali.

### 0. Pemulihan lingkungan (wajib tiap clone — kontainer datang KOSONG/template)
`git clone` → rsync ke `/app` (JANGAN timpa `backend/.env` & `frontend/.env`) →
`bash /app/.restore_env.sh` (pip + yarn + restart + `seed_realistic.py` + build FE).
`memory/test_credentials.md` di-gitignore → **ditulis ulang** (7 akun, semua `demo12345`).

### 1. Verifikasi titik henti — hasilnya BENAR, tetapi belum lengkap
| Klaim sesi lalu | Hasil verifikasi empiris |
|---|---|
| Backend E7a–E7g selesai | **BENAR** — POC `test_core_e7_interco_poc.py` **53/53** |
| Gate hijau | **BENAR** — `gate.sh --ci` 49 gate HIJAU |
| Frontend E-7 sudah ada | **BENAR** — semua komponen & test-id ada (`pin-tab-submitted` lahir dinamis dari `pin-tab-${key}`) |
| Frontend sudah diverifikasi | **BELUM** — inilah yang dikerjakan sesi ini |

### 2. Dua cacat NYATA yang hanya bisa ditemukan lewat LAYAR (bukan lewat API)
1. **`fixed-assets` mengaku memiliki aset yang sudah pindah PT.** `summary()` memakai aturan
   "semua yang bukan `disposed` = aktif", jadi setelah dua aset KSC pindah ke Kanda layar
   penjual tetap memamerkan **Nilai Perolehan Rp 420.000.000** dan **2 aktif** — padahal
   nilai buku barisnya sudah 0 dan haknya sudah berpindah. Pil status pun jatuh ke cadangan
   dan merender **hijau "Aktif"**. → `summary()` mengeluarkan `transferred` dari perhitungan
   dan **melaporkannya terpisah** (`transferred`, `transferred_book_value`,
   `transferred_unsettled`); pil status baru **"Pindah PT"** (biru); KPI baru
   **"Pindah ke PT Lain"** lengkap dengan "belum dibayar". 3 pemeriksaan baru di POC
   (53 → **56/56**).
2. **Layar `internal-requests` tanpa judul.** Tidak ada entri `PAGE_META` → kepala halaman
   berbunyi "BERANDA · WORKSPACE" + judul cadangan "Kain Nusantara" di layar yang justru
   mengurus barang & uang antar badan usaha. → entri ditambah **dan** dipagari gate baru
   `check_nav_map.py` **CHECK 5**: setiap layar yang bisa dituju WAJIB punya judul & kicker
   (94 layar diperiksa; kelas bug ini tak terlihat gate struktur menu karena menunya benar).

### 3. Verifikasi 10 user story frontend — LULUS SEMUA
`testing_agent_v3` iterasi **219**: 8/10 LULUS (nol error konsol, nol layar blank).
Dua sisa (**US6 pinjaman antar-PT**, **US8 pindah aset**) hanya diuji separuh oleh agen →
**diverifikasi tangan oleh agen utama lewat Playwright**:
- `KSC/ICL-00003 ⇄ KANDA/ICL-00003` dibuat draf → **Cairkan** → `Sudah dicairkan` →
  angsuran Rp 5.000.000 → **Lunas**.
- `KSC/FA-00001` → `KANDA/FA-00003` (nilai buku Rp 169.062.500, masa manfaat sisa ikut) →
  **Catat pembayaran** → uang berpindah `KANDA/CASH-00015 · KSC/CASH-00034`.

### 4. JEBAKAN PALING MAHAL SESI INI — laporan agen uji yang PALSU (BACA)
Iterasi **218** melaporkan *"navigation broken, session resets, 0% dari 9 user story"* dan
menyarankan "manual testing". **Semua itu salah.** Dua sebabnya:
1. Agen mengeklik `text=GUDANG`; wrapper `nav-group-*` adalah `div` **bukan** elemen klik —
   yang bisa diklik `nav-group-toggle-*`.
2. Skripnya memakai sintaks Playwright **sync** padahal lingkungan **async**, sehingga
   `locator.count()` mengembalikan *coroutine* dan disimpulkan "layar kosong". (Saya
   sendiri tertipu sekali oleh hal yang sama — screenshot pertama saya seolah menunjukkan
   "login ulang", padahal `fill()` tanpa `await` memang tidak pernah jalan.)

**RESEP NAVIGASI YANG BENAR (pakai ini, jangan klik sidebar):** aplikasi punya deep-link
`?view=<viewId>[&tab=<tab>][&entity=<entityId>]` (`hooks/useViewDeepLink.js`). Buka URL →
login → aplikasi **langsung mendarat** di layar itu dengan badan usaha terpilih; sesi
bertahan antar `page.goto` (token di localStorage). Terbukti untuk 7 layar. Iterasi 219
memakai resep ini dan langsung hijau. **Pelajaran: laporan "100%" maupun "0%" dari agen uji
harus dicek ulang bila bertabrakan dengan bukti POC.**

### 5. Bukti penutup
POC E-7 **56/56** · `gate.sh --ci` **HIJAU** (gate baru CHECK 5 PAGE_META) ·
`check_nav_map.py` PASS 94 layar · agen uji iterasi 219 · verifikasi tangan 2 alur uang ·
`seed_realistic.py` dijalankan ulang → data demo bersih (aset tetap 3 baris, pemasok
Entitas grup 2 baris, nol kas tingkat grup).

### 6. Berikutnya (keputusan pemilik sesi ini)
Urutan: **FASE E-8** → **FASE E-6** → **FASE E-9**. Untuk E-8 pemilik memilih
**akun demo BARU** `salesadmin@kainnusantara.id` & `finance@kainnusantara.id`
(akun `manager@` TETAP manajer). Cara kerja: bergelombang seperti E-7, POC + agen uji
di tiap gelombang.

---


## SESI 2026-08-11 (repo `kikijujahasa/kn`) — **FASE E-5 DITUTUP** · mulai **FASE E-7**

Permintaan pemilik: *"lanjutkan development dari repo ini … saya ingin anda verifikasi titik
berhenti jika sudah benar lanjutkan"* (titik berhenti sesi lalu: klaim E5.1/E5.2 sudah
selesai di E-0, E5.3 sedang diverifikasi).

### Verifikasi titik berhenti — hasilnya TIDAK seluruhnya benar
Klaim sesi lalu diuji ulang **empiris** (bukan baca dokumen):

| Klaim | Hasil | Bukti |
|---|---|---|
| E5.1 papan stok selesai di E-0 | **BENAR** | sales KSC: `by_entity`=[`ent_ksc`] · `total_available` = stok sendiri · `global_total` = stok grup · `other_entities_available` · `detail_scope="own_entity"` · minta PT lain → **403** |
| E5.2 pegging selesai di E-0 | **BENAR** | `resolve_list_scope("inventory_rolls", …)` → `owner_entity_id` |
| E5.3 mutasi pindah-kepemilikan | **SETENGAH** | jejak memang terlihat, tetapi label lawan **tidak ada**: API mengirim id teknis mentah `ent_kanda` dan layar Mutasi tidak menampilkan lawan sama sekali |

**Plus satu kebocoran BARU yang tidak ada di rencana mana pun:**
`GET /api/history/{product_id}` (Kartu Riwayat Produk) **tanpa scope entitas** →
sales PT Kain Suka Cita mengklik satu produk dan ikut membaca **2 mutasi milik CV Kanda
Suka** lengkap nomor lot `KANDA/LOT-2608-0001` + nama gudang. Sekelas L21.
*Kenapa lolos gate:* gate isolasi menyapu endpoint **daftar**; endpoint "riwayat satu
induk" berparameter `product_id` (bukan `entity_id`) sehingga tidak pernah dicurigai.

### Yang dikerjakan
- **E5.3** `services/movement_label_service.attach_counterparty_labels()` — badan usaha
  lawan pada mutasi hanya **NAMA SINGKAT** (`counterparty_entity_name`,
  `counterparty_direction`, `counterparty_label`). Untuk peran non-lintas id teknis
  `from_owner_entity_id`/`to_owner_entity_id` **dicabut** & nama badan hukum tidak dikirim;
  peran lintas-entitas tetap menerima keduanya (wewenang tidak berkurang). Dipasang di
  **dua** jalur `list_movements` (biasa + paginasi) dan `product_history`.
- **E5.3c** kebocoran Kartu Riwayat ditutup (`resolve_list_scope`).
- **Frontend** `CounterpartyBadge` dipakai layar **Mutasi** (`LedgerTable.jsx`) & **Kartu
  Riwayat Produk** (`ProductHistoryPanel.jsx`): lencana biru "↙ dari Kanda" / jingga
  "↗ ke Kanda" + tooltip.
- **POC** `backend/test_core_e5_visibility_poc.py` **52/52**, **terbukti bisa MEMERAH**
  (scope disabotase → 7 FAIL), terdaftar di `scripts/gate.sh`.
- **Kerapian repo**: **124 skrip uji lama** akar repo → `tests/archive/` + README
  (nol rujukan dari `scripts/`, gate tetap hijau). Akar kini hanya 3 skrip seed.
- `memory/test_credentials.md` diisi (berkas ini di-gitignore, jadi hilang tiap clone).

### Bukti penutup
`gate.sh --ci` **HIJAU** · POC E-5 **52/52** · `testing_agent_v3` iterasi **216:
frontend 23/23 LULUS, nol error konsol**.

### Jebakan yang layak diingat
1. **Jangan** `search_replace` **paralel pada berkas yang sama** — dua edit di
   `LedgerTable.jsx` saling menimpa, baris impor hilang, layar blank
   (`PAGE ERROR: CounterpartyBadge is not defined`). Gate tidak menangkapnya karena gate
   tidak menjalankan peramban; screenshot + log konsol yang menangkap.
2. `plan.md` repo ini **BUKAN** berkas yang boleh ditimpa alat `plan` bawaan — ia roadmap
   71 KB. Backup: `.logs/plan.md.bak.session-E5-E7`.
3. Setelah clone: jalankan `bash /app/.restore_env.sh` (pip + yarn + restart + seed + build).

### Berikutnya
**FASE E-7 (antar-entitas)** — keadaan awal sudah diverifikasi sesi ini: E7.1 permintaan
internal **belum ada** · E7.2/E7.7 penanda entitas grup di `customers`/`suppliers`
**belum ada** (nol rujukan `business_entities`) · E7.4 "Kas Besar Grup" (`entity_id="all"`)
+ **13 dari 19** transaksi kas masih `all` · E7.5 pinjaman antar-PT & pindah aset tetap
**belum ada** (`fin_fixed_assets` 0 baris) · E7.6 `interco_returns` mengirim
`return_pair_id` tanpa `pair_id`/`qty_total`, `TRF-00001..3` masih seri grup.
Rencana eksekusi bergelombang: lihat `plan.md` §RENCANA EKSEKUSI E-7.

---


## SESI 2026-08-10 (repo `janabagganajana/kn`) — **VERIFIKASI FONDASI MULTI-ENTITAS (TANPA EKSEKUSI KODE)**

Permintaan pemilik (kalimat aslinya): *"saya ingin benahi soal pengaturan entitas, mulai dari
mekanisme pemilihan dan penambahan entitas lalu pembuatan akunya yang tertaut dengan entitas,
coba telusuri dulu bagaimana codenya yang berhubungan dengan ini laporkan baru lanjut
development"* → dilanjutkan *"sekarang kita masih tahap verifikasi dan validasi… pastikan
belum ada eksekusi, semuanya ditampung dan dibuatkan execution plan-nya"*.

**Sesi ini SENGAJA tidak mengubah kode fitur.** Yang dihasilkan: peta kode, bukti empiris
cacat, keputusan pemilik, dan rencana eksekusi terperinci di `plan.md` (plan D-14 lama
diarsipkan ke `.logs/plan_archive_pre_ENTITAS.md`).

### Yang dilakukan
- Repo dipulihkan & dijalankan (backend + build FE + `seed_realistic.py`).
- Penelusuran kode entitas: `routers/entities.py` · `services/entity_provisioning_service.py` ·
  `services/entity_context_service.py` · `entity_scope.py` · `core_utils.next_doc_number` ·
  `routers/users.py` · `routers/auth.py` · `permissions_config.py` · FE `EntitySwitcher.jsx` ·
  `AdminView.jsx` (tab Entities/Users) · `useAppActions.js` · `SettingsHub.jsx`.
- **Audit empiris** (alat baru, hanya-baca): `scripts/entity_audit/` — sapuan **300 endpoint GET
  × 4 identitas**, verifikasi baris-demi-baris, probe siklus hidup entitas & akun.
  Laporan: `AUDIT_ISOLASI_ENTITAS.md`, `AUDIT_ENTITAS_2026-08-10.md`,
  `.logs/audit_isolation_report.md`.

### Temuan utama (semua berbukti, rincian + akar masalah di `plan.md` §1.2)
- **Fondasi scoping BAGUS** (`entity_scope.py`) dan dokumen inti benar-benar terisolasi
  (SO 8↔1, pelanggan 4↔1, neraca Rp 981 jt ↔ Rp 46,6 jt, dst). Anti-IDOR 403/404 di 6 endpoint.
- **12 kebocoran nyata**: notifikasi · rencana bayar · selisih bayar · nota denda · target sales ·
  insentif sales · **jejak audit seluruh grup terbaca sales & gudang** · `GET /api/lots/{id}`
  (200 untuk lot PT lain) · **AR aging mencampur dua PT** (`entity_id` selalu `"all"`) ·
  **`/api/settings/effective` mengabaikan `X-Entity-Id`** (Kanda non-PKP tetap dapat PPN 12%) ·
  12 `hr_org_units` yatim (entitas sudah dihapus) · stempel entitas salah pada target/insentif seed.
- **15 cacat pengaturan entitas & akun**: `PATCH /entities` tanpa cek keunikan `doc_prefix`
  (berhasil membuat dua entitas ber-prefix `KSC`), cache kode entitas tak pernah dibersihkan,
  entitas nonaktif tetap bisa dipilih lalu **jatuh diam-diam** ke entitas home, mode
  "Semua Entitas" **menulis diam-diam** ke home, deaktivasi entitas tanpa pagar (user-nya masih
  bisa bekerja di entitas mati), `DELETE /api/users/{id}` **405**, email akun bisa duplikat lewat
  PATCH, turun jabatan admin→sales tidak mencabut akses lintas-PT, tak ada formulir ubah
  entitas/akun, notifikasi "entities dibuat: undefined", 7 field entitas tak ada di UI.
- **Master & konfigurasi masih bersama** padahal harus per entitas: kop surat/template dokumen,
  tarif insentif (`all`), aturan persetujuan (`all`), syarat pembayaran, kategori biaya,
  kebijakan retur; **gudang tidak punya field entitas sama sekali**; **47 dari 200 entri Pusat
  Pengaturan hanya bisa global** (seluruh BPJS/PPh21/lembur, UOM, lot, penerimaan, makloon).
- **Nomor dokumen campur**: data demo memakai seri grup (`PO-00005`=Kanda, `PO-00007`=KSC) vs
  data baru ber-prefix (`KSC/PO-00012`); `warehouse_transfers` masih mode grup.
- **Harga per entitas**: mesin `entity_prices` + `/api/pricelist` ADA tetapi **0 baris** —
  jalur harga per entitas belum pernah terbukti dipakai.

### Keputusan pemilik yang mengikat eksekusi berikutnya
1. Sales: **detail stok entitas sendiri + angka global agregat**; detail per-entitas hanya sisi
   admin. (Analisis akses/UI **sales vs admin-sales** DIPARKIR sampai urusan entitas selesai.)
2. Semua modul pinggir wajib per entitas. **Jejak audit: hanya admin, hanya entitas aktif.**
3. Gudang **campur**: ada bersama, ada khusus entitas.
4. Harga: **master global + override per entitas**, UI override & label asal nilai wajib jelas.
5. Nomor dokumen **wajib ber-prefix entitas**; dokumen demo lama dihapus, seed disesuaikan.
6. **Semua** master/konfigurasi yang masih bersama harus jadi per entitas.
7. Entitas karyawan **bersumber dari HR**. Pelanggan sama di 2 entitas: dibiarkan, tanpa
   perlakuan khusus. Jumlah entitas **bisa puluhan**. Jenis entitas **bukan hanya PT** — CV,
   **perorangan**, dst.

### Berikutnya
Eksekusi `plan.md` mulai **FASE E-0 (tutup kebocoran + pagar anti-regresi)**.

---

## SESI 2026-08-10 (lanjutan) — **VERIFIKASI ANTAR-ENTITAS + DOMAIN SALES vs ADMIN SALES**

Masih **tanpa eksekusi kode**. Dua permintaan lanjutan pemilik:
*"bagaimana sekarang dengan antar entitas, di system apa yang support dengan antar entitas
misal pembelian antar entitas dll"* → lalu *"sekarang fokus pada domain sales dan admin sales
mari kita bedah dan luruskan"*.

### A. Antar-entitas (laporan: `AUDIT_ANTAR_ENTITAS.md`)
**Fondasi G-6/G-6b kuat & terbukti** (POC `backend/tests/test_g6_poc.py` **21/21**,
`scripts/verify_data_integrity.py` **233 PASS/0 FAIL** termasuk **INV-IC-01..08**):
dokumen kembar `KSC/IC-0000x ↔ KANDA/IC-0000x` · harga wajib dari kontrak internal
(`supplier_contracts.partner_kind="entity"`) · 3 mode harga & 3 mode PPN (ber-scope entitas) ·
faktur pajak internal berpasangan `KSC/FKT-00003` ↔ masukan Kanda · saldo pasangan
IC-AR Rp 1.766.010 == IC-AP · netting `KANDA/ICS-00001` Rp 1.887.888 · jembatan gudang
`TRF-00004` (roll pindah pemilik + dinilai ulang, tanpa jurnal dobel) · retur antar-PT
`KANDA/ICR-00001 ↔ KSC/ICR-00001` · eliminasi margin **otomatis** di konsolidasi
(unrealized Rp 2.437.100) · laporan margin per pair & per produk · 7 kunci konfigurasi
grup **"antar-entitas"**.

**Celah baru (masuk E-0/E-7)**: `/api/transfers*` **tanpa scoping entitas sama sekali**
(list/detail/approve/reject/status/delete) & 2 transfer antar-PT **tanpa `entity_id`** ·
**18 koleksi ber-`entity_id` tidak terdaftar** di registry + drift `input_tax_invoices` →
`tax_invoices_in` · 6 router tanpa scoping + 5 parsial · **cetak Surat Jalan PT lain**
(`documents/preview/{order_id}` 200) & jejak dokumen lintas-PT · **gudang bisa membaca saldo
antar-PT, settlement, laporan margin** · **tidak ada pagar** bila PT grup didaftarkan sebagai
supplier/pelanggan biasa (margin tak tereliminasi) · HPP penjual bisa 0 → "margin 100%" ·
**Kas Besar Grup** (13/19 transaksi kas ber-`entity_id="all"`, termasuk penerimaan piutang KSC).

**Keputusan pemilik**: entitas lain diperlakukan **seperti PEMASOK, bukan pelanggan**
(pembedanya menu Antar Entitas) · **kas grup dihapus** (setiap uang milik satu entitas) ·
HPP taksiran **boleh tapi wajib berlabel** · jalur baru yang dibangun **hanya pinjaman uang
antar-PT & pindah aset tetap** (titip bayar/alokasi biaya/makloon internal/penempatan
karyawan: tidak terjadi).

### B. Domain Sales vs Admin Sales (laporan: `ANALISIS_DOMAIN_SALES.md`)
**Akar masalah**: sistem hanya punya **4 peran** — **tidak ada "admin sales"**. Orang itu
harus dijadikan `sales` (tak bisa Konfirmasi SO) atau `manager` (ikut dapat tutup buku,
payroll, bayar tagihan supplier, hapus master).

**Kabar baik — mesin pemenuhan SO sudah ada**: `preview-allocation` sudah mengklasifikasi
`from_stock/from_incoming/inter_company/backorder` + `cross_entity[]` + kalimat penjelas ·
`GET /stock/pending-so` (papan pending + coverage + promise date) · `repeat-restock`
SO→PR dengan jejak dua arah (`source="so_repeat"`) · `restock-state` (`open_pr_number`) ·
`stock/atp` · pegging · auto-fulfill backorder · mesin Antar Entitas. **E-8 = menyatukan +
memberi peran**, bukan menulis mesin baru.

**Penyimpangan (A1–A10)**: sales melihat SO rekannya (Bima lihat 8 SO Ayu, nol miliknya) ·
progres gudang 403 walau menunya tampil · sales boleh terbitkan faktur pajak/catat kwitansi/
putuskan selisih bayar/pegging/memicu PR (lalu daftar PR-nya 403) · `mark-delivered` oleh
sales · Konfirmasi SO hanya manajer · validasi administratif tercampur persetujuan `nilai` ·
transaksi antar-PT **tidak tertaut SO** · keputusan pemenuhan tersebar di 5 layar domain lain.

**Temuan KRITIS L21**: `preview-allocation` & `preview-lots` **mengabaikan `entity_ctx`** dan
jatuh ke `DEFAULT_ENTITY_ID` → **sales CV Kanda dijanjikan stok 788 yard milik KSC** ("Stok
on-hand cukup (788). Dapat langsung direservasi.") dan boleh memaksa `entity_id=ent_ksc`;
`preview-roll-reconcile?all_entities=true` membocorkan nomor roll & kode lot PT lain
(`RL-632A10`, `KSC/LOT-2608-0026`).


### C. Rantai jual → beli internal antar-PT → retur berantai (laporan: `ANALISIS_FLOW_RETUR_BERANTAI.md`)
Skenario pemilik dilacak langkah demi langkah. **Didukung ±80%.** Lengkap & terbukti:
dokumen kembar antar-PT + kontrak harga internal + faktur pajak internal + jembatan gudang
(pindah kepemilikan roll + re-home lot bergenealogi + revaluasi) + saldo pasangan + netting +
eliminasi margin · retur pelanggan (kebijakan retur, inspeksi per roll, 4 outcome partial,
karantina lot `RTN-*`, nota kredit) · retur antar-PT kembar (alasan wajib + dual-control) ·
retur beli ke supplier (kebijakan impor, siklus supplier-accept/reject).

**6 titik rantai yang putus/berisiko (→ FASE E-9 di `plan.md`):**
1. Penerimaan barang antar-PT **tidak memicu** `auto_fulfill_backorders` (hanya dari
   `inbound_receiving.py:585` & `qc_service.py:263`) → SO tetap `waiting_stock` walau barang datang.
2. `interco_transactions` **tanpa `source_order_id`** → tak ada jejak "IC ini untuk SO-0009"
   (padahal PR sudah punya `source_ref_id`).
3. **DUA JALAN** untuk "A retur ke B" tanpa rambu: `/api/interco/returns` (benar) vs
   `return_service.transfer_return_roll_ownership` (at-cost, tanpa PPN, tanpa memperbarui
   `returned_qty` & eliminasi margin) → saldo antar-PT tidak akan nol bila salah pilih.
4. Retur antar-PT memilih roll **FEFO per produk**, bukan roll retur pelanggan → **roll bagus
   terkirim balik, roll cacat tinggal**.
5. Roll hasil retur pelanggan dibuat **tanpa `supplier_id`/`po_id`** dan `acquired` ditimpa
   `{"via":"transfer"}` saat pindah kepemilikan → Entitas B **tidak bisa** meretur barang itu
   ke supplier aslinya (`build_returnable_rolls` menyaring supplier/PO).
6. Ketiga retur **tidak saling tertaut** (mesin relasi G-4 belum dipasang untuk rantai ini).

Prasyarat: **L21** wajib beres lebih dulu (keputusan beli-internal tidak boleh berangkat dari
angka stok PT yang salah). POC wajib: `backend/test_core_rantai_retur_poc.py` (E9.8).

### Berikutnya
Eksekusi `plan.md` mulai **FASE E-0** (kini termasuk L13–L21).
**Keputusan penutup pemilik untuk E-8 (sudah dikunci):** Admin Sales **berbasis penugasan
entitas** (1 atau beberapa PT, pakai `allowed_entity_ids`, JANGAN masuk `CROSS_ENTITY_ROLES`) ·
**Kasir/Finance dipisah** → dibuat **2 peran baru**: `sales_admin` + `finance`, dan
**uang masuk (kwitansi AR) + Faktur Pajak keluaran = `finance`** ·
`mark-delivered` **boleh gudang maupun Admin Sales** (dicabut dari sales) ·
Admin Sales **berkuasa penuh** atas keputusan pemenuhan (PR/reorder, ambil dari PT lain,
pegging) **tanpa** persetujuan manajer, dengan config ambang tetap tersedia.
Total peran menjadi **6**: admin · manager · sales_admin · finance · sales · warehouse.
Hirarki: `sales:1 · warehouse:1 · sales_admin:2 · finance:2 · manager:3 · admin:4`.

---


## SESI 2026-08-07 (lanjutan, repo `kamanabamaanaba/kn`) — **FASE 4: KPI SAYA · DASBOR MANAJER · RAPOR DESAINER**

Tugas pemilik (tiga permintaan lanjutan, kalimat aslinya): *"KPI Saya: Beri desainer
halaman nilai dirinya sendiri di Profil Saya, tanpa bisa melihat nilai rekan"* ·
*"Dasbor Manajer: Bangun halaman depan khusus manajer berisi antrean persetujuan, target
tim, dan keterlambatan hari ini"* · *"Rapor Desainer: Buat tombol unduh laporan KPI
desainer ke PDF/Excel supaya bisa dibawa ke rapat bulanan"*.

### A. KPI Saya (privasi ditegakkan di SERVER)
- `rnd_kpi_service.my_kpi()` + `my_rounds()` → `GET /api/rnd/reports/my-kpi?period=`.
  **Tanpa `require_permission`** (setiap orang berhak melihat nilainya sendiri), tetapi
  penyaringan nama dilakukan di server sehingga nilai rekan **tidak mungkin** terkirim.
  Yang dikembalikan: `me` (baris sendiri), `rank`/`total_designers`, `team` (AGREGAT:
  rata-rata nilai, on-time%, rework%), `rounds[]` + `overdue[]` milik sendiri, `weights`
  (yang dinilai berhak tahu aturannya). Tidak ada key `items`/`leaderboard`.
- FE `features/hr/MyDesignerKpiCard.jsx` dipasang di Profil Saya (ESS): nilai + huruf
  grade, peringkat, pembanding tim, 5 metrik, blok "round Anda lewat tenggat", riwayat
  round sendiri, filter periode. Bila belum punya round → kartu ringkas penjelas
  (`ess-designer-kpi-none`), bukan tabel kosong.
- Demo: seeder menambah 2 permintaan yang dikerjakan **akun manajer (Dewi Rahayu)** dan
  **dinilai admin** (bukan menilai diri sendiri) — batch terpisah `rnd_kpi_me_v1` supaya
  bisa ditambahkan ke database yang sudah punya batch v1. Tanpa ini fitur tak bisa
  diperagakan karena desainer demo lain hanyalah NAMA pada jejak round (tanpa akun).

### B. Dasbor Manajer (menutup satu-satunya sisa EPIC 1)
- `home_service.manager_home()` diperkaya + helper `_approval_queue`, `_late_today`,
  `_designer_snapshot`. `GET /api/home/manager` (sudah ada, kini berisi):
  antrean persetujuan **dirinci per jenis** (SO / PO / harga khusus / permintaan lain,
  masing-masing dengan `view` tujuan klik), `target` yang dibandingkan dengan **kemajuan
  bulan** (`month_progress_pct`, hari ke-n dari m), `team[]` dengan target & capaian
  per sales, `late_today` dari **4 sumber** (piutang lewat tempo · round R&D lewat
  tenggat · tugas gudang > 2 hari · WO dirilis > 3 hari), dan cuplikan kinerja desainer.
- FE `features/home/ManagerHome.jsx` + rute `manager-home`; `ROLE_HOME_REGISTRY.manager`
  diubah dari `reports` → `manager-home`. Setiap baris bisa diklik langsung ke layar
  kerjanya.

### C. Rapor Desainer (ekspor)
- `services/rnd_kpi_export.py` — **satu definisi kolom** dipakai CSV, Excel, dan PDF
  supaya isi ketiga berkas tidak mungkin berbeda dari layar. CSV (BOM UTF-8 agar Excel
  Windows benar) · Excel (`openpyxl`, header navy + freeze pane + format rupiah) · PDF
  (`reportlab` landscape, pola sama slip gaji, huruf grade berwarna).
- `GET /api/rnd/reports/designer-kpi/export?period=&format=csv|xlsx|pdf` (RBAC penilai:
  admin/manager 200 · sales/gudang 403; format tak dikenal → **400 pesan jelas**).
  FE: 3 tombol di layar KPI Desainer + notifikasi hasil unduhan.

### Perbaikan yang muncul saat pengujian (dua-duanya nyata)
1. **Landing peran tidak deterministik** — `App.js` kini me-reset view+navId setiap kali
   `user.id` berubah (login, pulih sesi akun lain, tukar akun di tab yang sama). Dulu
   layar peran sebelumnya bisa tertinggal (temuan agen uji: manajer melihat "Operasi
   Gudang"). Deep-link tidak terganggu karena efek hanya dipicu oleh perubahan `user.id`.
2. **Sesi basi merender kerangka rusak** — dulu `if (!user)` saja: bila `kn_user` masih
   tersimpan tetapi `kn_token` hilang/kedaluwarsa, aplikasi merender seluruh kerangka
   yang setiap panelnya berisi galat "Login diperlukan". Sekarang `if (!user || !token)`
   → kembali ke layar masuk dengan pesan **"Sesi Anda sudah berakhir — silakan masuk lagi."**
3. **Tech-debt gate dibereskan**: `IntercoTaxModal.jsx` memecah path aksi faktur pajak
   internal menjadi **literal** (`/tax-invoice`, `/tax-invoice/replace`, `/tax-invoice/cancel`)
   → `verify_api_contract` kini **0 ERROR / 0 WARN** (sebelumnya 1 error pra-ada).

### Bukti empiris
`POST /auth/login` manajer → mendarat di **Dasbor Manajer** (bukan Laporan/WMS) pada tiga
skenario: login segar · gudang→logout→manajer di tab yang sama · sesi `kn_user` basi
milik gudang. Sales & gudang: **tidak ada** menu Desainer, ESS menampilkan kartu ringkas,
**nol** nama rekan di layar (diperiksa dari `body.innerText`). `my-kpi` manajer →
grade **C 57,6**, peringkat **3/4**, 3 round, 1 nunggak. Ekspor: CSV 1.099 B ·
XLSX 6.303 B (4 baris data = 4 desainer) · PDF 3.847 B (`%PDF`), nama berkas
`kpi-desainer-<periode>-<tanggal>.<ext>`.

### Gate & Test
POC `test_core_phase4.py` **29/29** · POC `test_core_ps18.py` **23/23** (tanpa regresi) ·
`verify_api_contract` **0 ERROR / 0 WARN** · `check_nav_map` PASS · `validate_compliance`
**22 PASS / 0 FAIL** · `verify_data_integrity` **233 / 0 / 0** ·
`testing_agent_v3` iter_199: backend **68/68 (100%)**, frontend Dasbor Manajer 10/10 —
satu temuan HIGH (landing manajer) **sudah diperbaiki** lalu diverifikasi ulang di browser
untuk 3 skenario + 4 peran.

### Catatan untuk sesi berikutnya
* Tetap: **frontend tanpa hot reload** → `bash /app/scripts/rebuild_frontend.sh`.
* **Jebakan uji**: `dependencies.extract_token` mengutamakan cookie sesi HttpOnly di atas
  header Bearer. Bila satu klien HTTP dipakai login beberapa peran, cookie login terakhir
  menimpa semuanya dan uji RBAC salah baca — bersihkan cookie setelah login.
* Sisa backlog: **PS-17** (divisi sebagai aktor R&D) menunggu keputusan **D-13**;
  opsional lanjutan: tren grade bulanan (chart) & ekspor rapor per desainer.

---

## SESI 2026-08-07 (repo `kamanabamaanaba/kn`) — **PS-18 KPI DESAINER + ESKALASI SLA DITUTUP & HIJAU**

Tugas pemilik: *"lanjutkan development dari repo ini, sesi terakhir berhenti di sini"* →
titik henti = pertanyaan kebijakan PS-18. Pemilik menyetujui **1a · 2a · 3a · 4a** dengan
TAMBAHAN penting: *"pindahkan ke designer, designer dan rnd juga dipisahkan menunya jangan
digabungkan"*. Ambang/bobot: pemilik minta pakai default → dibuat **configurable** di Pusat
Pengaturan (bukan hardcode).

### Setup restore
`git clone https://github.com/kamanabamaanaba/kn` → rsync ke `/app` (`.env` DIPERTAHANKAN:
MONGO_URL/DB_NAME/REACT_APP_BACKEND_URL) → `bash .restore_env.sh` (pip + yarn + restart +
seed + `rebuild_frontend.sh`). Login demo terverifikasi: `admin@kainnusantara.id / demo12345`
(dicatat ulang di `memory/test_credentials.md` yang sebelumnya kosong).

### Audit sebelum menulis kode (KODE MENANG atas DOKUMEN)
* SUDAH ADA: `GET /api/rnd/reports/performer` (round/ACC/revisi/rata skor/rata hari), papan SLA
  di `RndReportsView` (merah tapi **PASIF**), registry `scheduler_service.JOBS` (17 job),
  `notification_service.create_notification` + `wa_alert_service`, `config_catalog_rnd.py`.
* BELUM ADA: job penjadwal untuk SLA R&D, metrik on-time/rework/grade, filter periode, dan
  menu desainer yang terpisah.

### Yang dibangun (ringkas — detail per-berkas di `memory/PRD.md` §PS-18)
1. **POC lebih dulu** — `test_core_ps18.py` membuat data uji lewat LAYANAN NYATA (create →
   send dengan tenggat lampau → unggah bukti → setor → nilai), menguji math KPI, dua tingkat
   eskalasi, idempotensi, lalu **membersihkan datanya**. **23/23 lulus** sebelum UI disentuh.
2. `services/rnd_kpi_service.py` (KPI + grade komposit + filter periode, bobot dinormalkan).
3. `services/rnd_sla_service.py` (papan + `job_rnd_sla_escalation`, manager → admin ≥3 hari,
   dedupe harian, permintaan `decided`/`cancelled` dilewati).
4. Job `rnd_sla_escalation` harian 07:35 WIB di `JOBS` (18 job total).
5. 3 endpoint baru + **RBAC penilaian** (`APPRAISAL_ROLES` admin/manager; sales & gudang 403).
6. 6 kunci config `rnd.sla_escalate_admin_days` / `rnd.kpi_weight_*` / `rnd.kpi_penalty_*`.
7. **IA dipisah**: menu **"Desainer"** (KPI Desainer · Desain & Pattern · Galeri Desain + AI)
   berdiri sendiri; `rnd-hub` jadi "R&D (Spesifikasi & Sample)" 3 tab; hub HRD jadi
   "KPI Karyawan". `features/designer/` 5 berkas baru; `RndReportsView` menyisakan 3 teratas
   + pintu masuk.
8. `scripts/seed_rnd_kpi_demo.py` — data demo idempotent 2 desainer baru + 2 round nunggak
   (1 hari & 4 hari) + `_realism_pass()` yang menggeser `sent_at` round demo lama supaya
   kolom "rata hari" tidak nol.

### Bukti empiris
`POST /api/rnd/sla/escalate` → `created=3, scanned=2, detail="2 round lewat tenggat · 1
dinaikkan ke admin"`; panggilan kedua `created=0` (idempotent). `GET /api/rnd/sla/board` →
KSC/SMP-00010 4 hari `tier=admin`, KSC/SMP-00008 1 hari `tier=manager`.
`GET /api/rnd/reports/designer-kpi?period=30d` → Dewi Lestari **B 75,9** · Rina Kartika
**C 67,1** · Bagas Nugroho **D 0** (semua round terlambat + 100% diulang → penalti 60 melebihi
nilai dasar 21,4 lalu dijepit 0; tooltip menjelaskan "nilai dasar − penalti").
RBAC: admin/manager 200 · sales/warehouse **403** pada designer-kpi & sla/board & escalate,
tetapi `/rnd/samples` & `/rnd/reports/performer` tetap 200 (wewenang lama tidak hilang).

### Gate & Test
`test_core_ps18.py` **23/23** · `check_nav_map` PASS · `validate_compliance` **22 PASS/0 FAIL**
· `verify_data_integrity` **233 PASS/0 FAIL** · `audit_config_wiring` 105 kunci, **0 DEAD /
0 ORPHAN_UI** · `health_check` 23 PASS/0 FAIL · `ux_audit` tidak menandai berkas baru ·
`testing_agent_v3` iter_198: backend **91/93**, frontend **11/11**, 0 bug UI.
Satu temuan (sales/gudang bisa membaca designer-kpi) **sudah diperbaiki** lalu diverifikasi
ulang dengan curl 4 peran.

### Catatan untuk sesi berikutnya
* **FRONTEND TIDAK ADA HOT RELOAD** — wajib `bash /app/scripts/rebuild_frontend.sh` setelah
  mengubah `frontend/src` (lihat `memory/PREVIEW_STABLE_MODE.md`).
* 1 ERROR PRA-ADA di `verify_api_contract`: `features/finance/interco/IntercoTaxModal.jsx`
  memakai path dinamis `${API}/interco/transactions/${id}/tax-invoice${path}` → gate tidak bisa
  meresolusinya. Bukan regresi sesi ini; perbaikannya = pecah menjadi path literal.
* Sisa FASE H: **PS-17** (divisi sebagai aktor R&D) masih menunggu keputusan bisnis **D-13**.

---

## SESI 2026-08-06 (repo `janabavanaka/kn`) — **FASE G-5 UNLOCK PERIODE DITUTUP & HIJAU**

Tugas pemilik: *"lihat dokumen handoff dan lanjutkan"* → prioritas #1 yang disetujui
pemilik = **G-5 Unlock Periode Berotoritas** (config bawaan: jendela 24 jam · batas mundur 7 hari).

### Yang dibangun (FASE G-5) — "wajib dua orang & menutup sendiri"
- **Hard-lock periode tertutup**: `gl_service.enforce_closed_period_guard` dipanggil di
  `_insert_entry` **dan** `create_manual_entry` — jurnal MUNDUR ke periode `closed`
  **DITOLAK** kecuali ada jendela unlock aktif (dulu cuma peringatan/soft). JE yang lahir
  di jendela ditandai `backdated_in_unlock: <plu_id>` + membuat closing jadi **Basi**.
- **Kontrol ganda**: pengusul ≠ penyetuju (self-approve ditolak 400).
- **Jendela berbatas waktu**: config `periode.unlock_window_hours` (24) — sesudah disetujui,
  periode terbuka sekian jam; lewat batas = **auto-reclose** (job `period_unlock_auto_close`
  interval 1 jam + tombol `/reclose-expired`). Batas mundur: `periode.max_days_after_close` (7).
- **Koleksi** `period_unlock_requests` (prefix `plu_`) · **router** `/api/finance/period-unlocks`
  (list/active/POST/approve/reject/reclose-expired) · **izin** modul `period:[unlock,backdate]`
  (admin+manager, ter-sync otomatis via `sync_permission_modules`).
- **Frontend**: layar **Keuangan → Buka Periode (Unlock)** (`PeriodUnlockView.jsx`) — usul/
  setujui/tolak/riwayat + countdown jendela + dual-control (tombol setujui mati untuk pengusul).
  **Banner MERAH global** (`PeriodUnlockBanner.jsx`) tampil di semua layar admin/manager saat
  ada jendela aktif. Catatan ClosingView diperbarui (kunci = hard-lock, arahkan ke layar unlock).

### Bukti hijau
- **POC**: `cd /app/backend && python -m pytest tests/test_g5_poc.py` → **12/12** (termasuk
  bukti-merah INV-CLS-01/02 & auto-reclose, tanpa residu).
- **Gate**: `python scripts/verify_data_integrity.py` → **233 PASS / 0 FAIL / 0 WARN**
  (invarian baru **INV-CLS-01** [tak ada JE mundur menyusup periode tertutup tanpa unlock] &
  **INV-CLS-02** [tiap unlock disetujui: ber-alasan + pengusul ≠ penyetuju], layer `closing`).
- **Testing agent**: backend **16/16** · frontend komponen lengkap + banner terlihat di dashboard.

### Lingkungan (pemulihan repo di sesi ini)
Kode disinkron dari GitHub → `pip install` (tambah reportlab/weasyprint/pymupdf/openpyxl/qrcode/
APScheduler/anthropic) → seed `python seed_realistic.py` → build `bash scripts/rebuild_frontend.sh`
(FE dilayani `static_server.js` dari `frontend/build`, **bukan** dev-server). Login admin
`admin@kainnusantara.id` / `demo12345`.

### Prioritas BERIKUTNYA (urutan disetujui pemilik 2026-08-06 — G-5 SUDAH ✅)
1. ~~**P0 · G-5 Unlock Periode**~~ ✅ **SELESAI sesi ini**
2. **P1 · F-2 Harga kontrak di PO manual** — picker kontrak di POCreateForm + jejak sumber di PODetailPanel.
3. **P2 · Cetak nota retur & faktur pajak internal** (document_templates + esign).
4. **P3 · Rapor margin per BARANG** (urut margin terbesar + penyaring pasangan PT).

---

## 0000000. SESI 2026-07-30 (repo `ghananamakaa/kn`) — **FASE G-6 ANTAR ENTITAS DITUTUP** + 8 bug NYATA

Dokumen lengkap: **`docs/KN_36_PLAN_FASE_G6_ANTAR_ENTITAS.md` §8**

### 0000000.1 Titik henti yang diverifikasi lebih dulu
Tugas pemilik: *"clone repo `ghananamakaa/kn`, verifikasi titik berhenti (testing agent
sebelumnya berhenti tanpa menjalankan satu pun uji), lanjutkan."*

| Klaim titik henti | Verifikasi |
|---|---|
| POC G-6 15/15 | ✅ benar (`cd /app/backend && python -m pytest tests/test_g6_poc.py`) |
| backend + UI interco lengkap | ✅ ada & hidup di layar |
| blok jurnal di Detail Panel | ❌ **selalu kosong** — memanggil `/api/gl/entries` (404), galat ditelan |
| eliminasi margin bisa dipakai user | ❌ **tanpa tombol** (hanya lewat curl) |
| INV-IC dijaga gate | ❌ **belum ada**; POC G-6 juga belum terdaftar di `gate.sh` |
| data demo G-6 | ❌ layar **kosong** setelah `seed_realistic.py` |
| US8 "tanpa dobel mutasi" | ❌ transfer gudang antar-PT **masih** memposting jurnal at-cost M-3 |

### 0000000.2 Yang dibangun
* **Jembatan gudang (US8)** — `POST /api/interco/transactions/{id}/warehouse-task`;
  saat gudang menyetujui: at-cost M-3 **dilewati** (alasan tercatat), roll pembeli
  **dinilai ulang** ke harga beli internal, status pair maju ke `received`, lot ikut
  pindah pemilik (genealogi ke lot asal).
* **Jurnal MENGIKUTI BARANG** — akun baru **`1-1310` Persediaan Dalam Perjalanan (Antar-PT)**.
  Konfirmasi = dokumen & utang; perpindahan = HPP penjual + `1-1310 → 1-1300` pembeli.
  HPP memakai **biaya nyata roll yang keluar** (bukan WAC×qty). Efek: WARN `INV-GL-DRIFT`
  HILANG → integritas **229 PASS / 0 FAIL / 0 WARN**.
* **Eliminasi unrealized profit OTOMATIS** (create/update/remove) + tombol
  **Sinkron Antar-PT (G-6)** & **Sinkron Pasangan Jurnal (M-3)** di Konsolidasi Grup.
* **Batal ber-alasan yang MEMBALIK jurnal** dua buku (+ modal alasan di layar).
* **Detail Panel** menampilkan seluruh bukti: 2 buku jurnal · HPP · penerimaan · pembalikan ·
  eliminasi (badge AUTO G-6) · tugas gudang · timeline.
* **Gate**: lapisan `interco` **INV-IC-01..06** + POC G-6 di `gate.sh --full`; POC jadi
  **bukti-merah** & **nol residu** (snapshot/restore stok).
* **Data demo** lewat jalur produksi: `seed_interco()` (4 transaksi + 3 kontrak internal).

### 0000000.3 Cara uji cepat
```bash
cd /app/backend && python -m pytest tests/test_g6_poc.py -q       # 21 / 0
cd /app && python scripts/verify_data_integrity.py                # 229 / 0 / 0
cd /app && python scripts/verify_data_integrity.py --only interco  # INV-IC-01..06
cd /app && bash scripts/gate.sh --full                            # SEMUA GATE HIJAU
```
UI: **PEMBELIAN → Hutang Supplier (AP) → tab "Antar Entitas (Jual-Beli)"** ·
eliminasi: **KEUANGAN → Laporan & Analitik → Konsolidasi Grup → tab Eliminasi**.

### 0000000.4 Jebakan yang sudah terbukti (jangan diulang)
* **Jangan** memposting persediaan pembeli saat dokumen dibuat — barangnya belum ada.
  Itu akar drift GL↔subledger; gunakan `1-1310` lalu reklas saat barang diterima.
* **Jangan** membuat transfer antar-PT terpisah untuk barang yang sudah punya transaksi G-6:
  pakai *Buat Tugas Gudang* (menyimpan `interco_pair_id`) supaya jurnal tidak dobel.
* Menjalankan POC G-6 **membersihkan** data demo G-6 di akhir (memang begitu) →
  jalankan `python seed_realistic.py` sesudahnya bila layar mau berisi lagi.
* Sesudah login, backend menaruh cookie `session_token` HttpOnly dan `require_permission`
  membacanya LEBIH DULU daripada header `Authorization` (SEC-2). Jadi "200 tanpa header"
  pada klien yang sudah login **bukan** endpoint tanpa penjaga — tanpa kredensial tetap 401.
* ⚠️ **POC G-9 memakai angka ABSOLUT** (mis. saldo uang muka supplier di master supplier).
  Kalau sebelumnya ada skrip uji manual yang menerbitkan uang muka/refund dan tidak
  dibersihkan, POC G-9 bisa MERAH di `gate.sh --full` walau kodenya sehat. Terjadi sekali di
  sesi ini: standalone `python backend/test_g9_case_poc.py` sesudah `seed_realistic.py`
  langsung **118 PASS / 0 FAIL**, dan `gate.sh --full` hijau lagi. Aturan praktisnya:
  **seed ulang sebelum menyalakan gate penuh** kalau baru menjalankan uji manual.

---

## 0000000. SESI 2026-08-06 (repo `hanabavaja/kn`) — **FASE G-6b DITUTUP** (4 lanjutan Antar Entitas) + 4 bug NYATA

Dokumen lengkap: **`docs/KN_36_PLAN_FASE_G6_ANTAR_ENTITAS.md` §9**

### Titik henti yang diverifikasi LEBIH DULU
Tugas pemilik: *"lanjutkan development repo ini, plan apa saja yang belum diexekusi
lanjutkan"* — lalu koreksi pemilik: *"cek kembali, harusnya G-6 sudah"*.

| Klaim | Verifikasi di lingkungan ini |
|---|---|
| G-6 sudah dibangun | ✅ BENAR — POC `tests/test_g6_poc.py` **21/0**, `gate.sh --full` hijau, layar hidup (8 dokumen kembar) |
| Penutupan G-6 tercatat di dokumen | ❌ belum di clone pertama → pemilik **push ulang**, sesudah rsync semuanya lengkap (KN_36 §8, ENTITY_REGISTRY, BUG_REGISTRY 9 entri, tests/INDEX) |
| Bug Aset Tetap sudah diperbaiki | ❌ **masih hidup** di clone pertama (`salvage >= biaya`) — diperbaiki sesi ini, lalu ikut hijau di push pemilik |

Pilihan pemilik untuk lanjutan: **4 lanjutan G-6 → G-5 Unlock Periode → utang teknis §G-12/F-2**.

### Yang dibangun (FASE G-6b)
* **A. Faktur Pajak Internal ber-PPN** — `services/interco_tax_service.py`: pasangan
  dokumen NYATA di koleksi yang SUDAH ADA (`tax_invoices` keluaran di penjual +
  `tax_invoices_in` masukan di pembeli, `source_type="interco"`). Efek langsung:
  **rekap `vat_summary` tiap PT akhirnya memperhitungkan PPN antar-PT** (sebelumnya
  posisi kurang/lebih bayar SALAH untuk semua transaksi internal). Retur → faktur
  ditandai *perlu pengganti*, bukan diedit.
* **B. Retur Antar-PT** — `services/interco_return_service.py` + koleksi
  `interco_returns`: dokumen kembar, **dual-control**, jurnal dipisah seperti G-6
  (dokumen saat disetujui · barang saat **tugas gudang ARAH BALIK** selesai), roll
  dinilai ulang KEMBALI ke harga perolehan asli penjual (kalau tidak: GL 1-1300 ≠
  subledger selamanya). Nilai dokumen TIDAK diedit — retur dicatat `returned_*`.
* **C. Pengingat Settlement** — `services/interco_reminder.py` + job harian
  `interco_settlement_reminder` (07:40 WIB) + tombol **Ingatkan**. Netting tetap
  MANUAL (keputusan pemilik #3 dihormati).
* **D. Rapor Margin Grup** — `services/interco_margin.py` + tab **Rapor Margin**:
  realized vs unrealized dari **sisa panjang roll bertanda** (data nyata).

### 🔴 4 BUG NYATA yang ditutup (detail: `memory/BUG_REGISTRY.md`)
| ID | Sev | Inti |
|---|---|---|
| **KN-FA-SALVAGE-UNDEF** | **P1** | `FixedAssetsParts.jsx` memakai `biaya` yang tak terdefinisi → tombol **Simpan** Aset Tetap terasa MATI tanpa pesan. Sisa codemod bahasa; ketemu lewat `oxlint no-undef`, bukan uji fungsional |
| **KN-G6-ELIM-FULL-MARGIN** | **P1** | Eliminasi konsolidasi menghapus **100% margin** antar-PT walau barangnya sudah terjual ke pihak luar ⇒ **laba grup dilaporkan terlalu kecil**. INV-IC-03 lama ikut membenarkannya (**"invarian hijau tapi hampa"**). Kini `Dr Pendapatan S · Cr HPP (S−M·u) · Cr Persediaan (M·u)`, `u` dari roll nyata; identik dengan perilaku lama saat u=1 |
| **KN-G6-IDLE-FAKE** | P2 | "Umur saldo" dari `updated_at` yang ikut berubah setiap hitung-ulang ⇒ saldo menganggur berbulan-bulan tampak 0 hari dan pengingat tak pernah menyala. Kini dari **aktivitas nyata** |
| **KN-G6-POC-RESTORE-GAP** | P2 | POC G-6 belum memulihkan koleksi turunan baru ⇒ `gate.sh --full` MEMERAH (INV-IC-07/08) walau produknya benar — contoh nyata "gate merusak data" |

### Bukti penutupan
```
pytest backend/tests/test_g6b_poc.py -q     # 15 PASS / 0 FAIL (nol residu)
pytest backend/tests/test_g6_poc.py  -q     # 21 PASS / 0 FAIL
python scripts/verify_data_integrity.py     # 231 PASS / 0 FAIL / 0 WARN (INV-IC-01..08)
bash scripts/gate.sh --full                 # SEMUA GATE HIJAU (160 s)
testing_agent_v3 iter_193                   # backend 53/53 (100%)
```

### Catatan penting untuk agen berikutnya
* 🔴 **Jangan jalankan `test_g6_poc.py` dan `test_g6b_poc.py` dalam SATU perintah
  pytest** — xdist menjalankannya paralel dan blok bersih-bersih saling menimpa
  (9 gagal palsu). `gate.sh` memanggilnya sebagai gate TERPISAH; manual: satu per satu.
* 🔴 **Aplikasi ini TIDAK punya routing berbasis URL.** 117+ layar dipilih lewat
  `activeView` (nav/tab) + deep-link `kn-open-*`. Laporan uji "URL `/finance/...`
  menampilkan Control Tower" adalah **false positive** — bukan bug.
* ⚠️ Menulis file dokumen besar lewat Python: **selalu `encoding="utf-8"` saat read
  DAN write, dan tulis ke berkas sementara lalu `os.replace`**. Sesi ini `plan.md`
  sempat terpotong menjadi 0 baris karena `open(p,"w")` menghapus isi sebelum
  `UnicodeEncodeError` (dipulihkan dengan `git checkout -- plan.md`).
* Faktur pajak internal data demo **sengaja** ditandai *perlu pengganti* (ada retur
  sesudahnya) supaya tombol **Faktur Pengganti** bisa dicoba pengguna.
* Sesudah testing agent menjalankan alur tulis, jalankan `python seed_realistic.py`
  lalu `verify_data_integrity.py` untuk memulihkan data demo.

### Langkah berikutnya — **4 item DIMINTA PEMILIK 2026-08-06** (rencana rinci: `memory/PRD.md` §LINGKUP FASE BERIKUTNYA)
1. **P0 · G-5 Unlock Periode Berotoritas** — *"wajib dua orang & menutup sendiri saat
   waktunya habis"*. BELUM ADA KODE. `period_unlock_requests` (`plu_`) · dual-control ·
   jendela `periode.unlock_window_hours` + job **auto-reclose** · tag
   `backdated_in_unlock` · permission `period:{unlock,backdate}` · banner merah global ·
   **INV-CLS-01/02** + POC `tests/test_g5_poc.py`.
2. **P1 · F-2 Harga kontrak di PO manual** — contract picker di `POCreateForm` ·
   `_create_po_core` → `contract_service.resolve_active` · jejak sourcing di
   `PODetailPanel` (datanya sudah tersimpan, hanya tak pernah terlihat).
3. **P2 · Cetak nota retur & faktur pajak internal** — lewat `document_templates` +
   `esign_service` (blok ttd bernama + QR verifikasi + blok Referensi Dokumen G-4).
4. **P3 · Rapor margin per BARANG** — agregasi `interco_margin.py` per `product_id`,
   tab baru di Rapor Margin, urut margin terbesar.

### Fitur lain yang BELUM diimplementasikan (inventaris jujur, untuk sesi berikutnya)
| # | Belum ada | Catatan teknis |
|---|---|---|
| 1 | **FASE H · PS-17** divisi/jabatan sebagai aktor R&D | TERBLOKIR: butuh keputusan pemilik **D-13** (daftar final divisi & approver) |
| 2 | **FASE H · PS-18** KPI designer + eskalasi SLA | `hr_kpi` sudah ada (6 dok); belum ada perancang KPI & SLA-nya |
| 3 | **FASE H · PS-20** produk eksklusif per sales | belum ada peta produk↔sales |
| 4 | **Alur Penawaran (Quotation)** | config `sales.quotation_enabled` sengaja `NOT_USED` — NOL endpoint. Jangan aktifkan sebelum alurnya dibangun |
| 5 | **WhatsApp NYATA** | provider masih `simulated` (Outbox saja). Butuh Fonnte (1 token) atau Meta Cloud (`phone_number_id` + token + template UTILITY) |
| 6 | **NSFP resmi DJP** faktur pajak (termasuk internal) | masih diisi MANUAL; belum ada alokasi/e-Faktur otomatis |
| 7 | **`MODAL_BASELINE`** 12 modal lama tanpa bilah error sendiri | utang teknis terpantau gate INV-UI-03 — daftar hanya boleh MENGECIL |
| 8 | 13 berkas sisa baseline `ux_audit` | migration backlog (loading/empty state), bukan bug |
| 9 | **`validate_compliance` 3 WARN** | 1 NAMING `db.interco_transactions` (prefix domain) + 2 lain — sengaja WARN, bukan FAIL |
| 10 | Retur antar-PT **sesudah sebagian terjual keluar** | saat ini retur memakai roll yang masih ada; belum ada penjaga khusus bila stoknya sudah habis terjual (gudang akan menolak reservasi — pesannya sudah jelas, tapi belum ada pratinjau di layar) |
| 11 | **Pengingat settlement per-PT** | ambang `antar_entitas.settlement_reminder_days` sudah ber-scope entity, tetapi belum ada layar untuk melihat riwayat pengingat yang pernah terkirim (hanya lonceng) |

**Mulai dari #1.** Sesi 2026-08-06 berhenti di sini SETELAH fase G-6b ditutup penuh
(semua gate hijau, dokumen lengkap) — bukan di tengah pekerjaan.

---

## 000000. SESI 2026-07-30 (repo `hakakanabava/kn`) — **FASE G-7 KONTRABON DITUTUP** + 7 bug NYATA (2 di antaranya sumber "hijau lalu merah")

Dokumen lengkap: **`docs/KN_35_PLAN_FASE_G7_KONTRABON.md` §7**

### 000000.1 Titik henti yang diverifikasi lebih dulu
Tugas pemilik: *"clone repo `hakakanabava/kn`, verifikasi, lanjutkan — sebelumnya terhenti
di dua `search_replace` pada `doc_refs_service.py` & `contra_bon_service.py`."*

| Klaim titik henti | Verifikasi di lingkungan baru |
|---|---|
| dua suntingan terakhir tersimpan | ✅ benar — ada di commit `050860a "WIP: simpan progress saya"` |
| backend G-7 lengkap | ✅ benar — service 1.371 baris · 24 endpoint · POC 951 baris · invarian INV-CB-01..04 |
| POC G-7 hijau | ❌ **TIDAK** — `16 PASS / 16 FAIL`, berhenti di langkah pertama |
| frontend G-7 | ❌ **BELUM ADA SAMA SEKALI** (`features/purchasing/contrabon/` tidak ada) |

**Akar POC merah bukan di produk:** POC memaku **id supplier** (`sup_c3dd8f4879ea`, …) dan
**nomor PO** (`KSC/PO-00007`) — dua hal yang berubah setiap `seed_realistic.py` dijalankan.
Sesudah id diresolusi dari data (dan PO kedua DICARI, bukan dipaku): **120 PASS / 0 FAIL**.

### 000000.2 Yang dibangun
* **SELURUH frontend FASE G-7** — `frontend/src/features/purchasing/contrabon/`:
  `ContraBonsView` (6 KPI + 3 tab: *Daftar Kontrabon* · *GR Belum Ditagih* ·
  *Jadwal Tukar Faktur*) · `ContraBonListTable` · `ContraBonDetailPanel` + `ContraBonParts` ·
  `ContraBonCreateWizard` (3 langkah) · `UnbilledReceiptsTab` · `ExchangeSchedulesTab` ·
  6 modal (`ExchangeSchedule` · `Deduction` · `Decision` · `Pay` · `PaymentSchedule` ·
  `ReasonNote`) · `contraBonApi.js`.
* **Jembatan G-8 ↔ G-7 di layar**: `features/finance/bank/ReconContraBonModal.jsx` + tombol
  **"Bayar kontrabon"** pada baris mutasi dana KELUAR (`ReconLinesTable`). Terbukti: baris
  berubah jadi **Tercocok · satu-satu** ke `CASH-00018` setelah kontrabon dibayar dari sana.
* **IA**: tab hub `accounts-payable` → *Kontrabon (Tukar Faktur)* (Gudang ikut melihat),
  `navMeta` (`contra-bons`), `AppViewRouter`.
* **Data demo lewat JALUR PRODUKSI**: `seed_contra_bons()` di `seed_realistic.py` memanggil
  endpoint yang SAMA dengan UI memakai `httpx.ASGITransport` (in-process, tanpa jaringan,
  tanpa perlu server hidup) → 3 kontrabon (LUNAS berpotongan denda · dijadwalkan bayar ·
  diajukan dengan selisih 3-way menunggu keputusan) + 1 faktur dibiarkan bebas + 3 jadwal
  tukar faktur + 1 baris mutasi bank keluar untuk melatih US8.
* **Gate baru**: `POC FASE G-7` di `scripts/gate.sh`; label invarian 219 → **223**.
* `ENTITY_REGISTRY.md`: koleksi `contra_bons` dicatat lengkap (field, invarian, jurnal per
  jenis potongan, endpoint, RBAC, daftar **JANGAN BUAT**).

### 000000.3 🔴 7 BUG NYATA yang ditutup (detail: `memory/BUG_REGISTRY.md`)
| ID | Sev | Inti masalah |
|---|---|---|
| **KN-G7-POC-DRIFT** | P2 | POC memaku id supplier & nomor PO → **titik henti sesi sebelumnya** |
| **KN-SEED-PO-ENTITY-RANDOM** | **P1** | entitas PO demo diacak `random.random() < 0.3` **tanpa `random.seed`** → data demo tidak deterministik (POC flaky, nomor `KSC/PO-*` bergeser) **dan** PO milik PT KSC ditujukan ke supplier yang terdaftar di CV Kanda. Kini entitas PO = entitas supplier |
| **KN-G7-CSS-GHOST** | **P1** | `stat-card` `stat-label` `stat-value` `input-field` `modal-panel` `link-button` dipakai **11 berkas layar** tetapi **0 kemunculan** di bundel CSS hasil build → kartu KPI tampil sebagai tulisan telanjang, kotak isian tanpa garis tepi, tombol tautan tabel jadi tombol abu bawaan browser. **Uji fungsional tetap hijau** — hanya mata/bundel CSS yang bisa menangkapnya |
| **KN-G7-WH-PERM-NOISE** | P2 | peran Gudang disambut bilah merah "Permission ditolak: supplier.view" di layar yang memang boleh dibukanya |
| **KN-G7-SCHED-DEFAULT-NONE** | P2 | "Atur jadwal" default *Tidak terjadwal* → Simpan tidak berdampak apa pun yang terlihat |
| **KN-G7-NOTICE-TIMER** | P2 | timer pesan lama menghapus konfirmasi baru (tampil ±0,5 detik) — pola ini **diwarisi dari G-9**, periksa layar lain |
| **KN-G7-DEMO-NO-CANDIDATE** | P2 | seluruh faktur demo terpakai → wizard "Kontrabon baru" kosong untuk semua supplier |

### 000000.3b Lanjutan sesi — dua permintaan pemilik berikutnya
* ✅ **Potongan Otomatis (dikerjakan)** — wizard kontrabon kini MENAWARKAN dokumen potongan
  yang tersedia (nota debit retur beli & uang muka supplier) langsung di langkah 2:
  centang → nominal (boleh sebagian) → ringkasan hidup `faktur − potongan = yang dibayar` →
  potongan menempel otomatis sesudah nomor kontrabon terbit (tiap potongan tetap lewat
  penjaganya sendiri, INV-CB-04). Nilai bersih negatif → peringatan + tombol terkunci.
  Langkah yang DITOLAK backend dilaporkan di bilah error (kontrabon tetap terbit).
  Berkas baru: `WizardCreditPicker.jsx`. Data demo menambah **1 uang muka supplier**
  (kelebihan bayar jalur G-3) supaya fitur ini bisa dicoba. Uji layar **8 PASS / 0 FAIL**.
* 📋 **G-6 Transaksi Antar Entitas (BARU DIRENCANAKAN, belum dibangun)** — rencana lengkap
  hasil pembacaan kode ada di **`docs/KN_36_PLAN_FASE_G6_ANTAR_ENTITAS.md`**: 8 temuan awal
  (a.l. jurnal antar-PT sudah ada TAPI **at-cost by design**, `intercompany_accounts` belum
  ada, eliminasi konsolidasi baru pada level pasangan akun — **unrealized profit belum
  dihitung**), 11 user story, invarian **INV-IC-01..04**, urutan eksekusi G-6.0..G-6.5, dan
  **3 keputusan pemilik SUDAH MASUK (2026-07-30)** dan terkunci di §6 dokumen itu:
  (1) harga antar-PT **`fixed_price` dari kontrak internal** — transaksi DITOLAK bila barang
  belum berharga di kontrak aktif, sistem tidak boleh menebak; (2) **PPN per-PT** lewat
  config ber-scope entity `antar_entitas.ppn_mode` (`ikut_pkp` bawaan · `tanpa_ppn` ·
  `dengan_ppn`) + invarian baru **INV-IC-05** (PPN keluaran penjual == PPN masukan pembeli);
  (3) settlement **sewaktu-waktu** lewat tombol — **tanpa job penjadwal**, hanya pengingat
  opsional bila saldo menganggur. Karena harganya tetap dari kontrak, **eliminasi unrealized
  profit di konsolidasi WAJIB ikut dibangun** (INV-IC-03), bukan ditunda.
  Eksekusi berikutnya mulai dari §7 urutan `G-6.0 → G-6.5`.
* 🐞 Ditemukan & ditutup saat verifikasi ulang: **KN-G9-POC-SC-RESIDU** — POC G-9
  meninggalkan baris buku saldo kredit `adjust −120.000` sehingga jalan BERIKUTNYA merah
  (POC memblokir dirinya sendiri). Kini POC membersihkan baris yang menyebut nomor kasusnya.

### 000000.4 Bukti penutupan
```
python backend/test_g7_contrabon_poc.py     # 120 PASS / 0 FAIL (nol residu)
python scripts/verify_data_integrity.py     # 223 PASS / 0 FAIL / 0 WARN
bash scripts/gate.sh --full                 # 41 gate HIJAU (140 s)
testing_agent_v3                            # iter_189 — BE 120/120 · FE nol bug
uji layar Playwright (3 bagian · 4 peran)   # 49 PASS / 0 FAIL
```

### 000000.5 Catatan penting untuk agen berikutnya
* 🔴 **Login menaruh session cookie (SEC-2).** `require_permission` memakai cookie LEBIH DULU
  daripada header `Authorization`. Skrip apa pun yang memakai **dua peran** WAJIB memakai
  **dua klien HTTP terpisah** — kalau tidak, semua permintaan dikenali sebagai satu orang dan
  pemisahan tugas ("pembuat ≠ penyetuju") menolak sendiri. Ini menghabiskan waktu di sesi ini.
* 🔴 **Frontend TIDAK punya hot reload** (bundle statis). Sesudah mengubah `frontend/src`:
  `bash /app/scripts/rebuild_frontend.sh`.
* ✅ **`frontend FATAL` karena port 3000 dipegang proses yatim SUDAH DIPERBAIKI**
  (`KN-FE-PORT-ORPHAN`): pemicunya `supervisorctl signal HUP frontend` di
  `rebuild_frontend.sh` — Node mati oleh SIGHUP sementara pembungkusnya tidak, lalu proses
  yatim menahan port. Sekarang HUP dihapus (tidak pernah diperlukan: `static_server.js`
  membaca berkas dari disk per permintaan) dan `yarn start` membebaskan port lebih dulu.
  Bila masih terjadi, jangan tambal manual — periksa siapa yang mengirim sinyal.
* Uji layar dari dalam container **wajib memakai preview URL**, bukan `localhost:3000`
  (dari origin localhost, CORS menolak panggilan `/api` ke domain preview).
* Playwright: `inner_text()` mengembalikan teks TER-RENDER, jadi kepala tabel ber-`uppercase`
  terbaca HURUF BESAR. Nominal `formatCurrency` memakai **spasi tak-putus** (U+00A0) — jangan
  bandingkan dengan `"Rp 0"` biasa.
* Anti-residu POC memakai **garis dasar**, bukan "harus nol dokumen": POC mencatat jumlah
  kontrabon + penghitung nomor `CB` + jadwal supplier sebelum jalan lalu memulihkannya.
  Menghapus buta penghitung nomor akan membuat nomor kontrabon **kembar** dengan data demo.
* Data demo menyisakan **satu faktur supplier bebas** (`INV-SLO-2620`) supaya wizard bisa
  dicoba. Jangan menghabiskannya tanpa mengganti.
* Fase berikutnya menurut §G-11: **G-6 Transaksi Antar Entitas** → **G-5 Unlock Periode**.

---

## 00000. SESI 2026-07-30 (repo `gababannauahanam/kn`) — **FASE G-9 DITUTUP** + 3 bug NYATA di jalur "apa yang dibaca pengguna"

Dokumen lengkap: **`docs/KN_34_PLAN_FASE_G9_PUSAT_KASUS_KEUANGAN.md`**

### 00000.1 Titik henti yang diverifikasi lebih dulu
Tugas pemilik: *"clone repo `gababannauahanam/kn`, verifikasi, lanjutkan. Titik terhenti di
ronde `testing_agent_v3` untuk FASE G-9."*

| Klaim titik henti | Verifikasi di lingkungan baru |
|---|---|
| POC G-9 `116 PASS / 0 FAIL` | ✅ benar (dijalankan ulang apa adanya) |
| `gate.sh --full` 38 gate HIJAU | ✅ benar (124s) · `verify_data_integrity` **219 PASS / 0 FAIL / 0 WARN** |
| `finance_cases` terdaftar SCOPED + `ENTITY_REGISTRY.md` | ✅ ada |
| Laporan ronde lalu: **US8 NOT_TESTED · regresi PARTIAL** | ✅ benar — dua lubang itu dikerjakan sesi ini |
| `docs/KN_34_…` (deliverable penutup fase) | ❌ BELUM ADA — dibuat sesi ini |

Restore: `git clone` → `rsync` ke `/app` (`.env` DIPERTAHANKAN) → **`bash .restore_env.sh`**
(pip minus `emergentintegrations`/`litellm` yang URL-pin · `yarn install` · `seed_realistic.py`
· `scripts/rebuild_frontend.sh`). Catatan lapangan yang TERULANG lagi: supervisor `frontend`
FATAL `EADDRINUSE :3000` karena proses `static_server.js` **yatim** dari boot masih memegang
port → `kill -9` PID-nya lalu `supervisorctl restart frontend`.

### 00000.2 Kenapa ronde uji sebelumnya melaporkan "95%" padahal ada bug P1
Ronde iter_187 memeriksa **respons API**; ia tidak pernah menanyakan **apa yang terlihat di
layar ketika API menolak**. Ketiga bug sesi ini persis di celah itu — logika uangnya benar,
penyampaiannya ke manusia yang rusak. **Tambahkan pertanyaan uji ini selamanya:**
*"kalau backend MENOLAK, kalimat apa yang dibaca pengguna, dan di mana?"*

### 00000.3 Bug NYATA yang ditutup (detail: `memory/BUG_REGISTRY.md`)
1. **`KN-G9-ERR-SILENT` (P1)** — `components/ErrorNotice.jsx` menerima prop **`message`**,
   tetapi 2 layar keuangan TERBARU mengirim objek error axios lewat prop **`error=`**
   (`FinanceCasesView` G-9 · `BankReconciliationView` G-8) → komponen `return null` →
   **SEMUA penolakan backend tak terlihat**: tekan "Jalankan & selesaikan"/"Buka kasus" →
   tidak terjadi apa pun. 115 layar lain memakai `message=` dengan benar. Lapisan kedua:
   wizard & modal adalah MODAL, bilah error layar induk ada di BELAKANG lapisan modal — jadi
   memperbaiki nama prop saja belum cukup. Perbaikan: helper baru `utils/apiError.js`
   (`apiErrorText`), `ErrorNotice` menormalkan objek juga (pertahanan berlapis) + prop
   `onAction/actionLabel`, dan **6 modal** dapat bilah error SENDIRI. Penjaga baru
   **INV-UI-03** `scripts/guardrails/verify_error_notice.py --self-test` (aturan A prop
   `message` wajib · B normalisasi · C modal penulis API wajib punya bilah error sendiri),
   dengan `MODAL_BASELINE` 12 modal lama yang **hanya boleh MENGECIL**.
2. **`KN-G9-REASON-MISMATCH` (P2)** — wizard menawarkan SELURUH 12 label alasan untuk SEMUA
   11 jenis kasus, sehingga *"Dana masuk tak dikenal"* bisa ditutup beralasan *"Cek / giro
   ditolak bank"*. **INV-CASE-01 tetap HIJAU** karena ia hanya memeriksa alasan ADA — kelas
   **"invarian hijau tapi hampa"**. Perbaikan: `reason_codes` per playbook (SSOT di
   `services/finance_case_playbooks.py`), penjaga `_reason_or_fail(code, case_type)` dengan
   pesan MENUNTUN (menyebut label yang benar, bukan kode), UI menyaring `case-field-reason`
   & `case-reject-reason`. **2 uji bukti-merah baru → POC 116 → 118 PASS.**
3. **`KN-I18N-MONEY` (P2)** — sesudah bug #1 diperbaiki, pesan yang akhirnya TERLIHAT memakai
   angka gaya Inggris (*"Rp 999,000,000"*) di antarmuka Bahasa Indonesia. **Tidak mungkin
   ditemukan sebelum #1 diperbaiki** — contoh nyata *bug yang saling menyembunyikan*.
   Perbaikan: `core_utils.rupiah()` jadi SATU sumber format uang, **91 pola** di 30 berkas
   dialihkan (codemod tercatat `scripts/_codemod_rupiah.py`), 8 helper `_rp()` lokal jadi
   alias tipis. Penjaga: `audit_i18n_id.py` **aturan [7]** (self-test 12 → **16 skenario**).
4. **`KN-G9-REOPEN-NOUI` (P2)** — `POST /finance-cases/{id}/reopen` hidup di backend TANPA
   satu tombol pun. Ditambah `case-reopen-box`: ditutup tanpa dokumen → boleh dibuka ulang
   (alasan wajib); sudah melahirkan dokumen → tombol TERKUNCI **beserta alasannya**
   (`case-reopen-locked`), bukan disembunyikan.

### 00000.4 Dua lubang ronde lalu — DITUTUP
* **US8 (dulu NOT_TESTED, dan ternyata SENYAP).** Tombol "Buka kasus" di **Rekonsiliasi Bank
  → Dana Titipan** dulu hanya memanggil API lalu menyuruh pengguna mencari menunya sendiri —
  dan bila kasusnya sudah ada, penolakannya tak terlihat. Sekarang ada deep-link global BARU
  **`kn-open-finance-case`** (`features/finance/cases/caseDeepLink.js` +
  `hooks/useCaseDeepLink.js`, pola yang sama dengan `kn-open-config` G-0 / `kn-open-trace`
  G-4 / `kn-open-rnd` FASE F): tekan tombol → berpindah sendiri ke Pusat Kasus Keuangan →
  panel detail terbuka pada kasusnya → kalimat penuntun tampil bergaya PERINGATAN (bukan
  hijau sukses). Kasus tujuan diambil ulang lewat `GET /finance-cases/{id}` — bukan dicari di
  daftar yang mungkin belum selesai dimuat (lomba-waktu itu sempat membuat layar salah
  berkata "kasus tidak ada di daftar ini" padahal barisnya terpampang).
* **Regresi keuangan (dulu PARTIAL).** 12 layar disapu lewat Playwright: Dasbor Keuangan ·
  AR/Piutang & Umur · Rencana Bayar & Denda · Store Credit · Buku Besar & CoA · Laporan &
  Analitik · Tutup Buku · Pajak · Kas & Bank (Rekening & Saldo) · Rekonsiliasi Bank keempat
  tab (`lines`/`holding`/`rules`/`formats`) · Pusat Pengaturan. **0 error JS · 0 halaman
  kosong · 0 id teknis mentah** (`ent_*`, `fcs_*`, `cash_*`, `stmtline_*`, `amr_*`, `cust_*`).

### 00000.5 Penyelesaian NYATA dari layar (US2) — bukti, bukan klaim
KSC/CASE-00001 → aksi *Alokasikan ke pelanggan / pesanan* → pelanggan *Butik Bali Indah* →
alokasi Rp 100.000 ke SO-0003 → alasan *Pemilik dana ketemu* → **status Selesai** +
**Dokumen turunan (2)**: `KSC/JE-00058` (Dr 2-1950 Titipan Dana / Cr 1-1200 Piutang) dan
`SO-0003` pelunasan Rp 100.000; **Relasi dokumen** `SO-0003 (settles)`; **Jejak waktu**
memuat 2 entri eskalasi + entri penyelesaian. Sesudah uji, data demo dipulihkan
(`seed_realistic.py`) dan `verify_data_integrity` kembali **219 PASS / 0 FAIL / 0 WARN**.

### 00000.6 Gate & bukti akhir
`bash scripts/gate.sh --full` → **39 gate HIJAU** (126s; +1 gate baru
`guard:error_notice`) · POC G-9 **118 PASS / 0 FAIL** nol residu ·
`verify_data_integrity` **219 PASS / 0 FAIL / 0 WARN** · `audit_i18n_id --strict` **0 temuan**
(dengan aturan [7] aktif) · `ruff --select F821` bersih · `esbuild` bersih ·
`testing_agent_v3` **iter_188** (BE 19/19 · FE 100%, 0 bug).

### 00000.7 Langkah berikutnya (menunggu keputusan pemilik)
1. **G-7 Kontrabon Advanced** — urutan §G-11 #7, butuh G-1 + G-4, dan sudah dirujuk playbook
   `lebih_bayar_supplier` ("potong kontrabon").
2. **G-6 Transaksi Antar Entitas** — dirujuk playbook `salah_entitas`; paling berdampak ke
   akuntansi & konsolidasi.
3. **G-5 Unlock Periode** — kecil, bisa diselipkan kapan saja.
4. Alternatif **FASE H** (PS-17 divisi sebagai aktor R&D — butuh keputusan pemilik D-13;
   PS-18 KPI designer + eskalasi SLA; PS-20 produk eksklusif per sales).
5. **Utang teknis tercatat & terpantau gate:** `MODAL_BASELINE` (12 modal lama belum punya
   bilah error sendiri) — daftar hanya boleh MENGECIL.

---


## 0000. SESI 2026-07-29 (lanjutan-2, repo `janababamakam/kn`) — **TITIK HENTI DITUTUP + GATE 2,7× LEBIH CEPAT**

### 0000.1 Titik henti yang diverifikasi
Tugas pemilik: *"clone repo `janababamakam/kn`, verifikasi, lanjutkan. Titik terakhir =
fase terakhir lulus gate atau tidak."* Plus pertanyaan: *"kenapa proses gate ini lama dan
panjang sekali, apakah semua itu penting?"*

| Klaim titik henti | Verifikasi |
|---|---|
| Guardrail baru **INV-UI-02** (`verify_entity_label.py`) sudah masuk `gate.sh` | ✅ ada & HIJAU (0 pelanggaran · self-test bukti-merah lolos) |
| 5 layar tidak lagi menampilkan `ent_ksc` | ✅ dicek di layar: Beranda/Control Tower, POS, Pusat Pengaturan, **Payroll** (dulu pilihan KOSONG → kini **"PT Kain Suka Cita"**) — nol `ent_*` mentah |
| `gate.sh --full` lulus semua? | ❌ **TIDAK** — 1 gate MERAH: `POC F0-C`. **Bukan** kebocoran PT, tapi **fixture flaky** |
| Data & invarian | ✅ `verify_data_integrity` **211 PASS / 0 FAIL / 0 WARN** |

Restore: `git clone` → `rsync` (`.env` DIPERTAHANKAN) → `pip install` (minus
`emergentintegrations`/`litellm` yang URL-pin) → `yarn install` → `seed_realistic.py` →
**`bash scripts/rebuild_frontend.sh` (WAJIB: `frontend/build` tidak ada di repo)**.
Catatan lapangan: supervisor `frontend` bisa FATAL karena proses `static_server.js` yatim
dari boot masih memegang port 3000 → `kill` proses yatim lalu `supervisorctl restart frontend`.

### 0000.2 Bug NYATA yang ditutup — `KN-F0C-FLAKY-FIXTURE`
`POC F0-C` MERAH di dalam gate tapi HIJAU saat dijalankan sendiri (26/1 vs 27/0) — pola khas
uji flaky. Akar: `stamp()` memilih dokumen dengan `find_one({"entity_id": ent})` **tanpa
syarat & tanpa urutan**. Untuk PT-B yang terpilih `wms_tasks` OUTBOUND (tanpa `po_number`),
sehingga himpunan nomor PT-B KOSONG → pemeriksaan "admin `X-Entity-Id=all` melihat kedua
entitas" MEMERAH karena bug uji. Bahaya sebenarnya bukan merahnya, tapi **hijau hampa**:
pemeriksaan "PT-A tidak melihat dokumen PT-B" lolos otomatis kalau himpunan PT-B kosong.
Perbaikan: pilih dokumen yang nomornya BENAR-BENAR dilaporkan endpoint (`NUM_FIELD` selaras
`routers/uom_conversions.py`) + `sort` deterministik + **bukti-merah kedua**: fixture WAJIB
punya nomor di kedua entitas, kalau tidak gate MEMERAH. Hasil: **28/0 · stabil 3× berturut**.

### 0000.3 Kenapa gate lama — dan apa yang diperbaiki (angka terukur)
Pengukuran, bukan dugaan: `verify_data_integrity.py --timing` menunjukkan **1 dari 30
lapisan** memakan 83% waktu (`config` 6,37s dari 7,66s). Turunannya: lapisan itu memanggil
`audit_config_wiring.hits()` yang **me-regex-scan 719 berkas untuk SETIAP setting**
(105 setting × 3 korpus = 315 pemindaian penuh). Karena POC fase memanggil skrip invarian
8–10× masing-masing, satu `gate --full` membakar ±200 detik hanya di situ.

| Perbaikan | Sebelum | Sesudah |
|---|---|---|
| `audit_config_wiring.build_rows` (index token sekali-jalan) | 6,23s | **0,07s (89×)** |
| `scripts/verify_data_integrity.py` (LENGKAP, 211 invarian) | 8,35s | **2,0s** |
| `audit_config_wiring --strict` | 5s | **0,7s** |
| POC fase pakai `--only <lapisan>` untuk blok BUKTI-MERAH | G-2 53s · G-3 49s · G-4 41s · F 54s | **12s · 11s · 10s · 12s** |
| `gate.sh --quick` | ~15s | **~8s** |
| **`gate.sh --full`** | **272s** | **99s** |

**Cakupan TIDAK dikurangi** — 36 gate & 211 invarian sama persis (bandingkan tabel receipt
sebelum/sesudah). Yang berubah hanya cara kerjanya:
1. **Index token** (`build_hit_index`) menggantikan regex per-setting. Supaya optimasi tak
   diam-diam menghilangkan temuan, `audit_config_wiring --self-test` bagian **[6]**
   membandingkan jalur index vs jalur regex untuk 315 pasangan → **315/315 identik**.
   (Satu beda ditemukan saat pengembangan: literal `'manager'` di dalam f-string
   `services/purchase_requisition_service.py` — pola tangkap diperbaiki agar identik.)
2. **`--only KEY[,KEY]`** pada `verify_data_integrity.py` (+ `--timing`). Dipakai POC HANYA
   di blok bukti-merah yang memang menguji satu keluarga invarian. Semua klaim GLOBAL
   ("invarian global HIJAU", "nol residu") **tetap** eksekusi LENGKAP 211 invarian.
3. **Kolam paralel gate STATIK** (11 gate read-only, `--jobs` = kuota cgroup, di sini 2) yang
   **menumpang jalan** bersama blok DB/runtime. `guard:numeric_bounds` SENGAJA dikecualikan:
   ia login + POST probe ke API, jadi tak boleh berbarengan dengan seed.
4. Mode baru **`--ci`**: cakupan = default, tanpa warna ANSI, plus **`memory/GATE_RECEIPT.json`**
   (untuk robot/CI). `--json` bisa dipakai di mode mana pun.

### 0000.4 Cara pakai gate sekarang (hemat waktu, tanpa menurunkan mutu)
```bash
bash scripts/gate.sh --quick   # ~8s  · sesudah menyentuh FE/dokumen (statik saja)
bash scripts/gate.sh           # ~25s · sesudah menyentuh backend/data
bash scripts/gate.sh --ci      # ~25s · untuk robot: tanpa warna + receipt JSON
bash scripts/gate.sh --full    # ~99s · SEBELUM menutup fase / klaim "selesai"
python scripts/verify_data_integrity.py --timing        # cari lapisan yang lambat
python scripts/verify_data_integrity.py --only rnd      # 1 keluarga invarian saja (~0,7s)
```

---


## 000. SESI 2026-07-29 (lanjutan) — **FASE F (R&D & DESIGN) DITUTUP**: US3 · US11 · US12 terverifikasi

Dokumen lengkap: **`docs/KN_31_PLAN_FASE_F_RND_DESIGN.md` §10**

### 000.1 Titik henti yang diverifikasi lebih dulu
Tugas pemilik: *"clone repo `malalakausa/kn`, verifikasi titik berhenti, lanjutkan."*
Titik henti = sesi sebelumnya berhenti tepat saat `testing_agent_v3` dipanggil untuk
ronde verifikasi penuh. Hasil verifikasi ulang di lingkungan baru:

| Klaim titik henti | Verifikasi |
|---|---|
| 5 kebocoran entity-scoping lintas-PT sudah diperbaiki | ✅ `backend/test_f0c_scoping_leak_poc.py` **27 PASS / 0 FAIL** + gate `verify_entity_scoping` HIJAU |
| Lokalisasi Inggris→Indonesia selesai (757 penggantian, ~230 berkas) | ✅ `scripts/audit_i18n_id.py` **0 temuan** + SELF-TEST bukti-merah HIJAU |
| `GET /api/onboarding` berbahasa Indonesia | ✅ 4 peran diperiksa; tidak ada *task queue/inbound/outbound/Advance/confirmed/dispatched* |
| US3, US11, US12 **belum diuji** | ✅ benar — dikerjakan sesi ini |

Setup restore: `git clone` → `rsync` ke `/app` (`.env` DIPERTAHANKAN), `pip install -r
requirements.txt` (minus `emergentintegrations`/`litellm` yang URL-pin), `yarn install`.
**Wajib diingat:** frontend disajikan sebagai **STATIC BUILD** (`frontend/build` +
`static_server.js`) — `frontend/build` **tidak ada di repo** (gitignore), jadi pasca-restore
preview 503 sampai `bash scripts/rebuild_frontend.sh` dijalankan. Lihat
`memory/PREVIEW_STABLE_MODE.md`. Di kontainer ini tersedia 8 vCPU sehingga `yarn build`
selesai **~28 s** (dokumen lama menyebut ~5 menit pada 1 vCPU).

### 000.2 US3/US11/US12 — hasil
POC baru **`backend/test_fase_f_us3_us11_us12_poc.py`** (single script, HTTP nyata,
self-cleanup, **42 PASS / 0 FAIL**, nol residu) + verifikasi UI langsung lewat Playwright,
lalu **`testing_agent_v3` iter_183: US3/US11/US12 100% (68/68 POC)**.

* **US3 — sales ditolak menjual produk R&D.** `RND-KTN-150` (`lifecycle=disetujui`) TETAP
  tampil di katalog (ditandai, bukan disembunyikan); `?orderable_only=true` menyaringnya;
  `POST /api/sales-orders` → **400** dgn pesan yang menuntun *"Selesaikan dulu alur R&D
  (Spesifikasi → Sample → Rilis ke Produksi)"*. Kontrol positif `BTK-MEGA-001` tetap lolos.
* **US11 — gudang melihat pengambilan bahan sample.** Tab **Mutasi** (`inventory-tab-ledger`).
  Ditambah **penyaring Jenis mutasi** + pintasan **"Ambil Bahan Sample (R&D)"** dan param
  BE baru `movement_type` → 1 baris, qty −3, dokumen `KSC/SMP-00001`. Nol kode mentah.
* **US12 — jejak dokumen.** Ditambah tombol **Jejak Dokumen** pada tiap baris
  *Kontrak Mitra & Supplier* → rantai `KSC/SPEC-00001 → KSC/SMP-00001 → KSC/SCT-00007`
  + daftar relasi dua arah. Node bisa diklik jadi jangkar (telusur berjenjang).

### 000.3 Bug NYATA yang ditemukan & diperbaiki sesi ini (detail: `memory/BUG_REGISTRY.md`)
1. **KN-F-LEDGER-RAWID (P2, FIXED)** — kolom **Dokumen** pada layar Mutasi menampilkan id
   teknis (`so_d29e63366078`, `wo_b1df696d5b1f`, `mko_b1ab0520c6c7:1`) untuk **5 dari 12**
   jenis mutasi. Modul baru `services/movement_label_service.py` menambah field turunan
   `source_document_label` (resolusi berkelompok, tanpa N+1): `so_…`→`SO-0007`,
   `mko_…:1`→`MKO-00001 · langkah 1`, dokumen terhapus → **"(dokumen sudah dihapus)"**
   (ditandai warna + `title`, bukan disembunyikan). Dipakai `/inventory/movements` &
   `/history/{product_id}`.
2. **POC-RESIDU-01 (P2, FIXED)** — satu `gate.sh --full` dari seed bersih menggeser data
   demo: `inventory_rolls` **53→75** (+22 roll potongan) dan saldo `prod_batik_mega`
   (`reserved` 50→173 · `available` 435→307). **Tidak terdeteksi** karena
   `gate_residue.py --check` berjalan SEBELUM blok POC. Ditutup dengan (a) checkpoint
   anti-residu **kedua** khusus blok POC, (b) modul `backend/poc_stock_guard.py`
   (snapshot→restore EKSAK koleksi stok) dipakai di POC G-0/G-1/G-2/G-3 + POC baru,
   (c) pembersihan mutasi yatim `reservation`/`release_reservation` di 4 POC,
   (d) jaring kedua: `seed_realistic` + `verify_data_integrity` dijalankan SETELAH blok POC.
3. **KN-F-SEED-NUMBER-DRIFT (P2, FIXED)** — `number_sequences` tidak ikut direset di
   `seed_realistic.clear_collections()` → seed ke-3 menghasilkan `KSC/SCT-00026…00032`
   untuk 7 kontrak. Nomor demo kini deterministik (`KSC/SCT-00001…00007`).
4. **UX POS (FIXED)** — tombol produk terkunci sebelumnya `disabled` = jalan buntu tanpa
   penjelasan. Sekarang bisa diklik (`aria-disabled` + `data-orderable="false"`) dan
   memunculkan alasan + langkah; keranjang tetap tidak bisa diisi.
5. **ux_audit E1 (FIXED)** — `features/rnd/SampleRoundList.jsx` (berkas FASE F sendiri)
   melanggar baseline UX: tanpa loading-state. Ditambah skeleton + empty-state per mitra.

### 000.4 Pelajaran proses (WAJIB dibaca agen berikutnya)
**JANGAN pernah memanggil `search_replace` PARALEL pada SATU berkas yang sama** — edit
saling menimpa dan yang terakhir menang. Terjadi lagi sesi ini: 4 edit paralel di
`InventoryStockView.jsx` → 1 hilang (penyaring tampil tetapi daftar tidak tersaring), dan
3 edit paralel di `SampleDetailPanel.jsx` → 1 hilang. Gejalanya HALUS (UI terlihat benar,
perilaku salah). Lakukan berurutan, lalu verifikasi dengan `grep`.

### 000.5 Gate & bukti akhir
`bash scripts/gate.sh --full` → **34 gate HIJAU** (2 gate BARU: `POC FASE F US3/US11/US12`,
`INV-GATE-01 anti-residu FASE POC`). `verify_data_integrity` **204 PASS / 0 FAIL** ·
`verify_api_contract` **0 ERROR** (417 path FE) · `audit_i18n_id` **0 temuan** ·
`validate_compliance` 23 PASS / 0 FAIL / 1 WARN (pra-ada `amendment_reasons` naming) ·
`check_nav_map` PASS · `find_dead_services` 122/122 dipakai · `esbuild` bersih ·
`testing_agent_v3` **iter_183** US3/US11/US12 **100%**.

### 000.6 Langkah berikutnya (menunggu keputusan pemilik)
1. **FASE H (PS-17/18/19/20)** — divisi/jabatan sebagai aktor R&D (butuh keputusan pemilik
   D-13: daftar final divisi & approver), KPI designer + eskalasi SLA, produk eksklusif per sales.
2. **FASE G sisa** menurut `plan.md` §G-11: G-8 Rekonsiliasi Bank → G-9 Pusat Kasus
   Keuangan → G-7 Kontrabon Advanced → G-6 Antar-Entitas → G-5 Unlock Periode.
3. **Utang teknis** `plan.md` §G-12 (F-2: contract picker di PO manual, jejak sourcing di
   PODetailPanel) + 13 berkas sisa baseline `ux_audit` (migration backlog, bukan FASE F).

---

## 00. SESI 2026-07-29 — **FASE G-3 DITUTUP** + kolom denda Umur Piutang **tertaut ke nota nyata**

Dokumen lengkap: **`docs/KN_30_PLAN_FASE_G3_SELISIH_PEMBAYARAN.md`**

### 00.1 Permintaan pemilik yang dikerjakan
1. **G-3 Selisih Pembayaran (lebih & kurang bayar)** — urutan berikutnya di `plan.md` §G-11.
2. **Menautkan kolom denda pada laporan Umur Piutang ke nota denda NYATA** (dokumen G-2).

### 00.2 Inti desain G-3 (kenapa angkanya jujur)
Dua batas dipakai: `expected` = Σ tagihan yang **sudah jatuh tempo** pada pesanan tujuan ·
`capacity` = nominal yang benar-benar **bisa dialokasikan**. Uang di antara keduanya
(bayar cicilan berikutnya lebih awal) **BUKAN selisih**. Selisih di dalam toleransi
diselesaikan **otomatis tapi tetap berlabel**; di luar toleransi wajib keputusan:
kurang → *sisa tetap piutang · ubah jadwal · hapus sisa*; lebih → *deposit · alokasi ke
pesanan lain · kembalikan dana*. Keputusan adalah **dokumen bernomor** (`<ENT>/SLB-#####`)
dengan **jurnalnya sendiri** (kwitansi tidak pernah diubah — ledger append-only).

### 00.3 Yang selesai
| Hal | Hasil |
|---|---|
| Koleksi & layanan | `payment_variance_decisions` · `services/payment_variance_service.py` · `routers/payment_variance.py` (8 endpoint) |
| Akun GL baru | **6-9100** Beban Selisih Pembayaran (+ routing kas `ar_refund` & `ap_advance`) |
| Rencana pembayaran | alokasi bisa **menyebut baris** (`plan_line_seq`) · `reschedule_line` (Σ rencana tetap) |
| Jalur AP | bayar supplier kurang receh → tagihan LUNAS · lebih bayar → **uang muka supplier** (1-1400 + `suppliers.advance_balance`) |
| Konfigurasi | **9 kunci** baru di Pusat Pengaturan → *Uang Masuk & Piutang* |
| Label alasan | **9 label** baru `applies_to: payment_variance` (taksonomi G-1) |
| RBAC | `payment_variance: [view, decide]`; hapus sisa & refund dijaga kebijakan + batas nominal |
| Invarian | **INV-VAR-01** (setiap selisih berlabel; menggantung >7 hari = FAIL) · **INV-VAR-02** (uang tidak hilang; tiap pemindahan uang punya jurnal) |
| Frontend | `PaymentVarianceDialog` (kalimat manusia + 3 kartu pilihan + dampak) · tab **Selisih Bayar** (antrean + riwayat + anulir) · takar selisih **live** di modal kwitansi · kolom **Selisih** di riwayat kwitansi |
| Umur Piutang | kolom **Denda** = nota denda nyata (bisa diklik) + *est. belum jadi nota* · tombol **Buat Nota Denda** (`POST /api/ar/aging/{id}/accrue-penalties`, idempoten) · drill-down memuat `PenaltyPanel` penuh |
| Denda tanpa rencana | `penalty_service.accrue_order()` — pesanan **tanpa** rencana pembayaran kini juga bisa punya nota denda (pakai term pelanggan) |
| Data demo | `seed_payment_variances()` — 3 keputusan berlabel (pembulatan · sisa tetap piutang · deposit), tanpa meninggalkan antrean menggantung |

### 00.4 Bug nyata yang ditemukan POC (bukan teori)
1. `ReceiptPayload` membuang field `variance` & `plan_line_seq` → **semua keputusan inline
   gagal senyap**.
2. Selisih sempat dihitung hanya terhadap tagihan jatuh tempo → pembayaran lebih awal
   salah dilaporkan "lebih bayar".
3. Jurnal kas AR tertunda sampai backfill startup → saldo Uang Muka Pelanggan sesaat
   negatif; sekarang diposting seketika + `post_cash_void` untuk pembatalan.
4. Contoh demo sempat membayar pesanan yang pendapatannya belum dijurnal → saldo AR negatif
   (INV-AR-01 benar memperingatkan). Seed kini hanya memilih pesanan ber-jurnal pendapatan.
5. Pembersihan POC belum menghapus **jurnal mutasi kas** (source_id = id CASH, bukan id
   kwitansi) → residu membuat AR negatif. Sudah diperbaiki; cleanup POC sekarang 0 WARN.

### 00.5 Bukti
`backend/test_g3_variance_poc.py` **70/0 HIJAU** (bukti-merah 4 invarian + nol residu) ·
`verify_data_integrity` **204 PASS / 0 FAIL / 0 WARN** · `bash scripts/gate.sh --full`
**HIJAU** (POC G-0/G-1/G-2/**G-3**/G-4/F-1/D) · `testing_agent_v3` iter_178 backend
**43/43** (0 bug) · 7 user story UI diverifikasi langsung lewat browser.

### 00.6 Langkah berikutnya
**G-8 Rekonsiliasi Bank** → G-9 Pusat Kasus Keuangan → G-7 Kontrabon (memakai uang muka
supplier dari G-3) → G-6 Antar Entitas → G-5 Unlock Periode.

---

## 00. SESI 2026-07-26 (lanjutan-4) — **FASE G-0 SELESAI 100%**

Dokumen lengkap: **`docs/KN_27_PENUTUPAN_FASE_G0_SATU_SUMBER_KEBENARAN.md`**

### 00.1 Titik berhenti yang ditutup
`App.js` punya `const [configFocus, setConfigFocus] = useState("")` yang **tidak pernah dipakai**;
`SettingsHub.focusKey` tidak pernah terisi; `LEGACY_DEEPLINK` nol importer. Janji "13 editor lama
menunjuk ke satu sumber kebenaran" belum ditepati.

### 00.2 Keputusan pemilik
> *Editor konfigurasi lama **DIHAPUS**, semua diarahkan ke Pusat Pengaturan.*
Bukan read-only, bukan "tetap ada + tombol".

### 00.3 Yang selesai
| Hal | Hasil |
|---|---|
| Deep-link global `kn-open-config` (pola `kn-open-palette`) | `configDeepLink.js` + `hooks/useConfigDeepLink.js` → `SettingsHub` pilih kelompok, scroll, **sorot kartu 8 detik** (`data-testid="cfg-card-<key>"`, `data-focused="1"`) |
| **8 permukaan editor lama dihapus** | `SettingsPanel` · `TaxConfigPanel` · `PayrollSetupView` · `MakloonPolicyModal` · `ReceivingUomPolicyCard` · `ToleranceCard` · `EnforcementCard` · blok "Strategi Komisi" |
| Pengganti | `ConfigRedirectCard` di 5 layar + tombol yang langsung `openConfig()` |
| Data master TETAP di layarnya | rate insentif · aturan konversi satuan · daftar lot |
| **Wewenang tidak berkurang** | registry punya `permission` + `roles` per kunci → admin 96 · **manager 31** (6 lot + 7 makloon + 18 hr) · sales/warehouse 0 |
| Nav "Pusat Pengaturan" | kini **admin + manager** (manager lihat banner `cfg-limited-rights`, tab Daftar Dampak disembunyikan) |
| Editor tabel terstruktur | `row_shape`+`columns` di registry → `tax.pph_items` & `hr.jkk_classes` jadi BARIS, `hr.ptkp_table` jadi kunci–nilai (bukan JSON mentah) |

### 00.4 🔴 Guardrail yang BERBOHONG — diperbaiki
`audit_config_wiring.py` menilai "bisa diubah user" dengan **grep nama kunci di frontend**. Sejak
Pusat Pengaturan merender registry secara generik, tidak ada nama kunci di kode FE. Saat editor
lama dihapus, audit meledak jadi **77 HIDDEN palsu**.

Sekarang audit **mengimpor `config_registry.py`** (sumber kebenaran) lalu **membuktikan rantai
UI-nya utuh** (`hub_wired()`: nav → route → SettingsHub → SettingEditor). Kalau rantai diputus,
semua kunci registry otomatis kembali HIDDEN.

```
SEBELUM : OK 24 · HIDDEN 77 · DEAD 4
SESUDAH : OK 96 · NOT_USED 9 · HIDDEN 0 · ORPHAN_UI 0 · DEAD 0
```

Bukti-merah wajib: `python scripts/audit_config_wiring.py --self-test` (5 skenario, termasuk
"kartu pengalih TIDAK boleh dihitung sebagai editor kedua").

### 00.5 Invarian & gate baru
`INV-CFG-01..05` di `verify_data_integrity.py` (**183 → 188 invarian**) + 2 gate baru:
```
config_wiring (INV-CFG-01/04, satu sumber kebenaran)
config_wiring SELF-TEST (bukti-merah guardrail)
```
INV-CFG-04 = **tidak ada layar selain Pusat Pengaturan yang boleh menulis konfigurasi**.

### 00.6 Bukti
`bash scripts/gate.sh --full` → **19/19 HIJAU (56s)** · `verify_data_integrity` **188/0/0** ·
`test_g0_config_poc.py` **115/0** · `validate_compliance` **24/0/0** · `check_nav_map` PASS ·
`testing_agent_v3` **iter_171** (backend 6/6 + 11 skenario UI, 0 bug) & **iter_172** (8 user story
sisa, 0 bug).

### 00.7 Titik lanjut berikutnya
**FASE G-1 — Fondasi Amandemen** (`plan.md` §G-1, urutan eksekusi G-11 #1): tidak ada edit senyap;
setiap koreksi dokumen finansial = **dokumen amandemen bernomor** + `reason_code` + approval
berbasis dampak (ambang **configurable lewat registry G-0**), ledger append-only, `refs[]` dua arah,
RBAC `finance_amendment:{propose,approve,admin}`, invarian `INV-AMD-*`.

---

## 0. SESI 2026-07-26 (lanjutan-3) — RESTORE + **EFISIENSI GUARDRAIL** (permintaan pemilik)

### 0.1 Perintah verifikasi sekarang — BERTINGKAT
```bash
bash scripts/gate.sh --quick   # ~1 s   STATIK saja — untuk iterasi cepat
bash scripts/gate.sh           # ~16 s  DEFAULT — 14 gate (statik+seed+invarian+runtime+anti-residu)
bash scripts/gate.sh --full    # ~34 s  DEFAULT + POC fase G-0 / F-1 / D
```
Receipt: `memory/GATE_RECEIPT.md` (17 gate PASS, mode `full`, 34 s).

### 0.2 Latar belakang
Pemilik melaporkan bahwa di repo lain gate/guardrail menjadi **bottleneck** dan **justru
menumbuhkan bug** (“hanya menemukan hantu”), lalu meminta review + efisiensi di repo ini.

**Hasil review (jujur, terukur):** gate di repo ini **BUKAN** bottleneck waktu — total **34 s**
(bukan >20 menit), dan `verify_data_integrity` memberi **183 invarian dalam 1 detik** (rasio
nilai/biaya terbaik). **Tidak ada gate keamanan/uang yang dipangkas.**
**Tetapi 5 patologi yang disebut pemilik memang ada** dan sudah ditutup.

### 0.3 Patologi yang ditutup

| # | Patologi | Bukti konkret | Perbaikan |
|---|---|---|---|
| 1 | **Guardrail-nya sendiri bug → temuan hantu** | `validate_compliance.py` `check_imports` memakai `imp_line.split(' as ')[-1]` tanpa membuang komentar ⇒ alias jadi `"_dr  # Fase A · R7 …"` ⇒ 3 warning “unused” padahal `_dr` dipakai 2× | Ganti ke **AST**. Hantu hilang; lalu ketemu **39 import mati NYATA** (silang-validasi `ruff F401` = 39) → dibersihkan |
| 2 | **Check duplikat** | `check_monster_files()` = fotokopi `check_file_sizes()` (limit/glob/ambang sama) ⇒ 10 dari 19 warning fakta yang sama | `check_monster_files` **dihapus** |
| 3 | **Aturan mengunci desain** | `MAX_LINES_COMPONENT=500` = FAIL keras; `PurchaseReturns.jsx` **498/500** ⇒ +3 baris = MERAH ⇒ dipaksa split artifisial | **WARN di limit, FAIL di limit × 2** |
| 4 | **Gate menyuruh memalsukan RBAC** | Invarian “admin lihat semua menu” mutlak; `SESSION_HANDOFF §5` lama menyuruh *“longgarkan `roles` item yang sudah ada”* agar hijau | Opt-out eksplisit **`adminExempt: true`** di `navStructure.js` — lulus **dan dilaporkan** |
| 5 | **Dua sumber kebenaran** | `check_entity_registry_sync` bilang “tidak ada di ENTITY_REGISTRY.md” tapi **tak pernah membaca file itu** (allowlist hardcode 79 entri) | Kini **membaca `ENTITY_REGISTRY.md`** (203 nama) + tokenize anti-komentar |
| 6 | **Gate MERUSAK data demo** (nol cleanup) | Terukur dari seed bersih, **1× gate**: `SO-0006` `reserved/Reserved` → `cancelled/Cancelled` · `songket/wh_jakarta` reserved 20→10 · `lurik/wh_bandung` reserved 40→0 · `inventory_movements` 38→40 · `audit_logs` 6→16 · `vendor_bills` +1 · `ar_receipts` +1 | **`DbSnapshot` + `run_with_restore`** di 6 gate runtime ⇒ **NOL residu** (terbukti 3 putaran, jumlah **dan** nilai) |
| 7 | **Tak ada yang menjaga penjaganya** | 183 invarian semuanya memeriksa konsistensi internal; tak satu pun bertanya “apakah gate merusak data?” | Gate baru **`INV-GATE-01`** (`scripts/gate_residue.py`) — langsung membuktikan diri dengan menemukan residu `vendor_bills`/`ar_receipts` |
| 8 | **Ledger mutasi tak terjaga** | Kebocoran no.6 lolos karena semua invarian stok memeriksa `inventory_balances` | Lapisan baru **`INV-MOV-01..04`** ⇒ **179 → 183** invarian |
| 9 | Gate selalu penuh walau edit dokumen | 34 s untuk perubahan 1 baris | Gate **bertingkat** `--quick`/default/`--full` |
| 10 | 151 skrip uji (62.010 baris) tanpa daftar isi | agen baru tak tahu mana relevan | **`tests/INDEX.md`** + **`scripts/INDEX.md`** + 10 skrip orphan → `scripts/_legacy/` |

### 0.4 🔴 BUG PRODUK yang ketemu BERKAT guardrail diperbaiki
`routers/hr.py:346` membaca **`db.hr_kpi_entries`** — koleksi dengan **NOL penulis** di seluruh
repo (0 dokumen). Koleksi sebenarnya **`hr_kpi`** (6 dok, field `employee_id`/`period`/`score`).
Akibatnya seksi **KPI di profil karyawan SELALU KOSONG tanpa error**. Sudah diperbaiki.
`hr_kpi_entries` **tidak dipakai lagi — jangan dihidupkan kembali.**

### 0.5 Yang SENGAJA TIDAK dilakukan
Invarian `Σ inventory_movements == on_hand_qty` **diuji dan DITOLAK**: pada seed bersih **14 dari
22** pasangan (produk, gudang) tidak rekonsiliasi, bahkan ada balance dengan **nol** mutasi
(`prod_ulos_batak/wh_jakarta` on_hand 95). Ledger mutasi di repo ini **ilustratif, bukan
otoritatif** ⇒ menambahkannya = gate palsu yang selalu merah.

### 0.6 Aturan baru menulis guardrail (lihat `scripts/INDEX.md` §5)
1. Harus menjawab: *uang / data / keamanan / alur produk*. Kalau tidak → alat ad-hoc, bukan gate.
2. **Jangan grep teks mentah** untuk menilai kode — pakai **AST**. (2 bug guardrail lahir dari ini.)
3. Satu fakta = satu laporan.
4. **Gate runtime WAJIB `run_with_restore(main)`** — `INV-GATE-01` memerahkan bila lupa.
5. Satu sumber kebenaran — **baca dokumennya**, jangan salin daftarnya ke skrip.
6. Sertakan **bukti-merah** (buktikan gate MEMERAH saat pelanggaran disuntik).
   *Contoh nyata:* helper `_py_code_only` versi pertama menggabungkan token dengan spasi
   sehingga `db.x` → `db . x` dan deteksi **selalu lulus** — hanya ketemu karena diuji-negatif.
7. Batas gaya (panjang file/naming) = **WARN**, bukan FAIL.

### 0.7 Status FASE G-0 (titik lanjut berikutnya)
- **Backend: LENGKAP & TERBUKTI** — `python backend/test_g0_config_poc.py` → **115/0**;
  14 endpoint `/api/config/*`; `audit_config_wiring` **ORPHAN_UI = 0**.
- **Frontend: BELUM TERSAMBUNG** — `features/settings/config/{SettingCard,ConfigDrawers,ImpactPicker,SettingEditor,configApi}`
  sudah ada tetapi **nol impor**; belum ada view “Pusat Pengaturan” di `navStructure.js`.
- Sisa gap: **33 setting HIDDEN** (dipakai mesin, tanpa UI) · **4 key DEAD**
  (`hr.ptkp_table.K0..K3`) belum ditandai `not_used` · 13 editor lama belum jadi deep-link.

---


## 0. SESI 2026-07-25 (LANJUTAN REPO `bananamakaja/kn`) — FASE A DIVERIFIKASI · PS-21 · FASE B

| Item | Status | Bukti |
|---|---|---|
| Restore repo + dependensi + data demo | ✅ | `python seed_realistic.py` · gate `seed_realistic` PASS |
| **Verifikasi Fase A** (klaim dokumen vs container) | ✅ | `backend/test_fase_a_poc.py` **53/0** |
| **Gap Fase A ditutup** (jalur non-form: seed · import CSV · SKU custom MTO · snapshot roll) | ✅ | INV-DOMAIN-02/04/05 hijau pada DB yang baru di-seed (sebelumnya MERAH) |
| **PS-21** notifikasi operasional + repeat/restock 1-klik | ✅ | `backend/test_ps21_poc.py` **43/0** · `docs/KN_21_...md` |
| **Fase B** konversi satuan global + toleransi configurable | ✅ | `backend/test_fase_b_uom_poc.py` **49/0** · `docs/KN_22_...md` |
| Invarian & gate | ✅ | `verify_data_integrity.py` **158 PASS / 0 FAIL / 0 WARN** · `scripts/gate.sh` **12/12 HIJAU** |

**Uji cepat (urut):**
```bash
cd /app && python seed_realistic.py
python scripts/seed_ar_due_soon_demo.py --run     # kondisi piutang H-3/H-1/H/H+1 (data nyata)
python backend/test_fase_a_poc.py                 # 53/0
python backend/test_ps21_poc.py                   # 43/0
python backend/test_fase_b_uom_poc.py             # 49/0
python scripts/verify_data_integrity.py           # 158/0/0
bash scripts/gate.sh                              # 12/12
bash scripts/rebuild_frontend.sh                  # WAJIB setelah ubah frontend/src
```
**Menu baru:** Produk & Harga → **Konversi Satuan** · SO detail → panel **Pendingan &
Repeat/Restock** · Penjadwal & Notifikasi → **12 job** (3 baru PS-21).

**Fase berikutnya (menunggu keputusan):** Fase C (lot kelas satu · D-10) → Fase D (wizard
makloon multi-tahap + klaim) → Fase E/F/G/H (KN_18 §7 & §A.5).

---

## 1. RINGKAS STATUS PROGRAM

| Fase | Modul | Status |
|---|---|---|
| Phase 5–6 | R5.6 Margin · R6.1 Bank Reconciliation | ✅ DONE & teruji |
| Phase 7 | R6.2 Fixed Assets & Penyusutan (+ disposal gain/loss) | ✅ DONE & teruji |
| Phase 8 | R6.3 Budget Control penuh | ✅ DONE & teruji |
| Phase 9 | R6.4 Produksi In-House (BOM & Work Order) | ✅ DONE & teruji |
| Phase 10 | R6.5 Scheduler (APScheduler) + Notifikasi + kanal WhatsApp | ✅ **DONE & TERUJI** |
| **Phase 11** | **R6.6 Ringkasan Harian · Eskalasi Bertingkat · Filter Bell** | ✅ **DONE & TERUJI** |

Bukti terakhir: POC R6.5 **67/0** · POC R6.6 **66/0** · integritas **144 PASS / 0 FAIL / 0 WARN** ·
`scripts/gate.sh` **12/12 HIJAU** · `testing_agent_v3` **iter_160** (R6.5: backend 95/95, 10/10
user story) & **iter_161** (R6.6: backend 28/28, 23 skenario UI lintas 4 role, 0 bug).

**Semua fase di `plan.md` (Phase 5–11) SELESAI.** Fase berikutnya menunggu keputusan user.

---

## 2. YANG DIKERJAKAN DI SESI INI

### 2.1 Restore repo
- `github.com/jananabamalam/kn` (commit `5423235`) di-clone & di-rsync ke `/app` **tanpa** menimpa
  `.env` container. `pip install -r backend/requirements.txt` (skip `emergentintegrations` &
  `litellm` — bentrok resolusi, sudah ada di base image; **APScheduler 3.11.3** terpasang),
  `yarn install` (⚠️ `leaflet` wajib), `yarn build`, `python seed_realistic.py`.

### 2.2 R6.5 (Phase 10) — diverifikasi & 5 celah ditutup
Kode R6.5 sudah ada di commit tetapi belum pernah diverifikasi. Temuan yang ditutup:
1. **BUG zona waktu** — waktu tampil UTC padahal jadwal WIB → `fmtWaktu` eksplisit
   `timeZone: "Asia/Jakarta"` + sufiks WIB.
2. **BUG label ganda** — `schedule_label` tampil 2× untuk role tanpa hak configure.
3. **GAP RBAC nav** — manager punya hak `view+run` tetapi menu admin-only → `settings-hub`
   + tab "Penjadwal & Notifikasi" dibuka untuk admin **+ manager** (kontrol configure disabled).
4. **GAP coherency** — param `runs?job_id=` tak dipakai FE → filter riwayat per job.
5. **GAP coherency** — field `job.link` tak dipakai FE → tombol deep-link "Buka <modul>".
Tambahan: invarian **SCH-1..SCH-4**, dokumentasi ENTITY_REGISTRY, label gate diperbaiki (142).

### 2.3 R6.6 (Phase 11) — 3 fitur permintaan user
1. **Ringkasan Harian** (`services/digest_service.py` + job `daily_digest` 08:30 WIB):
   alert hari ini dikelompokkan per jenis → **1 pesan WhatsApp per penerima per hari**
   (dedupe `digest:<hari>|<nomor>`). Mode `wa.delivery_mode` = `instant` | `digest`;
   `wa.critical_bypass` (default ON) menjaga alert **critical** tetap terkirim seketika.
   Endpoint pratinjau `GET /api/scheduler/digest-preview?role=`.
   **Efek nyata di data demo: 52 pesan/hari → 13 pesan/hari (7 ringkasan + 4 critical + 2 eskalasi).**
2. **Eskalasi Bertingkat** (`services/escalation_service.py` + job `escalation_scan` tiap 2 jam):
   alert **belum dibaca** > `after_hours` (default 8) & severity ≥ ambang dinaikkan ke atasan
   (**sales/warehouse → manager → admin**, berhenti di admin). Notifikasi eskalasi = notifikasi
   biasa bertingkat **critical**, judul `ESKALASI: …`, deep-link + aksi inline induk disalin.
   Induk ditandai `escalation_level=1` ⇒ tidak pernah dieskalasi dua kali. Kebijakan di
   `system_settings.scope="alerts".escalation` {enabled, after_hours 1–72, min_severity, max_level 1–3}.
3. **Filter Bell** (`components/NotificationCenter.jsx`): chip tingkat kepentingan
   (Semua/Penting/Perhatian/Info), toggle "Belum dibaca", dropdown jenis (native `<select>`
   agar tidak menutup panel), hitungan "Menampilkan X dari Y", tombol Reset, badge **ESKALASI**.

### 2.4 🔴 BUG PENTING yang diperbaiki (ditemukan lewat regresi POC R6.5)
**Scheduler mati permanen setelah hot-reload.** Lock single-instance masih terlihat "segar"
(heartbeat < 180s) padahal PROSES pemegangnya sudah mati (uvicorn `--reload` mengganti worker)
→ worker baru menolak menjadwalkan job **dan tidak pernah mencoba lagi** (`running=false`,
`next_run` kosong, alert otomatis tidak jalan sama sekali).
**Fix di `services/scheduler_service.py`:**
- `_owner_alive()` — lock milik PID yang sudah mati **di node yang sama** langsung diambil alih.
- `_lock_retry_loop()` — retry tiap **30 detik** sampai scheduler benar-benar menyala.
- `_boot_scheduler()` — dipisah agar bisa dipakai saat startup maupun saat ambil-alih.
Regresi ditutup POC R6.6 bagian **I1–I6** (termasuk cek "pemegang lock adalah proses HIDUP").

### 2.5 Tambahan
- Invarian **SCH-5** (rantai eskalasi) & **SCH-6** (ringkasan + konfigurasi kanal) → integritas **144**.
- `scripts/seed_escalation_demo.py` — menggeser umur beberapa alert **NYATA** (default 20 jam,
  `dedupe_key` disesuaikan agar SCH-2 valid) lalu menjalankan job eskalasi, supaya fitur
  berbasis waktu terlihat di UI tanpa menunggu. Isi alert tidak dipalsukan.
- POC R6.5 dibuat tahan-kondisi (tidak lagi mengasumsikan DB baru di-seed) + ekspektasi 9 job.

---

## 3. ARSITEKTUR ALERT (R6.5 + R6.6)

```
APScheduler (AsyncIOScheduler, zona Asia/Jakarta) ← services/scheduler_service.py
  ├── lock single-instance: system_settings.scope="alerts".lock
  │     TTL 180s · heartbeat 60s · takeover bila PID mati · retry loop 30s
  ├── 9 JOB (jadwal dapat diubah user via API, TANPA deploy):
  │     ar_overdue 08:00 · ap_due 08:05 · depreciation_due 08:10 · budget_alert 08:15 ·
  │     production_stalled 08:20 · ops_stalled /4jam · event_scan /4jam ·
  │     escalation_scan /2jam (R6.6) · daily_digest 08:30 (R6.6)
  ├── setiap eksekusi → sys_scheduler_runs (status, created, wa_queued, durasi, detail, error)
  ├── alert_service → create_notification(dedupe_scope="day") → koleksi `notifications`
  │     └── wa_alert_service.push_notification()
  │           ├── mode instant → sys_wa_outbox (1 pesan/alert/nomor/hari)
  │           └── mode digest  → DITEKAN (kecuali critical + critical_bypass)
  ├── escalation_service → notifikasi ESKALASI (critical) ke atasan + tandai induk
  └── digest_service     → 1 pesan RINGKASAN/penerima/hari → sys_wa_outbox
```
UI: **Pengaturan & Master Data → Penjadwal & Notifikasi** (tab Job Terjadwal + panel Eskalasi ·
Riwayat Eksekusi + filter per job · WhatsApp: provider, mode pengiriman, pratinjau ringkasan, Outbox)
dan **bell** di header (filter jenis/severity/belum dibaca + badge ESKALASI).

---

## 4. CARA UJI CEPAT (untuk agen berikutnya)

```bash
cd /app
python seed_realistic.py                        # reset data demo
python scripts/verify_data_integrity.py         # harus 144 PASS / 0 FAIL / 0 WARN
python test_r6_5_scheduler_poc.py               # harus 67 / 0
python test_r6_6_digest_escalation_poc.py       # harus 66 / 0
python test_r6_4_production_poc.py              # harus 44 / 0
bash scripts/gate.sh                            # harus SEMUA GATE HIJAU (12/12)

# agar rantai eskalasi terlihat di UI (fitur berbasis waktu):
python scripts/seed_escalation_demo.py 2 20
```
UI: preview URL → quick-login (Admin/Sales/Manager/Warehouse, **langsung login**) →
**Pengaturan & Master Data** → **Penjadwal & Notifikasi**. Kredensial: `memory/test_credentials.md`
(semua password `demo12345`).

---

## 5. CATATAN PENTING UNTUK AGEN BERIKUTNYA

- 🔴 **Frontend TIDAK punya hot reload.** Preview dari bundle statis `frontend/build`
  (`yarn start` === `node static_server.js`). Setelah mengubah `frontend/src`:
  `bash /app/scripts/rebuild_frontend.sh`. `build/` gitignored → **selalu build ulang setelah clone.**
- ⚠️ **KOREKSI 2026-07-26 (instruksi lama di baris ini SALAH — jangan diikuti).**
  Teks lama: *“`navStructure.js` mepet batas guardrail utility 380 baris. Menambah item nav
  khusus non-admin MELANGGAR gate `check_nav_map` — longgarkan `roles` item yang sudah ada
  bila perlu.”* Itu menyuruh **memalsukan RBAC** agar gate hijau. Sekarang:
  - Batas panjang file = **WARN**, FAIL hanya di **limit × 2** (380 → keras 760). Tidak perlu
    memecah `navStructure.js` secara artifisial lagi.
  - Menu **khusus satu role** itu SAH: tandai `adminExempt: true` pada item tersebut.
    `check_nav_map` akan LULUS dan melaporkannya eksplisit. **JANGAN** melonggarkan `roles`.
- `KNSelect` = combobox (Popover+cmdk) bila opsi ≥ 6, Radix Select bila < 6. Untuk Playwright:
  klik trigger lalu `{testId}-option-{value}`. **Filter jenis di bell memakai `<select>` native**
  (disengaja: dropdown portal akan menutup panel bell).
- Waktu di UI scheduler WAJIB dirender zona `Asia/Jakarta` (`fmtWaktu`) — server/browser = UTC.
- Scheduler bisa dimatikan saat debugging: `KN_DISABLE_SCHEDULER=1`.
- Bila `GET /api/scheduler/jobs` melaporkan `running=false` + `next_run` kosong: cek
  `system_settings.scope="alerts".lock` (owner PID hidup?) — mekanisme takeover + retry 30s
  seharusnya menyalakan otomatis; log ada di `/var/log/supervisor/backend.*.log` (prefix `[scheduler]`).
- Setelah perubahan skema/koleksi: `python seed_realistic.py` lalu gate lengkap.
- Jangan ubah `.env` (`REACT_APP_BACKEND_URL`, `MONGO_URL`). Pakai UUID & `datetime timezone.utc`.
- Setiap koleksi baru WAJIB dicatat di `ENTITY_REGISTRY.md` + domain prefix + scoping `entity_id`.

---

## 6. KONDISI PENGATURAN ALERT SAAT INI (siap dipakai user)

- Kanal WhatsApp: **aktif**, provider **`simulated`** (pesan tercatat di Outbox, TIDAK dikirim
  ke jaringan) — sesuai keputusan user; kredensial kosong.
- Mode pengiriman: **`digest`** (Ringkasan Harian 08:30 WIB) + **critical bypass ON**.
- Ambang kirim: `warning` (Perhatian & Penting).
- Eskalasi: **aktif**, batas **8 jam**, ambang `warning`, kedalaman **2 tingkat**.
- Data demo: 9 job aktif · ±33 notifikasi hari ini · 7 ringkasan · **4 eskalasi nyata**
  (2 → manager, 2 → admin).

## 7. LANGKAH BERIKUTNYA (menunggu keputusan user)
1. **Aktivasi WhatsApp nyata**: Fonnte (1 token) atau Meta Cloud (`phone_number_id` +
   system-user access token + template UTILITY disetujui, 2 variabel body).
2. Kandidat fase lanjutan `MASTER_ROADMAP.md`: EPIC 0 (IA hygiene) · EPIC 1 (Role Experience &
   Sales Home) · EPIC 2 (Master Kategori + snapshot SO) · EPIC 3 (Costing WAC + AR receipt
   ledger) · EPIC 4 (Incentive Engine v2).
3. Kandidat lanjutan alert (belum diminta): quiet-hours pengiriman WA, ringkasan mingguan
   manajemen, "snooze" alert per user.

---

## 8. KREDENSIAL UJI
Semua password: **`demo12345`** — `admin@` · `sales@` · `sales2@` · `manager@` ·
`warehouse@` · `warehouse2@` `kainnusantara.id`.
Login API: `POST /api/auth/login` → respons memakai key **`token`** (bukan `access_token`).

---
## SESI 2026-08-10 (repo `ajajaabahayaja/KN`) — **FASE 2: DAFTAR HARGA PER PELANGGAN (F1b/D-14) DITUTUP**

Titik henti yang diwariskan: *"Found a real bug in CSV number parsing (Indonesian
thousand separators vs decimal points). Fixing it."* — bug NYATA: `.replace(".","")`
membuat hasil ekspor sistem `126540.00` terbaca **12.654.000** (100× lipat). Kini
`_parse_money` membaca dua gaya sekaligus dan diuji eksplisit di POC.

### Keputusan pemilik (dikonfirmasi di sesi ini)
1. Harga pelanggan di bawah **harga PT/HPP** wajib persetujuan manajer, **memakai
   logika/mesin Harga Khusus yang sudah ada — jangan duplikasi**.
2. POS memakai harga langganan otomatis saat kasir memilih pelanggan (bawaan harga PT).
3. admin/manager kelola · sales hanya lihat. 4. Format CSV bawaan.

### Yang dibangun (ringkas)
- **SATU definisi batas bawah harga** (`services/price_guard_service.py`) dipakai
  Daftar Harga per Pelanggan **dan** layar Harga Khusus + 3 sakelar di Pusat Pengaturan.
- **SATU mesin persetujuan**: harga di bawah batas → record `pending_approval` +
  pengajuan `price_approvals` (`source="customer_pricelist"`). Bagian bersama dipindah
  ke `services/price_approval_service.py` supaya router tidak menyalin logika.
- **SATU resolver harga** (`customer_price_service.resolve_many`) dipakai SO, POS, grid:
  harga khusus → pelanggan → PT → umum. FE memakai `hooks/useEffectivePrices.js`
  (1 panggilan, dulu ≤40 panggilan/render dan harga dasarnya harga UMUM).
- Layar baru **Daftar Harga per Pelanggan** + **bilah pilih pelanggan di POS** +
  lencana sumber harga di kartu POS/keranjang/checkout/baris SO.
- **Endpoint baru `POST /api/price-approvals/{id}/revoke` ("Akhiri Aturan")** —
  menutup celah: aturan `approved` dulu TIDAK BISA dihentikan (hapus 409, ubah hanya draf).

### Jebakan/temuan untuk sesi berikutnya (BACA INI)
- **POC yang gagal saat dijalankan ULANG adalah sinyal, bukan gangguan.** Kegagalan
  jalan-ulang POC F1b membongkar celah revoke di atas. POC sekarang idempotent (94/94, 3×).
- **Agen uji memakai navigasi hash (`#/view`)** dan menyimpulkan "navigasi rusak".
  Aplikasi ini TIDAK pernah memakai hash routing — navigasi berbasis state lewat sidebar
  (`onNavSelect`). Satu-satunya jalur URL: `/verify-document/:id`. Verifikasi UI harus
  lewat klik `nav-group-{groupId}` → `nav-{id}`.
- **Agen uji pernah menimpa `/app/backend_test.py`** (uji R&D milik repo). Sudah
  dipulihkan dari repo; skrip agen dipindah ke `backend_test_customer_prices.py`.
  Ingatkan agen uji memakai nama berkas baru.
- Menambah view `cs-*` yang SUDAH nyata: WAJIB daftarkan ke `LIVE_CS_VIEWS` di
  `config/navigationConfig.js`, kalau tidak layar dirender BERSAMA kartu "Segera Hadir".
- Pelanggan demo **"Toko Kain Sejahtera" terblokir kredit** (gate lama) — untuk uji
  membuat pesanan pakai "Butik Bali Indah" / "Fashion Bandung Kencana" / "Tekstil Medan Jaya".
- Batas bawah = harga PT/HPP → **hampir semua DISKON butuh persetujuan**. Itu memang
  permintaan pemilik. Kalau terasa terlalu ketat: kendurkan lewat Pusat Pengaturan
  (`pricelist.customer_price_floor` = `hpp` saja, atau naikkan toleransi %).

### Bukti
POC 94/94 (3× tanpa seed ulang) · `gate.sh` HIJAU · `verify_api_contract` 0/0 ·
`check_nav_map` PASS · `audit_i18n_id` 0 · build FE bersih · testing_agent_v3
iter 207/208/209 backend 100% · verifikasi mandiri browser: POS→Pesanan
**KSC/SO-00013 Rp 3.220.000 = 322.000 × 10, `price_source="customer"`**.

### Berikutnya
Fase 3 **BOM Printing** (`cs-bom`) → Fase 4 **BI Sales + BI Stok** (`cs-bi-sales`, `cs-bi-stock`).

---
## SESI 2026-08-10 (lanjutan · repo `akakanahauaha/kn`) — **FASE E-3 DITUTUP**

Titik henti yang diwariskan: di tengah pembersihan `AdminView.jsx` (tab `Entities`/`Users`
dipindah ke layar baru), tepat setelah rantai ternary `records` diganti tabel eksplisit.
Permintaan pemilik: *"verifikasi dan lanjutkan"*.

### 0. Pemulihan lingkungan (wajib diulang tiap clone)
Kontainer datang KOSONG (template), repo dipulihkan dari GitHub lalu:
`pip install -r backend/requirements.txt` (tanpa `emergentintegrations`/`litellm`) ·
`yarn install` · `python seed_realistic.py` · `bash scripts/rebuild_frontend.sh`.
`memory/test_credentials.md` di-.gitignore → **ditulis ulang** (lihat berkas itu).
⚠️ Koreksi kredensial: akun ber-home **CV Kanda Suka** adalah **`sales3@`**
(bukan `sales2@`/`warehouse2@` seperti tertulis di catatan lama).

### 1. Verifikasi: dua gate MERAH warisan sesi sebelumnya (bukan diakali, diperbaiki)
- `guard:entity_label` (INV-UI-02) — `AccountFormDrawer.jsx:112` memakai
  `res.home_entity_id` sebagai cadangan teks, jadi pengguna bisa melihat `ent_ksc`.
  → lewat `entityFull()` dari `utils/entityLabel.js`.
- `audit_i18n_id` — `AccountList.jsx` "Login terakhir" → **"Terakhir masuk"**.

### 2. CACAT BARU yang ditemukan & ditutup (ini inti sesi ini)
```
POST /api/customers   header X-Entity-Id: all   →  200 OK
dokumen mendarat di   entity_id = "ent_ksc"          ← badan usaha HOME, tanpa pesan
```
Admin yang sedang melihat **gabungan** membuat dokumen, dan sistem memilih buku badan
usahanya **diam-diam**. Ini cacat yang dicatat `plan.md` §1.2 dan **user story 7**.

**Obatnya: `backend/entity_write_guard.py` (middleware, deny-by-default).**
Aturannya satu kalimat: *membuat sesuatu yang baru butuh memilih satu badan usaha;
menindak dokumen yang sudah ada tetap boleh karena dokumen itu sudah punya badan usahanya.*
- Menyala hanya bila header `X-Entity-Id: all` + metode tulis.
- Template rute dicocokkan memakai **mesin routing Starlette yang sama** (bukan regex
  karangan) → keputusan pagar tidak pernah beda dari rute yang benar-benar jalan.
- Rute ber-parameter jalur (`/api/x/{id}/aksi`) BOLEH. Akar koleksi DITOLAK 409.
- `GROUP_LEVEL_EXACT` = daftar eksplisit dengan alasan per baris: master **BERSAMA**
  (products/uoms/product-categories/document-templates/warehouses/color-library/…),
  **tingkat grup** (entities/users/permissions/settings/config/scheduler/WA),
  **antar-entitas** (`/api/interco/*`, `transfers/inter-company`, konsolidasi),
  dan **pratinjau/pemeliharaan** (preview-*/pdf/labels/scan/run-*).
- **Deny-by-default disengaja**: rute tulis baru yang lupa didaftarkan akan MENOLAK
  dengan pesan menuntun, bukan menulis ke buku yang salah. Untuk urusan uang,
  gagal-berisik jauh lebih murah daripada sukses-salah.

### 3. Sisi layar (supaya pengguna tak pernah menabrak pagar tanpa tahu)
- `components/ScopeReadOnlyBanner.jsx` — pita "Anda sedang melihat gabungan semua badan
  usaha" + **pilih-cepat satu klik** (`scope-pick-{entityId}`).
- `components/EntitySwitcher.jsx` ditulis ulang: tag **"hanya lihat"** pada mode gabungan,
  **⭐ Utama** pada badan usaha home, badan usaha **terarsip disaring**, **pencarian
  otomatis bila > 8** badan usaha, semua label lewat `entityLabel` helper.
- `context/EntityScopeContext.jsx` + `utils/writeScope.js` — SATU definisi "boleh
  menyimpan?" untuk semua layar (`useEntityScope()`), dipakai mematikan tombol di
  `AdminView` (Simpan Pelanggan), `CartPanel` (Buat SO), `CheckoutDrawer` (POS).
- `services/apiClient.js` — interseptor: 409 pagar SELALU muncul sebagai toast menuntun
  + event `kn:scope-blocked` (pita berdenyut). Galat tetap dilempar ulang (INV-UI-03).
- Konsistensi: breadcrumb menyebut cakupan (`page-scope-label`), empty state memakai
  `scopeSuffix()` ("Belum ada pesanan aktif **untuk CV Kanda Suka**."), daftar badan
  usaha menambah kolom **mata uang** & **#gudang** (`readiness.warehouse_count`).

### 4. Bukti
`bash scripts/gate.sh` **SEMUA GATE HIJAU (30 gate, 36 s)** · POC baru
`backend/test_core_e3_write_guard_poc.py` **26/26** (3× berturut-turut, **nol residu**,
memulihkan data demo yang disentuhnya) · `python -m entity_write_guard --self-test`
**17/17** · `pytest backend/tests/test_g6b_poc.py` **15/15** (antar-entitas tidak regresi) ·
`testing_agent_v3` iterasi **211: backend 27/27 · frontend 21/21 (100%)`.
Dua gate baru terdaftar di `scripts/gate.sh`: `guard:write_scope SELF-TEST` (statik) dan
`POC FASE E-3` (runtime).

### 5. Jebakan untuk sesi berikutnya (BACA)
- **Agen uji meninggalkan 5 dokumen residu** (`Test Customer/UOM/Category …`) — sudah
  dibersihkan tangan. Selalu periksa residu setelah memanggil agen uji, jangan percaya
  laporan "100%" untuk urusan kebersihan data.
- Menambah endpoint tulis baru? Kalau itu **akar koleksi tingkat grup**, daftarkan di
  `GROUP_LEVEL_EXACT`; kalau tidak, ia akan 409 di mode gabungan (memang begitu maunya).
- `AdminView.jsx` **tidak lagi** menerima prop `users`/`entities`. Kalau butuh daftar
  akun, layarnya sekarang **"Badan Usaha & Akses"** — jangan hidupkan pintu kedua.
- Rantai ternary panjang untuk memilih data per tab adalah kelas bug tersendiri: dulu ia
  **jatuh ke `users`** untuk tab tak dikenal sehingga tab "Integrasi AI" menampilkan
  daftar pengguna. Sekarang tabel eksplisit `RECORDS_BY_TAB`.

### 6. Berikutnya
**FASE E-4 — master data & konfigurasi per badan usaha**: gudang `sharing_mode`
(`shared`/`dedicated` + `entity_ids`) dan penyaringan di semua pemilih gudang · kop surat
& template dokumen per badan usaha · tarif insentif/aturan persetujuan/syarat pembayaran/
kategori biaya/kebijakan retur per badan usaha · 47 entri Pusat Pengaturan yang masih
hanya-global. Catatan: bagian E-4 "mode Semua Entitas menulis diam-diam" **sudah tertutup**
di sesi ini oleh pagar tulis.

---
## SESI 2026-08-14 (repo `oyahubnalaja/KN`) — **GATE MERAH G-6b DITUTUP DI AKARNYA**

Titik henti yang diwariskan: `gate.sh --full` **MERAH** pada 1 dari 51 gate —
`POC FASE G-6b` → `test_c1 … AssertionError: butuh satu pasangan PT dengan utang terbuka
(assert [])`. Permintaan pemilik: *"lanjutkan development"* → **gate HIJAU dulu, lalu FASE E-9**.

### 0. Pemulihan lingkungan (wajib diulang tiap clone)
Kontainer datang KOSONG (template). Repo dipulihkan dari GitHub ke `/app`
(`.env` backend/frontend TIDAK ditimpa — keduanya di-.gitignore), lalu
`bash .restore_env.sh` (pip · yarn · `seed_realistic.py` · `scripts/rebuild_frontend.sh`).
`memory/test_credentials.md` di-.gitignore → **ditulis ulang** (lihat berkas itu).

### 1. Diagnosis: kegagalan-hanya-di-gate itu SINYAL, bukan gangguan
POC G-6b lulus **15/15 sendiri**, dan tetap lulus bila dijalankan **sesudah** POC G-6 —
jadi bukan G-6 pelakunya. Bisect blok gate (13 POC `--full` satu per satu, lalu blok
gate *default*) menunjukkan: **sesudah blok default, `open_payable` 1 → 0**. Barisnya
tidak berubah nilai — barisnya **berganti arti**:
```
sesudah seed  : ica_ent_kanda_ent_ksc  role=payable     out=1.766.010   ← utang nyata
sesudah gate  : ica_ent_kanda_ent_ksc  role=receivable  out=0           ← arti tertimpa
```

### 2. Akar masalah (P0) — `KN-G6-ICA-CLOBBER`
Id baris saldo dulu `ica_{X}_{Y}` **tanpa penanda peran**, jadi *piutang arah A→B* dan
*utang arah B→A* **menempati satu dokumen**. Siapa pun yang dihitung terakhir menang:
```
_update_account_balance(A,B) → ica_A_B = piutang ,  ica_B_A = utang
_update_account_balance(B,A) → ica_B_A = piutang ,  ica_A_B = utang   ← menimpa
```
Pemicunya alur bisnis yang **normal**, bukan kasus aneh:
1. **Permintaan Internal** ("stok saya habis, kirim dari PT sebelah" — POC E-7d) menerbitkan
   transaksi arah balik. **Satu DRAF saja cukup**; tidak perlu ada uang berpindah.
2. **Pinjaman & pindah aset antar-PT** — `interco_money_service.refresh_pair_exposure`
   memanggil KEDUA arah berurutan, jadi panggilan kedua selalu menghapus yang pertama.

Dampaknya: utang **Rp 1.766.010** hilang dari layar *Saldo Antar-PT* **tanpa pesan**, dan
tombol **Ingatkan** menjawab "Saldo pasangan PT ini sudah nol".

### 3. Celah gate yang ikut ditutup (kenapa ini tidak pernah tertangkap)
- **INV-IC-02/04 "hijau tapi hampa"** — keduanya memeriksa *baris yang ADA*. Baris yang
  **HILANG** tak pernah diperiksa, dan baris sisanya memang konsisten dengan arah lain.
  Dibuktikan: menjalankan versi LAMA `verify_data_integrity.py` pada keadaan uang-hilang →
  **PASS 8 · FAIL 0 · WARN 0**. Sekarang INV-IC-04 dipimpin **arah dagang dari transaksi**
  (setiap arah dengan dokumen terbuka WAJIB punya baris piutang & utang, nominal cocok) dan
  INV-IC-02 menjodohkan lewat `pair_key` + memerah bila dua baris beperan sama berbagi arah.
- **Residu tak terlihat** — POC E-7d meninggalkan dokumen kembar `KANDA/IC-#####` setiap
  `gate --full` (menumpuk permanen) karena `gate_residue.py` belum memantau koleksi antar-PT.
  Residu itulah pemicu tabrakan di gate. POC E-7 sekarang menghapus draf yang ia buat, dan
  WATCH ditambah `interco_transactions/settlements/returns`. `interco_accounts` **sengaja
  TIDAK** dipantau (tabel turunan; kebenarannya kini dijaga INV-IC-04).

### 4. Perbaikan
- `interco_service`: `ica_ar_id()` / `ica_ap_id()` / `ica_pair_key()` → id
  **`ica_{penjual}_{pembeli}_ar`** & **`ica_{pembeli}_{penjual}_ap`**, plus field eksplisit
  `pair_key`, `seller_entity_id/name`, `buyer_entity_id/name`. Baris warisan dibuang saat
  arahnya dihitung ulang.
- `get_account(from, to, role)` **wajib ber-peran** (bawaan `payable` = "berapa utang `from`
  kepada `to`"); endpoint `GET /api/interco/accounts/{from}/{to}?role=payable|receivable`.
- Migrasi idempotent **`scripts/migrate_g6b_ica_directional.py`** (`--dry-run`) memakai mesin
  produksi (bukan rumus tiruan) untuk basis data lama.
- Layar **Saldo Antar-PT**: kolom baru **"Dasar dagang"** (`PT A menjual ke PT B`) +
  `data-testid="interco-acc-dir-{id}"`, dan penjelasan bahwa dua PT yang berdagang **dua arah**
  punya saldo **terpisah** per arah. Tanpa kolom ini, dua baris berbeda arti bisa tampak
  identik (Dari/Ke sama, hanya beda lencana Piutang/Utang).

### 5. Bukti
- **Bukti-merah** POC baru `test_c4_dua_arah_dagang_tidak_saling_menimpa_saldo`: dijalankan
  pada kode ASLI (`git show HEAD:…`) berbunyi
  *"utang Rp 1.766.010,00 tertimpa menjadi Rp 0,00 hanya karena arah balik dihitung ulang —
  inilah KN-G6-ICA-CLOBBER"*; hijau setelah perbaikan.
- `bash scripts/gate.sh --full` **HIJAU 54/54, dua kali berturut-turut** (190s & 188s).
- POC G-6b **16/16** · POC G-6 **21/21** · POC E-7 **57/57** (dengan "dihapus 2 draf · sisa 0").
- `verify_data_integrity` **229 PASS / 0 FAIL / 0 WARN** · build FE bersih · verifikasi
  mandiri di peramban: layar *Saldo Antar-PT* menampilkan 2 baris dengan kolom "Dasar dagang".

### 6. Jebakan untuk sesi berikutnya (BACA)
- **Identitas baris agregat wajib memuat SELURUH dimensinya.** Di sini dimensinya dua —
  *arah dagang* & *peran buku*. Menghilangkan satu dimensi membuat dua fakta berebut satu
  dokumen, dan gejalanya bukan galat melainkan **angka yang tenang-tenang salah**.
- Menulis invarian? Jangan hanya memeriksa *baris yang ada*. Mulailah dari **dokumen sumber**
  lalu tuntut barisnya ADA. Invarian yang tidak bisa menangkap "baris hilang" adalah invarian
  yang tidak bisa memerah.
- `get_account()` tidak lagi bisa dipanggil tanpa peran — kalau menambah pemakai baru,
  sebutkan `role="payable"` atau `"receivable"` secara sadar.
- Deep-link `?view=interco-transactions` bekerja, tetapi `&tab=balances` **belum** membuka
  tab Saldo Antar-PT (harus diklik). Kecil, tapi jangan dianggap navigasi rusak.
- POC fase yang menyentuh koleksi sama tetap TIDAK boleh dijalankan dalam satu pemanggilan
  pytest (xdist paralel) — `gate.sh` sudah memisahkannya.

### 7. Berikutnya
**FASE E-9 — rantai jual → beli internal → retur berantai** (plan.md §E-9 + user story
§"FASE E-9"). Catatan: perbaikan sesi ini adalah **prasyarat** E-9, karena rantai itu
menciptakan transaksi antar-PT **dua arah** pada pasangan PT yang sama.
