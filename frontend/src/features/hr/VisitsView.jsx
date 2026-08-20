import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Route, Users, BarChart3, RefreshCw, Building2 } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import { MyVisitsPanel } from "./MyVisitsPanel";
// FASE E-8 (E8.3 · SD4) — riwayat + KPI kunjungan MILIK SENDIRI (`/hr/visits/mine`).
// Dulu sales hanya melihat kunjungan HARI INI; catatan kerja sebulannya cuma bisa
// dilihat manajer, sehingga sales tak punya bukti apa pun atas usahanya sendiri.
import MyVisitsHistory from "./MyVisitsHistory";
import { OUTCOME_PILL, VISIT_STATUS_PILL, fmtTime, fmtMin, todayStr, monthStr } from "./trackingUtils";

function Stat({ label, value, color }) {
  return (
    <div className="section-card !p-3">
      <p className="text-[10.5px] uppercase font-semibold text-[#6B6B73]">{label}</p>
      <p className="text-[18px] font-bold tabular-nums leading-tight" style={{ color: color || "#1A1A1F" }}>{value}</p>
    </div>
  );
}

// Manager/Admin — Log Kunjungan + KPI ringkas per sales.
function VisitsLog({ currentUser, selectedEntity }) {
  const params = useMemo(
    () => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}),
    [selectedEntity]
  );
  const [dateFrom, setDateFrom] = useState(todayStr());
  const [dateTo, setDateTo] = useState(todayStr());
  const [month, setMonth] = useState(monthStr());
  const [empFilter, setEmpFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    axios.get(`${API}/hr/employees`, { params }).then((r) => setEmployees(Array.isArray(r.data) ? r.data : [])).catch(() => {});
  }, [selectedEntity]); // eslint-disable-line
  useEffect(() => { loadVisits(); }, [dateFrom, dateTo, empFilter, statusFilter, selectedEntity]); // eslint-disable-line
  useEffect(() => { loadSummary(); }, [month, selectedEntity]); // eslint-disable-line

  async function loadVisits() {
    setLoading(true);
    try {
      const q = { ...params, date_from: dateFrom, date_to: dateTo };
      if (empFilter) q.employee_id = empFilter;
      if (statusFilter) q.status = statusFilter;
      const r = await axios.get(`${API}/hr/visits`, { params: q });
      setRows(Array.isArray(r.data) ? r.data : []); setError("");
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat kunjungan."); }
    finally { setLoading(false); }
  }
  async function loadSummary() {
    try { const r = await axios.get(`${API}/hr/visits/summary`, { params: { ...params, month } }); setSummary(r.data || null); }
    catch (_) { /* noop */ }
  }

  const empOpts = [{ value: "", label: "Semua Karyawan" }, ...employees.map((e) => ({ value: e.id, label: `${e.name}${e.code ? ` (${e.code})` : ""}` }))];
  const statusOpts = [{ value: "", label: "Semua Status" }, { value: "ongoing", label: "Berjalan" }, { value: "done", label: "Selesai" }];
  const t = summary?.totals || {};

  return (
    <div data-testid="visits-view">
      <ErrorNotice message={error} onRetry={loadVisits} onDismiss={() => setError("")} testId="visits-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2"><Route size={16} className="text-[#0058CC]" /><h2 data-testid="visits-title">Kunjungan Sales — Log & KPI</h2></div>
          <button data-testid="visits-refresh" onClick={loadVisits} className="icon-button" title="Muat ulang"><RefreshCw size={15} /></button>
        </div>
      </div>

      {/* KPI bulanan */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4 mb-3">
        <Stat label="Sales Aktif (bln)" value={t.sales ?? 0} />
        <Stat label="Total Kunjungan" value={t.visits ?? 0} color="#0058CC" />
        <Stat label="Berbuah Pesanan" value={t.with_order ?? 0} color="#1F9D55" />
        <div className="section-card !p-3">
          <p className="text-[10.5px] uppercase font-semibold text-[#6B6B73]">Periode KPI</p>
          <input data-testid="visits-month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="field !py-1 mt-1" />
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_330px]">
        {/* Tabel kunjungan */}
        <div>
          <div className="section-card mb-3">
            <div className="section-body grid gap-2 md:grid-cols-4">
              <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Dari</label>
                <input data-testid="visits-date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="field" /></div>
              <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Sampai</label>
                <input data-testid="visits-date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="field" /></div>
              <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Karyawan</label>
                <KNSelect data-testid="visits-emp-filter" value={empFilter} onValueChange={setEmpFilter} className="field" searchable options={empOpts} /></div>
              <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Status</label>
                <KNSelect data-testid="visits-status-filter" value={statusFilter} onValueChange={setStatusFilter} className="field" options={statusOpts} /></div>
            </div>
          </div>
          <div className="section-card">
            <div className="grid grid-cols-[1.4fr_1.4fr_84px_84px_72px_96px_96px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Sales</span><span>Pelanggan</span><span>Masuk</span><span>Keluar</span><span className="text-right">Durasi</span><span>Hasil</span><span>Status</span>
            </div>
            {loading ? (
              <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="visits-loading">Memuat kunjungan...</div>
            ) : rows.length === 0 ? (
              <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="visits-empty"><Route className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada kunjungan pada rentang ini.</p></div>
            ) : (
              <div className="divide-y divide-[#EFF0F2] max-h-[520px] overflow-y-auto">
                {rows.map((v) => {
                  const oc = OUTCOME_PILL[v.outcome] || OUTCOME_PILL[""];
                  const st = VISIT_STATUS_PILL[v.status] || VISIT_STATUS_PILL.done;
                  return (
                    <div key={v.id} data-testid={`visit-row-${v.id}`} className="grid grid-cols-[1.4fr_1.4fr_84px_84px_72px_96px_96px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                      <div className="min-w-0 flex items-center gap-1"><EntityBadge entityId={v.entity_id} /><span className="text-[12px] font-semibold truncate">{v.employee_name}</span></div>
                      <span className="text-[11.5px] truncate flex items-center gap-1"><Building2 size={12} className="text-[#9A9BA3]" /> {v.customer_name}</span>
                      <span className="text-[11.5px] tabular-nums">{fmtTime(v.check_in?.ts)}</span>
                      <span className="text-[11.5px] tabular-nums">{fmtTime(v.check_out?.ts)}</span>
                      <span className="text-[11.5px] tabular-nums text-right">{fmtMin(v.duration_min)}</span>
                      <span><span className={`status-pill ${oc.cls}`}>{oc.label}</span></span>
                      <span><span data-testid={`visit-status-${v.id}`} className={`status-pill ${st.cls}`}>{st.label}</span></span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Rekap per sales (bulanan) */}
        <div className="section-card">
          <div className="px-3 py-2 border-b border-[#EFF0F2] text-[11px] font-bold uppercase text-[#6B6B73] flex items-center gap-1"><BarChart3 size={13} /> KPI per Sales · {month}</div>
          {(summary?.rows || []).length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="visits-summary-empty"><Users className="mx-auto mb-2 text-gray-300" size={26} /><p>Belum ada data KPI bulan ini.</p></div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
              {(summary?.rows || []).map((r) => (
                <div key={r.employee_id} data-testid={`visits-kpi-${r.employee_id}`} className="px-3 py-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[12.5px] font-semibold truncate">{r.employee_name}</span>
                    <span className="text-[11px] tabular-nums text-[#6B6B73]">{fmtMin(r.total_minutes)}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-[11.5px] text-[#6B6B73]">
                    <span>Kunjungan: <b className="tabular-nums text-[#0058CC]">{r.total}</b></span>
                    <span>Selesai: <b className="tabular-nums">{r.done}</b></span>
                    <span>Pesanan: <b className="tabular-nums text-[#1F9D55]">{r.with_order}</b></span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function VisitsView({ currentUser, selectedEntity }) {
  if (currentUser?.role === "sales") {
    return (
      <div data-testid="my-visits-view">
        <MyVisitsPanel currentUser={currentUser} />
        <MyVisitsHistory />
      </div>
    );
  }
  return <VisitsLog currentUser={currentUser} selectedEntity={selectedEntity} />;
}
