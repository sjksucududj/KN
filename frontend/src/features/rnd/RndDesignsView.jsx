/**
 * RndDesignsView (FASE F · PS-14) — **Master Desain & Pattern** ber-kode & ber-versi.
 *
 * Ini PERLUASAN koleksi `design_gallery` yang sudah ada (galeri motif HRD H5), bukan
 * koleksi kedua. Yang ditambahkan supaya desain layak jadi master: kode unik, jenis,
 * versi artwork, atribut printing, dan **pengesahan** — karena permintaan *proofing*
 * WAJIB merujuk desain yang sah (kebijakan `rnd.require_design_for_proofing`).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Beaker, CheckCircle2, Layers, Pencil, Plus, RefreshCw, Search, Trash2, Upload,
} from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import LineFilter from "../../components/LineFilter";   // FASE L
import StarRating from "../../components/StarRating";
import DesignFormModal from "./DesignFormModal";
import { openRnd } from "./rndDeepLink";
import {
  approveDesign, deleteDesign, designFileUrl, listDesigns, rateDesign, unrateDesign,
  uploadDesignFile,
} from "./rndApi";
import { DESIGN_STATUS_META, DESIGN_TYPE_LABEL, errMsg } from "./rndMeta";

const STATUS_FILTERS = [
  { key: "", label: "Semua" },
  { key: "draft", label: "Draf" },
  { key: "approved", label: "Disahkan" },
  { key: "retired", label: "Tidak dipakai" },
];

export default function RndDesignsView({ currentUser, selectedEntity }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [minRating, setMinRating] = useState(0); // 0 = semua
  const [lineFilter, setLineFilter] = useState("");   // FASE L
  const [modal, setModal] = useState(null);   // { mode, design }
  const [busyId, setBusyId] = useState("");

  const canManage = ["admin", "manager"].includes(currentUser?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (selectedEntity && selectedEntity !== "all") params.entity_id = selectedEntity;
      if (lineFilter) params.line = lineFilter;          // FASE L
      const res = await listDesigns(params);
      setRows(Array.isArray(res) ? res : res?.items || []);
      setError("");
    } catch (e) {
      setError(errMsg(e, "Gagal memuat master desain."));
    } finally { setLoading(false); }
  }, [selectedEntity, lineFilter]);
  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    return rows.filter((d) => {
      if (status && (d.status || "draft") !== status) return false;
      if (minRating > 0 && Number(d.rating_avg || 0) < minRating) return false;
      if (!term) return true;
      return [d.code, d.title, d.story, ...(d.tags || [])]
        .some((v) => (v || "").toLowerCase().includes(term));
    });
  }, [rows, q, status, minRating]);

  const RATING_FILTERS = [
    { v: 0, label: "Semua" }, { v: 3, label: "★ 3+" },
    { v: 4, label: "★ 4+" }, { v: 4.5, label: "★ 4,5+" },
  ];

  const stats = useMemo(() => ({
    total: rows.length,
    approved: rows.filter((d) => d.status === "approved").length,
    draft: rows.filter((d) => (d.status || "draft") === "draft").length,
    noCode: rows.filter((d) => !(d.code || "").trim()).length,
  }), [rows]);

  const run = async (id, fn, done) => {
    setBusyId(id); setError(""); setOkMsg("");
    try {
      await fn();
      await load();
      if (done) setOkMsg(done);
    } catch (e) {
      setError(errMsg(e, "Aksi desain gagal dijalankan."));
    } finally { setBusyId(""); }
  };

  return (
    <div data-testid="rnd-designs-view">
      <ErrorNotice message={error} onRetry={load} onDismiss={() => setError("")}
        testId="rnd-designs-error" />

      <div className="section-card mb-3">
        <div className="section-head">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-[#6B219A]" />
            <h2 data-testid="rnd-designs-title">Desain & Pattern (Master)</h2>
          </div>
          <div className="flex items-center gap-2">
            <button className="secondary-button" onClick={load} data-testid="rnd-designs-refresh">
              <RefreshCw size={13} /> Muat ulang
            </button>
            {canManage && (
              <button className="primary-button" data-testid="design-create-button"
                onClick={() => setModal({ mode: "create" })}>
                <Plus size={13} /> Desain Baru
              </button>
            )}
          </div>
        </div>
        <div className="section-body space-y-2.5">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4" data-testid="rnd-designs-stats">
            <Kpi label="Total desain" value={String(stats.total)} />
            <Kpi label="Disahkan" value={String(stats.approved)} tone="#1B7F4B" />
            <Kpi label="Draf" value={String(stats.draft)} tone="#B26A00" />
            <Kpi label="Belum berkode" value={String(stats.noCode)} tone="#C0392B" />
          </div>
          {okMsg && (
            <div className="rounded-lg bg-[#EAF7EF] px-3 py-2 text-[11.5px] text-[#1A7A3A]"
              data-testid="rnd-designs-ok">{okMsg}</div>
          )}
          <p className="text-[11px] text-[#6B6B73]" data-testid="rnd-designs-note">
            Desain hanya bisa <b>disahkan</b> bila sudah punya <b>kode</b> dan minimal
            <b> 1 berkas artwork</b>. Permintaan <b>proofing</b> wajib merujuk desain —
            supaya tidak ada printing tanpa gambar acuan yang jelas.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative max-w-sm flex-1">
              <Search size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
              <input data-testid="rnd-designs-search" value={q}
                onChange={(e) => setQ(e.target.value)} className="field !pl-8"
                placeholder="Cari kode / judul / tag…" />
            </div>
            <LineFilter value={lineFilter} onChange={setLineFilter} storageKey="rnd-designs"
                        allowed={currentUser?.allowed_line_codes} testId="rnd-designs-line-filter" />
            <div className="flex flex-wrap gap-1.5" data-testid="rnd-designs-filters">
              {STATUS_FILTERS.map((f) => (
                <button key={f.key} data-testid={`rnd-designs-filter-${f.key || "all"}`}
                  onClick={() => setStatus(f.key)}
                  className={`rounded-full border px-3 py-1 text-[11px] font-medium ${status === f.key
                    ? "border-[#6B219A] bg-[#6B219A] text-white"
                    : "border-[#E5E5EA] bg-white text-[#3C3C43] hover:border-[#6B219A]"}`}>
                  {f.label}
                </button>
              ))}
            </div>
            <div className="inline-flex items-center rounded-full border border-[#E5E5EA] overflow-hidden"
              data-testid="rnd-designs-minrating" title="Saring berdasarkan rating minimal">
              {RATING_FILTERS.map((f) => (
                <button key={f.v} data-testid={`rnd-designs-minrating-${f.v}`}
                  onClick={() => setMinRating(f.v)}
                  className={`px-2.5 py-1 text-[11px] font-medium transition-colors ${minRating === f.v
                    ? "bg-[#F5A623] text-white"
                    : "bg-white text-[#3C3C43] hover:bg-[#FFF7E8]"}`}>
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="section-body">
          {loading ? (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-[210px] animate-pulse rounded-lg bg-[#F5F5F7]" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[12px] text-[#6B6B73]"
              data-testid="rnd-designs-empty">
              <Layers className="mx-auto mb-2 text-gray-300" size={28} />
              {(minRating > 0 || status || q.trim()) ? (
                <p>Tidak ada desain yang cocok dengan saringan saat ini.
                  {minRating > 0 && <> Coba turunkan rating minimal.</>}
                  {" "}
                  <button className="underline text-[#6B219A]" data-testid="rnd-designs-reset-filter"
                    onClick={() => { setMinRating(0); setStatus(""); setQ(""); }}>
                    Reset saringan
                  </button>
                </p>
              ) : (
                <p>Belum ada desain. Daftarkan motif/pattern dengan <b>kode</b> agar bisa
                  dipakai permintaan proofing dan ditautkan ke produk.</p>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
              {filtered.map((d) => {
                const meta = DESIGN_STATUS_META[d.status || "draft"] || DESIGN_STATUS_META.draft;
                const cover = (d.files || [])[0];
                const busy = busyId === d.id;
                return (
                  <div key={d.id} data-testid={`design-card-${d.id}`}
                    className="overflow-hidden rounded-lg border border-[#E5E5EA] bg-white">
                    <div className="flex h-28 items-center justify-center bg-[#F5F5F7]">
                      {cover ? (
                        <img src={designFileUrl(d.id, cover.id)} alt={d.title}
                          data-testid={`design-cover-${d.id}`}
                          className="h-full w-full object-cover" />
                      ) : (
                        <span className="text-[10.5px] text-[#9A9BA3]">belum ada artwork</span>
                      )}
                    </div>
                    <div className="space-y-1 p-2">
                      <div className="flex items-center justify-between gap-1">
                        <span className="truncate text-[11.5px] font-bold"
                          data-testid={`design-code-${d.id}`}>{d.code || "tanpa kode"}</span>
                        <span className="shrink-0 rounded bg-[#F5F5F7] px-1 text-[9px] font-bold text-[#6B6B73]">
                          v{d.version || 1}
                        </span>
                      </div>
                      <p className="truncate text-[10.5px] text-[#3C3C43]">{d.title}</p>
                      <p className="flex items-center justify-between text-[9.5px] text-[#9A9BA3]">
                        <span>{DESIGN_TYPE_LABEL[d.design_type] || d.design_type || "motif"}</span>
                        <span>{d.color_count ? `${d.color_count} warna` : "—"}</span>
                      </p>
                      <span className={`status-pill ${meta.cls}`}
                        data-testid={`design-status-${d.id}`}>{meta.label}</span>

                      <div className="pt-1" data-testid={`design-rating-${d.id}`}>
                        <StarRating value={d.rating_avg} count={d.rating_count} my={d.my_rating}
                          editable={canManage} busy={busy} size={14}
                          onRate={(stars) => run(d.id, () => rateDesign(d.id, stars),
                            `Rating ${stars} bintang tersimpan untuk ${d.code || d.title}.`)}
                          onClear={() => run(d.id, () => unrateDesign(d.id),
                            "Rating Anda dihapus.")}
                          testId={`design-stars-${d.id}`} />
                      </div>

                      <div className="flex flex-wrap gap-1 pt-1">
                        {canManage && (
                          <>
                            <label className="secondary-button !px-1.5 !py-0.5 cursor-pointer text-[10px]"
                              data-testid={`design-upload-label-${d.id}`}>
                              <Upload size={11} /> Artwork
                              <input type="file" className="hidden" accept="image/*,.pdf"
                                data-testid={`design-upload-${d.id}`}
                                onChange={(e) => {
                                  const file = e.target.files?.[0];
                                  if (file) {
                                    run(d.id, () => uploadDesignFile(d.id, file),
                                      `Artwork "${file.name}" terunggah.`);
                                  }
                                  e.target.value = "";
                                }} />
                            </label>
                            <button className="secondary-button !px-1.5 !py-0.5 text-[10px]"
                              disabled={busy} data-testid={`design-edit-${d.id}`}
                              onClick={() => setModal({ mode: "edit", design: d })}>
                              <Pencil size={11} /> Ubah
                            </button>
                            <button className="secondary-button !px-1.5 !py-0.5 text-[10px]"
                              disabled={busy} data-testid={`design-version-${d.id}`}
                              title="Naikkan versi artwork"
                              onClick={() => setModal({ mode: "version", design: d })}>
                              v+
                            </button>
                            {d.status !== "approved" && (
                              <button className="primary-button !px-1.5 !py-0.5 text-[10px]"
                                disabled={busy} data-testid={`design-approve-${d.id}`}
                                onClick={() => run(d.id,
                                  () => approveDesign(d.id, "Disahkan dari layar Desain & Pattern"),
                                  `Desain ${d.code || d.title} disahkan — boleh dipakai proofing.`)}>
                                <CheckCircle2 size={11} /> Sahkan
                              </button>
                            )}
                            <button className="icon-button text-red-400 hover:text-red-600"
                              disabled={busy} title="Hapus desain"
                              data-testid={`design-delete-${d.id}`}
                              onClick={() => run(d.id, () => deleteDesign(d.id),
                                "Desain dihapus.")}>
                              <Trash2 size={11} />
                            </button>
                          </>
                        )}
                        {d.status === "approved" && (
                          <button className="secondary-button !px-1.5 !py-0.5 text-[10px]"
                            data-testid={`design-proofing-${d.id}`}
                            title="Buat permintaan proofing memakai desain ini"
                            onClick={() => openRnd({ view: "rnd-samples", designId: d.id,
                              designLabel: `${d.code || d.title} v${d.version || 1}` })}>
                            <Beaker size={11} /> Proofing
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {modal && (
        <DesignFormModal mode={modal.mode} design={modal.design}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load(); }} />
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
