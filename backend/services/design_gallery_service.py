"""HRD H5 services — Design Gallery (motif kain) + upload gambar (storage lokal).

Koleksi kanonik (entity-scoped): `design_gallery` (dsgn_). Keputusan owner 3a:
upload gambar (JPG/PNG ≤10MB via storage_service) + judul + cerita + tags +
(opsional) link produk. AI auto-tag GRACEFUL via hr_ai_service (HR-Q5).

CATATAN storage: `storage_service.get_object()` MENGEMBALIKAN TUPLE (data, ctype).
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, safe_doc
from services import storage_service as storage
from services import hr_ai_service
from services import line_scope as _lines      # FASE L — satu pintu normalisasi lini


def _clean_tags(tags) -> List[str]:
    out, seen = [], set()
    for t in (tags or []):
        s = str(t).strip()
        k = s.lower()
        if s and k not in seen:
            seen.add(k)
            out.append(s)
    return out[:30]


DESIGN_TYPES = ("motif", "pattern", "artwork")
# UTANG ALUR F-6.7 (dibayar 2026-08-18): `pending_approval` disisipkan antara draf
# dan sah. Tanpa itu pengesahan bekerja dari `draft`, sehingga desain yang masih
# digambar desainer tak bisa dibedakan dari yang siap disahkan — dan antrean
# keputusan tidak mungkin menghitungnya tanpa menyebut pekerjaan orang sebagai
# antrean (alasan pembebasan lama di `verify_approval_queues.DOOR_EXEMPT`).
DESIGN_STATUSES = ("draft", "pending_approval", "approved", "retired")


# ─── Rating desain (bintang 1–5, 1 nilai per penilai) ──────────────────────────
def _rating_fields(doc: Optional[Dict[str, Any]],
                   viewer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Perkaya dokumen desain dengan ringkasan rating agar UI cukup baca 3 field:
    `rating_avg` (rata-rata bintang), `rating_count` (jumlah penilai), dan
    `my_rating` (bintang milik penilai yang sedang melihat, bila ada).

    Rating disimpan di `ratings: [{user_id, name, stars, note, at}]` — SATU baris
    per penilai (upsert), sehingga rata-rata selalu mencerminkan penilai unik.
    """
    if not doc:
        return doc
    ratings = doc.get("ratings") or []
    stars = [int(r.get("stars") or 0) for r in ratings if r.get("stars")]
    count = len(stars)
    out = dict(doc)
    out["rating_avg"] = round(sum(stars) / count, 2) if count else 0.0
    out["rating_count"] = count
    out["my_rating"] = None
    if viewer_id:
        for r in ratings:
            if r.get("user_id") == viewer_id:
                out["my_rating"] = int(r.get("stars") or 0)
                break
    return out


async def set_rating(gallery_id: str, user_id: str, name: str, stars: Any,
                     note: str = "") -> Dict[str, Any]:
    """Set/ubah rating bintang 1–5 milik SATU penilai (upsert, tanpa duplikat)."""
    try:
        stars_i = int(stars)
    except (TypeError, ValueError):
        raise ValueError("Nilai bintang harus angka 1–5.")
    if stars_i < 1 or stars_i > 5:
        raise ValueError("Nilai bintang harus di antara 1 sampai 5.")
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    # buang rating lama milik penilai yang sama → jaga 1 baris per penilai
    ratings = [r for r in (cur.get("ratings") or []) if r.get("user_id") != user_id]
    ratings.append({"user_id": user_id, "name": name or "", "stars": stars_i,
                    "note": (note or "").strip(), "at": now_iso()})
    await db.design_gallery.update_one(
        {"id": gallery_id}, {"$set": {"ratings": ratings, "updated_at": now_iso()}})
    doc = safe_doc(await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0}))
    return _rating_fields(doc, user_id)


async def clear_rating(gallery_id: str, user_id: str) -> Dict[str, Any]:
    """Hapus rating milik penilai (mis. salah beri nilai)."""
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    ratings = [r for r in (cur.get("ratings") or []) if r.get("user_id") != user_id]
    await db.design_gallery.update_one(
        {"id": gallery_id}, {"$set": {"ratings": ratings, "updated_at": now_iso()}})
    doc = safe_doc(await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0}))
    return _rating_fields(doc, user_id)


