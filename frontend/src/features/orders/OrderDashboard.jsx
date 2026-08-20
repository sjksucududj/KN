import { useState, useMemo } from "react";
import { TrendingUp, TrendingDown, AlertCircle, Clock, Package, DollarSign, Users, Calendar } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { getStage, stageMeta } from "../../utils/soStatus";

function OrderDashboard({ orders = [], loading = false }) {
  const [timeRange, setTimeRange] = useState("7d"); // 7d, 30d, 90d
  
  // Calculate metrics
  const metrics = useMemo(() => {
    const now = new Date();
    const cutoffDays = timeRange === "7d" ? 7 : timeRange === "30d" ? 30 : 90;
    const cutoffDate = new Date(now.getTime() - cutoffDays * 24 * 60 * 60 * 1000);
    
    const recentOrders = orders.filter(o => new Date(o.created_at) >= cutoffDate);
    
    const FULFILLED_STATUSES = ["confirmed", "partially_picked", "picked",
      "partially_shipped", "shipped", "dispatched", "done"];
    const totalRevenue = recentOrders
      .filter(o => FULFILLED_STATUSES.includes(o.status))
      .reduce((sum, o) => sum + (o.total_amount || 0), 0);
    
    const pendingOrders = orders.filter(o => 
      ["waiting_approval", "reserved", "approved"].includes(o.status)
    );
    
    const expiringSoon = orders.filter(o => {
      if (!o.reservation_expires_at) return false;
      const expiryDate = new Date(o.reservation_expires_at);
      const hoursUntilExpiry = (expiryDate - now) / (1000 * 60 * 60);
      return hoursUntilExpiry > 0 && hoursUntilExpiry < 24;
    });
    
    // Top customers
    const customerOrders = {};
    recentOrders.forEach(o => {
      if (!customerOrders[o.customer_id]) {
        customerOrders[o.customer_id] = {
          name: o.customer_name,
          count: 0,
          revenue: 0
        };
      }
      customerOrders[o.customer_id].count++;
      customerOrders[o.customer_id].revenue += o.total_amount || 0;
    });
    
    const topCustomers = Object.values(customerOrders)
      .sort((a, b) => b.revenue - a.revenue)
      .slice(0, 5);
    
    // Orders by status
    const statusCounts = {
      waiting: orders.filter(o => o.status === "waiting_approval").length,
      reserved: orders.filter(o => o.status === "reserved").length,
      approved: orders.filter(o => o.status === "approved").length,
      confirmed: orders.filter(o => ["confirmed", "partially_picked", "picked"].includes(o.status)).length,
      dispatched: orders.filter(o => ["partially_shipped", "shipped", "dispatched"].includes(o.status)).length,
      done: orders.filter(o => o.status === "done").length,
      cancelled: orders.filter(o => o.status === "cancelled").length,
    };
    
    return {
      totalRevenue,
      totalOrders: recentOrders.length,
      pendingOrders: pendingOrders.length,
      expiringSoon: expiringSoon.length,
      avgOrderValue: recentOrders.length > 0 ? totalRevenue / recentOrders.length : 0,
      topCustomers,
      statusCounts,
      recentOrders: orders.slice(0, 10)
    };
  }, [orders, timeRange]);
  
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: "IDR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };
  
  return (
    <div className="flex flex-col gap-3">
      {loading && (
        <div className="animate-pulse rounded-lg bg-[#FAFBFC] px-3 py-2 text-[12px] text-[#6B6B73]">Memuat data dasbor…</div>
      )}
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[18px] font-bold">Dasbor Pesanan</h1>
          <p className="text-[12px] text-[#6B6B73]">Monitoring & analytics untuk sales orders</p>
        </div>
        <KNSelect
          className="field !py-1.5 !text-[11px] w-auto"
          value={timeRange}
          onValueChange={setTimeRange}
          options={[
            { value: "7d", label: "7 Hari Terakhir" },
            { value: "30d", label: "30 Hari Terakhir" },
            { value: "90d", label: "90 Hari Terakhir" },
          ]}
        />
      </div>
      
      {/* Key Metrics */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="dashboard-metrics-row">
        <div className="section-card !p-3" data-testid="dashboard-metric-revenue">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-lg bg-[#EFF4FF]">
              <DollarSign size={14} className="text-[#007AFF]" />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Revenue</p>
          </div>
          <p className="text-[18px] font-bold text-[#007AFF]">{formatCurrency(metrics.totalRevenue)}</p>
          <p className="text-[10px] text-[#8E8E93] mt-1">{metrics.totalOrders} orders</p>
        </div>
        
        <div className="section-card !p-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-lg bg-orange-50">
              <Clock size={14} className="text-[#FF9500]" />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Menunggu</p>
          </div>
          <p className="text-[18px] font-bold text-[#FF9500]">{metrics.pendingOrders}</p>
          <p className="text-[10px] text-[#8E8E93] mt-1">Butuh persetujuan</p>
        </div>
        
        <div className="section-card !p-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-lg bg-red-50">
              <AlertCircle size={14} className="text-red-500" />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Expiring</p>
          </div>
          <p className="text-[18px] font-bold text-red-500">{metrics.expiringSoon}</p>
          <p className="text-[10px] text-[#8E8E93] mt-1">Expires &lt; 24h</p>
        </div>
        
        <div className="section-card !p-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="p-1.5 rounded-lg bg-green-50">
              <Package size={14} className="text-[#34C759]" />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Rata-rata Pesanan</p>
          </div>
          <p className="text-[18px] font-bold text-[#34C759]">{formatCurrency(metrics.avgOrderValue)}</p>
          <p className="text-[10px] text-[#8E8E93] mt-1">Per pesanan</p>
        </div>
      </div>
      
      {/* Charts & Lists */}
      <div className="grid gap-3 lg:grid-cols-2">
        {/* Top Customers */}
        <div className="section-card" data-testid="dashboard-top-customers">
          <div className="section-head">
            <div className="flex items-center gap-2">
              <Users size={14} className="text-[#007AFF]" />
              <h2>Top Customers</h2>
            </div>
          </div>
          <div className="section-body">
            {metrics.topCustomers.length === 0 ? (
              <p className="text-[12px] text-[#8E8E93] text-center py-4">Belum ada data pelanggan</p>
            ) : (
              <div className="space-y-2">
                {metrics.topCustomers.map((customer, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2 rounded-md bg-[#FAFBFC] border border-[#EFF0F2]">
                    <div className="flex-1 min-w-0">
                      <p className="text-[11.5px] font-semibold truncate">{customer.name}</p>
                      <p className="text-[10px] text-[#6B6B73]">{customer.count} orders</p>
                    </div>
                    <p className="text-[12px] font-bold text-[#007AFF]">{formatCurrency(customer.revenue)}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        
        {/* Status Distribution */}
        <div className="section-card" data-testid="dashboard-status-distribution">
          <div className="section-head">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-[#007AFF]" />
              <h2>Status Distribution</h2>
            </div>
          </div>
          <div className="section-body">
            <div className="space-y-2">
              {[
                { label: "Menunggu Persetujuan", count: metrics.statusCounts.waiting, color: "bg-gray-400" },
                { label: "Dipesan", count: metrics.statusCounts.reserved, color: "bg-[#FF9500]" },
                { label: "Disetujui", count: metrics.statusCounts.approved, color: "bg-blue-500" },
                { label: "Diproses (Ditahan/Sudah Diambil)", count: metrics.statusCounts.confirmed, color: "bg-[#34C759]" },
                { label: "Dikirim (Partial/Shipped)", count: metrics.statusCounts.dispatched, color: "bg-[#5856D6]" },
                { label: "Selesai", count: metrics.statusCounts.done, color: "bg-green-600" },
                { label: "Dibatalkan", count: metrics.statusCounts.cancelled, color: "bg-red-500" },
              ].map(({ label, count, color }) => {
                const percentage = orders.length > 0 ? (count / orders.length) * 100 : 0;
                return (
                  <div key={label} className="space-y-1">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-semibold">{label}</span>
                      <span className="text-[#6B6B73]">{count} ({percentage.toFixed(0)}%)</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-[#EFF0F2] overflow-hidden">
                      <div className={`h-full ${color}`} style={{ width: `${percentage}%` }}></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
      
      {/* Recent Orders */}
      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Calendar size={14} className="text-[#007AFF]" />
            <h2>Recent Orders</h2>
          </div>
          <span className="text-[11px] text-[#6B6B73]">10 terbaru</span>
        </div>
        <div className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-[#FAFBFC] border-b border-[#EFF0F2]">
                <tr className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
                  <th className="px-3 py-2 text-left">Pesanan</th>
                  <th className="px-3 py-2 text-left">Pelanggan</th>
                  <th className="px-3 py-2 text-left">Date</th>
                  <th className="px-3 py-2 text-right">Total</th>
                  <th className="px-3 py-2 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EFF0F2]">
                {metrics.recentOrders.map((order) => (
                  <tr key={order.id} className="hover:bg-[#FAFBFC]">
                    <td className="px-3 py-2 text-[11.5px] font-bold text-[#007AFF]">{order.number}</td>
                    <td className="px-3 py-2 text-[11px]">{order.customer_name}</td>
                    <td className="px-3 py-2 text-[10.5px] text-[#6B6B73]">
                      {new Date(order.created_at).toLocaleDateString("id-ID")}
                    </td>
                    <td className="px-3 py-2 text-[11.5px] font-semibold text-right tabular-nums">{formatCurrency(order.total_amount)}</td>
                    <td className="px-3 py-2 text-center">
                      <span
                        data-testid={`dashboard-order-stage-${order.id}`}
                        className={`status-pill ${stageMeta(getStage(order)).cls}`}
                      >
                        {stageMeta(getStage(order)).label}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default OrderDashboard;
