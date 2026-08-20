/**
 * rndMeta (FASE F) — label & warna status R&D di SATU tempat supaya semua layar
 * memakai kosakata yang sama (tidak ada istilah teknis yang bocor ke pengguna).
 */
export const SPEC_STATUS_META = {
  draft: { label: "Draf", cls: "pill-muted" },
  review: { label: "Menunggu ACC", cls: "pill-warning" },
  approved: { label: "Disetujui", cls: "pill-success" },
  rejected: { label: "Ditolak", cls: "pill-danger" },
};

export const SAMPLE_STATUS_META = {
  draft: { label: "Draf", cls: "pill-muted" },
  sent: { label: "Terkirim ke supplier", cls: "pill-info" },
  in_progress: { label: "Dikerjakan", cls: "pill-warning" },
  assessed: { label: "Ada yang ACC", cls: "pill-success" },
  decided: { label: "Pemenang dipilih", cls: "pill-success" },
  cancelled: { label: "Dibatalkan", cls: "pill-danger" },
};

export const LIFECYCLE_META = {
  konsep: { label: "Konsep", tone: "#8E8E93", sellable: false },
  labdip: { label: "Labdip", tone: "#0058CC", sellable: false },
  proofing: { label: "Proofing", tone: "#6B219A", sellable: false },
  disetujui: { label: "Disetujui (belum rilis)", tone: "#B26A00", sellable: false },
  produksi: { label: "Produksi (boleh dijual)", tone: "#1B7F4B", sellable: true },
  dihentikan: { label: "Dihentikan", tone: "#C0392B", sellable: false },
};

export const ROUND_RESULT_META = {
  "": { label: "Menunggu hasil", tone: "#8E8E93" },
  revisi: { label: "Revisi", tone: "#B26A00" },
  acc: { label: "ACC", tone: "#1B7F4B" },
  tolak: { label: "Ditolak", tone: "#C0392B" },
};

export const SAMPLE_TYPE_LABEL = {
  labdip: "Labdip (kain polos)",
  proofing: "Proofing (printing)",
  bulk_sample: "Bulk sample",
};

export const DESIGN_TYPE_LABEL = {
  motif: "Motif",
  pattern: "Pattern",
  artwork: "Artwork",
};

export const DESIGN_STATUS_META = {
  draft: { label: "Draf", cls: "pill-muted" },
  approved: { label: "Disahkan", cls: "pill-success" },
  retired: { label: "Tidak dipakai", cls: "pill-danger" },
};

export const lifecycleMeta = (value) =>
  LIFECYCLE_META[(value || "produksi").toLowerCase()] || LIFECYCLE_META.produksi;

/** Ambil pesan galat backend yang sudah ramah pengguna (Bahasa Indonesia). */
export const errMsg = (e, fallback) => e?.response?.data?.detail || fallback;
