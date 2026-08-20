# PROPOSAL RESTRUKTURISASI INFORMATION ARCHITECTURE (IA) — Navigasi & Menu
> **STATUS: ✅ DIEKSEKUSI PENUH (Opsi A) — 2 Jul 2026.** Admin 62 → ±23 menu; Pajak satu pintu di Keuangan; Command Palette (Ctrl+K) + Favorit/Pin live. Verifikasi: testing agent iteration_98 (19/19 hub, 55/55 tab) + self-test role & regresi. Detail implementasi di PRD changelog v1.12.

**Tanggal:** 1 Juli 2026 · **Sumber:** `frontend/src/config/navigationConfig.js`, `App.js` (render map), audit forensik U-1
**Masalah:** Navigasi admin = **62 item live + 12 "Segera Hadir" (74 entri)** dalam 9 grup + 4 standalone. Sales melihat 17, warehouse 22. Sistem baru ±50% — tanpa restrukturisasi, item akan tembus 100+ saat P3–P5, RFID, produksi, dll masuk.

---

## 1. PETA STRUKTUR SAAT INI (as-is)

| Grup | Item Live | Coming Soon | Catatan |
|---|---|---|---|
| (standalone) | Beranda · Pusat Persetujuan · Profil Saya · Eskalasi | — | 4 item |
| Penjualan | POS · Pelanggan/CRM · Kunjungan Sales · Pesanan (SO) · Approval Harga · Faktur Pajak Jual · Returns & BS · Special Order · Pricelist per-PT · Template & Varian | Price List per Customer | **10 live** |
| Pembelian | PO · Blanket PO · PR · RFQ · Saran Reorder · Pemasok · Approval Pembelian · Retur Beli · Tagihan Supplier · Landed Cost · Faktur Pajak Masukan · Pengelolaan Kas | BOM Printing | **12 live** — terbanyak |
| Gudang | Stok & Inventori · Inbound · Inspeksi QC · Outbound · Transfer Antar Gudang · Cycle Count · Status Stok & ATP · Stok Multi-Bucket · Transfer Antar-Entitas | Stock Analytics | **9 live** (5 di antaranya = tab dari SATU view `operations`) |
| RFID | — | 4 item | ok (auto-collapse) |
| Keuangan | AR/Aging · Konsolidasi · CoA · Jurnal/Buku Besar · Laporan Keuangan · Kas & Bank · Pajak (TaxCenter) · Tutup Buku | — | 8 live |
| SDM (HRD) | Karyawan · Struktur Org · Presensi · Shift & Geofence · Lacak Lapangan · Payroll Run · Slip Gaji · Setup Penggajian · Cuti & Izin · Lembur · KPI Design · Design Gallery AI | — | **12 live** |
| Analitik (BI) | Dashboard · Margin & HPP · BI Keuangan · BI SDM | BI Sales · BI Stok | 4 live |
| Dokumen & Print | Print Center | — | ⚠️ grup berisi 1 item (anti-pattern) |
| Admin & Master Data | Master Data & Audit (12 tab internal) · Approval Rules | — | 2 |

**Pola bagus yang SUDAH ada tapi tidak dipakai konsisten:**
- `CrmView` = 1 menu → 8 tab (Customers/Leads/Interaksi/Collection/Salesforce/Rates/Schemes/Approvals) ✅
- `operations` (WMS) = 1 view → 5 tab, dengan dukungan `item.tab` di nav ✅
- `AdminView` = 1 menu → 12 tab ✅
- Auto-collapse "Segera Hadir" ✅ · Role-filtered nav ✅ · Role-home registry ✅

---

## 2. TEMUAN IA (akar masalah)

