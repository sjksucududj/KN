import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Receipt, Plus, Send, Wallet, Scale, Search } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import EntityBadge from "../../components/EntityBadge";
import PaginationBar from "../../components/PaginationBar";
import { usePagedList } from "../../hooks/usePagedList";

// FASE P6 — kolom Unduh CSV (mengikuti kolom tabel vendor bill).
const CSV_COLUMNS = [
  { key: "bill_number", header: "Nomor Tagihan" },
  { key: "supplier_name", header: "Supplier" },
  { key: "po_number", header: "No. PO" },
  { header: "Jumlah Item", type: "int", get: (b) => b.items?.length || 0 },
  { key: "grand_total", header: "Total", type: "num" },
  { header: "Sisa", type: "num", get: (b) => Number(b.financials?.outstanding ?? b.outstanding ?? 0) },
  { key: "match_status", header: "Match" },
  { key: "status", header: "Status" },
  { key: "supplier_invoice_no", header: "Inv. Supplier" },
  { key: "due_date", header: "Jatuh Tempo", type: "date" },
];
import VendorBillCreateModal from "./VendorBillCreateModal";
import VendorBillDetailPanel from "./VendorBillDetailPanel";
import DetailModal from "../../components/DetailModal";

/**
 * VendorBillsView (Fase 5.2 — P0-2) — Tagihan Supplier (Vendor Bill) + 3-Way Matching.
 * AP berbasis bill posted. PO ↔ GR ↔ Bill dicocokkan dengan toleransi qty & harga.
 */
const TABS = [
  { key: "all", label: "Semua" },
  { key: "draft", label: "Draf" },
  { key: "pending_approval", label: "Menunggu" },
  { key: "posted", label: "Posted" },
  { key: "paid", label: "Lunas" },
  { key: "cancelled", label: "Batal" },
];

function StatusPill({ status }) {
  const map = {
    draft: ["pill-muted", "Draft"], pending_approval: ["pill-warning", "Menunggu"],
    posted: ["pill-info", "Posted"], paid: ["pill-success", "Lunas"], cancelled: ["pill-danger", "Batal"],
  };
  const [cls, label] = map[status] || ["pill-muted", status];
  return <span className={`status-pill ${cls}`}>{label}</span>;
}
function MatchPill({ status }) {
  const map = { matched: ["pill-success", "Match"], warning: ["pill-warning", "Selisih"], blocked: ["pill-danger", "Over-bill"] };
  const [cls, label] = map[status] || ["pill-muted", "—"];
  return <span className={`status-pill ${cls}`}>{label}</span>;
}

