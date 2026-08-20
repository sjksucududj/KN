"""R6.2 — Fixed Assets & Depresiasi (straight-line) + disposal gain/loss.

Koleksi:
- `fin_fixed_assets`       (prefix `fasset_`, number `FA-#####` per entitas) — master aset.
- `fin_depreciation_entries` (prefix `depe_`) — histori penyusutan per (asset, period).

Prinsip:
- Straight-line: penyusutan bulanan = (harga_perolehan − nilai_residu) / masa_manfaat_bulan.
- Idempotent per (asset_id, period): rerun run_depreciation tidak menduplikasi.
- GL: Dr 6-6000 Beban Penyusutan / Cr 1-2900 Akumulasi Penyusutan (via gl_service.post_depreciation).
- Disposal: hitung book_value & gain/loss (proceeds − book_value), post JE self-balancing
  (via gl_service.post_asset_disposal). Aset → status 'disposed' (append-only, tak dihapus).
"""
from typing import Any, Dict, List, Optional

from db import db
from core_utils import new_id, now_iso, next_doc_number, safe_doc, DEFAULT_ENTITY_ID
from services import gl_service

EPS = 0.01

# Kategori aset → akun GL aset default (boleh dioverride saat create).
CATEGORY_ACCOUNT = {
    "Peralatan & Mesin": "1-2100",
    "Kendaraan": "1-2200",
    "Inventaris & Perabot Kantor": "1-2300",
    "Bangunan": "1-2400",
}
DEFAULT_ASSET_ACC = "1-2100"
ASSET_CATEGORIES = list(CATEGORY_ACCOUNT.keys())


# ── Helpers periode (YYYY-MM) ────────────────────────────────────────────────
def _period_of(date_str: str) -> str:
    return (date_str or now_iso())[:7]


def _add_months(period: str, n: int) -> str:
    y, m = int(period[:4]), int(period[5:7])
    idx = (y * 12 + (m - 1)) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _monthly_amount(cost: float, salvage: float, life: int) -> float:
    depreciable = max(round(float(cost or 0) - float(salvage or 0), 2), 0.0)
    if life <= 0:
        return 0.0
    return round(depreciable / life, 2)


def _recompute(asset: Dict[str, Any]) -> Dict[str, Any]:
    """Derive book_value & status dari accumulated (dipakai saat create/patch)."""
    cost = round(float(asset.get("acquisition_cost", 0) or 0), 2)
    acc = round(float(asset.get("accumulated_depreciation", 0) or 0), 2)
    salvage = round(float(asset.get("salvage_value", 0) or 0), 2)
    depreciable = max(round(cost - salvage, 2), 0.0)
    asset["book_value"] = round(cost - acc, 2)
    if asset.get("status") != "disposed":
        asset["status"] = "fully_depreciated" if acc >= depreciable - EPS and depreciable > 0 else "active"
    return asset


