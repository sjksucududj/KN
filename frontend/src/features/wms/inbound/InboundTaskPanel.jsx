/**
 * InboundTaskPanel — panel kanan layar Inbound (detail 1 task penerimaan).
 *
 * Dipisah dari `InboundScanInterface.jsx` (FASE F-1) agar file utama tetap di bawah
 * batas guardrail setelah penambahan input **satuan supplier**. State tetap dikelola
 * parent lewat props — komponen ini murni presentasi + delegasi aksi.
 */
import { AlertTriangle, Camera, CameraOff, CheckCircle, TrendingUp, X } from "lucide-react";
import InboundScanForm from "../InboundScanForm";
import ReceiveTrailHistory from "./ReceiveTrailHistory";
import DocRefsPanel from "../../documents/trace/DocRefsPanel";
import { formatQty } from "../../../utils/formatters";
import QtyDual from "../../../components/QtyDual";      // FASE U — dua satuan

const STATUS_MAP = {
  waiting_goods: { label: "Waiting", cls: "bg-gray-100 text-gray-600" },
  receiving:     { label: "Penerimaan", cls: "bg-blue-100 text-blue-700" },
  qc_check:      { label: "QC", cls: "bg-purple-100 text-purple-700" },
  put_away:      { label: "Put Away", cls: "bg-indigo-100 text-indigo-700" },
  completed:     { label: "Selesai", cls: "bg-green-100 text-green-700" },
  escalated:     { label: "Escalated", cls: "bg-red-100 text-red-700" },
  qc_pending:    { label: "QC Menunggu", cls: "bg-amber-100 text-amber-700" },
};

