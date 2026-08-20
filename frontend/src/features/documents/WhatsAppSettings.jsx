// WhatsAppSettings — panel pengaturan integrasi WhatsApp + aturan auto-kirim (admin/manager).
import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import { Switch } from "@/components/ui/switch";
import { X, Save, Loader2, MessageCircle, Settings2, Zap } from "lucide-react";
import WhatsAppRules from "./WhatsAppRules";

export default function WhatsAppSettings({ open, onClose }) {
  const [s, setS] = useState(null);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("settings");
  const [docTypes, setDocTypes] = useState([]);

  useEffect(() => {
    if (open) {
      setMsg(""); setErr(""); setToken(""); setTab("settings");
      axios.get(`${API}/deliveries/whatsapp/settings`).then((r) => setS(r.data)).catch(() => setErr("Gagal memuat pengaturan."));
      axios.get(`${API}/pdf/doc-types`).then((r) => setDocTypes(r.data || [])).catch(() => {});
    }
  }, [open]);

  const patch = (k, v) => setS((prev) => ({ ...(prev || {}), [k]: v }));

  const save = async () => {
    setBusy(true); setErr(""); setMsg("");
    try {
      const payload = {
        provider: s.provider, simulate: s.simulate, enabled: s.enabled,
        phone_number_id: s.phone_number_id, default_country_code: s.default_country_code,
        sender_label: s.sender_label,
      };
      if (token.trim()) payload.access_token = token.trim();
      const r = await axios.put(`${API}/deliveries/whatsapp/settings`, payload);
      setS(r.data); setToken(""); setMsg("Pengaturan tersimpan.");
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan."); }
    finally { setBusy(false); }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4" data-testid="wa-settings-modal"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-[480px] overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#EDEEF1] px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#E7F8EE] text-[#1F7A45]"><MessageCircle size={16} /></span>
            <h3 className="text-[14px] font-bold">Pengaturan WhatsApp</h3>
          </div>
          <button onClick={onClose} className="relative z-[1] text-[#9A9BA3] hover:text-[#1a1a1a]" data-testid="wa-settings-close"><X size={18} /></button>
        </div>
        {/* Tabs */}
        <div className="flex gap-1 border-b border-[#EDEEF1] px-3 pt-2">
          <TabBtn active={tab === "settings"} onClick={() => setTab("settings")} icon={<Settings2 size={13} />} label="Koneksi" testId="wa-tab-settings" />
          <TabBtn active={tab === "rules"} onClick={() => setTab("rules")} icon={<Zap size={13} />} label="Aturan Auto-Kirim" testId="wa-tab-rules" />
        </div>
        <div className="max-h-[72vh] overflow-y-auto px-5 py-4">
          {tab === "rules" ? (
            <WhatsAppRules docTypes={docTypes} />
          ) : !s ? (
            <div className="flex justify-center py-8"><Loader2 size={22} className="animate-spin text-[#0058CC]" /></div>
          ) : (
            <div className="grid gap-3">
              {err && <div className="notice-bar danger !py-1.5"><span className="text-[11.5px]">{err}</span></div>}
              {msg && <div className="notice-bar success !py-1.5"><span className="text-[11.5px]">{msg}</span></div>}
              <label className="flex items-center justify-between gap-3 rounded-lg border border-[#EDEEF1] px-3 py-2">
                <span className="text-[12.5px] font-medium">Mode simulasi (tidak kirim nyata)</span>
                <Switch checked={!!s.simulate} onCheckedChange={(v) => patch("simulate", v)} data-testid="wa-set-simulate" />
              </label>
              <label className="flex items-center justify-between gap-3 rounded-lg border border-[#EDEEF1] px-3 py-2">
                <span className="text-[12.5px] font-medium">Integrasi aktif</span>
                <Switch checked={!!s.enabled} onCheckedChange={(v) => patch("enabled", v)} data-testid="wa-set-enabled" />
              </label>
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Provider</label>
                <KNSelect value={s.provider} onValueChange={(v) => patch("provider", v)}
                  options={(s.available_providers || ["simulated"]).map((p) => ({ value: p, label: p === "simulated" ? "Simulasi" : "Meta WhatsApp Cloud" }))}
                  className="field" data-testid="wa-set-provider" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="grid gap-1">
                  <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Kode Negara</label>
                  <input className="form-input" value={s.default_country_code || ""} onChange={(e) => patch("default_country_code", e.target.value)} data-testid="wa-set-cc" />
                </div>
                <div className="grid gap-1">
                  <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Label Pengirim</label>
                  <input className="form-input" value={s.sender_label || ""} onChange={(e) => patch("sender_label", e.target.value)} data-testid="wa-set-label" />
                </div>
              </div>
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Phone Number ID (Meta)</label>
                <input className="form-input" value={s.phone_number_id || ""} onChange={(e) => patch("phone_number_id", e.target.value)} placeholder="opsional (mode nyata)" data-testid="wa-set-pnid" />
              </div>
              <div className="grid gap-1">
                <label className="text-[11px] font-bold uppercase tracking-[0.03em] text-[#6B6B73]">Access Token {s.has_token && <span className="text-[#1F7A45]">(tersimpan)</span>}</label>
                <input className="form-input" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={s.has_token ? "•••• (isi untuk mengganti)" : "opsional (mode nyata)"} data-testid="wa-set-token" />
              </div>
              <button className="btn-primary flex items-center justify-center gap-2" onClick={save} disabled={busy} data-testid="wa-set-save">
                {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Simpan Pengaturan
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TabBtn({ active, onClick, icon, label, testId }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId}
      className={`flex items-center gap-1.5 rounded-t-lg px-3 py-2 text-[12px] font-semibold transition-colors ${
        active ? "border-b-2 border-[#1F7A45] text-[#1F7A45]" : "text-[#6B6B73] hover:text-[#1a1a1a]"}`}>
      {icon} {label}
    </button>
  );
}
