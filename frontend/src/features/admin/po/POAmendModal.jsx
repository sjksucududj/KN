import { useMemo, useState } from "react";
import { XCircle, Plus, AlertTriangle, FileEdit, Trash2, Lock } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import KNSelect from "../../../components/KNSelect";
import { unitOptions } from "../../../utils/uom";                  // FASE U — satuan dari master
import useUomConversions from "../../../hooks/useUomConversions";  // FASE U — memuat katalog

/**
 * POAmendModal — Phase 7.2: form revisi / amandemen Purchase Order.
 *
 * Aturan owner (di-enforce backend, di-mirror di UI untuk UX):
 *  - 1.c: boleh ubah item/supplier/gudang/tanggal/catatan.
 *  - 2.a: SELALU re-approval dari awal (ditampilkan sebagai peringatan).
 *  - 3.b: saat partial receiving — qty tak boleh < diterima; item ber-penerimaan
 *         tak bisa dihapus; gudang tak bisa diganti bila sudah ada penerimaan.
 *  - 5.a: alasan WAJIB.
 *
 * Props: po, products, warehouses, suppliers, onSubmit(payload), onClose, submitting
 */
function unitOptionsFor(product, currentUnit) {
  // FASE U — satuan dari MASTER (`utils/uom.unitOptions` sudah menggabungkan master
  // satuan dengan satuan produk). `currentUnit` selalu ikut walau masternya kini
  // nonaktif: dropdown yang tidak memuat nilainya sendiri terlihat kosong dan
  // menggoda pengguna menyimpan ulang dengan satuan yang salah.
  const opts = unitOptions(product);
  if (currentUnit && !opts.some((o) => o.value === String(currentUnit).toLowerCase())) {
    opts.push({ value: currentUnit, label: currentUnit });
  }
  return opts;
}

