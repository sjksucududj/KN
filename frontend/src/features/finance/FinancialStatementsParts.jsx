// Presentational sub-components untuk FinancialStatementsView (dipisah agar file
// utama di bawah batas guardrail). Semua pure — hanya render dari props.
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";

function fmtDelta(v) {
  const n = Number(v || 0);
  if (Math.abs(n) < 0.005) return formatCurrency(0);
  const body = formatCurrency(Math.abs(n));
  return n > 0 ? `+${body}` : `-${body}`;
}

export function SectionBlock({ section }) {
  const hasLines = (section.lines || []).length > 0;
  return (
    <>
      <tr className="bg-[#FAF6FE] border-b border-[#EFF0F2]" data-testid={`fs-pl-section-${section.key}`}>
        <td className="px-3 py-2 font-bold text-[#1C1C1E]">{section.label}</td>
        <td className="px-3 py-2 text-right tabular-nums font-bold text-[#1C1C1E]" data-testid={`fs-pl-section-${section.key}-total`}>{formatCurrency(section.total)}</td>
      </tr>
      {hasLines ? section.lines.map((ln) => (
        <tr key={ln.code} className="border-b border-[#F5F5F7]">
          <td className="px-3 py-1.5 pl-6"><span className="font-mono text-[10px] text-[#9A9BA3] mr-1.5">{ln.code}</span>{ln.name}</td>
          <td className="px-3 py-1.5 text-right tabular-nums text-[#3C3C43]">{formatCurrency(ln.amount)}</td>
        </tr>
      )) : (
        <tr className="border-b border-[#F5F5F7]"><td className="px-3 py-1.5 pl-6 text-[11px] text-[#9A9BA3]" colSpan={2}>Tidak ada mutasi pada periode ini.</td></tr>
      )}
    </>
  );
}

export function SummaryRow({ label, value, extra, highlight }) {
  return (
    <tr className={`border-t-2 border-[#E4E4EA] ${highlight ? "bg-[#F3EAFB]" : "bg-[#FAFBFC]"}`}>
      <td className="px-3 py-2.5 font-bold text-[#1C1C1E]">{label}{extra ? <span className="ml-2 text-[10px] font-normal text-[#9A9BA3]">{extra}</span> : null}</td>
      <td className={`px-3 py-2.5 text-right tabular-nums font-bold ${highlight ? "text-[#6B219A]" : (value ?? 0) >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}>{formatCurrency(value)}</td>
    </tr>
  );
}

export function GroupHeader({ label, isComp }) {
  return (
    <tr className="bg-[#F0EAFB] border-b border-[#D9C4EC]">
      <td className="px-3 py-2 font-bold text-[11px] uppercase tracking-wide text-[#6B219A]" colSpan={isComp ? 4 : 2}>{label}</td>
    </tr>
  );
}

export function BsSection({ section, isComp }) {
  return (
    <>
      <tr className="bg-[#FAF6FE] border-b border-[#F5F5F7]">
        <td className="px-3 py-1.5 pl-5 font-semibold text-[#3C3C43]">{section.label}</td>
        <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{formatCurrency(section.total)}</td>
        {isComp && <td className="px-3 py-1.5 text-right tabular-nums font-semibold text-[#6B6B73]">{formatCurrency(section.compare_total)}</td>}
        {isComp && <td className="px-3 py-1.5 text-right tabular-nums font-semibold text-[#6B6B73]">{fmtDelta(section.delta)}</td>}
      </tr>
      {(section.lines || []).map((ln) => <BsLine key={ln.code} line={ln} isComp={isComp} indent />)}
    </>
  );
}

export function BsLine({ line, isComp, indent }) {
  const delta = Number(line.delta || 0);
  return (
    <tr className="border-b border-[#F5F5F7]" data-testid={line.code ? `fs-bs-line-${line.code}` : undefined}>
      <td className={`px-3 py-1.5 ${indent ? "pl-8" : "pl-5"}`}>
        {line.code ? <span className="font-mono text-[10px] text-[#9A9BA3] mr-1.5">{line.code}</span> : null}{line.name}
      </td>
      <td className="px-3 py-1.5 text-right tabular-nums text-[#3C3C43]">{formatCurrency(line.amount)}</td>
      {isComp && <td className="px-3 py-1.5 text-right tabular-nums text-[#9A9BA3]">{formatCurrency(line.compare_amount)}</td>}
      {isComp && <td className={`px-3 py-1.5 text-right tabular-nums ${delta > 0 ? "text-[#1B7F4B]" : delta < 0 ? "text-[#C0392B]" : "text-[#9A9BA3]"}`}>{fmtDelta(line.delta)}</td>}
    </tr>
  );
}

export function BsTotalRow({ label, value, compare, isComp, testId }) {
  return (
    <tr className="bg-[#FAFBFC] border-b border-[#E4E4EA] font-bold">
      <td className="px-3 py-2 text-[#1C1C1E]">{label}</td>
      <td className="px-3 py-2 text-right tabular-nums" data-testid={testId}>{formatCurrency(value)}</td>
      {isComp && <td className="px-3 py-2 text-right tabular-nums text-[#6B6B73]">{formatCurrency(compare)}</td>}
      {isComp && <td className="px-3 py-2 text-right tabular-nums text-[#6B6B73]">{fmtDelta((value ?? 0) - (compare ?? 0))}</td>}
    </tr>
  );
}

export function Labeled({ label, children }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</span>
      {children}
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

export function BalancedKpi({ balanced }) {
  const ok = balanced !== false;
  return (
    <div className="section-card" data-testid="fs-bs-kpi-balanced">
      <div className="section-body flex items-center gap-3 py-3">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${ok ? "bg-[#E6F6EC]" : "bg-[#FDEDE7]"}`}>
          {ok ? <CheckCircle2 size={17} className="text-[#1B7F4B]" /> : <AlertTriangle size={17} className="text-[#C0392B]" />}
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Status Neraca</p>
          <p className={`text-[17px] font-bold truncate ${ok ? "text-[#1B7F4B]" : "text-[#C0392B]"}`} data-testid="fs-bs-kpi-balanced-value">{ok ? "Seimbang" : "Tidak Seimbang"}</p>
        </div>
      </div>
    </div>
  );
}
