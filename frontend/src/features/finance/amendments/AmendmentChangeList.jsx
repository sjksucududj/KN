/**
 * AmendmentChangeList — FASE G-1 · daftar "dari → menjadi" yang bisa dibaca orang.
 *
 * Bentuk `changes[]` identik di pratinjau maupun dokumen amandemen tersimpan:
 *   { product_id, product_name, field, label, from, to }
 * Nilai uang diformat sebagai uang, persen sebagai persen, jumlah sebagai qty —
 * supaya penyetuju tidak perlu menebak satuan angka yang sedang ia putuskan.
 */
import { ArrowRight } from "lucide-react";
import { formatCurrency, formatQty } from "../../../utils/formatters";

function renderValue(field, value) {
  const n = Number(value || 0);
  if (field === "price") return formatCurrency(n);
  if (field === "discount_percent" || field === "order_discount_percent") return `${formatQty(n)}%`;
  return formatQty(n);
}

export default function AmendmentChangeList({ changes = [], testId = "amd-changes" }) {
  if (!changes.length) {
    return (
      <p data-testid={`${testId}-empty`} className="text-[11px] text-[#6B6B73]">
        Belum ada perubahan yang diusulkan.
      </p>
    );
  }
  return (
    <div data-testid={testId} className="rounded-md border border-[#EFF0F2] overflow-hidden">
      <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase tracking-wide text-[#6B6B73] border-b border-[#EFF0F2]">
        Rincian perubahan ({changes.length})
      </div>
      {changes.map((c, i) => (
        <div key={`${c.product_id || "order"}-${c.field}-${i}`}
          data-testid={`${testId}-row-${i}`}
          className="px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0">
          <p className="text-[11px] font-semibold text-[#1C1C1E] truncate">{c.product_name || "Pesanan"}</p>
          <div className="flex items-center gap-1.5 text-[10.5px]">
            <span className="text-[#6B6B73]">{c.label || c.field}</span>
            <span className="tabular-nums text-[#8E8E93] line-through">{renderValue(c.field, c.from)}</span>
            <ArrowRight size={10} className="text-[#0058CC] shrink-0" />
            <span className="tabular-nums font-bold text-[#0058CC]">{renderValue(c.field, c.to)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
