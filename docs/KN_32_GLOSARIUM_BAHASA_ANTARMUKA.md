# KN_32 — GLOSARIUM & KEBIJAKAN BAHASA ANTARMUKA

**Berlaku sejak:** 2026-07-29 · **Status:** ditegakkan oleh gate (bukan imbauan)
**Keputusan pemilik:** seluruh antarmuka memakai **Bahasa Indonesia**.

---

## 1. Masalah yang diselesaikan

Aplikasi ini dipakai bersama tim gudang, sales, dan keuangan yang bekerja dalam
Bahasa Indonesia. Sebelum sesi ini, "sudah Bahasa Indonesia" hanyalah **klaim prosa**:

* satu berkas diterjemahkan, berkas berikutnya kembali berbahasa Inggris;
* tidak ada satu pun alat yang bisa **GAGAL** ketika label Inggris masuk lagi;
* sebagian teks yang dilihat pengguna ternyata lahir di **backend**
  (`routers/onboarding.py`, judul dokumen cetak, pesan penjadwal) — bagian ini
  tidak pernah ikut diperiksa.

Akibat nyata di lapangan: operator gudang melihat `Available`, `Picked`,
`Quarantine`, `Putaway` — dan keraguan di gudang berujung salah kirim.

## 2. Bentuk penegakan (executable guardrail)

| Alat | Peran |
|---|---|
| `scripts/audit_i18n_id.py --strict` | **MEMERAH** bila ada istilah Inggris pada teks yang dilihat pengguna (FE **dan** BE) |
| `scripts/audit_i18n_id.py --self-test` | **bukti-merah**: 12 skenario membuktikan audit benar-benar bisa memerah, dan tidak salah-lapor pada `data-testid` / `className` / kunci objek / URL |
| `scripts/fix_i18n_id.py --apply` | codemod: menerjemahkan **hanya rentang teks pengguna** memakai pemindai yang sama |
| `scripts/fix_i18n_id.py --self-test` | **bukti-merah**: 11 skenario membuktikan codemod TIDAK menyentuh kunci objek, nilai status backend, `data-testid`, `className`, atau jalur impor |
| `scripts/i18n_table_id.py` | tabel terjemahan tingkat-frasa (data, bisa di-review seperti daftar kata) |

Ketiganya masuk `scripts/gate.sh` (blok STATIK) sehingga `bash scripts/gate.sh`
memerah bila ada regresi bahasa.

### 2.1 Yang dipindai (dan yang TIDAK)

**Dipindai** — hanya yang benar-benar tampil:

* teks JSX antar-tag `>Tersedia<`
* teks di **sekitar interpolasi** `>Onboarding — {peran}<` · `>{n}× pesanan<`
  (celah nyata yang pernah meloloskan 60+ label)
* potongan **template literal** `` sub={`${n} pesanan`} ``
* nilai prop teks: `label` · `title` · `placeholder` · `sub` · `description` · dst.
* di **backend**: nilai kunci `label` · `description` · `title` · `message` · `detail` · `note`

**Tidak dipindai** (supaya nol temuan palsu): `data-testid`, `className`, kunci
objek, nama field API, jalur impor, URL, komentar, dan berkas uji/POC/seed.

## 3. Kata yang WAJIB diterjemahkan (kamus)

134 istilah. Cetak lengkap: `python scripts/audit_i18n_id.py --list`. Contoh inti:

| Inggris | Indonesia | | Inggris | Indonesia |
|---|---|---|---|---|
| Available | Tersedia | | Pending | Menunggu |
| Reserved | Dipesan | | Approved | Disetujui |
| Committed | Dialokasikan | | Rejected | Ditolak |
| Picked | Sudah Diambil | | Cancelled | Dibatalkan |
| Packed | Sudah Dikemas | | Overdue | Lewat Jatuh Tempo |
| Quarantine | Karantina | | Outstanding | Belum Lunas |
| Blocked | Diblokir | | Inbound | Barang Masuk |
| Damaged | Rusak | | Outbound | Barang Keluar |
| Sold | Terjual | | Receiving | Penerimaan |
| Putaway | Penempatan Rak | | Picking | Pengambilan |
| In-Transit | Dalam Perjalanan | | Packing | Pengemasan |
| Draft | Draf | | Dispatch | Pengiriman |
| Order | Pesanan | | On Hand | Stok Fisik |
| Customer | Pelanggan | | Ledger | Mutasi |
| Invoice | Faktur | | Void | Anulir |
| Approval | Persetujuan | | Reversal | Pembalikan |
| Warehouse | Gudang | | Refund | Pengembalian Dana |
| Work Order | Perintah Kerja | | Cycle Count | Stock Opname |

