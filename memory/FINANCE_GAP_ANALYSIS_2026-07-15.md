# ANALISIS FINANCE & AKUNTANSI — Gap vs Model Bisnis (Tekstil, Multi-Entitas)
> Tanggal: 2026-07-15. Metode: audit router/service/frontend + query DB. Grounded dari kode.

## A. YANG SUDAH ADA (matang & terverifikasi)

### Buku Besar / GL (`routers/gl.py`, `gl_service.py`)
- Chart of Accounts (45 akun, standar Indonesia, hierarki parent_code).
- Jurnal (manual + auto-posting dari SO/COGS/AR/vendor bill/pajak), void, GL sync/backfill.
- **Trial Balance**, Ledger per akun, **Suspense** (reclass), **Inventory Reconciliation**, opening balance.

### Laporan Keuangan (`financial_statements.py`)
- **Laba-Rugi (Income Statement)** + margin kotor/bersih, compare periode, export CSV.
- **Neraca (Balance Sheet)** + equity lines + current earnings, balanced check, export CSV.

### AR / Piutang
- **AR Aging** per customer + bucket (`/ar/aging`), AR Receipt (apply pembayaran, void, uang muka/deposit), open-orders, credit status/gate.

### AP / Hutang
- **Vendor Bill** (3-way match, submit/approve/pay), **AP Payables Summary + Aging** (0-30/31-60/61-90/>90 per supplier & per bill), **Landed Cost** voucher (approve/pay → HPP).

### Pajak (`tax_center.py`, `tax_invoices.py`, `input_tax.py`)
- **Pusat Pajak**: PPN keluaran−masukan, PPh (21/omzet/manual), entity-aware PKP/Non-PKP.
- **Faktur Pajak Keluaran** (NSFP, replace, cancel, dokumen), **Faktur Masukan**, VAT summary.

### Kas & Bank (`bank.py`, `cash.py`)
- Rekening bank/kas, saldo, **ledger per rekening**, transaksi kas (kas kecil/besar), flag rekonsiliasi.

### Costing & Closing & Konsolidasi
- **WAC** per produk/entitas (landed-cost aware). **Tutup Buku** bulanan+tahunan (reopen/reclose/stale).
- **Konsolidasi Grup** + eliminasi intercompany.

### BI & Visualisasi (`finance_bi.py` + `BiFinanceView.jsx` + recharts)
- Tren bulanan (revenue/COGS/opex/GP/NI), KPI YTD, **rasio** (gross/net margin, current ratio, debt-to-equity), perbandingan antar-entitas. Chart aktif.
- Report operasional: stock-aging, reservation-funnel, order-velocity, top-customers, warehouse-utilization.

---

## B. GAP (belum ada / belum lengkap) — PRIORITAS

### 🔴 P0 — Kelengkapan Akuntansi Inti (paling bernilai, data sudah tersedia)
1. **Laporan Arus Kas (Cash Flow Statement)** — TIDAK ADA. Hanya P&L + Neraca (2 dari 3 laporan inti). Perlu metode tak langsung (Operasi/Investasi/Pendanaan) dari GL + perubahan neraca. *Enabler: GL + Balance Sheet compare sudah ada.*
2. **Analisis Profitabilitas / Margin** per **produk / kategori / pelanggan / sales** — TIDAK ADA sebagai laporan. Revenue−COGS(WAC) per baris SO sudah bisa dihitung; hanya perlu agregasi + drill. *Sangat relevan tekstil (margin per-SKU) & sudah ada mesin margin-aware insentif.*

### 🟠 P1 — Analitik Manajemen
3. **Proyeksi Arus Kas (Cash Flow Forecast)** — dari AR jatuh tempo + AP jatuh tempo (aging sudah ada). Posisi kas 30/60/90 hari ke depan.
4. **Anggaran (Budget) vs Aktual + Commitment Control** — TIDAK ADA. Budget per akun/periode/entitas, realisasi vs anggaran, komitmen PO terbuka.
5. **Finance Control Tower (dashboard terpadu)** — posisi kas, AR/AP aging chart, margin trend, jatuh tempo pajak, approval finance dalam satu layar + visual.

