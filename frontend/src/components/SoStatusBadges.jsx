// F4 — Komponen badge & timeline berbasis STAGE+SUB-STATUS (SSOT 2-level).
// Reusable di OrderDetailPanel, OrdersView, OrderDashboard.
import { Check, Package, Truck, PackageCheck, Circle, X } from "lucide-react";
import {
  STAGE_FLOW, STAGE_LABEL_LONG, getStage, getSubStatus, stageMeta, stageIndex, subStatusLabel,
} from "../utils/soStatus";

const STAGE_ICON = {
  Reserved: Check, Approved: Check, Confirmed: Check,
  Picked: Package, Shipped: Truck, Delivered: PackageCheck,
};

// Pill stage (induk) — warna konsisten dgn palet status-pill existing.
export function StagePill({ order, stage, testId }) {
  const s = stage || getStage(order);
  const meta = stageMeta(s);
  return (
    <span data-testid={testId} className={`status-pill ${meta.cls}`}>{meta.label}</span>
  );
}

// Chip sub-status (anak, boleh >1) — alasan "kenapa berhenti di sini".
export function SubStatusChips({ order, subs, testIdPrefix = "substatus", className = "" }) {
  const list = subs || getSubStatus(order);
  if (!list || !list.length) return null;
  return (
    <span className={`inline-flex flex-wrap gap-1 ${className}`}>
      {list.map((k) => (
        <span
          key={k}
          data-testid={`${testIdPrefix}-${k}`}
          className="rounded bg-[#F2F2F7] px-1.5 py-0.5 text-[9px] font-semibold text-[#3C3C43] whitespace-nowrap"
        >
          {subStatusLabel(k)}
        </span>
      ))}
    </span>
  );
}

// Timeline stage-based (induk linear) + chip sub-status pada stage aktif.
export function StageTimeline({ order }) {
  const curStage = getStage(order);
  const subs = getSubStatus(order);
  const isCancelled = curStage === "Cancelled";
  const curIdx = stageIndex(curStage);
  return (
    <div data-testid="order-stage-timeline" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
      <p className="text-[10px] font-bold uppercase text-[#6B6B73] mb-2">Status Timeline</p>
      <div className="space-y-1.5">
        {STAGE_FLOW.map((stage, idx) => {
          const Icon = STAGE_ICON[stage] || Circle;
          const isActive = !isCancelled && idx === curIdx;
          const isPassed = !isCancelled && idx < curIdx;
          return (
            <div key={stage} data-testid={`order-stage-step-${stage}`} className="flex items-center gap-2">
              <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] flex-shrink-0 ${
                isCancelled ? "bg-gray-200 text-gray-400" :
                isActive ? "bg-[#007AFF] text-white font-bold" :
                isPassed ? "bg-green-500 text-white" : "bg-gray-200 text-gray-400"
              }`}>
                {isPassed || isActive ? <Icon size={11} /> : <Circle size={7} />}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-[11px] ${
                  isCancelled ? "text-gray-400" :
                  isActive ? "font-bold text-[#007AFF]" :
                  isPassed ? "text-green-700 font-semibold" : "text-[#8E8E93]"
                }`}>
                  {STAGE_LABEL_LONG[stage] || stage}
                </p>
                {isActive && subs?.length > 0 && (
                  <div className="mt-0.5">
                    <SubStatusChips subs={subs} testIdPrefix="order-substatus" />
                  </div>
                )}
              </div>
              {isActive && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#007AFF] text-white font-bold">CURRENT</span>
              )}
            </div>
          );
        })}
        {isCancelled && (
          <div className="flex items-center gap-2 mt-2 pt-2 border-t border-[#EFF0F2]">
            <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] flex-shrink-0 bg-red-500 text-white">
              <X size={11} />
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-[11px] font-bold text-red-600">Pesanan Dibatalkan</p>
              <SubStatusChips subs={subs} testIdPrefix="order-substatus" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
