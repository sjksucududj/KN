# KN — Development Plan dari Hasil Assessment
## Acuan Resmi Planning Development ERP Enterprise + RFID — Kain Nusantara Group

> **Sumber:** *Dokumen Hasil Assessment & Data Requirement ERP Enterprise & RFID Implementation* — disusun PT. Kubus Teknologi Indonesia.
> **Disusun oleh:** Tim Development (E2/Emergent) — 15 Jun 2026.
> **Status dokumen:** DRAFT v1 — menunggu konfirmasi & prioritas dari user (Vendor IT).
> **Sifat:** Planning/architecture only. **BELUM ADA CODING.** Setiap penambahan collection/endpoint/menu WAJIB melewati ENTITY_REGISTRY.md + KN_13 sesuai guardrail.

---

## 0. Cara Membaca Dokumen Ini
- **Bagian 1** — Ringkasan assessment (apa yang diminta).
- **Bagian 2** — Gap Analysis: kebutuhan assessment vs **sistem eksisting** (Sudah Ada / Parsial / Belum Ada). Ini inti "review & mapping" agar development terarah & tanpa konflik data.
- **Bagian 3** — Cross-cutting architecture decisions (multi-entity, pajak, notifikasi/real-time, RFID) yang memengaruhi banyak modul.
- **Bagian 4** — Roadmap 6 fase (selaras assessment) + detail per fase: scope, entitas baru, endpoint, menu, business rules, acceptance criteria.
- **Bagian 5** — Rencana Data Migration.
- **Bagian 6** — Keputusan & pertanyaan terbuka yang HARUS dijawab user sebelum coding.
- **Bagian 7** — Rekomendasi prioritas & quick wins.

---

## 1. Ringkasan Assessment (What the Client Wants)

**Konteks bisnis:** Kain Nusantara Group = konglomerasi tekstil multi-entitas (mis. **PT Kain Suka Cita**, **CV Kanda Suka**), multi-lokasi gudang (**Bandung, Jakarta, Tamim**). Operasional saat ini manual & terfragmentasi.

**5 Pain Point utama (as-is):**
1. UI/UX belum user friendly.
2. Tingkat error input tinggi (validasi minim).
3. Integrasi antar divisi belum optimal (Sales/Finance/Warehouse/HRD tidak real-time).
4. Monitoring belum real-time (laporan periodik, rekap manual).
5. Kontrol harga & outstanding masih manual (rawan kecurangan).

**Target (to-be):** Ekosistem digital terintegrasi, terukur, real-time, mendukung pertumbuhan — mencakup Sales, HRD, Purchasing, Finance, Warehouse, RFID, dan BI.

**Roadmap 6 fase (versi assessment):**
| Fase | Modul | Inti |
|------|-------|------|
| 1 | Sales & Marketing | master customer, katalog, SO, invoice, approval harga, multi-entity, PPN |
| 2 | HRD | absensi fingerprint, KPI design, gallery motif (AI Gemini) |
| 3 | Purchasing (MD) | master supplier, approval beli, BOM printing, kas, toleransi ±2% |
| 4 | Finance & Accounting | multi-entity, multi-bank, COA fleksibel, tax (PPN/PPH/Coretax), closing, outstanding+denda |
| 5 | Warehouse & RFID | multi-gudang, allocation/trend, transfer, notif real-time, RFID tracking |
| 6 | Additional | Creative & design, com-hub, dll (by request) |

**Business rules / angka spesifik (WAJIB dipatuhi):**
- Toleransi kedatangan benang: **±2%** dari qty PO.
- Denda keterlambatan piutang: **1%–3%** dari nilai outstanding.
- Dead stock: **> 3 bulan** tidak terjual.
- Closing bulanan: dukung tanggal **28 / 30 / 31**.
- Backup UPS RFID: tahan **≥ 30 menit** saat listrik padam.
- Alarm gate RFID: **Green** = valid, **Red** = tidak valid/tidak terdaftar → notifikasi supervisor.

---

## 2. GAP ANALYSIS — Assessment vs Sistem Eksisting (KN4)

> Legend: ✅ **Sudah Ada** · 🟡 **Parsial** (perlu enhancement) · ❌ **Belum Ada** (perlu build).
> Sistem eksisting = 23 router FastAPI, 22 koleksi kanonik, frontend React role-based. Kontrak aktual: auth Bearer `sess_`+SHA256, response array langsung, prefix `/api` ("code wins").

