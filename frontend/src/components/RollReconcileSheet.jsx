import { useEffect, useState } from "react";
import axios, { API } from "../services/apiClient";
import { X, ArrowUp, ArrowDown, Scissors, Check, Loader2, AlertTriangle, Layers } from "lucide-react";
import { formatCurrency, formatQty } from "../utils/formatters";

const META = {
  exact_whole: { label: "Pas (roll utuh)", icon: Layers, tone: "#126E2C", bg: "#E7F6EC", desc: "Kebetulan kombinasi roll utuh pas dengan permintaan." },
  round_up:    { label: "Genapkan ke atas", icon: ArrowUp, tone: "#0058CC", bg: "#EAF2FF", desc: "Tambah roll — qty & harga naik." },
  round_down:  { label: "Genapkan ke bawah", icon: ArrowDown, tone: "#9A5B00", bg: "#FFF6E9", desc: "Kurangi roll — qty & harga turun." },
  exact_cut:   { label: "Potong roll (pas)", icon: Scissors, tone: "#A8221A", bg: "#FBEAE8", desc: "Opsi terakhir — potong sebagian 1 roll agar pas. Minimalkan." },
  take_all:    { label: "Ambil semua + backorder", icon: AlertTriangle, tone: "#A8221A", bg: "#FBEAE8", desc: "Stok roll kurang dari permintaan." },
};
const ORDER = ["exact_whole", "round_up", "round_down", "exact_cut", "take_all"];

/**
 * RollReconcileSheet — SALES REVAMP V2 (C2). Genapkan pesanan per-yard ke roll utuh.
 * Tampilkan opsi genapkan ke atas/bawah + potong (opsi terakhir). onConfirm(rollLines, totalQty, snapshot, key).
 */
export default function RollReconcileSheet({ open, productId, entityId, targetQty, unitPrice = 0, baseUnit = "meter", onConfirm, onClose }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);
  const [pick, setPick] = useState("");

  useEffect(() => {
    if (!open || !productId) return;
    let cancel = false;
    setLoading(true); setError(""); setData(null); setPick("");
    const eff = entityId && entityId !== "all" ? entityId : "";
    axios.post(`${API}/sales-orders/preview-roll-reconcile`, {
      items: [{ product_id: productId, quantity: Number(targetQty) }],
      entity_id: eff, all_entities: true,
    }).then((r) => {
      if (cancel) return;
      const rec = (r.data || [])[0] || null;
      setData(rec);
      // default pilihan: exact_whole > round_up
      if (rec?.options) {
        const def = rec.options.exact_whole ? "exact_whole" : (rec.options.round_up ? "round_up" : (rec.options.take_all ? "take_all" : Object.keys(rec.options)[0]));
        setPick(def || "");
      }
    }).catch((e) => { if (!cancel) setError(e.response?.data?.detail || "Gagal menghitung opsi roll."); })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [open, productId, targetQty, entityId]);

  if (!open) return null;
  const options = data?.options || {};
  const keys = ORDER.filter((k) => options[k]);
  const chosen = options[pick];

  const confirm = () => {
    if (!chosen) return;
    onConfirm?.(chosen.roll_lines || [], Number(chosen.total_qty || 0), chosen.snapshot || [], pick);
  };

  return (
    <div className="fixed inset-0 z-[150] flex items-end justify-center sm:items-center" data-testid="roll-reconcile-sheet">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl">
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <div>
            <h3 className="text-[14px] font-bold text-[#1C1C1E]">Genapkan ke Roll Utuh</h3>
            <p className="text-[11px] text-[#6B6B73]">Diminta <b className="tabular-nums">{formatQty(targetQty)} {baseUnit}</b> — pilih pembulatan roll.</p>
          </div>
          <button data-testid="reconcile-close" onClick={onClose} className="text-[#6B6B73]" aria-label="Tutup"><X size={18} /></button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto px-4 py-3">
          {loading && <div data-testid="reconcile-loading" className="flex items-center justify-center gap-2 py-8 text-[12px] text-[#6B6B73]"><Loader2 size={15} className="animate-spin" /> Menghitung opsi roll…</div>}
          {error && <div data-testid="reconcile-error" className="py-6 text-center text-[12px] text-[#C0392B]">{error}</div>}
          {!loading && !error && keys.length === 0 && <div data-testid="reconcile-empty" className="py-6 text-center text-[12px] text-[#8E8E93]">Tidak ada roll tersedia untuk produk ini.</div>}

          {!loading && !error && keys.map((k) => {
            const opt = options[k]; const m = META[k]; const Icon = m.icon; const on = pick === k;
            const subtotal = Math.round(Number(opt.total_qty || 0) * unitPrice * 100) / 100;
            return (
              <button key={k} type="button" data-testid={`reconcile-option-${k}`} onClick={() => setPick(k)}
                className={`mb-2 block w-full rounded-lg border px-3 py-2.5 text-left transition ${on ? "border-[#0058CC] ring-1 ring-[#0058CC]" : "border-[#E5E5EA] hover:border-[#9A9BA3]"}`}>
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full" style={{ background: m.bg, color: m.tone }}><Icon size={13} /></span>
                  <span className="text-[12.5px] font-bold text-[#1C1C1E]">{m.label}</span>
                  {k === "exact_cut" && <span className="rounded-full bg-[#FBEAE8] px-1.5 py-0.5 text-[9px] font-bold text-[#A8221A]">opsi terakhir</span>}
                  <span className="ml-auto text-right">
                    <span className="block text-[13px] font-bold tabular-nums" style={{ color: m.tone }}>{formatQty(opt.total_qty)} {baseUnit}</span>
                    {typeof opt.delta === "number" && Math.abs(opt.delta) > 0.01 && (
                      <span className="block text-[10px] tabular-nums text-[#8E8E93]">{opt.delta > 0 ? "+" : ""}{formatQty(opt.delta)} vs minta</span>
                    )}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between pl-8">
                  <span className="text-[10.5px] text-[#6B6B73]">{opt.roll_count} roll{k === "exact_cut" ? ` · potong ${formatQty(opt.cut_qty)} dari ${opt.cut_roll_no}` : ""}{k === "take_all" ? ` · backorder ${formatQty(opt.backorder_qty)}` : ""}</span>
                  <span className="text-[11.5px] font-semibold tabular-nums text-[#1C1C1E]">{formatCurrency(subtotal)}</span>
                </div>
                {/* roll chips */}
                <div className="mt-1.5 flex flex-wrap gap-1 pl-8">
                  {(opt.snapshot || []).slice(0, 8).map((r) => (
                    <span key={r.roll_id} className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[9px] ${r.cut ? "bg-[#FBEAE8] text-[#A8221A]" : r.is_cross_entity ? "bg-[#FFF3E0] text-[#9A5B00]" : "bg-[#EEF1F4] text-[#3C3C43]"}`}>
                      {r.roll_no}{r.cut ? ` (potong ${formatQty(r.length)})` : ` ${formatQty(r.length)}`}{r.is_cross_entity ? " ⇄" : ""}
                    </span>
                  ))}
                  {(opt.snapshot || []).length > 8 && <span className="text-[9px] text-[#8E8E93]">+{opt.snapshot.length - 8} lagi</span>}
                </div>
              </button>
            );
          })}
        </div>

        <div className="border-t border-[#EFF0F2] px-4 py-3">
          <button data-testid="reconcile-confirm" disabled={!chosen} onClick={confirm} className="primary-button w-full justify-center py-2.5 disabled:opacity-50">
            <Check size={15} /> Pakai Opsi Ini
          </button>
        </div>
      </div>
    </div>
  );
}
