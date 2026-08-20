/**
 * PendingSoTab (F2b) — Papan Pending SO: backorder aktif yang dijanjikan dari
 * incoming PO **maupun pembelian internal antar-PT** (E9.2). Menampilkan coverage
 * (covered/partial/uncovered) + promise date + PT sebelah yang menjanjikan barangnya.
 * Sumber: GET /api/stock/pending-so. Read-only.
 */
import { Building2, Clock, PackageSearch, TruckIcon } from "lucide-react";
import EntityBadge from "../../components/EntityBadge";
import { formatQty } from "../../utils/formatters";

const COVERAGE = {
  covered: { label: "Terjamin", tone: "bg-[#E6F6EC] text-[#1B7F4B] border-[#BDE5CC]" },
  partial: { label: "Sebagian", tone: "bg-[#FFF3DC] text-[#9A6700] border-[#EFD9A8]" },
  uncovered: { label: "Belum Ada Suplai", tone: "bg-[#FDEDE7] text-[#C0392B] border-[#F3C9BD]" },
};

function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return s;
  }
}

export default function PendingSoTab({ rows = [], entities = [], loading = false }) {
  if (loading) {
    return (
      <div className="grid gap-2" data-testid="sb-pending-loading">
        {[0, 1, 2].map((i) => <div key={i} className="h-12 bg-[#F5F5F7] rounded animate-pulse" />)}
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div data-testid="sb-pending-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
        <PackageSearch size={26} className="mx-auto mb-2 text-gray-300" />
        Tidak ada SO Menunggu. Semua permintaan terpenuhi dari stok.
      </div>
    );
  }
  return (
    <div className="overflow-auto rounded-md border border-[#EFF0F2]" data-testid="sb-pending-list">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
            <th className="px-3 py-2">SO / Pelanggan</th>
            <th className="px-3 py-2">Produk</th>
            <th className="px-3 py-2">Pemilik</th>
            <th className="px-3 py-2 text-right">Backorder</th>
            <th className="px-3 py-2">Suplai (Incoming)</th>
            <th className="px-3 py-2">Janji (ETA)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const cov = COVERAGE[r.coverage] || COVERAGE.uncovered;
            return (
              <tr key={r.backorder_id || `${r.order_id}-${r.product_id}`}
                  data-testid={`sb-pending-row-${r.order_id}-${r.product_id}`}
                  className="border-b border-[#F5F5F7] last:border-0 align-top">
                <td className="px-3 py-2">
                  <span className="font-semibold text-[#1C1C1E]">{r.order_number || r.order_id}</span>
                  <span className="block text-[11px] text-[#6B6B73]">{r.customer_name}{r.customer_city ? ` · ${r.customer_city}` : ""}</span>
                </td>
                <td className="px-3 py-2">
                  <span className="font-medium text-[#1C1C1E]">{r.product_name}</span>
                  <span className="block text-[10px] font-mono text-[#9A9BA3]">{r.sku}</span>
                </td>
                <td className="px-3 py-2"><EntityBadge entityId={r.owner_entity_id} entities={entities} /></td>
                <td className="px-3 py-2 text-right">
                  <span className="tabular-nums font-bold text-[#C0392B]">{formatQty(r.backorder_qty)}</span>
                  <span className="text-[10px] text-[#9A9BA3]"> {r.unit}</span>
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center gap-1 text-[10px] rounded px-1.5 py-0.5 border ${cov.tone}`}>
                    <TruckIcon size={11} /> {cov.label}
                  </span>
                  <span className="block text-[10px] text-[#6B6B73] mt-0.5 tabular-nums">
                    incoming {formatQty(r.incoming_total)}{r.uncovered_qty > 0 ? ` · kurang ${formatQty(r.uncovered_qty)}` : ""}
                  </span>
                  {/* E9.2 — sebut PT sebelah yang menjanjikan barangnya, supaya tidak
                      ada permintaan beli kedua untuk barang yang sudah di jalan. */}
                  {(r.interco_promises || []).map((ic) => (
                    <span key={ic.interco_id}
                          data-testid={`sb-pending-interco-${r.order_id}-${ic.interco_id}`}
                          className="mt-1 flex items-center gap-1 text-[10px] text-[#0F6B52] bg-[#E6F7F1] border border-[#BDE5CC] rounded px-1.5 py-0.5 w-fit">
                      <Building2 size={10} />
                      {formatQty(ic.qty)} dari {ic.from_entity_name || "PT lain"} lewat {ic.interco_number}
                    </span>
                  ))}
                </td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1 text-[11px] text-[#0058CC] font-medium">
                    <Clock size={12} /> {fmtDate(r.promise_date)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
