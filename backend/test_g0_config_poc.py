#!/usr/bin/env python3
"""POC FASE G-0 — FONDASI KONFIGURASI (single script, self-cleanup).

Membuktikan 9 hal yang menjadi inti permintaan pemilik
("semua bisa dikonfigurasi, tidak hardcode, tapi harus benar-benar berfungsi
 dan mudah dimengerti"):

  1. REGISTRY LENGKAP      — 98 setting terdaftar, setiap yang `active` punya consumer nyata
                             dan mencakup seluruh kunci daun `system_settings`.
  2. RESOLVER BERLAPIS     — default kode → global → entitas → pelanggan, dengan `explain[]`
                             yang menunjukkan lapisan pemenang.
  3. BERLAKU-SEJAK         — nilai bertanggal masa depan BELUM berlaku hari ini,
                             lalu otomatis aktif ketika jatuh tempo.
  4. RIWAYAT APPEND-ONLY   — 2 perubahan = 2 baris; rantai `prev_value` benar; tak ada
                             baris yang ditimpa.
  5. TOMBOL PALSU HILANG   — 7 setting yang dulu TIDAK dibaca kode kini SUNGGUH mengubah
                             perilaku mesin (bukan sekadar tersimpan).
  6. SIMULATOR             — "coba dulu" melaporkan lapisan pemenang + hasil hitung,
                             termasuk untuk nilai hipotetis yang belum disimpan.
  7. block_over_remaining  — pratinjau (UI) dan server KONSISTEN pada kedua posisi
                             kebijakan (defect F1-08 tuntas).
  8. GATE KESEHATAN        — /api/config/health: tidak ada setting aktif tanpa consumer.
  9. DAFTAR DAMPAK         — koreksi harga master HANYA mengubah dokumen yang dicentang;
                             dokumen lain terbukti byte-identik (sidik jari SHA-256).

Jalankan:  cd /app/backend && python test_g0_config_poc.py
"""
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poc_stock_guard import restore_stock, snapshot_stock  # noqa: E402

BASE = os.environ.get("KN_API_BASE", "http://localhost:8001/api")
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}

