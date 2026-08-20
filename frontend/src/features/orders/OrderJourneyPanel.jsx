/**
 * OrderJourneyPanel — FASE E-8 (E8.14 · US12) · **PERJALANAN PESANAN** untuk sales.
 *
 * Pertanyaan yang paling sering ditanyakan pelanggan ke sales adalah "barang saya
 * sampai mana?". Sebelum ini jawabannya cuma bisa didapat dari layar GUDANG — layar
 * yang memang bukan wewenang sales (dan memang 403). Akibatnya sales menelepon admin,
 * atau lebih buruk: menjanjikan tanggal yang ia karang sendiri.
 *
 * Panel ini read-only dan menggabungkan 9 tahap + progres gudang + pengiriman + faktur
 * + pembayaran + **sumber pemenuhan** ("kekurangan 200 yard diambil dari PT lain lewat
 * KANDA/IC-00007") dalam satu tempat, TANPA memberi akses layar gudang.
 */
import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeftRight, CheckCircle2, Circle, Clock3, FileSignature, PackageSearch,
  RefreshCw, Route, Truck, Wallet, XCircle,
} from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { apiErrorText } from "../../utils/apiError";
import { orderJourney } from "../sales_admin/workDeskApi";

const STATE_STYLE = {
  done: { icon: CheckCircle2, color: "#1B7F4B", line: "#BFE6CE" },
  pending: { icon: Circle, color: "#C7C7CC", line: "#EFF0F2" },
  cancelled: { icon: XCircle, color: "#C0392B", line: "#F5C9BC" },
};

export default function OrderJourneyPanel({ orderId, orderNumber }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!orderId) return;
    setLoading(true);
    try { setData(await orderJourney(orderId)); setError(""); }
    catch (e) { setError(apiErrorText(e, "Gagal memuat perjalanan pesanan.")); }
    finally { setLoading(false); }
  }, [orderId]);

  useEffect(() => { load(); }, [load]);

  const steps = Array.isArray(data?.steps) ? data.steps : [];
  const ful = data?.fulfillment || {};
  const tasks = Array.isArray(data?.warehouse_tasks) ? data.warehouse_tasks : [];
  const kirim = Array.isArray(data?.shipments) ? data.shipments : [];
  const faktur = Array.isArray(data?.tax_invoices) ? data.tax_invoices : [];
  const kwitansi = Array.isArray(data?.receipts) ? data.receipts : [];
  const percent = data?.progress?.percent || 0;

  return (
    <aside className="section-card" data-testid="order-journey-panel">
      <div className="section-head">
        <div className="flex min-w-0 items-center gap-2">
          <Route size={15} className="text-[#0058CC]" />
          <h2 data-testid="journey-title">Perjalanan {data?.order_number || orderNumber}</h2>
        </div>
        <button data-testid="journey-refresh" className="icon-button" onClick={load}
                aria-label="Muat ulang perjalanan">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
                   testId="journey-error" />

      {loading && !data ? (
        <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="journey-loading">
          Menyusun perjalanan pesanan…
        </div>
      ) : !data ? (
        <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="journey-empty">
          Perjalanan pesanan belum bisa ditampilkan.
        </div>
      ) : (
        <>
          {/* Tahap sekarang + progres */}
          <div className="px-3 pb-2 pt-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                  Tahap sekarang
                </p>
                <p data-testid="journey-current" className="text-[13px] font-bold text-[#1C1C1E]">
                  {data.current_label}
                </p>
                <p className="text-[10.5px] text-[#8E8E93]">
                  {data.customer_name}{data.sales_name ? ` · sales ${data.sales_name}` : ""}
                </p>
              </div>
              <span data-testid="journey-progress"
                    className="text-[12px] font-bold tabular-nums text-[#0058CC]">
                {data.progress?.done || 0}/{data.progress?.total || 0} tahap
              </span>
            </div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[#EFF0F2]">
              <div className="h-full rounded-full" data-testid="journey-progress-bar"
                   style={{ width: `${percent}%`,
                            background: data.cancelled ? "#C0392B" : "#0058CC" }} />
            </div>
          </div>

          {/* Ringkasan uang — sales memang ditanya soal ini */}
          <div className="grid grid-cols-3 gap-2 px-3 pb-3" data-testid="journey-money">
            <Money label="Nilai Pesanan" value={data.grand_total} testId="journey-total" />
            <Money label="Sudah Dibayar" value={data.paid_total} tone="#1B7F4B"
                   testId="journey-paid" />
            <Money label="Sisa Tagihan" value={data.outstanding}
                   tone={data.outstanding > 0 ? "#C0392B" : "#1B7F4B"} testId="journey-outstanding" />
          </div>

          {/* SUMBER PEMENUHAN — kalimat yang bisa dibacakan ke pelanggan (US12) */}
          {(ful.sentence || (ful.shortages || []).length > 0) && (
            <div className="mx-3 mb-3 rounded-lg border border-[#F5D9A8] bg-[#FFF9EF] px-3 py-2"
                 data-testid="journey-fulfillment">
              <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#8A5300]">
                <PackageSearch size={11} /> Sumber pemenuhan kekurangan
              </p>
              {ful.sentence && (
                <p data-testid="journey-fulfillment-sentence"
                   className="text-[11.5px] font-semibold text-[#7A4A00]">{ful.sentence}</p>
              )}
              {ful.ref_number && (
                <p className="mt-0.5 flex items-center gap-1 text-[10.5px] text-[#8A5300]">
                  <ArrowLeftRight size={10} />
                  <span data-testid="journey-fulfillment-ref" className="font-bold">
                    {ful.ref_number}
                  </span>
                  {ful.mode_label ? ` · ${ful.mode_label}` : ""}
                </p>
              )}
              {(ful.shortages || []).map((s, i) => (
                <p key={i} data-testid={`journey-shortage-${i}`}
                   className="mt-0.5 text-[10.5px] text-[#8A5300]">
                  {s.product_name}: kurang {formatQty(s.backorder_qty)} {s.unit}
                  {s.promise_date ? ` · janji ${String(s.promise_date).slice(0, 10)}` : ""}
                </p>
              ))}
            </div>
          )}

          {/* 9 TAHAP */}
          <div className="border-t border-[#EFF0F2]" data-testid="journey-steps">
            {steps.map((s, i) => (
              <StepRow key={s.key} step={s} last={i === steps.length - 1} />
            ))}
          </div>

          {/* Progres gudang — TANPA memberi akses layar gudang */}
          <Block title="Progres Gudang" icon={Truck} testId="journey-tasks"
                 empty="Belum ada tugas gudang untuk pesanan ini." rows={tasks}
                 render={(t) => (
                   <>
                     <span className="truncate text-[11.5px] font-semibold">{t.product_name}</span>
                     <span className="text-[10.5px] text-[#8E8E93]">
                       {t.warehouse_name || "—"} · diambil {formatQty(t.picked_qty)} dari{" "}
                       {formatQty(t.quantity)} {t.unit}
                     </span>
                   </>
                 )} />

          <Block title="Surat Jalan" icon={Truck} testId="journey-shipments"
                 empty="Belum ada surat jalan." rows={kirim}
                 render={(s) => (
                   <>
                     <span className="truncate text-[11.5px] font-semibold text-[#0058CC]">
                       {s.shipment_no}
                     </span>
                     <span className="text-[10.5px] text-[#8E8E93]">
                       {s.product_name || "—"} · {formatQty(s.qty)} {s.unit}
                       {s.is_partial ? " · kiriman sebagian" : ""}
                     </span>
                   </>
                 )} />

          <Block title="Faktur Pajak" icon={FileSignature} testId="journey-tax"
                 empty="Belum ada faktur pajak — penerbitannya wewenang Finance." rows={faktur}
                 render={(f) => (
                   <>
                     <span className="truncate text-[11.5px] font-semibold text-[#6B219A]">
                       {f.number}
                     </span>
                     <span className="text-[10.5px] text-[#8E8E93]">
                       {(f.faktur_date || "").slice(0, 10)} · PPN {formatCurrency(f.ppn_amount)}
                     </span>
                   </>
                 )} />

          <Block title="Uang Masuk" icon={Wallet} testId="journey-receipts"
                 empty="Belum ada pembayaran yang dialokasikan ke pesanan ini." rows={kwitansi}
                 render={(k) => (
                   <>
                     <span className="truncate text-[11.5px] font-semibold text-[#1B7F4B]">
                       {k.number}
                     </span>
                     <span className="text-[10.5px] text-[#8E8E93]">
                       {(k.receipt_date || "").slice(0, 10)} · {formatCurrency(k.applied)}
                     </span>
                   </>
                 )} />

          <p className="px-3 py-2 text-[10.5px] leading-relaxed text-[#9A9BA3]">
            Panel ini hanya membaca. Tindakan gudang, penerbitan faktur pajak, dan
            pencatatan uang masuk dikerjakan peran yang berwenang — statusnya tetap
            terlihat di sini supaya Anda bisa menjawab pelanggan tanpa menebak.
          </p>
        </>
      )}
    </aside>
  );
}

