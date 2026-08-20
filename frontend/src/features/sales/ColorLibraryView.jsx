/**
 * ColorLibraryView (M0) — Pustaka Warna (master warna Pantone-style, SHARED).
 * CRUD penuh: cari, filter family/sistem/status, tambah/edit/nonaktifkan warna.
 * Dipakai lintas menu via PantoneFinder. Sumber: /api/color-library.
 * Akses: admin/manager kelola penuh; sales boleh tambah (quick-create).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Palette, Search, Plus, RefreshCw, Pencil, Ban, X, Save, Layers } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import { overlayDismiss } from "@/utils/overlayDismiss";
import { openRnd } from "../rnd/rndDeepLink";
import { askConfirm } from "@/services/confirmService";

const SYSTEMS = [
  { value: "KN", label: "KN (Internal)" },
  { value: "TCX", label: "TCX" }, { value: "TPX", label: "TPX" },
  { value: "C", label: "Coated (C)" }, { value: "U", label: "Uncoated (U)" },
];
const STATUS_OPTS = [
  { value: "active", label: "Aktif" }, { value: "inactive", label: "Nonaktif" }, { value: "all", label: "Semua" },
];

export default function ColorLibraryView({ currentUser }) {
  const role = currentUser?.role;
  const canManage = role === "admin" || role === "manager";
  const canCreate = canManage || role === "sales";

  const [colors, setColors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [family, setFamily] = useState("");
  const [system, setSystem] = useState("");
  const [status, setStatus] = useState("active");
  const [modal, setModal] = useState(null); // {mode, color}

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/color-library`, { params: { status } });
      setColors(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat pustaka warna.");
    } finally { setLoading(false); }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const families = useMemo(
    () => [...new Set(colors.map((c) => c.family).filter(Boolean))].sort(), [colors]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return colors.filter((c) => {
      if (family && c.family !== family) return false;
      if (system && c.system !== system) return false;
      if (s && !`${c.code}${c.name}${c.family}`.toLowerCase().includes(s)) return false;
      return true;
    });
  }, [colors, q, family, system]);

  const deactivate = async (c) => {
    const ok = await askConfirm({
      title: `Nonaktifkan warna "${c.code} · ${c.name}"?`,
      message: "Warna ini tidak lagi muncul di pilihan warna produk baru.",
      confirmLabel: "Nonaktifkan",
      danger: true,
      testId: "color-deactivate-confirm",
    });
    if (!ok) return;
    try { await axios.delete(`${API}/color-library/${c.id}`); load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menonaktifkan warna."); }
  };

  const familyOpts = [{ value: "", label: "Semua Family" }, ...families.map((f) => ({ value: f, label: f }))];

  return (
    <div data-testid="color-library-view">
      <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi testId="color-kpi-total" label="Total Warna" value={colors.length} icon={Palette} />
        <Kpi testId="color-kpi-family" label="Family" value={families.length} icon={Layers} tone="#6B219A" />
        <div className="section-card hidden lg:col-span-2 lg:block">
          <div className="section-body flex items-center gap-3 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#EAF2FF]"><Palette size={17} className="text-[#0058CC]" /></div>
            <p className="text-[11px] leading-tight text-[#6B6B73]">Master warna dipakai di <b>Produk</b>, <b>Template Varian</b>, <b>POS</b> & <b>Makloon</b>. Pilih warna via <b>PantoneFinder</b>, bukan teks bebas.</p>
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="section-head flex-wrap gap-2">
          <div className="relative min-w-[180px] flex-1">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="color-search" className="field w-full pl-8" placeholder="Cari kode / nama warna…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <KNSelect data-testid="color-family-filter" className="field w-[150px]" value={family} onValueChange={setFamily} options={familyOpts} />
          <KNSelect data-testid="color-system-filter" className="field w-[140px]" value={system} onValueChange={setSystem} options={[{ value: "", label: "Semua Sistem" }, ...SYSTEMS]} />
          <KNSelect data-testid="color-status-filter" className="field w-[120px]" value={status} onValueChange={setStatus} options={STATUS_OPTS} />
          <button data-testid="color-refresh" className="icon-button" onClick={load} aria-label="Refresh"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          {canCreate && (
            <button data-testid="color-create-btn" className="primary-button" onClick={() => setModal({ mode: "create" })}><Plus size={14} /> Tambah Warna</button>
          )}
        </div>
        <div className="section-body">
          <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="color-error" />
          {loading ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {Array.from({ length: 12 }).map((_, i) => <div key={i} className="h-[104px] animate-pulse rounded-lg bg-[#F5F5F7]" />)}
            </div>
          ) : filtered.length === 0 ? (
            <div data-testid="color-empty" className="py-14 text-center text-[12px] text-[#8E8E93]">
              <Palette size={28} className="mx-auto mb-2 text-gray-300" />Belum ada warna yang cocok.
              {canCreate && <div className="mt-2"><button className="secondary-button" onClick={() => setModal({ mode: "create" })}><Plus size={13} /> Tambah Warna</button></div>}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {filtered.map((c) => (
                <div key={c.id} data-testid={`color-card-${c.id}`} className={`group relative overflow-hidden rounded-lg border ${c.status === "inactive" ? "border-dashed border-[#E5E5EA] opacity-60" : "border-[#E5E5EA]"} bg-white`}>
                  <div className="h-14 w-full" style={{ backgroundColor: c.hex }} />
                  <div className="p-2">
                    <div className="flex items-center justify-between gap-1">
                      <span className="truncate text-[11.5px] font-bold text-[#1C1C1E]">{c.code}</span>
                      <span className="shrink-0 rounded bg-[#F5F5F7] px-1 text-[9px] font-bold text-[#6B6B73]">{c.system}</span>
                    </div>
                    <p className="truncate text-[10.5px] text-[#6B6B73]">{c.name}</p>
                    <p className="mt-0.5 flex items-center justify-between text-[9.5px] text-[#9A9BA3]">
                      <span className="truncate">{c.family || "—"}</span>
                      <span className="font-mono">{c.hex}</span>
                    </p>
                    {canCreate && c.status !== "inactive" && (
                      <button data-testid={`color-labdip-${c.id}`}
                        title="Buat permintaan labdip memakai warna ini (PS-13: warna dari pustaka, bukan teks bebas)"
                        className="mt-1.5 w-full rounded border border-[#E5E5EA] px-1 py-[3px] text-[9.5px] font-bold text-[#0058CC] hover:border-[#0058CC] hover:bg-[#F2F7FF]"
                        onClick={() => openRnd({
                          view: "rnd-samples", colorId: c.id,
                          colorLabel: `warna ${c.code} · ${c.name}`,
                        })}>
                        Buat Labdip
                      </button>
                    )}
                  </div>
                  {canManage && (
                    <div className="absolute right-1 top-1 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button data-testid={`color-edit-${c.id}`} className="rounded bg-white/90 p-1 shadow-sm hover:bg-white" onClick={() => setModal({ mode: "edit", color: c })} aria-label="Ubah"><Pencil size={12} className="text-[#0058CC]" /></button>
                      {c.status === "active" && (
                        <button data-testid={`color-delete-${c.id}`} className="rounded bg-white/90 p-1 shadow-sm hover:bg-white" onClick={() => deactivate(c)} aria-label="Nonaktifkan"><Ban size={12} className="text-[#A8221A]" /></button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {modal && (
        <ColorModal mode={modal.mode} color={modal.color} onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load(); }} onError={setError} />
      )}
    </div>
  );
}

function Kpi({ label, value, icon: Icon, tone = "#0058CC", testId }) {
  return (
    <div className="section-card" data-testid={testId}>
      <div className="section-body flex items-center gap-3 py-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ backgroundColor: `${tone}14` }}><Icon size={17} style={{ color: tone }} /></div>
        <div><p className="text-[10px] font-bold uppercase text-[#8E8E93]">{label}</p><p className="text-[18px] font-bold tabular-nums leading-tight">{value}</p></div>
      </div>
    </div>
  );
}

function ColorModal({ mode, color, onClose, onSaved, onError }) {
  const [form, setForm] = useState({
    code: color?.code || "", name: color?.name || "", hex: color?.hex || "#",
    system: color?.system || "KN", family: color?.family || "", status: color?.status || "active",
  });
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const hexValid = /^#[0-9a-fA-F]{6}$/.test(form.hex);

  const save = async () => {
    if (mode === "create" && !form.code.trim()) { onError("Kode warna wajib diisi."); return; }
    if (!hexValid) { onError("Hex tidak valid (mis. #1A2B3C)."); return; }
    setSaving(true);
    try {
      if (mode === "edit") {
        await axios.patch(`${API}/color-library/${color.id}`, {
          name: form.name, hex: form.hex, system: form.system, family: form.family, status: form.status,
        });
      } else {
        await axios.post(`${API}/color-library`, form);
      }
      onSaved();
    } catch (e) {
      onError(e.response?.data?.detail || "Gagal menyimpan warna.");
      setSaving(false);
    }
  };

  return (
    <div data-testid="color-modal" className="fixed inset-0 z-[160] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="w-full max-w-[460px] overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold"><Palette size={16} className="text-[#0058CC]" /> {mode === "edit" ? "Edit Warna" : "Tambah Warna"}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={18} /></button>
        </div>
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-3">
            <div className="h-16 w-16 shrink-0 rounded-lg border border-[#E5E5EA]" style={{ backgroundColor: hexValid ? form.hex : "#F5F5F7" }} />
            <div className="flex-1 space-y-2">
              <Field label="Kode Warna *">
                <input data-testid="color-form-code" className="field" placeholder="KN-BLU-01" value={form.code} onChange={set("code")} disabled={mode === "edit"} autoFocus={mode === "create"} />
              </Field>
              <Field label="Nama Warna *">
                <input data-testid="color-form-name" className="field" placeholder="Biru Indigo" value={form.name} onChange={set("name")} />
              </Field>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Hex *">
              <div className="flex items-center gap-1.5">
                <input type="color" data-testid="color-form-hex-picker" className="h-9 w-10 shrink-0 cursor-pointer rounded border border-[#E5E5EA]" value={hexValid ? form.hex : "#888888"} onChange={(e) => setForm({ ...form, hex: e.target.value })} />
                <input data-testid="color-form-hex" className="field" placeholder="#RRGGBB" value={form.hex} onChange={set("hex")} />
              </div>
            </Field>
            <Field label="Sistem">
              <KNSelect data-testid="color-form-system" className="field" value={form.system} onValueChange={(v) => setForm({ ...form, system: v })} options={SYSTEMS} />
            </Field>
            <Field label="Family">
              <input data-testid="color-form-family" className="field" placeholder="Biru / Merah / …" value={form.family} onChange={set("family")} />
            </Field>
            {mode === "edit" && (
              <Field label="Status">
                <KNSelect data-testid="color-form-status" className="field" value={form.status} onValueChange={(v) => setForm({ ...form, status: v })} options={[{ value: "active", label: "Aktif" }, { value: "inactive", label: "Nonaktif" }]} />
              </Field>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button data-testid="color-form-save" className="primary-button" onClick={save} disabled={saving}><Save size={14} /> {saving ? "Menyimpan…" : "Simpan"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</span>
      {children}
    </label>
  );
}
