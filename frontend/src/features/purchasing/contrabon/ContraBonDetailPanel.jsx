/**
 * FASE G-7 — **panel detail kontrabon**: satu tempat untuk seluruh siklus
 * `draf → diajukan → terverifikasi → disetujui → dijadwalkan → dibayar`.
 *
 * Prinsip layar ini:
 *   · MENUNTUN — tombol utama selalu langkah berikutnya (`nextStep`), bukan daftar
 *     panjang aksi yang harus dihafal;
 *   · JUJUR — setiap penolakan backend tampil apa adanya (INV-UI-03), termasuk
 *     alasan wajib, pemisahan tugas, dan ambang persetujuan;
 *   · TIDAK MEMAKSA — selisih 3-way wajib diputus berlabel sebelum verifikasi.
 */
import { useCallback, useEffect, useState } from "react";
import {
  X, RefreshCw, CheckCircle2, AlertTriangle, Ban, Clock, Building2,
} from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { apiErrorText } from "../../../utils/apiError";
import { formatCurrency } from "../../../utils/formatters";
import DocumentActionsBar from "../../documents/DocumentActionsBar";
import DocRefsPanel from "../../documents/trace/DocRefsPanel";
import {
  BillsSection, DecisionsSection, DeductionsSection, DisputeBanner, PaymentsSection,
  ReceiptSection, TimelineSection, TotalsGrid,
} from "./ContraBonParts";
import DeductionModal from "./DeductionModal";
import DecisionModal from "./DecisionModal";
import PayModal from "./PayModal";
import PaymentScheduleModal from "./PaymentScheduleModal";
import ReasonNoteModal from "./ReasonNoteModal";
import { STATUS_CLASS, fmtDate, nextStep, pendingExceptions, slaText } from "./contraBonApi";

const EDITABLE = ["draft", "submitted", "disputed"];

