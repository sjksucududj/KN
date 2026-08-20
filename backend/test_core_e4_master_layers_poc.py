#!/usr/bin/env python3
"""POC FASE E-4 (E4.2/E4.3) — MASTER BERLAPIS: **global → badan usaha**.

Keputusan pemilik #6: *"semua master/konfigurasi yang masih bersama harus jadi per
entitas"*. BUKTI-MERAH yang dikunci berkas ini (keadaan nyata sebelum fase ini):

    db.payment_terms      6 baris · 0 ber-entity_id   → satu syarat bayar untuk SEMUA
    db.expense_categories 8 baris · 0 ber-entity_id   → satu pemetaan akun untuk SEMUA
    db.document_templates 2 baris · 0 ber-entity_id   → kop surat KSC dipakai CV Kanda

Yang dibuktikan di sini (dan HARUS tetap benar selamanya):
  1. Baris GLOBAL tetap terlihat dari konteks badan usaha mana pun (tidak hilang
     setelah koleksi pindah SHARED → SCOPED) dan berlencana `Global`.
  2. "Buat khusus" (override) menyalin baris global menjadi milik badan usaha aktif,
     berlencana `Badan usaha ini`, dan baris global-nya ditandai `is_overridden`.
  3. Nilai override MENANG di daftar **efektif** — dan daftar efektif tidak kembar
     (satu kode = satu baris), karena dropdown pesanan/POS memakai daftar ini.
  4. **Isolasi**: override milik CV Kanda Suka TIDAK terlihat & TIDAK berlaku di
     PT Kain Suka Cita.
  5. Mengubah baris GLOBAL dari konteks satu badan usaha **DITOLAK 409** dengan
     kalimat menuntun (mencegah admin diam-diam mengubah nilai seluruh grup).
     Di mode "Semua Entitas" perubahan itu BOLEH.
  6. "Kembalikan ke global" menghapus override → nilai efektif kembali ke global.
  7. Konsumen nyata ikut berlapis: `net_days` pesanan penjualan memakai override
     badan usaha, dan template cetak Surat Jalan memakai kop surat badan usaha
     pemilik dokumen.
  8. Di mode "Semua Entitas" baris baru lahir sebagai GLOBAL (tak ada pemiliknya).
  9. **Nol residu**: seluruh data uji dibersihkan; POC aman dijalankan berulang.

Jalankan:  cd /app && python backend/test_core_e4_master_layers_poc.py
"""
from __future__ import annotations

import os
import sys
import uuid

import requests

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
PW = "demo12345"
ADMIN = "admin@kainnusantara.id"

PASS = 0
FAIL = 0
CLEANUP: list = []          # (collection, id)


def ok(cond: bool, label: str, extra: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f"\n         → {extra}" if extra else ""))
    return bool(cond)


def login(email: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": PW}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "Content-Type": "application/json"})
    return s


def h(entity: str) -> dict:
    return {"X-Entity-Id": entity}


def _db():
    from pymongo import MongoClient
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ["DB_NAME"]]


def rows_of(sess: requests.Session, kind: str, entity: str) -> list:
    r = sess.get(f"{BASE}/api/entity-masters/{kind}", headers=h(entity), timeout=30)
    assert r.status_code == 200, f"{kind} layered: {r.status_code} {r.text[:200]}"
    return r.json().get("rows", [])


def effective(sess: requests.Session, kind: str, entity: str) -> list:
    r = sess.get(f"{BASE}/api/entity-masters/{kind}/effective", headers=h(entity), timeout=30)
    assert r.status_code == 200, f"{kind} effective: {r.status_code} {r.text[:200]}"
    return r.json()


