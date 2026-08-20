# KN_28 — FASE G-4: RELASI DOKUMEN, NOMOR REFERENSI & TANDA TANGAN

**Status:** ✅ DITUTUP · 2026-07-27
**Bukti:** POC `backend/test_g4_refs_poc.py` **49/0** · `verify_data_integrity` **196 PASS / 0 FAIL / 0 WARN** ·
`scripts/audit_doc_refs.py --strict` **HIJAU (29 PASS)** · `bash scripts/gate.sh --full` **23/23 HIJAU** ·
`testing_agent_v3` iter_176 (backend 105/106) + verifikasi UI 13 user story lintas 3 role.

---

## 1. MASALAH PEMILIK (kalimat aslinya)

> *"SO customer pending → KN harus PO ke supplier → banyak surat lahir tapi saling tidak
> mereferensikan → tracking & penelusuran retur susah."*

Sebelum fase ini relasi antar dokumen hanya **diturunkan saat dibaca**
(`document_relations_service`) dan hanya untuk **2 jangkar** (SO & PO). Akibat nyatanya:

1. Dokumen di tengah rantai (Faktur, Kwitansi, Nota Retur, Tagihan Supplier) **buntu** —
   tidak bisa dipakai sebagai titik masuk penelusuran.
2. Dokumen **cetak** tidak pernah menyebut nomor surat terkait, sehingga penerima kertas
   tidak bisa menghubungkan Surat Jalan dengan pesanannya.
3. Tidak ada satu pun invarian yang bisa berkata **"dokumen turunan ini yatim"**.

---

## 2. YANG DIBANGUN

### 2.1 Relasi disimpan sebagai DATA (dua arah)

`services/doc_refs_service.py` — setiap dokumen menyimpan:

```
refs: [{rel, doc_type, doc_id, doc_number, note, at}]
```

* **20 jenis dokumen** terdaftar di satu peta (`DOC_TYPES`) — Special Order, PR, RFQ, Kontrak,
  PO, GRN, Landed Cost, Tagihan Supplier, Retur Beli, Order Makloon, SO, Tugas Pengambilan,
  Surat Jalan, Faktur Pajak, Kwitansi, Retur Jual, Amandemen, Nota Kredit/Debit,
  Surat Jalan Transfer, Stock Opname.
* **17 kosakata relasi** berlabel Bahasa Indonesia (`Berasal dari`, `Menurunkan`, `Melunasi`,
  `Mengamandemen`, `Membalik`, …) dengan **inverse otomatis** → penulisan SELALU dua arah.
* Penulisan terjadi di **titik LAHIR** dokumen (bukan batch semalam), lewat `safe_link()`
  yang tidak boleh menggagalkan transaksi bisnis.
* `backfill()` **idempotent** untuk data lama: membentuk relasi dari kolom penghubung yang
  MEMANG sudah ada (`shipments.order_id`, `wms_tasks.po_id`, `ar_receipts.allocations[]`, …).
  Tidak mengarang relasi.

**Hook penautan di titik lahir (diaudit otomatis):** PR→PO · PO→GRN · PO→Tagihan Supplier ·
PO→Retur Beli · PO→Landed Cost · Makloon→Tagihan Jasa · SO→Tugas Pengambilan ·
SO→Surat Jalan · SO→Faktur Pajak · SO→Kwitansi · SO→Retur Jual · SO→Amandemen ·
Amandemen→Nota Kredit/Debit.

### 2.2 Jejak Dokumen dari jangkar MANA PUN

`GET /api/documents/trace/{doc_type}/{doc_id}` — BFS atas `refs[]`, kedalaman configurable
(`docref.trace_max_depth`). Mengembalikan `anchor · nodes · edges · groups · truncated`
sehingga UI tidak perlu menghitung ulang urutan tahap.

Endpoint pendukung: `/documents/refs/{type}/{id}` · `/documents/trace-search?q=` ·
`/documents/ref-types` · `POST /documents/refs/backfill?dry_run=`.

### 2.3 Dokumen CETAK menyebut referensinya + QR

`services/pdf_service.py::attach_document_refs` dipasang di **SATU** tempat (bukan 21 resolver),
sehingga **semua** jenis dokumen cetak otomatis memuat blok **"Referensi Dokumen"**:

```
Referensi Dokumen
Merujuk: PICK-C77989 · SJ-00001 · FKT-00001 · AR-00001 · SRET-00001
Menurunkan Tugas Pengambilan PICK-C77989 · Menurunkan Surat Jalan SJ-00001 · …
[QR] Scan QR untuk membuka Jejak Dokumen. Atau buka: https://…/jejak-dokumen/sales_order/so_001
```

### 2.4 Tanda tangan elektronik BERNAMA

Blok e-sign pada dokumen cetak kini menyebut **nama + JABATAN + waktu** per penandatangan
(sebelumnya hanya deretan nama) + kode verifikasi + hash SHA-256 + QR verifikasi publik
(`/verify-document/{kode}`, tanpa login).

### 2.5 Frontend

| Layar | Isi |
|---|---|
| **Pusat Dokumen → Jejak Dokumen** (`doc-trace`) | pencarian lintas jenis · kartu jangkar + 5 KPI · **rantai dokumen per tahap** · daftar relasi berlabel · pemilih kedalaman · Salin tautan · Susun Ulang Relasi (admin) |
| **Pusat Dokumen → Daftar Dokumen** | kolom **Referensi** (`N surat` → langsung ke Jejak) + kolom **Tanda Tangan** |
| Panel **Referensi Dokumen** (`DocRefsPanel`) | dipasang di detail **SO · PO · Tagihan Supplier · Penerimaan Barang (GRN) · Kwitansi(AR)** — kelompok "Berasal dari" / "Menurunkan" + tombol *Buka Jejak Dokumen* |
| **Deep-link QR** | `/jejak-dokumen/{doc_type}/{doc_id}` — bertahan melewati layar login lalu mendarat tepat di dokumennya |

