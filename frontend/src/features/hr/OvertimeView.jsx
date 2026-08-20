import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Timer, RefreshCw, Plus, Check, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import { REQ_STATUS, recentMonths, wibToday } from "./leaveUtils";

function StatusPill({ status }) {
  const s = REQ_STATUS[status] || REQ_STATUS.pending;
  return <span className={`status-pill ${s.cls}`}>{s.label}</span>;
}

function OvertimeCreateModal({ open, onClose, employees, onSubmit }) {
  const [empId, setEmpId] = useState("");
  const [date, setDate] = useState(wibToday());
  const [hours, setHours] = useState("2");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (open) { setEmpId(""); setDate(wibToday()); setHours("2"); setReason(""); setErr(""); setBusy(false); } }, [open]);
  if (!open) return null;

  async function submit() {
    if (!empId) { setErr("Pilih karyawan dulu."); return; }
    const h = parseFloat(hours);
    if (!(h > 0 && h <= 12)) { setErr("Jam lembur harus > 0 dan ≤ 12."); return; }
    setBusy(true); setErr("");
    try { await onSubmit({ employee_id: empId, date, hours: h, reason }); onClose(); }
    catch (e) { setErr(e.response?.data?.detail || "Gagal mengajukan lembur."); }
    finally { setBusy(false); }
  }

  return (
    <div className="modal-overlay" data-testid="overtime-create-modal" onClick={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className="modal-card">
        <p className="modal-title">Ajukan Lembur untuk Karyawan</p>
        {err && <div className="notice-bar danger !mb-2 !py-1.5"><span className="text-[11.5px]">{err}</span></div>}
        <div className="grid gap-2.5 mt-1">
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Karyawan *</label>
            <KNSelect data-testid="overtime-form-employee" value={empId} onValueChange={setEmpId} className="field" placeholder="Pilih karyawan"
              options={employees.map((e) => ({ value: e.id, label: `${e.name}${e.code ? ` (${e.code})` : ""}` }))} /></div>
          <div className="grid grid-cols-2 gap-2">
            <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Tanggal</label>
              <input data-testid="overtime-form-date" type="date" className="form-input" value={date} onChange={(e) => setDate(e.target.value)} /></div>
            <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Jam (maks 12)</label>
              <input data-testid="overtime-form-hours" type="number" step="0.5" min="0" max="12" className="form-input" value={hours} onChange={(e) => setHours(e.target.value)} /></div>
          </div>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Alasan</label>
            <textarea data-testid="overtime-form-reason" className="form-input" rows="2" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Opsional" /></div>
        </div>
        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose} disabled={busy}>Batal</button>
          <button data-testid="overtime-form-submit" className="btn-primary" onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Ajukan"}</button>
        </div>
      </div>
    </div>
  );
}

