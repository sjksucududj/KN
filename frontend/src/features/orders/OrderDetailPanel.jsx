import { useEffect, useState } from "react";
import { XCircle, Clock3, Truck, CreditCard, PackageX, ShieldAlert, Send, FileText, AlertTriangle, PackageCheck } from "lucide-react";
import { can } from "../../config/roles";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { StatusPill } from "../../components/CoreWidgets";
import { StagePill, StageTimeline } from "../../components/SoStatusBadges";
import QtyDual from "../../components/QtyDual";      // FASE U — dua satuan
import axios, { API } from "../../services/apiClient";
import ProcessTimeline from "../documents/ProcessTimeline";
import DocumentActionsBar from "../documents/DocumentActionsBar";
import RelatedDocsPanel from "../documents/RelatedDocsPanel";
import DocRefsPanel from "../documents/trace/DocRefsPanel";
import SoPaymentPanel from "../finance/payments/SoPaymentPanel";
import SoApprovalsPanel from "./SoApprovalsPanel";
import OrderFulfillmentBadges from "./OrderFulfillmentBadges";
// FASE E-9 (E9.2 · US23/US24) — pita "diambil dari PT lain lewat KSC/IC-000xx".
import OrderIntercoSupplyPanel from "./OrderIntercoSupplyPanel";
import RestockPanel from "./RestockPanel";
// FASE G-1 — jejak koreksi dokumen (amandemen bernomor + nota kredit/debit).
import AmendmentTrailPanel from "../finance/amendments/AmendmentTrailPanel";
// F1b — arti `price_source` yang di-snapshot pada baris SO (dari resolver harga).
const PRICE_SOURCE_BADGE = {
  special_approval: { label: "Harga khusus", fg: "#6B219A", bg: "#F3E9FA" },
  customer: { label: "Harga pelanggan", fg: "#0058CC", bg: "#E7F0FF" },
  entity: { label: "Harga PT", fg: "#1B7F4B", bg: "#E6F6EC" },
  global: { label: "Harga umum", fg: "#6B6B73", bg: "#F5F5F7" },
};

