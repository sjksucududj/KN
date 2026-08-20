/**
 * designerMeta (PS-18) — kosakata & warna **KPI Desainer** di satu tempat.
 *
 * Semua istilah dibuat awam: yang dibaca pemilik usaha adalah "tepat waktu",
 * "diulang", "terlambat" — bukan "on-time ratio" atau "rework rate".
 */

/** Pilihan periode (fallback bila backend belum mengirim `period_options`). */
export const PERIOD_OPTIONS = [
  { value: "month", label: "Bulan ini" },
  { value: "30d", label: "30 hari terakhir" },
  { value: "90d", label: "90 hari terakhir" },
  { value: "all", label: "Semua waktu" },
];

/** Warna & arti huruf grade — memakai palet yang sudah dipakai layar R&D. */
export const GRADE_META = {
  A: { cls: "pill-success", tone: "#1B7F4B", label: "A" },
  B: { cls: "pill-info", tone: "#0058CC", label: "B" },
  C: { cls: "pill-warning", tone: "#B26A00", label: "C" },
  D: { cls: "pill-danger", tone: "#C0392B", label: "D" },
  "—": { cls: "pill-muted", tone: "#8E8E93", label: "—" },
};

export const gradeMeta = (letter) => GRADE_META[letter] || GRADE_META["—"];

/** Warna angka persentase: makin tinggi makin baik (on-time, ACC). */
export function goodPctTone(value) {
  if (value === null || value === undefined) return "#8E8E93";
  if (value >= 90) return "#1B7F4B";
  if (value >= 70) return "#0058CC";
  if (value >= 50) return "#B26A00";
  return "#C0392B";
}

/** Warna angka persentase: makin tinggi makin BURUK (rework). */
export function badPctTone(value) {
  if (value === null || value === undefined) return "#8E8E93";
  if (value <= 10) return "#1B7F4B";
  if (value <= 30) return "#0058CC";
  if (value <= 50) return "#B26A00";
  return "#C0392B";
}

/** Tampilkan angka atau tanda "belum ada data" — jangan pernah 0 palsu. */
export const num = (v, suffix = "") =>
  v === null || v === undefined ? "—" : `${v}${suffix}`;

/** Kalimat penjelas cara nilai dihitung (dibaca pemilik, bukan developer). */
export function gradeFormula(w) {
  if (!w) return "";
  return (
    `Nilai = tepat waktu ${w.on_time}% + skor penilaian ${w.score}% + ` +
    `sekali-jadi (ACC) ${w.acc}%, lalu dikurangi penalti pengulangan ` +
    `(${w.penalty_rework}× persen diulang) dan penalti keterlambatan ` +
    `(${w.penalty_overdue}× persen terlambat).`
  );
}

/** Label tingkat eskalasi untuk papan SLA. */
export const TIER_META = {
  manager: { label: "Manajer", cls: "pill-warning" },
  admin: { label: "Manajer + Admin", cls: "pill-danger" },
};
export const tierMeta = (tier) => TIER_META[tier] || TIER_META.manager;
