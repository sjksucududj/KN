/**
 * paymentApi — FASE G-2 · jembatan tipis ke endpoint **Rencana Pembayaran & Denda**.
 *
 * Tanpa React (pola `amendmentApi.js` / `traceApi.js`) supaya panel detail SO bisa
 * mengimpornya tanpa menarik bundel layar keuangan.
 */
import axios, { API } from "../../../services/apiClient";

export const PENALTY_STATUS_META = {
  draft: { label: "Usulan (belum berjurnal)", fg: "#8A6D00", bg: "#FFF3CD" },
  issued: { label: "Terbit (berjurnal)", fg: "#0058CC", bg: "#EFF4FF" },
  adjusted: { label: "Nominal diubah", fg: "#6B219A", bg: "#F3EAFB" },
  waived: { label: "Dibebaskan", fg: "#6B6B73", bg: "#F2F2F7" },
  paid: { label: "Sudah dibayar", fg: "#1B7A43", bg: "#E5F6EC" },
};

export function penaltyMeta(status) {
  return PENALTY_STATUS_META[status] || { label: status || "—", fg: "#6B6B73", bg: "#F2F2F7" };
}

export const LINE_STATUS_META = {
  open: { label: "Belum dibayar", fg: "#8A6D00", bg: "#FFF3CD" },
  partial: { label: "Sebagian", fg: "#0058CC", bg: "#EFF4FF" },
  paid: { label: "Lunas", fg: "#1B7A43", bg: "#E5F6EC" },
};

export function lineMeta(status) {
  return LINE_STATUS_META[status] || LINE_STATUS_META.open;
}

export function errText(e, fallback = "Terjadi kesalahan.") {
  return e?.response?.data?.detail || e?.message || fallback;
}

export function money(n) {
  return "Rp " + Number(n || 0).toLocaleString("id-ID", { maximumFractionDigits: 0 });
}

export async function fetchMeta(entityId = "", customerId = "") {
  const r = await axios.get(`${API}/payment-plans/meta`, {
    params: { entity_id: entityId && entityId !== "all" ? entityId : "", customer_id: customerId },
  });
  return r.data || {};
}

export async function previewPlan(body) {
  const r = await axios.post(`${API}/payment-plans/preview`, body);
  return r.data || {};
}

export async function planByDoc(docType, docId) {
  const r = await axios.get(`${API}/payment-plans/by-doc/${docType}/${docId}`);
  return r.data || {};
}

export async function createPlan(body) {
  const r = await axios.post(`${API}/payment-plans`, body);
  return r.data || {};
}

export async function updatePlan(planId, body) {
  const r = await axios.patch(`${API}/payment-plans/${planId}`, body);
  return r.data || {};
}

export async function voidPlan(planId, reason) {
  const r = await axios.post(`${API}/payment-plans/${planId}/void`, { reason });
  return r.data || {};
}

export async function accrueNow(planId) {
  const r = await axios.post(`${API}/payment-plans/${planId}/accrue`, null);
  return r.data || {};
}

export async function listPlans(params = {}) {
  const r = await axios.get(`${API}/payment-plans`, { params });
  return r.data || { items: [] };
}

export async function listPenalties(params = {}) {
  const r = await axios.get(`${API}/penalties`, { params });
  return r.data || { items: [], stats: {} };
}

export async function issuePenalty(id) {
  const r = await axios.post(`${API}/penalties/${id}/issue`, null);
  return r.data || {};
}

export async function waivePenalty(id, body) {
  const r = await axios.post(`${API}/penalties/${id}/waive`, body);
  return r.data || {};
}

export async function adjustPenalty(id, body) {
  const r = await axios.post(`${API}/penalties/${id}/adjust`, body);
  return r.data || {};
}

export async function payPenalty(id, body) {
  const r = await axios.post(`${API}/penalties/${id}/pay`, body);
  return r.data || {};
}

