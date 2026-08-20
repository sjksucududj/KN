/**
 * AmendmentTrailPanel — FASE G-1 · jejak koreksi pada satu dokumen (Sales Order).
 *
 * Panel ini menempel di panel detail pesanan dan menjawab tiga pertanyaan yang
 * dulu hanya bisa dijawab lewat database:
 *   1. Pernahkah angka dokumen ini dikoreksi? Oleh siapa, kapan, alasannya apa?
 *   2. Berapa dampaknya — dan dokumen apa yang terbit karenanya (nota kredit/debit)?
 *   3. Bagaimana cara mengoreksinya sekarang tanpa mengubah angka diam-diam?
 *
 * Untuk dokumen yang SUDAH TERBIT, nilai aslinya sengaja tidak pernah berubah;
 * yang bertambah hanyalah nota koreksi yang tertaut — itu terlihat jelas di sini.
 */
import { useCallback, useEffect, useState } from "react";
import { FileEdit, Loader2, ReceiptText, ScrollText } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import AmendmentProposeModal from "./AmendmentProposeModal";
import { amendmentsForDoc, errText, methodMeta, statusMeta } from "./amendmentApi";

const PROPOSER_ROLES = ["admin", "manager", "sales"];

function shortDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" }); }
  catch { return iso; }
}

export default function AmendmentTrailPanel({ order, currentUser, onRefresh }) {
  const [rows, setRows] = useState([]);
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showModal, setShowModal] = useState(false);

  const canPropose = PROPOSER_ROLES.includes(currentUser?.role);

  const load = useCallback(async () => {
    if (!order?.id) return;
    setLoading(true);
    try {
      const { amendments, notes: ns } = await amendmentsForDoc("sales_order", order.id);
      setRows(amendments);
      setNotes(ns);
      setError("");
    } catch (e) {
      setError(errText(e, "Gagal memuat jejak amandemen."));
    } finally {
      setLoading(false);
    }
  }, [order?.id]);

  useEffect(() => { load(); }, [load]);

  const handleDone = () => { load(); onRefresh?.(); };

  return (
    <div data-testid="amendment-trail-panel" className="rounded-md border border-[#EFF0F2] overflow-hidden">
      <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 bg-[#FAFBFC] border-b border-[#EFF0F2]">
        <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          <ScrollText size={12} className="text-[#0058CC]" />
          Koreksi & Amandemen
          <span data-testid="amd-trail-count" className="rounded bg-[#EFF4FF] px-1.5 py-0.5 text-[9px] font-bold text-[#0058CC]">
            {rows.length}
          </span>
        </p>
        {canPropose && (
          <button data-testid="open-amend-modal-btn" className="primary-button !py-1 !px-2 !text-[10.5px]"
            onClick={() => setShowModal(true)}>
            <FileEdit size={12} /> Ajukan Amandemen
          </button>
        )}
      </div>

      <div className="p-2.5 space-y-2">
        {error && (
          <p data-testid="amd-trail-error" className="rounded border border-red-200 bg-red-50 px-2 py-1.5 text-[10.5px] text-red-700">
            {error}
          </p>
        )}

        {loading ? (
          <p className="py-3 text-center text-[11px] text-[#6B6B73]">
            <Loader2 size={12} className="inline animate-spin" /> Memuat jejak koreksi…
          </p>
        ) : rows.length === 0 ? (
          <p data-testid="amd-trail-empty" className="py-2 text-[10.5px] leading-snug text-[#6B6B73]">
            Belum ada koreksi pada dokumen ini. Setiap perubahan angka wajib lewat amandemen
            bernomor — tidak ada edit senyap.
          </p>
        ) : (
          rows.map((a) => {
            const sm = statusMeta(a.status);
            const mm = methodMeta(a.method);
            const delta = Number(a.impact?.delta || 0);
            return (
              <div key={a.id} data-testid={`amd-trail-row-${a.id}`}
                className="rounded-md border border-[#EFF0F2] px-2 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10.5px] font-bold text-[#0058CC]">{a.number}</span>
                  <span className="rounded px-1.5 py-0.5 text-[8.5px] font-bold uppercase tracking-wide"
                    style={{ background: sm.bg, color: sm.fg }}>{sm.label}</span>
                </div>
                <p className="text-[10.5px] text-[#3C3C43]">{a.reason_label}</p>
                <p className="text-[10px] text-[#6B6B73] tabular-nums">
                  {delta < 0 ? "−" : "+"} {formatCurrency(Math.abs(delta))} · {mm.label}
                </p>
                <p className="text-[9.5px] text-[#9A9BA3]">
                  Diusulkan {a.proposed_by || "—"} · {shortDate(a.proposed_at)}
                  {a.decided_by ? ` · diputus ${a.decided_by}` : ""}
                </p>
                {a.note && <p className="mt-0.5 text-[10px] italic text-[#6B6B73]">“{a.note}”</p>}
              </div>
            );
          })
        )}

        {notes.length > 0 && (
          <div data-testid="amd-trail-notes" className="rounded-md border border-[#E5EEFB] bg-[#F5F9FF] p-2">
            <p className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#0058CC] mb-1">
              <ReceiptText size={11} /> Nota koreksi terbit ({notes.length})
            </p>
            <p className="mb-1.5 text-[9.5px] leading-snug text-[#4A4A52]">
              Nilai dokumen asal sengaja TIDAK diubah. Koreksinya berdiri sendiri sebagai nota di bawah ini.
            </p>
            {notes.map((n) => (
              <div key={n.id} data-testid={`amd-note-${n.id}`}
                className="flex items-center justify-between gap-2 rounded bg-white px-2 py-1 border border-[#E5EEFB] mb-1 last:mb-0">
                <div className="min-w-0">
                  <p className="text-[10.5px] font-bold text-[#0058CC]">{n.number}</p>
                  <p className="text-[9.5px] text-[#6B6B73] truncate">
                    {n.kind === "credit_note" ? "Nota Kredit" : "Nota Debit"} · {n.reason_label}
                  </p>
                </div>
                <span className={`text-[11px] font-bold tabular-nums shrink-0 ${n.direction === "decrease" ? "text-[#A8221A]" : "text-[#1B7A43]"}`}>
                  {n.direction === "decrease" ? "−" : "+"} {formatCurrency(n.gross_amount)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <AmendmentProposeModal
          order={order}
          currentUser={currentUser}
          onClose={() => { setShowModal(false); load(); }}
          onDone={handleDone}
        />
      )}
    </div>
  );
}
