/**
 * IncentiveRatesEditor (EPIC4) — Editor rate insentif v2 (matriks entity × kategori).
 *
 * FASE G-0: toggle **strategi komisi** (setting global `commission.*`) DIHAPUS dari
 * layar ini. Yang tersisa di sini adalah DATA MASTER rate insentif per entitas ×
 * kategori — bukan aturan sistem. Aturan globalnya diatur di Pusat Pengaturan
 * sehingga tidak ada dua form yang menulis kunci yang sama.
 * Manage rate: admin/manager.
 */
import { useCallback, useEffect, useState } from "react";
import { Save, Trash2, Pencil, RefreshCw, Percent, XCircle } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import ConfigRedirectCard from "../settings/config/ConfigRedirectCard";
import { entityFullById, entityOptions } from "../../utils/entityLabel";
import { askReason } from "@/services/confirmService";
import useUomConversions from "../../hooks/useUomConversions";
import { uomSelectOptions } from "../../utils/uomCatalog";

const THRESHOLD_TYPES = [
  { value: "pct", label: "% diskon" },
  { value: "rp_per_unit", label: "Rp / unit" },
];
const MECHANICS = [
  { value: "tier_factor", label: "Faktor (komisi × faktor)" },
  { value: "potong_rp", label: "Potong Rp/unit" },
  { value: "cutoff", label: "Cutoff (komisi 0)" },
];
const EMPTY = {
  entity_id: "all", category: "", incentive_unit: "meter", per_unit_amount: 0,
  discount_threshold_type: "pct", discount_threshold: 10, discount_mechanic: "tier_factor",
  discount_factor: 0.5, discount_potong_rp: 0, margin_cap_pct: 50, status: "active",
};

