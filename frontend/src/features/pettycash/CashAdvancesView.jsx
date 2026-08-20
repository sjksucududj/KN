import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Wallet, Plus, RefreshCw, FileText } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import { CA_STATUS, StatusPill, fmtDate } from "./pettyCashShared";
import CashAdvanceForm from "./CashAdvanceForm";
import CashAdvanceDetail from "./CashAdvanceDetail";

/**
 * CashAdvancesView — Form Pengajuan Dana (PD).
 * List + metrics + filter status; buat/ubah via CashAdvanceForm; detail + workflow
 * (submit → approval berjenjang → disburse) via CashAdvanceDetail.
 */
const TABS = [
  { key: "", label: "Semua" },
  { key: "draft", label: "Draf" },
  { key: "pending_atasan", label: "Menunggu Persetujuan" },
  { key: "approved", label: "Disetujui" },
  { key: "disbursed", label: "Dicairkan" },
  { key: "settled", label: "Selesai" },
  { key: "rejected", label: "Ditolak" },
];
const PENDING = ["pending_atasan", "pending_pimpinan", "pending_finance"];

export default function CashAdvancesView({ currentUser, selectedEntity = "all", entities = [] }) {
  const [view, setView] = useState("list");     // list | create | edit | detail
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState(null);

  const canCreate = ["admin", "manager", "sales"].includes(currentUser?.role);

  useEffect(() => { load(); }, [selectedEntity]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const res = await axios.get(`${API}/cash-advances`, { params });
      setRows(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Pengajuan Dana.");
    } finally { setLoading(false); }
  }

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 3500); }

  async function openDetail(id) {
    try {
      const res = await axios.get(`${API}/cash-advances/${id}`);
      setSelected(res.data); setView("detail");
    } catch (e) { flash(e.response?.data?.detail || "Gagal memuat detail."); }
  }

  const metrics = useMemo(() => {
    const m = { total: rows.length, pending: 0, approved: 0, disbursed: 0, amount: 0 };
    rows.forEach((r) => {
      if (PENDING.includes(r.status)) m.pending += 1;
      if (r.status === "approved") m.approved += 1;
      if (r.status === "disbursed" || r.status === "settled") m.disbursed += 1;
      m.amount += Number(r.total_amount) || 0;
    });
    return m;
  }, [rows]);

  const filtered = rows.filter((r) => {
    if (!statusFilter) return true;
    if (statusFilter === "pending_atasan") return PENDING.includes(r.status);
    return r.status === statusFilter;
  });

  const entityName = (id) => entities.find((e) => e.id === id)?.short_name
    || entities.find((e) => e.id === id)?.legal_name || id || "—";

  if (view === "create" || view === "edit") {
    return (
      <CashAdvanceForm
        record={view === "edit" ? selected : null}
        entities={entities} selectedEntity={selectedEntity}
        onCancel={() => setView(selected && view === "edit" ? "detail" : "list")}
        onSaved={(rec, isEdit) => { flash(`${rec.number} ${isEdit ? "diperbarui" : "dibuat"}.`); setSelected(rec); setView("detail"); load(); }}
      />
    );
  }

  if (view === "detail" && selected) {
    return (
      <CashAdvanceDetail
        ca={selected} currentUser={currentUser} entities={entities}
        onBack={() => { setSelected(null); setView("list"); load(); }}
        onEdit={(rec) => { setSelected(rec); setView("edit"); }}
        onChanged={(rec) => { setSelected(rec); load(); }}
        flash={flash}
      />
    );
  }

  return (
    <div data-testid="cash-advances-view" className="grid gap-4">
      {toast && <div className="notice-bar success" data-testid="ca-toast"><span>{toast}</span><button onClick={() => setToast("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="ca-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Wallet size={15} className="text-[#0058CC]" />
            <span className="kicker">Kas & Petty Cash</span>
            <h2 data-testid="ca-title">Pengajuan Dana (PD)</h2>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="ca-refresh" className="icon-button" onClick={load} aria-label="Muat ulang"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
            {canCreate && <button data-testid="ca-create-btn" className="btn-primary" onClick={() => { setSelected(null); setView("create"); }}><Plus size={14} /> PD Baru</button>}
          </div>
        </div>

        <section data-testid="ca-metrics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 p-3">
          <Metric label="Total PD" value={metrics.total} tone="rgba(0,122,255,.12)" testId="ca-metric-total" />
          <Metric label="Menunggu Persetujuan" value={metrics.pending} tone="rgba(255,149,0,.16)" testId="ca-metric-pending" />
          <Metric label="Disetujui" value={metrics.approved} tone="rgba(52,199,89,.15)" testId="ca-metric-approved" />
          <Metric label="Nilai Diajukan" value={formatCurrency(metrics.amount)} tone="rgba(0,122,255,.10)" testId="ca-metric-amount" money />
        </section>

        <div className="flex flex-wrap gap-1.5 px-3 pb-3">
          {TABS.map((t) => (
            <button key={t.key || "all"} data-testid={`ca-tab-${t.key || "all"}`} className={`tab-button ${statusFilter === t.key ? "active" : ""}`} onClick={() => setStatusFilter(t.key)}>{t.label}</button>
          ))}
        </div>
      </section>

      <section className="section-card">
        <div className="overflow-x-auto">
          <div className="grid grid-cols-[100px_1.4fr_120px_140px_130px_90px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Kegiatan / Divisi</span><span>Entitas</span><span className="text-right">Total</span><span>Status</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div data-testid="ca-loading" className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
          ) : filtered.length === 0 ? (
            <div data-testid="ca-empty" className="py-12 text-center text-[12px] text-[#6B6B73]">
              <FileText className="mx-auto mb-2 text-gray-300" size={28} />
              <p>Belum ada Pengajuan Dana. Klik <b>PD Baru</b> untuk membuat.</p>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2]">
              {filtered.map((r) => (
                <div key={r.id} data-testid={`ca-row-${r.id}`} className="grid grid-cols-[100px_1.4fr_120px_140px_130px_90px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{r.number}</span>
                  <div className="min-w-0"><p className="text-[12px] font-semibold truncate">{r.kegiatan || "—"}</p><p className="text-[10.5px] text-[#9A9BA3] truncate">{r.divisi || "—"} · {fmtDate(r.tanggal_pengajuan)}</p></div>
                  <span className="text-[11px] truncate">{entityName(r.entity_id)}</span>
                  <span className="text-[12px] tabular-nums text-right font-semibold">{formatCurrency(r.total_amount)}</span>
                  <StatusPill status={r.status} />
                  <div className="text-right"><button data-testid={`ca-open-${r.id}`} className="btn-secondary btn-xs" onClick={() => openDetail(r.id)}>Detail</button></div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value, tone, testId, money }) {
  return (
    <div data-testid={testId} className="metric-card">
      <div className="metric-icon" style={{ background: tone }}><Wallet size={16} className="text-[#1C1C1E]" /></div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
        <p className={`${money ? "text-[15px]" : "text-[17px]"} font-bold tabular-nums truncate`}>{value}</p>
      </div>
    </div>
  );
}
