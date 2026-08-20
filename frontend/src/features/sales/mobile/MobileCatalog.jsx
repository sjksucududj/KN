import { useMemo, useState } from "react";
import { Search, ShoppingCart, PackageX } from "lucide-react";
import { MobileProductCard } from "../../pos/mobile/MobileProductCard";
import { PosBestSellers } from "../../pos/PosBestSellers";
import { groupByTemplate } from "../../../utils/variants";
import MobileQuickView from "./MobileQuickView";
import { formatCurrency } from "../../../utils/formatters";
import { useEffectivePrices, pickPrice } from "../../../hooks/useEffectivePrices";

export default function MobileCatalog({ data, loading, onAdd, onInspect, entityId, cart, onOpenCart,
  selectedCustomer = null }) {
  const [search, setSearch] = useState("");
  const [cat, setCat] = useState("all");
  const [activeGroup, setActiveGroup] = useState(null);

  const products = useMemo(() => data?.products || [], [data]);
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
  const groups = useMemo(() => groupByTemplate(filtered), [filtered]);

  // F1b — harga efektif pelanggan (harga khusus → pelanggan → PT → umum) dalam SATU panggilan.
  const catalogIds = useMemo(() => groups.slice(0, 40).flatMap((g) => g.variants.map((v) => v.id)),
                             [groups]);
  const { priceMap } = useEffectivePrices({
    customerId: selectedCustomer?.id || "", entityId,
    productIds: catalogIds, delay: 450,
  });

  const cartCount = (cart || []).reduce((s, it) => s + Number(it.quantity || 0), 0);
  const cartSubtotal = (cart || []).reduce((s, it) => {
    const e = pickPrice(priceMap[it.product?.id], it.quantity);
    const unit = e && e.price != null ? Number(e.price) : Number(it.product?.price || 0);
    return s + unit * Number(it.quantity || 0);
  }, 0);

  const handleOpen = (group) => { setActiveGroup(group); onInspect && onInspect(group.base); };

  return (
    <div data-testid="mobile-catalog">
      {/* Sticky search + categories */}
      <div className="sticky top-0 z-10 border-b border-[#EFF0F2] bg-white px-3 py-2.5">
        <div className="flex items-center gap-2 rounded-xl bg-[#F2F3F5] px-3 py-2">
          <Search size={15} className="text-[#8E8E93]" />
          <input data-testid="mobile-catalog-search" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Cari produk, SKU, warna…"
            className="w-full bg-transparent text-[13px] text-[#1C1C1E] outline-none placeholder:text-[#8E8E93]" />
        </div>
        <div className="no-scrollbar mt-2 flex gap-2 overflow-x-auto">
          {categories.map((c) => (
            <button key={c} data-testid={`mobile-cat-${c}`} onClick={() => setCat(c)}
              className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-[12px] font-semibold transition ${cat === c ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3A3A3C]"}`}>
              {c === "all" ? "Semua" : c}
            </button>
          ))}
        </div>
      </div>

      <div className="px-3 pt-3" style={{ paddingBottom: cartCount > 0 ? "104px" : "16px" }}>
        {!loading && <PosBestSellers entityId={entityId} onAdd={onAdd} />}
        {loading ? (
          <div className="grid grid-cols-2 gap-2.5">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-56 animate-pulse rounded-xl bg-[#ECEDF0]" />)}
          </div>
        ) : groups.length === 0 ? (
          <div data-testid="mobile-catalog-empty" className="flex flex-col items-center gap-2 py-16 text-center m-muted">
            <PackageX size={32} className="text-[#C7C7CC]" />
            <p className="text-[13px] font-medium">Tidak ada produk cocok.</p>
            <p className="text-[11.5px]">Coba kata kunci atau kategori lain.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2.5">
            {groups.map((g) => (
              <MobileProductCard specialMap={priceMap} key={g.key} group={g} onOpen={handleOpen}
                rndEnforcement={data?.rnd_policy?.lifecycle_enforcement || "block"} />
            ))}
          </div>
        )}
      </div>

      {cartCount > 0 && (
        <div className="m-fab-bar">
          <button data-testid="mobile-catalog-cart-bar" onClick={onOpenCart}
            className="m-press flex w-full items-center justify-between rounded-xl bg-[#1C1C1E] px-4 py-3 text-white shadow-lg">
            <span className="flex items-center gap-2 text-[13px] font-semibold">
              <ShoppingCart size={17} /> Lihat Keranjang ({cartCount})
            </span>
            <span className="text-[14px] font-bold tabular-nums">{formatCurrency(cartSubtotal)}</span>
          </button>
        </div>
      )}

      {activeGroup && (
        <MobileQuickView specialMap={priceMap} group={activeGroup} entityId={entityId} onAdd={onAdd}
          rndEnforcement={data?.rnd_policy?.lifecycle_enforcement || "block"}
          onClose={() => setActiveGroup(null)} />
      )}
    </div>
  );
}
