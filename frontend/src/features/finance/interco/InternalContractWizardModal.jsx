/**
 * FASE G-6 — Wizard **KONTRAK INTERNAL** (`partner_kind="entity"`).
 *
 * Keuangan bisa menerbitkan harga tetap PT-A → PT-B untuk barang tertentu
 * tanpa membuka layar Kontrak umum. Setelah tersimpan, transaksi antar-PT
 * dengan `pricing_mode="fixed_price"` untuk barang itu langsung SIAP DITERBITKAN.
 */
import { useEffect, useState } from "react";
import { X, Handshake } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { KNSelect } from "../../../components/KNSelect";
import ErrorNotice from "../../../components/ErrorNotice";
import { apiErrorText } from "../../../utils/apiError";

export default function InternalContractWizardModal({
  entities = [], sellerEntityId = "", buyerEntityId = "",
  onClose, onCreated,
}) {
  const [seller, setSeller] = useState(sellerEntityId);
  const [buyer, setBuyer]   = useState(buyerEntityId);
  const [products, setProducts] = useState([]);
  const [productId, setProductId] = useState("");
  const [rate, setRate] = useState("");
  const [validFrom, setValidFrom] = useState(new Date().toISOString().slice(0, 10));
  const [validTo, setValidTo] = useState("");
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    axios.get(`${API}/products`, { params: { limit: 500 } })
      .then((r) => setProducts(Array.isArray(r.data) ? r.data : (r.data.items || [])))
      .catch(() => setProducts([]));
  }, []);

  const entOptions = entities
    .filter((e) => e.status !== "inactive")
    .map((e) => ({ value: e.id, label: e.short_name || e.legal_name || e.name || e.id }));
  const prodOptions = products.map((p) => ({
    value: p.id,
    label: `${p.sku || ""} · ${p.name || ""}`,
  }));

  const submit = async () => {
    setErr("");
    if (!seller || !buyer) { setErr("PT penjual & pembeli wajib dipilih."); return; }
    if (seller === buyer) { setErr("PT penjual & pembeli harus berbeda."); return; }
    if (!productId) { setErr("Produk wajib dipilih."); return; }
    const rateNum = parseFloat(rate);
    if (!rateNum || rateNum <= 0) { setErr("Harga per unit harus > 0."); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/supplier-contracts`, {
        contract_type: "internal",
        entity_id: seller,
        partner_id: buyer,
        product_id: productId,
        tariff_basis: "lumpsum",
        tariff_rate: rateNum,
        tariff_qty_source: "output",
        valid_from: validFrom,
        valid_to: validTo,
        title: title || `Harga internal ${seller}→${buyer}`,
        notes,
        status: "active",
      }, { headers: { "X-Entity-Id": seller } });
      onCreated?.();
    } catch (e) { setErr(apiErrorText(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="interco-contract-modal">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[92vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5E5EA]">
          <div className="flex items-center gap-3">
            <Handshake size={18} className="text-[#0058CC]" />
            <div>
              <h2 className="text-lg font-semibold text-[#1D1D1F]">Kontrak Internal</h2>
              <p className="text-xs text-[#6E6E73] mt-0.5">
                Tetapkan harga jual antar-PT untuk satu produk. Transaksi ber-mode
                <b className="mx-1">Harga tetap</b>
                setelahnya akan otomatis memakai harga ini.
              </p>
            </div>
          </div>
          <button onClick={onClose} data-testid="interco-contract-close" className="p-1.5 hover:bg-[#F2F2F5] rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {err && <ErrorNotice message={err} onDismiss={() => setErr("")} />}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="PT Penjual (penerbit kontrak)">
              <KNSelect value={seller} onChange={setSeller} options={entOptions} data-testid="interco-contract-seller" />
            </Field>
            <Field label="PT Pembeli (partner)">
              <KNSelect value={buyer} onChange={setBuyer} options={entOptions} data-testid="interco-contract-buyer" />
            </Field>
            <Field label="Produk">
              <KNSelect value={productId} onChange={setProductId} options={prodOptions} data-testid="interco-contract-product" />
            </Field>
            <Field label="Harga per unit (Rp)">
              <input
                type="number" min="0" step="0.01" value={rate}
                onChange={(e) => setRate(e.target.value)}
                data-testid="interco-contract-rate"
                className="w-full px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg focus:outline-none focus:border-[#0058CC]"
              />
            </Field>
            <Field label="Berlaku sejak">
              <input
                type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)}
                data-testid="interco-contract-valid-from"
                className="w-full px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg"
              />
            </Field>
            <Field label="Berlaku hingga (opsional)">
              <input
                type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)}
                data-testid="interco-contract-valid-to"
                className="w-full px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg"
              />
            </Field>
          </div>

          <Field label="Judul (opsional)">
            <input
              value={title} onChange={(e) => setTitle(e.target.value)}
              data-testid="interco-contract-title"
              className="w-full px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg"
            />
          </Field>
          <Field label="Catatan (opsional)">
            <textarea
              value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
              data-testid="interco-contract-notes"
              className="w-full px-3 py-2 text-sm border border-[#E5E5EA] rounded-lg"
            />
          </Field>
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-[#E5E5EA] bg-[#FAFAFB]">
          <button onClick={onClose} data-testid="interco-contract-cancel" className="px-4 py-2 text-sm rounded-lg text-[#3C3C43] hover:bg-[#F2F2F5]">
            Batal
          </button>
          <button
            onClick={submit} disabled={busy}
            data-testid="interco-contract-submit"
            className="px-4 py-2 text-sm rounded-lg bg-[#0F172A] text-white hover:bg-black disabled:opacity-50"
          >
            {busy ? "Menerbitkan..." : "Terbitkan Kontrak Internal"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-[#3C3C43] mb-1">{label}</label>
      {children}
    </div>
  );
}
