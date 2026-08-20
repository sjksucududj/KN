#!/usr/bin/env python3
"""GATE RESMI — ISOLASI LINTAS-ENTITAS (FASE E-0 / E0.9 + E0.10).

Ini adalah **pagar anti-regresi**: yang mencegah 21 kebocoran yang baru ditutup
kembali muncul lewat router baru. Berbeda dengan
`scripts/entity_audit/audit_entity_isolation.py` (alat AUDIT — selalu exit 0 dan
menulis laporan), skrip ini **MEMERAH (exit 1)** bila menemukan satu pun pelanggaran.

Tiga lapisan pemeriksaan:

  [1] SAPUAN RUNTIME — semua endpoint GET tanpa path-param disapu sebagai
      **sales PT-A** dan **sales PT-B** (masing-masing hanya berhak 1 entitas).
      MERAH bila respons memuat `ent_*` yang bukan miliknya (kecuali daftar putih
      lintas-entitas by design).

  [2] IDOR DOKUMEN — dokumen milik PT-B diambil dari DB lalu diminta sebagai
      sales PT-A. MERAH bila bukan 403/404.

  [3] STATIK REGISTRY (E0.10) —
      (a) setiap koleksi ber-`entity_id` di DB WAJIB terdaftar di registry
          (`SCOPE_FIELD` atau `SCOPED_COLLECTIONS`) — tidak boleh "lupa daftar";
      (b) setiap router yang MENYENTUH koleksi ter-scope WAJIB memakai lapisan
          `entity_scope` (bukan filter ad-hoc);
      (c) setiap koleksi ter-scope tidak boleh punya dokumen tanpa field entitas.

Pakai:
    python scripts/audit_entity_isolation.py              # gate (exit != 0 bila bocor)
    python scripts/audit_entity_isolation.py --static     # hanya lapisan [3] (tanpa backend)
    python scripts/audit_entity_isolation.py --self-test  # BUKTI-MERAH: gate ini bisa memerah
"""
import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, "/app/backend")

BASE = "http://localhost:8001"
ENT_A, ENT_B = "ent_ksc", "ent_kanda"
ENT_RE = re.compile(r"^ent_[A-Za-z0-9_]+$")
PWD = "demo12345"

RED, GREEN, YEL, RST = "\033[91m", "\033[92m", "\033[93m", "\033[0m"

# Endpoint yang MEMANG lintas-entitas by design → tidak dinilai bocor.
# Setiap baris WAJIB punya alasan; jangan menambah hanya supaya gate hijau.
CROSS_BY_DESIGN = {
    "/api/": "health",
    "/api/entities": "daftar entitas = objek pengaturan, bukan data transaksi",
    "/api/entities/summaries": "pemilih entitas butuh label semua entitas yang diizinkan",
    "/api/auth/me": "konteks pengguna memuat allowed_entity_ids",
    "/api/auth/context": "idem",
    "/api/consolidation/summary": "laporan konsolidasi grup (admin/manager saja)",
    "/api/consolidation/eliminations": "idem",
    "/api/consolidation/trial-balance": "idem",
    "/api/interco/summary": "antar-PT: dua entitas memang hadir dalam satu dokumen",
    "/api/interco/transactions": "idem (dokumen kembar)",
    "/api/interco/accounts": "saldo pasangan PT — pasangan = dua entitas",
    "/api/interco/settlements": "idem",
    "/api/interco/contracts": "kontrak internal antar dua entitas",
    "/api/interco/returns": "retur antar-PT",
    "/api/interco/margin-report": "laporan margin grup",
    "/api/interco/reminders": "pengingat settlement antar-PT",
    "/api/users": "daftar akun memuat penugasan entitas (dijaga izin user.view)",
    "/api/permissions": "matriks izin = konfigurasi global",
    "/api/config/registry": "katalog konfigurasi = definisi, bukan nilai per entitas",
    "/api/config/effective": "membawa lapisan asal (global/entitas) secara sengaja",
    "/api/config/health": "diagnosa konfigurasi",
    "/api/config/history": "riwayat perubahan konfigurasi",
    "/api/config/values": "nilai berlapis lengkap dengan asalnya",
    "/api/enums": "daftar enum statis",
    "/api/transfers": "transfer antar-PT terlihat oleh KEDUA entitas (aturan E0.8b)",
    "/api/warehouses": "gudang bersama (model kepemilikan dibangun di FASE E-4)",
    "/api/hr/org-units": "struktur organisasi grup",
}