/* ── FASE G-3 — Selisih Pembayaran (lebih & kurang bayar) ───────────────────
 * Setiap selisih di luar toleransi WAJIB punya keputusan berlabel. Jembatan ini
 * dipakai dialog di layar kwitansi maupun antrean "Selisih Bayar" di Keuangan.
 */
export const VARIANCE_KIND_META = {
  outstanding: { label: "Sisa tetap jadi piutang", fg: "#0058CC", bg: "#EFF4FF" },
  reschedule: { label: "Jadwal diubah", fg: "#6B219A", bg: "#F3EAFB" },
  writeoff: { label: "Sisa dihapus", fg: "#9B1C1C", bg: "#FDE2E2" },
  deposit: { label: "Jadi deposit pelanggan", fg: "#1B7A43", bg: "#E5F6EC" },
  allocate: { label: "Dialokasikan ke pesanan lain", fg: "#0058CC", bg: "#EFF4FF" },
  refund: { label: "Dana dikembalikan", fg: "#8A6D00", bg: "#FFF3CD" },
  rounding_writeoff: { label: "Pembulatan — sisa dihapus", fg: "#6B6B73", bg: "#F2F2F7" },
  rounding_deposit: { label: "Pembulatan — jadi deposit", fg: "#6B6B73", bg: "#F2F2F7" },
  ap_outstanding: { label: "Sisa tetap hutang supplier", fg: "#0058CC", bg: "#EFF4FF" },
  ap_writeoff: { label: "Sisa hutang ditutup", fg: "#9B1C1C", bg: "#FDE2E2" },
  ap_advance: { label: "Jadi uang muka supplier", fg: "#1B7A43", bg: "#E5F6EC" },
  ap_rounding_writeoff: { label: "Pembulatan — hutang ditutup", fg: "#6B6B73", bg: "#F2F2F7" },
  ap_rounding_advance: { label: "Pembulatan — uang muka", fg: "#6B6B73", bg: "#F2F2F7" },
};

export function varianceKindMeta(kind) {
  return VARIANCE_KIND_META[kind] || { label: kind || "—", fg: "#6B6B73", bg: "#F2F2F7" };
}

export const DIRECTION_META = {
  under: { label: "Kurang bayar", fg: "#9B1C1C", bg: "#FDE2E2" },
  over: { label: "Lebih bayar", fg: "#8A6D00", bg: "#FFF3CD" },
  rounding: { label: "Pembulatan", fg: "#6B6B73", bg: "#F2F2F7" },
  none: { label: "Pas", fg: "#1B7A43", bg: "#E5F6EC" },
};

export function directionMeta(dir) {
  return DIRECTION_META[dir] || DIRECTION_META.none;
}

export async function varianceMeta(entityId = "", customerId = "") {
  const r = await axios.get(`${API}/payment-variances/meta`, {
    params: { entity_id: entityId && entityId !== "all" ? entityId : "", customer_id: customerId },
  });
  return r.data || {};
}

export async function assessVariance(body) {
  const r = await axios.post(`${API}/payment-variances/assess`, body);
  return r.data || {};
}

export async function listVariances(params = {}) {
  const r = await axios.get(`${API}/payment-variances`, { params });
  return r.data || { items: [], pending: [], stats: {} };
}

export async function pendingVariances(params = {}) {
  const r = await axios.get(`${API}/payment-variances/pending`, { params });
  return r.data || { items: [] };
}

export async function varianceByReceipt(receiptId) {
  const r = await axios.get(`${API}/payment-variances/receipt/${receiptId}`);
  return r.data || {};
}

export async function decideVariance(receiptId, body) {
  const r = await axios.post(`${API}/payment-variances/receipt/${receiptId}/decide`, body);
  return r.data || {};
}

export async function reverseVariance(decisionId, reason) {
  const r = await axios.post(`${API}/payment-variances/${decisionId}/reverse`, { reason });
  return r.data || {};
}
