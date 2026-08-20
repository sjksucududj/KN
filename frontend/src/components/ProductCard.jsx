import { Plus } from "lucide-react";
import { formatCurrency, formatQty } from "../utils/formatters";

export function ProductCard({ product, onAdd, onInspect }) {
  const lowStock = product.available_qty <= 40;
  
  return (
    <article data-testid={`product-card-${product.id}`} className="product-card">
      <button 
        data-testid={`product-image-button-${product.id}`} 
        className="block w-full text-left" 
        onClick={() => onInspect(product)}
      >
        <img 
          data-testid={`product-image-${product.id}`} 
          src={product.image} 
          alt={product.name} 
          className="product-image" 
        />
      </button>
      <div className="p-3">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p 
              data-testid={`product-sku-${product.id}`} 
              className="text-[10.5px] font-bold uppercase tracking-wide text-[#0058CC]"
            >
              {product.sku}
            </p>
            <h3 
              data-testid={`product-name-${product.id}`} 
              className="mt-0.5 text-[14px] font-semibold leading-tight line-clamp-2"
            >
              {product.name}
            </h3>
          </div>
          <span 
            data-testid={`product-grade-${product.id}`} 
            className="rounded-md bg-black px-1.5 py-0.5 text-[10px] font-bold text-white"
          >
            {product.grade}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-1.5 text-center">
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-1.5 py-1">
            <p className="text-[9.5px] font-bold uppercase text-[#6B6B73]">Avail</p>
            <p 
              data-testid={`product-available-${product.id}`} 
              className="text-[12.5px] font-bold text-[#126E2C]"
            >
              {formatQty(product.available_qty)}
            </p>
          </div>
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-1.5 py-1">
            <p className="text-[9.5px] font-bold uppercase text-[#6B6B73]">Resv</p>
            <p 
              data-testid={`product-reserved-${product.id}`} 
              className="text-[12.5px] font-bold text-[#6B219A]"
            >
              {formatQty(product.reserved_qty)}
            </p>
          </div>
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-1.5 py-1">
            <p className="text-[9.5px] font-bold uppercase text-[#6B6B73]">Harga</p>
            <p 
              data-testid={`product-price-${product.id}`} 
              className="text-[11.5px] font-bold tabular-nums"
            >
              {formatCurrency(product.price)}
            </p>
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between gap-2">
          <span 
            data-testid={`product-stock-badge-${product.id}`} 
            className={`status-pill ${lowStock ? "status-waiting_approval" : "status-confirmed"}`}
          >
            {lowStock ? "Low stock" : "Ready"}
          </span>
          <button 
            data-testid={`add-to-cart-button-${product.id}`} 
            className="primary-button" 
            onClick={() => onAdd(product)}
          >
            <Plus size={13} /> Reserve
          </button>
        </div>
      </div>
    </article>
  );
}