export default function VendorBillsView({ currentUser, selectedEntity }) {
  const [pos, setPos] = useState([]);
  const [summary, setSummary] = useState(null);
  const [counts, setCounts] = useState({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);

  const canApprove = ["admin", "manager"].includes(currentUser?.role);
  const canCreate = ["admin", "manager"].includes(currentUser?.role);

  // P2 — paginasi server-side; tab status jadi filter server, search q server-side.
  const params = useMemo(() => {
    const p = {};
    if (selectedEntity && selectedEntity !== "all") p.entity_id = selectedEntity;
    if (tab !== "all") p.status = tab;
    return p;
  }, [selectedEntity, tab]);
  const paged = usePagedList("/vendor-bills", { pageSize: 20, params, search });
  const filtered = paged.items;   // sudah difilter status di server
  const loading = paged.loading;

  useEffect(() => { loadMeta(); }, [selectedEntity]); // eslint-disable-line

  async function loadMeta() {
    try {
      const mp = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const [poRes, sRes, cRes] = await Promise.all([
        axios.get(`${API}/purchase-orders`, { params: mp }).catch(() => ({ data: [] })),
        axios.get(`${API}/vendor-bills/payables/summary`, { params: mp }).catch(() => ({ data: null })),
        axios.get(`${API}/vendor-bills/status-counts`, { params: mp }).catch(() => ({ data: {} })),
      ]);
      const poData = Array.isArray(poRes.data) ? poRes.data : (poRes.data?.items || []);
      // PO yang bisa ditagih: sudah disetujui/diterima (bukan draft/menunggu/batal/ditolak)
      const billable = poData.filter(
        (p) => !["waiting_approval", "rejected", "cancelled", "draft"].includes(p.status));
      setPos(billable);
      setSummary(sRes.data);
      setCounts(cRes.data || {});
    } catch (e) { /* non-blocking */ }
  }

  const reload = () => { paged.refresh(); loadMeta(); };

  async function refreshDetail(id) {
    try {
      const r = await axios.get(`${API}/vendor-bills/${id}`);
      setDetail(r.data);
    } catch { /* ignore */ }
  }

  function onCreated(bill, submitted) {
    setShowCreate(false);
    const msg = bill.status === "posted" ? "langsung di-posting (match bersih)"
      : bill.status === "pending_approval" ? "menunggu approval (ada selisih)" : "disimpan sebagai draft";
    setNotice(`Vendor Bill ${bill.bill_number} dibuat — ${msg}.`);
    reload();
  }

  async function onAction(action, data) {
    const labels = { submit: "disubmit", approve: "disetujui & posted", reject: "ditolak", cancel: "dibatalkan", pay: "pembayaran dicatat" };
    setNotice(`${data.bill_number}: ${labels[action] || action}.`);
    setDetail(data);
    reload();
  }

  async function quickAct(bill, action, body) {
    try {
      const urls = {
        submit: `${API}/vendor-bills/${bill.id}/submit`,
        approve: `${API}/vendor-bills/${bill.id}/approve`,
      };
      const r = await axios.post(urls[action], body || {});
      const labels = { submit: "disubmit", approve: "disetujui & posted" };
      setNotice(`${r.data.bill_number}: ${labels[action] || action}.`);
      reload();
    } catch (e) {
      setError(e.response?.data?.detail || `Gagal ${action}.`);
    }
  }

  return (
    <div data-testid="vendor-bills-view">
      {notice && <div className="notice-bar success" data-testid="vb-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <ErrorNotice message={error || paged.error} onRetry={reload} onDismiss={() => setError("")} testId="vb-error" />

      {/* AP summary */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 mb-3" data-testid="vb-summary">
          <SummaryCard label="Total Hutang (AP)" value={formatCurrency(summary.total_outstanding)} tone="text-red-600" big testId="vb-summary-total" />
          <SummaryCard label="0–30 hari" value={formatCurrency(summary.aging?.["0-30"])} />
          <SummaryCard label="31–60 hari" value={formatCurrency(summary.aging?.["31-60"])} />
          <SummaryCard label="61–90 hari" value={formatCurrency(summary.aging?.["61-90"])} tone="text-amber-600" />
          <SummaryCard label="> 90 hari" value={formatCurrency(summary.aging?.[">90"])} tone="text-red-600" />
        </div>
      )}

      {/* Header + tabs */}
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Receipt size={16} className="text-[#0058CC]" />
            <h2 data-testid="vendor-bills-title">Tagihan Supplier (Vendor Bill)</h2>
          </div>
          {canCreate && (
            <button data-testid="create-vendor-bill-button" onClick={() => setShowCreate(true)} className="primary-button">
              <Plus size={13} /> Buat Vendor Bill
            </button>
          )}
        </div>
        <div className="section-body">
          <div className="relative max-w-sm mb-2">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="vb-search" value={search} onChange={(e) => setSearch(e.target.value)}
              className="field !pl-8 !py-1.5 text-[12px]" placeholder="Cari No. bill / supplier / PO / inv. supplier..." />
          </div>
          <div className="tab-bar">
            {TABS.map((t) => (
              <button key={t.key} data-testid={`vb-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                {t.label}<span className="tab-badge">{counts[t.key] || 0}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* List */}
      <div className="section-card">
        <div className="overflow-hidden">
          <div className="grid grid-cols-[110px_1.4fr_120px_120px_110px_90px_100px_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Supplier / PO</span><span className="text-right">Total</span><span className="text-right">Sisa</span>
            <span>Match</span><span>Status</span><span>Inv. Supplier</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat vendor bill...</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]">
              <Scale className="mx-auto mb-2 text-gray-300" size={28} />
              <p>Belum ada vendor bill{tab !== "all" ? ` (${tab})` : ""}.</p>
              {canCreate && tab === "all" && <p className="mt-1 text-[11px]">Buat tagihan dari PO yang sudah diterima untuk memulai 3-way matching.</p>}
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2]">
              {filtered.map((b) => (
                <div key={b.id} data-testid={`vb-row-${b.id}`} onClick={() => setDetail(b)}
                     className="grid grid-cols-[110px_1.4fr_120px_120px_110px_90px_100px_120px] items-center px-3 py-2.5 hover:bg-[#FAFBFC] cursor-pointer">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{b.bill_number}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{b.supplier_name}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate flex items-center gap-1">
                      <EntityBadge entityId={b.entity_id} />
                      <span className="truncate">{b.po_number} · {b.items?.length || 0} item</span>
                    </p>
                  </div>
                  <span className="text-[12px] font-bold tabular-nums text-right">{formatCurrency(b.grand_total)}</span>
                  <span className="text-[12px] tabular-nums text-right text-red-600">{formatCurrency(b.financials?.outstanding ?? b.outstanding)}</span>
                  <MatchPill status={b.match_status} />
                  <StatusPill status={b.status} />
                  <span className="text-[10.5px] text-[#6B6B73] truncate">{b.supplier_invoice_no || "—"}</span>
                  <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                    {b.status === "draft" && (
                      <button data-testid={`vb-quick-submit-${b.id}`} onClick={() => quickAct(b, "submit")} className="secondary-button !px-2 !py-1 text-[11px]"><Send size={11} /> Kirim</button>
                    )}
                    {b.status === "pending_approval" && canApprove && (
                      <button data-testid={`vb-quick-approve-${b.id}`} onClick={() => quickAct(b, "approve")} className="primary-button !px-2 !py-1 text-[11px]">Setujui</button>
                    )}
                    {b.status === "posted" && (
                      <button data-testid={`vb-quick-pay-${b.id}`} onClick={() => setDetail(b)} className="primary-button !px-2 !py-1 text-[11px]"><Wallet size={11} /> Bayar</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="px-3 py-2 border-t border-[#EFF0F2]">
          <PaginationBar
            testId="vb-pager" label="vendor bill"
            page={paged.page} pageSize={paged.pageSize} total={paged.total}
            hasMore={paged.hasMore} loading={paged.loading}
            onPrev={paged.prev} onNext={paged.next} onPageSize={paged.setPageSize}
            exportConfig={{ columns: CSV_COLUMNS, rows: filtered,
              fetchAll: paged.fetchAll, filename: "tagihan-supplier" }}
          />
        </div>
      </div>

      <VendorBillCreateModal
        open={showCreate}
        pos={pos}
        selectedEntity={selectedEntity}
        onClose={() => setShowCreate(false)}
        onCreated={onCreated}
        onError={(m) => setError(m)}
      />

      {detail && (
        <DetailModal onClose={() => setDetail(null)}
          label="Rincian tagihan supplier" testId="vb-detail-modal">
          <VendorBillDetailPanel
            bill={detail}
            canApprove={canApprove}
            currentUser={currentUser}
            onClose={() => setDetail(null)}
            onAction={onAction}
            onError={(m) => setError(m)}
          />
        </DetailModal>
      )}
    </div>
  );
}

function SummaryCard({ label, value, tone, big, testId }) {
  return (
    <div className="section-card !p-3" data-testid={testId}>
      <p className="text-[9.5px] font-bold uppercase text-[#6B6B73]">{label}</p>
      <p className={`${big ? "text-[18px]" : "text-[14px]"} font-bold tabular-nums ${tone || "text-[#0F1115]"}`}>{value}</p>
    </div>
  );
}