export function TaskBadge({ status }) {
  const s = STATUS_MAP[status] || { label: status, cls: "bg-gray-100 text-gray-600" };
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold ${s.cls}`}>
      {s.label}
    </span>
  );
}

export default function InboundTaskPanel({
  task, scanData, setScanData, uom,
  cameraActive, scanValue, onStartCamera, onStopCamera,
  onClose, onScanReceive, onComplete, onEscalate, submitting,
}) {
  const blocked = uom?.preview?.level === "block";
  const canSubmit = !submitting && Number(scanData.doc_qty) > 0 && !blocked;
  return (
    <div className="overflow-hidden rounded-xl border border-[#EFF0F2] bg-white">
      <div className="flex items-center justify-between border-b border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Scan Receive</span>
          <TaskBadge status={task.status} />
        </div>
        <button onClick={onClose} data-testid="inbound-panel-close"
          className="text-[#6B6B73] hover:text-black" aria-label="Tutup panel">
          <X size={14} />
        </button>
      </div>

      <div className="space-y-3 p-3">
        {/* Info bar */}
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-lg bg-[#F5F7FF] p-2">
            <p className="text-[10px] font-semibold uppercase text-[#6B6B73]">PO</p>
            <p className="text-[12px] font-bold text-[#007AFF]">{task.po_number}</p>
          </div>
          <div className="rounded-lg bg-[#F5F7FF] p-2">
            <p className="text-[10px] font-semibold uppercase text-[#6B6B73]">SKU</p>
            <p className="truncate text-[11px] font-semibold">{task.sku}</p>
          </div>
          <div className="rounded-lg bg-[#F5F7FF] p-2">
            <p className="text-[10px] font-semibold uppercase text-[#6B6B73]">Progress</p>
            <p data-testid="inbound-progress" className="text-[12px] font-bold tabular-nums">
              {formatQty(task.received_qty || 0)}
              <span className="text-[10px] text-[#6B6B73]">/{formatQty(task.expected_qty)} {task.unit}</span>
              {/* FASE U — dua satuan: jumlah roll yang benar-benar dibuat vs rencana PO. */}
              <span className="ml-1 text-[10px] text-[#6B6B73]" data-testid="inbound-task-dual">
                <QtyDual rolls={task.qty_rolls} measure={task.received_qty || 0} unit={task.unit} compact />
              </span>
            </p>
          </div>
        </div>

        <div className="rounded-lg bg-[#FAFBFC] p-2">
          <p className="text-[11px] font-medium text-[#3C3C43]">{task.product_name}</p>
          <p className="text-[10.5px] text-[#6B6B73]">
            Supplier: {task.supplier_name || "-"} · Gudang: {task.warehouse_name}
          </p>
          {/* FASE E — nama & kode barang VERSI SUPPLIER berdampingan dengan nama KN,
              agar petugas gudang tidak salah barang saat mencocokkan surat jalan. */}
          {(task.supplier_sku || task.supplier_item_name) && (
            <p data-testid="inbound-supplier-naming"
              className="mt-1 rounded-md border border-[#E5F0FF] bg-[#F5F9FF] px-2 py-1 text-[10.5px] text-[#0058CC]">
              Di surat jalan supplier: <b>{task.supplier_sku || "-"}</b>
              {task.supplier_item_name ? ` — ${task.supplier_item_name}` : ""}
              {task.expected_grade ? ` · grade dijanjikan ${task.expected_grade}` : ""}
            </p>
          )}
        </div>

        {/* Escalation info */}
        {task.status === "escalated" && task.escalation && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-[11px]">
            <p className="font-semibold text-red-700">Escalated: {task.escalation.escalated_by}</p>
            <p className="text-red-600">{task.escalation.reason}</p>
            {task.escalation.status === "resolved" && (
              <p className="mt-1 inline-flex items-center gap-1 text-green-700">
                <CheckCircle size={12} /> Resolved by {task.escalation.resolved_by}: {task.escalation.resolution_notes}
              </p>
            )}
          </div>
        )}

        {!["completed", "escalated"].includes(task.status) && (
          <>
            <div className="flex items-center gap-2">
              <button onClick={cameraActive ? onStopCamera : onStartCamera}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium ${
                  cameraActive ? "bg-red-500 text-white"
                              : "border border-[#007AFF]/30 bg-[#F5F7FF] text-[#007AFF]"}`}>
                {cameraActive ? <><CameraOff size={12} /> Stop Camera</> : <><Camera size={12} /> Camera</>}
              </button>
              {scanValue && (
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-green-700">
                  <CheckCircle size={11} /> {scanValue}
                </span>
              )}
            </div>
            <video id="inbound-video-compact"
              className={`w-full rounded-lg border border-[#007AFF]/30 ${cameraActive ? "block" : "hidden"}`}
              style={{ maxHeight: "160px" }} />

            <InboundScanForm scanData={scanData} setScanData={setScanData} uom={uom} />

            <div className="flex gap-2">
              <button onClick={onScanReceive} disabled={!canSubmit}
                data-testid={`scan-task-${task.id}`}
                className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-[#34C759] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#28A745] disabled:opacity-50">
                <CheckCircle size={13} /> Kirim Hasil Scan
              </button>
              {(task.received_qty || 0) >= task.expected_qty && (
                <button onClick={onComplete} disabled={submitting}
                  data-testid={`complete-task-${task.id}`}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-[#007AFF] px-3 py-2 text-[12px] font-semibold text-white hover:bg-[#0056B3] disabled:opacity-50">
                  <TrendingUp size={13} /> Complete
                </button>
              )}
              <button onClick={onEscalate} data-testid="inbound-escalate-open"
                className="flex items-center gap-1.5 rounded-lg border border-orange-300 bg-orange-50 px-3 py-2 text-[12px] font-semibold text-orange-600 hover:bg-orange-100">
                <AlertTriangle size={13} /> Eskalasi
              </button>
            </div>

            {/* FASE F-1 — jejak konversi penerimaan sebelumnya (D-07) */}
            {(task.scan_log || []).length > 0 && (
              <div className="rounded-lg border border-[#EFF0F2] bg-white p-2">
                <ReceiveTrailHistory task={task} />
              </div>
            )}
          </>
        )}

        {task.status === "completed" && (
          <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-center">
            <CheckCircle className="mx-auto mb-1 text-green-500" size={24} />
            <p className="text-[12px] font-semibold text-green-700">Penerimaan selesai!</p>
            <p className="text-[11px] text-green-600">
              {formatQty(task.received_qty)} {task.unit} diterima
            </p>
            <div className="mt-2">
              <ReceiveTrailHistory task={task} tone="success" />
            </div>
          </div>
        )}

        {/* FASE G-4 — penerimaan ini lahir dari PO mana? (referensi tersimpan dua arah) */}
        <DocRefsPanel docType="grn" docId={task.id} />
      </div>
    </div>
  );
}
