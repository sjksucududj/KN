"""master_registry (FASE L, diperluas FASE T) — JEMBATAN master ↔ `domain_registry`.

MASALAH YANG DITUTUP
====================
Daftar yang bisa **bertambah** (lini produk sekarang; tahapan proses & jenis
sampling pada fase berikutnya) harus hidup sebagai **master** supaya pemilik bisa
menambahnya tanpa programmer. Tetapi `domain_registry.py` tetap dibutuhkan sebagai
**bentuk + nilai benih**: ia dipakai validasi sinkron di banyak tempat dan harus
bisa diimpor tanpa basis data (skrip, gate statik, tes unit).

Kalau keduanya dibiarkan berdiri sendiri, lahirlah dua daftar — kelas bug termahal
di repo ini. Aturan yang dipakai:

    domain_registry  →  BENTUK + NILAI BENIH (seed)          [sinkron, tanpa DB]
    koleksi master   →  NILAI HIDUP (bisa ditambah pemilik)   [asinkron, per PT]
    berkas ini       →  SATU PEMBACA untuk keduanya

Urutan resolusi: baris master **efektif** untuk badan usaha itu (override PT menang
atas baris global) → bila koleksinya **kosong**, pakai nilai benih. Fallback itu
bukan kemewahan: instalasi baru & basis data uji tidak boleh mati hanya karena
migrasi seed belum dijalankan.

Cache 60 detik per (kind, badan usaha) supaya `/api/enums` dan penyaring 12 layar
tidak memukul Mongo tiap ketukan. `invalidate()` dipanggil `routers/entity_masters.py`
sesudah master diubah — pola yang sama dengan `core_utils.invalidate_entity_code`
(pelajaran FASE E-1: tanpa itu perubahan master baru terasa setelah backend restart).
"""
import time
from typing import Any, Dict, List, Optional

import domain_registry as dr

CACHE_TTL_SECONDS = 60
_cache: Dict[str, Dict[str, Any]] = {}       # key -> {"at": ts, "rows": [...]}

# kind master (URL slug) → nama enum benih di domain_registry
SEEDS: Dict[str, str] = {
    "product-lines": "product_line",
    # FASE T — tahapan proses (benang · tenun · rajut · pfp · pfd · celup · screen ·
    # printing · proofing · inspect). Benihnya `domain_registry.PROCESS_STAGES`.
    "process-stages": "process_stage",
}


def invalidate(kind: str = "") -> None:
    """Buang cache. Tanpa argumen = seluruh cache."""
    if not kind:
        _cache.clear()
        return
    for key in [k for k in _cache if k.startswith(f"{kind}:")]:
        _cache.pop(key, None)


def _seed_rows(kind: str) -> List[Dict[str, Any]]:
    enum_name = SEEDS.get(kind, "")
    if not enum_name:
        return []
    return [dict(v) for v in dr.enum_items(enum_name)]


def _row_to_item(row: Dict[str, Any], key_field: str, name_field: str) -> Dict[str, Any]:
    """Baris master → bentuk item enum (`value`/`label`) + seluruh field lainnya.

    Bentuknya disamakan dengan `domain_registry` supaya layar & `useDomainEnums`
    tidak perlu tahu nilainya datang dari master atau dari benih.
    """
    out = {k: v for k, v in row.items() if k not in ("_id",)}
    out["value"] = str(row.get(key_field) or "").strip().lower()
    out["label"] = str(row.get(name_field) or out["value"] or "")
    return out


async def rows(kind: str, entity_id: str = "") -> List[Dict[str, Any]]:
    """Nilai HIDUP master `kind` untuk satu badan usaha (dengan fallback benih)."""
    key = f"{kind}:{entity_id or 'all'}"
    hit = _cache.get(key)
    now = time.time()
    if hit and (now - hit["at"]) < CACHE_TTL_SECONDS:
        return hit["rows"]
    from services import entity_master_service as ems
    try:
        spec = ems.spec(kind)
        live = await ems.effective_rows(kind, entity_id or "")
        items = [_row_to_item(r, spec.key_field, spec.name_field) for r in live]
        items = [i for i in items if i["value"]]
    except Exception:                      # noqa: BLE001 — master belum terdaftar/DB mati
        items = []
    if not items:
        items = _seed_rows(kind)
    _cache[key] = {"at": now, "rows": items}
    return items


