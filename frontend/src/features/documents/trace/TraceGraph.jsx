/**
 * TraceGraph — FASE G-4 · rantai dokumen sebagai **kolom per tahap**.
 *
 * Kenapa bukan graf bebas: pemilik membaca rantai sebagai alur proses
 * (Special Order → PR → PO → Penerimaan → Tagihan …). Node dikelompokkan per
 * jenis dokumen dengan urutan `order` dari registry backend, sehingga urutan
 * tahap tidak pernah ditebak di browser.
 *
 * Klik satu dokumen = jadikan jangkar baru (menelusuri dari sisi itu).
 */
import { ArrowRight, ExternalLink, Link2 } from "lucide-react";
import EntityBadge from "../../../components/EntityBadge";
import { formatCurrency } from "../../../utils/formatters";
import { relTone, shortDate } from "./traceApi";

function NodeCard({ node, isAnchor, onAnchor, onOpen }) {
  return (
    <div data-testid={`trace-node-${node.doc_id}`}
      className={`rounded-lg border p-2 transition-colors ${isAnchor
        ? "border-[#0058CC] bg-[#EFF4FF] shadow-[0_0_0_1px_#0058CC]"
        : "border-[#EFF0F2] bg-white hover:border-[#B9CDF5]"}`}>
      <div className="flex items-start justify-between gap-1.5">
        <button type="button" data-testid={`trace-anchor-${node.doc_id}`}
          onClick={() => onAnchor(node)}
          className="min-w-0 text-left">
          <span className="flex items-center gap-1.5">
            <span className="truncate text-[11.5px] font-bold text-[#0058CC]">{node.number}</span>
            <EntityBadge entityId={node.entity_id} />
          </span>
          <span className="block truncate text-[10px] text-[#6B6B73]">{node.title || "—"}</span>
        </button>
        {node.link?.view && (
          <button type="button" title="Buka dokumennya" data-testid={`trace-open-${node.doc_id}`}
            onClick={() => onOpen(node)}
            className="shrink-0 rounded-md border border-[#EDEEF1] p-1 text-[#4A4B52] hover:bg-[#F2F3F5]">
            <ExternalLink size={12} />
          </button>
        )}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[9.5px] text-[#8E8E93]">
        <span>{shortDate(node.date)}</span>
        {node.status && (
          <span className="rounded bg-[#F1F2F4] px-1.5 py-0.5 font-semibold uppercase tracking-wide text-[#4A4B52]">
            {node.status}
          </span>
        )}
        {isAnchor && (
          <span className="rounded bg-[#0058CC] px-1.5 py-0.5 font-bold uppercase tracking-wide text-white">
            titik mulai
          </span>
        )}
      </div>
      {Number(node.amount) > 0 && (
        <p className="mt-0.5 text-[10.5px] font-semibold tabular-nums text-[#1C1C1E]">
          {formatCurrency(node.amount)}
        </p>
      )}
    </div>
  );
}

export default function TraceGraph({ trace, loading = false, onAnchor, onOpen }) {
  const groups = trace?.groups || [];
  const nodes = trace?.nodes || [];
  const byKey = {};
  nodes.forEach((n) => { byKey[n.key] = n; });

  if (loading) {
    return (
      <section className="section-card" data-testid="trace-graph-loading">
        <div className="section-body space-y-2 py-6">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-[#F2F3F5]" />
          ))}
          <p className="text-center text-[11.5px] text-[#6B6B73]">Menyusun rantai dokumen…</p>
        </div>
      </section>
    );
  }

  if (!groups.length) return null;

  return (
    <div className="grid gap-3">
      <section className="section-card" data-testid="trace-graph">
        <div className="section-head">
          <h3 className="text-[12.5px] font-bold">Rantai dokumen</h3>
          <span className="text-[10.5px] text-[#8E8E93]">
            {nodes.length} dokumen · {trace.edge_count || 0} relasi · kedalaman {trace.depth}
          </span>
        </div>
        <div className="section-body">
          <div className="flex gap-3 overflow-x-auto pb-1">
            {groups.map((g, gi) => (
              <div key={g.doc_type} className="flex items-start gap-2">
                <div className="min-w-[200px] max-w-[240px] shrink-0">
                  <p className="mb-1.5 flex items-center gap-1 text-[9.5px] font-bold uppercase tracking-wide text-[#6B6B73]">
                    {g.label}
                    <span className="rounded-full bg-[#F1F2F4] px-1.5 text-[9px] text-[#4A4B52]">{g.docs.length}</span>
                  </p>
                  <div className="space-y-1.5">
                    {g.docs.map((n) => (
                      <NodeCard key={n.key} node={n} isAnchor={n.is_anchor}
                        onAnchor={onAnchor} onOpen={onOpen} />
                    ))}
                  </div>
                </div>
                {gi < groups.length - 1 && (
                  <ArrowRight size={14} className="mt-8 shrink-0 text-[#C4C5CC]" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section-card" data-testid="trace-edges">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Link2 size={14} className="text-[#0058CC]" />
            <h3 className="text-[12.5px] font-bold">Daftar relasi (bisa dibaca dua arah)</h3>
          </div>
          <span className="text-[10.5px] text-[#8E8E93]">{(trace.edges || []).length} tautan</span>
        </div>
        <div className="section-body">
          {(trace.edges || []).length === 0 ? (
            <p data-testid="trace-edges-empty" className="py-6 text-center text-[11.5px] text-[#6B6B73]">
              Dokumen ini belum menaut surat lain. Admin dapat menjalankan
              <b> Susun Ulang Relasi</b> untuk membentuk relasi data lama.
            </p>
          ) : (
            <ul className="divide-y divide-[#EFF0F2]">
              {(trace.edges || []).map((e, i) => {
                const a = byKey[e.from]; const b = byKey[e.to];
                const tone = relTone(e.rel);
                return (
                  <li key={`${e.from}-${e.to}-${i}`} data-testid={`trace-edge-${i}`}
                    className="flex flex-wrap items-center gap-2 py-1.5 text-[11px]">
                    <span className="font-semibold text-[#1C1C1E]">{a?.number || e.from}</span>
                    <span className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide"
                      style={{ background: tone.bg, color: tone.fg }}>{e.rel_label || e.rel}</span>
                    <ArrowRight size={12} className="text-[#C4C5CC]" />
                    <span className="font-semibold text-[#1C1C1E]">{b?.number || e.to}</span>
                    {e.note && <span className="text-[10px] text-[#8E8E93]">· {e.note}</span>}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