export function OrderDetailPanel({
  order: sel,
  user,
  onRefresh,
  onApprove,
  onConfirm,
  onCancel,
  onPay,
  onGenerateDocument,
  onReleaseReservation,
  onSubmitForApproval,
  onMarkDelivered,
  onIssueTaxInvoice,
  onOpenDocument,
  onClose,
}) {
  const [shipments, setShipments] = useState([]);
  const [taxInvoices, setTaxInvoices] = useState([]);
  const [issuingTax, setIssuingTax] = useState(false);
  const FULFILL_STATUSES = ["partially_picked", "picked", "partially_shipped", "shipped", "done"];
  const TAX_ELIGIBLE = ["confirmed", "partially_picked", "picked", "partially_shipped", "shipped", "done"];
  const taxEligible = sel?.is_pkp !== false && Number(sel?.ppn_amount) > 0 && TAX_ELIGIBLE.includes(sel?.status);
  // FASE E-8 (E8.1/E8.2) — wewenang dibaca dari IZIN EFEKTIF yang dikirim server
  // (`can(perms, modul, aksi)`), bukan dari nama peran. Dulu satu bendera
  // `isApprover = admin|manager` mengunci DUA hal berbeda (setujui NILAI dan
  // konfirmasi rutin), sehingga peran Admin Sales lahir tanpa tombol Konfirmasi
  // walau server sudah mengizinkannya — dan tombol Faktur Pajak/uang masuk tetap
  // muncul untuk sales lalu ditolak 403 (pengguna menyalahkan dirinya sendiri).
  const perms = user?.permissions || {};
  const canApprove = can(perms, "order", "approve");     // NILAI/kredit → manajer
  const canConfirm = can(perms, "order", "confirm");     // rutin → + Admin Sales
  const canDeliver = can(perms, "order", "deliver");     // gudang & Admin Sales
  const canIssueTax = can(perms, "tax_invoice", "create");   // Finance
  // AUDIT SALES vs ADMIN SALES (2026-08-15) — `GET /shipments` menuntut `wms.view`,
  // izin yang SENGAJA dicabut dari sales di E8.3. Dulu panggilannya tetap jalan dan
  // 403-nya diserap `.catch` → seksi Surat Jalan berbunyi "Belum ada pengiriman
  // tercatat" padahal surat jalannya ADA. Kalimat salah lebih buruk daripada kalimat
  // "tidak boleh": sales menelepon gudang menanyakan barang yang sudah dikirim.
  // Sekarang: tidak dipanggil bila tak berhak, dan layarnya menunjuk ke tab
  // "Perjalanan Pesanan" (E8.14) yang memang dirancang untuk sales.
  const canSeeShipments = can(perms, "wms", "view");
  const canTakeMoney = can(perms, "ar_receipt", "create");   // Finance

  useEffect(() => {
    let active = true;
    if (sel?.id && FULFILL_STATUSES.includes(sel.status) && canSeeShipments) {
      axios.get(`${API}/shipments`, { params: { order_id: sel.id } })
        .then((r) => { if (active) setShipments(Array.isArray(r.data) ? r.data : []); })
        .catch(() => { if (active) setShipments([]); });
    } else {
      setShipments([]);
    }
    if (sel?.id && TAX_ELIGIBLE.includes(sel.status) && can(perms, "tax_invoice", "view")) {
      axios.get(`${API}/tax-invoices`, { params: { order_id: sel.id } })
        .then((r) => { if (active) setTaxInvoices(Array.isArray(r.data) ? r.data : []); })
        .catch(() => { if (active) setTaxInvoices([]); });
    } else {
      setTaxInvoices([]);
    }
    return () => { active = false; };
  }, [sel?.id, sel?.status]);

  const openSuratJalan = (shipmentId) => {
    window.open(`${API}/shipments/${shipmentId}/surat-jalan`, "_blank", "noopener,noreferrer");
  };
  const openFakturDocument = (fid) => {
    window.open(`${API}/tax-invoices/${fid}/document`, "_blank", "noopener,noreferrer");
  };
  const handleIssueTax = async () => {
    if (!onIssueTaxInvoice || issuingTax) return;
    setIssuingTax(true);
    try {
      await onIssueTaxInvoice(sel.id, { kode_transaksi: null });
      const r = await axios.get(`${API}/tax-invoices`, { params: { order_id: sel.id } });
      setTaxInvoices(Array.isArray(r.data) ? r.data : []);
    } finally {
      setIssuingTax(false);
    }
  };
  const ff = sel.fulfillment || {};
  return (
    <aside data-testid="order-detail-panel" className="section-card self-start">
      <div className="section-head">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#0058CC]">{sel.number}</p>
          <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
            <StagePill order={sel} testId="order-stage-pill" />
            <StatusPill status={sel.payment_status} />
            {sel.has_backorder && (
              <span data-testid="order-backorder-chip" className="rounded bg-[#FFF1EA] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[#B23B14]">
                Backorder
              </span>
            )}
            {sel.has_mixed_lot && (
              <span data-testid="order-mixedlot-chip" className="rounded bg-[#F3E9FA] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[#6B219A]">
                Mixed Lot
              </span>
            )}
          </div>
        </div>
        <button className="icon-button" onClick={onClose}>
          <XCircle size={14} />
        </button>
      </div>
      <div className="section-body space-y-3">
        <DocumentActionsBar docType="sales_order" sourceId={sel.id} entityId={sel.entity_id}
          number={sel.number} label="Pesanan Penjualan" esignable currentUser={user} onChanged={onRefresh}
          className="rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] px-2.5 py-2" />
        {/* Dokumen gudang & penagihan (gap docs) — muncul saat order sudah diproses */}
        {["confirmed", "partially_picked", "picked", "partially_shipped", "shipped", "done"].includes(sel.status) && (
          <RelatedDocsPanel
            title="Dokumen Gudang & Penagihan"
            docs={[
              { docType: "picking_list", label: "Surat Pengambilan Barang" },
              { docType: "packing_list", label: "Daftar Kemasan" },
              { docType: "delivery_note", label: "Surat Jalan Pengiriman" },
              { docType: "invoice", label: "Faktur Komersial" },
            ]}
            sourceId={sel.id}
            entityId={sel.entity_id}
            number={sel.number}
            currentUser={user}
            onChanged={onRefresh}
          />
        )}
        <div>
          <p data-testid="order-customer-detail" className="text-[12px] font-semibold">{sel.customer_name}</p>
          <p className="text-[11px] text-[#6B6B73]">{sel.customer_city || sel.shipping_city || "—"} · Sales: {sel.sales_name || "—"}</p>
          {sel.reservation_expires_at && (
            <p data-testid="order-expiry-detail" className="mt-0.5 flex items-center gap-1 text-[10.5px] text-[#7A2CA0]">
              <Clock3 size={11} /> {new Date(sel.reservation_expires_at).toLocaleString("id-ID")}
            </p>
          )}
        </div>

        {/* Sub-fase 1.6 — banner backorder (waiting_stock) */}
        {sel.has_backorder && (sel.backorders || []).length > 0 && (
          <div data-testid="order-backorder-panel" className="rounded-md border border-[#F5C9A6] bg-[#FFF7EF] p-2.5">
            <div className="flex items-center gap-1.5 mb-1.5">
              <AlertTriangle size={13} className="text-[#B23B14]" />
              <p className="text-[10px] font-bold uppercase tracking-wide text-[#8C4A00]">Menunggu Stok (Backorder)</p>
            </div>
            <p className="text-[10.5px] text-[#8C4A00] mb-2">
              Sebagian item menunggu barang masuk. Akan otomatis ter-reservasi saat barang diterima (Goods Receipt).
            </p>
            <div className="space-y-1">
              {(sel.backorders || []).filter((b) => Number(b.backorder_qty) > 0).map((b) => (
                <div
                  key={b.id || b.product_id}
                  data-testid={`order-backorder-line-${b.product_id}`}
                  className="flex items-center justify-between rounded bg-white/70 px-2 py-1 text-[10.5px]"
                >
                  <span className="font-semibold text-[#1C1C1E] truncate">{b.product_name || b.sku}</span>
                  <span className="tabular-nums text-[#B23B14] font-bold shrink-0">{formatQty(b.backorder_qty)} menunggu</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* FASE E-9 (E9.2 · US24) — kekurangan yang diurus lewat PEMBELIAN INTERNAL:
            sebutkan dari PT mana & lewat dokumen apa, supaya tidak ada yang menerbitkan
            permintaan beli kedua untuk barang yang sudah di jalan.
            Panel MENGAMBIL DATANYA SENDIRI: `interco_supply` hanya ada di respons
            DETAIL, sedangkan `sel` di sini berasal dari respons DAFTAR — lihat
            penjelasan lengkap di `OrderIntercoSupplyPanel.jsx`. */}
        <OrderIntercoSupplyPanel orderId={sel.id} fallback={sel.interco_supply} />

        <StageTimeline order={sel} />

        {/* PS-21 — pendingan + repeat/restock 1 klik (SO → PR + notifikasi MD) */}
        <RestockPanel order={sel} currentUser={user} onNavigate={onOpenDocument}
          onChanged={onRefresh} />

        {/* EPIC6 — Document Hub: rantai dokumen terkait + deep-link */}
        <ProcessTimeline docType="sales_order" docId={sel.id} onNavigate={onOpenDocument} />

        {/* FASE G-2 — Jadwal pembayaran (DP/cicilan/milestone) + antrean denda */}
        <SoPaymentPanel order={sel} currentUser={user} onChanged={onRefresh} />

        {/* FASE G-4 — Referensi Dokumen tersimpan (refs[] dua arah) + Jejak Dokumen */}
        <DocRefsPanel docType="sales_order" docId={sel.id} onOpenDocument={onOpenDocument} />

        <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
          <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">Items</div>
          {(sel.items || []).map((item, idx) => (
            <div
              data-testid={`order-item-${sel.id}-${item.id || item.product_id || idx}`}
              key={item.id || item.product_id || idx}
              className="px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0"
            >
              <p className="text-[10.5px] font-bold text-[#0058CC]">{item.sku}</p>
              <div className="flex justify-between">
                <p className="text-[11px]">{item.product_name}</p>
                <p className="text-[11px] font-semibold"><QtyDual rolls={item.qty_rolls} measure={item.quantity} unit={item.unit} factor={item.unit_factor} factorTo={item.unit_factor_to} testId={`order-item-qty-${item.product_id}`} /></p>
              </div>
              {Number(item.backorder_qty) > 0 && (
                <div data-testid={`order-item-backorder-${item.product_id}`} className="mt-0.5 flex gap-3 text-[10px] tabular-nums">
                  <span className="font-semibold text-[#126E2C]">Dipesan {formatQty(item.reserved_qty)}</span>
                  <span className="font-semibold text-[#B23B14]">Backorder {formatQty(item.backorder_qty)}</span>
                </div>
              )}
              <div className="flex justify-between text-[10.5px] text-[#6B6B73]">
                <span>
                  {formatCurrency(item.price)}/{item.unit}
                  {/* F1b — dari mana harga baris ini datang (snapshot saat SO dibuat). */}
                  {item.price_source && (
                    <span data-testid={`order-item-price-source-${item.product_id}`}
                      className="ml-1 rounded px-1 py-0.5 text-[9px] font-bold"
                      style={{ background: PRICE_SOURCE_BADGE[item.price_source]?.bg || "#F5F5F7",
                               color: PRICE_SOURCE_BADGE[item.price_source]?.fg || "#6B6B73" }}>
                      {PRICE_SOURCE_BADGE[item.price_source]?.label || item.price_source}
                    </span>
                  )}
                  {Number(item.discount_percent) > 0 && (
                    <span className="ml-1 text-[#FF9500] font-semibold">· disc {item.discount_percent}%</span>
                  )}
                </span>
                <span className="font-semibold text-[#3C3C43]">
                  {formatCurrency(item.line_total != null ? item.line_total : item.subtotal)}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Sub-fase 1.7 — Alokasi Stok (Lot & Gudang) + penjelasan (CLARITY) */}
        {(sel.allocations || []).length > 0 && (
          <div data-testid="order-allocation-panel" className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2] flex items-center justify-between gap-2">
              <span>Alokasi Stok (Lot & Gudang)</span>
              {sel.allocation_policy?.lot_selection && (
                <span className="text-[9px] font-semibold text-[#6B219A] normal-case lowercase">{sel.allocation_policy.lot_selection?.toUpperCase()} · {sel.allocation_policy.lot_mode}</span>
              )}
            </div>
            {(sel.allocations || []).map((a, idx) => (
              <div key={a.id || idx} data-testid={`order-alloc-${a.id || idx}`} className="px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold text-[#1C1C1E] truncate">{a.warehouse_name}{a.warehouse_city ? ` · ${a.warehouse_city}` : ""}</span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${a.lot_mode === "mixed" ? "bg-[#F3E9FA] text-[#6B219A]" : "bg-[#EAF6EC] text-[#126E2C]"}`}>
                      {a.lot_mode === "mixed" ? "Mixed Lot" : "Single Lot"}
                    </span>
                    <span className="text-[11px] font-semibold tabular-nums">{formatQty(a.quantity)}</span>
                  </div>
                </div>
                {(a.lots || []).length > 0 && (
                  <p className="text-[10px] text-[#6B6B73] mt-0.5">Lot: <span className="font-medium text-[#3C3C43]">{(a.lots || []).join(", ")}</span></p>
                )}
                {a.allocation_explanation && (
                  <p data-testid={`order-alloc-explain-${a.id || idx}`} className="text-[10px] text-[#8E8E93] mt-0.5 italic">{a.allocation_explanation}</p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Sub-fase 1.8 — Progres Pemenuhan + Pengiriman (Surat Jalan) */}
        {["partially_picked", "picked", "partially_shipped", "shipped", "done"].includes(sel.status) && (
          <div data-testid="order-fulfillment-panel" className="rounded-md border border-[#D9E8FF] bg-[#F5F9FF] p-2.5">
            <div className="flex items-center gap-1.5 mb-1.5">
              <PackageCheck size={13} className="text-[#0058CC]" />
              <p className="text-[10px] font-bold uppercase tracking-wide text-[#0058CC]">Pemenuhan & Pengiriman</p>
            </div>
            {ff.total_qty != null && (
              <div className="grid grid-cols-3 gap-2 mb-2 text-center">
                <div className="rounded bg-white/70 px-1.5 py-1">
                  <p className="text-[9px] uppercase text-[#8E8E93]">Total</p>
                  <p data-testid="ff-total" className="text-[12px] font-bold tabular-nums">{formatQty(ff.total_qty)}</p>
                </div>
                <div className="rounded bg-white/70 px-1.5 py-1">
                  <p className="text-[9px] uppercase text-[#8E8E93]">Dikirim</p>
                  <p data-testid="ff-shipped" className="text-[12px] font-bold tabular-nums text-[#0058CC]">{formatQty(ff.shipped_qty)}</p>
                </div>
                <div className="rounded bg-white/70 px-1.5 py-1">
                  <p className="text-[9px] uppercase text-[#8E8E93]">Sisa</p>
                  <p data-testid="ff-remaining" className="text-[12px] font-bold tabular-nums text-[#B23B14]">{formatQty(ff.remaining_qty)}</p>
                </div>
              </div>
            )}
            {shipments.length > 0 ? (
              <div className="space-y-1">
                {shipments.map((s) => (
                  <div key={s.id} data-testid={`shipment-row-${s.id}`}
                    className="flex items-center justify-between gap-2 rounded bg-white px-2 py-1.5 border border-[#E5EEFB]">
                    <div className="min-w-0">
                      <p className="text-[10.5px] font-bold text-[#0058CC]">
                        {s.shipment_no}
                        {s.is_partial && <span className="ml-1 rounded bg-[#FFF1EA] px-1 py-0.5 text-[8.5px] font-bold uppercase text-[#B23B14]">Parsial</span>}
                      </p>
                      <p className="text-[10px] text-[#6B6B73] truncate">{s.product_name} · {s.warehouse_name}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[11px] font-semibold tabular-nums">{formatQty(s.qty)} {s.unit}</span>
                      <button data-testid={`shipment-sj-btn-${s.id}`} className="icon-button" title="Cetak Surat Jalan" onClick={() => openSuratJalan(s.id)}>
                        <Truck size={13} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : canSeeShipments ? (
              <p className="text-[10.5px] text-[#6B6B73]">Belum ada pengiriman tercatat.</p>
            ) : (
              <p className="text-[10.5px] text-[#6B6B73]"
                 data-testid="order-shipments-no-access">
                Rincian surat jalan diurus gudang. Status pengirimannya bisa Anda lihat
                di tab <strong>Perjalanan Pesanan</strong>.
              </p>
            )}
          </div>
        )}

        {/* Ringkasan harga + pajak (Fase 1B) */}
        <div data-testid="order-pricing-breakdown" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5 space-y-1 text-[11.5px]">
          <p className="text-[10px] font-bold uppercase text-[#6B6B73] mb-1">Ringkasan Harga</p>
          <BreakRow label="Subtotal (bruto)" value={formatCurrency(sel.total_amount)} />
          {Number(sel.discount_total) > 0 && (
            <>
              <BreakRow label="Diskon" value={`− ${formatCurrency(sel.discount_total)}`} amber />
              <BreakRow label="Subtotal netto (DPP)" value={formatCurrency(sel.net_subtotal != null ? sel.net_subtotal : sel.total_amount)} />
            </>
          )}
          {Number(sel.ppn_amount) > 0 ? (
            <BreakRow label={`PPN ${sel.ppn_rate || 0}%`} value={formatCurrency(sel.ppn_amount)} />
          ) : (
            <BreakRow label="PPN" value={sel.is_pkp === false ? "Non-PKP (0)" : formatCurrency(0)} muted />
          )}
          {sel.needs_tax_invoice && (
            <div data-testid="order-needs-faktur-badge" className="mt-1 flex items-center gap-1 rounded bg-[#EFF4FF] px-2 py-1 text-[10px] font-semibold text-[#0058CC]">
              <FileText size={11} /> Pelanggan minta Faktur Pajak
            </div>
          )}
          <div className="flex items-center justify-between border-t border-[#E5E5EA] pt-1 mt-1">
            <span className="text-[10px] font-bold uppercase text-[#6B6B73]">Grand Total</span>
            <span data-testid="order-grand-total" className="text-[14px] font-bold text-[#007AFF]">
              {formatCurrency(sel.grand_total != null ? sel.grand_total : sel.total_amount)}
            </span>
          </div>
          {sel.payment_term_name && (
            <p className="text-[10.5px] text-[#6B6B73] pt-0.5">Termin: <span className="font-semibold text-[#3C3C43]">{sel.payment_term_name}</span></p>
          )}
        </div>

        {/* Faktur Pajak Jual (Sub-fase 1.9) — opsional, hanya entitas PKP + ber-PPN */}
        {taxEligible && (
          <div data-testid="order-tax-invoice-section" className="rounded-md border border-[#E5EEFB] bg-[#F5F9FF] p-2.5">
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-[10px] font-bold uppercase text-[#0058CC] flex items-center gap-1">
                <FileText size={12} /> Faktur Pajak
              </p>
              {taxInvoices.filter((f) => f.status !== "batal").length === 0 && canIssueTax && (
                <button
                  data-testid="issue-tax-invoice-btn"
                  disabled={issuingTax}
                  onClick={handleIssueTax}
                  className="rounded bg-[#0058CC] px-2 py-1 text-[10px] font-bold text-white disabled:opacity-50"
                >
                  {issuingTax ? "Menerbitkan…" : "Terbitkan Faktur Pajak"}
                </button>
              )}
            </div>
            {taxInvoices.length > 0 ? (
              <div className="space-y-1">
                {taxInvoices.map((f) => (
                  <div
                    key={f.id}
                    data-testid={`tax-invoice-row-${f.id}`}
                    className="flex items-center justify-between gap-2 rounded bg-white px-2 py-1.5 border border-[#E5EEFB]"
                  >
                    <div className="min-w-0">
                      <p className="text-[10.5px] font-bold text-[#0058CC]">
                        {f.number}
                        <span
                          className={`ml-1 rounded px-1 py-0.5 text-[8.5px] font-bold uppercase ${
                            f.status === "batal"
                              ? "bg-[#FDE2E2] text-[#9B1C1C]"
                              : f.status === "pengganti"
                              ? "bg-[#FFF3CD] text-[#8A6D00]"
                              : "bg-[#E5F6EC] text-[#1B7A43]"
                          }`}
                        >
                          {f.status}
                        </span>
                      </p>
                      <p className="text-[10px] text-[#6B6B73] truncate">
                        {f.nsfp ? `NSFP ${f.nsfp}` : "NSFP belum diisi"} · PPN {formatCurrency(f.ppn_amount)}
                      </p>
                    </div>
                    <button
                      data-testid={`tax-invoice-doc-btn-${f.id}`}
                      className="icon-button"
                      title="Cetak Faktur Pajak"
                      onClick={() => openFakturDocument(f.id)}
                    >
                      <FileText size={13} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[10.5px] text-[#6B6B73]">Belum ada Faktur Pajak. Bersifat opsional (pajak tidak wajib).</p>
            )}
          </div>
        )}

        {/* Badge kebutuhan approval (Fase 1B) */}
        {sel.approval_required && sel.required_approval_role && ["reserved", "waiting_approval"].includes(sel.status) && (
          <div data-testid="order-approval-badge" className="flex items-center gap-2 rounded-md border border-[#FFE2B8] bg-[#FFF7EC] px-2.5 py-1.5 text-[11px] text-[#9A5B00]">
            <ShieldAlert size={13} />
            <span>Butuh persetujuan peran <b className="uppercase">{sel.required_approval_role}</b> (Rp {formatQty(sel.approval_amount || sel.grand_total)})</span>
          </div>
        )}

        <OrderFulfillmentBadges order={sel} />

        {/* FASE G-1 — Koreksi & Amandemen: tidak ada perubahan angka secara diam-diam. */}
        <AmendmentTrailPanel order={sel} currentUser={user} onRefresh={onRefresh} />


        {/* F5 — Unified Approval (special price + over-credit + nilai) */}
        <SoApprovalsPanel order={sel} user={user} onRefresh={onRefresh} />

        <div className="flex flex-wrap gap-2">
          {sel.status === "reserved" && onSubmitForApproval && (
            <button data-testid={`submit-approval-button-${sel.id}`} className="primary-button" onClick={() => onSubmitForApproval(sel.id)}>
              <Send size={13} /> Ajukan untuk Persetujuan
            </button>
          )}
          {sel.status === "waiting_approval" && canApprove && (
            <button data-testid={`approve-order-button-${sel.id}`} className="primary-button" onClick={() => onApprove(sel.id)}>
              <FileText size={13} /> Setujui{sel.required_approval_role ? ` (${sel.required_approval_role})` : ""}
            </button>
          )}
          {sel.status === "approved" && canConfirm && (
            <button data-testid={`confirm-order-button-${sel.id}`} className="primary-button" onClick={() => onConfirm(sel.id)}>
              <FileText size={13} /> Confirm
            </button>
          )}
          {sel.status === "confirmed" && sel.payment_status !== "paid" && canTakeMoney && (
            <button data-testid={`simulate-payment-button-${sel.id}`} className="secondary-button" onClick={() => onPay(sel.id)}>
              <CreditCard size={13} /> Simulate Payment
            </button>
          )}
          {["reserved", "waiting_approval", "approved", "waiting_stock"].includes(sel.status) && (
            <button data-testid={`release-reservation-button-${sel.id}`} className="secondary-button" onClick={() => onReleaseReservation(sel.id)}>
              <PackageX size={13} /> Release Reservation
            </button>
          )}
          {sel.status === "shipped" && onMarkDelivered && canDeliver && (
            <button data-testid={`mark-delivered-button-${sel.id}`} className="primary-button" onClick={() => onMarkDelivered(sel.id)}>
              <PackageCheck size={13} /> Tandai Diterima (Selesai)
            </button>
          )}
          {!["done", "cancelled", "partially_shipped", "shipped"].includes(sel.status) && (
            <button data-testid={`cancel-order-button-${sel.id}`} className="secondary-button text-red-600" onClick={() => onCancel(sel.id)}>
              <XCircle size={13} /> Batal
            </button>
          )}
          {["confirmed", "partially_picked", "picked", "partially_shipped", "shipped", "done"].includes(sel.status) && (
            <>
              <button data-testid={`generate-invoice-button-${sel.id}`} className="secondary-button" onClick={() => onGenerateDocument("invoice", sel.id)}>
                <FileText size={13} /> Faktur (PPN)
              </button>
              <button data-testid={`generate-sj-button-${sel.id}`} className="secondary-button" onClick={() => onGenerateDocument("surat_jalan", sel.id)}>
                <Truck size={13} /> Surat Jalan
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}

function BreakRow({ label, value, amber = false, muted = false }) {
  return (
    <div className="flex items-center justify-between">
      <span className={muted ? "text-[#8E8E93]" : "text-[#6B6B73]"}>{label}</span>
      <span className={amber ? "font-semibold text-[#FF9500]" : muted ? "text-[#8E8E93]" : "font-semibold text-[#3C3C43]"}>{value}</span>
    </div>
  );
}
