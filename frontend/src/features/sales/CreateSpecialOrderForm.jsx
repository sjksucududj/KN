/**
 * Create Special Order Form
 * For custom products not in catalog
 */
import { useState, useEffect } from "react";
import axios, { API } from "../../services/apiClient";
import { AlertCircle, ArrowLeft, Loader2, Sparkles, X, Phone } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import useUomConversions from "../../hooks/useUomConversions";   // FASE U
import { uomSelectOptions } from "../../utils/uomCatalog";        // FASE U


export default function CreateSpecialOrderForm({ token, onCreated, onCancel }) {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // FASE U — satuan pesanan khusus dari MASTER SATUAN. Pesanan khusus justru yang
  // PALING sering memakai satuan tidak biasa (panel, lembar, set); daftar yang diketik
  // di layar memaksa pelanggan itu dicatat dalam satuan yang salah sejak awal.
  useUomConversions();
  const unitOpts = uomSelectOptions({ dimensions: ["length", "weight", "count"] });

  // Form state
  const [customerId, setCustomerId] = useState("");
  const [description, setDescription] = useState("");
  const [specifications, setSpecifications] = useState([{ key: "", value: "" }]);
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState("meter");
  const [targetPrice, setTargetPrice] = useState("");
  const [expectedDelivery, setExpectedDelivery] = useState("");
  const [notes, setNotes] = useState("");
  const [submitForApproval, setSubmitForApproval] = useState(true);

  useEffect(() => {
    loadCustomers();
  }, []);

  async function loadCustomers() {
    try {
      const res = await axios.get(`${API}/customers`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setCustomers(res.data.items || res.data || []);
    } catch (e) {
      console.error("Failed to load customers:", e);
    }
  }

  function addSpec() {
    setSpecifications([...specifications, { key: "", value: "" }]);
  }

  function updateSpec(i, field, value) {
    setSpecifications(prev => prev.map((s, idx) => idx === i ? { ...s, [field]: value } : s));
  }

  function removeSpec(i) {
    setSpecifications(prev => prev.filter((_, idx) => idx !== i));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!customerId) return setError("Pilih customer");
    if (!description) return setError("Deskripsi item wajib diisi");
    if (!quantity || parseFloat(quantity) <= 0) return setError("Quantity harus > 0");
    if (!targetPrice || parseFloat(targetPrice) < 0) return setError("Target price tidak valid");
    if (!expectedDelivery) return setError("Expected delivery wajib diisi");

    setLoading(true);
    setError(null);

    try {
      const specs = {};
      specifications.forEach(s => {
        if (s.key && s.value) specs[s.key] = s.value;
      });

      const payload = {
        customer_id: customerId,
        custom_item: {
          description,
          specifications: specs,
          quantity: parseFloat(quantity),
          unit,
          target_price: parseFloat(targetPrice),
          notes: ""
        },
        expected_delivery: expectedDelivery,
        notes,
        submit_for_approval: submitForApproval
      };

      const res = await axios.post(`${API}/special-orders`, payload, {
        headers: { Authorization: `Bearer ${token}` }
      });

      onCreated(res.data);
    } catch (e) {
      setError("Gagal membuat special order: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }

  const selectedCustomer = customers.find(c => c.id === customerId);

  return (
    <div data-testid="create-special-order-form" className="view-container">
      <button className="back-button" onClick={onCancel}>
        <ArrowLeft size={14} /> Batal
      </button>

      <div className="view-header">
        <div>
          <h1 className="view-title">
            <Sparkles size={20} /> Buat Pesanan Khusus Baru
          </h1>
          <p className="view-subtitle">
            Untuk produk custom yang belum ada di katalog
          </p>
        </div>
      </div>

      {error && (
        <div className="notice-bar danger">
          <AlertCircle size={14} /> {error}
          <button onClick={() => setError(null)}><X size={12} /></button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="form-card">
        {/* Customer */}
        <div className="form-group">
          <label className="form-label" htmlFor="sord-customer">
            Pelanggan <span className="req">*</span>
          </label>
          <KNSelect
            data-testid="sord-customer-select"
            className="form-select"
            value={customerId}
            onValueChange={setCustomerId}
            placeholder="-- Pilih Pelanggan --"
            options={[
              { value: "", label: "-- Pilih Pelanggan --" },
              ...customers.map(c => ({ value: c.id, label: `${c.name}${c.email ? ` (${c.email})` : ""}` })),
            ]}
          />
          {selectedCustomer && (
            <p className="form-help inline-flex items-center gap-1">
              {selectedCustomer.phone && <span className="inline-flex items-center gap-1"><Phone size={11} /> {selectedCustomer.phone}</span>}
              {selectedCustomer.city && ` • ${selectedCustomer.city}`}
            </p>
          )}
        </div>

        {/* Description */}
        <div className="form-group">
          <label className="form-label" htmlFor="sord-desc">
            Deskripsi Item Custom <span className="req">*</span>
          </label>
          <input
            id="sord-desc"
            data-testid="sord-description"
            type="text"
            className="form-input"
            placeholder="Contoh: Kain Batik Motif Custom Perusahaan"
            value={description}
            onChange={e => setDescription(e.target.value)}
            required
          />
        </div>

        {/* Specifications */}
        <div className="form-group">
          <label className="form-label">Spesifikasi Custom</label>
          <div className="space-y-2">
            {specifications.map((spec, i) => (
              <div key={i} className="flex gap-2 items-center">
                <input
                  data-testid={`spec-key-${i}`}
                  type="text"
                  className="form-input flex-1"
                  placeholder="Key (contoh: Warna)"
                  value={spec.key}
                  onChange={e => updateSpec(i, "key", e.target.value)}
                />
                <input
                  data-testid={`spec-value-${i}`}
                  type="text"
                  className="form-input flex-1"
                  placeholder="Nilai (contoh: Biru Navy)"
                  value={spec.value}
                  onChange={e => updateSpec(i, "value", e.target.value)}
                />
                <button
                  type="button"
                  className="icon-button danger"
                  onClick={() => removeSpec(i)}
                  disabled={specifications.length === 1}
                  data-testid={`remove-spec-${i}`}
                >
                  <X size={14} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="link-button"
              onClick={addSpec}
              data-testid="add-spec-btn"
            >
              + Tambah Spesifikasi
            </button>
          </div>
        </div>

        {/* Quantity & Unit */}
        <div className="form-row-2col">
          <div className="form-group">
            <label className="form-label" htmlFor="sord-qty">
              Jumlah <span className="req">*</span>
            </label>
            <input
              id="sord-qty"
              data-testid="sord-quantity"
              type="number"
              min="0.01"
              step="0.01"
              className="form-input"
              value={quantity}
              onChange={e => setQuantity(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="sord-unit">
              Satuan <span className="req">*</span>
            </label>
            <KNSelect
              data-testid="sord-unit"
              className="form-select"
              value={unit}
              onValueChange={setUnit}
              options={unitOpts}
            />
          </div>
        </div>

        {/* Target Price */}
        <div className="form-group">
          <label className="form-label" htmlFor="sord-price">
            Harga Target per Satuan (IDR) <span className="req">*</span>
          </label>
          <input
            id="sord-price"
            data-testid="sord-target-price"
            type="number"
            min="0"
            step="1"
            className="form-input"
            placeholder="0"
            value={targetPrice}
            onChange={e => setTargetPrice(e.target.value)}
            required
          />
          {quantity && targetPrice && (
            <p className="form-help">
              Total estimasi: <strong className="tabular-nums">Rp {new Intl.NumberFormat("id-ID").format(parseFloat(quantity) * parseFloat(targetPrice))}</strong>
            </p>
          )}
        </div>

        {/* Expected Delivery */}
        <div className="form-group">
          <label className="form-label" htmlFor="sord-delivery">
            Tanggal Perkiraan Pengiriman <span className="req">*</span>
          </label>
          <input
            id="sord-delivery"
            data-testid="sord-expected-delivery"
            type="date"
            className="form-input"
            value={expectedDelivery}
            onChange={e => setExpectedDelivery(e.target.value)}
            required
          />
        </div>

        {/* Notes */}
        <div className="form-group">
          <label className="form-label" htmlFor="sord-notes">
            Catatan Tambahan
          </label>
          <textarea
            id="sord-notes"
            data-testid="sord-notes"
            className="textarea"
            rows={3}
            placeholder="Catatan atau instruksi khusus..."
            value={notes}
            onChange={e => setNotes(e.target.value)}
          />
        </div>

        {/* Submit for approval */}
        <div className="form-group">
          <label className="form-check-label">
            <input
              type="checkbox"
              data-testid="sord-submit-for-approval"
              checked={submitForApproval}
              onChange={e => setSubmitForApproval(e.target.checked)}
            />
            {" "}Langsung kirim untuk persetujuan (jika total &gt; Rp 10.000.000)
          </label>
        </div>

        {/* Actions */}
        <div className="form-actions">
          <button type="button" className="secondary-button" onClick={onCancel}>
            Batal
          </button>
          <button
            type="submit"
            data-testid="sord-submit-btn"
            className="primary-button"
            disabled={loading}
          >
            {loading ? (
              <>
                <Loader2 size={14} className="spin" /> Menyimpan...
              </>
            ) : (
              <>
                <Sparkles size={14} /> Buat Pesanan Khusus
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
