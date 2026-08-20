import { useEffect, useMemo, useState } from "react";
import axios, { API } from "../../services/apiClient";
import { Palette, Plus, Search, Upload, Trash2, Sparkles, ImageOff, Settings, X, Tag, Send, CheckCircle2, Undo2} from "lucide-react";
import ErrorNotice from "../../components/ErrorNotice";
import { askReason } from "../../services/confirmService";
import ConfirmModal from "../../components/ConfirmModal";
import StarRating from "../../components/StarRating";
import { rateDesign, unrateDesign } from "../rnd/rndApi";
import { ACCEPT_IMG, MAX_IMG_MB, fetchGalleryImageUrl, validateImage, fmtBytes } from "./galleryUtils";

// FASE H5 — Design Gallery (motif kain) + upload gambar + AI auto-tag (graceful). Keputusan 3a.
export default function DesignGalleryView({ currentUser, selectedEntity }) {
  const canManage = ["admin", "manager"].includes(currentUser?.role);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [minRating, setMinRating] = useState(0); // 0 = semua
  const [showCreate, setShowCreate] = useState(false);
  const [manage, setManage] = useState(null); // gallery doc in manage modal
  const [delTarget, setDelTarget] = useState(null);

  const params = useMemo(
    () => (selectedEntity && selectedEntity !== "all" ? { entity_id: selectedEntity } : {}),
    [selectedEntity]
  );

  useEffect(() => { load(); }, [selectedEntity]); // eslint-disable-line
  async function load() {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/design-gallery`, { params: { ...params, ...(q ? { q } : {}) } });
      setItems(Array.isArray(r.data) ? r.data : []);
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Gagal memuat galeri.");
    } finally { setLoading(false); }
  }

  async function refreshManage(id) {
    try {
      const r = await axios.get(`${API}/design-gallery/${id}`);
      setManage(r.data);
      // sinkronkan kartu di grid
      setItems((prev) => prev.map((it) => (it.id === id ? r.data : it)));
    } catch (_) { /* noop */ }
  }

  async function doDelete(g) {
    try { await axios.delete(`${API}/design-gallery/${g.id}`); await load(); }
    catch (e) { setError(e.response?.data?.detail || "Gagal menghapus motif."); }
    finally { setDelTarget(null); }
  }

  // Saring berdasarkan rating minimal (di sisi klien — daftar sudah dimuat).
  const RATING_FILTERS = [
    { v: 0, label: "Semua" },
    { v: 3, label: "★ 3+" },
    { v: 4, label: "★ 4+" },
    { v: 4.5, label: "★ 4,5+" },
  ];
  const visibleItems = useMemo(
    () => (minRating > 0
      ? items.filter((g) => Number(g.rating_avg || 0) >= minRating)
      : items),
    [items, minRating]
  );

  return (
    <div className="grid gap-3" data-testid="design-gallery-view">
      {/* Toolbar */}
      <section className="section-card !p-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative flex-1 min-w-[200px] max-w-[360px]">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#9A9BA3]" />
            <input data-testid="gallery-search" className="form-input !pl-8" placeholder="Cari judul, cerita, atau tag…" value={q}
              onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") load(); }} />
          </div>
          <button data-testid="gallery-search-button" className="secondary-button" onClick={load}><Search size={13} /> Cari</button>
          <div className="inline-flex items-center rounded-lg border border-[#E1E4EA] overflow-hidden"
            data-testid="gallery-minrating" title="Saring berdasarkan rating minimal">
            {RATING_FILTERS.map((f) => (
              <button key={f.v} type="button" data-testid={`gallery-minrating-${f.v}`}
                onClick={() => setMinRating(f.v)}
                className={`px-2.5 py-1 text-[11.5px] font-semibold transition-colors ${
                  minRating === f.v ? "bg-[#F5A623] text-white" : "bg-white text-[#4A4B52] hover:bg-[#FFF7E8]"
                }`}>
                {f.label}
              </button>
            ))}
          </div>
          {canManage && (
            <button data-testid="gallery-add-button" className="primary-button ml-auto" onClick={() => setShowCreate(true)}><Plus size={14} /> Tambah Motif</button>
          )}
        </div>
      </section>

      {error && <ErrorNotice message={error} onRetry={load} testId="gallery-error" />}

      {/* Grid */}
      {loading ? (
        <div className="section-card !p-10 text-center"><p className="text-[12px] text-[#6B6B73]" data-testid="gallery-loading">Memuat galeri motif…</p></div>
      ) : items.length === 0 ? (
        <div className="section-card !p-12 text-center" data-testid="gallery-empty">
          <Palette size={30} className="mx-auto text-[#C7C9CF] mb-2" />
          <p className="text-[13px] font-semibold text-[#3A3B42]">Belum ada motif</p>
          <p className="text-[12px] text-[#9A9BA3] mt-0.5">Tambahkan motif kain pertama Anda beserta cerita dan gambarnya.</p>
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="section-card !p-12 text-center" data-testid="gallery-filter-empty">
          <Palette size={30} className="mx-auto text-[#C7C9CF] mb-2" />
          <p className="text-[13px] font-semibold text-[#3A3B42]">
            Tidak ada motif dengan rating ≥ {String(minRating).replace(".", ",")}
          </p>
          <p className="text-[12px] text-[#9A9BA3] mt-0.5">
            Turunkan ambang rating atau pilih “Semua”.
          </p>
          <button className="secondary-button mt-2 mx-auto" data-testid="gallery-minrating-reset"
            onClick={() => setMinRating(0)}>Tampilkan semua</button>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" data-testid="gallery-grid">
          {visibleItems.map((g) => (
            <GalleryCard key={g.id} g={g} canManage={canManage}
              onManage={() => setManage(g)} onDelete={() => setDelTarget(g)} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateModal params={params} onClose={() => setShowCreate(false)} onCreated={async (id) => { setShowCreate(false); await load(); const r = await axios.get(`${API}/design-gallery/${id}`); setManage(r.data); }} />
      )}
      {manage && (
        <ManageModal g={manage} canManage={canManage} onClose={() => { setManage(null); }} onChanged={() => refreshManage(manage.id)} />
      )}

      <ConfirmModal open={!!delTarget} title="Hapus Motif?" message={delTarget ? `Hapus "${delTarget.title}" beserta gambarnya?` : ""} confirmLabel="Hapus" danger onConfirm={() => doDelete(delTarget)} onCancel={() => setDelTarget(null)} testId="gallery-delete-modal" />
    </div>
  );
}

// UTANG ALUR F-6.7 — status desain kini bertahap: draf → diajukan → sah.
// Tanpa tahap "diajukan", pengesahan bekerja dari draf sehingga karya yang masih
// digambar tak bisa dibedakan dari yang menunggu keputusan, dan antrean keputusan
// tak mungkin menghitungnya dengan jujur.
const DESIGN_STATUS = {
  draft: { cls: "pill-muted", label: "Draf" },
  pending_approval: { cls: "pill-warning", label: "Menunggu pengesahan" },
  approved: { cls: "pill-success", label: "Sah" },
  retired: { cls: "pill-danger", label: "Tidak dipakai" },
};

// ─── Kartu motif ────────────────────────────────────────────
function GalleryCard({ g, canManage, onManage, onDelete }) {
  const cover = (g.files || [])[0];
  const aiOn = g.ai_meta?.enabled && (g.ai_meta?.tags || []).length > 0;
  return (
    <div className="section-card !p-0 overflow-hidden flex flex-col" data-testid={`gallery-card-${g.id}`}>
      <div className="aspect-[4/3] bg-[#F2F3F5] relative">
        {cover ? <GalleryImage galleryId={g.id} fileId={cover.id} alt={g.title} />
          : <div className="h-full w-full flex flex-col items-center justify-center text-[#C7C9CF]"><ImageOff size={26} /><span className="text-[11px] mt-1">Tanpa gambar</span></div>}
        {aiOn && <span className="absolute top-2 right-2 px-1.5 py-0.5 rounded bg-[#0058CC] text-white text-[10px] font-semibold flex items-center gap-1"><Sparkles size={10} /> AI</span>}
      </div>
      <div className="p-3 flex flex-col gap-1.5 flex-1">
        <div className="flex items-center gap-1.5">
          <h3 className="text-[13px] font-bold leading-tight truncate flex-1">{g.title}</h3>
          <span className={`status-pill ${(DESIGN_STATUS[g.status] || DESIGN_STATUS.draft).cls}`}
            data-testid={`gallery-card-status-${g.id}`}>
            {(DESIGN_STATUS[g.status] || DESIGN_STATUS.draft).label}
          </span>
        </div>
        {g.code && <p className="text-[10.5px] font-mono text-[#6B6B73]">{g.code}</p>}
        {g.story && <p className="text-[11.5px] text-[#6B6B73] line-clamp-2">{g.story}</p>}
        <div className="flex flex-wrap gap-1 mt-0.5">
          {(g.tags || []).slice(0, 6).map((t) => <span key={t} className="px-1.5 py-0.5 rounded bg-[#EEF1F5] text-[#4A4B52] text-[10.5px]">{t}</span>)}
          {(g.tags || []).length === 0 && <span className="text-[10.5px] text-[#9A9BA3]">Belum ada tag</span>}
        </div>
        <div className="mt-1" data-testid={`gallery-card-rating-${g.id}`}>
          <StarRating value={g.rating_avg} count={g.rating_count} size={13}
            testId={`gallery-card-stars-${g.id}`} />
        </div>
        <div className="flex items-center gap-2 mt-auto pt-2">
          <button data-testid={`gallery-manage-${g.id}-button`} className="secondary-button flex-1 justify-center" onClick={onManage}><Settings size={13} /> {canManage ? "Kelola" : "Detail"}</button>
          {canManage && <button data-testid={`gallery-delete-${g.id}-button`} className="icon-button text-[#C0341D]" title="Hapus" onClick={onDelete}><Trash2 size={14} /></button>}
        </div>
      </div>
    </div>
  );
}

// Gambar via blob-fetch ber-Authorization → objectURL (revoke saat unmount).
function GalleryImage({ galleryId, fileId, alt }) {
  const [url, setUrl] = useState("");
  const [fail, setFail] = useState(false);
  useEffect(() => {
    let active = true; let created = "";
    fetchGalleryImageUrl(galleryId, fileId).then((u) => { if (active) { created = u; setUrl(u); } }).catch(() => active && setFail(true));
    return () => { active = false; if (created) URL.revokeObjectURL(created); };
  }, [galleryId, fileId]);
  if (fail) return <div className="h-full w-full flex items-center justify-center text-[#C7C9CF]"><ImageOff size={24} /></div>;
  if (!url) return <div className="h-full w-full animate-pulse bg-[#E9EBEF]" />;
  return <img src={url} alt={alt} className="h-full w-full object-cover" />;
}

// ─── Modal buat motif ──────────────────────────────────────
function CreateModal({ onClose, onCreated }) {
  const [title, setTitle] = useState("");
  const [story, setStory] = useState("");
  const [tags, setTags] = useState("");
  const [productId, setProductId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function save() {
    if (!title.trim()) { setErr("Judul motif wajib diisi."); return; }
    setBusy(true); setErr("");
    try {
      const r = await axios.post(`${API}/design-gallery`, {
        title: title.trim(), story,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean), product_id: productId.trim(),
      });
      onCreated(r.data.id);
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan motif."); }
    finally { setBusy(false); }
  }
  return (
    <div className="modal-overlay" data-testid="gallery-create-modal" onClick={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className="modal-card">
        <p className="modal-title">Tambah Motif</p>
        {err && <div className="notice-bar danger !mb-2 !py-1.5" data-testid="gallery-create-error"><span className="text-[11.5px]">{err}</span></div>}
        <div className="grid gap-2.5">
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Judul *</label>
            <input data-testid="gallery-create-title" className="form-input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="mis. Batik Mega Mendung" /></div>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Cerita / Deskripsi</label>
            <textarea data-testid="gallery-create-story" className="form-input" rows="3" value={story} onChange={(e) => setStory(e.target.value)} placeholder="Filosofi & cerita di balik motif…" /></div>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Tags (pisah dengan koma)</label>
            <input data-testid="gallery-create-tags" className="form-input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="batik, floral, klasik" /></div>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Link Produk (opsional)</label>
            <input data-testid="gallery-create-product" className="form-input" value={productId} onChange={(e) => setProductId(e.target.value)} placeholder="ID/SKU produk" /></div>
          <div className="modal-actions">
            <button className="btn-secondary" onClick={onClose} disabled={busy}>Batal</button>
            <button data-testid="gallery-create-submit" className="btn-primary" onClick={save} disabled={busy}>{busy ? "Menyimpan…" : "Simpan & Lanjut Upload"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Modal kelola (edit + files + autotag) ──────────────────────────
function ManageModal({ g, canManage, onClose, onChanged }) {
  const [title, setTitle] = useState(g.title || "");
  const [story, setStory] = useState(g.story || "");
  const [tags, setTags] = useState((g.tags || []).join(", "));
  const [productId, setProductId] = useState(g.product_id || "");
  const [code, setCode] = useState(g.code || "");
  const [busy, setBusy] = useState(false);
  const [flowBusy, setFlowBusy] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [ai, setAi] = useState(null);
  const [ratingBusy, setRatingBusy] = useState(false);
  const files = g.files || [];

  async function doRate(stars) {
    setRatingBusy(true); setErr(""); setMsg("");
    try {
      await rateDesign(g.id, stars);
      setMsg(`Rating Anda tersimpan: ${stars} bintang.`); await onChanged();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan rating."); }
    finally { setRatingBusy(false); }
  }
  async function doClearRating() {
    setRatingBusy(true); setErr(""); setMsg("");
    try {
      await unrateDesign(g.id);
      setMsg("Rating Anda dihapus."); await onChanged();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menghapus rating."); }
    finally { setRatingBusy(false); }
  }

  async function saveMeta() {
    if (!title.trim()) { setErr("Judul tidak boleh kosong."); return; }
    setBusy(true); setErr(""); setMsg("");
    try {
      await axios.put(`${API}/design-gallery/${g.id}`, {
        title: title.trim(), story, code: code.trim(),
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean), product_id: productId.trim(),
      });
      setMsg("Perubahan tersimpan."); await onChanged();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menyimpan."); }
    finally { setBusy(false); }
  }
  async function onPickFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    const v = validateImage(file);
    if (v) { setErr(v); return; }
    setUploadBusy(true); setErr(""); setMsg("");
    try {
      const fd = new FormData(); fd.append("file", file);
      await axios.post(`${API}/design-gallery/${g.id}/files`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setMsg("Gambar terunggah."); await onChanged();
    } catch (e2) { setErr(e2.response?.data?.detail || "Gagal mengunggah gambar."); }
    finally { setUploadBusy(false); }
  }
  async function delFile(fid) {
    setErr(""); setMsg("");
    try { await axios.delete(`${API}/design-gallery/${g.id}/files/${fid}`); setMsg("Gambar dihapus."); await onChanged(); }
    catch (e) { setErr(e.response?.data?.detail || "Gagal menghapus gambar."); }
  }
  // UTANG ALUR F-6.7 — Ajukan / Sahkan / Kembalikan ke draf.
  async function flow(action) {
    setFlowBusy(action); setErr(""); setMsg("");
    try {
      if (action === "submit") {
        await axios.post(`${API}/design-gallery/${g.id}/submit`);
        setMsg("Desain diajukan — kini masuk antrean pengesahan.");
      } else if (action === "approve") {
        await axios.post(`${API}/design-gallery/${g.id}/approve`, { note: "" });
        setMsg("Desain disahkan — boleh dipakai spesifikasi & proofing.");
      }
      await onChanged();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal memproses desain."); }
    finally { setFlowBusy(""); }
  }
  async function rejectFlow() {
    const reason = await askReason({
      title: "Kembalikan desain ini ke draf?",
      description: "Desainer bisa memperbaikinya. Alasannya tersimpan di dokumen desain.",
      confirmLabel: "Kembalikan ke draf",
      reasonPlaceholder: "Contoh: warna belum sesuai brief pelanggan",
      danger: true,
    });
    if (!reason) return;
    setFlowBusy("reject"); setErr(""); setMsg("");
    try {
      await axios.post(`${API}/design-gallery/${g.id}/reject`, { reason });
      setMsg("Desain dikembalikan ke draf."); await onChanged();
    } catch (e) { setErr(e.response?.data?.detail || "Gagal mengembalikan desain."); }
    finally { setFlowBusy(""); }
  }

  async function runAutotag() {
    setAiBusy(true); setErr(""); setMsg(""); setAi(null);
    try {
      const r = await axios.post(`${API}/design-gallery/${g.id}/autotag`);
      setAi(r.data);
      if (r.data?.enabled && !r.data?.error) { setMsg("Auto-tag AI selesai."); await onChanged(); }
    } catch (e) { setErr(e.response?.data?.detail || "Gagal menjalankan auto-tag."); }
    finally { setAiBusy(false); }
  }

  return (
    <div className="modal-overlay" data-testid="gallery-manage-modal" onClick={(e) => { if (e.target === e.currentTarget && !busy && !uploadBusy && !aiBusy) onClose(); }}>
      <div className="modal-card !max-w-[640px]">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <p className="modal-title !mb-0 truncate">{canManage ? "Kelola Motif" : g.title}</p>
            <span className={`status-pill ${(DESIGN_STATUS[g.status] || DESIGN_STATUS.draft).cls}`}
              data-testid="gallery-manage-status">
              {(DESIGN_STATUS[g.status] || DESIGN_STATUS.draft).label}
            </span>
          </div>
          <button className="icon-button" onClick={onClose}><X size={16} /></button>
        </div>
        {canManage && (
          <div className="flex flex-wrap items-center gap-2 mt-2" data-testid="gallery-flow-actions">
            {g.status === "draft" && (
              <button data-testid="gallery-submit-button" className="primary-button !py-1.5"
                disabled={flowBusy === "submit"} onClick={() => flow("submit")}>
                <Send size={13} /> {flowBusy === "submit" ? "Mengajukan…" : "Ajukan"}
              </button>
            )}
            {g.status === "pending_approval" && (
              <>
                <button data-testid="gallery-approve-button" className="primary-button !py-1.5"
                  disabled={flowBusy === "approve"} onClick={() => flow("approve")}>
                  <CheckCircle2 size={13} /> {flowBusy === "approve" ? "Mengesahkan…" : "Sahkan"}
                </button>
                <button data-testid="gallery-reject-button" className="secondary-button !py-1.5"
                  disabled={flowBusy === "reject"} onClick={rejectFlow}>
                  <Undo2 size={13} /> Kembalikan ke Draf
                </button>
              </>
            )}
            <span className="text-[10.5px] text-[#9A9BA3]">
              {g.status === "draft"
                ? "Ajukan bila desain sudah punya kode & minimal 1 gambar."
                : g.status === "pending_approval"
                  ? "Menunggu keputusan — muncul di Pusat Persetujuan & KPI beranda."
                  : "Desain sah boleh dirujuk spesifikasi & proofing."}
            </span>
          </div>
        )}
        {g.reject_reason && (
          <div className="notice-bar warning !my-2 !py-1.5" data-testid="gallery-reject-reason">
            <span className="text-[11.5px]"><b>Dikembalikan ke draf</b>
              {g.rejected_by ? ` oleh ${g.rejected_by}` : ""}: {g.reject_reason}</span>
          </div>
        )}
        {err && <div className="notice-bar danger !my-2 !py-1.5" data-testid="gallery-manage-error"><span className="text-[11.5px]">{err}</span></div>}
        {msg && <div className="notice-bar success !my-2 !py-1.5" data-testid="gallery-manage-msg"><span className="text-[11.5px]">{msg}</span></div>}

        {/* Gambar */}
        <div className="grid gap-1.5 mt-2">
          <label className="text-[11px] font-bold uppercase text-[#6B6B73]">Gambar ({files.length})</label>
          <div className="flex flex-wrap gap-2">
            {files.map((f) => (
              <div key={f.id} className="relative w-[88px]">
                <div className="aspect-square rounded-md overflow-hidden bg-[#F2F3F5] border border-[#EFF0F2]"><GalleryImage galleryId={g.id} fileId={f.id} alt={f.filename} /></div>
                <span className="block text-[9.5px] text-[#9A9BA3] truncate mt-0.5">{fmtBytes(f.size)}</span>
                {canManage && <button data-testid={`gallery-file-del-${f.id}-button`} className="absolute -top-1.5 -right-1.5 bg-white rounded-full shadow p-0.5 text-[#C0341D]" onClick={() => delFile(f.id)}><X size={12} /></button>}
              </div>
            ))}
            {canManage && (
              <label data-testid="gallery-upload-label" className={`w-[88px] aspect-square rounded-md border-2 border-dashed border-[#CDD2DA] flex flex-col items-center justify-center text-[#6B6B73] cursor-pointer hover:border-[#0058CC] hover:text-[#0058CC] ${uploadBusy ? "opacity-50 pointer-events-none" : ""}`}>
                <Upload size={16} /><span className="text-[9.5px] mt-1 text-center px-1">{uploadBusy ? "Mengunggah…" : "Tambah"}</span>
                <input data-testid="gallery-upload-input" type="file" accept={ACCEPT_IMG} className="hidden" onChange={onPickFile} />
              </label>
            )}
          </div>
          <p className="text-[10px] text-[#9A9BA3]">JPG / PNG / WEBP, maks {MAX_IMG_MB}MB.</p>
        </div>

        {/* Rating desain (bintang 1–5, 1 nilai per penilai) */}
        <div className="mt-3 rounded-lg border border-[#F1E7CC] bg-[#FFFBF0] p-2.5" data-testid="gallery-rating-block">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-[12px] font-semibold text-[#8C6A00]">Rating Desain</span>
            <StarRating value={g.rating_avg} count={g.rating_count} my={g.my_rating}
              editable={canManage} busy={ratingBusy} size={18}
              onRate={doRate} onClear={doClearRating}
              testId="gallery-manage-rating" />
          </div>
          <p className="text-[10.5px] text-[#9A9BA3] mt-1">
            {canManage
              ? "Klik bintang untuk memberi/mengubah nilai Anda. Kartu menampilkan rata-rata semua penilai."
              : "Rata-rata penilaian dari admin & manajer."}
          </p>
        </div>

        {/* AI auto-tag */}
        {canManage && (
          <div className="mt-3 rounded-lg border border-[#EAF1FF] bg-[#F6F9FF] p-2.5">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-[12px] font-semibold text-[#0058CC]"><Sparkles size={14} /> Auto-tag AI (Anthropic Claude)</span>
              <button data-testid="gallery-autotag-button" className="secondary-button !py-1" onClick={runAutotag} disabled={aiBusy || files.length === 0}>{aiBusy ? "Menganalisa…" : "Jalankan"}</button>
            </div>
            {files.length === 0 && <p className="text-[10.5px] text-[#9A9BA3] mt-1">Unggah gambar dulu untuk dianalisa.</p>}
            {ai && !ai.enabled && <p className="text-[11px] text-[#B7791F] mt-1.5" data-testid="gallery-ai-disabled">AI nonaktif. Admin dapat mengaktifkan & mengisi API key di Pengaturan → Integrasi AI.</p>}
            {ai && ai.enabled && ai.error && <p className="text-[11px] text-[#C0341D] mt-1.5" data-testid="gallery-ai-error">{ai.error}</p>}
            {ai && ai.enabled && !ai.error && (
              <div className="mt-1.5" data-testid="gallery-ai-result">
                {ai.summary && <p className="text-[11.5px] text-[#3A3B42]">{ai.summary}</p>}
                <div className="flex flex-wrap gap-1 mt-1">{(ai.tags || []).map((t) => <span key={t} className="px-1.5 py-0.5 rounded bg-[#0058CC] text-white text-[10.5px] flex items-center gap-1"><Tag size={9} />{t}</span>)}</div>
              </div>
            )}
          </div>
        )}

        {/* Metadata */}
        <div className="grid gap-2.5 mt-3">
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Judul</label>
            <input data-testid="gallery-edit-title" className="form-input" value={title} disabled={!canManage} onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Kode Desain</label>
            <input data-testid="gallery-edit-code" className="form-input" value={code} disabled={!canManage}
              placeholder="Contoh: DSG-PARANG-01" onChange={(e) => setCode(e.target.value)} />
            <p className="text-[10px] text-[#9A9BA3]">Wajib sebelum desain diajukan — dipakai spesifikasi & proofing untuk merujuk desain ini.</p></div>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Cerita / Deskripsi</label>
            <textarea data-testid="gallery-edit-story" className="form-input" rows="3" value={story} disabled={!canManage} onChange={(e) => setStory(e.target.value)} /></div>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Tags (pisah koma)</label>
            <input data-testid="gallery-edit-tags" className="form-input" value={tags} disabled={!canManage} onChange={(e) => setTags(e.target.value)} /></div>
          <div className="grid gap-1"><label className="text-[11px] font-bold uppercase text-[#6B6B73]">Link Produk</label>
            <input data-testid="gallery-edit-product" className="form-input" value={productId} disabled={!canManage} onChange={(e) => setProductId(e.target.value)} /></div>
          {canManage && (
            <div className="modal-actions">
              <button className="btn-secondary" onClick={onClose} disabled={busy}>Tutup</button>
              <button data-testid="gallery-edit-submit" className="btn-primary" onClick={saveMeta} disabled={busy}>{busy ? "Menyimpan…" : "Simpan Perubahan"}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
