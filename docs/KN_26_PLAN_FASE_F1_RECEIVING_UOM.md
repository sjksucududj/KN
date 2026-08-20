# KN_26 — RENCANA & HASIL FASE F-1: PENERIMAAN BERBASIS SATUAN SUPPLIER

> Status: **✅ SELESAI & TERUJI** (Phase 6 `plan.md`, sesi 2026-07-26 lanjutan-2).
> Keputusan desain yang dieksekusi: **F1-01 … F1-08** (lihat §2).
> Induk: `KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` (PS-03/PS-04 satuan & konversi),
> `KN_22_PLAN_FASE_B_UOM.md` (registry konversi global + jejak `uom_trail` + toleransi),
> `KN_25_PLAN_FASE_E_SOURCING_CONTRACTS.md` (`supplier_items.supplier_uom` / `conv_factor`).
> Aturan emas: **kode menang atas dokumen**.

---

## 1. Masalah yang diselesaikan

Fase E sudah membuat layar penerimaan **menampilkan** kode & nama barang versi supplier
("Di surat jalan supplier: `SLW-YARN-30S` — Cotton Combed 30s Cone 1,89 Kg"). Tetapi **input
qty masih WAJIB dalam satuan KN**. Padahal supplier menulis surat jalan dalam satuannya sendiri.

| Gejala | Akibat |
|---|---|
| Surat jalan: "25 cone", layar minta "kg" | operator mengalikan sendiri (25 × 1,89 = 47,25). Salah ketik **tidak terdeteksi** |
| Faktor konversi hanya ada di kepala/kalkulator | angka stok **tidak bisa dipertanggungjawabkan** — tidak ada jejak dari mana asalnya |
| Selisih kiriman dihitung dalam satuan KN | klaim ke supplier sulit ("kurang 3,78 kg" ⟶ supplier berpikir dalam cone) |
| Sisa PO hanya tampil dalam satuan KN | operator tidak tahu "berapa cone lagi" tanpa membagi manual |
| **BONUS (bug P1 pra-ada):** produk berbasis `kg` (benang, obat celup) tanpa gramasi/lebar | **penerimaan mustahil diselesaikan** — `complete` selalu 400 (lihat §9) |

Fase F-1 memindahkan aritmetika satuan **dari kepala operator ke server**, dengan jejak wajib.

---

## 2. Keputusan desain yang dieksekusi

| # | Keputusan | Implementasi |
|---|---|---|
| **F1-01** | Titik input satuan supplier | `POST /api/inbound/tasks/{id}/scan-receive` menerima **`doc_uom` + `doc_qty`** (opsional). Diisi ⇒ server konversi ke satuan task, `actual_qty` **diabaikan**. Kosong ⇒ **perilaku lama 100% backward-compatible** |
| **F1-02** | Prioritas resolusi faktor | 1) `same_unit` → 2) **`supplier_item`** (`doc_uom == supplier_uom` ⇒ `conv_factor`) → 3) **registry global** (`uom_rules_service`) → 4) gagal ⇒ **400 actionable** (arahkan ke *Barang Supplier* / *Konversi Satuan*). `source` **selalu** dicatat |
| **F1-03** | Jejak konversi WAJIB (D-07) | `wms_tasks.scan_log[].uom_trail` + akumulasi `wms_tasks.receive_uom_trails[]` (dengan `scan_id` + `actor`). Ditegakkan `INV-RCV-01..03` |
| **F1-04** | Endpoint bantu FE | `GET …/uom-options` → satuan task/dasar + katalog supplier + **opsi satuan berikut faktor & hint** + **sisa PO dalam dua satuan** |
| **F1-05** | Pratinjau sebelum simpan | `POST …/preview-uom` → jejak + sisa + level toleransi, **tanpa menulis apa pun** (dibuktikan di POC) |
| **F1-06** | Pesan menyebut DUA satuan | Over-receipt ⇒ *"Qty terima 480 yard melebihi batas PO 408 yard. Input Anda: 12 roll = 480 yard. Sisa 200 yard ≈ 5 roll."* |
| **F1-07** | Roll fisik tetap fisik | `GRRollLine` (panjang/berat) **tidak diubah** — roll diukur fisik saat GR; validasi Σroll ≈ qty diterima tetap berlaku |
| **F1-08** | Kebijakan tanpa deploy | `system_settings` scope **`receiving`**: `supplier_uom_input_mode` (`off\|optional\|prefer`) · `require_supplier_item_for_supplier_uom` · `block_over_remaining` |

---

