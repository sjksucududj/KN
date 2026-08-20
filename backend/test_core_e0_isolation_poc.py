"""POC FASE E-0 — BUKTI-MERAH 21 kebocoran lintas-entitas (L1–L21).

Rujukan: `plan.md` §1.2 (tabel A & A-lanjutan) · `AUDIT_ISOLASI_ENTITAS.md` ·
`AUDIT_ANTAR_ENTITAS.md`.

Disiplin repo yang dipakai:
  1. **BUKTI-MERAH** — setiap pemeriksaan isolasi didahului pembuktian bahwa data
     entitas lain BENAR-BENAR ADA di DB. Tanpa itu "0 kebocoran" bisa palsu.
  2. **Nol residu** (INV-GATE-01) — semua fixture & sesi POC dihapus di akhir dan
     dibuktikan bersih.
  3. Satu berkas, semua kasus. Jalankan:
        cd /app/backend && python test_core_e0_isolation_poc.py

Identitas uji (semua password `demo12345`):
  admin@      admin    home ent_ksc   lintas-entitas
  manager@    manager  home ent_ksc   lintas-entitas
  sales@      sales    home ent_ksc   1 entitas
  sales3@     sales    home ent_kanda 1 entitas  ← saksi utama isolasi
  warehouse@  warehouse home ent_ksc  1 entitas
"""
import asyncio
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import db  # noqa: E402

BASE = os.environ.get("KN_BASE", "http://localhost:8001").rstrip("/")
if BASE.endswith("/api"):          # `path` argumen SUDAH memuat prefix /api
    BASE = BASE[:-4]
PWD = "demo12345"
ENT_A = "ent_ksc"       # PT Kain Suka Cita (PKP)
ENT_B = "ent_kanda"     # CV Kanda Suka (non-PKP)

PASS, FAIL, SKIP = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m", "\033[93mSKIP\033[0m"
results = {"pass": 0, "fail": 0, "skip": 0}
failed_names = []


def check(name, cond, extra=""):
    results["pass" if cond else "fail"] += 1
    if not cond:
        failed_names.append(name)
    print(f"  [{PASS if cond else FAIL}] {name}" + (f"  ({extra})" if extra else ""))
    return bool(cond)


def skip(name, why=""):
    results["skip"] += 1
    print(f"  [{SKIP}] {name}" + (f"  ({why})" if why else ""))


def section(title):
    print(f"\n\033[96m── {title}\033[0m")


def login(email):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PWD}, timeout=30)
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("session_token")
    assert tok, f"token tidak ada di respons login {email}: {r.text[:200]}"
    return tok


def _h(token, entity=None):
    h = {"Authorization": f"Bearer {token}"}
    if entity:
        h["X-Entity-Id"] = entity
    return h


def get(token, path, params=None, entity=None):
    return requests.get(f"{BASE}{path}", params=params or {}, headers=_h(token, entity), timeout=60)


def post(token, path, body=None, entity=None, params=None):
    return requests.post(f"{BASE}{path}", json=body or {}, params=params or {},
                         headers=_h(token, entity), timeout=60)


