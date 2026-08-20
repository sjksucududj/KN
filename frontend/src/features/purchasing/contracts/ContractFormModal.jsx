/**
 * ContractFormModal (FASE D/E) — buat/ubah kontrak mitra & supplier.
 * Basis tarif BEBAS (D-07) + biaya tambahan + susut standar (D-05) + toleransi (D-09).
 */
import { useEffect, useMemo, useState } from "react";
import { FileText, Plus, Save, Trash2, X } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import KNSelect from "../../../components/KNSelect";
import MakloonSelect from "../../../components/MakloonSelect";
import ProductSelect from "../../../components/ProductSelect";
import {
  AUX_BASIS_OPTIONS, createContract, FALLBACK_BASIS_LABELS, fetchEnum, patchContract, tariffPreview,
} from "../makloon/makloonApi";
import { overlayDismiss } from "@/utils/overlayDismiss";

const TYPE_OPTS = [
  { value: "makloon", label: "Kontrak Makloon (jasa proses)" },
  { value: "purchase", label: "Kontrak Pembelian (barang supplier)" },
];
const QTY_SOURCE_OPTS = [
  { value: "output", label: "Qty hasil (output)" },
  { value: "input", label: "Qty bahan (input)" },
];

export default function ContractFormModal({ contract, selectedEntity, onClose, onSaved, onError }) {
  const isEdit = Boolean(contract?.id);
  const [processOptions, setProcessOptions] = useState([]);
  const [basisOptions, setBasisOptions] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [sim, setSim] = useState(null);
  const [simQty, setSimQty] = useState("100");

  const [f, setF] = useState(() => ({
    contract_type: contract?.contract_type || "makloon",
    partner_id: contract?.partner_id || "",
    partner_name: contract?.partner_name || "",
    title: contract?.title || "",
    process_type: contract?.process_type || "tenun",
    product_id: contract?.product_id || "",
    product_name: contract?.product_name || "",
    input_product_id: contract?.input_product_id || "",
    tariff_basis: contract?.tariff_basis || "meter",
    tariff_rate: String(contract?.tariff_rate ?? ""),
    tariff_formula: contract?.tariff_formula || "",
    tariff_qty_source: contract?.tariff_qty_source || "output",
    ppi: String(contract?.ppi ?? ""),
    min_charge: String(contract?.min_charge ?? ""),
    shrinkage_pct: String(contract?.shrinkage_pct ?? ""),
    tolerance_pct: contract?.tolerance_pct == null ? "" : String(contract.tolerance_pct),
    yield_factor: String(contract?.yield_factor ?? ""),
    byproduct_pct: String(contract?.byproduct_pct ?? ""),
    moq: String(contract?.moq ?? ""),
    lead_time_days: String(contract?.lead_time_days ?? ""),
    valid_from: contract?.valid_from || "",
    valid_to: contract?.valid_to || "",
    status: contract?.status || "active",
    notes: contract?.notes || "",
    aux_fees: (contract?.aux_fees || []).map((a) => ({ ...a, amount: String(a.amount ?? "") })),
  }));
  const set = (patch) => setF((p) => ({ ...p, ...patch }));

  useEffect(() => {
    (async () => {
      const [pe, be, sup] = await Promise.all([
        fetchEnum("process_type").catch(() => null),
        fetchEnum("tariff_basis").catch(() => null),
        axios.get(`${API}/suppliers`).catch(() => ({ data: [] })),
      ]);
      setProcessOptions((pe?.values || []).map((v) => ({ value: v.value, label: v.label })));
      setBasisOptions((be?.values || Object.entries(FALLBACK_BASIS_LABELS).map(([value, label]) => ({ value, label })))
        .map((v) => ({ value: v.value, label: v.label })));
      setSuppliers(Array.isArray(sup.data) ? sup.data : []);
    })();
  }, []);

  const supOpts = useMemo(
    () => [{ value: "", label: "— Pilih supplier —" }, ...suppliers.map((s) => ({ value: s.id, label: s.name }))],
    [suppliers]);

  const runSim = async () => {
    setErr("");
    if (!f.product_id) { setErr("Pilih produk dulu untuk simulasi tarif."); return; }
    try {
      const res = await tariffPreview({
        product_id: f.product_id, qty: parseFloat(simQty) || 0,
        tariff_basis: f.tariff_basis, tariff_rate: parseFloat(f.tariff_rate) || 0,
        tariff_formula: f.tariff_formula, min_charge: parseFloat(f.min_charge) || 0,
        ppi: parseFloat(f.ppi) || 0, colors: 1, repeats: 1,
        aux_fees: (f.aux_fees || []).filter((a) => parseFloat(a.amount) > 0)
          .map((a) => ({ ...a, amount: parseFloat(a.amount) || 0 })),
      });
      setSim(res);
    } catch (e) { setErr(e.response?.data?.detail || "Simulasi tarif gagal."); }
  };

  const save = async () => {
    setErr("");
    if (!f.partner_id) { setErr("Mitra/supplier wajib dipilih."); return; }
    if (f.contract_type === "makloon" && !f.process_type) { setErr("Jenis proses wajib diisi."); return; }
    setSaving(true);
    const body = {
      contract_type: f.contract_type, partner_id: f.partner_id, partner_name: f.partner_name,
      title: f.title, process_type: f.contract_type === "makloon" ? f.process_type : "",
      product_id: f.product_id, input_product_id: f.input_product_id,
      tariff_basis: f.tariff_basis, tariff_rate: parseFloat(f.tariff_rate) || 0,
      tariff_formula: f.tariff_formula, tariff_qty_source: f.tariff_qty_source,
      ppi: parseFloat(f.ppi) || 0, min_charge: parseFloat(f.min_charge) || 0,
      shrinkage_pct: parseFloat(f.shrinkage_pct) || 0,
      yield_factor: parseFloat(f.yield_factor) || 0,
      byproduct_pct: parseFloat(f.byproduct_pct) || 0,
      moq: parseFloat(f.moq) || 0, lead_time_days: parseInt(f.lead_time_days, 10) || 0,
      valid_from: f.valid_from, valid_to: f.valid_to, status: f.status, notes: f.notes,
      aux_fees: (f.aux_fees || []).filter((a) => parseFloat(a.amount) > 0)
        .map((a) => ({ code: a.code || a.label || "biaya", label: a.label || a.code || "Biaya",
                       basis: a.basis || "lumpsum", amount: parseFloat(a.amount) || 0 })),
      entity_id: selectedEntity && selectedEntity !== "all" ? selectedEntity : "",
    };
    if (f.tolerance_pct !== "") body.tolerance_pct = parseFloat(f.tolerance_pct);
    try {
      if (isEdit) await patchContract(contract.id, body);
      else await createContract(body);
      onSaved?.();
    } catch (e) {
      const d = e.response?.data?.detail;
      setErr(typeof d === "string" ? d : "Gagal menyimpan kontrak.");
      setSaving(false);
    }
  };

  const addAux = () => set({ aux_fees: [...(f.aux_fees || []), { code: "", label: "", basis: "lumpsum", amount: "" }] });
  const updAux = (i, k, v) => set({ aux_fees: f.aux_fees.map((a, idx) => (idx === i ? { ...a, [k]: v } : a)) });

  return (
    <div data-testid="contract-form-modal" className="fixed inset-0 z-[170] flex items-center justify-center bg-black/50 p-4" {...overlayDismiss(onClose)}>
      <div className="flex max-h-[94vh] w-full max-w-[820px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="flex items-center gap-2 text-[15px] font-bold">
            <FileText size={16} className="text-[#0058CC]" /> {isEdit ? `Ubah ${contract.contract_number}` : "Kontrak Baru"}
          </h2>
          <button className="icon-button" onClick={onClose} data-testid="contract-form-close"><X size={18} /></button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {err && <div className="rounded-lg bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]" data-testid="contract-form-error">{err}</div>}

          <div className="grid gap-2.5 md:grid-cols-3">
            <Field label="Jenis Kontrak">
              <KNSelect data-testid="contract-type" className="field" value={f.contract_type}
                onValueChange={(v) => set({ contract_type: v, partner_id: "", partner_name: "" })}
                options={TYPE_OPTS} disabled={isEdit} />
            </Field>
            {f.contract_type === "makloon" ? (
              <>
                <Field label="Mitra Makloon">
                  <MakloonSelect value={f.partner_id} valueName={f.partner_name} processType={f.process_type}
                    triggerTestId="contract-partner" onSelect={(m) => set({ partner_id: m.id, partner_name: m.name })} />
                </Field>
                <Field label="Jenis Proses">
                  <KNSelect data-testid="contract-process" className="field" value={f.process_type}
                    onValueChange={(v) => set({ process_type: v })} options={processOptions} />
                </Field>
              </>
            ) : (
              <>
                <Field label="Supplier">
                  <KNSelect data-testid="contract-supplier" className="field" value={f.partner_id}
                    onValueChange={(v) => set({ partner_id: v, partner_name: suppliers.find((s) => s.id === v)?.name || "" })}
                    options={supOpts} />
                </Field>
                <Field label="Judul Kontrak">
                  <input data-testid="contract-title" className="field" value={f.title} onChange={(e) => set({ title: e.target.value })} />
                </Field>
              </>
            )}
            <Field label="Produk (kosong = semua produk)">
              <ProductSelect value={f.product_id} valueName={f.product_name} triggerTestId="contract-product"
                onSelect={(p) => set({ product_id: p.id, product_name: p.name })} />
            </Field>
            {f.contract_type === "makloon" && (
              <Field label="Judul Kontrak">
                <input data-testid="contract-title-mk" className="field" value={f.title} onChange={(e) => set({ title: e.target.value })}
                  placeholder="mis. Tenun katun 2026 — per pick" />
              </Field>
            )}
            <Field label="Dasar qty tarif">
              <KNSelect data-testid="contract-qty-source" className="field" value={f.tariff_qty_source}
                onValueChange={(v) => set({ tariff_qty_source: v })} options={QTY_SOURCE_OPTS} />
            </Field>
          </div>

          <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-3">
            <p className="mb-2 text-[11px] font-bold uppercase text-[#6B6B73]">Tarif (basis bebas · D-07)</p>
            <div className="grid gap-2.5 md:grid-cols-4">
              <Field label="Basis tarif">
                <KNSelect data-testid="contract-basis" className="field" value={f.tariff_basis}
                  onValueChange={(v) => set({ tariff_basis: v })} options={basisOptions} />
              </Field>
              <Field label="Tarif (Rp per basis)">
                <input data-testid="contract-rate" className="field" value={f.tariff_rate} onChange={(e) => set({ tariff_rate: e.target.value })} />
              </Field>
              <Field label="PPI (basis pick)">
                <input data-testid="contract-ppi" className="field" value={f.ppi} onChange={(e) => set({ ppi: e.target.value })}
                  placeholder="kosong = dari konstruksi produk" />
              </Field>
              <Field label="Tagihan minimum (Rp)">
                <input data-testid="contract-min-charge" className="field" value={f.min_charge} onChange={(e) => set({ min_charge: e.target.value })} />
              </Field>
              <div className="md:col-span-4">
                <Field label="Formula custom (opsional — var: qty_base, basis_qty, rate, gsm, lebar, ppi, roll_count, colors, repeats)">
                  <input data-testid="contract-formula" className="field" value={f.tariff_formula}
                    onChange={(e) => set({ tariff_formula: e.target.value })} placeholder="mis. basis_qty * rate + colors * 150000" />
                </Field>
              </div>
            </div>

            <div className="mt-2">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10.5px] font-semibold text-[#6B6B73]">Biaya tambahan (screen, repeat, dll)</span>
                <button type="button" className="secondary-button !py-0.5 !px-2 text-[10.5px]" onClick={addAux} data-testid="contract-add-aux">+ Biaya</button>
              </div>
              {(f.aux_fees || []).map((a, i) => (
                <div key={i} className="mb-1 grid grid-cols-[1.2fr_1fr_0.9fr_auto] items-center gap-1.5">
                  <input className="field !py-1.5 text-[11.5px]" placeholder="Nama biaya" value={a.label}
                    data-testid={`contract-aux-label-${i}`} onChange={(e) => updAux(i, "label", e.target.value)} />
                  <KNSelect className="field !py-1.5 text-[11.5px]" value={a.basis} onValueChange={(v) => updAux(i, "basis", v)} options={AUX_BASIS_OPTIONS} />
                  <input className="field !py-1.5 text-[11.5px]" placeholder="Rp" value={a.amount}
                    data-testid={`contract-aux-amount-${i}`} onChange={(e) => updAux(i, "amount", e.target.value)} />
                  <button type="button" className="icon-button text-red-400" onClick={() => set({ aux_fees: f.aux_fees.filter((_, x) => x !== i) })}>
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>

            <div className="mt-2 flex flex-wrap items-end gap-2">
              <Field label="Simulasi qty">
                <input data-testid="contract-sim-qty" className="field !py-1.5 !w-32 text-[11.5px]" value={simQty} onChange={(e) => setSimQty(e.target.value)} />
              </Field>
              <button type="button" className="secondary-button !py-1.5 text-[11.5px]" onClick={runSim} data-testid="contract-simulate">Simulasikan tarif</button>
              {sim && (
                <div className="flex-1 rounded border border-[#DCE9FF] bg-[#F5F9FF] px-2.5 py-1.5 text-[11px]" data-testid="contract-sim-result">
                  <b>Hasil: Rp {Number(sim.amount || 0).toLocaleString("id-ID")}</b>
                  <ul className="mt-1 space-y-0.5 text-[10.5px] text-[#3C3C43]">
                    {(sim.explain || []).map((l, i) => <li key={i}>• {l}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>

          <div className="grid gap-2.5 md:grid-cols-4">
            <Field label="Susut standar (%) — D-05">
              <input data-testid="contract-shrinkage" className="field" value={f.shrinkage_pct} onChange={(e) => set({ shrinkage_pct: e.target.value })} />
            </Field>
            <Field label="Toleransi selisih (%) — D-09">
              <input data-testid="contract-tolerance" className="field" value={f.tolerance_pct} onChange={(e) => set({ tolerance_pct: e.target.value })}
                placeholder="kosong = kebijakan global" />
            </Field>
            <Field label="Yield override (0 = rumus GSM)">
              <input data-testid="contract-yield" className="field" value={f.yield_factor} onChange={(e) => set({ yield_factor: e.target.value })} />
            </Field>
            <Field label="Barang sisa (%)">
              <input data-testid="contract-byproduct" className="field" value={f.byproduct_pct} onChange={(e) => set({ byproduct_pct: e.target.value })} />
            </Field>
            <Field label="MOQ">
              <input data-testid="contract-moq" className="field" value={f.moq} onChange={(e) => set({ moq: e.target.value })} />
            </Field>
            <Field label="Lead time (hari)">
              <input data-testid="contract-lead-time" className="field" value={f.lead_time_days} onChange={(e) => set({ lead_time_days: e.target.value })} />
            </Field>
            <Field label="Berlaku dari">
              <input type="date" data-testid="contract-valid-from" className="field" value={f.valid_from} onChange={(e) => set({ valid_from: e.target.value })} />
            </Field>
            <Field label="Berlaku sampai">
              <input type="date" data-testid="contract-valid-to" className="field" value={f.valid_to} onChange={(e) => set({ valid_to: e.target.value })} />
            </Field>
            <div className="md:col-span-4">
              <Field label="Catatan">
                <input data-testid="contract-notes" className="field" value={f.notes} onChange={(e) => set({ notes: e.target.value })} />
              </Field>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" onClick={save} disabled={saving} data-testid="contract-save">
            <Save size={13} /> {saving ? "Menyimpan…" : "Simpan Kontrak"}
          </button>
        </div>
      </div>
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
