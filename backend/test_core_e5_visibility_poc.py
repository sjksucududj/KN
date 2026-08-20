"""POC FASE E-5 — VISIBILITAS STOK SESUAI KEPUTUSAN #1 PEMILIK (bukti-merah).

Keputusan #1 pemilik (2026-08-10): *"Sales: detail stok entitas sendiri + angka
global agregat; detail per-entitas hanya sisi admin."*

Satu berkas, self-cleanup, menguji **empat** hal yang menyusun FASE E-5:

  E5.1  `GET /api/inventory/status-board`
        peran non-lintas → `by_entity` HANYA badan usahanya sendiri, ditambah
        `global_total` (agregat grup TANPA rincian entitas/gudang),
        `other_entities_available`, `detail_scope="own_entity"`, dan isyarat
        `has_intercompany_opportunity`. Admin/manajer → rincian penuh
        (`detail_scope="group"`), wewenang TIDAK berkurang.

  E5.2  `GET /api/pegging/rolls` ter-scope `owner_entity_id`.

  E5.3  Mutasi **pindah-kepemilikan antar badan usaha** tetap TERLIHAT dari sisi
        pemiliknya masing-masing (jejak wajib, tidak boleh disembunyikan), tetapi
        badan usaha lawan hanya muncul sebagai **NAMA SINGKAT**
        (`counterparty_entity_name` = "Kanda"), bukan id teknis `ent_kanda` dan
        bukan nama badan hukum "CV Kanda Suka".

  E5.3c `GET /api/history/{product_id}` (Kartu Riwayat Produk) — **kebocoran yang
        ditemukan sesi 2026-08-11**: endpoint ini SAMA SEKALI tidak ter-scope
        entitas, sehingga sales PT Kain Suka Cita mengklik satu produk dan ikut
        membaca mutasi milik CV Kanda Suka lengkap dengan nomor lot & gudangnya
        (terbukti: 9 baris, 2 di antaranya milik badan usaha lain).

Disiplin repo yang dipakai (sama dengan `test_f0c_scoping_leak_poc.py`):
  1. **BUKTI-MERAH** — setiap klaim isolasi didahului pembuktian bahwa data badan
     usaha lain BENAR-BENAR ADA di DB. Tanpa itu "0 kebocoran" bisa hijau palsu
     karena datanya memang kosong.
  2. **Nol residu** — seluruh fixture (saldo, roll, mutasi) + jejak autentikasi
     dihapus di akhir dan diverifikasi. POC ini dijalankan DI DALAM `gate.sh`
     sehingga tidak boleh menggeser stok/dokumen (INV-GATE-01).
  3. Satu berkas, semua kasus.

Jalankan: cd /app/backend && python test_core_e5_visibility_poc.py
"""
import asyncio
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import db  # noqa: E402

BASE = os.environ.get("KN_BASE", "http://localhost:8001/api")
PWD = "demo12345"
ENT_A = "ent_ksc"      # rumah admin / sales / warehouse
ENT_B = "ent_kanda"    # badan usaha lawan
TAG = "POC_E5_VIS"

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
results = {"pass": 0, "fail": 0}

# id fixture deterministik (dipakai juga oleh pembersihan)
FIX_BAL_B = f"bal_{TAG.lower()}_b"
FIX_ROLL_PEG_A = f"roll_{TAG.lower()}_peg_a"
FIX_ROLL_PEG_B = f"roll_{TAG.lower()}_peg_b"
FIX_MOV_OUT = f"mov_{TAG.lower()}_out"   # milik ENT_A: A → B (keluar)
FIX_MOV_IN = f"mov_{TAG.lower()}_in"     # milik ENT_B: A → B (masuk)
FIX_DOC = "KSC/TRF-POCE5"

made = {"balance_b": False, "peg_a": False, "peg_b": False}
ENT_NAMES: dict = {}


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


def get(token, path, params=None, entity=None):
    h = {"Authorization": f"Bearer {token}"}
    if entity:
        h["X-Entity-Id"] = entity
    return requests.get(f"{BASE}{path}", params=params or {}, headers=h, timeout=60)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE — jadikan uji deterministik, jangan bergantung kebetulan seed
