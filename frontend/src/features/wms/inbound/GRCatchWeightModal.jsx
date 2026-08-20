import { X, CheckCircle } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { formatQty } from "../inventory/inventoryConstants";
import { kgPerBaseUnit } from "../../../utils/uom";

const GRADE_OPTIONS = [
  { value: "A", label: "Grade A" },
  { value: "B", label: "Grade B" },
  { value: "C", label: "Grade C" },
  { value: "reject", label: "Reject" },
];

const r2 = (n) => Math.round((Number(n) + Number.EPSILON) * 100) / 100;
// FASE B/C — berat per 1 BASE UNIT produk (yard ≠ meter!). Memakai util bersama agar
// prefill berat di form GR SAMA dengan perhitungan server (tanpa selisih ±9,4%).
function kgPerUnit(p) {
  return kgPerBaseUnit(p);
}

/**
 * GRCatchWeightModal (Fase 8) — entri roll saat Goods Receipt.
 * Operator mengisi panjang (m) + berat (kg) per roll; pasangan kg↔m diisi otomatis
 * dari faktor produk (gramasi×lebar / kg_per_meter) namun bisa di-override (catch-weight aktual).
 * Validasi Σ kontribusi (berat utk PO per-kg, panjang utk PO per-meter) ≈ qty diterima.
 */
