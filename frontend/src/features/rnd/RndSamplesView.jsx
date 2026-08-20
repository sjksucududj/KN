/**
 * RndSamplesView (FASE F · PS-12/PS-18) — **Permintaan Sample (Labdip / Proofing)**.
 * Antrean permintaan + ringkasan SLA; detail per permintaan menampilkan timeline
 * round `rnd 1 → n` per supplier beserta bukti & penilaiannya.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Beaker, Plus, RefreshCw, Search } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import LineFilter from "../../components/LineFilter";   // FASE L
import EntityBadge from "../../components/EntityBadge";
import { formatCurrency } from "../../utils/formatters";
import SampleFormModal from "./SampleFormModal";
import SampleDetailPanel from "./SampleDetailPanel";
import { listSamples } from "./rndApi";
import { errMsg, SAMPLE_STATUS_META, SAMPLE_TYPE_LABEL } from "./rndMeta";
import DetailModal from "../../components/DetailModal";

const TYPE_FILTERS = [
  { key: "", label: "Semua" },
  { key: "labdip", label: "Labdip" },
  { key: "proofing", label: "Proofing" },
  { key: "bulk_sample", label: "Bulk sample" },
];

export default function RndSamplesView({ currentUser, selectedEntity, focus, onFocusConsumed }) {
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [lineFilter, setLineFilter] = useState("");   // FASE L
  const [showForm, setShowForm] = useState(false);
  const [openId, setOpenId] = useState("");
  // Deep-link (event `kn-open-rnd`): prefill form dari Pustaka Warna / kartu desain,
  // atau buka permintaan tertentu dari nomornya (tautan "asal harga" di kontrak).
  const [prefill, setPrefill] = useState(null);
  const [pendingNumber, setPendingNumber] = useState("");

  const role = currentUser?.role;
  const canCreate = ["admin", "manager", "sales"].includes(role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 300 };
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      if (type) params.sample_type = type;
      if (lineFilter) params.line = lineFilter;          // FASE L
      const res = await listSamples(params);
      setRows(res?.items || []);
      setStats(res?.stats || {});
      setError("");
    } catch (e) {
      setError(errMsg(e, "Gagal memuat permintaan sample."));
    } finally { setLoading(false); }
  }, [selectedEntity, type, lineFilter]);
  useEffect(() => { load(); }, [load]);

  // ── Deep-link masuk ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!focus?.nonce) return;
    if (focus.sampleId) setOpenId(focus.sampleId);
    else if (focus.sampleNumber) setPendingNumber(focus.sampleNumber);
    if (focus.colorId || focus.designId) {
      setPrefill({
        color_id: focus.colorId || "",
        design_id: focus.designId || "",
        sample_type: focus.designId ? "proofing" : "labdip",
        source_label: focus.colorLabel || focus.designLabel || "",
      });
      setShowForm(true);
    }
    onFocusConsumed?.();
    // Hanya `nonce` yang jadi pemicu — deep-link ke objek sama 2x tetap bekerja.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce]);

  // Nomor permintaan → id (dipakai tautan "asal harga" pada layar kontrak).
  useEffect(() => {
    if (!pendingNumber || rows.length === 0) return;
    const hit = rows.find((r) => r.number === pendingNumber);
    if (hit) { setOpenId(hit.id); setPendingNumber(""); }
  }, [pendingNumber, rows]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((r) => [r.number, r.title, r.spec_number, r.color_target?.name,
      r.design_code, ...(r.participants || []).map((p) => p.supplier_name)]
      .some((v) => (v || "").toLowerCase().includes(term)));
  }, [rows, q]);

  return (
    <div data-testid="rnd-samples-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
        testId="rnd-samples-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Beaker size={16} className="text-[#0058CC]" />
            <h2 data-testid="rnd-samples-title">Permintaan Sample (Labdip / Proofing)</h2>
          </div>
          <div className="flex items-center gap-2">
            <button className="secondary-button" onClick={load} data-testid="rnd-samples-refresh">
              <RefreshCw size={13} /> Muat ulang
            </button>
            {canCreate && (
              <button className="primary-button" data-testid="rnd-sample-create-button"
                onClick={() => setShowForm(true)}>
                <Plus size={13} /> Permintaan Baru
              </button>
            )}
          </div>
        </div>
        <div className="section-body space-y-2.5">
          {pendingNumber && (
            <div className="rounded-lg bg-[#FFF6E5] px-3 py-2 text-[11.5px] text-[#8C4A00]"
              data-testid="rnd-samples-pending-number">
              Mencari permintaan <b>{pendingNumber}</b>… Bila tidak ditemukan, permintaan itu
              mungkin milik entitas (PT) lain — ganti entitas di pemilih kanan atas.
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 md:grid-cols-6" data-testid="rnd-samples-stats">
            <Kpi label="Total permintaan" value={String(stats.total ?? 0)} />
            <Kpi label="Dikerjakan" value={String(stats.in_progress ?? 0)} tone="#B26A00" />
            <Kpi label="Ada yang ACC" value={String(stats.assessed ?? 0)} tone="#0058CC" />
            <Kpi label="Sudah diputus" value={String(stats.decided ?? 0)} tone="#1B7F4B" />
            <Kpi label="Round terlambat" value={String(stats.overdue_rounds ?? 0)} tone="#C0392B" />
            <Kpi label="Biaya sample" value={formatCurrency(stats.cost_total || 0)} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative max-w-sm flex-1">
              <Search size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="rnd-samples-search" value={q}
                onChange={(e) => setQ(e.target.value)} className="field !pl-8"
                placeholder="Cari nomor / judul / supplier / warna…" />
            </div>
            <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="rnd-samples"
                        allowed={currentUser?.allowed_line_codes} testId="rnd-samples-line-filter" />
            <div className="flex flex-wrap gap-1.5" data-testid="rnd-samples-filters">
              {TYPE_FILTERS.map((f) => (
                <button key={f.key} data-testid={`rnd-samples-filter-${f.key || "all"}`}
                  onClick={() => setType(f.key)}
                  className={`rounded-full border px-3 py-1 text-[11px] font-medium ${type === f.key
                    ? "border-[#0058CC] bg-[#0058CC] text-white"
                    : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#0058CC]"}`}>
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="grid grid-cols-[125px_1.5fr_120px_1.2fr_110px_130px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
          <span>No. Permintaan</span><span>Judul / spesifikasi</span><span>Jenis</span>
          <span>Supplier & round</span><span>Biaya</span>
          <span className="text-right">Status</span>
        </div>
        {loading ? (
          <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat permintaan…</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#6B6B73]"
            data-testid="rnd-samples-empty">
            <Beaker className="mx-auto mb-2 text-gray-300" size={28} />
            <p>Belum ada permintaan sample. Kirim labdip/proofing ke beberapa supplier
              sekaligus agar hasilnya bisa dibandingkan sebelum harga dikunci.</p>
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F2] max-h-[620px] overflow-y-auto">
            {filtered.map((s) => {
              const meta = SAMPLE_STATUS_META[s.status] || SAMPLE_STATUS_META.draft;
              const overdue = (s.rounds || []).some((r) => r.overdue);
              return (
                <div key={s.id} data-testid={`rnd-sample-row-${s.id}`}
                  className="grid grid-cols-[125px_1.5fr_120px_1.2fr_110px_130px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <button className="text-left text-[11.5px] font-bold text-[#0058CC]"
                    data-testid={`rnd-sample-open-${s.id}`} onClick={() => setOpenId(s.id)}>
                    {s.number}
                  </button>
                  <div className="min-w-0">
                    <p className="truncate text-[12px] font-semibold">{s.title}</p>
                    <p className="truncate text-[10.5px] text-[#6B6B73] flex items-center gap-1">
                      <EntityBadge entityId={s.entity_id} />
                      {s.spec_number || "tanpa spesifikasi"}
                      {s.design_code ? ` · ${s.design_code}` : ""}
                    </p>
                  </div>
                  <span className="text-[11px]">
                    {SAMPLE_TYPE_LABEL[s.sample_type] || s.sample_type}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-[11.5px]">
                      {(s.participants || []).map((p) => p.supplier_name).join(", ") || "—"}
                    </p>
                    <p className="text-[10px] text-[#6B6B73]">
                      {(s.rounds || []).length} round
                      {overdue && <span className="ml-1 font-bold text-[#C0392B]">· terlambat</span>}
                    </p>
                  </div>
                  <span className="text-[11.5px] tabular-nums">
                    {formatCurrency(s.cost_total || 0)}
                  </span>
                  <div className="flex items-center justify-end">
                    <span className={`status-pill ${meta.cls}`}
                      data-testid={`rnd-sample-status-${s.id}`}>{meta.label}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showForm && (
        <SampleFormModal selectedEntity={selectedEntity} prefill={prefill}
          onClose={() => { setShowForm(false); setPrefill(null); }}
          onSaved={(created) => {
            setShowForm(false); setPrefill(null); load(); setOpenId(created?.id || "");
          }} />
      )}
      {openId && (
        <DetailModal onClose={() => setOpenId("")}
          label="Rincian sample" testId="sample-detail-modal">
          <SampleDetailPanel sampleId={openId} currentUser={currentUser}
            onClose={() => setOpenId("")} onChanged={load} />
        </DetailModal>
      )}
    </div>
  );
}

function Kpi({ label, value, tone = "#1C1C1E" }) {
  return (
    <div className="rounded-lg border border-[#EFF0F2] bg-[#FAFBFC] p-2">
      <p className="text-[9.5px] font-bold uppercase text-[#8E8E93]">{label}</p>
      <p className="text-[13px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
    </div>
  );
}
