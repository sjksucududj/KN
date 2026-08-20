/**
 * FASE G-6b — Modal **FAKTUR PAJAK INTERNAL** untuk transaksi antar-PT ber-PPN.
 *
 * Kenapa layar ini ada: PPN antar-PT sudah benar di jurnal, tetapi tiap PT tetap
 * butuh DOKUMEN pajaknya sendiri (keluaran di penjual, masukan di pembeli) supaya
 * rekap PPN kurang/lebih bayar di Pusat Pajak jujur. Modal ini menampilkan angka
 * bersih (sesudah retur), alasan bila tombol belum boleh ditekan, dan jalur
 * **Faktur Pengganti** ketika angkanya berubah — dokumen terbit tidak pernah diedit.
 */
import { useCallback, useEffect, useState } from "react";
import { X, Receipt, FileCheck2, AlertTriangle, RefreshCw, Ban } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency } from "../../../utils/formatters";
import { apiErrorText } from "../../../utils/apiError";
import { fmtDate } from "./intercoApi";

export default function IntercoTaxModal({ doc, onClose, onDone }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [nsfp, setNsfp] = useState("");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState("");   // "" | "replace" | "cancel"

  const load = useCallback(async () => {
    setBusy(true); setErr("");
    try {
      const r = await axios.get(`${API}/interco/transactions/${doc.id}/tax-invoice`);
      setState(r.data);
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  }, [doc.id]);

  useEffect(() => { load(); }, [load]);

  /** Kirim aksi faktur pajak internal.
   *
   * Path ditulis LITERAL per aksi (bukan `...tax-invoice${path}`) supaya gate
   * `verify_api_contract` CHECK B bisa mencocokkannya ke route backend — path
   * dinamis membuat kontrak FE↔BE tidak bisa diverifikasi otomatis.
   */
  const act = async (action, body) => {
    setBusy(true); setErr("");
    const base = `${API}/interco/transactions/${doc.id}`;
    try {
      if (action === "replace") await axios.post(`${base}/tax-invoice/replace`, body);
      else if (action === "cancel") await axios.post(`${base}/tax-invoice/cancel`, body);
      else await axios.post(`${base}/tax-invoice`, body);
      setMode(""); setReason("");
      await load();
      onDone?.();
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  };

  const out = state?.out;
  const inn = state?.in;

  return (
    <div className="fixed inset-0 z-50 bg-[rgba(15,23,42,0.45)] flex items-center justify-center p-4"
         data-testid="interco-tax-modal"
         onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E5E5EA] flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[#1D1D1F] flex items-center gap-2">
              <Receipt size={17} /> Faktur Pajak Internal
            </h2>
            <p className="text-xs text-[#6E6E73] mt-0.5">
              {doc.number} · {state?.seller_entity_name} → {state?.buyer_entity_name}
              {state?.tax_apply ? ` · PPN ${state.tax_rate}%` : " · tanpa PPN"}
            </p>
          </div>
          <button onClick={onClose} data-testid="interco-tax-close"
                  className="p-1.5 rounded-md text-[#6E6E73] hover:bg-[#F2F2F5]" aria-label="Tutup">
            <X size={17} />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4 max-h-[70vh] overflow-y-auto">
          {err && <ErrorNotice message={err} onDismiss={() => setErr("")} />}

          <div className="grid grid-cols-3 gap-3">
            <Box label="DPP bersih" value={formatCurrency(state?.net_dpp || 0)} testid="interco-tax-dpp" />
            <Box label="PPN bersih" value={formatCurrency(state?.net_ppn || 0)} testid="interco-tax-ppn" />
            <Box label="Total" value={formatCurrency(state?.net_total || 0)} testid="interco-tax-total" />
          </div>

          {state?.blocked_reason && (
            <div className="flex items-start gap-2 rounded-lg bg-[#FFF4E5] px-3 py-2.5 text-[13px] text-[#8A5300]"
                 data-testid="interco-tax-blocked">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <span>{state.blocked_reason}</span>
            </div>
          )}

          {state?.needs_replacement && (
            <div className="flex items-start gap-2 rounded-lg bg-[#FDEDE7] px-3 py-2.5 text-[13px] text-[#9B1C1C]"
                 data-testid="interco-tax-needs-replacement">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <span>
                Angka faktur yang sudah terbit <b>tidak lagi sama</b> dengan nilai bersih
                transaksi (ada retur sesudah faktur terbit). Terbitkan <b>Faktur Pengganti</b>
                {" "}— dokumen pajak yang sudah terbit tidak boleh diubah diam-diam.
              </span>
            </div>
          )}

          {(out || inn) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="interco-tax-docs">
              <FakturCard title="Faktur Pajak Keluaran (penjual)" doc={out}
                          testid="interco-tax-out" />
              <FakturCard title="Faktur Pajak Masukan (pembeli)" doc={inn}
                          testid="interco-tax-in" />
            </div>
          )}

          {!out && !state?.blocked_reason && (
            <div className="rounded-lg border border-[#E5E5EA] bg-[#FAFBFC] p-3 space-y-2">
              <label className="block text-xs font-medium text-[#3C3C43]">
                NSFP resmi DJP (opsional — boleh diisi menyusul)
              </label>
              <input
                value={nsfp}
                onChange={(e) => setNsfp(e.target.value)}
                placeholder="mis. 010.000-26.00000001"
                data-testid="interco-tax-nsfp-input"
                className="w-full rounded-lg border border-[#E5E5EA] bg-white px-3 py-2 text-sm text-[#1D1D1F]"
              />
              <p className="text-[11px] text-[#8E8E93]">
                Tanpa NSFP, faktur tetap terbit dengan nomor internal — nomor seri resmi
                bisa ditambahkan setelah alokasi dari Coretax/e-Faktur.
              </p>
            </div>
          )}

          {mode && (
            <div className="rounded-lg border border-[#E5E5EA] bg-[#FAFBFC] p-3 space-y-2">
              <label className="block text-xs font-medium text-[#3C3C43]">
                Alasan {mode === "replace" ? "penggantian" : "pembatalan"} (wajib, minimal 5 huruf)
              </label>
              <textarea
                value={reason} rows={2}
                onChange={(e) => setReason(e.target.value)}
                data-testid="interco-tax-reason-input"
                className="w-full rounded-lg border border-[#E5E5EA] bg-white px-3 py-2 text-sm text-[#1D1D1F]"
                placeholder="mis. ada retur sebagian sesudah faktur terbit"
              />
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-[#E5E5EA] flex flex-wrap items-center justify-end gap-2 bg-[#FAFBFC]">
          <button onClick={onClose} data-testid="interco-tax-cancel-btn"
                  className="px-3.5 py-2 text-sm rounded-lg border border-[#E5E5EA] bg-white text-[#3C3C43] hover:bg-[#F2F2F5]">
            Tutup
          </button>
          {out && !mode && (
            <>
              <button onClick={() => setMode("cancel")} disabled={busy}
                      data-testid="interco-tax-open-cancel"
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm rounded-lg border border-[#F2C9BE] bg-white text-[#C0392B] hover:bg-[#FDEDE7]">
                <Ban size={14} /> Batalkan Faktur
              </button>
              <button onClick={() => setMode("replace")} disabled={busy}
                      data-testid="interco-tax-open-replace"
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm rounded-lg border border-[#0058CC] bg-white text-[#0058CC] hover:bg-[#EAF2FF]">
                <RefreshCw size={14} /> Faktur Pengganti
              </button>
            </>
          )}
          {mode && (
            <button
              onClick={() => act(mode === "replace" ? "replace" : "cancel", { reason })}
              disabled={busy || reason.trim().length < 5}
              data-testid="interco-tax-confirm-reason"
              className="px-3.5 py-2 text-sm rounded-lg bg-[#0F172A] text-white hover:bg-black disabled:opacity-40">
              {busy ? "Memproses…" : mode === "replace" ? "Terbitkan Pengganti" : "Batalkan Faktur"}
            </button>
          )}
          {state?.can_issue && !mode && (
            <button onClick={() => act("", { nsfp, kode_transaksi: "01" })} disabled={busy}
                    data-testid="interco-tax-issue-btn"
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm rounded-lg bg-[#0F172A] text-white hover:bg-black disabled:opacity-40">
              <FileCheck2 size={14} /> {busy ? "Menerbitkan…" : "Terbitkan Faktur Pajak"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Box({ label, value, testid }) {
  return (
    <div className="rounded-lg border border-[#E5E5EA] bg-white p-3" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-wide text-[#8E8E93]">{label}</div>
      <div className="mt-1 text-[15px] font-semibold text-[#1D1D1F] tabular-nums">{value}</div>
    </div>
  );
}

function FakturCard({ title, doc, testid }) {
  const STATUS_ID = {
    normal: "Normal", pengganti: "Pengganti", batal: "Dibatalkan",
    recorded: "Tercatat", cancelled: "Dibatalkan",
  };
  return (
    <div className="rounded-lg border border-[#E5E5EA] bg-white overflow-hidden" data-testid={testid}>
      <div className="px-3 py-2 bg-[#F7F7F9] text-xs font-medium text-[#3C3C43]">{title}</div>
      <div className="p-3 space-y-1 text-[13px]">
        {doc ? (
          <>
            <div className="font-semibold text-[#1D1D1F]">{doc.number}</div>
            <div className="text-[#6E6E73]">Tanggal {fmtDate(doc.faktur_date)}</div>
            <div className="text-[#6E6E73]">
              DPP {formatCurrency(doc.dpp)} · PPN {formatCurrency(doc.ppn_amount)}
            </div>
            <div className="text-[#6E6E73]">NSFP: {doc.nsfp || "belum diisi"}</div>
            <span className="inline-flex mt-1 px-2 py-0.5 rounded text-[11px] bg-[#EAF2FF] text-[#0058CC]">
              {STATUS_ID[doc.status] || doc.status}
            </span>
          </>
        ) : (
          <span className="text-[#8E8E93]">Belum diterbitkan.</span>
        )}
      </div>
    </div>
  );
}