---

## 3. KONFIGURASI (tanpa deploy) — Pusat Pengaturan → kelompok **Dokumen**

| Kunci | Arti | Default |
|---|---|---|
| `docref.autolink_enabled` | tautkan dokumen turunan otomatis saat lahir | ON |
| `docref.trace_max_depth` | kedalaman penelusuran (1–8) | 4 |
| `docref.require_parent` | invarian INV-REF-01 aktif | ON |
| `docref.show_in_pdf` | cetak blok Referensi Dokumen | ON |
| `docref.qr_in_pdf` | sertakan QR ke Jejak Dokumen | ON |
| `docref.pdf_max_refs` | maksimum nomor yang dicetak (sisanya "+N lainnya") | 6 |

Semua sakelar **terbukti berpengaruh** di POC (bukan tombol hiasan): mematikan
`autolink_enabled` membuat dokumen baru tidak menaut; mematikan `qr_in_pdf` menghilangkan QR
tetapi nomor referensi tetap tercetak; `trace_max_depth=1` memangkas graf.

---

## 4. INVARIAN & GUARDRAIL

| Kode | Isi | Bukti-merah |
|---|---|---|
| **INV-REF-01** | dokumen turunan yang PUNYA kolom sumber wajib menunjuk induk yang HIDUP | POC menjadikan tagihan supplier yatim → gate MERAH, lalu hijau lagi |
| **INV-REF-02** | relasi selalu dua arah (A→B ⇒ B→A) | POC menyuntik relasi satu arah → gate MERAH |
| **INV-REF-03** | dokumen cetak benar-benar memuat blok referensi + QR — **termasuk saat dirender tanpa browser** (job/penjadwal/WhatsApp) | render nyata lewat mesin PDF di dalam gate |
| `scripts/audit_doc_refs.py` | cakupan KODE (hook di titik lahir) + cakupan DATA per koleksi + kesehatan tautan (menggantung/satu arah/tak dikenal/duplikat) | `--self-test` membuktikan audit bisa MEMERAH |

**Kejujuran invarian:** dokumen yang memang berdiri sendiri (penerimaan tanpa PO, kwitansi uang
muka tanpa alokasi, tagihan biaya langsung tanpa PO) **tidak** dituduh yatim — dibedakan lewat
`source_fk` di registry, dan jumlahnya dilaporkan eksplisit oleh gate supaya tidak jadi tempat
sembunyi.

Gate baru di `scripts/gate.sh`: `audit_doc_refs SELF-TEST` (statik) ·
`audit_doc_refs --strict` (data) · `POC FASE G-4` (mode `--full`).

---

## 5. BUG NYATA YANG DITEMUKAN & DIPERBAIKI DI FASE INI

1. **Blok tanda tangan cetak tidak menyebut jabatan/waktu** → `pdf_service._attach_esign`
   sekarang mengirim daftar penandatangan lengkap ke template.
2. **QR kosong bila dokumen dirender tanpa browser** (cetak batch, penjadwal, kiriman
   WhatsApp, integrasi). Dulu URL diambil hanya dari header `Origin`. Sekarang ada resolver
   tunggal `services/app_url.py` (Origin → `PUBLIC_APP_URL` → `APP_URL` → env → `frontend/.env`)
   dan fallback di `pdf_service.build_document`; dijaga invarian INV-REF-03.
3. **Amandemen & Nota Kredit menulis `refs` manual** (bypass layanan pusat) → sakelar admin &
   dedupe tidak berlaku, dan Nota **Debit** memakai doc_type yang tidak ada di peta sehingga
   tautannya ditolak diam-diam. Sekarang lewat `safe_link` dengan doc_type kanonik.
4. **Tugas pengambilan (outbound) lahir tanpa menaut SO** → hook ditambahkan di
   `services/fulfillment_status.py`.
5. **POC G-1 meninggalkan residu** (tugas gudang milik SO yang sudah dihapus) → cleanup POC
   G-1 diperluas; INV-REF-01 yang menemukannya.

---

## 6. CARA UJI CEPAT

```bash
cd /app
python seed_realistic.py                     # data demo (idempotent)
python backend/test_g4_refs_poc.py           # harus 49 / 0
python scripts/verify_data_integrity.py      # harus 196 PASS / 0 FAIL / 0 WARN
python scripts/audit_doc_refs.py --strict    # harus HIJAU
python scripts/audit_doc_refs.py --self-test # bukti-merah audit
bash scripts/gate.sh --full                  # harus 23/23 HIJAU
bash scripts/rebuild_frontend.sh             # WAJIB setelah ubah frontend/src
```

UI: preview → quick-login (Admin/Sales/Manager/Warehouse) → **Pusat Dokumen** →
tab **Jejak Dokumen**. Coba juga URL `/jejak-dokumen/sales_order/so_001` (jalur QR).

---

## 7. BATAS CAKUPAN (jujur)

* Graf ditampilkan sebagai **kolom per tahap**, belum diagram bebas (cukup untuk membaca alur,
  dan tidak menambah beban render di kontainer 1 CPU).
* Editor template PDF belum diubah di fase ini (blok referensi ikut template master).
* Jenis dokumen yang wajib punya induk memakai `source_fk` — bila nanti ada jalur pembuatan
  dokumen baru yang lupa menyimpan kolom sumber, dokumen itu akan tampil sebagai
  "berdiri sendiri" di laporan gate (bukan MERAH). Angkanya wajib dipantau.
