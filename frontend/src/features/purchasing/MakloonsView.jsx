import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Factory, Plus, Search, Pencil, Power, BarChart3, MapPin } from "lucide-react";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import MakloonFormModal from "./MakloonFormModal";
import Makloon360Panel from "./Makloon360Panel";
import useProcessTypes from "../../hooks/useProcessTypes";

/** MakloonsView (M1) — master mitra makloon: list, search, CRUD, Makloon 360. */
export default function MakloonsView({ currentUser, selectedEntity }) {
  const { labelOf: processLabel } = useProcessTypes();   // FASE T (4a)
  const [rows, setRows] = useState([]);
  const [entities, setEntities] = useState([]);
  const [terms, setTerms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);
  useEffect(() => { loadAll(); }, [selectedEntity]); // eslint-disable-line

  async function loadAll() {
    setLoading(true);
    try {
      const params = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const [mRes, eRes, tRes] = await Promise.all([
        axios.get(`${API}/makloons`, { params }),
        axios.get(`${API}/entities`).catch(() => ({ data: [] })),
        axios.get(`${API}/payment-terms`).catch(() => ({ data: [] })),
      ]);
      setRows(Array.isArray(mRes.data) ? mRes.data : []);
      setEntities(Array.isArray(eRes.data) ? eRes.data : []);
      setTerms(Array.isArray(tRes.data) ? tRes.data.filter((t) => t.active !== false) : []);
      setError("");
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat data makloon."); }
    finally { setLoading(false); }
  }

  async function doDeactivate(m) {
    try { await axios.delete(`${API}/makloons/${m.id}`); setDeactivateTarget(null); await loadAll(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menonaktifkan makloon."); setDeactivateTarget(null); }
  }

  const filtered = rows.filter((m) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return [m.name, m.code, m.city, m.pic_name].some((v) => (v || "").toLowerCase().includes(q));
  });

  if (detailId) {
    return <Makloon360Panel makloonId={detailId} currentUser={currentUser} onError={setError}
      onBack={() => { setDetailId(null); loadAll(); }}
      onEdit={(m) => { setDetailId(null); setEditTarget(m); setShowForm(true); }} />;
  }

  return (
    <div data-testid="makloons-view">
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="makloon-error" />
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0"><Factory size={16} className="text-[#0058CC]" /><h2 data-testid="makloons-title">Mitra Makloon (Subkontraktor)</h2></div>
          {canManage && <button data-testid="create-makloon-button" onClick={() => { setEditTarget(null); setShowForm(true); }} className="primary-button"><Plus size={13} /> Buat Makloon</button>}
        </div>
        <div className="section-body">
          <div className="relative max-w-sm">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="makloon-search" value={search} onChange={(e) => setSearch(e.target.value)} className="field !pl-8" placeholder="Cari nama / kode / kota…" />
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="grid grid-cols-[90px_1.5fr_1.1fr_130px_80px_110px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
          <span>Kode</span><span>Nama / Proses</span><span>Kontak</span><span>Kota / Lead</span><span>Status</span><span className="text-right">Aksi</span>
        </div>
        {loading ? <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat makloon…</div>
         : filtered.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="makloon-empty">
            <Factory className="mx-auto mb-2 text-gray-300" size={28} />
            <p>{search ? "Tidak ada makloon cocok." : "Belum ada makloon. Buat mitra makloon pertama."}</p>
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
            {filtered.map((m) => (
              <div key={m.id} data-testid={`makloon-row-${m.id}`} className="grid grid-cols-[90px_1.5fr_1.1fr_130px_80px_110px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                <span className="text-[11.5px] font-bold text-[#0058CC]">{m.code}</span>
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold truncate">{m.name}</p>
                  <p className="text-[10.5px] text-[#6B6B73] truncate flex items-center gap-1"><EntityBadge entityId={m.entity_id} /><span className="truncate">{(m.process_types || []).map((p) => processLabel(p)).join(", ") || "—"}</span></p>
                </div>
                <div className="min-w-0"><p className="text-[11px] truncate">{m.pic_name || "—"}</p><p className="text-[10.5px] text-[#6B6B73] truncate">{m.phone || "—"}</p></div>
                <div className="min-w-0"><p className="text-[11px] truncate flex items-center gap-1"><MapPin size={10} />{m.city || "—"}</p><p className="text-[10.5px] text-[#6B6B73]">{m.lead_time_days || 0} hari</p></div>
                <span className={`status-pill ${m.status === "active" ? "pill-success" : "pill-muted"}`}>{m.status === "active" ? "Aktif" : "Nonaktif"}</span>
                <div className="flex items-center justify-end gap-1">
                  <button data-testid={`detail-makloon-${m.id}`} onClick={() => setDetailId(m.id)} className="icon-button text-[#0058CC]" title="Makloon 360"><BarChart3 size={13} /></button>
                  {canManage && <>
                    <button data-testid={`edit-makloon-${m.id}`} onClick={() => { setEditTarget(m); setShowForm(true); }} className="icon-button" title="Ubah"><Pencil size={13} /></button>
                    {m.status === "active" && <button data-testid={`deactivate-makloon-${m.id}`} onClick={() => setDeactivateTarget(m)} className="icon-button text-red-400 hover:text-red-600" title="Nonaktifkan"><Power size={13} /></button>}
                  </>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <MakloonFormModal open={showForm} editTarget={editTarget} entities={entities} terms={terms} selectedEntity={selectedEntity}
        onClose={() => { setShowForm(false); setEditTarget(null); }}
        onSaved={() => { setShowForm(false); setEditTarget(null); loadAll(); }} onError={setError} />
      <ConfirmModal open={!!deactivateTarget} title={`Nonaktifkan ${deactivateTarget?.name || "Makloon"}`}
        message="Makloon yang dinonaktifkan tidak akan muncul saat memilih makloon baru."
        confirmLabel="Nonaktifkan" danger onConfirm={() => doDeactivate(deactivateTarget)}
        onCancel={() => setDeactivateTarget(null)} testId="makloon-deactivate-modal" />
    </div>
  );
}
