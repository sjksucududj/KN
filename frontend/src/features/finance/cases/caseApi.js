/**
 * FASE G-9 — Kamus tampilan **Pusat Kasus Keuangan**.
 *
 * Hanya label/warna/format. Sumber kebenaran playbook & aksi tetap di backend
 * (`GET /api/finance-cases/playbooks`) supaya layar tidak pernah menawarkan langkah
 * yang tidak ada mesinnya.
 */
export const STATUS_LABEL = {
  open: "Baru",
  in_progress: "Sedang ditangani",
  resolved: "Selesai",
  rejected: "Ditutup tanpa tindakan",
};

export const STATUS_CLASS = {
  open: "bg-[#FFF4E5] text-[#B26A00]",
  in_progress: "bg-[#EAF2FF] text-[#0058CC]",
  resolved: "bg-[#E8F6EE] text-[#1B7F4B]",
  rejected: "bg-[#F2F2F5] text-[#6B6B73]",
};

export const STATUS_FILTERS = [
  { value: "", label: "Semua status" },
  { value: "open", label: "Baru" },
  { value: "in_progress", label: "Sedang ditangani" },
  { value: "resolved", label: "Selesai" },
  { value: "rejected", label: "Ditutup tanpa tindakan" },
];

export const DOC_KIND_LABEL = {
  journal_entry: "Jurnal",
  cash_transaction: "Transaksi kas",
  order_payment: "Pelunasan pesanan",
  ar_receipt: "Kwitansi",
  penalty: "Nota denda",
  store_credit_entry: "Buku saldo kredit",
  supplier_advance: "Uang muka supplier",
};

export const SOURCE_LABEL = {
  bank_holding: "Titipan dana (Rekonsiliasi Bank)",
  bank_line: "Mutasi bank",
  ar_receipt: "Kwitansi pelanggan",
  vendor_bill: "Tagihan supplier",
  manual: "Dilaporkan manual",
};

export const EVENT_LABEL = {
  dibuka: "Kasus dibuka",
  ditugaskan: "Ditugaskan",
  catatan: "Catatan / bukti",
  langkah: "Langkah dijalankan",
  selesai: "Diselesaikan",
  ditolak: "Ditutup tanpa tindakan",
  dibuka_ulang: "Dibuka kembali",
  eskalasi: "Eskalasi",
};

export function fmtDateTime(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString("id-ID", {
      day: "2-digit", month: "short", year: "2-digit",
      hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta",
    }) + " WIB";
  } catch { return String(s); }
}

/** Umur/sisa waktu dalam kalimat manusia (bukan angka jam telanjang). */
export function humanAge(hours) {
  const h = Number(hours || 0);
  if (h < 1) return "baru saja";
  if (h < 24) return `${Math.round(h)} jam`;
  const d = Math.floor(h / 24);
  const rest = Math.round(h % 24);
  return rest ? `${d} hari ${rest} jam` : `${d} hari`;
}

export function slaText(c) {
  if (c.status === "resolved" || c.status === "rejected") return "—";
  if (c.overdue) return `Terlambat · umur ${humanAge(c.age_hours)}`;
  const left = Math.max(0, Number(c.sla_hours || 0) - Number(c.age_hours || 0));
  return `Sisa ${humanAge(left)}`;
}
