/**
 * OmnichannelInteractions (CRM Omnichannel) — timeline interaksi manual.
 * Channel: phone/email/whatsapp/meeting/chat/sms/other. Filter per pelanggan/channel.
 * Sumber: /api/crm/interactions. Gaya ikut CRM existing.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Plus, RefreshCw, X, Phone, Mail, MessageSquare, Users, MessageCircle,
  Smartphone, CircleDot, ArrowDownLeft, ArrowUpRight, CalendarClock, Trash2,
} from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import KNSelect from "../../components/KNSelect";
import { askConfirm } from "@/services/confirmService";

const CHANNELS = [
  { value: "phone", label: "Telepon", icon: Phone, color: "#0058CC" },
  { value: "email", label: "Email", icon: Mail, color: "#8A5A00" },
  { value: "whatsapp", label: "WhatsApp", icon: MessageSquare, color: "#1B7F4B" },
  { value: "meeting", label: "Meeting", icon: Users, color: "#6B219A" },
  { value: "chat", label: "Chat", icon: MessageCircle, color: "#0058CC" },
  { value: "sms", label: "SMS", icon: Smartphone, color: "#8A5A00" },
  { value: "other", label: "Lainnya", icon: CircleDot, color: "#6B6B73" },
];
const CH = Object.fromEntries(CHANNELS.map((c) => [c.value, c]));
const DIRECTIONS = [{ value: "outbound", label: "Keluar" }, { value: "inbound", label: "Masuk" }];

const entityParam = (e) => (e && e !== "all" ? { entity_id: e } : {});

function localNow() {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}
function fmtDateTime(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

export default function OmnichannelInteractions({ currentUser, selectedEntity }) {
  const [items, setItems] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fCustomer, setFCustomer] = useState("");
  const [fChannel, setFChannel] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = { ...entityParam(selectedEntity) };
      if (fCustomer) params.customer_id = fCustomer;
      if (fChannel) params.channel = fChannel;
      const r = await axios.get(`${API}/crm/interactions`, { params });
      setItems(Array.isArray(r.data) ? r.data : []);
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat interaksi."); }
    finally { setLoading(false); }
  }, [selectedEntity, fCustomer, fChannel]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    axios.get(`${API}/customers`, { params: { with_credit: false, ...entityParam(selectedEntity) } })
      .then((r) => setCustomers((r.data || []).map((c) => ({ value: c.id, label: c.name || c.code })))).catch(() => {});
  }, [selectedEntity]);

  const custOpts = useMemo(() => [{ value: "", label: "Semua Pelanggan" }, ...customers], [customers]);
  const chanFilterOpts = useMemo(() => [{ value: "", label: "Semua Channel" }, ...CHANNELS.map((c) => ({ value: c.value, label: c.label }))], []);

  const remove = async (it) => {
    const ok = await askConfirm({
      title: "Hapus catatan interaksi ini?",
      message: "Riwayat percakapan dengan pelanggan ini hilang dari daftar interaksi.",
      confirmLabel: "Hapus Interaksi",
      danger: true,
      testId: "interaction-delete-confirm",
    });
    if (!ok) return;
    setBusy(true); setError("");
    try { await axios.delete(`${API}/crm/interactions/${it.id}`); load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menghapus interaksi."); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid="omnichannel-interactions">
      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2"><MessageSquare size={15} className="text-[#6B219A]" />
            <h3 className="text-[13px] font-bold text-[#1C1C1E]">Timeline Interaksi (Omnichannel)</h3></div>
          <div className="flex items-center gap-2 ml-auto flex-wrap">
            <div className="w-[180px]"><KNSelect data-testid="intx-filter-customer" className="field py-1.5 text-[12px]" value={fCustomer} onValueChange={setFCustomer} options={custOpts} placeholder="Pelanggan" /></div>
            <div className="w-[150px]"><KNSelect data-testid="intx-filter-channel" className="field py-1.5 text-[12px]" value={fChannel} onValueChange={setFChannel} options={chanFilterOpts} placeholder="Channel" /></div>
            <button data-testid="intx-add-btn" className="btn-primary text-[12px] py-1.5 px-3 inline-flex items-center gap-1" onClick={() => setShowForm(true)}><Plus size={13} /> Catat Interaksi</button>
            <button data-testid="intx-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="intx-error" />
          {loading ? (
            <div className="space-y-2" data-testid="intx-loading">{[0, 1, 2, 3].map((i) => <div key={i} className="h-16 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
          ) : items.length === 0 ? (
            <div data-testid="intx-empty" className="py-12 text-center text-[12px] text-[#8E8E93]">
              <MessageSquare size={26} className="mx-auto mb-2 text-gray-300" />Belum ada interaksi tercatat. Klik "Catat Interaksi".
            </div>
          ) : (
            <ol className="relative border-l-2 border-[#EFF0F2] ml-3 space-y-3" data-testid="intx-feed">
              {items.map((it) => {
                const ch = CH[it.channel] || CH.other;
                const Icon = ch.icon;
                const inbound = it.direction === "inbound";
                return (
                  <li key={it.id} data-testid={`intx-item-${it.id}`} className="ml-5 relative">
                    <span className="absolute -left-[30px] top-1 w-6 h-6 rounded-full flex items-center justify-center" style={{ background: `${ch.color}1A` }}>
                      <Icon size={13} style={{ color: ch.color }} />
                    </span>
                    <div className="rounded-md border border-[#EFF0F2] bg-white p-2.5">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] font-bold rounded-full px-1.5 py-0.5" style={{ background: `${ch.color}1A`, color: ch.color }}>{ch.label}</span>
                        <span className={`text-[10px] font-semibold rounded-full px-1.5 py-0.5 inline-flex items-center gap-0.5 ${inbound ? "bg-[#E7F0FF] text-[#0058CC]" : "bg-[#E6F6EC] text-[#1B7F4B]"}`}>
                          {inbound ? <ArrowDownLeft size={10} /> : <ArrowUpRight size={10} />}{inbound ? "Masuk" : "Keluar"}
                        </span>
                        {it.customer_name && <span className="text-[11px] font-semibold text-[#1C1C1E]">{it.customer_name}</span>}
                        <span className="text-[10px] text-[#9A9BA3] ml-auto">{fmtDateTime(it.occurred_at)}</span>
                        <button data-testid={`intx-del-${it.id}`} className="text-[#C9C9CE] hover:text-[#C0392B]" onClick={() => remove(it)} disabled={busy} aria-label="Hapus"><Trash2 size={12} /></button>
                      </div>
                      {it.subject && <p className="text-[12px] font-semibold text-[#1C1C1E] mt-1">{it.subject}</p>}
                      {it.notes && <p className="text-[11px] text-[#6B6B73] mt-0.5 whitespace-pre-wrap">{it.notes}</p>}
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-[#9A9BA3]">oleh {it.created_by}</span>
                        {it.follow_up_date && <span className="text-[10px] text-[#8A5A00] inline-flex items-center gap-0.5"><CalendarClock size={10} /> Tindak lanjut {fmtDateTime(it.follow_up_date)}</span>}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>

      {showForm && (
        <InteractionForm customers={customers} selectedEntity={selectedEntity}
          onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); }} setError={setError} />
      )}
    </div>
  );
}

function InteractionForm({ customers, selectedEntity, onClose, onSaved, setError }) {
  const [form, setForm] = useState({
    channel: "whatsapp", direction: "outbound", customer_id: "", subject: "", notes: "",
    occurred_at: localNow(), follow_up_date: "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const custOpts = [{ value: "", label: "— (Tanpa pelanggan)" }, ...customers];

  const save = async () => {
    if (!form.subject.trim() && !form.notes.trim()) { setError("Isi subjek atau catatan interaksi."); return; }
    setSaving(true); setError("");
    try {
      const body = { ...form };
      if (body.occurred_at) body.occurred_at = new Date(body.occurred_at).toISOString();
      if (body.follow_up_date) body.follow_up_date = new Date(body.follow_up_date).toISOString();
      else body.follow_up_date = null;
      await axios.post(`${API}/crm/interactions`, { ...body, ...entityParam(selectedEntity) });
      onSaved();
    } catch (e) { setError(e.response?.data?.detail || "Gagal menyimpan interaksi."); setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="intx-modal">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2]">
          <h3 className="text-[14px] font-bold text-[#1C1C1E]">Catat Interaksi</h3>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3 overflow-y-auto">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Channel"><KNSelect data-testid="intx-form-channel" className="field" value={form.channel} onValueChange={(v) => set("channel", v)} options={CHANNELS.map((c) => ({ value: c.value, label: c.label }))} /></Field>
            <Field label="Arah"><KNSelect data-testid="intx-form-direction" className="field" value={form.direction} onValueChange={(v) => set("direction", v)} options={DIRECTIONS} /></Field>
          </div>
          <Field label="Pelanggan (opsional)"><KNSelect data-testid="intx-form-customer" className="field" value={form.customer_id} onValueChange={(v) => set("customer_id", v)} options={custOpts} /></Field>
          <Field label="Subjek"><input data-testid="intx-form-subject" className="field" value={form.subject} onChange={(e) => set("subject", e.target.value)} placeholder="mis. Follow-up penawaran" /></Field>
          <Field label="Catatan"><textarea data-testid="intx-form-notes" className="field min-h-[72px]" value={form.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Waktu Interaksi"><input data-testid="intx-form-occurred" type="datetime-local" className="field" value={form.occurred_at} onChange={(e) => set("occurred_at", e.target.value)} /></Field>
            <Field label="Tindak Lanjut (opsional)"><input data-testid="intx-form-followup" type="datetime-local" className="field" value={form.follow_up_date} onChange={(e) => set("follow_up_date", e.target.value)} /></Field>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#EFF0F2]">
          <button className="btn-secondary text-[12px] py-1.5 px-3" onClick={onClose}>Batal</button>
          <button data-testid="intx-form-save" className="btn-primary text-[12px] py-1.5 px-4" onClick={save} disabled={saving}>{saving ? "Menyimpan…" : "Simpan"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (<label className="block"><span className="text-[10px] font-bold uppercase tracking-wide text-[#8E8E93] block mb-1">{label}</span>{children}</label>);
}
