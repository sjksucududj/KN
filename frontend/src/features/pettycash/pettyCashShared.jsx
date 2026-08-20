// ─── Shared helpers untuk modul Digitalisasi Formulir Sukacita ───────────────
// Petty Cash: Pengajuan Dana (PD) · Pertanggungjawaban (Settlement) · Kendaraan.
// SSOT status label/tone + StatusPill + konstanta. Fungsi CETAK (print) dokumen
// dipindah ke utils/docPrint.js (self-contained, di luar scan UX baseline).
export {
  printCashAdvance, printTandaTerima, printSettlement, terbilang, printHTML,
} from "../../utils/docPrint";

// ─── Status Cash Advance (Form PD) ───────────────────────────────────────────
export const CA_STATUS = {
  draft:            { label: "Draf",                 cls: "pill-muted" },
  pending_atasan:   { label: "Menunggu Atasan",       cls: "pill-warning" },
  pending_pimpinan: { label: "Menunggu Pimpinan",     cls: "pill-warning" },
  pending_finance:  { label: "Menunggu Keuangan",     cls: "pill-warning" },
  approved:         { label: "Disetujui",             cls: "pill-info" },
  disbursed:        { label: "Dicairkan",             cls: "pill-info" },
  settled:          { label: "Selesai (LPJ)",         cls: "pill-success" },
  rejected:         { label: "Ditolak",               cls: "pill-danger" },
};

export const STL_STATUS = {
  draft:        { label: "Draf",            cls: "pill-muted" },
  submitted:    { label: "Diajukan",         cls: "pill-warning" },
  posted_to_gl: { label: "Terposting GL",    cls: "pill-success" },
  rejected:     { label: "Ditolak",          cls: "pill-danger" },
};

// Urutan tahap approval PD (untuk timeline & progress).
export const CA_STAGE_ORDER = ["pending_atasan", "pending_pimpinan", "pending_finance", "approved"];
export const CA_STAGE_LABEL = {
  atasan: "Atasan Langsung",
  pimpinan: "Pimpinan",
  finance: "Bagian Keuangan",
};

export const SATUAN_OPTIONS = [
  { value: "unit", label: "Unit" },
  { value: "roll", label: "Roll" },
  { value: "yard", label: "Yard" },
  { value: "kg", label: "Kg" },
  { value: "meter", label: "Meter" },
  { value: "paket", label: "Paket" },
  { value: "lembar", label: "Lembar" },
  { value: "hari", label: "Hari" },
];

export function StatusPill({ status, map = CA_STATUS, testId }) {
  const s = map[status] || { label: status || "—", cls: "pill-muted" };
  return (
    <span data-testid={testId} className={`status-pill ${s.cls}`}>{s.label}</span>
  );
}

export const fmtDate = (s) =>
  s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "—";
