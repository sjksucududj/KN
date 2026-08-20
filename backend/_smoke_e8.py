"""Smoke cepat E-8 saat membangun (BUKAN pengganti POC `test_core_e8_desk_poc.py`)."""
import json
import os
import urllib.error
import urllib.request

API = os.environ.get("KN_API", "http://localhost:8001/api")


def call(method, path, token="", entity="ent_ksc", body=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if entity:
        req.add_header("X-Entity-Id", entity)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "null")
        except json.JSONDecodeError:
            return e.code, raw[:300]


def login(email):
    _, d = call("POST", "/auth/login", entity="",
                body={"email": email, "password": "demo12345"})
    return (d or {}).get("token", "")


SA = login("salesadmin@kainnusantara.id")
FI = login("finance@kainnusantara.id")
S1 = login("sales@kainnusantara.id")

_, orders = call("GET", "/sales-orders", SA)
so9 = next((o for o in orders if o.get("number") == "SO-0009"), {})
oid = so9.get("id", "")
print("SO-0009 id =", oid, "| status =", so9.get("status"))

print("\n--- US12 perjalanan SO-0001 (sales) ---")
st, j = call("GET", "/sales-orders/so_001/journey", S1)
print(" ", st, j.get("order_number"), "|", j.get("current_label"), "|", j.get("progress"))
for s in (j.get("steps") or []):
    print("    ", "v" if s["done"] else ".", s["label"], "|", s["detail"][:55])
print("  pemenuhan:", (j.get("fulfillment") or {}).get("sentence", "")[:100])

print("\n--- US16 pilihan pemenuhan ---")
st, f = call("GET", f"/sales-admin/orders/{oid}/fulfillment", SA)
print(" ", st)
if isinstance(f, dict) and "options" in f:
    print("  kekurangan:",
          [(s["product_name"], s["backorder_qty"], s["unit"]) for s in f["shortages"]])
    for k, v in f["options"].items():
        print(f"   {k:9s} tersedia={v['available']} · {v.get('reason','')[:60]}")
    for c in f["options"]["interco"]["candidates"]:
        print("     kandidat:", c["entity_name"], "cukup=", c["enough"],
              [(l["product_name"][:20], l["available"], l["needed"]) for l in c["lines"]])
else:
    print("  GAGAL:", str(f)[:400])

print("\n--- E8.13 pratinjau verifikasi ---")
st, v = call("GET", f"/sales-orders/{oid}/verification", SA)
print(" ", st, "ready=", v.get("ready") if isinstance(v, dict) else v)
if isinstance(v, dict):
    print("  blocking:", v.get("blocking_gaps"), "| warn:", v.get("warnings"))
    for c in (v.get("checks") or []):
        print("    ", "v" if c["ok"] else "x", c["label"], "|", c["detail"][:55])

print("\n--- Meja Admin Sales ---")
st, d = call("GET", "/sales-admin/desk", SA)
print(" ", st, "| open_items:", (d.get("totals") or {}).get("open_items"))
for q in (d.get("queues") or []):
    print(f"   {q['id']:22s} n={q['count']:3d} nilai={q['total_value']:>16,.0f} "
          f"tertua={q['oldest_age_days']}h · {q['action_label']}")

print("\n--- Meja Finance ---")
st, d = call("GET", "/finance/desk", FI)
print(" ", st, "| open_items:", (d.get("totals") or {}).get("open_items"))
for q in (d.get("queues") or []):
    print(f"   {q['id']:22s} n={q['count']:3d} nilai={q['total_value']:>16,.0f} "
          f"· {q['action_label']}")
