"""FASE B — REGISTRY KONVERSI SATUAN **GLOBAL** + TOLERANSI (D-06/D-07).

Rujukan: `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` §3 (rumus baku) & §11
(D-06 basis tarif bebas, D-07 **wajib jejak konversi**) · `docs/KN_22_PLAN_FASE_B_UOM.md`.

Keputusan pemilik (sesi 2026-07-25):
  * “konversi dibuatkan **global** saja dengan opsi yang luas/banyak” → SATU registry
    global `uom_conversion_rules` (bukan tabel per kontrak/mitra).
  * “toleransi **bisa dikonfigurasi**” → `system_settings` scope `uom`
    (`warn_pct`, `block_pct`, `allow_override`, `precision`).

ATURAN SSOT (R3) — modul ini TIDAK menghitung ulang matematika konversi.
Matematika tetap di `services/uom_service.py` (mesin Sub-fase 1.13 yang sudah ada);
modul ini menambah:
  1. registry aturan GLOBAL yang bisa dikelola user (CRUD + aktif/nonaktif),
  2. katalog satuan yang luas (panjang/berat/hitungan/luas),
  3. **jejak konversi** (`uom_trail`) yang wajib disimpan di dokumen (D-07),
  4. kebijakan **toleransi selisih** konversi vs ukur/timbang aktual (warn/block),
  5. seeding idempoten aturan fisika (bukan angka karangan).

Urutan resolusi faktor (paling spesifik → paling umum):
  product.uom_conversions[]  →  aturan GLOBAL aktif  →  formula (GSM × lebar)  →
  konstanta panjang kanonik  →  400 (tidak pernah diam-diam memakai 1).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from db import db
from core_utils import new_id, now_iso, parse_decimal
from services import uom_service

SETTINGS_SCOPE = "uom"
RULES_COLL = "uom_conversion_rules"

# ── Katalog satuan (luas & bisa ditambah user lewat master UOM) ───────────────
# `dimension` dipakai UI untuk mengelompokkan + memvalidasi aturan sejenis.
UNIT_CATALOG: List[Dict[str, Any]] = [
    # panjang
    {"code": "meter", "label": "Meter (m)", "dimension": "length", "aliases": ["m", "mtr"]},
    {"code": "yard", "label": "Yard (yd)", "dimension": "length", "aliases": ["yd", "yrd"]},
    {"code": "cm", "label": "Centimeter (cm)", "dimension": "length", "aliases": ["centimeter"]},
    {"code": "mm", "label": "Milimeter (mm)", "dimension": "length", "aliases": ["milimeter"]},
    {"code": "inch", "label": "Inci (in)", "dimension": "length", "aliases": ["in", "inci"]},
    {"code": "feet", "label": "Kaki (ft)", "dimension": "length", "aliases": ["ft", "kaki"]},
    {"code": "km", "label": "Kilometer (km)", "dimension": "length", "aliases": []},
    # berat
    {"code": "kg", "label": "Kilogram (kg)", "dimension": "weight", "aliases": ["kilo", "kilogram"]},
    {"code": "gram", "label": "Gram (g)", "dimension": "weight", "aliases": ["g", "gr"]},
    {"code": "ton", "label": "Ton (t)", "dimension": "weight", "aliases": ["tonne"]},
    {"code": "lbs", "label": "Pound (lbs)", "dimension": "weight", "aliases": ["pound", "lb"]},
    {"code": "ounce", "label": "Ounce (oz)", "dimension": "weight", "aliases": ["oz"]},
    # hitungan / kemasan
    {"code": "piece", "label": "Piece / Pcs", "dimension": "count", "aliases": ["pcs", "pc", "buah"]},
    {"code": "dozen", "label": "Lusin (12 pcs)", "dimension": "count", "aliases": ["lusin"]},
    {"code": "gross", "label": "Gross (144 pcs)", "dimension": "count", "aliases": ["kodi_gross"]},
    {"code": "roll", "label": "Roll", "dimension": "count", "aliases": ["rol", "rll"]},
    {"code": "bale", "label": "Bal / Bale", "dimension": "count", "aliases": ["bal", "ball"]},
    {"code": "cone", "label": "Cone (benang)", "dimension": "count", "aliases": ["kon"]},
    {"code": "box", "label": "Box / Karton", "dimension": "count", "aliases": ["karton", "dus"]},
    {"code": "pack", "label": "Pack", "dimension": "count", "aliases": ["paket"]},
    {"code": "lot", "label": "Lot (borongan)", "dimension": "count", "aliases": []},
    # luas
    {"code": "m2", "label": "Meter persegi (m²)", "dimension": "area", "aliases": ["sqm", "meter2"]},
    {"code": "sqft", "label": "Square feet (ft²)", "dimension": "area", "aliases": ["ft2"]},
]
UNIT_BY_CODE = {u["code"]: u for u in UNIT_CATALOG}
DIMENSIONS = [
    {"value": "length", "label": "Panjang"},
    {"value": "weight", "label": "Berat"},
    {"value": "count", "label": "Hitungan / Kemasan"},
    {"value": "area", "label": "Luas"},
    {"value": "cross", "label": "Lintas dimensi (butuh spesifikasi produk)"},
]
RULE_KINDS = [
    {"value": "fixed", "label": "Faktor tetap (fisika/standar)",
     "note": "Berlaku untuk semua produk — mis. 1 yard = 0,9144 meter"},
    {"value": "pack", "label": "Ukuran kemasan (roll/bal/cone/box)",
     "note": "Nilai umum perusahaan; dapat ditimpa per produk lewat master produk"},
    {"value": "formula", "label": "Formula (GSM × lebar)",
     "note": "Panjang ↔ berat memakai gramasi & lebar produk (KN_18 §3)"},
]
FORMULAS = [{"value": "gsm_width", "label": "GSM × lebar ÷ 1000 (kg per meter)"}]

# Aturan FISIKA/standar (bukan angka karangan) — di-seed idempoten.
CANONICAL_RULES: List[Dict[str, Any]] = [
    # panjang (basis meter)
    {"from_unit": "yard", "to_unit": "meter", "factor": 0.9144, "dimension": "length"},
    {"from_unit": "cm", "to_unit": "meter", "factor": 0.01, "dimension": "length"},
    {"from_unit": "mm", "to_unit": "meter", "factor": 0.001, "dimension": "length"},
    {"from_unit": "inch", "to_unit": "meter", "factor": 0.0254, "dimension": "length"},
    {"from_unit": "feet", "to_unit": "meter", "factor": 0.3048, "dimension": "length"},
    {"from_unit": "km", "to_unit": "meter", "factor": 1000.0, "dimension": "length"},
    # berat (basis kg)
    {"from_unit": "gram", "to_unit": "kg", "factor": 0.001, "dimension": "weight"},
    {"from_unit": "ton", "to_unit": "kg", "factor": 1000.0, "dimension": "weight"},
    {"from_unit": "lbs", "to_unit": "kg", "factor": 0.45359237, "dimension": "weight"},
    {"from_unit": "ounce", "to_unit": "kg", "factor": 0.0283495231, "dimension": "weight"},
    # hitungan
    {"from_unit": "dozen", "to_unit": "piece", "factor": 12.0, "dimension": "count"},
    {"from_unit": "gross", "to_unit": "piece", "factor": 144.0, "dimension": "count"},
    # luas
    {"from_unit": "sqft", "to_unit": "m2", "factor": 0.09290304, "dimension": "area"},
]
CANONICAL_FORMULA_RULES: List[Dict[str, Any]] = [
    {"from_unit": "meter", "to_unit": "kg", "kind": "formula", "formula": "gsm_width",
     "dimension": "cross",
     "note": "kg = meter × (GSM × lebar ÷ 1000) — butuh gramasi & lebar produk (KN_18 §3.1)"},
]

DEFAULT_SETTINGS: Dict[str, Any] = {
    "warn_pct": 2.0,        # selisih ≥ ini → peringatan + needs_review
    "block_pct": 5.0,       # selisih ≥ ini → DITOLAK (kecuali override diizinkan + alasan)
    "allow_override": True,  # manager/admin boleh melanjutkan dengan alasan
    "precision": 2,          # pembulatan hasil konversi
    "require_trail": True,   # dokumen wajib menyimpan jejak konversi (D-07)
}


class UomRuleError(ValueError):
    """Kesalahan aturan/konversi → dipetakan ke HTTP 400 oleh router."""


def _norm(u: Any) -> str:
    return str(u or "").strip().lower()


def normalize_unit(raw: Any) -> str:
    """Samakan alias satuan ke kode kanonik ('yd' → 'yard', 'pcs' → 'piece')."""
    text = _norm(raw)
    if not text:
        return ""
    if text in UNIT_BY_CODE:
        return text
    for u in UNIT_CATALOG:
        if text in [_norm(a) for a in u.get("aliases", [])]:
            return u["code"]
    return text          # satuan bebas dari master UOM tetap diterima (tidak dipaksa)


def unit_dimension(unit: Any) -> str:
    return (UNIT_BY_CODE.get(normalize_unit(unit), {}) or {}).get("dimension", "")


# ═══ Pengaturan toleransi (configurable — keputusan pemilik) ═════════════════
async def get_settings(entity_id: str = "") -> Dict[str, Any]:
    """Kebijakan efektif. FASE E-4 (E4.5): bila `entity_id` diisi, setelan khusus
    badan usaha itu MENIMPA nilai global — dulu satu nilai memaksa seluruh grup.
    Tanpa `entity_id` perilakunya identik dengan sebelumnya (nol risiko regresi).
    """
    doc = await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 0}) or {}
    out = dict(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        if doc.get(k) is not None:
            out[k] = doc[k]
    out["updated_at"] = doc.get("updated_at", "")
    out["updated_by"] = doc.get("updated_by", "")
    if entity_id and entity_id != "all":
        from services.config_resolver import entity_overlay
        ovr = await entity_overlay(SETTINGS_SCOPE, entity_id) or {}
        for _k, _v in ovr.items():
            if _k in DEFAULT_SETTINGS:
                out[_k] = _v
        out["entity_id"] = entity_id
        # Daftar kunci yang benar-benar ditimpa — dipakai UI untuk lencana asal nilai.
        out["entity_overrides"] = sorted(_k for _k in ovr if _k in DEFAULT_SETTINGS)
    return out


async def update_settings(payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    """Ubah kebijakan toleransi. Validasi: 0 < warn ≤ block ≤ 100."""
    cur = await get_settings()
    nxt = dict(cur)
    for key in ("warn_pct", "block_pct"):
        if payload.get(key) is not None:
            nxt[key] = round(parse_decimal(payload[key]), 3)
    for key in ("allow_override", "require_trail"):
        if payload.get(key) is not None:
            nxt[key] = bool(payload[key])
    if payload.get("precision") is not None:
        nxt["precision"] = int(payload["precision"])
    if not (0 < float(nxt["warn_pct"]) <= float(nxt["block_pct"]) <= 100):
        raise UomRuleError(
            "Toleransi tidak sah: syaratnya 0 < toleransi peringatan ≤ toleransi blokir ≤ 100 "
            f"(diberikan peringatan {nxt['warn_pct']}%, blokir {nxt['block_pct']}%).")
    if not (0 <= int(nxt["precision"]) <= 6):
        raise UomRuleError("Pembulatan (precision) harus 0–6 angka desimal.")
    await db.system_settings.update_one(
        {"scope": SETTINGS_SCOPE},
        {"$set": {**{k: nxt[k] for k in DEFAULT_SETTINGS},
                  "updated_at": now_iso(), "updated_by": actor},
         "$setOnInsert": {"id": new_id("set"), "scope": SETTINGS_SCOPE}},
        upsert=True)
    return await get_settings()


# ═══ Registry aturan GLOBAL ═════════════════════════════════════════════════
async def list_rules(status: str = "", dimension: str = "", kind: str = "") -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if dimension:
        q["dimension"] = dimension
    if kind:
        q["kind"] = kind
    rows = await db[RULES_COLL].find(q, {"_id": 0}).sort("from_unit", 1).to_list(2000)
    return rows


def _validate_rule(doc: Dict[str, Any]) -> Dict[str, Any]:
    kind = _norm(doc.get("kind")) or "fixed"
    if kind not in [k["value"] for k in RULE_KINDS]:
        raise UomRuleError(
            f"Jenis aturan '{kind}' tidak dikenal. Pilihan: "
            + ", ".join(k["value"] for k in RULE_KINDS))
    fu, tu = normalize_unit(doc.get("from_unit")), normalize_unit(doc.get("to_unit"))
    if not fu or not tu:
        raise UomRuleError("Satuan asal dan satuan tujuan wajib diisi.")
    if fu == tu:
        raise UomRuleError("Satuan asal dan tujuan tidak boleh sama.")
    out = {**doc, "from_unit": fu, "to_unit": tu, "kind": kind}
    if kind == "formula":
        formula = _norm(doc.get("formula")) or "gsm_width"
        if formula not in [f["value"] for f in FORMULAS]:
            raise UomRuleError(f"Formula '{formula}' tidak dikenal.")
        out["formula"] = formula
        out["factor"] = 0.0
        out["dimension"] = doc.get("dimension") or "cross"
    else:
        try:
            factor = parse_decimal(doc.get("factor"), places=8)
        except ValueError as exc:
            raise UomRuleError("Faktor harus berupa angka (mis. 0,9144).") from exc
        if factor <= 0:
            raise UomRuleError("Faktor konversi harus lebih besar dari 0.")
        out["factor"] = factor
        out["formula"] = ""
        dim_f, dim_t = unit_dimension(fu), unit_dimension(tu)
        out["dimension"] = doc.get("dimension") or (
            dim_f if (dim_f and dim_f == dim_t) else ("cross" if dim_f and dim_t else dim_f or dim_t or "count"))
        if kind == "fixed" and dim_f and dim_t and dim_f != dim_t:
            raise UomRuleError(
                f"Faktor tetap hanya untuk satuan sedimensi ({dim_f} vs {dim_t}). "
                "Untuk lintas dimensi (mis. meter ↔ kg) gunakan jenis 'formula', atau "
                "'pack' bila ini ukuran kemasan.")
    out["label"] = str(doc.get("label") or "").strip() or (
        f"1 {fu} = {out['factor']:g} {tu}" if kind != "formula" else f"{fu} ↔ {tu} (formula)")
    out["note"] = str(doc.get("note") or "").strip()
    out["status"] = _norm(doc.get("status")) or "active"
    if out["status"] not in ("active", "inactive"):
        raise UomRuleError("Status aturan hanya 'active' atau 'inactive'.")
    return out


async def create_rule(payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    doc = _validate_rule(dict(payload))
    dupe = await db[RULES_COLL].find_one(
        {"from_unit": doc["from_unit"], "to_unit": doc["to_unit"], "status": "active"},
        {"_id": 0, "id": 1, "label": 1})
    if dupe and doc["status"] == "active":
        raise UomRuleError(
            f"Aturan aktif untuk {doc['from_unit']} → {doc['to_unit']} sudah ada "
            f"({dupe.get('label')}). Ubah aturan itu atau nonaktifkan dulu "
            "(satu pasangan satuan = satu aturan aktif).")
    doc.update({"id": new_id("uomr"), "created_by": actor, "created_at": now_iso(),
                "updated_at": now_iso(), "source": doc.get("source") or "user"})
    await db[RULES_COLL].insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def update_rule(rule_id: str, payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    cur = await db[RULES_COLL].find_one({"id": rule_id}, {"_id": 0})
    if not cur:
        raise UomRuleError("Aturan konversi tidak ditemukan.")
    merged = {**cur, **{k: v for k, v in (payload or {}).items() if v is not None}}
    doc = _validate_rule(merged)
    if doc["status"] == "active":
        dupe = await db[RULES_COLL].find_one(
            {"from_unit": doc["from_unit"], "to_unit": doc["to_unit"], "status": "active",
             "id": {"$ne": rule_id}}, {"_id": 0, "label": 1})
        if dupe:
            raise UomRuleError(
                f"Aturan aktif untuk {doc['from_unit']} → {doc['to_unit']} sudah ada "
                f"({dupe.get('label')}).")
    doc["updated_at"] = now_iso()
    doc["updated_by"] = actor
    await db[RULES_COLL].update_one({"id": rule_id}, {"$set": {
        k: doc[k] for k in ("from_unit", "to_unit", "kind", "factor", "formula", "dimension",
                            "label", "note", "status", "updated_at", "updated_by")}})
    return await db[RULES_COLL].find_one({"id": rule_id}, {"_id": 0})


async def set_rule_status(rule_id: str, status: str, actor: str = "") -> Dict[str, Any]:
    if _norm(status) not in ("active", "inactive"):
        raise UomRuleError("Status hanya 'active' atau 'inactive'.")
    return await update_rule(rule_id, {"status": _norm(status)}, actor)


async def load_pair_rules() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Peta {(from,to) → {factor, rule_id, kind}} dari aturan GLOBAL yang AKTIF."""
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in await db[RULES_COLL].find({"status": "active"}, {"_id": 0}).to_list(2000):
        if r.get("kind") == "formula":
            continue
        try:
            f = float(r.get("factor") or 0)
        except (TypeError, ValueError):
            continue
        if f <= 0:
            continue
        out[(_norm(r.get("from_unit")), _norm(r.get("to_unit")))] = {
            "factor": f, "rule_id": r.get("id"), "kind": r.get("kind"), "label": r.get("label")}
    return out


