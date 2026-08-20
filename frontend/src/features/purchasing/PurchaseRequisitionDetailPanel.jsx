import { useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  ArrowLeft, CheckCircle2, XCircle, Send, ShoppingCart, AlertTriangle, Ban, Printer,
} from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import { printPurchaseRequisition } from "../../utils/docPrint";
import DocumentActionsBar from "../documents/DocumentActionsBar";
import { SOURCE_LABEL, StatusPill, Field } from "./prConstants";
import PrSourcingPanel from "./PrSourcingPanel";
import { FULFILLMENT_META } from "./supplier-items/supplierItemsApi";
import QtyDual from "../../components/QtyDual";      // FASE U — dua satuan

/**
 * DetailPanel — detail PR + aksi lifecycle (submit/approve/reject/cancel/convert).
 * Diekstrak dari PurchaseRequisitions.jsx agar file utama < 500 baris (compliance).
 */
export default function DetailPanel({ pr, canApprove, suppliers, warehouses, onBack, onChanged, reload }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [showConvert, setShowConvert] = useState(false);
  const [convSupplier, setConvSupplier] = useState(pr.preferred_supplier_id || "");
  const [convWarehouse, setConvWarehouse] = useState(pr.warehouse_id || "");
  const [convDate, setConvDate] = useState("");
  const [showReject, setShowReject] = useState(false);   // H3 — tangkap alasan tolak
  const [rejectReason, setRejectReason] = useState("");

  const nonCatalog = (pr.items || []).some((it) => !it.product_id);

  async function act(path, body) {
    setBusy(true); setErr("");
    try {
      await axios.post(`${API}/purchase-requisitions/${pr.id}${path}`, body || {});
      onChanged("Tindakan berhasil.");
      reload(pr.id);
    } catch (e) {
      setErr(e.response?.data?.detail || "Aksi gagal.");
    } finally { setBusy(false); }
  }

  async function doReject() {
    if (!rejectReason.trim()) { setErr("Alasan penolakan wajib diisi."); return; }
    setBusy(true); setErr("");
    try {
      await axios.post(`${API}/purchase-requisitions/${pr.id}/reject`, { notes: rejectReason.trim() });
      onChanged(`${pr.number} ditolak.`);
      setShowReject(false);
      reload(pr.id);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal menolak PR.");
    } finally { setBusy(false); }
  }

  async function doConvert() {    if (!convSupplier) { setErr("Pilih supplier."); return; }
    setBusy(true); setErr("");
    try {
      const res = await axios.post(`${API}/purchase-requisitions/${pr.id}/convert-to-po`, {
        supplier_id: convSupplier, warehouse_id: convWarehouse, expected_delivery_date: convDate,
      });
      onChanged(`Dikonversi ke ${res.data.po.po_number}.`);
      setShowConvert(false);
      reload(pr.id);
    } catch (e) {
      setErr(e.response?.data?.detail || "Konversi gagal.");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="pr-detail" className="grid gap-4">
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <button className="icon-button" onClick={onBack}><ArrowLeft size={15} /></button>
            <h2 data-testid="pr-detail-number">{pr.number}</h2>
            <StatusPill status={pr.status} />
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="pr-print" className="btn-secondary btn-xs" onClick={() => printPurchaseRequisition(pr, pr.entity_name || pr.entity_short_name || "")}><Printer size={13} /> Cetak PR</button>
            <span className="status-pill pill-muted">{SOURCE_LABEL[pr.source] || pr.source}</span>
          </div>
        </div>
        <div className="section-body grid gap-3">
          {err && <div className="notice-bar danger" data-testid="pr-detail-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}

          <div className="grid gap-2 sm:grid-cols-3 text-[12px]">
            <Field label="Gudang" value={pr.warehouse_name || "—"} />
            <Field label="Supplier Preferensi" value={pr.preferred_supplier_name || "—"} />
            <Field label="Dibutuhkan" value={pr.needed_by_date || "—"} />
            <Field label="Dibuat oleh" value={pr.created_by} />
            <Field label="Persetujuan" value={pr.approval_required ? `Butuh ${pr.required_approval_role || "manager"}` : "Tidak perlu"} />
            <Field label="Total Estimasi" value={formatCurrency(pr.total_est_amount)} />
          </div>
          {pr.reason && <p className="text-[12px] text-[#6B6B73]"><b>Alasan:</b> {pr.reason}</p>}
          {pr.po_number && <p className="text-[12px]" data-testid="pr-linked-po"><b>PO terkait:</b> <span className="text-[#0058CC] font-semibold">{pr.po_number}</span></p>}

          {/* Dokumen PR (mesin dokumen terpadu — PDF asli / e-sign / WA) */}
          <DocumentActionsBar docType="purchase_requisition" sourceId={pr.id} entityId={pr.entity_id}
            number={pr.number} label="Permintaan Pembelian" currentUser={{ role: "admin" }}
            className="rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] px-2.5 py-2" />


          {/* Items */}
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1.4fr_105px_100px_120px_120px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
              <span>Item</span><span>Pemenuhan</span><span className="text-right">Qty</span><span className="text-right">Est. Harga</span><span className="text-right">Subtotal</span>
            </div>
            {(pr.items || []).map((it, i) => (
              <div key={i} data-testid={`pr-detail-item-${i}`} className="grid grid-cols-[1.4fr_105px_100px_120px_120px] items-center px-3 py-2 border-t border-[#F4F5F7]">
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold truncate">{it.product_name || it.description}</p>
                  <p className="text-[10px] text-[#9A9BA3]">{it.product_id ? `${it.sku} · ${it.unit}` : <span className="text-[#8C4A00]">Non-katalog · {it.unit}</span>}</p>
                </div>
                <span>
                  <span data-testid={`pr-detail-mode-${i}`}
                    className={`status-pill ${(FULFILLMENT_META[it.fulfillment_mode || "purchase"] || {}).cls || "pill-muted"}`}>
                    {(FULFILLMENT_META[it.fulfillment_mode || "purchase"] || {}).label || "Beli"}
                  </span>
                </span>
                <span className="text-[12px] tabular-nums text-right"><QtyDual rolls={it.qty_rolls} measure={it.quantity} unit={it.unit} factor={it.unit_factor} factorTo={it.unit_factor_to} /></span>
                <span className="text-[12px] tabular-nums text-right">{formatCurrency(it.est_price)}</span>
                <span className="text-[12px] tabular-nums text-right font-semibold">{formatCurrency(it.subtotal)}</span>
              </div>
            ))}
            {(pr.items || []).length === 0 && (
              <div data-testid="pr-detail-items-empty" className="px-3 py-4 text-center text-[12px] text-[#9A9BA3]">Belum ada item pada PR ini.</div>
            )}
          </div>

          {nonCatalog && (
            <div className="flex items-center gap-2 text-[11.5px] text-[#8C4A00] bg-[#FFF8EE] border border-[#FFE2B8] rounded-md px-3 py-2">
              <AlertTriangle size={14} /> Ada item non-katalog (dari Pesanan Khusus) — tidak bisa dikonversi otomatis ke PO. Buat produk dulu atau proses manual.
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap justify-end gap-2 pt-1">
            {pr.status === "draft" && (
              <button data-testid="pr-action-submit" className="btn-primary" disabled={busy} onClick={() => act("/submit")}><Send size={14} /> Ajukan</button>
            )}
            {pr.status === "pending_approval" && canApprove && (
              <>
                <button data-testid="pr-action-reject" className="btn-danger" disabled={busy} onClick={() => { setRejectReason(""); setErr(""); setShowReject(true); }}><XCircle size={14} /> Tolak</button>
                <button data-testid="pr-action-approve" className="btn-primary" disabled={busy} onClick={() => act("/approve")}><CheckCircle2 size={14} /> Setujui</button>
              </>
            )}
            {pr.status === "approved" && (
              <button data-testid="pr-action-convert" className="btn-primary" disabled={busy || nonCatalog} onClick={() => setShowConvert(true)}><ShoppingCart size={14} /> Konversi ke PO</button>
            )}
            {["draft", "pending_approval", "approved"].includes(pr.status) && (
              <button data-testid="pr-action-cancel" className="btn-secondary" disabled={busy} onClick={() => act("/cancel")}><Ban size={14} /> Batalkan</button>
            )}
          </div>
        </div>
      </section>

      {/* FASE E — routing & realisasi per baris (beli ke supplier / proses via makloon) */}
      {["approved", "converted"].includes(pr.status) && (
        <PrSourcingPanel pr={pr} suppliers={suppliers} warehouses={warehouses}
          onChanged={onChanged} reload={reload} />
      )}

      {/* Convert modal */}
      {showConvert && (
        <div className="modal-overlay" data-testid="pr-convert-modal">
          <div className="modal-card small">
            <p className="modal-title">Konversi {pr.number} → Pesanan Pembelian</p>
            <p className="modal-subtitle">Pilih supplier & gudang untuk membuat PO.</p>
            {err && <div className="notice-bar danger"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}
            <div className="grid gap-3 mt-2">
              <div className="grid gap-1.5">
                <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Supplier *</label>
                <KNSelect
                  data-testid="pr-convert-supplier"
                  className="form-input"
                  value={convSupplier}
                  onValueChange={setConvSupplier}
                  placeholder="— Pilih supplier —"
                  options={suppliers.map((s) => ({ value: s.id, label: s.name }))}
                />
              </div>
              <div className="grid gap-1.5">
                <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Gudang</label>
                <KNSelect
                  data-testid="pr-convert-warehouse"
                  className="form-input"
                  value={convWarehouse}
                  onValueChange={setConvWarehouse}
                  placeholder="— Pilih gudang —"
                  options={warehouses.map((w) => ({ value: w.id, label: w.name }))}
                />
              </div>
              <div className="grid gap-1.5">
                <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Estimasi Tanggal Terima</label>
                <input type="date" className="form-input" value={convDate} onChange={(e) => setConvDate(e.target.value)} />
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowConvert(false)}>Batal</button>
              <button data-testid="pr-convert-confirm" className="btn-primary" onClick={doConvert} disabled={busy}>{busy ? "Memproses…" : "Buat PO"}</button>
            </div>
          </div>
        </div>
      )}

      {/* H3 — Reject modal (alasan wajib, bukan hardcode) */}
      {showReject && (
        <div className="modal-overlay" data-testid="pr-reject-modal">
          <div className="modal-card small">
            <p className="modal-title">Tolak {pr.number}</p>
            <p className="modal-subtitle">Berikan alasan penolakan (akan tersimpan di riwayat & audit).</p>
            {err && <div className="notice-bar danger"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}
            <div className="grid gap-1.5 mt-2">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Alasan Penolakan *</label>
              <textarea data-testid="pr-reject-reason" className="form-input" rows="3"
                value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Mis. nilai di atas anggaran, supplier belum disetujui, dsb." />
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowReject(false)}>Batal</button>
              <button data-testid="pr-reject-confirm" className="btn-danger" onClick={doReject} disabled={busy || !rejectReason.trim()}>{busy ? "Memproses…" : "Tolak PR"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}