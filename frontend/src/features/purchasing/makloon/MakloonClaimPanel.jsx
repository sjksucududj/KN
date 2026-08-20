/**
 * MakloonClaimPanel (FASE D · PS-11 · D-09)
 * Panel selisih & klaim untuk SATU langkah makloon:
 *   selisih vs estimasi → ajukan tindakan (potong bon / ganti rugi / terima) →
 *   persetujuan manajer/admin → dampak (tagihan & jurnal) terlihat.
 */
import { useState } from "react";
import { CheckCircle2, Scale, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import { approveClaim, CLAIM_ACTION_LABELS, CLAIM_STATUS_META, proposeClaim, rejectClaim } from "./makloonApi";

const ACTION_OPTS = Object.entries(CLAIM_ACTION_LABELS).map(([value, label]) => ({ value, label }));

export default function MakloonClaimPanel({ mkoId, step, currentUser, onDone, onError, compact = false }) {
  const claim = step.claim || {};
  const variance = step.variance || {};
  const [action, setAction] = useState(claim.action || "potong_bon");
  const [amount, setAmount] = useState(String(claim.amount || claim.amount_suggested || 0));
  const [reason, setReason] = useState(claim.reason || "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const role = currentUser?.role;
  const canPropose = ["admin", "manager", "warehouse"].includes(role);
  const canDecide = ["admin", "manager"].includes(role);
  const meta = CLAIM_STATUS_META[claim.status || "none"] || CLAIM_STATUS_META.none;

  if (!claim.status || claim.status === "none") {
    if (!variance.variance_pct && variance.variance_pct !== 0) return null;
    return (
      <div className="mt-2 rounded-lg border border-[#E6F4EA] bg-[#F4FBF6] px-2.5 py-1.5 text-[11px] text-[#1B7F4B]"
        data-testid={`claim-ok-${step.seq}`}>
        <CheckCircle2 size={11} className="mr-1 inline" />
        Selisih {variance.variance_pct}% masih dalam toleransi {variance.tolerance_pct}% — tidak ada klaim.
      </div>
    );
  }

  const act = async (fn, payload, label) => {
    setBusy(true);
    try {
      await fn(mkoId, payload);
      onDone?.();
    } catch (e) {
      onError?.(e.response?.data?.detail || `Gagal ${label}.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-lg border border-[#FFE0B2] bg-[#FFFBF3] p-2.5" data-testid={`claim-panel-${step.seq}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#B26A00]">
          <Scale size={12} /> Selisih & Klaim
        </p>
        <span className={`status-pill ${meta.cls}`} data-testid={`claim-status-${step.seq}`}>{meta.label}</span>
      </div>

      <div className="mt-1.5 grid grid-cols-2 gap-2 md:grid-cols-4 text-[11px]">
        <Mini label="Estimasi" value={`${formatQty(variance.expected_qty || 0)} ${variance.unit || ""}`} />
        <Mini label="Aktual" value={`${formatQty(variance.actual_qty || 0)} ${variance.unit || ""}`} />
        <Mini label="Selisih" value={`${variance.variance_pct ?? "—"}% (tol. ${variance.tolerance_pct ?? "—"}%)`} tone="#C0392B" />
        <Mini label="Nilai kekurangan" value={formatCurrency(variance.shortfall_value || claim.amount_suggested || 0)} tone="#C0392B" />
      </div>
      {claim.message && <p className="mt-1 text-[11px] text-[#6B6B73]">{claim.message}</p>}

      {claim.status === "approved" && (
        <div className="mt-2 rounded border border-[#CDE8D5] bg-white px-2.5 py-1.5 text-[11px]" data-testid={`claim-result-${step.seq}`}>
          <p className="font-semibold text-[#1B7F4B]">
            <ShieldCheck size={11} className="mr-1 inline" />
            {CLAIM_ACTION_LABELS[claim.action] || claim.action} · {formatCurrency(claim.amount || 0)}
          </p>
          <p className="text-[#6B6B73]">Disetujui oleh {claim.approved_by} · alasan: {claim.reason}</p>
          {claim.effect?.accounting_effect === "ap_reduced" && (
            <p className="text-[#6B6B73]">Tagihan mitra dipotong → sisa {formatCurrency(claim.effect.bill_new_total || 0)} · jurnal Dr Hutang / Cr Pendapatan Klaim.</p>
          )}
          {claim.effect?.accounting_effect === "claim_receivable" && (
            <p className="text-[#6B6B73]">Piutang klaim mitra dibukukan (Dr 1-1260 / Cr 4-9200).</p>
          )}
          {claim.effect?.accounting_effect === "none" && (
            <p className="text-[#6B6B73]">{claim.effect?.note || "Tidak ada jurnal tambahan."}</p>
          )}
        </div>
      )}

      {claim.status === "rejected" && (
        <p className="mt-2 text-[11px] text-[#C0392B]" data-testid={`claim-rejected-${step.seq}`}>
          <XCircle size={11} className="mr-1 inline" /> Ditolak oleh {claim.rejected_by}: {claim.rejected_reason}
        </p>
      )}

      {claim.status === "open" && canPropose && !compact && (
        <div className="mt-2 grid gap-2 md:grid-cols-[1.2fr_0.8fr_1.5fr_auto]">
          <KNSelect data-testid={`claim-action-${step.seq}`} className="field !py-1.5 text-[11.5px]" value={action}
            onValueChange={setAction} options={ACTION_OPTS} />
          <input data-testid={`claim-amount-${step.seq}`} className="field !py-1.5 text-[11.5px]" value={amount}
            onChange={(e) => setAmount(e.target.value)} placeholder="Nilai klaim (Rp)"
            disabled={action === "terima_catatan"} />
          <input data-testid={`claim-reason-${step.seq}`} className="field !py-1.5 text-[11.5px]" value={reason}
            onChange={(e) => setReason(e.target.value)} placeholder="Alasan (wajib, jejak audit)" />
          <button data-testid={`claim-submit-${step.seq}`} className="primary-button !py-1.5 text-[11.5px]" disabled={busy}
            onClick={() => act(proposeClaim, {
              step_seq: step.seq, action,
              amount: action === "terima_catatan" ? 0 : parseFloat(amount) || 0,
              reason,
            }, "mengajukan klaim")}>
            Ajukan
          </button>
        </div>
      )}

      {claim.status === "pending_approval" && (
        <div className="mt-2" data-testid={`claim-pending-${step.seq}`}>
          <p className="text-[11px] text-[#3C3C43]">
            Diajukan {claim.proposed_by}: <b>{CLAIM_ACTION_LABELS[claim.action] || claim.action}</b>
            {" "}· {formatCurrency(claim.amount || 0)} · {claim.reason}
          </p>
          {canDecide ? (
            <div className="mt-1.5 grid gap-2 md:grid-cols-[2fr_auto_auto]">
              <input data-testid={`claim-note-${step.seq}`} className="field !py-1.5 text-[11.5px]" value={note}
                onChange={(e) => setNote(e.target.value)} placeholder="Catatan keputusan (opsional untuk setuju, wajib untuk tolak)" />
              <button data-testid={`claim-approve-${step.seq}`} className="primary-button !py-1.5 text-[11.5px]" disabled={busy}
                onClick={() => act(approveClaim, { step_seq: step.seq, note }, "menyetujui klaim")}>
                <CheckCircle2 size={12} /> Setujui
              </button>
              <button data-testid={`claim-reject-${step.seq}`} className="secondary-button !py-1.5 text-[11.5px] !text-[#C0392B] !border-[#F3C6BF]"
                disabled={busy || !note.trim()}
                onClick={() => act(rejectClaim, { step_seq: step.seq, reason: note }, "menolak klaim")}>
                <XCircle size={12} /> Tolak
              </button>
            </div>
          ) : (
            <p className="mt-1 text-[11px] text-[#B26A00]">
              <TriangleAlert size={11} className="mr-1 inline" /> Menunggu keputusan manajer/admin.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Mini({ label, value, tone = "#1C1C1E" }) {
  return (
    <div>
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[11.5px] font-bold tabular-nums" style={{ color: tone }}>{value}</p>
    </div>
  );
}
