/**
 * MyDesignerKpiCard (PS-18) — kartu **"KPI Saya (R&D)"** di layar Profil Saya.
 *
 * PRIVASI adalah inti kartu ini: yang tampil HANYA angka milik pengguna yang sedang
 * masuk. Nama & nilai rekan tidak pernah dikirim oleh server (`/rnd/reports/my-kpi`
 * menyaring di sisi server), jadi tidak mungkin bocor lewat layar ini. Pembanding
 * yang ditampilkan sengaja hanya **rata-rata tim** dan **posisi peringkat** — cukup
 * untuk tahu diri, tanpa membuka rapor orang lain.
 */
import { useCallback, useEffect, useState } from "react";
import { Award, CalendarClock, Palette, RefreshCw, TriangleAlert } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { gradeMeta, num, PERIOD_OPTIONS } from "../designer/designerMeta";
import { myDesignerKpi } from "../designer/designerApi";

const RESULT_META = {
  acc: { label: "ACC", cls: "pill-success" },
  revisi: { label: "Revisi", cls: "pill-warning" },
  tolak: { label: "Ditolak", cls: "pill-danger" },
  "": { label: "Menunggu", cls: "pill-muted" },
};

export function MyDesignerKpiCard() {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("30d");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await myDesignerKpi({ period }));
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat KPI R&D Anda.");
    } finally { setLoading(false); }
  }, [period]);
  useEffect(() => { load(); }, [load]);

  const me = data?.me || null;
  const rounds = data?.rounds || [];
  const overdue = data?.overdue || [];
  const team = data?.team || {};
  const g = gradeMeta(me?.grade_letter);
  const opts = data?.period_options?.length ? data.period_options : PERIOD_OPTIONS;

  // Belum pernah menyetor round R&D → kartu ringkas (bukan tabel kosong).
  if (!loading && !error && !me && rounds.length === 0) {
    return (
      <div className="section-card !p-4" data-testid="ess-designer-kpi-none">
        <div className="mb-1 flex items-center gap-2">
          <Palette size={15} className="text-[#6B219A]" />
          <h3 className="text-[12.5px] font-bold">KPI Saya (R&amp;D)</h3>
        </div>
        <p className="text-[11.5px] leading-relaxed text-[#6B6B73]">
          Belum ada round sample R&amp;D atas nama Anda. Kartu ini terisi sendiri begitu
          Anda menyetor hasil round beserta buktinya — tidak perlu mengisi apa pun.
        </p>
      </div>
    );
  }

  return (
    <div className="section-card" data-testid="ess-designer-kpi-card">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <Palette size={16} className="text-[#6B219A]" />
          <h2 className="text-[13px] font-bold">KPI Saya (R&amp;D) — hanya nilai Anda</h2>
        </div>
        <div className="flex items-center gap-2">
          <KNSelect data-testid="ess-designer-kpi-period" value={period}
            onValueChange={setPeriod} options={opts} className="field !h-7 !w-[150px] !text-[11px]" />
          <button className="secondary-button" onClick={load}
            data-testid="ess-designer-kpi-refresh">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
          </button>
        </div>
      </div>
      <div className="section-body space-y-2.5">
        {error && (
          <div className="notice-bar danger !mb-0 !py-1.5" data-testid="ess-designer-kpi-error">
            <span className="text-[11.5px]">{error}</span>
          </div>
        )}
        {loading && !data ? (
          <p className="py-6 text-center text-[12px] text-[#6B6B73]"
            data-testid="ess-designer-kpi-loading">Memuat KPI R&amp;D Anda…</p>
        ) : (
          <>
            {/* Nilai saya + posisi */}
            <div className="flex flex-wrap items-center gap-3 rounded-lg bg-[#F7F8FA] p-3">
              <div>
                <p className="text-[10px] font-semibold uppercase text-[#9A9BA3]">
                  Nilai saya · {data?.period_label}
                </p>
                <p className="text-[24px] font-bold leading-tight tabular-nums"
                  style={{ color: g.tone }} data-testid="ess-designer-kpi-score">
                  {num(me?.grade_score)}
                </p>
              </div>
              <span className={`status-pill ${g.cls}`} data-testid="ess-designer-kpi-grade">
                {g.label} · {me?.grade_meaning || "—"}
              </span>
              {data?.rank && (
                <span className="flex items-center gap-1 text-[11.5px] text-[#3C3C43]"
                  data-testid="ess-designer-kpi-rank">
                  <Award size={13} className="text-[#B8860B]" />
                  Peringkat <b>{data.rank}</b> dari {data.total_designers} desainer
                </span>
              )}
              <span className="ml-auto text-[11px] text-[#6B6B73]"
                data-testid="ess-designer-kpi-team">
                Rata-rata tim: <b>{num(team.avg_grade)}</b>{" · "}
                tepat waktu tim <b>{num(team.on_time_pct, "%")}</b>
              </span>
            </div>

            {/* Metrik saya */}
            <div className="grid grid-cols-2 gap-2 md:grid-cols-5"
              data-testid="ess-designer-kpi-metrics">
              <Mini label="Round saya" value={num(me?.rounds)} />
              <Mini label="Tepat waktu" value={num(me?.on_time_pct, "%")}
                tone={(me?.on_time_pct ?? 0) >= 80 ? "#1B7F4B" : "#B26A00"} />
              <Mini label="Diulang" value={num(me?.rework_pct, "%")}
                tone={(me?.rework_pct ?? 0) <= 30 ? "#1B7F4B" : "#C0392B"} />
              <Mini label="Rata skor" value={num(me?.avg_score)} />
              <Mini label="Terlambat" value={num(me?.late_total)}
                tone={(me?.late_total ?? 0) > 0 ? "#C0392B" : "#1B7F4B"} />
            </div>

            {/* Yang harus saya kejar hari ini */}
            {overdue.length > 0 && (
              <div className="rounded-lg border border-[#FFD9D6] bg-[#FFF7F6] p-2.5"
                data-testid="ess-designer-kpi-overdue">
                <p className="mb-1 flex items-center gap-1 text-[10.5px] font-bold text-[#A8221A]">
                  <TriangleAlert size={11} /> {overdue.length} round Anda lewat tenggat —
                  manager sudah diberi tahu otomatis
                </p>
                {overdue.map((r) => (
                  <p key={r.round_id} className="text-[11.5px] text-[#3C3C43]"
                    data-testid={`ess-designer-kpi-overdue-${r.round_id}`}>
                    <b className="text-[#0058CC]">{r.number}</b> rnd {r.round_no} ·{" "}
                    {r.supplier_name || "supplier"} · tenggat {r.due_date} ·{" "}
                    <b className="text-[#C0392B]">{r.days_late} hari</b>
                  </p>
                ))}
              </div>
            )}

            {/* Riwayat round saya */}
            <div>
              <p className="mb-1 flex items-center gap-1 text-[10.5px] font-bold uppercase text-[#8E8E93]">
                <CalendarClock size={11} /> Round saya terbaru
              </p>
              {rounds.length === 0 ? (
                <p className="py-4 text-center text-[11.5px] text-[#6B6B73]"
                  data-testid="ess-designer-kpi-rounds-empty">
                  Belum ada round pada periode ini — coba pilih periode yang lebih panjang.
                </p>
              ) : (
                <div className="max-h-[220px] divide-y divide-[#F4F5F7] overflow-y-auto"
                  data-testid="ess-designer-kpi-rounds">
                  {rounds.map((r) => {
                    const rm = RESULT_META[r.result || ""] || RESULT_META[""];
                    return (
                      <div key={r.round_id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1.5 text-[11.5px]"
                        data-testid={`ess-designer-round-${r.round_id}`}>
                        <span className="font-bold text-[#0058CC]">{r.number}</span>
                        <span className="text-[#9A9BA3]">rnd {r.round_no}</span>
                        <span className="min-w-0 flex-1 truncate">{r.title}</span>
                        <span className="truncate text-[#6B6B73]">{r.supplier_name}</span>
                        {r.on_time === true && (
                          <span className="status-pill pill-success">Tepat waktu</span>
                        )}
                        {r.on_time === false && (
                          <span className="status-pill pill-danger">Setor telat</span>
                        )}
                        {r.days_late > 0 && (
                          <span className="font-semibold tabular-nums text-[#C0392B]">
                            telat {r.days_late} hari
                          </span>
                        )}
                        <span className={`status-pill ${rm.cls}`}>{rm.label}</span>
                        <span className="w-9 text-right font-bold tabular-nums">
                          {num(r.score)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <p className="text-[10.5px] leading-relaxed text-[#9A9BA3]">
              Angka ini terbentuk sendiri dari round yang Anda setor (lampiran + catatan
              wajib) — tidak ada yang mengisinya manual. Anda hanya bisa melihat nilai
              sendiri; nilai rekan tidak dikirim ke halaman ini.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function Mini({ label, value, tone = "#1C1C1E" }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[13px] font-bold leading-tight tabular-nums" style={{ color: tone }}>
        {value}
      </p>
    </div>
  );
}

export default MyDesignerKpiCard;
