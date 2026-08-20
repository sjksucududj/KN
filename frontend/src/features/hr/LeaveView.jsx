import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { CalendarDays, RefreshCw, Plus, Check, X, Ban, Users } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import { LEAVE_TYPES, LEAVE_TYPE_LABEL, REQ_STATUS, recentMonths, curMonth, wibToday, countWorkdays, monthCells } from "./leaveUtils";

const WEEKDAYS = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"];

function StatusPill({ status }) {
  const s = REQ_STATUS[status] || REQ_STATUS.pending;
  return <span className={`status-pill ${s.cls}`}>{s.label}</span>;
}

// Modal pengajuan cuti untuk karyawan (HRD).
function LeaveCreateModal({ open, onClose, employees, onSubmit }) {
  const [empId, setEmpId] = useState("");
  const [type, setType] = useState("cuti_tahunan");
  const [from, setFrom] = useState(wibToday());
  const [to, setTo] = useState(wibToday());
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (open) { setEmpId(""); setType("cuti_tahunan"); setFrom(wibToday()); setTo(wibToday()); setReason(""); setErr(""); setBusy(false); } }, [open]);
  if (!open) return null;
  const days = countWorkdays(from, to);

  async function submit() {
    if (!empId) { setErr("Pilih karyawan dulu."); return; }
    if (days < 1) { setErr("Rentang tanggal harus mengandung minimal 1 hari kerja."); return; }
    setBusy(true); setErr("");
    try {
      await onSubmit({ employee_id: empId, leave_type: type, date_from: from, date_to: to, reason });
      onClose();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal mengajukan cuti."); }
    finally { setBusy(false); }
  }

  return (
    <div className="modal-overlay" data-testid="leave-create-modal" onClick={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className="modal-card">
        <p className="modal-title">Ajukan Cuti / Izin untuk Karyawan</p>
        {err && <div className="notice-bar danger !mb-2 !py-1.5"><span className="text-[11.5px]">{err}</span></div>}
        <div className="grid gap-2.5 mt-1">
          <div className="grid gap-1">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Karyawan *</label>
            <KNSelect data-testid="leave-form-employee" value={empId} onValueChange={setEmpId} className="field" placeholder="Pilih karyawan"
              options={employees.map((e) => ({ value: e.id, label: `${e.name}${e.code ? ` (${e.code})` : ""}` }))} />
          </div>
          <div className="grid gap-1">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Tipe</label>
            <KNSelect data-testid="leave-form-type" value={type} onValueChange={setType} className="field"
              options={LEAVE_TYPES.map((t) => ({ value: t.value, label: t.label + (t.deduct ? " · potong saldo" : "") }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Dari</label>
              <input data-testid="leave-form-from" type="date" className="form-input" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
            <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Sampai</label>
              <input data-testid="leave-form-to" type="date" className="form-input" value={to} onChange={(e) => setTo(e.target.value)} /></div>
          </div>
          <p className="text-[11px] text-[#6B6B73]">Estimasi <b>{days}</b> hari kerja.</p>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Alasan</label>
            <textarea data-testid="leave-form-reason" className="form-input" rows="2" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Opsional" /></div>
        </div>
        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose} disabled={busy}>Batal</button>
          <button data-testid="leave-form-submit" className="btn-primary" onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Ajukan"}</button>
        </div>
      </div>
    </div>
  );
}

export default function LeaveView({ currentUser, selectedEntity }) {
  const [tab, setTab] = useState("requests");
  const [rows, setRows] = useState([]);
  const [balances, setBalances] = useState([]);
  const [calendar, setCalendar] = useState({ month: curMonth(), leaves: [] });
  const [employees, setEmployees] = useState([]);
  const [month, setMonth] = useState("");
  const [status, setStatus] = useState("");
  const [calMonth, setCalMonth] = useState(curMonth());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [cancelTarget, setCancelTarget] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const params = useMemo(() => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}), [selectedEntity]);
  const empName = useMemo(() => Object.fromEntries(employees.map((e) => [e.id, e.name])), [employees]);

  useEffect(() => { loadEmployees(); }, [selectedEntity]); // eslint-disable-line
  useEffect(() => { if (tab === "requests") loadRequests(); }, [tab, month, status, selectedEntity]); // eslint-disable-line
  useEffect(() => { if (tab === "balance") loadBalances(); }, [tab, selectedEntity]); // eslint-disable-line
  useEffect(() => { if (tab === "calendar") loadCalendar(); }, [tab, calMonth, selectedEntity]); // eslint-disable-line

  async function loadEmployees() {
    try { const r = await axios.get(`${API}/hr/employees`, { params }); setEmployees(Array.isArray(r.data) ? r.data : []); } catch (_) { /* noop */ }
  }
  async function loadRequests() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/leave-requests`, { params: { ...params, ...(month ? { month } : {}), ...(status ? { status } : {}) } }); setRows(Array.isArray(r.data) ? r.data : []); setError(""); }
    catch (e) { setError(e.response?.data?.detail || "Gagal memuat pengajuan cuti."); }
    finally { setLoading(false); }
  }
  async function loadBalances() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/leave-balances`, { params }); setBalances(Array.isArray(r.data) ? r.data : []); setError(""); }
    catch (e) { setError(e.response?.data?.detail || "Gagal memuat saldo cuti."); }
    finally { setLoading(false); }
  }
  async function loadCalendar() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/leave-calendar`, { params: { ...params, month: calMonth } }); setCalendar(r.data || { month: calMonth, leaves: [] }); setError(""); }
    catch (e) { setError(e.response?.data?.detail || "Gagal memuat kalender cuti."); }
    finally { setLoading(false); }
  }

  async function createLeave(payload) {
    await axios.post(`${API}/hr/leave-requests`, payload);
    setNotice("Pengajuan cuti dibuat."); loadRequests();
  }
  async function approve(id) {
    try { await axios.post(`${API}/hr/leave-requests/${id}/approve`); setNotice("Cuti disetujui."); setError(""); loadRequests(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menyetujui."); }
  }
  async function doReject(reason) {
    const id = rejectTarget.id; setRejectTarget(null);
    try { await axios.post(`${API}/hr/leave-requests/${id}/reject`, { reason }); setNotice("Cuti ditolak."); setError(""); loadRequests(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menolak."); }
  }
  async function doCancel(reason) {
    const id = cancelTarget.id; setCancelTarget(null);
    try { await axios.post(`${API}/hr/leave-requests/${id}/cancel`, { reason }); setNotice("Cuti dibatalkan."); setError(""); loadRequests(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal membatalkan."); }
  }

  const monthOpts = [{ value: "", label: "Semua Periode" }, ...recentMonths().map((m) => ({ value: m, label: m }))];
  const statusOpts = [{ value: "", label: "Semua Status" }, ...Object.entries(REQ_STATUS).map(([v, s]) => ({ value: v, label: s.label }))];
  const calMonthOpts = recentMonths(15).map((m) => ({ value: m, label: m }));

  // index leaves per tanggal untuk kalender
  const leavesByDate = useMemo(() => {
    const map = {};
    (calendar.leaves || []).forEach((lv) => {
      (lv.work_dates || []).forEach((d) => { (map[d] = map[d] || []).push(lv); });
    });
    return map;
  }, [calendar]);

  const TABS = [
    { id: "requests", label: "Pengajuan" },
    { id: "calendar", label: "Kalender" },
    { id: "balance", label: "Saldo Cuti" },
  ];

  return (
    <div data-testid="leave-view">
      <ErrorNotice message={error} onRetry={() => { setError(""); }} onDismiss={() => setError("")} testId="leave-error" />
      {notice && <div className="notice-bar success !mb-2" data-testid="leave-notice"><span className="text-[12px]">{notice}</span><button onClick={() => setNotice("")} className="ml-auto text-[11px] underline">tutup</button></div>}

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2"><CalendarDays size={16} className="text-[#0058CC]" /><h2 data-testid="leave-title">Cuti & Izin</h2></div>
          <div className="flex items-center gap-2">
            {canManage && <button data-testid="leave-create-button" onClick={() => setCreateOpen(true)} className="primary-button !py-1.5"><Plus size={14} /> Ajukan utk Karyawan</button>}
            <button data-testid="leave-refresh" onClick={() => { loadRequests(); loadBalances(); loadCalendar(); }} className="icon-button" title="Muat ulang"><RefreshCw size={15} /></button>
          </div>
        </div>
        <div className="flex items-center gap-1 px-3 pb-2">
          {TABS.map((t) => (
            <button key={t.id} data-testid={`leave-tab-${t.id}`} onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 text-[12px] font-semibold rounded-md ${tab === t.id ? "bg-[#0058CC] text-white" : "text-[#6B6B73] hover:bg-[#F2F4F7]"}`}>{t.label}</button>
          ))}
        </div>
      </div>

      {/* TAB: Pengajuan */}
      {tab === "requests" && (
        <div className="section-card">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-[#EFF0F2]">
            <div className="w-[150px]"><KNSelect data-testid="leave-filter-month" value={month} onValueChange={setMonth} className="field !py-1" options={monthOpts} /></div>
            <div className="w-[150px]"><KNSelect data-testid="leave-filter-status" value={status} onValueChange={setStatus} className="field !py-1" options={statusOpts} /></div>
          </div>
          <div className="grid grid-cols-[1.5fr_1fr_1.2fr_70px_100px_1.3fr] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Karyawan</span><span>Tipe</span><span>Periode</span><span className="text-center">Hari</span><span>Status</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="leave-loading">Memuat...</div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="leave-empty"><CalendarDays className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada pengajuan cuti.</p></div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
              {rows.map((r) => (
                <div key={r.id} data-testid={`leave-row-${r.id}`} className="grid grid-cols-[1.5fr_1fr_1.2fr_70px_100px_1.3fr] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="flex items-center gap-1 min-w-0"><EntityBadge entityId={r.entity_id} /><span className="text-[12px] font-semibold truncate">{r.employee_name}</span></span>
                  <span className="text-[11.5px]">{LEAVE_TYPE_LABEL[r.leave_type] || r.leave_type}</span>
                  <span className="text-[11px] text-[#6B6B73]">{r.date_from} → {r.date_to}</span>
                  <span className="text-[12px] font-bold text-center tabular-nums">{r.days}</span>
                  <span><StatusPill status={r.status} /></span>
                  <div className="flex items-center justify-end gap-1">
                    {canManage && r.status === "pending" && (
                      <>
                        <button data-testid={`leave-approve-${r.id}`} onClick={() => approve(r.id)} className="icon-button text-[#1F7A45] hover:bg-green-50" title="Setujui"><Check size={14} /></button>
                        <button data-testid={`leave-reject-${r.id}`} onClick={() => setRejectTarget(r)} className="icon-button text-[#C0392B] hover:bg-red-50" title="Tolak"><X size={14} /></button>
                      </>
                    )}
                    {canManage && r.status === "approved" && (
                      <button data-testid={`leave-cancel-${r.id}`} onClick={() => setCancelTarget(r)} className="icon-button text-[#6B6B73] hover:bg-gray-100" title="Batalkan"><Ban size={14} /></button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB: Kalender */}
      {tab === "calendar" && (
        <div className="section-card" data-testid="leave-calendar">
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#EFF0F2]">
            <p className="text-[12px] font-bold">Kalender Cuti Disetujui</p>
            <div className="w-[150px]"><KNSelect data-testid="leave-calendar-month" value={calMonth} onValueChange={setCalMonth} className="field !py-1" options={calMonthOpts} /></div>
          </div>
          <div className="p-3">
            <div className="grid grid-cols-7 gap-1 mb-1">
              {WEEKDAYS.map((w) => <div key={w} className="text-center text-[10px] font-bold uppercase text-[#9A9BA3]">{w}</div>)}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {monthCells(calMonth).map((d, i) => (
                <div key={i} className={`min-h-[64px] rounded-md border p-1 ${d ? "border-[#EFF0F2] bg-white" : "border-transparent"}`}>
                  {d && <p className="text-[10px] text-[#9A9BA3] mb-0.5">{Number(d.slice(-2))}</p>}
                  {(leavesByDate[d] || []).slice(0, 3).map((lv) => (
                    <div key={lv.id + d} className="text-[9.5px] leading-tight truncate rounded px-1 py-0.5 mb-0.5"
                      style={{ background: lv.leave_type && lv.leave_type.startsWith("cuti") ? "#E7F0FF" : "#FFF3E0", color: "#444" }}
                      title={`${lv.employee_name} · ${LEAVE_TYPE_LABEL[lv.leave_type] || lv.leave_type}`}>{lv.employee_name}</div>
                  ))}
                  {(leavesByDate[d] || []).length > 3 && <p className="text-[9px] text-[#9A9BA3]">+{leavesByDate[d].length - 3}</p>}
                </div>
              ))}
            </div>
            {loading && <p className="text-[11px] text-[#6B6B73] mt-2">Memuat...</p>}
          </div>
        </div>
      )}

      {/* TAB: Saldo */}
      {tab === "balance" && (
        <div className="section-card" data-testid="leave-balance-tab">
          <div className="grid grid-cols-[1.6fr_110px_90px_90px_100px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Karyawan</span><span className="text-center">Jatah</span><span className="text-center">Terpakai</span><span className="text-center">Menunggu</span><span className="text-right">Sisa</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat...</div>
          ) : balances.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="leave-balance-empty"><Users className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada saldo cuti.</p></div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
              {balances.map((b) => (
                <div key={b.id} data-testid={`leave-balance-row-${b.employee_id}`} className="grid grid-cols-[1.6fr_110px_90px_90px_100px] items-center px-3 py-2.5">
                  <span className="flex items-center gap-1 min-w-0"><EntityBadge entityId={b.entity_id} /><span className="text-[12px] font-semibold truncate">{empName[b.employee_id] || b.employee_id}</span></span>
                  <span className="text-[12px] text-center tabular-nums">{b.entitlement} hari</span>
                  <span className="text-[12px] text-center tabular-nums text-[#C0392B]">{b.used}</span>
                  <span className="text-[12px] text-center tabular-nums text-[#B7791F]">{b.pending}</span>
                  <span className="text-[13px] text-right font-bold tabular-nums text-[#1F7A45]">{b.remaining}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <LeaveCreateModal open={createOpen} onClose={() => setCreateOpen(false)} employees={employees} onSubmit={createLeave} />
      <ConfirmModal open={!!rejectTarget} title="Tolak Pengajuan Cuti" message={`Tolak cuti ${rejectTarget?.employee_name || ""}?`} confirmLabel="Tolak" danger withReason reasonLabel="Alasan penolakan" reasonRequired={false} onConfirm={doReject} onCancel={() => setRejectTarget(null)} testId="leave-reject-modal" />
      <ConfirmModal open={!!cancelTarget} title="Batalkan Cuti" message={`Batalkan cuti ${cancelTarget?.employee_name || ""}? Status absensi terkait akan dikembalikan.`} confirmLabel="Batalkan" danger withReason reasonLabel="Alasan" reasonRequired={false} onConfirm={doCancel} onCancel={() => setCancelTarget(null)} testId="leave-cancel-modal" />
    </div>
  );
}