async def create_gallery(payload: Dict[str, Any], actor_name: str, entity_id: str) -> Dict[str, Any]:
    title = (payload.get("title") or "").strip()
    if not title:
        raise ValueError("Judul motif wajib diisi.")
    # FASE F (PS-14) — perluasan menjadi MASTER DESAIN: kode unik, versi, jenis,
    # dan atribut printing (repeat/jumlah warna/screen). Additive: entri lama tetap sah.
    code = (payload.get("code") or "").strip().upper()
    if code and await db.design_gallery.find_one({"code": code, "entity_id": entity_id},
                                                 {"_id": 0, "id": 1}):
        raise ValueError(f"Kode desain '{code}' sudah dipakai pada entitas ini.")
    dtype = (payload.get("design_type") or "motif").strip().lower()
    if dtype not in DESIGN_TYPES:
        raise ValueError(f"Jenis desain harus salah satu: {', '.join(DESIGN_TYPES)}.")
    doc = {
        "id": new_id("dsgn"),
        "title": title, "story": payload.get("story", ""),
        "tags": _clean_tags(payload.get("tags")),
        "files": [], "product_id": payload.get("product_id", ""),
        "code": code, "design_type": dtype, "version": 1, "status": "draft",
        # FASE L — lini kerja MD desain (kosong = belum bergolong, tetap terlihat semua).
        "line_code": _lines.norm(payload.get("line_code")),
        "repeat_cm": payload.get("repeat_cm"),
        "color_count": int(payload.get("color_count") or 0),
        "screen_count": int(payload.get("screen_count") or 0),
        "versions": [{"version": 1, "note": "Versi awal", "at": now_iso(),
                      "by": actor_name, "files": []}],
        "approved_by": "", "approved_at": "",
        "ratings": [],
        "ai_meta": {"enabled": False, "model": "", "tags": [], "summary": "",
                    "attributes": {}, "analyzed_at": ""},
        "entity_id": entity_id,
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.design_gallery.insert_one(doc)
    return safe_doc(doc)


async def list_gallery(scope: Dict[str, Any], tag: Optional[str] = None,
                       q: Optional[str] = None,
                       viewer_id: Optional[str] = None) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = dict(scope or {})
    if tag:
        query["tags"] = tag
    rows = await db.design_gallery.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    rows = [_rating_fields(safe_doc(r), viewer_id) for r in rows]
    if q:
        s = q.lower()
        rows = [r for r in rows if s in (r.get("title", "") or "").lower()
                or s in (r.get("story", "") or "").lower()
                or any(s in (t or "").lower() for t in (r.get("tags") or []))]
    return rows


async def get_gallery(gallery_id: str,
                      viewer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return _rating_fields(
        safe_doc(await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})),
        viewer_id)


