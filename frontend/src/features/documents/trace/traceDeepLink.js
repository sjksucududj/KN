/**
 * traceDeepLink — FASE G-4 · "buka Jejak Dokumen ini" dari layar mana pun.
 *
 * Pola sama dengan `configDeepLink.js` (FASE G-0) dan `kn-open-palette`: modul
 * TANPA dependensi (tidak impor React/axios) supaya panel detail yang cuma ingin
 * MENAUTKAN tidak ikut menarik bundel layar Jejak Dokumen yang di-`lazy()`.
 *
 *   openTrace({ docType: "vendor_bill", docId: "vb_123" })
 *
 * `App.js` mendengarkan event ini (lihat `hooks/useTraceDeepLink.js`), berpindah
 * view ke `doc-trace`, lalu meneruskan jangkar ke <DocTraceView anchor .../>.
 */

/** Nama event global — satu konstanta agar tidak ada salah ketik di 2 tempat. */
export const TRACE_EVENT = "kn-open-trace";

/** Pola URL publik yang dipakai QR pada dokumen cetak. */
export const TRACE_PATH_RE = /^\/jejak-dokumen\/([a-z_]+)\/([^/?#]+)/i;

/**
 * Buka layar Jejak Dokumen pada dokumen tertentu.
 * @param {{docType: string, docId: string, number?: string}} target
 */
export function openTrace(target) {
  const t = target || {};
  if (!t.docType || !t.docId) return;
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(TRACE_EVENT, {
    detail: { docType: t.docType, docId: t.docId, number: t.number || "" },
  }));
}

/** Baca jangkar dari URL (QR dokumen cetak). Mengembalikan null bila bukan URL jejak. */
export function anchorFromLocation() {
  if (typeof window === "undefined") return null;
  const m = window.location.pathname.match(TRACE_PATH_RE);
  if (!m) return null;
  return { docType: m[1], docId: decodeURIComponent(m[2]), nonce: 1 };
}
