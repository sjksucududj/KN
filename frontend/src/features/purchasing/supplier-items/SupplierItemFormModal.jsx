/**
 * SupplierItemFormModal (FASE E) — buat/ubah satu Barang Supplier.
 * Menerjemahkan KODE & NAMA versi supplier ↔ SKU KN + konversi satuan (E-03).
 */
import { useEffect, useMemo, useState } from "react";
import { Save, X } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { createSupplierItem, patchSupplierItem } from "./supplierItemsApi";
import { overlayDismiss } from "@/utils/overlayDismiss";

const GRADE_OPTIONS = [
  { value: "", label: "— Tidak ditentukan —" },
  { value: "A", label: "A" }, { value: "A1", label: "A1" }, { value: "A2", label: "A2" },
  { value: "B", label: "B" }, { value: "BS", label: "BS" },
];

export default function SupplierItemFormModal({
  editing, suppliers, products, selectedEntity, onClose, onSaved,
}) {
  const isEdit = Boolean(editing?.id);
  const [form, setForm] = useState({
    supplier_id: "", product_id: "", supplier_sku: "", supplier_item_name: "",
    supplier_uom: "", conv_factor: "1", last_price: "", moq: "", lead_time_days: "",
    expected_grade: "", barcode: "", notes: "", status: "active",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!editing) return;
    setForm({
      supplier_id: editing.supplier_id || "",
      product_id: editing.product_id || "",
      supplier_sku: editing.supplier_sku || "",
      supplier_item_name: editing.supplier_item_name || "",
      supplier_uom: editing.supplier_uom || "",
      conv_factor: String(editing.conv_factor ?? "1"),
      last_price: String(editing.last_price ?? ""),
      moq: String(editing.moq ?? ""),
      lead_time_days: String(editing.lead_time_days ?? ""),
      expected_grade: editing.expected_grade || "",
      barcode: editing.barcode || "",
      notes: editing.notes || "",
      status: editing.status || "active",
    });
  }, [editing]);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));
  const product = useMemo(
    () => products.find((p) => p.id === form.product_id) || null, [products, form.product_id]);
  const baseUnit = product?.base_unit || "";
  const convPreview = useMemo(() => {
    const f = parseFloat(form.conv_factor);
    if (!f || !baseUnit) return "";
    const uom = form.supplier_uom || baseUnit;
    return `1 ${uom} = ${f} ${baseUnit}`;
  }, [form.conv_factor, form.supplier_uom, baseUnit]);

  async function save() {
    if (!form.supplier_id) { setErr("Supplier wajib dipilih."); return; }
    if (!form.product_id) { setErr("Produk KN wajib dipilih."); return; }
    if (!form.supplier_sku.trim()) { setErr("Kode barang versi supplier wajib diisi."); return; }
    if (!(parseFloat(form.conv_factor) > 0)) { setErr("Faktor konversi harus lebih besar dari 0."); return; }
    setBusy(true); setErr("");
    const body = {
      supplier_id: form.supplier_id,
      product_id: form.product_id,
      supplier_sku: form.supplier_sku.trim(),
      supplier_item_name: form.supplier_item_name.trim(),
      supplier_uom: form.supplier_uom.trim(),
      conv_factor: parseFloat(form.conv_factor),
      last_price: parseFloat(form.last_price) || 0,
      moq: parseFloat(form.moq) || 0,
      lead_time_days: parseInt(form.lead_time_days, 10) || 0,
      expected_grade: form.expected_grade,
      barcode: form.barcode.trim(),
      notes: form.notes,
      status: form.status,
      entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "",
    };
    try {
      const saved = isEdit ? await patchSupplierItem(editing.id, body) : await createSupplierItem(body);
      onSaved?.(saved);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal menyimpan barang supplier.");
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" data-testid="supplier-item-form-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card wide" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <p className="modal-title">{isEdit ? "Ubah Barang Supplier" : "Barang Supplier Baru"}</p>
            <p className="modal-subtitle">
              Petakan KODE & NAMA versi supplier ke SKU KN, termasuk konversi satuan.
            </p>
          </div>
          <button className="icon-button" onClick={onClose} data-testid="supplier-item-form-close">
            <X size={16} />
          </button>
        </div>

        {err && (
          <div className="notice-bar danger" data-testid="supplier-item-form-error">
            <span>{err}</span><button onClick={() => setErr("")}>×</button>
          </div>
        )}

        <div className="grid gap-3 mt-2 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Supplier *</label>
            <KNSelect data-testid="supplier-item-supplier" className="form-input"
              value={form.supplier_id} onValueChange={(v) => set("supplier_id", v)}
              placeholder="— Pilih supplier —" disabled={isEdit}
              options={suppliers.map((s) => ({ value: s.id, label: s.name }))} />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Produk KN (SKU) *</label>
            <KNSelect data-testid="supplier-item-product" className="form-input"
              value={form.product_id} onValueChange={(v) => set("product_id", v)}
              placeholder="— Pilih produk —"
              options={products.filter((p) => p.status !== "inactive")
                .map((p) => ({ value: p.id, label: `${p.sku} · ${p.name}` }))} />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Kode Barang Supplier *</label>
            <input data-testid="supplier-item-sku" className="form-input" value={form.supplier_sku}
              onChange={(e) => set("supplier_sku", e.target.value)} placeholder="mis. TX-COT-30S" />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Nama Barang Supplier</label>
            <input data-testid="supplier-item-name" className="form-input" value={form.supplier_item_name}
              onChange={(e) => set("supplier_item_name", e.target.value)}
              placeholder="mis. Cotton Combed 30s Cone 1,89kg" />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">
              Satuan Supplier {baseUnit ? `(satuan KN: ${baseUnit})` : ""}
            </label>
            <input data-testid="supplier-item-uom" className="form-input" value={form.supplier_uom}
              onChange={(e) => set("supplier_uom", e.target.value)}
              placeholder={baseUnit || "mis. cone / roll / bale"} />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Faktor Konversi *</label>
            <input type="number" step="0.0001" data-testid="supplier-item-conv" className="form-input"
              value={form.conv_factor} onChange={(e) => set("conv_factor", e.target.value)} />
            {convPreview && (
              <p className="text-[10.5px] text-[#1B7F4B] tabular-nums" data-testid="supplier-item-conv-preview">
                {convPreview}
              </p>
            )}
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Harga Terakhir (per satuan supplier)</label>
            <input type="number" data-testid="supplier-item-price" className="form-input"
              value={form.last_price} onChange={(e) => set("last_price", e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">MOQ</label>
            <input type="number" data-testid="supplier-item-moq" className="form-input"
              value={form.moq} onChange={(e) => set("moq", e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Lead Time (hari)</label>
            <input type="number" data-testid="supplier-item-lead" className="form-input"
              value={form.lead_time_days} onChange={(e) => set("lead_time_days", e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Grade Dijanjikan</label>
            <KNSelect data-testid="supplier-item-grade" className="form-input"
              value={form.expected_grade} onValueChange={(v) => set("expected_grade", v)}
              placeholder="— Tidak ditentukan —" options={GRADE_OPTIONS} />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Barcode</label>
            <input data-testid="supplier-item-barcode" className="form-input" value={form.barcode}
              onChange={(e) => set("barcode", e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Status</label>
            <KNSelect data-testid="supplier-item-status" className="form-input"
              value={form.status} onValueChange={(v) => set("status", v)}
              options={[{ value: "active", label: "Aktif" }, { value: "inactive", label: "Nonaktif" }]} />
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Catatan</label>
            <textarea data-testid="supplier-item-notes" className="form-input" rows="2"
              value={form.notes} onChange={(e) => set("notes", e.target.value)} />
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose}>Batal</button>
          <button data-testid="supplier-item-save" className="btn-primary" onClick={save} disabled={busy}>
            <Save size={14} /> {busy ? "Menyimpan…" : "Simpan"}
          </button>
        </div>
      </div>
    </div>
  );
}
