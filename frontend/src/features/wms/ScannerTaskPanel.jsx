import { useEffect, useState, useRef, useCallback } from "react";
import { Camera, CheckCircle2, Plus, ScanLine, Truck, VideoOff, ZapOff } from "lucide-react";
import { StatusPill } from "../../components/CoreWidgets";

export default function ScannerTaskPanel({ tasks, products, warehouses, orders, onCreateInboundTask, onCreateOutboundTasks, onScanTask, onAdvanceTask }) {
  const [taskId, setTaskId] = useState("");
  const [scanType, setScanType] = useState("sku");
  const [scanValue, setScanValue] = useState("");
  const [scanQueue, setScanQueue] = useState([]);
  const [scanMode, setScanMode] = useState("review");
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [cameraMessage, setCameraMessage] = useState("Kamera belum aktif");
  const [lastScanned, setLastScanned] = useState("");
  const [inbound, setInbound] = useState({ product_id: "prod_batik_mega", quantity: 5, unit: "meter", warehouse_id: "wh_jakarta", bin_id: "bin_jkt_a1_01", batch: "BTK-INB-NEW", lot: "LOT-INB-01", roll_id: "ROLL-INB-001" });
  const videoRef = useRef(null);
  const readerRef = useRef(null);
  const scanCooldownRef = useRef(false);

  const selectedTask = tasks.find((task) => task.id === taskId) || tasks[0];
  const terminalTask = ["done", "dispatched", "cancelled", "completed"].includes(selectedTask?.status);

  useEffect(() => {
    if (!taskId && tasks[0]) setTaskId(tasks[0].id);
  }, [tasks, taskId]);

  // Cleanup camera on unmount
  useEffect(() => {
    return () => { if (readerRef.current) { try { readerRef.current.reset(); } catch (_) {} readerRef.current = null; } };
  }, []);

  const stopCamera = useCallback(() => {
    if (readerRef.current) {
      try { readerRef.current.reset(); } catch (_) {}
      readerRef.current = null;
    }
    setCameraActive(false);
    setCameraMessage("Kamera dimatikan");
  }, []);

  const startCamera = async () => {
    try {
      // Import @zxing/browser dynamically
      const { BrowserMultiFormatReader } = await import("@zxing/browser");
      if (readerRef.current) {
        try { readerRef.current.reset(); } catch (_) {}
        readerRef.current = null;
      }
      const videoInputDevices = await BrowserMultiFormatReader.listVideoInputDevices();
      if (!videoInputDevices || videoInputDevices.length === 0) {
        setCameraError("Tidak ada kamera ditemukan. Gunakan input manual.");
        setCameraMessage("Tidak ada kamera ditemukan. Gunakan input manual.");
        return;
      }
      readerRef.current = new BrowserMultiFormatReader();
      setCameraActive(true);
      setCameraMessage("Kamera aktif — arahkan ke barcode/QR code");
      setCameraError("");
      const deviceId = videoInputDevices[videoInputDevices.length - 1].deviceId;
      await readerRef.current.decodeFromVideoDevice(deviceId, videoRef.current, (result, err) => {
        if (result) {
          const decoded = result.getText();
          // Cooldown 2 seconds between scans to prevent duplicates
          if (!scanCooldownRef.current && decoded !== lastScanned) {
            scanCooldownRef.current = true;
            setLastScanned(decoded);
            setScanValue(decoded);
            setCameraMessage(`Scan berhasil: ${decoded}`);
            // Auto-submit if in auto mode
            if (scanMode === "auto" && selectedTask && !terminalTask) {
              handleAutoScan(decoded);
            }
            setTimeout(() => { scanCooldownRef.current = false; }, 2000);
          }
        }
      });
    } catch (err) {
      const msg = err?.message || "Kamera tidak bisa diakses";
      setCameraError(msg);
      setCameraMessage(`Error: ${msg}`);
      setCameraActive(false);
      readerRef.current = null;
    }
  };

  const handleAutoScan = async (value) => {
    if (!selectedTask || !value) return;
    const ok = await onScanTask(selectedTask.id, scanType, value);
    const entry = {
      id: `${Date.now()}`, task_id: selectedTask.id, scan_type: scanType, scan_value: value,
      status: ok ? "submitted" : "failed", timestamp: new Date().toISOString()
    };
    setScanQueue((current) => [entry, ...current].slice(0, 12));
  };

  const submitQueuedScan = async () => {
    if (!selectedTask || !scanValue) return;
    const entry = {
      id: `${Date.now()}`, task_id: selectedTask.id, scan_type: scanType, scan_value: scanValue,
      status: scanMode === "review" ? "pending_review" : "submitting",
      timestamp: new Date().toISOString()
    };
    if (terminalTask) {
      setScanQueue((current) => [{ ...entry, status: "blocked_terminal" }, ...current].slice(0, 12));
      setScanValue("");
      return;
    }
    setScanQueue((current) => [entry, ...current].slice(0, 12));
    if (scanMode === "auto") {
      const ok = await onScanTask(selectedTask.id, scanType, scanValue);
      setScanQueue((current) => current.map((item) => item.id === entry.id ? { ...item, status: ok ? "submitted" : "failed" } : item));
    }
    setScanValue("");
  };

  const approveQueuedScan = async (entry) => {
    setScanQueue((current) => current.map((item) => item.id === entry.id ? { ...item, status: "submitting" } : item));
    const ok = await onScanTask(entry.task_id, entry.scan_type, entry.scan_value);
    setScanQueue((current) => current.map((item) => item.id === entry.id ? { ...item, status: ok ? "submitted" : "failed" } : item));
  };

  return (
    <section data-testid="scanner-task-panel" className="section-card">
      <div className="section-head">
        <div className="flex items-center gap-3 min-w-0">
          <span className="kicker">Scanner WMS</span>
          <h2>Barang Masuk · Barang Keluar · Pengambilan · Pengemasan · Pengiriman</h2>
        </div>
      </div>
      <div className="section-body">
        <div className="grid gap-3 lg:grid-cols-[.9fr_1.1fr]">
          {/* Left: Create tasks */}
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3">
            <h3 className="text-[13px] font-bold mb-2">Buat tugas barang masuk</h3>
            <div className="grid gap-2">
              <div data-testid="scanner-inbound-product-select" className="grid max-h-32 gap-1 overflow-auto">
                {products.map((p) => (
                  <button key={p.id} data-testid={`scanner-inbound-product-option-${p.id}`}
                    className={`secondary-button justify-start ${inbound.product_id === p.id ? "!bg-[#007AFF] !text-white !border-[#007AFF]" : ""}`}
                    onClick={() => setInbound({ ...inbound, product_id: p.id })}>
                    {p.sku} — {p.name}
                  </button>
                ))}
              </div>
              <div data-testid="scanner-inbound-warehouse-select" className="grid max-h-28 gap-1 overflow-auto">
                {warehouses.map((w) => (
                  <button key={w.id} data-testid={`scanner-inbound-warehouse-option-${w.id}`}
                    className={`secondary-button justify-start ${inbound.warehouse_id === w.id ? "!bg-black !text-white !border-black" : ""}`}
                    onClick={() => setInbound({ ...inbound, warehouse_id: w.id })}>
                    {w.name}
                  </button>
                ))}
              </div>
              {[["bin_id", "Bin ID"], ["batch", "Batch"], ["lot", "Lot"], ["roll_id", "Roll ID"], ["quantity", "Qty"]].map(([key, ph]) => (
                <input key={key} data-testid={`scanner-inbound-${key}-input`} className="field" placeholder={ph} value={inbound[key]}
                  onChange={(e) => setInbound({ ...inbound, [key]: key === "quantity" ? Number(e.target.value) : e.target.value })} />
              ))}
              <button data-testid="create-inbound-task-button" className="primary-button" onClick={() => onCreateInboundTask(inbound)}>
                <Plus size={14} /> Buat Tugas Barang Masuk
              </button>
            </div>
            <h3 className="mt-4 text-[13px] font-bold mb-2">Buat barang keluar dari pesanan terkonfirmasi</h3>
            <div className="grid gap-1.5">
              {(orders || []).filter((o) => o.status === "confirmed").map((order) => (
                <button key={order.id} data-testid={`create-outbound-task-${order.id}-button`}
                  className="secondary-button justify-start"
                  onClick={() => onCreateOutboundTasks(order.id)}>
                  <Truck size={14} /> {order.number}
                </button>
              ))}
            </div>
          </div>

          {/* Right: Scan panel */}
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3">
            <h3 className="text-[13px] font-bold mb-2">Scan tugas</h3>
            <div data-testid="scanner-mode-toggle" className="flex flex-wrap gap-1.5 rounded-md bg-white border border-[#EFF0F2] p-1">
              <button data-testid="scanner-review-mode-button"
                className={`secondary-button ${scanMode === "review" ? "!bg-black !text-white !border-black" : "!border-transparent"}`}
                onClick={() => setScanMode("review")}>Review</button>
              <button data-testid="scanner-auto-mode-button"
                className={`secondary-button ${scanMode === "auto" ? "!bg-[#007AFF] !text-white !border-[#007AFF]" : "!border-transparent"}`}
                onClick={() => setScanMode("auto")}>Kirim otomatis</button>
            </div>
            <div data-testid="scanner-task-select" className="mt-2 grid max-h-32 gap-1 overflow-auto">
              {tasks.map((task) => (
                <button key={task.id} data-testid={`scanner-task-option-${task.id}`}
                  className={`secondary-button justify-start ${selectedTask?.id === task.id ? "!bg-[#007AFF] !text-white !border-[#007AFF]" : ""}`}
                  onClick={() => setTaskId(task.id)}>
                  {task.flow_type} • {task.product_name} • {task.status}
                </button>
              ))}
            </div>
            {selectedTask && (
              <div data-testid="scanner-selected-task-info" className="mt-2 rounded-md border border-[#EFF0F2] bg-white p-2.5 text-[11.5px]">
                <p className="font-semibold">{selectedTask.sku} • {selectedTask.product_name}</p>
                <p className="mt-0.5 text-[#3C3C43]">Expected: SKU {selectedTask.sku}, Batch {selectedTask.batch}, Lot {selectedTask.lot}, Roll {selectedTask.roll_id}, Bin {selectedTask.bin_id}</p>
                <div className="mt-1.5"><StatusPill status={selectedTask.status} testId="scanner-selected-task-status" /></div>
                {terminalTask && <p data-testid="scanner-terminal-task-warning" className="mt-1.5 text-[10.5px] font-bold text-[#A8221A]">Tugas terminal: scan baru diblokir.</p>}
              </div>
            )}
            <div className="mt-2.5 grid gap-2 sm:grid-cols-[150px_1fr]">
              <div data-testid="scanner-scan-type-select" className="flex flex-wrap gap-1">
                {["sku", "batch", "lot", "roll", "bin"].map((type) => (
                  <button key={type} data-testid={`scanner-scan-type-${type}-button`}
                    className={`secondary-button ${scanType === type ? "!bg-black !text-white !border-black" : ""}`}
                    onClick={() => setScanType(type)}>{type}</button>
                ))}
              </div>
              <input data-testid="scanner-scan-value-input" className="field"
                placeholder="Tempel / ketik hasil scan barcode"
                value={scanValue} onChange={(e) => setScanValue(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submitQueuedScan()} />
            </div>

            {/* Camera preview */}
            {cameraActive && (
              <div className="mt-2.5 relative rounded-md overflow-hidden border border-[#EFF0F2] bg-black">
                <video ref={videoRef} className="w-full h-40 object-cover" autoPlay playsInline muted />
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="border-2 border-[#007AFF] rounded-md w-48 h-20 opacity-70" />
                </div>
                <div className="absolute bottom-1 left-1 right-1 text-center">
                  <span className="text-[10px] text-white bg-black/60 px-2 py-0.5 rounded">{cameraMessage}</span>
                </div>
              </div>
            )}

            <div className="mt-2.5 flex flex-wrap gap-2">
              <button data-testid="submit-scan-button" className="primary-button" disabled={terminalTask} onClick={submitQueuedScan}>
                <ScanLine size={14} /> Kirim Hasil Scan
              </button>
              <button data-testid="advance-wms-task-button" className="secondary-button" disabled={terminalTask} onClick={() => onAdvanceTask(selectedTask?.id)}>
                <CheckCircle2 size={14} /> Lanjutkan Tahap
              </button>
              {!cameraActive ? (
                <button data-testid="start-camera-scan-button" className="secondary-button" onClick={startCamera}>
                  <Camera size={14} /> Camera Scan
                </button>
              ) : (
                <button data-testid="stop-camera-scan-button" className="secondary-button !border-red-300 !text-red-700" onClick={stopCamera}>
                  <VideoOff size={14} /> Stop Kamera
                </button>
              )}
            </div>
            {cameraError && <p className="mt-1 text-[11px] text-red-600">{cameraError}</p>}
            {!cameraActive && <p data-testid="camera-scan-message" className="mt-1.5 text-[11.5px] text-[#3C3C43]">{cameraMessage}</p>}

            {lastScanned && (
              <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-green-700 bg-green-50 border border-green-200 rounded px-2 py-1">
                <CheckCircle2 size={12} /> Scan terakhir: <span className="font-bold">{lastScanned}</span>
              </div>
            )}

            <div data-testid="scanner-scan-queue" className="mt-2.5 rounded-md border border-[#EFF0F2] bg-white p-2.5">
              <p className="text-[11px] font-bold uppercase tracking-wide text-[#6B6B73]">Antrean Scan / Log</p>
              <div className="mt-1.5 grid max-h-36 gap-1.5 overflow-auto">
                {scanQueue.length === 0 && <p data-testid="scanner-empty-queue" className="text-[11px] text-[#3C3C43]">Belum ada scan dalam sesi ini.</p>}
                {scanQueue.map((entry) => (
                  <div data-testid={`scanner-queue-row-${entry.id}`} key={entry.id}
                    className={`flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[11px] font-semibold border ${
                      entry.status === "failed" || entry.status === "blocked_terminal"
                        ? "border-red-200 bg-red-50 text-[#A8221A]"
                        : entry.status === "submitted" ? "border-green-200 bg-green-50 text-green-800"
                        : "border-[#EFF0F2] bg-[#FAFBFC]"
                    }`}>
                    <span>{entry.scan_type} • {entry.scan_value} • {entry.status}</span>
                    {entry.status === "pending_review" && (
                      <button data-testid={`scanner-queue-submit-${entry.id}`} className="secondary-button" onClick={() => approveQueuedScan(entry)}>Kirim</button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
