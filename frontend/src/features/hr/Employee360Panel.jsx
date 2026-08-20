import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ArrowLeft, Edit3, UserCircle, Building2, Briefcase, MapPin, PhoneCall,
  CalendarCheck, CalendarDays, Wallet, ReceiptText, Target, Download, Loader2 } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import RecordDetailModal from "../documents/RecordDetailModal";

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "—");
const money = (v) => formatCurrency(Number(v || 0));
const sumAllow = (a) => (typeof a === "number" ? a : (a && typeof a === "object" ? Object.values(a).reduce((s, v) => s + (Number(v) || 0), 0) : 0));

const ATT_TONE = { hadir: "success", present: "success", wfh: "info", dinas: "info", cuti: "warning", izin: "warning", sakit: "warning", alfa: "danger", absent: "danger", mangkir: "danger" };
const LEAVE_TONE = { approved: "success", pending: "warning", rejected: "danger", cancelled: "muted" };
const tone = (map, s) => map[(s || "").toLowerCase()] || "muted";

const TABS = [
  { key: "attendance", label: "Absensi", icon: CalendarCheck },
  { key: "leave", label: "Cuti/Izin", icon: CalendarDays },
  { key: "payslips", label: "Slip Gaji", icon: ReceiptText },
  { key: "kpi", label: "KPI", icon: Target },
];

