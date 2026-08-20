/**
 * FASE F — satu tempat menerjemahkan `products.lifecycle` menjadi
 * "boleh dijual atau belum" untuk kebutuhan UI.
 *
 * SUMBER KEBENARAN tetap server (`backend/services/rnd_gate.py:assert_orderable`,
 * dipakai di SO/PR/PO/katalog). Berkas ini HANYA pagar UX supaya sales tidak
 * menabrak penolakan di ujung checkout — logika & ambangnya disamakan persis:
 *   · lifecycle kosong/tidak ada  = data lama = dianggap `produksi` (boleh dijual)
 *   · hanya `produksi` yang boleh masuk keranjang/dokumen
 *   · penegakan mengikuti kebijakan `rnd.lifecycle_enforcement`
 *     (`off` = abaikan · `warn` = boleh tapi diberi tahu · `block` = dilarang)
 */

export const LIFECYCLE_LABEL = {
  konsep: "Konsep R&D",
  labdip: "Tahap labdip",
  proofing: "Tahap proofing",
  disetujui: "Disetujui (belum rilis)",
  produksi: "Produksi",
  dihentikan: "Dihentikan",
};

// Alasan yang BISA DITINDAK — bukan sekadar "tidak boleh".
const REASON = {
  konsep: "masih konsep R&D (belum ada sample yang disetujui)",
  labdip: "sedang tahap labdip (menunggu hasil sample warna)",
  proofing: "sedang tahap proofing (menunggu hasil sample printing)",
  disetujui: "spesifikasinya sudah disetujui tetapi BELUM dirilis ke produksi",
  dihentikan: "sudah dihentikan (discontinued)",
};

export const ORDERABLE_LIFECYCLES = ["produksi"];

/** Lifecycle efektif; kosong → `produksi` (kompatibilitas data lama). */
export function lifecycleOf(product) {
  return String(product?.lifecycle || "").trim().toLowerCase() || "produksi";
}

export function isOrderable(product) {
  return ORDERABLE_LIFECYCLES.includes(lifecycleOf(product));
}

/** Label pendek untuk badge kartu produk. */
export function lifecycleLabel(product) {
  const lc = lifecycleOf(product);
  return LIFECYCLE_LABEL[lc] || lc;
}

/** Pesan lengkap + jalan keluarnya (dipakai notice/keranjang/quick view). */
export function notOrderableReason(product) {
  const lc = lifecycleOf(product);
  const name = product?.name || product?.sku || "Produk ini";
  return `${name} belum boleh dijual — ${REASON[lc] || lc}. `
    + "Selesaikan alur R&D (Spesifikasi → Sample → Rilis ke Produksi) di menu "
    + "R&D & Desain, atau ubah kebijakan di Pengaturan → R&D & Desain.";
}

/**
 * Apakah UI harus MELARANG (bukan cuma memberi tahu)?
 * Mengikuti kebijakan server; default `block` (sama seperti default registry).
 */
export function blocksOrder(product, enforcement = "block") {
  const mode = String(enforcement || "block").trim().toLowerCase();
  if (mode === "off") return false;
  return !isOrderable(product) && mode !== "warn";
}
