import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { FileStack, Plus, Layers } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import BlanketPOCreateModal from "./BlanketPOCreateModal";
import BlanketPODetailPanel from "./BlanketPODetailPanel";

/**
 * BlanketPOView (P2 — Blanket / Contract PO + call-off).
 *
 * Aturan owner: 1.c qty per item + plafon nilai · 2.a call-off = PO anak normal ·
 * 3.b harga call-off boleh override (alasan wajib) · 4.b over-call wajib approval ·
 * 5.a kontrak kadaluarsa/habis/ditutup → call-off baru ditolak.
 *
 * List kontrak (GET /purchase-orders/blanket) → detail drawdown + call-off.
 */
const TABS = [
  { key: "all", label: "Semua" },
  { key: "active", label: "Aktif" },
  { key: "exhausted", label: "Habis" },
  { key: "expired", label: "Kadaluarsa" },
  { key: "closed", label: "Ditutup" },
];

const fmtDate = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");

export function ContractStatusPill({ status }) {
  const map = {
    active: ["pill-success", "Aktif"],
    exhausted: ["pill-info", "Habis"],
    expired: ["pill-warning", "Kadaluarsa"],
    closed: ["pill-muted", "Ditutup"],
  };
  const [cls, label] = map[status] || ["pill-muted", status || "—"];
  return <span className={`status-pill ${cls}`} data-testid={`blanket-status-${status}`}>{label}</span>;
}

export default function BlanketPOView({ currentUser, selectedEntity }) {
  const [blankets, setBlankets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("all");
  const [showCreate, setShowCreate] = useState(false);
  const [detailId, setDetailId] = useState(null);

  const canCreate = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => { load(); }, [selectedEntity]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const params = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const r = await axios.get(`${API}/purchase-orders/blanket`, { params });
      setBlankets(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat kontrak Blanket PO.");
    } finally { setLoading(false); }
  }

  function onCreated(blanket) {
    setShowCreate(false);
    setNotice(`Kontrak ${blanket.po_number} dibuat.`);
    load();
    setDetailId(blanket.id);
  }

  const filtered = useMemo(
    () => blankets.filter((b) => tab === "all" || (b.contract_status || "active") === tab),
    [blankets, tab]);
  const counts = useMemo(() => TABS.reduce((a, t) => ({
    ...a,
    [t.key]: t.key === "all" ? blankets.length : blankets.filter((b) => (b.contract_status || "active") === t.key).length,
  }), {}), [blankets]);

  return (
    <div data-testid="blanket-po-view">
      {notice && (
        <div className="notice-bar success" data-testid="blanket-notice">
          <span>{notice}</span><button onClick={() => setNotice("")}>×</button>
        </div>
      )}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="blanket-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <FileStack size={16} className="text-[#0058CC]" />
            <div className="min-w-0">
              <span className="kicker">Pembelian</span>
              <h2 data-testid="blanket-title">Blanket / Contract PO — Call-off</h2>
            </div>
          </div>
          {canCreate && (
            <button data-testid="blanket-create-button" onClick={() => setShowCreate(true)} className="primary-button">
              <Plus size={13} /> Buat Kontrak
            </button>
          )}
        </div>
        <div className="section-body">
          <p className="text-[11.5px] text-[#6B6B73] mb-2">
            Kontrak harga sepakat dengan supplier (komitmen kuantitas per item + plafon nilai). Penarikan bertahap (call-off) memicu PO anak yang melewati approval & penerimaan normal.
          </p>
          <div className="tab-bar">
            {TABS.map((t) => (
              <button key={t.key} data-testid={`blanket-tab-${t.key}`}
                className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                {t.label}<span className="tab-badge">{counts[t.key] ?? 0}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_400px]">
        <div className="section-card">
          <div className="overflow-hidden">
            <div className="grid grid-cols-[100px_1.4fr_60px_1fr_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Nomor</span><span>Supplier</span><span className="text-center">Item</span><span>Terpakai / Plafon</span><span>Status</span>
            </div>
            {loading ? (
              <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="blanket-loading">Memuat kontrak...</div>
            ) : filtered.length === 0 ? (
              <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="blanket-empty">
                <Layers className="mx-auto mb-2 text-gray-300" size={28} />
                <p>Belum ada kontrak Blanket PO{tab !== "all" ? ` (${tab})` : ""}.</p>
                {canCreate && tab === "all" && (
                  <p className="mt-1 text-[11px]">Buat kontrak untuk mengunci harga & komitmen kuantitas dengan supplier.</p>
                )}
              </div>
            ) : (
              <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
                {filtered.map((b) => {
                  const cap = Number(b.contract_value_cap || 0);
                  const called = Number(b.value_called || 0);
                  const pct = cap > 0 ? Math.min(100, Math.round((called / cap) * 100)) : 0;
                  return (
                    <button key={b.id} data-testid={`blanket-row-${b.id}`} onClick={() => setDetailId(b.id)}
                      className={`w-full text-left grid grid-cols-[100px_1.4fr_60px_1fr_120px] items-center px-3 py-2.5 hover:bg-[#FAFBFC] transition-colors ${detailId === b.id ? "bg-[#EFF4FF]" : ""}`}>
                      <span className="text-[11.5px] font-bold text-[#0058CC]">{b.po_number}</span>
                      <div className="min-w-0">
                        <p className="text-[12px] font-semibold truncate">{b.supplier_name}</p>
                        <p className="text-[10.5px] text-[#6B6B73] truncate">{b.warehouse_name} · {b.call_off_count || 0} call-off</p>
                      </div>
                      <span className="text-[12px] text-center tabular-nums">{(b.contract_items || []).length}</span>
                      <div className="pr-2">
                        <div className="flex items-center gap-1.5">
                          <div className="flex-1 h-1.5 rounded-full bg-[#EFF0F2] overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${pct}%`, background: pct >= 100 ? "#B45309" : "#0058CC" }} />
                          </div>
                          <span className="text-[10px] tabular-nums text-[#6B6B73] whitespace-nowrap">{pct}%</span>
                        </div>
                        <p className="text-[10.5px] text-[#6B6B73] tabular-nums mt-0.5">{formatCurrency(called)} / {formatCurrency(cap)}</p>
                      </div>
                      <div><ContractStatusPill status={b.contract_status || "active"} />
                        {b.valid_until && <p className="text-[10px] text-[#6B6B73] mt-0.5">s/d {fmtDate(b.valid_until)}</p>}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <BlanketPODetailPanel
          blanketId={detailId}
          currentUser={currentUser}
          onClose={() => setDetailId(null)}
          onChanged={(msg) => { if (msg) setNotice(msg); load(); }}
          onError={(m) => setError(m)}
        />
      </div>

      <BlanketPOCreateModal open={showCreate} selectedEntity={selectedEntity}
        onClose={() => setShowCreate(false)} onCreated={onCreated} onError={(m) => setError(m)} />
    </div>
  );
}
