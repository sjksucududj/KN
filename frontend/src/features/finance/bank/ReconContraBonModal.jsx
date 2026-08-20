/**
 * FASE G-7 ↔ G-8 · US8 — **bayar kontrabon dari baris mutasi bank**.
 *
 * Alurnya sengaja dibalik dari kebiasaan: petugas melihat uang KELUAR di rekening,
 * lalu menunjuk kontrabon mana yang dilunasinya. Sistem membuat transaksi kasnya,
 * membayar kontrabon, lalu MENAUTKAN barisnya — rekonsiliasi langsung beres tanpa
 * pindah layar. Kandidat diurutkan: nominal tepat lebih dulu.
 *
 * INV-UI-03 aturan C: modal ini menulis lewat axios, jadi punya bilah error sendiri.
 */
import { useCallback, useEffect, useState } from "react";
import { X, RefreshCw, Receipt, CheckCircle2 } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import ErrorNotice from "../../../components/ErrorNotice";
import { apiErrorText } from "../../../utils/apiError";

const fmtDate = (s) => {
  if (!s) return "—";
  try {
    return new Date(String(s).length <= 10 ? `${s}T00:00:00` : s)
      .toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return s; }
};

export default function ReconContraBonModal({ line, onClose, onDone, onError }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("load");
  const [mErr, setMErr] = useState("");

  const load = useCallback(async () => {
    setBusy("load");
    try {
      const r = await axios.get(`${API}/contra-bons/bank-line-candidates/${line.id}`);
      setData(r.data);
      setMErr("");
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); } finally { setBusy(""); }
  }, [line.id, onError]);

  useEffect(() => { load(); }, [load]);

  async function pay(cb) {
    setBusy(cb.id);
    try {
      const r = await axios.post(`${API}/contra-bons/${cb.id}/pay-from-bank-line/${line.id}`, {
        note: "Dibayar dari baris mutasi bank",
      });
      const updated = r.data || {};
      onDone(`Kontrabon ${updated.number || cb.number} dibayar `
        + `${formatCurrency(line.amount)} dan baris mutasi ini otomatis tertaut ke transaksi kasnya`
        + (updated.status === "paid" ? " — kontrabon LUNAS." : "."));
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); } finally { setBusy(""); }
  }

  const cands = data?.candidates || [];

  return (
    <div className="modal-overlay" data-testid="recon-contrabon-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card wide">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="modal-title flex items-center gap-1.5">
            <Receipt size={15} /> Bayar kontrabon dari mutasi ini
          </h3>
          <button className="icon-button" data-testid="recon-contrabon-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        {mErr && (
          <ErrorNotice message={mErr} onRetry={load} onDismiss={() => setMErr("")}
            testId="recon-contrabon-error" />
        )}
        <p className="modal-subtitle">
          {fmtDate(line.stmt_date)} · dana keluar <b>{formatCurrency(line.amount)}</b> —{" "}
          {line.description || "tanpa keterangan"}
        </p>
        <p className="mt-1 text-[11px] text-[#8E8E93]">
          Hanya kontrabon yang sudah <b>disetujui</b> atau <b>dijadwalkan bayar</b> dan masih
          punya sisa yang bisa dilunasi dari sini.
        </p>

        <div className="mt-2 max-h-[340px] overflow-auto rounded border border-[#EFF0F2]">
          {busy === "load"
            ? (
              <div className="p-4 text-center text-[12px] text-[#8E8E93]">
                <RefreshCw size={14} className="spin inline" /> Mencari kontrabon yang pantas…
              </div>
            )
            : cands.length === 0
              ? (
                <div className="p-4 text-center text-[12px] text-[#8E8E93]"
                  data-testid="recon-contrabon-empty">
                  Tidak ada kontrabon yang siap dibayar. Setujui kontrabonnya lebih dulu di
                  Pembelian → Hutang Supplier → Kontrabon.
                </div>
              )
              : cands.map((c) => (
                <div key={c.id} data-testid={`recon-cb-cand-${c.id}`}
                  className="border-b border-[#F5F5F7] px-3 py-2 last:border-0">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-[12px]">
                        <b>{c.number}</b> · {c.supplier_name}{" "}
                        <span className="text-[#8E8E93]">({c.bills_count} faktur)</span>
                      </p>
                      <p className="text-[10px] text-[#8E8E93]">
                        {c.status_label} · sisa {formatCurrency(c.outstanding)}
                        {c.planned_payment_date ? ` · rencana ${fmtDate(c.planned_payment_date)}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        c.exact ? "bg-[#EAF7EE] text-[#1B7F4B]" : "bg-[#FFF4E5] text-[#B26A00]"}`}>
                        {c.exact ? "nominal tepat" : `selisih ${formatCurrency(c.amount_diff)}`}
                      </span>
                      <button data-testid={`recon-cb-pay-${c.id}`} className="primary-button"
                        disabled={!!busy} onClick={() => pay(c)}>
                        {busy === c.id
                          ? <RefreshCw size={13} className="spin" />
                          : <CheckCircle2 size={13} />}
                        Bayar & tautkan
                      </button>
                    </div>
                  </div>
                </div>
              ))}
        </div>
      </div>
    </div>
  );
}
