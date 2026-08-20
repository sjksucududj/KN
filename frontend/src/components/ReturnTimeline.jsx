/**
 * ReturnTimeline — riwayat status retur (sales & purchase) sebagai timeline vertikal.
 * Dipakai di ReturnDetail (sales) & ReturnDetailPanel (purchase).
 *
 * Field yang dibaca (sama di kedua jenis retur):
 *   status, created_at, created_by, submitted_at, submitted_by,
 *   approved_at, approved_by, rejected_at, rejected_by, reject_reason
 *
 * Props:
 *   ret      : objek retur
 *   variant  : "sales" | "purchase" (default "sales") — hanya mengubah teks kecil
 */
import { CheckCircle2, Clock, XCircle, Circle, FileText, PackageCheck } from "lucide-react";

function fmtDateTime(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    return d.toLocaleString("id-ID", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return null;
  }
}

const TONE = {
  done: { dot: "#34C759", ring: "#DCFCE7", text: "#15803D" },
  reject: { dot: "#FF3B30", ring: "#FEE2E2", text: "#B91C1C" },
  active: { dot: "#FF9500", ring: "#FEF3C7", text: "#B45309" },
  upcoming: { dot: "#C7C7CC", ring: "#F2F2F7", text: "#8E8E93" },
};

function Step({ icon: Icon, tone, title, actor, time, note, isLast }) {
  const t = TONE[tone] || TONE.upcoming;
  return (
    <div className="flex gap-3" data-testid={`timeline-step-${title.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="flex flex-col items-center">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-full"
          style={{ background: t.ring, color: t.dot }}
        >
          <Icon size={15} />
        </span>
        {!isLast && <span className="w-px flex-1 my-1" style={{ background: "#E5E5EA", minHeight: 18 }} />}
      </div>
      <div className={`pb-4 ${isLast ? "" : ""}`}>
        <p className="text-[12.5px] font-semibold" style={{ color: t.text }}>{title}</p>
        {(actor || time) && (
          <p className="text-[11px] text-[#6B6B73] mt-0.5">
            {actor && <span className="font-medium text-[#48484A]">{actor}</span>}
            {actor && time && " · "}
            {time}
          </p>
        )}
        {note && <p className="text-[11px] mt-0.5" style={{ color: t.text }}>{note}</p>}
        {!actor && !time && !note && (
          <p className="text-[11px] text-[#8E8E93] mt-0.5">Belum terjadi</p>
        )}
      </div>
    </div>
  );
}

export default function ReturnTimeline({ ret, variant = "sales" }) {
  if (!ret) return null;
  const status = ret.status;
  const past = (s) => {
    // urutan: draft(0) → pending_approval(1) → approved/rejected(2)
    const order = { draft: 0, pending_approval: 1, approved: 2, rejected: 2 };
    return (order[status] ?? 0) >= s;
  };

  // Step 1 — Dibuat
  const s1 = {
    icon: FileText,
    tone: "done",
    title: "Dibuat",
    actor: ret.created_by || "—",
    time: fmtDateTime(ret.created_at),
  };

  // Step 2 — Diajukan ke Approval
  const submitted = past(1);
  const s2 = {
    icon: submitted ? CheckCircle2 : Circle,
    tone: submitted ? "done" : (status === "draft" ? "active" : "upcoming"),
    title: "Diajukan ke Persetujuan",
    actor: submitted ? (ret.submitted_by || ret.created_by || null) : null,
    time: submitted ? (fmtDateTime(ret.submitted_at) || fmtDateTime(ret.updated_at)) : null,
    note: status === "draft" ? "Menunggu diajukan dari status draft" : null,
  };

  // Step 3 — Keputusan
  let s3;
  if (status === "approved") {
    s3 = {
      icon: variant === "sales" ? PackageCheck : CheckCircle2,
      tone: "done",
      title: "Disetujui",
      actor: ret.approved_by || "—",
      time: fmtDateTime(ret.approved_at),
      note: variant === "sales" ? "Stok dikembalikan ke gudang" : "Stok keluar / roll ditandai retur",
    };
  } else if (status === "rejected") {
    s3 = {
      icon: XCircle,
      tone: "reject",
      title: "Ditolak",
      actor: ret.rejected_by || "—",
      time: fmtDateTime(ret.rejected_at),
      note: ret.reject_reason ? `Alasan: ${ret.reject_reason}` : null,
    };
  } else {
    s3 = {
      icon: Clock,
      tone: status === "pending_approval" ? "active" : "upcoming",
      title: "Menunggu Keputusan",
      actor: null,
      time: null,
      note: status === "pending_approval" ? "Menunggu approval manager" : null,
    };
  }

  const steps = [s1, s2, s3];

  return (
    <div className="section-card" data-testid="return-timeline">
      <div className="section-header"><Clock size={14} /> Riwayat Status</div>
      <div className="p-3">
        {steps.map((s, i) => (
          <Step key={i} {...s} isLast={i === steps.length - 1} />
        ))}
      </div>
    </div>
  );
}
