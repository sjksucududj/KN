# RENCANA KOMPREHENSIF — MAKLOON / SUBKONTRAK BERLAPIS (Procure-to-Process-to-Pay)
Tanggal: 2026-07 · Status: EKSEKUSI BERJALAN · Bahasa: ID

> **STATUS EKSEKUSI (E2):**
> - ✅ **Fase M0 — Master Produk & Warna: SELESAI** (color_library + PantoneFinder + stage + VariantAxisPicker + Pustaka Warna). Gate hijau; testing_agent backend 20/20 + frontend 3/3 user story (iteration_126/127).
> - ⏳ Fase M1–M4: belum mulai (berurutan).
> - 🔑 **Perubahan keputusan LOT (§13.3):** LOT = **per-roll, INPUT MANUAL** (nomor lot dari supplier; TIDAK auto-generate). Berlaku untuk implementasi GR nanti (Fase M3) — §14.3 disesuaikan.

> Ditulis berdasarkan pembacaan kode NYATA (0 halusinasi). Referensi file diverifikasi:
> `schemas.py`, `schemas_purchasing.py`, `routers/purchase_orders.py`, `routers/suppliers.py`,
> `services/supplier_service.py`, `services/customer_service.py`, `services/gl_service.py`,
> `services/stock_bucket_service.py`, `server.py`, `permissions_config.py`, `AppViewRouter.jsx`,
> `config/navStructure.js`, `config/navMeta.js`, `scripts/validate_compliance.py`, `seed_realistic.py`.

---

## 1. PROBLEM STATEMENT

KN (Kain Nusantara) membeli & mengolah bahan tekstil secara **subkontrak (makloon)** berlapis:

```
BENANG (kg) ──[TENUN @vendor]──► GREY (yard) ──[CELUP/FINISHING @vendor]──► FINISHED GOODS (yard)
                                                                              + BARANG SISA (kembali ke KN)
```

Master data & purchasing SAAT INI **belum mendukung**:
1. Klasifikasi tahap bahan (benang/grey/finished) — `products.category` hanya teks bebas.
2. Transformasi input≠output pada pembelian — PO hanya "beli putus".
3. Ongkos jasa proses (tenun/celup) sebagai komponen HPP.
4. Pelacakan stok milik KN yang **fisiknya di vendor** (WIP-at-vendor).
5. Master mitra **Makloon** + riwayatnya (seperti Customer).
6. Estimasi/forecast input→output + **barang sisa** yang harus kembali ke KN.

**Sasaran:** menyediakan kemampuan **beli + proses (atau proses-saja dari stok)** sebagai **OPSI di alur Procure-to-Pay** (bukan menu transaksi baru), lengkap dengan master Makloon, resep konversi, costing berlapis, forecast, dan pengembalian finished goods + barang sisa ke gudang KN — tanpa merusak fitur yang ada dan tetap lolos `gate.sh`.

### Non-Goals (fase awal)
- Bukan MRP/penjadwalan produksi penuh.
- Bukan manufaktur in-house (semua proses tetap di vendor).
- Tidak mengubah `.env`, `MONGO_URL`, `REACT_APP_BACKEND_URL`.

---

## 2. GLOSSARY
- **Makloon / Maklon**: subkontrak jasa proses; bahan milik KN, vendor menagih ONGKOS saja.
- **Beli Putus**: pembelian normal (grey/FG jadi) — perilaku PO existing, TIDAK berubah.
- **WIP-at-vendor**: stok milik KN yang fisik berada di mitra makloon (belum tersedia/ATP).
- **Barang Sisa (remnant)**: output sampingan bernilai yang WAJIB kembali ke gudang KN.
- **Recipe / Resep**: definisi konversi (input→output) + susut + tarif + faktor forecast.

---

