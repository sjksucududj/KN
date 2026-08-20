"""POC F0-C — BUKTI-MERAH kebocoran lintas-entitas pada 5 query yang gagal di gate.

Latar: `scripts/verify_entity_scoping.py` (STATIC CHECK) menemukan 5 pelanggaran
nyata setelah restore repo:

    routers/product_traceability.py  inventory_rolls, purchase_orders
    routers/uom_conversions.py       purchase_orders, purchase_requisitions, wms_tasks

Gate statik hanya membuktikan "helper diimpor". Skrip ini membuktikan **PERILAKU
HTTP nyata**: user PT A tidak lagi bisa membaca data PT B lewat 3 endpoint:

    GET /api/products/{product_id}/purchase-history
    GET /api/purchase-returns/source-rolls
    GET /api/uom-conversions/usage

Disiplin repo yang dipakai:
  1. **BUKTI-MERAH** — setiap pemeriksaan isolasi didahului pembuktian bahwa data
     PT lain BENAR-BENAR ADA di DB. Tanpa itu "0 kebocoran" bisa palsu karena
     datanya memang kosong.
  2. **Nol residu** — semua fixture (uom_trail) dihapus di akhir & diverifikasi.
  3. Satu berkas, semua kasus. Jalankan: cd /app/backend && python test_f0c_scoping_leak_poc.py
"""
import asyncio
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import db  # noqa: E402

BASE = os.environ.get("KN_BASE", "http://localhost:8001/api")
PWD = "demo12345"
ENT_A = "ent_ksc"      # entitas rumah admin/sales/warehouse
ENT_B = "ent_kanda"    # entitas rumah sales3
POC_TAG = "POC_F0C_TRAIL"

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
results = {"pass": 0, "fail": 0}


def check(name, cond, extra=""):
    results["pass" if cond else "fail"] += 1
    print(f"  [{PASS if cond else FAIL}] {name}" + (f"  ({extra})" if extra else ""))
    return bool(cond)


def login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PWD}, timeout=30)
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("session_token")
    assert tok, f"token tidak ada di respons login {email}: {r.text[:200]}"
    return tok


def get(token, path, params=None, entity_header=None):
    h = {"Authorization": f"Bearer {token}"}
    if entity_header:
        h["X-Entity-Id"] = entity_header
    return requests.get(f"{BASE}{path}", params=params or {}, headers=h, timeout=60)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE BERSAMA — roll PT-B yang deterministik
# ─────────────────────────────────────────────────────────────────────────────
# `seed_realistic.py` TIDAK menjamin ada produk yang punya roll di dua entitas
# (pernah terjadi: sesudah re-seed, PT-B hanya punya 1 roll `quarantine` pada
# produk lain). Kalau fixture-nya kebetulan, uji isolasi bisa "HIJAU palsu"
# karena datanya memang tidak ada. Jadi POC ini MEMBUAT sendiri satu roll PT-B
# sebagai kembaran roll PT-A yang `available`, lalu menghapusnya di akhir.
FIXTURE_ROLL_ID = f"roll_{POC_TAG.lower()}"


async def ensure_cross_entity_roll():
    """Pastikan ADA produk dengan roll available di PT-A dan PT-B. Return product_id."""
    base = await db.inventory_rolls.find_one(
        {"owner_entity_id": ENT_A, "status": "available", "length_remaining": {"$gt": 0}},
        {"_id": 0})
    if not base:
        return None
    await db.inventory_rolls.delete_one({"id": FIXTURE_ROLL_ID})
    twin = dict(base)
    twin.pop("_id", None)
    twin.update({"id": FIXTURE_ROLL_ID, "roll_no": f"{POC_TAG}-01",
                 "owner_entity_id": ENT_B, "poc_tag": POC_TAG})
    await db.inventory_rolls.insert_one(twin)
    return base["product_id"]


async def drop_cross_entity_roll():
    await db.inventory_rolls.delete_many({"poc_tag": POC_TAG})
    return await db.inventory_rolls.count_documents({"poc_tag": POC_TAG})


