"""F1b — SATU definisi **batas bawah harga jual** (price floor) untuk seluruh sistem.

MENGAPA ADA (keputusan pemilik, sesi 2026-08-10):
    *"Harga khusus pelanggan wajib persetujuan manajer bila di bawah harga PT/HPP.
      Cek dengan logic special price yang ada — logikanya harus SAMA, jangan duplikasi."*

Sebelum modul ini, pertanyaan **"harga ini terlalu murah?"** dijawab dua kali dengan
cara berbeda:
  · layar **Harga Khusus** (`price_approvals`) memakai `products.price` (harga GLOBAL)
    sebagai `normal_price` — biaya pokok (HPP) tidak pernah dilihat;
  · layar **Daftar Harga per Pelanggan** (F1b) belum memeriksa apa pun.
Akibatnya harga di bawah biaya pokok bisa lolos tanpa satu pun peringatan.

Sekarang KEDUA alur memanggil `evaluate()` yang sama, sehingga ambang, dasar
perhitungan, dan kalimat penjelasannya TIDAK MUNGKIN berbeda.

Dasar batas dapat diatur pemilik di **Pusat Pengaturan → Harga, Diskon & Komisi**:
  · `pricelist.customer_price_approval`      — nyalakan/matikan penjagaan
  · `pricelist.customer_price_floor`         — entity_price | hpp | both (bawaan)
  · `pricelist.customer_price_tolerance_pct` — toleransi persen di bawah batas

HPP dibaca dari SUMBER YANG SAMA dengan yang dipakai baris pesanan penjualan
(`costing_service.wac_for_product` → fallback `products.harga_pokok`) supaya angka
di peringatan sama dengan angka di laporan margin.
"""
from typing import Any, Dict, Optional

from core_utils import rupiah
from services import costing_service, pricelist_service
from services.config_resolver import value_of

K_ON = "pricelist.customer_price_approval"
K_BASIS = "pricelist.customer_price_floor"
K_TOL = "pricelist.customer_price_tolerance_pct"

BASIS_LABEL = {
    "entity_price": "harga jual PT",
    "hpp": "biaya pokok (HPP)",
    "both": "harga PT & HPP (dipakai yang lebih tinggi)",
}


