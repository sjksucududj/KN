import { useEffect, useState, useCallback } from "react";
import {
  Wallet, TrendingUp, Target, Banknote, ShoppingBag, RefreshCw,
  ArrowUpRight, AlertTriangle, Users, ChevronRight, Receipt,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency } from "../../../utils/formatters";
import { getStage, stageMeta } from "../../../utils/soStatus";

function MiniKpi({ icon: Icon, label, value, sub, color = "#007AFF", loading }) {
  return (
    <div className="m-card p-3" data-testid={`m-kpi-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="flex items-center gap-2">
        <span className="grid h-7 w-7 place-items-center rounded-lg" style={{ background: `${color}1A` }}>
          <Icon size={15} style={{ color }} />
        </span>
        <span className="text-[11px] font-semibold m-muted leading-tight">{label}</span>
      </div>
      {loading ? (
        <div className="mt-2 h-6 animate-pulse rounded bg-[#F1F2F4]" />
      ) : (
        <p className="mt-1.5 text-[18px] font-bold tabular-nums text-[#1C1C1E] leading-tight">{value}</p>
      )}
      {sub && <p className="mt-0.5 text-[10.5px] m-muted">{sub}</p>}
    </div>
  );
}

export default function MobileSalesHome({ token, user, onNewOrder, onOpenTab }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/home/sales`);
      setData(res.data);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat performa. Coba lagi.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const comm = data?.commission || {};
  const target = data?.target || {};
  const kpi = data?.kpi || {};
  const achievement = Math.min(target.achievement_pct || 0, 100);
  const recent = data?.recent_orders || [];
  const collections = data?.collections || [];

  return (
    <div className="space-y-3" data-testid="mobile-sales-home">
      <button data-testid="m-home-new-order" onClick={onNewOrder}
        className="primary-button m-press w-full justify-center py-3 text-[14px]">
        <ShoppingBag size={16} /> Buat Pesanan Baru
      </button>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="m-home-error" />

      <div className="flex items-center justify-between px-0.5">
        <h2 className="m-section-title">Performa Saya{data?.period ? ` — ${data.period}` : ""}</h2>
        <button onClick={load} className="text-[#6B6B73]" data-testid="m-home-refresh" aria-label="Muat ulang">
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <MiniKpi icon={Wallet} label="Komisi MTD" value={formatCurrency(comm.mtd_accrual)} sub="Akrual berjalan" color="#34C759" loading={loading} />
        <MiniKpi icon={TrendingUp} label="Proyeksi" value={formatCurrency(comm.projection_month_end)} sub="Akhir bulan" color="#007AFF" loading={loading} />
        <MiniKpi icon={Banknote} label="Penjualan MTD" value={formatCurrency(kpi.total_sales)} sub={`${kpi.orders_count || 0} pesanan`} color="#FF9500" loading={loading} />
        <MiniKpi icon={ArrowUpRight} label="Tertagih" value={formatCurrency(kpi.total_collected)} sub={`${kpi.collection_rate || 0}% tertagih`} color="#30D158" loading={loading} />
        <MiniKpi icon={Receipt} label="Piutang Belum Lunas" value={formatCurrency(kpi.ar_outstanding)} sub="Piutang berjalan" color="#007AFF" loading={loading} />
        <MiniKpi icon={AlertTriangle} label="Lewat Jatuh Tempo" value={formatCurrency(kpi.overdue_amount)} sub="Lewat jatuh tempo" color="#FF3B30" loading={loading} />
      </div>

      {/* Target progress */}
      <div className="m-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-[13px] font-bold">Capaian Target Penagihan</h3>
          <span className="text-[12px] font-bold tabular-nums text-[#5856D6]">{target.achievement_pct || 0}%</span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-[#EFF0F2]">
          <div className="h-full rounded-full bg-[#5856D6] transition-all" style={{ width: `${achievement}%` }} />
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] m-muted">
          <span>Tertagih {formatCurrency(kpi.total_collected)}</span>
          <span>Target {formatCurrency(target.amount)}</span>
        </div>
      </div>

      {/* Recent orders */}
      <div className="m-card">
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-2.5">
          <h3 className="text-[13px] font-bold">Pesanan Terbaru</h3>
          <button onClick={() => onOpenTab && onOpenTab("orders")} className="inline-flex items-center gap-0.5 text-[12px] font-semibold text-[#0058CC]" data-testid="m-home-see-orders">
            Semua <ChevronRight size={14} />
          </button>
        </div>
        <div className="px-4 py-1">
          {loading ? (
            <div className="py-6 text-center text-[12px] m-muted">Memuat…</div>
          ) : recent.length === 0 ? (
            <div className="py-6 text-center text-[12px] m-muted">Belum ada pesanan.</div>
          ) : recent.slice(0, 5).map((o) => (
            <div key={o.id} className="m-list-row">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12.5px] font-semibold">{o.number}</p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className={`status-pill ${stageMeta(getStage(o)).cls}`}>{stageMeta(getStage(o)).label}</span>
                  <p className="truncate text-[10.5px] m-muted">{o.customer_name}</p>
                </div>
              </div>
              <span className="text-[12px] font-bold tabular-nums text-[#0058CC]">{formatCurrency(o.grand_total)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Overdue collections */}
      {collections.length > 0 && (
        <div className="m-card">
          <div className="flex items-center gap-2 border-b border-[#EFF0F2] px-4 py-2.5">
            <Banknote size={15} className="text-[#FF3B30]" />
            <h3 className="text-[13px] font-bold">Penagihan (Lewat Tempo)</h3>
          </div>
          <div className="px-4 py-1">
            {collections.slice(0, 5).map((c) => (
              <div key={c.id} className="m-list-row">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12.5px] font-semibold">{c.name}</p>
                  <p className="text-[10.5px] m-muted">AR {formatCurrency(c.ar_outstanding)}</p>
                </div>
                <span className="text-[12px] font-bold tabular-nums text-[#C0392B]">{formatCurrency(c.overdue_amount)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
