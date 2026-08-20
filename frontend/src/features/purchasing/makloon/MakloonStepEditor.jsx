/**
 * MakloonStepEditor (FASE D · PS-03/PS-04/PS-07/PS-08 · FASE T tahapan proses)
 * Editor SATU langkah rantai makloon di dalam wizard:
 *   TAHAP (dari master) → mitra → produk output → kontrak (auto-resolve) → tarif
 *   (basis bebas) → estimasi berbasis GSM (angka antara terlihat) → toleransi selisih.
 *
 * Rantai dipaksa: bahan masuk langkah ini = hasil langkah sebelumnya (read-only).
 *
 * FASE T (keputusan pemilik 1c & 4a) — yang berubah di layar ini:
 *   · pilihan langkah datang dari **master Tahapan Proses**, bukan daftar hardcode;
 *   · tahap yang `changes_stage=false` (mis. pembuatan kasa/SCREEN) TIDAK mengubah
 *     kain: kolom susut/yield/barang-sisa dimatikan dengan penjelasan, dan produk
 *     hasil tidak perlu dipilih (kain yang sama);
 *   · bila master membuka dua-duanya (`either`), petugas memilih **kain dikirim**
 *     atau **jasa murni** di sini — pilihan itu menentukan aksi yang muncul nanti
 *     (Issue/Terima Hasil vs Catat Jasa), jadi ia disebut sebelum disimpan.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Calculator, FileText, Info, Layers, Trash2, TriangleAlert, Wand2 } from "lucide-react";
import MakloonSelect from "../../../components/MakloonSelect";
import ProductSelect from "../../../components/ProductSelect";
import KNSelect from "../../../components/KNSelect";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import { MATERIAL_FLOW_BADGE, MATERIAL_FLOW_LABELS, NEXT_ACTION_LABELS } from "../../../constants/makloonVocab";
import { estimateStep, FALLBACK_BASIS_LABELS, AUX_BASIS_OPTIONS } from "./makloonApi";

const FLOW_PICK_OPTIONS = [
  { value: "moves", label: MATERIAL_FLOW_LABELS.moves },
  { value: "service_only", label: MATERIAL_FLOW_LABELS.service_only },
];

/** Aliran kain efektif langkah ini: master mengunci, langkah memilih bila `either`. */
export function effectiveFlow(stage, step) {
  const allowed = String(stage?.material_flow || "");
  if (allowed === "either") {
    const picked = String(step?.material_flow || "");
    if (picked === "moves" || picked === "service_only") return picked;
    return stage?.material_flow_default === "service_only" ? "service_only" : "moves";
  }
  if (allowed === "moves" || allowed === "service_only") return allowed;
  return "moves";
}