## 3. Model data (additive — tanpa koleksi baru)

### 3.1 `wms_tasks` (inbound) — field baru
```
supplier_uom              # satuan versi supplier (dari supplier_items, via baris PO)
supplier_conv_factor      # 1 supplier_uom = N base_unit produk
last_receive_doc_uom      # satuan terakhir yang dipakai operator (UI mengingat pilihan)
receive_uom_trails[]      # akumulasi jejak konversi penerimaan (F1-03)
scan_log[].uom_trail      # jejak per scan (kosong bila input memakai satuan KN)
```

### 3.2 Bentuk `uom_trail` (SATU bentuk untuk semua penerimaan)
```
doc_uom, doc_qty            # apa yang DIKETIK operator (surat jalan supplier)
doc_uom_label               # label satuan yang enak dibaca ("Cone (benang)")
task_uom, task_qty          # hasil dalam satuan PO/task → INI yang masuk received_qty
base_uom, base_qty          # hasil dalam satuan DASAR produk (stok/roll/laporan)
factor                      # faktor doc → task
source                      # same_unit | supplier_item | fixed_uom | product_override
                            # | global_rule | formula_gsm_width | hop_base
rule_id, path[]             # aturan registry yang dipakai + langkah penjelasan
supplier_item_id, supplier_sku, supplier_item_name, supplier_uom
context, converted_at       # "goods_receipt_scan" + waktu UTC
```

### 3.3 `purchase_orders.items[]` — field baru (additive)
```
supplier_uom, supplier_conv_factor   # distempel saat PO dibuat (manual & hasil realisasi PR)
```
> PO manual sebelumnya **tidak** membawa jejak barang supplier (hanya PO hasil realisasi PR).
> Sekarang `_create_po_core` me-resolve `supplier_items` per (supplier × produk) sehingga layar
> penerimaan bisa menawarkan satuan supplier untuk **semua** PO.

### 3.4 Kebijakan `system_settings` scope `receiving`
| Field | Default | Arti |
|---|---|---|
| `supplier_uom_input_mode` | `prefer` | `off` = hanya satuan KN · `optional` = tersedia, default KN · `prefer` = default satuan supplier bila terdaftar |
| `require_supplier_item_for_supplier_uom` | `true` | satuan di luar satuan KN/dasar hanya boleh bila terdaftar di *Barang Supplier* (cegah satuan karangan yang faktornya kebetulan ada di registry) |
| `block_over_remaining` | `true` | hasil konversi melebihi sisa PO + toleransi ⇒ level `block` (butuh Eskalasi) |

---

## 4. Prioritas resolusi faktor (F1-02) — contoh nyata

Task: PO benang **120 kg**, produk `BNG-KTN-001` (`base_unit = kg`), supplier *Solo Weave*,
katalog supplier `SLW-YARN-30S` (`supplier_uom = cone`, `conv_factor = 1,89`).

| Input operator | Jalur | Faktor | Hasil | `source` |
|---|---|---|---|---|
| `25` + `kg` | satuan task = satuan input | 1 | 25 kg | `same_unit` |
| `25` + `cone` | **katalog supplier** | 1,89 | **47,25 kg** | `supplier_item` |
| `3` + `bale` | tidak terdaftar & kebijakan `require…=true` | — | **400 actionable** | — |
| `50` + `yard` (produk kain) | satuan dasar produk lewat registry | 1 | 50 yard | `same_unit`/registry |

Pesan 400 untuk kasus ke-3 (bukan error teknis):
> *Satuan 'bale' belum sah untuk penerimaan ini. Barang supplier 'F1-FAB-ROLL' terdaftar dengan
> satuan 'roll', bukan 'bale'. Daftarkan/perbaiki di Pembelian → Master Pembelian → Barang
> Supplier (satuan supplier + faktor konversi ke yard), atau terima dalam satuan yard.*

---

## 5. API

| Method & path | Guna | RBAC |
|---|---|---|
| `GET /api/inbound/tasks/{id}/uom-options` | opsi satuan + faktor + hint + sisa 2 satuan + katalog supplier + kebijakan | `wms:view` |
| `POST /api/inbound/tasks/{id}/preview-uom` | pratinjau konversi + level toleransi (**read-only**) | `wms:view` |
| `POST /api/inbound/tasks/{id}/scan-receive` | terima barang; **`doc_uom` + `doc_qty` opsional** | `wms:update` |
| `GET /api/receiving/uom-settings` | baca kebijakan | `wms:view` |
| `PUT /api/receiving/uom-settings` | ubah kebijakan (tanpa deploy) | **`settings:manage`** (admin) |

