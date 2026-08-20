/** transferConstants — status badge map + StatusBadge component for transfers. */
const STATUS_MAP = {
  draft: { label: "Draf", className: "bg-gray-200 text-gray-700" },
  waiting_approval: { label: "Menunggu Persetujuan", className: "bg-yellow-100 text-yellow-700" },
  approved: { label: "Disetujui", className: "bg-blue-100 text-blue-700" },
  picking: { label: "Pengambilan", className: "bg-purple-100 text-purple-700" },
  staging: { label: "Staging", className: "bg-indigo-100 text-indigo-700" },
  dispatched: { label: "Terkirim", className: "bg-orange-100 text-orange-700" },
  completed: { label: "Selesai", className: "bg-green-100 text-green-700" },
  rejected: { label: "Ditolak", className: "bg-red-100 text-red-700" },
  cancelled: { label: "Dibatalkan", className: "bg-gray-300 text-gray-600" },
};

export function statusLabel(status) {
  return STATUS_MAP[status]?.label || status;
}

export function StatusBadge({ status }) {
  const badge = STATUS_MAP[status] || { label: status, className: "bg-gray-200 text-gray-700" };
  return (
    <span data-testid="transfer-status-badge" className={`rounded-full px-3 py-1 text-xs font-semibold ${badge.className}`}>
      {badge.label}
    </span>
  );
}
