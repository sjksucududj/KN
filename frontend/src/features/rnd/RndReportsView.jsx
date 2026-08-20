/**
 * RndReportsView (FASE F · PS-18) — **Laporan R&D**: pertanyaan pemilik dijawab dari
 * data NYATA (bukan angka hias):
 *   1. Round mana yang TERLAMBAT sekarang? (papan SLA)
 *   2. Berapa produk yang masih BELUM boleh dijual, dan di tahap apa? (papan lifecycle)
 *
 * CATATAN IA (PS-18): tabel kinerja pelaksana yang dulu ada di sini DIPINDAH ke menu
 * **Desainer › KPI Desainer** (lebih kaya: tepat waktu, pengulangan, nilai komposit,
 * filter periode). Di layar ini tinggal ringkasan 3 teratas + pintu masuknya, supaya
 * tidak ada dua tempat yang mengaku sumber kebenaran kinerja desainer.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, BarChart3, Palette, RefreshCw, Settings2 } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import { openConfig } from "../settings/config/configDeepLink";
import { designerKpi } from "../designer/designerApi";
import { gradeMeta, num } from "../designer/designerMeta";
import { lifecycleBoard, listSamples, performerReport } from "./rndApi";
import { openRnd } from "./rndDeepLink";
import { errMsg, lifecycleMeta, SAMPLE_TYPE_LABEL } from "./rndMeta";

export default function RndReportsView({ currentUser, selectedEntity }) {
  const [perf, setPerf] = useState([]);
  const [stats, setStats] = useState({});
  const [board, setBoard] = useState({});
  const [samples, setSamples] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const [rep, kpi, brd, smp] = await Promise.all([
        performerReport(params),
        designerKpi({ ...params, period: "30d" }).catch(() => ({ items: [] })),
        lifecycleBoard(params).catch(() => ({})),
        listSamples({ ...params, limit: 300 }).catch(() => ({ items: [] })),
      ]);
      setStats(rep?.stats || {});
      setPerf((kpi?.items || []).slice(0, 3));
      setBoard(brd || {});
      setSamples(smp?.items || []);
      setError("");
    } catch (e) {
      setError(errMsg(e, "Gagal memuat laporan R&D."));
    } finally { setLoading(false); }
  }, [selectedEntity]);
  useEffect(() => { load(); }, [load]);

  /** Papan SLA — round yang masih berjalan; yang terlambat naik ke atas. */
  const slaRows = useMemo(() => {
    const out = [];
    samples.forEach((s) => {
      (s.rounds || []).forEach((r) => {
        if (r.status === "open" || r.status === "submitted") {
          out.push({
            key: r.id, number: s.number, title: s.title,
            type: s.sample_type, supplier: r.supplier_name,
            round_no: r.round_no, due: r.due_date || "—",
            state: r.status === "open" ? "menunggu hasil supplier" : "menunggu penilaian",
            overdue: Boolean(r.overdue) || isPast(r.due_date),
          });
        }
      });
    });
    out.sort((a, b) => (Number(b.overdue) - Number(a.overdue))
      || String(a.due).localeCompare(String(b.due)));
    return out;
  }, [samples]);

  const lifeCounts = board?.counts || {};
  const notOrderable = board?.not_orderable || [];

  return (
    <div data-testid="rnd-reports-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
        testId="rnd-reports-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <BarChart3 size={16} className="text-[#0058CC]" />
            <h2 data-testid="rnd-reports-title">Laporan R&D</h2>
          </div>
          <div className="flex items-center gap-2">
            <button className="secondary-button" onClick={load} data-testid="rnd-reports-refresh">
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
            </button>
            {canManage && (
              <button className="secondary-button" data-testid="rnd-reports-policy-button"
                onClick={() => openConfig({ group: "rnd", key: "rnd.round_sla_days" })}>
                <Settings2 size={13} /> Target SLA
              </button>
            )}
          </div>
        </div>
        <div className="section-body">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="rnd-reports-kpi">
            <Kpi label="Total permintaan" value={String(stats.total ?? 0)} />
            <Kpi label="Round berjalan" value={String(stats.open_rounds ?? 0)} tone="#0058CC" />
            <Kpi label="Round terlambat" value={String(stats.overdue_rounds ?? 0)} tone="#C0392B" />
            <Kpi label="Sudah diputus" value={String(stats.decided ?? 0)} tone="#1B7F4B" />
            <Kpi label="Total biaya sample" value={formatCurrency(stats.cost_total || 0)} />
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* Ringkasan kinerja desainer — sumber lengkapnya di menu Desainer */}
        <div className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2">
              <Palette size={16} className="text-[#6B219A]" />
              <h2>Desainer Teratas (30 hari)</h2>
            </div>
            <button className="secondary-button" data-testid="rnd-reports-open-designer"
              onClick={() => openRnd({ view: "designer-kpi" })}>
              Buka KPI Desainer <ArrowRight size={13} />
            </button>
          </div>
          <div className="section-body">
            <p className="mb-2 text-[11px] leading-relaxed text-[#6B6B73]"
              data-testid="rnd-reports-designer-note">
              Penilaian kinerja desainer kini punya menunya sendiri (<b>Desainer › KPI
              Desainer</b>) dengan ketepatan waktu, pengulangan kerja, nilai komposit,
              filter periode, dan papan eskalasi SLA. Di sini hanya 3 teratas.
            </p>
            {perf.length === 0 ? (
              <p className="py-8 text-center text-[11.5px] text-[#6B6B73]"
                data-testid="rnd-perf-empty">
                Belum ada round yang disetor dalam 30 hari terakhir. Angka terbentuk
                sendiri begitu desainer menyetor hasil round — tidak diisi manual.
              </p>
            ) : (
              <div className="divide-y divide-[#F4F5F7]">
                {perf.map((p) => {
                  const g = gradeMeta(p.grade_letter);
                  return (
                    <div key={p.designer} data-testid={`rnd-perf-row-${p.designer}`}
                      className="flex items-center gap-2 py-1.5 text-[11.5px]">
                      <span className="w-4 text-[10px] font-bold text-[#9A9BA3]">
                        #{p.rank}
                      </span>
                      <span className="min-w-0 flex-1 truncate font-semibold">
                        {p.designer}
                      </span>
                      <span className="tabular-nums text-[#6B6B73]">
                        {p.rounds} round
                      </span>
                      <span className="tabular-nums font-semibold text-[#1B7F4B]">
                        {num(p.on_time_pct, "%")} tepat
                      </span>
                      {p.late_total > 0 && (
                        <span className="tabular-nums font-semibold text-[#C0392B]">
                          {p.late_total} telat
                        </span>
                      )}
                      <span className={`status-pill ${g.cls}`}>
                        {g.label} · {num(p.grade_score)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Papan lifecycle produk */}
        <div className="section-card">
          <div className="section-head">
            <h2>Tahap Produk (boleh dijual atau belum)</h2>
          </div>
          <div className="section-body space-y-2">
            <p className="text-[11px] text-[#6B6B73]" data-testid="rnd-board-enforcement">
              Ketegasan sekarang:{" "}
              <b>{board.enforcement === "block" ? "tolak pesanan"
                : board.enforcement === "warn" ? "beri peringatan" : "abaikan"}</b>
              {" "}bila produk yang belum sah dipesan. Total produk: <b>{board.total ?? 0}</b>.
            </p>
            <div className="grid grid-cols-2 gap-1.5 md:grid-cols-3" data-testid="rnd-board-counts">
              {Object.keys(lifeCounts).length === 0 && (
                <p className="text-[11.5px] text-[#6B6B73]">Belum ada data produk.</p>
              )}
              {Object.entries(lifeCounts).map(([k, v]) => {
                const m = lifecycleMeta(k);
                return (
                  <div key={k} data-testid={`rnd-board-count-${k}`}
                    className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
                    <p className="text-[9.5px] font-bold uppercase" style={{ color: m.tone }}>
                      {m.label}
                    </p>
                    <p className="text-[14px] font-bold tabular-nums leading-tight">{v}</p>
                  </div>
                );
              })}
            </div>
            {notOrderable.length > 0 && (
              <div className="rounded-lg border border-[#FFE0B2] bg-[#FFFAF2] p-2"
                data-testid="rnd-board-not-orderable">
                <p className="mb-1 flex items-center gap-1 text-[10.5px] font-bold text-[#8C4A00]">
                  <AlertTriangle size={11} /> {notOrderable.length} produk BELUM boleh dijual
                </p>
                <div className="max-h-[180px] space-y-0.5 overflow-y-auto">
                  {notOrderable.map((p) => (
                    <p key={p.id} className="text-[11px] text-[#3C3C43]"
                      data-testid={`rnd-board-blocked-${p.id}`}>
                      <b>{p.sku}</b> {p.name}
                      <span className="text-[#8C4A00]">
                        {" · "}{lifecycleMeta(p.lifecycle).label}
                      </span>
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Papan SLA round */}
      <div className="section-card mt-3">
        <div className="section-head"><h2>Papan SLA Round (yang masih berjalan)</h2></div>
        <div className="section-body">
          <div className="grid grid-cols-[130px_1.3fr_1fr_70px_110px_1fr] px-1 pb-1 text-[9.5px] font-bold uppercase text-[#8E8E93]">
            <span>No. Permintaan</span><span>Judul</span><span>Supplier</span><span>Round</span>
            <span>Tenggat</span><span>Keadaan</span>
          </div>
          {slaRows.length === 0 ? (
            <p className="py-8 text-center text-[11.5px] text-[#6B6B73]" data-testid="rnd-sla-empty">
              Tidak ada round yang sedang berjalan. Semua permintaan sudah dinilai atau diputus.
            </p>
          ) : (
            <div className="divide-y divide-[#F4F5F7] max-h-[360px] overflow-y-auto">
              {slaRows.map((r) => (
                <div key={r.key} data-testid={`rnd-sla-row-${r.key}`}
                  className="grid grid-cols-[130px_1.3fr_1fr_70px_110px_1fr] items-center px-1 py-1.5 text-[11.5px]">
                  <span className="font-bold text-[#0058CC]">{r.number}</span>
                  <span className="truncate">
                    {r.title}
                    <span className="text-[#9A9BA3]">
                      {" · "}{SAMPLE_TYPE_LABEL[r.type] || r.type}
                    </span>
                  </span>
                  <span className="truncate">{r.supplier}</span>
                  <span className="tabular-nums">rnd {r.round_no}</span>
                  <span className={`tabular-nums ${r.overdue ? "font-bold text-[#C0392B]" : ""}`}>
                    {r.due}
                  </span>
                  <span className={r.overdue ? "font-semibold text-[#C0392B]" : "text-[#6B6B73]"}>
                    {r.state}{r.overdue ? " · TERLAMBAT" : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Tenggat sudah lewat hari ini? (dipakai sebagai penanda terlambat di papan SLA). */
function isPast(due) {
  if (!due) return false;
  try { return new Date(`${String(due).slice(0, 10)}T23:59:59`) < new Date(); }
  catch { return false; }
}

function Kpi({ label, value, tone = "#1C1C1E" }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[13px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
    </div>
  );
}
