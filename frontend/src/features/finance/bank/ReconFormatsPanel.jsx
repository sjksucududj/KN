/**
 * FASE G-8 — ReconFormatsPanel: kelola TEMPLATE pembacaan rekening koran.
 *
 * Tujuannya menghapus ketergantungan pada developer: kalau bank mengubah susunan
 * kolom (atau Anda memakai bank lain), template baru bisa dibuat sendiri di sini —
 * pemetaan kolom, format tanggal, gaya desimal, dan penanda arah dana.
 */
import { useState } from "react";
import { FileCog, Plus, Save, Trash2, X, RefreshCw } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import { KNSelect } from "../../../components/KNSelect";
import { overlayDismiss } from "../../../utils/overlayDismiss";
import ErrorNotice from "../../../components/ErrorNotice";
import { apiErrorText } from "../../../utils/apiError";

const KIND_OPTS = [
  { value: "csv", label: "CSV / teks berpemisah" },
  { value: "mt940", label: "MT940 (SWIFT)" },
  { value: "ofx", label: "OFX / QFX" },
];
const DEC_OPTS = [
  { value: "auto", label: "Kenali otomatis" },
  { value: "id", label: "Indonesia — 1.234.567,89" },
  { value: "en", label: "Inggris — 1,234,567.89" },
];
const DATE_OPTS = [
  { value: "auto", label: "Kenali otomatis" },
  { value: "dd/mm/yyyy", label: "31/07/2026" },
  { value: "dd-mm-yyyy", label: "31-07-2026" },
  { value: "yyyy-mm-dd", label: "2026-07-31" },
  { value: "yyyymmdd", label: "20260731" },
  { value: "yymmdd", label: "260731" },
];
const COLS = [
  ["date", "Kolom tanggal"],
  ["description", "Kolom keterangan"],
  ["ref", "Kolom nomor referensi"],
  ["amount", "Kolom nominal (satu kolom)"],
  ["direction", "Kolom penanda arah (DB/CR)"],
  ["amount_in", "Kolom nominal masuk (kredit)"],
  ["amount_out", "Kolom nominal keluar (debet)"],
  ["balance", "Kolom saldo"],
  ["external_id", "Kolom id unik bank"],
];

const EMPTY = {
  name: "", bank_code: "custom", file_kind: "csv", delimiter: ",", has_header: true,
  skip_rows: 0, decimal_style: "auto", date_format: "auto",
  columns: {}, in_markers: ["cr", "kredit"], out_markers: ["db", "debet"], note: "",
};

