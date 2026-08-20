/**
 * SchedulerPolicy (R6.6) — panel kebijakan alert:
 *  - Eskalasi bertingkat: alert penting yang belum dibaca melewati batas waktu
 *    dinaikkan otomatis ke atasan (sales/gudang → manager → admin).
 *  - Pratinjau Ringkasan Harian (isi pesan WhatsApp gabungan) sebelum diaktifkan.
 */
import { useEffect, useState } from "react";
import { ArrowUpCircle, ShieldAlert, Clock4, Save, Loader2 } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { inputCls, labelCls } from "./SchedulerParts";

const SEVERITY_OPTS = [
  { value: "warning", label: "Perhatian & Penting (disarankan)" },
  { value: "critical", label: "Hanya Penting" },
  { value: "info", label: "Semua tingkat (paling agresif)" },
];
const LEVEL_OPTS = [
  { value: "1", label: "1 tingkat (→ manager)" },
  { value: "2", label: "2 tingkat (→ manager → admin)" },
  { value: "3", label: "3 tingkat (rantai penuh)" },
];

function Stat({ label, value, testId, tone = "#6B219A" }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-3 py-2" data-testid={testId}>
      <div className="text-[10px] font-bold uppercase tracking-wide text-[#9A9BA3]">{label}</div>
      <div className="mt-0.5 text-[15px] font-bold tabular-nums" style={{ color: tone }}>{value}</div>
    </div>
  );
}

