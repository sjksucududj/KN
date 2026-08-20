/**
 * ARReceiptsHistory (EPIC3B) — daftar penerimaan pembayaran terbaru.
 * GET /api/ar-receipts. Refresh saat `refreshKey` berubah.
 */
import { useCallback, useEffect, useState } from "react";
import { Wallet, RefreshCw, Ban, Route } from "lucide-react";
import axios, { API } from "../../services/apiClient";
import ErrorNotice from "../../components/ErrorNotice";
import { formatCurrency } from "../../utils/formatters";
import { fmtDate } from "./crmUtils";
import DocumentActionsBar from "../documents/DocumentActionsBar";
import { openTrace } from "../documents/trace/traceDeepLink";
import { can } from "../../config/roles";
// FASE G-3 — status selisih pembayaran per kwitansi (diputus / menunggu keputusan).
import { directionMeta, varianceKindMeta } from "../finance/payments/paymentApi";
import { askReason } from "@/services/confirmService";

export default function ARReceiptsHistory({ refreshKey, selectedEntity, currentUser, onChanged }) {
  // FASE E-8 — membatalkan kwitansi (uang masuk yang sudah tercatat) tetap
  // wewenang manajer: Finance boleh MENCATAT, tidak boleh MENGHAPUS jejak uang.
  const canVoid = can(currentUser?.permissions || {}, "ar_receipt", "void");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [voiding, setVoiding] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/ar-receipts`);
      let list = Array.isArray(r.data) ? r.data : [];
      if (selectedEntity && selectedEntity !== "all") list = list.filter((x) => x.entity_id === selectedEntity);
      setRows(list.slice(0, 25));
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat riwayat pembayaran.");
    } finally { setLoading(false); }
  }, [selectedEntity]);

  useEffect(() => { load(); }, [load, refreshKey]);

  async function voidReceipt(r) {
    // Berdampak UANG: membalik pembayaran pada order + kas + deposit.
    const reason = await askReason({
      title: `Batalkan penerimaan ${r.number}?`,
      message: `Nominal ${formatCurrency(r.amount)} akan dibalik: pembayaran pada order, `
        + `catatan kas, dan deposit pelanggan dikoreksi kembali.`,
      reasonLabel: "Alasan pembatalan",
      reasonPlaceholder: "Contoh: transfer ditolak bank / salah pelanggan",
      confirmLabel: "Batalkan Penerimaan",
      danger: true,
      testId: "ar-void-confirm",
    });
    if (reason === null) return;
    setVoiding(r.id);
    try {
      await axios.post(`${API}/ar-receipts/${r.id}/void`, null, { params: { reason } });
      await load();
      onChanged?.(`Penerimaan ${r.number} dibatalkan (void).`);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal membatalkan penerimaan.");
    } finally { setVoiding(""); }
  }

  return (
    <div className="section-card mt-3" data-testid="ar-receipts-history">
      <div className="section-head">
        <div className="flex items-center gap-2"><Wallet size={15} className="text-[#1B7F4B]" /><h2>Riwayat Pembayaran (AR)</h2></div>
        <button data-testid="ar-history-refresh" className="icon-button ml-auto" onClick={load} aria-label="Refresh"><RefreshCw size={13} className={loading ? "animate-spin" : ""} /></button>
      </div>
      <div className="section-body">
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="ar-history-error" />
        {loading ? (
          <div className="py-6 text-center text-[12px] text-[#6B6B73]" data-testid="ar-history-loading">Memuat...</div>
        ) : rows.length === 0 ? (
          <div className="py-8 text-center text-[12px] text-[#6B6B73]" data-testid="ar-history-empty">Belum ada pembayaran tercatat.</div>
        ) : (
          <div className="overflow-auto rounded-md border border-[#EFF0F2]">
            <table className="w-full text-[12px]" data-testid="ar-history-table">
              <thead>
                <tr className="text-left text-[10px] font-bold uppercase text-[#8E8E93] bg-[#FAFBFC] border-b border-[#EFF0F2]">
                  <th className="px-3 py-2">No.</th><th className="px-3 py-2">Tanggal</th><th className="px-3 py-2">Pelanggan</th>
                  <th className="px-3 py-2">Metode</th><th className="px-3 py-2 text-right">Jumlah</th><th className="px-3 py-2">Pesanan</th>
                  <th className="px-3 py-2">Selisih</th>
                  <th className="px-3 py-2 text-center">Status</th><th className="px-3 py-2 text-center">Dokumen</th>{canVoid && <th className="px-3 py-2 text-center">Aksi</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const isVoid = r.status === "void";
                  return (
                  <tr key={r.id} data-testid={`ar-history-row-${r.id}`} className={`border-b border-[#F5F5F7] last:border-0 ${isVoid ? "opacity-55" : ""}`}>
                    <td className="px-3 py-2 font-mono text-[11px] text-[#0058CC]">{r.number}</td>
                    <td className="px-3 py-2 text-[#6B6B73]">{fmtDate(r.receipt_date)}</td>
                    <td className="px-3 py-2 font-semibold">{r.customer_name}</td>
                    <td className="px-3 py-2 capitalize text-[#3C3C43]">{r.method}</td>
                    <td className={`px-3 py-2 text-right tabular-nums font-semibold ${isVoid ? "line-through text-[#9A9BA3]" : "text-[#1B7F4B]"}`}>{formatCurrency(r.amount)}</td>
                    <td className="px-3 py-2 text-[11px] text-[#6B6B73]">{(r.allocations || []).map((a) => a.order_number).join(", ") || "—"}</td>
                    <td className="px-3 py-2" data-testid={`ar-history-variance-${r.id}`}>
                      {(() => {
                        const v = r.variance || {};
                        if (!v.direction || v.direction === "none") return <span className="text-[#C7C7CC]">—</span>;
                        if (v.decision_kind) {
                          const km = varianceKindMeta(v.decision_kind);
                          return (
                            <span className="rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide"
                              style={{ background: km.bg, color: km.fg }}
                              title={`${v.decision_number || ""} · ${v.reason_label || ""}`}>
                              {km.label}
                            </span>
                          );
                        }
                        const dm = directionMeta(v.direction);
                        return (
                          <span className="rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide"
                            style={{ background: dm.bg, color: dm.fg }}
                            title="Menunggu keputusan di Keuangan → Rencana Bayar & Denda → Selisih Bayar">
                            {dm.label} · perlu diputus
                          </span>
                        );
                      })()}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span data-testid={`ar-history-status-${r.id}`} className={`status-pill ${isVoid ? "pill-danger" : "pill-success"}`}>{isVoid ? "Void" : "Posted"}</span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center justify-center gap-1">
                        <DocumentActionsBar
                          docType="ar_receipt"
                          sourceId={r.id}
                          entityId={r.entity_id}
                          number={r.number}
                          label="Kwitansi (Receipt)"
                          esignable={!isVoid}
                          autoCheckSignature={false}
                          currentUser={currentUser}
                          compact
                        />
                        {/* FASE G-4 — telusuri dari kwitansi ke SO → Surat Jalan → Faktur → Retur */}
                        <button type="button" data-testid={`ar-history-trace-${r.id}`}
                          title="Buka Jejak Dokumen (rantai surat terkait)"
                          onClick={() => openTrace({ docType: "ar_receipt", docId: r.id, number: r.number })}
                          className="flex h-7 w-7 items-center justify-center rounded-md border border-[#BBD3FF] bg-[#EAF2FF] text-[#0058CC] hover:bg-[#DBEAFE]">
                          <Route size={13} />
                        </button>
                      </div>
                    </td>
                    {canVoid && (
                      <td className="px-3 py-2 text-center">
                        {!isVoid && (
                          <button data-testid={`ar-history-void-${r.id}`} className="icon-button text-[#D14343]" disabled={voiding === r.id}
                            onClick={() => voidReceipt(r)} title="Batalkan (anulir) penerimaan"><Ban size={14} /></button>
                        )}
                      </td>
                    )}
                  </tr>
                );})}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
