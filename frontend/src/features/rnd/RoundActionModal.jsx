/**
 * RoundActionModal (FASE F · PS-18) — dua peran:
 *  - mode "submit": setor hasil round (catatan + hasil ukur + biaya). Lampiran WAJIB
 *    sudah diunggah lebih dulu — server menolak bila belum ada.
 *  - mode "assess": nilai hasil (acc | revisi | tolak) + skor (wajib saat ACC).
 */
import { useState } from "react";
import { Save, X } from "lucide-react";
import KNSelect from "../../components/KNSelect";
import { overlayDismiss } from "@/utils/overlayDismiss";

const RESULT_OPTS = [
  { value: "acc", label: "ACC — diterima (wajib skor)" },
  { value: "revisi", label: "Revisi — minta perbaikan (round berikutnya)" },
  { value: "tolak", label: "Tolak — supplier tidak dilanjutkan" },
];

export default function RoundActionModal({ mode, round, onClose, onConfirm, busy }) {
  const [note, setNote] = useState("");
  const [cost, setCost] = useState("");
  const [result, setResult] = useState("acc");
  const [score, setScore] = useState("");
  const [m, setM] = useState({ delta_e: "", gsm_actual: "", shrinkage_pct: "",
    colorfastness_wash: "", colorfastness_rub: "" });
  const setMeas = (k, v) => setM((p) => ({ ...p, [k]: v }));
  const isSubmit = mode === "submit";
  const nAttach = (round?.attachments || []).length;

  const confirm = () => {
    if (isSubmit) {
      onConfirm({
        note, cost: cost || 0,
        measurements: Object.fromEntries(
          Object.entries(m).map(([k, v]) => [k, v === "" ? null : v])),
      });
    } else {
      onConfirm({ result, score: score === "" ? null : score, note });
    }
  };

  return (
    <div data-testid="round-action-modal"
      className="fixed inset-0 z-[176] flex items-center justify-center bg-black/50 p-4"
      {...overlayDismiss(onClose)}>
      <div className="flex max-h-[92vh] w-full max-w-[560px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#EFF0F2] px-4 py-3">
          <h2 className="text-[15px] font-bold">
            {isSubmit ? `Setor hasil rnd ${round?.round_no}` : `Nilai hasil rnd ${round?.round_no}`}
            <span className="ml-2 text-[11.5px] font-normal text-[#6B6B73]">
              {round?.supplier_name}
            </span>
          </h2>
          <button className="icon-button" onClick={onClose} data-testid="round-modal-close">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-2.5 overflow-y-auto p-4">
          {isSubmit && (
            <div className={`rounded-lg px-3 py-2 text-[11.5px] ${nAttach
              ? "bg-[#EAF7EF] text-[#1A7A3A]" : "bg-[#FFF6E5] text-[#8C4A00]"}`}
              data-testid="round-attach-hint">
              {nAttach
                ? `${nAttach} bukti sudah terunggah — hasil boleh disetor.`
                : "Belum ada bukti terunggah. Unggah minimal 1 berkas (foto hasil / artwork / "
                  + "hasil ukur) di baris round sebelum menyetor — server akan menolaknya."}
            </div>
          )}

          {isSubmit ? (
            <>
              <Field label="Catatan / penjelasan hasil (WAJIB)">
                <textarea className="field" rows={3} data-testid="round-note-input" value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="mis. Warna sedikit lebih tua dari target, handfeel bagus" />
              </Field>
              <div className="grid gap-2.5 md:grid-cols-3">
                <Field label="ΔE (selisih warna)">
                  <input className="field" data-testid="round-deltae-input" value={m.delta_e}
                    onChange={(e) => setMeas("delta_e", e.target.value)} placeholder="1.2" />
                </Field>
                <Field label="GSM aktual">
                  <input className="field" data-testid="round-gsm-input" value={m.gsm_actual}
                    onChange={(e) => setMeas("gsm_actual", e.target.value)} placeholder="135" />
                </Field>
                <Field label="Susut (%)">
                  <input className="field" data-testid="round-shrink-input" value={m.shrinkage_pct}
                    onChange={(e) => setMeas("shrinkage_pct", e.target.value)} placeholder="2" />
                </Field>
                <Field label="Tahan cuci (1–5)">
                  <input className="field" data-testid="round-wash-input"
                    value={m.colorfastness_wash}
                    onChange={(e) => setMeas("colorfastness_wash", e.target.value)} placeholder="4" />
                </Field>
                <Field label="Tahan gosok (1–5)">
                  <input className="field" data-testid="round-rub-input" value={m.colorfastness_rub}
                    onChange={(e) => setMeas("colorfastness_rub", e.target.value)} placeholder="4" />
                </Field>
                <Field label="Biaya sample (Rp)">
                  <input className="field" data-testid="round-cost-input" value={cost}
                    onChange={(e) => setCost(e.target.value)} placeholder="150000" />
                </Field>
              </div>
            </>
          ) : (
            <>
              <Field label="Hasil penilaian *">
                <KNSelect data-testid="round-result-select" className="field" value={result}
                  options={RESULT_OPTS} onValueChange={setResult} />
              </Field>
              <Field label={`Skor 0–100${result === "acc" ? " (WAJIB saat ACC)" : ""}`}>
                <input className="field" data-testid="round-score-input" value={score}
                  onChange={(e) => setScore(e.target.value)} placeholder="92" />
              </Field>
              <Field label="Catatan penilai">
                <textarea className="field" rows={2} data-testid="round-assess-note" value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="mis. Warna presisi, siap dilanjutkan ke kontrak" />
              </Field>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[#EFF0F2] px-4 py-3">
          <button className="secondary-button" onClick={onClose}>Batal</button>
          <button className="primary-button" onClick={confirm} disabled={busy}
            data-testid="round-modal-confirm">
            <Save size={13} /> {busy ? "Menyimpan…" : isSubmit ? "Setor hasil" : "Simpan penilaian"}
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
