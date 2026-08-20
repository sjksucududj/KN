import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { IdCard, Clock, Wallet, CalendarDays, Building2, Briefcase, Phone, Mail, CreditCard, LogIn, LogOut, MapPin } from "lucide-react";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import { STATUS_PILL, fmtTime, fmtMin } from "./AttendanceView";
import { MyPayslipCard } from "./MyPayslipCard";
import { MyLeaveCard } from "./MyLeaveCard";
import { MyKpiCard } from "./MyKpiCard";
import { MyDesignerKpiCard } from "./MyDesignerKpiCard";

function InfoRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-start gap-2 py-1.5">
      <Icon size={14} className="text-[#6B6B73] mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="text-[10px] uppercase font-semibold text-[#9A9BA3]">{label}</p>
        <p className="text-[12.5px] font-medium break-words" data-testid={`ess-${label.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value || "—"}</p>
      </div>
    </div>
  );
}

function getPosition() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  });
}

function AttendanceClockCard() {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { load(); }, []); // eslint-disable-line
  async function load() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/attendance/me`); setMe(r.data || null); setErr(""); }
    catch (e) { setErr(e.response?.data?.detail || "Gagal memuat absensi."); }
    finally { setLoading(false); }
  }
  async function clock(action) {
    setBusy(action); setMsg(""); setErr("");
    const pos = await getPosition();
    try {
      const r = await axios.post(`${API}/hr/attendance/${action}`, pos || {});
      setMsg(action === "clock-in"
        ? `Clock-in berhasil pukul ${fmtTime(r.data.clock_in)} (${STATUS_PILL[r.data.status]?.label || r.data.status}).`
        : `Clock-out berhasil pukul ${fmtTime(r.data.clock_out)} · kerja ${fmtMin(r.data.work_min)}.`);
      await load();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal mencatat absen."); }
    finally { setBusy(""); }
  }

  const today = me?.today;
  const pill = today ? (STATUS_PILL[today.status] || STATUS_PILL.hadir) : null;
  return (
    <div className="section-card !p-4" data-testid="ess-attendance-card">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2"><Clock size={15} className="text-[#0058CC]" /><p className="text-[12px] font-bold">Absen Hari Ini</p></div>
        {me?.shift?.name && <span className="text-[10.5px] text-[#6B6B73]">{me.shift.name} · {me.shift.jam_in}–{me.shift.jam_out}</span>}
      </div>
      {msg && <div className="notice-bar success !mb-2 !py-1.5" data-testid="ess-clock-notice"><span className="text-[11.5px]">{msg}</span></div>}
      {err && <div className="notice-bar danger !mb-2 !py-1.5" data-testid="ess-clock-error"><span className="text-[11.5px]">{err}</span></div>}
      {loading ? (
        <p className="text-[12px] text-[#6B6B73] py-3" data-testid="ess-clock-loading">Memuat...</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div className="rounded-lg bg-[#F7F8FA] p-2.5">
              <p className="text-[10px] uppercase font-semibold text-[#9A9BA3]">Masuk</p>
              <p className="text-[16px] font-bold tabular-nums" data-testid="ess-clock-in-time">{fmtTime(today?.clock_in)}</p>
            </div>
            <div className="rounded-lg bg-[#F7F8FA] p-2.5">
              <p className="text-[10px] uppercase font-semibold text-[#9A9BA3]">Keluar</p>
              <p className="text-[16px] font-bold tabular-nums" data-testid="ess-clock-out-time">{fmtTime(today?.clock_out)}</p>
            </div>
          </div>
          {pill && (
            <div className="flex items-center gap-2 mb-3 text-[11.5px]">
              <span className={`status-pill ${pill.cls}`} data-testid="ess-today-status">{pill.label}</span>
              {today?.outside_geofence && <span className="text-[#C0392B] flex items-center gap-1"><MapPin size={12} /> di luar lokasi</span>}
              {today?.late_min > 0 && <span className="text-[#B7791F]">telat {fmtMin(today.late_min)}</span>}
            </div>
          )}
          {!today?.clock_in ? (
            <button data-testid="ess-clock-in-button" disabled={busy} onClick={() => clock("clock-in")} className="primary-button w-full justify-center"><LogIn size={14} /> {busy === "clock-in" ? "Memproses..." : "Clock In"}</button>
          ) : !today?.clock_out ? (
            <button data-testid="ess-clock-out-button" disabled={busy} onClick={() => clock("clock-out")} className="primary-button w-full justify-center" style={{ background: "#6B219A" }}><LogOut size={14} /> {busy === "clock-out" ? "Memproses..." : "Clock Out"}</button>
          ) : (
            <p className="text-[11.5px] text-center text-[#1F9D55] font-semibold py-1.5" data-testid="ess-clock-done">✓ Absensi hari ini lengkap</p>
          )}
          {(me?.recent || []).length > 0 && (
            <div className="mt-3 pt-2 border-t border-[#EFF0F2]">
              <p className="text-[10px] uppercase font-semibold text-[#9A9BA3] mb-1">Riwayat Terakhir</p>
              <div className="space-y-1 max-h-[120px] overflow-y-auto">
                {(me.recent || []).slice(0, 7).map((r) => (
                  <div key={r.id} className="flex items-center justify-between text-[11px]">
                    <span className="text-[#6B6B73]">{r.date}</span>
                    <span className="tabular-nums">{fmtTime(r.clock_in)}–{fmtTime(r.clock_out)}</span>
                    <span className={`status-pill ${(STATUS_PILL[r.status] || STATUS_PILL.hadir).cls}`}>{(STATUS_PILL[r.status] || STATUS_PILL.hadir).label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function PlaceholderCard({ icon: Icon, label, hint, testId }) {
  return (
    <div className="section-card !p-4" data-testid={testId}>
      <div className="flex items-center gap-2 mb-1">
        <Icon size={15} className="text-[#0058CC]" />
        <p className="text-[12px] font-bold">{label}</p>
      </div>
      <p className="text-[18px] font-bold tabular-nums">—</p>
      <span className="status-pill pill-muted mt-1 inline-block">Segera hadir</span>
      <p className="text-[10.5px] text-[#9A9BA3] mt-1">{hint}</p>
    </div>
  );
}

export default function EmployeeSelfService({ currentUser }) {
  const [emp, setEmp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);

  useEffect(() => { load(); }, []); // eslint-disable-line

  async function load() {
    setLoading(true); setNotFound(false);
    try {
      const res = await axios.get(`${API}/hr/employees/me`);
      setEmp(res.data || null);
      setError("");
    } catch (e) {
      if (e.response?.status === 404) setNotFound(true);
      else setError(e.response?.data?.detail || "Gagal memuat profil.");
    } finally {
      setLoading(false);
    }
  }

  const totalAllowance = (emp?.allowances || []).reduce((s, a) => s + (parseFloat(a.amount) || 0), 0);

  return (
    <div data-testid="ess-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="ess-error" />

      {loading ? (
        <div className="section-card"><div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="ess-loading">Memuat profil...</div></div>
      ) : notFound ? (
        <div className="section-card"><div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="ess-empty">
          <IdCard className="mx-auto mb-2 text-gray-300" size={28} />
          <p>Profil karyawan belum tersedia untuk akun Anda.</p>
          <p className="text-[11px] mt-1">Hubungi admin HR untuk menautkan akun Anda ke data karyawan.</p>
        </div></div>
      ) : emp && (
        <div className="space-y-3">
          {/* Identity header */}
          <div className="section-card !p-5" data-testid="ess-profile-card">
            <div className="flex items-center gap-4">
              <div className="h-14 w-14 rounded-full grid place-items-center text-[18px] font-bold text-white" style={{ background: "linear-gradient(135deg,#0058CC,#6B219A)" }}>
                {(emp.name || "?").charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <h2 className="text-[16px] font-bold truncate" data-testid="ess-name">{emp.name}</h2>
                <p className="text-[12px] text-[#6B6B73] flex items-center gap-1.5 flex-wrap">
                  <span className="font-semibold text-[#0058CC]">{emp.code}</span>
                  <span>· {emp.position_name || "—"}</span>
                  <EntityBadge entityId={emp.entity_id} />
                </p>
              </div>
            </div>
          </div>

          {/* Live attendance (H1) + Slip Gaji (H4) + Cuti & Lembur (H3) + KPI Saya (H5) */}
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            <AttendanceClockCard />
            <MyPayslipCard />
            <MyLeaveCard />
            <MyKpiCard />
          </div>

          {/* PS-18 — KPI Saya (R&D): nilai desainer milik SENDIRI. Server menyaring,
              jadi nilai rekan tidak pernah terkirim ke halaman ini. */}
          <MyDesignerKpiCard />

          {/* Details */}
          <div className="grid gap-3 md:grid-cols-2">
            <div className="section-card">
              <div className="section-head"><h2 className="text-[13px] font-bold">Data Kepegawaian</h2></div>
              <div className="section-body">
                <InfoRow icon={Building2} label="Departemen" value={emp.department_name} />
                <InfoRow icon={Briefcase} label="Jabatan" value={emp.position_name} />
                <InfoRow icon={IdCard} label="Tipe" value={emp.employment_type} />
                <InfoRow icon={CalendarDays} label="Tanggal Masuk" value={emp.join_date} />
                <InfoRow icon={Phone} label="Telepon" value={emp.phone} />
                <InfoRow icon={Mail} label="Email" value={emp.email} />
              </div>
            </div>
            <div className="section-card">
              <div className="section-head"><h2 className="text-[13px] font-bold">Gaji & Bank</h2></div>
              <div className="section-body">
                <InfoRow icon={Wallet} label="Gaji Pokok" value={formatCurrency(emp.base_salary)} />
                <InfoRow icon={Wallet} label="Total Tunjangan" value={formatCurrency(totalAllowance)} />
                <InfoRow icon={CreditCard} label="Bank" value={emp.bank_name} />
                <InfoRow icon={CreditCard} label="No Rekening" value={emp.bank_acc_no} />
                <InfoRow icon={IdCard} label="NPWP" value={emp.npwp} />
                <InfoRow icon={IdCard} label="Status PTKP" value={emp.ptkp_status} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