def rows_of(resp):
    """Normalisasi respons: array telanjang / {items:[]} / {data:[]}."""
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "data", "rows", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def foreign(rows, mine, field="entity_id"):
    """Baris yang ber-entitas BUKAN milik saya (dan bukan global/None)."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        ent = r.get(field) or r.get("owner_entity_id")
        if ent and ent not in (mine, "all") and ent != mine:
            out.append(r.get("id") or r.get("number") or str(r)[:40])
    return out


# ═══════════════════════════════════════════════════════════════════════════
#  L1–L6 — daftar modul pinggir yang bocor ke sales entitas lain
# ═══════════════════════════════════════════════════════════════════════════
async def case_side_modules(tok):
    section("L1–L6 · modul pinggir (notifikasi · rencana bayar · selisih · denda · target · insentif)")
    specs = [
        ("L1", "/api/notifications", "notifications"),
        ("L2", "/api/payment-plans", "payment_plans"),
        ("L3", "/api/payment-variances", "payment_variance_decisions"),
        ("L4", "/api/penalties", "penalties"),
        ("L5", "/api/sales-targets", "sales_targets"),
        ("L6", "/api/sales-incentives", "sales_incentives"),
    ]
    for code, path, coll in specs:
        n_a = await db[coll].count_documents({"entity_id": ENT_A})
        if not check(f"{code} BUKTI-MERAH: ada {coll} milik {ENT_A} di DB", n_a > 0, f"{n_a} baris"):
            continue
        r = get(tok["sales3"], path, entity=ENT_B)
        if r.status_code == 403:
            check(f"{code} {path} — sales {ENT_B} ditolak (403 juga sah)", True)
            continue
        if r.status_code != 200:
            check(f"{code} {path} — respons terbaca", False, f"HTTP {r.status_code}")
            continue
        leak = foreign(rows_of(r), ENT_B)
        check(f"{code} {path} — sales {ENT_B} TIDAK melihat data {ENT_A}",
              not leak, f"bocor={leak[:4]}")


# ═══════════════════════════════════════════════════════════════════════════
#  L7 — jejak audit
# ═══════════════════════════════════════════════════════════════════════════
async def case_audit(tok):
    section("L7 · jejak audit (hanya admin, hanya entitas aktif)")
    n = await db.audit_logs.count_documents({})
    check("L7 BUKTI-MERAH: audit_logs terisi", n > 0, f"{n} baris")
    for who in ("sales", "sales3", "warehouse"):
        r = get(tok[who], "/api/audit-logs", entity=ENT_B if who == "sales3" else ENT_A)
        check(f"L7 /api/audit-logs — {who} ditolak 403", r.status_code == 403,
              f"HTTP {r.status_code}")
    r = get(tok["admin"], "/api/audit-logs", entity=ENT_A)
    check("L7 /api/audit-logs — admin boleh (200)", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        leak = [x.get("id") for x in rows_of(r)
                if isinstance(x, dict) and x.get("scope_entity_id")
                and x["scope_entity_id"] not in (ENT_A, "all")]
        check("L7 admin@KSC hanya melihat jejak entitas aktif", not leak, f"bocor={leak[:4]}")


# ═══════════════════════════════════════════════════════════════════════════
#  L8 — lot detail lintas-entitas (anti-IDOR)
# ═══════════════════════════════════════════════════════════════════════════
async def case_lot_detail(tok):
    section("L8 · detail lot / silsilah / label lintas-entitas")
    lot = await db.inventory_lots.find_one({"owner_entity_id": ENT_B}, {"_id": 0})
    if not check("L8 BUKTI-MERAH: ada lot milik " + ENT_B, bool(lot),
                 (lot or {}).get("id", "-")):
        return
    lid = lot["id"]
    for suffix, label in (("", "detail"), ("/genealogy", "silsilah"), ("/recall", "recall")):
        r = get(tok["sales"], f"/api/lots/{lid}{suffix}", entity=ENT_A)
        check(f"L8 GET /api/lots/{{id}}{suffix} ({label}) — sales KSC ditolak",
              r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = post(tok["sales"], f"/api/lots/{lid}/label", {"copies": 1}, entity=ENT_A)
    check("L8 POST /api/lots/{id}/label — sales KSC ditolak",
          r.status_code in (403, 404), f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════
#  L9 — AR aging harus per entitas
# ═══════════════════════════════════════════════════════════════════════════
def case_ar_aging(tok):
    section("L9 · laporan piutang (AR aging) per entitas")
    ra = get(tok["manager"], "/api/ar/aging", entity=ENT_A)
    rb = get(tok["manager"], "/api/ar/aging", entity=ENT_B)
    if not check("L9 AR aging terbaca untuk kedua entitas",
                 ra.status_code == 200 and rb.status_code == 200,
                 f"{ra.status_code}/{rb.status_code}"):
        return
    a, b = ra.json(), rb.json()
    check("L9 entity_id respons = entitas aktif (bukan 'all')",
          a.get("entity_id") == ENT_A and b.get("entity_id") == ENT_B,
          f"A={a.get('entity_id')} B={b.get('entity_id')}")
    ta = (a.get("totals") or {}).get("total", a.get("total_outstanding"))
    tb = (b.get("totals") or {}).get("total", b.get("total_outstanding"))
    check("L9 total piutang BERBEDA antar entitas (tidak dicampur)", ta != tb,
          f"A={ta} B={tb}")
    check("L9 laporan menyebut nama entitas",
          bool(a.get("entity_name")) and bool(b.get("entity_name")),
          f"A={a.get('entity_name')} B={b.get('entity_name')}")
    cust_b = {c.get("customer_id") for c in (b.get("rows") or b.get("customers") or [])
              if isinstance(c, dict)}
    cust_a = {c.get("customer_id") for c in (a.get("rows") or a.get("customers") or [])
              if isinstance(c, dict)}
    check("L9 daftar pelanggan tidak tumpang-tindih antar entitas",
          not (cust_a & cust_b), f"irisan={list(cust_a & cust_b)[:3]}")


# ═══════════════════════════════════════════════════════════════════════════
#  L10 — settings/effective harus baca X-Entity-Id
# ═══════════════════════════════════════════════════════════════════════════
def case_settings(tok):
    section("L10 · /api/settings/effective wajib menghormati X-Entity-Id")
    by_header = get(tok["admin"], "/api/settings/effective", entity=ENT_B)
    by_param = get(tok["admin"], "/api/settings/effective", params={"entity_id": ENT_B})
    if not check("L10 kedua jalur terbaca",
                 by_header.status_code == 200 and by_param.status_code == 200,
                 f"{by_header.status_code}/{by_param.status_code}"):
        return
    h, p = by_header.json(), by_param.json()

    def tax(d):
        t = d.get("tax") or {}
        return (t.get("is_pkp"), t.get("ppn_percent", t.get("ppn_rate")))
    check("L10 header X-Entity-Id memberi hasil SAMA dengan ?entity_id",
          tax(h) == tax(p), f"header={tax(h)} param={tax(p)}")
    check(f"L10 {ENT_B} non-PKP → is_pkp False", tax(h)[0] is False, f"{tax(h)}")


# ═══════════════════════════════════════════════════════════════════════════
#  L11 / L12 — kebersihan data
# ═══════════════════════════════════════════════════════════════════════════
async def case_data_hygiene():
    section("L11–L12 · kebersihan data (referensi entitas yatim & stempel salah)")
    live = {e["id"] async for e in db.business_entities.find({}, {"_id": 0, "id": 1})}
    check("L11 BUKTI-MERAH: daftar entitas hidup terbaca", bool(live), f"{sorted(live)}")
    orphan_total, orphan_detail = 0, {}
    for coll in ("hr_org_units", "hr_employees", "sales_targets", "sales_incentives",
                 "notifications", "warehouse_transfers", "penalties", "payment_plans"):
        bad = 0
        async for d in db[coll].find({}, {"_id": 0, "entity_id": 1}):
            ent = d.get("entity_id")
            if ent and ent not in live and ent != "all":
                bad += 1
        if bad:
            orphan_detail[coll] = bad
        orphan_total += bad
    check("L11 nol dokumen menunjuk entitas yang sudah tidak ada", orphan_total == 0,
          f"{orphan_detail}")

    mism = []
    users = {u["id"]: u async for u in db.users.find({}, {"_id": 0, "id": 1, "email": 1,
                                                          "home_entity_id": 1})}
    for coll in ("sales_targets", "sales_incentives"):
        async for d in db[coll].find({}, {"_id": 0}):
            owner = users.get(d.get("sales_id"))
            if owner and d.get("entity_id") and owner.get("home_entity_id") \
                    and d["entity_id"] != owner["home_entity_id"]:
                mism.append(f"{coll}:{owner['email']}={d['entity_id']}!={owner['home_entity_id']}")
    check("L12 stempel entitas target/insentif = entitas home pemiliknya", not mism,
          f"{mism[:3]}")


# ═══════════════════════════════════════════════════════════════════════════
#  L13 / L14 — transfers
# ═══════════════════════════════════════════════════════════════════════════
async def case_transfers(tok):
    section("L13–L14 · /api/transfers (list · detail · aksi) + registry")
    n_a = await db.warehouse_transfers.count_documents({"entity_id": ENT_A})
    check("L13 BUKTI-MERAH: ada transfer milik " + ENT_A, n_a > 0, f"{n_a} baris")

    r = get(tok["sales3"], "/api/transfers", entity=ENT_B)
    if r.status_code == 200:
        rows = rows_of(r)
        leak = [t.get("id") for t in rows if isinstance(t, dict)
                and (t.get("entity_id") or t.get("source_entity_id")) not in (ENT_B, None, "all")
                and t.get("dest_entity_id") != ENT_B]
        check("L13 GET /api/transfers — konteks Kanda tidak melihat transfer internal KSC",
              not leak, f"bocor={leak[:4]}")
    else:
        check("L13 GET /api/transfers — Kanda ditolak (403 juga sah)",
              r.status_code == 403, f"HTTP {r.status_code}")

    own = await db.warehouse_transfers.find_one(
        {"entity_id": ENT_A, "transfer_kind": {"$ne": "inter_entity"}}, {"_id": 0})
    if own:
        tid = own["id"]
        # Saksi = admin (lintas-entitas) dengan konteks Kanda: dulu transfer KSC
        # terbuka HTTP 200 karena `/api/transfers*` tidak punya cakupan entitas.
        r = get(tok["admin"], f"/api/transfers/{tid}", entity=ENT_B)
        check("L13 GET /api/transfers/{id} — konteks Kanda tidak membuka transfer KSC",
              r.status_code in (403, 404), f"HTTP {r.status_code}")
        for act in ("approve", "reject"):
            r = post(tok["admin"], f"/api/transfers/{tid}/{act}",
                     {"approved_by": "poc", "rejected_by": "poc", "reason": "poc e0"},
                     entity=ENT_B)
            check(f"L13 POST /api/transfers/{{id}}/{act} — konteks Kanda ditolak",
                  r.status_code in (403, 404), f"HTTP {r.status_code}")
        r = post(tok["admin"], f"/api/transfers/{tid}/status",
                 {"status": "dispatched", "updated_by": "poc"}, entity=ENT_B)
        check("L13 POST /api/transfers/{id}/status — konteks Kanda ditolak",
              r.status_code in (403, 404), f"HTTP {r.status_code}")
        r = requests.delete(f"{BASE}/api/transfers/{tid}",
                            headers=_h(tok["admin"], ENT_B), timeout=30)
        check("L13 DELETE /api/transfers/{id} — konteks Kanda ditolak",
              r.status_code in (403, 404), f"HTTP {r.status_code}")
        # Kontrol positif: entitas pemilik TETAP boleh membuka dokumennya.
        r = get(tok["admin"], f"/api/transfers/{tid}", entity=ENT_A)
        check("L13 kontrol positif: entitas pemilik tetap bisa membuka transfernya",
              r.status_code == 200, f"HTTP {r.status_code}")
    else:
        skip("L13 detail/aksi transfer", "tidak ada transfer internal KSC di DB")

    from entity_scope import SCOPED_COLLECTIONS
    check("L14 warehouse_transfers terdaftar di SCOPED_COLLECTIONS",
          "warehouse_transfers" in SCOPED_COLLECTIONS)
    missing = await db.warehouse_transfers.count_documents(
        {"$or": [{"entity_id": {"$exists": False}}, {"entity_id": None}, {"entity_id": ""}]})
    check("L14 semua warehouse_transfers punya entity_id (backfill)", missing == 0,
          f"kosong={missing}")


# ═══════════════════════════════════════════════════════════════════════════
#  L15 / L16 / L17 — registry & pemindaian statik
# ═══════════════════════════════════════════════════════════════════════════
async def case_registry():
    section("L15–L17 · registry koleksi & drift nama")
    from entity_scope import SCOPE_FIELD, SCOPED_COLLECTIONS
    registered = set(SCOPE_FIELD) | set(SCOPED_COLLECTIONS)
    unregistered = []
    for coll in await db.list_collection_names():
        if coll.startswith("system."):
            continue
        if coll in registered:
            continue
        has = await db[coll].count_documents(
            {"$or": [{"entity_id": {"$exists": True}}, {"owner_entity_id": {"$exists": True}}]})
        if has:
            unregistered.append(f"{coll}({has})")
    check("L15 nol koleksi ber-entity_id yang belum terdaftar di registry",
          not unregistered, f"{unregistered[:8]}")
    check("L16 drift nama diperbaiki: tax_invoices_in terdaftar",
          "tax_invoices_in" in registered)
    check("L16 drift nama diperbaiki: input_tax_invoices tidak lagi terdaftar sendiri",
          "input_tax_invoices" not in SCOPED_COLLECTIONS)

    import pathlib
    import re
    bad = []
    routers_dir = pathlib.Path(__file__).parent / "routers"
    for path in sorted(routers_dir.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if not re.search(r"@router\.(get|post|patch|put|delete)", src):
            continue
        touches = re.findall(r"db\.([a-z_][a-z0-9_]*)", src)
        scoped_touched = {t for t in touches if t in SCOPED_COLLECTIONS}
        if scoped_touched and not re.search(
                r"entity_ctx|resolve_list_scope|apply_entity_scope|resolve_scope_ids", src):
            bad.append(f"{path.name}:{sorted(scoped_touched)[:3]}")
    check("L17 nol router menyentuh koleksi ter-scope tanpa lapisan scoping",
          not bad, f"{bad[:6]}")


# ═══════════════════════════════════════════════════════════════════════════
#  L18 / L19 — cetak & jejak dokumen lintas-entitas
# ═══════════════════════════════════════════════════════════════════════════
async def case_documents(tok):
    section("L18–L19 · cetak & jejak dokumen lintas-entitas")
    so_a = await db.sales_orders.find_one({"entity_id": ENT_A}, {"_id": 0})
    so_b = await db.sales_orders.find_one({"entity_id": ENT_B}, {"_id": 0})

    def _num(so):
        return (so or {}).get("so_number") or (so or {}).get("number") \
            or (so or {}).get("order_number") or (so or {}).get("id")
    if not check("L18 BUKTI-MERAH: ada SO di kedua entitas", bool(so_a and so_b),
                 f"A={_num(so_a)} B={_num(so_b)}"):
        return
    r = get(tok["sales3"], f"/api/documents/preview/{so_a['id']}",
            params={"document_type": "surat_jalan"}, entity=ENT_B)
    check("L18 cetak Surat Jalan SO KSC oleh sales Kanda ditolak",
          r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = post(tok["sales3"], "/api/documents/generate",
             {"document_type": "surat_jalan", "source_id": so_a["id"]}, entity=ENT_B)
    check("L18 generate dokumen SO KSC oleh sales Kanda ditolak",
          r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = get(tok["sales"], f"/api/documents/trace/sales_order/{so_b['id']}", entity=ENT_A)
    check("L19 jejak dokumen SO Kanda oleh sales KSC ditolak",
          r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = get(tok["sales"], f"/api/documents/refs/sales_order/{so_b['id']}", entity=ENT_A)
    check("L19 refs dokumen SO Kanda oleh sales KSC ditolak",
          r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = get(tok["sales"], f"/api/documents/relations/sales_order/{so_b['id']}", entity=ENT_A)
    check("L19 relations dokumen SO Kanda oleh sales KSC ditolak",
          r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = get(tok["sales"], "/api/documents/trace-search", params={"q": ""}, entity=ENT_A)
    if r.status_code == 200:
        leak = foreign(rows_of(r), ENT_A)
        check("L19 pencarian jejak dokumen ter-scope entitas aktif", not leak,
              f"bocor={leak[:4]}")


# ═══════════════════════════════════════════════════════════════════════════
#  L20 — RBAC keuangan antar-PT untuk gudang
# ═══════════════════════════════════════════════════════════════════════════
def case_interco_rbac(tok):
    section("L20 · gudang tidak boleh membaca keuangan antar-PT")
    for path in ("/api/interco/accounts", "/api/interco/settlements",
                 "/api/interco/margin-report", "/api/interco/reminders"):
        r = get(tok["warehouse"], path, entity=ENT_A)
        check(f"L20 {path} — gudang ditolak 403", r.status_code == 403,
              f"HTTP {r.status_code}")
    r = get(tok["warehouse"], "/api/interco/transactions", entity=ENT_A)
    check("L20 gudang TETAP boleh melihat transaksi antar-PT (aliran barang)",
          r.status_code == 200, f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════
#  L21 — pratinjau alokasi mengabaikan entitas (KRITIS)
# ═══════════════════════════════════════════════════════════════════════════
async def case_preview_allocation(tok):
    section("L21 · pratinjau alokasi/lot WAJIB memakai entitas konteks (KRITIS)")
    roll = await db.inventory_rolls.find_one(
        {"owner_entity_id": ENT_A, "status": "available", "length_remaining": {"$gt": 0}},
        {"_id": 0})
    if not check("L21 BUKTI-MERAH: ada roll available milik KSC", bool(roll),
                 (roll or {}).get("roll_number", "-")):
        return
    pid = roll["product_id"]
    body = {"items": [{"product_id": pid, "quantity": 1, "unit": "meter"}]}

    r = post(tok["sales3"], "/api/sales-orders/preview-allocation", body, entity=ENT_B)
    if check("L21 preview-allocation terbaca untuk sales Kanda", r.status_code == 200,
             f"HTTP {r.status_code}"):
        d = r.json()
        check("L21 preview-allocation memakai entitas Kanda (bukan default KSC)",
              d.get("entity_id") in (ENT_B, None) and d.get("entity_id") != ENT_A,
              f"entity_id={d.get('entity_id')}")
        own = 0
        for ln in d.get("lines", d.get("items", [])) or []:
            if isinstance(ln, dict):
                own = max(own, float(ln.get("own_available", 0) or 0))
        ksc_stock = 0.0
        async for b in db.inventory_balances.find(
                {"owner_entity_id": ENT_A, "product_id": pid}, {"_id": 0}):
            ksc_stock += float(b.get("available") or b.get("quantity") or 0)
        kanda_stock = 0.0
        async for b in db.inventory_balances.find(
                {"owner_entity_id": ENT_B, "product_id": pid}, {"_id": 0}):
            kanda_stock += float(b.get("available") or b.get("quantity") or 0)
        check("L21 own_available bukan angka stok KSC",
              not (ksc_stock > 0 and abs(own - ksc_stock) < 0.01 and ksc_stock != kanda_stock),
              f"own={own} ksc={ksc_stock} kanda={kanda_stock}")

    r = post(tok["sales3"], "/api/sales-orders/preview-allocation",
             {**body, "entity_id": ENT_A}, entity=ENT_B)
    check("L21 sales Kanda TIDAK boleh memaksa entity_id=KSC di payload",
          r.status_code == 403, f"HTTP {r.status_code}")
    r = post(tok["sales3"], "/api/sales-orders/preview-lots",
             {**body, "entity_id": ENT_A}, entity=ENT_B)
    check("L21 preview-lots juga menolak entity_id paksaan",
          r.status_code == 403, f"HTTP {r.status_code}")
    r = post(tok["sales3"], "/api/sales-orders/preview-lots", body, entity=ENT_B)
    if r.status_code == 200:
        check("L21 preview-lots memakai entitas Kanda", r.json().get("entity_id") == ENT_B,
              f"entity_id={r.json().get('entity_id')}")
    r = post(tok["sales3"], "/api/sales-orders/preview-roll-reconcile",
             {"items": [{"product_id": pid, "quantity": 1, "unit": "meter"}],
              "all_entities": True}, entity=ENT_B)
    if r.status_code == 200:
        body_json = r.json()
        blob = str(body_json)
        foreign_lot = [c for c in ("KSC/LOT", "KSC/") if c in blob]
        check("L21 preview-roll-reconcile all_entities tidak membocorkan lot/roll PT lain",
              not foreign_lot, f"jejak={foreign_lot}")
    else:
        check("L21 preview-roll-reconcile all_entities ditolak untuk peran non-lintas",
              r.status_code == 403, f"HTTP {r.status_code}")


# ═══════════════════════════════════════════════════════════════════════════
#  Sapuan tambahan: router tanpa scoping (admin/incentive_rates/landed_cost/pegging)
# ═══════════════════════════════════════════════════════════════════════════
async def case_unscoped_routers(tok):
    section("L17-lanjutan · endpoint router yang sebelumnya tanpa scoping")
    n = await db.incentive_rates.count_documents({})
    check("BUKTI-MERAH: incentive_rates terisi", n > 0, f"{n} baris")
    probes = [
        ("/api/incentive-rates", "sales3", ENT_B),
        ("/api/landed-costs", "sales3", ENT_B),
        ("/api/pegging/rolls", "sales3", ENT_B),
        ("/api/cycle-count/sessions", "sales3", ENT_B),
        ("/api/purchase-returns", "sales3", ENT_B),
        ("/api/credit-notes", "sales3", ENT_B),
        ("/api/budgets", "sales3", ENT_B),
        ("/api/approval-rules", "sales3", ENT_B),
        ("/api/return-policies", "sales3", ENT_B),
        ("/api/rfid/tags", "sales3", ENT_B),
    ]
    for path, who, ent in probes:
        r = get(tok[who], path, entity=ent)
        if r.status_code in (403, 404):
            check(f"{path} — {who} ditolak/kosong ({r.status_code})", True)
            continue
        if r.status_code != 200:
            skip(f"{path}", f"HTTP {r.status_code}")
            continue
        leak = foreign(rows_of(r), ent)
        check(f"{path} — tidak membocorkan entitas lain", not leak, f"bocor={leak[:3]}")


# ═══════════════════════════════════════════════════════════════════════════
async def main():
    print("\n" + "=" * 78)
    print("  POC FASE E-0 — ISOLASI LINTAS-ENTITAS (L1–L21)  ·  bukti-merah + nol residu")
    print("=" * 78)

    audit_before = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}

    section("Prasyarat")
    ents = {e["id"] async for e in db.business_entities.find({}, {"_id": 0, "id": 1})}
    if not check("dua entitas demo tersedia", {ENT_A, ENT_B} <= ents, f"{sorted(ents)}"):
        print("\n  Jalankan dulu: python /app/seed_realistic.py\n")
        return 1
    tok = {}
    for key, email in (("admin", "admin@kainnusantara.id"),
                       ("manager", "manager@kainnusantara.id"),
                       ("sales", "sales@kainnusantara.id"),
                       ("sales3", "sales3@kainnusantara.id"),
                       ("warehouse", "warehouse@kainnusantara.id")):
        tok[key] = login(email)
    check("login 5 identitas (admin · manager · sales KSC · sales Kanda · gudang KSC)",
          all(tok.values()))

    await case_side_modules(tok)
    await case_audit(tok)
    await case_lot_detail(tok)
    case_ar_aging(tok)
    case_settings(tok)
    await case_data_hygiene()
    await case_transfers(tok)
    await case_registry()
    await case_documents(tok)
    case_interco_rbac(tok)
    await case_preview_allocation(tok)
    await case_unscoped_routers(tok)

    # ── CLEANUP (INV-GATE-01) ──────────────────────────────────────────────
    section("CLEANUP · nol residu")
    await db.sessions.delete_many({"token": {"$in": list(tok.values())}})
    left_sessions = await db.sessions.count_documents({"token": {"$in": list(tok.values())}})
    check("sesi POC dihapus", left_sessions == 0, f"sisa={left_sessions}")
    audit_after = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    new_audit = audit_after - audit_before
    if new_audit:
        await db.audit_logs.delete_many({"id": {"$in": list(new_audit)}})
    left = await db.audit_logs.count_documents({"id": {"$in": list(new_audit)}})
    check("jejak audit dari POC dihapus", left == 0, f"dihapus={len(new_audit)} sisa={left}")
    await db.generated_documents.delete_many({"created_by": {"$regex": "^$"}})

    print("\n" + "=" * 78)
    print(f"  HASIL: \033[92m{results['pass']} PASS\033[0m · "
          f"\033[91m{results['fail']} FAIL\033[0m · \033[93m{results['skip']} SKIP\033[0m")
    if failed_names:
        print("\n  Yang masih gagal:")
        for n in failed_names:
            print(f"    · {n}")
    print("=" * 78 + "\n")
    return 1 if results["fail"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
