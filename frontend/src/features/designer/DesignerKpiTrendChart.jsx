/**
 * DesignerKpiTrendChart (PS-18 lanjutan) — grafik **Tren Nilai Desainer per Bulan**.
 *
 * Menjawab pertanyaan pemilik: "arah kinerja tiap desainer ke mana?" — bukan sekadar
 * angka bulan ini. Titik grafik dihitung server memakai rumus grade yang SAMA dengan
 * tabel KPI (disaring per bulan) atau rata-rata skor mutu. Komponen ini mandiri:
 * mengambil datanya sendiri dan punya kendali metrik + rentang bulan, sehingga tidak
 * terikat pada periode tabel di atasnya.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { TrendingUp } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { errMsg } from "../rnd/rndMeta";
import { designerKpiTrend } from "./designerApi";

// Palet garis — dibedakan tegas & aman untuk buta warna ringan.
const PALETTE = ["#0058CC", "#1B7F4B", "#B8860B", "#C0392B",
  "#7E57C2", "#0097A7", "#EF6C00", "#5D4037"];

const MONTH_OPTIONS = [
  { value: "3", label: "3 bulan terakhir" },
  { value: "6", label: "6 bulan terakhir" },
  { value: "12", label: "12 bulan terakhir" },
];

export default function DesignerKpiTrendChart({ params = {}, testId = "designer-kpi-trend" }) {
  const [metric, setMetric] = useState("avg_score");
  const [months, setMonths] = useState("6");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await designerKpiTrend({ ...params, metric, months: Number(months) });
      setData(res || null);
      setError("");
    } catch (e) {
      setError(errMsg(e, "Gagal memuat tren nilai desainer."));
    } finally {
      setLoading(false);
    }
  }, [params, metric, months]);

  useEffect(() => { load(); }, [load]);

  const series = data?.series || [];
  const labels = data?.month_labels || [];

  // Ubah ke bentuk baris-per-bulan yang dimengerti Recharts:
  // [{ month: "Mar 2026", "Rina Kartika": 79, ... }, ...]
  const rows = useMemo(() => {
    if (!data) return [];
    return (data.months || []).map((_, i) => {
      const row = { month: labels[i] };
      series.forEach((s) => { row[s.designer] = s.points?.[i]?.score ?? null; });
      return row;
    });
  }, [data, labels, series]);

  const hasData = series.some((s) => (s.points || []).some((p) => p.score !== null));

  return (
    <section className="section-card" data-testid={testId}>
      <div className="section-head">
        <div className="flex items-center gap-2">
          <TrendingUp size={16} className="text-[#0058CC]" />
          <h2>Tren nilai desainer per bulan</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-[#E1E4EA] overflow-hidden"
            data-testid={`${testId}-metric`}>
            {[
              { k: "avg_score", label: "Rata-rata skor" },
              { k: "grade", label: "Grade" },
            ].map((m) => (
              <button
                key={m.k}
                type="button"
                data-testid={`${testId}-metric-${m.k}`}
                onClick={() => setMetric(m.k)}
                className={`px-2.5 py-1 text-[11.5px] font-semibold transition-colors ${
                  metric === m.k ? "bg-[#0058CC] text-white" : "bg-white text-[#4A4B52] hover:bg-[#F2F5FA]"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <KNSelect data-testid={`${testId}-months`} value={months}
            onValueChange={setMonths} options={MONTH_OPTIONS} className="field !w-[170px]" />
        </div>
      </div>
      <div className="section-body">
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
          testId={`${testId}-error`} />
        <p className="mb-1 text-[11.5px] text-[#6B6B73]" data-testid={`${testId}-note`}>
          {metric === "grade"
            ? "Nilai komposit (0–100) bila desainer dinilai dari pekerjaan bulan itu — rumus sama dengan tabel."
            : "Rata-rata skor mutu round (0–100) yang disetor pada bulan itu."}
          {" "}Titik kosong = tidak ada round pada bulan tersebut.
        </p>

        {loading && !data ? (
          <p className="py-10 text-center text-[12px] text-[#6B6B73]"
            data-testid={`${testId}-loading`}>Memuat grafik tren…</p>
        ) : !hasData ? (
          <div className="py-10 text-center" data-testid={`${testId}-empty`}>
            <p className="text-[12px] font-semibold text-[#4A4B52]">Belum ada data tren</p>
            <p className="text-[11.5px] text-[#9A9BA3]">
              Round sample yang sudah dinilai akan muncul sebagai titik bulanan di sini.
            </p>
          </div>
        ) : (
          <div style={{ width: "100%", height: 340 }} data-testid={`${testId}-chart`}>
            <ResponsiveContainer>
              <LineChart data={rows} margin={{ top: 8, right: 16, left: -8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F3" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#6B6B73" }}
                  axisLine={{ stroke: "#E1E4EA" }} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#6B6B73" }}
                  axisLine={false} tickLine={false} width={38} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid #E1E4EA" }}
                  formatter={(v, name) => [v == null ? "—" : v, name]} />
                <Legend wrapperStyle={{ fontSize: 11.5, paddingTop: 6 }} iconType="plainline" />
                {series.map((s, idx) => (
                  <Line
                    key={s.designer}
                    type="monotone"
                    dataKey={s.designer}
                    name={s.designer}
                    stroke={PALETTE[idx % PALETTE.length]}
                    strokeWidth={2.2}
                    dot={{ r: 2.5 }}
                    activeDot={{ r: 5 }}
                    connectNulls
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {hasData && (
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1"
            data-testid={`${testId}-avg-legend`}>
            {series.map((s, idx) => (
              <span key={s.designer} className="inline-flex items-center gap-1 text-[11px] text-[#4A4B52]">
                <span className="inline-block h-2 w-2 rounded-full"
                  style={{ background: PALETTE[idx % PALETTE.length] }} />
                {s.designer}
                <b className="tabular-nums">· rata-rata {s.avg ?? "—"}</b>
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
