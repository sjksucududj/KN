import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Target, Plus, Pencil, Trash2, RefreshCw, BarChart3 } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import ConfirmModal from "../../components/ConfirmModal";
import { lastMonths, curMonth, scoreCls, scoreBadge, weightedAvg } from "./kpiUtils";

// FASE H5 — KPI Design (input KPI manual per karyawan/periode + rekap). Keputusan 2a.
export default function KpiView({ currentUser, selectedEntity }) {
  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState(curMonth());
  const [empFilter, setEmpFilter] = useState("");
  // modal
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blankForm());
  const [busy, setBusy] = useState(false);
  const [fErr, setFErr] = useState("");
  const [delTarget, setDelTarget] = useState(null);

  const params = useMemo(
    () => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}),
    [selectedEntity]
  );

  useEffect(() => { loadEmployees(); }, [selectedEntity]); // eslint-disable-line
  useEffect(() => { load(); }, [period, empFilter, selectedEntity]); // eslint-disable-line

  async function loadEmployees() {
    try {
      const r = await axios.get(`${API}/hr/employees`, { params });
      setEmployees(Array.isArray(r.data) ? r.data : []);
    } catch (_) { /* noop */ }
  }
  async function load() {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/hr/kpi`, {
        params: { ...params, ...(period ? { period } : {}), ...(empFilter ? { employee_id: empFilter } : {}) },
      });
      setRows(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat data KPI.");
    } finally {
      setLoading(false);
    }
  }

  function blankForm() {
    return { employee_id: "", period: curMonth(), metric: "", target: "", actual: "", score: "", weight: "1", note: "" };
  }
  function openCreate() { setEditing(null); setForm(blankForm()); setFErr(""); setOpen(true); }
  function openEdit(r) {
    setEditing(r);
    setForm({ employee_id: r.employee_id, period: r.period, metric: r.metric, target: String(r.target ?? ""), actual: String(r.actual ?? ""), score: "", weight: String(r.weight ?? "1"), note: r.note || "" });
    setFErr(""); setOpen(true);
  }

  async function save() {
    if (!editing && !form.employee_id) { setFErr("Pilih karyawan."); return; }
    if (!form.metric.trim()) { setFErr("Nama metrik wajib diisi."); return; }
    if (!/^\d{4}-\d{2}$/.test(form.period)) { setFErr("Periode harus format YYYY-MM."); return; }
    setBusy(true); setFErr("");
    const payload = {
      period: form.period, metric: form.metric.trim(),
      target: parseFloat(form.target) || 0, actual: parseFloat(form.actual) || 0,
      weight: parseFloat(form.weight) || 1, note: form.note,
    };
    if (form.score !== "" && !Number.isNaN(parseFloat(form.score))) payload.score = parseFloat(form.score);
    try {
      if (editing) await axios.put(`${API}/hr/kpi/${editing.id}`, payload);
      else await axios.post(`${API}/hr/kpi`, { ...payload, employee_id: form.employee_id });
      setOpen(false); await load();
    } catch (e) {
      setFErr(e.response?.data?.detail || "Gagal menyimpan KPI.");
    } finally { setBusy(false); }
  }
  async function doDelete(r) {
    try { await axios.delete(`${API}/hr/kpi/${r.id}`); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menghapus KPI."); }
    finally { setDelTarget(null); }
  }

  const periodOpts = lastMonths(12).map((m) => ({ value: m, label: m }));
  const empOpts = [{ value: "", label: "Semua Karyawan" }, ...employees.map((e) => ({ value: e.id, label: e.name }))];
  const avg = weightedAvg(rows);

  return (
    <div className="grid gap-3" data-testid="kpi-view">
      {/* Toolbar */}
      <section className="section-card !p-3">
        <div className="flex flex-wrap items-end gap-2.5">
          <div className="grid gap-1">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Periode</label>
            <KNSelect data-testid="kpi-period-filter" value={period} onValueChange={setPeriod} options={periodOpts} className="field !w-[150px]" />
          </div>
          <div className="grid gap-1">
            <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Karyawan</label>
            <KNSelect data-testid="kpi-emp-filter" value={empFilter} onValueChange={setEmpFilter} options={empOpts} className="field !w-[220px]" placeholder="Semua Karyawan" />
          </div>
          <button data-testid="kpi-refresh-button" className="secondary-button" onClick={load}><RefreshCw size={13} /> Muat ulang</button>
          <div className="ml-auto flex items-end gap-2">
            {canManage && (
              <button data-testid="kpi-add-button" className="primary-button" onClick={openCreate}><Plus size={14} /> Tambah KPI</button>
            )}
          </div>
        </div>
      </section>

      {/* Rekap */}
      <section className="grid gap-3 sm:grid-cols-3">
        <RecapCard icon={BarChart3} label="Total Entri KPI" value={rows.length} />
        <RecapCard icon={Target} label="Rata-rata Skor (tertimbang)" value={avg} valueCls={scoreCls(avg)} suffix="" />
        <RecapCard icon={Target} label="Periode Aktif" value={period || "—"} small />
      </section>

      {error && <ErrorNotice message={error} onRetry={load} testId="kpi-error" />}

      {/* Tabel */}
      <section className="section-card">
        <div className="section-head"><h2 className="text-[13px] font-bold">Daftar KPI</h2></div>
        <div className="section-body">
          {loading ? (
            <p className="text-[12px] text-[#6B6B73] py-6 text-center" data-testid="kpi-loading">Memuat data KPI…</p>
          ) : rows.length === 0 ? (
            <div className="py-10 text-center" data-testid="kpi-empty">
              <Target size={28} className="mx-auto text-[#C7C9CF] mb-2" />
              <p className="text-[13px] font-semibold text-[#3A3B42]">Belum ada data KPI</p>
              <p className="text-[12px] text-[#9A9BA3] mt-0.5">Tambahkan KPI karyawan untuk periode {period}.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]" data-testid="kpi-table">
                <thead>
                  <tr className="text-left text-[11px] uppercase text-[#9A9BA3] border-b border-[#EFF0F2]">
                    <th className="py-2 pr-3">Karyawan</th><th className="py-2 pr-3">Periode</th>
                    <th className="py-2 pr-3">Metrik</th>
                    <th className="py-2 pr-3 text-right">Target</th><th className="py-2 pr-3 text-right">Aktual</th>
                    <th className="py-2 pr-3 text-right">Skor</th><th className="py-2 pr-3 text-right">Bobot</th>
                    {canManage && <th className="py-2 pr-1 text-right">Aksi</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#F2F3F5]">
                  {rows.map((r) => {
                    const b = scoreBadge(r.score);
                    return (
                      <tr key={r.id} data-testid={`kpi-row-${r.id}`} className="hover:bg-[#FAFBFC]">
                        <td className="py-2 pr-3 font-medium">{r.employee_name}</td>
                        <td className="py-2 pr-3 tabular-nums">{r.period}</td>
                        <td className="py-2 pr-3">{r.metric}{r.note ? <span className="block text-[11px] text-[#9A9BA3] truncate max-w-[220px]">{r.note}</span> : null}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.target}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.actual}</td>
                        <td className="py-2 pr-3 text-right"><span className={`font-bold tabular-nums ${scoreCls(r.score)}`}>{r.score}</span> <span className={`ml-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${b.cls}`}>{b.label}</span></td>
                        <td className="py-2 pr-3 text-right tabular-nums">{r.weight}</td>
                        {canManage && (
                          <td className="py-2 pr-1 text-right whitespace-nowrap">
                            <button data-testid={`kpi-edit-${r.id}-button`} className="icon-button" title="Ubah" onClick={() => openEdit(r)}><Pencil size={14} /></button>
                            <button data-testid={`kpi-delete-${r.id}-button`} className="icon-button text-[#C0341D]" title="Hapus" onClick={() => setDelTarget(r)}><Trash2 size={14} /></button>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Modal create/edit */}
      {open && (
        <div className="modal-overlay" data-testid="kpi-modal" onClick={(e) => { if (e.target === e.currentTarget && !busy) setOpen(false); }}>
          <div className="modal-card">
            <p className="modal-title">{editing ? "Edit KPI" : "Tambah KPI"}</p>
            {fErr && <div className="notice-bar danger !mb-2 !py-1.5" data-testid="kpi-modal-error"><span className="text-[11.5px]">{fErr}</span></div>}
            <div className="grid gap-2.5">
              {!editing && (
                <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Karyawan *</label>
                  <KNSelect data-testid="kpi-form-employee" value={form.employee_id} onValueChange={(v) => setForm({ ...form, employee_id: v })} options={employees.map((e) => ({ value: e.id, label: e.name }))} className="field" placeholder="Pilih karyawan" searchable /></div>
              )}
              {editing && <p className="text-[12px] text-[#6B6B73]">Karyawan: <b>{editing.employee_name}</b></p>}
              <div className="grid grid-cols-2 gap-2">
                <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Periode *</label>
                  <KNSelect data-testid="kpi-form-period" value={form.period} onValueChange={(v) => setForm({ ...form, period: v })} options={periodOpts} className="field" /></div>
                <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Bobot</label>
                  <input data-testid="kpi-form-weight" type="number" step="0.5" min="0" className="form-input" value={form.weight} onChange={(e) => setForm({ ...form, weight: e.target.value })} /></div>
              </div>
              <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Metrik *</label>
                <input data-testid="kpi-form-metric" className="form-input" value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value })} placeholder="mis. Jumlah Desain Baru" /></div>
              <div className="grid grid-cols-3 gap-2">
                <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Target</label>
                  <input data-testid="kpi-form-target" type="number" step="any" className="form-input" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} /></div>
                <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Aktual</label>
                  <input data-testid="kpi-form-actual" type="number" step="any" className="form-input" value={form.actual} onChange={(e) => setForm({ ...form, actual: e.target.value })} /></div>
                <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Skor (opsional)</label>
                  <input data-testid="kpi-form-score" type="number" step="any" className="form-input" value={form.score} onChange={(e) => setForm({ ...form, score: e.target.value })} placeholder="auto" /></div>
              </div>
              <p className="text-[10.5px] text-[#9A9BA3]">Kosongkan skor untuk hitung otomatis: min(aktual/target, 1.5) × 100.</p>
              <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Catatan</label>
                <textarea data-testid="kpi-form-note" className="form-input" rows="2" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Opsional" /></div>
              <div className="modal-actions">
                <button className="btn-secondary" onClick={() => setOpen(false)} disabled={busy}>Batal</button>
                <button data-testid="kpi-form-submit" className="btn-primary" onClick={save} disabled={busy}>{busy ? "Menyimpan…" : editing ? "Simpan Perubahan" : "Simpan KPI"}</button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal open={!!delTarget} title="Hapus KPI?" message={delTarget ? `Hapus KPI "${delTarget.metric}" untuk ${delTarget.employee_name}?` : ""} confirmLabel="Hapus" danger onConfirm={() => doDelete(delTarget)} onCancel={() => setDelTarget(null)} testId="kpi-delete-modal" />
    </div>
  );
}

function RecapCard({ icon: Icon, label, value, valueCls = "", small = false }) {
  return (
    <div className="section-card !p-3 flex items-center gap-3">
      <div className="h-9 w-9 rounded-lg bg-[#EAF1FF] flex items-center justify-center shrink-0"><Icon size={17} className="text-[#0058CC]" /></div>
      <div className="min-w-0">
        <p className="text-[10.5px] uppercase font-semibold text-[#9A9BA3] truncate">{label}</p>
        <p className={`${small ? "text-[15px]" : "text-[20px]"} font-bold leading-tight tabular-nums ${valueCls}`}>{value}</p>
      </div>
    </div>
  );
}
