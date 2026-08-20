/**
 * amendmentApi — FASE G-1 · jembatan tipis ke endpoint **Amandemen Dokumen**.
 *
 * Sengaja TANPA React supaya murah di-impor dari layar mana pun (panel detail SO,
 * Pusat Amandemen, Pusat Persetujuan) tanpa menarik bundel besar.
 *
 * Prinsip yang di-mirror dari backend (services/amendment_service.py):
 *   koreksi angka = DOKUMEN AMANDEMEN BERNOMOR + label alasan + dampak terhitung
 *   + persetujuan berbasis dampak + jejak dua arah. Tidak ada edit senyap.
 */
import axios, { API } from "../../../services/apiClient";

// ── Label status (SSOT tampilan) ────────────────────────────────────────────
export const AMD_STATUS_META = {
  pending_approval: { label: "Menunggu persetujuan", fg: "#8A6D00", bg: "#FFF3CD" },
  approved: { label: "Disetujui", fg: "#1B7A43", bg: "#E5F6EC" },
  applied: { label: "Diterapkan", fg: "#1B7A43", bg: "#E5F6EC" },
  auto_applied: { label: "Diterapkan otomatis", fg: "#0058CC", bg: "#EFF4FF" },
  rejected: { label: "Ditolak", fg: "#9B1C1C", bg: "#FDE2E2" },
};

export function statusMeta(status) {
  return AMD_STATUS_META[status] || { label: status || "—", fg: "#6B6B73", bg: "#F2F2F7" };
}

/** Status yang berarti "angka dokumen sudah benar-benar berubah / nota terbit". */
export const APPLIED_STATUSES = ["applied", "auto_applied"];

export const METHOD_META = {
  re_derive: {
    label: "Dihitung ulang",
    help: "Dokumen belum terbit, jadi nilainya dihitung ulang memakai mesin harga yang sama.",
    fg: "#0058CC", bg: "#EFF4FF",
  },
  credit_note: {
    label: "Nota Kredit",
    help: "Dokumen sudah terbit — angkanya TIDAK diubah. Selisih turun diterbitkan sebagai Nota Kredit.",
    fg: "#9B1C1C", bg: "#FDE2E2",
  },
  debit_note: {
    label: "Nota Debit",
    help: "Dokumen sudah terbit — angkanya TIDAK diubah. Selisih naik diterbitkan sebagai Nota Debit.",
    fg: "#1B7A43", bg: "#E5F6EC",
  },
};

export function methodMeta(method) {
  return METHOD_META[method] || { label: method || "—", help: "", fg: "#6B6B73", bg: "#F2F2F7" };
}

/** Field baris dokumen yang boleh dikoreksi (cermin EDITABLE_FIELDS backend). */
export const EDITABLE_FIELDS = ["quantity", "price", "discount_percent"];

export const FIELD_LABEL = {
  quantity: "Jumlah",
  price: "Harga satuan",
  discount_percent: "Diskon baris (%)",
  order_discount_percent: "Diskon pesanan (%)",
};

/** Ambil pesan error yang SIAP TAMPIL (backend mengirim Bahasa Indonesia). */
export function errText(e, fallback = "Terjadi kesalahan.") {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d.trim()) return d;
  if (Array.isArray(d) && d.length) {
    return d.map((x) => x?.msg || JSON.stringify(x)).join(" · ");
  }
  return e?.message || fallback;
}

// ── Label alasan (configurable oleh admin) ──────────────────────────────────
export async function listReasons(docType = "sales_order", includeInactive = false) {
  const params = {};
  if (docType) params.doc_type = docType;
  if (includeInactive) params.include_inactive = true;
  const r = await axios.get(`${API}/amendment-reasons`, { params });
  return Array.isArray(r.data) ? r.data : [];
}

export async function upsertReason(payload) {
  const r = await axios.put(`${API}/amendment-reasons`, payload);
  return r.data;
}

// ── Pratinjau & usul ────────────────────────────────────────────────────────
export async function previewAmendment(body) {
  const r = await axios.post(`${API}/amendments/preview`, body);
  return r.data;
}

export async function proposeAmendment(body) {
  const r = await axios.post(`${API}/amendments`, body);
  return r.data;
}

// ── Daftar, detail & putusan ────────────────────────────────────────────────
export async function listAmendments(params = {}) {
  const r = await axios.get(`${API}/amendments`, { params });
  return Array.isArray(r.data) ? r.data : [];
}

export async function amendmentStats(params = {}) {
  const r = await axios.get(`${API}/amendments/stats/summary`, { params });
  return r.data || {};
}

export async function amendmentDetail(id) {
  const r = await axios.get(`${API}/amendments/${id}`);
  return r.data;
}

export async function decideAmendment(id, action, note = "") {
  const r = await axios.post(`${API}/amendments/${id}/decision`, { action, note });
  return r.data;
}

/** Amandemen + nota koreksi milik SATU dokumen (untuk panel jejak di detail SO). */
export async function amendmentsForDoc(docType, docId) {
  const r = await axios.get(`${API}/amendments/doc/${docType}/${docId}`);
  return { amendments: r.data?.amendments || [], notes: r.data?.notes || [] };
}