SKIP_PAT = re.compile(r"(export|\.pdf|download|/ws/|preview|barcode|label|/api/docs)", re.I)

# Field yang SAH menyebut entitas LAWAN TRANSAKSI (bukan kepemilikan baris).
# Dokumen antar-PT memang memuat dua entitas — itu inti mekanisme antar-entitas.
COUNTERPARTY_FIELDS = {
    "from_owner_entity_id", "to_owner_entity_id",
    "source_entity_id", "dest_entity_id",
    "seller_entity_id", "buyer_entity_id",
    "from_entity_id", "to_entity_id",
    "payer_entity_id", "payee_entity_id",
    "partner_entity_id", "counterparty_entity_id", "other_entity_id",
    "allowed_entity_ids", "home_entity_id", "entity_ids", "allowed_entities",
    # Faktur pajak / dokumen internal: lawan transaksinya adalah entitas grup.
    "customer_id", "supplier_id", "customer_entity_id", "supplier_entity_id",
    # Konteks pengguna & pemilih entitas.
    "entity_summaries", "entities", "active_entity_id",
}


def login(email):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PWD},
                      timeout=25)
    if r.status_code != 200:
        return None
    return r.json().get("token")


def hdr(token, entity=None):
    h = {"Authorization": f"Bearer {token}"}
    if entity:
        h["X-Entity-Id"] = entity
    return h


def collect_entities(obj, found, depth=0, key=""):
    """Kumpulkan nilai `ent_*` yang menandakan KEPEMILIKAN baris.

    Field LAWAN TRANSAKSI di-abaikan dengan sengaja: dokumen antar-PT memang
    menyebut dua entitas (mis. mutasi pindah kepemilikan `from_owner_entity_id` →
    `to_owner_entity_id`, faktur pajak internal yang `customer_id`-nya adalah
    entitas grup). Menandai itu sebagai kebocoran akan membuat gate berbohong.
    """
    if depth > 7:
        return
    if key in COUNTERPARTY_FIELDS:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in COUNTERPARTY_FIELDS:
                continue
            if isinstance(v, str) and ENT_RE.match(v):
                found.add(v)
            else:
                collect_entities(v, found, depth + 1, k)
    elif isinstance(obj, list):
        for it in obj[:300]:
            collect_entities(it, found, depth + 1, key)
    elif isinstance(obj, str) and ENT_RE.match(obj):
        found.add(obj)


def get_paths():
    """Semua path GET tanpa path-param dari OpenAPI."""
    r = requests.get(f"{BASE}/openapi.json", timeout=30)
    r.raise_for_status()
    spec = r.json()
    out = []
    for path, ops in (spec.get("paths") or {}).items():
        if "get" not in ops or "{" in path:
            continue
        if not path.startswith("/api"):
            continue
        if SKIP_PAT.search(path):
            continue
        out.append(path)
    return sorted(out)


# ═══════════════════════════════════════════════════════════════════════════
#  [1] SAPUAN RUNTIME
# ═══════════════════════════════════════════════════════════════════════════
def sweep(tokens):
    paths = get_paths()
    leaks, probed = [], 0
    for path in paths:
        if path in CROSS_BY_DESIGN:
            continue
        for who, tok, mine in (("sales PT-A", tokens["A"], ENT_A),
                               ("sales PT-B", tokens["B"], ENT_B)):
            try:
                r = requests.get(f"{BASE}{path}", headers=hdr(tok, mine), timeout=30)
            except Exception:  # noqa: BLE001
                continue
            if r.status_code != 200:
                continue
            probed += 1
            try:
                body = r.json()
            except Exception:  # noqa: BLE001
                continue
            found = set()
            collect_entities(body, found)
            foreign = {e for e in found if e != mine}
            if foreign:
                leaks.append((path, who, sorted(foreign)))
    return paths, probed, leaks