async def load_engine() -> Dict[str, Any]:
    """Muat sekali per request: faktor FIXED (uoms) + aturan pasangan GLOBAL + setting."""
    fixed = await uom_service.load_fixed_factors()
    pairs = await load_pair_rules()
    settings = await get_settings()
    return {"fixed": fixed, "pairs": pairs, "settings": settings}


# ═══ Konversi + JEJAK (D-07) ════════════════════════════════════════════════
async def convert_with_trail(product: Dict[str, Any], qty: Any, from_unit: str,
                             to_unit: str = "", engine: Optional[Dict[str, Any]] = None,
                             context: str = "") -> Dict[str, Any]:
    """Konversi + kembalikan **jejak** siap-simpan (`uom_trail`).

    Jejak berisi: satuan & qty dokumen (apa yang diketik user), satuan & qty dasar
    (yang dipakai stok/laporan), faktor, sumber faktor, dan waktu konversi —
    memenuhi kewajiban D-07 (“wajib jejak konversi”).
    """
    eng = engine or await load_engine()
    base_unit = normalize_unit(product.get("base_unit") or "meter")
    target = normalize_unit(to_unit) or base_unit
    src_unit = normalize_unit(from_unit) or base_unit
    q = parse_decimal(qty)
    precision = int(eng["settings"].get("precision", 2))

    resolved = uom_service.resolve_factor(
        product, src_unit, target, eng["fixed"], pair_rules=eng["pairs"])
    if resolved is None:
        raise UomRuleError(
            f"Konversi '{src_unit}' → '{target}' belum punya aturan untuk produk "
            f"{product.get('sku') or product.get('id') or '-'}. Tambahkan aturan di "
            "Produk & Harga → Konversi Satuan, atau isi gramasi & lebar produk "
            "(untuk konversi panjang ↔ berat).")
    factor = float(resolved["factor"])
    base_qty = round(q * factor, precision)
    return {
        "doc_uom": src_unit, "doc_qty": round(q, precision),
        "base_uom": target, "base_qty": base_qty,
        "factor": round(factor, 8), "source": resolved["source"],
        "rule_id": resolved.get("rule_id", ""), "formula": resolved.get("formula", ""),
        "path": resolved.get("path", []),
        "context": context, "converted_at": now_iso(),
    }


