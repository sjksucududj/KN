import { useEffect, useState } from "react";
import { Anchor, X } from "lucide-react";
import KNSelect from "./KNSelect";
import { overlayDismiss } from "@/utils/overlayDismiss";

/**
 * Dialog Pegging/Earmark satu roll ke customer (KN_15 — soft hold).
 * Customer dibatasi ke entitas pemilik roll (owner-scoped D3).
 */
export function PeggingModal({ roll, customers = [], onCancel, onConfirm }) {
  const [customerId, setCustomerId] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { setCustomerId(""); setNote(""); setErr(""); setBusy(false); }, [roll?.id]);
  if (!roll) return null;

  const eligible = customers.filter((c) => !roll.owner_entity_id || c.entity_id === roll.owner_entity_id);

  const submit = async () => {
    if (!customerId) { setErr("Pilih customer untuk pegging."); return; }
    setBusy(true); setErr("");
    try {
      await onConfirm(customerId, note);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Gagal pegging roll.");
      setBusy(false);
    }
  };

  return (
    <div data-testid="pegging-modal" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" {...overlayDismiss(onCancel)}>
      <div className="w-full max-w-md rounded-lg bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <div className="flex items-center gap-2">
            <Anchor size={16} className="text-[#6B219A]" />
            <h3 className="text-[13px] font-bold text-[#1C1C1E]">Pegging Roll {roll.roll_no}</h3>
          </div>
          <button className="icon-button" onClick={onCancel} aria-label="Tutup"><X size={14} /></button>
        </div>
        <div className="space-y-3 px-4 py-3">
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5 text-[11px] text-[#3C3C43]">
            <p><span className="text-[#8E8E93]">Produk:</span> <span className="font-semibold">{roll.product_name}</span> ({roll.sku})</p>
            <p><span className="text-[#8E8E93]">Lot:</span> <span className="font-mono">{roll.lot}</span> · <span className="text-[#8E8E93]">Gudang:</span> {roll.warehouse_name} · <span className="text-[#8E8E93]">Pemilik:</span> {roll.owner_entity_name}</p>
            <p><span className="text-[#8E8E93]">Sisa:</span> <span className="font-bold tabular-nums">{roll.length_remaining} {roll.unit}</span></p>
          </div>
          <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
            Pelanggan (entitas {roll.owner_entity_name})
            <KNSelect data-testid="pegging-customer-select" className="field" value={customerId} onValueChange={setCustomerId}
              placeholder="— Pilih Pelanggan —"
              options={[{ value: "", label: "— Pilih Pelanggan —" }, ...eligible.map(c => ({ value: c.id, label: c.name }))]}
            />
          </label>
          {eligible.length === 0 && <p className="text-[10.5px] text-[#A8221A]">Tidak ada pelanggan untuk entitas pemilik roll ini.</p>}
          <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
            Catatan (opsional)
            <input data-testid="pegging-note-input" className="field" placeholder="cth: tahan untuk PO besar" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          {err && <p data-testid="pegging-error" className="text-[11px] font-semibold text-[#A8221A]">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button data-testid="pegging-cancel" className="secondary-button" onClick={onCancel}>Batal</button>
          <button data-testid="pegging-confirm" className="primary-button" disabled={busy || !customerId} onClick={submit}>
            <Anchor size={13} /> {busy ? "Memproses…" : "Peg ke Customer"}
          </button>
        </div>
      </div>
    </div>
  );
}
