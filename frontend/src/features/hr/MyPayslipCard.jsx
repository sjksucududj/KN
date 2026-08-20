import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Wallet, FileText } from "lucide-react";
import { rp, openPayslipPdf } from "./payrollUtils";

// ESS — kartu Slip Gaji Terakhir (menggantikan placeholder H4).
export function MyPayslipCard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => { load(); }, []);
  async function load() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/payslips/me`); setData(r.data || null); }
    catch (_) { /* noop */ } finally { setLoading(false); }
  }
  async function openPdf(id) {
    setBusy(true);
    try { await openPayslipPdf(id); } catch (_) { /* noop */ } finally { setBusy(false); }
  }

  const slips = data?.payslips || [];
  const latest = slips[0];
  return (
    <div className="section-card !p-4" data-testid="ess-payslip-card">
      <div className="flex items-center gap-2 mb-2"><Wallet size={15} className="text-[#0058CC]" /><h3 className="text-[12.5px] font-bold">Slip Gaji Terakhir</h3></div>
      {loading ? (
        <p className="text-[12px] text-[#6B6B73] py-3" data-testid="ess-payslip-loading">Memuat...</p>
      ) : !latest ? (
        <p className="text-[12px] text-[#6B6B73] py-3" data-testid="ess-payslip-empty">Belum ada slip gaji terbit.</p>
      ) : (
        <div data-testid="ess-payslip-latest">
          <p className="text-[11px] text-[#6B6B73]">Periode {latest.period}</p>
          <p className="text-[20px] font-bold tabular-nums text-[#0058CC] leading-tight">{rp(latest.net)}</p>
          <p className="text-[10.5px] text-[#6B6B73]">Take-home pay</p>
          <button data-testid="ess-payslip-pdf" disabled={busy} onClick={() => openPdf(latest.id)}
            className="primary-button w-full justify-center mt-2 !py-1.5"><FileText size={13} /> {busy ? "Membuka..." : "Lihat Slip (PDF)"}</button>
          {slips.length > 1 && <p className="text-[10.5px] text-[#6B6B73] mt-1 text-center">{slips.length} slip tersedia</p>}
        </div>
      )}
    </div>
  );
}
