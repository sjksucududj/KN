import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { X, Ruler, CheckCircle2, RefreshCw } from "lucide-react";
import { formatQty } from "../../utils/formatters";
import DecimalInput from "../../components/DecimalInput";
import RollGradePanel from "./RollGradePanel";

/**
 * RollInspectionModal (Fase 6.2 — P1) — Inspeksi 4-Point per roll.
 * Catat poin defect (severity 1..4) + GSM/lebar aktual → set Grade roll (A/B/C).
 * Skor = Σ(point_value × count); grade dari ambang configurable (qc.grade_thresholds).
 */
const POINT_LEVELS = [
  { pv: 1, label: "1 poin (kecil <3\")" },
  { pv: 2, label: "2 poin (3–6\")" },
  { pv: 3, label: "3 poin (6–9\")" },
  { pv: 4, label: "4 poin (>9\")" },
];

export default function RollInspectionModal({ taskId, taskLabel, entityId, currentUser, onClose, onDone }) {
  const [rolls, setRolls] = useState([]);
  // Fase A · D-01 — ambang 5 tingkat (A|A1|A2|B|BS); a1/a2 di-interpolasi backend
  // bila konfigurasi lama hanya berisi a_max & b_max.
  const [thresholds, setThresholds] = useState({ a_max: 20, a1_max: 26.67, a2_max: 33.33, b_max: 40 });
  const [gradePanelRoll, setGradePanelRoll] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openRoll, setOpenRoll] = useState(null);
  const [form, setForm] = useState({});       // pv -> count
  const [gsm, setGsm] = useState("");
  const [width, setWidth] = useState("");
  const [note, setNote] = useState("");
  // FASE C (D-10) — inspeksi = titik input lot kedua (lot supplier & dye lot/shade)
  const [lotDraft, setLotDraft] = useState({ supplier_lot: "", dye_lot: "", shade_ref: "" });
  const [lotSettings, setLotSettings] = useState(null);
  const [lotWarnings, setLotWarnings] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { load(); }, [taskId]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const params = (entityId && entityId !== "all") ? { entity_id: entityId } : {};
      const [r, t, ls] = await Promise.all([
        axios.get(`${API}/inbound/qc/tasks/${taskId}/rolls`),
        axios.get(`${API}/qc/grade-thresholds`, { params }).catch(() => ({ data: { a_max: 20, b_max: 40 } })),
        axios.get(`${API}/lots/settings`).catch(() => ({ data: { enforcement_mode: "warn",
          require_supplier_lot: true, require_dye_lot: true } })),
      ]);
      setRolls(Array.isArray(r.data) ? r.data : []);
      setThresholds(t.data || { a_max: 20, b_max: 40 });
      setLotSettings(ls.data || null);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat roll.");
    } finally { setLoading(false); }
  }

  function openForm(roll) {
    setOpenRoll(roll.id);
    const insp = roll.inspection || {};
    const f = {};
    (insp.defects || []).forEach((d) => { f[d.point_value] = d.count; });
    setForm(f);
    setGsm(insp.gsm_actual ?? "");
    setWidth(insp.width_actual ?? "");
    setNote(insp.note || "");
    setLotWarnings([]);
    setLotDraft({
      supplier_lot: roll.supplier_lot || "",
      dye_lot: roll.dye_lot || "",
      shade_ref: roll.shade_ref || "",
    });
  }

  const points = useMemo(
    () => POINT_LEVELS.reduce((s, lv) => s + lv.pv * (Number(form[lv.pv]) || 0), 0), [form]);
  // Fase A · D-01 — prediksi grade 5 tingkat sesuai ambang server.
  const predictedGrade = points <= thresholds.a_max ? "A"
    : points <= (thresholds.a1_max ?? thresholds.a_max) ? "A1"
    : points <= (thresholds.a2_max ?? thresholds.b_max) ? "A2"
    : points <= thresholds.b_max ? "B" : "BS";

  async function save(rollId) {
    setBusy(true);
    try {
      const defects = POINT_LEVELS
        .filter((lv) => Number(form[lv.pv]) > 0)
        .map((lv) => ({ point_value: lv.pv, count: Number(form[lv.pv]) }));
      // PS-15 — kirim apa adanya (boleh "182,5"); backend memakai parse_decimal.
      // FASE C — lot supplier / dye lot / shade ikut disimpan ke lot (SSOT).
      const res = await axios.post(`${API}/inbound/rolls/${rollId}/inspect`, {
        defects, gsm_actual: gsm === "" ? null : gsm,
        width_actual: width === "" ? null : width, note,
        supplier_lot: lotDraft.supplier_lot || "",
        dye_lot: lotDraft.dye_lot || "",
        shade_ref: lotDraft.shade_ref || "",
      });
      setLotWarnings(res.data?.lot_warnings || []);
      setOpenRoll(null);
      await load();
      onDone?.();
    } catch (e) {
      setError(e.response?.data?.detail || "Inspeksi gagal.");
    } finally { setBusy(false); }
  }

  const gradeTone = (g) => (g === "A" || g === "A1") ? "pill-success"
    : (g === "A2" || g === "B") ? "pill-warning" : g === "BS" ? "pill-danger" : "pill-muted";

  return (
    <div className="modal-overlay" data-testid="roll-inspection-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 720, width: "95vw", maxHeight: "92vh", overflowY: "auto" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2] sticky top-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <Ruler size={16} className="text-[#0058CC]" />
            <div>
              <h2 className="text-[14px] font-bold">Inspeksi 4-Point per Roll</h2>
              <p className="text-[10.5px] text-[#6B6B73]" data-testid="roll-inspect-thresholds">
                {taskLabel} · Grade (D-01): ≤{thresholds.a_max}=A, ≤{thresholds.a1_max}=A1,
                ≤{thresholds.a2_max}=A2, ≤{thresholds.b_max}=B, &gt;{thresholds.b_max}=BS
              </p>
            </div>
          </div>
          <button data-testid="roll-inspect-close" onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-2">
          {error && <div className="notice-bar danger"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
          {loading ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]"><RefreshCw size={18} className="animate-spin mx-auto mb-2" /> Memuat roll...</div>
          ) : rolls.length === 0 ? (
            <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="roll-inspect-empty">Tidak ada roll untuk tugas ini.</div>
          ) : rolls.map((roll) => (
            <div key={roll.id} data-testid={`roll-card-${roll.id}`} className="rounded-md border border-[#EFF0F2]">
              <div className="flex items-center justify-between px-3 py-2">
                <div className="min-w-0">
                  <p className="text-[12.5px] font-semibold">{roll.roll_no} · {roll.sku}
                    {roll.grade && <span className={`status-pill ${gradeTone(roll.grade)} ml-2`} data-testid={`roll-grade-${roll.id}`}>Grade {roll.grade}</span>}
                    {roll.inspected && <CheckCircle2 size={13} className="inline ml-1 text-emerald-500" />}
                  </p>
                  <p className="text-[10.5px] text-[#9A9BA3]">
                    {formatQty(roll.length_initial)} {roll.unit} · Std GSM {roll.gsm_standard ?? "—"} · Std Lebar {roll.width_standard ?? "—"}
                    {roll.inspection?.points != null && <> · {roll.inspection.points} poin</>}
                  </p>
                  <p className="text-[10.5px]" data-testid={`roll-lot-info-${roll.id}`}>
                    <span className="font-semibold text-[#0058CC]">{roll.lot_number || "tanpa lot"}</span>
                    <span className="text-[#9A9BA3]">
                      {" "}· lot supplier {roll.supplier_lot || "—"} · dye lot {roll.dye_lot || "—"}
                      {roll.lot_status ? ` · ${roll.lot_status}` : ""}
                    </span>
                  </p>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <button data-testid={`roll-grade-history-btn-${roll.id}`}
                          onClick={() => setGradePanelRoll(roll)}
                          className="secondary-button text-[11px]" title="Riwayat & override grade (PS-09)">
                    Grade
                  </button>
                  <button data-testid={`roll-inspect-btn-${roll.id}`} onClick={() => (openRoll === roll.id ? setOpenRoll(null) : openForm(roll))}
                          className="secondary-button text-[11px]">{roll.inspected ? "Ubah" : "Inspeksi"}</button>
                </div>
              </div>

              {openRoll === roll.id && (
                <div className="px-3 pb-3 border-t border-[#EFF0F2] pt-2.5" data-testid={`roll-inspect-form-${roll.id}`}>
                  <p className="text-[11px] font-bold uppercase text-[#6B6B73] mb-1.5">Poin Defect (4-Point)</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {POINT_LEVELS.map((lv) => (
                      <div key={lv.pv}>
                        <label className="block text-[10px] text-[#6B6B73] mb-0.5">{lv.label}</label>
                        <input type="number" min="0" data-testid={`roll-defect-${lv.pv}`} value={form[lv.pv] ?? ""}
                          onChange={(e) => setForm((f) => ({ ...f, [lv.pv]: e.target.value }))}
                          className="field text-center" placeholder="0" />
                      </div>
                    ))}
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-2">
                    <div><label className="block text-[10px] text-[#6B6B73] mb-0.5">GSM aktual</label>
                      <DecimalInput data-testid={`roll-gsm-${roll.id}`} value={gsm} onChange={setGsm} min={0}
                        placeholder={String(roll.gsm_standard ?? "gsm")} /></div>
                    <div><label className="block text-[10px] text-[#6B6B73] mb-0.5">Lebar aktual</label>
                      <DecimalInput data-testid={`roll-width-${roll.id}`} value={width} onChange={setWidth} min={0}
                        placeholder={String(roll.width_standard ?? "cm")} /></div>
                    <div><label className="block text-[10px] text-[#6B6B73] mb-0.5">Catatan</label>
                      <input value={note} onChange={(e) => setNote(e.target.value)} className="field" placeholder="opsional" /></div>
                  </div>
                  {/* FASE C (D-10) — lengkapi identitas lot saat inspeksi (PS-10) */}
                  <div className="mt-2 rounded-md border border-[#EFF0F2] bg-[#FAFBFC] px-2 py-2"
                    data-testid={`roll-lot-fields-${roll.id}`}>
                    <p className="mb-1 text-[10px] font-bold uppercase text-[#6B6B73]">
                      Identitas lot {roll.lot_number ? `· ${roll.lot_number}` : ""}
                      <span className={`ml-1 font-semibold ${(lotSettings?.enforcement_mode === "block") ? "text-rose-600" : "text-amber-600"}`}>
                        {(lotSettings?.enforcement_mode === "block") ? "(wajib — mode blokir)" : "(disarankan — mode peringatan)"}
                      </span>
                    </p>
                    <div className="grid grid-cols-3 gap-2">
                      <div><label className="block text-[10px] text-[#6B6B73] mb-0.5">Lot supplier</label>
                        <input data-testid={`roll-supplier-lot-${roll.id}`} className="field"
                          value={lotDraft.supplier_lot} placeholder="mis. SUP-2024-118"
                          onChange={(e) => setLotDraft({ ...lotDraft, supplier_lot: e.target.value })} /></div>
                      <div><label className="block text-[10px] text-[#6B6B73] mb-0.5">Dye lot / shade</label>
                        <input data-testid={`roll-dye-lot-${roll.id}`} className="field"
                          value={lotDraft.dye_lot} placeholder="mis. DL-RED-01"
                          onChange={(e) => setLotDraft({ ...lotDraft, dye_lot: e.target.value })} /></div>
                      <div><label className="block text-[10px] text-[#6B6B73] mb-0.5">Referensi shade</label>
                        <input data-testid={`roll-shade-ref-${roll.id}`} className="field"
                          value={lotDraft.shade_ref} placeholder="mis. SHADE-A"
                          onChange={(e) => setLotDraft({ ...lotDraft, shade_ref: e.target.value })} /></div>
                    </div>
                    {lotWarnings.length > 0 && (
                      <div className="mt-1" data-testid={`roll-lot-warnings-${roll.id}`}>
                        {lotWarnings.map((w) => (
                          <p key={w} className="text-[10.5px] text-amber-700">⚠ {w}</p>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center justify-between mt-2.5 rounded-md bg-[#FAFBFC] border border-[#EFF0F2] px-3 py-2">
                    <span className="text-[12px]">Total Poin: <b className="tabular-nums" data-testid={`roll-points-${roll.id}`}>{points}</b></span>
                    <span className="text-[12px]">Grade: <span className={`status-pill ${gradeTone(predictedGrade)}`} data-testid={`roll-predicted-${roll.id}`}>{predictedGrade}</span></span>
                    <button data-testid={`roll-inspect-save-${roll.id}`} disabled={busy} onClick={() => save(roll.id)} className="primary-button text-[11px]">{busy ? "..." : "Simpan & Set Grade"}</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      {gradePanelRoll && (
        <RollGradePanel rollId={gradePanelRoll.id} rollNo={gradePanelRoll.roll_no}
          currentUser={currentUser} onClose={() => setGradePanelRoll(null)}
          onChanged={() => { load(); onDone?.(); }} />
      )}
    </div>
  );
}
