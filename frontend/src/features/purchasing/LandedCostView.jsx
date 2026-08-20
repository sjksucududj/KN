import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Ship, Plus, Send, Wallet, Layers } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import LandedCostCreateModal from "./LandedCostCreateModal";
import LandedCostDetailPanel from "./LandedCostDetailPanel";
import DetailModal from "../../components/DetailModal";

/**
 * LandedCostView (Fase 5.4 — P0-5) — Landed Cost Voucher → alokasi HPP roll.
 * Biaya tambahan (freight/bea/asuransi/handling) dialokasikan ke unit_cost roll
 * saat APPROVE (manager+, SoD, idempotent).
 */
const TABS = [
  { key: "all", label: "Semua" },
  { key: "draft", label: "Draf" },
  { key: "pending_approval", label: "Menunggu" },
  { key: "applied", label: "Diterapkan" },
  { key: "paid", label: "Lunas" },
  { key: "cancelled", label: "Batal" },
];

function StatusPill({ status }) {
  const map = {
    draft: ["pill-muted", "Draft"], pending_approval: ["pill-warning", "Menunggu"],
    applied: ["pill-info", "Diterapkan"], paid: ["pill-success", "Lunas"], cancelled: ["pill-danger", "Batal"],
  };
  const [cls, label] = map[status] || ["pill-muted", status];
  return <span className={`status-pill ${cls}`}>{label}</span>;
}

