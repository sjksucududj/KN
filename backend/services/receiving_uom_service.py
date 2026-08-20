"""FASE F-1 — PENERIMAAN BERBASIS **SATUAN SUPPLIER** (lanjutan Fase B & Fase E).

Masalah nyata yang diselesaikan
-------------------------------
Setelah Fase E, layar penerimaan **menampilkan** kode & nama barang versi supplier, tetapi
qty masih WAJIB diketik dalam satuan KN. Supplier menulis surat jalan dalam satuannya sendiri
(`cone`, `roll`, `lembar`, `bal`) sehingga operator gudang mengalikan sendiri
(25 cone × 1,89 kg = 47,25 kg). Salah ketik tidak terdeteksi dan asal angka stok tidak
terlacak.

Modul ini menambah **satu pintu** untuk:
  1. menyusun **opsi satuan** yang sah untuk sebuah inbound task (F1-04),
  2. mengonversi `doc_qty` + `doc_uom` → satuan task dengan **prioritas eksplisit** (F1-02),
  3. membangun **jejak konversi** siap-simpan (F1-03 · kewajiban D-07),
  4. menghitung **sisa PO dalam dua satuan** untuk pesan/UI (F1-06),
  5. **kebijakan configurable tanpa deploy** (`system_settings` scope `receiving`, F1-08).

ATURAN SSOT (R3) — modul ini TIDAK menghitung ulang matematika konversi. Matematika tetap di
`services/uom_service.py`; faktor kemasan supplier tetap di `supplier_items.conv_factor`
(Fase E). Di sini hanya **urutan prioritas + jejak + kebijakan**.

Prioritas resolusi faktor (paling spesifik → paling umum):
  satuan sama → **barang supplier** (`supplier_uom`/`conv_factor`) → **registry global**
  (`uom_rules_service`) → gagal ⇒ `ReceivingUomError` dengan pesan yang memberi tahu
  langkah perbaikan (bukan error teknis).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, parse_decimal, safe_doc
from services import uom_rules_service as _uomr
from services import supplier_item_service as _sis

SETTINGS_SCOPE = "receiving"
CONTEXT_SCAN = "goods_receipt_scan"

DEFAULT_SETTINGS: Dict[str, Any] = {
    # off      = layar penerimaan hanya menerima satuan KN (perilaku pra-F1)
    # optional = satuan supplier tersedia, tapi default tetap satuan KN
    # prefer   = default memakai satuan supplier bila barang supplier terdaftar
    "supplier_uom_input_mode": "prefer",
    # True  = satuan di luar satuan KN/base hanya boleh bila terdaftar di Barang Supplier
    #         (mencegah operator mengarang satuan yang faktornya kebetulan ada di registry)
    "require_supplier_item_for_supplier_uom": True,
    # True  = hasil konversi yang melebihi sisa PO + toleransi kedatangan ditolak
    "block_over_remaining": True,
}
INPUT_MODES = ("off", "optional", "prefer")


class ReceivingUomError(ValueError):
    """Kesalahan satuan/konversi penerimaan → dipetakan ke HTTP 400 oleh router."""


# ═══════════════════════════════════════════════════════════════════════════
# 1. KEBIJAKAN (configurable tanpa deploy)
# ═══════════════════════════════════════════════════════════════════════════
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
    cur = await get_settings()
    nxt = {k: cur[k] for k in DEFAULT_SETTINGS}
    mode = payload.get("supplier_uom_input_mode")
    if mode is not None:
        mode = str(mode).strip().lower()
        if mode not in INPUT_MODES:
            raise ReceivingUomError(
                "Mode input satuan supplier hanya: " + " · ".join(INPUT_MODES)
                + f" (diberikan '{mode}').")
        nxt["supplier_uom_input_mode"] = mode
    for key in ("require_supplier_item_for_supplier_uom", "block_over_remaining"):
        if payload.get(key) is not None:
            nxt[key] = bool(payload[key])
    await db.system_settings.update_one(
        {"scope": SETTINGS_SCOPE},
        {"$set": {**nxt, "updated_at": now_iso(), "updated_by": actor},
         "$setOnInsert": {"id": new_id("set"), "scope": SETTINGS_SCOPE}},
        upsert=True)
    return await get_settings()


async def ensure_defaults(actor: str = "system") -> Dict[str, Any]:
    """Idempoten — dipakai bootstrap/seed agar kebijakan selalu ada."""
    found = await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 0, "id": 1})
    if found:
        return {"created": 0}
    await db.system_settings.insert_one({
        "id": new_id("set"), "scope": SETTINGS_SCOPE, **DEFAULT_SETTINGS,
        "updated_at": now_iso(), "updated_by": actor})
    return {"created": 1}


# ═══════════════════════════════════════════════════════════════════════════
# 2. KONTEKS TASK (produk · PO · barang supplier)
# ═══════════════════════════════════════════════════════════════════════════
def _n(u: Any) -> str:
    return _uomr.normalize_unit(u)


def _unit_label(code: str) -> str:
    hit = _uomr.UNIT_BY_CODE.get(_n(code))
    return hit["label"] if hit else (str(code or "").strip() or "-")


def _id_num(v: Any, places: int = 6) -> str:
    """Angka gaya Indonesia (koma desimal) untuk teks yang tampil di layar."""
    try:
        s = f"{round(float(v), places):g}"
    except (TypeError, ValueError):
        return str(v)
    return s.replace(".", ",")


async def task_context(task: Dict[str, Any]) -> Dict[str, Any]:
    """Kumpulkan sekali: produk, PO/supplier, barang supplier terkait task."""
    product = safe_doc(await db.products.find_one(
        {"id": task.get("product_id")}, {"_id": 0})) or {}
    po = None
    if task.get("po_id"):
        po = safe_doc(await db.purchase_orders.find_one(
            {"id": task["po_id"]}, {"_id": 0, "id": 1, "po_number": 1, "supplier_id": 1,
                                    "supplier_name": 1, "entity_id": 1}))
    supplier_item = None
    if task.get("supplier_item_id"):
        supplier_item = safe_doc(await db[_sis.COLL].find_one(
            {"id": task["supplier_item_id"]}, {"_id": 0}))
    if not supplier_item and (po or {}).get("supplier_id") and task.get("product_id"):
        # Task lama (dibuat sebelum Fase E) tidak menyimpan supplier_item_id → resolve
        # dari (supplier × produk) supaya fitur tetap berguna untuk data lama.
        supplier_item = await _sis.resolve_for_product(
            supplier_id=po["supplier_id"], product_id=task["product_id"],
            entity_id=(po or {}).get("entity_id") or "")
    return {
        "product": product,
        "po": po or {},
        "supplier_item": supplier_item,
        "task_uom": _n(task.get("unit")) or _n(product.get("base_unit")) or "meter",
        "base_uom": _n(product.get("base_unit")) or _n(task.get("unit")) or "meter",
    }


def remaining_qty(task: Dict[str, Any]) -> float:
    expected = parse_decimal(task.get("expected_qty") or 0)
    received = parse_decimal(task.get("received_qty") or 0)
    return round(max(expected - received, 0.0), 4)


# ═══════════════════════════════════════════════════════════════════════════
# 3. KONVERSI BERPRIORITAS + JEJAK (F1-02 / F1-03)
# ═══════════════════════════════════════════════════════════════════════════
async def _to_task_unit(product: Dict[str, Any], qty: float, from_uom: str,
                        task_uom: str, engine: Dict[str, Any]) -> Dict[str, Any]:
    """Konversi via registry global; raise ReceivingUomError bila tak ada aturan."""
    try:
        return await _uomr.convert_with_trail(
            product, qty, from_uom, task_uom, engine=engine, context=CONTEXT_SCAN)
    except _uomr.UomRuleError as exc:
        raise ReceivingUomError(str(exc)) from exc


async def convert_doc_qty(task: Dict[str, Any], doc_uom: str, doc_qty: Any,
                          ctx: Optional[Dict[str, Any]] = None,
                          settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Konversi qty **surat jalan supplier** → satuan task + jejak siap-simpan.

    Jejak (`uom_trail`) memuat: apa yang diketik operator (`doc_uom`/`doc_qty`), hasil dalam
    satuan task & satuan dasar, faktor, **sumber faktor**, referensi barang supplier, dan
    waktu — sehingga angka di stok selalu bisa dipertanggungjawabkan (D-07).
    """
    c = ctx or await task_context(task)
    st = settings or await get_settings()
    product, sup_item = c["product"], c["supplier_item"]
    task_uom, base_uom = c["task_uom"], c["base_uom"]
    src_uom = _n(doc_uom)
    q = parse_decimal(doc_qty)

    if not src_uom:
        raise ReceivingUomError("Satuan surat jalan (doc_uom) wajib diisi.")
    if q <= 0:
        raise ReceivingUomError("Qty surat jalan (doc_qty) harus lebih besar dari 0.")
    if st.get("supplier_uom_input_mode") == "off" and src_uom != task_uom:
        raise ReceivingUomError(
            "Input satuan supplier sedang DIMATIKAN oleh kebijakan penerimaan. "
            f"Masukkan qty dalam satuan {task_uom}, atau aktifkan di "
            "Pengaturan → Penerimaan → Satuan Supplier.")

    engine = await _uomr.load_engine()
    precision = int(engine["settings"].get("precision", 2))
    sup_uom = _n((sup_item or {}).get("supplier_uom"))
    conv = parse_decimal((sup_item or {}).get("conv_factor") or 0, 6)

    # ── Jalur 1: satuan sama dengan satuan task (perilaku lama) ──────────────
    if src_uom == task_uom:
        task_qty = round(q, precision)
        source, factor, path = "same_unit", 1.0, [f"{src_uom} = {task_uom} (satuan PO)"]
        rule_id = ""
    # ── Jalur 2: satuan supplier terdaftar → conv_factor (Fase E) ────────────
    elif sup_item and sup_uom and src_uom == sup_uom and conv > 0:
        base_from_supplier = round(q * conv, 6)
        if base_uom == task_uom:
            task_qty = round(base_from_supplier, precision)
            hop = f"{base_uom} = satuan PO"
        else:
            hop_trail = await _to_task_unit(product, base_from_supplier, base_uom,
                                            task_uom, engine)
            task_qty = hop_trail["base_qty"]
            hop = (f"{base_uom} → {task_uom} faktor "
                   f"{hop_trail['factor']:g} ({hop_trail['source']})")
        source, rule_id = "supplier_item", ""
        factor = round(task_qty / q, 8) if q else 0.0
        path = [f"barang supplier {sup_item.get('supplier_sku')}: 1 {src_uom} = "
                f"{_id_num(conv)} {base_uom}", hop]
    # ── Jalur 3: registry global (dengan guardrail kebijakan) ────────────────
    else:
        if (bool(st.get("require_supplier_item_for_supplier_uom", True))
                and src_uom not in (task_uom, base_uom)):
            hint = (f"Barang supplier '{sup_item.get('supplier_sku')}' terdaftar dengan satuan "
                    f"'{sup_uom or '-'}', bukan '{src_uom}'."
                    if sup_item else
                    "Barang supplier untuk produk ini belum terdaftar.")
            raise ReceivingUomError(
                f"Satuan '{src_uom}' belum sah untuk penerimaan ini. {hint} "
                "Daftarkan/perbaiki di Pembelian → Master Pembelian → Barang Supplier "
                f"(satuan supplier + faktor konversi ke {base_uom}), atau terima dalam "
                f"satuan {task_uom}.")
        trail = await _to_task_unit(product, q, src_uom, task_uom, engine)
        task_qty = trail["base_qty"]
        source, rule_id = trail["source"], trail.get("rule_id", "")
        factor = trail["factor"]
        path = list(trail.get("path") or [])

    # Qty dalam satuan DASAR produk (dipakai stok/roll/laporan)
    if task_uom == base_uom:
        base_qty = task_qty
    else:
        try:
            base_qty = (await _to_task_unit(product, task_qty, task_uom, base_uom,
                                            engine))["base_qty"]
        except ReceivingUomError:
            base_qty = task_qty

    return {
        "doc_uom": src_uom, "doc_qty": round(q, precision),
        "doc_uom_label": _unit_label(src_uom),
        "task_uom": task_uom, "task_qty": round(task_qty, precision),
        "base_uom": base_uom, "base_qty": round(base_qty, precision),
        "factor": round(float(factor), 8), "source": source, "rule_id": rule_id,
        "path": path,
        "supplier_item_id": (sup_item or {}).get("id", ""),
        "supplier_sku": (sup_item or {}).get("supplier_sku", ""),
        "supplier_item_name": (sup_item or {}).get("supplier_item_name", ""),
        "supplier_uom": sup_uom,
        "context": CONTEXT_SCAN, "converted_at": now_iso(),
    }


