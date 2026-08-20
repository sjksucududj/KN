import { useEffect, useState } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  Users, CalendarCheck, Clock, Wallet, ShieldCheck, Receipt, TrendingUp,
  RefreshCw, UserPlus, Building2, Timer,
} from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import axios, { API } from "../../services/apiClient";

const COLORS = ["#0058CC", "#34C759", "#FF9500", "#C0341D", "#5856D6", "#1F7A45", "#8E8E93"];
const fmt = new Intl.NumberFormat("id-ID");
const fmtCur = (v) => `Rp ${fmt.format(Math.round(v || 0))}`;
function fmtShort(v) {
  const n = Math.round(v || 0);
  if (n >= 1e9) return `Rp ${(n / 1e9).toFixed(1)} M`;
  if (n >= 1e6) return `Rp ${(n / 1e6).toFixed(1)} jt`;
  if (n >= 1e3) return `Rp ${(n / 1e3).toFixed(0)} rb`;
  return `Rp ${n}`;
}

function KPICard({ icon: Icon, label, value, sub, color = "#0058CC", loading, testId }) {
  return (
    <div data-testid={testId} className="rounded-xl border border-[#EFF0F2] bg-white p-4 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="rounded-lg p-1.5" style={{ background: `${color}18` }}><Icon size={16} style={{ color }} /></div>
        <span className="text-[12px] font-semibold text-[#6B6B73]">{label}</span>
      </div>
      {loading ? <div className="h-7 bg-[#F5F5F7] rounded animate-pulse" />
        : <p className="text-[22px] font-bold text-[#1C1C1E] tabular-nums leading-tight">{value}</p>}
      {sub && <p className="text-[11px] text-[#6B6B73]">{sub}</p>}
    </div>
  );
}

