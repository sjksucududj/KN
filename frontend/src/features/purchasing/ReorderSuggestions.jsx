import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  Target, RefreshCw, ShoppingCart, AlertTriangle, TrendingDown, Save, CheckCircle2, Clock,
} from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";

function fmtEta(d) {
  if (!d) return "";
  try { return new Date(d).toLocaleDateString("id-ID", { day: "2-digit", month: "short" }); }
  catch { return d; }
}

/**
 * Reorder Suggestions / Replenishment (Depth #2b).
 * Saran beli untuk produk dengan proyeksi stok (available + on_order) <= reorder_point.
 * on_order diperhitungkan untuk mencegah double-order. Bisa langsung buat PR (source=reorder).
 */
export default function ReorderSuggestions({ currentUser, selectedEntity = "all" }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [checked, setChecked] = useState({});       // product_id -> bool
  const [editQty, setEditQty] = useState({});       // product_id -> suggested override
  const [warehouses, setWarehouses] = useState([]);
  const [warehouseId, setWarehouseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);     // product_id being edited (reorder point)
  const [rp, setRp] = useState({});                 // product_id -> {reorder_point, reorder_qty}

  useEffect(() => { loadWarehouses(); }, []);        // eslint-disable-line
  useEffect(() => { load(); }, [selectedEntity]);    // eslint-disable-line

  async function loadWarehouses() {
    try {
      const w = await axios.get(`${API}/warehouses`);
      const list = Array.isArray(w.data) ? w.data : (w.data?.items || []);
      setWarehouses(list);
      if (list[0]) setWarehouseId(list[0].id);
    } catch (e) { /* ignore */ }
  }

  async function load() {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const res = await axios.get(`${API}/purchase-requisitions/reorder-suggestions`, { params });
      const items = res.data?.items || [];
      setRows(items);
      const eq = {}; items.forEach((r) => { eq[r.product_id] = r.suggested_qty; });
      setEditQty(eq);
      setChecked({});
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat saran reorder.");
    } finally { setLoading(false); }
  }

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 3500); }

  const selectedRows = useMemo(() => rows.filter((r) => checked[r.product_id]), [rows, checked]);
  const selectedTotal = useMemo(
    () => selectedRows.reduce((s, r) => s + (Number(editQty[r.product_id]) || 0) * (r.est_price || 0), 0),
    [selectedRows, editQty]
  );

  function toggleAll() {
    if (selectedRows.length === rows.length) setChecked({});
    else { const all = {}; rows.forEach((r) => { all[r.product_id] = true; }); setChecked(all); }
  }

  async function createPR() {
    if (selectedRows.length === 0) { flash("Pilih minimal satu produk."); return; }
    if (!warehouseId) { flash("Pilih gudang tujuan."); return; }
    setBusy(true);
    try {
      // needed_by_date = ETA terjauh di antara item terpilih (lead-time supplier).
      const etas = selectedRows.map((r) => r.expected_arrival_date).filter(Boolean).sort();
      const neededBy = etas.length ? etas[etas.length - 1] : "";
      // preferred_supplier_id bila semua item terpilih dari supplier yang sama.
      const supIds = [...new Set(selectedRows.map((r) => r.preferred_supplier_id).filter(Boolean))];
      const payload = {
        items: selectedRows.map((r) => ({
          product_id: r.product_id, quantity: Number(editQty[r.product_id]) || r.suggested_qty,
          unit: r.unit, est_price: r.est_price,
        })),
        warehouse_id: warehouseId,
        entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "",
        needed_by_date: neededBy,
        preferred_supplier_id: supIds.length === 1 ? supIds[0] : "",
        source: "reorder", reason: "Replenishment otomatis (di bawah reorder point)",
        submit_now: true,
      };
      const res = await axios.post(`${API}/purchase-requisitions`, payload);
      flash(`${res.data.number} dibuat (${selectedRows.length} item). Lihat di menu Purchase Requisition.`);
      load();
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal membuat PR.");
    } finally { setBusy(false); }
  }

  async function saveReorder(r) {
    const v = rp[r.product_id] || {};
    setBusy(true);
    try {
      await axios.patch(`${API}/products/${r.product_id}`, {
        data: {
          reorder_point: Number(v.reorder_point ?? r.reorder_point),
          reorder_qty: Number(v.reorder_qty ?? r.reorder_qty),
        },
      });
      flash(`Reorder point ${r.sku} diperbarui.`);
      setEditing(null);
      load();
    } catch (e) {
      flash(e.response?.data?.detail || "Gagal menyimpan reorder point.");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="reorder-suggestions-view" className="grid gap-4">
      {toast && <div className="notice-bar success" data-testid="reorder-toast"><span>{toast}</span><button onClick={() => setToast("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="reorder-error" />

      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <Target size={15} className="text-[#0058CC]" />
            <span className="kicker">Pembelian</span>
            <h2 data-testid="reorder-title">Saran Reorder · Replenishment</h2>
          </div>
          <button data-testid="reorder-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
        <p className="px-4 py-2 text-[12px] text-[#6B6B73]">
          Proyeksi = <b>Tersedia + Dalam Pesanan (PO terbuka) + Dalam Permintaan (PR terbuka)</b>. Produk muncul
          jika proyeksi ≤ reorder point. On-order & on-request diperhitungkan agar tidak
          <i> pesanan ganda / permintaan ganda</i> (PR ganda).
        </p>

        <section className="grid gap-3 sm:grid-cols-3 px-3 pb-3">
          <Metric icon={TrendingDown} label="Produk Perlu Restock" value={rows.length} tone="rgba(255,59,48,.12)" testId="reorder-metric-count" />
          <Metric icon={CheckCircle2} label="Dipilih" value={selectedRows.length} tone="rgba(0,122,255,.12)" testId="reorder-metric-selected" />
          <Metric icon={ShoppingCart} label="Estimasi Pilihan" value={formatCurrency(selectedTotal)} tone="rgba(52,199,89,.15)" testId="reorder-metric-total" />
        </section>
      </section>

      <section className="section-card">
        <div className="section-head">
          <h2 className="text-[13px] font-bold">Daftar Saran</h2>
          <div className="flex items-center gap-2">
            <div style={{ maxWidth: 200, minWidth: 160 }}>
              <KNSelect
                data-testid="reorder-warehouse"
                className="form-input"
                value={warehouseId}
                onValueChange={setWarehouseId}
                placeholder="— Gudang tujuan —"
                options={warehouses.map((w) => ({ value: w.id, label: w.name }))}
              />
            </div>
            <button data-testid="reorder-create-pr" className="btn-primary" onClick={createPR} disabled={busy || selectedRows.length === 0}>
              <ShoppingCart size={14} /> Buat PR dari Pilihan ({selectedRows.length})
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <div className="grid grid-cols-[28px_1.3fr_80px_80px_84px_84px_84px_92px_110px_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span><input type="checkbox" data-testid="reorder-check-all" checked={rows.length > 0 && selectedRows.length === rows.length} onChange={toggleAll} /></span>
            <span>Produk</span>
            <span className="text-right">Tersedia</span>
            <span className="text-right">Dalam Pesanan</span>
            <span className="text-right">Dalam Permintaan</span>
            <span className="text-right">Proyeksi</span>
            <span className="text-right">Reorder Pt</span>
            <span className="text-right">Saran Qty</span>
            <span>Lead / ETA</span>
            <span>Supplier</span>
          </div>

          {loading ? (
            <div data-testid="reorder-loading" className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
          ) : rows.length === 0 ? (
            <div data-testid="reorder-empty" className="flex flex-col items-center gap-2 py-12 text-center text-[12px] text-[#6B6B73]">
              <CheckCircle2 size={28} className="text-[#16A34A]" />
              <span>Semua stok di atas reorder point. Tidak ada saran replenishment.</span>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2]">
              {rows.map((r) => {
                const below = r.projected < r.reorder_point;
                const isEditing = editing === r.product_id;
                return (
                  <div key={r.product_id} data-testid={`reorder-row-${r.product_id}`} className="grid grid-cols-[28px_1.3fr_80px_80px_84px_84px_84px_92px_110px_120px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                    <span><input type="checkbox" data-testid={`reorder-check-${r.product_id}`} checked={!!checked[r.product_id]} onChange={() => setChecked({ ...checked, [r.product_id]: !checked[r.product_id] })} /></span>
                    <div className="min-w-0">
                      <p className="text-[10px] font-bold uppercase text-[#0058CC]">{r.sku}</p>
                      <p className="text-[12px] font-semibold truncate">{r.product_name}</p>
                      {Array.isArray(r.existing_prs) && r.existing_prs.length > 0 && (
                        <span
                          data-testid={`reorder-pr-badge-${r.product_id}`}
                          title="Sudah ada Permintaan Pembelian terbuka untuk produk ini — hindari PR ganda"
                          className="mt-0.5 inline-flex items-center gap-1 rounded-full bg-[#FFF4E5] px-2 py-0.5 text-[10px] font-semibold text-[#8C4A00] border border-[#FFD9A8]"
                        >
                          <Clock size={9} /> Sudah ada PR: {r.existing_prs.join(", ")}
                        </span>
                      )}
                    </div>
                    <span className="text-[12px] tabular-nums text-right text-[#126E2C]">{formatQty(r.available)}</span>
                    <span className="text-[12px] tabular-nums text-right text-[#8C4A00]">{formatQty(r.on_order)}</span>
                    <span className={`text-[12px] tabular-nums text-right ${Number(r.on_request) > 0 ? "font-bold text-[#8C4A00]" : "text-[#9A9BA3]"}`} data-testid={`reorder-onrequest-${r.product_id}`}>{formatQty(r.on_request || 0)}</span>
                    <span className={`text-[12px] tabular-nums text-right font-bold ${below ? "text-red-600" : ""}`}>
                      {formatQty(r.projected)} {below && <AlertTriangle size={11} className="inline -mt-0.5 text-red-500" />}
                    </span>
                    <span className="text-right">
                      {isEditing ? (
                        <input type="number" data-testid={`reorder-rp-input-${r.product_id}`} className="form-input text-right" style={{ width: 80 }}
                          defaultValue={r.reorder_point}
                          onChange={(e) => setRp({ ...rp, [r.product_id]: { ...(rp[r.product_id] || {}), reorder_point: e.target.value } })} />
                      ) : (
                        <button className="text-[12px] tabular-nums underline decoration-dotted" data-testid={`reorder-rp-${r.product_id}`} onClick={() => setEditing(r.product_id)}>{formatQty(r.reorder_point)}</button>
                      )}
                    </span>
                    <span className="text-right">
                      <input type="number" data-testid={`reorder-qty-${r.product_id}`} className="form-input text-right" style={{ width: 84 }}
                        value={editQty[r.product_id] ?? r.suggested_qty}
                        onChange={(e) => setEditQty({ ...editQty, [r.product_id]: e.target.value })} />
                    </span>
                    <span className="min-w-0" data-testid={`reorder-eta-${r.product_id}`}>
                      {r.lead_time_days > 0 ? (
                        <>
                          <span className="inline-flex items-center gap-1 text-[11.5px] font-semibold"><Clock size={11} className="text-[#0058CC]" />{r.lead_time_days} hari</span>
                          {r.expected_arrival_date && <p className="text-[10px] text-[#6B6B73]">≈ {fmtEta(r.expected_arrival_date)}</p>}
                        </>
                      ) : <span className="text-[11px] text-[#9A9BA3]">—</span>}
                    </span>
                    <span className="text-[11.5px] truncate flex items-center gap-1">
                      {isEditing ? (
                        <button className="btn-primary btn-xs" data-testid={`reorder-save-${r.product_id}`} onClick={() => saveReorder(r)} disabled={busy}><Save size={12} /> Simpan</button>
                      ) : (r.preferred_supplier_name || "—")}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Metric({ icon: Icon, label, value, tone, testId }) {
  return (
    <div data-testid={testId} className="metric-card">
      <div className="metric-icon" style={{ background: tone }}><Icon size={16} className="text-[#1C1C1E]" /></div>
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
        <p className="text-[17px] font-bold tabular-nums">{value}</p>
      </div>
    </div>
  );
}
