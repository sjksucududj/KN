/** Sub-fase 1.11 — Return detail panel with approve/reject/upload. */
import { useState, useRef, useEffect } from "react";
import axios, { API } from "../../services/apiClient";
import {
  AlertCircle, ArrowLeft, Check, CheckCircle2, FileText, Loader2,
  Package, Paperclip, Receipt, RotateCcw, Upload, X, XCircle,
} from "lucide-react";
import { ReturnTypeBadge, ReturnStatusPill, OUTCOME_LABEL, fmtNum, fmtDate } from "./ReturnShared";
import ReturnTimeline from "../../components/ReturnTimeline";
import ReturnInspectPanel from "./ReturnInspectPanel";
import ReturnSettleModal from "./ReturnSettleModal";
import ReturnQuarantinePanel from "./ReturnQuarantinePanel";
import ReturnChainPanel from "./ReturnChainPanel";
import DocumentActionsBar from "../documents/DocumentActionsBar";
import QtyDual from "../../components/QtyDual";      // FASE U — dua satuan

const TERMINAL = ["refund_settled", "credit_settled", "nego_settled", "rejected", "cancelled"];

export default function ReturnDetail({
  ret, token, canApprove, currentUser,
  onApprove, onReject, onSubmit, onStartInspect, onCompleteInspect, onSettle, onReverse, onBack,
  onAttachmentUploaded, notice, onClearNotice, onNavigate,
}) {
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [showSettleModal, setShowSettleModal] = useState(false);
  const [showReverseModal, setShowReverseModal] = useState(false);
  const [reverseReason, setReverseReason]     = useState("");
  const [reversing, setReversing]             = useState(false);
  const [rejectReason, setRejectReason]       = useState("");
  const [uploading, setUploading]             = useState(false);
  const [localError, setLocalError]           = useState(null);
  const [creditNote, setCreditNote]           = useState(null);
  const fileRef = useRef(null);
  const isTerminal = TERMINAL.includes(ret.status);
  const canReject = ["pending_approval", "approved", "inspecting", "inspected"].includes(ret.status);
  const isSettled = ["refund_settled", "credit_settled", "nego_settled"].includes(ret.status);

  // F3 — ambil detail Nota Kredit bila retur sudah menghasilkan credit note.
  useEffect(() => {
    let active = true;
    async function loadCN() {
      if (!ret?.credit_note_id && !ret?.credit_note_number) { setCreditNote(null); return; }
      try {
        const res = await axios.get(`${API}/credit-notes`, {
          headers: { Authorization: `Bearer ${token}` },
          params: { return_id: ret.id },
        });
        const items = res.data?.items || [];
        if (active) setCreditNote(items[0] || null);
      } catch (_) { /* best-effort: chip ringkas tetap tampil dari field ret */ }
    }
    loadCN();
    return () => { active = false; };
  }, [ret?.id, ret?.credit_note_id, ret?.credit_note_number, token]);

  async function uploadFile(file) {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await axios.post(
        `${API}/sales-returns/${ret.id}/attachments`,
        fd,
        { headers: { Authorization: `Bearer ${token}`, "Content-Type": "multipart/form-data" } }
      );
      const updated = await axios.get(`${API}/sales-returns/${ret.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      onAttachmentUploaded(updated.data);
    } catch (e) {
      setLocalError("Upload gagal: " + (e.response?.data?.detail || e.message));
    } finally { setUploading(false); }
  }

  const attachments = (ret.attachments || []).filter(a => !a.is_deleted);

  // R2 — refresh dokumen retur (dipakai setelah release/scrap roll karantina).
  async function refetchReturn() {
    try {
      const updated = await axios.get(`${API}/sales-returns/${ret.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      onAttachmentUploaded(updated.data);
    } catch (_) { /* best-effort */ }
  }

  // R5.4 — reversal/koreksi retur yang sudah settled.
  async function submitReverse() {
    if (!reverseReason.trim()) return;
    setReversing(true);
    try {
      await onReverse(ret, reverseReason.trim());
      setShowReverseModal(false);
      setReverseReason("");
    } catch (e) {
      setLocalError("Gagal reversal: " + (e.response?.data?.detail || e.message));
    } finally {
      setReversing(false);
    }
  }

  return (
    <div data-testid="return-detail-view" className="view-container">
      <button className="back-button" onClick={onBack} data-testid="return-back-btn">
        <ArrowLeft size={14} /> Kembali ke Daftar Return
      </button>

      {notice && (
        <div className="notice-bar success" data-testid="return-notice">
          <CheckCircle2 size={14} /> {notice}
          <button onClick={onClearNotice}><X size={12} /></button>
        </div>
      )}
      {localError && (
        <div className="notice-bar danger">
          <AlertCircle size={14} /> {localError}
          <button onClick={() => setLocalError(null)}><X size={12} /></button>
        </div>
      )}

      <div className="detail-header">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="detail-title" data-testid="return-number">{ret.number}</h2>
            <ReturnTypeBadge type={ret.return_type} />
            <ReturnStatusPill status={ret.status} />
          </div>
          <p className="detail-subtitle">
            Pesanan: <strong>{ret.order_number}</strong>
            {ret.customer_name && <> · Customer: <strong>{ret.customer_name}</strong></>}
            {" "}· Dibuat: {fmtDate(ret.created_at)} oleh {ret.created_by || "-"}
          </p>
        </div>
        <div className="detail-actions">
          {ret.status === "draft" && (
            <button data-testid="submit-return-btn" className="secondary-button" onClick={() => onSubmit(ret)}>
              <FileText size={13} /> Kirim untuk Persetujuan
            </button>
          )}
          {ret.status === "pending_approval" && canApprove && (
            <button data-testid="approve-return-btn" className="primary-button" onClick={() => onApprove(ret)}>
              <Check size={13} /> Setujui (Manager)
            </button>
          )}
          {ret.status === "inspected" && canApprove && (
            <button data-testid="open-settle-btn" className="primary-button" onClick={() => setShowSettleModal(true)}>
              <Receipt size={13} /> Selesaikan (Pilih Outcome)
            </button>
          )}
          {canReject && (
            <button data-testid="reject-return-btn" className="danger-button" onClick={() => setShowRejectModal(true)}>
              <X size={13} /> Tolak
            </button>
          )}
          {ret.status === "approved" && (
            <div className="info-chip success">
              <CheckCircle2 size={13} /> Disetujui oleh {ret.approved_by} · {fmtDate(ret.approved_at)}
            </div>
          )}
          {["refund_settled", "credit_settled", "nego_settled"].includes(ret.status) && (
            <div className="info-chip success" data-testid="return-outcome-chip">
              <CheckCircle2 size={13} /> Selesai: {OUTCOME_LABEL[ret.outcome] || ret.outcome}
              {ret.settled_by ? ` · oleh ${ret.settled_by}` : ""}
            </div>
          )}
          {isSettled && canApprove && (
            <button data-testid="reverse-return-btn" className="danger-button" onClick={() => setShowReverseModal(true)}>
              <RotateCcw size={13} /> Batal / Pembalikan
            </button>
          )}
          {ret.credit_note_number && (
            <div className="info-chip success" data-testid="return-credit-note-chip">
              <Receipt size={13} /> Nota Kredit: {ret.credit_note_number}
            </div>
          )}
          {ret.status === "rejected" && (
            <div className="info-chip danger">
              <XCircle size={13} /> Ditolak oleh {ret.rejected_by} · Alasan: {ret.reject_reason}
            </div>
          )}
          {ret.status === "cancelled" && ret.reversed && (
            <div className="info-chip danger" data-testid="return-reversed-chip">
              <RotateCcw size={13} /> Dibatalkan (Pembalikan){ret.reversed_by ? ` oleh ${ret.reversed_by}` : ""}
              {ret.reversal_reason ? ` · ${ret.reversal_reason}` : ""}
            </div>
          )}
        </div>
      </div>

      <DocumentActionsBar docType="sales_return" sourceId={ret.id} entityId={ret.entity_id}
        number={ret.number} label="Nota Retur Jual" esignable={false} currentUser={currentUser}
        className="mb-3 rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] px-2.5 py-2" />

      {/* R2 — Inspeksi 4-point (approved → inspecting → inspected) */}
      <ReturnInspectPanel ret={ret} onStartInspect={onStartInspect} onCompleteInspect={onCompleteInspect} />

      <div className="detail-grid-2col">
        <div className="section-card">
          <div className="section-header"><Package size={14} /> Item yang Diretur</div>
          <table className="data-table">
            <thead>
              <tr><th>Produk</th><th>Qty</th><th>Sat.</th><th>Kondisi</th><th>Alasan</th></tr>
            </thead>
            <tbody>
              {(ret.items || []).map((item, i) => (
                <tr key={i}>
                  <td>
                    <div className="font-medium">{item.product_name || item.product_id}</div>
                    <div className="text-xs text-muted font-mono">{item.sku || "—"}</div>
                  </td>
                  <td className="font-mono"><strong><QtyDual rolls={item.qty_rolls} measure={item.quantity_returned} unit={item.unit} compact /></strong></td>
                  <td>{item.unit}</td>
                  <td>
                    <span className={`feature-badge ${item.condition === "ok" ? "badge-green" : "badge-orange"}`}>
                      {item.condition === "ok" ? "Baik" : "Rusak"}
                    </span>
                  </td>
                  <td className="text-muted text-sm">{item.reason || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {ret.notes && <div className="section-notes"><strong>Catatan:</strong> {ret.notes}</div>}
        </div>

        <div className="section-card">
          <div className="section-header">
            <Paperclip size={14} /> Lampiran Bukti
            {!isTerminal && (
              <button data-testid="upload-attachment-btn" className="link-button ml-auto"
                onClick={() => fileRef.current?.click()} disabled={uploading}>
                {uploading ? <Loader2 size={12} className="spin" /> : <Upload size={12} />} Upload
              </button>
            )}
          </div>
          <input ref={fileRef} type="file" accept="image/*,.pdf" style={{ display: "none" }}
            data-testid="attachment-file-input"
            onChange={e => { if (e.target.files[0]) uploadFile(e.target.files[0]); e.target.value = ""; }} />
          {attachments.length === 0 ? (
            <div className="empty-state small">
              <Paperclip size={18} style={{ opacity: 0.3 }} />
              <p>Belum ada lampiran.</p>
              {!isTerminal && (
                <button className="link-button" onClick={() => fileRef.current?.click()}>+ Upload foto / dokumen</button>
              )}
            </div>
          ) : (
            <div className="attachments-grid">
              {attachments.map(att => (
                <div key={att.id} className="attachment-chip" data-testid={`attachment-${att.id}`}>
                  <Paperclip size={11} />
                  <a href={`${API}/sales-returns/${ret.id}/attachments/${att.id}/download`}
                    target="_blank" rel="noreferrer" className="link-button">{att.filename}</a>
                  <span className="text-muted text-xs">{(att.size / 1024).toFixed(0)} KB</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* F3 — Nota Kredit (Credit Note) hasil retur yang sudah di-approve */}
      {(creditNote || ret.credit_note_number) && (
        <div className="section-card" data-testid="return-credit-note-section">
          <div className="section-header">
            <Receipt size={14} /> Nota Kredit
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-muted">Nomor CN</div>
              <div className="font-semibold font-mono" data-testid="credit-note-number">
                {creditNote?.number || ret.credit_note_number}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted">Nilai Bruto</div>
              <div className="font-bold tabular-nums" data-testid="credit-note-gross">
                Rp {fmtNum(creditNote?.gross_amount ?? ret.credit_note_amount, 0)}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted">DPP / PPN</div>
              <div className="font-medium tabular-nums">
                Rp {fmtNum(creditNote?.net_amount, 0)} / Rp {fmtNum(creditNote?.ppn_amount, 0)}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted">Penyelesaian</div>
              <div>
                <span className={`feature-badge ${creditNote?.settlement === "cash" ? "badge-green" : "badge-blue"}`}>
                  {{ cash: "Refund Tunai", ar: "Pengurang Piutang", store_credit: "Store Credit", nego: "Diskon Nego" }[creditNote?.settlement] || "Pengurang Piutang"}
                </span>
              </div>
            </div>
          </div>
          {creditNote?.cogs_amount > 0 && (
            <div className="section-notes" data-testid="credit-note-cogs">
              Pembalikan HPP (barang kembali ke stok): Rp {fmtNum(creditNote.cogs_amount, 0)}
            </div>
          )}
          <div className="section-notes text-muted">
            Posting GL otomatis: Dr Pendapatan{creditNote?.ppn_amount > 0 ? " + Dr PPN Keluaran" : ""} / Cr {creditNote?.settlement === "cash" ? "Kas" : "Piutang"}
            {creditNote?.cogs_amount > 0 ? " · Dr Persediaan / Cr HPP" : ""}.
          </div>
        </div>
      )}

      <ReturnTimeline ret={ret} variant="sales" />

      {/* R2 — Karantina roll retur (release ke stok / scrap) */}
      <ReturnQuarantinePanel ret={ret} canApprove={canApprove} onReleased={refetchReturn}
        onNavigate={onNavigate} />

      {/* FASE E-9 (E9.6 · US29) — rantai retur utuh: pelanggan → antar-PT → beli/simpan */}
      <ReturnChainPanel docId={ret.id} />

      <ReturnSettleModal ret={ret} open={showSettleModal}
        onClose={() => setShowSettleModal(false)} onSettle={onSettle} />

      {showRejectModal && (
        <div className="modal-overlay" data-testid="reject-modal">
          <div className="modal-card small">
            <h3 className="modal-title">Tolak Return {ret.number}?</h3>
            <p className="modal-subtitle">Berikan alasan penolakan</p>
            <textarea data-testid="reject-reason-input" className="textarea" rows={3}
              placeholder="Alasan penolakan..." value={rejectReason} onChange={e => setRejectReason(e.target.value)} />
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => setShowRejectModal(false)}>Batal</button>
              <button data-testid="confirm-reject-btn" className="danger-button"
                disabled={!rejectReason.trim()}
                onClick={() => { onReject(ret, rejectReason); setShowRejectModal(false); setRejectReason(""); }}>
                <X size={13} /> Tolak Return
              </button>
            </div>
          </div>
        </div>
      )}

      {showReverseModal && (
        <div className="modal-overlay" data-testid="reverse-modal">
          <div className="modal-card small">
            <h3 className="modal-title">Batal / Pembalikan Retur {ret.number}?</h3>
            <p className="modal-subtitle">
              Tindakan ini membalik jurnal (GL), menghapus roll retur yang masuk stok,
              membatalkan refund kas & store credit, serta membatalkan Nota Kredit. Riwayat tetap tersimpan (audit).
            </p>
            <div className="rounded-md bg-[#FDF3E7] border border-[#F5E0C3] px-3 py-2 text-[12px] text-[#B45309] mb-2 flex items-start gap-1.5">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>Reversal ditolak jika roll retur sudah dilepas dari karantina, sudah dipesan/terpakai, atau saldo store credit sudah dipakai.</span>
            </div>
            <textarea data-testid="reverse-reason-input" className="textarea" rows={3}
              placeholder="Alasan pembatalan / koreksi..." value={reverseReason} onChange={e => setReverseReason(e.target.value)} />
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => { setShowReverseModal(false); setReverseReason(""); }} data-testid="reverse-cancel-btn">Batal</button>
              <button data-testid="confirm-reverse-btn" className="danger-button"
                disabled={!reverseReason.trim() || reversing}
                onClick={submitReverse}>
                {reversing ? <Loader2 size={13} className="spin" /> : <RotateCcw size={13} />} Lakukan Pembalikan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
