/**
 * qtyDualCsv.js — FASE U · kolom **Roll** & **Jumlah** untuk unduhan CSV daftar dokumen.
 *
 * KEPUTUSAN PEMILIK 2026-08-20
 * ============================
 * Di **layar** dua satuan ditulis sebagai satu kalimat (`<QtyDual/>` → "12 roll ·
 * 540 yard") karena di sana yang dicari adalah *pemahaman sekilas*. Di **berkas
 * unduhan** pemilik memilih **DUA KOLOM TERPISAH** (`Roll` | `Jumlah`), karena yang
 * dicari di sana adalah *penjumlahan*: kolom "12 roll · 540 yard" tidak bisa di-SUM
 * di Excel, dan itu justru alasan orang mengunduh CSV.
 *
 * `Jumlah` sengaja tetap TEKS ("150 yard + 30 kg")
 * ------------------------------------------------
 * Satu dokumen boleh memuat baris ber-satuan BERBEDA (knit dalam kg, woven dalam
 * yard — user story U.3). Menjumlahkannya menjadi satu angka akan MENCAMPUR satuan
 * dan menghasilkan bilangan yang terlihat sah tetapi tidak berarti apa pun. Jadi
 * kolom ini menjumlahkan **per satuan** lalu menuliskannya apa adanya. Kolom `Roll`
 * memang angka murni (gulungan tidak punya satuan) sehingga BISA di-SUM.
 *
 * ATURAN SEL KOSONG (keputusan pemilik: CSV ≠ PDF)
 * -----------------------------------------------
 * Dokumen lama yang tidak pernah menyebut jumlah roll → **sel dikosongkan**, BUKAN
 * "—" dan BUKAN "0". Alasannya teknis dan disengaja: Excel memperlakukan "—" sebagai
 * TEKS, dan satu sel teks di tengah kolom angka membuat SUM/AVERAGE pada kolom itu
 * berhenti bekerja tanpa peringatan. Di PDF "—" justru yang benar (di sana tidak ada
 * yang menjumlahkan, dan sel kosong terbaca sebagai kelalaian cetak).
 * `sumRolls()` mengembalikan `null` untuk keadaan itu, dan `csvExport.csvCellText`
 * menuliskan `null` sebagai sel kosong.
 *
 * SATU HELPER, BUKAN 15 SALINAN (§U.C rencana)
 * -------------------------------------------
 * Sebelum berkas ini, `PurchaseReturns` menghitung jumlah roll sendiri dari
 * `items[].roll_ids.length` — **sumber kedua** untuk fakta yang sudah punya
 * fieldnya (`qty_rolls`). Begitu keduanya berbeda (retur disetujui sebagian,
 * roll dibatalkan), berkas unduhan dan layar akan menyebut angka berbeda dan tidak
 * ada yang tahu mana yang benar. Gate `INV-QTY-01` menuntut daftar dokumen memakai
 * helper ini.
 */

/** Nama field ukuran yang dipakai di repo ini, diurutkan dari yang paling khusus. */
const MEASURE_FIELDS = ["quantity_returned", "quantity", "qty", "measure"];

/** Angka gaya Indonesia untuk teks kolom `Jumlah` (desimal koma, tanpa ribuan). */
function num(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return String(Math.round(n * 10000) / 10000).replace(".", ",");
}

/**
 * Total gulungan sebuah dokumen.
 * @returns {number|null} `null` bila TIDAK SATU PUN baris menyebut jumlah roll.
 *   Sengaja bukan `0`: "0 roll" adalah pernyataan bahwa tidak ada gulungan, dan
 *   pernyataan itu salah untuk dokumen yang sekadar belum mencatatnya.
 */
export function sumRolls(items, field = "qty_rolls") {
  const rows = Array.isArray(items) ? items : [];
  let total = null;
  rows.forEach((it) => {
    const v = it?.[field];
    if (v === null || v === undefined || v === "") return;
    const n = Number(v);
    if (!Number.isFinite(n)) return;
    total = (total === null ? 0 : total) + Math.round(n);
  });
  return total;
}

/** Ukuran dokumen, dijumlahkan PER SATUAN → `"150 yard + 30 kg"` (kosong bila tak ada). */
export function sumMeasure(items, { unitField = "unit", measureFields = MEASURE_FIELDS } = {}) {
  const rows = Array.isArray(items) ? items : [];
  const perUnit = new Map();
  rows.forEach((it) => {
    if (!it) return;
    const key = String(it[unitField] || "").trim();
    let raw;
    for (let i = 0; i < measureFields.length; i += 1) {
      const v = it[measureFields[i]];
      if (v !== null && v !== undefined && v !== "") { raw = v; break; }
    }
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    perUnit.set(key, (perUnit.get(key) || 0) + n);
  });
  const parts = [];
  perUnit.forEach((v, k) => { if (v) parts.push(`${num(v)}${k ? ` ${k}` : ""}`); });
  return parts.join(" + ");
}

/**
 * Dua definisi kolom CSV siap pakai (`Roll` lalu `Jumlah`) — judul & artinya SAMA
 * di semua daftar, jadi berkas dari layar mana pun bisa ditumpuk di satu lembar.
 *
 * @param {object} opts
 *   `itemsOf`      – cara mengambil baris dokumen (bawaan `row.items`).
 *   `rollField`    – field jumlah roll di baris (bawaan `qty_rolls`).
 *   `rollHeader`   – judul kolom roll (mis. "Roll Diterima" di papan PO).
 *   `measureHeader`– judul kolom ukuran.
 */
export function qtyDualCsvColumns(opts = {}) {
  const {
    itemsOf = (r) => r?.items || [],
    rollField = "qty_rolls",
    rollHeader = "Roll",
    measureHeader = "Jumlah",
    unitField = "unit",
    measureFields = MEASURE_FIELDS,
  } = opts;
  return [
    { header: rollHeader, type: "int", get: (r) => sumRolls(itemsOf(r), rollField) },
    { header: measureHeader, get: (r) => sumMeasure(itemsOf(r), { unitField, measureFields }) },
  ];
}

/** Versi satu-baris (dokumen ROOT ber-`qty_rolls`, mis. mutasi / tugas gudang / surat jalan). */
export function qtyDualRootCsvColumns(opts = {}) {
  const {
    rollField = "qty_rolls", rollHeader = "Roll", measureHeader = "Jumlah",
    measureField = "quantity", unitField = "unit",
  } = opts;
  return [
    { header: rollHeader, type: "int",
      get: (r) => sumRolls([r], rollField) },
    { header: measureHeader,
      get: (r) => sumMeasure([r], { unitField, measureFields: [measureField] }) },
  ];
}

export default { sumRolls, sumMeasure, qtyDualCsvColumns, qtyDualRootCsvColumns };
