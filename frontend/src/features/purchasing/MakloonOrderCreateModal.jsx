/**
 * MakloonOrderCreateModal (M3 · FASE T) — buat order makloon (1 step konversi).
 * Pilih resep (auto-isi bahan/output/makloon/param) → qty + gudang → forecast → simpan.
 * Mode: process_only (bahan dari stok) | buy_process (spawn PO bahan).
 *
 * FASE T mengubah dua hal di sini:
 *   1. **Tahapan proses dari master** (keputusan 4a) — dulu daftarnya hardcode 5 nilai
 *      (`tenun/celup/finishing/printing/lainnya`), jadi `rajut`, `pre_treatment`, dan
 *      `screen` tidak bisa dipilih sama sekali dari layar ini.
 *   2. **Yield tidak lagi berbawaan 1 tanpa alasan.** Bawaan lama `yield_factor: "1"`
 *      membuat SETIAP penyimpanan dari layar ini ditolak 400 oleh pagar PS-03 ("override
 *      yield wajib beralasan") — jalan buntu yang tak pernah terlihat karena pesannya
 *      berbicara soal kolom yang tidak ada di form ini. Sekarang: kosong = pakai rumus
 *      GSM, dan bila diisi (atau datang dari resep) alasannya ikut diisi & bisa disunting.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Boxes, X, Save, Calculator, ArrowRight, GitBranch, Layers } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import ProductSelect from "../../components/ProductSelect";
import MakloonSelect from "../../components/MakloonSelect";
import { formatQty } from "../../utils/formatters";
import { MATERIAL_FLOW_BADGE } from "../../constants/makloonVocab";
import { fetchStages } from "./makloon/makloonApi";
import { overlayDismiss } from "@/utils/overlayDismiss";

const MODE_OPTS = [
  { value: "process_only", label: "Proses Saja (bahan dari stok)" },
  { value: "buy_process", label: "Beli + Proses (buat PO bahan)" },
];
const FLOW_PICK_OPTIONS = [
  { value: "moves", label: MATERIAL_FLOW_BADGE.moves },
  { value: "service_only", label: MATERIAL_FLOW_BADGE.service_only },
];

export default function MakloonOrderCreateModal({ selectedEntity, initialMode, lockMode, onClose, onSaved, onError }) {
  const [recipes, setRecipes] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [stages, setStages] = useState([]);            // FASE T — dari master
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(null);

  const [f, setF] = useState({
    mode: initialMode || "process_only", recipe_id: "",
    material_product_id: "", material_name: "", material_qty: "", material_unit: "",
    from_warehouse_id: "", target_warehouse_id: "",
    supplier_id: "", supplier_name: "", material_price: "",
    stage_code: "", material_flow: "",
    process_type: "tenun", makloon_id: "", makloon_name: "",
    output_product_id: "", output_name: "", byproduct_product_id: "", byproduct_name: "",
    // Kosong = pakai rumus GSM (PS-03). Lihat catatan kepala berkas.
    yield_factor: "", yield_override_reason: "",
    waste_pct: "0", byproduct_pct: "0", tariff: "0", aux_cost: "0",
    notes: "",
  });
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));

  useEffect(() => {
    (async () => {
      try {
        const [r, w, s, st] = await Promise.all([
          axios.get(`${API}/process-recipes`, { params: { status: "active" } }),
          axios.get(`${API}/warehouses`).catch(() => ({ data: [] })),
          axios.get(`${API}/suppliers`).catch(() => ({ data: [] })),
          fetchStages().catch(() => []),
        ]);
        setRecipes(Array.isArray(r.data) ? r.data : []);
        const whs = Array.isArray(w.data) ? w.data : [];
        setWarehouses(whs);
        setSuppliers(Array.isArray(s.data) ? s.data : []);
        const rows = Array.isArray(st) ? st : [];
        setStages(rows);
        setF((p) => {
          const hit = rows.find((o) => o.process_type === p.process_type) || rows[0];
          return {
            ...p,
            from_warehouse_id: whs[0]?.id || p.from_warehouse_id,
            target_warehouse_id: whs[0]?.id || p.target_warehouse_id,
            stage_code: hit?.value || "",
            process_type: hit?.process_type || p.process_type,
            material_flow: hit?.material_flow === "either"
              ? (hit.material_flow_default || "moves") : "",
          };
        });
      } catch (e) { onError?.(e.response?.data?.detail || "Gagal memuat data pendukung."); }
    })();
  }, []); // eslint-disable-line

  const stage = useMemo(() => stages.find((o) => o.value === f.stage_code) || null, [stages, f.stage_code]);
  const noTransform = stage?.changes_stage === false;
  const stageOpts = useMemo(() => stages.map((o) => ({ value: o.value, label: o.label || o.value })), [stages]);

  const pickStage = (code) => {
    const m = stages.find((o) => o.value === code) || null;
    setF((p) => ({
      ...p,
      stage_code: code,
      process_type: m?.process_type || p.process_type,
      material_flow: m?.material_flow === "either" ? (m.material_flow_default || "moves") : "",
      // Angka yang tidak berlaku jangan tersimpan (lihat MakloonStepEditor).
      ...(m && m.changes_stage === false
        ? { waste_pct: "0", byproduct_pct: "0", yield_factor: "", yield_override_reason: "" }
        : {}),
      makloon_id: m?.process_type && m.process_type !== p.process_type ? "" : p.makloon_id,
      makloon_name: m?.process_type && m.process_type !== p.process_type ? "" : p.makloon_name,
    }));
  };

  const applyRecipe = (rid) => {
    const r = recipes.find((x) => x.id === rid);
    if (!r) { setF((p) => ({ ...p, recipe_id: "" })); return; }
    const hit = stages.find((o) => o.process_type === (r.process_type || "")) || null;
    setF((p) => ({
      ...p, recipe_id: rid, process_type: r.process_type || "tenun",
      stage_code: hit?.value || p.stage_code,
      material_flow: hit?.material_flow === "either" ? (hit.material_flow_default || "moves") : "",
      material_product_id: r.input_product_id || "",
      material_name: r.input_sku ? `${r.input_sku}` : (p.material_name || ""),
      material_unit: r.input_unit || p.material_unit,
      output_product_id: r.output_product_id || "",
      output_name: r.output_sku || "",
      byproduct_product_id: r.byproduct_product_id || "",
      byproduct_name: r.byproduct_name ? `${r.byproduct_name}` : (r.byproduct_sku || ""),
      makloon_id: r.default_makloon_id || "", makloon_name: r.default_makloon_name || "",
      yield_factor: r.yield_factor ? String(r.yield_factor) : "",
      // Yield yang datang dari resep TETAP override atas rumus GSM — jadi alasannya
      // diisi otomatis dengan asalnya (bisa disunting), bukan dibiarkan kosong lalu
      // ditolak 400 di detik terakhir.
      yield_override_reason: r.yield_factor ? `Yield dari resep "${r.name}"` : "",
      waste_pct: String(r.waste_pct ?? 0),
      byproduct_pct: String(r.byproduct_pct ?? 0), tariff: String(r.default_tariff ?? 0),
      aux_cost: String(r.aux_cost_default ?? 0),
    }));
    setPreview(null);
  };

  const runForecast = useCallback(async () => {
    try {
      const res = await axios.post(`${API}/process-recipes/forecast`, {
        input_qty: parseFloat(f.material_qty) || 0, yield_factor: parseFloat(f.yield_factor) || 1,
        waste_pct: parseFloat(f.waste_pct) || 0, byproduct_pct: parseFloat(f.byproduct_pct) || 0,
      });
      setPreview(res.data);
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal menghitung forecast."); }
  }, [f.material_qty, f.yield_factor, f.waste_pct, f.byproduct_pct]); // eslint-disable-line

  const whOpts = useMemo(() => warehouses.map((w) => ({ value: w.id, label: `${w.name} (${w.code})` })), [warehouses]);
  const supOpts = useMemo(() => [{ value: "", label: "— Pilih supplier —" }, ...suppliers.map((s) => ({ value: s.id, label: s.name }))], [suppliers]);
  const recipeOpts = useMemo(() => [{ value: "", label: "— Pilih resep (opsional) —" }, ...recipes.map((r) => ({ value: r.id, label: r.name }))], [recipes]);

  const save = async () => {
    if (!f.material_product_id) { onError?.("Produk bahan wajib dipilih."); return; }
    if (!(parseFloat(f.material_qty) > 0)) { onError?.("Qty bahan harus > 0."); return; }
    // Tahap tanpa transformasi: produk hasil = kain yang sama (diisi backend).
    if (!noTransform && !f.output_product_id) { onError?.("Produk output wajib dipilih."); return; }
    if (!f.from_warehouse_id) { onError?.("Gudang sumber bahan wajib dipilih."); return; }
    if (f.mode === "buy_process" && !f.supplier_id) { onError?.("Supplier bahan wajib dipilih untuk mode Beli + Proses."); return; }
    if (parseFloat(f.yield_factor) > 0 && !f.yield_override_reason.trim()) {
      onError?.("Yield yang diisi manual adalah override atas rumus GSM — alasannya wajib "
        + "diisi agar bisa diaudit (PS-03).");
      return;
    }
    // Mitra TIDAK memblokir (keputusan pemilik 3b) — backend menyimpan peringatannya
    // di dokumen dan layar rincian menampilkannya.
    setSaving(true);
    const supplier = suppliers.find((s) => s.id === f.supplier_id);
    const step = {
      stage_code: f.stage_code || "",
      process_type: f.process_type, makloon_id: f.makloon_id, recipe_id: f.recipe_id,
      input_product_id: f.material_product_id, output_product_id: f.output_product_id,
      byproduct_product_id: f.byproduct_product_id,
      yield_factor: parseFloat(f.yield_factor) || 0,
      yield_override_reason: parseFloat(f.yield_factor) > 0 ? f.yield_override_reason : "",
      waste_pct: parseFloat(f.waste_pct) || 0,
      byproduct_pct: parseFloat(f.byproduct_pct) || 0,
      tariff: parseFloat(f.tariff) || 0, aux_cost: parseFloat(f.aux_cost) || 0,
    };
    if (stage?.material_flow === "either") step.material_flow = f.material_flow || "moves";
    const payload = {
      mode: f.mode, material_product_id: f.material_product_id,
      material_qty: parseFloat(f.material_qty) || 0, material_unit: f.material_unit,
      from_warehouse_id: f.from_warehouse_id, target_warehouse_id: f.target_warehouse_id || f.from_warehouse_id,
      supplier_id: f.supplier_id, supplier_name: supplier?.name || "", material_price: parseFloat(f.material_price) || 0,
      notes: f.notes,
      entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "",
      steps: [step],
    };
    try {
      const res = await axios.post(`${API}/makloon-orders`, payload);
      onSaved?.(res.data);
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal membuat order makloon."); setSaving(false); }
  };

  return (
    <div data-testid="makloon-order-create-modal" className="fixed inset-0 z-[160] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="flex max-h-[92vh] w-full max-w-[720px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold"><Boxes size={16} className="text-[#0058CC]" /> {lockMode ? (f.mode === "buy_process" ? "Buat PO — Raw Material & Proses" : "Buat PO — Proses Saja") : "Buat Order Makloon"}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Tutup"><X size={18} /></button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {lockMode ? (
            <div className="rounded-lg border border-[#DCEAFE] bg-[#F2F7FF] p-2.5">
              <p className="text-[10px] font-bold uppercase text-[#0058CC]">Mode Pengadaan</p>
              <p className="text-[12.5px] font-semibold text-[#1B2733]">{f.mode === "buy_process" ? "Raw Material & Proses — beli bahan + kirim ke makloon" : "Proses Saja — bahan dari stok, kirim ke makloon"}</p>
            </div>
          ) : (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Mode Pengadaan"><KNSelect data-testid="mko-mode" className="field" value={f.mode} onValueChange={(v) => setF((p) => ({ ...p, mode: v }))} options={MODE_OPTS} /></Field>
            <Field label="Dari Resep (auto-isi)"><KNSelect data-testid="mko-recipe" className="field" value={f.recipe_id} onValueChange={applyRecipe} options={recipeOpts} /></Field>
          </div>
          )}
          {lockMode && (
            <Field label="Dari Resep (auto-isi)"><KNSelect data-testid="mko-recipe" className="field" value={f.recipe_id} onValueChange={applyRecipe} options={recipeOpts} /></Field>
          )}

          {f.mode === "buy_process" && (
            <div className="grid grid-cols-2 gap-3 rounded-lg border border-[#EFD9A8] bg-[#FFFBEF] p-3">
              <Field label="Supplier Bahan" req><KNSelect data-testid="mko-supplier" className="field" value={f.supplier_id} onValueChange={(v) => setF((p) => ({ ...p, supplier_id: v }))} options={supOpts} /></Field>
              <Field label="Harga Bahan / unit (Rp)"><input data-testid="mko-material-price" type="number" className="field" value={f.material_price} onChange={set("material_price")} placeholder="mis. 51500" /></Field>
            </div>
          )}

          <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-3">
            <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
              <div>
                <p className="mb-1 text-[10px] font-bold uppercase text-[#6B6B73]">Bahan (Input)</p>
                <ProductSelect triggerTestId="mko-material-product" value={f.material_product_id} valueName={f.material_name}
                  onSelect={(p) => setF((prev) => ({ ...prev, material_product_id: p.id, material_name: `${p.name} (${p.sku})`, material_unit: p.base_unit }))} label="Pilih bahan…" />
              </div>
              <ArrowRight size={18} className="mb-2 text-[#0058CC]" />
              <div>
                <p className="mb-1 text-[10px] font-bold uppercase text-[#6B6B73]">Output</p>
                {noTransform ? (
                  <div data-testid="mko-output-auto"
                    className="flex h-[34px] items-center rounded-md border border-dashed border-[#D6E6FF] bg-[#F5F9FF] px-2 text-[11.5px] text-[#004099]">
                    Otomatis: kain yang sama
                  </div>
                ) : (
                  <ProductSelect triggerTestId="mko-output-product" value={f.output_product_id} valueName={f.output_name}
                    onSelect={(p) => setF((prev) => ({ ...prev, output_product_id: p.id, output_name: `${p.name} (${p.sku})` }))} label="Pilih output…" />
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Field label="Qty Bahan" req><input data-testid="mko-material-qty" type="number" className="field" value={f.material_qty} onChange={set("material_qty")} placeholder="mis. 50" /></Field>
            <Field label="Satuan"><input data-testid="mko-material-unit" className="field" value={f.material_unit} onChange={set("material_unit")} placeholder="kg" /></Field>
            <Field label="Tahapan Proses (dari master)">
              <KNSelect data-testid="mko-stage" className="field" value={f.stage_code}
                onValueChange={pickStage} options={stageOpts} placeholder="Pilih tahap…" />
            </Field>
          </div>

          {stage && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-2"
              data-testid="mko-stage-meta">
              <Layers size={13} className="text-[#6B219A]" />
              <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ${
                noTransform ? "bg-[#F3E9FA] text-[#6B219A]" : "bg-[#EAF2FF] text-[#0058CC]"}`}>
                {noTransform ? "Tidak mengubah kain — hanya biaya jasa" : "Mengubah tahap kain"}
              </span>
              {stage.material_flow === "either" ? (
                <span className="flex items-center gap-1.5">
                  <span className="text-[10.5px] font-semibold text-[#6B6B73]">Kainnya:</span>
                  <KNSelect data-testid="mko-flow" className="field !h-7 !py-0 !text-[11px] w-[180px]"
                    value={f.material_flow || "moves"}
                    onValueChange={(v) => setF((p) => ({ ...p, material_flow: v }))}
                    options={FLOW_PICK_OPTIONS} />
                </span>
              ) : (
                <span className="rounded-full border border-[#E5E5EA] bg-white px-2 py-0.5 text-[10.5px] font-semibold text-[#3C3C43]">
                  {MATERIAL_FLOW_BADGE[stage.material_flow] || stage.material_flow || "Kain dikirim"}
                </span>
              )}
              {stage.needs_vendor && !f.makloon_id && (
                <span className="text-[10.5px] text-[#B26A00]">
                  Tahap ini dikerjakan mitra — pilih mitranya (boleh disimpan dulu, akan diperingatkan).
                </span>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Gudang Sumber Bahan" req><KNSelect data-testid="mko-from-warehouse" className="field" value={f.from_warehouse_id} onValueChange={(v) => setF((p) => ({ ...p, from_warehouse_id: v }))} options={whOpts} /></Field>
            <Field label="Mitra Makloon">
              <MakloonSelect triggerTestId="mko-makloon" processType={f.process_type} value={f.makloon_id} valueName={f.makloon_name}
                onSelect={(m) => setF((p) => ({ ...p, makloon_id: m.id, makloon_name: m.name }))} label="Pilih makloon…" />
            </Field>
          </div>

          <div className="grid grid-cols-4 gap-3">
            <Field label="Yield (kosong = rumus GSM)">
              <input data-testid="mko-yield" type="number" step="0.01" className="field" value={f.yield_factor}
                onChange={set("yield_factor")} disabled={noTransform} placeholder={noTransform ? "—" : "otomatis"} />
            </Field>
            <Field label="Waste (%)"><input data-testid="mko-waste" type="number" step="0.1" className="field" value={f.waste_pct} onChange={set("waste_pct")} disabled={noTransform} /></Field>
            <Field label="Sisa (%)"><input data-testid="mko-byproduct" type="number" step="0.1" className="field" value={f.byproduct_pct} onChange={set("byproduct_pct")} disabled={noTransform} /></Field>
            <Field label="Tarif/unit (Rp)"><input data-testid="mko-tariff" type="number" className="field" value={f.tariff} onChange={set("tariff")} /></Field>
          </div>
          {parseFloat(f.yield_factor) > 0 && (
            <Field label="Alasan override yield (wajib — bisa diaudit)" req>
              <input data-testid="mko-yield-reason" className="field" value={f.yield_override_reason}
                onChange={set("yield_override_reason")}
                placeholder="mis. Kontrak mitra menetapkan yield 3.8 yard/kg" />
            </Field>
          )}

          <div className="rounded-lg border border-[#EFE0C8] bg-[#FFFBF3] p-3">
            <p className="mb-1 text-[10px] font-bold uppercase text-[#9A6B1E]">Barang Sisa (leftover bahan input yang dikembalikan makloon, diterima sbg produk tersendiri)</p>
            <ProductSelect triggerTestId="mko-byproduct-product" value={f.byproduct_product_id} valueName={f.byproduct_name}
              onSelect={(p) => setF((prev) => ({ ...prev, byproduct_product_id: p.id, byproduct_name: `${p.name} (${p.sku})` }))} label="Pilih produk barang sisa (mis. Benang/Grey Sisa)…" />
            <p className="mt-1 text-[10px] text-[#9A9BA3]">Kosongkan bila tak ada sisa. Sisa dinilai pada HPP bahan & mengurangi HPP output.</p>
          </div>

          <div className="rounded-lg border border-dashed border-[#0058CC]/40 bg-[#EAF2FF]/40 p-3">
            <div className="flex items-center gap-2">
              <button data-testid="mko-forecast-btn" type="button" className="secondary-button" onClick={runForecast}><Calculator size={13} /> Hitung Estimasi Hasil</button>
              {preview && (
                <div className="flex-1 text-[11.5px]" data-testid="mko-forecast-result">
                  Output ≈ <b className="tabular-nums text-[#0058CC]">{formatQty(preview.expected_output)}</b> · Barang Sisa ≈ <b className="tabular-nums">{formatQty(preview.expected_byproduct)}</b>
                </div>
              )}
            </div>
          </div>

          <Field label="Catatan"><textarea data-testid="mko-notes" className="field" rows="2" value={f.notes} onChange={set("notes")} placeholder="Instruksi khusus…" /></Field>
        </div>
        <div className="flex items-center justify-between gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <p className="flex items-center gap-1.5 text-[11px] text-[#6B6B73]"><GitBranch size={12} /> Pesanan tersimpan sebagai <b>Draf</b> — lalu {noTransform ? "Catat Jasa" : "Issue & Terima"} di detail.</p>
          <div className="flex gap-2">
            <button className="secondary-button" onClick={onClose}>Batal</button>
            <button data-testid="mko-form-save" className="primary-button" disabled={saving} onClick={save}><Save size={14} /> {saving ? "Menyimpan…" : "Simpan Order"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, req, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">{label} {req && <span className="text-[#D14343]">*</span>}</span>
      {children}
    </label>
  );
}
