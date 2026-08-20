import { useEffect, useState } from "react";
import { Package, Scan, X, ChevronRight } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { apiErrorText } from "../../utils/apiError";
import { notifySuccess } from "../../utils/feedback";
import { overlayDismiss } from "../../utils/overlayDismiss";
import GRCatchWeightModal from "./inbound/GRCatchWeightModal";
import InboundTaskPanel, { TaskBadge } from "./inbound/InboundTaskPanel";
import useReceivingUom from "../../hooks/useReceivingUom";
import { formatQty } from "../../utils/formatters";
import { kgPerBaseUnit } from "../../utils/uom";

function MiniBar({ pct, status }) {
  const color = status === 'completed' ? 'bg-[#34C759]' : status === 'escalated' ? 'bg-red-400' : 'bg-[#007AFF]';
  return (
    <div className="h-1 w-full rounded-full bg-gray-200 overflow-hidden">
      <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
}

const EMPTY_SCAN = { doc_uom: "", doc_qty: "", batch: "", lot: "", dye_lot: "",
                     grade: "A", roll_id: "", bin_id: "" };

export default function InboundScanInterface({ user }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedTask, setSelectedTask] = useState(null);
  const [filterStatus, setFilterStatus] = useState("all");

  const [cameraActive, setCameraActive] = useState(false);
  const [scanValue, setScanValue] = useState("");
  const [scanData, setScanData] = useState(EMPTY_SCAN);

  const [showEscalateModal, setShowEscalateModal] = useState(false);
  const [escalationReason, setEscalationReason] = useState("");
  // FASE P5 — galat eskalasi tampil DI DALAM pop-upnya (lihat OutboundScanInterface).
  const [escalateError, setEscalateError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Fase 8 (Catch-weight) — entri roll saat Goods Receipt (panjang m + berat kg per roll).
  const [products, setProducts] = useState({});
  const [showGRModal, setShowGRModal] = useState(false);
  const [grRolls, setGrRolls] = useState([]);
  // FASE C (D-10/D-27) — identitas lot batch penerimaan + kebijakan penegakan
  const [lotFields, setLotFields] = useState({ supplier_lot: "", lot_number: "", shade_ref: "" });
  const [lotSettings, setLotSettings] = useState(null);
  const [lotResult, setLotResult] = useState(null);   // {lots:[], warnings:[]}
  const round2 = (n) => Math.round((Number(n) + Number.EPSILON) * 100) / 100;
  // FASE B/C — berat per BASE UNIT produk (yard ≠ meter) → prefill GR sama dgn server.
  const kgPerMeter = (p) => kgPerBaseUnit(p);

  // FASE F-1 — opsi satuan (termasuk satuan supplier) + pratinjau konversi dari server
  const uom = useReceivingUom(selectedTask?.id);

  useEffect(() => {
    axios.get(`${API}/products`).then((r) => {
      const m = {};
      (r.data || []).forEach((p) => { m[p.id] = p; });
      setProducts(m);
    }).catch(() => { /* opsional */ });
  }, []);

  useEffect(() => { fetchTasks(); }, [filterStatus]);

  // FASE C — kebijakan penegakan lot (warn/block) ditarik sekali untuk form GR
  useEffect(() => {
    axios.get(`${API}/lots/settings`).then((r) => setLotSettings(r.data))
      .catch(() => setLotSettings({ enforcement_mode: "warn", require_supplier_lot: true,
                                    require_dye_lot: true }));
  }, []);

  // FASE F-1 — satuan default mengikuti kebijakan server (`prefer` → satuan supplier)
  useEffect(() => {
    const def = uom.options?.default_uom;
    if (def) setScanData((prev) => (prev.doc_uom ? prev : { ...prev, doc_uom: def }));
  }, [uom.options]);

  // pratinjau live setiap qty/satuan berubah (debounce di hook)
  useEffect(() => {
    if (!selectedTask) return;
    uom.runPreview(scanData.doc_uom, scanData.doc_qty);
  }, [scanData.doc_uom, scanData.doc_qty, selectedTask?.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const params = filterStatus !== "all" ? `?status=${filterStatus}` : "";
      const res = await axios.get(`${API}/inbound/tasks${params}`);
      setTasks(res.data);
      setError("");
    } catch (e) { setError(e.response?.data?.detail || "Gagal memuat inbound task."); }
    finally { setLoading(false); }
  };

  const selectTask = (task) => {
    stopCamera();
    setSelectedTask(task);
    setScanData({ ...EMPTY_SCAN, doc_uom: "" });
    setScanValue("");
  };

  const startCamera = async () => {
    try {
      const { BrowserMultiFormatReader } = await import("@zxing/browser");
      const reader = new BrowserMultiFormatReader();
      const el = document.getElementById("inbound-video-compact");
      if (!el) return;
      await reader.decodeFromVideoDevice(null, el, (result) => {
        if (result) { setScanValue(result.getText()); stopCamera(); }
      });
      setCameraActive(true);
    } catch { setError("Gagal membuka kamera. Beri izin kamera pada peramban, atau ketik kode roll secara manual."); }
  };

  const stopCamera = () => {
    const el = document.getElementById("inbound-video-compact");
    if (el?.srcObject) { el.srcObject.getTracks().forEach(t => t.stop()); el.srcObject = null; }
    setCameraActive(false);
  };

  const handleScanReceive = async () => {
    if (!selectedTask) return;
    const qty = Number(scanData.doc_qty);
    if (!Number.isFinite(qty) || qty <= 0) {
      setError("Masukkan jumlah yang diterima (lebih besar dari 0) sebelum menyimpan penerimaan.");
      return;
    }
    const docUom = scanData.doc_uom || uom.options?.task_uom || "";
    setSubmitting(true);
    try {
      // FASE F-1 — server yang mengonversi ke satuan PO & menyimpan jejaknya (D-07).
      const res = await axios.post(`${API}/inbound/tasks/${selectedTask.id}/scan-receive`, {
        product_id: selectedTask.product_id,
        doc_uom: docUom, doc_qty: qty,
        batch: scanData.batch, lot: scanData.lot, dye_lot: scanData.dye_lot,
        grade: scanData.grade, roll_id: scanData.roll_id, bin_id: scanData.bin_id,
      });
      setTasks(prev => prev.map(t => t.id === selectedTask.id ? res.data : t));
      setSelectedTask(res.data);
      setScanData({ ...EMPTY_SCAN, doc_uom: docUom });
      setScanValue("");
      uom.clearPreview();
      uom.reload();
      setError("");
      notifySuccess("Penerimaan tercatat",
        `Diterima ${formatQty(res.data?.received_qty || 0)} dari ${formatQty(res.data?.expected_qty || 0)} ${res.data?.unit || ""}.`);
    } catch (e) { setError(apiErrorText(e, "Gagal mencatat penerimaan.")); }
    finally { setSubmitting(false); }
  };

  // Fase 8 — buka modal entri roll catch-weight; prefilled 1 roll dari qty diterima.
  const openComplete = () => {
    if (!selectedTask) return;
    if ((selectedTask.received_qty || 0) < selectedTask.expected_qty) {
      setError(`Jumlah diterima (${formatQty(selectedTask.received_qty || 0)} ${selectedTask.unit || ""}) `
        + `masih di bawah pesanan (${formatQty(selectedTask.expected_qty)} ${selectedTask.unit || ""}). `
        + `Terima sisanya, atau eskalasi ke manajer bila barangnya memang kurang.`);
      return;
    }
    const isKg = (selectedTask.unit || "").toLowerCase() === "kg";
    const kgm = kgPerMeter(products[selectedTask.product_id]);
    const recv = Number(selectedTask.received_qty) || 0;
    setGrRolls([{
      length: isKg ? (kgm > 0 ? round2(recv / kgm) : 0) : recv,
      weight: isKg ? recv : (kgm > 0 ? round2(recv * kgm) : 0),
      dye_lot: selectedTask.dye_lot || "",
      grade: "A",
    }]);
    setShowGRModal(true);
  };

  const submitComplete = async () => {
    if (!selectedTask) return;
    setSubmitting(true);
    try {
      const rolls = grRolls.map((r) => ({
        length: Number(r.length) || 0,
        weight: Number(r.weight) || 0,
        dye_lot: r.dye_lot || "",
        grade: r.grade || "A",
      }));
      // FASE C — identitas lot batch dikirim bersama rincian roll
      const res = await axios.post(`${API}/inbound/tasks/${selectedTask.id}/complete`, {
        rolls,
        supplier_lot: lotFields.supplier_lot || "",
        lot_number: lotFields.lot_number || "",
        shade_ref: lotFields.shade_ref || "",
      });
      setLotResult({ lots: res.data?.lots || [], warnings: res.data?.lot_warnings || [] });
      setShowGRModal(false);
      setGrRolls([]);
      setLotFields({ supplier_lot: "", lot_number: "", shade_ref: "" });
      fetchTasks();
      setSelectedTask(null);
      setError("");
      notifySuccess("Barang masuk gudang",
        `${(res.data?.lots || []).length || 1} lot terbentuk dari ${rolls.length} roll.`);
    } catch (e) { setError(apiErrorText(e, "Gagal menyelesaikan penerimaan.")); }
    finally { setSubmitting(false); }
  };

  const handleEscalate = async () => {
    if (!escalationReason.trim()) {
      setEscalateError("Tulis dulu alasan eskalasinya — manajer memakai catatan ini untuk memutuskan.");
      return;
    }
    setEscalateError("");
    setSubmitting(true);
    try {
      await axios.post(`${API}/inbound/tasks/${selectedTask.id}/escalate`, null, {
        params: { reason: escalationReason }
      });
      setShowEscalateModal(false);
      setEscalationReason("");
      fetchTasks();
      setSelectedTask(null);
      notifySuccess("Dieskalasi ke manajer", "Tugas menunggu keputusan manajer.");
    } catch (e) { setEscalateError(apiErrorText(e, "Gagal mengeskalasi tugas.")); }
    finally { setSubmitting(false); }
  };

  const FILTERS = ["all", "waiting_goods", "receiving", "qc_check", "escalated"];
  const FILTER_LABELS = { all: "Semua", waiting_goods: "Waiting", receiving: "Receiving", qc_check: "QC", escalated: "Escalated" };

  return (
    <div data-testid="inbound-scan-panel" className="flex flex-col gap-3">
      <ErrorNotice message={error} onRetry={fetchTasks} onDismiss={() => setError("")} testId="inbound-scan-error" />
      {/* FASE C — hasil pembentukan lot setelah penerimaan + peringatan kelengkapan */}
      {lotResult && (
        <div data-testid="gr-lot-result"
          className={`rounded-md border px-2.5 py-2 ${lotResult.warnings.length
            ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-[11.5px] font-semibold text-[#1C1C1E]">
                Penerimaan selesai · lot terbentuk:{" "}
                {(lotResult.lots || []).map((l) => l.lot_number).join(", ") || "—"}
              </p>
              {(lotResult.warnings || []).map((w) => (
                <p key={w} className="text-[10.5px] text-amber-800">⚠ {w}</p>
              ))}
              {!lotResult.warnings.length && (
                <p className="text-[10.5px] text-emerald-700">
                  Identitas lot lengkap — traceability & recall siap dipakai.
                </p>
              )}
            </div>
            <button data-testid="gr-lot-result-close" className="text-[#6B6B73]"
              onClick={() => setLotResult(null)}><X size={14} /></button>
          </div>
        </div>
      )}
      {/* Filter strip */}
      <div className="flex items-center gap-1.5 overflow-x-auto">
        {FILTERS.map(s => (
          <button key={s}
            data-testid={`filter-status-${s}`}
            onClick={() => setFilterStatus(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition-all ${filterStatus === s ? "bg-[#34C759] text-white" : "bg-white border border-[#E5E5EA] text-[#6B6B73] hover:border-[#34C759]"}`}>
            {FILTER_LABELS[s]}
          </button>
        ))}
        <span className="ml-auto text-[11px] text-[#6B6B73] whitespace-nowrap">{tasks.length} tugas</span>
      </div>

      {/* 2-panel layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-3">
        {/* LEFT: Task List */}
        <div className="bg-white border border-[#EFF0F2] rounded-xl overflow-hidden">
          <div className="px-3 py-2 border-b border-[#EFF0F2] bg-[#FAFBFC] flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Tugas Barang Masuk</span>
            <button onClick={fetchTasks} data-testid="inbound-refresh"
              className="text-[#007AFF] text-[11px] font-medium">Refresh</button>
          </div>
          {loading ? (
            <div className="py-8 text-center text-[12px] text-[#6B6B73]">Memuat…</div>
          ) : tasks.length === 0 ? (
            <div className="py-8 text-center text-[12px] text-[#6B6B73]">
              <Package size={28} className="mx-auto mb-2 text-gray-300" />
              <p>Tidak ada tugas barang masuk</p>
            </div>
          ) : (
            <div className="divide-y divide-[#EFF0F2] overflow-y-auto max-h-[520px]">
              {tasks.map(task => {
                const pct = task.expected_qty ? Math.min((task.received_qty || 0) / task.expected_qty * 100, 100) : 0;
                const isSelected = selectedTask?.id === task.id;
                return (
                  <button key={task.id}
                    data-testid={`inbound-task-${task.id}`}
                    onClick={() => selectTask(task)}
                    className={`w-full text-left px-3 py-2.5 hover:bg-[#F5F7FF] transition-colors ${isSelected ? 'bg-[#EFF4FF] border-l-2 border-[#007AFF]' : ''}`}>
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-[12px] font-bold text-[#007AFF]">{task.po_number}</span>
                      <div className="flex items-center gap-1">
                        <TaskBadge status={task.status} />
                        <ChevronRight size={12} className="text-gray-400" />
                      </div>
                    </div>
                    <p className="text-[11px] text-[#3C3C43] truncate">{task.sku}</p>
                    <p className="text-[10px] text-[#8E8E93] truncate">{task.product_name}</p>
                    {/* FASE F-1 — satuan supplier terlihat langsung di daftar */}
                    {task.supplier_uom && task.supplier_uom !== task.unit && (
                      <p data-testid={`inbound-task-supplier-uom-${task.id}`}
                        className="text-[9.5px] font-semibold text-[#0058CC]">
                        surat jalan: {task.supplier_sku || "-"} · per {task.supplier_uom}
                      </p>
                    )}
                    <div className="mt-1.5">
                      <MiniBar pct={pct} status={task.status} />
                      <div className="flex justify-between mt-0.5">
                        <span className="text-[10px] text-[#8E8E93]">{formatQty(task.received_qty || 0)}/{formatQty(task.expected_qty)} {task.unit}</span>
                        <span className="text-[10px] font-semibold text-[#3C3C43]">{pct.toFixed(0)}%</span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* RIGHT: Scan Panel */}
        {selectedTask ? (
          <InboundTaskPanel
            task={selectedTask}
            scanData={scanData}
            setScanData={setScanData}
            uom={uom}
            cameraActive={cameraActive}
            scanValue={scanValue}
            onStartCamera={startCamera}
            onStopCamera={stopCamera}
            onClose={() => { stopCamera(); setSelectedTask(null); }}
            onScanReceive={handleScanReceive}
            onComplete={openComplete}
            onEscalate={() => { setEscalateError(""); setShowEscalateModal(true); }}
            submitting={submitting}
          />
        ) : (
          <div className="bg-white border border-dashed border-[#E5E5EA] rounded-xl flex items-center justify-center">
            <div className="text-center p-8">
              <Scan size={32} className="mx-auto mb-2 text-gray-300" />
              <p className="text-[13px] font-semibold text-[#6B6B73]">Pilih tugas dari daftar</p>
              <p className="text-[11px] text-[#8E8E93] mt-1">Klik baris tugas untuk buka formulir scan</p>
            </div>
          </div>
        )}
      </div>

      {/* Escalate Modal */}
      {showEscalateModal && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" {...overlayDismiss(() => setShowEscalateModal(false))}>
          <div className="bg-white rounded-xl p-5 w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="text-[13px] font-bold mb-3">Eskalasi ke Manager</h3>
            <textarea value={escalationReason} onChange={e => setEscalationReason(e.target.value)}
              data-testid="inbound-escalate-reason"
              className="w-full border border-[#E5E5EA] rounded-lg px-3 py-2 text-sm mb-3" rows="3"
              placeholder="Alasan escalation (contoh: Qty kurang 10m dari PO)" />
            <ErrorNotice message={escalateError} onDismiss={() => setEscalateError("")} testId="inbound-escalate-error" />
            <div className="flex gap-2">
              <button onClick={handleEscalate} disabled={submitting}
                data-testid="inbound-escalate-submit"
                className="flex-1 bg-orange-500 hover:bg-orange-600 text-white rounded-lg px-4 py-2 text-[12px] font-semibold disabled:opacity-50">
                Eskalasi
              </button>
              <button onClick={() => setShowEscalateModal(false)}
                className="flex-1 bg-[#F2F2F7] text-[#3C3C43] rounded-lg px-4 py-2 text-[12px] font-semibold">
                Batal
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Fase 8 — Goods Receipt: entri roll catch-weight (panjang m + berat kg) */}
      {showGRModal && selectedTask && (
        <GRCatchWeightModal
          task={selectedTask}
          product={products[selectedTask.product_id]}
          rolls={grRolls}
          setRolls={setGrRolls}
          onSubmit={submitComplete}
          onClose={() => setShowGRModal(false)}
          submitting={submitting}
          lotFields={lotFields}
          setLotFields={setLotFields}
          lotSettings={lotSettings}
        />
      )}
    </div>
  );
}