### 2.1 Fase 1 — Sales & Marketing
| Kebutuhan Assessment | Status | Catatan / Gap konkret |
|---|---|---|
| Master Customer | 🟡 | Ada `customers` (code, name, city, type, pic_name, addresses). **Gap:** `npwp`, `credit_limit/plafond`, `sales_pic`, `entity_id`, status aktif granular. |
| Master Produk + katalog | 🟡 | Ada `products` (sku, name, category, variant, color, motif, grade, base_unit, price, image). **Gap:** `gramasi`, `harga_pokok` (saat ini hanya `price`=harga jual), `entity_id`. |
| Sales Order | 🟡 | Ada `sales_orders` (items, allocations, status, payment_status, tax). **Gap:** status lifecycle assessment (Pending/Keep/Ready/Waiting Shipment/Partial/Complete), `entity_id`, PPN/faktur. |
| Invoice | 🟡 | Router `invoices` ada tapi pembayaran **SIMULATED**, koleksi kosong. **Gap:** faktur pajak, integrasi AR/outstanding nyata. |
| **Approval Harga** (Sales→Negosiasi→Upload Bukti→Approval Owner→Disetujui) | ❌ | Approval saat ini hanya approve ORDER, bukan negosiasi harga + upload bukti + approval owner. Perlu workflow + attachment. |
| **Multi-Entity** (PT Kain Suka Cita / CV Kanda Suka) | ❌ | Tidak ada konsep entitas. **Cross-cutting** (lihat 3.1). |
| **PPN / Non-PPN + Faktur Pajak** | ❌ | Ada field `tax` numerik di SO, tapi tanpa logika PPN/non-PPN, nomor faktur, e-faktur/Coretax. |
| **Special Price per Customer** | ❌ | Harga produk tunggal; belum ada price-list/diskon per customer/kategori. |
| **Status Pending Order** | ❌ | Perlu state machine: Pending/Keep/Ready/Waiting Shipment/Partial/Complete. |
| **Return & BS** (barang sisa/cacat) | ❌ | Belum ada modul retur/tukar. |
| **Special Order (OD)** custom/non-custom | ❌ | Belum ada (estimasi produksi). |
| **Ecommerce Catalog** publik | 🟡 | Ada katalog internal (Sales POS). **Gap:** katalog publik (foto, harga, stok ready). |

### 2.2 Fase 2 — HRD
| Kebutuhan | Status | Catatan |
|---|---|---|
| Absensi Fingerprint | ❌ | Belum ada modul HRD sama sekali. Perlu integrasi/import data mesin fingerprint. |
| Monitoring kehadiran/keterlambatan | ❌ | Belum ada. |
| KPI Design (jumlah/kualitas desain) | ❌ | Belum ada. |
| Gallery Design + AI Gemini (analisa motif) | ❌ | Belum ada. Integrasi LLM (Gemini) → butuh playbook + key. |

### 2.3 Fase 3 — Purchasing (MD)
| Kebutuhan | Status | Catatan |
|---|---|---|
| Purchase Order | 🟡 | Ada `purchase_orders` (items, supplier_name string, warehouse_id, status). |
| **Master Supplier** | ❌ | Supplier masih **string** (`supplier_name`/`product.supplier`). Perlu koleksi `suppliers` master. |
| Alur approval pembelian (request→review→approve owner) | 🟡/❌ | Status PO ada, workflow approval bertingkat belum eksplisit. |
| Integrasi Printing (BOM benang & bahan) | ❌ | Belum ada. |
| Pengelolaan Kas (kas kecil per entitas, kas besar gabungan) | ❌ | Belum ada. |
| Toleransi kedatangan **±2%** | ❌ | Belum ada validasi toleransi saat receiving. |

### 2.4 Fase 4 — Finance & Accounting
| Kebutuhan | Status | Catatan |
|---|---|---|
| Multi-Entity Accounting (Bandung/Jakarta, PT/CV) | ❌ | Cross-cutting (3.1). |
| Multi-Bank Account (PT/CV/owner/pribadi) | ❌ | Perlu `bank_accounts`. |
| Flexible Chart of Account + Jurnal/GL | ❌ | Belum ada GL/COA/journal. Modul akuntansi penuh. |
| Tax Module (PPN, PPH, Coretax) | ❌ | Belum ada. |
| Monthly Closing (28/30/31) | ❌ | Belum ada. |
| **Outstanding Customer + Reminder + Denda 1–3%** | ❌ | Belum ada AR aging, credit-limit enforcement, reminder, denda. |

