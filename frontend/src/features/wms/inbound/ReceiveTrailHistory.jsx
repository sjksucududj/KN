/**
 * ReceiveTrailHistory (FASE F-1 · F1-03) — riwayat scan penerimaan + **jejak konversi**.
 *
 * Kewajiban D-07: setiap penerimaan yang memakai satuan supplier WAJIB menyimpan jejak
 * (qty & satuan surat jalan, faktor, sumber faktor, siapa, kapan). Panel ini membuat
 * jejak itu terlihat oleh operator & auditor tanpa membuka database.
 */
import { ArrowRight, History } from "lucide-react";
import { RECEIVE_SOURCE_LABEL } from "../../../hooks/useReceivingUom";
import { formatQty } from "../../../utils/formatters";

export default function ReceiveTrailHistory({ task, tone = "neutral" }) {
  const logs = task?.scan_log || [];
  if (!logs.length) return null;
  const border = tone === "success" ? "border-green-200" : "border-[#EFF0F2]";
  return (
    <div data-testid="receive-trail-history" className="text-left">
      <p className="mb-1 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
        <History size={11} /> Riwayat penerimaan ({logs.length})
      </p>
      <div className="space-y-0.5">
        {logs.map((log, i) => {
          const tr = log.uom_trail;
          return (
            <div key={log.id || i} data-testid={`receive-trail-row-${i}`}
              className={`border-t ${border} py-1`}>
              <div className="flex items-center justify-between gap-2 text-[10.5px]">
                <span className="truncate text-[#6B6B73]">
                  {log.roll_id || log.batch || log.lot || log.actor || log.scanned_by || "—"}
                </span>
                <span className="shrink-0 font-semibold tabular-nums">
                  {formatQty(log.actual_qty)} {task.unit}
                </span>
              </div>
              {tr && (
                <div data-testid={`receive-trail-detail-${i}`}
                  className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px] text-[#0058CC]">
                  <span className="font-semibold tabular-nums">
                    {formatQty(tr.doc_qty)} {tr.doc_uom}
                  </span>
                  <ArrowRight size={9} className="text-[#8E8E93]" />
                  <span className="font-bold tabular-nums">
                    {formatQty(tr.task_qty)} {tr.task_uom}
                  </span>
                  <span className="text-[#6B6B73]">
                    (faktor {Number(tr.factor).toLocaleString("id-ID", { maximumFractionDigits: 6 })}
                    {" · "}{RECEIVE_SOURCE_LABEL[tr.source] || tr.source}
                    {tr.supplier_sku ? ` · ${tr.supplier_sku}` : ""})
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
