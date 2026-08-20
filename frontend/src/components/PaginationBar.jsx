/**
 * PaginationBar — kontrol paginasi reusable (P2) + **Unduh CSV** (P6).
 * Menampilkan rentang "X–Y dari N", tombol Prev/Next, indikator halaman,
 * pemilih ukuran halaman berbasis tombol (lolos ux_audit — tanpa dropdown bawaan),
 * dan tombol Unduh CSV bila `exportConfig` diberikan.
 *
 * Props:
 *  - page, pageSize, total, hasMore, loading
 *  - onPrev, onNext, onPageSize (opsional)
 *  - testId  (prefix data-testid, default "pager")
 *  - pageSizeOptions (default [20, 50, 100])
 *  - label   (kata benda entitas, mis. "roll", "order")
 *  - exportConfig (opsional → memunculkan tombol Unduh CSV):
 *      {
 *        columns:  [{ key, header, type?, get? }]   // lihat utils/csvExport.js
 *        rows:     baris HALAMAN AKTIF (yang sedang dilihat)
 *        fetchAll: async ({onProgress, isCancelled}) => semua baris hasil filter
 *        filename: dasar nama berkas, mis. "retur-jual"
 *      }
 *
 * KENAPA UNDUH DIPASANG DI SINI, BUKAN DI 12 LAYAR (FASE P6)
 * =========================================================
 * Komponen ini sudah menjadi satu-satunya kontrol halaman di seluruh aplikasi, jadi ia
 * adalah satu-satunya tempat yang **pasti** ada di setiap daftar berhalaman. Menaruh
 * tombol Unduh di sini berarti: satu perilaku, satu bentuk dialog, satu format berkas —
 * dan daftar berhalaman BERIKUTNYA ikut kebagian tanpa ada yang perlu ingat. Bila tiap
 * layar membuat tombolnya sendiri, dalam beberapa sesi akan ada 12 varian yang berbeda
 * soal cakupan, nama berkas, dan pemisah kolom.
 *
 * TIGA KEPUTUSAN YANG SENGAJA DIAMBIL DI SINI
 * -------------------------------------------
 *  1. **Pengguna yang memilih cakupan** (keputusan pemilik): "Halaman ini" atau "Semua
 *     hasil filter", lewat `askChoice()` — standar dialog yang sama dengan FASE P5.
 *  2. **Dialognya DILEWATI bila kedua pilihan identik.** Saat seluruh hasil filter sudah
 *     tampil di satu halaman, "Halaman ini" == "Semua hasil filter". Menanyakannya tetap
 *     hanya menambah satu klik untuk pertanyaan yang tidak punya dua jawaban.
 *  3. **Gagal = bilah yang MENEMPEL, bukan toast** (`ErrorNotice`, keputusan pemilik P5).
 *     Bilahnya dirender oleh komponen ini sendiri supaya tidak ada layar yang bisa
 *     "lupa" menyediakan tempat galat dan membuat kegagalan unduh jadi senyap.
 */
import { useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Loader2 } from "lucide-react";
import ErrorNotice from "./ErrorNotice";
import { askChoice } from "../services/confirmService";
import { notifySuccess } from "../utils/feedback";
import { apiErrorText } from "../utils/apiError";
import { buildCsv, csvFilename, downloadCsv } from "../utils/csvExport";

