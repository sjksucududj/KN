import { useEffect, useState, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  Wallet, TrendingUp, Target, Banknote, AlertTriangle, Users,
  ShoppingBag, RefreshCw, ArrowUpRight, Receipt,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";

const fmt = new Intl.NumberFormat("id-ID");
const fmtCur = (v) => `Rp ${fmt.format(Math.round(v || 0))}`;

const CREDIT_TONE = {
  ok: { label: "Aman", cls: "text-green-700 bg-green-50" },
  warning: { label: "Waspada", cls: "text-orange-600 bg-orange-50" },
  blocked: { label: "Blokir", cls: "text-red-600 bg-red-50" },
};

function KPICard({ icon: Icon, label, value, sub, color = "#007AFF", loading }) {
  return (
    <div data-testid={`kpi-${label.toLowerCase().replace(/\s+/g, "-")}`}
      className="rounded-xl border border-[#EFF0F2] bg-white p-4 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="rounded-lg p-1.5" style={{ background: `${color}18` }}>
          <Icon size={16} style={{ color }} />
        </div>
        <span className="text-[12px] font-semibold text-[#6B6B73]">{label}</span>
      </div>
      {loading ? (
        <div className="h-7 bg-[#F5F5F7] rounded animate-pulse" />
      ) : (
        <p className="text-2xl font-bold text-[#1C1C1E] tabular-nums">{value}</p>
      )}
      {sub && <p className="text-[11px] text-[#6B6B73]">{sub}</p>}
    </div>
  );
}

export default function SalesHome({ token, user, onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  const headers = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/home/sales`, { headers });
      setData(res.data);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Performa Saya. Coba lagi.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const comm = data?.commission || {};
  const target = data?.target || {};
  const kpi = data?.kpi || {};
  const achievement = Math.min(target.achievement_pct || 0, 100);
  const history = (data?.history || []).map((h) => ({
    period: (h.period || "").slice(5),
    incentive: h.total_incentive ?? h.commission ?? 0,
  }));

  return (
    <section data-testid="sales-home" className="section-card">
      <div className="section-head">
        <p className="text-[12px] text-[#6B6B73] min-w-0 truncate">Komisi, target & penagihan{data?.period ? ` — ${data.period}` : ""}</p>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={() => onNavigate && onNavigate("sales")} className="primary-button" data-testid="sales-home-new-order">
            <ShoppingBag size={14} /> Buat Pesanan
          </button>
          <button onClick={load} className="secondary-button" data-testid="sales-home-refresh">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <div className="section-body">
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="sales-home-error" />

        {/* KPI */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KPICard icon={Wallet} label="Komisi MTD" value={fmtCur(comm.mtd_accrual)} sub="Akrual berjalan" color="#34C759" loading={loading} />
          <KPICard icon={TrendingUp} label="Proyeksi Bulan" value={fmtCur(comm.projection_month_end)} sub="Estimasi akhir bulan" color="#007AFF" loading={loading} />
          <KPICard icon={Target} label="Capaian Target" value={`${target.achievement_pct || 0}%`} sub={fmtCur(target.amount)} color="#5856D6" loading={loading} />
          <KPICard icon={Banknote} label="Penjualan MTD" value={fmtCur(kpi.total_sales)} sub={`${kpi.orders_count || 0} pesanan`} color="#FF9500" loading={loading} />
          <KPICard icon={ArrowUpRight} label="Tertagih" value={fmtCur(kpi.total_collected)} sub={`${kpi.collection_rate || 0}% tertagih`} color="#30D158" loading={loading} />
          <KPICard icon={Receipt} label="Piutang Belum Lunas" value={fmtCur(kpi.ar_outstanding)} sub="Piutang berjalan" color="#007AFF" loading={loading} />
          <KPICard icon={AlertTriangle} label="Lewat Jatuh Tempo" value={fmtCur(kpi.overdue_amount)} sub="Jatuh tempo lewat" color="#FF3B30" loading={loading} />
          <KPICard icon={Users} label="Pelanggan Saya" value={kpi.customers_count || 0} sub={`${kpi.new_customers || 0} baru bulan ini`} color="#8E8E93" loading={loading} />
        </div>

        {/* Target progress */}
        <div className="mt-4 rounded-xl border border-[#EFF0F2] bg-white p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[14px] font-bold">Progress Target Penagihan</h3>
            <span className="text-[12px] font-bold text-[#5856D6] tabular-nums">{target.achievement_pct || 0}%</span>
          </div>
          <div className="h-2.5 bg-[#EFF0F2] rounded-full overflow-hidden">
            <div className="h-full rounded-full bg-[#5856D6] transition-all" style={{ width: `${achievement}%` }} />
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-[#6B6B73]">
            <span>Tertagih {fmtCur(kpi.total_collected)}</span>
            <span>Target {fmtCur(target.amount)}</span>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
            <div className="rounded-lg bg-[#F8F9FB] p-2"><span className="text-[#8E8E93]">Basis komisi</span><p className="font-bold tabular-nums">{fmtCur(comm.base_amount)}</p></div>
            <div className="rounded-lg bg-[#F8F9FB] p-2"><span className="text-[#8E8E93]">{comm.strategy === "per_sku" ? "Strategi" : "Rate"}</span><p className="font-bold tabular-nums">{comm.strategy === "per_sku" ? "Per-SKU v2" : `${((comm.applied_rate || 0) * 100).toFixed(1)}%`}</p></div>
            <div className="rounded-lg bg-[#F8F9FB] p-2"><span className="text-[#8E8E93]">Proyeksi saat lunas</span><p className="font-bold tabular-nums text-[#1B7F4B]">{fmtCur(comm.projection_full ?? comm.projection_month_end)}</p></div>
          </div>
        </div>

        {/* Rincian komisi per-SKU (EPIC4 — hanya mode per_sku) */}
        {comm.strategy === "per_sku" && (
          <div className="mt-4 rounded-xl border border-[#EFF0F2] bg-white p-4" data-testid="sales-home-commission-breakdown">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[14px] font-bold">Rincian Komisi per Kategori / SKU</h3>
              <span className="text-[11px] text-[#6B6B73]">saat tertagih · memperhatikan margin</span>
            </div>
            {(comm.breakdown || []).length > 0 ? (
              <div className="overflow-auto rounded-md border border-[#EFF0F2]">
                <table className="w-full text-[12px]" data-testid="commission-breakdown-table">
                  <thead>
                    <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                      <th className="px-3 py-2">Kategori</th><th className="px-3 py-2">Produk</th>
                      <th className="px-3 py-2 text-right">Qty terbayar</th><th className="px-3 py-2 text-right">Komisi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comm.breakdown.map((b, i) => (
                      <tr key={`${b.sku}-${i}`} data-testid={`commission-breakdown-row-${i}`} className="border-b border-[#F5F5F7] last:border-0">
                        <td className="px-3 py-2 font-semibold">{b.category || "—"}</td>
                        <td className="px-3 py-2 text-[#3C3C43]">{b.name}<span className="text-[10px] text-[#9A9BA3] font-mono"> · {b.sku}</span></td>
                        <td className="px-3 py-2 text-right tabular-nums">{fmt.format(b.qty_base || 0)} m</td>
                        <td className="px-3 py-2 text-right tabular-nums font-semibold text-[#1B7F4B]">{fmtCur(b.commission)}</td>
                      </tr>
                    ))}
                    <tr className="bg-[#FAFBFC] font-bold">
                      <td className="px-3 py-2" colSpan={3}>Total Komisi (akrual MTD)</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[#1B7F4B]" data-testid="commission-breakdown-total">{fmtCur(comm.mtd_accrual)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="h-20 flex items-center justify-center text-[13px] text-[#8E8E93]" data-testid="commission-breakdown-empty">Belum ada komisi terkumpul bulan ini. Komisi terbentuk saat pembayaran masuk.</div>
            )}
          </div>
        )}

        {/* History trend */}
        <div className="mt-4 rounded-xl border border-[#EFF0F2] bg-white p-4">
          <h3 className="text-[14px] font-bold mb-3">Tren Komisi (6 bulan)</h3>
          {loading ? (
            <div className="h-36 bg-[#F5F5F7] rounded animate-pulse" />
          ) : history.length > 0 ? (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={history} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EFF0F2" />
                <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => fmt.format(v / 1000) + "k"} />
                <Tooltip formatter={(v) => [fmtCur(v), "Insentif"]} />
                <Line type="monotone" dataKey="incentive" stroke="#34C759" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-36 flex items-center justify-center text-[13px] text-[#8E8E93]">Belum ada riwayat komisi</div>
          )}
        </div>

        {/* Penagihan + Order terbaru */}
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4" data-testid="sales-home-collections">
            <div className="flex items-center gap-2 mb-3"><Banknote size={15} className="text-[#FF3B30]" /><h3 className="text-[14px] font-bold">Penagihan Saya (Lewat Tempo)</h3></div>
            {(data?.collections || []).length > 0 ? (
              <div className="grid gap-1.5">
                {data.collections.map((c) => (
                  <div key={c.id} className="flex items-center gap-2 py-1.5 border-b border-[#F5F5F7] last:border-0">
                    <div className="flex-1 min-w-0"><p className="text-[12px] font-semibold truncate">{c.name}</p>
                      <p className="text-[10.5px] text-[#8E8E93]">AR {fmtCur(c.ar_outstanding)}</p></div>
                    <span className="text-[12px] font-bold text-red-600 tabular-nums">{fmtCur(c.overdue_amount)}</span>
                  </div>
                ))}
              </div>
            ) : <div className="h-20 flex items-center justify-center text-[13px] text-[#8E8E93]">Tidak ada tunggakan 🎉</div>}
          </div>

          <div className="rounded-xl border border-[#EFF0F2] bg-white p-4" data-testid="sales-home-recent-orders">
            <div className="flex items-center gap-2 mb-3"><ShoppingBag size={15} className="text-[#007AFF]" /><h3 className="text-[14px] font-bold">Pesanan Terbaru</h3></div>
            {(data?.recent_orders || []).length > 0 ? (
              <div className="grid gap-1.5">
                {data.recent_orders.map((o) => (
                  <div key={o.id} className="flex items-center gap-2 py-1.5 border-b border-[#F5F5F7] last:border-0">
                    <div className="flex-1 min-w-0"><p className="text-[12px] font-semibold truncate">{o.number}</p>
                      <p className="text-[10.5px] text-[#8E8E93] truncate">{o.customer_name} • {o.status}</p></div>
                    <span className="text-[12px] font-bold text-[#007AFF] tabular-nums">{fmtCur(o.grand_total)}</span>
                  </div>
                ))}
              </div>
            ) : <div className="h-20 flex items-center justify-center text-[13px] text-[#8E8E93]">Belum ada pesanan</div>}
          </div>
        </div>

        {/* Customers */}
        <div className="mt-4 rounded-xl border border-[#EFF0F2] bg-white p-4" data-testid="sales-home-customers">
          <div className="flex items-center gap-2 mb-3"><Users size={15} className="text-[#5856D6]" /><h3 className="text-[14px] font-bold">Pelanggan Saya & Kredit</h3></div>
          {(data?.customers || []).length > 0 ? (
            <div className="grid gap-1 max-h-72 overflow-auto">
              <div className="grid grid-cols-[1fr_110px_110px_70px] gap-2 text-[10px] font-bold uppercase text-[#8E8E93] pb-1 border-b border-[#EFF0F2]">
                <span>Pelanggan</span><span className="text-right">AR</span><span className="text-right">Lewat Jatuh Tempo</span><span className="text-center">Status</span>
              </div>
              {data.customers.map((c) => {
                const tone = CREDIT_TONE[c.status] || CREDIT_TONE.ok;
                return (
                  <div key={c.id} className="grid grid-cols-[1fr_110px_110px_70px] gap-2 text-[12px] py-1.5 border-b border-[#F5F5F7] last:border-0 items-center">
                    <span className="font-semibold truncate">{c.name}</span>
                    <span className="text-right tabular-nums text-[#3C3C43]">{fmtCur(c.ar_outstanding)}</span>
                    <span className="text-right tabular-nums text-red-600">{fmtCur(c.overdue_amount)}</span>
                    <span className="text-center"><span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${tone.cls}`}>{tone.label}</span></span>
                  </div>
                );
              })}
            </div>
          ) : <div className="h-20 flex items-center justify-center text-[13px] text-[#8E8E93]">Belum ada pelanggan ditugaskan</div>}
        </div>
      </div>
    </section>
  );
}