def find(rows: list, key_field: str, key: str, scope: str = "") -> dict:
    for r in rows:
        if r.get(key_field) == key and (not scope or r.get("entity_scope") == scope):
            return r
    return {}


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    tag = uuid.uuid4().hex[:6]
    audit_before = {d["id"] for d in _db().audit_logs.find({}, {"_id": 0, "id": 1})}
    print("=" * 78)
    print("  POC FASE E-4 (E4.2/E4.3) — MASTER BERLAPIS: global → badan usaha")
    print("=" * 78)

    admin = login(ADMIN)
    ents = admin.get(f"{BASE}/api/entities", params={"status": "active"}, timeout=30).json()
    ok(len(ents) >= 2, f"prasyarat: minimal 2 badan usaha aktif (ada {len(ents)})")
    if len(ents) < 2:
        return 1
    a_id, b_id = ents[0]["id"], ents[1]["id"]
    a_name = ents[0].get("short_name") or a_id
    b_name = ents[1].get("short_name") or b_id
    print(f"  badan usaha uji: A={a_id} ({a_name}) · B={b_id} ({b_name})\n")

    # ── 1. Baris GLOBAL tetap terlihat & berlencana ──────────────────────────
    print("── 1. Baris global tidak hilang setelah koleksi jadi per badan usaha ──")
    for kind, key_field, label in (("payment-terms", "code", "Syarat Pembayaran"),
                                   ("expense-categories", "code", "Kategori Biaya"),
                                   ("document-templates", "document_type", "Template Dokumen")):
        rows = rows_of(admin, kind, a_id)
        globals_ = [r for r in rows if r.get("entity_scope") == "global"]
        ok(len(globals_) >= 2, f"{label}: {len(globals_)} baris global terlihat dari {a_name}",
           f"rows={len(rows)}")
        ok(all(r.get("source_label") == "Global" for r in globals_),
           f"{label}: semua baris global berlencana 'Global'")
        ok(all(r.get("can_edit_here") is False for r in globals_),
           f"{label}: baris global TIDAK bisa diubah dari konteks satu badan usaha")

    terms_a = rows_of(admin, "payment-terms", a_id)
    net30 = find(terms_a, "code", "NET30", "global")
    ok(bool(net30), "syarat bayar 'NET30' ada di lapisan global (dipakai untuk uji override)")
    if not net30:
        return 1
    base_days = int(net30.get("net_days") or 0)

    # ── 2. Override: "Buat khusus <badan usaha>" ─────────────────────────────
    print("\n── 2. 'Buat khusus' menyalin baris global menjadi milik badan usaha B ──")
    r = admin.post(f"{BASE}/api/entity-masters/payment-terms/{net30['id']}/override",
                   headers=h(b_id), timeout=30)
    ok(r.status_code == 200, f"POST override NET30 untuk {b_name} → 200",
       f"dapat {r.status_code}: {r.text[:200]}")
    if r.status_code != 200:
        return 1
    ovr = r.json()
    CLEANUP.append(("payment_terms", ovr["id"]))
    ok(ovr.get("entity_id") == b_id and ovr.get("entity_scope") == "entity",
       f"baris hasil override milik {b_name} & berlencana 'Badan usaha ini'",
       f"{ovr.get('entity_id')} / {ovr.get('source_label')}")
    ok(ovr.get("overrides_id") == net30["id"],
       "baris override menyimpan jejak baris global asalnya (`overrides_id`)")

    rows_b = rows_of(admin, "payment-terms", b_id)
    glob_b = find(rows_b, "code", "NET30", "global")
    ok(glob_b.get("is_overridden") is True,
       "baris global NET30 ditandai 'sudah ditimpa' saat dilihat dari badan usaha B")

    # override kedua untuk kode yang sama harus DITOLAK (bukan menumpuk)
    r = admin.post(f"{BASE}/api/entity-masters/payment-terms/{net30['id']}/override",
                   headers=h(b_id), timeout=30)
    ok(r.status_code == 409, "override kedua untuk kode yang sama → 409 (tidak menumpuk)",
       f"dapat {r.status_code}: {r.text[:160]}")

    # ── 3. Nilai override MENANG & daftar efektif tidak kembar ───────────────
    print("\n── 3. Nilai override menang; daftar efektif tidak pernah kembar ──")
    new_days = base_days + 15
    r = admin.patch(f"{BASE}/api/entity-masters/payment-terms/{ovr['id']}",
                    json={"data": {"net_days": new_days, "name": f"NET30 khusus {b_name}"}},
                    headers=h(b_id), timeout=30)
    ok(r.status_code == 200, f"ubah override menjadi net_days={new_days} → 200",
       f"dapat {r.status_code}: {r.text[:200]}")

    eff_b = effective(admin, "payment-terms", b_id)
    row_b = find(eff_b, "code", "NET30")
    ok(int(row_b.get("net_days") or 0) == new_days,
       f"daftar efektif {b_name}: NET30 = {new_days} hari (override menang)",
       f"dapat {row_b.get('net_days')}")
    codes = [r.get("code") for r in eff_b]
    ok(len(codes) == len(set(codes)),
       f"daftar efektif {b_name} tidak kembar ({len(codes)} baris, {len(set(codes))} kode unik)")

    # dropdown nyata (endpoint yang dipakai layar pesanan/POS) juga tidak kembar
    r = admin.get(f"{BASE}/api/payment-terms", headers=h(b_id), timeout=30)
    dd = r.json() if r.status_code == 200 else []
    dd_codes = [x.get("code") for x in dd]
    ok(r.status_code == 200 and len(dd_codes) == len(set(dd_codes)),
       "GET /api/payment-terms (dropdown pesanan & POS) tidak menampilkan kode kembar",
       f"{dd_codes}")
    ok(int((find(dd, 'code', 'NET30') or {}).get("net_days") or 0) == new_days,
       "dropdown badan usaha B ikut memakai nilai override")

    # ── 4. Isolasi: override B tidak menyentuh A ─────────────────────────────
    print("\n── 4. Isolasi: override badan usaha B tidak terlihat/berlaku di A ──")
    rows_a = rows_of(admin, "payment-terms", a_id)
    ok(not find(rows_a, "code", "NET30", "entity"),
       f"{a_name} tidak melihat baris khusus milik {b_name}")
    eff_a = effective(admin, "payment-terms", a_id)
    ok(int((find(eff_a, "code", "NET30") or {}).get("net_days") or 0) == base_days,
       f"{a_name} tetap memakai nilai global ({base_days} hari)",
       f"dapat {(find(eff_a, 'code', 'NET30') or {}).get('net_days')}")

    # ── 5. Baris GLOBAL tak boleh diubah dari konteks satu badan usaha ───────
    print("\n── 5. Mengubah baris GLOBAL dari konteks badan usaha → ditolak menuntun ──")
    r = admin.patch(f"{BASE}/api/entity-masters/payment-terms/{net30['id']}",
                    json={"data": {"net_days": 999}}, headers=h(b_id), timeout=30)
    ok(r.status_code == 409, "PATCH baris global (konteks badan usaha) → 409",
       f"dapat {r.status_code}: {r.text[:200]}")
    detail = (r.json() or {}).get("detail", "") if r.status_code == 409 else ""
    ok("Global" in str(detail) and ("Buat khusus" in str(detail)
                                    or "Semua Entitas" in str(detail)),
       "pesannya menjelaskan sebabnya DAN menawarkan jalan keluar",
       str(detail)[:200])
    after = find(rows_of(admin, "payment-terms", a_id), "code", "NET30", "global")
    ok(int(after.get("net_days") or 0) == base_days,
       "nilai global TIDAK berubah setelah penolakan (bukan gagal separuh jalan)")

    # di mode "Semua Entitas" perubahan global BOLEH
    r = admin.patch(f"{BASE}/api/entity-masters/payment-terms/{net30['id']}",
                    json={"data": {"notes": f"disunting POC {tag}"}},
                    headers=h("all"), timeout=30)
    ok(r.status_code == 200, "PATCH baris global di mode 'Semua Entitas' → 200",
       f"dapat {r.status_code}: {r.text[:200]}")

    # ── 6. Kembalikan ke global ──────────────────────────────────────────────
    print("\n── 6. 'Kembalikan ke global' melepas override ──")
    r = admin.delete(f"{BASE}/api/entity-masters/payment-terms/{ovr['id']}",
                     headers=h(b_id), timeout=30)
    ok(r.status_code == 200 and r.json().get("fell_back_to_global") is True,
       "DELETE override → 200 & nilai kembali mengikuti baris global",
       f"dapat {r.status_code}: {r.text[:200]}")
    eff_b2 = effective(admin, "payment-terms", b_id)
    ok(int((find(eff_b2, "code", "NET30") or {}).get("net_days") or 0) == base_days,
       f"{b_name} kembali memakai nilai global ({base_days} hari)")
    ok(not find(rows_of(admin, "payment-terms", b_id), "code", "NET30", "entity"),
       "baris override sudah tidak ada (bukan sekadar dinonaktifkan)")

    # ── 7. Konsumen nyata ikut berlapis ──────────────────────────────────────
    print("\n── 7. Konsumen nyata: kategori biaya & template cetak ikut berlapis ──")
    cats = rows_of(admin, "expense-categories", b_id)
    cat_glob = next((c for c in cats if c.get("entity_scope") == "global"), {})
    if cat_glob:
        r = admin.post(f"{BASE}/api/entity-masters/expense-categories/{cat_glob['id']}/override",
                       headers=h(b_id), timeout=30)
        if r.status_code == 200:
            cat_ovr = r.json()
            CLEANUP.append(("expense_categories", cat_ovr["id"]))
            admin.patch(f"{BASE}/api/entity-masters/expense-categories/{cat_ovr['id']}",
                        json={"data": {"account_code": "6-9999"}}, headers=h(b_id), timeout=30)
            eff_cat_b = find(effective(admin, "expense-categories", b_id),
                             "code", cat_glob.get("code"))
            eff_cat_a = find(effective(admin, "expense-categories", a_id),
                             "code", cat_glob.get("code"))
            ok(eff_cat_b.get("account_code") == "6-9999",
               f"kategori biaya '{cat_glob.get('code')}' di {b_name} memetakan ke akun override")
            ok(eff_cat_a.get("account_code") != "6-9999",
               f"kategori yang sama di {a_name} TETAP memakai akun global",
               f"dapat {eff_cat_a.get('account_code')}")
            # endpoint nyata yang dipakai layar kas kecil
            r = admin.get(f"{BASE}/api/expense-categories", headers=h(b_id), timeout=30)
            codes = [c.get("code") for c in (r.json() if r.status_code == 200 else [])]
            ok(r.status_code == 200 and len(codes) == len(set(codes)),
               "GET /api/expense-categories (layar kas kecil) tidak kembar", f"{codes}")

    tmpls = rows_of(admin, "document-templates", b_id)
    tmpl_glob = next((t for t in tmpls if t.get("entity_scope") == "global"
                      and t.get("document_type") == "surat_jalan"), {})
    if tmpl_glob:
        r = admin.post(f"{BASE}/api/entity-masters/document-templates/{tmpl_glob['id']}/override",
                       headers=h(b_id), timeout=30)
        if r.status_code == 200:
            t_ovr = r.json()
            CLEANUP.append(("document_templates", t_ovr["id"]))
            kop = f"KOP KHUSUS {b_name.upper()} {tag}"
            admin.patch(f"{BASE}/api/entity-masters/document-templates/{t_ovr['id']}",
                        json={"data": {"header": kop}}, headers=h(b_id), timeout=30)
            eff_t_b = find(effective(admin, "document-templates", b_id),
                           "document_type", "surat_jalan")
            eff_t_a = find(effective(admin, "document-templates", a_id),
                           "document_type", "surat_jalan")
            ok(eff_t_b.get("header") == kop,
               f"template Surat Jalan {b_name} memakai kop surat khusus badan usaha")
            ok(eff_t_a.get("header") != kop,
               f"template Surat Jalan {a_name} TIDAK terpengaruh (masih kop global)")
            # cetak nyata: Surat Jalan pesanan milik B harus memakai kop khusus B
            orders = admin.get(f"{BASE}/api/sales-orders", headers=h(b_id), timeout=30).json()
            order = next((o for o in orders if o.get("entity_id") == b_id), None)
            if order:
                pv = admin.get(f"{BASE}/api/documents/preview/{order['id']}",
                               params={"document_type": "surat_jalan"},
                               headers=h(b_id), timeout=60)
                body = pv.text if pv.status_code == 200 else ""
                ok(pv.status_code == 200 and kop in body,
                   f"cetak Surat Jalan {order.get('order_number', order['id'])} "
                   f"memakai kop surat {b_name}",
                   f"status={pv.status_code} · kop ditemukan={kop in body}")
            else:
                print(f"  [SKIP] tidak ada pesanan milik {b_name} untuk uji cetak")

    # ── 8. Mode "Semua Entitas": baris baru lahir GLOBAL ─────────────────────
    print("\n── 8. Di mode 'Semua Entitas' baris baru lahir sebagai GLOBAL ──")
    body = {"code": f"POC{tag.upper()}", "name": f"Term POC {tag}", "type": "credit",
            "net_days": 21, "sort": 99}
    r = admin.post(f"{BASE}/api/entity-masters/payment-terms", json=body,
                   headers=h("all"), timeout=30)
    ok(r.status_code == 200, "POST syarat bayar di mode gabungan → 200",
       f"dapat {r.status_code}: {r.text[:200]}")
    if r.status_code == 200:
        made = r.json()
        CLEANUP.append(("payment_terms", made["id"]))
        ok(made.get("entity_id") == "all" and made.get("entity_scope") == "global",
           "baris baru itu GLOBAL (tak ada satu badan usaha yang memilikinya)",
           f"{made.get('entity_id')}")
        # dan terlihat dari kedua badan usaha
        seen_a = bool(find(rows_of(admin, "payment-terms", a_id), "code", body["code"]))
        seen_b = bool(find(rows_of(admin, "payment-terms", b_id), "code", body["code"]))
        ok(seen_a and seen_b, "baris global itu langsung terlihat di kedua badan usaha")

    # baris baru saat SATU badan usaha aktif → milik badan usaha itu
    body2 = {"code": f"POCE{tag.upper()}", "name": f"Term POC entitas {tag}",
             "type": "credit", "net_days": 7, "sort": 98}
    r = admin.post(f"{BASE}/api/entity-masters/payment-terms", json=body2,
                   headers=h(b_id), timeout=30)
    if r.status_code == 200:
        made2 = r.json()
        CLEANUP.append(("payment_terms", made2["id"]))
        ok(made2.get("entity_id") == b_id,
           f"baris baru saat {b_name} aktif → menjadi milik {b_name}")
        ok(not find(rows_of(admin, "payment-terms", a_id), "code", body2["code"]),
           f"baris khusus {b_name} itu tidak terlihat di {a_name}")
    else:
        ok(False, "POST syarat bayar saat satu badan usaha aktif → 200",
           f"dapat {r.status_code}: {r.text[:200]}")

    # ── 9. Pusat Pengaturan berlapis (E4.5/E4.6) ─────────────────────────────
    print("\n── 9. Setelan operasional per badan usaha (E4.5) + kembalikan ke global (E4.6) ──")
    CFG_KEY = "lot.enforcement_mode"
    reg = admin.get(f"{BASE}/api/config/registry", timeout=30).json()
    entry = next((e for e in (reg.get("entries") or []) if e.get("key") == CFG_KEY), None)
    ok(entry is not None, f"{CFG_KEY} terdaftar di registry Pusat Pengaturan")
    if entry is not None:
        ok("entity" in (entry.get("scopes") or []),
           f"{CFG_KEY}: registry mengizinkan lapisan badan usaha (E4.5)",
           f"scopes={entry.get('scopes')}")
    ops_keys = [e for e in (reg.get("entries") or [])
                if e["key"].split(".")[0] in ("hr", "uom", "lot", "receiving", "makloon")]
    no_entity = [e["key"] for e in ops_keys if "entity" not in (e.get("scopes") or [])]
    ok(not no_entity,
       f"seluruh {len(ops_keys)} setelan hr./uom./lot./receiving./makloon. bisa per badan usaha",
       f"masih hanya-global: {no_entity[:6]}")

    def lot_mode(ent: str) -> str:
        r = admin.get(f"{BASE}/api/lots/settings", headers=h(ent), timeout=30)
        return str((r.json() or {}).get("enforcement_mode", "")) if r.status_code == 200 else ""

    base_mode_a, base_mode_b = lot_mode(a_id), lot_mode(b_id)
    ok(bool(base_mode_a) and base_mode_a == base_mode_b,
       f"awalnya kedua badan usaha memakai nilai global yang sama ('{base_mode_a}')")

    new_mode = "block" if base_mode_b != "block" else "warn"
    r = admin.put(f"{BASE}/api/config/values", headers=h(b_id), timeout=30, json={"items": [{
        "key": CFG_KEY, "value": new_mode, "scope_type": "entity", "scope_id": b_id,
        "reason": f"POC E4.5 {tag}"}]})
    ok(r.status_code == 200, f"set '{CFG_KEY}' = '{new_mode}' khusus {b_name} → 200",
       f"dapat {r.status_code}: {r.text[:200]}")
    ok(lot_mode(b_id) == new_mode,
       f"mesin lot {b_name} memakai nilai badan usaha ('{new_mode}')", f"dapat {lot_mode(b_id)}")
    ok(lot_mode(a_id) == base_mode_a,
       f"mesin lot {a_name} TIDAK terpengaruh (tetap '{base_mode_a}')", f"dapat {lot_mode(a_id)}")

    ex = admin.get(f"{BASE}/api/config/explain",
                   params={"key": CFG_KEY, "entity_id": b_id}, headers=h(b_id), timeout=30).json()
    ok(ex.get("source_layer") == "entity",
       "jejak lapisan menyebut 'Entitas' sebagai pemenang (bukan menebak)",
       f"dapat {ex.get('source_layer')}")

    r = admin.post(f"{BASE}/api/config/values/clear", headers=h(b_id), timeout=30,
                   json={"key": CFG_KEY, "scope_type": "entity", "scope_id": b_id,
                         "reason": f"POC E4.6 {tag}"})
    ok(r.status_code == 200, "'Kembalikan ke global' (POST /config/values/clear) → 200",
       f"dapat {r.status_code}: {r.text[:200]}")
    body = r.json() if r.status_code == 200 else {}
    ok(str(body.get("value_now")) == base_mode_b,
       f"nilainya kembali ke global ('{base_mode_b}'), bukan ke bawaan kode",
       f"dapat {body.get('value_now')}")
    ok(lot_mode(b_id) == base_mode_b,
       f"mesin lot {b_name} ikut kembali ke nilai global", f"dapat {lot_mode(b_id)}")
    # 'clear' pada lapisan global harus DITOLAK — tidak ada 'global' di atas global.
    r = admin.post(f"{BASE}/api/config/values/clear", headers=h("all"), timeout=30,
                   json={"key": CFG_KEY, "scope_type": "global", "scope_id": ""})
    ok(r.status_code == 400, "mengosongkan lapisan Global ditolak dengan penjelasan",
       f"dapat {r.status_code}: {r.text[:160]}")

    # ── 10. Nol residu ───────────────────────────────────────────────────────
    print("\n── 10. Bersih-bersih (POC harus bisa dijalankan berulang) ──")
    db = _db()
    removed = 0
    for coll, _id in CLEANUP:
        if _id:
            removed += db[coll].delete_many({"id": _id}).deleted_count
    removed += db.payment_terms.delete_many({"code": {"$regex": "^POC"}}).deleted_count
    # Baris konfigurasi uji (E4.5/E4.6) — termasuk baris NISAN dari 'kembalikan ke global'.
    removed += db.config_values.delete_many(
        {"reason": {"$regex": f"POC E4\\.[56] {tag}"}}).deleted_count
    # nilai global yang disunting di langkah 5 dipulihkan
    db.payment_terms.update_one({"id": net30["id"]},
                               {"$set": {"net_days": base_days}, "$unset": {"notes": ""}})
    new_audit = {d["id"] for d in db.audit_logs.find({}, {"_id": 0, "id": 1})} - audit_before
    audit_removed = (db.audit_logs.delete_many({"id": {"$in": list(new_audit)}}).deleted_count
                     if new_audit else 0)
    ok(removed >= 1, f"data uji dibersihkan ({removed} dokumen · {audit_removed} jejak audit)")

    left = (db.payment_terms.count_documents({"code": {"$regex": "^POC"}})
            + db.payment_terms.count_documents({"entity_id": {"$nin": ["all", "", None]}})
            + db.expense_categories.count_documents({"entity_id": {"$nin": ["all", "", None]}})
            + db.document_templates.count_documents({"entity_id": {"$nin": ["all", "", None]}})
            + db.config_values.count_documents({"reason": {"$regex": f"POC E4\\.[56] {tag}"}})
            + db.audit_logs.count_documents({"id": {"$in": list(new_audit)}}))
    ok(left == 0, "nol residu setelah POC (tidak ada override/jejak uji yang tertinggal)",
       f"{left} dokumen tersisa")
    restored = db.payment_terms.find_one({"id": net30["id"]}, {"_id": 0})
    ok(int((restored or {}).get("net_days") or 0) == base_days and "notes" not in (restored or {}),
       "nilai global NET30 dipulihkan seperti semula")

    print("\n" + "=" * 78)
    print(f"  HASIL: {PASS} PASS · {FAIL} FAIL")
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    sys.exit(main())
