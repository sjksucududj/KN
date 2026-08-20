import { useEffect, useState } from "react";
import { Repeat, Plus } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatCurrency } from "../../utils/formatters";
import { onImageError, productImage } from "../../utils/productImage";

/** EPIC5 — "Sering dibeli customer ini" (reorder cepat). */
export function ReorderStrip({ customer, products = [], onAdd, priceMap = {} }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!customer?.id) { setItems([]); return undefined; }
    let cancelled = false;
    setLoading(true);
    axios.get(`${API}/sales-orders/frequent-products`, { params: { customer_id: customer.id, limit: 8 } })
      .then((r) => { if (!cancelled) setItems(Array.isArray(r.data) ? r.data : []); })
      .catch(() => { if (!cancelled) setItems([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [customer]);

  if (!customer?.id || (!loading && items.length === 0)) return null;

  // Gabung dgn data.products untuk ketersediaan terkini.
  const byId = Object.fromEntries(products.map((p) => [p.id, p]));

  return (
    <div data-testid="reorder-strip" className="section-card mb-4">
      <div className="section-head">
        <div className="flex items-center gap-2"><Repeat size={14} className="text-[#0058CC]" /><h2 className="text-[13px]">Sering dibeli {customer.name}</h2></div>
      </div>
      <div className="section-body">
        {loading ? (
          <p className="py-2 text-[12px] text-[#6B6B73] animate-pulse">Memuat riwayat…</p>
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {items.map((it) => {
              const live = byId[it.id] || it;
              const unit = it.reorder_last_unit || live.base_unit || "meter";
              return (
                <div key={it.id} data-testid={`reorder-item-${it.id}`} className="flex min-w-[200px] items-center gap-2 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2">
                  <img src={productImage(live)} onError={onImageError} alt={live.name} className="h-12 w-12 rounded-md object-cover" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] font-semibold">{live.name}</p>
                    {/* F1b — harga efektif pelanggan (harga langganan/khusus) bila ada. */}
                    <p className="text-[10.5px] text-[#6B6B73] tabular-nums">
                      {formatCurrency(priceMap[live.id]?.price != null ? priceMap[live.id].price : live.price)}/{live.base_unit} · {it.reorder_count}×
                    </p>
                  </div>
                  <button data-testid={`reorder-add-${it.id}`} className="primary-button px-2 py-1" onClick={() => onAdd(live, 1, unit)} aria-label="Tambah ulang"><Plus size={13} /></button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
