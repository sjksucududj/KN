/**
 * ManagerHome (EPIC 1 · PS-18) — **Dasbor Manajer**: halaman depan khusus manajer.
 *
 * Sebelum ini manajer mendarat di layar "Laporan" generik dan harus berkeliling
 * beberapa menu untuk tahu apa yang perlu ditindak. Dasbor ini menjawab tiga
 * pertanyaan yang sama setiap pagi, dari data NYATA:
 *   1. Apa yang menunggu tanda tangan saya?  → antrean persetujuan per jenis (bisa diklik)
 *   2. Tim saya di mana posisinya?           → target vs capaian + papan peringkat
 *   3. Apa yang sudah TERLAMBAT hari ini?    → piutang, round R&D, gudang, produksi
 * Ditambah cuplikan kinerja desainer (divisi MD dipimpin manajer).
 */
import { useCallback, useEffect, useState } from "react";
import {
  Award, BellRing, CalendarClock, ChevronRight, Clock, Palette, RefreshCw,
  Target, TrendingUp, TriangleAlert, Users,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import { gradeMeta, num } from "../designer/designerMeta";

const pct = (v) => (v === null || v === undefined ? "—" : `${v}%`);

export default function ManagerHome({ selectedEntity = "all", onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = selectedEntity && selectedEntity !== "all"
        ? { entity_id: selectedEntity } : {};
      const res = await axios.get(`${API}/home/manager`, { params });
      setData(res.data || null);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Dasbor Manajer.");
    } finally { setLoading(false); }
  }, [selectedEntity]);
  useEffect(() => { load(); }, [load]);

  const go = (view) => { if (view && onNavigate) onNavigate(view); };

  const totals = data?.totals || {};
  const target = data?.target || {};
  const approvals = data?.approvals || {};
  const late = data?.late_today || {};
  const team = data?.team || [];
  const designers = data?.designers || {};
  const ach = Number(target.achievement_pct || 0);
  const prog = Number(target.month_progress_pct || 0);
  const onTrack = ach >= prog;

  return (
    <div className="grid gap-3" data-testid="manager-home">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
        testId="manager-home-error" />

      {/* ── Ringkasan + target tim ──────────────────────────────────────── */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Target size={16} className="text-[#0058CC]" />
            <h2 data-testid="manager-home-title">Dasbor Manajer</h2>
            <span className="text-[11px] text-[#9A9BA3]">periode {data?.period || "—"}</span>
          </div>
          <button className="secondary-button" onClick={load} data-testid="manager-home-refresh">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
          </button>
        </div>
        <div className="section-body space-y-3">
          {loading && !data ? (
            <p className="py-8 text-center text-[12px] text-[#6B6B73]"
              data-testid="manager-home-loading">Memuat dasbor manajer…</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-5"
                data-testid="manager-home-kpi">
                <Kpi label="Penjualan tim (bulan ini)" value={formatCurrency(totals.total_sales || 0)} />
                <Kpi label="Tertagih" value={formatCurrency(totals.total_collected || 0)}
                  tone="#1B7F4B" />
                <Kpi label="Piutang berjalan" value={formatCurrency(totals.ar_outstanding || 0)}
                  tone="#0058CC" />
                <Kpi label="Piutang lewat tempo" value={formatCurrency(totals.overdue_amount || 0)}
                  tone={(totals.overdue_amount || 0) > 0 ? "#C0392B" : "#1B7F4B"} />
                <Kpi label="Menunggu tanda tangan" value={String(approvals.total ?? 0)}
                  tone={(approvals.total ?? 0) > 0 ? "#B26A00" : "#1B7F4B"} />
              </div>

              {/* Target tim vs kemajuan bulan */}
              <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-3"
                data-testid="manager-home-target">
                <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11.5px]">
                  <span className="font-bold uppercase text-[#8E8E93]">Target penagihan tim</span>
                  <span className="tabular-nums">{formatCurrency(target.amount || 0)}</span>
                  <span className={`status-pill ${onTrack ? "pill-success" : "pill-warning"}`}
                    data-testid="manager-home-target-status">
                    {onTrack ? "Sesuai jalur" : "Di bawah kemajuan bulan"}
                  </span>
                  <span className="ml-auto text-[#6B6B73]">
                    Capaian <b className="tabular-nums">{pct(target.achievement_pct)}</b>
                    {" · "}bulan sudah berjalan{" "}
                    <b className="tabular-nums">{pct(target.month_progress_pct)}</b>
                    {" "}(hari {target.day}/{target.days_in_month})
                  </span>
                </div>
                <div className="h-2.5 w-full overflow-hidden rounded-full bg-[#EDEFF2]">
                  <div className="h-full rounded-full"
                    style={{ width: `${Math.min(Math.max(ach, 0), 100)}%`,
                      background: onTrack ? "#1B7F4B" : "#B26A00" }} />
                </div>
              </div>
            </>
          )}
        </div>
      </section>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* ── Antrean persetujuan ───────────────────────────────────────── */}
        <section className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2">
              <BellRing size={16} className="text-[#B26A00]" />
              <h2>Menunggu Persetujuan Saya</h2>
            </div>
            <button className="secondary-button" onClick={() => go("approval-inbox")}
              data-testid="manager-home-goto-approvals">
              Pusat Persetujuan <ChevronRight size={13} />
            </button>
          </div>
          <div className="section-body">
            {loading && !data ? (
              <p className="py-6 text-center text-[12px] text-[#6B6B73]"
                data-testid="manager-home-approvals-loading">Memuat antrean…</p>
            ) : (approvals.items || []).length === 0 ? (
              <p className="py-8 text-center text-[11.5px] text-[#1B7F4B]"
                data-testid="manager-home-approvals-empty">
                Tidak ada dokumen yang menunggu tanda tangan Anda. Meja Anda bersih.
              </p>
            ) : (
              <div className="divide-y divide-[#F4F5F7]" data-testid="manager-home-approvals">
                {(approvals.items || []).map((a) => (
                  <button key={a.key} type="button" onClick={() => go(a.view)}
                    data-testid={`manager-home-approval-${a.key}`}
                    className="flex w-full items-center gap-2 bg-white px-1 py-2 text-left text-[12px] hover:bg-[#FAFBFC]">
                    <Clock size={13} className="shrink-0 text-[#B26A00]" />
                    <span className="min-w-0 flex-1 truncate">{a.label}</span>
                    <span className="tabular-nums text-[14px] font-bold text-[#B26A00]">
                      {a.count}
                    </span>
                    <ChevronRight size={13} className="text-[#C7C9CF]" />
                  </button>
                ))}
              </div>
            )}
            {/* PALING LAMA MENUNGGU (permintaan pemilik 2026-08-15) — isi yang sama
                dengan pengingat harian di notifikasi, supaya yang dibaca di WhatsApp/
                lonceng dan yang dilihat di beranda tidak pernah berbeda. */}
            {(approvals.oldest || []).length > 0 && (
              <div className="mt-3 border-t border-[#F4F5F7] pt-2"
                data-testid="manager-home-approvals-oldest">
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-[#9A9BA3]">
                  Paling lama menunggu keputusan Anda
                </p>
                <div className="grid gap-1">
                  {(approvals.oldest || []).map((o) => (
                    <button key={`${o.key}-${o.id}`} type="button" onClick={() => go(o.view)}
                      data-testid={`manager-home-oldest-${o.id || o.number}`}
                      className="flex w-full items-center gap-2 rounded-lg border border-[#F4F5F7] bg-white px-2 py-1.5 text-left hover:border-[#E0C08A] transition">
                      <span className="shrink-0 text-[12px] font-semibold text-[#1C1C1E]">{o.number}</span>
                      <span className="min-w-0 flex-1 truncate text-[11.5px] text-[#6B6B73]">
                        {o.queue_label.replace(" menunggu ACC", "")} · {o.title}
                      </span>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums ${
                        o.days_waiting >= 7 ? "bg-[#FDE7E7] text-[#C0392B]" : "bg-[#FFF4E0] text-[#B26A00]"}`}>
                        {o.days_waiting} hari
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ── Keterlambatan hari ini ────────────────────────────────────── */}
        <section className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2">
              <TriangleAlert size={16} className="text-[#C0392B]" />
              <h2>Terlambat Hari Ini</h2>
            </div>
            <span className="text-[11px] text-[#9A9BA3]" data-testid="manager-home-late-total">
              {late.total_items ?? 0} hal perlu dikejar
            </span>
          </div>
          <div className="section-body">
            {loading && !data ? (
              <p className="py-6 text-center text-[12px] text-[#6B6B73]"
                data-testid="manager-home-late-loading">Memuat keterlambatan…</p>
            ) : (late.rows || []).length === 0 ? (
              <p className="py-8 text-center text-[11.5px] text-[#1B7F4B]"
                data-testid="manager-home-late-empty">
                Tidak ada keterlambatan hari ini — piutang, sample R&amp;D, gudang, dan
                produksi semuanya dalam tenggat.
              </p>
            ) : (
              <div className="divide-y divide-[#F4F5F7]" data-testid="manager-home-late">
                {(late.rows || []).map((r) => (
                  <button key={r.key} type="button" onClick={() => go(r.view)}
                    data-testid={`manager-home-late-${r.key}`}
                    className="flex w-full items-start gap-2 bg-white px-1 py-2 text-left hover:bg-[#FAFBFC]">
                    <TriangleAlert size={13} className="mt-0.5 shrink-0 text-[#C0392B]" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12px] font-semibold">{r.label}</span>
                      <span className="block text-[10.5px] text-[#9A9BA3]">{r.hint}</span>
                    </span>
                    <span className="shrink-0 text-right text-[12.5px] font-bold tabular-nums text-[#C0392B]">
                      {r.amount !== null && r.amount !== undefined
                        ? formatCurrency(r.amount) : r.count}
                    </span>
                    <ChevronRight size={13} className="mt-0.5 text-[#C7C9CF]" />
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* ── Papan peringkat tim ───────────────────────────────────────── */}
        <section className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2">
              <Users size={16} className="text-[#0058CC]" />
              <h2>Tim Sales — Target vs Capaian</h2>
            </div>
            <button className="secondary-button" onClick={() => go("customers-crm")}
              data-testid="manager-home-goto-crm">
              Sales Force <ChevronRight size={13} />
            </button>
          </div>
          <div className="section-body">
            {loading && !data ? (
              <p className="py-6 text-center text-[12px] text-[#6B6B73]"
                data-testid="manager-home-team-loading">Memuat tim…</p>
            ) : team.length === 0 ? (
              <p className="py-8 text-center text-[11.5px] text-[#6B6B73]"
                data-testid="manager-home-team-empty">
                Belum ada aktivitas penjualan pada periode ini.
              </p>
            ) : (
              <div className="divide-y divide-[#F4F5F7]" data-testid="manager-home-team">
                {team.map((t) => {
                  const a = Number(t.achievement_pct || 0);
                  return (
                    <div key={t.sales_id} data-testid={`manager-home-team-${t.sales_id}`}
                      className="py-2 text-[11.5px]">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="w-4 text-[10px] font-bold text-[#9A9BA3]">
                          #{t.rank}
                        </span>
                        <span className="min-w-0 flex-1 truncate font-semibold">
                          {t.sales_name}
                        </span>
                        <span className="tabular-nums text-[#6B6B73]">
                          {t.orders_count || 0} pesanan
                        </span>
                        <span className="tabular-nums font-bold text-[#0058CC]">
                          {formatCurrency(t.total_sales || 0)}
                        </span>
                        <span className={`status-pill ${a >= prog ? "pill-success" : "pill-warning"}`}>
                          {t.achievement_pct === null ? "tanpa target" : `${a}%`}
                        </span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#EDEFF2]">
                        <div className="h-full rounded-full"
                          style={{ width: `${Math.min(Math.max(a, 0), 100)}%`,
                            background: a >= prog ? "#1B7F4B" : "#B26A00" }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {/* ── Cuplikan kinerja desainer (PS-18) ─────────────────────────── */}
        <section className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2">
              <Palette size={16} className="text-[#6B219A]" />
              <h2>Kinerja Desainer ({designers.period_label || "30 hari"})</h2>
            </div>
            <button className="secondary-button" onClick={() => go("designer-kpi")}
              data-testid="manager-home-goto-designer">
              KPI Desainer <ChevronRight size={13} />
            </button>
          </div>
          <div className="section-body space-y-2">
            {loading && !data ? (
              <p className="py-6 text-center text-[12px] text-[#6B6B73]"
                data-testid="manager-home-designer-loading">Memuat kinerja desainer…</p>
            ) : (designers.top || []).length === 0 ? (
              <p className="py-8 text-center text-[11.5px] text-[#6B6B73]"
                data-testid="manager-home-designer-empty">
                Belum ada round sample yang disetor pada 30 hari terakhir.
              </p>
            ) : (
              <>
                <div className="grid grid-cols-3 gap-2" data-testid="manager-home-designer-kpi">
                  <Kpi label="Tepat waktu" value={pct(designers.summary?.on_time_pct)}
                    tone={(designers.summary?.on_time_pct ?? 0) >= 80 ? "#1B7F4B" : "#B26A00"} />
                  <Kpi label="Kerja diulang" value={pct(designers.summary?.rework_pct)}
                    tone={(designers.summary?.rework_pct ?? 0) <= 30 ? "#1B7F4B" : "#C0392B"} />
                  <Kpi label="Nunggak tenggat"
                    value={String(designers.summary?.overdue_now ?? 0)}
                    tone={(designers.summary?.overdue_now ?? 0) > 0 ? "#C0392B" : "#1B7F4B"} />
                </div>
                <div className="divide-y divide-[#F4F5F7]" data-testid="manager-home-designer">
                  {(designers.top || []).map((d) => {
                    const g = gradeMeta(d.grade_letter);
                    return (
                      <div key={d.designer} className="flex items-center gap-2 py-1.5 text-[11.5px]"
                        data-testid={`manager-home-designer-${d.designer}`}>
                        <span className="w-4 text-[10px] font-bold text-[#9A9BA3]">#{d.rank}</span>
                        <span className="min-w-0 flex-1 truncate font-semibold">{d.designer}</span>
                        <span className="tabular-nums text-[#6B6B73]">
                          {num(d.on_time_pct, "%")} tepat
                        </span>
                        {d.late_total > 0 && (
                          <span className="tabular-nums font-semibold text-[#C0392B]">
                            {d.late_total} telat
                          </span>
                        )}
                        <span className={`status-pill ${g.cls}`}>
                          {g.label} · {num(d.grade_score)}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {designers.summary?.best_designer && (
                  <p className="flex items-center gap-1.5 text-[11px] text-[#6B6B73]"
                    data-testid="manager-home-designer-best">
                    <Award size={12} className="text-[#B8860B]" />
                    Terbaik: <b>{designers.summary.best_designer}</b>
                    {" "}({designers.summary.best_grade})
                  </p>
                )}
              </>
            )}
          </div>
        </section>
      </div>

      <p className="flex items-center gap-1.5 px-1 text-[10.5px] text-[#9A9BA3]">
        <CalendarClock size={11} />
        Seluruh angka dihitung langsung dari transaksi & jejak kerja yang tercatat —
        tidak ada satu pun yang diisi manual. Klik baris mana pun untuk membuka layar
        kerjanya.
        <TrendingUp size={11} className="ml-auto" />
      </p>
    </div>
  );
}

function Kpi({ label, value, tone = "#1C1C1E" }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[13px] font-bold leading-tight tabular-nums" style={{ color: tone }}>
        {value}
      </p>
    </div>
  );
}
