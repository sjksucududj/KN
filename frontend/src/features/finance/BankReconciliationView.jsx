/**
 * FASE G-8 — BankReconciliationView: Rekonsiliasi Bank (parser multi-bank, skor
 * berbobot, split 1:N & N:1, aturan pembelajaran, titipan dana belum teridentifikasi).
 *
 * Akses: izin `cash` (admin/manager). Sumber data: /api/bank-reconciliation/*.
 * Layar ini TIDAK mengubah jurnal terposting; satu-satunya jalur yang menerbitkan
 * jurnal baru adalah TITIPAN DANA & alokasinya (karena di situ ada uang nyata).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, Landmark, Wand2, Upload, CheckCircle2, AlertTriangle, PiggyBank,
  Sparkles, FileCog, ListChecks, FilterX,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { apiErrorText } from "../../utils/apiError";
import { KNSelect } from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";
import ReconImportPanel from "./bank/ReconImportPanel";
import ReconLinesTable from "./bank/ReconLinesTable";
import ReconMatchModal from "./bank/ReconMatchModal";
import ReconHoldingPanel from "./bank/ReconHoldingPanel";
import ReconRulesPanel from "./bank/ReconRulesPanel";
import ReconFormatsPanel from "./bank/ReconFormatsPanel";

const TABS = [
  { id: "lines", label: "Mutasi & Pencocokan", icon: ListChecks },
  { id: "holding", label: "Dana Titipan", icon: PiggyBank },
  { id: "rules", label: "Aturan Pembelajaran", icon: Sparkles },
  { id: "formats", label: "Template Bank", icon: FileCog },
];

// Status baris mutasi (SSOT status ada di backend: unmatched|matched|ignored|holding).
const STATUS_FILTERS = [
  { value: "", label: "Semua status" },
  { value: "unmatched", label: "Perlu keputusan" },
  { value: "matched", label: "Tercocok" },
  { value: "holding", label: "Dititipkan" },
  { value: "ignored", label: "Diabaikan" },
];

export default function BankReconciliationView() {
  const [accounts, setAccounts] = useState([]);
  const [acctId, setAcctId] = useState("");
  const [tab, setTab] = useState("lines");
  const [lines, setLines] = useState([]);
  const [summary, setSummary] = useState(null);
  const [holding, setHolding] = useState(null);
  const [rules, setRules] = useState([]);
  const [formats, setFormats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [matchFor, setMatchFor] = useState(null);
  // Penutupan FASE G-8 — rekening koran nyata bisa ratusan baris per bulan. Backend sudah
  // menerima filter status & periode sejak awal, tetapi layar belum memakainya sehingga
  // pengguna harus memindai semuanya dengan mata. Filter ini juga dipakai ringkasan supaya
  // angka kartu selalu bercerita tentang periode yang sedang dilihat.
  const [fStatus, setFStatus] = useState("");
  const [fStart, setFStart] = useState("");
  const [fEnd, setFEnd] = useState("");

  const notify = (m) => { setMsg(m); setTimeout(() => setMsg(""), 5000); };
  // KN-G9-ERR-SILENT — semua penolakan backend dinormalkan ke KALIMAT sebelum
  // ditampilkan, supaya tidak ada objek axios mentah yang masuk ke <ErrorNotice>.
  const fail = (e) => setErr(apiErrorText(e));

  const loadAccounts = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/bank-accounts`);
      const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
      setAccounts(list);
      setAcctId((cur) => cur || (list[0]?.id ?? ""));
    } catch (e) { fail(e); }
  }, []);

  const loadData = useCallback(async () => {
    if (!acctId) return;
    setLoading(true); setErr("");
    try {
      const period = { ...(fStart ? { start: fStart } : {}), ...(fEnd ? { end: fEnd } : {}) };
      const [ln, sm, hd, rl, fm] = await Promise.all([
        axios.get(`${API}/bank-reconciliation/lines`,
          { params: { bank_account_id: acctId, ...period,
            ...(fStatus ? { status: fStatus } : {}) } }),
        axios.get(`${API}/bank-reconciliation/summary`,
          { params: { bank_account_id: acctId, ...period } }),
        axios.get(`${API}/bank-reconciliation/holding`, { params: { bank_account_id: acctId } }),
        axios.get(`${API}/bank-reconciliation/rules`, { params: { bank_account_id: acctId } }),
        axios.get(`${API}/bank-reconciliation/formats`),
      ]);
      setLines(Array.isArray(ln.data) ? ln.data : []);
      setSummary(sm.data);
      setHolding(hd.data);
      setRules(Array.isArray(rl.data) ? rl.data : []);
      setFormats(Array.isArray(fm.data) ? fm.data : []);
    } catch (e) { fail(e); }
    finally { setLoading(false); }
  }, [acctId, fStatus, fStart, fEnd]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);
  useEffect(() => { loadData(); }, [loadData]);

  async function doAutoMatch() {
    setBusy("auto"); setErr("");
    try {
      const r = await axios.post(`${API}/bank-reconciliation/auto-match`,
        { bank_account_id: acctId });
      const d = r.data || {};
      notify(`Pencocokan otomatis: ${d.matched} tertaut (skor ≥ ${d.auto_min}), `
        + `${d.suggested} usulan (skor ≥ ${d.suggest_min}), ${d.unmatched_lines} baris tersisa.`);
      await loadData();
    } catch (e) { fail(e); } finally { setBusy(""); }
  }

  async function lineAction(lineId, action, body, successMsg) {
    setBusy(lineId + action); setErr("");
    try {
      await axios.post(`${API}/bank-reconciliation/lines/${lineId}/${action}`, body || {});
      notify(successMsg || "Perubahan tersimpan.");
      setMatchFor(null);
      await loadData();
      return true;
    } catch (e) { fail(e); return false; } finally { setBusy(""); }
  }

  const suggestedRules = useMemo(
    () => rules.filter((r) => r.status === "suggested").length, [rules]);
  const acctOptions = useMemo(
    () => accounts.map((a) => ({ value: a.id, label: a.name || a.bank_name || a.id })),
    [accounts]);
  const filterOn = !!(fStatus || fStart || fEnd);

  return (
    <div className="p-5" data-testid="bank-reconciliation-view">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <h2 className="text-[17px] font-bold text-[#1C1C1E] flex items-center gap-2">
            <Landmark size={18} className="text-[#0058CC]" /> Rekonsiliasi Bank
          </h2>
          <p className="text-[12px] text-[#6B6B73]">
            Baca mutasi rekening koran bank apa pun, cocokkan dengan transaksi kas (buku),
            dan tampung dana yang belum teridentifikasi tanpa mengubah jurnal.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="min-w-[220px]">
            <KNSelect data-testid="recon-account-select" value={acctId}
              onValueChange={setAcctId} options={acctOptions} placeholder="Pilih akun bank" />
          </div>
          <button data-testid="recon-refresh" className="secondary-button" onClick={loadData}>
            <RefreshCw size={14} className={loading ? "spin" : ""} /> Muat ulang
          </button>
        </div>
      </div>

      {err && <ErrorNotice message={err} onRetry={loadData} onDismiss={() => setErr("")}
        testId="recon-error" />}
      {msg && (
        <div className="notice-bar success mb-3" data-testid="recon-notice">
          <CheckCircle2 size={14} /> {msg}
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-4" data-testid="recon-summary">
          <div className="stat-card">
            <p className="stat-label">Rekening (bersih)</p>
            <p className="stat-value tabular-nums">{formatCurrency(summary.statement.net)}</p>
            <p className="text-[10px] text-[#8E8E93]">{summary.statement.lines} baris mutasi</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Buku (bersih)</p>
            <p className="stat-value tabular-nums">{formatCurrency(summary.book.net)}</p>
            <p className="text-[10px] text-[#8E8E93]">
              {summary.unmatched_book_txns} transaksi belum tertaut
            </p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Tercocok</p>
            <p className="stat-value text-[#1B7F4B]" data-testid="recon-matched">{summary.matched}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Perlu keputusan</p>
            <p className="stat-value text-[#B26A00]" data-testid="recon-unmatched">
              {summary.unmatched_lines}
            </p>
            <p className="text-[10px] text-[#8E8E93]">{summary.suggested} punya usulan</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Dana titipan</p>
            <p className="stat-value text-[#0058CC]" data-testid="recon-holding-balance">
              {formatCurrency(summary.holding?.balance || 0)}
            </p>
            <p className="text-[10px] text-[#8E8E93]">
              {summary.holding?.count || 0} baris
              {summary.holding?.needs_action ? ` · ${summary.holding.needs_action} perlu tindakan` : ""}
            </p>
          </div>
          <div className={`stat-card ${Math.abs(summary.difference) < 0.5 ? "" : "ring-1 ring-[#F3C9C7]"}`}>
            <p className="stat-label">Selisih rekening vs buku</p>
            <p className={`stat-value ${Math.abs(summary.difference) < 0.5 ? "text-[#1B7F4B]" : "text-[#C0392B]"}`}
              data-testid="recon-difference">{formatCurrency(summary.difference)}</p>
            {summary.fully_reconciled && (
              <p className="text-[10px] text-[#1B7F4B] font-semibold">Terekonsiliasi penuh ✓</p>
            )}
          </div>
        </div>
      )}

      <div className="flex items-center gap-1 border-b border-[#E5E5EA] mb-3 flex-wrap">
        {TABS.map((t) => {
          const Icon = t.icon;
          const badge = t.id === "rules" && suggestedRules ? suggestedRules
            : t.id === "holding" && holding?.needs_action ? holding.needs_action : 0;
          return (
            <button key={t.id} data-testid={`recon-tab-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`px-3 py-2 text-[12px] font-semibold flex items-center gap-1.5 border-b-2 -mb-px ${
                tab === t.id
                  ? "border-[#0058CC] text-[#0058CC]"
                  : "border-transparent text-[#6B6B73] hover:text-[#1C1C1E]"}`}>
              <Icon size={14} /> {t.label}
              {badge ? (
                <span className="ml-1 rounded-full bg-[#FFF4E5] text-[#B26A00] px-1.5 text-[10px] font-bold">
                  {badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {tab === "lines" && (
        <>
          <div className="flex items-center gap-2 flex-wrap mb-3">
            <button data-testid="recon-import-toggle" className="secondary-button"
              onClick={() => setShowImport((v) => !v)}>
              <Upload size={14} /> {showImport ? "Tutup panel impor" : "Impor mutasi bank"}
            </button>
            <button data-testid="recon-auto-match" className="primary-button"
              disabled={busy === "auto" || !acctId} onClick={doAutoMatch}>
              {busy === "auto" ? <RefreshCw size={14} className="spin" /> : <Wand2 size={14} />}
              Cocokkan otomatis
            </button>
            <span className="text-[11px] text-[#8E8E93]">
              Ambang & bobot skor diatur di Pengaturan → Rekonsiliasi Bank (tanpa perlu rilis baru).
            </span>
          </div>

          <div className="mb-3 flex flex-wrap items-end gap-3 rounded-lg border border-[#E5E5EA] bg-[#FAFBFC] px-3 py-2"
            data-testid="recon-filter-bar">
            <div className="min-w-[190px]">
              <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                Tampilkan status
              </label>
              <KNSelect data-testid="recon-filter-status" value={fStatus}
                onValueChange={setFStatus} options={STATUS_FILTERS} />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                Mutasi dari tanggal
              </label>
              <input data-testid="recon-filter-start" type="date" className="input-field"
                value={fStart} onChange={(e) => setFStart(e.target.value)} />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                sampai tanggal
              </label>
              <input data-testid="recon-filter-end" type="date" className="input-field"
                value={fEnd} onChange={(e) => setFEnd(e.target.value)} />
            </div>
            {filterOn && (
              <button data-testid="recon-filter-clear" className="secondary-button"
                onClick={() => { setFStatus(""); setFStart(""); setFEnd(""); }}>
                <FilterX size={14} /> Bersihkan filter
              </button>
            )}
            <span className="text-[11px] text-[#6B6B73]" data-testid="recon-filter-count">
              {loading ? "Memuat…" : `${lines.length} baris ditampilkan`}
              {filterOn ? " · kartu ringkasan mengikuti periode yang dipilih" : ""}
            </span>
          </div>

          {showImport && (
            <ReconImportPanel accountId={acctId} formats={formats}
              onDone={async (info) => { setShowImport(false); notify(info); await loadData(); }}
              onError={fail} />
          )}

          <ReconLinesTable lines={lines} busy={busy} onAction={lineAction}
            onOpenMatch={(l) => setMatchFor(l)} onReload={loadData} onError={fail}
            onNotify={notify} />
        </>
      )}

      {tab === "holding" && (
        <ReconHoldingPanel holding={holding} busy={busy}
          onAction={lineAction} onReload={loadData} onError={fail} onNotify={notify} />
      )}

      {tab === "rules" && (
        <ReconRulesPanel rules={rules} onReload={loadData} onError={fail} onNotify={notify} />
      )}

      {tab === "formats" && (
        <ReconFormatsPanel formats={formats} onReload={loadData} onError={fail}
          onNotify={notify} />
      )}

      {matchFor && (
        <ReconMatchModal line={matchFor} onClose={() => setMatchFor(null)}
          onDone={async (m) => { setMatchFor(null); notify(m); await loadData(); }}
          onError={fail} />
      )}

      <p className="mt-3 text-[11px] text-[#9A9BA3] flex items-center gap-1">
        <AlertTriangle size={11} /> Pencocokan bersifat tambah-saja: ia hanya menautkan mutasi ke
        transaksi kas. Jurnal baru terbit hanya pada tiga jalur berlabel: dana dititipkan
        (Dr Bank / Cr Titipan), titipan dialokasikan (Dr Titipan / Cr Piutang), dan biaya ·
        bunga bank yang dibukukan langsung dari layar ini (Dr Beban Adm Bank / Cr Bank atau
        sebaliknya untuk bunga).
      </p>
    </div>
  );
}
