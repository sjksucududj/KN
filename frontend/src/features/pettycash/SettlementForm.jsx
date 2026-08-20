import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import { fmtDate } from "./pettyCashShared";

/**
 * SettlementForm — Buat Laporan Pertanggungjawaban atas PD yang sudah dicairkan.
 * Baris pengeluaran (tanggal/uraian/kategori/nominal) → ringkasan per kategori +
 * sisa/kurang dana (BE hitung ulang & posting GL saat disetujui).
 */
const emptyLine = () => ({ date: new Date().toISOString().slice(0, 10), description: "", category: "petty_cash_lain", amount: "" });

export default function SettlementForm({ categories, preselectPd, selectedEntity, onCancel, onSaved }) {
  const [advances, setAdvances] = useState([]);
  const [pdId, setPdId] = useState(preselectPd?.id || "");
  const [divisi, setDivisi] = useState("");
  const [periode, setPeriode] = useState("");
  const [catatan, setCatatan] = useState("");
  const [lines, setLines] = useState([emptyLine()]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { loadAdvances(); }, [selectedEntity]); // eslint-disable-line

  async function loadAdvances() {
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const res = await axios.get(`${API}/cash-advances`, { params });
      const all = Array.isArray(res.data) ? res.data : [];
      setAdvances(all.filter((a) => ["disbursed", "settled"].includes(a.status)));
    } catch (e) { /* non-blocking */ }
  }

  const selectedPd = advances.find((a) => a.id === pdId) || (preselectPd?.id === pdId ? preselectPd : null);
  const danaDiterima = Number(selectedPd?.total_amount) || 0;
  const totalPengeluaran = useMemo(() => lines.reduce((s, l) => s + (Number(l.amount) || 0), 0), [lines]);
  const sisa = danaDiterima - totalPengeluaran;

  const catTotals = useMemo(() => {
    const m = {};
    lines.forEach((l) => { const a = Number(l.amount) || 0; if (a > 0) m[l.category] = (m[l.category] || 0) + a; });
    return m;
  }, [lines]);

  const catOptions = categories.filter((c) => c.active !== false).map((c) => ({ value: c.code, label: c.label }));
  const catLabel = (code) => categories.find((c) => c.code === code)?.label || code;

  function updLine(i, k, v) { setLines(lines.map((l, idx) => (idx === i ? { ...l, [k]: v } : l))); }
  function addLine() { setLines([...lines, emptyLine()]); }
  function rmLine(i) { setLines(lines.length > 1 ? lines.filter((_, idx) => idx !== i) : lines); }

  async function submit() {
    setErr("");
    if (!pdId) { setErr("Pilih PD yang akan dipertanggungjawabkan."); return; }
    const clean = lines
      .filter((l) => (Number(l.amount) || 0) > 0)
      .map((l) => ({ date: l.date, description: l.description || "", category: l.category, amount: Number(l.amount) || 0 }));
    if (clean.length === 0) { setErr("Minimal 1 baris pengeluaran dengan nominal > 0."); return; }
    setBusy(true);
    try {
      const res = await axios.post(`${API}/cash-advance-settlements`, {
        cash_advance_id: pdId, divisi, periode, expense_lines: clean, catatan,
      });
      onSaved(res.data);
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal menyimpan pertanggungjawaban.");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="stl-form" className="grid gap-4">
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <button className="icon-button" onClick={onCancel} aria-label="Kembali"><ArrowLeft size={15} /></button>
            <h2 data-testid="stl-form-title">Buat Pertanggungjawaban (LPJ)</h2>
          </div>
        </div>
        <div className="section-body grid gap-3">
          {err && <div className="notice-bar danger" data-testid="stl-form-error"><span>{err}</span><button onClick={() => setErr("")}>×</button></div>}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Pengajuan Dana (PD)" req>
              <KNSelect data-testid="stl-pd-select" className="form-input" value={pdId} onValueChange={setPdId}
                placeholder="Pilih PD yang sudah dicairkan"
                options={advances.map((a) => ({ value: a.id, label: `${a.number} · ${a.kegiatan || a.divisi || ""} · ${formatCurrency(a.total_amount)}` }))} />
            </Field>
            <Field label="Divisi">
              <input data-testid="stl-divisi" className="form-input" value={divisi} onChange={(e) => setDivisi(e.target.value)} placeholder={selectedPd?.divisi || "Divisi"} />
            </Field>
            <Field label="Periode">
              <input data-testid="stl-periode" className="form-input" value={periode} onChange={(e) => setPeriode(e.target.value)} placeholder="mis. Juli 2026" />
            </Field>
            <Field label="Dana Diterima (dari PD)">
              <input data-testid="stl-dana" className="form-input bg-[#F7F8FA]" value={formatCurrency(danaDiterima)} readOnly />
            </Field>
          </div>

          {/* Expense lines */}
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[120px_1.5fr_1fr_130px_36px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
              <span>Tanggal</span><span>Uraian</span><span>Kategori</span><span className="text-right">Nominal</span><span></span>
            </div>
            {lines.map((l, i) => (
              <div key={i} data-testid={`stl-line-${i}`} className="grid grid-cols-[120px_1.5fr_1fr_130px_36px] items-center gap-1 px-3 py-2 border-t border-[#F4F5F7]">
                <input type="date" data-testid={`stl-line-date-${i}`} className="form-input" value={l.date} onChange={(e) => updLine(i, "date", e.target.value)} />
                <input data-testid={`stl-line-desc-${i}`} className="form-input" value={l.description} onChange={(e) => updLine(i, "description", e.target.value)} placeholder="Uraian pengeluaran" />
                <KNSelect data-testid={`stl-line-cat-${i}`} className="form-input" value={l.category} onValueChange={(v) => updLine(i, "category", v)} options={catOptions} />
                <input type="number" data-testid={`stl-line-amount-${i}`} className="form-input text-right" value={l.amount} onChange={(e) => updLine(i, "amount", e.target.value)} placeholder="0" />
                <button className="icon-button text-red-500" onClick={() => rmLine(i)} aria-label="Hapus"><Trash2 size={14} /></button>
              </div>
            ))}
            <div className="px-3 py-2 border-t border-[#EFF0F2] bg-[#FAFBFC]">
              <button data-testid="stl-add-line" className="btn-secondary btn-xs" onClick={addLine}><Plus size={13} /> Tambah Baris</button>
            </div>
          </div>

          {/* Summary per category + sisa/kurang */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md border border-[#EFF0F2] p-3">
              <p className="text-[10px] font-bold uppercase text-[#6B6B73] mb-1.5">Ringkasan per Kategori</p>
              {Object.keys(catTotals).length === 0 ? <p className="text-[11.5px] text-[#9A9BA3]">Belum ada pengeluaran.</p> : (
                <div className="space-y-1">
                  {Object.entries(catTotals).map(([c, a]) => (
                    <div key={c} className="flex justify-between text-[11.5px]"><span className="text-[#3C3C43]">{catLabel(c)}</span><span className="font-semibold tabular-nums">{formatCurrency(a)}</span></div>
                  ))}
                </div>
              )}
            </div>
            <div className="rounded-md border border-[#EFF0F2] p-3 space-y-1.5">
              <Row k="Total Pengeluaran" v={formatCurrency(totalPengeluaran)} testId="stl-total-pengeluaran" />
              <Row k="Dana Diterima" v={formatCurrency(danaDiterima)} />
              <div className="border-t border-[#EFF0F2] pt-1.5">
                <Row k={sisa >= 0 ? "Sisa Dikembalikan" : "Kekurangan Dana"} v={formatCurrency(Math.abs(sisa))} strong tone={sisa >= 0 ? "#1A7A3A" : "#C62828"} testId="stl-sisa" />
              </div>
            </div>
          </div>

          <Field label="Catatan">
            <textarea data-testid="stl-catatan" className="form-input" rows="2" value={catatan} onChange={(e) => setCatatan(e.target.value)} placeholder="Keterangan tambahan..." />
          </Field>

          <div className="flex justify-end gap-2 pt-1">
            <button className="btn-secondary" onClick={onCancel}>Batal</button>
            <button data-testid="stl-submit" className="btn-primary" onClick={submit} disabled={busy}>{busy ? "Menyimpan…" : "Simpan LPJ"}</button>
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({ label, req, children }) {
  return (<div className="grid gap-1.5"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">{label}{req && <span className="req"> *</span>}</label>{children}</div>);
}
function Row({ k, v, strong, tone, testId }) {
  return (<div className="flex justify-between text-[12px]"><span className="text-[#3C3C43]">{k}</span><span data-testid={testId} className="font-bold tabular-nums" style={tone ? { color: tone } : {}}>{v}</span></div>);
}
