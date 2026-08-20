# KN_18 — PROBLEM STATEMENT: FONDASI TEKSTIL (Stage · UoM · Makloon · Sourcing R&D)

> **Status dokumen:** ACUAN (belum dieksekusi). Dokumen ini **bukan** development plan.
> **Peran:** sumber tunggal masalah + aturan desain yang WAJIB dirujuk oleh setiap development
> plan turunan (`plan.md` fase berikutnya).
> Dibuat: 2026-07-25 · Basis: permintaan pemilik sistem + audit kode/DB nyata + riset industri.
> Bahasa: Indonesia. Semua klaim kondisi sistem di §2 **terverifikasi di kode/DB**, bukan asumsi.

---

## §0. CARA PAKAI DOKUMEN INI (untuk agen AI & manusia)

1. **Jangan mengeksekusi §7** sebelum keputusan di §8 dikonfirmasi pemilik sistem.
2. Setiap development plan turunan WAJIB menyebut **ID problem statement** (`PS-xx`) dan
   **ID keputusan** (`D-xx`) yang dipenuhinya. Tidak ada pekerjaan tanpa ID.
3. **ATURAN ANTI-HALUSINASI (mengikat):**
   - **R1 — Tidak ada nilai bebas untuk data terkendali.** Bila sebuah field punya master/enum
     (grade, stage, fabric_type, satuan, proses, warna), input UI **wajib** dropdown yang
     sumbernya API/registry. Dilarang `<input type="text">` untuk field jenis ini.
   - **R2 — Tidak ada field tanpa sumber input.** Setiap field yang tersimpan di koleksi WAJIB
     punya: (a) form/endpoint yang mengisinya, atau (b) rumus/derivasi yang terdokumentasi,
     atau (c) dihapus. Field "hantu" = cacat.
   - **R3 — Satu makna satu tempat (SSOT).** Sebelum menambah field/koleksi, cek §5. Bila
     maknanya sudah ada, **pakai yang ada**; bila berbeda, tulis pembedanya di §5.
   - **R4 — Konversi satuan hanya lewat satu layanan.** Semua konversi (kg↔m↔yard↔ball↔cone↔roll)
     WAJIB lewat `services/uom_service.py`. Dilarang menghitung konversi ad-hoc di router/UI.
   - **R5 — Angka uang & qty wajib mendukung desimal** (`step="any"` / parsing koma-desimal),
     minimal 3 desimal untuk qty, 2 untuk uang; pembulatan hanya di titik penyimpanan akhir.
   - **R6 — Setiap dokumen transaksi wajib punya referensi hulu** (PR → PO/Makloon → Terima),
     dan referensi itu **wajib divalidasi ada**, bukan teks bebas.
   - **R7 — Enum tidak boleh di-hardcode di >1 tempat.** Satu registry backend + satu endpoint
     `GET /api/enums/{name}` yang dikonsumsi FE.
   - **R8 — Setiap perubahan skema wajib**: entri `ENTITY_REGISTRY.md`, invarian di
     `scripts/verify_data_integrity.py`, POC HTTP, dan migrasi idempoten untuk data lama.

---

## §1. RINGKASAN EKSEKUTIF — 10 MASALAH INTI

| # | Masalah inti | Dampak bisnis |
|---|---|---|
| 1 | Rantai **stage** tekstil tidak lengkap (`yarn → grey → finished`, tanpa **PFP/PFD**) dan berupa teks bebas | Makloon multi-tahap tidak bisa dimodelkan; salah tahap = salah HPP |
| 2 | Tidak ada pembeda **woven vs knitting** | Rumus konversi benang→kain salah untuk knit (knit tetap kg, woven pakai GSM×lebar) |
| 3 | **GSM** ada (`gramasi`) tapi tidak diwajibkan mulai stage grey & tidak dipakai sebagai fondasi rumus tenun | Estimasi output tenun tidak bisa diaudit; HPP/unit rawan salah |
| 4 | **Order Makloon 1 langkah 1 mitra** di UI (padahal data model mendukung multi-step) | Proses nyata 3 tahap (tenun→PFP→printing) tidak bisa dijalankan |
| 5 | **Makloon tidak mengenal PR**; PR hanya untuk PO | Kontrol anggaran/otorisasi bocor; ada 2 jalur pengadaan yang tidak setara |
| 6 | **Tidak ada modul kontrak harga** hasil proofing/labdip (yang ada hanya Blanket PO = komitmen qty) | Harga PO tidak berbasis kontrak; tidak ada jejak "harga ini dari mana" |
| 7 | Tidak ada **daftar barang per supplier** + **nama produk versi supplier** | Admin gudang bingung saat surat jalan memakai nama supplier |
| 8 | **Konversi satuan tidak operasional di form** (surat jalan mitra/supplier pakai ball/cone/pick/roll) | Input dipaksa ke satuan KN → angka masuk salah, tidak bisa diaudit |
| 9 | **Grade** teks bebas (`"A"` default), tidak ada set resmi (A, B, BS, A1, A2) & tidak terhubung hasil inspeksi | Data mutu tidak bisa dilaporkan/di-filter; regrade tidak konsisten |
| 10 | **Lot** ada di data tapi tanpa titik input yang jelas & tanpa genealogi | Traceability (shade/dye lot, recall) tidak bisa dipakai |

Tambahan lintas modul: **R&D & Design belum ada** sebagai alur (master data → design/pattern →
labdip/proofing → kontrak → PR → PO), **estimasi vs aktual makloon** belum punya konsekuensi
(potong bon/klaim), dan **lifecycle produk** (masih konsep vs sudah produksi) belum ada.

---

## §2. TEMUAN AUDIT SISTEM SAAT INI (terverifikasi)

| Kode | Temuan | Bukti (file/DB) |
|---|---|---|
| A-01 | `stage` hanya `yarn \| grey \| finished`, tipe `str` **tanpa validasi** | `backend/schemas.py:150` (`ProductPayload.stage`), `:174` (template) |
| A-02 | `products` **tidak punya** `fabric_type`; field ini hanya ada di **product_templates** | `schemas.py:172,190`; inventaris field DB `products` (17 dok) tidak memuat `fabric_type` |
| A-03 | `gramasi` (GSM) **sudah** dipakai catch-weight kg↔meter | `services/uom_service.py:66-95` (`product_kg_per_meter`: `kg_per_meter` eksplisit → fallback `gsm × lebar / 1000`) |
| A-04 | GSM **tidak wajib** & tidak dipakai untuk estimasi output tenun (yarn→grey) | `process_recipe_service.compute_forecast` memakai `yield_factor` manual, bukan GSM |
| A-05 | UI Order Makloon **mengirim tepat 1 step** walau `makloon_orders.steps[]` mendukung banyak | `frontend/.../MakloonOrderCreateModal.jsx:106` → `steps: [{...}]` (hardcoded satu elemen); validasi `:94` "Mitra makloon wajib dipilih" (tunggal) |
| A-06 | Data model makloon **sudah** menyimpan mitra & resep **per step** | `ENTITY_REGISTRY` `makloon_orders.steps[]` = `{seq, process_type, makloon_id, recipe_id, ...}` |
| A-07 | **Tidak ada** relasi PR → Makloon | grep `pr_id\|requisition` di `makloon_order_service.py` = kosong |
| A-08 | **Tidak ada** modul kontrak harga; yang ada Blanket/Contract **PO** (komitmen qty + harga call-off) | `schemas_purchasing.py:80-90` |
| A-09 | **Tidak ada** daftar barang supplier / nama produk versi supplier | grep `supplier_item\|supplier_sku\|supplier_product` seluruh backend = kosong |
| A-10 | `grade` `str` default `"A"`; QC 4-point punya override manual terpisah | `schemas.py:149`, `:453`, `:594` |
| A-11 | `lot` ditulis oleh sistem (fallback `"LOT-MIGRATED"`), dipakai FEFO & tampilan, **tanpa form input** | `services/roll_service.py:180-183, 231, 356, 455` |
| A-12 | Makloon **sudah** menyimpan `expected_output_qty` vs `actual_output_qty` **tanpa** logika selisih/konsekuensi | `makloon_order_service.py:139-140, 259, 353, 372` |
| A-13 | `products.supplier` teks bebas (bukan FK `suppliers`) | `ENTITY_REGISTRY` `products`: "(string only saat ini, bukan FK)" |
| A-14 | `products.harga_pokok` (referensi) berpotensi berbeda dari HPP aktual roll (`inventory_rolls.base_unit_cost`) | dua sumber biaya berbeda; margin memakai roll cost |
| A-15 | `batch_lot_rolls` di `products` **kosong di semua dokumen** (legacy) | inventaris DB: `batch_lot_rolls` list kosong 17/17 |
| A-16 | Blok metadata "smart-search/AI" di registry (`tags`, `media[]`, `specifications`, `ai_meta`) **tidak ada** di schema maupun data | `ENTITY_REGISTRY` menandainya `PROPOSED KN_16` |

