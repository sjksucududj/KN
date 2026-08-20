"""Probe: telusuri perilaku nyata pengaturan entitas + akun tertaut entitas.

Tujuan: menemukan cacat NYATA (bukan asumsi) pada
1) penambahan entitas (provisioning),
2) pemilihan entitas (switcher / X-Entity-Id / mode "all"),
3) pembuatan akun yang tertaut entitas.
"""
import json
import os
import sys
import time

import requests

BASE = "http://localhost:8001/api"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}


def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code != 200:
        return None, r
    return r.json(), r


def h(token, entity=None):
    hh = {"Authorization": f"Bearer {token}"}
    if entity:
        hh["X-Entity-Id"] = entity
    return hh


def show(label, resp, keys=None):
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:200]
    if keys and isinstance(body, dict):
        body = {k: body.get(k) for k in keys}
    if isinstance(body, list):
        body = f"list[{len(body)}] {json.dumps(body[:2], ensure_ascii=False)[:300]}"
    print(f"  [{resp.status_code}] {label}: {json.dumps(body, ensure_ascii=False)[:600] if not isinstance(body, str) else body}")


def main():
    out = {}
    admin, _ = login(**ADMIN)
    if not admin:
        print("FATAL: admin login gagal")
        return 1
    at = admin["token"]
    print("== 1. Konteks entitas admin ==")
    print("  ", json.dumps(admin["entity_context"], ensure_ascii=False)[:400])

    stamp = str(int(time.time()))[-5:]
    print("\n== 2. Provisioning entitas baru (POST /entities) ==")
    payload = {"legal_name": f"PT Probe Nusantara {stamp}", "short_name": f"PRB{stamp}",
               "type": "PT", "npwp": "01.234.567.8-999.000", "address": "Jl Probe 1",
               "city": "Bandung", "default_tax_mode": "ppn", "doc_prefix": f"PRB{stamp}"}
    r = requests.post(f"{BASE}/entities", json=payload, headers=h(at), timeout=30)
    show("create entity", r)
    new_ent = r.json().get("id") if r.status_code == 200 else None

    print("\n== 2b. Duplikat short_name & doc_prefix ==")
    r = requests.post(f"{BASE}/entities", json=payload, headers=h(at), timeout=30)
    show("create entity duplikat", r)

    print("\n== 2c. Payload minimal (tanpa doc_prefix) ==")
    r = requests.post(f"{BASE}/entities", json={"legal_name": f"CV Probe Minim {stamp}",
                                                "short_name": f"PMN{stamp}"}, headers=h(at), timeout=30)
    show("create entity minimal", r)
    min_ent = r.json().get("id") if r.status_code == 200 else None

    print("\n== 3. Apakah entitas baru siap pakai? (gudang / pelanggan / nomor dokumen / CoA) ==")
    for path in ["warehouses", "customers", "products", "sales-orders", "gl/accounts",
                 "settings/effective", "bank-accounts"]:
        r = requests.get(f"{BASE}/{path}", headers=h(at, new_ent), timeout=30)
        show(f"GET {path} @entitas baru", r)

    print("\n== 4. Buat akun sales tertaut entitas baru ==")
    ur = requests.post(f"{BASE}/users", json={
        "name": f"Sales Probe {stamp}", "email": f"sales.probe{stamp}@kn.id",
        "role": "sales", "password": "probe12345", "home_entity_id": new_ent,
        "allowed_entity_ids": [new_ent]}, headers=h(at), timeout=30)
    show("create user (home=entitas baru)", ur)

    print("\n== 4b. Buat akun dengan home_entity_id KOSONG (perilaku default) ==")
    ur2 = requests.post(f"{BASE}/users", json={
        "name": f"Sales NoEnt {stamp}", "email": f"sales.noent{stamp}@kn.id",
        "role": "sales", "password": "probe12345"}, headers=h(at), timeout=30)
    show("create user tanpa entitas", ur2, keys=["id", "email", "home_entity_id", "allowed_entity_ids"])

    print("\n== 4c. Buat akun dengan home_entity_id NGAWUR ==")
    ur3 = requests.post(f"{BASE}/users", json={
        "name": "Sales Ngawur", "email": f"sales.ngawur{stamp}@kn.id",
        "role": "sales", "password": "probe12345", "home_entity_id": "ent_tidak_ada"},
        headers=h(at), timeout=30)
    show("create user entitas ngawur", ur3)

    print("\n== 5. Login akun baru → apa yang dilihat? ==")
    su, sr = login(f"sales.probe{stamp}@kn.id", "probe12345")
    if not su:
        show("login sales baru GAGAL", sr)
    else:
        print("  entity_context:", json.dumps(su["entity_context"], ensure_ascii=False)[:400])
        st = su["token"]
        for path in ["dashboard", "customers", "warehouses", "products", "sales-orders"]:
            r = requests.get(f"{BASE}/{path}", headers=h(st), timeout=30)
            try:
                d = r.json()
                n = len(d) if isinstance(d, list) else (len(d.get("products", [])) if isinstance(d, dict) else "?")
            except Exception:
                n = "?"
            print(f"  [{r.status_code}] sales baru GET {path} → {n} baris")
        # coba buat SO tanpa pelanggan/produk milik entitasnya
        r = requests.get(f"{BASE}/auth/context", headers=h(st, "all"), timeout=20)
        show("sales minta X-Entity-Id=all", r, keys=["active_entity_id", "allowed_entity_ids"])

    print("\n== 6. Mode 'Semua Entitas' (admin) — tulis ke mana? ==")
    r = requests.post(f"{BASE}/customers", json={"name": f"Probe Cust {stamp}", "pic_name": "PIC",
                                                 "phone": "0811", "city": "Bandung", "address": "Jl A"},
                      headers=h(at, "all"), timeout=30)
    show("POST /customers dengan X-Entity-Id=all", r, keys=["id", "name", "entity_id"])

    print("\n== 7. PATCH entitas (ubah nama & mode pajak) ==")
    if new_ent:
        r = requests.patch(f"{BASE}/entities/{new_ent}",
                           json={"data": {"legal_name": f"PT Probe Nusantara {stamp} (Revisi)",
                                          "default_tax_mode": "non_ppn", "city": "Solo"}},
                           headers=h(at), timeout=30)
        show("PATCH entity", r, keys=["id", "legal_name", "default_tax_mode", "city"])
        # doc_prefix ganti → apakah diizinkan meski dokumen sudah pakai prefix lama?
        r = requests.patch(f"{BASE}/entities/{new_ent}", json={"data": {"doc_prefix": "ZZZ"}},
                           headers=h(at), timeout=30)
        show("PATCH doc_prefix (tanpa cek unik?)", r, keys=["id", "doc_prefix"])
        # coba tabrak prefix entitas lain
        r = requests.patch(f"{BASE}/entities/{new_ent}", json={"data": {"doc_prefix": "KSC"}},
                           headers=h(at), timeout=30)
        show("PATCH doc_prefix jadi KSC (duplikat!)", r, keys=["id", "doc_prefix"])

    print("\n== 8. Deaktivasi entitas yang punya user aktif ==")
    if min_ent:
        r = requests.delete(f"{BASE}/entities/{min_ent}", headers=h(at), timeout=30)
        show("DELETE entity kosong", r, keys=["id", "status"])
    if new_ent:
        r = requests.delete(f"{BASE}/entities/{new_ent}", headers=h(at), timeout=30)
        show("DELETE entity yang dipakai user", r, keys=["id", "status"])
        # user-nya masih bisa login?
        su2, sr2 = login(f"sales.probe{stamp}@kn.id", "probe12345")
        if su2:
            print("  login sales setelah entitasnya nonaktif:",
                  json.dumps(su2["entity_context"], ensure_ascii=False)[:300])
        else:
            show("login sales setelah entitas nonaktif", sr2)
        # reaktivasi
        r = requests.patch(f"{BASE}/entities/{new_ent}", json={"data": {"status": "active"}},
                           headers=h(at), timeout=30)
        show("reaktivasi entity", r, keys=["id", "status"])

    print("\n== 9. Non-admin coba buat entitas ==")
    m, _ = login("manager@kainnusantara.id", "demo12345")
    s, _ = login("sales@kainnusantara.id", "demo12345")
    for label, u in [("manager", m), ("sales", s)]:
        if not u:
            continue
        r = requests.post(f"{BASE}/entities", json={"legal_name": "PT Nakal", "short_name": f"NKL{stamp}{label[:2]}"},
                          headers=h(u["token"]), timeout=30)
        show(f"{label} POST /entities", r)
        r = requests.get(f"{BASE}/entities", headers=h(u["token"]), timeout=30)
        try:
            print(f"  [{r.status_code}] {label} GET /entities → {len(r.json())} entitas")
        except Exception:
            show(f"{label} GET /entities", r)

    print("\n== 10. Field yang tersimpan pada entitas baru ==")
    if new_ent:
        r = requests.get(f"{BASE}/entities/{new_ent}", headers=h(at), timeout=20)
        print("  ", json.dumps(r.json(), ensure_ascii=False, indent=1)[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
