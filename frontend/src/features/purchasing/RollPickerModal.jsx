/**
 * RollPickerModal (S#2026-07-21) — pilih roll/lot SPESIFIK untuk retur PRESISI.
 * Menampilkan roll available yang bisa diretur (difilter asal supplier/PO),
 * lengkap dengan lot, PO, no. invoice, sisa qty & harga.
 * Sumber: GET /api/purchase-returns/source-rolls
 */
import { useEffect, useState } from "react";
import { X, Check, Layers } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatQty } from "../../utils/formatters";

export default function RollPickerModal({
  open, productId, productLabel, supplierId, poId, warehouseId, entityId,
  initialSelected = [], onClose, onConfirm,
}) {
  const [rolls, setRolls] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState(new Set(initialSelected));

  useEffect(() => {
    if (!open || !productId) return;
    let alive = true;
    (async () => {
      setLoading(true); setErr("");
      try {
        const params = { product_id: productId };
        if (supplierId) params.supplier_id = supplierId;
        if (poId) params.po_id = poId;
        if (warehouseId) params.warehouse_id = warehouseId;
        if (entityId && entityId !== "all") params.entity_id = entityId;
        const r = await axios.get(`${API}/purchase-returns/source-rolls`, { params });
        if (alive) { setRolls(r.data?.rolls || []); setSel(new Set(initialSelected)); }
      } catch (e) {
        if (alive) setErr(e.response?.data?.detail || "Gagal memuat roll asal.");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [open, productId, supplierId, poId, warehouseId, entityId]); // eslint-disable-line

  if (!open) return null;

  const toggle = (id) => setSel((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });
  const selected = rolls.filter((r) => sel.has(r.roll_id));
  const totalQty = selected.reduce((a, r) => a + Number(r.qty_remaining || 0), 0);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4" data-testid="roll-picker-modal">
      <div className="w-full max-w-2xl rounded-xl bg-white shadow-xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <div className="flex items-center gap-2">
            <Layers size={15} className="text-[#6B219A]" />
            <h3 className="text-[13px] font-bold">Pilih Roll / Lot untuk Retur Presisi</h3>
          </div>
          <button className="icon-button" onClick={onClose} data-testid="roll-picker-close"><X size={15} /></button>
        </div>
        <p className="px-4 pt-2 text-[11px] text-[#6B6B73]">
          {productLabel || productId} · pilih roll spesifik yang akan diretur (harga & qty otomatis dari roll asal).
        </p>

        <div className="flex-1 overflow-y-auto px-4 py-2">
          {loading ? (
            <p className="py-8 text-center text-[12px] text-[#9A9BA3]">Memuat roll…</p>
          ) : err ? (
            <p className="py-8 text-center text-[12px] text-[#C0392B]">{err}</p>
          ) : rolls.length === 0 ? (
            <p className="py-8 text-center text-[12px] text-[#9A9BA3]" data-testid="roll-picker-empty">
              Tidak ada roll tersedia dari asal ini. Pastikan supplier/PO sesuai.
            </p>
          ) : (
            <div className="space-y-1.5">
              {rolls.map((r) => {
                const on = sel.has(r.roll_id);
                return (
                  <button
                    key={r.roll_id}
                    data-testid={`roll-pick-${r.roll_id}`}
                    onClick={() => toggle(r.roll_id)}
                    className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition ${on ? "border-[#6B219A] bg-[#FBF5FF]" : "border-[#EFF0F2] bg-white hover:bg-[#FAFBFC]"}`}
                  >
                    <span className={`flex h-4 w-4 items-center justify-center rounded border ${on ? "bg-[#6B219A] border-[#6B219A] text-white" : "border-[#C7C7CC]"}`}>
                      {on && <Check size={11} />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11.5px] font-bold text-[#6B219A]">{r.roll_no || r.roll_id}</span>
                        <span className="text-[10.5px] text-[#8E8E93]">Lot {r.lot || "—"}</span>
                        {r.grade && <span className="rounded bg-[#F0F0F2] px-1 text-[10px] text-[#6B6B73]">{r.grade}</span>}
                      </div>
                      <div className="text-[10.5px] text-[#8E8E93] truncate">
                        {r.po_number || "—"} · {r.supplier_invoice_no ? `Inv ${r.supplier_invoice_no}` : "belum ditagih"} · {r.supplier_name || "—"}
                      </div>
                    </div>
                    <span className="text-right tabular-nums text-[11.5px] font-semibold">{formatQty(r.qty_remaining)} {r.unit}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-[#EFF0F2] px-4 py-3">
          <span className="text-[11.5px] text-[#3C3C43]" data-testid="roll-picker-summary">
            {selected.length} roll dipilih · total <b className="tabular-nums">{formatQty(totalQty)}</b>
          </span>
          <div className="flex gap-2">
            <button className="secondary-button" onClick={onClose}>Batal</button>
            <button
              data-testid="roll-picker-confirm"
              className="primary-button"
              onClick={() => onConfirm(selected)}
            >
              Gunakan {selected.length} Roll
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