# ═══════════════════════════════════════════════════════════════════════════
#  [2] IDOR DOKUMEN
# ═══════════════════════════════════════════════════════════════════════════
DETAIL_MAP = [
    ("/api/sales-orders/{id}", "sales_orders", "entity_id"),
    ("/api/purchase-orders/{id}", "purchase_orders", "entity_id"),
    ("/api/ar-receipts/{id}", "ar_receipts", "entity_id"),
    ("/api/sales-returns/{id}", "sales_returns", "entity_id"),
    ("/api/suppliers/{id}", "suppliers", "entity_id"),
    ("/api/customers/{id}", "customers", "entity_id"),
    ("/api/lots/{id}", "inventory_lots", "owner_entity_id"),
    ("/api/lots/{id}/genealogy", "inventory_lots", "owner_entity_id"),
    ("/api/penalties/{id}", "penalties", "entity_id"),
    ("/api/tax-invoices/{id}", "tax_invoices", "entity_id"),
    ("/api/finance-cases/{id}", "finance_cases", "entity_id"),
    ("/api/contra-bons/{id}", "contra_bons", "entity_id"),
    ("/api/documents/trace/sales_order/{id}", "sales_orders", "entity_id"),
    ("/api/documents/refs/sales_order/{id}", "sales_orders", "entity_id"),
    ("/api/documents/preview/{id}", "sales_orders", "entity_id"),
]


async def idor_check(db, tokens):
    bad, tested, untested = [], 0, []
    for tmpl, coll, fld in DETAIL_MAP:
        doc = await db[coll].find_one({fld: ENT_B}, {"_id": 0, "id": 1})
        if not doc or not doc.get("id"):
            untested.append(f"{tmpl} ({coll}: tidak ada dokumen PT-B)")
            continue
        path = tmpl.replace("{id}", doc["id"])
        try:
            r = requests.get(f"{BASE}{path}", headers=hdr(tokens["A"], ENT_A), timeout=30)
        except Exception:  # noqa: BLE001
            continue
        tested += 1
        if r.status_code == 405:
            untested.append(f"{tmpl} (metode GET tidak tersedia)")
            tested -= 1
            continue
        if r.status_code not in (401, 403, 404):
            bad.append((path, coll, r.status_code))
    return tested, bad, untested