export default function LandedCostView({ currentUser, selectedEntity }) {
  const [vouchers, setVouchers] = useState([]);
  const [pos, setPos] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("all");
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);

  const canApprove = ["admin", "manager"].includes(currentUser?.role);
  const canCreate = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => { loadAll(); }, [selectedEntity]); // eslint-disable-line

  async function loadAll() {
    setLoading(true);
    try {
      const params = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const [vRes, poRes, sRes] = await Promise.all([
        axios.get(`${API}/landed-costs`, { params }),
        axios.get(`${API}/purchase-orders`, { params }).catch(() => ({ data: [] })),
        axios.get(`${API}/landed-costs/payables/summary`, { params }).catch(() => ({ data: null })),
      ]);
      setVouchers(Array.isArray(vRes.data) ? vRes.data : []);
      const received = (Array.isArray(poRes.data) ? poRes.data : []).filter(
        (p) => !["waiting_approval", "rejected", "cancelled", "draft"].includes(p.status));
      setPos(received);
      setSummary(sRes.data);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data landed cost.");
    } finally { setLoading(false); }
  }

  function onCreated(v) {
    setShowCreate(false);
    const msg = v.status === "pending_approval" ? "menunggu approval manager" : "disimpan sebagai draft";
    setNotice(`Landed Cost ${v.voucher_number} dibuat — ${msg}.`);
    loadAll();
  }

  async function onAction(action, data) {
    const labels = { submit: "disubmit", approve: "disetujui & HPP dialokasikan", reject: "ditolak", cancel: "dibatalkan", pay: "pembayaran dicatat" };
    setNotice(`${data.voucher_number}: ${labels[action] || action}.`);
    setDetail(data);
    await loadAll();
  }

  async function quickAct(v, action) {
    try {
      const urls = {
        submit: `${API}/landed-costs/${v.id}/submit`,
        approve: `${API}/landed-costs/${v.id}/approve`,
      };
      const r = await axios.post(urls[action], {});
      const labels = { submit: "disubmit", approve: "disetujui & HPP dialokasikan" };
      setNotice(`${r.data.voucher_number}: ${labels[action] || action}.`);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || `Gagal ${action}.`);
    }
  }

  const filtered = useMemo(() => vouchers.filter((v) => tab === "all" || v.status === tab), [vouchers, tab]);
  const counts = useMemo(() => TABS.reduce((acc, t) => ({
    ...acc, [t.key]: t.key === "all" ? vouchers.length : vouchers.filter((v) => v.status === t.key).length,
  }), {}), [vouchers]);

  return (
    <div data-testid="landed-cost-view">
      {notice && <div className="notice-bar success" data-testid="lc-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="lc-error" />

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-3" data-testid="lc-summary">
          <SummaryCard label="Total Landed Cost (applied)" value={formatCurrency(summary.total_applied)} big testId="lc-summary-applied" />
          <SummaryCard label="Sisa Hutang Biaya" value={formatCurrency(summary.total_outstanding)} tone="text-red-600" big testId="lc-summary-outstanding" />
          <SummaryCard label="Penyedia Berhutang" value={String((summary.by_provider || []).length)} />
          <SummaryCard label="Voucher Aktif" value={String((summary.vouchers || []).length)} />
        </div>
      )}

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Ship size={16} className="text-[#0058CC]" />
            <h2 data-testid="landed-cost-title">Landed Cost (Alokasi HPP Roll)</h2>
          </div>
          {canCreate && (
            <button data-testid="create-landed-cost-button" onClick={() => setShowCreate(true)} className="primary-button">
              <Plus size={13} /> Buat Landed Cost
            </button>
          )}
        </div>
        <div className="section-body">
          <div className="tab-bar">
            {TABS.map((t) => (
              <button key={t.key} data-testid={`lc-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                {t.label}<span className="tab-badge">{counts[t.key]}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="overflow-hidden">
          <div className="grid grid-cols-[120px_1.5fr_130px_120px_90px_90px_70px_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Penyedia / PO</span><span className="text-right">Total Biaya</span><span className="text-right">Sisa</span>
            <span>Basis</span><span>Status</span><span className="text-right">Roll</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat landed cost...</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]">
              <Layers className="mx-auto mb-2 text-gray-300" size={28} />
              <p>Belum ada voucher landed cost{tab !== "all" ? ` (${tab})` : ""}.</p>
              {canCreate && tab === "all" && <p className="mt-1 text-[11px]">Buat dari PO yang sudah diterima untuk membebankan biaya angkut/bea ke HPP roll.</p>}
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
              {filtered.map((v) => (
                <div key={v.id} data-testid={`lc-row-${v.id}`} onClick={() => setDetail(v)}
                     className="grid grid-cols-[120px_1.5fr_130px_120px_90px_90px_70px_120px] items-center px-3 py-2.5 hover:bg-[#FAFBFC] cursor-pointer">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{v.voucher_number}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{v.provider_name || "—"}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate">{(v.po_numbers || []).join(", ") || "—"} · {(v.cost_lines || []).length} biaya</p>
                  </div>
                  <span className="text-[12px] font-bold tabular-nums text-right">{formatCurrency(v.total_cost)}</span>
                  <span className="text-[12px] tabular-nums text-right text-red-600">{formatCurrency(v.financials?.outstanding ?? 0)}</span>
                  <span className="text-[10.5px] text-[#6B6B73] capitalize">{v.effective_basis || v.basis}</span>
                  <StatusPill status={v.status} />
                  <span className="text-[11px] tabular-nums text-right">{v.target_roll_count || 0}</span>
                  <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                    {v.status === "draft" && (
                      <button data-testid={`lc-quick-submit-${v.id}`} onClick={() => quickAct(v, "submit")} className="secondary-button !px-2 !py-1 text-[11px]"><Send size={11} /> Kirim</button>
                    )}
                    {v.status === "pending_approval" && canApprove && (
                      <button data-testid={`lc-quick-approve-${v.id}`} onClick={() => quickAct(v, "approve")} className="primary-button !px-2 !py-1 text-[11px]">Setujui</button>
                    )}
                    {v.status === "applied" && (
                      <button data-testid={`lc-quick-pay-${v.id}`} onClick={() => setDetail(v)} className="primary-button !px-2 !py-1 text-[11px]"><Wallet size={11} /> Bayar</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <LandedCostCreateModal
        open={showCreate}
        pos={pos}
        selectedEntity={selectedEntity}
        onClose={() => setShowCreate(false)}
        onCreated={onCreated}
        onError={(m) => setError(m)}
      />

      {detail && (
        <DetailModal onClose={() => setDetail(null)}
          label="Rincian biaya masuk (landed cost)" testId="lc-detail-modal">
          <LandedCostDetailPanel
            voucher={detail}
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
