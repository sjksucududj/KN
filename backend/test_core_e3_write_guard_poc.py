#!/usr/bin/env python3
"""POC FASE E-3 (user story 7) — PAGAR TULIS MODE "SEMUA ENTITAS".

BUKTI-MERAH yang dikunci berkas ini (cacat nyata, dibuktikan 2026-08-10):

    POST /api/customers        X-Entity-Id: all   →  200 OK
    dokumennya mendarat di     entity_id = "ent_ksc"   (badan usaha HOME)

Artinya admin yang sedang melihat **gabungan** membuat dokumen, dan sistem
diam-diam memilih buku badan usaha untuknya. Keputusan pemilik (user story 7):
mode gabungan **hanya untuk melihat** — membuat data wajib memilih satu badan
usaha lebih dulu.

Yang dibuktikan di sini (dan HARUS tetap benar selamanya):
  1. Buat pelanggan / pesanan / uang-masuk di mode gabungan → **409** dengan
     pesan yang menuntun (bukan 500, bukan sukses senyap).
  2. Setelah memilih satu badan usaha, aksi yang sama **berhasil** dan
     `entity_id` dokumennya = badan usaha yang dipilih (bukan HOME).
  3. **Membaca** gabungan tetap boleh (itulah gunanya mode ini).
  4. Master **bersama** (produk, satuan, kategori, template) tetap boleh dibuat
     di mode gabungan — koleksinya tidak punya kolom badan usaha.
  5. Master **badan usaha & akun** tetap boleh dikelola di mode gabungan
     (itu justru layar tingkat grup).
  6. Aksi atas dokumen yang **sudah ada** tetap boleh (badan usahanya diambil
     dari dokumennya; anti-IDOR sudah dijaga `assert_entity_access`).
  7. Peran yang terkunci satu badan usaha (sales) **tidak terpengaruh**: minta
     `all` tidak membuatnya bisa/tak-bisa menulis secara berbeda.
  8. **Nol residu**: seluruh data uji dibersihkan; POC aman dijalankan berulang.

Jalankan:  cd /app && python backend/test_core_e3_write_guard_poc.py
"""
from __future__ import annotations

import os
import sys
import uuid

import requests

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
PW = "demo12345"
ADMIN = "admin@kainnusantara.id"
SALES = "sales@kainnusantara.id"

PASS = 0
FAIL = 0
CLEANUP: list = []          # (collection, id) untuk dibersihkan lewat DB


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
    body = r.json()
    s.headers.update({"Authorization": f"Bearer {body['token']}",
                      "Content-Type": "application/json"})
    return s


def h(entity: str) -> dict:
    return {"X-Entity-Id": entity}


def guarded(resp: requests.Response) -> bool:
    """Respons ini penolakan pagar mode gabungan yang benar?"""
    if resp.status_code != 409:
        return False
    detail = (resp.json() or {}).get("detail", "")
    return isinstance(detail, str) and "Semua Entitas" in detail


