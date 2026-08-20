/**
 * SupplierItemImportModal (FASE E · E-01/E-02) — IMPOR MASSAL Barang Supplier.
 *
 * Alur aman 2 tahap: **Pratinjau** (tidak menulis apa pun, setiap baris invalid
 * diberi alasan) → **Commit**. Commit bersifat idempotent (upsert by supplier + kode),
 * jadi mengunggah berkas yang sama dua kali TIDAK menggandakan data.
 */
import { useRef, useState } from "react";
import { Download, FileSpreadsheet, Upload, X } from "lucide-react";
import KNSelect from "../../../components/KNSelect";
import {
  downloadImportTemplate, importSupplierItems, importSupplierItemsFile,
} from "./supplierItemsApi";
import { overlayDismiss } from "@/utils/overlayDismiss";

export default function SupplierItemImportModal({ suppliers, selectedEntity, onClose, onDone }) {
  const [supplierId, setSupplierId] = useState("");
  const [mode, setMode] = useState("file");        // file | paste
  const [csvText, setCsvText] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const fileRef = useRef(null);

  const entityParam = selectedEntity && selectedEntity !== "all" ? selectedEntity : "";

  async function run(dryRun) {
    if (!supplierId) { setErr("Pilih supplier tujuan impor terlebih dahulu."); return; }
    if (mode === "file" && !file) { setErr("Pilih berkas CSV atau XLSX."); return; }
    if (mode === "paste" && !csvText.trim()) { setErr("Tempel isi CSV terlebih dahulu."); return; }
    setBusy(true); setErr("");
    try {
      const res = mode === "file"
        ? await importSupplierItemsFile(file, { supplier_id: supplierId, entity_id: entityParam, dry_run: dryRun })
        : await importSupplierItems({ supplier_id: supplierId, entity_id: entityParam, csv_text: csvText, dry_run: dryRun });
      setPreview(res);
      if (!dryRun) onDone?.(res);
    } catch (e) {
      setErr(e.response?.data?.detail || "Impor gagal diproses.");
    } finally { setBusy(false); }
  }

  const canCommit = Boolean(preview) && (preview?.valid || 0) > 0;

  return (
    <div className="modal-overlay" data-testid="supplier-item-import-modal" {...overlayDismiss(onClose)}>
      <div className="modal-card wide" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <p className="modal-title">Impor Massal Barang Supplier</p>
            <p className="modal-subtitle">
              Unggah CSV/XLSX daftar barang versi supplier. Pratinjau dulu — commit bersifat
              idempotent (kunci: supplier + kode barang).
            </p>
          </div>
          <button className="icon-button" onClick={onClose} data-testid="supplier-item-import-close">
            <X size={16} />
          </button>
        </div>

        {err && (
          <div className="notice-bar danger" data-testid="supplier-item-import-error">
            <span>{err}</span><button onClick={() => setErr("")}>×</button>
          </div>
        )}

        <div className="grid gap-3 mt-2">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Supplier Tujuan *</label>
              <KNSelect data-testid="import-supplier" className="form-input" value={supplierId}
                onValueChange={(v) => { setSupplierId(v); setPreview(null); }}
                placeholder="— Pilih supplier —"
                options={suppliers.map((s) => ({ value: s.id, label: s.name }))} />
            </div>
            <div className="grid gap-1.5">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Cara Impor</label>
              <div className="tab-bar">
                <button data-testid="import-mode-file"
                  className={`tab-button ${mode === "file" ? "is-active" : ""}`}
                  onClick={() => { setMode("file"); setPreview(null); }}>Unggah Berkas</button>
                <button data-testid="import-mode-paste"
                  className={`tab-button ${mode === "paste" ? "is-active" : ""}`}
                  onClick={() => { setMode("paste"); setPreview(null); }}>Tempel CSV</button>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button data-testid="import-download-template" className="btn-secondary btn-xs"
              onClick={() => downloadImportTemplate().catch(() => setErr("Gagal mengunduh template."))}>
              <Download size={13} /> Unduh Template CSV
            </button>
            <span className="text-[10.5px] text-[#6B6B73]">
              Kolom: supplier_sku, supplier_item_name, sku (SKU KN), supplier_uom, conv_factor,
              last_price, moq, lead_time_days, expected_grade, barcode, notes
            </span>
          </div>

          {mode === "file" ? (
            <div className="grid gap-1.5">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Berkas CSV / XLSX *</label>
              <input ref={fileRef} type="file" accept=".csv,.xlsx" data-testid="import-file-input"
                className="form-input"
                onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); }} />
              {file && (
                <p className="text-[10.5px] text-[#6B6B73] flex items-center gap-1">
                  <FileSpreadsheet size={12} /> {file.name}
                </p>
              )}
            </div>
          ) : (
            <div className="grid gap-1.5">
              <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Isi CSV *</label>
              <textarea data-testid="import-csv-text" className="form-input font-mono text-[11px]" rows="6"
                value={csvText} onChange={(e) => { setCsvText(e.target.value); setPreview(null); }}
                placeholder={"supplier_sku,supplier_item_name,sku,supplier_uom,conv_factor,last_price\nTX-COT-30S,Cotton Combed 30s,BNG-KTN-001,cone,1.89,94500"} />
            </div>
          )}

          {preview && (
            <div className="grid gap-2" data-testid="import-preview">
              <div className="grid gap-2 sm:grid-cols-4">
                <div className="metric-tile">
                  <span className="text-[10px] uppercase text-[#6B6B73]">Total Baris</span>
                  <b data-testid="import-total" className="tabular-nums">{preview.total ?? 0}</b>
                </div>
                <div className="metric-tile">
                  <span className="text-[10px] uppercase text-[#6B6B73]">Valid</span>
                  <b data-testid="import-valid" className="tabular-nums text-[#1B7F4B]">{preview.valid ?? 0}</b>
                </div>
                <div className="metric-tile">
                  <span className="text-[10px] uppercase text-[#6B6B73]">Ditolak</span>
                  <b data-testid="import-invalid" className="tabular-nums text-[#C0392B]">{preview.invalid ?? 0}</b>
                </div>
                <div className="metric-tile">
                  <span className="text-[10px] uppercase text-[#6B6B73]">
                    {preview.dry_run ? "Rencana" : "Hasil"}
                  </span>
                  <b data-testid="import-effect" className="tabular-nums">
                    {preview.dry_run
                      ? `+${preview.will_create ?? 0} baru · ${preview.will_update ?? 0} update`
                      : `+${preview.created ?? 0} baru · ${preview.updated ?? 0} update`}
                  </b>
                </div>
              </div>

              {(preview.errors || []).length > 0 && (
                <div className="rounded-md border border-[#FFE2B8] bg-[#FFF8EE] overflow-hidden">
                  <div className="px-3 py-1.5 text-[10px] font-bold uppercase text-[#8C4A00]">
                    Baris ditolak — perbaiki lalu unggah ulang
                  </div>
                  <div className="max-h-[180px] overflow-y-auto">
                    {preview.errors.map((e, i) => (
                      <div key={i} data-testid={`import-error-${i}`}
                        className="grid grid-cols-[70px_130px_1fr] gap-2 border-t border-[#FFE9CC] px-3 py-1.5 text-[11px]">
                        <span className="text-[#8C4A00]">Baris {e.row}</span>
                        <span className="font-semibold truncate">{e.supplier_sku || "—"}</span>
                        <span className="text-[#6B6B73]">{e.error}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(preview.preview || []).length > 0 && (
                <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
                  <div className="grid grid-cols-[80px_1.2fr_1.2fr_110px_110px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
                    <span>Aksi</span><span>Kode Supplier</span><span>Produk KN</span>
                    <span className="text-right">Konversi</span><span className="text-right">Harga</span>
                  </div>
                  <div className="max-h-[200px] overflow-y-auto">
                    {preview.preview.map((row, i) => (
                      <div key={i} data-testid={`import-row-${i}`}
                        className="grid grid-cols-[80px_1.2fr_1.2fr_110px_110px] items-center border-t border-[#F4F5F7] px-3 py-1.5 text-[11px]">
                        <span className={`status-pill ${row.action === "create" ? "pill-success" : "pill-info"}`}>
                          {row.action === "create" ? "Baru" : "Update"}
                        </span>
                        <span className="truncate font-semibold">{row.supplier_sku}</span>
                        <span className="truncate">{row.sku} · {row.product_name}</span>
                        <span className="text-right tabular-nums">
                          1 {row.supplier_uom} = {row.conv_factor} {row.base_unit}
                        </span>
                        <span className="text-right tabular-nums">{row.last_price}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose}>Tutup</button>
          <button data-testid="import-preview-button" className="btn-secondary"
            onClick={() => run(true)} disabled={busy}>
            {busy ? "Memproses…" : "Pratinjau"}
          </button>
          <button data-testid="import-commit-button" className="btn-primary"
            onClick={() => run(false)} disabled={busy || !canCommit}>
            <Upload size={14} /> {busy ? "Mengimpor…" : "Impor Sekarang"}
          </button>
        </div>
      </div>
    </div>
  );
}
