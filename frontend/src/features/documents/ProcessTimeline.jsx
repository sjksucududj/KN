import { useEffect, useState } from "react";
import {
  GitBranch, FileText, Truck, Receipt, Wallet, Coins, ClipboardList,
  Package, PackageCheck, Layers, ExternalLink, Printer, ChevronRight, Circle, RefreshCw,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import { formatCurrency } from "../../utils/formatters";

/**
 * EPIC6 — ProcessTimeline / Document Hub (generic).
 *
 * Menampilkan rantai dokumen terkait (read-only) + deep-link in-app.
 * Sumber: GET /api/documents/relations/{docType}/{docId}.
 *   - docType: "sales_order" | "purchase_order"
 *   - onNavigate(link): callback navigasi in-app (App.js openDocument).
 * Stage kosong tetap ditampilkan (no dead-end) dengan empty_hint.
 */

const TYPE_META = {
  special_order:         { Icon: FileText,      tone: "#6B219A", bg: "#F3E8FF" },
  sales_order:           { Icon: FileText,      tone: "#0058CC", bg: "#EFF4FF" },
  shipment:              { Icon: Truck,         tone: "#0058CC", bg: "#EFF4FF" },
  tax_invoice:           { Icon: Receipt,       tone: "#15803D", bg: "#E9F7EF" },
  ar_receipt:            { Icon: Wallet,        tone: "#15803D", bg: "#E9F7EF" },
  commission:            { Icon: Coins,         tone: "#9A5B00", bg: "#FFF7EC" },
  purchase_requisition:  { Icon: ClipboardList, tone: "#6B219A", bg: "#F3E8FF" },
  purchase_order:        { Icon: Package,       tone: "#0058CC", bg: "#EFF4FF" },
  grn:                   { Icon: PackageCheck,  tone: "#15803D", bg: "#E9F7EF" },
  landed_cost:           { Icon: Layers,        tone: "#9A5B00", bg: "#FFF7EC" },
  vendor_bill:           { Icon: Wallet,        tone: "#B23B14", bg: "#FFF1EA" },
};

function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" });
  } catch { return ""; }
}

