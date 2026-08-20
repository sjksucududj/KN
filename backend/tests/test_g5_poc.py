"""FASE G-5 — **POC BUKTI-MERAH** Unlock Periode Berotoritas ("wajib dua orang & menutup sendiri").

Menguji lewat HTTP nyata (bukan unit test) seluruh janji fitur:

  1. HARD-LOCK      — posting/koreksi MUNDUR ke periode `closed` DITOLAK bila tak ada
                      jendela unlock aktif (bukan sekadar peringatan seperti dulu).
  2. DUAL CONTROL   — pengusul TIDAK boleh menyetujui usulnya sendiri.
  3. JENDELA WAKTU  — sesudah disetujui, periode terbuka sekian jam (config), dan
                      setiap JE yang lahir di jendela ditandai `backdated_in_unlock`.
  4. AUTO-RECLOSE   — jendela lewat batas → tertutup sendiri → posting mundur DITOLAK lagi.

Ditambah **BUKTI-MERAH**: pelanggaran INV-CLS-01/02 disuntik → gate WAJIB MEMERAH →
lalu dipulihkan. Tanpa itu, invarian bisa "hijau tapi hampa".

POC ini **tidak meninggalkan residu**: semua yang ia buat dihapus di akhir (dibuktikan
test terakhir). Periode uji = 2019-06 (bulan tua & kosong) pada PT `ent_ksc`.

Jalankan: `cd /app/backend && python -m pytest tests/test_g5_poc.py -q`
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
MANAGER = {"email": "manager@kainnusantara.id", "password": "demo12345"}
ENTITY = "ent_ksc"
PTYPE, PKEY = "month", "2019-06"
DAY_IN = "2019-06-15"
DAY_IN2 = "2019-06-16"
STATE: dict = {}


def _login(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    # Konteks entitas KONKRET — unlock/backdate wajib per-PT (bukan mode "all").
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "X-Entity-Id": ENTITY})
    return s


def _db():
    from pymongo import MongoClient
    cli = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli[os.environ.get("DB_NAME", "test_database")]


def _wipe():
    """Bersihkan residu periode uji sebelum & sesudah (idempotent)."""
    db = _db()
    db.period_unlock_requests.delete_many(
        {"entity_id": ENTITY, "period_key": PKEY})
    db.period_unlock_requests.delete_many({"id": "plu_poc_fake"})
    db.journal_entries.delete_many(
        {"entity_id": ENTITY, "date": {"$regex": "^2019-06"}})
    db.period_closings.delete_many({"entity_id": ENTITY, "period_key": PKEY})


def _je_payload(date):
    return {"date": date, "description": "[G5-POC] koreksi uji", "entity_id": ENTITY,
            "lines": [{"account_code": "1-1100", "debit": 1000, "credit": 0,
                       "description": "kas"},
                      {"account_code": "1-1110", "debit": 0, "credit": 1000,
                       "description": "kas kecil"}]}


def _run_gate():
    """Jalankan gate hanya lapisan closing → (rc, stdout)."""
    r = subprocess.run(
        [sys.executable, "scripts/verify_data_integrity.py", "--only", "closing"],
        cwd="/app", capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def manager():
    return _login(MANAGER)


# ─── 00 · Setup: tutup periode uji ────────────────────────────────────────────
def test_00_setup_close_period(admin):
    _wipe()
    r = admin.post(f"{BASE}/api/finance/closing/close",
                   json={"period_type": PTYPE, "period_key": PKEY,
                         "entity_id": ENTITY, "note": "POC G-5"})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["status"] == "closed"
    STATE["closing_id"] = rec["id"]
    # Konfirmasi status_for_date melihat periode tertutup.
    s = admin.get(f"{BASE}/api/finance/closing/status",
                  params={"date": DAY_IN, "entity_id": ENTITY})
    assert s.status_code == 200 and s.json().get("closed") is True, s.text
    print("✅ 00 periode 2019-06 ditutup")


# ─── 01 · Hard-lock: posting mundur DITOLAK tanpa unlock ──────────────────────
def test_01_guard_blocks_without_unlock(admin):
    r = admin.post(f"{BASE}/api/gl/journal", json=_je_payload(DAY_IN))
    assert r.status_code == 400, f"harus DITOLAK, dapat {r.status_code}: {r.text}"
    assert "DITUTUP" in r.text or "Buka Periode" in r.text, r.text
    # Pastikan benar-benar tidak ada JE yang lahir.
    assert _db().journal_entries.count_documents(
        {"entity_id": ENTITY, "date": {"$regex": "^2019-06"}}) == 0
    print("✅ 01 hard-lock menolak jurnal mundur tanpa unlock")


# ─── 02 · Usul buka periode (alasan wajib) ────────────────────────────────────
def test_02_request_requires_reason(admin):
    r = admin.post(f"{BASE}/api/finance/period-unlocks",
                   json={"period_type": PTYPE, "period_key": PKEY,
                         "entity_id": ENTITY, "reason": "  "})
    assert r.status_code == 400 and "Alasan" in r.text, r.text

    r = admin.post(f"{BASE}/api/finance/period-unlocks",
                   json={"period_type": PTYPE, "period_key": PKEY,
                         "entity_id": ENTITY, "reason": "Koreksi salah posting Juni 2019"})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["status"] == "pending" and rec["requested_by_id"] == "user_admin_01"
    STATE["plu_id"] = rec["id"]
    print("✅ 02 usul dibuat (pending) + alasan wajib ditegakkan")


# ─── 03 · Dual control: pengusul tak boleh menyetujui sendiri ─────────────────
def test_03_self_approve_blocked(admin):
    r = admin.post(f"{BASE}/api/finance/period-unlocks/{STATE['plu_id']}/approve")
    assert r.status_code == 400, r.text
    assert "ganda" in r.text.lower() or "pengusul" in r.text.lower(), r.text
    print("✅ 03 kontrol ganda menolak self-approve")


# ─── 04 · Manager menyetujui → jendela mulai ──────────────────────────────────
def test_04_manager_approves(manager):
    r = manager.post(f"{BASE}/api/finance/period-unlocks/{STATE['plu_id']}/approve")
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["status"] == "approved"
    assert rec["approved_by_id"] == "user_manager_01"
    assert rec["window_hours"] == 24 and rec["window_until"]
    print("✅ 04 disetujui manager · jendela 24 jam aktif")


# ─── 05 · Jurnal mundur di jendela → BOLEH & ditandai ─────────────────────────
def test_05_backdated_je_allowed_and_tagged(admin):
    r = admin.post(f"{BASE}/api/gl/journal", json=_je_payload(DAY_IN))
    assert r.status_code == 200, f"harus BOLEH di jendela: {r.text}"
    je = r.json()
    assert je.get("backdated_in_unlock") == STATE["plu_id"], je
    STATE["je_id"] = je["id"]
    # je_ids terdaftar di usul-nya.
    got = admin.get(f"{BASE}/api/finance/period-unlocks",
                    params={"entity_id": ENTITY}).json()
    mine = next(x for x in got if x["id"] == STATE["plu_id"])
    assert je["id"] in mine["je_ids"], mine
    print("✅ 05 jurnal mundur diterima & ditandai backdated_in_unlock")


# ─── 06 · Banner: unlock aktif terlihat ───────────────────────────────────────
def test_06_active_banner(admin):
    r = admin.get(f"{BASE}/api/finance/period-unlocks/active",
                  params={"entity_id": ENTITY})
    assert r.status_code == 200, r.text
    active = r.json()
    assert any(x["id"] == STATE["plu_id"] for x in active), active
    row = next(x for x in active if x["id"] == STATE["plu_id"])
    assert row["window_seconds_left"] > 0
    print("✅ 06 banner: unlock aktif + sisa waktu terlihat")


# ─── 07 · Gate HIJAU (INV-CLS-01/02 lulus) ────────────────────────────────────
def test_07_gate_green(admin):
    rc, out = _run_gate()
    assert "INV-CLS-01" in out and "INV-CLS-02" in out, out[-800:]
    assert rc == 0, out[-1500:]
    print("✅ 07 gate closing HIJAU")


# ─── 08 · BUKTI-MERAH INV-CLS-01 (hapus tanda → memerah → pulih) ──────────────
def test_08_redproof_cls01(admin):
    db = _db()
    db.journal_entries.update_one({"id": STATE["je_id"]},
                                  {"$unset": {"backdated_in_unlock": ""}})
    rc, out = _run_gate()
    assert rc != 0 and "INV-CLS-01" in out, "INV-CLS-01 harus MEMERAH saat tanda dilepas"
    # pulihkan
    db.journal_entries.update_one({"id": STATE["je_id"]},
                                  {"$set": {"backdated_in_unlock": STATE["plu_id"]}})
    rc2, _ = _run_gate()
    assert rc2 == 0, "gate harus hijau lagi setelah tanda dipulihkan"
    print("✅ 08 bukti-merah INV-CLS-01 sahih")


# ─── 09 · BUKTI-MERAH INV-CLS-02 (pengusul==penyetuju → memerah → pulih) ──────
def test_09_redproof_cls02(admin):
    db = _db()
    from core_utils import now_iso
    db.period_unlock_requests.insert_one({
        "id": "plu_poc_fake", "entity_id": ENTITY, "period_type": PTYPE,
        "period_key": "2019-05", "period_label": "Mei 2019",
        "start_date": "2019-05-01", "end_date": "2019-05-31",
        "reason": "uji", "status": "approved",
        "requested_by_id": "user_x", "approved_by_id": "user_x",  # PELANGGARAN
        "requested_by": "X", "approved_by": "X",
        "window_hours": 24, "window_until": now_iso(), "je_ids": [],
        "created_at": now_iso(), "updated_at": now_iso()})
    rc, out = _run_gate()
    assert rc != 0 and "INV-CLS-02" in out, "INV-CLS-02 harus MEMERAH (kontrol ganda gagal)"
    db.period_unlock_requests.delete_one({"id": "plu_poc_fake"})
    rc2, _ = _run_gate()
    assert rc2 == 0, "gate harus hijau lagi setelah pelanggaran dihapus"
    print("✅ 09 bukti-merah INV-CLS-02 sahih")


# ─── 10 · Auto-reclose: jendela lewat batas → tertutup → tolak lagi ───────────
def test_10_auto_reclose(admin):
    from datetime import datetime, timedelta, timezone
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _db().period_unlock_requests.update_one(
        {"id": STATE["plu_id"]}, {"$set": {"window_until": past}})
    r = admin.post(f"{BASE}/api/finance/period-unlocks/reclose-expired")
    assert r.status_code == 200 and r.json().get("reclosed", 0) >= 1, r.text
    # Status jadi 'reclosed' (karena sempat ada JE mundur).
    got = admin.get(f"{BASE}/api/finance/period-unlocks",
                    params={"entity_id": ENTITY}).json()
    mine = next(x for x in got if x["id"] == STATE["plu_id"])
    assert mine["status"] == "reclosed", mine
    # Posting mundur BARU harus DITOLAK lagi (jendela sudah tutup).
    r2 = admin.post(f"{BASE}/api/gl/journal", json=_je_payload(DAY_IN2))
    assert r2.status_code == 400, f"harus DITOLAK setelah reclose: {r2.text}"
    print("✅ 10 auto-reclose menutup jendela & menolak posting mundur baru")


# ─── 11 · Bersih residu (tanpa jejak) ─────────────────────────────────────────
def test_11_no_residue(admin):
    _wipe()
    db = _db()
    assert db.period_unlock_requests.count_documents(
        {"entity_id": ENTITY, "period_key": PKEY}) == 0
    assert db.journal_entries.count_documents(
        {"entity_id": ENTITY, "date": {"$regex": "^2019-06"}}) == 0
    assert db.period_closings.count_documents(
        {"entity_id": ENTITY, "period_key": PKEY}) == 0
    rc, _ = _run_gate()
    assert rc == 0
    print("✅ 11 tidak ada residu · gate tetap hijau")
