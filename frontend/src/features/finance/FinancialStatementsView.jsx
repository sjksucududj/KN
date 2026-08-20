/**
 * FinancialStatementsView (FINANCE) — Laporan Keuangan: Laba-Rugi & Neraca.
 * Diturunkan dari GL (journal_entries + gl_accounts). Akses admin/manager.
 * Sumber: /api/finance/income-statement, /api/finance/balance-sheet (+ export.csv).
 * Ikut gaya modul GL (section-card, #6B219A, KNSelect, formatCurrency, ErrorNotice).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, TrendingUp, Scale, Download, PiggyBank, Percent, ArrowUpRight,
  CheckCircle2, AlertTriangle, CalendarRange, CalendarDays, Building2, Wallet, Waves,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";
import { SectionBlock, SummaryRow, GroupHeader, BsSection, BsLine, BsTotalRow, Labeled, Kpi, BalancedKpi } from "./FinancialStatementsParts";
import CashFlowTab from "./CashFlowTab";
import EquityChangesTab from "./EquityChangesTab";

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

const pad = (n) => String(n).padStart(2, "0");
const lastDay = (y, m) => new Date(Number(y), Number(m), 0).getDate();
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const endOfPrevMonth = () => ymd(new Date(NOW.getFullYear(), NOW.getMonth(), 0));

function fmtDateID(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return iso; }
}

function fmtDelta(v) {
  const n = Number(v || 0);
  if (Math.abs(n) < 0.005) return formatCurrency(0);
  const body = formatCurrency(Math.abs(n));
  return n > 0 ? `+${body}` : `-${body}`;
}

const entityParam = (selectedEntity) =>
  selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {};

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

const TABS = [
  { id: "pl", label: "Laba-Rugi", icon: TrendingUp },
  { id: "bs", label: "Neraca", icon: Scale },
  { id: "cf", label: "Arus Kas", icon: Waves },
  { id: "eq", label: "Perubahan Ekuitas", icon: PiggyBank },
];

// ═════════════════════════════════════════════════════════════════════════════
//  ROOT
// ═════════════════════════════════════════════════════════════════════════════
export default function FinancialStatementsView({ selectedEntity }) {
  const [tab, setTab] = useState("pl");

  return (
    <div data-testid="financial-statements-view">
      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-1.5 flex-wrap">
            {TABS.map((t) => (
              <button key={t.id} data-testid={`fs-tab-${t.id}`} onClick={() => setTab(t.id)}
                className={`inline-flex items-center gap-1.5 text-[12px] font-semibold rounded-lg px-3 py-1.5 border transition-colors ${tab === t.id ? "bg-[#6B219A] text-white border-[#6B219A]" : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#D9C4EC]"}`}>
                <t.icon size={14} />{t.label}
              </button>
            ))}
          </div>
        </div>
        <div className="section-body">
          {tab === "pl" && <IncomeStatementTab selectedEntity={selectedEntity} />}
          {tab === "bs" && <BalanceSheetTab selectedEntity={selectedEntity} />}
          {tab === "cf" && <CashFlowTab selectedEntity={selectedEntity} />}
          {tab === "eq" && <EquityChangesTab selectedEntity={selectedEntity} />}
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
//  LABA-RUGI (Income Statement)
// ═════════════════════════════════════════════════════════════════════════════
function IncomeStatementTab({ selectedEntity }) {
  const [mode, setMode] = useState("range"); // range | period
  const [range, setRange] = useState({ start: `${NOW.getFullYear()}-01-01`, end: ymd(NOW) });
  const [period, setPeriod] = useState({
    type: "month", month: pad(NOW.getMonth() + 1), year: String(NOW.getFullYear()),
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const effRange = useMemo(() => {
    if (mode === "range") return { start: range.start, end: range.end };
    const y = period.year;
    if (period.type === "year") return { start: `${y}-01-01`, end: `${y}-12-31` };
    const m = period.month;
    return { start: `${y}-${m}-01`, end: `${y}-${m}-${pad(lastDay(y, m))}` };
  }, [mode, range, period]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { ...entityParam(selectedEntity) };
      if (effRange.start) params.start = effRange.start;
      if (effRange.end) params.end = effRange.end;
      const res = await axios.get(`${API}/finance/income-statement`, { params });
      setData(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Laba-Rugi.");
    } finally {
      setLoading(false);
    }
  }, [selectedEntity, effRange]);

  useEffect(() => { load(); }, [load]);

  const doExport = async () => {
    try {
      const res = await axios.get(`${API}/finance/income-statement/export.csv`, {
        params: { ...entityParam(selectedEntity), start: effRange.start, end: effRange.end },
        responseType: "blob",
      });
      saveBlob(res.data, `laba-rugi_${effRange.start || "awal"}_${effRange.end || "akhir"}.csv`);
    } catch (e) { setError("Gagal mengunduh CSV."); }
  };

  return (
    <div data-testid="fs-income-statement">
      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <Kpi testId="fs-pl-kpi-revenue" label="Pendapatan" value={formatCurrency(data?.revenue_total)} icon={TrendingUp} tone="text-[#1B7F4B]" />
        <Kpi testId="fs-pl-kpi-gross" label="Laba Kotor" value={formatCurrency(data?.gross_profit)} icon={ArrowUpRight} />
        <Kpi testId="fs-pl-kpi-net" label="Laba Bersih" value={formatCurrency(data?.net_income)} icon={PiggyBank} tone={(data?.net_income ?? 0) >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"} />
        <Kpi testId="fs-pl-kpi-margin" label="Marjin Bersih" value={`${Number(data?.net_margin ?? 0).toFixed(1)}%`} icon={Percent} tone={(data?.net_margin ?? 0) >= 0 ? "text-[#0058CC]" : "text-[#C0392B]"} />
      </div>

      {/* Filter */}
      <div className="rounded-lg border border-[#EFF0F2] p-3 mb-3 bg-[#FCFCFD]">
        <div className="flex items-center gap-1.5 mb-3">
          <button data-testid="fs-pl-mode-range" onClick={() => setMode("range")}
            className={`inline-flex items-center gap-1.5 text-[11px] font-semibold rounded-lg px-2.5 py-1.5 border ${mode === "range" ? "bg-[#F3EAFB] text-[#6B219A] border-[#D9C4EC]" : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#D9C4EC]"}`}>
            <CalendarRange size={13} /> Rentang Tanggal
          </button>
          <button data-testid="fs-pl-mode-period" onClick={() => setMode("period")}
            className={`inline-flex items-center gap-1.5 text-[11px] font-semibold rounded-lg px-2.5 py-1.5 border ${mode === "period" ? "bg-[#F3EAFB] text-[#6B219A] border-[#D9C4EC]" : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#D9C4EC]"}`}>
            <CalendarDays size={13} /> Periode (Bulan/Tahun)
          </button>
          <button data-testid="fs-pl-export" onClick={doExport}
            className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1 ml-auto">
            <Download size={13} /> Ekspor CSV
          </button>
        </div>

        {mode === "range" ? (
          <div className="flex flex-wrap items-end gap-3">
            <Labeled label="Dari Tanggal">
              <input type="date" data-testid="fs-pl-start" className="field py-1.5 text-[12px]" value={range.start}
                onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))} />
            </Labeled>
            <Labeled label="Sampai Tanggal">
              <input type="date" data-testid="fs-pl-end" className="field py-1.5 text-[12px]" value={range.end}
                onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))} />
            </Labeled>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <Labeled label="Tipe Periode">
              <div className="w-[140px]">
                <KNSelect data-testid="fs-pl-period-type" className="field py-1.5 text-[12px]" value={period.type}
                  onValueChange={(v) => setPeriod((p) => ({ ...p, type: v }))}
                  options={[{ value: "month", label: "Bulanan" }, { value: "year", label: "Tahunan" }]} />
              </div>
            </Labeled>
            {period.type === "month" && (
              <Labeled label="Bulan">
                <div className="w-[150px]">
                  <KNSelect data-testid="fs-pl-period-month" className="field py-1.5 text-[12px]" value={period.month}
                    onValueChange={(v) => setPeriod((p) => ({ ...p, month: v }))} options={MONTHS} />
                </div>
              </Labeled>
            )}
            <Labeled label="Tahun">
              <div className="w-[110px]">
                <KNSelect data-testid="fs-pl-period-year" className="field py-1.5 text-[12px]" value={period.year}
                  onValueChange={(v) => setPeriod((p) => ({ ...p, year: v }))} options={YEARS} />
              </div>
            </Labeled>
            <span className="text-[11px] text-[#9A9BA3] pb-1.5" data-testid="fs-pl-period-hint">
              {effRange.start} s/d {effRange.end}
            </span>
          </div>
        )}
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="fs-pl-error" />

      {loading ? (
        <div className="grid gap-2" data-testid="fs-pl-loading">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
      ) : !data ? null : (
        <div className="overflow-auto rounded-md border border-[#EFF0F2]" data-testid="fs-pl-table">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                <th className="px-3 py-2">Akun</th>
                <th className="px-3 py-2 text-right">Jumlah</th>
              </tr>
            </thead>
            <tbody>
              {(data.sections || []).map((sec) => (
                <SectionBlock key={sec.key} section={sec} />
              ))}
              <SummaryRow label="Laba Kotor" value={data.gross_profit} extra={`Marjin ${Number(data.gross_margin || 0).toFixed(1)}%`} />
              <SummaryRow label="Laba Bersih" value={data.net_income} extra={`Marjin ${Number(data.net_margin || 0).toFixed(1)}%`} highlight />
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[11px] text-[#9A9BA3]">Diturunkan dari jurnal (bukan anulir). Laba Bersih = Pendapatan − HPP − Beban Operasional.</p>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
//  NERACA (Balance Sheet)
// ═════════════════════════════════════════════════════════════════════════════
function BalanceSheetTab({ selectedEntity }) {
  const [asOf, setAsOf] = useState(ymd(NOW));
  const [comparative, setComparative] = useState(true);
  const [compareAsOf, setCompareAsOf] = useState(endOfPrevMonth());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { ...entityParam(selectedEntity) };
      if (asOf) params.as_of = asOf;
      if (comparative && compareAsOf) params.compare_as_of = compareAsOf;
      const res = await axios.get(`${API}/finance/balance-sheet`, { params });
      setData(res.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat Neraca.");
    } finally {
      setLoading(false);
    }
  }, [selectedEntity, asOf, comparative, compareAsOf]);

  useEffect(() => { load(); }, [load]);

  const doExport = async () => {
    try {
      const res = await axios.get(`${API}/finance/balance-sheet/export.csv`, {
        params: { ...entityParam(selectedEntity), as_of: asOf, ...(comparative && compareAsOf ? { compare_as_of: compareAsOf } : {}) },
        responseType: "blob",
      });
      saveBlob(res.data, `neraca_${asOf}.csv`);
    } catch (e) { setError("Gagal mengunduh CSV."); }
  };

  const isComp = data?.comparative;
  const cmp = data?.compare || {};

  return (
    <div data-testid="fs-balance-sheet">
      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <Kpi testId="fs-bs-kpi-assets" label="Total Aset" value={formatCurrency(data?.assets_total)} icon={Building2} tone="text-[#0058CC]" />
        <Kpi testId="fs-bs-kpi-liab" label="Total Kewajiban" value={formatCurrency(data?.liabilities_total)} icon={Wallet} tone="text-[#C0392B]" />
        <Kpi testId="fs-bs-kpi-equity" label="Total Ekuitas" value={formatCurrency(data?.equity_total)} icon={PiggyBank} tone="text-[#1B7F4B]" />
        <BalancedKpi balanced={data?.balanced} />
      </div>

      {/* Filter */}
      <div className="rounded-lg border border-[#EFF0F2] p-3 mb-3 bg-[#FCFCFD]">
        <div className="flex flex-wrap items-end gap-3">
          <Labeled label="Posisi Per Tanggal">
            <input type="date" data-testid="fs-bs-asof" className="field py-1.5 text-[12px]" value={asOf}
              onChange={(e) => setAsOf(e.target.value)} />
          </Labeled>
          <label className="flex items-center gap-2 text-[12px] text-[#3C3C43] pb-1.5 cursor-pointer select-none" data-testid="fs-bs-compare-toggle">
            <input type="checkbox" className="accent-[#6B219A] w-4 h-4" checked={comparative}
              onChange={(e) => setComparative(e.target.checked)} />
            Bandingkan periode
          </label>
          {comparative && (
            <Labeled label="Pembanding Per Tanggal">
              <input type="date" data-testid="fs-bs-compare-asof" className="field py-1.5 text-[12px]" value={compareAsOf}
                onChange={(e) => setCompareAsOf(e.target.value)} />
            </Labeled>
          )}
          <div className="ml-auto flex items-center gap-2">
            <button data-testid="fs-bs-export" onClick={doExport}
              className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1">
              <Download size={13} /> Ekspor CSV
            </button>
            <button data-testid="fs-bs-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="fs-bs-error" />

      {loading ? (
        <div className="grid gap-2" data-testid="fs-bs-loading">{[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
      ) : !data ? null : (
        <div className="overflow-auto rounded-md border border-[#EFF0F2]" data-testid="fs-bs-table">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                <th className="px-3 py-2">Akun</th>
                <th className="px-3 py-2 text-right">{fmtDateID(asOf)}</th>
                {isComp && <th className="px-3 py-2 text-right">{fmtDateID(compareAsOf)}</th>}
                {isComp && <th className="px-3 py-2 text-right">Δ Perubahan</th>}
              </tr>
            </thead>
            <tbody>
              {/* ASET */}
              <GroupHeader label="ASET" isComp={isComp} />
              {(data.assets?.sections || []).map((sec) => (
                <BsSection key={`a-${sec.key}`} section={sec} isComp={isComp} />
              ))}
              <BsTotalRow label="TOTAL ASET" value={data.assets_total} compare={cmp.assets_total} isComp={isComp} testId="fs-bs-total-assets" />

              {/* KEWAJIBAN */}
              <GroupHeader label="KEWAJIBAN" isComp={isComp} />
              {(data.liabilities?.sections || []).length === 0 && (
                <tr className="border-b border-[#F5F5F7]"><td className="px-3 py-1.5 pl-6 text-[11px] text-[#9A9BA3]" colSpan={isComp ? 4 : 2}>Tidak ada kewajiban.</td></tr>
              )}
              {(data.liabilities?.sections || []).map((sec) => (
                <BsSection key={`l-${sec.key}`} section={sec} isComp={isComp} />
              ))}
              <BsTotalRow label="TOTAL KEWAJIBAN" value={data.liabilities_total} compare={cmp.liabilities_total} isComp={isComp} testId="fs-bs-total-liab" />

              {/* EKUITAS */}
              <GroupHeader label="EKUITAS" isComp={isComp} />
              {(data.equity?.lines || []).map((ln) => (
                <BsLine key={`e-${ln.code}`} line={ln} isComp={isComp} />
              ))}
              <BsLine isComp={isComp} line={{
                code: "", name: "Laba Tahun Berjalan",
                amount: data.equity?.current_earnings,
                compare_amount: data.equity?.compare_current_earnings,
                delta: (data.equity?.current_earnings ?? 0) - (data.equity?.compare_current_earnings ?? 0),
              }} />
              <BsTotalRow label="TOTAL EKUITAS" value={data.equity_total} compare={cmp.equity_total} isComp={isComp} testId="fs-bs-total-equity" />

              {/* GRAND TOTAL */}
              <tr className={`border-t-2 border-[#E4E4EA] ${data.balanced ? "bg-[#F3EAFB]" : "bg-[#FDEDE7]"}`}>
                <td className="px-3 py-2.5 font-bold text-[#1C1C1E]">
                  TOTAL KEWAJIBAN + EKUITAS {data.balanced ? "✓" : "⚠"}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums font-bold text-[#6B219A]" data-testid="fs-bs-total-liab-equity">{formatCurrency(data.liabilities_equity_total)}</td>
                {isComp && <td className="px-3 py-2.5 text-right tabular-nums font-bold text-[#6B6B73]">{formatCurrency(cmp.liabilities_equity_total)}</td>}
                {isComp && <td className="px-3 py-2.5 text-right tabular-nums font-bold text-[#6B6B73]">{fmtDelta((data.liabilities_equity_total ?? 0) - (cmp.liabilities_equity_total ?? 0))}</td>}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[11px] text-[#9A9BA3]">Ekuitas termasuk Laba Tahun Berjalan (akumulatif) sehingga Aset = Kewajiban + Ekuitas.</p>
    </div>
  );
}
