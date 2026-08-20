/**
 * FASE G-9 — CaseCreateModal: laporkan kasus keuangan baru (manual).
 *
 * Jenis kasus dipilih dari playbook yang DIKIRIM BACKEND, sehingga layar tidak pernah
 * menawarkan jenis yang tidak punya mesin penyelesaian.
 */
import { useMemo, useState } from "react";
import { X, Plus } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import ErrorNotice from "../../../components/ErrorNotice";
import { KNSelect } from "../../../components/KNSelect";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import { apiErrorText } from "../../../utils/apiError";

export default function CaseCreateModal({ playbooks, customers, suppliers, onClose,
  onCreated, onError }) {
  const [caseType, setCaseType] = useState(playbooks[0]?.code || "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [saving, setSaving] = useState(false);
  // KN-G9-ERR-SILENT — modal wajib menampilkan penolakannya sendiri (bilah error layar
  // induk tertutup modal ini), mis. 403 "kasus PT lain" atau 400 "kasus kembar".
  const [err, setErr] = useState("");

  const pb = useMemo(() => playbooks.find((p) => p.code === caseType) || null,
    [playbooks, caseType]);
  const typeOptions = useMemo(
    () => playbooks.map((p) => ({ value: p.code, label: p.label })), [playbooks]);
  const custOptions = useMemo(
    () => customers.map((c) => ({ value: c.id, label: c.name || c.id })), [customers]);
  const supOptions = useMemo(
    () => suppliers.map((s) => ({ value: s.id, label: s.name || s.id })), [suppliers]);

  async function submit() {
    setSaving(true); setErr("");
    try {
      const r = await axios.post(`${API}/finance-cases`, {
        case_type: caseType,
        title: title.trim() || pb?.label || "",
        description: description.trim(),
        amount: Number(amount) || 0,
        customer_id: customerId,
        supplier_id: supplierId,
      });
      onCreated(r.data);
    } catch (e) {
      setErr(apiErrorText(e));
      onError?.(e);
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-overlay" data-testid="case-create-modal" {...overlayDismiss(onClose)}>
      <div className="modal-panel max-h-[92vh] w-[560px] max-w-[95vw] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h3 className="flex items-center gap-2 text-[14px] font-bold text-[#1C1C1E]">
            <Plus size={15} className="text-[#0058CC]" /> Laporkan kasus keuangan
          </h3>
          <button className="icon-button" data-testid="case-create-close" onClick={onClose}>
            <X size={15} />
          </button>
        </div>

        <div className="space-y-3 px-4 py-4">
          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Jenis kasus
            </label>
            <KNSelect data-testid="case-create-type" value={caseType}
              onValueChange={setCaseType} options={typeOptions} />
            {pb && (
              <p className="mt-1 rounded-md bg-[#F2F7FF] px-2 py-1.5 text-[11px] text-[#1C1C1E]">
                {pb.question}
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Judul singkat
            </label>
            <input data-testid="case-create-title" className="input-field w-full"
              value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder={pb?.label || "Ringkas masalahnya dalam satu baris"} />
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Nominal yang dipertaruhkan (Rp)
            </label>
            <input data-testid="case-create-amount" type="number" min={0}
              className="input-field w-full" value={amount}
              onChange={(e) => setAmount(e.target.value)} placeholder="0" />
            <p className="mt-1 text-[10px] text-[#8E8E93]">
              Nominal menentukan batas waktu penyelesaian & apakah perlu persetujuan.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Pelanggan (bila terkait)
              </label>
              <KNSelect data-testid="case-create-customer" value={customerId}
                onValueChange={setCustomerId} options={custOptions}
                placeholder="Pilih pelanggan" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
                Supplier (bila terkait)
              </label>
              <KNSelect data-testid="case-create-supplier" value={supplierId}
                onValueChange={setSupplierId} options={supOptions}
                placeholder="Pilih supplier" />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Ceritakan kejadiannya
            </label>
            <textarea data-testid="case-create-desc" className="textarea w-full" rows={3}
              value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="Mis. pelanggan bilang sudah transfer 2× untuk faktur yang sama." />
          </div>
        </div>

        {err && (
          <div className="px-4">
            <ErrorNotice message={err} onDismiss={() => setErr("")} testId="case-create-error" />
          </div>
        )}

        <div className="flex items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" data-testid="case-create-submit"
            disabled={saving || !caseType} onClick={submit}>
            {saving ? "Menyimpan…" : "Buat kasus"}
          </button>
        </div>
      </div>
    </div>
  );
}
