/**
 * workDeskApi.js — FASE E-8 (E8.7/E8.13/E8.15/E8.20) · **MEJA KERJA** (Admin Sales & Finance).
 *
 * SATU tempat untuk panggilan API kedua meja + kamus tampilannya. Alasannya bukan
 * kerapian: dua meja membicarakan ANTREAN yang sama-sama berisi "pesanan", "retur",
 * "jatuh tempo". Kalau tiap layar menyalin label & warnanya sendiri, satu keadaan
 * (`pending_approval`) berakhir dengan dua kata berbeda di dua layar — dan pengguna
 * menyimpulkan ada dua hal berbeda.
 *
 * Pembagian meja mengikuti keputusan pemilik E8.10b#2: faktur pajak & uang masuk
 * ada di **Meja Finance**, alur pesanan & pemenuhan di **Meja Admin Sales**.
 */
import axios, { API } from "../../services/apiClient";
import {
  AlertTriangle, ArrowLeftRight, BadgeCheck, CalendarClock, CheckCircle2,
  ClipboardCheck, FileSignature, PackageSearch, Printer, RotateCcw, Scale,
  ShieldQuestion, Wallet,
} from "lucide-react";

// ─── PANGGILAN API ──────────────────────────────────────────────────────────
export const salesAdminDesk = (params = {}) =>
  axios.get(`${API}/sales-admin/desk`, { params }).then((r) => r.data);

export const financeDesk = (params = {}) =>
  axios.get(`${API}/finance/desk`, { params }).then((r) => r.data);

/** Daftar periksa kelengkapan (read-only) — dibaca SEBELUM menekan Verifikasi. */
export const verificationPreview = (orderId) =>
  axios.get(`${API}/sales-orders/${orderId}/verification`).then((r) => r.data);

export const verifyOrder = (orderId, note = "") =>
  axios.post(`${API}/sales-orders/${orderId}/verify`, { note }).then((r) => r.data);

export const confirmOrder = (orderId) =>
  axios.post(`${API}/sales-orders/${orderId}/confirm`).then((r) => r.data);

export const fulfillmentOptions = (orderId) =>
  axios.get(`${API}/sales-admin/orders/${orderId}/fulfillment`).then((r) => r.data);

export const fulfillmentDecision = (orderId, payload) =>
  axios.post(`${API}/sales-admin/orders/${orderId}/fulfillment-decision`, payload)
    .then((r) => r.data);

/** US12 — perjalanan pesanan (read-only, tanpa akses layar gudang). */
export const orderJourney = (orderId) =>
  axios.get(`${API}/sales-orders/${orderId}/journey`).then((r) => r.data);

export const issueTaxInvoice = (orderId) =>
  axios.post(`${API}/sales-orders/${orderId}/tax-invoice`, {}).then((r) => r.data);

/** E8.3 — riwayat kunjungan MILIK SENDIRI + KPI ringkasnya (tanpa izin HR). */
export const myVisitsHistory = (month = "") =>
  axios.get(`${API}/hr/visits/mine`, { params: month ? { month } : {} }).then((r) => r.data);

// ─── KAMUS TAMPILAN ANTREAN ─────────────────────────────────────────────────
// `tone` dipakai untuk ikon & angka; `bg` untuk latar lencana ikon.
export const QUEUE_META = {
  perlu_verifikasi:    { icon: ClipboardCheck, tone: "#8A5300", bg: "rgba(255,149,0,.16)" },
  siap_dikonfirmasi:   { icon: CheckCircle2,   tone: "#1B7F4B", bg: "rgba(52,199,89,.16)" },
  menunggu_manajer:    { icon: ShieldQuestion, tone: "#6B219A", bg: "rgba(107,33,154,.12)" },
  siap_cetak_dokumen:  { icon: Printer,        tone: "#0058CC", bg: "rgba(0,122,255,.12)" },
  perlu_dipenuhi:      { icon: PackageSearch,  tone: "#B23B14", bg: "rgba(255,89,48,.14)" },
  jatuh_tempo:         { icon: CalendarClock,  tone: "#C0392B", bg: "rgba(255,59,48,.14)" },
  retur:               { icon: RotateCcw,      tone: "#8A5300", bg: "rgba(255,149,0,.16)" },
  permintaan_internal: { icon: ArrowLeftRight, tone: "#0058CC", bg: "rgba(0,122,255,.12)" },
  siap_faktur_pajak:   { icon: FileSignature,  tone: "#6B219A", bg: "rgba(107,33,154,.12)" },
  uang_masuk:          { icon: Wallet,         tone: "#1B7F4B", bg: "rgba(52,199,89,.16)" },
  selisih_bayar:       { icon: Scale,          tone: "#8A5300", bg: "rgba(255,149,0,.16)" },
  denda_draft:         { icon: AlertTriangle,  tone: "#C0392B", bg: "rgba(255,59,48,.14)" },
};

export const DEFAULT_QUEUE_META = {
  icon: BadgeCheck, tone: "#0058CC", bg: "rgba(0,122,255,.12)",
};

export const queueMeta = (id) => QUEUE_META[id] || DEFAULT_QUEUE_META;