export default function ReconFormatsPanel({ formats, onReload, onError, onNotify }) {
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState("");
  // INV-UI-03 — modal WAJIB menampilkan penolakannya sendiri: bilah error layar
  // induk berada di belakang lapisan modal ini, jadi tak terlihat pengguna.
  const [mErr, setMErr] = useState("");

  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const setCol = (k, v) => setDraft((d) => ({ ...d, columns: { ...(d.columns || {}), [k]: v } }));

  async function save() {
    setBusy("save");
    try {
      const body = {
        ...draft,
        skip_rows: Number(draft.skip_rows) || 0,
        in_markers: typeof draft.in_markers === "string"
          ? draft.in_markers.split(",").map((s) => s.trim()).filter(Boolean) : draft.in_markers,
        out_markers: typeof draft.out_markers === "string"
          ? draft.out_markers.split(",").map((s) => s.trim()).filter(Boolean) : draft.out_markers,
      };
      const r = await axios.post(`${API}/bank-reconciliation/formats`, body);
      // Menyimpan template BAWAAN menghasilkan SALINAN milik entitas (preset dipakai
      // bersama semua PT), jadi nama yang dikonfirmasi diambil dari jawaban server.
      onNotify(`Template “${r.data?.name || draft.name}” tersimpan.`);
      setDraft(null);
      await onReload();
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); } finally { setBusy(""); }
  }

  async function remove(f) {
    setBusy(f.id);
    try {
      await axios.delete(`${API}/bank-reconciliation/formats/${f.id}`);
      onNotify(`Template “${f.name}” dinonaktifkan.`);
      await onReload();
    } catch (e) { setMErr(apiErrorText(e)); onError?.(e); } finally { setBusy(""); }
  }

  return (
    <div data-testid="recon-formats-panel">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[12px] text-[#6B6B73]">
          <FileCog size={13} className="inline mr-1 text-[#0058CC]" />
          {(formats || []).length} template tersedia. Template bawaan bisa dijadikan contoh:
          buka, ubah pemetaan kolomnya, lalu simpan sebagai template Anda sendiri.
        </p>
        <button data-testid="recon-format-new" className="primary-button"
          onClick={() => setDraft({ ...EMPTY })}>
          <Plus size={14} /> Template baru
        </button>
      </div>

      <div className="rounded-lg border border-[#E5E5EA] overflow-hidden" data-testid="recon-formats-table">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
              <th className="px-3 py-2">Nama template</th>
              <th className="px-3 py-2">Bank</th>
              <th className="px-3 py-2">Jenis berkas</th>
              <th className="px-3 py-2">Desimal</th>
              <th className="px-3 py-2">Tanggal</th>
              <th className="px-3 py-2 text-right">Tindakan</th>
            </tr>
          </thead>
          <tbody>
            {(formats || []).length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-[#8E8E93]">
                  Belum ada template.
                </td>
              </tr>
            ) : formats.map((f) => (
              <tr key={f.id} data-testid={`recon-format-${f.id}`}
                className="border-b border-[#F5F5F7] last:border-0">
                <td className="px-3 py-2">
                  {f.name}
                  {f.builtin && (
                    <span className="ml-1 rounded bg-[#F0F0F2] px-1 text-[10px] text-[#6B6B73]">
                      bawaan
                    </span>
                  )}
                  {f.note && <p className="text-[10px] text-[#8E8E93]">{f.note}</p>}
                </td>
                <td className="px-3 py-2 uppercase">{f.bank_code}</td>
                <td className="px-3 py-2 uppercase">{f.file_kind}</td>
                <td className="px-3 py-2">{f.decimal_style}</td>
                <td className="px-3 py-2">{f.date_format}</td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <div className="flex justify-end gap-2">
                    <button data-testid={`recon-format-edit-${f.id}`} className="link-button"
                      onClick={() => setDraft({ ...f })}>Buka</button>
                    {!f.builtin && (
                      <button data-testid={`recon-format-delete-${f.id}`} className="link-button"
                        style={{ color: "#B4231F" }} disabled={busy === f.id}
                        onClick={() => remove(f)}>
                        <Trash2 size={12} /> Nonaktifkan
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {draft && (
        <div className="modal-overlay" data-testid="recon-format-modal"
          {...overlayDismiss(() => setDraft(null))}>
          <div className="modal-card max-w-[720px]">
            <div className="flex items-center justify-between mb-2">
              <h3 className="modal-title flex items-center gap-1.5">
                <FileCog size={15} />
                {draft.id
                  ? (draft.builtin
                    ? "Template bawaan — simpan sebagai salinan Anda"
                    : "Ubah template bank")
                  : "Template bank baru"}
              </h3>
              <button className="icon-button" data-testid="recon-format-close"
                onClick={() => setDraft(null)}><X size={15} /></button>
            </div>
            {mErr && (
              <ErrorNotice message={mErr} onDismiss={() => setMErr("")}
                testId="recon-format-error" />
            )}
            <p className="modal-subtitle">
              Kolom bisa ditulis dengan NAMA header (mis. “Keterangan”) atau NOMOR kolom
              dimulai dari 0 bila berkas tidak punya header.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
              <div className="md:col-span-2">
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Nama template
                </label>
                <input data-testid="recon-format-name" className="input-field w-full"
                  value={draft.name} onChange={(e) => set("name", e.target.value)}
                  placeholder="Contoh: BCA Giro — ekspor Juli 2026" />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Kode bank
                </label>
                <input data-testid="recon-format-bank" className="input-field w-full"
                  value={draft.bank_code} onChange={(e) => set("bank_code", e.target.value)} />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Jenis berkas
                </label>
                <KNSelect data-testid="recon-format-kind" value={draft.file_kind}
                  onValueChange={(v) => set("file_kind", v)} options={KIND_OPTS} />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Gaya desimal
                </label>
                <KNSelect data-testid="recon-format-decimal" value={draft.decimal_style}
                  onValueChange={(v) => set("decimal_style", v)} options={DEC_OPTS} />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Format tanggal
                </label>
                <KNSelect data-testid="recon-format-date" value={draft.date_format}
                  onValueChange={(v) => set("date_format", v)} options={DATE_OPTS} />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Pemisah kolom
                </label>
                <input data-testid="recon-format-delimiter" className="input-field w-full"
                  value={draft.delimiter} onChange={(e) => set("delimiter", e.target.value)}
                  placeholder="Contoh: , atau ;" />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Baris dilewati di awal
                </label>
                <input data-testid="recon-format-skip" type="number" min={0} max={20}
                  className="input-field w-full" value={draft.skip_rows}
                  onChange={(e) => set("skip_rows", e.target.value)} />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-[12px]">
                  <input data-testid="recon-format-header" type="checkbox"
                    checked={!!draft.has_header}
                    onChange={(e) => set("has_header", e.target.checked)} />
                  Baris pertama adalah header
                </label>
              </div>
            </div>

            <p className="mt-3 text-[11px] font-bold uppercase text-[#8E8E93]">Pemetaan kolom</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-1">
              {COLS.map(([key, label]) => (
                <div key={key}>
                  <label className="block text-[11px] text-[#6B6B73] mb-1">{label}</label>
                  <input data-testid={`recon-format-col-${key}`} className="input-field w-full"
                    value={(draft.columns || {})[key] ?? ""}
                    onChange={(e) => setCol(key, e.target.value)} />
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Penanda uang masuk (dipisah koma)
                </label>
                <input data-testid="recon-format-in" className="input-field w-full"
                  value={Array.isArray(draft.in_markers) ? draft.in_markers.join(", ") : draft.in_markers}
                  onChange={(e) => set("in_markers", e.target.value)} />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#6B6B73] mb-1">
                  Penanda uang keluar (dipisah koma)
                </label>
                <input data-testid="recon-format-out" className="input-field w-full"
                  value={Array.isArray(draft.out_markers) ? draft.out_markers.join(", ") : draft.out_markers}
                  onChange={(e) => set("out_markers", e.target.value)} />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-4">
              <button className="secondary-button" onClick={() => setDraft(null)}>Batal</button>
              <button data-testid="recon-format-save" className="primary-button"
                disabled={!draft.name?.trim() || busy === "save"} onClick={save}>
                {busy === "save" ? <RefreshCw size={14} className="spin" /> : <Save size={14} />}
                {draft.builtin ? "Simpan sebagai salinan" : "Simpan template"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