### 🟡 P2 — Lanjutan / Kepatuhan
6. **Aset Tetap & Penyusutan (Fixed Assets & Depreciation)** — TIDAK ADA. Register aset (mesin/loom), jadwal & posting penyusutan.
7. **Multi-currency / FX** — schema `currency` ada tapi FX/revaluation belum diimplementasi (relevan untuk impor bahan).
8. **Ekspor Pajak Formal** — e-Faktur (CSV/XML), SPT Masa PPN, Bukti Potong PPh. Saat ini hanya ringkasan.
9. **Rekonsiliasi Bank formal** — impor mutasi + matching (kini hanya flag reconciled).
10. **Laporan Perubahan Ekuitas** (dedicated) — kini hanya bagian Neraca.

---

## C. REKOMENDASI URUTAN EKSEKUSI
1. **Arus Kas (P0-1)** — melengkapi 3 laporan keuangan inti. Grounded penuh dari GL.
2. **Analisis Margin/Profitabilitas (P0-2)** — nilai bisnis tinggi (tekstil per-SKU), data siap.
3. **Proyeksi Kas (P1-3)** + **Finance Control Tower (P1-5)** — analitik & visual.
4. **Budget vs Actual (P1-4)**.
5. P2 sesuai kebutuhan (aset tetap, FX, ekspor pajak formal, rekonsiliasi bank).

---

## ✅ EKSEKUSI GAP FINANCE (2026-07-15) — P0 + P1 SELESAI & TERVERIFIKASI
Gate.sh 12/12 HIJAU + testing agent (iter_124): BACKEND 11/11 (100%), FRONTEND 5 view.
- P0-1 Laporan Arus Kas (indirect) — cash_flow_service.py + /api/finance/cash-flow (+export.csv, reconciled=true) + tab "Arus Kas".
- P0-2 Profitabilitas/Margin (WAC) — profitability_service.py + /api/finance/profitability (produk/kategori/pelanggan/sales + tren) + ProfitabilityView.
- P1-3 Proyeksi Kas — cashflow_forecast_service.py + /api/finance/cashflow-forecast (5 bucket) + CashFlowForecastView.
- P1-4 Anggaran vs Realisasi + Commitment — budget_service.py + /api/finance/budgets CRUD + /budget-vs-actual; koleksi budgets (seed 6) + BudgetView.
- P1-5 Finance Control Tower (Dashboard) — finance_tower_service.py + /api/finance/tower + FinanceTowerView/Parts.
Nav: "Dashboard Keuangan" (grup Keuangan) + hub "Laporan & Analitik". UI: recharts + KPI card modern.
SISA (P2, belum): Aset Tetap & Penyusutan, Multi-currency/FX, ekspor pajak formal (e-Faktur/SPT/Bukti Potong), rekonsiliasi bank, Laporan Perubahan Ekuitas.

## ✅ P2-10 Laporan Perubahan Ekuitas — SELESAI (2026-07-15)
- equity_statement_service.py + /api/finance/equity-changes (+ export.csv) — diturunkan dari balance_sheet (REKONSILIASI dgn Neraca terverifikasi).
- Frontend: tab ke-4 "Perubahan Ekuitas" (EquityChangesTab.jsx) di Laporan Keuangan (KPI + bar chart + tabel komponen).
- Testing agent iter_125: backend 17/17, frontend 18/18 (100%). gate.sh HIJAU.

## ✅ POC hygiene — 4 assertion usang dirapikan (test-only, 100% hijau)
- EPIC2 15/0 (pakai $elemMatch, abaikan order tanpa baris), EPIC3 17/0 (nomor AR opsional prefix entitas),
  EPIC7b 23/0 (seed 3 rekening), EPIC7c 44/0 (nomor JE opsional prefix entitas). Kode produk TIDAK diubah.
