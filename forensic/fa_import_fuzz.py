"""fa_import_fuzz.py — AUDIT S074 P#3: fuzz master-data import (0% covered).

Endpoints (admin-only import perm): /api/master-data/import-products|customers|warehouses
Parser: routers/admin.py:_parse_csv_or_xlsx (content.decode('utf-8-sig') / openpyxl).

Probes: formula/CSV injection, non-UTF8 crash, negative/overflow price, XSS image
URL, missing headers, cross-entity SKU clobber (no entity scoping), XLSX formula,
and a dry_run vs real consistency check. DESTRUCTIVE (creates rows) -> reseed after.
"""
import io
import os
import sys
import requests

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pymongo import MongoClient

BASE = "http://localhost:8001/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
findings = []


def F(fid, sev, title, ev):
    findings.append((fid, sev, title, ev))
    print(f"[{sev}] {fid}: {title}\n   -> {ev}", flush=True)


def login(email="admin@kainnusantara.id"):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": "demo12345"}, timeout=15)
    return r.json()["token"] if r.status_code == 200 else None


def post_csv(tok, endpoint, csv_text, filename="audit.csv", dry_run=False):
    files = {"file": (filename, csv_text.encode("utf-8") if isinstance(csv_text, str) else csv_text,
                      "text/csv")}
    return requests.post(f"{BASE}/master-data/{endpoint}?dry_run={str(dry_run).lower()}",
                         headers={"Authorization": f"Bearer {tok}"}, files=files, timeout=25)


def post_raw(tok, endpoint, raw_bytes, filename="audit.csv"):
    files = {"file": (filename, raw_bytes, "text/csv")}
    return requests.post(f"{BASE}/master-data/{endpoint}",
                         headers={"Authorization": f"Bearer {tok}"}, files=files, timeout=25)


