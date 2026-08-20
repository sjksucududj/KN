import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Network, Plus, Pencil, Power, Building2, Briefcase, Users } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import FormModal from "../../components/FormModal";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";

const EMPTY = { name: "", code: "", description: "", entity_id: "", parent_id: "", unit_type: "department" };

function Field({ label, req, children }) {
  return (
    <div>
      <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">{label} {req && <span className="req">*</span>}</label>
      {children}
    </div>
  );
}

export default function OrgUnitsView({ currentUser, selectedEntity }) {
  const [tree, setTree] = useState([]);
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [delTarget, setDelTarget] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => { loadAll(); }, [selectedEntity]); // eslint-disable-line

  async function loadAll() {
    setLoading(true);
    try {
      const params = selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {};
      const [tRes, eRes] = await Promise.all([
        axios.get(`${API}/hr/org-units/tree`, { params }),
        axios.get(`${API}/entities`).catch(() => ({ data: [] })),
      ]);
      setTree(Array.isArray(tRes.data) ? tRes.data : []);
      setEntities(Array.isArray(eRes.data) ? eRes.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat struktur organisasi.");
    } finally {
      setLoading(false);
    }
  }

  function openCreateDept() {
    setEditId(null);
    setForm({ ...EMPTY, unit_type: "department", entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "" });
    setShowForm(true);
  }
  function openCreatePosition(dept) {
    setEditId(null);
    setForm({ ...EMPTY, unit_type: "position", parent_id: dept.id, entity_id: dept.entity_id });
    setShowForm(true);
  }
  function openEdit(unit) {
    setEditId(unit.id);
    setForm({ name: unit.name || "", code: unit.code || "", description: unit.description || "", entity_id: unit.entity_id || "", parent_id: unit.parent_id || "", unit_type: unit.unit_type });
    setShowForm(true);
  }

  async function submit() {
    if (!form.name.trim()) { setError("Nama unit wajib diisi."); return; }
    try {
      if (editId) {
        await axios.patch(`${API}/hr/org-units/${editId}`, { data: { name: form.name, code: form.code, description: form.description } });
        setNotice("Unit organisasi diperbarui.");
      } else {
        await axios.post(`${API}/hr/org-units`, form);
        setNotice(form.unit_type === "department" ? "Departemen dibuat." : "Jabatan dibuat.");
      }
      setShowForm(false); setForm(EMPTY); setEditId(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan unit organisasi.");
    }
  }

  async function doDelete(unit) {
    try {
      await axios.delete(`${API}/hr/org-units/${unit.id}`);
      setNotice(`${unit.name} dinonaktifkan.`);
      setDelTarget(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menonaktifkan unit.");
      setDelTarget(null);
    }
  }

  return (
    <div data-testid="org-units-view">
      {notice && (
        <div className="notice-bar success" data-testid="org-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>
      )}
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="org-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Network size={16} className="text-[#0058CC]" />
            <h2 data-testid="org-units-title">Struktur Organisasi</h2>
          </div>
          {canManage && (
            <button data-testid="create-department-button" onClick={openCreateDept} className="primary-button"><Plus size={13} /> Tambah Departemen</button>
          )}
        </div>
        <div className="section-body text-[11.5px] text-[#6B6B73]">
          Hierarki: <b>Perusahaan (Entitas)</b> &rsaquo; <b>Departemen</b> &rsaquo; <b>Jabatan</b>. Pilih entitas aktif di kanan atas untuk melihat strukturnya.
        </div>
      </div>

      {/* FASE P4 — form unit organisasi menjadi POP-UP (dulu menyelip di atas pohon
          struktur sehingga hierarkinya terdorong ke bawah). Logika form tidak diubah. */}
      <FormModal
        open={showForm && canManage}
        onClose={() => { setShowForm(false); setEditId(null); }}
        title={editId ? "Ubah Unit Organisasi" : form.unit_type === "department" ? "Tambah Departemen" : "Tambah Jabatan"}
        subtitle="Perusahaan (Entitas) › Departemen › Jabatan"
        icon={Network}
        size="md"
        testId="org-form"
        onSubmit={submit}
        submitLabel={editId ? "Simpan Perubahan" : "Simpan"}
        submitTestId="submit-org-button"
        cancelTestId="cancel-org-button"
        error={error}
      >
        <div className="grid grid-cols-2 gap-3">
            <Field label="Nama Unit" req>
              <input data-testid="org-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="field" placeholder={form.unit_type === "department" ? "Penjualan" : "Sales Executive"} />
            </Field>
            <Field label="Kode (opsional)">
              <input data-testid="org-code-input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className="field" placeholder="Otomatis bila kosong" />
            </Field>
            {!editId && (
              <Field label="Entitas">
                <KNSelect data-testid="org-entity-select" value={form.entity_id} onValueChange={(v) => setForm({ ...form, entity_id: v })} className="field" placeholder="Pilih entitas"
                  options={[{ value: "", label: "— Entitas aktif —" }, ...entities.map((e) => ({ value: e.id, label: e.short_name || e.legal_name || e.id }))]} />
              </Field>
            )}
            <div className="col-span-2">
              <Field label="Deskripsi">
                <input data-testid="org-desc-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="field" placeholder="Deskripsi singkat" />
              </Field>
            </div>
        </div>
      </FormModal>

      <div className="section-card">
        <div className="section-body">
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="org-loading">Memuat struktur...</div>
          ) : tree.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="org-empty">
              <Network className="mx-auto mb-2 text-gray-300" size={28} />
              <p>Belum ada struktur organisasi untuk entitas ini.</p>
            </div>
          ) : (
            <div className="space-y-3" data-testid="org-tree">
              {tree.map((dept) => (
                <div key={dept.id} className="rounded-lg border border-[#EFF0F2]" data-testid={`org-dept-${dept.id}`}>
                  <div className="flex items-center gap-2 px-3 py-2.5 bg-[#FAFBFC] rounded-t-lg">
                    <Building2 size={15} className="text-[#0058CC]" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[12.5px] font-bold truncate">{dept.name}</p>
                      <p className="text-[10.5px] text-[#6B6B73] flex items-center gap-1"><EntityBadge entityId={dept.entity_id} /><span>{dept.code}</span></p>
                    </div>
                    <span className="text-[10.5px] text-[#6B6B73] flex items-center gap-1"><Users size={11} />{dept.employee_count || 0}</span>
                    {canManage && (
                      <div className="flex items-center gap-1">
                        <button data-testid={`add-position-${dept.id}`} onClick={() => openCreatePosition(dept)} className="icon-button text-[#0058CC]" title="Tambah Jabatan"><Plus size={13} /></button>
                        <button data-testid={`edit-org-${dept.id}`} onClick={() => openEdit(dept)} className="icon-button" title="Ubah"><Pencil size={12} /></button>
                        <button data-testid={`delete-org-${dept.id}`} onClick={() => setDelTarget(dept)} className="icon-button text-red-400 hover:text-red-600" title="Nonaktifkan"><Power size={12} /></button>
                      </div>
                    )}
                  </div>
                  <div className="divide-y divide-[#F4F5F7]">
                    {(dept.children || []).length === 0 ? (
                      <p className="px-3 py-2 text-[11px] text-[#9A9BA3]">Belum ada jabatan.</p>
                    ) : (
                      (dept.children || []).map((pos) => (
                        <div key={pos.id} className="flex items-center gap-2 px-3 py-2 pl-8" data-testid={`org-position-${pos.id}`}>
                          <Briefcase size={13} className="text-[#6B219A]" />
                          <div className="min-w-0 flex-1">
                            <p className="text-[12px] font-medium truncate">{pos.name}</p>
                            <p className="text-[10px] text-[#9A9BA3]">{pos.code}</p>
                          </div>
                          <span className="text-[10.5px] text-[#6B6B73] flex items-center gap-1"><Users size={11} />{pos.employee_count || 0}</span>
                          {canManage && (
                            <div className="flex items-center gap-1">
                              <button data-testid={`edit-org-${pos.id}`} onClick={() => openEdit(pos)} className="icon-button" title="Ubah"><Pencil size={12} /></button>
                              <button data-testid={`delete-org-${pos.id}`} onClick={() => setDelTarget(pos)} className="icon-button text-red-400 hover:text-red-600" title="Nonaktifkan"><Power size={12} /></button>
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={!!delTarget}
        title={`Nonaktifkan · ${delTarget?.name || "Unit"}`}
        message="Unit dengan sub-unit atau karyawan aktif tidak dapat dinonaktifkan. Pindahkan dulu bila perlu."
        confirmLabel="Nonaktifkan"
        danger
        onConfirm={() => doDelete(delTarget)}
        onCancel={() => setDelTarget(null)}
        testId="org-delete-modal"
      />
    </div>
  );
}
