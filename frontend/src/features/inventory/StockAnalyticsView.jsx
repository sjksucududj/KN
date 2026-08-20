import { useEffect, useMemo, useState } from "react";
import {
  PieChart, Pie, Cell, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  TrendingUp, Boxes, Snowflake, Flame, Clock, RefreshCw, PackageX, Search, Layers,
} from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import axios, { API } from "../../services/apiClient";

const fmt = new Intl.NumberFormat("id-ID");
const fmtQty = (v) => fmt.format(Math.round((v || 0) * 100) / 100);
function fmtShort(v) {
  const n = Math.round(v || 0);
  if (n >= 1e9) return `Rp ${(n / 1e9).toFixed(1)} M`;
  if (n >= 1e6) return `Rp ${(n / 1e6).toFixed(1)} jt`;
  if (n >= 1e3) return `Rp ${(n / 1e3).toFixed(0)} rb`;
  return `Rp ${n}`;
}
const fmtCur = (v) => `Rp ${fmt.format(Math.round(v || 0))}`;

const CLASS_META = {
  fast: { label: "Fast Moving", color: "#34C759", icon: Flame },
  slow: { label: "Slow Moving", color: "#FF9500", icon: Clock },
  dead: { label: "Stok Mati", color: "#C0341D", icon: Snowflake },
};

function KPICard({ icon: Icon, label, value, sub, color = "#0058CC", loading, testId, active, onClick }) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={`text-left rounded-xl border bg-white p-4 flex flex-col gap-2 transition-all ${
        active ? "border-[#0058CC] ring-2 ring-[#0058CC]/20" : "border-[#EFF0F2] hover:border-[#D0D0D5]"
      } ${onClick ? "cursor-pointer" : "cursor-default"}`}
    >
      <div className="flex items-center gap-2">
        <div className="rounded-lg p-1.5" style={{ background: `${color}18` }}><Icon size={16} style={{ color }} /></div>
        <span className="text-[12px] font-semibold text-[#6B6B73]">{label}</span>
      </div>
      {loading ? <div className="h-7 bg-[#F5F5F7] rounded animate-pulse" />
        : <p className="text-[22px] font-bold text-[#1C1C1E] tabular-nums leading-tight">{value}</p>}
      {sub && <p className="text-[11px] text-[#6B6B73]">{sub}</p>}
    </button>
  );
}

