# AUDIT ISOLASI ENTITAS — VERIFIKASI & VALIDASI (bukti empiris)

> 2026-08-10 · basis data demo penuh (`seed_realistic.py`: 2 PT, 7 akun, 9 SO, 13 PO,
> 67 jurnal, 55 roll). Alat: `/app/audit_entity_isolation.py` (sapuan 300 endpoint GET ×
> 4 identitas), `/app/verify_leaks.py`, `/app/verify_leaks2.py`.
> Identitas uji: `sales@` (home **ent_ksc**, terkunci) · `sales3@` (home **ent_kanda**,
> terkunci) · `admin@` (lintas-PT) · `warehouse@` (home ent_ksc).

## RINGKASAN EKSEKUTIF

| Aspek | Status |
|---|---|
| Fondasi scoping (`entity_scope.py`, registry koleksi, `X-Entity-Id`) | **BAGUS** — terpusat & benar |
| Dokumen inti (SO, PO, pelanggan, supplier, stok, jurnal, kas) | **TERISOLASI** (terbukti) |
| Buka dokumen PT lain via URL/ID (IDOR) | **AMAN** di 6 endpoint teruji, **BOCOR di `/api/lots/{id}`** |
| Modul pinggir (notifikasi, target/insentif sales, rencana bayar, selisih bayar, denda, jejak audit) | **BOCOR lintas-PT** |
| Laporan piutang (AR Aging) | **TERCAMPUR** — dua PT dijumlahkan jadi satu |
| Papan stok & pegging | **SENGAJA lintas-PT** (fitur peluang antar-PT) → perlu keputusan pemilik |
| Nomor dokumen | **CAMPUR**: seri lama satu untuk grup (`SO-0001`, `PO-00004`) vs baru ber-prefix (`KSC/PO-00012`) |
| Harga per PT | Mesin ADA (`entity_prices` + `/api/pricelist`) tetapi **KOSONG** → semua PT pakai harga master yang sama |

---

## 1. YANG SUDAH BENAR (terbukti terisolasi)

Sales PT-A vs sales PT-B melihat himpunan data yang **berbeda** pada:

| Endpoint | PT-A | PT-B |
|---|---|---|
| `/api/customers` | 4 | 1 |
| `/api/suppliers` | 4 | 2 |
| `/api/sales-orders` | 8 | 1 |
| `/api/purchase-orders` | 9 | 4 |
| `/api/inventory/movements` | 41 | 2 |
| `/api/gl/trial-balance` | 26 akun · Rp 981.324.092 | 14 akun · Rp 46.599.692 |
| `/api/cash-transactions/summary` | kas kecil Rp 7.750.000 | kas kecil Rp 3.800.000 |
| `/api/reports/summary` | omzet bulan Rp 79.250.000 | Rp 0 |
| `/api/hr/employees` · `/api/makloons` · `/api/supplier-contracts` · `/api/customer-prices` | terisi | 0 |

Anti-IDOR terbukti: sales PT-A meminta dokumen PT-B → **404/403** pada
`sales-orders`, `purchase-orders`, `ar-receipts`, `sales-returns`, `suppliers`
(+ `products/{id}/purchase-history`, `purchase-returns/source-rolls`,
`uom-conversions/usage` lewat POC F0-C: **28 PASS / 0 FAIL**).
Permintaan `X-Entity-Id: all` dari sales **diabaikan** (tetap PT sendiri).

## 2. KEBOCORAN NYATA (harus ditutup)

