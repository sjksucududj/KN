import { Plus, Layers, Repeat, FlaskConical, Lock } from "lucide-react";
import { formatCurrency, formatQty } from "../../utils/formatters";
import { blocksOrder, lifecycleLabel } from "../../utils/lifecycle";
import { onImageError, productImage } from "../../utils/productImage";

/**
 * EPIC-VAR — kartu produk POS (group-aware & ringkas).
 * Kartu menampilkan grup produk (1+ varian). Klik gambar / "Tambah"("Pilih Varian")
 * / "Detail" semuanya membuka ProductQuickView (popup) — qty, satuan, varian, dan
 * detail stok dipindahkan ke popup.
 *
 * FASE F — varian yang masih di alur R&D (lifecycle ≠ produksi) ditandai jelas
 * "Belum boleh dijual" supaya sales tidak menabrak penolakan di ujung checkout.
 */
export function PosProductCard({ group, specialMap = {}, onOpen, reorder, rndEnforcement = "block" }) {
  const rep = group.base;
  const total = group.totalAvailable;
  const availState = total <= 0 ? "habis" : total <= 40 ? "low" : "ready";
  const availLabel = { habis: "Habis", low: "Stok rendah", ready: "Tersedia" }[availState];
  const availPill = { habis: "status-cancelled", low: "status-waiting_approval", ready: "status-confirmed" }[availState];
  const anySpecial = group.variants.some((v) => specialMap[v.id]?.has_special);
  // F1b — kartu juga menandai harga LANGGANAN pelanggan (bukan cuma harga khusus),
  // supaya sales tahu kenapa angka di kartu berbeda dari daftar harga umum.
  const anyCustomer = !anySpecial
    && group.variants.some((v) => specialMap[v.id]?.source === "customer");
  const isExclusive = group.variants.some((v) => v.exclusivity === "sales_tertentu");
  const blockedVariants = group.variants.filter((v) => blocksOrder(v, rndEnforcement));
  const allBlocked = blockedVariants.length > 0 && blockedVariants.length === group.variants.length;
  // F1b — kartu WAJIB menampilkan harga yang benar-benar akan dipakai. Dulu kartu
  // memasang lencana "Harga pelanggan" tetapi angkanya tetap harga UMUM, jadi layar
  // menjanjikan satu harga dan pesanan menyimpan harga lain.
  const effPrices = group.variants
    .map((v) => (specialMap[v.id]?.price != null ? Number(specialMap[v.id].price) : null))
    .filter((v) => v != null && v > 0);
  const hasEff = effPrices.length === group.variants.length && effPrices.length > 0;
  const effMin = hasEff ? Math.min(...effPrices) : group.priceMin;
  const effMax = hasEff ? Math.max(...effPrices) : group.priceMax;
  const listChanged = hasEff && (effMin !== group.priceMin || effMax !== group.priceMax);
  const priceText = group.isMulti && effMin !== effMax
    ? `${formatCurrency(effMin)} – ${formatCurrency(effMax)}`
    : formatCurrency(effMin);
  const listText = group.isMulti && group.priceMin !== group.priceMax
    ? `${formatCurrency(group.priceMin)} – ${formatCurrency(group.priceMax)}`
    : formatCurrency(group.priceMin);
  const open = (expand = false) => onOpen(group, expand);

  return (
    <article data-testid={`product-card-${rep.id}`} className="product-card flex flex-col">
      <button data-testid={`product-image-button-${rep.id}`} className="relative block w-full text-left" onClick={() => open(true)}>
        <img data-testid={`product-image-${rep.id}`} src={productImage(rep)} onError={onImageError} alt={group.name} className="product-image" loading="lazy" decoding="async" />
        <span data-testid={`product-grade-${rep.id}`} className="absolute right-2 top-2 rounded-md bg-black/85 px-1.5 py-0.5 text-[10px] font-bold text-white">{rep.grade}</span>
        {group.isMulti && (
          <span data-testid={`product-variant-count-${rep.id}`} className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-[#0058CC] px-2 py-0.5 text-[9.5px] font-bold text-white"><Layers size={10} /> {group.variants.length} varian</span>
        )}
        {anySpecial && (
          <span data-testid={`product-special-badge-${rep.id}`} className="absolute left-2 bottom-2 rounded-full bg-[#6B219A] px-2 py-0.5 text-[9.5px] font-bold text-white">Harga khusus</span>
        )}
        {anyCustomer && (
          <span data-testid={`product-customer-price-badge-${rep.id}`} className="absolute left-2 bottom-2 rounded-full bg-[#0058CC] px-2 py-0.5 text-[9.5px] font-bold text-white">Harga pelanggan</span>
        )}
        {allBlocked && (
          <span data-testid={`product-lifecycle-badge-${rep.id}`}
            className="absolute inset-x-2 top-1/2 -translate-y-1/2 rounded-md bg-[#8C4A00]/92 px-2 py-1 text-center text-[10px] font-bold uppercase tracking-wide text-white">
            {lifecycleLabel(rep)} · belum boleh dijual
          </span>
        )}
        {reorder && (
          <span className="absolute right-2 bottom-2 inline-flex items-center gap-1 rounded-full bg-black/80 px-2 py-0.5 text-[9.5px] font-bold text-white"><Repeat size={10} /> {reorder.reorder_count}×</span>
        )}
      </button>
      <div className="flex flex-1 flex-col p-3">
        <p data-testid={`product-sku-${rep.id}`} className="text-[10.5px] font-bold uppercase tracking-wide text-[#0058CC]">{group.isMulti ? rep.category : rep.sku}</p>
        {isExclusive && (
          <span data-testid={`product-exclusive-badge-${rep.id}`}
            className="mt-1 inline-flex w-fit items-center gap-1 rounded-full bg-[#6D4AC0] px-2 py-0.5 text-[9.5px] font-bold text-white">
            <Lock size={10} /> Eksklusif — PO sendiri
          </span>
        )}
        <h3 data-testid={`product-name-${rep.id}`} className="mt-0.5 text-[14px] font-semibold leading-tight line-clamp-2">{group.name}</h3>
        <p className="mt-0.5 text-[11px] text-[#6B6B73] line-clamp-1">{group.isMulti ? `${group.variants.length} pilihan warna/grade` : `${rep.category} • ${rep.color}`}</p>

        <div className="mt-2 flex items-center justify-between gap-2">
          <p data-testid={`product-price-${rep.id}`} className="text-[14px] font-bold tabular-nums text-[#1C1C1E]">
            {priceText}<span className="text-[10px] font-medium text-[#8E8E93]">/{rep.base_unit || "meter"}</span>
            {listChanged && (
              <span data-testid={`product-list-price-${rep.id}`} className="ml-1 block text-[10px] font-normal text-[#8E8E93] line-through">{listText}</span>
            )}
          </p>
          <span data-testid={`product-stock-badge-${rep.id}`} className={`status-pill ${availPill}`}>{availLabel}</span>
        </div>
        <p className="mt-1 text-[10.5px] text-[#6B6B73]"><b data-testid={`product-rolls-${rep.id}`} className="text-[#1C1C1E]">{group.totalRolls || 0} roll</b> / <b data-testid={`product-available-${rep.id}`} className="text-[#126E2C]">{formatQty(total)}</b> {rep.base_unit || "meter"} tersedia</p>

        <div className="mt-2">
          {allBlocked ? (
            <>
              <p data-testid={`product-not-orderable-${rep.id}`}
                className="mb-1.5 flex items-start gap-1 rounded-md bg-[#FFF6E5] px-2 py-1.5 text-[10.5px] font-semibold leading-snug text-[#8C4A00]">
                <FlaskConical size={12} className="mt-[1px] shrink-0" />
                Belum boleh dijual — {lifecycleLabel(rep)}. Selesaikan alur R&D
                (Spesifikasi → Sample → Rilis ke Produksi) di menu R&D & Desain.
              </p>
              {/* Tombol TIDAK dimatikan: pengguna harus bisa tahu ALASAN & LANGKAHNYA
                  (jalan buntu tanpa penjelasan = UX buruk). Klik → popup berisi
                  alasan lengkap + jalan keluar; keranjang tetap tidak bisa diisi. */}
              <button data-testid={`add-to-cart-button-${rep.id}`} className="secondary-button w-full"
                aria-disabled="true" data-orderable="false"
                title="Produk ini belum boleh dijual — klik untuk melihat alasan & langkah selanjutnya"
                onClick={() => open(true)}>
                Belum boleh dijual — lihat alasan
              </button>
            </>
          ) : (
            <button data-testid={`add-to-cart-button-${rep.id}`} className="primary-button w-full" data-orderable="true" disabled={availState === "habis"} onClick={() => open(true)}>
              <Plus size={13} /> {group.isMulti ? "Pilih Varian & Detail" : "Lihat Detail & Tambah"}
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
