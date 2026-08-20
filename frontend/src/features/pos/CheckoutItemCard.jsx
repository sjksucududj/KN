import { XCircle, BadgePercent } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { sourceMeta } from "../../hooks/useEffectivePrices";
import { FulfillmentInfo } from "../../components/FulfillmentInfo";

/**
 * Kartu satu item di Checkout step-2 (Term & Lot). Dipisah dari CheckoutDrawer
 * agar file tetap di bawah batas guardrail (≤500 baris) & mudah diuji.
 * Menampilkan: badge harga khusus, qty, shortcut "Minta Harga Khusus" + notice,
 * (opsional) diskon per item, dan info fulfillment/alokasi.
 */
export function CheckoutItemCard({
  item, sp, notice, allowItemDiscount = false, selectedCustomer,
  onRemove, onUpdateQty, onUpdateDiscount, onRequestSpecial,
  allocationLine, allocationLoading = false, reqStatus, onRequestTransfer,
}) {
  const pid = item.product.id;
  const isSpecial = !!(sp && sp.has_special);
  const baseUnit = item.product.base_unit || "meter";
  const rollCount = Number(item.product.roll_count || 0);
  // F1b — harga baris = harga EFEKTIF pelanggan (khusus → pelanggan → PT → umum).
  const unitPrice = sp && sp.price != null ? Number(sp.price) : Number(item.product.price || 0);
  const srcMeta = sp ? sourceMeta(sp.source) : null;
  const showSource = !!(srcMeta && ["special_approval", "customer"].includes(sp.source));
  const lineSubtotal = unitPrice * (item.quantity || 0);
  const dp = allowItemDiscount ? Number(item.discount_percent || 0) : 0;
  const lineTotal = lineSubtotal - (lineSubtotal * dp) / 100;

  return (
    <div data-testid={`cart-item-${pid}`} className="rounded-md border border-[#EFF0F2] bg-white p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10.5px] font-bold uppercase tracking-wide text-[#0058CC]">{item.product.sku}</p>
          <p data-testid={`cart-item-name-${pid}`} className="text-[12.5px] font-semibold truncate">{item.product.name}</p>
          {showSource && (
            <p data-testid={`cart-item-special-${pid}`}
              className="mt-0.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9.5px] font-bold"
              style={{ background: srcMeta.bg, color: srcMeta.fg }}>
              {srcMeta.label} {formatCurrency(unitPrice)}
              {Number(sp.normal_price) > unitPrice && (
                <span className="font-normal text-[#8E8E93] line-through">{formatCurrency(sp.normal_price)}</span>
              )}
            </p>
          )}
          {sp?.special_blocked_by_min && (
            <p data-testid={`cart-item-min-qty-${pid}`} className="mt-0.5 text-[9.5px] font-semibold text-[#B26A00]">
              Harga khusus baru berlaku dari {formatQty(sp.min_quantity)} {baseUnit}
            </p>
          )}
        </div>
        <button data-testid={`remove-cart-item-button-${pid}`} className="icon-button" onClick={() => onRemove(pid)} aria-label="Hapus"><XCircle size={14} /></button>
      </div>
      <div className="mt-2">
        <label className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Qty ({baseUnit})</label>
        <input data-testid={`cart-item-qty-input-${pid}`} className="field" type="number" min="1" value={item.quantity} onChange={(e) => onUpdateQty(pid, e.target.value)} />
        <p data-testid={`cart-item-rolls-${pid}`} className="mt-1 text-[10px] text-[#9A9BA3]">{rollCount} roll tersedia · dijual per {baseUnit}</p>
      </div>
      {/* Shortcut Harga Khusus — ajukan tanpa pindah menu. Notice tetap tampil
          walau isSpecial (approve path) agar feedback 'diterapkan/menunggu'
          tidak hilang saat badge muncul. */}
      {(notice || !isSpecial) && (
        <div className="mt-2">
          {notice ? (
            <p data-testid={`cart-item-sp-notice-${pid}`}
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9.5px] font-bold ${notice.applied ? "bg-[#E7F7EC] text-[#1B7E3B]" : "bg-[#FFF3D6] text-[#9A5B00]"}`}>
              {notice.message}
            </p>
          ) : (
            <button data-testid={`request-special-price-${pid}`}
              disabled={!selectedCustomer}
              onClick={onRequestSpecial}
              className="inline-flex items-center gap-1 rounded-md border border-[#6B219A] px-2 py-1 text-[10.5px] font-bold text-[#6B219A] hover:bg-[#F7EEFB] disabled:opacity-40">
              <BadgePercent size={12} /> Minta Harga Khusus
            </button>
          )}
        </div>
      )}
      {allowItemDiscount && (
        <div className="mt-2 grid grid-cols-[64px_1fr] items-end gap-2">
          <div>
            <label className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Disc %</label>
            <input data-testid={`cart-item-discount-input-${pid}`} className="field" type="number" min="0" max="100" value={item.discount_percent || 0} onChange={(e) => onUpdateDiscount(pid, e.target.value)} />
          </div>
          <div className="text-right">
            <p className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Subtotal</p>
            <p className="text-[12px] font-semibold tabular-nums">{formatCurrency(lineTotal)}{dp > 0 && <span className="ml-1 text-[10px] text-[#8E8E93] line-through">{formatCurrency(lineSubtotal)}</span>}</p>
          </div>
        </div>
      )}
      <FulfillmentInfo line={allocationLine} loading={allocationLoading} reqStatus={reqStatus} onRequestTransfer={onRequestTransfer} />
    </div>
  );
}

/** Baris label→nilai untuk panel review (footer gelap) checkout. */
export function Row({ label, value, muted = false }) {
  return (
    <div className="flex items-center justify-between">
      <span className={muted ? "text-white/50" : "text-white/80"}>{label}</span>
      <span className={muted ? "text-white/50" : "font-semibold"}>{value}</span>
    </div>
  );
}