## 4. Kata yang SENGAJA dibiarkan (43 istilah)

Menerjemahkan istilah berikut **memperburuk** kejelasan, bukan memperbaikinya.

### 4.1 Singkatan dokumen yang dipakai lisan sehari-hari
`PO` · `SO` · `PR` · `GR` · `RFQ` · `SKU` · `UOM` · `QC` · `WMS` · `CRM` · `POS` · `HPP` · `RFID`

### 4.2 Istilah tekstil / bahasa kerja industri
`Lot` · `Roll` · `Grade` · `Makloon` · `Finishing` · `Batch` · `Stock Opname` ·
`Landed Cost` · `Supplier` · `Item`

### 4.3 Kata yang memang Bahasa Indonesia / serapan baku
`Total` · `Status` · `Detail` · `Info` · `Transfer` · `Filter` · `Reset` ·
`Bank` · `Debit` · `Target` · `Email` · `Password` · `Scan` · `No.` · `Log` · `CSV`

### 4.4 Dua keputusan yang perlu penjelasan
| Kata | Alasan tetap Inggris |
|---|---|
| **Sales** | dalam praktik Indonesia berarti **orang/tim penjualan** ("tim sales", "kunjungan sales"). Menerjemahkan jadi "Penjualan" mengubah maknanya dari *orang* menjadi *proses*. |
| **Stage** | **enum domain tekstil** (`yarn → grey → finished`) yang divalidasi server (`domain_registry`, aturan transisi). Layar sengaja menyebut nama enumnya supaya cocok dengan pesan penolakan server. |
| **Unit** | sah dalam Bahasa Indonesia (unit organisasi/kerja). Untuk **satuan ukur** dipakai kata "Satuan". |

### 4.5 Istilah keuangan yang sudah jadi nama akun/laporan
`Store Credit` · `Petty Cash` · `Cash Advance` · `AR/AP Aging` · `Weighted Average Cost` ·
`Backorder` — menerjemahkannya memutus kaitan layar dengan nama akun GL & laporan
yang dipakai tim keuangan.

## 5. Izin khusus per-kalimat (`IZIN_KHUSUS`)

Beberapa kalimat **sengaja** memuat kata Inggris karena kata itu adalah **nilai
sistem**, bukan kalimat untuk dibaca. Contoh paling jelas: nama peran RBAC.

> "Hanya `manager/admin` yang dapat menyetujui."

Kalau layar menulis "manajer" sementara nilai di server `manager`, pengguna
mencari "manajer" di matriks izin dan tidak menemukannya. Karena itu setiap
pengecualian **wajib mencantumkan alasan** di `IZIN_KHUSUS` — daftarnya sengaja
pendek agar tidak berubah menjadi tempat sampah.

## 6. Cara menambah istilah baru

```bash
# 1) lihat apa yang masih Inggris
python scripts/audit_i18n_id.py

# 2) tambahkan pasangan istilah ke KAMUS (scripts/audit_i18n_id.py)
#    atau kalimat utuh ke TABEL (scripts/i18n_table_id.py)

# 3) terapkan + buktikan
python scripts/fix_i18n_id.py --apply
python scripts/audit_i18n_id.py --strict     # harus 0 temuan
python scripts/fix_i18n_id.py --self-test    # codemod tetap aman
bash scripts/rebuild_frontend.sh             # preview = bundel statis, WAJIB rebuild
```

## 7. Catatan operasional

* **Tidak ada hot-reload frontend** (lihat `memory/PREVIEW_STABLE_MODE.md`).
  Setiap perubahan `frontend/src` wajib `bash scripts/rebuild_frontend.sh`.
* Codemod **tidak** menyentuh `data-testid`, jadi seluruh skrip uji tetap jalan.
  Satu kasus khusus diperbaiki manual: `LoginScreen` dulu memakai satu nilai
  untuk label DAN testid (`demo-login-${role}`), kini dipisah `key` vs `label`.
* Angka acuan sesi ini: **757 penggantian** di **±230 berkas** (FE + BE),
  audit akhir **0 temuan**.
