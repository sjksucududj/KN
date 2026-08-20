/**
 * caseDeepLink.js — FASE G-9 · jembatan "buka kasus keuangan ini" dari layar mana pun.
 *
 * KENAPA MODUL TERPISAH (pola yang sama dengan `configDeepLink.js` G-0,
 * `rndDeepLink.js` FASE F, dan `kn-open-trace` G-4): layar yang cuma ingin MENAUTKAN
 * ke sebuah kasus tidak boleh ikut menarik seluruh bundel Pusat Kasus Keuangan.
 * Modul ini sengaja TANPA dependensi (tidak impor React, tidak impor axios).
 *
 * Dipakai US8: dari **Rekonsiliasi Bank → Dana Titipan**, tombol "Buka kasus"
 * membuat kasus lalu MENGANTAR petugas ke kasusnya — tanpa mengetik ulang dan tanpa
 * menyuruh pengguna mencari menunya sendiri.
 *
 *   openFinanceCase({ caseId: "fcs_…" })            → buka & sorot kasus itu
 *   openFinanceCase({ number: "KSC/CASE-00001" })   → cocokkan lewat nomor kasus
 *   openFinanceCase()                                → buka inbox kasus saja
 */

/** Nama event global. Satu konstanta supaya tidak ada salah ketik di 2 tempat. */
export const CASE_EVENT = "kn-open-finance-case";

/** Ambil nomor kasus (`<ENT>/CASE-#####`) dari kalimat penolakan backend. */
export function caseNumberFromText(text) {
  const m = String(text || "").match(/\b[A-Z0-9]{2,8}\/CASE-\d{3,}\b/);
  return m ? m[0] : "";
}

/**
 * Buka Pusat Kasus Keuangan, opsional langsung pada satu kasus.
 *
 * @param {{caseId?: string, number?: string}|string} target
 *   String dianggap `caseId`.
 */
export function openFinanceCase(target) {
  const t = typeof target === "string" ? { caseId: target } : (target || {});
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(CASE_EVENT, {
    // `note` = kalimat yang harus dibaca pengguna SETELAH mendarat. Pesan sukses tidak
    // boleh ditinggal di layar asal: begitu berpindah view, pesan itu ikut hilang.
    detail: {
      caseId: t.caseId || "", number: t.number || "", note: t.note || "",
      // `noteKind`: "success" (kasus baru lahir) atau "warning" (kasusnya sudah ada —
      // permintaan tadi DITOLAK, jadi jangan dipoles jadi bilah hijau).
      noteKind: t.noteKind || "success",
    },
  }));
}