## 3. KONDISI SISTEM SAAT INI (temuan terverifikasi)
- **Produk**: `ProductPayload`/`ProductTemplateCreate` punya `category`, `base_unit`, catch-weight (`kg_per_meter`, `gramasi`, `lebar`), `uom_conversions`. Belum ada `stage`.
- **PO**: `purchase_orders` sudah punya `po_type` (`standard|blanket|call_off`) → mudah ditambah `subcon`. Inti pembuatan = `_create_po_core()` + `_create_inbound_tasks_for_po()` di `routers/purchase_orders.py`.
- **Supplier**: `suppliers` (prefix `sup_`) + `supplier_price_lists` + `services/supplier_service.py` (scorecard dari data nyata). Detail panel + scorecard sudah ada (belum se-"360" Customer).
- **Customer**: `customers` + `services/customer_service.py` `customer_360()` (riwayat order/dokumen/kredit) = pola "master + history" yang jadi acuan.
- **Stok = roll-as-SSOT**: `inventory_rolls` (punya `status` bucket & `is_remnant`!), `inventory_balances` (derived via `rebuild_balance`), `inventory_movements`. Operasi transisi bucket di `services/stock_bucket_service.py` (`move_rolls_by_qty`, `start_wip`, `complete_wip`). `BOARD_BUCKETS` daftar bucket tampil.
- **GL**: `services/gl_service.py` — pola `post_goods_receipt` (Dr Persediaan/Cr GR-IR), `post_vendor_bill` (Dr GR-IR+PPN/Cr Hutang), `post_landed_cost` (Dr Persediaan/Cr Hutang). Akun: `ACC_PERSEDIAAN`=1-1300, `ACC_GRIR`=2-1150, `ACC_HUTANG`=2-1100, `ACC_PPN_IN`=1-1500, `ACC_SUSPENSE`. `seed_default_coa()` menambah akun.
- **Router registrasi**: `server.py` blok `from routers import (...)` + loop `include_router`.
- **Guardrail** (`scripts/validate_compliance.py`): router ≤ **800** baris, komponen JSX ≤ **500**, utility ≤ 380, CSS ≤ 400. `check_nav_map.py` sinkron navStructure/navMeta/AppViewRouter. `verify_data_integrity.py` (122 invarian GL) + `seed_realistic.py` harus bersih. Auth wajib di tiap endpoint.

---

## 4. TARGET BLUEPRINT

### 4.1 Master Data — 3 pilar (Customer · Supplier · Makloon), pola "Partner 360"
- **Customer** (ada) → tetap.
- **Supplier** (ada) → di-upgrade ke "Supplier 360" (tab: Profil, PO, Tagihan, Retur, Scorecard).
- **Makloon** (BARU, koleksi `makloons` prefix `mak_`) → "Makloon 360" (tab: Profil, Order Makloon, Tagihan Jasa, Scorecard proses, Kapasitas).

### 4.2 Tahap Bahan (stage) di master produk
Tambah field `stage ∈ {yarn, grey, finished}` pada `products` & `product_templates`.
- `yarn` (benang): base_unit = `kg`.
- `grey`: base_unit = `yard` (atau meter).
- `finished`: base_unit = `yard` + faktor `meter_per_yard` (per konfirmasi user: FG semua yard).

### 4.3 Resep Konversi (koleksi `process_recipes` prefix `prcp_`)
Definisi transformasi + parameter forecast + tarif default:
```
{ id, name, process_type: tenun|celup|finishing,
  input_product_id, input_stage, output_product_id, output_stage,
  yield_factor,          # output_unit per input_unit (mis. yard grey / kg benang)
  waste_pct,             # susut proses (%)
  byproduct_pct,         # barang sisa (%) yang kembali ke KN
  byproduct_product_id,  # produk "sisa" tujuan (opsional)
  default_makloon_id, default_tariff, tariff_unit,  # ongkos per output/input/roll
  aux_cost_default,      # bahan pembantu (obat celup) opsional
  entity_id, status }
```

### 4.4 Transaksi = OPSI di Procure-to-Pay (bukan menu baru)
Entry point = **form buat PO** (`POCreateForm.jsx`) diberi **"Mode Pengadaan"**:
1. **Beli Putus** (default) → jalur PO existing, tak berubah.
2. **Beli + Makloon** → beli bahan (benang/grey) lalu proses berlapis di vendor.
3. **Proses Saja (dari stok)** → pakai stok benang/grey yang SUDAH ada, tanpa beli.

Mode 2 & 3 membuat dokumen **`makloon_orders`** (prefix `mko_`) berisi header + `steps[]` (rantai proses). Bahan (jika beli) tetap lewat **PO standard** existing; ongkos jasa tiap step ditagih via **`vendor_bills`** (ditambah dukungan referensi makloon). Output akhir = **finished goods** (mengacu master FG; boleh **buat FG baru on-the-fly**) + **barang sisa** kembali ke gudang KN.

