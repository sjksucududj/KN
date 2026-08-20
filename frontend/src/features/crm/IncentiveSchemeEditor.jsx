import { useEffect, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Target, Award, Plus, Trash2, Save, Info, SlidersHorizontal } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import { currentPeriod } from "./crmUtils";

/**
 * IncentiveSchemeEditor (KN_17 §6.1/§6.2) — editor Target sales per periode +
 * Skema Insentif/Tier (basis + tiers + bonus). Akses: Admin & Manager.
 * Backend: GET/POST /api/sales-targets, GET/POST /api/sales-incentives.
 */
export default function IncentiveSchemeEditor({ currentUser, selectedEntity }) {
  const role = currentUser?.role;
  const isManager = role === "admin" || role === "manager";

  const [salesUsers, setSalesUsers] = useState([]);
  const [salesId, setSalesId] = useState("");
  const [period, setPeriod] = useState(currentPeriod());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Target state
  const [target, setTarget] = useState(blankTarget());
  const [savingTarget, setSavingTarget] = useState(false);

  // Incentive state
  const [scheme, setScheme] = useState(blankScheme());
  const [savingScheme, setSavingScheme] = useState(false);

  useEffect(() => { loadSales(); }, []); // eslint-disable-line
  useEffect(() => { if (salesId) loadConfig(); }, [salesId, period]); // eslint-disable-line

  async function loadSales() {
    try {
      const r = await axios.get(`${API}/sales-users`);
      const list = r.data || [];
      setSalesUsers(list);
      if (list.length && !salesId) setSalesId(list[0].id);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat daftar sales.");
    }
  }

  async function loadConfig() {
    setLoading(true);
    try {
      const [tRes, sRes] = await Promise.all([
        axios.get(`${API}/sales-targets`, { params: { sales_id: salesId, period } }),
        axios.get(`${API}/sales-incentives`, { params: { sales_id: salesId, period } }),
      ]);
      const t = (tRes.data || [])[0];
      setTarget(t ? {
        period_type: t.period_type || "month",
        target_sales_amount: t.target_sales_amount || 0,
        target_collection_amount: t.target_collection_amount || 0,
        target_new_customers: t.target_new_customers || 0,
        notes: t.notes || "",
      } : blankTarget());

      const s = (sRes.data || [])[0];
      setScheme(s ? {
        basis: s.basis || "collection",
        tiers: (s.tiers && s.tiers.length ? s.tiers : defaultTiers()).map((x) => ({
          min_achievement: Number(x.min_achievement) || 0, rate: Number(x.rate) || 0,
        })),
        bonus_new_customer: s.bonus_new_customer || 0,
        bonus_focus_product: s.bonus_focus_product || 0,
        notes: s.notes || "",
      } : blankScheme());
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat konfigurasi.");
    } finally { setLoading(false); }
  }

  async function saveTarget() {
    if (!salesId) { setError("Pilih salesperson dulu."); return; }
    setSavingTarget(true);
    try {
      const entity = (selectedEntity && selectedEntity !== "all") ? selectedEntity : "";
      await axios.post(`${API}/sales-targets`, {
        sales_id: salesId, period, entity_id: entity,
        period_type: target.period_type,
        target_sales_amount: Number(target.target_sales_amount) || 0,
        target_collection_amount: Number(target.target_collection_amount) || 0,
        target_new_customers: Number(target.target_new_customers) || 0,
        notes: target.notes,
      });
      setNotice(`Target periode ${period} tersimpan.`);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan target.");
    } finally { setSavingTarget(false); }
  }

  async function saveScheme() {
    if (!salesId) { setError("Pilih salesperson dulu."); return; }
    // Validasi tiers
    for (const t of scheme.tiers) {
      if (Number(t.min_achievement) < 0 || Number(t.rate) < 0) {
        setError("Min. capaian & rate tidak boleh negatif."); return;
      }
    }
    setSavingScheme(true);
    try {
      const entity = (selectedEntity && selectedEntity !== "all") ? selectedEntity : "";
      const tiers = [...scheme.tiers]
        .map((t) => ({ min_achievement: Number(t.min_achievement) || 0, rate: Number(t.rate) || 0 }))
        .sort((a, b) => a.min_achievement - b.min_achievement);
      await axios.post(`${API}/sales-incentives`, {
        sales_id: salesId, period, entity_id: entity,
        basis: scheme.basis, tiers,
        bonus_new_customer: Number(scheme.bonus_new_customer) || 0,
        bonus_focus_product: Number(scheme.bonus_focus_product) || 0,
        notes: scheme.notes,
      });
      setScheme((s) => ({ ...s, tiers }));
      setNotice(`Skema insentif periode ${period} tersimpan.`);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menyimpan skema insentif.");
    } finally { setSavingScheme(false); }
  }

  function addTier() {
    setScheme((s) => ({ ...s, tiers: [...s.tiers, { min_achievement: 0, rate: 0 }] }));
  }
  function removeTier(idx) {
    setScheme((s) => ({ ...s, tiers: s.tiers.filter((_, i) => i !== idx) }));
  }
  function updateTier(idx, key, val) {
    setScheme((s) => ({
      ...s,
      tiers: s.tiers.map((t, i) => (i === idx ? { ...t, [key]: val } : t)),
    }));
  }

  if (!isManager) {
    return (
      <div className="section-card" data-testid="incentive-editor-denied">
        <div className="section-body py-10 text-center text-[12px] text-[#6B6B73]">
          Hanya Manager / Admin yang dapat mengatur skema insentif & target.
        </div>
      </div>
    );
  }

  return (
    <div data-testid="incentive-scheme-editor">
      {notice && (
        <div className="notice-bar success" data-testid="incentive-notice">
          <span>{notice}</span><button onClick={() => setNotice("")}>×</button>
        </div>
      )}
      <ErrorNotice message={error} onRetry={loadConfig} onDismiss={() => setError("")} testId="incentive-error" />

      {/* Selector bar */}
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={16} className="text-[#0058CC]" />
            <h2 data-testid="incentive-title">Skema Insentif & Target Sales</h2>
          </div>
          <div className="flex items-center gap-2">
            <KNSelect
              value={salesId} onValueChange={setSalesId} className="field w-[180px]"
              data-testid="incentive-sales-select" placeholder="Pilih sales"
              options={salesUsers.map((s) => ({ value: s.id, label: s.name }))}
            />
            <input
              type="month" data-testid="incentive-period" value={period}
              onChange={(e) => setPeriod(e.target.value)} className="field w-[150px]"
            />
          </div>
        </div>
        <div className="section-body">
          <p className="text-[11px] text-[#6B6B73] flex items-center gap-1.5">
            <Info size={12} className="text-[#0058CC]" />
            Atur kuota target dan skema komisi tiered per salesperson & periode. Komisi default berbasis <b>pencairan</b> (collected).
          </p>
        </div>
      </div>

      {loading ? (
        <div className="section-card py-10 text-center text-[12px] text-[#6B6B73]" data-testid="incentive-loading">Memuat…</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {/* ── Target editor ── */}
          <div className="section-card" data-testid="target-editor">
            <div className="section-head">
              <div className="flex items-center gap-2"><Target size={15} className="text-[#0058CC]" /><h3 className="text-[12.5px] font-bold">Target Sales (Kuota)</h3></div>
            </div>
            <div className="section-body grid gap-3">
              <div>
                <label className="block text-[11px] font-semibold mb-1">Tipe Periode</label>
                <KNSelect
                  value={target.period_type}
                  onValueChange={(v) => setTarget((t) => ({ ...t, period_type: v }))}
                  className="field" data-testid="target-period-type"
                  options={[
                    { value: "month", label: "Bulanan" },
                    { value: "quarter", label: "Kuartal" },
                    { value: "year", label: "Tahunan" },
                  ]}
                />
              </div>
              <NumberField label="Target Penjualan (Rp)" testId="target-sales-amount"
                value={target.target_sales_amount}
                onChange={(v) => setTarget((t) => ({ ...t, target_sales_amount: v }))}
                hint={formatCurrency(target.target_sales_amount)} />
              <NumberField label="Target Pencairan (Rp)" testId="target-collection-amount"
                value={target.target_collection_amount}
                onChange={(v) => setTarget((t) => ({ ...t, target_collection_amount: v }))}
                hint={formatCurrency(target.target_collection_amount)} />
              <NumberField label="Target Pelanggan Baru" testId="target-new-customers"
                value={target.target_new_customers}
                onChange={(v) => setTarget((t) => ({ ...t, target_new_customers: v }))} />
              <div>
                <label className="block text-[11px] font-semibold mb-1">Catatan</label>
                <textarea data-testid="target-notes" rows="2" className="field"
                  value={target.notes} onChange={(e) => setTarget((t) => ({ ...t, notes: e.target.value }))}
                  placeholder="Opsional…" />
              </div>
              <button data-testid="save-target-button" disabled={savingTarget || !salesId}
                onClick={saveTarget} className="primary-button w-full">
                <Save size={14} /> {savingTarget ? "Menyimpan…" : "Simpan Target"}
              </button>
            </div>
          </div>

          {/* ── Incentive scheme editor ── */}
          <div className="section-card" data-testid="scheme-editor">
            <div className="section-head">
              <div className="flex items-center gap-2"><Award size={15} className="text-[#B45309]" /><h3 className="text-[12.5px] font-bold">Skema Insentif / Tier</h3></div>
            </div>
            <div className="section-body grid gap-3">
              <div>
                <label className="block text-[11px] font-semibold mb-1">Basis Komisi</label>
                <KNSelect
                  value={scheme.basis}
                  onValueChange={(v) => setScheme((s) => ({ ...s, basis: v }))}
                  className="field" data-testid="scheme-basis"
                  options={[
                    { value: "collection", label: "Pencairan (collected)" },
                    { value: "sales", label: "Penjualan (sales)" },
                    { value: "tiered", label: "Tiered (capaian target)" },
                  ]}
                />
              </div>

              {/* Tiers table */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-[11px] font-semibold">Tier Komisi (capaian → rate)</label>
                  <button data-testid="add-tier-button" onClick={addTier}
                    className="secondary-button !py-1 !px-2 text-[11px]"><Plus size={12} /> Tambah Tier</button>
                </div>
                <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
                  <div className="grid grid-cols-[1fr_1fr_44px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
                    <span>Min. Capaian (%)</span><span>Rate Komisi (%)</span><span></span>
                  </div>
                  {scheme.tiers.length === 0 ? (
                    <div className="py-6 text-center text-[11px] text-[#9A9BA3]" data-testid="tiers-empty">
                      Belum ada tier. Sistem akan memakai tier default bila kosong.
                    </div>
                  ) : scheme.tiers.map((t, i) => (
                    <div key={i} data-testid={`tier-row-${i}`}
                      className="grid grid-cols-[1fr_1fr_44px] items-center gap-2 px-3 py-2 border-b border-[#EFF0F2] last:border-0">
                      <input type="number" min="0" step="1" className="field" data-testid={`tier-min-${i}`}
                        value={t.min_achievement}
                        onChange={(e) => updateTier(i, "min_achievement", e.target.value)} />
                      <input type="number" min="0" step="0.1" className="field" data-testid={`tier-rate-${i}`}
                        value={t.rate}
                        onChange={(e) => updateTier(i, "rate", e.target.value)} />
                      <button data-testid={`remove-tier-${i}`} onClick={() => removeTier(i)}
                        className="icon-button text-[#C0392B]" title="Hapus tier"><Trash2 size={14} /></button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <NumberField label="Bonus / Pelanggan Baru (Rp)" testId="bonus-new-customer"
                  value={scheme.bonus_new_customer}
                  onChange={(v) => setScheme((s) => ({ ...s, bonus_new_customer: v }))} />
                <NumberField label="Bonus / Produk Fokus (Rp)" testId="bonus-focus-product"
                  value={scheme.bonus_focus_product}
                  onChange={(v) => setScheme((s) => ({ ...s, bonus_focus_product: v }))} />
              </div>

              <div>
                <label className="block text-[11px] font-semibold mb-1">Catatan</label>
                <textarea data-testid="scheme-notes" rows="2" className="field"
                  value={scheme.notes} onChange={(e) => setScheme((s) => ({ ...s, notes: e.target.value }))}
                  placeholder="Opsional…" />
              </div>

              <button data-testid="save-scheme-button" disabled={savingScheme || !salesId}
                onClick={saveScheme} className="primary-button w-full">
                <Save size={14} /> {savingScheme ? "Menyimpan…" : "Simpan Skema Insentif"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function NumberField({ label, value, onChange, testId, hint }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold mb-1">{label}</label>
      <input type="number" min="0" className="field" data-testid={testId}
        value={value} onChange={(e) => onChange(e.target.value)} />
      {hint && <p className="text-[10px] text-[#9A9BA3] mt-0.5 tabular-nums">{hint}</p>}
    </div>
  );
}

function blankTarget() {
  return { period_type: "month", target_sales_amount: 0, target_collection_amount: 0, target_new_customers: 0, notes: "" };
}
function defaultTiers() {
  return [
    { min_achievement: 0, rate: 1.0 },
    { min_achievement: 80, rate: 1.5 },
    { min_achievement: 100, rate: 2.5 },
    { min_achievement: 120, rate: 3.5 },
  ];
}
function blankScheme() {
  return { basis: "collection", tiers: defaultTiers(), bonus_new_customer: 0, bonus_focus_product: 0, notes: "" };
}
