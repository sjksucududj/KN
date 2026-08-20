"""FINANCE — Konsolidasi Grup + Eliminasi Intercompany.

Menghasilkan matriks Per-PT + Eliminasi + Konsolidasi untuk Laba-Rugi (tahun) &
Neraca (as_of). Eliminasi = adjustment level grup (koleksi
`intercompany_eliminations`), TIDAK memodifikasi journal_entries per-PT
(audit trail via dokumen eliminasi). Mendukung eliminasi manual + auto-deteksi
kandidat akun intercompany.

Prinsip keseimbangan: entri eliminasi harus balanced (Σdebit=Σkredit) sehingga
`assets_elim = liabilities_elim + equity_total_elim` dan Neraca konsolidasi tetap
seimbang. equity_total_elim = equity_langsung + net_income_elim.
"""
from typing import Any, Dict, List, Optional, Tuple

from db import db
from core_utils import new_id, now_iso, rupiah, safe_doc
from services import financial_statement_service as fs

IC_KEYWORDS = ["intercompany", "inter-co", "interco", "antar entitas",
               "antar-entitas", "antar-pt", "antar pt", "antarperusahaan",
               "antar perusahaan", "ic-", "i/c"]


def _blank() -> Dict[str, float]:
    return {"revenue": 0.0, "cogs": 0.0, "opex": 0.0,
            "assets": 0.0, "liabilities": 0.0, "equity": 0.0}


def _classify_line(acc_type: str, code: str, debit: float, credit: float) -> Dict[str, float]:
    """Kontribusi satu baris jurnal ke metrik (orientasi saldo normal)."""
    d = round(float(debit or 0) - float(credit or 0), 2)  # debit_net
    c = round(float(credit or 0) - float(debit or 0), 2)   # credit_net
    m = _blank()
    if acc_type == "income":
        m["revenue"] += c
    elif acc_type == "expense":
        if code.startswith("5"):
            m["cogs"] += d
        else:
            m["opex"] += d
    elif acc_type == "asset":
        m["assets"] += d
    elif acc_type == "liability":
        m["liabilities"] += c
    elif acc_type == "equity":
        m["equity"] += c
    return m


