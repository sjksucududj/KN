/**
 * BankAccountsView (EPIC7-B) — Kas & Bank: multi-akun + ledger + rekonsiliasi.
 * Akses admin/manager (permission "cash"). Sumber: /api/bank-accounts (+ /ledger, /reconcile).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  RefreshCw, Plus, Landmark, Wallet, CheckCircle2, Circle, X, Banknote, ArrowDownLeft, ArrowUpRight,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import DetailModal from "../../components/DetailModal";

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "2-digit" }); }
  catch { return "—"; }
}

const EMPTY_FORM = { name: "", account_type: "bank", bank_name: "", account_number: "", opening_balance: "" };

export default function BankAccountsView({ selectedEntity }) {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);     // account id
  const [ledger, setLedger] = useState(null);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const res = await axios.get(`${API}/bank-accounts`, { params });
      setAccounts(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat akun kas/bank.");
    } finally {
      setLoading(false);
    }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load]);

  const openLedger = useCallback(async (id, silent = false) => {
    setSelected(id);
    if (!silent) { setLedger(null); setLedgerLoading(true); }
    try {
      const res = await axios.get(`${API}/bank-accounts/${id}/ledger`);
      setLedger(res.data || null);
    } catch {
      if (!silent) setLedger(null);
    } finally {
      if (!silent) setLedgerLoading(false);
    }
  }, []);

  const toggleReconcile = async (txn) => {
    const next = !txn.reconciled;
    // optimistic update agar tombol langsung berubah
    setLedger((prev) => prev ? {
      ...prev,
      transactions: prev.transactions.map((t) => t.id === txn.id ? { ...t, reconciled: next } : t),
    } : prev);
    try {
      await axios.post(`${API}/cash-transactions/${txn.id}/reconcile`, { reconciled: next });
      await load();                       // sinkron saldo kartu
      await openLedger(selected, true);   // silent refresh (tanpa flash skeleton)
    } catch (err) {
      setError(err.response?.data?.detail || "Gagal memperbarui rekonsiliasi.");
      await openLedger(selected, true);   // revert dari server
    }
  };

  const submitForm = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/bank-accounts`, {
        ...form, opening_balance: Number(form.opening_balance || 0),
      });
      setForm(EMPTY_FORM);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || "Gagal membuat akun.");
    } finally {
      setSaving(false);
    }
  };

  const summary = useMemo(() => {
    const total = accounts.reduce((s, a) => s + (a.balance || 0), 0);
    const bank = accounts.filter((a) => a.account_type === "bank").reduce((s, a) => s + (a.balance || 0), 0);
    const cash = accounts.filter((a) => a.account_type === "cash").reduce((s, a) => s + (a.balance || 0), 0);
    const unrec = accounts.reduce((s, a) => s + (a.unreconciled_count || 0), 0);
    return { total, bank, cash, unrec, count: accounts.length };
  }, [accounts]);

  return (
    <div data-testid="bank-accounts-view">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <Kpi testId="bank-kpi-total" label="Total Saldo" value={formatCurrency(summary.total)} icon={Banknote} />
        <Kpi testId="bank-kpi-bank" label="Saldo Bank" value={formatCurrency(summary.bank)} icon={Landmark} tone="text-[#0058CC]" />
        <Kpi testId="bank-kpi-cash" label="Saldo Kas" value={formatCurrency(summary.cash)} icon={Wallet} tone="text-[#1B7F4B]" />
        <Kpi testId="bank-kpi-unrec" label="Belum Rekonsiliasi" value={summary.unrec} icon={Circle} tone={summary.unrec > 0 ? "text-[#B45309]" : ""} />
      </div>

      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2"><Landmark size={16} className="text-[#6B219A]" /><h2 data-testid="bank-title">Akun Kas & Bank</h2></div>
          <div className="flex items-center gap-2 ml-auto">
            <button data-testid="bank-add-toggle" className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={() => setShowForm((v) => !v)}>
              <Plus size={14} /> Tambah Akun
            </button>
            <button data-testid="bank-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="bank-error" />

          {showForm && (
            <form data-testid="bank-add-form" onSubmit={submitForm} className="mb-3 rounded-lg border border-[#E6E0F2] bg-[#FAF8FE] p-3 grid grid-cols-2 md:grid-cols-3 gap-2">
              <div>
                <label className="text-[10px] font-bold uppercase text-[#8E8E93]">Nama Akun</label>
                <input data-testid="bank-form-name" className="field py-1 text-[12px]" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="BCA Operasional" required />
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase text-[#8E8E93]">Jenis</label>
                <div className="flex gap-1 mt-0.5">
                  {["bank", "cash"].map((t) => (
                    <button type="button" key={t} data-testid={`bank-form-type-${t}`}
                      className={`flex-1 text-[12px] font-semibold rounded-md py-1 border ${form.account_type === t ? "bg-[#6B219A] text-white border-[#6B219A]" : "bg-white border-[#EFF0F2] text-[#6B6B73]"}`}
                      onClick={() => setForm({ ...form, account_type: t })}>{t === "bank" ? "Bank" : "Kas"}</button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase text-[#8E8E93]">Saldo Awal</label>
                <input data-testid="bank-form-opening" type="number" className="field py-1 text-[12px] tabular-nums" value={form.opening_balance} onChange={(e) => setForm({ ...form, opening_balance: e.target.value })} placeholder="0" />
              </div>
              {form.account_type === "bank" && (
                <>
                  <div>
                    <label className="text-[10px] font-bold uppercase text-[#8E8E93]">Nama Bank</label>
                    <input data-testid="bank-form-bankname" className="field py-1 text-[12px]" value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} placeholder="BCA" />
                  </div>
                  <div>
                    <label className="text-[10px] font-bold uppercase text-[#8E8E93]">No. Rekening</label>
                    <input data-testid="bank-form-accountno" className="field py-1 text-[12px] tabular-nums" value={form.account_number} onChange={(e) => setForm({ ...form, account_number: e.target.value })} placeholder="0123456789" />
                  </div>
                </>
              )}
              <div className="col-span-2 md:col-span-3 flex justify-end gap-2 mt-1">
                <button type="button" className="btn-secondary text-[12px] py-1.5 px-3" onClick={() => { setShowForm(false); setForm(EMPTY_FORM); }}>Batal</button>
                <button type="submit" data-testid="bank-form-submit" className="btn-primary text-[12px] py-1.5 px-4" disabled={saving}>{saving ? "Menyimpan..." : "Simpan Akun"}</button>
              </div>
            </form>
          )}

          {loading ? (
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3" data-testid="bank-loading">{[0, 1, 2].map((i) => <div key={i} className="h-28 bg-[#F5F5F7] rounded-lg animate-pulse" />)}</div>
          ) : accounts.length === 0 ? (
            <div data-testid="bank-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
              <Landmark size={26} className="mx-auto mb-2 text-gray-300" />Belum ada akun. Klik “Tambah Akun”.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="bank-cards">
              {accounts.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  data-testid={`bank-card-${a.id}`}
                  onClick={() => openLedger(a.id)}
                  className={`text-left rounded-xl border p-3.5 transition-all hover:shadow-md ${selected === a.id ? "border-[#6B219A] ring-1 ring-[#6B219A]/30 bg-[#FBF8FE]" : "border-[#EFF0F2] bg-white"}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`w-7 h-7 rounded-lg flex items-center justify-center ${a.account_type === "bank" ? "bg-[#E7F0FF] text-[#0058CC]" : "bg-[#E6F6EC] text-[#1B7F4B]"}`}>
                      {a.account_type === "bank" ? <Landmark size={15} /> : <Wallet size={15} />}
                    </span>
                    <div className="min-w-0">
                      <p className="font-bold text-[13px] text-[#1C1C1E] truncate">{a.name}</p>
                      <p className="text-[10px] text-[#9A9BA3] truncate">{a.account_type === "bank" ? `${a.bank_name || "Bank"} · ${a.account_number || "-"}` : "Kas tunai"}{a.is_active === false ? " · nonaktif" : ""}</p>
                      {/* FASE E-7 (E7.4) — rekening tingkat grup sudah tidak sah lagi.
                          Ditandai TERANG-TERANGAN supaya dipetakan, bukan dipakai lagi. */}
                      {["all", "", null, undefined].includes(a.entity_id) && (
                        <span data-testid={`bank-group-flag-${a.id}`}
                          title="Rekening tingkat grup — setiap rekening wajib milik satu badan usaha (jalankan scripts/migrate_e7_group_cash.py)"
                          className="mt-0.5 inline-block rounded border border-[#F5D9A8] bg-[#FFF4E5] px-1.5 py-[1px] text-[9.5px] font-bold text-[#8A5300]">
                          KAS GRUP — perlu dipetakan
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-[20px] font-bold tabular-nums text-[#1C1C1E] mt-1">{formatCurrency(a.balance)}</p>
                  <div className="flex items-center gap-3 text-[10.5px] text-[#6B6B73] mt-1.5">
                    <span className="inline-flex items-center gap-1 text-[#1B7F4B]"><ArrowDownLeft size={12} />{formatCurrency(a.inflow)}</span>
                    <span className="inline-flex items-center gap-1 text-[#C0392B]"><ArrowUpRight size={12} />{formatCurrency(a.outflow)}</span>
                    <span className="ml-auto">{a.txn_count} txn{a.unreconciled_count > 0 ? ` · ${a.unreconciled_count} belum rekon` : ""}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {selected && (
        <DetailModal onClose={() => { setSelected(null); setLedger(null); }}
          label="Mutasi rekening bank" testId="bank-ledger-modal">
          <LedgerPanel
            ledger={ledger}
            loading={ledgerLoading}
            onClose={() => { setSelected(null); setLedger(null); }}
            onToggle={toggleReconcile}
          />
        </DetailModal>
      )}
    </div>
  );
}

function LedgerPanel({ ledger, loading, onClose, onToggle }) {
  return (
    <div className="section-card mt-3" data-testid="bank-ledger">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <Banknote size={15} className="text-[#0058CC]" />
          <h2>{ledger?.name || "Buku Akun"}</h2>
          {ledger && <span className="text-[11px] text-[#6B6B73]">· Saldo <b className="tabular-nums">{formatCurrency(ledger.balance)}</b> · Terekonsiliasi <b className="tabular-nums">{formatCurrency(ledger.reconciled_balance)}</b></span>}
        </div>
        <button data-testid="bank-ledger-close" className="icon-button ml-auto" onClick={onClose} aria-label="Tutup"><X size={14} /></button>
      </div>
      <div className="section-body">
        {loading ? (
          <div className="grid gap-2" data-testid="bank-ledger-loading">{[0, 1, 2].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
        ) : !ledger || (ledger.transactions || []).length === 0 ? (
          <div className="py-8 text-center text-[12px] text-[#8E8E93]" data-testid="bank-ledger-empty">Belum ada transaksi pada akun ini.</div>
        ) : (
          <div className="overflow-auto rounded-md border border-[#EFF0F2]">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                  <th className="px-3 py-2">Tanggal</th>
                  <th className="px-3 py-2">No / Deskripsi</th>
                  <th className="px-3 py-2 text-right">Masuk</th>
                  <th className="px-3 py-2 text-right">Keluar</th>
                  <th className="px-3 py-2 text-right">Saldo</th>
                  <th className="px-3 py-2 text-center">Rekonsiliasi</th>
                </tr>
              </thead>
              <tbody>
                {ledger.transactions.map((t) => (
                  <tr key={t.id} data-testid={`bank-ledger-row-${t.id}`} className="border-b border-[#F5F5F7] last:border-0">
                    <td className="px-3 py-2 text-[#3C3C43]">{fmtDate(t.txn_date)}</td>
                    <td className="px-3 py-2"><span className="font-mono text-[10px] text-[#9A9BA3]">{t.number}</span><br />{t.description}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-[#1B7F4B]">{t.direction === "in" ? formatCurrency(t.amount) : "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-[#C0392B]">{t.direction === "out" ? formatCurrency(t.amount) : "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-semibold">{formatCurrency(t.running_balance)}</td>
                    <td className="px-3 py-2 text-center">
                      <button
                        data-testid={`bank-reconcile-${t.id}`}
                        onClick={() => onToggle(t)}
                        className={`inline-flex items-center gap-1 text-[10.5px] font-semibold rounded-full px-2 py-0.5 border ${t.reconciled ? "bg-[#E6F6EC] border-[#BDE5CC] text-[#1B7F4B]" : "bg-white border-[#E4E4EA] text-[#8E8E93] hover:border-[#C9DBF7]"}`}
                      >
                        {t.reconciled ? <CheckCircle2 size={12} /> : <Circle size={12} />}{t.reconciled ? "Terekonsiliasi" : "Tandai"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
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
