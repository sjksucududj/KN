import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ShieldCheck, Check, XCircle } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import { fmtDate } from "./crmUtils";

/** Persetujuan override kredit (KN_17 §5.2 / S37) — Manager/Finance. */
export default function CreditOverridesPanel({ currentUser }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("pending");
  const [confirm, setConfirm] = useState(null); // {row, decision}

  useEffect(() => { load(); }, [tab]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const params = tab !== "all" ? { status: tab } : {};
      const r = await axios.get(`${API}/credit-overrides`, { params });
      setRows(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat permohonan override.");
    } finally { setLoading(false); }
  }

  async function decide(row, decision, reason) {
    try {
      await axios.post(`${API}/credit-overrides/${row.id}/decision`, { decision, reason });
      setConfirm(null);
      setNotice(`Permohonan ${row.customer_name} ${decision === "approve" ? "disetujui" : "ditolak"}.`);
      load();
    } catch (e) {
      setConfirm(null);
      setError(e.response?.data?.detail || "Gagal memproses keputusan.");
    }
  }

  const TABS = [
    { key: "pending", label: "Menunggu" },
    { key: "approved", label: "Disetujui" },
    { key: "rejected", label: "Ditolak" },
    { key: "all", label: "Semua" },
  ];

  return (
    <div data-testid="credit-overrides-panel">
      {notice && <div className="notice-bar success" data-testid="override-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="override-list-error" />

      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2"><ShieldCheck size={16} className="text-[#0058CC]" /><h2 data-testid="overrides-title">Persetujuan Override Kredit</h2></div>
        </div>
        <div className="section-body">
          <div className="tab-bar mb-3">
            {TABS.map((t) => (
              <button key={t.key} data-testid={`override-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>{t.label}</button>
            ))}
          </div>
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1.3fr_110px_1fr_120px_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Pelanggan / Alasan</span><span>Nilai</span><span>Pemohon</span><span>Status</span><span>Aksi</span>
            </div>
            {loading ? (
              <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="overrides-loading">Memuat...</div>
            ) : rows.length === 0 ? (
              <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="overrides-empty">Tidak ada permohonan {tab !== "all" ? `(${tab})` : ""}.</div>
            ) : (
              <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
                {rows.map((r) => (
                  <div key={r.id} data-testid={`override-row-${r.id}`} className="grid grid-cols-[1.3fr_110px_1fr_120px_120px] items-center px-3 py-2.5 text-[11.5px]">
                    <div className="min-w-0"><p className="font-semibold truncate">{r.customer_name}</p><p className="text-[10.5px] text-[#6B6B73] truncate">{r.reason}</p></div>
                    <span className="tabular-nums font-semibold">{formatCurrency(r.amount)}</span>
                    <span className="truncate text-[#3C3C43]">{r.requested_by}<br /><span className="text-[10px] text-[#9A9BA3]">{fmtDate(r.created_at)}</span></span>
                    <span><span className={`status-pill ${r.status === "approved" ? "pill-success" : r.status === "rejected" ? "pill-danger" : "pill-warning"}`}>{r.status}</span></span>
                    <div className="flex gap-1">
                      {r.status === "pending" ? (
                        <>
                          <button data-testid={`override-approve-${r.id}`} onClick={() => setConfirm({ row: r, decision: "approve" })} className="icon-button text-[#1E8E5A]" title="Setujui"><Check size={15} /></button>
                          <button data-testid={`override-reject-${r.id}`} onClick={() => setConfirm({ row: r, decision: "reject" })} className="icon-button text-[#C0392B]" title="Tolak"><XCircle size={15} /></button>
                        </>
                      ) : <span className="text-[10px] text-[#9A9BA3]">{r.decided_by || "—"}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <ConfirmModal
        open={!!confirm}
        title={confirm?.decision === "approve" ? "Setujui Override Kredit" : "Tolak Override Kredit"}
        message={confirm ? `${confirm.decision === "approve" ? "Setujui" : "Tolak"} permohonan ${confirm.row.customer_name} (${formatCurrency(confirm.row.amount)})?` : ""}
        confirmLabel={confirm?.decision === "approve" ? "Setujui" : "Tolak"}
        danger={confirm?.decision === "reject"}
        withReason
        reasonLabel="Catatan keputusan"
        onConfirm={(reason) => decide(confirm.row, confirm.decision, reason)}
        onCancel={() => setConfirm(null)}
        testId="override-decision-confirm"
      />
    </div>
  );
}
