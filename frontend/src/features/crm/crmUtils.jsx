import { formatCurrency } from "../../utils/formatters";

/** Shared CRM helpers, pills, badges (KN_17). */
export const fmtDate = (iso) =>
  iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—";

export const currentPeriod = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

export const pct = (v) => `${Math.round((Number(v) || 0) * 100)}%`;

export function CreditStatusPill({ status, testId }) {
  const map = {
    active: ["pill-success", "Sehat"],
    warning: ["pill-warning", "Perhatian"],
    blocked: ["pill-danger", "Terblokir"],
  };
  const [cls, label] = map[status] || ["pill-muted", status || "—"];
  return <span className={`status-pill ${cls}`} data-testid={testId}>{label}</span>;
}

export function SegmentBadge({ segment }) {
  const map = {
    VIP: "pill-success",
    Distributor: "pill-info",
    Wholesale: "pill-info",
    Retail: "pill-muted",
  };
  return <span className={`status-pill ${map[segment] || "pill-muted"}`}>{segment || "Retail"}</span>;
}

export function OutcomePill({ outcome }) {
  const map = {
    paid: ["pill-success", "Lunas"],
    promised: ["pill-info", "Dijanjikan"],
    contacted: ["pill-muted", "Dihubungi"],
    no_response: ["pill-warning", "Tak Respon"],
    escalated: ["pill-danger", "Eskalasi"],
  };
  const [cls, label] = map[outcome] || ["pill-muted", outcome || "—"];
  return <span className={`status-pill ${cls}`}>{label}</span>;
}

export function KpiTile({ label, value, sub, tone, testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-white p-3" data-testid={testId}>
      <p className="text-[10.5px] uppercase font-semibold text-[#6B6B73] tracking-wide">{label}</p>
      <p className={`text-[18px] font-bold tabular-nums mt-0.5 ${tone || "text-[#1C1C1E]"}`}>{value}</p>
      {sub && <p className="text-[10.5px] text-[#9A9BA3] mt-0.5">{sub}</p>}
    </div>
  );
}

export function money(v) {
  return formatCurrency(Number(v) || 0);
}
