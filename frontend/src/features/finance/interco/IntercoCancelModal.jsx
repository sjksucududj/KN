/**
 * FASE G-6 — **BATALKAN TRANSAKSI ANTAR-PT** (wajib ber-alasan).
 *
 * Kenapa ada layar sendiri: transaksi yang sudah dikonfirmasi punya jurnal di DUA
 * buku. Membatalkannya berarti **menerbitkan jurnal pembalik** — dan itu tidak
 * boleh terjadi tanpa sebab yang tercatat (pola G-1: koreksi ber-alasan).
 */
import { useState } from "react";
import { X, Undo2, AlertTriangle } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { apiErrorText } from "../../../utils/apiError";
import { formatCurrency } from "../../../utils/formatters";

export default function IntercoCancelModal({ doc, onClose, onCancelled }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (!doc) return null;

  const perluAlasan = doc.status !== "draft";
  const kurang = perluAlasan && reason.trim().length < 5;

  const submit = async () => {
    setBusy(true); setErr("");
    try {
      const r = await axios.post(
        `${API}/interco/transactions/${doc.id}/cancel`, { note: reason.trim() });
      onCancelled?.(r.data);
    } catch (e) {
      setErr(apiErrorText(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
         data-testid="interco-cancel-modal">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg">
        <div className="flex items-start justify-between px-6 py-4 border-b border-[#E5E5EA]">
          <div className="flex items-start gap-3">
            <Undo2 size={18} className="text-[#C0392B] mt-0.5" />
            <div>
              <h2 className="text-base font-semibold text-[#1D1D1F]">
                Batalkan Transaksi Antar-PT
              </h2>
              <p className="text-xs text-[#6E6E73] mt-0.5">
                {doc.number} · {formatCurrency(doc.grand_total)}
              </p>
            </div>
          </div>
          <button onClick={onClose} data-testid="interco-cancel-close"
                  className="p-1.5 hover:bg-[#F2F2F5] rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-4 space-y-3">
          {perluAlasan && (
            <div className="flex items-start gap-2 rounded-lg bg-[#FFF7E6] border border-[#FFE1A8] px-3 py-2.5 text-[12px] text-[#8A5A00]">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>
                Transaksi ini sudah dikonfirmasi, jadi jurnalnya akan <b>dibalik di kedua
                buku PT</b> (pendapatan, piutang &amp; utang antar-PT kembali nol) dan
                entri eliminasi grup ikut dihapus. Alasan wajib dicatat.
              </span>
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-[#3C3C43] mb-1">
              Alasan pembatalan {perluAlasan && <span className="text-[#C0392B]">*</span>}
            </label>
            <textarea
              data-testid="interco-cancel-reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Contoh: salah PT pembeli — diterbitkan ulang ke CV Kanda"
              className="w-full rounded-lg border border-[#E5E5EA] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#0058CC]/30"
            />
            {kurang && (
              <p className="text-[11px] text-[#C0392B] mt-1">
                Minimal 5 huruf supaya jejak koreksinya berguna saat diaudit.
              </p>
            )}
          </div>
          {err && (
            <div data-testid="interco-cancel-error"
                 className="rounded-lg bg-[#FDEDE7] border border-[#F7C3B4] text-[#9B1C1C] text-[12px] px-3 py-2">
              {err}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-[#E5E5EA]">
          <button onClick={onClose} data-testid="interco-cancel-abort"
                  className="px-3.5 py-2 text-sm rounded-lg border border-[#E5E5EA] text-[#3C3C43] hover:bg-[#F2F2F5]">
            Tidak, kembali
          </button>
          <button
            onClick={submit}
            disabled={busy || kurang}
            data-testid="interco-cancel-submit"
            className="px-3.5 py-2 text-sm rounded-lg bg-[#C0392B] text-white hover:bg-[#A93226] disabled:opacity-50"
          >
            {busy ? "Membatalkan…" : "Batalkan & Balik Jurnal"}
          </button>
        </div>
      </div>
    </div>
  );
}
