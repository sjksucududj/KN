/**
 * ProductLifecycleCell (FASE F) — penanda **Tahap Produk** untuk layar Master Produk.
 *
 * KENAPA ADA: sejak Fase F produk punya `lifecycle`. Bila tahapnya belum `produksi`,
 * produk itu **tidak boleh** masuk SO/PR/PO (dijaga `services/rnd_gate.py`). Tanpa
 * penanda di Master Produk, pengguna akan bingung kenapa barangnya "hilang" dari
 * POS/pesanan. Komponen ini menjelaskannya + memberi jalan keluar yang benar:
 *   - produk lahir dari spesifikasi R&D → dirilis lewat dokumen spesifikasi (berjejak);
 *   - produk lama/manual → ubah tahap langsung (tetap tercatat di audit produk).
 */
import { useState } from "react";
import { Rocket } from "lucide-react";
import { lifecycleMeta } from "./rndMeta";
import { releaseProduct } from "./rndApi";

export default function ProductLifecycleCell({ product, canManage, onPatch, onDone }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const life = lifecycleMeta(product?.lifecycle);
  const REASON = "Dirilis dari Master Produk — sample & harga sudah beres";

  const release = async (e) => {
    e.stopPropagation();
    setBusy(true); setErr("");
    try {
      if (product.spec_id) await releaseProduct(product.spec_id, REASON);
      else await onPatch?.(product.id, { lifecycle: "produksi" });
      await onDone?.();
    } catch (ex) {
      setErr(ex?.response?.data?.detail || "Gagal merilis produk ke produksi.");
    } finally { setBusy(false); }
  };

  return (
    <span className="inline-flex flex-wrap items-center gap-1"
      data-testid={`product-lifecycle-${product?.id}`}>
      <span className="status-pill" title={life.sellable
        ? "Produk sah dipesan & dijual" : "Produk BELUM boleh masuk SO/PR/PO"}
        style={{ background: `${life.tone}1A`, color: life.tone }}>
        {life.label}
      </span>
      {!life.sellable && canManage && (
        <button className="secondary-button !px-1.5 !py-0.5 text-[10px]" disabled={busy}
          data-testid={`product-release-${product?.id}`} onClick={release}
          title={product?.spec_id
            ? "Rilis lewat spesifikasi R&D asalnya (berjejak)"
            : "Ubah tahap produk menjadi produksi"}>
          <Rocket size={10} /> {busy ? "…" : "Rilis ke produksi"}
        </button>
      )}
      {err && (
        <span className="text-[10px] font-semibold text-[#C0392B]"
          data-testid={`product-release-error-${product?.id}`}>{err}</span>
      )}
    </span>
  );
}
