import { useEffect, useState } from "react";
import { Flame, Plus } from "lucide-react";
import { fetchBestSellers, recToProduct } from "./posApi";
import { formatCurrency } from "../../utils/formatters";
import { onImageError, productImage } from "../../utils/productImage";

/** F-4b — Strip produk terlaris (kurasi otomatis dari histori order). */
export function PosBestSellers({ entityId, onAdd, priceMap = {} }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let on = true;
    setLoading(true);
    fetchBestSellers(entityId, 10)
      .then((d) => { if (on) setItems(d); })
      .catch(() => { if (on) setItems([]); })
      .finally(() => { if (on) setLoading(false); });
    return () => { on = false; };
  }, [entityId]);

  if (!loading && items.length === 0) return null;

  return (
    <section data-testid="pos-best-sellers" className="mb-3">
      <header className="mb-2 flex items-center gap-1.5 px-1">
        <Flame size={15} className="text-[#FF6B35]" />
        <h2 className="text-[13px] font-bold text-[#1C1C1E]">Produk Terlaris</h2>
        <span className="text-[11px] text-[#8E8E93]">kurasi otomatis</span>
      </header>
      <div className="no-scrollbar flex gap-2.5 overflow-x-auto pb-1">
        {loading
          ? Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-44 w-36 shrink-0 animate-pulse rounded-xl bg-[#ECEDF0]" />)
          : items.map((p, idx) => {
              const oos = Number(p.available_qty || 0) <= 0;
              return (
                <article key={p.product_id} data-testid={`bestseller-${p.product_id}`} className="flex w-36 shrink-0 flex-col overflow-hidden rounded-xl border border-[#E5E5EA] bg-white">
                  <div className="relative">
                    <img src={productImage(p)} onError={onImageError} alt={p.product_name} className="h-20 w-full object-cover" />
                    <span className="absolute left-1.5 top-1.5 flex items-center gap-1 rounded-md bg-[#FF6B35] px-1.5 py-0.5 text-[9px] font-bold text-white">#{idx + 1}</span>
                  </div>
                  <div className="flex flex-1 flex-col p-2">
                    <p className="text-[9px] font-bold uppercase text-[#0058CC]">{p.sku}</p>
                    <h3 className="line-clamp-2 text-[11.5px] font-semibold leading-tight">{p.product_name}</h3>
                    <p className="mt-0.5 text-[10px] text-[#8E8E93]">{p.order_count}× pesanan</p>
                    {/* F1b — harga efektif pelanggan bila sudah dipilih, supaya satu layar
                        tidak memperlihatkan dua harga berbeda untuk barang yang sama. */}
                    <p className="mt-auto pt-1 text-[12px] font-bold tabular-nums">
                      {formatCurrency(priceMap[p.product_id]?.price != null
                        ? priceMap[p.product_id].price : p.price)}
                    </p>
                    <button data-testid={`bestseller-add-${p.product_id}`} className="primary-button mt-1.5 justify-center py-1.5 text-[11px]" disabled={oos} onClick={() => onAdd(recToProduct(p), 1, p.base_unit)}>
                      <Plus size={12} /> {oos ? "Habis" : "Tambah"}
                    </button>
                  </div>
                </article>
              );
            })}
      </div>
    </section>
  );
}
