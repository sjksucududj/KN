# AUDIT ANTAR-ENTITAS (FASE G-6 / G-6b) — VERIFIKASI & VALIDASI

> 2026-08-10 · basis data demo penuh · alat: `scripts/entity_audit/verify_interco.py`,
> `backend/tests/test_g6_poc.py` (**21/21 PASS**), `scripts/verify_data_integrity.py`
> (**233 PASS / 0 FAIL / 0 WARN**, termasuk INV-IC-01..08).

---

## A. YANG SUDAH ADA & TERBUKTI BEKERJA

### A1. Jual-beli antar-entitas = dokumen kembar (bukan pindah gudang)
Satu transaksi melahirkan **dua dokumen**, satu di tiap badan usaha, saling menunjuk
lewat `pair_id` — sehingga isolasi antar-entitas **tidak dilonggarkan**:

| Penjual (KSC) | Pembeli (Kanda) | Status | Nilai | PPN | Pelunasan |
|---|---|---|---|---|---|
| `KSC/IC-00001` | `KANDA/IC-00001` | invoiced | Rp 1.766.010 | Rp 175.010 | 0 (tugas gudang `TRF-00004`) |
| `KSC/IC-00002` | `KANDA/IC-00002` | settled | Rp 1.887.888 | Rp 187.088 | Rp 1.887.888 (netting) |
| `KSC/IC-00003` | `KANDA/IC-00003` | draft | Rp 264.735 | Rp 26.235 | — |
| `KSC/IC-00004` | `KANDA/IC-00004` | confirmed | Rp 529.803 | Rp 52.503 | diretur `KANDA/ICR-00001` |

Siklus: `draft → confirmed → shipped → received → invoiced → settled`
(+ `returned` · `disputed` · `cancelled`). Nomor **per entitas** (`<ENT>/IC-#####`).

### A2. Harga internal wajib dari kontrak (sistem tidak menebak)
- 3 kontrak internal aktif KSC→Kanda (`supplier_contracts` dengan `partner_kind="entity"`).
- 3 mode harga: **`fixed_price`** (bawaan, wajib ada kontrak — kalau tidak, transaksi
  **DITOLAK** dengan kalimat menuntun), **`at_cost`**, **`cost_plus_pct`**.

### A3. Pajak internal berpasangan
- 3 mode PPN ber-scope entitas: `ikut_pkp` (bawaan) · `tanpa_ppn` · `dengan_ppn`.
- Faktur pajak internal nyata: keluaran penjual `KSC/FKT-00003` ↔ masukan pembeli
  (`tax_invoices_in`), ditandai `source_type="interco"`, `is_internal=true`.
- Ada penjaga urutan: `can_issue=false` + `blocked_reason` ("Terbitkan Faktur Internal dulu…").
- Jalur pengganti umum **menolak** dokumen internal dan mengarahkan ke layar Antar Entitas.
- **INV-IC-05/07**: PPN keluaran penjual == PPN masukan pembeli; mode tanpa-PPN nol di dua sisi.

### A4. Saldo pasangan PT + pelunasan/netting
- `interco_accounts` (proyeksi, selalu dihitung ulang): KSC→Kanda **piutang** 2 dokumen
  terbuka, bruto Rp 2.295.813, sisa Rp 1.766.010; sisi Kanda **hutang** dengan angka sama
  (**INV-IC-02**).
- `interco_settlements`: `KANDA/ICS-00001` metode **netting** Rp 1.887.888 (tanpa uang keluar).
  Metode tersedia: netting · transfer bank · kas.
- **Pengingat pelunasan** aktif: saldo menganggur > `settlement_reminder_days` (30 hari).

### A5. Barang fisik lewat tugas gudang (tanpa jurnal dobel)
- `warehouse_transfers` ber-`transfer_kind="inter_entity"` + `interco_pair_id`
  (`TRF-00004` untuk penjualan, `TRF-00005` untuk retur).
- Roll & lot **berpindah pemilik** (`owner_entity_id`) dan **dinilai ulang** ke harga beli
  internal; jurnal at-cost lama **dilewati** supaya tidak dobel (**INV-IC-06**).
- "Tandai Diterima" **ditolak** bila tugas gudang belum selesai.

