/**
 * FASE G-7 — modal **jadwalkan pembayaran** kontrabon yang sudah disetujui.
 * Tanggal rencana inilah yang dipakai KPI “jatuh tempo ≤ 7 hari” di layar induk.
 */
import { useEffect, useMemo, useState } from "react";
import { X, CalendarCheck } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";
import { METHOD_OPTIONS, fmtDate, todayISO } from "./contraBonApi";

export default function PaymentScheduleModal({ cb, onClose, onSaved, onError }) {
  const cur = cb.schedule || {};
  const [when, setWhen] = useState(cur.planned_payment_date || cb.due_date || todayISO());
  const [method, setMethod] = useState(cur.method || "transfer");
  const [accountId, setAccountId] = useState(cur.bank_account_id || "");
  const [notes, setNotes] = useState(cur.notes || "");
  const [accounts, setAccounts] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/bank-accounts`);
        const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
        if (alive) setAccounts(list);
      } catch (e) { if (alive) setErr(apiErrorText(e)); }
    })();
    return () => { alive = false; };
  }, []);

  const accountOptions = useMemo(() => accounts.map((a) => ({
    value: a.id, label: `${a.name}${a.bank_name ? ` · ${a.bank_name}` : ""}`,
  })), [accounts]);

  async function save() {
    setSaving(true); setErr("");
    try {
      const r = await axios.post(`${API}/contra-bons/${cb.id}/schedule`, {
        planned_payment_date: when,
        method,
        bank_account_id: accountId,
        notes: notes.trim(),
      });
      onSaved(r.data);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" data-testid="cb-schedule-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="modal-title flex items-center gap-1.5">
            <CalendarCheck size={15} /> Jadwalkan pembayaran
          </h3>
          <button className="icon-button" data-testid="cb-schedule-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        <p className="modal-subtitle">
          {cb.number} · {cb.supplier_name}
          {cb.due_date ? ` — jatuh tempo faktur ${fmtDate(cb.due_date)}` : ""}
        </p>

        {err && (
          <ErrorNotice message={err} onDismiss={() => setErr("")} testId="cb-schedule-error" />
        )}

        <div className="mt-3 space-y-3">
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Tanggal rencana pembayaran (wajib)
            </label>
            <input data-testid="cb-schedule-date" type="date" className="input-field w-full"
              value={when} onChange={(e) => setWhen(e.target.value)} />
            <p className="mt-1 text-[10px] text-[#8E8E93]">
              Tanggal ini yang dipakai KPI “jatuh tempo ≤ 7 hari” dan proyeksi arus kas.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Cara bayar</label>
              <KNSelect data-testid="cb-schedule-method" value={method} onValueChange={setMethod}
                options={METHOD_OPTIONS} className="field" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Rekening rencana
              </label>
              <KNSelect data-testid="cb-schedule-account" value={accountId}
                onValueChange={setAccountId} options={accountOptions} className="field"
                placeholder="Pilih rekening" />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Catatan</label>
            <textarea data-testid="cb-schedule-notes" className="textarea w-full" rows={2}
              value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Mis. dibayar bersama batch transfer Selasa pagi." />
          </div>
        </div>

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="cb-schedule-save"
            disabled={saving || !when} onClick={save}>
            {saving ? "Menyimpan…" : "Simpan jadwal bayar"}
          </button>
        </div>
      </div>
    </div>
  );
}