async def update_gallery(gallery_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    from pymongo import ReturnDocument
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    updates: Dict[str, Any] = {}
    if patch.get("title") is not None:
        if not str(patch["title"]).strip():
            raise ValueError("Judul motif tidak boleh kosong.")
        updates["title"] = str(patch["title"]).strip()
    if patch.get("story") is not None:
        updates["story"] = patch["story"]
    if patch.get("product_id") is not None:
        updates["product_id"] = patch["product_id"]
    if patch.get("tags") is not None:
        updates["tags"] = _clean_tags(patch["tags"])
    if patch.get("line_code") is not None:      # FASE L
        updates["line_code"] = _lines.norm(patch["line_code"])
    # FASE F (PS-14) — atribut master desain.
    if patch.get("code") is not None:
        code = str(patch["code"]).strip().upper()
        if code:
            dup = await db.design_gallery.find_one(
                {"code": code, "entity_id": cur.get("entity_id"), "id": {"$ne": gallery_id}},
                {"_id": 0, "id": 1})
            if dup:
                raise ValueError(f"Kode desain '{code}' sudah dipakai desain lain.")
        updates["code"] = code
    if patch.get("design_type") is not None:
        dtype = str(patch["design_type"]).strip().lower()
        if dtype not in DESIGN_TYPES:
            raise ValueError(f"Jenis desain harus salah satu: {', '.join(DESIGN_TYPES)}.")
        updates["design_type"] = dtype
    if patch.get("status") is not None:
        st = str(patch["status"]).strip().lower()
        if st not in DESIGN_STATUSES:
            raise ValueError(f"Status desain harus salah satu: {', '.join(DESIGN_STATUSES)}.")
        updates["status"] = st
    for num, caster in (("repeat_cm", float), ("color_count", int), ("screen_count", int)):
        if patch.get(num) is not None:
            try:
                updates[num] = caster(patch[num])
            except (TypeError, ValueError):
                raise ValueError(f"Nilai '{num}' harus angka.")
    if not updates:
        raise ValueError("Tidak ada field valid untuk diupdate.")
    updates["updated_at"] = now_iso()
    doc = await db.design_gallery.find_one_and_update(
        {"id": gallery_id}, {"$set": updates},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    return safe_doc(doc)


async def delete_gallery(gallery_id: str) -> Dict[str, Any]:
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    # FASE F — desain yang sudah dipakai spesifikasi/sample TIDAK boleh dihapus:
    # jejak asal motif harus tetap bisa ditelusuri (aturan repo: append-only).
    used_spec = await db.md_specs.count_documents({"design_id": gallery_id})
    used_smp = await db.md_samples.count_documents({"design_id": gallery_id})
    if used_spec or used_smp:
        raise ValueError(
            f"Desain ini sudah dipakai {used_spec} spesifikasi & {used_smp} permintaan sample — "
            "tidak bisa dihapus. Ubah statusnya menjadi 'retired' bila tidak dipakai lagi.")
    await db.design_gallery.delete_one({"id": gallery_id})
    return {"id": gallery_id, "deleted": True}


async def bump_version(gallery_id: str, payload: Dict[str, Any], actor_name: str) -> Dict[str, Any]:
    """FASE F (PS-14) — naikkan versi desain; berkas versi sebelumnya diarsipkan."""
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    nextv = int(cur.get("version") or 1) + 1
    entry = {"version": nextv, "note": (payload.get("note") or "").strip(),
             "at": now_iso(), "by": actor_name,
             "files": [f.get("id") for f in (cur.get("files") or [])]}
    updates: Dict[str, Any] = {"version": nextv, "status": "draft",
                               "approved_by": "", "approved_at": "", "updated_at": now_iso()}
    for num, caster in (("repeat_cm", float), ("color_count", int), ("screen_count", int)):
        if payload.get(num) is not None:
            updates[num] = caster(payload[num])
    await db.design_gallery.update_one({"id": gallery_id},
                                      {"$set": updates, "$push": {"versions": entry}})
    return await get_gallery(gallery_id)


async def submit_design(gallery_id: str, actor_name: str) -> Dict[str, Any]:
    """draft → pending_approval (desainer menyatakan desain SIAP disahkan).

    Syarat kelengkapan diperiksa di SINI (kode + minimal 1 berkas), bukan hanya saat
    pengesahan: desain tanpa kode/berkas yang menumpuk di antrean penyetuju hanya
    memindahkan pekerjaan, bukan menyelesaikannya.
    """
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    if cur.get("status") != "draft":
        raise ValueError(f"Hanya desain draf yang bisa diajukan (status sekarang: "
                         f"'{cur.get('status')}').")
    if not (cur.get("code") or "").strip():
        raise ValueError("Desain wajib punya KODE sebelum diajukan "
                         "(supaya bisa dirujuk spesifikasi & proofing).")
    if not (cur.get("files") or []):
        raise ValueError("Desain wajib punya minimal 1 berkas artwork/mockup sebelum diajukan.")
    await db.design_gallery.update_one({"id": gallery_id}, {"$set": {
        "status": "pending_approval", "submitted_by": actor_name,
        "submitted_at": now_iso(), "reject_reason": "", "rejected_by": "",
        "rejected_at": "", "updated_at": now_iso()}})
    return await get_gallery(gallery_id)


async def reject_design(gallery_id: str, actor_name: str, reason: str) -> Dict[str, Any]:
    """pending_approval → draft dengan ALASAN yang tersimpan di dokumennya."""
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    if cur.get("status") != "pending_approval":
        raise ValueError(f"Hanya desain yang sedang diajukan bisa dikembalikan "
                         f"(status sekarang: '{cur.get('status')}').")
    if not (reason or "").strip():
        raise ValueError("Alasan wajib diisi supaya desainer tahu apa yang harus diperbaiki.")
    hist = list(cur.get("decision_history") or [])
    hist.append({"action": "rejected", "by": actor_name, "at": now_iso(),
                 "reason": reason.strip(), "from_status": "pending_approval",
                 "to_status": "draft"})
    await db.design_gallery.update_one({"id": gallery_id}, {"$set": {
        "status": "draft", "reject_reason": reason.strip(), "rejected_by": actor_name,
        "rejected_at": now_iso(), "decision_history": hist, "updated_at": now_iso()}})
    return await get_gallery(gallery_id)


async def approve_design(gallery_id: str, actor_name: str, note: str = "") -> Dict[str, Any]:
    """Sahkan desain agar boleh dipakai proofing/produk (status `approved`)."""
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    if cur.get("status") != "pending_approval":
        raise ValueError(
            "Desain ini belum diajukan. Desainer perlu menekan “Ajukan” dulu supaya "
            "draf yang masih dikerjakan tidak bercampur dengan yang siap disahkan."
            if cur.get("status") == "draft" else
            f"Desain berstatus '{cur.get('status')}' tidak bisa disahkan.")
    if not (cur.get("code") or "").strip():
        raise ValueError("Desain wajib punya KODE sebelum disahkan "
                         "(supaya bisa dirujuk spesifikasi & proofing).")
    if not (cur.get("files") or []):
        raise ValueError("Desain wajib punya minimal 1 berkas artwork/mockup sebelum disahkan.")
    await db.design_gallery.update_one({"id": gallery_id}, {"$set": {
        "status": "approved", "approved_by": actor_name, "approved_at": now_iso(),
        "approve_note": note, "updated_at": now_iso()}})
    return await get_gallery(gallery_id)


async def add_file(gallery_id: str, filename: str, content_type: str, data: bytes) -> Dict[str, Any]:
    cur = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not cur:
        raise ValueError("Entri galeri tidak ditemukan.")
    ct = storage.validate_upload(filename, content_type, len(data))  # raise ValueError bila invalid
    ext = storage.ext_of(filename)
    path = storage.build_path("design_gallery", ext)
    await storage.put_object(path, data, ct)
    fmeta = {
        "id": new_id("file"), "filename": filename, "path": path,
        "content_type": ct, "size": len(data), "uploaded_at": now_iso(),
    }
    await db.design_gallery.update_one(
        {"id": gallery_id},
        {"$push": {"files": fmeta}, "$set": {"updated_at": now_iso()}})
    return safe_doc(fmeta)


def _find_file(doc: Dict[str, Any], file_id: str) -> Optional[Dict[str, Any]]:
    for f in (doc.get("files") or []):
        if f.get("id") == file_id:
            return f
    return None


async def get_file_bytes(gallery_id: str, file_id: str):
    """Return (data, content_type) untuk file dalam galeri. Raise ValueError bila tak ada."""
    doc = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not doc:
        raise ValueError("Entri galeri tidak ditemukan.")
    fmeta = _find_file(doc, file_id)
    if not fmeta:
        raise ValueError("File tidak ditemukan.")
    data, ctype = await storage.get_object(fmeta["path"])  # storage MENGEMBALIKAN TUPLE
    return data, fmeta.get("content_type") or ctype


async def delete_file(gallery_id: str, file_id: str) -> Dict[str, Any]:
    doc = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not doc:
        raise ValueError("Entri galeri tidak ditemukan.")
    if not _find_file(doc, file_id):
        raise ValueError("File tidak ditemukan.")
    await db.design_gallery.update_one(
        {"id": gallery_id},
        {"$pull": {"files": {"id": file_id}}, "$set": {"updated_at": now_iso()}})
    return {"id": file_id, "deleted": True}


async def autotag(gallery_id: str) -> Dict[str, Any]:
    """Auto-tag motif via AI (Claude). GRACEFUL: bila AI nonaktif → {enabled:False}.
    Bila sukses → simpan ai_meta + gabung tag unik ke tags[]. Return ai_meta-like."""
    doc = await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0})
    if not doc:
        raise ValueError("Entri galeri tidak ditemukan.")
    files = doc.get("files") or []
    if not files:
        return {"enabled": await hr_ai_service.is_enabled(), "error": "Belum ada gambar untuk dianalisa."}
    fmeta = files[0]
    data, ctype = await storage.get_object(fmeta["path"])
    result = await hr_ai_service.autotag_image(
        data, fmeta.get("content_type") or ctype, context=f"Judul: {doc.get('title', '')}.")
    # Persist ai_meta selalu (transparansi status), gabung tags bila sukses.
    ai_meta = {
        "enabled": bool(result.get("enabled")),
        "model": result.get("model", ""),
        "tags": result.get("tags", []),
        "summary": result.get("summary", ""),
        "attributes": result.get("attributes", {}),
        "analyzed_at": result.get("analyzed_at", now_iso()),
        "error": result.get("error", ""),
    }
    set_doc: Dict[str, Any] = {"ai_meta": ai_meta, "updated_at": now_iso()}
    if result.get("enabled") and result.get("tags") and not result.get("error"):
        merged = _clean_tags(list(doc.get("tags") or []) + list(result.get("tags") or [])) 
        set_doc["tags"] = merged
    await db.design_gallery.update_one({"id": gallery_id}, {"$set": set_doc})
    updated = safe_doc(await db.design_gallery.find_one({"id": gallery_id}, {"_id": 0}))
    return {**result, "gallery": updated}
