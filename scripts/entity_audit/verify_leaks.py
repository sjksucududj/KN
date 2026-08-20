#!/usr/bin/env python3
"""Verifikasi PRESISI kandidat kebocoran lintas-entitas (bukti baris demi baris)."""
import json
import requests

BASE = "http://localhost:8001/api"
A, B = "ent_ksc", "ent_kanda"


def login(e, p="demo12345"):
    return requests.post(f"{BASE}/auth/login", json={"email": e, "password": p}, timeout=20).json()["token"]


TA = login("sales@kainnusantara.id")       # sales PT-A (ent_ksc)
TB = login("sales3@kainnusantara.id")      # sales PT-B (ent_kanda)
TADM = login("admin@kainnusantara.id")
TWH = login("warehouse@kainnusantara.id")


def get(path, tok, ent=None):
    h = {"Authorization": f"Bearer {tok}"}
    if ent:
        h["X-Entity-Id"] = ent
    r = requests.get(f"http://localhost:8001{path}", headers=h, timeout=25)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


def rows(body):
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in ("items", "rows", "data", "results", "orders", "records", "lines", "movements", "products"):
            if isinstance(body.get(k), list):
                return body[k]
    return []


def report(title, path, field="entity_id", extra=()):
    print(f"\n── {title}  ({path}) ──")
    for label, tok in [("sales PT-A (KSC)", TA), ("sales PT-B (KANDA)", TB)]:
        st, body = get(path, tok)
        rs = rows(body)
        own = A if "PT-A" in label else B
        foreign = [r for r in rs if isinstance(r, dict) and r.get(field) and r.get(field) != own]
        print(f"  [{st}] {label}: {len(rs)} baris · milik PT lain = {len(foreign)}")
        for r in foreign[:3]:
            keys = ["id", field] + [k for k in extra if k in r]
            print("      BOCOR:", {k: r.get(k) for k in keys})


print("=" * 78)
print("  VERIFIKASI PRESISI — KEBOCORAN LINTAS ENTITAS")
print("=" * 78)

report("1. Buku besar stok (movements)", "/api/inventory/movements", "owner_entity_id",
       extra=("product_name", "qty", "movement_type", "reference"))
report("2. Papan status stok", "/api/inventory/status-board", "owner_entity_id", extra=("sku",))
report("3. Notifikasi", "/api/notifications", "entity_id", extra=("title", "type"))
report("4. Rencana pembayaran", "/api/payment-plans", "entity_id", extra=("plan_number", "customer_name"))
report("5. Selisih pembayaran", "/api/payment-variances", "entity_id", extra=("decision_number",))
report("6. Nota denda", "/api/penalties", "entity_id", extra=("penalty_number",))
report("7. Target sales", "/api/sales-targets", "entity_id", extra=("sales_name", "period"))
report("8. Insentif sales", "/api/sales-incentives", "entity_id", extra=("sales_name", "amount"))
report("9. Faktur pajak keluaran", "/api/tax-invoices", "entity_id", extra=("fkt_number", "customer_name"))
report("10. Pegging roll", "/api/pegging/rolls", "owner_entity_id", extra=("roll_number",))

print("\n── 11. Jejak audit (audit-logs) ──")
for label, tok in [("sales PT-A", TA), ("sales PT-B", TB), ("gudang PT-A", TWH)]:
    st, body = get("/api/audit-logs", tok)
    rs = rows(body)
    print(f"  [{st}] {label}: {len(rs)} baris jejak audit SELURUH GRUP terlihat"
          f" (contoh aksi: {[r.get('action') for r in rs[:4]]})")

print("\n── 12. Apakah dokumen milik PT lain bisa dibuka langsung? (lots) ──")
st, body = get("/api/lots?limit=200", TADM, "all")
lots = rows(body)
kanda = [l for l in lots if l.get("owner_entity_id") == B or l.get("entity_id") == B]
if kanda:
    lid = kanda[0].get("id")
    st2, b2 = get(f"/api/lots/{lid}", TA)
    print(f"  sales PT-A buka lot PT-B {lid} → HTTP {st2}"
          f" {'BOCOR' if st2 == 200 else 'aman'}")
    if st2 == 200:
        print("      isi:", json.dumps({k: b2.get(k) for k in
              ("id", "lot_code", "owner_entity_id", "entity_id", "product_name", "qty_on_hand")},
              ensure_ascii=False))

print("\n── 13. Ringkasan keuangan & dasbor: apakah angkanya per-PT? ──")
for path in ["/api/dashboard", "/api/reports/summary", "/api/gl/trial-balance",
             "/api/financial-statements/profit-loss", "/api/ar/aging",
             "/api/cash-transactions/summary"]:
    out = []
    for label, tok, ent in [("A", TADM, A), ("B", TADM, B), ("ALL", TADM, "all")]:
        st, body = get(path, tok, ent)
        if isinstance(body, dict):
            m = body.get("metrics") or body
            sig = json.dumps(m, ensure_ascii=False)[:90]
        else:
            sig = f"list[{len(body or [])}]"
        out.append(f"{label}[{st}]={sig}")
    print(f"  {path}\n      " + "\n      ".join(out))

print("\n── 14. Nomor dokumen per PT (apakah terpisah?) ──")
st, body = get("/api/sales-orders?entity_id=all", TADM, "all")
for r in rows(body)[:12]:
    print(f"   {r.get('order_number'):18s} entity={r.get('entity_id'):12s} cust={r.get('customer_name')}")

print("\n── 15. Master data BERSAMA (harus sama di semua PT?) ──")
for path, field in [("/api/products", None), ("/api/warehouses", None), ("/api/uoms", None),
                    ("/api/document-templates", None), ("/api/payment-terms", None),
                    ("/api/product-categories", None), ("/api/color-library", None),
                    ("/api/suppliers", "entity_id"), ("/api/customers", "entity_id"),
                    ("/api/incentive-rates", "entity_id"), ("/api/approval-rules", "entity_id"),
                    ("/api/bank-accounts", "entity_id"), ("/api/gl/accounts", "entity_id")]:
    sa, ba = get(path, TADM, A)
    sb, bb = get(path, TADM, B)
    ra, rb = rows(ba), rows(bb)
    ida = {r.get("id") for r in ra if isinstance(r, dict)}
    idb = {r.get("id") for r in rb if isinstance(r, dict)}
    same = "IDENTIK" if ida and ida == idb else ("BEDA" if ida != idb else "kosong")
    print(f"  {path:32s} A={len(ra):4d} B={len(rb):4d} → {same}")
