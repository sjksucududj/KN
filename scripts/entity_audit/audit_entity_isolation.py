#!/usr/bin/env python3
"""AUDIT ISOLASI ENTITAS — sapuan menyeluruh (verifikasi & validasi).

Menjawab pertanyaan pemilik:
  1. Apakah karyawan yang di-assign ke 1 entitas BENAR-BENAR tidak bisa melihat
     data entitas lain? (semua endpoint daftar, bukan hanya 3 yang sudah diuji)
  2. Apakah data transaksi (SO, keuangan, dll) selalu jelas entitasnya dan tidak
     tercampur saat karyawan berpindah entitas?
  3. Master data mana yang SHARED dan mana yang terpisah — apakah nyata di API?

Cara kerja:
  FASE 1 — sapu SEMUA endpoint GET tanpa path-param sebagai 4 identitas:
           sales PT-A (ent_ksc) · sales PT-B (ent_kanda) · admin@PT-A · admin@ALL.
           Untuk setiap respons: kumpulkan semua nilai `ent_*` yang muncul
           (entity_id/owner_entity_id/apa pun) + himpunan id baris.
           Verdict: BOCOR (melihat ent_ lain) · SAMA (identik antar-PT) ·
                    TERPISAH (himpunan beda) · KOSONG.
  FASE 2 — IDOR per-dokumen: ambil dokumen milik PT-B dari DB lalu minta
           sebagai sales PT-A → harus 403/404.
  FASE 3 — ringkasan koleksi ber-entity_id di DB + yang KOSONG entity_id-nya
           (dokumen "tak bertuan" = sumber campur-aduk).

Output: /app/.logs/audit_isolation_report.md (+ ringkasan ke stdout)
"""
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001/api"
ENT_A, ENT_B = "ent_ksc", "ent_kanda"
ENT_RE = re.compile(r"^ent_[A-Za-z0-9_]+$")

ACCOUNTS = {
    "admin": ("admin@kainnusantara.id", "demo12345"),
    "sales_A": ("sales@kainnusantara.id", "demo12345"),      # home ent_ksc
    "sales_B": ("sales3@kainnusantara.id", "demo12345"),     # home ent_kanda
    "manager": ("manager@kainnusantara.id", "demo12345"),
    "wh_A": ("warehouse@kainnusantara.id", "demo12345"),
}

SKIP_PAT = re.compile(r"(export|pdf|download|/ws/|preview|barcode|label)", re.I)

# Endpoint yang MEMANG lintas-entitas by design (tidak dinilai bocor)
CROSS_BY_DESIGN = {
    "/api/", "/api/entities", "/api/auth/me", "/api/auth/context",
    "/api/consolidation/summary", "/api/consolidation/eliminations",
    "/api/interco/accounts", "/api/interco/transactions", "/api/interco/summary",
    "/api/interco/settlements", "/api/users", "/api/permissions",
    "/api/config/registry", "/api/config/effective", "/api/config/health",
    "/api/config/history", "/api/config/values",
}

DETAIL_MAP = [
    ("/api/sales-orders/{id}", "sales_orders"),
    ("/api/purchase-orders/{id}", "purchase_orders"),
    ("/api/purchase-requisitions/{id}", "purchase_requisitions"),
    ("/api/rfqs/{id}", "rfqs"),
    ("/api/vendor-bills/{id}", "vendor_bills"),
    ("/api/ar-receipts/{id}", "ar_receipts"),
    ("/api/tax-invoices/{id}", "tax_invoices"),
    ("/api/input-tax-invoices/{id}", "input_tax_invoices"),
    ("/api/sales-returns/{id}", "sales_returns"),
    ("/api/special-orders/{id}", "special_orders"),
    ("/api/price-approvals/{id}", "price_approvals"),
    ("/api/contra-bons/{id}", "contra_bons"),
    ("/api/finance-cases/{id}", "finance_cases"),
    ("/api/fixed-assets/{id}", "fin_fixed_assets"),
    ("/api/makloons/{id}", "makloons"),
    ("/api/makloon-orders/{id}", "makloon_orders"),
    ("/api/suppliers/{id}", "suppliers"),
    ("/api/supplier-contracts/{id}", "supplier_contracts"),
    ("/api/supplier-items/{id}", "supplier_items"),
    ("/api/cash-advances/{id}", "cash_advances"),
    ("/api/lots/{id}", "inventory_lots"),
    ("/api/landed-costs/{id}", "landed_costs"),
    ("/api/transfers/{id}", "warehouse_transfers"),
    ("/api/amendments/{id}", "doc_amendments"),
]


def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code != 200:
        return None
    return r.json()["token"]


def hdr(token, entity=None):
    h = {"Authorization": f"Bearer {token}"}
    if entity:
        h["X-Entity-Id"] = entity
    return h


