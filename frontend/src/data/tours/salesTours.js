/**
 * Sales & Order tour definitions (used by tourDefinitions.js).
 * See tourDefinitions.js for the step-schema documentation.
 */

export const createSalesOrder = {
  id: "create-sales-order",
  name: "Create Sales Order",
  description: "Panduan langkah demi langkah membuat pesanan penjualan dari POS",
  roles: ["admin", "sales"],
  steps: [
    {
      before: "nav-sales-button",
      target: "nav-sales-button",
      title: "Buka Sales POS",
      content: "Mulai dari menu Sales POS di sidebar. Tour akan otomatis membuka halaman ini.",
      placement: "right",
    },
    {
      target: "customer-select",
      title: "Pilih Pelanggan",
      content: "Pilih customer dari dropdown. Jika belum ada, gunakan form 'Buat Customer' di bawahnya.",
      placement: "left",
    },
    {
      target: "product-grid",
      title: "Pilih Produk",
      content: "Klik salah satu produk di grid POS untuk menambahkannya ke keranjang dengan qty default 1 meter.",
      placement: "top",
    },
    {
      target: "cart-panel",
      title: "Review Keranjang",
      content: "Keranjang menampilkan semua produk yang dipilih beserta total. Anda bisa adjust qty atau hapus item.",
      placement: "left",
    },
    {
      target: "submit-sales-order-button",
      title: "Kirim Pesanan",
      content: "Klik 'Reserve & Submit' untuk membuat sales order. Status awal: Waiting Approval.",
      placement: "top",
    },
  ],
};

export const approveOrder = {
  id: "approve-order",
  name: "Approve Sales Order",
  description: "Cara menyetujui pesanan penjualan yang masuk",
  roles: ["admin", "manager"],
  steps: [
    {
      before: "nav-orders-button",
      target: "nav-orders-button",
      title: "Buka Menu Orders",
      content: "Buka modul Orders dari sidebar untuk melihat semua sales order.",
      placement: "right",
    },
    {
      before: "tab-list",
      target: "tab-list",
      title: "Tab Daftar Pesanan",
      content: "Pilih tab Order List untuk melihat daftar order yang masih perlu diproses.",
      placement: "bottom",
    },
    {
      target: "orders-search-input",
      title: "Cari Pesanan (Opsional)",
      content: "Gunakan search untuk filter cepat berdasarkan nomor order, customer, atau produk.",
      placement: "bottom",
    },
    {
      target: "[data-testid^='order-card-']",
      title: "Pilih Pesanan",
      content: "Klik salah satu order pada tabel untuk membuka detail di panel kanan.",
      placement: "right",
      optional: true,
    },
    {
      target: "order-detail-panel",
      title: "Tinjau & Setujui",
      content: "Cek detail order (customer, items, total). Jika status 'Waiting Approval', tombol Approve akan muncul di panel ini.",
      placement: "left",
      optional: true,
    },
  ],
};

export const orderDashboard = {
  id: "order-dashboard",
  name: "Order Dashboard & Analytics",
  description: "Cara gunakan dasbor untuk memantau pesanan",
  roles: ["admin", "manager", "sales"],
  steps: [
    {
      before: "nav-orders-button",
      target: "nav-orders-button",
      title: "Buka Menu Orders",
      content: "Buka modul Orders dari sidebar.",
      placement: "right",
    },
    {
      before: "tab-dashboard",
      target: "tab-dashboard",
      title: "Tab Dasbor",
      content: "Pilih tab 'Dashboard & Analytics' untuk melihat ringkasan performa orders.",
      placement: "bottom",
    },
    {
      target: "dashboard-metric-revenue",
      title: "Key Metrics",
      content: "Kartu Revenue menampilkan total pendapatan dalam timeframe terpilih (7/30/90 hari). Di sebelahnya ada Pending, Expiring, dan Avg Order.",
      placement: "bottom",
    },
    {
      target: "dashboard-top-customers",
      title: "Top Customers",
      content: "Lihat customer mana yang paling banyak order dan total revenue mereka.",
      placement: "right",
    },
    {
      target: "dashboard-status-distribution",
      title: "Status Distribution",
      content: "Progress bar menampilkan distribusi orders per status. Berguna untuk mengidentifikasi bottleneck di flow approval/fulfillment.",
      placement: "left",
    },
  ],
};
