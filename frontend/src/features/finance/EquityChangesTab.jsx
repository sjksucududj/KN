/**
 * EquityChangesTab (FINANCE) — Laporan Perubahan Ekuitas (Statement of Changes in Equity).
 * Sumber: /api/finance/equity-changes (+ export.csv). Dipakai di FinancialStatementsView.
 */
import { useCallback, useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { RefreshCw, Download, PiggyBank, TrendingUp, Landmark, ArrowRightLeft } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import {
  FC, NOW, ymd, compactIDR, entityParam, saveBlob, chartTooltip,
  KpiCard, Panel, EmptyState, formatCurrency,
} from "./financeShared";

export default function EquityChangesTab({ selectedEntity }) {
  const [range, setRange] = useState({ start: `${NOW.getFullYear()}-01-01`, end: ymd(NOW) });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { ...entityParam(selectedEntity) };
      if (range.start) params.start = range.start;
      if (range.end) params.end = range.end;
      const res = await axios.get(`${API}/finance/equity-changes`, { params });
      setData(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Laporan Perubahan Ekuitas.");
    } finally { setLoading(false); }
  }, [selectedEntity, range]);

  useEffect(() => { load(); }, [load]);

  const doExport = async () => {
    try {
      const res = await axios.get(`${API}/finance/equity-changes/export.csv`, {
        params: { ...entityParam(selectedEntity), start: range.start, end: range.end },
        responseType: "blob",
      });
      saveBlob(res.data, `perubahan-ekuitas_${range.start}_${range.end}.csv`);
    } catch { setError("Gagal mengunduh CSV."); }
  };

  const comps = data?.components || [];
  const chartData = comps
    .filter((c) => c.begin || c.end)
    .map((c) => ({
      name: c.name?.length > 16 ? `${c.name.slice(0, 15)}…` : c.name,
      "Saldo Awal": c.begin, "Saldo Akhir": c.end,
    }));

  return (
    <div data-testid="fs-equity-changes">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <KpiCard testId="eq-kpi-begin" label="Ekuitas Awal" value={formatCurrency(data?.begin_total)} icon={Landmark} accent={FC.muted} />
        <KpiCard testId="eq-kpi-netincome" label="Laba Periode Berjalan" value={formatCurrency(data?.net_income)} icon={TrendingUp} accent={FC.revenue} tone={(data?.net_income ?? 0) >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"} />
        <KpiCard testId="eq-kpi-movement" label="Total Pergerakan" value={formatCurrency(data?.movement_total)} icon={ArrowRightLeft} accent={FC.purple} tone={(data?.movement_total ?? 0) >= 0 ? "text-[#6B219A]" : "text-[#C0392B]"} />
        <KpiCard testId="eq-kpi-end" label="Ekuitas Akhir" value={formatCurrency(data?.end_total)} icon={PiggyBank} accent={FC.cash} tone="text-[#0058CC]" />
      </div>

      <div className="rounded-lg border border-[#EFF0F2] p-3 mb-3 bg-[#FCFCFD] flex flex-wrap items-end gap-3">
        <div><label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Dari Tanggal</label>
          <input type="date" data-testid="eq-start" className="field py-1.5 text-[12px]" value={range.start}
            onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))} /></div>
        <div><label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Sampai Tanggal</label>
          <input type="date" data-testid="eq-end" className="field py-1.5 text-[12px]" value={range.end}
            onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))} /></div>
        <div className="ml-auto flex items-center gap-2">
          <button data-testid="eq-export" onClick={doExport} className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1"><Download size={13} /> Ekspor CSV</button>
          <button data-testid="eq-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
        </div>
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="eq-error" />

      {loading ? (
        <div className="h-[280px] bg-[#F5F5F7] rounded animate-pulse" data-testid="eq-loading" />
      ) : !data ? (
        /* FASE P5 — dulu `null`: layar KOSONG tanpa satu kata pun, sehingga pengguna tidak
           bisa membedakan "belum ada data ekuitas" dari "masih memuat" atau "gagal". */
        <EmptyState icon={PiggyBank} testId="eq-empty"
          title="Belum ada data perubahan ekuitas untuk rentang ini"
          hint="Coba lebarkan rentang tanggal, atau pastikan sudah ada jurnal pada periode tersebut." />
      ) : (
        <div className="grid lg:grid-cols-5 gap-3">
          <div className="lg:col-span-2">
            <Panel title="Ekuitas: Saldo Awal vs Akhir" icon={PiggyBank} testId="eq-chart">
              {/* FASE P5 — grafik tanpa data dulu tampil sebagai kotak kosong bergaris:
                  terlihat seperti grafik yang RUSAK. Sekarang kekosongannya dijelaskan. */}
              {chartData.length === 0 ? (
                <EmptyState icon={PiggyBank} testId="eq-chart-empty"
                  title="Belum ada komponen ekuitas bergerak"
                  hint="Grafik muncul begitu ada saldo awal atau saldo akhir pada rentang ini." />
              ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={FC.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-12} textAnchor="end" height={54} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={compactIDR} width={52} />
                  <Tooltip formatter={(v, n) => [formatCurrency(v), n]} {...chartTooltip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="Saldo Awal" fill={FC.muted} radius={[4, 4, 0, 0]} maxBarSize={20} />
                  <Bar dataKey="Saldo Akhir" fill={FC.purple} radius={[4, 4, 0, 0]} maxBarSize={20} />
                </BarChart>
              </ResponsiveContainer>
              )}
            </Panel>
          </div>
          <div className="lg:col-span-3">
            <div className="overflow-auto rounded-xl border border-[#EFF0F2]" data-testid="eq-table">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                    <th className="px-3 py-2">Komponen Ekuitas</th>
                    <th className="px-3 py-2 text-right">Saldo Awal</th>
                    <th className="px-3 py-2 text-right">Pergerakan</th>
                    <th className="px-3 py-2 text-right">Saldo Akhir</th>
                  </tr>
                </thead>
                <tbody>
                  {comps.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-3 py-4 text-center text-[11px] text-[#9A9BA3]">
                        Belum ada komponen ekuitas pada rentang tanggal ini.
                      </td>
                    </tr>
                  )}
                  {comps.map((c) => (
                    <tr key={c.code} data-testid={`eq-row-${c.code}`} className="border-b border-[#F5F5F7] last:border-0">
                      <td className="px-3 py-2 font-semibold text-[#1C1C1E]">
                        {c.code !== "__pl__" && <span className="text-[10px] text-[#9A9BA3] mr-1.5">{c.code}</span>}{c.name}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#6B6B73]">{formatCurrency(c.begin)}</td>
                      <td className={`px-3 py-2 text-right tabular-nums font-medium ${c.movement >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}>{formatCurrency(c.movement)}</td>
                      <td className="px-3 py-2 text-right tabular-nums font-semibold text-[#1C1C1E]">{formatCurrency(c.end)}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-[#E4E4EA] bg-[#F3EAFB]">
                    <td className="px-3 py-2.5 font-bold text-[#1C1C1E]">TOTAL EKUITAS</td>
                    <td className="px-3 py-2.5 text-right tabular-nums font-bold text-[#6B6B73]">{formatCurrency(data.begin_total)}</td>
                    <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${data.movement_total >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}`} data-testid="eq-movement-total">{formatCurrency(data.movement_total)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums font-bold text-[#0058CC]" data-testid="eq-end-total">{formatCurrency(data.end_total)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
      <p className="mt-2 text-[11px] text-[#9A9BA3]">Diturunkan dari Neraca (rekonsiliasi penuh). Ekuitas Akhir = Ekuitas Awal + Pergerakan modal + Laba periode berjalan.</p>
    </div>
  );
}
