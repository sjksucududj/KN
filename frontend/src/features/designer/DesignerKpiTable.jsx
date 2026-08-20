/**
 * DesignerKpiTable (PS-18) — tabel kinerja per desainer.
 *
 * Semua kolom lahir dari jejak round yang sudah wajib ber-bukti (lampiran + catatan),
 * jadi TIDAK ada angka yang diisi tangan. Bisa diurutkan supaya pemilik bisa bertanya
 * dari sudut berbeda ("siapa paling sering terlambat?", "siapa paling sering diulang?").
 */
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, FileText, Users } from "lucide-react";
import { badPctTone, goodPctTone, gradeMeta, num } from "./designerMeta";

const COLS = [
  { key: "designer", label: "Desainer", align: "left", w: "minmax(150px,1.5fr)" },
  { key: "division_name", label: "Divisi", align: "left", w: "minmax(92px,0.9fr)",
    hint: "Divisi R&D (PS-17)", noSort: true },
  { key: "rounds", label: "Round", w: "62px", hint: "Jumlah round yang ditangani" },
  { key: "acc", label: "ACC", w: "58px", hint: "Round yang langsung diterima" },
  { key: "revisi", label: "Revisi", w: "62px", hint: "Diminta perbaikan" },
  { key: "tolak", label: "Tolak", w: "58px", hint: "Hasil ditolak" },
  { key: "late_total", label: "Terlambat", w: "84px",
    hint: "Disetor melewati tenggat + yang masih menggantung" },
  { key: "on_time_pct", label: "Tepat waktu", w: "92px", hint: "Patuh tenggat SLA" },
  { key: "rework_pct", label: "Diulang", w: "78px", hint: "Revisi + tolak dari yang dinilai" },
  { key: "avg_score", label: "Rata skor", w: "80px", hint: "Skor penilaian manajer" },
  { key: "avg_days", label: "Rata hari", w: "80px", hint: "Lama round dari kirim ke setor" },
  { key: "grade_score", label: "Nilai", w: "96px", hint: "Nilai komposit + huruf" },
  { key: "report", label: "Rapor", w: "110px", hint: "Unduh rapor 1 halaman (PDF)", noSort: true },
];

const GRID = COLS.map((c) => c.w).join(" ");