function Panel({ title, right, children }) {
  return (
    <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[13px] font-bold text-[#1C1C1E]">{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

function ClassBadge({ cls, neverSold }) {
  const m = CLASS_META[cls] || CLASS_META.slow;
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold"
          style={{ background: `${m.color}18`, color: m.color }}>
      <m.icon size={11} /> {m.label}{neverSold ? " • blm terjual" : ""}
    </span>
  );
}

export default function StockAnalyticsView({ currentUser, selectedEntity }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [warehouses, setWarehouses] = useState([]);
  const [warehouseId, setWarehouseId] = useState("all");
  const [category, setCategory] = useState("all");
  const [classFilter, setClassFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    axios.get(`${API}/warehouses`).then((r) => setWarehouses(r.data || [])).catch(() => {});
  }, []);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const ent = selectedEntity && selectedEntity !== "all" ? selectedEntity : "all";
      const params = { entity_id: ent };
      if (warehouseId && warehouseId !== "all") params.warehouse_id = warehouseId;
      if (category && category !== "all") params.category = category;
      const r = await axios.get(`${API}/inventory/stock-analytics`, { params });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || "Gagal memuat Stock Analytics");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [selectedEntity, warehouseId, category]); // eslint-disable-line

  const summary = data?.summary || {};
  const byClass = summary.by_class || {};
  const rows = data?.rows || [];
  const th = data?.thresholds || {};

  const categoryOpts = useMemo(() => {
    const set = new Set(rows.map((r) => r.category).filter(Boolean));
    return [{ value: "all", label: "Semua Kategori" }, ...[...set].sort().map((c) => ({ value: c, label: c }))];
  }, [rows]);
  const warehouseOpts = [{ value: "all", label: "Semua Gudang" },
    ...warehouses.map((w) => ({ value: w.id, label: w.name }))];

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) =>
      (classFilter === "all" || r.classification === classFilter) &&
      (!q || `${r.sku} ${r.product_name}`.toLowerCase().includes(q))
    );
  }, [rows, classFilter, search]);

  const pieData = ["fast", "slow", "dead"]
    .map((c) => ({ name: CLASS_META[c].label, key: c, value: byClass[c]?.value || 0, color: CLASS_META[c].color }))
    .filter((d) => d.value > 0);
  const agingData = (summary.aging_buckets || []).map((b) => ({ name: b.bucket, value: b.value || 0 }));
  const hasAgingValue = agingData.some((a) => a.value > 0);

  return (
    <div data-testid="stock-analytics-view" className="space-y-4">
      {/* Header + filters */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[12px] font-semibold text-[#0058CC] tracking-wide">GUDANG</p>
          <h1 className="text-[20px] font-bold text-[#1C1C1E] flex items-center gap-2">
            <TrendingUp size={20} className="text-[#0058CC]" /> Analitik Stok — Cepat / Lambat / Mati
          </h1>
          <p className="text-[12px] text-[#6B6B73] mt-0.5">
            Klasifikasi per SKU berdasar penjualan terakhir. Ambang: Fast ≤ {th.fast_max_days ?? 30}h · Slow ≤ {th.slow_max_days ?? 90}h · Dead &gt; {th.slow_max_days ?? 90}h · jendela velocity {th.velocity_window_days ?? 90}h.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <KNSelect data-testid="sa-warehouse-filter" value={warehouseId} onValueChange={setWarehouseId}
            options={warehouseOpts} className="field !py-1 !px-2 text-[12px] w-auto" placeholder="Gudang" />
          <KNSelect data-testid="sa-category-filter" value={category} onValueChange={setCategory}
            options={categoryOpts} className="field !py-1 !px-2 text-[12px] w-auto" placeholder="Kategori" />
          <button data-testid="sa-refresh" onClick={load}
            className="flex items-center gap-1 rounded-lg border border-[#EFF0F2] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#1C1C1E] hover:bg-[#F5F5F7]">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {error && <ErrorNotice message={error} onRetry={load} />}

      {/* KPI row (klik untuk filter kelas) */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <KPICard testId="sa-kpi-total-value" icon={Boxes} label="Nilai Persediaan" color="#0058CC" loading={loading}
          value={fmtShort(summary.total_on_hand_value)} sub={`${summary.sku_count ?? 0} SKU`}
          active={classFilter === "all"} onClick={() => setClassFilter("all")} />
        <KPICard testId="sa-kpi-fast" icon={Flame} label="Fast Moving" color="#34C759" loading={loading}
          value={byClass.fast?.count ?? 0} sub={fmtShort(byClass.fast?.value)}
          active={classFilter === "fast"} onClick={() => setClassFilter("fast")} />
        <KPICard testId="sa-kpi-slow" icon={Clock} label="Slow Moving" color="#FF9500" loading={loading}
          value={byClass.slow?.count ?? 0} sub={fmtShort(byClass.slow?.value)}
          active={classFilter === "slow"} onClick={() => setClassFilter("slow")} />
        <KPICard testId="sa-kpi-dead" icon={Snowflake} label="Stok Mati" color="#C0341D" loading={loading}
          value={byClass.dead?.count ?? 0} sub={fmtShort(byClass.dead?.value)}
          active={classFilter === "dead"} onClick={() => setClassFilter("dead")} />
        <KPICard testId="sa-kpi-neversold" icon={PackageX} label="Belum Pernah Terjual" color="#8E8E93" loading={loading}
          value={summary.never_sold_skus ?? 0} sub="perlu strategi jual" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Distribusi Nilai per Klasifikasi">
          {pieData.length === 0 ? (
            <EmptyBox icon={Layers} text="Belum ada data persediaan untuk ditampilkan." />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={(e) => e.name}>
                  {pieData.map((d) => <Cell key={d.key} fill={d.color} />)}
                </Pie>
                <Tooltip formatter={(v) => fmtCur(v)} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Panel>
        <Panel title="Umur Persediaan (nilai per umur)" right={<span className="text-[11px] text-[#6B6B73]">hari sejak masuk gudang</span>}>
          {!hasAgingValue ? (
            <EmptyBox icon={Clock} text="Belum ada nilai persediaan untuk di-aging." />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={agingData} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F2" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={fmtShort} tick={{ fontSize: 10 }} width={60} />
                <Tooltip formatter={(v) => fmtCur(v)} />
                <Bar dataKey="value" fill="#0058CC" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>
      </div>

      {/* Table */}
      <Panel
        title="Rincian per SKU"
        right={
          <div className="relative">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#8E8E93]" />
            <input data-testid="sa-search" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Cari SKU / nama…"
              className="pl-7 pr-2 py-1 text-[12px] rounded-lg border border-[#EFF0F2] bg-white w-44" />
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-[#6B6B73] border-b border-[#EFF0F2]">
                <th className="py-2 pr-3 font-semibold">Klasifikasi</th>
                <th className="py-2 pr-3 font-semibold">SKU / Produk</th>
                <th className="py-2 pr-3 font-semibold">Gudang</th>
                <th className="py-2 pr-3 font-semibold text-right">Stok fisik</th>
                <th className="py-2 pr-3 font-semibold text-right">Nilai</th>
                <th className="py-2 pr-3 font-semibold text-right">Terjual ({th.velocity_window_days ?? 90}h)</th>
                <th className="py-2 pr-3 font-semibold text-right">Jual terakhir</th>
                <th className="py-2 pr-3 font-semibold text-right">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} className="border-b border-[#F5F5F7]">
                    <td colSpan={8} className="py-2"><div className="h-5 bg-[#F5F5F7] rounded animate-pulse" /></td>
                  </tr>
                ))
              ) : filteredRows.length === 0 ? (
                <tr><td colSpan={8}><EmptyBox icon={Boxes} text="Tidak ada SKU sesuai filter." /></td></tr>
              ) : (
                filteredRows.map((r) => (
                  <tr key={r.product_id} data-testid={`sa-row-${r.product_id}`} className="border-b border-[#F5F5F7] hover:bg-[#FAFAFB]">
                    <td className="py-2 pr-3"><ClassBadge cls={r.classification} neverSold={r.never_sold} /></td>
                    <td className="py-2 pr-3">
                      <p className="font-semibold text-[#1C1C1E]">{r.sku}</p>
                      <p className="text-[11px] text-[#6B6B73]">{r.product_name}</p>
                    </td>
                    <td className="py-2 pr-3 text-[11px] text-[#6B6B73]">{r.warehouses?.join(", ") || "—"}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmtQty(r.on_hand_qty)} {r.unit}</td>
                    <td className="py-2 pr-3 text-right tabular-nums font-semibold">{fmtShort(r.value)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmtQty(r.sold_qty_window)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {r.days_since_sale == null ? <span className="text-[#8E8E93]">belum</span> : `${r.days_since_sale} hr lalu`}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {r.days_of_supply == null ? <span className="text-[#8E8E93]">∞</span> : `${fmtQty(r.days_of_supply)} hr`}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function EmptyBox({ icon: Icon, text }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="rounded-full bg-[#F5F5F7] p-3"><Icon size={22} className="text-[#8E8E93]" /></div>
      <p className="text-[12px] text-[#6B6B73] max-w-xs">{text}</p>
    </div>
  );
}