export default function GRCatchWeightModal({ task, product, rolls, setRolls, onSubmit, onClose,
                                            submitting, lotFields, setLotFields, lotSettings }) {
  if (!task) return null;
  const isKg = (task.unit || "").toLowerCase() === "kg";
  const kgm = kgPerUnit(product);
  const baseUnit = product?.base_unit || "meter";
  const sumLen = r2(rolls.reduce((a, x) => a + (Number(x.length) || 0), 0));
  const sumWt = r2(rolls.reduce((a, x) => a + (Number(x.weight) || 0), 0));
  const expected = Number(task.received_qty) || 0;
  const taskTotal = isKg ? sumWt : sumLen;
  const tol = Math.max(0.5, r2(expected * 0.02));
  const matched = Math.abs(taskTotal - expected) <= tol;
  // FASE C (D-10/D-27) — kelengkapan lot: wajib di form, penegakan server warn/block
  const lf = lotFields || { supplier_lot: "", lot_number: "", shade_ref: "" };
  const blocking = (lotSettings?.enforcement_mode || "warn") === "block";
  const needSupplierLot = (lotSettings?.require_supplier_lot !== false) && !lf.supplier_lot.trim();
  const needDyeLot = (lotSettings?.require_dye_lot !== false)
    && rolls.some((r) => !(r.dye_lot || "").trim());
  const lotIncomplete = needSupplierLot || needDyeLot;

  const setField = (i, k, v) => setRolls(rolls.map((x, idx) => (idx === i ? { ...x, [k]: v } : x)));
  const updateDerived = (i, k, v) => {
    const row = { ...rolls[i], [k]: v };
    if (kgm > 0) {
      if (k === "weight" && (!Number(rolls[i].length) || rolls[i]._autoLen)) { row.length = r2((Number(v) || 0) / kgm); row._autoLen = true; }
      if (k === "length" && (!Number(rolls[i].weight) || rolls[i]._autoWt)) { row.weight = r2((Number(v) || 0) * kgm); row._autoWt = true; }
      if (k === "length") row._autoLen = false;
      if (k === "weight") row._autoWt = false;
    }
    setRolls(rolls.map((x, idx) => (idx === i ? row : x)));
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      onClick={() => !submitting && onClose()} data-testid="gr-catchweight-modal">
      <div className="bg-white rounded-xl p-5 w-full max-w-2xl max-h-[88vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-[14px] font-bold mb-1">Goods Receipt — Rincian Roll</h3>
        <p className="text-[11px] text-[#6B6B73] mb-3">
          {task.sku} · {task.product_name} — diterima <b>{formatQty(expected)} {task.unit}</b>
          {kgm > 0
            ? <span className="ml-1 text-[#0058CC]">· catch-weight aktif: 1 {baseUnit} ≈ {kgm.toFixed(3)} kg</span>
            : <span className="ml-1 text-amber-600">· tanpa faktor kg/m (isi panjang & berat manual)</span>}
        </p>

        <div className="rounded-md border border-[#EFF0F2] overflow-hidden mb-3" data-testid="gr-lot-section">
          <div className="flex items-center gap-1.5 px-2 py-1.5 bg-[#FAFBFC] border-b border-[#EFF0F2]">
            <span className="text-[10px] font-bold uppercase text-[#6B6B73]">
              Identitas Lot (Fase C · 1 batch penerimaan = 1 lot per dye lot)
            </span>
            <span className={`ml-auto text-[10px] font-semibold ${blocking ? "text-rose-600" : "text-amber-600"}`}>
              {blocking ? "Mode blokir: wajib diisi" : "Mode peringatan: sangat disarankan"}
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 px-2 py-2">
            <label className="grid gap-1">
              <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
                Nomor lot supplier {needSupplierLot && <span className="text-rose-500">*</span>}
              </span>
              <input data-testid="gr-supplier-lot" type="text" value={lf.supplier_lot}
                placeholder="mis. SUP-2024-118"
                onChange={(e) => setLotFields({ ...lf, supplier_lot: e.target.value })}
                className={`border rounded px-2 py-1 text-[12px] ${needSupplierLot ? "border-amber-400 bg-amber-50" : "border-[#E5E5EA]"}`} />
            </label>
            <label className="grid gap-1">
              <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
                Referensi shade (opsional)
              </span>
              <input data-testid="gr-shade-ref" type="text" value={lf.shade_ref}
                placeholder="mis. SHADE-A"
                onChange={(e) => setLotFields({ ...lf, shade_ref: e.target.value })}
                className="border border-[#E5E5EA] rounded px-2 py-1 text-[12px]" />
            </label>
            <label className="grid gap-1">
              <span className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">
                Tempel ke lot yang ada (opsional)
              </span>
              <input data-testid="gr-lot-number" type="text" value={lf.lot_number}
                placeholder="mis. KSC/LOT-2607-0012"
                onChange={(e) => setLotFields({ ...lf, lot_number: e.target.value })}
                className="border border-[#E5E5EA] rounded px-2 py-1 text-[12px]" />
            </label>
          </div>
          {lotIncomplete && (
            <p data-testid="gr-lot-warning" className="px-2 pb-2 text-[10.5px] text-amber-700">
              Data lot belum lengkap{needSupplierLot ? " · nomor lot supplier kosong" : ""}
              {needDyeLot ? " · ada roll tanpa dye lot" : ""}. Traceability & recall tidak akan
              lengkap{blocking ? " — penerimaan akan DITOLAK server." : "."}
            </p>
          )}
        </div>

        <div className="rounded-md border border-[#EFF0F2] overflow-hidden mb-3">
          <div className="grid grid-cols-[1fr_1fr_1fr_90px_36px] gap-1 px-2 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
            <span>Panjang ({baseUnit})</span><span>Berat (kg)</span><span>Dye Lot</span><span>Grade</span><span></span>
          </div>
          {rolls.map((row, i) => (
            <div key={i} data-testid={`gr-roll-row-${i}`} className="grid grid-cols-[1fr_1fr_1fr_90px_36px] gap-1 px-2 py-1.5 border-b border-[#EFF0F2] last:border-0 items-center">
              <input data-testid={`gr-roll-length-${i}`} type="number" value={row.length} placeholder="m"
                onChange={(e) => updateDerived(i, "length", parseFloat(e.target.value) || 0)}
                className="border border-[#E5E5EA] rounded px-2 py-1 text-[12px]" />
              <input data-testid={`gr-roll-weight-${i}`} type="number" value={row.weight} placeholder="kg"
                onChange={(e) => updateDerived(i, "weight", parseFloat(e.target.value) || 0)}
                className="border border-[#E5E5EA] rounded px-2 py-1 text-[12px]" />
              <input data-testid={`gr-roll-dyelot-${i}`} type="text" value={row.dye_lot} placeholder="DL-…"
                onChange={(e) => setField(i, "dye_lot", e.target.value)}
                className={`border rounded px-2 py-1 text-[12px] ${!(row.dye_lot || "").trim() && (lotSettings?.require_dye_lot !== false) ? "border-amber-400 bg-amber-50" : "border-[#E5E5EA]"}`} />
              <KNSelect className="border border-[#E5E5EA] rounded px-1 py-1 text-[12px] bg-white text-left"
                value={row.grade} onValueChange={(v) => setField(i, "grade", v)} options={GRADE_OPTIONS} />
              <button data-testid={`gr-roll-remove-${i}`} onClick={() => setRolls(rolls.filter((_, idx) => idx !== i))}
                disabled={rolls.length <= 1} className="text-red-400 hover:text-red-600 disabled:opacity-30 justify-self-center">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between mb-3">
          <button data-testid="gr-add-roll" onClick={() => setRolls([...rolls, { length: 0, weight: 0, dye_lot: "", grade: "A" }])}
            className="text-[11px] font-semibold text-[#0058CC] flex items-center gap-1">+ Tambah Roll</button>
          <div data-testid="gr-roll-totals" className={`text-[11px] font-semibold ${matched ? "text-green-700" : "text-amber-600"}`}>
            Σ {rolls.length} roll: {sumLen} {baseUnit} · {sumWt} kg
            <span className="ml-2 font-normal text-[#6B6B73]">
              (validasi {isKg ? "berat" : "panjang"}: {taskTotal}/{r2(expected)} {task.unit}{matched ? " ✓" : ` — selisih > ±${tol}`})
            </span>
          </div>
        </div>

        <div className="flex gap-2">
          <button data-testid="gr-submit-complete" onClick={onSubmit} disabled={submitting || !matched}
            className="flex-1 bg-[#007AFF] hover:bg-[#0056B3] text-white rounded-lg px-4 py-2 text-[12px] font-semibold disabled:opacity-50 flex items-center justify-center gap-1.5">
            <CheckCircle size={13} /> {submitting ? "Memproses…" : "Selesaikan Penerimaan"}
          </button>
          <button onClick={onClose} disabled={submitting}
            className="bg-[#F2F2F7] text-[#3C3C43] rounded-lg px-4 py-2 text-[12px] font-semibold disabled:opacity-50">Batal</button>
        </div>
      </div>
    </div>
  );
}
