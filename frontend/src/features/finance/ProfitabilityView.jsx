/**
 * ProfitabilityView (FINANCE) — Analisis Profitabilitas / Margin (WAC).
 * Dimensi: Produk · Kategori · Pelanggan · Sales. Sumber: /api/finance/profitability.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ComposedChart, BarChart, Bar, Line, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import {
  RefreshCw, TrendingUp, Coins, Percent, Boxes, Package, Layers3, Users, UserCog, Building2,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import {
  FC, NOW, ymd, compactIDR, entityParam, chartTooltip, fmtPct,
  KpiCard, Panel, EmptyState, formatCurrency,
} from "./financeShared";

const DIMS = [
  { id: "by_product", label: "Produk", icon: Package },
  { id: "by_category", label: "Kategori", icon: Layers3 },
  { id: "by_customer", label: "Pelanggan", icon: Users },
  { id: "by_sales", label: "Sales", icon: UserCog },
  { id: "by_entity", label: "Per-PT", icon: Building2 },
];

export default function ProfitabilityView({ selectedEntity }) {
  const [range, setRange] = useState({ start: `${NOW.getFullYear()}-01-01`, end: ymd(NOW) });
  const [dim, setDim] = useState("by_product");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { ...entityParam(selectedEntity) };
      if (range.start) params.start = range.start;
      if (range.end) params.end = range.end;
      const res = await axios.get(`${API}/finance/profitability`, { params });
      setData(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat analisis profitabilitas.");
    } finally { setLoading(false); }
  }, [selectedEntity, range]);

  useEffect(() => { load(); }, [load]);

  const tot = data?.totals || {};
  const rows = useMemo(() => (data?.[dim] || []), [data, dim]);
  const topRows = useMemo(() => rows.slice(0, 8).map((r) => ({
    ...r, short: r.name?.length > 16 ? `${r.name.slice(0, 15)}…` : r.name,
  })), [rows]);
  const monthly = data?.monthly || [];
  const hasData = (tot.revenue || 0) !== 0 || rows.length > 0;

  return (
    <div data-testid="profitability-view">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <KpiCard testId="prof-kpi-revenue" label="Pendapatan (Realisasi)" value={formatCurrency(tot.revenue)} icon={TrendingUp} accent={FC.revenue} tone="text-[#1B7F4B]" />
        <KpiCard testId="prof-kpi-cogs" label="HPP (WAC)" value={formatCurrency(tot.cogs)} icon={Coins} accent={FC.amber} tone="text-[#C77700]" sub={tot.landed_included ? `termasuk landed ${compactIDR(tot.cogs_landed || 0)}` : "tanpa landed cost"} />
        <KpiCard testId="prof-kpi-margin" label="Marjin Kotor" value={formatCurrency(tot.margin)} icon={Boxes} accent={FC.net} tone={(tot.margin ?? 0) >= 0 ? "text-[#6B219A]" : "text-[#C0392B]"} />
        <KpiCard testId="prof-kpi-marginpct" label="Marjin %" value={fmtPct(tot.margin_pct)} icon={Percent} accent={FC.teal} sub={`${tot.orders || 0} pesanan · ${Number(tot.qty || 0).toLocaleString("id-ID")} unit`} />
      </div>

      <div className="rounded-lg border border-[#EFF0F2] p-3 mb-3 bg-[#FCFCFD] flex flex-wrap items-end gap-3">
        <div><label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Dari</label>
          <input type="date" data-testid="prof-start" className="field py-1.5 text-[12px]" value={range.start}
            onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))} /></div>
        <div><label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Sampai</label>
          <input type="date" data-testid="prof-end" className="field py-1.5 text-[12px]" value={range.end}
            onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))} /></div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[10px] font-semibold text-[#6B219A] bg-[#F3EAFB] rounded-full px-2 py-1">Basis Biaya: WAC (incl. landed)</span>
          <button data-testid="prof-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
        </div>
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="prof-error" />

      {loading ? (
        <div className="grid gap-3" data-testid="prof-loading"><div className="h-[280px] bg-[#F5F5F7] rounded animate-pulse" /></div>
      ) : !hasData ? (
        <Panel title="Profitabilitas" icon={Boxes}><EmptyState icon={Boxes} title="Belum ada penjualan pada periode ini" hint="Pilih rentang tanggal lain atau pastikan ada Pesanan Penjualan terkonfirmasi." testId="prof-empty" /></Panel>
      ) : (
        <>
          <div className="grid lg:grid-cols-2 gap-3 mb-3">
            <Panel title="Tren Bulanan — Pendapatan, HPP & Marjin" icon={TrendingUp} testId="prof-trend">
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={monthly} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={FC.grid} />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={compactIDR} width={52} />
                  <Tooltip formatter={(v, n) => [formatCurrency(v), n]} {...chartTooltip} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="revenue" name="Pendapatan" fill={FC.revenue} radius={[4, 4, 0, 0]} maxBarSize={24} />
                  <Bar dataKey="cogs" name="HPP" fill={FC.amber} radius={[4, 4, 0, 0]} maxBarSize={24} />
                  <Line type="monotone" dataKey="margin" name="Marjin" stroke={FC.net} strokeWidth={2.5} dot={{ r: 2 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </Panel>
            <Panel title={`Top Marjin per ${DIMS.find((d) => d.id === dim)?.label}`} icon={Boxes} testId="prof-topchart">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={topRows} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={FC.grid} horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10 }} tickFormatter={compactIDR} />
                  <YAxis type="category" dataKey="short" tick={{ fontSize: 10 }} width={96} />
                  <Tooltip formatter={(v, n) => [formatCurrency(v), n]} {...chartTooltip} />
                  <Bar dataKey="margin" name="Marjin" radius={[0, 4, 4, 0]} maxBarSize={20}>
                    {topRows.map((r, i) => <Cell key={i} fill={r.margin >= 0 ? FC.net : FC.expense} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Panel>
          </div>

          <Panel title="Rincian Profitabilitas" icon={Boxes} testId="prof-table-panel"
            actions={
              <div className="flex items-center gap-1">
                {DIMS.map((d) => (
                  <button key={d.id} data-testid={`prof-dim-${d.id}`} onClick={() => setDim(d.id)}
                    className={`inline-flex items-center gap-1 text-[11px] font-semibold rounded-lg px-2.5 py-1 border transition-colors ${dim === d.id ? "bg-[#6B219A] text-white border-[#6B219A]" : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#D9C4EC]"}`}>
                    <d.icon size={12} />{d.label}
                  </button>
                ))}
              </div>
            }>
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]" data-testid="prof-table">
                <thead>
                  <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                    <th className="px-3 py-2">{DIMS.find((d) => d.id === dim)?.label}</th>
                    <th className="px-3 py-2 text-right">Pendapatan</th>
                    <th className="px-3 py-2 text-right">HPP Dasar</th>
                    <th className="px-3 py-2 text-right">Landed</th>
                    <th className="px-3 py-2 text-right">Total COGS</th>
                    <th className="px-3 py-2 text-right">Marjin</th>
                    <th className="px-3 py-2 text-right">Marjin %</th>
                    <th className="px-3 py-2 text-right">Qty</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={8} className="px-3 py-6 text-center text-[11px] text-[#8E8E93]">Tidak ada data.</td></tr>
                  ) : rows.map((r) => (
                    <tr key={r.key} data-testid={`prof-row-${r.key}`} className="border-b border-[#F5F5F7] last:border-0">
                      <td className="px-3 py-2 font-semibold text-[#1C1C1E] max-w-[240px] truncate" title={r.name}>{r.name}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#1B7F4B]">{formatCurrency(r.revenue)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#6B6B73]" data-testid={`prof-base-${r.key}`}>{formatCurrency(r.cogs_base)}</td>
                      <td className="px-3 py-2 text-right tabular-nums" data-testid={`prof-landed-${r.key}`}>
                        {(r.cogs_landed || 0) > 0
                          ? <span className="inline-block rounded bg-[#F0F5FF] text-[#1B4F9C] px-1.5 py-0.5 text-[11px] font-semibold" title="Komponen landed cost (freight/bea/handling)">{formatCurrency(r.cogs_landed)}</span>
                          : <span className="text-[#C7C7CC]">—</span>}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#C77700] font-medium">{formatCurrency(r.cogs)}</td>
                      <td className={`px-3 py-2 text-right tabular-nums font-semibold ${r.margin >= 0 ? "text-[#6B219A]" : "text-[#C0392B]"}`}>{formatCurrency(r.margin)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        <span className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-bold ${(r.margin_pct ?? 0) >= 20 ? "bg-[#EAF6EF] text-[#1B7F4B]" : (r.margin_pct ?? 0) >= 0 ? "bg-[#FBF3E5] text-[#C77700]" : "bg-[#FDECEC] text-[#C0392B]"}`}>{fmtPct(r.margin_pct)}</span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#6B6B73]">{Number(r.qty || 0).toLocaleString("id-ID")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
      <p className="mt-2 text-[11px] text-[#9A9BA3]">Marjin = Pendapatan baris SO − (WAC × qty). HPP memakai Weighted Average Cost per produk/entitas, <b>termasuk landed cost</b> (kolom Landed memisah komponen freight/bea/handling). Dimensi <b>Per-PT</b> menampilkan margin per entitas.</p>
    </div>
  );
}
