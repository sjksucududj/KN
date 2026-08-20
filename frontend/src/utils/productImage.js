/**
 * Gambar produk + cadangan (fallback) yang ANGGUN.
 *
 * Kenapa ada: produk yang lahir dari alur R&D (FASE F) — atau master data yang belum
 * diberi foto — tidak punya `image`. Tanpa cadangan, browser menampilkan ikon
 * "gambar rusak" + teks alt, dan kartu produk terlihat seperti bug.
 * Cadangan di bawah adalah SVG inline (tanpa permintaan jaringan) berisi ikon kain
 * netral, jadi kartu tetap rapi baik di POS desktop maupun mobile.
 */
const FALLBACK = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
     <defs>
       <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
         <stop offset="0" stop-color="#EEF2F7"/><stop offset="1" stop-color="#DCE3EC"/>
       </linearGradient>
     </defs>
     <rect width="400" height="300" fill="url(#g)"/>
     <g fill="none" stroke="#9AA7B8" stroke-width="8" stroke-linecap="round">
       <path d="M120 108h160M120 150h160M120 192h160"/>
     </g>
     <text x="200" y="248" font-family="Inter,Arial,sans-serif" font-size="20"
           fill="#7B8798" text-anchor="middle">Belum ada foto</text>
   </svg>`);

export const PRODUCT_IMAGE_FALLBACK = FALLBACK;

/** URL gambar produk; kosong/None → cadangan SVG. */
export function productImage(product) {
  const src = String(product?.image || product?.image_url || "").trim();
  return src || FALLBACK;
}

/** Handler `onError` untuk <img> supaya tautan mati pun tidak tampak rusak. */
export function onImageError(event) {
  if (event?.target && event.target.src !== FALLBACK) event.target.src = FALLBACK;
}
