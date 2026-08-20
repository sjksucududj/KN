import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Clock, CalendarDays, BarChart3, Upload, CheckCircle2, Plus, FileSpreadsheet, AlertTriangle } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";

export const STATUS_PILL = {
  hadir: { cls: "pill-success", label: "Hadir" },
  telat: { cls: "pill-warning", label: "Telat" },
  flagged: { cls: "pill-danger", label: "Perlu Review" },
  izin: { cls: "pill-info", label: "Izin" },
  cuti: { cls: "pill-info", label: "Cuti" },
  alpha: { cls: "pill-danger", label: "Alpha" },
  libur: { cls: "pill-muted", label: "Libur" },
};
const METHOD_LABEL = { geo: "GPS", fingerprint: "Fingerprint", manual: "Manual" };
const STATUS_OPTS = ["hadir", "telat", "izin", "cuti", "alpha", "libur"].map((v) => ({ value: v, label: STATUS_PILL[v]?.label || v }));

export const fmtTime = (iso) => (iso && iso.length >= 16 ? iso.slice(11, 16) : "—");
export const fmtMin = (m) => {
  m = Number(m) || 0;
  if (m <= 0) return "—";
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}j ${m % 60 ? `${m % 60}m` : ""}`.trim();
};
const todayStr = () => new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 10);
const monthStr = () => new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 7);

function TabBtn({ id, active, onClick, icon: Icon, children }) {
  return (
    <button data-testid={`attendance-tab-${id}`} onClick={() => onClick(id)}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold transition ${active ? "bg-[#0058CC] text-white" : "text-[#6B6B73] hover:bg-[#F2F4F7]"}`}>
      <Icon size={14} /> {children}
    </button>
  );
}

function Stat({ label, value, color }) {
  return (
    <div className="section-card !p-3">
      <p className="text-[10.5px] uppercase font-semibold text-[#6B6B73]">{label}</p>
      <p className="text-[18px] font-bold tabular-nums leading-tight" style={{ color: color || "#1A1A1F" }}>{value}</p>
    </div>
  );
}