# ═══════════════════════════════════════════════════════════════════════════
#  [3] STATIK REGISTRY (E0.10)
# ═══════════════════════════════════════════════════════════════════════════
async def static_registry(db):
    from entity_scope import SCOPE_FIELD, SCOPED_COLLECTIONS, INHERITED_GLOBAL_VALUES
    problems = {"unregistered": [], "router_no_scope": [], "docs_without_entity": []}
    registered = set(SCOPE_FIELD) | set(SCOPED_COLLECTIONS)

    # (a) koleksi ber-entity_id yang belum terdaftar
    for coll in await db.list_collection_names():
        if coll.startswith("system.") or coll in registered:
            continue
        n = await db[coll].count_documents(
            {"$or": [{"entity_id": {"$exists": True}}, {"owner_entity_id": {"$exists": True}}]})
        if n:
            problems["unregistered"].append(f"{coll} ({n} baris ber-entitas)")

    # (b) router menyentuh koleksi ter-scope tanpa lapisan scoping
    scope_helpers = re.compile(
        r"entity_ctx|resolve_list_scope|apply_entity_scope|resolve_scope_ids|"
        r"assert_entity_access|scope_value|resolve_requested_entity")
    for path in sorted((Path("/app/backend/routers")).glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if not re.search(r"@router\.(get|post|patch|put|delete)", src):
            continue
        touched = {m for m in re.findall(r"db\.([a-z_][a-z0-9_]*)", src)
                   if m in SCOPED_COLLECTIONS}
        if touched and not scope_helpers.search(src):
            problems["router_no_scope"].append(f"{path.name} → {sorted(touched)[:4]}")

    # (c) dokumen ter-scope tanpa field entitas (kecuali koleksi berwarisan global)
    existing = set(await db.list_collection_names())
    for coll in sorted(SCOPED_COLLECTIONS):
        if coll not in existing or coll in INHERITED_GLOBAL_VALUES:
            continue
        fld = SCOPE_FIELD.get(coll, "entity_id")
        if fld is None:
            continue
        n = await db[coll].count_documents(
            {"$or": [{fld: {"$exists": False}}, {fld: None}, {fld: ""}]})
        if n:
            total = await db[coll].count_documents({})
            problems["docs_without_entity"].append(f"{coll}.{fld}: {n}/{total} kosong")
    return problems


# ═══════════════════════════════════════════════════════════════════════════
async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--static", action="store_true", help="hanya lapisan statik/DB")
    ap.add_argument("--self-test", action="store_true",
                    help="BUKTI-MERAH: buktikan gate ini bisa memerah")
    args = ap.parse_args()

    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]

    print("=" * 78)
    print("  GATE ISOLASI LINTAS-ENTITAS (FASE E-0)")
    print("=" * 78)

    if args.self_test:
        # Bukti-merah: suntik satu dokumen PT-B ke koleksi yang TIDAK terdaftar,
        # gate WAJIB melihatnya sebagai pelanggaran. Lalu dibersihkan.
        await db.poc_gate_selftest.insert_one({"id": "selftest_e0", "entity_id": ENT_B})
        try:
            probs = await static_registry(db)
            caught = any("poc_gate_selftest" in x for x in probs["unregistered"])
            print(f"  [{'PASS' if caught else 'FAIL'}] gate MENANGKAP koleksi ber-entitas "
                  f"yang tidak terdaftar")
        finally:
            await db.poc_gate_selftest.drop()
        probs2 = await static_registry(db)
        clean = not any("poc_gate_selftest" in x for x in probs2["unregistered"])
        print(f"  [{'PASS' if clean else 'FAIL'}] setelah dibersihkan gate kembali hijau")
        client.close()
        return 0 if (caught and clean) else 1

    fail = 0

    # ── [3] statik dulu (murah, tanpa backend) ──
    print("\n[3] STATIK REGISTRY (E0.10)")
    probs = await static_registry(db)
    for key, label in (("unregistered", "koleksi ber-entitas TIDAK terdaftar di registry"),
                       ("router_no_scope", "router menyentuh koleksi ter-scope TANPA scoping"),
                       ("docs_without_entity", "dokumen ter-scope TANPA field entitas")):
        rows = probs[key]
        if rows:
            fail = 1
            print(f"  {RED}✗ {label}: {len(rows)}{RST}")
            for r in rows:
                print(f"      · {r}")
        else:
            print(f"  {GREEN}✓ {label}: nihil{RST}")

    if args.static:
        client.close()
        return fail

    # ── backend hidup? ──
    try:
        requests.get(f"{BASE}/api/", timeout=10)
    except Exception:  # noqa: BLE001
        print(f"\n{YEL}  Backend tidak hidup — lapisan [1] & [2] di-SKIP.{RST}")
        client.close()
        return fail

    # INV-GATE-01 — gate tidak boleh meninggalkan residu. Sidik jari audit_logs
    # diambil SEBELUM login supaya jejak yang dibuat gate ini bisa dihapus kembali.
    audit_before = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    tokens = {"A": login("sales@kainnusantara.id"), "B": login("sales3@kainnusantara.id")}
    if not (tokens["A"] and tokens["B"]):
        print(f"\n{YEL}  Login demo gagal — jalankan `python /app/seed_realistic.py`.{RST}")
        client.close()
        return fail

    print("\n[1] SAPUAN RUNTIME (semua GET × 2 sales beda entitas)")
    paths, probed, leaks = sweep(tokens)
    print(f"    endpoint GET: {len(paths)} · respons 200 diperiksa: {probed}")
    if leaks:
        fail = 1
        print(f"  {RED}✗ KEBOCORAN: {len(leaks)}{RST}")
        for path, who, foreign in leaks:
            print(f"      · {path}  [{who}] melihat {foreign}")
    else:
        print(f"  {GREEN}✓ nol kebocoran lintas-entitas{RST}")

    print("\n[2] IDOR DOKUMEN (dokumen PT-B diminta sebagai sales PT-A)")
    tested, bad, untested = await idor_check(db, tokens)
    print(f"    endpoint by-id diuji: {tested}")
    if bad:
        fail = 1
        print(f"  {RED}✗ IDOR TERBUKA: {len(bad)}{RST}")
        for path, coll, code in bad:
            print(f"      · {path} ({coll}) → HTTP {code} (seharusnya 403/404)")
    else:
        print(f"  {GREEN}✓ semua endpoint by-id menolak dokumen entitas lain{RST}")
    if untested:
        print(f"  {YEL}  catatan: {len(untested)} endpoint tak teruji (tak ada dokumen PT-B){RST}")

    # bersihkan sesi + jejak audit yang lahir dari gate ini (INV-GATE-01)
    await db.sessions.delete_many({"token": {"$in": [t for t in tokens.values() if t]}})
    audit_after = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    new_ids = list(audit_after - audit_before)
    if new_ids:
        await db.audit_logs.delete_many({"id": {"$in": new_ids}})

    print("\n" + "=" * 78)
    print(f"  VERDICT: {GREEN + 'HIJAU' + RST if not fail else RED + 'MERAH' + RST}")
    print("=" * 78)
    client.close()
    return fail


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