def _f(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


async def settings_for(entity_id: str = "") -> Dict[str, Any]:
    """Kebijakan penjagaan harga yang BERLAKU (global → ditimpa per entitas)."""
    ctx = {"entity_id": entity_id or ""}
    basis = str(await value_of(K_BASIS, ctx) or "both").strip().lower()
    if basis not in BASIS_LABEL:
        basis = "both"
    tol = _f(await value_of(K_TOL, ctx), 0.0)
    return {
        "guard_on": bool(await value_of(K_ON, ctx)),
        "basis": basis,
        "basis_label": BASIS_LABEL[basis],
        "tolerance_pct": max(0.0, min(100.0, tol)),
    }


async def floor_for(entity_id: str, product: Optional[Dict[str, Any]],
                    cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Batas bawah harga untuk satu produk di satu entitas (per base unit).

    `entity_reference` = harga PT bila entitas punya pricelist sendiri, kalau tidak
    jatuh ke harga global — sengaja SAMA dengan yang dipakai saat menghitung harga
    baris pesanan, supaya "pembanding" di layar bukan angka karangan.
    """
    product = product or {}
    cfg = cfg or await settings_for(entity_id)
    pid = str(product.get("id") or "")
    global_price = round(_f(product.get("price")), 2)
    pt = await pricelist_service.resolve_sell_price(entity_id, pid, product)
    entity_reference = round(_f(pt.get("price"), global_price), 2)
    has_entity_price = pt.get("source") == "entity"

    hpp = 0.0
    if pid:
        try:
            wac = await costing_service.wac_for_product(pid, entity_id=entity_id or None,
                                                       product=product)
            hpp = _f((wac or {}).get("wac"))
        except Exception:  # noqa: BLE001 — HPP tidak boleh menjatuhkan penyimpanan harga
            hpp = 0.0
    if hpp <= 0:
        hpp = _f(product.get("harga_pokok"))
    hpp = round(hpp, 2)

    candidates: Dict[str, float] = {}
    if cfg["basis"] in ("entity_price", "both") and entity_reference > 0:
        candidates["entity_price"] = entity_reference
    if cfg["basis"] in ("hpp", "both") and hpp > 0:
        candidates["hpp"] = hpp
    floor = round(max(candidates.values()), 2) if candidates else 0.0
    floor_from = max(candidates, key=lambda k: candidates[k]) if candidates else ""
    tol = cfg["tolerance_pct"]
    threshold = round(floor * (1 - tol / 100.0), 2) if floor > 0 else 0.0
    return {
        "product_id": pid, "sku": product.get("sku", ""),
        "product_name": product.get("name", ""),
        "base_unit": product.get("base_unit", "meter"),
        "global_price": global_price,
        "entity_price": entity_reference if has_entity_price else None,
        "entity_reference": entity_reference,
        "has_entity_price": has_entity_price,
        "hpp": hpp,
        "floor": floor, "floor_from": floor_from, "threshold": threshold,
        "guard_on": cfg["guard_on"], "basis": cfg["basis"],
        "basis_label": cfg["basis_label"], "tolerance_pct": tol,
    }


def _pct(value: float) -> str:
    """Persen gaya Indonesia: 45.9 → '45,9' (bukan '45.9')."""
    return f"{value:.1f}".replace(".", ",")


async def evaluate(price: float, entity_id: str, product: Optional[Dict[str, Any]],
                   cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Boleh langsung berlaku, atau wajib persetujuan manajer?

    Return (dipakai backend & ditampilkan apa adanya di layar):
      {..floor_for.., price, below_floor, needs_approval, gap, gap_pct,
       margin_pct, reasons[], summary}
    """
    info = await floor_for(entity_id, product, cfg)
    price = round(_f(price), 2)
    unit = info["base_unit"]
    floor = info["floor"]
    below = bool(floor > 0 and price < info["threshold"] - 0.005)
    reasons = []
    if info["basis"] in ("entity_price", "both") and info["entity_reference"] > 0 \
            and price < info["entity_reference"] - 0.005:
        drop = (info["entity_reference"] - price) / info["entity_reference"] * 100.0
        label = "harga PT" if info["has_entity_price"] else "harga umum"
        reasons.append(f"{rupiah(price)}/{unit} berada {_pct(drop)}% di bawah {label} "
                       f"{rupiah(info['entity_reference'])}/{unit}.")
    if info["basis"] in ("hpp", "both") and info["hpp"] > 0 and price < info["hpp"] - 0.005:
        reasons.append(f"{rupiah(price)}/{unit} berada DI BAWAH biaya pokok "
                       f"{rupiah(info['hpp'])}/{unit} — setiap {unit} terjual merugi.")
    margin_pct = (round((price - info["hpp"]) / price * 100.0, 2)
                  if price > 0 and info["hpp"] > 0 else None)
    needs = bool(info["guard_on"] and below)
    if not below:
        summary = (f"Harga aman: {rupiah(price)}/{unit} tidak di bawah batas "
                   f"{rupiah(floor)}/{unit}." if floor > 0 else
                   "Belum ada pembanding harga PT/HPP untuk produk ini.")
    elif needs:
        summary = ("Harga di bawah batas — perlu persetujuan manajer sebelum berlaku. "
                   + " ".join(reasons))
    else:
        summary = ("Harga di bawah batas, tetapi penjagaan persetujuan sedang DIMATIKAN "
                   "di Pusat Pengaturan. " + " ".join(reasons))
    return {
        **info, "price": price, "below_floor": below, "needs_approval": needs,
        "gap": round(floor - price, 2) if floor > 0 else 0.0,
        "gap_pct": round((floor - price) / floor * 100.0, 2) if floor > 0 else 0.0,
        "margin_pct": margin_pct, "reasons": reasons, "summary": summary,
    }


async def evaluate_product_id(price: float, entity_id: str, product_id: str,
                              cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Versi praktis bila pemanggil hanya punya `product_id`."""
    from db import db  # impor lokal: modul ini dipakai juga oleh skrip audit
    product = await db.products.find_one({"id": product_id}, {"_id": 0}) or {}
    return await evaluate(price, entity_id, product, cfg)
