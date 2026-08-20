/**
 * DesignFormModal (FASE F · PS-14) — satu permukaan untuk master **Desain & Pattern**:
 *  - mode "create" / "edit": kode unik, jenis, atribut printing (repeat/warna/screen)
 *  - mode "version"        : naikkan versi artwork (versi lama tetap terarsip)
 *
 * Catatan penting: koleksi yang dipakai adalah `design_gallery` yang SUDAH ADA
 * (galeri motif HRD H5) — diperluas, bukan dibuat koleksi kedua.
 */
import { useState } from "react";
import { Layers, Save, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { bumpDesignVersion, createDesign, patchDesign } from "./rndApi";
import { errMsg } from "./rndMeta";

const TYPE_OPTS = [
  { value: "motif", label: "Motif — corak kain" },
  { value: "pattern", label: "Pattern — pola berulang" },
  { value: "artwork", label: "Artwork — gambar siap cetak" },
];
const STATUS_OPTS = [
  { value: "draft", label: "Draf — belum boleh dipakai proofing" },
  { value: "approved", label: "Disahkan — boleh dipakai proofing" },
  { value: "retired", label: "Tidak dipakai lagi" },
];

export default function DesignFormModal({ mode = "create", design, onClose, onSaved }) {
  const [f, setF] = useState({
    title: design?.title || "",
    code: design?.code || "",
    design_type: design?.design_type || "motif",
    repeat_cm: design?.repeat_cm ?? "",
    color_count: design?.color_count ?? "",
    screen_count: design?.screen_count ?? "",
    story: design?.story || "",
    tags: (design?.tags || []).join(", "),
    status: design?.status || "draft",
    note: "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const isVersion = mode === "version";

  const num = (v) => (v === "" || v === null ? null : Number(String(v).replace(",", ".")));

  const save = async () => {
    setErr("");
    if (!isVersion && !f.title.trim()) { setErr("Judul desain wajib diisi."); return; }
    setSaving(true);
    try {
      let res;
      if (isVersion) {
        res = await bumpDesignVersion(design.id, {
          note: f.note, repeat_cm: num(f.repeat_cm),
          color_count: num(f.color_count), screen_count: num(f.screen_count),
        });
      } else {
        const body = {
          title: f.title, code: f.code, design_type: f.design_type,
          repeat_cm: num(f.repeat_cm), color_count: num(f.color_count),
          screen_count: num(f.screen_count), story: f.story,
          tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
        };
        res = mode === "edit"
          ? await patchDesign(design.id, { ...body, status: f.status })
          : await createDesign(body);
      }
      onSaved?.(res);
    } catch (e) {
      setErr(errMsg(e, "Desain gagal disimpan."));
      setSaving(false);
    }
  };

  return (
    <div data-testid="design-form-modal"
      className="fixed inset-0 z-[172] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[92vh] w-full max-w-[620px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <Layers size={16} className="text-[#6B219A]" />
            {isVersion ? `Naikkan versi — ${design?.code || design?.title}`
              : mode === "edit" ? "Ubah Desain" : "Desain Baru"}
          </h2>
          <button className="icon-button" onClick={onClose} data-testid="design-form-close">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-2.5 overflow-y-auto p-4">
          {err && (
            <div className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]"
              data-testid="design-form-error">{err}</div>
          )}

          {isVersion ? (
            <>
              <div className="rounded-lg bg-[#F2F7FF] px-3 py-2 text-[11.5px] text-[#004099]">
                Versi sekarang <b>v{design?.version || 1}</b> → akan menjadi
                <b> v{Number(design?.version || 1) + 1}</b>. Status kembali <b>draf</b> dan
                harus disahkan lagi — supaya proofing tidak memakai artwork yang belum diperiksa.
              </div>
              <Field label="Apa yang berubah pada versi ini? *">
                <textarea className="field" rows={3} data-testid="design-version-note"
                  value={f.note} onChange={(e) => set("note", e.target.value)}
                  placeholder="mis. warna latar diganti, repeat dikoreksi jadi 32 cm" />
              </Field>
            </>
          ) : (
            <>
              <div className="grid gap-2.5 md:grid-cols-2">
                <Field label="Judul desain *">
                  <input className="field" data-testid="design-title-input" value={f.title}
                    onChange={(e) => set("title", e.target.value)}
                    placeholder="mis. Batik Parang Modern" />
                </Field>
                <Field label="Kode desain (wajib sebelum disahkan)">
                  <input className="field" data-testid="design-code-input" value={f.code}
                    onChange={(e) => set("code", e.target.value.toUpperCase())}
                    placeholder="mis. DSG-PARANG-01" />
                </Field>
              </div>
              <div className="grid gap-2.5 md:grid-cols-2">
                <Field label="Jenis desain">
                  <KNSelect data-testid="design-type-select" className="field"
                    value={f.design_type} options={TYPE_OPTS}
                    onValueChange={(v) => set("design_type", v)} />
                </Field>
                {mode === "edit" && (
                  <Field label="Status">
                    <KNSelect data-testid="design-status-select" className="field"
                      value={f.status} options={STATUS_OPTS}
                      onValueChange={(v) => set("status", v)} />
                  </Field>
                )}
              </div>
            </>
          )}

          <div className="grid gap-2.5 md:grid-cols-3">
            <Field label="Repeat (cm)">
              <input className="field" data-testid="design-repeat-input" value={f.repeat_cm}
                onChange={(e) => set("repeat_cm", e.target.value)} placeholder="32" />
            </Field>
            <Field label="Jumlah warna">
              <input className="field" data-testid="design-colors-input" value={f.color_count}
                onChange={(e) => set("color_count", e.target.value)} placeholder="4" />
            </Field>
            <Field label="Jumlah screen">
              <input className="field" data-testid="design-screens-input" value={f.screen_count}
                onChange={(e) => set("screen_count", e.target.value)} placeholder="4" />
            </Field>
          </div>

          {!isVersion && (
            <>
              <Field label="Cerita / catatan desain">
                <textarea className="field" rows={2} data-testid="design-story-input"
                  value={f.story} onChange={(e) => set("story", e.target.value)}
                  placeholder="mis. inspirasi motif parang untuk koleksi lebaran" />
              </Field>
              <Field label="Tag (pisahkan dengan koma)">
                <input className="field" data-testid="design-tags-input" value={f.tags}
                  onChange={(e) => set("tags", e.target.value)} placeholder="batik, parang, klasik" />
              </Field>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" onClick={save} disabled={saving}
            data-testid="design-form-save">
            <Save size={13} /> {saving ? "Menyimpan…" : isVersion ? "Naikkan versi" : "Simpan"}
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
