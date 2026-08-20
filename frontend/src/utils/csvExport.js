/**
 * csvExport.js — satu bentuk baku untuk **UNDUH CSV** (FASE P6).
 *
 * KEPUTUSAN PEMILIK YANG DIWUJUDKAN DI SINI
 * =========================================
 *  1. **Pemisah `;` + BOM UTF-8.** Excel dengan wilayah Indonesia membaca `;` sebagai
 *     pemisah kolom. Dengan `,` (standar internasional) berkasnya tetap "valid" tetapi
 *     terbuka **menumpuk di kolom A** — dan yang membukanya menyimpulkan fitur unduhnya
 *     rusak. BOM (`\uFEFF`) membuat Excel mengenali UTF-8, tanpa itu "Pelanggan Ekaputra
 *     Tekstil" bisa tampil sebagai mojibake pada nama ber-aksen/simbol Rp.
 *  2. **Desimal KOMA untuk kolom angka.** Karena pemisah kolomnya `;`, `12500,5` dibaca
 *     Excel ID sebagai ANGKA (bisa dijumlah). Bila dikirim `12500.5`, Excel ID
 *     menganggapnya TEKS — kolomnya tidak bisa di-SUM, dan itu tepat alasan orang
 *     mengunduh CSV keuangan.
 *
 * TIGA HAL YANG MUDAH TERLEWAT DAN SUDAH DIBERESKAN DI SATU TEMPAT
 * ----------------------------------------------------------------
 *  · **Escaping RFC 4180.** Sel yang memuat `;`, tanda kutip, atau baris baru dibungkus
 *    kutip ganda dan kutipnya digandakan. Tanpa ini satu nama pelanggan seperti
 *    `Toko "Sejahtera"; Cabang Bandung` **menggeser seluruh kolom di kanannya** — dan
 *    barisnya tetap terlihat "masuk", jadi kerusakannya senyap.
 *  · **Anti CSV-injection.** Sel yang dimulai `=`, `+`, `@`, TAB, atau CR diawali kutip
 *    tunggal. Nama/catatan datang dari isian pengguna; tanpa ini `=HYPERLINK(...)` yang
 *    diketik seseorang akan **dieksekusi Excel** di komputer pemilik.
 *    `-` SENGAJA TIDAK ikut dilindungi: daftar keuangan penuh angka negatif
 *    (`-1500000`), dan mengawalinya dengan kutip akan mengubah setiap angka negatif
 *    menjadi teks yang tak bisa dijumlah — obatnya lebih merusak dari penyakitnya.
 *  · **CRLF antar baris**, sesuai RFC 4180 & yang diharapkan Excel di Windows.
 *
 * Bentuk kolom (didefinisikan oleh layar yang merender tabelnya, supaya isi berkas =
 * isi yang TERLIHAT):
 *   [{ key: "number", header: "Nomor" },
 *    { key: "total",  header: "Total", type: "num" },
 *    { key: "date",   header: "Tanggal", type: "date" },
 *    { header: "Pelanggan", get: (row) => row.customer?.name }]
 *
 * `type`: "text" (baku) · "num" (desimal koma) · "int" (dibulatkan) · "date" (dd/mm/yyyy)
 *         · "datetime" (dd/mm/yyyy HH:MM).
 *
 * Dijaga `scripts/guardrails/verify_list_export.py` (INV-UI-07) — penjaga itu MENJALANKAN
 * berkas ini dengan Node dan menguji hasil escaping-nya sungguhan, bukan hanya membaca
 * polanya. Karena itu berkas ini sengaja **tanpa import apa pun**.
 */

export const CSV_DELIMITER = ";";
export const CSV_BOM = "\uFEFF";

/** Karakter pembuka yang membuat Excel memperlakukan sel sebagai FORMULA. */
const INJECTION_PREFIX = /^[=+@\t\r]/;

const pad2 = (n) => String(n).padStart(2, "0");

/** ISO / Date → `dd/mm/yyyy` (urutan yang dibaca Excel wilayah Indonesia). */
export function formatCsvDate(value) {
  if (value === null || value === undefined || value === "") return "";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
}

/** ISO / Date → `dd/mm/yyyy HH:MM` — untuk buku besar/mutasi, di mana JAM ikut penting. */
export function formatCsvDateTime(value) {
  if (value === null || value === undefined || value === "") return "";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`
    + ` ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/**
 * Angka → teks berdesimal KOMA, **tanpa pemisah ribuan**.
 * Pemisah ribuan sengaja dihindari: `1.250.000` akan dibaca Excel ID sebagai teks.
 */
export function formatCsvNumber(value) {
  if (value === null || value === undefined || value === "") return "";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "";
  return String(n).replace(".", ",");
}

/** Nilai mentah → teks sel, sesuai `type` kolom. */
export function csvCellText(value, type = "text") {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "Ya" : "Tidak";
  if (Array.isArray(value)) return value.map((v) => csvCellText(v, "text")).join(", ");
  if (type === "num") return formatCsvNumber(value);
  if (type === "int") {
    const n = Number(value);
    return Number.isFinite(n) ? String(Math.round(n)) : "";
  }
  if (type === "date") return formatCsvDate(value);
  if (type === "datetime") return formatCsvDateTime(value);
  if (typeof value === "object") return "";
  return String(value);
}

/** Satu sel → teks yang aman ditulis ke CSV (escaping + anti-injection). */
export function escapeCsvCell(text, delimiter = CSV_DELIMITER) {
  let s = text === null || text === undefined ? "" : String(text);
  if (INJECTION_PREFIX.test(s)) s = `'${s}`;
  if (s.includes(delimiter) || s.includes('"') || s.includes("\n") || s.includes("\r")) {
    s = `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/** Ambil nilai satu kolom dari satu baris (mendukung `get(row)` untuk field turunan). */
export function csvValue(row, col) {
  const raw = typeof col.get === "function" ? col.get(row) : row?.[col.key];
  return csvCellText(raw, col.type || "text");
}

/** Baris + definisi kolom → isi berkas CSV (tanpa BOM; BOM ditambah saat diunduh). */
export function buildCsv(rows, columns, delimiter = CSV_DELIMITER) {
  const cols = columns || [];
  const header = cols.map((c) => escapeCsvCell(c.header, delimiter)).join(delimiter);
  const body = (rows || []).map((row) =>
    cols.map((c) => escapeCsvCell(csvValue(row, c), delimiter)).join(delimiter));
  return [header, ...body].join("\r\n");
}

/** `pesanan_semua_20260818-1432.csv` — cakupan & waktu ikut tercetak di nama berkas. */
export function csvFilename(base, scope) {
  const d = new Date();
  const stamp = `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}`
    + `-${pad2(d.getHours())}${pad2(d.getMinutes())}`;
  return `${base || "data"}_${scope === "all" ? "semua" : "halaman"}_${stamp}.csv`;
}

/** Picu unduhan di peramban (BOM ditambahkan di sini, satu kali, di satu tempat). */
export function downloadCsv(filename, csv) {
  const blob = new Blob([CSV_BOM + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default { buildCsv, downloadCsv, csvFilename, escapeCsvCell, CSV_DELIMITER };
