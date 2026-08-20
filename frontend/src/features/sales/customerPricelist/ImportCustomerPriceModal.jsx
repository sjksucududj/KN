/**
 * ImportCustomerPriceModal (F1b) — impor massal harga langganan dari CSV.
 *
 * CSV dikirim MENTAH ke server (`csv_text`) supaya pembacaan angka gaya Indonesia
 * ("126.540" = seratus dua puluh enam ribu lima ratus empat puluh, "126.540,50" =
 * dengan sen) hanya punya SATU implementasi — layar lain dulu memotong sendiri dengan
 * `split(",")` sehingga angka ber-titik terbaca 100× lebih besar.
 */
import { useRef, useState } from "react";
import { CheckCircle2, FileUp, Upload, X } from "lucide-react";
import axios, { API } from "../../../services/apiClient";

const TEMPLATE = "sku;nama_produk;harga_pelanggan;berlaku_dari;berlaku_sampai;catatan";

export default function ImportCustomerPriceModal({ customer, entityId, onClose, onDone }) {
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const fileRef = useRef(null);

  const pickFile = async (file) => {
    if (!file) return;
    setFileName(file.name);
    setErr("");
    try {
      setText(await file.text());
    } catch {
      setErr("Gagal membaca berkas CSV.");
    }
  };

  const submit = async () => {
    if (!text.trim()) { setErr("Tempelkan isi CSV atau pilih berkas lebih dulu."); return; }
    setBusy(true); setErr(""); setResult(null);
    try {
      const res = await axios.post(`${API}/customer-prices/import`, {
        customer_id: customer.id, entity_id: entityId, csv_text: text,
      });
      setResult(res.data);
      onDone(res.data);
    } catch (e) {
      setErr(e.response?.data?.detail || "Impor gagal.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4"
      data-testid="cpl-import-modal">
      <div className="flex max-h-[88vh] w-full max-w-xl flex-col rounded-xl bg-white shadow-xl">
        <div className="flex items-center gap-2 border-b border-[#EFF0F2] px-4 py-3">
          <Upload size={16} className="text-[#0058CC]" />
          <h3 className="truncate text-[14px] font-bold">Impor Harga · {customer.name}</h3>
          <button data-testid="cpl-import-close" className="icon-button ml-auto" onClick={onClose}
            aria-label="Tutup"><X size={15} /></button>
        </div>

        <div className="space-y-3 overflow-auto p-4 text-[12px]">
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-3 py-2">
            <p className="font-semibold text-[#1C1C1E]">
              Format kolom (pemisah <b>;</b> atau <b>,</b>)
            </p>
            <code className="mt-1 block break-all text-[11px] text-[#0058CC]">{TEMPLATE}</code>
            <p className="mt-1 text-[11px] text-[#6B6B73]">
              Angka boleh gaya Indonesia (<b>126.540</b>) maupun desimal titik
              (<b>126540.00</b>) dan koma (<b>126.540,50</b>) — semuanya dibaca benar.
              Baris tanpa harga dilewati (harga lama tetap). Harga di bawah batas bawah
              masuk antrean persetujuan, bukan langsung berlaku.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden"
              data-testid="cpl-import-file"
              onChange={(e) => { pickFile(e.target.files?.[0]); e.target.value = ""; }} />
            <button className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-[12px]"
              onClick={() => fileRef.current?.click()} data-testid="cpl-import-pick">
              <FileUp size={13} /> Pilih berkas CSV
            </button>
            {fileName && <span className="text-[11px] text-[#6B6B73]">{fileName}</span>}
          </div>

          <div>
            <label className="mb-1 block text-[11px] font-semibold text-[#6B6B73]">
              Atau tempelkan isi CSV
            </label>
            <textarea data-testid="cpl-import-text" value={text}
              onChange={(e) => setText(e.target.value)}
              className="field min-h-[120px] w-full font-mono text-[11.5px]"
              placeholder={`${TEMPLATE}\nBTK-001;Batik Mega Mendung;126.540;;;kontrak 2026`} />
          </div>

          {err && (
            <div data-testid="cpl-import-error"
              className="rounded-md border border-[#F5C6C6] bg-[#FDEDE7] px-3 py-2 text-[11.5px] text-[#C0392B]">
              {err}
            </div>
          )}

          {result && (
            <div data-testid="cpl-import-result"
              className="rounded-md border border-[#BDE5CC] bg-[#E6F6EC] px-3 py-2 text-[11.5px] text-[#1B6E3C]">
              <p className="flex items-center gap-1.5 font-bold">
                <CheckCircle2 size={13} />
                {result.applied} harga langsung berlaku
                {result.pending > 0 && ` · ${result.pending} menunggu persetujuan`}
                {result.skipped > 0 && ` · ${result.skipped} dilewati`}
                {" "}dari {result.total_rows} baris
              </p>
              {(result.errors || []).length > 0 && (
                <ul className="mt-1 max-h-[140px] list-disc space-y-0.5 overflow-auto pl-5 text-[#8C4A00]">
                  {result.errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="btn-secondary px-4 py-1.5 text-[12px]" onClick={onClose}>
            {result ? "Tutup" : "Batal"}
          </button>
          <button data-testid="cpl-import-submit" onClick={submit} disabled={busy}
            className="btn-primary inline-flex items-center gap-1 px-4 py-1.5 text-[12px] disabled:opacity-50">
            <Upload size={14} /> {busy ? "Mengimpor…" : "Impor Sekarang"}
          </button>
        </div>
      </div>
    </div>
  );
}
