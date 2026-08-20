/** LedgerTable — chronological inventory movement history (max 60 rows). */
import { formatQty, formatDate, MOV_TYPE_MAP, CounterpartyBadge } from "./inventoryConstants";
import QtyDual, { rollsText } from "../../../components/QtyDual";      // FASE U — dua satuan

export default function LedgerTable({ movements = [], balances = [], loading = false }) {
  return (
    <div className="bg-white rounded-xl border border-[#EFF0F2] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-[11.5px]">
          <thead>
            <tr className="bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Waktu</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Tipe</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Produk</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Gudang</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Batch/Lot</th>
              <th className="text-right px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Qty</th>
              <th className="text-left px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Dokumen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#EFF0F2]">
            {loading && (
              <tr><td colSpan={7} className="text-center py-8 text-[12px] text-[#6B6B73]">Memuat…</td></tr>
            )}
            {!loading && movements.length === 0 && (
              <tr><td colSpan={7} className="text-center py-10 text-[12px] text-[#6B6B73]">Tidak ada data pergerakan stok</td></tr>
            )}
            {!loading && movements.slice(0, 60).map((m) => {
              const mt = MOV_TYPE_MAP[m.movement_type] || { label: m.movement_type, color: "text-gray-600", dot: "bg-gray-400" };
              const prod = balances.find(b => b.product_id === m.product_id);
              return (
                <tr key={m.id} data-testid={`movement-row-${m.id}`} className="hover:bg-[#FAFBFC] transition-colors">
                  <td className="px-3 py-2 text-[10.5px] text-[#6B6B73] whitespace-nowrap">{formatDate(m.timestamp)}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${mt.dot}`} />
                      <span data-testid={`movement-type-${m.id}`}
                        data-movement-type={m.movement_type}
                        className={`text-[10.5px] font-semibold ${mt.color}`}>{mt.label}</span>
                    </div>
                    {/* E5.3 — badan usaha lawan: NAMA SINGKAT saja. Jejak pindah
                        kepemilikan wajib terbaca, rincian stok lawan tidak boleh bocor. */}
                    <CounterpartyBadge movement={m} className="mt-0.5 ml-3" />
                  </td>
                  <td className="px-3 py-2">
                    <p className="font-semibold text-[#007AFF]">{prod?.sku || m.product_id}</p>
                  </td>
                  <td className="px-3 py-2 text-[10.5px] text-[#6B6B73]">
                    {balances.find(b => b.warehouse_id === m.warehouse_id)?.warehouse_name || m.warehouse_id}
                  </td>
                  <td className="px-3 py-2 text-[10.5px] text-[#6B6B73]">
                    {[m.batch, m.lot, m.roll_id].filter(Boolean).join(" · ") || "-"}
                  </td>
                  <td className={`px-3 py-2 text-right font-bold tabular-nums ${m.quantity < 0 ? "text-red-600" : "text-green-700"}`}>
                    {m.quantity > 0 ? "+" : ""}{formatQty(m.quantity)}
                    {/* FASE U — DUA SATUAN di kartu stok: satu baris mutasi yang menunjuk
                        satu roll = 1 roll. Baris lama tanpa angka roll tampil tanpa
                        tambahan apa pun (BUKAN "0 roll"). Syarat "layak ditulis" datang
                        dari `rollsText` di komponen bersama — bukan ditulis ulang di sini,
                        supaya kartu mutasi tidak bisa menyimpang dari layar lain. */}
                    {rollsText(m.qty_rolls) && (
                      <span className="ml-1 text-[10px] font-normal text-[#6B6B73]"
                        data-testid={`movement-rolls-${m.id}`}>
                        · {rollsText(m.qty_rolls)}
                      </span>
                    )}
                  </td>
                  {/* Kolom Dokumen memakai `source_document_label` dari server:
                      id teknis (so_/wo_/mko_) sudah diterjemahkan ke nomor manusia.
                      Dokumen yang sudah dihapus ditandai jujur, bukan disembunyikan. */}
                  <td className={`px-3 py-2 text-[10.5px] ${m.source_document_missing ? "text-[#B26A00] italic" : "text-[#007AFF]"}`}
                    data-testid={`movement-doc-${m.id}`}
                    title={m.source_document_missing ? "Dokumen sumber sudah dihapus — mutasi ini yatim" : undefined}>
                    {m.source_document_label || m.source_document || "-"}
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