### A6. Retur antar-PT (G-6b)
`KANDA/ICR-00001` (nota retur, role `returner`) ↔ `KSC/ICR-00001` (nota kredit, role
`receiver`), alasan **wajib** ≥5 huruf, **dual-control** (pembuat ≠ penyetuju), tugas gudang
arah balik, faktur pajak ditandai `needs_replacement` (**INV-IC-08**).

### A7. Konsolidasi grup & eliminasi margin otomatis
- `GET /api/finance/consolidation/summary`: laba/aset/ekuitas **per entitas** + `gross` grup
  + baris `elimination` (KSC laba bersih Rp 26.292.979 · Kanda Rp 2.410.000).
- 3 eliminasi **otomatis** dari pair G-6 (`auto_generated=true`, `source_g6_pair_id`),
  ikut diperbarui saat settlement & dihapus saat pembatalan (**INV-IC-03**:
  unrealized profit Rp 2.437.100 tidak menggelembungkan laba grup).
- Kandidat eliminasi manual dideteksi dari akun IC (1-1250 IC-AR / 2-1250 IC-AP).

### A8. Laporan margin antar-PT
`/api/interco/margin-report` (per pair: subtotal, cost, margin, `unsold_ratio`,
unrealized vs realized) dan `/api/interco/margin-by-product`.

### A9. Konfigurasi (Pusat Pengaturan, grup **"antar-entitas"** — 7 kunci, scope global+entity)
`antar_entitas.pricing_mode` · `ppn_mode` · `ppn_rate_percent` ·
`approval_threshold_rupiah` · `approval_role` · `high_value_approval_role` ·
`settlement_reminder_days`.

### A10. Akun GL khusus antar-PT
`1-1250` IC-AR · `2-1250` IC-AP · `1-1310` Persediaan Dalam Perjalanan (Antar-PT) ·
`1-1300` Persediaan · `4-1000` Pendapatan · `5-1000` HPP · `2-1200`/`1-1500` PPN.

---

## B. TEMUAN BARU (celah nyata di sekitar antar-entitas)