// ─── LENCANA BARIS ──────────────────────────────────────────────────────────
// Kunci = status/penanda MENTAH dari server (huruf kecil). Nilai = kata yang
// dibaca pengguna. Tanpa kamus ini layar menuliskan `partially_shipped` mentah.
const BADGE_LABEL = {
  draft: "Draf",
  reserved: "Dipesan",
  waiting_approval: "Menunggu persetujuan",
  waiting_stock: "Menunggu stok",
  approved: "Disetujui",
  confirmed: "Dikonfirmasi",
  partially_picked: "Sebagian diambil",
  picked: "Sudah diambil",
  partially_shipped: "Sebagian dikirim",
  shipped: "Dikirim",
  dispatched: "Dikirim",
  done: "Selesai",
  cancelled: "Dibatalkan",
  menunggu: "Menunggu manajer",
  covered: "Barang masuk menutup",
  partial: "Tertutup sebagian",
  uncovered: "Belum ada penutup",
  lewat: "Lewat tempo",
  segera: "Segera jatuh tempo",
  pending_approval: "Menunggu persetujuan",
  pending_process: "Menunggu diproses",
  quarantine: "Karantina",
  submitted: "Diajukan",
  open: "Terbuka",
  pending: "Menunggu",
};

const BADGE_TONE = {
  danger: "border-[#F5C9BC] bg-[#FDEDE7] text-[#C0392B]",
  warn: "border-[#F5D9A8] bg-[#FFF4E5] text-[#8A5300]",
  ok: "border-[#BFE6CE] bg-[#E6F6EC] text-[#1B7F4B]",
  info: "border-[#CBDFFF] bg-[#EAF2FF] text-[#0058CC]",
  mute: "border-[#E2E2E7] bg-[#F2F2F5] text-[#6E6E73]",
};

const BADGE_GROUP = {
  danger: ["lewat", "uncovered", "cancelled", "quarantine"],
  warn: ["segera", "partial", "menunggu", "waiting_approval", "waiting_stock",
         "pending_approval", "pending_process", "pending", "draft"],
  ok: ["approved", "confirmed", "picked", "shipped", "dispatched", "done", "covered"],
  info: ["reserved", "submitted", "open", "partially_picked", "partially_shipped"],
};

/** Kata Indonesia untuk penanda baris; tak dikenal → dirapikan, tidak dibuang. */
export function badgeLabel(badge) {
  if (!badge) return "";
  const key = String(badge).toLowerCase();
  return BADGE_LABEL[key] || String(badge).replace(/_/g, " ");
}

export function badgeClass(badge) {
  const key = String(badge || "").toLowerCase();
  const group = Object.keys(BADGE_GROUP).find((g) => BADGE_GROUP[g].includes(key));
  return BADGE_TONE[group || "mute"];
}

// ─── ISYARAT UMUR (SLA) ─────────────────────────────────────────────────────
// US15 menuntut "umur tertua" terbaca. Angka telanjang tidak menjelaskan apa pun —
// yang menolong adalah WARNA yang memberi tahu kapan sebuah baris mulai basi.
export function ageTone(days) {
  const d = Number(days || 0);
  if (d >= 7) return { cls: BADGE_TONE.danger, label: `${d} hari` };
  if (d >= 3) return { cls: BADGE_TONE.warn, label: `${d} hari` };
  if (d >= 1) return { cls: BADGE_TONE.info, label: `${d} hari` };
  return { cls: BADGE_TONE.mute, label: "hari ini" };
}

// ─── TUJUAN NAVIGASI SATU BARIS ─────────────────────────────────────────────
// Meja kerja bukan tempat mengerjakan SEGALA hal; ia tempat MENEMUKAN pekerjaan
// lalu melompat ke layar yang memang menanganinya. Peta ini membuat lompatan itu
// satu klik (memakai `openDocument` yang sudah ada: navigasi + auto-buka dokumen).
export const ROW_TARGET = {
  sales_order:      { view: "orders",            nav_id: "sales-orders",  focus_type: "sales_order" },
  sales_return:     { view: "returns",           nav_id: "sales-orders",  focus_type: "sales_return" },
  internal_request: { view: "internal-requests", nav_id: "sales-orders",  focus_type: "internal_request" },
  customer:         { view: "customers-crm",     nav_id: "customers-crm", focus_type: "customer" },
};

/** Antrean Finance menunjuk layar yang berbeda walau jenis dokumennya sama. */
export const FINANCE_QUEUE_TARGET = {
  siap_faktur_pajak: { view: "tax-invoices", nav_id: "tax-hub" },
  uang_masuk:        { view: "customers-crm", nav_id: "customers-crm" },
  selisih_bayar:     { view: "payment-plans", nav_id: "payment-plans" },
  denda_draft:       { view: "payment-plans", nav_id: "payment-plans" },
  jatuh_tempo:       { view: "ar-aging", nav_id: "ar-aging" },
};

export function rowLink(row, queueId = "", desk = "sales_admin") {
  const byQueue = desk === "finance" ? FINANCE_QUEUE_TARGET[queueId] : null;
  const base = byQueue || ROW_TARGET[row?.ref_type] || ROW_TARGET.sales_order;
  return {
    view: base.view,
    nav_id: base.nav_id,
    focus_type: base.focus_type || row?.ref_type || "",
    focus_id: row?.order_id || row?.ref_id || "",
  };
}
