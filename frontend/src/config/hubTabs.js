/**
 * hubTabs.js — TAB per HUB (Restrukturisasi IA — Opsi A).
 *
 * Satu menu = satu proses bisnis; variasi/langkahnya menjadi TAB (bar sekunder di
 * atas view). `view` = activeView yang dirender AppViewRouter (komponen TIDAK
 * berubah, deep-link lama tetap hidup). `roles` = siapa yang boleh melihat tab itu.
 *
 * DIPISAH dari `navStructure.js` (S#FASE-F) karena keduanya sama-sama registri DATA
 * yang terus bertambah setiap ada menu baru; digabung membuat satu berkas terus
 * melewati panduan panjang berkas tanpa alasan struktural.
 * SSOT tetap satu: `navigationConfig.js` me-re-export dari sini.
 */
export const HUB_TABS = {
  "approval-inbox": [
    { view: "approval-inbox",    label: "Inbox Persetujuan",     roles: ["manager", "admin"] },
    { view: "my-approvals",      label: "Persetujuan Saya",      roles: ["manager", "admin"] },
    { view: "price-approvals",   label: "Persetujuan Harga",        roles: ["admin", "sales", "manager"] },
    { view: "purchase-approval", label: "Persetujuan Pembelian",    roles: ["admin", "manager"] },
  ],
  "sales-orders": [
    { view: "orders",            label: "Pesanan (SO)",          roles: ["admin", "sales", "manager"] },
    { view: "amendments",        label: "Koreksi & Amandemen",   roles: ["admin", "sales", "manager"] },
    { view: "returns",           label: "Retur & Barang Sisa",   roles: ["admin", "sales", "manager"] },
    { view: "return-policies",   label: "Kebijakan Retur",       roles: ["admin", "manager"] },
    { view: "special-orders",    label: "Pesanan Khusus (OD)",    roles: ["admin", "sales", "manager"] },
    // FASE E-7 (E7d) — jalur yang dulu buntu: papan stok bilang "tersedia di badan
    // usaha lain", tetapi seluruh menu Antar Entitas 403 untuk sales. Di sini sales
    // MENGAJUKAN, admin/manajer MENINDAK (jadi transaksi antar-PT G-6).
    { view: "internal-requests", label: "Permintaan Internal (PIN)", roles: ["admin", "sales", "manager"] },
  ],
  "customers-crm": [
    { view: "customers-crm",     label: "CRM & Pelanggan",       roles: ["admin", "sales", "manager"] },
    { view: "hr-visits",         label: "Kunjungan Sales",       roles: ["admin", "sales", "manager"] },
  ],
  "products-pricing": [
    { view: "md-products",       label: "Produk (Master)",       roles: ["admin", "manager"] },
    { view: "product-templates", label: "Template & Varian",     roles: ["admin", "manager"] },
    { view: "md-categories",     label: "Kategori",              roles: ["admin", "manager"] },
    { view: "color-library",     label: "Pustaka Warna",         roles: ["admin", "manager"] },
    { view: "md-uoms",           label: "Satuan (UOM)",          roles: ["admin", "manager"] },
    { view: "domain-registry",   label: "Registry Domain",       roles: ["admin", "manager"] },
    { view: "uom-conversions",   label: "Konversi Satuan",       roles: ["admin", "manager"] },
    { view: "pricelist",         label: "Pricelist per-PT",      roles: ["admin", "manager"] },
  ],
  "sourcing": [
    { view: "reorder",               label: "Saran Reorder",     roles: ["admin", "manager"] },
    { view: "purchase-requisitions", label: "Permintaan Pembelian", roles: ["admin", "manager", "warehouse"] },
    { view: "rfq",                   label: "RFQ / Penawaran",   roles: ["admin", "manager", "warehouse"] },
  ],
  "purchase-orders": [
    { view: "purchasing",        label: "Pesanan Pembelian (PO)", roles: ["admin", "manager"] },
    { view: "blanket-po",        label: "Blanket / Kontrak",     roles: ["admin", "manager"] },
    { view: "makloon-orders",    label: "Order Makloon",         roles: ["admin", "manager", "warehouse", "sales"] },
    { view: "makloon-claims",    label: "Klaim Selisih Makloon", roles: ["admin", "manager", "warehouse"] },
  ],
  "master-pembelian": [
    { view: "suppliers",         label: "Pemasok (Supplier)",    roles: ["admin", "manager"] },
    { view: "makloons",          label: "Mitra Makloon",         roles: ["admin", "manager"] },
    { view: "supplier-contracts", label: "Kontrak Mitra & Supplier", roles: ["admin", "manager", "warehouse"] },
    { view: "supplier-items",    label: "Barang Supplier",       roles: ["admin", "manager", "warehouse"] },
    { view: "process-recipes",   label: "Resep Proses",          roles: ["admin", "manager"] },
  ],
  "accounts-payable": [
    { view: "vendor-bills",      label: "Tagihan Supplier",      roles: ["admin", "manager"] },
    // FASE G-7 — kontrabon: satu siklus tukar faktur = satu tanda terima + satu
    // pembayaran. Gudang ikut MELIHAT karena tab "GR Belum Ditagih" adalah pekerjaan
    // mereka (barang sudah diterima tapi faktur supplier belum datang).
    { view: "contra-bons",       label: "Kontrabon (Tukar Faktur)", roles: ["admin", "manager", "warehouse"] },
    // FASE G-6 — antar-PT sebagai jual-beli (bukan pindah gudang): dokumen kembar,
    // saldo pasangan PT, settlement/netting. Gudang boleh MELIHAT (barang fisik
    // tetap lewat mereka) & menandai ship/receive.
    { view: "interco-transactions", label: "Antar Entitas (Jual-Beli)", roles: ["admin", "manager", "warehouse"] },
    { view: "landed-cost",       label: "Landed Cost (HPP)",     roles: ["admin", "manager"] },
    { view: "purchase-returns",  label: "Retur Beli (Nota Debit)", roles: ["admin", "manager", "warehouse"] },
  ],
  // FASE F — R&D: hulu rantai (spesifikasi → labdip/proofing → kontrak).
  // warehouse ikut melihat karena dialah yang mengeluarkan bahan sample (PS-19).
  // CATATAN IA (PS-18): "Desain & Pattern" DIPINDAH ke hub `designer-hub` supaya
  // urusan desainer tidak lagi bercampur dengan proses R&D.
  "rnd-hub": [
    { view: "rnd-specs",   label: "Spesifikasi Produk", roles: ["admin", "manager", "sales"] },
    { view: "rnd-samples", label: "Permintaan Sample",  roles: ["admin", "manager", "sales", "warehouse"] },
    { view: "rnd-reports", label: "Laporan R&D",        roles: ["admin", "manager"] },
  ],
  // PS-18 — hub DESAINER (terpisah dari R&D): orang + karyanya.
  "designer-hub": [
    { view: "designer-kpi",      label: "KPI Desainer",       roles: ["admin", "manager"] },
    { view: "rnd-designs",       label: "Desain & Pattern",   roles: ["admin", "manager"] },
    { view: "cs-design-gallery", label: "Galeri Desain + AI", roles: ["admin", "manager"] },
    { view: "rnd-divisions",     label: "Divisi & Persetujuan", roles: ["admin", "manager"] },
  ],
  "wms-operations": [
    { view: "operations",        label: "Operasi WMS",           roles: ["admin", "warehouse", "manager", "sales"] },
    { view: "qc-inspection",     label: "Inspeksi QC",           roles: ["admin", "warehouse", "manager"] },
    { view: "interco-transfers", label: "Transfer Antar-Entitas", roles: ["admin", "warehouse", "manager"] },
  ],
  "stock-atp": [
    { view: "inventory-board",   label: "Status Stok & ATP",     roles: ["admin", "warehouse", "manager", "sales"] },
    { view: "stock-buckets",     label: "Stok Multi-Bucket",     roles: ["admin", "warehouse", "manager"] },
    { view: "inventory-lots",    label: "Lot & Silsilah",        roles: ["admin", "warehouse", "manager", "sales"] },
  ],
  "cash-bank": [
    { view: "bank-accounts",     label: "Rekening & Saldo",      roles: ["admin", "manager"] },
    { view: "cash-management",   label: "Transaksi Kas",         roles: ["admin", "manager"] },
    { view: "bank-reconciliation", label: "Rekonsiliasi Bank",   roles: ["admin", "manager"] },
  ],
  "petty-cash": [
    { view: "cash-advances",      label: "Pengajuan Dana (PD)",  roles: ["admin", "manager", "sales"] },
    { view: "settlements",        label: "Pertanggungjawaban",   roles: ["admin", "manager", "sales"] },
    { view: "expense-categories", label: "Kategori Beban",       roles: ["admin", "manager"] },
  ],
  "tax-hub": [
    { view: "tax-invoices",      label: "Faktur Keluaran",       roles: ["admin", "manager"] },
    { view: "input-tax",         label: "Faktur Masukan",        roles: ["admin", "manager"] },
    { view: "cs-pajak",          label: "PPh & Rekap",           roles: ["admin", "manager"] },
  ],
  "ledger": [
    { view: "general-ledger",    label: "Jurnal & Buku Besar",   roles: ["admin", "manager"] },
    { view: "chart-of-accounts", label: "Chart of Accounts",     roles: ["admin", "manager"] },
  ],
  "fin-reports": [
    { view: "financial-statements", label: "Laba-Rugi, Neraca & Arus Kas", roles: ["admin", "manager"] },
    { view: "profitability",        label: "Profitabilitas & Margin",       roles: ["admin", "manager"] },
    { view: "cashflow-forecast",    label: "Proyeksi Arus Kas",             roles: ["admin", "manager"] },
    { view: "budget",               label: "Anggaran vs Realisasi",         roles: ["admin", "manager"] },
    { view: "consolidation",        label: "Konsolidasi Grup",              roles: ["admin", "manager"] },
  ],
  "hr-people": [
    { view: "hr-employees",      label: "Karyawan",              roles: ["admin", "manager"] },
    { view: "hr-org-units",      label: "Struktur Organisasi",   roles: ["admin", "manager"] },
  ],
  "hr-attendance-hub": [
    { view: "hr-attendance",       label: "Presensi",            roles: ["admin", "manager"] },
    { view: "hr-leave",            label: "Cuti & Izin",         roles: ["admin", "manager"] },
    { view: "hr-overtime",         label: "Lembur",              roles: ["admin", "manager"] },
    { view: "hr-live-tracking",    label: "Lacak Lapangan",      roles: ["admin", "manager"] },
    { view: "hr-attendance-setup", label: "Shift & Geofence",    roles: ["admin", "manager"] },
  ],
  "hr-payroll-hub": [
    { view: "hr-payroll-runs",   label: "Payroll Run",           roles: ["admin", "manager"] },
    { view: "hr-payslips",       label: "Slip Gaji",             roles: ["admin", "manager"] },
    // FASE G-0 — "Setup Penggajian" DIHAPUS. Semua aturan BPJS/PPh21/lembur kini
    // hanya ada di Pusat Pengaturan (kelompok "SDM & Penggajian"). Manager tetap
    // berwenang mengubahnya lewat izin hr.manage_payroll — tidak ada wewenang hilang.
  ],
  "hr-kpi-hub": [
    { view: "cs-kpi",            label: "KPI Karyawan (manual)", roles: ["admin", "manager"] },
  ],
  "analytics": [
    { view: "reports",           label: "Ringkasan",              roles: ["admin", "manager"] },
    { view: "costing",           label: "Margin & HPP",          roles: ["admin", "manager"] },
    { view: "bi-finance",        label: "BI Keuangan",           roles: ["admin", "manager"] },
    { view: "cs-bi-hrd",         label: "BI SDM",                roles: ["admin", "manager"] },
  ],
  // FASE G-4 — Pusat Dokumen menjadi hub: daftar dokumen + Jejak Dokumen (relasi surat).
  "document-center": [
    { view: "document-center", label: "Daftar Dokumen",  roles: ["admin", "sales", "manager", "warehouse"] },
    { view: "doc-trace",       label: "Jejak Dokumen",   roles: ["admin", "sales", "manager", "warehouse"] },
  ],
  "settings-hub": [
    { view: "settings-config",   label: "Pusat Pengaturan",      roles: ["admin", "manager"] },
    // FASE E-3 — SATU PINTU badan usaha & hak akses (mengganti tab "Entities" dan
    // "Users" di Master Data, yang sengaja DIHAPUS supaya tidak ada dua pintu).
    { view: "entities-access",   label: "Badan Usaha & Akses",   roles: ["admin", "manager"] },
    { view: "admin",             label: "Master Data & Audit",   roles: ["admin"] },
    // FASE E-4 (E4d) — master BERLAPIS global → badan usaha (syarat bayar, kategori
    // biaya, kop surat, kebijakan retur, tarif insentif, aturan persetujuan).
    { view: "entity-masters",    label: "Master per Badan Usaha", roles: ["admin", "manager"] },
    { view: "scheduler",         label: "Penjadwal & Notifikasi", roles: ["admin", "manager"] },
    { view: "pdf-templates",     label: "Template PDF",          roles: ["admin"] },
    { view: "approval-rules",    label: "Aturan Persetujuan",        roles: ["admin"] },
  ],
};
