/**
 * FASE G-7 · US1 — modal **atur jadwal tukar faktur** satu supplier.
 *
 * INV-UI-03 aturan C: modal ini menulis lewat axios, jadi WAJIB punya bilah error
 * sendiri (bilah error layar induk berada di belakang lapisan modal).
 */
import { useMemo, useState } from "react";
import { X, CalendarClock } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";
import { fmtDate } from "./contraBonApi";

export default function ExchangeScheduleModal({ row, meta, onClose, onSaved, onError }) {
  const cur = row?.invoice_exchange || {};
  // Supplier yang BELUM punya jadwal datang dengan mode "none". Kalau nilai itu dipakai
  // sebagai isian awal, petugas menekan "Simpan" dan… tidak terjadi apa-apa yang terlihat:
  // jadwalnya tetap "belum dijadwalkan" dan nama PIC yang sudah diketik tidak pernah
  // tampil di tabel (terukur saat uji layar). Isian awal karena itu jatuh ke ritme yang
  // paling sering dipakai supplier tekstil — mingguan — dan "Tidak terjadwal" tetap bisa
  // dipilih sadar-sadar bila memang mau dilepas.
  const [mode, setMode] = useState(cur.mode && cur.mode !== "none" ? cur.mode : "weekly");
  const [weekday, setWeekday] = useState(String(cur.weekday ?? 1));
  const [dayOfMonth, setDayOfMonth] = useState(String(cur.day_of_month ?? 25));
  const [pic, setPic] = useState(cur.pic_name || "");
  const [notes, setNotes] = useState(cur.notes || "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const modeOptions = useMemo(
    () => (meta?.schedule_modes || []).map((m) => ({ value: m.value, label: m.label })), [meta]);
  const weekdayOptions = useMemo(
    () => (meta?.weekdays || []).map((w) => ({ value: String(w.value), label: w.label })), [meta]);

  async function save() {
    setSaving(true); setErr("");
    try {
      const r = await axios.put(`${API}/suppliers/${row.supplier_id}/invoice-exchange`, {
        mode,
        weekday: Number(weekday) || 0,
        day_of_month: Number(dayOfMonth) || 25,
        pic_name: pic.trim(),
        notes: notes.trim(),
      });
      onSaved(r.data);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" data-testid="cb-exchange-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="modal-title flex items-center gap-1.5">
            <CalendarClock size={15} /> Jadwal tukar faktur
          </h3>
          <button className="icon-button" data-testid="cb-exchange-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>
        <p className="modal-subtitle">
          {row?.supplier_name} — hari tetap supplier datang menukar faktur dengan tanda terima kita.
        </p>

        {err && (
          <ErrorNotice message={err} onDismiss={() => setErr("")} testId="cb-exchange-error" />
        )}

        <div className="mt-3 space-y-3">
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Ritme siklus</label>
            <KNSelect data-testid="cb-exchange-mode" value={mode} onValueChange={setMode}
              options={modeOptions} className="field" />
          </div>

          {(mode === "weekly" || mode === "biweekly") && (
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Hari</label>
              <KNSelect data-testid="cb-exchange-weekday" value={weekday}
                onValueChange={setWeekday} options={weekdayOptions} className="field" />
              <p className="mt-1 text-[10px] text-[#8E8E93]">
                {mode === "biweekly"
                  ? "Dua pekan sekali dihitung dari tanggal acuan hari ini."
                  : "Berulang setiap pekan pada hari ini."}
              </p>
            </div>
          )}

          {mode === "monthly" && (
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Tanggal dalam bulan (1–28)
              </label>
              <input data-testid="cb-exchange-dom" type="number" min={1} max={28}
                className="input-field w-full" value={dayOfMonth}
                onChange={(e) => setDayOfMonth(e.target.value)} />
              <p className="mt-1 text-[10px] text-[#8E8E93]">
                Dibatasi 28 supaya jadwal tidak pernah hilang di bulan Februari.
              </p>
            </div>
          )}

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              PIC dari pihak supplier
            </label>
            <input data-testid="cb-exchange-pic" className="input-field w-full" value={pic}
              onChange={(e) => setPic(e.target.value)}
              placeholder="Nama orang yang biasa mengantar faktur" />
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">Catatan</label>
            <textarea data-testid="cb-exchange-notes" className="textarea w-full" rows={2}
              value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Mis. datang pagi sebelum jam 11, bawa nota debit sekalian." />
          </div>

          {row?.next_exchange_date && (
            <p className="rounded-md bg-[#F2F7FF] px-2 py-1.5 text-[11px] text-[#1C1C1E]">
              Siklus tersimpan saat ini: <b>{row.schedule_label}</b> · berikutnya{" "}
              {fmtDate(row.next_exchange_date)}.
            </p>
          )}
        </div>

        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="cb-exchange-save"
            disabled={saving} onClick={save}>
            {saving ? "Menyimpan…" : "Simpan jadwal"}
          </button>
        </div>
      </div>
    </div>
  );
}
