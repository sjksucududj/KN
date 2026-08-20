/**
 * BudgetView (R6.3 — Budget Control penuh) — Anggaran vs Komitmen vs Realisasi.
 * Dua dimensi: **Akun COA** & **Kategori Beban**. Sumber: /api/finance/budget-vs-actual,
 * CRUD /api/finance/budgets, /api/finance/budget-keys, GET|PUT /api/finance/budget-rules.
 * Komitmen = PO terbuka + LPJ petty cash pending · Realisasi = jurnal GL / LPJ terposting.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import {
  RefreshCw, Target, Wallet, TrendingDown, ClipboardList, Plus, ShieldCheck, AlertTriangle,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import {
  FC, NOW, YEARS, compactIDR, entityParam, chartTooltip, fmtPct,
  KpiCard, Panel, EmptyState, formatCurrency,
} from "./financeShared";
import {
  DIM_TABS, BudgetFormRow, BudgetTable, BudgetRulesPanel, AlertsStrip, UnbudgetedPanel,
} from "./BudgetParts";

export default function BudgetView({ selectedEntity, currentUser }) {
  const [year, setYear] = useState(String(NOW.getFullYear()));
  const [tab, setTab] = useState("account");
  const [data, setData] = useState(null);
  const [keys, setKeys] = useState({ accounts: [], categories: [], default_po_account: "1-1300" });
  const [rules, setRules] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState(null);
  const [editAmount, setEditAmount] = useState("");
  const isAdmin = currentUser?.role === "admin";

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [rep, rl] = await Promise.all([
        axios.get(`${API}/finance/budget-vs-actual`, { params: { year, ...entityParam(selectedEntity) } }),
        axios.get(`${API}/finance/budget-rules`, { params: entityParam(selectedEntity) }).catch(() => ({ data: null })),
      ]);
      setData(rep.data || null);
      setRules(rl.data || rep.data?.rules || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat anggaran.");
    } finally { setLoading(false); }
  }, [year, selectedEntity]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    axios.get(`${API}/finance/budget-keys`, { params: entityParam(selectedEntity) })
      .then((r) => setKeys(r.data || {}))
      .catch(() => { /* opsional */ });
  }, [selectedEntity]);

  const notify = (m) => { setMsg(m); setTimeout(() => setMsg(""), 6000); };

  const tot = data?.totals || {};
  const allRows = data?.rows || [];
  const rows = useMemo(() => allRows.filter((r) => r.dimension === tab), [allRows, tab]);
  const dimSum = data?.by_dimension?.[tab] || {};
  const unbudgeted = useMemo(
    () => (data?.unbudgeted_commitments || []).filter((u) => u.dimension === tab), [data, tab]);

  const chartData = useMemo(() => rows.slice(0, 8).map((r) => ({
    name: (r.label || r.key || "").length > 14 ? `${(r.label || r.key).slice(0, 13)}\u2026` : (r.label || r.key),
    Anggaran: r.budget, Komitmen: r.committed, Realisasi: r.actual,
  })), [rows]);

  async function submitForm(form) {
    if (!form.key || !form.amount) { setError("Pilih akun/kategori dan isi nominal anggaran."); return false; }
    try {
      const res = await axios.post(`${API}/finance/budgets`, {
        ...entityParam(selectedEntity), year: Number(year), month: Number(form.month),
        dimension: tab, key: form.key, amount: Number(form.amount), note: form.note,
      });
      notify(`Anggaran ${res.data?.label || form.key} tersimpan (${formatCurrency(res.data?.amount)}).`);
      setShowForm(false); await load();
      return true;
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan anggaran.");
      return false;
    }
  }

  async function saveEdit(id) {
    try {
      await axios.patch(`${API}/finance/budgets/${id}`, { amount: Number(editAmount) });
      setEditId(null); notify("Nominal anggaran diperbarui."); await load();
    } catch (e) { setError(e.response?.data?.detail || "Gagal memperbarui anggaran."); }
  }

  async function removeBudget(id) {
    try { await axios.delete(`${API}/finance/budgets/${id}`); notify("Anggaran dihapus."); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menghapus anggaran."); }
  }

  async function saveRules(patch) {
    try {
      const res = await axios.put(`${API}/finance/budget-rules`, { ...entityParam(selectedEntity), ...patch });
      setRules(res.data);
      notify(`Kebijakan anggaran disimpan: mode ${String(res.data?.mode).toUpperCase()}.`);
      await load();
      return true;
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan kebijakan anggaran.");
      return false;
    }
  }

  return (
    <div data-testid="budget-view">
      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-3">
        <KpiCard testId="budget-kpi-total" label={`Anggaran ${year}`} value={formatCurrency(tot.budget)}
          icon={Target} accent={FC.purple} sub={`${allRows.length} baris anggaran`} />
        <KpiCard testId="budget-kpi-commitment" label="Komitmen (PO/LPJ)" value={formatCurrency(tot.commitment)}
          icon={ClipboardList} accent={FC.amber} tone="text-[#C77700]" sub="belanja terikat belum realisasi" />
        <KpiCard testId="budget-kpi-actual" label="Realisasi" value={formatCurrency(tot.actual)}
          icon={Wallet} accent={FC.cash} tone="text-[#0058CC]" sub={`Terpakai ${fmtPct(tot.used_pct)}`} />
        <KpiCard testId="budget-kpi-remaining" label="Sisa (Tersedia)" value={formatCurrency(tot.remaining)}
          icon={TrendingDown} accent={(tot.remaining ?? 0) >= 0 ? FC.revenue : FC.expense}
          tone={(tot.remaining ?? 0) >= 0 ? "text-[#1B7F4B]" : "text-[#C0392B]"}
          sub={`Anggaran − komitmen − realisasi (${fmtPct(tot.spent_pct)})`} />
        <KpiCard testId="budget-kpi-over" label="Pos Over-Budget" value={`${tot.over_count || 0}`}
          icon={AlertTriangle} accent={FC.expense}
          tone={(tot.over_count || 0) > 0 ? "text-[#C0392B]" : "text-[#1B7F4B]"}
          sub={`Kebijakan: ${String(rules?.mode || "warn").toUpperCase()}`} />
      </div>

      {/* Toolbar: tahun + tab dimensi + aksi */}
      <div className="rounded-lg border border-[#EFF0F2] p-3 mb-3 bg-[#FCFCFD] flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Tahun</label>
          <div className="w-[110px]">
            <KNSelect data-testid="budget-year" className="field py-1.5 text-[12px]" value={year}
              onValueChange={setYear} options={YEARS} />
          </div>
        </div>
        <div>
          <label className="block text-[10px] font-bold uppercase text-[#8E8E93] mb-1">Dimensi Anggaran</label>
          <div className="flex items-center gap-1.5" data-testid="budget-dim-tabs">
            {DIM_TABS.map((t) => (
              <button key={t.value} data-testid={`budget-tab-${t.value}`}
                onClick={() => { setTab(t.value); setShowForm(false); }}
                className={`text-[11.5px] font-semibold rounded-md px-3 py-1.5 border transition-colors ${
                  tab === t.value ? "bg-[#F3EAFB] border-[#D9C4EC] text-[#6B219A]"
                    : "bg-white border-[#EFF0F2] text-[#6B6B73] hover:border-[#D9C4EC]"}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button data-testid="budget-add-toggle" onClick={() => setShowForm((s) => !s)}
            className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1">
            <Plus size={13} /> Tambah Anggaran
          </button>
          <button data-testid="budget-refresh" className="icon-button" onClick={load} aria-label="Refresh">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {showForm && (
        <BudgetFormRow dimension={tab} keys={keys} onSubmit={submitForm} onCancel={() => setShowForm(false)} />
      )}

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="budget-error" />
      {msg && (
        <div className="notice-bar success mb-3" data-testid="budget-notice">
          <span>{msg}</span><button onClick={() => setMsg("")} aria-label="Tutup">×</button>
        </div>
      )}

      <BudgetRulesPanel rules={rules} isAdmin={isAdmin} onSave={saveRules}
        defaultAccount={keys.default_po_account} />

      <AlertsStrip alerts={data?.alerts || []} />

      {loading ? (
        <div className="h-[280px] bg-[#F5F5F7] rounded animate-pulse" data-testid="budget-loading" />
      ) : rows.length === 0 ? (
        <Panel title={`Anggaran vs Realisasi — ${DIM_TABS.find((t) => t.value === tab)?.label}`} icon={Target}>
          <EmptyState icon={Target} title="Belum ada anggaran untuk dimensi & tahun ini"
            hint="Klik ‘Tambah Anggaran’ untuk menetapkan pagu per akun COA atau per kategori beban."
            testId="budget-empty" />
        </Panel>
      ) : (
        <>
          <Panel title={`Anggaran · Komitmen · Realisasi (${DIM_TABS.find((t) => t.value === tab)?.label})`}
            icon={Target} testId="budget-chart" className="mb-3"
            actions={<span className="text-[10.5px] text-[#8E8E93]">
              Pagu {formatCurrency(dimSum.budget)} · Terikat {formatCurrency(dimSum.committed)} ·
              Realisasi {formatCurrency(dimSum.actual)} · Sisa {formatCurrency(dimSum.remaining)}
            </span>}>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={FC.grid} />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-12} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={compactIDR} width={52} />
                <Tooltip formatter={(v, n) => [formatCurrency(v), n]} {...chartTooltip} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="Anggaran" fill={FC.purple} radius={[4, 4, 0, 0]} maxBarSize={18} />
                <Bar dataKey="Komitmen" fill={FC.amber} radius={[4, 4, 0, 0]} maxBarSize={18} />
                <Bar dataKey="Realisasi" fill={FC.cash} radius={[4, 4, 0, 0]} maxBarSize={18} />
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Rincian Anggaran" icon={ClipboardList} testId="budget-table-panel">
            <BudgetTable rows={rows} editId={editId} editAmount={editAmount}
              setEditAmount={setEditAmount}
              onEdit={(r) => { setEditId(r.id); setEditAmount(String(r.budget)); }}
              onCancelEdit={() => setEditId(null)} onSave={saveEdit} onDelete={removeBudget} />
          </Panel>
        </>
      )}

      <UnbudgetedPanel items={unbudgeted} dimension={tab} />

      <p className="mt-2 text-[11px] text-[#9A9BA3] flex items-start gap-1.5">
        <ShieldCheck size={12} className="mt-0.5 shrink-0" />
        <span>
          <b>Realisasi</b>: dimensi akun dari jurnal GL (non-void, exclude penutup); dimensi kategori dari
          LPJ petty cash terposting. <b>Komitmen</b>: PO terbuka (nilai DPP; default akun
          {" "}{keys.default_po_account || "1-1300"} bila PO tak ditandai) + LPJ menunggu.
          <b> Sisa</b> = Anggaran − Komitmen − Realisasi. Semua angka diturunkan langsung dari sumber (tanpa cache).
        </span>
      </p>
    </div>
  );
}