# ─── FASE L — LINI PRODUK ────────────────────────────────────────────────────
async def product_lines(entity_id: str = "") -> List[Dict[str, Any]]:
    return await rows("product-lines", entity_id)


async def line_codes(entity_id: str = "") -> List[str]:
    return [r["value"] for r in await product_lines(entity_id)]


async def line_meta(code: str, entity_id: str = "") -> Dict[str, Any]:
    want = str(code or "").strip().lower()
    for r in await product_lines(entity_id):
        if r["value"] == want:
            return r
    return {}


async def line_options(entity_id: str = "") -> List[Dict[str, Any]]:
    """Bentuk siap-dropdown untuk `/api/enums` & komponen `<LineFilter/>`."""
    out = []
    for r in await product_lines(entity_id):
        out.append({
            "value": r["value"], "label": r["label"],
            "fabric_type_required": r.get("fabric_type_required", "") or "",
            "measure_unit_default": r.get("measure_unit_default", "") or "",
            "stage_sequence": r.get("stage_sequence") or [],
            "sample_types_default": r.get("sample_types_default") or [],
            "description": r.get("description", "") or r.get("notes", "") or "",
            "sort": r.get("sort", 0) or 0,
        })
    return out


async def live_enum_values(name: str, entity_id: str = "") -> Optional[List[Dict[str, Any]]]:
    """Nilai hidup untuk sebuah enum `domain_registry`, bila enum itu ber-master.

    Dipakai `routers/enums.py` untuk menimpa nilai benih **hanya** pada enum yang
    memang punya master — enum lain tetap apa adanya.
    """
    # FASE T — `process_type` TIDAK punya master sendiri, tetapi daftar hidupnya
    # bisa BERTAMBAH lewat master tahapan (tahap baru boleh menunjuk jenis proses
    # yang belum ada di benih). Kalau tidak di-union di sini, tahap yang sah akan
    # muncul di pemilih langkah sementara jenis prosesnya tidak ada di dropdown
    # mana pun — pengguna melihat langkah yang tak bisa diisi.
    if name == "process_type":
        return await process_types(entity_id)
    for kind, enum_name in SEEDS.items():
        if enum_name == name:
            return await rows(kind, entity_id)
    return None


# ─── FASE T — TAHAPAN PROSES ─────────────────────────────────────────────────
# Satu pembaca untuk dua sumber (master hidup + benih registry). Semua konsumen
# (router SPK, papan PO, `/api/enums`, gate INV-DOMAIN-06) WAJIB lewat sini —
# begitu ada yang membaca koleksinya langsung, fallback benih hilang dan
# instalasi baru mati hanya karena migrasi seed belum dijalankan.

def _norm_flow(row: Dict[str, Any]) -> str:
    """`material_flow` yang sudah dibersihkan (kosong → 'moves' untuk tahap makloon)."""
    flow = str(row.get("material_flow") or "").strip().lower()
    if flow in ("moves", "service_only", "either"):
        return flow
    # Tahap non-makloon tidak punya aliran kain; tahap makloon lama yang belum
    # punya field ini berperilaku seperti sebelum FASE T: kainnya bergerak.
    return "moves" if str(row.get("kind") or "makloon") == "makloon" else ""


async def stages(entity_id: str = "") -> List[Dict[str, Any]]:
    """Seluruh tahapan proses EFEKTIF untuk satu badan usaha (aktif & non-aktif)."""
    return await rows("process-stages", entity_id)


async def active_stages(entity_id: str = "") -> List[Dict[str, Any]]:
    """Hanya tahapan yang aktif — bentuk yang dipakai dropdown & papan."""
    out = []
    for r in await stages(entity_id):
        if r.get("active") is False or str(r.get("status") or "") == "inactive":
            continue
        out.append(r)
    return out


async def stage_meta(code: str, entity_id: str = "") -> Dict[str, Any]:
    """Satu baris tahapan (dinormalkan) atau {} bila kodenya tidak dikenal."""
    want = str(code or "").strip().lower()
    if not want:
        return {}
    for r in await stages(entity_id):
        if r.get("value") == want:
            meta = dict(r)
            meta["material_flow"] = _norm_flow(r)
            meta["changes_stage"] = r.get("changes_stage") is not False
            meta["needs_vendor"] = bool(r.get("needs_vendor"))
            meta["kind"] = str(r.get("kind") or "makloon")
            return meta
    return {}