| # | Endpoint | Bukti |
|---|---|---|
| L1 | `GET /api/notifications` | sales **Kanda** menerima notifikasi KSC: `ntf_9f2bdb658c61` "Order menunggu persetujuan: SO-0007" (`entity_id=ent_ksc`) |
| L2 | `GET /api/payment-plans` | sales Kanda melihat **2 dari 2** rencana bayar KSC (Butik Bali Indah, Toko Kain Sejahtera) |
| L3 | `GET /api/payment-variances` | sales Kanda melihat **4 dari 4** keputusan selisih bayar KSC |
| L4 | `GET /api/penalties` | sales Kanda melihat nota denda KSC `pnl_3bddc1591159` |
| L5 | `GET /api/sales-targets` | target sales lintas-PT terlihat semua |
| L6 | `GET /api/sales-incentives` | insentif lintas-PT terlihat semua |
| L7 | `GET /api/audit-logs` | **sales & gudang** membaca **66 baris jejak audit SELURUH grup**. Gerbangnya `require_permission("product","view")` (bukan izin audit) dan **tanpa scope entitas** |
| L8 | `GET /api/lots/{id}` | sales PT-A membuka lot PT-B → **HTTP 200** (daftar `/api/lots` ter-scope, detailnya tidak) |
| L9 | `GET /api/ar/aging` | `entity_id` yang dilaporkan selalu `"all"`; total **identik** untuk KSC / KANDA / ALL (Rp 20.260.900) → piutang dua PT dijumlahkan. Akar: `ar_aging_service.aging_report()` dipanggil tanpa konteks entitas dari header |
| L10 | `hr_org_units` | 12 baris masih menunjuk entitas yang **sudah dihapus** (`ent_f39d5cfe1728`) → data yatim setelah entitas dihapus (bootstrap menanam divisi per entitas aktif, tidak ada pembersihan) |
| L11 | stempel entitas salah pada seed | `sales_targets`/`sales_incentives` milik **Citra Lestari (sales Kanda)** ber-`entity_id=ent_ksc` |

## 3. SENGAJA LINTAS-PT — PERLU KEPUTUSAN PEMILIK

- `GET /api/inventory/status-board`: setiap baris SKU membawa `by_entity[]` berisi
  **angka stok tiap PT sampai rincian gudang** + `has_intercompany_opportunity: true`.
  Respons untuk sales KSC dan sales Kanda **identik** (mis. BTK-MEGA-001: KSC 933 unit
  di 3 gudang, Kanda 7 unit). Ini pintu fitur "beli antar-PT" (FASE G-6).
- `GET /api/pegging/rolls`: roll milik PT lain ikut muncul (A lihat 1 roll Kanda,
  B lihat 3 roll KSC).
- `/api/inventory/movements` menampilkan `from_owner_entity_id`/`to_owner_entity_id`
  pada mutasi pindah-kepemilikan antar-PT (2 baris) — wajar untuk jejak, tapi berarti
  nama PT lawan terlihat.

## 4. MASTER DATA — kondisi saat ini

| Kelompok | Sekarang | Catatan |
|---|---|---|
| Produk, kategori, UOM, pustaka warna, gudang | **BERSAMA** (identik di semua PT) | sesuai keinginan pemilik |
| Bagan akun (CoA) | **BERSAMA by-code**, buku besar terpisah per PT | terbukti benar |
| Pelanggan, supplier, karyawan HR, divisi, makloon, kontrak supplier, harga pelanggan | **PER-PT** | terbukti terpisah |
| Template dokumen / kop surat | **BERSAMA** (2 template dipakai kedua PT) | kop surat PT berbeda? perlu keputusan |
| Syarat pembayaran, kategori biaya | **BERSAMA** | perlu keputusan |
| Tarif insentif (`incentive_rates`) | **`entity_id="all"`** (11 baris) | padahal insentif = beban PT masing-masing |
| Aturan persetujuan (`approval_rules`) | **`entity_id="all"`** (9 baris) | limit approval bisa beda per PT? |
| Format parser bank (`bank_statement_formats`) | `entity_id="all"` | wajar (teknis) |
| Harga jual per PT (`entity_prices`) | **0 baris** — fitur belum dipakai | semua PT pakai `products.price` |

## 5. NOMOR DOKUMEN

- Mesin `next_doc_number()` mendukung dua mode: **per-PT** (`KSC/PO-00012`) dan
  **grup** (`PO-00012`). 35 titik pemanggilan memakai mode per-PT, tetapi
  `warehouse_transfers` (TRF) masih memakai mode grup.
- Data hasil seed memakai seri **grup**: `SO-0001…SO-0009` dan `PO-00004…PO-00011`
  dipakai bercampur oleh KSC & Kanda (mis. `PO-00005`=Kanda, `PO-00007`=KSC).
  Akibatnya nomor dokumen **tidak bisa dipakai** membedakan PT untuk data lama.
- `PATCH /api/entities` boleh mengubah `doc_prefix` tanpa cek keunikan **dan**
  `_ENTITY_CODE_CACHE` tidak pernah dibersihkan → risiko nomor kembar antar-PT.
