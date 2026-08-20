import { useState, useEffect } from "react";
import { Minus, Plus, Trash2, ShoppingCart, Loader2, CheckCircle2, ArrowLeft, PackageX } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { PosFBT } from "../../pos/PosFBT";
import { SalesTeamEditor, salesTeamError, customerDefaultTeam } from "../../pos/SalesTeamEditor";
import { formatCurrency } from "../../../utils/formatters";
import { onImageError, productImage } from "../../../utils/productImage";

const lineTotal = (it) => Number(it.product?.price || 0) * Number(it.quantity || 0);

export default function MobileCart({
  cart, setCart, data, selectedCustomer, setSelectedCustomer,
  selectedAddress, setSelectedAddress, paymentTerms = [], onSubmitOrder, onAdd,
  entityId, onBrowse, onDone,
}) {
  const customers = data?.customers || [];
  const [step, setStep] = useState("cart");      // "cart" | "checkout"
  const [termCode, setTermCode] = useState("");
  const [allowBackorder, setAllowBackorder] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [salesTeam, setSalesTeam] = useState([]);   // F-4c REVISI — tim sales per order
  const [deliveryDate, setDeliveryDate] = useState("");  // F-SHIP — request tgl kirim (opsional)
  const today = new Date().toISOString().slice(0, 10);

  // Prefill tim sales dari default customer (boleh di-override per order).
  useEffect(() => { setSalesTeam(customerDefaultTeam(selectedCustomer)); }, [selectedCustomer?.id]); // eslint-disable-line

  const subtotal = cart.reduce((s, it) => s + lineTotal(it), 0);
  const setQty = (pid, qv) => setCart((cur) => cur.map((it) => it.product.id === pid ? { ...it, quantity: Math.max(1, qv) } : it));
  const removeItem = (pid) => setCart((cur) => cur.filter((it) => it.product.id !== pid));

  const customer = customers.find((c) => c.id === selectedCustomer?.id) || selectedCustomer;
  const addresses = customer?.addresses || [];

  async function placeOrder() {
    if (!selectedCustomer?.id) { setStep("checkout"); return; }
    if (salesTeamError(salesTeam)) { setStep("checkout"); return; }
    setSubmitting(true);
    try {
      const ok = await onSubmitOrder({ payment_term_code: termCode, allow_backorder: allowBackorder, sales_team: salesTeam, delivery_date: deliveryDate });
      if (ok) { setStep("cart"); onDone && onDone(); }
    } finally {
      setSubmitting(false);
    }
  }

  if (cart.length === 0) {
    return (
      <div data-testid="mobile-cart-empty" className="flex flex-col items-center gap-3 py-20 text-center m-muted">
        <ShoppingCart size={34} className="text-[#C7C7CC]" />
        <p className="text-[14px] font-semibold text-[#1C1C1E]">Keranjang kosong</p>
        <p className="text-[12px]">Tambahkan produk dari katalog untuk membuat pesanan.</p>
        <button data-testid="mobile-cart-browse" onClick={onBrowse} className="primary-button mt-2 px-5 py-2.5">Mulai Belanja</button>
      </div>
    );
  }

  return (
    <div data-testid="mobile-cart" className="space-y-3" style={{ paddingBottom: "96px" }}>
      {step === "cart" ? (
        <>
          <div className="flex items-center gap-2">
            <ShoppingCart size={16} className="text-[#0058CC]" />
            <h2 className="m-section-title">Keranjang ({cart.length})</h2>
          </div>
          <div className="space-y-2.5">
            {cart.map((it) => (
              <div key={it.product.id} data-testid={`mobile-cart-item-${it.product.id}`} className="m-card flex items-center gap-2.5 p-2.5">
                <img src={productImage(it.product)} onError={onImageError} alt={it.product.name} className="h-14 w-14 rounded-lg object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12.5px] font-semibold">{it.product.name}</p>
                  <p className="text-[11px] tabular-nums m-muted">{formatCurrency(it.product.price)}/{it.unit}</p>
                  <p className="text-[12px] font-bold tabular-nums text-[#0058CC]">{formatCurrency(lineTotal(it))}</p>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <button data-testid={`mobile-cart-remove-${it.product.id}`} className="text-[#C0392B]" onClick={() => removeItem(it.product.id)} aria-label="Hapus"><Trash2 size={15} /></button>
                  <div className="flex items-center rounded-lg border border-[#E5E5EA]">
                    <button data-testid={`mobile-cart-minus-${it.product.id}`} className="px-2.5 py-1.5 text-[#6B6B73]" onClick={() => setQty(it.product.id, Number(it.quantity) - 1)} aria-label="Kurangi"><Minus size={13} /></button>
                    <span data-testid={`mobile-cart-qty-${it.product.id}`} className="min-w-[30px] text-center text-[12.5px] tabular-nums">{it.quantity}</span>
                    <button data-testid={`mobile-cart-plus-${it.product.id}`} className="px-2.5 py-1.5 text-[#6B6B73]" onClick={() => setQty(it.product.id, Number(it.quantity) + 1)} aria-label="Tambah"><Plus size={13} /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          {onAdd && cart[0] && (
            <PosFBT productId={cart[0].product.id} entityId={entityId} onAdd={onAdd} excludeIds={cart.map((it) => it.product.id)} />
          )}
        </>
      ) : (
        <>
          <button data-testid="mobile-cart-back" className="inline-flex items-center gap-1 text-[13px] font-semibold text-[#0058CC]" onClick={() => setStep("cart")}>
            <ArrowLeft size={16} /> Kembali ke keranjang
          </button>
          <div className="m-card space-y-3 p-4">
            <div>
              <label className="mb-1 block text-[12px] font-semibold">Pelanggan <span className="text-[#C0392B]">*</span></label>
              <KNSelect data-testid="mobile-customer-select" className="field" value={selectedCustomer?.id || ""}
                onValueChange={(id) => { const c = customers.find((x) => x.id === id); setSelectedCustomer(c || null); setSelectedAddress(c?.addresses?.[0]?.id || ""); }}
                placeholder="-- Pilih pelanggan --"
                options={[{ value: "", label: "-- Pilih pelanggan --" }, ...customers.map((c) => ({ value: c.id, label: `${c.name}${c.city ? " — " + c.city : ""}` }))]} />
            </div>
            {addresses.length > 0 && (
              <div>
                <label className="mb-1 block text-[12px] font-semibold">Alamat Kirim</label>
                <KNSelect data-testid="mobile-address-select" className="field" value={selectedAddress || ""} onValueChange={setSelectedAddress}
                  options={addresses.map((a) => ({ value: a.id, label: `${a.label || a.street || "Alamat"}${a.city ? " — " + a.city : ""}` }))} />
              </div>
            )}
            <div>
              <label className="mb-1 block text-[12px] font-semibold">Termin Pembayaran</label>
              <KNSelect data-testid="mobile-term-select" className="field" value={termCode} onValueChange={setTermCode} placeholder="Default sistem"
                options={[{ value: "", label: "Default sistem" }, ...paymentTerms.map((t) => ({ value: t.code, label: t.name || t.code }))]} />
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
        </>
      )}

      {/* Sticky CTA */}
      <div className="m-cta-bar">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[12px] m-muted">Estimasi subtotal</span>
          <span data-testid="mobile-cart-subtotal" className="text-[16px] font-bold tabular-nums">{formatCurrency(subtotal)}</span>
        </div>
        {step === "cart" ? (
          <button data-testid="mobile-checkout-btn" className="primary-button w-full justify-center py-3" disabled={cart.length === 0} onClick={() => setStep("checkout")}>
            Lanjut ke Checkout
          </button>
        ) : (
          <button data-testid="mobile-place-order-btn" className="primary-button w-full justify-center py-3" disabled={submitting || !selectedCustomer?.id || cart.length === 0} onClick={placeOrder}>
            {submitting ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />} Buat Pesanan
          </button>
        )}
        {step === "checkout" && !selectedCustomer?.id && <p className="mt-1.5 text-center text-[11px] text-[#C0392B]">Pilih pelanggan dulu.</p>}
      </div>
    </div>
  );
}
