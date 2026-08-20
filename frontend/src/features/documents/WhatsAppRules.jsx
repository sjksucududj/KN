// WhatsAppRules — kelola aturan auto-kirim dokumen via WhatsApp (admin/manager).
// Aturan: (jenis dokumen + pemicu) → penerima (pelanggan/pemasok/nomor tetap) + caption.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import { Switch } from "@/components/ui/switch";
import { Plus, Trash2, Loader2, Zap, Save, X, Info } from "lucide-react";

const EVENT_OPTIONS = [
  { value: "created", label: "Dibuat" },
  { value: "approved", label: "Disetujui" },
  { value: "confirmed", label: "Dikonfirmasi" },
  { value: "issued", label: "Diterbitkan" },
  { value: "shipped", label: "Dikirim" },
  { value: "done", label: "Selesai" },
];
const MODE_OPTIONS = [
  { value: "customer", label: "Pelanggan (otomatis)" },
  { value: "supplier", label: "Pemasok (otomatis)" },
  { value: "fixed", label: "Nomor tetap" },
];
const eventLabel = (v) => EVENT_OPTIONS.find((e) => e.value === v)?.label || v;
const modeLabel = (v) => MODE_OPTIONS.find((m) => m.value === v)?.label || v;
const emptyDraft = { doc_type: "", event: "confirmed", recipient_mode: "customer", fixed_number: "", caption_template: "", enabled: true };

