/**
 * decimalInput (Fase A · PS-15 / R5) — util input desimal seragam.
 *
 * Aturan repo: pengguna Indonesia mengetik **koma** sebagai pemisah desimal
 * ("10,5"). Backend (`core_utils.parse_decimal`) sudah menerima keduanya; util ini
 * dipakai FE untuk (a) menghitung tampilan/estimasi lokal, (b) menjaga nilai form
 * tetap apa adanya sehingga tidak ada digit yang hilang saat mengetik.
 */

/** "1.234,56" | "1,234.56" | "10,5" | 12 → number (NaN bila jelas bukan angka). */
export function parseDecimal(value) {
  if (value === null || value === undefined || value === "") return 0;
  if (typeof value === "number") return value;
  let text = String(value).trim().replace(/\s/g, "").replace(/^rp\.?/i, "");
  const neg = text.startsWith("-");
  text = text.replace(/^[+-]/, "");
  const hasDot = text.includes(".");
  const hasComma = text.includes(",");
  if (hasDot && hasComma) {
    text = text.lastIndexOf(",") > text.lastIndexOf(".")
      ? text.replace(/\./g, "").replace(",", ".")
      : text.replace(/,/g, "");
  } else if (hasComma) {
    text = (text.match(/,/g) || []).length === 1
      ? text.replace(",", ".")
      : text.replace(/,/g, "");
  } else if ((text.match(/\./g) || []).length > 1) {
    text = text.replace(/\./g, "");
  }
  const out = Number.parseFloat(text);
  if (Number.isNaN(out)) return NaN;
  return neg ? -out : out;
}

/** true bila teks yang diketik masih bisa menjadi angka (izinkan "10," saat mengetik). */
export function isDecimalDraft(value) {
  if (value === "" || value === null || value === undefined) return true;
  return /^-?\d*([.,]\d*)?$/.test(String(value).replace(/\s/g, ""));
}

/** Angka → teks siap-input dengan koma-desimal (konsisten dengan kebiasaan lokal). */
export function toDecimalText(value, places = 3) {
  const n = parseDecimal(value);
  if (Number.isNaN(n)) return "";
  if (n === 0) return value === 0 || value === "0" ? "0" : "";
  return Number(n.toFixed(places)).toString().replace(".", ",");
}
