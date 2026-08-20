// Fase 1B — preview pricing di sisi klien (CERMIN backend services/config_service.compute_order_pricing).
// Tujuan: tampilkan ringkasan diskon + PPN sebelum order dibuat. Backend tetap
// otoritatif saat menyimpan; util ini hanya untuk preview UX.
// F-10 Coretax — dukung DPP Nilai Lain 11/12 (PPN efektif = tarif × 11/12).

export function computeOrderPreview(items, orderDiscountPercent, settings) {
  const sales = (settings && settings.sales) || {};
  const tax = (settings && settings.tax) || {};
  const allowItem = sales.allow_item_discount !== false;
  const allowOrder = sales.allow_order_discount !== false;
  const isPkp = tax.is_pkp !== false;
  const rate = isPkp ? Number(tax.ppn_rate || 0) : 0;
  const mode = tax.ppn_mode || "excluded";
  const useNL = rate > 0 && tax.dpp_nilai_lain === true;
  const dppFactor = useNL ? 11 / 12 : 1;
  const effRate = rate * dppFactor;

  let gross = 0;
  let itemsDisc = 0;
  (items || []).forEach((it) => {
    const price = Number((it.product && it.product.price) || it.price || 0);
    const qty = Number(it.quantity || 0);
    const subtotal = price * qty;
    const dp = allowItem ? Math.max(0, Math.min(100, Number(it.discount_percent || 0))) : 0;
    gross += subtotal;
    itemsDisc += (subtotal * dp) / 100;
  });

  const afterItem = gross - itemsDisc;
  const odp = allowOrder ? Math.max(0, Math.min(100, Number(orderDiscountPercent || 0))) : 0;
  const orderDisc = (afterItem * odp) / 100;
  const net = afterItem - orderDisc;

  let dpp;
  let ppn;
  let grand;
  if (!isPkp || rate <= 0) {
    dpp = net; ppn = 0; grand = net;
  } else if (mode === "included") {
    const hargaJual = net / (1 + effRate / 100);
    dpp = hargaJual * dppFactor; ppn = net - hargaJual; grand = net;
  } else {
    dpp = net * dppFactor; ppn = (net * effRate) / 100; grand = net + ppn;
  }

  return {
    gross,
    itemsDisc,
    orderDisc,
    discountTotal: itemsDisc + orderDisc,
    net,
    dpp,
    ppnRate: rate,
    effectiveRate: effRate,
    dppNilaiLain: useNL,
    ppn,
    grand,
    mode,
    isPkp,
    allowItem,
    allowOrder,
  };
}
