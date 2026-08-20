/**
 * PaymentVarianceQueue — FASE G-3 · antrean & riwayat **Selisih Pembayaran**.
 *
 * Dua daftar dalam satu tempat kerja:
 *   1. **Perlu diputus** — kwitansi yang uangnya tidak pas dan belum ada keputusannya.
 *      Selama masih di sini, tidak ada yang "diam-diam dianggap lunas".
 *   2. **Riwayat keputusan** — apa yang diputus, oleh siapa, alasannya, jurnalnya, dan
 *      tombol anulir (jurnal pembalik) bila keputusannya salah.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck, Clock3, Loader2, RefreshCw, Route, Scale, Undo2,
} from "lucide-react";
import EntityBadge from "../../../components/EntityBadge";
import ErrorNotice from "../../../components/ErrorNotice";
import { openTrace } from "../../documents/trace/traceDeepLink";
import PaymentVarianceDialog from "./PaymentVarianceDialog";
import {
  decideVariance, directionMeta, errText, listVariances, money, reverseVariance,
  varianceByReceipt, varianceKindMeta, varianceMeta,
} from "./paymentApi";
import { askReason } from "@/services/confirmService";

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("id-ID",
      { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return "—"; }
}

function Kpi({ label, value, tone = "#1C1C1E", testId }) {
  return (
    <div data-testid={testId} className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
      <p className="text-[14px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
    </div>
  );
}

export default function PaymentVarianceQueue({ currentUser, selectedEntity, onOpenDocument }) {
  const [data, setData] = useState({ items: [], pending: [], stats: {} });
  const [reasons, setReasons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState(null);      // {receipt_id, assessment}
  const [busy, setBusy] = useState(false);
  const [dialogErr, setDialogErr] = useState("");
  const [reversing, setReversing] = useState("");

  const canDecide = ["admin", "manager", "sales"].includes(currentUser?.role);
  const canReverse = ["admin", "manager"].includes(currentUser?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const [res, meta] = await Promise.all([
        listVariances(params),
        varianceMeta(selectedEntity || "").catch(() => ({})),
      ]);
      setData(res);
      setReasons(meta.reasons || []);
      setError("");
    } catch (e) { setError(errText(e, "Gagal memuat selisih pembayaran.")); }
    finally { setLoading(false); }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load]);

  const stats = data.stats || {};
  const pending = useMemo(() => data.pending || [], [data.pending]);
  const decisions = useMemo(() => data.items || [], [data.items]);

  const openDecide = async (row) => {
    setDialogErr("");
    try {
      const res = await varianceByReceipt(row.receipt_id);
      if (!res.assessment) {
        setError("Selisih kwitansi ini sudah diputus atau tidak lagi memerlukan keputusan.");
        await load();
        return;
      }
      setDialog({ receipt_id: row.receipt_id, number: row.number, assessment: res.assessment });
    } catch (e) { setError(errText(e, "Gagal memuat rincian selisih.")); }
  };

  const confirm = async (payload) => {
    setBusy(true); setDialogErr("");
    try {
      await decideVariance(dialog.receipt_id, payload);
      setDialog(null);
      await load();
    } catch (e) { setDialogErr(errText(e, "Keputusan gagal disimpan.")); }
    finally { setBusy(false); }
  };

  const reverse = async (row) => {
    // FASE P5 — dulu `window.prompt`: bila alasan < 3 huruf, fungsi ini DIAM-DIAM berhenti
    // tanpa memberi tahu apa pun (tombol tampak mati). Sekarang tombol konfirmasi memang
    // tidak bisa ditekan sampai alasannya diisi, dan alasan terlalu pendek dijelaskan.
    const reason = await askReason({
      title: `Anulir keputusan ${row.number}?`,
      message: "Efek keputusan sebelumnya dibalik lewat jurnal pembalik. Jejak keputusan lama "
        + "tetap tersimpan (append-only).",
      reasonLabel: "Alasan anulir (minimal 3 huruf)",
      confirmLabel: "Anulir Keputusan",
      danger: true,
      testId: "pv-reverse-confirm",
    });
    if (reason === null) return;
    if (reason.trim().length < 3) {
      setError("Alasan anulir minimal 3 huruf supaya jejaknya bisa dibaca ulang.");
      return;
    }
    setReversing(row.id);
    try { await reverseVariance(row.id, reason.trim()); await load(); }
    catch (e) { setError(errText(e, "Gagal menganulir keputusan.")); }
    finally { setReversing(""); }
  };

  return (
    <div data-testid="payment-variance-queue" className="space-y-3">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="pv-queue-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex min-w-0 items-center gap-2">
            <Scale size={16} className="text-[#0058CC]" />
            <div className="min-w-0">
              <h3 className="text-[12.5px] font-bold">Selisih Pembayaran</h3>
              <p className="text-[11px] text-[#6B6B73]">
                Uang masuk jarang pas. Sistem tidak menuntut nominal persis — tapi setiap
                selisih wajib punya <b>keputusan berlabel</b>.
              </p>
            </div>
          </div>
          <button className="secondary-button" onClick={load} data-testid="pv-queue-refresh">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
          </button>
        </div>
        <div className="section-body space-y-2.5">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="pv-queue-kpis">
            <Kpi testId="pv-kpi-pending" label="Perlu diputus" value={String(pending.length)}
              tone={pending.length ? "#9B1C1C" : "#1B7A43"} />
            <Kpi testId="pv-kpi-writeoff" label="Sisa dihapus" value={money(stats.writeoff_amount)} tone="#9B1C1C" />
            <Kpi testId="pv-kpi-refund" label="Dana dikembalikan" value={money(stats.refund_amount)} tone="#8A6D00" />
            <Kpi testId="pv-kpi-allocated" label="Dialihkan ke pesanan lain" value={money(stats.allocated_amount)} tone="#0058CC" />
            <Kpi testId="pv-kpi-auto" label="Selesai otomatis (pembulatan)" value={String(stats.auto || 0)} tone="#6B6B73" />
          </div>

          <div className="overflow-hidden rounded-lg border border-[#EDEEF1]">
            <div className="flex items-center gap-2 border-b border-[#EDEEF1] bg-[#FFF9E6] px-3 py-1.5">
              <Clock3 size={13} className="text-[#8A6D00]" />
              <p className="text-[11px] font-bold uppercase tracking-wide text-[#8A6D00]">
                Perlu diputus ({pending.length})
              </p>
            </div>
            {pending.length === 0 ? (
              <div className="py-6 text-center" data-testid="pv-pending-empty">
                <BadgeCheck size={22} className="mx-auto mb-1 text-[#1B7A43]" />
                <p className="text-[12px] font-semibold text-[#3C3C43]">
                  Tidak ada selisih yang menggantung.
                </p>
                <p className="text-[11px] text-[#6B6B73]">
                  Setiap rupiah yang masuk sudah jelas perlakuannya.
                </p>
              </div>
            ) : (
              <table className="w-full text-[12px]" data-testid="pv-pending-table">
                <thead>
                  <tr className="border-b border-[#EDEEF1] bg-[#FAFBFC] text-left text-[10px] uppercase tracking-wide text-[#8E8E93]">
                    <th className="px-2 py-2">Kwitansi</th><th className="px-2 py-2">Pelanggan</th>
                    <th className="px-2 py-2">Tanggal</th><th className="px-2 py-2 text-right">Uang masuk</th>
                    <th className="px-2 py-2 text-right">Seharusnya</th>
                    <th className="px-2 py-2 text-right">Selisih</th>
                    <th className="px-2 py-2 text-center">Umur</th>
                    <th className="px-2 py-2 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map((p) => {
                    const dm = directionMeta(p.direction);
                    return (
                      <tr key={p.receipt_id} data-testid={`pv-pending-row-${p.receipt_id}`}
                        className="border-b border-[#F5F5F7] hover:bg-[#FAFBFC]">
                        <td className="px-2 py-2 font-semibold text-[#0058CC]">
                          <button type="button" className="hover:underline"
                            data-testid={`pv-pending-trace-${p.receipt_id}`}
                            onClick={() => openTrace({ docType: "ar_receipt", docId: p.receipt_id, number: p.number })}>
                            {p.number}
                          </button>
                          <EntityBadge entityId={p.entity_id} />
                        </td>
                        <td className="px-2 py-2">{p.customer_name || "—"}</td>
                        <td className="px-2 py-2 text-[#6B6B73]">{fmtDate(p.receipt_date)}</td>
                        <td className="px-2 py-2 text-right tabular-nums">{money(p.funds)}</td>
                        <td className="px-2 py-2 text-right tabular-nums text-[#6B6B73]">{money(p.expected)}</td>
                        <td className="px-2 py-2 text-right">
                          <span className="rounded px-1.5 py-0.5 text-[10.5px] font-bold tabular-nums"
                            style={{ background: dm.bg, color: dm.fg }}>
                            {Number(p.delta) < 0 ? "−" : "+"}{money(Math.abs(Number(p.delta || 0)))}
                          </span>
                        </td>
                        <td className="px-2 py-2 text-center">
                          <span className={`text-[10.5px] font-bold ${
                            (p.age_days || 0) > 7 ? "text-[#9B1C1C]" : "text-[#6B6B73]"}`}>
                            {p.age_days || 0} hr
                          </span>
                        </td>
                        <td className="px-2 py-2 text-right">
                          {canDecide && (
                            <button type="button" className="primary-button !py-1 !px-2 !text-[11px]"
                              data-testid={`pv-decide-${p.receipt_id}`} onClick={() => openDecide(p)}>
                              Putuskan
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </section>

      <section className="section-card">
        <div className="section-head">
          <h3 className="text-[12.5px] font-bold">Riwayat keputusan selisih</h3>
          <span className="text-[10.5px] text-[#8E8E93]">{decisions.length} keputusan</span>
        </div>
        <div className="section-body overflow-x-auto">
          {loading && decisions.length === 0 && (
            <p className="animate-pulse py-8 text-center text-[12px] text-[#6B6B73]">Memuat keputusan…</p>
          )}
          {!loading && decisions.length === 0 && (
            <div className="py-10 text-center" data-testid="pv-decisions-empty">
              <Scale size={26} className="mx-auto mb-2 text-[#C4C5CC]" />
              <p className="text-[12.5px] font-semibold text-[#3C3C43]">Belum ada keputusan selisih.</p>
              <p className="text-[11.5px] text-[#6B6B73]">
                Keputusan muncul di sini saat ada pembayaran yang kurang/lebih dari tagihan.
              </p>
            </div>
          )}
          {decisions.length > 0 && (
            <table className="w-full text-[12px]" data-testid="pv-decisions-table">
              <thead>
                <tr className="border-b border-[#EDEEF1] text-left text-[10px] uppercase tracking-wide text-[#8E8E93]">
                  <th className="px-2 py-2">Nomor</th><th className="px-2 py-2">Sumber</th>
                  <th className="px-2 py-2">Pihak</th><th className="px-2 py-2">Keputusan</th>
                  <th className="px-2 py-2 text-right">Nominal</th><th className="px-2 py-2">Alasan</th>
                  <th className="px-2 py-2">Pemutus</th><th className="px-2 py-2">Jurnal</th>
                  <th className="px-2 py-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d) => {
                  const km = varianceKindMeta(d.kind);
                  const reversed = d.status === "reversed";
                  return (
                    <tr key={d.id} data-testid={`pv-decision-row-${d.id}`}
                      className={`border-b border-[#F5F5F7] hover:bg-[#FAFBFC] ${reversed ? "opacity-60" : ""}`}>
                      <td className="px-2 py-2 font-semibold text-[#0058CC]">
                        <button type="button" className="hover:underline"
                          data-testid={`pv-decision-trace-${d.id}`}
                          onClick={() => openTrace({ docType: "payment_variance", docId: d.id, number: d.number })}>
                          {d.number}
                        </button>
                        {reversed && (
                          <span className="ml-1 rounded bg-[#F2F2F7] px-1 text-[9px] font-bold uppercase text-[#6B6B73]">
                            dianulir
                          </span>
                        )}
                      </td>
                      <td className="px-2 py-2 text-[#3C3C43]">
                        {d.receipt_number || d.bill_number || "—"}
                        {onOpenDocument && d.receipt_id && (
                          <button type="button" title="Buka Jejak Dokumen"
                            data-testid={`pv-decision-src-${d.id}`}
                            onClick={() => openTrace({ docType: "ar_receipt", docId: d.receipt_id, number: d.receipt_number })}
                            className="ml-1 align-middle text-[#0058CC]">
                            <Route size={12} />
                          </button>
                        )}
                      </td>
                      <td className="px-2 py-2">{d.customer_name || d.supplier_name || "—"}</td>
                      <td className="px-2 py-2">
                        <span className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
                          style={{ background: km.bg, color: km.fg }}>{km.label}</span>
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums font-semibold">{money(d.amount)}</td>
                      <td className="px-2 py-2 text-[11px] text-[#6B6B73]" title={d.note || ""}>
                        {d.reason_label || "—"}
                      </td>
                      <td className="px-2 py-2 text-[11px] text-[#6B6B73]">
                        {d.decided_by || "—"}{d.auto ? " (otomatis)" : ""}
                      </td>
                      <td className="px-2 py-2 font-mono text-[10.5px] text-[#6B6B73]">
                        {d.je_number || "—"}
                      </td>
                      <td className="px-2 py-2 text-right">
                        {canReverse && !reversed && (
                          <button type="button" className="secondary-button !py-1 !px-2"
                            data-testid={`pv-reverse-${d.id}`} disabled={reversing === d.id}
                            onClick={() => reverse(d)} title="Anulir keputusan (jurnal pembalik)">
                            {reversing === d.id ? <Loader2 size={12} className="animate-spin" />
                              : <Undo2 size={12} />}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {dialog && (
        <PaymentVarianceDialog assessment={dialog.assessment} reasons={reasons}
          busy={busy} error={dialogErr} submitLabel="Simpan keputusan"
          onCancel={() => { setDialog(null); setDialogErr(""); }} onConfirm={confirm} />
      )}
    </div>
  );
}