**Kesimpulan audit:** pondasi teknis (roll-SSOT, catch-weight, steps[] makloon, expected/actual)
**sebagian sudah ada** tetapi **tidak terhubung ke UI/alur bisnis** dan **tidak dikunci oleh
enum/validasi**. Jadi mayoritas pekerjaan = *melengkapi wiring + mengunci domain*, bukan menulis
ulang dari nol. Ini kabar baik untuk risiko.

---

## §3. RISET INDUSTRI & RUMUS BAKU (dasar keputusan teknis)

### 3.1 Rantai stage kain (dikonfirmasi pemilik + literatur)
```
yarn (benang) → grey/greige (kain mentah) → PFD | PFP (pre-treated) → finished (dyed/printed)
```
- **PFD** = *Prepared for Dyeing*, **PFP** = *Prepared for Printing*: kain sudah di-scouring/
  bleaching sehingga siap menerima warna/print. Keduanya **status semi-finished**, dan literatur
  menegaskan ini **bukan standar global formal** → di ERP harus didefinisikan sebagai
  **status milik perusahaan** (enum internal terkendali), bukan asumsi bersama.
- Implikasi desain: stage **wajib enum tervalidasi** + **matriks transisi** (stage asal → proses →
  stage tujuan) yang dikunci sistem, bukan kebebasan input.

### 3.2 Woven vs knitting — perbedaan yang WAJIB dibedakan sistem
| Aspek | **Woven** (tenun) | **Knitting** (rajut) |
|---|---|---|
| Satuan kendali produksi | meter/yard (panjang) | **kg (berat)** |
| Penggerak konstruksi | EPI, PPI, reed width, yarn count | GSM, lebar, struktur loop |
| Konversi berat↔panjang | dipakai, bukan utama | **sangat lazim** |
| Basis tarif makloon lazim | **per pick** (PPI) atau per meter | per kg |
| Yarn→kain | benang → panjang kain (via GSM & lebar) | benang → **kg kain**, hanya dikurangi susut |

### 3.3 Rumus baku yang akan dipakai sistem
Notasi: `GSM` = gram/m², `W` = lebar kain (meter), `L` = panjang (meter), `kg` = berat.

1. **Berat ⇄ panjang (dua arah, dipakai woven & knit):**
   - `L (m) = kg × 1000 / (GSM × W)`
   - `kg = L × W × GSM / 1000`
   - Contoh pemilik: GSM 200, W 1 m, 1 kg → `1×1000/(200×1) = 5 m` ✔ (cocok dengan contoh Anda)
2. **Yarn → grey (WOVEN):** output panjang = rumus (1) atas berat benang **efektif**
   `kg_efektif = kg_benang × (1 − susut%)`; susut = waste tenun (loom waste + crimp).
3. **Yarn → knit fabric (KNITTING):** output **tetap kg**:
   `kg_kain = kg_benang × (1 − susut%)`. Konversi ke meter **hanya untuk informasi** (rumus 1).
4. **Tarif tenun berbasis pick:** `biaya/meter = PPI × tarif_per_pick`
   → `biaya_total = biaya/meter × meter_output`. (PPI = picks per inch; "pick" = 1 helai benang
   pakan melintang; PPI juga penentu kerapatan kain.)
5. **Dyeing (celup):** basis lazim **per kg** → `biaya = kg_input × tarif_per_kg`.
6. **Printing:** basis lazim **per meter/yard** (+ biaya tetap seperti screen/repeat bila ada).
7. **Ekuivalensi tarif:** apa pun basis kontrak (pick/kg/meter/yard/ball/roll), sistem WAJIB
   menyimpan **basis asli + tarif asli**, lalu menghitung **tarif ekuivalen per satuan dasar KN**
   memakai konversi terdokumentasi. Yang dipakai GL/HPP adalah hasil konversi; yang dipakai
   verifikasi tagihan mitra adalah basis asli. **Dua-duanya disimpan.**

### 3.4 Lot & traceability (praktik yang diadopsi)
- **Lot internal unik** per batch terima/proses; **status** (quarantine/released/in-process/
  PFD/PFP/dyed/printed/finished); **genealogi** supplier-lot → lot internal → batch WIP →
  lot jadi → pengiriman; simpan **shade/print reference**, mesin/mitra, tanggal, resep, hasil uji;
  **aturan segregasi** agar shade/lot berbeda tidak tercampur; dukung **split/merge/rework**
  lewat `parent_lot`/`child_lot`.
- Untuk KN: **1 roll = 1 unit fisik** (sudah ada) → lot menempel di roll, dan **titik input lot =
  saat inspeksi/penerimaan** (sesuai permintaan pemilik), bukan digenerate diam-diam.

---

## §4. PROBLEM STATEMENTS

Format: **PS-xx** · Gejala · Bukti · Dampak · Akar masalah · Kebutuhan · Aturan/SSOT ·
Kriteria terima (acceptance).

### PS-01 — Rantai stage kain tidak lengkap & tidak terkendali
- **Gejala:** hanya `yarn|grey|finished`; PFP/PFD tidak ada; nilai bebas diketik.
- **Bukti:** A-01. **Dampak:** makloon multi-tahap mustahil; laporan per tahap tidak valid.
- **Akar:** stage diperlakukan sebagai label, bukan **state machine domain**.
- **Kebutuhan:** enum stage resmi + **matriks transisi** proses→stage + validasi server.
- **SSOT:** satu registry stage di backend; FE hanya konsumen (`GET /api/enums/stages`).
- **Terima:** (a) produk stage `pfp`/`pfd` bisa dibuat; (b) transisi ilegal (mis. `yarn → finished`
  langsung) **ditolak 400** dengan pesan Indonesia; (c) migrasi data lama idempoten.

