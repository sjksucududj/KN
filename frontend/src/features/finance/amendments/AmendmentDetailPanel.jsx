/**
 * AmendmentDetailPanel — FASE G-1 · meninjau & memutus satu amandemen.
 *
 * Yang ditampilkan bukan sekadar "setuju / tolak", melainkan seluruh bahan
 * keputusan: perubahan baris demi baris, dampak rupiah & persen, cara penerapan,
 * AMBANG YANG BERLAKU SAAT USULAN DIBUAT (`policy_snapshot`) supaya keputusan bisa
 * diaudit ulang bertahun kemudian, serta jejak dokumen yang dihasilkan.
 *
 * Aturan yang di-mirror dari backend (bukan diakali di UI):
 *   · hanya status `pending_approval` yang bisa diputus (tidak ada putusan ganda);
 *   · peran pemutus harus sesuai `required_role` (admin selalu boleh);
 *   · bila kontrol ganda aktif, pengusul tidak boleh menyetujui usulannya sendiri.
 * UI menonaktifkan tombolnya lebih awal DAN menjelaskan alasannya — server tetap
 * menjadi penjaga terakhir.
 */
import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2, Link2, Loader2, Scale, ShieldAlert, UserCheck, XCircle,
} from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import AmendmentChangeList from "./AmendmentChangeList";
import AmendmentImpactCard from "./AmendmentImpactCard";
import { amendmentDetail, decideAmendment, errText, statusMeta } from "./amendmentApi";

const APPROVER_ROLES = ["admin", "manager"];

function when(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }); }
  catch { return iso; }
}

function PolicyRow({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-2 text-[10.5px]">
      <span className="text-[#6B6B73]">{label}</span>
      <span className="text-right font-semibold tabular-nums text-[#3C3C43]">{value}</span>
    </div>
  );
}

