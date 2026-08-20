// Badge + MiniBar untuk OutboundScanInterface (dipisah agar file utama di bawah
// batas guardrail). Pure presentational.

const STATUS_MAP = {
  scheduled:  { label: "Terjadwal", cls: "bg-purple-100 text-purple-700" },
  created:    { label: "Created", cls: "bg-gray-100 text-gray-600" },
  picking:    { label: "Pengambilan", cls: "bg-blue-100 text-blue-700" },
  packing:    { label: "Pengemasan", cls: "bg-purple-100 text-purple-700" },
  staging:    { label: "Staging", cls: "bg-indigo-100 text-indigo-700" },
  partially_shipped: { label: "Terkirim Sebagian", cls: "bg-orange-100 text-orange-700" },
  dispatched: { label: "Terkirim", cls: "bg-green-100 text-green-700" },
  escalated:  { label: "Escalated", cls: "bg-red-100 text-red-700" },
};

export function Badge({ status }) {
  const s = STATUS_MAP[status] || { label: status, cls: "bg-gray-100 text-gray-600" };
  return <span data-testid={`outbound-status-badge-${status}`} className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold ${s.cls}`}>{s.label}</span>;
}

export function MiniBar({ pct, status }) {
  const color = status === 'dispatched' ? 'bg-[#34C759]' : status === 'escalated' ? 'bg-red-400' : 'bg-[#FF9500]';
  return (
    <div className="h-1 w-full rounded-full bg-gray-200 overflow-hidden">
      <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
}
