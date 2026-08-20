import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Star, Clock, TrendingUp, CheckCircle2, AlertTriangle, Wallet, PackageCheck, RefreshCw } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";

/**
 * SupplierScorecard (Depth #3) — metrik performa supplier dari data NYATA
 * (purchase_orders + penerimaan + purchase_returns). Read-only.
 */
const pct = (v) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`);

function Stars({ rating }) {
  if (rating === null || rating === undefined) {
    return <span data-testid="scorecard-rating-value" className="text-[#9A9BA3] text-[13px]">Belum dinilai</span>;
  }
  const full = Math.round(rating);
  return (
    <div className="flex items-center gap-1" data-testid="scorecard-rating-value">
      {[1, 2, 3, 4, 5].map((n) => (
        <Star key={n} size={16} className={n <= full ? "text-[#F5A623]" : "text-[#D6D7DC]"}
          fill={n <= full ? "#F5A623" : "none"} />
      ))}
      <span className="ml-1 text-[14px] font-bold tabular-nums">{rating.toFixed(1)}</span>
      <span className="text-[11px] text-[#9A9BA3]">/ 5</span>
    </div>
  );
}

function Tile({ testId, icon: Icon, label, value, tone, sub }) {
  return (
    <div className="metric-tile" data-testid={testId}>
      <div className="flex items-center gap-1.5">
        <Icon size={13} style={{ color: tone || "#0058CC" }} />
        <span className="metric-label">{label}</span>
      </div>
      <div className="metric-value tabular-nums" data-testid={`${testId}-value`}>{value}</div>
      {sub && <div className="text-[10.5px] text-[#8E8E93] mt-0.5">{sub}</div>}
    </div>
  );
}

export default function SupplierScorecard({ supplierId }) {
  const [card, setCard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [supplierId]);

  async function load() {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/suppliers/${supplierId}/scorecard`);
      setCard(res.data);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat scorecard supplier.");
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <div data-testid="scorecard-loading" className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat scorecard...</div>;
  }
  if (error) {
    return (
      <div data-testid="scorecard-error" className="py-8 text-center">
        <AlertTriangle className="mx-auto mb-2 text-[#C62828]" size={26} />
        <p className="text-[12px] text-[#C62828] mb-2">{error}</p>
        <button data-testid="scorecard-retry" onClick={load} className="secondary-button mx-auto"><RefreshCw size={13} /> Coba lagi</button>
      </div>
    );
  }

  const m = card?.metrics || {};
  if (!card?.has_data) {
    return (
      <div data-testid="scorecard-empty" className="py-12 text-center text-[12px] text-[#6B6B73]">
        <TrendingUp className="mx-auto mb-2 text-gray-300" size={28} />
        <p>Belum ada transaksi PO untuk supplier ini.</p>
        <p className="text-[10.5px] text-[#9A9BA3] mt-1">Scorecard akan terisi otomatis setelah ada PO & penerimaan.</p>
      </div>
    );
  }

  return (
    <div data-testid="supplier-scorecard">
      {/* Rating header */}
      <div className="section-card mb-3">
        <div className="section-body flex items-center justify-between flex-wrap gap-2">
          <div>
            <p className="text-[10.5px] font-bold uppercase text-[#8E8E93] mb-1">Rating Keseluruhan</p>
            <Stars rating={m.rating} />
          </div>
          <div className="text-right">
            <p className="text-[10.5px] text-[#8E8E93]">Lead-time default</p>
            <p className="text-[14px] font-bold tabular-nums" data-testid="scorecard-leadtime-default">{card.lead_time_days_default || 0} hari</p>
          </div>
        </div>
      </div>

      {/* Metric grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2.5 mb-3">
        <Tile testId="scorecard-ontime" icon={Clock} tone="#0058CC" label="Ketepatan Pengiriman"
          value={pct(m.on_time_rate)} sub={`${m.delivered_pos || 0} PO dievaluasi`} />
        <Tile testId="scorecard-quality" icon={CheckCircle2} tone="#1A7A3A" label="Quality Rate"
          value={pct(m.quality_rate)} sub={`Reject ${pct(m.reject_rate)}`} />
        <Tile testId="scorecard-fill" icon={PackageCheck} tone="#6B219A" label="Fill Rate"
          value={pct(m.fill_rate)} sub={`${formatQty(m.received_qty)} / ${formatQty(m.ordered_qty)}`} />
        <Tile testId="scorecard-leadtime" icon={TrendingUp} tone="#A05000" label="Avg Lead Time"
          value={m.avg_lead_time_days === null || m.avg_lead_time_days === undefined ? "—" : `${m.avg_lead_time_days} hari`} />
        <Tile testId="scorecard-spend" icon={Wallet} tone="#0B0B0F" label="Total Spend"
          value={formatCurrency(m.total_spend)} sub={`${m.total_pos || 0} PO`} />
        <Tile testId="scorecard-reject" icon={AlertTriangle} tone="#C62828" label="Qty Reject"
          value={formatQty(m.rejected_qty)} sub={`${m.return_count || 0} retur`} />
      </div>

      {/* PO breakdown */}
      <div className="section-card">
        <div className="section-head"><h2 className="text-[12.5px] font-bold">Rincian Pesanan Pembelian</h2></div>
        <div className="overflow-hidden">
          <div className="grid grid-cols-[90px_1fr_90px_90px_70px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Status / Terima</span><span className="text-right">Qty</span><span className="text-right">Nilai</span><span className="text-center">On-Time</span>
          </div>
          {(card.purchase_orders || []).length === 0 ? (
            <div className="py-8 text-center text-[12px] text-[#6B6B73]">Belum ada PO.</div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[280px] overflow-y-auto">
              {card.purchase_orders.map((po) => (
                <div key={po.po_id} data-testid={`scorecard-po-${po.po_id}`}
                  className="grid grid-cols-[90px_1fr_90px_90px_70px] items-center px-3 py-2 text-[11.5px]">
                  <span className="font-bold text-[#0058CC]">{po.po_number}</span>
                  <div className="min-w-0">
                    <span className={`status-pill status-${po.status}`}>{String(po.status).replaceAll("_", " ")}</span>
                    {po.lead_time_days !== null && po.lead_time_days !== undefined && (
                      <span className="ml-1 text-[10px] text-[#8E8E93]">· {po.lead_time_days} hari</span>
                    )}
                  </div>
                  <span className="text-right tabular-nums">{formatQty(po.received_qty)}/{formatQty(po.ordered_qty)}</span>
                  <span className="text-right tabular-nums">{formatCurrency(po.total_amount)}</span>
                  <span className="text-center">
                    {po.on_time === null || po.on_time === undefined ? (
                      <span className="text-[#C7C7CC]">—</span>
                    ) : po.on_time ? (
                      <span className="pill-success status-pill" data-testid={`scorecard-po-ontime-${po.po_id}`}>Tepat</span>
                    ) : (
                      <span className="pill-warning status-pill" data-testid={`scorecard-po-late-${po.po_id}`}>Telat</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
