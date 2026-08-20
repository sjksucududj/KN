"""FASE D — KONTRAK MITRA/SUPPLIER (`supplier_contracts`) + MESIN TARIF CONFIGURABLE.

Rujukan: `docs/KN_24_PLAN_FASE_D_MAKLOON.md` · KN_18 §5.1/§5.2 · PS-06 · PS-11.

Keputusan pemilik (mengikat, sesi 2026-07-25):
  * **D-07** — "semua basis didukung, bisa custom, jangan terpaku pada satu variabel":
    tarif dihitung dari `tariff_basis` BEBAS (pick|kg|meter|yard|bale|cone|roll|lot|
    lumpsum|custom) + `tariff_formula` opsional (dievaluasi AMAN lewat AST terbatas)
    + `aux_fees[]` (mis. biaya screen & repeat printing) + `min_charge`.
  * **D-05** — susut standar (`shrinkage_pct`) ditentukan **per mitra/kontrak**.
  * **D-09** — toleransi selisih (`tolerance_pct`) juga per kontrak; bila kosong →
    kebijakan global `system_settings` scope `makloon`.

Prinsip (jangan dilanggar):
  1. SSOT harga/tarif & toleransi = koleksi ini. Dokumen (order makloon/PO) hanya
     menyimpan SNAPSHOT + `contract_id` (jangan hitung ulang di router/FE).
  2. Konversi satuan HANYA lewat `uom_service`/`uom_rules_service` (R4) dan WAJIB
     menyimpan jejak (D-07).
  3. Tidak ada angka karangan: bila faktor konversi tidak ada → error yang bisa
     ditindak (bukan diam-diam memakai 1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import domain_registry as dr
from core_utils import new_id, next_doc_number, now_iso, parse_decimal, safe_doc, rupiah
from db import db
from services import uom_service
from services import uom_rules_service as uomr
from services.process_recipe_service import safe_eval_formula

COLL = "supplier_contracts"
SETTINGS_SCOPE = "makloon"

CONTRACT_TYPES = ("makloon", "purchase", "internal")
CONTRACT_STATUSES = ("draft", "active", "expired", "terminated")
QTY_SOURCES = ("output", "input")
AUX_BASES = ("lumpsum", "per_roll", "per_color", "per_repeat", "per_kg",
             "per_meter", "per_output_unit")

# Kebijakan makloon — configurable tanpa deploy (D-05/D-09).
DEFAULT_SETTINGS: Dict[str, Any] = {
    "variance_tolerance_pct": 3.0,      # dipakai bila kontrak tidak menetapkan
    "default_shrinkage_pct": 0.0,       # tidak mengarang susut bila kontrak kosong
    "contract_mode": "warn",            # off | warn | block (order tanpa kontrak aktif)
    "auto_claim": True,                 # selisih di luar toleransi → klaim otomatis dibuka
    "claim_approval_roles": ["manager", "admin"],
    "require_output_product": True,     # KN_18 §5.2 — output produk wajib per langkah
    "require_yield_reason": True,       # PS-03 — override yield wajib beralasan
}


class ContractError(Exception):
    """Pelanggaran aturan kontrak/tarif (dipetakan ke HTTP 400 di router)."""


# ═══════════════════════════════════════════════════════════════════════════
# 1. KEBIJAKAN (system_settings scope `makloon`)
# ═══════════════════════════════════════════════════════════════════════════
async def get_settings(entity_id: str = "") -> Dict[str, Any]:
    """Kebijakan efektif. FASE E-4 (E4.5): bila `entity_id` diisi, setelan khusus
    badan usaha itu MENIMPA nilai global — dulu satu nilai memaksa seluruh grup.
    Tanpa `entity_id` perilakunya identik dengan sebelumnya (nol risiko regresi).
    """
    doc = await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 0}) or {}
    out = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        if doc.get(key) is not None:
            out[key] = doc[key]
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
    mode = (payload.get("contract_mode") or "").strip().lower()
    if mode:
        if mode not in ("off", "warn", "block"):
            raise ContractError("Mode kontrak harus 'off', 'warn', atau 'block'.")
        nxt["contract_mode"] = mode
    for key in ("variance_tolerance_pct", "default_shrinkage_pct"):
        if payload.get(key) is not None:
            val = parse_decimal(payload[key])
            if val < 0 or val > 100:
                raise ContractError(f"{key} harus 0–100 persen.")
            nxt[key] = val
    for flag in ("auto_claim", "require_output_product", "require_yield_reason"):
        if payload.get(flag) is not None:
            nxt[flag] = bool(payload[flag])
    roles = payload.get("claim_approval_roles")
    if roles is not None:
        if not isinstance(roles, list) or not roles:
            raise ContractError("Peran penyetuju klaim minimal satu (mis. manager, admin).")
        nxt["claim_approval_roles"] = [str(r).strip().lower() for r in roles if str(r).strip()]
    nxt.update({"scope": SETTINGS_SCOPE, "updated_at": now_iso(), "updated_by": actor})
    await db.system_settings.update_one({"scope": SETTINGS_SCOPE}, {"$set": nxt}, upsert=True)
    return await get_settings()


async def ensure_defaults(actor: str = "bootstrap") -> bool:
    """Pasang kebijakan makloon default bila belum ada (idempoten)."""
    if await db.system_settings.find_one({"scope": SETTINGS_SCOPE}, {"_id": 1}):
        return False
    await db.system_settings.update_one(
        {"scope": SETTINGS_SCOPE},
        {"$set": {**DEFAULT_SETTINGS, "scope": SETTINGS_SCOPE,
                  "updated_at": now_iso(), "updated_by": actor}}, upsert=True)
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 2. CRUD KONTRAK
# ═══════════════════════════════════════════════════════════════════════════
def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


async def next_contract_number(entity_id: str = "") -> str:
    return await next_doc_number(COLL, "contract_number", "SCT-", width=5,
                                 entity_id=entity_id or None)


async def _partner_snapshot(contract_type: str, partner_id: str) -> Dict[str, str]:
    """Kembalikan snapshot mitra. FASE G-6: contract_type='internal' → partner adalah PT.

    - 'makloon'  → koleksi `makloons`, partner_kind='makloon'
    - 'internal' → koleksi `business_entities`, partner_kind='entity' (PT dalam grup)
    - default   → koleksi `suppliers`, partner_kind='supplier'
    """
    if not partner_id:
        kind = {"makloon": "makloon", "internal": "entity"}.get(contract_type, "supplier")
        return {"name": "", "kind": kind}
    if contract_type == "internal":
        coll = db.business_entities
        kind = "entity"
    elif contract_type == "makloon":
        coll = db.makloons
        kind = "makloon"
    else:
        coll = db.suppliers
        kind = "supplier"
    doc = await coll.find_one({"id": partner_id}, {"_id": 0, "name": 1}) or {}
    return {"name": doc.get("name", ""), "kind": kind}


async def _product_snapshot(product_id: str) -> Dict[str, str]:
    if not product_id:
        return {"sku": "", "name": "", "base_unit": ""}
    p = await db.products.find_one({"id": product_id},
                                   {"_id": 0, "sku": 1, "name": 1, "base_unit": 1}) or {}
    return {"sku": p.get("sku", ""), "name": p.get("name", ""),
            "base_unit": p.get("base_unit", "")}


def _validate_aux(fees: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in fees or []:
        basis = (f.get("basis") or "lumpsum").strip().lower()
        if basis not in AUX_BASES:
            raise ContractError(
                f"Basis biaya tambahan '{basis}' tidak dikenal. Pilihan: {', '.join(AUX_BASES)}.")
        out.append({"code": (f.get("code") or "").strip(),
                    "label": (f.get("label") or "").strip(),
                    "basis": basis, "amount": parse_decimal(f.get("amount"), 2)})
    return out


def _validate_core(doc: Dict[str, Any]) -> None:
    ctype = doc.get("contract_type")
    if ctype not in CONTRACT_TYPES:
        raise ContractError(
            f"Jenis kontrak harus salah satu: {', '.join(CONTRACT_TYPES)}.")
    if not doc.get("partner_id"):
        raise ContractError("Mitra/supplier kontrak wajib dipilih.")
    basis = (doc.get("tariff_basis") or "").strip().lower()
    allowed = set(dr.values_of("tariff_basis")) | {"lumpsum", "custom"}
    if basis and basis not in allowed:
        raise ContractError(
            f"Basis tarif '{basis}' tidak dikenal. Pilihan: {', '.join(sorted(allowed))}.")
    if ctype == "makloon":
        pt = (doc.get("process_type") or "").strip()
        if not pt:
            raise ContractError("Jenis proses wajib diisi untuk kontrak makloon.")
        if not dr.is_valid("process_type", pt):
            raise ContractError(
                f"Jenis proses '{pt}' tidak ada di registry. Pilihan: "
                f"{', '.join(dr.values_of('process_type'))}.")
    if doc.get("tariff_qty_source") not in QTY_SOURCES:
        raise ContractError("Dasar qty tarif harus 'output' atau 'input'.")
    vf, vt = doc.get("valid_from") or "", doc.get("valid_to") or ""
    if vf and vt and vt < vf:
        raise ContractError("Masa berlaku kontrak tidak valid (berakhir sebelum mulai).")
    if doc.get("status") not in CONTRACT_STATUSES:
        raise ContractError(f"Status kontrak harus salah satu: {', '.join(CONTRACT_STATUSES)}.")


async def create_contract(payload: Dict[str, Any], *, entity_id: str,
                          actor: str = "") -> Dict[str, Any]:
    ctype = (payload.get("contract_type") or "makloon").strip().lower()
    partner_id = payload.get("partner_id") or ""
    psnap = await _partner_snapshot(ctype, partner_id)
    prod = await _product_snapshot(payload.get("product_id") or "")
    tol = payload.get("tolerance_pct")
    doc: Dict[str, Any] = {
        "id": new_id("sct"),
        "contract_number": "",
        "entity_id": entity_id or "",
        "contract_type": ctype,
        "partner_kind": psnap["kind"],
        "partner_id": partner_id,
        "partner_name": payload.get("partner_name") or psnap["name"],
        "title": (payload.get("title") or "").strip(),
        "process_type": (payload.get("process_type") or "").strip(),
        "product_id": payload.get("product_id") or "",
        "product_sku": prod["sku"], "product_name": prod["name"],
        "input_product_id": payload.get("input_product_id") or "",
        "tariff_basis": (payload.get("tariff_basis") or "lumpsum").strip().lower(),
        "tariff_rate": parse_decimal(payload.get("tariff_rate"), 2),
        "tariff_formula": (payload.get("tariff_formula") or "").strip(),
        "tariff_qty_source": (payload.get("tariff_qty_source") or "output").strip().lower(),
        "ppi": parse_decimal(payload.get("ppi")),
        "aux_fees": _validate_aux(payload.get("aux_fees")),
        "min_charge": parse_decimal(payload.get("min_charge"), 2),
        "currency": payload.get("currency") or "IDR",
        "shrinkage_pct": parse_decimal(payload.get("shrinkage_pct")),
        "tolerance_pct": None if tol in (None, "") else parse_decimal(tol),
        "yield_factor": parse_decimal(payload.get("yield_factor")),
        "byproduct_pct": parse_decimal(payload.get("byproduct_pct")),
        "moq": parse_decimal(payload.get("moq")),
        "lead_time_days": int(payload.get("lead_time_days") or 0),
        "payment_term_code": payload.get("payment_term_code") or "",
        "valid_from": payload.get("valid_from") or _today(),
        "valid_to": payload.get("valid_to") or "",
        "status": (payload.get("status") or "active").strip().lower(),
        "sample_ref": payload.get("sample_ref") or "",
        "notes": payload.get("notes") or "",
        "usage_count": 0,
        "created_at": now_iso(), "created_by": actor,
        "updated_at": now_iso(), "updated_by": actor,
    }
    _validate_core(doc)
    doc["contract_number"] = await next_contract_number(entity_id)
    await db[COLL].insert_one(dict(doc))
    return safe_doc(doc)


async def get_contract(cid: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db[COLL].find_one({"id": cid}, {"_id": 0}))


async def patch_contract(cid: str, payload: Dict[str, Any], actor: str = "") -> Dict[str, Any]:
    cur = await db[COLL].find_one({"id": cid}, {"_id": 0})
    if not cur:
        raise ContractError("Kontrak tidak ditemukan.")
    nxt = dict(cur)
    for key in ("title", "partner_name", "process_type", "product_id", "input_product_id",
                "tariff_basis", "tariff_formula", "tariff_qty_source", "payment_term_code",
                "valid_from", "valid_to", "sample_ref", "notes"):
        if payload.get(key) is not None:
            nxt[key] = payload[key]
    for key in ("tariff_rate", "min_charge"):
        if payload.get(key) is not None:
            nxt[key] = parse_decimal(payload[key], 2)
    for key in ("ppi", "shrinkage_pct", "yield_factor", "byproduct_pct", "moq"):
        if payload.get(key) is not None:
            nxt[key] = parse_decimal(payload[key])
    if payload.get("tolerance_pct") is not None:
        nxt["tolerance_pct"] = parse_decimal(payload["tolerance_pct"])
    if payload.get("lead_time_days") is not None:
        nxt["lead_time_days"] = int(payload["lead_time_days"] or 0)
    if payload.get("aux_fees") is not None:
        nxt["aux_fees"] = _validate_aux(payload["aux_fees"])
    if payload.get("product_id") is not None:
        snap = await _product_snapshot(payload["product_id"])
        nxt["product_sku"], nxt["product_name"] = snap["sku"], snap["name"]
    _validate_core(nxt)
    nxt["updated_at"], nxt["updated_by"] = now_iso(), actor
    await db[COLL].replace_one({"id": cid}, nxt)
    return safe_doc(nxt)


async def set_status(cid: str, status: str, reason: str = "", actor: str = "") -> Dict[str, Any]:
    status = (status or "").strip().lower()
    if status not in CONTRACT_STATUSES:
        raise ContractError(f"Status kontrak harus salah satu: {', '.join(CONTRACT_STATUSES)}.")
    cur = await db[COLL].find_one({"id": cid}, {"_id": 0})
    if not cur:
        raise ContractError("Kontrak tidak ditemukan.")
    await db[COLL].update_one({"id": cid}, {"$set": {
        "status": status, "status_reason": reason,
        "updated_at": now_iso(), "updated_by": actor}})
    return await get_contract(cid)


def _rx(term: str) -> Dict[str, Any]:
    import re
    return {"$regex": re.escape(term.strip()), "$options": "i"}


async def list_contracts(query: Dict[str, Any], *, q: str = "", limit: int = 200,
                         skip: int = 0, sort: str = "-created_at") -> List[Dict[str, Any]]:
    flt = dict(query or {})
    if q:
        flt["$or"] = [{"contract_number": _rx(q)}, {"partner_name": _rx(q)},
                      {"title": _rx(q)}, {"product_sku": _rx(q)}, {"product_name": _rx(q)}]
    field = sort.lstrip("-") or "created_at"
    direction = -1 if sort.startswith("-") else 1
    rows = await db[COLL].find(flt, {"_id": 0}).sort(field, direction) \
        .skip(max(skip, 0)).limit(max(min(limit, 500), 1)).to_list(500)
    return [safe_doc(r) for r in rows]


async def count_contracts(query: Dict[str, Any]) -> int:
    return await db[COLL].count_documents(query or {})


async def stats(query: Dict[str, Any]) -> Dict[str, Any]:
    rows = await db[COLL].find(query or {}, {"_id": 0}).to_list(2000)
    today = _today()
    active = [r for r in rows if r.get("status") == "active"
              and (not r.get("valid_to") or r["valid_to"] >= today)]
    expiring = [r for r in active if r.get("valid_to") and r["valid_to"] <= _plus_days(today, 30)]
    return {
        "total": len(rows),
        "active": len(active),
        "makloon": len([r for r in rows if r.get("contract_type") == "makloon"]),
        "purchase": len([r for r in rows if r.get("contract_type") == "purchase"]),
        "expiring_30d": len(expiring),
        "draft": len([r for r in rows if r.get("status") == "draft"]),
        "terminated": len([r for r in rows if r.get("status") in ("terminated", "expired")]),
    }


def _plus_days(iso_date: str, days: int) -> str:
    from datetime import timedelta
    try:
        d = datetime.fromisoformat(iso_date).date()
    except ValueError:
        return iso_date
    return (d + timedelta(days=days)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# 3. RESOLVER KONTRAK AKTIF (paling spesifik menang)
# ═══════════════════════════════════════════════════════════════════════════
async def resolve_active(*, partner_id: str, contract_type: str = "makloon",
                         process_type: str = "", product_id: str = "",
                         input_product_id: str = "", entity_id: str = "",
                         at: str = "") -> Optional[Dict[str, Any]]:
    """Kontrak aktif paling spesifik untuk (mitra × proses × produk) pada tanggal `at`."""
    if not partner_id:
        return None
    day = at or _today()
    flt: Dict[str, Any] = {"contract_type": contract_type, "partner_id": partner_id,
                           "status": "active"}
    if entity_id:
        flt["entity_id"] = {"$in": [entity_id, "", None]}
    rows = await db[COLL].find(flt, {"_id": 0}).to_list(500)
    best, best_score = None, -1
    for r in rows:
        if r.get("valid_from") and r["valid_from"] > day:
            continue
        if r.get("valid_to") and r["valid_to"] < day:
            continue
        if process_type and r.get("process_type") and r["process_type"] != process_type:
            continue
        if product_id and r.get("product_id") and r["product_id"] != product_id:
            continue
        if input_product_id and r.get("input_product_id") and r["input_product_id"] != input_product_id:
            continue
        score = 0
        if r.get("product_id") == product_id and product_id:
            score += 4
        if r.get("process_type") == process_type and process_type:
            score += 2
        if r.get("input_product_id") == input_product_id and input_product_id:
            score += 1
        if score > best_score:
            best, best_score = r, score
    return safe_doc(best) if best else None


async def mark_used(cid: str) -> None:
    if cid:
        await db[COLL].update_one({"id": cid}, {"$inc": {"usage_count": 1},
                                                "$set": {"last_used_at": now_iso()}})


# ═══════════════════════════════════════════════════════════════════════════
# 4. MESIN TARIF (D-07 — basis bebas + formula custom + jejak konversi)
# ═══════════════════════════════════════════════════════════════════════════
BASIS_UNIT_MAP = {"kg": "kg", "meter": "meter", "yard": "yard",
                  "ball": "bale", "bale": "bale", "cone": "cone"}


def _product_ppi(product: Dict[str, Any]) -> float:
    cons = product.get("construction") or {}
    if isinstance(cons, dict):
        return parse_decimal(cons.get("ppi") or 0)
    return 0.0


async def compute_tariff(*, product: Dict[str, Any], qty_base: Any,
                         contract: Optional[Dict[str, Any]] = None,
                         override: Optional[Dict[str, Any]] = None,
                         roll_count: int = 0, colors: int = 0, repeats: int = 0,
                         engine: Optional[Dict[str, Any]] = None,
                         label: str = "") -> Dict[str, Any]:
    """Hitung ongkos jasa makloon + **jejak yang bisa diaudit**.

    `override` (dari langkah order) MENANG atas kontrak → kasus ad-hoc tetap terlayani
    tanpa mengubah kontrak. Semua angka antara dikembalikan di `explain[]` supaya
    user/manajer bisa memeriksa (PS-03/PS-11 “bisa diaudit”).
    """
    ov = {k: v for k, v in (override or {}).items() if v not in (None, "")}
    ct = contract or {}
    basis = str(ov.get("tariff_basis") or ct.get("tariff_basis") or "lumpsum").strip().lower()
    rate = parse_decimal(ov.get("tariff_rate", ct.get("tariff_rate") or 0), 2)
    formula = str(ov.get("tariff_formula") or ct.get("tariff_formula") or "").strip()
    min_charge = parse_decimal(ov.get("min_charge", ct.get("min_charge") or 0), 2)
    aux_src = ov.get("aux_fees") if ov.get("aux_fees") is not None else ct.get("aux_fees")
    aux_fees = _validate_aux(aux_src or [])
    ppi = parse_decimal(ov.get("ppi", ct.get("ppi") or 0)) or _product_ppi(product)

    qty = parse_decimal(qty_base)
    base_unit = uomr.normalize_unit(product.get("base_unit") or "meter")
    eng = engine or await uomr.load_engine()
    explain: List[str] = []
    warnings: List[str] = []
    conversion: Dict[str, Any] = {}

    async def _conv(target: str) -> float:
        nonlocal conversion
        if uomr.normalize_unit(target) == base_unit:
            conversion = {"factor": 1.0, "source": "same_unit",
                          "from": base_unit, "to": base_unit}
            return qty
        trail = await uomr.convert_with_trail(product, qty, base_unit, target,
                                              engine=eng, context=f"tarif:{label}")
        conversion = {"factor": trail["factor"], "source": trail["source"],
                      "from": trail["doc_uom"], "to": trail["base_uom"],
                      "rule_id": trail.get("rule_id", "")}
        explain.append(f"Konversi {qty:g} {base_unit} → {trail['base_qty']:g} {target} "
                       f"(faktor {trail['factor']:g} · sumber {trail['source']})")
        return float(trail["base_qty"])

    basis_uom = basis
    if basis in ("lumpsum", "lot", "custom"):
        basis_qty = 1.0
        basis_uom = "lot" if basis == "lot" else basis
        explain.append(f"Basis {basis} → dihitung borongan (1 × tarif).")
    elif basis == "roll":
        basis_qty = float(roll_count or 0) or 1.0
        basis_uom = "roll"
        explain.append(f"Basis per roll → {basis_qty:g} roll × tarif.")
    elif basis == "pick":
        meters = await _conv("meter")
        if ppi <= 0:
            raise ContractError(
                "Basis tarif 'pick' butuh PPI (pick per inch). Isi konstruksi produk "
                "(construction.ppi) atau field PPI pada kontrak/langkah order.")
        basis_qty = round(meters * ppi, 3)
        basis_uom = "pick·meter"
        explain.append(f"Basis pick → {meters:g} meter × PPI {ppi:g} = {basis_qty:g} pick·meter.")
    else:
        target = BASIS_UNIT_MAP.get(basis, basis)
        basis_qty = round(await _conv(target), 3)
        basis_uom = target
        explain.append(f"Basis {target} → qty tarif {basis_qty:g} {target}.")

    gsm = parse_decimal(product.get("gramasi") or 0)
    lebar = parse_decimal(product.get("lebar") or 0)
    variables = {"qty_base": qty, "basis_qty": basis_qty, "rate": rate, "gsm": gsm,
                 "gramasi": gsm, "lebar": lebar, "ppi": ppi,
                 "roll_count": float(roll_count or 0), "colors": float(colors or 0),
                 "repeats": float(repeats or 0), "min_charge": min_charge}
    formula_used = ""
    if formula:
        try:
            service_amount = round(float(safe_eval_formula(formula, variables)), 2)
            formula_used = formula
            explain.append(f"Formula kontrak dipakai: {formula} → {rupiah(service_amount)}")
        except (ValueError, SyntaxError, TypeError) as exc:
            warnings.append(f"Formula tarif gagal dievaluasi ({exc}); memakai tarif × basis.")
            service_amount = round(rate * basis_qty, 2)
    else:
        service_amount = round(rate * basis_qty, 2)
        explain.append(f"Ongkos jasa = tarif {rupiah(rate)} × {basis_qty:g} {basis_uom} "
                       f"= {rupiah(service_amount)}")

    # Biaya tambahan (screen/repeat/dll)
    aux_breakdown: List[Dict[str, Any]] = []
    aux_total = 0.0
    for fee in aux_fees:
        amt = parse_decimal(fee["amount"], 2)
        b = fee["basis"]
        if b == "lumpsum":
            value = amt
        elif b == "per_roll":
            value = amt * float(roll_count or 0)
        elif b == "per_color":
            value = amt * float(colors or 0)
        elif b == "per_repeat":
            value = amt * float(repeats or 0)
        elif b == "per_output_unit":
            value = amt * qty
        elif b == "per_kg":
            value = amt * (await _conv("kg") if base_unit != "kg" else qty)
        elif b == "per_meter":
            value = amt * (await _conv("meter") if base_unit != "meter" else qty)
        else:
            value = amt
        value = round(value, 2)
        aux_total += value
        aux_breakdown.append({**fee, "value": value})
        if value:
            explain.append(f"Biaya {fee['label'] or fee['code'] or b}: {rupiah(value)} ({b})")
    aux_total = round(aux_total, 2)

    total = round(service_amount + aux_total, 2)
    min_applied = False
    if min_charge > 0 and total < min_charge:
        explain.append(f"Tagihan minimum kontrak {rupiah(min_charge)} berlaku "
                       f"(hitungan {rupiah(total)}).")
        total = min_charge
        min_applied = True

    return {
        "basis": basis, "basis_qty": round(basis_qty, 3), "basis_uom": basis_uom,
        "rate": rate, "qty_base": qty, "base_uom": base_unit,
        "conversion": conversion, "formula_used": formula_used,
        "service_amount": round(service_amount, 2),
        "aux_total": aux_total, "aux_breakdown": aux_breakdown,
        "min_charge": min_charge, "min_charge_applied": min_applied,
        "amount": total,
        "contract_id": ct.get("id", ""), "contract_number": ct.get("contract_number", ""),
        "source": "override" if ov.get("tariff_basis") or ov.get("tariff_rate") is not None
                  else ("contract" if ct else "manual"),
        "explain": explain, "warnings": warnings, "computed_at": now_iso(),
    }


async def tariff_preview(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simulasi tarif untuk wizard (tanpa menyimpan apa pun)."""
    product = await db.products.find_one({"id": payload.get("product_id")}, {"_id": 0})
    if not product:
        raise ContractError("Produk untuk simulasi tarif tidak ditemukan.")
    contract = None
    if payload.get("contract_id"):
        contract = await get_contract(payload["contract_id"])
        if not contract:
            raise ContractError("Kontrak tidak ditemukan.")
    elif payload.get("partner_id"):
        contract = await resolve_active(partner_id=payload["partner_id"],
                                        process_type=payload.get("process_type") or "",
                                        product_id=payload.get("product_id") or "")
    qty = parse_decimal(payload.get("qty"))
    unit = uomr.normalize_unit(payload.get("unit") or product.get("base_unit") or "meter")
    base_unit = uomr.normalize_unit(product.get("base_unit") or "meter")
    eng = await uomr.load_engine()
    input_trail = None
    if unit != base_unit:
        input_trail = await uomr.convert_with_trail(product, qty, unit, base_unit,
                                                    engine=eng, context="tarif_preview")
        qty = float(input_trail["base_qty"])
    override = {k: payload.get(k) for k in
                ("tariff_basis", "tariff_rate", "tariff_formula", "min_charge", "ppi")
                if payload.get(k) not in (None, "")}
    if payload.get("aux_fees"):
        override["aux_fees"] = payload["aux_fees"]
    result = await compute_tariff(product=product, qty_base=qty, contract=contract,
                                  override=override, roll_count=int(payload.get("roll_count") or 0),
                                  colors=int(payload.get("colors") or 0),
                                  repeats=int(payload.get("repeats") or 0), engine=eng,
                                  label="preview")
    result["input_trail"] = input_trail
    result["contract"] = contract
    return result
