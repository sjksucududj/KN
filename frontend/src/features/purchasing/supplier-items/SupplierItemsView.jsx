/**
 * SupplierItemsView (FASE E · E-01/E-02/E-03)
 * Master **Barang Supplier** (`supplier_items`): peta KODE & NAMA versi supplier ↔ SKU KN,
 * konversi satuan supplier → satuan dasar KN, harga terakhir, MOQ, lead time & grade.
 * Termasuk **impor massal** CSV/XLSX dan **pencarian barang KN dari kode supplier**.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { PackageSearch, Pencil, Plus, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import KNSelect from "../../../components/KNSelect";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import SupplierItemFormModal from "./SupplierItemFormModal";
import SupplierItemImportModal from "./SupplierItemImportModal";
import {
  deleteSupplierItem, listSupplierItems, lookupSupplierSku, supplierItemStats,
} from "./supplierItemsApi";

export default function SupplierItemsView({ currentUser, selectedEntity }) {
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState({});
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [q, setQ] = useState("");
  const [supplierFilter, setSupplierFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [lookupSku, setLookupSku] = useState("");
  const [lookupResult, setLookupResult] = useState(null);

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 300 };
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      if (supplierFilter) params.supplier_id = supplierFilter;
      const [list, st] = await Promise.all([
        listSupplierItems(params),
        supplierItemStats(params.entity_id ? { entity_id: params.entity_id } : {}).catch(() => ({})),
      ]);
      setRows(Array.isArray(list) ? list : (list?.items || []));
      setStats(st || {});
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Barang Supplier.");
    } finally { setLoading(false); }
  }, [selectedEntity, supplierFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    (async () => {
      const [s, p] = await Promise.all([
        axios.get(`${API}/suppliers`).catch(() => ({ data: [] })),
        axios.get(`${API}/products`).catch(() => ({ data: [] })),
      ]);
      setSuppliers(Array.isArray(s.data) ? s.data : (s.data?.items || []));
      setProducts(Array.isArray(p.data) ? p.data : (p.data?.items || []));
    })();
  }, []);

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 4000); }

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((r) => [r.supplier_sku, r.supplier_item_name, r.sku, r.product_name, r.barcode]
      .some((v) => (v || "").toLowerCase().includes(term)));
  }, [rows, q]);

  async function doLookup() {
    if (!lookupSku.trim()) return;
    setLookupResult(null);
    try {
      const res = await lookupSupplierSku({
        supplier_sku: lookupSku.trim(),
        ...(supplierFilter ? { supplier_id: supplierFilter } : {}),
        ...(selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}),
      });
      setLookupResult({ ok: true, item: res.item });
    } catch (e) {
      setLookupResult({ ok: false, message: e.response?.data?.detail || "Kode supplier tidak ditemukan." });
    }
  }

  async function remove(row) {
    try {
      await deleteSupplierItem(row.id);
      flash(`${row.supplier_sku} dihapus.`);
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Barang supplier tidak bisa dihapus.");
    }
  }

  return (
    <div data-testid="supplier-items-view" className="grid gap-4">
      {toast && (
        <div className="notice-bar success" data-testid="supplier-items-toast">
          <span>{toast}</span><button onClick={() => setToast("")}>×</button>
        </div>
      )}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="supplier-items-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <PackageSearch size={15} className="text-[#0058CC]" />
            <h2>Barang Supplier</h2>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="supplier-items-refresh" className="btn-secondary btn-xs" onClick={load}>
              <RefreshCw size={13} /> Muat ulang
            </button>
            {canManage && (
              <>
                <button data-testid="supplier-items-import" className="btn-secondary btn-xs"
                  onClick={() => setShowImport(true)}>
                  <Upload size={13} /> Impor Massal
                </button>
                <button data-testid="supplier-items-create" className="btn-primary"
                  onClick={() => { setEditing(null); setShowForm(true); }}>
                  <Plus size={14} /> Barang Baru
                </button>
              </>
            )}
          </div>
        </div>

        <div className="section-body grid gap-3">
          <p className="text-[11.5px] text-[#6B6B73]">
            Supplier menyebut barang dengan kode & nama sendiri. Peta ini membuat PO dan
            penerimaan barang memakai <b>nama KN</b> dan <b>nama supplier</b> berdampingan —
            termasuk konversi satuan supplier ke satuan dasar KN.
          </p>

          <div className="grid gap-2 sm:grid-cols-4">
            {[
              ["Total Barang", stats.total ?? 0, "supplier-items-kpi-total"],
              ["Aktif", stats.active ?? 0, "supplier-items-kpi-active"],
              ["Supplier Terpeta", stats.suppliers ?? 0, "supplier-items-kpi-suppliers"],
              ["Produk Terpeta", stats.mapped_products ?? 0, "supplier-items-kpi-products"],
            ].map(([label, value, tid]) => (
              <div key={tid} className="metric-card">
                <span className="text-[10px] font-bold uppercase text-[#6B6B73]">{label}</span>
                <b data-testid={tid} className="text-[18px] tabular-nums">{value}</b>
              </div>
            ))}
          </div>

          {/* Cari barang KN dari kode supplier */}
          <div className="rounded-lg border border-[#E5F0FF] bg-[#F5F9FF] px-3 py-2.5 grid gap-2">
            <span className="text-[10px] font-bold uppercase text-[#0058CC]">
              Cari Barang KN dari Kode Supplier
            </span>
            <div className="flex flex-wrap gap-2">
              <input data-testid="supplier-items-lookup-input" className="form-input flex-1 min-w-[180px]"
                value={lookupSku} onChange={(e) => setLookupSku(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") doLookup(); }}
                placeholder="Ketik kode supplier, mis. TX-COT-30S" />
              <button data-testid="supplier-items-lookup-button" className="btn-secondary"
                onClick={doLookup} disabled={!lookupSku.trim()}>
                <Search size={14} /> Cari
              </button>
            </div>
            {lookupResult?.ok && (
              <p data-testid="supplier-items-lookup-hit" className="text-[11.5px] text-[#1B7F4B]">
                <b>{lookupResult.item.supplier_sku}</b> ({lookupResult.item.supplier_item_name || "—"}) →{" "}
                <b>{lookupResult.item.sku}</b> {lookupResult.item.product_name} · 1{" "}
                {lookupResult.item.supplier_uom} = {formatQty(lookupResult.item.conv_factor)}{" "}
                {lookupResult.item.base_unit}
              </p>
            )}
            {lookupResult && !lookupResult.ok && (
              <p data-testid="supplier-items-lookup-miss" className="text-[11.5px] text-[#C0392B]">
                {lookupResult.message}
              </p>
            )}
          </div>

          {/* Filter */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex-1 min-w-[180px]">
              <input data-testid="supplier-items-search" className="form-input" value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Cari kode / nama supplier / SKU KN…" />
            </div>
            <div className="min-w-[200px]">
              <KNSelect data-testid="supplier-items-supplier-filter" className="form-input"
                value={supplierFilter} onValueChange={setSupplierFilter}
                placeholder="— Semua supplier —"
                options={[{ value: "", label: "Semua supplier" },
                  ...suppliers.map((s) => ({ value: s.id, label: s.name }))]} />
            </div>
          </div>

          {/* Tabel */}
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1.1fr_1.3fr_1.3fr_130px_120px_90px_80px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
              <span>Kode Supplier</span><span>Nama Supplier</span><span>Produk KN</span>
              <span className="text-right">Konversi</span><span className="text-right">Harga Terakhir</span>
              <span className="text-center">Status</span><span className="text-right">Aksi</span>
            </div>
            {loading && (
              <div data-testid="supplier-items-loading" className="px-3 py-6 text-center text-[12px] text-[#9A9BA3]">
                Memuat data…
              </div>
            )}
            {!loading && filtered.map((r) => (
              <div key={r.id} data-testid={`supplier-item-row-${r.id}`}
                className="grid grid-cols-[1.1fr_1.3fr_1.3fr_130px_120px_90px_80px] items-center px-3 py-2 border-t border-[#F4F5F7]">
                <div className="min-w-0">
                  <p className="text-[12px] font-bold truncate">{r.supplier_sku}</p>
                  <p className="text-[10px] text-[#9A9BA3] truncate">{r.supplier_name}</p>
                </div>
                <p className="text-[11.5px] truncate">{r.supplier_item_name || "—"}</p>
                <div className="min-w-0">
                  <p className="text-[11.5px] font-semibold truncate">{r.product_name}</p>
                  <p className="text-[10px] text-[#9A9BA3]">{r.sku}</p>
                </div>
                <span className="text-[11px] tabular-nums text-right">
                  1 {r.supplier_uom} = {formatQty(r.conv_factor)} {r.base_unit}
                </span>
                <span className="text-[11.5px] tabular-nums text-right font-semibold">
                  {formatCurrency(r.last_price)}
                </span>
                <span className="text-center">
                  <span className={`status-pill ${r.status === "active" ? "pill-success" : "pill-muted"}`}>
                    {r.status === "active" ? "Aktif" : "Nonaktif"}
                  </span>
                </span>
                <div className="flex justify-end gap-1">
                  {canManage && (
                    <>
                      <button data-testid={`supplier-item-edit-${r.id}`} className="icon-button"
                        onClick={() => { setEditing(r); setShowForm(true); }}>
                        <Pencil size={13} />
                      </button>
                      <button data-testid={`supplier-item-delete-${r.id}`} className="icon-button text-red-500"
                        onClick={() => remove(r)}>
                        <Trash2 size={13} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
            {!loading && filtered.length === 0 && (
              <div data-testid="supplier-items-empty" className="px-3 py-8 text-center text-[12px] text-[#9A9BA3]">
                Belum ada Barang Supplier. Tambah manual atau pakai <b>Impor Massal</b> agar
                PO & penerimaan bisa memakai kode/nama versi supplier.
              </div>
            )}
          </div>
        </div>
      </section>

      {showForm && (
        <SupplierItemFormModal editing={editing} suppliers={suppliers} products={products}
          selectedEntity={selectedEntity}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={(saved) => {
            setShowForm(false); setEditing(null);
            flash(`${saved.supplier_sku} disimpan.`); load();
          }} />
      )}

      {showImport && (
        <SupplierItemImportModal suppliers={suppliers} selectedEntity={selectedEntity}
          onClose={() => setShowImport(false)}
          onDone={(res) => {
            flash(`Impor selesai: +${res.created || 0} baru · ${res.updated || 0} diperbarui.`);
            load();
          }} />
      )}
    </div>
  );
}
