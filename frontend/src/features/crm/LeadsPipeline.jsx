/**
 * LeadsPipeline (CRM Omnichannel) — Kanban pipeline lead.
 * Stage: Baru → Kualifikasi → Penawaran → Menang → Kalah. Pencatatan manual.
 * Sumber: /api/crm/leads(/board), /api/crm/pipeline-stats. Gaya ikut CRM existing.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Plus, RefreshCw, Target, TrendingUp, Trophy, Percent, Wallet, Pencil, Trash2,
  UserPlus, X, MessageSquare, Phone, Mail, Instagram, Globe, Users,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { formatCurrency } from "../../utils/formatters";
import { askConfirm } from "@/services/confirmService";

const STAGES = [
  { key: "new", label: "Baru", accent: "#0058CC", bg: "#E7F0FF" },
  { key: "qualified", label: "Kualifikasi", accent: "#8A5A00", bg: "#FDF3E7" },
  { key: "proposal", label: "Penawaran", accent: "#6B219A", bg: "#F3EAFB" },
  { key: "won", label: "Menang", accent: "#1B7F4B", bg: "#E6F6EC" },
  { key: "lost", label: "Kalah", accent: "#C0392B", bg: "#FDEDE7" },
];
const STAGE_OPTS = STAGES.map((s) => ({ value: s.key, label: s.label }));
const SOURCES = [
  { value: "whatsapp", label: "WhatsApp" }, { value: "instagram", label: "Instagram" },
  { value: "email", label: "Email" }, { value: "phone", label: "Telepon" },
  { value: "walk_in", label: "Walk-in" }, { value: "referral", label: "Referral" },
  { value: "web", label: "Website" }, { value: "other", label: "Lainnya" },
];
const SOURCE_LABEL = Object.fromEntries(SOURCES.map((s) => [s.value, s.label]));

const entityParam = (e) => (e && e !== "all" ? { entity_id: e } : {});

export default function LeadsPipeline({ currentUser, selectedEntity }) {
  const [board, setBoard] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [salesUsers, setSalesUsers] = useState([]);
  const [modal, setModal] = useState(null); // {mode:'create'|'edit', lead}
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [b, s] = await Promise.all([
        axios.get(`${API}/crm/leads/board`, { params: { ...entityParam(selectedEntity) } }),
        axios.get(`${API}/crm/pipeline-stats`, { params: { ...entityParam(selectedEntity) } }),
      ]);
      setBoard(b.data); setStats(s.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat pipeline lead.");
    } finally { setLoading(false); }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    axios.get(`${API}/sales-users`).then((r) => setSalesUsers(r.data || [])).catch(() => {});
  }, []);

  const moveStage = async (lead, stage) => {
    if (stage === lead.stage) return;
    setBusy(true); setError("");
    try {
      await axios.patch(`${API}/crm/leads/${lead.id}`, { stage });
      load();
    } catch (e) { setError(e.response?.data?.detail || "Gagal memindahkan stage."); }
    finally { setBusy(false); }
  };

  const removeLead = async (lead) => {
    const ok = await askConfirm({
      title: `Hapus lead "${lead.name}"?`,
      message: "Calon pelanggan ini dan catatan tahapannya dihapus dari papan pipeline.",
      confirmLabel: "Hapus Lead",
      danger: true,
      testId: "lead-delete-confirm",
    });
    if (!ok) return;
    setBusy(true); setError("");
    try { await axios.delete(`${API}/crm/leads/${lead.id}`); setNotice("Lead dihapus."); load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menghapus lead."); }
    finally { setBusy(false); }
  };

  const convertLead = async (lead) => {
    const ok = await askConfirm({
      title: `Konversi lead "${lead.name}" menjadi pelanggan?`,
      message: "Pelanggan baru dibuat dari data lead ini sehingga bisa langsung dipakai membuat pesanan.",
      confirmLabel: "Konversi Sekarang",
      testId: "lead-convert-confirm",
    });
    if (!ok) return;
    setBusy(true); setError("");
    try {
      const r = await axios.post(`${API}/crm/leads/${lead.id}/convert`, {});
      setNotice(`Lead dikonversi menjadi pelanggan (ID ${r.data.customer_id}).`);
      load();
    } catch (e) { setError(e.response?.data?.detail || "Gagal konversi lead."); }
    finally { setBusy(false); }
  };

  const columns = board?.columns || [];

  return (
    <div data-testid="leads-pipeline">
      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <Kpi testId="lead-kpi-open" label="Lead Aktif" value={stats?.open_count ?? 0} icon={Target} />
        <Kpi testId="lead-kpi-openval" label="Nilai Pipeline Aktif" value={formatCurrency(stats?.open_value)} icon={Wallet} tone="text-[#0058CC]" />
        <Kpi testId="lead-kpi-win" label="Win Rate" value={`${Number(stats?.win_rate ?? 0).toFixed(1)}%`} icon={Percent} tone="text-[#1B7F4B]" />
        <Kpi testId="lead-kpi-wonval" label="Nilai Menang" value={formatCurrency(stats?.won_value)} icon={Trophy} tone="text-[#1B7F4B]" />
      </div>

      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2"><TrendingUp size={15} className="text-[#6B219A]" />
            <h3 className="text-[13px] font-bold text-[#1C1C1E]">Pipeline Lead</h3></div>
          <div className="flex items-center gap-2 ml-auto">
            <button data-testid="lead-add-btn" className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1"
              onClick={() => setModal({ mode: "create", lead: null })}><Plus size={13} /> Tambah Lead</button>
            <button data-testid="lead-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="lead-error" />
          {notice && (
            <div data-testid="lead-notice" className="mb-3 rounded-md bg-[#E6F6EC] border border-[#BDE5CC] text-[#1B7F4B] text-[12px] px-3 py-2 flex items-center gap-2">
              {notice}<button className="ml-auto" onClick={() => setNotice("")} aria-label="Tutup"><X size={13} /></button>
            </div>
          )}

          {loading ? (
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="lead-loading">
              {STAGES.map((s) => <div key={s.key} className="h-64 bg-[#F5F5F7] rounded animate-pulse" />)}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-5 gap-3" data-testid="lead-board">
              {columns.map((col) => {
                const meta = STAGES.find((s) => s.key === col.stage) || STAGES[0];
                return (
                  <div key={col.stage} data-testid={`lead-col-${col.stage}`} className="rounded-lg border border-[#EFF0F2] bg-[#FCFCFD] flex flex-col min-h-[200px]">
                    <div className="px-3 py-2 border-b border-[#EFF0F2] rounded-t-lg" style={{ background: meta.bg }}>
                      <div className="flex items-center justify-between">
                        <span className="text-[12px] font-bold" style={{ color: meta.accent }}>{col.label}</span>
                        <span className="text-[10px] font-bold rounded-full px-2 py-0.5 bg-white" style={{ color: meta.accent }} data-testid={`lead-col-${col.stage}-count`}>{col.count}</span>
                      </div>
                      <p className="text-[10px] text-[#6B6B73] mt-0.5 tabular-nums">{formatCurrency(col.total_value)}</p>
                    </div>
                    <div className="p-2 space-y-2 flex-1">
                      {col.leads.length === 0 ? (
                        <p data-testid={`lead-col-empty-${col.stage || col.key || ""}`}
                          className="text-[11px] text-[#9A9BA3] text-center py-4">
                          Belum ada lead di tahap ini.
                        </p>
                      ) : col.leads.map((lead) => (
                        <div key={lead.id} data-testid={`lead-card-${lead.id}`} className="rounded-md border border-[#EFF0F2] bg-white p-2.5 shadow-sm">
                          <div className="flex items-start justify-between gap-1">
                            <p className="text-[12px] font-bold text-[#1C1C1E] leading-tight">{lead.name}</p>
                            <div className="flex items-center gap-1 shrink-0">
                              <button data-testid={`lead-edit-${lead.id}`} className="text-[#8E8E93] hover:text-[#6B219A]" onClick={() => setModal({ mode: "edit", lead })} aria-label="Ubah"><Pencil size={12} /></button>
                              <button data-testid={`lead-del-${lead.id}`} className="text-[#8E8E93] hover:text-[#C0392B]" onClick={() => removeLead(lead)} aria-label="Hapus"><Trash2 size={12} /></button>
                            </div>
                          </div>
                          {lead.company && <p className="text-[11px] text-[#6B6B73]">{lead.company}</p>}
                          <p className="text-[12px] font-semibold text-[#0058CC] tabular-nums mt-1">{formatCurrency(lead.est_value)}</p>
                          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                            <span className="text-[9px] font-bold rounded-full px-1.5 py-0.5 bg-[#F3EAFB] text-[#6B219A]">{SOURCE_LABEL[lead.source] || lead.source}</span>
                            {lead.owner_name && <span className="text-[9px] text-[#9A9BA3] inline-flex items-center gap-0.5"><Users size={9} />{lead.owner_name}</span>}
                          </div>
                          <div className="mt-2 flex items-center gap-1">
                            <KNSelect data-testid={`lead-stage-${lead.id}`} className="field !py-1 text-[11px] flex-1" value={lead.stage}
                              onValueChange={(v) => moveStage(lead, v)} options={STAGE_OPTS} />
                            {!lead.customer_id && (
                              <button data-testid={`lead-convert-${lead.id}`} title="Konversi ke Pelanggan" className="icon-button !w-7 !h-7 text-[#1B7F4B]" onClick={() => convertLead(lead)} disabled={busy}><UserPlus size={13} /></button>
                            )}
                          </div>
                          {lead.customer_id && <p className="text-[9px] text-[#1B7F4B] mt-1 font-semibold">✓ Sudah jadi pelanggan</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {modal && (
        <LeadModal mode={modal.mode} lead={modal.lead} salesUsers={salesUsers} selectedEntity={selectedEntity}
          onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} setError={setError} />
      )}
    </div>
  );
}

function LeadModal({ mode, lead, salesUsers, selectedEntity, onClose, onSaved, setError }) {
  const [form, setForm] = useState({
    name: lead?.name || "", company: lead?.company || "", phone: lead?.phone || "",
    email: lead?.email || "", source: lead?.source || "whatsapp", stage: lead?.stage || "new",
    est_value: lead?.est_value || 0, owner_id: lead?.owner_id || "", notes: lead?.notes || "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const ownerOpts = [{ value: "", label: "— (Saya)" }, ...salesUsers.map((u) => ({ value: u.id, label: u.name }))];

  const save = async () => {
    if (!form.name.trim()) { setError("Nama lead wajib diisi."); return; }
    setSaving(true); setError("");
    try {
      const body = { ...form, est_value: Number(form.est_value) || 0 };
      if (mode === "create") {
        await axios.post(`${API}/crm/leads`, { ...body, ...entityParam(selectedEntity) });
      } else {
        await axios.patch(`${API}/crm/leads/${lead.id}`, body);
      }
      onSaved();
    } catch (e) { setError(e.response?.data?.detail || "Gagal menyimpan lead."); setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="lead-modal">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2]">
          <h3 className="text-[14px] font-bold text-[#1C1C1E]">{mode === "create" ? "Tambah Lead" : "Ubah Lead"}</h3>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3 overflow-y-auto">
          <Field label="Nama Kontak *"><input data-testid="lead-form-name" className="field" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="mis. Bu Rina" /></Field>
          <Field label="Perusahaan"><input data-testid="lead-form-company" className="field" value={form.company} onChange={(e) => set("company", e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Telepon"><input data-testid="lead-form-phone" className="field" value={form.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
            <Field label="Email"><input data-testid="lead-form-email" className="field" value={form.email} onChange={(e) => set("email", e.target.value)} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Sumber Channel"><KNSelect data-testid="lead-form-source" className="field" value={form.source} onValueChange={(v) => set("source", v)} options={SOURCES} /></Field>
            <Field label="Stage"><KNSelect data-testid="lead-form-stage" className="field" value={form.stage} onValueChange={(v) => set("stage", v)} options={STAGE_OPTS} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Estimasi Nilai (Rp)"><input data-testid="lead-form-value" type="number" className="field tabular-nums" value={form.est_value} onChange={(e) => set("est_value", e.target.value)} /></Field>
            <Field label="Pemilik (Sales)"><KNSelect data-testid="lead-form-owner" className="field" value={form.owner_id} onValueChange={(v) => set("owner_id", v)} options={ownerOpts} /></Field>
          </div>
          <Field label="Catatan"><textarea data-testid="lead-form-notes" className="field min-h-[64px]" value={form.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
        </div>
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2]">
          <button className="btn-secondary text-[12px] py-1.5 px-3" onClick={onClose}>Batal</button>
          <button data-testid="lead-form-save" className="btn-primary text-[12px] py-1.5 px-4" onClick={save} disabled={saving}>{saving ? "Menyimpan…" : "Simpan"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (<label className="block"><span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93] block mb-1">{label}</span>{children}</label>);
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
