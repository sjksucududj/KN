import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, Plus, Trash2, ClipboardList } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import GroupEntityBadge, { isGroupEntityPartner } from "../../components/GroupEntityBadge";

/**
 * RFQCreateModal (Fase 6.1) — buat RFQ dari PR approved atau manual,
 * lalu undang beberapa supplier untuk memberi penawaran.
 */
export default function RFQCreateModal({ open, selectedEntity, onClose, onCreated, onError }) {
  const [source, setSource] = useState("manual");
  const [title, setTitle] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [prId, setPrId] = useState("");
  const [neededBy, setNeededBy] = useState("");
  const [rows, setRows] = useState([{ product_id: "", quantity: "", unit: "meter" }]);
  const [supplierIds, setSupplierIds] = useState([]);
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [prs, setPrs] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) { reset(); return; }
    (async () => {
      try {
        const [p, s, w, pr] = await Promise.all([
          axios.get(`${API}/products`),
          axios.get(`${API}/suppliers`),
          axios.get(`${API}/warehouses`),
          axios.get(`${API}/purchase-requisitions`, { params: { status: "approved" } }).catch(() => ({ data: { items: [] } })),
        ]);
        setProducts(Array.isArray(p.data) ? p.data : []);
        setSuppliers(Array.isArray(s.data) ? s.data : []);
        setWarehouses(Array.isArray(w.data) ? w.data : []);
        const prItems = Array.isArray(pr.data) ? pr.data : (pr.data?.items || []);
        setPrs(prItems.filter((x) => x.status === "approved" && !x.po_id));
      } catch (e) { onError?.("Gagal memuat data master."); }
    })();
  }, [open]); // eslint-disable-line

  function reset() {
    setSource("manual"); setTitle(""); setWarehouseId(""); setPrId(""); setNeededBy("");
    setRows([{ product_id: "", quantity: "", unit: "meter" }]); setSupplierIds([]);
  }

  const selectedPr = useMemo(() => prs.find((p) => p.id === prId), [prs, prId]);
  const productOptions = useMemo(() => products.map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` })), [products]);
  const warehouseOptions = useMemo(() => warehouses.map((w) => ({ value: w.id, label: w.name })), [warehouses]);
  const prOptions = useMemo(() => prs.map((p) => ({ value: p.id, label: `${p.number} · ${(p.items || []).length} item` })), [prs]);

  function setRow(i, patch) { setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r))); }
  function addRow() { setRows((rs) => [...rs, { product_id: "", quantity: "", unit: "meter" }]); }
  function delRow(i) { setRows((rs) => rs.filter((_, idx) => idx !== i)); }
  function toggleSupplier(id) {
    setSupplierIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  async function submit() {
    if (!warehouseId) { onError?.("Pilih gudang tujuan."); return; }
    if (supplierIds.length === 0) { onError?.("Undang minimal 1 supplier."); return; }
    let items = [];
    if (source === "manual") {
      items = rows.filter((r) => r.product_id && Number(r.quantity) > 0)
        .map((r) => ({ product_id: r.product_id, quantity: Number(r.quantity), unit: r.unit || "meter" }));
      if (items.length === 0) { onError?.("Tambah minimal 1 item (produk + qty)."); return; }
    } else if (!prId) { onError?.("Pilih PR sumber."); return; }

    setBusy(true);
    try {
      const body = {
        source, pr_id: source === "pr" ? prId : "", title,
        entity_id: (selectedEntity && selectedEntity !== "all") ? selectedEntity : "",
        warehouse_id: warehouseId, items, supplier_ids: supplierIds, needed_by_date: neededBy,
      };
      const r = await axios.post(`${API}/rfqs`, body);
      onCreated?.(r.data);
    } catch (e) {
      onError?.(e.response?.data?.detail || "Gagal membuat RFQ.");
    } finally { setBusy(false); }
  }

  if (!open) return null;

  return (
    <div className="modal-overlay" data-testid="rfq-create-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 720, width: "95vw", maxHeight: "92vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2] sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2"><ClipboardList size={16} className="text-[#0058CC]" /><h2 className="text-[14px] font-bold">Buat RFQ / Penawaran</h2></div>
          <button data-testid="rfq-create-close" onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-3">
          <div className="flex gap-2">
            <button data-testid="rfq-source-manual" onClick={() => setSource("manual")}
              className={`flex-1 py-2 rounded-md text-[12px] font-semibold border ${source === "manual" ? "border-[#0058CC] bg-[#EAF2FF] text-[#0058CC]" : "border-[#EFF0F2] text-[#6B6B73]"}`}>Manual (pilih produk)</button>
            <button data-testid="rfq-source-pr" onClick={() => setSource("pr")}
              className={`flex-1 py-2 rounded-md text-[12px] font-semibold border ${source === "pr" ? "border-[#0058CC] bg-[#EAF2FF] text-[#0058CC]" : "border-[#EFF0F2] text-[#6B6B73]"}`}>Dari PR disetujui</button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Judul RFQ"><input data-testid="rfq-title-input" value={title} onChange={(e) => setTitle(e.target.value)} className="field" placeholder="mis. Pengadaan kain Q1" /></Field>
            <Field label="Gudang Tujuan" req><KNSelect value={warehouseId} onValueChange={setWarehouseId} options={warehouseOptions} className="field" placeholder="Pilih gudang..." data-testid="rfq-warehouse-select" /></Field>
          </div>

          {source === "pr" ? (
            <Field label="Permintaan Pembelian (disetujui)" req>
              {prs.length === 0 ? (
                <p className="text-[11px] text-[#9A9BA3] px-2 py-2 rounded-md border border-[#EFF0F2]" data-testid="rfq-no-pr">Tidak ada PR disetujui yang belum dikonversi.</p>
              ) : (
                <KNSelect value={prId} onValueChange={setPrId} options={prOptions} className="field" placeholder="Pilih PR..." data-testid="rfq-pr-select" />
              )}
              {selectedPr && (
                <div className="mt-2 rounded-md bg-[#FAFBFC] border border-[#EFF0F2] p-2 text-[11px]" data-testid="rfq-pr-items">
                  {(selectedPr.items || []).map((it, i) => (
                    <div key={i} className="flex justify-between py-0.5"><span>{it.sku || it.description} × {it.quantity} {it.unit}</span></div>
                  ))}
                </div>
              )}
            </Field>
          ) : (
            <div>
              <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Item <span className="text-red-500">*</span></label>
              <div className="space-y-2">
                {rows.map((r, i) => (
                  <div key={i} className="grid grid-cols-[1fr_90px_80px_32px] gap-2" data-testid={`rfq-item-row-${i}`}>
                    <KNSelect value={r.product_id} onValueChange={(v) => { const p = products.find((x) => x.id === v); setRow(i, { product_id: v, unit: p?.base_unit || "meter" }); }} options={productOptions} className="field" placeholder="Produk..." data-testid={`rfq-item-product-${i}`} />
                    <input type="number" value={r.quantity} onChange={(e) => setRow(i, { quantity: e.target.value })} className="field" placeholder="Qty" data-testid={`rfq-item-qty-${i}`} />
                    <div className="field flex items-center bg-[#F5F5F7] font-semibold text-[#3C3C43]" data-testid={`rfq-item-unit-${i}`} title="Satuan mengikuti master data produk">{r.unit || "—"}</div>
                    <button onClick={() => delRow(i)} disabled={rows.length === 1} className="icon-button text-red-500 disabled:opacity-30"><Trash2 size={14} /></button>
                  </div>
                ))}
              </div>
              <button data-testid="rfq-add-item" onClick={addRow} className="secondary-button mt-2 text-[11px]"><Plus size={12} /> Tambah Item</button>
            </div>
          )}

          <Field label="Dibutuhkan Sebelum"><input type="date" data-testid="rfq-needed-date" value={neededBy} onChange={(e) => setNeededBy(e.target.value)} className="field !w-[180px]" /></Field>

          <div>
            <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Undang Supplier <span className="text-red-500">*</span> <span className="text-[#9A9BA3]">({supplierIds.length} dipilih)</span></label>
            <div className="grid grid-cols-2 gap-1.5 max-h-[160px] overflow-y-auto" data-testid="rfq-supplier-list">
              {suppliers.map((sup) => {
                // FASE E-7 (E7.2) — badan usaha grup TIDAK menawar: harganya diatur
                // kontrak internal. Kotak centangnya dimatikan + diberi lencana supaya
                // alasannya terbaca, bukan sekadar tidak bisa diklik.
                const isGroup = isGroupEntityPartner(sup);
                return (
                  <label key={sup.id} data-testid={`rfq-supplier-${sup.id}`}
                    title={isGroup ? `${sup.name} adalah badan usaha di dalam grup — pakai menu Antar Entitas` : ""}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded-md border text-[12px] ${
                      isGroup ? "border-violet-200 bg-violet-50/60 cursor-not-allowed opacity-90"
                        : supplierIds.includes(sup.id) ? "border-[#0058CC] bg-[#EAF2FF] cursor-pointer"
                        : "border-[#EFF0F2] cursor-pointer"}`}>
                    <input type="checkbox" disabled={isGroup} checked={supplierIds.includes(sup.id)}
                      onChange={() => !isGroup && toggleSupplier(sup.id)} />
                    <span className="truncate">{sup.name}</span>
                    {isGroup && <GroupEntityBadge partner={sup} className="ml-auto" />}
                  </label>
                );
              })}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2] sticky bottom-0 bg-white">
          <button onClick={onClose} className="secondary-button">Batal</button>
          <button data-testid="rfq-submit" disabled={busy} onClick={submit} className="primary-button">{busy ? "Menyimpan..." : "Buat RFQ"}</button>
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