export default function AmendmentDetailPanel({ amdId, currentUser, onDecided, onClose }) {
  const [amd, setAmd] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    if (!amdId) return;
    setLoading(true);
    try {
      setAmd(await amendmentDetail(amdId));
      setError("");
    } catch (e) {
      setError(errText(e, "Gagal memuat detail amandemen."));
    } finally {
      setLoading(false);
    }
  }, [amdId]);

  useEffect(() => { load(); setNote(""); }, [load]);

  async function decide(action) {
    setBusy(action);
    setError("");
    try {
      const row = await decideAmendment(amdId, action, note.trim());
      setAmd(row);
      onDecided?.(row);
    } catch (e) {
      setError(errText(e, "Keputusan gagal disimpan."));
    } finally {
      setBusy("");
    }
  }

  if (loading) {
    return (
      <aside className="section-card self-start" data-testid="amd-detail-loading">
        <div className="section-body py-10 text-center text-[12px] text-[#6B6B73]">
          <Loader2 size={16} className="mx-auto mb-2 animate-spin" /> Memuat amandemen…
        </div>
      </aside>
    );
  }
  if (!amd) {
    return (
      <aside className="section-card self-start" data-testid="amd-detail-error">
        <div className="section-body py-10 text-center text-[12px] text-[#A8221A]">{error || "Tidak ditemukan."}</div>
      </aside>
    );
  }

  const sm = statusMeta(amd.status);
  const policy = amd.policy_snapshot || {};
  const pending = amd.status === "pending_approval";
  const isProposer = !!currentUser?.id && currentUser.id === amd.proposed_by_id;
  const roleOk = currentUser?.role === "admin"
    || currentUser?.role === (amd.required_role || policy.approver_role || "manager");
  const dualBlocked = !!policy.dual_control && isProposer;
  const canDecide = pending && APPROVER_ROLES.includes(currentUser?.role) && roleOk && !dualBlocked;

  return (
    <aside className="section-card self-start" data-testid="amd-detail-panel">
      <div className="section-head">
        <div className="min-w-0">
          <p data-testid="amd-detail-number" className="text-[10px] font-bold uppercase tracking-wide text-[#0058CC]">
            {amd.number}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <span data-testid="amd-detail-status" className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide"
              style={{ background: sm.bg, color: sm.fg }}>{sm.label}</span>
            <span className="text-[10.5px] text-[#6B6B73]">{amd.doc_number}</span>
          </div>
        </div>
        <button className="icon-button" data-testid="amd-detail-close" onClick={onClose}><XCircle size={14} /></button>
      </div>

      <div className="section-body space-y-3">
        {error && (
          <p data-testid="amd-detail-err" className="rounded border border-red-200 bg-red-50 px-2 py-1.5 text-[11px] text-red-700">
            {error}
          </p>
        )}

        <div>
          <p className="text-[10px] font-bold uppercase text-[#6B6B73]">Alasan</p>
          <p data-testid="amd-detail-reason" className="text-[12px] font-semibold text-[#1C1C1E]">{amd.reason_label}</p>
          {amd.note && <p data-testid="amd-detail-note" className="mt-0.5 text-[11px] italic text-[#4A4A52]">“{amd.note}”</p>}
          {amd.affects_master && (
            <p className="mt-1 rounded bg-[#FFF7EC] px-2 py-1 text-[10.5px] font-semibold text-[#9A5B00]">
              Alasan ini ditandai menyangkut data master.
            </p>
          )}
        </div>

        <AmendmentImpactCard data={amd} testId="amd-detail-impact" />
        <AmendmentChangeList changes={amd.changes || []} testId="amd-detail-changes" />

        {(amd.attachments || []).length > 0 && (
          <div data-testid="amd-detail-attachments" className="rounded-md border border-[#EFF0F2] p-2 space-y-1">
            <p className="text-[10px] font-bold uppercase text-[#6B6B73]">Bukti terlampir</p>
            {(amd.attachments || []).map((a, i) => (
              <a key={i} href={a.url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 text-[10.5px] text-[#0058CC] hover:underline">
                <Link2 size={10} /> {a.name || a.url}
              </a>
            ))}
          </div>
        )}

        {/* Ambang yang berlaku SAAT ITU — inti dari "keputusan bisa diaudit ulang" */}
        <div data-testid="amd-detail-policy" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5 space-y-1">
          <p className="flex items-center gap-1 text-[10px] font-bold uppercase text-[#6B6B73]">
            <Scale size={11} /> Ambang yang berlaku saat usulan dibuat
          </p>
          <PolicyRow label="Wajib disetujui di atas" value={formatCurrency(policy.approval_threshold_amount || 0)} />
          <PolicyRow label="Wajib disetujui di atas (%)" value={`${policy.approval_threshold_pct ?? 0}%`} />
          <PolicyRow label="Penyetuju standar" value={(policy.approver_role || "—").toUpperCase()} />
          <PolicyRow label="Naik ke admin di atas" value={formatCurrency(policy.admin_approval_above || 0)} />
          <PolicyRow label="Wajib penjelasan di atas" value={formatCurrency(policy.require_note_above || 0)} />
          <PolicyRow label="Kontrol ganda" value={policy.dual_control ? "Aktif" : "Nonaktif"} />
          <PolicyRow label="Dokumen terbit" value={policy.issued_doc_policy === "note_only" ? "Hanya lewat nota" : "Boleh dihitung ulang"} />
        </div>

        {/* Jejak dua arah + dokumen hasil */}
        {(amd.refs || []).length > 0 && (
          <div data-testid="amd-detail-refs" className="rounded-md border border-[#EFF0F2] p-2 space-y-1">
            <p className="text-[10px] font-bold uppercase text-[#6B6B73]">Jejak dokumen</p>
            {(amd.refs || []).map((r, i) => (
              <p key={i} data-testid={`amd-detail-ref-${i}`} className="text-[10.5px] text-[#3C3C43]">
                <span className="rounded bg-[#EFF4FF] px-1 py-0.5 text-[9px] font-bold uppercase text-[#0058CC]">{r.rel}</span>{" "}
                <b>{r.doc_number}</b> <span className="text-[#8E8E93]">({r.doc_type})</span>
                {r.note ? ` · ${r.note}` : ""}
              </p>
            ))}
          </div>
        )}

        <div className="rounded-md border border-[#EFF0F2] p-2 space-y-0.5 text-[10.5px] text-[#6B6B73]">
          <p><UserCheck size={10} className="mr-1 inline text-[#0058CC]" />Diusulkan <b className="text-[#3C3C43]">{amd.proposed_by || "—"}</b> · {when(amd.proposed_at)}</p>
          {amd.decided_by && (
            <p data-testid="amd-detail-decider">Diputus <b className="text-[#3C3C43]">{amd.decided_by}</b> · {when(amd.decided_at)}</p>
          )}
          {amd.decision_note && <p className="italic">“{amd.decision_note}”</p>}
          {amd.applied_at && <p>Diterapkan {when(amd.applied_at)}</p>}
        </div>

        {/* Kotak keputusan */}
        {pending && (
          <div data-testid="amd-decision-box" className="rounded-md border border-[#FFE2B8] bg-[#FFF7EC] p-2.5 space-y-2">
            <p className="flex items-center gap-1 text-[10px] font-bold uppercase text-[#9A5B00]">
              <ShieldAlert size={11} /> Keputusan diperlukan ({(amd.required_role || "manager").toUpperCase()})
            </p>
            {dualBlocked && (
              <p data-testid="amd-dual-control-warning" className="rounded bg-white px-2 py-1.5 text-[10.5px] text-[#9B1C1C]">
                Kontrol ganda aktif: Anda pengusul amandemen ini, jadi tidak boleh menyetujuinya sendiri.
                Minta rekan dengan wewenang yang sama untuk memutus.
              </p>
            )}
            {!dualBlocked && !roleOk && (
              <p data-testid="amd-role-warning" className="rounded bg-white px-2 py-1.5 text-[10.5px] text-[#9B1C1C]">
                Amandemen ini harus diputus oleh {(amd.required_role || "manager").toUpperCase()}.
                Peran Anda: {(currentUser?.role || "—").toUpperCase()}.
              </p>
            )}
            {!APPROVER_ROLES.includes(currentUser?.role) && (
              <p data-testid="amd-noperm-warning" className="rounded bg-white px-2 py-1.5 text-[10.5px] text-[#6B6B73]">
                Anda dapat memantau statusnya di sini, tetapi keputusan dilakukan oleh manager/admin.
              </p>
            )}
            <textarea data-testid="amd-decision-note" rows="2" value={note} onChange={(e) => setNote(e.target.value)}
              className="field" placeholder="Catatan keputusan (tersimpan permanen pada jejak audit)" />
            <div className="flex gap-2">
              <button data-testid="amd-approve-btn" className="primary-button !py-1.5 flex-1" disabled={!canDecide || !!busy}
                onClick={() => decide("approve")}>
                <CheckCircle2 size={13} /> {busy === "approve" ? "Memproses…" : "Setujui & Terapkan"}
              </button>
              <button data-testid="amd-reject-btn" className="danger-button !py-1.5 flex-1" disabled={!canDecide || !!busy}
                onClick={() => decide("reject")}>
                <XCircle size={13} /> {busy === "reject" ? "Memproses…" : "Tolak"}
              </button>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