def variance_pct(expected: Any, actual: Any) -> Optional[float]:
    """Selisih % actual vs expected (None bila expected 0/kosong)."""
    e, a = parse_decimal(expected), parse_decimal(actual)
    if e == 0:
        return None
    return round((a - e) / e * 100.0, 3)


async def check_variance(expected: Any, actual: Any, settings: Optional[Dict[str, Any]] = None,
                         label: str = "hasil konversi") -> Dict[str, Any]:
    """Bandingkan hasil konversi vs ukur/timbang AKTUAL memakai toleransi configurable.

    Level: `ok` · `warn` (≥ warn_pct → tandai `needs_review`) · `block` (≥ block_pct →
    ditolak, kecuali `allow_override` + alasan).
    """
    st = settings or await get_settings()
    pct = variance_pct(expected, actual)
    if pct is None:
        return {"level": "ok", "variance_pct": None, "message": "",
                "warn_pct": st["warn_pct"], "block_pct": st["block_pct"]}
    ab = abs(pct)
    level = "ok"
    if ab >= float(st["block_pct"]):
        level = "block"
    elif ab >= float(st["warn_pct"]):
        level = "warn"
    msg = ""
    if level != "ok":
        arah = "lebih besar" if pct > 0 else "lebih kecil"
        msg = (f"Aktual {arah} {ab:.2f}% dari {label} "
               f"(perkiraan {parse_decimal(expected):g} vs aktual {parse_decimal(actual):g}). "
               + ("Melebihi batas blokir "
                  f"{float(st['block_pct']):g}% — periksa timbangan/ukuran atau perbaiki "
                  "faktor konversi produk."
                  if level == "block" else
                  f"Melebihi toleransi {float(st['warn_pct']):g}% — ditandai perlu ditinjau."))
    return {"level": level, "variance_pct": pct, "message": msg,
            "warn_pct": st["warn_pct"], "block_pct": st["block_pct"],
            "allow_override": bool(st.get("allow_override", True))}


