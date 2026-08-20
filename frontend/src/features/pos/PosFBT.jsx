import { useEffect, useState } from "react";
import { Sparkles, Plus } from "lucide-react";
import { fetchFrequentlyBoughtTogether, recToProduct } from "./posApi";
import { formatCurrency } from "../../utils/formatters";
import { onImageError, productImage } from "../../utils/productImage";

/** F-4b — "Sering dibeli bersama" (market-basket) untuk produk acuan. */
export function PosFBT({ productId, entityId, onAdd, excludeIds = [] }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let on = true;
    setLoading(true);
    fetchFrequentlyBoughtTogether(productId, entityId, 6)
      .then((d) => { if (on) setItems(d); })
      .catch(() => { if (on) setItems([]); })
      .finally(() => { if (on) setLoading(false); });
    return () => { on = false; };
  }, [productId, entityId]);

  const visible = items.filter((p) => !excludeIds.includes(p.product_id));
  if (loading) return null;
  if (visible.length === 0) return null;

  return (
    <div data-testid="pos-fbt" className="mt-3 rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
      <div className="mb-2 flex items-center gap-1.5">
        <Sparkles size={13} className="text-[#6B219A]" />
        <h4 className="text-[12px] font-bold">Sering dibeli bersama</h4>
      </div>
      <div className="no-scrollbar flex gap-2 overflow-x-auto">
        {visible.map((p) => {
          const oos = Number(p.available_qty || 0) <= 0;
          return (
            <div key={p.product_id} data-testid={`fbt-${p.product_id}`} className="flex w-32 shrink-0 flex-col rounded-lg border border-[#E5E5EA] bg-white p-1.5">
              <img src={productImage(p)} onError={onImageError} alt={p.product_name} className="h-14 w-full rounded-md object-cover" />
              <p className="mt-1 line-clamp-2 text-[10.5px] font-semibold leading-tight">{p.product_name}</p>
              <p className="text-[10px] tabular-nums text-[#0058CC]">{formatCurrency(p.price)}</p>
              <button data-testid={`fbt-add-${p.product_id}`} className="secondary-button mt-1 justify-center py-1 text-[10.5px]" disabled={oos} onClick={() => onAdd(recToProduct(p), 1, p.base_unit)}>
                <Plus size={11} /> {oos ? "Habis" : "Tambah"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
