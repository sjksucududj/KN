// pdfConstants.js — opsi konfigurasi untuk PDF Template Designer (Fase 3).
// Mengikuti DEFAULT_TEMPLATE_CFG di backend/services/pdf_service.py.

export const PAPER_SIZES = [
  { value: "A4", label: "A4 (210 × 297 mm)" },
  { value: "Letter", label: "Letter (216 × 279 mm)" },
  { value: "Legal", label: "Legal (216 × 356 mm)" },
  { value: "A5", label: "A5 (148 × 210 mm)" },
];

export const ORIENTATIONS = [
  { value: "portrait", label: "Portrait (tegak)" },
  { value: "landscape", label: "Landscape (mendatar)" },
];

// WeasyPrint memakai fontconfig; DejaVu tersedia default. Sisanya fallback aman.
export const FONT_FAMILIES = [
  { value: "'DejaVu Sans'", label: "DejaVu Sans (default)" },
  { value: "'DejaVu Serif'", label: "DejaVu Serif" },
  { value: "Helvetica, Arial, sans-serif", label: "Helvetica / Arial" },
  { value: "'Times New Roman', Times, serif", label: "Times New Roman" },
  { value: "'Courier New', monospace", label: "Courier (monospace)" },
];

export const FONT_SIZES = [8, 9, 10, 11, 12, 13, 14].map((n) => ({
  value: String(n),
  label: `${n} pt`,
}));

// Preset warna cepat (mengikuti palette KN — biru #0058CC dominan).
export const COLOR_PRESETS = [
  "#0058CC", "#007AFF", "#1F7A45", "#B7791F", "#6B219A", "#C0392B", "#1a1a1a", "#334155",
];

export const EDITOR_TABS = [
  { id: "layout", label: "Layout" },
  { id: "kop", label: "Kop Surat" },
  { id: "typografi", label: "Font & Warna" },
  { id: "field", label: "Field" },
  { id: "ttd", label: "Tanda Tangan" },
  { id: "footer", label: "Footer" },
];