export default function MakloonStepEditor({
  index, step, inputProduct, stageOptions = [], basisOptions, entityId,
  onChange, onRemove, canRemove,
}) {
  const [preview, setPreview] = useState(null);
  const [previewErr, setPreviewErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const set = (patch) => onChange({ ...step, ...patch });

  const stage = useMemo(
    () => stageOptions.find((o) => o.value === step.stage_code) || null,
    [stageOptions, step.stage_code]);
  // Sebelum pratinjau termuat, arti tahap dibaca dari master di layar; sesudah itu
  // JAWABAN BACKEND yang dipakai — dialah yang akan mengeksekusi saat disimpan.
  const srv = preview?.stage || null;
  const noTransform = srv ? srv.changes_stage === false : stage?.changes_stage === false;
  const flow = srv ? srv.material_flow : effectiveFlow(stage, step);
  const flowAllowed = srv ? (srv.material_flow_allowed || "") : String(stage?.material_flow || "");
  const serviceOnly = flow === "service_only";
  const needsVendor = srv ? srv.needs_vendor : Boolean(stage?.needs_vendor);
  const stageOpts = useMemo(
    () => stageOptions.map((o) => ({ value: o.value, label: o.label || o.value })), [stageOptions]);

  /** Ganti tahap = ganti ARTI langkah, jadi field turunannya ikut disesuaikan. */
  const pickStage = (code) => {
    const m = stageOptions.find((o) => o.value === code) || null;
    const patch = {
      stage_code: code,
      // `process_type` tetap dikirim: mesin tarif/estimasi & pemilih mitra memakainya,
      // dan SPK lama pun menyimpannya (jembatan kompatibilitas tidak dilepas).
      process_type: m?.process_type || step.process_type || "",
      material_flow: m?.material_flow === "either"
        ? (m.material_flow_default || "moves") : "",
    };
    if (m && m.changes_stage === false) {
      // Angka yang TIDAK berlaku jangan tersimpan: susut 3% yang tetap tersimpan di
      // langkah tanpa transformasi akan membuat penerimaan menghitung selisih
      // terhadap angka yang tidak pernah berlaku, lalu membuka klaim palsu.
      patch.waste_pct = "";
      patch.yield_factor = "";
      patch.yield_override_reason = "";
      patch.byproduct_pct = "";
    }
    // Mitra yang tidak sanggup mengerjakan proses baru dilepas, supaya kolom mitra
    // tidak memperlihatkan nama yang pasti ditolak pemilih (daftarnya tersaring).
    if (m?.process_type && step.makloon_id && m.process_type !== step.process_type) {
      patch.makloon_id = "";
      patch.makloon_name = "";
    }
    set(patch);
  };

  const runPreview = useCallback(async () => {
    const needOutput = !(stage?.changes_stage === false);
    if (!inputProduct?.id || !(parseFloat(step.input_qty) > 0)
        || (needOutput && !step.output_product_id)) {
      setPreview(null);
      return;
    }
    setBusy(true);
    setPreviewErr("");
    try {
      const body = {
        input_product_id: inputProduct.id,
        // Kosong untuk tahap tanpa transformasi — backend memakai kain yang sama.
        output_product_id: step.output_product_id || "",
        makloon_id: step.makloon_id || "",
        process_type: step.process_type || "",
        // FASE T — tanpa dua field ini pratinjau memakai jalur "tahap tidak dikenal"
        // dan menampilkan angka yang berbeda dari yang akan tersimpan.
        stage_code: step.stage_code || "",
        material_flow: step.material_flow || "",
        input_qty: parseFloat(step.input_qty) || 0,
        byproduct_pct: parseFloat(step.byproduct_pct) || 0,
        colors: parseInt(step.colors, 10) || 0,
        repeats: parseInt(step.repeats, 10) || 0,
        entity_id: entityId && entityId !== "all" ? entityId : "",
      };
      if (step.waste_pct !== "" && step.waste_pct != null) body.waste_pct = parseFloat(step.waste_pct);
      if (step.tolerance_pct !== "" && step.tolerance_pct != null) body.tolerance_pct = parseFloat(step.tolerance_pct);
      if (parseFloat(step.yield_factor) > 0) {
        body.yield_factor = parseFloat(step.yield_factor);
        body.yield_override_reason = step.yield_override_reason || "";
      }
      if (step.tariff_basis) body.tariff_basis = step.tariff_basis;
      if (step.tariff_rate !== "" && step.tariff_rate != null) body.tariff_rate = parseFloat(step.tariff_rate);
      if (step.tariff_formula) body.tariff_formula = step.tariff_formula;
      if (step.ppi !== "" && step.ppi != null) body.ppi = parseFloat(step.ppi);
      if ((step.aux_fees || []).length) body.aux_fees = step.aux_fees;
      const res = await estimateStep(body);
      setPreview(res);
      onChange({ ...step, _preview: res });
    } catch (e) {
      setPreviewErr(e.response?.data?.detail || "Gagal menghitung estimasi.");
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }, [inputProduct?.id, step.output_product_id, step.makloon_id, step.process_type, step.input_qty,
      step.stage_code, step.material_flow, stage?.changes_stage,
      step.waste_pct, step.tolerance_pct, step.yield_factor, step.tariff_basis, step.tariff_rate,
      step.tariff_formula, step.ppi, step.colors, step.repeats, step.byproduct_pct]); // eslint-disable-line

  useEffect(() => {
    const t = setTimeout(runPreview, 450);
    return () => clearTimeout(t);
  }, [runPreview]);

  const est = preview?.estimate;
  const tariff = preview?.tariff;
  const stageWarnings = srv?.warnings || [];

  return (
    <div className="rounded-xl border border-[#E5E5EA] bg-white" data-testid={`wizard-step-${index + 1}`}>
      <div className="flex items-center justify-between gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="rounded bg-[#0058CC] px-1.5 py-0.5 text-[10.5px] font-bold text-white">Langkah {index + 1}</span>
          <span className="truncate text-[11.5px] text-[#3C3C43]">
            {inputProduct?.name || "bahan"}
            {noTransform ? (
              <> <ArrowRight size={10} className="inline" /> kain yang sama</>
            ) : (
              <> <ArrowRight size={10} className="inline" /> {step.output_name || "pilih output"}</>
            )}
          </span>
        </div>
        {canRemove && (
          <button type="button" data-testid={`wizard-remove-step-${index + 1}`} onClick={onRemove}
            className="icon-button text-red-400 hover:text-red-600"><Trash2 size={14} /></button>
        )}
      </div>

      <div className="space-y-3 p-3">
        <div className="grid gap-2.5 md:grid-cols-3">
          <Field label="Tahapan Proses (dari master)">
            <KNSelect data-testid={`wizard-stage-${index + 1}`} className="field" value={step.stage_code || ""}
              onValueChange={pickStage} options={stageOpts} placeholder="Pilih tahap…" />
          </Field>
          <Field label={needsVendor ? "Mitra Makloon (wajib untuk tahap ini)" : "Mitra Makloon"}>
            <MakloonSelect value={step.makloon_id} valueName={step.makloon_name}
              processType={step.process_type}
              triggerTestId={`wizard-partner-${index + 1}`}
              onSelect={(m) => set({ makloon_id: m.id, makloon_name: m.name })} />
          </Field>
          {noTransform ? (
            <Field label="Produk Hasil (output)">
              <div data-testid={`wizard-output-auto-${index + 1}`}
                className="flex h-[34px] items-center rounded-md border border-dashed border-[#D6E6FF] bg-[#F5F9FF] px-2 text-[11.5px] text-[#004099]">
                Otomatis: {inputProduct?.name || "kain yang sama"}
              </div>
            </Field>
          ) : (
            <Field label="Produk Hasil (output)">
              <ProductSelect value={step.output_product_id} valueName={step.output_name}
                triggerTestId={`wizard-output-${index + 1}`}
                onSelect={(p) => set({ output_product_id: p.id, output_name: p.name, output_unit: p.base_unit })} />
            </Field>
          )}
        </div>

        {/* FASE T — arti tahap: apakah kain berubah & apakah kain benar-benar dikirim */}
        {(stage || srv) && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] px-2.5 py-2"
            data-testid={`wizard-stage-meta-${index + 1}`}>
            <Layers size={13} className="text-[#6B219A]" />
            <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ${
              noTransform ? "bg-[#F3E9FA] text-[#6B219A]" : "bg-[#EAF2FF] text-[#0058CC]"}`}
              data-testid={`wizard-transform-badge-${index + 1}`}>
              {noTransform ? "Tidak mengubah kain — hanya biaya jasa" : "Mengubah tahap kain"}
            </span>
            <span className="rounded-full bg-white px-2 py-0.5 text-[10.5px] font-semibold text-[#3C3C43] border border-[#E5E5EA]"
              data-testid={`wizard-flow-badge-${index + 1}`}>
              {MATERIAL_FLOW_BADGE[flow] || flow}
            </span>
            <span className="text-[10.5px] text-[#6B6B73]">
              Aksi setelah disimpan: <b>{NEXT_ACTION_LABELS[serviceOnly ? "record_service" : "issue"]}</b>
            </span>
            {flowAllowed === "either" && (
              <div className="ml-auto flex items-center gap-1.5">
                <span className="text-[10.5px] font-semibold text-[#6B6B73]">Kainnya:</span>
                <KNSelect data-testid={`wizard-flow-${index + 1}`}
                  className="field !h-7 !py-0 !text-[11px] w-[230px]"
                  value={flow} onValueChange={(v) => set({ material_flow: v })}
                  options={FLOW_PICK_OPTIONS} />
              </div>
            )}
          </div>
        )}
        {stageWarnings.map((w, i) => (
          <p key={`sw${i}`} className="text-[11px] text-[#B26A00]" data-testid={`wizard-stage-warning-${index + 1}-${i}`}>
            <TriangleAlert size={11} className="mr-1 inline" />{w}
          </p>
        ))}

        <div className="grid gap-2.5 md:grid-cols-4">
          <Field label={`Bahan Masuk (${inputProduct?.base_unit || "unit"})`}>
            <input data-testid={`wizard-input-qty-${index + 1}`} className="field" value={step.input_qty}
              onChange={(e) => set({ input_qty: e.target.value })} disabled={index > 0}
              title={index > 0 ? "Otomatis = hasil langkah sebelumnya" : ""} />
          </Field>
          <Field label={noTransform ? "Susut (%) — tidak berlaku" : "Susut (%) — kosong = ikut kontrak"}>
            <input data-testid={`wizard-waste-${index + 1}`} className="field" value={noTransform ? "" : (step.waste_pct ?? "")}
              disabled={noTransform}
              placeholder={noTransform ? "0 — kain tidak berubah" : (est ? String(est.shrinkage_pct ?? "") : "kontrak")}
              onChange={(e) => set({ waste_pct: e.target.value })} />
          </Field>
          <Field label="Toleransi selisih (%)">
            <input data-testid={`wizard-tolerance-${index + 1}`} className="field" value={step.tolerance_pct ?? ""}
              placeholder={preview ? String(preview.tolerance_pct ?? "") : "kontrak"}
              onChange={(e) => set({ tolerance_pct: e.target.value })} />
          </Field>
          <Field label={noTransform ? "Barang sisa — tidak berlaku" : "Barang sisa (% bahan)"}>
            <input data-testid={`wizard-byproduct-${index + 1}`} className="field"
              value={noTransform ? "" : (step.byproduct_pct ?? "")} disabled={noTransform}
              onChange={(e) => set({ byproduct_pct: e.target.value })} />
          </Field>
        </div>

        {/* Kontrak & tarif */}
        <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#6B6B73]">
              <FileText size={12} /> Kontrak & Tarif
            </p>
            <button type="button" data-testid={`wizard-advanced-${index + 1}`} className="secondary-button !py-1 !px-2 text-[11px]"
              onClick={() => setShowAdvanced((v) => !v)}>
              {showAdvanced ? "Sembunyikan override" : "Override tarif / yield"}
            </button>
          </div>
          <p className="mt-1.5 text-[11px]" data-testid={`wizard-contract-info-${index + 1}`}>
            {preview?.contract_found ? (
              <span className="text-[#1B7F4B]">
                Kontrak aktif <b>{preview.contract.contract_number}</b> · basis{" "}
                <b>{FALLBACK_BASIS_LABELS[preview.contract.tariff_basis] || preview.contract.tariff_basis}</b>
                {" "}· tarif {formatCurrency(preview.contract.tariff_rate || 0)} · susut {preview.contract.shrinkage_pct}%
              </span>
            ) : (
              <span className="text-[#B26A00]">
                <TriangleAlert size={11} className="mr-1 inline" />
                Belum ada kontrak aktif untuk mitra & proses ini — isi tarif manual di bawah atau buat kontrak.
              </span>
            )}
            {stage?.tariff_basis_default && !step.tariff_basis && (
              <span className="ml-1 text-[#6B6B73]" data-testid={`wizard-basis-hint-${index + 1}`}>
                · usulan master: {FALLBACK_BASIS_LABELS[stage.tariff_basis_default] || stage.tariff_basis_default}
              </span>
            )}
          </p>

          {(showAdvanced || !preview?.contract_found) && (
            <div className="mt-2 grid gap-2.5 md:grid-cols-4">
              <Field label="Basis tarif">
                <KNSelect data-testid={`wizard-basis-${index + 1}`} className="field" value={step.tariff_basis || ""}
                  onValueChange={(v) => set({ tariff_basis: v })}
                  options={[{ value: "", label: "— ikut kontrak —" }, ...basisOptions]} />
              </Field>
              <Field label="Tarif (Rp per basis)">
                <input data-testid={`wizard-rate-${index + 1}`} className="field" value={step.tariff_rate ?? ""}
                  onChange={(e) => set({ tariff_rate: e.target.value })} />
              </Field>
              <Field label="PPI (basis pick)">
                <input data-testid={`wizard-ppi-${index + 1}`} className="field" value={step.ppi ?? ""}
                  onChange={(e) => set({ ppi: e.target.value })} placeholder="dari konstruksi produk" />
              </Field>
              <Field label="Formula custom (opsional)">
                <input data-testid={`wizard-formula-${index + 1}`} className="field" value={step.tariff_formula ?? ""}
                  onChange={(e) => set({ tariff_formula: e.target.value })}
                  placeholder="mis. basis_qty * rate * 1.1" />
              </Field>
              <Field label="Jumlah warna (screen)">
                <input data-testid={`wizard-colors-${index + 1}`} className="field" value={step.colors ?? ""}
                  onChange={(e) => set({ colors: e.target.value })} />
              </Field>
              <Field label="Jumlah repeat">
                <input data-testid={`wizard-repeats-${index + 1}`} className="field" value={step.repeats ?? ""}
                  onChange={(e) => set({ repeats: e.target.value })} />
              </Field>
              {!noTransform && (
                <>
                  <Field label="Override yield (0 = rumus GSM)">
                    <input data-testid={`wizard-yield-${index + 1}`} className="field" value={step.yield_factor ?? ""}
                      onChange={(e) => set({ yield_factor: e.target.value })} />
                  </Field>
                  <Field label="Alasan override yield (wajib bila diisi)">
                    <input data-testid={`wizard-yield-reason-${index + 1}`} className="field"
                      value={step.yield_override_reason ?? ""}
                      onChange={(e) => set({ yield_override_reason: e.target.value })} />
                  </Field>
                </>
              )}
              <div className="md:col-span-4">
                <AuxFeeEditor index={index} fees={step.aux_fees || []}
                  onChange={(fees) => set({ aux_fees: fees })} />
              </div>
            </div>
          )}
        </div>

        {/* Hasil hitung — angka antara terlihat (auditable) */}
        <div className="rounded-lg border border-[#DCE9FF] bg-[#F5F9FF] p-2.5" data-testid={`wizard-preview-${index + 1}`}>
          <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase text-[#0058CC]">
            <Calculator size={12} /> Perkiraan hasil & biaya {busy && <span className="text-[10px] font-normal text-[#6B6B73]">menghitung…</span>}
          </p>
          {previewErr && <p className="mt-1 text-[11px] text-[#C0392B]">{previewErr}</p>}
          {est ? (
            <>
              <div className="mt-1.5 grid grid-cols-2 gap-2 md:grid-cols-4">
                <Mini label={noTransform ? "Kain keluar (tidak berubah)" : "Perkiraan hasil"}
                  value={`${formatQty(est.expected_output_qty)} ${est.output_unit}`} tone="#0058CC" />
                <Mini label="Susut dipakai" value={`${est.shrinkage_pct}% (${est.shrinkage_source})`} />
                <Mini label="Toleransi selisih" value={`${preview.tolerance_pct}%`} />
                <Mini label="Ongkos jasa" value={tariff ? formatCurrency(tariff.amount) : "—"} tone="#1B7F4B" />
              </div>
              <details className="mt-2" data-testid={`wizard-explain-${index + 1}`}>
                <summary className="cursor-pointer text-[11px] font-semibold text-[#0058CC]">
                  <Info size={11} className="mr-1 inline" /> Lihat rumus & angka antara (bisa diaudit)
                </summary>
                <ul className="mt-1.5 space-y-1 text-[11px] text-[#3C3C43]">
                  {(est.explain || []).map((l, i) => <li key={`e${i}`}>• {l}</li>)}
                  {(tariff?.explain || []).map((l, i) => <li key={`t${i}`} className="text-[#1B7F4B]">• {l}</li>)}
                </ul>
              </details>
              {(est.warnings || []).map((w, i) => (
                <p key={i} className="mt-1 text-[11px] text-[#B26A00]"><TriangleAlert size={11} className="mr-1 inline" />{w}</p>
              ))}
              {preview?.tariff_error && (
                <p className="mt-1 text-[11px] text-[#C0392B]"><TriangleAlert size={11} className="mr-1 inline" />{preview.tariff_error}</p>
              )}
            </>
          ) : (
            <p className="mt-1 text-[11px] text-[#6B6B73]">
              <Wand2 size={11} className="mr-1 inline" />
              {noTransform
                ? "Lengkapi mitra & qty bahan — tahap ini tidak mengubah kain, jadi sistem hanya menghitung biaya jasanya."
                : "Lengkapi mitra, produk hasil & qty bahan — sistem menghitung otomatis dari GSM, lebar & susut kontrak."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function AuxFeeEditor({ index, fees, onChange }) {
  const add = () => onChange([...fees, { code: "", label: "", basis: "lumpsum", amount: "" }]);
  const upd = (i, k, v) => onChange(fees.map((f, idx) => (idx === i ? { ...f, [k]: v } : f)));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10.5px] font-semibold text-[#6B6B73]">Biaya tambahan (screen, repeat, dll)</span>
        <button type="button" data-testid={`wizard-add-aux-${index + 1}`} className="secondary-button !py-0.5 !px-2 text-[10.5px]" onClick={add}>+ Biaya</button>
      </div>
      {(fees || []).map((f, i) => (
        <div key={i} className="mb-1 grid grid-cols-[1.2fr_1fr_0.9fr_auto] items-center gap-1.5">
          <input className="field !py-1.5 text-[11.5px]" placeholder="Nama biaya" value={f.label}
            onChange={(e) => upd(i, "label", e.target.value)} data-testid={`wizard-aux-label-${index + 1}-${i}`} />
          <KNSelect className="field !py-1.5 text-[11.5px]" value={f.basis} onValueChange={(v) => upd(i, "basis", v)}
            options={AUX_BASIS_OPTIONS} />
          <input className="field !py-1.5 text-[11.5px]" placeholder="Rp" value={f.amount}
            onChange={(e) => upd(i, "amount", e.target.value)} data-testid={`wizard-aux-amount-${index + 1}-${i}`} />
          <button type="button" className="icon-button text-red-400" onClick={() => onChange(fees.filter((_, x) => x !== i))}>
            <Trash2 size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10.5px] font-semibold text-[#6B6B73]">{label}</span>
      {children}
    </label>
  );
}

function Mini({ label, value, tone = "#1C1C1E" }) {
  return (
    <div>
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[12px] font-bold tabular-nums" style={{ color: tone }}>{value}</p>
    </div>
  );
}