# ── CRUD ─────────────────────────────────────────────────────────────────────
async def list_assets(scope: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    q = dict(scope or {})
    rows = await db.fin_fixed_assets.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return [safe_doc(r) for r in rows]


async def get_asset(asset_id: str) -> Optional[Dict[str, Any]]:
    a = await db.fin_fixed_assets.find_one({"id": asset_id}, {"_id": 0})
    if not a:
        return None
    entries = await db.fin_depreciation_entries.find(
        {"asset_id": asset_id}, {"_id": 0}).sort("period", 1).to_list(2000)
    a["depreciation_entries"] = [safe_doc(e) for e in entries]
    a["schedule"] = depreciation_schedule(a, entries)
    return safe_doc(a)


async def create_asset(payload: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Nama aset wajib diisi.")
    cost = round(float(payload.get("acquisition_cost", 0) or 0), 2)
    if cost <= 0:
        raise ValueError("Harga perolehan harus > 0.")
    life = int(payload.get("useful_life_months", 0) or 0)
    if life <= 0:
        raise ValueError("Masa manfaat (bulan) harus > 0.")
    salvage = round(float(payload.get("salvage_value", 0) or 0), 2)
    if salvage < 0 or salvage >= cost:
        raise ValueError("Nilai residu harus ≥ 0 dan < harga perolehan.")
    category = (payload.get("category") or "Peralatan & Mesin").strip()
    entity_id = payload.get("entity_id") or DEFAULT_ENTITY_ID
    asset_acc = (payload.get("gl_account_asset") or CATEGORY_ACCOUNT.get(category, DEFAULT_ASSET_ACC))
    funding_acc = (payload.get("funding_account") or gl_service.ACC_KAS_BESAR)
    acq_date = (payload.get("acquisition_date") or now_iso())[:10]
    await gl_service.seed_default_coa()
    number = await next_doc_number("fin_fixed_assets", "number", "FA-", entity_id=entity_id)
    doc = {
        "id": new_id("fasset"),
        "number": number,
        "name": name,
        "category": category,
        "acquisition_cost": cost,
        "acquisition_date": acq_date,
        "useful_life_months": life,
        "salvage_value": salvage,
        "method": "straight_line",
        "entity_id": entity_id,
        "gl_account_asset": asset_acc,
        "gl_account_dep_exp": gl_service.ACC_DEP_EXPENSE,
        "gl_account_acc_dep": gl_service.ACC_FA_ACCUM_DEP,
        "funding_account": funding_acc,
        "monthly_depreciation": _monthly_amount(cost, salvage, life),
        "accumulated_depreciation": 0.0,
        "book_value": cost,
        "depreciated_months": 0,
        "last_depreciation_period": "",
        "status": "active",
        "acquisition_je": "",
        "disposal": None,
        "notes": (payload.get("notes") or "").strip(),
        "created_by": actor.get("name", "system"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.fin_fixed_assets.insert_one(dict(doc))
    # Posting perolehan → GL (Dr aset / Cr sumber dana). GL-safe, idempotent.
    je = await gl_service.post_asset_acquisition(
        asset_id=doc["id"], entity_id=entity_id, amount=cost, asset_acc=asset_acc,
        funding_acc=funding_acc, label=f"{number} {name}".strip(), date=acq_date)
    if je:
        doc["acquisition_je"] = je.get("number", "")
        await db.fin_fixed_assets.update_one(
            {"id": doc["id"]}, {"$set": {"acquisition_je": doc["acquisition_je"]}})
    return safe_doc(doc)


async def update_asset(asset_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    a = await db.fin_fixed_assets.find_one({"id": asset_id}, {"_id": 0})
    if not a:
        return None
    if a.get("status") == "disposed":
        raise ValueError("Aset sudah dilepas (disposed) — tidak bisa diubah.")
    allowed = {"name", "category", "notes", "gl_account_asset"}
    upd: Dict[str, Any] = {k: patch[k] for k in allowed if k in patch and patch[k] is not None}
    # Ubah parameter penyusutan hanya bila belum ada penyusutan terposting.
    if a.get("depreciated_months", 0) == 0:
        for k in ("acquisition_cost", "useful_life_months", "salvage_value", "acquisition_date"):
            if patch.get(k) is not None:
                upd[k] = patch[k]
    if not upd:
        return safe_doc(a)
    a.update(upd)
    a["monthly_depreciation"] = _monthly_amount(
        a.get("acquisition_cost", 0), a.get("salvage_value", 0), int(a.get("useful_life_months", 0) or 0))
    _recompute(a)
    a["updated_at"] = now_iso()
    await db.fin_fixed_assets.update_one({"id": asset_id}, {"$set": {k: a[k] for k in a if k != "id"}})
    return safe_doc(a)


# ── Jadwal penyusutan (preview straight-line) ────────────────────────────────
def depreciation_schedule(asset: Dict[str, Any],
                          entries: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    cost = round(float(asset.get("acquisition_cost", 0) or 0), 2)
    salvage = round(float(asset.get("salvage_value", 0) or 0), 2)
    life = int(asset.get("useful_life_months", 0) or 0)
    start = _period_of(asset.get("acquisition_date", ""))
    monthly = _monthly_amount(cost, salvage, life)
    posted = {e["period"]: e for e in (entries or [])}
    out: List[Dict[str, Any]] = []
    acc = 0.0
    depreciable = max(round(cost - salvage, 2), 0.0)
    for i in range(life):
        period = _add_months(start, i)
        remaining = round(depreciable - acc, 2)
        amt = monthly if remaining > monthly + EPS else remaining
        amt = round(max(amt, 0.0), 2)
        acc = round(acc + amt, 2)
        out.append({
            "period": period,
            "amount": amt,
            "accumulated": acc,
            "book_value": round(cost - acc, 2),
            "posted": period in posted,
        })
    return out


# ── Jalankan penyusutan periode (idempotent per asset+period) ────────────────
async def run_depreciation(period: str, actor: Dict[str, Any],
                           asset_id: Optional[str] = None,
                           scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    period = (period or now_iso())[:7]
    q: Dict[str, Any] = dict(scope or {})
    q["status"] = "active"
    if asset_id:
        q["id"] = asset_id
    assets = await db.fin_fixed_assets.find(q, {"_id": 0}).to_list(5000)
    posted: List[Dict[str, Any]] = []
    skipped = 0
    total = 0.0
    for a in assets:
        start = _period_of(a.get("acquisition_date", ""))
        if period < start:  # belum mulai disusutkan
            skipped += 1
            continue
        cost = round(float(a.get("acquisition_cost", 0) or 0), 2)
        salvage = round(float(a.get("salvage_value", 0) or 0), 2)
        life = int(a.get("useful_life_months", 0) or 0)
        acc = round(float(a.get("accumulated_depreciation", 0) or 0), 2)
        depreciable = max(round(cost - salvage, 2), 0.0)
        remaining = round(depreciable - acc, 2)
        if remaining <= EPS or a.get("depreciated_months", 0) >= life:
            skipped += 1
            continue
        # Idempotent: sudah ada entry utk periode ini?
        if await db.fin_depreciation_entries.find_one(
                {"asset_id": a["id"], "period": period}, {"_id": 1}):
            skipped += 1
            continue
        monthly = _monthly_amount(cost, salvage, life)
        amt = monthly if remaining > monthly + EPS else remaining
        amt = round(max(amt, 0.0), 2)
        if amt <= EPS:
            skipped += 1
            continue
        je = await gl_service.post_depreciation(
            asset_id=a["id"], period=period, entity_id=a.get("entity_id", ""),
            amount=amt, asset_label=f"{a.get('number', '')} {a.get('name', '')}".strip(),
            dep_exp_acc=a.get("gl_account_dep_exp", gl_service.ACC_DEP_EXPENSE),
            acc_dep_acc=a.get("gl_account_acc_dep", gl_service.ACC_FA_ACCUM_DEP))
        new_acc = round(acc + amt, 2)
        new_months = int(a.get("depreciated_months", 0)) + 1
        new_book = round(cost - new_acc, 2)
        status = "fully_depreciated" if (new_acc >= depreciable - EPS or new_months >= life) else "active"
        await db.fin_depreciation_entries.insert_one({
            "id": new_id("depe"),
            "asset_id": a["id"], "asset_number": a.get("number", ""),
            "entity_id": a.get("entity_id", ""), "period": period, "amount": amt,
            "accumulated_after": new_acc, "book_value_after": new_book,
            "je_id": (je or {}).get("id", ""), "je_number": (je or {}).get("number", ""),
            "created_by": actor.get("name", "system"), "created_at": now_iso(),
        })
        await db.fin_fixed_assets.update_one({"id": a["id"]}, {"$set": {
            "accumulated_depreciation": new_acc, "book_value": new_book,
            "depreciated_months": new_months, "last_depreciation_period": period,
            "status": status, "updated_at": now_iso()}})
        total = round(total + amt, 2)
        posted.append({"asset_id": a["id"], "number": a.get("number", ""),
                       "name": a.get("name", ""), "amount": amt,
                       "accumulated": new_acc, "book_value": new_book, "status": status})
    return {"period": period, "posted": len(posted), "skipped": skipped,
            "total_amount": total, "assets": posted}


# ── Disposal (gain/loss) ─────────────────────────────────────────────────────
async def dispose_asset(asset_id: str, proceeds: float, actor: Dict[str, Any],
                        date: str = "", note: str = "") -> Dict[str, Any]:
    a = await db.fin_fixed_assets.find_one({"id": asset_id}, {"_id": 0})
    if not a:
        raise ValueError("Aset tidak ditemukan.")
    if a.get("status") == "disposed":
        raise ValueError("Aset sudah dilepas (disposed).")
    proceeds = round(float(proceeds or 0), 2)
    if proceeds < 0:
        raise ValueError("Nilai jual/proceeds tidak boleh negatif.")
    cost = round(float(a.get("acquisition_cost", 0) or 0), 2)
    acc = round(float(a.get("accumulated_depreciation", 0) or 0), 2)
    book_value = round(cost - acc, 2)
    gain_loss = round(proceeds - book_value, 2)
    je = await gl_service.post_asset_disposal(
        asset_id=asset_id, entity_id=a.get("entity_id", ""), acquisition_cost=cost,
        accumulated=acc, proceeds=proceeds, asset_acc=a.get("gl_account_asset", DEFAULT_ASSET_ACC),
        acc_dep_acc=a.get("gl_account_acc_dep", gl_service.ACC_FA_ACCUM_DEP),
        label=f"{a.get('number', '')} {a.get('name', '')}".strip(), date=date)
    disposal = {
        "date": (date or now_iso())[:10], "proceeds": proceeds, "book_value": book_value,
        "gain_loss": gain_loss, "result": "gain" if gain_loss > EPS else ("loss" if gain_loss < -EPS else "impas"),
        "je_id": (je or {}).get("id", ""), "je_number": (je or {}).get("number", ""),
        "note": (note or "").strip(), "by": actor.get("name", "system"), "at": now_iso(),
    }
    await db.fin_fixed_assets.update_one({"id": asset_id}, {"$set": {
        "status": "disposed", "disposal": disposal, "updated_at": now_iso()}})
    a["status"] = "disposed"
    a["disposal"] = disposal
    return safe_doc(a)


# ── Ringkasan KPI ────────────────────────────────────────────────────────────
async def transfer_to_entity(asset_id: str, payload: Dict[str, Any],
                             actor: Dict[str, Any]) -> Dict[str, Any]:
    """FASE E-7 (E7g) — **PINDAH ASET TETAP ANTAR-PT** (keputusan pemilik E7.7).

    Yang dijaga di sini (dan inilah sebabnya bukan sekadar mengganti `entity_id`):

    * **Nilai buku ikut pindah, bukan harga perolehan asli.** Aset lahir kembali di PT
      penerima dengan harga = harga pindah (bawaan: nilai buku) dan **masa manfaat SISA**,
      supaya penyusutannya tidak dimulai dari awal (itu akan mengecilkan beban bertahun-tahun).
    * **Akumulasi penyusutan di PT pengirim dihapus lewat jurnal**, tidak “dibawa” —
      buku pengirim harus bersih dari aset yang sudah bukan miliknya.
    * **Laba/rugi pindah dijurnal DAN dieliminasi** di konsolidasi: kalau dijual di atas
      nilai buku ke PT sendiri, laba itu tidak nyata bagi grup.
    * Aset lama TIDAK dihapus (append-only) → status `transferred` + jejak `transfer`.

    Jurnalnya (dua buku):
        pengirim : Dr Akum.Penyusutan + Dr IC-AR (harga) [+ Dr Rugi] / Cr Aset (perolehan)
                   [+ Cr Laba Pelepasan]
        penerima : Dr Aset (harga) / Cr IC-AP (harga)
    """
    from services import interco_money_service as money

    a = await db.fin_fixed_assets.find_one({"id": asset_id}, {"_id": 0})
    if not a:
        raise ValueError("Aset tetap tidak ditemukan.")
    if a.get("status") == "disposed":
        raise ValueError("Aset sudah dilepas (disposed) — tidak bisa dipindahkan.")
    if (a.get("transfer") or {}).get("to_entity_id"):
        raise ValueError(
            f"Aset ini sudah pernah dipindahkan ke badan usaha lain "
            f"({(a.get('transfer') or {}).get('to_entity_name', '')}) — yang aktif sekarang "
            f"adalah aset penggantinya di badan usaha itu.")
    from_ent = a.get("entity_id") or DEFAULT_ENTITY_ID
    to_ent = (payload.get("to_entity_id") or "").strip()
    snaps = await money.assert_pair(from_ent, to_ent, what="Pindah aset tetap antar-PT")
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise ValueError(
            "Alasan pindah wajib diisi (minimal 5 huruf) — pemindahan aset antar badan "
            "hukum harus bisa dijelaskan ke auditor & pemeriksa pajak.")

    cost = round(float(a.get("acquisition_cost") or 0), 2)
    accum = round(float(a.get("accumulated_depreciation") or 0), 2)
    book = round(cost - accum, 2)
    price = round(float(payload.get("transfer_price") or 0), 2) or book
    if price <= 0:
        raise ValueError("Harga pindah harus lebih dari 0 (atau kosongkan untuk memakai "
                         "nilai buku).")
    gain = round(price - book, 2)
    tdate = (payload.get("transfer_date") or now_iso())[:10]
    life_left = max(int(a.get("useful_life_months") or 0) - int(a.get("depreciated_months") or 0), 1)
    salvage_new = round(min(float(a.get("salvage_value") or 0), max(price - 1, 0.0)), 2)

    # (1) Aset baru di PT penerima — masa manfaat SISA, akumulasi mulai nol.
    new_doc = await create_asset({
        "name": a.get("name", ""), "category": a.get("category", ""),
        "acquisition_cost": price, "acquisition_date": tdate,
        "useful_life_months": life_left, "salvage_value": salvage_new,
        "entity_id": to_ent, "gl_account_asset": a.get("gl_account_asset"),
        "funding_account": gl_service.ACC_IC_AP,   # dibayar lewat utang antar-PT
        "notes": (f"Pindah dari {snaps['a']['name']} ({a.get('number')}) pada {tdate}. "
                  f"Nilai buku saat pindah {book} · harga pindah {price} · "
                  f"masa manfaat sisa {life_left} bulan. Alasan: {reason}"),
    }, actor)

    # (2) Jurnal dua buku (pengirim menghapus aset + akumulasi; penerima mencatat aset).
    lines_from: List[Dict[str, Any]] = []
    if accum > EPS:
        lines_from.append({"account_code": a.get("gl_account_acc_dep", gl_service.ACC_FA_ACCUM_DEP),
                           "debit": accum, "credit": 0.0,
                           "description": f"Hapus akumulasi penyusutan {a.get('number')}"})
    lines_from.append({"account_code": gl_service.ACC_IC_AR, "debit": price, "credit": 0.0,
                       "description": f"Piutang antar-PT pindah aset ke {snaps['b']['name']}"})
    if gain < -EPS:
        lines_from.append({"account_code": gl_service.ACC_FA_LOSS, "debit": round(-gain, 2),
                           "credit": 0.0, "description": f"Rugi pindah aset {a.get('number')}"})
    lines_from.append({"account_code": a.get("gl_account_asset", DEFAULT_ASSET_ACC),
                       "debit": 0.0, "credit": cost,
                       "description": f"Hapus aset {a.get('number')} (harga perolehan)"})
    if gain > EPS:
        lines_from.append({"account_code": gl_service.ACC_FA_GAIN, "debit": 0.0,
                           "credit": gain,
                           "description": f"Laba pindah aset {a.get('number')} (dieliminasi di grup)"})
    await gl_service.post_paired_entry(
        source_type="fixed_asset_transfer", source_id=f"{asset_id}:from",
        entity_id=from_ent, lines=lines_from,
        label=f"Pindah aset {a.get('number')} → {snaps['b']['name']}", date=tdate)
    # Sisi penerima: `create_asset` sudah menjurnal Dr Aset / Cr <funding=IC-AP>.

    # (3) Jejak di aset lama (append-only) + saldo pasangan PT + eliminasi konsolidasi.
    transfer = {
        "from_entity_id": from_ent, "from_entity_name": snaps["a"]["name"],
        "to_entity_id": to_ent, "to_entity_name": snaps["b"]["name"],
        "transfer_date": tdate, "book_value": book, "price": price, "gain": gain,
        "reason": reason, "new_asset_id": new_doc["id"], "new_asset_number": new_doc["number"],
        "useful_life_left_months": life_left,
        "settled": False, "settled_at": "", "cash_txn_ids": [],
        "by": actor.get("name", ""), "at": now_iso(),
    }
    await db.fin_fixed_assets.update_one({"id": asset_id}, {"$set": {
        "status": "transferred", "transfer": transfer,
        "book_value": 0.0, "updated_at": now_iso()}})
    await money.refresh_pair_exposure(from_ent, to_ent)
    await money.sync_non_trade_elimination(
        source_key=f"asset:{asset_id}", pair_id=asset_id,
        from_entity=from_ent, to_entity=to_ent, outstanding=price,
        label=f"pindah aset {a.get('number')} → {new_doc['number']}",
        extra_note=(f"Laba pindah {gain} ikut dieliminasi karena penjualnya PT sendiri."
                    if gain > EPS else ""))
    # Laba pindah antar-PT BUKAN laba grup: dihapus dari laba konsolidasi sekaligus
    # menurunkan nilai aset yang ikut naik hanya karena berpindah tangan di dalam grup.
    # Entri ini TIDAK hilang saat utangnya dibayar — ia hidup selama asetnya dipegang.
    if gain > EPS:
        await money.sync_non_trade_elimination(
            source_key=f"asset_gain:{asset_id}", pair_id=asset_id,
            from_entity=from_ent, to_entity=to_ent, outstanding=gain,
            label=f"laba pindah aset {a.get('number')} → {new_doc['number']}",
            accounts=(gl_service.ACC_FA_GAIN,
                      new_doc.get("gl_account_asset", DEFAULT_ASSET_ACC)),
            kind_note="laba pindah aset (bukan laba grup)",
            extra_note=("Harga pindah di atas nilai buku; selisihnya laba internal, jadi "
                        "dihapus dari laba grup dan dari nilai aset konsolidasi."))
    return {"source": safe_doc({**a, "status": "transferred", "transfer": transfer}),
            "new_asset": new_doc, "gain": gain, "book_value": book, "price": price}


async def settle_transfer(asset_id: str, actor: Dict[str, Any],
                          note: str = "") -> Dict[str, Any]:
    """E7g — bayar utang antar-PT atas aset yang dipindah (uang benar-benar berpindah).

    Dipisah dari pemindahannya karena di lapangan aset sering pindah dulu, uangnya
    menyusul (atau di-netting). Selama belum dibayar, saldonya tampil sebagai
    **saldo non-dagang** di papan pasangan PT — bukan hilang.
    """
    from services import interco_money_service as money

    a = await db.fin_fixed_assets.find_one({"id": asset_id}, {"_id": 0})
    if not a:
        raise ValueError("Aset tetap tidak ditemukan.")
    tr = a.get("transfer") or {}
    if not tr.get("to_entity_id"):
        raise ValueError("Aset ini tidak pernah dipindahkan antar badan usaha.")
    if tr.get("settled"):
        raise ValueError("Pembayaran pindah aset ini sudah dicatat.")
    price = round(float(tr.get("price") or 0), 2)
    from_ent, to_ent = tr["from_entity_id"], tr["to_entity_id"]
    cash = await money.twin_cash(
        out_entity=to_ent, in_entity=from_ent, amount=price,
        category="pindah aset tetap antar-PT",
        description=(f"Pembayaran pindah aset {a.get('number')} ke {tr.get('from_entity_name')}"
                     + (f" — {note}" if note else "")),
        ref_type="fixed_asset_transfer", ref_id=asset_id, actor=actor.get("name", "system"))
    await money.twin_je(
        source_type="fixed_asset_transfer_settlement", pair_id=asset_id, suffix="settle",
        entity_a=to_ent,
        lines_a=money.pair_line(gl_service.ACC_IC_AP, gl_service.ACC_KAS_BESAR, price,
                                f"Bayar pindah aset {a.get('number')}"),
        entity_b=from_ent,
        lines_b=money.pair_line(gl_service.ACC_KAS_BESAR, gl_service.ACC_IC_AR, price,
                                f"Terima pembayaran pindah aset {a.get('number')}"),
        label=f"Pelunasan pindah aset {a.get('number')}")
    await db.fin_fixed_assets.update_one({"id": asset_id}, {"$set": {
        "transfer.settled": True, "transfer.settled_at": now_iso(),
        "transfer.settled_by": actor.get("name", ""),
        "transfer.cash_txn_ids": [cash["out"]["id"], cash["in"]["id"]],
        "updated_at": now_iso()}})
    await money.refresh_pair_exposure(from_ent, to_ent)
    await money.sync_non_trade_elimination(
        source_key=f"asset:{asset_id}", pair_id=asset_id, from_entity=from_ent,
        to_entity=to_ent, outstanding=0.0, label=f"pindah aset {a.get('number')}")
    return {"asset_id": asset_id, "paid": price,
            "cash": [cash["out"]["number"], cash["in"]["number"]]}


async def summary(scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rows = await db.fin_fixed_assets.find(dict(scope or {}), {"_id": 0}).to_list(5000)
    # FASE E-7 (E7g) — aset yang SUDAH PINDAH ke badan usaha lain BUKAN milik badan usaha
    # ini lagi. Dulu hanya `disposed` yang dikeluarkan, sehingga buku penjual mengaku
    # masih memegang Rp 420 jt aset yang fisik & haknya sudah berpindah (dan nilai buku
    # barisnya sudah 0). Untuk urusan angka, mengaku punya yang tidak dipunya itu cacat.
    gone = {"disposed", "transferred"}
    owned = [r for r in rows if r.get("status") not in gone]
    gross = round(sum(float(r.get("acquisition_cost", 0) or 0) for r in owned), 2)
    accum = round(sum(float(r.get("accumulated_depreciation", 0) or 0) for r in owned), 2)
    net = round(gross - accum, 2)
    disposed = [r for r in rows if r.get("status") == "disposed"]
    transferred = [r for r in rows if r.get("status") == "transferred"]
    disposal_gain = round(sum(float((r.get("disposal") or {}).get("gain_loss", 0) or 0) for r in disposed), 2)
    # Nilai buku saat berpindah + apakah pembayarannya sudah dicatat — supaya layar bisa
    # menagih "utang antar-PT atas aset yang belum dibayar" tanpa menghitung ulang.
    tr_book = round(sum(float((r.get("transfer") or {}).get("book_value", 0) or 0) for r in transferred), 2)
    tr_unsettled = [r for r in transferred if not (r.get("transfer") or {}).get("settled")]
    return {
        "count": len(rows), "active": len(owned),
        "fully_depreciated": sum(1 for r in owned if r.get("status") == "fully_depreciated"),
        "disposed": len(disposed),
        "transferred": len(transferred),
        "transferred_book_value": tr_book,
        "transferred_unsettled": len(tr_unsettled),
        "gross_cost": gross, "accumulated_depreciation": accum, "net_book_value": net,
        "disposal_gain_loss": disposal_gain, "generated_at": now_iso(),
    }
