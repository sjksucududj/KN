/** RollsTable — daftar roll fisik (Roll-as-SSOT, Fase 0.5) + Pegging (Sub-fase 1.7). */
import { Layers, Anchor } from "lucide-react";
import { formatQty, RollStatusBadge } from "./inventoryConstants";

export default function RollsTable({ loading, rolls = [], canPeg = false, onPeg, onUnpeg, busyRollId = null }) {
  return (
    <div className="bg-white rounded-xl border border-[#EFF0F2] overflow-hidden" data-testid="rolls-table">
      <div className="overflow-x-auto">
        <table className="w-full text-[11.5px]">
          <thead>
            <tr className="bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Roll No</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Produk</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Pemilik</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Gudang</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Lot</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Dye Lot</th>
              <th className="text-center px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Grade</th>
              <th className="text-right px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Panjang</th>
              <th className="text-right px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Berat</th>
              <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Status</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Pegging</th>
              <th className="text-right px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#EFF0F2]">
            {loading && (
              <tr><td colSpan={12} className="text-center py-8 text-[12px] text-[#6B6B73]">Memuat…</td></tr>
            )}
            {!loading && rolls.length === 0 && (
              <tr>
                <td colSpan={12} className="text-center py-10">
                  <Layers size={28} className="mx-auto mb-2 text-gray-300" />
                  <p className="text-[12px] text-[#6B6B73]">Tidak ada roll</p>
                </td>
              </tr>
            )}
            {rolls.map((r) => {
              const ear = r.earmarked_for;
              const busy = busyRollId === r.id;
              return (
                <tr key={r.id} data-testid={`roll-row-${r.id}`} className={`transition-colors ${ear ? "bg-[#FBF7FF] hover:bg-[#F6EDFF]" : "hover:bg-[#FAFBFC]"}`}>
                  <td className="px-3 py-2 font-bold text-[#007AFF] tabular-nums">{r.roll_no}</td>
                  <td className="px-3 py-2">
                    <p className="font-medium">{r.product_name}</p>
                    <p className="text-[10px] text-[#8E8E93]">{r.sku}</p>
                  </td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center rounded-md bg-[#EEF2FF] px-1.5 py-0.5 text-[10px] font-semibold text-[#4338CA]">
                      {r.owner_entity_name}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <p className="font-medium">{r.warehouse_name}</p>
                    <p className="text-[10px] text-[#8E8E93]">{r.warehouse_city}</p>
                  </td>
                  <td className="px-3 py-2 font-mono text-[10.5px] text-[#3C3C43]"
                    data-testid={`roll-lot-${r.id}`}>
                    {r.lot}
                    {/* Fase C — tanda roll belum bertaut lot kelas satu (mode peringatan) */}
                    {!r.lot_id && (
                      <span title="Roll belum bertaut lot kelas satu — buka Lot & Silsilah untuk menambal"
                        className="ml-1 rounded bg-amber-100 px-1 text-[9px] font-semibold text-amber-700">
                        tanpa lot
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-[10.5px] text-[#6B219A]" data-testid={`roll-dyelot-${r.id}`}>{r.dye_lot || "—"}</td>
                  <td className="px-3 py-2 text-center font-semibold">
                    {r.grade || "-"}
                    {Array.isArray(r.defects) && r.defects.length > 0 && (
                      <span data-testid={`roll-defects-${r.id}`} title={r.defects.join(", ")}
                            className="ml-1 inline-block rounded bg-red-100 text-red-700 text-[9px] px-1 align-middle">
                        {r.defects.length} cacat
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-bold tabular-nums">
                    {formatQty(r.length_remaining)} <span className="text-[9px] text-[#8E8E93]">{r.unit}</span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums" data-testid={`roll-weight-${r.id}`}>
                    {/* FASE U — UKURAN KEDUA roll. Roll kain sering diukur DUA kali:
                        panjang (yard/meter) dan berat (kg). `secondary_measures`
                        adalah petanya (satuan → nilai) dan `weight_kg` tetap sumber
                        untuk kg. Satuan lain yang sudah tersimpan ikut ditampilkan —
                        tanpa ini angka yang SUDAH ada di basis data tidak pernah
                        terlihat siapa pun, dan penimbangnya menyimpulkan datanya hilang. */}
                    {(() => {
                      const sec = r.secondary_measures && typeof r.secondary_measures === "object"
                        ? r.secondary_measures : {};
                      const kg = Number(sec.kg ?? r.weight_kg) || 0;
                      const extra = Object.entries(sec)
                        .filter(([u, v]) => u !== "kg" && Number(v) > 0);
                      if (!kg && extra.length === 0) return <span className="text-[#C7C7CC]">—</span>;
                      return (
                        <>
                          {kg > 0 && <>{formatQty(kg)} <span className="text-[9px] text-[#8E8E93]">kg</span></>}
                          {extra.map(([u, v]) => (
                            <span key={u} className="ml-1 text-[10px] text-[#6B6B73]">
                              {formatQty(v)} {u}
                            </span>
                          ))}
                        </>
                      );
                    })()}
                  </td>
                  <td className="px-3 py-2"><RollStatusBadge status={r.status} /></td>
                  <td className="px-3 py-2">
                    {ear ? (
                      <span
                        data-testid={`roll-earmark-badge-${r.id}`}
                        title={ear.note ? `Catatan: ${ear.note}` : `Di-peg untuk ${ear.name}`}
                        className="inline-flex items-center gap-1 rounded-md bg-[#F3E8FF] px-1.5 py-0.5 text-[10px] font-semibold text-[#6B219A] max-w-[150px]"
                      >
                        <Anchor size={9} className="shrink-0" />
                        <span className="truncate">{ear.name}</span>
                      </span>
                    ) : (
                      <span className="text-[#C7C7CC]">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {!canPeg && <span className="text-[#C7C7CC]">—</span>}
                    {canPeg && ear && (
                      <button
                        data-testid={`roll-unpeg-btn-${r.id}`}
                        onClick={() => onUnpeg?.(r)}
                        disabled={busy}
                        className="inline-flex items-center gap-1 rounded-md border border-[#E5C7F5] bg-white px-2 py-1 text-[10.5px] font-semibold text-[#6B219A] hover:bg-[#FBF7FF] disabled:opacity-50"
                      >
                        <Anchor size={10} /> {busy ? "…" : "Lepas"}
                      </button>
                    )}
                    {canPeg && !ear && r.status === "available" && (
                      <button
                        data-testid={`roll-peg-btn-${r.id}`}
                        onClick={() => onPeg?.(r)}
                        disabled={busy}
                        className="inline-flex items-center gap-1 rounded-md border border-[#D6CCF0] bg-white px-2 py-1 text-[10.5px] font-semibold text-[#6B219A] hover:bg-[#FBF7FF] disabled:opacity-50"
                      >
                        <Anchor size={10} /> Peg
                      </button>
                    )}
                    {canPeg && !ear && r.status !== "available" && (
                      <span className="text-[#C7C7CC]">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
