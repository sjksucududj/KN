#!/usr/bin/env python3
"""POC FASE L — LINI PRODUK: master yang bisa bertambah + pagar keras yang bisa dikonfigurasi.

Permintaan pemilik (sesi 2026-08-18): *"woven / knit / printing dikerjakan staf
berbeda; harus master yang bisa bertambah, pembedanya pagar keras tapi bisa
dikonfigurasi (satu staf boleh dapat lebih dari satu lini), dan berlaku di semua
tempat — bukan hanya saat membuat PO."*

DELAPAN HAL YANG DIBUKTIKAN DI SINI (RENCANA_EKSEKUSI_MD_ERP.md §L.F)
====================================================================
  L1  Master bisa DITAMBAH lewat API (lini ke-4 "Denim") tanpa satu baris kode
      diubah → langsung muncul di `/api/enums` (sumber chip 12 layar).
  L2  Akun ber-`allowed_line_codes=["printing"]` TIDAK melihat produk woven di
      `/api/products`, dan mendapat **403 ber-kalimat Indonesia** saat mencoba
      membuat SO berisi kain woven (bukan 500, bukan daftar kosong tanpa sebab).
  L3  Akun TANPA `allowed_line_codes` melihat semua (kosong = semua lini → nol regresi).
  L4  Dokumen/produk lama TANPA `line_code` TETAP terlihat oleh akun berpagar
      (kalau tidak, seluruh layar mendadak kosong — kelas kejadian yang paling
      cepat menghancurkan kepercayaan pengguna).
  L5  SNAPSHOT: mengubah lini master produk TIDAK mengubah baris SO yang sudah
      terbit (riwayat tidak boleh ikut berpindah papan).
  L6  INV-LINE-02: produk `line_code="knit"` ber-`fabric_type="woven"` DITOLAK 400.
  L7  Pagar entitas tetap berlaku pada KOSAKATA: lini khusus CV Kanda Suka tidak
      bocor ke PT Kain Suka Cita; baris global terlihat keduanya.
  L8  `POST /api/products` di mode "Semua Entitas" tetap berperilaku seperti
      sebelumnya (master BERSAMA — pagar tulis E-3 tidak berubah).
  L9  NOL RESIDU: seluruh data uji dibersihkan (POC aman dijalankan berulang).

Jalankan:  cd /app && python backend/test_core_lini_poc.py
"""
from __future__ import annotations

import os
import sys
import uuid

import requests

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
PW = "demo12345"
ADMIN = "admin@kainnusantara.id"
ENT_A = "ent_ksc"
ENT_B = "ent_kanda"

PASS = 0
FAIL = 0


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


def enum_values(sess: requests.Session, entity: str, name: str = "product_line") -> list:
    r = sess.get(f"{BASE}/api/enums", headers=h(entity), timeout=30)
    assert r.status_code == 200, f"/api/enums: {r.status_code} {r.text[:200]}"
    return [v.get("value") for v in (r.json().get("enums", {}).get(name, {}).get("values") or [])]


def products_of(sess: requests.Session, entity: str, line: str = "") -> list:
    url = f"{BASE}/api/products" + (f"?line={line}" if line else "")
    r = sess.get(url, headers=h(entity), timeout=60)
    assert r.status_code == 200, f"/api/products: {r.status_code} {r.text[:200]}"
    return r.json()


def make_product(sess: requests.Session, entity: str, sku: str, name: str,
                 line_code: str, fabric: str = "woven") -> requests.Response:
    return sess.post(f"{BASE}/api/products", headers=h(entity), timeout=30, json={
        "sku": sku, "name": name, "category": "Kain", "variant": "Regular",
        "color": "Natural", "motif": "Polos", "grade": "A", "stage": "finished",
        "fabric_type": fabric, "supplier": "Internal", "base_unit": "meter",
        "price": 50000, "harga_pokok": 30000, "gramasi": 120, "lebar": 1.15,
        "line_code": line_code, "description": "produk uji POC FASE L",
    })


