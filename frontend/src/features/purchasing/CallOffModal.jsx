import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, PackagePlus, AlertTriangle } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";

/**
 * CallOffModal (P2) — buat call-off (release) terhadap kontrak Blanket.
 *  - 2.a : call-off → PO anak normal (approval + receiving).
 *  - 3.b : harga boleh override (price ≠ contract_price) → alasan WAJIB.
 *  - 4.b : over-call (qty > sisa item ATAU nilai > sisa plafon) → diizinkan, tapi PO anak dipaksa approval.
 *
 * `blanket` = objek detail kontrak (berisi contract_items dgn remaining_qty,
 *  contract_price, unit, sku; value_remaining; warehouse_id/name).
 */
export default function CallOffModal({ open, blanket, onClose, onCreated, onError }) {
  const [rows, setRows] = useState({});           // product_id -> { qty, price }
  const [warehouseId, setWarehouseId] = useState("");
  const [eta, setEta] = useState("");
  const [notes, setNotes] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [warehouses, setWarehouses] = useState([]);
  const [busy, setBusy] = useState(false);

  const items = useMemo(() => (blanket?.contract_items || []), [blanket]);

  useEffect(() => {
    if (!open) { reset(); return; }
    setWarehouseId(blanket?.warehouse_id || "");
    (async () => {
      try {
        const w = await axios.get(`${API}/warehouses`);
        setWarehouses(Array.isArray(w.data) ? w.data : []);
      } catch (e) { /* warehouse opsional; default ikut kontrak */ }
    })();
  }, [open]); // eslint-disable-line

  function reset() {
    setRows({}); setWarehouseId(""); setEta(""); setNotes(""); setOverrideReason("");
  }

  const warehouseOptions = useMemo(
    () => warehouses.map((w) => ({ value: w.id, label: `${w.name}${w.code ? ` (${w.code})` : ""}` })), [warehouses]);

  function setRow(pid, patch) {
    setRows((rs) => ({ ...rs, [pid]: { ...(rs[pid] || {}), ...patch } }));
  }

  // Derivasi: baris terisi, deteksi override harga & over-call (qty/nilai).
  const analysis = useMemo(() => {
    const picked = [];
    let hasOverride = false;
    let qtyOverItems = [];
    let totalValue = 0;
    for (const it of items) {
      const r = rows[it.product_id];
      const qty = Number(r?.qty) || 0;
      if (qty <= 0) continue;
      const cprice = Number(it.contract_price) || 0;
      const price = r?.price === "" || r?.price === undefined ? cprice : Number(r.price) || 0;
      if (Math.abs(price - cprice) > 0.01) hasOverride = true;
      const rem = Number(it.remaining_qty ?? 0);
      if (qty > rem + 1e-6) qtyOverItems.push(`${it.sku} (minta ${formatQty(qty)}, sisa ${formatQty(rem)})`);
      totalValue += qty * price;
      picked.push({ product_id: it.product_id, quantity: qty, price, unit: it.unit || "" });
    }
    const valueRemaining = Number(blanket?.value_remaining ?? 0);
    const cap = Number(blanket?.contract_value_cap ?? 0);
    const valueOver = cap > 0 && totalValue > valueRemaining + 1e-6;
    const overCall = qtyOverItems.length > 0 || valueOver;
    return { picked, hasOverride, qtyOverItems, valueOver, overCall, totalValue, valueRemaining };
  }, [items, rows, blanket]);

  async function submit() {
    if (analysis.picked.length === 0) { onError?.("Isi qty > 0 pada minimal 1 item."); return; }
    if (analysis.hasOverride && !overrideReason.trim()) {
      onError?.("Override harga wajib menyertakan alasan (aturan 3.b)."); return;
    }
    setBusy(true);
    try {
      const body = {
        items: analysis.picked.map((p) => ({
          product_id: p.product_id, quantity: p.quantity, unit: p.unit, price: p.price, discount_percent: 0,
        })),
        warehouse_id: warehouseId || "",
        expected_delivery_date: eta,
        notes,
        price_override_reason: overrideReason.trim(),
      };
      const r = await axios.post(`${API}/purchase-orders/${blanket.id}/call-off`, body);
      onCreated?.(r.data);
    } catch (e) {
      onError?.(e.response?.data?.detail || "Gagal membuat call-off.");
    } finally { setBusy(false); }
  }

  if (!open || !blanket) return null;

  return (
    <div className="modal-overlay" data-testid="calloff-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 680, width: "95vw", maxHeight: "92vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2] sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <PackagePlus size={16} className="text-[#0058CC]" />
            <div>
              <h2 className="text-[14px] font-bold">Buat Call-off</h2>
              <p className="text-[10.5px] text-[#6B6B73]">Kontrak {blanket.po_number} · {blanket.supplier_name}</p>
            </div>
          </div>
          <button data-testid="calloff-close" onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-3">
          {/* Item kontrak → qty + harga (override 3.b) */}
          <div>
            <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Tarik dari Kontrak <span className="text-red-500">*</span></label>
            <div className="grid grid-cols-[1fr_84px_96px_110px] gap-2 px-1 mb-1 text-[10px] font-bold uppercase text-[#9A9BA3]">
              <span>Produk</span><span className="text-right">Sisa</span><span>Qty Tarik</span><span>Harga</span>
            </div>
            <div className="space-y-2">
              {items.map((it) => {
                const r = rows[it.product_id] || {};
                const rem = Number(it.remaining_qty ?? 0);
                const qty = Number(r.qty) || 0;
                const over = qty > rem + 1e-6;
                return (
                  <div key={it.product_id} className="grid grid-cols-[1fr_84px_96px_110px] gap-2 items-center" data-testid={`calloff-row-${it.product_id}`}>
                    <div className="min-w-0">
                      <p className="text-[11.5px] font-semibold truncate">{it.sku}</p>
                      <p className="text-[10px] text-[#6B6B73] truncate">{it.product_name}</p>
                    </div>
                    <span className={`text-[11px] text-right tabular-nums ${rem <= 0 ? "text-[#B45309]" : "text-[#6B6B73]"}`}>{formatQty(rem)} {it.unit}</span>
                    <input type="number" value={r.qty ?? ""} onChange={(e) => setRow(it.product_id, { qty: e.target.value })}
                      className={`field ${over ? "!border-[#B45309]" : ""}`} placeholder="0" data-testid={`calloff-qty-${it.product_id}`} />
                    <input type="number" value={r.price ?? it.contract_price} onChange={(e) => setRow(it.product_id, { price: e.target.value })}
                      className="field" placeholder={`${it.contract_price}`} data-testid={`calloff-price-${it.product_id}`} />
                  </div>
                );
              })}
            </div>
          </div>

          {/* Warning over-call (4.b) */}
          {analysis.overCall && (
            <div data-testid="calloff-overcall-warning" className="flex items-start gap-2 rounded-md border border-[#FFE2B8] bg-[#FFF7EC] px-2.5 py-2 text-[11px] text-[#9A5B00]">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <div>
                <b>Over-call terdeteksi</b> — call-off ini melebihi sisa kontrak, sehingga PO anak akan <b>dipaksa melewati persetujuan</b> (aturan 4.b).
                {analysis.qtyOverItems.length > 0 && <p className="mt-0.5">Qty: {analysis.qtyOverItems.join("; ")}</p>}
                {analysis.valueOver && <p className="mt-0.5 tabular-nums">Nilai: minta {formatCurrency(analysis.totalValue)}, sisa plafon {formatCurrency(analysis.valueRemaining)}</p>}
              </div>
            </div>
          )}

          {/* Override harga (3.b) → alasan wajib */}
          {analysis.hasOverride && (
            <div>
              <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Alasan Override Harga <span className="text-red-500">*</span></label>
              <input data-testid="calloff-override-reason" value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)}
                className="field" placeholder="mis. harga spot naik / nego baru" />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Gudang Terima</label>
              <KNSelect value={warehouseId} onValueChange={setWarehouseId} options={warehouseOptions}
                className="field" placeholder="Ikut kontrak" data-testid="calloff-warehouse-select" />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Perkiraan Tiba</label>
              <input type="date" data-testid="calloff-eta" value={eta} onChange={(e) => setEta(e.target.value)} className="field" />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">Catatan</label>
            <textarea data-testid="calloff-notes" value={notes} onChange={(e) => setNotes(e.target.value)} className="field" rows="2" placeholder="Catatan call-off..." />
          </div>

          {/* Ringkasan nilai call-off */}
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5 text-[11.5px]" data-testid="calloff-summary">
            <div className="flex justify-between"><span className="text-[#6B6B73]">Nilai Call-off</span><span data-testid="calloff-total" className="tabular-nums font-bold text-[#007AFF]">{formatCurrency(analysis.totalValue)}</span></div>
            <div className="flex justify-between mt-0.5"><span className="text-[#6B6B73]">Sisa Plafon</span><span className="tabular-nums">{formatCurrency(analysis.valueRemaining)}</span></div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2] sticky bottom-0 bg-white">
          <button onClick={onClose} className="secondary-button">Batal</button>
          <button data-testid="calloff-submit" disabled={busy} onClick={submit} className="primary-button">
            {busy ? "Memproses..." : "Buat Call-off"}
          </button>
        </div>
      </div>
    </div>
  );
}