def walk_entities(obj, found, ids, depth=0):
    """Kumpulkan semua nilai ent_* + id baris tingkat atas."""
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and ENT_RE.match(v):
                found.add(v)
            else:
                walk_entities(v, found, ids, depth + 1)
    elif isinstance(obj, list):
        for it in obj[:200]:
            if isinstance(it, dict):
                rid = it.get("id") or it.get("code") or it.get("number")
                if isinstance(rid, str):
                    ids.add(rid)
            walk_entities(it, found, ids, depth + 1)
    elif isinstance(obj, str) and ENT_RE.match(obj):
        found.add(obj)


def rows_of(body):
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in ("items", "rows", "data", "results", "orders", "records", "lines"):
            if isinstance(body.get(k), list):
                return body[k]
    return []


def probe(path, token, entity):
    try:
        r = requests.get(f"http://localhost:8001{path}", headers=hdr(token, entity), timeout=25)
    except Exception as e:  # noqa: BLE001
        return None, f"ERR {e.__class__.__name__}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        return r.json(), ""
    except Exception:  # noqa: BLE001
        return None, "non-json"


def phase1(tokens, gets):
    print(f"\n=== FASE 1 — sapuan {len(gets)} endpoint GET × 4 identitas ===")
    rows = []
    for i, path in enumerate(sorted(gets), 1):
        if SKIP_PAT.search(path):
            continue
        res = {}
        for label, tok, ent in [
            ("salesA", tokens["sales_A"], None),
            ("salesB", tokens["sales_B"], None),
            ("adminA", tokens["admin"], ENT_A),
            ("adminALL", tokens["admin"], "all"),
        ]:
            body, err = probe(path, tok, ent)
            ents, ids = set(), set()
            if body is not None:
                walk_entities(body, ents, ids)
            res[label] = {"err": err, "ents": ents, "ids": ids,
                          "n": len(rows_of(body)) if body is not None else 0}
        rows.append((path, res))
        if i % 40 == 0:
            print(f"  ... {i}/{len(gets)}")
    return rows


def classify(path, res):
    a, b = res["salesA"], res["salesB"]
    tags = []
    if path in CROSS_BY_DESIGN:
        return ["LINTAS-BY-DESIGN"]
    # 1. kebocoran: sales PT-A melihat ent_kanda (atau sebaliknya)
    if ENT_B in a["ents"]:
        tags.append("BOCOR-A-lihat-B")
    if ENT_A in b["ents"]:
        tags.append("BOCOR-B-lihat-A")
    # 2. identik antar PT (kandidat SHARED atau entity-blind)
    if a["ids"] and a["ids"] == b["ids"]:
        tags.append("SAMA-antar-PT")
    elif a["ids"] and b["ids"] and a["ids"] != b["ids"]:
        tags.append("TERPISAH")
    elif a["n"] and not b["n"]:
        tags.append("A-isi/B-kosong")
    elif b["n"] and not a["n"]:
        tags.append("B-isi/A-kosong")
    # 3. baris tanpa penanda entitas sama sekali
    if (a["n"] or b["n"]) and not (a["ents"] or b["ents"]):
        tags.append("TANPA-PENANDA-ENTITAS")
    if a["err"] or b["err"]:
        tags.append(f"err(A={a['err']}|B={b['err']})")
    return tags or ["KOSONG"]


async def phase3(db):
    print("\n=== FASE 3 — sebaran entity_id di database ===")
    out = []
    names = await db.list_collection_names()
    for c in sorted(names):
        coll = db[c]
        total = await coll.count_documents({})
        if not total:
            continue
        for fld in ("entity_id", "owner_entity_id"):
            n_field = await coll.count_documents({fld: {"$exists": True}})
            if not n_field:
                continue
            empty = await coll.count_documents({fld: {"$in": ["", None]}})
            per = {}
            for eid in [ENT_A, ENT_B, "all"]:
                per[eid] = await coll.count_documents({fld: eid})
            other = n_field - sum(per.values()) - empty
            out.append({"coll": c, "field": fld, "total": total, "berfield": n_field,
                        "kosong": empty, **per, "lain": other})
    return out


