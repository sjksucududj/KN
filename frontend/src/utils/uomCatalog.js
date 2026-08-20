/**
 * uomCatalog.js — FASE U · penyimpan KATALOG SATUAN di level modul (tanpa impor).
 *
 * MASALAH YANG DISELESAIKAN
 * =========================
 * Katalog satuan datang dari server (`GET /api/uom-conversions/catalog`, sudah
 * di-overlay baris master `uoms` — jadi `PANEL` yang ditambah pemilik muncul di
 * sana tanpa satu baris kode diubah). Tetapi katalog itu hanya bisa diambil di
 * dalam React (hook `useUomConversions`), sedangkan `utils/uom.js` adalah util
 * MURNI yang dipakai di luar React (POS, modal amandemen PO). Akibatnya util itu
 * dulu menyimpan daftar satuannya SENDIRI:
 *
 *     const seen = new Set([base, "yard", "cm", "inch"]);     ← daftar ketikan
 *
 * dan itulah bentuk paling murni dari keluhan pemilik: **menambah satuan di master
 * tidak mengubah apa pun di layar**. Pemilih satuan di layar POS/PO tidak pernah
 * menawarkan `PANEL` walau masternya sudah ada.
 *
 * BENTUK PERBAIKAN
 * ================
 * Satu penyimpan kecil di level modul. `useUomConversions` MENGISI (satu arah),
 * util murni MEMBACA. Tidak ada `import` di berkas ini, jadi tidak mungkin ada
 * impor melingkar dan berkas ini bisa diuji Node apa adanya (pola `csvExport.js`).
 *
 * Bila katalog belum termuat (permintaan pertama masih jalan), pembaca menerima
 * daftar KOSONG — dan pemanggilnya WAJIB tetap menyertakan satuan produk sendiri.
 * Jadi layar tidak pernah kehilangan pilihan yang memang sah, ia hanya belum
 * menampilkan tambahan dari master. Ini disengaja: layar kosong lebih berbahaya
 * daripada layar yang belum lengkap sedetik.
 */

let _units = [];        // [{ code, label, dimension, aliases[], factor_per_document }]

/** Diisi `useUomConversions` setiap kali katalog server termuat/di-reload. */
export function setUomCatalogUnits(units) {
  _units = Array.isArray(units) ? units : [];
}

/** Semua satuan katalog (kosong bila belum termuat). */
export function uomCatalogUnits() {
  return _units;
}

/** Satuan katalog untuk satu dimensi (`length` / `weight` / `count` / `area`). */
export function uomCatalogUnitsOf(dimension) {
  if (!dimension) return _units;
  return _units.filter((u) => u.dimension === dimension);
}

/** Dimensi sebuah kata satuan (lewat `code` MAUPUN alias) — "" bila tak dikenal. */
export function uomDimensionOf(code) {
  const w = String(code || "").trim().toLowerCase();
  if (!w) return "";
  const hit = _units.find((u) => String(u.code).toLowerCase() === w
    || (u.aliases || []).some((a) => String(a).toLowerCase() === w));
  return hit?.dimension || "";
}

/** Label ramah untuk satu kata satuan (jatuh ke katanya sendiri bila tak dikenal). */
export function uomLabelOf(code) {
  const w = String(code || "").trim().toLowerCase();
  const hit = _units.find((u) => String(u.code).toLowerCase() === w);
  return hit?.label || (w ? w.charAt(0).toUpperCase() + w.slice(1) : "");
}

/**
 * Opsi `<KNSelect/>` dari MASTER untuk satu/lebih dimensi.
 * `extra` = kata satuan yang WAJIB tetap ada (mis. satuan yang sudah tersimpan di
 * dokumen lama, walau masternya kini nonaktif) supaya nilai tersimpan tidak hilang
 * dari pemilih — dropdown yang tidak memuat nilainya sendiri terlihat "kosong"
 * dan menggoda pengguna menyimpan ulang dengan satuan yang salah.
 */
export function uomSelectOptions({ dimensions = [], extra = [] } = {}) {
  const dims = Array.isArray(dimensions) ? dimensions.filter(Boolean) : [];
  const src = dims.length ? _units.filter((u) => dims.includes(u.dimension)) : _units;
  const out = [];
  const seen = new Set();
  src.forEach((u) => {
    const code = String(u.code || "").toLowerCase();
    if (!code || seen.has(code)) return;
    seen.add(code);
    out.push({ value: code, label: u.label || code });
  });
  (extra || []).forEach((e) => {
    const code = String(e || "").trim().toLowerCase();
    if (!code || seen.has(code)) return;
    seen.add(code);
    out.push({ value: code, label: uomLabelOf(code) });
  });
  return out;
}

export default {
  setUomCatalogUnits, uomCatalogUnits, uomCatalogUnitsOf,
  uomDimensionOf, uomLabelOf, uomSelectOptions,
};
