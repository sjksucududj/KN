"""R6.3 — Budget Control penuh: Anggaran vs Komitmen vs Realisasi + enforcement.

Koleksi:
- `budgets` (prefix `budget_`) — anggaran per (entity_id, year, month, dimension, key).
  * `dimension` = "account" (kode akun COA) | "category" (kode kategori beban).
  * `month` 0 = anggaran TAHUNAN; 1..12 = anggaran BULANAN.
  * `key` = account_code | expense category code. `account_code` dipertahankan (legacy/back-compat).
- `fin_budget_rules` (prefix `bgrule_`) — kebijakan over-budget per ENTITAS (configurable):
  * `mode` = "off" | "warn" | "block"
  * `warn_threshold_pct` — ambang peringatan dini (default 85%)
  * `unbudgeted_action` = "allow" | "warn" | "block" (bila belum ada anggaran utk key tsb)
  * `enforce_po_create` / `enforce_po_approve` — titik penegakan.

Sumber angka (semua diturunkan / derived — TIDAK ada materialized cache, GL-safe):
- **Realisasi (actual)**
  * dimension=account   → `journal_entries` (non-void, exclude closing) per account_code & bulan.
  * dimension=category  → `cash_advance_settlements` status `posted_to_gl` (`category_totals`).
- **Komitmen (committed)**
  * PO terbuka (`purchase_orders` status ∈ OPEN_PO_STATUSES) → key dari `budget_key`/`budget_dimension`
    PO (bila di-tag) atau default akun Persediaan (1-1300); nilai = net_subtotal (DPP, excl PPN).
  * LPJ petty cash (`cash_advance_settlements` status draft/submitted) → per kategori beban.

Enforcement: `enforce_po_budget()` dipanggil dari router PO saat create & approve.
`mode=block` → ValueError (router → HTTP 400/409); `mode=warn` → daftar peringatan; `off` → lewati.
"""
from typing import Any, Dict, List, Optional, Tuple

from db import db
from core_utils import now_iso, new_id, rupiah
from services import financial_statement_service as fs

EPS = 0.005

DIM_ACCOUNT = "account"
DIM_CATEGORY = "category"
DIMENSIONS = (DIM_ACCOUNT, DIM_CATEGORY)

RULES_COLL = "fin_budget_rules"
DEFAULT_PO_BUDGET_ACCOUNT = "1-1300"          # Persediaan Barang (belanja barang dagang)
OPEN_PO_STATUSES = ["draft", "submitted", "waiting_approval", "pending", "approved",
                    "confirmed", "sent", "receiving", "partially_received"]
OPEN_STL_STATUSES = ["draft", "submitted"]     # LPJ belum diposting → komitmen
POSTED_STL_STATUS = "posted_to_gl"             # LPJ terposting → realisasi

DEFAULT_RULES = {
    "mode": "warn",
    "warn_threshold_pct": 85.0,
    "unbudgeted_action": "allow",
    "enforce_po_create": True,
    "enforce_po_approve": True,
}
VALID_MODES = ("off", "warn", "block")
VALID_UNBUDGETED = ("allow", "warn", "block")


def _r(v: Any) -> float:
    return round(float(v or 0), 2)


def _month_of(date_str: str) -> int:
    try:
        return int(str(date_str or "")[5:7] or 0)
    except (ValueError, TypeError):
        return 0


def _year_of(date_str: str) -> int:
    try:
        return int(str(date_str or "")[:4] or 0)
    except (ValueError, TypeError):
        return 0


async def _accounts_map() -> Dict[str, Dict[str, Any]]:
    return await fs._accounts_map()


async def _category_map(entity_id: str = "") -> Dict[str, Dict[str, Any]]:
    """Kategori biaya EFEKTIF untuk satu badan usaha (override → global).

    FASE E-4 (E4.3): satu kode kategori boleh dipetakan ke akun buku besar yang
    berbeda per badan usaha, jadi peta ini tidak boleh lagi dibaca tanpa lapisan.
    """
    from services import entity_master_service as ems
    rows = await ems.effective_rows("expense-categories", entity_id)
    return {r.get("code", ""): r for r in rows}


