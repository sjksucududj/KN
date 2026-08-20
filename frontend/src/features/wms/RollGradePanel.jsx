/**
 * RollGradePanel (Fase A · PS-09 · D-01/D-23) — tata kelola grade satu roll.
 *
 * Menampilkan grade aktif + RIWAYAT perubahan (before → after, sumber, alasan,
 * aktor) dan menyediakan **override** grade tanpa inspeksi yang:
 *   • hanya untuk admin/manager,
 *   • WAJIB menyertakan alasan,
 *   • selalu tercatat di `grade_history` + audit log.
 *
 * Props: rollId, rollNo, currentUser, onClose, onChanged
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, History, ShieldCheck, X } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import KNSelect from "../../components/KNSelect";
import useDomainEnums from "../../hooks/useDomainEnums";

export default function RollGradePanel({ rollId, rollNo = "", currentUser, onClose, onChanged }) {
  const { options, labelOf } = useDomainEnums();
  const role = currentUser?.role;
  const canOverride = role === "admin" || role === "manager";

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [grade, setGrade] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [okMsg, setOkMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await axios.get(`${API}/inventory/rolls/${rollId}/grade-history`);
      setData(res.data || null);
      setGrade(res.data?.grade || "");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat riwayat grade roll.");
    } finally { setLoading(false); }
  }, [rollId]);

  useEffect(() => { load(); }, [load]);

  async function submitOverride() {
    setBusy(true); setError(""); setOkMsg("");
    try {
      const res = await axios.post(`${API}/inventory/rolls/${rollId}/grade-override`,
        { grade, reason });
      setOkMsg(`Grade diubah ${res.data?.grade_before || "—"} → ${res.data?.grade_after}.`);
      setReason("");
      await load();
      if (onChanged) onChanged(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal mengubah grade roll.");
    } finally { setBusy(false); }
  }

  const history = Array.isArray(data?.history) ? data.history : [];
  const tone = (dir) => (dir === "turun" ? "pill-danger" : dir === "naik" ? "pill-success" : "pill-muted");

  return (
    <div className="modal-overlay" data-testid="roll-grade-panel">
      <div className="modal-card max-w-[560px]">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="modal-title">Grade Roll {rollNo || data?.roll_no || ""}</p>
            <p className="modal-subtitle">
              Grade aktif:{" "}
              <b data-testid="roll-grade-current">{data?.grade || "—"}</b>
              {data?.grade ? ` · ${labelOf("grade", data.grade)}` : ""}
              {data?.grade_source ? ` · sumber: ${labelOf("grade_change_source", data.grade_source)}` : ""}
            </p>
          </div>
          <button data-testid="roll-grade-close" className="icon-button" onClick={onClose} aria-label="Tutup">
            <X size={15} />
          </button>
        </div>

        {error && (
          <div className="notice-bar danger" data-testid="roll-grade-error">
            <span>{error}</span><button onClick={() => setError("")}>×</button>
          </div>
        )}
        {okMsg && (
          <div className="notice-bar" data-testid="roll-grade-success">
            <span>{okMsg}</span><button onClick={() => setOkMsg("")}>×</button>
          </div>
        )}

        <div className="mt-2 grid gap-3">
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-2.5">
            <p className="mb-1.5 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">
              <History size={12} /> Riwayat Perubahan Grade
            </p>
            {loading ? (
              <p data-testid="roll-grade-loading" className="text-[11.5px] text-[#6B6B73]">Memuat riwayat…</p>
            ) : history.length === 0 ? (
              <p data-testid="roll-grade-history-empty" className="text-[11.5px] text-[#6B6B73]">
                Belum ada perubahan grade tercatat untuk roll ini.
              </p>
            ) : (
              <div className="grid gap-1.5">
                {history.slice().reverse().map((h, i) => (
                  <div key={i} data-testid={`roll-grade-history-${i}`}
                    className="rounded-md border border-[#EFF0F2] bg-white px-2 py-1.5 text-[11.5px]">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono font-semibold">{h.grade_before || "—"} → {h.grade_after}</span>
                      <span className={`status-pill ${tone(h.direction)}`}>{h.direction}</span>
                      <span className="status-pill pill-muted">{h.source_label || h.source}</span>
                      <span className="ml-auto text-[10.5px] text-[#8E8E93]">
                        {h.changed_at ? new Date(h.changed_at).toLocaleString("id-ID") : ""}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10.5px] text-[#3C3C43]">
                      {h.reason || "—"} · oleh <b>{h.changed_by || "sistem"}</b>
                      {h.changed_by_role ? ` (${h.changed_by_role})` : ""}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-md border border-[#FFE2B8] bg-[#FFF8EE] p-2.5">
            <p className="mb-1.5 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-[#8C4A00]">
              <ShieldCheck size={12} /> Override Grade tanpa Inspeksi (D-23)
            </p>
            {!canOverride ? (
              <p data-testid="roll-grade-no-permission" className="flex items-start gap-1 text-[11.5px] text-[#8C4A00]">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                Hanya <b>manager/admin</b> yang boleh mengubah grade tanpa inspeksi. Jalur normal:
                inspeksi QC 4-point.
              </p>
            ) : (
              <div className="grid gap-2">
                <p className="text-[10.5px] text-[#8C4A00]">
                  Jalur normal perubahan grade adalah <b>inspeksi QC</b>. Override hanya untuk koreksi
                  salah input / kasus darurat — alasan WAJIB dan tercatat permanen.
                </p>
                <div className="grid gap-2 md:grid-cols-[160px_1fr_auto]">
                  <KNSelect data-testid="roll-grade-select" className="field" value={grade}
                    placeholder="Grade baru" onValueChange={setGrade} options={options("grade")} />
                  <input data-testid="roll-grade-reason-input" className="field"
                    placeholder="Alasan (wajib) — mis. salah input grade saat inspeksi awal"
                    value={reason} onChange={(e) => setReason(e.target.value)} />
                  <button data-testid="roll-grade-submit" className="primary-button"
                    disabled={busy || !grade || !reason.trim()} onClick={submitOverride}>
                    {busy ? "Menyimpan…" : "Simpan Grade"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="modal-actions">
          <button data-testid="roll-grade-done" className="btn-secondary" onClick={onClose}>Tutup</button>
        </div>
      </div>
    </div>
  );
}
