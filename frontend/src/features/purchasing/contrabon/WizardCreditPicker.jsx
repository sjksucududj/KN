/**
 * FASE G-7 — pemilih **POTONGAN OTOMATIS** di wizard kontrabon.
 *
 * Dokumen yang ditawarkan hanya yang MEMANG tersedia (dikirim `GET /contra-bons/prepare`):
 * nota debit retur beli yang sudah disetujui berkonsekuensi potong hutang, dan uang muka
 * supplier yang belum terpakai. Nota/uang muka yang sudah dipotong di kontrabon lain tidak
 * pernah muncul di sini — penjaganya tetap backend (INV-CB-04), layar hanya menawarkan.
 */
import { formatCurrency } from "../../../utils/formatters";
import { fmtDate } from "./contraBonApi";

const KIND_HINT = {
  purchase_return: "Retur beli (nota debit) — pelunasan non-kas, tanpa jurnal baru",
  supplier_advance: "Uang muka / titipan ke supplier — jurnal Dr Hutang / Cr Uang Muka",
};

export default function WizardCreditPicker({ credits, picked, amounts, onTogglePick,
  onChangeAmount }) {
  if (!credits.length) return null;
  return (
    <div className="overflow-hidden rounded-lg border border-[#CBDCF7]"
      data-testid="cb-create-credits">
      <div className="flex items-center justify-between bg-[#F2F7FF] px-3 py-1.5">
        <p className="text-[11px] font-bold text-[#0058CC]">
          Potongan tersedia untuk supplier ini ({credits.length})
        </p>
        <span className="text-[10.5px] text-[#1C1C1E]">
          Centang untuk langsung dipotong di kontrabon ini
        </span>
      </div>
      {credits.map((c) => (
        <div key={c.ref_id} data-testid={`cb-create-cred-row-${c.ref_id}`}
          className="flex items-center justify-between gap-3 border-t border-[#EFF0F2] bg-white px-3 py-1.5">
          <label className="flex min-w-0 items-start gap-2">
            <input type="checkbox" className="mt-[3px]"
              data-testid={`cb-create-cred-${c.ref_id}`}
              checked={!!picked[c.ref_id]}
              onChange={(e) => onTogglePick(c.ref_id, e.target.checked)} />
            <span className="min-w-0">
              <span className="block text-[11.5px] font-semibold text-[#1C1C1E]">{c.label}</span>
              <span className="block text-[10px] text-[#8E8E93]">
                {KIND_HINT[c.kind] || "Dokumen potongan"}
                {c.po_number ? ` · ${c.po_number}` : ""}
                {c.date ? ` · ${fmtDate(c.date)}` : ""}
              </span>
            </span>
          </label>
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-[10.5px] text-[#8E8E93] tabular-nums">sisa {formatCurrency(c.amount)}</span>
            <input type="number" min={0} step={1000}
              data-testid={`cb-create-cred-amount-${c.ref_id}`}
              className="input-field w-[130px] text-right"
              disabled={!picked[c.ref_id]}
              placeholder={String(Math.round(Number(c.amount || 0)))}
              value={amounts[c.ref_id] ?? ""}
              onChange={(e) => onChangeAmount(c.ref_id, e.target.value)} />
          </div>
        </div>
      ))}
      <p className="border-t border-[#EFF0F2] bg-[#FAFBFC] px-3 py-1.5 text-[10.5px] text-[#6B6B73]">
        Satu nota debit / uang muka hanya boleh dipotong SEKALI (INV-CB-04) — yang sudah
        terpakai di kontrabon lain tidak muncul di sini. Denda supplier & selisih 3-way
        ditambahkan dari panel detail setelah kontrabon terbit.
      </p>
    </div>
  );
}
