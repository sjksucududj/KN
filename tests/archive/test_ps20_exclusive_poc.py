"""POC PS-20 — Produk eksklusif per sales ("PO sendiri"). Bukti-merah lewat API.

Membuktikan (KN_18 §PS-20, kriteria terima a/b/c):
  (a) Sales A (pemilik) MELIHAT item eksklusifnya; Sales B TIDAK — via API GET /products.
  (b) admin/manager MELIHAT semua.
  (c) SO dari item eksklusif hanya boleh dibuat pemiliknya → Sales B ditolak 403 di API.
      (Sales A lolos gate eksklusivitas — dibuktikan level service tanpa memutasi data.)
  + GET /products/sales-owners mengembalikan daftar sales untuk form.
  + Enforcement DI BACKEND (bukan UI) — sales B benar-benar tak menerima kodenya dari API.

Jalankan: /root/.venv/bin/python test_ps20_exclusive_poc.py
"""
import asyncio
import sys

import requests

sys.path.insert(0, "/app/backend")
from db import db  # noqa: E402
from services import product_exclusivity as pexcl  # noqa: E402

BASE = "http://localhost:8001/api"
PW = "demo12345"
SKU = "PS20-EXCL-POC"
AYU = "user_sales_01"   # pemilik
BIMA = "user_sales_02"  # bukan pemilik
CUST, ADDR, ENT = "cust_toko_kain", "addr_001", "ent_ksc"

PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✅ {name} {extra}")
    else:
        FAIL += 1; print(f"  ❌ {name} {extra}")


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


async def cleanup():
    await db.products.delete_many({"sku": SKU})


async def main():
    print("\n=== POC PS-20 — Produk Eksklusif per Sales ===\n")
    await cleanup()

    admin = login("admin@kainnusantara.id")
    ayu = login("sales@kainnusantara.id")
    bima = login("sales2@kainnusantara.id")
    check("login admin/ayu/bima", all([admin, ayu, bima]))

    # Admin membuat produk EKSKLUSIF milik Ayu (user_sales_01)
    body = {
        "sku": SKU, "name": "Kain Eksklusif PO-Sendiri (POC)", "category": "Batik",
        "stage": "finished", "fabric_type": "woven", "grade": "A",
        "gramasi": 150, "lebar": 1.5,
        "base_unit": "meter", "price": 100000, "lifecycle": "produksi", "status": "active",
        "exclusivity": "sales_tertentu", "owner_sales_ids": [AYU],
    }
    r = requests.post(f"{BASE}/products", json=body, headers=H(admin), timeout=20)
    check("admin buat produk eksklusif (201/200)", r.status_code in (200, 201), f"(HTTP {r.status_code} {r.text[:120]})")
    created = r.json() if r.status_code in (200, 201) else {}
    check("tersimpan exclusivity=sales_tertentu", created.get("exclusivity") == "sales_tertentu")
    check("owner_sales_ids = [Ayu]", created.get("owner_sales_ids") == [AYU], f"({created.get('owner_sales_ids')})")

    def skus(tok):
        rr = requests.get(f"{BASE}/products", headers=H(tok), timeout=20)
        rr.raise_for_status()
        return {p["sku"] for p in rr.json()}

    # (a) visibilitas
    check("(a) Ayu (pemilik) MELIHAT produk eksklusif", SKU in skus(ayu))
    check("(a) Bima (bukan pemilik) TIDAK melihat", SKU not in skus(bima))
    # (b) admin lihat semua
    check("(b) admin MELIHAT produk eksklusif", SKU in skus(admin))

    # sales-owners endpoint (untuk form)
    r = requests.get(f"{BASE}/products/sales-owners", headers=H(admin), timeout=15)
    owners = r.json() if r.status_code == 200 else []
    check("GET /products/sales-owners (admin) 200 & memuat Ayu", r.status_code == 200 and any(u["id"] == AYU for u in owners),
          f"({len(owners)} sales)")
    # sales TIDAK boleh mengakses daftar owner (butuh product:update)
    r2 = requests.get(f"{BASE}/products/sales-owners", headers=H(bima), timeout=15)
    check("sales tak boleh akses sales-owners (403)", r2.status_code == 403, f"(HTTP {r2.status_code})")

    # (c) SO create oleh Bima memakai produk eksklusif → 403 (enforcement backend, sebelum mutasi)
    pid = created.get("id")
    so_payload = {
        "customer_id": CUST, "shipping_address_id": ADDR, "entity_id": ENT,
        "items": [{"product_id": pid, "quantity": 2, "unit": "meter"}],
    }
    r = requests.post(f"{BASE}/sales-orders", json=so_payload, headers=H(bima), timeout=20)
    check("(c) Bima buat SO item eksklusif → 403", r.status_code == 403, f"(HTTP {r.status_code})")
    check("(c) pesan 403 = 'eksklusif milik sales lain'", "eksklusif" in r.text.lower(), f"({r.text[:120]})")

    # (c) Ayu (pemilik) LOLOS gate eksklusivitas — dibuktikan level service (tanpa memutasi data)
    prod_doc = await db.products.find_one({"sku": SKU}, {"_id": 0})
    ok_ayu = pexcl.can_view({"role": "sales", "id": AYU}, prod_doc)
    ok_bima = pexcl.can_view({"role": "sales", "id": BIMA}, prod_doc)
    ok_admin = pexcl.can_view({"role": "admin", "id": "x"}, prod_doc)
    check("(c) service: Ayu boleh menjual", ok_ayu is True)
    check("(c) service: Bima TIDAK boleh", ok_bima is False)
    check("(b) service: admin boleh", ok_admin is True)

    await cleanup()
    print(f"\n=== HASIL: {PASS} PASS / {FAIL} FAIL ===\n")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