export default function PaginationBar({
  page = 1,
  pageSize = 20,
  total = 0,
  hasMore = false,
  loading = false,
  onPrev,
  onNext,
  onPageSize,
  testId = "pager",
  pageSizeOptions = [20, 50, 100],
  label = "data",
  exportConfig = null,
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(null);   // {done,total} saat menarik semua
  const [exportError, setExportError] = useState("");
  const cancelRef = useRef(false);

  const rowsOnPage = exportConfig?.rows || [];
  // "Semua hasil filter" hanya berbeda bila memang ada baris di luar halaman ini.
  const allDiffersFromPage =
    typeof exportConfig?.fetchAll === "function" && total > rowsOnPage.length;

  async function handleExport() {
    if (!exportConfig || exporting) return;
    const { columns, fetchAll, filename } = exportConfig;
    setExportError("");

    let scope = "page";
    if (allDiffersFromPage) {
      const pilihan = await askChoice({
        title: `Unduh ${label} sebagai CSV`,
        message: "Pilih seberapa banyak yang ikut diunduh. Filter dan pencarian yang "
          + "sedang aktif tetap dipakai untuk keduanya.",
        choices: [
          {
            key: "page",
            label: `Halaman ini — ${rowsOnPage.length} baris`,
            description: `Hanya yang terlihat sekarang (halaman ${page} dari ${totalPages}).`,
          },
          {
            key: "all",
            label: `Semua hasil filter — ${total} baris`,
            description: "Seluruh baris yang lolos filter & pencarian, dari semua halaman.",
          },
        ],
      });
      if (!pilihan) return;              // null = pengguna menutup dialog
      scope = pilihan;
    }

    setExporting(true);
    cancelRef.current = false;
    try {
      let rows = rowsOnPage;
      if (scope === "all") {
        setProgress({ done: 0, total });
        rows = await fetchAll({
          onProgress: (done, grandTotal) => setProgress({ done, total: grandTotal }),
          isCancelled: () => cancelRef.current,
        });
      }
      const csv = buildCsv(rows, columns);
      downloadCsv(csvFilename(filename || label, scope), csv);
      notifySuccess(
        `${rows.length} baris diunduh`,
        `Berkas CSV siap dibuka di Excel (pemisah titik-koma).`,
      );
    } catch (e) {
      setExportError(apiErrorText(e, "Gagal menyiapkan berkas CSV."));
    } finally {
      setExporting(false);
      setProgress(null);
    }
  }

  return (
    <>
      <div
        data-testid={`${testId}-bar`}
        className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#EFF0F2] bg-white px-3 py-2"
      >
        <span data-testid={`${testId}-info`} className="text-[11.5px] text-[#6B6B73] tabular-nums">
          {total === 0 ? `Tidak ada ${label}` : (
            <>Menampilkan <strong className="text-[#1C1C1E]">{from}–{to}</strong> dari <strong className="text-[#1C1C1E]">{total}</strong> {label}</>
          )}
        </span>

        <div className="flex items-center gap-2">
          {exportConfig && (
            <button
              type="button"
              data-testid={`${testId}-export`}
              onClick={handleExport}
              disabled={loading || exporting || total === 0}
              title={`Unduh ${label} sebagai berkas CSV (mengikuti filter & pencarian aktif)`}
              className="inline-flex items-center gap-1 rounded-md border border-[#E5E5EA] bg-white px-2.5 py-1 text-[11.5px] font-semibold text-[#3C3C43] hover:border-[#007AFF] hover:text-[#0058CC] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {exporting
                ? <><Loader2 size={13} className="animate-spin" />
                    {progress
                      ? `Menyiapkan ${progress.done}/${progress.total}…`
                      : "Menyiapkan…"}</>
                : <><Download size={13} /> Unduh CSV</>}
            </button>
          )}

          {onPageSize && (
            <div className="flex items-center gap-1" data-testid={`${testId}-sizes`}>
              <span className="text-[10.5px] text-[#8E8E93] mr-1">Per halaman</span>
              {pageSizeOptions.map((sz) => (
                <button
                  key={sz}
                  data-testid={`${testId}-size-${sz}`}
                  onClick={() => onPageSize(sz)}
                  disabled={loading}
                  className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors disabled:opacity-50 ${
                    pageSize === sz
                      ? "bg-[#007AFF] text-white"
                      : "bg-white border border-[#E5E5EA] text-[#6B6B73] hover:border-[#007AFF]"
                  }`}
                >
                  {sz}
                </button>
              ))}
            </div>
          )}

          <div className="flex items-center gap-1">
            <button
              data-testid={`${testId}-prev`}
              onClick={onPrev}
              disabled={page <= 1 || loading}
              className="inline-flex items-center gap-1 rounded-md border border-[#E5E5EA] bg-white px-2.5 py-1 text-[11.5px] font-semibold text-[#3C3C43] hover:bg-[#F2F2F7] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft size={13} /> Sebelumnya
            </button>
            <span data-testid={`${testId}-page`} className="px-2 text-[11.5px] font-semibold text-[#6B6B73] tabular-nums whitespace-nowrap">
              Hal {page} / {totalPages}
            </span>
            <button
              data-testid={`${testId}-next`}
              onClick={onNext}
              disabled={!hasMore || loading}
              className="inline-flex items-center gap-1 rounded-md border border-[#E5E5EA] bg-white px-2.5 py-1 text-[11.5px] font-semibold text-[#3C3C43] hover:bg-[#F2F2F7] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Berikutnya <ChevronRight size={13} />
            </button>
          </div>
        </div>
      </div>

      {exportError && (
        <div className="mt-2">
          <ErrorNotice
            message={exportError}
            onRetry={handleExport}
            onDismiss={() => setExportError("")}
            testId={`${testId}-export-error`}
          />
        </div>
      )}
    </>
  );
}
