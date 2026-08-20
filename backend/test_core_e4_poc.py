#!/usr/bin/env python3
"""POC FASE E-4 (E4.1 gudang bersama/khusus · E4.7 harga per badan usaha).

KEPUTUSAN PEMILIK yang dikunci berkas ini:
  #3 Gudang **campur**: ada gudang bersama, ada gudang KHUSUS badan usaha tertentu.
  #4 Harga master **global + override per badan usaha**; asal harga wajib berlabel.
  #5 Override dihapus → harga kembali ke global. Urutan menang:
     harga khusus disetujui → pelanggan → **badan usaha** → global.

Yang dibuktikan (dan HARUS tetap benar selamanya):

  E4.1 — GUDANG
   1. Daftar gudang **tersaring dua arah**: pengguna KSC tidak melihat gudang khusus
      Kanda, pengguna Kanda tidak melihat gudang khusus KSC.
   2. `?scope=all` (admin) melihat semuanya + tanda `usable_by_active` yang benar.
   3. Menulis ke gudang khusus badan usaha lain → **403 dengan pesan menuntun**
      (opname, transfer, PO, stok awal) — bukan 500, bukan sukses senyap.
   4. Kontrol positif: gudang **bersama** tetap boleh dipakai (pagar tidak asal tolak).
   5. Gudang tidak bisa dijadikan "khusus" bila masih menyimpan stok badan usaha
      lain → **409 menyebut jumlah roll & nama pemiliknya** (barang tidak terkurung).
      Setelah pemilik stok disertakan → boleh.
   6. Gudang BARU bawaannya **khusus badan usaha aktif** (harus sengaja dibuka).
   7. `GET /warehouses/{id}/occupancy` menjawab "isi gudang ini punya siapa".

  E4.7 — HARGA
   8. Dua badan usaha, satu produk, **harga berbeda**: Kanda memakai harga sendiri,
      KSC tetap harga global (user story 9).
   9. Grid mengirim TIGA angka + asal harga (`global` / `entity`), bukan satu angka
      yang ambigu.
  10. Harga baru **menutup** harga lama (riwayat utuh, timeline tidak bertumpuk).
  11. Harga **terjadwal** (mulai bulan depan) tidak mengubah harga hari ini.
  12. **Kembalikan ke global** melepas override tanpa menghapus riwayat.
  13. Rantai harga pesanan/POS (`/customer-prices/quote`) memakai harga badan usaha.
  14. Ekspor/impor CSV: angka gaya Indonesia terbaca benar; baris tanpa harga
      DILEWATI (satu impor tidak boleh menghapus harga khusus).

  15. **Nol residu**: seluruh data uji dibersihkan; POC aman dijalankan berulang.

Jalankan:  cd /app && python backend/test_core_e4_poc.py
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
PW = "demo12345"
ADMIN = "admin@kainnusantara.id"
SALES_KSC = "sales@kainnusantara.id"      # home ent_ksc
SALES_KANDA = "sales3@kainnusantara.id"   # home ent_kanda
WAREHOUSE = "warehouse@kainnusantara.id"

KSC, KANDA = "ent_ksc", "ent_kanda"
WH_SHARED = "wh_jakarta"        # bersama
WH_KSC = "wh_bandung"           # khusus KSC
WH_KANDA = "wh_tangerang"       # khusus Kanda
WH_SBY = "wh_surabaya"          # bersama, berisi stok KSC

PROD_TEST = "prod_denim_selvedge"   # tidak dipakai contoh harga demo
SKU_TEST = "DNM-BDG-001"
PROD_DEMO_KANDA = "prod_batik_mega"  # sudah punya harga Kanda dari seed

PASS = 0
FAIL = 0
CLEAN_WAREHOUSES: list = []
CLEAN_PRICES: list = []
CLEAN_SESSIONS: list = []


def ok(cond: bool, label: str, extra: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f"\n         → {extra}" if extra else ""))
    return bool(cond)


def login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": PW}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "Content-Type": "application/json"})
    return s


def h(entity: str) -> dict:
    return {"X-Entity-Id": entity}


def _db():
    from pymongo import MongoClient
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ.get("DB_NAME", "test_database")]


def guides(resp: requests.Response, *needles: str) -> bool:
    """Penolakan yang MENUNTUN: menyebut sebab & jalan keluar, bukan kode teknis."""
    try:
        detail = (resp.json() or {}).get("detail", "")
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(detail, str):
        return False
    return all(n.lower() in detail.lower() for n in needles)


def grid_row(sess: requests.Session, entity_id: str, product_id: str) -> dict:
    r = sess.get(f"{BASE}/api/pricelist", params={"entity_id": entity_id}, timeout=60)
    assert r.status_code == 200, f"grid {entity_id}: {r.status_code} {r.text[:200]}"
    for row in r.json().get("rows", []):
        if row["product_id"] == product_id:
            return row
    return {}


# ═══════════════════════════════════════════════════════════════════════════
def part_warehouse_visibility(admin, sales_ksc, sales_kanda) -> None:
    print("\n── E4.1 · 1-2 · gudang mana yang terlihat ────────────────────────────")
    a = sales_ksc.get(f"{BASE}/api/warehouses", timeout=30)
    b = sales_kanda.get(f"{BASE}/api/warehouses", timeout=30)
    ids_a = {w["id"] for w in (a.json() or [])}
    ids_b = {w["id"] for w in (b.json() or [])}
    ok(WH_KSC in ids_a and WH_KANDA not in ids_a,
       "pengguna KSC melihat gudang khusus KSC, TIDAK melihat gudang khusus Kanda",
       f"KSC melihat: {sorted(ids_a)}")
    ok(WH_KANDA in ids_b and WH_KSC not in ids_b,
       "pengguna Kanda melihat gudang khusus Kanda, TIDAK melihat gudang khusus KSC",
       f"Kanda melihat: {sorted(ids_b)}")
    ok(WH_SHARED in ids_a and WH_SHARED in ids_b,
       "gudang bersama terlihat oleh keduanya")

    all_r = admin.get(f"{BASE}/api/warehouses", params={"scope": "all"},
                      headers=h(KANDA), timeout=30)
    rows = {w["id"]: w for w in (all_r.json() or [])}
    ok(len(rows) >= 4, "admin ?scope=all melihat seluruh gudang", f"{len(rows)} gudang")
    ok(rows.get(WH_KSC, {}).get("usable_by_active") is False
       and rows.get(WH_KANDA, {}).get("usable_by_active") is True,
       "tanda 'boleh dipakai' benar saat admin berkonteks Kanda")
    ok(rows.get(WH_KSC, {}).get("sharing_label", "").startswith("Khusus")
       and rows.get(WH_SHARED, {}).get("sharing_label", "").startswith("Bersama"),
       "lencana mode gudang memakai kata manusia (Bersama / Khusus …)",
       f"{rows.get(WH_KSC, {}).get('sharing_label')!r}")


def part_warehouse_write_guard(admin, wh_user) -> None:
    print("\n── E4.1 · 3-4 · menulis ke gudang orang lain ─────────────────────────")
    # 3a. stock opname di gudang khusus Kanda, sebagai KSC
    r = wh_user.post(f"{BASE}/api/cycle-count/sessions", headers=h(KSC),
                     json={"warehouse_id": WH_KANDA, "name": f"poc-{uuid.uuid4().hex[:6]}"},
                     timeout=30)
    ok(r.status_code == 403 and guides(r, "khusus", "pilih gudang lain"),
       "stock opname di gudang khusus badan usaha lain → 403 menuntun",
       f"{r.status_code} {r.text[:200]}")

    # 3b. transfer dengan gudang tujuan milik badan usaha lain
    r = wh_user.post(f"{BASE}/api/transfers", headers=h(KSC), json={
        "source_warehouse_id": WH_SHARED, "dest_warehouse_id": WH_KANDA,
        "items": [{"product_id": PROD_TEST, "qty": 1}], "notes": "poc e4"}, timeout=30)
    ok(r.status_code == 403 and guides(r, "khusus"),
       "transfer ke gudang khusus badan usaha lain → 403 menuntun",
       f"{r.status_code} {r.text[:200]}")

    # 3c. PO dengan gudang penerimaan milik badan usaha lain
    r = admin.post(f"{BASE}/api/purchase-orders", headers=h(KSC), json={
        "supplier_name": "POC Supplier E4", "warehouse_id": WH_KANDA,
        "items": [{"product_id": PROD_TEST, "quantity": 5, "unit_price": 100000}],
    }, timeout=30)
    ok(r.status_code == 403 and guides(r, "khusus"),
       "PO dengan gudang penerimaan badan usaha lain → 403 menuntun",
       f"{r.status_code} {r.text[:200]}")

    # 3d. stok awal ke gudang khusus badan usaha lain
    r = admin.post(f"{BASE}/api/inventory/initial-stock", headers=h(KSC), json={
        "product_id": PROD_TEST, "warehouse_id": WH_KANDA, "quantity": 3,
        "lot": "POC-E4"}, timeout=30)
    ok(r.status_code == 403 and guides(r, "khusus"),
       "stok awal ke gudang khusus badan usaha lain → 403 menuntun",
       f"{r.status_code} {r.text[:200]}")

    # 4. kontrol positif — gudang bersama tetap boleh
    r = wh_user.post(f"{BASE}/api/cycle-count/sessions", headers=h(KSC),
                     json={"warehouse_id": WH_SHARED, "name": f"poc-{uuid.uuid4().hex[:6]}"},
                     timeout=30)
    if ok(r.status_code in (200, 201), "gudang BERSAMA tetap boleh dipakai (pagar tidak asal tolak)",
          f"{r.status_code} {r.text[:200]}"):
        CLEAN_SESSIONS.append(r.json().get("id"))


def part_dedication_guard(admin) -> None:
    print("\n── E4.1 · 5 · jangan mengurung barang orang ──────────────────────────")
    occ = admin.get(f"{BASE}/api/warehouses/{WH_SBY}/occupancy", timeout=30).json()
    owners = {o["entity_id"]: o for o in occ.get("owners", [])}
    ok(KSC in owners and owners[KSC]["rolls"] > 0,
       f"isi gudang Surabaya terbaca: {owners.get(KSC, {}).get('rolls')} roll milik KSC")

    r = admin.patch(f"{BASE}/api/warehouses/{WH_SBY}", headers=h(KANDA),
                    json={"data": {"sharing_mode": "dedicated", "entity_ids": [KANDA]}},
                    timeout=30)
    ok(r.status_code == 409 and guides(r, "roll", "terkurung"),
       "jadikan khusus padahal berisi stok badan usaha lain → 409 menyebut roll & pemilik",
       f"{r.status_code} {r.text[:250]}")

    # setelah pemilik stok disertakan → boleh
    r = admin.patch(f"{BASE}/api/warehouses/{WH_SBY}", headers=h(KANDA),
                    json={"data": {"sharing_mode": "dedicated", "entity_ids": [KANDA, KSC]}},
                    timeout=30)
    ok(r.status_code == 200 and set(r.json().get("entity_ids", [])) == {KANDA, KSC},
       "setelah pemilik stok disertakan → perubahan diterima",
       f"{r.status_code} {r.text[:200]}")

    # pulihkan ke keadaan semula (bersama)
    back = admin.patch(f"{BASE}/api/warehouses/{WH_SBY}", headers=h(KANDA),
                       json={"data": {"sharing_mode": "shared", "entity_ids": []}}, timeout=30)
    ok(back.status_code == 200 and back.json().get("sharing_mode") == "shared",
       "gudang Surabaya dipulihkan menjadi bersama (POC tidak meninggalkan jejak)")


def part_new_warehouse_default(admin, sales_ksc) -> None:
    print("\n── E4.1 · 6 · gudang baru bawaannya khusus ───────────────────────────")
    code = f"POC-{uuid.uuid4().hex[:5].upper()}"
    r = admin.post(f"{BASE}/api/warehouses", headers=h(KANDA), json={
        "code": code, "name": f"Gudang POC {code}", "city": "Semarang"}, timeout=30)
    if not ok(r.status_code in (200, 201), "gudang baru dibuat", f"{r.status_code} {r.text[:200]}"):
        return
    doc = r.json()
    CLEAN_WAREHOUSES.append(doc["id"])
    ok(doc.get("sharing_mode") == "dedicated" and doc.get("entity_ids") == [KANDA],
       "gudang baru otomatis KHUSUS badan usaha aktif (harus sengaja dibuka)",
       str({k: doc.get(k) for k in ("sharing_mode", "entity_ids")}))
    seen = {w["id"] for w in sales_ksc.get(f"{BASE}/api/warehouses", timeout=30).json()}
    ok(doc["id"] not in seen,
       "badan usaha lain langsung TIDAK melihat gudang baru itu")


# ═══════════════════════════════════════════════════════════════════════════
def part_price_isolation(admin, sales_ksc, sales_kanda) -> None:
    print("\n── E4.7 · 8-9 · satu produk, dua harga (user story 9) ────────────────")
    row_kanda = grid_row(admin, KANDA, PROD_DEMO_KANDA)
    row_ksc = grid_row(admin, KSC, PROD_DEMO_KANDA)
    ok(row_kanda.get("entity_price") not in (None, 0)
       and row_kanda.get("price_source") == "entity",
       f"Kanda memakai harga sendiri: {row_kanda.get('entity_price')} (asal: entity)")
    ok(row_ksc.get("entity_price") is None and row_ksc.get("price_source") == "global"
       and row_ksc.get("effective_price") == row_ksc.get("global_price"),
       f"KSC untuk produk yang sama tetap harga global: {row_ksc.get('effective_price')}")
    ok(row_kanda.get("effective_price") != row_ksc.get("effective_price"),
       "harga efektif kedua badan usaha BERBEDA untuk produk yang sama")
    ok(all(k in row_kanda for k in ("global_price", "entity_price", "effective_price",
                                    "price_source")),
       "grid mengirim tiga angka + asal harga (layar tidak perlu menebak)")
    # sales biasa (bukan admin) juga melihat harga badan usahanya
    q = sales_kanda.get(f"{BASE}/api/pricelist", timeout=60)
    ok(q.status_code == 200 and any(r["product_id"] == PROD_DEMO_KANDA
                                    and r["price_source"] == "entity" for r in q.json()["rows"]),
       "sales Kanda melihat harga badan usahanya di layar harga")


def part_price_lifecycle(admin) -> None:
    print("\n── E4.7 · 10-12 · tetapkan · jadwalkan · kembalikan ke global ────────")
    before = grid_row(admin, KANDA, PROD_TEST)
    ok(before.get("entity_price") is None,
       f"produk uji {SKU_TEST} awalnya ikut harga global {before.get('global_price')}")

    # 10. tetapkan harga sekarang
    r = admin.post(f"{BASE}/api/pricelist", headers=h(KANDA), json={
        "product_id": PROD_TEST, "sell_price": 158000, "entity_id": KANDA,
        "valid_from": datetime.now(timezone.utc).date().isoformat(),
        "note": "POC E-4"}, timeout=30)
    if ok(r.status_code in (200, 201), "harga badan usaha ditetapkan", f"{r.status_code} {r.text[:200]}"):
        CLEAN_PRICES.append(r.json()["id"])
    after = grid_row(admin, KANDA, PROD_TEST)
    ok(after.get("entity_price") == 158000 and after.get("effective_price") == 158000
       and after.get("price_source") == "entity",
       "harga efektif langsung memakai harga badan usaha",
       str({k: after.get(k) for k in ("entity_price", "effective_price", "price_source")}))

    # 10b. harga kedua menutup yang pertama (timeline tidak bertumpuk)
    r2 = admin.post(f"{BASE}/api/pricelist", headers=h(KANDA), json={
        "product_id": PROD_TEST, "sell_price": 162000, "entity_id": KANDA,
        "valid_from": datetime.now(timezone.utc).date().isoformat(),
        "note": "POC E-4 revisi"}, timeout=30)
    if r2.status_code in (200, 201):
        CLEAN_PRICES.append(r2.json()["id"])
    recs = admin.get(f"{BASE}/api/pricelist/records",
                     params={"product_id": PROD_TEST, "entity_id": KANDA}, timeout=30).json()
    closed = [x for x in recs if x["id"] == CLEAN_PRICES[0] and x.get("valid_until")]
    ok(bool(closed), "harga lama ditutup otomatis saat harga baru berlaku (riwayat utuh)",
       str([{k: x.get(k) for k in ("sell_price", "valid_until", "effective_status")} for x in recs]))
    ok(grid_row(admin, KANDA, PROD_TEST).get("effective_price") == 162000,
       "harga terbaru yang dipakai (bukan yang lama)")

    # 11. harga terjadwal tidak mengubah hari ini
    start = (datetime.now(timezone.utc) + timedelta(days=20)).date().isoformat()
    r3 = admin.post(f"{BASE}/api/pricelist", headers=h(KANDA), json={
        "product_id": PROD_TEST, "sell_price": 175000, "entity_id": KANDA,
        "valid_from": start, "note": "POC E-4 terjadwal"}, timeout=30)
    if r3.status_code in (200, 201):
        CLEAN_PRICES.append(r3.json()["id"])
    sched = grid_row(admin, KANDA, PROD_TEST)
    ok(sched.get("effective_price") == 162000 and sched.get("scheduled_count", 0) >= 1,
       "harga terjadwal terlihat sebagai 'terjadwal' dan belum mengubah harga hari ini",
       str({k: sched.get(k) for k in ("effective_price", "scheduled_count")}))

    # 12. kembalikan ke global
    rev = admin.delete(f"{BASE}/api/pricelist/override/{PROD_TEST}",
                       params={"entity_id": KANDA}, headers=h(KANDA), timeout=30)
    ok(rev.status_code == 200 and rev.json().get("reverted") is True,
       "tombol 'kembalikan ke global' diterima server", f"{rev.status_code} {rev.text[:200]}")
    back = grid_row(admin, KANDA, PROD_TEST)
    ok(back.get("entity_price") is None and back.get("price_source") == "global"
       and back.get("effective_price") == back.get("global_price"),
       "produk kembali memakai harga global setelah override dilepas")
    hist = admin.get(f"{BASE}/api/pricelist/records",
                     params={"product_id": PROD_TEST, "entity_id": KANDA}, timeout=30).json()
    ok(len(hist) >= 3, "riwayat harga TIDAK hilang setelah dilepas (hanya dinonaktifkan)",
       f"{len(hist)} record")


def part_price_chain(admin, sales_kanda, sales_ksc) -> None:
    print("\n── E4.7 · 13 · rantai harga yang dipakai pesanan & POS ───────────────")
    db = _db()
    cust_kanda = db.customers.find_one({"entity_id": KANDA}, {"_id": 0, "id": 1})
    cust_ksc = db.customers.find_one({"entity_id": KSC}, {"_id": 0, "id": 1})
    if not cust_kanda or not cust_ksc:
        ok(False, "pelanggan demo tiap badan usaha tersedia")
        return
    q1 = sales_kanda.get(f"{BASE}/api/customer-prices/quote",
                         params={"customer_id": cust_kanda["id"],
                                 "product_ids": PROD_DEMO_KANDA}, timeout=30)
    p1 = (q1.json().get("prices") or {}).get(PROD_DEMO_KANDA, {})
    ok(q1.status_code == 200 and p1.get("source") == "entity",
       f"quote sales Kanda memakai harga badan usaha ({p1.get('price')})",
       f"{q1.status_code} {q1.text[:200]}")
    q2 = sales_ksc.get(f"{BASE}/api/customer-prices/quote",
                       params={"customer_id": cust_ksc["id"],
                               "product_ids": PROD_TEST}, timeout=30)
    p2 = (q2.json().get("prices") or {}).get(PROD_TEST, {})
    ok(q2.status_code == 200 and p2.get("source") == "global",
       "quote sales KSC untuk produk tanpa override tetap harga global",
       f"{q2.status_code} {q2.text[:200]}")
    ok(p1.get("global_price") is not None and p1.get("entity_price") is not None,
       "quote membawa rincian lapisan harga (global & badan usaha) untuk lencana di layar")


def part_csv(admin) -> None:
    print("\n── E4.7 · 14 · ekspor & impor CSV ────────────────────────────────────")
    r = admin.get(f"{BASE}/api/pricelist/export",
                  params={"entity_id": KANDA, "only_with_price": True}, timeout=60)
    text = r.text
    ok(r.status_code == 200 and "harga_entitas" in text and "172500" in text,
       "ekspor CSV berisi kolom & angka harga badan usaha",
       f"{r.status_code} {text[:160]}")

    # Impor gaya Indonesia (titik ribuan) + satu baris TANPA harga (harus dilewati)
    csv_text = (
        "sku;nama_produk;harga_global;harga_entitas;berlaku_dari;berlaku_sampai;catatan\n"
        f"{SKU_TEST};Denim;165.000;171.500;;;POC impor\n"
        "BTK-MEGA-002;Batik;185.000;;;;tanpa harga - harus dilewati\n"
        "SKU-TIDAK-ADA;Entah;1;99.000;;;produk tak ada\n"
    )
    imp = admin.post(f"{BASE}/api/pricelist/import", headers=h(KANDA),
                     json={"entity_id": KANDA, "csv_text": csv_text}, timeout=60)
    body = imp.json() if imp.status_code == 200 else {}
    ok(imp.status_code == 200 and body.get("applied") == 1,
       "impor menerapkan tepat 1 baris berharga", f"{imp.status_code} {imp.text[:250]}")
    row = grid_row(admin, KANDA, PROD_TEST)
    ok(row.get("entity_price") == 171500,
       "angka gaya Indonesia '171.500' terbaca 171500 (bukan 171,5 atau 171500000)",
       str(row.get("entity_price")))
    ok(grid_row(admin, KANDA, "prod_batik_mega_merah").get("entity_price") is None,
       "baris tanpa kolom harga TIDAK mengubah apa pun (impor tidak menghapus harga)")
    ok(any("SKU-TIDAK-ADA" in e for e in body.get("errors", [])),
       "SKU yang tidak ada dilaporkan per baris, bukan menggagalkan seluruh berkas",
       str(body.get("errors")))

    # bersihkan record hasil impor
    for rec in admin.get(f"{BASE}/api/pricelist/records",
                         params={"product_id": PROD_TEST, "entity_id": KANDA},
                         timeout=30).json():
        if rec["id"] not in CLEAN_PRICES:
            CLEAN_PRICES.append(rec["id"])


# ═══════════════════════════════════════════════════════════════════════════
def cleanup(db, audit_before: set) -> dict:
    """Hapus SEMUA jejak POC. Nol residu adalah bagian dari uji.

    Termasuk `audit_logs`: aksi POC (buat gudang, tetapkan harga, impor) menulis
    jejak audit, dan jejak itu pun residu — gate `INV-GATE-01` menghitungnya.
    Yang dihapus hanya baris yang BARU muncul sejak POC mulai.
    """
    removed = {"warehouses": 0, "entity_prices": 0, "cycle_count_sessions": 0,
               "audit_logs": 0}
    for wid in CLEAN_WAREHOUSES:
        removed["warehouses"] += db.warehouses.delete_many({"id": wid}).deleted_count
    for pid in CLEAN_PRICES:
        removed["entity_prices"] += db.entity_prices.delete_many({"id": pid}).deleted_count
    # sisa record harga produk uji (mis. dibuat impor) — produk ini tidak dipakai seed
    removed["entity_prices"] += db.entity_prices.delete_many(
        {"entity_id": KANDA, "product_id": PROD_TEST}).deleted_count
    for sid in CLEAN_SESSIONS:
        removed["cycle_count_sessions"] += db.cycle_count_sessions.delete_many(
            {"id": sid}).deleted_count
    new_audit = {d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})} - audit_before
    if new_audit:
        removed["audit_logs"] = db.audit_logs.delete_many(
            {"id": {"$in": list(new_audit)}}).deleted_count
    return removed


def main() -> int:
    print("=" * 78)
    print("  POC FASE E-4 — GUDANG BERSAMA/KHUSUS (E4.1) & HARGA PER BADAN USAHA (E4.7)")
    print("=" * 78)
    db = _db()
    # Sidik jari diambil SEBELUM login: `POST /auth/login` sendiri menulis satu
    # baris audit per pengguna, dan baris itu pun residu bagi gate INV-GATE-01.
    audit_before = {d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    baseline = {
        "warehouses": db.warehouses.count_documents({}),
        "audit_logs": db.audit_logs.count_documents({}),
        "entity_prices": db.entity_prices.count_documents({}),
        "cycle_count_sessions": db.cycle_count_sessions.count_documents({}),
        "rolls_sby": db.inventory_rolls.count_documents({"warehouse_id": WH_SBY}),
        "sby_mode": (db.warehouses.find_one({"id": WH_SBY}) or {}).get("sharing_mode"),
    }
    admin = login(ADMIN)
    sales_ksc = login(SALES_KSC)
    sales_kanda = login(SALES_KANDA)
    wh_user = login(WAREHOUSE)

    try:
        part_warehouse_visibility(admin, sales_ksc, sales_kanda)
        part_warehouse_write_guard(admin, wh_user)
        part_dedication_guard(admin)
        part_new_warehouse_default(admin, sales_ksc)
        part_price_isolation(admin, sales_ksc, sales_kanda)
        part_price_lifecycle(admin)
        part_price_chain(admin, sales_kanda, sales_ksc)
        part_csv(admin)
    finally:
        print("\n── 15 · pembersihan (nol residu) ─────────────────────────────────────")
        removed = cleanup(db, audit_before)
        print(f"  dibersihkan: {removed}")
        after = {
            "warehouses": db.warehouses.count_documents({}),
            "audit_logs": db.audit_logs.count_documents({}),
            "entity_prices": db.entity_prices.count_documents({}),
            "cycle_count_sessions": db.cycle_count_sessions.count_documents({}),
            "rolls_sby": db.inventory_rolls.count_documents({"warehouse_id": WH_SBY}),
            "sby_mode": (db.warehouses.find_one({"id": WH_SBY}) or {}).get("sharing_mode"),
        }
        ok(after == baseline, "database kembali ke keadaan semula (nol residu)",
           f"sebelum={baseline} sesudah={after}")

    print("\n" + "=" * 78)
    print(f"  HASIL: {PASS} PASS · {FAIL} FAIL")
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
