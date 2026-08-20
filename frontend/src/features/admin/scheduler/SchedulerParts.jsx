/**
 * SchedulerParts (R6.5) — komponen bersama view Penjadwal & Notifikasi:
 * Modal, badge status, tabel job (dengan editor jadwal inline), tabel riwayat run.
 */
import { useEffect, useState } from "react";
import { X, Play, Clock, CheckCircle2, AlertTriangle, Loader2, Save, ExternalLink } from "lucide-react";
import { Badge } from "../../finance/financeShared";

export const inputCls = "w-full rounded-lg border border-[#E2E2E7] bg-white px-2.5 py-1.5 text-[12px] text-[#1C1C1E] focus:border-[#6B219A] focus:outline-none";
export const labelCls = "block text-[11px] font-bold text-[#3A3A3C] mb-1";

// ── RBAC UI (selaras permissions_config: resource "scheduler") ───────────────
export function schedPerms(role) {
  return {
    view: ["admin", "manager"].includes(role),
    run: ["admin", "manager"].includes(role),
    configure: role === "admin",
  };
}

/**
 * Semua waktu di view ini ditampilkan dalam zona **WIB (Asia/Jakarta)** — sama dengan
 * zona scheduler backend. Tanpa `timeZone` eksplisit, browser/server memakai UTC
 * sehingga job "Harian 08:00 WIB" tampil "01.00" → menyesatkan operator.
 */
