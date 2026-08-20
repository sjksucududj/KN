/** InitialStockForm — manual initial-stock (roll) entry (admin/manager only). */
import { X } from "lucide-react";
import KNSelect from "../../../components/KNSelect";

export default function InitialStockForm({ stockForm, setStockForm, products = [], warehouses = [], entities = [], submitting, onSubmit, onClose, variant = "card" }) {
  // FASE P5 — `variant="modal"`: kartu, judul & tombolnya sendiri dilepas karena
  // `FormModal` sudah menyediakannya (anti kartu-di-dalam-kartu & judul bertumpuk).
  // Form ini dulu INLINE: kartunya menyelip di tengah halaman dan mendorong tabel stok
  // ke bawah. Ia lolos dari gate P4 karena seluruh isiannya ada di berkas ini (anak),
  // sementara penjaganya hanya memeriksa berkas induk — celah itu ikut ditutup.
  const isModal = variant === "modal";
  return (
    <div className={isModal ? "" : "rounded-xl border border-[#E5E5EA] bg-white p-3"}>
      {!isModal && (
        <div className="flex items-center justify-between mb-2.5">
          <p className="text-[12px] font-bold">Tambah Stok Awal (Roll)</p>
          <button onClick={onClose} data-testid="close-stock-form"><X size={13} className="text-[#6B6B73]" /></button>
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div className="col-span-2 sm:col-span-1">
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Produk *</label>
          <KNSelect data-testid="stock-product-select" value={stockForm.product_id}
            onValueChange={v => setStockForm({ ...stockForm, product_id: v })}
            className="field" placeholder="Pilih produk..."
            options={[{ value: "", label: "Pilih produk..." }, ...products.map(p => ({ value: p.id, label: `${p.sku} — ${p.name}` }))]}
          />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Pemilik (Entitas) *</label>
          <KNSelect data-testid="stock-owner-select" value={stockForm.owner_entity_id}
            onValueChange={v => setStockForm({ ...stockForm, owner_entity_id: v })}
            className="field" placeholder="Pilih entitas..."
            options={[{ value: "", label: "Pilih entitas..." }, ...entities.map(en => ({ value: en.id, label: en.short_name || en.legal_name }))]}
          />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Gudang *</label>
          <KNSelect data-testid="stock-warehouse-select" value={stockForm.warehouse_id}
            onValueChange={v => setStockForm({ ...stockForm, warehouse_id: v })}
            className="field" placeholder="Pilih gudang..."
            options={[{ value: "", label: "Pilih gudang..." }, ...warehouses.map(w => ({ value: w.id, label: w.name }))]}
          />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Panjang (Qty) *</label>
          <input type="number" data-testid="stock-qty-input" value={stockForm.quantity} onChange={e => setStockForm({ ...stockForm, quantity: parseFloat(e.target.value) || 0 })} className="field tabular-nums" placeholder="0" />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Unit</label>
          <input type="text" value={stockForm.unit} onChange={e => setStockForm({ ...stockForm, unit: e.target.value })} className="field" placeholder="meter" />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Lot *</label>
          <input type="text" data-testid="stock-lot-input" value={stockForm.lot} onChange={e => setStockForm({ ...stockForm, lot: e.target.value })} className="field" placeholder="LOT-2026-001" />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Grade</label>
          <KNSelect data-testid="stock-grade-select" value={stockForm.grade}
            onValueChange={v => setStockForm({ ...stockForm, grade: v })}
            className="field"
            options={[{ value: "A", label: "A" }, { value: "B", label: "B" }, { value: "C", label: "C" }, { value: "Reject", label: "Reject" }]}
          />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Roll No</label>
          <input type="text" value={stockForm.roll_no} onChange={e => setStockForm({ ...stockForm, roll_no: e.target.value })} className="field" placeholder="(auto)" />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-[#6B6B73] mb-1">Batch</label>
          <input type="text" value={stockForm.batch} onChange={e => setStockForm({ ...stockForm, batch: e.target.value })} className="field" />
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        {!isModal && (
          <>
            <button onClick={onSubmit} disabled={submitting} data-testid="submit-stock-button"
              className="flex-1 bg-[#34C759] hover:bg-[#28A745] text-white rounded-lg px-4 py-2 text-[12px] font-semibold disabled:opacity-50">
              Simpan Roll
            </button>
            <button onClick={onClose} className="secondary-button">Batal</button>
          </>
        )}
      </div>
    </div>
  );
}
