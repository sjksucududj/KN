/**
 * FASE G-7 — tabel daftar kontrabon. Sengaja padat: satu baris menjawab
 * "supplier siapa · berapa faktur · nilai bersih · sisa · sudah sampai mana".
 */
import { FileText, AlertTriangle, Clock } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import { STATUS_CLASS, fmtDate, slaText, pendingExceptions } from "./contraBonApi";

export default function ContraBonListTable({ rows, loading, activeId, onOpen }) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#E5E5EA] bg-white"
      data-testid="cb-list-table">
      <div className="max-h-[560px] overflow-auto">
        <table className="data-table w-full text-[12px]">
          <thead className="sticky top-0 z-10 bg-[#FAFBFC]">
            <tr className="text-left text-[10.5px] uppercase tracking-wide text-[#8E8E93]">
              <th className="px-3 py-2">Nomor</th>
              <th className="px-3 py-2">Supplier</th>
              <th className="px-3 py-2">Faktur</th>
              <th className="px-3 py-2 text-right">Nilai bersih</th>
              <th className="px-3 py-2 text-right">Sisa</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Jadwal bayar</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-[12px] text-[#8E8E93]">
                Memuat kontrabon…
              </td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-8 text-center" data-testid="cb-list-empty">
                <p className="text-[13px] font-semibold text-[#1C1C1E]">
                  Belum ada kontrabon pada saringan ini.
                </p>
                <p className="mt-1 text-[11.5px] text-[#6B6B73]">
                  Tekan “Kontrabon baru” saat supplier datang menukar faktur — banyak faktur
                  digabung jadi satu tanda terima dan satu pembayaran.
                </p>
              </td></tr>
            )}
            {!loading && rows.map((cb) => {
              const t = cb.totals || {};
              const pend = pendingExceptions(cb).length;
              const poCount = new Set((cb.bills || []).map((b) => b.po_number).filter(Boolean)).size;
              return (
                <tr key={cb.id} data-testid={`cb-row-${cb.id}`}
                  onClick={() => onOpen(cb)}
                  className={`cursor-pointer border-t border-[#F2F2F5] hover:bg-[#F7F9FC] ${
                    activeId === cb.id ? "bg-[#EAF2FF]" : ""}`}>
                  <td className="px-3 py-2">
                    <p className="flex items-center gap-1.5 font-bold text-[#0058CC]">
                      <FileText size={12} /> {cb.number}
                    </p>
                    <p className="text-[10px] text-[#8E8E93]">{fmtDate(cb.cycle_date)}</p>
                  </td>
                  <td className="px-3 py-2">
                    <p className="font-semibold text-[#1C1C1E]">{cb.supplier_name || "—"}</p>
                    <p className="text-[10px] text-[#8E8E93]">
                      {cb.supplier_pic ? `diserahkan ${cb.supplier_pic}` : "tanpa nama pengantar"}
                    </p>
                  </td>
                  <td className="px-3 py-2">
                    <p>{(cb.bills || []).length} faktur</p>
                    <p className="text-[10px] text-[#8E8E93]">
                      {poCount} PO{pend ? ` · ${pend} selisih belum diputus` : ""}
                    </p>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold">
                    {formatCurrency(t.net_payable)}
                    {Number(t.deductions_total) > 0 && (
                      <p className="text-[10px] font-normal text-[#B26A00]">
                        potongan {formatCurrency(t.deductions_total)}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    <span className={Number(t.outstanding) > 0 ? "text-[#C0392B]" : "text-[#1B7F4B]"}>
                      {formatCurrency(t.outstanding)}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span data-testid={`cb-status-${cb.id}`}
                      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        STATUS_CLASS[cb.status] || "bg-[#F2F2F5] text-[#5A5A60]"}`}>
                      {cb.status_label || cb.status}
                    </span>
                    <p className={`mt-0.5 flex items-center gap-1 text-[10px] ${
                      cb.sla?.overdue ? "text-[#C0392B]" : "text-[#8E8E93]"}`}>
                      {cb.sla?.overdue ? <AlertTriangle size={9} /> : <Clock size={9} />}
                      {slaText(cb)}
                    </p>
                  </td>
                  <td className="px-3 py-2 text-[11px]">
                    {(cb.schedule || {}).planned_payment_date
                      ? (
                        <>
                          <p className="font-semibold">
                            {fmtDate(cb.schedule.planned_payment_date)}
                          </p>
                          <p className="text-[10px] text-[#8E8E93]">
                            {cb.schedule.method || "transfer"}
                          </p>
                        </>
                      )
                      : <span className="text-[#C7C7CC]">belum dijadwalkan</span>}
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
