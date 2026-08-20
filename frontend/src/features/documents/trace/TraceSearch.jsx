/**
 * TraceSearch — FASE G-4 · titik masuk penelusuran: cari surat lintas jenis.
 *
 * Pemilik tidak selalu ingat dokumen mana yang "induk". Karena itu pencarian di
 * sini LINTAS JENIS (SO, PO, Faktur, Kwitansi, Retur, Tagihan Supplier, …) dan
 * hasilnya bisa langsung dijadikan jangkar penelusuran.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { FileSearch, Loader2, Search } from "lucide-react";
import EntityBadge from "../../../components/EntityBadge";
import { formatCurrency } from "../../../utils/formatters";
import { errText, searchDocs, shortDate } from "./traceApi";

export default function TraceSearch({ entityId, onPick, onError }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [touched, setTouched] = useState(false);
  const timer = useRef(null);

  const run = useCallback(async (term) => {
    if ((term || "").trim().length < 2) { setRows([]); return; }
    setLoading(true);
    try {
      setRows(await searchDocs(term.trim(), entityId));
      if (onError) onError("");
    } catch (e) {
      if (onError) onError(errText(e, "Gagal mencari dokumen."));
      setRows([]);
    } finally { setLoading(false); }
  }, [entityId, onError]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => run(q), 350);
    return () => timer.current && clearTimeout(timer.current);
  }, [q, run]);

  return (
    <div className="section-card" data-testid="trace-search-card">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <FileSearch size={15} className="text-[#0058CC]" />
          <h3 className="text-[12.5px] font-bold">Cari dokumen</h3>
        </div>
        {loading && <Loader2 size={13} className="animate-spin text-[#0058CC]" />}
      </div>
      <div className="section-body space-y-2">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
          <input data-testid="trace-search-input" value={q}
            onChange={(e) => { setQ(e.target.value); setTouched(true); }}
            className="field !pl-8"
            placeholder="Nomor surat (SO-0001, PO-00003, SCT-, SMP-, SPEC-, FKT-, AR-, VB-…) / pelanggan / supplier" />
        </div>
        <p className="text-[10.5px] text-[#8E8E93]">
          Penelusuran bisa dimulai dari dokumen APA PUN — termasuk dari tengah rantai
          seperti Kwitansi atau Tagihan Supplier, maupun dari HULU seperti Kontrak
          Supplier, Permintaan Sample (SMP), dan Spesifikasi Produk (SPEC).
        </p>

        {touched && !loading && q.trim().length >= 2 && rows.length === 0 && (
          <div data-testid="trace-search-empty" className="rounded-lg border border-dashed border-[#E5E5EA] bg-[#FAFBFC] p-4 text-center">
            <p className="text-[12px] font-semibold text-[#3C3C43]">Tidak ada dokumen cocok.</p>
            <p className="text-[11px] text-[#6B6B73]">Coba potongan nomor surat, atau nama pelanggan/supplier.</p>
          </div>
        )}

        {rows.length > 0 && (
          <div className="divide-y divide-[#EFF0F2] overflow-hidden rounded-lg border border-[#EFF0F2]"
            data-testid="trace-search-results">
            {rows.map((n) => (
              <button key={n.key} type="button" data-testid={`trace-result-${n.doc_id}`}
                onClick={() => onPick(n)}
                className="flex w-full items-center justify-between gap-2 bg-white px-3 py-2 text-left transition-colors hover:bg-[#F5F8FF]">
                <span className="min-w-0">
                  <span className="flex items-center gap-1.5">
                    <span className="text-[12px] font-bold text-[#0058CC]">{n.number}</span>
                    <EntityBadge entityId={n.entity_id} />
                    <span className="rounded bg-[#F1F2F4] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[#4A4B52]">
                      {n.label}
                    </span>
                  </span>
                  <span className="block truncate text-[10.5px] text-[#6B6B73]">
                    {n.title || "—"} · {shortDate(n.date)}
                    {n.ref_count ? ` · ${n.ref_count} referensi` : " · belum ada referensi"}
                  </span>
                </span>
                {Number(n.amount) > 0 && (
                  <span className="shrink-0 text-[11.5px] font-semibold tabular-nums text-[#1C1C1E]">
                    {formatCurrency(n.amount)}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
