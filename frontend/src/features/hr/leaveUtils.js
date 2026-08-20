// HRD H3 — util Cuti & Lembur bersama.
import { formatCurrency } from "../../utils/formatters";

export const LEAVE_TYPES = [
  { value: "cuti_tahunan", label: "Cuti Tahunan", deduct: true },
  { value: "cuti_besar", label: "Cuti Besar", deduct: true },
  { value: "izin", label: "Izin", deduct: false },
  { value: "sakit", label: "Sakit", deduct: false },
  { value: "unpaid", label: "Cuti Tanpa Gaji", deduct: false },
];
export const LEAVE_TYPE_LABEL = Object.fromEntries(LEAVE_TYPES.map((t) => [t.value, t.label]));

export const REQ_STATUS = {
  pending: { cls: "pill-warning", label: "Menunggu" },
  approved: { cls: "pill-success", label: "Disetujui" },
  rejected: { cls: "pill-danger", label: "Ditolak" },
  cancelled: { cls: "pill-muted", label: "Dibatalkan" },
};

const WIB_OFFSET_MS = 7 * 3600 * 1000;
export const wibToday = () => new Date(Date.now() + WIB_OFFSET_MS).toISOString().slice(0, 10);
export const curMonth = () => new Date(Date.now() + WIB_OFFSET_MS).toISOString().slice(0, 7);
export function recentMonths(n = 12) {
  const out = [];
  const d = new Date(Date.now() + WIB_OFFSET_MS);
  d.setDate(1);
  for (let i = 0; i < n; i++) { out.push(d.toISOString().slice(0, 7)); d.setMonth(d.getMonth() - 1); }
  return out;
}
export const rp = (v) => formatCurrency(v || 0);

// Hitung hari kerja (Senin–Jumat) dalam rentang inklusif — cermin logika backend (V1 tanpa libur).
export function countWorkdays(from, to) {
  if (!from) return 0;
  const d0 = new Date(`${from}T00:00:00Z`);
  const d1 = new Date(`${(to || from)}T00:00:00Z`);
  if (isNaN(d0) || isNaN(d1) || d1 < d0) return 0;
  let n = 0; const cur = new Date(d0);
  for (let i = 0; i < 367 && cur <= d1; i++) {
    const wd = cur.getUTCDay(); // 0=Min..6=Sab
    if (wd >= 1 && wd <= 5) n++;
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return n;
}

// Daftar sel kalender bulanan (Senin awal pekan). null = padding.
export function monthCells(month) {
  const [y, m] = (month || "").split("-").map(Number);
  if (!y || !m) return [];
  const totalDays = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const firstWd = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7; // Senin=0
  const cells = [];
  for (let i = 0; i < firstWd; i++) cells.push(null);
  for (let d = 1; d <= totalDays; d++) cells.push(`${month}-${String(d).padStart(2, "0")}`);
  return cells;
}
