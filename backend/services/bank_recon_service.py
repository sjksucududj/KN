"""FASE G-8 — REKONSILIASI BANK OTOMATIS (skor berbobot · split · aturan · titipan).

Rekonsiliasi mutasi bank (baris statement yang diimpor) terhadap `cash_transactions`
(SSOT kas). **Append-only & GL-safe:** rekonsiliasi TIDAK mengubah jurnal terposting —
ia hanya MENAUTKAN statement line ↔ cash_transaction. Satu-satunya jalur yang
menerbitkan jurnal baru adalah **titipan dana** (uang masuk yang belum teridentifikasi)
dan **alokasinya**, karena di sana memang ada uang nyata yang harus diakui.

KOLEKSI
-------
`bank_statement_lines`  (SCOPED `entity_id`)
    { id, bank_account_id, entity_id, stmt_date, amount(>0), direction in|out,
      description, counterparty, desc_key, ref, external_id, balance,
      status unmatched|matched|ignored|holding,
      match_kind ""|1:1|1:N|N:1, matched_txn_id, matched_txn_ids[],
      allocations[{txn_id, amount}], score, score_explain[], suggestions[],
      holding{cash_txn_id, je_id, at, by, note}, holding_allocated[], holding_remaining,
      import_batch, format_id, created_at, updated_at }
`bank_statement_formats` (SCOPED) — template parser per bank (`bsf_`).
`bank_match_rules`       (SCOPED) — aturan hasil pembelajaran (`bmr_`).

MENGAPA SKOR BERBOBOT
---------------------
Skor lama hanya 2 faktor (`ref cocok`, `tanggal terdekat`) tanpa penjelasan, sehingga
user tidak bisa menilai apakah sistem menebak benar. Kini setiap pasangan punya
`explain[]` — daftar alasan berpoin (nominal · tanggal · referensi · nama · aturan) yang
tampil di layar. Bobot & ambangnya ada di Pusat Pengaturan (`config_catalog_bank.py`),
bukan di dalam kode.

ISOLASI ENTITAS (F0-C)
----------------------
Sebelum fase ini `bank_statement_lines` TIDAK terdaftar sebagai koleksi SCOPED dan router
tidak memakai `entity_scope`: user PT-A cukup mengirim `bank_account_id` PT-B untuk
membaca mutasinya. Sekarang SETIAP fungsi menerima `entity_ids` (hasil
`resolve_scope_ids`) dan menolak (403) akun/baris di luar cakupan. Akun bank GRUP
(`entity_id == "all"`) tetap boleh dipakai semua entitas, tetapi barisnya di-stamp
dengan entitas AKTIF pengimpor supaya tetap terisolasi.
"""
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from db import db
from core_utils import new_id, now_iso, safe_doc, rupiah
from services import bank_statement_parser as parser
from services.config_resolver import value_of

STATUS = ("unmatched", "matched", "ignored", "holding")
GROUP_ENTITY = "all"
EPS = 0.01

CFG_KEYS = (
    "bank.match_weight_amount", "bank.match_weight_date", "bank.match_weight_ref",
    "bank.match_weight_name", "bank.auto_match_min_score", "bank.suggest_min_score",
    "bank.date_window_days", "bank.amount_tolerance", "bank.rule_learn_after",
    "bank.rule_bonus_score", "bank.holding_account_code", "bank.holding_max_age_days",
    "bank.charge_account_code", "bank.interest_account_code",
)


# ═════════════════════════════════════════════════════════════════════════════
#  KONFIGURASI (Pusat Pengaturan — tidak ada angka sihir di kode)
# ═════════════════════════════════════════════════════════════════════════════
async def load_cfg(entity_id: str = "") -> Dict[str, Any]:
    ctx = {"entity_id": entity_id or ""}
    raw = {}
    for k in CFG_KEYS:
        raw[k.split(".", 1)[1]] = await value_of(k, ctx)
    return {
        "w_amount": float(raw.get("match_weight_amount") or 0),
        "w_date": float(raw.get("match_weight_date") or 0),
        "w_ref": float(raw.get("match_weight_ref") or 0),
        "w_name": float(raw.get("match_weight_name") or 0),
        "auto_min": float(raw.get("auto_match_min_score") or 0),
        "suggest_min": float(raw.get("suggest_min_score") or 0),
        "window_days": int(raw.get("date_window_days") or 0),
        "amount_tol": float(raw.get("amount_tolerance") or 0),
        "learn_after": int(raw.get("rule_learn_after") or 3),
        "rule_bonus": float(raw.get("rule_bonus_score") or 0),
        "holding_acc": str(raw.get("holding_account_code") or "2-1950"),
        "holding_max_age_days": int(raw.get("holding_max_age_days") or 7),
        # Penutupan FASE G-8 — baris rekening koran yang memang TIDAK punya pasangan di buku
        # (biaya administrasi bank, bunga/jasa giro) dibukukan langsung ke akun ini. Tanpa
        # jalur ini "Selisih rekening vs buku" tidak pernah bisa nol.
        "charge_acc": str(raw.get("charge_account_code") or "6-8000"),
        "interest_acc": str(raw.get("interest_account_code") or "4-9000"),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  UTILITAS
# ═════════════════════════════════════════════════════════════════════════════
def _d(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10])
    except Exception:  # noqa: BLE001
        return None


def _norm_dir(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("in", "credit", "cr", "masuk", "kredit", "debit_bank"):
        return "in"
    return "out"


def _round(v: Any) -> float:
    return round(float(v or 0), 2)


def _scope_q(entity_ids: Optional[List[str]], field: str = "entity_id") -> Dict[str, Any]:
    """Filter entitas. `None` = tanpa filter (khusus pemakaian internal/seed)."""
    if entity_ids is None:
        return {}
    ids = list(entity_ids)
    if GROUP_ENTITY not in ids:
        ids.append(GROUP_ENTITY)   # akun/transaksi kas GRUP boleh dilihat semua entitas
    return {field: {"$in": ids}}


async def _account(bank_account_id: str, entity_ids: Optional[List[str]]) -> Dict[str, Any]:
    acc = await db.bank_accounts.find_one({"id": bank_account_id}, {"_id": 0})
    if not acc:
        raise ValueError("Akun bank tidak ditemukan")
    if entity_ids is not None:
        owner = acc.get("entity_id") or ""
        if owner and owner != GROUP_ENTITY and owner not in entity_ids:
            raise HTTPException(status_code=403, detail="Tidak berwenang atas akun bank entitas ini")
    return acc


async def _line(line_id: str, entity_ids: Optional[List[str]]) -> Dict[str, Any]:
    ln = await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0})
    if not ln:
        raise ValueError("Baris mutasi tidak ditemukan")
    if entity_ids is not None:
        ent = ln.get("entity_id") or ""
        if ent and ent != GROUP_ENTITY and ent not in entity_ids:
            raise HTTPException(status_code=403, detail="Tidak berwenang atas mutasi entitas ini")
    return ln


def _stamp_entity(acc: Dict[str, Any], active_entity: str) -> str:
    owner = acc.get("entity_id") or ""
    if owner and owner != GROUP_ENTITY:
        return owner
    return active_entity or owner or GROUP_ENTITY


