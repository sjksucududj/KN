import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, Percent } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";

/**
 * InputTaxCreateModal (Fase 5.5) — catat Faktur Pajak Masukan dari Vendor Bill.
 * DPP/PPN otomatis dari bill; user mengisi NSFP supplier (16-digit) + tanggal faktur.
 */
const KODE_OPTIONS = [
  { value: "01", label: "01 — Penyerahan ke ber-NPWP (normal)" },
  { value: "02", label: "02 — Pemungut Bendaharawan" },
  { value: "03", label: "03 — Pemungut Selain Bendaharawan" },
  { value: "07", label: "07 — PPN Tidak Dipungut" },
  { value: "08", label: "08 — PPN Dibebaskan" },
];

export default function InputTaxCreateModal({ open, bills, onClose, onCreated, onError }) {
  const [billId, setBillId] = useState("");
  const [nsfp, setNsfp] = useState("");
  const [fakturDate, setFakturDate] = useState("");
  const [kode, setKode] = useState("01");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (!open) reset(); }, [open]);
  function reset() { setBillId(""); setNsfp(""); setFakturDate(""); setKode("01"); setNotes(""); }

  const bill = useMemo(() => (bills || []).find((b) => b.vendor_bill_id === billId), [bills, billId]);
  const billOptions = useMemo(() => (bills || []).map((b) => ({
    value: b.vendor_bill_id,
    label: `${b.bill_number} · ${b.supplier_name} · PPN ${formatCurrency(b.ppn_amount)}`,
  })), [bills]);

  async function submit() {
    if (!billId) { onError?.("Pilih Vendor Bill sumber dulu."); return; }
    if (!nsfp.trim()) { onError?.("NSFP (Nomor Seri Faktur Pajak) wajib diisi."); return; }
    setBusy(true);
    try {
      const body = { vendor_bill_id: billId, nsfp: nsfp.trim(), faktur_date: fakturDate || "", kode_transaksi: kode, notes };
      const r = await axios.post(`${API}/input-tax-invoices`, body);
      onCreated?.(r.data);
    } catch (e) {
      onError?.(e.response?.data?.detail || "Gagal mencatat Faktur Pajak Masukan.");
    } finally { setBusy(false); }
  }

  if (!open) return null;

  return (
    <div className="modal-overlay" data-testid="input-tax-create-modal"
         onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 620, width: "94vw", maxHeight: "92vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2] sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <Percent size={16} className="text-[#0058CC]" />
            <h2 className="text-[14px] font-bold">Catat Faktur Pajak Masukan</h2>
          </div>
          <button data-testid="it-create-close" onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-3">
          <Field label="Tagihan Supplier (Vendor Bill ber-PPN)" req>
            {(bills || []).length === 0 ? (
              <p className="text-[11px] text-[#9A9BA3] px-2 py-2 rounded-md border border-[#EFF0F2]" data-testid="it-no-bills">
                Tidak ada Vendor Bill ber-PPN (posted/paid) yang belum dicatat. Posting Tagihan Supplier dulu.
              </p>
            ) : (
              <KNSelect value={billId} onValueChange={setBillId} options={billOptions}
                        className="field" placeholder="Pilih tagihan supplier..." data-testid="it-bill-select" />
            )}
          </Field>

          {bill && (
            <div className="grid grid-cols-3 gap-3 rounded-md bg-[#FAFBFC] border border-[#EFF0F2] p-3" data-testid="it-bill-preview">
              <Info label="DPP" value={formatCurrency(bill.dpp)} />
              <Info label={`PPN (${bill.ppn_rate || 0}%)`} value={formatCurrency(bill.ppn_amount)} strong />
              <Info label="Total Tagihan" value={formatCurrency(bill.grand_total)} />
              <Info label="Supplier" value={bill.supplier_name} />
              <Info label="NPWP" value={bill.supplier_npwp || "—"} />
              <Info label="PO" value={bill.po_number || "—"} />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="NSFP — No. Seri Faktur Pajak (16 digit)" req>
              <input data-testid="it-nsfp-input" value={nsfp} onChange={(e) => setNsfp(e.target.value)}
                className="field tabular-nums" placeholder="010.000-00.00000000" />
            </Field>
            <Field label="Tanggal Faktur Pajak">
              <input type="date" data-testid="it-faktur-date" value={fakturDate} onChange={(e) => setFakturDate(e.target.value)}
                className="field" />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Kode Transaksi">
              <KNSelect value={kode} onValueChange={setKode} options={KODE_OPTIONS} className="field" data-testid="it-kode-select" />
            </Field>
            <Field label="Catatan">
              <input data-testid="it-notes-input" value={notes} onChange={(e) => setNotes(e.target.value)}
                className="field" placeholder="opsional" />
            </Field>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2] sticky bottom-0 bg-white">
          <button onClick={onClose} className="secondary-button">Batal</button>
          <button data-testid="it-submit" disabled={busy || !billId || !nsfp.trim()} onClick={submit} className="primary-button">
            {busy ? "Menyimpan..." : "Catat Faktur Masukan"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-[#4A4B53] mb-1">{label}{req && <span className="text-red-500"> *</span>}</label>
      {children}
    </div>
  );
}

function Info({ label, value, strong }) {
  return (
    <div>
      <p className="text-[9.5px] font-bold uppercase text-[#9A9BA3]">{label}</p>
      <p className={`text-[12px] ${strong ? "font-bold" : "font-medium"} tabular-nums truncate text-[#0F1115]`}>{value}</p>
    </div>
  );
}