### 2.5 Fase 5 — Warehouse & RFID
| Kebutuhan | Status | Catatan |
|---|---|---|
| Inventory multi-gudang (balances/movements) | ✅ | `inventory_balances`, `inventory_movements`. |
| Struktur gudang Zone/Rack/Bin | 🟡 | Ada Zone/Rack/Bin di `warehouses`. **Gap:** assessment minta tambah **Level** (Zone→Rack→**Level**→Bin). |
| Transfer antar gudang | ✅ | `warehouse_transfers` (+ lifecycle, baru di-refactor). |
| Cycle Count | ✅ | `cycle_count_sessions`. |
| Inbound/Outbound (receiving/picking) | ✅ | `inbound_receiving`, `outbound_picking`, `wms_tasks`. |
| **Stock Allocation + Trend** (fast/slow/dead >3bln) | ❌ | Belum ada analitik klasifikasi stok. |
| **Notifikasi Real-Time** (stok menipis, kedatangan, transfer, dead stock) | ❌ | Belum ada notifikasi/WebSocket. |
| **RFID** (tag, printer, reader, handheld, gate, alarm, server) | ❌ | Belum ada sama sekali (hanya arsitektur). Hardware + edge agent. |
| Kontinjensi RFID (SOP padam, UPS 30’, manual, recovery) | ❌ | SOP + fallback manual. |

### 2.6 BI / Analytics
| Kebutuhan | Status | Catatan |
|---|---|---|
| Dashboard dasar | 🟡 | Ada `dashboard`/`reporting` (KPI dasar). |
| Fast/Slow/Dead stock, Product/Fashion trend | ❌ | Belum ada. |
| Brand performance, Gross profit by category | ❌ | Belum ada. |
| Outstanding monitoring, Sales by territory, KPI sales per rep | ❌ | Belum ada. |

### 2.7 Ringkasan Skor Kesiapan
| Fase | Kesiapan eksisting (estimasi) |
|---|---|
| Fase 1 Sales | ~40% (fondasi SO/customer/produk ada, fitur lanjutan belum) |
| Fase 2 HRD | ~0% |
| Fase 3 Purchasing | ~30% (PO dasar ada, supplier master & workflow belum) |
| Fase 4 Finance | ~10% (invoice simulated saja) |
| Fase 5 Warehouse | ~65% (WMS kuat; RFID & analitik belum) |
| Fase 6 Additional | ~0% |
| BI | ~20% |

> **Insight kunci:** Sistem eksisting adalah **fondasi WMS/Sales yang kuat** namun BELUM menyentuh Finance/Akuntansi penuh, HRD, Supplier master, Multi-Entity, dan RFID. Multi-Entity & Tax adalah perubahan **arsitektural lintas modul** → harus diputuskan paling awal agar tidak rework.

---

## 3. Cross-Cutting Architecture Decisions (Putuskan Lebih Dulu)

### 3.1 Multi-Entity (PALING KRITIS — fondasi semua fase)
- Tambah koleksi **`business_entities`** (PT Kain Suka Cita, CV Kanda Suka, dst: nama legal, NPWP, alamat, default PPN/non-PPN, prefix dokumen).
- Tambah `entity_id` ke: `customers`, `products`(opsional/sharing), `sales_orders`, `invoices`, `purchase_orders`, dan semua koleksi finance.
- **Dampak data eksisting:** perlu migrasi — set `entity_id` default untuk data lama (mis. entitas "Default/PT Utama"). Backfill aman karena guardrail (number-series & integrity).
- Nomor dokumen per-entitas (SO/INV/PO/Faktur) → series terpisah.
- **Keputusan user:** Berapa entitas? Apakah produk & gudang di-share lintas entitas atau terpisah?

### 3.2 Tax / PPN / Faktur Pajak / Coretax
- PPN 11% (atau sesuai regulasi terbaru), flag PPN/Non-PPN per entitas/customer/SO.
- Nomor faktur pajak + export. **Coretax** = integrasi DJP (butuh kredensial & API resmi → kemungkinan fase lanjutan/manual export dulu).
- **Keputusan user:** Integrasi e-Faktur/Coretax otomatis atau cukup generate faktur + export manual di v1?

### 3.3 Notifikasi & Real-Time
- Assessment minta monitoring real-time (stok, piutang, sales, RFID alarm).
- Opsi v1: **polling + in-app notification center** (koleksi `notifications`) — cepat, no infra.
- Opsi v2: **WebSocket** (sesuai KN_05) untuk push real-time + RFID gate events.
- **Keputusan user:** mulai dengan polling/notification center dulu (rekomendasi), upgrade WebSocket saat RFID.

