/**
 * poUtils.jsx — shared helpers untuk PurchaseOrderManagement sub-komponen.
 */

export function getStatusBadge(status) {
  const statusMap = {
    waiting_approval: { label: "Menunggu Persetujuan", cls: "bg-amber-100 text-amber-700" },
    pending:          { label: "Menunggu",           cls: "bg-yellow-100 text-yellow-700" },
    receiving:        { label: "Penerimaan",         cls: "bg-blue-100 text-blue-700" },
    completed:        { label: "Selesai",         cls: "bg-green-100 text-green-700" },
    partial:          { label: "Partial",           cls: "bg-orange-100 text-orange-700" },
    cancelled:        { label: "Dibatalkan",         cls: "bg-gray-200 text-gray-500" },
    rejected:         { label: "Ditolak",          cls: "bg-red-100 text-red-700" },
    closed_short:     { label: "Closed (Short)",     cls: "bg-stone-200 text-stone-600" },
  };
  const b = statusMap[status] || { label: status, cls: "bg-gray-200 text-gray-700" };
  return (
    <span data-testid={`po-status-badge-${status}`} className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${b.cls}`}>
      {b.label}
    </span>
  );
}

export function getPaymentBadge(status) {
  const map = {
    unpaid:  { label: "Belum Bayar", cls: "bg-red-50 text-red-600 border border-red-200" },
    partial: { label: "Sebagian",    cls: "bg-amber-50 text-amber-700 border border-amber-200" },
    paid:    { label: "Lunas",       cls: "bg-green-50 text-green-700 border border-green-200" },
  };
  const b = map[status] || { label: status || "—", cls: "bg-gray-100 text-gray-600" };
  return (
    <span data-testid={`po-payment-badge-${status}`} className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${b.cls}`}>
      {b.label}
    </span>
  );
}