def _pnl_derive(m: Dict[str, float]) -> Dict[str, float]:
    revenue = round(m.get("revenue", 0), 2)
    cogs = round(m.get("cogs", 0), 2)
    opex = round(m.get("opex", 0), 2)
    expense = round(cogs + opex, 2)
    return {
        "revenue": revenue, "cogs": cogs, "opex": opex, "expense": expense,
        "gross_profit": round(revenue - cogs, 2),
        "net_income": round(revenue - expense, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  PER-PT & SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

async def _entity_row(eid: str, ent: Dict[str, Any], year: int, as_of: str) -> Dict[str, Any]:
    scope = {"entity_id": eid}
    pnl = await fs.income_statement(start=f"{year}-01-01", end=f"{year}-12-31", scope=scope)
    bs = await fs.balance_sheet(as_of=as_of, scope=scope)
    revenue = float(pnl.get("revenue_total", 0) or 0)
    cogs = float(pnl.get("cogs_total", 0) or 0)
    opex = float(pnl.get("opex_total", 0) or 0)
    return {
        "entity_id": eid,
        "entity_name": ent.get("legal_name") or ent.get("short_name") or eid,
        "short_name": ent.get("short_name") or ent.get("doc_prefix") or eid,
        "revenue": round(revenue, 2),
        "cogs": round(cogs, 2),
        "opex": round(opex, 2),
        "expense": round(cogs + opex, 2),
        "gross_profit": round(revenue - cogs, 2),
        "net_income": float(pnl.get("net_income", 0) or 0),
        "assets": float(bs.get("assets_total", 0) or 0),
        "liabilities": float(bs.get("liabilities_total", 0) or 0),
        "equity": float(bs.get("equity_total", 0) or 0),
    }


async def _applicable_eliminations(year: int, as_of: str):
    """Kembalikan (pl_elims, bs_elims) sesuai filter tanggal efektif."""
    all_elims = await db.intercompany_eliminations.find({}, {"_id": 0}).to_list(2000)
    y0, y1 = f"{year}-01-01", f"{year}-12-31"
    pl = [e for e in all_elims if y0 <= (e.get("effective_date") or "")[:10] <= y1]
    bs = [e for e in all_elims if (e.get("effective_date") or "")[:10] <= as_of]
    return pl, bs, all_elims


def _aggregate_impacts(elims: List[Dict[str, Any]]) -> Dict[str, float]:
    total = _blank()
    for e in elims:
        imp = e.get("impact") or _blank()
        for k in total:
            total[k] += float(imp.get(k, 0) or 0)
    return {k: round(v, 2) for k, v in total.items()}


async def summary(entity_ids: List[str], year: int, as_of: str) -> Dict[str, Any]:
    # M-3: Sinkronisasi otomatis eliminasi dari intercompany_pair_id (idempotent).
    # Setiap kali laporan konsolidasi dibuka, pair baru yang belum ter-cover akan
    # otomatis mendapat entri eliminasi. Hasilnya masuk ke `intercompany_eliminations`.
    try:
        await sync_ic_eliminations_from_pairs(as_of=as_of)
    except Exception:
        # Jangan gagalkan konsolidasi hanya karena sync gagal (mis. race). Log ringan.
        pass

    ents = {e["id"]: e for e in await db.business_entities.find(
        {"id": {"$in": list(entity_ids)}}, {"_id": 0}).to_list(200)}

    rows: List[Dict[str, Any]] = []
    for eid in entity_ids:
        e = ents.get(eid, {})
        if e.get("is_group"):
            continue
        rows.append(await _entity_row(eid, e, year, as_of))
    rows.sort(key=lambda r: r["revenue"], reverse=True)

    sum_fields = ["revenue", "cogs", "opex", "expense", "gross_profit",
                  "net_income", "assets", "liabilities", "equity"]
    gross = {f: round(sum(float(r.get(f, 0) or 0) for r in rows), 2) for f in sum_fields}

    pl_elims, bs_elims, _all = await _applicable_eliminations(year, as_of)
    pl_agg = _aggregate_impacts(pl_elims)
    bs_agg = _aggregate_impacts(bs_elims)
    pl_elim = _pnl_derive(pl_agg)
    # net income effect (dari baris P&L pada eliminasi BS) → mempengaruhi ekuitas
    bs_ni = _pnl_derive(bs_agg)["net_income"]
    equity_total_elim = round(bs_agg.get("equity", 0) + bs_ni, 2)
    elimination = {
        "revenue": pl_elim["revenue"], "cogs": pl_elim["cogs"], "opex": pl_elim["opex"],
        "expense": pl_elim["expense"], "gross_profit": pl_elim["gross_profit"],
        "net_income": pl_elim["net_income"],
        "assets": round(bs_agg.get("assets", 0), 2),
        "liabilities": round(bs_agg.get("liabilities", 0), 2),
        "equity": equity_total_elim,
    }

    consolidated = {
        "revenue": round(gross["revenue"] + elimination["revenue"], 2),
        "cogs": round(gross["cogs"] + elimination["cogs"], 2),
        "opex": round(gross["opex"] + elimination["opex"], 2),
        "assets": round(gross["assets"] + elimination["assets"], 2),
        "liabilities": round(gross["liabilities"] + elimination["liabilities"], 2),
        "equity": round(gross["equity"] + elimination["equity"], 2),
    }
    consolidated["expense"] = round(consolidated["cogs"] + consolidated["opex"], 2)
    consolidated["gross_profit"] = round(consolidated["revenue"] - consolidated["cogs"], 2)
    consolidated["net_income"] = round(consolidated["revenue"] - consolidated["expense"], 2)

    balanced = abs(consolidated["assets"] - (consolidated["liabilities"] + consolidated["equity"])) < 1.0

    return {
        "year": year,
        "as_of": as_of,
        "entities": rows,
        "gross": gross,
        "elimination": elimination,
        "consolidated": consolidated,
        "eliminations_count": len(_all),
        "eliminations_pl_count": len(pl_elims),
        "eliminations_bs_count": len(bs_elims),
        "eliminations_auto_count": sum(1 for e in _all if e.get("auto_generated")),
        "balanced": balanced,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  ELIMINATIONS CRUD
# ═══════════════════════════════════════════════════════════════════════════

async def _accounts_lookup() -> Dict[str, Dict[str, Any]]:
    accs = await db.gl_accounts.find({}, {"_id": 0, "code": 1, "name": 1, "type": 1}).to_list(2000)
    return {a["code"]: a for a in accs}


async def _compute_impact(lines: List[Dict[str, Any]], amap: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    total = _blank()
    for ln in lines:
        acc = amap.get(ln.get("account_code"), {})
        contrib = _classify_line(acc.get("type", ""), ln.get("account_code", ""),
                                 ln.get("debit", 0), ln.get("credit", 0))
        for k in total:
            total[k] += contrib[k]
    return {k: round(v, 2) for k, v in total.items()}


async def list_eliminations() -> List[Dict[str, Any]]:
    return await db.intercompany_eliminations.find({}, {"_id": 0}).sort("effective_date", -1).to_list(1000)


async def create_elimination(data: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    amap = await _accounts_lookup()
    raw_lines = data.get("lines") or []
    lines: List[Dict[str, Any]] = []
    total_d = total_c = 0.0
    for ln in raw_lines:
        code = (ln.get("account_code") or "").strip()
        if not code:
            continue
        debit = round(float(ln.get("debit") or 0), 2)
        credit = round(float(ln.get("credit") or 0), 2)
        if abs(debit) < 0.005 and abs(credit) < 0.005:
            continue
        lines.append({
            "account_code": code,
            "account_name": amap.get(code, {}).get("name", code),
            "debit": debit, "credit": credit,
            "description": (ln.get("description") or "").strip(),
        })
        total_d += debit
        total_c += credit
    if not lines:
        raise ValueError("Minimal satu baris eliminasi diperlukan.")
    balanced = abs(round(total_d - total_c, 2)) < 0.5
    impact = await _compute_impact(lines, amap)
    doc = {
        "id": new_id("icelim"),
        "name": (data.get("name") or "Eliminasi Intercompany").strip(),
        "entity_from": data.get("entity_from") or None,
        "entity_to": data.get("entity_to") or None,
        "effective_date": (data.get("effective_date") or now_iso())[:10],
        "note": (data.get("note") or "").strip(),
        "lines": lines,
        "total_debit": round(total_d, 2),
        "total_credit": round(total_c, 2),
        "balanced": balanced,
        "impact": impact,
        "created_by": actor.get("name", "system"),
        "created_by_id": actor.get("id"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.intercompany_eliminations.insert_one(dict(doc))
    return safe_doc(doc)


async def delete_elimination(elim_id: str) -> bool:
    r = await db.intercompany_eliminations.delete_one({"id": elim_id})
    return r.deleted_count > 0


# ═══════════════════════════════════════════════════════════════════════════
#  AUTO-ELIMINATION FROM INTERCOMPANY_PAIR_ID (M-3)
# ═══════════════════════════════════════════════════════════════════════════
# Setiap inter-company transfer meng-post 2 JE (source & dest) yang dilink via
# `intercompany_pair_id`. Konsolidasi grup harus meng-eliminasi:
#   Cr 1-1250 IC-AR (source side) DAN Dr 2-1250 IC-AP (dest side)
# supaya piutang↔utang antar-PT tidak double-counted di neraca konsolidasi.
# Fungsi di bawah menghasilkan/memelihara entri `intercompany_eliminations`
# secara idempotent berdasarkan pair_id. User boleh delete manual bila perlu.

async def _pair_totals(as_of: str = "") -> List[Dict[str, Any]]:
    """Agregat total nilai per intercompany_pair_id dari journal_entries (posted).

    Return list of {pair_id, total, source_entity_id, dest_entity_id,
    effective_date, source_je_ids, dest_je_ids}.
    """
    q: Dict[str, Any] = {
        "intercompany_pair_id": {"$exists": True, "$ne": None},
        "status": {"$ne": "void"},
    }
    if as_of:
        q["date"] = {"$lte": f"{as_of}T23:59:59+00:00"}
    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(20000)
    pairs: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        pid = e.get("intercompany_pair_id")
        if not pid:
            continue
        p = pairs.setdefault(pid, {
            "pair_id": pid, "total": 0.0,
            "source_entity_id": None, "dest_entity_id": None,
            "effective_date": e.get("date", "")[:10],
            "source_je_ids": [], "dest_je_ids": [],
        })
        stype_id = str(e.get("source_id") or "")
        is_src = stype_id.endswith(":src")
        is_dst = stype_id.endswith(":dst")
        if is_src:
            p["source_entity_id"] = e.get("entity_id")
            p["source_je_ids"].append(e.get("id"))
            p["total"] = max(p["total"], float(e.get("total_debit", 0) or 0))
        elif is_dst:
            p["dest_entity_id"] = e.get("entity_id")
            p["dest_je_ids"].append(e.get("id"))
        # tanggal paling awal jadi effective_date
        edate = (e.get("date") or "")[:10]
        if edate and (not p["effective_date"] or edate < p["effective_date"]):
            p["effective_date"] = edate
    return [p for p in pairs.values()
            if p["source_entity_id"] and p["dest_entity_id"] and p["total"] > 0]


async def sync_ic_eliminations_from_pairs(as_of: str = "") -> Dict[str, Any]:
    """Idempotent: buat entri eliminasi otomatis untuk setiap intercompany_pair_id
    yang belum tercatat di `intercompany_eliminations`.

    Logika eliminasi (nol-kan piutang↔utang antar-PT di neraca konsolidasi):
      Dr 2-1250 IC-AP  <total>   (offset saldo IC-AP di dest)
      Cr 1-1250 IC-AR  <total>   (offset saldo IC-AR di source)
    Impact: assets -total, liabilities -total → equity tidak berubah, neraca tetap
    seimbang di level grup.
    """
    from services.gl_service import ACC_IC_AR, ACC_IC_AP
    pairs = await _pair_totals(as_of=as_of)
    amap = await _accounts_lookup()

    existing = await db.intercompany_eliminations.find(
        {"source_pair_id": {"$exists": True, "$ne": None}},
        {"_id": 0, "source_pair_id": 1}).to_list(5000)
    covered = {e["source_pair_id"] for e in existing}

    created: List[Dict[str, Any]] = []
    skipped = 0
    for p in pairs:
        if p["pair_id"] in covered:
            skipped += 1
            continue
        total = round(float(p["total"]), 2)
        lines = [
            {"account_code": ACC_IC_AP, "account_name": amap.get(ACC_IC_AP, {}).get("name", ACC_IC_AP),
             "debit": total, "credit": 0.0,
             "description": f"Eliminasi IC-AP (pair {p['pair_id']})"},
            {"account_code": ACC_IC_AR, "account_name": amap.get(ACC_IC_AR, {}).get("name", ACC_IC_AR),
             "debit": 0.0, "credit": total,
             "description": f"Eliminasi IC-AR (pair {p['pair_id']})"},
        ]
        impact = await _compute_impact(lines, amap)
        doc = {
            "id": new_id("icelim"),
            "name": f"Auto: Eliminasi IC transfer {p['pair_id']}",
            "entity_from": p["source_entity_id"],
            "entity_to": p["dest_entity_id"],
            "effective_date": p["effective_date"] or now_iso()[:10],
            "note": "Auto-generated dari intercompany transfer JE pair. "
                    "Menghapus dobel-hitung piutang↔utang antar-PT di neraca konsolidasi.",
            "lines": lines,
            "total_debit": total,
            "total_credit": total,
            "balanced": True,
            "impact": impact,
            "auto_generated": True,
            "source_pair_id": p["pair_id"],
            "source_je_ids": p["source_je_ids"] + p["dest_je_ids"],
            "created_by": "system",
            "created_by_id": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        await db.intercompany_eliminations.insert_one(dict(doc))
        created.append(safe_doc(doc))
    return {
        "created": len(created), "skipped_existing": skipped,
        "pairs_seen": len(pairs), "entries": created,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  AUTO-DETECT INTERCOMPANY CANDIDATES
# ═══════════════════════════════════════════════════════════════════════════

def _is_ic_account(acc: Dict[str, Any]) -> bool:
    hay = f"{acc.get('code','')} {acc.get('name','')}".lower()
    return any(kw in hay for kw in IC_KEYWORDS)


async def ic_candidates(entity_ids: List[str], as_of: str) -> Dict[str, Any]:
    amap = await _accounts_lookup()
    ic_accounts = {code: a for code, a in amap.items() if _is_ic_account(a)}
    ents = {e["id"]: e for e in await db.business_entities.find(
        {"id": {"$in": list(entity_ids)}}, {"_id": 0}).to_list(200)}

    # agregat saldo per entitas per akun IC
    date_filter = {"$lte": fs._day_end(as_of)} if as_of else None
    candidates: List[Dict[str, Any]] = []
    suggested_lines: List[Dict[str, Any]] = []

    per_account: Dict[str, Dict[str, float]] = {code: {} for code in ic_accounts}
    for eid in entity_ids:
        e = ents.get(eid, {})
        if e.get("is_group"):
            continue
        agg = await fs._aggregate({"entity_id": eid}, date_filter, include_closing=True)
        for code in ic_accounts:
            v = agg.get(code)
            if not v:
                continue
            net = round(v["debit"] - v["credit"], 2)  # debit_net
            if abs(net) > 0.005:
                per_account[code][eid] = net

    for code, acc in ic_accounts.items():
        by_ent = per_account.get(code, {})
        if not by_ent:
            continue
        total_net = round(sum(by_ent.values()), 2)
        per_entity = [{
            "entity_id": eid,
            "short_name": (ents.get(eid, {}) or {}).get("short_name", eid),
            "balance": bal,
        } for eid, bal in by_ent.items()]
        candidates.append({
            "account_code": code,
            "account_name": acc.get("name", code),
            "type": acc.get("type", ""),
            "per_entity": per_entity,
            "total_net": total_net,
        })
        # saran baris eliminasi: balikkan saldo total (debit_net>0 → kredit; sebaliknya)
        if abs(total_net) > 0.005:
            if total_net > 0:
                suggested_lines.append({"account_code": code, "account_name": acc.get("name", code),
                                        "debit": 0.0, "credit": abs(total_net),
                                        "description": f"Eliminasi {acc.get('name', code)}"})
            else:
                suggested_lines.append({"account_code": code, "account_name": acc.get("name", code),
                                        "debit": abs(total_net), "credit": 0.0,
                                        "description": f"Eliminasi {acc.get('name', code)}"})

    return {
        "as_of": as_of,
        "keywords": IC_KEYWORDS,
        "candidates": candidates,
        "suggested_lines": suggested_lines,
        "detected_accounts": len(ic_accounts),
    }


# ═══════════════════════════════════════════════════════════════════════════
# FASE G-6 — Eliminasi TRANSAKSI ANTAR-PT (jual-beli internal)
# ═══════════════════════════════════════════════════════════════════════════
async def _g6_pair_totals(as_of: str = "", pair_id: str = "") -> List[Dict[str, Any]]:
    """Kumpulkan pair G-6 dari `interco_transactions`.

    Untuk tiap pair (dokumen kembar), kembalikan:
      * seller_entity_id, buyer_entity_id
      * subtotal, tax_amount, grand_total
      * cost (agregat WAC × qty di sisi penjual, diambil dari JE `{pair}:cogs`)
      * status (untuk menentukan bagian yang masih di persediaan pembeli)
    """
    q: Dict[str, Any] = {"role": "seller"}
    if as_of:
        q["doc_date"] = {"$lte": as_of}
    if pair_id:
        q["pair_id"] = pair_id
    seller_docs = await db.interco_transactions.find(q, {"_id": 0}).to_list(20000)
    pairs: List[Dict[str, Any]] = []
    for d in seller_docs:
        if d.get("status") in ("draft", "cancelled"):
            continue
        # Ambil biaya HPP dari JE :cogs (baru ada SESUDAH barang keluar gudang)
        cogs_je = await db.journal_entries.find_one(
            {"source_type": "interco_transaction",
             "source_id": f"{d['pair_id']}:cogs",
             "status": "posted"},
            {"_id": 0, "total_debit": 1})
        cost = float((cogs_je or {}).get("total_debit") or 0)
        # Barangnya sudah diterima pembeli? Menentukan DI AKUN MANA margin bersarang:
        # sudah diterima → `1-1300 Persediaan`; masih jalan → `1-1310 Dalam Perjalanan`.
        receipt_je = await db.journal_entries.find_one(
            {"source_type": "interco_transaction",
             "source_id": f"{d['pair_id']}:receipt",
             "status": "posted"},
            {"_id": 0, "id": 1})
        # FASE G-6b — bagian yang sudah DIRETUR bukan transaksi intra-grup lagi
        # (barangnya kembali ke penjual), jadi nilainya dikeluarkan dari eliminasi.
        ret_sub = float(d.get("returned_subtotal") or 0)
        ret_cost = float(d.get("returned_cost") or 0)
        # FASE G-6b — rasio barang yang MASIH ada di gudang pembeli (belum terjual
        # ke pihak luar). Dari data roll nyata, bukan asumsi.
        from services import interco_margin as _margin
        u = await _margin.unsold_ratio(d["pair_id"], seller=d,
                                       delivered=bool(receipt_je))
        # FASE E-7 (E7.3) — kalau JE HPP belum ada, angka HPP yang dieliminasi memang 0.
        # Itu BUKAN "HPP nol": itu "HPP belum diketahui". Entri eliminasi wajib
        # membawa labelnya + taksiran WAC sebagai keterangan, supaya orang yang
        # membaca laporan konsolidasi tidak menyimpulkan margin grup 100%.
        disc = await _margin.cost_disclosure(
            d, cost, round(float(d.get("subtotal") or 0) - ret_sub, 2))
        pairs.append({
            "pair_id": d["pair_id"],
            "seller_entity_id": d["seller_entity_id"],
            "buyer_entity_id": d["buyer_entity_id"],
            "seller_number": d.get("number", ""),
            "subtotal": round(float(d.get("subtotal") or 0) - ret_sub, 2),
            "tax_amount": float(d.get("tax_amount") or 0),
            "grand_total": float(d.get("grand_total") or 0),
            "settled_amount": float(d.get("settled_amount") or 0),
            "returned_amount": float(d.get("returned_amount") or 0),
            "cost": round(cost - ret_cost, 2),
            "unsold_ratio": u["ratio"],
            "qty_base": u["qty_base"],
            "qty_remaining": u["qty_remaining"],
            "delivered": bool(receipt_je),
            "status": d.get("status"),
            "effective_date": (d.get("doc_date") or d.get("created_at") or "")[:10],
            "cost_estimated": bool(disc.get("cost_estimated")),
            "cost_basis": disc.get("cost_basis", ""),
            "cost_estimate": float(disc.get("cost_estimate") or 0),
            "cost_estimate_reason": disc.get("cost_estimate_reason", ""),
        })
    return pairs


def _g6_elim_lines(p: Dict[str, Any], amap: Dict[str, Any],
                   acc: Dict[str, str]) -> List[Dict[str, Any]]:
    """Rakit baris eliminasi untuk SATU pair G-6 (selalu seimbang).

    Dipisah dari `sync_g6_ic_eliminations` supaya angka eliminasi bisa
    **dihitung ulang** (bukan hanya dibuat sekali) ketika transaksinya
    berubah — mis. setelah settlement, IC-AR/IC-AP yang tersisa mengecil.
    Tanpa perhitungan ulang, entri eliminasi lama akan menghapus saldo yang
    sudah tidak ada lagi (INV-IC-03 memerah).
    """
    subtotal = round(float(p["subtotal"]), 2)
    cost = round(float(p["cost"]), 2)
    margin = round(subtotal - cost, 2)          # bisa negatif (jual di bawah HPP)
    outstanding = round(float(p["grand_total"]) - float(p["settled_amount"])
                        - float(p.get("returned_amount") or 0), 2)
    label = p.get("seller_number") or p["pair_id"]
    # FASE G-6b — hanya margin yang MASIH menempel di persediaan pembeli yang
    # dieliminasi. Begitu pembeli menjual barangnya ke pihak luar, laba itu NYATA
    # bagi grup dan tidak boleh dihapus lagi (kalau tetap dihapus, laba grup
    # dilaporkan terlalu kecil). Identitas yang dipakai (u = rasio belum terjual):
    #     Dr Pendapatan S · Cr HPP (C·u + S·(1−u)) · Cr Persediaan (M·u)
    # Saat u = 1 rumus ini identik dengan perilaku lama (Cr HPP C, Cr Persediaan M).
    u = float(p.get("unsold_ratio", 1.0) or 0.0)
    u = max(0.0, min(1.0, u))
    s_ratio = round(1.0 - u, 6)
    margin_unrealized = round(margin * u, 2)
    # Cr HPP = C·u + S·(1−u) — ditulis sebagai `S − M·u` supaya pembulatan tidak
    # pernah membuat entri jadi tidak seimbang (Dr == Cr persis).
    cogs_elim = round(subtotal - margin_unrealized, 2)
    # Margin bersarang di akun yang benar: begitu barang diterima ia ada di
    # `1-1300 Persediaan`; selama masih jalan ia ada di `1-1310 Dalam Perjalanan`.
    inv_acc = acc["inventory"] if p.get("delivered") else acc["inventory_transit"]
    lines: List[Dict[str, Any]] = []

    def _nm(code: str) -> str:
        return amap.get(code, {}).get("name", code)

    # A. Pendapatan + HPP intra-grup + unrealized profit di persediaan pembeli
    if subtotal > 0.005:
        lines.append({
            "account_code": acc["revenue"], "account_name": _nm(acc["revenue"]),
            "debit": subtotal, "credit": 0.0,
            "description": f"Eliminasi pendapatan antar-PT {label}",
        })
    if cogs_elim > 0.005:
        lines.append({
            "account_code": acc["cogs"], "account_name": _nm(acc["cogs"]),
            "debit": 0.0, "credit": cogs_elim,
            "description": (f"Eliminasi HPP antar-PT {label}"
                            + (f" (termasuk {int(round(s_ratio * 100))}% yang sudah "
                               f"terjual ke pihak luar)" if s_ratio > 0.005 else "")),
        })
    # Selisih ditutup di Persediaan: margin>0 → Cr (turunkan nilai buku pembeli
    # ke HPP asli penjual); margin<0 → Dr (jual di bawah HPP → naikkan kembali).
    if margin_unrealized > 0.005:
        lines.append({
            "account_code": inv_acc, "account_name": _nm(inv_acc),
            "debit": 0.0, "credit": margin_unrealized,
            "description": (f"Unrealized profit antar-PT {label} "
                            f"(margin belum direalisasi ke pihak luar"
                            + (f" · {int(round(u * 100))}% barang masih di gudang pembeli)"
                               if s_ratio > 0.005 else ")")),
        })
    elif margin_unrealized < -0.005:
        lines.append({
            "account_code": inv_acc, "account_name": _nm(inv_acc),
            "debit": abs(margin_unrealized), "credit": 0.0,
            "description": (f"Koreksi nilai persediaan antar-PT {label} "
                            f"(jual di bawah HPP — balikkan ke nilai asli)"),
        })
    # B. IC-AR ↔ IC-AP untuk sisa yang belum di-settle
    if outstanding > 0.005:
        lines.append({
            "account_code": acc["ic_ap"], "account_name": _nm(acc["ic_ap"]),
            "debit": outstanding, "credit": 0.0,
            "description": f"Eliminasi IC-AP {label}",
        })
        lines.append({
            "account_code": acc["ic_ar"], "account_name": _nm(acc["ic_ar"]),
            "debit": 0.0, "credit": outstanding,
            "description": f"Eliminasi IC-AR {label}",
        })
    return lines


def _lines_differ(old: Any, new: List[Dict[str, Any]]) -> bool:
    """Bandingkan baris eliminasi (akun + nilai) — abaikan urutan & deskripsi."""
    def key(rows: Any) -> List[Tuple[str, float, float]]:
        return sorted((str(r.get("account_code")),
                       round(float(r.get("debit") or 0), 2),
                       round(float(r.get("credit") or 0), 2)) for r in (rows or []))
    return key(old) != key(new)


async def sync_g6_ic_eliminations(as_of: str = "", pair_id: str = "") -> Dict[str, Any]:
    """FASE G-6 (US7) — Eliminasi konsolidasi untuk transaksi antar-PT.

    Untuk setiap pair G-6 diterbitkan SATU entri eliminasi berimbang yang:

      1. **Mengeliminasi Pendapatan & HPP intra-grup** (transaksi tidak pernah
         menghasilkan laba bagi grup):
            Dr 4-1000 Pendapatan        subtotal
              Cr 5-1000 HPP               cost
              Cr 1-1300 Persediaan        (subtotal - cost)   ← *unrealized profit*
                                                              (margin yang masih
                                                               "berdiam" di
                                                               persediaan pembeli)

      2. **Mengeliminasi IC-AR ↔ IC-AP** (piutang & utang antar-PT saling hapus):
            Dr 2-1250 IC-AP             outstanding
              Cr 1-1250 IC-AR             outstanding

    Idempotent lewat `source_g6_pair_id`, tetapi **bukan sekadar "sudah ada →
    lewati"**: bila angka transaksinya berubah (mis. setelah settlement, sisa
    IC-AR/IC-AP mengecil) entri auto akan **diperbarui**; bila pair-nya
    dibatalkan/kembali draf, entri auto akan **dihapus**. Dengan begitu laporan
    konsolidasi tidak pernah menghapus saldo yang sudah tidak ada (INV-IC-03).

    Dipanggil otomatis dari `interco_service` saat transaksi dikonfirmasi /
    dilunasi / dibatalkan, dan bisa dipanggil manual dari layar Konsolidasi Grup
    (tombol "Sinkron Antar-PT (G-6)") untuk data lama.
    """
    from services.gl_service import (
        ACC_IC_AR, ACC_IC_AP, ACC_PERSEDIAAN, ACC_PERSEDIAAN_TRANSIT,
        ACC_PENDAPATAN, ACC_HPP,
    )
    acc = {"revenue": ACC_PENDAPATAN, "cogs": ACC_HPP, "inventory": ACC_PERSEDIAAN,
           "inventory_transit": ACC_PERSEDIAAN_TRANSIT,
           "ic_ar": ACC_IC_AR, "ic_ap": ACC_IC_AP}
    pairs = await _g6_pair_totals(as_of=as_of, pair_id=pair_id)
    amap = await _accounts_lookup()

    q_exist: Dict[str, Any] = {"source_g6_pair_id": {"$exists": True, "$ne": None}}
    if pair_id:
        q_exist["source_g6_pair_id"] = pair_id
    existing = await db.intercompany_eliminations.find(q_exist, {"_id": 0}).to_list(5000)
    by_pair = {e["source_g6_pair_id"]: e for e in existing}
    qualifying = {p["pair_id"] for p in pairs}

    created: List[Dict[str, Any]] = []
    updated: List[Dict[str, Any]] = []
    removed = 0
    skipped = 0
    for p in pairs:
        lines = _g6_elim_lines(p, amap, acc)
        prev = by_pair.get(p["pair_id"])
        if not lines:
            # Tidak ada apa pun untuk dieliminasi (nilai nol) → jangan simpan entri kosong.
            if prev:
                await db.intercompany_eliminations.delete_one({"id": prev["id"]})
                removed += 1
            continue
        total_debit = round(sum(l["debit"] for l in lines), 2)
        total_credit = round(sum(l["credit"] for l in lines), 2)
        payload: Dict[str, Any] = {
            "name": f"Auto G-6: Eliminasi antar-PT {p['seller_number'] or p['pair_id']}",
            "entity_from": p["seller_entity_id"],
            "entity_to": p["buyer_entity_id"],
            "effective_date": p["effective_date"] or now_iso()[:10],
            "note": (
                "Auto-generated dari transaksi antar-PT (FASE G-6). "
                "Mengeliminasi pendapatan+HPP intra-grup, unrealized profit yang "
                "masih di persediaan pembeli, dan saldo IC-AR/IC-AP yang belum "
                "diselesaikan (INV-IC-02/INV-IC-03)."
            ),
            "lines": lines,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "balanced": abs(total_debit - total_credit) < 0.01,
            "impact": await _compute_impact(lines, amap),
            "auto_generated": True,
            "source_g6_pair_id": p["pair_id"],
            "source_status": p.get("status", ""),
            # FASE G-6b — jejak angka yang dipakai (dibaca invarian INV-IC-03 &
            # layar Rapor Margin Grup, supaya tidak ada dua rumus yang berbeda).
            "g6_unsold_ratio": round(float(p.get("unsold_ratio", 1.0) or 0.0), 6),
            "g6_subtotal_effective": round(float(p["subtotal"]), 2),
            "g6_cost_effective": round(float(p["cost"]), 2),
            "g6_qty_base": round(float(p.get("qty_base") or 0), 4),
            "g6_qty_remaining": round(float(p.get("qty_remaining") or 0), 4),
            # FASE E-7 (E7.3) — label HPP taksiran ikut menempel di entri eliminasi.
            "g6_cost_estimated": bool(p.get("cost_estimated")),
            "g6_cost_basis": p.get("cost_basis", ""),
            "g6_cost_estimate": round(float(p.get("cost_estimate") or 0), 2),
            "g6_cost_estimate_reason": p.get("cost_estimate_reason", ""),
            "updated_at": now_iso(),
        }
        if p.get("cost_estimated"):
            payload["note"] += (
                " ⚠ HPP penjual BELUM diposting, jadi HPP yang dieliminasi masih 0 "
                "(bukan berarti HPP-nya nol). Taksiran WAC penjual: "
                f"{rupiah(float(p.get('cost_estimate') or 0))} — angka ini keterangan, "
                "bukan jurnal. Setelah barang keluar gudang, entri ini otomatis "
                "diperbarui dengan HPP sebenarnya.")
        if prev is None:
            doc = {"id": new_id("icelim"), **payload,
                   "created_by": "system", "created_by_id": None,
                   "created_at": now_iso()}
            await db.intercompany_eliminations.insert_one(dict(doc))
            created.append(safe_doc(doc))
        elif _lines_differ(prev.get("lines"), lines) or \
                bool(prev.get("g6_cost_estimated")) != bool(payload["g6_cost_estimated"]):
            # Label HPP taksiran juga alasan sah untuk memperbarui entri: begitu HPP
            # sebenarnya diposting, keterangan "taksiran" WAJIB hilang dari layar.
            await db.intercompany_eliminations.update_one(
                {"id": prev["id"]}, {"$set": payload})
            updated.append(safe_doc({**prev, **payload}))
        else:
            skipped += 1

    # Entri auto yang pair-nya sudah tidak sah lagi (dibatalkan / kembali draf /
    # dokumennya dihapus) WAJIB ikut hilang — kalau tidak, konsolidasi menghapus
    # pendapatan yang sebenarnya tidak pernah ada.
    for pid, e in by_pair.items():
        if pid in qualifying:
            continue
        still = await db.interco_transactions.count_documents({
            "pair_id": pid, "role": "seller",
            "status": {"$nin": ["draft", "cancelled"]}})
        if still == 0:
            await db.intercompany_eliminations.delete_one({"id": e["id"]})
            removed += 1

    return {
        "created": len(created), "updated": len(updated), "removed": removed,
        "skipped_existing": skipped, "pairs_seen": len(pairs),
        "entries": created + updated,
    }


async def sync_g6_for_pair(pair_id: str) -> Dict[str, Any]:
    """Sinkronkan eliminasi untuk SATU pair (dipakai hook interco_service).

    Kegagalan tidak boleh menggagalkan transaksi bisnis — pemanggil membungkus
    dengan try/except; di sini kita hanya membatasi cakupan kerja.
    """
    return await sync_g6_ic_eliminations(pair_id=pair_id)