export default function AttendanceView({ currentUser, selectedEntity }) {
  const [tab, setTab] = useState("harian");
  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const params = useMemo(() => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}), [selectedEntity]);

  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // daily
  const [date, setDate] = useState(todayStr());
  const [statusFilter, setStatusFilter] = useState("");
  const [rows, setRows] = useState([]);
  const [loadingDaily, setLoadingDaily] = useState(true);
  const [approveTarget, setApproveTarget] = useState(null);

  // recap
  const [month, setMonth] = useState(monthStr());
  const [recap, setRecap] = useState(null);
  const [loadingRecap, setLoadingRecap] = useState(false);

  // employees (for manual)
  const [employees, setEmployees] = useState([]);
  const [showManual, setShowManual] = useState(false);
  const [manual, setManual] = useState({ employee_id: "", date: todayStr(), clock_in: "", clock_out: "", status: "hadir", note: "" });
  const [savingManual, setSavingManual] = useState(false);

  // import
  const [csvText, setCsvText] = useState("");
  const [fileName, setFileName] = useState("");
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState("");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  useEffect(() => { axios.get(`${API}/hr/employees`, { params }).then((r) => setEmployees(Array.isArray(r.data) ? r.data : [])).catch(() => {}); }, [selectedEntity]); // eslint-disable-line
  useEffect(() => { if (tab === "harian") loadDaily(); }, [tab, date, selectedEntity]); // eslint-disable-line
  useEffect(() => { if (tab === "rekap") loadRecap(); }, [tab, month, selectedEntity]); // eslint-disable-line
  useEffect(() => { if (tab === "import") axios.get(`${API}/hr/devices`, { params }).then((r) => setDevices(Array.isArray(r.data) ? r.data : [])).catch(() => {}); }, [tab, selectedEntity]); // eslint-disable-line

  async function loadDaily() {
    setLoadingDaily(true);
    try {
      const r = await axios.get(`${API}/hr/attendance`, { params: { ...params, date_from: date, date_to: date } });
      setRows(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat kehadiran."); }
    finally { setLoadingDaily(false); }
  }
  async function loadRecap() {
    setLoadingRecap(true);
    try {
      const r = await axios.get(`${API}/hr/attendance/recap`, { params: { ...params, month } });
      setRecap(r.data || null); setError("");
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat rekap."); }
    finally { setLoadingRecap(false); }
  }

  async function approve(rec) {
    try {
      await axios.patch(`${API}/hr/attendance/${rec.id}`, { data: { approved: true, status: "hadir" } });
      setNotice(`Absen ${rec.employee_name} disetujui.`); setApproveTarget(null); loadDaily();
    } catch (e) { setError(e.response?.data?.detail || "Gagal menyetujui absen."); setApproveTarget(null); }
  }

  async function submitManual() {
    if (!manual.employee_id) { setError("Pilih karyawan untuk entry manual."); return; }
    setSavingManual(true);
    try {
      await axios.post(`${API}/hr/attendance/manual`, manual);
      setNotice("Absen manual tersimpan."); setShowManual(false);
      setManual({ employee_id: "", date: todayStr(), clock_in: "", clock_out: "", status: "hadir", note: "" });
      if (manual.date === date) loadDaily();
    } catch (e) { setError(e.response?.data?.detail || "Gagal menyimpan absen manual."); }
    finally { setSavingManual(false); }
  }

  function handleFile(e) {
    const f = e.target.files?.[0]; if (!f) return;
    const r = new FileReader();
    r.onload = () => { setCsvText(String(r.result || "")); setImportResult(null); };
    r.readAsText(f); setFileName(f.name);
  }
  async function runImport() {
    if (!csvText.trim()) { setError("Pilih file CSV atau tempel data terlebih dahulu."); return; }
    setImporting(true); setImportResult(null);
    try {
      const body = { csv_text: csvText, device_id: deviceId || "" };
      if (selectedEntity && selectedEntity !== "all") body.entity_id = selectedEntity;
      const r = await axios.post(`${API}/hr/attendance/import`, body);
      setImportResult(r.data); setNotice(`Import selesai: ${r.data.imported || 0} kehadiran.`); setError("");
    } catch (e) { setError(e.response?.data?.detail || "Gagal import CSV."); }
    finally { setImporting(false); }
  }

  const shown = rows.filter((r) => (statusFilter ? r.status === statusFilter : true));
  const counts = useMemo(() => {
    const c = { total: rows.length, hadir: 0, telat: 0, flagged: 0 };
    rows.forEach((r) => { if (r.status === "hadir") c.hadir++; else if (r.status === "telat") c.telat++; else if (r.status === "flagged") c.flagged++; });
    return c;
  }, [rows]);
  const empOpts = [{ value: "", label: "— pilih karyawan —" }, ...employees.map((e) => ({ value: e.id, label: `${e.name} (${e.code})` }))];

  return (
    <div data-testid="attendance-view">
      {notice && (<div className="notice-bar success" data-testid="attendance-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>)}
      <ErrorNotice message={error} onRetry={tab === "rekap" ? loadRecap : loadDaily} onDismiss={() => setError("")} testId="attendance-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2"><Clock size={16} className="text-[#0058CC]" /><h2 data-testid="attendance-title">Presensi & Kehadiran</h2></div>
          <div className="flex items-center gap-1 bg-[#F7F8FA] rounded-lg p-1">
            <TabBtn id="harian" active={tab === "harian"} onClick={setTab} icon={CalendarDays}>Kehadiran Harian</TabBtn>
            <TabBtn id="rekap" active={tab === "rekap"} onClick={setTab} icon={BarChart3}>Rekap Periode</TabBtn>
            {canManage && <TabBtn id="import" active={tab === "import"} onClick={setTab} icon={Upload}>Impor Sidik Jari</TabBtn>}
          </div>
        </div>
      </div>

      {tab === "harian" && (
        <>
          <div className="grid gap-3 grid-cols-2 lg:grid-cols-4 mb-3">
            <Stat label="Total Hari Ini" value={counts.total} />
            <Stat label="Hadir" value={counts.hadir} color="#1F9D55" />
            <Stat label="Telat" value={counts.telat} color="#B7791F" />
            <Stat label="Perlu Review" value={counts.flagged} color="#C0392B" />
          </div>
          <div className="section-card mb-3">
            <div className="section-body grid gap-2 md:grid-cols-[180px_180px_1fr]">
              <div>
                <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Tanggal</label>
                <input data-testid="attendance-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} className="field" />
              </div>
              <div>
                <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Status</label>
                <KNSelect data-testid="attendance-status-filter" value={statusFilter} onValueChange={setStatusFilter} className="field" placeholder="Semua Status"
                  options={[{ value: "", label: "Semua Status" }, ...STATUS_OPTS, { value: "flagged", label: "Perlu Review" }]} />
              </div>
              {canManage && (
                <div className="flex items-end justify-end">
                  <button data-testid="attendance-manual-button" onClick={() => { setShowManual((s) => !s); setManual((m) => ({ ...m, date })); }} className="primary-button"><Plus size={13} /> Entry Manual</button>
                </div>
              )}
            </div>
            {showManual && canManage && (
              <div className="section-body border-t border-[#EFF0F2] grid gap-2 md:grid-cols-[1.4fr_130px_110px_110px_140px_auto]" data-testid="attendance-manual-panel">
                <KNSelect data-testid="manual-employee" value={manual.employee_id} onValueChange={(v) => setManual((m) => ({ ...m, employee_id: v }))} className="field" placeholder="Karyawan" searchable options={empOpts} />
                <input data-testid="manual-date" type="date" value={manual.date} onChange={(e) => setManual((m) => ({ ...m, date: e.target.value }))} className="field" />
                <input data-testid="manual-in" type="time" value={manual.clock_in} onChange={(e) => setManual((m) => ({ ...m, clock_in: e.target.value }))} className="field" />
                <input data-testid="manual-out" type="time" value={manual.clock_out} onChange={(e) => setManual((m) => ({ ...m, clock_out: e.target.value }))} className="field" />
                <KNSelect data-testid="manual-status" value={manual.status} onValueChange={(v) => setManual((m) => ({ ...m, status: v }))} className="field" options={STATUS_OPTS} />
                <button data-testid="manual-save" disabled={savingManual} onClick={submitManual} className="primary-button justify-center">{savingManual ? "..." : "Simpan"}</button>
              </div>
            )}
          </div>

          <div className="section-card">
            <div className="grid grid-cols-[1.6fr_1fr_84px_84px_80px_80px_96px_110px_84px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Karyawan</span><span>Shift</span><span>Masuk</span><span>Keluar</span><span>Telat</span><span>Kerja</span><span>Metode</span><span>Status</span><span className="text-right">Aksi</span>
            </div>
            {loadingDaily ? (
              <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="attendance-loading">Memuat kehadiran...</div>
            ) : shown.length === 0 ? (
              <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="attendance-empty"><CalendarDays className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada kehadiran pada tanggal ini.</p></div>
            ) : (
              <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
                {shown.map((r) => {
                  const pill = STATUS_PILL[r.status] || STATUS_PILL.hadir;
                  return (
                    <div key={r.id} data-testid={`attendance-row-${r.id}`} className="grid grid-cols-[1.6fr_1fr_84px_84px_80px_80px_96px_110px_84px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                      <div className="min-w-0 flex items-center gap-1"><EntityBadge entityId={r.entity_id} /><span className="text-[12px] font-semibold truncate">{r.employee_name}</span></div>
                      <span className="text-[11px] text-[#6B6B73] truncate">{r.shift_name || "—"}</span>
                      <span className="text-[11.5px] tabular-nums">{fmtTime(r.clock_in)}</span>
                      <span className="text-[11.5px] tabular-nums">{fmtTime(r.clock_out)}</span>
                      <span className="text-[11.5px] tabular-nums" style={{ color: r.late_min > 0 ? "#B7791F" : "#9A9BA3" }}>{fmtMin(r.late_min)}</span>
                      <span className="text-[11.5px] tabular-nums">{fmtMin(r.work_min)}</span>
                      <span className="text-[11px]">{METHOD_LABEL[r.method] || r.method}</span>
                      <span><span data-testid={`attendance-status-${r.id}`} className={`status-pill ${pill.cls}`}>{pill.label}</span></span>
                      <div className="flex items-center justify-end">
                        {canManage && r.status === "flagged" && (
                          <button data-testid={`approve-attendance-${r.id}`} onClick={() => setApproveTarget(r)} className="icon-button text-[#1F9D55]" title="Setujui"><CheckCircle2 size={15} /></button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}

      {tab === "rekap" && (
        <>
          <div className="section-card mb-3"><div className="section-body flex items-end gap-2">
            <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Periode (Bulan)</label>
              <input data-testid="recap-month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="field" /></div>
          </div></div>
          {loadingRecap ? (
            <div className="section-card py-10 text-center text-[12px] text-[#6B6B73]" data-testid="recap-loading">Memuat rekap...</div>
          ) : (
            <>
              <div className="grid gap-3 grid-cols-2 lg:grid-cols-4 mb-3">
                <Stat label="Karyawan" value={recap?.totals?.employees ?? 0} />
                <Stat label="Total Hadir (hari)" value={recap?.totals?.present_days ?? 0} color="#1F9D55" />
                <Stat label="Total Telat (hari)" value={recap?.totals?.late_days ?? 0} color="#B7791F" />
                <Stat label="Total Lembur" value={fmtMin(recap?.totals?.total_overtime_min)} color="#0058CC" />
              </div>
              <div className="section-card">
                <div className="grid grid-cols-[90px_1.6fr_1.1fr_72px_72px_84px_90px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
                  <span>Kode</span><span>Nama</span><span>Departemen</span><span className="text-right">Hadir</span><span className="text-right">Telat</span><span className="text-right">Review</span><span className="text-right">Lembur</span>
                </div>
                {(recap?.rows || []).length === 0 ? (
                  <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="recap-empty"><BarChart3 className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada data kehadiran pada periode ini.</p></div>
                ) : (
                  <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
                    {(recap?.rows || []).map((r) => (
                      <div key={r.employee_id} data-testid={`recap-row-${r.employee_id}`} className="grid grid-cols-[90px_1.6fr_1.1fr_72px_72px_84px_90px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                        <span className="text-[11.5px] font-bold text-[#0058CC]">{r.code || "—"}</span>
                        <span className="text-[12px] font-semibold truncate">{r.employee_name}</span>
                        <span className="text-[11px] text-[#6B6B73] truncate">{r.department_name || "—"}</span>
                        <span className="text-[11.5px] tabular-nums text-right">{r.present_days}</span>
                        <span className="text-[11.5px] tabular-nums text-right" style={{ color: r.late_days ? "#B7791F" : "#9A9BA3" }}>{r.late_days}</span>
                        <span className="text-[11.5px] tabular-nums text-right" style={{ color: r.flagged_days ? "#C0392B" : "#9A9BA3" }}>{r.flagged_days}</span>
                        <span className="text-[11.5px] tabular-nums text-right">{fmtMin(r.total_overtime_min)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}

      {tab === "import" && canManage && (
        <div className="grid gap-3 lg:grid-cols-[1.3fr_1fr]">
          <div className="section-card">
            <div className="section-head"><div className="flex items-center gap-2"><FileSpreadsheet size={15} className="text-[#0058CC]" /><h2>Impor Log Mesin Sidik Jari (ZKTeco)</h2></div></div>
            <div className="section-body space-y-3">
              <div>
                <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">File CSV</label>
                <input data-testid="import-file" type="file" accept=".csv,text/csv" onChange={handleFile} className="field !py-1.5" />
                {fileName && <p className="text-[11px] text-[#6B6B73] mt-1">{fileName}</p>}
              </div>
              <div>
                <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">atau tempel data CSV</label>
                <textarea data-testid="import-textarea" value={csvText} onChange={(e) => { setCsvText(e.target.value); setImportResult(null); }} rows="6" className="field font-mono text-[11px]" placeholder="user_id,timestamp\n1001,2026-05-04 08:01:00\n1001,2026-05-04 17:05:00" />
              </div>
              <div className="grid grid-cols-[1fr_auto] gap-2 items-end">
                <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Perangkat (opsional)</label>
                  <KNSelect data-testid="import-device" value={deviceId} onValueChange={setDeviceId} className="field" placeholder="— tanpa perangkat —"
                    options={[{ value: "", label: "— tanpa perangkat —" }, ...devices.map((d) => ({ value: d.id, label: d.name }))]} /></div>
                <button data-testid="import-run" disabled={importing} onClick={runImport} className="primary-button justify-center"><Upload size={13} /> {importing ? "Mengimpor..." : "Import"}</button>
              </div>
            </div>
          </div>
          <div className="space-y-3">
            <div className="section-card"><div className="section-body text-[11.5px] text-[#6B6B73] space-y-1">
              <p className="font-semibold text-[#1A1A1F]">Format kolom CSV:</p>
              <p><code className="text-[#0058CC]">user_id</code> = ID enroll mesin (cocok dgn <em>ID Mesin Fingerprint</em> karyawan).</p>
              <p><code className="text-[#0058CC]">timestamp</code> = <code>YYYY-MM-DD HH:MM:SS</code>. Multi-punch otomatis digabung (masuk=awal, keluar=akhir).</p>
              <p className="flex items-start gap-1"><AlertTriangle size={13} className="text-[#B7791F] mt-0.5" /> Idempoten: impor ulang tidak menggandakan data.</p>
            </div></div>
            {importResult && (
              <div className="section-card" data-testid="import-result"><div className="section-body">
                <p className="text-[12px] font-bold mb-2">Hasil Impor</p>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <Stat label="Kehadiran terbentuk" value={importResult.imported || 0} color="#1F9D55" />
                  <Stat label="Baris dilewati" value={importResult.skipped_rows || 0} color="#B7791F" />
                </div>
                {importResult.message && <p className="text-[11.5px] text-[#B7791F]">{importResult.message}</p>}
                <div className="divide-y divide-[#EFF0F2] max-h-[200px] overflow-y-auto">
                  {(importResult.records || []).map((r, i) => (
                    <div key={i} className="flex items-center justify-between py-1.5 text-[11.5px]"><span className="truncate">{r.employee_name} · {r.date}</span><span className="text-[#6B6B73]">{r.punches} punch · {STATUS_PILL[r.status]?.label || r.status}</span></div>
                  ))}
                </div>
              </div></div>
            )}
          </div>
        </div>
      )}

      <ConfirmModal open={!!approveTarget} title={`Setujui Absen · ${approveTarget?.employee_name || ""}`}
        message="Absen di luar geofence ini akan disetujui dan ditandai Hadir." confirmLabel="Setujui"
        onConfirm={() => approve(approveTarget)} onCancel={() => setApproveTarget(null)} testId="approve-attendance-modal" />
    </div>
  );
}