function Panel({ title, right, children }) {
  return (
    <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[13.5px] font-bold">{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

export default function HrAnalyticsView({ currentUser, selectedEntity }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState("");

  useEffect(() => { load(period); }, [period, selectedEntity]); // eslint-disable-line

  async function load(p) {
    setLoading(true);
    const ent = selectedEntity && selectedEntity !== "all" ? selectedEntity : "all";
    try {
      const r = await axios.get(`${API}/hr/analytics/summary`, { params: { entity_id: ent, ...(p ? { period: p } : {}) } });
      setData(r.data || null);
      if (!p && r.data?.period) setPeriod(r.data.period);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat analitik SDM.");
    } finally { setLoading(false); }
  }

  const hc = data?.headcount || {};
  const att = data?.attendance || {};
  const tn = data?.turnover || {};
  const pay = data?.payroll || {};
  const stat = data?.statutory || {};
  const payTrend = data?.payroll_trend || [];
  const otTrend = data?.overtime_trend || [];
  const byType = hc.by_type || [];
  const byDept = hc.by_department || [];
  const attStatus = (att.by_status || []).filter((s) => s.count > 0);
  const periodOpts = (data?.periods || []).map((p) => ({ value: p, label: p }));
  const hasPayroll = pay.has_run;
  const hasOt = otTrend.some((o) => o.minutes > 0);

  return (
    <section data-testid="hr-analytics-view" className="section-card">
      <div className="section-head">
        <p className="text-[12px] text-[#6B6B73] min-w-0 truncate">Ringkasan kinerja SDM — periode {data?.period || "—"}</p>
        <div className="flex items-center gap-2 flex-shrink-0">
          <KNSelect data-testid="hr-analytics-period" value={period} onValueChange={setPeriod}
            options={periodOpts} className="field !py-1 !px-2 text-[12px] w-auto" placeholder="Periode" />
          <button data-testid="hr-analytics-refresh" onClick={() => load(period)} className="secondary-button">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>
      <div className="section-body">
        <ErrorNotice message={error} onRetry={() => load(period)} onDismiss={() => setError("")} testId="hr-analytics-error" />

        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3" data-testid="hr-analytics-kpis">
          <KPICard testId="kpi-headcount" icon={Users} label="Headcount" value={loading ? "" : (hc.total ?? "—")} sub={`${tn.new_hires ?? 0} hire periode ini`} color="#0058CC" loading={loading} />
          <KPICard testId="kpi-attendance-rate" icon={CalendarCheck} label="Kehadiran" value={loading ? "" : `${att.attendance_rate ?? 0}%`} sub={`${att.present ?? 0} hadir · ${att.late ?? 0} telat`} color="#34C759" loading={loading} />
          <KPICard testId="kpi-punctuality" icon={Clock} label="Ketepatan" value={loading ? "" : `${att.punctuality_rate ?? 0}%`} sub={`Rata telat ${att.avg_late_min ?? 0} mnt`} color="#FF9500" loading={loading} />
          <KPICard testId="kpi-payroll-net" icon={Wallet} label="Biaya Gaji (Net)" value={loading ? "" : (hasPayroll ? fmtShort(pay.net) : "—")} sub={hasPayroll ? `Gross ${fmtShort(pay.gross)}` : "Belum ada run"} color="#5856D6" loading={loading} />
          <KPICard testId="kpi-bpjs" icon={ShieldCheck} label="BPJS Payable" value={loading ? "" : (hasPayroll ? fmtShort(stat.bpjs_total) : "—")} sub={hasPayroll ? `Emp ${fmtShort(stat.bpjs_emp)} · ER ${fmtShort(stat.bpjs_er)}` : "—"} color="#1F7A45" loading={loading} />
          <KPICard testId="kpi-pph21" icon={Receipt} label="PPh21 Payable" value={loading ? "" : (hasPayroll ? fmtShort(stat.pph21) : "—")} sub={`Turnover ${tn.turnover_rate ?? 0}%`} color="#C0341D" loading={loading} />
        </div>

        {/* Row: Headcount by dept + by type */}
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Panel title="Headcount per Departemen" right={<span className="text-[12px] text-[#6B6B73] flex items-center gap-1"><Building2 size={13} /> {hc.total ?? 0} karyawan</span>}>
            {loading ? <div className="h-44 bg-[#F5F5F7] rounded animate-pulse" />
              : byDept.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={byDept} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#EFF0F2" />
                    <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={120} />
                    <Tooltip formatter={(v) => [v, "Karyawan"]} />
                    <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={18}>
                      {byDept.map((e, i) => <Cell key={e.name} fill={COLORS[i % COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyBox text="Belum ada data karyawan" />}
          </Panel>

          <Panel title="Komposisi Tipe Pekerja">
            {loading ? <div className="h-44 bg-[#F5F5F7] rounded animate-pulse" />
              : byType.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={byType} dataKey="count" nameKey="type" cx="50%" cy="50%" outerRadius={72} label={(e) => `${e.type} (${e.count})`} labelLine={false}>
                      {byType.map((e, i) => <Cell key={e.type} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v, n) => [v, n]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : <EmptyBox text="Belum ada data tipe pekerja" />}
          </Panel>
        </div>

        {/* Row: Attendance breakdown + Payroll trend */}
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Panel title="Distribusi Kehadiran" right={<span className="text-[12px] text-[#6B6B73]">{att.total ?? 0} record</span>}>
            {loading ? <div className="h-44 bg-[#F5F5F7] rounded animate-pulse" />
              : attStatus.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={attStatus} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#EFF0F2" />
                    <XAxis dataKey="status" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                    <Tooltip formatter={(v) => [v, "Hari"]} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]} barSize={42}>
                      {attStatus.map((e, i) => <Cell key={e.status} fill={COLORS[i % COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyBox text="Belum ada data absensi periode ini" />}
          </Panel>

          <Panel title="Tren Biaya Gaji (6 bulan)">
            {loading ? <div className="h-44 bg-[#F5F5F7] rounded animate-pulse" />
              : hasPayroll || payTrend.some((p) => p.gross > 0) ? (
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={payTrend} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#EFF0F2" />
                    <XAxis dataKey="period" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(2)} />
                    <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => (v >= 1e6 ? `${(v / 1e6).toFixed(0)}jt` : v)} width={38} />
                    <Tooltip formatter={(v, n) => [fmtCur(v), n === "gross" ? "Gross" : n === "net" ? "Net" : n]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="gross" stroke="#0058CC" strokeWidth={2} dot={{ r: 2 }} name="gross" />
                    <Line type="monotone" dataKey="net" stroke="#34C759" strokeWidth={2} dot={{ r: 2 }} name="net" />
                  </LineChart>
                </ResponsiveContainer>
              ) : <EmptyBox text="Belum ada run payroll" />}
          </Panel>
        </div>

        {/* Row: Overtime trend + Statutory & Turnover summary */}
        <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <Panel title="Tren Lembur (6 bulan)" right={<span className="text-[12px] text-[#6B6B73] flex items-center gap-1"><Timer size={13} /> jam</span>}>
            {loading ? <div className="h-40 bg-[#F5F5F7] rounded animate-pulse" />
              : hasOt ? (
                <ResponsiveContainer width="100%" height={190}>
                  <BarChart data={otTrend} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#EFF0F2" />
                    <XAxis dataKey="period" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(2)} />
                    <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                    <Tooltip formatter={(v, n) => [n === "hours" ? `${v} jam` : v, n === "hours" ? "Lembur" : "Pengajuan"]} />
                    <Bar dataKey="hours" fill="#FF9500" radius={[4, 4, 0, 0]} name="hours" barSize={34} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyBox text="Belum ada lembur disetujui dalam 6 bulan" />}
          </Panel>

          <Panel title="Statutory & Turnover">
            {loading ? <div className="h-40 bg-[#F5F5F7] rounded animate-pulse" /> : (
              <div className="grid gap-2" data-testid="hr-analytics-statutory">
                <StatRow label="BPJS Karyawan" value={fmtCur(stat.bpjs_emp)} />
                <StatRow label="BPJS Perusahaan" value={fmtCur(stat.bpjs_er)} />
                <StatRow label="BPJS Total" value={fmtCur(stat.bpjs_total)} bold />
                <StatRow label="PPh21" value={fmtCur(stat.pph21)} />
                <div className="h-px bg-[#EFF0F2] my-1" />
                <StatRow label="Headcount Aktif" value={String(tn.headcount ?? 0)} icon={Users} />
                <StatRow label="New Hire (periode)" value={String(tn.new_hires ?? 0)} icon={UserPlus} />
                <StatRow label="Separations" value={String(tn.separations ?? 0)} />
                <StatRow label="Turnover Rate" value={`${tn.turnover_rate ?? 0}%`} icon={TrendingUp} bold />
                {!hasPayroll && <p className="text-[10.5px] text-[#B7791F] mt-1">Statutory Rp0 karena belum ada run payroll periode {data?.period}.</p>}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </section>
  );
}

function EmptyBox({ text }) {
  return <div className="h-44 flex items-center justify-center text-[12.5px] text-[#8E8E93]">{text}</div>;
}

function StatRow({ label, value, bold, icon: Icon }) {
  return (
    <div className="flex items-center justify-between text-[12.5px]">
      <span className="flex items-center gap-1.5 text-[#6B6B73]">{Icon && <Icon size={13} className="text-[#0058CC]" />}{label}</span>
      <span className={`tabular-nums ${bold ? "font-bold text-[#1C1C1E]" : "text-[#3C3C43]"}`}>{value}</span>
    </div>
  );
}
