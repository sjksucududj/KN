/**
 * AmendmentCenterView — FASE G-1 · PUSAT AMANDEMEN.
 *
 * Satu layar untuk seluruh siklus koreksi dokumen keuangan:
 *   · antrean yang menunggu persetujuan (dengan dampak rupiah yang sudah dihitung);
 *   · riwayat koreksi yang sudah diterapkan / ditolak beserta pengusul & pemutus;
 *   · taksonomi label alasan yang bisa diubah admin tanpa deploy.
 *
 * Angka ringkasan di atas berasal dari `GET /amendments/stats/summary` — bukan
 * hitungan ulang di browser — supaya badge dan daftar tidak pernah berbeda cerita.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ExternalLink, FileEdit, RefreshCw, Scale, Search, Tag,
} from "lucide-react";
import EntityBadge from "../../../components/EntityBadge";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency } from "../../../utils/formatters";
import { openConfig } from "../../settings/config/configDeepLink";
import AmendmentDetailPanel from "./AmendmentDetailPanel";
import AmendmentReasonsPanel from "./AmendmentReasonsPanel";
import { amendmentStats, errText, listAmendments, methodMeta, statusMeta } from "./amendmentApi";

const STATUS_TABS = [
  { key: "", label: "Semua" },
  { key: "pending_approval", label: "Menunggu persetujuan" },
  { key: "applied", label: "Diterapkan" },
  { key: "auto_applied", label: "Diterapkan otomatis" },
  { key: "rejected", label: "Ditolak" },
];

function when(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" }); }
  catch { return iso; }
}

function Kpi({ label, value, tone = "#1C1C1E", testId }) {
  return (
    <div data-testid={testId} className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase tracking-wide text-[#8E8E93]">{label}</p>
      <p className="text-[14px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
    </div>
  );
}

export default function AmendmentCenterView({ currentUser, selectedEntity }) {
  const [tab, setTab] = useState("daftar");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  const canSeeReasons = ["admin", "manager"].includes(currentUser?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const [list, st] = await Promise.all([
        listAmendments({ ...params, ...(status ? { status } : {}) }),
        amendmentStats(params).catch(() => ({})),
      ]);
      setRows(list);
      setStats(st || {});
      setError("");
    } catch (e) {
      setError(errText(e, "Gagal memuat daftar amandemen."));
    } finally {
      setLoading(false);
    }
  }, [selectedEntity, status]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((r) => [r.number, r.doc_number, r.reason_label, r.proposed_by]
      .some((v) => (v || "").toLowerCase().includes(term)));
  }, [rows, q]);

  const applied = Number(stats.applied || 0) + Number(stats.auto_applied || 0);

  return (
    <div data-testid="amendment-center-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="amd-center-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex min-w-0 items-center gap-2">
            <Scale size={16} className="text-[#0058CC]" />
            <div className="min-w-0">
              <h2 data-testid="amd-center-title">Pusat Amandemen</h2>
              <p className="text-[11px] text-[#6B6B73]">
                Setiap koreksi angka pada dokumen keuangan tercatat di sini — bernomor, ber-alasan,
                ber-dampak, dan ber-penyetuju. Tidak ada edit senyap.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="amd-open-policy-config" className="secondary-button"
              onClick={() => openConfig({ group: "amandemen" })}>
              <ExternalLink size={13} /> Ambang & Aturan
            </button>
            <button data-testid="amd-center-refresh" className="secondary-button" onClick={load}>
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Muat ulang
            </button>
          </div>
        </div>
        <div className="section-body space-y-2.5">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="amd-center-stats">
            <Kpi testId="amd-kpi-total" label="Total amandemen" value={String(stats.total ?? 0)} />
            <Kpi testId="amd-kpi-pending" label="Menunggu persetujuan" value={String(stats.pending_approval ?? 0)} tone="#B26A00" />
            <Kpi testId="amd-kpi-applied" label="Sudah diterapkan" value={String(applied)} tone="#1B7F4B" />
            <Kpi testId="amd-kpi-rejected" label="Ditolak" value={String(stats.rejected ?? 0)} tone="#9B1C1C" />
            <Kpi testId="amd-kpi-impact" label="Total dampak diterapkan" value={formatCurrency(stats.impact_total || 0)} tone="#0058CC" />
          </div>

          <div className="tab-bar">
            <button data-testid="amd-tab-daftar" className={`tab-button ${tab === "daftar" ? "active" : ""}`}
              onClick={() => setTab("daftar")}>
              <FileEdit size={12} className="mr-1 inline" /> Daftar Amandemen
              <span className="tab-badge">{rows.length}</span>
            </button>
            {canSeeReasons && (
              <button data-testid="amd-tab-alasan" className={`tab-button ${tab === "alasan" ? "active" : ""}`}
                onClick={() => setTab("alasan")}>
                <Tag size={12} className="mr-1 inline" /> Label Alasan
              </button>
            )}
          </div>
        </div>
      </div>

      {tab === "alasan" ? (
        <AmendmentReasonsPanel currentUser={currentUser} />
      ) : (
        <>
          <div className="section-card mb-3">
            <div className="section-body flex flex-wrap items-center gap-2">
              <div className="relative max-w-sm flex-1">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
                <input data-testid="amd-search" value={q} onChange={(e) => setQ(e.target.value)}
                  className="field !pl-8" placeholder="Cari no. amandemen / dokumen / alasan / pengusul…" />
              </div>
              <div className="flex flex-wrap gap-1.5" data-testid="amd-status-filters">
                {STATUS_TABS.map((f) => (
                  <button key={f.key} data-testid={`amd-filter-${f.key || "all"}`} onClick={() => { setStatus(f.key); setSelected(null); }}
                    className={`rounded-full border px-3 py-1 text-[11px] font-medium ${status === f.key ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
            <section className="section-card">
              <div className="section-head">
                <h3 className="text-[12.5px] font-bold">Daftar amandemen</h3>
                <span className="text-[10.5px] text-[#8E8E93]">{filtered.length} dokumen</span>
              </div>
              <div className="overflow-hidden">
                <div className="grid grid-cols-[1fr_120px_110px] gap-2 border-b border-[#EFF0F2] bg-[#FAFBFC] px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6B6B73]">
                  <span>Amandemen</span><span className="text-right">Dampak</span><span>Status</span>
                </div>
                <div className="max-h-[620px] divide-y divide-[#EFF0F2] overflow-y-auto">
                  {loading && (
                    <p className="animate-pulse px-3 py-10 text-center text-[12px] text-[#6B6B73]">Memuat amandemen…</p>
                  )}
                  {!loading && filtered.length === 0 && (
                    <div data-testid="amd-list-empty" className="px-3 py-12 text-center text-[12px] text-[#6B6B73]">
                      <Scale className="mx-auto mb-2 text-gray-300" size={28} />
                      <p className="font-semibold text-[#3C3C43]">Tidak ada amandemen pada filter ini.</p>
                      <p>Koreksi dokumen diajukan dari panel detail Pesanan Penjualan.</p>
                    </div>
                  )}
                  {!loading && filtered.map((a) => {
                    const sm = statusMeta(a.status);
                    const mm = methodMeta(a.method);
                    const delta = Number(a.impact?.delta || 0);
                    return (
                      <div key={a.id} data-testid={`amd-row-${a.id}`} role="button" tabIndex={0}
                        onClick={() => setSelected(a.id)}
                        onKeyDown={(e) => { if (e.key === "Enter") setSelected(a.id); }}
                        className={`grid cursor-pointer grid-cols-[1fr_120px_110px] items-center gap-2 px-3 py-2.5 transition-colors hover:bg-[#FAFBFC] ${selected === a.id ? "border-l-2 border-[#007AFF] bg-[#EFF4FF]" : ""}`}>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[12px] font-bold text-[#0058CC]">{a.number}</span>
                            <EntityBadge entityId={a.entity_id} />
                            <span className="rounded px-1 py-0.5 text-[8.5px] font-bold uppercase tracking-wide"
                              style={{ background: mm.bg, color: mm.fg }}>{mm.label}</span>
                          </div>
                          <p className="truncate text-[10.5px] text-[#6B6B73]">
                            {a.doc_number} · {a.reason_label}
                          </p>
                          <p className="truncate text-[10px] text-[#9A9BA3]">
                            {a.proposed_by || "—"} · {when(a.proposed_at)}
                          </p>
                        </div>
                        <p className={`text-right text-[12px] font-bold tabular-nums ${delta < 0 ? "text-[#A8221A]" : "text-[#1B7A43]"}`}>
                          {delta < 0 ? "−" : "+"} {formatCurrency(Math.abs(delta))}
                        </p>
                        <span className="justify-self-start rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide"
                          style={{ background: sm.bg, color: sm.fg }}>{sm.label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </section>

            {selected ? (
              <AmendmentDetailPanel amdId={selected} currentUser={currentUser}
                onDecided={load} onClose={() => setSelected(null)} />
            ) : (
              <aside className="section-card flex min-h-[220px] items-center justify-center border-dashed">
                <div className="p-6 text-center">
                  <Scale size={28} className="mx-auto mb-2 text-gray-300" />
                  <p className="text-[12px] text-[#6B6B73]">Pilih amandemen untuk melihat dampak, ambang, dan memutuskan.</p>
                </div>
              </aside>
            )}
          </div>
        </>
      )}
    </div>
  );
}
