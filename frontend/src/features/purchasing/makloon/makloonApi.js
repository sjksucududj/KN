/**
 * makloonApi (FASE D) — satu pintu akses API makloon rantai proses.
 * Semua endpoint ber-prefix /api (REACT_APP_BACKEND_URL) via apiClient.
 */
import axios, { API } from "../../../services/apiClient";

// ── Estimasi & simulasi (wizard) ─────────────────────────────────────────────
export const estimateStep = (body) =>
  axios.post(`${API}/makloon-orders/estimate`, body).then((r) => r.data);

export const tariffPreview = (body) =>
  axios.post(`${API}/supplier-contracts/tariff-preview`, body).then((r) => r.data);

export const resolveContract = (params) =>
  axios.post(`${API}/supplier-contracts/resolve`, null, { params }).then((r) => r.data);

// ── Kontrak mitra/supplier ───────────────────────────────────────────────────
export const listContracts = (params) =>
  axios.get(`${API}/supplier-contracts`, { params }).then((r) => r.data);
export const contractStats = (params) =>
  axios.get(`${API}/supplier-contracts/stats`, { params }).then((r) => r.data);
export const createContract = (body) =>
  axios.post(`${API}/supplier-contracts`, body).then((r) => r.data);
export const patchContract = (id, body) =>
  axios.patch(`${API}/supplier-contracts/${id}`, body).then((r) => r.data);
export const setContractStatus = (id, status, reason = "") =>
  axios.post(`${API}/supplier-contracts/${id}/status`, { status, reason }).then((r) => r.data);
export const deleteContract = (id) =>
  axios.delete(`${API}/supplier-contracts/${id}`).then((r) => r.data);

// ── Kebijakan makloon (D-05/D-09) ────────────────────────────────────────────
// FASE G-0: `updatePolicy` DIHAPUS — kebijakan makloon hanya diubah lewat Pusat
// Pengaturan (kelompok "Produksi & Makloon"). Pembacaan tetap boleh, karena layar
// kontrak menampilkan kebijakan yang sedang berlaku.
export const getPolicy = () => axios.get(`${API}/supplier-contracts/policy`).then((r) => r.data);

// ── Klaim selisih (PS-11 · D-09) ─────────────────────────────────────────────
export const listClaims = (params) =>
  axios.get(`${API}/makloon-orders/claims`, { params }).then((r) => r.data);
export const claimStats = (params) =>
  axios.get(`${API}/makloon-orders/claims/stats`, { params }).then((r) => r.data);
export const proposeClaim = (mkoId, body) =>
  axios.post(`${API}/makloon-orders/${mkoId}/claim`, body).then((r) => r.data);
export const approveClaim = (mkoId, body) =>
  axios.post(`${API}/makloon-orders/${mkoId}/claim/approve`, body).then((r) => r.data);
export const rejectClaim = (mkoId, body) =>
  axios.post(`${API}/makloon-orders/${mkoId}/claim/reject`, body).then((r) => r.data);
export const partnerScorecard = (params) =>
  axios.get(`${API}/makloon-partners/scorecard`, { params }).then((r) => r.data);

// ── Registry enum (tanpa hardcode di FE — R7) ────────────────────────────────
export const fetchEnum = (name) => axios.get(`${API}/enums/${name}`).then((r) => r.data);

// ── FASE T — TAHAPAN PROSES dari master (keputusan pemilik 4a) ────────────────
// `spk_only` menyaring tahap yang memang bisa jadi langkah SPK (jenis makloon &
// sampling); `line` menyaring menurut lini kerja bila layarnya sedang berlini.
// Dipakai wizard & modal 1-langkah supaya keduanya membaca daftar yang SAMA.
export const fetchStages = (params = {}) =>
  axios.get(`${API}/process-stages`, { params: { spk_only: 1, ...params } }).then((r) => r.data);

/** FASE T — selesaikan langkah "jasa murni": tagihan mitra lahir, kain tidak bergerak. */
export const recordService = (mkoId, body) =>
  axios.post(`${API}/makloon-orders/${mkoId}/record-service`, body).then((r) => r.data);

export const CLAIM_STATUS_META = {
  none: { label: "—", cls: "pill-muted" },
  open: { label: "Selisih Terbuka", cls: "pill-warning" },
  pending_approval: { label: "Menunggu Persetujuan", cls: "pill-info" },
  approved: { label: "Disetujui", cls: "pill-success" },
  rejected: { label: "Ditolak", cls: "pill-danger" },
};

export const CLAIM_ACTION_LABELS = {
  potong_bon: "Potong bon (kurangi tagihan jasa)",
  tagih_ganti: "Tagih ganti rugi ke mitra",
  terima_catatan: "Terima dengan catatan",
};

export const CONTRACT_STATUS_META = {
  draft: { label: "Draf", cls: "pill-muted" },
  active: { label: "Aktif", cls: "pill-success" },
  expired: { label: "Kedaluwarsa", cls: "pill-warning" },
  terminated: { label: "Dihentikan", cls: "pill-danger" },
};

/** Label basis tarif — diambil dari registry, fallback aman bila offline. */
export const FALLBACK_BASIS_LABELS = {
  pick: "Per pick (PPI × tarif)", kg: "Per kilogram", meter: "Per meter", yard: "Per yard",
  ball: "Per ball", cone: "Per cone", roll: "Per roll", lot: "Per lot (borongan)",
  lumpsum: "Borongan / lumpsum", custom: "Formula custom",
};

export const AUX_BASIS_OPTIONS = [
  { value: "lumpsum", label: "Sekali (lumpsum)" },
  { value: "per_roll", label: "Per roll" },
  { value: "per_color", label: "Per warna (screen)" },
  { value: "per_repeat", label: "Per repeat" },
  { value: "per_kg", label: "Per kg" },
  { value: "per_meter", label: "Per meter" },
  { value: "per_output_unit", label: "Per satuan output" },
];
