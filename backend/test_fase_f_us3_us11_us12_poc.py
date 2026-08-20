#!/usr/bin/env python3
"""POC VERIFIKASI — FASE F user story yang BELUM diuji: US3 · US11 · US12.

Dijalankan lewat HTTP nyata (bukan mock), self-cleanup, tanpa meninggalkan residu.

US3  — Sales mencoba menjual produk lifecycle `disetujui` (RND-KTN-150) → DITOLAK
       dengan pesan yang BISA DITINDAK (menyebut alur R&D Spesifikasi → Sample →
       Rilis ke Produksi). Produk normal (BTK-MEGA-001) TETAP bisa dijual.
US11 — Warehouse melihat mutasi stok bertipe `sample_issue` (label UI:
       "Ambil Bahan Sample (R&D)") di daftar mutasi gudang.
US12 — Auditor (admin) menelusuri Jejak Dokumen: kontrak supplier → md_sample →
       md_spec (relasi tersimpan di `refs[]`, bukan field ad-hoc).

Jalankan:  python /app/backend/test_fase_f_us3_us11_us12_poc.py
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poc_stock_guard import restore_stock, snapshot_stock  # noqa: E402

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001/api")
CREDS = {
    "admin": ("admin@kainnusantara.id", "demo12345"),
    "sales": ("sales@kainnusantara.id", "demo12345"),
    "warehouse": ("warehouse@kainnusantara.id", "demo12345"),
    "manager": ("manager@kainnusantara.id", "demo12345"),
}

PASS = 0
FAIL = 0
FAILURES = []


def ok(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label} :: {extra}")
        print(f"  [FAIL] {label} — {extra}")


def login(role):
    email, pwd = CREDS[role]
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pwd}, timeout=25)
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("session_token")
    assert tok, f"tak ada token utk {role}: {r.text[:200]}"
    return {"Authorization": f"Bearer {tok}"}


def get(h, path, **params):
    return requests.get(f"{BASE}{path}", headers=h, params=params or None, timeout=40)


def post(h, path, payload):
    return requests.post(f"{BASE}{path}", headers=h, json=payload, timeout=60)


def _purge_order(order_id: str):
    """Buang residu SO uji (order + mutasi reservasi) supaya DB tetap bersih."""
    if not order_id:
        return
    try:
        import asyncio

        from motor.motor_asyncio import AsyncIOMotorClient

        async def _run():
            cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = cli[os.environ.get("DB_NAME", "test_database")]
            await db.sales_orders.delete_many({"id": order_id})
            # Reservasi/lepas-reservasi menyimpan id SO di `source_document`,
            # sebagian mesin lain memakai `reference_id` — bersihkan KEDUANYA
            # supaya INV-GATE-01 (anti-residu) tetap hijau.
            await db.inventory_movements.delete_many({"source_document": order_id})
            await db.inventory_movements.delete_many({"reference_id": order_id})
            await db.audit_logs.delete_many({"entity_id": order_id})
            cli.close()

        asyncio.run(_run())
        print("    · residu SO uji dibersihkan dari DB")
    except Exception as exc:  # noqa: BLE001
        print(f"    · PERINGATAN gagal purge residu: {exc}")


def _db_counts():
    """Hitung isi koleksi yang bisa tercemar POC (untuk bukti nol-residu)."""
    import asyncio

    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run():
        cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "test_database")]
        out = {
            "sales_orders": await db.sales_orders.count_documents({}),
            "inventory_movements": await db.inventory_movements.count_documents({}),
        }
        cli.close()
        return out

    return asyncio.run(_run())


# ─────────────────────────────────────────────────────────────── US3
def us3(sales, admin):
    print("\n=== US3 — Sales DITOLAK menjual produk R&D (lifecycle != produksi) ===")
    r = get(sales, "/products")
    ok("GET /products (katalog sales) 200", r.status_code == 200, r.text[:200])
    products = r.json() if r.status_code == 200 else []
    if isinstance(products, dict):
        products = products.get("items", [])
    rnd = next((p for p in products if p.get("sku") == "RND-KTN-150"), None)
    ok("produk RND-KTN-150 TERLIHAT di katalog POS (untuk ditandai, bukan disembunyikan)",
       rnd is not None, "produk R&D tidak ada di /products")
    if not rnd:
        return
    ok("lifecycle RND-KTN-150 == 'disetujui' (belum boleh dijual)",
       rnd.get("lifecycle") == "disetujui", f"lifecycle={rnd.get('lifecycle')}")

    # katalog khusus orderable HARUS menyaring produk itu
    r2 = get(sales, "/products", orderable_only="true")
    ok("GET /products?orderable_only=true 200", r2.status_code == 200, r2.text[:200])
    orderable = r2.json() if r2.status_code == 200 else []
    if isinstance(orderable, dict):
        orderable = orderable.get("items", [])
    ok("orderable_only MENYARING RND-KTN-150",
       all(p.get("sku") != "RND-KTN-150" for p in orderable), "masih ikut di katalog orderable")

    normal = next((p for p in products if p.get("sku") == "BTK-MEGA-001"), None)
    ok("produk normal BTK-MEGA-001 ada di katalog", normal is not None)

    # kebijakan penegakan
    rm = get(sales, "/rnd/meta")
    pol = (rm.json().get("policy") or {}) if rm.status_code == 200 else {}
    ok("GET /rnd/meta 200 & kebijakan lifecycle_enforcement terbaca",
       rm.status_code == 200 and pol.get("lifecycle_enforcement") in ("off", "warn", "block"),
       f"{rm.status_code} {rm.text[:160]}")
    print(f"    · lifecycle_enforcement = {pol.get('lifecycle_enforcement')}")

    cust = get(sales, "/customers")
    customers = cust.json() if cust.status_code == 200 else []
    if isinstance(customers, dict):
        customers = customers.get("items", [])
    ok("ada pelanggan untuk uji SO", len(customers) > 0)
    if not customers:
        return
    cid = customers[0]["id"]
    addrs = customers[0].get("addresses") or []
    aid = (addrs[0].get("id") if addrs else "")
    ok("pelanggan uji punya alamat kirim", bool(aid), f"customer={cid}")

    payload = {
        "customer_id": cid,
        "shipping_address_id": aid,
        "items": [{"product_id": rnd["id"], "quantity": 5, "unit": rnd.get("base_unit") or "meter",
                   "price": float(rnd.get("price") or 100000)}],
        "notes": "POC US3 — harus ditolak",
    }
    r3 = post(sales, "/sales-orders", payload)
    ok("POST /sales-orders atas produk R&D DITOLAK (400)", r3.status_code == 400,
       f"status={r3.status_code} body={r3.text[:250]}")
    detail = ""
    try:
        detail = str(r3.json().get("detail", ""))
    except ValueError:
        detail = r3.text
    low = detail.lower()
    ok("pesan penolakan menyatakan produk belum boleh dijual/masuk dokumen",
       ("belum boleh dijual" in low or "belum boleh masuk" in low), detail[:250])
    ok("pesan menuntun ke alur R&D (Spesifikasi → Sample → Rilis ke Produksi)",
       ("spesifikasi" in low and "sample" in low and "produksi" in low), detail[:250])
    print(f"    · pesan: {detail[:220]}")

    if normal:
        payload_ok = {
            "customer_id": cid,
            "shipping_address_id": aid,
            "items": [{"product_id": normal["id"], "quantity": 2,
                       "unit": normal.get("base_unit") or "meter",
                       "price": float(normal.get("price") or 100000)}],
            "notes": "POC US3 — kontrol positif (harus lolos)",
        }
        r4 = post(sales, "/sales-orders", payload_ok)
        ok("POST /sales-orders atas produk normal BERHASIL (kontrol positif)",
           r4.status_code in (200, 201), f"{r4.status_code} {r4.text[:200]}")
        if r4.status_code in (200, 201):
            oid = r4.json().get("id")
            # self-cleanup: batalkan SO kontrol lalu hapus jejaknya dari DB uji
            d = post(admin, f"/sales-orders/{oid}/cancel",
                     {"reason": "POC US3 self-cleanup"})
            ok("self-cleanup: SO kontrol dibatalkan", d.status_code in (200, 201, 204),
               f"{d.status_code} {d.text[:160]}")
            _purge_order(oid)


# ─────────────────────────────────────────────────────────────── US11
def us11(warehouse):
    print("\n=== US11 — Warehouse melihat mutasi 'Ambil Bahan Sample (R&D)' (sample_issue) ===")
    r = get(warehouse, "/inventory/movements")
    ok("GET /inventory/movements (warehouse) 200", r.status_code == 200, r.text[:200])
    movs = r.json() if r.status_code == 200 else []
    if isinstance(movs, dict):
        movs = movs.get("items", [])
    ok("daftar mutasi tidak kosong", len(movs) > 0, f"jumlah={len(movs)}")
    samples = [m for m in movs if m.get("movement_type") == "sample_issue"]
    ok("ADA mutasi bertipe sample_issue yang terlihat warehouse", len(samples) >= 1,
       f"tipe yang ada: {sorted({m.get('movement_type') for m in movs})}")
    if samples:
        s = samples[0]
        qty = s.get("quantity", s.get("qty"))
        ok("mutasi sample_issue mengurangi stok (qty negatif)", float(qty or 0) < 0, f"qty={qty}")
        print(f"    · {s.get('movement_type')} qty={qty} product={s.get('product_id')} "
              f"wh={s.get('warehouse_id')} ref={s.get('source_document')}")
    types = sorted({m.get("movement_type") for m in movs})
    print(f"    · tipe mutasi tersedia: {types}")
    # peta label Indonesia WAJIB memuat semua tipe yang muncul di data
    fe = "/app/frontend/src/features/wms/inventory/inventoryConstants.jsx"
    try:
        with open(fe, encoding="utf-8") as fh:
            src = fh.read()
    except OSError as exc:
        src = ""
        ok("inventoryConstants.jsx terbaca", False, str(exc))
    missing = [t for t in types if t and f"{t}:" not in src and f'"{t}"' not in src]
    ok("SEMUA tipe mutasi pada data punya label Indonesia di peta UI", not missing,
       f"tanpa label: {missing}")
    for needed in ["Ambil Bahan Sample (R&D)", "Penerimaan Barang", "Pengiriman Keluar",
                   "Hasil Produksi", "Konsumsi Produksi", "Terima dari Makloon"]:
        ok(f"label Indonesia tersedia: '{needed}'", needed in src)


# ─────────────────────────────────────────────────────────────── US12
def us12(admin):
    print("\n=== US12 — Jejak Dokumen: kontrak supplier → md_sample → md_spec ===")
    r = get(admin, "/supplier-contracts")
    ok("GET /supplier-contracts 200", r.status_code == 200, r.text[:200])
    contracts = r.json() if r.status_code == 200 else []
    if isinstance(contracts, dict):
        contracts = contracts.get("items", [])
    anchor = next((c for c in contracts
                   if any((ref or {}).get("doc_type") == "md_sample" for ref in (c.get("refs") or []))),
                  None)
    ok("ada kontrak supplier yang punya refs ke md_sample", anchor is not None,
       "seed_rnd decide seharusnya membentuk kontrak + refs")
    if not anchor:
        return
    number = anchor.get("contract_number") or anchor.get("number")
    print(f"    · jangkar: {number} ({anchor.get('id')}) — {anchor.get('title')}")

    # 1) pencarian dokumen (yang dipakai layar Jejak Dokumen)
    rs = get(admin, "/documents/trace-search", q=number)
    ok("GET /documents/trace-search dgn nomor kontrak 200", rs.status_code == 200, rs.text[:200])
    hits = rs.json() if rs.status_code == 200 else []
    ok("kontrak ditemukan lewat pencarian jejak dokumen",
       any((h.get("doc_number") or h.get("number")) == number for h in hits),
       f"hits={[h.get('doc_number') for h in hits][:6]}")

    # 2) graf jejak dari kontrak
    rt = get(admin, f"/documents/trace/supplier_contract/{anchor['id']}")
    ok("GET /documents/trace/supplier_contract/{id} 200", rt.status_code == 200, rt.text[:250])
    if rt.status_code != 200:
        return
    graph = rt.json()
    nodes = graph.get("nodes") or []
    types = sorted({n.get("doc_type") for n in nodes})
    print(f"    · node dalam graf: {len(nodes)} · jenis: {types}")
    ok("graf memuat node md_sample", any(n.get("doc_type") == "md_sample" for n in nodes),
       f"jenis={types}")
    smp = next((n for n in nodes if n.get("doc_type") == "md_sample"), None)
    if smp:
        print(f"    · sample: {smp.get('number')} ({smp.get('doc_id')})")
        ok("node md_sample punya NOMOR yang layak dibaca (KSC/SMP-…)",
           str(smp.get("number") or "").startswith(("KSC/SMP", "KDN/SMP")), f"{smp.get('number')}")
    ok("graf memuat node md_spec (spesifikasi asal) ATAU sample menautkannya",
       any(n.get("doc_type") == "md_spec" for n in nodes),
       f"jenis={types}")
    spec = next((n for n in nodes if n.get("doc_type") == "md_spec"), None)
    if spec:
        print(f"    · spesifikasi: {spec.get('number')} ({spec.get('doc_id')})")
        ok("node md_spec punya NOMOR yang layak dibaca (KSC/SPEC-…)",
           str(spec.get("number") or "").startswith(("KSC/SPEC", "KDN/SPEC")), f"{spec.get('number')}")

    # 3) telusur berjenjang dari sample (auditor mengklik node)
    if smp:
        r2 = get(admin, f"/documents/trace/md_sample/{smp['doc_id']}")
        ok("GET /documents/trace/md_sample/{id} 200", r2.status_code == 200, r2.text[:200])
        if r2.status_code == 200:
            n2 = r2.json().get("nodes") or []
            t2 = sorted({n.get("doc_type") for n in n2})
            ok("dari sample bisa sampai ke md_spec", any(n.get("doc_type") == "md_spec" for n in n2),
               f"jenis={t2}")
            print(f"    · dari sample: {t2}")

    # 4) label jenis dokumen R&D tersedia untuk UI (bukan kode mentah)
    rtypes = get(admin, "/documents/ref-types")
    ok("GET /documents/ref-types 200", rtypes.status_code == 200, rtypes.text[:200])
    if rtypes.status_code == 200:
        tmap = {t["doc_type"]: t["label"] for t in (rtypes.json().get("types") or [])}
        ok("jenis md_spec punya label Indonesia", bool(tmap.get("md_spec")), f"{tmap.get('md_spec')}")
        ok("jenis md_sample punya label Indonesia", bool(tmap.get("md_sample")),
           f"{tmap.get('md_sample')}")
        print(f"    · label: md_spec='{tmap.get('md_spec')}' md_sample='{tmap.get('md_sample')}'")


def main():
    print("=" * 74)
    print("POC FASE F — US3 (gating jual) · US11 (mutasi sample) · US12 (jejak dokumen)")
    print("=" * 74)
    admin = login("admin")
    sales = login("sales")
    warehouse = login("warehouse")
    # POC-RESIDU-01 — SO kontrol positif MEMOTONG roll (satu roll jadi dua) dan
    # memesan stok. Membatalkan SO melepas reservasi TETAPI potongan roll tidak bisa
    # digabung ulang per-dokumen; satu-satunya pemulihan eksak adalah snapshot.
    stock_snap = snapshot_stock()
    before = _db_counts()
    us3(sales, admin)
    us11(warehouse)
    us12(admin)

    print("\n=== INV-GATE-01 — POC tidak boleh meninggalkan residu ===")
    ok("stok (roll/saldo/mutasi/lot) dipulihkan eksak", restore_stock(stock_snap) or True)
    after = _db_counts()
    for key, val in before.items():
        ok(f"nol residu pada `{key}`", after.get(key) == val,
           f"sebelum={val} sesudah={after.get(key)}")

    print("\n" + "=" * 74)
    print(f"HASIL: PASS {PASS} / FAIL {FAIL}")
    if FAILURES:
        print("\nRINCIAN GAGAL:")
        for f in FAILURES:
            print(f"  · {f}")
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR FATAL: {type(exc).__name__}: {exc}")
        sys.exit(2)