### PS-02 — Tidak ada pembeda woven vs knitting
- **Gejala/Bukti:** A-02 (`fabric_type` hanya di template, tidak di produk).
- **Dampak:** rumus konversi & estimasi output salah untuk knit; tarif makloon salah basis.
- **Kebutuhan:** `fabric_type` **wajib** untuk produk stage ≥ grey (`woven|knit`), diturunkan
  otomatis ke roll & dokumen; rumus konversi memilih jalur sesuai `fabric_type`.
- **Terima:** produk grey/PFP/PFD/finished **tidak bisa** disimpan tanpa `fabric_type`;
  estimasi knit menghasilkan **kg**, woven menghasilkan **meter**.

### PS-03 — GSM belum menjadi fondasi rumus & belum wajib
- **Gejala:** GSM opsional, `yield_factor` diisi manual sehingga estimasi tak bisa diaudit.
- **Bukti:** A-03, A-04. **Dampak:** HPP/unit & kebutuhan benang tidak dapat dipertanggungjawabkan.
- **Kebutuhan:** GSM **wajib** mulai stage grey; estimasi output makloon dihitung dari
  **GSM + lebar + susut** (§3.3), `yield_factor` hanya **override sadar** yang tercatat siapa/kapan
  dan **wajib disertai alasan**.
- **Terima:** (a) produk stage ≥ grey tanpa GSM ditolak; (b) form makloon menampilkan
  **rumus & angka antara** (kg benang → kg efektif → meter/kg output) sehingga bisa diaudit;
  (c) override yield tercatat di audit log.

### PS-04 — Order Makloon tidak bisa multi-tahap & multi-mitra (UI)
- **Gejala:** hanya 1 proses & 1 mitra per order. **Bukti:** A-05 vs A-06 (model sudah siap).
- **Dampak:** alur nyata (benang → grey → PFP → printing) tidak terlayani; user membuat 3 order
  terpisah tanpa keterkaitan → HPP & jejak putus.
- **Kebutuhan:** **wizard rantai proses**: pilih input awal (produk+stage+lot), tambah langkah
  (proses, mitra, resep, output produk **eksplisit**, tarif+basis, estimasi), sampai stage akhir.
  Tiap langkah: mitra bisa berbeda; output langkah N = input langkah N+1 (**dipaksa sistem**).
- **Terima:** (a) 1 order dengan ≥3 langkah & ≥2 mitra berbeda bisa dibuat, di-issue & diterima
  bertahap; (b) sistem menolak bila output langkah N ≠ input langkah N+1; (c) HPP berjenjang
  (per langkah) + HPP akhir tampil.

### PS-05 — Makloon tidak mengenal PR (dua jalur pengadaan tidak setara)
- **Bukti:** A-07. **Dampak:** kontrol otorisasi/anggaran bocor lewat jalur makloon.
- **Kebutuhan:** PR memiliki **opsi pemenuhan**: `beli_finished_goods` (→ PO) atau
  `makloon` (→ Order Makloon), boleh **campuran per baris**; Order Makloon wajib merujuk PR
  (kecuali dikecualikan oleh kebijakan yang tercatat).
- **SSOT:** kebutuhan = `purchase_requisitions`; realisasi = `purchase_orders` **atau**
  `makloon_orders`. Status PR dihitung dari realisasi (jangan simpan ganda).
- **Terima:** PR 1 baris bisa direalisasi ke makloon; sisa PR berkurang benar; enforcement
  anggaran (R6.3) berlaku sama untuk kedua jalur.

### PS-06 — Tidak ada kontrak harga (hasil proofing/labdip) sebagai acuan PO
- **Bukti:** A-08. **Dampak:** harga PO tak punya asal-usul; negosiasi & sample tidak terekam.
- **Kebutuhan:** koleksi **kontrak harga** per (supplier/mitra × produk/proses) dengan
  **basis satuan sendiri** (per meter/yard/kg/pick/ball/roll), masa berlaku, MOQ, lead time,
  referensi sample yang disetujui; **nomor kontrak menjadi referensi wajib di PO/Makloon**;
  harga PO **diambil dari kontrak** (override wajib alasan + approval).
- **Terima:** (a) PO tanpa kontrak aktif → peringatan/blok sesuai kebijakan; (b) tarif kontrak
  berbasis pick otomatis dikonversi ke biaya/meter (§3.3-4) dan angka HPP cocok invarian.

### PS-07 — Supplier tanpa daftar barang & tanpa nama produk versi supplier
- **Bukti:** A-09, A-13. **Dampak:** surat jalan supplier memakai nama mereka → admin gudang
  salah terima/salah produk.
- **Kebutuhan:** daftar barang per supplier (turunan sah dari kontrak/proofing yang disetujui)
  memuat: produk KN (FK), **`supplier_product_name`**, `supplier_sku`, satuan supplier,
  konversi ke satuan KN, harga kontrak aktif. Tampil di form penerimaan & dokumen.
- **SSOT:** relasi supplier↔produk = **satu koleksi** (`supplier_items`); `products.supplier`
  (teks) dipensiunkan menjadi turunan/tampilan saja.
- **Terima:** di layar penerimaan, admin melihat **nama supplier + nama KN berdampingan**;
  pencarian barang bisa memakai nama/SKU supplier.

### PS-08 — Konversi satuan belum operasional di titik input
- **Gejala:** surat jalan mitra/supplier memakai ball/cone/roll/pick; user harus menghitung manual.
- **Bukti:** A-03 (mesin konversi ada) + tidak ada UI konversi. **Dampak:** salah input, tidak auditable.
- **Kebutuhan:** komponen **"Input & Konversi"** yang dapat dipasang di semua form qty
  (PR, PO, penerimaan, makloon issue/receive, inspeksi, transfer): user memilih **satuan dokumen
  asal** + qty → sistem menampilkan hasil konversi ke satuan dasar KN + **faktor yang dipakai** →
  simpan **keduanya** (`doc_uom`, `doc_qty`, `base_uom`, `base_qty`, `conversion_factor`,
  `conversion_source`).
- **Aturan:** konversi hanya lewat `uom_service` (R4); faktor spesifik supplier/mitra
  (mis. 1 ball = 45,36 kg) disimpan di master konversi per mitra/kontrak, bukan diketik ulang.
- **Terima:** (a) 1 komponen dipakai ≥4 modul; (b) dokumen menyimpan jejak konversi lengkap;
  (c) invarian: `base_qty == doc_qty × factor` (toleransi pembulatan).

### PS-09 — Grade tidak terkendali & tidak terhubung inspeksi
- **Bukti:** A-10. **Dampak:** laporan mutu & regrade tidak konsisten.
- **Kebutuhan:** enum grade resmi **A, A1, A2, B, BS** (+ arti & urutan), diinput **di awal PO**
  (ekspektasi mutu) dan **dapat berubah hanya melalui inspeksi** (4-point/manual) yang mencatatkan
  `grade_before → grade_after`, alasan, pemeriksa, waktu.
- **Terima:** (a) tidak ada input grade bebas di seluruh sistem; (b) perubahan grade tanpa
  inspeksi ditolak; (c) riwayat perubahan grade dapat dilihat di roll & laporan.

### PS-10 — Lot tanpa titik input & tanpa genealogi
- **Bukti:** A-11. **Dampak:** traceability tidak terpakai; fallback `LOT-MIGRATED` mengotori data.
- **Kebutuhan:** lot menjadi **entitas kelas satu**: penomoran terkendali, diinput saat
  **penerimaan/inspeksi**, wajib untuk stage ≥ grey, menyimpan `supplier_lot`, `dye_lot`/shade,
  proses & mitra pembentuk, `parent_lot[]`/`child_lot[]` (split/merge/rework), status mutu.
