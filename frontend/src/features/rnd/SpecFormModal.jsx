/**
 * SpecFormModal (FASE F · PS-12/PS-13/PS-14) — buat spesifikasi produk R&D.
 * Warna WAJIB dari Pustaka Warna (bukan teks bebas); desain WAJIB untuk proofing.
 */
import { useEffect, useState } from "react";
import { FlaskConical, Save, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { createSpec, listColors, listDesigns } from "./rndApi";
import { errMsg } from "./rndMeta";

const STAGE_OPTS = [
  { value: "finished", label: "Finished (kain jadi)" },
  { value: "grey", label: "Grey (kain mentah)" },
  { value: "pfd", label: "PFD (siap celup)" },
  { value: "pfp", label: "PFP (siap cetak)" },
];
const FABRIC_OPTS = [
  { value: "woven", label: "Woven (tenun)" },
  { value: "knit", label: "Knit (rajut)" },
];
const TYPE_OPTS = [
  { value: "labdip", label: "Labdip — kain polos (cocokkan warna)" },
  { value: "proofing", label: "Proofing — printing (butuh desain)" },
  { value: "bulk_sample", label: "Bulk sample" },
];
const GRADE_OPTS = [
  { value: "", label: "— tidak ditentukan —" },
  { value: "A", label: "A — mutu terbaik" },
  { value: "A1", label: "A1" }, { value: "A2", label: "A2" }, { value: "B", label: "B" },
];

export default function SpecFormModal({ selectedEntity, onClose, onSaved }) {
  const [colors, setColors] = useState([]);
  const [designs, setDesigns] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [f, setF] = useState({
    title: "", category: "", base_unit: "meter", sku_hint: "",
    sample_type_hint: "labdip", stage: "finished", fabric_type: "woven",
    gramasi: "", lebar: "", grade: "", epi: "", ppi: "",
    color_id: "", design_id: "", target_price: "", notes: "",
  });
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    listColors().then((c) => setColors(Array.isArray(c) ? c : c?.items || [])).catch(() => {});
    listDesigns().then((d) => setDesigns(Array.isArray(d) ? d : d?.items || [])).catch(() => {});
  }, []);

  const submit = async () => {
    setErr("");
    if (!f.title.trim()) { setErr("Judul spesifikasi wajib diisi."); return; }
    setSaving(true);
    try {
      const created = await createSpec({
        title: f.title, category: f.category, base_unit: f.base_unit,
        sku_hint: f.sku_hint, sample_type_hint: f.sample_type_hint,
        target: {
          stage: f.stage, fabric_type: f.fabric_type,
          gramasi: f.gramasi === "" ? null : f.gramasi,
          lebar: f.lebar === "" ? null : f.lebar,
          grade: f.grade, epi: f.epi === "" ? null : f.epi, ppi: f.ppi === "" ? null : f.ppi,
        },
        color_target: f.color_id ? { color_id: f.color_id } : {},
        design_id: f.design_id, target_price: f.target_price || 0, notes: f.notes,
        entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "",
      });
      onSaved?.(created);
    } catch (e) {
      setErr(errMsg(e, "Gagal menyimpan spesifikasi."));
      setSaving(false);
    }
  };

  return (
    <div data-testid="spec-form-modal"
      className="fixed inset-0 z-[170] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[94vh] w-full max-w-[820px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <FlaskConical size={16} className="text-[#0058CC]" /> Spesifikasi Produk Baru (R&D)
          </h2>
          <button className="icon-button" onClick={onClose} data-testid="spec-form-close">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {err && (
            <div className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]"
              data-testid="spec-form-error">{err}</div>
          )}
          <p className="rounded-lg bg-[#F2F7FF] px-3 py-2 text-[11.5px] text-[#004099]">
            Produk baru <b>tidak langsung bisa dijual</b>. Setelah spesifikasi disetujui,
            produk lahir dengan tahap <b>“Disetujui”</b>; barang baru boleh dipesan/dijual
            setelah <b>dirilis ke produksi</b>.
          </p>

          <Field label="Judul spesifikasi *">
            <input className="field" data-testid="spec-title-input" value={f.title}
              onChange={(e) => set("title", e.target.value)}
              placeholder="mis. Katun Premium 135gsm warna khusus pelanggan" />
          </Field>

          <div className="grid gap-2.5 md:grid-cols-3">
            <Field label="Jenis sample yang direncanakan">
              <KNSelect data-testid="spec-sample-type" className="field" value={f.sample_type_hint}
                options={TYPE_OPTS} onValueChange={(v) => set("sample_type_hint", v)} />
            </Field>
            <Field label="Tahap bahan">
              <KNSelect data-testid="spec-stage" className="field" value={f.stage}
                options={STAGE_OPTS} onValueChange={(v) => set("stage", v)} />
            </Field>
            <Field label="Jenis kain *">
              <KNSelect data-testid="spec-fabric" className="field" value={f.fabric_type}
                options={FABRIC_OPTS} onValueChange={(v) => set("fabric_type", v)} />
            </Field>
          </div>

          <div className="grid gap-2.5 md:grid-cols-4">
            <Field label="Gramasi (gsm)">
              <input className="field" data-testid="spec-gramasi-input" value={f.gramasi}
                onChange={(e) => set("gramasi", e.target.value)} placeholder="135" />
            </Field>
            <Field label="Lebar (cm)">
              <input className="field" data-testid="spec-lebar-input" value={f.lebar}
                onChange={(e) => set("lebar", e.target.value)} placeholder="115" />
            </Field>
            <Field label="EPI (benang lusi/inci)">
              <input className="field" data-testid="spec-epi-input" value={f.epi}
                onChange={(e) => set("epi", e.target.value)} placeholder="60" />
            </Field>
            <Field label="PPI (benang pakan/inci)">
              <input className="field" data-testid="spec-ppi-input" value={f.ppi}
                onChange={(e) => set("ppi", e.target.value)} placeholder="58" />
            </Field>
          </div>

          <div className="grid gap-2.5 md:grid-cols-2">
            <Field label="Warna target (wajib dari Pustaka Warna)">
              <KNSelect data-testid="spec-color" className="field" value={f.color_id}
                options={[{ value: "", label: "— belum ditentukan —" },
                  ...colors.map((c) => ({ value: c.id, label: `${c.code} · ${c.name}` }))]}
                onValueChange={(v) => set("color_id", v)} />
            </Field>
            <Field label={`Desain / pattern${f.sample_type_hint === "proofing" ? " (wajib untuk printing)" : ""}`}>
              <KNSelect data-testid="spec-design" className="field" value={f.design_id}
                options={[{ value: "", label: "— tanpa desain —" },
                  ...designs.map((d) => ({ value: d.id,
                    label: `${d.code || "tanpa kode"} · ${d.title} (v${d.version || 1})` }))]}
                onValueChange={(v) => set("design_id", v)} />
            </Field>
          </div>

          <div className="grid gap-2.5 md:grid-cols-4">
            <Field label="Kode SKU usulan">
              <input className="field" data-testid="spec-sku-input" value={f.sku_hint}
                onChange={(e) => set("sku_hint", e.target.value)} placeholder="KTN-PRM-135" />
            </Field>
            <Field label="Kategori">
              <input className="field" data-testid="spec-category-input" value={f.category}
                onChange={(e) => set("category", e.target.value)} placeholder="Katun" />
            </Field>
            <Field label="Satuan dasar">
              <input className="field" data-testid="spec-unit-input" value={f.base_unit}
                onChange={(e) => set("base_unit", e.target.value)} placeholder="meter" />
            </Field>
            <Field label="Grade diharapkan">
              <KNSelect data-testid="spec-grade" className="field" value={f.grade}
                options={GRADE_OPTS} onValueChange={(v) => set("grade", v)} />
            </Field>
          </div>

          <div className="grid gap-2.5 md:grid-cols-2">
            <Field label="Target harga jual (Rp)">
              <input className="field" data-testid="spec-price-input" value={f.target_price}
                onChange={(e) => set("target_price", e.target.value)} placeholder="48000" />
            </Field>
            <Field label="Catatan">
              <input className="field" data-testid="spec-notes-input" value={f.notes}
                onChange={(e) => set("notes", e.target.value)}
                placeholder="Permintaan pelanggan / referensi" />
            </Field>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" onClick={submit} disabled={saving}
            data-testid="spec-form-save">
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
