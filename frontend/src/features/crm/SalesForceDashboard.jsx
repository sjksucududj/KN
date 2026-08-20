import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { TrendingUp, Target, Award, X, BarChart3, ArrowUpRight, ArrowDownRight, Landmark, CheckCircle2 } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import { KpiTile, currentPeriod, pct } from "./crmUtils";

/** Sales Force dashboard (KN_17 §6) — KPI + komisi + leaderboard + target. */
export default function SalesForceDashboard({ currentUser, selectedEntity }) {
  const role = currentUser?.role;
  const isManager = role === "admin" || role === "manager";
  const [period, setPeriod] = useState(currentPeriod());
  const [salesUsers, setSalesUsers] = useState([]);
  const [salesId, setSalesId] = useState(isManager ? "" : currentUser?.id);
  const [kpi, setKpi] = useState(null);
  const [commission, setCommission] = useState(null);
  const [history, setHistory] = useState([]);
  const [board, setBoard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showTarget, setShowTarget] = useState(false);
  const [glStatus, setGlStatus] = useState(null);     // F0-E akrual insentif → GL
  const [postingGl, setPostingGl] = useState(false);
  const accrualEntity = (selectedEntity && selectedEntity !== "all") ? selectedEntity : null;

  useEffect(() => { if (isManager) loadSales(); }, []); // eslint-disable-line
  useEffect(() => { load(); }, [period, salesId, selectedEntity]); // eslint-disable-line
  useEffect(() => { if (isManager) refreshGlStatus(); }, [period, selectedEntity]); // eslint-disable-line

  async function refreshGlStatus() {
    if (!accrualEntity) { setGlStatus(null); return; }
    try {
      const r = await axios.get(`${API}/sales/incentive/gl-status`, { params: { period, entity_id: accrualEntity } });
      setGlStatus(r.data);
    } catch (e) { setGlStatus(null); }
  }

  async function postIncentiveGl() {
    if (!accrualEntity) { setError("Pilih entitas spesifik (bukan 'Semua Entitas') untuk posting insentif ke GL."); return; }
    setPostingGl(true);
    try {
      const r = await axios.post(`${API}/sales/incentive/post-gl`, null, { params: { period, entity_id: accrualEntity } });
      setNotice(r.data?.message || "Akrual insentif diposting ke GL.");
      setGlStatus(r.data || null);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal posting insentif ke GL.");
    } finally { setPostingGl(false); }
  }

  async function loadSales() {
    try {
      const r = await axios.get(`${API}/sales-users`);
      const list = r.data || [];
      setSalesUsers(list);
      if (isManager && !salesId && list.length) setSalesId(list[0].id);
    } catch (e) { /* */ }
  }

  async function load() {
    setLoading(true);
    try {
      const entity = (selectedEntity && selectedEntity !== "all") ? selectedEntity : undefined;
      const reqs = [];
      const targetSales = isManager ? (salesId || undefined) : currentUser?.id;
      reqs.push(axios.get(`${API}/sales/kpi`, { params: { sales_id: targetSales, period, entity_id: entity } }));
      reqs.push(axios.get(`${API}/sales/commission`, { params: { sales_id: targetSales, period, entity_id: entity } }));
      const histIdx = reqs.length;
      reqs.push(axios.get(`${API}/sales/commission-history`, { params: { sales_id: targetSales, period_type: "month", anchor: period, count: 6, entity_id: entity } }));
      const boardIdx = isManager ? reqs.length : -1;
      if (isManager) reqs.push(axios.get(`${API}/sales/leaderboard`, { params: { period, entity_id: entity } }));
      const res = await Promise.all(reqs);
      setKpi(res[0].data);
      setCommission(res[1].data);
      setHistory(Array.isArray(res[histIdx].data) ? res[histIdx].data : []);
      if (isManager) setBoard(Array.isArray(res[boardIdx].data) ? res[boardIdx].data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data sales force.");
    } finally { setLoading(false); }
  }

  const salesOptions = useMemo(() => [
    { value: "", label: "Saya / Default" },
    ...salesUsers.map((s) => ({ value: s.id, label: s.name })),
  ], [salesUsers]);

  return (
    <div data-testid="salesforce-dashboard">
      {notice && <div className="notice-bar success" data-testid="sf-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="sf-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2"><TrendingUp size={16} className="text-[#0058CC]" /><h2 data-testid="sf-title">Sales Force — KPI & Komisi</h2></div>
          <div className="flex items-center gap-2">
            {isManager && <KNSelect value={salesId} onValueChange={setSalesId} className="field w-[170px]" data-testid="sf-sales-select" options={salesOptions} />}
            <input type="month" data-testid="sf-period" value={period} onChange={(e) => setPeriod(e.target.value)} className="field w-[140px]" />
            {isManager && <button data-testid="sf-set-target" onClick={() => setShowTarget(true)} className="secondary-button"><Target size={13} /> Set Target</button>}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="section-card py-10 text-center text-[12px] text-[#6B6B73]" data-testid="sf-loading">Memuat...</div>
      ) : (
        <>
          {/* KPI tiles */}
          {kpi && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3" data-testid="sf-kpi">
              <KpiTile label="Penjualan (periode)" value={formatCurrency(kpi.total_sales)} sub={`${kpi.orders_count} pesanan`} testId="sf-kpi-sales" />
              <KpiTile label="Pencairan (collected)" value={formatCurrency(kpi.total_collected)} tone="text-[#1E8E5A]" sub={`rate ${pct(kpi.collection_rate)}`} testId="sf-kpi-collected" />
              <KpiTile label="Piutang Belum Lunas" value={formatCurrency(kpi.ar_outstanding)} tone={kpi.overdue_amount > 0 ? "text-[#C0392B]" : "text-[#0058CC]"} sub={`lewat jatuh tempo ${formatCurrency(kpi.overdue_amount)}`} testId="sf-kpi-ar" />
              <KpiTile label="Pelanggan" value={kpi.customers_count} sub={`${kpi.new_customers} baru · ${kpi.blocked_customers} blokir`} testId="sf-kpi-customers" />
            </div>
          )}

          {/* Commission card */}
          {commission && (
            <div className="section-card mb-3" data-testid="sf-commission">
              <div className="section-head"><div className="flex items-center gap-2"><Award size={14} className="text-[#B45309]" /><h3 className="text-[12.5px] font-bold">Komisi (pencairan + tiered)</h3></div></div>
              <div className="section-body grid grid-cols-2 md:grid-cols-4 gap-3">
                <KpiTile label="Basis (pencairan)" value={formatCurrency(commission.base_amount)} />
                <KpiTile label="Capaian Target" value={`${commission.achievement_pct}%`} sub={`target ${formatCurrency(commission.target_amount)}`} testId="sf-achievement" />
                <KpiTile label="Rate Berlaku" value={`${commission.applied_rate}%`} />
                <KpiTile label="Total Insentif" value={formatCurrency(commission.total_incentive)} tone="text-[#1E8E5A]" sub={commission.bonus_new_customer > 0 ? `+bonus ${formatCurrency(commission.bonus_new_customer)}` : ""} testId="sf-incentive" />
              </div>
            </div>
          )}

          {/* F0-E — Akrual Insentif → GL (Model 1: beban di buku entitas SO) */}
          {isManager && (
            <div className="section-card mb-3" data-testid="sf-incentive-gl">
              <div className="section-head">
                <div className="flex items-center gap-2"><Landmark size={14} className="text-[#6B219A]" /><h3 className="text-[12.5px] font-bold">Akrual Insentif → GL — {period}</h3></div>
                {!accrualEntity ? (
                  <span className="status-pill pill-muted" data-testid="sf-gl-status">Pilih entitas</span>
                ) : glStatus?.posted ? (
                  <span className="status-pill pill-success inline-flex items-center gap-1" data-testid="sf-gl-status"><CheckCircle2 size={11} /> Terposting</span>
                ) : (
                  <span className="status-pill pill-warning" data-testid="sf-gl-status">Belum diposting</span>
                )}
              </div>
              <div className="section-body flex items-center justify-between gap-3 flex-wrap">
                <div className="text-[11.5px] text-[#6B6B73] max-w-[60ch]">
                  {!accrualEntity ? (
                    "Pilih entitas spesifik di Entity Switcher untuk membukukan beban insentif ke buku entitas tersebut (oversight 'Semua Entitas' tidak bisa memposting)."
                  ) : glStatus?.posted ? (
                    <>Beban insentif <b className="tabular-nums">{formatCurrency(glStatus.amount)}</b> telah dibukukan (JE <span className="font-semibold">{glStatus.journal_number}</span>). <span className="text-[#1E8E5A]">Dr Beban Insentif Penjualan / Cr Hutang Insentif Penjualan.</span></>
                  ) : (
                    "Belum ada jurnal akrual periode ini. Posting untuk membukukan beban insentif penjualan ke buku entitas aktif (idempotent)."
                  )}
                </div>
                <button
                  data-testid="sf-post-incentive-gl"
                  disabled={postingGl || !accrualEntity || !!glStatus?.posted}
                  onClick={postIncentiveGl}
                  className="primary-button inline-flex items-center gap-1.5">
                  <Landmark size={13} /> {postingGl ? "Memposting..." : glStatus?.posted ? "Sudah Diposting" : "Posting ke GL"}
                </button>
              </div>
            </div>
          )}

          {/* Riwayat komisi multi-periode (KN_17 §6 / owner 5a) */}
          {history.length > 0 && (
            <CommissionHistory rows={history} data-testid="sf-commission-history" />
          )}

          {/* Leaderboard (manager) */}
          {isManager && (
            <div className="section-card" data-testid="sf-leaderboard">
              <div className="section-head"><h3 className="text-[12.5px] font-bold">Leaderboard</h3></div>
              <div className="section-body">
                <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
                  <div className="grid grid-cols-[40px_1.4fr_1fr_1fr_90px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
                    <span>#</span><span>Sales</span><span>Penjualan</span><span>Pencairan</span><span>Rate</span>
                  </div>
                  {board.length === 0 ? (
                    <div className="py-8 text-center text-[11.5px] text-[#9A9BA3]">Belum ada data.</div>
                  ) : board.map((b) => (
                    <div key={b.sales_id} data-testid={`sf-board-row-${b.sales_id}`} className="grid grid-cols-[40px_1.4fr_1fr_1fr_90px] items-center px-3 py-2 text-[11.5px] border-b border-[#EFF0F2] last:border-0">
                      <span className="font-bold text-[#B45309]">{b.rank}</span>
                      <span className="font-semibold truncate">{b.sales_name}</span>
                      <span className="tabular-nums">{formatCurrency(b.total_sales)}</span>
                      <span className="tabular-nums text-[#1E8E5A]">{formatCurrency(b.total_collected)}</span>
                      <span className="tabular-nums">{pct(b.collection_rate)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {showTarget && <SetTargetModal salesUsers={salesUsers} period={period} defaultSales={salesId}
        onClose={() => setShowTarget(false)}
        onDone={(m) => { setShowTarget(false); setNotice(m); load(); }} onError={(m) => setError(m)} />}
    </div>
  );
}

function CommissionHistory({ rows }) {
  const max = Math.max(...rows.map((r) => Number(r.total_incentive) || 0), 1);
  const latest = rows[rows.length - 1] || {};
  const prev = rows[rows.length - 2];
  const delta = prev ? (Number(latest.total_incentive || 0) - Number(prev.total_incentive || 0)) : 0;
  return (
    <div className="section-card mb-3" data-testid="sf-commission-history">
      <div className="section-head">
        <div className="flex items-center gap-2">
          <BarChart3 size={14} className="text-[#0058CC]" />
          <h3 className="text-[12.5px] font-bold">Riwayat Komisi (6 periode)</h3>
        </div>
        {prev && (
          <span className={`status-pill ${delta >= 0 ? "pill-success" : "pill-danger"} inline-flex items-center gap-1`} data-testid="sf-hist-delta">
            {delta >= 0 ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
            {delta >= 0 ? "+" : ""}{formatCurrency(delta)} vs periode lalu
          </span>
        )}
      </div>
      <div className="section-body">
        {/* Bar chart insentif per periode */}
        <div className="grid grid-cols-6 gap-2 items-end h-[120px] mb-3" data-testid="sf-hist-chart">
          {rows.map((r) => {
            const h = Math.round(((Number(r.total_incentive) || 0) / max) * 100);
            return (
              <div key={r.period} className="flex flex-col items-center justify-end h-full" data-testid={`sf-hist-bar-${r.period}`}>
                <span className="text-[9.5px] font-semibold text-[#0058CC] mb-1 tabular-nums">{formatCurrency(r.total_incentive)}</span>
                <div
                  className="w-full rounded-t-md bg-[#0058CC] transition-[height] duration-200"
                  style={{ height: `${Math.max(h, 3)}%`, minHeight: 4 }}
                  title={`${r.period} · ${formatCurrency(r.total_incentive)}`}
                />
              </div>
            );
          })}
        </div>
        {/* Tabel ringkas */}
        <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
          <div className="grid grid-cols-[90px_1fr_1fr_88px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Periode</span><span>Pencairan</span><span>Insentif</span><span>Capaian</span>
          </div>
          {rows.map((r) => (
            <div key={r.period} data-testid={`sf-hist-row-${r.period}`} className="grid grid-cols-[90px_1fr_1fr_88px] items-center px-3 py-2 text-[11.5px] border-b border-[#EFF0F2] last:border-0">
              <span className="font-semibold">{r.period}</span>
              <span className="tabular-nums text-[#1E8E5A]">{formatCurrency(r.total_collected)}</span>
              <span className="tabular-nums font-semibold">{formatCurrency(r.total_incentive)}</span>
              <span className="tabular-nums text-[#6B6B73]">{r.achievement_pct}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SetTargetModal({ salesUsers, period, defaultSales, onClose, onDone, onError }) {
  const [sid, setSid] = useState(defaultSales || "");
  const [per, setPer] = useState(period);
  const [sales, setSales] = useState("");
  const [coll, setColl] = useState("");
  const [newC, setNewC] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    if (!sid) { onError?.("Pilih sales."); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/sales-targets`, { sales_id: sid, period: per,
        target_sales_amount: Number(sales) || 0, target_collection_amount: Number(coll) || 0,
        target_new_customers: Number(newC) || 0 });
      onDone?.("Target sales disimpan.");
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal menyimpan target."); } finally { setBusy(false); }
  }
  return (
    <div className="modal-overlay" data-testid="set-target-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 460, width: "92vw" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2]">
          <div className="flex items-center gap-2"><Target size={16} className="text-[#0058CC]" /><h2 className="text-[14px] font-bold">Set Target Sales</h2></div>
          <button onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>
        <div className="p-4 grid grid-cols-2 gap-3">
          <div className="col-span-2"><label className="block text-[11px] font-semibold mb-1">Salesperson *</label>
            <KNSelect value={sid} onValueChange={setSid} className="field" data-testid="target-sales-select"
              placeholder="Pilih sales" options={(salesUsers || []).map((s) => ({ value: s.id, label: s.name }))} /></div>
          <div className="col-span-2"><label className="block text-[11px] font-semibold mb-1">Periode</label>
            <input type="month" data-testid="target-period" value={per} onChange={(e) => setPer(e.target.value)} className="field" /></div>
          <div><label className="block text-[11px] font-semibold mb-1">Target Penjualan</label>
            <input type="number" data-testid="target-sales-amount" value={sales} onChange={(e) => setSales(e.target.value)} className="field" placeholder="Rp" /></div>
          <div><label className="block text-[11px] font-semibold mb-1">Target Pencairan</label>
            <input type="number" data-testid="target-collection-amount" value={coll} onChange={(e) => setColl(e.target.value)} className="field" placeholder="Rp" /></div>
          <div className="col-span-2"><label className="block text-[11px] font-semibold mb-1">Target Pelanggan Baru</label>
            <input type="number" data-testid="target-new-customers" value={newC} onChange={(e) => setNewC(e.target.value)} className="field" placeholder="0" /></div>
        </div>
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2]">
          <button onClick={onClose} className="secondary-button">Batal</button>
          <button data-testid="target-submit" disabled={busy} onClick={go} className="primary-button">{busy ? "..." : "Simpan Target"}</button>
        </div>
      </div>
    </div>
  );
}
