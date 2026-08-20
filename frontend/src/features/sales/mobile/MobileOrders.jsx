import { useMemo, useState } from "react";
import { ClipboardList, Search, PackageX, ChevronDown } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import { StagePill, SubStatusChips } from "../../../components/SoStatusBadges";

const FILTERS = [
  { id: "all", label: "Semua" },
  { id: "active", label: "Aktif" },
  { id: "done", label: "Selesai" },
  { id: "cancelled", label: "Batal" },
];
const ACTIVE = ["reserved", "waiting_approval", "approved", "confirmed", "partially_picked", "picked", "partially_shipped", "shipped", "dispatched"];

export default function MobileOrders({ orders = [], loading, onBrowse }) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState(null);

  const list = useMemo(() => {
    const term = q.toLowerCase().trim();
    return orders.filter((o) => {
      if (filter === "active" && !ACTIVE.includes(o.status)) return false;
      if (filter === "done" && o.status !== "done" && o.status !== "delivered") return false;
      if (filter === "cancelled" && !["cancelled", "expired"].includes(o.status)) return false;
      if (!term) return true;
      return [o.number, o.customer_name].filter(Boolean).join(" ").toLowerCase().includes(term);
    });
  }, [orders, q, filter]);

  return (
    <div data-testid="mobile-orders">
      <div className="mb-2 flex items-center gap-2">
        <ClipboardList size={16} className="text-[#0058CC]" />
        <h2 className="m-section-title">Pesanan Saya</h2>
      </div>

      <div className="mb-2.5 flex items-center gap-2 rounded-xl bg-white px-3 py-2 border border-[#EFF0F2]">
        <Search size={15} className="text-[#8E8E93]" />
        <input data-testid="mobile-orders-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nomor / pelanggan…"
          className="w-full bg-transparent text-[13px] outline-none placeholder:text-[#8E8E93]" />
      </div>

      <div className="no-scrollbar mb-3 flex gap-2 overflow-x-auto">
        {FILTERS.map((f) => (
          <button key={f.id} data-testid={`mobile-orders-filter-${f.id}`} onClick={() => setFilter(f.id)}
            className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-[12px] font-semibold transition ${filter === f.id ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3A3A3C]"}`}>
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2.5">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-20 animate-pulse rounded-xl bg-[#ECEDF0]" />)}</div>
      ) : list.length === 0 ? (
        <div data-testid="mobile-orders-empty" className="flex flex-col items-center gap-3 py-20 text-center m-muted">
          <PackageX size={32} className="text-[#C7C7CC]" />
          <p className="text-[13px] font-medium text-[#1C1C1E]">Belum ada pesanan.</p>
          <button onClick={onBrowse} className="primary-button mt-1 px-5 py-2.5">Buat Pesanan</button>
        </div>
      ) : (
        <div className="space-y-2.5">
          {list.map((o) => {
            const total = o.grand_total ?? o.total_amount ?? 0;
            const isOpen = open === o.id;
            return (
              <div key={o.id} data-testid={`mobile-order-${o.id}`} className="m-card overflow-hidden">
                <button className="m-press flex w-full items-center gap-3 p-3 text-left" onClick={() => setOpen(isOpen ? null : o.id)}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[12.5px] font-bold text-[#0058CC]">{o.number}</span>
                      <StagePill order={o} testId={`mobile-order-stage-${o.id}`} />
                    </div>
                    <p className="mt-0.5 truncate text-[11.5px] text-[#3C3C43]">{o.customer_name}</p>
                    <SubStatusChips order={o} testIdPrefix={`mobile-order-sub-${o.id}`} className="mt-0.5" />
                    <p className="mt-0.5 text-[10.5px] m-muted">{(o.items || []).length} item • {o.payment_status === "paid" ? <span className="text-[#1A7A3A]">Lunas</span> : "Belum bayar"}</p>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="text-[13px] font-bold tabular-nums">{formatCurrency(total)}</span>
                    <ChevronDown size={15} className={`mt-1 text-[#8E8E93] transition-transform ${isOpen ? "rotate-180" : ""}`} />
                  </div>
                </button>
                {isOpen && (
                  <div data-testid={`mobile-order-detail-${o.id}`} className="border-t border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2.5">
                    {(o.items || []).map((it, i) => (
                      <div key={i} className="flex items-center justify-between py-1 text-[12px]">
                        <span className="min-w-0 flex-1 truncate text-[#3C3C43]">{it.product_name || it.name} <span className="m-muted">× {it.quantity}</span></span>
                        <span className="tabular-nums font-semibold">{formatCurrency((it.price || it.unit_price || 0) * (it.quantity || 0))}</span>
                      </div>
                    ))}
                    <div className="mt-1.5 flex items-center justify-between border-t border-[#EFF0F2] pt-1.5 text-[12.5px] font-bold">
                      <span>Total</span>
                      <span className="tabular-nums text-[#0058CC]">{formatCurrency(total)}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