export default function ContraBonDetailPanel({ cb, meta, currentUser, entityLabel,
  onClose, onChanged, onError, onNotify }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [modal, setModal] = useState("");            // deduction|pay|schedule|dispute|cancel
  const [decideOn, setDecideOn] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [loadingReceipt, setLoadingReceipt] = useState(false);

  const role = (currentUser?.role || "").toLowerCase();
  const canWrite = ["admin", "manager"].includes(role);
  const canEdit = canWrite && EDITABLE.includes(cb.status);
  const step = nextStep(cb);
  const pending = pendingExceptions(cb);

  const loadReceipt = useCallback(async () => {
    setLoadingReceipt(true);
    try {
      const r = await axios.get(`${API}/contra-bons/${cb.id}/receipt`);
      setReceipt(r.data || null);
    } catch (e) {
      setErr(apiErrorText(e));
    } finally { setLoadingReceipt(false); }
  }, [cb.id]);

  useEffect(() => { setReceipt(null); setErr(""); loadReceipt(); }, [cb.id, loadReceipt]);

  /** Aksi siklus tanpa isian tambahan (ajukan / verifikasi / setujui). */
  async function run(action, successMsg) {
    setBusy(action); setErr("");
    try {
      const r = await axios.post(`${API}/contra-bons/${cb.id}/${action}`, {});
      onChanged(r.data);
      onNotify?.(successMsg);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setBusy(""); }
  }

  async function removeDeduction(dedId) {
    setBusy(`ded-${dedId}`); setErr("");
    try {
      const r = await axios.delete(`${API}/contra-bons/${cb.id}/deductions/${dedId}`);
      onChanged(r.data);
      onNotify?.("Potongan dihapus — nilai bersih kontrabon dihitung ulang.");
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setBusy(""); }
  }

  function primaryAction() {
    if (!step) return;
    if (step.action === "submit") return run("submit", `${cb.number} diajukan untuk verifikasi.`);
    if (step.action === "verify") {
      return run("verify", `${cb.number} terverifikasi — 3-way match dijalankan ulang.`);
    }
    if (step.action === "approve") return run("approve", `${cb.number} disetujui.`);
    if (step.action === "schedule") return setModal("schedule");
    if (step.action === "pay") return setModal("pay");
    return undefined;
  }

  return (
    <div className="rounded-lg border border-[#E5E5EA] bg-white" data-testid="cb-detail-panel">
      <div className="flex items-start justify-between gap-2 border-b border-[#EFF0F2] px-3 py-2.5">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5">
            <span className="text-[14px] font-bold text-[#1C1C1E]" data-testid="cb-detail-number">
              {cb.number}
            </span>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
              STATUS_CLASS[cb.status] || "bg-[#F2F2F5] text-[#5A5A60]"}`}
              data-testid="cb-detail-status">
              {cb.status_label || cb.status}
            </span>
            {entityLabel && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[#F2F2F5] px-2 py-0.5 text-[9.5px] font-semibold text-[#5A5A60]">
                <Building2 size={9} /> {entityLabel}
              </span>
            )}
          </p>
          <p className="text-[11.5px] text-[#6B6B73]">
            {cb.supplier_name} · tukar faktur {fmtDate(cb.cycle_date)}
            {cb.due_date ? ` · jatuh tempo ${fmtDate(cb.due_date)}` : ""}
          </p>
          <p className={`flex items-center gap-1 text-[10.5px] ${
            cb.sla?.overdue ? "font-semibold text-[#C0392B]" : "text-[#8E8E93]"}`}>
            <Clock size={10} /> {slaText(cb)}
            {cb.sla?.sla_days ? ` · batas ${cb.sla.sla_days} hari` : ""}
          </p>
        </div>
        <button className="icon-button" data-testid="cb-detail-close" onClick={onClose}>
          <X size={15} />
        </button>
      </div>

      <div className="space-y-3 px-3 py-3">
        {err && (
          <ErrorNotice message={err} onDismiss={() => setErr("")} testId="cb-detail-error" />
        )}

        <DisputeBanner cb={cb} />

        <TotalsGrid totals={cb.totals} />

        {/* ── Tombol siklus: langkah berikutnya menonjol, sisanya tindakan lain ── */}
        <div className="flex flex-wrap items-center gap-2" data-testid="cb-detail-actions">
          {step && canWrite && (
            <button className="primary-button" data-testid="cb-action-primary"
              disabled={!!busy} onClick={primaryAction}>
              {busy ? <RefreshCw size={14} className="spin" /> : <CheckCircle2 size={14} />}
              {step.label}
            </button>
          )}
          {canWrite && cb.status === "scheduled_payment" && (
            <button className="secondary-button" data-testid="cb-action-reschedule"
              onClick={() => setModal("schedule")}>
              Ubah jadwal bayar
            </button>
          )}
          {canWrite && ["submitted", "verified", "approved", "scheduled_payment"].includes(cb.status)
            && Number((cb.totals || {}).paid_total) === 0 && (
            <button className="secondary-button" data-testid="cb-action-dispute"
              onClick={() => setModal("dispute")}>
              <AlertTriangle size={14} /> Sengketakan
            </button>
          )}
          {canWrite && ["draft", "submitted", "verified", "disputed"].includes(cb.status) && (
            <button className="secondary-button" data-testid="cb-action-cancel"
              style={{ color: "#B4231F" }} onClick={() => setModal("cancel")}>
              <Ban size={14} /> Batalkan
            </button>
          )}
          {!canWrite && (
            <p className="text-[11px] text-[#8E8E93]" data-testid="cb-detail-readonly">
              Peran Anda hanya bisa memantau kontrabon — keputusan atas uang ada di Keuangan.
            </p>
          )}
        </div>

        {pending.length > 0 && (
          <p className="flex items-start gap-1 rounded-md border border-[#FFE0B2] bg-[#FFFBF3] px-2 py-1.5 text-[11px] text-[#8C4A00]"
            data-testid="cb-pending-warning">
            <AlertTriangle size={11} className="mt-[2px] shrink-0" />
            {pending.length} selisih 3-way di luar toleransi belum diputus — verifikasi akan
            ditolak sampai setiap selisih punya keputusan berlabel.
          </p>
        )}

        {cb.policy_snapshot_live && (
          <p className="text-[10.5px] text-[#9A9BA3]" data-testid="cb-detail-policy">
            Toleransi berlaku {cb.policy_snapshot_live.qty_tolerance_percent}% /{" "}
            {formatCurrency(cb.policy_snapshot_live.value_tolerance_rupiah)} · ambang persetujuan{" "}
            {formatCurrency(cb.policy_snapshot_live.approval_threshold)} (di atasnya butuh peran{" "}
            {cb.policy_snapshot_live.high_value_role}) — semuanya diatur di Pengaturan → Kontrabon.
          </p>
        )}

        <BillsSection cb={cb} canDecide={canEdit} onDecide={(e) => setDecideOn(e)} />

        <DeductionsSection cb={cb} canEdit={canEdit} busy={busy}
          onAdd={() => setModal("deduction")} onRemove={removeDeduction} />

        <DecisionsSection cb={cb} />

        <PaymentsSection cb={cb} />

        <ReceiptSection receipt={receipt} loading={loadingReceipt} />

        <div>
          <p className="mb-1 text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
            Tanda Terima Kontrabon
          </p>
          <DocumentActionsBar docType="contra_bon" sourceId={cb.id} entityId={cb.entity_id}
            number={cb.number} currentUser={currentUser} />
          <p className="mt-1 text-[10.5px] text-[#9A9BA3]">
            Tanda terima memuat seluruh faktur, PO, penerimaan barang, potongan, dan nilai bersih
            — supplier bisa menandatanganinya secara elektronik.
          </p>
        </div>

        <DocRefsPanel docType="contra_bon" docId={cb.id} />

        <TimelineSection cb={cb} />
      </div>

      {modal === "deduction" && (
        <DeductionModal cb={cb} meta={meta} onClose={() => setModal("")}
          onSaved={(updated) => {
            setModal("");
            onChanged(updated);
            onNotify?.("Potongan ditambahkan — nilai bersih kontrabon dihitung ulang.");
          }}
          onError={onError} />
      )}

      {decideOn && (
        <DecisionModal cb={cb} exception={decideOn} meta={meta} onClose={() => setDecideOn(null)}
          onSaved={(updated, action) => {
            setDecideOn(null);
            onChanged(updated);
            onNotify?.(action === "deduct"
              ? "Selisih diputus DIPOTONG — potongan berikut jurnalnya dibuat otomatis."
              : action === "dispute"
                ? "Selisih disengketakan — kontrabon ditahan sampai supplier mengoreksi faktur."
                : "Selisih diterima — tagihan tetap dibayar penuh.",
            action === "dispute" ? "warning" : "success");
          }}
          onError={onError} />
      )}

      {modal === "schedule" && (
        <PaymentScheduleModal cb={cb} onClose={() => setModal("")}
          onSaved={(updated) => {
            setModal("");
            onChanged(updated);
            onNotify?.(`Pembayaran ${updated.number} dijadwalkan `
              + `${fmtDate((updated.schedule || {}).planned_payment_date)}.`);
          }}
          onError={onError} />
      )}

      {modal === "pay" && (
        <PayModal cb={cb} onClose={() => setModal("")}
          onPaid={(updated) => {
            setModal("");
            onChanged(updated);
            const res = updated.payment_result || {};
            const cash = res.cash_transaction || {};
            onNotify?.(`Pembayaran dicatat: ${formatCurrency(
              (updated.payments || []).slice(-1)[0]?.amount)}`
              + (cash.number ? ` lewat kas ${cash.number}` : "")
              + (res.deductions_applied
                ? ` · potongan ${formatCurrency(res.deductions_applied)} diterapkan non-kas`
                : "")
              + (updated.status === "paid" ? " — kontrabon LUNAS." : "."));
          }}
          onError={onError} />
      )}

      {(modal === "dispute" || modal === "cancel") && (
        <ReasonNoteModal cb={cb} kind={modal} meta={meta} onClose={() => setModal("")}
          onDone={(updated) => {
            const kind = modal;
            setModal("");
            onChanged(updated);
            onNotify?.(kind === "dispute"
              ? `${updated.number} masuk status Sengketa — supplier diminta mengoreksi fakturnya.`
              : `${updated.number} dibatalkan — fakturnya dilepas dan bisa dikontrabon ulang.`,
            "warning");
          }}
          onError={onError} />
      )}
    </div>
  );
}
