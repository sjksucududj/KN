import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, Plus, Trash2, FileStack } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import { GroupEntityNotice, isGroupEntityPartner, supplierOptionLabel }
  from "../../components/GroupEntityBadge";

/**
 * BlanketPOCreateModal (P2) — buat kontrak Blanket/Contract PO.
 * 1.c — komitmen = kuantitas per item (contract_qty) + plafon nilai (contract_value_cap).
 * Plafon 0 → backend default = Σ qty × harga.
 */
export default function BlanketPOCreateModal({ open, selectedEntity, onClose, onCreated, onError }) {
  const [supplierId, setSupplierId] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [supplierContact, setSupplierContact] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [valueCap, setValueCap] = useState("");
  const [notes, setNotes] = useState("");
  const [rows, setRows] = useState([{ product_id: "", contract_qty: "", contract_price: "", unit: "" }]);
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) { reset(); return; }
    (async () => {
      try {
        const [p, s, w] = await Promise.all([
          axios.get(`${API}/products`),
          axios.get(`${API}/suppliers`),
          axios.get(`${API}/warehouses`),
        ]);
        setProducts(Array.isArray(p.data) ? p.data : []);
        setSuppliers(Array.isArray(s.data) ? s.data : []);
        setWarehouses(Array.isArray(w.data) ? w.data : []);
      } catch (e) { onError?.("Gagal memuat data master."); }
    })();
  }, [open]); // eslint-disable-line

  function reset() {
    setSupplierId(""); setSupplierName(""); setSupplierContact(""); setWarehouseId("");
    setValidFrom(""); setValidUntil(""); setValueCap(""); setNotes("");
    setRows([{ product_id: "", contract_qty: "", contract_price: "", unit: "" }]);
  }

  const activeSuppliers = useMemo(() => suppliers.filter((s) => s.status !== "inactive"), [suppliers]);
  const supplierOptions = useMemo(() => [
    { value: "", label: "— Isi manual / tanpa master —" },
    // FASE E-7 (E7.2) — badan usaha grup ditandai sejak di daftar pilihan.
    ...activeSuppliers.map((s) => ({
      value: s.id, label: supplierOptionLabel(s, `${s.code || ""} ${s.name}`.trim()),
    })),
  ], [activeSuppliers]);
  const selectedSupplier = useMemo(
    () => suppliers.find((s) => s.id === supplierId) || null, [suppliers, supplierId]);
  const supplierIsGroupEntity = isGroupEntityPartner(selectedSupplier);
  const warehouseOptions = useMemo(
    () => warehouses.map((w) => ({ value: w.id, label: `${w.name}${w.code ? ` (${w.code})` : ""}` })), [warehouses]);
  const productOptions = useMemo(
    () => [{ value: "", label: "Pilih produk..." }, ...products.map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` }))], [products]);

  function handleSupplier(v) {
    setSupplierId(v);
    if (v) {
      const s = suppliers.find((x) => x.id === v);
      setSupplierName(s?.name || "");
      setSupplierContact([s?.pic_name, s?.phone].filter(Boolean).join(" · "));
    }
  }

  function setRow(i, patch) {
    setRows((rs) => rs.map((r, idx) => {
      if (idx !== i) return r;
      const next = { ...r, ...patch };
      if (patch.product_id !== undefined) {
        const prod = products.find((p) => p.id === patch.product_id);
        if (prod) {
          if (!next.unit) next.unit = prod.base_unit || "meter";
          if (!next.contract_price) next.contract_price = prod.price || "";
        }
      }
      return next;
    }));
  }
  function addRow() { setRows((rs) => [...rs, { product_id: "", contract_qty: "", contract_price: "", unit: "" }]); }
  function delRow(i) { setRows((rs) => (rs.length === 1 ? rs : rs.filter((_, idx) => idx !== i))); }

  const computedTotal = useMemo(
    () => rows.reduce((sum, r) => sum + (Number(r.contract_qty) || 0) * (Number(r.contract_price) || 0), 0), [rows]);
  const effectiveCap = Number(valueCap) > 0 ? Number(valueCap) : computedTotal;

  async function submit() {
    if (!warehouseId) { onError?.("Pilih gudang default."); return; }
    if (!supplierId && !supplierName.trim()) { onError?.("Pilih supplier master atau isi nama supplier."); return; }
    const items = rows
      .filter((r) => r.product_id && Number(r.contract_qty) > 0)
      .map((r) => ({
        product_id: r.product_id,
        contract_qty: Number(r.contract_qty),
        contract_price: Number(r.contract_price) || 0,
        unit: r.unit || "",
      }));
    if (items.length === 0) { onError?.("Tambah minimal 1 item kontrak (produk + qty > 0)."); return; }
    if (validFrom && validUntil && validUntil < validFrom) {
      onError?.("Masa berlaku akhir tidak boleh sebelum mulai."); return;
    }
    setBusy(true);
    try {
      const body = {
        supplier_id: supplierId, supplier_name: supplierName, supplier_contact: supplierContact,
        warehouse_id: warehouseId, items,
        contract_value_cap: Number(valueCap) || 0,
        valid_from: validFrom, valid_until: validUntil, notes,
        entity_id: (selectedEntity && selectedEntity !== "all") ? selectedEntity : "",
      };
      const r = await axios.post(`${API}/purchase-orders/blanket`, body);
      onCreated?.(r.data);
    } catch (e) {
      onError?.(e.response?.data?.detail || "Gagal membuat kontrak.");
    } finally { setBusy(false); }
  }

  if (!open) return null;

  return (
    <div className="modal-overlay" data-testid="blanket-create-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 760, width: "95vw", maxHeight: "92vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2] sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2"><FileStack size={16} className="text-[#0058CC]" /><h2 className="text-[14px] font-bold">Buat Kontrak Blanket / Contract PO</h2></div>
          <button data-testid="blanket-create-close" onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Supplier (Master)">
              <KNSelect value={supplierId} onValueChange={handleSupplier} options={supplierOptions}
                className="field" placeholder="Pilih dari master / manual" data-testid="blanket-supplier-select" />
            </Field>
            <Field label="Nama Supplier" req={!supplierId}>
              <input data-testid="blanket-supplier-name" value={supplierName} disabled={!!supplierId}
                onChange={(e) => setSupplierName(e.target.value)}
                className="field disabled:bg-gray-100 disabled:text-gray-500" placeholder="PT Supplier Textile" />
            </Field>
            <Field label="Kontak Supplier">
              <input data-testid="blanket-supplier-contact" value={supplierContact}
                onChange={(e) => setSupplierContact(e.target.value)} className="field" placeholder="PIC · telepon" />
            </Field>
            {/* FASE E-7 (E7.2) — komitmen harga ke badan usaha grup adalah KONTRAK
                INTERNAL, bukan Blanket PO: call-off-nya akan melahirkan PO biasa dan
                margin antar-PT tidak pernah dieliminasi di konsolidasi. */}
            {supplierIsGroupEntity && (
              <div className="col-span-2">
                <GroupEntityNotice partner={selectedSupplier} docLabel="Kontrak Blanket PO" />
              </div>
            )}
            <Field label="Gudang Default" req>
              <KNSelect value={warehouseId} onValueChange={setWarehouseId} options={warehouseOptions}
                className="field" placeholder="Pilih gudang..." data-testid="blanket-warehouse-select" />
            </Field>
            <Field label="Berlaku Mulai">
              <input type="date" data-testid="blanket-valid-from" value={validFrom}
                onChange={(e) => setValidFrom(e.target.value)} className="field" />
            </Field>
            <Field label="Berlaku Sampai">
              <input type="date" data-testid="blanket-valid-until" value={validUntil}
                onChange={(e) => setValidUntil(e.target.value)} className="field" />
              <p className="text-[10px] text-[#9A9BA3] mt-0.5">Kosongkan = tanpa kadaluarsa</p>
            </Field>
          </div>

          {/* Items kontrak */}
          <div>
            <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Item Kontrak <span className="text-red-500">*</span></label>
            <div className="grid grid-cols-[1fr_90px_110px_80px_32px] gap-2 px-1 mb-1 text-[10px] font-bold uppercase text-[#9A9BA3]">
              <span>Produk</span><span>Qty Kontrak</span><span>Harga Sepakat</span><span>Unit</span><span></span>
            </div>
            <div className="space-y-2">
              {rows.map((r, i) => (
                <div key={i} className="grid grid-cols-[1fr_90px_110px_80px_32px] gap-2" data-testid={`blanket-item-row-${i}`}>
                  <KNSelect value={r.product_id} onValueChange={(v) => setRow(i, { product_id: v })}
                    options={productOptions} className="field" placeholder="Produk..." data-testid={`blanket-item-product-${i}`} />
                  <input type="number" value={r.contract_qty} onChange={(e) => setRow(i, { contract_qty: e.target.value })}
                    className="field" placeholder="Qty" data-testid={`blanket-item-qty-${i}`} />
                  <input type="number" value={r.contract_price} onChange={(e) => setRow(i, { contract_price: e.target.value })}
                    className="field" placeholder="Harga" data-testid={`blanket-item-price-${i}`} />
                  <input value={r.unit} onChange={(e) => setRow(i, { unit: e.target.value })} className="field" placeholder="unit" />
                  <button onClick={() => delRow(i)} disabled={rows.length === 1}
                    className="icon-button text-red-500 disabled:opacity-30"><Trash2 size={14} /></button>
                </div>
              ))}
            </div>
            <button data-testid="blanket-add-item" onClick={addRow} className="secondary-button mt-2 text-[11px]">
              <Plus size={12} /> Tambah Item
            </button>
          </div>

          {/* Plafon nilai + ringkasan */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Plafon Nilai Kontrak (Rp)">
              <input type="number" data-testid="blanket-value-cap" value={valueCap}
                onChange={(e) => setValueCap(e.target.value)} className="field" placeholder="0 = otomatis Σ qty×harga" />
            </Field>
            <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5 text-[11.5px]" data-testid="blanket-summary">
              <div className="flex justify-between"><span className="text-[#6B6B73]">Σ qty × harga</span><span className="tabular-nums">{formatCurrency(computedTotal)}</span></div>
              <div className="flex justify-between font-bold mt-1 pt-1 border-t border-[#EFF0F2]">
                <span>Plafon Efektif</span>
                <span data-testid="blanket-effective-cap" className="tabular-nums text-[#007AFF]">{formatCurrency(effectiveCap)}</span>
              </div>
            </div>
          </div>

          <Field label="Catatan">
            <textarea data-testid="blanket-notes" value={notes} onChange={(e) => setNotes(e.target.value)}
              className="field" rows="2" placeholder="Catatan kontrak (termin, syarat, dll)…" />
          </Field>
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2] sticky bottom-0 bg-white">
          <button onClick={onClose} className="secondary-button">Batal</button>
          <button data-testid="blanket-submit" disabled={busy || supplierIsGroupEntity} onClick={submit}
            title={supplierIsGroupEntity
              ? `${selectedSupplier?.name} adalah badan usaha di dalam grup — pakai menu Antar Entitas`
              : ""}
            className="primary-button disabled:opacity-50 disabled:cursor-not-allowed">
            {busy ? "Menyimpan..." : "Buat Kontrak"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">{label}{req && <span className="text-red-500"> *</span>}</label>
      {children}
    </div>
  );
}