**Struktur `makloon_orders`:**
```
{ id, mko_number, entity_id, mode: buy_process|process_only,
  material: { product_id, source: purchase|stock, qty, unit,
              po_id (jika beli), from_warehouse_id },
  steps: [ { seq, process_type, makloon_id, recipe_id,
             input_product_id, input_qty,
             output_product_id, expected_output_qty, actual_output_qty,
             expected_byproduct_qty, actual_byproduct_qty,
             tariff, aux_cost, service_bill_id, status,
             issued_at, received_at } ],
  final_output_product_id, target_warehouse_id,
  forecast: { input_qty, expected_finished_qty, expected_byproduct_qty },
  status: draft|material_ready|in_process|partially_received|completed|cancelled,
  costing: { material_cost, service_cost, aux_cost, byproduct_credit, hpp_output },
  timeline[], created_by, created_at, updated_at }
```

### 4.5 Model WIP-at-vendor (reuse roll SSOT)
Tambah status roll baru **`subcon`** (fisik, owned, BUKAN available → otomatis keluar dari ATP, sama seperti `wip`). Alur:
- **Issue bahan ke makloon**: `available → subcon` (via helper baru `issue_to_subcon`, meniru `start_wip`), `bucket_ref = {type:"subcon", makloon_id, mko_id, step}`.
- **Terima output**: konsumsi roll `subcon` (retire qty input) → buat roll baru `available` untuk output (grey/FG) + roll `available` `is_remnant=true` untuk barang sisa.
- Tambah `subcon_qty` ke `BOARD_BUCKETS` & derivasi balance.

### 4.6 Costing & GL (tambah fungsi di `gl_service.py`, pola existing)
- **Issue bahan → makloon**: `post_subcon_issue` → Dr **1-1350 Persediaan Dalam Proses (Makloon/WIP)** / Cr **1-1300 Persediaan**. Nilai = WAC bahan × qty.
- **Tagihan jasa makloon (posted)**: reuse `post_vendor_bill` (Dr GR-IR/Persediaan-WIP + PPN / Cr Hutang) ATAU `post_subcon_service` → Dr 1-1350 / Cr 2-1100 (+ PPN 1-1500).
- **Terima output**: `post_subcon_receipt` → Dr **1-1300 Persediaan (output)** + Dr Persediaan (barang sisa senilai NRV) / Cr **1-1350 WIP**. 
- **HPP output** = material_cost + service_cost + aux_cost − byproduct_credit (pakai `costing_service` WAC).
- Akun baru via `seed_default_coa()`: `1-1350` (+ opsional `1-1360 Persediaan Barang Sisa`).

### 4.7 Forecast / Estimasi (rumus KN — perlu konfirmasi koefisien)
Panel estimasi saat buat makloon order, parametrik dari recipe:
```
expected_output   = input_qty × yield_factor × (1 − waste_pct/100)
expected_byproduct= input_qty × byproduct_pct/100     (atau turunan dari waste bernilai)
finished_final    = Π(step yields)   # kalau berlapis
```
> ACTION: mohon rumus/koefisien pasti KN (yield benang→grey, susut celup, % sisa) untuk dikunci di recipe.

### 4.8 Penempatan UI (Navigasi)
- **Transaksi**: TIDAK ada menu baru — opsi "Mode Pengadaan" di form PO (grup **Pembelian → Pesanan Pembelian (PO)**). Daftar/monitor makloon order muncul sebagai **tab** di hub `purchase-orders` (mis. tab "Order Makloon") + panel detail.
- **Master baru**: 
  - `Pembelian → Mitra Makloon` (master `makloons`, Makloon 360).
  - `Pembelian → Resep Proses` (master `process_recipes`) — atau letakkan di Pengaturan & Master Data.
- **Upgrade**: `Pembelian → Pemasok (Supplier)` menjadi Supplier 360.

---

## 5. DATA MODEL — KOLEKSI

### Koleksi BARU
| Koleksi | Prefix id | Fungsi |
|---|---|---|
| `makloons` | `mak_` | Master mitra makloon (mirror suppliers) |
| `process_recipes` | `prcp_` | Resep konversi + tarif + faktor forecast |
| `makloon_orders` | `mko_` | Dokumen transaksi makloon (header + steps) |

