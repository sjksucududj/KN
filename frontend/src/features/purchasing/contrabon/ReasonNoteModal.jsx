/**
 * FASE G-7 — modal **alasan + catatan** untuk sengketa & pembatalan kontrabon.
 *
 * Sengketa WAJIB berlabel (backend menolak tanpa `reason_code`); pembatalan cukup
 * catatan. Satu modal untuk keduanya supaya kalimat penolakan & jejaknya seragam.
 */
import { useMemo, useState } from "react";
import { X, AlertTriangle } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";

const COPY = {
  dispute: {
    title: "Sengketakan kontrabon",
    subtitle: "Faktur supplier keliru — kontrabon ditahan sampai supplier mengoreksinya.",
    button: "Sengketakan",
    needReason: true,
    hint: "Setelah supplier mengoreksi faktur, kontrabon bisa diajukan ulang tanpa membuat "
      + "dokumen baru.",
  },
  cancel: {
    title: "Batalkan kontrabon",
    subtitle: "Faktur yang tertahan akan DILEPAS kembali sehingga bisa dikontrabon ulang.",
    button: "Batalkan kontrabon",
    needReason: false,
    hint: "Kontrabon yang sudah ada pembayarannya tidak bisa dibatalkan — pakai Pusat Kasus "
      + "Keuangan bila uangnya perlu dikoreksi.",
  },
};

export default function ReasonNoteModal({ cb, kind, meta, onClose, onDone, onError }) {
  const copy = COPY[kind] || COPY.dispute;
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const reasonOptions = useMemo(
    () => (meta?.reasons || []).map((r) => ({ value: r.code, label: r.label })), [meta]);

  async function submit() {
    setSaving(true); setErr("");
    try {
      const r = await axios.post(`${API}/contra-bons/${cb.id}/${kind}`, {
        reason_code: reason, note: note.trim(),
      });
      onDone(r.data);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" data-testid={`cb-${kind}-modal`} {...overlayDismiss(onClose)}>
      <div className="modal-card">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="modal-title flex items-center gap-1.5">
            <AlertTriangle size={15} /> {copy.title}
          </h3>
          <button className="icon-button" data-testid={`cb-${kind}-close`} onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        <p className="modal-subtitle">{cb.number} · {cb.supplier_name} — {copy.subtitle}</p>

        {err && (
          <ErrorNotice message={err} onDismiss={() => setErr("")} testId={`cb-${kind}-error`} />
        )}

        <div className="mt-3 space-y-3">
          {copy.needReason && (
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Alasan berlabel (wajib)
              </label>
              <KNSelect data-testid={`cb-${kind}-reason`} value={reason} onValueChange={setReason}
                options={reasonOptions} className="field" placeholder="Pilih alasan" />
            </div>
          )}
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Catatan</label>
            <textarea data-testid={`cb-${kind}-note`} className="textarea w-full" rows={3}
              value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="Ceritakan apa yang keliru supaya rekan lain paham tanpa bertanya." />
          </div>
          <p className="text-[10.5px] text-[#9A9BA3]">{copy.hint}</p>
        </div>

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>Tutup</button>
          <button className={kind === "cancel" ? "danger-button" : "primary-button"}
            data-testid={`cb-${kind}-submit`}
            disabled={saving || (copy.needReason && !reason)} onClick={submit}>
            {saving ? "Memproses…" : copy.button}
          </button>
        </div>
      </div>
    </div>
  );
}