export function EscalationPanel({ esc = {}, stats = {}, perms, saving, onSave }) {
  const [form, setForm] = useState({
    enabled: esc.enabled !== false,
    after_hours: esc.after_hours ?? 8,
    min_severity: esc.min_severity || "warning",
    max_level: String(esc.max_level ?? 2),
  });
  useEffect(() => {
    setForm({
      enabled: esc.enabled !== false,
      after_hours: esc.after_hours ?? 8,
      min_severity: esc.min_severity || "warning",
      max_level: String(esc.max_level ?? 2),
    });
  }, [esc.enabled, esc.after_hours, esc.min_severity, esc.max_level]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const submit = () => onSave({
    enabled: form.enabled,
    after_hours: Number(form.after_hours),
    min_severity: form.min_severity,
    max_level: Number(form.max_level),
  });

  return (
    <div className="rounded-xl border border-[#EFF0F2] bg-white p-3.5" data-testid="esc-panel">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#FDECEC]">
          <ArrowUpCircle size={16} className="text-[#C0392B]" />
        </div>
        <div className="mr-auto min-w-[220px]">
          <div className="text-[13px] font-bold text-[#1C1C1E]">Eskalasi Bertingkat</div>
          <p className="mt-0.5 max-w-[560px] text-[11.5px] leading-snug text-[#8E8E93]">
            Alert penting yang <b>belum dibaca</b> melewati batas waktu dinaikkan otomatis ke
            atasan: <b>sales/gudang → manager → admin</b>. Notifikasi eskalasi selalu bertingkat
            <b> Penting</b> sehingga tetap dikirim WhatsApp seketika walau mode Ringkasan aktif.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Stat label="Eskalasi hari ini" value={stats.today ?? 0} testId="esc-stat-today" />
          <Stat label="Belum ditindak" value={stats.open ?? 0} testId="esc-stat-open" tone="#C0392B" />
          <Stat label="Calon naik" value={stats.pending_next_scan ?? 0} testId="esc-stat-pending" tone="#C77700" />
        </div>
      </div>

      <div className="mt-3 grid gap-3 border-t border-[#F2F2F5] pt-3 md:grid-cols-4">
        <label className="flex items-center gap-2 text-[12px] font-semibold text-[#1C1C1E]">
          <input data-testid="esc-enabled-toggle" type="checkbox" checked={form.enabled}
                 disabled={!perms.configure}
                 onChange={(e) => set("enabled", e.target.checked)}
                 className="h-4 w-4 accent-[#6B219A]" />
          Aktifkan eskalasi
        </label>
        <div>
          <label className={labelCls}>
            <Clock4 size={10} className="mr-1 inline align-[-1px]" /> Batas belum ditindak (jam)
          </label>
          <input data-testid="esc-hours-input" type="number" min="1" max="72"
                 className={inputCls} value={form.after_hours} disabled={!perms.configure}
                 onChange={(e) => set("after_hours", e.target.value)} />
        </div>
        <div>
          <label className={labelCls}>
            <ShieldAlert size={10} className="mr-1 inline align-[-1px]" /> Naikkan mulai tingkat
          </label>
          <KNSelect data-testid="esc-severity-select" value={form.min_severity}
                    onValueChange={(v) => set("min_severity", v)} options={SEVERITY_OPTS}
                    className={inputCls} disabled={!perms.configure} />
        </div>
        <div>
          <label className={labelCls}>Kedalaman rantai</label>
          <KNSelect data-testid="esc-level-select" value={form.max_level}
                    onValueChange={(v) => set("max_level", v)} options={LEVEL_OPTS}
                    className={inputCls} disabled={!perms.configure} />
        </div>
      </div>

      {perms.configure && (
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="text-[10.5px] text-[#9A9BA3]">
            Pemindaian berjalan lewat job <b>Eskalasi Alert Belum Ditindak</b> (tiap 2 jam).
          </span>
          <button data-testid="esc-save-button" disabled={saving} onClick={submit}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#6B219A] px-3 py-2 text-[12px] font-bold text-white hover:bg-[#581680] disabled:opacity-50">
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            Simpan Kebijakan
          </button>
        </div>
      )}
    </div>
  );
}

// ── Isi modal pratinjau Ringkasan Harian ────────────────────────────────────
export function DigestPreview({ data, role, onRole, loading }) {
  return (
    <div className="space-y-3" data-testid="digest-preview-panel">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-bold text-[#3A3A3C]">Pratinjau untuk peran</span>
        <KNSelect data-testid="digest-preview-role" value={role} onValueChange={onRole}
                  className={`${inputCls} w-44`}
                  options={[{ value: "admin", label: "Admin" },
                            { value: "manager", label: "Manager" },
                            { value: "sales", label: "Sales" },
                            { value: "warehouse", label: "Gudang" }]} />
        {loading && <Loader2 size={13} className="animate-spin text-[#6B219A]" />}
      </div>

      {!loading && data && (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Total alert" value={data.total ?? 0} testId="digest-total" />
            <Stat label="Belum dibaca" value={data.unread ?? 0} testId="digest-unread" tone="#C77700" />
            <Stat label="Kelompok" value={(data.groups || []).length} testId="digest-groups" tone="#0058CC" />
          </div>
          {(data.groups || []).length === 0 ? (
            <div className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-3 py-6 text-center text-[11.5px] text-[#8E8E93]"
                 data-testid="digest-preview-empty">
              Belum ada alert hari ini untuk peran ini — ringkasan tidak akan dikirim
              (job melewati penerima tanpa alert).
            </div>
          ) : (
            <>
              <div className="space-y-1">
                {(data.groups || []).map((g) => (
                  <div key={g.type} data-testid={`digest-group-${g.type}`}
                       className="flex items-center gap-2 rounded-lg border border-[#F2F2F5] px-2.5 py-1.5 text-[11.5px]">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${
                      g.severity === "critical" ? "bg-[#C0392B]"
                        : g.severity === "warning" ? "bg-[#C77700]" : "bg-[#0058CC]"}`} />
                    <span className="font-semibold text-[#1C1C1E]">{g.label}</span>
                    <span className="ml-auto tabular-nums font-bold text-[#3A3A3C]">{g.count}</span>
                  </div>
                ))}
              </div>
              <div>
                <div className="mb-1 text-[11px] font-bold text-[#3A3A3C]">Isi pesan WhatsApp</div>
                <pre data-testid="digest-preview-text"
                     style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, "Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", monospace' }}
                     className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] p-3 text-[11px] leading-relaxed text-[#1C1C1E]">
{data.text}
                </pre>
              </div>
            </>
          )}
          <p className="text-[10.5px] text-[#9A9BA3]">
            Mode saat ini: <b>{data.delivery_mode === "digest" ? "Ringkasan harian" : "Instan (per alert)"}</b>
            {" · "}kanal WhatsApp {data.wa_enabled ? "aktif" : "nonaktif"}
            {" · "}ambang {data.min_severity}.
          </p>
        </>
      )}
    </div>
  );
}
