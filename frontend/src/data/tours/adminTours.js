/**
 * Admin tour definitions (used by tourDefinitions.js).
 * See tourDefinitions.js for the step-schema documentation.
 */

export const adminMasterData = {
  id: "admin-master-data",
  name: "Manage Master Data",
  description: "Cara menambah produk, pelanggan, gudang baru",
  roles: ["admin"],
  steps: [
    {
      before: "nav-admin-button",
      target: "nav-admin-button",
      title: "Buka Admin Panel",
      content: "Modul Admin hanya bisa diakses oleh role Admin. Tour otomatis akan membuka halamannya.",
      placement: "right",
    },
    {
      before: "admin-tab-products-button",
      target: "admin-tab-products-button",
      title: "Tab Products",
      content: "Pilih tab Products untuk mengelola master produk. Tersedia juga tab Customer, Warehouse, UOM, Templates, Permissions, Audit, Users.",
      placement: "bottom",
    },
    {
      before: "toggle-admin-create-form-button",
      target: "toggle-admin-create-form-button",
      title: "Tampilkan Formulir Buat",
      content: "Klik tombol ini untuk membuka form 'Create Product'. Klik lagi untuk menyembunyikan.",
      placement: "bottom",
    },
    {
      target: "admin-product-sku-input",
      title: "Isi Detail Produk",
      content: "Isi field SKU, nama, kategori, varian, warna, motif, grade, supplier, base unit, dan harga. Semua field wajib.",
      placement: "right",
      optional: true,
    },
    {
      target: "admin-create-product-button",
      title: "Simpan Produk",
      content: "Klik 'Simpan Product' untuk menyimpan ke master data. Produk akan langsung tersedia di POS dan inventory.",
      placement: "top",
      optional: true,
    },
  ],
};