export default function IncentiveRatesEditor() {
  const [rows, setRows] = useState([]);
  const [cats, setCats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [entities, setEntities] = useState([]);
  // FASE U — satuan insentif dari MASTER satuan. Tarif insentif dihitung per satuan
  // jual; kalau daftarnya diketik di layar, produk yang dijual per `panel` tidak bisa
  // diberi tarif sama sekali dan komisi sales-nya diam-diam nol.
  useUomConversions();
  const unitOpts = uomSelectOptions({
    dimensions: ["length", "weight", "count"],
    extra: [form.incentive_unit].filter(Boolean),
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, c, e] = await Promise.all([
        axios.get(`${API}/incentive-rates`),
        axios.get(`${API}/product-categories`),
        axios.get(`${API}/entities`),
      ]);
      setRows(Array.isArray(r.data) ? r.data : []);
      setCats((Array.isArray(c.data) ? c.data : []).filter((x) => x.status === "active"));
      setEntities(Array.isArray(e.data) ? e.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat rate insentif.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const resetForm = () => { setForm(EMPTY); setEditingId(null); setFormError(""); };

  const startEdit = (r) => {
    setEditingId(r.id);
    setForm({ ...EMPTY, ...r });
    setFormError("");
  };

  const save = async () => {
    if (!String(form.category).trim()) { setFormError("Kategori wajib diisi."); return; }
    setSaving(true); setFormError("");
    const payload = {
      ...form,
      per_unit_amount: Number(form.per_unit_amount) || 0,
      discount_threshold: Number(form.discount_threshold) || 0,
      discount_factor: Number(form.discount_factor) || 0,
      discount_potong_rp: Number(form.discount_potong_rp) || 0,
      margin_cap_pct: Number(form.margin_cap_pct) || 0,
    };
    try {
      if (editingId) await axios.patch(`${API}/incentive-rates/${editingId}`, { data: payload });
      else await axios.post(`${API}/incentive-rates`, payload);
      resetForm(); await load();
      setNotice("Rate insentif tersimpan.");
    } catch (e) {
      setFormError(e.response?.data?.detail || "Gagal menyimpan rate.");
    } finally { setSaving(false); }
  };

  const remove = async (r) => {
    // Berdampak UANG: tarif ini yang dipakai menghitung komisi sales.
    const reason = await askReason({
      title: `Hapus tarif insentif ${r.category}?`,
      message: "Perhitungan komisi berikutnya untuk kategori ini akan memakai tarif lain "
        + "(atau nol bila tidak ada tarif pengganti).",
      reasonLabel: "Alasan penghapusan",
      confirmLabel: "Hapus Tarif",
      danger: true,
      testId: "incentive-rate-delete-confirm",
    });
    if (reason === null) return;
    try { await axios.delete(`${API}/incentive-rates/${r.id}`, { params: { reason } }); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menghapus rate."); }
  };

  const catOptions = cats.length
    ? cats.map((c) => ({ value: c.name, label: c.name }))
    : ["Batik", "Tenun", "Lurik", "Songket", "Ulos", "Jumputan", "Endek"].map((n) => ({ value: n, label: n }));

  // `/api/entities` tak punya field `name` — dulu opsi & kolom menampilkan `ent_ksc`.
  const entityOpts = [
    { value: "all", label: "Semua entitas" },
    ...entityOptions(entities),
  ];

  return (
    <div data-testid="incentive-rates-editor">
      {notice && <div className="mb-3 px-3 py-2 rounded-md bg-[#E6F6EC] text-[#1B7F4B] text-[12px] font-semibold" data-testid="incentive-notice">{notice}</div>}

      {/* FASE G-0 — aturan komisi global pindah ke Pusat Pengaturan.
          Tabel di bawah tetap di sini karena itu DATA (rate per entitas × kategori),
          bukan aturan sistem. */}
      <div className="mb-3">
        <ConfigRedirectCard
          title="Strategi & mekanik komisi"
          note="Rate per entitas × kategori di bawah ini tetap dikelola dari halaman ini."
          group="harga-diskon"
          testId="incentive-config-redirect"
          settings={[
            { key: "commission.strategy", label: "Strategi komisi" },
            { key: "commission.incentive_unit", label: "Satuan dasar insentif" },
            { key: "commission.discount_mechanic", label: "Mekanik potongan komisi" },
            { key: "commission.discount_threshold", label: "Ambang diskon" },
            { key: "commission.default_margin_cap_pct", label: "Batas margin komisi" },
          ]}
        />
      </div>

      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="incentive-error" />

      <section className="grid gap-3 lg:grid-cols-[340px_1fr]">
        {/* Form */}
        <div className="section-card">
          <div className="section-head">
            <div className="flex items-center gap-2"><Percent size={14} className="text-[#6B219A]" /><h2>{editingId ? "Edit Rate" : "Rate Baru"}</h2></div>
            {editingId && <button className="icon-button ml-auto" onClick={resetForm} data-testid="incentive-cancel-edit"><XCircle size={14} /></button>}
          </div>
          <div className="section-body grid gap-2">
            <L label="Entitas">
              <KNSelect data-testid="rate-entity-input" className="field" value={form.entity_id} onValueChange={(v) => setForm({ ...form, entity_id: v })} options={entityOpts} placeholder="Pilih entitas" />
            </L>
            <L label="Kategori *">
              <KNSelect data-testid="rate-category-input" className="field" value={form.category} onValueChange={(v) => setForm({ ...form, category: v })} options={catOptions} placeholder="Pilih kategori" />
            </L>
            <div className="grid grid-cols-2 gap-2">
              <L label="Rate (Rp/unit)"><input data-testid="rate-per-unit-input" type="number" className="field" value={form.per_unit_amount} onChange={(e) => setForm({ ...form, per_unit_amount: e.target.value })} /></L>
              <L label="Unit"><KNSelect data-testid="rate-unit-input" className="field" value={form.incentive_unit} onValueChange={(v) => setForm({ ...form, incentive_unit: v })} options={unitOpts} /></L>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <L label="Ambang diskon (basis)"><KNSelect data-testid="rate-threshold-type" className="field" value={form.discount_threshold_type} onValueChange={(v) => setForm({ ...form, discount_threshold_type: v })} options={THRESHOLD_TYPES} /></L>
              <L label="Ambang"><input data-testid="rate-threshold-input" type="number" className="field" value={form.discount_threshold} onChange={(e) => setForm({ ...form, discount_threshold: e.target.value })} /></L>
            </div>
            <L label="Mekanik diskon"><KNSelect data-testid="rate-mechanic-input" className="field" value={form.discount_mechanic} onValueChange={(v) => setForm({ ...form, discount_mechanic: v })} options={MECHANICS} /></L>
            <div className="grid grid-cols-2 gap-2">
              <L label="Faktor (tier)"><input data-testid="rate-factor-input" type="number" step="0.1" className="field" value={form.discount_factor} onChange={(e) => setForm({ ...form, discount_factor: e.target.value })} /></L>
              <L label="Potong Rp/unit"><input data-testid="rate-potong-input" type="number" className="field" value={form.discount_potong_rp} onChange={(e) => setForm({ ...form, discount_potong_rp: e.target.value })} /></L>
            </div>
            <L label="Margin cap (%)"><input data-testid="rate-margin-cap-input" type="number" className="field" value={form.margin_cap_pct} onChange={(e) => setForm({ ...form, margin_cap_pct: e.target.value })} /></L>
            {formError && <p className="text-[12px] font-semibold text-[#D14343]" data-testid="rate-form-error">{formError}</p>}
            <button data-testid="rate-save-button" className="primary-button mt-1" onClick={save} disabled={saving}>
              <Save size={14} /> {saving ? "Menyimpan..." : editingId ? "Update Rate" : "Simpan Rate"}
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="section-card">
          <div className="section-head">
            <h2>Matriks Rate Insentif {rows.length > 0 ? `(${rows.length})` : ""}</h2>
            <button data-testid="rate-refresh-button" className="icon-button ml-auto" onClick={load}><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
          </div>
          <div className="section-body">
            {loading ? (
              <div className="grid gap-2" data-testid="rate-loading">{[0, 1, 2, 3].map((i) => <div key={i} className="h-9 bg-[#F5F5F7] rounded animate-pulse" />)}</div>
            ) : rows.length === 0 ? (
              <div className="py-10 text-center text-[12px] text-[#8E8E93]" data-testid="rate-empty">Belum ada rate insentif.</div>
            ) : (
              <div className="overflow-auto rounded-md border border-[#EFF0F2]">
                <table className="w-full text-[12px]" data-testid="rate-table">
                  <thead>
                    <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                      <th className="px-2 py-2">Entitas</th><th className="px-2 py-2">Kategori</th>
                      <th className="px-2 py-2 text-right">Rate</th><th className="px-2 py-2">Diskon</th>
                      <th className="px-2 py-2 text-right">Margin Cap</th><th className="px-2 py-2 text-right">Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} data-testid={`rate-row-${r.id}`} className="border-b border-[#F5F5F7] last:border-0">
                        <td className="px-2 py-2 text-[11px] text-[#6B6B73]">{r.entity_id === "all" ? "Semua" : entityFullById(entities, r.entity_id)}</td>
                        <td className="px-2 py-2 font-semibold">{r.category}</td>
                        <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(r.per_unit_amount)}<span className="text-[10px] text-[#9A9BA3]">/{r.incentive_unit}</span></td>
                        <td className="px-2 py-2 text-[11px] text-[#6B6B73] tabular-nums">{r.discount_mechanic === "cutoff" ? "Cutoff" : r.discount_mechanic === "potong_rp" ? `−${formatCurrency(r.discount_potong_rp)}` : `×${r.discount_factor}`} @ {r.discount_threshold}{r.discount_threshold_type === "pct" ? "%" : "Rp"}</td>
                        <td className="px-2 py-2 text-right tabular-nums">{r.margin_cap_pct}%</td>
                        <td className="px-2 py-2">
                          <div className="flex items-center justify-end gap-1">
                            <button data-testid={`rate-edit-${r.id}`} className="icon-button" onClick={() => startEdit(r)}><Pencil size={13} /></button>
                            <button data-testid={`rate-delete-${r.id}`} className="icon-button" onClick={() => remove(r)}><Trash2 size={13} className="text-[#D14343]" /></button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function L({ label, children }) {
  return (
    <div>
      <label className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">{label}</label>
      {children}
    </div>
  );
}
