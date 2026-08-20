import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  ShieldCheck, RefreshCw, CheckCircle2, XCircle, PackageCheck,
  AlertTriangle, RotateCcw, Trash2,
} from "lucide-react";
import { formatQty } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import useDomainEnums from "../../hooks/useDomainEnums";
import RollInspectionModal from "./RollInspectionModal";

/**
 * QC Inspection (Depth #3a) — antrian inspeksi QC barang masuk.
 * Barang yang diterima (GR) ditahan di KARANTINA; inspektur memutuskan:
 *   - Terima (accept) → stok available + auto-fulfill backorder
 *   - Tolak (reject)  → Barang Rusak (damaged) ATAU Retur ke Supplier (Nota Debit)
 */
const DISPOSITION_OPTIONS = [
  { value: "damaged", label: "Barang Rusak — simpan di gudang (rusak)" },
  { value: "return", label: "Retur ke Supplier — terbitkan Nota Debit" },
];

// Fase A · PS-09/R7 — opsi grade DIAMBIL dari registry (`/api/enums`).
// Nilai lama "A+" & "C" TIDAK sah lagi; enum resmi: A | A1 | A2 | B | BS (D-01).

export default function QCInspection({ currentUser, selectedEntity }) {
  const { options: enumOptions, labelOf } = useDomainEnums();
  const gradeOptions = enumOptions("grade");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [active, setActive] = useState(null);   // task being inspected
  const [roll4pTask, setRoll4pTask] = useState(null);  // task for 4-point roll inspection
  const [accept, setAccept] = useState("");
  const [reject, setReject] = useState("");
  const [disposition, setDisposition] = useState("damaged");
  const [acceptGrade, setAcceptGrade] = useState("A");
  const [defects, setDefects] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [formErr, setFormErr] = useState("");

  useEffect(() => { load(); }, []);   // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/inbound/qc/queue`);
      setRows(Array.isArray(res.data) ? res.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat antrian QC.");
    } finally { setLoading(false); }
  }

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 4000); }

  function openInspect(task) {
    setActive(task);
    setAccept(String(task.quarantine_qty ?? task.quantity ?? 0));
    setReject("0");
    setDisposition("damaged");
    setAcceptGrade("A");
    setDefects("");
    setReason("");
    setFormErr("");
  }

  const totalQuarantine = useMemo(
    () => rows.reduce((s, t) => s + (Number(t.quarantine_qty) || 0), 0), [rows]);

  const acceptNum = Number(accept) || 0;
  const rejectNum = Number(reject) || 0;
  const maxQty = active ? Number(active.quarantine_qty || 0) : 0;
  const allocated = Math.round((acceptNum + rejectNum) * 100) / 100;
  const overAllocated = allocated > maxQty + 0.05;

  async function submitDecision() {
    if (!active) return;
    if (acceptNum + rejectNum <= 0.01) { setFormErr("Tentukan qty diterima dan/atau ditolak."); return; }
    if (overAllocated) { setFormErr(`Total (${allocated}) melebihi qty karantina (${maxQty}).`); return; }
    if (rejectNum > 0.01 && disposition === "return" && !active.supplier_name) {
      setFormErr("Task ini tanpa supplier — gunakan disposisi 'Barang Rusak'.");
      return;
    }
    setBusy(true); setFormErr("");
    try {
      const res = await axios.post(`${API}/inbound/tasks/${active.id}/qc-decision`, {
        accept_qty: acceptNum, reject_qty: rejectNum,
        reject_disposition: disposition, reason,
        accept_grade: acceptGrade,
        defects: defects.split(",").map((s) => s.trim()).filter(Boolean),
      });
      const r = res.data || {};
      let msg = `QC ${active.po_number || ""}: diterima ${formatQty(r.accepted_qty || 0)}`;
      if ((r.rejected_qty || 0) > 0) {
        msg += `, ditolak ${formatQty(r.rejected_qty)}`;
        if (r.purchase_return?.number) msg += ` → Nota Debit ${r.purchase_return.number}`;
        else msg += ` (rusak)`;
      }
      flash(msg + ".");
      setActive(null);
      await load();
    } catch (e) {
      setFormErr(e.response?.data?.detail || "Keputusan QC gagal.");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="qc-inspection-view" className="grid gap-4">
      {/* Header + metrics */}
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-[#0058CC]" />
            <h2>Inspeksi QC — Penerimaan</h2>
          </div>
          <button data-testid="qc-refresh" className="btn-secondary" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Muat ulang
          </button>
        </div>
        <div className="section-body">
          <p className="text-[12.5px] text-[#6B6B73] mb-3">
            Barang yang baru diterima ditahan di <b>karantina</b> sampai lolos inspeksi QC.
            Terima untuk menjadikannya stok tersedia, atau tolak (barang rusak / retur ke supplier).
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <div className="metric-tile" data-testid="qc-metric-tasks">
              <p className="metric-label">Tugas Menunggu QC</p>
              <p className="metric-value tabular-nums">{rows.length}</p>
            </div>
            <div className="metric-tile" data-testid="qc-metric-quarantine">
              <p className="metric-label">Total di Karantina</p>
              <p className="metric-value tabular-nums">{formatQty(totalQuarantine)} m</p>
            </div>
          </div>
        </div>
      </section>

      {toast && (
        <div className="notice-bar success" data-testid="qc-toast">
          <span><CheckCircle2 size={14} className="inline mr-1" />{toast}</span>
          <button onClick={() => setToast("")}>×</button>
        </div>
      )}

      {/* Queue */}
      <section className="section-card">
        <div className="section-head"><h3>Antrian Inspeksi</h3></div>
        <div className="section-body">
          {loading ? (
            <div data-testid="qc-loading" className="py-10 text-center text-[#9A9BA3] text-[13px]">
              <RefreshCw size={20} className="animate-spin mx-auto mb-2" /> Memuat antrian QC…
            </div>
          ) : error ? (
            <div data-testid="qc-error" className="notice-bar danger">
              <span><AlertTriangle size={14} className="inline mr-1" />{error}</span>
              <button onClick={load}>Coba lagi</button>
            </div>
          ) : rows.length === 0 ? (
            <div data-testid="qc-empty" className="py-12 text-center">
              <PackageCheck size={32} className="mx-auto mb-2 text-[#34C759]" />
              <p className="text-[13.5px] font-semibold">Tidak ada barang menunggu QC</p>
              <p className="text-[12px] text-[#9A9BA3]">Semua penerimaan sudah diinspeksi.</p>
            </div>
          ) : (
            <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
              <div className="grid grid-cols-[1.6fr_1fr_120px_120px] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase text-[#6B6B73]">
                <span>Produk</span><span>PO / Supplier</span>
                <span className="text-right">Karantina</span><span className="text-right">Aksi</span>
              </div>
              {rows.map((t, i) => (
                <div key={t.id} data-testid={`qc-task-row-${i}`}
                     className="grid grid-cols-[1.6fr_1fr_120px_120px] items-center px-3 py-2.5 border-t border-[#F4F5F7]">
                  <div className="min-w-0">
                    <p className="text-[12.5px] font-semibold truncate">{t.product_name || t.product_id}</p>
                    <p className="text-[10.5px] text-[#9A9BA3]">{t.sku} · {t.warehouse_name || t.warehouse_id}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold text-[#0058CC] truncate">{t.po_number || "—"}</p>
                    <p className="text-[10.5px] text-[#9A9BA3] truncate">{t.supplier_name || "Tanpa supplier"}</p>
                  </div>
                  <span className="text-[12.5px] tabular-nums text-right font-semibold text-[#8C4A00]">
                    {formatQty(t.quarantine_qty)} m
                  </span>
                  <div className="text-right flex flex-col items-end gap-1">
                    <button data-testid={`qc-inspect-btn-${i}`} className="btn-primary btn-sm"
                            onClick={() => openInspect(t)}>
                      <ShieldCheck size={13} /> Inspeksi
                    </button>
                    <button data-testid={`qc-4point-btn-${i}`} className="btn-secondary btn-sm"
                            onClick={() => setRoll4pTask(t)}>
                      <ShieldCheck size={12} /> 4-Point Roll
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Inspect modal */}
      {active && (
        <div className="modal-overlay" data-testid="qc-inspect-modal">
          <div className="modal-card">
            <p className="modal-title">Inspeksi QC — {active.product_name}</p>
            <p className="modal-subtitle">
              {active.po_number} · {active.supplier_name || "Tanpa supplier"} ·
              Karantina <b>{formatQty(active.quarantine_qty)} m</b>
            </p>
            {formErr && <div className="notice-bar danger"><span>{formErr}</span><button onClick={() => setFormErr("")}>×</button></div>}

            <div className="grid gap-3 mt-2">
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1.5">
                  <label className="text-[11px] font-bold uppercase text-[#1E7B34] flex items-center gap-1">
                    <CheckCircle2 size={13} /> Diterima (m)
                  </label>
                  <input data-testid="qc-accept-input" type="number" min="0" step="0.01"
                         className="form-input" value={accept}
                         onChange={(e) => setAccept(e.target.value)} />
                </div>
                <div className="grid gap-1.5">
                  <label className="text-[11px] font-bold uppercase text-[#B3261E] flex items-center gap-1">
                    <XCircle size={13} /> Ditolak (m)
                  </label>
                  <input data-testid="qc-reject-input" type="number" min="0" step="0.01"
                         className="form-input" value={reject}
                         onChange={(e) => setReject(e.target.value)} />
                </div>
              </div>

              <div className="flex items-center justify-between text-[11.5px] px-1">
                <span className="text-[#6B6B73]">Total dialokasikan</span>
                <span className={`tabular-nums font-semibold ${overAllocated ? "text-[#B3261E]" : "text-[#1C1C1E]"}`}>
                  {formatQty(allocated)} / {formatQty(maxQty)} m
                </span>
              </div>

              {acceptNum > 0.01 && (
                <div className="grid gap-1.5 rounded-md bg-[#F0FCF3] border border-[#BBE9C8] p-2.5">
                  <label className="text-[11px] font-bold uppercase text-[#1E7B34]">Grade Diterima (hasil inspeksi)</label>
                  <KNSelect
                    data-testid="qc-accept-grade-select"
                    className="form-input"
                    value={acceptGrade}
                    onValueChange={setAcceptGrade}
                    options={gradeOptions}
                  />
                  <p className="text-[10.5px] text-[#1E7B34]">
                    Urutan mutu (D-01): A → A1 → A2 → B → BS. Grade terpilih:{" "}
                    <b data-testid="qc-accept-grade-label">{labelOf("grade", acceptGrade)}</b>
                  </p>
                  <label className="text-[11px] font-bold uppercase text-[#1E7B34] mt-1">Profil Cacat (opsional, pisah koma)</label>
                  <input data-testid="qc-defects-input" className="form-input" placeholder="mis. belang, noda kuning"
                         value={defects} onChange={(e) => setDefects(e.target.value)} />
                </div>
              )}

              {rejectNum > 0.01 && (
                <div className="grid gap-1.5 rounded-md bg-[#FFF8EE] border border-[#FFE2B8] p-2.5">
                  <label className="text-[11px] font-bold uppercase text-[#8C4A00]">Disposisi Barang Ditolak</label>
                  <KNSelect
                    data-testid="qc-disposition-select"
                    className="form-input"
                    value={disposition}
                    onValueChange={setDisposition}
                    options={DISPOSITION_OPTIONS}
                  />
                  <p className="text-[10.5px] text-[#8C4A00] flex items-center gap-1">
                    {disposition === "return"
                      ? <><RotateCcw size={12} /> Membuat retur beli (Nota Debit) ke {active.supplier_name || "supplier"}.</>
                      : <><Trash2 size={12} /> Barang dicatat sebagai rusak & tetap di gudang.</>}
                  </p>
                </div>
              )}

              <div className="grid gap-1.5">
                <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Catatan / Alasan</label>
                <input data-testid="qc-reason-input" className="form-input" placeholder="mis. 5m luntur, sisanya OK"
                       value={reason} onChange={(e) => setReason(e.target.value)} />
              </div>

              <div className="flex gap-2 pt-1">
                <button data-testid="qc-accept-all" className="btn-secondary btn-sm flex-1"
                        onClick={() => { setAccept(String(maxQty)); setReject("0"); }}>
                  Terima Semua
                </button>
                <button data-testid="qc-reject-all" className="btn-secondary btn-sm flex-1"
                        onClick={() => { setReject(String(maxQty)); setAccept("0"); }}>
                  Tolak Semua
                </button>
              </div>
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setActive(null)} disabled={busy}>Batal</button>
              <button data-testid="qc-submit-decision" className="btn-primary"
                      onClick={submitDecision} disabled={busy || overAllocated}>
                {busy ? "Memproses…" : "Simpan Keputusan QC"}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* 4-Point per-roll inspection modal (Fase 6.2) */}
      {roll4pTask && (
        <RollInspectionModal
          currentUser={currentUser}
          taskId={roll4pTask.id}
          taskLabel={`${roll4pTask.po_number || ""} · ${roll4pTask.product_name || roll4pTask.sku || ""}`}
          entityId={selectedEntity}
          onClose={() => setRoll4pTask(null)}
          onDone={() => flash("Grade roll diperbarui dari inspeksi 4-Point.")}
        />
      )}
    </div>
  );
}