# ─────────────────────────────────────────────────────────────────────────────
# 1. Kartu Asal Produk (inventory_rolls + purchase_orders)
# ─────────────────────────────────────────────────────────────────────────────
async def case_purchase_history(tok, pid):
    print("\n── 1. GET /products/{id}/purchase-history — isolasi roll & PO ──")

    # BUKTI-MERAH: produk ini HARUS punya roll di kedua entitas.
    per_ent = {}
    async for r in db.inventory_rolls.find({"product_id": pid},
                                           {"_id": 0, "owner_entity_id": 1}):
        per_ent[r.get("owner_entity_id")] = per_ent.get(r.get("owner_entity_id"), 0) + 1
    if not check("BUKTI-MERAH: produk uji punya roll di 2 entitas (kalau tidak, uji palsu)",
                 per_ent.get(ENT_A, 0) > 0 and per_ent.get(ENT_B, 0) > 0,
                 f"product={pid} {per_ent}"):
        return
    n_a, n_b = per_ent[ENT_A], per_ent[ENT_B]
    print(f"     fixture: product={pid} · roll {ENT_A}={n_a} · roll {ENT_B}={n_b}")

    def roll_ids(payload):
        out = set()
        for ev in payload.get("events", []):
            for rl in ev.get("rolls", []):
                out.add(rl.get("roll_id"))
        return out

    async def owners_of(ids):
        if not ids:
            return set()
        docs = await db.inventory_rolls.find(
            {"id": {"$in": list(ids)}}, {"_id": 0, "owner_entity_id": 1}).to_list(50000)
        return {d.get("owner_entity_id") for d in docs}

    # sales (rumah = ENT_A), tanpa param → hanya ENT_A
    r = get(tok["sales"], f"/products/{pid}/purchase-history")
    ok = r.status_code == 200
    ids = roll_ids(r.json()) if ok else set()
    check("sales PT-A tanpa param → HTTP 200", ok, f"status={r.status_code}")
    check("sales PT-A TIDAK melihat roll PT-B", await owners_of(ids) <= {ENT_A},
          f"{len(ids)} roll, owner={sorted(await owners_of(ids))}")
    check("jumlah roll PT-A tepat (bukan sekadar tidak kosong)", len(ids) == n_a,
          f"api={len(ids)} db={n_a}")

    # sales3 (rumah = ENT_B) → hanya ENT_B
    r = get(tok["sales3"], f"/products/{pid}/purchase-history")
    ids_b = roll_ids(r.json()) if r.status_code == 200 else set()
    check("sales PT-B hanya melihat roll PT-B", await owners_of(ids_b) <= {ENT_B},
          f"{len(ids_b)} roll, owner={sorted(await owners_of(ids_b))}")
    check("jumlah roll PT-B tepat", len(ids_b) == n_b, f"api={len(ids_b)} db={n_b}")
    check("BUKTI-MERAH: himpunan roll PT-A & PT-B benar-benar berbeda",
          bool(ids) and bool(ids_b) and not (ids & ids_b))

    # sales PT-A minta entitas PT-B secara eksplisit → 403
    r = get(tok["sales"], f"/products/{pid}/purchase-history", {"entity_id": ENT_B})
    check("sales PT-A minta entity_id=PT-B → 403 (anti-IDOR)", r.status_code == 403,
          f"status={r.status_code}")

    # sales PT-A minta 'all' → BUKAN 403, tapi tetap hanya PT-A (role bukan lintas-entitas)
    r = get(tok["sales"], f"/products/{pid}/purchase-history", {"entity_id": "all"})
    ids_all = roll_ids(r.json()) if r.status_code == 200 else set()
    check("sales PT-A minta entity_id=all → tetap hanya PT-A",
          r.status_code == 200 and await owners_of(ids_all) <= {ENT_A},
          f"status={r.status_code} owner={sorted(await owners_of(ids_all))}")

    # admin (role lintas-entitas) dengan header all → boleh melihat keduanya
    r = get(tok["admin"], f"/products/{pid}/purchase-history", {"entity_id": "all"})
    ids_admin = roll_ids(r.json()) if r.status_code == 200 else set()
    check("admin + entity_id=all → melihat KEDUA entitas (wewenang tidak berkurang)",
          await owners_of(ids_admin) == {ENT_A, ENT_B},
          f"{len(ids_admin)} roll, owner={sorted(await owners_of(ids_admin))}")

    # enrichment PO tidak boleh membawa nomor PO PT lain
    r = get(tok["sales"], f"/products/{pid}/purchase-history")
    po_numbers = {ev.get("po_number") for ev in r.json().get("events", []) if ev.get("po_number")}
    leaked = []
    for num in po_numbers:
        po = await db.purchase_orders.find_one({"po_number": num}, {"_id": 0, "entity_id": 1})
        if po and po.get("entity_id") not in (None, "", ENT_A):
            leaked.append((num, po.get("entity_id")))
    check("enrichment purchase_orders tidak membocorkan nomor PO PT lain", not leaked,
          f"leaked={leaked}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Roll yang bisa diretur (jalur retur presisi)
# ─────────────────────────────────────────────────────────────────────────────
async def case_source_rolls(tok, pid):
    print("\n── 2. GET /purchase-returns/source-rolls — isolasi roll retur ──")
    rows = await db.inventory_rolls.find(
        {"product_id": pid, "status": "available", "length_remaining": {"$gt": 0}},
        {"_id": 0, "owner_entity_id": 1}).to_list(50000)
    ents = {r.get("owner_entity_id") for r in rows}
    if not check("BUKTI-MERAH: produk uji punya roll AVAILABLE di 2 entitas",
                 {ENT_A, ENT_B} <= ents, f"product={pid} entitas={sorted(ents)}"):
        return

    async def owners(payload):
        ids = [x.get("roll_id") for x in payload.get("rolls", [])]
        if not ids:
            return set()
        docs = await db.inventory_rolls.find(
            {"id": {"$in": ids}}, {"_id": 0, "owner_entity_id": 1}).to_list(50000)
        return {d.get("owner_entity_id") for d in docs}

    r = get(tok["admin"], "/purchase-returns/source-rolls", {"product_id": pid})
    check("admin (entitas aktif PT-A) → hanya roll PT-A",
          r.status_code == 200 and await owners(r.json()) <= {ENT_A},
          f"status={r.status_code} owner={sorted(await owners(r.json()))}")

    r = get(tok["admin"], "/purchase-returns/source-rolls",
            {"product_id": pid}, entity_header=ENT_B)
    check("admin ganti entitas aktif → PT-B → hanya roll PT-B",
          r.status_code == 200 and await owners(r.json()) == {ENT_B},
          f"status={r.status_code} owner={sorted(await owners(r.json()))}")

    r = get(tok["sales"], "/purchase-returns/source-rolls",
            {"product_id": pid, "entity_id": ENT_B})
    check("sales PT-A minta roll PT-B secara eksplisit → 403", r.status_code == 403,
          f"status={r.status_code}")

    r = get(tok["admin"], "/purchase-returns/source-rolls",
            {"product_id": pid, "entity_id": "all"})
    check("admin + entity_id=all → kedua entitas (oversight tetap jalan)",
          r.status_code == 200 and await owners(r.json()) == {ENT_A, ENT_B},
          f"owner={sorted(await owners(r.json()))}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Jejak konversi satuan (purchase_orders + purchase_requisitions + wms_tasks)
# ─────────────────────────────────────────────────────────────────────────────
async def case_uom_usage(tok):
    print("\n── 3. GET /uom-conversions/usage — isolasi jejak konversi ──")
    trail = {"from_unit": "roll", "to_unit": "meter", "factor": 50, "input_qty": 2,
             "output_qty": 100, "rule_id": POC_TAG, "converted_at": "2026-07-29T00:00:00Z",
             "poc_tag": POC_TAG}
    fixtures = []   # (collection, id, unset_path)

    # Nomor yang BENAR-BENAR dilaporkan endpoint per koleksi. WAJIB sama dengan
    # `routers/uom_conversions.py`: PO & wms_tasks → `po_number`, PR → `number`.
    NUM_FIELD = {"purchase_orders": "po_number",
                 "purchase_requisitions": "number",
                 "wms_tasks": "po_number"}

    async def stamp(coll, ent, unset_path, setter):
        """Tandai satu dokumen DETERMINISTIK yang nomornya dilaporkan endpoint.

        BUG UJI yang ditutup di sini (terukur 2026-07-29 saat `gate.sh --full`):
        dulu `find_one({"entity_id": ent})` mengambil dokumen APA PUN. Untuk PT-B
        yang terpilih adalah `wms_tasks` OUTBOUND — tanpa `po_number` — sehingga
        himpunan nomor PT-B KOSONG dan pemeriksaan "X-Entity-Id=all melihat kedua
        entitas" MEMERAH. POC-nya sendiri (dijalankan terpisah) 27/0, di dalam
        gate 26/1: gejala klasik fixture non-deterministik (flaky), BUKAN
        kebocoran lintas-PT. Kini dokumen dipilih dengan syarat nomornya ADA dan
        tidak kosong, plus `sort` agar hasilnya sama di setiap eksekusi.
        """
        field = NUM_FIELD[coll]
        doc = await db[coll].find_one(
            {"entity_id": ent, field: {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "id": 1}, sort=[("id", 1)])
        if not doc:
            return None
        await db[coll].update_one({"id": doc["id"]}, {"$set": setter})
        fixtures.append((coll, doc["id"], unset_path))
        return doc["id"]

    marks = {}
    for ent in (ENT_A, ENT_B):
        marks[("purchase_orders", ent)] = await stamp(
            "purchase_orders", ent, "items.0.uom_trail",
            {"items.0.uom_trail": trail})
        marks[("purchase_requisitions", ent)] = await stamp(
            "purchase_requisitions", ent, "items.0.uom_trail",
            {"items.0.uom_trail": trail})
        marks[("wms_tasks", ent)] = await stamp(
            "wms_tasks", ent, "uom_trail", {"uom_trail": trail})

    made = {k: v for k, v in marks.items() if v}
    if not check("BUKTI-MERAH: fixture uom_trail terpasang di KEDUA entitas",
                 any(k[1] == ENT_A for k in made) and any(k[1] == ENT_B for k in made),
                 f"{len(made)} dokumen ditandai"):
        return

    async def numbers_of(ent):
        """Nomor dokumen milik entitas `ent` yang ditandai fixture.

        CATATAN uji: `purchase_requisitions` menyimpan `number` (nomor PR) DAN
        `po_number` (PO turunan). Endpoint melaporkan `number`, jadi field yang
        dibaca di sini WAJIB persis `NUM_FIELD` — kalau tidak, uji ini gagal
        karena bug uji, bukan bug aplikasi.
        """
        out = set()
        for (coll, e), did in made.items():
            if e != ent:
                continue
            field = NUM_FIELD[coll]
            d = await db[coll].find_one({"id": did}, {"_id": 0, field: 1}) or {}
            if d.get(field):
                out.add(d[field])
        return out

    nums_a, nums_b = await numbers_of(ENT_A), await numbers_of(ENT_B)
    print(f"     fixture: nomor PT-A={sorted(nums_a)} · PT-B={sorted(nums_b)}")
    # BUKTI-MERAH kedua: tanpa nomor di KEDUA sisi, semua pemeriksaan di bawah
    # jadi hampa ("tidak bocor" karena himpunannya kosong). Wajib memerah.
    if not check("BUKTI-MERAH: fixture punya nomor dokumen yang TERLIHAT di kedua entitas",
                 bool(nums_a) and bool(nums_b),
                 f"PT-A={len(nums_a)} nomor · PT-B={len(nums_b)} nomor"):
        for coll, did, path in fixtures:
            await db[coll].update_one({"id": did}, {"$unset": {path: ""}})
        return

    r = get(tok["warehouse"], "/uom-conversions/usage", {"limit": 100})
    seen = {row.get("number") for row in (r.json().get("usage") or [])} if r.status_code == 200 else set()
    check("warehouse PT-A → HTTP 200", r.status_code == 200, f"status={r.status_code}")
    check("warehouse PT-A TIDAK melihat nomor dokumen PT-B", not (seen & nums_b),
          f"bocor={sorted(seen & nums_b)}")
    check("warehouse PT-A tetap melihat dokumen PT-A sendiri (tidak over-block)",
          bool(seen & nums_a) if nums_a else True, f"terlihat={sorted(seen & nums_a)}")

    r = get(tok["admin"], "/uom-conversions/usage", {"limit": 100}, entity_header=ENT_B)
    seen_b = {row.get("number") for row in (r.json().get("usage") or [])} if r.status_code == 200 else set()
    check("admin entitas aktif PT-B → hanya dokumen PT-B", not (seen_b & nums_a),
          f"bocor={sorted(seen_b & nums_a)}")

    r = get(tok["admin"], "/uom-conversions/usage", {"limit": 100}, entity_header="all")
    seen_all = {row.get("number") for row in (r.json().get("usage") or [])} if r.status_code == 200 else set()
    check("admin X-Entity-Id=all → melihat kedua entitas",
          bool(nums_a & seen_all) and bool(nums_b & seen_all),
          f"A={sorted(nums_a & seen_all)} B={sorted(nums_b & seen_all)}")

    # ── CLEANUP + verifikasi NOL RESIDU ──
    for coll, did, path in fixtures:
        await db[coll].update_one({"id": did}, {"$unset": {path: ""}})
    residue = 0
    for coll, key in (("purchase_orders", "items.uom_trail.poc_tag"),
                      ("purchase_requisitions", "items.uom_trail.poc_tag"),
                      ("wms_tasks", "uom_trail.poc_tag")):
        residue += await db[coll].count_documents({key: POC_TAG})
    check("CLEANUP: nol residu fixture di DB", residue == 0, f"residu={residue}")


async def main():
    print("\n" + "=" * 70)
    print("  POC F0-C — BUKTI-MERAH ISOLASI LINTAS-ENTITAS (5 temuan gate)")
    print("=" * 70)

    # INV-GATE-01 — POC ini dijalankan DI DALAM gate, jadi ia TIDAK BOLEH
    # meninggalkan residu. Login menulis `audit_logs` + `sessions`; keduanya
    # dibersihkan di akhir (sidik jari diambil sebelum login pertama).
    audit_before = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}

    tok = {
        "admin": login("admin@kainnusantara.id"),
        "sales": login("sales@kainnusantara.id"),
        "sales3": login("sales3@kainnusantara.id"),
        "warehouse": login("warehouse@kainnusantara.id"),
    }
    check("login 4 peran (admin PT-A · sales PT-A · sales PT-B · warehouse PT-A)",
          all(tok.values()))

    pid = await ensure_cross_entity_roll()
    if not check("FIXTURE: roll kembaran PT-B dibuat (uji jadi deterministik)", bool(pid),
                 f"product={pid}"):
        return 1
    await case_purchase_history(tok, pid)
    await case_source_rolls(tok, pid)
    await case_uom_usage(tok)

    # ── CLEANUP jejak fixture + autentikasi (INV-GATE-01: nol residu) ──
    left_roll = await drop_cross_entity_roll()
    check("CLEANUP: roll fixture PT-B dihapus (nol residu)", left_roll == 0, f"residu={left_roll}")
    await db.sessions.delete_many({"token": {"$in": list(tok.values())}})
    audit_after = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
    new_audit = audit_after - audit_before
    if new_audit:
        await db.audit_logs.delete_many({"id": {"$in": list(new_audit)}})
    left = await db.audit_logs.count_documents({"id": {"$in": list(new_audit)}})
    check("INV-GATE-01: nol residu audit_logs & sessions dari POC ini", left == 0,
          f"dihapus={len(new_audit)} sisa={left}")

    print("\n" + "=" * 70)
    print(f"  HASIL: \033[92m{results['pass']} PASS\033[0m · \033[91m{results['fail']} FAIL\033[0m")
    print("=" * 70 + "\n")
    return 1 if results["fail"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
