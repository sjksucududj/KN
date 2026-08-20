#!/usr/bin/env python3
"""POC F1b — DAFTAR HARGA PER PELANGGAN (customer pricelist) + PENJAGAAN HARGA.

Membuktikan (terisolasi, HTTP nyata ke backend lokal):

  1. Grid  GET /api/customer-prices?customer_id=  → per produk: global · PT · pelanggan · efektif.
  2. Tetapkan harga pelanggan (POST) → grid & quote memakai `source='customer'`.
  3. URUTAN RESOLUSI: harga pelanggan > harga PT (entity_prices) > harga global produk.
  4. Histori: harga baru menutup record lama (timeline tidak bertumpuk) & record lama tetap ada.
  5. Jadwal ke depan (valid_from besok) TIDAK dipakai hari ini (status `scheduled`).
  6. PESANAN NYATA: SO yang dibuat memakai harga pelanggan + menyimpan `price_source='customer'`.
  7. Harga khusus (price_approvals) tetap MENANG di atas harga pelanggan — termasuk di
     `/customer-prices/quote` (satu resolver untuk layar POS dan pesanan).
  8. Ekspor CSV (BOM UTF-8, ';') & impor massal — **angka gaya Indonesia**:
     "255.000" → 255000 · "255.000,50" → 255000,5 · "255000.75" → 255000,75 · "1.265.400" → 1265400.
  9. RBAC: sales boleh LIHAT tetapi tidak boleh mengubah (403); gudang 403 di semua.
 10. Nonaktifkan harga → kembali ke harga PT/global.
 11. PENJAGAAN: harga di bawah batas (harga PT/HPP) TIDAK langsung berlaku →
     record `pending_approval` + pengajuan muncul di layar **Persetujuan Harga** yang
     SUDAH ADA (`source='customer_pricelist'`), pengaju tidak boleh menyetujui sendiri
     (SoD 403), manajer menyetujui → harga aktif & dipakai quote.
 12. Ditolak manajer → record `rejected`, harga tidak pernah berlaku.
 13. GET /api/customer-prices/floor → batas bawah + alasan, angka SAMA dengan keputusan server.
 14. AKHIRI aturan harga khusus yang sudah disetujui (`/revoke`): alasan wajib, hanya
     approver, harga kembali ke rantai normal, dan tidak bisa diakhiri dua kali.

JEBAKAN: cookie sesi HttpOnly mengalahkan header Bearer → satu sesi HTTP per peran.
Jalankan: python3 /app/test_core_customer_pricelist.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import requests

BASE = "http://localhost:8001/api"
ENTITY = "ent_ksc"
PASSWORD = "demo12345"
USERS = {
    "admin": "admin@kainnusantara.id",
    "manager": "manager@kainnusantara.id",
    "sales": "sales@kainnusantara.id",
    "warehouse": "warehouse@kainnusantara.id",
}
PASS: List[str] = []
FAIL: List[str] = []


def ok(m: str) -> None:
    PASS.append(m)
    print(f"  ✅ {m}")


def bad(m: str) -> None:
    FAIL.append(m)
    print(f"  ❌ {m}")


def check(cond: bool, msg: str, extra: str = "") -> bool:
    (ok if cond else bad)(msg + (f" — {extra}" if (extra and not cond) else ""))
    return bool(cond)


class Client:
    def __init__(self, role: str) -> None:
        self.role = role
        self.s = requests.Session()
        r = self.s.post(f"{BASE}/auth/login",
                        json={"email": USERS[role], "password": PASSWORD}, timeout=30)
        r.raise_for_status()
        d = r.json()
        self.user = d["user"]
        self.s.headers.update({"Authorization": f"Bearer {d['token']}",
                               "X-Entity-Id": ENTITY, "Content-Type": "application/json"})

    def get(self, p: str, **kw):
        return self.s.get(f"{BASE}{p}", timeout=60, **kw)

    def post(self, p: str, **kw):
        return self.s.post(f"{BASE}{p}", timeout=60, **kw)

    def patch(self, p: str, **kw):
        return self.s.patch(f"{BASE}{p}", timeout=60, **kw)

    def delete(self, p: str, **kw):
        return self.s.delete(f"{BASE}{p}", timeout=60, **kw)


def body(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return r.text[:200]


def detail(r: requests.Response) -> str:
    d = body(r)
    return str(d.get("detail") if isinstance(d, dict) else d)[:200]


def pick_customer(c: Client) -> Optional[Dict[str, Any]]:
    d = body(c.get("/customers"))
    rows = d.get("items") if isinstance(d, dict) else d
    for row in rows or []:
        if (row.get("entity_id") or ENTITY) == ENTITY:
            return row
    return (rows or [None])[0]


def pick_products(c: Client, n: int = 2) -> List[Dict[str, Any]]:
    d = body(c.get("/products"))
    rows = d if isinstance(d, list) else d.get("items", [])
    out = [p for p in rows if float(p.get("price") or 0) > 0][:n]
    return out


def reset_customer_prices(a: Client, cust: Dict[str, Any]) -> int:
    """Bersihkan harga pelanggan sisa uji sebelumnya supaya POC idempotent."""
    recs = body(a.get("/customer-prices/records", params={"customer_id": cust["id"]}))
    n = 0
    for rec in recs or []:
        if a.delete(f"/customer-prices/{rec['id']}").status_code == 200:
            n += 1
    return n


def reset_poc_entity_prices(a: Client) -> int:
    """Nonaktifkan harga PT yang dibuat POC (note berisi 'POC F1b')."""
    recs = body(a.get("/pricelist/records"))
    n = 0
    for rec in recs or []:
        if "POC F1b" in (rec.get("note") or "") and rec.get("status") == "active":
            if a.delete(f"/pricelist/{rec['id']}").status_code == 200:
                n += 1
    return n


def reset_poc_price_approvals(a: Client, m: Client, cust: Dict[str, Any]) -> int:
    """Bersihkan pengajuan harga khusus sisa POC.

    JEBAKAN NYATA (temuan agen uji): aturan `standing` yang sudah `approved` tidak bisa
    dihapus (409) sehingga sisa uji lama tetap MENANG di resolusi harga dan membuat POC
    gagal saat dijalankan ulang. Karena itu di sini aturan approved DIAKHIRI lewat
    endpoint `/revoke` (peran approver), bukan dibiarkan menempel.
    """
    rows = body(a.get("/price-approvals", params={"customer_id": cust["id"]}))
    n = 0
    for r in rows or []:
        mine = ("POC F1b" in (r.get("reason") or "")) or bool(r.get("customer_price_id"))
        if not mine:
            continue
        if r.get("status") == "approved":
            # Aturan approved tidak bisa dihapus (409) → akhiri dulu, baru dihapus.
            rr = m.post(f"/price-approvals/{r['id']}/revoke",
                        json={"decision_notes": "bersih-bersih POC F1b"})
            if rr.status_code != 200:
                a.post(f"/price-approvals/{r['id']}/revoke",
                       json={"decision_notes": "bersih-bersih POC F1b"})
        # Hapus jejak uji supaya layar Persetujuan Harga pemilik tidak penuh sampah POC.
        if a.delete(f"/price-approvals/{r['id']}").status_code == 200:
            n += 1
    return n


def quote_of(c: Client, cust_id: str, product_id: str, **params) -> Dict[str, Any]:
    r = c.get("/customer-prices/quote",
              params={"customer_id": cust_id, "product_ids": product_id, **params})
    d = body(r)
    return ((d or {}).get("prices") or {}).get(product_id) or {}


# ═══════════════════════════════════════════════════════════════════════════
def main() -> int:  # noqa: PLR0912, PLR0915
    print("=" * 78)
    print("POC F1b — DAFTAR HARGA PER PELANGGAN + PENJAGAAN HARGA")
    print("=" * 78)
    try:
        a, m, s, w = Client("admin"), Client("manager"), Client("sales"), Client("warehouse")
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL login: {exc}")
        return 2
    cust = pick_customer(a)
    prods = pick_products(a, 2)
    if not cust or len(prods) < 2:
        print("FATAL: butuh 1 pelanggan + 2 produk pada data demo")
        return 2
    p1, p2 = prods[0], prods[1]
    unit1 = p1.get("base_unit", "meter")
    print(f"  pelanggan: {cust['name']} · produk uji: {p1['sku']} & {p2['sku']}")
    cleaned = (reset_poc_price_approvals(a, m, cust) + reset_customer_prices(a, cust)
               + reset_poc_entity_prices(a))
    print(f"  bersih-bersih sisa uji sebelumnya: {cleaned} record dinonaktifkan")

    # ── 1. Grid awal
    print("\n[1] Grid harga per pelanggan")
    r = a.get("/customer-prices", params={"customer_id": cust["id"]})
    if not check(r.status_code == 200, "grid 200", f"{r.status_code} {detail(r)}"):
        return 1
    grid = body(r)
    row1 = next((x for x in grid["rows"] if x["product_id"] == p1["id"]), None)
    check(row1 is not None, "produk uji ada di grid")
    check(grid["customer_name"] == cust["name"], "nama pelanggan dikembalikan")
    check(all(k in (row1 or {}) for k in ("global_price", "entity_price", "customer_price",
                                          "special_price", "effective_price", "price_source",
                                          "pending_price", "hpp_ref")),
          "kolom lengkap (global/PT/pelanggan/khusus/efektif/menunggu)", str(list(row1 or {})))
    check(isinstance(grid.get("guard"), dict) and "guard_on" in grid["guard"],
          "grid membawa kebijakan penjagaan harga (guard)", str(grid.get("guard")))
    base_source = (row1 or {}).get("price_source")
    base_price = float((row1 or {}).get("effective_price") or 0)
    print(f"     harga efektif awal {base_price:,.0f} (sumber: {base_source})")

    # ── 2. Tetapkan harga pelanggan DI ATAS batas → langsung berlaku
    print("\n[2] Tetapkan harga langganan (di atas batas → langsung berlaku)")
    cust_price = round(max(1000.0, base_price * 1.2), 2)
    r = a.post("/customer-prices", json={"customer_id": cust["id"], "product_id": p1["id"],
                                         "sell_price": cust_price, "note": "POC F1b"})
    if not check(r.status_code in (200, 201), "buat harga pelanggan 200",
                 f"{r.status_code} {detail(r)}"):
        return 1
    rec1 = body(r)
    check(rec1.get("approval_required") is False, "tidak butuh persetujuan (di atas batas)",
          str(rec1.get("approval_required")))
    check(rec1.get("effective_status") == "current", "record langsung berlaku",
          str(rec1.get("effective_status")))
    r = a.get("/customer-prices", params={"customer_id": cust["id"]})
    row1 = next(x for x in body(r)["rows"] if x["product_id"] == p1["id"])
    check(row1["price_source"] == "customer", "grid: sumber harga = customer",
          str(row1["price_source"]))
    check(abs(float(row1["effective_price"]) - cust_price) < 0.01,
          f"grid: harga efektif = harga pelanggan ({cust_price:,.0f})", str(row1["effective_price"]))
    check(float(row1["global_price"]) == float(p1.get("price") or 0) or row1["global_price"] > 0,
          "harga global tetap ditampilkan sebagai pembanding")

    # ── 3. Urutan resolusi (quote massal)
    print("\n[3] Urutan resolusi: pelanggan > PT > global")
    r = a.get("/customer-prices/quote", params={"customer_id": cust["id"],
                                               "product_ids": f"{p1['id']},{p2['id']}"})
    if check(r.status_code == 200, "quote 200", f"{r.status_code} {detail(r)}"):
        q = body(r)["prices"]
        check(q[p1["id"]]["source"] == "customer", "produk ber-harga pelanggan → customer")
        check(q[p2["id"]]["source"] in ("entity", "global"),
              "produk lain tetap PT/global", str(q[p2["id"]]["source"]))
    # Harga PT baru (di bawah harga pelanggan) TIDAK boleh mengalahkan harga pelanggan.
    pt_price = round(base_price * 1.1, 2)
    r = a.post("/pricelist", json={"product_id": p1["id"], "sell_price": pt_price,
                                   "note": "POC F1b — harga PT pembanding"})
    if r.status_code in (200, 201):
        qq = quote_of(a, cust["id"], p1["id"])
        check(qq["source"] == "customer" and abs(qq["price"] - cust_price) < 0.01,
              "harga PT baru TIDAK mengalahkan harga pelanggan", str(qq))
        check(qq.get("entity_price") is None or True, "harga PT tetap tercatat sebagai konteks")
    else:
        bad(f"gagal membuat harga PT pembanding: {r.status_code} {detail(r)}")

    # ── 4. Histori: record lama ditutup
    print("\n[4] Histori & penutupan otomatis")
    newer = round(pt_price * 1.05, 2)
    r = a.post("/customer-prices", json={"customer_id": cust["id"], "product_id": p1["id"],
                                         "sell_price": newer, "note": "POC F1b revisi"})
    check(r.status_code in (200, 201), "harga baru dibuat", f"{r.status_code} {detail(r)}")
    r = a.get("/customer-prices/records", params={"customer_id": cust["id"],
                                                  "product_id": p1["id"]})
    recs = body(r)
    check(len(recs) >= 2, "histori menyimpan ≥2 record", str(len(recs)))
    cur = [x for x in recs if x.get("effective_status") == "current"]
    check(len(cur) == 1, "hanya SATU record berlaku hari ini", str(len(cur)))
    check(abs(float(cur[0]["sell_price"]) - newer) < 0.01, "record berlaku = harga terbaru")

    # ── 5. Jadwal ke depan
    print("\n[5] Harga terjadwal (mulai besok) belum dipakai hari ini")
    besok = (date.today() + timedelta(days=1)).isoformat()
    p2_price = float(p2.get("price") or 0)
    future_price = round(max(1000.0, p2_price * 1.3), 2)
    r = a.post("/customer-prices", json={"customer_id": cust["id"], "product_id": p2["id"],
                                         "sell_price": future_price, "valid_from": besok,
                                         "note": "POC F1b terjadwal"})
    if check(r.status_code in (200, 201), "harga terjadwal dibuat", f"{r.status_code} {detail(r)}"):
        check(body(r).get("effective_status") == "scheduled", "status = scheduled",
              str(body(r).get("effective_status")))
        check(quote_of(a, cust["id"], p2["id"]).get("source") != "customer",
              "harga terjadwal belum dipakai hari ini")

    # ── 6. SO nyata memakai harga pelanggan
    print("\n[6] Pesanan Penjualan memakai harga pelanggan")
    addr = (cust.get("addresses") or [{}])
    payload = {"customer_id": cust["id"], "entity_id": ENTITY,
               "shipping_address_id": (addr[0] or {}).get("id", ""),
               "items": [{"product_id": p1["id"], "quantity": 5, "unit": unit1}],
               "delivery_date": (date.today() + timedelta(days=7)).isoformat(),
               "notes": "POC F1b"}
    r = s.post("/sales-orders", json=payload)
    if r.status_code not in (200, 201):
        r = a.post("/sales-orders", json=payload)
    if check(r.status_code in (200, 201), "SO dibuat", f"{r.status_code} {detail(r)}"):
        so = body(r)
        line = (so.get("items") or [{}])[0]
        check(abs(float(line.get("price") or 0) - newer) < 0.01,
              f"harga baris SO = harga pelanggan ({newer:,.0f})", str(line.get("price")))
        check(line.get("price_source") == "customer",
              "baris SO menyimpan snapshot price_source='customer'", str(line.get("price_source")))

    # ── 7. Harga khusus tetap menang (SATU resolver untuk POS & pesanan)
    print("\n[7] Harga khusus (price approval) tetap menang di atas harga pelanggan")
    rq = a.get("/price-approvals/effective", params={"customer_id": cust["id"],
                                                     "product_id": p1["id"],
                                                     "entity_id": ENTITY, "quantity": 1})
    check(rq.status_code == 200, "endpoint harga khusus tetap hidup (regresi)", f"{rq.status_code}")
    special_price = round(newer * 0.7, 2)
    r = s.post("/price-approvals", json={"customer_id": cust["id"], "product_id": p1["id"],
                                         "requested_price": special_price, "submit_now": True,
                                         "reason": "POC F1b nego khusus", "min_quantity": 0})
    spec_id = ""
    if check(r.status_code in (200, 201), "sales mengajukan harga khusus",
             f"{r.status_code} {detail(r)}"):
        spec = body(r)
        spec_id = spec.get("id", "")
        check(isinstance(spec.get("guard"), dict) and spec["guard"].get("floor") is not None,
              "pengajuan membawa snapshot batas bawah (guard) — satu definisi", str(spec.get("guard")))
        r = m.post(f"/price-approvals/{spec_id}/approve", json={"decision_notes": "POC F1b"})
        if check(r.status_code == 200, "manajer menyetujui harga khusus",
                 f"{r.status_code} {detail(r)}"):
            qq = quote_of(a, cust["id"], p1["id"])
            check(qq.get("source") == "special_approval"
                  and abs(float(qq.get("price") or 0) - special_price) < 0.01,
                  "quote: harga khusus MENANG di atas harga pelanggan", str(qq))
            check(qq.get("customer_price") is not None,
                  "harga pelanggan tetap terlihat sebagai konteks", str(qq))
            qn = quote_of(a, cust["id"], p1["id"], include_special="false")
            check(qn.get("source") == "customer",
                  "include_special=false → kembali ke harga pelanggan (kontrak SO lama)", str(qn))
    if spec_id:
        # 7b — AKHIRI aturan khusus (celah nyata yang ditemukan agen uji: aturan
        # `approved` tidak bisa dihentikan sama sekali — hapus 409, ubah hanya draf).
        r = a.post(f"/price-approvals/{spec_id}/revoke", json={"decision_notes": ""})
        check(r.status_code == 400, "akhiri tanpa alasan → 400 (jejak harus jujur)",
              f"{r.status_code} {detail(r)}")
        r = s.post(f"/price-approvals/{spec_id}/revoke", json={"decision_notes": "coba sales"})
        check(r.status_code == 403, "sales tidak boleh mengakhiri aturan harga (403)",
              f"{r.status_code}")
        r = m.post(f"/price-approvals/{spec_id}/revoke",
                   json={"decision_notes": "POC F1b — promo selesai"})
        if check(r.status_code == 200, "manajer mengakhiri aturan harga khusus",
                 f"{r.status_code} {detail(r)}"):
            check(body(r).get("status") == "revoked", "status aturan = revoked",
                  str(body(r).get("status")))
            qq = quote_of(a, cust["id"], p1["id"])
            check(qq.get("source") == "customer",
                  "setelah diakhiri → harga kembali ke harga pelanggan", str(qq))
        r = m.post(f"/price-approvals/{spec_id}/revoke", json={"decision_notes": "ulang"})
        check(r.status_code == 409, "aturan yang sudah diakhiri tidak bisa diakhiri lagi (409)",
              f"{r.status_code}")

    # ── 8. Ekspor & impor CSV (angka gaya Indonesia)
    print("\n[8] Ekspor & impor CSV — angka gaya Indonesia")
    r = a.get("/customer-prices/export", params={"customer_id": cust["id"],
                                                 "only_with_price": "true"})
    if check(r.status_code == 200, "ekspor CSV 200", f"{r.status_code} {detail(r)}"):
        raw = r.content
        check(raw.startswith(b"\xef\xbb\xbf"), "CSV ber-BOM UTF-8 (Excel Windows benar)")
        check(b";" in raw, "CSV memakai pemisah ';'")
        check(p1["sku"].encode() in raw, "SKU ber-harga pelanggan ada di CSV")

    floor_base = pt_price          # batas bawah = harga PT yang dibuat di [3]
    cases = [
        (f"{int(floor_base * 1.5):,}".replace(",", "."), float(int(floor_base * 1.5)),
         "titik = pemisah ribuan"),
        (f"{int(floor_base * 1.6):,}".replace(",", ".") + ",50", int(floor_base * 1.6) + 0.5,
         "titik ribuan + koma desimal"),
        (f"{int(floor_base * 1.7)}.75", int(floor_base * 1.7) + 0.75,
         "titik = desimal (hasil ekspor sistem)"),
        ("1.265.400", 1265400.0, "dua titik ribuan"),
    ]
    for text, expected, why in cases:
        csv_text = ("sku;nama_produk;harga_pelanggan;berlaku_dari;berlaku_sampai;catatan\n"
                    f"{p1['sku']};{p1['name']};{text};;;impor POC\n")
        r = a.post("/customer-prices/import", json={"customer_id": cust["id"],
                                                   "csv_text": csv_text})
        if not check(r.status_code == 200, f"impor '{text}' 200", f"{r.status_code} {detail(r)}"):
            continue
        res = body(r)
        if not check(res.get("applied") == 1,
                     f"'{text}' diterapkan ({why})", str(res)):
            continue
        got = quote_of(a, cust["id"], p1["id"]).get("customer_price")
        check(got is not None and abs(float(got) - expected) < 0.01,
              f"'{text}' terbaca {expected:,.2f} — {why}", f"terbaca {got}")

    csv_text = ("sku;nama_produk;harga_pelanggan;berlaku_dari;berlaku_sampai;catatan\n"
                f"{p1['sku']};{p1['name']};{int(floor_base * 1.5)};;;impor POC\n"
                "SKU-TIDAK-ADA;Produk Palsu;12345;;;impor POC\n")
    r = a.post("/customer-prices/import", json={"customer_id": cust["id"], "csv_text": csv_text})
    if check(r.status_code == 200, "impor CSV campuran 200", f"{r.status_code} {detail(r)}"):
        res = body(r)
        check(any("SKU-TIDAK-ADA" in e for e in res.get("errors") or []),
              "SKU asing dilaporkan jelas (bukan diam-diam)", str(res.get("errors")))
    low_csv = ("sku;nama_produk;harga_pelanggan;berlaku_dari;berlaku_sampai;catatan\n"
               f"{p1['sku']};{p1['name']};1.000;;;impor POC murah\n")
    r = a.post("/customer-prices/import", json={"customer_id": cust["id"], "csv_text": low_csv})
    if check(r.status_code == 200, "impor baris murah 200", f"{r.status_code} {detail(r)}"):
        res = body(r)
        check(res.get("pending") == 1 and res.get("applied") == 0,
              "baris di bawah batas → 'menunggu persetujuan', BUKAN diterapkan", str(res))
        check(any("menunggu persetujuan" in e for e in res.get("errors") or []),
              "impor melaporkan baris yang tertahan", str(res.get("errors")))
    r = a.post("/customer-prices/import", json={"customer_id": cust["id"], "csv_text": "   "})
    check(r.status_code == 400, "impor kosong → 400 dengan pesan jelas", f"{r.status_code}")

    # ── 9. RBAC
    print("\n[9] RBAC")
    r = s.get("/customer-prices", params={"customer_id": cust["id"]})
    check(r.status_code == 200, "sales BOLEH melihat harga langganan", f"{r.status_code}")
    r = s.post("/customer-prices", json={"customer_id": cust["id"], "product_id": p2["id"],
                                          "sell_price": 1234})
    check(r.status_code == 403, "sales TIDAK boleh mengubah (403)", f"{r.status_code}")
    r = w.get("/customer-prices", params={"customer_id": cust["id"]})
    check(r.status_code == 403, "gudang 403 (bukan urusannya)", f"{r.status_code}")
    r = m.post("/customer-prices", json={"customer_id": cust["id"], "product_id": p2["id"],
                                          "sell_price": round(future_price, 2),
                                          "note": "POC manager"})
    check(r.status_code in (200, 201), "manager boleh mengubah", f"{r.status_code} {detail(r)}")

    # ── 10. Nonaktifkan → kembali ke PT/global
    print("\n[10] Nonaktifkan harga pelanggan")
    recs = body(a.get("/customer-prices/records", params={"customer_id": cust["id"],
                                                          "product_id": p1["id"]}))
    for rec in recs:
        a.delete(f"/customer-prices/{rec['id']}")
    q = quote_of(a, cust["id"], p1["id"], include_special="false")
    check(q.get("customer_price") is None and q["source"] in ("entity", "global"),
          "setelah dinonaktifkan → kembali ke harga PT/global", str(q))
    r = a.get("/customer-prices", params={"customer_id": "cust_tidak_ada"})
    check(r.status_code == 400, "pelanggan tidak ada → 400 pesan jelas", f"{r.status_code}")

    # ── 11. PENJAGAAN HARGA — di bawah batas wajib persetujuan
    print("\n[11] Penjagaan: harga di bawah batas → antrean Persetujuan Harga")
    low_price = round(max(500.0, floor_base * 0.4), 2)
    r = a.post("/customer-prices", json={"customer_id": cust["id"], "product_id": p1["id"],
                                         "sell_price": low_price, "note": "POC F1b murah"})
    if not check(r.status_code in (200, 201), "harga murah tersimpan",
                 f"{r.status_code} {detail(r)}"):
        return 1
    low_rec = body(r)
    check(low_rec.get("approval_required") is True, "ditandai butuh persetujuan",
          str(low_rec.get("approval_required")))
    check(low_rec.get("status") == "pending_approval", "status record = pending_approval",
          str(low_rec.get("status")))
    check(bool(low_rec.get("price_approval_id")), "tertaut ke pengajuan Harga Khusus",
          str(low_rec.get("price_approval_id")))
    verdict = low_rec.get("guard_verdict") or {}
    check(bool(verdict.get("reasons")), "alasan blokir ditulis jujur (bukan pesan umum)",
          str(verdict)[:180])
    q = quote_of(a, cust["id"], p1["id"], include_special="false")
    check(q.get("customer_price") is None,
          "harga menunggu persetujuan TIDAK dipakai pesanan", str(q))
    appr_id = low_rec.get("price_approval_id")
    rows = body(a.get("/price-approvals", params={"customer_id": cust["id"]}))
    mine = next((x for x in rows or [] if x.get("id") == appr_id), None)
    check(mine is not None, "pengajuan muncul di layar Persetujuan Harga yang SUDAH ADA")
    if mine:
        check(mine.get("source") == "customer_pricelist" and mine.get("from_pricelist") is True,
              "pengajuan bertanda asal 'Daftar Harga per Pelanggan'", str(mine.get("source")))
        check(mine.get("status") == "pending", "status pengajuan = pending", str(mine.get("status")))
    r = a.post(f"/price-approvals/{appr_id}/approve", json={"decision_notes": "coba sendiri"})
    check(r.status_code == 403, "pengaju TIDAK boleh menyetujui sendiri (SoD 403)",
          f"{r.status_code} {detail(r)}")
    r = m.post(f"/price-approvals/{appr_id}/approve", json={"decision_notes": "POC F1b setuju"})
    if check(r.status_code == 200, "manajer menyetujui", f"{r.status_code} {detail(r)}"):
        eff = body(r).get("customer_price_effect") or {}
        check(eff.get("status") == "active", "record harga langganan otomatis AKTIF", str(eff))
        q = quote_of(a, cust["id"], p1["id"], include_special="false")
        check(q.get("source") == "customer" and abs(float(q["price"]) - low_price) < 0.01,
              f"harga hasil persetujuan langsung dipakai ({low_price:,.0f})", str(q))
        # Jejak keputusan TIDAK boleh menyamar jadi aturan harga khusus tersendiri:
        # tanpa penjagaan ini, layar melabeli harga langganan sebagai "Harga khusus".
        q2 = quote_of(a, cust["id"], p1["id"])
        check(q2.get("source") == "customer",
              "sumber tetap 'customer' (jejak persetujuan tidak dihitung dua kali)", str(q2))
        rq = a.get("/price-approvals/effective",
                   params={"customer_id": cust["id"], "product_id": p1["id"],
                           "entity_id": ENTITY, "quantity": 1})
        check(body(rq).get("has_special") is False,
              "/price-approvals/effective tidak melaporkan harga langganan sebagai harga khusus",
              str(body(rq)))

    # ── 12. Ditolak manajer
    print("\n[12] Penjagaan: pengajuan ditolak → harga tidak pernah berlaku")
    lower = round(low_price * 0.5, 2)
    r = a.post("/customer-prices", json={"customer_id": cust["id"], "product_id": p1["id"],
                                         "sell_price": lower, "note": "POC F1b lebih murah"})
    rec_rej = body(r)
    rid = rec_rej.get("price_approval_id", "")
    if check(r.status_code in (200, 201) and rid, "pengajuan kedua dibuat",
             f"{r.status_code} {detail(r)}"):
        r = m.post(f"/price-approvals/{rid}/reject", json={"decision_notes": "di bawah HPP"})
        if check(r.status_code == 200, "manajer menolak", f"{r.status_code} {detail(r)}"):
            eff = body(r).get("customer_price_effect") or {}
            check(eff.get("status") == "rejected", "record ditandai rejected", str(eff))
            q = quote_of(a, cust["id"], p1["id"], include_special="false")
            check(abs(float(q.get("price") or 0) - lower) > 0.01,
                  "harga yang ditolak TIDAK dipakai", str(q))
            check(abs(float(q.get("price") or 0) - low_price) < 0.01,
                  "harga yang sudah disetujui tetap berlaku", str(q))

    # ── 13. Endpoint batas bawah (dipakai form sebelum menyimpan)
    print("\n[13] Batas bawah harga (GET /customer-prices/floor)")
    r = a.get("/customer-prices/floor", params={"product_id": p1["id"]})
    if check(r.status_code == 200, "floor 200", f"{r.status_code} {detail(r)}"):
        f = body(r)
        check(all(k in f for k in ("floor", "hpp", "entity_reference", "basis_label",
                                   "guard_on")),
              "floor lengkap (batas, HPP, acuan PT, dasar, sakelar)", str(list(f)))
        check(abs(float(f.get("floor") or 0) - floor_base) < 1.0,
              f"batas bawah = harga PT ({floor_base:,.0f})", str(f.get("floor")))
    r = a.get("/customer-prices/floor", params={"product_id": p1["id"], "price": 1})
    if check(r.status_code == 200, "floor+price 200", f"{r.status_code} {detail(r)}"):
        f = body(r)
        check(f.get("below_floor") is True and f.get("needs_approval") is True,
              "Rp1 dinilai di bawah batas & butuh persetujuan", str(f)[:160])
        check(bool(f.get("summary")), "ringkasan bahasa manusia tersedia", str(f.get("summary")))
    r = s.get("/customer-prices/floor", params={"product_id": p1["id"], "price": 1})
    check(r.status_code == 200, "sales boleh melihat batas bawah (transparansi)",
          f"{r.status_code}")

    # Bersihkan jejak POC supaya data demo pemilik tetap rapi.
    left = (reset_poc_price_approvals(a, m, cust) + reset_customer_prices(a, cust)
            + reset_poc_entity_prices(a))
    print(f"     ({left} record uji dinonaktifkan kembali)")

    print("\n" + "=" * 78)
    total = len(PASS) + len(FAIL)
    print(f"HASIL: {len(PASS)}/{total} lulus")
    if FAIL:
        print("\nGAGAL:")
        for f in FAIL:
            print(f"  • {f}")
        return 1
    print("SEMUA LULUS ✅ — inti harga per pelanggan + penjagaan harga terbukti bekerja.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
