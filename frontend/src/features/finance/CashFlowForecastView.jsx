/**
 * CashFlowForecastView (FINANCE) — Proyeksi Arus Kas (AR/AP jatuh tempo).
 * Sumber: /api/finance/cashflow-forecast.
 */
import { useCallback, useEffect, useState } from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import {
  RefreshCw, Wallet, ArrowDownCircle, ArrowUpCircle, LineChart as LineIcon, Clock,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import {
  FC, compactIDR, entityParam, chartTooltip,
  KpiCard, Panel, EmptyState, formatCurrency,
} from "./financeShared";

export default function CashFlowForecastView({ selectedEntity }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/finance/cashflow-forecast`, { params: { ...entityParam(selectedEntity) } });
      setData(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat proyeksi kas.");
    } finally { setLoading(false); }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load]);

  const buckets = data?.buckets || [];
  const chartData = buckets.map((b) => ({
    label: b.label, inflow: b.inflow, outflow: -Math.abs(b.outflow), cumulative: b.cumulative_cash,
  }));
  const hasFlow = (data?.total_inflow || 0) !== 0 || (data?.total_outflow || 0) !== 0;

  return (
    <div data-testid="cashflow-forecast-view">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <KpiCard testId="fcst-kpi-cash" label="Kas Saat Ini" value={formatCurrency(data?.cash_now)} icon={Wallet} accent={FC.cash} tone="text-[#0058CC]" />
        <KpiCard testId="fcst-kpi-inflow" label="Estimasi Masuk (AR)" value={formatCurrency(data?.total_inflow)} icon={ArrowDownCircle} accent={FC.revenue} tone="text-[#1B7F4B]" />
        <KpiCard testId="fcst-kpi-outflow" label="Estimasi Keluar (AP)" value={formatCurrency(data?.total_outflow)} icon={ArrowUpCircle} accent={FC.expense} tone="text-[#C0392B]" />
        <KpiCard testId="fcst-kpi-projected" label="Proyeksi Kas Akhir" value={formatCurrency(data?.projected_cash)} icon={LineIcon} accent={FC.purple} tone={(data?.projected_cash ?? 0) >= 0 ? "text-[#6B219A]" : "text-[#C0392B]"} />
      </div>

      <div className="flex items-center justify-end mb-3">
        <button data-testid="fcst-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="fcst-error" />

      {loading ? (
        <div className="h-[300px] bg-[#F5F5F7] rounded animate-pulse" data-testid="fcst-loading" />
      ) : !data ? null : (
        <>
          <Panel title="Proyeksi Likuiditas per Bucket Jatuh Tempo" icon={LineIcon} testId="fcst-chart" className="mb-3">
            {!hasFlow ? (
              <EmptyState icon={Clock} title="Tidak ada piutang/hutang terbuka" hint="Semua tagihan sudah lunas atau belum ada transaksi jatuh tempo." testId="fcst-empty" />
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={FC.grid} />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={compactIDR} width={56} />
                  <Tooltip formatter={(v, n) => [formatCurrency(Math.abs(v)), n]} {...chartTooltip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <ReferenceLine y={0} stroke="#C7C7CC" />
                  <Bar dataKey="inflow" name="Masuk (AR)" fill={FC.revenue} radius={[4, 4, 0, 0]} maxBarSize={30} />
                  <Bar dataKey="outflow" name="Keluar (AP)" fill={FC.expense} radius={[0, 0, 4, 4]} maxBarSize={30} />
                  <Line type="monotone" dataKey="cumulative" name="Posisi Kas Kumulatif" stroke={FC.purple} strokeWidth={2.5} dot={{ r: 3 }} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </Panel>

          <div className="grid lg:grid-cols-2 gap-3">
            <DueList title="Piutang (AR) Jatuh Tempo" icon={ArrowDownCircle} items={data.ar_items} tone="in" testId="fcst-ar" />
            <DueList title="Hutang (AP) Jatuh Tempo" icon={ArrowUpCircle} items={data.ap_items} tone="out" testId="fcst-ap" />
          </div>
        </>
      )}
      <p className="mt-2 text-[11px] text-[#9A9BA3]">Jatuh tempo AR = tanggal pesanan + termin pelanggan; AP = tanggal jatuh tempo tagihan. Posisi kas awal = saldo GL Kas/Bank.</p>
    </div>
  );
}

function DueList({ title, icon: Icon, items, tone, testId }) {
  const arr = items || [];
  const color = tone === "in" ? "text-[#1B7F4B]" : "text-[#C0392B]";
  return (
    <Panel title={title} icon={Icon} testId={testId}>
      {arr.length === 0 ? (
        <p className="text-[11px] text-[#9A9BA3] py-4 text-center">Tidak ada tagihan terbuka.</p>
      ) : (
        <div className="overflow-auto max-h-[320px] rounded-md border border-[#EFF0F2]">
          <table className="w-full text-[12px]">
            <thead className="sticky top-0 bg-[#FAFBFC]">
              <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] border-b border-[#EFF0F2]">
                <th className="px-3 py-2">No</th><th className="px-3 py-2">Pihak</th>
                <th className="px-3 py-2 text-right">Nilai</th><th className="px-3 py-2 text-right">Jatuh Tempo</th>
              </tr>
            </thead>
            <tbody>
              {arr.map((it, i) => (
                <tr key={`${it.number}-${i}`} data-testid={`${testId}-row-${i}`} className="border-b border-[#F5F5F7] last:border-0">
                  <td className="px-3 py-1.5 font-semibold text-[#1C1C1E]">{it.number}</td>
                  <td className="px-3 py-1.5 text-[#6B6B73] max-w-[140px] truncate" title={it.party}>{it.party}</td>
                  <td className={`px-3 py-1.5 text-right tabular-nums font-semibold ${color}`}>{formatCurrency(it.amount)}</td>
                  <td className="px-3 py-1.5 text-right text-[11px]">
                    <span className={it.days_to_due < 0 ? "text-[#C0392B] font-semibold" : "text-[#6B6B73]"}>{it.due_date}</span>
                    {it.days_to_due < 0 && <span className="block text-[9px] text-[#C0392B]">telat {Math.abs(it.days_to_due)}h</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
