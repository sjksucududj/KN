/**
 * MakloonSelect (M1 — Master-Inline) — pemilih mitra makloon + quick-create.
 * Dipakai di form Resep Proses & Order Makloon. onSelect(makloon).
 *
 * FASE T: `PROCESS_LABELS` yang dulu hidup di sini DIHAPUS. Label jenis proses adalah
 * kosakata domain, bukan milik komponen pemilih mitra — dan daftarnya di sini hanya
 * memuat 5 dari 8 nilai yang sungguhan (`rajut`/`pre_treatment`/`screen` hilang), jadi
 * enam layar yang mengimpornya diam-diam kehilangan tiga pilihan. Sekarang: registry
 * hidup lewat `hooks/useProcessTypes` + cadangan di `constants/makloonVocab`.
 *
 * Modal dirender lewat **portal** (`createPortal`) karena komponen ini dipakai di dalam
 * `<Field>` = `<label>`: klik di dalam label diteruskan peramban ke tombol pemicunya,
 * sehingga modal yang lahir sebagai anak label akan **terbuka kembali** tiap kali
 * pemakai memilih mitra. Dijaga gate `INV-UI-09`.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Factory, Search, X, Plus, Check, ChevronDown } from "lucide-react";
import axios, { API } from "../services/apiClient";
import useProcessTypes from "../hooks/useProcessTypes";
import { overlayDismiss } from "@/utils/overlayDismiss";

export default function MakloonSelect({
  value = "", valueName = "", onSelect, processType = "",
  label = "Pilih makloon…", triggerTestId = "makloon-select-trigger", allowCreate = true, disabled = false,
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" data-testid={triggerTestId} disabled={disabled} onClick={() => setOpen(true)}
        className="field flex w-full items-center gap-2 text-left disabled:opacity-50">
        <Factory size={14} className="shrink-0 text-[#0058CC]" />
        <span className={`min-w-0 flex-1 truncate ${value ? "text-[#1C1C1E]" : "text-[#9A9BA3]"}`}>{value ? valueName : label}</span>
        <ChevronDown size={14} className="text-[#9A9BA3]" />
      </button>
      {open && createPortal(
        <MakloonPickerModal processType={processType} selectedId={value} allowCreate={allowCreate}
          onClose={() => setOpen(false)} onPick={(m) => { onSelect?.(m); setOpen(false); }} />,
        document.body)}
    </>
  );
}

function MakloonPickerModal({ processType, selectedId, allowCreate, onClose, onPick }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const { labelOf: processLabel } = useProcessTypes();

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/makloons`, { params: { status: "active" } });
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat makloon."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return rows.filter((m) => {
      if (processType && !(m.process_types || []).includes(processType)) return false;
      if (s && !`${m.code}${m.name}${m.city}`.toLowerCase().includes(s)) return false;
      return true;
    });
  }, [rows, q, processType]);

  return (
    <div data-testid="makloon-select-modal" className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="flex max-h-[85vh] w-full max-w-[520px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold"><Factory size={16} className="text-[#0058CC]" /> Pilih Makloon</h2>
          <div className="flex items-center gap-2">
            {allowCreate && <button data-testid="makloon-select-create-toggle" className="secondary-button" onClick={() => setShowCreate((v) => !v)}><Plus size={13} /> Baru</button>}
            <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={18} /></button>
          </div>
        </div>
        <div className="border-b border-[#EFF0F2] px-4 py-2.5">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="makloon-select-search" autoFocus className="field w-full pl-8" placeholder="Cari nama / kode / kota…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        {showCreate && <QuickCreateMakloon onCancel={() => setShowCreate(false)} onError={setError}
          onCreated={(m) => { setShowCreate(false); setRows((p) => [m, ...p]); onPick(m); }} />}
        <div className="flex-1 overflow-y-auto p-2">
          {loading ? <div className="py-8 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
           : error ? <div data-testid="makloon-select-error" className="py-8 text-center text-[12px] text-[#D14343]">{error}</div>
           : filtered.length === 0 ? (
            <div data-testid="makloon-select-empty" className="py-8 text-center text-[12px] text-[#8E8E93]">
              Tidak ada makloon{processType ? ` untuk proses ${processLabel(processType)}` : ""}.
              {allowCreate && <div className="mt-2"><button className="secondary-button" onClick={() => setShowCreate(true)}><Plus size={13} /> Buat Makloon</button></div>}
            </div>
          ) : filtered.map((m) => (
            <button key={m.id} data-testid={`makloon-select-item-${m.id}`} onClick={() => onPick(m)}
              className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left transition ${m.id === selectedId ? "border-[#0058CC] bg-[#EAF2FF]" : "border-transparent hover:bg-[#FAFBFC]"}`}>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12.5px] font-semibold">{m.name} <span className="text-[10.5px] font-normal text-[#0058CC]">{m.code}</span></p>
                <p className="truncate text-[10.5px] text-[#6B6B73]">{m.city || "—"} · {(m.process_types || []).map((p) => processLabel(p)).join(", ") || "—"}</p>
              </div>
              {m.id === selectedId && <Check size={15} className="text-[#0058CC]" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function QuickCreateMakloon({ onCancel, onCreated, onError }) {
  const [form, setForm] = useState({ name: "", city: "", pic_name: "", phone: "", process_types: [] });
  const [saving, setSaving] = useState(false);
  const { options: processOptions } = useProcessTypes();
  const toggle = (p) => setForm((f) => ({ ...f, process_types: f.process_types.includes(p) ? f.process_types.filter((x) => x !== p) : [...f.process_types, p] }));
  const submit = async () => {
    if (!form.name.trim()) { onError?.("Nama makloon wajib diisi."); return; }
    setSaving(true);
    try { const res = await axios.post(`${API}/makloons`, form); onCreated(res.data); }
    catch (e) { onError?.(e.response?.data?.detail || "Gagal membuat makloon."); setSaving(false); }
  };
  return (
    <div data-testid="makloon-quick-create" className="border-b border-[#EFF0F2] bg-[#FAFBFC] px-4 py-3 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <input data-testid="makloon-qc-name" className="field" placeholder="Nama makloon *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input data-testid="makloon-qc-city" className="field" placeholder="Kota" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
        <input data-testid="makloon-qc-pic" className="field" placeholder="PIC" value={form.pic_name} onChange={(e) => setForm({ ...form, pic_name: e.target.value })} />
        <input data-testid="makloon-qc-phone" className="field" placeholder="Telepon" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {processOptions().map(({ value: k, label: lbl }) => (
          <button key={k} type="button" onClick={() => toggle(k)}
            className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${form.process_types.includes(k) ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3C3C43]"}`}>{lbl}</button>
        ))}
      </div>
      <div className="flex justify-end gap-2">
        <button className="secondary-button" onClick={onCancel}>Batal</button>
        <button data-testid="makloon-qc-submit" className="primary-button" disabled={saving} onClick={submit}>{saving ? "…" : "Simpan"}</button>
      </div>
    </div>
  );
}
