import { FileText, Clock, CheckCircle2, XCircle, PackageCheck, Package, Wallet, Ban, History, FileEdit } from "lucide-react";

/**
 * POTimeline — riwayat / timeline approval & lifecycle Purchase Order.
 * Menampilkan `po.timeline` (created → submitted_for_approval → approved/rejected →
 * received/completed → paid → closed/cancelled). Bila `timeline` kosong (PO lama),
 * disintesis dari field timestamp (created_at/approved_at/rejected_at/...) agar
 * riwayat tetap informatif.
 */

const EVENT_META = {
  created:                { Icon: FileText,     tone: "#0058CC", bg: "#EFF4FF" },
  submitted_for_approval: { Icon: Clock,        tone: "#9A5B00", bg: "#FFF7EC" },
  approved:               { Icon: CheckCircle2, tone: "#15803D", bg: "#E9F7EF" },
  rejected:               { Icon: XCircle,      tone: "#B91C1C", bg: "#FEF3F2" },
  received:               { Icon: Package,      tone: "#0058CC", bg: "#EFF4FF" },
  completed:              { Icon: PackageCheck, tone: "#15803D", bg: "#E9F7EF" },
  paid:                   { Icon: Wallet,       tone: "#15803D", bg: "#E9F7EF" },
  closed_short:           { Icon: Ban,          tone: "#78716C", bg: "#F5F5F4" },
  cancelled:              { Icon: Ban,          tone: "#6B6B73", bg: "#F3F4F6" },
  amended:                { Icon: FileEdit,     tone: "#6B219A", bg: "#F3E8FF" },
};

function fmtDateTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("id-ID", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return String(iso);
  }
}

function synthesize(po) {
  const out = [];
  if (po.created_at) {
    out.push({ event: "created", label: "PO dibuat", actor: po.created_by || "Sistem", at: po.created_at, note: "" });
  }
  if (po.approval_required && po.required_approval_role && !po.approved_at && !po.rejected_at) {
    out.push({ event: "submitted_for_approval", label: `Menunggu persetujuan ${po.required_approval_role}`, actor: po.created_by || "Sistem", at: po.created_at, note: "" });
  }
  if (po.approved_at) {
    out.push({ event: "approved", label: "Disetujui", actor: po.approved_by || "", at: po.approved_at, note: "" });
  }
  if (po.rejected_at) {
    out.push({ event: "rejected", label: "Ditolak", actor: po.rejected_by || "", at: po.rejected_at, note: po.rejection_reason || "" });
  }
  (po.payments || []).forEach((p) => {
    out.push({ event: "paid", label: "Pembayaran dicatat", actor: p.paid_by || "", at: p.paid_at || "", note: p.method ? `via ${p.method}` : "" });
  });
  if (po.completed_at) {
    out.push({ event: "completed", label: "Penerimaan barang selesai", actor: "Sistem", at: po.completed_at, note: "" });
  }
  if (po.closed_at) {
    out.push({ event: "closed_short", label: "Ditutup-kurang", actor: po.closed_by || "", at: po.closed_at, note: po.close_reason || "" });
  }
  return out.sort((a, b) => new Date(a.at || 0) - new Date(b.at || 0));
}

export default function POTimeline({ po }) {
  if (!po) return null;
  const raw = Array.isArray(po.timeline) ? po.timeline : [];
  const entries = raw.length > 0 ? raw : synthesize(po);

  return (
    <div data-testid="po-timeline" className="rounded-md border border-[#EFF0F2] overflow-hidden">
      <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2] flex items-center gap-1.5">
        <History size={12} /> Riwayat / Jejak Persetujuan
      </div>
      {entries.length === 0 ? (
        <div data-testid="po-timeline-empty" className="px-2.5 py-4 text-center text-[11px] text-[#6B6B73]">
          Belum ada riwayat untuk PO ini.
        </div>
      ) : (
        <ol className="p-2.5 space-y-0">
          {entries.map((t, i) => {
            const meta = EVENT_META[t.event] || { Icon: History, tone: "#6B6B73", bg: "#F3F4F6" };
            const Icon = meta.Icon;
            const last = i === entries.length - 1;
            return (
              <li key={`${t.event}-${i}`} data-testid={`po-timeline-entry-${i}`} className="flex gap-2.5">
                <div className="flex flex-col items-center">
                  <span
                    className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full"
                    style={{ background: meta.bg, color: meta.tone }}
                  >
                    <Icon size={13} />
                  </span>
                  {!last && <span className="w-px flex-1 my-0.5" style={{ background: "#E5E7EB", minHeight: 14 }} />}
                </div>
                <div className={`min-w-0 flex-1 ${last ? "" : "pb-2.5"}`}>
                  <div className="flex items-baseline justify-between gap-2">
                    <p data-testid={`po-timeline-label-${i}`} className="text-[11.5px] font-semibold text-[#1C1C1E] truncate">{t.label || t.event}</p>
                    <span className="text-[10px] tabular-nums text-[#8E8E93] whitespace-nowrap">{fmtDateTime(t.at)}</span>
                  </div>
                  <p className="text-[10.5px] text-[#6B6B73]">
                    oleh <span className="font-medium text-[#3C3C43]">{t.actor || "Sistem"}</span>
                  </p>
                  {t.note ? <p className="mt-0.5 text-[10.5px] text-[#6B6B73] italic">{t.note}</p> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
