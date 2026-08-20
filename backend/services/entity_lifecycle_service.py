"""FASE E-1 — SIKLUS HIDUP BADAN USAHA (satu pintu untuk semua pagar).

Mengapa berkas ini ada: sebelum FASE E-1 aturan entitas tersebar di router
(`routers/entities.py` memvalidasi sendiri, `entity_provisioning_service`
memvalidasi versi lain) sehingga `PATCH` bisa menembus aturan yang ditegakkan
`POST`. Semua pagar sekarang tinggal DI SINI dan dipanggil dari satu tempat.

Isi:
  * E1.2  validasi + keunikan `short_name` / `doc_prefix` (case-insensitive)
  * E1.3  **kunci prefix** — `doc_prefix` tidak boleh diubah bila entitas sudah
          menerbitkan dokumen; pesan menyebut dokumen PERTAMA yang terbit
  * E1.6  pagar deaktivasi — hitung dampak (pengguna aktif, dokumen terbuka,
          saldo, periode belum tutup) → 409 berisi rincian; bila dipaksa
          (admin + alasan) status menjadi `archived` → **kunci-tulis**
  * E1.8  bentuk data entitas SERAGAM dengan `/auth/context`
"""
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from db import db
from core_utils import invalidate_entity_code, now_iso, safe_doc
from services.entity_context_service import ENTITY_DEFAULTS, is_pkp

STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"
# `inactive` = status lama (pra-E1) dengan MAKNA SAMA seperti archived: tidak boleh
# menerima transaksi baru. Dipertahankan supaya data lama tidak perlu dimigrasi keras.
STATUS_INACTIVE = "inactive"
WRITE_LOCKED_STATUSES = {STATUS_ARCHIVED, STATUS_INACTIVE}

# Field yang boleh diubah lewat PATCH (satu daftar, dipakai router).
EDITABLE_FIELDS = [
    "legal_name", "short_name", "type", "npwp", "address", "city",
    "default_tax_mode", "doc_prefix", "logo_url",
    "currency", "parent_entity_id", "is_group", "coa_template",
    "fiscal_year_start", "incentive_payer", "numbering_scheme",
    "owner_name", "business_label", "phone", "email",
]

# (koleksi, field nomor, label manusiawi) — sumber "entitas sudah menerbitkan dokumen".
# Dipakai kunci prefix (E1.3) dan hitungan dampak deaktivasi (E1.6).
DOC_SOURCES: List[Tuple[str, str, str]] = [
    ("sales_orders", "number", "Pesanan penjualan"),
    ("purchase_orders", "po_number", "Pesanan pembelian"),
    ("tax_invoices", "number", "Faktur pajak keluaran"),
    ("tax_invoices_in", "number", "Faktur pajak masukan"),
    ("ar_receipts", "number", "Kwitansi penerimaan"),
    ("journal_entries", "number", "Jurnal buku besar"),
    ("interco_transactions", "number", "Transaksi antar-PT"),
    ("interco_returns", "number", "Retur antar-PT"),
    ("credit_notes", "number", "Nota kredit"),
    ("sales_returns", "number", "Retur penjualan"),
    ("purchase_returns", "number", "Retur pembelian"),
    ("contra_bons", "number", "Kontrabon"),
    ("penalties", "number", "Nota denda"),
    ("payment_plans", "number", "Rencana pembayaran"),
    ("cash_transactions", "number", "Transaksi kas"),
    ("warehouse_transfers", "code", "Transfer gudang"),
    ("vendor_bills", "bill_number", "Tagihan supplier"),
]

# Status yang dianggap SUDAH SELESAI — sisanya dihitung "dokumen terbuka".
CLOSED_STATUSES = {
    "done", "completed", "closed", "cancelled", "canceled", "rejected",
    "paid", "settled", "void", "voided", "archived", "posted", "recorded",
    "normal", "issued_paid", "finished",
}


# ─── Pembacaan dasar ────────────────────────────────────────────────
def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


