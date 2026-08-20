# KN_25 — RENCANA & HASIL FASE E: SOURCING BERBASIS KONTRAK

> Status: **✅ SELESAI & TERUJI** (Phase 4–5 `plan.md`, sesi 2026-07-26).
> Keputusan pemilik yang dieksekusi: **E-01** `supplier_items` **FULL** termasuk **impor
> massal CSV/XLSX**, **E-02** baris PR ber-mode `makloon` → **1 klik membuka Wizard Makloon
> TER-PREFILL** (bukan form kosong).
> Induk: `KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md`,
> `KN_22_PLAN_FASE_B_UOM.md` (konversi satuan), `KN_23_PLAN_FASE_C_LOT.md` (lot),
> `KN_24_PLAN_FASE_D_MAKLOON.md` (kontrak makloon & rantai proses).
> Aturan emas: **kode menang atas dokumen**.

---

## 1. Masalah yang diselesaikan

Sebelum Fase E, pembelian kain/benang berjalan dengan tiga celah besar:

| Gejala | Akibat |
|---|---|
| Harga beli diketik manual di PO | kesepakatan kontrak tidak mengikat sistem; harga bisa melenceng tanpa jejak |
| Supplier menyebut barang dengan **kode & nama sendiri** (mis. `SLW-YARN-30S` = `BNG-KTN-001`) | pencocokan surat jalan dilakukan "di kepala" petugas → salah barang, salah satuan (1 cone ≠ 1 kg) |
| PR hanya bisa jadi **PO** | kebutuhan yang sebenarnya harus **diproses lewat mitra makloon** dipaksa jadi pembelian, atau dicatat di luar sistem |
| PR harus direalisasi **sekaligus** | PR campur (sebagian beli, sebagian makloon) tidak punya jalur; realisasi bertahap tak terlacak |

Fase E menjadikan **kontrak + peta barang supplier sebagai sumber kebenaran harga & penamaan**,
dan memecah PR menjadi **routing pemenuhan per BARIS** yang bisa direalisasi **bertahap**.

## 2. Keputusan pemilik yang dieksekusi

| # | Keputusan | Implementasi |
|---|---|---|
| E-01 | `supplier_items` **FULL** + **impor massal** | Koleksi baru `supplier_items` (prefix `sit_`) + CRUD + pencarian `lookup` + **impor CSV/XLSX 2 tahap** (pratinjau → commit) yang **idempotent** (upsert by `supplier_id` + `supplier_sku`) |
| E-02 | Baris makloon → **Wizard ter-prefill** | `GET …/makloon-prefill?line_no=N` menghitung bahan dari **Resep Proses** (yield × susut) lalu mengisi Wizard Makloon: produk bahan, qty, gudang, langkah, mitra, kontrak, produk hasil |
| E-03 | Kontrak **pembelian** | `supplier_contracts.contract_type="purchase"` (basis unit, harga, MOQ, masa berlaku) dengan **resolver** kontrak spesifik-produk **menang** atas kontrak generik; kontrak kedaluwarsa diabaikan |
| E-04 | Realisasi **parsial** | Pilih baris → PO; sisa baris tetap terbuka. `realization_status ∈ open · partially_realized · realized` **dihitung** dari `realizations[]` |
| E-05 | Penerimaan menampilkan **nama supplier** | `wms_tasks` inbound membawa `supplier_sku`, `supplier_item_name`, `expected_grade` → tampil berdampingan dengan nama KN di layar Inbound |

## 3. Model data

### 3.1 `supplier_items` (BARU · prefix `sit_`)

Kunci unik logis: **(`supplier_id`, `supplier_sku`)** — kode yang sama boleh dipakai supplier lain.

```
id, entity_id
supplier_id, supplier_name                    # snapshot nama saat dibuat
product_id, sku, product_name, base_unit      # sisi KN (SSOT produk)
supplier_sku                                  # KODE versi supplier  (wajib)
supplier_item_name                            # NAMA versi supplier  (default: nama KN)
supplier_uom, conv_factor                     # 1 supplier_uom = conv_factor base_unit (> 0)
last_price, currency, moq, lead_time_days
expected_grade, barcode, notes
status (active|inactive)
usage_count                                   # >0 ⇒ DELETE ditolak 409 (jejak audit aman)
created_at/by, updated_at/by
```

