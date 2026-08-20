import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Receipt, AlertTriangle, X, PhoneCall, BellRing, BellOff, CheckCircle2, Wallet } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";
import KNSelect from "../../components/KNSelect";
import ErrorNotice from "../../components/ErrorNotice";
import { can } from "../../config/roles";
import { KpiTile, fmtDate } from "./crmUtils";
import ARReceiptModal from "./ARReceiptModal";
import ARReceiptsHistory from "./ARReceiptsHistory";

/** Collection worklist + reminder (KN_17 §7 / owner 4b). */
export default function CollectionWorklist({ currentUser, selectedEntity }) {
  // FASE E-8 (E8.2) — mencatat UANG MASUK adalah wewenang peran `finance`. Dulu
  // tombolnya muncul untuk siapa pun yang bisa membuka worklist (termasuk sales),
  // lalu server menolak 403 di dalam modal — penolakan yang tak pernah dilihat
  // pengguna sebagai "bukan tugas saya", melainkan sebagai "sistemnya rusak".
  const canTakeMoney = can(currentUser?.permissions || {}, "ar_receipt", "create");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [mode, setMode] = useState("reminders"); // reminders (jatuh tempo<=60h) | overdue
  const [fu, setFu] = useState(null);
  const [marking, setMarking] = useState("");
  const [payRow, setPayRow] = useState(null);
  const [receiptRefresh, setReceiptRefresh] = useState(0);

  useEffect(() => { load(); }, [selectedEntity]); // eslint-disable-line

  async function load() {
    setLoading(true);
    try {
      const params = { days_ahead: 60 };
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const r = await axios.get(`${API}/collection-reminders`, { params });
      setRows(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat reminder penagihan.");
    } finally { setLoading(false); }
  }

  async function markReminded(row) {
    setMarking(row.order_id);
    try {
      await axios.post(`${API}/collection-reminders/mark`, {
        customer_id: row.customer_id, order_id: row.order_id,
        note: `Pengingat penagihan ${row.order_number}` });
      setNotice(`${row.customer_name} ditandai sudah diingatkan.`);
      load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal menandai reminder.");
    } finally { setMarking(""); }
  }

  const view = useMemo(() => (mode === "overdue" ? rows.filter((r) => r.overdue) : rows), [rows, mode]);
  const totals = useMemo(() => ({
    outstanding: rows.reduce((s, r) => s + Number(r.outstanding || 0), 0),
    overdue: rows.filter((r) => r.overdue).reduce((s, r) => s + Number(r.outstanding || 0), 0),
    needReminder: rows.filter((r) => (r.overdue || r.due_soon) && !r.reminded).length,
  }), [rows]);

  return (
    <div data-testid="collection-worklist">
      {notice && <div className="notice-bar success" data-testid="collection-notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="collection-error" />

      <div className="grid grid-cols-3 gap-3 mb-3">
        <KpiTile label="Total Tagihan (AR)" value={formatCurrency(totals.outstanding)} testId="collection-total" />
        <KpiTile label="Jatuh Tempo (Lewat Tempo)" value={formatCurrency(totals.overdue)} tone="text-[#C0392B]" testId="collection-overdue" />
        <KpiTile label="Perlu Diingatkan" value={totals.needReminder} sub={`${rows.length} tagihan aktif`} tone={totals.needReminder > 0 ? "text-[#B45309]" : ""} testId="collection-need-reminder" />
      </div>

      <div className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2"><Receipt size={16} className="text-[#0058CC]" /><h2 data-testid="collection-title">Reminder Penagihan</h2></div>
          <div className="tab-bar">
            <button data-testid="collection-mode-reminders" className={`tab-button ${mode === "reminders" ? "active" : ""}`} onClick={() => setMode("reminders")}>Semua aktif</button>
            <button data-testid="collection-mode-overdue" className={`tab-button ${mode === "overdue" ? "active" : ""}`} onClick={() => setMode("overdue")}>Lewat Jatuh Tempo</button>
          </div>
        </div>
        <div className="section-body">
          <div className="rounded-md border border-[#EFF0F2] overflow-hidden">
            <div className="grid grid-cols-[1.2fr_92px_120px_104px_80px_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
              <span>Pelanggan</span><span>Pesanan</span><span>Belum Lunas</span><span>Jatuh Tempo</span><span>Telat</span><span>Aksi</span>
            </div>
            {loading ? (
              <div className="py-10 text-center text-[12px] text-[#6B6B73]" data-testid="collection-loading">Memuat...</div>
            ) : view.length === 0 ? (
              <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="collection-empty">Tidak ada tagihan {mode === "overdue" ? "overdue" : "aktif"}. 🎉</div>
            ) : (
              <div className="divide-y divide-[#EFF0F2] max-h-[540px] overflow-y-auto">
                {view.map((r) => (
                  <div key={r.order_id} data-testid={`collection-row-${r.order_id}`} className="grid grid-cols-[1.2fr_92px_120px_104px_80px_120px] items-center px-3 py-2.5 text-[11.5px]">
                    <div className="min-w-0">
                      <p className="font-semibold truncate">{r.customer_name}</p>
                      <p className="text-[10px] text-[#6B6B73]">{r.sales_name}{r.reminded && <span className="ml-1 text-[#1E8E5A]">· diingatkan</span>}</p>
                    </div>
                    <span className="text-[#0058CC] font-semibold">{r.order_number}</span>
                    <span className="tabular-nums font-semibold">{formatCurrency(r.outstanding)}</span>
                    <span className="text-[#6B6B73]">{fmtDate(r.due_date)}</span>
                    <span>{r.overdue ? (
                      <span className="status-pill pill-danger inline-flex items-center gap-1"><AlertTriangle size={10} /> {r.days_late}h</span>
                    ) : <span className="status-pill pill-muted">{Math.abs(r.days_late)}h lagi</span>}</span>
                    <div className="flex gap-1">
                      {r.reminded ? (
                        <span className="icon-button text-[#1E8E5A]" title="Sudah diingatkan" data-testid={`collection-reminded-${r.order_id}`}><CheckCircle2 size={15} /></span>
                      ) : (
                        <button data-testid={`collection-mark-${r.order_id}`} disabled={marking === r.order_id}
                          onClick={() => markReminded(r)} className="icon-button text-[#B45309]" title="Tandai sudah diingatkan">
                          {marking === r.order_id ? <BellOff size={15} /> : <BellRing size={15} />}
                        </button>
                      )}
                      {canTakeMoney && (
                        <button data-testid={`collection-pay-${r.order_id}`} onClick={() => setPayRow(r)} className="icon-button text-[#1B7F4B]" title="Catat pembayaran"><Wallet size={14} /></button>
                      )}
                      <button data-testid={`collection-followup-${r.order_id}`} onClick={() => setFu(r)} className="icon-button text-[#0058CC]" title="Catat follow-up"><PhoneCall size={14} /></button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <p className="text-[10.5px] text-[#9A9BA3] mt-2">Menampilkan tagihan lewat tempo + akan jatuh tempo ≤ 60 hari. Pengingat bersifat sesuai permintaan (tanpa kirim ke luar).</p>
        </div>
      </div>

      <ARReceiptsHistory refreshKey={receiptRefresh} selectedEntity={selectedEntity} currentUser={currentUser}
        onChanged={(m) => { setNotice(m); setReceiptRefresh((k) => k + 1); load(); }} />

      {payRow && <ARReceiptModal customerId={payRow.customer_id} customerName={payRow.customer_name}
        preselectOrderId={payRow.order_id} onClose={() => setPayRow(null)}
        onDone={(m) => { setPayRow(null); setNotice(m); setReceiptRefresh((k) => k + 1); load(); }}
        onError={(m) => setError(m)} />}

      {fu && <WorklistFollowup row={fu} onClose={() => setFu(null)}
        onDone={(m) => { setFu(null); setNotice(m); load(); }} onError={(m) => setError(m)} />}
    </div>
  );
}

function WorklistFollowup({ row, onClose, onDone, onError }) {
  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState("contacted");
  const [busy, setBusy] = useState(false);
  async function go() {
    if (!note.trim()) { onError?.("Catatan wajib diisi."); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/customers/${row.customer_id}/followups`, {
        customer_id: row.customer_id, order_id: row.order_id, note, outcome });
      onDone?.(`Follow-up untuk ${row.customer_name} dicatat.`);
    } catch (e) { onError?.(e.response?.data?.detail || "Gagal menyimpan."); } finally { setBusy(false); }
  }
  return (
    <div className="modal-overlay" data-testid="worklist-followup-modal" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-card" style={{ maxWidth: 420, width: "92vw" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#EFF0F2]">
          <h2 className="text-[14px] font-bold">Follow-up: {row.customer_name}</h2>
          <button onClick={onClose} className="icon-button"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-[11px] text-[#6B6B73]">Pesanan {row.order_number} · {formatCurrency(row.outstanding)} {row.overdue ? `· telat ${row.days_late} hari` : ""}</p>
          <textarea data-testid="worklist-followup-note" value={note} onChange={(e) => setNote(e.target.value)} className="field" rows="2" placeholder="Hasil kontak penagihan..." />
          <KNSelect value={outcome} onValueChange={setOutcome} className="field" data-testid="worklist-followup-outcome"
            options={[{ value: "contacted", label: "Dihubungi" }, { value: "promised", label: "Dijanjikan bayar" },
              { value: "paid", label: "Sudah bayar" }, { value: "no_response", label: "Tak respon" }, { value: "escalated", label: "Eskalasi" }]} />
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="secondary-button">Batal</button>
            <button data-testid="worklist-followup-submit" disabled={busy} onClick={go} className="primary-button">{busy ? "..." : "Simpan"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
