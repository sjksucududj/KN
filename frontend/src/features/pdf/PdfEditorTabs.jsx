// PdfEditorTabs — panel editor (6 tab) untuk konfigurasi template PDF + branding entitas.
// Semua kontrol memakai kelas/komponen existing (field/form-input/btn-*, KNSelect, Switch).
import { useRef } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import KNSelect from "../../components/KNSelect";
import {
  PAPER_SIZES, ORIENTATIONS, FONT_FAMILIES, FONT_SIZES, COLOR_PRESETS, EDITOR_TABS,
} from "./pdfConstants";
import { Plus, Trash2, Upload, ImageOff, Save, Loader2, Info } from "lucide-react";

function Row({ label, hint, children }) {
  return (
    <div className="grid gap-1">
      <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">{label}</label>
      {children}
      {hint && <p className="text-[10.5px] text-[#9A9BA3] leading-snug">{hint}</p>}
    </div>
  );
}

function ColorField({ value, onChange, testId }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="color" value={value || "#0058CC"} onChange={(e) => onChange(e.target.value)}
        className="h-9 w-12 cursor-pointer rounded-md border border-[#D6D7DC] bg-white p-0.5"
        data-testid={testId}
        aria-label="Pilih warna"
      />
      <input
        type="text" value={value || ""} onChange={(e) => onChange(e.target.value)}
        className="form-input !w-[110px] font-mono text-[12px]"
      />
      <div className="flex items-center gap-1">
        {COLOR_PRESETS.map((c) => (
          <button key={c} type="button" onClick={() => onChange(c)} title={c}
            className="h-5 w-5 rounded-full border border-black/10 transition-transform hover:scale-110"
            style={{ background: c }} />
        ))}
      </div>
    </div>
  );
}

