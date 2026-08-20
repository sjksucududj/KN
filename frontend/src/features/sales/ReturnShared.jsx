/** Shared components for the Returns feature. */
const RETURN_TYPE_LABEL = {
  retur:       "Retur",
  bs:          "Barang Sisa (BS)",
  penggantian: "Penggantian",
  komplain:    "Komplain",
  garansi:     "Garansi",
};
const STATUS_STYLE = {
  draft:            { cls: "pill-muted",   label: "Draf" },
  pending_approval: { cls: "pill-warning", label: "Menunggu Persetujuan" },
  approved:         { cls: "pill-warning", label: "Disetujui" },
  inspecting:       { cls: "pill-warning", label: "Inspeksi" },
  inspected:        { cls: "pill-warning", label: "Selesai Inspeksi" },
  refund_settled:   { cls: "pill-success", label: "Pengembalian Dana" },
  credit_settled:   { cls: "pill-success", label: "Store Credit" },
  nego_settled:     { cls: "pill-success", label: "Nego" },
  rejected:         { cls: "pill-danger",  label: "Ditolak" },
  cancelled:        { cls: "pill-muted",   label: "Dibatalkan" },
};
export const OUTCOME_LABEL = {
  refund: "Refund", store_credit: "Store Credit (potong bon)",
  nego: "Nego (diskon)", reject: "Tolak",
};
export function fmtNum(n, d = 1) {
  return new Intl.NumberFormat("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n || 0);
}
export function fmtDate(s) {
  if (!s) return "-";
  return new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
}
export function ReturnStatusPill({ status }) {
  const s = STATUS_STYLE[status] || { cls: "pill-muted", label: status };
  return <span className={`status-pill ${s.cls}`} data-testid={`return-status-pill-${status}`}>{s.label}</span>;
}
export function ReturnTypeBadge({ type }) {
  const colors = {
    retur: "badge-blue", bs: "badge-orange", penggantian: "badge-purple",
    komplain: "badge-red", garansi: "badge-teal",
  };
  return (
    <span className={`feature-badge ${colors[type] || "badge-muted"}`} data-testid={`return-type-badge-${type}`}>
      {RETURN_TYPE_LABEL[type] || type}
    </span>
  );
}
