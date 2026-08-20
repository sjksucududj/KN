import { useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  ArrowLeft, CheckCircle2, XCircle, Send, Banknote, Printer, Pencil,
  FileText, Clock, Building2, ReceiptText,
} from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ConfirmModal from "../../components/ConfirmModal";
import {
  CA_STATUS, StatusPill, fmtDate, printCashAdvance, printTandaTerima,
} from "./pettyCashShared";

/**
 * CashAdvanceDetail — Detail Form PD: ringkasan, rincian, timeline approval,
 * dan aksi state-machine (submit → approve/reject berjenjang → disburse) + cetak.
 */
export default function CashAdvanceDetail({ ca, currentUser, entities, onBack, onEdit, onChanged, flash }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [reject, setReject] = useState(false);
  const [disburse, setDisburse] = useState(false);
  const [cashType, setCashType] = useState("kas_kecil");

  const role = currentUser?.role;
  const entityName = entities.find((e) => e.id === ca.entity_id)?.short_name
    || entities.find((e) => e.id === ca.entity_id)?.legal_name || ca.entity_id;

  const isPending = ["pending_atasan", "pending_pimpinan", "pending_finance"].includes(ca.status);
  const stageRoles = {
    pending_atasan: ["manager", "admin"], pending_pimpinan: ["admin"], pending_finance: ["admin"],
  };
  const canApproveStage = isPending && (role === "admin" || (stageRoles[ca.status] || []).includes(role));
  const canEdit = ["draft", "rejected"].includes(ca.status) && ["admin", "manager", "sales"].includes(role);
  const canSubmit = ["draft", "rejected"].includes(ca.status) && ["admin", "manager", "sales"].includes(role);
  const canDisburse = ca.status === "approved" && role === "admin";

  async function act(path, body, okMsg) {
    setBusy(true); setErr("");
    try {
      const res = await axios.post(`${API}/cash-advances/${ca.id}/${path}`, body || {});
      flash(okMsg);
      onChanged(res.data);
    } catch (e) {
      setErr(e.response?.data?.detail || "Aksi gagal.");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="ca-detail" className="grid gap-4">
      {/* Header */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <button className="icon-button" onClick={onBack} aria-label="Kembali"><ArrowLeft size={15} /></button>
            <FileText size={15} className="text-[#0058CC]" />
            <h2 data-testid="ca-detail-number">{ca.number}</h2>
            <StatusPill status={ca.status} testId="ca-detail-status" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button data-testid="ca-print" className="btn-secondary btn-xs" onClick={() => printCashAdvance(ca, entityName)}><Printer size={13} /> Cetak PD</button>
            {ca.status === "disbursed" || ca.status === "settled" ? (
              <button data-testid="ca-print-tt" className="btn-secondary btn-xs" onClick={() => printTandaTerima({
                dari: entityName, nama: ca.created_by, berupa: "Uang Tunai (Pencairan PD)",
                jumlah: ca.total_amount, keterangan: `${ca.number} — ${ca.kegiatan || ""}`, entityName,
              })}><ReceiptText size={13} /> Tanda Terima</button>
            ) : null}
            {canEdit && <button data-testid="ca-edit" className="btn-secondary btn-xs" onClick={() => onEdit(ca)}><Pencil size={13} /> Ubah</button>}
            {canSubmit && <button data-testid="ca-submit-btn" className="btn-primary btn-xs" onClick={() => act("submit", {}, `${ca.number} diajukan untuk persetujuan.`)} disabled={busy}><Send size={13} /> Ajukan</button>}
            {canApproveStage && <>
              <button data-testid="ca-approve-btn" className="btn-primary btn-xs" onClick={() => act("approve", { note: "" }, `${ca.number} disetujui tahap ini.`)} disabled={busy}><CheckCircle2 size={13} /> Setujui</button>
              <button data-testid="ca-reject-btn" className="btn-danger btn-xs" onClick={() => setReject(true)} disabled={busy}><XCircle size={13} /> Tolak</button>
            </>}
            {canDisburse && <button data-testid="ca-disburse-btn" className="btn-primary btn-xs" onClick={() => setDisburse(true)} disabled={busy}><Banknote size={13} /> Cairkan</button>}
          </div>
        </div>
        {err && <div className="notice-bar danger mx-3 mb-3" data-testid="ca-detail-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}
        {busy && <div data-testid="ca-detail-loading" className="mx-3 mb-2 h-1 rounded bg-[#E7F0FF] overflow-hidden"><div className="h-full w-1/3 bg-[#0058CC] animate-pulse" /></div>}

        <div className="section-body grid gap-4">
          {/* Meta */}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-[12px]">
            <Meta icon={Building2} k="Entitas" v={entityName} />
            <Meta k="Divisi" v={ca.divisi || "—"} />
            <Meta k="Tanggal" v={fmtDate(ca.tanggal_pengajuan)} />
            <Meta k="Kegiatan" v={ca.kegiatan || "—"} />
            <Meta k="Periode" v={`${fmtDate(ca.period_from)} — ${fmtDate(ca.period_to)}`} />
            <Meta k="Metode" v={ca.payment_method === "transfer" ? `Transfer · ${ca.bank_detail?.bank || ""} ${ca.bank_detail?.no_account || ""}` : "Tunai"} />
            <Meta k="Dibuat oleh" v={ca.created_by || "—"} />
            {ca.disbursement && <Meta k="Kas Keluar" v={`${ca.disbursement.cash_txn_number} · ${ca.disbursement.cash_type === "kas_besar" ? "Kas Besar" : "Kas Kecil"}`} />}
            {ca.rejected_reason && <Meta k="Alasan Tolak" v={ca.rejected_reason} danger />}
          </div>

          {/* Lines */}
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1.6fr_90px_100px_130px_130px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
              <span>Uraian</span><span className="text-right">Qty</span><span>Satuan</span><span className="text-right">Harga</span><span className="text-right">Jumlah</span>
            </div>
            {(ca.lines || []).map((l, i) => (
              <div key={i} className="grid grid-cols-[1.6fr_90px_100px_130px_130px] items-center px-3 py-2 border-t border-[#F4F5F7] text-[12px]">
                <div className="min-w-0"><p className="font-semibold truncate">{l.description || "—"}</p>{l.catatan && <p className="text-[10.5px] text-[#9A9BA3] truncate">{l.catatan}</p>}</div>
                <span className="text-right tabular-nums">{l.qty}</span>
                <span className="capitalize">{l.satuan}</span>
                <span className="text-right tabular-nums">{formatCurrency(l.unit_price)}</span>
                <span className="text-right tabular-nums font-semibold">{formatCurrency(l.amount)}</span>
              </div>
            ))}
            {(ca.lines || []).length === 0 && (
              <div data-testid="ca-detail-lines-empty" className="px-3 py-4 text-center text-[12px] text-[#9A9BA3] border-t border-[#F4F5F7]">Belum ada rincian pada PD ini.</div>
            )}
            <div className="flex justify-between items-center px-3 py-2 border-t border-[#EFF0F2] bg-[#FAFBFC]">
              <span className="text-[11px] font-bold uppercase text-[#6B6B73]">Total Pengajuan</span>
              <span data-testid="ca-detail-total" className="text-[16px] font-bold tabular-nums text-[#0058CC]">{formatCurrency(ca.total_amount)}</span>
            </div>
          </div>

          {ca.catatan && <p className="text-[12px] text-[#3C3C43]"><b>Catatan:</b> {ca.catatan}</p>}
        </div>
      </section>

      {/* Timeline approval */}
      <section className="section-card" data-testid="ca-timeline">
        <div className="section-head"><div className="flex items-center gap-2"><Clock size={14} className="text-[#0058CC]" /><h2 className="text-[13px]">Riwayat Persetujuan</h2></div></div>
        <div className="section-body">
          {(ca.approvals || []).length === 0 ? (
            <p className="text-[12px] text-[#9A9BA3]">Belum ada aktivitas persetujuan. Status: <b>{CA_STATUS[ca.status]?.label || ca.status}</b>.</p>
          ) : (
            <div className="space-y-2.5">
              {ca.approvals.map((a, i) => (
                <div key={i} data-testid={`ca-approval-${i}`} className="flex items-start gap-2.5">
                  {a.decision === "rejected"
                    ? <XCircle size={16} className="text-red-500 mt-0.5 shrink-0" />
                    : <CheckCircle2 size={16} className="text-green-600 mt-0.5 shrink-0" />}
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold">{a.label} — {a.decision === "rejected" ? "Ditolak" : "Disetujui"}</p>
                    <p className="text-[10.5px] text-[#6B6B73]">oleh {a.by} ({a.role}) · {fmtDate(a.at)}{a.note ? ` · "${a.note}"` : ""}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <ConfirmModal
        open={reject}
        title={`Tolak ${ca.number}`}
        message="Berikan alasan penolakan. PD akan kembali ke status Ditolak dan dapat direvisi."
        confirmLabel="Tolak PD" danger withReason reasonLabel="Alasan penolakan" reasonPlaceholder="mis. Nominal melebihi anggaran"
        onConfirm={async (reason) => { setReject(false); await act("reject", { note: reason }, `${ca.number} ditolak.`); }}
        onCancel={() => setReject(false)}
        testId="ca-reject-modal"
      />

      {disburse && (
        <div className="modal-overlay" data-testid="ca-disburse-modal" onClick={(e) => { if (e.target === e.currentTarget) setDisburse(false); }}>
          <div className="modal-card small">
            <p className="modal-title">Cairkan {ca.number}</p>
            <p className="modal-subtitle">Pencairan mencatat kas keluar {formatCurrency(ca.total_amount)} & jurnal Uang Muka otomatis.</p>
            <div className="grid gap-1.5 mt-2">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Sumber Kas</label>
              <KNSelect data-testid="ca-disburse-cashtype" className="form-input" value={cashType} onValueChange={setCashType}
                options={[{ value: "kas_kecil", label: "Kas Kecil (per entitas)" }, { value: "kas_besar", label: "Kas Besar (gabungan grup)" }]} />
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setDisburse(false)}>Batal</button>
              <button data-testid="ca-disburse-confirm" className="btn-primary" disabled={busy}
                onClick={async () => { setDisburse(false); await act("disburse", { cash_type: cashType }, `${ca.number} dicairkan (${formatCurrency(ca.total_amount)}).`); }}>
                Cairkan Dana
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Meta({ icon: Icon, k, v, danger }) {
  return (
    <div className="flex gap-2">
      <span className="text-[#8E8E93] w-24 shrink-0 flex items-center gap-1">{Icon && <Icon size={12} />}{k}</span>
      <span className={`font-semibold min-w-0 break-words ${danger ? "text-red-600" : ""}`}>{v}</span>
    </div>
  );
}
