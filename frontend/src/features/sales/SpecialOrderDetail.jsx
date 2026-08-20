/**
 * Special Order Detail View
 * Shows status timeline, custom item details, approval actions
 */
import { useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  AlertCircle, ArrowLeft, Check, CheckCircle2, ClipboardList, Loader2,
  ShoppingCart, Sparkles, Tag, X, XCircle
} from "lucide-react";
import { StatusPill, fmtDate } from "./SpecialOrderShared";
import { SpecialOrderInfoPanels } from "./SpecialOrderInfoPanels";
import DocumentActionsBar from "../documents/DocumentActionsBar";
import { askConfirm } from "@/services/confirmService";


export default function SpecialOrderDetail({
  order,
  token,
  currentUser,
  onBack,
  onUpdate,
  notice,
  onClearNotice
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [okMsg, setOkMsg] = useState(null);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const canApprove = order.status === "pending_approval" && ["manager", "admin"].includes(currentUser?.role);
  const canTransition = ["admin", "manager"].includes(currentUser?.role);

  // F3 MTO — gating tombol SKU & konversi
  const skuStages = ["confirmed", "in_production", "ready"];
  const canCreateSku = canTransition && skuStages.includes(order.status) && !order.linked_product_id;
  const canConvert = canTransition && !!order.linked_product_id && !order.linked_sales_order_id
    && skuStages.includes(order.status);

  async function handleCreateSku() {
    const ok = await askConfirm({
      title: `Buat SKU produk katalog dari ${order.number}?`,
      message: "Spesifikasi pesanan khusus ini disalin menjadi produk katalog sehingga bisa "
        + "dipesan ulang tanpa mengisi spesifikasi dari awal.",
      confirmLabel: "Buat SKU",
      testId: "so-create-sku-confirm",
    });
    if (!ok) return;
    setLoading(true);
    try {
      const res = await axios.post(
        `${API}/special-orders/${order.id}/create-sku`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      onUpdate(res.data.special_order);
      setOkMsg(`SKU produk dibuat: ${res.data.product?.sku} — ${res.data.product?.name}`);
      setError(null);
    } catch (e) {
      setError("Gagal membuat SKU: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  async function handleConvertToSo() {
    const ok = await askConfirm({
      title: `Konversi ${order.number} menjadi Pesanan Penjualan?`,
      message: "Pesanan penjualan standar dibuat dari pesanan khusus ini, lalu masuk alur "
        + "pemenuhan biasa (reservasi stok → gudang → kirim).",
      confirmLabel: "Konversi ke SO",
      testId: "so-convert-confirm",
    });
    if (!ok) return;
    setLoading(true);
    try {
      const res = await axios.post(
        `${API}/special-orders/${order.id}/convert-to-so`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      onUpdate(res.data.special_order);
      setOkMsg(`Berhasil dikonversi ke Sales Order ${res.data.sales_order?.number} (status: ${res.data.sales_order?.status}).`);
      setError(null);
    } catch (e) {
      setError("Gagal konversi ke SO: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove() {
    const ok = await askConfirm({
      title: `Setujui pesanan khusus ${order.number}?`,
      message: "Setelah disetujui, pesanan bisa lanjut ke pembuatan SKU / produksi.",
      confirmLabel: "Setujui",
      testId: "so-approve-confirm",
    });
    if (!ok) return;

    setLoading(true);
    try {
      const res = await axios.post(
        `${API}/special-orders/${order.id}/approve`,
        { notes: "" },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      onUpdate(res.data);
    } catch (e) {
      setError("Gagal approve: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  async function handleReject() {
    if (!rejectReason.trim()) return;

    setLoading(true);
    try {
      const res = await axios.post(
        `${API}/special-orders/${order.id}/reject`,
        { reason: rejectReason },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      onUpdate(res.data);
      setShowRejectModal(false);
      setRejectReason("");
    } catch (e) {
      setError("Gagal reject: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  async function handleStatusTransition(newStatus) {
    const ok = await askConfirm({
      title: `Ubah status menjadi "${newStatus}"?`,
      message: "Perubahan status tercatat pada riwayat pesanan khusus ini.",
      confirmLabel: "Ubah Status",
      testId: "so-status-confirm",
    });
    if (!ok) return;

    setLoading(true);
    try {
      const res = await axios.post(
        `${API}/special-orders/${order.id}/status`,
        { status: newStatus, notes: "" },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      onUpdate(res.data);
    } catch (e) {
      setError("Gagal update status: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreatePR() {
    const ok = await askConfirm({
      title: "Buat Permintaan Pembelian (PR) untuk pesanan khusus ini?",
      message: "PR langsung diajukan supaya bagian pembelian bisa mencari supplier untuk "
        + "bahan yang dibutuhkan.",
      confirmLabel: "Buat & Ajukan PR",
      testId: "so-create-pr-confirm",
    });
    if (!ok) return;
    setLoading(true);
    try {
      const res = await axios.post(
        `${API}/special-orders/${order.id}/create-pr`,
        { submit_now: true },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      onUpdate(res.data.special_order);
      setError(null);
    } catch (e) {
      setError("Gagal membuat PR: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  // Status transition buttons based on current status
  const statusActions = {
    confirmed: { next: "in_production", label: "Mulai Produksi" },
    in_production: { next: "ready", label: "Tandai Siap" },
    ready: { next: "shipped", label: "Kirim ke Pelanggan" },
    shipped: { next: "done", label: "Tandai Selesai" },
  };

  const action = statusActions[order.status];

  return (
    <div data-testid="special-order-detail-view" className="view-container">
      {/* Back */}
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={14} /> Kembali ke Daftar Pesanan Khusus
      </button>

      {/* Notice */}
      {notice && (
        <div className="notice-bar success">
          <CheckCircle2 size={14} /> {notice}
          <button onClick={onClearNotice}><X size={12} /></button>
        </div>
      )}

      {/* F3 success notice (lokal) */}
      {okMsg && (
        <div className="notice-bar success" data-testid="special-order-ok-notice">
          <CheckCircle2 size={14} /> {okMsg}
          <button onClick={() => setOkMsg(null)}><X size={12} /></button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="notice-bar danger">
          <AlertCircle size={14} /> {error}
          <button onClick={() => setError(null)}><X size={12} /></button>
        </div>
      )}

      {/* Header */}
      <div className="detail-header">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="detail-title" data-testid="special-order-number">
              <Sparkles size={18} className="text-purple-500" /> {order.number}
            </h2>
            <StatusPill status={order.status} />
            {order.requires_approval && order.status === "pending_approval" && (
              <span className="feature-badge badge-orange">Butuh Persetujuan</span>
            )}
          </div>
          <p className="detail-subtitle">
            Pelanggan: <strong>{order.customer_name}</strong>
            {" "}• Dibuat: {fmtDate(order.created_at)} oleh {order.created_by}
          </p>
        </div>

        {/* Actions */}
        <div className="detail-actions">
          {canApprove && (
            <>
              <button
                data-testid="approve-special-order-btn"
                className="primary-button"
                onClick={handleApprove}
                disabled={loading}
              >
                <Check size={13} /> Setujui
              </button>
              <button
                data-testid="reject-special-order-btn"
                className="danger-button"
                onClick={() => setShowRejectModal(true)}
                disabled={loading}
              >
                <X size={13} /> Reject
              </button>
            </>
          )}

          {action && canTransition && (
            <button
              data-testid="status-transition-btn"
              className="secondary-button"
              onClick={() => handleStatusTransition(action.next)}
              disabled={loading}
            >
              {loading ? <Loader2 size={13} className="spin" /> : <Check size={13} />}
              {action.label}
            </button>
          )}

          {["confirmed", "in_production"].includes(order.status) && !order.linked_pr_id && (
            <button
              data-testid="special-order-create-pr-btn"
              className="primary-button"
              onClick={handleCreatePR}
              disabled={loading}
              title="Jembatan ke pengadaan (Permintaan Pembelian)"
            >
              {loading ? <Loader2 size={13} className="spin" /> : <ClipboardList size={13} />}
              Buat PR Pengadaan
            </button>
          )}

          {order.linked_pr_number && (
            <div className="info-chip success" data-testid="special-order-linked-pr">
              <ClipboardList size={13} />
              PR: {order.linked_pr_number}
            </div>
          )}

          {/* F3 MTO — Buat SKU produk katalog dari item custom */}
          {canCreateSku && (
            <button
              data-testid="special-order-create-sku-btn"
              className="primary-button"
              onClick={handleCreateSku}
              disabled={loading}
              title="Materialisasi item custom menjadi SKU produk di katalog"
            >
              {loading ? <Loader2 size={13} className="spin" /> : <Tag size={13} />}
              Buat SKU Produk
            </button>
          )}

          {/* F3 MTO — Konversi ke Sales Order standar */}
          {canConvert && (
            <button
              data-testid="special-order-convert-btn"
              className="primary-button"
              onClick={handleConvertToSo}
              disabled={loading}
              title="Ubah pesanan khusus menjadi Pesanan Penjualan standar"
            >
              {loading ? <Loader2 size={13} className="spin" /> : <ShoppingCart size={13} />}
              Ubah ke Pesanan Penjualan
            </button>
          )}

          {/* F3 MTO — chip SKU tertaut */}
          {order.linked_product_id && (
            <div className="info-chip success" data-testid="special-order-linked-sku">
              <Tag size={13} />
              SKU: {order.linked_product_sku || order.linked_product_id}
            </div>
          )}

          {/* F3 MTO — chip Sales Order hasil konversi */}
          {order.linked_sales_order_number && (
            <div className="info-chip success" data-testid="special-order-linked-so">
              <ShoppingCart size={13} />
              SO: {order.linked_sales_order_number}
            </div>
          )}

          {order.status === "approved" && (
            <div className="info-chip success">
              <CheckCircle2 size={13} />
              Disetujui oleh {order.approved_by} pada {fmtDate(order.approved_at)}
            </div>
          )}

          {order.status === "cancelled" && (
            <div className="info-chip danger">
              <XCircle size={13} />
              {order.rejected_by ? (
                <>Ditolak: {order.reject_reason}</>
              ) : (
                <>Dibatalkan</>
              )}
            </div>
          )}
        </div>
      </div>

      {/* PS-20 — rantai persetujuan berjenjang (Manager → Direksi bila nilai besar).
          Pembuat dokumen bisa melihat sampai tingkat mana pesanannya sudah disetujui. */}
      {(order.approval_chain || []).length > 0 && (
        <div className="mb-3 rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] px-2.5 py-2"
          data-testid="special-order-approval-chain">
          <p className="text-[10.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
            Persetujuan berjenjang ({(order.approval_chain || []).filter((l) => l.status === "approved").length}
            /{(order.approval_chain || []).length} tingkat)
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {(order.approval_chain || []).map((lv) => (
              <span key={lv.level}
                data-testid={`special-order-chain-level-${lv.level}`}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${
                  lv.status === "approved"
                    ? "bg-[#E9F7EF] text-[#1B7F4B]"
                    : "bg-[#FFF4E5] text-[#B45309]"}`}>
                {lv.status === "approved" ? "✓" : "○"} {lv.level}. {lv.label}
                {lv.status === "approved" && lv.approved_by ? ` · ${lv.approved_by}` : ""}
              </span>
            ))}
          </div>
        </div>
      )}
      {/* Dokumen: pratinjau / unduh PDF / e-sign / kirim WA */}
      <DocumentActionsBar docType="special_order" sourceId={order.id} entityId={order.entity_id}
        number={order.number} label="Pesanan Khusus" esignable currentUser={currentUser}
        onChanged={() => onUpdate && onUpdate(order)}
        className="mb-3 rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] px-2.5 py-2" />

      {/* Main content */}
      <SpecialOrderInfoPanels order={order} />

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="modal-overlay" data-testid="reject-modal">
          <div className="modal-card small">
            <h3 className="modal-title">Tolak Pesanan Khusus {order.number}?</h3>
            <p className="modal-subtitle">Berikan alasan penolakan</p>
            <textarea
              data-testid="reject-reason-input"
              className="textarea"
              rows={3}
              placeholder="Alasan penolakan..."
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
            />
            <div className="modal-actions">
              <button className="secondary-button" onClick={() => setShowRejectModal(false)}>
                Batal
              </button>
              <button
                data-testid="confirm-reject-btn"
                className="danger-button"
                disabled={!rejectReason.trim() || loading}
                onClick={handleReject}
              >
                {loading ? <Loader2 size={13} className="spin" /> : <X size={13} />}
                {" "}Tolak Pesanan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
