/** BalancesTable — inventory balances grid with low-stock highlighting. */
import { Package } from "lucide-react";
import { formatQty, stockStatus, ROW_CLASSES, STATUS_BADGE } from "./inventoryConstants";

export default function BalancesTable({ loading, rows = [], selectedRow, onRowClick }) {
  return (
    <div className="bg-white rounded-xl border border-[#EFF0F2] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-[11.5px]">
          <thead>
            <tr className="bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">SKU</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Produk</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Pemilik</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Gudang</th>
              <th className="text-right px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Stok Fisik</th>
              <th className="text-right px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Dipesan</th>
              <th className="text-right px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Tersedia</th>
              <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#EFF0F2]">
            {loading && (
              <tr><td colSpan={8} className="text-center py-8 text-[12px] text-[#6B6B73]">Memuat…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center py-10">
                  <Package size={28} className="mx-auto mb-2 text-gray-300" />
                  <p className="text-[12px] text-[#6B6B73]">Tidak ada data stok</p>
                </td>
              </tr>
            )}
            {rows.map((b) => {
              const st = stockStatus(b);
              const isSelected = selectedRow?.id === b.id;
              return (
                <tr key={b.id}
                  data-testid={`balance-row-${b.id}`}
                  onClick={() => onRowClick(b)}
                  className={`cursor-pointer transition-colors ${ROW_CLASSES[st]} ${isSelected ? "ring-1 ring-inset ring-[#007AFF]" : ""}`}>
                  <td className="px-3 py-2 font-bold text-[#007AFF]">{b.sku}</td>
                  <td className="px-3 py-2">
                    <p className="font-medium">{b.product_name}</p>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center rounded-md bg-[#EEF2FF] px-1.5 py-0.5 text-[10px] font-semibold text-[#4338CA]">
                      {b.owner_entity_name || "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <p className="font-medium">{b.warehouse_name}</p>
                    <p className="text-[10px] text-[#8E8E93]">{b.warehouse_city}</p>
                  </td>
                  <td className="px-3 py-2 text-right font-bold tabular-nums">
                    {formatQty(b.on_hand_qty)}
                    <span className="block text-[9px] font-medium text-[#8E8E93]" data-testid={`balance-onhand-rolls-${b.id}`}>{b.on_hand_roll_count || 0} roll · {b.base_unit || "meter"}</span>
                  </td>
                  <td className="px-3 py-2 text-right font-semibold">
                    <div className="flex items-center justify-end gap-1">
                      <span className={`tabular-nums ${b.reserved_qty > 0 ? "text-[#FF9500]" : "text-[#8E8E93]"}`}>
                        {formatQty(b.reserved_qty)}
                      </span>
                      {b.reserved_qty > 0 && (
                        <span className="text-[9px] px-1 py-0.5 bg-orange-100 text-[#FF9500] rounded font-bold">
                          DIPESAN
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right text-[#34C759] font-bold tabular-nums">
                    {formatQty(b.available_qty)}
                    <span className="block text-[9px] font-medium text-[#8E8E93]" data-testid={`balance-avail-rolls-${b.id}`}>{b.roll_count || 0} roll · {b.base_unit || "meter"}</span>
                  </td>
                  <td className="px-3 py-2">{STATUS_BADGE[st]}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
