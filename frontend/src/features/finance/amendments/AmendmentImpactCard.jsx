/**
 * AmendmentImpactCard — FASE G-1 · kartu "apa yang berubah, seberapa besar,
 * dan apa konsekuensinya".
 *
 * Dipakai di dua tempat dengan bentuk data yang sama: hasil `POST /amendments/preview`
 * (sebelum mengirim usulan) dan dokumen amandemen tersimpan (saat meninjau/memutus).
 * Sengaja satu komponen supaya angka yang dilihat pengusul PERSIS sama dengan angka
 * yang dilihat penyetuju — tidak ada dua versi kebenaran.
 */
import { ArrowDownRight, ArrowUpRight, Info, ShieldAlert, Zap } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import { methodMeta } from "./amendmentApi";

export default function AmendmentImpactCard({ data, testId = "amd-impact", compact = false }) {
  if (!data) return null;
  const before = Number(data.before?.grand_total ?? data.impact?.amount_before ?? 0);
  const after = Number(data.after?.grand_total ?? data.impact?.amount_after ?? 0);
  const delta = Number(data.impact?.delta ?? after - before);
  const pct = Number(data.impact?.delta_pct ?? 0);
  const down = delta < 0;
  const mm = methodMeta(data.method);
  const needsApproval = !!data.requires_approval;

  return (
    <div data-testid={testId} className="rounded-lg border border-[#E5EEFB] bg-[#F5F9FF] p-2.5 space-y-2">
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-md bg-white px-1.5 py-1.5 border border-[#E5EEFB]">
          <p className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Nilai sekarang</p>
          <p data-testid={`${testId}-before`} className="text-[12.5px] font-bold tabular-nums text-[#3C3C43]">
            {formatCurrency(before)}
          </p>
        </div>
        <div className="rounded-md bg-white px-1.5 py-1.5 border border-[#E5EEFB]">
          <p className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Setelah koreksi</p>
          <p data-testid={`${testId}-after`} className="text-[12.5px] font-bold tabular-nums text-[#0058CC]">
            {formatCurrency(after)}
          </p>
        </div>
        <div className="rounded-md bg-white px-1.5 py-1.5 border border-[#E5EEFB]">
          <p className="text-[9px] font-bold uppercase tracking-wide text-[#8E8E93]">Dampak</p>
          <p data-testid={`${testId}-delta`}
            className={`text-[12.5px] font-bold tabular-nums flex items-center justify-center gap-0.5 ${down ? "text-[#A8221A]" : "text-[#1B7A43]"}`}>
            {down ? <ArrowDownRight size={12} /> : <ArrowUpRight size={12} />}
            {formatCurrency(Math.abs(delta))}
          </p>
          <p className="text-[9.5px] tabular-nums text-[#8E8E93]">{pct.toFixed(2)}% dari nilai dokumen</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span data-testid={`${testId}-method`} className="rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide"
          style={{ background: mm.bg, color: mm.fg }}>
          {mm.label}
        </span>
        {needsApproval ? (
          <span data-testid={`${testId}-approval`}
            className="inline-flex items-center gap-1 rounded bg-[#FFF3CD] px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-[#8A6D00]">
            <ShieldAlert size={11} /> Butuh persetujuan {data.required_role || "manager"}
          </span>
        ) : (
          <span data-testid={`${testId}-autoapply`}
            className="inline-flex items-center gap-1 rounded bg-[#E5F6EC] px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-[#1B7A43]">
            <Zap size={11} /> Langsung diterapkan
          </span>
        )}
      </div>

      {!compact && <p className="text-[10.5px] leading-snug text-[#4A4A52]">{mm.help}</p>}

      {Array.isArray(data.explain) && data.explain.length > 0 && (
        <ul data-testid={`${testId}-explain`} className="space-y-0.5">
          {data.explain.map((line, i) => (
            <li key={i} className="flex items-start gap-1 text-[10.5px] leading-snug text-[#4A4A52]">
              <Info size={10} className="mt-0.5 shrink-0 text-[#0058CC]" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