/** Karyawan 360° — profil + ringkasan absensi + cuti + slip gaji + KPI + dokumen. */
export default function Employee360Panel({ employeeId, currentUser, onBack, onEdit, onError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("attendance");
  const [record, setRecord] = useState(null);
  const [dl, setDl] = useState("");
  const canManage = ["admin", "manager"].includes(currentUser?.role);

  useEffect(() => { load(); }, [employeeId]); // eslint-disable-line
  async function load() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/employees/${employeeId}/360`); setData(r.data); }
    catch (e) { onError?.(e.response?.data?.detail || "Gagal memuat detail karyawan."); onBack?.(); }
    finally { setLoading(false); }
  }

  async function downloadPayslip(slip) {
    setDl(slip.id);
    try {
      const r = await axios.get(`${API}/hr/payslips/${slip.id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = `slip-gaji-${slip.number || slip.period || slip.id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) { onError?.("Gagal mengunduh slip gaji."); }
    finally { setDl(""); }
  }

  if (loading && !data) return <div className="section-card py-12 text-center text-[12px] text-[#6B6B73]" data-testid="employee-360-loading">Memuat detail karyawan…</div>;
  if (!data) return null;

  const summ = data.attendance_summary || {};
  const attendance = data.attendance || [];
  const leaves = data.leave_requests || [];
  const payslips = data.payslips || [];
  const kpis = data.kpi_entries || [];
  const pii = data.can_view_pii;
  const totalAllow = sumAllow(data.allowances);

  function openPayslip(p) {
    setRecord({
      icon: <ReceiptText size={17} className="text-[#0058CC]" />, title: `Slip ${p.period}`, code: p.number || p.period,
      statusText: p.status, statusTone: tone(LEAVE_TONE, p.status),
      meta: [
        { label: "Periode", value: p.period },
        { label: "Status", value: p.status },
        { label: "Gaji Pokok", value: pii ? money(p.base_salary) : "•••" },
        { label: "Tunjangan", value: pii ? money(sumAllow(p.allowances)) : "•••" },
        { label: "Lembur", value: pii ? money(p.overtime) : "•••" },
        { label: "Bruto", value: pii ? money(p.gross) : "•••" },
        { label: "PPh21", value: pii ? money(p.pph21) : "•••", tone: "text-[#C0392B]" },
        { label: "BPJS (Kry)", value: pii ? money(p.bpjs_emp_total ?? p.bpjs_emp) : "•••", tone: "text-[#C0392B]" },
        { label: "Take Home (Net)", value: pii ? money(p.net) : "•••", tone: "text-[#0058CC]" },
      ],
      customActions: (
        <button data-testid="employee-360-payslip-download" onClick={() => downloadPayslip(p)} disabled={dl === p.id}
          className="flex items-center gap-1.5 rounded-md border border-[#EDEEF1] px-2.5 py-1.5 text-[12px] font-semibold text-[#4A4B52] hover:bg-[#F2F3F5]">
          {dl === p.id ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />} Unduh Slip PDF
        </button>
      ),
      note: pii ? undefined : "Nilai gaji disembunyikan (tanpa izin hr.view_pii).",
    });
  }

  return (
    <div data-testid="employee-360-panel">
      <button data-testid="employee-360-back" onClick={onBack} className="secondary-button mb-3"><ArrowLeft size={13} /> Kembali ke daftar</button>

      {/* Header */}
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <UserCircle size={18} className="text-[#0058CC]" />
              <h2 className="truncate" data-testid="employee-360-name">{data.name}</h2>
              <span className="text-[11px] font-bold text-[#0058CC]">{data.code}</span>
              <span className={`status-pill ${data.status === "active" ? "pill-success" : data.status === "resigned" ? "pill-danger" : "pill-muted"}`}>{data.status === "active" ? "Aktif" : data.status === "resigned" ? "Resigned" : "Nonaktif"}</span>
            </div>
            <p className="text-[11px] text-[#6B6B73] mt-0.5 flex items-center gap-2 flex-wrap">
              {data.position_name && <span className="flex items-center gap-1"><Briefcase size={10} />{data.position_name}</span>}
              {data.department_name && <span className="flex items-center gap-1"><Building2 size={10} />{data.department_name}</span>}
              <span className="capitalize">· {data.employment_type}</span>
            </p>
          </div>
          {canManage && <button data-testid="employee-360-edit" onClick={() => onEdit?.(data)} className="secondary-button"><Edit3 size={13} /> Ubah</button>}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[320px_1fr]">
        {/* Left */}
        <div className="space-y-3">
          <div className="section-card">
            <div className="section-head"><div className="flex items-center gap-2"><Wallet size={14} className="text-[#0058CC]" /><h3 className="text-[12.5px] font-bold">Ringkasan Kepegawaian</h3></div></div>
            <div className="section-body grid grid-cols-2 gap-2">
              <Kpi label="Gaji Pokok" value={pii ? money(data.base_salary) : "•••"} tone="#0058CC" testId="employee-360-salary" />
              <Kpi label="Total Tunjangan" value={pii ? money(totalAllow) : "•••"} />
              <Kpi label="Tipe" value={<span className="capitalize">{data.employment_type || "—"}</span>} />
              <Kpi label="Tgl Masuk" value={fmtDate(data.join_date)} />
              <Kpi label="PTKP" value={data.ptkp_status || "—"} />
              <Kpi label="Bank" value={pii ? (data.bank_name || "—") : "•••"} sub={pii ? data.bank_acc_no : ""} />
            </div>
          </div>

          <div className="section-card">
            <div className="section-head"><div className="flex items-center gap-2"><CalendarCheck size={14} className="text-[#0058CC]" /><h3 className="text-[12.5px] font-bold">Absensi (30 hari terakhir)</h3></div></div>
            <div className="section-body grid grid-cols-2 gap-2">
              <Kpi label="Hadir" value={summ.present || 0} tone="#1F7A45" testId="employee-360-att-present" />
              <Kpi label="Terlambat" value={summ.late || 0} tone={summ.late ? "#B45309" : "#1C1C1E"} />
              <Kpi label="Cuti/Izin" value={summ.leave || 0} />
              <Kpi label="Alfa" value={summ.absent || 0} tone={summ.absent ? "#C0392B" : "#1C1C1E"} />
            </div>
          </div>

          <div className="section-card">
            <div className="section-head"><h3 className="text-[12.5px] font-bold">Profil & Kontak</h3></div>
            <div className="section-body space-y-2 text-[11.5px]">
              <p className="flex items-center gap-2"><PhoneCall size={12} className="text-[#6B6B73]" />{data.phone || "—"}</p>
              {data.email && <p className="pl-5 text-[#6B6B73]">{data.email}</p>}
              <p className="flex items-start gap-2"><MapPin size={12} className="text-[#6B6B73] mt-0.5" /><span className="text-[#3C3C43]">{data.address || "—"}</span></p>
              <div className="pt-2 border-t border-[#EFF0F2] space-y-1">
                <p><span className="text-[#9A9BA3]">NIK:</span> {pii ? (data.nik || "—") : "•••"}</p>
                <p><span className="text-[#9A9BA3]">NPWP:</span> {pii ? (data.npwp || "—") : "•••"}</p>
                <p><span className="text-[#9A9BA3]">BPJS Kes:</span> {data.bpjs_kes_enabled ? (pii ? (data.bpjs_kes_no || "aktif") : "aktif") : "—"}</p>
                <p><span className="text-[#9A9BA3]">BPJS TK:</span> {data.bpjs_tk_enabled ? (pii ? (data.bpjs_tk_no || "aktif") : "aktif") : "—"}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right */}
        <div className="section-card self-start">
          <div className="section-head"><div className="tab-bar">
            {TABS.map((t) => { const Icon = t.icon; const n = { attendance: attendance.length, leave: leaves.length, payslips: payslips.length, kpi: kpis.length }[t.key];
              return (
                <button key={t.key} data-testid={`employee-360-tab-${t.key}`} className={`tab-button ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                  <Icon size={13} /> {t.label}{n != null && <span className="tab-badge">{n}</span>}
                </button>
              ); })}
          </div></div>
          <div className="section-body">
            {tab === "attendance" && (
              attendance.length === 0 ? <Empty testId="employee-360-list-attendance-empty">Belum ada data absensi.</Empty> : (
                <div className="divide-y divide-[#EFF0F2] max-h-[460px] overflow-y-auto" data-testid="employee-360-list-attendance">
                  {attendance.map((a) => (
                    <div key={a.id} className="flex items-center justify-between py-2 text-[11.5px]">
                      <div><p className="font-semibold">{fmtDate(a.date)}</p><p className="text-[10px] text-[#6B6B73]">{a.clock_in || "—"} – {a.clock_out || "—"}{a.late_min ? ` · telat ${a.late_min}m` : ""}</p></div>
                      <span className={`status-pill ${{ success: "pill-success", warning: "pill-warning", danger: "pill-danger", info: "status-receiving" }[tone(ATT_TONE, a.status)] || "pill-muted"}`}>{a.status || "—"}</span>
                    </div>
                  ))}
                </div>
              )
            )}
            {tab === "leave" && (
              leaves.length === 0 ? <Empty testId="employee-360-list-leave-empty">Belum ada pengajuan cuti/izin.</Empty> : (
                <div className="divide-y divide-[#EFF0F2] max-h-[460px] overflow-y-auto" data-testid="employee-360-list-leave">
                  {leaves.map((l) => (
                    <div key={l.id} className="flex items-center justify-between py-2 text-[11.5px]">
                      <div className="min-w-0"><p className="font-semibold truncate">{l.leave_label || l.leave_type}</p><p className="text-[10px] text-[#6B6B73]">{fmtDate(l.date_from)} – {fmtDate(l.date_to)} · {l.days} hari</p></div>
                      <span className={`status-pill ${{ success: "pill-success", warning: "pill-warning", danger: "pill-danger" }[tone(LEAVE_TONE, l.status)] || "pill-muted"}`}>{l.status}</span>
                    </div>
                  ))}
                </div>
              )
            )}
            {tab === "payslips" && (
              payslips.length === 0 ? <Empty testId="employee-360-list-payslips-empty">Belum ada slip gaji.</Empty> : (
                <div className="divide-y divide-[#EFF0F2] max-h-[460px] overflow-y-auto" data-testid="employee-360-list-payslips">
                  {payslips.map((p) => (
                    <button key={p.id} data-testid={`employee-360-payslip-${p.id}`} onClick={() => openPayslip(p)}
                      className="flex w-full items-center justify-between py-2.5 px-1 text-left text-[11.5px] hover:bg-[#FAFBFC] rounded-md transition-colors">
                      <div><p className="font-semibold text-[#0058CC]">Slip {p.period}</p><p className="text-[10px] text-[#6B6B73]">{p.number || "—"} · {p.status}</p></div>
                      <span className="tabular-nums font-semibold">{pii ? money(p.net) : "•••"}</span>
                    </button>
                  ))}
                </div>
              )
            )}
            {tab === "kpi" && (
              kpis.length === 0 ? <Empty testId="employee-360-list-kpi-empty">Belum ada entri KPI.</Empty> : (
                <div className="divide-y divide-[#EFF0F2] max-h-[460px] overflow-y-auto" data-testid="employee-360-list-kpi">
                  {kpis.map((k, i) => (
                    <div key={k.id || i} className="flex items-center justify-between py-2 text-[11.5px]">
                      <div className="min-w-0"><p className="font-semibold truncate">{k.metric || k.name || k.period}</p><p className="text-[10px] text-[#6B6B73]">{k.period || fmtDate(k.created_at)}</p></div>
                      <span className="tabular-nums font-semibold">{k.score ?? k.value ?? "—"}</span>
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        </div>
      </div>

      <RecordDetailModal open={!!record} onClose={() => setRecord(null)} currentUser={currentUser} {...(record || {})} />
    </div>
  );
}

function Empty({ children, testId }) {
  return <div className="py-8 text-center text-[11.5px] text-[#9A9BA3]" data-testid={testId}>{children}</div>;
}

function Kpi({ label, value, sub, tone = "#1C1C1E", testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2" data-testid={testId}>
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[14px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
      {sub && <p className="text-[9.5px] text-[#9A9BA3]">{sub}</p>}
    </div>
  );
}
