import { useEffect, useMemo, useState } from "react";
import { X, Plus, Minus, ShoppingBag, Scissors } from "lucide-react";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import { unitOptions, convFactor } from "../../../utils/uom";
import { pickPrice } from "../../../hooks/useEffectivePrices";
import { variantLabel, deriveAxisOptions } from "../../../utils/variants";
import VariantAxisPicker from "../../../components/VariantAxisPicker";
import KNSelect from "../../../components/KNSelect";
import RollPicker from "../../../components/RollPicker";
import RollReconcileSheet from "../../../components/RollReconcileSheet";
import { blocksOrder, lifecycleLabel, notOrderableReason } from "../../../utils/lifecycle";
import { onImageError, productImage } from "../../../utils/productImage";

/** EPIC-VAR — bottom-sheet detail produk + pemilih varian (versi MOBILE).
 * SALES REVAMP V2: mode "Per yard" / "Beli per Roll"; inventory = total global saja.
 * FASE F: varian yang belum dirilis ke produksi tidak bisa ditambahkan. */
export default function MobileQuickView({ group, specialMap = {}, onAdd, onClose, entityId = "",
  rndEnforcement = "block" }) {
  const variants = useMemo(() => group?.variants || [], [group]);
  const [selectedId, setSelectedId] = useState(null);
  const [qty, setQty] = useState(1);
  const [unit, setUnit] = useState("meter");
  const [mode, setMode] = useState("qty");
  const [showReconcile, setShowReconcile] = useState(false);

  useEffect(() => {
    if (!group || variants.length === 0) return;
    const fa = variants.find((v) => Number(v.available_qty || 0) > 0) || variants[0];
    setSelectedId(fa.id); setQty(1); setUnit(fa.base_unit || "meter"); setMode("qty");
  }, [group]); // eslint-disable-line

  const selected = useMemo(() => variants.find((v) => v.id === selectedId) || variants[0] || null, [variants, selectedId]);
  const axisMode = useMemo(() => { const a = deriveAxisOptions(variants); return a.hasColor || a.hasGrade; }, [variants]);
  useEffect(() => { if (selected) setUnit(selected.base_unit || "meter"); }, [selectedId]); // eslint-disable-line

  if (!group || !selected) return null;
  const special = pickPrice(specialMap[selected.id], qty);
  const isSpecial = !!(special && special.has_special);
  const baseUnit = selected.base_unit || "meter";
  const factor = convFactor(selected, unit) ?? 1;
  // F1b — harga dasar = harga EFEKTIF pelanggan, bukan harga umum produk.
  const effBase = special && special.price != null ? Number(special.price) : Number(selected.price || 0);
  const unitPrice = isSpecial ? Number(special.price) : Math.round(effBase * factor * 100) / 100;
  const baseUnitPrice = effBase;
  const avail = Number(selected.available_qty || 0);
  const rollCount = Number(selected.roll_count || 0);
  const lineTotal = unitPrice * (Number(qty) || 0);
  const step = (d) => setQty((q) => Math.max(1, Number(q || 1) + d));
  const blocked = blocksOrder(selected, rndEnforcement);

  return (
    <div className="m-sheet-wrap" data-testid="mobile-quickview">
      <div className="m-sheet-backdrop" onClick={onClose} />
      <div className="m-sheet">
        <div className="m-sheet-grip" />
        <div className="flex items-center justify-between px-4 pb-1">
          <div className="min-w-0">
            <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#0058CC]">{group.category}{group.isMulti ? ` · ${variants.length} varian` : ""}</p>
            <h3 className="m-section-title truncate">{group.name}</h3>
          </div>
          <button data-testid="mobile-quickview-close" onClick={onClose} aria-label="Tutup" className="text-[#6B6B73]"><X size={18} /></button>
        </div>
        <div className="overflow-y-auto px-4 pb-4" style={{ maxHeight: "74vh" }}>
          <img src={productImage(selected)} onError={onImageError} alt={group.name} className="h-40 w-full rounded-xl object-cover" />
          <div className="mt-2 flex items-end justify-between">
            <p data-testid="mobile-quickview-price" className="text-[20px] font-bold tabular-nums">{formatCurrency(unitPrice)}<span className="text-[11px] font-medium text-[#8E8E93]">/{unit}</span></p>
            <p className="text-[12px] m-muted">Stok <b className="text-[#126E2C]">{formatQty(avail)}</b> {baseUnit} · {rollCount} roll</p>
          </div>
          {isSpecial && <p className="mt-1 inline-block rounded-full bg-[#F3E9FA] px-2 py-0.5 text-[10.5px] font-bold text-[#6B219A]">Harga khusus · normal {formatCurrency(special.normal_price)}</p>}

          {/* M0 — pemilih dua sumbu (Warna + Grade) di mobile */}
          {axisMode ? (
            <div className="mt-3">
              <VariantAxisPicker variants={variants} selectedId={selected.id} onSelect={(v) => setSelectedId(v.id)} testIdPrefix="mobile-quickview" />
            </div>
          ) : group.isMulti ? (
            <>
              <p className="mt-3 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">Pilih Varian</p>
              <div className="mt-1 flex flex-wrap gap-2" data-testid="mobile-quickview-variants">
                {variants.map((v) => {
                  const va = Number(v.available_qty || 0); const active = v.id === selected.id;
                  return (
                    <button key={v.id} data-testid={`mobile-quickview-variant-${v.id}`} onClick={() => setSelectedId(v.id)}
                      className={`rounded-lg border px-2.5 py-1.5 text-left ${active ? "border-[#0058CC] bg-[#EAF2FF]" : "border-[#E5E5EA] bg-white"}`}>
                      <span className="block text-[12px] font-semibold">{variantLabel(v)}</span>
                      <span className={`block text-[10px] ${va <= 0 ? "text-[#A8221A]" : "text-[#6B6B73]"}`}>{va <= 0 ? "Habis" : `Stok ${formatQty(va)}`} · {formatCurrency(v.price)}</span>
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}

          {/* FASE F — belum boleh dijual: alasan + jalan keluar (mobile) */}
          {blocked && (
            <div data-testid="mobile-quickview-not-orderable"
              className="mt-3 rounded-lg border border-[#F0D7A8] bg-[#FFF6E5] p-2.5 text-[11.5px] leading-relaxed text-[#8C4A00]">
              <b>{lifecycleLabel(selected)} — belum boleh dijual.</b> {notOrderableReason(selected)}
            </div>
          )}

          {/* SALES REVAMP V2 — mode beli */}
          <div data-testid="mobile-quickview-mode" className="mt-3 grid grid-cols-2 gap-2">
            <button type="button" data-testid="mobile-quickview-mode-qty" onClick={() => setMode("qty")}
              className={`rounded-lg border px-3 py-2 text-[12px] font-semibold ${mode === "qty" ? "border-[#0058CC] bg-[#EAF2FF] text-[#0058CC]" : "border-[#E5E5EA] bg-white text-[#3C3C43]"}`}>Per {baseUnit}</button>
            <button type="button" data-testid="mobile-quickview-mode-roll" onClick={() => setMode("roll")} disabled={rollCount <= 0 || blocked}
              className={`flex items-center justify-center gap-1 rounded-lg border px-3 py-2 text-[12px] font-semibold disabled:opacity-40 ${mode === "roll" ? "border-[#0058CC] bg-[#EAF2FF] text-[#0058CC]" : "border-[#E5E5EA] bg-white text-[#3C3C43]"}`}><Scissors size={13} /> Per Roll</button>
          </div>

          {mode === "qty" ? (
            <>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Qty</label>
                  <div className="flex items-center rounded-lg border border-[#E5E5EA]">
                    <button data-testid="mobile-quickview-qty-minus" className="px-3 py-2.5 text-[#6B6B73]" onClick={() => step(-1)} aria-label="Kurangi"><Minus size={15} /></button>
                    <input data-testid="mobile-quickview-qty-input" type="number" min="1" className="w-full border-x border-[#E5E5EA] bg-transparent py-2 text-center text-[15px] outline-none" value={qty} onChange={(e) => setQty(Math.max(1, Number(e.target.value) || 1))} />
                    <button data-testid="mobile-quickview-qty-plus" className="px-3 py-2.5 text-[#6B6B73]" onClick={() => step(1)} aria-label="Tambah"><Plus size={15} /></button>
                  </div>
                </div>
                <div className="min-w-0">
                  <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Satuan</label>
                  <KNSelect data-testid="mobile-quickview-unit-select" className="field w-full" value={unit} onValueChange={setUnit} options={unitOptions(selected)} />
                </div>
              </div>
              <button data-testid="mobile-quickview-add" disabled={avail <= 0 || blocked}
                className="primary-button mt-4 w-full justify-center py-3 text-[14px]"
                onClick={() => {
                  if (rollCount > 0) { setShowReconcile(true); }
                  else { onAdd(selected, qty, unit); onClose(); }
                }}>
                <ShoppingBag size={16} /> {blocked ? "Belum boleh dijual"
                  : avail <= 0 ? "Stok Habis" : `Tambah ${qty} ${unit} · ${formatCurrency(lineTotal)}`}
              </button>
            </>
          ) : (
            <div className="mt-3">
              <RollPicker
                productId={selected.id}
                entityId={entityId}
                unitPrice={baseUnitPrice}
                baseUnit={baseUnit}
                onConfirm={(rollLines, snapshot, totalQty) => {
                  onAdd(selected, totalQty, baseUnit, { purchase_mode: "roll", roll_lines: rollLines, rolls_snapshot: snapshot });
                  onClose();
                }}
              />
            </div>
          )}
        </div>
      </div>

      <RollReconcileSheet
        open={showReconcile}
        productId={selected.id}
        entityId={entityId}
        targetQty={Math.round((Number(qty) || 0) * factor * 100) / 100}
        unitPrice={baseUnitPrice}
        baseUnit={baseUnit}
        onClose={() => setShowReconcile(false)}
        onConfirm={(rollLines, totalQty, snapshot) => {
          setShowReconcile(false);
          onAdd(selected, totalQty, baseUnit, { purchase_mode: "roll", roll_lines: rollLines, rolls_snapshot: snapshot });
          onClose();
        }}
      />
    </div>
  );
}
