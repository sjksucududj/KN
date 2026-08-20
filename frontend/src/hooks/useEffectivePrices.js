/**
 * useEffectivePrices (F1b) — SATU panggilan untuk harga jual efektif per pelanggan.
 *
 * MENGAPA ADA: layar POS dulu memanggil `/price-approvals/effective` **satu kali per
 * produk** (sampai 40 permintaan sekali render) dan tetap memakai `products.price`
 * (harga GLOBAL) sebagai harga dasar — padahal server menyimpan pesanan dengan harga
 * pelanggan/PT. Akibatnya angka di layar bisa berbeda dari angka yang tersimpan.
 *
 * Sekarang: satu permintaan ke `/api/customer-prices/quote` yang memakai resolver
 * yang SAMA dengan pembuatan Pesanan Penjualan:
 *     harga khusus disetujui → harga pelanggan → harga PT → harga umum
 *
 * Bentuk lama (`has_special`, `requested_price`) tetap disediakan supaya komponen POS
 * yang sudah ada tidak perlu ditulis ulang.
 */
import { useCallback, useEffect, useState } from "react";
import axios, { API } from "../services/apiClient";

export const PRICE_SOURCE_META = {
  special_approval: { label: "Harga khusus", short: "Khusus", fg: "#6B219A", bg: "#F3E9FA" },
  customer: { label: "Harga pelanggan", short: "Pelanggan", fg: "#0058CC", bg: "#E7F0FF" },
  entity: { label: "Harga PT", short: "PT", fg: "#1B7F4B", bg: "#E6F6EC" },
  global: { label: "Harga umum", short: "Umum", fg: "#6B6B73", bg: "#F5F5F7" },
};

export const sourceMeta = (source) => PRICE_SOURCE_META[source] || PRICE_SOURCE_META.global;

/**
 * Harga yang benar untuk SATU baris, menghormati minimum qty aturan harga khusus.
 * Bila qty baris belum mencapai minimum, harga turun ke tingkat berikutnya
 * (pelanggan → PT → umum) — sama seperti keputusan server saat pesanan disimpan.
 */
export function pickPrice(entry, qty) {
  if (!entry) return null;
  const min = Number(entry.min_quantity || 0);
  const q = Number(qty);
  if (entry.source === "special_approval" && min > 0 && Number.isFinite(q) && q < min) {
    const fallbackSource = entry.customer_price != null
      ? "customer" : (entry.entity_price != null ? "entity" : "global");
    const price = Number(entry.customer_price ?? entry.entity_price ?? entry.global_price ?? 0);
    return {
      ...entry, price, source: fallbackSource, has_special: false, requested_price: price,
      special_blocked_by_min: true,
    };
  }
  return entry;
}

export function useEffectivePrices({
  customerId, entityId, productIds, quantity = null,
  enabled = true, delay = 350, refreshKey = 0,
}) {
  const [priceMap, setPriceMap] = useState({});
  const [loading, setLoading] = useState(false);
  const idsKey = (productIds || []).filter(Boolean).join(",");

  useEffect(() => {
    if (!enabled || !customerId || !idsKey) {
      setPriceMap({});
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const params = { customer_id: customerId, product_ids: idsKey };
        if (entityId) params.entity_id = entityId;
        if (quantity != null) params.quantity = quantity;
        const res = await axios.get(`${API}/customer-prices/quote`, { params });
        if (cancelled) return;
        const prices = res.data?.prices || {};
        const out = {};
        Object.entries(prices).forEach(([pid, v]) => {
          out[pid] = {
            ...v,
            has_special: v.source === "special_approval",
            requested_price: v.price,
            normal_price: v.entity_price ?? v.global_price ?? 0,
          };
        });
        setPriceMap(out);
      } catch {
        if (!cancelled) setPriceMap({});
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, delay);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [customerId, entityId, idsKey, quantity, enabled, delay, refreshKey]);

  const priceOf = useCallback((productId, qty) => pickPrice(priceMap[productId], qty),
                              [priceMap]);
  return { priceMap, priceOf, loading };
}

export default useEffectivePrices;