export default function WhatsAppRules({ docTypes = [] }) {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const [busy, setBusy] = useState(false);

  const docTypeOptions = useMemo(() => docTypes.map((d) => ({ value: d.doc_type, label: d.label })), [docTypes]);
  const docLabel = useCallback((dt) => docTypes.find((d) => d.doc_type === dt)?.label || dt, [docTypes]);

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const r = await axios.get(`${API}/deliveries/whatsapp/rules`);
      setRules(r.data.rules || []);
    } catch (e) { setErr("Gagal memuat aturan."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Tutup form dengan tombol Escape.
  useEffect(() => {
    if (!showForm) return;
    const onKey = (e) => { if (e.key === "Escape") setShowForm(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showForm]);

  const openNew = () => {
    setDraft({ ...emptyDraft, doc_type: docTypes[0]?.doc_type || "" });
    setMsg(""); setErr(""); setShowForm(true);
  };

  const save = async () => {
    setBusy(true); setErr(""); setMsg("");
    try {
      await axios.post(`${API}/deliveries/whatsapp/rules`, draft);
      setShowForm(false); setMsg("Aturan ditambahkan.");
      load();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan aturan."); }
    finally { setBusy(false); }
  };

  const toggle = async (rule) => {
    try {
      await axios.put(`${API}/deliveries/whatsapp/rules/${rule.id}`, { enabled: !rule.enabled });
      setRules((prev) => prev.map((r) => (r.id === rule.id ? { ...r, enabled: !r.enabled } : r)));
    } catch (e) { setErr("Gagal memperbarui aturan."); }
  };

  const remove = async (rule) => {
    try {
      await axios.delete(`${API}/deliveries/whatsapp/rules/${rule.id}`);
      setRules((prev) => prev.filter((r) => r.id !== rule.id));
    } catch (e) { setErr("Gagal menghapus aturan."); }
  };

  return (
    <div className="grid gap-3" data-testid="wa-rules">
      <div className="flex items-start gap-2 rounded-lg bg-[#EAF2FF] px-3 py-2 text-[11.5px] text-[#0058CC]">
        <Info size={14} className="mt-0.5 shrink-0" />
        <span>Pemicu aktif: <b>Pesanan Penjualan</b> (disetujui, dikonfirmasi) & <b>Kwitansi AR</b> (dibuat).
          Aturan untuk pemicu lain tersimpan dan otomatis berlaku saat modul terkait terhubung.</span>
      </div>
      {err && <div className="notice-bar danger !py-1.5"><span className="text-[11.5px]">{err}</span></div>}
      {msg && <div className="notice-bar success !py-1.5"><span className="text-[11.5px]">{msg}</span></div>}

      <div className="flex items-center justify-between">
        <p className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Aturan ({rules.length})</p>
        <button className="btn-secondary flex items-center gap-1.5 !py-1" onClick={openNew} data-testid="wa-rule-add">
          <Plus size={14} /> Tambah Aturan
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-6"><Loader2 size={20} className="animate-spin text-[#0058CC]" /></div>
      ) : rules.length === 0 ? (
        <div className="rounded-lg border border-dashed border-[#E5E6EB] py-8 text-center">
          <Zap size={22} className="mx-auto text-[#C4C5CC]" />
          <p className="mt-1 text-[12px] font-semibold text-[#6B6B73]">Belum ada aturan auto-kirim</p>
          <p className="text-[11px] text-[#9A9BA3]">Buat aturan agar dokumen terkirim otomatis saat status berubah.</p>
        </div>
      ) : (
        <div className="grid gap-1.5" data-testid="wa-rule-list">
          {rules.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-2 rounded-lg border border-[#EDEEF1] px-3 py-2" data-testid={`wa-rule-${r.id}`}>
              <div className="min-w-0">
                <p className="text-[12.5px] font-semibold text-[#0B1B3B]">
                  {docLabel(r.doc_type)} <span className="text-[#9A9BA3]">·</span> {eventLabel(r.event)}
                </p>
                <p className="truncate text-[11px] text-[#6B6B73]">
                  Ke: {modeLabel(r.recipient_mode)}{r.recipient_mode === "fixed" && r.fixed_number ? ` (${r.fixed_number})` : ""}
                  {r.caption_template ? ` · "${r.caption_template}"` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={!!r.enabled} onCheckedChange={() => toggle(r)} data-testid={`wa-rule-toggle-${r.id}`} />
                <button className="flex h-7 w-7 items-center justify-center rounded-md border border-[#F3D0CB] text-[#C0392B] hover:bg-[#FDECEA]"
                  title="Hapus" onClick={() => remove(r)} data-testid={`wa-rule-del-${r.id}`}><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form tambah aturan */}
      {showForm && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/45 p-4" data-testid="wa-rule-form"
          onClick={(e) => { if (e.target === e.currentTarget) setShowForm(false); }}>
          <div className="w-full max-w-[440px] overflow-hidden rounded-2xl bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#EDEEF1] px-5 py-3">
              <h3 className="text-[13.5px] font-bold">Aturan Auto-Kirim Baru</h3>
              <button onClick={() => setShowForm(false)} className="relative z-[1] text-[#9A9BA3] hover:text-[#1a1a1a]" data-testid="wa-rule-form-close"><X size={17} /></button>
            </div>
            <div className="grid gap-3 px-5 py-4">
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Jenis Dokumen</label>
                <KNSelect value={draft.doc_type} onValueChange={(v) => setDraft((d) => ({ ...d, doc_type: v }))}
                  options={docTypeOptions} className="field" searchable placeholder="Pilih dokumen…" data-testid="wa-rule-doctype" />
              </div>
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Pemicu (Event)</label>
                <KNSelect value={draft.event} onValueChange={(v) => setDraft((d) => ({ ...d, event: v }))}
                  options={EVENT_OPTIONS} className="field" data-testid="wa-rule-event" />
              </div>
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Penerima</label>
                <KNSelect value={draft.recipient_mode} onValueChange={(v) => setDraft((d) => ({ ...d, recipient_mode: v }))}
                  options={MODE_OPTIONS} className="field" data-testid="wa-rule-mode" />
              </div>
              {draft.recipient_mode === "fixed" && (
                <div className="grid gap-1">
                  <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Nomor Tetap</label>
                  <input className="form-input" value={draft.fixed_number} placeholder="08xxx atau 62xxx"
                    onChange={(e) => setDraft((d) => ({ ...d, fixed_number: e.target.value }))} data-testid="wa-rule-fixed" />
                </div>
              )}
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Template Caption (opsional)</label>
                <input className="form-input" value={draft.caption_template} placeholder="Cth: {label} {number} — mohon dicek"
                  onChange={(e) => setDraft((d) => ({ ...d, caption_template: e.target.value }))} data-testid="wa-rule-caption" />
                <span className="text-[10.5px] text-[#9A9BA3]">Placeholder: {"{number}"}, {"{label}"}</span>
              </div>
              <label className="flex items-center justify-between gap-3 rounded-lg border border-[#EDEEF1] px-3 py-2">
                <span className="text-[12.5px] font-medium">Aktifkan aturan</span>
                <Switch checked={!!draft.enabled} onCheckedChange={(v) => setDraft((d) => ({ ...d, enabled: v }))} data-testid="wa-rule-enabled" />
              </label>
              <button className="btn-primary flex items-center justify-center gap-2" onClick={save} disabled={busy || !draft.doc_type} data-testid="wa-rule-save">
                {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Simpan Aturan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