### 3.2 `supplier_contracts` — tambahan untuk `contract_type="purchase"`

Struktur sama dengan Fase D (lihat KN_24 §3.1); untuk pembelian yang dipakai:
`partner_kind="supplier"`, `partner_id`, `product_id` (kosong = **berlaku semua produk**),
`tariff_basis` = satuan harga, `tariff_rate` = **harga per satuan**, `moq`,
`valid_from`/`valid_to`, `expected_grade`, `status`, `usage_count`.

### 3.3 `purchase_requisitions` — routing & realisasi (additive)

```
items[]:
  line_no, product_id, sku, product_name, quantity, unit, est_price
  fulfillment_mode          # purchase | makloon        (WAJIB valid)
  realized_qty              # akumulasi realisasi baris
  realizations[]            # { type: purchase_order|makloon_order, ref_id, ref_number,
                            #   qty, at, by }
realization_status          # open | partially_realized | realized  (turunan, bukan input)
realization{}               # ringkasan: total/realized lines & qty, purchase_lines, makloon_lines
po_ids[], makloon_order_ids[]
```

### 3.4 `purchase_orders.items[]` — jejak sourcing (additive)

```
contract_id, contract_number                  # kontrak pembelian yang dipakai
supplier_item_id, supplier_sku, supplier_item_name
expected_grade, expected_grade_source         # supplier_contract | supplier_item
price_source                                  # contract | pr_estimate | supplier_item |
                                               # price_list | product_master
sourcing_explain[]                             # jejak keputusan harga (auditable)
pr_id, pr_number, pr_line_no
```

### 3.5 `wms_tasks` (inbound) — penamaan supplier

`supplier_sku`, `supplier_item_name`, `supplier_item_id`, `expected_grade` — diturunkan dari
baris PO saat task inbound dibentuk.

## 4. Prioritas harga (resolver, auditable)

`resolve_line_sourcing()` menyusun harga dengan urutan **berhenti di yang pertama ketemu**:

1. **Kontrak pembelian aktif** (`price_source="contract"`) — kontrak **spesifik produk** menang
   atas kontrak generik; kontrak di luar `valid_from..valid_to` diabaikan.
2. **Estimasi PR** (`pr_estimate`).
3. **Barang supplier** `last_price` (`supplier_item`).
4. **Price-list supplier** (`price_list`).
5. **Master produk** (`product_master`).

Setiap langkah menulis satu baris ke `sourcing_explain[]`; qty di bawah `moq` kontrak
menambah peringatan (`below_moq`) — **tidak** memblokir.

## 5. API

### 5.1 Barang supplier
| Method | Path | Catatan |
|---|---|---|
| GET | `/api/supplier-items?supplier_id=&q=&status=` | daftar + filter/pencarian |
| GET | `/api/supplier-items/stats` | KPI: total, aktif, supplier terpeta, produk terpeta |
| GET | `/api/supplier-items/lookup?supplier_sku=&supplier_id=` | **cari produk KN dari kode supplier**; tak dikenal → 404 beralasan |
| GET | `/api/supplier-items/import-template` | template CSV |
| POST | `/api/supplier-items/import` | body `csv_text` + `dry_run` (pratinjau **tidak** menulis) |
| POST | `/api/supplier-items/import-file` | multipart CSV/XLSX + `dry_run` |
| GET/POST/PATCH/DELETE | `/api/supplier-items[/{id}]` | DELETE 409 bila `usage_count>0` |

**Impor massal.** Pemisah CSV (`,` / `;` / tab) **dideteksi otomatis**; header memakai
**alias ramah pengguna** (`kode_supplier`, `nama_barang_supplier`, `sku_kn`, `satuan_supplier`,
`faktor_konversi`, `harga`, …). Setiap baris invalid **ditolak dengan alasan** (SKU KN tak ada,
`conv_factor<=0`, `supplier_sku` kosong, duplikat dalam berkas) dan baris valid tetap bisa
di-commit. Commit **idempotent**: menjalankan berkas yang sama dua kali → `created=0, updated=N`.