| Kode | Temuan | Bukti |
|---|---|---|
| **IC-G1** | **`GET/POST /api/transfers*` TIDAK ter-scope entitas sama sekali** — `list_transfers` memakai `query_filter = {}` tanpa `entity_ctx`. Detail, **approve**, **reject**, **status**, **delete** juga tanpa penjagaan entitas. | `routers/transfers.py:39,289,313,409,453,522`. Empiris: gudang KSC membuka `TRF-00003` (milik KSC) **dengan konteks Kanda** → **200** |
| **IC-G2** | `warehouse_transfers` **tidak terdaftar** di `SCOPED_COLLECTIONS`, dan 2 dari 5 dokumen (justru yang antar-PT: `TRF-00004`, `TRF-00005`) **tidak punya `entity_id`** → dokumen "tak bertuan" | pemindaian DB + registry |
| **IC-G3** | **18 koleksi ber-`entity_id` tidak terdaftar** di registry (bukan SCOPED, bukan SHARED): `approval_rules`, `audit_logs`, `budgets`, `credit_notes`, `cycle_count_sessions`, `fin_budget_rules`, `payment_plans`, `payment_variance_decisions`, `penalties`, `purchase_returns`, `rfid_reads`, `rfid_tags`, `rnd_person_divisions`, `sales_incentives`, `sales_targets`, `supplier_price_lists`, `tax_invoices_in`, `warehouse_transfers` | skrip statik registry↔DB |
| **IC-G4** | **Drift nama koleksi**: registry mendaftarkan `input_tax_invoices` (tidak ada di DB) sedangkan faktur pajak masukan nyata tersimpan di **`tax_invoices_in`** → faktur masukan (termasuk faktur internal antar-PT) **tidak dijaga registry** | registry vs DB |
| **IC-G5** | Pemindaian statik 52 router: **6 TANPA scoping** (`admin.py`, `documents.py`, `incentive_rates.py`, `landed_cost.py`, `payment_variance.py`, `pegging.py`) dan **5 PARSIAL** (`crm.py`, `cycle_count.py`, `products.py`, `return_policies.py`, `transfers.py`) meski menyentuh koleksi wajib ter-scope | skrip statik |
| **IC-G6** | **Cetak dokumen lintas-entitas**: `GET /api/documents/preview/{order_id}` → sales Kanda mencetak **Surat Jalan SO-0007 milik KSC** (200, HTML lengkap) dan sebaliknya | empiris |
| **IC-G7** | **Jejak dokumen lintas-entitas**: `GET /api/documents/trace/sales_order/{id}` → sales KSC melihat jejak `SO-0002` Kanda beserta nama pelanggan "Moda Surabaya Fashion" | empiris |
| **IC-G8** | **RBAC keuangan terlalu longgar**: role **gudang** dapat membaca `/api/interco/accounts` (saldo hutang-piutang antar-PT), `/api/interco/settlements`, dan `/api/interco/margin-report` → semua **200** | empiris |
| **IC-G9** | **Sales tidak punya jalan resmi meminta barang dari PT lain**: seluruh menu antar-entitas **403** untuk sales, padahal papan stok memberi isyarat `has_intercompany_opportunity` dan angka stok PT lain. Alur bisnis terputus | empiris |
| **IC-G10** | **Tidak ada pagar "lawan transaksi ternyata PT sendiri"**: `customers`/`suppliers` tidak punya penanda entitas grup dan tidak ada validasi. Satu PT grup bisa didaftarkan sebagai supplier/pelanggan biasa → transaksi antar-PT lewat **PO/SO biasa**, tanpa dokumen kembar, tanpa faktur internal, **tanpa eliminasi margin** (laba grup jadi kembung) | `routers/customers.py`, `routers/suppliers.py`, `schemas.py` — nol rujukan ke `business_entities` |
| **IC-G11** | **HPP penjual tidak selalu ada** → `margin-report` melaporkan `cost: 0.0` dan `margin_pct: 100%` untuk `KSC/IC-00002`; `margin-by-product` menandai `cost_estimated: true`. Akibatnya eliminasi margin bisa **berlebih/kurang** | empiris |
| **IC-G12** | **Kas/bank tingkat grup**: rekening **"Kas Besar Grup"** ber-`entity_id="all"` dan **13 dari 19** transaksi kas ber-`entity_id="all"` — termasuk penerimaan piutang PT KSC (`CASH-00014/15` "Penerimaan KSC/AR-00008/9") dan pembayaran vendor bill. Uang satu PT dibukukan di kas grup tanpa hutang/piutang antar-PT | empiris |
| **IC-G13** | `interco_returns` tidak mengembalikan `pair_id`/`qty_total` di daftar (null) — nama fieldnya `return_pair_id`; UI/laporan mudah salah baca | empiris |
| **IC-G14** | Nomor transfer masih seri grup (`TRF-00001..5`, tanpa prefix entitas) — sejalan temuan penomoran di `plan.md` E1.7 | empiris |

---

## C. YANG BELUM ADA SAMA SEKALI (bukan cacat — memang belum dibangun)
Transaksi antar-entitas yang **tidak** punya jalur resmi di sistem:
1. **Titip bayar / bayar-dibayarkan** (PT A membayar tagihan PT B) — hanya ada sebagai
   *kasus* di Pusat Kasus Keuangan (`salah_entitas`, `pembayar_pihak_ketiga`), bukan dokumen
   antar-PT yang menimbulkan hutang-piutang resmi.
2. **Pinjaman uang antar-PT** (intercompany loan) + bunga/jadwal.
3. **Alokasi biaya bersama** (sewa kantor, listrik, gaji staf pusat dibagi antar PT).
4. **Jasa/makloon internal** (PT B mengerjakan proses untuk PT A) — `makloons` hanya untuk
   mitra eksternal; belum ada `partner_kind="entity"` di jalur makloon.
5. **Pindah aset tetap antar-PT** (`fin_fixed_assets` ter-scope, tanpa alur pindah entitas).
6. **Pinjam/penempatan karyawan lintas-PT** (payroll per entitas; tak ada mekanisme bagi biaya).
7. **Konsolidasi neraca penuh** — ringkasan sudah ada; eliminasi otomatis hanya untuk
   margin persediaan G-6 (IC-AR/IC-AP masih perlu eliminasi manual dari kandidat).
