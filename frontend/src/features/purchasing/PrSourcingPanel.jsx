/**
 * PrSourcingPanel (FASE E) — Routing & REALISASI Purchase Requisition per BARIS.
 *
 * Satu PR sering campur: sebagian barang dibeli jadi (`purchase`), sebagian diproses
 * lewat mitra (`makloon`). Panel ini menampilkan progres realisasi per baris dan
 * menyediakan dua aksi: **Realisasi ke PO** (boleh sebagian baris) dan
 * **Buat Order Makloon** (1 klik → Wizard Makloon ter-prefill dari Resep Proses).
 */
import { useCallback, useEffect, useState } from "react";
import { Boxes, RefreshCw, ShoppingCart, TriangleAlert } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { formatQty } from "../../utils/formatters";
import MakloonWizard from "./makloon/MakloonWizard";
import {
  FULFILLMENT_META, makloonPrefill, prSourcing, realizePo, REALIZATION_META,
} from "./supplier-items/supplierItemsApi";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { GroupEntityNotice, isGroupEntityPartner, supplierOptionLabel }
  from "../../components/GroupEntityBadge";

export default function PrSourcingPanel({ pr, suppliers, warehouses, onChanged, reload }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState([]);            // line_no baris purchase terpilih
  const [showPo, setShowPo] = useState(false);
  const [supplierId, setSupplierId] = useState(pr.preferred_supplier_id || "");
  const [warehouseId, setWarehouseId] = useState(pr.warehouse_id || "");
  const [expDate, setExpDate] = useState("");
  const [wizard, setWizard] = useState(null);         // { lineNo, prefill }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await prSourcing(pr.id);
      setData(res);
      setErr("");
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal memuat status realisasi PR.");
    } finally { setLoading(false); }
  }, [pr.id]);

  useEffect(() => { load(); }, [load]);

  const lines = data?.lines || [];
  // FASE E-7 (E7.2) — pemasok terpilih pada modal realisasi (lencana + tombol mati).
  const selectedSupplier = (suppliers || []).find((s) => s.id === supplierId) || null;
  const supplierIsGroupEntity = isGroupEntityPartner(selectedSupplier);
  const summary = data?.summary || {};
  const openPurchase = lines.filter((l) => l.fulfillment_mode === "purchase" && l.remaining_qty > 0);
  const canAct = pr.status === "approved" || pr.status === "converted";

  function toggle(lineNo) {
    setPicked((prev) => (prev.includes(lineNo) ? prev.filter((n) => n !== lineNo) : [...prev, lineNo]));
  }

  async function doRealizePo() {
    if (!supplierId) { setErr("Pilih supplier."); return; }
    setBusy(true); setErr("");
    try {
      const res = await realizePo(pr.id, {
        supplier_id: supplierId, warehouse_id: warehouseId,
        line_nos: picked, expected_delivery_date: expDate,
      });
      onChanged?.(`Direalisasikan ke ${res.po.po_number}.`);
      setShowPo(false); setPicked([]);
      await load();
      reload?.(pr.id);
    } catch (e) {
      setErr(e.response?.data?.detail || "Realisasi ke PO gagal.");
    } finally { setBusy(false); }
  }

  async function openWizard(lineNo) {
    setBusy(true); setErr("");
    try {
      const pre = await makloonPrefill(pr.id, lineNo);
      if (!pre.ready) { setErr(pre.reason || "Prefill makloon belum tersedia."); return; }
      setWizard({ lineNo, prefill: pre });
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal menyiapkan Wizard Makloon.");
    } finally { setBusy(false); }
  }

  return (
    <section className="section-card" data-testid="pr-sourcing-panel">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <h3 className="text-[13px] font-bold">Pemenuhan & Realisasi</h3>
          <span data-testid="pr-realization-status"
            className={`status-pill ${(REALIZATION_META[summary.realization_status] || {}).cls || "pill-muted"}`}>
            {(REALIZATION_META[summary.realization_status] || {}).label || "—"}
          </span>
        </div>
        <button data-testid="pr-sourcing-refresh" className="btn-secondary btn-xs" onClick={load}>
          <RefreshCw size={12} /> Muat ulang
        </button>
      </div>

      <div className="section-body grid gap-3">
        {err && (
          <div className="notice-bar danger" data-testid="pr-sourcing-error">
            <span>{err}</span><button onClick={() => setErr("")}>×</button>
          </div>
        )}

        {loading && (
          <p data-testid="pr-sourcing-loading" className="text-[12px] text-[#9A9BA3]">Memuat status realisasi…</p>
        )}

        {!loading && (
          <>
            <div className="grid gap-2 sm:grid-cols-4">
              {[
                ["Baris Terealisasi", `${summary.realized_lines ?? 0}/${summary.total_lines ?? 0}`, "pr-kpi-lines"],
                ["Qty Terealisasi", `${formatQty(summary.realized_qty || 0)} / ${formatQty(summary.total_qty || 0)}`, "pr-kpi-qty"],
                ["Baris Beli", summary.purchase_lines ?? 0, "pr-kpi-purchase"],
                ["Baris Makloon", summary.makloon_lines ?? 0, "pr-kpi-makloon"],
              ].map(([label, value, tid]) => (
                <div key={tid} className="metric-tile">
                  <span className="text-[10px] uppercase text-[#6B6B73]">{label}</span>
                  <b data-testid={tid} className="tabular-nums">{value}</b>
                </div>
              ))}
            </div>

            <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
              <div className="grid grid-cols-[36px_1.4fr_110px_100px_100px_1fr_150px] gap-x-3 bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
                <span></span><span>Barang</span><span>Pemenuhan</span>
                <span className="text-right">Diminta</span><span className="text-right">Sisa</span>
                <span>Jejak Realisasi</span><span className="text-right">Aksi</span>
              </div>
              {lines.map((l) => (
                <div key={l.line_no} data-testid={`pr-source-line-${l.line_no}`}
                  className="grid grid-cols-[36px_1.4fr_110px_100px_100px_1fr_150px] gap-x-3 items-center px-3 py-2 border-t border-[#F4F5F7]">
                  <span>
                    {l.fulfillment_mode === "purchase" && l.remaining_qty > 0 && canAct && (
                      <input type="checkbox" data-testid={`pr-source-pick-${l.line_no}`}
                        checked={picked.includes(l.line_no)} onChange={() => toggle(l.line_no)} />
                    )}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{l.product_name || "—"}</p>
                    <p className="text-[10px] text-[#9A9BA3]">#{l.line_no} · {l.sku || "non-katalog"} · {l.unit}</p>
                  </div>
                  <span>
                    <span data-testid={`pr-source-mode-${l.line_no}`}
                      className={`status-pill ${(FULFILLMENT_META[l.fulfillment_mode] || {}).cls || "pill-muted"}`}>
                      {(FULFILLMENT_META[l.fulfillment_mode] || {}).label || l.fulfillment_mode}
                    </span>
                  </span>
                  <span className="text-[12px] tabular-nums text-right">{formatQty(l.quantity)}</span>
                  <span data-testid={`pr-source-remaining-${l.line_no}`}
                    className={`text-[12px] tabular-nums text-right font-semibold ${l.remaining_qty > 0 ? "text-[#8C4A00]" : "text-[#1B7F4B]"}`}>
                    {formatQty(l.remaining_qty)}
                  </span>
                  <div className="min-w-0">
                    {(l.realizations || []).length === 0 ? (
                      <span className="text-[10.5px] text-[#9A9BA3]">Belum ada</span>
                    ) : (l.realizations || []).map((r, i) => (
                      <p key={i} data-testid={`pr-source-ref-${l.line_no}-${i}`}
                        className="text-[10.5px] text-[#0058CC] font-semibold truncate">
                        {r.ref_number} <span className="text-[#9A9BA3] font-normal">
                          ({r.type === "purchase_order" ? "PO" : "Makloon"} · {formatQty(r.qty)})
                        </span>
                      </p>
                    ))}
                  </div>
                  <div className="flex justify-end">
                    {canAct && l.remaining_qty > 0 && l.fulfillment_mode === "makloon" && (
                      <button data-testid={`pr-source-makloon-${l.line_no}`} className="btn-secondary btn-xs"
                        disabled={busy} onClick={() => openWizard(l.line_no)}>
                        <Boxes size={12} /> Buat Order Makloon
                      </button>
                    )}
                    {l.remaining_qty <= 0 && (
                      <span className="status-pill pill-success">Selesai</span>
                    )}
                  </div>
                </div>
              ))}
              {lines.length === 0 && (
                <div data-testid="pr-source-empty" className="px-3 py-5 text-center text-[12px] text-[#9A9BA3]">
                  Belum ada baris pada PR ini.
                </div>
              )}
            </div>

            {!canAct && (
              <div className="flex items-center gap-2 text-[11.5px] text-[#8C4A00] bg-[#FFF8EE] border border-[#FFE2B8] rounded-md px-3 py-2">
                <TriangleAlert size={14} /> PR harus berstatus <b>disetujui</b> sebelum bisa direalisasikan.
              </div>
            )}

            {canAct && openPurchase.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[11.5px] text-[#6B6B73]">
                  {picked.length > 0
                    ? `${picked.length} baris dipilih untuk dijadikan PO.`
                    : `Tidak ada baris dipilih — semua ${openPurchase.length} baris beli yang terbuka akan masuk 1 PO.`}
                </span>
                <button data-testid="pr-realize-po-open" className="btn-primary"
                  onClick={() => { setErr(""); setShowPo(true); }}>
                  <ShoppingCart size={14} /> Realisasi ke PO
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Modal realisasi ke PO */}
      {showPo && (
        <div className="modal-overlay" data-testid="pr-realize-po-modal" {...overlayDismiss(() => setShowPo(false))}>
          <div className="modal-card small" onClick={(e) => e.stopPropagation()}>
            <p className="modal-title">Realisasi {pr.number} → Pesanan Pembelian</p>
            <p className="modal-subtitle">
              Harga diambil otomatis dari <b>kontrak pembelian</b> bila ada, lalu estimasi PR,
              barang supplier, price-list, terakhir master produk.
            </p>
            {err && <div className="notice-bar danger"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}
            <div className="grid gap-3 mt-2">
              <div className="grid gap-1.5">
                <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Supplier *</label>
                <KNSelect data-testid="pr-realize-supplier" className="form-input" value={supplierId}
                  onValueChange={setSupplierId} placeholder="— Pilih supplier —"
                  options={suppliers.map((s) => ({ value: s.id, label: supplierOptionLabel(s) }))} />
                {/* FASE E-7 (E7.2) — pintu inilah yang sebelumnya BOCOR: realisasi PR
                    membuat PO biasa ke badan usaha grup (bukti: KSC/PO-00013). */}
                {isGroupEntityPartner(selectedSupplier) && (
                  <GroupEntityNotice partner={selectedSupplier} docLabel="PO hasil realisasi PR" />
                )}
              </div>
              <div className="grid gap-1.5">
                <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Gudang</label>
                <KNSelect data-testid="pr-realize-warehouse" className="form-input" value={warehouseId}
                  onValueChange={setWarehouseId} placeholder="— Pilih gudang —"
                  options={warehouses.map((w) => ({ value: w.id, label: w.name }))} />
              </div>
              <div className="grid gap-1.5">
                <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Estimasi Tanggal Terima</label>
                <input type="date" className="form-input" value={expDate}
                  onChange={(e) => setExpDate(e.target.value)} />
              </div>
              <p className="text-[11px] text-[#6B6B73]">
                Baris yang akan diproses:{" "}
                <b data-testid="pr-realize-lines">
                  {picked.length > 0 ? picked.map((n) => `#${n}`).join(", ")
                    : openPurchase.map((l) => `#${l.line_no}`).join(", ")}
                </b>
              </p>
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowPo(false)}>Batal</button>
              <button data-testid="pr-realize-confirm" className="btn-primary" onClick={doRealizePo}
                disabled={busy || supplierIsGroupEntity}
                title={supplierIsGroupEntity
                  ? `${selectedSupplier?.name} adalah badan usaha di dalam grup — pakai menu Antar Entitas`
                  : ""}>
                {supplierIsGroupEntity ? "Pakai menu Antar Entitas"
                  : busy ? "Memproses…" : "Buat PO"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Wizard Makloon ter-prefill dari baris PR */}
      {wizard && (
        <MakloonWizard
          selectedEntity={pr.entity_id}
          prefill={wizard.prefill}
          prContext={{ pr_id: pr.id, pr_number: pr.number, line_no: wizard.lineNo }}
          onClose={() => setWizard(null)}
          onSaved={(order) => {
            setWizard(null);
            onChanged?.(`Order Makloon ${order?.mko_number || ""} dibuat dari ${pr.number}.`);
            load();
            reload?.(pr.id);
          }}
          onError={setErr}
        />
      )}
    </section>
  );
}
