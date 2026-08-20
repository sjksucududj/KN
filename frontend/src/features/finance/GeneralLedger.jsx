/**
 * GeneralLedger (EPIC7-C) — Jurnal Umum, Neraca Saldo, Buku Besar.
 * Akses admin/manager (permission "accounting"). Sumber: /api/gl/*.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, FileStack, Scale, BookOpen, Plus, RotateCcw, X, CheckCircle2, Boxes, ArrowLeftRight, Printer, Search,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import PaginationBar from "../../components/PaginationBar";
import { usePagedList } from "../../hooks/usePagedList";
import KNSelect from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";
import { printPaymentVoucher, printReceivedVoucher } from "../../utils/docPrint";
import JournalEntryModal from "./JournalEntryModal";
import InventoryReconTab from "./InventoryReconTab";
import SuspensePanel from "./SuspensePanel";
import { Kpi, BalancedKpi } from "./GeneralLedgerParts";

const SOURCE_META = {
  manual: { label: "Manual", tone: "bg-[#F3EAFB] text-[#6B219A]" },
  sales_order: { label: "Penjualan", tone: "bg-[#E6F6EC] text-[#1B7F4B]" },
  cash_transaction: { label: "Kas", tone: "bg-[#E7F0FF] text-[#0058CC]" },
};
const TABS = [
  { id: "journal", label: "Jurnal", icon: FileStack },
  { id: "trial", label: "Neraca Saldo", icon: Scale },
  { id: "ledger", label: "Buku Besar", icon: BookOpen },
  { id: "recon", label: "Rekonsiliasi Persediaan", icon: Boxes },
  { id: "suspense", label: "Suspense", icon: ArrowLeftRight },
];

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" }); }
  catch { return "—"; }
}

// FASE P6 — kolom Unduh CSV jurnal. Label "Sumber" & "Status" memakai kata yang SAMA
// dengan yang terbaca di tabel (bukan kode mentah `void`/`sales_order`), supaya berkasnya
// bisa dibaca orang yang tidak menghafal kode internal.
const JOURNAL_CSV_COLUMNS = [
  { key: "number", header: "No Jurnal" },
  { key: "date", header: "Tanggal", type: "date" },
  { header: "Sumber", get: (je) => SOURCE_META[je.source_type]?.label || je.source_type || "" },
  { key: "source_label", header: "Rujukan Sumber" },
  { key: "description", header: "Keterangan" },
  { key: "total_debit", header: "Nilai", type: "num" },
  { header: "Status", get: (je) => (je.status === "void" ? "Anulir" : "Posted") },
];

export default function GeneralLedger({ selectedEntity, entities = [] }) {
  const [tab, setTab] = useState("journal");
  const [summary, setSummary] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [notice, setNotice] = useState("");
  const [ledgerCode, setLedgerCode] = useState("");

  const loadMeta = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        axios.get(`${API}/gl/summary`),
        axios.get(`${API}/gl/accounts`),
      ]);
      setSummary(s.data || null);
      setAccounts(Array.isArray(a.data) ? a.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data GL.");
    }
  }, []);

  useEffect(() => { loadMeta(); }, [loadMeta]);

  const [refreshKey, setRefreshKey] = useState(0);
  const refreshAll = () => { setRefreshKey((k) => k + 1); loadMeta(); };

  const runSync = async () => {
    setSyncing(true); setError(""); setNotice("");
    try {
      const res = await axios.post(`${API}/gl/sync`);
      const r = res.data || {};
      setNotice(`Sinkron selesai: ${r.total || 0} jurnal baru (penjualan ${r.sales_orders || 0}, kas ${r.cash_transactions || 0}).`);
      refreshAll();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal sinkronisasi jurnal.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div data-testid="gl-view">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <Kpi testId="gl-kpi-count" label="Total Jurnal" value={summary?.journal_count ?? "—"} icon={FileStack} />
        <Kpi testId="gl-kpi-debit" label="Total Debit" value={formatCurrency(summary?.total_debit)} icon={Scale} tone="text-[#0058CC]" />
        <Kpi testId="gl-kpi-credit" label="Total Kredit" value={formatCurrency(summary?.total_credit)} icon={Scale} tone="text-[#1B7F4B]" />
        <BalancedKpi balanced={summary?.balanced} />
      </div>

      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-1.5 flex-wrap">
            {TABS.map((t) => (
              <button key={t.id} data-testid={`gl-tab-${t.id}`} onClick={() => setTab(t.id)}
                className={`inline-flex items-center gap-1.5 text-[12px] font-semibold rounded-lg px-3 py-1.5 border ${tab === t.id ? "bg-[#6B219A] text-white border-[#6B219A]" : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#D9C4EC]"}`}>
                <t.icon size={14} />{t.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            {tab === "journal" && (
              <>
                <button data-testid="gl-new-journal" className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={() => setShowModal(true)}><Plus size={14} /> Jurnal Baru</button>
                <button data-testid="gl-sync" className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={runSync} disabled={syncing}><RotateCcw size={13} className={syncing ? "animate-spin" : ""} /> Sinkronkan</button>
              </>
            )}
            <button data-testid="gl-refresh" className="icon-button" onClick={refreshAll} aria-label="Refresh"><RefreshCw size={14} /></button>
          </div>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={refreshAll} onDismiss={() => setError("")} testId="gl-error" />
          {notice && (
            <div data-testid="gl-notice" className="mb-3 rounded-md bg-[#E6F6EC] border border-[#BDE5CC] text-[#1B7F4B] text-[12px] px-3 py-2 flex items-center gap-2">
              <CheckCircle2 size={14} />{notice}
              <button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup"><X size={13} /></button>
            </div>
          )}

          {tab === "journal" && <JournalTab refreshKey={refreshKey} onChanged={refreshAll} onError={setError} entities={entities} selectedEntity={selectedEntity} />}
          {tab === "trial" && <TrialBalanceTab refreshKey={refreshKey} onError={setError} onDrill={(code) => { setTab("ledger"); setLedgerCode(code); }} />}
          {tab === "ledger" && <LedgerTab accounts={accounts} refreshKey={refreshKey} code={ledgerCode} setCode={setLedgerCode} onError={setError} />}
          {tab === "recon" && <InventoryReconTab refreshKey={refreshKey} onError={setError} onNotice={setNotice} onChanged={refreshAll} />}
          {tab === "suspense" && <SuspensePanel refreshKey={refreshKey} accounts={accounts} entities={entities} selectedEntity={selectedEntity} onNotice={setNotice} onChanged={refreshAll} />}
        </div>
      </div>

      {showModal && (
        <JournalEntryModal accounts={accounts} onClose={() => setShowModal(false)}
          onSaved={async () => { setShowModal(false); setNotice("Jurnal manual berhasil diposting."); refreshAll(); }} />
      )}
    </div>
  );
}

// ─── JURNAL TAB ──────────────────────────────────────────────────────────────
function JournalTab({ refreshKey, onChanged, onError, entities = [], selectedEntity }) {
  const [sourceFilter, setSourceFilter] = useState("");
  const [search, setSearch] = useState("");
  const [detail, setDetail] = useState(null);

  // P2 — jurnal dipaginasi di server. Sebelumnya daftarnya dipotong keras di 500 baris
  // TANPA halaman berikutnya, jadi entri ke-501 tidak bisa dijangkau dari layar sama
  // sekali — dan `journal_entries` justru koleksi yang tumbuh paling cepat (setiap
  // transaksi memposting entri).
  const params = useMemo(
    () => (sourceFilter ? { source: sourceFilter } : {}), [sourceFilter]);
  const paged = usePagedList("/gl/journal", { params, search, pageSize: 20 });
  const entries = paged.items;
  const loading = paged.loading;

  useEffect(() => { paged.refresh(); }, [refreshKey]); // eslint-disable-line
  useEffect(() => { if (paged.error) onError(paged.error); }, [paged.error]); // eslint-disable-line

  const voidEntry = async (je) => {
    try {
      await axios.post(`${API}/gl/journal/${je.id}/void`);
      setDetail(null);
      onChanged();
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal void jurnal.");
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <div className="w-[200px]">
          <KNSelect data-testid="gl-journal-source-filter" className="field py-1 text-[12px]" value={sourceFilter} onValueChange={setSourceFilter}
            placeholder="Semua sumber" options={[{ value: "", label: "Semua sumber" }, { value: "manual", label: "Manual" }, { value: "sales_order", label: "Penjualan" }, { value: "cash_transaction", label: "Kas" }]} />
        </div>
        <div className="flex min-w-[220px] flex-1 items-center gap-2 rounded-md border border-[#EFF0F2] bg-white px-2.5 py-1.5">
          <Search size={13} className="text-[#8E8E93]" />
          <input data-testid="gl-journal-search" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Cari nomor jurnal / keterangan…"
            className="flex-1 bg-transparent text-[12px] outline-none placeholder:text-[#9A9BA3]" />
          {search && (
            <button onClick={() => setSearch("")} aria-label="Kosongkan pencarian"
              className="text-[#8E8E93] hover:text-[#1C1C1E]"><X size={12} /></button>
          )}
        </div>
        <span className="text-[11px] text-[#9A9BA3] tabular-nums" data-testid="gl-journal-total">{paged.total} jurnal</span>
      </div>
      {loading ? (
        <div className="grid gap-2" data-testid="gl-journal-loading">{[0, 1, 2, 3].map((i) => <div key={i} className="h-10 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
      ) : entries.length === 0 ? (
        <div data-testid="gl-journal-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
          <FileStack size={26} className="mx-auto mb-2 text-gray-300" />
          {search.trim()
            ? `Tidak ada jurnal yang cocok dengan “${search.trim()}”.`
            : "Belum ada jurnal. Klik “Sinkronkan” untuk posting otomatis dari transaksi."}
        </div>
      ) : (
        <div className="overflow-auto rounded-md border border-[#EFF0F2]">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                <th className="px-3 py-2">No</th>
                <th className="px-3 py-2">Tanggal</th>
                <th className="px-3 py-2">Sumber</th>
                <th className="px-3 py-2">Keterangan</th>
                <th className="px-3 py-2 text-right">Nilai</th>
                <th className="px-3 py-2 text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((je) => {
                const sm = SOURCE_META[je.source_type] || { label: je.source_type, tone: "bg-gray-100 text-gray-600" };
                return (
                  <tr key={je.id} data-testid={`gl-journal-row-${je.id}`} onClick={() => setDetail(je)}
                    className="border-b border-[#F5F5F7] last:border-0 cursor-pointer hover:bg-[#FBF8FE]">
                    <td className="px-3 py-2 font-mono text-[11px] font-semibold text-[#3C3C43]">{je.number}</td>
                    <td className="px-3 py-2 text-[#3C3C43]">{fmtDate(je.date)}</td>
                    <td className="px-3 py-2"><span className={`text-[10px] font-bold rounded px-1.5 py-0.5 ${sm.tone}`}>{sm.label}</span>{je.source_label ? <span className="ml-1 text-[10px] text-[#9A9BA3]">{je.source_label}</span> : null}</td>
                    <td className="px-3 py-2 text-[#1C1C1E] max-w-[280px] truncate">{je.description}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-semibold">{formatCurrency(je.total_debit)}</td>
                    <td className="px-3 py-2 text-center">
                      {je.status === "void"
                        ? <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-[#FDEDE7] text-[#C0392B]">Anulir</span>
                        : <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-[#E6F6EC] text-[#1B7F4B]">Posted</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {/* P2 — kontrol halaman jurnal */}
      {!loading && entries.length > 0 && (
        <div className="mt-2">
          <PaginationBar
            page={paged.page} pageSize={paged.pageSize} total={paged.total}
            hasMore={paged.hasMore} loading={paged.loading}
            onPrev={paged.prev} onNext={paged.next} onPageSize={paged.setPageSize}
            testId="gl-journal-pager" label="jurnal"
            exportConfig={{ columns: JOURNAL_CSV_COLUMNS, rows: entries,
              fetchAll: paged.fetchAll, filename: "jurnal-umum" }}
          />
        </div>
      )}
      {detail && <JournalDetailModal je={detail} entities={entities} selectedEntity={selectedEntity} onClose={() => setDetail(null)} onVoid={voidEntry} />}
    </div>
  );
}

