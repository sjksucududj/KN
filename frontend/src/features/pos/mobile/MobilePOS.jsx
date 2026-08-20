import { useMemo, useState } from "react";
import { Search, ShoppingCart, Smartphone, PackageX } from "lucide-react";
import { MobileProductCard } from "./MobileProductCard";
import { MobileCartSheet } from "./MobileCartSheet";
import { PosBestSellers } from "../PosBestSellers";
import { PosSubstitutesSheet } from "../PosSubstitutesSheet";
import { formatCurrency } from "../../../utils/formatters";

/**
 * F-4a — Mobile POS dedicated.
 * Layar mobile-first khusus HP (di desktop tampil sebagai frame ponsel terpusat).
 * Reuse backend katalog & action yang sama (addToCart / submitOrder).
 */
export function MobilePOS({
  data, loading, onAdd, onInspect,
  cart, setCart,
  selectedCustomer, setSelectedCustomer, selectedAddress, setSelectedAddress,
  onSubmitOrder, paymentTerms = [],
  search, setSearch, entityId,
}) {
  const [cartOpen, setCartOpen] = useState(false);
  const [cat, setCat] = useState("all");
  const [substituteFor, setSubstituteFor] = useState(null);

  const products = data?.products || [];
  const customers = data?.customers || [];

  const categories = useMemo(() => {
    const set = new Set(products.map((p) => p.category).filter(Boolean));
    return ["all", ...Array.from(set)];
  }, [products]);

  const q = (search || "").toLowerCase().trim();
  const filtered = useMemo(() => products.filter((p) => {
    if (cat !== "all" && p.category !== cat) return false;
    if (!q) return true;
    return [p.name, p.sku, p.color, p.motif, p.category].filter(Boolean).join(" ").toLowerCase().includes(q);
  }), [products, cat, q]);

  const cartCount = cart.reduce((s, it) => s + Number(it.quantity || 0), 0);
  const cartSubtotal = cart.reduce((s, it) => s + Number(it.product?.price || 0) * Number(it.quantity || 0), 0);

  return (
    <div data-testid="mobile-pos-view" className="mx-auto w-full max-w-[460px]">
      <div className="relative overflow-hidden rounded-2xl border border-[#E5E5EA] bg-[#F7F8FA] shadow-sm">
        {/* Mobile header */}
        <header className="sticky top-0 z-10 bg-gradient-to-br from-[#0058CC] to-[#6B219A] px-4 pb-3 pt-4 text-white">
          <div className="flex items-center gap-2">
            <Smartphone size={16} />
            <h1 className="text-[15px] font-bold">Mobile POS</h1>
            <span className="ml-auto rounded-md bg-white/15 px-2 py-0.5 text-[10px] font-semibold">Katalog cepat</span>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-xl bg-white px-3 py-2">
            <Search size={15} className="text-[#8E8E93]" />
            <input
              data-testid="mobile-pos-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cari produk, SKU, warna…"
              className="w-full bg-transparent text-[13px] text-[#1C1C1E] outline-none placeholder:text-[#8E8E93]"
            />
          </div>
        </header>

        {/* Category chips */}
        <div className="no-scrollbar flex gap-2 overflow-x-auto px-4 py-3">
          {categories.map((c) => (
            <button
              key={c}
              data-testid={`mobile-cat-${c}`}
              onClick={() => setCat(c)}
              className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-[12px] font-semibold transition ${
                cat === c ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3A3A3C]"
              }`}
            >
              {c === "all" ? "Semua" : c}
            </button>
          ))}
        </div>

        {/* Catalog grid */}
        <div className="px-4 pb-28">
          {!loading && <PosBestSellers entityId={entityId} onAdd={onAdd} />}
          {loading ? (
            <div className="grid grid-cols-2 gap-2.5">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-56 animate-pulse rounded-xl bg-[#ECEDF0]" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div data-testid="mobile-products-empty" className="flex flex-col items-center gap-2 py-16 text-center text-[#6B6B73]">
              <PackageX size={32} className="text-[#C7C7CC]" />
              <p className="text-[13px] font-medium">Tidak ada produk cocok.</p>
              <p className="text-[11.5px]">Coba kata kunci atau kategori lain.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2.5">
              {filtered.map((p) => (
                <MobileProductCard key={p.id} product={p} onAdd={onAdd} onInspect={onInspect} onShowSubstitutes={setSubstituteFor} />
              ))}
            </div>
          )}
        </div>

        {/* Sticky cart bar */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 p-3">
          <button
            data-testid="mobile-cart-bar"
            onClick={() => setCartOpen(true)}
            className="pointer-events-auto flex w-full items-center justify-between rounded-xl bg-[#1C1C1E] px-4 py-3 text-white shadow-lg disabled:opacity-60"
            disabled={cartCount === 0}
          >
            <span className="flex items-center gap-2 text-[13px] font-semibold">
              <span className="relative">
                <ShoppingCart size={17} />
                {cartCount > 0 && (
                  <span data-testid="mobile-cart-count" className="absolute -right-2 -top-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#FF3B30] px-1 text-[9px] font-bold">{cartCount}</span>
                )}
              </span>
              {cartCount === 0 ? "Keranjang kosong" : "Lihat Keranjang"}
            </span>
            <span data-testid="mobile-cart-subtotal" className="text-[14px] font-bold tabular-nums">{formatCurrency(cartSubtotal)}</span>
          </button>
        </div>
      </div>

      <MobileCartSheet
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        cart={cart}
        setCart={setCart}
        customers={customers}
        selectedCustomer={selectedCustomer}
        setSelectedCustomer={setSelectedCustomer}
        selectedAddress={selectedAddress}
        setSelectedAddress={setSelectedAddress}
        paymentTerms={paymentTerms}
        onSubmitOrder={onSubmitOrder}
        onAdd={onAdd}
        entityId={entityId}
      />

      {substituteFor && (
        <PosSubstitutesSheet
          product={substituteFor}
          entityId={entityId}
          onAdd={onAdd}
          onClose={() => setSubstituteFor(null)}
        />
      )}
    </div>
  );
}

export default MobilePOS;
