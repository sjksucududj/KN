/**
 * configApi.js — FASE G-0 · klien API Pusat Pengaturan.
 *
 * Satu tempat untuk semua panggilan konfigurasi supaya komponen UI tetap tipis
 * dan tidak ada URL yang tersebar (aturan repo: satu jalur, bukan ad-hoc).
 */
import axios, { API } from "../../../services/apiClient";

const BASE = `${API}/config`;

export const configApi = {
  /** Katalog setting + grup (sumber tampilan UI generik). */
  registry: (params = {}) => axios.get(`${BASE}/registry`, { params }).then((r) => r.data),

  /** Nilai efektif untuk satu grup / hasil pencarian, mengikuti konteks scope. */
  effective: (params = {}) => axios.get(`${BASE}/effective`, { params }).then((r) => r.data),

  /** Jejak "kenapa nilainya begini?" untuk satu setting. */
  explain: (params = {}) => axios.get(`${BASE}/explain`, { params }).then((r) => r.data),

  /** "Coba dulu" — jalankan aturan tanpa menyimpan. */
  simulate: (body) => axios.post(`${BASE}/simulate`, body).then((r) => r.data),

  /** Simpan satu/beberapa perubahan (append-only + langsung aktif di mesin). */
  save: (items) => axios.put(`${BASE}/values`, { items }).then((r) => r.data),

  /** Kembalikan satu setting ke default sistem. */
  reset: (body) => axios.post(`${BASE}/values/reset`, body).then((r) => r.data),

  /** FASE E-4 (E4.6) — cabut nilai pada satu lapisan → kembali mewarisi lapisan di atasnya. */
  clear: (body) => axios.post(`${BASE}/values/clear`, body).then((r) => r.data),

  /** Riwayat perubahan (siapa, kapan, dari→ke, alasan). */
  history: (params = {}) => axios.get(`${BASE}/history`, { params }).then((r) => r.data),

  /** Kesehatan wiring: apakah setiap setting benar-benar tersambung ke kode. */
  health: () => axios.get(`${BASE}/health`).then((r) => r.data),

  /** DAFTAR DAMPAK — dokumen terbuka mana yang terpengaruh koreksi harga master. */
  impactPreview: (body) => axios.post(`${BASE}/impact-preview`, body).then((r) => r.data),

  /** Terapkan koreksi harga HANYA ke dokumen yang dicentang. */
  impactApply: (body) => axios.post(`${BASE}/impact-apply`, body).then((r) => r.data),
};

/** Pesan error yang enak dibaca user (bukan stack trace). */
export const errMsg = (e, fallback = "Terjadi kesalahan.") =>
  e?.response?.data?.detail || e?.message || fallback;

/** Angka gaya Indonesia (titik ribuan, koma desimal). */
export function idNum(v, maxDec = 2) {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString("id-ID", { maximumFractionDigits: maxDec });
}

/** Format nilai config menjadi teks yang dimengerti awam. */
export function formatValue(entry, value) {
  if (value === null || value === undefined || value === "") return "—";
  switch (entry.type) {
    case "bool":
      return value ? "Ya / Aktif" : "Tidak / Mati";
    case "pct":
      return `${idNum(value)}${entry.unit ? ` ${entry.unit}` : " %"}`;
    case "money":
      return `Rp ${idNum(value, 0)}`;
    case "int":
    case "duration":
    case "decimal":
      return `${idNum(value)}${entry.unit ? ` ${entry.unit}` : ""}`;
    case "enum": {
      const opt = (entry.options || []).find((o) => o.value === value);
      return opt ? opt.label : String(value);
    }
    case "list":
      return Array.isArray(value) ? value.join(" · ") : String(value);
    case "table":
      return Array.isArray(value)
        ? `${value.length} baris`
        : `${Object.keys(value || {}).length} entri`;
    default:
      return String(value);
  }
}

export const RISK_LABEL = { low: "Risiko rendah", medium: "Risiko sedang", high: "Risiko tinggi" };

/**
 * Ringkas nilai apa pun menjadi teks aman untuk JSX.
 *
 * Kenapa perlu: sebagian setting bertipe `table`/`list` bernilai objek/array.
 * `String(obj)` menghasilkan "[object Object]", dan merender objek langsung ke
 * JSX memicu React error #31 ("Objects are not valid as a React child") — hal
 * ini benar-benar terjadi pada `scheduled_applied` di layar Kesehatan Konfigurasi.
 */
export function shortVal(v, max = 60) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Ya" : "Tidak";
  if (typeof v === "object") {
    const s = Array.isArray(v) ? v.join(" · ") : JSON.stringify(v);
    return s.length > max ? `${s.slice(0, max)}…` : s;
  }
  return String(v);
}

export const LAYER_TONE = {
  code_default: "muted", legacy_global: "blue", global: "blue",
  legacy_entity: "purple", entity: "purple", supplier: "teal",
  customer: "teal", product: "orange", document: "orange", hypothetical: "orange",
};

export const WIRING_TONE = { OK: "green", STALE: "orange", MISSING: "red", NOT_USED: "muted" };
export const WIRING_LABEL = {
  OK: "Aktif & tersambung", STALE: "Referensi kode basi",
  MISSING: "Referensi kode salah", NOT_USED: "Tidak dipakai",
};
export const VERDICT_TONE = { ok: "green", warn: "orange", block: "red" };
export const SCOPE_LABEL = {
  global: "Semua entitas (Global)", entity: "Entitas ini",
  customer: "Pelanggan tertentu", supplier: "Supplier tertentu",
  product: "Produk tertentu", document: "Dokumen tertentu",
};