function JournalDetailModal({ je, entities = [], selectedEntity, onClose, onVoid }) {
  const sm = SOURCE_META[je.source_type] || { label: je.source_type, tone: "" };
  const entId = je.entity_id || (selectedEntity && selectedEntity !== "all" ? selectedEntity : "");
  const ent = entities.find((e) => e.id === entId);
  const entityName = ent?.short_name || ent?.legal_name || "";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="gl-journal-detail">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[#EFF0F2]">
          <FileStack size={16} className="text-[#6B219A]" />
          <h3 className="font-bold text-[14px]">Jurnal <span className="font-mono tabular-nums text-[#6B6B73]">{je.number}</span></h3>
          <span className={`text-[10px] font-bold rounded px-1.5 py-0.5 ${sm.tone}`}>{sm.label}</span>
          <button data-testid="gl-journal-detail-close" className="icon-button ml-auto" onClick={onClose} aria-label="Tutup"><X size={15} /></button>
        </div>
        <div className="p-4 overflow-auto">
          <div className="flex items-center justify-between text-[12px] text-[#6B6B73] mb-2">
            <span>{fmtDate(je.date)} · {je.description}</span>
            <span>oleh {je.created_by}</span>
          </div>
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
                {(je.lines || []).map((l, i) => (
                  <tr key={i} className="border-b border-[#F5F5F7] last:border-0">
                    <td className="px-3 py-2"><span className="font-mono text-[11px] text-[#9A9BA3]">{l.account_code}</span> {l.account_name}{l.description ? <span className="block text-[10px] text-[#9A9BA3]">{l.description}</span> : null}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{l.debit > 0 ? formatCurrency(l.debit) : "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{l.credit > 0 ? formatCurrency(l.credit) : "—"}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-[#FAFBFC] border-t border-[#EFF0F2] font-bold">
                  <td className="px-3 py-2 text-right text-[11px]">Total</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(je.total_debit)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(je.total_credit)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2]">
          <button data-testid="gl-print-payment-voucher" className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={() => printPaymentVoucher(je, entityName)}><Printer size={13} /> Payment Voucher</button>
          <button data-testid="gl-print-received-voucher" className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={() => printReceivedVoucher(je, entityName)}><Printer size={13} /> Received Voucher</button>
          {je.source_type === "manual" && je.status !== "void" && (
            <button data-testid="gl-journal-void" className="btn-secondary text-[12px] py-1.5 px-3 text-[#C0392B]" onClick={() => onVoid(je)}>Anulir Jurnal</button>
          )}
          <button className="btn-primary text-[12px] py-1.5 px-4" onClick={onClose}>Tutup</button>
        </div>
      </div>
    </div>
  );
}

// ─── NERACA SALDO TAB ────────────────────────────────────────────────────────
function TrialBalanceTab({ refreshKey, onError, onDrill }) {
  const [tb, setTb] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/gl/trial-balance`);
      setTb(res.data || null);
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal memuat neraca saldo.");
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (loading) return <div className="grid gap-2" data-testid="gl-trial-loading">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>;
  if (!tb || (tb.rows || []).length === 0) return <div data-testid="gl-trial-empty" className="py-12 text-center text-[12px] text-[#8E8E93]"><Scale size={26} className="mx-auto mb-2 text-gray-300" />Belum ada saldo. Posting jurnal terlebih dahulu.</div>;

  return (
    <div data-testid="gl-trial">
      <div className="overflow-auto rounded-md border border-[#EFF0F2]">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <th className="px-3 py-2">Kode</th>
              <th className="px-3 py-2">Nama Akun</th>
              <th className="px-3 py-2">Tipe</th>
              <th className="px-3 py-2 text-right">Debit</th>
              <th className="px-3 py-2 text-right">Kredit</th>
            </tr>
          </thead>
          <tbody>
            {tb.rows.map((r) => (
              <tr key={r.code} data-testid={`gl-trial-row-${r.code}`} onClick={() => onDrill(r.code)} className="border-b border-[#F5F5F7] last:border-0 cursor-pointer hover:bg-[#FBF8FE]">
                <td className="px-3 py-2 font-mono font-semibold text-[#3C3C43] tabular-nums">{r.code}</td>
                <td className="px-3 py-2 text-[#1C1C1E]">{r.name}</td>
                <td className="px-3 py-2 text-[10px] text-[#9A9BA3]">{r.type_label}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.debit_balance > 0 ? formatCurrency(r.debit_balance) : "—"}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.credit_balance > 0 ? formatCurrency(r.credit_balance) : "—"}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-[#FAFBFC] border-t-2 border-[#E4E4EA] font-bold">
              <td className="px-3 py-2.5" colSpan={3}>TOTAL {tb.balanced ? "✓ Seimbang" : "⚠ Tidak Seimbang"}</td>
              <td className="px-3 py-2.5 text-right tabular-nums" data-testid="gl-trial-total-debit">{formatCurrency(tb.total_debit)}</td>
              <td className="px-3 py-2.5 text-right tabular-nums" data-testid="gl-trial-total-credit">{formatCurrency(tb.total_credit)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-[#9A9BA3]">Klik baris akun untuk melihat Buku Besar (rincian mutasi).</p>
    </div>
  );
}

// ─── BUKU BESAR TAB ──────────────────────────────────────────────────────────
function LedgerTab({ accounts, refreshKey, code, setCode, onError }) {
  const [ledger, setLedger] = useState(null);
  const [loading, setLoading] = useState(false);

  const postableOptions = useMemo(
    () => accounts.filter((a) => a.is_postable).map((a) => ({ value: a.code, label: `${a.code} — ${a.name}` })),
    [accounts]);

  const load = useCallback(async (c) => {
    if (!c) { setLedger(null); return; }
    setLoading(true);
    try {
      const res = await axios.get(`${API}/gl/accounts/${c}/ledger`);
      setLedger(res.data || null);
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal memuat buku besar.");
      setLedger(null);
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => { if (code) load(code); }, [code, load, refreshKey]);

  return (
    <div data-testid="gl-ledger">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-[320px] max-w-full">
          <KNSelect data-testid="gl-ledger-account" className="field py-1.5 text-[12px]" value={code || ""} onValueChange={setCode}
            placeholder="Pilih akun untuk dilihat" options={postableOptions} searchable />
        </div>
        {ledger && <span className="ml-auto text-[12px] text-[#6B6B73]">Saldo akhir: <b className="tabular-nums">{formatCurrency(ledger.balance)}</b></span>}
      </div>

      {!code ? (
        <div data-testid="gl-ledger-prompt" className="py-12 text-center text-[12px] text-[#8E8E93]"><BookOpen size={26} className="mx-auto mb-2 text-gray-300" />Pilih akun untuk menampilkan buku besar.</div>
      ) : loading ? (
        <div className="grid gap-2" data-testid="gl-ledger-loading">{[0, 1, 2].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
      ) : !ledger || (ledger.lines || []).length === 0 ? (
        <div data-testid="gl-ledger-empty" className="py-10 text-center text-[12px] text-[#8E8E93]">Belum ada mutasi pada akun ini.</div>
      ) : (
        <div className="overflow-auto rounded-md border border-[#EFF0F2]">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                <th className="px-3 py-2">Tanggal</th>
                <th className="px-3 py-2">No / Keterangan</th>
                <th className="px-3 py-2 text-right">Debit</th>
                <th className="px-3 py-2 text-right">Kredit</th>
                <th className="px-3 py-2 text-right">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {ledger.lines.map((l, i) => (
                <tr key={`${l.entry_id}-${i}`} data-testid={`gl-ledger-row-${l.number}`} className="border-b border-[#F5F5F7] last:border-0">
                  <td className="px-3 py-2 text-[#3C3C43]">{fmtDate(l.date)}</td>
                  <td className="px-3 py-2"><span className="font-mono text-[10px] text-[#9A9BA3]">{l.number}</span><br />{l.description}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-[#1B7F4B]">{l.debit > 0 ? formatCurrency(l.debit) : "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-[#C0392B]">{l.credit > 0 ? formatCurrency(l.credit) : "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold">{formatCurrency(l.running_balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