# ═══ Seeding idempoten (dipakai bootstrap + migrasi) ════════════════════════
async def ensure_defaults(actor: str = "system") -> Dict[str, Any]:
    """Pasang aturan fisika standar + pengaturan toleransi bila belum ada (idempoten)."""
    created, existing = 0, 0
    for r in CANONICAL_RULES + CANONICAL_FORMULA_RULES:
        fu, tu = normalize_unit(r["from_unit"]), normalize_unit(r["to_unit"])
        found = await db[RULES_COLL].find_one({"from_unit": fu, "to_unit": tu}, {"_id": 0, "id": 1})
        if found:
            existing += 1
            continue
        doc = _validate_rule({
            "from_unit": fu, "to_unit": tu, "kind": r.get("kind", "fixed"),
            "factor": r.get("factor", 0), "formula": r.get("formula", ""),
            "dimension": r.get("dimension", ""), "note": r.get("note", ""),
            "status": "active",
        })
        doc.update({"id": new_id("uomr"), "created_by": actor, "created_at": now_iso(),
                    "updated_at": now_iso(), "source": "standard"})
        await db[RULES_COLL].insert_one(dict(doc))
        created += 1
    if not await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 0, "id": 1}):
        await db.system_settings.insert_one({
            "id": new_id("set"), "scope": SETTINGS_SCOPE, **DEFAULT_SETTINGS,
            "updated_at": now_iso(), "updated_by": actor})
    return {"rules_created": created, "rules_existing": existing}


def catalog_snapshot() -> Dict[str, Any]:
    """Payload katalog untuk FE (satu panggilan)."""
    return {"units": UNIT_CATALOG, "dimensions": DIMENSIONS,
            "kinds": RULE_KINDS, "formulas": FORMULAS}
