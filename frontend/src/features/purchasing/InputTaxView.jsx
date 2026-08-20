import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { can } from "../../config/roles";
import { Percent, Plus, Ban, FileText, Layers } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import InputTaxCreateModal from "./InputTaxCreateModal";

/**
 * InputTaxView (Fase 5.5 — P0-3) — Faktur Pajak Masukan (Input VAT).
 * Catat Faktur Pajak Masukan dari Vendor Bill ber-PPN (NSFP + dedupe) lalu
 * Rekap PPN Masukan vs Keluaran per periode (posisi kurang/lebih bayar).
 */
const STATUS_TABS = [
  { key: "all", label: "Semua" },
  { key: "recorded", label: "Tercatat" },
  { key: "cancelled", label: "Batal" },
];

function currentPeriod() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
const fmtDate = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");

function StatusPill({ status }) {
  const map = { recorded: ["pill-success", "Tercatat"], cancelled: ["pill-muted", "Batal"] };
  const [cls, label] = map[status] || ["pill-muted", status];
  return <span className={`status-pill ${cls}`}>{label}</span>;
}

export default function InputTaxView({ currentUser, selectedEntity }) {
  const [vouchers, setVouchers] = useState([]);
  const [bills, setBills] = useState([]);
  const [summary, setSummary] = useState(null);
  const [period, setPeriod] = useState(currentPeriod());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("all");
  const [view, setView] = useState("list"); // list | rekap
  const [showCreate, setShowCreate] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelReason, setCancelReason] = useState("");
  const [busy, setBusy] = useState(false);

  // FASE E-8 — pajak MASUKAN ada di sisi HUTANG: tetap manajer/admin (keputusan
  // pemilik: jangan diperluas ke Finance sendiri), tapi diputuskan oleh IZIN.
  const canCreate = can(currentUser?.permissions || {}, "input_tax", "create");

  useEffect(() => { loadAll(); }, [selectedEntity]); // eslint-disable-line
  useEffect(() => { loadSummary(); }, [period, selectedEntity]); // eslint-disable-line

  function entParams() {
    return (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
  }

  async function loadAll() {
    setLoading(true);
    try {
      const [vRes, bRes] = await Promise.all([
        axios.get(`${API}/input-tax-invoices`, { params: entParams() }),
        axios.get(`${API}/input-tax-invoices/eligible-bills`, { params: entParams() }).catch(() => ({ data: [] })),
      ]);
      setVouchers(Array.isArray(vRes.data) ? vRes.data : []);
      setBills(Array.isArray(bRes.data) ? bRes.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Faktur Pajak Masukan.");
    } finally { setLoading(false); }
  }

  async function loadSummary() {
    try {
      const params = { period, ...entParams() };
      const r = await axios.get(`${API}/tax/vat-summary`, { params });
      setSummary(r.data);
    } catch { setSummary(null); }
  }

  function onCreated(v) {
    setShowCreate(false);
    setNotice(`Faktur Masukan ${v.number} dicatat (NSFP ${v.nsfp}).`);
    loadAll(); loadSummary();
  }

  async function doCancel() {
    if (!cancelTarget || !cancelReason.trim()) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/input-tax-invoices/${cancelTarget.id}/cancel`, { reason: cancelReason.trim() });
      setNotice(`${r.data.number}: faktur masukan dibatalkan.`);
      setCancelTarget(null); setCancelReason("");
      loadAll(); loadSummary();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal membatalkan.");
    } finally { setBusy(false); }
  }

  const filtered = useMemo(
    () => vouchers.filter((v) => tab === "all" || v.status === tab),
    [vouchers, tab]);
  const counts = useMemo(() => STATUS_TABS.reduce((acc, t) => ({
    ...acc, [t.key]: t.key === "all" ? vouchers.length : vouchers.filter((v) => v.status === t.key).length,
  }), {}), [vouchers]);

  const netTone = summary?.position === "kurang_bayar" ? "text-red-600"
    : summary?.position === "lebih_bayar" ? "text-emerald-600" : "text-[#0F1115]";

  return (
    <div data-testid="input-tax-view">
      {notice && <div className="notice-bar success" data-testid="it-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="it-error" />

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-3" data-testid="it-summary">
          <SummaryCard label={`PPN Masukan (${summary.period})`} value={formatCurrency(summary.masukan?.ppn)} big testId="it-summary-masukan" />
          <SummaryCard label={`PPN Keluaran (${summary.period})`} value={formatCurrency(summary.keluaran?.ppn)} big testId="it-summary-keluaran" />
          <SummaryCard label="Posisi PPN (Net)" value={formatCurrency(Math.abs(summary.net_ppn || 0))} tone={netTone} big testId="it-summary-net" />
          <SummaryCard label="Status Periode" value={summary.position === "kurang_bayar" ? "Kurang Bayar" : summary.position === "lebih_bayar" ? "Lebih Bayar" : "Nihil"} testId="it-summary-position" />
        </div>
      )}

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Percent size={16} className="text-[#0058CC]" />
            <h2 data-testid="input-tax-title">Faktur Pajak Masukan (Input VAT)</h2>
          </div>
          <div className="flex items-center gap-2">
            <div className="tab-bar !mb-0">
              <button data-testid="it-view-list" className={`tab-button ${view === "list" ? "active" : ""}`} onClick={() => setView("list")}>Faktur Masukan</button>
              <button data-testid="it-view-rekap" className={`tab-button ${view === "rekap" ? "active" : ""}`} onClick={() => setView("rekap")}>Rekap PPN</button>
            </div>
            {canCreate && view === "list" && (
              <button data-testid="it-create-button" onClick={() => setShowCreate(true)} className="primary-button">
                <Plus size={13} /> Catat Faktur Masukan
              </button>
            )}
          </div>
        </div>
      </div>

      {view === "list" ? (
        <div className="section-card">
          <div className="section-body">
            <div className="tab-bar">
              {STATUS_TABS.map((t) => (
                <button key={t.key} data-testid={`it-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                  {t.label}<span className="tab-badge">{counts[t.key]}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="overflow-hidden">
            <div className="grid grid-cols-[110px_1.4fr_140px_120px_110px_90px_90px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Nomor</span><span>NSFP / Supplier</span><span>Tagihan / PO</span><span className="text-right">DPP</span><span className="text-right">PPN</span><span>Periode</span><span className="text-right">Aksi</span>
            </div>
            {loading ? (
              <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat faktur masukan...</div>
            ) : filtered.length === 0 ? (
              <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="it-empty">
                <Layers className="mx-auto mb-2 text-gray-300" size={28} />
                <p>Belum ada Faktur Pajak Masukan{tab !== "all" ? ` (${tab})` : ""}.</p>
                {canCreate && tab === "all" && <p className="mt-1 text-[11px]">Catat dari Tagihan Supplier (Vendor Bill) ber-PPN untuk mengkreditkan PPN Masukan.</p>}
              </div>
            ) : (
              <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
                {filtered.map((v) => (
                  <div key={v.id} data-testid={`it-row-${v.id}`}
                       className="grid grid-cols-[110px_1.4fr_140px_120px_110px_90px_90px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                    <span className="text-[11.5px] font-bold text-[#0058CC]">{v.number}</span>
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold tabular-nums truncate" data-testid={`it-nsfp-${v.id}`}>{v.nsfp_display || v.nsfp}</p>
                      <p className="text-[10.5px] text-[#6B6B73] truncate">{v.supplier_name || "—"}</p>
                    </div>
                    <div className="min-w-0">
                      <p className="text-[11px] truncate">{v.bill_number || "—"}</p>
                      <p className="text-[10.5px] text-[#6B6B73] truncate">{v.po_number || "—"}</p>
                    </div>
                    <span className="text-[12px] tabular-nums text-right">{formatCurrency(v.dpp)}</span>
                    <span className="text-[12px] font-bold tabular-nums text-right">{formatCurrency(v.ppn_amount)}</span>
                    <div><StatusPill status={v.status} /><p className="text-[10px] text-[#9A9BA3] mt-0.5">{v.period}</p></div>
                    <div className="flex items-center justify-end">
                      {v.status === "recorded" && canCreate && (
                        <button data-testid={`it-cancel-${v.id}`} onClick={() => { setCancelTarget(v); setCancelReason(""); }}
                                className="secondary-button !px-2 !py-1 text-[11px]"><Ban size={11} /> Batal</button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <RekapPanel period={period} setPeriod={setPeriod} summary={summary} netTone={netTone} loading={!summary} />
      )}

      <InputTaxCreateModal
        open={showCreate}
        bills={bills}
        onClose={() => setShowCreate(false)}
        onCreated={onCreated}
        onError={(m) => setError(m)}
      />

      {cancelTarget && (
        <div className="modal-overlay" data-testid="it-cancel-modal" onClick={(e) => { if (e.target === e.currentTarget) setCancelTarget(null); }}>
          <div className="modal-card" style={{ maxWidth: 440, width: "92vw" }}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2]">
              <h2 className="text-[14px] font-bold">Batalkan Faktur Masukan {cancelTarget.number}</h2>
            </div>
            <div className="p-4 space-y-3">
              <p className="text-[12px] text-[#6B6B73]">NSFP {cancelTarget.nsfp} akan dilepas & bisa dipakai ulang. Vendor Bill kembali dapat dicatat.</p>
              <textarea data-testid="it-cancel-reason" value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
                className="field" rows={3} placeholder="Alasan pembatalan (wajib)" />
              <div className="flex items-center justify-end gap-2">
                <button onClick={() => setCancelTarget(null)} className="secondary-button">Batal</button>
                <button data-testid="it-cancel-confirm" disabled={busy || !cancelReason.trim()} onClick={doCancel}
                        className="primary-button">{busy ? "Memproses..." : "Konfirmasi Pembatalan"}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RekapPanel({ period, setPeriod, summary, netTone, loading }) {
  return (
    <div className="section-card" data-testid="it-rekap-panel">
      <div className="section-head">
        <div className="flex items-center gap-2"><FileText size={15} className="text-[#0058CC]" /><h2>Rekap PPN — Masukan vs Keluaran</h2></div>
        <input type="month" data-testid="it-period-input" value={period} onChange={(e) => setPeriod(e.target.value || period)}
               className="field !w-[160px]" />
      </div>
      <div className="section-body">
        {loading || !summary ? (
          <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat rekap PPN...</div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
              <RekapCard title="PPN Keluaran (Jual)" ppn={summary.keluaran?.ppn} dpp={summary.keluaran?.dpp} count={summary.keluaran?.count} testId="it-rekap-keluaran" />
              <RekapCard title="PPN Masukan (Beli)" ppn={summary.masukan?.ppn} dpp={summary.masukan?.dpp} count={summary.masukan?.count} testId="it-rekap-masukan" />
              <div className="section-card !p-4 border-2" data-testid="it-rekap-net">
                <p className="text-[10px] font-bold uppercase text-[#6B6B73]">Posisi PPN (Keluaran − Masukan)</p>
                <p className={`text-[22px] font-bold tabular-nums ${netTone}`}>{formatCurrency(Math.abs(summary.net_ppn || 0))}</p>
                <p className={`text-[12px] font-semibold ${netTone}`}>{summary.position_label}</p>
              </div>
            </div>
            <div className="overflow-hidden border border-[#EFF0F2] rounded-md">
              <div className="grid grid-cols-[1.5fr_100px_140px_140px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
                <span>Supplier (Masukan)</span><span className="text-right">Faktur</span><span className="text-right">DPP</span><span className="text-right">PPN</span>
              </div>
              {(summary.masukan_by_supplier || []).length === 0 ? (
                <div className="py-8 text-center text-[12px] text-[#6B6B73]">Tidak ada PPN Masukan pada periode ini.</div>
              ) : (
                summary.masukan_by_supplier.map((s, i) => (
                  <div key={i} data-testid={`it-rekap-supplier-${i}`} className="grid grid-cols-[1.5fr_100px_140px_140px] items-center px-3 py-2 text-[12px] border-b border-[#F4F5F6] last:border-0">
                    <span className="font-semibold truncate">{s.supplier_name}</span>
                    <span className="text-right tabular-nums">{s.count}</span>
                    <span className="text-right tabular-nums">{formatCurrency(s.dpp)}</span>
                    <span className="text-right tabular-nums font-bold">{formatCurrency(s.ppn)}</span>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function RekapCard({ title, ppn, dpp, count, testId }) {
  return (
    <div className="section-card !p-4" data-testid={testId}>
      <p className="text-[10px] font-bold uppercase text-[#6B6B73]">{title}</p>
      <p className="text-[20px] font-bold tabular-nums text-[#0F1115]">{formatCurrency(ppn)}</p>
      <p className="text-[11px] text-[#6B6B73] tabular-nums">DPP {formatCurrency(dpp)} · {count || 0} faktur</p>
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