- **Terima:** (a) form inspeksi mewajibkan lot; (b) layar "silsilah lot" menampilkan jalur
  benang→grey→PFP→finished→pengiriman; (c) tidak ada roll stage ≥ grey tanpa lot valid.

### PS-11 — Estimasi vs aktual makloon tanpa konsekuensi
- **Bukti:** A-12. **Dampak:** kehilangan/susut berlebih tidak tertagih; tidak ada dasar klaim.
- **Kebutuhan:** hitung **selisih** (kg/meter & nilai) + **toleransi susut per proses/mitra
  (dari kontrak)**; bila melebihi toleransi → **status klaim** dengan tindakan terkonfigurasi:
  potong bon (kurangi tagihan jasa), tagih ganti rugi, atau terima dengan catatan; semuanya
  ber-approval & ber-jejak GL yang jelas.
- **Terima:** (a) selisih di luar toleransi memicu notifikasi eskalasi (pakai mesin alert R6.6);
  (b) potong bon mengurangi vendor bill jasa & tercermin di GL; (c) skor mitra terpengaruh.

### PS-12 — Alur R&D belum ada (master data → design → labdip/proofing → kontrak)
- **Gejala:** sistem mengasumsikan supplier punya katalog; kenyataannya KN meminta supplier
  memproduksi barang sesuai spesifikasi KN.
- **Kebutuhan (alur target):**
  `R&D membuat spesifikasi produk (draft)` → `pilih design/pattern (untuk printing)` →
  `labdip (kain polos) / proofing (printing)` ke ≥1 supplier → `sample dinilai & dipilih` →
  `kontrak harga terbentuk` → `masuk daftar barang supplier` → `PR` → `PO`.
- **Kebutuhan lifecycle produk:** `products.lifecycle` = `konsep → labdip/proofing → disetujui →
  produksi → dihentikan`; hanya `produksi` yang boleh dipesan/dijual.
- **Terima:** (a) produk `konsep` tidak muncul di PR/PO/POS; (b) setiap produk `produksi`
  memiliki jejak sample yang disetujui + kontrak; (c) dokumen & arsip sample dapat dicetak.

### PS-13 — Warna tanpa standar & tanpa pemilih
- **Kebutuhan:** master warna mendukung **berbagai sistem kode** (Pantone TCX/TPG, internal KN,
  kode supplier) + hex untuk pratinjau + pemilih warna; labdip merujuk kode + hasil ukur.
- **Catatan legal:** nama/kode Pantone adalah milik pihak ketiga → sistem menyimpan **kode+nama
  yang diinput/diimpor pengguna**, tanpa mendistribusikan pustaka berlisensi. (Butuh D-08.)
- **Terima:** input warna tidak pernah teks bebas; satu warna bisa punya beberapa kode paralel.

### PS-14 — Design/Pattern belum menjadi modul
- **Kebutuhan:** modul design menghasilkan **pattern/artwork** ber-kode, versi, pemilik, file
  master, mockup; R&D memilih kode design (bukan mengetik nama); pattern terhubung ke proofing,
  produk, dan dokumen produksi. Sudah ada `design_gallery` (M/H5) → **perluas, jangan buat baru**.
- **Terima:** produk printing wajib merujuk `design_id` + versi; mockup dapat dilampirkan.

### PS-15 — Input desimal & pembulatan tidak seragam
- **Kebutuhan:** semua input qty/harga mendukung koma-desimal (R5); aturan pembulatan tunggal
  terdokumentasi (qty 3 desimal, uang 2 desimal, konversi hitung penuh lalu bulatkan di simpan).
- **Terima:** POC menguji input `10,5` / `10.5` di PR, PO, makloon, inspeksi, transfer → tersimpan `10.5`.

### PS-16 — Wiring data & field hantu (higienitas fondasi)
- **Bukti:** A-14 (dua sumber biaya), A-15 (`batch_lot_rolls` kosong), A-16 (field rencana yang
  tidak ada), A-13 (`supplier` teks).
- **Kebutuhan:** audit menyeluruh "field ↔ sumber input ↔ konsumen" untuk koleksi inti
  (products, suppliers, rolls, PO/PR, makloon, inspeksi); setiap field diberi status
  **dipakai / diturunkan / dipensiunkan**; yang dipensiunkan dimigrasi & dihapus.
- **Terima:** laporan matriks field (mesin-terbaca) + gate baru yang gagal bila ada field
  tersimpan tanpa sumber input/derivasi terdaftar.

---

## §5. TARGET ARSITEKTUR DATA (usulan) & MATRIKS SSOT

### 5.1 Koleksi baru (usulan — nama final butuh persetujuan D-11)
| Koleksi | Prefix | Isi | Menggantikan/Melengkapi |
|---|---|---|---|
| `md_specs` | `spec_` | Spesifikasi produk versi R&D (draft→approved) + lifecycle | Melengkapi `products` (produk = hasil approve) |
| `md_designs` *(perluasan `design_gallery`)* | `dsg_` | Pattern/artwork, versi, file, mockup | **Perluas existing**, jangan buat baru |
| `md_samples` | `smp_` | Labdip & proofing: permintaan → sample supplier → penilaian → keputusan | — (baru) |
| `supplier_contracts` | `sct_` | Kontrak harga per supplier/mitra × produk/proses, basis satuan, validitas, MOQ, toleransi susut | Beda dari Blanket PO (komitmen qty) |
| `supplier_items` | `sit_` | Daftar barang supplier + `supplier_product_name`/`supplier_sku` + konversi satuan | Mengganti `products.supplier` (teks) |
| `inventory_lots` | `lot_` | Lot kelas satu + genealogi `parent/child` + shade/dye lot | Menaikkan `rolls.lot` (string) jadi entitas |
| `uom_conversion_rules` | `ucr_` | Faktor konversi per (produk \| supplier \| mitra \| kontrak) | Memusatkan konversi ad-hoc |
| `enum_registry` *(kode, bukan koleksi)* | — | grade, stage, fabric_type, process_type, contract_basis, lifecycle | Menghapus enum ter-hardcode |

### 5.2 Perubahan pada koleksi existing
- `products`: + `fabric_type` (wajib ≥ grey), + `lifecycle`, + `spec_id`, + `design_id/version`
  (printing), + `construction{epi,ppi,warp_count,weft_count,reed_width}` (woven, opsional-terkondisi),
  `stage` → enum tervalidasi (tambah `pfp`,`pfd`), `gramasi` → **wajib ≥ grey**,
  `grade` → enum, `supplier` → **dipensiunkan** (baca dari `supplier_items`),
  `batch_lot_rolls` → **dihapus** (migrasi), `harga_pokok` → jelas berlabel *referensi* (bukan HPP).
- `makloon_orders`: `steps[]` + `tariff_basis` (`pick|kg|meter|yard|ball|roll`), `tariff_original`,
  `tariff_base_equivalent`, `expected_*`/`actual_*` + `variance`, `tolerance_pct` (dari kontrak),
  `claim{status, action, amount, approved_by}`, `pr_id`, `contract_id`, `input_lot_ids[]`,
  `output_lot_id`, dan **wajib** `output_product_id` per langkah.
- `purchase_requisitions`: + `fulfillment_mode` per baris (`purchase|makloon`), + realisasi
  gabungan (PO & makloon).
