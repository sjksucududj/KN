/**
 * approvalsMatrixApi (PS-20 / D-14) — satu pintu akses API **matriks persetujuan**.
 *
 * Layar "Persetujuan Saya" hanya MEMBACA antrean dari `/approvals/my-queue`, tetapi
 * KEPUTUSAN tetap dikirim ke endpoint dokumen aslinya (spesifikasi R&D, PR, pesanan
 * khusus) supaya tidak ada dua jalur penulisan status.
 * Semua path ditulis literal supaya lolos gate `verify_api_contract` CHECK B.
 */
import axios, { API } from "../../services/apiClient";

/** Matriks + tingkat + kebijakan penegakan yang berlaku. */
export const approvalMatrix = (params) =>
  axios.get(`${API}/approvals/matrix`, { params }).then((r) => r.data);

/** Antrean lintas tahap: apa yang menunggu keputusan saya. */
export const myApprovalQueue = (params) =>
  axios.get(`${API}/approvals/my-queue`, { params }).then((r) => r.data);

/** Jejak keputusan & pelanggaran (audit matriks). */
export const approvalMatrixLog = (params) =>
  axios.get(`${API}/approvals/matrix-log`, { params }).then((r) => r.data);

// ── Keputusan per tahap (endpoint dokumen asli) ──────────────────────────
export const approveSpec = (id, body) =>
  axios.post(`${API}/rnd/specs/${id}/approve`, body).then((r) => r.data);

export const rejectSpec = (id, body) =>
  axios.post(`${API}/rnd/specs/${id}/reject`, body).then((r) => r.data);

export const approvePr = (id, body) =>
  axios.post(`${API}/purchase-requisitions/${id}/approve`, body).then((r) => r.data);

export const rejectPr = (id, body) =>
  axios.post(`${API}/purchase-requisitions/${id}/reject`, body).then((r) => r.data);

export const approveSpecialOrder = (id, body) =>
  axios.post(`${API}/special-orders/${id}/approve`, body).then((r) => r.data);

export const rejectSpecialOrder = (id, body) =>
  axios.post(`${API}/special-orders/${id}/reject`, body).then((r) => r.data);

/** Pesan galat yang bisa dibaca pemilik usaha (bukan stack trace). */
export function apiErr(e, fallback = "Terjadi kesalahan.") {
  return e?.response?.data?.detail || e?.message || fallback;
}
