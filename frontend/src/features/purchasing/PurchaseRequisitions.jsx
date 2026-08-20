import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  ClipboardList, Plus, ArrowLeft, Trash2, CheckCircle2, XCircle, Send,
  ShoppingCart, RefreshCw, AlertTriangle, Ban,
} from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import LineFilter from "../../components/LineFilter";   // FASE L
import { SOURCE_LABEL, StatusPill } from "./prConstants";
import { GroupEntityNotice, isGroupEntityPartner, supplierOptionLabel }
  from "../../components/GroupEntityBadge";
import { FULFILLMENT_OPTIONS } from "./supplier-items/supplierItemsApi";
import DetailPanel from "./PurchaseRequisitionDetailPanel";

/**
 * Purchase Requisitions (Depth #2a) — Hulu procurement.
 * PR → approval (matriks 'purchase_requisition') → konversi ke PO.
 * Sumber: manual | reorder | special_order.
 */

export default function PurchaseRequisitions({ currentUser, selectedEntity = "all" }) {
  const [view, setView] = useState("list");            // list | create | detail
  const [items, setItems] = useState([]);
  const [byStatus, setByStatus] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState(null);

  // master data
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [suppliers, setSuppliers] = useState([]);

  const role = currentUser?.role;
  const canApprove = role === "admin" || role === "manager";

  useEffect(() => { loadMasters(); }, []);             // eslint-disable-line
  const [lineFilter, setLineFilter] = useState("");   // FASE L
  useEffect(() => { load(); }, [statusFilter, selectedEntity, lineFilter]); // eslint-disable-line

  async function loadMasters() {
    try {
      const [p, w, s] = await Promise.all([
        axios.get(`${API}/products`).catch(() => ({ data: [] })),
        axios.get(`${API}/warehouses`).catch(() => ({ data: [] })),
        axios.get(`${API}/suppliers`).catch(() => ({ data: [] })),
      ]);
      setProducts(Array.isArray(p.data) ? p.data : (p.data?.items || []));
      setWarehouses(Array.isArray(w.data) ? w.data : (w.data?.items || []));
      setSuppliers(Array.isArray(s.data) ? s.data : (s.data?.items || []));
    } catch (e) { /* non-blocking */ }
  }

  async function load() {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      if (lineFilter) params.line = lineFilter;          // FASE L — disaring di server
      const res = await axios.get(`${API}/purchase-requisitions`, { params });
      setItems(res.data?.items || []);
      setByStatus(res.data?.by_status || {});
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Purchase Requisition.");
    } finally {
      setLoading(false);
    }
  }

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 3500); }

  async function openDetail(id) {
    try {
      const res = await axios.get(`${API}/purchase-requisitions/${id}`);
      setSelected(res.data); setView("detail");
    } catch (e) { flash(e.response?.data?.detail || "Gagal memuat detail PR."); }
  }

  const tabs = [
    { key: "", label: "Semua" },
    { key: "draft", label: "Draf" },
    { key: "pending_approval", label: "Menunggu Persetujuan" },
    { key: "approved", label: "Disetujui" },
    { key: "converted", label: "Jadi PO" },
    { key: "rejected", label: "Ditolak" },
  ];

  if (view === "create") {
    return (
      <CreateForm
        products={products} warehouses={warehouses} suppliers={suppliers}
        selectedEntity={selectedEntity}
        onCancel={() => setView("list")}
        onCreated={(pr) => { flash(`${pr.number} dibuat.`); setView("list"); load(); }}
      />
    );
  }

  if (view === "detail" && selected) {
    return (
      <DetailPanel
        pr={selected} canApprove={canApprove} suppliers={suppliers} warehouses={warehouses}
        onBack={() => { setSelected(null); setView("list"); load(); }}
        onChanged={(msg) => { flash(msg); }}
        reload={openDetail}
      />
    );
  }

  return (
    <div data-testid="purchase-requisitions-view" className="grid gap-4">
      {toast && <div className="notice-bar success" data-testid="pr-toast"><span>{toast}</span><button onClick={() => setToast("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="pr-error" />

      {/* Header */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <ClipboardList size={15} className="text-[#0058CC]" />
            <span className="kicker">Pembelian</span>
            <h2 data-testid="pr-title">Permintaan Pembelian (PR)</h2>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="pr-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
            <button data-testid="pr-create-btn" className="btn-primary" onClick={() => setView("create")}>
              <Plus size={14} /> PR Baru
            </button>
          </div>
        </div>

        {/* Metrics */}
        <section data-testid="pr-metrics" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 p-3">
          <Metric label="Total PR" value={items.length} tone="rgba(0,122,255,.12)" testId="pr-metric-total" />
          <Metric label="Menunggu Persetujuan" value={byStatus.pending_approval || 0} tone="rgba(255,149,0,.16)" testId="pr-metric-pending" />
          <Metric label="Disetujui" value={byStatus.approved || 0} tone="rgba(52,199,89,.15)" testId="pr-metric-approved" />
          <Metric label="Jadi PO" value={byStatus.converted || 0} tone="rgba(0,122,255,.10)" testId="pr-metric-converted" />
        </section>

        <div className="px-3 pb-2">
          <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="purchase-requisitions"
                      allowed={currentUser?.allowed_line_codes} testId="pr-line-filter" />
        </div>

        {/* Tabs */}
        <div className="flex flex-wrap gap-1.5 px-3 pb-3">
          {tabs.map((t) => (
            <button
              key={t.key || "all"}
              data-testid={`pr-tab-${t.key || "all"}`}
              className={`tab-button ${statusFilter === t.key ? "active" : ""}`}
              onClick={() => setStatusFilter(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </section>

      {/* List */}
      <section className="section-card">
        <div className="overflow-x-auto">
          <div className="grid grid-cols-[90px_1.4fr_110px_130px_120px_140px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Nomor</span><span>Item</span><span>Sumber</span><span className="text-right">Estimasi</span><span>Status</span><span className="text-right">Aksi</span>
          </div>
          {loading ? (
            <div data-testid="pr-loading" className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
          ) : items.length === 0 ? (
            <div data-testid="pr-empty" className="py-12 text-center text-[12px] text-[#6B6B73]">
              Belum ada Permintaan Pembelian. Klik <b>PR Baru</b> untuk membuat.
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2]">
              {items.map((pr) => (
                <div key={pr.id} data-testid={`pr-row-${pr.id}`} className="grid grid-cols-[90px_1.4fr_110px_130px_120px_140px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <span className="text-[11.5px] font-bold text-[#0058CC]">{pr.number}</span>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold truncate">{pr.items?.[0]?.product_name || "-"}{pr.items?.length > 1 ? ` +${pr.items.length - 1}` : ""}</p>
                    <p className="text-[10.5px] text-[#9A9BA3]">{pr.warehouse_name || "—"}</p>
                  </div>
                  <span className="status-pill pill-muted">{SOURCE_LABEL[pr.source] || pr.source}</span>
                  <span className="text-[12px] tabular-nums text-right font-semibold">{formatCurrency(pr.total_est_amount)}</span>
                  <StatusPill status={pr.status} />
                  <div className="text-right">
                    <button data-testid={`pr-open-${pr.id}`} className="btn-secondary btn-xs" onClick={() => openDetail(pr.id)}>Detail</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value, tone, testId }) {
  return (
    <div data-testid={testId} className="metric-card">
      <div className="metric-icon" style={{ background: tone }}><ClipboardList size={16} className="text-[#1C1C1E]" /></div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
        <p className="text-[17px] font-bold tabular-nums">{value}</p>
      </div>
    </div>
  );
}

// ─── Create Form ─────────────────────────────────────────────────────────────
function CreateForm({ products, warehouses, suppliers, selectedEntity, onCancel, onCreated }) {
  const [lines, setLines] = useState([]);
  const [warehouseId, setWarehouseId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [reason, setReason] = useState("");
  const [neededBy, setNeededBy] = useState("");
  const [submitNow, setSubmitNow] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pickProduct, setPickProduct] = useState("");

  const total = useMemo(() => lines.reduce((s, l) => s + (Number(l.est_price) || 0) * (Number(l.quantity) || 0), 0), [lines]);
  // FASE E-7 (E7.2) — pemasok terpilih dipakai untuk lencana + mematikan tombol Simpan.
  const selectedSupplier = useMemo(
    () => suppliers.find((s) => s.id === supplierId) || null, [suppliers, supplierId]);
  const supplierIsGroupEntity = isGroupEntityPartner(selectedSupplier);

  function addLine() {
    const p = products.find((x) => x.id === pickProduct);
    if (!p) return;
    if (lines.some((l) => l.product_id === p.id)) { setErr("Produk sudah ditambahkan."); return; }
    setLines([...lines, {
      product_id: p.id, sku: p.sku, product_name: p.name,
      quantity: p.reorder_qty || 100, unit: p.base_unit || "meter",
      est_price: p.harga_pokok || p.price || 0,
      fulfillment_mode: "purchase",
    }]);
    setPickProduct(""); setErr("");
  }
  function updLine(i, k, v) { setLines(lines.map((l, idx) => idx === i ? { ...l, [k]: v } : l)); }
  function rmLine(i) { setLines(lines.filter((_, idx) => idx !== i)); }

  async function submit() {
    if (lines.length === 0) { setErr("Tambahkan minimal satu item."); return; }
    if (!warehouseId) { setErr("Pilih gudang tujuan."); return; }
    setBusy(true); setErr("");
    try {
      const payload = {
        items: lines.map((l) => ({ product_id: l.product_id, quantity: Number(l.quantity), unit: l.unit, est_price: Number(l.est_price), fulfillment_mode: l.fulfillment_mode || "purchase" })),
        warehouse_id: warehouseId,
        entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "",
        preferred_supplier_id: supplierId,
        reason, needed_by_date: neededBy, source: "manual", submit_now: submitNow,
      };
      const res = await axios.post(`${API}/purchase-requisitions`, payload);
      onCreated(res.data);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal membuat PR.");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="pr-create-form" className="grid gap-4">
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <button className="icon-button" onClick={onCancel}><ArrowLeft size={15} /></button>
            <h2>Buat Permintaan Pembelian</h2>
          </div>
        </div>
        <div className="section-body grid gap-3">
          {err && <div className="notice-bar danger" data-testid="pr-form-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}

          {/* Item picker */}
          <div className="grid gap-1.5">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Tambah Item</label>
            <div className="flex gap-2">
              <KNSelect
                data-testid="pr-product-select"
                className="form-input flex-1"
                value={pickProduct}
                onValueChange={setPickProduct}
                placeholder="— Pilih produk —"
                options={products.filter((p) => p.status !== "inactive").map((p) => ({ value: p.id, label: `${p.sku} · ${p.name}` }))}
              />
              <button data-testid="pr-add-line" className="btn-secondary" onClick={addLine} disabled={!pickProduct}><Plus size={14} /> Tambah</button>
            </div>
          </div>

          {/* Lines */}
          {lines.length > 0 && (
            <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
              <div className="grid grid-cols-[1.3fr_150px_100px_120px_110px_40px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
                <span>Produk</span><span>Pemenuhan</span><span className="text-right">Qty</span><span className="text-right">Est. Harga</span><span className="text-right">Subtotal</span><span></span>
              </div>
              {lines.map((l, i) => (
                <div key={i} data-testid={`pr-line-${i}`} className="grid grid-cols-[1.3fr_150px_100px_120px_110px_40px] items-center gap-1 px-3 py-2 border-t border-[#F4F5F7]">
                  <div className="min-w-0"><p className="text-[12px] font-semibold truncate">{l.product_name}</p><p className="text-[10px] text-[#9A9BA3]">{l.sku} · {l.unit}</p></div>
                  <KNSelect data-testid={`pr-mode-${i}`} className="form-input"
                    value={l.fulfillment_mode || "purchase"}
                    onValueChange={(v) => updLine(i, "fulfillment_mode", v)}
                    options={FULFILLMENT_OPTIONS} />
                  <input type="number" data-testid={`pr-qty-${i}`} className="form-input text-right" value={l.quantity} onChange={(e) => updLine(i, "quantity", e.target.value)} />
                  <input type="number" data-testid={`pr-price-${i}`} className="form-input text-right" value={l.est_price} onChange={(e) => updLine(i, "est_price", e.target.value)} />
                  <span className="text-[12px] tabular-nums text-right font-semibold">{formatCurrency((Number(l.est_price) || 0) * (Number(l.quantity) || 0))}</span>
                  <button className="icon-button text-red-500" onClick={() => rmLine(i)}><Trash2 size={14} /></button>
                </div>
              ))}
              <div className="flex justify-between items-center px-3 py-2 border-t border-[#EFF0F2] bg-[#FAFBFC]">
                <span className="text-[11px] font-bold uppercase text-[#6B6B73]">Total Estimasi</span>
                <span data-testid="pr-form-total" className="text-[15px] font-bold tabular-nums text-[#0058CC]">{formatCurrency(total)}</span>
              </div>
            </div>
          )}
          {lines.some((l) => l.fulfillment_mode === "makloon") && (
            <p data-testid="pr-makloon-note" className="text-[11.5px] text-[#8C4A00] bg-[#FFF8EE] border border-[#FFE2B8] rounded-md px-3 py-2">
              Baris ber-mode <b>Proses via Makloon</b> tidak masuk PO. Setelah PR disetujui,
              buka detail PR → panel <b>Pemenuhan & Realisasi</b> → tombol
              <b> Buat Order Makloon</b> (bahan, mitra & qty terisi otomatis dari Resep Proses).
            </p>
          )}

          {/* Fields */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Gudang Tujuan *</label>
              <KNSelect
                data-testid="pr-warehouse"
                className="form-input"
                value={warehouseId}
                onValueChange={setWarehouseId}
                placeholder="— Pilih gudang —"
                options={warehouses.map((w) => ({ value: w.id, label: w.name }))}
              />
            </div>
            <div className="grid gap-1.5">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Supplier Preferensi</label>
              <KNSelect
                data-testid="pr-supplier"
                className="form-input"
                value={supplierId}
                onValueChange={setSupplierId}
                placeholder="— Opsional —"
                options={suppliers.map((s) => ({ value: s.id, label: supplierOptionLabel(s) }))}
              />
              {/* FASE E-7 (E7.2) — pagar dipasang SEJAK di hulu: PR yang menunjuk badan
                  usaha grup akan ditolak saat realisasi ke PO, jadi lebih baik dijelaskan
                  sekarang daripada setelah lewat persetujuan. */}
              {isGroupEntityPartner(selectedSupplier) && (
                <GroupEntityNotice partner={selectedSupplier} docLabel="Permintaan Pembelian (PR) biasa" />
              )}
            </div>
            <div className="grid gap-1.5">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Dibutuhkan Sebelum</label>
              <input type="date" data-testid="pr-needed-by" className="form-input" value={neededBy} onChange={(e) => setNeededBy(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Alasan / Justifikasi</label>
              <input data-testid="pr-reason" className="form-input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Restock produksi…" />
            </div>
          </div>

          <label className="flex items-center gap-2 text-[12px]">
            <input type="checkbox" data-testid="pr-submit-now" checked={submitNow} onChange={(e) => setSubmitNow(e.target.checked)} />
            Langsung ajukan persetujuan (jika di bawah ambang, otomatis disetujui)
          </label>

          <div className="flex justify-end gap-2 pt-1">
            <button className="btn-secondary" onClick={onCancel}>Batal</button>
            <button data-testid="pr-submit" className="btn-primary" onClick={submit}
              disabled={busy || supplierIsGroupEntity}
              title={supplierIsGroupEntity
                ? `${selectedSupplier?.name} adalah badan usaha di dalam grup — pakai menu Antar Entitas`
                : ""}>
              {supplierIsGroupEntity ? "Pakai menu Antar Entitas" : busy ? "Menyimpan…" : "Simpan PR"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