### Koleksi DIMODIFIKASI (additive, invariant-safe)
| Koleksi | Perubahan |
|---|---|
| `products` | + `stage` (yarn/grey/finished), pastikan UoM yard + `meter_per_yard` |
| `product_templates` | + `stage` |
| `purchase_orders` | dukung `po_type="subcon"` + `makloon_order_id` (link, opsional) |
| `inventory_rolls` | status baru `subcon` (+ `bucket_ref.makloon_id`) |
| `inventory_balances` | + `subcon_qty` (derived di `rebuild_balance`) |
| `vendor_bills` | izinkan tagihan JASA ber-`makloon_id`/`makloon_order_id` (po_id opsional) |
| `gl_accounts` | + `1-1350` (+opsional `1-1360`) via `seed_default_coa()` |

---

## 6. API CONTRACT

### Endpoint BARU (prefix `/api`, auth wajib)
```
# Master Makloon
GET    /makloons                      list (scope entitas)
POST   /makloons                      create
GET    /makloons/{id}                 Makloon 360 (profil + history + scorecard)
PATCH  /makloons/{id}                 update (whitelist)
DELETE /makloons/{id}                 soft delete (status inactive)
GET    /makloons/{id}/scorecard       metrik proses dari data nyata

# Resep Proses
GET    /process-recipes               list
POST   /process-recipes               create
PATCH  /process-recipes/{id}          update
DELETE /process-recipes/{id}          soft delete
POST   /process-recipes/forecast      preview forecast (input→output+sisa)

# Order Makloon (dipanggil dari opsi PO)
GET    /makloon-orders                list (scope)
POST   /makloon-orders                create (mode buy_process|process_only)
GET    /makloon-orders/{id}           detail (steps, costing, timeline)
POST   /makloon-orders/{id}/issue     keluarkan bahan ke makloon (step)
POST   /makloon-orders/{id}/receive   terima output + barang sisa (step)
POST   /makloon-orders/{id}/cancel    batalkan (guard status)
```

### Endpoint DIMODIFIKASI
```
POST /purchase-orders            + terima payload mode subcon (opsional) → chain ke makloon order
POST /vendor-bills               + dukung tagihan jasa makloon (makloon_order_id, tanpa po_id)
POST /products, /product-templates  + field stage
GET  /stock-buckets/board        + kolom subcon_qty
```

---

## 7. FILE-BY-FILE EXECUTION MAP

### BACKEND — file BARU
| File | Isi |
|---|---|
| `backend/schemas_makloon.py` | `MakloonCreate`, `MakloonPatch`, `ProcessRecipeCreate/Patch`, `ForecastPreviewIn`, `MakloonOrderCreate`, `MakloonStepInput`, `MakloonIssueIn`, `MakloonReceiveIn`. Re-export dari `schemas.py`. |
| `backend/routers/makloons.py` | CRUD + `/makloons/{id}` 360 + scorecard. Pola dari `routers/suppliers.py`. |
| `backend/services/makloon_service.py` | `makloon_360()`, `compute_makloon_scorecard()` (pola `supplier_service`+`customer_360`). |
| `backend/routers/process_recipes.py` | CRUD + `/forecast`. |
| `backend/services/process_recipe_service.py` | `compute_forecast()` (rumus §4.7). |
| `backend/routers/makloon_orders.py` | create/issue/receive/cancel/list/detail. |
| `backend/services/makloon_order_service.py` | orkestrasi: buat PO bahan (reuse `_create_po_core`), issue/receive stok (reuse `stock_bucket_service`), costing, panggil GL. |