### 3.4 RFID (hardware + edge)
- Software ERP hanya satu sisi; perlu **hardware** (printer/reader/handheld/gate/server/alarm) + **edge agent** (MQTT/HTTP) dari vendor RFID.
- ERP menyediakan: master lokasi RFID (Zone/Rack/Level/Bin), registrasi tag↔item, endpoint ingest event, validasi gate (green/red), audit.
- **Keputusan user:** vendor RFID & protokol (MQTT?) — di luar kendali app; app siapkan API ingest + simulator untuk testing.

### 3.5 Kepatuhan Guardrail (WAJIB di setiap fase)
- Semua entitas baru → daftarkan di **ENTITY_REGISTRY.md** dulu (hindari nama terlarang: `stock`, `orders`, `inbound_tasks`, dll).
- Semua menu baru → daftarkan di **KN_13_NAVIGATION_MAP.md**.
- Ikuti kontrak aktual (Bearer `sess_`, response array, `/api`). File ≤500 (jsx)/≤800 (py)/≤300 (util).
- Gates hijau sebelum "selesai": validate_compliance, ux_audit, verify_contract, data_integrity, api_contract.

---

## 4. Roadmap Pengembangan (6 Fase, Selaras Assessment)

> Urutan mengikuti assessment, **tapi Fase 0 (Multi-Entity & Tax foundation) disisipkan lebih dulu** karena lintas modul. Setiap fase: V1 fungsional → testing agent → gates hijau → demo.

### FASE 0 — Foundation: Multi-Entity + Tax + Notification Center (Enabler)
**Tujuan:** Menyiapkan fondasi lintas modul sebelum membangun fitur Sales lanjutan.
- **Entitas baru (register dulu):** `business_entities`, `notifications`.
- **Schema enhancement:** tambah `entity_id` ke `customers`, `sales_orders`, `invoices`, `purchase_orders`; tambah `npwp`, `credit_limit`, `sales_pic` ke `customers`; `harga_pokok`, `gramasi` ke `products`.
- **Endpoint:** CRUD `business_entities`; entity selector context; notification list/read.
- **Frontend:** entity switcher (global), Notification Center (bell + dropdown), field baru di Admin master data.
- **Migrasi data:** backfill `entity_id` default untuk data eksisting.
- **Acceptance:** semua list/transaksi terfilter per entitas; data lama tetap valid (data_integrity 64/0/0 tetap hijau).

### FASE 1 — Sales & Marketing (Prioritas Utama)
**Scope fitur:**
1. **Special Price per Customer** → `customer_price_lists` (per customer/kategori/produk, diskon, periode).
2. **Approval Harga** → `price_approvals` (Sales ajukan → negosiasi → upload bukti (attachment) → approval Owner → harga disetujui). Reuse pola attachment dari modul Discovery.
3. **Status Pending Order** → perluas state machine SO: Pending/Keep/Ready/Waiting Shipment/Partial/Complete.
4. **PPN/Non-PPN + Faktur Pajak** → field & generator faktur per entitas (export PDF; Coretax fase lanjut).
5. **Return & BS** → `sales_returns` (retur, tukar, barang sisa/cacat + dampak stok).
6. **Special Order (OD)** → custom/non-custom + estimasi.
7. **Ecommerce Catalog** (opsional/akhir fase) → katalog publik read-only (foto, harga, stok ready).
- **Menu baru (KN_13):** Price Approval, Returns, (Catalog publik = route terpisah seperti Discovery).
- **Business rules:** credit-limit check saat buat SO (blokir bila lewat plafond — link ke Fase 4).
- **Acceptance:** SO lengkap dengan harga khusus, approval owner, faktur PPN, retur memengaruhi stok, status order akurat.

### FASE 2 — HRD
**Scope:**
- **`employees`** (data karyawan, jabatan, divisi, entitas).
- **`attendance_records`** (import data fingerprint — CSV/format mesin; jam masuk/keluar, telat, durasi).
- **`kpi_records`** (KPI design: jumlah & kualitas desain, produktivitas).
- **`design_gallery`** (motif kain, story, file) + **AI Gemini** untuk analisa/auto-tag motif (butuh Emergent LLM key / playbook).
- **Menu:** HRD (Employees, Attendance, KPI, Design Gallery).
- **Acceptance:** import absensi, dashboard kehadiran/telat, KPI desain, gallery + AI tagging.
- **Catatan integrasi:** mesin fingerprint → tentukan metode (export file vs API/SDK vendor).

