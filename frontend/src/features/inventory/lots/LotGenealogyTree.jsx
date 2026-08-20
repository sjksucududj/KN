/**
 * LotGenealogyTree (FASE C · D-10) — silsilah lot interaktif.
 *
 * Menjawab PS-10: pengguna harus bisa melihat jalur benang → grey → PFD/PFP →
 * finished → pengiriman. Graph dirender per KEDALAMAN (hulu negatif, lot ini 0,
 * hilir positif) sehingga terbaca seperti pohon tanpa pustaka tambahan.
 */
import { ArrowDown, CornerDownRight, FileText, GitBranch } from "lucide-react";
import { formatQty } from "../../../utils/formatters";
import { LotSourcePill, LotStatusPill } from "./LotParts";
import { shortDate } from "./lotApi";

const RELATION_LABEL = { ancestor: "Hulu (induk)", self: "Lot ini", descendant: "Hilir (turunan)" };

export default function LotGenealogyTree({ data, loading, onOpenLot, labelOf }) {
  if (loading) {
    return <p data-testid="lot-genealogy-loading" className="py-6 text-center text-[11px] text-[#6B6B73]">Memuat silsilah…</p>;
  }
  const nodes = data?.nodes || [];
  if (!nodes.length) {
    return <p data-testid="lot-genealogy-empty" className="py-6 text-center text-[11px] text-[#6B6B73]">Silsilah belum tersedia.</p>;
  }
  const depths = [...new Set(nodes.map((n) => n.depth))].sort((a, b) => a - b);

  return (
    <div data-testid="lot-genealogy" className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
        <GitBranch size={12} className="text-[#0058CC]" />
        <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
          {data.ancestor_count} lot hulu · {data.descendant_count} lot hilir · {(data.edges || []).length} relasi
        </span>
        {(data.chain || []).length > 0 && (
          <span data-testid="lot-genealogy-chain" className="ml-auto text-[10.5px] text-[#6B6B73]">
            Rantai tahap:{" "}
            <b>{(data.chain || []).map((c) => labelOf("stage", c.stage)).join(" → ")}</b>
          </span>
        )}
      </div>

      {depths.map((depth) => {
        const group = nodes.filter((n) => n.depth === depth);
        const rel = group[0]?.relation;
        return (
          <div key={depth} data-testid={`lot-genealogy-depth-${depth}`}>
            <p className="mb-1 flex items-center gap-1 text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
              {depth < 0 ? <CornerDownRight size={10} /> : depth > 0 ? <ArrowDown size={10} /> : null}
              {RELATION_LABEL[rel] || rel} {depth !== 0 && `· tingkat ${Math.abs(depth)}`}
            </p>
            <div className="grid gap-1.5 md:grid-cols-2">
              {group.map((n) => (
                <div key={n.id} data-testid={`lot-node-${n.id}`}
                  className={`rounded-md border px-2.5 py-2 ${n.relation === "self"
                    ? "border-[#0058CC] bg-[#F0F6FF]" : "border-[#EFF0F2] bg-white"}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-[11.5px] font-bold text-[#1C1C1E]">{n.lot_number}</p>
                      <p className="truncate text-[10px] text-[#8E8E93]">
                        {n.sku} · {labelOf("stage", n.stage)} · {n.roll_count} roll ·{" "}
                        {formatQty(n.qty_remaining)} {n.unit}
                      </p>
                    </div>
                    {n.relation !== "self" && (
                      <button data-testid={`lot-node-open-${n.id}`}
                        className="btn-secondary !px-1.5 !py-0.5 !text-[9.5px]"
                        onClick={() => onOpenLot?.(n.id)}>Buka</button>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    <LotSourcePill value={n.source} label={n.source_label || labelOf("lot_source", n.source)} />
                    <LotStatusPill value={n.lot_status} label={labelOf("lot_status", n.lot_status)} />
                    {n.dye_lot && (
                      <span className="status-pill pill-muted">dye {n.dye_lot}</span>
                    )}
                    {(n.process || {}).process_type && (
                      <span className="status-pill pill-info">
                        {labelOf("process_type", n.process.process_type)}
                        {n.process.partner_name ? ` · ${n.process.partner_name}` : ""}
                      </span>
                    )}
                    <span className="ml-auto text-[9.5px] text-[#8E8E93]">{shortDate(n.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      <div className="rounded-md border border-[#EFF0F2] bg-white">
        <div className="flex items-center gap-1.5 border-b border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-1.5">
          <FileText size={12} className="text-[#0058CC]" />
          <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
            Dokumen pembentuk lot (penerimaan · makloon · work order)
          </span>
        </div>
        <div className="divide-y divide-[#F5F5F7]" data-testid="lot-genealogy-documents">
          {(data.documents || []).length === 0 && (
            <p className="px-2.5 py-2 text-[10.5px] text-[#8E8E93]">Tidak ada dokumen tertaut.</p>
          )}
          {(data.documents || []).map((d, i) => (
            <div key={`${d.lot_number}-${i}`} className="flex flex-wrap items-center gap-2 px-2.5 py-1.5 text-[10.5px]">
              <span className="font-semibold">{d.lot_number}</span>
              <span className="text-[#6B6B73]">{d.source_label || d.source}</span>
              {d.ref_number && <span className="status-pill pill-muted">{d.ref_number}</span>}
              {(d.detail || {}).supplier_name && (
                <span className="text-[#6B6B73]">supplier: {d.detail.supplier_name}</span>
              )}
              {(d.detail || {}).makloon_name && (
                <span className="text-[#6B6B73]">mitra: {d.detail.makloon_name}</span>
              )}
              {!d.ref_number && !d.ref_id && (
                <span className="text-[#8E8E93]">tanpa dokumen (input manual/migrasi)</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
