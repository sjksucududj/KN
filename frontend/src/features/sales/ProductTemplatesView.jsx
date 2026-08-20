/**
 * ProductTemplatesView (F1b) — Template & Varian Produk (ADDITIVE/non-destruktif).
 * Kelola Template induk + Generate Varian massal (Warna×Grade×Lebar → SKU otomatis).
 * Produk varian tetap unit jual ber-SKU (POS/stok/harga F1a tidak berubah).
 * Akses: admin manage; manager/sales view. Sumber: /api/product-templates/*.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Layers3, Plus, RefreshCw, Search, X, Trash2, Pencil, Wand2, Link2, Save,
  CheckCircle2, AlertTriangle, Package, Palette,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import DecimalInput from "../../components/DecimalInput";
import KNSelect from "../../components/KNSelect";
import useDomainEnums from "../../hooks/useDomainEnums";
import PantoneFinder, { ColorChip } from "../../components/PantoneFinder";
import { formatCurrency } from "../../utils/formatters";
import { Modal, Field, Kpi, AssignModal } from "./ProductTemplatesParts";
import { askConfirm } from "@/services/confirmService";

// Fase A · R1 — opsi grade TIDAK boleh teks bebas: placeholder mengikuti enum resmi
// (A|A1|A2|B|BS) dan divalidasi server saat generate varian.
const AXIS_PRESETS = [
  { key: "color", label: "Warna", placeholder: "Merah, Biru, Hijau" },
  { key: "grade", label: "Grade", placeholder: "A, A1, A2, B, BS" },
  { key: "lebar", label: "Lebar", placeholder: "115, 150 (cm)" },
];

function buildAxesPayload(axes) {
  return axes
    .map((a) => {
      if (a.key === "color") {
        return {
          key: "color", label: a.label,
          options: (a.colors || []).map((c) => ({ label: c.name, code: c.code, value: c.code, hex: c.hex })),
        };
      }
      const opts = (a.optionsText || "").split(",").map((s) => s.trim()).filter(Boolean);
      return {
        key: a.key,
        label: a.label,
        options: opts.map((label) => (a.key === "lebar" && !isNaN(parseFloat(label))
          ? { label: `${label}cm`, code: label, value: parseFloat(label) / 100 }
          : { label })),
      };
    })
    .filter((a) => a.label && a.options.length);
}

export default function ProductTemplatesView({ currentUser }) {
  const canManage = currentUser?.role === "admin";
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState(null); // 'create' | 'edit' | 'generate' | 'assign'

  const loadList = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/product-templates`, { params: { search } });
      setTemplates(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat template.");
    } finally {
      setLoading(false);
    }
  }, [search]);

  const loadDetail = useCallback(async (id) => {
    try {
      const res = await axios.get(`${API}/product-templates/${id}`);
      setSelected(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat detail template.");
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  const refreshAll = (id) => { loadList(); if (id) loadDetail(id); };
  const totalVariants = useMemo(() => templates.reduce((s, t) => s + (t.variant_count || 0), 0), [templates]);

  const removeTemplate = async (t) => {
    const ok = await askConfirm({
      title: `Hapus template "${t.name}"?`,
      message: `${t.variant_count} varian akan dilepas tautannya dari template ini. `
        + `Produknya sendiri TETAP ADA dan tidak terhapus.`,
      confirmLabel: "Hapus Template",
      danger: true,
      testId: "template-delete-confirm",
    });
    if (!ok) return;
    try {
      const res = await axios.delete(`${API}/product-templates/${t.id}`);
      setNotice(`Template dihapus. ${res.data.detached_variants} varian dilepas (produk tetap utuh).`);
      if (selected?.id === t.id) setSelected(null);
      loadList();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menghapus template.");
    }
  };

  return (
    <div data-testid="templates-view">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-3">
        <Kpi testId="tpl-kpi-templates" label="Template" value={templates.length} icon={Layers3} />
        <Kpi testId="tpl-kpi-variants" label="Total Varian" value={totalVariants} icon={Package} tone="text-[#6B219A]" />
        <div className="section-card hidden lg:block" data-testid="tpl-kpi-hint">
          <div className="section-body flex items-center gap-3 py-3">
            <div className="w-9 h-9 rounded-lg bg-[#F3EAFB] flex items-center justify-center"><Wand2 size={17} className="text-[#6B219A]" /></div>
            <p className="text-[11px] text-[#6B6B73] leading-tight">Buat varian massal dari kombinasi <b>Warna × Grade × Lebar</b> → SKU otomatis.</p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-[320px_1fr] gap-3">
        {/* ── Daftar Template ── */}
        <div className="section-card">
          <div className="section-head">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="tpl-search" className="field py-1.5 pl-8 text-[12px] w-full" placeholder="Cari template" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <button data-testid="tpl-refresh" className="icon-button ml-2" onClick={loadList} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
          <div className="section-body">
            <ErrorNotice message={error} onRetry={loadList} onDismiss={() => setError("")} testId="tpl-error" />
            {canManage && (
              <button data-testid="tpl-create-btn" className="btn-primary w-full text-[12px] py-2 mb-3 inline-flex items-center justify-center gap-1.5" onClick={() => setModal("create")}><Plus size={14} /> Template Baru</button>
            )}
            {loading ? (
              <div className="grid gap-2">{[0, 1, 2].map((i) => <div key={i} className="h-16 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
            ) : templates.length === 0 ? (
              <div data-testid="tpl-empty" className="py-10 text-center text-[12px] text-[#8E8E93]"><Layers3 size={26} className="mx-auto mb-2 text-gray-300" />Belum ada template.</div>
            ) : (
              <div className="space-y-2">
                {templates.map((t) => (
                  <button key={t.id} data-testid={`tpl-item-${t.id}`} onClick={() => loadDetail(t.id)}
                    className={`w-full text-left rounded-lg border p-3 transition-colors ${selected?.id === t.id ? "border-[#6B219A] bg-[#FBF8FE]" : "border-[#EFF0F2] hover:border-[#D9C4EC]"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-[12px] text-[#1C1C1E] truncate">{t.name}</span>
                      <span className="text-[9px] font-bold rounded px-1.5 py-0.5 bg-[#F0EAFB] text-[#6B2FB3] shrink-0">{t.variant_count} varian</span>
                    </div>
                    <p className="text-[10px] text-[#9A9BA3] mt-0.5">{t.category} · {t.motif} · {(t.axes || []).map((a) => a.label).join(" × ") || "tanpa axis"}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Detail Template ── */}
        <div className="section-card">
          {notice && (
            <div data-testid="tpl-notice" className="m-3 rounded-md bg-[#E6F6EC] border border-[#BDE5CC] text-[#1B7F4B] text-[12px] px-3 py-2 flex items-center gap-2">
              <CheckCircle2 size={14} />{notice}<button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup"><X size={13} /></button>
            </div>
          )}
          {!selected ? (
            <div className="section-body py-16 text-center text-[12px] text-[#8E8E93]" data-testid="tpl-detail-empty"><Layers3 size={30} className="mx-auto mb-2 text-gray-300" />Pilih template untuk melihat varian, atau buat template baru.</div>
          ) : (
            <>
              <div className="section-head flex-wrap gap-2">
                <div>
                  <h2 className="font-bold text-[14px] text-[#1C1C1E]">{selected.name}</h2>
                  <p className="text-[11px] text-[#9A9BA3]">{selected.category} · {selected.fabric_type || "—"} · Prefix SKU: <span className="font-mono">{selected.sku_prefix}</span></p>
                </div>
                {canManage && (
                  <div className="flex items-center gap-1.5 ml-auto">
                    <button data-testid="tpl-generate-btn" className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={() => setModal("generate")}><Wand2 size={13} /> Buat Varian</button>
                    <button data-testid="tpl-assign-btn" className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={() => setModal("assign")}><Link2 size={13} /> Assign</button>
                    <button data-testid="tpl-edit-btn" className="icon-button" title="Ubah" onClick={() => setModal("edit")}><Pencil size={14} /></button>
                    <button data-testid="tpl-delete-btn" className="icon-button text-[#C0392B]" title="Hapus" onClick={() => removeTemplate(selected)}><Trash2 size={14} /></button>
                  </div>
                )}
              </div>
              <div className="section-body">
                {/* Axes */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {(selected.axes || []).length === 0 ? (
                    <span className="text-[11px] text-[#9A9BA3]">Belum ada sumbu varian — ubah template untuk menambah Warna/Grade/Lebar.</span>
                  ) : selected.axes.map((a) => (
                    <div key={a.key} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
                      <span className="text-[10px] font-bold text-[#6B6B73] uppercase">{a.label}</span>
                      <div className="flex flex-wrap gap-1 mt-1">{a.options.map((o) => <span key={o.code} className="text-[10px] rounded bg-[#F0EAFB] text-[#6B2FB3] px-1.5 py-0.5">{o.label}</span>)}</div>
                    </div>
                  ))}
                </div>
                {/* Variants */}
                {(selected.variants || []).length === 0 ? (
                  <div data-testid="tpl-no-variants" className="py-8 text-center text-[12px] text-[#8E8E93]"><Package size={24} className="mx-auto mb-2 text-gray-300" />Belum ada varian. Klik <b>Buat Varian</b> atau <b>Assign</b>.</div>
                ) : (
                  <div className="overflow-auto rounded-md border border-[#EFF0F2]">
                    <table className="w-full text-[12px]">
                      <thead>
                        <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                          <th className="px-3 py-2">SKU</th><th className="px-3 py-2">Nama Varian</th>
                          <th className="px-3 py-2">Atribut</th><th className="px-3 py-2 text-right">Harga Dasar</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selected.variants.map((v) => (
                          <tr key={v.id} data-testid={`tpl-variant-${v.id}`} className="border-b border-[#F5F5F7] last:border-0">
                            <td className="px-3 py-2 font-mono text-[11px] text-[#6B6B73]">{v.sku}</td>
                            <td className="px-3 py-2 text-[#1C1C1E]">{v.name}</td>
                            <td className="px-3 py-2">{Object.entries(v.variant_attrs || {}).map(([k, val]) => <span key={k} className="text-[10px] rounded bg-[#F5F5F7] text-[#6B6B73] px-1.5 py-0.5 mr-1">{val}</span>)}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(v.price)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {(modal === "create" || modal === "edit") && (
        <TemplateModal mode={modal} template={modal === "edit" ? selected : null}
          onClose={() => setModal(null)} onError={setError}
          onSaved={(id) => { setModal(null); setNotice("Template tersimpan."); refreshAll(id || selected?.id); }} />
      )}
      {modal === "generate" && selected && (
        <GenerateModal template={selected} onClose={() => setModal(null)} onError={setError}
          onDone={(res) => { setModal(null); setNotice(`${res.created} varian dibuat${res.skipped ? `, ${res.skipped} dilewati (SKU sudah ada)` : ""}.`); refreshAll(selected.id); }} />
      )}
      {modal === "assign" && selected && (
        <AssignModal template={selected} onClose={() => setModal(null)} onError={setError}
          onDone={(n) => { setModal(null); setNotice(`${n} produk ditautkan ke template.`); refreshAll(selected.id); }} />
      )}
    </div>
  );
}

// ─── Template Create/Edit Modal ──────────────────────────────────────────────
function TemplateModal({ mode, template, onClose, onSaved, onError }) {
  // Fase A (PS-01/02/03) — template = induk produk: stage & fabric_type WAJIB sah.
  const { options, labelOf, fieldRules, fieldLabels } = useDomainEnums();
  const [form, setForm] = useState({
    name: template?.name || "", category: template?.category || "Kain",
    fabric_type: template?.fabric_type || "woven", motif: template?.motif || "Polos",
    base_unit: template?.base_unit || "meter", base_price: template?.base_price || "",
    gramasi: template?.gramasi || "", lebar: template?.lebar || "",
    stage: template?.stage || "finished",
    yarn_count: template?.yarn_count || "", yarn_count_system: template?.yarn_count_system || "",
    sku_prefix: template?.sku_prefix || "",
  });
  const [axes, setAxes] = useState(
    (template?.axes || []).map((a) => (a.key === "color"
      ? { key: a.key, label: a.label, colors: (a.options || []).map((o) => ({ code: o.code || o.value || o.label, name: o.label, hex: o.hex || "" })) }
      : { key: a.key, label: a.label, optionsText: (a.options || []).map((o) => o.label.replace("cm", "")).join(", ") })));
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  // Fase A · D-22 — kelengkapan wajib mengikuti kombinasi stage × fabric_type.
  const tplRules = fieldRules(form.stage, form.fabric_type);
  const tplMissing = tplRules.required.filter((k) => {
    const raw = form[k];
    if (k === "gramasi" || k === "lebar") return !(parseFloat(String(raw).replace(",", ".")) > 0);
    return !String(raw || "").trim();
  });

  const addAxis = (preset) => {
    if (axes.some((a) => a.key === preset.key)) return;
    setAxes([...axes, preset.key === "color"
      ? { key: "color", label: preset.label, colors: [] }
      : { key: preset.key, label: preset.label, optionsText: "" }]);
  };
  const updateAxisOptions = (idx, text) => setAxes(axes.map((a, i) => (i === idx ? { ...a, optionsText: text } : a)));
  const addColor = (idx, c) => setAxes(axes.map((a, i) => (i === idx
    ? { ...a, colors: [...(a.colors || []), c].filter((x, j, arr) => arr.findIndex((y) => y.code === x.code) === j) } : a)));
  const removeColor = (idx, code) => setAxes(axes.map((a, i) => (i === idx
    ? { ...a, colors: (a.colors || []).filter((c) => c.code !== code) } : a)));
  const removeAxis = (idx) => setAxes(axes.filter((_, i) => i !== idx));

  const save = async () => {
    if (!form.name.trim()) { onError("Nama template wajib diisi."); return; }
    if (tplMissing.length) {
      onError(`Lengkapi dulu: ${tplMissing.map((k) => fieldLabels[k] || k).join(", ")} `
        + `(wajib untuk stage ${labelOf("stage", form.stage)}).`);
      return;
    }
    setSaving(true);
    // PS-15 — angka dikirim apa adanya (string boleh berkoma); backend memakai
    // parse_decimal sehingga "210,5" tersimpan sebagai 210.5.
    const payload = { ...form, axes: buildAxesPayload(axes) };
    try {
      let id = template?.id;
      if (mode === "edit") await axios.patch(`${API}/product-templates/${template.id}`, payload);
      else { const res = await axios.post(`${API}/product-templates`, payload); id = res.data.id; }
      onSaved(id);
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal menyimpan template.");
      setSaving(false);
    }
  };

  return (
    <Modal title={mode === "edit" ? "Edit Template" : "Template Baru"} icon={Layers3} onClose={onClose} testId="tpl-modal" wide>
      <div className="grid sm:grid-cols-2 gap-3 text-[12px]">
        <Field label="Nama Template *"><input data-testid="tpl-input-name" className="field py-2 text-[13px]" value={form.name} onChange={set("name")} placeholder="Mis. Tenun Ikat Sumba" autoFocus /></Field>
        <Field label="Kategori"><input className="field py-2 text-[13px]" value={form.category} onChange={set("category")} /></Field>
        <Field label="Tahap Bahan (stage) *">
          <KNSelect data-testid="tpl-input-stage" className="field py-2 text-[13px]" value={form.stage}
            onValueChange={(v) => setForm({ ...form, stage: v })} options={options("stage")} />
        </Field>
        <Field label="Jenis Kain (woven/knit) *">
          <KNSelect data-testid="tpl-input-fabric_type" className="field py-2 text-[13px]" value={form.fabric_type}
            placeholder="Pilih woven / knit"
            onValueChange={(v) => setForm({ ...form, fabric_type: v })} options={options("fabric_type")} />
        </Field>
        <Field label="Motif"><input className="field py-2 text-[13px]" value={form.motif} onChange={set("motif")} /></Field>
        <Field label="Harga Dasar (per unit)">
          <DecimalInput data-testid="tpl-input-price" className="field py-2 text-[13px]" min={0}
            value={form.base_price} onChange={(v) => setForm({ ...form, base_price: v })} placeholder="175000" />
        </Field>
        <Field label={`Gramasi (gsm) ${tplRules.required.includes("gramasi") ? "*" : ""}`}>
          <DecimalInput data-testid="tpl-input-gramasi" className="field py-2 text-[13px]" min={0} suffix="gsm"
            value={form.gramasi} onChange={(v) => setForm({ ...form, gramasi: v })} placeholder="mis. 180,5" />
        </Field>
        <Field label={`Lebar (meter) ${tplRules.required.includes("lebar") ? "*" : ""}`}>
          <DecimalInput data-testid="tpl-input-lebar" className="field py-2 text-[13px]" min={0} suffix="m"
            value={form.lebar} onChange={(v) => setForm({ ...form, lebar: v })} placeholder="mis. 1,15" />
        </Field>
        {form.stage === "yarn" && (
          <>
            <Field label={`Nomor Benang ${tplRules.required.includes("yarn_count") ? "*" : ""}`}>
              <input data-testid="tpl-input-yarn_count" className="field py-2 text-[13px]" value={form.yarn_count}
                onChange={set("yarn_count")} placeholder="mis. 30s / 150D" />
            </Field>
            <Field label="Sistem Nomor Benang">
              <KNSelect data-testid="tpl-input-yarn_count_system" className="field py-2 text-[13px]"
                value={form.yarn_count_system} placeholder="Ne / Nm / Denier / Tex"
                onValueChange={(v) => setForm({ ...form, yarn_count_system: v })}
                options={options("yarn_count_system")} />
            </Field>
          </>
        )}
        <Field label="Prefix SKU"><input data-testid="tpl-input-prefix" className="field py-2 text-[13px] font-mono" value={form.sku_prefix} onChange={set("sku_prefix")} placeholder="otomatis dari nama" /></Field>
      </div>
      {tplMissing.length > 0 && (
        <p data-testid="tpl-domain-missing" className="mt-2 flex items-start gap-1 text-[11px] font-semibold text-[#D14343]">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          Wajib dilengkapi untuk stage “{labelOf("stage", form.stage)}”:{" "}
          {tplMissing.map((k) => fieldLabels[k] || k).join(", ")}.
        </p>
      )}

      <div className="mt-4">
        <div className="flex items-center justify-between mb-2">
          <label className="text-[11px] font-bold text-[#6B6B73] uppercase flex items-center gap-1"><Palette size={13} /> Axis Varian</label>
          <div className="flex gap-1">
            {AXIS_PRESETS.map((p) => (
              <button key={p.key} data-testid={`tpl-add-axis-${p.key}`} className="text-[11px] rounded border border-[#EFF0F2] px-2 py-1 hover:border-[#D9C4EC] disabled:opacity-40" disabled={axes.some((a) => a.key === p.key)} onClick={() => addAxis(p)}>+ {p.label}</button>
            ))}
          </div>
        </div>
        {axes.length === 0 ? (
          <p className="text-[11px] text-[#9A9BA3]">Tambah sumbu (Warna/Grade/Lebar) untuk membuat varian. Pisahkan opsi dengan koma.</p>
        ) : (
          <div className="space-y-2">
            {axes.map((a, idx) => (
              <div key={a.key} className="flex items-start gap-2" data-testid={`tpl-axis-${a.key}`}>
                <span className="mt-1.5 w-16 shrink-0 text-[11px] font-bold text-[#6B219A]">{a.label}</span>
                {a.key === "color" ? (
                  <div className="flex flex-1 flex-wrap items-center gap-1.5">
                    {(a.colors || []).map((c) => (
                      <span key={c.code} data-testid={`tpl-axis-color-chip-${c.code}`} className="inline-flex items-center gap-1 rounded-full border border-[#E5E5EA] bg-white px-2 py-1 text-[11px]">
                        <ColorChip hex={c.hex} size={12} /> <span className="font-semibold">{c.code}</span>
                        <button className="text-[#A8221A]" onClick={() => removeColor(idx, c.code)} aria-label="Hapus warna"><X size={11} /></button>
                      </span>
                    ))}
                    <PantoneFinder compact value="" onSelect={(c) => addColor(idx, c)} label="Tambah Warna" triggerTestId="tpl-axis-color-add" />
                  </div>
                ) : (
                  <input data-testid={`tpl-axis-options-${a.key}`} className="field flex-1 py-1.5 text-[12px]" value={a.optionsText} onChange={(e) => updateAxisOptions(idx, e.target.value)} placeholder={AXIS_PRESETS.find((p) => p.key === a.key)?.placeholder} />
                )}
                <button className="icon-button mt-0.5 text-[#C0392B]" onClick={() => removeAxis(idx)} aria-label="Hapus axis"><X size={14} /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2 pt-4 mt-2 border-t border-[#EFF0F2]">
        <button className="btn-secondary text-[12px] py-1.5 px-4" onClick={onClose}>Batal</button>
        <button data-testid="tpl-save" className="btn-primary text-[12px] py-1.5 px-4 inline-flex items-center gap-1" onClick={save} disabled={saving}><Save size={14} /> {saving ? "Menyimpan…" : "Simpan"}</button>
      </div>
    </Modal>
  );
}

// ─── Generate Varian Modal ───────────────────────────────────────────────────
function GenerateModal({ template, onClose, onDone, onError }) {
  const [selectedOpts, setSelectedOpts] = useState(
    Object.fromEntries((template.axes || []).map((a) => [a.key, new Set(a.options.map((o) => o.code))])));
  const [basePrice, setBasePrice] = useState(template.base_price || "");
  const [generating, setGenerating] = useState(false);

  const toggle = (axKey, code) => {
    setSelectedOpts((prev) => {
      const s = new Set(prev[axKey]); s.has(code) ? s.delete(code) : s.add(code);
      return { ...prev, [axKey]: s };
    });
  };
  const count = (template.axes || []).reduce((acc, a) => acc * Math.max(0, (selectedOpts[a.key] || new Set()).size), 1);

  const run = async () => {
    if (!count) { onError("Pilih minimal satu opsi pada tiap axis."); return; }
    setGenerating(true);
    const axesPayload = (template.axes || []).map((a) => ({
      key: a.key, label: a.label,
      options: a.options.filter((o) => (selectedOpts[a.key] || new Set()).has(o.code)),
    })).filter((a) => a.options.length);
    try {
      const res = await axios.post(`${API}/product-templates/${template.id}/generate-variants`,
        { axes: axesPayload, base_price: parseFloat(basePrice) || undefined });
      onDone(res.data);
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal generate varian.");
      setGenerating(false);
    }
  };

  return (
    <Modal title={`Buat Varian · ${template.name}`} icon={Wand2} onClose={onClose} testId="tpl-generate-modal">
      <div className="space-y-3 text-[12px]">
        {(template.axes || []).length === 0 ? (
          <p className="text-[12px] text-[#C0392B]">Template belum punya sumbu. Ubah template & tambah Warna/Grade/Lebar dulu.</p>
        ) : (template.axes || []).map((a) => (
          <div key={a.key}>
            <p className="text-[11px] font-bold text-[#6B6B73] uppercase mb-1.5">{a.label}</p>
            <div className="flex flex-wrap gap-1.5">
              {a.options.map((o) => {
                const on = (selectedOpts[a.key] || new Set()).has(o.code);
                return (
                  <button key={o.code} data-testid={`gen-opt-${a.key}-${o.code}`} onClick={() => toggle(a.key, o.code)}
                    className={`text-[11px] rounded-full px-2.5 py-1 border ${on ? "bg-[#6B219A] text-white border-[#6B219A]" : "bg-white border-[#EFF0F2] text-[#6B6B73]"}`}>{o.label}</button>
                );
              })}
            </div>
          </div>
        ))}
        <div className="grid grid-cols-2 gap-3 pt-2">
          <Field label="Harga Dasar Varian"><input data-testid="gen-base-price" type="number" className="field py-2 text-[13px]" value={basePrice} onChange={(e) => setBasePrice(e.target.value)} /></Field>
          <div className="flex items-end">
            <div className="rounded-md bg-[#FBF8FE] border border-[#E5D4F4] px-3 py-2 w-full text-center">
              <span className="text-[10px] text-[#9A9BA3] block">Akan dibuat</span>
              <span className="text-[18px] font-bold text-[#6B219A] tabular-nums" data-testid="gen-count">{count}</span><span className="text-[11px] text-[#6B6B73]"> SKU</span>
            </div>
          </div>
        </div>
      </div>
      <div className="flex justify-end gap-2 pt-4 mt-2 border-t border-[#EFF0F2]">
        <button className="btn-secondary text-[12px] py-1.5 px-4" onClick={onClose}>Batal</button>
        <button data-testid="gen-run" className="btn-primary text-[12px] py-1.5 px-4 inline-flex items-center gap-1" onClick={run} disabled={generating || !count}><Wand2 size={14} /> {generating ? "Membuat…" : `Generate ${count} Varian`}</button>
      </div>
    </Modal>
  );
}
