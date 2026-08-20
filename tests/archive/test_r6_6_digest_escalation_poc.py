#!/usr/bin/env python3
"""POC R6.6 — Ringkasan Harian (Digest) + Eskalasi Bertingkat + Filter Notifikasi.

Diuji via HTTP (server nyata, TANPA mock). Motor dipakai HANYA untuk setup/teardown
data uji (mem-backdate notifikasi — mustahil menunggu 8 jam nyata) dan verifikasi
langsung di koleksi.

  A. RBAC pengaturan baru (manager tidak boleh configure, sales/warehouse 403)
  B. Validasi pengaturan: delivery_mode, after_hours, max_level, min_severity
  C. RINGKASAN HARIAN: 1 pesan per penerima, dikelompokkan per tipe, dedupe harian
  D. MODE DIGEST menekan pesan per-alert; MODE INSTANT tetap mengirim per-alert
  E. CRITICAL BYPASS: alert PENTING tetap dikirim seketika walau mode digest
  F. ESKALASI: sales → manager → admin, tandai induk, tidak berulang, batas level,
     bisa dinonaktifkan
  G. Scoping notifikasi eskalasi (sales TIDAK melihat eskalasi milik manager)
  H. Pratinjau digest (endpoint /scheduler/digest-preview)

Jalankan: cd /app && python test_r6_6_digest_escalation_poc.py
"""
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("KN_API", "http://localhost:8001") + "/api"
PASS, FAIL = 0, 0
FAILURES = []


def _req(method, path, token=None, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"detail": raw[:300]}
    except Exception as exc:  # noqa: BLE001
        return 0, {"detail": str(exc)}


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \u2705 {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label} {extra}".strip())
        print(f"  \u274c {label} {extra}")


def login(email, password="demo12345"):
    st, body = _req("POST", "/auth/login", body={"email": email, "password": password})
    return body.get("token", "") if st == 200 else ""


def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    url, name = "mongodb://localhost:27017", "test_database"
    try:
        for line in open("/app/backend/.env"):
            if line.startswith("MONGO_URL="):
                url = line.split("=", 1)[1].strip().strip('"')
            if line.startswith("DB_NAME="):
                name = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return AsyncIOMotorClient(url)[name]


def now_utc():
    return datetime.now(timezone.utc)