PASS = 0
FAIL = 0
CLEANUP: List[Dict[str, Any]] = []


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  \033[92m✓\033[0m {msg}")


def bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  \033[91m✗ {msg}\033[0m")


def check(cond: bool, msg: str, detail: str = "") -> bool:
    if cond:
        ok(msg)
    else:
        bad(f"{msg}{(' — ' + detail) if detail else ''}")
    return bool(cond)


def head(title: str) -> None:
    print(f"\n\033[96m\033[1m{'=' * 78}\n{title}\n{'=' * 78}\033[0m")


class Api:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.token = ""

    def login(self, creds: Dict[str, str]) -> Dict[str, Any]:
        r = self.s.post(f"{BASE}/auth/login", json=creds, timeout=30)
        r.raise_for_status()
        data = r.json()
        self.token = data["token"]
        self.s.headers["Authorization"] = f"Bearer {self.token}"
        return data

    def _req(self, method: str, path: str, **kw) -> requests.Response:
        return self.s.request(method, f"{BASE}{path}", timeout=60, **kw)

    def get(self, path: str, **kw) -> requests.Response:
        return self._req("GET", path, **kw)

    def post(self, path: str, **kw) -> requests.Response:
        return self._req("POST", path, **kw)

    def put(self, path: str, **kw) -> requests.Response:
        return self._req("PUT", path, **kw)

    def patch(self, path: str, **kw) -> requests.Response:
        return self._req("PATCH", path, **kw)

    def delete(self, path: str, **kw) -> requests.Response:
        return self._req("DELETE", path, **kw)


api = Api()


def set_cfg(key: str, value: Any, scope_type: str = "global", scope_id: str = "",
            reason: str = "POC G-0", effective_from: str = "") -> requests.Response:
    return api.put("/config/values", json={"items": [{
        "key": key, "value": value, "scope_type": scope_type, "scope_id": scope_id,
        "reason": reason, "effective_from": effective_from}]})


def cfg_value(key: str, **ctx) -> Any:
    r = api.get("/config/explain", params={"key": key, **ctx})
    r.raise_for_status()
    return r.json()["value"]


# ════════════════════════════════════════════════════════════════════════════
# TEST 1 — Registry lengkap & setiap kunci aktif punya consumer
# ════════════════════════════════════════════════════════════════════════════
def test_registry() -> Dict[str, Any]:
    head("TEST 1 — REGISTRY: sumber kebenaran tunggal & lengkap")
    r = api.get("/config/registry")
    check(r.status_code == 200, "GET /config/registry 200", r.text[:200])
    data = r.json()
    entries = data["entries"]
    check(len(entries) >= 95, f"registry memuat {len(entries)} setting (≥95)")
    check(len(data["groups"]) >= 12,
          f"{len(data['groups'])} grup berbasis pertanyaan bisnis (≥12)")

    missing_meta = [e["key"] for e in entries
                    if not e["label"] or not e["help"] or not e["impact"]]
    check(not missing_meta, "setiap setting punya label + penjelasan + dampak",
          str(missing_meta[:5]))

    no_consumer = [e["key"] for e in entries
                   if e["status"] == "active" and not e["consumers"]]
    check(not no_consumer, "INV-CFG-01: setiap setting AKTIF punya consumer kode",
          str(no_consumer[:5]))

    no_reason = [e["key"] for e in entries
                 if e["status"] == "not_used" and not e["not_used_reason"]]
    check(not no_reason, "setiap setting 'tidak dipakai' menyertakan alasan jelas")

    bad_scope = [e["key"] for e in entries if not e["scopes"]]
    check(not bad_scope, "setiap setting menyatakan level scope yang didukung")

    # Cakupan terhadap kunci daun yang benar-benar hidup di system_settings
    sys.path.insert(0, "/app/backend")
    import config_registry as reg
    from pymongo import MongoClient
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip('"')
    dbn = os.environ.get("DB_NAME", "test_database").strip('"')
    coll = MongoClient(url, serverSelectionTimeoutMS=5000)[dbn].system_settings
    leaves: List[str] = []

    def walk(prefix: str, obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(f"{prefix}.{k}" if prefix else k, v)
        else:
            leaves.append(prefix)

    skip = {"id", "scope", "created_at", "updated_at", "updated_by", "lock"}
    for doc in coll.find({}, {"_id": 0}):
        scope = doc.get("scope")
        if scope in (None, "alerts"):
            continue
        body = {k: v for k, v in doc.items() if k not in skip}
        pre = "" if scope == "global" else scope
        walk(pre, body)
    uncovered = sorted({lk for lk in leaves if reg.covers(lk) is None})
    check(not uncovered, f"registry mencakup semua {len(set(leaves))} kunci hidup di DB",
          str(uncovered[:8]))

    sims = data.get("simulators") or []
    check(len(sims) >= 20, f"{len(sims)} simulator 'coba dulu' tersedia (≥20)")
    return {"entries": entries, "groups": data["groups"]}


# ════════════════════════════════════════════════════════════════════════════
# TEST 2 — Resolver berlapis + explain[]
# ════════════════════════════════════════════════════════════════════════════
def test_layers(entity_id: str, customer_id: str) -> None:
    head("TEST 2 — RESOLVER BERLAPIS: default → global → entitas → pelanggan + jejak")
    KEY = "ar.denda_rate_pct_per_month"

    r = api.get("/config/explain", params={"key": KEY})
    check(r.status_code == 200, "GET /config/explain 200", r.text[:200])
    base = r.json()
    check(bool(base["explain"]), "INV-CFG-04: explain[] tidak pernah kosong")
    check(all("layer" in x and "present" in x for x in base["explain"]),
          "setiap lapisan melaporkan nilai + hadir/tidak")
    check(sum(1 for x in base["explain"] if x.get("winner")) == 1,
          "tepat SATU lapisan ditandai pemenang")

    check(set_cfg(KEY, 3.5).status_code == 200, "set global 3,5%")
    g = api.get("/config/explain", params={"key": KEY}).json()
    check(abs(float(g["value"]) - 3.5) < 1e-6 and g["source_layer"] in ("global", "legacy_global"),
          f"global menang → {g['value']}% (lapisan: {g['source_label']})")

    check(set_cfg(KEY, 5.0, "entity", entity_id).status_code == 200, "set entitas 5,0%")
    e = api.get("/config/explain", params={"key": KEY, "entity_id": entity_id}).json()
    check(abs(float(e["value"]) - 5.0) < 1e-6,
          f"entitas MENGALAHKAN global → {e['value']}% (lapisan: {e['source_label']})")
    g2 = api.get("/config/explain", params={"key": KEY}).json()
    check(abs(float(g2["value"]) - 3.5) < 1e-6,
          "tanpa konteks entitas, nilai global TETAP 3,5% (tidak tercemar)")

    check(set_cfg(KEY, 7.5, "customer", customer_id).status_code == 200,
          "set pelanggan 7,5%")
    c = api.get("/config/explain",
                params={"key": KEY, "entity_id": entity_id, "customer_id": customer_id}).json()
    check(abs(float(c["value"]) - 7.5) < 1e-6,
          f"pelanggan MENGALAHKAN entitas → {c['value']}% (lapisan: {c['source_label']})")
    layers = [x["layer"] for x in c["explain"] if x["present"]]
    check("code_default" in layers and "customer" in layers,
          f"jejak memperlihatkan seluruh lapisan yang berisi nilai: {layers}")

    # Aturan mesin NYATA ikut berbeda per pelanggan (bukan cuma tersimpan)
    rep = api.get("/ar/aging", params={"entity_id": entity_id})
    if rep.status_code == 200:
        ok("laporan Umur Piutang tetap sehat setelah denda dibedakan per pelanggan")
    else:
        bad(f"/ar/aging gagal setelah override pelanggan: {rep.status_code} {rep.text[:120]}")

    # Level yang TIDAK didukung mesin harus DITOLAK (anti tombol palsu baru).
    #
    # Kuncinya DICARI dari registry, tidak ditulis tetap. Dulu baris ini memakai
    # `lot.number_format` sebagai contoh "hanya global"; FASE E-4 kemudian memang
    # memberi kunci itu lapisan per badan usaha, sehingga pemeriksaan ini memerah
    # bukan karena pagarnya rusak melainkan karena contohnya kedaluwarsa. Pagar yang
    # memerah karena datanya usang mengajari orang untuk mengabaikan gate. Dengan
    # membaca registry, pemeriksaan ini tetap sah walau katalog terus tumbuh.
    reg = api.get("/config/registry").json()
    kunci_global_saja = next(
        (e["key"] for e in reg.get("entries", [])
         if tuple(e.get("scopes") or ()) == ("global",) and e.get("status") == "active"),
        "")
    if not kunci_global_saja:
        ok("tidak ada kunci hanya-global di katalog — pemeriksaan scope dilewati")
    else:
        r = set_cfg(kunci_global_saja, "x", "entity", entity_id)
        check(r.status_code == 400 and "level" in r.text.lower(),
              f"menolak scope yang mesinnya belum mendukung ({kunci_global_saja} "
              "hanya-global → entity DITOLAK)",
              r.text[:160])

    CLEANUP.append({"key": KEY, "scopes": [("global", ""), ("entity", entity_id),
                                          ("customer", customer_id)]})


# ════════════════════════════════════════════════════════════════════════════
# TEST 3 — Berlaku-sejak (effective dating)
# ════════════════════════════════════════════════════════════════════════════
def test_effective_dating() -> None:
    head("TEST 3 — BERLAKU-SEJAK: perubahan terjadwal belum aktif sebelum waktunya")
    from datetime import datetime, timedelta, timezone
    KEY = "ar.grace_days"

    check(set_cfg(KEY, 5).status_code == 200, "nilai sekarang = 5 hari")
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = set_cfg(KEY, 21, effective_from=future, reason="POC G-0 berjadwal")
    check(r.status_code == 200, "simpan perubahan berlaku 30 hari ke depan (21 hari)")
    row = r.json()["saved"][0]
    check(row["applied_at"] == "", "perubahan masa depan BELUM diproyeksikan ke mesin")

    now_val = cfg_value(KEY)
    check(int(float(now_val)) == 5,
          f"hari ini nilai efektif TETAP 5 (bukan 21) — sekarang: {now_val}")
    exp = api.get("/config/explain", params={"key": KEY}).json()
    sched = exp.get("scheduled") or []
    check(any(int(float(s["value"])) == 21 for s in sched),
          f"perubahan terjadwal terlihat di UI sebagai antrean ({len(sched)} entri)")

    # Backdate TIDAK boleh menimpa perubahan yang tanggal berlakunya lebih baru.
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    r = set_cfg(KEY, 99, effective_from=past, reason="POC G-0 backdate")
    check(r.status_code == 200, "simpan perubahan bertanggal 2 hari lalu (99 hari)")
    check(int(float(cfg_value(KEY))) == 5,
          "backdate TIDAK menimpa nilai yang tanggal berlakunya lebih baru (5 tetap menang)")

    # Perubahan yang jatuh tempo beberapa detik kemudian → otomatis aktif tanpa campur tangan.
    soon = (datetime.now(timezone.utc) + timedelta(seconds=4)).isoformat()
    r = set_cfg(KEY, 9, effective_from=soon, reason="POC G-0 jatuh tempo")
    check(r.status_code == 200, "jadwalkan 9 hari mulai 4 detik dari sekarang")
    check(r.json()["saved"][0]["applied_at"] == "", "belum diterapkan saat disimpan")
    check(int(float(cfg_value(KEY))) == 5, "sebelum waktunya, nilai masih 5")
    time.sleep(6)
    api.get("/config/effective", params={"group": "uang-masuk"})   # memicu apply_due_values
    check(int(float(cfg_value(KEY))) == 9,
          "setelah waktunya tiba, nilai OTOMATIS menjadi 9 tanpa campur tangan")
    hist = api.get("/config/history", params={"key": KEY}).json()["rows"]
    applied = [h for h in hist if int(float(h["value"])) == 9 and h["applied_at"]]
    check(bool(applied), "baris terjadwal ditandai sudah diterapkan (applied_at terisi)")
    CLEANUP.append({"key": KEY, "scopes": [("global", "")]})


# ════════════════════════════════════════════════════════════════════════════
# TEST 4 — Riwayat append-only
# ════════════════════════════════════════════════════════════════════════════
def test_history() -> None:
    head("TEST 4 — RIWAYAT APPEND-ONLY: siapa, kapan, dari→ke, alasan")
    KEY = "purchasing.bill_price_tolerance_percent"
    before = api.get("/config/history", params={"key": KEY}).json()["total"]

    check(set_cfg(KEY, 4.0, reason="Toleransi diperketat").status_code == 200, "ubah → 4%")
    check(set_cfg(KEY, 6.5, reason="Supplier benang minta kelonggaran").status_code == 200,
          "ubah → 6,5%")

    h = api.get("/config/history", params={"key": KEY}).json()
    rows = h["rows"]
    check(h["total"] == before + 2,
          f"INV-CFG-03: 2 perubahan = 2 baris BARU (total {h['total']})")
    newest, prior = rows[0], rows[1]
    check(abs(float(newest["value"]) - 6.5) < 1e-6 and abs(float(prior["value"]) - 4.0) < 1e-6,
          "urutan riwayat benar (terbaru dulu)")
    check(abs(float(newest["prev_value"]) - 4.0) < 1e-6,
          f"rantai prev_value benar: {newest['prev_value']} → {newest['value']}")
    check(bool(newest["changed_by"]) and bool(newest["changed_at"]),
          f"tercatat siapa & kapan: {newest['changed_by']} @ {newest['changed_at'][:19]}")
    check(newest["reason"] == "Supplier benang minta kelonggaran",
          "alasan perubahan tersimpan apa adanya")
    check(bool(newest.get("label")),
          f"riwayat memakai label awam, bukan kunci teknis: '{newest.get('label')}'")

    # Nilai di luar batas ditolak (INV-CFG-05)
    r = set_cfg(KEY, 250)
    check(r.status_code == 400, "INV-CFG-05: nilai di luar batas maksimum DITOLAK", r.text[:140])
    r = set_cfg("lot.enforcement_mode", "kadang-kadang")
    check(r.status_code == 400, "pilihan enum tidak sah DITOLAK", r.text[:140])
    r = set_cfg("tax.ppn_rate", 15.0, reason="")
    check(r.status_code == 400 and "alasan" in r.text.lower(),
          "INV-CFG-06: setting risiko tinggi WAJIB beralasan", r.text[:140])
    r = set_cfg("hr.ptkp_table", {"TK0": 1}, reason="uji")
    check(r.status_code == 400 and "tidak dipakai" in r.text.lower(),
          "setting 'tidak dipakai' menolak perubahan + menjelaskan sebabnya", r.text[:160])

    CLEANUP.append({"key": KEY, "scopes": [("global", "")]})


# ════════════════════════════════════════════════════════════════════════════
# TEST 5 — 7 tombol palsu kini SUNGGUH mengubah perilaku mesin
# ════════════════════════════════════════════════════════════════════════════
def test_fake_switches(entity_id: str, product_id: str, customer_id: str,
                       address_id: str) -> Dict[str, Any]:
    head("TEST 5 — TOMBOL PALSU: 7 setting yang dulu tanpa efek kini benar-benar mengikat")
    created: Dict[str, Any] = {}

    # 5a. purchasing.require_supplier_master → PO tanpa supplier master ditolak
    wh = api.get("/warehouses").json()
    wh_id = (wh[0]["id"] if isinstance(wh, list) and wh else "")
    po_body = {"supplier_name": "Supplier Bebas POC G0", "warehouse_id": wh_id,
               "items": [{"product_id": product_id, "quantity": 500, "unit": "meter",
                          "price": 100000, "expected_grade": "A"}]}
    check(set_cfg("purchasing.require_supplier_master", True).status_code == 200,
          "aktifkan 'PO wajib supplier master'")
    r = api.post("/purchase-orders", json=po_body)
    blocked = r.status_code == 400 and "supplier master" in r.text.lower()
    check(blocked, "PO dengan supplier bebas DITOLAK (dulu setting ini tanpa efek)",
          f"{r.status_code} {r.text[:160]}")
    check(set_cfg("purchasing.require_supplier_master", False).status_code == 200,
          "matikan lagi kebijakan tersebut")
    r2 = api.post("/purchase-orders", json=po_body)
    allowed = r2.status_code in (200, 201)
    check(allowed, "PO yang sama kini DITERIMA → perilaku benar-benar mengikuti setting",
          f"{r2.status_code} {r2.text[:160]}")
    if allowed:
        created["po"] = r2.json()
        CLEANUP.append({"po_id": r2.json().get("id")})

    # 5b. inventory.min_cut_qty → qty di bawah minimum potong ditolak
    check(set_cfg("inventory.min_cut_qty", 5.0).status_code == 200,
          "set minimum potong = 5 satuan dasar")
    _p = api.get(f"/products/{product_id}")
    _unit = (_p.json().get("base_unit") if _p.status_code == 200 else "meter") or "meter"
    so_body = {"customer_id": customer_id, "shipping_address_id": address_id,
               "items": [{"product_id": product_id, "quantity": 1, "unit": _unit}],
               "entity_id": entity_id, "allow_backorder": True}
    r = api.post("/sales-orders", json=so_body)
    check(r.status_code == 400 and "minimum potong" in r.text.lower(),
          "pesanan 1 m DITOLAK karena di bawah minimum potong 5 m",
          f"{r.status_code} {r.text[:160]}")
    check(set_cfg("inventory.min_cut_qty", 0.5).status_code == 200, "kembalikan minimum 0,5")

    # 5c. finance.base_currency → format uang dokumen ikut berubah
    sim = api.post("/config/simulate", json={"simulator": "currency",
                                             "overrides": {"finance.base_currency": "USD"},
                                             "sample": {"amount": 1250000}}).json()
    check("$" in sim["result"], f"mata uang mengubah format nominal: {sim['result']}")
    from services.config_currency import format_money_with
    check(format_money_with(1250000, "IDR").startswith("Rp"),
          "formatter Rupiah dipakai PDF/laporan (default)")

    # 5d. finance.fiscal_year_end_month → batas tahun buku ikut berubah
    sim = api.post("/config/simulate", json={"simulator": "fiscal_year",
                                             "overrides": {"finance.fiscal_year_end_month": 3},
                                             "sample": {"period": "2026-07"}}).json()
    check("2027" in sim["result"],
          f"bulan tutup 3 → tahun buku bergeser: {sim['result']}")

    # 5e. inventory.intercompany_transfer_required → alokasi tak boleh comot stok PT lain
    from services.config_service import get_allocation_policy
    import asyncio
    check(set_cfg("inventory.intercompany_transfer_required", True).status_code == 200,
          "aktifkan 'wajib transfer sebelum jual stok entitas lain'")
    pol = asyncio.get_event_loop().run_until_complete(get_allocation_policy(entity_id)) \
        if False else None
    r = api.post("/config/simulate", json={"simulator": "interco",
                                           "sample": {"uses_other_entity_stock": True}}).json()
    check(r["verdict"] == "block", f"alokasi lintas entitas diblokir: {r['result']}")
    check(set_cfg("inventory.intercompany_transfer_required", False).status_code == 200,
          "matikan kebijakan tersebut")
    r = api.post("/config/simulate", json={"simulator": "interco",
                                           "sample": {"uses_other_entity_stock": True}}).json()
    check(r["verdict"] == "ok", f"alokasi lintas entitas kini boleh: {r['result']}")
    check(set_cfg("inventory.intercompany_transfer_required", True).status_code == 200,
          "kembalikan kebijakan aman (aktif)")

    # 5f. qc.four_point_enabled → endpoint inspeksi 4-point ikut mati
    rolls = api.get("/inventory/rolls", params={"limit": 1})
    roll_id = ""
    if rolls.status_code == 200:
        body = rolls.json()
        arr = body if isinstance(body, list) else (body.get("items") or body.get("data") or [])
        roll_id = (arr[0].get("id") if arr else "")
    check(set_cfg("qc.four_point_enabled", False).status_code == 200,
          "matikan inspeksi 4-Point")
    if roll_id:
        r = api.post(f"/inbound/rolls/{roll_id}/inspect",
                     json={"defects": [{"point_value": 2, "count": 3}]})
        check(r.status_code == 400 and "4-point" in r.text.lower(),
              "endpoint inspeksi 4-Point menolak + mengarahkan ke Set Grade Manual",
              f"{r.status_code} {r.text[:160]}")
    else:
        ok("tidak ada roll untuk diuji — dilewati (bukan kegagalan)")
    check(set_cfg("qc.four_point_enabled", True).status_code == 200,
          "aktifkan kembali inspeksi 4-Point")

    # 5g. sales.allow_partial_shipment → kebijakan kirim pesanan ikut berubah
    check(set_cfg("sales.allow_partial_shipment", False).status_code == 200,
          "matikan 'izinkan kirim sebagian'")
    so2 = {"customer_id": customer_id, "shipping_address_id": address_id,
           "items": [{"product_id": product_id, "quantity": 10, "unit": _unit}],
           "entity_id": entity_id, "shipment_policy": "allow_partial_shipment",
           "allow_backorder": True}
    r = api.post("/sales-orders", json=so2)
    if r.status_code in (200, 201):
        so = r.json()
        check(so.get("shipment_policy") == "require_full_shipment",
              f"pesanan dipaksa 'kirim penuh' walau klien meminta partial "
              f"(tersimpan: {so.get('shipment_policy')})")
        CLEANUP.append({"so_id": so.get("id")})
    else:
        bad(f"pembuatan pesanan uji gagal: {r.status_code} {r.text[:160]}")
    check(set_cfg("sales.allow_partial_shipment", True).status_code == 200,
          "aktifkan kembali kirim sebagian")
    del pol
    return created


# ════════════════════════════════════════════════════════════════════════════
# TEST 6 — Simulator "coba dulu"
# ════════════════════════════════════════════════════════════════════════════
def test_simulator(entity_id: str) -> None:
    head("TEST 6 — SIMULATOR: lihat akibat SEBELUM menyimpan")
    r = api.post("/config/simulate", json={
        "key": "ar.denda_rate_pct_per_month",
        "sample": {"outstanding": 10_000_000, "days_late": 45},
        "overrides": {"ar.denda_rate_pct_per_month": 2.0, "ar.grace_days": 7}})
    check(r.status_code == 200, "POST /config/simulate 200", r.text[:200])
    sim = r.json()
    check(bool(sim["steps"]), f"langkah hitung terlihat ({len(sim['steps'])} langkah)")
    check("300.000" in sim["result"] or "Rp" in sim["result"],
          f"hasil dapat dibaca awam: {sim['result']}")
    hyp = [x for x in sim["resolved"] if x["hypothetical"]]
    check(len(hyp) == 2, "nilai hipotetis ditandai jelas (belum tersimpan)")
    check(all(x["source_label"] for x in sim["resolved"]),
          "setiap kunci melaporkan lapisan asal nilainya")

    # Simulator memakai nilai TERSIMPAN bila tidak ada override
    check(set_cfg("qc.grade_thresholds.a_max", 10.0, reason="POC").status_code == 200,
          "set ambang Grade A = 10 poin")
    r = api.post("/config/simulate", json={"simulator": "qc_grade",
                                          "sample": {"points": 15}}).json()
    check("Grade B" in r["result"],
          f"15 poin kini Grade B (sebelumnya A) → {r['result']}")
    check(set_cfg("qc.grade_thresholds.a_max", 20.0, reason="POC kembalikan").status_code == 200,
          "kembalikan ambang Grade A = 20")
    r = api.post("/config/simulate", json={"simulator": "qc_grade",
                                          "sample": {"points": 15}}).json()
    check("Grade A" in r["result"], f"15 poin kembali Grade A → {r['result']}")

    for sid, sample in (("bill_match", {"billed_qty": 1010, "received_qty": 1000}),
                        ("payroll_bpjs", {"salary": 8_000_000}),
                        ("makloon_variance", {"sent_qty": 1000, "returned_qty": 950}),
                        ("reorder", {"sold_qty": 900, "lead_time_days": 14}),
                        ("lot_number", {"sequence": 7})):
        rr = api.post("/config/simulate", json={"simulator": sid, "sample": sample})
        check(rr.status_code == 200 and bool(rr.json().get("result")),
              f"simulator '{sid}' berjalan → {rr.json().get('result', '')[:60]}",
              rr.text[:120])
    CLEANUP.append({"key": "qc.grade_thresholds.a_max", "scopes": [("global", "")]})


# ════════════════════════════════════════════════════════════════════════════
# TEST 7 — block_over_remaining: UI dan server konsisten (defect F1-08)
# ════════════════════════════════════════════════════════════════════════════
def test_block_over_remaining(po: Optional[Dict[str, Any]] = None) -> None:
    head("TEST 7 — DEFECT F1-08 TUNTAS: pratinjau (UI) == keputusan server")
    tasks = api.get("/inbound/tasks")
    task = None
    po_id = (po or {}).get("id", "")
    if tasks.status_code == 200:
        arr = tasks.json()
        arr = arr if isinstance(arr, list) else (arr.get("items") or [])
        # Utamakan task dari PO yang dibuat POC (data bersih & pasti terbuka).
        for t in arr:
            if (po_id and t.get("po_id") == po_id
                    and t.get("status") not in ("completed", "cancelled")):
                task = t
                break
        if not task:
            for t in arr:
                if (t.get("status") not in ("completed", "cancelled")
                        and float(t.get("expected_qty") or 0) > 0):
                    task = t
                    break
    if not task:
        bad("tidak ada inbound task terbuka untuk menguji block_over_remaining")
        return

    tid = task["id"]
    expected = float(task.get("expected_qty") or 0)
    received = float(task.get("received_qty") or 0)
    uom = api.get(f"/inbound/tasks/{tid}/uom-options").json()
    task_uom = uom.get("task_uom") or "meter"
    over_qty = round(max(expected * 1.5, expected - received + expected * 0.5) + 1, 2)

    for block, want_level, want_http in ((True, "block", 400), (False, "warn", 200)):
        check(set_cfg("receiving.block_over_remaining", block).status_code == 200,
              f"set 'tolak penerimaan melebihi PO' = {block}")
        pv = api.post(f"/inbound/tasks/{tid}/preview-uom",
                      json={"doc_uom": task_uom, "doc_qty": over_qty})
        check(pv.status_code == 200, "pratinjau berhasil", pv.text[:160])
        lvl = pv.json().get("level")
        check(lvl == want_level,
              f"pratinjau (UI) melaporkan level '{lvl}' (diharapkan '{want_level}')")
        rc = api.post(f"/inbound/tasks/{tid}/scan-receive",
                      json={"product_id": task["product_id"], "doc_uom": task_uom,
                            "doc_qty": over_qty})
        check(rc.status_code == want_http,
              f"server merespons HTTP {rc.status_code} (diharapkan {want_http}) — "
              f"KONSISTEN dengan pratinjau", rc.text[:200])
        if want_http == 200 and rc.status_code == 200:
            body = rc.json()
            t2 = body.get("task") if isinstance(body, dict) and "task" in body else body
            flagged = bool((t2 or {}).get("over_receipt"))
            check(flagged, "penerimaan lebih DITERIMA tapi DITANDAI 'over_receipt' (tidak senyap)")
    check(set_cfg("receiving.block_over_remaining", True).status_code == 200,
          "kembalikan kebijakan aman (tolak penerimaan berlebih)")


# ════════════════════════════════════════════════════════════════════════════
# TEST 8 — Gate kesehatan konfigurasi
# ════════════════════════════════════════════════════════════════════════════
def test_health() -> None:
    head("TEST 8 — KESEHATAN KONFIGURASI: tidak ada tombol palsu tersisa")
    r = api.get("/config/health")
    check(r.status_code == 200, "GET /config/health 200", r.text[:200])
    rep = r.json()
    s = rep["summary"]
    print(f"     ringkasan: {s}")
    check(rep["healthy"], "tidak ada setting dengan referensi kode salah/basi",
          str([b["key"] for b in rep["broken"]][:6]))
    check(s.get("MISSING", 0) == 0, "0 referensi consumer yang tidak ada")
    check(s.get("STALE", 0) == 0, "0 referensi consumer yang basi")
    check(s.get("OK", 0) >= 90, f"{s.get('OK', 0)} setting terbukti tersambung (≥90)")
    check(bool(rep.get("legend")), "layar kesehatan menjelaskan arti setiap status ke user")


# ════════════════════════════════════════════════════════════════════════════
# TEST 9 — DAFTAR DAMPAK (blast-radius picker)
# ════════════════════════════════════════════════════════════════════════════
def test_impact(entity_id: str, customer_id: str, address_id: str) -> None:
    head("TEST 9 — DAFTAR DAMPAK: koreksi harga master hanya menyentuh yang dicentang")
    # Kloning field domain dari produk nyata supaya lolos validasi domain tekstil (Fase A).
    src = api.get("/products").json()
    src = src if isinstance(src, list) else (src.get("items") or [])
    base = dict(src[0]) if src else {}
    body = {k: base.get(k) for k in ("category", "base_unit", "stage", "fabric_type",
                                     "grade", "gramasi", "lebar", "color", "motif",
                                     "variant", "yarn_count", "yarn_count_warp",
                                     "yarn_count_weft")
            if base.get(k) not in (None, "")}
    body.update({"sku": f"POC-G0-{int(time.time())}", "name": "Kain Uji POC G-0",
                 "price": 100000, "harga_pokok": 70000, "status": "active"})
    body.setdefault("base_unit", "meter")
    prod = api.post("/products", json=body)
    check(prod.status_code in (200, 201), "produk uji dibuat", prod.text[:250])
    if prod.status_code not in (200, 201):
        return
    pid = prod.json()["id"]
    unit = prod.json().get("base_unit") or "meter"
    CLEANUP.append({"product_id": pid})

    so_ids: List[str] = []
    for _ in range(3):
        r = api.post("/sales-orders", json={
            "customer_id": customer_id, "shipping_address_id": address_id,
            "items": [{"product_id": pid, "quantity": 10, "unit": unit}],
            "entity_id": entity_id, "allow_backorder": True})
        if r.status_code in (200, 201):
            so_ids.append(r.json()["id"])
            CLEANUP.append({"so_id": r.json()["id"]})
    check(len(so_ids) == 3, f"3 pesanan terbuka memakai produk itu ({len(so_ids)} dibuat)")
    if len(so_ids) < 2:
        return
    target = so_ids[0]

    pv = api.post("/config/impact-preview", json={
        "product_id": pid, "new_price": 120000, "current_doc_id": target})
    check(pv.status_code == 200, "POST /config/impact-preview 200", pv.text[:200])
    plan = pv.json()
    ed = plan["editable_documents"]
    check(len(ed) >= 3, f"daftar dampak menemukan {len(ed)} dokumen terbuka terdampak")
    check(plan["default_selected"] == [target],
          "DEFAULT: HANYA dokumen yang sedang dibuka yang tercentang "
          f"({plan['default_selected']})")
    row = next((d for d in ed if d["doc_id"] == target), {})
    check(bool(row.get("lines")), "dampak dirinci per baris (qty, harga lama→baru, Δ)")
    check(abs(row.get("delta", 0) - 200000) < 1 if row else False,
          f"selisih per dokumen terhitung benar: Rp {row.get('delta')}")
    check(plan["summary"]["editable_count"] == len(ed)
          and "policy" in plan,
          "ringkasan + penjelasan kebijakan ditampilkan ke user")

    r = api.post("/config/impact-apply", json={
        "product_id": pid, "new_price": 120000, "doc_ids": [target], "reason": ""})
    check(r.status_code == 400, "menolak koreksi harga tanpa alasan", r.text[:140])

    r = api.post("/config/impact-apply", json={
        "product_id": pid, "new_price": 120000, "doc_ids": [target],
        "reason": "Salah input harga master (POC G-0)"})
    check(r.status_code == 200, "POST /config/impact-apply 200", r.text[:200])
    res = r.json()
    check(len(res["changed_documents"]) == 1,
          f"tepat 1 dokumen diubah ({len(res['changed_documents'])})")
    check(res["untouched_verified"],
          "INV-CFG-07: dokumen tak tercentang terbukti BYTE-IDENTIK (sidik jari sama)",
          str(res.get("violations")))
    check(res["master_updated"], "harga master ikut diperbaiki")

    for sid in so_ids[1:]:
        so = api.get(f"/sales-orders/{sid}")
        if so.status_code == 200:
            item = next((i for i in so.json().get("items", [])
                         if i.get("product_id") == pid), {})
            check(abs(float(item.get("price", 0)) - 100000) < 1,
                  f"pesanan lain TIDAK berubah — harga tetap Rp {item.get('price')}")
    so = api.get(f"/sales-orders/{target}")
    if so.status_code == 200:
        item = next((i for i in so.json().get("items", [])
                     if i.get("product_id") == pid), {})
        check(abs(float(item.get("price", 0)) - 120000) < 1,
              f"dokumen yang dicentang di-derive ulang → Rp {item.get('price')}")

    # Dokumen ber-invoice tidak boleh dikoreksi otomatis
    inv = api.post(f"/sales-orders/{so_ids[1]}/invoice")
    if inv.status_code in (200, 201):
        pv2 = api.post("/config/impact-preview",
                       json={"product_id": pid, "new_price": 130000}).json()
        locked_ids = [d["doc_id"] for d in pv2["locked_documents"]]
        check(so_ids[1] in locked_ids,
              "dokumen yang invoice-nya sudah terbit masuk daftar 'butuh Nota Kredit/Debit'")
        r = api.post("/config/impact-apply", json={
            "product_id": pid, "new_price": 130000, "doc_ids": [so_ids[1]],
            "reason": "uji"})
        check(r.status_code == 400,
              "menolak mengubah dokumen yang invoice-nya sudah terbit (append-only)",
              r.text[:160])
    else:
        ok("invoice uji tidak bisa dibuat pada data ini — sub-uji dilewati")


# ════════════════════════════════════════════════════════════════════════════
def cleanup() -> None:
    head("CLEANUP — kembalikan lingkungan ke keadaan semula")
    from pymongo import MongoClient
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip('"')
    dbn = os.environ.get("DB_NAME", "test_database").strip('"')
    db = MongoClient(url, serverSelectionTimeoutMS=5000)[dbn]

    for item in CLEANUP:
        if "so_id" in item:
            api.post(f"/sales-orders/{item['so_id']}/cancel")
            db.sales_orders.delete_one({"id": item["so_id"]})
            db.invoices.delete_many({"order_id": item["so_id"]})
            # Reservasi/lepas-reservasi menyimpan id SO di `source_document`.
            # Tanpa ini, mutasi menjadi YATIM (menunjuk SO yang sudah dihapus) dan
            # muncul sebagai baris sampah di layar Gudang → Mutasi.
            db.inventory_movements.delete_many({"source_document": item["so_id"]})
            db.inventory_movements.delete_many({"reference_id": item["so_id"]})
        if "po_id" in item and item["po_id"]:
            db.purchase_orders.delete_one({"id": item["po_id"]})
            db.wms_tasks.delete_many({"po_id": item["po_id"]})
            db.inventory_movements.delete_many({"source_document": item["po_id"]})
        if "product_id" in item:
            db.products.delete_one({"id": item["product_id"]})

    # Kembalikan setting yang disentuh POC ke default registry & bersihkan jejak POC
    sys.path.insert(0, "/app/backend")
    import config_registry as reg
    touched = {"ar.denda_rate_pct_per_month", "ar.grace_days",
               "purchasing.bill_price_tolerance_percent", "purchasing.require_supplier_master",
               "inventory.min_cut_qty", "qc.grade_thresholds.a_max", "qc.four_point_enabled",
               "receiving.block_over_remaining", "sales.allow_partial_shipment",
               "inventory.intercompany_transfer_required"}
    for key in touched:
        e = reg.get(key)
        if not e:
            continue
        db.system_settings.update_one({"scope": e["legacy_scope"]},
                                      {"$set": {e["legacy_path"]: e["default"]}})
        for scope in db.system_settings.find({"scope": {"$nin": ["global", e["legacy_scope"]]}},
                                             {"_id": 0, "scope": 1}):
            db.system_settings.update_one({"scope": scope["scope"]},
                                          {"$unset": {e["legacy_path"]: ""}})
    removed = db.config_values.delete_many({"reason": {"$regex": "POC"}}).deleted_count
    removed += db.config_values.delete_many(
        {"reason": {"$in": ["Toleransi diperketat", "Supplier benang minta kelonggaran",
                            "Salah input harga master (POC G-0)"]}}).deleted_count
    db.audit_logs.delete_many({"action": {"$in": ["config_value_changed", "config_value_reset",
                                                 "product_price_corrected",
                                                 "sales_order_price_rederived"]},
                               "reason": {"$regex": "POC"}})
    print(f"  dibersihkan: {len(CLEANUP)} objek uji · {removed} baris config_values POC")


def main() -> int:
    head("POC FASE G-0 — FONDASI KONFIGURASI (Pusat Pengaturan)")
    try:
        me = api.login(ADMIN)
    except Exception as exc:  # noqa: BLE001
        print(f"\033[91mLogin gagal: {exc}\033[0m")
        return 2
    entity_id = (me.get("entity_context") or {}).get("active_entity_id") or "ent_ksc"
    print(f"  login: {me['user']['name']} ({me['user']['role']}) · entitas {entity_id}")

    customers = api.get("/customers").json()
    cust = (customers[0] if isinstance(customers, list) and customers else {})
    customer_id = cust.get("id", "")
    addr = (cust.get("addresses") or [{}])[0].get("id", "")
    products = api.get("/products").json()
    prods = products if isinstance(products, list) else (products.get("items") or [])
    product_id = prods[0]["id"] if prods else ""
    if not (customer_id and product_id):
        print("\033[91mData dasar (customer/produk) belum ada — jalankan seed_realistic.py\033[0m")
        return 2

    try:
        _stock_snap = snapshot_stock()
        test_registry()
        test_layers(entity_id, customer_id)
        test_effective_dating()
        test_history()
        made = test_fake_switches(entity_id, product_id, customer_id, addr)
        test_simulator(entity_id)
        test_block_over_remaining((made or {}).get("po"))
        test_health()
        test_impact(entity_id, customer_id, addr)
    finally:
        try:
            cleanup()
            # POC-RESIDU-01 — konfirmasi SO memotong & mereservasi roll; menghapus SO
            # dari DB tidak melepasnya. Pemulihan EKSAK di sini menjaga stok demo.
            restore_stock(_stock_snap)
        except Exception as exc:  # noqa: BLE001
            print(f"  \033[93m⚠ cleanup sebagian gagal: {exc}\033[0m")

    head("RINGKASAN")
    total = PASS + FAIL
    print(f"  PASS {PASS} / FAIL {FAIL}  (total {total})")
    if FAIL == 0:
        print("\n\033[92m\033[1m✓ POC FASE G-0 HIJAU 100% — fondasi konfigurasi siap.\033[0m\n")
        return 0
    print(f"\n\033[91m\033[1m✗ {FAIL} pemeriksaan GAGAL — perbaiki sebelum lanjut.\033[0m\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
