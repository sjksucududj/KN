/** WarehouseStructure — collapsible Zone · Rack · Bin overview per warehouse. */
import { MapPin } from "lucide-react";

export default function WarehouseStructure({ warehouses = [], loading = false }) {
  if (loading) {
    return (
      <div data-testid="warehouse-structure-loading" className="rounded-xl border border-[#EFF0F2] bg-white p-3 text-[12px] text-[#6B6B73]">
        Memuat struktur gudang…
      </div>
    );
  }
  if (warehouses.length === 0) return null;
  return (
    <details data-testid="warehouse-structure" className="rounded-xl border border-[#EFF0F2] bg-white overflow-hidden">
      <summary className="px-3 py-2 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73] cursor-pointer select-none hover:bg-[#FAFBFC] flex items-center gap-2">
        <MapPin size={12} /> Struktur Gudang (Zone · Rack · Bin)
      </summary>
      <div className="border-t border-[#EFF0F2] p-3 grid gap-3 lg:grid-cols-3">
        {warehouses.map(wh => {
          // Dukung 2 skema: rack.bins (lama) & rack.levels[].bins (baru, Fase B)
          const bins = (wh.zones || []).flatMap(z =>
            (z.racks || []).flatMap(r =>
              (Array.isArray(r.levels) && r.levels.length)
                ? r.levels.flatMap(l => l.bins || [])
                : (r.bins || [])
            )
          );
          return (
            <div key={wh.id} className="rounded-md border border-[#EFF0F2] p-2.5">
              <p className="text-[10px] font-bold uppercase text-[#0058CC] mb-1">{wh.code} — {wh.name}</p>
              {bins.length === 0 ? (
                <p className="text-[10px] text-[#8E8E93]">Belum ada bin.</p>
              ) : (
                <div className="grid grid-cols-3 gap-1">
                  {bins.map(bin => (
                    <div key={bin.id} className="rounded border border-[#EFF0F2] bg-[#FAFBFC] px-1.5 py-1">
                      <p className="text-[10px] font-semibold">{bin.code || bin.id || "-"}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}
