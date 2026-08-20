/**
 * FASE G-6 — Wizard TERBITKAN TRANSAKSI ANTAR-PT.
 *
 * Bawaan: mode harga `fixed_price` (harga dari kontrak internal). Bila barangnya
 * belum berharga di kontrak aktif → backend MENOLAK dengan kalimat menuntun,
 * dan user bisa beralih ke mode manual (override unit_price) tanpa kontrak.
 */
import { useEffect, useState } from "react";
import { X, Plus, Trash2 } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { KNSelect } from "../../../components/KNSelect";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency } from "../../../utils/formatters";
import { apiErrorText } from "../../../utils/apiError";
import { PRICING_MODES, PPN_MODES } from "./intercoApi";

export default function IntercoCreateModal({
  entities = [], currentEntityId = "", onClose, onCreated,
}) {
  const [seller, setSeller] = useState(currentEntityId || (entities[0]?.id || ""));
  const [buyer, setBuyer] = useState("");
  const [pricingMode, setPricingMode] = useState("fixed_price");
  const [ppnMode, setPpnMode] = useState("ikut_pkp");
  const [items, setItems] = useState([{ product_id: "", quantity: 1, unit_price: "" }]);
  const [products, setProducts] = useState([]);
  const [submitNow, setSubmitNow] = useState(true);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    axios.get(`${API}/products`, { params: { limit: 500 } })
      .then((r) => {
        const list = Array.isArray(r.data) ? r.data : (r.data.items || []);
        setProducts(list);
      })
      .catch(() => setProducts([]));
  }, []);

  const entOptions = entities
    .filter((e) => e.status !== "inactive")
    .map((e) => ({
      value: e.id,
      label: e.short_name || e.legal_name || e.name || e.id,
    }));

  const prodOptions = products.map((p) => ({
    value: p.id,
    label: `${p.sku || ""} · ${p.name || ""}`,
  }));

  const setItem = (i, patch) =>
    setItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));
  const addLine = () =>
    setItems((prev) => [...prev, { product_id: "", quantity: 1, unit_price: "" }]);
  const removeLine = (i) =>
    setItems((prev) => prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev);

  const subtotalPreview = items.reduce(
    (s, it) => s + (parseFloat(it.quantity) || 0) * (parseFloat(it.unit_price) || 0), 0);

  const submit = async () => {
    setErr("");
    if (!seller || !buyer) { setErr("PT penjual dan pembeli wajib dipilih."); return; }
    if (seller === buyer) { setErr("PT penjual dan pembeli harus berbeda."); return; }
    const cleanItems = items
      .filter((it) => it.product_id && (parseFloat(it.quantity) || 0) > 0)
      .map((it) => ({
        product_id: it.product_id,
        quantity: parseFloat(it.quantity),
        unit_price: it.unit_price === "" ? null : parseFloat(it.unit_price),
      }));
    if (cleanItems.length === 0) {
      setErr("Minimal satu baris produk dengan jumlah > 0."); return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/interco/transactions`, {
        seller_entity_id: seller,
        buyer_entity_id: buyer,
        pricing_mode: pricingMode,
        ppn_mode: ppnMode,
        items: cleanItems,
        submit_now: submitNow,
        notes,
      });
      onCreated?.();
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="interco-create-modal">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5E5EA]">
          <div>
            <h2 className="text-lg font-semibold text-[#1D1D1F]">Transaksi Antar-PT Baru</h2>
            <p className="text-xs text-[#6E6E73] mt-0.5">Dokumen kembar akan terbit di kedua PT.</p>
          </div>
          <button onClick={onClose} data-testid="interco-create-close" className="p-1.5 hover:bg-[#F2F2F5] rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {err && <ErrorNotice message={err} onDismiss={() => setErr("")} />}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="PT Penjual" hint="menerbitkan Pesanan Jual + Surat Jalan + Faktur internal">
              <KNSelect value={seller} onChange={setSeller} options={entOptions} data-testid="interco-create-seller" />
            </Field>
            <Field label="PT Pembeli" hint="menerbitkan Pesanan Beli internal + Tagihan internal">
              <KNSelect value={buyer} onChange={setBuyer} options={entOptions} data-testid="interco-create-buyer" />
            </Field>
            <Field label="Mode Harga" hint="Harga tetap: diambil dari kontrak internal yang aktif">
              <KNSelect value={pricingMode} onChange={setPricingMode} options={PRICING_MODES} data-testid="interco-create-pricing" />
            </Field>
            <Field label="Mode PPN" hint="Ikut PKP: mengikuti status PKP PT penjual">
              <KNSelect value={ppnMode} onChange={setPpnMode} options={PPN_MODES} data-testid="interco-create-ppn" />
            </Field>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-[#1D1D1F]">Barang</h3>
              <button
                onClick={addLine}
                data-testid="interco-create-add-line"
                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-md border border-[#E5E5EA] hover:bg-[#F2F2F5]"
              >
                <Plus size={12} /> Tambah baris
              </button>
            </div>
            <div className="space-y-2">
              {items.map((it, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-start" data-testid={`interco-create-line-${i}`}>
                  <div className="col-span-6">
                    <KNSelect
                      value={it.product_id}
                      onChange={(v) => setItem(i, { product_id: v })}
                      options={prodOptions}
                      placeholder="Pilih produk"
                    />
                  </div>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={it.quantity}
                    onChange={(e) => setItem(i, { quantity: e.target.value })}
                    placeholder="Qty"
                    data-testid={`interco-create-qty-${i}`}
                    className="col-span-2 px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg focus:outline-none focus:border-[#0058CC]"
                  />
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={it.unit_price}
                    onChange={(e) => setItem(i, { unit_price: e.target.value })}
                    placeholder="Harga (auto dari kontrak bila kosong)"
                    data-testid={`interco-create-price-${i}`}
                    className="col-span-3 px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg focus:outline-none focus:border-[#0058CC]"
                  />
                  <button
                    onClick={() => removeLine(i)}
                    disabled={items.length <= 1}
                    className="col-span-1 p-2 text-[#8E8E93] hover:text-[#9B1C1C] disabled:opacity-30"
                    data-testid={`interco-create-remove-${i}`}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-3 text-right text-sm text-[#6E6E73]">
              Perkiraan subtotal: <span className="font-medium text-[#1D1D1F] tabular-nums">{formatCurrency(subtotalPreview)}</span>
              <span className="text-xs ml-1">(final dihitung backend)</span>
            </div>
          </div>

          <Field label="Catatan (opsional)">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              data-testid="interco-create-notes"
              className="w-full px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg focus:outline-none focus:border-[#0058CC]"
            />
          </Field>

          <label className="flex items-center gap-2 text-sm text-[#3C3C43] cursor-pointer">
            <input
              type="checkbox"
              checked={submitNow}
              onChange={(e) => setSubmitNow(e.target.checked)}
              data-testid="interco-create-submit-now"
            />
            Langsung dikonfirmasi (post jurnal & saldo antar-PT segera bergerak)
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-[#E5E5EA] bg-[#FAFAFB]">
          <button onClick={onClose} data-testid="interco-create-cancel" className="px-4 py-2 text-sm rounded-lg text-[#3C3C43] hover:bg-[#F2F2F5]">
            Batal
          </button>
          <button
            onClick={submit}
            disabled={busy}
            data-testid="interco-create-submit"
            className="px-4 py-2 text-sm rounded-lg bg-[#0F172A] text-white hover:bg-black disabled:opacity-50"
          >
            {busy ? "Menerbitkan..." : "Terbitkan Transaksi"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-[#3C3C43] mb-1">{label}</label>
      {children}
      {hint && <div className="text-xs text-[#8E8E93] mt-1">{hint}</div>}
    </div>
  );
}
