from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Optional
from pydantic import BeforeValidator
import bcrypt
import hashlib
import re
import uuid

# SEC-2 — umur session (jam). Sliding renewal saat sisa < setengah TTL.
SESSION_TTL_HOURS = 24


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def next_doc_number(collection: str, field: str, prefix: str, width: int = 5,
                          entity_id: Optional[str] = None,
                          scheme: str = "per_entity_prefix") -> str:
    """Generate nomor dokumen berurutan (deletion-safe).

    Dua mode:
    - **Legacy/shared** (`entity_id=None` atau `scheme="shared"`): pindai nomor
      tertinggi untuk `prefix` lalu +1. Format `PREFIX-NNNNN` (kompatibel data lama).
    - **Per-entitas** (`entity_id` di-set, `scheme="per_entity_prefix"`): sequence
      atomik per (entity_id, doc_type) di koleksi `number_sequences`
      (`find_one_and_update($inc)` → anti-duplikat & hemat scan). Format
      `{CODE}/{PREFIX}NNNNN`, mis. `KSC/SO-00001`, `KANDA/SO-00001`.

    Contoh: next_doc_number("purchase_orders","po_number","PO-",entity_id="ent_ksc") -> "KSC/PO-00010".
    """
    from db import db
    if entity_id is None or entity_id == "all" or scheme == "shared":
        coll = db[collection]
        pat = re.compile(r"(\d+)\s*$")
        n = 0
        async for d in coll.find(
            {field: {"$regex": f"^{re.escape(prefix)}"}}, {"_id": 0, field: 1}
        ):
            val = d.get(field)
            if isinstance(val, str):
                m = pat.search(val)
                if m:
                    n = max(n, int(m.group(1)))
        return f"{prefix}{n + 1:0{width}d}"

    # ── Mode per-entitas: sequence atomik ──────────────────────────────────
    from pymongo import ReturnDocument
    doc_type = prefix.rstrip("-/").upper() or prefix
    code = await entity_code(entity_id)
    key = {"entity_id": entity_id, "doc_type": doc_type}
    # Inisialisasi sekali dari nomor tertinggi existing (legacy & baru) agar tak tabrakan.
    if not await db.number_sequences.find_one(key):
        seed_no = await _max_existing_number(collection, field, prefix, entity_id)
        await db.number_sequences.update_one(
            key,
            {"$setOnInsert": {**key, "prefix": prefix, "last_no": seed_no,
                              "created_at": now_iso()}},
            upsert=True,
        )
    seq = await db.number_sequences.find_one_and_update(
        key,
        {"$inc": {"last_no": 1}, "$set": {"updated_at": now_iso()}},
        return_document=ReturnDocument.AFTER,
    )
    return f"{code}/{prefix}{seq['last_no']:0{width}d}"


_ENTITY_CODE_CACHE: Dict[str, str] = {}


async def entity_code(entity_id: str) -> str:
    """Kode pendek entitas untuk nomor dokumen (doc_prefix → short_name → upper id)."""
    if entity_id in _ENTITY_CODE_CACHE:
        return _ENTITY_CODE_CACHE[entity_id]
    from db import db
    ent = await db.business_entities.find_one(
        {"id": entity_id}, {"_id": 0, "doc_prefix": 1, "short_name": 1, "code": 1}) or {}
    code = (ent.get("doc_prefix") or ent.get("code") or ent.get("short_name")
            or (entity_id or "").replace("ent_", "").upper() or "ENT")
    _ENTITY_CODE_CACHE[entity_id] = code
    return code


def invalidate_entity_code(entity_id: str = "") -> None:
    """FASE E-1 (E1.4) — buang cache kode entitas setelah entitas dibuat/diubah.

    Tanpa ini, mengubah `doc_prefix` tidak berpengaruh sampai backend di-restart:
    `entity_code()` menyimpan hasil di memori proses, sehingga dokumen baru masih
    memakai kode LAMA sementara layar sudah menampilkan kode BARU — nomor dokumen
    dan tampilan jadi tidak sinkron. Panggil dari router entities (create/update/
    arsip/aktifkan-kembali). Tanpa argumen = kosongkan seluruh cache.
    """
    if entity_id:
        _ENTITY_CODE_CACHE.pop(entity_id, None)
    else:
        _ENTITY_CODE_CACHE.clear()


