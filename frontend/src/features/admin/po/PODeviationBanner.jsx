import { AlertCircle } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";

/**
 * PODeviationBanner — banner peringatan deviasi harga PO terhadap price-list supplier.
 * Dipakai bersama di PODetailPanel & PurchaseApprovalView (antrian approval).
 */
export default function PODeviationBanner({ deviation }) {
  if (!deviation?.flagged) return null;
  return (
    <div data-testid="po-price-deviation" className="rounded-md border border-[#FBD3D0] bg-[#FEF3F2] px-2.5 py-2 text-[11px] text-[#A8221A]">
      <div className="flex items-center gap-1.5 font-bold mb-1">
        <AlertCircle size={13} /> Harga di atas daftar harga supplier (+{deviation.max_deviation_pct}% &gt; batas {deviation.threshold_pct}%)
      </div>
      <div className="space-y-0.5">
        {(deviation.items || []).map((it, i) => (
          <div key={i} data-testid={`po-deviation-item-${i}`} className="flex items-center justify-between gap-2 text-[10.5px]">
            <span className="truncate">{it.sku || it.product_name}</span>
            <span className="tabular-nums">{formatCurrency(it.price)} vs {formatCurrency(it.ref_price)} <b className="text-[#A8221A]">(+{it.deviation_pct}%)</b></span>
          </div>
        ))}
      </div>
    </div>
  );
}
