import { useEffect, useState } from "react";
import { X, Send, BadgePercent, ShieldCheck } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatCurrency } from "../../utils/formatters";

/**
 * Shortcut ajukan Harga Khusus langsung dari checkout (tanpa navigasi ke menu
 * Approval Harga). Tetap lewat governance: sales -> "Ajukan untuk Approval"
 * (status pending). Admin/manager (canApprove) juga bisa "Setujui & Terapkan"
 * agar harga khusus langsung berlaku di order berjalan.
 */
export default function RequestSpecialPriceModal({
  open, onClose, product, customer, entityId = "", defaultQty = 0, canApprove = false, onSubmitted,
}) {
  const normalPrice = Number(product?.price || 0);
  const [price, setPrice] = useState("");
  const [minQty, setMinQty] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (open) {
      setPrice(""); setMinQty(defaultQty ? String(Math.round(defaultQty)) : "");
      setValidUntil(""); setReason(""); setErr(""); setBusy(false);
    }
  }, [open, product?.id]); // eslint-disable-line

  if (!open || !product) return null;

  const priceNum = parseFloat(price);
  const pct = normalPrice > 0 && priceNum > 0 ? Math.round((1 - priceNum / normalPrice) * 1000) / 10 : 0;

  const validate = () => {
    if (!customer?.id) { setErr("Pilih customer dulu."); return false; }
    if (!(priceNum > 0)) { setErr("Harga khusus harus lebih dari 0."); return false; }
    if (priceNum >= normalPrice) { setErr("Harga khusus harus lebih rendah dari harga normal."); return false; }
    return true;
  };

  const create = async () => {
    const res = await axios.post(`${API}/price-approvals`, {
      customer_id: customer.id, product_id: product.id, requested_price: priceNum,
      min_quantity: parseFloat(minQty) || 0, valid_until: validUntil || "",
      reason: reason || "", submit_now: true, entity_id: entityId || "",
    });
    return res.data;
  };

  const handleRequest = async () => {
    if (!validate()) return;
    setBusy(true); setErr("");
    try {
      await create();
      onSubmitted?.({ productId: product.id, applied: false,
        message: `Pengajuan harga khusus ${formatCurrency(priceNum)} terkirim — menunggu persetujuan.` });
      onClose();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal mengajukan harga khusus."); }
    finally { setBusy(false); }
  };

  const handleApprove = async () => {
    if (!validate()) return;
    setBusy(true); setErr("");
    try {
      const created = await create();
      await axios.post(`${API}/price-approvals/${created.id}/approve`, { decision_notes: "Disetujui saat checkout" });
      onSubmitted?.({ productId: product.id, applied: true,
        message: `Harga khusus ${formatCurrency(priceNum)} disetujui & diterapkan.` });
      onClose();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyetujui harga khusus."); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4" data-testid="request-special-price-modal">
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <div className="flex items-center gap-2">
            <BadgePercent size={16} className="text-[#6B219A]" />
            <h3 className="text-[13px] font-bold text-[#1C1C1E]">Minta Harga Khusus</h3>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Tutup" data-testid="rsp-close"><X size={14} /></button>
        </div>

        <div className="grid gap-3 p-4">
          <div className="rounded-md bg-[#FAFBFC] px-3 py-2 text-[11px]">
            <p className="font-semibold text-[#1C1C1E]">{product.name}</p>
            <p className="text-[#6B6B73]">{product.sku} · Pelanggan: <b>{customer?.name || "—"}</b></p>
            <p className="text-[#6B6B73]">Harga normal: <b>{formatCurrency(normalPrice)}</b> / {product.base_unit || "meter"}</p>
          </div>

          <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
            Harga Khusus / unit
            <input data-testid="rsp-price" type="number" min="0" className="field tabular-nums"
              placeholder="cth: 150000" value={price} onChange={(e) => setPrice(e.target.value)} />
            {priceNum > 0 && priceNum < normalPrice && (
              <span className="text-[10px] font-bold text-[#1B7E3B]">Diskon {pct}% dari harga normal</span>
            )}
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
              Qty Minimum
              <input data-testid="rsp-minqty" type="number" min="0" className="field tabular-nums"
                placeholder="0" value={minQty} onChange={(e) => setMinQty(e.target.value)} />
            </label>
            <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
              Berlaku Sampai
              <input data-testid="rsp-validuntil" type="date" className="field"
                value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </label>
          </div>

          <label className="grid gap-1 text-[11px] font-semibold text-[#6B6B73]">
            Alasan / Catatan
            <textarea data-testid="rsp-reason" className="field min-h-[52px] text-[12px]"
              placeholder="Konteks negosiasi harga…" value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>

          {err && <p data-testid="rsp-error" className="text-[11px] font-semibold text-[#A8221A]">{err}</p>}

          {!canApprove && (
            <p className="rounded-md bg-[#FFF7EC] px-2 py-1.5 text-[10px] text-[#9A5B00]">
              Pengajuan akan berstatus <b>menunggu</b> & baru berlaku setelah disetujui manager/admin.
            </p>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button data-testid="rsp-cancel" onClick={onClose} disabled={busy}
            className="rounded-md border border-[#E5E5EA] px-4 py-1.5 text-[12px] font-semibold text-[#3C3C43] disabled:opacity-50">
            Batal
          </button>
          <button data-testid="rsp-request" onClick={handleRequest} disabled={busy}
            className="flex items-center gap-1.5 rounded-md border border-[#6B219A] px-4 py-1.5 text-[12px] font-bold text-[#6B219A] disabled:opacity-50">
            <Send size={13} /> Ajukan untuk Persetujuan
          </button>
          {canApprove && (
            <button data-testid="rsp-approve" onClick={handleApprove} disabled={busy}
              className="flex items-center gap-1.5 rounded-md bg-[#6B219A] px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50">
              <ShieldCheck size={13} /> Setujui & Terapkan
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