def _db():
    from pymongo import MongoClient
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ["DB_NAME"]]


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    tag = uuid.uuid4().hex[:6]
    # Sidik jari jejak audit SEBELUM apa pun (termasuk sebelum login POC): pola yang
    # sama dipakai `test_core_e0_isolation_poc.py` — bersihkan berdasarkan ID BARU,
    # bukan berdasarkan waktu, supaya tidak pernah menyentuh jejak milik orang lain.
    audit_before = {d["id"] for d in _db().audit_logs.find({}, {"_id": 0, "id": 1})}
    print("=" * 78)
    print("  POC FASE E-3 (user story 7) — PAGAR TULIS MODE “SEMUA ENTITAS”")
    print("=" * 78)

    admin = login(ADMIN)
    ents = admin.get(f"{BASE}/api/entities", params={"status": "active"}, timeout=30).json()
    ok(len(ents) >= 2, f"prasyarat: minimal 2 badan usaha aktif (ada {len(ents)})")
    if len(ents) < 2:
        return 1
    home = admin.get(f"{BASE}/api/auth/context", timeout=30).json().get("home_entity_id")
    other = next((e["id"] for e in ents if e["id"] != home), ents[0]["id"])
    print(f"  konteks: home={home} · badan usaha lain={other}\n")

    cust_body = {"name": f"POC E3 {tag}", "pic_name": "PIC POC", "phone": "081200000000",
                 "address": "Jl. Uji Pagar 1", "city": "Bandung"}

    # ── 1. BUKTI-MERAH: buat data di mode gabungan harus DITOLAK ─────────────
    print("── 1. Mode gabungan: membuat data DITOLAK dengan pesan menuntun ──")
    r = admin.post(f"{BASE}/api/customers", json=cust_body, headers=h("all"), timeout=30)
    ok(guarded(r), "POST /api/customers (X-Entity-Id: all) → 409 pagar",
       f"dapat {r.status_code}: {r.text[:200]}")
    if r.status_code == 200:      # kalau lolos, jangan tinggalkan sampah
        CLEANUP.append(("customers", r.json().get("id")))
    ok("Pilih satu badan usaha" in r.text or "badan usaha" in r.text,
       "pesannya menyebut cara keluar dari keadaan ini")

    for path, body, label in (
        ("/api/sales-orders", {"customer_id": "x", "items": []}, "pesanan penjualan"),
        ("/api/ar-receipts", {"customer_id": "x", "amount": 1}, "uang masuk (AR receipt)"),
        ("/api/purchase-requisitions", {"items": []}, "permintaan pembelian"),
        ("/api/approval-rules", {"resource": "x"}, "aturan persetujuan"),
        ("/api/hr/employees", {"name": "x"}, "karyawan HR"),
        ("/api/suppliers", {"name": "x"}, "supplier"),
        ("/api/wms/tasks", {"task_type": "inbound"}, "tugas gudang"),
    ):
        rr = admin.post(f"{BASE}{path}", json=body, headers=h("all"), timeout=30)
        ok(guarded(rr), f"POST {path} ({label}) → 409 pagar",
           f"dapat {rr.status_code}: {rr.text[:160]}")

    # ── 2. Setelah memilih satu badan usaha: BERHASIL & masuk buku yang benar ─
    print("\n── 2. Setelah memilih satu badan usaha: berhasil & tidak salah buku ──")
    r = admin.post(f"{BASE}/api/customers", json=cust_body, headers=h(other), timeout=30)
    created = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200, "POST /api/customers (badan usaha dipilih) → 200",
       f"dapat {r.status_code}: {r.text[:200]}")
    if created.get("id"):
        CLEANUP.append(("customers", created["id"]))
    ok(created.get("entity_id") == other,
       f"pelanggan lahir di badan usaha yang DIPILIH ({other}), bukan HOME ({home})",
       f"entity_id={created.get('entity_id')}")

    # ── 3. Membaca gabungan tetap boleh ─────────────────────────────────────
    print("\n── 3. Membaca gabungan tetap boleh (itulah guna mode ini) ──")
    for path in ("/api/customers", "/api/sales-orders", "/api/dashboard"):
        rr = admin.get(f"{BASE}{path}", headers=h("all"), timeout=30)
        ok(rr.status_code == 200, f"GET {path} (mode gabungan) → 200",
           f"dapat {rr.status_code}: {rr.text[:120]}")

    # ── 4. Master BERSAMA tetap boleh dibuat di mode gabungan ───────────────
    print("\n── 4. Master bersama (tanpa kolom badan usaha) tetap boleh ──")
    r = admin.post(f"{BASE}/api/uoms", headers=h("all"), timeout=30,
                   json={"code": f"POC{tag[:3].upper()}", "name": f"Satuan POC {tag}",
                         "base_type": "length", "precision": 2})
    ok(r.status_code == 200, "POST /api/uoms (master satuan bersama) → 200",
       f"dapat {r.status_code}: {r.text[:160]}")
    if r.status_code == 200:
        CLEANUP.append(("uoms", r.json().get("id")))

    r = admin.post(f"{BASE}/api/product-categories", headers=h("all"), timeout=30,
                   json={"code": f"POCCAT{tag[:3].upper()}", "name": f"Kategori POC {tag}"})
    ok(r.status_code in (200, 201), "POST /api/product-categories (master bersama) → 200",
       f"dapat {r.status_code}: {r.text[:160]}")
    if r.status_code in (200, 201):
        CLEANUP.append(("product_categories", (r.json() or {}).get("id")))

    # ── 5. Master badan usaha & akun = tingkat grup, tetap boleh ────────────
    print("\n── 5. Layar tingkat grup (badan usaha & akun) tetap boleh ──")
    ent_before = admin.get(f"{BASE}/api/entities/{other}", timeout=30).json()
    orig_phone = ent_before.get("phone", "")
    r = admin.patch(f"{BASE}/api/entities/{other}", headers=h("all"), timeout=30,
                    json={"data": {"phone": f"0800{tag}"}})
    ok(r.status_code == 200, "PATCH /api/entities/{id} (mode gabungan) → 200",
       f"dapat {r.status_code}: {r.text[:160]}")
    # Pulihkan segera: POC tidak boleh menggeser data demo (INV-GATE-01).
    admin.patch(f"{BASE}/api/entities/{other}", timeout=30,
                headers=h(other), json={"data": {"phone": orig_phone}})
    r = admin.get(f"{BASE}/api/users", headers=h("all"), params={"limit": 1}, timeout=30)
    ok(r.status_code == 200, "GET /api/users (mode gabungan) → 200")

    # ── 6. Aksi atas dokumen yang SUDAH ada tetap boleh ─────────────────────
    print("\n── 6. Menindak dokumen yang sudah ada tetap boleh ──")
    if created.get("id"):
        r = admin.patch(f"{BASE}/api/customers/{created['id']}", headers=h("all"), timeout=30,
                        json={"data": {"city": "Jakarta"}})
        ok(r.status_code == 200,
           "PATCH /api/customers/{id} (mode gabungan) → 200 (badan usaha dari dokumen)",
           f"dapat {r.status_code}: {r.text[:160]}")

    # ── 7. Peran terkunci satu badan usaha tidak terpengaruh ───────────────
    print("\n── 7. Sales (terkunci 1 badan usaha) tidak terpengaruh pagar ──")
    sales = login(SALES)
    r = sales.get(f"{BASE}/api/auth/context", timeout=30)
    ctx = r.json()
    ok(ctx.get("can_switch_entity") is False,
       "sales memang terkunci (can_switch_entity=false) sehingga tak pernah di mode gabungan",
       str(ctx.get("can_switch_entity")))
    r = sales.get(f"{BASE}/api/customers", headers=h("all"), timeout=30)
    ok(r.status_code == 200, "sales tetap bisa membaca daftarnya sendiri")
    rows = r.json() if r.status_code == 200 else []
    leaks = [c for c in rows if c.get("entity_id") not in ("", None, ctx.get("home_entity_id"))]
    ok(not leaks, "sales tidak melihat pelanggan badan usaha lain walau meminta `all`",
       f"{len(leaks)} baris bocor")

    # ── 8. Nol residu ───────────────────────────────────────────────────────
    print("\n── 8. Bersih-bersih (POC harus bisa dijalankan berulang) ──")
    db = _db()
    removed = 0
    for coll, _id in CLEANUP:
        if _id:
            removed += db[coll].delete_many({"id": _id}).deleted_count
    removed += db.customers.delete_many({"name": {"$regex": "^POC E3 "}}).deleted_count
    removed += db.uoms.delete_many({"name": {"$regex": "^Satuan POC "}}).deleted_count
    removed += db.product_categories.delete_many(
        {"name": {"$regex": "^Kategori POC "}}).deleted_count
    # Jejak audit yang lahir dari POC ini juga residu (INV-GATE-01 menghitung
    # `audit_logs`). Dihapus berdasarkan ID yang BARU muncul sejak POC mulai.
    new_audit = {d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})} - audit_before
    audit_removed = (db.audit_logs.delete_many({"id": {"$in": list(new_audit)}}).deleted_count
                     if new_audit else 0)
    ok(removed >= 1, f"data uji dibersihkan ({removed} dokumen · {audit_removed} jejak audit)")
    left = (db.customers.count_documents({"name": {"$regex": "^POC E3 "}})
            + db.uoms.count_documents({"name": {"$regex": "^Satuan POC "}})
            + db.audit_logs.count_documents({"id": {"$in": list(new_audit)}}))
    ok(left == 0, "nol residu setelah POC", f"{left} dokumen tersisa")
    ent_after = admin.get(f"{BASE}/api/entities/{other}", timeout=30).json()
    ok(ent_after.get("phone", "") == orig_phone,
       "data demo badan usaha dipulihkan (nomor telepon kembali seperti semula)",
       f"{ent_after.get('phone')} != {orig_phone}")

    print("\n" + "=" * 78)
    print(f"  HASIL: {PASS} PASS · {FAIL} FAIL")
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    sys.exit(main())
