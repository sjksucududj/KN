/**
 * EPIC-VAR — Pengelompokan produk berdasarkan template_id untuk tampilan katalog.
 * PRINSIP: 1 varian = 1 SKU (product_id). Pengelompokan ini HANYA presentation
 * (katalog POS). Inventory/WMS/receiving tetap per-SKU.
 *
 * Produk tanpa template_id → grup tunggal (key = product.id).
 */

export function groupByTemplate(products = []) {
  const map = new Map();
  for (const p of products) {
    const key = p.template_id || p.id;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(p);
  }
  return Array.from(map.entries()).map(([key, variants]) => {
    const prices = variants.map((v) => Number(v.price || 0));
    const totalAvailable = variants.reduce((s, v) => s + Number(v.available_qty || 0), 0);
    // F2 (UoM SSOT) — total roll tersedia lintas varian (1 produk = 1 base_unit; roll beda panjang)
    const totalRolls = variants.reduce((s, v) => s + Number(v.roll_count || 0), 0);
    // Representatif: varian dengan stok tertinggi (fallback varian pertama).
    const rep =
      [...variants].sort((a, b) => Number(b.available_qty || 0) - Number(a.available_qty || 0))[0] ||
      variants[0];
    return {
      key,
      base: rep,
      name: rep.name,
      category: rep.category,
      image: rep.image,
      description: rep.description || "",  // F3 — deskripsi representatif (fallback popup)
      variants,
      isMulti: variants.length > 1,
      priceMin: prices.length ? Math.min(...prices) : 0,
      priceMax: prices.length ? Math.max(...prices) : 0,
      totalAvailable,
      totalRolls,
      anyAvailable: variants.some((v) => Number(v.available_qty || 0) > 0),
    };
  });
}

/** Label varian yang mudah dibaca: pakai variant_label bila ada, fallback warna · grade. */
export function variantLabel(p) {
  if (!p) return "";
  return (
    p.variant_label ||
    [p.color, p.grade ? `Grade ${p.grade}` : ""].filter(Boolean).join(" · ") ||
    p.sku ||
    ""
  );
}

/**
 * M0 — Pisahkan varian menjadi dua sumbu independen: Warna & Grade.
 * Warna memakai snapshot color_library (color_code/color_name/color_hex) bila ada,
 * fallback ke teks `color`. Mengembalikan opsi unik terurut + penyelesai SKU.
 */
export function colorKeyOf(v) {
  return (v?.color_code || v?.color || "").toString();
}

export function deriveAxisOptions(variants = []) {
  const colorMap = new Map();
  const gradeMap = new Map();
  for (const v of variants) {
    const ck = colorKeyOf(v);
    if (ck && !colorMap.has(ck)) {
      colorMap.set(ck, {
        key: ck,
        label: v.color_name || v.color || ck,
        hex: v.color_hex || "",
        code: v.color_code || "",
      });
    }
    const gk = (v.grade || "").toString();
    if (gk && !gradeMap.has(gk)) gradeMap.set(gk, { key: gk, label: gk });
  }
  const colors = [...colorMap.values()].sort((a, b) => a.label.localeCompare(b.label));
  const grades = [...gradeMap.values()].sort((a, b) => a.label.localeCompare(b.label));
  return { colors, grades, hasColor: colors.length > 1, hasGrade: grades.length > 1 };
}

/** Cari SKU konkret dari kombinasi warna+grade; fallback ke kandidat terdekat. */
export function resolveVariant(variants = [], colorKey, gradeKey) {
  const byBoth = variants.find(
    (v) => (!colorKey || colorKeyOf(v) === colorKey) && (!gradeKey || (v.grade || "") === gradeKey),
  );
  if (byBoth) return byBoth;
  const byColor = colorKey ? variants.find((v) => colorKeyOf(v) === colorKey) : null;
  const byGrade = gradeKey ? variants.find((v) => (v.grade || "") === gradeKey) : null;
  return byColor || byGrade || variants[0] || null;
}

/** Grade yang tersedia untuk sebuah warna (untuk disable kombinasi kosong). */
export function gradesForColor(variants = [], colorKey) {
  const set = new Set();
  for (const v of variants) if (!colorKey || colorKeyOf(v) === colorKey) set.add((v.grade || "").toString());
  return set;
}

