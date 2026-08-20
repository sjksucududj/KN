// PdfTemplateDesigner — Fase 3: Advanced PDF Configuration UI.
// Editor template per doc_type + branding per entitas + pratinjau HTML live (debounced)
// + unduh PDF. Konsumsi endpoint /api/pdf/* (lihat routers/pdf.py).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import PdfEditorTabs from "./PdfEditorTabs";
import {
  FileText, Download, Save, RotateCcw, Loader2, RefreshCw, FileWarning,
} from "lucide-react";

export default function PdfTemplateDesigner({ currentUser, selectedEntity, entities = [] }) {
  const [docTypes, setDocTypes] = useState([]);
  const [docType, setDocType] = useState("");
  const [config, setConfig] = useState(null);
  const [defaults, setDefaults] = useState(null);
  const [entityId, setEntityId] = useState("");
  const [branding, setBranding] = useState(null);
  const [newLogo, setNewLogo] = useState(null);       // data-URL logo baru (belum disimpan)
  const [sample, setSample] = useState(null);         // {source_id, number, entity_id, label}
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [previewNonce, setPreviewNonce] = useState(0);
  const [savingTpl, setSavingTpl] = useState(false);
  const [savingBrand, setSavingBrand] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [brandingMsg, setBrandingMsg] = useState("");
  const [brandingErr, setBrandingErr] = useState("");
  const flash = useRef(null);

  const docTypeOptions = useMemo(
    () => docTypes.map((d) => ({ value: d.doc_type, label: d.label })), [docTypes]);
  const entityOptions = useMemo(
    () => entities.map((e) => ({ value: e.id, label: e.legal_name || e.short_name || e.id })), [entities]);

  const flashMsg = useCallback((text) => {
    setMsg(text); setErr("");
    if (flash.current) clearTimeout(flash.current);
    flash.current = setTimeout(() => setMsg(""), 3500);
  }, []);

  // init entity dari konteks aktif
  useEffect(() => {
    if (!entities.length || entityId) return;
    const initial = (selectedEntity && selectedEntity !== "all" && entities.some((e) => e.id === selectedEntity))
      ? selectedEntity : entities[0].id;
    setEntityId(initial);
  }, [entities, selectedEntity, entityId]);

  // muat daftar doc types
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/pdf/doc-types`);
        setDocTypes(r.data || []);
        if (r.data?.length) setDocType((p) => p || r.data[0].doc_type);
      } catch (e) { setErr(e.response?.data?.detail || "Gagal memuat daftar dokumen."); }
    })();
  }, []);

  // muat template cfg saat docType berubah
  useEffect(() => {
    if (!docType) return;
    (async () => {
      try {
        const r = await axios.get(`${API}/pdf/templates/${docType}`);
        setConfig(r.data.config); setDefaults(r.data.defaults);
      } catch (e) { setErr(e.response?.data?.detail || "Gagal memuat template."); }
    })();
  }, [docType]);

  // muat branding saat entitas berubah
  useEffect(() => {
    if (!entityId) return;
    setNewLogo(null); setBrandingMsg(""); setBrandingErr("");
    (async () => {
      try {
        const r = await axios.get(`${API}/pdf/branding/${entityId}`);
        setBranding(r.data);
      } catch (e) { setBranding(null); }
    })();
  }, [entityId]);

  // muat sample doc saat docType/entitas berubah
  useEffect(() => {
    if (!docType) return;
    (async () => {
      try {
        const r = await axios.get(`${API}/pdf/sample/${docType}`, { params: { entity_id: entityId || undefined } });
        setSample(r.data);
      } catch (e) { setSample(null); }
    })();
  }, [docType, entityId]);

  // pratinjau debounced (config/docType/entity/sample/nonce)
  const cfgKey = config ? JSON.stringify(config) : "";
  useEffect(() => {
    if (!docType || !config) return undefined;
    if (!sample || !sample.source_id) { setPreviewHtml(""); setPreviewError(""); return undefined; }
    setPreviewLoading(true); setPreviewError("");
    const t = setTimeout(async () => {
      try {
        const r = await axios.post(`${API}/pdf/preview`, {
          doc_type: docType, source_id: sample.source_id,
          entity_id: entityId || sample.entity_id, config,
        }, { headers: { Accept: "text/html" } });
        setPreviewHtml(typeof r.data === "string" ? r.data : String(r.data || ""));
      } catch (e) {
        setPreviewError(e.response?.data?.detail || "Gagal memuat pratinjau.");
        setPreviewHtml("");
      } finally { setPreviewLoading(false); }
    }, 550);
    return () => clearTimeout(t);
  }, [cfgKey, docType, entityId, sample?.source_id, previewNonce]); // eslint-disable-line

  const patch = useCallback((k, v) => setConfig((c) => ({ ...(c || {}), [k]: v })), []);
  const patchBranding = useCallback((k, v) => setBranding((b) => ({ ...(b || {}), [k]: v })), []);

  const onLogoFile = useCallback((file) => {
    if (file.size > 1024 * 1024) { setBrandingErr("Ukuran logo maksimal 1 MB."); return; }
    const reader = new FileReader();
    reader.onload = () => { setNewLogo(reader.result); setBrandingErr(""); };
    reader.readAsDataURL(file);
  }, []);
  const onRemoveLogo = useCallback(() => {
    setNewLogo("");                                   // "" = minta hapus saat simpan
    setBranding((b) => ({ ...(b || {}), logo_src: "" }));
  }, []);

  async function saveTemplate() {
    if (!docType || !config) return;
    setSavingTpl(true); setErr("");
    try {
      const r = await axios.put(`${API}/pdf/templates/${docType}`, { config });
      setConfig(r.data.config);
      flashMsg("Template tersimpan.");
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan template."); }
    finally { setSavingTpl(false); }
  }

  async function saveBranding() {
    if (!entityId) return;
    setSavingBrand(true); setBrandingErr(""); setBrandingMsg("");
    try {
      const payload = {
        company_name: branding?.company_name || "",
        address: branding?.address || "",
        phone: branding?.phone || "",
        npwp: branding?.npwp || "",
      };
      if (newLogo !== null) payload.logo_b64 = newLogo; // data-url atau "" (hapus)
      const r = await axios.put(`${API}/pdf/branding/${entityId}`, payload);
      setBranding(r.data); setNewLogo(null);
      setBrandingMsg("Branding tersimpan.");
      setPreviewNonce((n) => n + 1);                  // segarkan pratinjau (branding server-side)
    } catch (e) { setBrandingErr(e.response?.data?.detail || "Gagal menyimpan branding."); }
    finally { setSavingBrand(false); }
  }

  function resetDefaults() {
    if (defaults) { setConfig({ ...defaults }); flashMsg("Dikembalikan ke default (belum disimpan)."); }
  }

  async function downloadPdf() {
    if (!sample?.source_id) return;
    setDownloading(true); setErr("");
    try {
      const r = await axios.get(`${API}/pdf/render/${docType}/${sample.source_id}`, {
        params: { format: "pdf", entity_id: entityId || sample.entity_id, download: true },
        responseType: "blob",
      });
      const blobUrl = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = blobUrl; a.download = `${docType}-${sample.number || sample.source_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(blobUrl);
      flashMsg("PDF diunduh.");
    } catch (e) { setErr("Gagal mengunduh PDF."); }
    finally { setDownloading(false); }
  }

  const hasSample = !!(sample && sample.source_id);

  return (
    <div className="grid gap-4" data-testid="pdf-template-designer">
      {/* Toolbar */}
      <section className="section-card">
        <div className="section-body flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <label className="kicker flex items-center gap-1"><FileText size={12} /> Jenis Dokumen</label>
            <KNSelect value={docType} onValueChange={setDocType} options={docTypeOptions}
              className="field !w-[240px]" searchable placeholder="Pilih dokumen…" data-testid="pdf-doctype-select" />
          </div>
          <div className="grid gap-1">
            <label className="kicker">Entitas (PT)</label>
            <KNSelect value={entityId} onValueChange={setEntityId} options={entityOptions}
              className="field !w-[220px]" placeholder="Pilih entitas…" data-testid="pdf-entity-select" />
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button className="btn-secondary flex items-center gap-1.5" onClick={resetDefaults} data-testid="pdf-reset-default">
              <RotateCcw size={14} /> Reset Default
            </button>
            <button className="btn-secondary flex items-center gap-1.5" onClick={downloadPdf}
              disabled={downloading || !hasSample} data-testid="pdf-download">
              {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Unduh PDF
            </button>
            <button className="btn-primary flex items-center gap-1.5" onClick={saveTemplate}
              disabled={savingTpl || !config} data-testid="pdf-save-template">
              {savingTpl ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Simpan Template
            </button>
          </div>
        </div>
        {(msg || err) && (
          <div className="px-4 pb-3">
            {msg && <div className="notice-bar success !py-1.5" data-testid="pdf-msg"><span className="text-[11.5px]">{msg}</span></div>}
            {err && <div className="notice-bar danger !py-1.5" data-testid="pdf-err"><span className="text-[11.5px]">{err}</span></div>}
          </div>
        )}
      </section>

      {/* Editor + Preview */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)] items-start">
        {config ? (
          <PdfEditorTabs
            config={config} patch={patch}
            branding={branding} patchBranding={patchBranding}
            onLogoFile={onLogoFile} onRemoveLogo={onRemoveLogo} onSaveBranding={saveBranding}
            savingBrand={savingBrand} brandingMsg={brandingMsg} brandingErr={brandingErr}
            newLogoPreview={newLogo}
          />
        ) : (
          <section className="section-card"><div className="section-body text-[12px] text-[#9A9BA3] py-6">Memuat konfigurasi…</div></section>
        )}

        {/* Preview pane */}
        <section className="section-card" data-testid="pdf-preview-pane">
          <div className="section-head flex items-center justify-between">
            <h2 className="text-[13px] font-bold flex items-center gap-2">
              Pratinjau
              {sample?.number && <span className="rounded-full bg-[#EAF2FF] px-2 py-0.5 text-[10.5px] font-semibold text-[#0058CC]">{sample.number}</span>}
              {previewLoading && <Loader2 size={13} className="animate-spin text-[#0058CC]" />}
            </h2>
            <button className="btn-secondary flex items-center gap-1.5 !py-1" onClick={() => setPreviewNonce((n) => n + 1)}
              disabled={!hasSample} data-testid="pdf-preview-refresh">
              <RefreshCw size={13} /> Segarkan
            </button>
          </div>
          <div className="section-body">
            {!hasSample ? (
              <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[#D6D7DC] bg-[#FAFBFC] py-16 text-center">
                <FileWarning size={26} className="text-[#C4C5CC]" />
                <p className="text-[12.5px] font-semibold text-[#6B6B73]">Belum ada data {sample?.label || "dokumen"} untuk entitas ini</p>
                <p className="text-[11.5px] text-[#9A9BA3] max-w-[320px]">Buat dokumen dulu, atau pilih entitas/jenis dokumen lain untuk melihat pratinjau.</p>
              </div>
            ) : previewError ? (
              <div className="notice-bar danger" data-testid="pdf-preview-error"><span className="text-[12px]">{previewError}</span></div>
            ) : (
              <iframe
                title="Pratinjau PDF"
                srcDoc={previewHtml}
                data-testid="pdf-preview-frame"
                sandbox="allow-same-origin"
                className="w-full rounded-lg border border-[#E5E6EB] bg-white"
                style={{ height: "78vh" }}
              />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