def main() -> int:  # noqa: C901 — POC linear supaya mudah dibaca sebagai bukti
    tag = uuid.uuid4().hex[:6]
    db = _db()
    audit_before = {d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    cleanup_master: list = []          # (collection, id)
    cleanup_products: list = []        # product id
    restore_product: list = []         # (product_id, line_code semula)
    temp_user_id = ""

    print("=" * 84)
    print("  POC FASE L — LINI PRODUK (master bertambah · pagar keras · snapshot)")
    print("=" * 84)
    admin = login(ADMIN)

    # ── 0. Prasyarat: master lini sudah ter-seed migrasi ─────────────────────
    print("\n── 0. Prasyarat ──")
    base_lines = enum_values(admin, ENT_A)
    ok(all(c in base_lines for c in ("woven", "knit", "printing")),
       "master lini berisi woven · knit · printing (hasil migrate_lini_produk.py)",
       f"dapat {base_lines}")
    all_products = products_of(admin, ENT_A)
    ok(len(all_products) > 0, f"katalog terbaca admin ({len(all_products)} produk)")
    woven_prod = next((p for p in all_products if p.get("line_code") == "woven"), None)
    printing_prod = next((p for p in all_products if p.get("line_code") == "printing"), None)
    ok(bool(woven_prod and printing_prod),
       "ada produk woven & printing untuk diuji",
       f"woven={bool(woven_prod)} printing={bool(printing_prod)}")
    if not (woven_prod and printing_prod):
        print("  → jalankan `python scripts/migrate_lini_produk.py` lebih dulu.")
        return 1

    # ── L1. Master bisa DITAMBAH tanpa ubah kode ─────────────────────────────
    print("\n── L1. Lini ke-4 “Denim” ditambah lewat API → muncul di /api/enums ──")
    code4 = f"denim{tag}"
    r = admin.post(f"{BASE}/api/entity-masters/product-lines", headers=h("all"), timeout=30,
                   json={"code": code4, "name": f"Denim POC {tag}", "sort": 9,
                         "fabric_type_required": "", "measure_unit_default": "yard",
                         "stage_sequence": ["yarn", "tenun", "celup", "inspect"],
                         "sample_types_default": ["labdip"], "active": True})
    ok(r.status_code == 200, "baris master lini baru dibuat (mode Semua Entitas → GLOBAL)",
       f"dapat {r.status_code}: {r.text[:200]}")
    if r.status_code == 200:
        row = r.json()
        cleanup_master.append(("product_lines", row.get("id", "")))
        ok(str(row.get("entity_id")) in ("all", ""),
           "baris baru lahir GLOBAL (dipakai semua badan usaha)", f"dapat {row.get('entity_id')}")
    after = enum_values(admin, ENT_A)
    ok(code4 in after, "lini baru langsung muncul di /api/enums (tanpa restart backend)",
       f"dapat {after}")
    r_one = admin.get(f"{BASE}/api/enums/product_line", headers=h(ENT_A), timeout=30)
    one_vals = [v.get("value") for v in (r_one.json().get("values") or [])]
    ok(code4 in one_vals, "GET /api/enums/product_line sepakat dengan snapshot registry",
       f"dapat {one_vals}")

    # ── L6. INV-LINE-02 (dibuktikan sebelum membuat produk uji lain) ─────────
    print("\n── L6. INV-LINE-02: lini knit untuk kain woven DITOLAK ──")
    r = make_product(admin, ENT_A, f"POC-L6-{tag}", f"Uji INV-LINE-02 {tag}",
                     line_code="knit", fabric="woven")
    ok(r.status_code == 400, "produk lini knit ber-fabric_type woven ditolak 400",
       f"dapat {r.status_code}: {r.text[:200]}")
    detail = (r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json")
              else r.text) or ""
    ok("knit" in str(detail).lower() and "INV-LINE-02" in str(detail),
       "pesan menyebut lini, jenis kain, dan invariannya (bisa ditindak pengguna)",
       f"dapat: {str(detail)[:200]}")
    ok(db.products.count_documents({"sku": f"POC-L6-{tag}"}) == 0,
       "produk yang ditolak TIDAK tersimpan (tolakan bukan setengah jalan)")

    # ── L8 + produk uji: mode "Semua Entitas" tetap boleh (master BERSAMA) ───
    print("\n── L8. POST /api/products di mode “Semua Entitas” tetap berperilaku sama ──")
    r = make_product(admin, ENT_A, f"POC-LP-{tag}", f"Kain Printing POC {tag}",
                     line_code="printing", fabric="woven")
    ok(r.status_code == 200, "produk lini printing dibuat", f"dapat {r.status_code}: {r.text[:200]}")
    p_print = r.json() if r.status_code == 200 else {}
    if p_print.get("id"):
        cleanup_products.append(p_print["id"])
    r = make_product(admin, "all", f"POC-LN-{tag}", f"Kain Tanpa Lini POC {tag}",
                     line_code="", fabric="woven")
    ok(r.status_code == 200,
       "produk TANPA lini dibuat di mode Semua Entitas (master bersama — pagar E-3 tak berubah)",
       f"dapat {r.status_code}: {r.text[:200]}")
    p_none = r.json() if r.status_code == 200 else {}
    if p_none.get("id"):
        cleanup_products.append(p_none["id"])
        ok(str(p_none.get("line_code") or "") == "",
           "produk tanpa lini tersimpan dengan lini KOSONG (bukan ditebak mesin)")

    # ── L3. Akun tanpa pagar lini melihat semua ─────────────────────────────
    print("\n── L2/L3/L4. Akun berpagar lini “printing” (Dewi) ──")
    email = f"dewi.printing.{tag}@kainnusantara.id"
    r = admin.post(f"{BASE}/api/users", headers=h(ENT_A), timeout=30, json={
        "name": f"Dewi Printing POC {tag}", "email": email, "role": "sales",
        "password": PW, "home_entity_id": ENT_A, "allowed_entity_ids": [ENT_A]})
    ok(r.status_code == 200, "akun uji dibuat", f"dapat {r.status_code}: {r.text[:200]}")
    if r.status_code != 200:
        return 1
    temp_user_id = r.json()["id"]
    dewi = login(email)
    before_list = products_of(dewi, ENT_A)
    ok(len(before_list) >= len(all_products) - 2,
       f"L3 — tanpa `allowed_line_codes` Dewi melihat semua ({len(before_list)} produk)",
       f"admin={len(all_products)} dewi={len(before_list)}")

    # pagar dinyalakan: hanya lini printing
    r = admin.patch(f"{BASE}/api/users/{temp_user_id}", headers=h(ENT_A), timeout=30,
                    json={"data": {"allowed_line_codes": ["printing"]}})
    ok(r.status_code == 200, "pagar lini disetel: hanya `printing`",
       f"dapat {r.status_code}: {r.text[:200]}")
    ok("lini" in " ".join(r.json().get("revoke_reasons", []) or []).lower(),
       "sesi Dewi dicabut karena hak lini berubah (tidak boleh terus memakai hak lama)",
       f"dapat {r.json().get('revoke_reasons')}")
    r = admin.patch(f"{BASE}/api/users/{temp_user_id}", headers=h(ENT_A), timeout=30,
                    json={"data": {"allowed_line_codes": ["printng"]}})
    ok(r.status_code == 400, "lini yang salah ketik DITOLAK 400 (bukan disimpan diam-diam)",
       f"dapat {r.status_code}: {r.text[:160]}")

    dewi = login(email)          # sesi baru (yang lama sudah dicabut)
    after_list = products_of(dewi, ENT_A)
    lines_seen = {str(p.get("line_code") or "") for p in after_list}
    ok("woven" not in lines_seen and "knit" not in lines_seen,
       "L2 — daftar produk Dewi TIDAK memuat lini woven/knit", f"dapat lini {lines_seen}")
    ok("printing" in lines_seen, "daftar Dewi memuat produk printing", f"dapat {lines_seen}")
    ok(any(p.get("id") == p_none.get("id") for p in after_list),
       "L4 — produk TANPA lini tetap terlihat (tidak ada layar mendadak kosong)")
    ok(len(after_list) < len(before_list),
       f"pagar benar-benar menyempitkan daftar ({len(before_list)} → {len(after_list)})")

    # baca per dokumen ikut berpagar (bukan hanya daftarnya)
    r = dewi.get(f"{BASE}/api/products/{woven_prod['id']}/stock-breakdown",
                 headers=h(ENT_A), timeout=30)
    ok(r.status_code == 403, "alamat langsung produk woven ditolak 403 (bukan hanya UI disaring)",
       f"dapat {r.status_code}: {r.text[:160]}")

    # `?line=` tidak bisa dipakai sebagai jalan belakang
    back = products_of(dewi, ENT_A, line="woven")
    ok(all(str(p.get("line_code") or "") != "woven" for p in back),
       "`?line=woven` dari akun printing tidak membocorkan produk woven",
       f"dapat {[p.get('sku') for p in back][:5]}")

    # ── L2b. 403 saat memakai produk di luar lini pada dokumen ──────────────
    print("\n── L2b. Membuat SO berisi kain woven → 403 ber-kalimat Indonesia ──")
    # Daftar pelanggan diambil sebagai ADMIN: akun uji baru belum punya pelanggan
    # yang ditugaskan kepadanya (kepemilikan data sales FASE E-8), jadi daftarnya
    # memang kosong bagi Dewi — itu perilaku yang benar, bukan bagian uji ini.
    cust = admin.get(f"{BASE}/api/customers", headers=h(ENT_A), timeout=30).json()
    rows = cust if isinstance(cust, list) else cust.get("items", [])
    target = next((c for c in rows if (c.get("addresses") or [])
                   and "Sejahtera" not in (c.get("name") or "")), None)
    ok(bool(target), "ada pelanggan uji dengan alamat kirim",
       f"dapat {len(rows)} pelanggan")
    if target:
        r = dewi.post(f"{BASE}/api/sales-orders", headers=h(ENT_A), timeout=60, json={
            "customer_id": target["id"],
            "shipping_address_id": target["addresses"][0]["id"],
            "items": [{"product_id": woven_prod["id"], "quantity": 1, "unit": "meter"}],
        })
        ok(r.status_code == 403, "SO berisi kain woven ditolak 403",
           f"dapat {r.status_code}: {r.text[:200]}")
        msg = str((r.json() or {}).get("detail", "")) if r.status_code == 403 else r.text
        ok("lini" in msg.lower() and "printing" in msg.lower(),
           "pesan menyebut lini dokumen & lini akun + cara memperbaikinya",
           f"dapat: {msg[:200]}")
        ok(db.sales_orders.count_documents({"items.product_id": woven_prod["id"],
                                            "created_by": f"Dewi Printing POC {tag}"}) == 0,
           "tidak ada SO setengah jadi yang tertinggal")

    # ── L5. Snapshot: riwayat tidak ikut berpindah papan ─────────────────────
    print("\n── L5. Snapshot lini pada baris dokumen yang sudah terbit ──")
    so = db.sales_orders.find_one({"items.line_code": {"$nin": ["", None]}}, {"_id": 0})
    ok(bool(so), "ada SO ber-snapshot lini (hasil migrasi)")
    if so:
        item = next(it for it in so["items"] if str(it.get("line_code") or "").strip())
        pid, before_code = item["product_id"], item["line_code"]
        head_before = sorted(so.get("line_codes") or [])
        prod = db.products.find_one({"id": pid}, {"_id": 0})
        restore_product.append((pid, str(prod.get("line_code") or "")))
        # pindahkan lini produk ke lini lain yang SAH untuk kain ini
        target_line = code4 if code4 in after else "printing"
        if target_line == before_code:
            target_line = "printing" if before_code != "printing" else code4
        r = admin.patch(f"{BASE}/api/products/{pid}", headers=h(ENT_A), timeout=30,
                        json={"data": {"line_code": target_line}})
        ok(r.status_code == 200, f"lini master produk dipindah ke `{target_line}`",
           f"dapat {r.status_code}: {r.text[:200]}")
        so_after = db.sales_orders.find_one({"id": so["id"]}, {"_id": 0})
        item_after = next(it for it in so_after["items"] if it["product_id"] == pid)
        ok(item_after.get("line_code") == before_code,
           f"baris SO {so.get('number')} TETAP lini `{before_code}` (snapshot, bukan join)",
           f"dapat {item_after.get('line_code')}")
        ok(sorted(so_after.get("line_codes") or []) == head_before,
           "turunan `line_codes[]` kepala dokumen juga tidak berubah",
           f"dapat {so_after.get('line_codes')}")

    # ── L7. Pagar entitas berlaku juga untuk KOSAKATA ───────────────────────
    print("\n── L7. Lini khusus satu badan usaha tidak bocor ke badan usaha lain ──")
    code_b = f"kandaonly{tag}"
    r = admin.post(f"{BASE}/api/entity-masters/product-lines", headers=h(ENT_B), timeout=30,
                   json={"code": code_b, "name": f"Khusus Kanda {tag}", "sort": 8,
                         "measure_unit_default": "yard", "active": True})
    ok(r.status_code == 200, "lini khusus CV Kanda Suka dibuat",
       f"dapat {r.status_code}: {r.text[:200]}")
    if r.status_code == 200:
        cleanup_master.append(("product_lines", r.json().get("id", "")))
        ok(r.json().get("entity_id") == ENT_B, "baris itu dimiliki CV Kanda Suka",
           f"dapat {r.json().get('entity_id')}")
    vals_b = enum_values(admin, ENT_B)
    vals_a = enum_values(admin, ENT_A)
    ok(code_b in vals_b, "lini itu terlihat DI CV Kanda Suka", f"dapat {vals_b}")
    ok(code_b not in vals_a, "lini itu TIDAK bocor ke PT Kain Suka Cita", f"dapat {vals_a}")
    ok(all(c in vals_a and c in vals_b for c in ("woven", "knit", "printing")),
       "baris GLOBAL tetap terlihat di kedua badan usaha")

    # ── L9. Nol residu ──────────────────────────────────────────────────────
    print("\n── L9. Bersih-bersih (POC harus bisa dijalankan berulang) ──")
    removed = 0
    for pid, code in restore_product:
        db.products.update_one({"id": pid}, {"$set": {"line_code": code}})
    for coll, _id in cleanup_master:
        if _id:
            removed += db[coll].delete_many({"id": _id}).deleted_count
    for pid in cleanup_products:
        removed += db.products.delete_many({"id": pid}).deleted_count
    removed += db.products.delete_many({"sku": {"$regex": f"^POC-L.-{tag}$"}}).deleted_count
    if temp_user_id:
        removed += db.users.delete_many({"id": temp_user_id}).deleted_count
        removed += db.user_sessions.delete_many({"user_id": temp_user_id}).deleted_count
    new_audit = {d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})} - audit_before
    audit_removed = (db.audit_logs.delete_many({"id": {"$in": list(new_audit)}}).deleted_count
                     if new_audit else 0)
    ok(removed >= 3, f"data uji dibersihkan ({removed} dokumen · {audit_removed} jejak audit)")
    left = db.product_lines.count_documents({"code": {"$regex": tag}})
    ok(left == 0, "tidak ada baris master uji yang tertinggal", f"sisa {left}")
    ok(db.products.count_documents({"sku": {"$regex": tag}}) == 0,
       "tidak ada produk uji yang tertinggal")

    print("\n" + "=" * 84)
    print(f"  HASIL: {PASS} PASS · {FAIL} FAIL")
    print("=" * 84)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except Exception:  # noqa: BLE001
        pass
    sys.exit(main())
