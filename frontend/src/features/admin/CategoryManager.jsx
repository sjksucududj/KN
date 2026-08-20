/**
 * CategoryManager — EPIC2 Master Kategori Produk (admin).
 * CRUD kategori produk: list (dengan product_count) + form create/edit + soft-delete.
 * Self-contained: fetch & mutasi via axios + API (path literal). Memanggil `onChanged`
 * setelah mutasi agar form produk (AdminView) refresh opsi dropdown.
 */
import { useCallback, useEffect, useState } from "react";
import { Save, Trash2, Pencil, Plus, RefreshCw, Tag, XCircle } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import useUomConversions from "../../hooks/useUomConversions";
import { uomSelectOptions } from "../../utils/uomCatalog";
import { askConfirm } from "@/services/confirmService";

const EMPTY = { code: "", name: "", base_unit: "meter", description: "", sort_order: 0, status: "active" };

export default function CategoryManager({ onChanged }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  // FASE U — satuan dasar kategori dari MASTER satuan (`uoms`). Dulu 5 nilai diketik
  // di berkas ini: kategori produk yang dijual per `panel` tidak bisa dibuat sama
  // sekali walau pemilik sudah menambah PANEL di Master Data → UOM.
  useUomConversions();
  const baseUnitOptions = uomSelectOptions({
    dimensions: ["length", "weight", "count"],
    extra: [form.base_unit].filter(Boolean),
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/product-categories`);
      setRows(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat kategori. Coba lagi.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const resetForm = () => { setForm(EMPTY); setEditingId(null); setFormError(""); };

  const startEdit = (row) => {
    setEditingId(row.id);
    setForm({
      code: row.code || "", name: row.name || "", base_unit: row.base_unit || "meter",
      description: row.description || "", sort_order: row.sort_order || 0, status: row.status || "active",
    });
    setFormError("");
  };

  const save = async () => {
    if (!form.name.trim()) { setFormError("Nama kategori wajib diisi."); return; }
    setSaving(true);
    setFormError("");
    try {
      if (editingId) {
        await axios.patch(`${API}/product-categories/${editingId}`, { data: form });
      } else {
        await axios.post(`${API}/product-categories`, form);
      }
      resetForm();
      await load();
      if (onChanged) onChanged();
    } catch (e) {
      setFormError(e.response?.data?.detail || "Gagal menyimpan kategori.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row) => {
    const ok = await askConfirm({
      title: `Nonaktifkan kategori "${row.name}"?`,
      message: "Kategori tidak lagi bisa dipilih untuk produk baru. Produk yang sudah memakainya tetap utuh.",
      confirmLabel: "Nonaktifkan",
      danger: true,
      testId: "category-deactivate-confirm",
    });
    if (!ok) return;
    try {
      await axios.delete(`${API}/product-categories/${row.id}`);
      await load();
      if (onChanged) onChanged();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menonaktifkan kategori.");
    }
  };

  const activeRows = rows;

  return (
    <section className="grid gap-3 lg:grid-cols-[360px_1fr]" data-testid="category-manager">
      {/* ─── Form ─── */}
      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Tag size={15} className="text-[#6B219A]" />
            <h2>{editingId ? "Edit Kategori" : "Kategori Baru"}</h2>
          </div>
          {editingId && (
            <button data-testid="category-cancel-edit-button" className="icon-button ml-auto" onClick={resetForm} aria-label="Batal ubah">
              <XCircle size={14} />
            </button>
          )}
        </div>
        <div className="section-body grid gap-2">
          <label className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Nama kategori *</label>
          <input data-testid="category-name-input" className="field" placeholder="mis. Batik"
            value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />

          <label className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Kode (opsional)</label>
          <input data-testid="category-code-input" className="field" placeholder="auto dari nama (BATIK)"
            value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />

          <label className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Base unit default</label>
          <KNSelect data-testid="category-base-unit-input" className="field" value={form.base_unit}
            onValueChange={(v) => setForm({ ...form, base_unit: v })} options={baseUnitOptions} />

          <label className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Deskripsi</label>
          <input data-testid="category-description-input" className="field" placeholder="Deskripsi singkat"
            value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Urutan</label>
              <input data-testid="category-sort-order-input" className="field" type="number"
                value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })} />
            </div>
            <div>
              <label className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Status</label>
              <KNSelect data-testid="category-status-input" className="field" value={form.status}
                onValueChange={(v) => setForm({ ...form, status: v })}
                options={[{ value: "active", label: "Aktif" }, { value: "inactive", label: "Nonaktif" }]} />
            </div>
          </div>

          {formError && <p data-testid="category-form-error" className="text-[12px] font-semibold text-[#D14343]">{formError}</p>}

          <div className="flex gap-2 mt-1">
            <button data-testid="category-save-button" className="primary-button" onClick={save} disabled={saving}>
              <Save size={14} /> {saving ? "Menyimpan..." : editingId ? "Update Kategori" : "Simpan Kategori"}
            </button>
            {editingId && (
              <button data-testid="category-cancel-edit-button-2" className="secondary-button" onClick={resetForm}>Batal</button>
            )}
          </div>
        </div>
      </div>

      {/* ─── List ─── */}
      <div className="section-card">
        <div className="section-head">
          <h2>Daftar Kategori {rows.length > 0 ? `(${rows.length})` : ""}</h2>
          <button data-testid="category-refresh-button" className="icon-button ml-auto" onClick={load} aria-label="Refresh">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="category-list-error" />

          {loading ? (
            <div className="grid gap-2" data-testid="category-loading">
              {[0, 1, 2, 3].map((i) => <div key={i} className="h-10 bg-[#F5F5F7] rounded animate-pulse" />)}
            </div>
          ) : activeRows.length === 0 ? (
            <div data-testid="category-empty" className="flex flex-col items-center justify-center gap-2 py-10 text-center">
              <Tag size={28} className="text-[#C7C7CC]" />
              <p className="text-[13px] text-[#8E8E93]">Belum ada kategori. Tambahkan kategori pertama Anda.</p>
              <button className="secondary-button" data-testid="category-empty-add-button" onClick={() => setForm({ ...EMPTY })}>
                <Plus size={14} /> Buat Kategori
              </button>
            </div>
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-[12.5px]" data-testid="category-table">
                <thead>
                  <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] border-b border-[#EFF0F2]">
                    <th className="py-2">Kode</th>
                    <th className="py-2">Nama</th>
                    <th className="py-2">Base Unit</th>
                    <th className="py-2 text-right">Produk</th>
                    <th className="py-2 text-center">Status</th>
                    <th className="py-2 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody>
                  {activeRows.map((row) => (
                    <tr key={row.id} data-testid={`category-row-${row.id}`} className="border-b border-[#F5F5F7] last:border-0">
                      <td className="py-2 font-mono text-[11px] text-[#6B6B73]">{row.code}</td>
                      <td className="py-2 font-semibold text-[#1C1C1E]">{row.name}</td>
                      <td className="py-2 text-[#3C3C43]">{row.base_unit}</td>
                      <td className="py-2 text-right tabular-nums" data-testid={`category-count-${row.id}`}>{row.product_count ?? 0}</td>
                      <td className="py-2 text-center">
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${row.status === "active" ? "text-[#1B7F4B] bg-[#E6F6EC]" : "text-[#8E8E93] bg-[#F0F0F2]"}`}>
                          {row.status === "active" ? "Aktif" : "Nonaktif"}
                        </span>
                      </td>
                      <td className="py-2">
                        <div className="flex items-center justify-end gap-1">
                          <button data-testid={`category-edit-${row.id}`} className="icon-button" onClick={() => startEdit(row)} aria-label={`Ubah ${row.name}`}>
                            <Pencil size={13} />
                          </button>
                          <button data-testid={`category-delete-${row.id}`} className="icon-button" onClick={() => remove(row)} aria-label={`Hapus ${row.name}`}>
                            <Trash2 size={13} className="text-[#D14343]" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
