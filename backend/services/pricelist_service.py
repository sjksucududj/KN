"""F1a — Pricelist per-entitas (harga jual per-PT) dengan histori & tanggal efektif.

Model SILO multi-entity (F0): tiap entitas (PT/CV) boleh menetapkan harga jual
sendiri per produk. Bila entitas BELUM punya harga aktif untuk produk → fallback
ke harga global `products.price` (keputusan owner F1a-2a).

Koleksi: `entity_prices` (prefix `epr_`) — SCOPED via entity_id.
  {id, entity_id, product_id, sku, product_name, sell_price (per base unit),
   currency, valid_from (iso), valid_until (iso|""), is_listed, status (active|inactive),
   note, created_by, created_at, updated_at}

Resolusi (`resolve_sell_price`): di antara record aktif (status active, is_listed,
valid_from <= as_of, valid_until kosong / >= as_of) → ambil valid_from TERBESAR.
"""
import csv
import io
from typing import Any, Dict, List, Optional, Tuple

from db import db
from core_utils import new_id, now_iso, safe_doc

PREFIX = "epr"


def _norm_dt(value: Optional[str], end_of_day: bool = False) -> str:
    """Normalisasi tanggal: 'YYYY-MM-DD' → awal/akhir hari UTC. Kosong → ''."""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) == 10 and v.count("-") == 2:
        return f"{v}T23:59:59+00:00" if end_of_day else f"{v}T00:00:00+00:00"
    return v


def effective_status(r: Dict[str, Any], now: Optional[str] = None) -> str:
    now = now or now_iso()
    if r.get("status") == "inactive":
        return "inactive"
    vf = r.get("valid_from") or ""
    vu = r.get("valid_until") or ""
    if vf and vf > now:
        return "scheduled"
    if vu and vu < now:
        return "expired"
    return "current"


def decorate(r: Dict[str, Any]) -> Dict[str, Any]:
    if not r:
        return r
    st = effective_status(r)
    r["effective_status"] = st
    r["is_current"] = st == "current"
    return r


def _active_candidates(records: List[Dict[str, Any]], as_of: str) -> List[Dict[str, Any]]:
    out = []
    for r in records:
        if r.get("status") == "inactive" or not r.get("is_listed", True):
            continue
        vf = r.get("valid_from") or ""
        vu = r.get("valid_until") or ""
        if vf and vf > as_of:
            continue
        if vu and vu < as_of:
            continue
        out.append(r)
    return out


def _rank(r: Dict[str, Any]) -> tuple:
    """Urutan “siapa yang menang” bila beberapa record sama-sama berlaku.

    `valid_from` saja TIDAK cukup: dua harga yang ditetapkan pada HARI yang sama
    punya `valid_from` identik (dinormalkan ke 00:00), dan `max()` lalu memilih
    sembarang — pernah membuat harga LAMA tetap dipakai setelah manajer
    memperbaiki angkanya di hari yang sama (ditemukan POC FASE E-4).
    Pemenangnya: tanggal berlaku terbaru → yang dibuat paling akhir.
    """
    return (r.get("valid_from") or "", r.get("created_at") or "", r.get("id") or "")


