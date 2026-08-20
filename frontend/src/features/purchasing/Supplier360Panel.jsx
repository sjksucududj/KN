import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ArrowLeft, Edit3, Truck, Building2, Clock, MapPin, PhoneCall, Wallet,
  ClipboardList, Receipt, Undo2, Tag, FileText, BarChart3, Star } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import RecordDetailModal from "../documents/RecordDetailModal";
import SupplierPriceList from "./SupplierPriceList";
import SupplierScorecard from "./SupplierScorecard";

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "—");
const money = (v) => formatCurrency(Number(v || 0));

const STATUS_TONE = {
  completed: "success", posted: "success", paid: "success", approved: "success",
  pending: "warning", waiting_approval: "warning", receiving: "info", partial: "info",
  rejected: "danger", cancelled: "danger", draft: "muted",
};
const tone = (s) => STATUS_TONE[(s || "").toLowerCase()] || "muted";

const TABS = [
  { key: "po", label: "PO", icon: ClipboardList },
  { key: "bills", label: "Tagihan", icon: Receipt },
  { key: "returns", label: "Retur Beli", icon: Undo2 },
  { key: "prices", label: "Daftar Harga", icon: Tag },
  { key: "documents", label: "Dokumen", icon: FileText },
  { key: "scorecard", label: "Scorecard", icon: BarChart3 },
];