# ─────────────────────────────────────────────────────────────────────────────
async def build_fixture():
    """Siapkan: 1 produk dengan SALDO di dua badan usaha · 1 roll pegging di
    masing-masing badan usaha · 1 pasang mutasi pindah-kepemilikan A→B.

    Return `(product_id, warehouse_id)` atau `(None, None)` bila DB kosong.
    """
    global ENT_NAMES
    ENT_NAMES = {
        e["id"]: e for e in await db.business_entities.find(
            {"id": {"$in": [ENT_A, ENT_B]}}, {"_id": 0}).to_list(10)
    }
    if len(ENT_NAMES) < 2:
        return None, None

    bal_a = await db.inventory_balances.find_one(
        {"owner_entity_id": ENT_A, "available_qty": {"$gt": 0}}, {"_id": 0})
    if not bal_a:
        return None, None
    pid, wid = bal_a["product_id"], bal_a["warehouse_id"]

    # (a) SALDO badan usaha lawan untuk produk yang SAMA — inti bukti-merah E5.1:
    #     kalau produk uji tidak punya stok di badan usaha lain, "tidak bocor"
    #     tidak membuktikan apa pun.
    bal_b = await db.inventory_balances.find_one(
        {"owner_entity_id": ENT_B, "product_id": pid}, {"_id": 0})
    if not bal_b or float(bal_b.get("available_qty", 0) or 0) <= 0:
        await db.inventory_balances.delete_one({"id": FIX_BAL_B})
        twin = {k: v for k, v in bal_a.items() if k != "_id"}
        twin.update({"id": FIX_BAL_B, "owner_entity_id": ENT_B, "poc_tag": TAG,
                     "on_hand_qty": 25.0, "available_qty": 25.0, "reserved_qty": 0.0})
        await db.inventory_balances.insert_one(twin)
        made["balance_b"] = True

    # (b) ROLL PEGGING di dua badan usaha (E5.2). Roll dikloning dari roll nyata
    #     supaya seluruh field domain (snapshot produk, satuan, dst) sah.
    base_roll = await db.inventory_rolls.find_one(
        {"owner_entity_id": ENT_A, "status": "available"}, {"_id": 0})
    if base_roll:
        ear = {"type": "customer", "id": f"{TAG}_demand", "note": "fixture POC E-5"}
        for fid, owner, key in ((FIX_ROLL_PEG_A, ENT_A, "peg_a"),
                                (FIX_ROLL_PEG_B, ENT_B, "peg_b")):
            await db.inventory_rolls.delete_one({"id": fid})
            twin = {k: v for k, v in base_roll.items() if k != "_id"}
            twin.update({"id": fid, "roll_no": f"{TAG}-{key}", "owner_entity_id": owner,
                         "status": "available", "reserved_ref": None,
                         "earmarked_for": ear, "poc_tag": TAG})
            await db.inventory_rolls.insert_one(twin)
            made[key] = True

    # (c) PASANGAN MUTASI PINDAH-KEPEMILIKAN A→B (E5.3). Ditulis langsung ke
    #     ledger (append-only) TANPA rebuild_balance supaya saldo tidak bergeser —
    #     yang diuji di sini adalah LABEL & CAKUPAN BACA, bukan mesin transfernya
    #     (mesinnya sudah diuji POC G-6).
    await db.inventory_movements.delete_many({"poc_tag": TAG})
    common = {
        "product_id": pid, "warehouse_id": wid, "unit": "yard", "lot": f"{TAG}-LOT",
        "roll_id": FIX_ROLL_PEG_A, "from_owner_entity_id": ENT_A,
        "to_owner_entity_id": ENT_B, "source_document": FIX_DOC,
        "timestamp": "2026-08-11T00:00:00+00:00", "poc_tag": TAG,
    }
    await db.inventory_movements.insert_many([
        {**common, "id": FIX_MOV_OUT, "owner_entity_id": ENT_A,
         "movement_type": "ownership_transfer_out", "quantity": -4.0},
        {**common, "id": FIX_MOV_IN, "owner_entity_id": ENT_B,
         "movement_type": "ownership_transfer_in", "quantity": 4.0},
    ])
    return pid, wid


