// HRD H2 — util bersama untuk Live Tracking + Kunjungan (Visits).
// Mengikuti konvensi nyata FE (KODE MENANG). Lihat memory/PLAN_HRD.md §H2.
import { BACKEND_URL } from "../../services/apiClient";

export const WIB_OFFSET_MS = 7 * 3600 * 1000;
export const todayStr = () => new Date(Date.now() + WIB_OFFSET_MS).toISOString().slice(0, 10);
export const monthStr = () => new Date(Date.now() + WIB_OFFSET_MS).toISOString().slice(0, 7);

export const fmtTime = (iso) => (iso && iso.length >= 16 ? iso.slice(11, 16) : "\u2014");
export const fmtDate = (iso) => (iso && iso.length >= 10 ? iso.slice(0, 10) : "\u2014");
export const fmtMin = (m) => {
  m = Number(m) || 0;
  if (m <= 0) return "\u2014";
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}j ${m % 60 ? `${m % 60}m` : ""}`.trim();
};

// "2 mnt lalu" — untuk last-seen posisi GPS.
export function timeAgo(iso) {
  if (!iso) return "\u2014";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "\u2014";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return `${sec} dtk lalu`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} mnt lalu`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} jam lalu`;
  return `${Math.floor(hr / 24)} hari lalu`;
}

// Durasi berjalan (untuk kunjungan ongoing) dari ts check-in.
export function elapsedMin(iso) {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return 0;
  return Math.max(0, Math.floor((Date.now() - t) / 60000));
}

export const VISIT_STATUS_PILL = {
  ongoing: { cls: "pill-warning", label: "Berjalan" },
  done: { cls: "pill-success", label: "Selesai" },
};

export const OUTCOME_PILL = {
  order: { cls: "pill-success", label: "Pesanan" },
  followup: { cls: "pill-info", label: "Follow-up" },
  no_order: { cls: "pill-danger", label: "Tanpa Pesanan" },
  other: { cls: "pill-muted", label: "Lainnya" },
  "": { cls: "pill-muted", label: "\u2014" },
};

export const OUTCOME_OPTS = [
  { value: "order", label: "Pesanan / Penutupan" },
  { value: "followup", label: "Follow-up" },
  { value: "no_order", label: "Tanpa Pesanan" },
  { value: "other", label: "Lainnya" },
];

// URL WebSocket realtime tracking (wss lewat ingress publik). Mode subscribe = manager Live Map.
// Fallback polling /hr/field-tracks/latest tetap ada di view (anti-blank bila WS gagal).
export function wsTrackUrl(token, mode = "subscribe") {
  const base = (BACKEND_URL || "").replace(/^http/i, "ws");
  return `${base}/api/ws/track?mode=${mode}&token=${encodeURIComponent(token || "")}`;
}

// Upsert posisi terkini per karyawan ke array (dipakai poll + WS).
export const ONLINE_WINDOW_SEC = 600; // <10 menit = online (samakan dengan backend)
export function isFreshTs(iso) {
  if (!iso) return false;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return false;
  return (Date.now() - t) / 1000 <= ONLINE_WINDOW_SEC;
}

export function upsertPosition(list, pos) {
  if (!pos || !pos.employee_id) return list;
  const withOnline = { ...pos, online: isFreshTs(pos.ts) };
  const next = list.filter((p) => p.employee_id !== pos.employee_id);
  next.push(withOnline);
  next.sort((a, b) => (Number(b.online) - Number(a.online)) || String(a.employee_name).localeCompare(String(b.employee_name)));
  return next;
}
