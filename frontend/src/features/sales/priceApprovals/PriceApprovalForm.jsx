import { useMemo } from "react";
import { X, Send } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import KNSelect from "../../../components/KNSelect";

/**
 * Form ajukan / edit pengajuan harga khusus.
 * Named export (komponen). State diangkat ke parent (PriceApprovals.jsx).
 */
export function PriceApprovalForm({
  editId,
  form,
  setForm,
  formErr,
  busyId,
  customers,
  products,
  onClose,
  onSubmit,
  variant = "card",
}) {
  // FASE P5 — `variant="modal"`: kartu & judulnya sendiri dilepas (FormModal yang
  // menyediakannya). Tombolnya tetap di sini karena ada DUA aksi berbeda
  // ("Simpan sebagai Draft" vs "Ajukan untuk Persetujuan") yang bukan satu tombol simpan.
  const isModal = variant === "modal";
  const selectedProduct = useMemo(
    () => products.find((p) => p.id === form.product_id),
    [products, form.product_id],
  );

  return (
    <section data-testid="price-approvals-form" className={isModal ? "" : "section-card p-4"}>
      {!isModal && (
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-[13px] font-bold text-[#1C1C1E]">{editId ? "Edit Pengajuan Harga" : "Ajukan Harga Khusus"}</h3>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={14} /></button>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
          Pelanggan
          <KNSelect
            data-testid="price-approvals-customer"
            className="field"
            disabled={!!editId}
            value={form.customer_id}
            onValueChange={(v) => setForm({ ...form, customer_id: v })}
            placeholder="— Pilih Pelanggan —"
            options={[
              { value: "", label: "— Pilih Pelanggan —" },
              ...customers.map((c) => ({ value: c.id, label: c.name })),
            ]}
          />
        </label>
        <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
          Produk
          <KNSelect
            data-testid="price-approvals-product"
            className="field"
            disabled={!!editId}
            value={form.product_id}
            onValueChange={(v) => setForm({ ...form, product_id: v })}
            placeholder="— Pilih Produk —"
            options={[
              { value: "", label: "— Pilih Produk —" },
              ...products.map((p) => ({ value: p.id, label: `${p.name} (${p.sku})` })),
            ]}
          />
        </label>
        <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
          Harga Khusus / unit
          {selectedProduct && (
            <span className="text-[10px] font-normal text-[#8E8E93]">Harga normal: {formatCurrency(selectedProduct.price)}</span>
          )}
          <input
            data-testid="price-approvals-price"
            type="number" min="0" className="field tabular-nums"
            placeholder="cth: 150000"
            value={form.requested_price}
            onChange={(e) => setForm({ ...form, requested_price: e.target.value })}
          />
        </label>
        <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
          Qty Minimum
          <input
            data-testid="price-approvals-minqty"
            type="number" min="0" className="field tabular-nums"
            placeholder="0"
            value={form.min_quantity}
            onChange={(e) => setForm({ ...form, min_quantity: e.target.value })}
          />
        </label>
        <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
          Berlaku Sampai (opsional)
          <input
            data-testid="price-approvals-validuntil"
            type="date" className="field"
            value={form.valid_until}
            onChange={(e) => setForm({ ...form, valid_until: e.target.value })}
          />
        </label>
        <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73] sm:col-span-2">
          Alasan / Catatan
          <textarea
            data-testid="price-approvals-reason"
            className="field min-h-[56px] text-[12px]"
            placeholder="Konteks negosiasi harga…"
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </label>
      </div>
      {formErr && <p data-testid="price-approvals-form-error" className="mt-2 text-[11px] font-semibold text-[#A8221A]">{formErr}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          data-testid="price-approvals-save"
          disabled={busyId === "form"}
          onClick={() => onSubmit(false)}
          className="rounded-md border border-[#E5E5EA] px-4 py-1.5 text-[12px] font-semibold text-[#3C3C43] disabled:opacity-50"
        >
          {editId ? "Simpan Perubahan" : "Simpan sebagai Draft"}
        </button>
        {!editId && (
          <button
            data-testid="price-approvals-save-submit"
            disabled={busyId === "form"}
            onClick={() => onSubmit(true)}
            className="flex items-center gap-1.5 rounded-md bg-[#6B219A] px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50"
          >
            <Send size={13} /> Ajukan untuk Persetujuan
          </button>
        )}
      </div>
    </section>
  );
}
