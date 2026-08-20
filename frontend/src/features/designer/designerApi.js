/**
 * designerApi (PS-18) — satu pintu akses API **Desainer** (KPI + eskalasi SLA + ekspor).
 *
 * SENGAJA terpisah dari `rndApi.js`: menu Desainer dipisahkan dari menu R&D
 * (keputusan pemilik), jadi lapisan datanya pun tidak dicampur agar mudah dirawat.
 * Semua path literal supaya lolos gate `verify_api_contract` CHECK B.
 */
import axios, { API } from "../../services/apiClient";

/** KPI per desainer untuk satu periode (`month` | `30d` | `90d` | `all`). */
export const designerKpi = (params) =>
  axios.get(`${API}/rnd/reports/designer-kpi`, { params }).then((r) => r.data);

/** Tren nilai desainer per bulan (grafik). metric: `avg_score` | `grade`. */
export const designerKpiTrend = (params) =>
  axios.get(`${API}/rnd/reports/designer-kpi/trend`, { params }).then((r) => r.data);

/** KPI MILIK SENDIRI (Profil Saya) — server menyaring, nilai rekan tidak dikirim. */
export const myDesignerKpi = (params) =>
  axios.get(`${API}/rnd/reports/my-kpi`, { params }).then((r) => r.data);

/** Papan eskalasi: round yang masih berjalan tetapi sudah lewat tenggat. */
export const slaBoard = (params) =>
  axios.get(`${API}/rnd/sla/board`, { params }).then((r) => r.data);

/** Jalankan eskalasi SLA sekarang (idempotent: 1 notifikasi per hari per round). */
export const runSlaEscalation = () =>
  axios.post(`${API}/rnd/sla/escalate`).then((r) => r.data);

/** Unduh laporan KPI desainer sebagai berkas (format: csv | xlsx | pdf). */
export const downloadDesignerKpi = (params) =>
  axios.get(`${API}/rnd/reports/designer-kpi/export`, { params, responseType: "blob" });

/** Unduh RAPOR 1 halaman untuk SATU desainer (PDF). params: {designer, period, entity_id}. */
export const downloadDesignerReport = (params) =>
  axios.get(`${API}/rnd/reports/designer-kpi/report`, { params, responseType: "blob" });

// ── PS-17 — Organisasi R&D (divisi + matriks persetujuan) ──────────────────────
/** Daftar divisi R&D + jumlah anggota + matriks persetujuan. */
export const listDivisions = (params) =>
  axios.get(`${API}/rnd/divisions`, { params }).then((r) => r.data);

/** Orang R&D (desainer + user) beserta divisinya. */
export const listDivisionMembers = (params) =>
  axios.get(`${API}/rnd/divisions/members`, { params }).then((r) => r.data);

/** Tetapkan/ubah divisi seseorang. body: {name, division}. */
export const setMemberDivision = (body, params) =>
  axios.put(`${API}/rnd/divisions/members`, body, { params }).then((r) => r.data);

/** Simpan blob hasil unduhan ke berkas di komputer pengguna. */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
