import { useEffect, useState } from "react";
import {
  Plus, ClipboardList, CheckCircle2, XCircle, ArrowRight,
  Package, AlertTriangle, Clock, RefreshCw
} from "lucide-react";
import { StatusPill } from "../../components/CoreWidgets";
import KNSelect from "../../components/KNSelect";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import DocumentActionsBar from "../documents/DocumentActionsBar";
import { entityShortFromCtx } from "../../utils/entityLabel";

const STATUS_LABELS = {
  open: "Open", submitted: "Submitted", approved: "Disetujui",
  rejected: "Ditolak"
};

const STATUS_COLORS = {
  open: "bg-blue-50 text-blue-700 border-blue-200",
  submitted: "bg-amber-50 text-amber-700 border-amber-200",
  approved: "bg-green-50 text-green-700 border-green-200",
  rejected: "bg-red-50 text-red-700 border-red-200",
};

const fmt = new Intl.NumberFormat("id-ID");

export default function CycleCount({ token, warehouses, products, userRole }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedSession, setSelectedSession] = useState(null);
  const [view, setView] = useState("list"); // list | create | detail
  const [form, setForm] = useState({ warehouse_id: "", name: "", notes: "" });
  const [addItem, setAddItem] = useState({ product_id: "", bin_id: "", notes: "" });
  const [actualQty, setActualQty] = useState({});
  const [approveReason, setApproveReason] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const loadSessions = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/cycle-count/sessions`, { headers });
      setSessions(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setErr("Gagal memuat sesi");
    } finally {
      setLoading(false);
    }
  };

  const loadSession = async (id) => {
    const res = await axios.get(`${API}/cycle-count/sessions/${id}`, { headers });
    const data = res.data;
    setSelectedSession(data);
    // Initialize actualQty from existing counted items
    const aq = {};
    (data.items || []).forEach(item => {
      if (item.actual_qty !== null && item.actual_qty !== undefined) {
        aq[item.id] = item.actual_qty;
      }
    });
    setActualQty(aq);
  };

  useEffect(() => { loadSessions(); }, []);

  const createSession = async () => {
    if (!form.warehouse_id) { setErr("Pilih gudang"); return; }
    setErr("");
    let data;
    try {
      const res = await axios.post(`${API}/cycle-count/sessions`, form, { headers });
      data = res.data;
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal membuat sesi"); return;
    }
    setMsg("Sesi cycle count berhasil dibuat");
    await loadSessions();
    await loadSession(data.id);
    setView("detail");
    setForm({ warehouse_id: "", name: "", notes: "" });
  };

  const addItemToSession = async () => {
    if (!addItem.product_id || !selectedSession) return;
    try {
      await axios.post(`${API}/cycle-count/sessions/${selectedSession.id}/items`, addItem, { headers });
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal tambah item"); return;
    }
    await loadSession(selectedSession.id);
    setAddItem({ product_id: "", bin_id: "", notes: "" });
    setMsg("Item ditambahkan");
  };

  const updateActualQty = async (itemId) => {
    if (actualQty[itemId] === undefined) return;
    try {
      await axios.patch(`${API}/cycle-count/sessions/${selectedSession.id}/items/${itemId}`,
        { actual_qty: Number(actualQty[itemId]), notes: "" }, { headers });
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal update"); return;
    }
    await loadSession(selectedSession.id);
    setMsg("Qty aktual tersimpan");
  };

  const submitSession = async () => {
    try {
      await axios.post(`${API}/cycle-count/sessions/${selectedSession.id}/submit`, null, { headers });
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal submit"); return;
    }
    await loadSession(selectedSession.id);
    await loadSessions();
    setMsg("Sesi disubmit ke manager untuk review");
  };

  const approveSession = async () => {
    try {
      await axios.post(`${API}/cycle-count/sessions/${selectedSession.id}/approve`,
        { reason: approveReason || "Disetujui sesuai hasil count" }, { headers });
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal approve"); return;
    }
    await loadSession(selectedSession.id);
    await loadSessions();
    setMsg("Cycle count disetujui — inventory telah disesuaikan");
  };

  const rejectSession = async () => {
    if (!rejectReason) { setErr("Alasan penolakan wajib diisi"); return; }
    try {
      await axios.post(`${API}/cycle-count/sessions/${selectedSession.id}/reject`,
        { reason: rejectReason }, { headers });
    } catch (e) {
      setErr(e.response?.data?.detail || "Gagal reject"); return;
    }
    await loadSession(selectedSession.id);
    await loadSessions();
    setMsg("Cycle count ditolak");
  };

  const uncountedItems = (selectedSession?.items || []).filter(i => i.status !== "counted");
  const canSubmit = selectedSession?.status === "open" &&
    (selectedSession?.items || []).length > 0 && uncountedItems.length === 0;
  const canApprove = ["admin", "manager"].includes(userRole) && selectedSession?.status === "submitted";

  return (
    <section data-testid="cycle-count-panel" className="section-card">
      <div className="section-head">
        <div className="flex items-center gap-3 min-w-0">
          <span className="kicker">Persediaan</span>
          <h2>Cycle Count / Stock Opname</h2>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { setView("create"); setErr(""); setMsg(""); }} className="primary-button" data-testid="new-cycle-count-button">
            <Plus size={13} /> Buat Sesi
          </button>
          <button onClick={() => { loadSessions(); setMsg(""); }} className="secondary-button" data-testid="refresh-cycle-count-button">
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {err && <div className="mx-4 mb-2"><ErrorNotice message={err} onRetry={loadSessions} onDismiss={() => setErr("")} testId="cycle-count-error" /></div>}
      {msg && <div className="mx-4 mb-2 rounded-md bg-green-50 border border-green-200 p-2 text-[12px] text-green-700">{msg}</div>}

      <div className="section-body">
        <div className="grid gap-3 lg:grid-cols-[280px_1fr]">
          {/* Sessions List */}
          <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-[13px] font-bold">Sesi Count</h3>
              <span className="text-[11px] text-[#6B6B73]">{sessions.length} sesi</span>
            </div>
            <div className="grid gap-1.5 max-h-80 overflow-auto">
              {sessions.length === 0 && !loading && (
                <div className="text-[12px] text-[#6B6B73] py-4 text-center">Belum ada sesi. Buat sesi baru.</div>
              )}
              {sessions.map(s => (
                <button key={s.id} data-testid={`cycle-count-session-${s.id}`}
                  className={`rounded-lg border p-2.5 text-left transition-all hover:shadow-sm ${
                    selectedSession?.id === s.id ? "border-[#007AFF] bg-white" : "border-[#EFF0F2] bg-white hover:border-[#C7C7CC]"
                  }`}
                  onClick={() => { loadSession(s.id); setView("detail"); setErr(""); setMsg(""); }}>
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] font-bold truncate">{s.name}</span>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                      STATUS_COLORS[s.status] || "bg-gray-50 text-gray-600 border-gray-200"
                    }`}>{STATUS_LABELS[s.status] || s.status}</span>
                  </div>
                  <p className="text-[11px] text-[#6B6B73] mt-0.5">{s.warehouse_name}</p>
                  <p className="text-[10.5px] text-[#8E8E93]">{(s.items || []).length} item • {s.created_at?.slice(0, 10)}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Main panel */}
          <div>
            {view === "create" && (
              <div className="rounded-md border border-[#EFF0F2] bg-white p-4">
                <h3 className="text-[14px] font-bold mb-3">Buat Sesi Stock Opname Baru</h3>
                <div className="grid gap-2 max-w-md">
                  <KNSelect
                    data-testid="cc-warehouse-select"
                    className="field"
                    value={form.warehouse_id}
                    onValueChange={v => setForm({...form, warehouse_id: v})}
                    placeholder="Pilih Gudang"
                    options={[
                      { value: "", label: "Pilih Gudang" },
                      ...warehouses.map(w => ({ value: w.id, label: `${w.name} — ${w.city}` })),
                    ]}
                  />
                  <input placeholder="Nama sesi (opsional)" value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="field" data-testid="cc-session-name-input" />
                  <textarea placeholder="Catatan (opsional)" value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} className="field" rows={2} data-testid="cc-session-notes-input" />
                  <div className="flex gap-2">
                    <button onClick={createSession} className="primary-button" data-testid="cc-create-session-button">Buat Sesi</button>
                    <button onClick={() => setView("list")} className="secondary-button">Batal</button>
                  </div>
                </div>
              </div>
            )}

            {view === "detail" && selectedSession && (
              <div className="grid gap-3">
                {/* Session header */}
                <div className="rounded-md border border-[#EFF0F2] bg-white p-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-[14px] font-bold">{selectedSession.name}</h3>
                      <p className="text-[12px] text-[#6B6B73]">{selectedSession.warehouse_name} • {selectedSession.created_by} • {selectedSession.created_at?.slice(0, 10)}</p>
                    </div>
                    <span className={`text-[11px] font-bold px-2 py-0.5 rounded border ${
                      STATUS_COLORS[selectedSession.status] || "bg-gray-50 text-gray-600 border-gray-200"
                    }`}>{STATUS_LABELS[selectedSession.status] || selectedSession.status}</span>
                  </div>
                  {selectedSession.notes && <p className="text-[12px] text-[#3C3C43] mt-1.5">{selectedSession.notes}</p>}
                  {/* Dokumen — Laporan Stock Opname (Pratinjau · Unduh PDF · Kirim WA) */}
                  <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-[#F0F1F3] pt-2.5">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-[#8E8E93]">Dokumen</span>
                    <DocumentActionsBar
                      docType="cycle_count"
                      sourceId={selectedSession.id}
                      entityId={selectedSession.entity_id}
                      number={selectedSession.number || selectedSession.name}
                      label="Laporan Stock Opname"
                      esignable={false}
                      autoCheckSignature={false}
                      currentUser={{ role: userRole }}
                    />
                  </div>
                </div>

                {/* Add item (only if open) */}
                {selectedSession.status === "open" && (
                  <div className="rounded-md border border-[#EFF0F2] bg-[#FAFBFC] p-3">
                    <h3 className="text-[13px] font-bold mb-2">Tambah Produk ke Count</h3>
                    <div className="flex gap-2 flex-wrap">
                      <KNSelect
                        data-testid="cc-add-product-select"
                        className="field flex-1 min-w-32"
                        value={addItem.product_id}
                        onValueChange={v => setAddItem({...addItem, product_id: v})}
                        placeholder="Pilih Produk"
                        options={[
                          { value: "", label: "Pilih Produk" },
                          ...products.map(p => ({ value: p.id, label: `${p.sku} — ${p.name}` })),
                        ]}
                      />
                      <input placeholder="Bin ID (opsional)" value={addItem.bin_id} onChange={e => setAddItem({...addItem, bin_id: e.target.value})} className="field w-28" />
                      <button onClick={addItemToSession} className="primary-button" data-testid="cc-add-item-button">
                        <Plus size={13} /> Tambah
                      </button>
                    </div>
                  </div>
                )}

                {/* Items table */}
                <div className="rounded-md border border-[#EFF0F2] bg-white p-3">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-[13px] font-bold">Item Count ({(selectedSession.items || []).length})</h3>
                    {uncountedItems.length > 0 && (
                      <span className="text-[11px] text-amber-600 flex items-center gap-1">
                        <AlertTriangle size={11} /> {uncountedItems.length} belum dihitung
                      </span>
                    )}
                  </div>
                  <div className="grid gap-2">
                    {(selectedSession.items || []).length === 0 && (
                      <p className="text-[12px] text-[#8E8E93] py-4 text-center">Belum ada item. Tambah produk di atas.</p>
                    )}
                    {(selectedSession.items || []).map((item) => (
                      <div key={item.id} data-testid={`cc-item-${item.id}`}
                        className={`rounded-lg border p-2.5 ${
                          item.status === "counted" ? "border-green-200 bg-green-50" : "border-[#EFF0F2] bg-[#FAFBFC]"
                        }`}>
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-[12px] font-semibold">{item.product_name}</p>
                            <p className="text-[11px] text-[#6B6B73]">{item.sku}{item.bin_id ? ` • Bin: ${item.bin_id}` : ""}{item.owner_entity_id ? ` • Pemilik: ${entityShortFromCtx(item.owner_entity_id)}` : ""}</p>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <div className="text-right">
                              <p className="text-[10.5px] text-[#8E8E93]">Expected</p>
                              <p className="text-[13px] font-bold">{fmt.format(item.expected_qty)}</p>
                            </div>
                            {selectedSession.status === "open" ? (
                              <div className="flex items-center gap-1.5">
                                <input type="number" className="field !w-20 text-right" placeholder="Actual"
                                  value={actualQty[item.id] ?? ""}
                                  onChange={e => setActualQty({...actualQty, [item.id]: e.target.value})}
                                  data-testid={`cc-actual-qty-${item.id}`} />
                                <button onClick={() => updateActualQty(item.id)} className="secondary-button"
                                  data-testid={`cc-save-qty-${item.id}`}>
                                  <CheckCircle2 size={13} />
                                </button>
                              </div>
                            ) : (
                              <div className="text-right">
                                <p className="text-[10.5px] text-[#8E8E93]">Actual</p>
                                <p className={`text-[13px] font-bold ${
                                  item.actual_qty > item.expected_qty ? "text-green-700"
                                    : item.actual_qty < item.expected_qty ? "text-red-600"
                                    : ""
                                }`}>{item.actual_qty !== null && item.actual_qty !== undefined ? fmt.format(item.actual_qty) : "—"}</p>
                              </div>
                            )}
                          </div>
                        </div>
                        {item.status === "counted" && item.actual_qty !== null && (
                          <div className={`mt-1.5 text-[11px] font-semibold ${
                            Math.abs(item.actual_qty - item.expected_qty) < 0.001 ? "text-green-700"
                              : item.actual_qty > item.expected_qty ? "text-blue-700" : "text-red-600"
                          }`}>
                            Selisih: {item.actual_qty - item.expected_qty > 0 ? "+" : ""}{fmt.format(item.actual_qty - item.expected_qty)} unit
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Discrepancies (for submitted/approved) */}
                {selectedSession.status !== "open" && (selectedSession.discrepancies || []).length > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
                    <h3 className="text-[13px] font-bold text-amber-800 mb-2">
                      Selisih ({selectedSession.discrepancies.length} item)
                    </h3>
                    <div className="grid gap-1.5">
                      {selectedSession.discrepancies.map(d => (
                        <div key={d.item_id} className="flex items-center justify-between text-[12px]">
                          <span className="font-semibold">{d.product_name} <span className="text-[#6B6B73] font-normal">{d.sku}</span></span>
                          <span className="font-bold">
                            Expected: {fmt.format(d.expected_qty)} → Actual: {fmt.format(d.actual_qty)}
                            <span className={`ml-2 ${
                              d.difference > 0 ? "text-blue-700" : "text-red-700"
                            }`}>
                              ({d.difference > 0 ? "+" : ""}{fmt.format(d.difference)})
                            </span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 flex-wrap">
                  {selectedSession.status === "open" && canSubmit && (
                    <button onClick={submitSession} className="primary-button" data-testid="cc-submit-button">
                      <ArrowRight size={13} /> Kirim ke Manajer
                    </button>
                  )}
                  {canApprove && (
                    <>
                      <input placeholder="Alasan persetujuan…" value={approveReason}
                        onChange={e => setApproveReason(e.target.value)}
                        className="field flex-1 min-w-32" data-testid="cc-approve-reason-input" />
                      <button onClick={approveSession} className="primary-button !bg-green-600 !border-green-600 hover:!bg-green-700" data-testid="cc-approve-button">
                        <CheckCircle2 size={13} /> Setujui
                      </button>
                      <input placeholder="Alasan penolakan (wajib)..." value={rejectReason}
                        onChange={e => setRejectReason(e.target.value)}
                        className="field flex-1 min-w-32" data-testid="cc-reject-reason-input" />
                      <button onClick={rejectSession} className="secondary-button !border-red-300 !text-red-700" data-testid="cc-reject-button">
                        <XCircle size={13} /> Reject
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}

            {view === "list" && sessions.length === 0 && !loading && (
              <div className="rounded-md border border-dashed border-[#C7C7CC] p-8 text-center">
                <ClipboardList size={32} className="mx-auto text-[#C7C7CC] mb-2" />
                <p className="text-[13px] text-[#6B6B73]">Belum ada sesi stock opname.</p>
                <p className="text-[12px] text-[#8E8E93]">Klik "Buat Sesi" untuk memulai stock opname.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
