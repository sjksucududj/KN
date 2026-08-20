/**
 * MakloonOrdersView (M3) — daftar & lifecycle transaksi makloon/subkontrak.
 * GET /makloon-orders · buka detail (issue/receive/cancel) · buat order baru.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Boxes, Plus, Search, ArrowRight, Factory } from "lucide-react";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import LineFilter from "../../components/LineFilter";   // FASE L
import { formatQty } from "../../utils/formatters";
import MakloonWizard from "./makloon/MakloonWizard";
import MakloonOrderDetailPanel from "./MakloonOrderDetailPanel";

export const MKO_STATUS = {
  draft: { label: "Draf", cls: "pill-muted" },
  in_process: { label: "Diproses", cls: "pill-info" },
  partially_received: { label: "Sebagian", cls: "pill-warning" },
  completed: { label: "Selesai", cls: "pill-success" },
  cancelled: { label: "Batal", cls: "pill-danger" },
};
const MODE_LABEL = { process_only: "Proses Saja", buy_process: "Beli + Proses" };
const FILTERS = [
  { key: "", label: "Semua" }, { key: "draft", label: "Draf" },
  { key: "in_process", label: "Diproses" }, { key: "partially_received", label: "Sebagian" },
  { key: "completed", label: "Selesai" }, { key: "cancelled", label: "Batal" },
];

export default function MakloonOrdersView({ currentUser, selectedEntity }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [lineFilter, setLineFilter] = useState("");   // FASE L
  const [showCreate, setShowCreate] = useState(false);
  const [detailId, setDetailId] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      if (statusFilter) params.status = statusFilter;
      if (lineFilter) params.line = lineFilter;          // FASE L
      const res = await axios.get(`${API}/makloon-orders`, { params });
      setRows(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat order makloon."); }
    finally { setLoading(false); }
  }, [selectedEntity, statusFilter, lineFilter]);
  useEffect(() => { loadAll(); }, [loadAll]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((o) => [o.mko_number, o.material_name, o.final_output_name]
      .some((v) => (v || "").toLowerCase().includes(q)));
  }, [rows, search]);

  if (detailId) {
    return <MakloonOrderDetailPanel mkoId={detailId} currentUser={currentUser}
      onBack={() => { setDetailId(null); loadAll(); }} onError={setError} />;
  }

  return (
    <div data-testid="makloon-orders-view">
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="mko-error" />
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0"><Boxes size={16} className="text-[#0058CC]" /><h2 data-testid="makloon-orders-title">Order Makloon (Subkontrak)</h2></div>
          {canManage && <button data-testid="create-makloon-order-button" onClick={() => setShowCreate(true)} className="primary-button"><Plus size={13} /> Buat Order Makloon</button>}
        </div>
        <div className="section-body space-y-2.5">
          <div className="relative max-w-sm">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="mko-search" value={search} onChange={(e) => setSearch(e.target.value)} className="field !pl-8" placeholder="Cari no. pesanan / produk…" />
          </div>
          <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="makloon-orders"
                      allowed={currentUser?.allowed_line_codes} testId="mko-line-filter" />
          <div className="flex flex-wrap gap-1.5" data-testid="mko-filters">
            {FILTERS.map((f) => (
              <button key={f.key} data-testid={`mko-filter-${f.key || "all"}`} onClick={() => setStatusFilter(f.key)}
                className={`rounded-full border px-3 py-1 text-[11px] font-medium ${statusFilter === f.key ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>{f.label}</button>
            ))}
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="grid grid-cols-[110px_1.6fr_120px_130px_100px_90px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
          <span>No. Pesanan</span><span>Bahan → Output</span><span>Mode</span><span>Progress</span><span>Status</span><span className="text-right">Aksi</span>
        </div>
        {loading ? <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat pesanan…</div>
         : filtered.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="mko-empty">
            <Factory className="mx-auto mb-2 text-gray-300" size={28} />
            <p>{search || statusFilter ? "Tidak ada order cocok." : "Belum ada order makloon. Buat order pertama."}</p>
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
            {filtered.map((o) => {
              const st = MKO_STATUS[o.status] || MKO_STATUS.draft;
              const recv = (o.steps || []).filter((s) => s.status === "received").length;
              const total = (o.steps || []).length;
              return (
                <div key={o.id} data-testid={`mko-row-${o.id}`} className="grid grid-cols-[110px_1.6fr_120px_130px_100px_90px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{o.mko_number}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate flex items-center gap-1">{o.material_name} <ArrowRight size={11} className="text-[#9A9BA3]" /> {o.final_output_name || "—"}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate flex items-center gap-1"><EntityBadge entityId={o.entity_id} /> {formatQty(o.material_qty)} {o.material_unit} · est. {formatQty(o.forecast?.expected_finished_qty)} out</p>
                  </div>
                  <span className="text-[10.5px] font-medium text-[#6B6B73]">{MODE_LABEL[o.mode] || o.mode}</span>
                  <div>
                    <div className="h-1.5 w-full rounded-full bg-[#EFF0F2] overflow-hidden"><div className="h-full bg-[#0058CC]" style={{ width: total ? `${(recv / total) * 100}%` : "0%" }} /></div>
                    <p className="mt-0.5 text-[10px] text-[#6B6B73]">{recv}/{total} langkah diterima</p>
                  </div>
                  <span className={`status-pill ${st.cls}`}>{st.label}</span>
                  <div className="flex items-center justify-end gap-1.5">
                    {(o.claim_summary?.needs_action || 0) > 0 && (
                      <span data-testid={`mko-claim-badge-${o.id}`} title="Klaim selisih perlu tindakan"
                        className="rounded-full bg-[#FFF4E5] px-2 py-0.5 text-[10px] font-bold text-[#B26A00]">
                        {o.claim_summary.needs_action} klaim
                      </span>
                    )}
                    <button data-testid={`detail-mko-${o.id}`} onClick={() => setDetailId(o.id)} className="secondary-button !py-1 !px-2 text-[11px]">Detail</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showCreate && <MakloonWizard selectedEntity={selectedEntity}
        onClose={() => setShowCreate(false)}
        onSaved={(o) => { setShowCreate(false); loadAll(); if (o?.id) setDetailId(o.id); }}
        onError={setError} />}
    </div>
  );
}