function DocNode({ node, isAnchor, onNavigate }) {
  const meta = TYPE_META[node.type] || { Icon: FileText, tone: "#6B6B73", bg: "#F3F4F6" };
  const Icon = meta.Icon;
  const link = node.link || {};
  const canNavigate = !isAnchor && link.kind !== "none" && (link.view || link.doc_url);
  const printUrl = link.doc_url ? `${API}${link.doc_url}` : null;

  const handleMain = () => {
    if (isAnchor) return;
    if (link.view) onNavigate?.(link);
    else if (printUrl) window.open(printUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div
      data-testid={`doc-node-${node.type}-${node.id || "x"}`}
      className={`group flex items-center gap-2 rounded-md border px-2.5 py-1.5 transition-colors ${
        isAnchor
          ? "border-[#0058CC] bg-[#EFF4FF]"
          : "border-[#EFF0F2] bg-white hover:border-[#C9DBF7] hover:bg-[#FAFBFF] cursor-pointer"
      }`}
      onClick={canNavigate ? handleMain : undefined}
      role={canNavigate ? "button" : undefined}
      tabIndex={canNavigate ? 0 : undefined}
      onKeyDown={canNavigate ? (e) => { if (e.key === "Enter") handleMain(); } : undefined}
    >
      <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full" style={{ background: meta.bg, color: meta.tone }}>
        <Icon size={13} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="truncate text-[11.5px] font-bold text-[#1C1C1E]">{node.number || node.title}</p>
          {node.status && (
            <span className="rounded bg-[#F2F2F7] px-1 py-0.5 text-[8.5px] font-bold uppercase tracking-wide text-[#6B6B73]">{node.status}</span>
          )}
          {isAnchor && <span className="rounded bg-[#0058CC] px-1 py-0.5 text-[8.5px] font-bold uppercase text-white">Aktif</span>}
        </div>
        <p className="truncate text-[10px] text-[#6B6B73]">
          {node.number ? node.title : ""}{node.meta ? `${node.number ? " · " : ""}${node.meta}` : ""}
          {node.date ? ` · ${fmtDate(node.date)}` : ""}
        </p>
      </div>
      {node.amount != null && node.amount > 0 && (
        <span className="shrink-0 text-[10.5px] font-semibold tabular-nums text-[#3C3C43]">{formatCurrency(node.amount)}</span>
      )}
      {printUrl && (
        <button
          data-testid={`doc-node-print-${node.id || "x"}`}
          className="icon-button shrink-0"
          title="Buka dokumen / cetak"
          onClick={(e) => { e.stopPropagation(); window.open(printUrl, "_blank", "noopener,noreferrer"); }}
        >
          <Printer size={12} />
        </button>
      )}
      {canNavigate && link.view && (
        <ExternalLink size={12} className="shrink-0 text-[#9A9BA3] group-hover:text-[#0058CC]" />
      )}
    </div>
  );
}

export default function ProcessTimeline({ docType, docId, onNavigate }) {
  const [state, setState] = useState({ loading: true, error: "", data: null });

  const load = () => {
    if (!docType || !docId) return;
    let active = true;
    setState({ loading: true, error: "", data: null });
    axios.get(`${API}/documents/relations/${docType}/${docId}`)
      .then((r) => { if (active) setState({ loading: false, error: "", data: r.data }); })
      .catch((e) => { if (active) setState({ loading: false, error: e.response?.data?.detail || "Gagal memuat relasi dokumen.", data: null }); });
    return () => { active = false; };
  };

  useEffect(load, [docType, docId]); // eslint-disable-line

  const { loading, error, data } = state;

  return (
    <div data-testid="process-timeline" className="rounded-md border border-[#EFF0F2] overflow-hidden">
      <div className="flex items-center justify-between gap-1.5 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
        <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          <GitBranch size={12} /> Alur Dokumen Terkait
        </span>
        <button data-testid="process-timeline-refresh" className="icon-button" title="Muat ulang" onClick={load}>
          <RefreshCw size={11} />
        </button>
      </div>

      {loading && (
        <div data-testid="process-timeline-loading" className="space-y-1.5 p-2.5">
          {[0, 1, 2].map((i) => <div key={i} className="h-8 animate-pulse rounded bg-[#F2F2F7]" />)}
        </div>
      )}

      {!loading && error && (
        <div data-testid="process-timeline-error" className="p-3 text-center">
          <p className="text-[11px] text-[#B23B14]">{error}</p>
          <button className="mt-1.5 text-[11px] font-semibold text-[#0058CC] underline" onClick={load}>Coba lagi</button>
        </div>
      )}

      {!loading && !error && data && (
        <ol className="p-2.5 space-y-0">
          {data.stages.map((stage, si) => {
            const last = si === data.stages.length - 1;
            const hasDocs = (stage.docs || []).length > 0;
            return (
              <li key={stage.key} data-testid={`process-stage-${stage.key}`} className="flex gap-2.5">
                <div className="flex flex-col items-center pt-0.5">
                  <span className={`flex h-3 w-3 flex-shrink-0 items-center justify-center rounded-full ${hasDocs ? "bg-[#0058CC]" : "bg-[#D1D5DB]"}`}>
                    <Circle size={5} className="text-white" fill="currentColor" />
                  </span>
                  {!last && <span className="my-0.5 w-px flex-1" style={{ background: "#E5E7EB", minHeight: 18 }} />}
                </div>
                <div className={`min-w-0 flex-1 ${last ? "" : "pb-2.5"}`}>
                  <div className="mb-1 flex items-center gap-1.5">
                    <p className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">{stage.label}</p>
                    {hasDocs && <span className="rounded-full bg-[#EFF4FF] px-1.5 text-[9px] font-bold text-[#0058CC]">{stage.docs.length}</span>}
                  </div>
                  {hasDocs ? (
                    <div className="space-y-1">
                      {stage.docs.map((node, ni) => (
                        <DocNode
                          key={`${node.type}-${node.id || ni}`}
                          node={node}
                          isAnchor={node.id === data.anchor?.id && node.type === data.anchor?.type}
                          onNavigate={onNavigate}
                        />
                      ))}
                    </div>
                  ) : (
                    <p data-testid={`process-stage-empty-${stage.key}`} className="flex items-center gap-1 text-[10.5px] italic text-[#9A9BA3]">
                      <ChevronRight size={11} /> {stage.empty_hint || "Belum ada dokumen."}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
