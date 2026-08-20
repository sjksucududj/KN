# KN_22 — FASE B: KONVERSI SATUAN GLOBAL & TOLERANSI SELISIH (D-06/D-07)

> **Status:** ✅ **SELESAI DIEKSEKUSI** (2026-07-25) · lanjutan sah dari
> `docs/KN_19_PLAN_FASE_A_FONDASI_DOMAIN.md` §5 dan `docs/KN_21_PLAN_PS21_NOTIFIKASI_OPERASIONAL.md`.
> **Mandat pemilik (sesi 2026-07-25):**
> * “konversi dibuatkan **global** saja dengan opsi yang **luas/banyak**”
> * “toleransi selisih **bisa dikonfigurasi**”
> **Keputusan yang dieksekusi:** **D-06** (basis tarif/satuan bebas per kontrak) ·
> **D-07** (**wajib** jejak konversi).
> **Aturan ditegakkan:** R3 (SSOT — matematika konversi tetap satu tempat) · R5 (desimal
> koma) · R7 (FE tidak hardcode satuan) · R8 (registry + invarian + POC + migrasi idempoten).

---

## §1. MASALAH NYATA YANG DITUTUP

| Gejala | Sebelum | Sesudah |
|---|---|---|
| Satu produk dibeli per **roll**, disimpan per **yard**, ditagih per **kg** | faktor tersebar: sebagian di `uoms`, sebagian di master produk, sebagian dihitung ulang di frontend | **satu registry global** `uom_conversion_rules` + master produk sebagai override; frontend hanya menampilkan hasil server |
| Timbangan gudang ≠ hasil konversi | tidak ada kebijakan; angka diterima apa adanya | **toleransi configurable**: ≥ peringatan → `needs_review`, ≥ blokir → **ditolak** (boleh override beralasan + audit) |
| Tagihan/laporan tidak bisa diaudit | dokumen hanya menyimpan `qty` + `unit` | tiap baris menyimpan **`uom_trail`** (qty & satuan dokumen, qty & satuan dasar, faktor, **sumber faktor**, waktu) — D-07 |
| Satuan tak dikenal | berisiko diam-diam dianggap 1:1 | **ditolak 400** dengan pesan Indonesia + saran tindakan |
| 🔴 **Bug lama**: produk berbasis **yard** dihitung seolah meter | berat/kg salah ±9,4% (GSM × lebar = kg **per meter** dipakai sebagai kg per yard) | `kg_per_base_unit()` mengoreksi ke satuan dasar produk (1 yard = 0,9144 m) — teruji di POC US-3b |

---

## §2. YANG DIBANGUN (backend)

| Berkas | Peran |
|---|---|
| `backend/services/uom_rules_service.py` **(baru)** | katalog satuan luas (23 satuan · 5 dimensi), CRUD aturan global + validasi, kebijakan toleransi (`system_settings` scope `uom`), `convert_with_trail()` (jejak D-07), `check_variance()`, `ensure_defaults()` (seed idempoten aturan **fisika**, bukan angka karangan) |
| `backend/services/uom_service.py` | **mesin matematika tetap satu** (R3): + `_pair()` (aturan global), + `resolve_factor()` (faktor **dan sumber**), + `kg_per_base_unit()` (perbaikan bug base-unit), semua fungsi lama tetap kompatibel |
| `backend/routers/uom_conversions.py` **(baru)** | `GET /api/uom-conversions/catalog · /rules · /settings · /usage` · `POST /rules` · `PATCH /rules/{id}` · `POST /rules/{id}/status` · `PUT /settings` · `POST /convert` · `POST /check-variance` |
| `backend/schemas_uom.py` **(baru)** | skema desimal-aman (`"0,9144"` diterima) + batas numerik (gate INV-NUM-01) |
| `backend/services/purchase_requisition_service.py` | baris PR menyimpan `uom_trail` + `base_unit`/`quantity_base`; satuan tanpa aturan → 400 |
| `backend/routers/purchase_orders.py` | baris PO menyimpan `uom_trail`; `quantity_base` kini hasil konversi berjejak (bukan fallback diam-diam) |
| `backend/routers/inbound_receiving.py` | GR: jejak konversi + **cek toleransi** berat aktual vs konversi → tolak/warn + `needs_review` + audit `uom_variance_flagged`; `variance_override_reason` untuk override beralasan |
| `backend/schemas_purchasing.py` | `GRCompletePayload.variance_override_reason` |
| `backend/bootstrap.py`, `seed_realistic.py` | seed aturan + toleransi + contoh faktor per produk (idempoten, tahan reset data demo) |
| `backend/scripts/migrate_fase_b_uom.py` **(baru)** | migrasi **idempoten**: seed aturan/toleransi + backfill `uom_trail` pada PO/PR lama; baris tanpa aturan ditandai `uom_unresolved` (tidak mengarang faktor) |
| `scripts/verify_data_integrity.py` | **INV-UOM-01…04** |
| `backend/test_fase_b_uom_poc.py` **(baru)** | POC HTTP tunggal — **49 pemeriksaan**, 10 user story |

