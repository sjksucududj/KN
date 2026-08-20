/**
 * MakloonFormModal (M1) — buat/edit master makloon.
 * POST /makloons | PATCH /makloons/{id} (via {data}).
 */
import { useState } from "react";
import { Factory, X, Save } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import useProcessTypes from "../../hooks/useProcessTypes";
import useUomConversions from "../../hooks/useUomConversions";
import { uomSelectOptions } from "../../utils/uomCatalog";
import { overlayDismiss } from "@/utils/overlayDismiss";

const TARIFF_UNITS = [
  { value: "output", label: "per Output" }, { value: "input", label: "per Input" }, { value: "roll", label: "per Roll" },
];

export default function MakloonFormModal({ open, editTarget, entities = [], terms = [], selectedEntity, onClose, onSaved, onError }) {
  const isEdit = !!editTarget;
  // FASE T (4a) — daftar kemampuan mitra dari registry hidup. Dulu daftarnya hardcode 5
  // nilai, sehingga mitra ber-kemampuan `screen`/`rajut`/`pre_treatment` tidak bisa
  // dicentang sama sekali: kemampuan yang sudah ada pun tak terlihat saat disunting.
  const { options: processOptions } = useProcessTypes();
  const procList = processOptions();
  // FASE U — satuan kapasitas mitra dari MASTER satuan (panjang · berat · hitungan).
  // Dulu daftarnya diketik 4 nilai, jadi mitra yang mengukur kapasitasnya dalam
  // `panel` (satuan yang baru ditambah pemilik) tidak bisa dicatat sama sekali.
  useUomConversions();          // memuat & membagikan katalog satuan ke penyimpan modul
  const capacityUnitOptions = uomSelectOptions({
    dimensions: ["length", "weight", "count"],
    extra: [editTarget?.capacity_unit || "yard"],
  });
  const [form, setForm] = useState(() => ({
    name: editTarget?.name || "", npwp: editTarget?.npwp || "", pic_name: editTarget?.pic_name || "",
    phone: editTarget?.phone || "", email: editTarget?.email || "", city: editTarget?.city || "",
    address: editTarget?.address || "", process_types: editTarget?.process_types || [],
    capacity_per_month: editTarget?.capacity_per_month ? String(editTarget.capacity_per_month) : "",
    capacity_unit: editTarget?.capacity_unit || "yard",
    default_tariff: editTarget?.default_tariff ? String(editTarget.default_tariff) : "",
    tariff_unit: editTarget?.tariff_unit || "output",
    payment_term_code: editTarget?.payment_term_code || "",
    lead_time_days: editTarget?.lead_time_days != null ? String(editTarget.lead_time_days) : "",
    entity_id: editTarget?.entity_id || (selectedEntity && selectedEntity !== "all" ? selectedEntity : ""),
    notes: editTarget?.notes || "",
  }));
  const [saving, setSaving] = useState(false);
  if (!open) return null;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const toggleProc = (p) => setForm((f) => ({ ...f, process_types: f.process_types.includes(p) ? f.process_types.filter((x) => x !== p) : [...f.process_types, p] }));

  const save = async () => {
    if (!form.name.trim()) { onError?.("Nama makloon wajib diisi."); return; }
    setSaving(true);
    const payload = {
      ...form,
      capacity_per_month: parseFloat(form.capacity_per_month) || 0,
      default_tariff: parseFloat(form.default_tariff) || 0,
      lead_time_days: parseInt(form.lead_time_days, 10) || 0,
    };
    try {
      if (isEdit) await axios.patch(`${API}/makloons/${editTarget.id}`, { data: payload });
      else await axios.post(`${API}/makloons`, payload);
      onSaved?.();
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal menyimpan makloon."); setSaving(false); }
  };

  return (
    <div data-testid="makloon-form-modal" className="fixed inset-0 z-[160] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="flex max-h-[90vh] w-full max-w-[620px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold"><Factory size={16} className="text-[#0058CC]" /> {isEdit ? "Edit Makloon" : "Buat Makloon Baru"}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={18} /></button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Nama Makloon" req><input data-testid="makloon-name-input" className="field" value={form.name} onChange={set("name")} placeholder="PT Tenun Nusantara" /></Field>
            <Field label="NPWP"><input data-testid="makloon-npwp-input" className="field" value={form.npwp} onChange={set("npwp")} placeholder="00.000.000.0-000.000" /></Field>
            <Field label="Nama PIC"><input data-testid="makloon-pic-input" className="field" value={form.pic_name} onChange={set("pic_name")} placeholder="Nama kontak" /></Field>
            <Field label="Telepon"><input data-testid="makloon-phone-input" className="field" value={form.phone} onChange={set("phone")} placeholder="0812xxxx" /></Field>
            <Field label="Email"><input data-testid="makloon-email-input" className="field" value={form.email} onChange={set("email")} placeholder="pic@makloon.co.id" /></Field>
            <Field label="Kota"><input data-testid="makloon-city-input" className="field" value={form.city} onChange={set("city")} placeholder="Majalaya" /></Field>
          </div>
          <Field label="Jenis Proses (Kemampuan)">
            <div className="flex flex-wrap gap-1.5" data-testid="makloon-process-types">
              {procList.map(({ value: k, label: lbl }) => (
                <button key={k} type="button" data-testid={`makloon-proc-${k}`} onClick={() => toggleProc(k)}
                  className={`rounded-full border px-3 py-1 text-[11.5px] font-medium ${form.process_types.includes(k) ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>{lbl}</button>
              ))}
            </div>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Kapasitas / Bulan"><input data-testid="makloon-capacity-input" type="number" className="field" value={form.capacity_per_month} onChange={set("capacity_per_month")} placeholder="mis. 50000" /></Field>
            <Field label="Satuan Kapasitas">
              <KNSelect data-testid="makloon-capacity-unit" className="field" value={form.capacity_unit} onValueChange={(v) => setForm({ ...form, capacity_unit: v })}
                options={capacityUnitOptions} />
            </Field>
            <Field label="Tarif Jasa Default (Rp)"><input data-testid="makloon-tariff-input" type="number" className="field" value={form.default_tariff} onChange={set("default_tariff")} placeholder="mis. 3500" /></Field>
            <Field label="Basis Tarif">
              <KNSelect data-testid="makloon-tariff-unit" className="field" value={form.tariff_unit} onValueChange={(v) => setForm({ ...form, tariff_unit: v })} options={TARIFF_UNITS} />
            </Field>
            <Field label="Lead Time (hari)"><input data-testid="makloon-leadtime-input" type="number" className="field" value={form.lead_time_days} onChange={set("lead_time_days")} placeholder="mis. 10" /></Field>
            <Field label="Termin Pembayaran">
              <KNSelect data-testid="makloon-term-select" className="field" value={form.payment_term_code} onValueChange={(v) => setForm({ ...form, payment_term_code: v })}
                options={[{ value: "", label: "— Tidak ditentukan —" }, ...terms.map((t) => ({ value: t.code, label: t.name }))]} />
            </Field>
            <Field label="Entitas">
              <KNSelect data-testid="makloon-entity-select" className="field" value={form.entity_id} onValueChange={(v) => setForm({ ...form, entity_id: v })}
                options={[{ value: "", label: "— Default (KSC) —" }, ...entities.map((e) => ({ value: e.id, label: e.short_name || e.legal_name }))]} />
            </Field>
            <Field label="Alamat"><input data-testid="makloon-address-input" className="field" value={form.address} onChange={set("address")} placeholder="Alamat lengkap" /></Field>
          </div>
          <Field label="Catatan / Kapasitas"><textarea data-testid="makloon-notes-input" className="field" rows="2" value={form.notes} onChange={set("notes")} placeholder="Catatan kapasitas / spesialisasi…" /></Field>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button data-testid="makloon-form-save" className="primary-button" disabled={saving} onClick={save}><Save size={14} /> {saving ? "Menyimpan…" : "Simpan"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">{label} {req && <span className="text-[#D14343]">*</span>}</span>
      {children}
    </label>
  );
}
