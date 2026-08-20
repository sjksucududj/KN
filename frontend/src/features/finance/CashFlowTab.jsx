/**
 * CashFlowTab (FINANCE) — Laporan Arus Kas (metode tak langsung).
 * Sumber: /api/finance/cash-flow (+ export.csv). Dipakai di FinancialStatementsView.
 */
import { useCallback, useEffect, useState } from "react";
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import {
  RefreshCw, Download, Waves, TrendingUp, Building2, Landmark, CheckCircle2, AlertTriangle, Wallet,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import {
  FC, NOW, ymd, compactIDR, entityParam, saveBlob, chartTooltip,
  KpiCard, Panel, EmptyState, formatCurrency,
} from "./financeShared";

export default function CashFlowTab({ selectedEntity }) {
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
      const res = await axios.get(`${API}/finance/cash-flow`, { params });
      setData(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Laporan Arus Kas.");
    } finally { setLoading(false); }
  }, [selectedEntity, range]);

  useEffect(() => { load(); }, [load]);

  const doExport = async () => {
    try {
      const res = await axios.get(`${API}/finance/cash-flow/export.csv`, {
        params: { ...entityParam(selectedEntity), start: range.start, end: range.end },
        responseType: "blob",
      });
      saveBlob(res.data, `arus-kas_${range.start}_${range.end}.csv`);
    } catch { setError("Gagal mengunduh CSV."); }
  };

  const op = data?.operating || {};
  const inv = data?.investing || {};
  const fin = data?.financing || {};
  const waterfall = data ? [
    { name: "Operasi", value: op.total || 0, fill: FC.revenue },
    { name: "Investasi", value: inv.total || 0, fill: FC.blue },
    { name: "Pendanaan", value: fin.total || 0, fill: FC.amber },
    { name: "Perub. Kas", value: data.net_change || 0, fill: FC.purple },
  ] : [];

  return (
    <div data-testid="fs-cash-flow">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <KpiCard testId="cf-kpi-begin" label="Kas Awal Periode" value={formatCurrency(data?.begin_cash)} icon={Wallet} accent={FC.muted} />
        <KpiCard testId="cf-kpi-operating" label="Kas Bersih Operasi" value={formatCurrency(op.total)} icon={TrendingUp} accent={FC.revenue} tone={(op.total ?? 0) >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"} />
        <KpiCard testId="cf-kpi-netchange" label="Perubahan Kas Bersih" value={formatCurrency(data?.net_change)} icon={Waves} accent={FC.purple} tone={(data?.net_change ?? 0) >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"} />
        <KpiCard testId="cf-kpi-end" label="Kas Akhir Periode" value={formatCurrency(data?.end_cash)} icon={Landmark} accent={FC.cash} tone="text-[#0058CC]" />
      </div>

      <div className="rounded-lg border border-[#EFF0F2] p-3 mb-3 bg-[#FCFCFD] flex flex-wrap items-end gap-3">
        <div><label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Dari Tanggal</label>
          <input type="date" data-testid="cf-start" className="field py-1.5 text-[12px]" value={range.start}
            onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))} /></div>
        <div><label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Sampai Tanggal</label>
          <input type="date" data-testid="cf-end" className="field py-1.5 text-[12px]" value={range.end}
            onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))} /></div>
        <div className="ml-auto flex items-center gap-2">
          {data && (
            <span data-testid="cf-reconcile" className={`inline-flex items-center gap-1 text-[11px] font-semibold rounded-full px-2.5 py-1 ${data.reconciled ? "bg-[#EAF6EF] text-[#1B7F4B]" : "bg-[#FDECEC] text-[#C0392B]"}`}>
              {data.reconciled ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
              {data.reconciled ? "Terekonsiliasi" : "Selisih rekonsiliasi"}
            </span>
          )}
          <button data-testid="cf-export" onClick={doExport} className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1"><Download size={13} /> Ekspor CSV</button>
          <button data-testid="cf-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
        </div>
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="cf-error" />

      {loading ? (
        <div className="grid gap-2" data-testid="cf-loading">{[0, 1, 2, 3].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
      ) : !data ? null : (
        <div className="grid lg:grid-cols-5 gap-3">
          <div className="lg:col-span-2">
            <Panel title="Kontribusi Arus Kas" icon={Waves} testId="cf-chart">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={waterfall} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={FC.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={compactIDR} width={52} />
                  <Tooltip formatter={(v) => formatCurrency(v)} {...chartTooltip} />
                  <ReferenceLine y={0} stroke="#C7C7CC" />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={44}>
                    {waterfall.map((d, i) => <Cell key={i} fill={d.value >= 0 ? d.fill : FC.expense} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Panel>
          </div>
          <div className="lg:col-span-3">
            <div className="overflow-auto rounded-xl border border-[#EFF0F2]" data-testid="cf-table">
              <table className="w-full text-[12px]">
                <tbody>
                  <SectionRows label={op.label} testId="op"
                    lead={{ name: op.net_income_label, amount: op.net_income }}
                    lines={op.working_capital} total={op.total} />
                  <SectionRows label={inv.label} testId="inv" lines={inv.lines} total={inv.total} />
                  <SectionRows label={fin.label} testId="fin" lines={fin.lines} total={fin.total} />
                  <tr className="border-t-2 border-[#E4E4EA] bg-[#F3EAFB]">
                    <td className="px-3 py-2.5 font-bold text-[#1C1C1E]">KENAIKAN/(PENURUNAN) KAS BERSIH</td>
                    <td className="px-3 py-2.5 text-right tabular-nums font-bold text-[#6B219A]" data-testid="cf-net-change">{formatCurrency(data.net_change)}</td>
                  </tr>
                  <tr className="border-b border-[#F5F5F7]"><td className="px-3 py-1.5 pl-6 text-[#6B6B73]">Kas Awal Periode</td><td className="px-3 py-1.5 text-right tabular-nums text-[#6B6B73]">{formatCurrency(data.begin_cash)}</td></tr>
                  <tr><td className="px-3 py-2 font-bold text-[#1C1C1E]">Kas Akhir Periode</td><td className="px-3 py-2 text-right tabular-nums font-bold text-[#0058CC]" data-testid="cf-end-cash">{formatCurrency(data.end_cash)}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
      <p className="mt-2 text-[11px] text-[#9A9BA3]">Metode tak langsung — diturunkan dari GL (jurnal non-void, exclude penutup). Kas & setara kas = Kas Besar/Bank + Kas Kecil.</p>
    </div>
  );
}

function SectionRows({ label, lead, lines, total, testId }) {
  const arr = lines || [];
  return (
    <>
      <tr className="bg-[#FAFBFC] border-y border-[#EFF0F2]"><td colSpan={2} className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B219A]">{label}</td></tr>
      {lead && (
        <tr className="border-b border-[#F5F5F7]" data-testid={`cf-${testId}-lead`}>
          <td className="px-3 py-1.5 pl-6 text-[#3C3C43]">{lead.name}</td>
          <td className="px-3 py-1.5 text-right tabular-nums text-[#1C1C1E]">{formatCurrency(lead.amount)}</td>
        </tr>
      )}
      {arr.length === 0 && !lead ? (
        <tr><td colSpan={2} className="px-3 py-1.5 pl-6 text-[11px] text-[#9A9BA3]">Tidak ada perubahan.</td></tr>
      ) : arr.map((ln) => (
        <tr key={ln.code} className="border-b border-[#F5F5F7]">
          <td className="px-3 py-1.5 pl-6 text-[#3C3C43]"><span className="text-[10px] text-[#9A9BA3] mr-1.5">{ln.code}</span>{ln.name}</td>
          <td className={`px-3 py-1.5 text-right tabular-nums ${ln.amount >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}>{formatCurrency(ln.amount)}</td>
        </tr>
      ))}
      <tr className="border-b border-[#EFF0F2] bg-[#FCFCFD]">
        <td className="px-3 py-1.5 pl-6 font-semibold text-[#1C1C1E]">Kas Bersih dari {label?.replace("Arus Kas dari ", "")}</td>
        <td className="px-3 py-1.5 text-right tabular-nums font-bold text-[#1C1C1E]" data-testid={`cf-${testId}-total`}>{formatCurrency(total)}</td>
      </tr>
    </>
  );
}
