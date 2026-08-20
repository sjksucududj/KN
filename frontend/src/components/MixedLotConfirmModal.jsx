import { Layers, X, AlertTriangle } from "lucide-react";
import { formatQty } from "../utils/formatters";

/**
 * Dialog konfirmasi pemenuhan lintas-lot (Mixed-Lot Confirmation).
 * Muncul saat allocation policy = prefer_single tapi qty harus diambil dari >1 lot.
 * Backend juga menggerbang via 409 MIXED_LOT_CONFIRMATION_REQUIRED (defense-in-depth).
 */
export function MixedLotConfirmModal({ open, lines = [], policy = {}, onCancel, onConfirm }) {
  if (!open) return null;
  return (
    <div
      data-testid="mixed-lot-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onCancel}
    >
      <div className="w-full max-w-md rounded-lg bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-[#6B219A]" />
            <h3 className="text-[13px] font-bold text-[#1C1C1E]">Konfirmasi Pemenuhan Lintas-Lot</h3>
          </div>
          <button className="icon-button" onClick={onCancel} aria-label="Tutup"><X size={14} /></button>
        </div>
        <div className="max-h-[60vh] space-y-2.5 overflow-y-auto px-4 py-3">
          <div className="flex items-start gap-2 rounded-md border border-[#F0E2D0] bg-[#FFF8EF] p-2.5">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[#8C4A00]" />
            <p className="text-[11.5px] text-[#8C4A00]">
              Sebagian item tidak dapat dipenuhi dari satu lot tunggal. Sistem akan menggabungkan beberapa lot (mixed lot) — warna/dye-lot bisa berbeda. Lanjutkan?
            </p>
          </div>
          {lines.map((l) => (
            <div key={l.product_id} data-testid={`mixed-lot-line-${l.product_id}`} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
              <p className="text-[12px] font-semibold text-[#1C1C1E]">{l.product_name}</p>
              <p className="mt-0.5 text-[10.5px] text-[#6B6B73]">
                Lot: <span className="font-semibold text-[#6B219A]">{(l.lots_used || []).join(" + ") || "—"}</span>
                {" · "}Terpenuhi {formatQty(l.reserved_qty)}
                {Number(l.backorder_qty) > 0 ? ` · Backorder ${formatQty(l.backorder_qty)}` : ""}
              </p>
              {l.explanation && <p className="mt-0.5 text-[10px] italic text-[#8E8E93]">{l.explanation}</p>}
            </div>
          ))}
          {policy?.lot_selection && (
            <p className="text-[10px] text-[#8E8E93]">Kebijakan: {String(policy.lot_selection).toUpperCase()} · {policy.lot_mode}</p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button data-testid="mixed-lot-cancel" className="secondary-button" onClick={onCancel}>Batal</button>
          <button data-testid="mixed-lot-confirm" className="primary-button" onClick={onConfirm}>
            <Layers size={13} /> Konfirmasi & Buat Pesanan
          </button>
        </div>
      </div>
    </div>
  );
}