async def _max_existing_number(collection: str, field: str, prefix: str,
                               entity_id: str, scope_field: str = "entity_id") -> int:
    """Nomor seri tertinggi existing utk (entitas, prefix) — match legacy & baru."""
    from db import db
    pat = re.compile(r"(\d+)\s*$")
    n = 0
    q = {field: {"$regex": re.escape(prefix)}, scope_field: entity_id}
    async for d in db[collection].find(q, {"_id": 0, field: 1}):
        val = d.get(field)
        if isinstance(val, str):
            m = pat.search(val)
            if m:
                n = max(n, int(m.group(1)))
    return n


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ── Fase A · PS-15 / R5 — input desimal seragam ───────────────────────────────
# Aturan tunggal (KN_18 §0 R5): qty maksimum 3 desimal, uang 2 desimal, dan
# input pengguna WAJIB menerima koma-desimal Indonesia ("10,5") maupun titik
# ("10.5") serta pemisah ribuan ("1.234,5" / "1,234.5"). Pembulatan HANYA di
# titik simpan akhir. Dipakai lewat tipe `QtyDecimal` / `MoneyDecimal` di schema
# agar tidak ada parsing ad-hoc di router (R4-style single path).
QTY_PLACES = 3
MONEY_PLACES = 2


def parse_decimal(value: Any, places: int = QTY_PLACES, default: float = 0.0) -> float:
    """Ubah input pengguna menjadi float desimal (mendukung koma-desimal).

    Contoh: `"10,5"` → 10.5 · `"1.234,56"` → 1234.56 · `"1,234.56"` → 1234.56
    · `" 12 "` → 12.0 · `None`/`""` → `default`.
    Melempar `ValueError` bila jelas bukan angka (mis. `"abc"`).
    """
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError("Nilai angka tidak boleh boolean")
    if isinstance(value, (int, float)):
        return round(float(value), places)
    text = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if not text:
        return default
    text = re.sub(r"(?i)^rp\.?", "", text).strip()
    neg = text.startswith("-")
    text = text.lstrip("+-")
    has_dot, has_comma = "." in text, "," in text
    if has_dot and has_comma:
        # pemisah desimal = tanda yang muncul paling akhir
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        # satu koma → desimal; beberapa koma → ribuan
        text = text.replace(",", ".") if text.count(",") == 1 else text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    if not re.fullmatch(r"\d*\.?\d*", text) or text in (".", ""):
        raise ValueError(f"'{value}' bukan angka yang sah")
    out = round(float(text), places)
    return -out if neg else out


def _qty_validator(value: Any) -> Any:
    try:
        return parse_decimal(value, QTY_PLACES)
    except ValueError as exc:
        raise ValueError(str(exc))


def _money_validator(value: Any) -> Any:
    try:
        return parse_decimal(value, MONEY_PLACES)
    except ValueError as exc:
        raise ValueError(str(exc))


QtyDecimal = Annotated[float, BeforeValidator(_qty_validator)]
MoneyDecimal = Annotated[float, BeforeValidator(_money_validator)]
OptQtyDecimal = Annotated[Optional[float], BeforeValidator(
    lambda v: None if v in (None, "") else _qty_validator(v))]
OptMoneyDecimal = Annotated[Optional[float], BeforeValidator(
    lambda v: None if v in (None, "") else _money_validator(v))]


def rupiah(value: Any) -> str:
    """Format nominal ke gaya Indonesia: `rupiah(5131200)` → `"Rp 5.131.200"`.

    KENAPA HELPER BERSAMA (temuan penutupan FASE G-9):
      Pesan yang dibaca pengguna dibangun di 40+ berkas dengan tiga gaya berbeda:
      `f"Rp {x:,.0f}"` (gaya INGGRIS → `Rp 5,131,200`), `f"Rp {x:,.0f}".replace(",", ".")`,
      dan helper `_rp()` lokal yang disalin ulang di beberapa service. Gaya Inggris itu
      tidak pernah kelihatan selama bug **KN-G9-ERR-SILENT** masih hidup (bilah error
      tidak dirender sama sekali). Begitu error ditampilkan, pengguna langsung melihat
      "Σ alokasi Rp 999,000,000" di antarmuka yang seluruhnya Bahasa Indonesia.
      Dijaga oleh `scripts/audit_i18n_id.py` aturan [7] (angka gaya Inggris).

    Negatif ditulis dengan tanda minus di depan: `-Rp 1.000`.
    """
    try:
        n = round(float(value or 0))
    except (TypeError, ValueError):
        return "Rp 0"
    sign = "-" if n < 0 else ""
    return f"{sign}Rp {abs(n):,}".replace(",", ".")


# ═════════════════════════════════════════════════════════════════════════════
# FASE U — DUA SATUAN (jumlah roll + ukuran) dalam SATU kalimat
# ═════════════════════════════════════════════════════════════════════════════
def qty_num_id(value: Any, places: int = 2) -> str:
    """Angka gaya Indonesia: `540.5` → `"540,5"` · `12.0` → `"12"`.

    Dijaga `scripts/audit_i18n_id.py` aturan [7]: angka gaya Inggris (`540.5`) di
    antarmuka Bahasa Indonesia adalah cacat yang tak pernah memicu galat.
    """
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    s = f"{n:,.{places}f}"
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s or "0"


