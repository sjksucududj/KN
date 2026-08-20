/** InventorySummaryCards — KPI row for the Stock tab. */
import { Layers, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import { formatQty } from "./inventoryConstants";

export default function InventorySummaryCards({ totalOnHand, totalAvail, totalReserved, lowCount }) {
  const cards = [
    { label: "Total Stok Fisik", value: formatQty(totalOnHand),   icon: Layers,        color: "text-[#007AFF]", bg: "bg-[#EFF4FF]" },
    { label: "Tersedia",     value: formatQty(totalAvail),    icon: TrendingUp,    color: "text-[#34C759]", bg: "bg-green-50" },
    { label: "Dipesan",      value: formatQty(totalReserved), icon: TrendingDown,  color: "text-[#FF9500]", bg: "bg-orange-50" },
    { label: "Stok Rendah",   value: lowCount,                 icon: AlertTriangle, color: "text-red-500",   bg: "bg-red-50" },
  ];
  return (
    <div data-testid="inventory-summary-cards" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {cards.map(({ label, value, icon: Icon, color, bg }) => (
        <div key={label} data-testid={`summary-card-${label.toLowerCase().replace(/\s+/g, "-")}`} className={`rounded-xl border border-[#EFF0F2] p-3 flex items-center gap-2.5 ${bg}`}>
          <div className={`rounded-lg p-1.5 ${bg}`}>
            <Icon size={16} className={color} />
          </div>
          <div>
            <p className="text-[10px] text-[#6B6B73] font-semibold uppercase">{label}</p>
            <p className={`text-[16px] font-bold leading-tight tabular-nums ${color}`}>{value}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