### FASE 3 — Purchasing (MD)
**Scope:**
- **`suppliers`** master (nama, NPWP, kontak, jenis barang, entitas).
- Refactor `purchase_orders` → relasi ke `suppliers` (bukan string).
- **Alur approval pembelian** (request → review purchasing → approval manajemen/owner).
- **Integrasi Printing / BOM** → `bom_printing` (benang + bahan printing per produk/order).
- **Pengelolaan Kas** → `cash_transactions` (kas kecil per entitas, kas besar gabungan).
- **Toleransi kedatangan ±2%** → validasi qty terima vs PO saat inbound (warning/approval bila >±2%).
- **Menu:** Suppliers, Purchase Approval, Cash Management.
- **Acceptance:** PO dengan supplier master + approval bertingkat; receiving menerapkan toleransi ±2%; kas tercatat per entitas.

### FASE 4 — Finance & Accounting
**Scope (modul terberat):**
- **`chart_of_accounts`** (Aktiva/Hutang/Modal/Pendapatan/Beban; fleksibel, mapping jurnal).
- **`journal_entries`** (GL, double-entry).
- **`bank_accounts`** (PT/CV/owner/pribadi).
- **Tax module** (PPN/PPH; rekap; export Coretax fase lanjut).
- **Outstanding/AR** → aging piutang dari `invoices`, **credit-limit enforcement**, **reminder** (link Notification Center), **denda 1–3%** otomatis.
- **Monthly closing** (28/30/31) + lock periode.
- **Auto-posting** dari Sales (invoice→jurnal) & Purchasing (PO/kas→jurnal).
- **Menu:** Finance (COA, Journal, Bank, Tax, AR/Outstanding, Closing).
- **Acceptance:** invoice membentuk jurnal otomatis; AR aging + reminder + denda; closing bulanan; laporan dasar (neraca/laba-rugi sederhana).

### FASE 5 — Warehouse Advanced + RFID
**Scope:**
- **Warehouse structure** → tambah level **Level** (Zone→Rack→Level→Bin) di `warehouses`.
- **Stock Allocation + Trend** → `stock_classifications` (fast/slow/dead >3 bln) + analitik tren.
- **Notifikasi real-time** → manfaatkan Notification Center (stok menipis, kedatangan, transfer, dead stock); upgrade WebSocket (KN_05).
- **RFID:**
  - `warehouse_locations` (master lokasi RFID hierarki), `rfid_tags` (tag↔item/lot), `rfid_devices` (printer/reader/handheld/gate/server), `rfid_events` (scan/gate log).
  - Endpoint ingest event + validasi gate (green/red) + alarm → notifikasi supervisor.
  - **Simulator** RFID untuk testing tanpa hardware.
  - Kontinjensi: SOP padam, UPS ≥30’, fallback manual (form input manual), recovery data.
- **Menu:** RFID (Locations, Tags, Devices, Gate Monitor), Stock Analytics.
- **Acceptance:** lokasi RFID termodel; ingest event → update stok + audit; gate green/red + notifikasi; mode manual saat down.

### FASE 6 — Additional (By Request)
- Creative & design hub, com-hub, dan permintaan lain. Ditentukan kemudian.

### FASE BI — Business Intelligence (Lintas, dibangun bertahap mengikuti data)
- Fast/Slow/Dead stock, Product/Fashion trend, Brand performance, Gross profit by category, Outstanding monitoring, Sales by territory, KPI sales per rep.
- Implementasi bertahap setelah data fase terkait tersedia (Sales→BI sales; Warehouse→BI stok; Finance→BI profit).

---

## 5. Rencana Data Migration (dari "Data Request: Existing System")

