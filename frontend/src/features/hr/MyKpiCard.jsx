import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Target, TrendingUp } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { scoreCls, scoreBadge } from "./kpiUtils";

// ESS — kartu "KPI Saya" (karyawan lihat KPI sendiri). FASE H5 keputusan 4a.
export function MyKpiCard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState("");

  useEffect(() => { load(); }, []); // eslint-disable-line
  async function load() {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/hr/kpi/me`);
      setData(r.data || null);
      setPeriod(r.data?.latest_period || "");
    } catch (_) { /* noop */ } finally { setLoading(false); }
  }

  const all = data?.all || [];
  const periods = data?.periods || [];
  const shown = period ? all.filter((r) => r.period === period) : (data?.latest || []);
  const avg = period === data?.latest_period || !period ? (data?.latest_score ?? 0)
    : Math.round((shown.reduce((a, r) => a + (Number(r.score) || 0) * (Number(r.weight) || 1), 0) /
        (shown.reduce((a, r) => a + (Number(r.weight) || 1), 0) || 1)) * 10) / 10;
  const badge = scoreBadge(avg);

  return (
    <div className="section-card !p-4" data-testid="ess-kpi-card">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2"><Target size={15} className="text-[#0058CC]" /><h3 className="text-[12.5px] font-bold">KPI Saya</h3></div>
        {periods.length > 0 && (
          <div className="w-[120px]">
            <KNSelect data-testid="ess-kpi-period" value={period} onValueChange={setPeriod} options={periods.map((p) => ({ value: p, label: p }))} className="field !h-7 !text-[11px]" />
          </div>
        )}
      </div>
      {loading ? (
        <p className="text-[12px] text-[#6B6B73] py-3" data-testid="ess-kpi-loading">Memuat…</p>
      ) : shown.length === 0 ? (
        <p className="text-[11px] text-[#9A9BA3] py-3" data-testid="ess-kpi-empty">Belum ada KPI tercatat untuk Anda.</p>
      ) : (
        <div data-testid="ess-kpi-content">
          <div className="rounded-lg bg-[#F7F8FA] p-2.5 mb-2 flex items-center justify-between">
            <div>
              <p className="text-[10px] uppercase font-semibold text-[#9A9BA3]">Skor Rata-rata {period}</p>
              <p className={`text-[22px] font-bold tabular-nums leading-tight ${scoreCls(avg)}`} data-testid="ess-kpi-score">{avg}</p>
            </div>
            <span className={`px-2 py-1 rounded text-[11px] font-semibold ${badge.cls}`}>{badge.label}</span>
          </div>
          <div className="space-y-1 max-h-[150px] overflow-y-auto" data-testid="ess-kpi-list">
            {shown.map((r) => (
              <div key={r.id} className="flex items-center justify-between text-[11.5px] gap-2">
                <span className="flex items-center gap-1 min-w-0"><TrendingUp size={11} className="text-[#0058CC] shrink-0" /><span className="truncate">{r.metric}</span></span>
                <span className="flex items-center gap-2 shrink-0"><span className="text-[#9A9BA3] tabular-nums">{r.actual}/{r.target}</span><span className={`font-bold tabular-nums ${scoreCls(r.score)}`}>{r.score}</span></span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
