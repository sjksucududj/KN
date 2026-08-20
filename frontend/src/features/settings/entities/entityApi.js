/**
 * entityApi.js — lapisan API untuk layar "Badan Usaha & Akses" (FASE E-3).
 *
 * Satu berkas supaya komponen tidak menyebar URL. Semua pesan galat dikembalikan
 * apa adanya dari server (server sudah berbahasa Indonesia & menuntun), sehingga
 * layar tidak perlu mengarang kalimat sendiri.
 */
import axios, { API } from "../../../services/apiClient";
// FASE E-8 (E8.1) — pilihan peran & daftar peran lintas-entitas TIDAK lagi ditulis
// di sini. Sumber tunggal: `config/roles.js` (cermin `backend/role_registry.py`),
// supaya peran baru muncul otomatis di formulir akun tanpa menyunting layar.
import { ROLE_OPTIONS as REG_ROLE_OPTIONS, CROSS_ENTITY_ROLES as REG_CROSS_ROLES }
  from "../../../config/roles";

/** Ubah galat axios menjadi kalimat manusia (mendukung detail berbentuk objek). */
export function errText(err, fallback = "Terjadi kesalahan.") {
  const d = err?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object") {
    const parts = [d.message || "", ...(d.blockers || []), d.hint || ""].filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }
  return err?.response?.data?.detail ? String(err.response.data.detail) : (err?.message || fallback);
}

/** Penghalang terstruktur (dipakai dialog arsip agar bisa ditampilkan sebagai daftar). */
export function errBlockers(err) {
  const d = err?.response?.data?.detail;
  if (d && typeof d === "object" && Array.isArray(d.blockers)) return d.blockers;
  return [];
}

// ─── Badan usaha ───────────────────────────────────────────────
export const listEntities = (params = {}) =>
  axios.get(`${API}/entities`, { params }).then((r) => r.data || []);

export const countEntities = (params = {}) =>
  axios.get(`${API}/entities/count`, { params }).then((r) => r.data?.count || 0);

export const getEntity = (id) =>
  axios.get(`${API}/entities/${id}`).then((r) => r.data || null);

export const createEntity = (body) =>
  axios.post(`${API}/entities`, body).then((r) => r.data);

export const patchEntity = (id, data) =>
  axios.patch(`${API}/entities/${id}`, { data }).then((r) => r.data);

export const getReadiness = (id) =>
  axios.get(`${API}/entities/${id}/readiness`).then((r) => r.data);

export const getDeactivationImpact = (id) =>
  axios.get(`${API}/entities/${id}/deactivation-impact`).then((r) => r.data);

export const archiveEntity = (id, { reason = "", force = false } = {}) =>
  axios.post(`${API}/entities/${id}/archive`, { reason, force }).then((r) => r.data);

export const reactivateEntity = (id) =>
  axios.post(`${API}/entities/${id}/reactivate`).then((r) => r.data);

export const getEntityAudit = (id) =>
  axios.get(`${API}/entities/${id}/audit`).then((r) => r.data || []);

// ─── Akun ────────────────────────────────────────────────────
export const listUsers = (params = {}) =>
  axios.get(`${API}/users`, { params }).then((r) => r.data);

export const createUser = (body) =>
  axios.post(`${API}/users`, body).then((r) => r.data);

export const patchUser = (id, data) =>
  axios.patch(`${API}/users/${id}`, { data }).then((r) => r.data);

export const deactivateUser = (id) =>
  axios.delete(`${API}/users/${id}`).then((r) => r.data);

export const reactivateUser = (id) =>
  axios.post(`${API}/users/${id}/reactivate`).then((r) => r.data);

export const resetUserPassword = (id, newPassword) =>
  axios.post(`${API}/users/${id}/reset-password`, { new_password: newPassword })
    .then((r) => r.data);

export const revokeUserSessions = (id) =>
  axios.post(`${API}/users/${id}/revoke-sessions`).then((r) => r.data);

export const availableEmployees = (params = {}) =>
  axios.get(`${API}/hr-employees-available`, { params }).then((r) => r.data || []);

// ─── Cek Kenyataan Peran (utang migrasi (ii) E-8) ───────────────────
// Laporan dihitung ulang di server setiap kali dibuka: peran usulan HARUS lahir
// dari jejak terbaru, bukan dari angka yang pernah disimpan.
export const roleReality = (params = {}) =>
  axios.get(`${API}/access/role-reality`, { params }).then((r) => r.data || {});

export const applyRoleReality = (id, role, note = "") =>
  axios.post(`${API}/access/role-reality/${id}/apply`, { role, note })
    .then((r) => r.data);

// ─── Enum jenis badan usaha (E1.1) ─────────────────────────────────
export const entityTypes = () =>
  axios.get(`${API}/enums/entity_type`).then((r) => r.data?.values || [])
    .catch(() => axios.get(`${API}/enums`)
      .then((r) => r.data?.enums?.entity_type?.values || []));

export const ROLE_OPTIONS = REG_ROLE_OPTIONS;

export const CROSS_ROLES = REG_CROSS_ROLES;
