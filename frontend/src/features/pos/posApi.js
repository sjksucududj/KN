import axios, { API } from "../../services/apiClient";

/** F-4b — POS advanced recommendation API helpers (dihitung dari histori sales_orders). */
export async function fetchBestSellers(entityId, limit = 10) {
  const { data } = await axios.get(`${API}/pos/best-sellers`, { params: { entity_id: entityId || undefined, limit } });
  return Array.isArray(data) ? data : [];
}

export async function fetchFrequentlyBoughtTogether(productId, entityId, limit = 6) {
  if (!productId) return [];
  const { data } = await axios.get(`${API}/pos/frequently-bought-together`, { params: { product_id: productId, entity_id: entityId || undefined, limit } });
  return Array.isArray(data) ? data : [];
}

export async function fetchSubstitutes(productId, entityId, limit = 6) {
  if (!productId) return [];
  const { data } = await axios.get(`${API}/pos/substitutes`, { params: { product_id: productId, entity_id: entityId || undefined, limit } });
  return Array.isArray(data) ? data : [];
}

/** Normalisasi baris rekomendasi -> objek product yang dipahami addToCart(). */
export function recToProduct(r) {
  return {
    id: r.product_id,
    name: r.product_name,
    sku: r.sku,
    price: r.price,
    image: r.image,
    base_unit: r.base_unit,
    category: r.category,
    color: r.color,
    grade: r.grade,
    available_qty: r.available_qty,
  };
}