### 5.2 Kontrak pembelian
`GET/POST/PATCH/DELETE /api/supplier-contracts` (filter `contract_type=purchase`) ·
`POST /api/supplier-contracts/resolve` · DELETE **409** bila kontrak sudah dipakai PO.

### 5.3 Sourcing PR
| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/purchase-requisitions/{id}/sourcing` | ringkasan + `lines[]` dengan `remaining_qty` & jejak realisasi |
| POST | `/api/purchase-requisitions/{id}/realize-po` | body `supplier_id`, `warehouse_id`, `line_nos[]` (kosong = semua baris beli terbuka) → PO ber-jejak sourcing |
| GET | `/api/purchase-requisitions/{id}/makloon-prefill?line_no=N` | `ready` + `payload` siap kirim ke Wizard + `explain[]` |
| POST | `/api/purchase-requisitions/{id}/realize-makloon` | buat Order Makloon tertaut `pr_id`/`pr_number`/`pr_line_no` |
| POST | `/api/purchase-requisitions/{id}/convert-to-po` | **endpoint lama tetap hidup** (backward compatible) untuk PR yang semua barisnya `purchase` |

**Aturan tolak (400/409) yang ditegakkan:** baris `makloon` tanpa `product_id` · `fulfillment_mode`
tak dikenal · realisasi baris yang sudah penuh · realisasi ke PO pada PR yang semua barisnya makloon ·
output langkah terakhir Wizard ≠ produk baris PR · PR belum `approved`.

## 6. RBAC

| Peran | `supplier_item` | Realisasi PR | Alasan |
|---|---|---|---|
| admin · manager | view, create, update, delete, **import** | ✅ | pemilik proses pembelian |
| warehouse | **view saja** (create/import → 403) | ❌ | butuh nama supplier saat penerimaan, bukan mengubah data komersial |
| sales | **403 (tanpa akses)** | ❌ | harga beli & kontrak = data komersial pembelian |

## 7. Frontend

| Layar | Lokasi | Isi |
|---|---|---|
| **Barang Supplier** | Pembelian → Master Pembelian → tab *Barang Supplier* | KPI, tabel (kode+nama supplier ↔ produk KN + konversi "1 cone = 1,89 kg"), pencarian, filter supplier, **Cari barang KN dari kode supplier**, tombol *Barang Baru* & *Impor Massal* |
| **Modal Impor Massal** | tombol *Impor Massal* | pilih supplier, mode *Unggah Berkas* / *Tempel CSV*, unduh template, **Pratinjau** (total/valid/ditolak + alasan per baris) → **Impor Sekarang** |
| **PR Baru** | Pembelian → Pengadaan (Sourcing) → tab *Purchase Requisition* | kolom **Pemenuhan** per baris (`Beli ke Supplier` / `Proses via Makloon`) + catatan pemandu bila ada baris makloon |
| **Panel Pemenuhan & Realisasi** | detail PR | status realisasi, KPI (baris terealisasi, qty, baris beli, baris makloon), per baris: mode, sisa, jejak dokumen; aksi **Realisasi ke PO** (centang baris) & **Buat Order Makloon** |
| **Wizard Makloon ter-prefill** | tombol *Buat Order Makloon* pada baris makloon | subtitle "Realisasi PR-xxxxx baris N", qty bahan & produk bahan/hasil, mitra, kontrak, susut — **terisi otomatis**, tetap bisa diubah |
| **Inbound (penerimaan)** | Gudang → Operasi WMS → tab *Inbound* | baris biru "**Di surat jalan supplier:** `SLW-YARN-30S` — Cotton Combed 30s Cone 1,89 Kg · grade dijanjikan A" |

## 8. Invarian

| ID | Invarian |
|---|---|
| **INV-SRC-01** | `items[].fulfillment_mode ∈ (purchase, makloon)`; `line_no` unik per PR |
| **INV-SRC-02** | Realisasi tidak melebihi kebutuhan: Σ`realizations[].qty` == `realized_qty` ≤ `quantity` |
| **INV-SRC-03** | `realization_status` **sama** dengan hasil hitung dari `realizations[]` (tak bisa di-set manual) |
| **INV-SRC-04** | Setiap `realizations[].ref_id` menunjuk dokumen yang **ADA** (PO / Order Makloon) |
| **INV-SRC-05** | `supplier_items` sehat: (`supplier_id`,`supplier_sku`) unik, `product_id` & `conv_factor>0` valid |
| **INV-UI-01** | (BARU, lintas-fitur) backdrop modal hanya menutup lewat gestur utuh di backdrop; isi dropdown Radix ber-portal wajib `stopPropagation()` — lihat `memory/INVARIANTS.md` |

## 9. Bukti uji

| Item | Hasil |
|---|---|
| `python backend/test_fase_e_contracts_poc.py` | **PASS 69 / FAIL 0** (self-cleanup) |
| `bash scripts/gate.sh` | **SEMUA GATE HIJAU** (kini 13 gate — `guard:modal_dismiss` baru) |
| `python scripts/verify_data_integrity.py` | **0 FAIL** (`INV-SRC-01..05` hijau) |
| `testing_agent_v3` iter_167 | Backend US-E1..E9 + FE US-E10 — 0 bug kritikal |
| `testing_agent_v3` iter_169 | **FE US-E11..E16 = 6/6 PASS**, regresi backend 12/12 endpoint, **0 bug** |
| Regresi UI manual | 20 halaman/tab render bersih, **0 console error** |

## 10. Bug yang ditemukan & diperbaiki di fase ini

Detail lengkap (gejala, akar masalah, bukti) ada di `memory/BUG_REGISTRY.md`:

1. **KN-FASEE-UI-MODAL-CLOSE (P1)** — memilih opsi dropdown **menutup modal** → impor massal
   tak bisa diselesaikan. Akar: isi dropdown Radix di **React portal** tetap merembet ke
   backdrop + opsi yang menjorok memang berada di atas backdrop. Perbaikan: helper
   `frontend/src/utils/overlayDismiss.js` di **21 backdrop** + `stopPropagation()` pada
   `ui/select.jsx` & `ui/popover.jsx`. **Gate baru INV-UI-01** dibuat agar tak terulang.
2. **KN-FASEE-UI-SELECT-BLANK (P2)** — `KNSelect` jalur Radix tampil **kotak kosong** tanpa
   petunjuk (mis. "Gudang Tujuan *"). Perbaikan: item sentinel berlabel placeholder (hanya saat
   nilai kosong) + gaya redup + `data-testid` per opsi.
3. **KN-FASEE-PREFILL-OUTPUT-NAME (P2)** — Wizard ter-prefill menampilkan "pilih output" dan
   ringkasan "?" walau data benar. Perbaikan: prefill menyertakan `output_name/unit` (+ input &
   byproduct) dan wizard memetakannya.
4. **KN-FASEE-UI-GRID-GAP (P2)** — kolom panel realisasi berhimpitan ("SISAJEJAK REALISASI").
   Perbaikan: `gap-x-3`.

## 11. Cara demo cepat (data seed)

```bash
cd /app && python seed_realistic.py          # 7 barang supplier · 3 kontrak pembelian · PR campur
```
1. **Pembelian → Master Pembelian → Barang Supplier**: cari `SLW-YARN-30S` → ketemu `BNG-KTN-001`.
2. Tombol **Impor Massal** → *Tempel CSV* → pratinjau (baris salah ditolak beralasan) → impor.
3. **Pengadaan (Sourcing) → Purchase Requisition → PR-00005** (3 baris: 2 beli, 1 makloon) → *Detail*.
4. Centang baris #1 → **Realisasi ke PO** (supplier *Solo Weave*) → harga **dari kontrak**,
   status jadi *Realisasi Sebagian*.
5. Baris #3 → **Buat Order Makloon** → Wizard ter-prefill (109,65 kg dari resep) → simpan.
6. **Gudang → Operasi WMS → Inbound** → pilih task PO baru → baris "**Di surat jalan supplier**".
