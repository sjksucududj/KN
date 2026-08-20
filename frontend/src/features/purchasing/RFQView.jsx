import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ClipboardList, Plus, Layers } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import RFQCreateModal from "./RFQCreateModal";
import RFQDetailPanel from "./RFQDetailPanel";
import DetailModal from "../../components/DetailModal";

/**
 * RFQView (Fase 6.1 — P1 Sourcing) — RFQ / Quotation.
 * Tender multi-supplier: create (PR/manual) → quote → compare → award → PO.
 */
const TABS = [
  { key: "all", label: "Semua" },
  { key: "draft", label: "Draf" },
  { key: "open", label: "Berjalan" },
  { key: "awarded", label: "Awarded" },
  { key: "cancelled", label: "Batal" },
];
const fmtDate = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");

function StatusPill({ status }) {
  const map = {
    draft: ["pill-muted", "Draft"], open: ["pill-info", "Berjalan"],
    awarded: ["pill-success", "Awarded"], cancelled: ["pill-muted", "Batal"],
  };
  const [cls, label] = map[status] || ["pill-muted", status];
  return <span className={`status-pill ${cls}`}>{label}</span>;
}

export default function RFQView({ currentUser, selectedEntity }) {
  const [rfqs, setRfqs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("all");
  const [showCreate, setShowCreate] = useState(false);
  const [detailId, setDetailId] = useState(null);

  const canCreate = ["admin", "manager", "warehouse"].includes(currentUser?.role);

  useEffect(() => { load(); }, [selectedEntity]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const params = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const r = await axios.get(`${API}/rfqs`, { params });
      setRfqs(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat RFQ.");
    } finally { setLoading(false); }
  }

  function onCreated(rfq) {
    setShowCreate(false);
    setNotice(`RFQ ${rfq.rfq_number} dibuat.`);
    load();
    setDetailId(rfq.id);
  }

  const filtered = useMemo(() => rfqs.filter((r) => tab === "all" || r.status === tab), [rfqs, tab]);
  const counts = useMemo(() => TABS.reduce((a, t) => ({
    ...a, [t.key]: t.key === "all" ? rfqs.length : rfqs.filter((r) => r.status === t.key).length,
  }), {}), [rfqs]);

  return (
    <div data-testid="rfq-view">
      {notice && <div className="notice-bar success" data-testid="rfq-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="rfq-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <ClipboardList size={16} className="text-[#0058CC]" />
            <h2 data-testid="rfq-title">RFQ / Penawaran — Tender Pengadaan</h2>
          </div>
          {canCreate && (
            <button data-testid="rfq-create-button" onClick={() => setShowCreate(true)} className="primary-button">
              <Plus size={13} /> Buat RFQ
            </button>
          )}
        </div>
        <div className="section-body">
          <div className="tab-bar">
            {TABS.map((t) => (
              <button key={t.key} data-testid={`rfq-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                {t.label}<span className="tab-badge">{counts[t.key]}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-hidden">
          <div className="grid grid-cols-[110px_1.5fr_90px_110px_130px_100px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Judul / Sumber</span><span className="text-center">Item</span><span className="text-center">Supplier</span><span>Status</span><span className="text-right">Dibuat</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat RFQ...</div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="rfq-empty">
              <Layers className="mx-auto mb-2 text-gray-300" size={28} />
              <p>Belum ada RFQ{tab !== "all" ? ` (${tab})` : ""}.</p>
              {canCreate && tab === "all" && <p className="mt-1 text-[11px]">Buat RFQ dari PR disetujui atau manual untuk membandingkan harga supplier.</p>}
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
              {filtered.map((r) => {
                const quoted = (r.suppliers || []).filter((s) => s.quote_status === "quoted").length;
                return (
                  <button key={r.id} data-testid={`rfq-row-${r.id}`} onClick={() => setDetailId(r.id)}
                          className="w-full text-left grid grid-cols-[110px_1.5fr_90px_110px_130px_100px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                    <span className="text-[11.5px] font-bold text-[#0058CC]">{r.rfq_number}</span>
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold truncate">{r.title}</p>
                      <p className="text-[10.5px] text-[#6B6B73] truncate">{r.source === "pr" ? `Dari ${r.pr_number}` : "Manual"} · {r.warehouse_name}</p>
                    </div>
                    <span className="text-[12px] text-center tabular-nums">{(r.items || []).length}</span>
                    <span className="text-[12px] text-center tabular-nums">{quoted}/{(r.suppliers || []).length}</span>
                    <div><StatusPill status={r.status} />{r.status === "awarded" && <p className="text-[10px] text-[#6B6B73] mt-0.5 truncate">{(r.award?.po_numbers || []).join(", ")}</p>}</div>
                    <span className="text-[11px] text-right text-[#6B6B73]">{fmtDate(r.created_at)}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <RFQCreateModal open={showCreate} selectedEntity={selectedEntity}
        onClose={() => setShowCreate(false)} onCreated={onCreated} onError={(m) => setError(m)} />

      {detailId && (
        <DetailModal onClose={() => setDetailId(null)}
          label="Rincian permintaan penawaran" testId="rfq-detail-modal">
          <RFQDetailPanel rfqId={detailId} currentUser={currentUser}
            onClose={() => setDetailId(null)}
            onChanged={(msg) => { if (msg) setNotice(msg); load(); }} />
        </DetailModal>
      )}
    </div>
  );
}
