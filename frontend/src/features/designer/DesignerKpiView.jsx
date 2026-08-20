/**
 * DesignerKpiView (PS-18) — layar utama menu **Desainer › KPI Desainer**.
 *
 * Menjawab tiga pertanyaan pemilik tanpa satu pun angka diisi tangan:
 *   1. Desainer mana yang paling bisa diandalkan? (nilai komposit + peringkat)
 *   2. Siapa yang sering terlambat atau sering diulang kerjanya? (tepat waktu / diulang)
 *   3. Pekerjaan mana yang SEKARANG menggantung lewat tenggat, dan sudah dinaikkan
 *      ke siapa? (papan eskalasi aktif — bukan sekadar tanda merah)
 *
 * Menu ini SENGAJA dipisah dari menu R&D (keputusan pemilik): R&D mengurus
 * spesifikasi & permintaan sample, Desainer mengurus orang & karyanya.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Award, BarChart3, Download, FileSpreadsheet, FileText, Info, RefreshCw, Settings2, Users } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";
import { openConfig } from "../settings/config/configDeepLink";
import { errMsg } from "../rnd/rndMeta";
import DesignerKpiTable from "./DesignerKpiTable";
import DesignerKpiTrendChart from "./DesignerKpiTrendChart";
import DesignerSlaPanel from "./DesignerSlaPanel";
import { designerKpi, downloadDesignerKpi, downloadDesignerReport, runSlaEscalation, saveBlob, slaBoard } from "./designerApi";
import { gradeFormula, gradeMeta, num, PERIOD_OPTIONS } from "./designerMeta";

export default function DesignerKpiView({ currentUser, selectedEntity }) {
  const [period, setPeriod] = useState("30d");
  const [report, setReport] = useState(null);
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [runInfo, setRunInfo] = useState(null);
  const [focusDesigner, setFocusDesigner] = useState("");
  const [division, setDivision] = useState(""); // "" = semua divisi (PS-17)
  const [showHow, setShowHow] = useState(false);
  const [exporting, setExporting] = useState("");
  const [exportMsg, setExportMsg] = useState(null);
  const [reportBusy, setReportBusy] = useState("");
  const [reportModal, setReportModal] = useState(null); // {designer, note} | null

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  const params = useMemo(() => {
    const p = {};
    if (selectedEntity && selectedEntity !== "all") p.entity_id = selectedEntity;
    return p;
  }, [selectedEntity]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rep, brd] = await Promise.all([
        designerKpi({ ...params, period, division }),
        slaBoard(params).catch(() => null),
      ]);
      setReport(rep || null);
      setBoard(brd || null);
      setError("");
    } catch (e) {
      setError(errMsg(e, "Gagal memuat KPI desainer."));
    } finally {
      setLoading(false);
    }
  }, [params, period, division]);

  useEffect(() => { load(); }, [load]);

  /** Unduh laporan untuk rapat bulanan (CSV / Excel / PDF) — angka sama dengan layar. */
  async function download(format) {
    setExporting(format);
    setExportMsg(null);
    try {
      const res = await downloadDesignerKpi({ ...params, period, format });
      const disp = String(res.headers?.["content-disposition"] || "");
      const match = disp.match(/filename=([^;]+)/i);
      const name = (match ? match[1] : `kpi-desainer-${period}.${format}`).trim();
      saveBlob(res.data, name);
      setExportMsg({ ok: true, message: `Berkas ${name} berhasil diunduh.` });
    } catch (e) {
      setExportMsg({ ok: false, message: errMsg(e, "Gagal mengunduh laporan KPI.") });
    } finally { setExporting(""); }
  }

  /** Unduh RAPOR 1 halaman (PDF) untuk SATU desainer — dengan catatan evaluasi opsional. */
  async function downloadReport(designer, note = "") {
    setReportBusy(designer);
    setExportMsg(null);
    try {
      const res = await downloadDesignerReport({ ...params, period, designer, note });
      const disp = String(res.headers?.["content-disposition"] || "");
      const match = disp.match(/filename=([^;]+)/i);
      const name = (match ? match[1] : `rapor-${designer}.pdf`).trim();
      saveBlob(res.data, name);
      setExportMsg({ ok: true, message: `Rapor ${designer} berhasil diunduh (${name}).` });
      setReportModal(null);
    } catch (e) {
      setExportMsg({ ok: false, message: errMsg(e, `Gagal mengunduh rapor ${designer}.`) });
    } finally { setReportBusy(""); }
  }

  async function escalateNow() {
    setBusy(true);
    setRunInfo(null);
    try {
      const run = await runSlaEscalation();
      const created = Number(run?.created || 0);
      setRunInfo({
        ok: run?.status === "success",
        message: run?.status === "success"
          ? (created > 0
            ? `${created} peringatan terkirim — ${run?.detail || ""}`
            : `Tidak ada peringatan baru: ${run?.detail || "semua sudah dikirim hari ini"}. `
              + "Satu round hanya diperingatkan sekali per hari.")
          : `Gagal menjalankan eskalasi: ${run?.error || "tidak diketahui"}`,
      });
      await load();
    } catch (e) {
      setRunInfo({ ok: false, message: errMsg(e, "Gagal menjalankan eskalasi SLA.") });
    } finally {
      setBusy(false);
    }
  }

  const items = report?.items || [];
  const sum = report?.summary || {};
  const w = report?.weights || null;
  const bands = report?.grade_bands || [];
  const periodOpts = (report?.period_options?.length ? report.period_options
    : PERIOD_OPTIONS);
  const divisionOpts = [{ value: "", label: "Semua divisi" },
    ...((report?.divisions_present || []).map((d) => ({ value: d.id, label: d.name })))];
  const best = items.find((r) => r.grade_score !== null) || null;

  return (
    <div className="grid gap-3" data-testid="designer-kpi-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
        testId="designer-kpi-error" />

      {/* ── Toolbar + ringkasan ─────────────────────────────────────────── */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <BarChart3 size={16} className="text-[#0058CC]" />
            <h2 data-testid="designer-kpi-title">KPI Desainer</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <KNSelect data-testid="designer-kpi-division" value={division}
              onValueChange={setDivision} options={divisionOpts} className="field !w-[160px]" />
            <KNSelect data-testid="designer-kpi-period" value={period}
              onValueChange={setPeriod} options={periodOpts} className="field !w-[170px]" />
            <button className="secondary-button" onClick={load}
              data-testid="designer-kpi-refresh">
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
            </button>
            <button className="secondary-button" onClick={() => setShowHow((v) => !v)}
              data-testid="designer-kpi-how-toggle">
              <Info size={13} /> Cara nilai dihitung
            </button>
            <button className="secondary-button" onClick={() => download("xlsx")}
              disabled={Boolean(exporting)} data-testid="designer-kpi-export-xlsx"
              title="Unduh sebagai Excel (bisa diolah lagi)">
              <FileSpreadsheet size={13} className={exporting === "xlsx" ? "animate-pulse" : ""} />
              {exporting === "xlsx" ? "Menyiapkan…" : "Excel"}
            </button>
            <button className="secondary-button" onClick={() => download("pdf")}
              disabled={Boolean(exporting)} data-testid="designer-kpi-export-pdf"
              title="Unduh sebagai PDF siap cetak untuk rapat">
              <FileText size={13} className={exporting === "pdf" ? "animate-pulse" : ""} />
              {exporting === "pdf" ? "Menyiapkan…" : "PDF"}
            </button>
            <button className="secondary-button" onClick={() => download("csv")}
              disabled={Boolean(exporting)} data-testid="designer-kpi-export-csv"
              title="Unduh sebagai CSV">
              <Download size={13} className={exporting === "csv" ? "animate-pulse" : ""} /> CSV
            </button>
            {canManage && (
              <button className="secondary-button" data-testid="designer-kpi-policy-button"
                onClick={() => openConfig({ group: "rnd", key: "rnd.kpi_weight_on_time" })}>
                <Settings2 size={13} /> Ubah bobot nilai
              </button>
            )}
          </div>
        </div>
        <div className="section-body space-y-2">
          {exportMsg && (
            <div className={`notice-bar ${exportMsg.ok ? "success" : "danger"} !mb-0 !py-1.5`}
              data-testid="designer-kpi-export-result">
              <span className="text-[11.5px]">{exportMsg.message}</span>
              <button onClick={() => setExportMsg(null)}
                data-testid="designer-kpi-export-dismiss">Tutup</button>
            </div>
          )}
          <p className="text-[11.5px] text-[#6B6B73]" data-testid="designer-kpi-period-note">
            Periode: <b>{report?.period_label || "—"}</b>
            {report?.from_date ? ` (${report.from_date} s/d ${report.to_date})` : ""}
            {" · "}angka terbentuk sendiri dari round sample yang disetor beserta buktinya —
            tidak ada input manual.
          </p>

          {loading && !report ? (
            <p className="py-8 text-center text-[12px] text-[#6B6B73]"
              data-testid="designer-kpi-loading">Memuat KPI desainer…</p>
          ) : (
            <div className="grid grid-cols-2 gap-2 md:grid-cols-6"
              data-testid="designer-kpi-summary">
              <Kpi label="Desainer aktif" value={String(sum.designers ?? 0)} />
              <Kpi label="Round dikerjakan" value={String(sum.rounds ?? 0)} tone="#0058CC" />
              <Kpi label="Tepat waktu" value={num(sum.on_time_pct, "%")}
                tone={(sum.on_time_pct ?? 0) >= 80 ? "#1B7F4B" : "#B26A00"} />
              <Kpi label="Kerja diulang" value={num(sum.rework_pct, "%")}
                tone={(sum.rework_pct ?? 0) <= 30 ? "#1B7F4B" : "#C0392B"} />
              <Kpi label="Nunggak lewat tenggat" value={String(sum.overdue_now ?? 0)}
                tone={(sum.overdue_now ?? 0) > 0 ? "#C0392B" : "#1B7F4B"} />
              <Kpi label="Biaya sample" value={formatCurrency(sum.cost_total || 0)} />
            </div>
          )}

          {showHow && w && (
            <div className="rounded-lg border border-[#DCE7FF] bg-[#F5F9FF] p-2.5"
              data-testid="designer-kpi-how">
              <p className="mb-1 text-[11px] font-bold uppercase text-[#0058CC]">
                Cara nilai (grade) dihitung
              </p>
              <p className="text-[11.5px] leading-relaxed text-[#3C3C43]">
                {gradeFormula(w)}
              </p>
              <p className="mt-1 text-[11.5px] leading-relaxed text-[#6B6B73]">
                Bila satu komponen belum punya data (mis. belum ada round yang dinilai),
                bobotnya tidak dihitung nol — bobot sisanya disesuaikan, supaya desainer
                baru tidak langsung jatuh ke nilai terendah.
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {bands.map((b) => {
                  const g = gradeMeta(b.letter);
                  return (
                    <span key={b.letter} className={`status-pill ${g.cls}`}
                      data-testid={`designer-kpi-band-${b.letter}`}>
                      {b.letter} · {b.min}+ · {b.meaning}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── Tren nilai desainer per bulan (grafik) ──────────────────────── */}
      <DesignerKpiTrendChart params={params} testId="designer-kpi-trend" />

      {/* ── Desainer terbaik + tabel ────────────────────────────────────── */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Users size={16} className="text-[#0058CC]" />
            <h2>Peringkat kinerja desainer</h2>
          </div>
          {best && (
            <span className="flex items-center gap-1.5 text-[11.5px]"
              data-testid="designer-kpi-best">
              <Award size={13} className="text-[#B8860B]" />
              Terbaik periode ini: <b>{best.designer}</b>
              <span className={`status-pill ${gradeMeta(best.grade_letter).cls}`}>
                {best.grade_letter} · {num(best.grade_score)}
              </span>
            </span>
          )}
        </div>
        <div className="section-body">
          {loading && !report ? (
            <p className="py-8 text-center text-[12px] text-[#6B6B73]"
              data-testid="designer-kpi-table-loading">Memuat tabel…</p>
          ) : (
            <>
              <DesignerKpiTable items={items} selected={focusDesigner}
                loading={loading && !report} onSelect={setFocusDesigner}
                onDownloadReport={(designer) => {
                  setExportMsg(null);
                  setReportModal({ designer, note: "" });
                }}
                downloadingReport={reportBusy} />
              {focusDesigner && (
                <p className="mt-2 text-[11px] text-[#0058CC]"
                  data-testid="designer-kpi-filter-note">
                  Papan eskalasi di bawah disaring untuk <b>{focusDesigner}</b> —
                  klik baris yang sama sekali lagi untuk melihat semuanya.
                </p>
              )}
              <p className="mt-2 text-[10.5px] leading-relaxed text-[#9A9BA3]">
                Penanggung jawab round = yang menyetor hasilnya; bila round masih berjalan
                dipakai yang membuka round tersebut. Kolom bisa diklik untuk mengurutkan.
              </p>
            </>
          )}
        </div>
      </section>

      {/* ── Papan eskalasi SLA (aktif) ──────────────────────────────────── */}
      <DesignerSlaPanel board={board} filterDesigner={focusDesigner} busy={busy}
        canManage={canManage} onEscalate={escalateNow} runInfo={runInfo} />

      {/* ── Modal: catatan evaluasi sebelum unduh Rapor PDF ─────────────── */}
      {reportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          data-testid="designer-report-modal"
          onClick={() => !reportBusy && setReportModal(null)}>
          <div className="w-full max-w-lg rounded-xl bg-white p-4 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center gap-2">
              <FileText size={16} className="text-[#0058CC]" />
              <h3 className="text-[14px] font-bold text-[#1C1C1E]">
                Rapor PDF — {reportModal.designer}
              </h3>
            </div>
            <p className="mb-2 text-[11.5px] text-[#6B6B73]">
              Tambahkan catatan evaluasi bebas (opsional). Catatan ini muncul sebagai
              kotak <b>“Catatan Evaluasi”</b> di rapor, siap ditandatangani. Kosongkan bila
              tidak perlu.
            </p>
            <textarea
              data-testid="designer-report-note"
              value={reportModal.note}
              maxLength={1200}
              rows={5}
              onChange={(e) => setReportModal((m) => ({ ...m, note: e.target.value }))}
              placeholder={"Contoh:\nKonsistensi warna membaik. Perlu percepat setor <2 hari.\nTanda tangan: ................"}
              className="field !h-auto w-full resize-y text-[12px]" />
            <div className="mt-1 flex items-center justify-between">
              <span className="text-[10px] text-[#9A9BA3]">
                {reportModal.note.length}/1200
              </span>
            </div>
            <div className="mt-3 flex items-center justify-end gap-2">
              <button className="secondary-button" disabled={Boolean(reportBusy)}
                data-testid="designer-report-cancel"
                onClick={() => setReportModal(null)}>Batal</button>
              <button className="primary-button" disabled={Boolean(reportBusy)}
                data-testid="designer-report-download"
                onClick={() => downloadReport(reportModal.designer, reportModal.note)}>
                <FileText size={13} className={reportBusy ? "animate-pulse" : ""} />
                {reportBusy ? "Menyiapkan…" : "Unduh PDF"}
              </button>
            </div>
          </div>
        </div>
      )}
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