### Urutan resolusi faktor (dikunci server)

```
satuan sama → master UOM (uoms.factor_to_base) → master produk (uom_conversions[])
→ aturan GLOBAL aktif (fixed | pack) → formula GSM × lebar (panjang ↔ berat)
→ 1-hop lewat satuan dasar → 400 “belum punya aturan” (TIDAK pernah diam-diam 1:1)
```

### Aturan standar yang di-seed (fisika/standar, bukan asumsi bisnis)

`yard·cm·mm·inch·feet·km → meter` · `gram·ton·lbs·ounce → kg` · `dozen·gross → piece` ·
`sqft → m²` · formula `meter ↔ kg (GSM × lebar ÷ 1000)`.
Ukuran kemasan (roll/bal/cone/box) **tidak** di-seed dengan angka karangan — diisi user
lewat layar Konversi Satuan (jenis `pack`) atau master produk.

---

## §3. YANG DIBANGUN (frontend)

| Berkas | Peran |
|---|---|
| `hooks/useUomConversions.js` **(baru)** | satu-satunya pintu FE ke katalog/aturan/konversi (cache modul) — komponen dilarang hardcode satuan (R7) |
| `components/UomInputConvert.jsx` **(baru)** | komponen **“Input & Konversi”**: qty desimal + pilih satuan + pratinjau hasil **dari server** + cek toleransi terhadap nilai aktual |
| `components/UomConvertHint.jsx` **(baru)** | baris pratinjau ringkas untuk form yang sudah punya input sendiri (dipakai form PO) |
| `features/admin/uom/UomConversionView.jsx` + `UomConversionParts.jsx` **(baru)** | layar **Konversi Satuan**: ringkasan, kartu **toleransi** (peringatan/blokir/pembulatan/override), kalkulator, tabel aturan + tambah/ubah/nonaktif, **jejak konversi dokumen** (bukti D-07) |
| `features/admin/po/POCreateForm.jsx` | opsi satuan dari katalog server + pratinjau konversi server (menggantikan rumus kg yang digandakan di FE) |
| `config/navStructure.js`, `config/navMeta.js`, `AppViewRouter.jsx` | menu **Produk & Harga → Konversi Satuan** (admin & manager; ubah butuh izin `uom:update`) |

---

## §4. BUKTI

| Bukti | Hasil |
|---|---|
| POC `backend/test_fase_b_uom_poc.py` | **49 PASS · 0 FAIL** (10 user story) |
| POC Fase A & PS-21 (tanpa regresi) | **53 PASS · 0 FAIL** · **43 PASS · 0 FAIL** |
| Invarian | INV-UOM-01…04 **PASS** · total `verify_data_integrity.py` **158 PASS / 0 FAIL / 0 WARN** |
| Migrasi | jalan ke-2 → `changed=0` (idempoten) |
| Gate | `scripts/gate.sh` **12/12 HIJAU** (termasuk INV-NUM-01 batas numerik & ux_audit file baru bersih) |

---

## §5. CARA UJI CEPAT

```bash
cd /app
python seed_realistic.py                        # data demo + aturan konversi
python backend/scripts/migrate_fase_b_uom.py     # idempoten (jalankan 2× → changed=0)
python backend/test_fase_b_uom_poc.py            # harus 49 / 0
python scripts/verify_data_integrity.py          # 158 PASS / 0 FAIL
bash scripts/gate.sh                             # 12/12 hijau
```
UI: quick-login **Admin** → *Produk & Harga → Konversi Satuan*:
ubah toleransi (mis. 1,5% / 3%), tambah aturan `cone → kg`, coba kalkulator
(`12,5 yard` → meter; `100 meter` → kg lewat GSM × lebar), lihat **Jejak Konversi Dokumen**.
Lalu *Pembelian → Pesanan Pembelian (PO)* → buat PO satuan `roll` → pratinjau
“2 roll = 100 yard (faktor 50 · master produk)”.

---

## §6. BATAS TEGAS (belum dikerjakan)

* **Fase C** lot kelas satu (`inventory_lots`, `LOT-YYMM-####`, genealogi) — D-10.
* **Fase D** wizard makloon multi-tahap/multi-mitra + selisih & klaim
  (`tariff_basis` & jejak konversi kini SIAP dipakai untuk menghitung tarif lintas satuan).
* **Fase E/F/G/H** sesuai KN_18 §7 + §A.5 (termasuk divisi/MD PS-17).
* Konversi **per kontrak/mitra**: sesuai keputusan pemilik, TIDAK dibuat — registry global +
  override master produk dianggap cukup. Bila kelak dibutuhkan, tambahkan lapisan
  `contract_id` pada aturan tanpa mengubah pemanggil (resolver sudah berlapis).
