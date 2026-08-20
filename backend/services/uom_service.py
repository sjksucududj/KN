"""Sub-fase 1.13 — UOM Conversion Engine (Multi-UOM).

Mendukung konversi multi-unit untuk penjualan/pembelian kain:
- FIXED (global, dari koleksi `uoms.factor_to_base` + kanonik): meter=1, yard=0.9144,
  cm=0.01, inch=0.0254. (base_type = length)
- VARIABLE (per produk, dari `product.uom_conversions[]`): mis. 1 roll = 50 m
  ({from_unit:"roll", to_unit:"meter", factor:50}). Beda tiap produk.

Resolusi faktor: unit sama → 1.0 → FIXED langsung → VARIABLE langsung → 1-hop via base unit.
Jika tidak ada faktor → HTTPException 400 (TIDAK diam-diam pakai 1).

Semua qty inventori/reservasi/movement SELALU disimpan dalam BASE UNIT produk (default meter).
Fungsi inti bersifat pure (tanpa I/O) supaya mudah diuji; `load_fixed_factors()` async hanya
membaca peta faktor FIXED dari DB sekali per request.
"""
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from db import db

# ═════════════════════════════════════════════════════════════════════════════
# FASE U — SATU DAFTAR BENIH SATUAN (SSOT) + `aliases`
# ═════════════════════════════════════════════════════════════════════════════
# MASALAH YANG DITUTUP (D1, terukur 2026-08-18 & diverifikasi ulang 2026-08-19):
#   * Dokumen menyimpan satuan sebagai **kata**: `yard` · `kg` · `meter`.
#     Master `uoms` menyimpan **kode**: `MTR` · `YRD` · `RLL` · `PCS`.
#     Jadi TAK SATU PUN nilai satuan yang tersimpan di 17 tempat dokumen cocok dengan
#     baris master — menambah baris `KG` di master **tidak mengubah apa pun di layar**,
#     dan pemilik tidak punya cara menambah satuan yang benar-benar dipakai dokumen.
#   * Daftar benihnya ada DUA (K1): `bootstrap.py` menanam 6 baris (MTR·YRD·CM·INCH·RLL·PCS,
#     ber-`factor_to_base`) sementara `seed_realistic.seed_uoms()` menanam 4 baris TANPA
#     faktor. Jumlah baris master karena itu bergantung urutan "restart vs seed" —
#     `CM`/`INCH` bisa ada atau hilang tanpa ada yang mengubah kode.
#
# KEPUTUSAN: satu daftar benih di SINI (dipakai `bootstrap.seed/sync` DAN
# `seed_realistic.seed_uoms`), dan setiap baris punya `aliases[]` = kosakata yang
# BENAR-BENAR tersimpan di dokumen. Master tetap boleh ditambah pemilik lewat
# `/api/uoms` (master menang; benih hanya jaring pengaman instalasi baru) — pola
# yang sama dengan FASE T (`domain_registry` = benih, koleksi master = nilai hidup).
#
# `factor_per_document=True` (hanya `PANEL`) — keputusan pemilik 2026-08-19:
# "panjang 1 panel BERBEDA PER PESANAN", jadi faktornya boleh ditulis di BARIS
# DOKUMEN. Sengaja jadi field MASTER, bukan hardcode nama satuan, supaya tidak lahir
# pintu ke-3: baris dokumen hanya boleh membawa faktor untuk satuan yang masternya
# menyatakan demikian.
UOM_SEED_ROWS: List[Dict[str, Any]] = [
    {"id": "uom_meter", "code": "MTR", "name": "Meter", "base_type": "length",
     "precision": 2, "factor_to_base": 1.0, "aliases": ["meter", "m", "mtr"]},
    {"id": "uom_yard", "code": "YRD", "name": "Yard", "base_type": "length",
     "precision": 2, "factor_to_base": 0.9144, "aliases": ["yard", "yd", "yrd"]},
    {"id": "uom_cm", "code": "CM", "name": "Cm", "base_type": "length",
     "precision": 2, "factor_to_base": 0.01, "aliases": ["cm", "centimeter"]},
    {"id": "uom_inch", "code": "INCH", "name": "Inch", "base_type": "length",
     "precision": 2, "factor_to_base": 0.0254, "aliases": ["inch", "in", "inci"]},
    # `RLL` dulu ber-`base_type="volume"` — dimensi yang tidak dipakai mesin konversi
    # mana pun (roll adalah HITUNGAN). Dirapikan ke `count`, idempotent.
    {"id": "uom_roll", "code": "RLL", "name": "Roll", "base_type": "count",
     "precision": 0, "factor_to_base": 1.0, "aliases": ["roll", "rll", "rol", "gulung"]},
    {"id": "uom_pcs", "code": "PCS", "name": "Pcs", "base_type": "count",
     "precision": 0, "factor_to_base": 1.0, "aliases": ["pcs", "pc", "piece", "buah"]},
    {"id": "uom_kg", "code": "KG", "name": "Kilogram", "base_type": "weight",
     "precision": 2, "factor_to_base": 1.0, "aliases": ["kg", "kilogram", "kilo"]},
    {"id": "uom_panel", "code": "PANEL", "name": "Panel", "base_type": "count",
     "precision": 0, "factor_to_base": 1.0, "aliases": ["panel", "pnl"],
     "factor_per_document": True},
]

