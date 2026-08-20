/**
 * QtyDual (FASE U) — SATU komponen untuk DUA satuan: jumlah roll + ukuran.
 *
 * Permintaan pemilik: *"catat roll dan yard/kg dan panel — jadi ada 2 satuan yang
 * ditulis... dan ini seharusnya sudah ada di semuanya, di WMS, di sales, di SO dll."*
 *
 * KENAPA SATU KOMPONEN (bukan dirangkai di tiap tabel)
 * Kalimat ini muncul di banyak layar untuk SATU fakta yang sama. Kalau tiap tabel
 * merangkainya sendiri (`{formatQty(it.quantity)} {it.unit}`), satu aturan tampilan
 * saja — mis. "dokumen lama tanpa jumlah roll harus tampil —, bukan 0 roll" — harus
 * dikejar di belasan berkas, dan yang tertinggal akan **berbohong dengan tenang**.
 * Gate `INV-QTY-01` menuntut layar dokumen memakai komponen ini.
 *
 * ATURAN TAMPILAN (sama dengan `core_utils.qty_dual()` di server — satu arti):
 *   · `rolls` null/undefined  → jumlah roll TIDAK ditulis (dokumen lama).
 *     Kalau ukurannya pun tak ada → "—".
 *   · `rolls = 0`             → ditulis "0 roll" (memang nol gulungan).
 *   · Ukuran memakai angka gaya Indonesia (`formatQty`) + satuan dari dokumen
 *     (JANGAN pernah menulis satuan sebagai teks tetap: dokumen bisa yard/kg/panel).
 *   · `factor`/`factorTo` (mis. 1 panel = 1,6 yard pada pesanan ini — keputusan
 *     pemilik 2026-08-19) ditampilkan sebagai keterangan kecil, bukan angka ke-3.
 */
import { formatQty } from "../utils/formatters";

/**
 * ATURAN SATU-SATUNYA "apakah jumlah roll layak ditulis?".
 *
 * Dipakai layar yang tata letaknya TIDAK bisa memuat `<QtyDual/>` utuh — contoh
 * nyata: kartu mutasi persediaan, yang angka utamanya membawa tanda `+`/`−` dan
 * warna merah/hijau, jadi urutan "roll dulu" akan membuat tandanya menempel pada
 * angka yang salah. Sebelum helper ini, layar itu menulis syaratnya sendiri
 * (`m.qty_rolls !== null && m.qty_rolls !== undefined`) — salinan KEDUA dari aturan
 * yang sama. Salinan kedua adalah tempat aturan mulai menyimpang: begitu "—"
 * berubah artinya, satu tempat ikut dan satu tempat tidak, dan yang tidak ikut
 * akan berbohong dengan tenang. Gate `INV-QTY-01` menuntut layar memakai salah
 * satu dari dua pintu ini (`<QtyDual/>` atau `rollsText`), bukan menulis sendiri.
 */
export function hasRolls(rolls) {
  return rolls !== null && rolls !== undefined && rolls !== "";
}

/** `12` → `"12 roll"` · `null`/`undefined`/`""` → `""` (BUKAN "0 roll"). */
export function rollsText(rolls) {
  return hasRolls(rolls) ? `${formatQty(rolls)} roll` : "";
}

export default function QtyDual({
  rolls = null, measure = null, unit = "", factor = null, factorTo = "",
  className = "", testId = "", compact = false,
}) {
  const adaRoll = rolls !== null && rolls !== undefined && rolls !== "";
  const adaUkuran = measure !== null && measure !== undefined && measure !== "";
  const setara = factor && adaUkuran ? Number(measure) * Number(factor) : null;

  if (!adaRoll && !adaUkuran) {
    return (
      <span data-testid={testId || undefined} className={`text-[#8E8E93] ${className}`}>—</span>
    );
  }
  return (
    <span data-testid={testId || undefined} className={`tabular-nums ${className}`}>
      {adaRoll && (
        <span className="font-semibold">
          {formatQty(rolls)} roll
        </span>
      )}
      {adaRoll && adaUkuran && <span className="text-[#9A9BA3]"> · </span>}
      {adaUkuran && (
        <span className={adaRoll ? "" : "font-semibold"}>
          {formatQty(measure)}{unit ? ` ${unit}` : ""}
        </span>
      )}
      {setara && !compact ? (
        <span className="ml-1 text-[10.5px] text-[#6B6B73]">
          (≈ {formatQty(setara)} {factorTo || ""})
        </span>
      ) : null}
    </span>
  );
}