### BACKEND — file DIEDIT
| File | Edit |
|---|---|
| `backend/server.py` | tambah 3 router ke `from routers import (...)` + loop `include_router`. |
| `backend/schemas.py` | `ProductPayload`/`ProductTemplateCreate`/`ProductTemplatePatch` + `stage`; re-export schemas_makloon. |
| `backend/routers/products.py` + `routers/product_templates.py` | simpan `stage`. |
| `backend/services/gl_service.py` | `ACC_WIP_SUBCON="1-1350"` (+`ACC_SISA`), tambah ke `seed_default_coa()`, `post_subcon_issue`, `post_subcon_service`, `post_subcon_receipt`. |
| `backend/services/stock_bucket_service.py` | `issue_to_subcon()`, `receive_from_subcon()`, tambah `subcon` ke status & `subcon_qty` ke `BOARD_BUCKETS`. |
| `backend/services/roll_service.py` | `rebuild_balance` hitung `subcon_qty` (status `subcon`). |
| `backend/routers/vendor_bills.py` + `schemas_purchasing.py` | `VendorBillCreate` izinkan `makloon_order_id` & `po_id` opsional untuk tagihan jasa. |
| `backend/permissions_config.py` | + resource `makloon`, `makloon_order`, `process_recipe` (admin/manager penuh; warehouse: view+receive). |
| `backend/routers/purchase_orders.py` | `_create_po_core` terima `makloon_order_id` (link balik, opsional). |
| `seed_realistic.py` | seed contoh: makloons, process_recipes, produk benang/grey/FG (stage), 1 makloon order contoh, akun GL baru. Harus lolos `verify_data_integrity`. |

### FRONTEND — file BARU (semua < 500 baris; pecah bila perlu)
| File | Isi |
|---|---|
| `features/purchasing/makloon/MakloonView.jsx` | master list Makloon (default export page). |
| `features/purchasing/makloon/Makloon360Panel.jsx` | detail 360 (tab profil/history/scorecard). |
| `features/purchasing/makloon/MakloonFormModal.jsx` | form tambah/edit makloon. |
| `features/purchasing/makloon/ProcessRecipeView.jsx` | master resep proses. |
| `features/purchasing/makloon/MakloonOrderModal.jsx` | form order makloon (dipicu dari mode PO). |
| `features/purchasing/makloon/MakloonForecastPanel.jsx` | panel estimasi input→output+sisa. |
| `features/purchasing/makloon/MakloonOrderDetailPanel.jsx` | detail order + issue/receive + costing. |
| `features/purchasing/makloon/makloonApi.js` | wrapper fetch (`REACT_APP_BACKEND_URL`). |

### FRONTEND — file DIEDIT
| File | Edit |
|---|---|
| `features/admin/po/POCreateForm.jsx` | tambah selektor **Mode Pengadaan**; jika makloon → render `MakloonOrderModal`. |
| `features/purchasing/SuppliersView.jsx` + `SupplierDetailPanel.jsx` | upgrade ke Supplier 360 (tab). |
| `config/navStructure.js` | + item `Mitra Makloon` & `Resep Proses` di grup Pembelian; + tab "Order Makloon" di hub `purchase-orders`. |
| `config/navMeta.js` | + `PAGE_META` untuk view baru. |
| `AppViewRouter.jsx` | import + `activeView === "makloon" / "process-recipes"` dst. |

---

## 8. KEPATUHAN GUARDRAIL (wajib hijau)
- Router baru ≤ 800 baris; JSX ≤ 500; util ≤ 380.
- Semua endpoint pakai `require_permission`/`require_role` (auth_coverage).
- Semua query ter-scope `entity_id` via `entity_scope` (cross-entity guard).
- ID pakai `new_id(prefix)` (UUID-based), waktu `now_iso()` (UTC).
- `check_nav_map`: navStructure + navMeta + AppViewRouter sinkron.
- GL selalu balanced (pakai `_insert_entry` + `_balanced_pair`), idempotent via `_already_posted`.
- Update `seed_realistic.py` agar `verify_data_integrity.py` tetap 100% hijau.

---

## 9. PHASING (usulan urutan eksekusi)
- **Fase M0 — Master Produk & Warna**: field `stage`, koleksi `color_library` + `PantoneFinder`, pemisahan axis Warna/Grade di POS (`VariantAxisPicker`), Special Order pakai Pantone. (Fondasi katalog; independen dari makloon.)
- **Fase M1 — Fondasi Master Mitra**: koleksi `makloons` + `process_recipes` (konfigurasi forecast) + Makloon 360 UI + Supplier 360 upgrade + prinsip Master-Inline (§12).
- **Fase M2 — Stok & GL WIP**: status roll `subcon`, `issue_to_subcon`/`receive_from_subcon`, akun 1-1350 + posting subcon.
- **Fase M3 — Transaksi Makloon**: `makloon_orders` + opsi Mode Pengadaan di PO + panel forecast + tagihan jasa (1 per step) + barang sisa (produk master) kembali ke KN.
- **Fase M4 — Uji & Guardrail**: testing agent (backend+frontend) + `gate.sh` hijau + seed.

---

