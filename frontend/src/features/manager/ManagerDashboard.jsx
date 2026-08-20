import { useEffect, useState } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from "recharts";
import {
  TrendingUp, Package, Users, Warehouse, AlertTriangle,
  Clock, CheckCircle, Star, RefreshCw, ArrowUpRight, ArrowDownRight
} from "lucide-react";
import KNSelect from "../../components/KNSelect";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";

const STATUS_COLORS = {
  draft: "#8E8E93", reserved: "#007AFF", waiting_approval: "#FF9500",
  approved: "#34C759", confirmed: "#30D158", done: "#1C7C4A",
  cancelled: "#FF3B30", expired: "#FF6B00", shipped: "#5856D6",
};

const CHART_COLORS = ["#007AFF", "#34C759", "#FF9500", "#FF3B30", "#5856D6", "#FF6B00", "#8E8E93"];

function KPICard({ icon: Icon, label, value, sub, color = "#007AFF", trend, loading }) {
  return (
    <div data-testid={`kpi-${label.toLowerCase().replace(/\s+/g, "-")}`}
      className="rounded-xl border border-[#EFF0F2] bg-white p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="rounded-lg p-1.5" style={{ background: `${color}18` }}>
            <Icon size={16} style={{ color }} />
          </div>
          <span className="text-[12px] font-semibold text-[#6B6B73]">{label}</span>
        </div>
        {trend !== undefined && (
          <span className={`text-[11px] font-bold flex items-center gap-0.5 ${
            trend >= 0 ? "text-green-600" : "text-red-600"
          }`}>
            {trend >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {Math.abs(trend)}%
          </span>
        )}
      </div>
      {loading ? (
        <div className="h-7 bg-[#F5F5F7] rounded animate-pulse" />
      ) : (
        <p className="text-2xl font-bold text-[#1C1C1E]">{value}</p>
      )}
      {sub && <p className="text-[11px] text-[#6B6B73]">{sub}</p>}
    </div>
  );
}

const fmt = new Intl.NumberFormat("id-ID");
const fmtCur = (v) => `Rp ${fmt.format(v)}`;

export default function ManagerDashboard({ token, selectedEntity }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState(30);
  const [summary, setSummary] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [velocity, setVelocity] = useState(null);
  const [topCustomers, setTopCustomers] = useState([]);
  const [utilization, setUtilization] = useState([]);
  const [aging, setAging] = useState([]);
  const [agingDays, setAgingDays] = useState(30);

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const load = async () => {
    setLoading(true);
    // F0-E: laporan ter-scope per entitas aktif ('all' = oversight lintas-PT).
    const ent = selectedEntity || "all";
    const cfg = { headers, params: { entity_id: ent } };
    try {
      const [sumRes, funnelRes, velRes, custRes, utilRes, agingRes] = await Promise.all([
        axios.get(`${API}/reports/summary`, cfg),
        axios.get(`${API}/reports/reservation-funnel`, cfg),
        axios.get(`${API}/reports/order-velocity?days=${period}`, cfg),
        axios.get(`${API}/reports/top-customers?limit=10`, cfg),
        axios.get(`${API}/reports/warehouse-utilization`, cfg),
        axios.get(`${API}/reports/stock-aging?days_threshold=${agingDays}`, cfg),
      ]);
      setSummary(sumRes.data);
      setFunnel(funnelRes.data);
      setVelocity(velRes.data);
      setTopCustomers(Array.isArray(custRes.data) ? custRes.data : []);
      setUtilization(Array.isArray(utilRes.data) ? utilRes.data : []);
      setAging(Array.isArray(agingRes.data) ? agingRes.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat dashboard. Periksa koneksi lalu coba lagi.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [period, agingDays, selectedEntity]);

  const funnelChartData = (funnel?.funnel || []).filter(f => !["cancelled", "expired"].includes(f.status));
  const velocityData = (velocity?.velocity || []).slice(-14); // last 14 days
  const utilizationData = utilization.map(w => ({
    name: w.warehouse_city || w.warehouse_name,
    on_hand: w.on_hand_qty,
    capacity: w.total_capacity,
    pct: w.utilization_pct,
  }));

  return (
    <section data-testid="manager-dashboard" className="section-card">
      <div className="section-head">
        <p className="text-[12px] text-[#6B6B73] min-w-0 truncate">Kinerja tim & operasi — {period} hari terakhir</p>
        <div className="flex items-center gap-2 flex-shrink-0">
          <KNSelect
            value={String(period)}
            onValueChange={(v) => setPeriod(Number(v))}
            className="field !py-1 !px-2 text-[12px] w-auto"
            options={[
              { value: "7",  label: "7 Hari" },
              { value: "14", label: "14 Hari" },
              { value: "30", label: "30 Hari" },
              { value: "60", label: "60 Hari" },
              { value: "90", label: "90 Hari" },
            ]}
          />
          <button onClick={load} className="secondary-button" data-testid="refresh-dashboard-button">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>
      <div className="section-body">
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="manager-dashboard-error" />
        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <KPICard icon={TrendingUp} label="Pesanan Hari Ini" value={summary?.orders_today ?? "—"} color="#007AFF" loading={loading} />
          <KPICard icon={Star} label="Pendapatan Bulan Ini" value={summary?.monthly_revenue !== undefined ? fmtCur(summary.monthly_revenue) : "—"} sub="30 hari terakhir" color="#34C759" loading={loading} />
          <KPICard icon={Clock} label="Menunggu Persetujuan" value={summary?.pending_approvals ?? "—"} sub="Perlu ditindak" color="#FF9500" loading={loading} />
          <KPICard icon={AlertTriangle} label="Stok Rendah" value={summary?.low_stock_items ?? "—"} sub="<100 unit tersedia" color="#FF3B30" loading={loading} />
          <KPICard icon={CheckCircle} label="Stock Opname Menunggu" value={summary?.pending_cycle_counts ?? "—"} sub="Menunggu review" color="#5856D6" loading={loading} />
        </div>

        {/* Order Velocity */}
        <div className="mt-5 rounded-xl border border-[#EFF0F2] bg-white p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-[14px] font-bold">Kecepatan Pesanan — {period} hari terakhir</h3>
            <span className="text-[12px] text-[#6B6B73]">{velocity?.total_orders ?? 0} order total • Avg {velocity?.avg_per_day ?? 0}/hari</span>
          </div>
          {loading ? (
            <div className="h-40 bg-[#F5F5F7] rounded animate-pulse" />
          ) : velocityData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={velocityData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EFF0F2" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={v => v.slice(5)} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip
                  formatter={(val, name) => [name === "total_amount" ? fmtCur(val) : val, name === "count" ? "Order" : "Revenue"]}
                  labelFormatter={l => `Tgl ${l}`}
                />
                <Line type="monotone" dataKey="count" stroke="#007AFF" strokeWidth={2} dot={false} name="count" />
                <Line type="monotone" dataKey="done" stroke="#34C759" strokeWidth={1.5} dot={false} strokeDasharray="4 2" name="done" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-40 flex items-center justify-center text-[13px] text-[#8E8E93]">Belum ada data pesanan untuk periode ini</div>
          )}
        </div>

        {/* Row: Funnel + Utilization */}
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {/* Reservation Funnel */}
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[14px] font-bold">Reservation Funnel</h3>
              <span className="text-[12px] text-[#6B6B73]">{funnel?.total_orders ?? 0} total</span>
            </div>
            {loading ? (
              <div className="h-36 bg-[#F5F5F7] rounded animate-pulse" />
            ) : funnelChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={170}>
                <BarChart data={funnelChartData} margin={{ top: 4, right: 8, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EFF0F2" />
                  <XAxis dataKey="status" tick={{ fontSize: 10 }} angle={-25} textAnchor="end" />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip formatter={(val) => [val, "Order"]} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {funnelChartData.map((entry, index) => (
                      <Cell key={entry.status} fill={STATUS_COLORS[entry.status] || CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-36 flex items-center justify-center text-[13px] text-[#8E8E93]">Belum ada data pesanan</div>
            )}
          </div>

          {/* Warehouse Utilization */}
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
            <h3 className="text-[14px] font-bold mb-3">Utilisasi Gudang</h3>
            {loading ? (
              <div className="h-36 bg-[#F5F5F7] rounded animate-pulse" />
            ) : utilizationData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={140}>
                  <BarChart data={utilizationData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#EFF0F2" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip formatter={(val, name) => [fmt.format(val), name === "on_hand" ? "On Hand" : "Kapasitas"]} />
                    <Bar dataKey="capacity" fill="#EFF0F2" name="capacity" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="on_hand" fill="#007AFF" name="on_hand" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
                <div className="mt-2 grid gap-1.5">
                  {utilization.map(w => (
                    <div key={w.warehouse_id} className="flex items-center gap-2">
                      <span className="text-[11px] text-[#6B6B73] w-32 truncate">{w.warehouse_name}</span>
                      <div className="flex-1 h-1.5 bg-[#EFF0F2] rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-[#007AFF]" style={{ width: `${Math.min(w.utilization_pct, 100)}%` }} />
                      </div>
                      <span className="text-[11px] font-bold text-[#1C1C1E] w-10 text-right">{w.utilization_pct}%</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="h-36 flex items-center justify-center text-[13px] text-[#8E8E93]">Belum ada data gudang</div>
            )}
          </div>
        </div>

        {/* Row: Top Customers + Stock Aging */}
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1.4fr]">
          {/* Top Customers */}
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
            <div className="flex items-center gap-2 mb-3">
              <Users size={15} className="text-[#007AFF]" />
              <h3 className="text-[14px] font-bold">Pelanggan Teratas</h3>
            </div>
            {loading ? (
              <div className="space-y-2">{[...Array(5)].map((_, i) => <div key={i} className="h-8 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
            ) : topCustomers.length > 0 ? (
              <div className="grid gap-1.5">
                {topCustomers.map((c, idx) => (
                  <div key={c.customer_id} className="flex items-center gap-2 py-1.5 border-b border-[#F5F5F7] last:border-0">
                    <span className="text-[11px] font-bold text-[#8E8E93] w-5">{idx + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-[12px] font-semibold truncate">{c.customer_name}</p>
                      <p className="text-[10.5px] text-[#6B6B73]">{c.order_count} pesanan</p>
                    </div>
                    <span className="text-[11px] font-bold text-[#007AFF] tabular-nums">{fmtCur(c.total_revenue)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="h-24 flex items-center justify-center text-[13px] text-[#8E8E93]">Belum ada data penjualan</div>
            )}
          </div>

          {/* Stock Aging */}
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Package size={15} className="text-[#FF9500]" />
                <h3 className="text-[14px] font-bold">Umur Stok</h3>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] text-[#6B6B73]">Min</span>
                <KNSelect
                  value={String(agingDays)}
                  onValueChange={(v) => setAgingDays(Number(v))}
                  className="field !py-0.5 !px-1.5 text-[11px] w-auto"
                  options={[
                    { value: "7",  label: "7 hari" },
                    { value: "14", label: "14 hari" },
                    { value: "30", label: "30 hari" },
                    { value: "60", label: "60 hari" },
                    { value: "90", label: "90 hari" },
                  ]}
                />
              </div>
            </div>
            {loading ? (
              <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-8 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
            ) : aging.length > 0 ? (
              <div className="grid gap-1 max-h-56 overflow-auto">
                <div className="grid grid-cols-[1fr_80px_60px_80px_80px] gap-2 text-[10px] font-bold uppercase text-[#8E8E93] pb-1 border-b border-[#EFF0F2]">
                  <span>Produk</span><span>Gudang</span><span>Stok Fisik</span><span>Hari</span><span>Nilai</span>
                </div>
                {aging.map((item, idx) => (
                  <div key={`${item.product_id}-${item.warehouse_id}-${item.lot || item.owner_entity_id || idx}`}
                    className="grid grid-cols-[1fr_80px_60px_80px_80px] gap-2 text-[11px] py-1.5 border-b border-[#F5F5F7] last:border-0">
                    <div className="min-w-0">
                      <p className="font-semibold truncate">{item.product_name}</p>
                      <p className="text-[10px] text-[#8E8E93]">{item.sku}</p>
                    </div>
                    <span className="text-[#6B6B73] truncate">{item.warehouse_city}</span>
                    <span className="font-semibold">{fmt.format(item.on_hand_qty)}</span>
                    <span className={`font-bold ${
                      (item.days_since_movement === null || item.days_since_movement > 60) ? "text-red-600"
                        : item.days_since_movement > 30 ? "text-orange-500"
                        : "text-[#1C1C1E]"
                    }`}>
                      {item.days_since_movement === null ? "Baru" : `${item.days_since_movement}h`}
                    </span>
                    <span className="text-[#3C3C43]">{fmtCur(item.estimated_value || 0)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="h-24 flex items-center justify-center text-[13px] text-[#8E8E93]">
                Semua stok aktif (tidak ada yang menua dalam {agingDays} hari)
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
