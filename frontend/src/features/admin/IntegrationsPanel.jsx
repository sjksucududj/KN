import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Sparkles, KeyRound, CheckCircle2, AlertCircle } from "lucide-react";
import KNSelect from "../../components/KNSelect";

// FASE H5 — Panel Integrasi AI (Anthropic Claude). Admin only. Keputusan 1a.
// Key TIDAK pernah ditampilkan plaintext — hanya status has_key.
export default function IntegrationsPanel() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("claude-sonnet-4-6");
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { load(); }, []); // eslint-disable-line
  async function load() {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/integrations`);
      const a = r.data?.anthropic || {};
      setCfg(a); setModel(a.model || "claude-sonnet-4-6"); setEnabled(!!a.enabled); setApiKey("");
    } catch (e) { setErr(e.response?.data?.detail || "Gagal memuat konfigurasi."); }
    finally { setLoading(false); }
  }

  async function save({ clear = false } = {}) {
    setBusy(true); setErr(""); setMsg("");
    const payload = { anthropic_model: model, anthropic_enabled: enabled };
    if (clear) payload.anthropic_clear_key = true;
    else if (apiKey.trim()) payload.anthropic_api_key = apiKey.trim();
    try {
      const r = await axios.put(`${API}/admin/integrations`, payload);
      const a = r.data?.anthropic || {};
      setCfg(a); setModel(a.model); setEnabled(!!a.enabled); setApiKey("");
      setMsg(clear ? "API key dihapus." : "Konfigurasi tersimpan.");
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan."); }
    finally { setBusy(false); }
  }

  const hasKey = !!cfg?.has_key;
  const active = hasKey && enabled;
  const modelOpts = (cfg?.models_available || ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"]).map((m) => ({ value: m, label: m }));

  return (
    <section className="section-card" data-testid="integrations-panel">
      <div className="section-head flex items-center gap-2"><Sparkles size={15} className="text-[#0058CC]" /><h2 className="text-[13px] font-bold">Integrasi AI — Anthropic Claude</h2></div>
      <div className="section-body">
        {loading ? (
          <p className="text-[12px] text-[#6B6B73] py-4">Memuat…</p>
        ) : (
          <div className="grid gap-3 max-w-[560px]">
            <div className={`flex items-center gap-2 rounded-lg px-3 py-2 text-[12px] font-semibold ${active ? "bg-[#E7F5EC] text-[#1F7A45]" : "bg-[#FBF3E2] text-[#B7791F]"}`} data-testid="integrations-status">
              {active ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
              {active ? "AI aktif — auto-tag galeri tersedia." : hasKey ? "Key tersimpan, tetapi AI dinonaktifkan." : "AI nonaktif — belum ada API key. Galeri tetap berfungsi penuh."}
            </div>

            {err && <div className="notice-bar danger !py-1.5" data-testid="integrations-error"><span className="text-[11.5px]">{err}</span></div>}
            {msg && <div className="notice-bar success !py-1.5" data-testid="integrations-msg"><span className="text-[11.5px]">{msg}</span></div>}

            <div className="grid gap-1">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73] flex items-center gap-1"><KeyRound size={12} /> API Key</label>
              <input data-testid="integrations-apikey" type="password" className="form-input" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                placeholder={hasKey ? "•••• tersimpan — isi untuk mengganti" : "Masukkan Anthropic API key (sk-ant-…)"} />
              <p className="text-[10.5px] text-[#9A9BA3]">Key disimpan aman di server & tidak pernah ditampilkan kembali.</p>
            </div>

            <div className="grid gap-1">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Model</label>
              <KNSelect data-testid="integrations-model" value={model} onValueChange={setModel} options={modelOpts} className="field !w-[260px]" />
            </div>

            <label className="flex items-center gap-2 text-[12.5px] cursor-pointer">
              <input data-testid="integrations-enabled" type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="h-4 w-4 accent-[#0058CC]" />
              Aktifkan auto-tag AI pada Galeri Desain
            </label>

            <div className="flex items-center gap-2 pt-1">
              <button data-testid="integrations-save" className="btn-primary" onClick={() => save()} disabled={busy}>{busy ? "Menyimpan…" : "Simpan Konfigurasi"}</button>
              {hasKey && <button data-testid="integrations-clear" className="btn-secondary" onClick={() => save({ clear: true })} disabled={busy}>Hapus Key</button>}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
