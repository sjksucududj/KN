/**
 * Sub-fase 1.12 — Special Order (OD)
 *
 * Main view untuk Special Orders (produk custom yang belum ada di katalog)
 * Features:
 * - List special orders dengan filter status
 * - Create special order
 * - Detail view
 * - Approve/Reject (manager/admin)
 */
import { useState, useEffect } from "react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { AlertCircle, CheckCircle2, Clock, Loader2, Package, Plus, Search, Sparkles, X } from "lucide-react";
import CreateSpecialOrderForm from "./CreateSpecialOrderForm";
import SpecialOrderDetail from "./SpecialOrderDetail";


// Helper functions
function fmtNum(n, d = 0) {
  return new Intl.NumberFormat("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n || 0);
}

function fmtDate(s) {
  if (!s) return "-";
  return new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
}

const STATUS_STYLE = {
  draft:             { cls: "pill-muted",   label: "Draf" },
  pending_approval:  { cls: "pill-warning", label: "Menunggu Persetujuan" },
  confirmed:         { cls: "pill-info",    label: "Terkonfirmasi" },
  in_production:     { cls: "pill-purple",  label: "Dalam Produksi" },
  ready:             { cls: "pill-success", label: "Siap" },
  shipped:           { cls: "pill-primary", label: "Shipped" },
  done:              { cls: "pill-success", label: "Selesai" },
  cancelled:         { cls: "pill-danger",  label: "Dibatalkan" },
};

function StatusPill({ status }) {
  const s = STATUS_STYLE[status] || { cls: "pill-muted", label: status };
  return <span className={`status-pill ${s.cls}`}>{s.label}</span>;
}

// Main component
export default function SpecialOrders({ currentUser }) {
  const [loading, setLoading] = useState(true);
  const [orders, setOrders] = useState([]);
  const [stats, setStats] = useState({});
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  
  // Filters
  const [statusFilter, setStatusFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  
  // Views
  const [view, setView] = useState("list"); // list | create | detail
  const [selectedOrder, setSelectedOrder] = useState(null);

  useEffect(() => {
    loadOrders();
  }, [statusFilter]);

  const token = localStorage.getItem("kn_token");

  async function loadOrders() {
    setLoading(true);
    if (!token) {
      setError("Session tidak valid. Silakan login kembali.");
      setLoading(false);
      return;
    }
    
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.append("status", statusFilter);
      
      const res = await axios.get(`${API}/special-orders?${params}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      setOrders(res.data.items || []);
      setStats(res.data.by_status || {});
      setError(null);
    } catch (e) {
      setError("Gagal memuat special orders: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  function handleCreateSuccess(newOrder) {
    setNotice(`Special Order ${newOrder.number} berhasil dibuat!`);
    setView("detail");
    setSelectedOrder(newOrder);
    loadOrders();
  }

  function handleDetailUpdate(updatedOrder) {
    setSelectedOrder(updatedOrder);
    loadOrders();
  }

  // Filter orders by search
  const filteredOrders = orders.filter(o => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      (o.number || "").toLowerCase().includes(q) ||
      (o.customer_name || "").toLowerCase().includes(q) ||
      (o.custom_item?.description || "").toLowerCase().includes(q)
    );
  });

  // Status tabs
  const statusTabs = [
    { key: "", label: "Semua" },
    { key: "draft", label: "Draf" },
    { key: "pending_approval", label: "Menunggu Persetujuan" },
    { key: "confirmed", label: "Terkonfirmasi" },
    { key: "in_production", label: "Produksi" },
    { key: "ready", label: "Siap" },
    { key: "shipped", label: "Shipped" },
    { key: "done", label: "Selesai" },
  ];

  const canCreate = ["admin", "sales", "manager"].includes(currentUser?.role);
  const soTotal = Object.values(stats).reduce((s, v) => s + (v.count || 0), 0);
  const soCnt = (k) => stats[k]?.count || 0;

  // ─── Render views ────────────────────────────────────────────────────────────────

  if (view === "create") {
    return (
      <CreateSpecialOrderForm
        token={token}
        onCreated={handleCreateSuccess}
        onCancel={() => setView("list")}
      />
    );
  }

  if (view === "detail" && selectedOrder) {
    return (
      <SpecialOrderDetail
        order={selectedOrder}
        token={token}
        currentUser={currentUser}
        onBack={() => { setView("list"); setSelectedOrder(null); }}
        onUpdate={handleDetailUpdate}
        notice={notice}
        onClearNotice={() => setNotice(null)}
      />
    );
  }

  // ─── List View ──────────────────────────────────────────────────────────────────

  return (
    <div data-testid="special-orders-view" className="view-container">
      {/* Notice */}
      {notice && (
        <div className="notice-bar success" data-testid="special-order-notice">
          <CheckCircle2 size={14} /> {notice}
          <button onClick={() => setNotice(null)}><X size={12} /></button>
        </div>
      )}

      {/* Error */}
      {error && (
        <ErrorNotice message={error} onRetry={loadOrders} onDismiss={() => setError(null)} testId="special-order-error" />
      )}

      {/* Header */}
      <div className="view-header">
        <div>
          <h1 className="view-title">
            <Sparkles size={20} /> Pesanan Khusus (OD)
          </h1>
          <p className="view-subtitle">
            Pesanan khusus untuk produk custom yang belum ada di katalog
          </p>
        </div>
        {canCreate && (
          <button
            data-testid="create-special-order-btn"
            className="primary-button"
            onClick={() => setView("create")}
          >
            <Plus size={14} /> Buat Pesanan Khusus
          </button>
        )}
      </div>

      {/* Ringkasan */}
      <div data-testid="special-order-stats" className="grid grid-cols-2 gap-2 sm:grid-cols-5" style={{ marginBottom: 12 }}>
        {[
          { label: "Total OD", value: soTotal, icon: Sparkles, hint: "semua status" },
          { label: "Draf", value: soCnt("draft"), icon: Package },
          { label: "Menunggu Persetujuan", value: soCnt("pending_approval"), icon: Clock },
          { label: "Produksi", value: soCnt("in_production"), icon: Loader2 },
          { label: "Selesai", value: soCnt("done"), icon: CheckCircle2 },
        ].map(({ label, value, icon: Icon, hint }) => (
          <div key={label} className="metric-card">
            <div className="metric-icon"><Icon size={16} /></div>
            <div className="metric-body">
              <div className="metric-label">{label}</div>
              <div className="metric-value tabular-nums">{fmtNum(value)}</div>
              {hint && <div className="metric-hint">{hint}</div>}
            </div>
          </div>
        ))}
      </div>

      {/* Search & Filter */}
      <div className="filter-bar">
        <div className="search-box">
          <Search size={14} />
          <input
            data-testid="special-order-search"
            type="text"
            placeholder="Cari nomor / pelanggan / keterangan…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Status tabs */}
      <div className="tab-bar">
        {statusTabs.map(tab => (
          <button
            key={tab.key}
            data-testid={`status-tab-${tab.key || "all"}`}
            className={`tab-button ${statusFilter === tab.key ? "active" : ""}`}
            onClick={() => setStatusFilter(tab.key)}
          >
            {tab.label}
            {tab.key && stats[tab.key] && (
              <span className="tab-badge">{stats[tab.key].count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading ? (
        <div className="loading-state">
          <Loader2 size={24} className="spin" />
          <p>Memuat special orders...</p>
        </div>
      ) : filteredOrders.length === 0 ? (
        <div className="empty-state" data-testid="special-order-empty">
          <Sparkles size={32} style={{ opacity: 0.3 }} />
          <p className="font-semibold">Belum ada pesanan khusus {statusFilter ? `dengan status ${statusTabs.find(t => t.key === statusFilter)?.label}` : ""}.</p>
          <p className="text-sm text-muted" style={{ maxWidth: 460, margin: "4px auto 0" }}>
            Special Order (OD) dipakai untuk produk custom yang belum ada di katalog — mis. kain motif khusus, warna Pantone, atau bordir seragam. Alur: buat OD → menunggu approval bila nilainya besar → produksi → kirim.
          </p>
          {canCreate && (
            <button className="primary-button" style={{ marginTop: 12 }} onClick={() => setView("create")}>
              <Plus size={14} /> Buat Pesanan Khusus Pertama
            </button>
          )}
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Nomor</th>
                <th>Pelanggan</th>
                <th>Deskripsi Item</th>
                <th>Qty</th>
                <th>Harga Target</th>
                <th>Total</th>
                <th>Status</th>
                <th>Expected Del.</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filteredOrders.map(order => (
                <tr key={order.id} data-testid={`special-order-row-${order.id}`}>
                  <td>
                    <div className="flex items-center gap-2">
                      <Sparkles size={12} className="text-purple-500" />
                      <span className="font-mono font-semibold">{order.number}</span>
                    </div>
                  </td>
                  <td>
                    <div className="font-medium">{order.customer_name}</div>
                    <div className="text-xs text-muted">{order.customer_email}</div>
                  </td>
                  <td>
                    <div className="max-w-xs">
                      <div className="font-medium truncate">
                        {order.custom_item?.description || "-"}
                      </div>
                      {order.custom_item?.specifications && Object.keys(order.custom_item.specifications).length > 0 && (
                        <div className="text-xs text-muted">
                          {Object.entries(order.custom_item.specifications).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(", ")}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="font-mono">
                    <strong>{fmtNum(order.custom_item?.quantity, 2)}</strong> {order.custom_item?.unit}
                  </td>
                  <td className="text-right font-mono tabular-nums">
                    Rp {fmtNum(order.custom_item?.target_price, 0)}
                  </td>
                  <td className="text-right font-mono font-semibold tabular-nums">
                    Rp {fmtNum(order.total_amount, 0)}
                  </td>
                  <td>
                    <StatusPill status={order.status} />
                  </td>
                  <td className="text-muted">
                    <Clock size={11} className="inline mr-1" />
                    {fmtDate(order.expected_delivery)}
                  </td>
                  <td>
                    <button
                      data-testid={`view-special-order-${order.id}`}
                      className="link-button"
                      onClick={() => { setSelectedOrder(order); setView("detail"); }}
                    >
                      Detail →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