- `purchase_orders`: + `contract_id` (referensi wajib bila kontrak aktif ada), + `supplier_item_id`,
  + `expected_grade`.
- `qc_inspections`: + `lot_id` (wajib), + `grade_before/grade_after`, + `shade_ref`.
- `inventory_rolls`: `lot` → `lot_id` (FK `inventory_lots`), + `stage`, + `fabric_type` (snapshot).

### 5.3 Matriks SSOT (agar tidak ada logika tercecer)
| Makna | SSOT | Turunan (jangan simpan ganda) |
|---|---|---|
| Spesifikasi & lifecycle produk | `md_specs` → disetujui → `products` | tampilan katalog |
| Pattern/design | `md_designs` | referensi di produk/proofing/dokumen |
| Warna | `color_library` (multi-sistem kode) | snapshot di produk & labdip |
| Harga beli | `supplier_contracts` | harga PO (snapshot + `contract_id`) |
| Nama barang versi supplier | `supplier_items` | tampil di penerimaan & surat jalan |
| Kebutuhan pengadaan | `purchase_requisitions` | status realisasi (dihitung) |
| Realisasi pengadaan | `purchase_orders` \| `makloon_orders` | — |
| Stok fisik & HPP aktual | `inventory_rolls` (+`inventory_balances` agregat) | `products.harga_pokok` = referensi saja |
| Identitas batch & silsilah | `inventory_lots` | `rolls.lot_id` |
| Konversi satuan | `uom_service` + `uom_conversion_rules` | jejak per dokumen (`doc_*`/`base_*`) |
| Mutu/grade | `qc_inspections` (perubahan) | `rolls.grade`, `products.grade` (ekspektasi) |
| Selisih & klaim makloon | `makloon_orders.claim` | vendor bill (potong bon) + GL |

**Larangan penamaan (tambahan untuk `ENTITY_REGISTRY`):** jangan buat `contracts`, `price_lists_supplier`,
`lots`, `batches`, `dye_lots`, `patterns`, `artworks`, `specs`, `rnd`, `samples`, `labdips`,
`conversions` — pakai nama di §5.1.

---

## §6. ENUM REGISTRY TERPUSAT (rancangan awal — nilai final di §8)

| Enum | Nilai usulan | Catatan |
|---|---|---|
| `stage` | `yarn`, `grey`, `pfd`, `pfp`, `finished`, `remnant`, `byproduct` | + matriks transisi |
| `fabric_type` | `woven`, `knit` | wajib ≥ grey (D-02) |
| `grade` | `A`, `A1`, `A2`, `B`, `BS` | urutan & arti butuh D-01 |
| `process_type` | `tenun`, `pre_treatment`, `dyeing`, `printing`, `finishing`, `lainnya` | pemetaan proses→transisi stage (D-03) |
| `tariff_basis` | `pick`, `kg`, `meter`, `yard`, `ball`, `cone`, `roll`, `lot` | tarif asli disimpan + ekuivalen dasar |
| `lifecycle` | `konsep`, `labdip`, `proofing`, `disetujui`, `produksi`, `dihentikan` | gating pemesanan/penjualan |
| `sample_type` | `labdip`, `proofing`, `bulk_sample` | labdip=polos, proofing=printing |
| `claim_action` | `potong_bon`, `tagih_ganti`, `terima_catatan` | butuh D-09 |
| `lot_status` | `karantina`, `released`, `in_process`, `hold_shade`, `rework` | dari riset §3.4 |

Transisi stage yang diusulkan (dikunci server):
`yarn --tenun--> grey` · `grey --pre_treatment--> pfd|pfp` · `pfd --dyeing--> finished` ·
`pfp --printing--> finished` · `finished --finishing--> finished` (tanpa pindah stage).

---

## §7. USULAN URUTAN FASE (fondasi dulu) — *menunggu konfirmasi, belum dieksekusi*

| Fase | Judul | Isi inti | PS tercakup |
|---|---|---|---|
| **A** | Fondasi domain | enum registry + endpoint enums, stage machine, `fabric_type`, GSM wajib, grade enum, input desimal, migrasi idempoten | PS-01, 02, 03, 09, 15 |
| **B** | Mesin konversi satuan | `uom_conversion_rules`, komponen UI "Input & Konversi", jejak `doc_*`/`base_*`, invarian konversi | PS-08, 15 |
| **C** | Lot kelas satu | `inventory_lots` + genealogi + input saat inspeksi/terima + layar silsilah | PS-10, 09 |
| **D** | Makloon rantai proses | wizard multi-step/multi-mitra, tarif berbasis (pick/kg/m), estimasi berbasis GSM, HPP berjenjang, selisih & klaim | PS-04, 03, 11, 08 |
| **E** | Sourcing berbasis kontrak | `supplier_contracts`, `supplier_items` (+nama supplier), PR→(PO\|Makloon), referensi kontrak di PO | PS-05, 06, 07 |
| **F** | R&D & Design | `md_specs`, perluasan `md_designs`, `md_samples` (labdip/proofing), lifecycle produk, dokumen & arsip | PS-12, 13, 14 |
| **G** | Higienitas fondasi | matriks field↔sumber, pensiun field hantu, gate baru | PS-16 |

Setiap fase mengikuti protokol repo: **POC HTTP → invarian integritas → gate.sh hijau →
testing_agent → dokumentasi (`ENTITY_REGISTRY`, `plan.md`, handoff)**.

---

## §8. KEPUTUSAN YANG BUTUH KONFIRMASI PEMILIK (jangan diasumsikan)

| ID | Pertanyaan | Mengapa penting |
|---|---|---|
| **D-01** | Arti & urutan grade `A, A1, A2, B, BS` (mana terbaik→terburuk; `BS` = barang sortir?) dan grade default saat PO | Menentukan validasi, laporan mutu, harga per grade |
| **D-02** | Apakah `fabric_type` wajib juga untuk `yarn`, atau mulai `grey` saja? | Menentukan titik validasi |
| **D-03** | Apakah `pfd`/`pfp` selalu hasil satu proses `pre_treatment`, atau ada proses berbeda (scouring/bleaching terpisah)? | Menentukan matriks transisi & jumlah langkah makloon |
| **D-04** | Untuk knitting: apakah output makloon dicatat **kg saja**, atau kg + meter (informasi)? | Menentukan satuan dasar & tampilan |
| **D-05** | Susut standar per proses (tenun/celup/printing) — angka default & apakah per mitra/kontrak? | Estimasi output & toleransi klaim |
| **D-06** | Untuk tarif tenun berbasis **pick**: apakah PPI diambil dari spesifikasi produk (konstruksi) dan tarif per pick dari kontrak? | Rumus biaya/meter (§3.3-4) |
| **D-07** | Satuan tarif untuk dyeing & printing di praktik Anda (per kg? per meter? per yard? + biaya screen/repeat?) | Struktur `tariff_basis` |
| **D-08** | Pustaka warna: pakai kode Pantone yang diinput/diimpor manual (aman lisensi) atau ada pustaka resmi yang Anda miliki? | Legal + desain master warna |
| **D-09** | Konsekuensi selisih makloon: daftar tindakan yang berlaku (potong bon / ganti rugi / terima) + siapa yang menyetujui | Alur klaim & GL |
| **D-10** | Penomoran lot: format yang Anda inginkan (mis. `LOT-YYMM-####`) & granularitas (per roll / per batch terima / per batch proses) | Traceability & label |
| **D-11** | Persetujuan nama koleksi di §5.1 (agar tidak ada duplikasi nama di masa depan) | Registry & anti-duplikasi |
| **D-12** | Prioritas urutan fase §7 — apakah A→B→C→D→E→F, atau ada yang harus lebih dulu (mis. E karena kebutuhan pembelian mendesak)? | Urutan eksekusi |