# Faktor length kanonik (meter per 1 unit) — fallback bila uoms belum punya factor_to_base.
CANONICAL_LENGTH_FACTORS: Dict[str, float] = {
    "meter": 1.0, "m": 1.0, "mtr": 1.0,
    "yard": 0.9144, "yd": 0.9144, "yrd": 0.9144,
    "cm": 0.01, "centimeter": 0.01,
    "inch": 0.0254, "in": 0.0254,
}


def _norm(u: Optional[str]) -> str:
    return (u or "").strip().lower()


# ═════════════════════════════════════════════════════════════════════════════
# FASE U — PEMBACA KOSAKATA SATUAN (master `uoms` + alias), cache 60 detik
# ═════════════════════════════════════════════════════════════════════════════
# Satu pembaca untuk semua yang perlu tahu "apakah satuan ini dikenal, dan apa
# kode kanoniknya": `routers/uoms.py` (validasi alias kembar), gate `INV-UOM-02`,
# `load_fixed_factors()`, dan pembulatan tampilan (`precision`).
_VOCAB_CACHE: Dict[str, Any] = {"at": 0.0, "rows": None}
_VOCAB_TTL = 60.0


def invalidate_vocab() -> None:
    """Dipanggil `routers/uoms.py` sesudah create/patch/delete master satuan."""
    _VOCAB_CACHE["rows"] = None
    _VOCAB_CACHE["at"] = 0.0


async def load_uom_rows(force: bool = False) -> List[Dict[str, Any]]:
    import time
    now = time.time()
    if (not force) and _VOCAB_CACHE["rows"] is not None and (now - _VOCAB_CACHE["at"]) < _VOCAB_TTL:
        return _VOCAB_CACHE["rows"]
    rows = await db.uoms.find({}, {"_id": 0}).to_list(500)
    _VOCAB_CACHE["rows"] = rows
    _VOCAB_CACHE["at"] = now
    return rows