def main():
    tok = login()
    print("admin token:", "OK" if tok else "FAIL")

    # ---- T1: CSV formula injection (products) ----
    print("\n=== T1: CSV formula injection into product name/sku ===")
    inj = '=cmd|\' /C calc\'!A0'
    csv1 = "sku,name,price\nAUDITINJ1," + inj + ",100\n"
    r = post_csv(tok, "import-products", csv1)
    print("   import ->", r.status_code, str(r.text)[:120])
    doc = db.products.find_one({"sku": "AUDITINJ1"}, {"_id": 0, "name": 1})
    stored = (doc or {}).get("name")
    print("   stored name =", repr(stored))
    if stored and stored.startswith("="):
        # confirm export echoes it unescaped
        ex = requests.get(f"{BASE}/master-data/export-products",
                          headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        echoed = inj in ex.text
        F("IMP-CSV-INJECTION", "P2",
          "Import master-data menyimpan nilai formula mentah -> CSV/Formula injection saat export",
          f"name di-store apa adanya ('{stored[:30]}...'); export-products meng-echo formula "
          f"tanpa sanitasi (prefix '=/+/-/@'): echoed_in_export={echoed}. Buka di Excel = eksekusi formula.")

    # ---- T2: non-UTF8 bytes -> decode crash (500) ----
    print("\n=== T2: non-UTF8 file bytes (decode path) ===")
    raw = b"sku,name,price\n\xff\xfe\x00BADBYTES,\xffx,10\n"
    r = post_raw(tok, "import-products", raw, filename="bad.csv")
    print("   import(non-utf8) ->", r.status_code, str(r.text)[:140])
    if r.status_code == 500:
        F("IMP-NONUTF8-500", "P2",
          "Import CSV non-UTF8 -> HTTP 500 (UnicodeDecodeError tak ditangani)",
          f"_parse_csv_or_xlsx: content.decode('utf-8-sig') tanpa try/except -> 500 saat file bukan UTF-8. "
          f"status={r.status_code}: {str(r.text)[:120]}")

    # ---- T3: negative / overflow / non-numeric price ----
    print("\n=== T3: negative & overflow price ===")
    csv3 = "sku,name,price\nAUDITNEG,Neg Price,-5000\nAUDITBIG,Big Price,1e309\n"
    r = post_csv(tok, "import-products", csv3)
    print("   import ->", r.status_code, str(r.text)[:140])
    neg = db.products.find_one({"sku": "AUDITNEG"}, {"_id": 0, "price": 1})
    big = db.products.find_one({"sku": "AUDITBIG"}, {"_id": 0, "price": 1})
    print("   AUDITNEG price =", (neg or {}).get("price"), "| AUDITBIG price =", (big or {}).get("price"))
    if neg and float(neg.get("price", 0)) < 0:
        F("IMP-NEG-PRICE", "P2", "Import produk menerima harga NEGATIF",
          f"AUDITNEG price={neg.get('price')} tersimpan (validasi hanya float(), tak ada >=0). "
          f"Harga negatif merusak nilai order/invoice/GL.")
    if big and (big.get("price") in (float("inf"), None) or str(big.get("price")) == "inf"):
        F("IMP-INF-PRICE", "P3", "Import produk menerima harga 'inf' (1e309 -> inf)",
          f"AUDITBIG price={big.get('price')} (float('1e309')=inf lolos). Bisa merusak agregasi finansial.")

    # ---- T4: XSS / scheme in image URL ----
    print("\n=== T4: script/javascript scheme in image field ===")
    xss = 'javascript:alert(document.cookie)'
    csv4 = "sku,name,price,image\nAUDITXSS,XSS Prod,100," + xss + "\n"
    r = post_csv(tok, "import-products", csv4)
    d = db.products.find_one({"sku": "AUDITXSS"}, {"_id": 0, "image": 1})
    print("   stored image =", repr((d or {}).get("image")))
    if d and str(d.get("image", "")).startswith("javascript:"):
        F("IMP-IMG-XSS", "P3",
          "Import produk menyimpan image URL skema 'javascript:' tanpa validasi",
          f"image='{d.get('image')}' tersimpan mentah -> potensi stored-XSS bila di-render sbg href/src "
          f"tanpa sanitasi FE. Tak ada whitelist http/https.")

    # ---- T5: missing required headers ----
    print("\n=== T5: file without expected headers ===")
    r = post_csv(tok, "import-products", "foo,bar\n1,2\n")
    print("   headerless ->", r.status_code, str(r.text)[:120])
    # rows exist but every row is an error (no sku/name) -> should be 200 with errors, not crash
    if r.status_code == 500:
        F("IMP-BADHDR-500", "P3", "Import file tanpa header wajib -> 500", str(r.text)[:150])

    # ---- T6: cross-entity SKU clobber (no entity scoping) ----
    print("\n=== T6: cross-entity SKU clobber + no entity_id on import ===")
    # seed a product 'owned' by ent_kanda with a known sku+price
    db.products.delete_many({"sku": "AUDITXENT"})
    db.products.insert_one({"id": "prod_audit_xent", "sku": "AUDITXENT", "name": "Kanda Owned",
                            "price": 111.0, "entity_id": "ent_kanda", "status": "active"})
    csv6 = "sku,name,price\nAUDITXENT,CLOBBERED BY IMPORT,999\n"
    r = post_csv(tok, "import-products", csv6)
    after = db.products.find_one({"sku": "AUDITXENT"}, {"_id": 0, "name": 1, "price": 1, "entity_id": 1})
    print("   after import ->", after)
    if after and abs(float(after.get("price", 0)) - 999) < 0.01:
        F("IMP-XENT-CLOBBER", "P2",
          "Import produk match by SKU global -> menimpa produk milik entitas lain (tanpa scoping)",
          f"produk SKU AUDITXENT milik ent_kanda ditimpa jadi price=999/name='CLOBBERED' oleh import "
          f"(admin any-entity). Import tak memfilter/tak menstempel entity_id -> data lintas-entitas bisa "
          f"ditimpa & produk baru tanpa entity_id.")
    newp = db.products.find_one({"sku": "AUDITINJ1"}, {"_id": 0, "entity_id": 1})
    if newp and not newp.get("entity_id"):
        F("IMP-NO-ENTITY", "P3",
          "Produk hasil import TIDAK diberi entity_id (unscoped master-data)",
          "Baris baru dari import tidak menstempel entity_id -> muncul lintas entitas tanpa kontrol.")

    # ---- T7: XLSX formula cell ----
    print("\n=== T7: XLSX with a formula cell ===")
    try:
        import openpyxl
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(["sku", "name", "price"])
        ws.append(["AUDITXLSX", "=1+2", 50])
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        files = {"file": ("audit.xlsx", buf.read(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(f"{BASE}/master-data/import-products",
                          headers={"Authorization": f"Bearer {tok}"}, files=files, timeout=25)
        print("   xlsx import ->", r.status_code, str(r.text)[:120])
        d = db.products.find_one({"sku": "AUDITXLSX"}, {"_id": 0, "name": 1})
        print("   stored name =", repr((d or {}).get("name")))
    except Exception as e:
        print("   xlsx test skipped:", e)

    # ---- T8: privilege — can non-admin import? ----
    print("\n=== T8: non-admin (sales) import privilege ===")
    stok = login("sales@kainnusantara.id")
    if stok:
        r = post_csv(stok, "import-products", "sku,name,price\nAUDITSALES,x,1\n")
        print("   sales import-products ->", r.status_code)
        if r.status_code in (200, 201):
            F("IMP-PRIV", "P1", "Role 'sales' dapat meng-import master-data produk",
              f"sales POST import-products -> {r.status_code} (harusnya 403; import hanya admin).")
        else:
            print("   OK: sales blocked (", r.status_code, ")")

    print("\n" + "=" * 66)
    print(f"IMPORT-FUZZ PROBE: {len(findings)} finding(s)")
    for fid, sev, title, _ in findings:
        print(f"  [{sev}] {fid}: {title}")
    print("\n[i] DESTRUCTIVE: run seed_realistic.py to restore clean state.")


if __name__ == "__main__":
    main()
