import { useState, useEffect } from "react";
import { Minus, Plus, Trash2, X, ArrowLeft, ShoppingCart, Loader2, CheckCircle2 } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { PosFBT } from "../PosFBT";
import { SalesTeamEditor, salesTeamError, customerDefaultTeam } from "../SalesTeamEditor";
import { formatCurrency } from "../../../utils/formatters";
import { onImageError, productImage } from "../../../utils/productImage";

const lineTotal = (it) => Number(it.product?.price || 0) * Number(it.quantity || 0);

/** F-4a — Bottom sheet keranjang + checkout untuk Mobile POS (2 langkah). */
export function MobileCartSheet({
  open, onClose, cart, setCart, customers = [],
  selectedCustomer, setSelectedCustomer, selectedAddress, setSelectedAddress,
  paymentTerms = [], onSubmitOrder, onAdd, entityId,
}) {
  const [step, setStep] = useState("cart");      // "cart" | "checkout"
  const [termCode, setTermCode] = useState("");
  const [allowBackorder, setAllowBackorder] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [salesTeam, setSalesTeam] = useState([]);   // F-4c REVISI — tim sales per order
  const [deliveryDate, setDeliveryDate] = useState("");  // F-SHIP — request tgl kirim (opsional)
  const today = new Date().toISOString().slice(0, 10);

  // Prefill tim sales dari default customer (boleh di-override per order).
  useEffect(() => { setSalesTeam(customerDefaultTeam(selectedCustomer)); }, [selectedCustomer?.id]); // eslint-disable-line

  if (!open) return null;

  const subtotal = cart.reduce((s, it) => s + lineTotal(it), 0);
  const setQty = (pid, q) => setCart((cur) => cur.map((it) => it.product.id === pid ? { ...it, quantity: Math.max(1, q) } : it));
  const removeItem = (pid) => setCart((cur) => cur.filter((it) => it.product.id !== pid));

  const customer = customers.find((c) => c.id === selectedCustomer?.id) || selectedCustomer;
  const addresses = customer?.addresses || [];

  async function placeOrder() {
    if (!selectedCustomer?.id) { setStep("checkout"); return; }
    if (salesTeamError(salesTeam)) { setStep("checkout"); return; }
    setSubmitting(true);
    try {
      const ok = await onSubmitOrder({ payment_term_code: termCode, allow_backorder: allowBackorder, sales_team: salesTeam, delivery_date: deliveryDate });
      if (ok) {
        onClose();
        setStep("cart");
      }
      // bila gagal (mis. kredit terblokir / stok kurang): sheet tetap terbuka, notice tampil di atas
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-end justify-center" data-testid="mobile-cart-sheet">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-[460px] rounded-t-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <div className="flex items-center gap-2">
            {step === "checkout" && (
              <button data-testid="mobile-cart-back" className="text-[#6B6B73]" onClick={() => setStep("cart")} aria-label="Kembali"><ArrowLeft size={18} /></button>
            )}
            <ShoppingCart size={16} className="text-[#0058CC]" />
            <h3 className="text-[14px] font-bold">{step === "cart" ? "Keranjang" : "Checkout"}</h3>
          </div>
          <button data-testid="mobile-cart-close" onClick={onClose} aria-label="Tutup" className="text-[#6B6B73]"><X size={18} /></button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto px-4 py-3">
          {step === "cart" ? (
            cart.length === 0 ? (
              <div data-testid="mobile-cart-empty" className="py-10 text-center text-[13px] text-[#6B6B73]">Keranjang kosong.</div>
            ) : (
              <>
                <div className="space-y-2.5">
                  {cart.map((it) => (
                    <div key={it.product.id} data-testid={`mobile-cart-item-${it.product.id}`} className="flex items-center gap-2.5 rounded-lg border border-[#EFF0F2] p-2">
                      <img src={productImage(it.product)} onError={onImageError} alt={it.product.name} className="h-12 w-12 rounded-md object-cover" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[12.5px] font-semibold">{it.product.name}</p>
                        <p className="text-[11px] tabular-nums text-[#6B6B73]">{formatCurrency(it.product.price)}/{it.unit}</p>
                        <p className="text-[11.5px] font-bold tabular-nums text-[#0058CC]">{formatCurrency(lineTotal(it))}</p>
                      </div>
                      <div className="flex items-center rounded-md border border-[#E5E5EA]">
                        <button data-testid={`mobile-cart-minus-${it.product.id}`} className="px-2 py-1 text-[#6B6B73]" onClick={() => setQty(it.product.id, Number(it.quantity) - 1)} aria-label="Kurangi"><Minus size={12} /></button>
                        <span data-testid={`mobile-cart-qty-${it.product.id}`} className="min-w-[28px] text-center text-[12px] tabular-nums">{it.quantity}</span>
                        <button data-testid={`mobile-cart-plus-${it.product.id}`} className="px-2 py-1 text-[#6B6B73]" onClick={() => setQty(it.product.id, Number(it.quantity) + 1)} aria-label="Tambah"><Plus size={12} /></button>
                      </div>
                      <button data-testid={`mobile-cart-remove-${it.product.id}`} className="icon-button px-1.5 text-[#C0392B]" onClick={() => removeItem(it.product.id)} aria-label="Hapus"><Trash2 size={13} /></button>
                    </div>
                  ))}
                </div>
                {onAdd && cart[0] && (
                  <PosFBT productId={cart[0].product.id} entityId={entityId} onAdd={onAdd} excludeIds={cart.map((it) => it.product.id)} />
                )}
              </>
            )
          ) : (
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[12px] font-semibold">Pelanggan <span className="text-[#C0392B]">*</span></label>
                <KNSelect
                  data-testid="mobile-customer-select"
                  className="field"
                  value={selectedCustomer?.id || ""}
                  onValueChange={(id) => {
                    const c = customers.find((x) => x.id === id);
                    setSelectedCustomer(c || null);
                    setSelectedAddress(c?.addresses?.[0]?.id || "");
                  }}
                  placeholder="-- Pilih pelanggan --"
                  options={[{ value: "", label: "-- Pilih pelanggan --" }, ...customers.map((c) => ({ value: c.id, label: `${c.name}${c.city ? " — " + c.city : ""}` }))]}
                />
              </div>
              {addresses.length > 0 && (
                <div>
                  <label className="mb-1 block text-[12px] font-semibold">Alamat Kirim</label>
                  <KNSelect
                    data-testid="mobile-address-select"
                    className="field"
                    value={selectedAddress || ""}
                    onValueChange={setSelectedAddress}
                    options={addresses.map((a) => ({ value: a.id, label: `${a.label || a.street || "Alamat"}${a.city ? " — " + a.city : ""}` }))}
                  />
                </div>
              )}
              <div>
                <label className="mb-1 block text-[12px] font-semibold">Termin Pembayaran</label>
                <KNSelect
                  data-testid="mobile-term-select"
                  className="field"
                  value={termCode}
                  onValueChange={setTermCode}
                  placeholder="Default sistem"
                  options={[{ value: "", label: "Default sistem" }, ...paymentTerms.map((t) => ({ value: t.code, label: t.name || t.code }))]}
                />
              </div>
              <label className="flex items-center gap-2 text-[12px]">
                <input type="checkbox" data-testid="mobile-allow-backorder" checked={allowBackorder} onChange={(e) => setAllowBackorder(e.target.checked)} />
                Izinkan backorder (stok kurang tetap dipesan)
              </label>
              <div data-testid="mobile-delivery-date" className="mt-1">
                <label className="mb-1 block text-[12px] font-semibold">Tanggal Pengiriman (opsional)</label>
                <input type="date" data-testid="mobile-delivery-date-input" className="field" min={today}
                  value={deliveryDate} onChange={(e) => setDeliveryDate(e.target.value)} />
              </div>
              {selectedCustomer?.id && (
                <div data-testid="mobile-sales-team" className="rounded-md border border-[#EFF0F2] bg-white p-2.5">
                  <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Tim Sales & Bagi Hasil (pesanan ini)</p>
                  <p className="mb-2 text-[10.5px] text-[#8E8E93]">Terisi dari bawaan pelanggan, bisa diubah per pesanan (total bagi 100%).</p>
                  <SalesTeamEditor value={salesTeam} onChange={setSalesTeam} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-[#EFF0F2] px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[12px] text-[#6B6B73]">Estimasi subtotal</span>
            <span data-testid="mobile-cart-est-subtotal" className="text-[16px] font-bold tabular-nums text-[#1C1C1E]">{formatCurrency(subtotal)}</span>
          </div>
          {step === "cart" ? (
            <button data-testid="mobile-checkout-btn" className="primary-button w-full justify-center py-2.5" disabled={cart.length === 0} onClick={() => setStep("checkout")}>
              Lanjut ke Checkout
            </button>
          ) : (
            <button data-testid="mobile-place-order-btn" className="primary-button w-full justify-center py-2.5" disabled={submitting || !selectedCustomer?.id || cart.length === 0} onClick={placeOrder}>
              {submitting ? <Loader2 size={15} className="spin" /> : <CheckCircle2 size={15} />} Buat Pesanan
            </button>
          )}
          {step === "checkout" && !selectedCustomer?.id && (
            <p className="mt-1.5 text-center text-[11px] text-[#C0392B]">Pilih pelanggan dulu untuk membuat pesanan.</p>
          )}
        </div>
      </div>
    </div>
  );
}
