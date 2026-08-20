import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ArrowLeft, Edit3, Factory, MapPin, PhoneCall, Gauge, Wallet, FileText,
  ClipboardList, Receipt, BookOpen, BarChart3 } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import useProcessTypes from "../../hooks/useProcessTypes";
import RecordDetailModal from "../documents/RecordDetailModal";

const TABS = [
  { key: "recipes", label: "Resep", icon: BookOpen },
  { key: "orders", label: "Order Makloon", icon: ClipboardList },
  { key: "bills", label: "Tagihan Jasa", icon: Receipt },
  { key: "documents", label: "Dokumen", icon: FileText },
  { key: "scorecard", label: "Scorecard", icon: BarChart3 },
];
const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "—");
const pct = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const money = (v) => formatCurrency(Number(v || 0));

const STATUS_TONE = { completed: "success", posted: "success", paid: "success", in_process: "info", in_progress: "info", processing: "info", pending: "warning", draft: "muted", cancelled: "danger", rejected: "danger" };
const tone = (s) => STATUS_TONE[(s || "").toLowerCase()] || "muted";

/** Makloon 360° — profil + kapasitas + keuangan jasa + resep/order/tagihan + dokumen + scorecard. */
export default function Makloon360Panel({ makloonId, currentUser, onBack, onEdit, onError }) {
  const { labelOf: processLabel } = useProcessTypes();   // FASE T (4a)
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("orders");
  const [record, setRecord] = useState(null);

  useEffect(() => { load(); }, [makloonId]); // eslint-disable-line
  async function load() {
    setLoading(true);
    try { const r = await axios.get(`${API}/makloons/${makloonId}`); setData(r.data); }
    catch (e) { onError?.(e.response?.data?.detail || "Gagal memuat detail makloon."); onBack?.(); }
    finally { setLoading(false); }
  }

  if (loading && !data) return <div className="section-card py-12 text-center text-[12px] text-[#6B6B73]" data-testid="makloon-360-loading">Memuat detail makloon…</div>;
  if (!data) return null;
  const sc = data.scorecard?.metrics || {};
  const fin = data.finance || {};
  const orders = data.orders || [];
  const bills = data.service_bills || [];
  const docs = data.documents || [];
  const entityId = data.entity_id;

  function openOrder(o) {
    setRecord({
      icon: <ClipboardList size={17} className="text-[#0058CC]" />, title: o.mko_number || o.id, code: o.mko_number,
      statusText: o.status, statusTone: tone(o.status),
      docType: "makloon_spk", sourceId: o.id, number: o.mko_number, entityId, esignable: true,
      meta: [
        { label: "Tanggal", value: fmtDate(o.created_at) },
        { label: "Status", value: o.status },
        { label: "Jumlah Langkah", value: (o.steps || []).length },
      ],
      items: o.steps || [],
      itemColumns: [
        { label: "Proses", render: (s) => processLabel(s.process_type) },
        { label: "Input", align: "right", render: (s) => formatQty(s.input_qty) },
        { label: "Output (exp.)", align: "right", render: (s) => formatQty(s.expected_output_qty) },
        { label: "Tarif", align: "right", render: (s) => money(s.tariff) },
        { label: "Status", render: (s) => s.status || "—" },
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
        { label: "Tarif", value: money(b.tariff) },
        { label: "Grand Total", value: money(b.grand_total), tone: "text-[#0058CC]" },
        { label: "Belum Lunas", value: money(b.outstanding), tone: Number(b.outstanding) > 0 ? "text-[#C0392B]" : "" },
      ],
      totals: [
        { label: "Netto", value: money(b.net_amount) },
        ...(b.ppn_amount ? [{ label: "PPN", value: money(b.ppn_amount) }] : []),
        { label: "Grand Total", value: money(b.grand_total), bold: true, tone: "text-[#0058CC]" },
      ],
      note: "Tagihan jasa makloon (vendor bill) — ringkasan nilai jasa.",
    });
  }
  function openDoc(d) {
    setRecord({
      icon: <FileText size={17} className="text-[#0058CC]" />, title: d.number, code: d.number,
      statusText: d.status, statusTone: tone(d.status),
      docType: d.doc_type, sourceId: d.source_id, number: d.number, entityId, label: d.label,
      esignable: ["makloon_spk", "vendor_bill"].includes(d.doc_type),
      meta: [
        { label: "Jenis", value: d.label }, { label: "Tanggal", value: fmtDate(d.date) },
        { label: "Status", value: d.status }, { label: "Nilai", value: money(d.amount), tone: "text-[#0058CC]" },
      ],
    });
  }

  return (
    <div data-testid="makloon-360-panel">
      <button data-testid="makloon-360-back" onClick={onBack} className="secondary-button mb-3"><ArrowLeft size={13} /> Kembali ke daftar</button>

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Factory size={17} className="text-[#0058CC]" />
              <h2 className="truncate" data-testid="makloon-360-name">{data.name}</h2>
              <span className="text-[11px] font-bold text-[#0058CC]">{data.code}</span>
              <span className={`status-pill ${data.status === "active" ? "pill-success" : "pill-muted"}`}>{data.status === "active" ? "Aktif" : "Nonaktif"}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {(data.process_types || []).map((p) => <span key={p} className="rounded-full bg-[#EAF2FF] px-2 py-0.5 text-[10.5px] font-semibold text-[#0058CC]">{processLabel(p)}</span>)}
            </div>
          </div>
          <button data-testid="makloon-360-edit" onClick={() => onEdit?.(data)} className="secondary-button"><Edit3 size={13} /> Ubah</button>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
        <div className="space-y-3">
          {/* Keuangan Jasa (AP) */}
          <div className="section-card">
            <div className="section-head"><h3 className="text-[12.5px] font-bold flex items-center gap-2"><Wallet size={14} className="text-[#0058CC]" /> Keuangan Jasa (AP)</h3></div>
            <div className="section-body grid grid-cols-2 gap-2">
              <Kpi label="Hutang Jasa (AP)" value={money(fin.service_ap_outstanding)} tone="#0058CC" testId="makloon-360-ap" />
              <Kpi label="Jatuh Tempo (Lewat Tempo)" value={money(fin.overdue_amount)} sub={fin.overdue_days ? `${fin.overdue_days} hari` : ""} tone={Number(fin.overdue_amount) > 0 ? "#C0392B" : "#1C1C1E"} />
              <Kpi label="Total Tagihan Jasa" value={money(fin.service_bill_total)} />
              <Kpi label="Pesanan Terbuka" value={fin.open_order_count || 0} />
            </div>
          </div>
          {/* Kapasitas & Tarif */}
          <div className="section-card">
            <div className="section-head"><h3 className="text-[12.5px] font-bold flex items-center gap-2"><Gauge size={14} className="text-[#0058CC]" /> Kapasitas & Tarif</h3></div>
            <div className="section-body grid grid-cols-2 gap-2">
              <Kpi label="Kapasitas/Bulan" value={`${formatQty(data.capacity_per_month || 0)} ${data.capacity_unit || ""}`} />
              <Kpi label="Tarif Default" value={data.default_tariff ? money(data.default_tariff) : "—"} sub={`per ${data.tariff_unit || "output"}`} />
              <Kpi label="Lead Time" value={`${data.lead_time_days || 0} hari`} />
              <Kpi label="Resep Terhubung" value={data.recipe_count || 0} />
            </div>
            {data.capacity_note && <p className="px-3 pb-3 text-[11px] text-[#6B6B73]">{data.capacity_note}</p>}
          </div>
          {/* Profil & Kontak */}
          <div className="section-card">
            <div className="section-head"><h3 className="text-[12.5px] font-bold">Profil & Kontak</h3></div>
            <div className="section-body space-y-1.5 text-[11.5px]">
              <p className="flex items-center gap-2"><PhoneCall size={12} className="text-[#6B6B73]" /> {data.pic_name || "—"} {data.phone ? `· ${data.phone}` : ""}</p>
              {data.email && <p className="text-[#6B6B73] pl-5">{data.email}</p>}
              <p className="flex items-start gap-2"><MapPin size={12} className="mt-0.5 text-[#6B6B73]" /> {[data.address, data.city].filter(Boolean).join(", ") || "—"}</p>
              {data.npwp && <p className="pl-5 text-[#6B6B73]">NPWP: {data.npwp}</p>}
              {data.notes && <p className="pt-2 border-t border-[#EFF0F2] text-[#3C3C43]">{data.notes}</p>}
            </div>
          </div>
        </div>

        <div className="section-card self-start">
          <div className="section-head"><div className="tab-bar">
            {TABS.map((t) => { const Icon = t.icon; const n = { recipes: data.recipe_count, orders: orders.length, bills: bills.length, documents: docs.length }[t.key];
              return (
                <button key={t.key} data-testid={`makloon-360-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                  <Icon size={13} /> {t.label}{n != null && <span className="tab-badge">{n}</span>}
                </button>
              ); })}
          </div></div>
          <div className="section-body">
            {tab === "scorecard" ? (
              <div data-testid="makloon-360-scorecard">
                {!data.scorecard?.has_data ? (
                  <div className="py-8 text-center text-[11.5px] text-[#9A9BA3]">Belum ada data proses (mulai terisi setelah Order Makloon dijalankan).</div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    <Kpi label="Total Pesanan" value={sc.total_orders} />
                    <Kpi label="Langkah Diterima" value={sc.received_steps} />
                    <Kpi label="Yield Realisasi" value={pct(sc.realized_yield)} tone="#0058CC" />
                    <Kpi label="Pencapaian Yield" value={pct(sc.yield_attainment)} />
                    <Kpi label="Total Input" value={formatQty(sc.total_input_qty)} />
                    <Kpi label="Total Output" value={formatQty(sc.total_output_qty)} />
                  </div>
                )}
              </div>
            ) : tab === "recipes" ? (
              <RecipeList rows={data.recipes || []} />
            ) : tab === "orders" ? (
              <RowList testId="makloon-360-list-orders" rows={orders} empty="Belum ada order makloon." onClick={openOrder}
                render={(o) => ({ id: o.id, title: o.mko_number || o.id, sub: `${fmtDate(o.created_at)} · ${o.status}`, amount: `${(o.steps || []).length} step` })} />
            ) : tab === "bills" ? (
              <RowList testId="makloon-360-list-bills" rows={bills} empty="Belum ada tagihan jasa." onClick={openBill}
                render={(b) => ({ id: b.id, title: b.bill_number || b.id, sub: `${fmtDate(b.created_at || b.bill_date)} · ${b.status}${Number(b.outstanding) > 0 ? " · sisa " + money(b.outstanding) : ""}`, amount: money(b.grand_total) })} />
            ) : (
              <RowList testId="makloon-360-list-documents" rows={docs} empty="Belum ada dokumen." onClick={openDoc}
                render={(d) => ({ id: d.source_id, title: `${d.label} · ${d.number}`, sub: `${fmtDate(d.date)} · ${d.status || "—"}`, amount: money(d.amount) })} />
            )}
          </div>
        </div>
      </div>

      <RecordDetailModal open={!!record} onClose={() => setRecord(null)} currentUser={currentUser}
        onChanged={load} {...(record || {})} />
    </div>
  );
}

function RecipeList({ rows }) {
  if (!rows.length) return <div className="py-8 text-center text-[11.5px] text-[#9A9BA3]" data-testid="makloon-360-empty-recipes">Belum ada resep memakai makloon ini.</div>;
  return (
    <div className="divide-y divide-[#EFF0F2] max-h-[460px] overflow-y-auto" data-testid="makloon-360-list-recipes">
      {rows.map((r) => (
        <div key={r.id} className="flex items-center justify-between py-2 text-[11.5px]">
          <div className="min-w-0"><p className="truncate font-semibold">{r.name}</p><p className="text-[10px] text-[#6B6B73]">{processLabel(r.process_type)} · yield {r.yield_factor}</p></div>
          <span className="rounded bg-[#F3E9FA] px-1.5 text-[10px] font-bold text-[#6B219A]">{r.process_type}</span>
        </div>
      ))}
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

function Kpi({ label, value, sub, tone = "#1C1C1E", testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2" data-testid={testId}>
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[15px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
      {sub && <p className="text-[9.5px] text-[#9A9BA3]">{sub}</p>}
    </div>
  );
}
