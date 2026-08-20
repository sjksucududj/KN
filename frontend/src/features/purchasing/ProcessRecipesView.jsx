import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { GitBranch, Plus, Search, Pencil, Power, ArrowRight } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import RecipeFormModal from "./RecipeFormModal";
import useProcessTypes from "../../hooks/useProcessTypes";

/** ProcessRecipesView (M1) — master resep konversi (input→output) + tarif + forecast. */
export default function ProcessRecipesView({ currentUser, selectedEntity }) {
  // FASE T (4a) — penyaring & lencana proses dibaca dari registry hidup.
  const { options: processOptions, labelOf: processLabel } = useProcessTypes();
  const PROC_FILTER = processOptions([{ value: "", label: "Semua Proses" }]);
  const [rows, setRows] = useState([]);
  const [makloons, setMakloons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [procFilter, setProcFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);
  useEffect(() => { loadAll(); }, [selectedEntity]); // eslint-disable-line

  async function loadAll() {
    setLoading(true);
    try {
      const params = (selectedEntity && selectedEntity !== "all") ? { entity_id: selectedEntity } : {};
      const [rRes, mRes] = await Promise.all([
        axios.get(`${API}/process-recipes`, { params }),
        axios.get(`${API}/makloons`, { params: { status: "active" } }).catch(() => ({ data: [] })),
      ]);
      setRows(Array.isArray(rRes.data) ? rRes.data : []);
      setMakloons(Array.isArray(mRes.data) ? mRes.data : []);
      setError("");
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat resep proses."); }
    finally { setLoading(false); }
  }

  async function doDeactivate(r) {
    try { await axios.delete(`${API}/process-recipes/${r.id}`); setDeactivateTarget(null); await loadAll(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menonaktifkan resep."); setDeactivateTarget(null); }
  }

  const filtered = rows.filter((r) => {
    if (procFilter && r.process_type !== procFilter) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return [r.name, r.input_sku, r.output_sku, r.default_makloon_name].some((v) => (v || "").toLowerCase().includes(q));
  });

  return (
    <div data-testid="process-recipes-view">
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="recipe-error" />
      <div className="section-card mb-3">
        <div className="section-head flex-wrap gap-2">
          <div className="flex items-center gap-2 min-w-0"><GitBranch size={16} className="text-[#0058CC]" /><h2 data-testid="recipes-title">Resep Proses (Konversi)</h2></div>
          <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
            <div className="relative min-w-[180px]">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="recipe-search" value={search} onChange={(e) => setSearch(e.target.value)} className="field !pl-8" placeholder="Cari resep / SKU / makloon…" />
            </div>
            <KNSelect data-testid="recipe-proc-filter" className="field w-[150px]" value={procFilter} onValueChange={setProcFilter} options={PROC_FILTER} />
            {canManage && <button data-testid="create-recipe-button" onClick={() => { setEditTarget(null); setShowForm(true); }} className="primary-button"><Plus size={13} /> Buat Resep</button>}
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="grid grid-cols-[1.4fr_1.6fr_1fr_150px_100px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
          <span>Resep / Proses</span><span>Konversi (Input → Output)</span><span>Makloon Default</span><span>Yield / Susut / Sisa</span><span className="text-right">Aksi</span>
        </div>
        {loading ? <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat resep…</div>
         : filtered.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="recipe-empty">
            <GitBranch className="mx-auto mb-2 text-gray-300" size={28} />
            <p>{search || procFilter ? "Tidak ada resep cocok." : "Belum ada resep. Buat resep konversi pertama."}</p>
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
            {filtered.map((r) => (
              <div key={r.id} data-testid={`recipe-row-${r.id}`} className="grid grid-cols-[1.4fr_1.6fr_1fr_150px_100px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                <div className="min-w-0"><p className="text-[12px] font-semibold truncate">{r.name}</p><span className="rounded bg-[#F3E9FA] px-1.5 text-[10px] font-bold text-[#6B219A]">{processLabel(r.process_type)}</span></div>
                <div className="min-w-0 flex items-center gap-1.5 text-[11px]">
                  <span className="truncate"><b>{r.input_sku || "?"}</b> <span className="text-[#9A9BA3]">{r.input_unit}</span></span>
                  <ArrowRight size={12} className="shrink-0 text-[#0058CC]" />
                  <span className="truncate"><b>{r.output_sku || "?"}</b> <span className="text-[#9A9BA3]">{r.output_unit}</span></span>
                </div>
                <p className="text-[11px] truncate">{r.default_makloon_name || "—"}</p>
                <p className="text-[10.5px] tabular-nums text-[#3C3C43]">y {r.yield_factor} · s {r.waste_pct}% · sisa {r.byproduct_pct}%</p>
                <div className="flex items-center justify-end gap-1">
                  {canManage && <>
                    <button data-testid={`edit-recipe-${r.id}`} onClick={() => { setEditTarget(r); setShowForm(true); }} className="icon-button" title="Ubah"><Pencil size={13} /></button>
                    {r.status === "active" && <button data-testid={`deactivate-recipe-${r.id}`} onClick={() => setDeactivateTarget(r)} className="icon-button text-red-400 hover:text-red-600" title="Nonaktifkan"><Power size={13} /></button>}
                  </>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showForm && <RecipeFormModal editTarget={editTarget} makloons={makloons} selectedEntity={selectedEntity}
        onClose={() => { setShowForm(false); setEditTarget(null); }}
        onSaved={() => { setShowForm(false); setEditTarget(null); loadAll(); }} onError={setError} />}
      <ConfirmModal open={!!deactivateTarget} title={`Nonaktifkan resep "${deactivateTarget?.name || ""}"`}
        message="Resep yang dinonaktifkan tidak muncul saat membuat order makloon." confirmLabel="Nonaktifkan" danger
        onConfirm={() => doDeactivate(deactivateTarget)} onCancel={() => setDeactivateTarget(null)} testId="recipe-deactivate-modal" />
    </div>
  );
}