async def get_entity_or_404(entity_id: str) -> Dict[str, Any]:
    entity = safe_doc(await db.business_entities.find_one({"id": entity_id}, {"_id": 0}))
    if not entity:
        raise HTTPException(status_code=404, detail="Badan usaha tidak ditemukan")
    return entity


def is_write_locked(entity: Dict[str, Any]) -> bool:
    return (entity or {}).get("status") in WRITE_LOCKED_STATUSES


# ─── E1.8 — bentuk data SERAGAM dengan /auth/context ────────────────────────
def uniform_entity(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Bentuk tunggal entitas untuk SEMUA konsumen (switcher, daftar, detail).

    Dulu `/api/entities` mengembalikan dokumen mentah sementara `/auth/context`
    mengembalikan bentuk ringkas — sehingga FE punya dua tambalan label
    (`utils/entityLabel.js`). Satu bentuk = satu sumber kebenaran.
    """
    e = dict(entity or {})
    for key, val in ENTITY_DEFAULTS.items():
        e.setdefault(key, val)
    return {
        "id": e.get("id", ""),
        "code": e.get("doc_prefix") or e.get("short_name") or e.get("id", ""),
        "name": e.get("legal_name") or e.get("short_name") or e.get("id", ""),
        "short_name": e.get("short_name", ""),
        "legal_name": e.get("legal_name", ""),
        "type": e.get("type", ""),
        "is_pkp": is_pkp(e),
        "currency": e.get("currency", "IDR"),
        "status": e.get("status", STATUS_ACTIVE),
        "doc_prefix": e.get("doc_prefix", ""),
        "logo_url": e.get("logo_url", ""),
        # tambahan (superset) — dibutuhkan layar Entitas & Akses
        "npwp": e.get("npwp", ""),
        "address": e.get("address", ""),
        "city": e.get("city", ""),
        "phone": e.get("phone", ""),
        "email": e.get("email", ""),
        "owner_name": e.get("owner_name", ""),
        "business_label": e.get("business_label", ""),
        "default_tax_mode": e.get("default_tax_mode", ""),
        "fiscal_year_start": e.get("fiscal_year_start", ""),
        "coa_template": e.get("coa_template", ""),
        "incentive_payer": e.get("incentive_payer", ""),
        "numbering_scheme": e.get("numbering_scheme", ""),
        "parent_entity_id": e.get("parent_entity_id", ""),
        "is_group": bool(e.get("is_group", False)),
        "write_locked": is_write_locked(e),
        "created_at": e.get("created_at", ""),
        "updated_at": e.get("updated_at", ""),
    }


# ─── E1.3 — kunci prefix dokumen ─────────────────────────────────────
async def first_issued_document(entity_id: str) -> Optional[Dict[str, Any]]:
    """Dokumen PERTAMA yang pernah diterbitkan entitas (untuk pesan kunci prefix).

    Dicari lintas koleksi lalu diambil yang `created_at` paling awal. Sengaja
    menyebut dokumen konkret supaya pesan galat bisa ditindaklanjuti pengguna
    ("kenapa saya tidak boleh ganti kode?" → "karena KSC/SO-00001 sudah terbit").
    """
    best: Optional[Dict[str, Any]] = None
    for coll, field, label in DOC_SOURCES:
        row = await db[coll].find_one(
            {"entity_id": entity_id, field: {"$exists": True, "$ne": ""}},
            {"_id": 0, field: 1, "created_at": 1},
            sort=[("created_at", 1)],
        )
        if not row:
            continue
        cand = {"collection": coll, "label": label,
                "number": row.get(field) or "", "created_at": row.get("created_at") or ""}
        if best is None or str(cand["created_at"]) < str(best["created_at"]):
            best = cand
    if best:
        return best
    # Cadangan: sequence nomor sudah pernah dipakai walau dokumennya terhapus.
    seq = await db.number_sequences.find_one(
        {"entity_id": entity_id, "last_no": {"$gt": 0}}, {"_id": 0})
    if seq:
        return {"collection": "number_sequences", "label": "Nomor dokumen",
                "number": f"{seq.get('prefix', '')}{int(seq.get('last_no', 0)):05d}",
                "created_at": seq.get("created_at", "")}
    return None


async def prefix_lock_info(entity_id: str) -> Dict[str, Any]:
    doc = await first_issued_document(entity_id)
    return {
        "locked": bool(doc),
        "first_document": doc,
        "reason": (
            f"Kode dokumen tidak bisa diubah karena badan usaha ini sudah menerbitkan "
            f"{(doc or {}).get('label', 'dokumen').lower()} “{(doc or {}).get('number', '')}”. "
            "Mengubah kode akan membuat nomor dokumen lama dan baru tidak bisa "
            "dibedakan lagi." if doc else ""
        ),
    }


async def assert_prefix_change_allowed(entity_id: str, current_prefix: str,
                                       new_prefix: str) -> None:
    if _norm(new_prefix) == _norm(current_prefix):
        return
    info = await prefix_lock_info(entity_id)
    if info["locked"]:
        raise HTTPException(status_code=409, detail=info["reason"])


# ─── E1.2 — keunikan (case-insensitive) ────────────────────────────────
async def assert_unique(field: str, value: str, exclude_id: str = "") -> None:
    """Keunikan tanpa peduli besar-kecil huruf (mis. “KSC” vs “ksc”)."""
    val = (value or "").strip()
    if not val:
        return
    label = {"short_name": "Nama singkat", "doc_prefix": "Kode dokumen"}.get(field, field)
    async for row in db.business_entities.find({}, {"_id": 0, "id": 1, field: 1,
                                                    "legal_name": 1}):
        if row.get("id") == exclude_id:
            continue
        if _norm(row.get(field)) == _norm(val):
            raise HTTPException(
                status_code=409,
                detail=f"{label} “{val}” sudah dipakai badan usaha “"
                       f"{row.get('legal_name') or row.get('id')}”. Pilih yang lain.")


# ─── E1.6 — dampak deaktivasi ───────────────────────────────────────
async def _open_documents(entity_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for coll, field, label in DOC_SOURCES:
        rows = await db[coll].find(
            {"entity_id": entity_id}, {"_id": 0, field: 1, "status": 1}).to_list(2000)
        open_rows = [r for r in rows if _norm(r.get("status")) not in CLOSED_STATUSES]
        if open_rows:
            out.append({
                "collection": coll, "label": label, "count": len(open_rows),
                "examples": [r.get(field) for r in open_rows[:3] if r.get(field)],
            })
    return out


async def _open_balances(entity_id: str) -> List[Dict[str, Any]]:
    """Saldo yang masih hidup: piutang belum lunas, saldo antar-PT, stok dimiliki."""
    out: List[Dict[str, Any]] = []
    ar = await db.sales_orders.aggregate([
        {"$match": {"entity_id": entity_id}},
        {"$group": {"_id": None,
                    "total": {"$sum": {"$ifNull": ["$grand_total", 0]}},
                    "paid": {"$sum": {"$ifNull": ["$paid_total", 0]}}}},
    ]).to_list(1)
    outstanding = round(float((ar[0]["total"] - ar[0]["paid"]) if ar else 0), 2)
    if outstanding > 0.01:
        out.append({"key": "piutang", "label": "Piutang pelanggan belum lunas",
                    "amount": outstanding})
    ic = await db.interco_accounts.find({"entity_id": entity_id}, {"_id": 0}).to_list(50)
    ic_total = round(sum(abs(float(r.get("balance") or 0)) for r in ic), 2)
    if ic_total > 0.01:
        out.append({"key": "antar_pt", "label": "Saldo antar badan usaha (IC-AR/IC-AP)",
                    "amount": ic_total})
    rolls = await db.inventory_rolls.count_documents(
        {"owner_entity_id": entity_id, "status": {"$nin": ["consumed", "sold", "scrapped"]}})
    if rolls:
        out.append({"key": "stok", "label": "Roll stok masih dimiliki", "amount": rolls,
                    "unit": "roll"})
    return out


async def _open_periods(entity_id: str) -> Dict[str, Any]:
    """Periode belum ditutup = ada jurnal setelah penutupan terakhir."""
    last = await db.period_closings.find_one(
        {"entity_id": entity_id, "status": {"$ne": "reopened"}},
        {"_id": 0, "period_end": 1, "period_label": 1}, sort=[("period_end", -1)])
    q: Dict[str, Any] = {"entity_id": entity_id}
    if last and last.get("period_end"):
        q["date"] = {"$gt": last["period_end"]}
    count = await db.journal_entries.count_documents(q)
    return {"journals_after_last_closing": count,
            "last_closing": (last or {}).get("period_label", "")}


async def deactivation_impact(entity_id: str) -> Dict[str, Any]:
    """Pratinjau dampak SEBELUM entitas diarsipkan (dipakai UI & endpoint DELETE)."""
    entity = await get_entity_or_404(entity_id)
    users = await db.users.find(
        {"status": "active",
         "$or": [{"home_entity_id": entity_id}, {"allowed_entity_ids": entity_id}]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "home_entity_id": 1}).to_list(200)
    home_users = [u for u in users if u.get("home_entity_id") == entity_id]
    open_docs = await _open_documents(entity_id)
    balances = await _open_balances(entity_id)
    periods = await _open_periods(entity_id)
    issued = await first_issued_document(entity_id)

    blockers: List[str] = []
    if home_users:
        blockers.append(
            f"{len(home_users)} pengguna masih ber-badan-usaha utama di sini — "
            "pindahkan dulu (" + ", ".join(u.get("name", "?") for u in home_users[:5]) + ")")
    total_open = sum(d["count"] for d in open_docs)
    if total_open:
        blockers.append(f"{total_open} dokumen masih terbuka — selesaikan atau batalkan dulu")
    if balances:
        blockers.append(
            "Masih ada saldo hidup: " + ", ".join(b["label"].lower() for b in balances))
    if periods["journals_after_last_closing"]:
        blockers.append(
            f"{periods['journals_after_last_closing']} jurnal belum masuk periode tertutup — "
            "lakukan tutup buku dulu")
    return {
        "entity_id": entity_id,
        "entity_name": entity.get("legal_name") or entity.get("short_name") or entity_id,
        "status": entity.get("status", STATUS_ACTIVE),
        "active_users": users,
        "home_users": home_users,
        "open_documents": open_docs,
        "open_documents_total": total_open,
        "balances": balances,
        "periods": periods,
        "has_issued_documents": bool(issued),
        "first_document": issued,
        "blockers": blockers,
        "can_archive": not blockers,
        "force_requires": ["peran admin", "alasan tertulis"],
    }


async def archive_entity(entity_id: str, actor: Dict[str, Any], reason: str = "",
                         force: bool = False) -> Dict[str, Any]:
    """Arsipkan entitas. Menolak (409) bila masih terpakai, kecuali dipaksa admin."""
    entity = await get_entity_or_404(entity_id)
    if is_write_locked(entity):
        raise HTTPException(status_code=409,
                            detail="Badan usaha ini sudah diarsipkan sebelumnya.")
    total_active = await db.business_entities.count_documents({"status": STATUS_ACTIVE})
    if total_active <= 1:
        raise HTTPException(
            status_code=409,
            detail="Ini satu-satunya badan usaha aktif. Buat badan usaha lain dulu "
                   "sebelum mengarsipkan yang ini.")
    impact = await deactivation_impact(entity_id)
    if impact["blockers"] and not force:
        raise HTTPException(status_code=409, detail={
            "message": "Badan usaha masih terpakai — belum bisa diarsipkan.",
            "blockers": impact["blockers"],
            "impact": impact,
            "hint": "Setelah semuanya beres, ulangi. Bila memang harus dipaksa, kirim "
                    "force=true beserta alasan (hanya admin).",
        })
    if force:
        if (actor or {}).get("role") != "admin":
            raise HTTPException(status_code=403,
                                detail="Hanya admin yang boleh memaksa pengarsipan.")
        if not (reason or "").strip():
            raise HTTPException(status_code=400,
                                detail="Alasan wajib diisi saat memaksa pengarsipan.")
    patch = {"status": STATUS_ARCHIVED, "archived_at": now_iso(),
             "archived_by": (actor or {}).get("name", ""),
             "archive_reason": (reason or "").strip(),
             "archive_forced": bool(force), "updated_at": now_iso()}
    await db.business_entities.update_one({"id": entity_id}, {"$set": patch})
    # Cabut sesi pengguna yang badan usaha utamanya diarsipkan (tidak boleh masuk lagi).
    home_ids = [u["id"] for u in impact["home_users"]]
    revoked = 0
    if home_ids:
        res = await db.sessions.delete_many({"user_id": {"$in": home_ids}})
        revoked = res.deleted_count
    invalidate_entity_code(entity_id)
    invalidate_status_cache()
    return {**(await get_entity_or_404(entity_id)), "impact": impact,
            "sessions_revoked": revoked}


async def reactivate_entity(entity_id: str, actor: Dict[str, Any]) -> Dict[str, Any]:
    entity = await get_entity_or_404(entity_id)
    if entity.get("status") == STATUS_ACTIVE:
        raise HTTPException(status_code=409, detail="Badan usaha ini sudah aktif.")
    await db.business_entities.update_one(
        {"id": entity_id},
        {"$set": {"status": STATUS_ACTIVE, "reactivated_at": now_iso(),
                  "reactivated_by": (actor or {}).get("name", ""), "updated_at": now_iso()},
         "$unset": {"archived_at": "", "archive_reason": "", "archive_forced": ""}})
    invalidate_entity_code(entity_id)
    invalidate_status_cache()
    return await get_entity_or_404(entity_id)


# ─── E1.6 — kunci-tulis entitas terarsip ───────────────────────────────
async def assert_entity_writable(entity_id: str, action: str = "membuat data") -> None:
    """Tolak TULIS ke entitas terarsip (data lama tetap boleh dibaca admin)."""
    if not entity_id or entity_id == "all":
        return
    entity = safe_doc(await db.business_entities.find_one(
        {"id": entity_id}, {"_id": 0, "status": 1, "legal_name": 1, "short_name": 1}))
    if entity and is_write_locked(entity):
        name = entity.get("legal_name") or entity.get("short_name") or entity_id
        raise HTTPException(
            status_code=409,
            detail=f"“{name}” sudah diarsipkan sehingga tidak bisa lagi menerima "
                   f"transaksi baru. Tidak bisa {action}. Aktifkan kembali badan "
                   "usaha ini bila memang masih dipakai.")


# ─── Cache status (dipakai penjaga tulis di setiap request) ──────────────────
_STATUS_CACHE: Dict[str, Dict[str, str]] = {}
_STATUS_CACHE_AT: Dict[str, float] = {"t": 0.0}
STATUS_CACHE_TTL_SECONDS = 20.0


def invalidate_status_cache() -> None:
    _STATUS_CACHE.clear()
    _STATUS_CACHE_AT["t"] = 0.0


async def entity_status_map() -> Dict[str, Dict[str, str]]:
    """Peta id → {status, name} dengan cache pendek.

    Penjaga kunci-tulis dipanggil pada SETIAP request yang mengubah data; tanpa
    cache itu berarti satu query Mongo tambahan per request hanya untuk membaca
    status yang hampir tidak pernah berubah.
    """
    now = time.monotonic()
    if _STATUS_CACHE and (now - _STATUS_CACHE_AT["t"]) < STATUS_CACHE_TTL_SECONDS:
        return _STATUS_CACHE
    rows = await db.business_entities.find(
        {}, {"_id": 0, "id": 1, "status": 1, "legal_name": 1, "short_name": 1}).to_list(500)
    _STATUS_CACHE.clear()
    for r in rows:
        _STATUS_CACHE[r["id"]] = {
            "status": r.get("status", STATUS_ACTIVE),
            "name": r.get("legal_name") or r.get("short_name") or r["id"],
        }
    _STATUS_CACHE_AT["t"] = now
    return _STATUS_CACHE


async def assert_entity_writable_cached(entity_id: str) -> None:
    """E1.6 — kunci-tulis badan usaha terarsip, dipasang di choke point auth.

    Dipanggil `dependencies.current_user()` untuk metode POST/PUT/PATCH/DELETE.
    Satu tempat = tidak ada endpoint yang lupa dipasangi pagar.
    """
    if not entity_id or entity_id == "all":
        return
    info = (await entity_status_map()).get(entity_id)
    if info and info["status"] in WRITE_LOCKED_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"“{info['name']}” sudah diarsipkan sehingga tidak bisa lagi "
                   "menerima transaksi baru. Data lama tetap bisa dibaca. Aktifkan "
                   "kembali badan usaha ini bila memang masih dipakai.")


# ─── E1.10 — PAGAR TULIS LINTAS BADAN USAHA (dipasang di choke point auth) ────
# Temuan POC E-1: FASE E-0 hanya menyapu endpoint BACA. Di sisi TULIS masih ada
# lubang nyata — `POST /api/customers`, `POST /api/sales-orders`,
# `POST /api/inventory/initial-stock`, kontrak blanket, retur beli, kwitansi, dan
# jurnal manual memakai `payload.entity_id` MENTAH lalu jatuh ke `DEFAULT_ENTITY_ID`.
# Artinya sales CV Kanda Suka bisa MENANAM dokumen di buku PT Kain Suka Cita hanya
# dengan mengirim satu field. Memasang penjaga di 11 titik satu-satu mudah terlewat
# saat endpoint baru lahir, jadi penjaganya dipasang di SATU tempat yang dilewati
# semua endpoint terautentikasi.
#
# Sengaja HANYA field kepemilikan dokumen. `source_entity_id`/`dest_entity_id`/
# `seller_entity_id`/`buyer_entity_id` (antar-PT) dan `home_entity_id`/
# `allowed_entity_ids` (penugasan akun) memang MENYEBUT badan usaha lain secara sah,
# jadi tidak boleh diblokir di sini.
BODY_ENTITY_FIELDS = ("entity_id", "owner_entity_id")


def _collect_body_entities(body: Any) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if not isinstance(body, dict):
        return out
    for fld in BODY_ENTITY_FIELDS:
        val = body.get(fld)
        if isinstance(val, str) and val.strip():
            out.append((fld, val.strip()))
    inner = body.get("data")          # bentuk GenericPatch: {"data": {...}}
    if isinstance(inner, dict):
        for fld in BODY_ENTITY_FIELDS:
            val = inner.get(fld)
            if isinstance(val, str) and val.strip():
                out.append((f"data.{fld}", val.strip()))
    return out


async def writable_entity_ids(user: Dict[str, Any]) -> set:
    """Badan usaha yang boleh DITULISI user ini (aktif saja)."""
    from services.entity_context_service import CROSS_ENTITY_ROLES
    smap = await entity_status_map()
    active = {eid for eid, info in smap.items()
              if info["status"] not in WRITE_LOCKED_STATUSES}
    if user.get("role") in CROSS_ENTITY_ROLES:
        return active | {"all"}      # 'all' = baris global (mis. aturan approval)
    home = user.get("home_entity_id") or ""
    stored = user.get("allowed_entity_ids") or ([home] if home else [])
    return {e for e in stored if e in active}


async def assert_body_entity_allowed(request: Any, user: Dict[str, Any]) -> None:
    ctype = (request.headers.get("content-type") or "").lower()
    if "json" not in ctype:
        return
    try:
        raw = await request.body()      # sudah di-cache Starlette; aman dibaca lagi
        if not raw:
            return
        body = json.loads(raw)
    except Exception:  # noqa: BLE001 — bukan JSON / kosong: bukan urusan penjaga ini
        return
    found = _collect_body_entities(body)
    if not found:
        return
    allowed = await writable_entity_ids(user)
    smap = await entity_status_map()
    for field, val in found:
        if val in allowed:
            continue
        info = smap.get(val)
        if not info:
            detail = (f"Badan usaha “{val}” tidak ada, jadi data tidak bisa disimpan "
                      f"ke sana (field {field}).")
        elif info["status"] in WRITE_LOCKED_STATUSES:
            detail = (f"“{info['name']}” sudah diarsipkan sehingga tidak bisa lagi "
                      f"menerima data baru (field {field}).")
        else:
            detail = (f"Anda tidak berwenang menyimpan data ke “{info['name']}”. "
                      "Data hanya boleh dibuat di badan usaha tempat Anda ditugaskan.")
        raise HTTPException(status_code=403, detail=detail)


async def readable_entity_ids(user: Dict[str, Any]) -> List[str]:
    """Badan usaha yang boleh DIBACA user (aktif saja) — urutan stabil.

    Sama aturannya dengan `entity_scope.entity_ctx` tetapi tanpa impor balik
    (entity_scope mengimpor dependencies, jadi tidak boleh sebaliknya).
    """
    from services.entity_context_service import CROSS_ENTITY_ROLES
    smap = await entity_status_map()
    active = [eid for eid, info in smap.items()
              if info["status"] not in WRITE_LOCKED_STATUSES]
    home = user.get("home_entity_id") or ""
    if user.get("role") in CROSS_ENTITY_ROLES:
        return active or ([home] if home else [])
    stored = user.get("allowed_entity_ids") or ([home] if home else [])
    out = [e for e in stored if e in active]
    return out or ([home] if home else [])


async def entity_denied_message(requested: str, allowed: List[str]) -> str:
    """Pesan 403 yang MENJELASKAN — bukan sekadar “tidak berwenang”.

    Tiga sebab berbeda perlu tiga kalimat berbeda supaya pengguna tahu harus apa:
    badan usahanya tidak ada, sudah diarsipkan, atau memang bukan penugasannya.
    """
    info = (await entity_status_map()).get(requested)
    if not info:
        return (f"Badan usaha “{requested}” tidak ada (mungkin sudah dihapus). "
                "Pilih badan usaha lain di pemilih entitas.")
    if info["status"] in WRITE_LOCKED_STATUSES:
        return (f"“{info['name']}” sudah diarsipkan sehingga tidak bisa dipakai sebagai "
                "konteks kerja. Pilih badan usaha yang masih aktif.")
    return (f"Anda tidak ditugaskan di “{info['name']}”. Hubungi admin bila memang perlu "
            "akses ke badan usaha ini.")


async def assert_requested_entity_allowed(request: Any, user: Dict[str, Any]) -> None:
    """FASE E-1 (E1.5) — header `X-Entity-Id` yang tidak sah DITOLAK di choke point.

    Kenapa di sini dan bukan hanya di `entity_scope.entity_ctx`: banyak endpoint
    (mis. `POST /api/customers`) tidak memakai `entity_ctx`. Tanpa penjaga ini,
    permintaan yang menyebut badan usaha lain dilayani **diam-diam atas nama badan
    usaha HOME** — layar bilang “Kanda”, datanya mendarat di KSC. Justru inilah
    kelas cacat yang paling sulit disadari pengguna.

    `all` (mode gabungan) sengaja TIDAK ditolak untuk peran non-lintas: nilainya
    tersimpan di localStorage peramban dan artinya “tidak ada preferensi”, bukan
    upaya menembus batas. Konteks efektifnya tetap badan usaha sendiri.
    """
    requested = (request.headers.get("X-Entity-Id") or "").strip()
    if not requested or requested == "all":
        return
    allowed = await readable_entity_ids(user)
    if requested not in allowed:
        raise HTTPException(status_code=403,
                            detail=await entity_denied_message(requested, allowed))
