import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Plus, Pencil, Power, Tag, X, RefreshCw, AlertTriangle } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import FormModal from "../../components/FormModal";
import { formatCurrency, formatQty } from "../../utils/formatters";

/**
 * SupplierPriceList (Depth #3) — CRUD daftar harga beli per (supplier, product).
 * Unit default = base_unit produk (UOM engine). Dipakai auto-isi harga PO/PR.
 */
const EMPTY = {
  product_id: "", price: "", unit: "", min_qty: "0", lead_time_days: "0",
  valid_from: "", valid_until: "", notes: "",
};

function fmtDate(d) {
  if (!d) return "∞";
  try { return new Date(d).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return d; }
}

export default function SupplierPriceList({ supplierId, canManage }) {
  const [entries, setEntries] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [showInactive, setShowInactive] = useState(false);
  const [deactivateTarget, setDeactivateTarget] = useState(null);

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [supplierId, showInactive]);

  async function load() {
    setLoading(true);
    try {
      const [eRes, pRes] = await Promise.all([
        axios.get(`${API}/suppliers/${supplierId}/price-list`, { params: { include_inactive: showInactive } }),
        axios.get(`${API}/products`).catch(() => ({ data: [] })),
      ]);
      setEntries(Array.isArray(eRes.data) ? eRes.data : []);
      setProducts(Array.isArray(pRes.data) ? pRes.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat price-list.");
    } finally {
      setLoading(false);
    }
  }

  function openCreate() {
    setEditId(null); setForm(EMPTY); setShowForm(true);
  }
  function openEdit(en) {
    setEditId(en.id);
    setForm({
      product_id: en.product_id, price: String(en.price ?? ""), unit: en.unit || "",
      min_qty: String(en.min_qty ?? "0"), lead_time_days: String(en.lead_time_days ?? "0"),
      valid_from: (en.valid_from || "").slice(0, 10), valid_until: (en.valid_until || "").slice(0, 10),
      notes: en.notes || "",
    });
    setShowForm(true);
  }

  function onSelectProduct(pid) {
    const p = products.find((x) => x.id === pid);
    setForm((f) => ({ ...f, product_id: pid, unit: f.unit || p?.base_unit || "meter" }));
  }

  async function handleSubmit() {
    if (!form.product_id) { setError("Pilih produk dahulu."); return; }
    if (!(parseFloat(form.price) > 0)) { setError("Harga harus lebih dari 0."); return; }
    try {
      if (editId) {
        await axios.patch(`${API}/supplier-price-list/${editId}`, {
          data: {
            price: parseFloat(form.price), unit: form.unit || "meter",
            min_qty: parseFloat(form.min_qty) || 0, lead_time_days: parseInt(form.lead_time_days, 10) || 0,
            valid_from: form.valid_from, valid_until: form.valid_until, notes: form.notes,
          },
        });
        setNotice("Entri harga diperbarui.");
      } else {
        await axios.post(`${API}/suppliers/${supplierId}/price-list`, {
          product_id: form.product_id, price: parseFloat(form.price), unit: form.unit || "",
          min_qty: parseFloat(form.min_qty) || 0, lead_time_days: parseInt(form.lead_time_days, 10) || 0,
          valid_from: form.valid_from, valid_until: form.valid_until, notes: form.notes,
        });
        setNotice("Entri harga ditambahkan.");
      }
      setShowForm(false); setEditId(null); setForm(EMPTY);
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan entri harga.");
    }
  }

  async function handleDeactivate(en) {
    setDeactivateTarget(en);
  }

  async function doDeactivate(en) {
    try {
      await axios.delete(`${API}/supplier-price-list/${en.id}`);
      setNotice("Entri harga dinonaktifkan.");
      setDeactivateTarget(null);
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menonaktifkan entri.");
      setDeactivateTarget(null);
    }
  }

  const productOpts = [
    { value: "", label: "Pilih Produk" },
    ...products.map((p) => ({ value: p.id, label: `${p.sku} - ${p.name}` })),
  ];

  return (
    <div data-testid="supplier-price-list">
      {notice && (
        <div className="notice-bar success" data-testid="price-list-notice">
          <span>{notice}</span><button onClick={() => setNotice("")}><X size={13} /></button>
        </div>
      )}
      {error && (
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="price-list-error" />
      )}

      <div className="flex items-center justify-between mb-2.5 flex-wrap gap-2">
        <label className="flex items-center gap-1.5 text-[11px] text-[#6B6B73] cursor-pointer">
          <input data-testid="price-list-show-inactive" type="checkbox" checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)} />
          Tampilkan nonaktif
        </label>
        {canManage && (
          <button data-testid="add-price-entry-button" onClick={openCreate} className="primary-button">
            <Plus size={13} /> Tambah Harga
          </button>
        )}
      </div>

      {/* FASE P4 — form harga beli menjadi POP-UP (dulu menyelip di atas tabel harga). */}
      <FormModal
        open={showForm && canManage}
        onClose={() => { setShowForm(false); setEditId(null); }}
        title={editId ? "Ubah Harga Beli" : "Tambah Harga Beli"}
        subtitle="Harga per unit, MOQ, lead time, dan masa berlaku"
        icon={Tag}
        size="md"
        testId="price-entry-form"
        onSubmit={handleSubmit}
        submitLabel={editId ? "Simpan" : "Tambah"}
        submitTestId="submit-price-entry-button"
        cancelTestId="cancel-price-entry-button"
        error={error}
      >
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Produk <span className="req">*</span></label>
              <KNSelect data-testid="price-product-select" value={form.product_id} onValueChange={onSelectProduct}
                disabled={!!editId} options={productOpts} placeholder="Pilih Produk" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Harga Beli (per unit) <span className="req">*</span></label>
              <input data-testid="price-amount-input" type="number" value={form.price}
                onChange={(e) => setForm({ ...form, price: e.target.value })} className="field" placeholder="150000" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Unit (UOM)</label>
              <input data-testid="price-unit-input" type="text" value={form.unit}
                onChange={(e) => setForm({ ...form, unit: e.target.value })} className="field" placeholder="meter" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">MOQ (qty minimum)</label>
              <input data-testid="price-minqty-input" type="number" value={form.min_qty}
                onChange={(e) => setForm({ ...form, min_qty: e.target.value })} className="field" placeholder="0" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Lead Time (hari)</label>
              <input data-testid="price-leadtime-input" type="number" value={form.lead_time_days}
                onChange={(e) => setForm({ ...form, lead_time_days: e.target.value })} className="field" placeholder="0 = pakai default" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Berlaku Dari</label>
              <input data-testid="price-validfrom-input" type="date" value={form.valid_from}
                onChange={(e) => setForm({ ...form, valid_from: e.target.value })} className="field" />
            </div>
            <div>
              <label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Berlaku Sampai</label>
              <input data-testid="price-validuntil-input" type="date" value={form.valid_until}
                onChange={(e) => setForm({ ...form, valid_until: e.target.value })} className="field" />
            </div>
          </div>
      </FormModal>

      <div className="section-card">
        <div className="overflow-hidden">
          <div className="grid grid-cols-[1.4fr_110px_70px_80px_110px_70px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Produk</span><span className="text-right">Harga / Unit</span><span className="text-right">MOQ</span><span className="text-right">Lead</span><span>Berlaku</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div data-testid="price-list-loading" className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat harga...</div>
          ) : error ? (
            <div className="py-8 text-center"><AlertTriangle className="mx-auto mb-2 text-[#C62828]" size={24} />
              <button data-testid="price-list-retry" onClick={load} className="secondary-button mx-auto"><RefreshCw size={13} /> Coba lagi</button></div>
          ) : entries.length === 0 ? (
            <div data-testid="price-list-empty" className="py-12 text-center text-[12px] text-[#6B6B73]">
              <Tag className="mx-auto mb-2 text-gray-300" size={26} />
              <p>Belum ada daftar harga. {canManage && "Tambah harga beli pertama."}</p>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[360px] overflow-y-auto">
              {entries.map((en) => (
                <div key={en.id} data-testid={`price-entry-${en.id}`}
                  className={`grid grid-cols-[1.4fr_110px_70px_80px_110px_70px] items-center px-3 py-2.5 ${en.status === "inactive" ? "opacity-50" : ""}`}>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{en.product_name}</p>
                    <p className="text-[10.5px] text-[#6B6B73] truncate">{en.sku}{en.notes ? ` · ${en.notes}` : ""}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[12px] font-bold tabular-nums" data-testid={`price-entry-amount-${en.id}`}>{formatCurrency(en.price)}</p>
                    <p className="text-[10px] text-[#6B6B73]">/ {en.unit}</p>
                  </div>
                  <span className="text-right text-[11.5px] tabular-nums">{en.min_qty > 0 ? formatQty(en.min_qty) : "—"}</span>
                  <span className="text-right text-[11.5px] tabular-nums">{en.lead_time_days > 0 ? `${en.lead_time_days}h` : "—"}</span>
                  <span className="text-[10.5px] text-[#6B6B73]">{fmtDate(en.valid_from)} – {fmtDate(en.valid_until)}</span>
                  <div className="flex items-center justify-end gap-1">
                    {canManage && (
                      <>
                        <button data-testid={`edit-price-${en.id}`} onClick={() => openEdit(en)} className="icon-button" title="Ubah"><Pencil size={13} /></button>
                        {en.status === "active" && (
                          <button data-testid={`deactivate-price-${en.id}`} onClick={() => handleDeactivate(en)} className="icon-button text-red-400 hover:text-red-600" title="Nonaktifkan"><Power size={13} /></button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={!!deactivateTarget}
        title={`Nonaktifkan harga ${deactivateTarget?.sku || ""}`}
        message="Entri harga ini tidak akan dipakai untuk auto-isi harga PO/PR. Bisa diaktifkan kembali nanti."
        confirmLabel="Nonaktifkan"
        danger
        onConfirm={() => doDeactivate(deactivateTarget)}
        onCancel={() => setDeactivateTarget(null)}
        testId="pricelist-deactivate-modal"
      />
    </div>
  );
}