async def drop_fixture():
    """Hapus seluruh fixture & laporkan sisa (harus 0)."""
    await db.inventory_movements.delete_many({"poc_tag": TAG})
    await db.inventory_rolls.delete_many({"poc_tag": TAG})
    if made["balance_b"]:
        await db.inventory_balances.delete_many({"poc_tag": TAG})
    left = (await db.inventory_movements.count_documents({"poc_tag": TAG})
            + await db.inventory_rolls.count_documents({"poc_tag": TAG})
            + await db.inventory_balances.count_documents({"poc_tag": TAG}))
    return left


# ─────────────────────────────────────────────────────────────────────────────
# 1. E5.1 — PAPAN STOK: detail sendiri + agregat grup, tanpa rincian PT lain
# ─────────────────────────────────────────────────────────────────────────────
async def case_status_board(tok, pid):
    print("\n── 1. E5.1 · GET /inventory/status-board — detail sendiri + agregat grup ──")

    def row_of(payload):
        for r in payload if isinstance(payload, list) else []:
            if r.get("product_id") == pid:
                return r
        return None

    # BUKTI-MERAH: produk uji WAJIB punya saldo tersedia di kedua badan usaha.
    avail = {}
    for b in await db.inventory_balances.find({"product_id": pid}, {"_id": 0}).to_list(5000):
        eid = b.get("owner_entity_id") or ENT_A
        avail[eid] = avail.get(eid, 0.0) + float(b.get("available_qty", 0) or 0)
    if not check("BUKTI-MERAH: produk uji punya stok tersedia di 2 badan usaha",
                 avail.get(ENT_A, 0) > 0 and avail.get(ENT_B, 0) > 0,
                 f"product={pid} {avail}"):
        return
    own, other = round(avail[ENT_A], 2), round(avail[ENT_B], 2)

    # ── sales (peran non-lintas, rumah ENT_A)
    r = get(tok["sales"], "/inventory/status-board", {"product_id": pid}, entity=ENT_A)
    check("sales → HTTP 200", r.status_code == 200, f"status={r.status_code}")
    row = row_of(r.json()) if r.status_code == 200 else None
    if not check("baris produk uji ada di papan stok sales", bool(row)):
        return

    ents_seen = {e.get("entity_id") for e in row.get("by_entity", [])}
    check("E5.1 · `by_entity` HANYA badan usaha sendiri (tidak ada rincian PT lain)",
          ents_seen == {ENT_A}, f"terlihat={sorted(ents_seen)}")
    check("E5.1 · `detail_scope` = own_entity", row.get("detail_scope") == "own_entity",
          f"detail_scope={row.get('detail_scope')}")
    check("E5.1 · total baris = stok SENDIRI (bukan stok grup)",
          abs(float(row.get("total_available", 0)) - own) < 0.01,
          f"api={row.get('total_available')} db_sendiri={own}")
    gt = row.get("global_total") or {}
    check("E5.1 · `global_total` hadir sebagai AGREGAT grup",
          abs(float(gt.get("available", -1)) - round(own + other, 2)) < 0.01,
          f"global_total.available={gt.get('available')} db_grup={round(own + other, 2)}")
    check("E5.1 · `global_total` TIDAK memuat rincian entitas/gudang",
          not any(k in gt for k in ("by_entity", "by_warehouse", "entities")),
          f"kunci={sorted(gt.keys())}")
    check("E5.1 · `other_entities_available` = stok badan usaha lain (angka saja)",
          abs(float(row.get("other_entities_available", -1)) - other) < 0.01,
          f"api={row.get('other_entities_available')} db={other}")
    check("E5.1 · isyarat `has_intercompany_opportunity` menyala",
          row.get("has_intercompany_opportunity") is True)

    # Sapuan MENTAH: nama/gudang badan usaha lawan tidak boleh muncul sama sekali
    raw = json.dumps(row, ensure_ascii=False)
    ent_b = ENT_NAMES.get(ENT_B, {})
    wh_b = set()
    for b in await db.inventory_balances.find({"product_id": pid, "owner_entity_id": ENT_B},
                                             {"_id": 0, "warehouse_id": 1}).to_list(500):
        wh_b.add(b.get("warehouse_id"))
    wh_only_b = wh_b - {b.get("warehouse_id") for b in await db.inventory_balances.find(
        {"product_id": pid, "owner_entity_id": ENT_A}, {"_id": 0, "warehouse_id": 1}).to_list(500)}
    leaked_names = [n for n in (ENT_B, ent_b.get("legal_name"), ent_b.get("short_name"))
                    if n and n in raw]
    check("E5.1 · identitas badan usaha lawan TIDAK muncul di baris papan stok sales",
          not leaked_names, f"bocor={leaked_names}")
    check("E5.1 · gudang yang HANYA dipakai badan usaha lawan tidak muncul",
          not [w for w in wh_only_b if w and w in raw], f"gudang_khusus_lawan={sorted(wh_only_b)}")

    # anti-IDOR: minta badan usaha lain secara eksplisit
    r = get(tok["sales"], "/inventory/status-board",
            {"product_id": pid, "owner_entity_id": ENT_B}, entity=ENT_A)
    check("E5.1 · sales minta owner_entity_id=PT lain → 403 (anti-IDOR)",
          r.status_code == 403, f"status={r.status_code}")

    # ── warehouse: peran non-lintas kedua (bukan hanya sales)
    r = get(tok["warehouse"], "/inventory/status-board", {"product_id": pid}, entity=ENT_A)
    row_w = row_of(r.json()) if r.status_code == 200 else None
    check("E5.1 · gudang (peran non-lintas) juga hanya melihat badan usahanya",
          bool(row_w) and {e.get("entity_id") for e in row_w.get("by_entity", [])} == {ENT_A},
          f"status={r.status_code}")

    # ── admin (lintas-entitas): wewenang TIDAK berkurang
    r = get(tok["admin"], "/inventory/status-board", {"product_id": pid}, entity="all")
    row_ad = row_of(r.json()) if r.status_code == 200 else None
    ents_ad = {e.get("entity_id") for e in (row_ad or {}).get("by_entity", [])}
    check("E5.1 · admin mode gabungan → rincian KEDUA badan usaha (wewenang utuh)",
          ents_ad == {ENT_A, ENT_B}, f"terlihat={sorted(ents_ad)}")
    check("E5.1 · admin `detail_scope` = group",
          (row_ad or {}).get("detail_scope") == "group",
          f"detail_scope={(row_ad or {}).get('detail_scope')}")
    check("E5.1 · admin melihat rincian per gudang (bukti detail penuh masih ada)",
          any(e.get("by_warehouse") for e in (row_ad or {}).get("by_entity", [])))


