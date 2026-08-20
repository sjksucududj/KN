import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle, XCircle, Package, Truck, Eye, X } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { apiErrorText } from "../../utils/apiError";
import { notifySuccess } from "../../utils/feedback";
import { overlayDismiss } from "../../utils/overlayDismiss";
import { formatQty } from "../../utils/formatters";

/**
 * ManagerEscalationDashboard
 * 
 * Manager dashboard untuk resolve escalated inbound & outbound tasks.
 * Manager bisa adjust qty atau investigate issue.
 */
export default function ManagerEscalationDashboard({ user }) {
  const [escalatedTasks, setEscalatedTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedTask, setSelectedTask] = useState(null);
  const [filterType, setFilterType] = useState("all");
  
  // Resolve state
  const [showResolveModal, setShowResolveModal] = useState(false);
  // FASE P5 — galat penyelesaian tampil DI DALAM pop-up penyelesaian. Kalau ditaruh di
  // bilah halaman, ia tertutup pop-up itu sendiri → manajer hanya melihat tombol yang
  // "tidak jalan" padahal backend menolak dengan alasan yang jelas.
  const [resolveError, setResolveError] = useState("");
  const [resolveData, setResolveData] = useState({
    adjusted_qty: null,
    resolution_notes: ""
  });

  useEffect(() => {
    fetchEscalatedTasks();
  }, [filterType]);

  const fetchEscalatedTasks = async () => {
    setLoading(true);
    try {
      // Fetch both inbound and outbound escalated tasks
      const [inboundRes, outboundRes] = await Promise.all([
        axios.get(`${API}/inbound/tasks?status=escalated`),
        axios.get(`${API}/outbound/tasks?status=escalated`)
      ]);
      
      const inbound = inboundRes.data.map(t => ({ ...t, task_type: "inbound" }));
      const outbound = outboundRes.data.map(t => ({ ...t, task_type: "outbound" }));
      
      let combined = [...inbound, ...outbound];
      
      if (filterType !== "all") {
        combined = combined.filter(t => t.task_type === filterType);
      }
      
      setEscalatedTasks(combined);
      setError("");
    } catch (error) {
      setError(error.response?.data?.detail || "Gagal memuat tugas eskalasi.");
    } finally {
      setLoading(false);
    }
  };

  const handleResolve = async () => {
    if (!selectedTask) return;

    if (!resolveData.resolution_notes.trim()) {
      setResolveError("Tulis dulu catatan penyelesaiannya — catatan ini yang menjelaskan "
        + "kepada gudang & audit mengapa jumlahnya disesuaikan.");
      return;
    }
    setResolveError("");

    try {
      const endpoint = selectedTask.task_type === "inbound"
        ? `${API}/inbound/tasks/${selectedTask.id}/resolve-escalation`
        : `${API}/outbound/tasks/${selectedTask.id}/resolve-escalation`;
      
      await axios.post(endpoint, null, {
        params: {
          adjusted_qty: resolveData.adjusted_qty,
          resolution_notes: resolveData.resolution_notes
        }
      });
      
      notifySuccess("Eskalasi diselesaikan", "Tugas dilanjutkan kembali oleh gudang.");
      setShowResolveModal(false);
      setSelectedTask(null);
      setResolveData({ adjusted_qty: null, resolution_notes: "" });
      fetchEscalatedTasks();
    } catch (error) {
      setResolveError(apiErrorText(error, "Gagal menyelesaikan eskalasi."));
    }
  };

  const getTaskTypeBadge = (type) => {
    return type === "inbound" ? (
      <span className="bg-green-100 text-green-700 text-xs font-semibold px-2 py-1 rounded-full flex items-center gap-1">
        <Package size={12} />
        Barang Masuk
      </span>
    ) : (
      <span className="bg-orange-100 text-orange-700 text-xs font-semibold px-2 py-1 rounded-full flex items-center gap-1">
        <Truck size={12} />
        Barang Keluar
      </span>
    );
  };

  return (
    <div data-testid="escalation-dashboard" className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-red-100">
            <AlertTriangle className="text-red-600" size={20} />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-[#000000]">Escalation Management</h2>
            <p className="text-sm text-[#3C3C43]">Tinjau & selesaikan tugas yang dieskalasi</p>
          </div>
        </div>
        <span className="bg-red-100 text-red-700 text-sm font-bold px-4 py-2 rounded-full">
          {escalatedTasks.length} Tugas
        </span>
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {["all", "inbound", "outbound"].map((type) => (
          <button
            key={type}
            data-testid={`filter-type-${type}`}
            onClick={() => setFilterType(type)}
            className={`rounded-full px-4 py-1.5 text-xs font-medium transition-all ${
              filterType === type
                ? "bg-red-500 text-white"
                : "bg-white border border-[#E5E5EA] text-[#3C3C43] hover:border-red-500"
            }`}
          >
            {type === "all" ? "Semua" : type}
          </button>
        ))}
      </div>

      {/* Tasks List */}
      <ErrorNotice message={error} onRetry={fetchEscalatedTasks} onDismiss={() => setError("")} testId="escalation-error" />
      <div className="grid gap-3">
        {loading ? (
          <div className="text-center py-8">Memuat…</div>
        ) : escalatedTasks.length === 0 ? (
          <div className="text-center py-8 text-[#3C3C43]">
            <CheckCircle size={48} className="mx-auto mb-2 text-green-400" />
            <p>Tidak ada tugas yang dieskalasi</p>
            <p className="text-xs mt-1">Semua tugas berjalan lancar!</p>
          </div>
        ) : (
          escalatedTasks.map((task) => (
            <div
              key={task.id}
              data-testid={`escalated-task-${task.id}`}
              className="bg-white/90 backdrop-blur-xl border-2 border-red-200 rounded-2xl p-4 shadow-sm"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    {getTaskTypeBadge(task.task_type)}
                    <span className="text-sm font-bold text-[#007AFF]">
                      {task.task_type === "inbound" ? task.po_number : task.order_number}
                    </span>
                  </div>
                  <p className="text-xs text-[#3C3C43]">{task.sku} - {task.product_name}</p>
                  {task.task_type === "inbound" && (
                    <p className="text-xs text-[#3C3C43] mt-1">Gudang: {task.warehouse_name}</p>
                  )}
                  {task.task_type === "outbound" && (
                    <p className="text-xs text-[#3C3C43] mt-1">
                      Pelanggan: {task.customer_name} | Warehouse: {task.warehouse_name}
                    </p>
                  )}
                </div>
                <span className="bg-red-100 text-red-700 text-xs font-semibold px-3 py-1 rounded-full">
                  ESCALATED
                </span>
              </div>

              {/* Qty Info */}
              <div className="bg-[#FFF3CD] border border-[#FFC107] rounded-lg p-3 mb-3">
                <p className="text-sm font-semibold text-[#856404] mb-1">Qty Issue:</p>
                {task.task_type === "inbound" ? (
                  <p className="text-sm text-[#856404]">
                    Expected: {formatQty(task.expected_qty)} {task.unit} | Received: {formatQty(task.received_qty || 0)} {task.unit}
                  </p>
                ) : (
                  <p className="text-sm text-[#856404]">
                    Expected: {formatQty(task.quantity)} {task.unit} | Picked: {formatQty(task.picked_qty || 0)} {task.unit}
                  </p>
                )}
              </div>

              {/* Escalation Info */}
              {task.escalation && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-3 text-sm">
                  <p className="font-semibold text-red-700 mb-1">Reason:</p>
                  <p className="text-red-600">{task.escalation.reason}</p>
                  <p className="text-[#3C3C43] text-xs mt-2">
                    Escalated by: {task.escalation.escalated_by} | {new Date(task.escalation.escalated_at).toLocaleString('id-ID')}
                  </p>
                </div>
              )}

              {/* Action Button */}
              <button
                data-testid={`resolve-task-${task.id}`}
                onClick={() => {
                  setSelectedTask(task);
                  setResolveError("");
                  setShowResolveModal(true);
                }}
                className="w-full bg-[#007AFF] hover:bg-[#0056B3] text-white rounded-full px-4 py-2 text-sm font-medium flex items-center justify-center gap-2"
              >
                <Eye size={14} />
                Review & Resolve
              </button>
            </div>
          ))
        )}
      </div>

      {/* Resolve Modal */}
      {showResolveModal && selectedTask && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" {...overlayDismiss(() => {
            setShowResolveModal(false);
            setSelectedTask(null);
            setResolveError("");
            setResolveData({ adjusted_qty: null, resolution_notes: "" });
          })}
        >
          <div
            className="bg-white/90 backdrop-blur-2xl border border-white/60 rounded-2xl w-full max-w-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">Resolve Escalation</h3>
                <button onClick={() => {
                  setShowResolveModal(false);
                  setSelectedTask(null);
                  setResolveData({ adjusted_qty: null, resolution_notes: "" });
                }}>
                  <X size={20} />
                </button>
              </div>

              {/* Task Info */}
              <div className="bg-[#F2F2F7] rounded-lg p-3 mb-4">
                <div className="flex items-center gap-2 mb-2">
                  {getTaskTypeBadge(selectedTask.task_type)}
                  <span className="text-sm font-bold">
                    {selectedTask.task_type === "inbound" ? selectedTask.po_number : selectedTask.order_number}
                  </span>
                </div>
                <p className="text-sm">{selectedTask.sku} - {selectedTask.product_name}</p>
                <p className="text-xs text-[#3C3C43] mt-1">Gudang: {selectedTask.warehouse_name}</p>
              </div>

              {/* Qty Mismatch */}
              <div className="bg-[#FFF3CD] border border-[#FFC107] rounded-lg p-3 mb-4">
                <p className="text-sm font-semibold text-[#856404]">Qty Status:</p>
                {selectedTask.task_type === "inbound" ? (
                  <div className="text-sm text-[#856404] mt-1">
                    <p>Expected: <strong>{formatQty(selectedTask.expected_qty)} {selectedTask.unit}</strong></p>
                    <p>Received: <strong>{formatQty(selectedTask.received_qty || 0)} {selectedTask.unit}</strong></p>
                    <p className="text-red-600 font-semibold mt-1">
                      Difference: {formatQty((selectedTask.expected_qty - (selectedTask.received_qty || 0)))} {selectedTask.unit}
                    </p>
                  </div>
                ) : (
                  <div className="text-sm text-[#856404] mt-1">
                    <p>Expected: <strong>{formatQty(selectedTask.quantity)} {selectedTask.unit}</strong></p>
                    <p>Sudah Diambil: <strong>{formatQty(selectedTask.picked_qty || 0)} {selectedTask.unit}</strong></p>
                    <p className="text-red-600 font-semibold mt-1">
                      Difference: {formatQty((selectedTask.quantity - (selectedTask.picked_qty || 0)))} {selectedTask.unit}
                    </p>
                  </div>
                )}
              </div>

              {/* Escalation Reason */}
              {selectedTask.escalation && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
                  <p className="text-sm font-semibold text-red-700">Escalation Reason:</p>
                  <p className="text-sm text-red-600 mt-1">{selectedTask.escalation.reason}</p>
                  <p className="text-xs text-[#3C3C43] mt-2">
                    By: {selectedTask.escalation.escalated_by} on {new Date(selectedTask.escalation.escalated_at).toLocaleString('id-ID')}
                  </p>
                </div>
              )}

              {/* Resolve Form */}
              <div className="space-y-3 mb-4">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Adjusted Qty (opsional - kosongkan jika tidak adjust)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={resolveData.adjusted_qty || ""}
                    onChange={(e) => setResolveData({ ...resolveData, adjusted_qty: e.target.value ? parseFloat(e.target.value) : null })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    placeholder={`Current: ${selectedTask.task_type === "inbound" ? selectedTask.expected_qty : selectedTask.quantity}`}
                  />
                  <p className="text-xs text-[#3C3C43] mt-1">
                    Adjust qty jika setelah investigasi memang ada perubahan legitimate (shortage, damage, etc)
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">
                    Catatan Penyelesaian * (wajib)
                  </label>
                  <textarea
                    value={resolveData.resolution_notes}
                    onChange={(e) => setResolveData({ ...resolveData, resolution_notes: e.target.value })}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    rows="4"
                    placeholder="Jelaskan hasil investigasi dan action yang diambil..."
                  />
                  <p className="text-xs text-[#3C3C43] mt-1">
                    Contoh: "Konfirmasi dengan supplier, barang shortage 10m. Qty disesuaikan ke actual received."
                  </p>
                </div>
              </div>

              {/* Actions */}
              <ErrorNotice message={resolveError} onDismiss={() => setResolveError("")} testId="escalation-resolve-error" />
              <div className="flex gap-2">
                <button
                  onClick={handleResolve}
                  data-testid="escalation-resolve-submit"
                  className="flex-1 bg-[#34C759] hover:bg-[#28A745] text-white rounded-full px-4 py-2 font-medium flex items-center justify-center gap-2"
                >
                  <CheckCircle size={14} />
                  Selesaikan & Lanjutkan Tugas
                </button>
                <button
                  onClick={() => {
                    setShowResolveModal(false);
                    setSelectedTask(null);
                    setResolveError("");
                    setResolveData({ adjusted_qty: null, resolution_notes: "" });
                  }}
                  className="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-full px-4 py-2 font-medium"
                >
                  Batal
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
