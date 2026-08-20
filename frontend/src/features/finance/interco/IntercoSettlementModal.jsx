/**
 * FASE G-6 — Wizard **SETTLEMENT / NETTING** (US6).
 *
 * Pola kontrabon G-7: satu dokumen menutup banyak transaksi. Pilih PT pembayar
 * & penerima, lalu centang transaksi terbuka yang mau dilunasi. Metode `netting`
 * (bawaan) tidak menggerakkan kas — hanya saling hapus IC-AR/IC-AP.
 */
import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { KNSelect } from "../../../components/KNSelect";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency } from "../../../utils/formatters";
import { apiErrorText } from "../../../utils/apiError";
import { SETTLEMENT_METHODS, fmtDate } from "./intercoApi";

const OPEN_STATUSES = ["confirmed", "shipped", "received", "invoiced"];

export default function IntercoSettlementModal({
  entities = [], transactions = [], presetPayerEntityId = "", presetPayeeEntityId = "",
  onClose, onCreated,
}) {
  const [payer, setPayer] = useState(presetPayerEntityId);
  const [payee, setPayee] = useState(presetPayeeEntityId);
  const [method, setMethod] = useState("netting");
  const [selected, setSelected] = useState({});   // {id: appliedAmount}
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const entOptions = entities.map((e) => ({
    value: e.id,
    label: e.short_name || e.legal_name || e.name || e.id,
  }));

  // Kandidat: transaksi terbuka dengan penjual=payee & pembeli=payer, role=seller.
  const candidates = useMemo(() => {
    if (!payer || !payee) return [];
    return transactions.filter(
      (r) => r.role === "seller"
          && r.seller_entity_id === payee
          && r.buyer_entity_id === payer
          && OPEN_STATUSES.includes(r.status)
          && (r.grand_total - (r.settled_amount || 0) > 0.01)
    );
  }, [transactions, payer, payee]);

  const toggle = (r) => {
    setSelected((prev) => {
      const nxt = { ...prev };
      if (r.id in nxt) delete nxt[r.id];
      else nxt[r.id] = (r.grand_total - (r.settled_amount || 0)).toFixed(2);
      return nxt;
    });
  };

  const total = Object.values(selected).reduce((s, v) => s + (parseFloat(v) || 0), 0);

  const submit = async () => {
    setErr("");
    if (!payer || !payee) { setErr("Pilih PT pembayar & penerima."); return; }
    if (payer === payee) { setErr("PT pembayar & penerima harus berbeda."); return; }
    const picks = Object.entries(selected)
      .filter(([, v]) => parseFloat(v) > 0)
      .map(([id, v]) => ({ interco_id: id, applied_amount: parseFloat(v) }));
    if (picks.length === 0) {
      setErr("Pilih minimal satu transaksi untuk dilunaskan.");
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/interco/settlements`, {
        payer_entity_id: payer,
        payee_entity_id: payee,
        transactions: picks,
        method,
        notes,
      });
      onCreated?.();
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="interco-settle-modal">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5E5EA]">
          <div>
            <h2 className="text-lg font-semibold text-[#1D1D1F]">Settlement Antar-PT</h2>
            <p className="text-xs text-[#6E6E73] mt-0.5">
              Netting: satu dokumen menutup banyak transaksi tanpa uang. Untuk transfer
              nyata, ubah metode.
            </p>
          </div>
          <button onClick={onClose} data-testid="interco-settle-close" className="p-1.5 hover:bg-[#F2F2F5] rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {err && <ErrorNotice message={err} onDismiss={() => setErr("")} />}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-[#3C3C43] mb-1">PT Pembayar</label>
              <KNSelect value={payer} onChange={setPayer} options={entOptions} data-testid="interco-settle-payer" />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#3C3C43] mb-1">PT Penerima</label>
              <KNSelect value={payee} onChange={setPayee} options={entOptions} data-testid="interco-settle-payee" />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#3C3C43] mb-1">Metode</label>
              <KNSelect value={method} onChange={setMethod} options={SETTLEMENT_METHODS} data-testid="interco-settle-method" />
            </div>
          </div>

          <div className="rounded-xl border border-[#E5E5EA] overflow-hidden">
            <table className="w-full text-sm" data-testid="interco-settle-candidates">
              <thead className="bg-[#F7F7F9] text-[#3C3C43]">
                <tr>
                  <th className="text-left px-3 py-2 font-medium w-10"></th>
                  <th className="text-left px-3 py-2 font-medium">Nomor</th>
                  <th className="text-left px-3 py-2 font-medium">Tanggal</th>
                  <th className="text-right px-3 py-2 font-medium">Sisa</th>
                  <th className="text-right px-3 py-2 font-medium">Diterapkan</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#F2F2F5]">
                {candidates.length === 0 && (
                  <tr><td colSpan={5} className="px-3 py-8 text-center text-[#8E8E93]">
                    {payer && payee
                      ? "Tidak ada transaksi terbuka untuk pasangan PT ini."
                      : "Pilih PT pembayar & penerima dulu."}
                  </td></tr>
                )}
                {candidates.map((r) => {
                  const remaining = r.grand_total - (r.settled_amount || 0);
                  const checked = r.id in selected;
                  return (
                    <tr key={r.id} data-testid={`interco-settle-cand-${r.id}`} className="hover:bg-[#FAFAFB]">
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggle(r)}
                          data-testid={`interco-settle-check-${r.id}`}
                        />
                      </td>
                      <td className="px-3 py-2 font-medium text-[#1D1D1F]">{r.number}</td>
                      <td className="px-3 py-2">{fmtDate(r.doc_date)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(remaining)}</td>
                      <td className="px-3 py-2 text-right">
                        {checked ? (
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={selected[r.id]}
                            onChange={(e) => setSelected((p) => ({ ...p, [r.id]: e.target.value }))}
                            data-testid={`interco-settle-amount-${r.id}`}
                            className="w-28 text-right px-2 py-1 text-sm border border-[#E5E5EA] rounded"
                          />
                        ) : (
                          <span className="text-[#8E8E93]">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between p-3 rounded-lg bg-[#F7F7F9]">
            <div className="text-sm text-[#6E6E73]">
              {Object.keys(selected).length} transaksi dipilih
            </div>
            <div className="text-sm text-[#1D1D1F]">
              Total: <span className="font-semibold tabular-nums">{formatCurrency(total)}</span>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#3C3C43] mb-1">Catatan</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              data-testid="interco-settle-notes"
              className="w-full px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg focus:outline-none focus:border-[#0058CC]"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-[#E5E5EA] bg-[#FAFAFB]">
          <button onClick={onClose} data-testid="interco-settle-cancel" className="px-4 py-2 text-sm rounded-lg text-[#3C3C43] hover:bg-[#F2F2F5]">
            Batal
          </button>
          <button
            onClick={submit}
            disabled={busy || total <= 0}
            data-testid="interco-settle-submit"
            className="px-4 py-2 text-sm rounded-lg bg-[#0F172A] text-white hover:bg-black disabled:opacity-50"
          >
            {busy ? "Menerbitkan..." : "Terbitkan Settlement"}
          </button>
        </div>
      </div>
    </div>
  );
}