### 2a. DUPLIKASI DOMAIN — logika/proses bisnis sama, menu terpisah di grup berbeda
| # | Duplikat | Lokasi | Masalah |
|---|---|---|---|
| D-1 | **Kas**: "Pengelolaan Kas" (`cash-management`) vs "Kas & Bank" (`bank-accounts`) | Pembelian vs Keuangan | Dua pintu untuk domain kas yang sama. Kas BUKAN sub-domain pembelian |
| D-2 | **Pajak 3 pintu**: Faktur Pajak Jual (Penjualan) · Faktur Pajak Masukan (Pembelian) · Pajak/TaxCenter (Keuangan) | 3 grup | Rekonsiliasi PPN keluaran-masukan justru butuh SATU tempat (SPT Masa) |
| D-3 | **Approval 4 pintu**: Pusat Persetujuan (standalone) · Approval Harga (Penjualan) · Approval Pembelian (Pembelian) · tab Approvals di CRM | 4 tempat | "Pusat Persetujuan" sudah dibangun sebagai pusat — tapi menu satelit tetap hidup |
| D-4 | **Stok 3 pintu**: Stok & Inventori (WMS tab) · Status Stok & ATP (`inventory-board`) · Stok Multi-Bucket | Gudang | Tiga cara melihat stok yang sama dari sudut berbeda → user bingung mana yang "benar" |
| D-5 | **Transfer 2 pintu**: Transfer Antar Gudang (WMS tab) vs Transfer Antar-Entitas | Gudang | Proses fisik identik (pindah barang), beda dimensi legal saja |
| D-6 | **Kunjungan Sales** (`hr-visits`, kicker "Penjualan") vs tab Salesforce di CRM | Penjualan | Aktivitas sales terpecah dua |
| D-7 | **Approval Rules** (menu sendiri) vs AdminView yang sudah punya 12 tab settings | Admin | Konfigurasi terpisah dari pusat konfigurasi |

### 2b. ANTI-PATTERN STRUKTUR
- **Grup 1 item**: "Dokumen & Print" → grup untuk satu tombol.
- **Grup >7 item**: Pembelian (12), SDM (12), Penjualan (10) — melampaui working memory 7±2; scanning cost tinggi.
- **Menu = tabel tunggal**: banyak menu (Slip Gaji, Lembur, Cuti, Shift & Geofence…) hanyalah satu tabel/form — layak jadi tab, bukan menu.
- **Role hygiene**: role `warehouse` melihat Tagihan Supplier, Landed Cost, Faktur Pajak Masukan (finansial AP) — tidak relevan dengan pekerjaannya.
- **PAGE_META mati**: 9 entri `cs-*` (cs-returns, cs-suppliers, cs-kas, cs-closing, cs-bank, cs-employees, cs-bi-finance, dst.) sudah punya versi live → sampah konfigurasi.

### 2c. TIDAK ADA JALUR CEPAT
Tidak ada command palette (Ctrl+K), favorit/pin, atau riwayat "sering dibuka" — padahal dengan 62 item, pencarian > navigasi.

---

## 3. BEST PRACTICE PEMBANDING (ERP matang)
- **Odoo**: ±10 app top-level; tiap app punya menu internal sendiri. Pajak, kas, retur = fitur DI DALAM app, bukan menu global.
- **SAP Fiori**: launchpad berbasis ROLE (space/pages) — user hanya melihat tile pekerjaannya; jumlah tile per space < 15.
- **NetSuite/Dynamics BC**: menu mengikuti **alur dokumen** (Quote→Order→Fulfillment→Invoice) dan "Role Center" sebagai beranda.
- **Prinsip yang diadopsi**: (1) Hub-and-Tab — menu = proses bisnis, tab = varian/langkah; (2) 7±2 item per grup; (3) urutan item = urutan proses; (4) satu domain satu pintu; (5) pencarian global sebagai jalur utama power-user.

---

## 4. USULAN STRUKTUR BARU (to-be) — **Opsi A: Restrukturisasi Penuh**

> Pola teknis: pakai mekanisme yang SUDAH ada (`item.view` + `item.tab` seperti WMS; tab internal seperti CrmView). Tanpa router baru, tanpa backend berubah.

