import { FileText, CheckCircle, XCircle, AlertCircle, Receipt, Ban, FileEdit } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import { getStatusBadge } from "./poUtils";
import POTimeline from "./POTimeline";
import POVersionHistory from "./POVersionHistory";
import PODeviationBanner from "./PODeviationBanner";
import ProcessTimeline from "../../documents/ProcessTimeline";
import DocRefsPanel from "../../documents/trace/DocRefsPanel";
import DocumentActionsBar from "../../documents/DocumentActionsBar";
import RelatedDocsPanel from "../../documents/RelatedDocsPanel";
import QtyDual from "../../../components/QtyDual";      // FASE U — dua satuan

/**
 * PODetailPanel — panel kanan detail PO (progress terima, status penagihan, retur).
 *
 * P0-B (SSOT AP): PO BUKAN lagi jalur hutang/pembayaran. Hutang & pembayaran
 * supplier dikelola SATU PINTU di menu "Tagihan Supplier" (Vendor Bill). Panel
 * ini hanya menampilkan STATUS PENAGIHAN informasional + ajakan buat Vendor Bill.
 *
 * Props: po, currentUser, onClose, onApprove, onCancel, onCloseShort, onAmend
 */
export default function PODetailPanel({ po, currentUser, onClose, onApprove, onCancel, onCloseShort, onAmend, onOpenDocument }) {
  if (!po) {
    return (
      <div className="section-card flex items-center justify-center min-h-[200px] border-dashed">
        <div className="text-center p-6">
          <FileText size={28} className="mx-auto mb-2 text-gray-300" />
          <p className="text-[12px] text-[#6B6B73]">Pilih PO untuk lihat detail</p>
        </div>
      </div>
    );
  }

  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const goodsReceived = ["receiving", "partial", "completed", "closed_short"].includes(po.status);
  const amendable = ["waiting_approval", "pending", "receiving", "partial"].includes(po.status);
  const version = Number(po.version || 1);

  // Ringkasan penagihan (di-maintain Vendor Bill via sync_po_billing).
  const grand = Number(po.grand_total ?? po.total_amount ?? 0);
  const billed = Number(po.billed_total ?? 0);
  const unbilled = Number(po.unbilled_total ?? Math.max(grand - billed, 0));
  const billCount = Number(po.bill_count ?? 0);
  const billState = billed <= 0.01 ? { label: "Belum Ditagih", cls: "bg-red-50 text-red-600 border border-red-200" }
    : unbilled <= 0.01 ? { label: "Tertagih Penuh", cls: "bg-green-50 text-green-700 border border-green-200" }
    : { label: "Tertagih Sebagian", cls: "bg-amber-50 text-amber-700 border border-amber-200" };

  return (
    <div className="section-card self-start" data-testid="po-detail-panel">
      <div className="section-head">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase text-[#0058CC]">{po.po_number}</p>
          <div className="mt-0.5 flex items-center gap-1">
            {getStatusBadge(po.status)}
            {version > 1 && (
              <span data-testid="po-version-badge" className="rounded bg-[#F3E8FF] px-1.5 py-0.5 text-[10px] font-semibold text-[#6B219A]">v{version}</span>
            )}
            {goodsReceived && (
              <span data-testid="po-billing-badge" className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${billState.cls}`}>{billState.label}</span>
            )}
          </div>
        </div>
        <button className="icon-button" onClick={onClose}><XCircle size={14} /></button>
      </div>

      <div className="section-body space-y-3">
        <DocumentActionsBar docType="purchase_order" sourceId={po.id} entityId={po.entity_id}
          number={po.po_number} label="Pesanan Pembelian" esignable currentUser={currentUser}
          className="rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] px-2.5 py-2" />
        {/* Dokumen penerimaan gudang (gap docs) — muncul setelah barang mulai diterima */}
        {goodsReceived && (
          <RelatedDocsPanel
            title="Dokumen Penerimaan Gudang"
            docs={[
              { docType: "goods_receipt", label: "Bukti Terima Barang (GRN)" },
              { docType: "put_away", label: "Daftar Put-Away" },
            ]}
            sourceId={po.id}
            entityId={po.entity_id}
            number={po.po_number}
            currentUser={currentUser}
          />
        )}
        {/* Supplier + Gudang */}
        <div className="grid grid-cols-2 gap-2 text-[11.5px]">
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2">
            <p className="text-[10px] text-[#6B6B73] uppercase font-semibold mb-0.5">Supplier</p>
            <p className="font-semibold">{po.supplier_name}</p>
            <p className="text-[10.5px] text-[#6B6B73]">{po.supplier_contact}</p>
          </div>
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2">
            <p className="text-[10px] text-[#6B6B73] uppercase font-semibold mb-0.5">Gudang</p>
            <p className="font-semibold">{po.warehouse_name}</p>
            <p className="text-[10.5px] text-[#6B6B73]">{po.warehouse_city}</p>
          </div>
        </div>

        {/* Items with receive progress */}
        <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
          <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            Items & Progress Terima ({po.items?.length || 0})
          </div>
          {po.items?.map((item, i) => {
            const ordered = Number(item.quantity || 0);
            const rcv = Number(item.received_qty || 0);
            const pct = ordered > 0 ? Math.min(100, Math.round((rcv / ordered) * 100)) : 0;
            const done = pct >= 100;
            return (
              <div key={i} data-testid={`po-item-${i}`} className="px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0 text-[11px]">
                <div className="flex justify-between items-center">
                  <p className="font-semibold truncate">{item.sku}</p>
                  <p className="font-bold tabular-nums">{formatCurrency(item.line_total ?? item.subtotal ?? ordered * (item.price || 0))}</p>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <div className="flex-1 h-1.5 rounded-full bg-[#EFF0F2] overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: done ? "#16A34A" : "#0058CC" }} />
                  </div>
                  <span className="text-[10px] tabular-nums text-[#6B6B73] whitespace-nowrap">{rcv}/{ordered} {item.unit}</span>
                </div>
                {/* FASE U — DUA SATUAN: rencana roll (diketik) vs roll yang BENAR-BENAR
                    diterima (turunan dari roll yang lahir). Dokumen lama tampil "—". */}
                <div className="mt-1 flex items-center justify-between gap-2 text-[10.5px]">
                  <span className="text-[#6B6B73]">Rencana <QtyDual rolls={item.qty_rolls} measure={item.quantity} unit={item.unit} factor={item.unit_factor} factorTo={item.unit_factor_to} compact testId={`po-item-${i}-plan-dual`} /></span>
                  <span className="text-[#6B6B73]">Diterima <QtyDual rolls={item.received_rolls} measure={item.received_qty} unit={item.unit} compact testId={`po-item-${i}-recv-dual`} /></span>
                </div>
                {/* FASE F-2 — jejak asal harga (kontrak / harga terakhir / manual) */}
                {(item.price_source || item.contract_number || item.supplier_sku) && (() => {
                  const SRC = {
                    contract: { label: "Kontrak", cls: "bg-[#E6F6EC] text-[#1B7F4B]" },
                    manual_override: { label: "Override", cls: "bg-[#FDF3E7] text-[#B26B00]" },
                    manual: { label: "Manual", cls: "bg-[#EFF0F2] text-[#6B6B73]" },
                    supplier_item: { label: "Harga Terakhir", cls: "bg-[#EAF2FF] text-[#0058CC]" },
                    price_list: { label: "Daftar Harga", cls: "bg-[#EAF2FF] text-[#0058CC]" },
                    pr_estimate: { label: "Estimasi PR", cls: "bg-[#EAF2FF] text-[#0058CC]" },
                    product_master: { label: "Master", cls: "bg-[#EFF0F2] text-[#6B6B73]" },
                  };
                  const s = SRC[item.price_source] || { label: item.price_source || "—", cls: "bg-[#EFF0F2] text-[#6B6B73]" };
                  const explain = Array.isArray(item.sourcing_explain) ? item.sourcing_explain.join("\n") : "";
                  return (
                    <div data-testid={`po-item-source-${i}`} className="mt-1 flex items-center gap-1.5 flex-wrap text-[10px] text-[#8E8E93]" title={explain}>
                      <span className="text-[9px] mr-0.5">Harga @ {formatCurrency(item.price || 0)} —</span>
                      <span className={`text-[9px] font-bold rounded px-1 py-0.5 ${s.cls}`}>{s.label}</span>
                      {item.contract_number && <span className="font-mono text-[9px] text-[#1B7F4B]">{item.contract_number}</span>}
                      {item.supplier_sku && <span className="font-mono text-[9px] text-[#9A9BA3]">SKU {item.supplier_sku}</span>}
                      {explain && <span className="text-[9px] text-[#B9AFC9] cursor-help">· jejak ↗</span>}
                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>

        {/* P0-1 — Rincian harga: diskon + DPP + PPN Masukan (PO ber-breakdown) */}
        {po.net_subtotal != null && (
          <div data-testid="po-pricing-breakdown" className="rounded-md border border-[#EFF0F2] overflow-hidden text-[11.5px]">
            <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">Rincian Harga & Pajak</div>
            <div className="p-2.5 space-y-1">
              <Row label="Subtotal" value={formatCurrency(po.total_amount)} />
              {Number(po.discount_total) > 0 && <Row label="Diskon" value={`- ${formatCurrency(po.discount_total)}`} tone="text-amber-700" />}
              <Row label="DPP" value={formatCurrency(po.dpp)} />
              <Row label={`PPN Masukan${Number(po.ppn_rate) > 0 ? ` (${po.ppn_rate}%)` : ""}`}
                value={Number(po.ppn_amount) > 0 ? formatCurrency(po.ppn_amount) : "—"} />
              <div className="flex justify-between border-t border-[#EFF0F2] pt-1 mt-1">
                <span className="font-bold">Grand Total</span>
                <span data-testid="po-grand-total" className="font-bold tabular-nums text-[#007AFF]">{formatCurrency(po.grand_total)}</span>
              </div>
            </div>
          </div>
        )}

        {/* Status Penagihan — SSOT hutang ada di Vendor Bill (Tagihan Supplier) */}
        {goodsReceived && (
          <div data-testid="po-billing-summary" className="rounded-md border border-[#EFF0F2] overflow-hidden text-[11.5px]">
            <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              Status Penagihan (Vendor Bill)
            </div>
            <div className="p-2.5 space-y-1">
              <Row label="Nilai PO (Grand Total)" value={formatCurrency(grand)} />
              <Row label={`Sudah Ditagih${billCount > 0 ? ` (${billCount} bill)` : ""}`} value={formatCurrency(billed)} tone="text-green-700" />
              <div className="flex justify-between border-t border-[#EFF0F2] pt-1 mt-1">
                <span className="font-bold">Belum Ditagih</span>
                <span data-testid="po-unbilled" className="font-bold tabular-nums text-amber-700">{formatCurrency(unbilled)}</span>
              </div>
              <div className="flex items-start gap-1.5 mt-1.5 rounded-md border border-[#D6E4FF] bg-[#F5F9FF] px-2 py-1.5 text-[10.5px] text-[#0058CC]">
                <Receipt size={12} className="mt-0.5 shrink-0" />
                <span>Hutang & pembayaran supplier dikelola di menu <b>Tagihan Supplier</b> (Vendor Bill). Buat Vendor Bill dari menu tersebut untuk menagih & membayar PO ini.</span>
              </div>
            </div>
          </div>
        )}

        {/* Returns linked */}
        {po.returns?.length > 0 && (
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">Retur Beli</div>
            {po.returns.map((r) => (
              <div key={r.id} className="flex items-center justify-between px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0 text-[11px]">
                <div><p className="font-semibold">{r.number}</p><p className="text-[10px] text-[#6B6B73]">{r.debit_note_number || r.status}</p></div>
                <span className="font-bold tabular-nums text-amber-700">{formatCurrency(r.total_amount)}</span>
              </div>
            ))}
          </div>
        )}

        {po.status === "waiting_approval" && po.required_approval_role && (
          <div data-testid="po-approval-badge" className="flex items-center gap-2 rounded-md border border-[#FFE2B8] bg-[#FFF7EC] px-2.5 py-1.5 text-[11px] text-[#9A5B00]">
            <AlertCircle size={13} />
            <span>Butuh persetujuan peran <b className="uppercase">{po.required_approval_role}</b> sebelum tugas barang masuk dibuat.</span>
          </div>
        )}
        {po.price_deviation?.flagged && <PODeviationBanner deviation={po.price_deviation} />}
        {(po.budget_check?.warnings || []).length > 0 && (
          <div data-testid="po-budget-warning" className="rounded-md border border-[#F5D9A8] bg-[#FFFBF3] px-2.5 py-2 text-[11px] text-[#8A5A00]">
            <div className="flex items-center gap-1.5 font-bold mb-1">
              <AlertCircle size={13} /> Peringatan Anggaran (kontrol {String(po.budget_check?.mode || "warn").toUpperCase()})
            </div>
            <div className="space-y-0.5">
              {(po.budget_check.warnings || []).map((w, i) => (
                <p key={i} data-testid={`po-budget-warning-${i}`} className="text-[10.5px]">• {w}</p>
              ))}
            </div>
            {po.budget_key && (
              <p className="mt-1 text-[10.5px] text-[#9A7A3A]">
                Tag anggaran: {po.budget_dimension === "category" ? "kategori" : "akun"} <b>{po.budget_key}</b>
              </p>
            )}
          </div>
        )}
        {po.status === "closed_short" && (
          <div className="rounded-md border border-stone-200 bg-stone-50 px-2.5 py-1.5 text-[11px] text-stone-600">
            PO ditutup-kurang. Alasan: {po.close_reason || "—"}
          </div>
        )}

        {/* Riwayat / timeline approval PO */}
        <POTimeline po={po} />

        {/* EPIC6 — Document Hub: rantai PR→PO→GRN→Landed Cost→Vendor Bill + deep-link */}
        <ProcessTimeline docType="purchase_order" docId={po.id} onNavigate={onOpenDocument} />

        {/* FASE G-4 — Referensi Dokumen tersimpan (refs[] dua arah) + Jejak Dokumen */}
        <DocRefsPanel docType="purchase_order" docId={po.id} onOpenDocument={onOpenDocument} />

        {/* Phase 7.2 — Riwayat amandemen (snapshot + diff per versi) */}
        {po.amendments?.length > 0 && <POVersionHistory amendments={po.amendments} currentVersion={version} />}

        {/* Actions */}
        <div className="flex flex-col gap-1.5">
          {amendable && canManage && (
            <button data-testid="amend-po-button" onClick={() => onAmend?.(po)} className="secondary-button justify-center">
              <FileEdit size={13} /> Revisi / Amandemen PO
            </button>
          )}
          {po.status === "waiting_approval" && canManage && (
            <button data-testid="approve-po-button" onClick={() => onApprove(po.id)} className="primary-button justify-center">
              <CheckCircle size={13} /> Setujui PO
            </button>
          )}
          {["receiving", "partial", "pending"].includes(po.status) && canManage && (
            <button data-testid="close-po-button" onClick={() => onCloseShort(po.id)} className="secondary-button justify-center">
              <Ban size={13} /> Tutup PO (Kurang)
            </button>
          )}
          {po.status === "completed" && (
            <button data-testid="view-receiving-goods-doc"
              onClick={() => window.open(`/api/inbound/po/${po.id}/receiving-goods-document`, "_blank")}
              className="secondary-button justify-center">
              <FileText size={13} /> Dokumen Goods Receipt
            </button>
          )}
          {["waiting_approval", "pending"].includes(po.status) && canManage && (
            <button data-testid="cancel-po-button" onClick={() => onCancel(po.id)} className="danger-button justify-center">
              Batalkan PO
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, tone }) {
  return (
    <div className="flex justify-between">
      <span className="text-[#6B6B73]">{label}</span>
      <span className={`font-semibold tabular-nums ${tone || ""}`}>{value}</span>
    </div>
  );
}
