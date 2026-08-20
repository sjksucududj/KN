/**
 * SoPaymentPanel — FASE G-2 · panel **Jadwal Pembayaran & Denda** di detail Pesanan.
 *
 * Menjawab dua pertanyaan yang tiap hari ditanyakan di lapangan:
 *   “Kapan pelanggan ini janji bayar, berapa per tahap?” dan
 *   “Ada denda tidak? Sudah jadi dokumen, atau masih usulan?”
 */
import { useCallback, useEffect, useState } from "react";
import { CalendarClock, Loader2, PencilLine, RefreshCw, Timer } from "lucide-react";
import PaymentPlanBuilder from "./PaymentPlanBuilder";
import PenaltyPanel from "./PenaltyPanel";
import { accrueNow, errText, fetchMeta, lineMeta, money, planByDoc } from "./paymentApi";

export default function SoPaymentPanel({ order, currentUser, onChanged }) {
  const [data, setData] = useState(null);
  const [tolerance, setTolerance] = useState(1);
  const [edit, setEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const docId = order?.id;
  const total = Number(order?.grand_total || order?.total_amount || 0);
  const canEdit = ["admin", "manager", "sales"].includes(currentUser?.role);

  const load = useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    try {
      const [res, meta] = await Promise.all([
        planByDoc("sales_order", docId),
        fetchMeta(order?.entity_id || "", order?.customer_id || "").catch(() => ({})),
      ]);
      setData(res);
      setTolerance(Number(meta?.plan_policy?.tolerance ?? 1));
      setErr("");
    } catch (e) { setErr(errText(e, "Gagal memuat jadwal pembayaran.")); }
    finally { setLoading(false); }
  }, [docId, order?.entity_id, order?.customer_id]);

  useEffect(() => { load(); }, [load]);

  const plan = data?.plan;
  const penalties = data?.penalties || [];

  const runAccrual = async () => {
    if (!plan?.id) return;
    setBusy(true);
    try { await accrueNow(plan.id); await load(); }
    catch (e) { setErr(errText(e, "Gagal menghitung denda.")); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid="so-payment-panel" className="rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] p-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          <CalendarClock size={12} className="text-[#0058CC]" /> Jadwal Pembayaran & Denda
          {plan?.number && <span className="rounded-full bg-[#EFF4FF] px-1.5 text-[9px] font-bold text-[#0058CC]">{plan.number}</span>}
        </p>
        <div className="flex items-center gap-1">
          <button type="button" title="Muat ulang" onClick={load} data-testid="sop-refresh"
            className="rounded-md border border-[#EDEEF1] bg-white p-1 text-[#4A4B52] hover:bg-[#F2F3F5]">
            {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          </button>
          {plan?.id && ["admin", "manager"].includes(currentUser?.role) && (
            <button type="button" className="secondary-button !py-1" onClick={runAccrual}
              disabled={busy} data-testid="sop-accrue">
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Timer size={12} />} Hitung Denda
            </button>
          )}
          {canEdit && (
            <button type="button" className="secondary-button !py-1" onClick={() => setEdit((v) => !v)}
              data-testid="sop-edit">
              <PencilLine size={12} /> {plan?.id ? "Ubah Jadwal" : "Susun Jadwal"}
            </button>
          )}
        </div>
      </div>

      {err && <div className="notice-bar danger !py-1.5" data-testid="sop-error">
        <span className="text-[11.5px]">{err}</span></div>}

      {loading && !data && (
        <p className="animate-pulse py-3 text-center text-[11px] text-[#6B6B73]">Memuat jadwal…</p>
      )}

      {edit && (
        <div className="mb-2">
          <PaymentPlanBuilder docType="sales_order" docId={docId} total={total} plan={plan}
            tolerance={tolerance}
            onSaved={async () => { setEdit(false); await load(); if (onChanged) onChanged(); }}
            onCancel={() => setEdit(false)} />
        </div>
      )}

      {!loading && !plan && !edit && (
        <p data-testid="sop-empty" className="py-2 text-[10.5px] text-[#6B6B73]">
          Belum ada jadwal pembayaran. Tekan <b>Susun Jadwal</b> untuk membuat DP + cicilan,
          milestone, atau pelunasan NET — bisa diubah bebas per pesanan.
        </p>
      )}

      {plan && !edit && (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2 text-[10.5px] text-[#6B6B73]">
            <span className="rounded bg-[#F1F2F4] px-1.5 py-0.5 font-semibold text-[#4A4B52]">{plan.mode_label}</span>
            <span>Terbayar <b className="tabular-nums">{money(plan.paid_total)}</b> dari {money(plan.total_amount)}</span>
            {data?.next_due && (
              <span data-testid="sop-next-due">· berikutnya {(data.next_due.due_date || "").slice(0, 10)}
                {" "}<b className="tabular-nums">{money(Number(data.next_due.amount || 0) - Number(data.next_due.paid_amount || 0))}</b></span>
            )}
            {(data?.overdue || []).length > 0 && (
              <span data-testid="sop-overdue" className="rounded bg-[#FDE2E2] px-1.5 py-0.5 font-semibold text-[#9B1C1C]">
                {(data.overdue || []).length} baris telat
              </span>
            )}
          </div>
          <div className="overflow-hidden rounded-md border border-[#EFF0F2] bg-white">
            <table className="w-full text-[11px]" data-testid="sop-lines">
              <thead>
                <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[9px] uppercase tracking-wide text-[#8E8E93]">
                  <th className="px-2 py-1">Tahap</th><th className="px-2 py-1">Jatuh tempo</th>
                  <th className="px-2 py-1 text-right">Nominal</th>
                  <th className="px-2 py-1 text-right">Terbayar</th><th className="px-2 py-1">Status</th>
                </tr>
              </thead>
              <tbody>
                {(plan.lines || []).map((l) => {
                  const lm = lineMeta(l.status);
                  return (
                    <tr key={l.seq} className="border-b border-[#F5F5F7] last:border-0"
                      data-testid={`sop-line-${l.seq}`}>
                      <td className="px-2 py-1 font-semibold text-[#1C1C1E]">{l.label}</td>
                      <td className="px-2 py-1 text-[#6B6B73]">{(l.due_date || "").slice(0, 10) || "—"}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{money(l.amount)}</td>
                      <td className="px-2 py-1 text-right tabular-nums text-[#1B7A43]">{money(l.paid_amount)}</td>
                      <td className="px-2 py-1">
                        <span className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide"
                          style={{ background: lm.bg, color: lm.fg }}>{lm.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <PenaltyPanel rows={penalties} currentUser={currentUser}
            entityId={order?.entity_id || ""} onChanged={load} />
        </div>
      )}
    </div>
  );
}
