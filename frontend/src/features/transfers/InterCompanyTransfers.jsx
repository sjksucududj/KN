import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import {
  ArrowLeftRight, RefreshCw, Check, X, Clock3, PackageCheck, Building2, Search,
} from "lucide-react";
import { formatQty } from "../../utils/formatters";
import ErrorNotice from "../../components/ErrorNotice";
import LineFilter from "../../components/LineFilter";   // FASE L
import QtyDual from "../../components/QtyDual";      // FASE U — dua satuan

/**
 * Transfer Antar-Entitas (Sub-fase 1.5 — Inter-Company Transfer Flow, KN_15 §7).
 * List + approve (pindah kepemilikan B→E) + reject permintaan transfer inter-company.
 */
export default function InterCompanyTransfers({ currentUser = {} }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [lineFilter, setLineFilter] = useState("");   // FASE L
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState("");
  const [rejectFor, setRejectFor] = useState("");
  const [rejectReason, setRejectReason] = useState("");

  const canApprove = ["manager", "admin"].includes((currentUser.role || "").toLowerCase());

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await axios.get(`${API}/transfers`, {
        params: { transfer_kind: "inter_entity", ...(lineFilter ? { line: lineFilter } : {}) },
      });
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat transfer antar-entitas.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [lineFilter]);

  const approve = async (id) => {
    setBusyId(id);
    try {
      await axios.post(`${API}/transfers/${id}/approve`, { approved_by: currentUser.name || "Manager" });
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal approve transfer.");
    } finally {
      setBusyId("");
    }
  };

  const reject = async (id) => {
    setBusyId(id);
    try {
      await axios.post(`${API}/transfers/${id}/reject`, {
        rejected_by: currentUser.name || "Manager",
        reason: rejectReason || "Ditolak entitas sumber",
      });
      setRejectFor("");
      setRejectReason("");
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal reject transfer.");
    } finally {
      setBusyId("");
    }
  };

  const filtered = useMemo(() => rows.filter((r) => {
    if (filter !== "all" && r.status !== filter) return false;
    const hay = `${r.code} ${r.source_entity_name} ${r.dest_entity_name} ${(r.items || []).map((i) => i.product_name).join(" ")}`.toLowerCase();
    return hay.includes(search.toLowerCase());
  }), [rows, filter, search]);

  const counts = useMemo(() => ({
    all: rows.length,
    waiting_approval: rows.filter((r) => r.status === "waiting_approval").length,
    completed: rows.filter((r) => r.status === "completed").length,
  }), [rows]);

  const FILTERS = [
    { id: "all", label: "Semua" },
    { id: "waiting_approval", label: "Menunggu" },
    { id: "completed", label: "Selesai" },
    { id: "rejected", label: "Ditolak" },
  ];

  return (
    <div data-testid="interco-transfers-view" className="grid gap-4">
      <section className="section-card">
        <div className="section-head">
          <div className="flex items-center gap-2 min-w-0">
            <ArrowLeftRight size={15} className="text-[#6B219A]" />
            <span className="kicker">Persediaan</span>
            <h2 data-testid="interco-title">Transfer Antar-Entitas</h2>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-md border border-[#E5E5EA] bg-white px-2 py-1.5 min-w-[180px]">
              <Search size={14} className="text-[#6B6B73]" />
              <input
                data-testid="interco-search"
                className="w-full bg-transparent text-[13px] outline-none"
                placeholder="Cari kode / produk..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button data-testid="interco-refresh" className="icon-button" onClick={load} aria-label="Muat ulang">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
        <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="interco-error" />
        <div className="px-4 pt-2">
          <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="interco-transfers"
                      allowed={currentUser?.allowed_line_codes} testId="interco-line-filter" />
        </div>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              data-testid={`interco-filter-${f.id}`}
              onClick={() => setFilter(f.id)}
              className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                filter === f.id ? "bg-[#1C1C1E] text-white" : "bg-[#F2F2F7] text-[#3C3C43] hover:bg-[#E5E5EA]"
              }`}
            >
              {f.label}
              {f.id === "waiting_approval" && counts.waiting_approval > 0 && (
                <span className="ml-1 rounded-full bg-[#FF9500] px-1.5 text-[9px] text-white">{counts.waiting_approval}</span>
              )}
            </button>
          ))}
          {!canApprove && (
            <span className="ml-auto text-[10px] text-[#8E8E93]">Hanya manager/admin yang dapat menyetujui.</span>
          )}
        </div>
      </section>

      {error && (
        <div data-testid="interco-error" className="rounded-md border border-[#F3C7C2] bg-[#FDF1F0] p-3 text-[12px] text-[#A8221A]">
          {error}
        </div>
      )}

      <section className="grid gap-3">
        {loading && (
          <div data-testid="interco-loading" className="section-card animate-pulse p-8 text-center text-[13px] text-[#6B6B73]">
            Memuat transfer…
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div data-testid="interco-empty" className="section-card p-10 text-center text-[13px] text-[#6B6B73]">
            Belum ada transfer antar-entitas.
          </div>
        )}
        {!loading && filtered.map((t) => (
          <article
            key={t.id}
            data-testid={`interco-card-${t.id}`}
            className="section-card p-0 overflow-hidden"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold uppercase tracking-wide text-[#6B219A]">{t.code}</span>
                <span className={`status-pill status-${t.status}`} data-testid={`interco-status-${t.id}`}>
                  {t.status === "waiting_approval" && <Clock3 size={11} />}
                  {t.status === "completed" && <PackageCheck size={11} />}
                  {t.status.replace(/_/g, " ")}
                </span>
              </div>
              <div className="flex items-center gap-2 text-[12px] font-semibold">
                <span className="flex items-center gap-1 rounded-md bg-[#FFF4E5] px-2 py-1 text-[#8C4A00]">
                  <Building2 size={12} /> {t.source_entity_name}
                </span>
                <ArrowLeftRight size={13} className="text-[#6B219A]" />
                <span className="flex items-center gap-1 rounded-md bg-[#E9F7EE] px-2 py-1 text-[#126E2C]">
                  <Building2 size={12} /> {t.dest_entity_name}
                </span>
              </div>
            </div>

            <div className="px-4 py-3">
              <table className="w-full text-[12.5px]">
                <thead>
                  <tr className="text-left text-[10px] font-bold uppercase tracking-wide text-[#8E8E93]">
                    <th className="pb-1">Produk</th>
                    <th className="pb-1 text-right">Qty</th>
                    <th className="pb-1 pl-3">Lot</th>
                  </tr>
                </thead>
                <tbody>
                  {(t.items || []).map((it, idx) => (
                    <tr key={idx} className="border-t border-[#F4F5F7]">
                      <td className="py-1.5">
                        <span className="text-[10px] font-bold uppercase text-[#0058CC]">{it.sku}</span>{" "}
                        <span className="font-medium">{it.product_name}</span>
                      </td>
                      <td className="py-1.5 text-right font-semibold tabular-nums"><QtyDual rolls={it.qty_rolls} measure={it.qty} unit={it.unit} /></td>
                      <td className="py-1.5 pl-3 text-[#6B6B73]">{(it.lots || []).join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[#8E8E93]">
                <span>Diminta: <span className="font-medium text-[#3C3C43]">{t.requested_by || "—"}</span></span>
                {t.linked_order_id && <span>SO: <span className="font-medium text-[#3C3C43]">{t.linked_order_id}</span></span>}
                {t.approved_by && <span>Disetujui: <span className="font-medium text-[#3C3C43]">{t.approved_by}</span></span>}
                {t.rejected_reason && <span className="text-[#A8221A]">Alasan tolak: {t.rejected_reason}</span>}
              </div>

              {t.status === "waiting_approval" && canApprove && (
                <div className="mt-3 border-t border-[#EFF0F2] pt-3">
                  {rejectFor === t.id ? (
                    <div className="grid gap-2">
                      <textarea
                        data-testid={`interco-reject-reason-${t.id}`}
                        className="field min-h-[56px] text-[12px]"
                        placeholder="Alasan penolakan…"
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <button
                          data-testid={`interco-reject-confirm-${t.id}`}
                          disabled={busyId === t.id}
                          onClick={() => reject(t.id)}
                          className="flex items-center gap-1 rounded-md bg-[#A8221A] px-3 py-1.5 text-[12px] font-semibold text-white disabled:opacity-50"
                        >
                          <X size={13} /> Konfirmasi Tolak
                        </button>
                        <button
                          onClick={() => { setRejectFor(""); setRejectReason(""); }}
                          className="rounded-md border border-[#E5E5EA] px-3 py-1.5 text-[12px] font-semibold text-[#3C3C43]"
                        >
                          Batal
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <button
                        data-testid={`interco-approve-${t.id}`}
                        disabled={busyId === t.id}
                        onClick={() => approve(t.id)}
                        className="flex items-center gap-1.5 rounded-md bg-[#126E2C] px-4 py-1.5 text-[12px] font-bold text-white transition hover:bg-[#0E5A24] disabled:opacity-50"
                      >
                        <Check size={14} /> {busyId === t.id ? "Memproses…" : "Approve & Pindahkan Kepemilikan"}
                      </button>
                      <button
                        data-testid={`interco-reject-${t.id}`}
                        disabled={busyId === t.id}
                        onClick={() => setRejectFor(t.id)}
                        className="flex items-center gap-1 rounded-md border border-[#E5E5EA] px-4 py-1.5 text-[12px] font-semibold text-[#A8221A] disabled:opacity-50"
                      >
                        <X size={14} /> Tolak
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