export default function PdfEditorTabs({
  config, patch, branding, patchBranding,
  onLogoFile, onRemoveLogo, onSaveBranding, savingBrand, brandingMsg, brandingErr, newLogoPreview,
}) {
  const fileRef = useRef(null);
  const cf = config || {};

  // ── custom fields helpers ───────────────────────────────
  const customFields = cf.custom_fields || [];
  const setCustom = (arr) => patch("custom_fields", arr);
  const addCustom = () => setCustom([...customFields, { label: "", value: "" }]);
  const updCustom = (i, k, v) => setCustom(customFields.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)));
  const delCustom = (i) => setCustom(customFields.filter((_, idx) => idx !== i));

  // ── signature slots helpers ─────────────────────────────
  const sigs = cf.signature_slots || [];
  const setSigs = (arr) => patch("signature_slots", arr);
  const addSig = () => setSigs([...sigs, { label: "", role: "", name: "" }]);
  const updSig = (i, k, v) => setSigs(sigs.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)));
  const delSig = (i) => setSigs(sigs.filter((_, idx) => idx !== i));

  // ── hidden fields (comma separated) ─────────────────────
  const hiddenStr = (cf.hidden_fields || []).join(", ");
  const setHidden = (str) => patch("hidden_fields", str.split(",").map((s) => s.trim()).filter(Boolean));

  const logoSrc = newLogoPreview || branding?.logo_src || "";

  return (
    <section className="section-card" data-testid="pdf-editor">
      <Tabs defaultValue="layout" className="w-full">
        <TabsList className="flex w-full flex-wrap gap-1 bg-transparent p-2 border-b border-[#EDEEF1]">
          {EDITOR_TABS.map((t) => (
            <TabsTrigger key={t.id} value={t.id} data-testid={`pdf-tab-${t.id}`}
              className="text-[12px] px-3 py-1.5 rounded-md data-[state=active]:bg-[#EAF2FF] data-[state=active]:text-[#0058CC] data-[state=active]:font-semibold">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="section-body grid gap-3">
          {/* ── LAYOUT ─────────────────────────────────────── */}
          <TabsContent value="layout" className="grid gap-3 mt-0">
            <Row label="Ukuran Kertas">
              <KNSelect value={cf.paper_size || "A4"} onValueChange={(v) => patch("paper_size", v)}
                options={PAPER_SIZES} className="field" data-testid="pdf-paper-size" />
            </Row>
            <Row label="Orientasi">
              <KNSelect value={cf.orientation || "portrait"} onValueChange={(v) => patch("orientation", v)}
                options={ORIENTATIONS} className="field" data-testid="pdf-orientation" />
            </Row>
            <Row label="Margin (mm)" hint="Atas · Kanan · Bawah · Kiri">
              <div className="grid grid-cols-4 gap-2">
                {["margin_top", "margin_right", "margin_bottom", "margin_left"].map((k) => (
                  <input key={k} type="number" min="0" max="60" className="form-input text-center"
                    value={cf[k] ?? 0} onChange={(e) => patch(k, Number(e.target.value))}
                    data-testid={`pdf-${k}`} />
                ))}
              </div>
            </Row>
            <Row label="Judul Dokumen (override)" hint="Kosongkan untuk memakai judul bawaan dokumen.">
              <input type="text" className="form-input" value={cf.title_override || ""}
                onChange={(e) => patch("title_override", e.target.value)}
                placeholder="mis. SURAT PESANAN" data-testid="pdf-title-override" />
            </Row>
            <label className="flex items-center justify-between gap-3 rounded-lg border border-[#EDEEF1] px-3 py-2">
              <span className="text-[12.5px] font-medium">Tampilkan logo perusahaan</span>
              <Switch checked={!!cf.show_logo} onCheckedChange={(v) => patch("show_logo", v)} data-testid="pdf-show-logo" />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-lg border border-[#EDEEF1] px-3 py-2">
              <span className="text-[12.5px] font-medium">Tampilkan “terbilang” (nominal huruf)</span>
              <Switch checked={!!cf.show_terbilang} onCheckedChange={(v) => patch("show_terbilang", v)} data-testid="pdf-show-terbilang" />
            </label>
          </TabsContent>

          {/* ── KOP SURAT (branding per entitas) ───────────── */}
          <TabsContent value="kop" className="grid gap-3 mt-0">
            <div className="flex items-start gap-2 rounded-lg bg-[#EFF4FF] px-3 py-2 text-[11.5px] text-[#0058CC]">
              <Info size={14} className="mt-0.5 shrink-0" />
              <span>Kop surat disimpan per <b>entitas (PT)</b>. Simpan branding untuk melihat perubahan di pratinjau.</span>
            </div>
            <Row label="Nama Perusahaan">
              <input type="text" className="form-input" value={branding?.company_name || ""}
                onChange={(e) => patchBranding("company_name", e.target.value)} data-testid="pdf-brand-name" />
            </Row>
            <Row label="Alamat">
              <textarea className="form-input min-h-[60px]" value={branding?.address || ""}
                onChange={(e) => patchBranding("address", e.target.value)} data-testid="pdf-brand-address" />
            </Row>
            <div className="grid grid-cols-2 gap-2">
              <Row label="Telepon">
                <input type="text" className="form-input" value={branding?.phone || ""}
                  onChange={(e) => patchBranding("phone", e.target.value)} data-testid="pdf-brand-phone" />
              </Row>
              <Row label="NPWP">
                <input type="text" className="form-input" value={branding?.npwp || ""}
                  onChange={(e) => patchBranding("npwp", e.target.value)} data-testid="pdf-brand-npwp" />
              </Row>
            </div>
            <Row label="Logo" hint="PNG/JPG, disarankan < 200 KB. Disimpan sebagai base64.">
              <div className="flex items-center gap-3">
                <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-md border border-[#E5E6EB] bg-[#F7F8FA]">
                  {logoSrc ? <img src={logoSrc} alt="logo" className="max-h-full max-w-full object-contain" /> : <ImageOff size={20} className="text-[#C4C5CC]" />}
                </div>
                <div className="flex flex-col gap-1">
                  <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                    onChange={(e) => e.target.files?.[0] && onLogoFile(e.target.files[0])} data-testid="pdf-brand-logo-input" />
                  <button type="button" className="btn-secondary flex items-center gap-1.5"
                    onClick={() => fileRef.current?.click()} data-testid="pdf-brand-logo-upload">
                    <Upload size={13} /> Unggah Logo
                  </button>
                  {logoSrc && <button type="button" className="text-[11px] text-[#C0392B] hover:underline" onClick={onRemoveLogo} data-testid="pdf-brand-logo-remove">Hapus logo</button>}
                </div>
              </div>
            </Row>
            <div className="flex items-center gap-2 pt-1">
              <button className="btn-primary flex items-center gap-1.5" onClick={onSaveBranding} disabled={savingBrand} data-testid="pdf-brand-save">
                {savingBrand ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Simpan Branding
              </button>
              {brandingMsg && <span className="text-[11.5px] font-semibold text-[#1F7A45]">{brandingMsg}</span>}
              {brandingErr && <span className="text-[11.5px] font-semibold text-[#C0392B]">{brandingErr}</span>}
            </div>
          </TabsContent>

          {/* ── FONT & WARNA ───────────────────────────────── */}
          <TabsContent value="typografi" className="grid gap-3 mt-0">
            <Row label="Font">
              <KNSelect value={cf.font_family || "'DejaVu Sans'"} onValueChange={(v) => patch("font_family", v)}
                options={FONT_FAMILIES} className="field" data-testid="pdf-font-family" />
            </Row>
            <Row label="Ukuran Font Dasar">
              <KNSelect value={String(cf.font_size || 10)} onValueChange={(v) => patch("font_size", Number(v))}
                options={FONT_SIZES} className="field !w-[140px]" data-testid="pdf-font-size" />
            </Row>
            <Row label="Warna Utama" hint="Judul, garis kop & header tabel.">
              <ColorField value={cf.color_primary} onChange={(v) => patch("color_primary", v)} testId="pdf-color-primary" />
            </Row>
            <Row label="Warna Aksen" hint="Teks isi & label.">
              <ColorField value={cf.color_accent} onChange={(v) => patch("color_accent", v)} testId="pdf-color-accent" />
            </Row>
          </TabsContent>

          {/* ── FIELD (custom + hidden) ────────────────────── */}
          <TabsContent value="field" className="grid gap-3 mt-0">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Field Tambahan</span>
              <button type="button" className="btn-secondary flex items-center gap-1" onClick={addCustom} data-testid="pdf-custom-add"><Plus size={13} /> Tambah</button>
            </div>
            {customFields.length === 0 && <p className="text-[11.5px] text-[#9A9BA3]">Belum ada field tambahan. Field ini muncul di bagian meta dokumen.</p>}
            <div className="grid gap-2">
              {customFields.map((r, i) => (
                <div key={i} className="flex items-center gap-2" data-testid={`pdf-custom-row-${i}`}>
                  <input className="form-input flex-1" placeholder="Label" value={r.label} onChange={(e) => updCustom(i, "label", e.target.value)} />
                  <input className="form-input flex-1" placeholder="Nilai" value={r.value} onChange={(e) => updCustom(i, "value", e.target.value)} />
                  <button type="button" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[#EDEEF1] text-[#C0392B] transition-colors hover:bg-[#FDECEA]" onClick={() => delCustom(i)} data-testid={`pdf-custom-del-${i}`} aria-label="Hapus"><Trash2 size={15} /></button>
                </div>
              ))}
            </div>
            <Row label="Sembunyikan Field (meta)" hint="Daftar label meta yang disembunyikan, pisahkan dengan koma. mis: Termin, Referensi">
              <input className="form-input" value={hiddenStr} onChange={(e) => setHidden(e.target.value)} data-testid="pdf-hidden-fields" />
            </Row>
          </TabsContent>

          {/* ── TANDA TANGAN (slots) ───────────────────────── */}
          <TabsContent value="ttd" className="grid gap-3 mt-0">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Slot Tanda Tangan</span>
              <button type="button" className="btn-secondary flex items-center gap-1" onClick={addSig} data-testid="pdf-sig-add"><Plus size={13} /> Tambah Slot</button>
            </div>
            {sigs.length === 0 && <p className="text-[11.5px] text-[#9A9BA3]">Kosong = pakai slot tanda tangan bawaan dokumen. Tambahkan untuk override.</p>}
            <div className="grid gap-2">
              {sigs.map((r, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-2" data-testid={`pdf-sig-row-${i}`}>
                  <input className="form-input" placeholder="Label (mis. Hormat kami)" value={r.label} onChange={(e) => updSig(i, "label", e.target.value)} />
                  <input className="form-input" placeholder="Peran (mis. finance)" value={r.role} onChange={(e) => updSig(i, "role", e.target.value)} />
                  <input className="form-input" placeholder="Nama" value={r.name} onChange={(e) => updSig(i, "name", e.target.value)} />
                  <button type="button" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[#EDEEF1] text-[#C0392B] transition-colors hover:bg-[#FDECEA]" onClick={() => delSig(i)} data-testid={`pdf-sig-del-${i}`} aria-label="Hapus"><Trash2 size={15} /></button>
                </div>
              ))}
            </div>
          </TabsContent>

          {/* ── FOOTER / WATERMARK ─────────────────────────── */}
          <TabsContent value="footer" className="grid gap-3 mt-0">
            <Row label="Teks Footer" hint="Muncul di bagian bawah setiap halaman.">
              <input className="form-input" value={cf.footer_text || ""} onChange={(e) => patch("footer_text", e.target.value)}
                placeholder="mis. Dokumen ini sah tanpa tanda tangan basah." data-testid="pdf-footer-text" />
            </Row>
            <Row label="Watermark" hint="Teks miring transparan di tengah halaman. Kosongkan untuk menonaktifkan.">
              <input className="form-input" value={cf.watermark_text || ""} onChange={(e) => patch("watermark_text", e.target.value)}
                placeholder="mis. SALINAN / LUNAS" data-testid="pdf-watermark-text" />
            </Row>
          </TabsContent>
        </div>
      </Tabs>
    </section>
  );
}