# ═════════════════════════════════════════════════════════════════════════════
#  TEMPLATE FORMAT BANK
# ═════════════════════════════════════════════════════════════════════════════
def _fmt_doc(payload: Dict[str, Any], entity_id: str, actor: str,
             builtin: bool = False) -> Dict[str, Any]:
    cols = payload.get("columns") or {}
    return {
        "id": payload.get("id") or new_id("bsf"),
        "entity_id": entity_id,
        "name": (payload.get("name") or "Template tanpa nama").strip(),
        "bank_code": (payload.get("bank_code") or "generic").strip().lower(),
        "file_kind": (payload.get("file_kind") or "csv").strip().lower(),
        "delimiter": payload.get("delimiter", ","),
        "has_header": bool(payload.get("has_header", True)),
        "skip_rows": int(payload.get("skip_rows") or 0),
        "decimal_style": (payload.get("decimal_style") or "auto").lower(),
        "date_format": (payload.get("date_format") or "auto"),
        "columns": {k: cols.get(k, "") for k in
                    ("date", "description", "ref", "amount", "amount_in", "amount_out",
                     "direction", "balance", "external_id")},
        "in_markers": list(payload.get("in_markers") or []),
        "out_markers": list(payload.get("out_markers") or []),
        "header_signature": list(payload.get("header_signature") or []),
        "note": payload.get("note", ""),
        "builtin": builtin,
        "active": bool(payload.get("active", True)),
        "created_by": actor,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


async def ensure_builtin_formats(entity_id: str = "", actor: str = "system") -> int:
    """Pasang preset bawaan SEKALI untuk semua entitas (`entity_id="all"`).

    KN-G8-FORMAT-DUP (temuan penutupan fase): preset dulu dipasang PER ENTITAS, sehingga
    pemilik 2 PT melihat SETIAP template bawaan dua kali ("BCA — Rekening Koran (CSV)"
    muncul 2×) tanpa cara membedakannya — baik di pengelola template maupun di pemilih
    template pada panel impor. Preset adalah pengetahuan tentang format BANK, bukan data
    milik entitas, jadi cukup satu salinan GRUP yang boleh dibaca semua entitas
    (`_scope_q` selalu menyertakan entitas GRUP).

    Salinan lama per-entitas DIPADAMKAN (`active=False`) — tidak dihapus, supaya baris
    mutasi lama yang menyimpan `format_id` tetap bisa dilacak. Idempoten.
    """
    made = 0
    for f in parser.BUILTIN_FORMATS:
        exists = await db.bank_statement_formats.find_one(
            {"entity_id": GROUP_ENTITY, "name": f["name"], "builtin": True}, {"_id": 1})
        if not exists:
            await db.bank_statement_formats.insert_one(
                _fmt_doc(f, GROUP_ENTITY, actor, builtin=True))
            made += 1
        await db.bank_statement_formats.update_many(
            {"name": f["name"], "builtin": True, "entity_id": {"$ne": GROUP_ENTITY},
             "active": True},
            {"$set": {"active": False, "updated_at": now_iso()}})
    return made


async def list_formats(entity_ids: Optional[List[str]], active_entity: str = "",
                       actor: str = "system") -> List[Dict[str, Any]]:
    await ensure_builtin_formats(active_entity, actor)
    q = {**_scope_q(entity_ids), "active": True}
    rows = await db.bank_statement_formats.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    return [safe_doc(r) for r in rows]


async def upsert_format(payload: Dict[str, Any], entity_id: str, actor: str,
                        entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    fid = payload.get("id") or ""
    if fid:
        cur = await db.bank_statement_formats.find_one({"id": fid}, {"_id": 0})
        if not cur:
            raise ValueError("Template tidak ditemukan")
        if cur.get("builtin"):
            # Preset bawaan dipakai BERSAMA semua PT — menyuntingnya di tempat akan mengubah
            # template semua orang. Jadi hasil suntingan disimpan sebagai template BARU milik
            # entitas penyunting, tepat seperti yang dijanjikan layar: "buka, ubah pemetaan
            # kolomnya, lalu simpan sebagai template Anda sendiri".
            name = (payload.get("name") or cur.get("name") or "").strip()
            if name == (cur.get("name") or "").strip():
                name = f"{name} — salinan"
            doc = _fmt_doc({**cur, **payload, "id": "", "name": name}, entity_id, actor,
                           builtin=False)
            await db.bank_statement_formats.insert_one(doc)
            return safe_doc(doc)
        if entity_ids is not None and cur.get("entity_id") not in list(entity_ids) + [GROUP_ENTITY]:
            raise HTTPException(status_code=403, detail="Template milik entitas lain")
        doc = _fmt_doc({**cur, **payload, "id": fid}, cur.get("entity_id") or entity_id, actor,
                       builtin=bool(cur.get("builtin")))
        doc["created_at"] = cur.get("created_at") or doc["created_at"]
        doc["created_by"] = cur.get("created_by") or actor
        await db.bank_statement_formats.replace_one({"id": fid}, doc)
        return safe_doc(doc)
    doc = _fmt_doc(payload, entity_id, actor)
    await db.bank_statement_formats.insert_one(doc)
    return safe_doc(doc)


async def delete_format(format_id: str, entity_ids: Optional[List[str]] = None) -> None:
    cur = await db.bank_statement_formats.find_one({"id": format_id}, {"_id": 0})
    if not cur:
        raise ValueError("Template tidak ditemukan")
    if cur.get("builtin"):
        raise ValueError("Template bawaan tidak bisa dinonaktifkan — buka lalu simpan sebagai "
                         "salinan Anda sendiri, dan sunting salinannya")
    if entity_ids is not None and cur.get("entity_id") not in list(entity_ids) + [GROUP_ENTITY]:
        raise HTTPException(status_code=403, detail="Template milik entitas lain")
    await db.bank_statement_formats.update_one({"id": format_id}, {"$set": {
        "active": False, "updated_at": now_iso()}})


async def _resolve_format(format_id: str, fmt: Optional[Dict[str, Any]], raw: str,
                          entity_ids: Optional[List[str]],
                          active_entity: str) -> Tuple[Dict[str, Any], bool]:
    """Ambil template: eksplisit → dikirim langsung → deteksi otomatis. (fmt, terdeteksi)."""
    if format_id:
        doc = await db.bank_statement_formats.find_one({"id": format_id}, {"_id": 0})
        if not doc:
            raise ValueError("Template tidak ditemukan")
        # Preset bawaan milik entitas GRUP ("all") boleh dipakai semua entitas — sama seperti
        # akun bank grup (lihat `_scope_q`). Tanpa pengecualian ini, memilih template bawaan
        # dari layar impor akan ditolak 403 (regresi KN-G8-FORMAT-DUP).
        if (entity_ids is not None and doc.get("entity_id")
                not in list(entity_ids) + [GROUP_ENTITY]):
            raise HTTPException(status_code=403, detail="Template milik entitas lain")
        return doc, False
    if fmt:
        return _fmt_doc(fmt, active_entity, "preview"), False
    known = await list_formats(entity_ids, active_entity)
    hit = parser.detect_format(raw, known)
    if hit:
        return hit, True
    raise ValueError("Template tidak dikenali dari isi berkas — pilih template secara manual")


async def preview(raw: str, format_id: str = "", fmt: Optional[Dict[str, Any]] = None,
                  entity_ids: Optional[List[str]] = None, active_entity: str = "",
                  year_hint: int = 0, limit: int = 50) -> Dict[str, Any]:
    """Baca mutasi TANPA menyimpan — user melihat hasil sebelum impor."""
    fdoc, detected = await _resolve_format(format_id, fmt, raw, entity_ids, active_entity)
    rows, errors = parser.parse_rows(raw, fdoc, year_hint)
    return {
        "format": {"id": fdoc.get("id", ""), "name": fdoc.get("name", ""),
                   "bank_code": fdoc.get("bank_code", ""), "file_kind": fdoc.get("file_kind", "")},
        "detected": detected,
        "rows": rows[:limit],
        "total": len(rows),
        "errors": errors[:20],
        "error_count": len(errors),
        "sum_in": _round(sum(r["amount"] for r in rows if r["direction"] == "in")),
        "sum_out": _round(sum(r["amount"] for r in rows if r["direction"] == "out")),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  IMPOR
# ═════════════════════════════════════════════════════════════════════════════
def _line_doc(bank_account_id: str, entity_id: str, r: Dict[str, Any], batch: str,
              format_id: str) -> Dict[str, Any]:
    desc = (r.get("description") or "").strip()
    now = now_iso()
    return {
        "id": new_id("stmtline"), "bank_account_id": bank_account_id, "entity_id": entity_id,
        "stmt_date": str(r.get("stmt_date") or "")[:10], "amount": _round(r.get("amount")),
        "direction": _norm_dir(r.get("direction")), "description": desc,
        "counterparty": r.get("counterparty") or parser.counterparty_of(desc),
        "desc_key": r.get("desc_key") or parser.desc_key(desc),
        "ref": (r.get("ref") or "").strip(), "external_id": (r.get("external_id") or "").strip(),
        "balance": _round(r.get("balance")),
        "status": "unmatched", "match_kind": "", "matched_txn_id": "", "matched_txn_ids": [],
        "allocations": [], "score": 0, "score_explain": [], "suggestions": [],
        "match_type": "", "matched_at": "", "matched_by": "",
        "holding": {}, "holding_allocated": [], "holding_remaining": 0.0,
        "import_batch": batch, "format_id": format_id,
        "created_at": now, "updated_at": now,
    }


async def _dup_exists(bank_account_id: str, doc: Dict[str, Any]) -> bool:
    q: Dict[str, Any] = {"bank_account_id": bank_account_id}
    if doc.get("external_id"):
        q["external_id"] = doc["external_id"]
    else:
        q.update({"stmt_date": doc["stmt_date"], "amount": doc["amount"],
                  "direction": doc["direction"], "description": doc["description"]})
    return bool(await db.bank_statement_lines.find_one(q, {"_id": 1}))


async def import_lines(bank_account_id: str, entity_id: str, lines: List[Dict[str, Any]],
                       actor: str, entity_ids: Optional[List[str]] = None,
                       active_entity: str = "", format_id: str = "") -> Dict[str, Any]:
    """Impor baris mutasi yang SUDAH terstruktur (dipakai juga oleh seed & impor berkas)."""
    acc = await _account(bank_account_id, entity_ids)
    ent = entity_id or _stamp_entity(acc, active_entity)
    batch = new_id("stmtbatch")
    imported, skipped = 0, 0
    for r in lines or []:
        doc = _line_doc(bank_account_id, ent, r, batch, format_id)
        if doc["amount"] <= 0 or not doc["stmt_date"]:
            skipped += 1
            continue
        if await _dup_exists(bank_account_id, doc):
            skipped += 1
            continue
        await db.bank_statement_lines.insert_one(doc)
        imported += 1
    return {"import_batch": batch, "imported": imported, "skipped": skipped}


async def import_raw(bank_account_id: str, raw: str, format_id: str = "",
                     fmt: Optional[Dict[str, Any]] = None,
                     entity_ids: Optional[List[str]] = None, active_entity: str = "",
                     actor: str = "", year_hint: int = 0) -> Dict[str, Any]:
    """Impor dari ISI BERKAS (CSV/MT940/OFX) memakai template."""
    fdoc, detected = await _resolve_format(format_id, fmt, raw, entity_ids, active_entity)
    rows, errors = parser.parse_rows(raw, fdoc, year_hint)
    if not rows:
        raise ValueError("Tidak ada baris mutasi yang bisa dibaca — periksa template/berkas")
    res = await import_lines(bank_account_id, "", rows, actor, entity_ids, active_entity,
                             fdoc.get("id", ""))
    res.update({"format_id": fdoc.get("id", ""), "format_name": fdoc.get("name", ""),
                "detected": detected, "parsed": len(rows),
                "errors": errors[:20], "error_count": len(errors)})
    return res


# ═════════════════════════════════════════════════════════════════════════════
#  SKOR BERBOBOT (dengan penjelasan yang dibaca manusia)
# ═════════════════════════════════════════════════════════════════════════════
def _txn_text(txn: Dict[str, Any]) -> str:
    return " ".join(str(txn.get(k, "") or "") for k in
                    ("number", "description", "category", "ref_id", "counterparty_name"))


def _ref_score(line: Dict[str, Any], txn: Dict[str, Any], w: float) -> Tuple[float, str]:
    if w <= 0:
        return 0.0, ""
    hay = _txn_text(txn).upper()
    toks = [t for t in ([line.get("ref")] + parser.ref_tokens_of(line.get("description", "")))
            if t]
    for t in toks:
        tu = str(t).upper()
        if len(tu) >= 4 and tu in hay:
            return w, f"nomor referensi '{tu}' ada di transaksi buku"
    for t in toks:
        digits = re.sub(r"\D", "", str(t))
        if len(digits) >= 4 and digits[-4:] in re.sub(r"\D", "", hay):
            return round(w / 2, 2), f"sebagian nomor ('…{digits[-4:]}') cocok"
    return 0.0, ""


def _name_score(line: Dict[str, Any], txn: Dict[str, Any], w: float) -> Tuple[float, str]:
    if w <= 0:
        return 0.0, ""
    cp = (line.get("counterparty") or parser.counterparty_of(line.get("description", ""))).lower()
    if not cp:
        return 0.0, ""
    cands = [str(txn.get(k, "") or "") for k in
             ("customer_name", "counterparty_name", "description", "category")]
    best, who = 0.0, ""
    for c in cands:
        if not c:
            continue
        r = SequenceMatcher(None, cp, c.lower()).ratio()
        # nama pelanggan sering hanya SEBAGIAN dari berita transfer → cek keterkandungan
        if c.lower() in cp or cp in c.lower():
            r = max(r, 0.9)
        if r > best:
            best, who = r, c
    if best >= 0.8:
        return w, f"nama mirip '{who[:40]}' ({int(best * 100)}%)"
    if best >= 0.6:
        return round(w / 2, 2), f"nama agak mirip '{who[:40]}' ({int(best * 100)}%)"
    return 0.0, ""


def score_pair(line: Dict[str, Any], txn: Dict[str, Any], cfg: Dict[str, Any],
               rule: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Skor 0..100+ untuk satu pasangan (baris bank ↔ transaksi buku), dengan alasan.

    Return {"score", "explain":[{label, points}], "amount_diff", "day_diff", "eligible"}.
    `eligible=False` artinya pasangan tidak layak dipertimbangkan sama sekali
    (arah berbeda / nominal terlalu jauh / tanggal di luar jendela).
    """
    explain: List[Dict[str, Any]] = []
    if _norm_dir(txn.get("direction")) != _norm_dir(line.get("direction")):
        return {"score": 0, "explain": [], "eligible": False, "amount_diff": 0, "day_diff": 0,
                "reason": "arah dana berbeda"}

    l_amt, t_amt = _round(line.get("amount")), _round(txn.get("amount"))
    diff = round(abs(l_amt - t_amt), 2)
    tol = max(cfg["amount_tol"], 0.0)
    if diff <= tol + 0.001:
        pts = cfg["w_amount"]
        explain.append({"label": "Nominal sama" + (f" (selisih {rupiah(diff)} ≤ toleransi)" if diff else ""),
                        "points": pts})
    elif diff <= max(tol * 2, l_amt * 0.01):
        pts = round(cfg["w_amount"] * 0.6, 2)
        explain.append({"label": f"Nominal beda tipis {rupiah(diff)} (≤1%)", "points": pts})
    else:
        return {"score": 0, "explain": [], "eligible": False, "amount_diff": diff, "day_diff": 0,
                "reason": f"nominal beda {rupiah(diff)}"}
    total = pts

    ld, td = _d(line.get("stmt_date")), _d(txn.get("txn_date") or txn.get("created_at"))
    day_diff = abs((td - ld).days) if (td and ld) else 999
    window = max(cfg["window_days"], 0)
    if day_diff > window:
        return {"score": 0, "explain": [], "eligible": False, "amount_diff": diff,
                "day_diff": day_diff, "reason": f"selisih {day_diff} hari di luar jendela {window} hari"}
    if cfg["w_date"] > 0:
        pts_d = cfg["w_date"] if day_diff == 0 else round(
            cfg["w_date"] * (1 - (day_diff / (window + 1))), 2)
        explain.append({"label": "Tanggal sama" if day_diff == 0 else f"Tanggal beda {day_diff} hari",
                        "points": pts_d})
        total += pts_d

    pts_r, why_r = _ref_score(line, txn, cfg["w_ref"])
    if pts_r:
        explain.append({"label": why_r, "points": pts_r})
        total += pts_r
    pts_n, why_n = _name_score(line, txn, cfg["w_name"])
    if pts_n:
        explain.append({"label": why_n, "points": pts_n})
        total += pts_n
    if rule and cfg["rule_bonus"] > 0:
        explain.append({"label": f"Aturan tersimpan: {rule.get('sample_desc', '')[:40]}",
                        "points": cfg["rule_bonus"]})
        total += cfg["rule_bonus"]
    return {"score": round(total, 2), "explain": explain, "eligible": True,
            "amount_diff": diff, "day_diff": day_diff, "reason": ""}


# ═════════════════════════════════════════════════════════════════════════════
#  KANDIDAT & PENCOCOKAN
# ═════════════════════════════════════════════════════════════════════════════
def _book_query(acc: Dict[str, Any], entity_ids: Optional[List[str]]) -> Dict[str, Any]:
    """Transaksi BUKU milik satu akun bank.

    JEMBATAN KOMPATIBILITAS (terukur 2026-07-29): `ar_receipt_service._post_cash_in`
    membuat `cash_transactions` **tanpa** `account_id` (hanya `cash_type`), sehingga
    penerimaan pelanggan — justru transaksi yang paling sering direkonsiliasi — tidak
    pernah muncul sebagai kandidat. Jadi kandidat = transaksi ber-`account_id` akun ini
    **atau** transaksi tanpa akun yang jenis kasnya sama (kolam kas besar/kecil).
    """
    kind = acc.get("cash_type") or "kas_besar"
    return {
        "status": {"$ne": "void"},
        "$or": [
            {"account_id": acc["id"]},
            {"account_id": {"$in": ["", None]}, "cash_type": kind},
            {"account_id": {"$exists": False}, "cash_type": kind},
        ],
        **_scope_q(entity_ids),
    }


async def _candidate_txns(bank_account_id: str, entity_ids: Optional[List[str]],
                          include_partial: bool = True) -> List[Dict[str, Any]]:
    acc = await db.bank_accounts.find_one({"id": bank_account_id}, {"_id": 0})
    if not acc:
        return []
    rows = await db.cash_transactions.find(_book_query(acc, entity_ids), {"_id": 0}).to_list(20000)
    out = []
    for t in rows:
        rec = _round(t.get("reconciled_amount"))
        if t.get("reconciled") and (not include_partial or rec >= _round(t.get("amount")) - EPS):
            continue
        out.append(t)
    return out


async def _active_rules(bank_account_id: str, entity_ids: Optional[List[str]]) -> Dict[str, Dict[str, Any]]:
    q = {"bank_account_id": bank_account_id, "status": "active", **_scope_q(entity_ids)}
    rows = await db.bank_match_rules.find(q, {"_id": 0}).to_list(2000)
    return {r["desc_key"]: r for r in rows if r.get("desc_key")}


def _rule_for(line: Dict[str, Any], rules: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    key = line.get("desc_key") or parser.desc_key(line.get("description", ""))
    if not key:
        return None
    r = rules.get(key)
    if r and _norm_dir(r.get("direction")) == _norm_dir(line.get("direction")):
        return r
    return None


def _txn_brief(t: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": t.get("id"), "number": t.get("number", ""), "amount": _round(t.get("amount")),
            "direction": t.get("direction"), "txn_date": t.get("txn_date", ""),
            "description": t.get("description", ""),
            "outstanding": _round(_round(t.get("amount")) - _round(t.get("reconciled_amount")))}


async def candidates(line_id: str, entity_ids: Optional[List[str]] = None,
                     limit: int = 8) -> Dict[str, Any]:
    """Kandidat berperingkat + penjelasan skor untuk satu baris (dipakai modal UI)."""
    ln = await _line(line_id, entity_ids)
    cfg = await load_cfg(ln.get("entity_id", ""))
    rules = await _active_rules(ln["bank_account_id"], entity_ids)
    rule = _rule_for(ln, rules)
    txns = await _candidate_txns(ln["bank_account_id"], entity_ids)
    scored = []
    for t in txns:
        s = score_pair(ln, t, cfg, rule)
        if not s["eligible"]:
            continue
        scored.append({**_txn_brief(t), "score": s["score"], "explain": s["explain"]})
    scored.sort(key=lambda r: -r["score"])
    return {"line": safe_doc(ln), "candidates": scored[:limit],
            "auto_min": cfg["auto_min"], "suggest_min": cfg["suggest_min"],
            "rule_applied": bool(rule)}


async def _link(line: Dict[str, Any], allocations: List[Dict[str, Any]], actor: str,
                match_type: str, match_kind: str) -> None:
    """Tautkan satu baris ke satu/beberapa transaksi buku (append-only pada dua sisi)."""
    now = now_iso()
    txn_ids = [a["txn_id"] for a in allocations]
    await db.bank_statement_lines.update_one({"id": line["id"]}, {"$set": {
        "status": "matched", "match_kind": match_kind,
        "matched_txn_id": txn_ids[0] if len(txn_ids) == 1 else "",
        "matched_txn_ids": txn_ids, "allocations": allocations,
        "match_type": match_type, "matched_at": now, "matched_by": actor,
        "updated_at": now}})
    for a in allocations:
        t = await db.cash_transactions.find_one({"id": a["txn_id"]}, {"_id": 0})
        if not t:
            continue
        rec = _round(_round(t.get("reconciled_amount")) + _round(a["amount"]))
        ids = [x for x in (t.get("matched_line_ids") or []) if x != line["id"]] + [line["id"]]
        full = rec >= _round(t.get("amount")) - EPS
        await db.cash_transactions.update_one({"id": a["txn_id"]}, {"$set": {
            "reconciled": bool(full), "reconciled_amount": rec,
            "reconciled_at": now if full else "",
            "matched_line_id": line["id"] if len(ids) == 1 else "",
            "matched_line_ids": ids, "updated_at": now}})


async def _unlink(line: Dict[str, Any]) -> None:
    now = now_iso()
    for a in (line.get("allocations") or []):
        t = await db.cash_transactions.find_one({"id": a["txn_id"]}, {"_id": 0})
        if not t:
            continue
        rec = max(0.0, _round(_round(t.get("reconciled_amount")) - _round(a["amount"])))
        ids = [x for x in (t.get("matched_line_ids") or []) if x != line["id"]]
        await db.cash_transactions.update_one({"id": a["txn_id"]}, {"$set": {
            "reconciled": bool(ids) and rec >= _round(t.get("amount")) - EPS,
            "reconciled_amount": rec, "reconciled_at": "",
            "matched_line_id": ids[0] if len(ids) == 1 else "",
            "matched_line_ids": ids, "updated_at": now}})
    await db.bank_statement_lines.update_one({"id": line["id"]}, {"$set": {
        "status": "unmatched", "match_kind": "", "matched_txn_id": "", "matched_txn_ids": [],
        "allocations": [], "match_type": "", "matched_at": "", "matched_by": "",
        "score": 0, "score_explain": [], "updated_at": now}})


async def auto_match(bank_account_id: str, entity_ids: Optional[List[str]] = None,
                     window_days: Optional[int] = None, amount_tol: Optional[float] = None,
                     actor: str = "", active_entity: str = "") -> Dict[str, Any]:
    """Cocokkan otomatis 3 pita: ≥ambang otomatis → tertaut · pita usulan → disimpan
    sebagai `suggestions[]` (TIDAK ditautkan) · di bawahnya → murni manual."""
    acc = await _account(bank_account_id, entity_ids)
    cfg = await load_cfg(_stamp_entity(acc, active_entity))
    if window_days is not None:
        cfg["window_days"] = int(window_days)
    if amount_tol is not None:
        cfg["amount_tol"] = float(amount_tol)
    lines = await db.bank_statement_lines.find(
        {"bank_account_id": bank_account_id, "status": "unmatched", **_scope_q(entity_ids)},
        {"_id": 0}).to_list(20000)
    txns = await _candidate_txns(bank_account_id, entity_ids)
    rules = await _active_rules(bank_account_id, entity_ids)
    by_id = {t["id"]: t for t in txns}
    used: Dict[str, float] = {}
    matched, suggested = 0, 0

    for ln in sorted(lines, key=lambda x: (x.get("stmt_date") or "", -_round(x.get("amount")))):
        rule = _rule_for(ln, rules)
        scored = []
        for t in txns:
            avail = _round(_round(t.get("amount")) - _round(t.get("reconciled_amount")) - used.get(t["id"], 0.0))
            if avail <= EPS:
                continue
            s = score_pair(ln, t, cfg, rule)
            if s["eligible"]:
                scored.append((s["score"], s["explain"], t))
        scored.sort(key=lambda r: (-r[0], r[2].get("txn_date") or ""))
        if not scored:
            await db.bank_statement_lines.update_one({"id": ln["id"]}, {"$set": {
                "suggestions": [], "score": 0, "score_explain": [], "updated_at": now_iso()}})
            continue
        top_score, top_explain, top_txn = scored[0]
        amt = _round(ln.get("amount"))
        top_avail = _round(_round(top_txn.get("amount"))
                           - _round(top_txn.get("reconciled_amount"))
                           - used.get(top_txn["id"], 0.0))
        # KN-G8-MATCH-PARTIAL (jalur OTOMATIS): dulu `min(nominal mutasi, sisa transaksi)`
        # sehingga baris bisa tertaut sendiri dengan Σ alokasi LEBIH KECIL dari nominalnya —
        # INV-BNK-01 memerah tanpa ada manusia yang menyentuh apa pun. Sekarang pita otomatis
        # hanya untuk pasangan yang menutup SELURUH nominal mutasi; yang tidak cukup turun
        # menjadi USULAN supaya manusia memilih jalur pecah (1:N) / gabung (N:1).
        if top_score >= cfg["auto_min"] and top_avail + EPS >= amt:
            await db.bank_statement_lines.update_one({"id": ln["id"]}, {"$set": {
                "score": top_score, "score_explain": top_explain, "suggestions": []}})
            fresh = await db.bank_statement_lines.find_one({"id": ln["id"]}, {"_id": 0})
            await _link(fresh, [{"txn_id": top_txn["id"], "amount": amt}], actor, "auto", "1:1")
            used[top_txn["id"]] = used.get(top_txn["id"], 0.0) + amt
            matched += 1
        elif top_score >= cfg["suggest_min"]:
            sug = [{**_txn_brief(t), "score": sc, "explain": ex} for sc, ex, t in scored[:3]]
            await db.bank_statement_lines.update_one({"id": ln["id"]}, {"$set": {
                "suggestions": sug, "score": top_score, "score_explain": top_explain,
                "updated_at": now_iso()}})
            suggested += 1
        else:
            await db.bank_statement_lines.update_one({"id": ln["id"]}, {"$set": {
                "suggestions": [], "score": top_score, "score_explain": top_explain,
                "updated_at": now_iso()}})
    remaining_lines = await db.bank_statement_lines.count_documents(
        {"bank_account_id": bank_account_id, "status": "unmatched", **_scope_q(entity_ids)})
    remaining_txns = len(await _candidate_txns(bank_account_id, entity_ids))
    return {"matched": matched, "suggested": suggested, "unmatched_lines": remaining_lines,
            "unmatched_txns": remaining_txns, "auto_min": cfg["auto_min"],
            "suggest_min": cfg["suggest_min"], "window_days": cfg["window_days"],
            "amount_tolerance": cfg["amount_tol"], "rules_active": len(rules),
            "by_id_count": len(by_id)}


async def manual_match(line_id: str, txn_id: str, actor: str,
                       entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    ln = await _line(line_id, entity_ids)
    if ln.get("status") == "matched":
        raise ValueError("Baris sudah tertaut. Lepaskan (unmatch) dulu.")
    if ln.get("status") == "holding":
        raise ValueError("Baris berstatus titipan. Batalkan titipan dulu.")
    t = await db.cash_transactions.find_one({"id": txn_id}, {"_id": 0})
    if not t:
        raise ValueError("Transaksi kas tidak ditemukan")
    if entity_ids is not None:
        ent = t.get("entity_id") or ""
        if ent and ent != GROUP_ENTITY and ent not in entity_ids:
            raise HTTPException(status_code=403, detail="Transaksi kas milik entitas lain")
    avail = _round(_round(t.get("amount")) - _round(t.get("reconciled_amount")))
    if avail <= EPS:
        raise ValueError("Transaksi kas sudah terekonsiliasi penuh.")
    amt = _round(ln.get("amount"))
    # KN-G8-MATCH-PARTIAL (temuan penutupan fase): dulu `min(nominal mutasi, sisa transaksi)`
    # sehingga baris bisa berstatus "tercocok" padahal Σ alokasinya LEBIH KECIL dari nominal
    # mutasinya → INV-BNK-01 memerah dan sisa uangnya tidak terjelaskan di mana pun. Sekarang
    # ditolak dengan arahan jalur yang benar, bukan diam-diam dipotong.
    if amt > avail + EPS:
        raise ValueError(
            f"Sisa transaksi {t.get('number')} hanya {rupiah(avail)} — lebih kecil dari nominal "
            f"mutasi {rupiah(amt)}. Pakai 'Pecah ke beberapa transaksi' agar SELURUH nominal "
            f"mutasi terjelaskan, atau titipkan dana ini bila sisanya belum diketahui.")
    await _link(ln, [{"txn_id": txn_id, "amount": amt}], actor, "manual", "1:1")
    learned = await learn_from_manual(ln, [t], actor, entity_ids)
    out = await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0})
    return {**safe_doc(out), "rule_learned": learned}


async def match_split(line_id: str, allocations: List[Dict[str, Any]], actor: str,
                      entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """1 transfer → BEBERAPA transaksi buku (1:N). Σ alokasi ≤ nominal transfer."""
    ln = await _line(line_id, entity_ids)
    if ln.get("status") in ("matched", "holding"):
        raise ValueError("Baris sudah tertaut/dititipkan. Lepaskan dulu.")
    if len(allocations or []) < 2:
        raise ValueError("Split butuh minimal 2 transaksi buku")
    total = _round(sum(_round(a.get("amount")) for a in allocations))
    if total > _round(ln.get("amount")) + EPS:
        raise ValueError(f"Σ alokasi {rupiah(total)} melebihi nominal mutasi "
                         f"{rupiah(_round(ln.get('amount')))}")
    # KN-G8-MATCH-PARTIAL: baris "tercocok" WAJIB terjelaskan penuh (INV-BNK-01), jadi
    # pemecahan yang menyisakan rupiah menggantung ditolak dengan arahan yang jelas.
    if total < _round(ln.get("amount")) - EPS:
        sisa = _round(_round(ln.get("amount")) - total)
        raise ValueError(
            f"Σ alokasi {rupiah(total)} belum menutup seluruh nominal mutasi "
            f"{rupiah(_round(ln.get('amount')))} — sisa {rupiah(sisa)} tidak terjelaskan. "
            "Tambahkan transaksi buku lain, atau titipkan dana ini dulu.")
    clean, txns = [], []
    for a in allocations:
        tid, amt = a.get("txn_id"), _round(a.get("amount"))
        if not tid or amt <= 0:
            raise ValueError("Alokasi tidak sah (txn_id/amount kosong)")
        t = await db.cash_transactions.find_one({"id": tid}, {"_id": 0})
        if not t:
            raise ValueError(f"Transaksi kas {tid} tidak ditemukan")
        if entity_ids is not None:
            ent = t.get("entity_id") or ""
            if ent and ent != GROUP_ENTITY and ent not in entity_ids:
                raise HTTPException(status_code=403, detail="Transaksi kas milik entitas lain")
        if _norm_dir(t.get("direction")) != _norm_dir(ln.get("direction")):
            raise ValueError(f"Arah dana transaksi {t.get('number')} berbeda dgn mutasi")
        avail = _round(_round(t.get("amount")) - _round(t.get("reconciled_amount")))
        if amt > avail + EPS:
            raise ValueError(f"Alokasi {rupiah(amt)} melebihi sisa transaksi "
                             f"{t.get('number')} ({rupiah(avail)})")
        clean.append({"txn_id": tid, "amount": amt})
        txns.append(t)
    await _link(ln, clean, actor, "manual", "1:N")
    learned = await learn_from_manual(ln, txns, actor, entity_ids)
    out = await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0})
    return {**safe_doc(out), "rule_learned": learned, "allocated_total": total}


async def match_group(line_ids: List[str], txn_id: str, actor: str,
                      entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """BEBERAPA transfer → 1 transaksi buku (N:1). Σ mutasi ≤ nominal transaksi."""
    if len(line_ids or []) < 2:
        raise ValueError("Gabung butuh minimal 2 baris mutasi")
    t = await db.cash_transactions.find_one({"id": txn_id}, {"_id": 0})
    if not t:
        raise ValueError("Transaksi kas tidak ditemukan")
    if entity_ids is not None:
        ent = t.get("entity_id") or ""
        if ent and ent != GROUP_ENTITY and ent not in entity_ids:
            raise HTTPException(status_code=403, detail="Transaksi kas milik entitas lain")
    lines = []
    for lid in line_ids:
        ln = await _line(lid, entity_ids)
        if ln.get("status") in ("matched", "holding"):
            raise ValueError(f"Baris {ln.get('stmt_date')} sudah tertaut/dititipkan")
        if _norm_dir(ln.get("direction")) != _norm_dir(t.get("direction")):
            raise ValueError("Arah dana baris mutasi berbeda dgn transaksi buku")
        lines.append(ln)
    total = _round(sum(_round(l.get("amount")) for l in lines))
    avail = _round(_round(t.get("amount")) - _round(t.get("reconciled_amount")))
    if total > avail + EPS:
        raise ValueError(f"Σ mutasi {rupiah(total)} melebihi sisa transaksi "
                         f"{t.get('number')} ({rupiah(avail)})")
    for ln in lines:
        await _link(ln, [{"txn_id": txn_id, "amount": _round(ln.get("amount"))}],
                    actor, "manual", "N:1")
    return {"txn_id": txn_id, "txn_number": t.get("number", ""), "lines": len(lines),
            "allocated_total": total, "match_kind": "N:1"}


async def unmatch(line_id: str, actor: str, entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    ln = await _line(line_id, entity_ids)
    # KN-G8-UNMATCH-NOGUARD (temuan penutupan fase): tanpa penjaga status, `unmatch` pada
    # baris TITIPAN membuat statusnya 'unmatched' sementara kas + jurnal titipannya tetap
    # hidup → INV-BNK-03 memerah (uang tak dikenal hilang dari laporan). Layar hanya
    # menampilkan tombol "Lepas" untuk baris tercocok, tapi API tidak boleh percaya layar.
    if ln.get("status") != "matched":
        raise ValueError(
            "Hanya baris berstatus TERCOCOK yang bisa dilepas. "
            "Baris titipan dilepas lewat 'Batalkan titipan'; baris diabaikan lewat "
            "'Batal abaikan'.")
    if ln.get("match_type") == "charge":
        await _reverse_charge(ln, actor)
    await _unlink(ln)
    return safe_doc(await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0}))


async def ignore_line(line_id: str, actor: str, entity_ids: Optional[List[str]] = None,
                      note: str = "") -> Dict[str, Any]:
    ln = await _line(line_id, entity_ids)
    if ln.get("status") == "matched":
        raise ValueError("Baris sudah tertaut. Lepaskan (unmatch) dulu.")
    if ln.get("status") == "holding":
        raise ValueError("Baris berstatus titipan. Batalkan titipan dulu.")
    await db.bank_statement_lines.update_one({"id": line_id}, {"$set": {
        "status": "ignored", "ignore_note": note, "ignored_by": actor,
        "suggestions": [], "updated_at": now_iso()}})
    return safe_doc(await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0}))


async def unignore_line(line_id: str, actor: str,
                        entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    ln = await _line(line_id, entity_ids)
    if ln.get("status") != "ignored":
        raise ValueError("Baris ini tidak berstatus diabaikan")
    await db.bank_statement_lines.update_one({"id": line_id}, {"$set": {
        "status": "unmatched", "ignore_note": "", "updated_at": now_iso()}})
    return safe_doc(await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0}))


# ═════════════════════════════════════════════════════════════════════════════
#  BIAYA & BUNGA BANK — baris rekening koran yang MEMANG tidak ada di buku
# ═════════════════════════════════════════════════════════════════════════════
# kind → (arah wajib, kategori kas, label manusia)
CHARGE_KINDS: Dict[str, Tuple[str, str, str]] = {
    "charge": ("out", "biaya administrasi bank", "Biaya bank"),
    "interest": ("in", "pendapatan bunga bank", "Bunga / jasa giro"),
}


async def book_charge(line_id: str, kind: str, note: str, actor: str,
                      entity_ids: Optional[List[str]] = None,
                      active_entity: str = "") -> Dict[str, Any]:
    """Bukukan baris rekening koran yang tidak punya pasangan di buku.

    Biaya administrasi/transfer dan bunga/jasa giro tidak pernah lahir sebagai transaksi
    kas lebih dulu — bank memotong/menambah sendiri. Sebelum ini satu-satunya pilihan di
    layar adalah **Abaikan**, sehingga bebannya hilang dari laba rugi dan "Selisih rekening
    vs buku" tidak pernah bisa nol (rekonsiliasi tidak pernah tuntas).

    Sekarang baris itu melahirkan transaksi kas + jurnal
    (`Dr Beban Adm Bank / Cr Bank` atau `Dr Bank / Cr Pendapatan Bunga`) lalu **tertaut ke
    barisnya sendiri**, jadi Σ alokasi == nominal mutasi (INV-BNK-01 tetap hijau) dan
    saldo buku ikut bergerak sebesar biaya itu.
    """
    kind = (kind or "").strip().lower()
    if kind not in CHARGE_KINDS:
        raise ValueError("Jenis pembukuan harus 'charge' (biaya bank) atau "
                         "'interest' (bunga/jasa giro)")
    want_dir, category, label = CHARGE_KINDS[kind]
    ln = await _line(line_id, entity_ids)
    if ln.get("status") == "matched":
        raise ValueError("Baris sudah tertaut. Lepaskan (unmatch) dulu.")
    if ln.get("status") == "holding":
        raise ValueError("Baris berstatus titipan. Batalkan titipan dulu.")
    cur_dir = _norm_dir(ln.get("direction"))
    if cur_dir != want_dir:
        raise ValueError(
            f"{label} hanya untuk dana {'KELUAR' if want_dir == 'out' else 'MASUK'} — "
            f"baris ini dana {'masuk' if cur_dir == 'in' else 'keluar'}")
    acc = await _account(ln["bank_account_id"], entity_ids)
    ent = ln.get("entity_id") or _stamp_entity(acc, active_entity)
    cfg = await load_cfg(ent)
    contra = cfg["charge_acc"] if kind == "charge" else cfg["interest_acc"]
    amount = _round(ln.get("amount"))
    if amount <= EPS:
        raise ValueError("Nominal mutasi nol — tidak ada yang bisa dibukukan")

    from core_utils import next_doc_number
    from services import gl_service as gl
    # Akun bisa berasal dari Pusat Pengaturan; pastikan bagan akun baku ada supaya jurnal
    # tidak jatuh ke Suspense pada database baru.
    await gl.seed_default_coa()
    number = await next_doc_number("cash_transactions", "number", "CASH-", entity_id=ent)
    cdoc = {
        "id": new_id("cash"), "number": number,
        "cash_type": acc.get("cash_type") or "kas_besar",
        "direction": want_dir, "amount": amount, "category": category,
        "contra_account_code": contra,
        "description": (f"{label} — {(ln.get('description') or '')[:80]}"
                        + (f" · {note}" if note else "")),
        "entity_id": ent, "account_id": ln["bank_account_id"],
        "ref_type": "bank_statement_line", "ref_id": ln["id"],
        "txn_date": ln.get("stmt_date") or now_iso(), "status": "posted",
        "reconciled": False, "reconciled_amount": 0.0,
        "created_by": actor, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.cash_transactions.insert_one(cdoc)
    je = await gl.post_cash_transaction(cdoc)
    await db.bank_statement_lines.update_one({"id": line_id}, {"$set": {
        "charge": {"kind": kind, "label": label, "cash_txn_id": cdoc["id"],
                   "cash_number": number, "je_id": (je or {}).get("id", ""),
                   "je_number": (je or {}).get("number", ""), "account_code": contra,
                   "at": now_iso(), "by": actor, "note": note},
        "suggestions": [], "updated_at": now_iso()}})
    ln = await _line(line_id, entity_ids)
    await _link(ln, [{"txn_id": cdoc["id"], "amount": amount}], actor, "charge", "1:1")
    out = safe_doc(await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0}))
    return {**out, "kind": kind, "label": label, "cash_number": number,
            "je_number": (je or {}).get("number", ""), "account_code": contra}


async def _reverse_charge(line: Dict[str, Any], actor: str) -> None:
    """Lepas baris biaya/bunga bank: kasnya di-void & jurnalnya DIBALIK (append-only).

    Jurnal asal TIDAK dihapus — dibalik dengan reversing entry (aturan repo: ledger
    append-only), memakai `gl.reverse_document` yang idempoten.
    """
    ch = line.get("charge") or {}
    if not ch.get("cash_txn_id"):
        return
    from services import gl_service as gl
    await db.cash_transactions.update_one({"id": ch["cash_txn_id"]}, {"$set": {
        "status": "void", "void_reason": "pembukuan biaya/bunga bank dilepas",
        "updated_at": now_iso()}})
    await gl.reverse_document("cash_transaction", ch["cash_txn_id"],
                              reason="pembukuan biaya/bunga bank dilepas", actor_name=actor)
    await db.bank_statement_lines.update_one({"id": line["id"]}, {"$set": {
        "charge": {}, "updated_at": now_iso()}})


# ═════════════════════════════════════════════════════════════════════════════
#  ATURAN YANG DIPELAJARI (ditawarkan, TIDAK dipaksakan)
# ═════════════════════════════════════════════════════════════════════════════
async def learn_from_manual(line: Dict[str, Any], txns: List[Dict[str, Any]], actor: str,
                            entity_ids: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Hitung pola pencocokan manual. Setelah N kali pola sama → TAWARKAN aturan.

    Sistem tidak pernah membuat aturan aktif sendiri: statusnya `suggested` sampai
    manusia menyetujui (`decide_rule`). Ini menjaga prinsip "tidak ada perubahan senyap".
    """
    key = line.get("desc_key") or parser.desc_key(line.get("description", ""))
    if not key:
        return None
    cfg = await load_cfg(line.get("entity_id", ""))
    direction = _norm_dir(line.get("direction"))
    bank_account_id = line["bank_account_id"]
    counterparty = line.get("counterparty") or parser.counterparty_of(line.get("description", ""))
    hits = await db.bank_statement_lines.count_documents({
        "bank_account_id": bank_account_id, "desc_key": key, "direction": direction,
        "match_type": "manual", "status": "matched", **_scope_q(entity_ids)})
    existing = await db.bank_match_rules.find_one(
        {"bank_account_id": bank_account_id, "desc_key": key, "direction": direction},
        {"_id": 0})
    now = now_iso()
    if existing:
        await db.bank_match_rules.update_one({"id": existing["id"]}, {"$set": {
            "hits": hits, "sample_desc": line.get("description", ""),
            "counterparty": counterparty, "updated_at": now}})
        return None if existing.get("status") != "suggested" else safe_doc(
            await db.bank_match_rules.find_one({"id": existing["id"]}, {"_id": 0}))
    if hits < cfg["learn_after"]:
        return None
    rule = {
        "id": new_id("bmr"), "entity_id": line.get("entity_id", ""),
        "bank_account_id": bank_account_id, "desc_key": key, "direction": direction,
        "counterparty": counterparty, "sample_desc": line.get("description", ""),
        "customer_id": (txns[0].get("customer_id", "") if txns else ""),
        "category": (txns[0].get("category", "") if txns else ""),
        "hits": hits, "status": "suggested",
        "learned_from": [line["id"]], "created_by": actor, "created_at": now,
        "decided_by": "", "decided_at": "", "updated_at": now,
    }
    await db.bank_match_rules.insert_one(rule)
    try:
        from services.notification_service import create_notification
        await create_notification(
            notif_type="bank_rule_suggested", severity="info",
            title="Aturan pencocokan bank ditawarkan",
            body=(f"Pola '{counterparty or key}' sudah dicocokkan manual {hits}×. "
                  f"Setujui aturannya agar mutasi berikutnya cocok otomatis."),
            link="/finance/bank-reconciliation", entity_id=line.get("entity_id", ""),
            recipient_role="manager", ref=rule["id"])
    except Exception:  # noqa: BLE001 — notifikasi bukan syarat sahnya aturan
        pass
    return safe_doc(rule)


async def list_rules(entity_ids: Optional[List[str]] = None, bank_account_id: str = "",
                     status: str = "") -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {**_scope_q(entity_ids)}
    if bank_account_id:
        q["bank_account_id"] = bank_account_id
    if status:
        q["status"] = status
    rows = await db.bank_match_rules.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [safe_doc(r) for r in rows]


async def decide_rule(rule_id: str, action: str, actor: str,
                      entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    r = await db.bank_match_rules.find_one({"id": rule_id}, {"_id": 0})
    if not r:
        raise ValueError("Aturan tidak ditemukan")
    if entity_ids is not None:
        ent = r.get("entity_id") or ""
        if ent and ent != GROUP_ENTITY and ent not in entity_ids:
            raise HTTPException(status_code=403, detail="Aturan milik entitas lain")
    mapping = {"activate": "active", "reject": "rejected", "suspend": "suggested"}
    if action not in mapping:
        raise ValueError("Aksi aturan tidak dikenal (activate|reject|suspend)")
    await db.bank_match_rules.update_one({"id": rule_id}, {"$set": {
        "status": mapping[action], "decided_by": actor, "decided_at": now_iso(),
        "updated_at": now_iso()}})
    return safe_doc(await db.bank_match_rules.find_one({"id": rule_id}, {"_id": 0}))


# ═════════════════════════════════════════════════════════════════════════════
#  TITIPAN DANA BELUM TERIDENTIFIKASI (jembatan ke FASE G-9)
# ═════════════════════════════════════════════════════════════════════════════
async def to_holding(line_id: str, note: str, actor: str,
                     entity_ids: Optional[List[str]] = None,
                     active_entity: str = "") -> Dict[str, Any]:
    """Dana masuk tak dikenal → buku kas + jurnal `Dr Bank / Cr Titipan`.

    Uang yang nyata masuk ke rekening TIDAK boleh menggantung tanpa catatan: ia diakui
    sebagai KEWAJIBAN (titipan) sampai pemiliknya ketemu.
    """
    ln = await _line(line_id, entity_ids)
    if _norm_dir(ln.get("direction")) != "in":
        raise ValueError("Hanya dana MASUK yang bisa dititipkan")
    if ln.get("status") == "matched":
        raise ValueError("Baris sudah tertaut. Lepaskan (unmatch) dulu.")
    if ln.get("status") == "holding":
        raise ValueError("Baris sudah berstatus titipan")
    acc = await _account(ln["bank_account_id"], entity_ids)
    ent = ln.get("entity_id") or _stamp_entity(acc, active_entity)
    amount = _round(ln.get("amount"))

    from core_utils import next_doc_number
    from services import gl_service as gl
    # Pastikan akun titipan ADA sebelum menjurnal. Tanpa ini, jurnal pertama di DB baru
    # jatuh ke akun Suspense (terukur di POC G-8) sehingga saldo titipan tak terbaca.
    await gl.seed_default_coa()
    number = await next_doc_number("cash_transactions", "number", "CASH-", entity_id=ent)
    cdoc = {
        "id": new_id("cash"), "number": number,
        "cash_type": "kas_besar" if (acc.get("cash_type") or "kas_besar") == "kas_besar" else acc.get("cash_type"),
        "direction": "in", "amount": amount,
        "category": "titipan dana belum teridentifikasi",
        "description": (f"Titipan dana belum teridentifikasi — {ln.get('description', '')[:80]}"
                        + (f" · {note}" if note else "")),
        "entity_id": ent, "account_id": ln["bank_account_id"],
        "ref_type": "bank_statement_line", "ref_id": ln["id"],
        "txn_date": ln.get("stmt_date") or now_iso(), "status": "posted",
        "reconciled": True, "reconciled_amount": amount, "matched_line_id": ln["id"],
        "matched_line_ids": [ln["id"]], "reconciled_at": now_iso(),
        "created_by": actor, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.cash_transactions.insert_one(cdoc)
    je = None
    try:
        je = await gl.post_cash_transaction(cdoc)
    except Exception:  # noqa: BLE001
        je = None
    await db.bank_statement_lines.update_one({"id": line_id}, {"$set": {
        "status": "holding", "suggestions": [],
        "holding": {"cash_txn_id": cdoc["id"], "cash_number": number,
                    "je_id": (je or {}).get("id", ""), "je_number": (je or {}).get("number", ""),
                    "at": now_iso(), "by": actor, "note": note},
        "holding_allocated": [], "holding_remaining": amount,
        "updated_at": now_iso()}})
    return safe_doc(await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0}))


async def allocate_holding(line_id: str, allocations: List[Dict[str, Any]], customer_id: str,
                           reason_code: str, note: str, actor: str,
                           entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Titipan teridentifikasi → lunasi pesanan pelanggan.

    Piutang pesanan berkurang (pola `apply_from_deposit` FASE G-3) dan jurnalnya
    `Dr Titipan / Cr Piutang` — **tanpa kas dobel**, karena kasnya sudah diakui saat
    dana dititipkan.
    """
    ln = await _line(line_id, entity_ids)
    if ln.get("status") != "holding":
        raise ValueError("Baris ini bukan titipan dana")
    if not reason_code:
        raise ValueError("Alasan (reason_code) wajib diisi — keputusan atas uang harus berlabel")
    remaining = _round(ln.get("holding_remaining", ln.get("amount")))
    total = _round(sum(_round(a.get("amount")) for a in (allocations or [])))
    if total <= 0:
        raise ValueError("Alokasi kosong")
    if total > remaining + EPS:
        raise ValueError(f"Σ alokasi {rupiah(total)} melebihi sisa titipan {rupiah(remaining)}")

    from services import ar_receipt_service as ar
    from services import gl_service as gl
    done: List[Dict[str, Any]] = []
    for a in allocations:
        order_id, amt = a.get("order_id"), _round(a.get("amount"))
        if not order_id or amt <= 0:
            raise ValueError("Alokasi tidak sah (order_id/amount kosong)")
        # KN-G8-ALLOC-CROSSPT (temuan penutupan fase): alokasi hanya memeriksa BARIS-nya,
        # tidak pernah memeriksa PESANAN tujuannya. Karena `_apply_to_order` mencari pesanan
        # hanya dengan id, titipan PT-A bisa diarahkan melunasi pesanan PT-B lewat id yang
        # dikirim tangan — uang PT-A membayar piutang PT-B, dan jurnalnya pecah di dua buku
        # (Cr Piutang di buku PT-B, Cr Titipan di buku PT-A). Tutup di sini.
        order = await db.sales_orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            raise ValueError("Pesanan tidak ditemukan")
        oent = order.get("entity_id") or ""
        lent = ln.get("entity_id") or ""
        if entity_ids is not None and oent and oent != GROUP_ENTITY and oent not in entity_ids:
            raise HTTPException(status_code=403, detail="Pesanan milik entitas lain")
        if lent and oent and oent != lent and GROUP_ENTITY not in (oent, lent):
            raise HTTPException(
                status_code=403,
                detail=f"Pesanan {order.get('number', order_id)} berada di entitas lain — "
                       "titipan dana hanya boleh melunasi pesanan pada entitas rekening itu")
        if customer_id and order.get("customer_id") and order["customer_id"] != customer_id:
            raise ValueError(
                f"Pesanan {order.get('number', order_id)} bukan milik pelanggan yang dipilih")
        res = await ar.apply_from_bank_holding(order_id, amt, ln["id"],
                                               ln.get("holding", {}).get("cash_number", ""),
                                               {"name": actor})
        je = await gl.post_bank_holding_allocation(
            source_id=f"{ln['id']}:{order_id}:{len(done)}",
            entity_id=res.get("entity_id") or ln.get("entity_id", ""), amount=amt,
            label=f"{res.get('order_number', order_id)}", date=now_iso(), created_by=actor)
        done.append({"order_id": order_id, "order_number": res.get("order_number", ""),
                     "amount": amt, "je_id": (je or {}).get("id", ""),
                     "je_number": (je or {}).get("number", ""),
                     "reason_code": reason_code, "note": note,
                     "customer_id": customer_id, "at": now_iso(), "by": actor,
                     "outstanding_after": res.get("outstanding_after")})
    new_remaining = _round(remaining - total)
    await db.bank_statement_lines.update_one({"id": line_id}, {"$push": {
        "holding_allocated": {"$each": done}}, "$set": {
        "holding_remaining": new_remaining, "customer_id": customer_id,
        "updated_at": now_iso()}})
    return {**safe_doc(await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0})),
            "allocated_now": total, "holding_remaining": new_remaining}


async def cancel_holding(line_id: str, actor: str,
                         entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Batalkan titipan yang BELUM dialokasikan (kas + jurnalnya dibalik).

    Bila sudah ada alokasi, pembatalan ditolak: koreksinya harus lewat amandemen
    (aturan repo #7 — ledger append-only).
    """
    ln = await _line(line_id, entity_ids)
    if ln.get("status") != "holding":
        raise ValueError("Baris ini bukan titipan dana")
    if ln.get("holding_allocated"):
        raise ValueError("Titipan sudah dialokasikan — koreksi harus lewat amandemen")
    from services import gl_service as gl
    hold = ln.get("holding") or {}
    if hold.get("cash_txn_id"):
        await db.cash_transactions.update_one({"id": hold["cash_txn_id"]}, {"$set": {
            "status": "void", "void_reason": "titipan dibatalkan", "updated_at": now_iso()}})
        # KN-G8-CANCEL-JE (temuan penutupan fase): dulu memanggil `gl.void_entry(je_id)` yang
        # MENOLAK jurnal non-manual (`source_type='cash_transaction'`) lalu galatnya ditelan,
        # sehingga kas jadi void tapi jurnal `Dr Bank / Cr 2-1950` tetap hidup → saldo titipan
        # buku besar tidak pernah kembali nol (INV-BNK-03 MERAH). Sekarang dibalik dengan
        # reversing entry (append-only, idempoten) seperti seluruh pembatalan lain di repo.
        await gl.reverse_document("cash_transaction", hold["cash_txn_id"],
                                  reason="titipan dana dibatalkan", actor_name=actor)
    await db.bank_statement_lines.update_one({"id": line_id}, {"$set": {
        "status": "unmatched", "holding": {}, "holding_allocated": [],
        "holding_remaining": 0.0, "updated_at": now_iso()}})
    return safe_doc(await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0}))


async def holding_refunded(line_id: str, amount: float, ref_label: str, actor: str,
                           label: str = "pengembalian dana",
                           entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """FASE G-9 — titipan dana KELUAR dari akun titipan tanpa melunasi piutang.

    Dipakai Pusat Kasus Keuangan untuk dua playbook: **dana dikembalikan ke pengirim**
    dan **settlement antar entitas** (uang ternyata milik PT lain). Jurnalnya diposting
    oleh pemanggil (kas keluar `Dr 2-1950 / Cr Bank`, atau `Dr 2-1950 / Cr 2-1250`),
    fungsi ini hanya menurunkan sisa titipan supaya **INV-BNK-03** tetap sah:
    saldo 2-1950 di buku besar == Σ titipan yang belum dialokasikan.

    Ledger tambah-saja: riwayatnya dicatat di `holding_settled[]`, baris aslinya tidak
    pernah dihapus.
    """
    ln = await _line(line_id, entity_ids)
    if ln.get("status") != "holding":
        raise ValueError("Baris ini bukan titipan dana")
    amt = _round(amount)
    remaining = _round(ln.get("holding_remaining", ln.get("amount")))
    if amt <= 0:
        raise ValueError("Nominal harus lebih dari 0")
    if amt > remaining + EPS:
        raise ValueError(
            f"Nominal {rupiah(amt)} melebihi sisa titipan {rupiah(remaining)}")
    await db.bank_statement_lines.update_one({"id": line_id}, {
        "$push": {"holding_settled": {
            "amount": amt, "kind": label, "ref": ref_label, "by": actor, "at": now_iso()}},
        "$set": {"holding_remaining": _round(remaining - amt), "updated_at": now_iso()}})
    return safe_doc(await db.bank_statement_lines.find_one({"id": line_id}, {"_id": 0}))


async def holding_summary(entity_ids: Optional[List[str]] = None,
                          bank_account_id: str = "") -> Dict[str, Any]:
    """Ringkasan titipan: saldo, umur, dan mana yang perlu ditindaklanjuti."""
    q: Dict[str, Any] = {"status": "holding", **_scope_q(entity_ids)}
    if bank_account_id:
        q["bank_account_id"] = bank_account_id
    rows = await db.bank_statement_lines.find(q, {"_id": 0}).sort("stmt_date", 1).to_list(5000)
    cfg = await load_cfg((entity_ids or [""])[0] if entity_ids else "")
    today = datetime.now(timezone.utc).date()
    items, total, overdue = [], 0.0, 0
    for r in rows:
        rem = _round(r.get("holding_remaining", r.get("amount")))
        d = _d(r.get("stmt_date"))
        # Umur tidak boleh negatif: mutasi bisa bertanggal "besok" (beda zona waktu bank /
        # data demo), dan layar yang menulis "-1 hari" hanya membingungkan pengguna.
        age = max(0, (today - d.date()).days) if d else 0
        stale = age > cfg["holding_max_age_days"] and rem > EPS
        if stale:
            overdue += 1
        total += rem
        items.append({"id": r["id"], "stmt_date": r.get("stmt_date"), "amount": _round(r.get("amount")),
                      "remaining": rem, "age_days": age, "needs_action": stale,
                      "description": r.get("description", ""),
                      "counterparty": r.get("counterparty", ""),
                      "allocated": _round(r.get("amount")) - rem,
                      "bank_account_id": r.get("bank_account_id", ""),
                      "entity_id": r.get("entity_id", "")})
    return {"account_code": cfg["holding_acc"], "max_age_days": cfg["holding_max_age_days"],
            "count": len(items), "needs_action": overdue, "balance": _round(total),
            "items": items}


# ═════════════════════════════════════════════════════════════════════════════
#  BACA (list & ringkasan)
# ═════════════════════════════════════════════════════════════════════════════
async def list_lines(bank_account_id: str, entity_ids: Optional[List[str]] = None,
                     status: Optional[str] = None, start: Optional[str] = None,
                     end: Optional[str] = None) -> List[Dict[str, Any]]:
    # Otorisasi AKUN lebih dulu: memakai id akun PT lain harus DITOLAK terang-terangan
    # (403), bukan dibalas daftar kosong. Daftar kosong menyembunyikan pelanggaran &
    # membuat gate isolasi bisa "hijau palsu" (lihat POC G-8 bagian isolasi).
    await _account(bank_account_id, entity_ids)
    q: Dict[str, Any] = {"bank_account_id": bank_account_id, **_scope_q(entity_ids)}
    if status:
        q["status"] = status
    if start or end:
        rng: Dict[str, str] = {}
        if start:
            rng["$gte"] = start[:10]
        if end:
            rng["$lte"] = end[:10]
        q["stmt_date"] = rng
    lines = await db.bank_statement_lines.find(q, {"_id": 0}).sort("stmt_date", -1).to_list(20000)
    tids = [a["txn_id"] for l in lines for a in (l.get("allocations") or [])]
    tmap: Dict[str, Dict[str, Any]] = {}
    if tids:
        for t in await db.cash_transactions.find({"id": {"$in": tids}}, {"_id": 0}).to_list(20000):
            tmap[t["id"]] = t
    for l in lines:
        allocs = l.get("allocations") or []
        l["matched_txns"] = [{**_txn_brief(tmap[a["txn_id"]]), "allocated": _round(a["amount"])}
                             for a in allocs if a.get("txn_id") in tmap]
        l["matched_txn"] = l["matched_txns"][0] if len(l["matched_txns"]) == 1 else None
        l["allocated_total"] = _round(sum(_round(a.get("amount")) for a in allocs))
    return [safe_doc(l) for l in lines]


async def summary(bank_account_id: str, entity_ids: Optional[List[str]] = None,
                  start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    acc = await _account(bank_account_id, entity_ids)
    lines = await list_lines(bank_account_id, entity_ids, start=start, end=end)
    counted = [l for l in lines if l["status"] != "ignored"]
    stmt_in = _round(sum(l["amount"] for l in counted if l["direction"] == "in"))
    stmt_out = _round(sum(l["amount"] for l in counted if l["direction"] == "out"))
    matched = sum(1 for l in lines if l["status"] == "matched")
    unmatched = sum(1 for l in lines if l["status"] == "unmatched")
    ignored = sum(1 for l in lines if l["status"] == "ignored")
    holding = [l for l in lines if l["status"] == "holding"]
    suggested = sum(1 for l in lines if l["status"] == "unmatched" and (l.get("suggestions") or []))
    unrec_txns = len(await _candidate_txns(bank_account_id, entity_ids))
    book_in = book_out = 0.0
    for t in await db.cash_transactions.find(
            _book_query(acc, entity_ids), {"_id": 0}).to_list(20000):
        amt = _round(t.get("amount"))
        if t.get("direction") == "in":
            book_in += amt
        else:
            book_out += amt
    stmt_net, book_net = _round(stmt_in - stmt_out), _round(book_in - book_out)
    hold = await holding_summary(entity_ids, bank_account_id)
    return {
        "bank_account_id": bank_account_id, "account_name": acc.get("name", ""),
        "entity_id": acc.get("entity_id", ""),
        "period": {"start": start or "", "end": end or ""},
        "statement": {"in": stmt_in, "out": stmt_out, "net": stmt_net, "lines": len(lines)},
        "book": {"in": _round(book_in), "out": _round(book_out), "net": book_net},
        "matched": matched, "unmatched_lines": unmatched, "ignored": ignored,
        "suggested": suggested,
        "holding": {"count": len(holding), "balance": hold["balance"],
                    "needs_action": hold["needs_action"], "account_code": hold["account_code"]},
        "unmatched_book_txns": unrec_txns,
        "difference": _round(stmt_net - book_net),
        "fully_reconciled": unmatched == 0 and unrec_txns == 0 and len(lines) > 0,
        "generated_at": now_iso(),
    }
