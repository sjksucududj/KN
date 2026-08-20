/**
 * WMS / Operations tour definitions (used by tourDefinitions.js).
 * See tourDefinitions.js for the step-schema documentation.
 */

export const processInbound = {
  id: "process-inbound",
  name: "Process Inbound Receipt",
  description: "Cara menerima barang masuk dari supplier",
  roles: ["admin", "warehouse"],
  steps: [
    {
      before: "nav-operations-button",
      target: "nav-operations-button",
      title: "Buka WMS",
      content: "Buka modul WMS dari sidebar untuk masuk ke warehouse operations.",
      placement: "right",
    },
    {
      before: "wms-tab-inbound",
      target: "wms-tab-inbound",
      title: "Tab Barang Masuk",
      content: "Pilih tab Inbound untuk melihat task receiving dari Purchase Order.",
      placement: "bottom",
    },
    {
      target: "[data-testid^='inbound-task-']",
      title: "Pilih Tugas PO",
      content: "Klik PO/task yang barangnya sudah datang dan siap diterima. Panel scan akan muncul di kanan.",
      placement: "right",
      optional: true,
    },
    {
      title: "Scan & Kirim Penerimaan",
      content: "Pada panel scan: input qty diterima, batch/lot/roll (opsional), lalu klik Submit. Anda juga bisa pakai kamera untuk scan barcode.",
      placement: "center",
    },
  ],
};

export const processOutbound = {
  id: "process-outbound",
  name: "Process Outbound Fulfillment",
  description: "Cara memenuhi pesanan penjualan dari gudang",
  roles: ["admin", "warehouse"],
  steps: [
    {
      before: "nav-operations-button",
      target: "nav-operations-button",
      title: "Buka WMS",
      content: "Masuk ke modul WMS dari sidebar.",
      placement: "right",
    },
    {
      before: "wms-tab-outbound",
      target: "wms-tab-outbound",
      title: "Tab Barang Keluar",
      content: "Pilih tab Outbound untuk melihat semua task picking dari sales order yang sudah di-confirm.",
      placement: "bottom",
    },
    {
      target: "[data-testid^='outbound-task-']",
      title: "Pilih Tugas Barang Keluar",
      content: "Klik salah satu task untuk membuka panel pick & dispatch.",
      placement: "right",
      optional: true,
    },
    {
      title: "Ambil & Kirim",
      content: "Pada panel pick: input qty yang dipick + detail batch/lot, lalu klik 'Submit Pick'. Jika qty sudah penuh, tombol 'Dispatch' akan aktif untuk mengirim order.",
      placement: "center",
    },
  ],
};

export const inventoryManagement = {
  id: "inventory-management",
  name: "Manage Inventory Stock",
  description: "Cara cek dan kelola stok persediaan",
  roles: ["admin", "warehouse", "manager"],
  steps: [
    {
      before: "nav-operations-button",
      target: "nav-operations-button",
      title: "Buka WMS",
      content: "Mulai dari modul WMS di sidebar.",
      placement: "right",
    },
    {
      before: "wms-tab-stok",
      target: "wms-tab-stok",
      title: "Tab Stok",
      content: "Pilih tab Stok untuk melihat inventory balance semua produk di setiap warehouse.",
      placement: "bottom",
    },
    {
      target: "inventory-stock-view",
      title: "Ringkasan Stok",
      content: "Halaman ini menampilkan ringkasan: Total On Hand, Available, Reserved, dan jumlah stok rendah. Data real-time per warehouse.",
      placement: "top",
    },
    {
      target: "inventory-search-input",
      title: "Cari Produk",
      content: "Gunakan search untuk filter cepat berdasarkan SKU, nama produk, atau nama gudang.",
      placement: "bottom",
    },
    {
      target: "inventory-warehouse-filters",
      title: "Filter per Gudang",
      content: "Klik pill gudang untuk filter stock pada warehouse tertentu saja. 'Semua Gudang' menampilkan total agregat.",
      placement: "bottom",
    },
  ],
};
