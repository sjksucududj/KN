import { useState } from "react";
import { Barcode } from "lucide-react";
import { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";

export default function DocumentsView({ templates, loading = false, lastDocument, lastLabel, onGenerateLabel, products }) {
  const [selectedProductId, setSelectedProductId] = useState("");

  const selectedProduct = products.find(p => p.id === selectedProductId);
  const generateCode = selectedProduct ? `ROLL-${selectedProduct.sku}` : "ROLL-BTK-001";

  return (
    <div data-testid="documents-view">
      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-3 min-w-0">
            <span className="kicker">Pusat Cetak</span>
            <h2>Template dokumen & barcode label</h2>
          </div>
        </div>
        <p className="px-4 py-2 text-[12px] text-[#6B6B73]">Header, footer, kolom, area tanda tangan, dan ukuran label dapat dikonfigurasi.</p>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <section className="section-card">
          <div className="section-head"><h2>Template aktif</h2></div>
          <div className="section-body grid gap-2">
            {loading && (
              <div className="animate-pulse py-2 text-[12px] text-[#6B6B73]">Memuat template…</div>
            )}
            {!loading && (templates || []).length === 0 && (
              <div data-testid="templates-empty" className="py-2 text-[12px] text-[#6B6B73]">Belum ada template aktif.</div>
            )}
            {!loading && (templates || []).map((template) => (
              <div data-testid={`template-card-${template.id}`} key={template.id} className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3">
                <p data-testid={`template-name-${template.id}`} className="text-[13px] font-semibold">{template.name}</p>
                <p data-testid={`template-type-${template.id}`} className="text-[11.5px] text-[#3C3C43]">{template.document_type} • {template.columns.join(", ")}</p>
              </div>
            ))}
          </div>
        </section>
        <section className="section-card">
          <div className="section-head"><h2>Buat label cepat</h2></div>
          <div className="section-body grid gap-2">
            <div>
              <label className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73] block mb-1.5">Pilih Produk</label>
              <KNSelect
                data-testid="label-product-selector"
                className="field w-full"
                value={selectedProductId || ""}
                onValueChange={setSelectedProductId}
                placeholder="-- Pilih produk untuk label --"
                options={[
                  { value: "", label: "-- Pilih produk untuk label --" },
                  ...products.map((p) => ({ value: p.id, label: `${p.sku} - ${p.name}` })),
                ]}
              />
            </div>
            <button
              data-testid="generate-demo-barcode-button"
              className="primary-button"
              disabled={!selectedProductId}
              onClick={() => onGenerateLabel("roll", generateCode)}
            >
              <Barcode size={14} /> Buat Label Roll
            </button>
            {lastLabel && (
              <div data-testid="last-barcode-label" className="mt-4 inline-block rounded-md border border-[#EFF0F2] bg-white p-3">
                <p data-testid="last-barcode-code" className="mb-2 text-[10.5px] font-bold tracking-wider">{lastLabel.code}</p>
                <div className="grid w-[130px] grid-cols-[repeat(13,10px)] gap-0">
                  {lastLabel.qr_matrix.flatMap((row, i) => row.map((cell, j) => <span data-testid={`qr-cell-${i}-${j}`} key={`${i}-${j}`} className={`qr-cell ${cell ? "on" : "off"} h-2.5 w-2.5`} />))}
                </div>
                <p className="mt-2 text-[11px] font-semibold">Size: {lastLabel.label_size}</p>
              </div>
            )}
            {lastDocument && (
              <div data-testid="last-generated-document" className="mt-4 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3">
                <p className="text-[10.5px] font-bold uppercase tracking-wide text-[#6B6B73]">Dokumen terakhir</p>
                <p data-testid="last-generated-document-number" className="text-[13px] font-semibold">{lastDocument.number}</p>
                <a data-testid="open-last-document-link" className="mt-2 inline-flex text-[12px] font-semibold text-[#0058CC] underline" href={`${API}/documents/${lastDocument.id}/print`} target="_blank" rel="noreferrer">Buka tampilan cetak</a>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
