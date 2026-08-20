/** ProductHistoryPanel — right-side panel: balance summary + reserved info + movement history. */
import { X, AlertTriangle } from "lucide-react";
import { formatQty, formatDate, MOV_TYPE_MAP, CounterpartyBadge } from "./inventoryConstants";

export default function ProductHistoryPanel({ selectedRow, history = [], histLoading, onClose }) {
  return (
    <div className="bg-white rounded-xl border border-[#EFF0F2] overflow-hidden self-start">
      <div className="px-3 py-2 border-b border-[#EFF0F2] bg-[#FAFBFC] flex items-center justify-between">
        <div>
          <p className="text-[10px] font-bold text-[#007AFF] uppercase">{selectedRow.sku}</p>
          <p className="text-[11.5px] font-semibold truncate max-w-[200px]">{selectedRow.product_name}</p>
        </div>
        <button onClick={onClose} data-testid="close-history-panel" className="text-[#6B6B73] hover:text-black"><X size={13} /></button>
      </div>
      {/* Mini balance summary */}
      <div className="grid grid-cols-3 divide-x divide-[#EFF0F2] border-b border-[#EFF0F2]">
        <div className="p-2 text-center">
          <p className="text-[9px] uppercase font-bold text-[#6B6B73]">Stok Fisik</p>
          <p className="text-[13px] font-bold tabular-nums">{formatQty(selectedRow.on_hand_qty)}</p>
        </div>
        <div className="p-2 text-center">
          <p className="text-[9px] uppercase font-bold text-[#6B6B73]">Dipesan</p>
          <p className="text-[13px] font-bold text-[#FF9500] tabular-nums">{formatQty(selectedRow.reserved_qty)}</p>
        </div>
        <div className="p-2 text-center">
          <p className="text-[9px] uppercase font-bold text-[#6B6B73]">Tersedia</p>
          <p className="text-[13px] font-bold text-green-600 tabular-nums">{formatQty(selectedRow.available_qty)}</p>
        </div>
      </div>

      {/* Reserved Info Card */}
      {selectedRow.reserved_qty > 0 && (
        <div className="m-3 rounded-lg border border-orange-200 bg-orange-50 p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className="text-[#FF9500] flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-[11px] font-bold text-[#FF9500]">Material Direserve</p>
              <p className="text-[10px] text-[#6B6B73] mt-1">
                <span className="font-bold tabular-nums">{formatQty(selectedRow.reserved_qty)}</span> {selectedRow.unit || 'unit'} dari stok ini sedang dipesan untuk pesanan penjualan yang belum dikonfirmasi.
              </p>
              <p className="text-[9px] text-[#8E8E93] mt-1.5 italic">
                Bahan yang dipesan akan otomatis dilepas jika pesanan dibatalkan atau kedaluwarsa.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* History */}
      <div className="px-3 py-2 border-b border-[#EFF0F2] bg-[#FAFBFC]">
        <p className="text-[10px] font-bold uppercase text-[#6B6B73]">Riwayat Pergerakan</p>
      </div>
      {histLoading ? (
        <div className="py-6 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
      ) : history.length === 0 ? (
        <div className="py-6 text-center text-[12px] text-[#6B6B73]">Belum ada riwayat</div>
      ) : (
        <div className="divide-y divide-[#EFF0F2] max-h-[360px] overflow-y-auto">
          {history.map((m) => {
            const mt = MOV_TYPE_MAP[m.movement_type] || { label: m.movement_type, color: "text-gray-600", dot: "bg-gray-400" };
            return (
              <div key={m.id} data-testid={`history-row-${m.id}`} className="px-3 py-2 hover:bg-[#FAFBFC]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${mt.dot}`} />
                    <span className={`text-[10.5px] font-semibold ${mt.color}`}>{mt.label}</span>
                    {/* E5.3 — nama singkat badan usaha lawan pada pindah kepemilikan */}
                    <CounterpartyBadge movement={m} />
                  </div>
                  <span className={`text-[12px] font-bold tabular-nums ${m.quantity < 0 ? "text-red-600" : "text-green-700"}`}>
                    {m.quantity > 0 ? "+" : ""}{formatQty(m.quantity)}
                  </span>
                </div>
                <p className="text-[10px] text-[#8E8E93] mt-0.5">{formatDate(m.timestamp)} · {m.source_document_label || m.source_document || ""}</p>
                {m.batch && <p className="text-[10px] text-[#6B6B73]">Batch: {m.batch}{m.lot ? ` · Lot: ${m.lot}` : ""}</p>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
