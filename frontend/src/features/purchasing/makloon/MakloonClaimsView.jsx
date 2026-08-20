/**
 * MakloonClaimsView (FASE D · PS-11 · D-09) — KOTAK MASUK KLAIM SELISIH MAKLOON.
 * Manajer/admin memutuskan tindakan (potong bon / ganti rugi / terima) di satu layar,
 * plus skor mitra (rata-rata selisih & nilai klaim) untuk evaluasi kemitraan.
 */
import { useCallback, useEffect, useState } from "react";
import { Award, RefreshCw, Scale, Search } from "lucide-react";
import axios, { API } from "../../../services/apiClient";
import EntityBadge from "../../../components/EntityBadge";
import ErrorNotice from "../../../components/ErrorNotice";
import { formatCurrency, formatQty } from "../../../utils/formatters";
import MakloonClaimPanel from "./MakloonClaimPanel";
import { claimStats, CLAIM_STATUS_META, listClaims, partnerScorecard } from "./makloonApi";

const FILTERS = [
  { key: "", label: "Semua" },
  { key: "open", label: "Selisih Terbuka" },
  { key: "pending_approval", label: "Menunggu Persetujuan" },
  { key: "approved", label: "Disetujui" },
  { key: "rejected", label: "Ditolak" },
];

export default function MakloonClaimsView({ currentUser, selectedEntity }) {
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState({});
  const [score, setScore] = useState([]);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      const [c, s, sc] = await Promise.all([
        listClaims({ ...params, ...(status ? { status } : {}) }),
        claimStats(params).catch(() => ({})),
        partnerScorecard(params).catch(() => []),
      ]);
      setRows(Array.isArray(c) ? c : []);
      setStats(s || {});
      setScore(Array.isArray(sc) ? sc : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat daftar klaim makloon.");
    } finally {
      setLoading(false);
    }
  }, [selectedEntity, status]);
  useEffect(() => { load(); }, [load]);

  const filtered = rows.filter((r) => {
    const term = q.trim().toLowerCase();
    if (!term) return true;
    return [r.mko_number, r.makloon_name, r.output_name].some((v) => (v || "").toLowerCase().includes(term));
  });

  return (
    <div data-testid="makloon-claims-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")} testId="claims-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Scale size={16} className="text-[#0058CC]" />
            <h2 data-testid="makloon-claims-title">Klaim Selisih Makloon</h2>
          </div>
          <button className="secondary-button" onClick={load} data-testid="claims-refresh">
            <RefreshCw size={13} /> Muat ulang
          </button>
        </div>
        <div className="section-body space-y-2.5">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="claims-stats">
            <Kpi label="Total klaim" value={String(stats.total ?? 0)} />
            <Kpi label="Selisih terbuka" value={String(stats.open ?? 0)} tone="#B26A00" />
            <Kpi label="Menunggu persetujuan" value={String(stats.pending_approval ?? 0)} tone="#0058CC" />
            <Kpi label="Disetujui" value={String(stats.approved ?? 0)} tone="#1B7F4B" />
            <Kpi label="Nilai disetujui" value={formatCurrency(stats.approved_amount || 0)} tone="#1B7F4B" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative max-w-sm flex-1">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="claims-search" value={q} onChange={(e) => setQ(e.target.value)}
                className="field !pl-8" placeholder="Cari no. pesanan / mitra / produk…" />
            </div>
            <div className="flex flex-wrap gap-1.5" data-testid="claims-filters">
              {FILTERS.map((f) => (
                <button key={f.key} data-testid={`claims-filter-${f.key || "all"}`} onClick={() => setStatus(f.key)}
                  className={`rounded-full border px-3 py-1 text-[11px] font-medium ${status === f.key ? "border-[#0058CC] bg-[#0058CC] text-white" : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="section-card mb-3">
        <div className="section-head"><h3 className="text-[12.5px] font-bold">Daftar klaim</h3></div>
        <div className="section-body space-y-2.5">
          {loading ? (
            <p className="py-8 text-center text-[12px] text-[#6B6B73]">Memuat klaim…</p>
          ) : filtered.length === 0 ? (
            <p className="py-8 text-center text-[12px] text-[#6B6B73]" data-testid="claims-empty">
              Tidak ada klaim pada filter ini — selisih hasil makloon masih dalam toleransi kontrak.
            </p>
          ) : filtered.map((r) => {
            const meta = CLAIM_STATUS_META[r.claim?.status] || CLAIM_STATUS_META.none;
            return (
              <div key={`${r.mko_id}-${r.step_seq}`} className="rounded-lg border border-[#EFF0F2] p-3"
                data-testid={`claim-row-${r.mko_id}-${r.step_seq}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold">
                      <span className="text-[#0058CC]">{r.mko_number}</span> · langkah {r.step_seq} · {r.process_type}
                    </p>
                    <p className="text-[10.5px] text-[#6B6B73] flex items-center gap-1">
                      <EntityBadge entityId={r.entity_id} /> {r.makloon_name} · {r.output_name}
                      {" "}· hasil {formatQty(r.actual_output_qty)} / estimasi {formatQty(r.expected_output_qty)} {r.output_unit}
                      {r.contract_number ? ` · kontrak ${r.contract_number}` : ""}
                    </p>
                  </div>
                  <span className={`status-pill ${meta.cls}`}>{meta.label}</span>
                </div>
                <MakloonClaimPanel mkoId={r.mko_id} step={{ seq: r.step_seq, claim: r.claim, variance: { ...r.claim, expected_qty: r.expected_output_qty, actual_qty: r.actual_output_qty, unit: r.output_unit } }}
                  currentUser={currentUser} onDone={load} onError={setError} />
              </div>
            );
          })}
        </div>
      </div>

      <div className="section-card">
        <div className="section-head">
          <h3 className="flex items-center gap-2 text-[12.5px] font-bold"><Award size={14} className="text-[#0058CC]" /> Skor Mitra Makloon</h3>
        </div>
        <div className="section-body">
          {score.length === 0 ? (
            <p className="py-6 text-center text-[12px] text-[#6B6B73]" data-testid="scorecard-empty">
              Belum ada penerimaan makloon untuk dinilai.
            </p>
          ) : (
            <table className="w-full text-[11.5px]" data-testid="partner-scorecard">
              <thead>
                <tr className="text-left text-[10px] uppercase text-[#6B6B73]">
                  <th className="py-1">Mitra</th><th className="text-right">Langkah selesai</th>
                  <th className="text-right">Rata-rata selisih</th><th className="text-right">Sesuai target</th>
                  <th className="text-right">Klaim</th><th className="text-right">Nilai klaim</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EFF0F2]">
                {score.map((s) => (
                  <tr key={s.makloon_id} data-testid={`scorecard-row-${s.makloon_id}`}>
                    <td className="py-1.5 font-medium">{s.makloon_name || s.makloon_id}</td>
                    <td className="text-right tabular-nums">{s.steps}</td>
                    <td className={`text-right tabular-nums ${(s.avg_variance_pct ?? 0) < 0 ? "text-[#C0392B]" : "text-[#1B7F4B]"}`}>
                      {s.avg_variance_pct ?? "—"}%
                    </td>
                    <td className="text-right tabular-nums">{s.on_target_pct ?? "—"}%</td>
                    <td className="text-right tabular-nums">{s.claims}</td>
                    <td className="text-right tabular-nums">{formatCurrency(s.claim_amount || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone = "#1C1C1E" }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[14px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
    </div>
  );
}