def qty_dual(rolls: Any, measure: Any, unit: str = "", *, places: int = 2) -> str:
    """Satu kalimat untuk DUA satuan: `qty_dual(12, 540.5, "yard")` →
    `"12 roll · 540,5 yard"`.

    KENAPA SATU HELPER (permintaan pemilik: *"catat roll dan yard/kg dan panel — jadi
    ada 2 satuan yang ditulis... dan ini seharusnya sudah ada di semuanya"*):
    kalimat ini muncul di **enam tampilan** untuk satu fakta (layar, PDF surat jalan,
    PDF faktur, CSV, papan PO, kartu stok). Kalau tiap tempat merangkainya sendiri,
    satu perubahan aturan (mis. dokumen lama tanpa jumlah roll) harus dikejar di enam
    tempat, dan yang tertinggal akan **berbohong dengan tenang** — persis kelas bug
    "tiga angka untuk satu pertanyaan" yang ditutup di FASE F-6.

    Aturan yang dipaksakan di sini (dan diuji POC U4):
      * `rolls` kosong/None (dokumen LAMA) → jumlah roll TIDAK ditulis "0 roll"
        (menyesatkan: 0 roll berarti "tidak ada gulungan"), melainkan **dihilangkan**;
        bila ukurannya pun tak ada, hasilnya "—".
      * `rolls = 0` yang memang disengaja tetap ditulis `0 roll` — bedanya dengan
        "belum diisi" dijaga di lapisan data (`None` vs `0`), bukan di layar.
    """
    bagian = []
    if rolls is not None and str(rolls) != "":
        try:
            bagian.append(f"{int(float(rolls))} roll")
        except (TypeError, ValueError):
            pass
    if measure is not None and str(measure) != "":
        try:
            if float(measure) != 0 or not bagian:
                bagian.append(f"{qty_num_id(measure, places)} {unit}".strip())
        except (TypeError, ValueError):
            pass
    return " · ".join(bagian) if bagian else "—"



def timeline_entry(event: str, label: str, actor: str = "", note: str = "") -> Dict[str, Any]:
    """Entri riwayat/timeline standar (dipakai PO approval history, dll)."""
    return {"event": event, "label": label, "actor": actor or "Sistem",
            "at": now_iso(), "note": note or ""}


def _coerce(value: Any) -> Any:
    """Recursively make a MongoDB document JSON-serializable."""
    try:
        from bson import ObjectId
        if isinstance(value, ObjectId):
            return str(value)
    except ImportError:
        pass
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [_coerce(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # datetime, etc.
    try:
        return str(value)
    except Exception:
        return None


def safe_doc(doc: Optional[Any]) -> Optional[Any]:
    """Recursively remove _id fields and convert ObjectId to str."""
    if doc is None:
        return None
    return _coerce(doc)


def hash_password(password: str) -> str:
    """SEC-1 — bcrypt (salt otomatis per-hash)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def legacy_hash_password(password: str) -> str:
    """Skema lama SHA256+pepper — hanya untuk verifikasi migrasi (rehash saat login)."""
    return hashlib.sha256(f"kain-nusantara::{password}".encode()).hexdigest()


def is_legacy_hash(hashed: str) -> bool:
    return not (hashed or "").startswith("$2")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    if is_legacy_hash(hashed):
        return hashed == legacy_hash_password(plain)
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ── S-10: redaksi field biaya/HPP untuk role non-cost ────────────────────────
COST_FIELDS = {
    "unit_cost", "base_unit_cost", "harga_pokok", "landed_cost_total",
    "landed_cost_refs", "cogs_amount", "cogs", "wac", "margin", "margin_pct",
}
COST_SAFE_ROLES = {"admin", "manager"}


def strip_cost_fields(data: Any, role: Optional[str]) -> Any:
    """S-10 — hapus field biaya (HPP/margin) dari respons bila role bukan admin/manager."""
    if role in COST_SAFE_ROLES:
        return data
    if isinstance(data, dict):
        return {k: strip_cost_fields(v, role) for k, v in data.items() if k not in COST_FIELDS}
    if isinstance(data, list):
        return [strip_cost_fields(v, role) for v in data]
    return data


# ── Multi-Entity (Fase 0) ─────────────────────────────────────────────────────
# Entitas legal utama grup. Dipakai sebagai default entity_id untuk data lama
# (backfill) & transaksi baru bila konteks entitas belum dipilih.
DEFAULT_ENTITY_ID = "ent_ksc"  # PT Kain Suka Cita
