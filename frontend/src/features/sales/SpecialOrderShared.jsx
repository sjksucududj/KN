/** Shared helpers & components for the Special Order feature. */
import { CheckCircle2, Clock, Package, XCircle } from "lucide-react";

export function fmtNum(n, d = 0) {
  return new Intl.NumberFormat("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n || 0);
}

export function fmtDate(s) {
  if (!s) return "-";
  return new Date(s).toLocaleDateString("id-ID", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export const STATUS_STYLE = {
  draft:             { cls: "pill-muted",   label: "Draf", icon: Clock },
  pending_approval:  { cls: "pill-warning", label: "Menunggu Persetujuan", icon: Clock },
  confirmed:         { cls: "pill-info",    label: "Terkonfirmasi", icon: CheckCircle2 },
  in_production:     { cls: "pill-purple",  label: "Dalam Produksi", icon: Package },
  ready:             { cls: "pill-success", label: "Siap", icon: CheckCircle2 },
  shipped:           { cls: "pill-primary", label: "Shipped", icon: Package },
  done:              { cls: "pill-success", label: "Selesai", icon: CheckCircle2 },
  cancelled:         { cls: "pill-danger",  label: "Dibatalkan", icon: XCircle },
};

export function StatusPill({ status }) {
  const s = STATUS_STYLE[status] || { cls: "pill-muted", label: status, icon: Clock };
  const Icon = s.icon;
  return (
    <span className={`status-pill ${s.cls}`} data-testid={`so-status-pill-${status}`}>
      <Icon size={11} /> {s.label}
    </span>
  );
}
