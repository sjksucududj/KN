/** TransferCreateForm — create a new inter-warehouse transfer (warehouses + items + notes). */
import { Plus, XCircle } from "lucide-react";
import { formatQty } from "../../../utils/formatters";
import KNSelect from "../../../components/KNSelect";

export default function TransferCreateForm({
  formData, setFormData, newItem, setNewItem,
  products = [], warehouses = [], onAddItem, onRemoveItem, onSubmit, onClose,
  variant = "card",
}) {
  // FASE P4 — `variant="modal"`: kartu & judul sendiri dilepas (FormModal yang
  // menyediakannya) supaya tidak ada kartu di dalam kartu dan dua judul bertumpuk.
  const isModal = variant === "modal";
  return (
    <div data-testid="create-transfer-form"
      className={isModal ? "" : "bg-white border border-[#E5E5EA] rounded-2xl p-6 shadow-sm"}>
      {!isModal && <h3 className="text-md font-semibold mb-4">Buat Transfer Baru</h3>}

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-[#3C3C43] mb-2">Gudang Asal</label>
          <KNSelect
            data-testid="source-warehouse-select"
            value={formData.source_warehouse_id}
            onValueChange={v => setFormData({ ...formData, source_warehouse_id: v })}
            className="w-full bg-white border border-gray-200 rounded-xl px-3 py-2 text-sm"
            placeholder="Pilih Gudang"
            options={[
              { value: "", label: "Pilih Gudang" },
              ...warehouses.map(wh => ({ value: wh.id, label: `${wh.name} (${wh.code})` })),
            ]}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-[#3C3C43] mb-2">Gudang Tujuan</label>
          <KNSelect
            data-testid="dest-warehouse-select"
            value={formData.dest_warehouse_id}
            onValueChange={v => setFormData({ ...formData, dest_warehouse_id: v })}
            className="w-full bg-white border border-gray-200 rounded-xl px-3 py-2 text-sm"
            placeholder="Pilih Gudang"
            options={[
              { value: "", label: "Pilih Gudang" },
              ...warehouses.map(wh => ({ value: wh.id, label: `${wh.name} (${wh.code})` })),
            ]}
          />
        </div>
      </div>

      {/* Add Item */}
      <div className="bg-[#F2F2F7] rounded-xl p-4 mb-4">
        <h4 className="text-sm font-semibold mb-3">Tambah Item</h4>
        <div className="grid grid-cols-[1fr_100px_100px_auto] gap-2">
          <KNSelect
            data-testid="item-product-select"
            value={newItem.product_id}
            onValueChange={v => setNewItem({ ...newItem, product_id: v })}
            className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm"
            placeholder="Pilih Produk"
            options={[
              { value: "", label: "Pilih Produk" },
              ...products.map(p => ({ value: p.id, label: `${p.sku} - ${p.name}` })),
            ]}
          />
          <input
            data-testid="item-qty-input"
            type="number"
            placeholder="Qty"
            value={newItem.qty}
            onChange={(e) => setNewItem({ ...newItem, qty: parseFloat(e.target.value) || 0 })}
            className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm tabular-nums"
          />
          <input
            data-testid="item-unit-input"
            type="text"
            placeholder="Unit"
            value={newItem.unit}
            onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })}
            className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
          <button
            data-testid="add-item-button"
            onClick={onAddItem}
            className="bg-[#007AFF] hover:bg-[#0056B3] text-white rounded-lg px-4 py-2 text-sm font-medium"
          >
            <Plus size={16} />
          </button>
        </div>
      </div>

      {/* Items List */}
      {formData.items.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-semibold mb-2">Items ({formData.items.length})</h4>
          <div className="space-y-2">
            {formData.items.map((item, index) => {
              const product = products.find((p) => p.id === item.product_id);
              return (
                <div key={index} data-testid={`item-row-${index}`} className="flex items-center justify-between bg-white rounded-lg p-2 border border-[#E5E5EA]">
                  <span className="text-sm">{product?.sku} - {product?.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold tabular-nums">{formatQty(item.qty)} {item.unit}</span>
                    <button
                      data-testid={`remove-item-${index}`}
                      onClick={() => onRemoveItem(index)}
                      className="text-red-500 hover:text-red-700"
                    >
                      <XCircle size={16} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Notes */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-[#3C3C43] mb-2">Catatan (opsional)</label>
        <textarea
          data-testid="transfer-notes-input"
          value={formData.notes}
          onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
          className="w-full bg-white border border-gray-200 focus:ring-2 focus:ring-[#007AFF]/20 focus:border-[#007AFF] rounded-xl px-3 py-2 text-sm"
          rows="2"
        />
      </div>

      {/* Tombol aksi hanya dipakai pada mode halaman; di pop-up, FormModal yang
          menyediakan tombol Simpan/Batal yang menempel di bawah. */}
      {!isModal && (
        <div className="flex gap-2">
          <button
            data-testid="submit-transfer-button"
            onClick={onSubmit}
            className="flex-1 bg-[#007AFF] hover:bg-[#0056B3] text-white rounded-full px-6 py-2.5 font-medium"
          >
            Buat Transfer
          </button>
          <button
            data-testid="cancel-form-button"
            onClick={onClose}
            className="flex-1 bg-white border border-[#E5E5EA] hover:border-[#007AFF] text-[#3C3C43] rounded-full px-6 py-2.5 font-medium"
          >
            Batal
          </button>
        </div>
      )}
    </div>
  );
}