/** Supplier 360° — halaman detail penuh (profil + keuangan AP + riwayat + dokumen). */
export default function Supplier360Panel({ supplierId, currentUser, onBack, onEdit, onError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("po");
  const [record, setRecord] = useState(null); // konfigurasi RecordDetailModal
  const canManage = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => { load(); }, [supplierId]); // eslint-disable-line
  async function load() {
    setLoading(true);
    try { const r = await axios.get(`${API}/suppliers/${supplierId}/360`); setData(r.data); }
    catch (e) { onError?.(e.response?.data?.detail || "Gagal memuat detail supplier."); onBack?.(); }
    finally { setLoading(false); }
  }

  if (loading && !data) return <div className="section-card py-12 text-center text-[12px] text-[#6B6B73]" data-testid="supplier-360-loading">Memuat detail supplier…</div>;
  if (!data) return null;

  const fin = data.finance || {};
  const pos = data.purchase_orders || [];
  const bills = data.vendor_bills || [];
  const rets = data.returns || [];
  const docs = data.documents || [];
  const priceHistory = data.price_history || [];
  const entityId = data.entity_id;

  // ── Builder RecordDetailModal per tipe ──
  function openPO(p) {
    setRecord({
      icon: <ClipboardList size={17} className="text-[#0058CC]" />, title: p.po_number || p.id, code: p.po_number,
      statusText: p.status, statusTone: tone(p.status),
      docType: "purchase_order", sourceId: p.id, number: p.po_number, entityId, esignable: true,
      meta: [
        { label: "Tanggal", value: fmtDate(p.created_at) },
        { label: "Status", value: p.status },
        { label: "Status Bayar", value: p.payment_status || "—" },
        { label: "Total", value: money(p.total_amount), tone: "text-[#0058CC]" },
        { label: "Dibayar", value: money(p.amount_paid) },
        { label: "Sudah Ditagih", value: money(p.billed_total) },
      ],
      items: p.items || [],
      itemColumns: [
        { label: "Produk", render: (r) => <span className="font-medium">{r.product_name || r.sku || r.product_id}</span> },
        { label: "Qty", align: "right", render: (r) => `${r.quantity ?? r.qty ?? 0} ${r.unit || ""}` },
        { label: "Harga", align: "right", render: (r) => money(r.price) },
        { label: "Subtotal", align: "right", render: (r) => money(r.line_total ?? r.subtotal) },
      ],
      totals: [
        { label: "Subtotal", value: money(p.net_subtotal ?? p.total_amount) },
        ...(p.ppn_amount ? [{ label: `PPN`, value: money(p.ppn_amount) }] : []),
        { label: "Grand Total", value: money(p.grand_total ?? p.total_amount), bold: true, tone: "text-[#0058CC]" },
      ],
    });
  }
  function openBill(b) {
    setRecord({
      icon: <Receipt size={17} className="text-[#0058CC]" />, title: b.bill_number || b.id, code: b.bill_number,
      statusText: b.status, statusTone: tone(b.status),
      docType: "vendor_bill", sourceId: b.id, number: b.bill_number, entityId, esignable: true,
      meta: [
        { label: "Tanggal", value: fmtDate(b.created_at || b.bill_date) },
        { label: "Status", value: b.status },
        { label: "Jatuh Tempo", value: fmtDate(b.due_date) },
        { label: "No. Faktur", value: b.supplier_invoice_no || "—" },
        { label: "Grand Total", value: money(b.grand_total), tone: "text-[#0058CC]" },
        { label: "Belum Lunas", value: money(b.outstanding), tone: Number(b.outstanding) > 0 ? "text-[#C0392B]" : "" },
      ],
      items: b.items || [],
      itemColumns: (b.items || []).length ? [
        { label: "Deskripsi", render: (r) => r.product_name || r.description || r.product_id || "—" },
        { label: "Qty", align: "right", render: (r) => `${r.qty ?? r.quantity ?? 0} ${r.unit || ""}` },
        { label: "Harga", align: "right", render: (r) => money(r.price) },
        { label: "Subtotal", align: "right", render: (r) => money(r.line_total ?? r.subtotal) },
      ] : [],
      totals: [
        { label: "Netto", value: money(b.net_amount) },
        ...(b.ppn_amount ? [{ label: "PPN", value: money(b.ppn_amount) }] : []),
        { label: "Grand Total", value: money(b.grand_total), bold: true, tone: "text-[#0058CC]" },
      ],
      note: (b.items || []).length ? undefined : "Vendor bill ini tidak memiliki rincian baris item (ringkasan nilai saja).",
    });
  }
  function openReturn(r) {
    setRecord({
      icon: <Undo2 size={17} className="text-[#0058CC]" />, title: r.debit_note_number || r.number || r.id, code: r.debit_note_number || r.number,
      statusText: r.status, statusTone: tone(r.status),
      docType: "purchase_return", sourceId: r.id, number: r.debit_note_number || r.number, entityId, esignable: false,
      meta: [
        { label: "Tanggal", value: fmtDate(r.created_at) },
        { label: "Status", value: r.status },
        { label: "PO Sumber", value: r.po_number || "—" },
        { label: "Gudang", value: r.warehouse_name || "—" },
        { label: "Total", value: money(r.total_amount), tone: "text-[#0058CC]" },
        { label: "Alasan", value: r.reason || "—" },
      ],
      items: r.items || [],
      itemColumns: [
        { label: "Produk", render: (x) => x.product_name || x.sku || x.product_id },
        { label: "Qty", align: "right", render: (x) => `${x.qty ?? x.quantity ?? 0} ${x.unit || ""}` },
        { label: "Harga", align: "right", render: (x) => money(x.price) },
        { label: "Subtotal", align: "right", render: (x) => money(x.line_total ?? x.subtotal) },
      ],
      totals: [{ label: "Total Retur", value: money(r.total_amount), bold: true, tone: "text-[#0058CC]" }],
    });
  }
  function openDoc(d) {
    setRecord({
      icon: <FileText size={17} className="text-[#0058CC]" />, title: d.number, code: d.number,
      statusText: d.status, statusTone: tone(d.status),
      docType: d.doc_type, sourceId: d.source_id, number: d.number, entityId, label: d.label,
      esignable: ["purchase_order", "vendor_bill"].includes(d.doc_type),
      meta: [
        { label: "Jenis", value: d.label },
        { label: "Tanggal", value: fmtDate(d.date) },
        { label: "Status", value: d.status },
        { label: "Nilai", value: money(d.amount), tone: "text-[#0058CC]" },
      ],
    });
  }

  return (
    <div data-testid="supplier-360-panel">
      <button data-testid="supplier-360-back" onClick={onBack} className="secondary-button mb-3"><ArrowLeft size={13} /> Kembali ke daftar</button>

      {/* Header */}
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Truck size={18} className="text-[#0058CC]" />
              <h2 className="truncate" data-testid="supplier-360-name">{data.name}</h2>
              <span className="text-[11px] font-bold text-[#0058CC]">{data.code}</span>
              <span className={`status-pill ${data.status === "active" ? "pill-success" : "pill-muted"}`}>{data.status === "active" ? "Aktif" : "Nonaktif"}</span>
            </div>
            <p className="text-[11px] text-[#6B6B73] mt-0.5 flex items-center gap-2 flex-wrap">
              {data.city && <span className="flex items-center gap-1"><Building2 size={10} />{data.city}</span>}
              {data.goods_type && <span>· {data.goods_type}</span>}
              {data.lead_time_days > 0 && <span className="flex items-center gap-1"><Clock size={10} />{data.lead_time_days} hari lead</span>}
            </p>
          </div>
          {canManage && <button data-testid="supplier-360-edit" onClick={() => onEdit?.(data)} className="secondary-button"><Edit3 size={13} /> Ubah</button>}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
        {/* Left: finance + profile */}
        <div className="space-y-3">
          <div className="section-card">
            <div className="section-head"><div className="flex items-center gap-2"><Wallet size={14} className="text-[#0058CC]" /><h3 className="text-[12.5px] font-bold">Keuangan Hutang (AP)</h3></div></div>
            <div className="section-body grid grid-cols-2 gap-2">
              <Kpi label="Total Hutang (AP)" value={money(fin.ap_outstanding)} tone="#0058CC" testId="supplier-360-ap" />
              <Kpi label="Jatuh Tempo (Lewat Tempo)" value={money(fin.overdue_amount)} sub={fin.overdue_days ? `${fin.overdue_days} hari` : ""} tone={Number(fin.overdue_amount) > 0 ? "#C0392B" : "#1C1C1E"} testId="supplier-360-overdue" />
              <Kpi label="Nilai PO Terbuka" value={money(fin.open_po_value)} sub={`${fin.open_po_count || 0} PO terbuka`} />
              <Kpi label="Total Pembelian YTD" value={money(fin.purchase_ytd)} />
              <Kpi label="Total Dibayar" value={money(fin.paid_total)} />
              <Kpi label="Total Tagihan" value={money(fin.bill_total)} />
              <Kpi label="Termin (TOP)" value={fin.payment_term_code || "—"} />
              <Kpi label="Lead Time" value={`${fin.lead_time_days || 0} hari`} sub={fin.avg_lead_time_days != null ? `rata2 ${fin.avg_lead_time_days} hari` : ""} />
              <Kpi label="Rating" value={fin.rating != null ? `${fin.rating} / 5` : "—"} icon={<Star size={11} className="text-[#F0A500]" />} />
            </div>
          </div>

          <div className="section-card">
            <div className="section-head"><h3 className="text-[12.5px] font-bold">Profil & Kontak</h3></div>
            <div className="section-body space-y-2 text-[11.5px]">
              <p className="flex items-center gap-2"><PhoneCall size={12} className="text-[#6B6B73]" /><span className="font-semibold">{data.pic_name || "—"}</span>{data.phone ? <span className="text-[#9A9BA3] ml-auto">{data.phone}</span> : null}</p>
              {data.email && <p className="pl-5 text-[#6B6B73]">{data.email}</p>}
              <p className="flex items-start gap-2"><MapPin size={12} className="text-[#6B6B73] mt-0.5" /><span className="text-[#3C3C43]">{[data.address, data.city].filter(Boolean).join(", ") || "—"}</span></p>
              <div className="pt-2 border-t border-[#EFF0F2] space-y-1">
                {data.npwp && <p><span className="text-[#9A9BA3]">NPWP:</span> {data.npwp}</p>}
                <p><span className="text-[#9A9BA3]">Jenis Barang:</span> {data.goods_type || "—"}</p>
                <p><span className="text-[#9A9BA3]">Termin Pembayaran:</span> {data.payment_term_code || "—"}</p>
              </div>
              {data.notes && <p className="pt-2 border-t border-[#EFF0F2] text-[#3C3C43]">{data.notes}</p>}
            </div>
          </div>
        </div>

        {/* Right: history */}
        <div className="section-card self-start">
          <div className="section-head">
            <div className="tab-bar">
              {TABS.map((t) => { const Icon = t.icon; const n = { po: pos.length, bills: bills.length, returns: rets.length, documents: docs.length, prices: data.price_list_count }[t.key];
                return (
                  <button key={t.key} data-testid={`supplier-360-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                    <Icon size={13} /> {t.label}{n != null && <span className="tab-badge">{n}</span>}
                  </button>
                ); })}
            </div>
          </div>
          <div className="section-body">
            {tab === "po" && <RowList testId="supplier-360-list-po" rows={pos} empty="Belum ada PO." onClick={openPO}
              render={(p) => ({ id: p.id, title: p.po_number || p.id, sub: `${fmtDate(p.created_at)} · ${p.status}`, amount: money(p.total_amount) })} />}
            {tab === "bills" && <RowList testId="supplier-360-list-bills" rows={bills} empty="Belum ada tagihan (vendor bill)." onClick={openBill}
              render={(b) => ({ id: b.id, title: b.bill_number || b.id, sub: `${fmtDate(b.created_at || b.bill_date)} · ${b.status}${Number(b.outstanding) > 0 ? " · sisa " + money(b.outstanding) : ""}`, amount: money(b.grand_total) })} />}
            {tab === "returns" && <RowList testId="supplier-360-list-returns" rows={rets} empty="Belum ada retur pembelian." onClick={openReturn}
              render={(r) => ({ id: r.id, title: r.debit_note_number || r.number || r.id, sub: `${fmtDate(r.created_at)} · ${r.status}`, amount: money(r.total_amount) })} />}
            {tab === "prices" && (
              <div className="space-y-3" data-testid="supplier-360-prices">
                <SupplierPriceList supplierId={data.id} canManage={canManage} />
                <PriceHistory history={priceHistory} />
              </div>
            )}
            {tab === "documents" && <RowList testId="supplier-360-list-documents" rows={docs} empty="Belum ada dokumen." onClick={openDoc}
              render={(d) => ({ id: d.source_id, title: `${d.label} · ${d.number}`, sub: `${fmtDate(d.date)} · ${d.status || "—"}`, amount: money(d.amount) })} />}
            {tab === "scorecard" && <SupplierScorecard supplierId={data.id} />}
          </div>
        </div>
      </div>

      <RecordDetailModal open={!!record} onClose={() => setRecord(null)} currentUser={currentUser}
        onChanged={load} {...(record || {})} />
    </div>
  );
}

function RowList({ rows, render, empty, onClick, testId }) {
  if (!rows.length) return <div className="py-8 text-center text-[11.5px] text-[#9A9BA3]" data-testid={`${testId}-empty`}>{empty}</div>;
  return (
    <div className="divide-y divide-[#EFF0F2] max-h-[460px] overflow-y-auto" data-testid={testId}>
      {rows.map((row, i) => { const r = render(row); return (
        <button key={r.id || i} data-testid={`${testId}-row-${r.id || i}`} onClick={() => onClick(row)}
          className="flex w-full items-center justify-between py-2.5 px-1 text-left text-[11.5px] hover:bg-[#FAFBFC] rounded-md transition-colors">
          <div className="min-w-0"><p className="truncate font-semibold text-[#0058CC]">{r.title}</p><p className="text-[10px] text-[#6B6B73]">{r.sub}</p></div>
          <span className="tabular-nums font-semibold shrink-0 ml-2">{r.amount}</span>
        </button>
      ); })}
    </div>
  );
}

function PriceHistory({ history }) {
  if (!history.length) return null;
  return (
    <div className="section-card" data-testid="supplier-360-price-history">
      <div className="section-head"><h3 className="text-[12px] font-bold">Riwayat Harga (dari PO)</h3></div>
      <div className="section-body space-y-2">
        {history.map((h) => (
          <div key={h.product_id} className="rounded-lg border border-[#EFF0F2] p-2">
            <div className="flex items-center justify-between mb-1">
              <p className="text-[11.5px] font-semibold">{h.product_name}</p>
              <span className="text-[10.5px] text-[#6B6B73]">terakhir <b className="text-[#0058CC]">{money(h.last_price)}</b> · {h.points} titik</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {h.entries.slice(0, 8).map((e, i) => (
                <span key={i} className="rounded bg-[#F4F6F8] px-1.5 py-0.5 text-[10px] text-[#4A4B53]" title={`${e.po_number} · ${fmtDate(e.date)}`}>
                  {money(e.price)} <span className="text-[#9A9BA3]">{fmtDate(e.date)}</span>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, tone = "#1C1C1E", icon, testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2" data-testid={testId}>
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93] flex items-center gap-1">{icon}{label}</p>
      <p className="text-[14px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
      {sub && <p className="text-[9.5px] text-[#9A9BA3]">{sub}</p>}
    </div>
  );
}
