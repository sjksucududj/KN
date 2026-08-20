"""F1b (D-14) — **Daftar Harga per Pelanggan** (customer pricelist) dengan histori,
tanggal efektif, dan **penjagaan harga** yang menyatu dengan fitur Harga Khusus.

Mengapa ada: `entity_prices` (F1a) menjawab “harga jual PT ini berapa”, dan
`price_approvals` menjawab “boleh turun harga untuk SATU order ini?”. Yang belum ada:
**harga langganan** — kesepakatan harga tetap untuk SATU pelanggan atas SATU produk
(mis. reseller besar) yang berlaku otomatis di setiap pesanan tanpa persetujuan ulang.

URUTAN RESOLUSI HARGA (keputusan pemilik):
    harga khusus disetujui  →  harga pelanggan  →  harga PT (entity_prices)  →  harga global
Harga khusus (`price_approvals`) tetap di puncak karena itu keputusan sadar yang
disetujui manajemen; `include_special=True` dipakai layar POS/keranjang & grid agar
angka di layar SAMA dengan angka yang tersimpan di pesanan.

PENJAGAAN HARGA (keputusan pemilik 2026-08-10):
    Harga langganan yang jatuh **di bawah harga PT / biaya pokok** tidak langsung
    berlaku. Record disimpan `pending_approval` dan sebuah pengajuan **Harga Khusus**
    dibuka di koleksi `price_approvals` (mesin persetujuan yang SUDAH ADA, bukan alur
    baru). Saat manajer menyetujui → record diaktifkan; ditolak → record ditandai
    ditolak. Batas bawahnya dihitung `price_guard_service` — SATU definisi untuk
    seluruh sistem.

Koleksi: `customer_prices` (prefix `cpr_`) — SCOPED via `entity_id`.
  {id, entity_id, customer_id, customer_name, product_id, sku, product_name,
   sell_price (per base unit), currency, valid_from, valid_until, is_listed,
   status (active|pending_approval|rejected|inactive), price_approval_id, guard,
   note, created_by, created_at, updated_at}

Helper tanggal/status SENGAJA dipakai ulang dari `pricelist_service` supaya aturan
“mana yang berlaku hari ini” hanya punya SATU definisi di seluruh sistem.
"""
import csv
import io
from typing import Any, Dict, List, Optional, Tuple

from core_utils import new_id, now_iso, safe_doc
from db import db
from services import price_approval_service as pas
from services import price_guard_service as guard
from services import pricelist_service as ep

PREFIX = "cpr"
COLL = "customer_prices"

STATUS_ACTIVE = "active"
STATUS_PENDING = "pending_approval"
STATUS_REJECTED = "rejected"
STATUS_INACTIVE = "inactive"

CSV_COLUMNS = ("sku", "product_name", "sell_price", "valid_from", "valid_until", "note")

STATUS_LABEL = {
    STATUS_ACTIVE: "Berlaku",
    STATUS_PENDING: "Menunggu persetujuan",
    STATUS_REJECTED: "Ditolak",
    STATUS_INACTIVE: "Nonaktif",
}


def decorate(r: Dict[str, Any]) -> Dict[str, Any]:
    """Field turunan untuk layar. Status persetujuan TIDAK boleh menyamar sebagai
    'berlaku' — record yang menunggu keputusan ditulis apa adanya."""
    if not r:
        return r
    r = ep.decorate(dict(r))
    st = r.get("status")
    if st == STATUS_PENDING:
        r["effective_status"] = STATUS_PENDING
        r["is_current"] = False
    elif st == STATUS_REJECTED:
        r["effective_status"] = STATUS_REJECTED
        r["is_current"] = False
    r["status_label"] = STATUS_LABEL.get(r.get("effective_status") or st or "", "")
    return r