## 10. KEPUTUSAN (TERKUNCI oleh user)
1. **Forecast**: rumus **BISA DIKONFIGURASI** → `process_recipes` menyimpan **formula ekspresi bebas** (`formula` string, dievaluasi aman di backend; variabel: `input_qty`, `gramasi`, `lebar`, `yield_factor`, `waste_pct`, `byproduct_pct`). Fallback ke 3 field bila `formula` kosong.
2. **Penempatan master**: master data **muncul di SETIAP menu yang relevan** (bukan satu tempat). → lihat §12 (prinsip Master-Inline) & §14 (UI popup + quick-create).
3. **Tagihan jasa**: **1 tagihan per step/makloon** (a).
4. **Barang sisa**: jadi **produk master tersendiri** (a) — punya SKU + stage `remnant`/`byproduct`.
5. **Eksekusi**: **Fase M0 SELESAI ✅** (lihat status di atas). Lanjut M1 menunggu instruksi user.

---

## 11. TAMBAHAN — MASTER PRODUK: WARNA PANTONE + PEMISAHAN AXIS WARNA/GRADE

### 11.1 Masalah (terverifikasi di kode)
- **Warna = teks bebas**: `ProductPayload.color` (default "Natural"); axis warna di `ProductTemplatesView.jsx` diketik manual ("Merah, Biru, Hijau"). Tidak konsisten & tak bisa dipakai matching akurat.
- **POS menggabung Warna+Grade jadi satu**: `utils/variants.js → variantLabel()` = `"{color} · Grade {grade}"`; `components/ProductQuickView.jsx` (baris 88–101) me-render daftar varian **tergabung** ("Biru-Coklat · Grade A"). Seharusnya **Warna = pilihan terpisah, Grade = pilihan terpisah**.

### 11.2 Target
1. **Warna via Pantone** (bukan free-text): pilih dari **Color Library bergaya Pantone** (code + nama + hex swatch) + **Pantone Finder** (cari by code/nama, filter family, grid swatch, opsi "cari terdekat by hex").
   > CATATAN LISENSI: pustaka Pantone resmi berlisensi. Rencana memakai koleksi internal **`color_library`** berstruktur Pantone-like (code/name/hex/system/family), di-seed subset warna tekstil umum; label "Pantone-style". Bila user punya lisensi/daftar resmi → tinggal impor.
2. **Axis Warna & Grade TERPISAH** di master & POS: pemilih warna (swatch) independen dari pemilih grade; kombinasi resolve ke SKU varian konkret + tampilkan stok/harga per kombinasi. Manfaatkan sistem `axes` (color/grade/lebar) yang SUDAH ada di `product_templates`.

### 11.3 Data model (warna)
- Koleksi BARU **`color_library`** (prefix `col_`): `{ id, code, name, hex, system(TPX|TCX|C|U|KN), family, status, created_* }`.
- `products` & `product_templates`: 
  - ganti `color` bebas → `color_code` (ref `color_library.code`) + `color_name` (snapshot) + `color_hex` (snapshot).
  - `variant_attrs.color` menyimpan `color_code`; label dari `color_name`.
  - Axis color di template: `options[].value = color_code`, `label = color_name`, tambahan `hex`.
- Backward-compat: bila `color_code` kosong (produk lama) → fallback pakai `color` teks (jangan rusak data lama).

### 11.4 API (warna)
```
GET  /color-library            list + query (q, family, system)
POST /color-library            create (admin/manager) — quick-add dari mana pun
PATCH/DELETE /color-library/{id}
GET  /color-library/nearest?hex=RRGGBB   cari warna terdekat (ΔE sederhana)
```

### 11.5 File (warna & axis)
**Backend baru:** `routers/color_library.py` + `services/color_service.py` (nearest-hex) + schema `ColorCreate` di `schemas.py`. Registrasi di `server.py`. Seed di `seed_realistic.py`.
**Backend edit:** `schemas.py` (`ProductPayload`/`Template` + `color_code/color_name/color_hex`), `routers/products.py` + `routers/product_templates.py` (simpan snapshot warna), `permissions_config.py` (+resource `color`).
**Frontend baru:** `components/PantoneFinder.jsx` (picker swatch + search + nearest) — dipakai lintas menu; `utils/variants.js` + helper `deriveAxisOptions(variants)` (pisah color & grade).
**Frontend edit:** 
- `components/ProductQuickView.jsx` + `features/sales/mobile/MobileQuickView.jsx`: ganti daftar varian tergabung → **2 selector terpisah** (Warna swatch + Grade chip) yang resolve ke SKU; jaga <500 baris (pecah ke `VariantAxisPicker.jsx` bila perlu).
- `features/sales/ProductTemplatesView.jsx`: axis "Warna" pakai `PantoneFinder` (bukan input teks).
- Master Produk form (di `AdminView`/product form): field warna → `PantoneFinder`.
- `features/pos/FacetRail.jsx`: filter warna pakai swatch Pantone.

