# RENCANA EKSEKUSI — "MD ERP" (lini · sampling · inspeksi/QC · makloon · papan PO)

> Sumber kebutuhan: 2 berkas pemilik (`docs/sumber/ERP_per_divisi_2026-08-18.xlsx`,
> `docs/sumber/FORMAT_GSHEET_MD_ERP_2026-08-18.xlsx`) + penjelasan alur pemilik
> (sesi 2026-08-18). Analisis & pengukuran keadaan awal: `ANALISIS_FLOW_DIVISI.md`.
>
> Dokumen ini adalah **rencana teknis**: nama koleksi, nama field, relasi, endpoint,
> berkas yang disentuh, migrasi, POC, dan gate. Semua nama yang disebut sebagai
> "SUDAH ADA" telah diverifikasi langsung ke kode/basis data — bukan ingatan.

---

## 0. PRINSIP (supaya tidak lahir duplikat)

1. **Satu fakta = satu tempat.** Angka turunan (mis. berapa yang sudah diterima)
   **dihitung** dari dokumen sumbernya, tidak diketik ulang & tidak disalin.
2. **Pakai mesin yang sudah ada.** Sebelum membuat koleksi/servis baru, wajib cek
   daftar §1. Menambah pintu kedua untuk fakta yang sama adalah kelas bug termahal
   di repo ini (riwayatnya: 3 angka berbeda untuk satu pertanyaan "berapa yang
   menunggu persetujuan").
3. **Master, bukan hardcode.** Semua daftar yang bisa bertambah (lini, tahapan
   proses, jenis sampling, jenis cacat) memakai mekanisme **master berlapis**
   yang sudah ada (`entity_master_service.MasterSpec`) → dapat layar & API
   otomatis, dan bisa ditimpa per badan usaha.
4. **Setiap fase ditutup bukti**: 1 POC yang bisa dijalankan + 1 gate (invarian)
   yang bisa **memerah**, terdaftar di `scripts/gate.sh`.
5. **Tidak setengah jalan.** Tiap fase punya daftar "titik yang WAJIB ikut berubah";
   fase dianggap selesai hanya bila seluruh daftar itu hijau.

---

## 1. INVENTARIS YANG SUDAH ADA (JANGAN DIBUAT ULANG)

| Kebutuhan | Sudah ada di | Bentuk |
|---|---|---|
| Master berlapis global→badan usaha + layar generik | `services/entity_master_service.py` (`MasterSpec`) · `routers/entity_masters.py` · `frontend/src/features/settings/masters/EntityMastersView.jsx` | `GET/POST/PATCH/DELETE /api/entity-masters/{kind}` (+`/effective`, `/override`) |
| Enum domain → frontend | `domain_registry.py` · `routers/enums.py` (`GET /api/enums`, `/api/enums/{name}`) · `frontend/src/hooks/useDomainEnums.js` | FE **dilarang** hardcode enum |
| Relasi antar dokumen (dua arah) | `services/doc_refs_service.py` — `refs:[{rel,doc_type,doc_id,doc_number,note,at}]` | dipakai SO/PO/GRN/retur/kontrabon/landed cost |
| Satu-satunya pintu ubah grade + riwayat | `services/grade_service.py` → `set_roll_grade()`, `grade_history[]`, sumber sah: `qc_inspection`·`quarantine_release`·`manager_override`·`migration` | |
| Inspeksi 4-point per roll (barang masuk) | `services/qc_inspection_service.py` · `routers/qc_inspection.py` · task `qc_pending` | cacat (poin 1–4 × jumlah) · gramasi & lebar aktual · lot/dye lot/shade |
| Sampling ke supplier + iterasi ber-bukti | `md_samples` (+`rounds[]`: `round_no`,`supplier_id`,`due_date`,`attachments`,`note`,`measurements`,`result`,`score`,`assessed_by`) · `services/rnd_sample_service.py` | lampiran + catatan **WAJIB** saat menutup round |
| Sample ambil bahan dari roll | `POST /api/rnd/samples/{id}/issue-material` → roll berkurang + `inventory_movements` jenis `sample_issue` | |
| Spesifikasi R&D → lahir produk | `md_specs` + `POST /api/rnd/specs/{id}/release-product` | |
| Keputusan sample → kontrak otomatis | `rnd.auto_contract_on_decide` → `supplier_contracts` | |
| Kontrak produksi/makloon | `supplier_contracts` (`contract_type`,`partner_kind`,`process_type`,`tariff_*`,`yield_factor`,`shrinkage_pct`,`sample_ref`,`valid_from/to`) | 12 dokumen di data demo |
| Makloon berantai + mitra per tahap | `makloon_orders.steps[]` (`seq`,`process_type`,`makloon_id`,`recipe_id`,`input_*`,`output_*`,`yield_factor`,`waste_pct`,`shrinkage_pct`,`estimate.explain[]`,`actual_output_qty`,`contract_id`) · mitra `makloons.process_types[]` | |
| Master satuan | koleksi `uoms` (`code`,`base_type`,`factor_to_base`,`precision`) + CRUD `/api/uoms` | isi sekarang: MTR·YRD·RLL·PCS·CM·INCH |
| Pustaka warna | `color_library` (`code`,`name`,`hex`,`system`,`family`) | `system` sekarang "KN" → siap menampung **Pantone** |
| Galeri desain + versi + ACC + nilai bintang | `design_gallery` (`code`,`design_type`,`files[]`,`versions[]`,`status`,`ratings[]`,`repeat_cm`,`color_count`,`screen_count`) | alur Ajukan→Sahkan lunas di F-6.7 |
| Eksklusivitas produk per sales (pagar di server) | `services/product_exclusivity.py` (`exclusivity`,`owner_sales_ids`) | **pola yang akan ditiru untuk LINI** |
| Antrean keputusan lintas modul | `services/approval_backlog_service.py` (`QUEUES`) + gate `INV-APPR-01` | setiap pintu keputusan baru WAJIB didaftarkan |
| Notifikasi + dedupe + eskalasi | `services/notification_service.py`, `alert_ops_service.py`, `scheduler_service.JOBS` | |
| Retur jual + karantina + pelepasan ber-grade | `services/return_service.py` (`release_quarantine`) | |

---

## 2. ALUR TARGET (bahasa pemilik → bentuk sistem)

```
                 ┌──────────────── JALUR A: BELI JADI ─────────────────┐
Pelanggan/ide ──▶ PERMINTAAN DESAIN ──▶ artwork (galeri) ──ACC──▶ SPESIFIKASI
   (SO / internal)   design_requests        design_gallery            md_specs
                                                                        │
                                                       SAMPLING KE SUPPLIER
                                                       md_samples  (labdip &/atau
                                                       handfeel &/atau proofing —
                                                       BOLEH LEBIH DARI SATU)
                                                         │ iterasi round 1..n
                                                         │ (lampiran+catatan WAJIB,
                                                         │  riwayat tiap iterasi)
                                                         ▼  ACC
                                            MASTER PRODUK  +  KONTRAK SUPPLIER
                                            products          supplier_contracts
                                                         │
                                                PR ──▶ PO ──▶ TERIMA DI GUDANG
                                    purchase_requisitions   purchase_orders  wms_tasks/GRN
                                                         │
                                          INSPEKSI & QC (dokumen ber-SPK)
                                                 inspections
                                                         │
                                              GRADING (grade_service)
                                                         │
                                    ┌────────────────────┴───────────────────┐
                             SIMPAN DI GUDANG                    PEMENUHAN SO (bila dari SO)
                             inventory_rolls/lots                 alur SO lengkap → kirim

                 └──────────────── JALUR B: MAKLOON (buat sendiri) ────┘
   Kontrak makloon ─▶ SPK Makloon (makloon_orders.steps: benang→tenun/rajut→celup /
                      proofing→pfp→screen→printing) ─▶ output ─▶ INSPEKSI & QC ─▶ GRADING
                      tiap tahap: mitra makloon + tarif + hasil aktual        ─▶ gudang / SO
```

Dua jalur itu **bertemu di titik yang sama**: penerimaan → inspeksi/QC → grading →
gudang/pemenuhan. Karena itu dokumen inspeksi dibuat **satu** dengan pembeda `kind`,
bukan dua koleksi berbeda.

---

## 3. FASE EKSEKUSI

Urutan dipilih berdasarkan **ketergantungan**, bukan kemudahan:
`L → T → U → S → I → P → D → N → M`.

---

### FASE L — LINI PRODUK (master + pagar keras yang bisa dikonfigurasi)

**Tujuan pemilik:** woven / knit / printing dikerjakan staf berbeda; harus jadi
master yang **bisa bertambah**, pembedanya **pagar keras tapi bisa dikonfigurasi**
(satu staf boleh dapat lebih dari satu lini), dan berlaku **di semua tempat**, bukan
hanya saat membuat PO.

**A. Master baru** — `MasterSpec` di `services/entity_master_service.py`:

```
"product-lines": MasterSpec(
    kind="product-lines", collection="product_lines", label="Lini Produk",
    key_field="code", name_field="name", id_prefix="pline",
    fields=("code","name","sort","active","notes",
            "measure_unit_default",      # yard | kg | panel  (satuan ukur bawaan)
            "stage_sequence",            # ["benang","tenun","celup","inspect"]
            "sample_types_default"),     # ["labdip","handfeel"]  (usulan saat sampling)
    sort=(("sort",1),("code",1)))
```
Seed awal (migrasi, idempotent): `woven` (meas=yard, stages benang→tenun→celup→inspect),
`knit` (meas=kg, stages benang→rajut→celup→inspect),
`printing` (meas=yard, stages proofing→pfp→screen→printing→inspect).

**B. Field baru di dokumen** (semua ber-index):

| Koleksi | Field | Aturan |
|---|---|---|
| `products` | `line_code: str` | WAJIB untuk produk baru; kosong = data lama = **tidak** ikut disaring (kompatibel) |
| `users` | `allowed_line_codes: [str]` | **kosong = semua lini** (bawaan). Diisi = pagar keras |
| `sales_orders.items[]`, `purchase_requisitions.items[]`, `purchase_orders.items[]`, `warehouse_transfers.items[]`, `sales_returns.items[]`, `purchase_returns.items[]`, `interco_transactions.items[]` | `line_code` (snapshot dari produk saat baris dibuat) | snapshot, bukan join — supaya riwayat tidak berubah saat master produk diubah |
| `sales_orders`, `purchase_orders`, `purchase_requisitions` | `line_codes: [str]` (turunan dari baris) | dipakai penyaringan daftar & papan |
| `md_specs`, `md_samples`, `design_requests`, `makloon_orders`, `inspections`, `inventory_rolls`, `inventory_lots` | `line_code` | roll & lot ikut snapshot domain yang sudah ada (`_domain_snapshot`) |

**C. Servis pagar** — `backend/services/line_scope.py` (**meniru** `product_exclusivity.py`):
* `visibility_query(actor, field="line_code") -> dict` → `{}` bila `allowed_line_codes`
  kosong; selain itu `{"$or":[{field:{"$in":allowed}},{field:{"$in":["",None]}}]}`
  (data lama tanpa lini tetap terlihat — kalau tidak, seluruh layar mendadak kosong).
* `assert_can_touch(actor, doc)` → HTTP **403** ber-kalimat Indonesia.
* Dipakai di **daftar** (query) **dan** di **aksi** (tulis) — dua-duanya, karena
  menyembunyikan di UI saja bisa ditembus lewat API.

**D. Endpoint**
* Master: sudah otomatis lewat `/api/entity-masters/product-lines`.
* `GET /api/enums` → tambah kunci `product_line` (dibaca dari master, lihat FASE T
  soal jembatan master↔registry).
* `PATCH /api/users/{id}` → terima `allowed_line_codes` (validasi ⊆ master aktif).
* Semua endpoint daftar yang menyentuh koleksi di tabel B → sisipkan
  `line_scope.visibility_query(actor)` + terima `?line=` (multi, dipisah koma).

**E. Layar**
* Chip penyaring **Woven · Knit · Printing · Semua** (dibangun dari master, **bukan**
  literal) di: Master Produk · Pesanan · Pesanan Pembelian · PR · Sample · Spesifikasi ·
  Desain · Roll/Stok · Transfer · Retur (jual & beli) · Makloon · Inspeksi.
  Komponen tunggal: `frontend/src/components/LineFilter.jsx`, pilihan tersimpan per
  pengguna (localStorage) — satu tempat, bukan 12 salinan.
* Layar "Akun & Akses": kolom + editor **Lini yang boleh diakses** (multi-pilih).

**F. Migrasi** — `scripts/migrate_lini_produk.py` (idempotent, ber-`--dry-run`):
1. Seed 3 baris master.
2. Isi `products.line_code` dari aturan terukur: `fabric_type=knit` → `knit`;
   `fabric_type=woven` **dan** produk punya `motif`/tautan desain printing → `printing`;
   sisanya `woven`. **Setiap keputusan ditulis ke laporan** supaya bisa dikoreksi
   manual (jangan menebak diam-diam).
3. Isi `line_code` mundur di dokumen baris dari `products` (backfill).

**G. POC** `backend/test_core_lini_poc.py` — membuktikan:
L1 master bisa **ditambah** (lini ke-4 "denim") tanpa satu baris kode diubah, dan
langsung muncul di `/api/enums` + penyaring layar.
L2 pengguna ber-`allowed_line_codes=["printing"]` **tidak** melihat produk woven
di `/api/products`, dan **403** saat mencoba membuat SO berisi produk woven.
L3 pengguna tanpa `allowed_line_codes` melihat semua (tanpa regresi).
L4 dokumen lama tanpa `line_code` tetap terlihat (tidak ada layar mendadak kosong).
L5 snapshot: mengganti `line_code` produk **tidak** mengubah baris SO yang sudah ada.

**H. Gate baru `INV-LINE-01`** (`scripts/guardrails/verify_line_scope.py`, ber-`--self-test`):
* setiap endpoint daftar pada koleksi ber-lini **wajib** memanggil `line_scope`;
* tidak ada literal `"woven"|"knit"|"printing"` di `frontend/src` (harus dari master);
* setiap koleksi di tabel B punya index `line_code`.

**Selesai bila:** POC 5/5 · gate hijau · 12 layar punya penyaring lini · laporan migrasi
nol produk "tak tergolong".

---

### FASE T — MASTER TAHAPAN PROSES (termasuk **Screen**) + jembatan ke registry

**Tujuan pemilik:** *"screen merupakan salah satu proses di makloon (tahapan), maka
tahapan makloon juga dibuatkan masternya, lalu setiap tahapan itu memiliki pekerjaan
di makloon siapa."*

**A. Master baru**

```
"process-stages": MasterSpec(
    kind="process-stages", collection="process_stages", label="Tahapan Proses",
    key_field="code", name_field="name", id_prefix="pstg",
    fields=("code","name","kind","applies_to_lines","seq","active","notes",
            "needs_vendor","process_type","changes_stage",
            "from_stage","to_stage","tariff_basis_default"))
```
* `kind`: `material` (Benang) · `makloon` (Tenun/Rajut/Celup/Printing/**Screen**) ·
  `sampling` (Proofing) · `inspection` (Inspect).
* `needs_vendor=true` → saat dipakai di SPK makloon **wajib** memilih mitra
  (`makloons` yang `process_types` memuat `process_type` tahap itu).
* `changes_stage=false` untuk **Screen** (membuat kasa/screen **tidak** memindahkan
  tahap kain) — ini yang mencegah mesin makloon menghitung output kain dari langkah
  yang sebenarnya tidak menghasilkan kain.

**B. Jembatan master ↔ `domain_registry` (titik paling rawan duplikat)**
Hari ini `PROCESS_TYPES` & `STAGE_TRANSITIONS` **hardcode** dan dipakai validasi
sinkron. Aturan yang dipakai:
* `domain_registry` tetap memegang **BENTUK + NILAI BENIH (seed)**;
* koleksi `process_stages` memegang **NILAI HIDUP**;
* satu pembaca: `backend/services/master_registry.py` → `async stages(entity_id)`,
  cache 60 detik, **fallback ke seed** bila koleksi kosong (instalasi baru tidak mati);
* `GET /api/enums` menyajikan hasil pembaca ini, sehingga layar tetap punya satu sumber.
* **Gate `INV-DOMAIN-06`**: nilai benih ⊆ master aktif (master boleh menambah, tidak
  boleh menghilangkan nilai yang sudah dipakai dokumen) — dibuktikan dengan menghitung
  dokumen yang memakai tiap nilai.

**C. Perubahan mesin makloon**
* `makloon_orders.steps[]` + `stage_code` (baru, dari master) di samping `process_type`
  (dipertahankan agar tarif/estimasi lama tetap jalan). Migrasi: `stage_code = process_type`.
* `services/makloon_service`: bila `changes_stage=false` → output = input (tanpa
  konversi hasil), biaya tetap dihitung; `estimate.explain[]` menuliskan alasannya
  ("tahap Screen tidak mengubah tahap kain — hanya biaya jasa").
* Seed tahap `screen` (kind=makloon, lini `printing`, needs_vendor=true, changes_stage=false).

**D. Endpoint**
* `GET /api/entity-masters/process-stages` (otomatis).
* `GET /api/process-stages/for-line/{line_code}` → urutan tahap untuk papan PO & SPK.
* `GET /api/makloons?process_type=screen` (sudah ada penyaringnya di layar mitra).

**E. Layar:** Pengaturan → Master → **Tahapan Proses** (generik) · pemilih tahap di
form SPK Makloon memakai master (bukan enum hardcode) · papan PO (FASE P) membaca
`product_lines.stage_sequence`.

**F. POC** `backend/test_core_tahapan_poc.py`:
T1 menambah tahap baru ("Sanforize") lewat API master → langsung muncul di form SPK
    makloon & papan PO tanpa perubahan kode.
T2 tahap `screen` bisa dipakai di SPK: mitra wajib dipilih, biaya masuk, **tahap kain
   tidak berubah**, dan `explain[]` menyebutkan alasannya.
T3 menghapus/menonaktifkan tahap yang masih dipakai dokumen **ditolak** (gate INV-DOMAIN-06).

**Selesai bila:** POC 3/3 · gate hijau · SPK makloon lama tetap bisa dibuka & dihitung
ulang dengan hasil **identik** (bukti regresi: bandingkan `estimate` sebelum/sesudah).

---

### FASE U — DUA SATUAN DI SEMUA DOKUMEN (jumlah roll + yard/kg/panel)

**Tujuan pemilik:** *"catat roll dan yard/kg dan panel — jadi ada 2 satuan yang
ditulis... dan ini seharusnya sudah ada di semuanya, di WMS, di sales, di SO dll."*

**A. Master satuan** (`uoms`) — tambah yang hilang:
* `KG` (`base_type="weight"`, `factor_to_base=1.0`) — hari ini `inventory_rolls.unit`
  sudah berisi `kg` **padahal satuannya tidak terdaftar** (lubang senyap yang ikut ditutup).
* `PANEL` (`base_type="count"`, `precision=0`).

**B. Bentuk data — MINIMAL, tanpa field kembar**
Setiap baris dokumen yang menyebut jumlah kain mendapat **satu** field baru:
`qty_rolls: int` (jumlah gulungan). Angka kedua **memakai field yang sudah ada**
(`quantity` + `unit`), sehingga **tidak ada dua tempat menyimpan hal yang sama**.
Untuk ukuran alternatif pada roll (mis. roll ber-yard yang juga ditimbang kg) dipakai
field yang **sudah ada tapi belum pernah diisi**: `inventory_rolls.secondary_measures`
→ diisi `{"kg": 12.5}` saat penerimaan.

**Koleksi yang WAJIB ikut** (diukur dari basis data — tidak boleh ada yang tertinggal):
`purchase_orders.items[]` · `purchase_requisitions.items[]` · `sales_orders.items[]` ·
`sales_returns.items[]` · `purchase_returns.items[]` · `warehouse_transfers.items[]` ·
`interco_transactions.items[]` · `interco_returns.items[]` · `internal_requests.items[]` ·
`rfqs.items[]` · `wms_tasks` (root) · `shipments` (root) · `inventory_movements` (root) ·
`makloon_orders.steps[]` (input & output) · `inspections.lines[]` (FASE I).

**C. Satu helper, bukan 15 salinan**
* Backend: `core_utils.qty_dual(rolls, measure, unit) -> str` + serializer dipakai PDF
  & CSV (`services/pdf_resolvers.py`, `utils/csvExport`).
* Frontend: komponen `<QtyDual rolls= measure= unit= />` → "12 roll · 540,5 yard".
* **Gate `INV-QTY-01`**: dilarang merangkai teks jumlah+satuan secara manual di layar
  (regex) — wajib lewat komponen itu; dan setiap koleksi di daftar B punya `qty_rolls`.

**D. Dari mana `qty_rolls` diisi**
* Penerimaan (`inbound/tasks/{id}/scan-receive`): jumlah roll = **hasil hitung roll yang
  benar-benar dibuat** (bukan diketik) → `wms_tasks.qty_rolls`, lalu diakumulasi ke
  `purchase_orders.items[].received_rolls` (turunan).
* SO/pengiriman: dari `allocations`/roll yang dipilih (mode `roll` sudah ada:
  `sales_orders.items[].roll_lines[]`).
* PO/PR/RFQ: **diketik** (rencana), karena saat memesan jumlah roll memang perkiraan.
* Retur: dari roll yang dikembalikan (`roll_ids[]` sudah ada di `PurchaseReturnItem`).

**E. POC** `backend/test_core_dua_satuan_poc.py`:
U1 PO 12 roll × 45 yard → terima 12 roll → **PO, GRN, kartu stok, papan PO, PDF, CSV**
   semuanya menyebut "12 roll · 540 yard" (satu sumber, enam tampilan).
U2 retur 2 roll → semua angka turun **serentak** (12→10 roll, 540→450 yard).
U3 lini knit memakai **kg**, printing memakai **panel** — satuan mengikuti master lini.
U4 dokumen lama tanpa `qty_rolls` tetap tampil (tanpa "0 roll" palsu — tampil "—").

**Selesai bila:** POC 4/4 · gate `INV-QTY-01` hijau · 15 koleksi punya field ·
tidak ada layar yang menampilkan "0 roll" untuk dokumen lama.

---

### FASE S — SAMPLING SUPPLIER: labdip · handfeel · proofing (BOLEH LEBIH DARI SATU)

**Tujuan pemilik:** *"daripada terlalu kaku, bisa dipilihkan lebih dari satu saja"* —
satu permintaan sampling boleh menempuh proofing **dan** labdip **dan** handfeel;
tiap iterasi punya **QC sample** dan **riwayat**.

**A. Master baru**
```
"sample-types": MasterSpec(
    kind="sample-types", collection="sample_types", label="Jenis Sampling",
    key_field="code", name_field="name", id_prefix="stype",
    fields=("code","name","applies_to_lines","seq","active","notes",
            "requires_design",        # proofing → wajib kode desain (perilaku lama)
            "measurement_fields"))    # field pengukuran yang muncul di form round
```
Seed: `labdip` (delta_e, colorfastness_wash, colorfastness_rub) ·
**`handfeel`** (gsm_actual, lebar, shrinkage_pct, **handfeel_score 1–5**) ·
`proofing` (requires_design=true, delta_e, repeat_cm, register) · `bulk_sample`
(dinonaktifkan bila pemilik tidak memakainya — **0 dokumen** di data hari ini).

**B. Perubahan `md_samples`**
* `sample_types: [str]` **menggantikan** `sample_type: str`.
  Migrasi `scripts/migrate_sample_types.py`: `sample_types=[sample_type]`, lalu
  **field lama dihapus** (bukan dibiarkan) supaya tidak ada dua sumber.
  Semua pembaca diubah: `rnd_sample_service` (validasi `requires_design`),
  `rnd_gate`, `rnd_kpi_service`, `approval_backlog_service` (label antrean),
  `routers/rnd.py`, layar `RndSamplesView.jsx`/`SampleFormModal.jsx`/`SampleDetailPanel.jsx`.
* `rounds[]` + `type_code` (round ini untuk jenis yang mana) — sehingga satu permintaan
  bisa punya round labdip #1, #2 dan round handfeel #1 secara **paralel & terpisah**.
* `rounds[].qc`: `{by, at, verdict}` — `verdict` memakai `result` yang **sudah ada**
  (`acc|revisi|tolak`); yang ditambah hanya siapa & kapan (hari ini hanya
  `assessed_by`/`assessed_at` untuk penilaian, belum untuk QC fisik sample).
* `md_samples.line_code` (FASE L) & `so_id` **dimunculkan di layar** (hari ini field
  ada tapi terisi 0 dari 28 dan tidak ada isiannya di form) + `customer_id`.
* Penanda selesai (gap S2 analisis): `finished_at`, `delivered_at`, `delivered_to`
  (`customer`/`sales`) → "sample sudah jadi & dikirim".

**C. Pustaka warna**: tambah `system="PANTONE"` (data, bukan skema) + penyaring sistem
warna di pemilih warna; `md_samples.color_target` sudah menyimpan `color_id/code/name/hex`.

**D. Endpoint** (semua sudah ada polanya, hanya diperluas)
* `POST /api/rnd/samples` — terima `sample_types[]`, `line_code`, `so_id`, `customer_id`.
* `POST /api/rnd/samples/{id}/rounds` — terima `type_code`.
* `POST /api/rnd/samples/{id}/rounds/{rid}/submit` — pengukuran mengikuti
  `measurement_fields` jenis itu (validasi dinamis dari master).
* **Baru**: `POST /api/rnd/samples/{id}/finish` (sample jadi) ·
  `POST /api/rnd/samples/{id}/deliver` (dikirim ke pelanggan/sales, wajib tujuan).
* Antrean: daftarkan `sample_delivery` bila perlu keputusan — kalau tidak, **jangan**
  didaftarkan (gate `INV-APPR-01` menuntut alasan tertulis untuk yang tidak didaftarkan).

**E. Layar**: form permintaan sampling multi-pilih jenis + tautan SO/pelanggan +
lini · papan iterasi per jenis (riwayat lengkap: siapa, kapan, hasil, lampiran) ·
tombol "Sample Jadi" & "Kirim".

**F. POC** `backend/test_core_sampling_poc.py`:
S1 satu permintaan dengan **dua jenis** (proofing + handfeel) → dua rangkaian round
   berjalan sendiri-sendiri, riwayat tidak tercampur.
S2 round handfeel menuntut `handfeel_score`; round labdip menuntut `delta_e`
   (validasi lahir dari master, bukan dari `if`).
S3 menutup round tetap **wajib lampiran + catatan** (perilaku lama tidak rusak).
S4 ACC → produk lahir (`release-product`) **dan** kontrak supplier terbit; keduanya
   ber-`refs` dua arah ke sample-nya.
S5 sample tertaut SO muncul di jejak dokumen SO tersebut.
S6 "jadi" & "dikirim" tercatat + terlihat di layar.

---

### FASE I — INSPEKSI & QC SEBAGAI DOKUMEN (SPK Inspeksi)

**Tujuan pemilik:** lembar `Inspect PO`, `Inspect Retur (per PT)`, `Inspect retur &
replacement` — dengan **SPK**, petugas, milestone, hasil warna & handfeel, keputusan.

**A. Koleksi baru `inspections`** (SATU koleksi, pembeda `kind` — bukan 3 koleksi):

```
inspections {
  id, number,                    # "KSC/INS-00001" (nomor per badan usaha)
  entity_id, line_code,
  kind,                          # po_receipt | makloon_output | return_customer
                                 # | return_supplier | replacement
  ref_doc_type, ref_doc_id, ref_doc_number,   # PO / MKO / retur — plus refs[] dua arah
  supplier_id/name | customer_id/name,
  spk_date, assigned_to, assigned_name, bagian,      # "Bagian Inspect"
  started_at, finished_at, status,                   # draft|assigned|in_progress|done|closed
  baseline_sample_id, baseline_sample_number,        # acuan: labdip/handfeel yang ACC
  baseline_contract_id,
  summary { rolls, measure, unit, points_total, grade_after_counts{A:..,B:..} },
  decision,                      # terima | terima_sebagian | turun_grade | tolak
  remark, history[], refs[]
}
inspections.lines[] {
  id, roll_id, roll_no, lot, dye_lot, product_id, article, sku,
  color_id, color_code, qty { rolls, measure, unit },
  defects[] {code, point_value, count, note},  points,
  gsm_actual, width_actual,
  color_result,      # sesuai | beda_shade | tolak     (+ delta_e opsional)
  handfeel_result,   # sesuai | beda | tolak           (+ handfeel_score 1..5)
  grade_before, grade_after, decision, remark,
  inspected_by, inspected_at
}
```
Index: `(entity_id, status)`, `(kind, ref_doc_id)`, `(line_code)`, `(assigned_to,status)`,
`lines.roll_id`.

**B. ATURAN ANTI-DUPLIKAT (penting)**
1. **Grade tetap hanya berubah lewat `grade_service.set_roll_grade(source="qc_inspection")`.**
   `inspections.lines[].grade_after` adalah **catatan hasil** panggilan itu, bukan sumber.
   Gate `INV-QC-02` membuktikan: untuk setiap baris inspeksi yang mengubah grade, ada
   entri `inventory_rolls.grade_history` yang cocok (roll, waktu ±, sumber) — dan
   sebaliknya tidak ada grade berubah tanpa dokumen inspeksi bila sumbernya `qc_inspection`.
2. **Poin cacat & ambang grade tetap dihitung `qc_inspection_service`** (`compute_points`,
   `grade_from_points`, ambang `qc.grade_thresholds`) — tidak ditulis ulang.
3. Dokumen inspeksi **melengkapi**, bukan menggantikan, tugas `qc_pending`: saat tugas
   masuk `qc_pending`, dokumen inspeksi `po_receipt` **lahir otomatis** dan layar QC lama
   diarahkan ke sana (tidak ada dua pintu).

**C. Warna & handfeel ikut menentukan keputusan (gap yang pemilik tekankan)**
Grade **tetap** dari poin cacat (mesin lama tak diubah). Yang baru: `decision` per baris
& per dokumen mempertimbangkan `color_result` + `handfeel_result`. Kebijakan di Pusat
Pengaturan (`qc.color_mismatch_action`, `qc.handfeel_mismatch_action`:
`abaikan|peringatkan|tahan`) — bila `tahan`, roll tidak boleh putaway sebelum ada
keputusan manusia. **Tanpa kebijakan ini keputusan akan tersembunyi di kepala petugas.**

**D. Endpoint**
```
POST   /api/inspections                      (dari PO/MKO/retur; kind + ref)
GET    /api/inspections?kind=&status=&line=&assigned_to=&q=   (berhalaman + CSV)
GET    /api/inspections/{id}
POST   /api/inspections/{id}/assign          {assigned_to, bagian}
POST   /api/inspections/{id}/start
POST   /api/inspections/{id}/lines/{lid}/inspect
        {defects[], gsm_actual, width_actual, color_result, handfeel_result,
         handfeel_score, remark}             → memanggil grade_service
POST   /api/inspections/{id}/finish          {decision, remark}   (wajib alasan bila tolak)
POST   /api/inspections/{id}/reopen          {reason}             (wajib alasan)
GET    /api/inspections/{id}/pdf             (SPK + hasil — lewat platform dokumen G-4)
```
Izin baru di `permissions_config`: resource **`inspection`** →
`admin/manager`: view·create·assign·inspect·decide·reopen ·
`warehouse`: view·inspect · `sales_admin`: view.

**E. Retur ikut lengkap** (`sales_returns` — milestone dari lembar pemilik):
`shipped_to_store_at` (SJ Kirim Toko) · `shipped_to_customer_at` (Kirim ke Cust) ·
`goods_arrived_at` (Barang Sampai) · `inspection_id` · `inspect_done_at` ·
`complaint_code` + `complaint_note` (master `complaint-reasons` — kecil, ikut MasterSpec) ·
`qty_rolls` (FASE U). Layar retur menampilkan **garis waktu** milestone itu.

**F. POC** `backend/test_core_inspeksi_poc.py`:
I1 PO diterima → dokumen inspeksi `po_receipt` **lahir otomatis** berisi baris per roll.
I2 petugas ditugaskan → status berjalan draft→assigned→in_progress→done.
I3 baris ber-cacat 24 poin → grade **B**; dan `grade_history` roll bertambah **tepat satu**
   dengan sumber `qc_inspection` (bukti anti-duplikat).
I4 `color_result="beda_shade"` dengan kebijakan `tahan` → roll **tidak bisa** putaway,
   pesannya menuntun ke keputusan.
I5 acuan sample terlihat: dokumen menyebut "acuan Labdip KSC/SMP-00003 · Pantone 19-4052".
I6 retur pelanggan → inspeksi `return_customer` + milestone terisi + qty dual.
I7 tutup inspeksi dengan keputusan `tolak` **wajib alasan**; alasan tersimpan di dokumen
   (bukan hanya jejak audit).
I8 nol residu.

---

### FASE P — PAPAN PO PER LINI (progres tahap seperti kertas kerja MD)

**A. Field baru `purchase_orders`**
| Field | Isi | Sumber |
|---|---|---|
| `line_code`, `line_codes[]` | lini | FASE L |
| `sales_user_id`, `sales_name` | **user yang membuat SO asalnya** | dirunut PR (`source="so_repeat"`, `source_ref_id=so_id`) → SO `created_by` |
| `source_so_ids[]` | SO yang memicu | dari PR + `refs[]` |
| `stage_progress[]` | `[{stage_code,status,at,by,note}]` | dibentuk dari `product_lines.stage_sequence`; **diinput manusia** kecuali `inspect` |
| `eta_ready` | Estimasi Ready | pakai `expected_delivery_date` yang sudah ada (jangan bikin field kedua) |
| `first_receipt_at`, `last_receipt_at` | Tanggal Masuk | **dihitung** dari GRN (`wms_tasks`), tidak diketik |
| `received_rolls`, `received_measure` | Qty terima | **dihitung** dari roll yang lahir |

Tahap `inspect` **tidak** diklik manusia: statusnya diturunkan dari dokumen inspeksi
(`draft/assigned/in_progress` → proses; `done/closed` → selesai). Ini mencegah papan
mengaku "sudah diinspeksi" tanpa dokumen.

**B. Endpoint**
```
GET   /api/purchase-orders/board?line=&status=&q=      → papan per lini (berhalaman)
PATCH /api/purchase-orders/{id}/stage {stage_code,status,note}   (izin purchase_order.update)
```

**C. Layar** `frontend/src/features/purchasing/PoBoardView.jsx` — kolom persis kertas
kerja: Nama Sales · No PO · Nama Item · Qty (**dual**) · Warna · Tanggal Order ·
Estimasi Ready · **tahap berjalan** (chip urut sesuai lini) · Tanggal Masuk ·
Qty Terima (dual) · Keterangan. Ganti tab per lini memakai master (bukan 4 blok statis).

**D. POC** `backend/test_core_po_board_poc.py`:
P1 PO lini woven menampilkan **tepat** urutan benang→tenun→celup→inspect; printing
   menampilkan proofing→pfp→screen→printing→inspect (dari master, bukan hardcode).
P2 `sales_name` terisi dari SO asal (dirunut lewat PR) — bukan diketik.
P3 tahap `inspect` **tidak bisa** ditandai selesai manual; ia mengikuti dokumen inspeksi.
P4 tanggal masuk & qty terima **berubah sendiri** setelah penerimaan (dihitung).
P5 papan menghormati pagar lini (staf printing tidak melihat PO woven).

---

### FASE D — PERMINTAAN DESAIN ("Design PO") + rapor desainer

**A. Koleksi baru `design_requests`**
```
design_requests {
  id, number,                 # KSC/DSR-00001
  entity_id, line_code,
  source,                     # so | customer | internal
  so_id, so_number, customer_id, customer_name,
  requested_by, requested_at,
  assigned_to, assigned_name, division,      # designer
  due_date, brief, target_type,              # motif|pattern|artwork
  color_targets[] {color_id, code, name, hex},
  status,                     # draft|submitted|assigned|in_progress|delivered|approved|revision|cancelled
  gallery_ids[],              # hasil kerja → design_gallery (1..n versi)
  decided_by, decided_at, reject_reason,
  history[], refs[]
}
```
`design_gallery` + `request_id` (tautan balik). **Batas tegas antar dokumen** (agar tidak
jadi dokumen ke-3 yang tumpang tindih):
* `design_requests` = **pekerjaan siapa & kapan** (penugasan, tenggat, status)
* `design_gallery` = **artwork-nya** (berkas, versi, kode, ACC, nilai bintang)
* `md_specs` = **angka tekniknya** (gramasi, lebar, konstruksi) → melahirkan produk

**B. Endpoint**
```
POST /api/design-requests · GET (filter lini/status/assigned_to/so) · GET /{id}
POST /api/design-requests/{id}/submit | /assign {assigned_to,due_date} | /deliver {gallery_id}
POST /api/design-requests/{id}/approve | /reject {reason}   (alasan WAJIB)
GET  /api/design/reports/by-designer?period=&line=
     → per desainer: diminta · dikerjakan · diserahkan · ACC · revisi ·
       rata-rata hari kerja · rata-rata bintang (dari design_gallery.ratings)
```
Antrean: daftarkan `design_request` ke `approval_backlog_service.QUEUES`
(status `delivered` = menunggu keputusan) — **wajib**, kalau tidak gate `INV-APPR-01` merah.

**C. Layar**: papan penugasan desain (kanban per status, tenggat menyala bila lewat) ·
rapor desainer · tombol "Tugaskan" di galeri.

**D. POC** `backend/test_core_design_request_poc.py`: penugasan → tenggat → serah →
ACC/revisi ber-alasan → rapor **cocok** dengan hitung ulang mandiri dari MongoDB →
muncul di antrean keputusan & KPI beranda.

---

### FASE N — NOTIFIKASI SAMPAI KE ORANG YANG BENAR (gap berkas pertama)

1. `ar_due_soon` → tambah penerima **finance** (hari ini hanya sales+manager; kotak
   finance terukur **nol**).
2. `low_stock` → berhenti `recipient_role="all"`; kirim ke pemegang wewenang beli
   (`purchase_order.create`) + **divisi MD** bila diisi. Terukur hari ini: finance &
   sales masing-masing menerima **9** notifikasi yang bukan urusannya.
3. **PO custom** (`special_orders`) → notifikasi saat diajukan (hari ini **nol**).
4. Notifikasi baru: sampling menunggu QC · inspeksi ditugaskan ke saya · permintaan
   desain ditugaskan/lewat tenggat · tahap PO macet > N hari.
5. **Alamat berbasis wewenang & divisi**: `create_notification(..., recipient_permission=("purchase_order","create"), recipient_division="md")`
   → satu penyelesai penerima (`services/notification_audience.py`), dedupe per orang.
   Gate `INV-NOTIF-02`: dilarang mengirim dengan `recipient_role="all"` untuk peristiwa
   yang punya pemilik jelas.

---

### FASE M — MAKLOON (jalur "buat sendiri") ikut lengkap

* `makloon_orders`: `line_code`, `steps[].stage_code` (FASE T), dual qty (FASE U) pada
  input & output tiap langkah.
* Output makloon diterima → **dokumen inspeksi `makloon_output`** (FASE I) → grading →
  gudang → lanjut pemenuhan SO/PO.
* Papan SPK makloon per lini memakai urutan tahap dari master (sama seperti papan PO).
* POC `backend/test_core_makloon_lini_poc.py`: rantai benang→tenun→celup menghasilkan
  roll ber-grade lewat inspeksi, dan **biaya per tahap** tercatat; tahap `screen` di
  jalur printing menambah biaya tanpa mengubah tahap kain.

---

## 4. PETA RELASI DOKUMEN (yang WAJIB tertulis lewat `doc_refs_service`)

```
design_requests ──child──▶ design_gallery ──child──▶ md_specs ──child──▶ md_samples
      │                                                    │                  │
      └── parent: sales_orders (bila source=so)            │                  ├─child─▶ supplier_contracts
                                                           └─child─▶ products │
supplier_contracts ──child──▶ purchase_requisitions ──child──▶ purchase_orders
purchase_orders ──child──▶ wms_tasks(GRN) ──child──▶ inventory_rolls/lots
purchase_orders ──child──▶ inspections(kind=po_receipt) ──ref──▶ md_samples (baseline)
makloon_orders  ──child──▶ inspections(kind=makloon_output)
sales_returns   ──child──▶ inspections(kind=return_customer)
sales_orders    ──child──▶ (alur pemenuhan yang sudah ada)
```
Kosakata `rel` memakai `REL_INVERSE` yang sudah ada — **jangan** menambah kosakata baru
tanpa mendaftarkannya di sana (gate INV-REF akan memerah).

---

## 5. RINGKASAN PERUBAHAN PER LAPISAN

**Koleksi BARU (5):** `product_lines` · `process_stages` · `sample_types` ·
`inspections` · `design_requests` (+ `complaint_reasons` kecil).
**Koleksi DIPERLUAS (17):** products · users · sales_orders · purchase_orders ·
purchase_requisitions · purchase_returns · sales_returns · warehouse_transfers ·
interco_transactions · interco_returns · internal_requests · rfqs · wms_tasks ·
shipments · inventory_movements · inventory_rolls · makloon_orders.
**Servis BARU (4):** `line_scope.py` · `master_registry.py` · `inspection_service.py` ·
`notification_audience.py`.
**Servis DIUBAH (9):** rnd_sample_service · qc_inspection_service (dipanggil dari
inspeksi) · makloon_service · restock_service (jejak sales) · roll_service
(secondary_measures) · return_service (milestone) · approval_backlog_service (+2 antrean) ·
alert_ops_service · notification_service.
**Migrasi (4):** `migrate_lini_produk.py` · `migrate_process_stages.py` ·
`migrate_sample_types.py` · `migrate_qty_rolls.py` — semuanya **idempotent + `--dry-run`
+ laporan keputusan**.
**Gate BARU (6):** `INV-LINE-01` · `INV-DOMAIN-06` · `INV-QTY-01` · `INV-QC-02` ·
`INV-NOTIF-02` (+ perluasan `INV-APPR-01` untuk 2 antrean baru).
**POC BARU (8):** lini · tahapan · dua satuan · sampling · inspeksi · papan PO ·
permintaan desain · makloon-lini.

---

## 6. URUTAN & KETERGANTUNGAN

| Urut | Fase | Bergantung pada | Kenapa urutannya begini |
|---|---|---|---|
| 1 | **L** Lini | — | Fondasi penyaring & papan; menundanya = mengerjakan ulang 12 layar |
| 2 | **T** Tahapan | L | Urutan tahap milik lini; "Screen" lahir di sini |
| 3 | **U** Dua satuan | — (paralel dengan T) | Menyentuh 15 koleksi; makin lama makin mahal |
| 4 | **S** Sampling | L, U | Handfeel + multi-jenis + tautan SO |
| 5 | **I** Inspeksi/QC | U, S | Butuh baris dual-qty & acuan sample ACC |
| 6 | **P** Papan PO | L, T, I | Tahap `inspect` diturunkan dari dokumen inspeksi |
| 7 | **D** Permintaan desain | L | Berdiri sendiri; menyambung ke sampling |
| 8 | **N** Notifikasi | D, I, P | Supaya sekalian mencakup peristiwa baru |
| 9 | **M** Makloon | T, U, I | Menutup jalur "buat sendiri" |

Tiap fase ditutup: POC hijau → `gate.sh --full` hijau → agen uji UI → `plan.md` diperbarui.

---

## 7. RISIKO YANG SUDAH TERLIHAT (dan penangkalnya)

1. **`process_type` hardcode dipakai validasi sinkron.** Penangkal: jembatan
   `master_registry` + gate `INV-DOMAIN-06` (seed ⊆ master; nilai yang dipakai dokumen
   tidak boleh hilang).
2. **Tahap "Screen" tidak mengubah tahap kain** — mesin makloon menghitung output dari
   `STAGE_TRANSITIONS`. Penangkal: `changes_stage=false` + uji regresi yang membandingkan
   `estimate` SPK lama sebelum/sesudah (harus identik).
3. **Grade punya dua calon sumber** setelah dokumen inspeksi lahir. Penangkal: gate
   `INV-QC-02` mencocokkan baris inspeksi ↔ `grade_history` dua arah.
4. **Pagar lini bisa membuat layar kosong** bagi akun lama. Penangkal: `allowed_line_codes`
   kosong = semua lini, dan dokumen tanpa `line_code` selalu terlihat; POC L3 & L4 menjaganya.
5. **`sample_type` → `sample_types[]`** menyentuh KPI & antrean. Penangkal: migrasi
   menghapus field lama (bukan menyisakan dua), + pencarian sisa pembaca lewat gate.
6. **Data demo harus ikut kaya**, kalau tidak fitur "hijau tapi hampa": seed wajib
   menghasilkan minimal 1 permintaan desain, 1 sampling multi-jenis, 1 inspeksi PO,
   1 inspeksi retur, 1 SPK makloon jalur printing (dengan Screen), PO di tiap lini.

---

## 8. YANG MASIH MENUNGGU KEPUTUSAN PEMILIK (tidak menghalangi FASE L–U)

1. **Panel** — 1 panel itu satuan tetap (mis. 1 panel = X yard) atau bebas per pesanan?
   (Menentukan apakah `PANEL` butuh faktor konversi.)
2. **Screen** — perlu mencatat **jumlah screen** (galeri desain sudah punya
   `screen_count`) & **biaya per screen**, atau cukup tanda "sudah/belum"?
3. **Jenis sampling per lini** — usulan bawaan: woven/knit → labdip + handfeel;
   printing → proofing (+ labdip bila perlu). Tetap bisa dipilih lebih dari satu.
4. **`bulk_sample`** (0 dokumen) — dipertahankan atau dinonaktifkan?
5. **Kebijakan warna/handfeel beda** saat inspeksi: `abaikan` · `peringatkan` · `tahan`
   (usulan saya: **tahan** untuk warna, **peringatkan** untuk handfeel).
