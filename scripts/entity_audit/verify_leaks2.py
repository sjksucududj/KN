#!/usr/bin/env python3
"""Verifikasi kedua: endpoint AGREGAT & master data (apakah angkanya per-PT?)."""
import json
import requests

BASE = "http://localhost:8001/api"
A, B = "ent_ksc", "ent_kanda"


def login(e, p="demo12345"):
    return requests.post(f"{BASE}/auth/login", json={"email": e, "password": p}, timeout=20).json()["token"]


TA, TB, TADM = login("sales@kainnusantara.id"), login("sales3@kainnusantara.id"), login("admin@kainnusantara.id")


def get(path, tok, ent=None):
    h = {"Authorization": f"Bearer {tok}"}
    if ent:
        h["X-Entity-Id"] = ent
    r = requests.get(f"http://localhost:8001{path}", headers=h, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


print("=" * 78)
print(" 1. PAPAN STATUS STOK — apakah sales PT-B melihat angka stok PT-A?")
print("=" * 78)
for label, tok in [("sales PT-A", TA), ("sales PT-B", TB)]:
    st, body = get("/api/inventory/status-board", tok)
    rows = body if isinstance(body, list) else body.get("items", [])
    tot = sum(float(r.get("available_qty") or r.get("qty_available") or 0) for r in rows if isinstance(r, dict))
    print(f"  [{st}] {label}: {len(rows)} baris SKU · Σ tersedia = {tot}")
    if rows:
        print("      contoh baris:", json.dumps(rows[0], ensure_ascii=False)[:400])

print("\n" + "=" * 78)
print(" 2. BUKU BESAR STOK — cari jejak entitas lain di dalam baris")
print("=" * 78)
for label, tok, own in [("sales PT-A", TA, A), ("sales PT-B", TB, B)]:
    st, body = get("/api/inventory/movements", tok)
    rows = body if isinstance(body, list) else body.get("items", [])
    hits = []
    other = B if own == A else A
    for r in rows:
        s = json.dumps(r, ensure_ascii=False)
        if other in s:
            hits.append({k: v for k, v in r.items() if other in json.dumps(v, ensure_ascii=False) or k in ("id", "product_name", "movement_type")})
    print(f"  [{st}] {label}: {len(rows)} baris · baris menyebut PT lain = {len(hits)}")
    for hh in hits[:3]:
        print("      ", json.dumps(hh, ensure_ascii=False)[:300])

print("\n" + "=" * 78)
print(" 3. NERACA SALDO (trial balance) — apakah beda per PT?")
print("=" * 78)
sig = {}
for label, ent in [("KSC", A), ("KANDA", B), ("ALL", "all")]:
    st, body = get("/api/gl/trial-balance", TADM, ent)
    rows = (body or {}).get("rows", [])
    tot_d = sum(float(r.get("debit") or 0) for r in rows)
    tot_k = sum(float(r.get("credit") or 0) for r in rows)
    sig[label] = (len(rows), tot_d, tot_k)
    print(f"  {label:6s} [{st}] {len(rows)} akun · debit={tot_d:,.0f} · kredit={tot_k:,.0f}")
print("  → KSC == KANDA ?", "YA (BERARTI TERCAMPUR!)" if sig["KSC"] == sig["KANDA"] else "tidak (terpisah, benar)")

print("\n" + "=" * 78)
print(" 4. AR AGING — respons melaporkan entity_id apa?")
print("=" * 78)
for label, ent in [("KSC", A), ("KANDA", B), ("ALL", "all")]:
    st, body = get("/api/ar/aging", TADM, ent)
    b = body or {}
    rows = b.get("rows") or b.get("items") or b.get("buckets") or []
    ents = set()
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("entity_id"):
            ents.add(r["entity_id"])
    print(f"  {label:6s} [{st}] entity_id dilaporkan = {b.get('entity_id')!r} · "
          f"{len(rows) if isinstance(rows, list) else '?'} baris · entitas di baris = {sorted(ents) or '-'}")
    print("      total:", json.dumps(b.get("totals") or b.get("summary") or {}, ensure_ascii=False)[:200])
st, body = get("/api/ar/aging", TB)
b = body or {}
rows = b.get("rows") or b.get("items") or []
print(f"  sales PT-B [{st}] entity_id={b.get('entity_id')!r} baris={len(rows) if isinstance(rows, list) else '?'}"
      f" → {json.dumps(rows[:2], ensure_ascii=False)[:300] if isinstance(rows, list) else ''}")

print("\n" + "=" * 78)
print(" 5. NOMOR DOKUMEN per PT")
print("=" * 78)
st, body = get("/api/sales-orders?entity_id=all", TADM, "all")
for r in (body if isinstance(body, list) else body.get("items", []))[:12]:
    print(f"   {str(r.get('order_number')):20s} entity={str(r.get('entity_id')):12s} cust={r.get('customer_name')}")
st, body = get("/api/purchase-orders?entity_id=all", TADM, "all")
for r in (body if isinstance(body, list) else body.get("items", []))[:10]:
    print(f"   {str(r.get('po_number')):20s} entity={str(r.get('entity_id')):12s} supplier={r.get('supplier_name')}")

print("\n" + "=" * 78)
print(" 6. MASTER DATA — identik antar PT atau terpisah?")
print("=" * 78)
for path in ["/api/products", "/api/warehouses", "/api/uoms", "/api/document-templates",
             "/api/payment-terms", "/api/product-categories", "/api/color-library",
             "/api/suppliers", "/api/customers", "/api/incentive-rates", "/api/approval-rules",
             "/api/bank-accounts", "/api/gl/accounts", "/api/pricelist", "/api/customer-prices/records",
             "/api/sales-return-policies", "/api/makloons", "/api/supplier-contracts",
             "/api/hr/employees", "/api/hr/org-units", "/api/expense-categories"]:
    sa, ba = get(path, TADM, A)
    sb, bb = get(path, TADM, B)
    ra = ba if isinstance(ba, list) else (ba or {}).get("items", []) if isinstance(ba, dict) else []
    rb = bb if isinstance(bb, list) else (bb or {}).get("items", []) if isinstance(bb, dict) else []
    ida = {r.get("id") for r in ra if isinstance(r, dict)}
    idb = {r.get("id") for r in rb if isinstance(r, dict)}
    if not ida and not idb:
        verd = f"kosong (A:{sa} B:{sb})"
    elif ida == idb:
        verd = "IDENTIK (shared)"
    elif ida & idb:
        verd = f"SEBAGIAN sama ({len(ida & idb)} irisan)"
    else:
        verd = "TERPISAH penuh"
    print(f"  {path:34s} A={len(ra):4d} B={len(rb):4d} → {verd}")

print("\n" + "=" * 78)
print(" 7. HARGA — apakah bisa beda per PT? (entity_prices / pricelist)")
print("=" * 78)
for ent in [A, B]:
    st, body = get("/api/pricelist", TADM, ent)
    rows = body if isinstance(body, list) else (body or {}).get("items", [])
    print(f"  {ent}: [{st}] {len(rows)} baris harga PT")
    for r in rows[:3]:
        print("      ", json.dumps({k: r.get(k) for k in ("product_id", "sku", "entity_id", "price", "entity_price", "base_price")}, ensure_ascii=False))
