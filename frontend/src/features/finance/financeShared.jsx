/**
 * financeShared (FINANCE) — UI kit bersama untuk modul analitik keuangan baru
 * (Arus Kas, Profitabilitas, Proyeksi Kas, Anggaran, Control Tower).
 * Konsisten dgn gaya existing (section-card, #6B219A, recharts, formatCurrency).
 */
import { formatCurrency } from "../../utils/formatters";

export const FC = {
  revenue: "#1B7F4B", cogs: "#C77700", expense: "#C0392B", net: "#6B219A",
  margin: "#0F766E", cash: "#0058CC", inflow: "#1B7F4B", outflow: "#C0392B",
  purple: "#6B219A", purpleBg: "#F3EAFB", grid: "#EFF0F2", muted: "#8E8E93",
  ink: "#1C1C1E", amber: "#C77700", blue: "#0058CC", teal: "#0F766E",
};
export const PIE = ["#6B219A", "#0058CC", "#1B7F4B", "#C77700", "#0F766E", "#C0392B", "#8E44AD", "#2E86DE"];

export const NOW = new Date();
export const YEARS = Array.from({ length: 6 }, (_, i) => {
  const y = String(NOW.getFullYear() - i);
  return { value: y, label: y };
});
export const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

const pad = (n) => String(n).padStart(2, "0");
export const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export function compactIDR(v) {
  const n = Number(v || 0);
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(1)} M`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1)} jt`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(0)} rb`;
  return `${n}`;
}

export const entityParam = (se) => (se && se !== "all" ? { entity_id: se } : {});
export const fmtPct = (v, d = 1) => (v == null ? "—" : `${Number(v).toFixed(d)}%`);

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export const chartTooltip = {
  contentStyle: { fontSize: 12, borderRadius: 10, border: "1px solid #EFF0F2", boxShadow: "0 4px 14px rgba(0,0,0,.06)" },
};

/** KPI card modern: chip ikon + aksen gradien tipis. */
export function KpiCard({ label, value, icon: Icon, tone, sub, accent = "#6B219A", testId }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-[#EFF0F2] bg-white p-3.5" data-testid={testId}>
      <span className="absolute left-0 top-0 h-full w-1" style={{ background: accent }} />
      <div className="flex items-start gap-3 pl-1.5">
        {Icon && (
          <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
               style={{ background: `${accent}14` }}>
            <Icon size={17} style={{ color: accent }} />
          </div>
        )}
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`text-[17px] font-bold tabular-nums truncate ${tone || "text-[#1C1C1E]"}`}
             data-testid={testId ? `${testId}-value` : undefined}>{value}</p>
          {sub && <p className="text-[10px] text-[#9A9BA3] mt-0.5 truncate" title={sub}>{sub}</p>}
        </div>
      </div>
    </div>
  );
}

export function Panel({ title, icon: Icon, actions, children, testId, className = "" }) {
  return (
    <div className={`rounded-xl border border-[#EFF0F2] bg-white ${className}`} data-testid={testId}>
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-b border-[#F2F2F5]">
        {Icon && <Icon size={14} className="text-[#6B219A]" />}
        <h4 className="text-[12px] font-bold text-[#1C1C1E]">{title}</h4>
        {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      </div>
      <div className="p-3.5">{children}</div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, hint, testId }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-10" data-testid={testId}>
      {Icon && <Icon size={22} className="text-[#C7C7CC] mb-2" />}
      <p className="text-[12px] font-semibold text-[#1C1C1E]">{title}</p>
      {hint && <p className="text-[11px] text-[#8E8E93] mt-1 max-w-sm">{hint}</p>}
    </div>
  );
}

export function Progress({ pct, color = "#6B219A" }) {
  const w = Math.max(0, Math.min(100, Number(pct || 0)));
  return (
    <div className="h-1.5 rounded-full bg-[#F0F0F3] overflow-hidden">
      <div className="h-full rounded-full" style={{ width: `${w}%`, background: color }} />
    </div>
  );
}

export function Badge({ tone = "neutral", children, testId }) {
  const map = {
    ok: "bg-[#EAF6EF] text-[#1B7F4B]", warning: "bg-[#FBF3E5] text-[#C77700]",
    over: "bg-[#FDECEC] text-[#C0392B]", neutral: "bg-[#F2F2F5] text-[#6B6B73]",
    purple: "bg-[#F3EAFB] text-[#6B219A]",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${map[tone] || map.neutral}`}
          data-testid={testId}>{children}</span>
  );
}

export { formatCurrency };
