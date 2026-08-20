import {
  Paperclip, Trash2, Eye, Clock3, Check, X, Send, Pencil, Loader2, CheckCircle2, XCircle,
  Repeat, ShieldAlert, Tag, Ban,
} from "lucide-react";
import { formatCurrency, formatQty } from "../../../utils/formatters";

const STATUS_META = {
  draft: { label: "Draf", icon: Pencil },
  pending: { label: "Menunggu", icon: Clock3 },
  approved: { label: "Disetujui", icon: CheckCircle2 },
  rejected: { label: "Ditolak", icon: XCircle },
  // F1b — aturan lama yang digantikan aturan baru, dan pengajuan yang ditarik
  // pengajunya. Ditulis apa adanya supaya laporan tidak menuduh manajer menolak.
  superseded: { label: "Digantikan", icon: Repeat },
  cancelled: { label: "Dibatalkan", icon: XCircle },
  revoked: { label: "Diakhiri", icon: Ban },
};

/**
 * Kartu satu pengajuan harga khusus + aksi (submit/approve/reject/edit/hapus/lampiran).
 * Named export (komponen). Aksi data dikirim via callback dari parent.
 */
export function PriceApprovalCard({
  r,
  canApprove,
  busyId,
  decideFor,
  setDecideFor,
  decisionNotes,
  setDecisionNotes,
  fileInputs,
  onUpload,
  onSubmit,
  onApprove,
  onReject,
  onRevoke,
  onEdit,
  onRemove,
  onViewAttachment,
  onDeleteAttachment,
}) {
  const meta = STATUS_META[r.status] || { label: r.status, icon: Clock3 };
  const StatusIcon = meta.icon;
  const editable = ["draft", "pending"].includes(r.status);
  const attachments = r.attachments || [];

  return (
    <article data-testid={`price-approvals-card-${r.id}`} className="section-card p-0 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-4 py-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate text-[12.5px] font-bold text-[#1C1C1E]">{r.customer_name}</span>
          <span className="text-[#C7C7CC]">·</span>
          <span className="text-[10px] font-bold uppercase text-[#0058CC]">{r.sku}</span>
          <span className="truncate text-[12px] text-[#3C3C43]">{r.product_name}</span>
          {r.from_pricelist && (
            <span data-testid={`price-approvals-source-${r.id}`}
              className="inline-flex items-center gap-1 rounded-full bg-[#E7F0FF] px-2 py-0.5 text-[9.5px] font-bold text-[#0058CC]">
              <Tag size={10} /> Daftar Harga Pelanggan
            </span>
          )}
        </div>
        <span className={`status-pill status-${r.status}`} data-testid={`price-approvals-status-${r.id}`}>
          <StatusIcon size={11} /> {meta.label}
          {r.is_expired && <span className="ml-1 text-[9px] text-[#A8221A]">(kadaluarsa)</span>}
        </span>
        {busyId === r.id && (
          <span data-testid={`price-approvals-loading-${r.id}`} className="flex items-center gap-1 text-[10px] text-[#6B219A]">
            <Loader2 size={12} className="animate-spin" /> Memproses…
          </span>
        )}
      </div>

      <div className="grid gap-3 px-4 py-3 sm:grid-cols-[1fr_auto]">
        <div className="grid gap-1.5">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px]">
            <span className="text-[#8E8E93] line-through tabular-nums">{formatCurrency(r.normal_price)}</span>
            <span className="font-bold text-[#6B219A] tabular-nums" data-testid={`price-approvals-price-${r.id}`}>{formatCurrency(r.requested_price)}</span>
            <span className="rounded-full bg-[#F3E9FA] px-2 py-0.5 text-[10px] font-bold text-[#6B219A]">−{formatQty(r.discount_percent)}%</span>
            {r.min_quantity > 0 && <span className="text-[11px] text-[#6B6B73]">min {formatQty(r.min_quantity)} {r.unit}</span>}
          </div>
          {r.reason && <p className="text-[11.5px] text-[#6B6B73]">{r.reason}</p>}
          {/* F1b — batas bawah yang dipakai menilai pengajuan ini (snapshot saat diajukan). */}
          {r.guard && Number(r.guard.floor) > 0 && (
            <p data-testid={`price-approvals-guard-${r.id}`}
              className={`flex items-start gap-1 text-[10.5px] ${r.guard.below_floor === false ? "text-[#6B6B73]" : "text-[#8C4A00]"}`}>
              <ShieldAlert size={11} className="mt-[1px] shrink-0" />
              <span>
                Batas bawah {formatCurrency(r.guard.floor)}/{r.unit}
                {r.guard.hpp > 0 && <> · HPP {formatCurrency(r.guard.hpp)}</>}
                {(r.guard.reasons || []).length > 0 && <> — {r.guard.reasons.join(" ")}</>}
              </span>
            </p>
          )}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 text-[10.5px] text-[#8E8E93]">
            <span>Pengaju: <span className="font-medium text-[#3C3C43]">{r.requested_by_name || "—"}</span></span>
            {r.valid_until && <span>Berlaku s/d: <span className="font-medium text-[#3C3C43]">{(r.valid_until || "").slice(0, 10)}</span></span>}
            {r.approved_by_name && <span>{r.status === "rejected" ? "Ditolak" : "Disetujui"}: <span className="font-medium text-[#3C3C43]">{r.approved_by_name}</span></span>}
          </div>
          {r.decision_notes && (
            <p className={`text-[11px] ${r.status === "rejected" ? "text-[#A8221A]" : "text-[#126E2C]"}`}>Catatan: {r.decision_notes}</p>
          )}

          {attachments.length === 0 && editable && (
            <p data-testid={`price-approvals-att-empty-${r.id}`} className="mt-1 text-[10.5px] text-[#8E8E93]">Belum ada bukti dilampirkan.</p>
          )}
          {attachments.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-2">
              {attachments.map((att) => (
                <span key={att.id} data-testid={`price-approvals-att-${att.id}`} className="flex items-center gap-1 rounded-md border border-[#E5E5EA] bg-white px-2 py-1 text-[10.5px] text-[#3C3C43]">
                  <Paperclip size={11} className="text-[#6B219A]" />
                  <button className="max-w-[140px] truncate hover:underline" onClick={() => onViewAttachment(r.id, att)} data-testid={`price-approvals-att-view-${att.id}`}>
                    {att.original_filename}
                  </button>
                  <button onClick={() => onViewAttachment(r.id, att)} aria-label="Lihat" className="text-[#0058CC]"><Eye size={11} /></button>
                  {editable && (
                    <button onClick={() => onDeleteAttachment(r.id, att.id)} aria-label="Hapus lampiran" className="text-[#A8221A]"><Trash2 size={11} /></button>
                  )}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-col items-stretch gap-1.5 sm:min-w-[180px]">
          {editable && (
            <>
              <input
                ref={(el) => (fileInputs.current[r.id] = el)}
                type="file" accept="image/*,application/pdf" className="hidden"
                data-testid={`price-approvals-file-${r.id}`}
                onChange={(e) => { onUpload(r.id, e.target.files?.[0]); e.target.value = ""; }}
              />
              <button
                data-testid={`price-approvals-upload-${r.id}`}
                disabled={busyId === r.id}
                onClick={() => fileInputs.current[r.id]?.click()}
                className="flex items-center justify-center gap-1.5 rounded-md border border-[#E5E5EA] px-3 py-1.5 text-[11.5px] font-semibold text-[#3C3C43] disabled:opacity-50"
              >
                <Paperclip size={13} /> Upload Bukti
              </button>
            </>
          )}

          {r.status === "draft" && (
            <button
              data-testid={`price-approvals-submit-${r.id}`}
              disabled={busyId === r.id}
              onClick={() => onSubmit(r.id)}
              className="flex items-center justify-center gap-1.5 rounded-md bg-[#6B219A] px-3 py-1.5 text-[11.5px] font-bold text-white disabled:opacity-50"
            >
              <Send size={13} /> Kirim
            </button>
          )}

          {r.status === "pending" && canApprove && decideFor !== `${r.id}:reject` && (
            <button
              data-testid={`price-approvals-approve-${r.id}`}
              disabled={busyId === r.id}
              onClick={() => { setDecideFor(`${r.id}:approve`); setDecisionNotes(""); }}
              className="flex items-center justify-center gap-1.5 rounded-md bg-[#126E2C] px-3 py-1.5 text-[11.5px] font-bold text-white disabled:opacity-50"
            >
              <Check size={13} /> Setujui
            </button>
          )}
          {r.can_revoke && canApprove && !decideFor.startsWith(`${r.id}:`) && (
            <button
              data-testid={`price-approvals-revoke-${r.id}`}
              disabled={busyId === r.id}
              onClick={() => { setDecideFor(`${r.id}:revoke`); setDecisionNotes(""); }}
              className="flex items-center justify-center gap-1.5 rounded-md border border-[#E5E5EA] px-3 py-1.5 text-[11.5px] font-semibold text-[#8C4A00] disabled:opacity-50"
              title="Akhiri aturan harga ini (mis. promo selesai)"
            >
              <Ban size={13} /> Akhiri Aturan
            </button>
          )}

          {r.status === "pending" && canApprove && decideFor !== `${r.id}:approve` && (
            <button
              data-testid={`price-approvals-reject-${r.id}`}
              disabled={busyId === r.id}
              onClick={() => { setDecideFor(`${r.id}:reject`); setDecisionNotes(""); }}
              className="flex items-center justify-center gap-1.5 rounded-md border border-[#E5E5EA] px-3 py-1.5 text-[11.5px] font-semibold text-[#A8221A] disabled:opacity-50"
            >
              <X size={13} /> Tolak
            </button>
          )}

          {editable && (
            <div className="flex gap-1.5">
              <button
                data-testid={`price-approvals-edit-${r.id}`}
                onClick={() => onEdit(r)}
                className="flex flex-1 items-center justify-center gap-1 rounded-md border border-[#E5E5EA] px-2 py-1.5 text-[11px] font-semibold text-[#3C3C43]"
              >
                <Pencil size={12} /> Ubah
              </button>
              <button
                data-testid={`price-approvals-delete-${r.id}`}
                disabled={busyId === r.id}
                onClick={() => onRemove(r.id)}
                className="flex flex-1 items-center justify-center gap-1 rounded-md border border-[#E5E5EA] px-2 py-1.5 text-[11px] font-semibold text-[#A8221A] disabled:opacity-50"
              >
                <Trash2 size={12} /> Hapus
              </button>
            </div>
          )}
        </div>
      </div>

      {decideFor.startsWith(`${r.id}:`) && (
        <div className="border-t border-[#EFF0F2] bg-[#FAFBFC] px-4 py-3">
          <textarea
            data-testid={`price-approvals-notes-${r.id}`}
            className="field min-h-[52px] w-full text-[12px]"
            placeholder={decideFor.endsWith("approve") ? "Catatan persetujuan (opsional)…"
              : decideFor.endsWith("revoke") ? "Alasan mengakhiri (wajib) — mis. promo selesai…"
              : "Alasan penolakan…"}
            value={decisionNotes}
            onChange={(e) => setDecisionNotes(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <button
              data-testid={`price-approvals-confirm-${r.id}`}
              disabled={busyId === r.id}
              onClick={() => (decideFor.endsWith("approve") ? onApprove(r.id, decisionNotes)
                : decideFor.endsWith("revoke") ? onRevoke(r.id, decisionNotes)
                : onReject(r.id, decisionNotes))}
              className={`flex items-center gap-1.5 rounded-md px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50 ${decideFor.endsWith("approve") ? "bg-[#126E2C]" : decideFor.endsWith("revoke") ? "bg-[#8C4A00]" : "bg-[#A8221A]"}`}
            >
              {decideFor.endsWith("approve") ? <Check size={13} /> : decideFor.endsWith("revoke") ? <Ban size={13} /> : <X size={13} />}
              {busyId === r.id ? "Memproses…" : decideFor.endsWith("approve") ? "Konfirmasi Setujui"
                : decideFor.endsWith("revoke") ? "Konfirmasi Akhiri" : "Konfirmasi Tolak"}
            </button>
            <button
              onClick={() => { setDecideFor(""); setDecisionNotes(""); }}
              className="rounded-md border border-[#E5E5EA] px-3 py-1.5 text-[12px] font-semibold text-[#3C3C43]"
            >
              Batal
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
