/**
 * SchedulerView (R6.5 — Penjadwal & Notifikasi) — pusat kendali alert otomatis.
 *
 * Sumber: /api/scheduler/jobs · /summary · /runs · /settings · /wa-outbox.
 * 3 tab: Job Terjadwal · Riwayat Eksekusi · WhatsApp (pengaturan + Outbox).
 * Semua alert dihitung dari data NYATA (AR, AP, penyusutan, anggaran, produksi, gudang).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, AlarmClock, ListChecks, MessageCircle, Bell, PlayCircle,
  CheckCircle2, AlertTriangle, Loader2,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import KNSelect from "../../../components/KNSelect";
import { KpiCard, EmptyState } from "../../finance/financeShared";
import { Modal, JobTable, RunTable, JobDetail, schedPerms } from "./SchedulerParts";
import { EscalationPanel, DigestPreview } from "./SchedulerPolicy";
import { WaSettingsPanel, WaOutboxTable } from "./SchedulerWa";

const TABS = [
  { k: "jobs", label: "Job Terjadwal", icon: AlarmClock },
  { k: "runs", label: "Riwayat Eksekusi", icon: ListChecks },
  { k: "wa", label: "WhatsApp", icon: MessageCircle },
];

export default function SchedulerView({ currentUser, onNavigate }) {
  const perms = useMemo(() => schedPerms(currentUser?.role), [currentUser]);
  const [tab, setTab] = useState("jobs");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null); // {msg, tone:'ok'|'err'}

  const [status, setStatus] = useState(null);   // {running, timezone, jobs[]}
  const [summary, setSummary] = useState(null);
  const [runs, setRuns] = useState([]);
  const [runJobFilter, setRunJobFilter] = useState("");
  const [settings, setSettings] = useState(null);
  const [outbox, setOutbox] = useState({ items: [], stats: {} });
  const [outFilter, setOutFilter] = useState("");

  const [busyId, setBusyId] = useState("");
  const [savingWa, setSavingWa] = useState(false);
  const [savingEsc, setSavingEsc] = useState(false);
  const [testing, setTesting] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const [detailJob, setDetailJob] = useState(null);
  // Pratinjau Ringkasan Harian (R6.6)
  const [digest, setDigest] = useState(null);   // {role, loading, data} | null

  const flash = useCallback((msg, tone = "ok") => {
    setNotice({ msg, tone });
    window.clearTimeout(flash._t);
    flash._t = window.setTimeout(() => setNotice(null), tone === "err" ? 6000 : 4000);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [j, s, r, st] = await Promise.all([
        axios.get(`${API}/scheduler/jobs`),
        axios.get(`${API}/scheduler/summary`),
        axios.get(`${API}/scheduler/runs`, {
          params: { limit: 80, ...(runJobFilter ? { job_id: runJobFilter } : {}) },
        }),
        axios.get(`${API}/scheduler/settings`),
      ]);
      setStatus(j.data || null);
      setSummary(s.data || null);
      setRuns(Array.isArray(r.data) ? r.data : []);
      setSettings(st.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data penjadwal.");
    } finally {
      setLoading(false);
    }
  }, [runJobFilter]);

  const loadOutbox = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/scheduler/wa-outbox`, {
        params: { limit: 200, ...(outFilter ? { status: outFilter } : {}) },
      });
      setOutbox({ items: data?.items || [], stats: data?.stats || {} });
    } catch {
      /* outbox opsional */
    }
  }, [outFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadOutbox(); }, [loadOutbox]);

  // ── actions ───────────────────────────────────────────────────────────────
  const runJob = async (jobId) => {
    setBusyId(jobId);
    try {
      const { data } = await axios.post(`${API}/scheduler/jobs/${jobId}/run`, {});
      if (data.status === "failed") {
        flash(`Job gagal: ${data.error || "kesalahan tidak diketahui"}`, "err");
      } else {
        flash(`${data.job_label}: ${data.created} notifikasi baru${data.detail ? ` · ${data.detail}` : ""}.`);
      }
      await Promise.all([load(), loadOutbox()]);
      if (detailJob) {
        const fresh = (await axios.get(`${API}/scheduler/jobs`)).data?.jobs || [];
        setDetailJob(fresh.find((x) => x.id === detailJob.id) || detailJob);
      }
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal menjalankan job.", "err");
    } finally { setBusyId(""); }
  };

  const runAll = async () => {
    setRunningAll(true);
    try {
      const { data } = await axios.post(`${API}/scheduler/jobs/all/run`, {});
      flash(`Semua job dijalankan · ${data.created} notifikasi baru`
            + (data.failed ? ` · ${data.failed} gagal` : ""), data.failed ? "err" : "ok");
      await Promise.all([load(), loadOutbox()]);
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal menjalankan semua job.", "err");
    } finally { setRunningAll(false); }
  };

  const patchJob = async (jobId, patch) => {
    setBusyId(jobId);
    try {
      await axios.put(`${API}/scheduler/settings`, { jobs: { [jobId]: patch } });
      flash("Jadwal job diperbarui.");
      await load();
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal menyimpan jadwal.", "err");
    } finally { setBusyId(""); }
  };

  const saveWa = async (waPatch) => {
    setSavingWa(true);
    try {
      await axios.put(`${API}/scheduler/settings`, { wa: waPatch });
      flash("Pengaturan WhatsApp disimpan.");
      await load();
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal menyimpan pengaturan WhatsApp.", "err");
    } finally { setSavingWa(false); }
  };

  // ── R6.6: kebijakan eskalasi + pratinjau ringkasan ────────────────────────
  const saveEscalation = async (patch) => {
    setSavingEsc(true);
    try {
      await axios.put(`${API}/scheduler/settings`, { escalation: patch });
      flash(patch.enabled === false
        ? "Eskalasi dinonaktifkan."
        : `Kebijakan eskalasi disimpan · naik setelah ${patch.after_hours} jam.`);
      await load();
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal menyimpan kebijakan eskalasi.", "err");
    } finally { setSavingEsc(false); }
  };

  const openDigest = async (role = "admin") => {
    setDigest({ role, loading: true, data: null });
    try {
      const { data } = await axios.get(`${API}/scheduler/digest-preview`, { params: { role } });
      setDigest({ role, loading: false, data });
    } catch (e) {
      setDigest(null);
      flash(e.response?.data?.detail || "Gagal memuat pratinjau ringkasan.", "err");
    }
  };

  const testWa = async (phone) => {
    setTesting(true);
    try {
      const { data } = await axios.post(`${API}/scheduler/wa-test`, { phone });
      flash(data.status === "sent"
        ? `Pesan uji TERKIRIM ke ${data.to}.`
        : data.status === "simulated"
          ? `Mode simulasi: pesan uji dicatat di Outbox untuk ${data.to} (tidak dikirim).`
          : `Pengiriman gagal: ${data.error || "cek kredensial provider"}`,
        data.status === "failed" ? "err" : "ok");
      await loadOutbox();
      setTab("wa");
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal mengirim pesan uji.", "err");
    } finally { setTesting(false); }
  };

  const retryWa = async (id) => {
    setBusyId(id);
    try {
      const { data } = await axios.post(`${API}/scheduler/wa-outbox/${id}/retry`, {});
      flash(data.status === "failed"
        ? `Kirim ulang gagal: ${data.error || "-"}` : `Kirim ulang: ${data.status}.`,
        data.status === "failed" ? "err" : "ok");
      await loadOutbox();
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal kirim ulang.", "err");
    } finally { setBusyId(""); }
  };

  const jobs = status?.jobs || [];
  const wa = settings?.wa || {};

  return (
    <div className="space-y-4" data-testid="scheduler-view">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#F3EAFB]">
          <AlarmClock size={19} className="text-[#6B219A]" />
        </div>
        <div className="mr-auto">
          <h2 className="text-[16px] font-bold text-[#1C1C1E]">Penjadwal & Notifikasi</h2>
          <p className="text-[11px] text-[#8E8E93]">
            Alert otomatis dari data nyata · zona {status?.timezone || "Asia/Jakarta"} (WIB)
            {status && (
              <span className={`ml-2 inline-flex items-center gap-1 font-semibold ${status.running ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}
                    data-testid="scheduler-running-state">
                {status.running ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}
                {status.running ? "Scheduler aktif" : "Scheduler tidak aktif"}
              </span>
            )}
          </p>
        </div>
        {perms.run && (
          <button data-testid="sched-run-all" onClick={runAll} disabled={runningAll}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#6B219A] px-3 py-2 text-[12px] font-bold text-white hover:bg-[#581680] disabled:opacity-50">
            {runningAll ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} />}
            Jalankan Semua
          </button>
        )}
        <button data-testid="sched-refresh" onClick={() => { load(); loadOutbox(); }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#E2E2E7] bg-white px-3 py-2 text-[12px] font-semibold text-[#3A3A3C] hover:bg-[#FAFAFA]">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Muat ulang
        </button>
      </div>

      {notice && (
        <div data-testid="scheduler-notice"
             className={`rounded-lg border px-3 py-2 text-[12px] font-semibold ${
               notice.tone === "err"
                 ? "border-[#F3D6D6] bg-[#FDECEC] text-[#C0392B]"
                 : "border-[#D6EBDD] bg-[#EAF6EF] text-[#1B7F4B]"}`}>
          {notice.msg}
        </div>
      )}
      {error && <ErrorNotice message={error} onRetry={load} />}

      {/* KPI */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard testId="sched-kpi-jobs" label="Job Aktif" icon={AlarmClock} accent="#6B219A"
                 value={`${summary?.jobs_enabled ?? 0} / ${summary?.jobs_total ?? 0}`}
                 sub="terjadwal otomatis" />
        <KpiCard testId="sched-kpi-runs" label="Eksekusi Hari Ini" icon={ListChecks} accent="#0058CC"
                 value={summary?.runs_today ?? 0}
                 sub={summary?.failed_today ? `${summary.failed_today} gagal` : "tanpa kegagalan"} />
        <KpiCard testId="sched-kpi-notif" label="Notifikasi Hari Ini" icon={Bell} accent="#C77700"
                 value={summary?.notifications_today ?? 0}
                 sub={`${summary?.notifications_unread ?? 0} belum dibaca · ${summary?.escalation?.open ?? 0} eskalasi terbuka`} />
        <KpiCard testId="sched-kpi-wa" label="Pesan WhatsApp" icon={MessageCircle} accent="#1B7F4B"
                 value={summary?.wa?.total ?? 0}
                 sub={`${summary?.wa?.today ?? 0} hari ini · ${wa.enabled
                   ? `${summary?.delivery_mode === "digest" ? "ringkasan" : "instan"} · ${wa.provider || "simulated"}`
                   : "nonaktif"}`} />
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-[#EFEFF4]">
        {TABS.map((t) => (
          <button key={t.k} data-testid={`sched-tab-${t.k}`} onClick={() => setTab(t.k)}
                  className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-[12px] font-bold transition ${tab === t.k ? "border-[#6B219A] text-[#6B219A]" : "border-transparent text-[#8E8E93] hover:text-[#3A3A3C]"}`}>
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === "jobs" && (
        <div className="space-y-3">
          <EscalationPanel esc={settings?.escalation || {}} stats={summary?.escalation || {}}
                           perms={perms} saving={savingEsc} onSave={saveEscalation} />
          {jobs.length === 0 && !loading ? (
            <EmptyState icon={AlarmClock} title="Belum ada job terdaftar"
                        hint="Job alert didefinisikan di backend (services/scheduler_service.py)."
                        testId="job-empty" />
          ) : (
            <JobTable jobs={jobs} perms={perms} busyId={busyId} onRun={runJob}
                      onPatch={patchJob} onOpenDetail={setDetailJob} />
          )}
        </div>
      )}

      {tab === "runs" && (
        <div className="space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <KNSelect data-testid="run-job-filter" value={runJobFilter} onValueChange={setRunJobFilter}
                      className="w-64 rounded-lg border border-[#E2E2E7] bg-white px-2.5 py-1.5 text-[12px] text-[#1C1C1E]"
                      options={[{ value: "", label: "Semua job" },
                                ...jobs.map((j) => ({ value: j.id, label: j.label }))]} />
            <span className="text-[11px] text-[#9A9BA3]" data-testid="run-count">
              {runs.length} eksekusi ditampilkan{runJobFilter ? " (terfilter)" : ""} · 80 terbaru
            </span>
          </div>
          {runs.length === 0 && !loading ? (
            <EmptyState icon={ListChecks} title="Belum ada riwayat eksekusi"
                        hint={runJobFilter
                          ? "Job ini belum pernah dijalankan. Pilih 'Semua job' atau jalankan job-nya."
                          : "Jalankan job secara manual atau tunggu jadwal otomatis."}
                        testId="run-empty" />
          ) : (
            <RunTable runs={runs} />
          )}
        </div>
      )}

      {tab === "wa" && settings && (
        <div className="space-y-4">
          <WaSettingsPanel wa={wa} perms={perms} saving={savingWa} onSave={saveWa}
                           onTest={testWa} testing={testing}
                           onPreviewDigest={() => openDigest("admin")} />
          <div>
            <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-[#8E8E93]">
              Outbox WhatsApp
            </div>
            <WaOutboxTable items={outbox.items} stats={outbox.stats} perms={perms}
                           busyId={busyId} onRetry={retryWa}
                           filter={outFilter} onFilter={setOutFilter} />
          </div>
        </div>
      )}

      {/* Modal pratinjau Ringkasan Harian (R6.6) */}
      {digest && (
        <Modal title="Pratinjau Ringkasan Harian" onClose={() => setDigest(null)} wide>
          <DigestPreview data={digest.data} role={digest.role} loading={digest.loading}
                         onRole={(r) => openDigest(r)} />
        </Modal>
      )}

      {/* Modal detail job */}
      {detailJob && (
        <Modal title={detailJob.label} onClose={() => setDetailJob(null)} wide>
          <JobDetail job={detailJob} runs={runs} perms={perms}
                     busy={busyId === detailJob.id} onRun={runJob}
                     onNavigate={onNavigate ? (target) => { setDetailJob(null); onNavigate(target); } : null} />
        </Modal>
      )}
    </div>
  );
}
