/**
 * SampleFormModal (FASE F) — buat permintaan sample (labdip / proofing / bulk).
 * Proofing WAJIB memilih kode desain (kebijakan `rnd.require_design_for_proofing`).
 */
import { useEffect, useState } from "react";
import { Beaker, Save, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { createSample, listColors, listDesigns, listSpecs } from "./rndApi";
import { errMsg } from "./rndMeta";

const TYPE_OPTS = [
  { value: "labdip", label: "Labdip — kain polos (cocokkan warna)" },
  { value: "proofing", label: "Proofing — printing (wajib kode desain)" },
  { value: "bulk_sample", label: "Bulk sample" },
];

export default function SampleFormModal({ selectedEntity, prefill, onClose, onSaved }) {
  const [specs, setSpecs] = useState([]);
  const [colors, setColors] = useState([]);
  const [designs, setDesigns] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [f, setF] = useState({
    spec_id: "", sample_type: prefill?.sample_type || "labdip", title: "", brief: "",
    color_id: prefill?.color_id || "", design_id: prefill?.design_id || "",
    target_date: "", qty_requested: "3", unit: "meter",
  });
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    const params = selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {};
    listSpecs({ ...params, limit: 200 }).then((r) => setSpecs(r?.items || [])).catch(() => {});
    listColors().then((c) => setColors(Array.isArray(c) ? c : c?.items || [])).catch(() => {});
    listDesigns().then((d) => setDesigns(Array.isArray(d) ? d : d?.items || [])).catch(() => {});
  }, [selectedEntity]);

  const pickSpec = (id) => {
    const s = specs.find((x) => x.id === id);
    setF((p) => ({
      ...p, spec_id: id,
      title: p.title || (s ? `${s.sample_type_hint === "proofing" ? "Proofing" : "Labdip"} ${s.title}` : ""),
      sample_type: s?.sample_type_hint || p.sample_type,
      color_id: s?.color_target?.color_id || p.color_id,
      design_id: s?.design_id || p.design_id,
      unit: s?.base_unit || p.unit,
    }));
  };

  const submit = async () => {
    setErr("");
    if (!f.title.trim()) { setErr("Judul permintaan wajib diisi."); return; }
    setSaving(true);
    try {
      const created = await createSample({
        spec_id: f.spec_id, sample_type: f.sample_type, title: f.title, brief: f.brief,
        color_target: f.color_id ? { color_id: f.color_id } : {},
        design_id: f.design_id, target_date: f.target_date,
        qty_requested: f.qty_requested || 0, unit: f.unit,
      });
      onSaved?.(created);
    } catch (e) {
      setErr(errMsg(e, "Gagal membuat permintaan sample."));
      setSaving(false);
    }
  };

  return (
    <div data-testid="sample-form-modal"
      className="fixed inset-0 z-[170] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[94vh] w-full max-w-[720px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <Beaker size={16} className="text-[#0058CC]" /> Permintaan Sample Baru
          </h2>
          <button className="icon-button" onClick={onClose} data-testid="sample-form-close">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {err && (
            <div className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]"
              data-testid="sample-form-error">{err}</div>
          )}
          {prefill?.source_label && (
            <div className="rounded-lg bg-[#F2F7FF] px-3 py-2 text-[11.5px] text-[#004099]"
              data-testid="sample-form-prefill">
              Diisi otomatis dari <b>{prefill.source_label}</b>
              {prefill.design_id ? " — jenis sample disetel ke proofing." : "."}
              {" "}Tinggal beri judul lalu simpan.
            </div>
          )}
          <div className="grid gap-2.5 md:grid-cols-2">
            <Field label="Spesifikasi acuan (opsional)">
              <KNSelect data-testid="sample-spec" className="field" value={f.spec_id}
                options={[{ value: "", label: "— tanpa spesifikasi —" },
                  ...specs.map((s) => ({ value: s.id, label: `${s.number} · ${s.title}` }))]}
                onValueChange={pickSpec} />
            </Field>
            <Field label="Jenis sample *">
              <KNSelect data-testid="sample-type" className="field" value={f.sample_type}
                options={TYPE_OPTS} onValueChange={(v) => set("sample_type", v)} />
            </Field>
          </div>
          <Field label="Judul permintaan *">
            <input className="field" data-testid="sample-title-input" value={f.title}
              onChange={(e) => set("title", e.target.value)}
              placeholder="mis. Labdip Katun Premium warna khusus" />
          </Field>
          <div className="grid gap-2.5 md:grid-cols-2">
            <Field label="Warna target">
              <KNSelect data-testid="sample-color" className="field" value={f.color_id}
                options={[{ value: "", label: "— belum ditentukan —" },
                  ...colors.map((c) => ({ value: c.id, label: `${c.code} · ${c.name}` }))]}
                onValueChange={(v) => set("color_id", v)} />
            </Field>
            <Field label={`Desain / pattern${f.sample_type === "proofing" ? " (WAJIB)" : ""}`}>
              <KNSelect data-testid="sample-design" className="field" value={f.design_id}
                options={[{ value: "", label: "— tanpa desain —" },
                  ...designs.map((d) => ({ value: d.id,
                    label: `${d.code || "tanpa kode"} · ${d.title} (v${d.version || 1})` }))]}
                onValueChange={(v) => set("design_id", v)} />
            </Field>
          </div>
          <div className="grid gap-2.5 md:grid-cols-3">
            <Field label="Jumlah diminta">
              <input className="field" data-testid="sample-qty-input" value={f.qty_requested}
                onChange={(e) => set("qty_requested", e.target.value)} placeholder="3" />
            </Field>
            <Field label="Satuan">
              <input className="field" data-testid="sample-unit-input" value={f.unit}
                onChange={(e) => set("unit", e.target.value)} placeholder="meter" />
            </Field>
            <Field label="Target tanggal selesai">
              <input className="field" type="date" data-testid="sample-target-date"
                value={f.target_date} onChange={(e) => set("target_date", e.target.value)} />
            </Field>
          </div>
          <Field label="Brief untuk supplier">
            <textarea className="field" rows={3} data-testid="sample-brief-input" value={f.brief}
              onChange={(e) => set("brief", e.target.value)}
              placeholder="mis. Cocokkan warna target maksimal ΔE 1.5, kirim swatch 3 meter" />
          </Field>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" onClick={submit} disabled={saving}
            data-testid="sample-form-save">
            <Save size={13} /> {saving ? "Menyimpan…" : "Simpan Draft"}
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
