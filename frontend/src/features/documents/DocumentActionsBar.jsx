// DocumentActionsBar — bar aksi dokumen reusable untuk detail-view tiap modul:
// Pratinjau · Unduh PDF · Tanda Tangan (E-Sign) · Kirim WhatsApp.
// Menggunakan kembali ESignModal & WhatsAppModal (Pusat Dokumen).
import { useCallback, useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import ESignModal from "./ESignModal";
import WhatsAppModal from "./WhatsAppModal";
import { Eye, Download, PenLine, MessageCircle, Loader2, X, ShieldCheck } from "lucide-react";

const ESIGN_ROLES = ["admin", "manager", "sales", "warehouse"];

// Cache jenis dokumen (label + esignable) agar tidak fetch berulang lintas komponen.
let _docTypesCache = null;
let _docTypesPromise = null;
async function fetchDocTypes() {
  if (_docTypesCache) return _docTypesCache;
  if (!_docTypesPromise) {
    _docTypesPromise = axios.get(`${API}/pdf/doc-types`)
      .then((r) => { _docTypesCache = r.data || []; return _docTypesCache; })
      .catch(() => { _docTypesPromise = null; return []; });
  }
  return _docTypesPromise;
}

export default function DocumentActionsBar({
  docType, sourceId, entityId, number, label: labelProp,
  currentUser, esignable: esignableProp, onChanged, className = "", compact = false,
  autoCheckSignature = true,
}) {
  const [meta, setMeta] = useState({ label: labelProp || "", esignable: esignableProp });
  const [preview, setPreview] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [esignOpen, setEsignOpen] = useState(false);
  const [waOpen, setWaOpen] = useState(false);
  const [signed, setSigned] = useState(null); // {verification_code}
  const [err, setErr] = useState("");

  const canSign = ESIGN_ROLES.includes(currentUser?.role);

  useEffect(() => {
    if (esignableProp !== undefined && labelProp) {
      setMeta({ label: labelProp, esignable: esignableProp });
      return;
    }
    let active = true;
    fetchDocTypes().then((dts) => {
      const d = dts.find((x) => x.doc_type === docType);
      if (active && d) setMeta({ label: labelProp || d.label, esignable: esignableProp ?? d.esignable });
    });
    return () => { active = false; };
  }, [docType, labelProp, esignableProp]);

  // Cek status tanda tangan terkini (untuk badge).
  // `force` melewati gate autoCheckSignature agar badge tetap muncul setelah
  // user menandatangani (aksi eksplisit tunggal, bukan fetch massal di list).
  const loadSignature = useCallback(async (force = false) => {
    if (!sourceId || (!autoCheckSignature && !force)) return;
    try {
      const r = await axios.get(`${API}/esign/signatures/${docType}/${sourceId}`);
      const sigs = r.data?.signatures || [];
      setSigned(sigs.length ? { verification_code: sigs[0].verification_code } : null);
    } catch (e) { /* ignore */ }
  }, [docType, sourceId, autoCheckSignature]);

  useEffect(() => { loadSignature(); }, [loadSignature]);

  const docObj = { doc_type: docType, source_id: sourceId, entity_id: entityId, number, label: meta.label };

  const openPreview = async () => {
    setPreview({ html: "", loading: true });
    try {
      const r = await axios.get(`${API}/pdf/render/${docType}/${sourceId}`, {
        params: { format: "html", entity_id: entityId || undefined },
        headers: { Accept: "text/html" },
      });
      setPreview({ html: typeof r.data === "string" ? r.data : "", loading: false });
    } catch (e) {
      setPreview({ html: "", loading: false, error: "Gagal memuat pratinjau." });
    }
  };

  const downloadPdf = async () => {
    setDownloading(true); setErr("");
    try {
      const r = await axios.get(`${API}/pdf/render/${docType}/${sourceId}`, {
        params: { format: "pdf", entity_id: entityId || undefined, download: true },
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${docType}-${number || sourceId}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setErr("Gagal mengunduh PDF."); }
    finally { setDownloading(false); }
  };

  if (!sourceId) return null;
  const btnCls = compact
    ? "flex h-8 w-8 items-center justify-center rounded-md border transition-colors"
    : "flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] font-semibold transition-colors";

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`} data-testid={`doc-actions-${docType}`}>
      <button type="button" onClick={openPreview} title="Pratinjau"
        className={`${btnCls} border-[#EDEEF1] text-[#4A4B52] hover:bg-[#F2F3F5]`} data-testid="doc-act-preview">
        <Eye size={15} />{!compact && "Pratinjau"}
      </button>
      <button type="button" onClick={downloadPdf} title="Unduh PDF" disabled={downloading}
        className={`${btnCls} border-[#EDEEF1] text-[#4A4B52] hover:bg-[#F2F3F5]`} data-testid="doc-act-download">
        {downloading ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}{!compact && "Unduh PDF"}
      </button>
      {meta.esignable && canSign && (
        <button type="button" onClick={() => setEsignOpen(true)} title="Tanda Tangan Elektronik"
          className={`${btnCls} border-[#BBD3FF] bg-[#EAF2FF] text-[#0058CC] hover:bg-[#DBEAFE]`} data-testid="doc-act-esign">
          <PenLine size={15} />{!compact && (signed ? "Tanda Tangan Ulang" : "Tanda Tangan")}
        </button>
      )}
      <button type="button" onClick={() => setWaOpen(true)} title="Kirim via WhatsApp"
        className={`${btnCls} border-[#BFE6CE] text-[#1F7A45] hover:bg-[#E7F8EE]`} data-testid="doc-act-wa">
        <MessageCircle size={15} />{!compact && "Kirim WA"}
      </button>
      {signed && (
        <span className="inline-flex items-center gap-1 rounded-full bg-[#ECFAF1] px-2 py-0.5 text-[10.5px] font-semibold text-[#1F7A45]"
          title={`Kode verifikasi: ${signed.verification_code}`} data-testid="doc-act-signed-badge">
          <ShieldCheck size={11} /> {signed.verification_code}
        </span>
      )}
      {err && <span className="text-[11px] font-medium text-[#C0392B]">{err}</span>}

      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/45 p-4" data-testid="doc-act-preview-modal"
          onClick={(e) => { if (e.target === e.currentTarget) setPreview(null); }}>
          <div className="flex w-full max-w-[820px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" style={{ maxHeight: "92vh" }}>
            <div className="flex items-center justify-between border-b border-[#EDEEF1] px-5 py-3">
              <h3 className="text-[14px] font-bold">Pratinjau · {number || sourceId}</h3>
              <div className="flex items-center gap-2">
                <button className="btn-secondary flex items-center gap-1.5 !py-1" onClick={downloadPdf}>
                  <Download size={13} /> Unduh PDF
                </button>
                <button onClick={() => setPreview(null)} className="text-[#9A9BA3] hover:text-[#1a1a1a]" data-testid="doc-act-preview-close"><X size={18} /></button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden bg-[#F2F3F5] p-3">
              {preview.loading ? (
                <div className="flex h-full items-center justify-center"><Loader2 size={24} className="animate-spin text-[#0058CC]" /></div>
              ) : preview.error ? (
                <div className="notice-bar danger"><span>{preview.error}</span></div>
              ) : (
                <iframe title="Pratinjau" srcDoc={preview.html} sandbox="allow-same-origin"
                  className="h-full w-full rounded-lg border border-[#E5E6EB] bg-white" style={{ minHeight: "70vh" }} data-testid="doc-act-preview-frame" />
              )}
            </div>
          </div>
        </div>
      )}

      <ESignModal open={esignOpen} onClose={() => setEsignOpen(false)} doc={docObj} currentUser={currentUser}
        onSigned={() => { loadSignature(true); onChanged && onChanged(); }} />
      <WhatsAppModal open={waOpen} onClose={() => setWaOpen(false)} doc={docObj}
        onSent={() => { onChanged && onChanged(); }} />
    </div>
  );
}
