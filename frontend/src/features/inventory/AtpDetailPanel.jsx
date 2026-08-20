/**
 * AtpDetailPanel (F2b) — Detail ATP future-aware untuk satu produk:
 * available + incoming(PO+ETA, dalam horizon) − pending demand (Pending SO).
 * Lazy-fetch saat baris produk diperluas. Sumber: GET /api/stock/atp.
 */
import { useEffect, useState } from "react";
import { Clock, TrendingUp } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatQty } from "../../utils/formatters";
import ProductPurchaseHistory from "./ProductPurchaseHistory";

function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short" });
  } catch {
    return s;
  }
}

export default function AtpDetailPanel({ productId, ownerEntityId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true); setErr("");
      try {
        const params = { product_id: productId };
        if (ownerEntityId) params.owner_entity_id = ownerEntityId;
        const r = await axios.get(`${API}/stock/atp`, { params });
        if (alive) setData(r.data);
      } catch (e) {
        if (alive) setErr(e.response?.data?.detail || "Gagal memuat ATP.");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [productId, ownerEntityId]);

  if (loading) return <div className="px-3 py-3 text-[11px] text-[#9A9BA3]" data-testid="sb-atp-loading">Memuat ATP…</div>;
  if (err) return <div className="px-3 py-3 text-[11px] text-[#C0392B]" data-testid="sb-atp-error">{err}</div>;
  if (!data) return null;

  return (
    <div className="px-3 py-3 bg-[#FBFAFD] border-t border-[#EFE6F6]" data-testid={`sb-atp-detail-${productId}`}>
      <div className="flex items-center gap-2 mb-2">
        <TrendingUp size={13} className="text-[#6B219A]" />
        <span className="text-[11px] font-bold uppercase tracking-wide text-[#6B219A]">ATP Future-Aware</span>
        <span className="text-[10px] text-[#9A9BA3]">horizon {data.horizon_days} hari</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <Metric label="Tersedia" value={data.available} tone="text-[#1B7F4B]" testId={`sb-atp-avail-${productId}`} />
        <Metric label="Incoming (horizon)" value={data.incoming_in_horizon} tone="text-[#00838F]" testId={`sb-atp-incoming-${productId}`} />
        <Metric label="Permintaan Menunggu" value={data.pending_total} tone="text-[#C0392B]" testId={`sb-atp-pending-${productId}`} />
        <Metric label="ATP (horizon)" value={data.atp_horizon} tone="text-[#0058CC]" bold testId={`sb-atp-horizon-${productId}`} />
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Suplai Incoming (PO)</p>
          {(data.incoming || []).length === 0 ? (
            <p className="text-[11px] text-[#9A9BA3]">Tidak ada PO incoming.</p>
          ) : (
            <ul className="space-y-1">
              {data.incoming.map((i, idx) => (
                <li key={idx} className="flex items-center justify-between text-[11px] bg-white border border-[#EFF0F2] rounded px-2 py-1">
                  <span className="font-mono text-[#0058CC]">{i.po_number || "PO"}</span>
                  <span className="flex items-center gap-2">
                    <span className="tabular-nums font-semibold">{formatQty(i.qty)}</span>
                    <span className={`inline-flex items-center gap-0.5 text-[10px] ${i.within_horizon ? "text-[#1B7F4B]" : "text-[#9A9BA3]"}`}>
                      <Clock size={10} /> {fmtDate(i.eta)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Permintaan Menunggu (SO)</p>
          {(data.pending_demand || []).length === 0 ? (
            <p className="text-[11px] text-[#9A9BA3]">Tidak ada permintaan menunggu.</p>
          ) : (
            <ul className="space-y-1">
              {data.pending_demand.map((d, idx) => (
                <li key={idx} className="flex items-center justify-between text-[11px] bg-white border border-[#EFF0F2] rounded px-2 py-1">
                  <span className="truncate">{d.order_number} · {d.customer_name}</span>
                  <span className="tabular-nums font-semibold text-[#C0392B]">{formatQty(d.qty)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Kartu Asal / Riwayat Pembelian produk (traceability asal barang) */}
      <ProductPurchaseHistory productId={productId} ownerEntityId={ownerEntityId} />
    </div>
  );
}

function Metric({ label, value, tone = "", bold = false, testId }) {
  return (
    <div className="bg-white border border-[#EFF0F2] rounded-md px-2 py-1.5" data-testid={testId}>
      <p className="text-[9px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className={`tabular-nums ${bold ? "text-[15px] font-bold" : "text-[13px] font-semibold"} ${tone}`}>{formatQty(value)}</p>
    </div>
  );
}
