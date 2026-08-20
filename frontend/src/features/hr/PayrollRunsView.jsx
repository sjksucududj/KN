import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Calculator, RefreshCw, CheckCircle2, BookCheck, Banknote, Plus, FileText, Users, Send, Undo2 } from "lucide-react";
import { askReason } from "../../services/confirmService";
import KNSelect from "../../components/KNSelect";
import EntityBadge from "../../components/EntityBadge";
import ErrorNotice from "../../components/ErrorNotice";
import { rp, pct, RUN_STATUS, recentMonths, curMonth, openPayslipPdf } from "./payrollUtils";
import { entityOptions } from "../../utils/entityLabel";

function Stat({ label, value, color }) {
  return (
    <div className="section-card !p-3">
      <p className="text-[10px] uppercase font-semibold text-[#6B6B73]">{label}</p>
      <p className="text-[15px] font-bold tabular-nums leading-tight" style={{ color: color || "#1A1A1F" }}>{value}</p>
    </div>
  );
}

export default function PayrollRunsView({ currentUser, selectedEntity }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [entities, setEntities] = useState([]);
  const [form, setForm] = useState({ entity_id: "", period: curMonth() });
  const [busy, setBusy] = useState("");
  const [sel, setSel] = useState(null);

  const params = useMemo(() => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}), [selectedEntity]);

  useEffect(() => { loadRuns(); }, [selectedEntity]); // eslint-disable-line
  useEffect(() => {
    axios.get(`${API}/entities`).then((r) => {
      const list = Array.isArray(r.data) ? r.data : [];
      setEntities(list);
      setForm((f) => ({ ...f, entity_id: (selectedEntity && selectedEntity !== "all") ? selectedEntity : (list[0]?.id || "") }));
    }).catch(() => {});
  }, [selectedEntity]); // eslint-disable-line

  async function loadRuns() {
    setLoading(true);
    try { const r = await axios.get(`${API}/hr/payroll/runs`, { params }); setRuns(Array.isArray(r.data) ? r.data : []); setError(""); }
    catch (e) { setError(e.response?.data?.detail || "Gagal memuat payroll runs."); }
    finally { setLoading(false); }
  }
  async function openRun(id) {
    try { const r = await axios.get(`${API}/hr/payroll/runs/${id}`); setSel(r.data || null); }
    catch (e) { setError(e.response?.data?.detail || "Gagal memuat detail run."); }
  }
  async function createRun() {
    if (!form.entity_id || !form.period) { setError("Pilih entitas & periode."); return; }
    setBusy("create");
    try {
      const r = await axios.post(`${API}/hr/payroll/runs`, { entity_id: form.entity_id, period: form.period });
      setNotice(`Run ${r.data.number} siap (${r.data.totals.employees} karyawan).`); setError("");
      await loadRuns(); setSel(r.data);
    } catch (e) { setError(e.response?.data?.detail || "Gagal membuat run."); }
    finally { setBusy(""); }
  }
  async function act(id, action, label) {
    setBusy(action);
    try {
      // Path eksplisit (literal) — agar kontrak FE↔BE terverifikasi statis.
      let r;
      if (action === "submit") r = await axios.post(`${API}/hr/payroll/runs/${id}/submit`);
      else if (action === "approve") r = await axios.post(`${API}/hr/payroll/runs/${id}/approve`);
      else if (action === "post-gl") r = await axios.post(`${API}/hr/payroll/runs/${id}/post-gl`);
      else r = await axios.post(`${API}/hr/payroll/runs/${id}/pay`, {});
      setNotice(`${label} berhasil.`); setError("");
      setSel(r.data); await loadRuns();
    } catch (e) { setError(e.response?.data?.detail || `Gagal ${label.toLowerCase()}.`); }
    finally { setBusy(""); }
  }

  // UTANG ALUR F-6.7 — kembalikan payroll yang diajukan ke draf. Alasan WAJIB dan
  // ditanyakan lewat `askReason()` (standar dialog P5): HR yang membukanya besok harus
  // tahu apa yang perlu diperbaiki tanpa membuka layar Jejak Audit.
  async function rejectRun(id) {
    const reason = await askReason({
      title: "Kembalikan payroll ini ke draf?",
      description: "Payroll akan kembali bisa diubah HR. Alasannya tersimpan di dokumen.",
      confirmLabel: "Kembalikan ke draf",
      reasonPlaceholder: "Contoh: tunjangan transport 3 karyawan belum masuk",
      danger: true,
    });
    if (!reason) return;
    setBusy("reject");
    try {
      const r = await axios.post(`${API}/hr/payroll/runs/${id}/reject`, { reason });
      setNotice("Payroll dikembalikan ke draf."); setError("");
      setSel(r.data); await loadRuns();
    } catch (e) { setError(e.response?.data?.detail || "Gagal mengembalikan payroll."); }
    finally { setBusy(""); }
  }

  // `/api/entities` tak punya field `name` — dulu label pilihan entitas KOSONG.
  const entOpts = entityOptions(entities);
  const monthOpts = recentMonths().map((m) => ({ value: m, label: m }));

  return (
    <div data-testid="payroll-runs-view">
      {notice && (<div className="notice-bar success" data-testid="payroll-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>)}
      <ErrorNotice message={error} onRetry={loadRuns} onDismiss={() => setError("")} testId="payroll-runs-error" />

      {/* Buat Run */}
      <div className="section-card mb-3">
        <div className="section-head"><div className="flex items-center gap-2"><Calculator size={16} className="text-[#0058CC]" /><h2 data-testid="payroll-runs-title">Payroll Run — Penggajian</h2></div>
          <button data-testid="payroll-runs-refresh" onClick={loadRuns} className="icon-button" title="Muat ulang"><RefreshCw size={15} /></button>
        </div>
        <div className="section-body grid gap-2 md:grid-cols-[1fr_180px_auto] items-end">
          <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Entitas</label>
            <KNSelect data-testid="payroll-create-entity" value={form.entity_id} onValueChange={(v) => setForm((f) => ({ ...f, entity_id: v }))} className="field" options={entOpts} placeholder="Pilih entitas" /></div>
          <div><label className="block text-[10.5px] font-semibold text-[#6B6B73] mb-1">Periode</label>
            <KNSelect data-testid="payroll-create-period" value={form.period} onValueChange={(v) => setForm((f) => ({ ...f, period: v }))} className="field" options={monthOpts} /></div>
          <button data-testid="payroll-create-submit" disabled={busy === "create"} onClick={createRun} className="primary-button justify-center"><Plus size={14} /> {busy === "create" ? "Memproses..." : "Buat / Hitung Run"}</button>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[300px_1fr]">
        {/* Daftar runs */}
        <div className="section-card">
          <div className="px-3 py-2 border-b border-[#EFF0F2] text-[11px] font-bold uppercase text-[#6B6B73]">Daftar Run</div>
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="payroll-runs-loading">Memuat...</div>
          ) : runs.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="payroll-runs-empty"><Calculator className="mx-auto mb-2 text-gray-300" size={26} /><p>Belum ada payroll run.</p></div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] max-h-[560px] overflow-y-auto">
              {runs.map((r) => {
                const st = RUN_STATUS[r.status] || RUN_STATUS.draft;
                return (
                  <button key={r.id} data-testid={`payroll-run-${r.id}`} onClick={() => openRun(r.id)}
                    className={`w-full text-left px-3 py-2.5 hover:bg-[#FAFBFC] ${sel?.id === r.id ? "bg-[#EEF4FF]" : ""}`}>
                    <div className="flex items-center justify-between"><span className="text-[12.5px] font-semibold">{r.number}</span><span className={`status-pill ${st.cls}`}>{st.label}</span></div>
                    <div className="flex items-center gap-2 mt-1 text-[11px] text-[#6B6B73]"><EntityBadge entityId={r.entity_id} /><span>{r.period}</span><span className="ml-auto tabular-nums">{rp(r.totals?.net)}</span></div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Detail run */}
        <div className="section-card">
          {!sel ? (
            <div className="py-16 text-center text-[12px] text-[#6B6B73]" data-testid="payroll-detail-empty"><FileText className="mx-auto mb-2 text-gray-300" size={28} /><p>Pilih run untuk melihat rincian payslip & alur persetujuan.</p></div>
          ) : (
            <div data-testid="payroll-run-detail">
              <div className="section-head">
                <div className="flex items-center gap-2"><h2>{sel.number} · {sel.period}</h2><span className={`status-pill ${(RUN_STATUS[sel.status] || RUN_STATUS.draft).cls}`} data-testid="payroll-detail-status">{(RUN_STATUS[sel.status] || RUN_STATUS.draft).label}</span></div>
                <div className="flex items-center gap-2">
                  {sel.status === "draft" && <button data-testid="payroll-submit" disabled={busy === "submit"} onClick={() => act(sel.id, "submit", "Ajukan")} className="primary-button !py-1.5"><Send size={13} /> Ajukan</button>}
                  {sel.status === "pending_approval" && <button data-testid="payroll-approve" disabled={busy === "approve"} onClick={() => act(sel.id, "approve", "Sahkan")} className="primary-button !py-1.5"><CheckCircle2 size={13} /> Sahkan</button>}
                  {sel.status === "pending_approval" && <button data-testid="payroll-reject" disabled={busy === "reject"} onClick={() => rejectRun(sel.id)} className="secondary-button !py-1.5"><Undo2 size={13} /> Kembalikan ke Draf</button>}
                  {sel.status === "approved" && <button data-testid="payroll-post-gl" disabled={busy === "post-gl"} onClick={() => act(sel.id, "post-gl", "Posting GL")} className="primary-button !py-1.5" style={{ background: "#B7791F" }}><BookCheck size={13} /> Posting GL</button>}
                  {sel.status === "posted" && <button data-testid="payroll-pay" disabled={busy === "pay"} onClick={() => act(sel.id, "pay", "Bayar")} className="primary-button !py-1.5" style={{ background: "#1F7A45" }}><Banknote size={13} /> Bayar</button>}
                </div>
              </div>
              <div className="section-body">
                <div className="grid gap-2 grid-cols-2 md:grid-cols-4 mb-3">
                  <Stat label="Karyawan" value={sel.totals?.employees ?? 0} />
                  <Stat label="Bruto" value={rp(sel.totals?.gross)} color="#0058CC" />
                  <Stat label="Potongan+Pajak" value={rp((sel.totals?.bpjs_emp || 0) + (sel.totals?.pph21 || 0))} color="#C0392B" />
                  <Stat label="Take-home (Net)" value={rp(sel.totals?.net)} color="#1F7A45" />
                </div>
                {sel.reject_reason && (
                  <div className="notice-bar warning !mb-3" data-testid="payroll-reject-reason">
                    <span><b>Dikembalikan ke draf</b>{sel.rejected_by ? ` oleh ${sel.rejected_by}` : ""}: {sel.reject_reason}</span>
                  </div>
                )}
                {(sel.journal_number || sel.paid_journal_number) && (
                  <div className="text-[11px] text-[#6B6B73] mb-2 flex flex-wrap gap-3">
                    {sel.journal_number && <span data-testid="payroll-journal-ref">Jurnal GL: <b className="text-[#0058CC]">{sel.journal_number}</b></span>}
                    {sel.paid_journal_number && <span data-testid="payroll-paid-ref">Jurnal Bayar: <b className="text-[#1F7A45]">{sel.paid_journal_number}</b></span>}
                  </div>
                )}
                <div className="overflow-x-auto border border-[#EFF0F2] rounded-lg">
                  <table className="w-full text-[11.5px] tabular-nums" data-testid="payroll-payslips-table">
                    <thead><tr className="bg-[#FAFBFC] text-[10px] uppercase text-[#6B6B73] text-right">
                      <th className="text-left px-2 py-1.5">Karyawan</th><th className="px-2">Pokok</th><th className="px-2">Tunj.</th><th className="px-2">Lembur</th><th className="px-2">Komisi</th><th className="px-2">Bruto</th><th className="px-2">BPJS</th><th className="px-2">PPh21</th><th className="px-2 pr-3">Net</th>
                    </tr></thead>
                    <tbody>
                      {(sel.payslips || []).map((s) => (
                        <tr key={s.id} data-testid={`payslip-${s.id}`} className="border-t border-[#EFF0F2] text-right hover:bg-[#FAFBFC]">
                          <td className="text-left px-2 py-1.5 font-semibold">{s.employee_name}<span className="text-[9.5px] text-[#9A9BA3] ml-1">TER-{s.ter_category}</span></td>
                          <td className="px-2 tabular-nums">{rp(s.base_salary)}</td><td className="px-2 tabular-nums">{rp(s.allowances)}</td><td className="px-2 tabular-nums">{rp(s.overtime)}</td><td className="px-2 tabular-nums">{rp(s.commission)}</td>
                          <td className="px-2 font-semibold text-[#0058CC] tabular-nums">{rp(s.gross)}</td><td className="px-2 text-[#C0392B] tabular-nums">{rp(s.bpjs_emp_total)}</td><td className="px-2 text-[#C0392B] tabular-nums">{rp(s.pph21)} <span className="text-[9px] text-[#9A9BA3]">{pct(s.pph21_rate)}</span></td>
                          <td className="px-2 pr-3 font-bold text-[#1F7A45] tabular-nums">{rp(s.net)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