# ─── Resolusi harga ────────────────────────────────────────────────
async def _customer_candidates(entity_id: str, customer_id: str,
                               product_ids: List[str], as_of: str) -> Dict[str, Dict[str, Any]]:
    """Record harga pelanggan yang BERLAKU per produk (valid_from terbesar)."""
    if not (entity_id and entity_id != "all") or not customer_id or not product_ids:
        return {}
    rows = await db[COLL].find(
        {"entity_id": entity_id, "customer_id": customer_id,
         "product_id": {"$in": list(dict.fromkeys(product_ids))}, "status": STATUS_ACTIVE},
        {"_id": 0}).to_list(10000)
    by_pid: Dict[str, List[Dict[str, Any]]] = {}
    for r in ep._active_candidates(rows, as_of):  # noqa: SLF001 — satu definisi "berlaku"
        by_pid.setdefault(r["product_id"], []).append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for pid, cand in by_pid.items():
        # SATU definisi "harga mana yang menang" (lihat pricelist_service.pick_best):
        # tanggal berlaku terbaru → yang dibuat paling akhir. Tanpa ini, dua harga
        # yang ditetapkan pada hari yang sama membuat harga LAMA bisa dipakai.
        out[pid] = ep.pick_best(cand)
    return out


async def _pending_candidates(entity_id: str, customer_id: str,
                              product_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Record yang MENUNGGU persetujuan (untuk ditampilkan jujur di grid)."""
    if not (entity_id and customer_id and product_ids):
        return {}
    rows = await db[COLL].find(
        {"entity_id": entity_id, "customer_id": customer_id,
         "product_id": {"$in": list(dict.fromkeys(product_ids))}, "status": STATUS_PENDING},
        {"_id": 0}).sort("created_at", -1).to_list(5000)
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        out.setdefault(r["product_id"], r)
    return out


async def resolve_many(entity_id: Optional[str], customer_id: Optional[str],
                       product_ids: List[str],
                       products_map: Optional[Dict[str, Any]] = None,
                       as_of: Optional[str] = None, *,
                       include_special: bool = False,
                       quantity: Optional[float] = None,
                       quantity_map: Optional[Dict[str, float]] = None,
                       ) -> Dict[str, Dict[str, Any]]:
    """Harga jual EFEKTIF per produk untuk satu pelanggan (rantai penuh).

    Return per product_id:
      {price, source: 'special_approval'|'customer'|'entity'|'global', record_id,
       global_price, entity_price, customer_price, special_price, price_approval_id,
       min_quantity, valid_until}

    `include_special=False` (bawaan) menjaga kontrak lama pembuatan SO: harga khusus
    hanya dipakai bila `price_approval_id` dikirim sadar oleh pembuat pesanan.
    """
    as_of = as_of or now_iso()
    products_map = products_map or {}
    ids = list(dict.fromkeys(product_ids or []))
    base = await ep.resolve_many(entity_id, ids, products_map, as_of)   # PT → global
    cust = await _customer_candidates(entity_id or "", customer_id or "", ids, as_of)
    spec: Dict[str, Dict[str, Any]] = {}
    if include_special:
        qmap = dict(quantity_map or {})
        if quantity is not None:
            for pid in ids:
                qmap.setdefault(pid, float(quantity))
        spec = await pas.standing_for(entity_id or "", customer_id or "", ids,
                                     as_of=as_of, quantity_map=qmap)
    out: Dict[str, Dict[str, Any]] = {}
    for pid in ids:
        b = base.get(pid) or {}
        glob = float((products_map.get(pid) or {}).get("price", 0) or 0)
        row: Dict[str, Any] = {
            "price": float(b.get("price", glob) or 0),
            "source": b.get("source", "global"),
            "record_id": b.get("record_id"),
            "global_price": glob,
            "entity_price": (float(b["price"]) if b.get("source") == "entity" else None),
            "customer_price": None,
            "special_price": None,
            "price_approval_id": "",
            "min_quantity": 0.0,
        }
        c = cust.get(pid)
        if c:
            row.update({"price": round(float(c["sell_price"]), 2), "source": "customer",
                        "record_id": c["id"], "customer_price": round(float(c["sell_price"]), 2),
                        "valid_until": c.get("valid_until", "")})
        s = spec.get(pid)
        if s:
            row.update({"price": round(float(s["requested_price"]), 2),
                        "source": "special_approval",
                        "special_price": round(float(s["requested_price"]), 2),
                        "price_approval_id": s.get("id", ""),
                        "min_quantity": float(s.get("min_quantity", 0) or 0),
                        "valid_until": s.get("valid_until", "")})
        out[pid] = row
    return out


async def resolve_one(entity_id: Optional[str], customer_id: Optional[str], product_id: str,
                      product: Optional[Dict[str, Any]] = None,
                      as_of: Optional[str] = None, **kw) -> Dict[str, Any]:
    res = await resolve_many(entity_id, customer_id, [product_id],
                             {product_id: product or {}}, as_of, **kw)
    return res.get(product_id) or {"price": 0.0, "source": "global", "record_id": None}


# ─── CRUD ──────────────────────────────────────────────────────
async def _customer(entity_id: str, customer_id: str) -> Dict[str, Any]:
    cust = await db.customers.find_one({"id": customer_id}, {"_id": 0})
    if not cust:
        raise ValueError("Pelanggan tidak ditemukan")
    cent = cust.get("entity_id") or ""
    if cent and entity_id and cent != entity_id:
        raise ValueError(f"Pelanggan {cust.get('name')} bukan milik entitas ini "
                         "— pilih entitas yang sesuai.")
    return cust


async def _close_overlapping(entity_id: str, customer_id: str, product_id: str,
                             valid_from: str, exclude_id: str = "") -> int:
    """Tutup record berlaku yang bertumpuk agar timeline tidak ganda.

    Dipanggil saat record benar-benar MULAI BERLAKU (langsung aktif atau baru
    disetujui) — bukan saat pengajuan dibuat, supaya harga lama tetap dipakai selama
    pengganti masih menunggu keputusan manajer.
    """
    existing = await db[COLL].find(
        {"entity_id": entity_id, "customer_id": customer_id, "product_id": product_id,
         "status": STATUS_ACTIVE}, {"_id": 0}).to_list(500)
    closed = 0
    for r in existing:
        if exclude_id and r.get("id") == exclude_id:
            continue
        rf = r.get("valid_from") or ""
        ru = r.get("valid_until") or ""
        # `<=`: memperbaiki harga langganan di hari yang sama WAJIB menutup yang lama.
        if rf <= valid_from and (ru == "" or ru >= valid_from):
            await db[COLL].update_one({"id": r["id"]},
                                      {"$set": {"valid_until": valid_from,
                                                "updated_at": now_iso()}})
            closed += 1
    return closed


def _actor_of(actor: Any) -> Dict[str, Any]:
    """Terima dict user ATAU nama (kompatibilitas pemanggil lama)."""
    if isinstance(actor, dict):
        return actor
    return {"id": "", "name": str(actor or "")}


async def create_price(data: Dict[str, Any], entity_id: str,
                       actor: Any) -> Dict[str, Any]:
    """Tetapkan harga langganan. Bila di bawah batas bawah → menunggu persetujuan."""
    who = _actor_of(actor)
    cust = await _customer(entity_id, (data.get("customer_id") or "").strip())
    product = await db.products.find_one({"id": (data.get("product_id") or "").strip()},
                                         {"_id": 0})
    if not product:
        raise ValueError("Produk tidak ditemukan")
    price = round(float(data.get("sell_price") or 0), 2)
    if price <= 0:
        raise ValueError("Harga jual harus lebih dari 0")
    vfrom = ep._norm_dt(data.get("valid_from")) or now_iso()      # noqa: SLF001
    vuntil = ep._norm_dt(data.get("valid_until"), end_of_day=True)  # noqa: SLF001
    if vuntil and vuntil < vfrom:
        raise ValueError("Tanggal berakhir tidak boleh sebelum tanggal mulai")

    # SATU sumber penilaian "harga terlalu murah" (dipakai juga layar Harga Khusus).
    verdict = await guard.evaluate(price, entity_id, product)
    needs = bool(verdict.get("needs_approval"))

    doc = {
        "id": new_id(PREFIX), "entity_id": entity_id,
        "customer_id": cust["id"], "customer_name": cust.get("name", ""),
        "product_id": product["id"], "sku": product.get("sku", ""),
        "product_name": product.get("name", ""),
        "base_unit": product.get("base_unit", "meter"),
        "sell_price": price, "currency": "IDR",
        "valid_from": vfrom, "valid_until": vuntil,
        "is_listed": bool(data.get("is_listed", True)),
        "status": STATUS_PENDING if needs else STATUS_ACTIVE,
        "note": (data.get("note") or "").strip(),
        "price_approval_id": "",
        "guard": {k: verdict.get(k) for k in
                  ("floor", "floor_from", "threshold", "basis", "basis_label",
                   "entity_reference", "has_entity_price", "hpp", "global_price",
                   "below_floor", "gap", "gap_pct", "margin_pct", "reasons", "summary",
                   "tolerance_pct", "guard_on")},
        "created_by": who.get("name", ""), "created_by_id": who.get("id", ""),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db[COLL].insert_one(dict(doc))
    if needs:
        appr = await pas.open_for_customer_price(customer_price=doc, customer=cust,
                                                product=product, guard=verdict,
                                                requester=who)
        doc["price_approval_id"] = appr["id"]
        await db[COLL].update_one({"id": doc["id"]},
                                  {"$set": {"price_approval_id": appr["id"],
                                            "updated_at": now_iso()}})
    else:
        await _close_overlapping(entity_id, cust["id"], product["id"], vfrom,
                                 exclude_id=doc["id"])
    out = decorate(safe_doc(doc))
    out["approval_required"] = needs
    out["guard_verdict"] = verdict
    return out


async def apply_approval_decision(cp_id: str, decision: str, approval: Dict[str, Any],
                                  actor: Dict[str, Any]) -> Dict[str, Any]:
    """Efek keputusan Harga Khusus terhadap record harga langganan (dipanggil
    `price_approval_service.after_decision`)."""
    rec = await db[COLL].find_one({"id": cp_id}, {"_id": 0})
    if not rec:
        return {}
    who = _actor_of(actor)
    now = now_iso()
    if decision == "approved":
        vfrom = rec.get("valid_from") or now
        # Harga baru mulai berlaku SEKARANG bila tanggal mulainya sudah lewat saat
        # menunggu keputusan — kalau tidak, harga akan tampak "berlaku surut".
        if vfrom < now:
            vfrom = now
        await _close_overlapping(rec.get("entity_id", ""), rec.get("customer_id", ""),
                                 rec.get("product_id", ""), vfrom, exclude_id=cp_id)
        upd = {"status": STATUS_ACTIVE, "valid_from": vfrom,
               "approved_by": who.get("name", ""), "approved_at": now, "updated_at": now}
    elif decision == "revoked":
        # Aturan penopangnya diakhiri approver → harga langganan ikut berhenti
        # (dinonaktifkan), BUKAN ditandai "ditolak": ia pernah sah berlaku.
        upd = {"status": STATUS_INACTIVE, "revoked_by": who.get("name", ""),
               "revoked_at": now, "updated_at": now,
               "revoke_note": (approval or {}).get("decision_notes", "")}
    else:
        upd = {"status": STATUS_REJECTED, "rejected_by": who.get("name", ""),
               "rejected_at": now, "updated_at": now,
               "rejection_note": (approval or {}).get("decision_notes", "")}
    await db[COLL].update_one({"id": cp_id}, {"$set": upd})
    return {"customer_price_id": cp_id, "status": upd["status"],
            "product_name": rec.get("product_name", ""),
            "customer_name": rec.get("customer_name", "")}


async def patch_price(price_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    rec = await db[COLL].find_one({"id": price_id}, {"_id": 0})
    if not rec:
        raise ValueError("Harga pelanggan tidak ditemukan")
    if rec.get("status") == STATUS_PENDING and data.get("sell_price") is not None:
        raise ValueError("Harga ini masih menunggu persetujuan manajer — batalkan dulu "
                        "atau tunggu keputusannya sebelum mengubah nominal.")
    upd: Dict[str, Any] = {}
    if data.get("sell_price") is not None:
        p = round(float(data["sell_price"]), 2)
        if p <= 0:
            raise ValueError("Harga jual harus lebih dari 0")
        upd["sell_price"] = p
    if data.get("valid_until") is not None:
        upd["valid_until"] = ep._norm_dt(str(data["valid_until"]), end_of_day=True)  # noqa: SLF001
    if data.get("is_listed") is not None:
        upd["is_listed"] = bool(data["is_listed"])
    if data.get("note") is not None:
        upd["note"] = (str(data["note"]) or "").strip()
    if not upd:
        raise ValueError("Tidak ada perubahan valid untuk disimpan")
    # Nominal berubah → nilai ulang batas bawah supaya tidak ada jalan pintas
    # menaruh harga murah lewat tombol "ubah".
    if "sell_price" in upd:
        product = await db.products.find_one({"id": rec.get("product_id")}, {"_id": 0}) or {}
        verdict = await guard.evaluate(upd["sell_price"], rec.get("entity_id", ""), product)
        if verdict.get("needs_approval"):
            raise ValueError(
                "Harga baru di bawah batas bawah sehingga wajib persetujuan. "
                "Buat harga baru (bukan ubah) agar masuk antrean Persetujuan Harga. "
                + (verdict.get("summary") or ""))
        upd["guard"] = {k: verdict.get(k) for k in
                        ("floor", "floor_from", "threshold", "basis", "basis_label",
                         "entity_reference", "has_entity_price", "hpp", "global_price",
                         "below_floor", "gap", "gap_pct", "margin_pct", "reasons",
                         "summary", "tolerance_pct", "guard_on")}
    upd["updated_at"] = now_iso()
    await db[COLL].update_one({"id": price_id}, {"$set": upd})
    return decorate(safe_doc(await db[COLL].find_one({"id": price_id}, {"_id": 0})))


async def deactivate_price(price_id: str, actor: Any = "") -> Dict[str, Any]:
    rec = await db[COLL].find_one({"id": price_id}, {"_id": 0})
    if not rec:
        raise ValueError("Harga pelanggan tidak ditemukan")
    who = _actor_of(actor)
    await db[COLL].update_one({"id": price_id},
                              {"$set": {"status": STATUS_INACTIVE, "updated_at": now_iso()}})
    cancelled = 0
    if rec.get("status") == STATUS_PENDING:
        cancelled = await pas.cancel_for_customer_price(price_id, who.get("name", ""))
    return {"deactivated": True, "id": price_id, "approval_cancelled": cancelled}


async def get_record(price_id: str) -> Optional[Dict[str, Any]]:
    return safe_doc(await db[COLL].find_one({"id": price_id}, {"_id": 0}))


async def list_records(scope: Dict[str, Any], customer_id: Optional[str] = None,
                       product_id: Optional[str] = None,
                       status: Optional[str] = None) -> List[Dict[str, Any]]:
    q = dict(scope or {})
    if customer_id:
        q["customer_id"] = customer_id
    if product_id:
        q["product_id"] = product_id
    if status:
        q["status"] = status
    rows = await db[COLL].find(q, {"_id": 0}).sort(
        [("product_id", 1), ("valid_from", -1)]).to_list(5000)
    return [decorate(safe_doc(r)) for r in rows]


async def grid(entity_id: str, customer_id: str, search: str = "") -> Dict[str, Any]:
    """Satu baris per produk: harga global · PT · pelanggan · harga khusus · efektif.

    `hpp_ref` memakai HPP tersimpan pada master produk (murah, tanpa query per
    produk). Batas bawah presisi (WAC berjalan) dihitung saat membuka form harga
    lewat `/api/customer-prices/floor` — supaya grid 1.000 produk tetap ringan.
    """
    cust = await _customer(entity_id, customer_id)
    products = await db.products.find({"status": {"$ne": "inactive"}}, {"_id": 0}).to_list(1000)
    if search:
        s = search.lower()
        products = [p for p in products
                    if s in f"{p.get('name','')}{p.get('sku','')}{p.get('category','')}".lower()]
    pmap = {p["id"]: p for p in products}
    resolved = await resolve_many(entity_id, cust["id"], list(pmap), pmap,
                                  include_special=True)
    pending = await _pending_candidates(entity_id, cust["id"], list(pmap))
    cfg = await guard.settings_for(entity_id)
    rows: List[Dict[str, Any]] = []
    for p in products:
        r = resolved.get(p["id"], {})
        pend = pending.get(p["id"])
        rows.append({
            "product_id": p["id"], "sku": p.get("sku", ""),
            "product_name": p.get("name", ""), "category": p.get("category", ""),
            "base_unit": p.get("base_unit", "meter"),
            "global_price": r.get("global_price", 0.0),
            "entity_price": r.get("entity_price"),
            "customer_price": r.get("customer_price"),
            "special_price": r.get("special_price"),
            "price_approval_id": r.get("price_approval_id", ""),
            "min_quantity": r.get("min_quantity", 0.0),
            "hpp_ref": round(float(p.get("harga_pokok") or 0), 2),
            "effective_price": r.get("price", 0.0),
            "price_source": r.get("source", "global"),
            "record_id": r.get("record_id"),
            "has_customer_price": r.get("customer_price") is not None,
            "pending_price": (round(float(pend["sell_price"]), 2) if pend else None),
            "pending_id": (pend or {}).get("id", ""),
            "pending_approval_id": (pend or {}).get("price_approval_id", ""),
        })
    rows.sort(key=lambda x: (x["category"], x["product_name"]))
    return {"entity_id": entity_id, "customer_id": cust["id"],
            "customer_name": cust.get("name", ""), "rows": rows, "count": len(rows),
            "with_customer_price": sum(1 for r in rows if r["has_customer_price"]),
            "with_special_price": sum(1 for r in rows if r["special_price"] is not None),
            "pending_count": sum(1 for r in rows if r["pending_price"] is not None),
            "guard": cfg}


# ─── Ekspor / impor CSV ───────────────────────────────────────────
async def export_csv(entity_id: str, customer_id: str,
                     only_with_price: bool = False) -> Tuple[bytes, str]:
    """CSV ber-BOM UTF-8 (Excel Windows membaca huruf Indonesia dengan benar)."""
    data = await grid(entity_id, customer_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["sku", "nama_produk", "harga_pelanggan", "berlaku_dari",
                "berlaku_sampai", "catatan"])
    recs = {r["product_id"]: r for r in await list_records({"entity_id": entity_id},
                                                          customer_id=customer_id)
            if r.get("effective_status") == "current"}
    for row in data["rows"]:
        if only_with_price and not row["has_customer_price"]:
            continue
        rec = recs.get(row["product_id"]) or {}
        w.writerow([row["sku"], row["product_name"],
                    (f"{float(row['customer_price']):.2f}"
                     if row["customer_price"] is not None else ""),
                    (rec.get("valid_from") or "")[:10], (rec.get("valid_until") or "")[:10],
                    rec.get("note", "")])
    content = "\ufeff" + buf.getvalue()
    fname = f"harga-pelanggan-{data['customer_name'].replace(' ', '-').lower()}.csv"
    return content.encode("utf-8"), fname


def _parse_money(text: str) -> float:
    """Angka rupiah dari CSV — SATU definisi di `services/csv_money.py`.

    Nama lama dipertahankan agar pemanggil & uji yang sudah ada tidak berubah.
    Kasus yang dijaga (termasuk bug pertama POC: 126540.0 terbaca 1.265.400)
    ditulis lengkap di modul itu.
    """
    from services.csv_money import parse_money
    return parse_money(text)


def parse_csv(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Baca CSV (pemisah ';' atau ',') → baris {sku, sell_price, valid_from, ...}."""
    body = (text or "").lstrip("\ufeff")
    if not body.strip():
        return [], ["Berkas kosong."]
    first = body.splitlines()[0]
    delim = ";" if first.count(";") >= first.count(",") else ","
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    reader = csv.reader(io.StringIO(body), delimiter=delim)
    for i, cells in enumerate(reader, start=1):
        if not cells or not any((c or "").strip() for c in cells):
            continue
        head = (cells[0] or "").strip().lower()
        if i == 1 and head in ("sku", "kode", "kode_sku"):
            continue                      # baris judul
        if len(cells) < 3:
            errors.append(f"Baris {i}: kolom kurang (minimal sku;nama;harga).")
            continue
        sku = (cells[0] or "").strip()
        if not sku:
            errors.append(f"Baris {i}: SKU kosong.")
            continue
        if not (cells[2] or "").strip():
            continue                      # tanpa harga = tidak diubah
        try:
            price = _parse_money(cells[2])
        except ValueError:
            errors.append(f"Baris {i}: harga '{cells[2]}' bukan angka.")
            continue
        rows.append({"sku": sku, "sell_price": price,
                     "valid_from": (cells[3].strip() if len(cells) > 3 else ""),
                     "valid_until": (cells[4].strip() if len(cells) > 4 else ""),
                     "note": (cells[5].strip() if len(cells) > 5 else "impor CSV")})
    return rows, errors


async def import_rows(entity_id: str, customer_id: str, rows: List[Dict[str, Any]],
                      actor: Any) -> Dict[str, Any]:
    """Terapkan baris impor (per SKU). Tidak menghapus apa pun — hanya menambah
    record harga baru (histori tetap utuh, record lama ditutup otomatis).

    Baris yang jatuh di bawah batas bawah TIDAK diterapkan diam-diam: ia masuk
    antrean Persetujuan Harga dan dilaporkan terpisah pada `pending`.
    """
    await _customer(entity_id, customer_id)
    skus = [str(r.get("sku") or "").strip().upper() for r in rows if r.get("sku")]
    prods = await db.products.find({"sku": {"$in": skus}}, {"_id": 0}).to_list(5000)
    by_sku = {str(p.get("sku", "")).upper(): p for p in prods}
    applied, pending, errors = 0, 0, []
    for r in rows:
        sku = str(r.get("sku") or "").strip().upper()
        p = by_sku.get(sku)
        if not p:
            errors.append(f"SKU '{sku}' tidak ada di master produk — dilewati.")
            continue
        try:
            rec = await create_price({"customer_id": customer_id, "product_id": p["id"],
                                      "sell_price": r.get("sell_price"),
                                      "valid_from": r.get("valid_from") or "",
                                      "valid_until": r.get("valid_until") or "",
                                      "note": r.get("note") or "impor CSV"},
                                     entity_id, actor)
            if rec.get("approval_required"):
                pending += 1
                errors.append(f"SKU '{sku}': harga di bawah batas → menunggu persetujuan "
                              "manajer (belum berlaku).")
            else:
                applied += 1
        except ValueError as exc:
            errors.append(f"SKU '{sku}': {exc}")
    return {"applied": applied, "pending": pending,
            "skipped": len(rows) - applied - pending, "errors": errors[:50],
            "total_rows": len(rows)}
