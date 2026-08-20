/**
 * FASE G-6 — Kamus tampilan **TRANSAKSI ANTAR ENTITAS**.
 *
 * Hanya label/warna/format + "langkah berikutnya yang wajar". Sumber kebenaran
 * siklus, mode harga & PPN, metode settlement tetap di backend
 * (`GET /api/interco/meta`) supaya layar tidak pernah menawarkan langkah yang
 * tidak punya mesinnya.
 */

/** Warna pil status — konsisten dengan pil status kontrabon G-7. */
export const STATUS_CLASS = {
  draft: "bg-[#F2F2F5] text-[#5A5A60]",
  confirmed: "bg-[#EAF2FF] text-[#0058CC]",
  shipped: "bg-[#FFF4E5] text-[#B26A00]",
  received: "bg-[#EDE7FB] text-[#6B219A]",
  invoiced: "bg-[#E6F7F1] text-[#0F6B52]",
  settled: "bg-[#E8F6EE] text-[#1B7F4B]",
  disputed: "bg-[#FDE2E2] text-[#9B1C1C]",
  cancelled: "bg-[#F2F2F5] text-[#8E8E93]",
};

export const STATUS_LABEL = {
  draft: "Draf",
  confirmed: "Dikonfirmasi",
  shipped: "Dikirim",
  received: "Diterima",
  invoiced: "Difakturkan",
  settled: "Lunas",
  disputed: "Sengketa",
  cancelled: "Dibatalkan",
};

export const STATUS_FILTERS = [
  { value: "", label: "Semua status" },
  { value: "draft", label: "Draf" },
  { value: "confirmed", label: "Dikonfirmasi" },
  { value: "shipped", label: "Dikirim" },
  { value: "received", label: "Diterima" },
  { value: "invoiced", label: "Difakturkan" },
  { value: "settled", label: "Lunas" },
  { value: "cancelled", label: "Dibatalkan" },
];

export const ROLE_FILTERS = [
  { value: "", label: "Semua peran" },
  { value: "seller", label: "Sebagai Penjual" },
  { value: "buyer", label: "Sebagai Pembeli" },
];

export const PRICING_MODES = [
  { value: "fixed_price", label: "Harga tetap dari kontrak internal" },
  { value: "at_cost", label: "Sesuai HPP penjual" },
  { value: "cost_plus_pct", label: "HPP + persen margin" },
];

export const PPN_MODES = [
  { value: "ikut_pkp", label: "Ikut status PKP penjual" },
  { value: "tanpa_ppn", label: "Tanpa PPN" },
  { value: "dengan_ppn", label: "Dengan PPN (paksa)" },
];

export const SETTLEMENT_METHODS = [
  { value: "netting", label: "Netting (saling hapus, tanpa uang)" },
  { value: "transfer", label: "Transfer bank" },
  { value: "cash", label: "Kas" },
];

/** Nama akun singkat untuk blok jurnal (bahasa layar, bukan kode saja). */
export const ACC_LABEL = {
  "1-1250": "Piutang Antar-PT (IC-AR)",
  "2-1250": "Utang Antar-PT (IC-AP)",
  "1-1300": "Persediaan Barang",
  "1-1310": "Persediaan Dalam Perjalanan",
  "1-1500": "PPN Masukan",
  "2-1200": "PPN Keluaran",
  "4-1000": "Pendapatan",
  "5-1000": "HPP",
  "1-1100": "Kas / Bank",
};

export function fmtDate(s) {
  if (!s) return "-";
  try {
    return new Date(s).toLocaleDateString("id-ID", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch { return s; }
}

/**
 * Langkah berikutnya yang wajar untuk sebuah transaksi.
 *
 * PENTING (US8): status "Diterima" TIDAK bisa ditekan manual — persediaan pembeli
 * hanya boleh naik ketika barangnya benar-benar berpindah. Karena itu langkah
 * sesudah konfirmasi adalah **menerbitkan tugas gudang**; gudang yang menyetujui
 * perpindahan, dan status + jurnal penerimaan tercatat otomatis dari sana.
 */
export function nextStep(doc, role = "seller") {
  if (!doc) return null;
  const s = doc.status;
  const hasTask = Boolean(doc.warehouse_transfer_id);
  const taskDone = doc.warehouse_transfer_status === "completed";
  if (s === "draft") return { action: "confirm", label: "Konfirmasi" };
  if ((s === "confirmed" || s === "shipped") && !hasTask) {
    return {
      action: "warehouse-task",
      label: "Buat Tugas Gudang",
      hint: "Barang berpindah lewat gudang — jurnal penerimaan mengikuti barangnya.",
    };
  }
  if ((s === "confirmed" || s === "shipped") && hasTask && !taskDone) {
    return {
      action: null,
      label: "Menunggu gudang menyetujui",
      disabled: true,
      hint: "Tugas gudang sudah terbit; persetujuan gudang yang memindahkan barang.",
    };
  }
  if (s === "received" && role !== "buyer") {
    return { action: "invoice", label: "Terbitkan Faktur Internal" };
  }
  return null;
}

/** Boleh dibatalkan? (setelah dikirim → harus lewat retur, bukan pembatalan) */
export function canCancel(doc) {
  if (!doc) return false;
  if (doc.warehouse_transfer_status === "completed") return false;
  return ["draft", "confirmed"].includes(doc.status);
}

/** FASE G-6b — status dokumen RETUR antar-PT (dokumen kembar nota retur ↔ nota kredit). */
export const RETURN_STATUS_LABEL = {
  draft: "Draf",
  approved: "Disetujui",
  completed: "Barang Sudah Kembali",
  cancelled: "Dibatalkan",
};

export const RETURN_STATUS_CLASS = {
  draft: "bg-[#F2F2F5] text-[#5A5A60]",
  approved: "bg-[#EAF2FF] text-[#0058CC]",
  completed: "bg-[#E8F6EE] text-[#1B7F4B]",
  cancelled: "bg-[#F2F2F5] text-[#8E8E93]",
};

export const RETURN_STATUS_FILTERS = [
  { value: "", label: "Semua status retur" },
  { value: "draft", label: "Draf" },
  { value: "approved", label: "Disetujui" },
  { value: "completed", label: "Barang Sudah Kembali" },
  { value: "cancelled", label: "Dibatalkan" },
];

/** FASE G-6b — apakah baris ini boleh menerbitkan / melihat faktur pajak internal? */
export function taxState(doc) {
  if (!doc) return { show: false };
  const eligible = ["invoiced", "settled", "returned"].includes(doc.status);
  if (!doc.tax_apply) return { show: false, reason: "transaksi tanpa PPN" };
  return {
    show: eligible || Boolean(doc.tax_faktur_out_number),
    issued: Boolean(doc.tax_faktur_out_number),
    number: doc.tax_faktur_out_number || "",
    needsReplacement: doc.tax_faktur_status === "needs_replacement",
    label: doc.tax_faktur_out_number ? "Faktur Pajak" : "Terbitkan Faktur Pajak",
  };
}

/**
 * FASE G-6b — retur hanya sah SESUDAH barangnya berpindah. Sebelum itu jalannya
 * adalah "Batalkan" (jurnalnya dibalik) — dua jalan yang tidak boleh tertukar.
 */
export function canReturn(doc) {
  if (!doc) return false;
  if (doc.warehouse_transfer_status !== "completed") return false;
  return ["received", "invoiced", "settled", "returned"].includes(doc.status);
}