# ═══ Aturan (rules) per entitas ══════════════════════════════════════════════
async def get_rules(entity_id: str) -> Dict[str, Any]:
    doc = await db[RULES_COLL].find_one({"entity_id": entity_id}, {"_id": 0})
    out = {"entity_id": entity_id, **DEFAULT_RULES, "is_default": doc is None}
    if doc:
        for k in DEFAULT_RULES:
            if doc.get(k) is not None:
                out[k] = doc[k]
        out["updated_at"] = doc.get("updated_at", "")
        out["updated_by"] = doc.get("updated_by", "")
    return out


async def set_rules(entity_id: str, patch: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    upd: Dict[str, Any] = {}
    if patch.get("mode") is not None:
        if patch["mode"] not in VALID_MODES:
            raise ValueError(f"mode harus salah satu dari {', '.join(VALID_MODES)}.")
        upd["mode"] = patch["mode"]
    if patch.get("unbudgeted_action") is not None:
        if patch["unbudgeted_action"] not in VALID_UNBUDGETED:
            raise ValueError(f"unbudgeted_action harus salah satu dari {', '.join(VALID_UNBUDGETED)}.")
        upd["unbudgeted_action"] = patch["unbudgeted_action"]
    if patch.get("warn_threshold_pct") is not None:
        pct = float(patch["warn_threshold_pct"])
        if pct < 0 or pct > 100:
            raise ValueError("warn_threshold_pct harus 0–100.")
        upd["warn_threshold_pct"] = round(pct, 1)
    for k in ("enforce_po_create", "enforce_po_approve"):
        if patch.get(k) is not None:
            upd[k] = bool(patch[k])
    if not upd:
        return await get_rules(entity_id)
    upd.update({"entity_id": entity_id, "updated_at": now_iso(),
                "updated_by": actor.get("name", "system")})
    await db[RULES_COLL].update_one({"entity_id": entity_id},
                                    {"$set": upd, "$setOnInsert": {"id": new_id("bgrule")}},
                                    upsert=True)
    return await get_rules(entity_id)


# ═══ CRUD anggaran ═══════════════════════════════════════════════════════════
async def backfill_dimensions() -> int:
    """Idempotent — dokumen `budgets` lama (tanpa dimension) → dimension=account."""
    res = await db.budgets.update_many(
        {"dimension": {"$exists": False}},
        [{"$set": {"dimension": DIM_ACCOUNT, "key": "$account_code",
                   "label": {"$ifNull": ["$account_name", "$account_code"]}}}])
    return res.modified_count


async def list_budgets(scope: Optional[Dict[str, Any]], year: Optional[int] = None,
                       dimension: Optional[str] = None) -> List[Dict[str, Any]]:
    await backfill_dimensions()
    q: Dict[str, Any] = {**(scope or {})}
    if year:
        q["year"] = int(year)
    if dimension:
        q["dimension"] = dimension
    return await db.budgets.find(q, {"_id": 0}).sort(
        [("year", -1), ("dimension", 1), ("key", 1), ("month", 1)]).to_list(5000)


async def resolve_key(dimension: str, key: str, entity_id: str = "") -> Tuple[str, str]:
    """Validasi key & ambil label. Return (key, label). Raise ValueError bila tak dikenal."""
    key = (key or "").strip()
    if not key:
        raise ValueError("Kunci anggaran (akun/kategori) wajib diisi.")
    if dimension == DIM_ACCOUNT:
        acc = (await _accounts_map()).get(key)
        if not acc:
            raise ValueError(f"Akun COA '{key}' tidak ditemukan.")
        return key, acc.get("name", key)
    cat = (await _category_map(entity_id)).get(key)
    if not cat:
        raise ValueError(f"Kategori beban '{key}' tidak ditemukan.")
    return key, cat.get("label", key)


async def create_budget(payload: Dict[str, Any], entity_id: str) -> Dict[str, Any]:
    dimension = (payload.get("dimension") or DIM_ACCOUNT).strip()
    if dimension not in DIMENSIONS:
        raise ValueError("dimension harus 'account' atau 'category'.")
    raw_key = payload.get("key") or payload.get("account_code") or payload.get("category_code") or ""
    key, label = await resolve_key(dimension, raw_key, entity_id)
    year = int(payload.get("year") or 0)
    if year < 2000 or year > 2999:
        raise ValueError("Tahun anggaran tidak valid.")
    month = int(payload.get("month", 0) or 0)
    if month < 0 or month > 12:
        raise ValueError("Bulan harus 0 (tahunan) atau 1–12.")
    amount = _r(payload.get("amount", 0))
    if amount <= 0:
        raise ValueError("Nominal anggaran harus > 0.")
    dupe = await db.budgets.find_one({"entity_id": entity_id, "year": year, "month": month,
                                      "dimension": dimension, "key": key}, {"_id": 1})
    if dupe:
        raise ValueError("Anggaran untuk kombinasi entitas/tahun/bulan/kunci ini sudah ada — ubah saja.")
    amap = await _accounts_map()
    acc_code = key if dimension == DIM_ACCOUNT else (await _category_map(entity_id)).get(key, {}).get("account_code", "")
    doc = {
        "id": new_id("budget"),
        "entity_id": entity_id,
        "year": year,
        "month": month,
        "dimension": dimension,
        "key": key,
        "label": label,
        "account_code": acc_code,
        "account_name": amap.get(acc_code, {}).get("name", acc_code),
        "account_type": amap.get(acc_code, {}).get("type", ""),
        "amount": amount,
        "note": payload.get("note", ""),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.budgets.insert_one(dict(doc))
    return doc


async def update_budget(budget_id: str, patch: Dict[str, Any],
                        scope: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    q = {"id": budget_id, **(scope or {})}
    upd: Dict[str, Any] = {"updated_at": now_iso()}
    if patch.get("amount") is not None:
        amount = _r(patch["amount"])
        if amount <= 0:
            raise ValueError("Nominal anggaran harus > 0.")
        upd["amount"] = amount
    if patch.get("note") is not None:
        upd["note"] = patch["note"]
    for k in ("month", "year"):
        if patch.get(k) is not None:
            val = int(patch[k])
            if k == "month" and (val < 0 or val > 12):
                raise ValueError("Bulan harus 0 (tahunan) atau 1–12.")
            upd[k] = val
    res = await db.budgets.find_one_and_update(q, {"$set": upd}, return_document=True)
    if res:
        res.pop("_id", None)
    return res


async def delete_budget(budget_id: str, scope: Optional[Dict[str, Any]]) -> bool:
    res = await db.budgets.delete_one({"id": budget_id, **(scope or {})})
    return res.deleted_count > 0


# ═══ Realisasi (actual) ══════════════════════════════════════════════════════
async def _actual_by_account(scope: Optional[Dict[str, Any]], year: int) -> Dict[str, Dict[int, float]]:
    """Realisasi net per (account_code, month) dari jurnal operasional tahun tsb."""
    q: Dict[str, Any] = {"status": {"$ne": "void"}, "source_type": {"$ne": "closing"}, **(scope or {})}
    q["date"] = {"$gte": f"{year}-01-01T00:00:00", "$lte": f"{year}-12-31T23:59:59.999999"}
    amap = await _accounts_map()
    out: Dict[str, Dict[int, float]] = {}
    async for je in db.journal_entries.find(q, {"_id": 0, "date": 1, "lines": 1}):
        mm = _month_of(je.get("date", ""))
        for ln in je.get("lines", []):
            code = ln.get("account_code")
            if not code:
                continue
            atype = amap.get(code, {}).get("type", "")
            debit = _r(ln.get("debit", 0))
            credit = _r(ln.get("credit", 0))
            val = (credit - debit) if atype == "income" else (debit - credit)
            slot = out.setdefault(code, {})
            slot[mm] = round(slot.get(mm, 0.0) + val, 2)
    return out


async def _actual_by_category(scope: Optional[Dict[str, Any]], year: int) -> Dict[str, Dict[int, float]]:
    """Realisasi per (kategori beban, month) dari LPJ petty cash yang sudah diposting GL."""
    q: Dict[str, Any] = {"status": POSTED_STL_STATUS, **(scope or {})}
    out: Dict[str, Dict[int, float]] = {}
    async for stl in db.cash_advance_settlements.find(
            q, {"_id": 0, "created_at": 1, "periode": 1, "category_totals": 1}):
        ref = stl.get("periode") or stl.get("created_at") or ""
        if _year_of(ref) != int(year):
            continue
        mm = _month_of(ref)
        for cat, amt in (stl.get("category_totals") or {}).items():
            slot = out.setdefault(cat, {})
            slot[mm] = round(slot.get(mm, 0.0) + _r(amt), 2)
    return out


# ═══ Komitmen (committed) ════════════════════════════════════════════════════
def po_budget_targets(po: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Target anggaran sebuah PO. Nilai = DPP/net subtotal (excl PPN) agar setara beban."""
    amount = _r(po.get("net_subtotal") or po.get("dpp") or po.get("total_amount") or 0)
    dim = (po.get("budget_dimension") or "").strip()
    key = (po.get("budget_key") or "").strip()
    if dim in DIMENSIONS and key:
        return [{"dimension": dim, "key": key, "amount": amount}]
    return [{"dimension": DIM_ACCOUNT, "key": DEFAULT_PO_BUDGET_ACCOUNT, "amount": amount}]


async def _commitment_map(scope: Optional[Dict[str, Any]], year: int,
                          exclude_po_id: str = "") -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Komitmen per (dimension, key) → {'total', 'by_month', 'docs'} dari PO terbuka + LPJ pending."""
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _bump(dim: str, key: str, month: int, amt: float, label: str, ref: str):
        slot = out.setdefault((dim, key), {"total": 0.0, "by_month": {}, "docs": []})
        slot["total"] = round(slot["total"] + amt, 2)
        slot["by_month"][month] = round(slot["by_month"].get(month, 0.0) + amt, 2)
        if len(slot["docs"]) < 25:
            slot["docs"].append({"ref": ref, "label": label, "amount": amt})

    po_q: Dict[str, Any] = {"status": {"$in": OPEN_PO_STATUSES}, **(scope or {})}
    if exclude_po_id:
        po_q["id"] = {"$ne": exclude_po_id}
    async for po in db.purchase_orders.find(po_q, {
            "_id": 0, "id": 1, "po_number": 1, "net_subtotal": 1, "dpp": 1, "total_amount": 1,
            "grand_total": 1, "budget_dimension": 1, "budget_key": 1, "expected_delivery_date": 1,
            "created_at": 1, "supplier_name": 1}):
        ref_date = po.get("expected_delivery_date") or po.get("created_at") or ""
        if _year_of(ref_date) != int(year):
            continue
        for t in po_budget_targets(po):
            if t["amount"] <= EPS:
                continue
            _bump(t["dimension"], t["key"], _month_of(ref_date), t["amount"],
                  po.get("supplier_name", ""), po.get("po_number", ""))

    stl_q: Dict[str, Any] = {"status": {"$in": OPEN_STL_STATUSES}, **(scope or {})}
    async for stl in db.cash_advance_settlements.find(stl_q, {
            "_id": 0, "number": 1, "periode": 1, "created_at": 1, "category_totals": 1, "divisi": 1}):
        ref_date = stl.get("periode") or stl.get("created_at") or ""
        if _year_of(ref_date) != int(year):
            continue
        for cat, amt in (stl.get("category_totals") or {}).items():
            if _r(amt) <= EPS:
                continue
            _bump(DIM_CATEGORY, cat, _month_of(ref_date), _r(amt),
                  stl.get("divisi", ""), stl.get("number", ""))
    return out


# ═══ Laporan Anggaran vs Komitmen vs Realisasi ═══════════════════════════════
def _status_of(budget: float, spent: float, warn_pct: float) -> str:
    if budget <= EPS:
        return "ok"
    pct = spent / budget * 100
    if spent > budget + EPS:
        return "over"
    return "warning" if pct >= warn_pct else "ok"


async def budget_vs_actual(scope: Optional[Dict[str, Any]], year: int,
                           entity_id_for_rules: str = "") -> Dict[str, Any]:
    year = int(year)
    budgets = await list_budgets(scope, year)
    acc_actuals = await _actual_by_account(scope, year)
    cat_actuals = await _actual_by_category(scope, year)
    commitments = await _commitment_map(scope, year)
    rules = await get_rules(entity_id_for_rules) if entity_id_for_rules else \
        {"entity_id": "", **DEFAULT_RULES, "is_default": True}
    warn_pct = float(rules.get("warn_threshold_pct", 85.0) or 85.0)

    rows: List[Dict[str, Any]] = []
    tot = {"budget": 0.0, "committed": 0.0, "actual": 0.0}
    per_dim: Dict[str, Dict[str, float]] = {}
    for b in budgets:
        dim = b.get("dimension") or DIM_ACCOUNT
        key = b.get("key") or b.get("account_code") or ""
        month = int(b.get("month", 0) or 0)
        src = acc_actuals if dim == DIM_ACCOUNT else cat_actuals
        by_month = src.get(key, {})
        cmt = commitments.get((dim, key), {"total": 0.0, "by_month": {}, "docs": []})
        if month > 0:
            actual = _r(by_month.get(month, 0.0))
            committed = _r(cmt["by_month"].get(month, 0.0))
        else:
            actual = _r(sum(by_month.values()))
            committed = _r(cmt["total"])
        budget_amt = _r(b.get("amount", 0))
        spent = round(actual + committed, 2)
        rows.append({
            "id": b["id"], "dimension": dim, "key": key,
            "label": b.get("label") or b.get("account_name") or key,
            "account_code": b.get("account_code", ""), "account_type": b.get("account_type", ""),
            "month": month, "budget": budget_amt, "committed": committed, "actual": actual,
            "spent": spent,
            "remaining": round(budget_amt - spent, 2),
            "variance": round(budget_amt - actual, 2),
            "used_pct": round(actual / budget_amt * 100, 1) if budget_amt > EPS else None,
            "spent_pct": round(spent / budget_amt * 100, 1) if budget_amt > EPS else None,
            "status": _status_of(budget_amt, spent, warn_pct),
            "commitment_docs": cmt["docs"][:8],
            "note": b.get("note", ""),
        })
        tot["budget"] += budget_amt
        tot["committed"] += committed
        tot["actual"] += actual
        d = per_dim.setdefault(dim, {"budget": 0.0, "committed": 0.0, "actual": 0.0, "rows": 0})
        d["budget"] += budget_amt
        d["committed"] += committed
        d["actual"] += actual
        d["rows"] += 1

    rows.sort(key=lambda r: (r["dimension"], r["key"], r["month"]))
    budgeted_keys = {(r["dimension"], r["key"]) for r in rows}
    unbudgeted = [
        {"dimension": dim, "key": key, "committed": _r(v["total"]), "docs": v["docs"][:5]}
        for (dim, key), v in commitments.items() if (dim, key) not in budgeted_keys and v["total"] > EPS
    ]
    unbudgeted.sort(key=lambda r: -r["committed"])
    spent_tot = round(tot["actual"] + tot["committed"], 2)
    for d in per_dim.values():
        for k in ("budget", "committed", "actual"):
            d[k] = _r(d[k])
        d["spent"] = round(d["actual"] + d["committed"], 2)
        d["remaining"] = round(d["budget"] - d["spent"], 2)
    return {
        "year": year,
        "rows": rows,
        "by_dimension": per_dim,
        "unbudgeted_commitments": unbudgeted,
        "alerts": [r for r in rows if r["status"] in ("over", "warning")],
        "rules": rules,
        "totals": {
            "budget": _r(tot["budget"]), "commitment": _r(tot["committed"]),
            "committed": _r(tot["committed"]), "actual": _r(tot["actual"]), "spent": spent_tot,
            "remaining": round(_r(tot["budget"]) - spent_tot, 2),
            "variance": round(_r(tot["budget"]) - _r(tot["actual"]), 2),
            "used_pct": round(tot["actual"] / tot["budget"] * 100, 1) if tot["budget"] > EPS else None,
            "spent_pct": round(spent_tot / tot["budget"] * 100, 1) if tot["budget"] > EPS else None,
            "over_count": sum(1 for r in rows if r["status"] == "over"),
        },
        "generated_at": now_iso(),
    }


# ═══ Pemeriksaan & penegakan (enforcement) ═══════════════════════════════════
async def check_budget(entity_id: str, dimension: str, key: str, amount: float,
                       date: str = "", exclude_po_id: str = "") -> Dict[str, Any]:
    """Cek satu target: sisa anggaran & apakah transaksi sebesar `amount` melampauinya."""
    if dimension not in DIMENSIONS:
        raise ValueError("dimension harus 'account' atau 'category'.")
    ref = (date or now_iso())[:10]
    year, month = _year_of(ref) or int(now_iso()[:4]), _month_of(ref)
    scope = {"entity_id": entity_id}
    rules = await get_rules(entity_id)
    await backfill_dimensions()
    monthly = await db.budgets.find_one({**scope, "year": year, "month": month,
                                         "dimension": dimension, "key": key}, {"_id": 0})
    annual = None if monthly else await db.budgets.find_one(
        {**scope, "year": year, "month": 0, "dimension": dimension, "key": key}, {"_id": 0})
    bdoc = monthly or annual
    src = (await _actual_by_account(scope, year)) if dimension == DIM_ACCOUNT \
        else (await _actual_by_category(scope, year))
    by_month = src.get(key, {})
    cmt = (await _commitment_map(scope, year, exclude_po_id=exclude_po_id)).get(
        (dimension, key), {"total": 0.0, "by_month": {}})
    if monthly:
        actual = _r(by_month.get(month, 0.0))
        committed = _r(cmt["by_month"].get(month, 0.0))
    else:
        actual = _r(sum(by_month.values()))
        committed = _r(cmt["total"])
    _, label = await resolve_key(dimension, key, entity_id)
    amount = _r(amount)
    budget_amt = _r((bdoc or {}).get("amount", 0))
    spent = round(actual + committed, 2)
    available = round(budget_amt - spent, 2)
    after = round(available - amount, 2)
    mode = rules.get("mode", "warn")
    out = {
        "entity_id": entity_id, "dimension": dimension, "key": key, "label": label,
        "year": year, "month": month, "period_basis": "monthly" if monthly else "annual",
        "has_budget": bdoc is not None, "budget": budget_amt, "actual": actual,
        "committed": committed, "spent": spent, "available": available,
        "amount": amount, "available_after": after,
        "over": bool(bdoc) and after < -EPS,
        "over_amount": round(-after, 2) if (bdoc and after < -EPS) else 0.0,
        "used_pct_after": round((spent + amount) / budget_amt * 100, 1) if budget_amt > EPS else None,
        "mode": mode, "unbudgeted_action": rules.get("unbudgeted_action", "allow"),
        "warn_threshold_pct": rules.get("warn_threshold_pct", 85.0),
    }
    if not bdoc:
        act = out["unbudgeted_action"]
        out["blocked"] = mode != "off" and act == "block"
        out["warning"] = (f"Belum ada anggaran {('akun' if dimension == DIM_ACCOUNT else 'kategori')} "
                          f"{key} · {label} untuk tahun {year}.") if (mode != "off" and act in ("warn", "block")) else ""
        return out
    near = out["used_pct_after"] is not None and out["used_pct_after"] >= float(out["warn_threshold_pct"])
    out["blocked"] = mode == "block" and out["over"]
    if mode == "off":
        out["warning"] = ""
    elif out["over"]:
        out["warning"] = (f"Over-budget {label} ({key}): kebutuhan {rupiah(amount)} melebihi sisa "
                          f"{rupiah(available)} sebesar {rupiah(out['over_amount'])} "
                          f"(anggaran {'bulan ' + str(month) if monthly else 'tahunan'} {year}).")
    elif near:
        out["warning"] = (f"Anggaran {label} ({key}) akan terpakai {out['used_pct_after']}% "
                          f"(ambang {out['warn_threshold_pct']}%).")
    else:
        out["warning"] = ""
    return out


async def enforce_po_budget(po: Dict[str, Any], when: str, actor: Dict[str, Any],
                            exclude_po_id: str = "") -> Dict[str, Any]:
    """Terapkan kebijakan anggaran pada PO. Raise ValueError bila mode=block & over-budget."""
    entity_id = po.get("entity_id") or ""
    rules = await get_rules(entity_id)
    result = {"mode": rules.get("mode", "warn"), "when": when, "checked_at": now_iso(),
              "warnings": [], "checks": [], "blocked": False, "skipped": False}
    if rules.get("mode") == "off":
        result["skipped"] = True
        return result
    flag = "enforce_po_create" if when == "po_create" else "enforce_po_approve"
    if not rules.get(flag, True):
        result["skipped"] = True
        return result
    ref_date = po.get("expected_delivery_date") or po.get("created_at") or now_iso()
    for t in po_budget_targets(po):
        if t["amount"] <= EPS:
            continue
        chk = await check_budget(entity_id, t["dimension"], t["key"], t["amount"],
                                 date=ref_date, exclude_po_id=exclude_po_id or po.get("id", ""))
        result["checks"].append(chk)
        if chk.get("warning"):
            result["warnings"].append(chk["warning"])
        if chk.get("blocked"):
            result["blocked"] = True
    if result["blocked"]:
        raise ValueError("Anggaran terlampaui (mode BLOCK): " + " ".join(result["warnings"]))
    _ = actor
    return result
