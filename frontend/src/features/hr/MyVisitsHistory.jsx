/**
 * MyVisitsHistory — FASE E-8 (E8.3 · SD4) · **RIWAYAT KUNJUNGAN SAYA + KPI**.
 *
 * Menu "Kunjungan Sales" dulu terlihat oleh sales tetapi selalu 403: layarnya memakai
 * `GET /api/hr/visits` yang bergerbang izin `hr.view` (izin HR — memuat kunjungan
 * SELURUH karyawan). Dua obat yang salah: memberi sales izin HR (ikut membuka data
 * rekan) atau menyembunyikan menunya (sales kehilangan catatan kerjanya sendiri).
 *
 * Obat yang benar dipakai di sini: `GET /api/hr/visits/mine` — hanya kunjungan milik
 * akun yang login (pagarnya `employee_id` dari sesi, bukan parameter yang bisa diputar),
 * lengkap dengan KPI bulanan yang dulu hanya dilihat manajer.
 */
import { useCallback, useEffect, useState } from "react";
import { BarChart3, Building2, MapPin, RefreshCw } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import { apiErrorText } from "../../utils/apiError";
import { myVisitsHistory } from "../sales_admin/workDeskApi";
import { OUTCOME_PILL, VISIT_STATUS_PILL, fmtMin, fmtTime, monthStr } from "./trackingUtils";

export default function MyVisitsHistory() {
  const [month, setMonth] = useState(monthStr());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await myVisitsHistory(month)); setError(""); }
    catch (e) { setError(apiErrorText(e, "Gagal memuat riwayat kunjungan Anda.")); }
    finally { setLoading(false); }
  }, [month]);

  useEffect(() => { load(); }, [load]);

  const t = data?.totals || {};
  const rows = Array.isArray(data?.rows) ? data.rows : [];

  return (
    <div className="section-card mt-3" data-testid="my-visits-history">
      <div className="section-head">
        <div className="flex min-w-0 items-center gap-2">
          <BarChart3 size={15} className="text-[#0058CC]" />
          <h2 data-testid="my-visits-history-title">Riwayat &amp; KPI Kunjungan Saya</h2>
        </div>
        <div className="flex items-center gap-2">
          <input data-testid="my-visits-history-month" type="month" value={month}
                 onChange={(e) => setMonth(e.target.value)} className="field !py-1 !w-[140px]" />
          <button data-testid="my-visits-history-refresh" className="icon-button" onClick={load}
                  aria-label="Muat ulang riwayat">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
                   testId="my-visits-history-error" />

      <div className="grid grid-cols-2 gap-2 p-3 lg:grid-cols-4" data-testid="my-visits-kpi">
        <Kpi label="Total Kunjungan" value={t.total ?? 0} testId="my-visits-kpi-total" />
        <Kpi label="Selesai" value={t.done ?? 0} color="#1B7F4B" testId="my-visits-kpi-done" />
        <Kpi label="Berbuah Pesanan" value={t.with_order ?? 0} color="#0058CC"
             testId="my-visits-kpi-order" />
        <Kpi label="Konversi" value={`${t.conversion_percent ?? 0}%`} color="#6B219A"
             testId="my-visits-kpi-conversion"
             hint={`Total waktu ${fmtMin(t.total_minutes || 0)}`} />
      </div>

      <div className="grid grid-cols-[1.6fr_84px_84px_72px_96px_96px] border-y border-[#EFF0F2] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
        <span>Pelanggan</span><span>Masuk</span><span>Keluar</span>
        <span className="text-right">Durasi</span><span>Hasil</span><span>Status</span>
      </div>

      {loading ? (
        <div className="py-10 text-center text-[12px] text-[#6B6B73]"
             data-testid="my-visits-history-loading">Memuat riwayat kunjungan…</div>
      ) : rows.length === 0 ? (
        <div className="py-12 text-center text-[12px] text-[#6B6B73]"
             data-testid="my-visits-history-empty">
          <MapPin className="mx-auto mb-2 text-[#D6D6DB]" size={26} />
          <p>Belum ada kunjungan tercatat pada {month}. Mulai kunjungan dari kartu di atas.</p>
        </div>
      ) : (
        <div className="max-h-[420px] divide-y divide-[#EFF0F2] overflow-y-auto">
          {rows.map((v) => {
            const oc = OUTCOME_PILL[v.outcome] || OUTCOME_PILL[""];
            const st = VISIT_STATUS_PILL[v.status] || VISIT_STATUS_PILL.done;
            return (
              <div key={v.id} data-testid={`my-visit-hist-${v.id}`}
                   className="grid grid-cols-[1.6fr_84px_84px_72px_96px_96px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                <span className="flex items-center gap-1 truncate text-[12px] font-semibold">
                  <Building2 size={12} className="shrink-0 text-[#9A9BA3]" /> {v.customer_name}
                </span>
                <span className="text-[11.5px] tabular-nums">{fmtTime(v.check_in?.ts)}</span>
                <span className="text-[11.5px] tabular-nums">{fmtTime(v.check_out?.ts)}</span>
                <span className="text-right text-[11.5px] tabular-nums">{fmtMin(v.duration_min)}</span>
                <span><span className={`status-pill ${oc.cls}`}>{oc.label}</span></span>
                <span><span className={`status-pill ${st.cls}`}>{st.label}</span></span>
              </div>
            );
          })}
        </div>
      )}

      <p className="px-3 py-2 text-[10.5px] text-[#9A9BA3]">
        Hanya kunjungan milik akun Anda. Rekap seluruh karyawan adalah wewenang manajer.
      </p>
    </div>
  );
}

function Kpi({ label, value, color, hint, testId }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] px-3 py-2" data-testid={testId}>
      <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
      <p className="text-[17px] font-bold leading-tight tabular-nums"
         style={{ color: color || "#1A1A1F" }}>{value}</p>
      {hint && <p className="text-[10px] text-[#9A9BA3]">{hint}</p>}
    </div>
  );
}