async def main():
    tokens = {}
    for k, (e, p) in ACCOUNTS.items():
        t = login(e, p)
        if not t:
            print(f"FATAL: login {k} ({e}) gagal")
            return 1
        tokens[k] = t
    print("Login OK:", ", ".join(tokens))

    spec = requests.get("http://localhost:8001/openapi.json", timeout=30).json()
    gets = [p for p, v in spec["paths"].items() if "get" in v and "{" not in p]

    rows = phase1(tokens, gets)

    buckets = defaultdict(list)
    for path, res in rows:
        for tag in classify(path, res):
            buckets[tag].append((path, res))

    print("\n----- RINGKASAN FASE 1 -----")
    for tag in sorted(buckets):
        print(f"  {tag}: {len(buckets[tag])}")

    print("\n>>> KEBOCOROAN (sales 1-entitas melihat entitas lain):")
    leaks = [(p, r) for p, r in rows if any(t.startswith("BOCOR") for t in classify(p, r))]
    for p, r in leaks:
        print(f"  {p}\n      salesA ents={sorted(r['salesA']['ents'])} n={r['salesA']['n']}"
              f" | salesB ents={sorted(r['salesB']['ents'])} n={r['salesB']['n']}")

    print("\n>>> SAMA-antar-PT (perlu diputuskan: SHARED yang benar, atau harus dipisah?):")
    for p, r in buckets["SAMA-antar-PT"]:
        print(f"  {p}  (n={r['salesA']['n']}, penanda={sorted(r['salesA']['ents']) or '-'})")

    print("\n>>> TANPA-PENANDA-ENTITAS (baris tidak membawa entity_id ke UI):")
    for p, r in buckets["TANPA-PENANDA-ENTITAS"]:
        print(f"  {p}  (nA={r['salesA']['n']} nB={r['salesB']['n']})")

    # ── FASE 2 — IDOR per dokumen ────────────────────────────────────────
    print("\n=== FASE 2 — IDOR dokumen PT-B diminta oleh sales PT-A ===")
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]
    idor = []
    for tmpl, coll in DETAIL_MAP:
        doc = await db[coll].find_one({"entity_id": ENT_B}, {"_id": 0, "id": 1})
        if not doc:
            doc = await db[coll].find_one({"owner_entity_id": ENT_B}, {"_id": 0, "id": 1})
        if not doc or not doc.get("id"):
            idor.append((tmpl, coll, "-", "tidak ada dokumen PT-B (tak teruji)"))
            continue
        path = tmpl.replace("{id}", doc["id"])
        r = requests.get(f"http://localhost:8001{path}",
                         headers=hdr(tokens["sales_A"]), timeout=25)
        verdict = "AMAN" if r.status_code in (403, 404) else f"BOCOR ({r.status_code})"
        idor.append((tmpl, coll, doc["id"], f"{r.status_code} → {verdict}"))
    for tmpl, coll, did, v in idor:
        print(f"  {tmpl:42s} {coll:24s} {v}")

    dist = await phase3(db)
    print(f"\n{'koleksi':34s} {'field':17s} {'total':>6s} {'KSC':>6s} {'KANDA':>6s} "
          f"{'all':>5s} {'KOSONG':>7s} {'lain':>5s}")
    for d in dist:
        flag = "  <== KOSONG!" if d["kosong"] else ""
        print(f"{d['coll']:34s} {d['field']:17s} {d['total']:6d} {d[ENT_A]:6d} "
              f"{d[ENT_B]:6d} {d['all']:5d} {d['kosong']:7d} {d['lain']:5d}{flag}")

    # tulis laporan markdown
    Path("/app/.logs").mkdir(exist_ok=True)
    with open("/app/.logs/audit_isolation_report.md", "w") as f:
        f.write("# AUDIT ISOLASI ENTITAS — hasil sapuan otomatis\n\n")
        f.write(f"Endpoint GET disapu: {len(rows)}\n\n## Ringkasan\n\n")
        for tag in sorted(buckets):
            f.write(f"- **{tag}**: {len(buckets[tag])}\n")
        f.write("\n## Kebocoran\n\n")
        for p, r in leaks:
            f.write(f"- `{p}` — salesA={sorted(r['salesA']['ents'])} salesB={sorted(r['salesB']['ents'])}\n")
        f.write("\n## Identik antar-PT (SHARED / entity-blind)\n\n")
        for p, r in buckets["SAMA-antar-PT"]:
            f.write(f"- `{p}` (n={r['salesA']['n']})\n")
        f.write("\n## Tanpa penanda entitas di respons\n\n")
        for p, r in buckets["TANPA-PENANDA-ENTITAS"]:
            f.write(f"- `{p}` (nA={r['salesA']['n']} nB={r['salesB']['n']})\n")
        f.write("\n## IDOR dokumen\n\n| endpoint | koleksi | hasil |\n|---|---|---|\n")
        for tmpl, coll, did, v in idor:
            f.write(f"| `{tmpl}` | {coll} | {v} |\n")
        f.write("\n## Sebaran entity_id di DB\n\n| koleksi | field | total | KSC | KANDA | all | KOSONG | lain |\n|---|---|---|---|---|---|---|---|\n")
        for d in dist:
            f.write(f"| {d['coll']} | {d['field']} | {d['total']} | {d[ENT_A]} | {d[ENT_B]} | "
                    f"{d['all']} | {d['kosong']} | {d['lain']} |\n")
    print("\nLaporan: /app/.logs/audit_isolation_report.md")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