export default function DesignerKpiTable({ items, onSelect, selected, loading = false,
  onDownloadReport, downloadingReport = "" }) {
  const [sortKey, setSortKey] = useState("grade_score");
  const [asc, setAsc] = useState(false);

  const rows = useMemo(() => {
    const out = [...(items || [])];
    out.sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (typeof va === "string" || typeof vb === "string") {
        return String(va || "").localeCompare(String(vb || "")) * (asc ? 1 : -1);
      }
      const na = va === null || va === undefined ? -1 : Number(va);
      const nb = vb === null || vb === undefined ? -1 : Number(vb);
      return (na - nb) * (asc ? 1 : -1);
    });
    return out;
  }, [items, sortKey, asc]);

  function toggle(key) {
    if (key === sortKey) setAsc(!asc);
    else { setSortKey(key); setAsc(key === "designer"); }
  }

  if (loading) {
    return (
      <div className="space-y-1.5 py-2" data-testid="designer-kpi-table-skeleton">
        <p className="text-[12px] text-[#6B6B73]">Memuat kinerja desainer…</p>
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-7 animate-pulse rounded-md bg-[#F2F3F5]" />
        ))}
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="py-10 text-center" data-testid="designer-kpi-empty">
        <Users size={26} className="mx-auto mb-2 text-[#C7C9CF]" />
        <p className="text-[13px] font-semibold text-[#3A3B42]">
          Belum ada kinerja desainer pada periode ini
        </p>
        <p className="mt-0.5 text-[12px] text-[#6B6B73]">
          Angka di sini terbentuk sendiri begitu desainer menyetor hasil round sample
          (lampiran + catatan wajib) — tidak pernah diisi manual. Coba pilih periode
          yang lebih panjang, atau mulai dari menu R&amp;D &rsaquo; Permintaan Sample.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[1200px]">
        <div className="grid px-1 pb-1 text-[9.5px] font-bold uppercase text-[#8E8E93]"
          style={{ gridTemplateColumns: GRID }}>
          {COLS.map((c) => (
            c.noSort ? (
              <span key={c.key} title={c.hint || c.label}
                className="flex items-center justify-start truncate text-[9.5px] font-bold uppercase text-[#8E8E93]">
                {c.label}
              </span>
            ) : (
              <button key={c.key} type="button" title={c.hint || c.label}
                data-testid={`designer-kpi-sort-${c.key}`}
                onClick={() => toggle(c.key)}
                className={`flex items-center gap-0.5 bg-transparent text-[9.5px] font-bold uppercase
                  ${c.align === "left" ? "justify-start" : "justify-start"}
                  ${sortKey === c.key ? "text-[#0058CC]" : "text-[#8E8E93]"}`}>
                <span className="truncate">{c.label}</span>
                {sortKey === c.key && (asc ? <ArrowUp size={9} /> : <ArrowDown size={9} />)}
              </button>
            )
          ))}
        </div>
        <div className="divide-y divide-[#F4F5F7]">
          {rows.map((r) => {
            const g = gradeMeta(r.grade_letter);
            const active = selected === r.designer;
            const busyReport = downloadingReport === r.designer;
            return (
              <div key={r.designer} role="button" tabIndex={0}
                data-testid={`designer-kpi-row-${r.designer}`}
                onClick={() => onSelect && onSelect(active ? "" : r.designer)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault(); onSelect && onSelect(active ? "" : r.designer);
                  }
                }}
                className={`grid w-full cursor-pointer items-center px-1 py-1.5 text-left text-[11.5px]
                  ${active ? "bg-[#F2F7FF]" : "bg-white hover:bg-[#FAFBFC]"}`}
                style={{ gridTemplateColumns: GRID }}>
                <span className="truncate font-semibold text-[#1C1C1E]">
                  <span className="mr-1 text-[10px] text-[#9A9BA3]">#{r.rank}</span>
                  {r.designer}
                </span>
                <span className="truncate" data-testid={`designer-kpi-division-${r.designer}`}>
                  {r.division_name ? (
                    <span className="inline-block rounded-full bg-[#EDE7F6] px-2 py-0.5 text-[10px] font-semibold text-[#5E35B1]">
                      {r.division_name}
                    </span>
                  ) : (
                    <span className="text-[10.5px] text-[#B8B9C0]">—</span>
                  )}
                </span>
                <span className="tabular-nums">{r.rounds}</span>
                <span className="tabular-nums font-bold text-[#1B7F4B]">{r.acc}</span>
                <span className="tabular-nums text-[#B26A00]">{r.revisi}</span>
                <span className="tabular-nums text-[#C0392B]">{r.tolak}</span>
                <span className="tabular-nums font-semibold"
                  style={{ color: r.late_total > 0 ? "#C0392B" : "#1B7F4B" }}>
                  {r.late_total}
                  {r.overdue_now > 0 && (
                    <span className="ml-1 text-[9.5px] font-bold text-[#C0392B]">
                      ({r.overdue_now} nunggak)
                    </span>
                  )}
                </span>
                <span className="tabular-nums font-semibold"
                  style={{ color: goodPctTone(r.on_time_pct) }}>
                  {num(r.on_time_pct, "%")}
                </span>
                <span className="tabular-nums font-semibold"
                  style={{ color: badPctTone(r.rework_pct) }}>
                  {num(r.rework_pct, "%")}
                </span>
                <span className="tabular-nums">{num(r.avg_score)}</span>
                <span className="tabular-nums">{num(r.avg_days)}</span>
                <span className="flex items-center gap-1"
                  title={r.grade_score === null ? "Data belum cukup untuk dinilai"
                    : `Nilai dasar ${r.grade_base} − penalti ${r.grade_penalty} = `
                      + `${r.grade_score} (${r.grade_meaning})`}>
                  <span className="tabular-nums font-bold" style={{ color: g.tone }}>
                    {num(r.grade_score)}
                  </span>
                  <span className={`status-pill ${g.cls}`}
                    data-testid={`designer-kpi-grade-${r.designer}`}>{g.label}</span>
                </span>
                <span className="flex items-center justify-start">
                  <button type="button"
                    data-testid={`designer-kpi-report-${r.designer}`}
                    title={`Unduh rapor PDF ${r.designer}`}
                    disabled={busyReport}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDownloadReport && onDownloadReport(r.designer);
                    }}
                    className={`inline-flex items-center gap-1 rounded-md border border-[#D5DBE6]
                      px-1.5 py-0.5 text-[10.5px] font-semibold text-[#0058CC]
                      ${busyReport ? "opacity-60" : "hover:bg-[#F2F7FF]"}`}>
                    <FileText size={11} className={busyReport ? "animate-pulse" : ""} />
                    {busyReport ? "Menyiapkan…" : "Rapor PDF"}
                  </button>
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