function StepRow({ step, last }) {
  const st = STATE_STYLE[step.state] || STATE_STYLE.pending;
  const Icon = st.icon;
  return (
    <div className="flex gap-2.5 px-3" data-testid={`journey-step-${step.key}`}>
      <div className="flex flex-col items-center pt-2.5">
        <Icon size={14} style={{ color: st.color }} />
        {!last && <span className="mt-0.5 w-px flex-1" style={{ background: st.line }} />}
      </div>
      <div className="min-w-0 flex-1 py-2">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <p className={`text-[12px] ${step.done ? "font-bold text-[#1C1C1E]" : "font-semibold text-[#8E8E93]"}`}>
            {step.label}
          </p>
          {step.at && (
            <span className="text-[10px] tabular-nums text-[#9A9BA3]">
              {String(step.at).slice(0, 16).replace("T", " ")}
            </span>
          )}
          {step.by && <span className="text-[10px] text-[#9A9BA3]">· {step.by}</span>}
        </div>
        {step.detail && (
          <p className="text-[10.5px] text-[#6B6B73]">{step.detail}</p>
        )}
      </div>
    </div>
  );
}

function Block({ title, icon: Icon, rows, render, empty, testId }) {
  return (
    <div className="border-t border-[#EFF0F2]" data-testid={testId}>
      <p className="flex items-center gap-1.5 bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
        <Icon size={11} /> {title}
      </p>
      {rows.length === 0 ? (
        <p className="px-3 py-2.5 text-[10.5px] text-[#9A9BA3]">{empty}</p>
      ) : (
        <div className="divide-y divide-[#F4F5F7]">
          {rows.map((r, i) => (
            <div key={r.id || i} className="flex flex-col px-3 py-1.5">{render(r)}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function Money({ label, value, tone, testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-2.5 py-2">
      <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
      <p data-testid={testId} className="text-[12px] font-bold tabular-nums"
         style={{ color: tone || "#1C1C1E" }}>{formatCurrency(value)}</p>
    </div>
  );
}
