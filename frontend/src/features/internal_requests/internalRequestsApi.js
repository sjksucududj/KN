/**
 * internalRequestsApi.js — FASE E-7 (E7d) · **Permintaan Internal** (`<ENT>/PIN-#####`).
 *
 * Satu tempat untuk semua panggilan + label status, supaya layar (papan stok,
 * daftar permintaan, panel detail) tidak menyalin string status masing-masing lalu
 * berbeda kata untuk keadaan yang sama.
 */
import axios, { API } from "../../services/apiClient";

export const PIN_STATUS_LABEL = {
  submitted: "Menunggu ditindak",
  converted: "Jadi transaksi antar-PT",
  rejected: "Ditolak",
  cancelled: "Dibatalkan",
};

export const PIN_STATUS_CLASS = {
  submitted: "bg-[#FFF4E5] text-[#8A5300] border-[#F5D9A8]",
  converted: "bg-[#E6F6EC] text-[#1B7F4B] border-[#BFE6CE]",
  rejected: "bg-[#FDEDE7] text-[#C0392B] border-[#F5C9BC]",
  cancelled: "bg-[#F2F2F5] text-[#6E6E73] border-[#E2E2E7]",
};

export const pinMeta = () =>
  axios.get(`${API}/internal-requests/meta`).then((r) => r.data);

export const listInternalRequests = (params = {}) =>
  axios.get(`${API}/internal-requests`, { params }).then((r) => r.data);

export const getInternalRequest = (id) =>
  axios.get(`${API}/internal-requests/${id}`).then((r) => r.data);

export const createInternalRequest = (payload) =>
  axios.post(`${API}/internal-requests`, payload).then((r) => r.data);

export const internalRequestSources = (id) =>
  axios.get(`${API}/internal-requests/${id}/sources`).then((r) => r.data);

export const convertInternalRequest = (id, payload) =>
  axios.post(`${API}/internal-requests/${id}/convert`, payload).then((r) => r.data);

export const rejectInternalRequest = (id, reason) =>
  axios.post(`${API}/internal-requests/${id}/reject`, { reason }).then((r) => r.data);

export const cancelInternalRequest = (id, reason) =>
  axios.post(`${API}/internal-requests/${id}/cancel`, { reason }).then((r) => r.data);

/** Isyarat stok satu barang (angka gabungan untuk sales, rinci untuk admin/manajer). */
export const productAvailability = (productId) =>
  axios.get(`${API}/internal-requests-availability/${productId}`).then((r) => r.data);

export const apiText = (e, fallback = "Terjadi kesalahan.") =>
  e?.response?.data?.detail || e?.message || fallback;
