/**
 * rndDeepLink.js — FASE F · "buka layar R&D ini" dari layar mana pun.
 *
 * Pola SAMA dengan `configDeepLink.js` (G-0) & `traceDeepLink.js` (G-4): modul
 * TANPA dependensi (tidak impor React/axios) supaya layar yang cuma ingin
 * MENAUTKAN (mis. Pustaka Warna, Kontrak Supplier) tidak ikut menarik bundel
 * layar R&D yang di-`lazy()`.
 *
 *   openRnd({ view: "rnd-samples", colorId: "clr_1" })      → buat labdip dari warna
 *   openRnd({ view: "rnd-samples", sampleNumber: "KSC/SMP-00001" })  → buka permintaan
 *   openRnd({ view: "rnd-specs", specId: "spec_1" })        → buka spesifikasi
 *
 * `App.js` mendengarkan event ini (lihat `hooks/useRndDeepLink.js`), berpindah ke
 * hub R&D pada tab yang diminta, lalu meneruskan fokusnya ke view tujuan.
 */

/** Nama event global — satu konstanta agar tidak ada salah ketik di 2 tempat. */
export const RND_EVENT = "kn-open-rnd";

/** View yang sah menjadi tujuan deep-link R&D.
 *
 * `designer-kpi` ikut di sini walau menunya SUDAH dipisah (hub `designer-hub`):
 * mekanisme navigasinya sama (event global → `onNavigate(view)` → App resolve hub
 * dari `VIEW_NAV_INDEX`), jadi tidak perlu kanal event kedua yang tugasnya identik.
 */
export const RND_VIEWS = ["rnd-specs", "rnd-samples", "rnd-designs", "rnd-reports",
  "designer-kpi"];

/**
 * Buka hub R&D pada tab & objek tertentu.
 * @param {{view?: string, specId?: string, sampleId?: string, sampleNumber?: string,
 *          colorId?: string, colorLabel?: string, designId?: string}|string} target
 */
export function openRnd(target) {
  const t = typeof target === "string" ? { view: target } : (target || {});
  const view = RND_VIEWS.includes(t.view) ? t.view : "rnd-samples";
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(RND_EVENT, { detail: { ...t, view } }));
}

export default openRnd;
