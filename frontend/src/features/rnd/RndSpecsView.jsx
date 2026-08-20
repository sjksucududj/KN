/**
 * RndSpecsView (FASE F · PS-12) — **Spesifikasi Produk versi R&D**.
 *
 * Inilah HULU rantai: R&D menuliskan target kain (jenis, GSM, lebar, warna dari
 * pustaka, desain untuk printing) → diajukan → di-ACC → **produk lahir** dengan status
 * BELUM boleh dijual → setelah sample & kontrak beres, produk dirilis ke produksi.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { FlaskConical, Plus, RefreshCw, Search, Settings2 } from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import LineFilter from "../../components/LineFilter";   // FASE L
import EntityBadge from "../../components/EntityBadge";
import { openConfig } from "../settings/config/configDeepLink";
import SpecFormModal from "./SpecFormModal";
import SpecDetailPanel from "./SpecDetailPanel";
import { listSpecs, rndMeta } from "./rndApi";
import { errMsg, lifecycleMeta, SAMPLE_TYPE_LABEL, SPEC_STATUS_META } from "./rndMeta";
import DetailModal from "../../components/DetailModal";

const STATUS_FILTERS = [
  { key: "", label: "Semua" },
  { key: "draft", label: "Draf" },
  { key: "review", label: "Menunggu ACC" },
  { key: "approved", label: "Disetujui" },
  { key: "rejected", label: "Ditolak" },
];

export default function RndSpecsView({ currentUser, selectedEntity, focus, onFocusConsumed }) {
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState({});
  const [policy, setPolicy] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [lineFilter, setLineFilter] = useState("");   // FASE L
  const [showForm, setShowForm] = useState(false);
  const [openId, setOpenId] = useState("");

  const role = currentUser?.role;
  const canCreate = ["admin", "manager", "sales"].includes(role);
  const canManage = ["admin", "manager"].includes(role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 300 };
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      if (status) params.status = status;
      if (lineFilter) params.line = lineFilter;          // FASE L
      const [res, meta] = await Promise.all([
        listSpecs(params),
        rndMeta(selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {})
          .catch(() => ({})),
      ]);
      setRows(res?.items || []);
      setStats(res?.stats || {});
      setPolicy(meta?.policy || {});
      setError("");
    } catch (e) {
      setError(errMsg(e, "Gagal memuat spesifikasi R&D."));
    } finally {
      setLoading(false);
    }
  }, [selectedEntity, status, lineFilter]);
  useEffect(() => { load(); }, [load]);

  // Deep-link (event `kn-open-rnd`) — buka spesifikasi tertentu langsung.
  useEffect(() => {
    if (!focus?.nonce) return;
    if (focus.specId) setOpenId(focus.specId);
    onFocusConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((r) => [r.number, r.title, r.sku_hint, r.color_target?.name,
      r.color_target?.code, r.product_sku]
      .some((v) => (v || "").toLowerCase().includes(term)));
  }, [rows, q]);

  return (
    <div data-testid="rnd-specs-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
        testId="rnd-specs-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <FlaskConical size={16} className="text-[#0058CC]" />
            <h2 data-testid="rnd-specs-title">Spesifikasi Produk (R&D)</h2>
          </div>
          <div className="flex items-center gap-2">
            <button className="secondary-button" onClick={load} data-testid="rnd-specs-refresh">
              <RefreshCw size={13} /> Muat ulang
            </button>
            {canManage && (
              <button className="secondary-button" data-testid="rnd-specs-policy-button"
                title="Kebijakan R&D diatur di Pusat Pengaturan"
                onClick={() => openConfig({ group: "rnd", key: "rnd.lifecycle_enforcement" })}>
                <Settings2 size={13} /> Kebijakan R&D
              </button>
            )}
            {canCreate && (
              <button className="primary-button" data-testid="rnd-spec-create-button"
                onClick={() => setShowForm(true)}>
                <Plus size={13} /> Spesifikasi Baru
              </button>
            )}
          </div>
        </div>
        <div className="section-body space-y-2.5">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="rnd-specs-stats">
            <Kpi label="Total spesifikasi" value={String(stats.total ?? 0)} />
            <Kpi label="Draf" value={String(stats.draft ?? 0)} />
            <Kpi label="Menunggu ACC" value={String(stats.review ?? 0)} tone="#B26A00" />
            <Kpi label="Disetujui" value={String(stats.approved ?? 0)} tone="#1B7F4B" />
            <Kpi label="Ditolak" value={String(stats.rejected ?? 0)} tone="#C0392B" />
          </div>
          <p className="text-[11px] text-[#6B6B73]" data-testid="rnd-policy-note">
            Barang hasil R&D baru boleh dipesan/dijual setelah <b>dirilis ke produksi</b>.
            Ketegasan sekarang: <b>{policy.lifecycle_enforcement === "block" ? "tolak"
              : policy.lifecycle_enforcement === "warn" ? "peringatkan" : "abaikan"}</b>
            {" · "}batas iterasi sample <b>{policy.max_rounds ?? "—"}</b> round
            {" · "}target <b>{policy.round_sla_days ?? "—"}</b> hari/round.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative max-w-sm flex-1">
              <Search size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="rnd-specs-search" value={q} onChange={(e) => setQ(e.target.value)}
                className="field !pl-8" placeholder="Cari nomor / judul / SKU / warna…" />
            </div>
            <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="rnd-specs"
                        allowed={currentUser?.allowed_line_codes} testId="rnd-specs-line-filter" />
            <div className="flex flex-wrap gap-1.5" data-testid="rnd-specs-filters">
              {STATUS_FILTERS.map((f) => (
                <button key={f.key} data-testid={`rnd-specs-filter-${f.key || "all"}`}
                  onClick={() => setStatus(f.key)}
                  className={`rounded-full border px-3 py-1 text-[11px] font-medium ${status === f.key
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
        <div className="grid grid-cols-[130px_1.5fr_1fr_130px_150px_120px] px-3 py-1.5 bg-[#FAFBFC] text-[10px] font-bold uppercase text-[#6B6B73] border-b border-[#EFF0F2]">
          <span>No. Spesifikasi</span><span>Judul / target kain</span><span>Warna target</span>
          <span>Jenis sample</span><span>Produk & tahap</span>
          <span className="text-right">Status</span>
        </div>
        {loading ? (
          <div className="py-10 text-center text-[12px] text-[#6B6B73]">Memuat spesifikasi…</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-[12px] text-[#6B6B73]" data-testid="rnd-specs-empty">
            <FlaskConical className="mx-auto mb-2 text-gray-300" size={28} />
            <p>Belum ada spesifikasi. Mulai dari sini bila KN meminta supplier membuat
              barang sesuai standar kita (bukan membeli dari katalog).</p>
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F2] max-h-[620px] overflow-y-auto">
            {filtered.map((s) => {
              const meta = SPEC_STATUS_META[s.status] || SPEC_STATUS_META.draft;
              const life = lifecycleMeta(s.lifecycle);
              return (
                <div key={s.id} data-testid={`rnd-spec-row-${s.id}`}
                  className="grid grid-cols-[130px_1.5fr_1fr_130px_150px_120px] items-center px-3 py-2.5 hover:bg-[#FAFBFC]">
                  <button className="text-left text-[11.5px] font-bold text-[#0058CC]"
                    data-testid={`rnd-spec-open-${s.id}`} onClick={() => setOpenId(s.id)}>
                    {s.number}
                  </button>
                  <div className="min-w-0">
                    <p className="truncate text-[12px] font-semibold">{s.title}</p>
                    <p className="truncate text-[10.5px] text-[#6B6B73] flex items-center gap-1">
                      <EntityBadge entityId={s.entity_id} />
                      {(s.target?.fabric_type || "—")}
                      {s.target?.gramasi ? ` · ${s.target.gramasi} gsm` : ""}
                      {s.target?.lebar ? ` · ${s.target.lebar} cm` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 min-w-0">
                    {s.color_target?.hex && (
                      <span className="inline-block h-3.5 w-3.5 rounded-full border border-[#E5E5EA]"
                        style={{ background: s.color_target.hex }} />
                    )}
                    <span className="truncate text-[11.5px]">
                      {s.color_target?.name || "—"}
                      {s.color_target?.code ? ` (${s.color_target.code})` : ""}
                    </span>
                  </div>
                  <span className="text-[11px]">
                    {SAMPLE_TYPE_LABEL[s.sample_type_hint] || s.sample_type_hint}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-[11.5px] font-semibold">{s.product_sku || "—"}</p>
                    <p className="text-[10px] font-bold" style={{ color: life.tone }}
                      data-testid={`rnd-spec-lifecycle-${s.id}`}>{life.label}</p>
                  </div>
                  <div className="flex items-center justify-end">
                    <span className={`status-pill ${meta.cls}`}
                      data-testid={`rnd-spec-status-${s.id}`}>{meta.label}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showForm && (
        <SpecFormModal selectedEntity={selectedEntity} onClose={() => setShowForm(false)}
          onSaved={(created) => { setShowForm(false); load(); setOpenId(created?.id || ""); }} />
      )}
      {openId && (
        <DetailModal onClose={() => setOpenId("")}
          label="Rincian spesifikasi" testId="spec-detail-modal">
          <SpecDetailPanel specId={openId} currentUser={currentUser}
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
      <p className="text-[14px] font-bold tabular-nums leading-tight" style={{ color: tone }}>{value}</p>
    </div>
  );
}
