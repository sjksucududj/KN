/**
 * PantoneFinder (M0) — pemilih warna master bergaya Pantone (reusable lintas menu).
 * Trigger (field) → modal: search, filter family/sistem, cari-terdekat by hex,
 * grid swatch, dan quick-create warna baru. Single-select: onSelect({code,name,hex}).
 *
 * Kontrak API: GET/POST ${API}/color-library (+ /nearest). Respons ARRAY telanjang.
 *
 * Modal dirender lewat **portal** (`createPortal`) — komponen ini juga dipakai di dalam
 * `<Field>` = `<label>`, dan klik di dalam label diteruskan peramban ke tombol pemicu,
 * sehingga modal anak-label akan terbuka kembali tiap kali warna dipilih. `INV-UI-09`.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Palette, Search, X, Plus, Check, Crosshair, ChevronDown } from "lucide-react";
import axios, { API } from "../services/apiClient";
import KNSelect from "./KNSelect";
import { overlayDismiss } from "@/utils/overlayDismiss";

const SYSTEMS = [
  { value: "", label: "Semua Sistem" },
  { value: "KN", label: "KN (Internal)" },
  { value: "TCX", label: "TCX" },
  { value: "TPX", label: "TPX" },
  { value: "C", label: "Coated (C)" },
  { value: "U", label: "Uncoated (U)" },
];

export function ColorChip({ hex, size = 16, className = "" }) {
  return (
    <span
      className={`inline-block shrink-0 rounded-[5px] border border-[#E5E5EA] ${className}`}
      style={{ width: size, height: size, backgroundColor: hex || "#FFFFFF" }}
    />
  );
}

export default function PantoneFinder({
  value = "", valueName = "", valueHex = "", onSelect,
  label = "Pilih warna…", allowCreate = true,
  triggerTestId = "pantone-finder-trigger", disabled = false, compact = false,
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {compact ? (
        <button
          type="button" data-testid={triggerTestId} disabled={disabled}
          onClick={() => setOpen(true)}
          className="secondary-button"
        >
          {value ? <><ColorChip hex={valueHex} size={13} /> {value}</> : <><Plus size={13} /> {label}</>}
        </button>
      ) : (
        <button
          type="button" data-testid={triggerTestId} disabled={disabled}
          onClick={() => setOpen(true)}
          className="field flex w-full items-center gap-2 text-left disabled:opacity-50"
        >
          {value ? (
            <>
              <ColorChip hex={valueHex} size={18} />
              <span className="min-w-0 flex-1 truncate">
                <span className="font-semibold text-[#1C1C1E]">{value}</span>
                {valueName ? <span className="text-[#6B6B73]"> · {valueName}</span> : null}
              </span>
            </>
          ) : (
            <span className="flex-1 text-[#9A9BA3]">{label}</span>
          )}
          <ChevronDown size={14} className="text-[#9A9BA3]" />
        </button>
      )}
      {open && createPortal(
        <PantonePickerModal
          allowCreate={allowCreate}
          selectedCode={value}
          onClose={() => setOpen(false)}
          onPick={(c) => { onSelect?.(c); setOpen(false); }}
        />,
        document.body)}
    </>
  );
}

function PantonePickerModal({ selectedCode, allowCreate, onClose, onPick }) {
  const [colors, setColors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [family, setFamily] = useState("");
  const [system, setSystem] = useState("");
  const [hexQuery, setHexQuery] = useState("");
  const [nearestOrder, setNearestOrder] = useState(null); // [ids] or null
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/color-library`, { params: { status: "active" } });
      setColors(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat warna.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const families = useMemo(
    () => [...new Set(colors.map((c) => c.family).filter(Boolean))].sort(), [colors]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    let rows = colors.filter((c) => {
      if (family && c.family !== family) return false;
      if (system && c.system !== system) return false;
      if (s && !`${c.code}${c.name}${c.family}`.toLowerCase().includes(s)) return false;
      return true;
    });
    if (nearestOrder) {
      const rank = new Map(nearestOrder.map((id, i) => [id, i]));
      rows = [...rows].sort((a, b) => (rank.has(a.id) ? rank.get(a.id) : 999) - (rank.has(b.id) ? rank.get(b.id) : 999));
    }
    return rows;
  }, [colors, q, family, system, nearestOrder]);

  const runNearest = async () => {
    const hx = hexQuery.replace("#", "").trim();
    if (!/^[0-9a-fA-F]{6}$/.test(hx)) { setError("Hex harus 6 digit, mis. #1A2B3C"); return; }
    setError("");
    try {
      const res = await axios.get(`${API}/color-library/nearest`, { params: { hex: hx, limit: 12 } });
      setNearestOrder((res.data.results || []).map((r) => r.id));
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal mencari warna terdekat.");
    }
  };

  const nearestTopId = nearestOrder?.[0];

  return (
    <div data-testid="pantone-finder-modal" className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="flex max-h-[88vh] w-full max-w-[640px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3 border-b border-[#EFF0F2] px-4 py-3">
          <div className="flex items-center gap-2">
            <Palette size={16} className="text-[#0058CC]" />
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-[#0058CC]">Pustaka Warna</p>
              <h2 className="text-[15px] font-bold leading-tight">Pilih Warna</h2>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {allowCreate && (
              <button data-testid="pantone-finder-create-toggle" className="secondary-button" onClick={() => setShowCreate((v) => !v)}>
                <Plus size={13} /> Buat Warna Baru
              </button>
            )}
            <button data-testid="pantone-finder-close" className="icon-button" onClick={onClose} aria-label="Tutup"><X size={18} /></button>
          </div>
        </div>

        <div className="space-y-2.5 border-b border-[#EFF0F2] px-4 py-3">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="pantone-finder-search-input" autoFocus className="field w-full pl-8" placeholder="Cari kode / nama warna…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="grid grid-cols-[1fr_auto] items-center gap-2">
            <KNSelect data-testid="pantone-finder-system-filter" className="field" value={system} onValueChange={setSystem} options={SYSTEMS} />
            <div className="flex items-center gap-1.5">
              <input data-testid="pantone-finder-hex-input" className="field w-28" placeholder="#RRGGBB" value={hexQuery} onChange={(e) => setHexQuery(e.target.value)} />
              <button data-testid="pantone-finder-hex-search-button" className="secondary-button" onClick={runNearest} title="Cari warna terdekat"><Crosshair size={13} /> Terdekat</button>
              {nearestOrder && <button className="icon-button" onClick={() => { setNearestOrder(null); setHexQuery(""); }} aria-label="Reset terdekat"><X size={14} /></button>}
            </div>
          </div>
          {families.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <button className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${!family ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3C3C43]"}`} onClick={() => setFamily("")}>Semua</button>
              {families.map((f) => (
                <button key={f} data-testid={`pantone-finder-family-chip-${f}`} onClick={() => setFamily(family === f ? "" : f)}
                  className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${family === f ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>{f}</button>
              ))}
            </div>
          )}
        </div>

        {showCreate && (
          <CreateColorInline onCancel={() => setShowCreate(false)} onCreated={(c) => { setShowCreate(false); setColors((prev) => [c, ...prev]); onPick(c); }} onError={setError} />
        )}

        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
              {Array.from({ length: 18 }).map((_, i) => <div key={i} className="h-[72px] animate-pulse rounded-[10px] bg-[#F5F5F7]" />)}
            </div>
          ) : error && colors.length === 0 ? (
            <div data-testid="pantone-finder-error-state" className="py-10 text-center text-[12px] text-[#D14343]">
              {error}<div className="mt-2"><button className="secondary-button" onClick={load}>Coba lagi</button></div>
            </div>
          ) : filtered.length === 0 ? (
            <div data-testid="pantone-finder-empty-state" className="py-10 text-center text-[12px] text-[#8E8E93]">
              <Palette size={26} className="mx-auto mb-2 text-gray-300" />Tidak ada warna yang cocok.
              {allowCreate && <div className="mt-2"><button className="secondary-button" onClick={() => setShowCreate(true)}><Plus size={13} /> Buat Warna Baru</button></div>}
            </div>
          ) : (
            <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
              {filtered.map((c) => {
                const active = c.code === selectedCode;
                const isNearest = c.id === nearestTopId;
                return (
                  <button key={c.id} data-testid={`pantone-finder-swatch-${c.id}`} onClick={() => onPick({ code: c.code, name: c.name, hex: c.hex })}
                    className={`group relative flex flex-col items-center rounded-[10px] border bg-white p-2 text-center transition-shadow hover:shadow-[0_6px_16px_rgba(0,88,204,0.10)] ${active ? "border-[#0058CC] ring-2 ring-[#0058CC]/30" : isNearest ? "border-dashed border-[#0058CC]" : "border-[#E5E5EA]"}`}
                    aria-label={`Pilih warna ${c.code} ${c.name}`}>
                    {active && <Check size={12} className="absolute right-1 top-1 text-[#0058CC]" />}
                    <span className="h-8 w-8 rounded-md border border-[#E5E5EA]" style={{ backgroundColor: c.hex }} />
                    <span className="mt-1 block w-full truncate text-[10.5px] font-semibold text-[#1C1C1E]">{c.code}</span>
                    <span className="block w-full truncate text-[9.5px] text-[#6B6B73]">{c.name}</span>
                    {isNearest && <span className="mt-0.5 rounded-full bg-[#EAF2FF] px-1.5 text-[9px] font-bold text-[#0058CC]">Terdekat</span>}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CreateColorInline({ onCancel, onCreated, onError }) {
  const [form, setForm] = useState({ code: "", name: "", hex: "#", system: "KN", family: "" });
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async () => {
    setSaving(true);
    try {
      const res = await axios.post(`${API}/color-library`, form);
      onCreated(res.data);
    } catch (e) {
      onError?.(e.response?.data?.detail || "Gagal membuat warna.");
      setSaving(false);
    }
  };
  return (
    <div data-testid="pantone-finder-create-form" className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-4 py-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <input data-testid="pantone-create-code" className="field" placeholder="Kode (KN-XXX-01)" value={form.code} onChange={set("code")} />
        <input data-testid="pantone-create-name" className="field" placeholder="Nama warna" value={form.name} onChange={set("name")} />
        <div className="flex items-center gap-1.5">
          <input type="color" data-testid="pantone-create-hex-picker" className="h-9 w-10 shrink-0 cursor-pointer rounded border border-[#E5E5EA]" value={/^#[0-9a-fA-F]{6}$/.test(form.hex) ? form.hex : "#888888"} onChange={(e) => setForm({ ...form, hex: e.target.value })} />
          <input data-testid="pantone-create-hex" className="field" placeholder="#RRGGBB" value={form.hex} onChange={set("hex")} />
        </div>
        <KNSelect data-testid="pantone-create-system" className="field" value={form.system} onValueChange={(v) => setForm({ ...form, system: v })} options={SYSTEMS.filter((s) => s.value)} />
        <input data-testid="pantone-create-family" className="field" placeholder="Family (Biru/Merah…)" value={form.family} onChange={set("family")} />
        <div className="flex items-center gap-1.5">
          <button data-testid="pantone-finder-create-submit" className="primary-button flex-1 justify-center" disabled={saving} onClick={submit}>{saving ? "…" : "Simpan"}</button>
          <button data-testid="pantone-finder-create-cancel" className="secondary-button" onClick={onCancel}>Batal</button>
        </div>
      </div>
    </div>
  );
}
