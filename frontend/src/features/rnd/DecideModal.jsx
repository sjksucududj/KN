/**
 * DecideModal (FASE F) — pilih SUPPLIER PEMENANG sample.
 * Keputusan ini melahirkan **kontrak harga** + **barang supplier** (Fase E), sehingga
 * dampaknya dijelaskan terang-terangan sebelum tombol ditekan.
 */
import { useState } from "react";
import { Trophy, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { formatCurrency } from "../../utils/formatters";

export default function DecideModal({ sample, reasons, onClose, onConfirm, busy }) {
  const accBySupplier = {};
  (sample.rounds || []).forEach((r) => {
    if (r.result === "acc") accBySupplier[r.supplier_id] = r;
  });
  const candidates = (sample.participants || []).filter((p) => accBySupplier[p.supplier_id]);
  const [supplierId, setSupplierId] = useState(candidates[0]?.supplier_id || "");
  const [reasonCode, setReasonCode] = useState(reasons?.[0]?.value || "");
  const [price, setPrice] = useState("");
  const [supplierSku, setSupplierSku] = useState("");
  const [supplierUom, setSupplierUom] = useState("");
  const [moq, setMoq] = useState("");
  const [lead, setLead] = useState("");
  const [note, setNote] = useState("");

  return (
    <div data-testid="decide-modal"
      className="fixed inset-0 z-[176] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[92vh] w-full max-w-[620px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <Trophy size={16} className="text-[#B26A00]" /> Pilih Supplier Pemenang
          </h2>
          <button className="icon-button" onClick={onClose} data-testid="decide-close">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-2.5 overflow-y-auto p-4">
          <div className="rounded-lg bg-[#F2F7FF] px-3 py-2 text-[11.5px] text-[#004099]">
            Keputusan ini <b>membentuk kontrak harga</b> untuk supplier terpilih dan
            mendaftarkan <b>barang supplier</b>. Nomor sample <b>{sample.number}</b> akan
            menjadi referensi asal harga, sehingga pertanyaan “harga PO ini dari mana?”
            selalu bisa dijawab.
          </div>

          {candidates.length === 0 ? (
            <p className="rounded-lg bg-[#FFF6E5] px-3 py-2 text-[11.5px] text-[#8C4A00]"
              data-testid="decide-no-candidate">
              Belum ada supplier yang hasilnya <b>ACC</b>. Nilai dulu hasil sample-nya
              — pemenang hanya boleh dipilih dari supplier yang sudah ACC.
            </p>
          ) : (
            <>
              <Field label="Supplier pemenang *">
                <KNSelect data-testid="decide-supplier" className="field" value={supplierId}
                  options={candidates.map((p) => ({
                    value: p.supplier_id,
                    label: `${p.supplier_name} · skor ${accBySupplier[p.supplier_id]?.score ?? "—"}`,
                  }))} onValueChange={setSupplierId} />
              </Field>
              <Field label="Alasan keputusan *">
                <KNSelect data-testid="decide-reason" className="field" value={reasonCode}
                  options={(reasons || []).map((r) => ({ value: r.value, label: r.label }))}
                  onValueChange={setReasonCode} />
              </Field>
              <div className="grid gap-2.5 md:grid-cols-2">
                <Field label="Harga kesepakatan per satuan (Rp) *">
                  <input className="field" data-testid="decide-price" value={price}
                    onChange={(e) => setPrice(e.target.value)} placeholder="42500" />
                </Field>
                <Field label="Kode barang versi supplier">
                  <input className="field" data-testid="decide-supplier-sku" value={supplierSku}
                    onChange={(e) => setSupplierSku(e.target.value)} placeholder="SUP-KTN-135" />
                </Field>
                <Field label="Satuan supplier">
                  <input className="field" data-testid="decide-supplier-uom" value={supplierUom}
                    onChange={(e) => setSupplierUom(e.target.value)} placeholder="meter" />
                </Field>
                <Field label="MOQ">
                  <input className="field" data-testid="decide-moq" value={moq}
                    onChange={(e) => setMoq(e.target.value)} placeholder="100" />
                </Field>
                <Field label="Lead time (hari)">
                  <input className="field" data-testid="decide-lead" value={lead}
                    onChange={(e) => setLead(e.target.value)} placeholder="14" />
                </Field>
                <Field label="Catatan">
                  <input className="field" data-testid="decide-note" value={note}
                    onChange={(e) => setNote(e.target.value)} placeholder="mis. ΔE 0.9 paling dekat" />
                </Field>
              </div>
              {price && (
                <p className="text-[11.5px] text-[#6B6B73]" data-testid="decide-impact">
                  Kontrak akan terbit dengan harga <b>{formatCurrency(Number(price) || 0)}</b>
                  {" "}per satuan untuk supplier terpilih.
                </p>
              )}
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="decide-confirm"
            disabled={busy || !supplierId || !reasonCode || !price}
            onClick={() => onConfirm({
              supplier_id: supplierId, reason_code: reasonCode, note,
              price: price || 0, supplier_sku: supplierSku, supplier_uom: supplierUom,
              moq: moq || 0, lead_time_days: lead || 0,
            })}>
            <Trophy size={13} /> {busy ? "Memproses…" : "Putuskan & buat kontrak"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">{label}</span>
      {children}
    </label>
  );
}
