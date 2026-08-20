"""Probe lanjutan: cacat pada pengelolaan akun tertaut entitas."""
import json
import time
import requests

BASE = "http://localhost:8001/api"


def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=20)
    return (r.json() if r.status_code == 200 else None), r


def h(t, e=None):
    hh = {"Authorization": f"Bearer {t}"}
    if e:
        hh["X-Entity-Id"] = e
    return hh


def show(label, r, keys=None):
    try:
        b = r.json()
    except Exception:
        b = r.text[:200]
    if keys and isinstance(b, dict):
        b = {k: b.get(k) for k in keys}
    print(f"  [{r.status_code}] {label}: {json.dumps(b, ensure_ascii=False)[:400] if not isinstance(b, str) else b}")


admin, _ = login("admin@kainnusantara.id", "demo12345")
at = admin["token"]
stamp = str(int(time.time()))[-5:]

print("== A. DELETE /users/{id} (tombol 'Deactivate' di tab Users) ==")
u = requests.post(f"{BASE}/users", json={"name": f"Uji Hapus {stamp}", "email": f"uji.hapus{stamp}@kn.id",
                                         "role": "sales", "password": "probe12345"}, headers=h(at), timeout=20)
uid = u.json().get("id")
r = requests.delete(f"{BASE}/users/{uid}", headers=h(at), timeout=20)
show("DELETE /users/{id}", r)

print("\n== B. PATCH /users → email duplikat ==")
r = requests.patch(f"{BASE}/users/{uid}", json={"data": {"email": "admin@kainnusantara.id"}},
                   headers=h(at), timeout=20)
show("PATCH email jadi email admin", r, keys=["id", "email"])
n = 0
try:
    lst = requests.get(f"{BASE}/users", headers=h(at), timeout=20).json()
    n = len([x for x in lst if x.get("email") == "admin@kainnusantara.id"])
except Exception:
    pass
print(f"  → jumlah user dengan email admin@kainnusantara.id sekarang: {n}")
requests.patch(f"{BASE}/users/{uid}", json={"data": {"email": f"uji.hapus{stamp}@kn.id"}}, headers=h(at), timeout=20)

print("\n== C. Turunkan role admin→sales: apakah akses lintas-PT ikut turun? ==")
u2 = requests.post(f"{BASE}/users", json={"name": f"Bekas Admin {stamp}", "email": f"bekas.admin{stamp}@kn.id",
                                          "role": "admin", "password": "probe12345"}, headers=h(at), timeout=20)
print("  buat admin:", json.dumps({k: u2.json().get(k) for k in ["id", "role", "allowed_entity_ids"]}, ensure_ascii=False))
u2id = u2.json()["id"]
r = requests.patch(f"{BASE}/users/{u2id}", json={"data": {"role": "sales"}}, headers=h(at), timeout=20)
show("PATCH role admin→sales", r, keys=["id", "role", "home_entity_id", "allowed_entity_ids"])
su, _ = login(f"bekas.admin{stamp}@kn.id", "probe12345")
print("  konteks setelah jadi sales:", json.dumps(su["entity_context"], ensure_ascii=False)[:260] if su else "gagal login")

print("\n== D. PATCH password lewat data.password → bisa login? ==")
r = requests.patch(f"{BASE}/users/{u2id}", json={"data": {"password": "ganti99999"}}, headers=h(at), timeout=20)
print("  status patch:", r.status_code)
su2, sr2 = login(f"bekas.admin{stamp}@kn.id", "ganti99999")
print("  login dgn password baru:", "OK" if su2 else f"GAGAL {sr2.status_code}")

print("\n== E. Entitas nonaktif tetap muncul di GET /entities (dipakai switcher FE) ==")
ents = requests.get(f"{BASE}/entities", headers=h(at), timeout=20).json()
print("  daftar:", json.dumps([{"id": e["id"], "short": e.get("short_name"), "status": e.get("status"),
                                "prefix": e.get("doc_prefix")} for e in ents], ensure_ascii=False))
inactive = [e for e in ents if e.get("status") != "active"]
if inactive:
    eid = inactive[0]["id"]
    r = requests.get(f"{BASE}/auth/context", headers=h(at, eid), timeout=20)
    show(f"pilih entitas NONAKTIF {eid} sebagai konteks", r, keys=["active_entity_id"])
    r = requests.post(f"{BASE}/customers", json={"name": f"Cust di PT mati {stamp}", "pic_name": "x",
                                                 "phone": "08", "city": "x", "address": "x"},
                      headers=h(at, eid), timeout=20)
    show("POST /customers ke entitas NONAKTIF", r, keys=["id", "entity_id"])

print("\n== F. Nomor dokumen: dua entitas dengan doc_prefix sama ==")
dup = {}
for e in ents:
    dup.setdefault(e.get("doc_prefix"), []).append(e.get("short_name"))
print("  prefix ganda:", {k: v for k, v in dup.items() if len(v) > 1})

print("\n== G. GET /users — apakah ada penyaring entitas / paging? ==")
r = requests.get(f"{BASE}/users?entity_id=ent_ksc", headers=h(at), timeout=20)
try:
    print(f"  [{r.status_code}] jumlah user (param entity_id diabaikan?): {len(r.json())}")
except Exception:
    show("GET users", r)