# ─────────────────────────────────────────────────────────────────────────────
# 2. E5.2 — PEGGING/ROLLS ter-scope owner_entity_id
# ─────────────────────────────────────────────────────────────────────────────
async def case_pegging(tok):
    print("\n── 2. E5.2 · GET /pegging/rolls — ter-scope kepemilikan roll ──")
    if not check("BUKTI-MERAH: fixture roll pegging ada di 2 badan usaha",
                 made["peg_a"] and made["peg_b"]):
        return

    r = get(tok["sales"], "/pegging/rolls", entity=ENT_A)
    rows = r.json() if r.status_code == 200 else []
    owners = {x.get("owner_entity_id") for x in rows}
    ids = {x.get("id") for x in rows}
    check("sales → HTTP 200", r.status_code == 200, f"status={r.status_code}")
    check("E5.2 · sales hanya melihat roll pegging badan usahanya",
          owners <= {ENT_A}, f"owner={sorted(o for o in owners if o)}")
    check("E5.2 · roll pegging badan usaha lawan TIDAK ikut terbaca",
          FIX_ROLL_PEG_B not in ids)
    check("BUKTI-MERAH: roll pegging badan usaha sendiri MEMANG terbaca "
          "(bukan hijau karena daftar kosong)", FIX_ROLL_PEG_A in ids, f"{len(ids)} roll")

    r = get(tok["admin"], "/pegging/rolls", entity=ENT_B)
    ids_b = {x.get("id") for x in (r.json() if r.status_code == 200 else [])}
    check("E5.2 · admin di konteks badan usaha lawan melihat roll itu (wewenang utuh)",
          FIX_ROLL_PEG_B in ids_b, f"status={r.status_code} n={len(ids_b)}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. E5.3 — MUTASI PINDAH-KEPEMILIKAN: terlihat, lawan hanya nama singkat
# ─────────────────────────────────────────────────────────────────────────────
def _find(rows, mid):
    for x in rows if isinstance(rows, list) else []:
        if x.get("id") == mid:
            return x
    return None


async def case_movements(tok):
    print("\n── 3. E5.3 · mutasi pindah-kepemilikan: jejak tetap ada, lawan = nama singkat ──")
    short_b = (ENT_NAMES.get(ENT_B, {}).get("short_name")
               or ENT_NAMES.get(ENT_B, {}).get("doc_prefix"))
    short_a = (ENT_NAMES.get(ENT_A, {}).get("short_name")
               or ENT_NAMES.get(ENT_A, {}).get("doc_prefix"))
    legal_b = ENT_NAMES.get(ENT_B, {}).get("legal_name")

    # BUKTI-MERAH: pasangan mutasi memang ada di DB, satu milik tiap badan usaha.
    n_out = await db.inventory_movements.count_documents({"id": FIX_MOV_OUT,
                                                         "owner_entity_id": ENT_A})
    n_in = await db.inventory_movements.count_documents({"id": FIX_MOV_IN,
                                                        "owner_entity_id": ENT_B})
    if not check("BUKTI-MERAH: pasangan mutasi A→B ada di DB (1 milik A, 1 milik B)",
                 n_out == 1 and n_in == 1, f"out={n_out} in={n_in}"):
        return

    # ── sisi ENT_A (sales, peran non-lintas)
    r = get(tok["sales"], "/inventory/movements",
            {"movement_type": "ownership_transfer_out"}, entity=ENT_A)
    rows = r.json() if r.status_code == 200 else []
    mv = _find(rows, FIX_MOV_OUT)
    check("E5.3 · JEJAK WAJIB: sales tetap melihat mutasi pindah-kepemilikan sisinya",
          bool(mv), f"status={r.status_code} n={len(rows)}")
    if mv:
        check("E5.3 · nama lawan = NAMA SINGKAT badan usaha lawan",
              mv.get("counterparty_entity_name") == short_b,
              f"api={mv.get('counterparty_entity_name')!r} harap={short_b!r}")
        check("E5.3 · arah terbaca 'keluar' (dari kita ke sana)",
              mv.get("counterparty_direction") == "out",
              f"arah={mv.get('counterparty_direction')}")
        check("E5.3 · kalimat siap tampil 'ke <lawan>'",
              mv.get("counterparty_label") == f"ke {short_b}",
              f"label={mv.get('counterparty_label')!r}")
        check("E5.3 · id TEKNIS badan usaha dicabut untuk peran non-lintas",
              "from_owner_entity_id" not in mv and "to_owner_entity_id" not in mv,
              f"kunci_entitas={[k for k in mv if 'owner_entity' in k]}")
        blob = json.dumps(mv, ensure_ascii=False)
        check("E5.3 · nama badan HUKUM lawan tidak dibocorkan (cukup nama singkat)",
              bool(legal_b) and legal_b not in blob, f"legal={legal_b!r}")
        check("E5.3 · id teknis badan usaha lawan tidak muncul di mana pun pada baris",
              ENT_B not in blob)
    check("E5.3 · sales TIDAK melihat baris kembar milik badan usaha lawan",
          _find(rows, FIX_MOV_IN) is None)

    r = get(tok["sales"], "/inventory/movements",
            {"movement_type": "ownership_transfer_in"}, entity=ENT_A)
    check("E5.3 · penyaring 'masuk' pun tidak memunculkan baris milik PT lain",
          _find(r.json() if r.status_code == 200 else [], FIX_MOV_IN) is None)

    # ── jalur PAGINASI (layar Mutasi memakai ini) juga wajib berlabel
    r = get(tok["sales"], "/inventory/movements",
            {"movement_type": "ownership_transfer_out", "page": 1, "page_size": 50},
            entity=ENT_A)
    body = r.json() if r.status_code == 200 else {}
    mvp = _find(body.get("items", []), FIX_MOV_OUT)
    check("E5.3 · jalur PAGINASI ikut memberi label lawan (layar Mutasi memakai ini)",
          bool(mvp) and mvp.get("counterparty_entity_name") == short_b,
          f"status={r.status_code} label={(mvp or {}).get('counterparty_label')!r}")

    # ── sisi ENT_B: arah harus TERBALIK, bukan tertukar
    r = get(tok["admin"], "/inventory/movements",
            {"movement_type": "ownership_transfer_in"}, entity=ENT_B)
    mv_b = _find(r.json() if r.status_code == 200 else [], FIX_MOV_IN)
    check("E5.3 · sisi badan usaha lawan melihat mutasi yang sama sebagai 'masuk'",
          bool(mv_b) and mv_b.get("counterparty_direction") == "in",
          f"arah={(mv_b or {}).get('counterparty_direction')}")
    check("E5.3 · dari sisi lawan, nama singkat yang tampil adalah badan usaha kita",
          bool(mv_b) and mv_b.get("counterparty_entity_name") == short_a,
          f"api={(mv_b or {}).get('counterparty_entity_name')!r} harap={short_a!r}")
    check("E5.3 · peran LINTAS-ENTITAS tetap mendapat nama badan hukum (wewenang utuh)",
          bool(mv_b) and mv_b.get("from_entity_name") == ENT_NAMES[ENT_A].get("legal_name"),
          f"from_entity_name={(mv_b or {}).get('from_entity_name')!r}")
    check("E5.3 · peran lintas-entitas tetap mendapat id teknis (dipakai layar admin)",
          bool(mv_b) and mv_b.get("from_owner_entity_id") == ENT_A)


# ─────────────────────────────────────────────────────────────────────────────
# 4. E5.3c — KARTU RIWAYAT PRODUK: kebocoran yang ditutup sesi ini
# ─────────────────────────────────────────────────────────────────────────────
async def case_product_history(tok, pid):
    print("\n── 4. E5.3c · GET /history/{product_id} — kebocoran Kartu Riwayat ditutup ──")
    per_ent = {}
    for m in await db.inventory_movements.find({"product_id": pid},
                                               {"_id": 0, "owner_entity_id": 1}).to_list(20000):
        eid = m.get("owner_entity_id") or ENT_A
        per_ent[eid] = per_ent.get(eid, 0) + 1
    if not check("BUKTI-MERAH: produk uji punya mutasi milik 2 badan usaha di DB",
                 per_ent.get(ENT_A, 0) > 0 and per_ent.get(ENT_B, 0) > 0,
                 f"product={pid} {per_ent}"):
        return

    r = get(tok["sales"], f"/history/{pid}", entity=ENT_A)
    rows = r.json() if r.status_code == 200 else []
    owners = {x.get("owner_entity_id") for x in rows}
    check("sales → HTTP 200", r.status_code == 200, f"status={r.status_code}")
    check("E5.3c · Kartu Riwayat sales HANYA memuat mutasi badan usahanya",
          owners <= {ENT_A}, f"owner={sorted(o for o in owners if o)}")
    check("E5.3c · jumlah baris TEPAT sama dengan jumlah mutasi badan usaha itu "
          "(bukan sekadar 'tidak kosong')",
          len(rows) == per_ent[ENT_A], f"api={len(rows)} db={per_ent[ENT_A]}")
    check("E5.3c · baris mutasi milik badan usaha lawan hilang dari Kartu Riwayat",
          _find(rows, FIX_MOV_IN) is None)
    check("BUKTI-MERAH: mutasi pindah-kepemilikan SISI SENDIRI tetap tampil "
          "(jejak tidak ikut terhapus)", _find(rows, FIX_MOV_OUT) is not None)
    mv = _find(rows, FIX_MOV_OUT)
    check("E5.3c · Kartu Riwayat ikut memberi nama singkat lawan",
          bool(mv) and mv.get("counterparty_entity_name") == (
              ENT_NAMES.get(ENT_B, {}).get("short_name")),
          f"label={(mv or {}).get('counterparty_label')!r}")

    r = get(tok["warehouse"], f"/history/{pid}", entity=ENT_A)
    ow = {x.get("owner_entity_id") for x in (r.json() if r.status_code == 200 else [])}
    check("E5.3c · gudang (peran non-lintas kedua) juga tidak lagi melihat PT lain",
          ow <= {ENT_A}, f"owner={sorted(o for o in ow if o)}")

    # wewenang admin TIDAK berkurang
    r = get(tok["admin"], f"/history/{pid}", entity=ENT_B)
    ids_b = {x.get("id") for x in (r.json() if r.status_code == 200 else [])}
    check("E5.3c · admin di konteks badan usaha lawan melihat mutasi badan usaha itu",
          FIX_MOV_IN in ids_b, f"status={r.status_code} n={len(ids_b)}")
    r = get(tok["admin"], f"/history/{pid}", entity="all")
    ids_all = {x.get("id") for x in (r.json() if r.status_code == 200 else [])}
    check("E5.3c · admin mode gabungan melihat KEDUA sisi (rincian grup masih ada)",
          {FIX_MOV_OUT, FIX_MOV_IN} <= ids_all, f"n={len(ids_all)}")


# ─────────────────────────────────────────────────────────────────────────────
async def main():
    print("\n" + "=" * 78)
    print("  POC FASE E-5 — VISIBILITAS STOK (E5.1 papan · E5.2 pegging · E5.3 mutasi"
          " · E5.3c riwayat)")
    print("=" * 78)

    audit_before = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}

    tok = {
        "admin": login("admin@kainnusantara.id"),
        "sales": login("sales@kainnusantara.id"),
        "warehouse": login("warehouse@kainnusantara.id"),
    }
    check("login 3 peran (admin lintas-entitas · sales · gudang)", all(tok.values()))

    pid, wid = await build_fixture()
    if not check("FIXTURE siap (saldo 2 badan usaha · roll pegging · pasangan mutasi)",
                 bool(pid), f"product={pid} warehouse={wid}"):
        await drop_fixture()
        return 1

    try:
        await case_status_board(tok, pid)
        await case_pegging(tok)
        await case_movements(tok)
        await case_product_history(tok, pid)
    finally:
        print("\n── CLEANUP (INV-GATE-01: nol residu) ──")
        left = await drop_fixture()
        check("CLEANUP: seluruh fixture dihapus (saldo · roll · mutasi)", left == 0,
              f"residu={left}")
        await db.sessions.delete_many({"token": {"$in": list(tok.values())}})
        audit_after = {d["id"] async for d in db.audit_logs.find({}, {"_id": 0, "id": 1})}
        new_audit = audit_after - audit_before
        if new_audit:
            await db.audit_logs.delete_many({"id": {"$in": list(new_audit)}})
        rest = await db.audit_logs.count_documents({"id": {"$in": list(new_audit)}})
        check("CLEANUP: nol residu audit_logs & sessions", rest == 0,
              f"dihapus={len(new_audit)} sisa={rest}")

    print("\n" + "=" * 78)
    print(f"  HASIL: \033[92m{results['pass']} PASS\033[0m · \033[91m{results['fail']} FAIL\033[0m")
    print("=" * 78 + "\n")
    return 1 if results["fail"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
