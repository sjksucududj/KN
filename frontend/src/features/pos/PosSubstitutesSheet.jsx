import { useEffect, useState } from "react";
import { X, Plus, PackageX, Loader2, Repeat } from "lucide-react";
import { fetchSubstitutes, recToProduct } from "./posApi";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { onImageError, productImage } from "../../utils/productImage";

const REASON_LABEL = { kategori: "Kategori sama", grade: "Grade sama", populer: "Populer" };
const REASON_CLS = { kategori: "status-confirmed", grade: "status-waiting_approval", populer: "status-pill" };

/** F-4b — Sheet alternatif (substitusi) saat produk OOS. */
export function PosSubstitutesSheet({ product, entityId, onAdd, onClose }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!product) return;
    let on = true;
    setLoading(true);
    fetchSubstitutes(product.id, entityId, 8)
      .then((d) => { if (on) setItems(d); })
      .catch(() => { if (on) setItems([]); })
      .finally(() => { if (on) setLoading(false); });
    return () => { on = false; };
  }, [product, entityId]);

  if (!product) return null;

  return (
    <div className="fixed inset-0 z-[130] flex items-end justify-center" data-testid="pos-substitutes-sheet">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-[460px] rounded-t-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <div className="flex items-center gap-2">
            <Repeat size={16} className="text-[#0058CC]" />
            <div>
              <h3 className="text-[14px] font-bold">Alternatif Pengganti</h3>
              <p className="text-[11px] text-[#8E8E93]">{product.name} sedang habis</p>
            </div>
          </div>
          <button data-testid="pos-substitutes-close" onClick={onClose} aria-label="Tutup" className="text-[#6B6B73]"><X size={18} /></button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto px-4 py-3">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-[#6B6B73]"><Loader2 size={16} className="spin" /> Memuat alternatif…</div>
          ) : items.length === 0 ? (
            <div data-testid="pos-substitutes-empty" className="flex flex-col items-center gap-2 py-10 text-center text-[#6B6B73]">
              <PackageX size={28} className="text-[#C7C7CC]" />
              <p className="text-[13px]">Tidak ada alternatif yang ada stoknya saat ini.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((p) => (
                <div key={p.product_id} data-testid={`substitute-${p.product_id}`} className="flex items-center gap-2.5 rounded-lg border border-[#EFF0F2] p-2">
                  <img src={productImage(p)} onError={onImageError} alt={p.product_name} className="h-12 w-12 rounded-md object-cover" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className="truncate text-[12.5px] font-semibold">{p.product_name}</p>
                      <span className={`status-pill ${REASON_CLS[p.match_reason] || "status-pill"} scale-90`}>{REASON_LABEL[p.match_reason] || p.match_reason}</span>
                    </div>
                    <p className="text-[11px] text-[#6B6B73]">{p.category} · {p.color} · Grade {p.grade}</p>
                    <p className="text-[11.5px] font-bold tabular-nums text-[#0058CC]">{formatCurrency(p.price)} <span className="font-normal text-[#126E2C]">· stok {formatQty(p.available_qty)}</span></p>
                  </div>
                  <button data-testid={`substitute-add-${p.product_id}`} className="primary-button px-3 py-2 text-[12px]" onClick={() => { onAdd(recToProduct(p), 1, p.base_unit); onClose(); }}>
                    <Plus size={13} /> Tambah
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
