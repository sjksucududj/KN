/** Sub-fase 1.11 — Create return form. */
import { useState, useEffect } from "react";
import axios, { API } from "../../services/apiClient";
import { AlertCircle, ArrowLeft, CalendarClock, Loader2, Plus, RotateCcw, ShieldCheck, Trash2, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import useUomConversions from "../../hooks/useUomConversions";   // FASE U
import { uomSelectOptions } from "../../utils/uomCatalog";        // FASE U


export default function CreateReturnForm({ orders, token, onCreated, onCancel,
                                           onLoadOrders, variant = "page" }) {
  // FASE P4 — `variant="modal"`: lepas chrome halaman (tombol kembali + judul besar)
  // karena FormModal sudah menyediakannya; tanpa ini pengguna melihat DUA judul.
  const isModal = variant === "modal";
  // FASE U — satuan baris retur dari MASTER SATUAN. Pesanan ber-satuan `panel` dulu
  // tidak bisa diretur dalam satuan yang sama (pilihannya hanya meter/kg/roll/pcs),
  // jadi petugas memilih satuan yang salah dan angka retur tidak bisa dicocokkan
  // dengan pesanan asalnya.
  useUomConversions();
  const unitOpts = uomSelectOptions({ dimensions: ["length", "weight", "count"] });
  const [orderId, setOrderId]       = useState("");
  const [returnType, setReturnType] = useState("retur");
  const [items, setItems]           = useState([{ product_id: "", product_name: "", quantity_returned: "", unit: "meter", reason: "", condition: "ok" }]);
  const [notes, setNotes]           = useState("");
  const [submitNow, setSubmitNow]   = useState(true);
  const [saving, setSaving]         = useState(false);
  const [error, setError]           = useState(null);
  const [eligibility, setEligibility] = useState(null);
  const [checking, setChecking]     = useState(false);

  useEffect(() => { onLoadOrders(); }, []); // eslint-disable-line

  // R0 — cek kelayakan & deadline retur tiap kali order/tipe berubah.
  useEffect(() => {
    if (!orderId) { setEligibility(null); return; }
    let cancelled = false;
    (async () => {
      setChecking(true);
      try {
        const res = await axios.get(`${API}/sales-return-policies/eligibility`, {
          params: { order_id: orderId, return_type: returnType },
        });
        if (!cancelled) setEligibility(res.data);
      } catch {
        if (!cancelled) setEligibility(null);
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => { cancelled = true; };
  }, [orderId, returnType]);

  function handleOrderChange(id) {
    setOrderId(id);
    const order = orders.find(o => o.id === id);
    if (order?.items?.length) {
      setItems(order.items.map(li => ({
        product_id:        li.product_id || "",
        product_name:      li.product_name || "",
        quantity_returned: "",
        unit:              li.unit || "meter",
        reason:            "",
        condition:         "ok",
      })));
    }
  }

  const updateItem = (i, f, v) => setItems(prev => prev.map((it, idx) => idx === i ? { ...it, [f]: v } : it));
  const addItem    = () => setItems(prev => [...prev, { product_id: "", product_name: "", quantity_returned: "", unit: "meter", reason: "", condition: "ok" }]);
  const removeItem = (i) => setItems(prev => prev.filter((_, idx) => idx !== i));

  async function handleSubmit(e) {
    e.preventDefault();
    if (!orderId) return setError("Pilih pesanan terlebih dahulu");
    const validItems = items.filter(it => it.product_id && parseFloat(it.quantity_returned) > 0);
    if (!validItems.length) return setError("Minimal 1 item dengan kuantitas > 0");
    setSaving(true); setError(null);
    try {
      const res = await axios.post(`${API}/sales-returns`, {
        order_id: orderId, return_type: returnType,
        items: validItems.map(it => ({ ...it, quantity_returned: parseFloat(it.quantity_returned) })),
        notes, submit_now: submitNow,
      }, { headers: { Authorization: `Bearer ${token}` } });
      onCreated(res.data);
    } catch (err) {
      setError("Gagal membuat return: " + (err.response?.data?.detail || err.message));
    } finally { setSaving(false); }
  }

  return (
    <div data-testid="create-return-form" className={isModal ? "" : "view-container"}>
      {!isModal && (
        <button className="back-button" onClick={onCancel}><ArrowLeft size={14} /> Batal</button>
      )}

      {!isModal && (
        <div className="view-header">
          <div>
            <h1 className="view-title">Buat Return Baru</h1>
            <p className="view-subtitle">Retur barang, Barang Sisa (BS), penggantian, komplain & garansi (purna jual) dari pelanggan</p>
          </div>
        </div>
      )}

      {error && (
        <div className="notice-bar danger">
          <AlertCircle size={14} /> {error}
          <button onClick={() => setError(null)}><X size={12} /></button>
        </div>
      )}

      <form onSubmit={handleSubmit} className={isModal ? "" : "form-card"}>
        <div className="form-row-2col">
          <div className="form-group">
            <label className="form-label" htmlFor="ret-order">Pesanan (SO) <span className="req">*</span></label>
            <KNSelect
              data-testid="return-order-select"
              className="form-select"
              value={orderId}
              onValueChange={handleOrderChange}
              placeholder="-- Pilih pesanan --"
              options={[
                { value: "", label: "-- Pilih pesanan --" },
                ...orders.map(o => ({ value: o.id, label: `${o.number} — ${o.customer_name} (${o.status})` })),
              ]}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="ret-type">Tipe Return <span className="req">*</span></label>
            <KNSelect
              data-testid="return-type-select"
              className="form-select"
              value={returnType}
              onValueChange={setReturnType}
              options={[
                { value: "retur", label: "Retur (pelanggan kembalikan barang)" },
                { value: "bs", label: "Barang Sisa — BS (sisa penggunaan)" },
                { value: "penggantian", label: "Penggantian (cacat / salah kirim)" },
                { value: "komplain", label: "Komplain (keluhan kualitas)" },
                { value: "garansi", label: "Garansi (klaim jaminan)" },
              ]}
            />
          </div>
        </div>

        {/* R0 — Banner kelayakan & deadline retur (kebijakan retur jual) */}
        {orderId && (
          <div data-testid="return-eligibility-banner"
            className={`rounded-md border px-3 py-2.5 text-[11.5px] ${
              eligibility?.blocked ? "border-[#E5484D] bg-[#FDECEC]"
                : eligibility?.within_window === false ? "border-[#A05000] bg-[#FFF6E9]"
                : "border-[#EFF0F2] bg-[#FAFBFC]"}`}>
            {checking ? (
              <span className="flex items-center gap-1.5 text-[#6B6B73]"><Loader2 size={12} className="spin" /> Mengecek kebijakan retur...</span>
            ) : eligibility ? (
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="flex items-center gap-1.5 font-semibold">
                    <ShieldCheck size={13} className="text-[#0058CC]" />
                    Kebijakan: {eligibility.policy?.name || "Default"}
                  </span>
                  <span className="flex items-center gap-1.5 tabular-nums" data-testid="eligibility-deadline">
                    <CalendarClock size={12} className="text-[#6B6B73]" />
                    {eligibility.deadline
                      ? <>Deadline retur: <b>{String(eligibility.deadline).slice(0, 10)}</b>
                          {eligibility.days_remaining != null && ` (${eligibility.days_remaining} hari lagi)`}</>
                      : `Window ${eligibility.window_days} hari (tgl kirim tidak diketahui)`}
                  </span>
                  {eligibility.require_inspection && (
                    <span className="status-pill pill-warning">Inspeksi wajib setelah disetujui</span>
                  )}
                </div>
                {(eligibility.warnings || []).map((w, i) => (
                  <p key={i} className="text-[#A05000] flex items-center gap-1" data-testid={`eligibility-warning-${i}`}>
                    <AlertCircle size={11} /> {w}
                  </p>
                ))}
                {eligibility.blocked && (
                  <p className="text-[#E5484D] font-semibold">Kebijakan memblokir retur di luar window. Hubungi manajer bila tetap perlu diproses.</p>
                )}
              </div>
            ) : (
              <span className="text-[#6B6B73]">Kebijakan retur tidak dapat dievaluasi untuk pesanan ini.</span>
            )}
          </div>
        )}

        <div className="form-group">
          <label className="form-label">Item yang Diretur <span className="req">*</span></label>
          <div className="form-items-table">
            <div className="form-items-header">
              <span>Produk</span><span>Qty</span><span>Satuan</span><span>Kondisi</span><span>Alasan</span><span></span>
            </div>
            {items.map((it, i) => (
              <div key={i} className="form-items-row" data-testid={`return-item-row-${i}`}>
                <input data-testid={`item-product-${i}`} className="form-input" placeholder="ID Produk"
                  value={it.product_id} onChange={e => updateItem(i, "product_id", e.target.value)} />
                <input data-testid={`item-qty-${i}`} className="form-input text-right" type="number"
                  min="0.01" step="0.01" placeholder="0.00"
                  value={it.quantity_returned} onChange={e => updateItem(i, "quantity_returned", e.target.value)} />
                <KNSelect data-testid={`item-unit-${i}`} className="form-select" value={it.unit}
                  onValueChange={v => updateItem(i, "unit", v)}
                  options={unitOpts}
                />
                <KNSelect data-testid={`item-condition-${i}`} className="form-select" value={it.condition}
                  onValueChange={v => updateItem(i, "condition", v)}
                  options={[
                    { value: "ok", label: "Baik" },
                    { value: "damaged", label: "Rusak" },
                  ]}
                />
                <input data-testid={`item-reason-${i}`} className="form-input" placeholder="Alasan..."
                  value={it.reason} onChange={e => updateItem(i, "reason", e.target.value)} />
                <button type="button" className="icon-button danger" onClick={() => removeItem(i)}
                  disabled={items.length === 1} data-testid={`remove-item-${i}`}>
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
            <button type="button" className="link-button" onClick={addItem} data-testid="add-return-item-btn">
              <Plus size={12} /> Tambah Item
            </button>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="ret-notes">Catatan</label>
          <textarea id="ret-notes" data-testid="return-notes-input" className="textarea" rows={2}
            placeholder="Keterangan tambahan..." value={notes} onChange={e => setNotes(e.target.value)} />
        </div>

        <div className="form-group">
          <label className="form-check-label">
            <input type="checkbox" data-testid="submit-now-check" checked={submitNow}
              onChange={e => setSubmitNow(e.target.checked)} />
            {" "}Langsung kirim untuk persetujuan (lewati draf)
          </label>
        </div>

        <div className="form-actions">
          <button type="button" className="secondary-button" onClick={onCancel}>Batal</button>
          <button type="submit" data-testid="save-return-btn" className="primary-button" disabled={saving}>
            {saving ? <Loader2 size={14} className="spin" /> : <RotateCcw size={14} />} Buat Return
          </button>
        </div>
      </form>
    </div>
  );
}
