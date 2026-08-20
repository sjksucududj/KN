import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Users, Plus, Search, Pencil, Power, UserCheck, Building2, Briefcase, BarChart3 } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import { formatCurrency } from "../../utils/formatters";
import { EmployeeFormDrawer } from "./EmployeeFormDrawer";
import Employee360Panel from "./Employee360Panel";

const STATUS_PILL = {
  active: { cls: "pill-success", label: "Aktif" },
  inactive: { cls: "pill-muted", label: "Nonaktif" },
  resigned: { cls: "pill-danger", label: "Resigned" },
};

function Stat({ icon: Icon, label, value, testId }) {
  return (
    <div className="section-card !p-3 flex items-center gap-3" data-testid={testId}>
      <div className="h-9 w-9 rounded-lg grid place-items-center" style={{ background: "rgba(0,88,204,.10)" }}>
        <Icon size={16} className="text-[#0058CC]" />
      </div>
      <div className="min-w-0">
        <p className="text-[10.5px] uppercase font-semibold text-[#6B6B73] truncate">{label}</p>
        <p className="text-[16px] font-bold tabular-nums leading-tight">{value}</p>
      </div>
    </div>
  );
}

export default function EmployeesView({ currentUser, selectedEntity }) {
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [positions, setPositions] = useState([]);
  const [entities, setEntities] = useState([]);
  const [users, setUsers] = useState([]);
  const [shifts, setShifts] = useState([]);
  const [settings, setSettings] = useState({});
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [filterDept, setFilterDept] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editEmployee, setEditEmployee] = useState(null);
  const [deactivateTarget, setDeactivateTarget] = useState(null);
  const [detailId, setDetailId] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => { loadAll(); }, [selectedEntity]); // eslint-disable-line

  async function loadAll() {
    setLoading(true);
    try {
      const params = selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {};
      const [empRes, orgRes, entRes, usrRes, setRes, sumRes, shiftRes] = await Promise.all([
        axios.get(`${API}/hr/employees`, { params }),
        axios.get(`${API}/hr/org-units`, { params }),
        axios.get(`${API}/entities`).catch(() => ({ data: [] })),
        axios.get(`${API}/users`).catch(() => ({ data: [] })),
        axios.get(`${API}/hr/settings`).catch(() => ({ data: {} })),
        axios.get(`${API}/hr/summary`, { params }).catch(() => ({ data: null })),
        axios.get(`${API}/hr/shifts`, { params }).catch(() => ({ data: [] })),
      ]);
      setEmployees(Array.isArray(empRes.data) ? empRes.data : []);
      const org = Array.isArray(orgRes.data) ? orgRes.data : [];
      setDepartments(org.filter((u) => u.unit_type === "department" && u.status === "active"));
      setPositions(org.filter((u) => u.unit_type === "position" && u.status === "active"));
      setEntities(Array.isArray(entRes.data) ? entRes.data : []);
      setUsers(Array.isArray(usrRes.data) ? usrRes.data : []);
      setSettings(setRes.data || {});
      setSummary(sumRes.data || null);
      setShifts((Array.isArray(shiftRes.data) ? shiftRes.data : []).filter((s) => s.status === "active"));
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data karyawan.");
    } finally {
      setLoading(false);
    }
  }

  function openCreate() { setEditEmployee(null); setDrawerOpen(true); }
  function openEdit(emp) { setEditEmployee(emp); setDrawerOpen(true); }

  async function doDeactivate(emp) {
    try {
      await axios.delete(`${API}/hr/employees/${emp.id}`);
      setNotice(`${emp.name} ditandai resigned.`);
      setDeactivateTarget(null);
      await loadAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menonaktifkan karyawan.");
      setDeactivateTarget(null);
    }
  }

  const filtered = employees.filter((e) => {
    if (filterDept && e.department_id !== filterDept) return false;
    if (filterStatus && e.status !== filterStatus) return false;
    if (search) {
      const q = search.toLowerCase();
      if (![e.name, e.code, e.nik, e.phone, e.email, e.position_name].some((v) => (v || "").toLowerCase().includes(q))) return false;
    }
    return true;
  });

  if (detailId) {
    return <Employee360Panel employeeId={detailId} currentUser={currentUser} onError={setError}
      onBack={() => { setDetailId(null); loadAll(); }}
      onEdit={(e) => { setDetailId(null); openEdit(e); }} />;
  }

  return (
    <div data-testid="employees-view">
      {notice && (
        <div className="notice-bar success" data-testid="employee-notice">
          <span>{notice}</span><button onClick={() => setNotice("")}>×</button>
        </div>
      )}
      <ErrorNotice message={error} onRetry={loadAll} onDismiss={() => setError("")} testId="employee-error" />

      {/* Summary */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4 mb-3">
        <Stat icon={Users} label="Total Karyawan" value={summary?.total_employees ?? employees.length} testId="stat-total-employees" />
        <Stat icon={UserCheck} label="Aktif" value={summary?.active ?? "-"} testId="stat-active-employees" />
        <Stat icon={Building2} label="Departemen" value={summary?.departments ?? departments.length} testId="stat-departments" />
        <Stat icon={Briefcase} label="Akun Ter-link" value={summary?.linked_accounts ?? "-"} testId="stat-linked-accounts" />
      </div>

      {/* Header + filters */}
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Users size={16} className="text-[#0058CC]" />
            <h2 data-testid="employees-title">Master Karyawan</h2>
          </div>
          {canManage && (
            <button data-testid="create-employee-button" onClick={openCreate} className="primary-button">
              <Plus size={13} /> Tambah Karyawan
            </button>
          )}
        </div>
        <div className="section-body grid gap-2 md:grid-cols-[1fr_180px_160px]">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="employee-search" value={search} onChange={(e) => setSearch(e.target.value)} className="field !pl-8" placeholder="Cari nama / kode / NIK / jabatan..." />
          </div>
          <KNSelect data-testid="employee-filter-dept" value={filterDept} onValueChange={setFilterDept} className="field" placeholder="Semua Departemen"
            options={[{ value: "", label: "Semua Departemen" }, ...departments.map((d) => ({ value: d.id, label: d.name }))]} />
          <KNSelect data-testid="employee-filter-status" value={filterStatus} onValueChange={setFilterStatus} className="field" placeholder="Semua Status"
            options={[{ value: "", label: "Semua Status" }, { value: "active", label: "Aktif" }, { value: "inactive", label: "Nonaktif" }, { value: "resigned", label: "Resigned" }]} />
        </div>
      </div>

      {/* Table */}
      <div className="section-card">
        <div className="grid grid-cols-[90px_1.5fr_1.1fr_120px_110px_90px_96px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
          <span>Kode</span><span>Nama / Jabatan</span><span>Departemen / Akun</span><span>Tipe</span><span className="text-right">Gaji Pokok</span><span>Status</span><span className="text-right">Aksi</span>
        </div>
        {loading ? (
          <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="employees-loading">Memuat karyawan...</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="employees-empty">
            <Users className="mx-auto mb-2 text-gray-300" size={28} />
            <p>{search || filterDept || filterStatus ? "Tidak ada karyawan cocok." : "Belum ada karyawan. Tambah karyawan pertama."}</p>
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
            {filtered.map((e) => {
              const pill = STATUS_PILL[e.status] || STATUS_PILL.inactive;
              return (
                <div key={e.id} data-testid={`employee-row-${e.id}`} className="grid grid-cols-[90px_1.5fr_1.1fr_120px_110px_90px_96px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{e.code}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{e.name}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate">{e.position_name || "—"}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-[11px] truncate flex items-center gap-1"><EntityBadge entityId={e.entity_id} /><span className="truncate">{e.department_name || "—"}</span></p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate">{e.has_account ? `🔗 ${e.user_role}` : "tanpa akun"}</p>
                  </div>
                  <span className="text-[11px] capitalize">{e.employment_type}</span>
                  <span className="text-[11.5px] tabular-nums text-right">{e.pii_redacted ? "•••" : formatCurrency(e.base_salary)}</span>
                  <span><span data-testid={`employee-status-${e.id}`} className={`status-pill ${pill.cls}`}>{pill.label}</span></span>
                  <div className="flex items-center justify-end gap-1">
                    <button data-testid={`detail-employee-${e.id}`} onClick={() => setDetailId(e.id)} className="icon-button text-[#0058CC]" title="Karyawan 360°"><BarChart3 size={13} /></button>
                    {canManage && (
                      <>
                        <button data-testid={`edit-employee-${e.id}`} onClick={() => openEdit(e)} className="icon-button" title="Ubah"><Pencil size={13} /></button>
                        {e.status !== "resigned" && (
                          <button data-testid={`deactivate-employee-${e.id}`} onClick={() => setDeactivateTarget(e)} className="icon-button text-red-400 hover:text-red-600" title="Resign / Nonaktifkan"><Power size={13} /></button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <EmployeeFormDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSaved={(msg) => { setNotice(msg); loadAll(); }}
        editEmployee={editEmployee}
        departments={departments}
        positions={positions}
        entities={entities}
        users={users}
        settings={settings}
        shifts={shifts}
        defaultEntity={selectedEntity}
      />

      <ConfirmModal
        open={!!deactivateTarget}
        title={`Tandai Resigned · ${deactivateTarget?.name || "Karyawan"}`}
        message="Karyawan akan ditandai keluar (resign) dan tidak muncul di daftar aktif. Anda dapat mengubah statusnya kembali lewat Ubah."
        confirmLabel="Tandai Resigned"
        danger
        onConfirm={() => doDeactivate(deactivateTarget)}
        onCancel={() => setDeactivateTarget(null)}
        testId="employee-deactivate-modal"
      />
    </div>
  );
}
