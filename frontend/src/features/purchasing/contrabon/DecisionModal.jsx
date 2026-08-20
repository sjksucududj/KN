/**
 * FASE G-7 · US4 — modal **KEPUTUSAN SELISIH 3-WAY** (INV-CB-03).
 *
 * Selisih di luar toleransi tidak boleh "lewat begitu saja": setiap selisih wajib
 * diputus berlabel — diterima, dipotong, atau disengketakan — sebelum kontrabon
 * bisa diverifikasi. Tindakan & label alasan datang dari backend (`meta`) supaya
 * layar tidak pernah menawarkan keputusan yang tidak ada mesinnya.
 */
import { useMemo, useState } from "react";
import { X, Scale, Info } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { formatCurrency } from "../../../utils/formatters";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";
import { EXCEPTION_TYPE_LABEL } from "./contraBonApi";

export default function DecisionModal({ cb, exception, meta, onClose, onSaved, onError }) {
  const actions = meta?.exception_actions || [];
  const reasons = meta?.reasons || [];
  const [action, setAction] = useState(actions[0]?.action || "accept");
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState(String(exception?.amount ?? ""));
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const spec = useMemo(() => actions.find((a) => a.action === action) || null, [actions, action]);
  const reasonOptions = useMemo(
    () => reasons.map((r) => ({ value: r.code, label: r.label })), [reasons]);

  async function save() {
    setSaving(true); setErr("");
    try {
      const r = await axios.post(`${API}/contra-bons/${cb.id}/decide`, {
        exception_key: exception.key,
        action,
        reason_code: reason,
        amount: amount === "" ? null : Number(amount),
        note: note.trim(),
      });
      onSaved(r.data, action);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" data-testid="cb-decision-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card wide">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="modal-title flex items-center gap-1.5">
            <Scale size={15} /> Putuskan selisih 3-way match
          </h3>
          <button className="icon-button" data-testid="cb-decision-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        <p className="modal-subtitle">
          {cb.number} · {exception?.bill_number} — {exception?.product_name}
        </p>

        {err && (
          <ErrorNotice message={err} onDismiss={() => setErr("")} testId="cb-decision-error" />
        )}

        <div className="mt-3 rounded-lg border border-[#FFE0B2] bg-[#FFFBF3] px-3 py-2"
          data-testid="cb-decision-detail">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[#8C4A00]">
            {EXCEPTION_TYPE_LABEL[exception?.type] || "Selisih 3-way"}
          </p>
          <p className="mt-1 text-[12px] text-[#1C1C1E]">{exception?.detail}</p>
          <p className="mt-1 text-[11px] text-[#8C4A00]">
            Nilai selisih <b>{formatCurrency(exception?.amount)}</b>
            {exception?.variance_percent ? ` · ${exception.variance_percent}% dari acuan` : ""}
          </p>
        </div>

        <div className="mt-3 space-y-3">
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Tindakan</label>
            <KNSelect data-testid="cb-decision-action" value={action} onValueChange={setAction}
              options={actions.map((a) => ({ value: a.action, label: a.label }))} className="field" />
            {spec && (
              <p className="mt-1 flex items-start gap-1 rounded-md bg-[#F2F7FF] px-2 py-1.5 text-[11px] text-[#1C1C1E]">
                <Info size={11} className="mt-[2px] shrink-0" /> {spec.help}
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Alasan berlabel (wajib)
              </label>
              <KNSelect data-testid="cb-decision-reason" value={reason} onValueChange={setReason}
                options={reasonOptions} className="field" placeholder="Pilih alasan" />
              <p className="mt-1 text-[10px] text-[#8E8E93]">
                Keputusan atas uang harus berlabel supaya bisa dibaca auditor.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Nominal {action === "deduct" ? "yang dipotong" : "selisih"} (Rp)
              </label>
              <input data-testid="cb-decision-amount" type="number" min={0} step={1000}
                className="input-field w-full" value={amount} disabled={action === "dispute"}
                onChange={(e) => setAmount(e.target.value)} />
              {action === "deduct" && (
                <p className="mt-1 text-[10px] text-[#B26A00]">
                  Sistem otomatis membuat potongan “Selisih 3-way match” berikut jurnalnya.
                </p>
              )}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Catatan</label>
            <textarea data-testid="cb-decision-note" className="textarea w-full" rows={2}
              value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="Mis. sudah dikonfirmasi lewat telepon dengan Bu Sri tanggal 12." />
          </div>

          {action === "dispute" && (
            <p className="rounded-md bg-[#FDE2E2] px-2 py-1.5 text-[11px] text-[#9B1C1C]">
              Kontrabon akan berpindah ke status <b>Sengketa</b> dan tertahan sampai supplier
              mengoreksi fakturnya. Setelah dikoreksi, kontrabon bisa diajukan ulang.
            </p>
          )}
        </div>

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="cb-decision-save"
            disabled={saving || !reason} onClick={save}>
            {saving ? "Menyimpan…" : "Simpan keputusan"}
          </button>
        </div>
      </div>
    </div>
  );
}