def pick_best(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """SATU definisi “harga mana yang dipakai” untuk seluruh sistem."""
    return max(candidates, key=_rank) if candidates else None


async def resolve_sell_price(entity_id: Optional[str], product_id: str,
                             product: Optional[Dict[str, Any]] = None,
                             as_of: Optional[str] = None) -> Dict[str, Any]:
    """Harga jual efektif (per base unit) untuk (entity, product). Fallback global."""
    as_of = as_of or now_iso()
    fallback = float((product or {}).get("price", 0) or 0)
    if not entity_id or entity_id == "all":
        return {"price": fallback, "source": "global", "record_id": None}
    recs = await db.entity_prices.find(
        {"entity_id": entity_id, "product_id": product_id, "status": "active"}, {"_id": 0}).to_list(300)
    cand = _active_candidates(recs, as_of)
    if not cand:
        return {"price": fallback, "source": "global", "record_id": None}
    best = pick_best(cand)
    return {"price": round(float(best["sell_price"]), 2), "source": "entity",
            "record_id": best["id"], "valid_until": best.get("valid_until", "")}


async def resolve_many(entity_id: Optional[str], product_ids: List[str],
                       products_map: Optional[Dict[str, Any]] = None,
                       as_of: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Batch resolve harga jual efektif untuk banyak produk (1 query)."""
    as_of = as_of or now_iso()
    products_map = products_map or {}
    ids = list(dict.fromkeys(product_ids))
    base = {pid: float((products_map.get(pid) or {}).get("price", 0) or 0) for pid in ids}
    if not entity_id or entity_id == "all":
        return {pid: {"price": base.get(pid, 0.0), "source": "global", "record_id": None} for pid in ids}
    recs = await db.entity_prices.find(
        {"entity_id": entity_id, "product_id": {"$in": ids}, "status": "active"}, {"_id": 0}).to_list(10000)
    by_pid: Dict[str, List[Dict[str, Any]]] = {}
    for r in _active_candidates(recs, as_of):
        by_pid.setdefault(r["product_id"], []).append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for pid in ids:
        cand = by_pid.get(pid)
        if cand:
            best = pick_best(cand)
            out[pid] = {"price": round(float(best["sell_price"]), 2), "source": "entity", "record_id": best["id"]}
        else:
            out[pid] = {"price": base.get(pid, 0.0), "source": "global", "record_id": None}
    return out


async def create_price(data: Dict[str, Any], entity_id: str, actor_name: str) -> Dict[str, Any]:
    product = await db.products.find_one({"id": data.get("product_id")}, {"_id": 0})
    if not product:
        raise ValueError("Produk tidak ditemukan")
    price = round(float(data.get("sell_price") or 0), 2)
    if price <= 0:
        raise ValueError("Harga jual harus lebih dari 0")
    eid = (data.get("entity_id") or "").strip() or entity_id
    vfrom = _norm_dt(data.get("valid_from")) or now_iso()
    vuntil = _norm_dt(data.get("valid_until"), end_of_day=True)
    if vuntil and vuntil < vfrom:
        raise ValueError("Tanggal berakhir tidak boleh sebelum tanggal mulai")
    # Auto-close record open-ended yang masih berlaku agar timeline tidak overlap.
    existing = await db.entity_prices.find(
        {"entity_id": eid, "product_id": product["id"], "status": "active"}, {"_id": 0}).to_list(300)
    for r in existing:
        rf = r.get("valid_from") or ""
        ru = r.get("valid_until") or ""
        # `<=` (bukan `<`): memperbaiki harga di HARI YANG SAMA harus menutup harga
        # sebelumnya. Dengan `<` keduanya tetap "berlaku" dan harga lama bisa menang.
        if rf <= vfrom and (ru == "" or ru >= vfrom):
            await db.entity_prices.update_one(
                {"id": r["id"]}, {"$set": {"valid_until": vfrom, "updated_at": now_iso()}})
    doc = {
        "id": new_id(PREFIX), "entity_id": eid, "product_id": product["id"],
        "sku": product.get("sku", ""), "product_name": product.get("name", ""),
        "sell_price": price, "currency": "IDR",
        "valid_from": vfrom, "valid_until": vuntil,
        "is_listed": bool(data.get("is_listed", True)), "status": "active",
        "note": (data.get("note") or "").strip(),
        "created_by": actor_name, "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.entity_prices.insert_one(doc)
    return decorate(safe_doc(doc))


async def patch_price(price_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    rec = await db.entity_prices.find_one({"id": price_id}, {"_id": 0})
    if not rec:
        raise ValueError("Harga tidak ditemukan")
    upd: Dict[str, Any] = {}
    if data.get("sell_price") is not None:
        p = round(float(data["sell_price"]), 2)
        if p <= 0:
            raise ValueError("Harga jual harus lebih dari 0")
        upd["sell_price"] = p
    if data.get("valid_until") is not None:
        upd["valid_until"] = _norm_dt(str(data["valid_until"]), end_of_day=True)
    if data.get("is_listed") is not None:
        upd["is_listed"] = bool(data["is_listed"])
    if data.get("note") is not None:
        upd["note"] = (str(data["note"]) or "").strip()
    if not upd:
        raise ValueError("Tidak ada perubahan valid untuk disimpan")
    upd["updated_at"] = now_iso()
    await db.entity_prices.update_one({"id": price_id}, {"$set": upd})
    return decorate(safe_doc(await db.entity_prices.find_one({"id": price_id}, {"_id": 0})))


async def deactivate_price(price_id: str) -> Dict[str, Any]:
    rec = await db.entity_prices.find_one({"id": price_id}, {"_id": 0})
    if not rec:
        raise ValueError("Harga tidak ditemukan")
    await db.entity_prices.update_one(
        {"id": price_id}, {"$set": {"status": "inactive", "updated_at": now_iso()}})
    return {"deactivated": True, "id": price_id}


async def get_record(price_id: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db.entity_prices.find_one({"id": price_id}, {"_id": 0}))


async def list_records(scope: Dict[str, Any], product_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q = dict(scope or {})
    if product_id:
        q["product_id"] = product_id
    rows = await db.entity_prices.find(q, {"_id": 0}).sort(
        [("product_id", 1), ("valid_from", -1)]).to_list(5000)
    return [decorate(safe_doc(r)) for r in rows]


async def pricelist_grid(entity_id: str, search: str = "") -> List[Dict[str, Any]]:
    """Satu baris per produk dengan **tiga angka + asal harga** (E4.7).

    Kolom yang dipakai layar:
      `global_price`     harga master (dipakai semua badan usaha)
      `entity_price`     harga khusus badan usaha ini — `None` bila ikut global
      `effective_price`  yang benar-benar dipakai hari ini
      `price_source`     "entity" | "global"  → lencana asal harga di layar

    Baris juga membawa **masa berlaku** record yang sedang berjalan dan jumlah
    record terjadwal, supaya pengguna tahu harga akan berubah minggu depan.
    """
    products = await db.products.find({"status": {"$ne": "inactive"}}, {"_id": 0}).to_list(1000)
    if search:
        s = search.lower()
        products = [p for p in products
                    if s in f"{p.get('name','')}{p.get('sku','')}{p.get('category','')}".lower()]
    pids = [p["id"] for p in products]
    pmap = {p["id"]: p for p in products}
    resolved = await resolve_many(entity_id, pids, pmap)

    # Record entitas (aktif) untuk produk-produk ini — satu query, bukan per baris.
    recs: List[Dict[str, Any]] = []
    if entity_id and entity_id != "all" and pids:
        recs = await db.entity_prices.find(
            {"entity_id": entity_id, "product_id": {"$in": pids}, "status": "active"},
            {"_id": 0}).to_list(20000)
    now = now_iso()
    by_pid: Dict[str, List[Dict[str, Any]]] = {}
    for r in recs:
        by_pid.setdefault(r["product_id"], []).append(r)

    rows = []
    for p in products:
        r = resolved.get(p["id"], {})
        glob = float(p.get("price", 0) or 0)
        mine = by_pid.get(p["id"], [])
        current = None
        scheduled = 0
        currents = []
        for rec in mine:
            st = effective_status(rec, now)
            if st == "current":
                currents.append(rec)
            elif st == "scheduled":
                scheduled += 1
        current = pick_best(currents)
        has_entity = r.get("source") == "entity"
        rows.append({
            "product_id": p["id"], "sku": p.get("sku", ""), "product_name": p.get("name", ""),
            "category": p.get("category", ""), "base_unit": p.get("base_unit", "meter"),
            "global_price": glob,
            "entity_price": (round(float(current["sell_price"]), 2) if current else None),
            "effective_price": r.get("price", glob),
            "price_source": r.get("source", "global"),
            "has_entity_price": has_entity,
            "record_id": (current or {}).get("id", ""),
            "valid_from": (current or {}).get("valid_from", ""),
            "valid_until": (current or {}).get("valid_until", ""),
            "note": (current or {}).get("note", ""),
            "scheduled_count": scheduled,
            "history_count": len(mine),
            "hpp_ref": round(float(p.get("harga_pokok") or 0), 2),
            "diff_vs_global": (round(float(current["sell_price"]) - glob, 2) if current else 0.0),
        })
    rows.sort(key=lambda x: (x["category"], x["product_name"]))
    return rows


async def grid_summary(entity_id: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ringkasan untuk kartu di atas grid (dihitung dari baris yang sama)."""
    with_override = [r for r in rows if r["entity_price"] is not None]
    higher = sum(1 for r in with_override if r["diff_vs_global"] > 0)
    lower = sum(1 for r in with_override if r["diff_vs_global"] < 0)
    return {
        "products": len(rows),
        "with_entity_price": len(with_override),
        "following_global": len(rows) - len(with_override),
        "higher_than_global": higher,
        "lower_than_global": lower,
        "scheduled": sum(r["scheduled_count"] for r in rows),
    }


async def remove_override(entity_id: str, product_id: str) -> Dict[str, Any]:
    """“Kembalikan ke harga global” — hentikan SEMUA harga khusus badan usaha ini
    untuk satu produk.

    Record TIDAK dihapus: dinonaktifkan, supaya riwayat harga (dan alasan pesanan
    lama memakai angka tertentu) tetap bisa dibaca.
    """
    rows = await db.entity_prices.find(
        {"entity_id": entity_id, "product_id": product_id, "status": "active"},
        {"_id": 0}).to_list(500)
    if not rows:
        raise ValueError("Produk ini sudah memakai harga global — tidak ada yang perlu dilepas.")
    await db.entity_prices.update_many(
        {"entity_id": entity_id, "product_id": product_id, "status": "active"},
        {"$set": {"status": "inactive", "updated_at": now_iso()}})
    product = await db.products.find_one({"id": product_id}, {"_id": 0}) or {}
    return {"reverted": True, "product_id": product_id, "deactivated": len(rows),
            "product_name": product.get("name", ""),
            "global_price": round(float(product.get("price", 0) or 0), 2)}


# ─── Ekspor / impor CSV (E4.7) ────────────────────────────────────────────────
CSV_HEADER = ("sku", "nama_produk", "harga_global", "harga_entitas",
              "berlaku_dari", "berlaku_sampai", "catatan")


async def export_csv(entity_id: str, only_with_price: bool = False) -> Tuple[bytes, str]:
    """CSV ber-BOM UTF-8 (Excel Windows membaca huruf Indonesia dengan benar).

    Kolom `harga_entitas` sengaja DIKOSONGKAN untuk produk yang ikut global —
    supaya file yang dikirim balik tidak diam-diam mengunci ribuan harga baru.
    """
    rows = await pricelist_grid(entity_id)
    ent = await db.business_entities.find_one({"id": entity_id}, {"_id": 0}) or {}
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(list(CSV_HEADER))
    for r in rows:
        if only_with_price and r["entity_price"] is None:
            continue
        w.writerow([r["sku"], r["product_name"], f"{r['global_price']:.2f}",
                    ("" if r["entity_price"] is None else f"{r['entity_price']:.2f}"),
                    (r["valid_from"] or "")[:10], (r["valid_until"] or "")[:10],
                    r["note"] or ""])
    name = (ent.get("short_name") or ent.get("legal_name") or entity_id).replace(" ", "-").lower()
    return ("\ufeff" + buf.getvalue()).encode("utf-8"), f"harga-{name}.csv"


def parse_csv(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Baca CSV harga per badan usaha → baris {sku, sell_price, valid_from, ...}.

    Menerima berkas hasil ekspor sendiri (7 kolom) maupun berkas ringkas
    (`sku;harga`). Kolom harga yang KOSONG berarti “jangan diubah”, bukan nol —
    kalau tidak, sekali impor bisa menghapus seluruh harga khusus.
    """
    from services.csv_money import parse_money, sniff_delimiter
    body = (text or "").lstrip("\ufeff")
    if not body.strip():
        return [], ["Berkas kosong."]
    delim = sniff_delimiter(body.splitlines()[0])
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    reader = csv.reader(io.StringIO(body), delimiter=delim)
    for i, cells in enumerate(reader, start=1):
        if not cells or not any((c or "").strip() for c in cells):
            continue
        head = (cells[0] or "").strip().lower()
        if i == 1 and head in ("sku", "kode", "kode_sku"):
            continue                          # baris judul
        sku = (cells[0] or "").strip()
        if not sku:
            errors.append(f"Baris {i}: SKU kosong.")
            continue
        # Kolom harga: berkas ekspor kami = kolom ke-4 (harga_entitas);
        # berkas ringkas `sku;harga` = kolom ke-2.
        price_cell = ""
        if len(cells) >= 4 and (cells[3] or "").strip():
            price_cell = cells[3]
        elif len(cells) == 2 and (cells[1] or "").strip():
            price_cell = cells[1]
        elif len(cells) == 3 and (cells[2] or "").strip():
            price_cell = cells[2]
        if not str(price_cell).strip():
            continue                          # tanpa harga = tidak diubah
        try:
            price = parse_money(price_cell)
        except ValueError:
            errors.append(f"Baris {i}: harga '{price_cell}' bukan angka.")
            continue
        rows.append({"sku": sku, "sell_price": price,
                     "valid_from": (cells[4].strip() if len(cells) > 4 else ""),
                     "valid_until": (cells[5].strip() if len(cells) > 5 else ""),
                     "note": (cells[6].strip() if len(cells) > 6 else "impor CSV")})
    return rows, errors


async def import_rows(entity_id: str, rows: List[Dict[str, Any]],
                      actor_name: str) -> Dict[str, Any]:
    """Terapkan baris impor per SKU. Tidak menghapus apa pun: record lama ditutup
    otomatis oleh `create_price` sehingga riwayat harga tetap utuh."""
    skus = [str(r.get("sku") or "").strip().upper() for r in rows if r.get("sku")]
    prods = await db.products.find({"sku": {"$in": skus}}, {"_id": 0}).to_list(5000)
    by_sku = {str(p.get("sku", "")).upper(): p for p in prods}
    applied, errors = 0, []
    for r in rows:
        sku = str(r.get("sku") or "").strip().upper()
        p = by_sku.get(sku)
        if not p:
            errors.append(f"SKU '{sku}' tidak ada di master produk — dilewati.")
            continue
        try:
            await create_price({"product_id": p["id"], "sell_price": r.get("sell_price"),
                                "valid_from": r.get("valid_from") or "",
                                "valid_until": r.get("valid_until") or "",
                                "note": r.get("note") or "impor CSV"},
                               entity_id, actor_name)
            applied += 1
        except ValueError as exc:
            errors.append(f"SKU '{sku}': {exc}")
    return {"applied": applied, "skipped": len(rows) - applied,
            "errors": errors[:50], "total_rows": len(rows)}
