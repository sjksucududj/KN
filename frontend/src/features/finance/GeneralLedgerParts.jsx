// Presentational KPI cards untuk GeneralLedger (dipisah agar file utama di bawah
// batas guardrail). Pure — render dari props.
import { CheckCircle2, AlertTriangle } from "lucide-react";

export function BalancedKpi({ balanced }) {
  const ok = balanced !== false;
  return (
    <div className="section-card" data-testid="gl-kpi-balanced">
      <div className="section-body flex items-center gap-3 py-3">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${ok ? "bg-[#E6F6EC]" : "bg-[#FDEDE7]"}`}>
          {ok ? <CheckCircle2 size={17} className="text-[#1B7F4B]" /> : <AlertTriangle size={17} className="text-[#C0392B]" />}
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Status Buku</p>
          <p className={`text-[17px] font-bold truncate ${ok ? "text-[#1B7F4B]" : "text-[#C0392B]"}`} data-testid="gl-kpi-balanced-value">{ok ? "Seimbang" : "Tidak Seimbang"}</p>
        </div>
      </div>
    </div>
  );
}

export function Kpi({ label, value, icon: Icon, tone = "", testId }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="w-9 h-9 rounded-lg bg-[#F3EAFB] flex items-center justify-center"><Icon size={17} className="text-[#6B219A]" /></div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`text-[17px] font-bold tabular-nums truncate ${tone || "text-[#1C1C1E]"}`} data-testid={`${testId}-value`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
