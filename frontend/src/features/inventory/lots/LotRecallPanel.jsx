/**
 * LotRecallPanel (FASE C · keputusan pemilik 5d) — laporan dampak penarikan.
 * Dari satu lot → seluruh roll (termasuk lot turunan hasil split/rework) → SO →
 * pengiriman → pelanggan + kontak, agar tim bisa menindak cepat.
 */
import { AlertOctagon, Phone, Truck } from "lucide-react";
import { formatQty } from "../../../utils/formatters";
import { shortDate } from "./lotApi";

export default function LotRecallPanel({ data, loading }) {
  if (loading) {
    return <p data-testid="lot-recall-loading" className="py-6 text-center text-[11px] text-[#6B6B73]">Menghitung dampak…</p>;
  }
  if (!data) {
    return <p data-testid="lot-recall-empty" className="py-6 text-center text-[11px] text-[#6B6B73]">Belum ada data recall.</p>;
  }
  const t = data.totals || {};
  const cards = [
    { k: "Lot dalam cakupan", v: t.lots ?? 0, s: "termasuk lot turunan" },
    { k: "Roll terdampak", v: t.rolls ?? 0, s: `sisa ${formatQty(t.qty_remaining)}` },
    { k: "Pesanan (SO)", v: t.orders ?? 0, s: "pesanan menyentuh lot ini" },
    { k: "Pengiriman", v: t.shipments ?? 0, s: `keluar ${formatQty(t.qty_dispatched)}` },
    { k: "Pelanggan", v: t.customers ?? 0, s: "perlu dihubungi" },
  ];
  return (
    <div data-testid="lot-recall" className="space-y-2">
      <div className="flex items-center gap-1.5 rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1.5">
        <AlertOctagon size={12} className="text-rose-600" />
        <span className="text-[10.5px] text-rose-700">
          Laporan ini <b>tidak mengubah data</b>. Gunakan untuk memutuskan penarikan barang atau
          pemberitahuan pelanggan bila ditemukan masalah mutu/warna pada lot.
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
        {cards.map((c) => (
          <div key={c.k} data-testid={`lot-recall-stat-${c.k}`}
            className="rounded-md border border-[#EFF0F2] bg-white px-2.5 py-2">
            <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{c.k}</p>
            <p className="text-[16px] font-bold tabular-nums">{c.v}</p>
            <p className="text-[10px] text-[#8E8E93]">{c.s}</p>
          </div>
        ))}
      </div>

      <div className="rounded-md border border-[#EFF0F2] bg-white">
        <div className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          Pelanggan terdampak (hubungi lebih dulu)
        </div>
        <div className="divide-y divide-[#F5F5F7]" data-testid="lot-recall-customers">
          {(data.customers || []).length === 0 && (
            <p className="px-2.5 py-2 text-[10.5px] text-[#8E8E93]">
              Belum ada pelanggan terdampak — barang lot ini belum terjual/terkirim.
            </p>
          )}
          {(data.customers || []).map((c) => (
            <div key={c.customer_id || c.customer_name}
              data-testid={`lot-recall-customer-${c.customer_id || c.customer_name}`}
              className="flex flex-wrap items-center gap-2 px-2.5 py-1.5 text-[10.5px]">
              <span className="font-semibold">{c.customer_name || "(tanpa nama)"}</span>
              {c.city && <span className="text-[#8E8E93]">{c.city}</span>}
              {c.contact_person && <span className="text-[#6B6B73]">{c.contact_person}</span>}
              {c.phone && (
                <span className="flex items-center gap-1 text-[#0058CC]">
                  <Phone size={10} /> {c.phone}
                </span>
              )}
              <span className="ml-auto text-[#6B6B73]">{c.order_count} pesanan: {(c.orders || []).join(", ")}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <div className="rounded-md border border-[#EFF0F2] bg-white">
          <div className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
            Pesanan (SO)
          </div>
          <div className="divide-y divide-[#F5F5F7]" data-testid="lot-recall-orders">
            {(data.orders || []).length === 0 && (
              <p className="px-2.5 py-2 text-[10.5px] text-[#8E8E93]">Tidak ada pesanan.</p>
            )}
            {(data.orders || []).map((o) => (
              <div key={o.id} className="flex items-center gap-2 px-2.5 py-1.5 text-[10.5px]">
                <span className="font-semibold">{o.number}</span>
                <span className="status-pill pill-muted">{o.sub_status || o.status}</span>
                <span className="text-[#6B6B73]">{o.customer_name}</span>
                <span className="ml-auto text-[#8E8E93]">{shortDate(o.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-md border border-[#EFF0F2] bg-white">
          <div className="flex items-center gap-1.5 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
            <Truck size={12} className="text-[#0058CC]" />
            <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Pengiriman</span>
          </div>
          <div className="divide-y divide-[#F5F5F7]" data-testid="lot-recall-shipments">
            {(data.shipments || []).length === 0 && (
              <p className="px-2.5 py-2 text-[10.5px] text-[#8E8E93]">Belum ada pengiriman.</p>
            )}
            {(data.shipments || []).map((sh) => (
              <div key={sh.id} className="flex items-center gap-2 px-2.5 py-1.5 text-[10.5px]">
                <span className="font-semibold">{sh.shipment_no}</span>
                <span className="text-[#6B6B73]">{sh.order_number}</span>
                <span className="status-pill pill-muted">{sh.status}</span>
                <span className="ml-auto tabular-nums text-[#6B6B73]">
                  {formatQty(sh.qty)} {sh.unit}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
