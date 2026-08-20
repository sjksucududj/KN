import { useEffect, useState } from "react";
import { X, Info, Tag, BarChart3, Building2, Truck, Clock, ClipboardList, Receipt, Undo2 } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatCurrency } from "../../utils/formatters";
import SupplierPriceList from "./SupplierPriceList";
import SupplierScorecard from "./SupplierScorecard";
import { overlayDismiss } from "@/utils/overlayDismiss";

/**
 * SupplierDetailPanel — di-upgrade ke "Supplier 360" (M1):
 *   Info · PO · Tagihan · Retur · Daftar Harga · Scorecard.
 * Data PO/Tagihan/Retur dari GET /suppliers/{id}/360 (data nyata).
 */
const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "—");

function InfoRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b border-[#F2F3F5] last:border-0">
      <span className="text-[11px] text-[#6B6B73]">{label}</span>
      <span className="text-[12px] font-medium text-right">{value || "—"}</span>
    </div>
  );
}

export default function SupplierDetailPanel({ supplier, currentUser, onClose }) {
  const [tab, setTab] = useState("info");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const canManage = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => {
    if (!supplier) return;
    let ok = true;
    (async () => {
      setLoading(true);
      try { const r = await axios.get(`${API}/suppliers/${supplier.id}/360`); if (ok) setData(r.data); }
      catch { /* fallback ke prop supplier */ }
      finally { if (ok) setLoading(false); }
    })();
    return () => { ok = false; };
  }, [supplier]);

  if (!supplier) return null;
  const d = data || supplier;
  const pos = d.purchase_orders || [];
  const bills = d.vendor_bills || [];
  const rets = d.returns || [];

  const TABS = [
    { id: "info", label: "Info", icon: Info },
    { id: "po", label: `PO (${pos.length})`, icon: ClipboardList },
    { id: "bills", label: `Tagihan (${bills.length})`, icon: Receipt },
    { id: "returns", label: `Retur (${rets.length})`, icon: Undo2 },
    { id: "price", label: "Daftar Harga", icon: Tag },
    { id: "scorecard", label: "Scorecard", icon: BarChart3 },
  ];

  return (
    <div className="modal-overlay" data-testid="supplier-detail-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card wide" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-[#EFF4FF] flex items-center justify-center shrink-0"><Truck size={17} className="text-[#0058CC]" /></div>
            <div className="min-w-0">
              <p data-testid="supplier-detail-name" className="modal-title truncate">{d.name}</p>
              <p className="text-[11px] text-[#6B6B73] flex items-center gap-2 flex-wrap">
                <span className="font-bold text-[#0058CC]">{d.code}</span>
                {d.city && <span className="flex items-center gap-1"><Building2 size={10} />{d.city}</span>}
                {d.lead_time_days > 0 && <span className="flex items-center gap-1"><Clock size={10} />{d.lead_time_days} hari lead</span>}
              </p>
            </div>
          </div>
          <button data-testid="supplier-detail-close" className="icon-button" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="tab-bar">
          {TABS.map((t) => { const Icon = t.icon; return (
            <button key={t.id} data-testid={`supplier-tab-${t.id}`} className={`tab-button ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
              <Icon size={14} /> {t.label}
            </button>
          ); })}
        </div>

        {tab === "info" && (
          <div data-testid="supplier-tab-info-content" className="section-card">
            <div className="section-body">
              <InfoRow label="Nama" value={d.name} /><InfoRow label="Kode" value={d.code} />
              <InfoRow label="NPWP" value={d.npwp} /><InfoRow label="PIC" value={d.pic_name} />
              <InfoRow label="Telepon" value={d.phone} /><InfoRow label="Email" value={d.email} />
              <InfoRow label="Alamat" value={d.address} /><InfoRow label="Kota" value={d.city} />
              <InfoRow label="Jenis Barang" value={d.goods_type} />
              <InfoRow label="Termin Pembayaran" value={d.payment_term_code} />
              <InfoRow label="Lead Time Default" value={`${d.lead_time_days || 0} hari`} />
              <InfoRow label="Total Nilai PO" value={d.po_total_value != null ? formatCurrency(d.po_total_value) : "—"} />
              <InfoRow label="Status" value={d.status === "active" ? "Aktif" : "Nonaktif"} />
            </div>
          </div>
        )}
        {tab === "po" && <ListCard testId="supplier-po-list" loading={loading} rows={pos} empty="Belum ada PO."
          render={(p) => ({ title: p.po_number || p.id, sub: `${fmtDate(p.created_at)} · ${p.status}`, amount: formatCurrency(p.total_amount || 0) })} />}
        {tab === "bills" && <ListCard testId="supplier-bills-list" loading={loading} rows={bills} empty="Belum ada tagihan (vendor bill)."
          render={(b) => ({ title: b.number || b.bill_number || b.id, sub: `${fmtDate(b.created_at)} · ${b.status || ""}`, amount: formatCurrency(b.grand_total || b.total || b.total_amount || 0) })} />}
        {tab === "returns" && <ListCard testId="supplier-returns-list" loading={loading} rows={rets} empty="Belum ada retur pembelian."
          render={(r) => ({ title: r.debit_note_number || r.number || r.id, sub: `${fmtDate(r.created_at)} · ${r.status || ""}`, amount: formatCurrency(r.total_amount || 0) })} />}
        {tab === "price" && <SupplierPriceList supplierId={d.id} canManage={canManage} />}
        {tab === "scorecard" && <SupplierScorecard supplierId={d.id} />}
      </div>
    </div>
  );
}

function ListCard({ rows, render, empty, loading, testId }) {
  if (loading) return <div className="section-card"><div className="section-body py-8 text-center text-[12px] text-[#6B6B73]">Memuat…</div></div>;
  if (!rows.length) return <div className="section-card"><div className="section-body py-8 text-center text-[12px] text-[#9A9BA3]" data-testid={`${testId}-empty`}>{empty}</div></div>;
  return (
    <div className="section-card"><div className="section-body">
      <div className="divide-y divide-[#EFF0F2] max-h-[440px] overflow-y-auto" data-testid={testId}>
        {rows.map((row, i) => { const r = render(row); return (
          <div key={row.id || i} className="flex items-center justify-between py-2 text-[11.5px]">
            <div className="min-w-0"><p className="truncate font-semibold text-[#0058CC]">{r.title}</p><p className="text-[10px] text-[#6B6B73]">{r.sub}</p></div>
            <span className="tabular-nums font-semibold">{r.amount}</span>
          </div>
        ); })}
      </div>
    </div></div>
  );
}
