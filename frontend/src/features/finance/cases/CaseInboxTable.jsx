/**
 * FASE G-9 — CaseInboxTable: antrean kasus keuangan.
 *
 * Urutan datang dari backend (terlambat → prioritas tinggi → tertua) supaya layar
 * MENUNTUN, bukan sekadar menampilkan daftar acak.
 */
import { AlertTriangle, ArrowUpRight, Flame } from "lucide-react";
import { formatCurrency } from "../../../utils/formatters";
import { STATUS_CLASS, STATUS_LABEL, humanAge, slaText } from "./caseApi";

export default function CaseInboxTable({ cases, loading, activeId, onOpen }) {
  if (loading) {
    return (
      <div className="rounded-lg border border-[#E5E5EA] bg-white p-4"
        data-testid="case-table-loading">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="mb-2 h-9 animate-pulse rounded bg-[#F2F2F5]" />
        ))}
      </div>
    );
  }

  if (!cases.length) {
    return (
      <div className="rounded-lg border border-[#E5E5EA] bg-white px-4 py-10 text-center"
        data-testid="case-table-empty">
        <p className="text-[13px] font-semibold text-[#1C1C1E]">
          Tidak ada kasus pada saringan ini.
        </p>
        <p className="mt-1 text-[12px] text-[#6B6B73]">
          Kasus muncul sendiri saat sistem menemukan dana titipan yang menganggur atau
          pembayaran yang terlihat dobel — atau buat manual lewat tombol “Kasus baru”.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-[#E5E5EA] bg-white"
      data-testid="case-table">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-[#EFF0F2] bg-[#FAFBFC] text-left text-[10px] font-bold uppercase text-[#8E8E93]">
            <th className="px-3 py-2">Nomor</th>
            <th className="px-3 py-2">Jenis kasus</th>
            <th className="px-3 py-2 text-right">Nominal</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Batas waktu</th>
            <th className="px-3 py-2">Penanggung jawab</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id} data-testid={`case-row-${c.id}`}
              onClick={() => onOpen(c)}
              className={`cursor-pointer border-b border-[#F4F4F6] last:border-0 hover:bg-[#FAFBFF] ${
                activeId === c.id ? "bg-[#F2F7FF]" : ""}`}>
              <td className="px-3 py-2">
                <span className="font-semibold text-[#0058CC]">{c.number}</span>
                <p className="text-[10px] text-[#8E8E93]">{humanAge(c.age_hours)} lalu</p>
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-1.5">
                  {c.priority === "tinggi" && (
                    <Flame size={12} className="text-[#C0392B]" title="Prioritas tinggi" />
                  )}
                  <span className="font-semibold text-[#1C1C1E]">{c.case_type_label}</span>
                </div>
                <p className="max-w-[380px] truncate text-[11px] text-[#6B6B73]" title={c.title}>
                  {c.title}
                </p>
              </td>
              <td className="px-3 py-2 text-right font-semibold tabular-nums">{formatCurrency(c.amount)}</td>
              <td className="px-3 py-2">
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  STATUS_CLASS[c.status] || "bg-[#F2F2F5] text-[#6B6B73]"}`}
                  data-testid={`case-status-${c.id}`}>
                  {STATUS_LABEL[c.status] || c.status}
                </span>
                {c.escalation_level > 0 && (
                  <span className="ml-1 rounded-full bg-[#FDECEA] px-1.5 py-0.5 text-[10px] font-bold text-[#C0392B]">
                    ESKALASI {c.escalation_level}
                  </span>
                )}
              </td>
              <td className={`px-3 py-2 ${
                c.overdue ? "font-semibold text-[#C0392B]" : "text-[#6B6B73]"}`}>
                <span className="inline-flex items-center gap-1">
                  {c.overdue && <AlertTriangle size={11} />} {slaText(c)}
                </span>
              </td>
              <td className="px-3 py-2 text-[#6B6B73]">{c.assignee || "—"}</td>
              <td className="px-3 py-2 text-right">
                <ArrowUpRight size={13} className="text-[#8E8E93]" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
