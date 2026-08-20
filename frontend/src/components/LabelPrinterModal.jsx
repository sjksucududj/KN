import { useState } from "react";
import { Printer, Copy, Download, X, CheckCircle } from "lucide-react";
import axios, { API } from "../services/apiClient";
import KNSelect from "./KNSelect";

/**
 * LabelPrinterModal
 * 
 * Modal untuk generate ZPL/ESC-POS label command.
 * User bisa copy command atau download sebagai file .txt
 * 
 * Props:
 * - product: object dengan id, sku, name, price
 * - warehouse: object dengan id, name, code (optional)
 * - onClose: callback untuk close modal
 */
export default function LabelPrinterModal({ product, warehouse = null, onClose }) {
  const [format, setFormat] = useState("zpl");
  const [qty, setQty] = useState(1);
  const [loading, setLoading] = useState(false);
  const [labelData, setLabelData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    setLoading(true);
    setError("");
    setLabelData(null);
    setCopied(false);

    try {
      const payload = {
        product_id: product.id,
        warehouse_id: warehouse?.id || "",
        format: format,
        qty: parseInt(qty, 10),
        barcode_value: ""
      };

      const response = await axios.post(`${API}/labels/generate`, payload);
      setLabelData(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Gagal generate label");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!labelData?.content) return;
    
    navigator.clipboard.writeText(labelData.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {
      setError("Gagal copy ke clipboard");
    });
  };

  const handleDownload = () => {
    if (!labelData?.content) return;

    const blob = new Blob([labelData.content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `label_${product.sku}_${format}_${Date.now()}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div
      data-testid="label-printer-modal-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        data-testid="label-printer-modal-content"
        className="bg-white/90 backdrop-blur-2xl backdrop-saturate-150 border border-white/60 shadow-[0_8px_32px_rgba(0,0,0,0.12)] rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-[#E5E5EA]">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-full bg-[#007AFF]/10">
              <Printer className="text-[#007AFF]" size={20} />
            </div>
            <div>
              <h2 data-testid="modal-title" className="text-lg font-semibold text-[#000000]">
                Buat Label Barcode
              </h2>
              <p data-testid="modal-subtitle" className="text-sm text-[#3C3C43]">
                {product.sku} - {product.name}
              </p>
            </div>
          </div>
          <button
            data-testid="close-modal-button"
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-full hover:bg-[#F2F2F7] transition-colors"
            aria-label="Tutup"
          >
            <X size={18} className="text-[#3C3C43]" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-180px)]">
          {/* Form */}
          <div className="space-y-4 mb-6">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label data-testid="format-label" className="block text-sm font-medium text-[#3C3C43] mb-2">
                  Format Label
                </label>
                <KNSelect
                  data-testid="format-select"
                  value={format}
                  onValueChange={setFormat}
                  className="w-full bg-white/50 border border-gray-200 rounded-xl px-3 py-2 text-sm"
                  options={[
                    { value: "zpl",    label: "ZPL (Zebra Printers)" },
                    { value: "escpos", label: "ESC/POS (Thermal Printers)" },
                  ]}
                />
              </div>

              <div>
                <label data-testid="qty-label" className="block text-sm font-medium text-[#3C3C43] mb-2">
                  Jumlah Label
                </label>
                <input
                  data-testid="qty-input"
                  type="number"
                  min="1"
                  max="100"
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                  className="w-full bg-white/50 border border-gray-200 focus:bg-white focus:ring-2 focus:ring-[#007AFF]/20 focus:border-[#007AFF] rounded-xl px-3 py-2 text-sm transition-all"
                />
              </div>
            </div>

            {warehouse && (
              <div className="bg-[#F2F2F7] rounded-xl p-3">
                <p data-testid="warehouse-context" className="text-xs text-[#3C3C43]">
                  <span className="font-semibold">Lokasi Gudang:</span> {warehouse.name} ({warehouse.code})
                </p>
              </div>
            )}

            <button
              data-testid="generate-button"
              onClick={handleGenerate}
              disabled={loading}
              className="w-full bg-[#007AFF] hover:bg-[#0056B3] text-white rounded-full px-6 py-2.5 font-medium transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Generating..." : "Generate Label Command"}
            </button>
          </div>

          {/* Error */}
          {error && (
            <div data-testid="error-message" className="bg-[#FF3B30]/10 border border-[#FF3B30]/20 rounded-xl p-3 mb-4">
              <p className="text-sm text-[#FF3B30]">{error}</p>
            </div>
          )}

          {/* Result */}
          {labelData && (
            <div data-testid="label-result" className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-[#3C3C43]">
                  Label Command ({labelData.format.toUpperCase()})
                </p>
                <div className="flex gap-2">
                  <button
                    data-testid="copy-button"
                    onClick={handleCopy}
                    className="flex items-center gap-2 bg-white border border-[#E5E5EA] hover:border-[#007AFF] text-[#007AFF] rounded-full px-4 py-1.5 text-sm font-medium transition-all"
                  >
                    {copied ? (
                      <>
                        <CheckCircle size={14} />
                        <span>Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={14} />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                  <button
                    data-testid="download-button"
                    onClick={handleDownload}
                    className="flex items-center gap-2 bg-[#007AFF] hover:bg-[#0056B3] text-white rounded-full px-4 py-1.5 text-sm font-medium transition-all"
                  >
                    <Download size={14} />
                    <span>Download .txt</span>
                  </button>
                </div>
              </div>

              <div className="bg-[#000000] text-[#00FF00] rounded-xl p-4 overflow-x-auto">
                <pre data-testid="label-command-content" className="text-xs font-mono whitespace-pre-wrap">
                  {labelData.content}
                </pre>
              </div>

              {/* Meta info */}
              <div className="grid grid-cols-2 gap-3 text-xs text-[#3C3C43]">
                <div className="bg-[#F2F2F7] rounded-lg p-2">
                  <span className="font-semibold">Label Size:</span> {labelData.meta.label_size}
                </div>
                <div className="bg-[#F2F2F7] rounded-lg p-2">
                  <span className="font-semibold">Barcode Type:</span> {labelData.meta.barcode_type}
                </div>
                <div className="bg-[#F2F2F7] rounded-lg p-2">
                  <span className="font-semibold">SKU:</span> {labelData.meta.sku}
                </div>
                <div className="bg-[#F2F2F7] rounded-lg p-2">
                  <span className="font-semibold">Jumlah:</span> {labelData.meta.qty}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
