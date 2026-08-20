import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Receipt, RefreshCw, FileText, Building2 } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import { rp, pct, recentMonths, openPayslipPdf } from "./payrollUtils";

function DRow({ label, value, strong, color }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className={`text-[11.5px] ${strong ? "font-bold" : "text-[#6B6B73]"}`}>{label}</span>
      <span className={`text-[11.5px] tabular-nums ${strong ? "font-bold" : ""}`} style={color ? { color } : undefined}>{rp(value)}</span>
    </div>
  );
}

export default function PayslipsView({ currentUser, selectedEntity }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState("");
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);

  const params = useMemo(() => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}), [selectedEntity]);

  useEffect(() => { load(); }, [period, selectedEntity]); // eslint-disable-line
  async function load() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/payslips`, { params: { ...params, ...(period ? { period } : {}) } }); setRows(Array.isArray(r.data) ? r.data : []); setError(""); }
    catch (e) { setError(e.response?.data?.detail || "Gagal memuat slip gaji."); }
    finally { setLoading(false); }
  }
  async function pdf(id) { setBusy(true); try { await openPayslipPdf(id); } catch (_) { /* noop */ } finally { setBusy(false); } }

  const periodOpts = [{ value: "", label: "Semua Periode" }, ...recentMonths().map((m) => ({ value: m, label: m }))];
  const empB = sel?.bpjs_emp || {};
  const erB = sel?.bpjs_er || {};

  return (
    <div data-testid="payslips-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="payslips-error" />
      <div className="section-card mb-3">
        <div className="section-head"><div className="flex items-center gap-2"><Receipt size={16} className="text-[#0058CC]" /><h2 data-testid="payslips-title">Slip Gaji Karyawan</h2></div>
          <div className="flex items-center gap-2">
            <div className="w-[160px]"><KNSelect data-testid="payslips-period" value={period} onValueChange={setPeriod} className="field !py-1" options={periodOpts} /></div>
            <button data-testid="payslips-refresh" onClick={load} className="icon-button" title="Muat ulang"><RefreshCw size={15} /></button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
        <div className="section-card">
          <div className="grid grid-cols-[1.6fr_72px_1fr_1fr_1fr] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Karyawan</span><span>Periode</span><span className="text-right">Bruto</span><span className="text-right">Potongan</span><span className="text-right">Net</span>
          </div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="payslips-loading">Memuat...</div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="payslips-empty"><Receipt className="mx-auto mb-2 text-gray-300" size={28} /><p>Belum ada slip gaji. Buat & posting payroll run dulu.</p></div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
              {rows.map((s) => (
                <button key={s.id} data-testid={`payslip-row-${s.id}`} onClick={() => setSel(s)}
                  className={`w-full grid grid-cols-[1.6fr_72px_1fr_1fr_1fr] items-center px-3 py-2.5 text-left hover:bg-[#FAFBFC] ${sel?.id === s.id ? "bg-[#EEF4FF]" : ""}`}>
                  <span className="flex items-center gap-1 min-w-0"><EntityBadge entityId={s.entity_id} /><span className="text-[12px] font-semibold truncate">{s.employee_name}</span></span>
                  <span className="text-[11px] text-[#6B6B73]">{s.period}</span>
                  <span className="text-[11.5px] tabular-nums text-right text-[#0058CC]">{rp(s.gross)}</span>
                  <span className="text-[11.5px] tabular-nums text-right text-[#C0392B]">{rp((s.bpjs_emp_total || 0) + (s.pph21 || 0))}</span>
                  <span className="text-[11.5px] tabular-nums text-right font-bold text-[#1F7A45]">{rp(s.net)}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Detail slip */}
        <div className="section-card">
          {!sel ? (
            <div className="py-16 text-center text-[12px] text-[#6B6B73]" data-testid="payslip-detail-empty"><FileText className="mx-auto mb-2 text-gray-300" size={26} /><p>Pilih slip untuk rincian.</p></div>
          ) : (
            <div data-testid="payslip-detail">
              <div className="px-3 py-3 border-b border-[#EFF0F2]">
                <p className="text-[13px] font-bold flex items-center gap-1"><Building2 size={14} className="text-[#6B6B73]" /> {sel.employee_name}</p>
                <p className="text-[11px] text-[#6B6B73]">{sel.number} · {sel.period} · PTKP {sel.ptkp_status} · TER-{sel.ter_category}</p>
              </div>
              <div className="px-3 py-2">
                <p className="text-[10px] uppercase font-bold text-[#0058CC] mt-1">Penerimaan</p>
                <DRow label="Gaji Pokok" value={sel.base_salary} />
                <DRow label="Tunjangan" value={sel.allowances} />
                <DRow label="Lembur" value={sel.overtime} />
                {sel.commission > 0 && <DRow label="Komisi / Insentif" value={sel.commission} />}
                <DRow label="Bruto" value={sel.gross} strong color="#0058CC" />
                <p className="text-[10px] uppercase font-bold text-[#C0392B] mt-2">Potongan</p>
                <DRow label="BPJS Kesehatan" value={empB.kesehatan} />
                <DRow label="BPJS JHT" value={empB.jht} />
                <DRow label="BPJS JP" value={empB.jp} />
                <DRow label={`PPh 21 (${pct(sel.pph21_rate)})`} value={sel.pph21} />
                <DRow label="Total Potongan" value={(sel.bpjs_emp_total || 0) + (sel.pph21 || 0)} strong color="#C0392B" />
                <div className="mt-2 rounded-lg px-3 py-2 flex items-center justify-between" style={{ background: "#0058CC" }}>
                  <span className="text-[12px] font-bold text-white">Take-home (Net)</span>
                  <span className="text-[14px] font-bold text-white tabular-nums" data-testid="payslip-detail-net">{rp(sel.net)}</span>
                </div>
                <p className="text-[10px] uppercase font-bold text-[#6B6B73] mt-2">Kontribusi Perusahaan</p>
                <DRow label="BPJS (Kes+JHT+JP+JKK+JKM)" value={sel.bpjs_er_total} />
                <button data-testid="payslip-detail-pdf" disabled={busy} onClick={() => pdf(sel.id)} className="primary-button w-full justify-center mt-3"><FileText size={13} /> {busy ? "Membuka..." : "Unduh / Lihat PDF"}</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