### 11.6 Guardrail khusus
- `ProductQuickView.jsx` sudah 210 baris → refaktor picker ke komponen `VariantAxisPicker.jsx` agar tetap <500.
- Perubahan warna bersifat **additive + backward-compatible** (produk lama tanpa `color_code` tetap tampil).

---

## 12. PRINSIP LINTAS-FITUR — "MASTER DATA INLINE DI TIAP MENU RELEVAN" (keputusan #2)
Master data TIDAK hanya di satu menu; setiap entitas master punya **quick-add/quick-select inline** di alur yang relevan:
| Master | Muncul inline di |
|---|---|
| **Warna (Pantone)** | Form Master Produk, Template Varian, **POS** (filter/pilih), Special Order, Order Makloon (spesifikasi celup) |
| **Makloon** | Form Order Makloon (di opsi PO), Resep Proses (default makloon), Tagihan Jasa |
| **Supplier** | Form PO, RFQ, Vendor Bill, Purchase Requisition |
| **Finished Goods** | Output Order Makloon (**buat FG baru on-the-fly**), Template |
| **Resep Proses** | Order Makloon (pilih/duplikat resep) |

Pola implementasi: setiap picker (`PantoneFinder`, MakloonSelect, SupplierSelect, ProductSelect) punya tombol **"+ Buat Baru"** → modal quick-create memanggil `POST` master terkait, lalu auto-terpilih. Master tetap punya menu kelola penuh, tapi entry cepat tersedia kontekstual.

---

## 13. OPEN QUESTION TERSISA
1. ✅ **Daftar warna awal**: TERKUNCI — pakai Color Library internal (Pantone-style) buatan kami.
2. ✅ **Rumus forecast**: TERKUNCI — pakai **formula ekspresi bebas** (bukan sekadar 3 field). → `process_recipes.formula` (string ekspresi aman, variabel: `input_qty`, `gramasi`, `lebar`, `yield_factor`, dst) dievaluasi via evaluator ekspresi aman di backend; fallback ke `yield_factor/waste_pct/byproduct_pct`.
3. **LOT granularity** — ✅ **TERKUNCI: per-roll, INPUT MANUAL**. Setiap roll punya field `lot` yang **diisi manual** dari nomor lot **supplier** saat Goods Receipt (BUKAN auto-generate). Validasi keunikan tetap dianjurkan.

---

## 14. TAMBAHAN — UI/UX PR/PO/MASTER: POPUP, KEJELASAN FORM, LOT/GRADE, FILTER/SORT, MASTER-INLINE

### 14.1 Temuan (terverifikasi di kode)
- **PO create = expand di ATAS list**, bukan popup: `PurchaseOrderManagement.jsx` (baris 228–237) `showCreateForm && <POCreateForm/>` di dalam `section-card`. → user minta **POPUP**.
- **Item PO** (`POCreateForm.jsx`) menangkap: produk, qty, unit, harga, disc. **TIDAK ADA**: grade, warna, lot, dye_lot, gramasi/lebar.
- **Item PR** (`PurchaseRequisitionItem`): product_id, description, qty, unit, est_price, note. **TIDAK ADA** grade/warna/lot.
- **LOT / dye_lot / grade** baru muncul di **Goods Receipt per roll** (`GRRollLine`, `POReceiveItem`) — tidak di PR/PO → banyak field kosong bila hanya diisi dari PR/PO.
- **List PO/PR**: belum ada filter & sort komprehensif.
- **Supplier**: bisa dipilih master ATAU ketik manual, tapi **tak ada "+ buat supplier"** inline.

