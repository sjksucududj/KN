// OrderFulfillmentBadges — ringkas: metode pemenuhan (Ambil/Kirim + tanggal)
// dan tim sales per order (PIC + co-sales + split insentif). Dipisah dari
// OrderDetailPanel agar file utama tetap di bawah batas guardrail.
import { PackageCheck, Truck, Users } from "lucide-react";

export default function OrderFulfillmentBadges({ order: sel }) {
  const team = Array.isArray(sel?.sales_team) ? sel.sales_team : [];
  return (
    <>
      {sel?.fulfillment_method === "ambil" ? (
        <div data-testid="order-pickup-badge" className="flex items-center gap-2 rounded-md border border-[#CDE3FF] bg-[#EFF4FF] px-2.5 py-1.5 text-[11px] text-[#0058CC]">
          <PackageCheck size={13} />
          <span>Ambil di Gudang{sel.pickup_date ? ` · ${sel.pickup_date}` : ""} — pengambilan ditahan sampai tanggal ambil</span>
        </div>
      ) : sel?.delivery_date ? (
        <div data-testid="order-delivery-badge" className="flex items-center gap-2 rounded-md border border-[#CDE3FF] bg-[#EFF4FF] px-2.5 py-1.5 text-[11px] text-[#0058CC]">
          <Truck size={13} />
          <span>Dikirim · request tanggal pengiriman {sel.delivery_date}</span>
        </div>
      ) : null}

      {team.length > 0 && (
        <div data-testid="order-sales-team" className="flex items-start gap-2 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[11px] text-[#3C3C43]">
          <Users size={13} className="mt-0.5 shrink-0 text-[#0058CC]" />
          <span>
            <span className="font-semibold text-[#6B6B73]">Tim Sales (pesanan ini): </span>
            {team.map((m, i) => (
              <span key={i} data-testid={`order-sales-team-member-${i}`}>
                {i > 0 ? " · " : ""}{m.name || m.sales_id}{m.role === "pic" ? " (PIC)" : ""} {Number(m.split_pct || 0)}%
              </span>
            ))}
          </span>
        </div>
      )}
    </>
  );
}