### Standalone (4)
| Menu | Isi |
|---|---|
| Beranda | role-home (tetap) |
| ✅ **Pusat Persetujuan** | SATU pintu approval: tab **SO/Harga · Pembelian · Kredit (override) · Interco**. Menu "Approval Harga", "Approval Pembelian", tab CRM approvals → dilebur ke sini (view lama tetap ada sebagai konten tab; deep-link dipertahankan) |
| Profil Saya (ESS) | tetap |
| Eskalasi | tetap (operasional harian; badge count) |

### Penjualan (4 — dari 10)
| Menu baru | Tab di dalamnya | Asal |
|---|---|---|
| POS / Sales Portal | — | tetap |
| **Pesanan & Retur** | Pesanan (SO) · Retur & Barang Sisa · Special Order (OD) | 3 menu → 1 (satu alur pasca-jual) |
| **Pelanggan & CRM** | 8 tab existing + **Kunjungan Sales** | 2 menu → 1 (D-6) |
| **Produk & Harga** | Template & Varian · Pricelist per-PT · Price/Customer *(soon)* | 3 menu → 1 (semua = master penawaran) |
| ~~Faktur Pajak Jual~~ | → pindah ke Keuangan ▸ Pajak (D-2) | |

### Pembelian (4 — dari 12)
| Menu baru | Tab | Asal |
|---|---|---|
| **Pengadaan (Sourcing)** | Saran Reorder · PR · RFQ | 3 menu → 1 (alur pra-PO berurutan) |
| **Pesanan Pembelian** | PO · Blanket/Kontrak · *(BOM Printing — soon)* | 2 menu → 1 |
| **Pemasok** | Master · Scorecard · Price List supplier | tetap 1 |
| **Hutang Supplier (AP)** | Tagihan (3-way) · Landed Cost · Retur Beli/Nota Debit | 3 menu → 1 (alur AP satu tarikan napas) |
| ~~Pengelolaan Kas~~ → Keuangan (D-1) · ~~Faktur Masukan~~ → Keuangan ▸ Pajak (D-2) | | |

### Gudang (3 — dari 9)
| Menu baru | Tab | Asal |
|---|---|---|
| **Operasi WMS** | Inbound (+QC inspeksi) · Outbound · Transfer (antar-gudang **+ antar-entitas**) · Cycle Count | 7 menu → 1 (D-5; QC menempel di penerimaan) |
| **Stok & ATP** | Ringkasan/ATP · Roll & Inventori · Multi-Bucket · *(Analytics — soon)* | 3 menu → 1 (D-4) |
| RFID & Traceability | (Segera Hadir — tetap collapse) | |

### Keuangan (6 — dari 8, tapi menyerap 4 menu dari grup lain)
| Menu | Tab | Asal |
|---|---|---|
| **Kas & Bank** | Rekening & Saldo · Transaksi Kas (masuk/keluar) · Rekonsiliasi | melebur `cash-management` (D-1) |
| **Piutang (AR)** | Aging · Penerimaan (AR Receipts) | tetap |
| **Pajak** | Faktur Keluaran · Faktur Masukan · PPh & Rekap (TaxCenter) | 3 pintu → 1 (D-2) |
| **Buku Besar** | Jurnal & Ledger · Chart of Accounts | 2 menu → 1 |
| **Laporan & Konsolidasi** | Laba-Rugi & Neraca · Konsolidasi Grup | 2 menu → 1 |
| **Tutup Buku** | — | tetap (proses krusial, layak berdiri) |

### SDM (4 — dari 12)
| Menu | Tab | Asal |
|---|---|---|
| **Karyawan & Organisasi** | Karyawan · Struktur Org | 2 → 1 |
| **Kehadiran & Cuti** | Presensi · Cuti & Izin · Lembur · Lacak Lapangan · ⚙ Shift & Geofence | 5 → 1 |
| **Payroll** | Payroll Run · Slip Gaji · ⚙ Setup Gaji/BPJS/PPh21 | 3 → 1 |
| **KPI & Design** | KPI Design · Design Gallery AI | 2 → 1 (atau ke Segera Hadir) |