RBAC terbukti di POC: warehouse **boleh** lihat opsi & menerima, **ditolak 403** mengubah
kebijakan; **sales ditolak 403** total (bukan wewenangnya); task tidak ada ⇒ **404** (bukan 500).

### Catatan status kode (sengaja)
`doc_qty` dipagari `ge=0` (bukan `gt=0`) supaya qty **0** — salah ketik yang wajar di gudang —
dijawab **400 berbahasa Indonesia** ("Qty surat jalan (doc_qty) harus lebih besar dari 0."),
bukan 422 detail Pydantic yang tak bisa dibaca operator. Nilai **negatif** tetap ditolak lapis
skema (memenuhi `INV-NUM-01`).

---

## 6. Layar (frontend)

**Gudang → Operasi WMS → tab Inbound**
- Daftar task menampilkan `surat jalan: <kode supplier> · per <satuan supplier>`.
- Panel kanan: blok **“Qty diterima — boleh pakai satuan supplier”**
  (`data-testid="receive-uom-panel"`):
  - pemilih satuan (`receive-doc-uom-select`) — default mengikuti kebijakan `prefer`,
  - kotak qty (`receive-doc-qty-input`) — placeholder "Qty dalam cone",
  - **hint faktor** (`receive-uom-hint`) — "1 cone = 1,89 kg (barang supplier SLW-YARN-30S)",
  - **pratinjau live** (`receive-uom-preview`) — "25 cone → 47,25 kg (faktor 1,89 · barang supplier)",
  - **sisa 2 satuan** (`receive-uom-remaining`) — "Sisa PO: 120 kg ≈ 63,49 cone",
  - **peringatan** (`receive-uom-warning`) merah + tombol *Submit Scan* **disabled** bila `block`.
- **Riwayat penerimaan** (`receive-trail-history`) menampilkan jejak konversi tiap scan.

**Produk & Harga → Konversi Satuan** (admin)
- Kartu **Penerimaan dalam Satuan Supplier** (`receiving-uom-policy-card`): mode input,
  wajib-terdaftar, dan perlakuan melebihi sisa PO. Peran non-admin melihat read-only.

Berkas: `hooks/useReceivingUom.js` · `features/wms/inbound/ReceiveUomPanel.jsx` ·
`features/wms/inbound/ReceiveTrailHistory.jsx` · `features/wms/inbound/InboundTaskPanel.jsx` ·
`features/wms/InboundScanForm.jsx` · `features/wms/InboundScanInterface.jsx` ·
`features/admin/uom/ReceivingUomPolicyCard.jsx`.

> Catatan refactor: panel kanan layar Inbound dipindah ke `InboundTaskPanel.jsx` agar
> `InboundScanInterface.jsx` tetap di bawah batas guardrail (446 → **372** baris).

---

## 7. Invarian baru

| Invariant | Isi |
|---|---|
| **INV-RCV-01** | Setiap `scan_log[].uom_trail` yang ada WAJIB lengkap: `doc_uom`, `doc_qty > 0`, `task_uom`, `task_qty > 0`, `factor > 0`. Jejak tidak boleh setengah |
| **INV-RCV-02** | `doc_qty × factor == task_qty` (toleransi pembulatan) **dan** `task_qty == scan_log[].actual_qty` — angka di layar = angka yang masuk stok |
| **INV-RCV-03** | `source` ∈ daftar sah; bila `source == supplier_item` maka `supplier_item_id` WAJIB menunjuk `supplier_items` yang ADA; `receive_uom_trails[]` sinkron dengan jejak di `scan_log` |

Diperiksa di `scripts/verify_data_integrity.py` → `layer_receiving_uom_invariants` (lapis `L4-RCV`).

---

## 8. Bukti uji

| Item | Hasil |
|---|---|
| `python backend/test_fase_f1_receiving_uom_poc.py` | **PASS 47 / FAIL 0** (single script, via HTTP, **self-cleanup**) |
| `python scripts/verify_data_integrity.py` | **179 PASS / 0 FAIL / 0 WARN** (`INV-RCV-01..03` hijau) |
| `python scripts/validate_compliance.py` | **124 PASS / 0 FAIL / 19 WARN** (tech-debt lama — **tidak ada warning baru**) |
| `python scripts/check_nav_map.py` | **PASS** |
| `bash scripts/gate.sh` | **SEMUA GATE HIJAU** (termasuk `INV-NUM-01`, lihat §5) |
| `python backend/test_fase_e_contracts_poc.py` | **69 PASS / 0 FAIL** (regresi Fase E nol) |
| `testing_agent_v3` iter_170 | **overall 99%** · 0 bug kritikal · FE 6/6 fitur terverifikasi · **0 console error** |
| Verifikasi UI manual (Playwright) | opsi satuan · hint · pratinjau · sisa 2 satuan · peringatan 2 satuan · riwayat jejak — semua tampil benar |

