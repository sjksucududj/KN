/**
 * ClosingView (FINANCE) — Tutup Buku bulanan & tahunan.
 * Buat jurnal penutup otomatis (Laba Bersih → Laba Ditahan 3-2000) + kunci periode
 * (soft). Admin dapat Reopen. Sumber: /api/finance/closing/*. Gaya modul GL.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, CalendarX, Lock, Unlock, FileStack, CheckCircle2, AlertTriangle,
  Eye, Building2, RotateCcw,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";

const NOW = new Date();
const MONTHS = [
  { value: "01", label: "Januari" }, { value: "02", label: "Februari" },
  { value: "03", label: "Maret" }, { value: "04", label: "April" },
  { value: "05", label: "Mei" }, { value: "06", label: "Juni" },
  { value: "07", label: "Juli" }, { value: "08", label: "Agustus" },
  { value: "09", label: "September" }, { value: "10", label: "Oktober" },
  { value: "11", label: "November" }, { value: "12", label: "Desember" },
];
const YEARS = Array.from({ length: 6 }, (_, i) => {
  const y = String(NOW.getFullYear() - i);
  return { value: y, label: y };
});

function fmtDateTime(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

export default function ClosingView({ selectedEntity, entities = [], currentUser }) {
  const isAdmin = currentUser?.role === "admin";
  const entityOptions = useMemo(
    () => entities.filter((e) => !e.is_group).map((e) => ({ value: e.id, label: e.short_name || e.legal_name || e.id })),
    [entities]);

  const initialEntity = useMemo(() => {
    if (selectedEntity && selectedEntity !== "all") return selectedEntity;
    return entityOptions[0]?.value || "";
  }, [selectedEntity, entityOptions]);

  const [entityId, setEntityId] = useState(initialEntity);
  useEffect(() => { if (initialEntity && !entityId) setEntityId(initialEntity); }, [initialEntity, entityId]);

  const [periodType, setPeriodType] = useState("month");
  const [month, setMonth] = useState(String(NOW.getMonth() + 1).padStart(2, "0"));
  const [year, setYear] = useState(String(NOW.getFullYear()));

  const [closings, setClosings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const periodKey = periodType === "year" ? year : `${year}-${month}`;

  const load = useCallback(async () => {
    if (!entityId) { setClosings([]); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/finance/closing`, { params: { entity_id: entityId } });
      setClosings(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data tutup buku.");
    } finally {
      setLoading(false);
    }
  }, [entityId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPreview(null); }, [periodType, month, year, entityId]);

  const doPreview = async () => {
    setError(""); setNotice(""); setBusy(true);
    try {
      const res = await axios.get(`${API}/finance/closing/preview`, {
        params: { period_type: periodType, period_key: periodKey, entity_id: entityId },
      });
      setPreview(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat pratinjau.");
    } finally {
      setBusy(false);
    }
  };

  const doClose = async () => {
    setError(""); setNotice(""); setBusy(true);
    try {
      const res = await axios.post(`${API}/finance/closing/close`, {
        period_type: periodType, period_key: periodKey, entity_id: entityId,
      });
      setNotice(`Periode ${res.data.period_label} berhasil ditutup. Jurnal penutup: ${res.data.journal_entry_number || "—"}.`);
      setPreview(null);
      load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menutup periode.");
    } finally {
      setBusy(false);
    }
  };

  const doReopen = async (rec) => {
    setError(""); setNotice(""); setBusy(true);
    try {
      await axios.post(`${API}/finance/closing/${rec.id}/reopen`);
      setNotice(`Periode ${rec.period_label} dibuka kembali (jurnal penutup di-void).`);
      load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal membuka kembali periode.");
    } finally {
      setBusy(false);
    }
  };

  const doReclose = async (rec) => {
    setError(""); setNotice(""); setBusy(true);
    try {
      const res = await axios.post(`${API}/finance/closing/${rec.id}/reclose`);
      setNotice(`Periode ${res.data.period_label} ditutup ulang. Jurnal penutup baru: ${res.data.journal_entry_number || "—"}.`);
      load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menutup ulang periode.");
    } finally {
      setBusy(false);
    }
  };

  const canReclose = isAdmin || currentUser?.role === "manager";

  const closedCount = closings.filter((c) => c.status === "closed").length;

  return (
    <div data-testid="closing-view">
      {/* KPI ringkas */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-3">
        <Kpi testId="closing-kpi-closed" label="Periode Tertutup" value={closedCount} icon={Lock} tone="text-[#6B219A]" />
        <Kpi testId="closing-kpi-total" label="Total Riwayat" value={closings.length} icon={FileStack} />
        <Kpi testId="closing-kpi-entity" label="Entitas Aktif" value={entityOptions.find((e) => e.value === entityId)?.label || "—"} icon={Building2} />
      </div>

      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 flex-wrap">
            <CalendarX size={15} className="text-[#6B219A]" />
            <h3 className="text-[13px] font-bold text-[#1C1C1E]">Tutup Buku (Closing)</h3>
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <div className="w-[200px]">
              <KNSelect data-testid="closing-entity-select" className="field py-1.5 text-[12px]" value={entityId}
                onValueChange={setEntityId} placeholder="Pilih Entitas (PT)" options={entityOptions} />
            </div>
            <button data-testid="closing-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>

        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="closing-error" />
          {notice && (
            <div data-testid="closing-notice" className="mb-3 rounded-md bg-[#E6F6EC] border border-[#BDE5CC] text-[#1B7F4B] text-[12px] px-3 py-2 flex items-center gap-2">
              <CheckCircle2 size={14} />{notice}
              <button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup">✕</button>
            </div>
          )}

          {!entityId ? (
            <div data-testid="closing-no-entity" className="py-10 text-center text-[12px] text-[#8E8E93]">
              <Building2 size={26} className="mx-auto mb-2 text-gray-300" />Pilih entitas (PT) terlebih dahulu untuk tutup buku.
            </div>
          ) : (
            <>
              {/* Form tutup buku */}
              <div className="rounded-lg border border-[#EFF0F2] p-3 mb-4 bg-[#FCFCFD]">
                <div className="flex flex-wrap items-end gap-3">
                  <Labeled label="Jenis Periode">
                    <div className="w-[140px]">
                      <KNSelect data-testid="closing-period-type" className="field py-1.5 text-[12px]" value={periodType}
                        onValueChange={setPeriodType} options={[{ value: "month", label: "Bulanan" }, { value: "year", label: "Tahunan" }]} />
                    </div>
                  </Labeled>
                  {periodType === "month" && (
                    <Labeled label="Bulan">
                      <div className="w-[150px]">
                        <KNSelect data-testid="closing-month" className="field py-1.5 text-[12px]" value={month} onValueChange={setMonth} options={MONTHS} />
                      </div>
                    </Labeled>
                  )}
                  <Labeled label="Tahun">
                    <div className="w-[110px]">
                      <KNSelect data-testid="closing-year" className="field py-1.5 text-[12px]" value={year} onValueChange={setYear} options={YEARS} />
                    </div>
                  </Labeled>
                  <button data-testid="closing-preview-btn" onClick={doPreview} disabled={busy}
                    className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1">
                    <Eye size={13} /> Pratinjau
                  </button>
                  <button data-testid="closing-close-btn" onClick={doClose} disabled={busy}
                    className="btn-primary text-[12px] py-1.5 px-4 inline-flex items-center gap-1">
                    <Lock size={13} /> Tutup Buku
                  </button>
                </div>

                {/* Pratinjau */}
                {preview && (
                  <div className="mt-3 pt-3 border-t border-[#EFF0F2]" data-testid="closing-preview">
                    {!preview.can_close && (
                      <div className="mb-2 rounded-md bg-[#FDEDE7] border border-[#F5C6C0] text-[#C0392B] text-[12px] px-3 py-2 flex items-center gap-2" data-testid="closing-preview-block">
                        <AlertTriangle size={14} />
                        Periode tumpang tindih dengan penutupan aktif{preview.blocking_closing ? ` (${preview.blocking_closing.period_label})` : ""}. Buka kembali dulu untuk menutup ulang.
                      </div>
                    )}
                    {preview.suspense_warning && (
                      <div className="mb-2 rounded-md bg-[#FDF3E7] border border-[#F0D9B8] text-[#B9770E] text-[12px] px-3 py-2 flex items-center gap-2" data-testid="closing-preview-suspense">
                        <AlertTriangle size={14} />
                        Saldo Suspense (1-9999) belum nol: {formatCurrency(preview.suspense_balance)}. Sebaiknya reklasifikasi via Buku Besar → tab Suspense sebelum tutup buku.
                      </div>
                    )}
                    {Math.abs((preview.residual_net_income || 0) - (preview.net_income || 0)) > 0.01 && (
                      <div className="mb-2 rounded-md bg-[#F3EAFB] border border-[#E3CCF3] text-[#6B219A] text-[12px] px-3 py-2 flex items-center gap-2" data-testid="closing-preview-residual">
                        <Lock size={14} />
                        Sebagian periode sudah ditutup bulanan. Jurnal ini hanya menutup <b>sisa</b>: {formatCurrency(preview.residual_net_income)} (dari total {formatCurrency(preview.net_income)}).
                      </div>
                    )}
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
                      <MiniStat label="Pendapatan" value={formatCurrency(preview.revenue_total)} tone="text-[#1B7F4B]" />
                      <MiniStat label="Beban" value={formatCurrency(preview.expense_total)} tone="text-[#C0392B]" />
                      <MiniStat label="Laba/Rugi Bersih → Laba Ditahan" value={formatCurrency(preview.net_income)} tone={preview.net_income >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"} />
                    </div>
                    <p className="text-[11px] font-bold uppercase tracking-wide text-[#8E8E93] mb-1">Jurnal Penutup (Pratinjau)</p>
                    {(preview.closing_lines || []).length === 0 ? (
                      <p className="text-[12px] text-[#9A9BA3]">Tidak ada saldo laba/rugi untuk ditutup pada periode ini.</p>
                    ) : (
                      <div className="overflow-auto rounded-md border border-[#EFF0F2]">
                        <table className="w-full text-[12px]">
                          <thead>
                            <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                              <th className="px-3 py-2">Akun</th>
                              <th className="px-3 py-2 text-right">Debit</th>
                              <th className="px-3 py-2 text-right">Kredit</th>
                            </tr>
                          </thead>
                          <tbody>
                            {preview.closing_lines.map((ln, i) => (
                              <tr key={i} className="border-b border-[#F5F5F7] last:border-0">
                                <td className="px-3 py-1.5"><span className="font-mono text-[10px] text-[#9A9BA3] mr-1.5">{ln.account_code}</span>{ln.description}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums">{ln.debit > 0 ? formatCurrency(ln.debit) : "—"}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums">{ln.credit > 0 ? formatCurrency(ln.credit) : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Riwayat penutupan */}
              <p className="text-[11px] font-bold uppercase tracking-wide text-[#8E8E93] mb-2">Riwayat Tutup Buku</p>
              {loading ? (
                <div className="grid gap-2" data-testid="closing-loading">{[0, 1, 2].map((i) => <div key={i} className="h-10 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
              ) : closings.length === 0 ? (
                <div data-testid="closing-empty" className="py-10 text-center text-[12px] text-[#8E8E93]">
                  <CalendarX size={26} className="mx-auto mb-2 text-gray-300" />Belum ada periode yang ditutup untuk entitas ini.
                </div>
              ) : (
                <div className="overflow-auto rounded-md border border-[#EFF0F2]">
                  <table className="w-full text-[12px]">
                    <thead>
                      <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                        <th className="px-3 py-2">Periode</th>
                        <th className="px-3 py-2">Jenis</th>
                        <th className="px-3 py-2 text-right">Laba/Rugi Bersih</th>
                        <th className="px-3 py-2">Jurnal Penutup</th>
                        <th className="px-3 py-2 text-center">Status</th>
                        <th className="px-3 py-2">Ditutup</th>
                        <th className="px-3 py-2 text-right">Aksi</th>
                      </tr>
                    </thead>
                    <tbody>
                      {closings.map((c) => (
                        <tr key={c.id} data-testid={`closing-row-${c.id}`} className="border-b border-[#F5F5F7] last:border-0">
                          <td className="px-3 py-2 font-semibold text-[#1C1C1E]">{c.period_label}</td>
                          <td className="px-3 py-2 text-[#6B6B73]">{c.period_type === "year" ? "Tahunan" : "Bulanan"}</td>
                          <td className={`px-3 py-2 text-right tabular-nums font-semibold ${c.net_income >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}>{formatCurrency(c.net_income)}</td>
                          <td className="px-3 py-2 font-mono text-[11px] text-[#9A9BA3]">{c.journal_entry_number || "—"}</td>
                          <td className="px-3 py-2 text-center">
                            {c.status === "closed"
                              ? <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-[#F3EAFB] text-[#6B219A] inline-flex items-center gap-1"><Lock size={10} /> Tertutup</span>
                              : <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-[#FDF3E7] text-[#B26B00] inline-flex items-center gap-1"><Unlock size={10} /> Dibuka</span>}
                            {c.stale && c.status === "closed" && (
                              <span data-testid={`closing-stale-${c.id}`} title={c.stale_reason || "Angka berubah setelah periode ditutup"}
                                className="ml-1 text-[9px] font-bold rounded-full px-1.5 py-0.5 bg-[#FDEDE7] text-[#C0392B] inline-flex items-center gap-1">
                                <AlertTriangle size={9} /> Basi
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-[11px] text-[#6B6B73]">{c.closed_by}<br /><span className="text-[10px] text-[#9A9BA3]">{fmtDateTime(c.closed_at)}</span></td>
                          <td className="px-3 py-2 text-right">
                            <div className="inline-flex items-center gap-1 justify-end">
                              {c.status === "closed" && c.stale && canReclose && (
                                <button data-testid={`closing-reclose-${c.id}`} onClick={() => doReclose(c)} disabled={busy}
                                  className="btn-secondary text-[11px] py-1 px-2 inline-flex items-center gap-1 text-[#6B219A]">
                                  <RotateCcw size={12} /> Tutup Ulang
                                </button>
                              )}
                              {c.status === "closed" && isAdmin && (
                                <button data-testid={`closing-reopen-${c.id}`} onClick={() => doReopen(c)} disabled={busy}
                                  className="btn-secondary text-[11px] py-1 px-2 inline-flex items-center gap-1 text-[#B26B00]">
                                  <Unlock size={12} /> Reopen
                                </button>
                              )}
                              {!(c.status === "closed" && (isAdmin || (c.stale && canReclose))) && <span className="text-[10px] text-[#C9C9CE]">—</span>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="mt-2 text-[11px] text-[#9A9BA3]">Jurnal penutup memindahkan Laba/Rugi Bersih ke akun Laba Ditahan (3-2000). Periode yang ditutup <b>terkunci penuh</b> — jurnal/koreksi mundur ditolak kecuali ada izin resmi di menu <b>Buka Periode (Unlock)</b>.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Labeled({ label, children }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</span>
      {children}
    </div>
  );
}

function MiniStat({ label, value, tone = "text-[#1C1C1E]" }) {
  return (
    <div className="rounded-md border border-[#EFF0F2] px-3 py-2 bg-white">
      <p className="text-[9px] font-bold uppercase tracking-wide text-[#9A9BA3]">{label}</p>
      <p className={`text-[13px] font-bold tabular-nums ${tone}`}>{value}</p>
    </div>
  );
}

function Kpi({ label, value, icon: Icon, tone = "", testId }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="w-9 h-9 rounded-lg bg-[#F3EAFB] flex items-center justify-center"><Icon size={17} className="text-[#6B219A]" /></div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
          <p className={`text-[17px] font-bold tabular-nums truncate ${tone || "text-[#1C1C1E]"}`} data-testid={`${testId}-value`}>{value}</p>
        </div>
      </div>
    </div>
  );
}