export default function POAmendModal({
  po, products = [], warehouses = [], suppliers = [],
  onSubmit, onClose, submitting = false,
}) {
  const hasReceipt = (po.items || []).some((it) => Number(it.received_qty || 0) > 0);
  const activeSuppliers = suppliers.filter((s) => s.status !== "inactive");
  // FASE U — memuat katalog satuan supaya `unitOptionsFor` bisa menawarkan satuan
  // yang ditambah pemilik di master (mis. PANEL) saat baris PO diamandemen.
  useUomConversions();

  const [reason, setReason] = useState("");
  const [supplierId, setSupplierId] = useState(po.supplier_id || "");
  const [supplierName, setSupplierName] = useState(po.supplier_name || "");
  const [supplierContact, setSupplierContact] = useState(po.supplier_contact || "");
  const [warehouseId, setWarehouseId] = useState(po.warehouse_id || "");
  const [eta, setEta] = useState(po.expected_delivery_date || "");
  const [notes, setNotes] = useState(po.notes || "");
  const [orderDisc, setOrderDisc] = useState(Number(po.order_discount_percent || 0));
  const [taxMode, setTaxMode] = useState(po.tax_mode || "");
  const [items, setItems] = useState(() => (po.items || []).map((it) => ({
    product_id: it.product_id, sku: it.sku, product_name: it.product_name,
    quantity: Number(it.quantity || 0), unit: it.unit || "meter",
    price: Number(it.price || 0), discount_percent: Number(it.discount_percent || 0),
    received_qty: Number(it.received_qty || 0),
  })));
  const [newItem, setNewItem] = useState({ product_id: "", quantity: 0, unit: "meter", price: 0, discount_percent: 0 });
  const [localErr, setLocalErr] = useState("");

  const round2 = (n) => Math.round((Number(n) + Number.EPSILON) * 100) / 100;
  const clampPct = (v) => Math.min(Math.max(Number(v) || 0, 0), 100);

  const est = useMemo(() => {
    let gross = 0, disc = 0;
    for (const it of items) {
      const sub = round2((Number(it.price) || 0) * (Number(it.quantity) || 0));
      gross += sub; disc += round2(sub * clampPct(it.discount_percent) / 100);
    }
    const afterItem = round2(gross - disc);
    const oda = round2(afterItem * clampPct(orderDisc) / 100);
    return { gross: round2(gross), disc: round2(disc + oda), net: round2(afterItem - oda) };
  }, [items, orderDisc]); // eslint-disable-line

  function updateItem(idx, patch) {
    setItems((arr) => arr.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }
  function removeItem(idx) {
    const it = items[idx];
    if (Number(it.received_qty || 0) > 0) {
      setLocalErr(`Item ${it.sku} sudah diterima ${it.received_qty}, tidak bisa dihapus.`); return;
    }
    setItems((arr) => arr.filter((_, i) => i !== idx));
    setLocalErr("");
  }
  function addItem() {
    if (!newItem.product_id || Number(newItem.quantity) <= 0) { setLocalErr("Pilih produk & masukkan qty > 0."); return; }
    if (items.some((it) => it.product_id === newItem.product_id)) {
      setLocalErr("Produk sudah ada di daftar — ubah qty-nya langsung."); return;
    }
    const p = products.find((x) => x.id === newItem.product_id);
    setItems((arr) => [...arr, {
      product_id: newItem.product_id, sku: p?.sku || "", product_name: p?.name || "",
      quantity: Number(newItem.quantity), unit: newItem.unit || p?.base_unit || "meter",
      price: Number(newItem.price) > 0 ? Number(newItem.price) : Number(p?.price || 0),
      discount_percent: clampPct(newItem.discount_percent), received_qty: 0,
    }]);
    setNewItem({ product_id: "", quantity: 0, unit: "meter", price: 0, discount_percent: 0 });
    setLocalErr("");
  }

  function handleSupplierSelect(v) {
    if (v) {
      const s = suppliers.find((x) => x.id === v);
      setSupplierId(v); setSupplierName(s?.name || "");
      setSupplierContact(s ? [s.pic_name, s.phone].filter(Boolean).join(" · ") : supplierContact);
    } else { setSupplierId(""); }
  }
  function handleNewProductSelect(v) {
    const p = products.find((x) => x.id === v);
    setNewItem((cur) => ({ ...cur, product_id: v, unit: p?.base_unit || cur.unit || "meter", price: Number(p?.price || 0) }));
  }

  function validateAndSubmit() {
    if (!reason.trim()) { setLocalErr("Alasan amandemen wajib diisi."); return; }
    if (items.length === 0) { setLocalErr("PO harus punya minimal 1 item."); return; }
    for (const it of items) {
      if (Number(it.quantity) < Number(it.received_qty || 0) - 0.001) {
        setLocalErr(`Qty ${it.sku} (${it.quantity}) tak boleh < qty diterima (${it.received_qty}).`); return;
      }
      if (Number(it.quantity) <= 0) { setLocalErr(`Qty ${it.sku} harus > 0.`); return; }
    }
    setLocalErr("");
    onSubmit({
      reason: reason.trim(),
      items: items.map((it) => ({
        product_id: it.product_id, quantity: Number(it.quantity), unit: it.unit,
        price: Number(it.price), discount_percent: clampPct(it.discount_percent),
      })),
      supplier_id: supplierId || "",
      supplier_name: supplierId ? null : supplierName,
      supplier_contact: supplierContact,
      warehouse_id: warehouseId,
      expected_delivery_date: eta,
      notes,
      order_discount_percent: clampPct(orderDisc),
      tax_mode: taxMode,
    });
  }

  return (
    <div className="modal-overlay" data-testid="po-amend-modal"
      onClick={(e) => { if (e.target === e.currentTarget && !submitting) onClose?.(); }}>
      <div className="modal-card wide">
        <div className="flex items-start justify-between">
          <div>
            <p className="modal-title flex items-center gap-1.5"><FileEdit size={17} /> Revisi / Amandemen PO</p>
            <p className="modal-subtitle">{po.po_number} · versi aktif v{po.version || 1} → akan menjadi v{(Number(po.version || 1)) + 1}</p>
          </div>
          <button className="icon-button" data-testid="po-amend-close" onClick={onClose} disabled={submitting}><XCircle size={16} /></button>
        </div>

        {/* Peringatan re-approval (2.a) */}
        <div data-testid="po-amend-reapproval-warning" className="mt-3 flex items-start gap-2 rounded-md border border-[#FFE2B8] bg-[#FFF7EC] px-2.5 py-2 text-[11.5px] text-[#9A5B00]">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>Setiap revisi <b>mengulang persetujuan dari awal</b> berdasarkan nilai baru. Tugas barang masuk yang belum menerima barang akan dibuat ulang setelah disetujui.</span>
        </div>
        {hasReceipt && (
          <div data-testid="po-amend-receipt-note" className="mt-2 flex items-start gap-2 rounded-md border border-[#D6E4FF] bg-[#F5F9FF] px-2.5 py-2 text-[11.5px] text-[#0058CC]">
            <Lock size={13} className="mt-0.5 shrink-0" />
            <span>PO ini sudah ada penerimaan barang. Gudang terkunci, qty item tak boleh di bawah jumlah yang sudah diterima, dan item ber-penerimaan tidak dapat dihapus.</span>
          </div>
        )}

        {localErr && (
          <div data-testid="po-amend-error" className="mt-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-[11.5px] text-red-600">{localErr}</div>
        )}

        <div className="mt-3 space-y-3">
          {/* Alasan WAJIB */}
          <div>
            <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Alasan Amandemen <span className="req">*</span></label>
            <textarea data-testid="po-amend-reason" value={reason} rows="2"
              onChange={(e) => setReason(e.target.value)} className="field"
              placeholder="Mis. revisi qty/harga sesuai konfirmasi supplier" />
          </div>

          {/* Supplier + gudang + tanggal */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Supplier (Master)</label>
              <KNSelect data-testid="po-amend-supplier-select" value={supplierId || ""} onValueChange={handleSupplierSelect}
                className="field" placeholder="Pilih master / isi manual"
                options={[{ value: "", label: "— Isi manual / tanpa master —" },
                  ...activeSuppliers.map((s) => ({ value: s.id, label: `${s.code} · ${s.name}` }))]} />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Nama Supplier {!supplierId && <span className="req">*</span>}</label>
              <input data-testid="po-amend-supplier-name" type="text" value={supplierName} disabled={!!supplierId}
                onChange={(e) => setSupplierName(e.target.value)}
                className="field disabled:bg-gray-100 disabled:text-gray-500" placeholder="PT Supplier Textile" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Kontak Supplier</label>
              <input data-testid="po-amend-supplier-contact" type="text" value={supplierContact}
                onChange={(e) => setSupplierContact(e.target.value)} className="field" placeholder="081234567890" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Gudang {hasReceipt && <Lock size={10} className="inline -mt-0.5 text-[#6B6B73]" />}</label>
              <KNSelect data-testid="po-amend-warehouse-select" value={warehouseId} disabled={hasReceipt}
                onValueChange={(v) => setWarehouseId(v)} className="field" placeholder="Pilih Gudang"
                options={warehouses.map((wh) => ({ value: wh.id, label: `${wh.name} (${wh.code})` }))} />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Perkiraan Pengiriman</label>
              <input data-testid="po-amend-eta" type="date" value={eta || ""} onChange={(e) => setEta(e.target.value)} className="field" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Catatan</label>
              <input data-testid="po-amend-notes" type="text" value={notes || ""} onChange={(e) => setNotes(e.target.value)} className="field" placeholder="Catatan revisi…" />
            </div>
          </div>

          {/* Items editable */}
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1fr_84px_78px_96px_56px_64px_28px] px-2.5 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Produk</span><span>Qty</span><span>Unit</span><span>Harga</span><span>Disc%</span><span>Diterima</span><span></span>
            </div>
            {items.length === 0 ? (
              <div data-testid="po-amend-items-empty" className="px-2.5 py-4 text-center text-[11px] text-[#6B6B73]">Belum ada item. Tambahkan di bawah.</div>
            ) : items.map((it, i) => {
              const prod = products.find((p) => p.id === it.product_id);
              const locked = Number(it.received_qty || 0) > 0;
              return (
                <div key={it.product_id} data-testid={`po-amend-item-${i}`}
                  className="grid grid-cols-[1fr_84px_78px_96px_56px_64px_28px] items-center gap-1 px-2.5 py-1.5 border-b border-[#EFF0F2] last:border-0 text-[11.5px]">
                  <span className="truncate" title={`${it.sku} — ${it.product_name}`}>{it.sku}<span className="text-[#9A9BA3]"> · {it.product_name}</span></span>
                  <input data-testid={`po-amend-item-qty-${i}`} type="number" min={it.received_qty || 0} value={it.quantity}
                    onChange={(e) => updateItem(i, { quantity: parseFloat(e.target.value) || 0 })} className="field !py-1 !px-1.5 text-[11px]" />
                  <KNSelect data-testid={`po-amend-item-unit-${i}`} value={it.unit} onValueChange={(v) => updateItem(i, { unit: v })}
                    className="field !py-1 !px-1.5 text-[11px]" options={unitOptionsFor(prod, it.unit)} />
                  <input data-testid={`po-amend-item-price-${i}`} type="number" min="0" value={it.price}
                    onChange={(e) => updateItem(i, { price: parseFloat(e.target.value) || 0 })} className="field !py-1 !px-1.5 text-[11px]" />
                  <input data-testid={`po-amend-item-disc-${i}`} type="number" min="0" max="100" value={it.discount_percent}
                    onChange={(e) => updateItem(i, { discount_percent: parseFloat(e.target.value) || 0 })} className="field !py-1 !px-1.5 text-[11px]" />
                  <span className="tabular-nums text-[10.5px] text-[#6B6B73] text-center">{locked ? `${it.received_qty}` : "—"}</span>
                  <button data-testid={`po-amend-item-remove-${i}`} onClick={() => removeItem(i)} disabled={locked}
                    title={locked ? "Sudah diterima — tidak bisa dihapus" : "Hapus item"}
                    className={`justify-self-end ${locked ? "text-gray-300 cursor-not-allowed" : "text-red-400 hover:text-red-600"}`}>
                    {locked ? <Lock size={12} /> : <Trash2 size={12} />}
                  </button>
                </div>
              );
            })}
          </div>

          {/* Add item */}
          <div className="bg-[#FAFBFC] rounded-md border border-[#EFF0F2] p-2.5">
            <p className="text-[10.5px] font-bold uppercase text-[#6B6B73] mb-2">Tambah Item</p>
            <div className="grid grid-cols-[1fr_72px_70px_90px_52px_auto] gap-2">
              <KNSelect data-testid="po-amend-new-product" value={newItem.product_id} onValueChange={handleNewProductSelect}
                className="field" placeholder="Pilih Produk"
                options={[{ value: "", label: "Pilih Produk" }, ...products.map((p) => ({ value: p.id, label: `${p.sku} - ${p.name}` }))]} />
              <input data-testid="po-amend-new-qty" type="number" placeholder="Qty" value={newItem.quantity || ""}
                onChange={(e) => setNewItem({ ...newItem, quantity: parseFloat(e.target.value) || 0 })} className="field" />
              <KNSelect data-testid="po-amend-new-unit" value={newItem.unit} onValueChange={(v) => setNewItem({ ...newItem, unit: v })}
                className="field" options={unitOptionsFor(products.find((p) => p.id === newItem.product_id), newItem.unit)} />
              <input data-testid="po-amend-new-price" type="number" placeholder="Harga" value={newItem.price || ""}
                onChange={(e) => setNewItem({ ...newItem, price: parseFloat(e.target.value) || 0 })} className="field" />
              <input data-testid="po-amend-new-disc" type="number" placeholder="Disc%" min="0" max="100" value={newItem.discount_percent || ""}
                onChange={(e) => setNewItem({ ...newItem, discount_percent: parseFloat(e.target.value) || 0 })} className="field" />
              <button data-testid="po-amend-add-item" onClick={addItem} className="primary-button !px-3"><Plus size={13} /></button>
            </div>
          </div>

          {/* Diskon order + pajak + estimasi */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Diskon Pesanan (%)</label>
              <input data-testid="po-amend-order-discount" type="number" min="0" max="100" value={orderDisc}
                onChange={(e) => setOrderDisc(parseFloat(e.target.value) || 0)} className="field" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Pajak (PPN Masukan)</label>
              <KNSelect data-testid="po-amend-tax-mode" value={taxMode || ""} onValueChange={(v) => setTaxMode(v)}
                className="field" placeholder="Ikut konfigurasi"
                options={[{ value: "", label: "Ikut konfigurasi" }, { value: "non_ppn", label: "Non-PPN (supplier non-PKP)" }]} />
            </div>
          </div>
          <div data-testid="po-amend-estimate" className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5 text-[11.5px] space-y-1">
            <div className="flex justify-between"><span className="text-[#6B6B73]">Subtotal (GROSS)</span><span data-testid="po-amend-est-gross" className="tabular-nums">{formatCurrency(est.gross)}</span></div>
            {est.disc > 0 && <div className="flex justify-between"><span className="text-[#6B6B73]">Total Diskon</span><span data-testid="po-amend-est-disc" className="tabular-nums text-[#A8221A]">− {formatCurrency(est.disc)}</span></div>}
            <div className="flex justify-between border-t border-[#E5E6E8] pt-1 mt-1 font-bold"><span>Subtotal Bersih (sebelum PPN)</span><span data-testid="po-amend-est-net" className="tabular-nums text-[#007AFF]">{formatCurrency(est.net)}</span></div>
          </div>
        </div>

        <div className="modal-actions">
          <button className="secondary-button" data-testid="po-amend-cancel" onClick={onClose} disabled={submitting}>Batal</button>
          <button className="primary-button" data-testid="po-amend-submit" onClick={validateAndSubmit} disabled={submitting || !reason.trim()}>
            {submitting ? "Memproses…" : "Simpan Revisi & Re-approval"}
          </button>
        </div>
      </div>
    </div>
  );
}
