/**
 * GroupConsolidationView (FINANCE) — Konsolidasi Grup + Eliminasi Intercompany.
 * Matriks Per-PT + Eliminasi + Konsolidasi untuk Laba-Rugi (tahun) & Neraca (as_of).
 * Eliminasi manual + auto-deteksi kandidat intercompany.
 * Sumber: /api/finance/consolidation/*. Gaya ikut finance existing.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, Building2, Scale, TrendingUp, Layers, Plus, Trash2, X, Wand2,
  CheckCircle2, AlertTriangle, ScissorsLineDashed, ArrowRightLeft, Link2,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";
import { askReason } from "@/services/confirmService";

const NOW = new Date();
const YEARS = Array.from({ length: 6 }, (_, i) => {
  const y = String(NOW.getFullYear() - i);
  return { value: y, label: y };
});
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const PNL_ROWS = [
  { key: "revenue", label: "Pendapatan" },
  { key: "cogs", label: "HPP" },
  { key: "opex", label: "Beban Operasional" },
  { key: "expense", label: "Total Beban", muted: true },
  { key: "gross_profit", label: "Laba Kotor", strong: true },
  { key: "net_income", label: "Laba Bersih", strong: true },
];
const BS_ROWS = [
  { key: "assets", label: "Total Aset", strong: true },
  { key: "liabilities", label: "Total Kewajiban" },
  { key: "equity", label: "Total Ekuitas" },
];

const TABS = [
  { id: "pnl", label: "Laba-Rugi", icon: TrendingUp },
  { id: "bs", label: "Neraca", icon: Scale },
  { id: "elim", label: "Eliminasi", icon: ScissorsLineDashed },
];

export default function GroupConsolidationView({ entities = [] }) {
  const [tab, setTab] = useState("pnl");
  const [year, setYear] = useState(String(NOW.getFullYear()));
  const [asOf, setAsOf] = useState(ymd(NOW));
  const [data, setData] = useState(null);
  const [elims, setElims] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState(null); // {lines?, name?}
  const [detect, setDetect] = useState(null); // ic-candidates result
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [s, e] = await Promise.all([
        axios.get(`${API}/finance/consolidation/summary`, { params: { year, as_of: asOf } }),
        axios.get(`${API}/finance/consolidation/eliminations`),
      ]);
      setData(s.data); setElims(Array.isArray(e.data) ? e.data : []);
    } catch (err) {
      setError(err.response?.data?.detail || "Gagal memuat konsolidasi.");
    } finally { setLoading(false); }
  }, [year, asOf]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    axios.get(`${API}/gl/accounts`).then((r) => {
      const opts = (r.data || [])
        .filter((a) => !/-0000$/.test(a.code) && !/-\d000$/.test(a.code))
        .map((a) => ({ value: a.code, label: `${a.code} — ${a.name}` }));
      setAccounts(opts);
    }).catch(() => {});
  }, []);

  const removeElim = async (el) => {
    // Berdampak UANG (laporan konsolidasi grup) → alasan wajib & ikut tercatat di audit.
    const reason = await askReason({
      title: `Hapus entri eliminasi "${el.name}"?`,
      message: "Laporan konsolidasi grup akan berubah karena pasangan transaksi ini tidak "
        + "lagi dieliminasi.",
      reasonLabel: "Alasan penghapusan",
      confirmLabel: "Hapus Eliminasi",
      danger: true,
      testId: "elim-delete-confirm",
    });
    if (reason === null) return;
    setBusy(true); setError("");
    try { await axios.delete(`${API}/finance/consolidation/eliminations/${el.id}`, { params: { reason } }); setNotice("Eliminasi dihapus."); load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menghapus eliminasi."); }
    finally { setBusy(false); }
  };

  const runDetect = async () => {
    setBusy(true); setError("");
    try {
      const r = await axios.get(`${API}/finance/consolidation/ic-candidates`, { params: { as_of: asOf } });
      setDetect(r.data);
    } catch (e) { setError(e.response?.data?.detail || "Gagal mendeteksi kandidat."); }
    finally { setBusy(false); }
  };

  /**
   * FASE G-6 (US7) — sinkronkan eliminasi transaksi antar-PT.
   *
   * Eliminasi ini SUDAH dijaga otomatis setiap transaksi antar-PT dikonfirmasi /
   * dilunasi / dibatalkan. Tombol ini untuk **data lama (backfill)** dan untuk
   * memastikan angkanya masih pas — laporan ini kehilangan artinya kalau margin
   * antar-PT masih ikut terhitung sebagai laba grup.
   */
  const syncG6 = async () => {
    setBusy(true); setError(""); setNotice("");
    try {
      const r = await axios.post(`${API}/consolidation/sync-g6`, {}, { params: { as_of: asOf } });
      const d = r.data || {};
      setNotice(
        `Eliminasi antar-PT (G-6) tersinkron: ${d.created || 0} baru · ` +
        `${d.updated || 0} diperbarui · ${d.removed || 0} dihapus · ` +
        `${d.skipped_existing || 0} sudah pas — dari ${d.pairs_seen || 0} transaksi antar-PT.`);
      load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyinkronkan eliminasi antar-PT (G-6).");
    } finally { setBusy(false); }
  };

  /** M-3 — eliminasi dari PASANGAN jurnal transfer antar-PT lama (at-cost). */
  const syncPairs = async () => {
    setBusy(true); setError(""); setNotice("");
    try {
      const r = await axios.post(`${API}/finance/consolidation/eliminations/sync-from-pairs`,
                                 {}, { params: { as_of: asOf } });
      const d = r.data || {};
      setNotice(
        `Eliminasi pasangan jurnal (M-3): ${d.created || 0} baru · ` +
        `${d.skipped_existing || 0} sudah ada — dari ${d.pairs_seen || 0} pasangan.`);
      load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyinkronkan eliminasi pasangan jurnal.");
    } finally { setBusy(false); }
  };

  const useCandidatesAsDraft = () => {
    const lines = (detect?.suggested_lines || []).map((l) => ({
      account_code: l.account_code, debit: l.debit || 0, credit: l.credit || 0, description: l.description || "",
    }));
    setDetect(null);
    setModal({ name: "Eliminasi Intercompany (Auto)", lines: lines.length ? lines : undefined });
  };

  const entityCols = data?.entities || [];
  const colClass = "px-3 py-2 text-right tabular-nums whitespace-nowrap";

  const renderMatrix = (rows) => (
    <div className="overflow-x-auto rounded-md border border-[#EFF0F2]" data-testid={`cons-matrix-${tab}`}>
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
            <th className="px-3 py-2 sticky left-0 bg-[#FAFBFC]">Pos</th>
            {entityCols.map((e) => <th key={e.entity_id} className="px-3 py-2 text-right whitespace-nowrap">{e.short_name}</th>)}
            <th className="px-3 py-2 text-right whitespace-nowrap text-[#C0392B]">Eliminasi</th>
            <th className="px-3 py-2 text-right whitespace-nowrap text-[#6B219A]">Konsolidasi</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const elimV = data?.elimination?.[row.key] ?? 0;
            const consV = data?.consolidated?.[row.key] ?? 0;
            return (
              <tr key={row.key} data-testid={`cons-row-${row.key}`} className={`border-b border-[#F5F5F7] ${row.strong ? "bg-[#FAF6FE] font-bold" : row.muted ? "bg-[#FCFCFD]" : ""}`}>
                <td className={`px-3 py-2 sticky left-0 ${row.strong ? "bg-[#FAF6FE] font-bold" : "bg-white"} text-[#1C1C1E]`}>{row.label}</td>
                {entityCols.map((e) => <td key={e.entity_id} className={`${colClass} text-[#3C3C43] tabular-nums`}>{formatCurrency(e[row.key])}</td>)}
                <td className={`${colClass} tabular-nums ${Math.abs(elimV) > 0.005 ? "text-[#C0392B]" : "text-[#C9C9CE]"}`} data-testid={`cons-elim-${row.key}`}>{formatCurrency(elimV)}</td>
                <td className={`${colClass} font-bold text-[#6B219A] tabular-nums`} data-testid={`cons-consolidated-${row.key}`}>{formatCurrency(consV)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  return (
    <div data-testid="group-consolidation-view">
      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-1.5 flex-wrap">
            {TABS.map((t) => (
              <button key={t.id} data-testid={`cons-tab-${t.id}`} onClick={() => setTab(t.id)}
                className={`inline-flex items-center gap-1.5 text-[12px] font-semibold rounded-lg px-3 py-1.5 border transition-colors ${tab === t.id ? "bg-[#6B219A] text-white border-[#6B219A]" : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#D9C4EC]"}`}>
                <t.icon size={14} />{t.label}{t.id === "elim" && elims.length ? ` (${elims.length})` : ""}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            {tab === "pnl" && <div className="w-[110px]"><KNSelect data-testid="cons-year" className="field py-1.5 text-[12px]" value={year} onValueChange={setYear} options={YEARS} /></div>}
            {tab !== "pnl" && <input type="date" data-testid="cons-asof" className="field py-1.5 text-[12px] w-[150px]" value={asOf} onChange={(e) => setAsOf(e.target.value)} />}
            <button data-testid="cons-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>

        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="cons-error" />
          {notice && (
            <div data-testid="cons-notice" className="mb-3 rounded-md bg-[#E6F6EC] border border-[#BDE5CC] text-[#1B7F4B] text-[12px] px-3 py-2 flex items-center gap-2">
              <CheckCircle2 size={14} />{notice}<button className="ml-auto" onClick={() => setNotice("")}><X size={13} /></button>
            </div>
          )}

          {loading ? (
            <div className="h-64 bg-[#F5F5F7] rounded animate-pulse" data-testid="cons-loading" />
          ) : tab === "pnl" ? (
            <>
              <div className="flex items-center gap-2 mb-2 text-[11px] text-[#8E8E93]"><Layers size={13} className="text-[#6B219A]" /> Laba-Rugi Konsolidasi Tahun {year} — {entityCols.length} entitas</div>
              {renderMatrix(PNL_ROWS)}
            </>
          ) : tab === "bs" ? (
            <>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-[11px] text-[#8E8E93]"><Building2 size={13} className="text-[#6B219A]" /> Neraca Konsolidasi per {asOf}</div>
                <span data-testid="cons-balanced" className={`text-[11px] font-bold rounded-full px-2 py-0.5 inline-flex items-center gap-1 ${data?.balanced ? "bg-[#E6F6EC] text-[#1B7F4B]" : "bg-[#FDEDE7] text-[#C0392B]"}`}>
                  {data?.balanced ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}{data?.balanced ? "Seimbang" : "Tidak Seimbang"}
                </span>
              </div>
              {renderMatrix(BS_ROWS)}
            </>
          ) : (
            <EliminationsPanel elims={elims} onAdd={() => setModal({})} onDetect={runDetect}
                               onDelete={removeElim} onSyncG6={syncG6} onSyncPairs={syncPairs} busy={busy} />
          )}
          <p className="mt-2 text-[11px] text-[#9A9BA3]">Konsolidasi = Σ Per-PT + Eliminasi. Eliminasi bersifat adjustment grup (tidak mengubah jurnal per-PT). Neraca konsolidasi tetap seimbang bila entri eliminasi balanced.</p>
        </div>
      </div>

      {modal && (
        <EliminationModal initial={modal} accounts={accounts} entities={entities}
          onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); setNotice("Eliminasi tersimpan."); }} setError={setError} />
      )}
      {detect && (
        <DetectModal detect={detect} onClose={() => setDetect(null)} onUse={useCandidatesAsDraft} />
      )}
    </div>
  );
}

function EliminationsPanel({ elims, onAdd, onDetect, onDelete, onSyncG6, onSyncPairs, busy }) {
  const autoG6 = elims.filter((e) => e.source_g6_pair_id).length;
  return (
    <div data-testid="cons-elim-panel">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <h4 className="text-[12px] font-bold text-[#1C1C1E]">Entri Eliminasi Intercompany</h4>
        {autoG6 > 0 && (
          <span data-testid="cons-elim-g6-count"
                className="text-[10px] font-bold rounded-full px-1.5 py-0.5 bg-[#EDE7FB] text-[#6B219A]">
            {autoG6} otomatis dari transaksi antar-PT
          </span>
        )}
        <div className="ml-auto flex items-center gap-2 flex-wrap">
          <button data-testid="cons-sync-g6-btn"
                  title="Sinkronkan eliminasi margin (unrealized profit) dari transaksi antar-PT FASE G-6"
                  className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1"
                  onClick={onSyncG6} disabled={busy}>
            <ArrowRightLeft size={13} /> Sinkron Antar-PT (G-6)
          </button>
          <button data-testid="cons-sync-pairs-btn"
                  title="Sinkronkan eliminasi dari pasangan jurnal transfer antar-PT lama (nilai perolehan · M-3)"
                  className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1"
                  onClick={onSyncPairs} disabled={busy}>
            <Link2 size={13} /> Sinkron Pasangan Jurnal
          </button>
          <button data-testid="cons-detect-btn" className="btn-secondary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={onDetect} disabled={busy}><Wand2 size={13} /> Deteksi Otomatis</button>
          <button data-testid="cons-elim-add" className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={onAdd}><Plus size={13} /> Tambah Eliminasi</button>
        </div>
      </div>
      {elims.length === 0 ? (
        <div data-testid="cons-elim-empty" className="py-10 text-center text-[12px] text-[#8E8E93]">
          <ScissorsLineDashed size={26} className="mx-auto mb-2 text-gray-300" />Belum ada entri eliminasi. Transaksi antar-PT (G-6) akan mengisi ini sendiri; untuk data lama pakai "Sinkron Antar-PT (G-6)", "Deteksi Otomatis", atau "Tambah Eliminasi".
        </div>
      ) : (
        <div className="space-y-2">
          {elims.map((el) => (
            <div key={el.id} data-testid={`cons-elim-${el.id}`} className="rounded-md border border-[#EFF0F2] p-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[12px] font-bold text-[#1C1C1E]">{el.name}</span>
                <span className="text-[10px] text-[#9A9BA3]">Efektif {el.effective_date}</span>
                <span className={`text-[10px] font-bold rounded-full px-1.5 py-0.5 ${el.balanced ? "bg-[#E6F6EC] text-[#1B7F4B]" : "bg-[#FDEDE7] text-[#C0392B]"}`}>{el.balanced ? "Balanced" : "Tidak balanced"}</span>
                {el.source_g6_pair_id && (
                  <span data-testid={`cons-elim-auto-g6-${el.id}`}
                        title="Dijaga otomatis dari transaksi antar-PT (FASE G-6) — ikut berubah saat transaksinya dilunasi/dibatalkan"
                        className="text-[10px] font-bold rounded-full px-1.5 py-0.5 bg-[#EDE7FB] text-[#6B219A]">
                    AUTO G-6
                  </span>
                )}
                {/* FASE E-7 (E7.3) — keputusan pemilik: HPP taksiran BOLEH, tetapi tidak
                    boleh tampil sebagai angka telanjang. Entri yang HPP-nya belum
                    diposting ditandai di sini + alasannya ada di catatan. */}
                {el.g6_cost_estimated && (
                  <span data-testid={`cons-elim-cost-estimated-${el.id}`}
                        title={el.g6_cost_estimate_reason || "HPP penjual belum diposting"}
                        className="text-[10px] font-bold rounded-full px-1.5 py-0.5 bg-[#FFF4E5] text-[#8A5300]">
                    HPP TAKSIRAN
                  </span>
                )}
                <span className="text-[11px] text-[#6B6B73] ml-auto tabular-nums">Rp {Number(el.total_debit || 0).toLocaleString("id-ID")}</span>
                {el.source_g6_pair_id ? (
                  <span className="text-[10px] text-[#9A9BA3]" title="Dikelola sistem: ikut transaksi antar-PT-nya (batalkan transaksinya bila ingin hilang)">
                    dikelola sistem
                  </span>
                ) : (
                  <button data-testid={`cons-elim-del-${el.id}`} className="text-[#C9C9CE] hover:text-[#C0392B]" onClick={() => onDelete(el)} disabled={busy} aria-label="Hapus"><Trash2 size={13} /></button>
                )}
              </div>
              {el.note && <p className="text-[11px] text-[#6B6B73] mt-0.5">{el.note}</p>}
              <div className="mt-2 overflow-x-auto rounded border border-[#F5F5F7]">
                <table className="w-full text-[11px]">
                  <thead><tr className="text-left text-[9px] font-bold uppercase text-[#9A9BA3] bg-[#FAFBFC]"><th className="px-2 py-1">Akun</th><th className="px-2 py-1 text-right">Debit</th><th className="px-2 py-1 text-right">Kredit</th></tr></thead>
                  <tbody>
                    {(el.lines || []).map((l, i) => (
                      <tr key={i} className="border-t border-[#F5F5F7]">
                        <td className="px-2 py-1"><span className="font-mono text-[9px] text-[#9A9BA3] mr-1">{l.account_code}</span>{l.account_name}</td>
                        <td className="px-2 py-1 text-right tabular-nums">{l.debit > 0 ? formatCurrency(l.debit) : "—"}</td>
                        <td className="px-2 py-1 text-right tabular-nums">{l.credit > 0 ? formatCurrency(l.credit) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EliminationModal({ initial, accounts, entities, onClose, onSaved, setError }) {
  const [name, setName] = useState(initial.name || "Eliminasi Intercompany");
  const [effDate, setEffDate] = useState(ymd(NOW));
  const [note, setNote] = useState("");
  const [lines, setLines] = useState(initial.lines || [{ account_code: "", debit: 0, credit: 0, description: "" }, { account_code: "", debit: 0, credit: 0, description: "" }]);
  const [saving, setSaving] = useState(false);
  const entOpts = [{ value: "", label: "—" }, ...entities.filter((e) => !e.is_group).map((e) => ({ value: e.id, label: e.short_name || e.id }))];
  const [entFrom, setEntFrom] = useState("");
  const [entTo, setEntTo] = useState("");

  const setLine = (i, k, v) => setLines((ls) => ls.map((l, idx) => idx === i ? { ...l, [k]: v } : l));
  const addLine = () => setLines((ls) => [...ls, { account_code: "", debit: 0, credit: 0, description: "" }]);
  const rmLine = (i) => setLines((ls) => ls.filter((_, idx) => idx !== i));

  const totalD = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const totalC = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
  const balanced = Math.abs(totalD - totalC) < 0.5 && totalD > 0;

  const save = async () => {
    const clean = lines.filter((l) => l.account_code && ((Number(l.debit) || 0) > 0 || (Number(l.credit) || 0) > 0));
    if (clean.length === 0) { setError("Minimal satu baris eliminasi dengan akun & nominal."); return; }
    setSaving(true); setError("");
    try {
      await axios.post(`${API}/finance/consolidation/eliminations`, {
        name, effective_date: effDate, note, entity_from: entFrom || null, entity_to: entTo || null,
        lines: clean.map((l) => ({ account_code: l.account_code, debit: Number(l.debit) || 0, credit: Number(l.credit) || 0, description: l.description })),
      });
      onSaved();
    } catch (e) { setError(e.response?.data?.detail || "Gagal menyimpan eliminasi."); setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="cons-elim-modal">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[92vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2]">
          <h3 className="text-[14px] font-bold text-[#1C1C1E]">Tambah Eliminasi Intercompany</h3>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3 overflow-y-auto">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Nama"><input data-testid="cons-form-name" className="field" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Tanggal Efektif"><input data-testid="cons-form-date" type="date" className="field" value={effDate} onChange={(e) => setEffDate(e.target.value)} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Entitas Dari"><KNSelect className="field" value={entFrom} onValueChange={setEntFrom} options={entOpts} /></Field>
            <Field label="Entitas Ke"><KNSelect className="field" value={entTo} onValueChange={setEntTo} options={entOpts} /></Field>
          </div>
          <Field label="Catatan"><input data-testid="cons-form-note" className="field" value={note} onChange={(e) => setNote(e.target.value)} /></Field>

          <div className="rounded-md border border-[#EFF0F2]">
            <div className="flex items-center px-2 py-1.5 bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">Baris Jurnal Eliminasi</span>
              <button data-testid="cons-form-addline" className="ml-auto text-[11px] text-[#6B219A] font-semibold inline-flex items-center gap-1" onClick={addLine}><Plus size={12} /> Baris</button>
            </div>
            <div className="p-2 space-y-2">
              {lines.map((l, i) => (
                <div key={i} className="grid grid-cols-12 gap-1.5 items-center" data-testid={`cons-form-line-${i}`}>
                  <div className="col-span-5"><KNSelect data-testid={`cons-form-line-acct-${i}`} className="field !py-1 text-[11px]" value={l.account_code} onValueChange={(v) => setLine(i, "account_code", v)} options={accounts} placeholder="Pilih akun" searchable /></div>
                  <input data-testid={`cons-form-line-debit-${i}`} type="number" className="field !py-1 text-[11px] col-span-2 tabular-nums" placeholder="Debit" value={l.debit || ""} onChange={(e) => setLine(i, "debit", e.target.value)} />
                  <input data-testid={`cons-form-line-credit-${i}`} type="number" className="field !py-1 text-[11px] col-span-2 tabular-nums" placeholder="Kredit" value={l.credit || ""} onChange={(e) => setLine(i, "credit", e.target.value)} />
                  <input className="field !py-1 text-[11px] col-span-2" placeholder="Ket." value={l.description || ""} onChange={(e) => setLine(i, "description", e.target.value)} />
                  <button className="col-span-1 text-[#C9C9CE] hover:text-[#C0392B] flex justify-center" onClick={() => rmLine(i)} aria-label="Hapus baris"><Trash2 size={13} /></button>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-3 px-3 py-2 border-t border-[#EFF0F2] text-[11px]">
              <span className="text-[#6B6B73]">Total Debit: <b className="tabular-nums">{formatCurrency(totalD)}</b></span>
              <span className="text-[#6B6B73]">Total Kredit: <b className="tabular-nums">{formatCurrency(totalC)}</b></span>
              <span data-testid="cons-form-balance" className={`ml-auto font-bold rounded-full px-2 py-0.5 ${balanced ? "bg-[#E6F6EC] text-[#1B7F4B]" : "bg-[#FDEDE7] text-[#C0392B]"}`}>{balanced ? "Balanced ✓" : "Belum balanced"}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2]">
          <button className="btn-secondary text-[12px] py-1.5 px-3" onClick={onClose}>Batal</button>
          <button data-testid="cons-form-save" className="btn-primary text-[12px] py-1.5 px-4" onClick={save} disabled={saving || !balanced}>{saving ? "Menyimpan…" : "Simpan Eliminasi"}</button>
        </div>
      </div>
    </div>
  );
}

function DetectModal({ detect, onClose, onUse }) {
  const cands = detect?.candidates || [];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="cons-detect-modal">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2]">
          <h3 className="text-[14px] font-bold text-[#1C1C1E] inline-flex items-center gap-2"><Wand2 size={15} className="text-[#6B219A]" /> Deteksi Kandidat Intercompany</h3>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={16} /></button>
        </div>
        <div className="p-4 overflow-y-auto">
          <p className="text-[11px] text-[#8E8E93] mb-3">Terdeteksi {detect?.detected_accounts || 0} akun ber-keyword intercompany. Kandidat dengan saldo per-PT:</p>
          {cands.length === 0 ? (
            <div data-testid="cons-detect-empty" className="py-8 text-center text-[12px] text-[#8E8E93]">
              Tidak ada akun/saldo intercompany terdeteksi. Beri nama akun mengandung kata "Intercompany"/"Antar-PT" agar terdeteksi otomatis.
            </div>
          ) : (
            <div className="space-y-2">
              {cands.map((c) => (
                <div key={c.account_code} data-testid={`cons-cand-${c.account_code}`} className="rounded-md border border-[#EFF0F2] p-2.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-[#9A9BA3]">{c.account_code}</span>
                    <span className="text-[12px] font-bold text-[#1C1C1E]">{c.account_name}</span>
                    <span className="text-[11px] text-[#6B6B73] ml-auto tabular-nums">Net {formatCurrency(c.total_net)}</span>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {c.per_entity.map((p) => (
                      <span key={p.entity_id} className="text-[10px] rounded-full px-2 py-0.5 bg-[#F3F3F5] text-[#6B6B73]">{p.short_name}: <b className="tabular-nums">{formatCurrency(p.balance)}</b></span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2]">
          <button className="btn-secondary text-[12px] py-1.5 px-3" onClick={onClose}>Tutup</button>
          <button data-testid="cons-detect-use" className="btn-primary text-[12px] py-1.5 px-4" onClick={onUse} disabled={(detect?.suggested_lines || []).length === 0}>Jadikan Draf Eliminasi</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (<label className="block"><span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93] block mb-1">{label}</span>{children}</label>);
}
