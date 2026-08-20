// SSOT metadata untuk Mode Pemenuhan (Sub-fase 1.4 — ATP & Fulfillment Modes, KN_16 §2).
// Dipakai oleh CartPanel (POS) & Inventory Status Board agar label/warna konsisten.

export const FULFILLMENT_MODES = {
  from_stock: {
    label: "Dari Stok",
    short: "Stok",
    cls: "fmode-from_stock",
    desc: "Stok fisik milik entitas penjual cukup.",
  },
  from_incoming: {
    label: "Dari Incoming (ATP)",
    short: "ATP",
    cls: "fmode-from_incoming",
    desc: "Sebagian dipatok ke barang masuk (PO / dalam perjalanan).",
  },
  inter_company: {
    label: "Antar-Entitas",
    short: "Inter-Co",
    cls: "fmode-inter_company",
    desc: "Dipenuhi dari stok entitas lain (perlu transfer).",
  },
  backorder: {
    label: "Backorder",
    short: "Backorder",
    cls: "fmode-backorder",
    desc: "Tidak ada sumber \u2192 menunggu stok.",
  },
};

export const modeMeta = (mode) =>
  FULFILLMENT_MODES[mode] || { label: mode || "-", short: mode || "-", cls: "fmode-backorder", desc: "" };
