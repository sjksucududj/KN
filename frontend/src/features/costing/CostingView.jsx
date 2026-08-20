/**
 * CostingView (EPIC3A) — Margin & HPP (WAC) per produk.
 * Akses admin/manager (sales dicabut dari HPP). Sumber: GET /api/costing/wac.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, TrendingUp, Search, Layers, AlertTriangle } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency, formatQty } from "../../utils/formatters";

const SOURCE_LABEL = {
  roll: "Roll (WAC)", roll_partial: "Roll (parsial)", harga_pokok: "HPP manual", none: "Belum ada cost",
};

function marginBadge(pct) {
  if (pct == null) return { cls: "text-[#8E8E93] bg-[#F0F0F2]", label: "—" };
  if (pct < 15) return { cls: "text-[#C0392B] bg-[#FCEBEA]", label: `${pct}%` };
  if (pct < 30) return { cls: "text-[#B45309] bg-[#FDF3E7]", label: `${pct}%` };
  return { cls: "text-[#1B7F4B] bg-[#E6F6EC]", label: `${pct}%` };
}

export default function CostingView({ selectedEntity }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const res = await axios.get(`${API}/costing/wac`, { params });
      setRows(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data costing (WAC).");
    } finally {
      setLoading(false);
    }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load]);

  const view = useMemo(() => {
    const term = q.trim().toLowerCase();
    return term ? rows.filter((r) => `${r.name} ${r.sku} ${r.category}`.toLowerCase().includes(term)) : rows;
  }, [rows, q]);

  const summary = useMemo(() => {
    const withMargin = rows.filter((r) => r.margin_pct != null);
    const avg = withMargin.length
      ? Math.round(withMargin.reduce((s, r) => s + r.margin_pct, 0) / withMargin.length)
      : null;
    return {
      products: rows.length,
      avgMargin: avg,
      lowMargin: rows.filter((r) => r.margin_pct != null && r.margin_pct < 15).length,
      noCost: rows.filter((r) => r.source === "none").length,
    };
  }, [rows]);

  return (
    <div data-testid="costing-view">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <Kpi label="Produk" value={summary.products} icon={Layers} />
        <Kpi label="Rata-rata Margin" value={summary.avgMargin != null ? `${summary.avgMargin}%` : "—"} icon={TrendingUp} tone="text-[#1B7F4B]" />
        <Kpi label="Margin Rendah (<15%)" value={summary.lowMargin} icon={AlertTriangle} tone={summary.lowMargin > 0 ? "text-[#C0392B]" : ""} />
        <Kpi label="Tanpa Biaya" value={summary.noCost} icon={AlertTriangle} tone={summary.noCost > 0 ? "text-[#B45309]" : ""} />
      </div>

      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2"><TrendingUp size={16} className="text-[#6B219A]" /><h2 data-testid="costing-title">Margin & HPP (WAC)</h2></div>
          <div className="flex items-center gap-2 ml-auto">
            <div className="relative">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="costing-search" className="field pl-7 py-1 text-[12px]" placeholder="Cari produk..." value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <button data-testid="costing-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="costing-error" />
          {loading ? (
            <div className="grid gap-2" data-testid="costing-loading">{[0,1,2,3,4].map((i) => <div key={i} className="h-10 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
          ) : view.length === 0 ? (
            <div data-testid="costing-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">Tidak ada produk.</div>
          ) : (
            <div className="overflow-auto rounded-md border border-[#EFF0F2]">
              <table className="w-full text-[12px]" data-testid="costing-table">
                <thead>
                  <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                    <th className="px-3 py-2">Produk</th>
                    <th className="px-3 py-2">Kategori</th>
                    <th className="px-3 py-2 text-right">Stok</th>
                    <th className="px-3 py-2 text-right">HPP / WAC</th>
                    <th className="px-3 py-2 text-right">Harga Jual</th>
                    <th className="px-3 py-2 text-right">Margin Katalog</th>
                    <th className="px-3 py-2 text-center">Margin %</th>
                    <th className="px-3 py-2">Sumber</th>
                  </tr>
                </thead>
                <tbody>
                  {view.map((r) => {
                    const b = marginBadge(r.margin_pct);
                    return (
                      <tr key={r.product_id} data-testid={`costing-row-${r.product_id}`} className="border-b border-[#F5F5F7] last:border-0">
                        <td className="px-3 py-2">
                          <p className="font-semibold text-[#1C1C1E]">{r.name}</p>
                          <p className="text-[10px] text-[#9A9BA3] font-mono">{r.sku}</p>
                        </td>
                        <td className="px-3 py-2 text-[#3C3C43]">{r.category}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-[#6B6B73]">{formatQty(r.qty_on_hand)} {r.base_unit}</td>
                        <td className="px-3 py-2 text-right tabular-nums font-semibold">{formatCurrency(r.wac)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(r.price)}</td>
                        <td className="px-3 py-2 text-right tabular-nums font-semibold">{r.margin_amount != null ? formatCurrency(r.margin_amount) : "—"}</td>
                        <td className="px-3 py-2 text-center"><span data-testid={`costing-margin-${r.product_id}`} className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${b.cls}`}>{b.label}</span></td>
                        <td className="px-3 py-2 text-[10px] text-[#6B6B73]">{SOURCE_LABEL[r.source] || r.source}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[10.5px] text-[#9A9BA3] mt-2">WAC = rata-rata tertimbang biaya roll (termasuk landed cost) per unit, bobot panjang sisa. <b>Margin Katalog</b> = Harga Jual katalog − WAC (belum memperhitungkan diskon/transaksi nyata); margin realisasi per order bisa lebih rendah setelah diskon.</p>
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, icon: Icon, tone = "" }) {
  return (
    <div className="section-card">
      <div className="section-body flex items-center gap-3 py-3">
        <div className="w-9 h-9 rounded-lg bg-[#F3EAFB] flex items-center justify-center"><Icon size={17} className="text-[#6B219A]" /></div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`text-[18px] font-bold tabular-nums ${tone || "text-[#1C1C1E]"}`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
