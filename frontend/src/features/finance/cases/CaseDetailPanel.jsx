/**
 * FASE G-9 — CaseDetailPanel: satu kasus dilihat utuh.
 *
 * Isi panel = yang dibutuhkan auditor & petugas dalam satu tarikan napas: sumber uang,
 * langkah playbook, bukti, **dokumen turunan yang benar-benar lahir**, jejak waktu
 * (siapa melakukan apa kapan), dan relasi dokumen (FASE G-4).
 */
import { useMemo, useState } from "react";
import {
  X, Landmark, Paperclip, FileCheck2, History, Link2, UserCog, Ban, Wand2, ShieldCheck,
  RotateCcw,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency } from "../../../utils/formatters";
import { apiErrorText } from "../../../utils/apiError";
import KNSelect from "../../../components/KNSelect";
import {
  DOC_KIND_LABEL, EVENT_LABEL, SOURCE_LABEL, STATUS_CLASS, STATUS_LABEL, fmtDateTime,
  humanAge, slaText,
} from "./caseApi";

export default function CaseDetailPanel({ caseData: c, reasons, canResolve, onClose,
  onChanged, onOpenWizard, onError, onNotify }) {
  const [note, setNote] = useState("");
  const [attachName, setAttachName] = useState("");
  const [rejectMode, setRejectMode] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [assignee, setAssignee] = useState(c.assignee || "");
  const [busy, setBusy] = useState("");
  // KN-G9-ERR-SILENT — penolakan tindakan (tugaskan / catatan / tolak / buka ulang)
  // ditampilkan DI SEBELAH tombolnya, bukan hanya di bilah paling atas layar yang bisa
  // sudah tergulir keluar pandangan saat panel ini panjang.
  const [err, setErr] = useState("");
  // US3 — pilihan alasan penutupan disaring ke yang NYAMBUNG dengan jenis kasus ini
  // (daftar sahnya dari backend, `reason_codes`). Backend menolak yang lain dengan 400,
  // jadi menawarkannya di layar hanya memancing kesalahan.
  const reasonChoices = useMemo(() => {
    const allow = c.reason_codes || [];
    const fit = allow.length ? reasons.filter((r) => allow.includes(r.code)) : reasons;
    return fit.length ? fit : reasons;
  }, [reasons, c.reason_codes]);

  async function post(path, body, msg) {
    setBusy(path); setErr("");
    try {
      const r = await axios.post(`${API}/finance-cases/${c.id}/${path}`, body);
      onNotify(msg);
      onChanged(r.data);
      return true;
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
      return false;
    } finally { setBusy(""); }
  }

  const closed = c.status === "resolved" || c.status === "rejected";

  return (
    <div className="rounded-lg border border-[#E5E5EA] bg-white" data-testid="case-detail">
      <div className="flex items-start justify-between border-b border-[#EFF0F2] px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-[14px] font-bold text-[#1C1C1E]">{c.number}</h3>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
              STATUS_CLASS[c.status]}`} data-testid="case-detail-status">
              {STATUS_LABEL[c.status]}
            </span>
            {c.priority === "tinggi" && (
              <span className="rounded-full bg-[#FDECEA] px-2 py-0.5 text-[10px] font-bold text-[#C0392B]">
                PRIORITAS TINGGI
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[12px] font-semibold text-[#1C1C1E]">{c.case_type_label}</p>
          <p className="text-[12px] text-[#6B6B73]">{c.title}</p>
        </div>
        <button className="icon-button" data-testid="case-detail-close" onClick={onClose}>
          <X size={15} />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 border-b border-[#EFF0F2] px-4 py-3 md:grid-cols-4">
        <div>
          <p className="text-[10px] font-bold uppercase text-[#8E8E93]">Nominal</p>
          <p className="text-[13px] font-bold text-[#1C1C1E] tabular-nums">{formatCurrency(c.amount)}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-[#8E8E93]">Batas waktu</p>
          <p className={`text-[12px] font-semibold ${
            c.overdue ? "text-[#C0392B]" : "text-[#1C1C1E]"}`} data-testid="case-detail-sla">
            {slaText(c)}
          </p>
          <p className="text-[10px] text-[#8E8E93]">SLA {c.sla_hours} jam</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-[#8E8E93]">Umur kasus</p>
          <p className="text-[12px] text-[#1C1C1E]">{humanAge(c.age_hours)}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-[#8E8E93]">Penanggung jawab</p>
          <p className="text-[12px] text-[#1C1C1E]">{c.assignee || "belum ditugaskan"}</p>
        </div>
      </div>

      {!!c.description && (
        <p className="border-b border-[#EFF0F2] px-4 py-3 text-[12px] text-[#1C1C1E]">
          {c.description}
        </p>
      )}

      <div className="border-b border-[#EFF0F2] px-4 py-3">
        <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#8E8E93]">
          <Landmark size={12} /> Sumber kasus
        </p>
        <p className="text-[12px] text-[#1C1C1E]" data-testid="case-detail-source">
          {SOURCE_LABEL[c.source?.kind] || "Dilaporkan manual"}
          {c.source?.label ? ` · ${c.source.label}` : ""}
        </p>
        {!!c.auto_source && (
          <p className="mt-0.5 text-[11px] text-[#0058CC]">
            Ditemukan otomatis oleh sistem ({c.auto_source})
          </p>
        )}
      </div>

      {!!(c.playbook || []).length && !closed && (
        <div className="border-b border-[#EFF0F2] px-4 py-3">
          <p className="mb-1 text-[11px] font-bold uppercase text-[#8E8E93]">Langkah playbook</p>
          <ol className="space-y-1 text-[12px] text-[#1C1C1E]" data-testid="case-detail-playbook">
            {c.playbook.map((s, i) => <li key={i}><b>{i + 1}.</b> {s}</li>)}
          </ol>
        </div>
      )}

      {closed && (
        <div className="border-b border-[#EFF0F2] bg-[#F7FBF8] px-4 py-3"
          data-testid="case-detail-resolution">
          <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#1B7F4B]">
            <ShieldCheck size={12} /> Penyelesaian
          </p>
          <p className="text-[12px] font-semibold text-[#1C1C1E]">
            {c.resolution?.action_label || STATUS_LABEL[c.status]}
          </p>
          {!!c.resolution?.effect && (
            <p className="text-[11px] text-[#6B6B73]">{c.resolution.effect}</p>
          )}
          <p className="mt-1 text-[11px] text-[#1C1C1E]">
            Alasan: <b>{c.reason_label || "—"}</b>
            {c.resolution?.amount ? ` · ${formatCurrency(c.resolution.amount)}` : ""}
          </p>
          <p className="text-[11px] text-[#6B6B73]">
            Oleh {c.resolved_by || "—"} · {fmtDateTime(c.resolved_at)}
            {c.approved_by ? ` · disetujui ${c.approved_by}` : ""}
            {c.resolution?.auto_resolved ? " · di bawah ambang (tanpa persetujuan)" : ""}
          </p>
          {!!c.resolution?.note && (
            <p className="mt-1 text-[11px] italic text-[#6B6B73]">“{c.resolution.note}”</p>
          )}
          {!!c.resolution?.extra?.pending_phase && (
            <p className="mt-1 rounded bg-[#FFF4E5] px-2 py-1 text-[11px] text-[#B26A00]">
              Menunggu fase lanjutan: {c.resolution.extra.pending_phase}
            </p>
          )}
        </div>
      )}

      {!!(c.documents || []).length && (
        <div className="border-b border-[#EFF0F2] px-4 py-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#8E8E93]">
            <FileCheck2 size={12} /> Dokumen turunan ({c.documents.length})
          </p>
          <ul className="space-y-1" data-testid="case-detail-documents">
            {c.documents.map((d, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px]">
                <span className="mt-[2px] rounded bg-[#EAF2FF] px-1.5 py-0.5 text-[10px] font-bold text-[#0058CC]">
                  {DOC_KIND_LABEL[d.kind] || d.kind}
                </span>
                <span className="text-[#1C1C1E]">
                  {d.number ? <b>{d.number}</b> : null} {d.label}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!!(c.attachments || []).length && (
        <div className="border-b border-[#EFF0F2] px-4 py-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#8E8E93]">
            <Paperclip size={12} /> Bukti ({c.attachments.length})
          </p>
          <ul className="space-y-0.5 text-[12px] text-[#1C1C1E]" data-testid="case-detail-attachments">
            {c.attachments.map((a, i) => <li key={i}>• {a.name || a.path}</li>)}
          </ul>
        </div>
      )}

      {!!(c.refs || []).length && (
        <div className="border-b border-[#EFF0F2] px-4 py-3">
          <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#8E8E93]">
            <Link2 size={12} /> Relasi dokumen
          </p>
          <ul className="space-y-0.5 text-[12px] text-[#1C1C1E]" data-testid="case-detail-refs">
            {c.refs.map((r, i) => (
              <li key={i}>• {r.doc_number || r.doc_id} <span className="text-[#8E8E93]">({r.rel})</span></li>
            ))}
          </ul>
        </div>
      )}

      {err && (
        <div className="px-4 pt-3">
          <ErrorNotice message={err} onDismiss={() => setErr("")} testId="case-detail-error" />
        </div>
      )}

      <div className="border-b border-[#EFF0F2] px-4 py-3">
        <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#8E8E93]">
          <History size={12} /> Jejak waktu
        </p>
        <ol className="space-y-1.5" data-testid="case-detail-timeline">
          {(c.timeline || []).map((t, i) => (
            <li key={i} className="border-l-2 border-[#E5E5EA] pl-2.5 text-[12px]">
              <p className="font-semibold text-[#1C1C1E]">
                {t.label || EVENT_LABEL[t.event] || t.event}
              </p>
              <p className="text-[10px] text-[#8E8E93]">
                {t.actor || "sistem"} · {fmtDateTime(t.at)}
              </p>
              {!!t.note && <p className="text-[11px] italic text-[#6B6B73]">“{t.note}”</p>}
            </li>
          ))}
        </ol>
      </div>

      {!closed && (
        <div className="space-y-3 px-4 py-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-[180px] flex-1">
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Penanggung jawab
              </label>
              <input data-testid="case-assignee-input" className="input-field w-full"
                value={assignee} onChange={(e) => setAssignee(e.target.value)}
                placeholder="Nama petugas keuangan" />
            </div>
            <button className="secondary-button" data-testid="case-assign-btn"
              disabled={busy === "assign"}
              onClick={() => post("assign", { assignee }, "Penanggung jawab diperbarui.")}>
              <UserCog size={13} /> Tugaskan
            </button>
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Tambah catatan / bukti
            </label>
            <textarea data-testid="case-note-input" className="textarea w-full" rows={2}
              value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="Mis. sudah telepon pelanggan, menunggu bukti transfer." />
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <input data-testid="case-attach-name" className="input-field flex-1"
                value={attachName} onChange={(e) => setAttachName(e.target.value)}
                placeholder="Nama berkas bukti (mis. bukti_transfer.jpg)" />
              <button className="secondary-button" data-testid="case-note-btn"
                disabled={busy === "note" || (!note.trim() && !attachName.trim())}
                onClick={async () => {
                  const okDone = await post("note", {
                    note,
                    attachments: attachName.trim()
                      ? [{ name: attachName.trim(), path: `bukti/${attachName.trim()}` }]
                      : [],
                  }, "Catatan / bukti tersimpan.");
                  if (okDone) { setNote(""); setAttachName(""); }
                }}>
                <Paperclip size={13} /> Simpan
              </button>
            </div>
          </div>

          {canResolve && (
            <div className="flex flex-wrap items-center gap-2 border-t border-[#EFF0F2] pt-3">
              <button className="primary-button" data-testid="case-open-wizard"
                onClick={() => onOpenWizard(c)}>
                <Wand2 size={13} /> Selesaikan lewat playbook
              </button>
              <button className="secondary-button" data-testid="case-reject-toggle"
                onClick={() => setRejectMode((v) => !v)}>
                <Ban size={13} /> Tutup tanpa tindakan
              </button>
            </div>
          )}

          {rejectMode && canResolve && (
            <div className="rounded-lg border border-[#E5E5EA] p-3" data-testid="case-reject-box">
              <p className="mb-1.5 text-[11px] text-[#6B6B73]">
                Kasus ditutup tanpa perpindahan uang. Alasan & penjelasan wajib diisi supaya
                keputusan ini tetap bisa dibaca auditor.
              </p>
              <KNSelect data-testid="case-reject-reason" className="input-field mb-2 w-full"
                value={rejectReason} onValueChange={setRejectReason}
                aria-label="Alasan penolakan kasus" placeholder="— pilih alasan —"
                options={reasonChoices.map((r) => ({ value: r.code, label: r.label }))} />
              <textarea data-testid="case-reject-note" className="textarea mb-2 w-full" rows={2}
                value={note} onChange={(e) => setNote(e.target.value)}
                placeholder="Penjelasan (wajib)" />
              <button className="primary-button" data-testid="case-reject-submit"
                disabled={!rejectReason || !note.trim() || busy === "reject"}
                onClick={async () => {
                  const okDone = await post("reject",
                    { reason_code: rejectReason, note }, "Kasus ditutup tanpa tindakan.");
                  if (okDone) { setRejectMode(false); setNote(""); setRejectReason(""); }
                }}>
                Tutup kasus
              </button>
            </div>
          )}
        </div>
      )}
      {/* Kasus yang sudah DITUTUP.
          · Ditutup tanpa tindakan (`rejected`) & belum melahirkan dokumen → BOLEH dibuka
            ulang: ternyata uangnya memang harus diurus. Wajib menyebut alasannya supaya
            jejaknya tetap terbaca auditor.
          · Sudah melahirkan dokumen → TIDAK boleh (buku besar tambah-saja); tombolnya
            tetap ditampilkan tetapi terkunci beserta ALASANNYA, bukan disembunyikan
            sehingga petugas menyangka fitur ini tidak ada. */}
      {closed && canResolve && (
        <div className="space-y-2 px-4 py-3" data-testid="case-reopen-box">
          <label className="block text-[11px] font-semibold text-[#6B6B73]">
            Buka ulang kasus (alasan wajib)
          </label>
          <textarea data-testid="case-reopen-note" className="textarea w-full" rows={2}
            value={note} onChange={(e) => setNote(e.target.value)}
            disabled={!!(c.documents || []).length}
            placeholder="Mis. pelanggan menagih lagi, ternyata dananya belum kembali." />
          <div className="flex flex-wrap items-center gap-2">
            <button className="secondary-button" data-testid="case-reopen-btn"
              disabled={!!(c.documents || []).length || !note.trim() || busy === "reopen"}
              onClick={async () => {
                const okDone = await post("reopen", { note }, "Kasus dibuka kembali.");
                if (okDone) setNote("");
              }}>
              <RotateCcw size={13} /> Buka ulang kasus
            </button>
            {!!(c.documents || []).length && (
              <span className="text-[11px] text-[#B26A00]" data-testid="case-reopen-locked">
                Terkunci: kasus ini sudah melahirkan {(c.documents || []).length} dokumen.
                Buku besar bersifat tambah-saja — tindak lanjutnya kasus baru.
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