def vocab_from_rows(rows: List[Dict[str, Any]], active_only: bool = True) -> Dict[str, Dict[str, Any]]:
    """Peta {kata satuan (huruf kecil) -> baris master} dari `code`, `name`, dan `aliases`.

    Satu baris master menyumbang BANYAK kunci — itu inti perbaikan D1: dokumen
    menulis `yard`, master menyimpan `YRD`; keduanya menunjuk baris yang sama.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if active_only and (r.get("status") or "active") != "active":
            continue
        keys = [r.get("code"), r.get("name")] + list(r.get("aliases") or [])
        for k in keys:
            k = _norm(k)
            if k:
                out.setdefault(k, r)
    return out


async def load_vocab(active_only: bool = True) -> Dict[str, Dict[str, Any]]:
    return vocab_from_rows(await load_uom_rows(), active_only=active_only)


async def canonical_unit(raw: Any) -> str:
    """Kode master kanonik untuk satuan apa pun ('yard' → 'YRD'); '' bila tak dikenal."""
    hit = (await load_vocab()).get(_norm(raw if isinstance(raw, str) else str(raw or "")))
    return str(hit.get("code") or "") if hit else ""


# ── Di mana kata satuan BENAR-BENAR tersimpan (SSOT untuk gate INV-UOM-02 & pagar
#    penonaktifan satuan). Diukur dari basis data 2026-08-19, bukan dikira-kira.
UNIT_DOC_FIELDS: Dict[str, List[str]] = {
    "sales_orders": ["items.unit"],
    "purchase_orders": ["items.unit"],
    "purchase_requisitions": ["items.unit"],
    "rfqs": ["items.unit"],
    "sales_returns": ["items.unit"],
    "purchase_returns": ["items.unit"],
    "warehouse_transfers": ["items.unit"],
    "interco_transactions": ["items.unit"],
    "interco_returns": ["items.unit"],
    "internal_requests": ["items.unit"],
    "inventory_rolls": ["unit"],
    "inventory_movements": ["unit"],
    "wms_tasks": ["unit"],
    "shipments": ["unit"],
    "makloon_orders": ["material_unit", "steps.input_unit", "steps.output_unit"],
    "products": ["base_unit"],
}


async def count_unit_usage(words: List[str]) -> Dict[str, int]:
    """Berapa dokumen memakai salah satu `words` sebagai satuan, per koleksi.

    Dipakai dua tempat: (a) pagar `DELETE /api/uoms/{id}` — satuan yang masih dipakai
    dokumen tidak boleh dinonaktifkan (aturan yang sama dengan tahap proses di FASE T);
    (b) gate `INV-UOM-02` untuk menyebut JUMLAH pemakainya, bukan sekadar "ada".
    """
    keys = [w for w in {(_norm(w)) for w in words} if w]
    if not keys:
        return {}
    variants = sorted({*keys, *[k.upper() for k in keys], *[k.capitalize() for k in keys]})
    out: Dict[str, int] = {}
    for col, fields in UNIT_DOC_FIELDS.items():
        n = 0
        for f in fields:
            n += await db[col].count_documents({f: {"$in": variants}})
        if n:
            out[col] = n
    return out


async def load_fixed_factors() -> Dict[str, float]:
    """Peta {unit(lowercase) -> meter per 1 unit} dari uoms (base_type=length) + kanonik.

    FASE U: kunci diambil dari `code`, `name`, **dan `aliases`** — sebelum ini hanya
    `name`/`code`, sehingga baris master `YRD` tidak pernah cocok dengan nilai `yard`
    yang tersimpan di dokumen (D1). Sekaligus mengisi cache faktor BERAT dari master
    (`base_type="weight"`), supaya satuan berat baru yang ditambah pemilik ikut
    dikenali `kg_per_base_unit()` tanpa mengubah kode.
    """
    factors: Dict[str, float] = dict(CANONICAL_LENGTH_FACTORS)
    rows = await load_uom_rows()
    weights: Dict[str, float] = {}
    for u in rows:
        if (u.get("status") or "active") != "active":
            continue
        f = u.get("factor_to_base")
        base_type = _norm(u.get("base_type"))
        keys = [u.get("name"), u.get("code")] + list(u.get("aliases") or [])
        if base_type == "length":
            if f in (None, 0):
                continue
            for key in keys:
                if key:
                    factors[_norm(key)] = float(f)
        elif base_type == "weight" and f not in (None, 0):
            for key in keys:
                if key:
                    weights[_norm(key)] = float(f)
    if weights:
        _WEIGHT_MASTER.clear()
        _WEIGHT_MASTER.update(weights)
    return factors


def _fixed(from_u: str, to_u: str, fixed: Dict[str, float]) -> Optional[float]:
    a, b = fixed.get(from_u), fixed.get(to_u)
    if a is not None and b not in (None, 0):
        return a / b
    return None


def _pair(from_u: str, to_u: str,
          pair_rules: Optional[Dict[Any, Any]]) -> Optional[Dict[str, Any]]:
    """FASE B — faktor dari registry aturan GLOBAL (`uom_conversion_rules`).

    `pair_rules` = {(from,to): {factor, rule_id, kind}} (lihat
    `services/uom_rules_service.load_pair_rules`). Aturan dianggap dua arah:
    bila hanya ada (to,from), dipakai kebalikannya.
    """
    if not pair_rules:
        return None
    hit = pair_rules.get((from_u, to_u))
    if hit and float(hit.get("factor") or 0) > 0:
        return {"factor": float(hit["factor"]), "rule_id": hit.get("rule_id", ""),
                "kind": hit.get("kind", "fixed"), "reversed": False}
    rev = pair_rules.get((to_u, from_u))
    if rev and float(rev.get("factor") or 0) > 0:
        return {"factor": 1.0 / float(rev["factor"]), "rule_id": rev.get("rule_id", ""),
                "kind": rev.get("kind", "fixed"), "reversed": True}
    return None


def _variable(product: Dict[str, Any], from_u: str, to_u: str) -> Optional[float]:
    for c in product.get("uom_conversions", []) or []:
        cf, ct, fac = _norm(c.get("from_unit")), _norm(c.get("to_unit")), c.get("factor")
        if not fac:
            continue
        if cf == from_u and ct == to_u:
            return float(fac)
        if cf == to_u and ct == from_u and float(fac) != 0:
            return 1.0 / float(fac)
    return None


# FASE F-1 — base unit yang MEMANG satuan berat: kg per 1 base unit = fisika murni
# (tidak butuh gramasi/lebar). Dipakai `kg_per_base_unit()` agar penerimaan produk
# per-kg (benang, obat celup) tidak lagi mustahil diselesaikan.
WEIGHT_BASE_KG: Dict[str, float] = {
    "kg": 1.0, "gram": 0.001, "ton": 1000.0, "lbs": 0.45359237, "ounce": 0.0283495231,
}

# FASE U — satuan BERAT yang datang dari MASTER (`uoms.base_type="weight"`, termasuk
# `aliases`). Diisi `load_fixed_factors()`; `WEIGHT_BASE_KG` tetap jaring pengaman
# fisika supaya instalasi tanpa baris master tidak berubah perilaku.
_WEIGHT_MASTER: Dict[str, float] = {}


def weight_factors() -> Dict[str, float]:
    """Fisika (hardcode) ∪ master. Master MENANG bila pemilik mengubah faktornya."""
    return {**WEIGHT_BASE_KG, **_WEIGHT_MASTER}


def product_kg_per_meter(product: Dict[str, Any]) -> float:
    """Faktor catch-weight: kg per 1 BASE unit (meter).

    Prioritas: field eksplisit `kg_per_meter` (>0) → else turunan `gramasi(gsm) × lebar(m) / 1000`.
    Mengembalikan 0.0 bila tidak tersedia (produk tanpa data berat).
    """
    try:
        explicit = float(product.get("kg_per_meter") or 0)
    except (TypeError, ValueError):
        explicit = 0.0
    if explicit > 0:
        return explicit
    try:
        gsm = float(product.get("gramasi") or 0)
        width = float(product.get("lebar") or 0)
    except (TypeError, ValueError):
        return 0.0
    v = gsm * width / 1000.0
    return v if v > 0 else 0.0


def kg_per_base_unit(product: Dict[str, Any],
                     fixed: Optional[Dict[str, float]] = None) -> float:
    """FASE B — berat (kg) per 1 **BASE UNIT produk**.

    `product_kg_per_meter()` menghasilkan kg per **METER** (GSM × lebar ÷ 1000).
    Bila base unit produk bukan meter (mis. **yard**), nilai itu WAJIB dikalikan
    meter-per-base-unit (1 yard = 0,9144 m) — kalau tidak, berat akan salah ~9,4%
    untuk seluruh produk berbasis yard (bug lama Sub-fase 1.13/Fase 8 yang
    diperbaiki di Fase B).

    FASE F-1 (bug `KN-F1-KGBASE-GR`) — bila base unit produk **memang satuan berat**
    (benang per `kg`, obat celup per `kg`/`gram`, dsb), faktor kg-per-base-unit adalah
    **FISIKA murni** dan TIDAK butuh gramasi/lebar. Sebelum perbaikan ini fungsi
    mengembalikan 0 untuk produk berbasis kg tanpa gramasi, sehingga
    `resolve_roll_measures()` menolak menyelesaikan Goods Receipt
    ("tak bisa menurunkan panjang dari berat") — artinya **seluruh penerimaan benang
    & bahan kimia mustahil diselesaikan**. `makloon_calc_service` sudah lama
    men-hardcode `1.0` untuk `kg`, jadi perbaikan ini menyeragamkan aturan ke SSOT.
    """
    base = _norm(product.get("base_unit", "meter"))
    weights = weight_factors()          # FASE U: fisika ∪ master (`base_type="weight"`)
    if base in weights:
        return weights[base]
    kg_per_m = product_kg_per_meter(product)
    if kg_per_m <= 0:
        return 0.0
    if base in ("meter", "m", "mtr", ""):
        return kg_per_m
    factors = dict(CANONICAL_LENGTH_FACTORS)
    if fixed:
        factors.update({k: v for k, v in fixed.items() if v})
    m_per_base = factors.get(base)
    if not m_per_base or m_per_base <= 0:
        return kg_per_m               # base unit non-panjang (roll/pcs) → biarkan apa adanya
    return kg_per_m * float(m_per_base)


def _catch_weight(product: Dict[str, Any], from_u: str, to_u: str,
                  fixed: Optional[Dict[str, float]] = None) -> Optional[float]:
    """Sub-fase 1.13 / Fase 8 — konversi kg ↔ base unit produk via catch-weight.
    kg per 1 base unit = `kg_per_base_unit()` (GSM × lebar ÷ 1000, disesuaikan base unit).
    """
    base = _norm(product.get("base_unit", "meter"))
    kg_per_base = kg_per_base_unit(product, fixed)
    if kg_per_base <= 0:
        return None
    if from_u == "kg" and to_u == base:
        return 1.0 / kg_per_base          # base unit per 1 kg
    if from_u == base and to_u == "kg":
        return kg_per_base                # kg per 1 base unit
    return None


def _resolve(product: Dict[str, Any], from_u: str, to_u: str, fixed: Dict[str, float],
             pair_rules: Optional[Dict[Any, Any]] = None) -> Optional[float]:
    """Faktor konversi (angka saja). FASE B: aturan GLOBAL ikut dipertimbangkan.

    Urutan: sama → FIXED (uoms/kanonik) → per-produk (`uom_conversions`) →
    aturan GLOBAL (`uom_conversion_rules`) → catch-weight (GSM × lebar) → 1-hop base.
    """
    if from_u == to_u:
        return 1.0
    direct = _fixed(from_u, to_u, fixed)
    if direct is not None:
        return direct
    var = _variable(product, from_u, to_u)
    if var is not None:
        return var
    glob = _pair(from_u, to_u, pair_rules)
    if glob is not None:
        return glob["factor"]
    cw = _catch_weight(product, from_u, to_u, fixed)
    if cw is not None:
        return cw
    # 1-hop lewat base unit produk (mis. roll -> meter -> yard, atau kg -> meter -> yard)
    base = _norm(product.get("base_unit", "meter"))
    if from_u != base and to_u != base:
        f1 = _fixed(from_u, base, fixed)
        if f1 is None:
            f1 = _variable(product, from_u, base)
        if f1 is None:
            _g1 = _pair(from_u, base, pair_rules)
            f1 = _g1["factor"] if _g1 else None
        if f1 is None:
            f1 = _catch_weight(product, from_u, base, fixed)
        f2 = _fixed(base, to_u, fixed)
        if f2 is None:
            f2 = _variable(product, base, to_u)
        if f2 is None:
            _g2 = _pair(base, to_u, pair_rules)
            f2 = _g2["factor"] if _g2 else None
        if f2 is None:
            f2 = _catch_weight(product, base, to_u, fixed)
        if f1 is not None and f2 is not None:
            return f1 * f2
    return None


def resolve_factor(product: Dict[str, Any], from_unit: str, to_unit: str,
                   fixed_factors: Dict[str, float],
                   pair_rules: Optional[Dict[Any, Any]] = None) -> Optional[Dict[str, Any]]:
    """FASE B — faktor + **SUMBER** faktor (untuk jejak konversi D-07).

    Return `{factor, source, rule_id, formula, path[]}` atau None bila tak ada aturan.
    `source` ∈ same_unit | fixed_uom | product_override | global_rule | formula_gsm_width | hop_base
    """
    fu, tu = _norm(from_unit), _norm(to_unit)
    if fu == tu:
        return {"factor": 1.0, "source": "same_unit", "rule_id": "", "formula": "",
                "path": [f"{fu} = {tu}"]}
    direct = _fixed(fu, tu, fixed_factors)
    if direct is not None:
        return {"factor": direct, "source": "fixed_uom", "rule_id": "", "formula": "",
                "path": [f"master UOM: 1 {fu} = {direct:g} {tu}"]}
    var = _variable(product, fu, tu)
    if var is not None:
        return {"factor": var, "source": "product_override", "rule_id": "", "formula": "",
                "path": [f"master produk: 1 {fu} = {var:g} {tu}"]}
    glob = _pair(fu, tu, pair_rules)
    if glob is not None:
        return {"factor": glob["factor"], "source": "global_rule",
                "rule_id": glob.get("rule_id", ""), "formula": "",
                "path": [f"aturan global ({glob.get('kind')}): 1 {fu} = {glob['factor']:g} {tu}"]}
    cw = _catch_weight(product, fu, tu, fixed_factors)
    if cw is not None:
        return {"factor": cw, "source": "formula_gsm_width", "rule_id": "",
                "formula": "gsm_width",
                "path": [f"GSM × lebar: 1 {fu} = {cw:g} {tu} "
                         f"(kg per {_norm(product.get('base_unit', 'meter'))} = "
                         f"{kg_per_base_unit(product, fixed_factors):g})"]}
    hop = _resolve(product, fu, tu, fixed_factors, pair_rules)
    if hop is not None:
        base = _norm(product.get("base_unit", "meter"))
        return {"factor": hop, "source": "hop_base", "rule_id": "", "formula": "",
                "path": [f"{fu} → {base} → {tu}"]}
    return None


def convert(product: Dict[str, Any], qty: float, from_unit: str, to_unit: str,
            fixed_factors: Dict[str, float], precision: int = 2,
            pair_rules: Optional[Dict[Any, Any]] = None) -> float:
    """Konversi `qty` dari `from_unit` ke `to_unit`. Raise 400 bila faktor tak tersedia."""
    f = _resolve(product, _norm(from_unit), _norm(to_unit), fixed_factors, pair_rules)
    if f is None:
        raise HTTPException(status_code=400, detail=(
            f"Konversi unit '{from_unit}' → '{to_unit}' tidak tersedia untuk produk "
            f"{product.get('sku') or product.get('id')}. Tambahkan faktor di uom_conversions."
        ))
    return round(float(qty) * f, precision)


def to_base(product: Dict[str, Any], qty: float, unit: str,
            fixed_factors: Dict[str, float], precision: int = 2,
            pair_rules: Optional[Dict[Any, Any]] = None) -> float:
    """Konversi qty (dalam `unit`) ke BASE UNIT produk."""
    return convert(product, qty, unit, product.get("base_unit", "meter"), fixed_factors,
                   precision, pair_rules)


def from_base(product: Dict[str, Any], base_qty: float, unit: str,
              fixed_factors: Dict[str, float], precision: int = 2,
              pair_rules: Optional[Dict[Any, Any]] = None) -> float:
    """Konversi qty (dalam base unit) ke `unit` tampilan."""
    return convert(product, base_qty, product.get("base_unit", "meter"), unit, fixed_factors,
                   precision, pair_rules)


def resolve_roll_measures(product: Dict[str, Any], task_unit: str,
                          length_in: float, weight_in: float,
                          fixed_factors: Dict[str, float]) -> Dict[str, float]:
    """Fase 8 (Catch-weight) — resolusi ukuran SATU roll fisik saat Goods Receipt.

    Mengembalikan dict {length_base, weight_kg, task_qty}:
      - length_base : panjang roll dlm BASE unit produk (meter) → qty stok inventori.
      - weight_kg   : berat roll (kg) → catch-weight aktual yg disimpan di roll.
      - task_qty    : kontribusi roll thd qty diterima dlm SATUAN TASK (utk validasi Σ).

    Aturan (pilihan owner: faktor default per-produk + override AKTUAL saat GR):
      • task_unit == 'kg' (PO per berat):
          - weight = weight_in; length = length_in (meter aktual) bila diisi,
            else turunan weight/kgpm (butuh faktor). task_qty = weight.
      • task_unit panjang (meter/yard/…):
          - length_base = to_base(length_in); weight = weight_in (aktual) bila diisi,
            else estimasi length_base × kgpm (0 bila tak ada faktor). task_qty = length_in.
    """
    base = _norm(product.get("base_unit", "meter"))
    tu = _norm(task_unit) or base
    kgpm = kg_per_base_unit(product, fixed_factors)   # FASE B — kg per BASE unit
    L = float(length_in or 0)
    W = float(weight_in or 0)
    sku = product.get("sku") or product.get("id") or "?"

    if tu == "kg":
        if W <= 0 and L <= 0:
            raise HTTPException(status_code=400, detail=f"Roll {sku}: isi berat (kg) atau panjang (m).")
        weight = round(W if W > 0 else L * kgpm, 3)
        if L > 0:
            length_base = round(L, 2)
        else:
            if kgpm <= 0:
                raise HTTPException(status_code=400, detail=(
                    f"Roll {sku}: tak bisa menurunkan panjang dari berat — "
                    f"isi gramasi & lebar (atau kg_per_meter) produk, atau masukkan panjang aktual."))
            length_base = round(W / kgpm, 2)
        task_qty = weight
    else:
        if L <= 0:
            raise HTTPException(status_code=400, detail=f"Roll {sku}: panjang ({task_unit}) harus > 0.")
        length_base = to_base(product, L, task_unit, fixed_factors)
        weight = round(W if W > 0 else length_base * kgpm, 3)
        task_qty = round(L, 2)

    return {"length_base": length_base, "weight_kg": weight, "task_qty": round(task_qty, 3)}
