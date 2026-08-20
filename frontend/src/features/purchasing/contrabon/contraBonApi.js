/**
 * FASE G-7 — Kamus tampilan **KONTRABON** (siklus tukar faktur supplier).
 *
 * Hanya label/warna/format. Sumber kebenaran siklus, jenis potongan, tindakan
 * selisih, dan label alasan tetap di backend (`GET /api/contra-bons/meta`) supaya
 * layar tidak pernah menawarkan langkah yang tidak punya mesinnya.
 */

/** Warna pil status — mengikuti bahasa visual pil status modul lain. */
export const STATUS_CLASS = {
  draft: "bg-[#F2F2F5] text-[#5A5A60]",
  submitted: "bg-[#FFF4E5] text-[#B26A00]",
  verified: "bg-[#EAF2FF] text-[#0058CC]",
  approved: "bg-[#EDE7FB] text-[#6B219A]",
  scheduled_payment: "bg-[#E6F7F1] text-[#0F6B52]",
  paid: "bg-[#E8F6EE] text-[#1B7F4B]",
  disputed: "bg-[#FDE2E2] text-[#9B1C1C]",
  cancelled: "bg-[#F2F2F5] text-[#8E8E93]",
};

export const STATUS_FILTERS = [
  { value: "", label: "Semua status" },
  { value: "draft", label: "Draf" },
  { value: "submitted", label: "Diajukan" },
  { value: "verified", label: "Terverifikasi" },
  { value: "approved", label: "Disetujui" },
  { value: "scheduled_payment", label: "Dijadwalkan bayar" },
  { value: "paid", label: "Sudah dibayar" },
  { value: "disputed", label: "Sengketa" },
  { value: "cancelled", label: "Dibatalkan" },
];

export const METHOD_OPTIONS = [
  { value: "transfer", label: "Transfer bank" },
  { value: "giro", label: "Giro / cek" },
  { value: "cash", label: "Tunai" },
];

export const CASH_TYPE_OPTIONS = [
  { value: "kas_besar", label: "Kas Besar" },
  { value: "kas_kecil", label: "Kas Kecil" },
];

/** Jenis selisih 3-way — kalimat singkat untuk kepala baris pengecualian. */
export const EXCEPTION_TYPE_LABEL = {
  qty_over_billed: "Ditagih lebih banyak dari yang diterima",
  price_variance: "Harga faktur berbeda dari harga PO",
};

/** Peristiwa jejak waktu → kalimat manusia. */
export const EVENT_LABEL = {
  dibuat: "Kontrabon dibuat",
  diajukan: "Diajukan untuk verifikasi",
  diverifikasi: "3-way match diverifikasi",
  disetujui: "Disetujui",
  dijadwalkan: "Pembayaran dijadwalkan",
  dibayar: "Pembayaran dicatat",
  potongan: "Potongan ditambah",
  potongan_hapus: "Potongan dihapus",
  keputusan: "Keputusan selisih",
  sengketa: "Disengketakan",
  dibatalkan: "Dibatalkan",
};

export function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(String(s).length <= 10 ? `${s}T00:00:00` : s)
      .toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return String(s); }
}

export function fmtDateTime(s) {
  if (!s) return "—";
  try {
    return `${new Date(s).toLocaleString("id-ID", {
      day: "2-digit", month: "short", year: "2-digit",
      hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta",
    })} WIB`;
  } catch { return String(s); }
}

/** Tanggal hari ini dalam bentuk `YYYY-MM-DD` (zona lokal pengguna). */
export function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Umur/sisa hari dalam kalimat manusia, bukan angka telanjang. */
export function humanDays(days) {
  const n = Number(days || 0);
  if (n <= 0) return "hari ini";
  if (n === 1) return "1 hari";
  return `${Math.round(n)} hari`;
}

/** Kalimat SLA verifikasi untuk satu kontrabon. */
export function slaText(cb) {
  const sla = cb?.sla || {};
  if (!sla.sla_days) return "—";
  if (["paid", "cancelled"].includes(cb.status)) return "selesai";
  if (sla.overdue) return `Terlambat · menunggu ${humanDays(sla.age_days)}`;
  const left = Math.max(0, Number(sla.sla_days || 0) - Number(sla.age_days || 0));
  return `Sisa ${humanDays(left)}`;
}

/**
 * Langkah BERIKUTNYA yang wajar untuk satu kontrabon — dipakai tombol utama
 * panel detail supaya petugas tidak perlu menghafal urutan siklus.
 * `null` bila memang tidak ada langkah lanjutan (lunas / dibatalkan).
 */
export function nextStep(cb) {
  switch (cb?.status) {
    case "draft": return { action: "submit", label: "Ajukan ke verifikasi" };
    case "submitted": return { action: "verify", label: "Verifikasi 3-way match" };
    case "verified": return { action: "approve", label: "Setujui kontrabon" };
    case "approved": return { action: "schedule", label: "Jadwalkan pembayaran" };
    case "scheduled_payment": return { action: "pay", label: "Catat pembayaran" };
    case "disputed": return { action: "submit", label: "Ajukan ulang setelah koreksi" };
    default: return null;
  }
}

/** Daftar pengecualian 3-way yang BELUM diputus (dipakai badge & modal keputusan). */
export function pendingExceptions(cb) {
  const decided = new Set((cb?.decisions || []).map((d) => d.exception_key));
  const out = [];
  (cb?.bills || []).forEach((b) => {
    ((b.match || {}).exceptions || []).forEach((e) => {
      if (!decided.has(e.key)) out.push(e);
    });
  });
  return out;
}
