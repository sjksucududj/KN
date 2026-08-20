"""FASE G-6b — **RAPOR MARGIN GRUP** antar-PT (realized vs unrealized).

MASALAH NYATA
-------------
Eliminasi konsolidasi G-6 menghapus **seluruh** margin antar-PT sebagai
*unrealized profit* — benar selama barangnya masih menumpuk di gudang pembeli,
tetapi SALAH begitu pembeli menjual barangnya ke pihak luar. Sejak saat itu laba
itu NYATA bagi grup dan tidak boleh dihapus lagi. Tanpa modul ini:

* laba grup **terlalu kecil** (margin yang sudah direalisasi tetap dieliminasi), dan
* tidak ada satu layar pun yang bisa menjawab *"berapa margin antar-PT kita, dan
  berapa yang sudah benar-benar jadi uang dari pihak luar?"*

CARA MENGUKUR (data nyata, bukan taksiran)
------------------------------------------
Saat barang antar-PT berpindah, `interco_service.on_warehouse_task_executed`
menandai roll pembeli dengan `cost_basis.interco_pair_id`. Jadi sisa panjang roll
bertanda itu = bagian yang **belum terjual keluar**. Rasio `u` (unsold) dihitung
dari sana — bukan dari asumsi.

    u = Σ panjang roll bertanda (masih dimiliki pembeli) / qty yang berpindah
    margin belum terealisasi = margin × u

Identitas eliminasi yang dipakai konsolidasi (S=harga internal, C=HPP penjual,
M=S−C, s=1−u):

    Dr Pendapatan  S
      Cr HPP         C·u + S·s
      Cr Persediaan  M·u

Saat u=1 (belum ada yang terjual) rumus ini identik dengan perilaku lama
(Cr HPP = C, Cr Persediaan = M) — jadi tidak ada data lama yang berubah artinya.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from db import db

EPS = 0.01
ACTIVE_ROLL_STATUS = ("available", "reserved", "allocated", "in_transit")


async def _receipt_posted(pair_id: str) -> bool:
    je = await db.journal_entries.find_one(
        {"source_type": "interco_transaction", "source_id": f"{pair_id}:receipt",
         "status": "posted"}, {"_id": 0, "id": 1})
    return bool(je)


async def unsold_ratio(pair_id: str, seller: Optional[Dict[str, Any]] = None,
                      delivered: Optional[bool] = None) -> Dict[str, Any]:
    """Rasio barang antar-PT yang MASIH ada di gudang pembeli (0..1) + buktinya.

    * Barang belum berpindah → `1.0` (belum mungkin terjual ke pihak luar).
    * Barang sudah berpindah tetapi tidak ada roll bertanda lagi → `0.0`
      (semuanya sudah terpakai/terjual keluar).
    * Barang yang sudah DIRETUR tidak dihitung di penyebut (ia kembali ke penjual,
      bukan terjual ke pihak luar) — dan rollnya kehilangan tanda pair-nya.
    """
    if seller is None:
        seller = await db.interco_transactions.find_one(
            {"pair_id": pair_id, "role": "seller"}, {"_id": 0})
    if not seller:
        return {"ratio": 1.0, "qty_base": 0.0, "qty_remaining": 0.0,
                "delivered": False, "rolls": 0}
    qty_total = round(sum(float(i.get("quantity") or 0)
                          for i in seller.get("items", [])), 4)
    qty_returned = round(float(seller.get("returned_qty") or 0), 4)
    qty_base = round(max(qty_total - qty_returned, 0.0), 4)
    if delivered is None:
        delivered = await _receipt_posted(pair_id)
    if not delivered or qty_base <= 0:
        return {"ratio": 1.0, "qty_base": qty_base, "qty_remaining": qty_base,
                "delivered": bool(delivered), "rolls": 0}
    rolls = await db.inventory_rolls.find(
        {"cost_basis.interco_pair_id": pair_id,
         "owner_entity_id": seller.get("buyer_entity_id"),
         "status": {"$in": list(ACTIVE_ROLL_STATUS)}},
        {"_id": 0, "length_remaining": 1}).to_list(20000)
    remaining = round(sum(float(r.get("length_remaining") or 0) for r in rolls), 4)
    ratio = remaining / qty_base if qty_base > 0 else 1.0
    ratio = max(0.0, min(1.0, round(ratio, 6)))
    return {"ratio": ratio, "qty_base": qty_base, "qty_remaining": remaining,
            "delivered": True, "rolls": len(rolls)}


async def _cogs_of(pair_id: str) -> float:
    je = await db.journal_entries.find_one(
        {"source_type": "interco_transaction", "source_id": f"{pair_id}:cogs",
         "status": "posted"}, {"_id": 0, "total_debit": 1})
    return round(float((je or {}).get("total_debit") or 0), 2)


# ─── FASE E-7 (E7.3 + keputusan pemilik E7.7 no.4b) — HPP TAKSIRAN WAJIB BERLABEL ──
# Temuan IC-G11: selama JE `{pair}:cogs` belum diposting (barang belum keluar gudang
# penjual), `_cogs_of` mengembalikan 0 sehingga rapor margin memberitakan **margin
# 100%** — angka telanjang yang dipakai pemilik untuk mengambil keputusan.
# Keputusan pemilik: taksiran DIBOLEHKAN, tetapi WAJIB BERLABEL. Jadi angka
# otoritatif (`cost`/`margin`) TIDAK diubah — supaya identitas eliminasi konsolidasi
# (INV-IC-03: dieliminasi == belum terealisasi) tetap utuh — dan di sampingnya
# dikirim taksiran yang jelas-jelas ditandai beserta ALASANNYA.
COST_BASIS_POSTED = "posted_je"       # HPP dari jurnal (otoritatif)
COST_BASIS_WAC = "wac_estimate"       # taksiran rata-rata bergerak (WAC) penjual
COST_BASIS_UNKNOWN = "unknown"        # WAC pun belum ada — jangan mengarang angka


async def cost_disclosure(seller: Dict[str, Any], cost_posted_gross: float,
                          subtotal_net: float) -> Dict[str, Any]:
    """Keterangan HPP satu pair: otoritatif atau taksiran (+ alasan + kekurangannya)."""
    if cost_posted_gross > EPS:
        return {
            "cost_estimated": False,
            "cost_basis": COST_BASIS_POSTED,
            "cost_estimate": 0.0,
            "margin_estimate": 0.0,
            "margin_pct_estimate": 0.0,
            "cost_estimate_reason": "",
            "cost_estimate_missing_wac": [],
        }
    from services.costing_service import wac_for_product
    seller_ent = seller.get("seller_entity_id") or ""
    est = 0.0
    missing: List[str] = []
    for it in seller.get("items", []) or []:
        pid = it.get("product_id") or ""
        qty = float(it.get("quantity") or 0)
        wac = 0.0
        if pid:
            w = await wac_for_product(pid, entity_id=seller_ent)
            wac = float((w or {}).get("wac") or 0)
        if wac <= 0:
            missing.append(it.get("sku") or pid or "(tanpa produk)")
        est += wac * qty
    est = round(max(est - float(seller.get("returned_cost") or 0), 0.0), 2)
    margin_est = round(subtotal_net - est, 2)
    reason = (
        "HPP penjual belum diposting (jurnal HPP baru terbit saat barang keluar gudang), "
        "jadi angka HPP di sini adalah TAKSIRAN dari rata-rata bergerak (WAC) penjual. "
        "Margin final bisa berubah setelah barang benar-benar dikirim.")
    if missing:
        reason += (" Perhatian: WAC belum ada untuk "
                   + ", ".join(missing[:5])
                   + (" …" if len(missing) > 5 else "")
                   + " — bagian itu dihitung nol, jadi margin masih terlalu besar.")
    return {
        "cost_estimated": True,
        "cost_basis": COST_BASIS_WAC if est > EPS else COST_BASIS_UNKNOWN,
        "cost_estimate": est,
        "margin_estimate": margin_est,
        "margin_pct_estimate": round(margin_est / subtotal_net * 100.0, 2)
        if subtotal_net > EPS else 0.0,
        "cost_estimate_reason": reason,
        "cost_estimate_missing_wac": missing,
    }


async def pair_margin(seller: Dict[str, Any]) -> Dict[str, Any]:
    """Angka margin satu pair (sesudah retur) + pembagian realized/unrealized."""
    pair_id = seller["pair_id"]
    subtotal = round(float(seller.get("subtotal") or 0)
                     - float(seller.get("returned_subtotal") or 0), 2)
    cost_gross = await _cogs_of(pair_id)
    cost = round(cost_gross - float(seller.get("returned_cost") or 0), 2)
    margin = round(subtotal - cost, 2)
    u = await unsold_ratio(pair_id, seller=seller)
    ratio = u["ratio"]
    unrealized = round(margin * ratio, 2)
    realized = round(margin - unrealized, 2)
    # E7.3 — label HPP taksiran (angka otoritatif di atas TIDAK diubah).
    disc = await cost_disclosure(seller, cost_gross, subtotal)
    return {
        **disc,
        "pair_id": pair_id,
        "number": seller.get("number", ""),
        "seller_entity_id": seller.get("seller_entity_id"),
        "seller_entity_name": seller.get("seller_entity_name", ""),
        "buyer_entity_id": seller.get("buyer_entity_id"),
        "buyer_entity_name": seller.get("buyer_entity_name", ""),
        "status": seller.get("status"),
        "doc_date": (seller.get("doc_date") or seller.get("created_at") or "")[:10],
        "subtotal": subtotal,
        "cost": cost,
        "margin": margin,
        "margin_pct": round((margin / subtotal * 100.0), 2) if subtotal > EPS else 0.0,
        "unsold_ratio": ratio,
        "qty_base": u["qty_base"],
        "qty_remaining": u["qty_remaining"],
        "delivered": u["delivered"],
        "unrealized_margin": unrealized,
        # FASE E-9 — LABA vs RUGI belum terealisasi dipisah dengan sengaja.
        # Eliminasi konsolidasi hanya menghapus LABA antar-PT yang belum benar-benar
        # terjadi bagi grup. Kalau marginnya NEGATIF (mis. barang yang diretur sudah
        # dihapus-bukukan menjadi Rp 0 sehingga penjual menanggung selisihnya), itu
        # RUGI nyata bagi grup — konservatisme akuntansi: rugi TIDAK dieliminasi.
        # Yang tidak boleh terjadi adalah rugi itu hilang tanpa keterangan; karena itu
        # angkanya tetap dilaporkan lewat `unrealized_loss` + kalimat penjelas.
        "unrealized_profit": max(unrealized, 0.0),
        "unrealized_loss": round(-min(unrealized, 0.0), 2),
        "loss_not_eliminated": unrealized < -EPS,
        "loss_reason": (
            "Rugi belum terealisasi tidak dieliminasi (konservatisme): margin antar-PT "
            "dokumen ini negatif — biasanya karena barang yang diretur sudah "
            "dihapus-bukukan, jadi penjual menanggung selisihnya."
            if unrealized < -EPS else ""),
        "realized_margin": realized,
        "returned_subtotal": round(float(seller.get("returned_subtotal") or 0), 2),
        "returned_cost": round(float(seller.get("returned_cost") or 0), 2),
    }


async def margin_report(scope_entity_ids: Optional[List[str]] = None,
                        entity_id: str = "", as_of: str = "") -> Dict[str, Any]:
    """Rapor margin antar-PT per pasangan PT + bandingkan dengan eliminasi terpasang."""
    q: Dict[str, Any] = {"role": "seller",
                         "status": {"$nin": ["draft", "cancelled"]}}
    if as_of:
        q["doc_date"] = {"$lte": as_of}
    sellers = await db.interco_transactions.find(q, {"_id": 0}).to_list(20000)
    if entity_id and entity_id != "all":
        sellers = [s for s in sellers
                   if entity_id in (s.get("seller_entity_id"), s.get("buyer_entity_id"))]
    elif scope_entity_ids:
        sellers = [s for s in sellers
                   if s.get("seller_entity_id") in scope_entity_ids
                   or s.get("buyer_entity_id") in scope_entity_ids]

    elims = await db.intercompany_eliminations.find(
        {"source_g6_pair_id": {"$exists": True, "$ne": None}}, {"_id": 0}).to_list(20000)
    elim_by_pair: Dict[str, Dict[str, Any]] = {e["source_g6_pair_id"]: e for e in elims}

    rows: List[Dict[str, Any]] = []
    for s in sellers:
        row = await pair_margin(s)
        e = elim_by_pair.get(row["pair_id"])
        elim_inv = 0.0
        if e:
            elim_inv = round(sum(float(l.get("credit") or 0) for l in e.get("lines", [])
                                 if l.get("account_code") in ("1-1300", "1-1310")), 2)
        row["eliminated_unrealized"] = elim_inv
        row["elimination_id"] = (e or {}).get("id", "")
        row["elimination_name"] = (e or {}).get("name", "")
        row["elimination_gap"] = round(elim_inv - row["unrealized_profit"], 2)
        rows.append(row)

    pairs: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = f"{r['seller_entity_id']}|{r['buyer_entity_id']}"
        agg = pairs.setdefault(key, {
            "key": key,
            "seller_entity_id": r["seller_entity_id"],
            "seller_entity_name": r["seller_entity_name"],
            "buyer_entity_id": r["buyer_entity_id"],
            "buyer_entity_name": r["buyer_entity_name"],
            "doc_count": 0, "subtotal": 0.0, "cost": 0.0, "margin": 0.0,
            "unrealized_margin": 0.0, "unrealized_profit": 0.0,
            "unrealized_loss": 0.0, "realized_margin": 0.0,
            "eliminated_unrealized": 0.0,
            # E7.3 — berapa dokumen di pasangan ini yang HPP-nya masih taksiran.
            "cost_estimated": False, "estimated_doc_count": 0,
            "cost_estimate": 0.0, "margin_estimate": 0.0,
        })
        agg["doc_count"] += 1
        if r.get("cost_estimated"):
            agg["cost_estimated"] = True
            agg["estimated_doc_count"] += 1
            agg["cost_estimate"] = round(agg["cost_estimate"] + r.get("cost_estimate", 0.0), 2)
            agg["margin_estimate"] = round(agg["margin_estimate"] + r.get("margin_estimate", 0.0), 2)
        else:
            agg["cost_estimate"] = round(agg["cost_estimate"] + r["cost"], 2)
            agg["margin_estimate"] = round(agg["margin_estimate"] + r["margin"], 2)
        for k in ("subtotal", "cost", "margin", "unrealized_margin",
                  "unrealized_profit", "unrealized_loss",
                  "realized_margin", "eliminated_unrealized"):
            agg[k] = round(agg[k] + r[k], 2)
    for agg in pairs.values():
        agg["margin_pct"] = round(agg["margin"] / agg["subtotal"] * 100.0, 2) \
            if agg["subtotal"] > EPS else 0.0
        agg["elimination_gap"] = round(
            agg["eliminated_unrealized"] - agg["unrealized_profit"], 2)
        agg["loss_not_eliminated"] = agg["unrealized_loss"] > EPS

    totals = {
        "doc_count": len(rows),
        "subtotal": round(sum(r["subtotal"] for r in rows), 2),
        "cost": round(sum(r["cost"] for r in rows), 2),
        "margin": round(sum(r["margin"] for r in rows), 2),
        "unrealized_margin": round(sum(r["unrealized_margin"] for r in rows), 2),
        "unrealized_profit": round(sum(r["unrealized_profit"] for r in rows), 2),
        "unrealized_loss": round(sum(r["unrealized_loss"] for r in rows), 2),
        "realized_margin": round(sum(r["realized_margin"] for r in rows), 2),
        "eliminated_unrealized": round(sum(r["eliminated_unrealized"] for r in rows), 2),
        # E7.3 — kejujuran di tingkat total: berapa dokumen yang HPP-nya taksiran, dan
        # berapa margin bila taksiran itu dipakai. `margin` tetap angka otoritatif.
        "estimated_doc_count": sum(1 for r in rows if r.get("cost_estimated")),
        "cost_estimated": any(r.get("cost_estimated") for r in rows),
        "cost_estimate": round(sum(r.get("cost_estimate", 0.0) if r.get("cost_estimated")
                                   else r["cost"] for r in rows), 2),
        "margin_estimate": round(sum(r.get("margin_estimate", 0.0) if r.get("cost_estimated")
                                     else r["margin"] for r in rows), 2),
    }
    totals["margin_pct"] = round(totals["margin"] / totals["subtotal"] * 100.0, 2) \
        if totals["subtotal"] > EPS else 0.0
    totals["elimination_gap"] = round(
        totals["eliminated_unrealized"] - totals["unrealized_profit"], 2)
    totals["loss_not_eliminated"] = totals["unrealized_loss"] > EPS
    totals["loss_reason"] = next((r["loss_reason"] for r in rows if r.get("loss_reason")), "")

    return {
        "as_of": as_of or "",
        "rows": sorted(rows, key=lambda r: -r["margin"]),
        "pairs": sorted(pairs.values(), key=lambda p: -p["margin"]),
        "totals": totals,
    }


# ─── FASE P3 — RAPOR MARGIN PER BARANG (antar-PT) ────────────────────────────
async def margin_by_product(scope_entity_ids: Optional[List[str]] = None,
                            entity_id: str = "", pair: str = "",
                            as_of: str = "") -> Dict[str, Any]:
    """Margin transaksi antar-PT **dipecah per BARANG**, urut margin terbesar.

    * Pendapatan  = `line_subtotal` (harga jual internal penjual, sebelum retur).
    * HPP per baris = HPP transaksi (`_cogs_of` = JE COGS penjual, otoritatif)
      dibagi proporsional terhadap nilai baris → jumlah per-barang PASTI konsisten
      dengan rapor per-pasangan (tanpa asumsi konversi satuan).
    * Penyaring `pair` = "seller_entity_id|buyer_entity_id" (pasangan PT).

    Mengembalikan juga daftar `pairs` (untuk dropdown penyaring) + `totals`.
    """
    q: Dict[str, Any] = {"role": "seller", "status": {"$nin": ["draft", "cancelled"]}}
    if as_of:
        q["doc_date"] = {"$lte": as_of}
    sellers = await db.interco_transactions.find(q, {"_id": 0}).to_list(20000)

    if entity_id and entity_id != "all":
        sellers = [s for s in sellers
                   if entity_id in (s.get("seller_entity_id"), s.get("buyer_entity_id"))]
    elif scope_entity_ids:
        sellers = [s for s in sellers
                   if s.get("seller_entity_id") in scope_entity_ids
                   or s.get("buyer_entity_id") in scope_entity_ids]

    # Daftar pasangan PT yang tersedia (untuk penyaring di UI) — dari semua yang ter-scope.
    pair_index: Dict[str, Dict[str, Any]] = {}
    for s in sellers:
        pkey = f"{s.get('seller_entity_id')}|{s.get('buyer_entity_id')}"
        pair_index.setdefault(pkey, {
            "key": pkey,
            "seller_entity_id": s.get("seller_entity_id"),
            "seller_entity_name": s.get("seller_entity_name", ""),
            "buyer_entity_id": s.get("buyer_entity_id"),
            "buyer_entity_name": s.get("buyer_entity_name", ""),
            "label": f"{s.get('seller_entity_name', '')} → {s.get('buyer_entity_name', '')}",
        })

    if pair:
        sellers = [s for s in sellers
                   if f"{s.get('seller_entity_id')}|{s.get('buyer_entity_id')}" == pair]

    by_product: Dict[str, Dict[str, Any]] = {}
    for s in sellers:
        pair_id = s.get("pair_id")
        gross_subtotal = float(s.get("subtotal") or 0)
        txn_cogs = await _cogs_of(pair_id)
        seller_ent = s.get("seller_entity_id")
        use_wac = txn_cogs <= EPS   # HPP belum diposting (mis. belum kirim) → estimasi WAC
        items = s.get("items") or []
        # Total nilai baris (untuk pembagian HPP proporsional).
        line_total_sum = sum(float(it.get("line_subtotal") or 0) for it in items) or gross_subtotal
        for it in items:
            pid = it.get("product_id") or it.get("sku") or "(tanpa produk)"
            revenue = float(it.get("line_subtotal") or 0)
            qty = float(it.get("quantity") or 0)
            estimated = False
            if use_wac:
                from services.costing_service import wac_for_product
                w = await wac_for_product(pid, entity_id=seller_ent)
                cost = round(float(w.get("wac", 0) or 0) * qty, 2)
                estimated = True
            else:
                share = (revenue / line_total_sum) if line_total_sum > EPS else 0.0
                cost = round(txn_cogs * share, 2)
            row = by_product.setdefault(pid, {
                "product_id": pid, "sku": it.get("sku", ""),
                "product_name": it.get("product_name") or pid,
                "qty": 0.0, "unit": it.get("unit", ""),
                "revenue": 0.0, "cost": 0.0, "margin": 0.0,
                "txn_count": 0, "cost_estimated": False, "_pairs": set(),
            })
            row["qty"] = round(row["qty"] + qty, 3)
            row["revenue"] = round(row["revenue"] + revenue, 2)
            row["cost"] = round(row["cost"] + cost, 2)
            row["txn_count"] += 1
            if estimated:
                row["cost_estimated"] = True
            row["_pairs"].add(f"{s.get('seller_entity_name', '')}→{s.get('buyer_entity_name', '')}")

    rows: List[Dict[str, Any]] = []
    for row in by_product.values():
        row["margin"] = round(row["revenue"] - row["cost"], 2)
        row["margin_pct"] = round(row["margin"] / row["revenue"] * 100.0, 2) \
            if row["revenue"] > EPS else 0.0
        row["pairs"] = sorted(row.pop("_pairs"))
        rows.append(row)
    rows.sort(key=lambda r: -r["margin"])

    totals = {
        "product_count": len(rows),
        "revenue": round(sum(r["revenue"] for r in rows), 2),
        "cost": round(sum(r["cost"] for r in rows), 2),
        "margin": round(sum(r["margin"] for r in rows), 2),
    }
    totals["margin_pct"] = round(totals["margin"] / totals["revenue"] * 100.0, 2) \
        if totals["revenue"] > EPS else 0.0

    return {
        "as_of": as_of or "",
        "pair": pair or "",
        "rows": rows,
        "pairs": sorted(pair_index.values(), key=lambda p: p["label"]),
        "totals": totals,
    }