async def main():  # noqa: C901, PLR0915 — POC linear agar mudah dibaca
    db = _mongo()
    print("=" * 70)
    print("POC R6.6 — Ringkasan Harian, Eskalasi Bertingkat & Filter Notifikasi")
    print("=" * 70)

    # ── A. RBAC ───────────────────────────────────────────────────────────
    print("\n[A] RBAC pengaturan baru")
    admin = login("admin@kainnusantara.id")
    manager = login("manager@kainnusantara.id")
    sales = login("sales@kainnusantara.id")
    wh = login("warehouse@kainnusantara.id")
    ok(all([admin, manager, sales, wh]), "A0: login 4 role")

    st, _ = _req("PUT", "/scheduler/settings", manager, {"escalation": {"after_hours": 6}})
    ok(st == 403, "A1: manager dilarang mengubah kebijakan eskalasi (403)", f"got {st}")
    st, _ = _req("GET", "/scheduler/digest-preview?role=manager", sales)
    ok(st == 403, "A2: sales dilarang melihat pratinjau ringkasan (403)", f"got {st}")
    st, _ = _req("GET", "/scheduler/digest-preview?role=manager", wh)
    ok(st == 403, "A3: warehouse dilarang melihat pratinjau ringkasan (403)", f"got {st}")
    st, _ = _req("GET", "/scheduler/digest-preview?role=manager", manager)
    ok(st == 200, "A4: manager BOLEH melihat pratinjau ringkasan (view)", f"got {st}")

    # ── B. Validasi pengaturan ────────────────────────────────────────────
    print("\n[B] Validasi pengaturan digest & eskalasi")
    st, b = _req("PUT", "/scheduler/settings", admin, {"wa": {"delivery_mode": "harian"}})
    ok(st == 400, "B1: delivery_mode tak dikenal ditolak 400", f"got {st}")
    st, _ = _req("PUT", "/scheduler/settings", admin, {"escalation": {"after_hours": 0}})
    ok(st == 400, "B2: after_hours 0 ditolak 400", f"got {st}")
    st, _ = _req("PUT", "/scheduler/settings", admin, {"escalation": {"after_hours": 100}})
    ok(st == 400, "B3: after_hours 100 ditolak 400", f"got {st}")
    st, _ = _req("PUT", "/scheduler/settings", admin, {"escalation": {"max_level": 0}})
    ok(st == 400, "B4: max_level 0 ditolak 400", f"got {st}")
    st, _ = _req("PUT", "/scheduler/settings", admin, {"escalation": {"max_level": 9}})
    ok(st == 400, "B5: max_level 9 ditolak 400", f"got {st}")
    st, _ = _req("PUT", "/scheduler/settings", admin, {"escalation": {"min_severity": "gawat"}})
    ok(st == 400, "B6: min_severity eskalasi invalid ditolak 400", f"got {st}")

    st, b = _req("PUT", "/scheduler/settings", admin, {
        "escalation": {"enabled": True, "after_hours": 8, "min_severity": "warning",
                       "max_level": 2}})
    ok(st == 200 and b.get("escalation", {}).get("after_hours") == 8,
       "B7: kebijakan eskalasi tersimpan", f"got {st} {b.get('escalation')}")
    st, b = _req("GET", "/scheduler/settings", admin)
    ok(st == 200 and b.get("delivery_modes") == ["instant", "digest"],
       "B8: daftar mode pengiriman tersedia", f"got {b.get('delivery_modes')}")
    ok(b.get("escalation", {}).get("max_level") == 2,
       "B9: kebijakan eskalasi terbaca di GET settings")

    # ── C. Ringkasan harian ───────────────────────────────────────────────
    print("\n[C] RINGKASAN HARIAN (digest)")
    st, _ = _req("PUT", "/scheduler/settings", admin, {
        "wa": {"enabled": True, "provider": "simulated", "min_severity": "warning",
               "delivery_mode": "digest", "critical_bypass": True, "send_to_roles": True}})
    ok(st == 200, "C1: aktifkan WA simulasi + mode Ringkasan Harian", f"got {st}")

    day = now_utc().isoformat()[:10]
    await db.sys_wa_outbox.delete_many({"notif_type": "daily_digest"})
    st, run = _req("POST", "/scheduler/jobs/daily_digest/run", admin, {})
    ok(st == 200 and run.get("status") == "success" and run.get("created", 0) > 0,
       "C2: job Ringkasan Harian sukses & mengirim >0 pesan",
       f"got {st} {run.get('created')} {run.get('error')}")
    digests = await db.sys_wa_outbox.find({"notif_type": "daily_digest"}, {"_id": 0}).to_list(100)
    ok(len(digests) == run.get("created"), "C3: jumlah pesan di Outbox == created",
       f"{len(digests)} vs {run.get('created')}")
    sample = digests[0] if digests else {}
    ok("RINGKASAN HARIAN" in (sample.get("text") or ""),
       "C4: isi pesan adalah ringkasan (bukan per-alert)")
    ok(sample.get("digest_groups", 0) >= 1 and sample.get("digest_alerts", 0) >= 1,
       "C5: metadata kelompok & jumlah alert tercatat",
       f"groups={sample.get('digest_groups')} alerts={sample.get('digest_alerts')}")
    ok(str(sample.get("to", "")).startswith("62"), "C6: nomor tujuan ternormalisasi 62xx")
    ok(sample.get("status") in ("simulated", "sent"), "C7: status pengiriman valid")
    ok(all(d.get("dedupe_key") == f"digest:{day}|{d['to']}" for d in digests),
       "C8: kunci dedupe digest = digest:<hari>|<nomor>")
    ok(len({d["to"] for d in digests}) == len(digests),
       "C9: maksimal 1 ringkasan per nomor")

    st, run2 = _req("POST", "/scheduler/jobs/daily_digest/run", admin, {})
    ok(st == 200 and run2.get("created") == 0,
       "C10: rerun hari sama TIDAK mengirim ulang (idempotent)", f"got {run2.get('created')}")
    total_after = await db.sys_wa_outbox.count_documents({"notif_type": "daily_digest"})
    ok(total_after == len(digests), "C11: jumlah pesan digest tidak bertambah")

    # Perbandingan volume: 1 digest vs N alert individual per penerima.
    ok(sample.get("digest_alerts", 0) > 1,
       "C12: 1 pesan menggantikan banyak alert (anti-banjir notifikasi)",
       f"alerts={sample.get('digest_alerts')}")

    # ── D. Mode digest menekan pesan per-alert ────────────────────────────
    # CATATAN: Outbox WA di-dedupe per (dedupe_key notifikasi, nomor) → 1 pesan per
    # alert per hari per tujuan. Agar uji ini VALID (bukan lolos karena dedupe),
    # baris outbox untuk kunci alert yang diuji dibersihkan lebih dulu, sehingga
    # push yang tidak muncul benar-benar akibat mode digest.
    print("\n[D] Mode DIGEST menekan pesan per-alert; INSTANT tetap kirim")

    async def _clean_outbox_for(dedupe_key):
        import re as _re
        return (await db.sys_wa_outbox.delete_many(
            {"dedupe_key": {"$regex": f"^{_re.escape(dedupe_key)}\\|"}})).deleted_count

    target = await db.notifications.find_one({"type": "low_stock"}, {"_id": 0})
    if not target:
        ok(False, "D0: butuh minimal 1 notifikasi low_stock dari data seed")
    else:
        alert_key = target["dedupe_key"]
        # -- mode digest (aktif dari bagian C) --
        await db.notifications.delete_one({"id": target["id"]})
        await _clean_outbox_for(alert_key)
        before = await db.sys_wa_outbox.count_documents({"notif_type": "low_stock"})
        st, g = _req("POST", "/notifications/generate", admin, {})
        ok(st == 200 and g.get("created", 0) >= 1,
           "D1: notifikasi low_stock dibuat ulang dari data NYATA", f"got {st} {g}")
        after = await db.sys_wa_outbox.count_documents({"notif_type": "low_stock"})
        ok(after == before, "D2: mode digest → TIDAK ada pesan per-alert baru",
           f"{before} -> {after}")

        # -- mode instan --
        st, _ = _req("PUT", "/scheduler/settings", admin, {"wa": {"delivery_mode": "instant"}})
        ok(st == 200, "D3: ganti ke mode Instan")
        recreated = await db.notifications.find_one({"dedupe_key": alert_key}, {"_id": 0})
        if recreated:
            await db.notifications.delete_one({"id": recreated["id"]})
        await _clean_outbox_for(alert_key)
        before2 = await db.sys_wa_outbox.count_documents({"notif_type": "low_stock"})
        st, g2 = _req("POST", "/notifications/generate", admin, {})
        after2 = await db.sys_wa_outbox.count_documents({"notif_type": "low_stock"})
        ok(after2 > before2, "D4: mode instan → pesan per-alert TERKIRIM",
           f"{before2} -> {after2} (created={g2.get('created')})")
        st, _ = _req("PUT", "/scheduler/settings", admin, {"wa": {"delivery_mode": "digest"}})
        ok(st == 200, "D5: kembali ke mode Ringkasan untuk uji berikutnya")

    # ── E/F. Eskalasi bertingkat ──────────────────────────────────────────
    print("\n[E] ESKALASI BERTINGKAT (sales → manager → admin)")
    created_at = (now_utc() - timedelta(hours=20)).isoformat()
    parent_id = "ntf_poc_r66_parent"
    await db.notifications.delete_many({"id": parent_id})
    await db.notifications.delete_many({"ref": f"escal:{parent_id}:1"})
    parent_ref = "poc_r66:esc-1"
    await db.notifications.insert_one({
        "id": parent_id, "entity_id": None, "recipient_role": "sales",
        "recipient_user": None, "type": "poc_r66", "title": "Uji eskalasi POC R6.6",
        "body": "Notifikasi uji yang sengaja dibiarkan belum dibaca 20 jam.",
        "link": "orders", "severity": "warning", "ref": parent_ref,
        "dedupe_key": f"poc_r66:{parent_ref}:{created_at[:10]}", "read": False,
        "created_at": created_at, "action_type": "", "action_id": "", "action_role": "",
    })
    wa_before = await db.sys_wa_outbox.count_documents({"notif_type": "escalation"})
    st, run = _req("POST", "/scheduler/jobs/escalation_scan/run", admin, {})
    ok(st == 200 and run.get("status") == "success" and run.get("created", 0) >= 1,
       "E1: job eskalasi sukses & menaikkan >=1 alert",
       f"got {st} {run.get('created')} {run.get('error')}")
    esc1 = await db.notifications.find_one({"escalated_from": parent_id}, {"_id": 0})
    ok(bool(esc1), "E2: notifikasi ESKALASI terbentuk untuk induk uji")
    if esc1:
        ok(esc1.get("recipient_role") == "manager",
           "E3: eskalasi level-1 ditujukan ke MANAGER", f"got {esc1.get('recipient_role')}")
        ok(esc1.get("severity") == "critical",
           "E4: severity dinaikkan ke critical", f"got {esc1.get('severity')}")
        ok(esc1.get("escalation_depth") == 1, "E5: kedalaman rantai = 1",
           f"got {esc1.get('escalation_depth')}")
        ok(esc1.get("title", "").startswith("ESKALASI:"), "E6: judul diberi penanda ESKALASI")
        ok("20 jam" in esc1.get("body", "") or "jam" in esc1.get("body", ""),
           "E7: isi menyebut lama tak ditindak")
        ok(esc1.get("link") == "orders", "E8: deep-link modul asal dipertahankan")
    parent = await db.notifications.find_one({"id": parent_id}, {"_id": 0})
    ok(parent.get("escalation_level") == 1 and parent.get("escalated_to") == "manager",
       "E9: induk ditandai sudah dieskalasi (anti-berulang)",
       f"got {parent.get('escalation_level')} {parent.get('escalated_to')}")

    st, run = _req("POST", "/scheduler/jobs/escalation_scan/run", admin, {})
    again = await db.notifications.count_documents({"escalated_from": parent_id})
    ok(again == 1, "E10: rerun TIDAK mengeskalasi induk yang sama dua kali", f"got {again}")

    print("\n[F] Rantai level-2 & pagar batas")
    if esc1:
        await db.notifications.update_one(
            {"id": esc1["id"]},
            {"$set": {"created_at": (now_utc() - timedelta(hours=20)).isoformat()}})
        st, _ = _req("POST", "/scheduler/jobs/escalation_scan/run", admin, {})
        esc2 = await db.notifications.find_one({"escalated_from": esc1["id"]}, {"_id": 0})
        ok(bool(esc2), "F1: eskalasi level-2 terbentuk dari eskalasi level-1")
        if esc2:
            ok(esc2.get("recipient_role") == "admin",
               "F2: level-2 ditujukan ke ADMIN", f"got {esc2.get('recipient_role')}")
            ok(esc2.get("escalation_depth") == 2, "F3: kedalaman rantai = 2",
               f"got {esc2.get('escalation_depth')}")
            # Level tertinggi: notifikasi admin tidak boleh dieskalasi lagi.
            await db.notifications.update_one(
                {"id": esc2["id"]},
                {"$set": {"created_at": (now_utc() - timedelta(hours=30)).isoformat()}})
            _req("POST", "/scheduler/jobs/escalation_scan/run", admin, {})
            esc3 = await db.notifications.count_documents({"escalated_from": esc2["id"]})
            ok(esc3 == 0, "F4: notifikasi level ADMIN tidak dieskalasi lagi (berhenti)",
               f"got {esc3}")
        wa_after = await db.sys_wa_outbox.count_documents({"notif_type": "escalation"})
        ok(wa_after > wa_before,
           "F5: CRITICAL BYPASS — eskalasi tetap dikirim WA walau mode Ringkasan",
           f"{wa_before} -> {wa_after}")

    # Nonaktifkan eskalasi
    st, _ = _req("PUT", "/scheduler/settings", admin, {"escalation": {"enabled": False}})
    parent2 = "ntf_poc_r66_parent2"
    await db.notifications.delete_many({"id": parent2})
    ref2 = "poc_r66:esc-2"
    ca2 = (now_utc() - timedelta(hours=20)).isoformat()
    await db.notifications.insert_one({
        "id": parent2, "entity_id": None, "recipient_role": "sales", "recipient_user": None,
        "type": "poc_r66", "title": "Uji eskalasi nonaktif", "body": "-", "link": "",
        "severity": "warning", "ref": ref2,
        "dedupe_key": f"poc_r66:{ref2}:{ca2[:10]}", "read": False, "created_at": ca2,
        "action_type": "", "action_id": "", "action_role": "",
    })
    st, run = _req("POST", "/scheduler/jobs/escalation_scan/run", admin, {})
    ok(run.get("created") == 0 and "nonaktif" in (run.get("detail") or ""),
       "F6: eskalasi dinonaktifkan → tidak ada alert dinaikkan",
       f"got {run.get('created')} {run.get('detail')}")
    st, _ = _req("PUT", "/scheduler/settings", admin, {"escalation": {"enabled": True}})

    # Batas ambang: severity info tidak dieskalasi (min_severity=warning)
    parent3 = "ntf_poc_r66_parent3"
    await db.notifications.delete_many({"id": parent3})
    ref3 = "poc_r66:esc-3"
    ca3 = (now_utc() - timedelta(hours=20)).isoformat()
    await db.notifications.insert_one({
        "id": parent3, "entity_id": None, "recipient_role": "sales", "recipient_user": None,
        "type": "poc_r66", "title": "Uji severity info", "body": "-", "link": "",
        "severity": "info", "ref": ref3,
        "dedupe_key": f"poc_r66:{ref3}:{ca3[:10]}", "read": False, "created_at": ca3,
        "action_type": "", "action_id": "", "action_role": "",
    })
    _req("POST", "/scheduler/jobs/escalation_scan/run", admin, {})
    n_info = await db.notifications.count_documents({"escalated_from": parent3})
    ok(n_info == 0, "F7: alert severity INFO tidak dieskalasi (di bawah ambang)", f"got {n_info}")

    # Notifikasi yang sudah DIBACA tidak dieskalasi
    parent4 = "ntf_poc_r66_parent4"
    await db.notifications.delete_many({"id": parent4})
    ref4 = "poc_r66:esc-4"
    ca4 = (now_utc() - timedelta(hours=20)).isoformat()
    await db.notifications.insert_one({
        "id": parent4, "entity_id": None, "recipient_role": "sales", "recipient_user": None,
        "type": "poc_r66", "title": "Uji sudah dibaca", "body": "-", "link": "",
        "severity": "critical", "ref": ref4,
        "dedupe_key": f"poc_r66:{ref4}:{ca4[:10]}", "read": True, "created_at": ca4,
        "action_type": "", "action_id": "", "action_role": "",
    })
    _req("POST", "/scheduler/jobs/escalation_scan/run", admin, {})
    n_read = await db.notifications.count_documents({"escalated_from": parent4})
    ok(n_read == 0, "F8: alert yang SUDAH DIBACA tidak dieskalasi", f"got {n_read}")

    # ── G. Scoping notifikasi eskalasi ────────────────────────────────────
    print("\n[G] Scoping notifikasi eskalasi di bell")
    st, mgr_list = _req("GET", "/notifications", manager)
    ok(st == 200 and any(n.get("type") == "escalation" for n in mgr_list),
       "G1: manager melihat notifikasi ESKALASI di bell-nya", f"got {st}")
    st, sales_list = _req("GET", "/notifications", sales)
    leaked = [n for n in sales_list if n.get("type") == "escalation"
              and n.get("recipient_role") in ("manager", "admin")]
    ok(st == 200 and not leaked,
       "G2: sales TIDAK melihat eskalasi milik manager/admin (tidak bocor)",
       f"leak={len(leaked)}")
    st, unread = _req("GET", "/notifications?unread_only=true", manager)
    ok(st == 200 and all(not n.get("read") for n in unread),
       "G3: filter unread_only mengembalikan hanya yang belum dibaca")
    ok(all({"severity", "type"} <= set(n.keys()) for n in mgr_list[:5]),
       "G4: setiap notifikasi punya field severity & type (dasar filter bell)")

    # ── H. Pratinjau digest ───────────────────────────────────────────────
    print("\n[H] Pratinjau Ringkasan Harian")
    st, prev = _req("GET", "/scheduler/digest-preview?role=manager", admin)
    ok(st == 200 and prev.get("total", 0) > 0 and prev.get("groups"),
       "H1: pratinjau berisi kelompok alert nyata", f"got {st} {prev.get('total')}")
    ok("RINGKASAN HARIAN" in (prev.get("text") or ""), "H2: pratinjau menyertakan teks pesan")
    ok(prev.get("delivery_mode") == "digest" and prev.get("wa_enabled") is True,
       "H3: pratinjau melaporkan mode & status kanal",
       f"got {prev.get('delivery_mode')} {prev.get('wa_enabled')}")
    st, _ = _req("GET", "/scheduler/digest-preview?role=dukun", admin)
    ok(st == 400, "H4: peran pratinjau tak dikenal ditolak 400", f"got {st}")
    st, ringkas = _req("GET", "/scheduler/summary", admin)
    ok(st == 200 and "escalation" in ringkas and ringkas.get("delivery_mode") == "digest",
       "H5: KPI ringkas memuat status eskalasi & mode pengiriman", f"got {st}")
    ok(ringkas.get("jobs_total") == 9, "H6: total job kini 9 (7 alert + eskalasi + ringkasan)",
       f"got {ringkas.get('jobs_total')}")

    # ── I. Ketahanan scheduler (regresi bug lock basi) ────────────────────
    print("\n[I] Ketahanan scheduler (lock single-instance)")
    st, jobs_res = _req("GET", "/scheduler/jobs", admin)
    ok(st == 200 and jobs_res.get("running") is True,
       "I1: scheduler AKTIF (tidak mati akibat lock basi pasca hot-reload)",
       f"running={jobs_res.get('running')}")
    jobs_all = jobs_res.get("jobs", [])
    daily = next((j for j in jobs_all if j["id"] == "daily_digest"), {})
    esc_job = next((j for j in jobs_all if j["id"] == "escalation_scan"), {})
    ok(bool(daily.get("next_run")), "I2: job Ringkasan Harian punya jadwal berikutnya",
       f"got {daily.get('next_run')}")
    ok(bool(esc_job.get("next_run")), "I3: job Eskalasi punya jadwal berikutnya",
       f"got {esc_job.get('next_run')}")
    ok(daily.get("schedule_label", "").startswith("Harian 08:30"),
       "I4: ringkasan dijadwalkan 08:30 WIB (setelah semua job alert)",
       f"got {daily.get('schedule_label')}")
    ok("Setiap 2 jam" in esc_job.get("schedule_label", ""),
       "I5: eskalasi dipindai setiap 2 jam", f"got {esc_job.get('schedule_label')}")
    lock_doc = await db.system_settings.find_one({"scope": "alerts"}, {"_id": 0, "lock": 1}) or {}
    owner = (lock_doc.get("lock") or {}).get("owner", "")
    alive = os.path.exists(f"/proc/{owner.rsplit(':', 1)[-1]}") if ":" in owner else False
    ok(alive, "I6: pemegang lock adalah proses yang HIDUP (bukan lock basi)",
       f"owner={owner}")

    # ── Teardown: bersihkan data uji sintetis (jaga invarian integritas) ──
    print("\n[Z] Bersihkan data uji")
    poc_parents = [parent_id, parent2, parent3, parent4]
    chain = await db.notifications.find(
        {"$or": [{"escalated_from": {"$in": poc_parents}}, {"type": "poc_r66"}]},
        {"_id": 0, "id": 1}).to_list(50)
    ids = [c["id"] for c in chain]
    # eskalasi level-2 (anak dari eskalasi level-1)
    more = await db.notifications.find({"escalated_from": {"$in": ids}},
                                       {"_id": 0, "id": 1}).to_list(50)
    ids += [m["id"] for m in more]
    r1 = await db.notifications.delete_many({"id": {"$in": ids + poc_parents}})
    r2 = await db.sys_wa_outbox.delete_many({"notification_id": {"$in": ids}})
    ok(True, f"Z1: {r1.deleted_count} notifikasi uji & {r2.deleted_count} pesan WA uji dibersihkan")

    print("\n" + "=" * 70)
    print(f"=== HASIL R6.6: PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        print("\nGAGAL:")
        for f in FAILURES:
            print(" -", f)
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
