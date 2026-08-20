// HRD H5 — helper KPI (murni). Bulan terakhir + warna skor + rekap tertimbang.
export function lastMonths(n = 12) {
  const out = [];
  const d = new Date();
  for (let i = 0; i < n; i++) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    out.push(`${y}-${m}`);
    d.setMonth(d.getMonth() - 1);
  }
  return out;
}

export function curMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// Kelas warna teks berdasar skor (0–150).
export function scoreCls(s) {
  const v = Number(s) || 0;
  if (v >= 100) return "text-[#1F7A45]"; // hijau — tercapai
  if (v >= 80) return "text-[#0058CC]";  // biru — baik
  if (v >= 60) return "text-[#B7791F]";  // kuning — cukup
  return "text-[#C0341D]";               // merah — kurang
}

export function scoreBadge(s) {
  const v = Number(s) || 0;
  if (v >= 100) return { cls: "bg-[#E7F5EC] text-[#1F7A45]", label: "Tercapai" };
  if (v >= 80) return { cls: "bg-[#E7F0FF] text-[#0058CC]", label: "Baik" };
  if (v >= 60) return { cls: "bg-[#FBF3E2] text-[#B7791F]", label: "Cukup" };
  return { cls: "bg-[#FBEAE7] text-[#C0341D]", label: "Kurang" };
}

// Rekap rata-rata skor tertimbang dari array baris KPI.
export function weightedAvg(rows) {
  if (!rows || rows.length === 0) return 0;
  const tw = rows.reduce((a, r) => a + (Number(r.weight) || 1), 0) || 1;
  const s = rows.reduce((a, r) => a + (Number(r.score) || 0) * (Number(r.weight) || 1), 0);
  return Math.round((s / tw) * 10) / 10;
}