| Kategori | Field kunci | Target koleksi | Catatan |
|---|---|---|---|
| Master Customer | Kode, Nama Toko, Alamat/Kota, NPWP, Jenis, Plafond, Sales PIC, Status | `customers` (+field baru) | enhance schema dulu (Fase 0) |
| Master Produk | SKU, Nama, Jenis kain, Kategori, Satuan, Harga Pokok, Harga Jual, Foto, Gramasi, Status | `products` (+field baru) | tambah harga_pokok, gramasi |
| Stock Existing | SKU, Lot, Yard, Lokasi gudang, Rak, Qty | `inventory_balances` (+movements opening) | opening stock |
| Sales Order & Invoice | No SO, Customer, Produk, Qty, Harga, No Invoice, Nominal, Pajak, Jatuh tempo, Status bayar, Outstanding, Umur | `sales_orders`, `invoices` | histori + AR aging |
| Supplier & Purchasing | Nama supplier, NPWP, Kontak, Jenis barang, PO, Produk, Qty, Harga | `suppliers`, `purchase_orders` | Fase 3 |
| COA & HRD | Aktiva/Hutang/Modal/Pendapatan/Beban, Rekening PT/CV/owner/pribadi, Karyawan/Jabatan/Divisi, Fingerprint, KPI | `chart_of_accounts`, `bank_accounts`, `employees`, dll | Fase 2 & 4 |

**Proses migrasi (per fase):** Export → Validasi → Cleansing → Mapping → Import (script seed terkontrol) → Reconcile (gates integrity). Format export ideal: **CSV/XLSX**.

---

## 6. Keputusan & Pertanyaan Terbuka (HARUS dijawab sebelum coding)

1. **Multi-Entity:** Berapa entitas legal? Produk & gudang di-share atau dipisah per entitas?
2. **Prioritas fase:** Mulai dari Fase 1 (Sales) penuh, atau bangun Fase 0 (Multi-Entity+Tax) dulu? (Rekomendasi: Fase 0 ringkas → Fase 1.)
3. **Tax/Coretax:** v1 cukup generate faktur + export, atau wajib integrasi e-Faktur/Coretax otomatis (butuh kredensial DJP)?
4. **HRD fingerprint:** metode ambil data (export file dari mesin vs API/SDK vendor)? Merek mesin?
5. **AI Gemini (gallery motif):** setuju pakai **Emergent LLM key** (Gemini) untuk analisa/auto-tag motif?
6. **RFID:** vendor & protokol (MQTT/HTTP)? Boleh kami buat **simulator** dulu untuk validasi alur tanpa hardware?
7. **Real-time:** setuju mulai dengan Notification Center (polling) lalu WebSocket di Fase 5? 
8. **Scope v1 tiap fase:** apakah boleh kami kirim per-fase (incremental, demo tiap fase) — bukan sekaligus?
9. **Data migration:** kapan data export existing tersedia? Format apa?

---

## 7. Rekomendasi Prioritas & Quick Wins

**Rekomendasi urutan eksekusi (paling aman & berdampak):**
1. **Fase 0 (ringkas)** — Multi-Entity + field master + Notification Center. *(enabler, hindari rework)*
2. **Fase 1 — Sales & Marketing** *(prioritas assessment + fondasi sudah 40%)*
3. **Fase 3 — Purchasing/Supplier master** *(melengkapi rantai SO↔stok↔beli; supplier master mudah & berdampak)*
4. **Fase 4 — Finance/AR/Outstanding** *(kontrol piutang = pain point finansial utama)*
5. **Fase 5 — Warehouse Advanced + RFID** *(WMS sudah 65%, tinggal analitik + RFID)*
6. **Fase 2 — HRD** & **Fase 6 — Additional** *(paralel/menyusul sesuai prioritas bisnis)*
7. **BI** dibangun menempel tiap fase.

**Quick wins (efek besar, usaha kecil):**
- **Supplier master** (`suppliers`) — ubah string → master + relasi PO.
- **Credit limit + Outstanding monitoring** dasar (AR aging dari invoice) — langsung jawab pain point #5.
- **Toleransi ±2%** saat receiving — validasi kecil, nilai operasional tinggi.
- **Status Pending Order** + Notification Center — tingkatkan visibilitas real-time.
- **Field enhancement** (NPWP, plafond, gramasi, harga pokok) — prasyarat migrasi data.

---

## 8. Catatan Penting
- Dokumen ini **selaras** dengan `plan.md`, `ENTITY_REGISTRY.md`, `KN_13_NAVIGATION_MAP.md`, dan guardrail di `/app/scripts`. Setiap fase yang dieksekusi akan **mengupdate** dokumen-dokumen tersebut.
- **Tidak ada perubahan kode** dilakukan oleh dokumen ini. Implementasi menunggu konfirmasi prioritas & jawaban Bagian 6.
- Estimasi skala: program multi-bulan, multi-modul. Pengiriman **incremental per fase** sangat disarankan (demo + testing tiap fase).

---
*Disusun dari: `Hasil Assessment KN dan Kebutuhan Data_compressed.pdf` + review/mapping sistem eksisting KN4 (Session #013).*