### Analitik (1 — dari 4+2)
| Menu | Tab |
|---|---|
| **Analytics Hub** | Overview (Dashboard) · Margin & HPP · BI Keuangan · BI SDM · *(BI Sales, BI Stok — soon)* |

### Pengaturan (1 — dari 2) + utilitas
| Menu | Isi |
|---|---|
| **Master Data & Pengaturan** | 12 tab existing + tab ke-13 **Approval Rules** (D-7) |
| Print Center | jadi **standalone** kecil di bawah (bukan grup sendiri) |

### 📊 Hasil Opsi A
| Role | Sekarang (live) | Sesudah | Penurunan |
|---|---|---|---|
| Admin | **62** | **± 24** | **−61%** |
| Manager | ± 55 | ± 22 | −60% |
| Warehouse | 22 | ± 8 (+ role hygiene: cabut AP/pajak) | −64% |
| Sales | 17 | ± 7 | −59% |

Grup terbesar (Pembelian) turun 12 → 4. Tidak ada grup > 6 item. Semua deep-link lama tetap hidup (view di-mount sebagai tab; `resolveActiveNavId` sudah mendukung multi-nav→satu-view).

---

## 5. Opsi B — "Light Merge" (hanya membunuh duplikasi, tanpa hub besar)
Kalau ingin perubahan minim-risiko dulu:
1. D-1 Kas: hapus `cash-management` dari Pembelian → tab di "Kas & Bank".
2. D-2 Pajak: satukan 3 menu pajak → 1 hub "Pajak" di Keuangan.
3. D-3 Approval: hapus `price-approvals` & `purchase-approval` dari nav → tab di Pusat Persetujuan.
4. D-4/D-5 Stok & Transfer: satukan inventory-board+stock-buckets; interco-transfers jadi tab Transfer.
5. D-6 Kunjungan → tab CRM. D-7 Approval Rules → tab Admin. Dokumen & Print → standalone.

Hasil: admin 62 → **± 44** (−29%). Cepat (semua pola sudah ada), tapi grup Pembelian/SDM masih gemuk.

## 6. PELENGKAP (kedua opsi)
- **Command Palette (Ctrl+K)**: cari menu + dokumen (SO/PO/nomor jurnal) — jalur utama power-user.
- **Favorit/Pin** per user di atas sidebar (max 5).
- **Badge count** di Pusat Persetujuan & Eskalasi (jumlah pending).
- **Bersih-bersih**: hapus 9 PAGE_META `cs-*` mati; update `GUIDANCE_MAP`; role hygiene warehouse.
- Konvensi ke depan: **fitur baru = tab di hub yang ada dulu; menu baru hanya jika proses bisnisnya benar-benar baru** (tulis di ENGINEERING_GUARDRAILS).

## 7. RENCANA EKSEKUSI (jika Opsi A disetujui)
1. **Fase 1 — Duplikasi (D-1…D-7)** = Opsi B. Uji regresi navigasi per role.
2. **Fase 2 — Hub Penjualan/Pembelian/Gudang** (Pesanan & Retur, Pengadaan, AP, WMS+QC, Stok).
3. **Fase 3 — Hub SDM/Keuangan/Analitik** + Pengaturan.
4. **Fase 4 — Command palette + favorit + badge**.
Tiap fase: update `navigationConfig.js` + wrapper hub kecil (pola `CrmView`) + `PAGE_META` + testing_agent navigasi per role. Backend TIDAK berubah.

**Risiko & mitigasi:** kebiasaan user berubah → tambahkan "redirect halus" (klik menu lama dari riwayat/link → buka hub pada tab yang tepat, sudah didukung `resolveActiveNavId`); onboarding tooltip 1×.
