/**
 * DocRefsPanel — FASE G-4 · panel **Referensi Dokumen** untuk layar detail.
 *
 * Dipasang di detail SO / PO / Tagihan Supplier / Kwitansi / Penerimaan Barang.
 * Menjawab pertanyaan yang dulu harus dijawab manual: "surat ini berasal dari mana,
 * dan surat apa saja yang lahir darinya?" — plus satu klik ke **Jejak Dokumen**
 * untuk melihat seluruh rantainya.
 *
 * Sengaja ringan: hanya `GET /documents/refs/...` (bukan graf penuh).
 */
import { useCallback, useEffect, useState } from "react";
import { ExternalLink, GitBranch, Loader2, RefreshCw } from "lucide-react";
import { errText, fetchRefs, relTone } from "./traceApi";
import { openTrace } from "./traceDeepLink";

export default function DocRefsPanel({ docType, docId, onOpenDocument, compact = false }) {
  const [rows, setRows] = useState([]);
  const [number, setNumber] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    if (!docType || !docId) return;
    setLoading(true);
    try {
      const res = await fetchRefs(docType, docId);
      setRows(res.refs || []);
      setNumber(res.number || "");
      setErr("");
    } catch (e) {
      setErr(errText(e, "Gagal memuat referensi dokumen."));
      setRows([]);
    } finally { setLoading(false); }
  }, [docType, docId]);

  useEffect(() => { load(); }, [load]);

  const upstream = rows.filter((r) => relTone(r.rel) !== "downstream");
  const downstream = rows.filter((r) => relTone(r.rel) === "downstream");

  const Row = ({ r }) => {
    const tone = relTone(r.rel);
    return (
      <div data-testid={`docrefs-row-${r.doc_id}`}
        className="flex items-center justify-between gap-2 rounded-md border border-[#EFF0F2] bg-white px-2 py-1.5">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="rounded px-1.5 py-0.5 text-[8.5px] font-bold uppercase tracking-wide"
              style={{ background: tone.bg, color: tone.fg }}>{r.rel_label || r.rel}</span>
            <span className="truncate text-[11px] font-bold text-[#0058CC]">{r.doc_number || r.doc_id}</span>
          </div>
          <p className="truncate text-[9.5px] text-[#8E8E93]">
            {r.label}{r.status ? ` · ${r.status}` : ""}{r.alive === false ? " · dokumen sudah tidak ada" : ""}
            {r.note ? ` · ${r.note}` : ""}
          </p>
        </div>
        {r.link?.view && onOpenDocument && (
          <button type="button" title="Buka dokumen" data-testid={`docrefs-open-${r.doc_id}`}
            onClick={() => onOpenDocument(r.link)}
            className="shrink-0 rounded-md border border-[#EDEEF1] p-1 text-[#4A4B52] hover:bg-[#F2F3F5]">
            <ExternalLink size={12} />
          </button>
        )}
      </div>
    );
  };

  return (
    <div data-testid="doc-refs-panel"
      className="rounded-lg border border-[#EDEEF1] bg-[#FAFBFC] p-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          <GitBranch size={12} className="text-[#0058CC]" /> Referensi Dokumen
          {rows.length > 0 && (
            <span className="rounded-full bg-[#EFF4FF] px-1.5 text-[9px] font-bold text-[#0058CC]">{rows.length}</span>
          )}
        </p>
        <div className="flex items-center gap-1">
          <button type="button" title="Muat ulang referensi" data-testid="docrefs-refresh"
            onClick={load} className="rounded-md border border-[#EDEEF1] bg-white p-1 text-[#4A4B52] hover:bg-[#F2F3F5]">
            {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          </button>
          <button type="button" data-testid="docrefs-open-trace"
            onClick={() => openTrace({ docType, docId, number })}
            className="rounded-md border border-[#BBD3FF] bg-[#EAF2FF] px-2 py-1 text-[10px] font-semibold text-[#0058CC] hover:bg-[#DBEAFE]">
            Buka Jejak Dokumen
          </button>
        </div>
      </div>

      {loading && (
        <p className="animate-pulse py-3 text-center text-[11px] text-[#6B6B73]">Memuat referensi…</p>
      )}

      {!loading && err && (
        <div className="flex items-center justify-between gap-2 rounded-md border border-[#F5C2C7] bg-[#FDE2E2] px-2 py-1.5">
          <span data-testid="docrefs-error" className="text-[10.5px] text-[#9B1C1C]">{err}</span>
          <button type="button" onClick={load} data-testid="docrefs-retry"
            className="rounded border border-[#E5A6AB] bg-white px-2 py-0.5 text-[10px] font-semibold text-[#9B1C1C]">
            Coba lagi
          </button>
        </div>
      )}

      {!loading && !err && rows.length === 0 && (
        <p data-testid="docrefs-empty" className="py-2 text-[10.5px] text-[#6B6B73]">
          Belum ada surat lain yang tertaut ke dokumen ini.
        </p>
      )}

      {!loading && !err && rows.length > 0 && (
        <div className="space-y-2">
          {upstream.length > 0 && (
            <div className="space-y-1">
              {!compact && (
                <p className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Berasal dari</p>
              )}
              {upstream.map((r) => <Row key={`${r.rel}-${r.doc_id}`} r={r} />)}
            </div>
          )}
          {downstream.length > 0 && (
            <div className="space-y-1">
              {!compact && (
                <p className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Menurunkan</p>
              )}
              {downstream.map((r) => <Row key={`${r.rel}-${r.doc_id}`} r={r} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