export default function OvertimeView({ currentUser, selectedEntity }) {
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [month, setMonth] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const params = useMemo(() => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}), [selectedEntity]);

  useEffect(() => { loadEmployees(); }, [selectedEntity]); // eslint-disable-line
  useEffect(() => { load(); }, [month, status, selectedEntity]); // eslint-disable-line

  async function loadEmployees() {
    try { const r = await axios.get(`${API}/hr/employees`, { params }); setEmployees(Array.isArray(r.data) ? r.data : []); } catch (_) { /* noop */ }
  }
  async function load() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/overtime`, { params: { ...params, ...(month ? { month } : {}), ...(status ? { status } : {}) } }); setRows(Array.isArray(r.data) ? r.data : []); setError(""); }
    catch (e) { setError(e.response?.data?.detail || "Gagal memuat data lembur."); }
    finally { setLoading(false); }
  }
  async function createOt(payload) { await axios.post(`${API}/hr/overtime`, payload); setNotice("Pengajuan lembur dibuat."); load(); }
  async function approve(id) {
    try { await axios.post(`${API}/hr/overtime/${id}/approve`); setNotice("Lembur disetujui & masuk perhitungan payroll."); setError(""); load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menyetujui."); }
  }
  async function doReject(reason) {
    const id = rejectTarget.id; setRejectTarget(null);
    try { await axios.post(`${API}/hr/overtime/${id}/reject`, { reason }); setNotice("Lembur ditolak."); setError(""); load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menolak."); }
  }

  const monthOpts = [{ value: "", label: "Semua Periode" }, ...recentMonths().map((m) => ({ value: m, label: m }))];
  const statusOpts = [{ value: "", label: "Semua Status" }, ...Object.entries(REQ_STATUS).filter(([v]) => v !== "cancelled").map(([v, s]) => ({ value: v, label: s.label }))];

  return (
    <div data-testid="overtime-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="overtime-error" />
      {notice && <div className="notice-bar success !mb-2" data-testid="overtime-notice"><span className="text-[12px]">{notice}</span><button onClick={() => setNotice("")} className="ml-auto text-[11px] underline">tutup</button></div>}

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2"><Timer size={16} className="text-[#0058CC]" /><h2 data-testid="overtime-title">Lembur</h2></div>
          <div className="flex items-center gap-2">
            {canManage && <button data-testid="overtime-create-button" onClick={() => setCreateOpen(true)} className="primary-button !py-1.5"><Plus size={14} /> Ajukan utk Karyawan</button>}
            <button data-testid="overtime-refresh" onClick={load} className="icon-button" title="Muat ulang"><RefreshCw size={15} /></button>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 pb-2">
          <div className="w-[150px]"><KNSelect data-testid="overtime-filter-month" value={month} onValueChange={setMonth} className="field !py-1" options={monthOpts} /></div>
          <div className="w-[150px]"><KNSelect data-testid="overtime-filter-status" value={status} onValueChange={setStatus} className="field !py-1" options={statusOpts} /></div>
        </div>
      </div>

      <div className="section-card">
        <div className="grid grid-cols-[1.5fr_110px_80px_1.4fr_100px_90px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
          <span>Karyawan</span><span>Tanggal</span><span className="text-center">Jam</span><span>Alasan</span><span>Status</span><span className="text-right">Aksi</span>
        </div>
        {loading ? (
          <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="overtime-loading">Memuat...</div>
        ) : rows.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="overtime-empty"><Timer className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada pengajuan lembur.</p></div>
        ) : (
          <div className="divide-y divide-[#EFF0F2] max-h-[600px] overflow-y-auto">
            {rows.map((r) => (
              <div key={r.id} data-testid={`overtime-row-${r.id}`} className="grid grid-cols-[1.5fr_110px_80px_1.4fr_100px_90px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                <span className="flex items-center gap-1 min-w-0"><EntityBadge entityId={r.entity_id} /><span className="text-[12px] font-semibold truncate">{r.employee_name}</span></span>
                <span className="text-[11px] text-[#6B6B73]">{r.date}</span>
                <span className="text-[12px] font-bold text-center tabular-nums">{r.hours} j</span>
                <span className="text-[11px] text-[#6B6B73] truncate" title={r.reason}>{r.reason || "—"}</span>
                <span><StatusPill status={r.status} /></span>
                <div className="flex items-center justify-end gap-1">
                  {canManage && r.status === "pending" && (
                    <>
                      <button data-testid={`overtime-approve-${r.id}`} onClick={() => approve(r.id)} className="icon-button text-[#1F7A45] hover:bg-green-50" title="Setujui"><Check size={14} /></button>
                      <button data-testid={`overtime-reject-${r.id}`} onClick={() => setRejectTarget(r)} className="icon-button text-[#C0392B] hover:bg-red-50" title="Tolak"><X size={14} /></button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <OvertimeCreateModal open={createOpen} onClose={() => setCreateOpen(false)} employees={employees} onSubmit={createOt} />
      <ConfirmModal open={!!rejectTarget} title="Tolak Pengajuan Lembur" message={`Tolak lembur ${rejectTarget?.employee_name || ""}?`} confirmLabel="Tolak" danger withReason reasonLabel="Alasan penolakan" reasonRequired={false} onConfirm={doReject} onCancel={() => setRejectTarget(null)} testId="overtime-reject-modal" />
    </div>
  );
}