export function fmtWaktu(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toLocaleString("id-ID", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    timeZone: "Asia/Jakarta",
  })} WIB`;
}

export function Modal({ title, children, onClose, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4"
         data-testid="sched-modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`mt-10 w-full ${wide ? "max-w-3xl" : "max-w-lg"} rounded-2xl border border-[#E7E7EC] bg-white shadow-xl`}>
        <div className="flex items-center gap-2 border-b border-[#F0F0F3] px-4 py-3">
          <h3 className="text-[13px] font-bold text-[#1C1C1E]">{title}</h3>
          <button data-testid="sched-modal-close" onClick={onClose}
                  className="ml-auto rounded-lg p-1 text-[#8E8E93] hover:bg-[#F2F2F5]"><X size={16} /></button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function RunStatusBadge({ status }) {
  if (status === "success") return <Badge tone="ok" testId="run-status-success">Sukses</Badge>;
  if (status === "failed") return <Badge tone="over" testId="run-status-failed">Gagal</Badge>;
  if (status === "running") return <Badge tone="purple" testId="run-status-running">Berjalan</Badge>;
  return <Badge tone="neutral">Belum pernah</Badge>;
}

// ── Editor jadwal 1 job (harian jam:menit ATAU interval jam) ────────────────
function ScheduleEditor({ job, onSave, saving }) {
  const [hour, setHour] = useState(job.hour ?? 8);
  const [minute, setMinute] = useState(job.minute ?? 0);
  const [interval, setInterval] = useState(job.interval_hours ?? 4);
  useEffect(() => {
    setHour(job.hour ?? 8); setMinute(job.minute ?? 0); setInterval(job.interval_hours ?? 4);
  }, [job.hour, job.minute, job.interval_hours]);

  return (
    <div className="flex items-center gap-1.5">
      {job.kind === "daily" ? (
        <>
          <input data-testid={`job-hour-${job.id}`} type="number" min="0" max="23"
                 value={hour} onChange={(e) => setHour(e.target.value)}
                 className="w-14 rounded-lg border border-[#E2E2E7] bg-white px-1.5 py-1 text-center text-[11.5px]" />
          <span className="text-[11px] text-[#8E8E93]">:</span>
          <input data-testid={`job-minute-${job.id}`} type="number" min="0" max="59"
                 value={minute} onChange={(e) => setMinute(e.target.value)}
                 className="w-14 rounded-lg border border-[#E2E2E7] bg-white px-1.5 py-1 text-center text-[11.5px]" />
          <span className="text-[10px] text-[#9A9BA3]">WIB</span>
        </>
      ) : (
        <>
          <span className="text-[11px] text-[#8E8E93]">tiap</span>
          <input data-testid={`job-interval-${job.id}`} type="number" min="1" max="24"
                 value={interval} onChange={(e) => setInterval(e.target.value)}
                 className="w-14 rounded-lg border border-[#E2E2E7] bg-white px-1.5 py-1 text-center text-[11.5px]" />
          <span className="text-[10px] text-[#9A9BA3]">jam</span>
        </>
      )}
      <button data-testid={`job-schedule-save-${job.id}`} disabled={saving}
              onClick={() => onSave(job.kind === "daily"
                ? { hour: Number(hour), minute: Number(minute) }
                : { interval_hours: Number(interval) })}
              title="Simpan jadwal"
              className="rounded-lg border border-[#E2E2E7] p-1 text-[#6B219A] hover:bg-[#F7F2FB] disabled:opacity-40">
        <Save size={13} />
      </button>
    </div>
  );
}

// ── Tabel job ────────────────────────────────────────────────────────
export function JobTable({ jobs, perms, busyId, onRun, onPatch, onOpenDetail }) {
  return (
    <div className="overflow-hidden rounded-xl border border-[#EFF0F2] bg-white" data-testid="job-table">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="bg-[#FAFAFC] text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
            <th className="px-3 py-2.5 font-bold">Job</th>
            <th className="px-3 py-2.5 font-bold">Jadwal</th>
            <th className="px-3 py-2.5 font-bold">Berikutnya</th>
            <th className="px-3 py-2.5 font-bold">Terakhir Jalan</th>
            <th className="px-3 py-2.5 font-bold text-center">Hasil</th>
            <th className="px-3 py-2.5 font-bold text-center">Aktif</th>
            <th className="px-3 py-2.5 font-bold text-right">Aksi</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#F2F2F5]">
          {jobs.map((j) => (
            <tr key={j.id} data-testid={`job-row-${j.id}`} className="hover:bg-[#FCFAFE]">
              <td className="px-3 py-2.5">
                <button data-testid={`job-detail-${j.id}`} onClick={() => onOpenDetail(j)}
                        className="text-left font-semibold text-[#6B219A] hover:underline">
                  {j.label}
                </button>
                <div className="mt-0.5 max-w-[420px] text-[10.5px] leading-snug text-[#8E8E93]">
                  {j.description}
                </div>
              </td>
              <td className="px-3 py-2.5">
                {perms.configure ? (
                  <>
                    <ScheduleEditor job={j} saving={busyId === j.id}
                                    onSave={(patch) => onPatch(j.id, patch)} />
                    <div className="mt-0.5 text-[10px] text-[#9A9BA3]">
                      Tersimpan: {j.schedule_label}
                    </div>
                  </>
                ) : (
                  <span className="text-[#3A3A3C]">{j.schedule_label}</span>
                )}
              </td>
              <td className="px-3 py-2.5 text-[#3A3A3C]">
                {j.enabled ? fmtWaktu(j.next_run) : <span className="text-[#9A9BA3]">Nonaktif</span>}
              </td>
              <td className="px-3 py-2.5 text-[#3A3A3C]">
                {fmtWaktu(j.last_run_at)}
                {j.last_detail && (
                  <div className="mt-0.5 max-w-[260px] truncate text-[10px] text-[#9A9BA3]"
                       title={j.last_detail}>{j.last_detail}</div>
                )}
              </td>
              <td className="px-3 py-2.5 text-center">
                <RunStatusBadge status={j.last_status} />
                <div className="mt-0.5 text-[10px] text-[#9A9BA3]">
                  {j.last_status ? `${j.last_created} notifikasi` : "—"}
                </div>
              </td>
              <td className="px-3 py-2.5 text-center">
                <button data-testid={`job-toggle-${j.id}`}
                        disabled={!perms.configure || busyId === j.id}
                        onClick={() => onPatch(j.id, { enabled: !j.enabled })}
                        title={j.enabled ? "Nonaktifkan job" : "Aktifkan job"}
                        className={`inline-flex h-5 w-9 items-center rounded-full transition ${j.enabled ? "bg-[#1B7F4B]" : "bg-[#D1D1D6]"} disabled:opacity-50`}>
                  <span className={`h-4 w-4 rounded-full bg-white transition ${j.enabled ? "translate-x-4" : "translate-x-0.5"}`} />
                </button>
              </td>
              <td className="px-3 py-2.5 text-right">
                <button data-testid={`job-run-${j.id}`} disabled={!perms.run || busyId === j.id}
                        onClick={() => onRun(j.id)} title="Jalankan sekarang"
                        className="inline-flex items-center gap-1 rounded-lg border border-[#E2E2E7] px-2 py-1 text-[11.5px] font-semibold text-[#6B219A] hover:bg-[#F7F2FB] disabled:opacity-40">
                  {busyId === j.id ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                  Jalankan
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Tabel riwayat run ─────────────────────────────────────────────────
export function RunTable({ runs }) {
  return (
    <div className="overflow-hidden rounded-xl border border-[#EFF0F2] bg-white" data-testid="run-table">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="bg-[#FAFAFC] text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
            <th className="px-3 py-2.5 font-bold">Waktu</th>
            <th className="px-3 py-2.5 font-bold">Job</th>
            <th className="px-3 py-2.5 font-bold">Pemicu</th>
            <th className="px-3 py-2.5 font-bold text-center">Status</th>
            <th className="px-3 py-2.5 font-bold text-right">Notifikasi</th>
            <th className="px-3 py-2.5 font-bold text-right">WA</th>
            <th className="px-3 py-2.5 font-bold text-right">Durasi</th>
            <th className="px-3 py-2.5 font-bold">Keterangan</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#F2F2F5]">
          {runs.map((r) => (
            <tr key={r.id} data-testid={`run-row-${r.id}`} className="hover:bg-[#FCFAFE]">
              <td className="px-3 py-2 whitespace-nowrap text-[#3A3A3C]">{fmtWaktu(r.started_at)}</td>
              <td className="px-3 py-2 font-semibold text-[#1C1C1E]">{r.job_label || r.job_id}</td>
              <td className="px-3 py-2 text-[#8E8E93]">
                {r.trigger === "manual" ? `Manual · ${r.actor || "-"}` : "Terjadwal"}
              </td>
              <td className="px-3 py-2 text-center"><RunStatusBadge status={r.status} /></td>
              <td className="px-3 py-2 text-right tabular-nums">{r.created ?? 0}</td>
              <td className="px-3 py-2 text-right tabular-nums">{r.wa_queued ?? 0}</td>
              <td className="px-3 py-2 text-right tabular-nums text-[#8E8E93]">{r.duration_ms ?? 0} ms</td>
              <td className="px-3 py-2 text-[11px] text-[#8E8E93]">
                {r.error ? <span className="font-semibold text-[#C0392B]">{r.error}</span> : (r.detail || "—")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Panel detail job ─────────────────────────────────────────────────
// Label modul tujuan untuk tombol deep-link (memakai field `link` dari backend).
export const LINK_LABEL = {
  "ar-aging": "Piutang (AR Aging)",
  "vendor-bills": "Tagihan Supplier",
  "fixed-assets": "Aset Tetap",
  budget: "Anggaran vs Realisasi",
  production: "Produksi (BOM & WO)",
  operations: "Operasi WMS",
};

export function JobDetail({ job, runs, onRun, busy, perms, onNavigate }) {
  const mine = runs.filter((r) => r.job_id === job.id).slice(0, 8);
  return (
    <div className="space-y-3" data-testid="job-detail-panel">
      <p className="text-[12px] leading-relaxed text-[#3A3A3C]">{job.description}</p>
      <div className="grid grid-cols-2 gap-2 text-[11.5px]">
        <div className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-3 py-2">
          <div className="text-[10px] font-bold uppercase text-[#9A9BA3]">Jadwal</div>
          <div className="mt-0.5 flex items-center gap-1 font-semibold text-[#1C1C1E]">
            <Clock size={12} /> {job.schedule_label}
          </div>
        </div>
        <div className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-3 py-2">
          <div className="text-[10px] font-bold uppercase text-[#9A9BA3]">Jalan berikutnya</div>
          <div className="mt-0.5 font-semibold text-[#1C1C1E]" data-testid="job-detail-next">
            {job.enabled ? fmtWaktu(job.next_run) : "Job nonaktif"}
          </div>
        </div>
      </div>
      {job.last_error && (
        <div className="flex items-start gap-2 rounded-lg border border-[#F3D6D6] bg-[#FDECEC] px-3 py-2 text-[11.5px] text-[#C0392B]">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span><b>Error terakhir:</b> {job.last_error}</span>
        </div>
      )}
      <div>
        <div className="mb-1.5 text-[11px] font-bold text-[#3A3A3C]">8 eksekusi terakhir</div>
        {mine.length === 0 ? (
          <div className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-3 py-4 text-center text-[11.5px] text-[#8E8E93]">
            Belum pernah dijalankan.
          </div>
        ) : (
          <div className="space-y-1">
            {mine.map((r) => (
              <div key={r.id} className="flex items-center gap-2 rounded-lg border border-[#F2F2F5] px-2.5 py-1.5 text-[11.5px]">
                {r.status === "success"
                  ? <CheckCircle2 size={13} className="text-[#1B7F4B]" />
                  : <AlertTriangle size={13} className="text-[#C0392B]" />}
                <span className="text-[#3A3A3C]">{fmtWaktu(r.started_at)}</span>
                <span className="text-[#8E8E93]">· {r.created ?? 0} notifikasi</span>
                <span className="ml-auto text-[10px] text-[#9A9BA3]">{r.duration_ms} ms</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="flex items-center justify-end gap-2 pt-1">
        {job.link && onNavigate && (
          <button data-testid="job-detail-open-module" onClick={() => onNavigate(job.link)}
                  className="mr-auto inline-flex items-center gap-1.5 rounded-lg border border-[#E2E2E7] px-3 py-2 text-[12px] font-semibold text-[#6B219A] hover:bg-[#F7F2FB]">
            <ExternalLink size={13} /> Buka {LINK_LABEL[job.link] || job.link}
          </button>
        )}
        <button data-testid="job-detail-run" disabled={!perms.run || busy} onClick={() => onRun(job.id)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#6B219A] px-3 py-2 text-[12px] font-bold text-white hover:bg-[#581680] disabled:opacity-50">
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Jalankan sekarang
        </button>
      </div>
    </div>
  );
}
