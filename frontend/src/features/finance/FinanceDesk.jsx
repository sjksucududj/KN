/**
 * FinanceDesk — FASE E-8 (E8.20 · US20) · **MEJA FINANCE** (uang masuk & pajak keluaran).
 *
 * Keputusan pemilik E8.10b#2 memisahkan kasir/finance dari Admin Sales: yang MENCATAT
 * uang masuk dan MENERBITKAN Faktur Pajak adalah peran `finance`. Layar ini adalah
 * antrean pekerjaan itu — dan ia menyebut terang-terangan apa yang BUKAN wewenangnya
 * (membuat/mengonfirmasi pesanan, keputusan pemenuhan, sisi hutang), supaya tidak ada
 * yang mencari tombol yang memang tidak ada.
 *
 * Dua tindakan dikerjakan LANGSUNG di sini karena keduanya pekerjaan sehari-hari yang
 * berulang: **terbitkan Faktur Pajak** dan **catat kwitansi** (memakai ARReceiptModal
 * yang sudah ada — alokasi FIFO, deposit, dan takaran selisih bayar ikut terpakai).
 */
import { useCallback, useEffect, useState } from "react";
import { Coins, Inbox, Landmark, RefreshCw, ShieldAlert } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import { apiErrorText } from "../../utils/apiError";
import DeskQueueCard from "../sales_admin/DeskQueueCard";
import { financeDesk, issueTaxInvoice, rowLink } from "../sales_admin/workDeskApi";
import ARReceiptModal from "../crm/ARReceiptModal";

export default function FinanceDesk({ currentUser, selectedEntity = "all", onOpenDocument }) {
  const [desk, setDesk] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [busyRef, setBusyRef] = useState("");
  const [payRow, setPayRow] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      setDesk(await financeDesk(params));
      setError("");
    } catch (e) {
      setError(apiErrorText(e, "Gagal memuat Meja Finance."));
    } finally { setLoading(false); }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load]);

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 5000); }

  async function doIssueTax(row) {
    setBusyRef(row.ref_id); setError("");
    try {
      const res = await issueTaxInvoice(row.ref_id);
      flash(`Faktur Pajak ${res?.number || ""} diterbitkan untuk ${row.number}.`);
      await load();
    } catch (e) {
      setError(apiErrorText(e, "Gagal menerbitkan Faktur Pajak."));
    } finally { setBusyRef(""); }
  }

  function handleAction(row, queue) {
    if (row.action_kind === "issue_tax") { doIssueTax(row); return; }
    if (row.action_kind === "receipt") {
      setPayRow({ customer_id: row.ref_id, customer_name: row.title, order_id: row.order_id });
      return;
    }
    onOpenDocument?.(rowLink(row, queue?.id, "finance"));
  }

  const queues = Array.isArray(desk?.queues) ? desk.queues : [];
  const openItems = queues.reduce((s, q) => s + (q.count || 0), 0);
  const totalMoney = queues.reduce((s, q) => s + (q.total_value || 0), 0);
  const oldest = Math.max(0, ...queues.map((q) => q.oldest_age_days || 0));

  return (
    <div data-testid="finance-desk" className="grid gap-4">
      {toast && (
        <div className="notice-bar success" data-testid="fin-desk-toast">
          <span>{toast}</span><button onClick={() => setToast("")}>×</button>
        </div>
      )}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
                   testId="fin-desk-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex min-w-0 items-center gap-2">
            <Landmark size={15} className="text-[#0058CC]" />
            <span className="kicker">Finance</span>
            <h2 data-testid="fin-desk-title">Meja Finance</h2>
          </div>
          <button data-testid="fin-desk-refresh" className="icon-button" onClick={load}
                  aria-label="Muat ulang meja">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        <p className="px-3 pt-2 text-[11.5px] leading-relaxed text-[#6B6B73]">
          Sisi <b>uang masuk</b> &amp; <b>pajak keluaran</b>: terbitkan Faktur Pajak, catat
          kwitansi pelanggan dan alokasikan ke tagihan, putuskan selisih bayar dalam batas
          kewenangan Anda, terbitkan denda, dan pantau jatuh tempo.
        </p>

        <section data-testid="fin-desk-metrics" className="grid gap-3 p-3 sm:grid-cols-3">
          <Metric icon={Inbox} label="Perlu Ditindak" value={openItems}
                  tone="rgba(255,149,0,.16)" testId="fin-desk-metric-open" />
          <Metric icon={Coins} label="Nilai Antrean" value={formatCurrency(totalMoney)}
                  tone="rgba(52,199,89,.16)" testId="fin-desk-metric-value" />
          <Metric icon={ShieldAlert} label="Umur Tertua"
                  value={oldest > 0 ? `${oldest} hari` : "hari ini"}
                  tone="rgba(255,59,48,.14)" testId="fin-desk-metric-oldest" />
        </section>

        {(desk?.not_my_desk || []).length > 0 && (
          <div data-testid="fin-desk-not-mine"
               className="mx-3 mb-3 rounded-lg border border-[#CBDFFF] bg-[#F2F7FF] px-3 py-2">
            <p className="text-[10.5px] font-bold uppercase tracking-wide text-[#0058CC]">
              Bukan wewenang meja ini
            </p>
            <p className="text-[11.5px] text-[#31465F]">
              {(desk.not_my_desk || []).join(" · ")}
            </p>
          </div>
        )}
      </section>

      {loading && !desk ? (
        <div className="section-card py-14 text-center text-[12px] text-[#6B6B73]"
             data-testid="fin-desk-loading">
          Menyusun antrean uang masuk & pajak…
        </div>
      ) : queues.length === 0 ? (
        <div className="section-card py-14 text-center text-[12px] text-[#6B6B73]"
             data-testid="fin-desk-empty">
          <Inbox size={26} className="mx-auto mb-2 text-[#D6D6DB]" />
          Belum ada antrean untuk badan usaha yang sedang Anda lihat.
        </div>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {queues.map((q) => (
            <DeskQueueCard key={q.id} queue={q} busyRef={busyRef} loading={loading}
                           testPrefix="fin-desk" onAction={handleAction} />
          ))}
        </div>
      )}

      {payRow && (
        <ARReceiptModal
          customerId={payRow.customer_id}
          customerName={payRow.customer_name}
          preselectOrderId={payRow.order_id}
          onClose={() => setPayRow(null)}
          onDone={(msg) => { setPayRow(null); flash(msg || "Kwitansi tercatat."); load(); }}
          onError={(msg) => setError(msg)}
        />
      )}
    </div>
  );
}

function Metric({ icon: Icon, label, value, tone, testId }) {
  return (
    <div data-testid={testId} className="metric-card">
      <div className="metric-icon" style={{ background: tone }}>
        <Icon size={16} className="text-[#1C1C1E]" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
        <p className="text-[15px] font-bold tabular-nums">{value}</p>
      </div>
    </div>
  );
}
