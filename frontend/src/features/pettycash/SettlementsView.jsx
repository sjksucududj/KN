import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  ReceiptText, Plus, RefreshCw, ArrowLeft, CheckCircle2, XCircle, Send, Printer, FileText,
} from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import { STL_STATUS, StatusPill, fmtDate, printSettlement } from "./pettyCashShared";
import SettlementForm from "./SettlementForm";

/**
 * SettlementsView — Laporan Pertanggungjawaban (LPJ) atas PD dicairkan.
 * List + detail (submit → approve[post GL] / reject) + cetak.
 */
const TABS = [
  { key: "", label: "Semua" }, { key: "draft", label: "Draf" },
  { key: "submitted", label: "Diajukan" }, { key: "posted_to_gl", label: "Terposting" },
  { key: "rejected", label: "Ditolak" },
];

export default function SettlementsView({ currentUser, selectedEntity = "all", entities = [] }) {
  const [view, setView] = useState("list");
  const [rows, setRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState(null);

  const canCreate = ["admin", "manager", "sales"].includes(currentUser?.role);

  useEffect(() => { load(); loadCats(); }, [selectedEntity]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const res = await axios.get(`${API}/cash-advance-settlements`, { params });
      setRows(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat pertanggungjawaban.");
    } finally { setLoading(false); }
  }
  async function loadCats() {
    try { const r = await axios.get(`${API}/expense-categories`); setCategories(Array.isArray(r.data) ? r.data : []); } catch (e) { /* noop */ }
  }
  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 3500); }

  async function openDetail(id) {
    try { const res = await axios.get(`${API}/cash-advance-settlements/${id}`); setSelected(res.data); setView("detail"); }
    catch (e) { flash(e.response?.data?.detail || "Gagal memuat detail."); }
  }

  const metrics = useMemo(() => {
    const m = { total: rows.length, submitted: 0, posted: 0, amount: 0 };
    rows.forEach((r) => {
      if (r.status === "submitted") m.submitted += 1;
      if (r.status === "posted_to_gl") m.posted += 1;
      m.amount += Number(r.total_pengeluaran) || 0;
    });
    return m;
  }, [rows]);

  const filtered = rows.filter((r) => !statusFilter || r.status === statusFilter);
  const entityName = (id) => entities.find((e) => e.id === id)?.short_name || entities.find((e) => e.id === id)?.legal_name || id || "—";
  const catLabels = useMemo(() => Object.fromEntries(categories.map((c) => [c.code, c.label])), [categories]);

  if (view === "create") {
    return (
      <SettlementForm categories={categories} selectedEntity={selectedEntity}
        onCancel={() => setView("list")}
        onSaved={(rec) => { flash(`${rec.number} dibuat.`); setSelected(rec); setView("detail"); load(); }} />
    );
  }

  if (view === "detail" && selected) {
    return (
      <SettlementDetail stl={selected} currentUser={currentUser} entities={entities} catLabels={catLabels}
        onBack={() => { setSelected(null); setView("list"); load(); }}
        onChanged={(rec) => { setSelected(rec); load(); }} flash={flash} />
    );
  }

  return (
    <div data-testid="settlements-view" className="grid gap-4">
      {toast && <div className="notice-bar success" data-testid="stl-toast"><span>{toast}</span><button onClick={() => setToast("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="stl-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <ReceiptText size={15} className="text-[#0058CC]" />
            <span className="kicker">Kas & Petty Cash</span>
            <h2 data-testid="stl-title">Pertanggungjawaban (LPJ)</h2>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="stl-refresh" className="icon-button" onClick={load} aria-label="Muat ulang"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
            {canCreate && <button data-testid="stl-create-btn" className="btn-primary" onClick={() => setView("create")}><Plus size={14} /> LPJ Baru</button>}
          </div>
        </div>

        <section data-testid="stl-metrics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 p-3">
          <Metric label="Total LPJ" value={metrics.total} tone="rgba(0,122,255,.12)" testId="stl-metric-total" />
          <Metric label="Diajukan" value={metrics.submitted} tone="rgba(255,149,0,.16)" testId="stl-metric-submitted" />
          <Metric label="Terposting GL" value={metrics.posted} tone="rgba(52,199,89,.15)" testId="stl-metric-posted" />
          <Metric label="Total Pengeluaran" value={formatCurrency(metrics.amount)} tone="rgba(0,122,255,.10)" testId="stl-metric-amount" money />
        </section>

        <div className="flex flex-wrap gap-1.5 px-3 pb-3">
          {TABS.map((t) => (<button key={t.key || "all"} data-testid={`stl-tab-${t.key || "all"}`} className={`tab-button ${statusFilter === t.key ? "active" : ""}`} onClick={() => setStatusFilter(t.key)}>{t.label}</button>))}
        </div>
      </section>

      <section className="section-card">
        <div className="overflow-x-auto">
          <div className="grid grid-cols-[100px_1.3fr_110px_140px_130px_90px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Ref PD / Divisi</span><span>Entitas</span><span className="text-right">Pengeluaran</span><span>Status</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div data-testid="stl-loading" className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
          ) : filtered.length === 0 ? (
            <div data-testid="stl-empty" className="py-12 text-center text-[12px] text-[#6B6B73]"><FileText className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada pertanggungjawaban. Klik <b>LPJ Baru</b>.</p></div>
          ) : (
            <div className="divide-y divide-[#EFF0F2]">
              {filtered.map((r) => (
                <div key={r.id} data-testid={`stl-row-${r.id}`} className="grid grid-cols-[100px_1.3fr_110px_140px_130px_90px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{r.number}</span>
                  <div className="min-w-0"><p className="text-[12px] font-semibold truncate">{r.cash_advance_number || "—"}</p><p className="text-[10.5px] text-[#9A9BA3] truncate">{r.divisi || "—"} · {r.periode || "—"}</p></div>
                  <span className="text-[11px] truncate">{entityName(r.entity_id)}</span>
                  <span className="text-[12px] tabular-nums text-right font-semibold">{formatCurrency(r.total_pengeluaran)}</span>
                  <StatusPill status={r.status} map={STL_STATUS} />
                  <div className="text-right"><button data-testid={`stl-open-${r.id}`} className="btn-secondary btn-xs" onClick={() => openDetail(r.id)}>Detail</button></div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

// ─── Detail ──────────────────────────────────────────────────────────────────
function SettlementDetail({ stl, currentUser, entities, catLabels, onBack, onChanged, flash }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [reject, setReject] = useState(false);
  const role = currentUser?.role;
  const entityName = entities.find((e) => e.id === stl.entity_id)?.short_name || entities.find((e) => e.id === stl.entity_id)?.legal_name || stl.entity_id;

  const canSubmit = stl.status === "draft" && ["admin", "manager", "sales"].includes(role);
  const canApprove = ["submitted", "draft"].includes(stl.status) && ["admin", "manager"].includes(role);
  const sisa = Number(stl.sisa_kurang_dana) || 0;

  async function act(path, body, okMsg) {
    setBusy(true); setErr("");
    try {
      const res = await axios.post(`${API}/cash-advance-settlements/${stl.id}/${path}`, body || {});
      flash(okMsg); onChanged(res.data);
    } catch (e) { setErr(e.response?.data?.detail || "Aksi gagal."); } finally { setBusy(false); }
  }

  return (
    <div data-testid="stl-detail" className="grid gap-4">
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <button className="icon-button" onClick={onBack} aria-label="Kembali"><ArrowLeft size={15} /></button>
            <ReceiptText size={15} className="text-[#0058CC]" />
            <h2 data-testid="stl-detail-number">{stl.number}</h2>
            <StatusPill status={stl.status} map={STL_STATUS} testId="stl-detail-status" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button data-testid="stl-print" className="btn-secondary btn-xs" onClick={() => printSettlement(stl, entityName, catLabels)}><Printer size={13} /> Cetak LPJ</button>
            {canSubmit && <button data-testid="stl-submit-btn" className="btn-primary btn-xs" onClick={() => act("submit", {}, `${stl.number} diajukan.`)} disabled={busy}><Send size={13} /> Ajukan</button>}
            {canApprove && <>
              <button data-testid="stl-approve-btn" className="btn-primary btn-xs" onClick={() => act("approve", {}, `${stl.number} disetujui & diposting ke GL.`)} disabled={busy}><CheckCircle2 size={13} /> Setujui & Posting GL</button>
              <button data-testid="stl-reject-btn" className="btn-danger btn-xs" onClick={() => setReject(true)} disabled={busy}><XCircle size={13} /> Tolak</button>
            </>}
          </div>
        </div>
        {err && <div className="notice-bar danger mx-3 mb-3" data-testid="stl-detail-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}

        <div className="section-body grid gap-4">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-[12px]">
            <Meta k="Ref. PD" v={stl.cash_advance_number || "—"} />
            <Meta k="Entitas" v={entityName} />
            <Meta k="Divisi" v={stl.divisi || "—"} />
            <Meta k="Periode" v={stl.periode || "—"} />
            <Meta k="Dibuat oleh" v={stl.dibuat_oleh || "—"} />
            {stl.journal_entry_number && <Meta k="Jurnal GL" v={stl.journal_entry_number} />}
            {stl.disetujui_oleh && <Meta k="Disetujui" v={stl.disetujui_oleh} />}
            {stl.rejected_reason && <Meta k="Alasan Tolak" v={stl.rejected_reason} danger />}
          </div>

          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[110px_1.5fr_1fr_130px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
              <span>Tanggal</span><span>Uraian</span><span>Kategori</span><span className="text-right">Nominal</span>
            </div>
            {(stl.expense_lines || []).map((l, i) => (
              <div key={i} className="grid grid-cols-[110px_1.5fr_1fr_130px] items-center px-3 py-2 border-t border-[#F4F5F7] text-[12px]">
                <span>{fmtDate(l.date)}</span>
                <span className="truncate">{l.description || "—"}</span>
                <span className="truncate">{catLabels[l.category] || l.category}</span>
                <span className="text-right tabular-nums font-semibold">{formatCurrency(l.amount)}</span>
              </div>
            ))}
            <div className="px-3 py-2 border-t border-[#EFF0F2] bg-[#FAFBFC] grid gap-1">
              <RowLine k="Total Pengeluaran" v={formatCurrency(stl.total_pengeluaran)} testId="stl-detail-total" />
              <RowLine k="Dana Diterima (PD)" v={formatCurrency(stl.total_pettycash)} />
              <RowLine k={sisa >= 0 ? "Sisa Dikembalikan" : "Kekurangan Dana"} v={formatCurrency(Math.abs(sisa))} strong tone={sisa >= 0 ? "#1A7A3A" : "#C62828"} testId="stl-detail-sisa" />
            </div>
          </div>
          {stl.catatan && <p className="text-[12px] text-[#3C3C43]"><b>Catatan:</b> {stl.catatan}</p>}
        </div>
      </section>

      <ConfirmModal open={reject} title={`Tolak ${stl.number}`} message="Berikan alasan penolakan LPJ."
        confirmLabel="Tolak LPJ" danger withReason reasonLabel="Alasan" reasonPlaceholder="mis. Bukti tidak lengkap"
        onConfirm={async (reason) => { setReject(false); await act("reject", { note: reason }, `${stl.number} ditolak.`); }}
        onCancel={() => setReject(false)} testId="stl-reject-modal" />
    </div>
  );
}

function Metric({ label, value, tone, testId, money }) {
  return (<div data-testid={testId} className="metric-card"><div className="metric-icon" style={{ background: tone }}><ReceiptText size={16} className="text-[#1C1C1E]" /></div><div className="min-w-0"><p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p><p className={`${money ? "text-[15px]" : "text-[17px]"} font-bold tabular-nums truncate`}>{value}</p></div></div>);
}
function Meta({ k, v, danger }) {
  return (<div className="flex gap-2"><span className="text-[#8E8E93] w-24 shrink-0">{k}</span><span className={`font-semibold min-w-0 break-words ${danger ? "text-red-600" : ""}`}>{v}</span></div>);
}
function RowLine({ k, v, strong, tone, testId }) {
  return (<div className="flex justify-between text-[12px]"><span className="text-[#3C3C43]">{k}</span><span data-testid={testId} className={`tabular-nums ${strong ? "font-bold" : "font-semibold"}`} style={tone ? { color: tone } : {}}>{v}</span></div>);
}
