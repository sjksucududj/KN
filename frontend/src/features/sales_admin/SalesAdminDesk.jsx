/**
 * SalesAdminDesk — FASE E-8 (E8.7 · US15/US16/US17/US18/US22) · **MEJA ADMIN SALES**.
 *
 * Bukan "menu tambahan", melainkan tempat kerja: 8 antrean, tiap antrean membawa
 * jumlah + nilai + umur tertua, tiap baris membawa SATU tindakan. Mesinnya sudah ada
 * (papan pending SO · backorder · retur · permintaan internal · pengingat penagihan) —
 * layar ini menyatukannya, tidak membangun ulang (E8.11).
 *
 * Batas wewenang ditulis di layar, bukan disembunyikan: apa yang BUKAN meja ini
 * (faktur pajak, uang masuk, keputusan selisih bayar) disebut terang-terangan supaya
 * Admin Sales tidak mencari-cari tombol yang memang bukan haknya (E8.10b#2).
 */
import { useCallback, useEffect, useState } from "react";
import { ClipboardList, RefreshCw, ShieldAlert, Inbox, Layers } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import DeskQueueCard from "./DeskQueueCard";
import VerifyOrderDialog from "./VerifyOrderDialog";
import FulfillmentDecisionDialog from "./FulfillmentDecisionDialog";
import { confirmOrder, rowLink, salesAdminDesk } from "./workDeskApi";
import { apiErrorText } from "../../utils/apiError";

export default function SalesAdminDesk({ currentUser, selectedEntity = "all", onOpenDocument }) {
  const [desk, setDesk] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [errorAction, setErrorAction] = useState(null);
  const [toast, setToast] = useState("");
  const [busyRef, setBusyRef] = useState("");
  const [verifyRow, setVerifyRow] = useState(null);
  const [fulfillRow, setFulfillRow] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      setDesk(await salesAdminDesk(params));
      setError(""); setErrorAction(null);
    } catch (e) {
      setError(apiErrorText(e, "Gagal memuat Meja Admin Sales."));
    } finally { setLoading(false); }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load]);

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 5000); }

  async function doConfirm(row) {
    setBusyRef(row.ref_id); setError(""); setErrorAction(null);
    try {
      const res = await confirmOrder(row.ref_id);
      flash(`${res?.number || row.number} dikonfirmasi — tugas gudang lahir.`);
      await load();
    } catch (e) {
      setError(apiErrorText(e, "Gagal mengonfirmasi pesanan."));
      // E8.13 — bila sakelar "verifikasi dulu" HIDUP, penolakannya MENUNTUN.
      // Tuntunan tanpa tombol tetap membuat pengguna mencari sendiri; jadi
      // tombolnya disediakan langsung di bilah galat.
      setErrorAction({ label: "Verifikasi sekarang", run: () => setVerifyRow(row) });
    } finally { setBusyRef(""); }
  }

  function handleAction(row, queue) {
    if (row.action_kind === "verify") { setVerifyRow(row); return; }
    if (row.action_kind === "fulfill") { setFulfillRow(row); return; }
    if (row.action_kind === "confirm") { doConfirm(row); return; }
    onOpenDocument?.(rowLink(row, queue?.id, "sales_admin"));
  }

  const queues = Array.isArray(desk?.queues) ? desk.queues : [];
  const openItems = desk?.totals?.open_items || 0;
  const moneyQueues = queues.filter((q) => q.value_kind !== "qty");
  const totalMoney = moneyQueues.reduce((s, q) => s + (q.total_value || 0), 0);
  const oldest = Math.max(0, ...queues.map((q) => q.oldest_age_days || 0));

  return (
    <div data-testid="sales-admin-desk" className="grid gap-4">
      {toast && (
        <div className="notice-bar success" data-testid="desk-toast">
          <span>{toast}</span><button onClick={() => setToast("")}>×</button>
        </div>
      )}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => { setError(""); setErrorAction(null); }}
                   onAction={errorAction ? errorAction.run : undefined}
                   actionLabel={errorAction ? errorAction.label : undefined}
                   testId="desk-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex min-w-0 items-center gap-2">
            <ClipboardList size={15} className="text-[#0058CC]" />
            <span className="kicker">Admin Sales</span>
            <h2 data-testid="desk-title">Meja Admin Sales</h2>
          </div>
          <button data-testid="desk-refresh" className="icon-button" onClick={load}
                  aria-label="Muat ulang meja">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        <p className="px-3 pt-2 text-[11.5px] leading-relaxed text-[#6B6B73]">
          Alur pesanan dari ujung ke ujung: <b>periksa kelengkapan</b> → <b>putuskan
          pemenuhan</b> (stok sendiri · ambil dari PT lain · reorder ke supplier) →
          <b> konfirmasi</b> → dokumen → proses retur. Konfirmasi rutin adalah wewenang
          Anda; nilai besar, kredit, dan harga khusus tetap keputusan manajer.
        </p>

        <section data-testid="desk-metrics" className="grid gap-3 p-3 sm:grid-cols-3">
          <Metric icon={Inbox} label="Perlu Ditindak" value={openItems}
                  tone="rgba(255,149,0,.16)" testId="desk-metric-open" />
          <Metric icon={Layers} label="Nilai Antrean" value={formatCurrency(totalMoney)}
                  tone="rgba(0,122,255,.12)" testId="desk-metric-value" />
          <Metric icon={ShieldAlert} label="Umur Tertua"
                  value={oldest > 0 ? `${oldest} hari` : "hari ini"}
                  tone="rgba(255,59,48,.14)" testId="desk-metric-oldest" />
        </section>

        {(desk?.not_my_desk || []).length > 0 && (
          <div data-testid="desk-not-mine"
               className="mx-3 mb-3 rounded-lg border border-[#CBDFFF] bg-[#F2F7FF] px-3 py-2">
            <p className="text-[10.5px] font-bold uppercase tracking-wide text-[#0058CC]">
              Bukan wewenang meja ini — ada di Meja Finance
            </p>
            <p className="text-[11.5px] text-[#31465F]">
              {(desk.not_my_desk || []).join(" · ")}
            </p>
          </div>
        )}
      </section>

      {loading && !desk ? (
        <div className="section-card py-14 text-center text-[12px] text-[#6B6B73]"
             data-testid="desk-loading">
          Menyusun antrean kerja…
        </div>
      ) : queues.length === 0 ? (
        <div className="section-card py-14 text-center text-[12px] text-[#6B6B73]"
             data-testid="desk-empty">
          <Inbox size={26} className="mx-auto mb-2 text-[#D6D6DB]" />
          Belum ada antrean untuk badan usaha yang sedang Anda lihat.
        </div>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {queues.map((q) => (
            <DeskQueueCard key={q.id} queue={q} busyRef={busyRef} loading={loading}
                           testPrefix="desk" onAction={handleAction} />
          ))}
        </div>
      )}

      {verifyRow && (
        <VerifyOrderDialog
          orderId={verifyRow.ref_id}
          orderNumber={verifyRow.number}
          customerName={verifyRow.title}
          onClose={() => setVerifyRow(null)}
          onVerified={(msg) => { setVerifyRow(null); flash(msg); load(); }}
        />
      )}

      {fulfillRow && (
        <FulfillmentDecisionDialog
          orderId={fulfillRow.ref_id}
          orderNumber={fulfillRow.number}
          customerName={fulfillRow.title}
          onClose={() => setFulfillRow(null)}
          onDecided={(msg) => { setFulfillRow(null); flash(msg); load(); }}
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