Cakupan POC (US-F1…US-F8): terima pakai satuan supplier · pratinjau tanpa menulis · sisa 2 satuan ·
pesan actionable · jejak + audit log · kebijakan `off`/`optional`/`prefer` + mode ngawur ditolak ·
over-receipt 2 satuan · **regresi cara lama** · GR complete + roll · RBAC · INV-RCV-01..03 ·
pembersihan data.

---

## 9. Bug P1 PRA-ADA yang ikut diperbaiki

### `KN-F1-KGBASE-GR` — penerimaan produk berbasis `kg` mustahil diselesaikan (P1)
- **Gejala:** `POST /api/inbound/tasks/{id}/complete` untuk produk dengan `base_unit = kg`
  (benang, obat celup — **tanpa** gramasi/lebar) selalu **400**:
  *"Roll BNG-KTN-001: tak bisa menurunkan panjang dari berat — isi gramasi & lebar
  (atau kg_per_meter) produk, atau masukkan panjang aktual."*
- **Dibuktikan pra-ada:** direproduksi memakai jalur **lama** (`actual_qty` saja, tanpa
  `doc_uom`) pada produk seed `prod_benang_katun` → tetap 400. Jadi **bukan** regresi F-1.
- **Akar masalah:** `uom_service.kg_per_base_unit()` mengembalikan `0` bila `gramasi × lebar`
  tak tersedia. Untuk produk yang base unit-nya **memang satuan berat**, faktor kg-per-base-unit
  adalah **fisika murni** (1 kg = 1 kg) — GSM/lebar tidak relevan. Akibat nilai 0,
  `resolve_roll_measures()` menolak menurunkan `length_base` dari berat.
- **Perbaikan:** tabel `WEIGHT_BASE_KG` (`kg` 1,0 · `gram` 0,001 · `ton` 1000 · `lbs` 0,45359237
  · `ounce` 0,0283495231) dipakai **lebih dulu** di `kg_per_base_unit()`. Menyeragamkan aturan
  dengan `makloon_calc_service` yang sudah lama men-hardcode `1.0` untuk `kg`.
- **Dampak samping positif:** konversi `kg ↔ gram/ton/lbs/ounce` untuk produk berbasis berat
  kini tersedia tanpa perlu aturan registry tambahan.
- **Bukti FIXED:** POC Fase F-1 TEST 9 — GR complete 200 & roll benang terbentuk dengan
  `weight_kg` total = qty PO. Regresi `test_catch_weight_poc.py` Bagian A (fungsi murni) tetap
  **14/14 PASS**, termasuk kasus "tanpa gramasi/lebar → 0" (produk berbasis *meter*).

---

## 10. Cara demo cepat (data seed)

```bash
cd /app && python seed_realistic.py      # menyiapkan 2 task inbound demo Fase F-1
```
1. Login **warehouse@kainnusantara.id / demo12345**.
2. **Gudang → Operasi WMS → tab Inbound**.
3. Pilih task **BNG-KTN-001** (badge `Waiting`, keterangan *surat jalan: SLW-YARN-30S · per cone*).
   Satuan sudah otomatis **Cone** (kebijakan `prefer`).
4. Ketik **25** → layar menampilkan **“25 cone → 47,25 kg (faktor 1,89 · barang supplier)”**
   dan **“Sisa PO: 120 kg ≈ 63,49 cone”**. Tekan **Submit Scan** → `received_qty` = 47,25 kg.
5. Pilih task **LRK-CLSC-001** (*per roll*, sudah diterima 5 roll = 200 yard) → panel
   **Riwayat penerimaan** menampilkan jejak “5 roll → 200 yard (faktor 40 · barang supplier ·
   SLW-LRK-40)”. Ketik **12** → peringatan merah menyebut **kedua satuan** & *Submit Scan* mati.
6. Login **admin** → **Produk & Harga → Konversi Satuan** → kartu **Penerimaan dalam Satuan
   Supplier** → ubah mode ke `Off` → simpan → kembali ke Inbound: pemilih satuan menyusut ke
   satuan KN saja. (Kembalikan ke `Prefer` setelah mencoba.)
