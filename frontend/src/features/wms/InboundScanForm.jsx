// Form input Goods-Receipt scan (grid field) untuk InboundScanInterface, dipisah
// agar file utama di bawah batas guardrail. State tetap dikelola parent via props.
//
// FASE F-1 — kotak "Actual Qty" digantikan `ReceiveUomPanel`: operator memilih satuan
// (satuan KN atau **satuan supplier**) lalu mengetik qty apa adanya dari surat jalan;
// konversi + jejaknya dihitung server.
import KNSelect from "../../components/KNSelect";
import ReceiveUomPanel from "./inbound/ReceiveUomPanel";

// P0-4 — grade tekstil aktual (A | A+ | B | C | BS)
export const GRADE_OPTIONS = [
  { value: "A", label: "Grade A" },
  { value: "A+", label: "Grade A+" },
  { value: "B", label: "Grade B" },
  { value: "C", label: "Grade C" },
  { value: "BS", label: "BS (Barang Sisa)" },
];

export default function InboundScanForm({ scanData, setScanData, uom }) {
  return (
    <div className="space-y-2">
      {/* FASE F-1 — Qty & satuan (boleh satuan supplier) + pratinjau konversi */}
      <ReceiveUomPanel
        uom={uom}
        docUom={scanData.doc_uom}
        docQty={scanData.doc_qty}
        onUomChange={(v) => setScanData({ ...scanData, doc_uom: v })}
        onQtyChange={(v) => setScanData({ ...scanData, doc_qty: v })} />

      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="mb-1 block text-[10px] font-semibold text-[#6B6B73]">Batch</label>
          <input type="text" value={scanData.batch}
            data-testid="scan-batch-input"
            onChange={e => setScanData({ ...scanData, batch: e.target.value })}
            className="w-full rounded-lg border border-[#E5E5EA] px-2 py-1.5 text-sm" placeholder="BTK-001" />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold text-[#6B6B73]">Lot</label>
          <input type="text" value={scanData.lot}
            data-testid="scan-lot-input"
            onChange={e => setScanData({ ...scanData, lot: e.target.value })}
            className="w-full rounded-lg border border-[#E5E5EA] px-2 py-1.5 text-sm" placeholder="LOT-001" />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold text-[#6B6B73]">Dye Lot</label>
          <input type="text" value={scanData.dye_lot}
            data-testid="scan-dye-lot-input"
            onChange={e => setScanData({ ...scanData, dye_lot: e.target.value })}
            className="w-full rounded-lg border border-[#E5E5EA] px-2 py-1.5 text-sm" placeholder="DL-RED-01" />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold text-[#6B6B73]">Grade</label>
          <KNSelect
            data-testid="scan-grade-select"
            className="w-full rounded-lg border border-[#E5E5EA] bg-white px-2 py-1.5 text-left text-sm"
            value={scanData.grade}
            onValueChange={(v) => setScanData({ ...scanData, grade: v })}
            options={GRADE_OPTIONS}
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold text-[#6B6B73]">Roll ID</label>
          <input type="text" value={scanData.roll_id}
            data-testid="scan-roll-input"
            onChange={e => setScanData({ ...scanData, roll_id: e.target.value })}
            className="w-full rounded-lg border border-[#E5E5EA] px-2 py-1.5 text-sm" placeholder="ROLL-001" />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-semibold text-[#6B6B73]">Bin Location *</label>
          <input type="text" value={scanData.bin_id}
            data-testid="scan-bin-input"
            onChange={e => setScanData({ ...scanData, bin_id: e.target.value })}
            className="w-full rounded-lg border border-[#E5E5EA] px-2 py-1.5 text-sm" placeholder="A1-01" />
        </div>
      </div>
    </div>
  );
}