async def to_doc_uom(task: Dict[str, Any], task_qty: Any, doc_uom: str,
                     ctx: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """Balik arah: qty satuan task → satuan surat jalan (untuk pesan/sisa 2 satuan)."""
    c = ctx or await task_context(task)
    src = _n(doc_uom)
    if not src or src == c["task_uom"]:
        return round(parse_decimal(task_qty), 2)
    try:
        one = await convert_doc_qty(task, src, 1, ctx=c,
                                    settings={**DEFAULT_SETTINGS,
                                              "require_supplier_item_for_supplier_uom": False,
                                              "supplier_uom_input_mode": "optional"})
    except ReceivingUomError:
        return None
    f = float(one.get("task_qty") or 0)
    return round(parse_decimal(task_qty) / f, 2) if f > 0 else None


# ═══════════════════════════════════════════════════════════════════════════
# 4. OPSI SATUAN UNTUK FE (F1-04)
# ═══════════════════════════════════════════════════════════════════════════
async def uom_options(task: Dict[str, Any]) -> Dict[str, Any]:
    """Satuan yang sah + faktor + hint + sisa dalam dua satuan untuk 1 inbound task."""
    c = await task_context(task)
    st = await get_settings()
    product, sup_item = c["product"], c["supplier_item"]
    task_uom, base_uom = c["task_uom"], c["base_uom"]
    rem = remaining_qty(task)

    options: List[Dict[str, Any]] = [{
        "value": task_uom, "label": f"{_unit_label(task_uom)} · satuan KN",
        "source": "same_unit", "factor": 1.0, "hint": "Qty diketik apa adanya (satuan PO).",
        "remaining": rem,
    }]
    seen = {task_uom}
    mode = st.get("supplier_uom_input_mode", "prefer")
    sup_uom = _n((sup_item or {}).get("supplier_uom"))
    conv = parse_decimal((sup_item or {}).get("conv_factor") or 0, 6)

    if mode != "off" and sup_item and sup_uom and sup_uom not in seen and conv > 0:
        try:
            probe = await convert_doc_qty(task, sup_uom, 1, ctx=c, settings=st)
            rem_doc = round(rem / probe["task_qty"], 2) if probe["task_qty"] else None
            options.append({
                "value": sup_uom,
                "label": f"{_unit_label(sup_uom)} · satuan supplier",
                "source": "supplier_item", "factor": probe["task_qty"],
                "hint": (f"1 {sup_uom} = {_id_num(probe['task_qty'])} {task_uom} "
                         f"(barang supplier {sup_item.get('supplier_sku')})"),
                "remaining": rem_doc,
            })
            seen.add(sup_uom)
        except ReceivingUomError:
            pass

    if mode != "off" and base_uom not in seen:
        try:
            probe = await convert_doc_qty(task, base_uom, 1, ctx=c,
                                          settings={**st,
                                                    "require_supplier_item_for_supplier_uom": False})
            options.append({
                "value": base_uom,
                "label": f"{_unit_label(base_uom)} · satuan dasar",
                "source": probe["source"], "factor": probe["task_qty"],
                "hint": f"1 {base_uom} = {_id_num(probe['task_qty'])} {task_uom}",
                "remaining": round(rem / probe["task_qty"], 2) if probe["task_qty"] else None,
            })
            seen.add(base_uom)
        except ReceivingUomError:
            pass

    default_uom = task_uom
    if mode == "prefer" and sup_uom and sup_uom in seen:
        default_uom = sup_uom

    return {
        "task_id": task.get("id"), "po_number": task.get("po_number", ""),
        "product_id": task.get("product_id"), "sku": task.get("sku", ""),
        "product_name": task.get("product_name") or product.get("name", ""),
        "task_uom": task_uom, "base_uom": base_uom,
        "expected_qty": round(parse_decimal(task.get("expected_qty") or 0), 2),
        "received_qty": round(parse_decimal(task.get("received_qty") or 0), 2),
        "remaining_qty": rem,
        "supplier": {"id": c["po"].get("supplier_id", ""),
                     "name": c["po"].get("supplier_name", "") or task.get("supplier_name", "")},
        "supplier_item": ({
            "id": sup_item.get("id"), "supplier_sku": sup_item.get("supplier_sku"),
            "supplier_item_name": sup_item.get("supplier_item_name"),
            "supplier_uom": sup_uom, "conv_factor": conv,
            "expected_grade": sup_item.get("expected_grade", ""),
            "last_price": sup_item.get("last_price", 0),
        } if sup_item else None),
        "mode": mode, "settings": st,
        "default_uom": default_uom, "options": options,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. PRATINJAU (F1-05) — tidak menulis apa pun
# ═══════════════════════════════════════════════════════════════════════════
async def preview(task: Dict[str, Any], doc_uom: str, doc_qty: Any,
                  tolerance_pct: float = 0.0) -> Dict[str, Any]:
    c = await task_context(task)
    st = await get_settings()
    trail = await convert_doc_qty(task, doc_uom, doc_qty, ctx=c, settings=st)
    rem = remaining_qty(task)
    rem_doc = await to_doc_uom(task, rem, trail["doc_uom"], ctx=c)
    max_qty = round(parse_decimal(task.get("expected_qty") or 0) * (1 + tolerance_pct / 100.0), 4)
    after = round(parse_decimal(task.get("received_qty") or 0) + trail["task_qty"], 4)
    over = after > max_qty + 1e-6
    return {
        "trail": trail, "remaining_qty": rem, "remaining_in_doc_uom": rem_doc,
        "received_after": after, "expected_qty": round(parse_decimal(task.get("expected_qty") or 0), 2),
        "max_qty": max_qty, "tolerance_pct": tolerance_pct,
        "over_remaining": over,
        "level": "block" if (over and bool(st.get("block_over_remaining", True))) else
                 ("warn" if over else "ok"),
        "message": (dual_unit_message(trail, rem, rem_doc, max_qty, after) if over else ""),
    }


def dual_unit_message(trail: Dict[str, Any], rem: float, rem_doc: Optional[float],
                      max_qty: float, after: float) -> str:
    """Pesan penolakan/peringatan yang menyebut **kedua satuan** (F1-06)."""
    t_uom, d_uom = trail["task_uom"], trail["doc_uom"]
    head = (f"Qty terima {_id_num(after, 2)} {t_uom} melebihi batas PO "
            f"{_id_num(max_qty, 2)} {t_uom}.")
    inp = (f" Input Anda: {_id_num(trail['doc_qty'], 2)} {d_uom} = "
           f"{_id_num(trail['task_qty'], 2)} {t_uom}." if d_uom != t_uom else "")
    sisa = f" Sisa {_id_num(rem, 2)} {t_uom}"
    if d_uom != t_uom and rem_doc is not None:
        sisa += f" ≈ {_id_num(rem_doc, 2)} {d_uom}"
    return head + inp + sisa + ". Gunakan Eskalasi bila kiriman memang lebih."


# ═══════════════════════════════════════════════════════════════════════════
# 6. ORKESTRASI UNTUK ROUTER (agar router tetap tipis)
# ═══════════════════════════════════════════════════════════════════════════
async def prepare_scan(task: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    """Hitung qty efektif (satuan task) + jejak konversi untuk satu `scan-receive`.

    `doc_uom` + `doc_qty` diisi ⇒ dikonversi & `actual_qty` diabaikan (F1-01).
    Kosong ⇒ pakai `actual_qty` apa adanya (perilaku lama, backward-compatible).
    """
    trail: Dict[str, Any] = {}
    ctx: Optional[Dict[str, Any]] = None
    qty = float(getattr(payload, "actual_qty", 0) or 0)
    doc_uom = (getattr(payload, "doc_uom", "") or "").strip()
    doc_qty = getattr(payload, "doc_qty", None)
    if doc_uom and doc_qty is not None and float(doc_qty or 0) > 0:
        ctx = await task_context(task)
        trail = await convert_doc_qty(task, doc_uom, doc_qty, ctx=ctx)
        qty = trail["task_qty"]
    if qty <= 0:
        raise ReceivingUomError(
            "Qty terima harus lebih besar dari 0 — isi `actual_qty` (satuan KN) atau "
            "`doc_uom` + `doc_qty` (satuan surat jalan supplier).")
    return {"qty": round(qty, 4), "trail": trail, "ctx": ctx}


async def over_limit_message(task: Dict[str, Any], prepared: Dict[str, Any],
                             max_qty: float, after: float) -> str:
    """Pesan tolak over-receipt (dua satuan bila input memakai satuan supplier)."""
    trail = prepared.get("trail") or {}
    rem = remaining_qty(task)
    rem_doc = await to_doc_uom(task, rem, trail["doc_uom"], ctx=prepared.get("ctx"))
    return dual_unit_message(trail, rem, rem_doc, max_qty, after)


async def receive_tolerance_pct(task: Dict[str, Any]) -> float:
    """Toleransi kedatangan ±X% (Fase 3 · configurable per entitas, default 2%)."""
    from services.config_service import get_effective_settings
    po = await db.purchase_orders.find_one({"id": task.get("po_id")}, {"_id": 0, "entity_id": 1})
    st = await get_effective_settings((po or {}).get("entity_id"))
    return float((st.get("purchasing", {}) or {}).get("receive_tolerance_percent", 2.0) or 0)


async def preflight_scan(task: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    """SEMUA pemeriksaan sebelum menulis: konversi satuan (F1-01/02) + toleransi kedatangan.

    Router cukup memanggil ini lalu menyimpan hasilnya — sehingga aturan bisnis tinggal di
    satu tempat (SSOT) dan router tetap tipis. Melempar `ReceivingUomError` dengan pesan
    siap-tampil (termasuk pesan dua satuan F1-06 bila over-receipt).
    """
    prep = await prepare_scan(task, payload)
    st = await get_settings()
    expected = parse_decimal(task.get("expected_qty") or 0)
    new_received = round(parse_decimal(task.get("received_qty") or 0) + prep["qty"], 4)
    tol_pct = await receive_tolerance_pct(task)
    max_qty = round(expected * (1 + tol_pct / 100.0), 4)
    over = new_received > max_qty + 1e-6
    # FASE G-0 (perbaikan defect F1-08) — kebijakan `receiving.block_over_remaining` kini
    # DIHORMATI server. Sebelumnya pratinjau memberi level "warn" (Submit aktif) padahal
    # server SELALU menolak 400 ⇒ UI dan mesin bertentangan (config = tombol palsu).
    # Sekarang: True  → tolak (perilaku lama)
    #           False → TERIMA, tetapi tandai `over_receipt` + pesan agar bisa ditindaklanjuti.
    block = bool(st.get("block_over_remaining", True))
    over_msg = ""
    if over:
        if prep["trail"]:
            over_msg = await over_limit_message(task, prep, max_qty, new_received)
        else:
            over_msg = (f"Qty terima ({new_received:g}) melebihi toleransi +{tol_pct:g}% dari PO "
                        f"({expected:g}, maks {max_qty:g}).")
        if block:
            raise ReceivingUomError(
                over_msg if prep["trail"] else
                over_msg + " Gunakan Eskalasi untuk penyesuaian manager.")
    var_pct = round((new_received - expected) / expected * 100.0, 2) if expected else 0.0
    return {**prep, "new_received": new_received, "expected_qty": expected,
            "tolerance_pct": tol_pct, "tolerance_qty": max_qty,
            "variance_pct": var_pct, "within_tolerance": abs(var_pct) <= tol_pct,
            "over_receipt": over, "over_blocked": block,
            "over_message": over_msg if over else ""}