async def stage_by_process_type(process_type: str, entity_id: str = "",
                               target_use: str = "") -> Dict[str, Any]:
    """Tahap yang cocok untuk satu `process_type` (dipakai SPK lama tanpa `stage_code`).

    Ini jembatan KOMPATIBILITAS, bukan sumber baru: 3 SPK yang lahir sebelum FASE T
    hanya menyimpan `process_type`, dan angkanya WAJIB tidak bergeser saat dibuka
    ulang. `target_use` dipakai memilah `pre_treatment` (dye→PFD vs print→PFP).
    """
    pt = str(process_type or "").strip().lower()
    tu = str(target_use or "").strip().lower()
    if not pt:
        return {}
    cand = [r for r in await active_stages(entity_id)
            if str(r.get("process_type") or "").strip().lower() == pt]
    if tu:
        exact = [r for r in cand if str(r.get("target_use") or "").strip().lower() == tu]
        if exact:
            cand = exact
    if not cand:
        return {}
    cand.sort(key=lambda r: (int(r.get("seq") or 0), str(r.get("value") or "")))
    return await stage_meta(cand[0].get("value") or "", entity_id)


async def stages_for_line(line_code: str = "", entity_id: str = "",
                         spk_only: bool = False) -> List[Dict[str, Any]]:
    """Tahapan yang berlaku untuk satu lini kerja.

    Aturan **kosong = semua** dipakai konsisten dengan FASE L: baris tanpa
    `applies_to_lines` berlaku untuk SEMUA lini, dan `line_code` kosong berarti
    "jangan disaring". Kalau ini dibalik menjadi wajib-isi, layar SPK akan
    mendadak kosong bagi lini yang belum dipetakan.
    """
    want = str(line_code or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for r in await active_stages(entity_id):
        lines = [str(x).strip().lower() for x in (r.get("applies_to_lines") or []) if str(x).strip()]
        if want and lines and want not in lines:
            continue
        meta = await stage_meta(r.get("value") or "", entity_id)
        if spk_only:
            kind_row = next((k for k in dr.enum_items("process_stage_kind")
                             if k["value"] == meta.get("kind")), None)
            if not (kind_row or {}).get("spk_step"):
                continue
        out.append(meta)
    out.sort(key=lambda r: (int(r.get("seq") or 0), str(r.get("value") or "")))
    return out


async def process_types(entity_id: str = "") -> List[Dict[str, Any]]:
    """`PROCESS_TYPES` benih **∪** jenis proses yang dipakai baris master aktif."""
    seed = [dict(v) for v in dr.enum_items("process_type")]
    known = {v["value"] for v in seed}
    try:
        extra = await active_stages(entity_id)
    except Exception:                      # noqa: BLE001 — DB mati ≠ dropdown mati
        extra = []
    for r in extra:
        pt = str(r.get("process_type") or "").strip().lower()
        if pt and pt not in known:
            known.add(pt)
            seed.append({"value": pt, "label": r.get("label") or pt, "fabric_type": None,
                         "description": f"Dari master tahapan '{r.get('label') or pt}' "
                                        "— belum terdaftar di domain_registry "
                                        "(INV-DOMAIN-06 akan memperingatkan)."})
    return seed


async def stage_options(entity_id: str = "", line_code: str = "") -> List[Dict[str, Any]]:
    """Bentuk siap-dropdown untuk pemilih langkah SPK & papan PO."""
    out = []
    for r in await stages_for_line(line_code, entity_id, spk_only=True):
        out.append({
            "value": r["value"], "label": r["label"],
            "kind": r.get("kind", ""),
            "seq": r.get("seq", 0) or 0,
            "process_type": r.get("process_type", "") or "",
            "target_use": r.get("target_use", "") or "",
            "changes_stage": r.get("changes_stage") is not False,
            "from_stage": r.get("from_stage", "") or "",
            "to_stage": r.get("to_stage", "") or "",
            "needs_vendor": bool(r.get("needs_vendor")),
            "material_flow": r.get("material_flow", "") or "",
            "material_flow_default": r.get("material_flow_default", "") or "",
            "tariff_basis_default": r.get("tariff_basis_default", "") or "",
            "applies_to_lines": r.get("applies_to_lines") or [],
            "notes": r.get("notes", "") or r.get("description", "") or "",
        })
    return out
