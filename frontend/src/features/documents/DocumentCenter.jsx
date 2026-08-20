// DocumentCenter (Pusat Dokumen) — daftar semua dokumen per jenis + aksi:
// Pratinjau, Unduh PDF, dan E-Sign (untuk dokumen yang esignable).
import { useCallback, useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import ESignModal from "./ESignModal";
import WhatsAppModal from "./WhatsAppModal";
import WhatsAppSettings from "./WhatsAppSettings";
import {
  FileText, Eye, Download, PenLine, Search, Loader2, X, ShieldCheck, RefreshCw, FileWarning,
  MessageCircle, Settings, Route,
} from "lucide-react";
import { openTrace } from "./trace/traceDeepLink";

const ESIGN_ROLES = ["admin", "manager", "sales", "warehouse"];
const WA_MANAGE_ROLES = ["admin", "manager"];
const rp = (n) => "Rp " + (Number(n || 0)).toLocaleString("id-ID");

export default function DocumentCenter({ currentUser, selectedEntity, entities = [] }) {
  const [docTypes, setDocTypes] = useState([]);
  const [docType, setDocType] = useState("");
  const [entityId, setEntityId] = useState(selectedEntity || "all");
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState(null);     // {html, doc, loading}
  const [esignDoc, setEsignDoc] = useState(null);
  const [waDoc, setWaDoc] = useState(null);
  const [showWaSettings, setShowWaSettings] = useState(false);
  const [downloading, setDownloading] = useState("");

  const canSign = ESIGN_ROLES.includes(currentUser?.role);
  const canManageWa = WA_MANAGE_ROLES.includes(currentUser?.role);

  const docTypeOptions = useMemo(() => docTypes.map((d) => ({ value: d.doc_type, label: d.label })), [docTypes]);
  const entityOptions = useMemo(
    () => [{ value: "all", label: "Semua Entitas" }, ...entities.map((e) => ({ value: e.id, label: e.legal_name || e.short_name || e.id }))],
    [entities]);
  const currentLabel = useMemo(() => docTypes.find((d) => d.doc_type === docType)?.label || "", [docTypes, docType]);
  const isEsignable = useMemo(() => docTypes.find((d) => d.doc_type === docType)?.esignable, [docTypes, docType]);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/pdf/doc-types`);
        setDocTypes(r.data || []);
        if (r.data?.length) setDocType((p) => p || r.data[0].doc_type);
      } catch (e) { setErr("Gagal memuat jenis dokumen."); }
    })();
  }, []);

  const load = useCallback(async () => {
    if (!docType) return;
    setLoading(true); setErr("");
    try {
      const r = await axios.get(`${API}/pdf/documents/${docType}`, {
        params: { entity_id: entityId, q: search || undefined, limit: 150 },
      });
      setRows(r.data.documents || []);
    } catch (e) { setErr(e.response?.data?.detail || "Gagal memuat dokumen."); setRows([]); }
    finally { setLoading(false); }
  }, [docType, entityId, search]);

  // debounce load on filters/search
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [load]);

  const openPreview = async (d) => {
    const docMeta = { doc_type: docType, source_id: d.source_id, entity_id: d.entity_id, number: d.number, label: currentLabel };
    setPreview({ html: "", doc: docMeta, loading: true });
    try {
      const r = await axios.get(`${API}/pdf/render/${docType}/${d.source_id}`, {
        params: { format: "html", entity_id: d.entity_id || undefined },
        headers: { Accept: "text/html" },
      });
      setPreview({ html: typeof r.data === "string" ? r.data : "", doc: docMeta, loading: false });
    } catch (e) {
      setPreview({ html: "", doc: docMeta, loading: false, error: "Gagal memuat pratinjau." });
    }
  };

  const downloadPdf = async (d) => {
    setDownloading(d.source_id);
    try {
      const r = await axios.get(`${API}/pdf/render/${docType}/${d.source_id}`, {
        params: { format: "pdf", entity_id: d.entity_id || undefined, download: true },
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${docType}-${d.number || d.source_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setErr("Gagal mengunduh PDF."); }
    finally { setDownloading(""); }
  };

  return (
    <div className="grid gap-4" data-testid="document-center">
      {/* Toolbar */}
      <section className="section-card">
        <div className="section-body flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <label className="kicker flex items-center gap-1"><FileText size={12} /> Jenis Dokumen</label>
            <KNSelect value={docType} onValueChange={setDocType} options={docTypeOptions}
              className="field !w-[240px]" searchable placeholder="Pilih dokumen…" data-testid="dc-doctype-select" />
          </div>
          <div className="grid gap-1">
            <label className="kicker">Entitas</label>
            <KNSelect value={entityId} onValueChange={setEntityId} options={entityOptions}
              className="field !w-[210px]" data-testid="dc-entity-select" />
          </div>
          <div className="grid gap-1 flex-1 min-w-[200px]">
            <label className="kicker">Cari</label>
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input className="form-input !pl-8" placeholder="Nomor / pihak / status…" value={search}
                onChange={(e) => setSearch(e.target.value)} data-testid="dc-search" />
            </div>
          </div>
          <button className="btn-secondary flex items-center gap-1.5" onClick={load} data-testid="dc-refresh">
            <RefreshCw size={14} /> Segarkan
          </button>
          {canManageWa && (
            <button className="btn-secondary flex items-center gap-1.5" onClick={() => setShowWaSettings(true)} data-testid="dc-wa-settings">
              <Settings size={14} /> Pengaturan WA
            </button>
          )}
        </div>
        {err && <div className="px-4 pb-3"><div className="notice-bar danger !py-1.5"><span className="text-[11.5px]">{err}</span></div></div>}
      </section>

      {/* Table */}
      <section className="section-card">
        <div className="section-head flex items-center justify-between">
          <h2 className="text-[13px] font-bold">{currentLabel || "Dokumen"} <span className="text-[#9A9BA3] font-normal">({rows.length})</span></h2>
          {loading && <Loader2 size={14} className="animate-spin text-[#0058CC]" />}
        </div>
        <div className="section-body overflow-x-auto">
          {rows.length === 0 && !loading ? (
            <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
              <FileWarning size={26} className="text-[#C4C5CC]" />
              <p className="text-[12.5px] font-semibold text-[#6B6B73]">Tidak ada dokumen</p>
              <p className="text-[11.5px] text-[#9A9BA3]">Coba ubah jenis dokumen, entitas, atau kata kunci.</p>
            </div>
          ) : (
            <table className="w-full text-[12.5px]" data-testid="dc-table">
              <thead>
                <tr className="border-b border-[#EDEEF1] text-left text-[10.5px] uppercase tracking-wide text-[#9A9BA3]">
                  <th className="px-2 py-2">Nomor</th>
                  <th className="px-2 py-2">Tanggal</th>
                  <th className="px-2 py-2">Pihak</th>
                  <th className="px-2 py-2 text-right">Nilai</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Tanda Tangan</th>
                  <th className="px-2 py-2">Referensi</th>
                  <th className="px-2 py-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.source_id} className="border-b border-[#F2F3F5] hover:bg-[#FAFBFC]" data-testid={`dc-row-${d.source_id}`}>
                    <td className="px-2 py-2 font-semibold text-[#0B1B3B]">{d.number}</td>
                    <td className="px-2 py-2 text-[#6B6B73]">{d.date || "-"}</td>
                    <td className="px-2 py-2">{d.party || "-"}</td>
                    <td className="px-2 py-2 text-right font-medium tabular-nums">{rp(d.amount)}</td>
                    <td className="px-2 py-2"><span className="rounded-full bg-[#F1F2F4] px-2 py-0.5 text-[10.5px] font-medium capitalize text-[#4A4B52]">{d.status || "-"}</span></td>
                    <td className="px-2 py-2">
                      {d.signed ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-[#ECFAF1] px-2 py-0.5 text-[10.5px] font-semibold text-[#1F7A45]" title={`Kode: ${d.verification_code}`} data-testid={`dc-signed-${d.source_id}`}>
                          <ShieldCheck size={11} /> {d.verification_code}
                        </span>
                      ) : (
                        <span className="text-[11px] text-[#9A9BA3]">Belum</span>
                      )}
                    </td>
                    <td className="px-2 py-2">
                      {/* FASE G-4 — surat ini menyebut surat lain? langsung ke Jejak Dokumen. */}
                      {d.trace_type ? (
                        <button type="button" data-testid={`dc-trace-${d.source_id}`}
                          title="Buka Jejak Dokumen (rantai surat terkait)"
                          onClick={() => openTrace({ docType: d.trace_type, docId: d.source_id, number: d.number })}
                          className="inline-flex items-center gap-1 rounded-full border border-[#BBD3FF] bg-[#EAF2FF] px-2 py-0.5 text-[10.5px] font-semibold text-[#0058CC] hover:bg-[#DBEAFE]">
                          <Route size={11} /> {d.ref_count || 0} surat
                        </button>
                      ) : (
                        <span className="text-[11px] text-[#9A9BA3]">—</span>
                      )}
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex items-center justify-end gap-1">
                        <IconBtn title="Pratinjau" onClick={() => openPreview(d)} testId={`dc-preview-${d.source_id}`}><Eye size={15} /></IconBtn>
                        <IconBtn title="Unduh PDF" onClick={() => downloadPdf(d)} testId={`dc-download-${d.source_id}`}>
                          {downloading === d.source_id ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
                        </IconBtn>
                        {d.esignable && canSign && (
                          <IconBtn title="Tanda Tangan Elektronik" tone="primary" onClick={() => setEsignDoc({ doc_type: docType, source_id: d.source_id, entity_id: d.entity_id, number: d.number, label: currentLabel })} testId={`dc-esign-${d.source_id}`}>
                            <PenLine size={15} />
                          </IconBtn>
                        )}
                        <IconBtn title="Kirim via WhatsApp" tone={d.last_delivery ? "wa-sent" : "wa"} onClick={() => setWaDoc({ doc_type: docType, source_id: d.source_id, entity_id: d.entity_id, number: d.number, label: currentLabel })} testId={`dc-wa-${d.source_id}`}>
                          <MessageCircle size={15} />
                        </IconBtn>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/45 p-4" data-testid="dc-preview-modal">
          <div className="flex w-full max-w-[820px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl" style={{ maxHeight: "92vh" }}>
            <div className="flex items-center justify-between border-b border-[#EDEEF1] px-5 py-3">
              <h3 className="text-[14px] font-bold">Pratinjau · {preview.doc?.number || preview.doc?.source_id}</h3>
              <div className="flex items-center gap-2">
                <button className="btn-secondary flex items-center gap-1.5 !py-1" onClick={() => downloadPdf({ source_id: preview.doc.source_id, entity_id: preview.doc.entity_id, number: preview.doc.number })}>
                  <Download size={13} /> Unduh PDF
                </button>
                <button onClick={() => setPreview(null)} className="text-[#9A9BA3] hover:text-[#1a1a1a]" data-testid="dc-preview-close"><X size={18} /></button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden bg-[#F2F3F5] p-3">
              {preview.loading ? (
                <div className="flex h-full items-center justify-center"><Loader2 size={24} className="animate-spin text-[#0058CC]" /></div>
              ) : preview.error ? (
                <div className="notice-bar danger"><span>{preview.error}</span></div>
              ) : (
                <iframe title="Pratinjau" srcDoc={preview.html} sandbox="allow-same-origin"
                  className="h-full w-full rounded-lg border border-[#E5E6EB] bg-white" style={{ minHeight: "70vh" }} data-testid="dc-preview-frame" />
              )}
            </div>
          </div>
        </div>
      )}

      {/* E-Sign modal */}
      <ESignModal open={!!esignDoc} onClose={() => setEsignDoc(null)} doc={esignDoc} currentUser={currentUser} onSigned={load} />
      {/* WhatsApp modals */}
      <WhatsAppModal open={!!waDoc} onClose={() => setWaDoc(null)} doc={waDoc} onSent={load} />
      <WhatsAppSettings open={showWaSettings} onClose={() => setShowWaSettings(false)} />
    </div>
  );
}

function IconBtn({ children, title, onClick, tone, testId }) {
  const tones = {
    primary: "border-[#BBD3FF] bg-[#EAF2FF] text-[#0058CC] hover:bg-[#DBEAFE]",
    wa: "border-[#BFE6CE] text-[#1F7A45] hover:bg-[#E7F8EE]",
    "wa-sent": "border-[#1F7A45] bg-[#E7F8EE] text-[#146c38] hover:bg-[#D6F0E0]",
  };
  const cls = tones[tone] || "border-[#EDEEF1] text-[#4A4B52] hover:bg-[#F2F3F5]";
  return (
    <button type="button" title={title} onClick={onClick} data-testid={testId}
      className={`flex h-8 w-8 items-center justify-center rounded-md border transition-colors ${cls}`}>
      {children}
    </button>
  );
}
