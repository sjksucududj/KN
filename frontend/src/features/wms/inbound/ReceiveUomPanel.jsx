/**
 * ReceiveUomPanel (FASE F-1 · F1-01/F1-02/F1-05/F1-06) — blok input **Qty & Satuan**
 * pada layar penerimaan barang.
 *
 * Masalah yang dijawab: surat jalan supplier memakai satuan supplier (cone/roll/lembar),
 * stok KN memakai kg/yard. Sebelum ini operator mengalikan sendiri — rawan salah dan
 * tidak ada jejak. Sekarang operator memilih satuan, mengetik qty **apa adanya**, dan
 * melihat hasil konversi + sumber faktor + sisa PO dalam dua satuan SEBELUM submit.
 *
 * Semua angka berasal dari server (`preview-uom`) — komponen ini tidak menghitung faktor.
 */
import { AlertTriangle, ArrowRight, Info, Scale } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import { RECEIVE_SOURCE_LABEL } from "../../../hooks/useReceivingUom";
import { formatQty } from "../../../utils/formatters";

export default function ReceiveUomPanel({
  uom,                    // hasil useReceivingUom()
  docUom, docQty,
  onUomChange, onQtyChange,
  disabled = false,
}) {
  const opt = uom?.options;
  const taskUom = opt?.task_uom || "";
  const list = opt?.options || [];
  const supplierMode = Boolean(docUom && taskUom && docUom !== taskUom);
  const chosen = list.find((o) => o.value === docUom);
  const pv = uom?.preview;
  const trail = pv?.trail;
  const blocked = pv?.level === "block";

  const remainingLabel = () => {
    if (!opt) return "";
    const base = `${formatQty(opt.remaining_qty)} ${taskUom}`;
    if (supplierMode && chosen?.remaining !== null && chosen?.remaining !== undefined) {
      return `${base} ≈ ${formatQty(chosen.remaining)} ${docUom}`;
    }
    return base;
  };

  return (
    <div data-testid="receive-uom-panel" className="rounded-lg border border-[#E5F0FF] bg-[#F7FBFF] p-2">
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-1">
        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-[#0058CC]">
          <Scale size={11} /> Qty diterima — boleh pakai satuan supplier
        </span>
        {opt && (
          <span data-testid="receive-uom-remaining"
            className="text-[10px] font-semibold text-[#3C3C43] tabular-nums">
            Sisa PO: {remainingLabel()}
          </span>
        )}
      </div>

      <div className="grid grid-cols-[1fr_178px] gap-1.5">
        <input type="number" min="0" step="any"
          data-testid="receive-doc-qty-input"
          value={docQty ?? ""}
          disabled={disabled || !opt}
          onChange={(e) => onQtyChange(e.target.value)}
          placeholder={opt ? `Qty dalam ${docUom || taskUom}` : "Memuat…"}
          className="w-full rounded-lg border border-[#E5E5EA] bg-white px-2 py-1.5 text-sm disabled:bg-[#F2F2F7]" />
        <KNSelect
          data-testid="receive-doc-uom-select"
          className="w-full rounded-lg border border-[#E5E5EA] bg-white px-2 py-1.5 text-left text-sm"
          value={docUom || ""}
          disabled={disabled || !opt || list.length <= 1}
          placeholder="Satuan"
          options={list.map((o) => ({ value: o.value, label: o.label }))}
          onValueChange={(v) => onUomChange(v)} />
      </div>

      {/* hint faktor satuan terpilih */}
      {chosen?.hint && (
        <p data-testid="receive-uom-hint" className="mt-1 text-[10px] text-[#6B6B73]">
          {chosen.hint}
        </p>
      )}

      {/* pratinjau konversi dari server */}
      {uom?.previewing && !trail && (
        <p className="mt-1 inline-flex items-center gap-1 text-[10.5px] text-[#8E8E93]">
          <Info size={11} /> Menghitung konversi…
        </p>
      )}
      {trail && supplierMode && (
        <p data-testid="receive-uom-preview"
          className="mt-1 flex flex-wrap items-center gap-1 text-[10.5px] text-[#3C3C43]">
          <span className="font-semibold tabular-nums">{formatQty(trail.doc_qty)} {trail.doc_uom}</span>
          <ArrowRight size={10} className="text-[#8E8E93]" />
          <span data-testid="receive-uom-preview-task"
            className="font-bold tabular-nums text-[#0058CC]">
            {formatQty(trail.task_qty)} {trail.task_uom}
          </span>
          <span className="text-[#8E8E93]">
            (faktor {Number(trail.factor).toLocaleString("id-ID", { maximumFractionDigits: 6 })}
            {" · "}{RECEIVE_SOURCE_LABEL[trail.source] || trail.source})
          </span>
        </p>
      )}
      {trail && !supplierMode && (
        <p data-testid="receive-uom-preview" className="mt-1 text-[10.5px] text-[#6B6B73]">
          Qty dicatat apa adanya dalam satuan PO ({trail.task_uom}).
        </p>
      )}

      {/* peringatan melebihi sisa — pesan server menyebut kedua satuan */}
      {pv?.message && (
        <p data-testid="receive-uom-warning"
          className={`mt-1 flex items-start gap-1 text-[10.5px] font-semibold ${
            blocked ? "text-[#B4231F]" : "text-[#8C4A00]"}`}>
          <AlertTriangle size={11} className="mt-0.5 shrink-0" /> {pv.message}
        </p>
      )}
      {uom?.previewError && (
        <p data-testid="receive-uom-error"
          className="mt-1 flex items-start gap-1 text-[10.5px] font-semibold text-[#B4231F]">
          <AlertTriangle size={11} className="mt-0.5 shrink-0" /> {uom.previewError}
        </p>
      )}
      {uom?.error && !opt && (
        <p data-testid="receive-uom-options-error"
          className="mt-1 text-[10.5px] font-semibold text-[#B4231F]">{uom.error}</p>
      )}

      {/* konteks barang supplier (kode + satuan) agar cocok dgn surat jalan */}
      {opt?.supplier_item && (
        <p data-testid="receive-uom-supplier-item"
          className="mt-1.5 rounded-md border border-[#E5F0FF] bg-white px-2 py-1 text-[10px] text-[#0058CC]">
          Katalog supplier: <b>{opt.supplier_item.supplier_sku}</b>
          {opt.supplier_item.supplier_item_name ? ` — ${opt.supplier_item.supplier_item_name}` : ""}
          {opt.supplier_item.supplier_uom
            ? ` · 1 ${opt.supplier_item.supplier_uom} = ${formatQty(opt.supplier_item.conv_factor)} ${opt.base_uom}`
            : ""}
        </p>
      )}
      {opt && !opt.supplier_item && opt.mode !== "off" && (
        <p data-testid="receive-uom-no-supplier-item" className="mt-1.5 text-[10px] text-[#8E8E93]">
          Barang ini belum punya katalog supplier — daftarkan di <b>Pembelian → Master
          Pembelian → Barang Supplier</b> agar qty bisa diketik dalam satuan supplier.
        </p>
      )}
    </div>
  );
}