### 14.2 GAP MASTER ↔ PR/PO (inti keluhan user)
| Field (ada di master `products`) | Tertangkap di PR/PO? | Rencana |
|---|---|---|
| grade | ❌ tak tampil | Tampilkan **grade rencana** (dari master) sebagai chip; grade aktual tetap saat GR |
| color/`color_code` (Pantone) | ❌ | Tampilkan **swatch warna** (dari master) di baris item |
| motif, gramasi, lebar | ❌ | Tampilkan chip atribut (read-only) agar konteks jelas |
| base_unit + catch-weight | ⚠️ sebagian | Sudah ada UoM hint; pertegas |
| **LOT** | ❌ tak ada konsep di PR/PO | Jadikan first-class (lihat §14.3) |
| dye_lot / lot_policy | ❌ | Tampilkan **kebijakan lot** (dari customer/`enforce_single_dye_lot`) sebagai info |

Prinsip: **form PR/PO menampilkan atribut master (preview chip) begitu produk dipilih**, sehingga tidak "terasa kosong" & mengurangi gap. Field yang secara alami baru ada saat penerimaan (lot/dye_lot/grade aktual per roll) tetap di GR, tetapi diberi **placeholder/rencana** yang jelas di PR/PO.

### 14.3 LOT — jadikan konsep first-class
- **Setiap roll punya LOT** — **diisi MANUAL** dari nomor lot **supplier** saat GR (bukan auto-generate; keputusan user), disimpan `inventory_rolls.lot`; anjurkan validasi uniqueness + traceability (PO→GR→roll→SO).
- PR/PO memilih **lot policy** (auto/manual). Default: auto unik saat GR.
- Tambah util `generate_lot()` di `services/roll_service.py` + tampilkan lot di detail penerimaan & katalog.
- ❗Granularity final menunggu jawaban §13.3.

### 14.4 PERUBAHAN UI (lintas Purchasing + master)
1. **Semua aksi "Buat" → POPUP (Shadcn `Dialog`)**, bukan expand di atas. Terdampak: PO, PR, RFQ (sudah modal → pola acuan), Vendor Bill, Landed Cost, Supplier, Makloon, Resep, Color. `POCreateForm` dibungkus `Dialog`; `PurchaseRequisitions` create → `Dialog`.
2. **Master-Inline / Quick-Create**: tiap picker (Supplier/Product/Color/Makloon/FG) diberi tombol **"+ Buat Baru"** → sub-modal quick-create → `POST` master → auto-terpilih. (Memenuhi keputusan #2 "master di tiap menu relevan".)
3. **Form jelas**: label grup, **chip atribut master** (SKU/grade/warna-swatch/motif/gramasi×lebar), UoM hint, validasi inline, ringkasan harga.
4. **Filter + Sort** di semua list Purchasing (PO/PR/RFQ/Vendor Bill/Supplier/Makloon): filter status/supplier/tanggal/entitas + sort tanggal/nilai/nama. Komponen reusable `FilterSortBar`.

### 14.5 File terdampak
**Frontend baru:** `components/FilterSortBar.jsx`, `components/ProductAttrChips.jsx`, `components/quickcreate/{SupplierQuickCreate,ProductQuickCreate,ColorQuickCreate,MakloonQuickCreate}.jsx`.
**Frontend edit:** `features/admin/PurchaseOrderManagement.jsx` (expand→Dialog + FilterSortBar), `features/admin/po/POCreateForm.jsx` (dalam Dialog + attr chips + inline create), `features/purchasing/PurchaseRequisitions.jsx` (create→Dialog + attr chips + filter/sort), `features/purchasing/SuppliersView.jsx` & `RFQView.jsx` & `VendorBillsView.jsx` (filter/sort + quick-create), `components/KNSelect.jsx` (opsi footer "+ Buat Baru").
**Backend edit:** `PurchaseRequisitionItem`/`POItemCreate` opsional snapshot `grade`/`color_code` (untuk kejelasan & dokumen), `services/roll_service.py` (`generate_lot()` + uniqueness), endpoint list PR/PO terima query filter/sort (opsional; boleh client-side dulu).

### 14.6 Catatan desain
- Sebelum implementasi UI (Fase M0/M1), panggil **design_agent** untuk pola Dialog, FilterSortBar, chip atribut, dan Pantone swatch agar konsisten dgn `design_guidelines`.
- Jaga guardrail: file JSX <500 baris (pecah modal & bar ke komponen sendiri).