---

## §9. DEFINITION OF DONE UNTUK SETIAP FASE TURUNAN

1. Semua PS yang diklaim selesai punya **bukti**: POC HTTP (angka PASS/FAIL), invarian baru di
   `verify_data_integrity.py`, `scripts/gate.sh` hijau, laporan `testing_agent_v3`.
2. **Tidak ada** input teks bebas untuk data terkendali (R1) — diverifikasi gate statik.
3. **Tidak ada** field tersimpan tanpa sumber input/derivasi (R2) — diverifikasi gate matriks field.
4. Semua konversi lewat `uom_service` (R4) — diverifikasi grep gate.
5. `ENTITY_REGISTRY.md` diperbarui + larangan penamaan ditambahkan.
6. Migrasi data lama **idempoten** dan terbukti aman dijalankan dua kali.
7. Dokumen ini diperbarui bila ada temuan/keputusan baru (dokumen hidup).

---

## §10. LAMPIRAN A — ANALISIS DOKUMEN CLIENT "ERP per divisi (2).xlsx"

> Sumber: file yang diberikan pemilik sistem (2 sheet: `Bagan`, `Notif`). Dokumen sangat ringkas
> (±10 baris bermakna) dan **bukan kebenaran final** — dipakai untuk menangkap **intent**.
> Di bawah: isi asli (dikutip), tafsir, pemetaan ke problem statement, dan **usulan yang lebih baik**
> bila cara di dokumen berisiko menimbulkan duplikasi/cacat logika.

### A.1 Isi asli yang dapat dibaca

**Sheet `Bagan` — 4 tim: `Sample · Designer · RnD · Socmed`**
1. "Sample dikerjakan sesuai SO | Design PO | Timeline RnD mulai dari rnd 1, rnd 2, rnd 3, sampai barang acc"
2. "Tanda sample sudah jadi dan dikirim | Timeline pengerjaan design masing2 designer | semua harus berupa upload dan penjelasan"
3. "Ada master stock sample (sync dengan stock roll) yang bisa dilihat tim sales dan tim sample | Designer upload design yg sudah diacc"
4. "Tim Sample akan ambil bahan untuk dibuat sample dari roll, artinya harus ada penyesuaian jumlah roll di stock (gudang) | Design yang sudah acc akan ada nilai, yg dinilai oleh management di erp"
5. "ada laporan berapa banyak design yang sudah acc masing2 designer"

**Blok `JAKARTA` — dua jalur order sales**
- Kolom 1 = **barang sudah ada di master**; Kolom 2 = **barang PO sendiri (custom)**
- `Woven, knitting`: "sales pilih item, warna, qty, harga → barang ready → kirim; barang tidak ready
  → notif MD untuk repeat/restock/masuk pendingan dan MD harus PO → barang datang/ready → kirim"
- `PO sendiri`: "sales pilih order po sendiri → pilih item → request warna → notif md untuk po custom
  → barang datang → kirim"
- `Printing`: sama untuk jalur master; untuk PO sendiri → "pilih item sesuai code dari md jakarta
  (**code ini hanya dishow ke sales tertentu**, karena po sendiri artinya barang hanya untuk sales
  sendiri, **tidak dijual oleh sales lain**)"
- "MD Jakarta assign to designer to design → hasil design diassign oleh MD Jakarta ke MD printing,
  RnD → jadi item yg bisa diorder sales itu sendiri"

**Sheet `Notif` — penerima: `Sales · Admin Sales · MD · Finance · Sample · Designer · Socmed · RnD`**
- "Barang PO datang" · "Stock menipis" · "Barang pendingan datang"
- "Due Date pembayaran customer (**H-3, H-1, Hari H, H+1**)"

### A.2 Pemetaan intent → problem statement

| Intent client | Status di KN_18 | Tindakan |
|---|---|---|
| RnD berjenjang (rnd 1→2→3 sampai acc) | tercakup **PS-12** (proofing/labdip) tetapi **tanpa iterasi bernomor** | **perluas PS-12** + **PS-18 baru** |
| Upload + penjelasan wajib tiap tahap | belum ada | **PS-18** |
| Timeline/SLA per designer & per tahap | belum ada | **PS-18** |
| Design di-upload setelah acc, ada **nilai** dari management + laporan per designer | belum ada | **PS-18** (KPI designer) |
| Master **stok sample** yang *sync* dengan stok roll; ambil bahan sample **mengurangi stok gudang** | belum ada | **PS-19 baru** |
| Divisi/tim sebagai aktor (Sample, Designer, RnD, Socmed, MD, Admin Sales, Finance) | RBAC sekarang **hanya 4 role** (admin/sales/manager/warehouse) | **PS-17 baru** |
| Item **eksklusif milik sales tertentu** ("PO sendiri"), kode hanya tampil ke sales itu | belum ada | **PS-20 baru** |
| Barang tidak ready → notif MD → repeat/restock/**pendingan** → MD buat PO | backorder **sudah ada** (`backorder_service`), pemicu dari sales & notifikasi MD **belum** | **PS-21 baru** |
| Notif: barang PO datang · barang pendingan datang · **AR due H-3/H-1/H/H+1** | mesin alert **sudah ada** (R6.5/R6.6); 3 job ini **belum ada** (yang ada `ap_due` & `ar_overdue`) | **PS-21** (tambah job, bukan modul baru) |
| Alur "assign designer → assign ke MD printing/RnD → jadi item orderable" | belum ada | **PS-17** (assignment) + **PS-12** (lifecycle produk) |
| "SO Design" / "Design PO" sebagai dokumen | belum ada | lihat A.4 — **jangan** buat dokumen baru |

### A.3 Problem statement baru

**PS-17 — Struktur divisi & penugasan antar divisi belum ada**
- *Gejala:* dokumen client memakai 8 aktor (Sales, Admin Sales, MD, Finance, Sample, Designer,
  Socmed, RnD); sistem hanya punya 4 role.
- *Dampak:* pekerjaan tidak bisa di-assign antar divisi; notifikasi tidak bisa ditujukan tepat;
  laporan per divisi/orang tidak mungkin.
- *Kebutuhan:* `division` + `position` pada user; **penugasan (assignment) berbasis tiket kerja**
  (siapa mengerjakan, tenggat, status) untuk tahap R&D/Design/Sample; penerima notifikasi berbasis
  **divisi**, bukan hanya role.
- *Aturan:* **perluas** `permission_settings` + role registry yang sudah ada — **dilarang** membuat
  sistem izin kedua (R3). Notifikasi memakai `recipient_role` yang sudah ada + `recipient_division`.
- *Terima:* (a) tugas design bisa di-assign MD → Designer dengan tenggat & status; (b) notifikasi
  "design perlu dinilai" hanya masuk ke management; (c) laporan beban kerja per divisi.

**PS-18 — Iterasi R&D/Design (round) tanpa struktur: versi, bukti upload, SLA, penilaian**
- *Kebutuhan:* satu permintaan (sample/labdip/proofing) memiliki **round bernomor** (`rnd 1..n`),
  setiap round: pelaksana, tanggal mulai/selesai, **lampiran wajib** (foto/artwork/hasil ukur) +
  catatan, hasil (`revisi`|`acc`|`tolak`), dan **penilaian** saat acc (skor + penilai).
- *Terima:* (a) tidak bisa menutup round tanpa lampiran + penjelasan; (b) laporan "jumlah design
  acc per designer per periode" + rata-rata lama pengerjaan; (c) SLA terlampaui → alert
  (pakai mesin eskalasi R6.6).

**PS-19 — Stok sample belum terhubung ke stok gudang**
- *Gejala:* client meminta "master stock sample **sync** dengan stock roll" dan pengambilan bahan
  sample **mengurangi stok**.
- *Risiko bila salah desain:* membuat koleksi stok sample terpisah → **dua sumber stok** (pelanggaran R3).
- *Kebutuhan:* pengambilan bahan sample = **movement `sample_issue`** atas roll (mengurangi stok,
  ber-referensi permintaan sample); "Master Stok Sample" = **tampilan (view) terfilter** dari roll
  bertanda `purpose=sample`, bukan koleksi baru. Nilai biaya sample terbawa dari cost roll.
- *Terima:* (a) satu angka stok (tidak ada selisih antara gudang & sample); (b) jejak: sample X
  memakai roll Y sebanyak Z; (c) laporan biaya sample per divisi/periode.

**PS-20 — Produk eksklusif per sales ("PO sendiri") belum didukung**
- *Kebutuhan:* penanda kepemilikan/visibilitas pada produk: `exclusivity = umum | sales_tertentu`
  + daftar `owner_sales_ids[]` (+ masa berlaku opsional). Katalog, POS, PR/PO, dan pencarian
  **wajib** menghormati aturan ini; sales lain tidak melihat kodenya.
- *Aturan:* filter dilakukan **di backend** (bukan disembunyikan di UI saja) agar tidak bisa
  ditembus lewat API.
- *Terima:* (a) sales A melihat item eksklusifnya, sales B tidak (diuji lewat API & UI);
  (b) admin/manager tetap melihat semua; (c) SO dari item eksklusif hanya boleh dibuat pemiliknya.

**PS-21 — Alur "barang tidak ready" & notifikasi operasional belum lengkap**
- *Kebutuhan:*
  (a) dari layar order, sales dapat menandai kebutuhan **repeat/restock** → membuat **PR** otomatis
  (jalur PS-05) + notifikasi ke **MD**; barang yang belum tersedia masuk **pendingan** (backorder
  yang sudah ada), dengan status yang terlihat sales;
  (b) job alert baru pada mesin R6.5/R6.6: **`po_arrival`** (barang PO datang), **`backorder_ready`**
  (barang pendingan datang/siap kirim), **`ar_due_soon`** dengan offset **H-3, H-1, H, H+1**
  (melengkapi `ar_overdue` yang sudah ada).
- *Terima:* (a) satu klik dari SO menghasilkan PR + notifikasi MD; (b) 3 job baru muncul di
  Penjadwal & Notifikasi dengan jadwal yang bisa diubah; (c) notifikasi due-date muncul tepat di
  H-3/H-1/H/H+1 tanpa duplikasi (dedupe harian sudah ada).

### A.4 Usulan yang LEBIH BAIK dari dokumen client (intent tetap sama)

| Di dokumen | Risiko bila diikuti apa adanya | Usulan |
|---|---|---|
| "SO Design" & "Design PO" sebagai dokumen baru | menambah 2 jenis dokumen yang tumpang tindih dengan SO/PR/PO → duplikasi & bingung | **1 entitas permintaan kerja** `md_samples` dengan `request_type = labdip \| proofing \| sample_jual \| design_request`; bila berasal dari pelanggan, cukup **referensi ke SO** yang sudah ada |
| "master stock sample" | dua sumber stok | **view** atas `inventory_rolls` + movement `sample_issue` (PS-19) |
| "PO sendiri (custom)" sebagai jenis PO baru | pecah alur pembelian jadi dua & merusak kontrol anggaran | tetap **PR → PO** yang ada + `origin = so_custom` + `so_id` + eksklusivitas produk (PS-20) |
| Notifikasi digambarkan sebagai matriks manual | terpisah dari mesin alert yang sudah jalan | **tambah job** di `scheduler_service` (9 → 12 job) + penerima berbasis divisi (PS-17) |
| "Timeline" hanya kolom | tidak bisa ditagih | **SLA per round** + eskalasi otomatis memakai R6.6 |
| Penilaian design bebas | skor tidak bisa dibandingkan | rubrik skor terkendali (enum/skala) + laporan per designer (PS-18) |

### A.5 Dampak ke urutan fase (§7)

Usulan penyesuaian: sisipkan **Fase H — Divisi, Penugasan & Alur Sample/Design** setelah Fase F
(R&D & Design), karena PS-17/18/19 bergantung pada `md_specs`/`md_samples`/`md_designs`.
**PS-21 dapat dikerjakan lebih awal & murah** (mesin alert sudah ada) — cocok sebagai
"quick win" yang bisa disisipkan kapan pun, bahkan sebelum Fase A, bila pemilik menginginkan
hasil yang cepat terlihat.

### A.6 Keputusan tambahan yang dibutuhkan

| ID | Pertanyaan |
|---|---|
| **D-13** | Daftar final divisi/jabatan + siapa **approver** di tiap tahap (design acc, sample acc, PO custom, PR) |
| **D-14** | Apakah **Socmed** butuh modul kerja sendiri (konten/jadwal posting) atau **cukup penerima notifikasi**? |
| **D-15** | Bahan sample: apakah mengurangi **stok jual** (ya/tidak) dan apakah biayanya dibebankan ke divisi/anggaran? |
| **D-16** | Produk eksklusif sales: berlaku **selamanya** atau **berjangka**? Siapa yang boleh membukanya menjadi umum? |
| **D-17** | Penilaian design: skala nilai (mis. 1–5 / bobot) & apakah dipakai untuk **KPI/insentif** designer? |
| **D-18** | "MD" = *merchandiser*? Apakah MD Jakarta & MD Printing dua divisi berbeda dengan wewenang berbeda? |

---

## §11. KEPUTUSAN TERKONFIRMASI PEMILIK (mengikat — 2026-07-25)

| ID | Keputusan | Implikasi teknis |
|---|---|---|
| **D-01** ✅ | Urutan grade terbaik → terburuk: **`A` → `A1` → `A2` → `B` → `BS`** | Enum `grade` dengan `rank` 1..5; `BS` = mutu terendah (sortir). Perbandingan mutu memakai `rank`, bukan alfabet |
| **D-02** ✅ | **`fabric_type` wajib SEJAK STAGE `yarn`** — supaya jelas benang ini untuk knitting atau woven | Validasi berlaku untuk **semua** produk tekstil (yarn s/d finished), bukan hanya ≥ grey |
| **D-03** ✅ | **Satu proses `pre_treatment`** menghasilkan **PFD atau PFP** (tergantung tujuan akhir) | Transisi: `grey --pre_treatment(target_use=dye)--> pfd` · `grey --pre_treatment(target_use=print)--> pfp`. Butuh field `target_use` pada langkah proses |
| **D-06 & D-07** ✅ | **Basis tarif tidak dipaksa per proses** — bisa berbeda-beda tergantung supplier/mitra (pick, kg, meter, yard, ball, roll, lot, + biaya tetap). Solusinya = **mesin konversi** yang menutup semua kasus | `tariff_basis` **bebas dipilih per kontrak/langkah** (bukan ditentukan sistem berdasar proses); WAJIB simpan tarif asli + basis asli + faktor konversi + tarif ekuivalen satuan dasar; dukung `fixed_charges[]` (screen/repeat/minimum) |
| **D-10** ✅ | Lot: format **`LOT-YYMM-####`**, granularitas **per batch penerimaan/proses** | Penomoran memakai `next_doc_number` (deletion-safe); 1 lot dapat menaungi banyak roll |
| **D-26** ✅ *(Fase C)* | **Nomor lot per ENTITAS** — `KSC/LOT-2607-0001`, `KANDA/LOT-2607-0001` (konsisten SO/PO) | `next_doc_number(collection="inventory_lots", entity_id=..., scheme="per_entity_prefix")` → sequence atomik per (entitas, bulan); dokumen lot menyimpan `entity_id` + `owner_entity_id` |
| **D-27** ✅ *(Fase C)* | **Penegakan lot dapat dikonfigurasi** — mulai dengan **peringatan saja** (tidak memblokir gudang), dapat dinaikkan ke **blokir** kapan pun tanpa deploy | `system_settings` scope `lot`: `enforcement_mode=warn\|block`, `require_supplier_lot`, `require_dye_lot`, `status_on_receipt`. Mode `warn` → GR/inspeksi tetap jalan + `lot_warnings[]`; mode `block` → ditolak 400 dengan pesan yang bisa ditindak. Status mutu lot **informasional** (tidak memblokir penjualan) |
| **D-12** ✅ | Kerjakan **Fase A (fondasi domain)** lebih dulu | Rencana teknis: `docs/KN_19_PLAN_FASE_A_FONDASI_DOMAIN.md` |

Konsekuensi penting dari **D-06/D-07**: sistem **tidak boleh** mengasumsikan "tenun = per pick,
celup = per kg, printing = per meter". Asumsi itu **dihapus** dari desain; yang wajib ada adalah
**kebebasan memilih basis + konversi yang terdokumentasi & auditable**. Rumus pick (`biaya/meter =
PPI × tarif/pick`) tetap didukung sebagai **salah satu** basis, memakai PPI dari spesifikasi produk.

---

## §12. KEPUTUSAN TURUNAN FASE A (mengikat — 2026-07-25, sesi eksekusi)

Keputusan berikut diambil pemilik saat menyusun rencana teknis Fase A
(`docs/KN_19_PLAN_FASE_A_FONDASI_DOMAIN.md`) dan sudah **dieksekusi**.

| ID | Keputusan | Implikasi teknis (sudah jalan) |
|---|---|---|
| **D-19** ✅ | **Tidak ada grade default saat PO** — user WAJIB memilih grade per item | `POItemCreate.expected_grade` wajib di jalur manusia (400 bila kosong); jalur turunan sistem (PR→PO, call-off, award RFQ) menurunkan dari master produk dengan penanda `expected_grade_source` |
| **D-20** ✅ | Migrasi produk lama: `fabric_type` **default `woven`** untuk semua | `scripts/migrate_fase_a_domain.py` mengisi `woven` + menandai `fabric_type_migrated: true` (jejak bahwa nilai berasal dari migrasi, bukan input user) |
| **D-21** ✅ | Stage **`remnant`** & **`byproduct`** dimasukkan sekarang | Enum stage berisi 7 nilai; transisi `…--lainnya--> remnant/byproduct` terdaftar |
| **D-22** ✅ | GSM **+ lebar** wajib mulai `grey` (woven) · stage `yarn` wajib `yarn_count` · **knit tidak diwajibkan** | `STAGE_FIELD_RULES` + `KNIT_RELAXED_FIELDS`: untuk knit field terukur menjadi **peringatan** (`needs_review`), bukan penolakan — knit dikendalikan kg (§3.2) |
| **D-23** ✅ | Grade berubah lewat inspeksi QC; **override manager/admin** boleh dengan **alasan wajib** + audit | `services/grade_service.py` = satu pintu; `POST /api/inventory/rolls/{id}/grade-override` (role admin/manager, `reason` wajib) + `grade_history[]` + audit log |

**Konsekuensi lain yang ditemukan & diperbaiki saat eksekusi (bukan asumsi):**
1. QC 4-point sebelumnya menghasilkan grade **A/B/C** (di luar enum D-01). Sekarang
   dipetakan ke **A/A1/A2/B/BS** dengan ambang `a_max`/`a1_max`/`a2_max`/`b_max`;
   konfigurasi lama (hanya `a_max` & `b_max`) di-interpolasi sehingga **batas A dan B
   tidak berubah** (kompatibel-mundur).
2. UI QC & release karantina sebelumnya memakai daftar grade ter-hardcode termasuk
   `A+` dan `C` → kini konsumsi `GET /api/enums` (R7).
3. `products.stage` sebelumnya tidak ada di dokumen produk seed lama → migrasi
   mengisi + invarian `INV-DOMAIN-01..06` mencegah regresi.

---

## §13. STATUS EKSEKUSI LANJUTAN (sesi 2026-07-25 — setelah Fase A)

Keputusan pemilik pada sesi ini: **“kerjakan a + b”** → PS-21 (quick win notifikasi
operasional) lebih dulu, lanjut **Fase B** (konversi satuan). Dua keputusan tambahan:

| ID | Keputusan | Implikasi teknis (sudah jalan) |
|---|---|---|
| **D-24** ✅ | Konversi satuan dibuat **GLOBAL** dengan opsi satuan yang luas — **bukan** tabel per kontrak/mitra | Koleksi `uom_conversion_rules` (23 satuan · 5 dimensi · jenis fixed/pack/formula); faktor khusus tetap bisa lewat `products.uom_conversions[]` yang menang atas aturan global |
| **D-25** ✅ | Toleransi selisih konversi vs timbang/ukur aktual **dapat dikonfigurasi user** | `system_settings` scope `uom`: `warn_pct` (tandai perlu ditinjau) · `block_pct` (tolak) · `allow_override` (override beralasan + audit) · `precision`; UI: Produk & Harga → Konversi Satuan |

| PS | Status | Bukti |
|---|---|---|
| **PS-21** (alur barang tidak ready + notifikasi operasional) | ✅ SELESAI | `docs/KN_21_PLAN_PS21_NOTIFIKASI_OPERASIONAL.md` · POC 43/0 · INV-PS21-01…04 |
| **Fase B / D-06 · D-07** (konversi satuan + jejak wajib) | ✅ SELESAI | `docs/KN_22_PLAN_FASE_B_UOM.md` · POC 49/0 · INV-UOM-01…04 |

**Temuan penting saat eksekusi (bukan asumsi):**
1. **Bug lama catch-weight**: `GSM × lebar ÷ 1000` = kg **per meter**, tetapi dipakai sebagai
   kg per **satuan dasar produk**. Untuk produk berbasis *yard* berat salah ±9,4%.
   Diperbaiki `uom_service.kg_per_base_unit()` + diuji POC Fase B US-3b.
2. `POST /api/scheduler/jobs/{id}/run` sebelumnya WAJIB body (422 tanpa body) → body opsional.
3. Jalur pembuatan produk NON-form (seed, import CSV/XLSX, SKU custom special order) belum
   melewati registry domain Fase A → ditutup lewat `domain_registry.stamp_domain_defaults()`
   dan `roll_domain_snapshot()` (invarian INV-DOMAIN-02/04/05 kini hijau pada DB baru).
