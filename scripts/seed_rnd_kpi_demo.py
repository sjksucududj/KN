#!/usr/bin/env python3
"""seed_rnd_kpi_demo.py — Data demo **KPI DESAINER & ESKALASI SLA** (PS-18).

MENGAPA SCRIPT INI ADA
----------------------
Data demo R&D bawaan hanya berisi 2 permintaan dengan SATU pelaksana dan TANPA
keterlambatan. Akibatnya dua fitur PS-18 tidak terlihat sama sekali saat pertama dibuka:
laporan KPI hanya punya satu baris, dan papan eskalasi selalu kosong.

YANG DIBUAT (semuanya lewat LAYANAN NYATA — nomor dokumen, validasi bukti, hitungan
SLA & status mengikuti jalur yang sama dengan UI; tidak ada insert mentah):
  * **Rina Kartika** — 3 round disetor TEPAT WAKTU (2 ACC, 1 revisi → dibuka round 2 lalu
    ACC) + 1 round masih menggantung **terlambat 1 hari** (tingkat: manager).
  * **Bagas Nugroho** — 2 round disetor **TERLAMBAT** (1 tolak, 1 revisi) + 1 round masih
    menggantung **terlambat 4 hari** (tingkat: manager **dan** admin).
Dengan begitu semua kolom KPI terisi nyata: on-time%, rework%, tolak, terlambat, dan
grade komposit berbeda antar desainer.

CATATAN JUJUR: seperti `seed_realistic.py` yang menggeser tanggal order/PO agar demo
realistis, `sent_at` tiap round demo digeser ke masa lalu (tenggat − target SLA) supaya
kolom "rata hari" tidak nol. Isi/bukti/penilaian TIDAK dipalsukan.

Idempotent: permintaan demo ditandai `demo_batch = "rnd_kpi_v1"`; bila sudah ada,
script berhenti tanpa membuat apa pun.

Jalankan: cd /app && python scripts/seed_rnd_kpi_demo.py
Dipakai juga oleh `seed_realistic.py::seed_rnd()` supaya seed baru langsung kaya.
"""
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from db import db                                        # noqa: E402
from services import rnd_gate                            # noqa: E402
from services import rnd_sample_service as smp           # noqa: E402

BATCH = "rnd_kpi_v1"
# Penanda terpisah untuk sample yang dikerjakan AKUN LOGIN (dipakai kartu "KPI Saya"
# di Profil Saya). Dipisah agar bisa ditambahkan ke database yang sudah punya batch v1.
BATCH_ME = "rnd_kpi_me_v1"
ENT = "ent_ksc"
MANAGER = {"name": "Dewi Rahayu", "role": "manager"}
ADMIN = {"name": "Budi Santoso", "role": "admin"}
RINA = "Rina Kartika"
BAGAS = "Bagas Nugroho"
# Manajer MD di perusahaan kecil sering ikut menangani labdip sendiri — dan dialah
# satu-satunya desainer demo yang PUNYA AKUN LOGIN, sehingga kartu "KPI Saya" bisa
# benar-benar dilihat. Penilaiannya tetap dilakukan ADMIN (bukan menilai diri sendiri).
ME = MANAGER["name"]

_PNG_1PX = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
            b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
            b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


async def _mark(sample_id: str, batch: str = BATCH) -> None:
    await db.md_samples.update_one({"id": sample_id}, {"$set": {"demo_batch": batch}})


async def _shift_sent_at(sample_id: str, sla_days: int) -> None:
    """Geser `sent_at` tiap round ke (tenggat − target SLA) agar 'rata hari' realistis."""
    doc = await db.md_samples.find_one({"id": sample_id}, {"_id": 0, "rounds": 1})
    for rd in (doc or {}).get("rounds") or []:
        due = str(rd.get("due_date") or "")[:10]
        if not due:
            continue
        try:
            base = date.fromisoformat(due) - timedelta(days=max(sla_days, 1))
        except ValueError:
            continue
        sent = datetime(base.year, base.month, base.day, 9, 0, tzinfo=timezone.utc)
        await db.md_samples.update_one(
            {"id": sample_id, "rounds.id": rd["id"]},
            {"$set": {"rounds.$.sent_at": sent.isoformat()}})


async def _create(title: str, *, actor: str, due_offset: int, supplier_ids: list,
                  sample_type: str = "labdip", brief: str = "", design_id: str = "",
                  qty: float = 3, unit: str = "meter", sla_days: int = 7,
                  batch: str = BATCH) -> dict:
    payload = {
        "sample_type": sample_type, "title": title,
        "brief": brief or "Data demo PS-18 — dipakai memperagakan KPI desainer & SLA.",
        "target_date": _day(max(due_offset, 1)), "qty_requested": qty, "unit": unit,
    }
    if design_id:
        payload["design_id"] = design_id
    doc = await smp.create_sample(payload, entity_id=ENT, actor=actor)
    await _mark(doc["id"], batch)
    await smp.send_sample(doc["id"], supplier_ids, due_date=_day(due_offset),
                          note="Mohon kirim hasil beserta bukti ukur", actor=actor)
    await _shift_sent_at(doc["id"], sla_days)
    return await smp.get_sample(doc["id"])


async def _round(sample_id: str, supplier_id: str, *, actor: str, note: str,
                 meas: dict, cost: float, result: str = "", score=None,
                 assess_note: str = "", assessor: dict = None) -> dict:
    """Satu siklus round: unggah bukti → setor hasil → (opsional) dinilai penilai.

    `assessor` bisa dibedakan dari `actor` supaya tidak ada yang menilai hasil kerjanya
    sendiri (dipakai pada sample milik akun manajer).
    """
    doc = await smp.get_sample(sample_id)
    mine = [r for r in (doc.get("rounds") or [])
            if r["supplier_id"] == supplier_id and r["status"] == "open"]
    if not mine:
        raise RuntimeError(f"Tidak ada round terbuka untuk supplier {supplier_id}")
    row = max(mine, key=lambda r: int(r.get("round_no") or 0))
    await smp.add_attachment(sample_id, row["id"], "hasil_sample.png", "image/png",
                             _PNG_1PX, actor)
    await smp.submit_round(sample_id, row["id"],
                           {"note": note, "measurements": meas, "cost": cost}, actor)
    if result:
        await smp.assess_round(sample_id, row["id"],
                               {"result": result, "score": score, "note": assess_note},
                               assessor or MANAGER)
    return row


async def _realism_pass(verbose: bool = True) -> int:
    """Buat kolom "rata hari" bermakna untuk round demo LAMA.

    Round pada seed bawaan disetor pada detik yang sama dengan saat dikirim, sehingga
    "rata hari" selalu 0,0 — terlihat seperti kerusakan padahal hanya artefak seed.
    Di sini `sent_at` round demo lama digeser ke (tenggat − target SLA), persis
    perlakuan `seed_realistic.py` yang menggeser tanggal order/PO. Hanya round yang
    tanggal kirim & tanggal setornya SAMA yang disentuh (idempotent).
    """
    touched = 0
    async for s in db.md_samples.find({}, {"_id": 0, "id": 1, "rounds": 1}):
        for rd in (s.get("rounds") or []):
            sent = str(rd.get("sent_at") or "")[:10]
            recv = str(rd.get("received_at") or "")[:10]
            due = str(rd.get("due_date") or "")[:10]
            if not (sent and recv and due) or sent != recv:
                continue
            try:
                base = date.fromisoformat(due) - timedelta(days=7)
                recv_d = date.fromisoformat(recv)
            except ValueError:
                continue
            if base >= recv_d:
                base = recv_d - timedelta(days=3)
            shifted = datetime(base.year, base.month, base.day, 9, 0, tzinfo=timezone.utc)
            await db.md_samples.update_one(
                {"id": s["id"], "rounds.id": rd["id"]},
                {"$set": {"rounds.$.sent_at": shifted.isoformat()}})
            touched += 1
    if touched and verbose:
        print(f"   · {touched} round demo lama digeser tanggal kirimnya "
              "(agar 'rata hari' tidak nol)")
    return touched


async def _suppliers() -> list:
    return await db.suppliers.find({"status": "active"},
                                   {"_id": 0, "id": 1, "name": 1}).to_list(10)


async def seed_me(verbose: bool = True) -> int:
    """Sample yang dikerjakan AKUN LOGIN (manajer MD) — supaya kartu "KPI Saya" berisi.

    Tanpa ini, semua desainer demo hanyalah NAMA pada jejak round (tidak punya akun),
    sehingga fitur "KPI Saya" di Profil Saya tidak akan pernah bisa diperagakan.
    Penilaian dilakukan ADMIN — tidak ada yang menilai hasil kerjanya sendiri.
    """
    def say(msg: str) -> None:
        if verbose:
            print(msg)

    if await db.md_samples.count_documents({"demo_batch": BATCH_ME}) > 0:
        say('ℹ️  data demo "KPI Saya" sudah ada — dilewati (idempotent)')
        return 0
    sups = await _suppliers()
    if len(sups) < 2:
        say('  [warn] supplier < 2 — seed "KPI Saya" dilewati')
        return 0
    s1, s2 = sups[0], sups[1]
    pol = await rnd_gate.policy(ENT)
    sla = int(pol.get("round_sla_days") or 7)

    a = await _create("Labdip Katun Twill 240 gsm — merah maroon", actor=ME,
                      due_offset=3, supplier_ids=[s1["id"], s2["id"]], sla_days=sla,
                      batch=BATCH_ME,
                      brief="Merah maroon untuk seragam korporat; wajib tahan cuci 4.")
    await _round(a["id"], s1["id"], actor=ME,
                 note="Warna tepat, kain padat, tahan cuci baik.",
                 meas={"delta_e": 0.8, "gsm_actual": 241, "shrinkage_pct": 1,
                       "colorfastness_wash": 4, "colorfastness_rub": 4},
                 cost=190000, result="acc", score=91, assessor=ADMIN,
                 assess_note="ΔE 0.8 — terbaik di antara peserta, tepat waktu.")
    await _round(a["id"], s2["id"], actor=ME,
                 note="Warna sedikit kusam, perlu perbaikan pencelupan.",
                 meas={"delta_e": 2.2, "gsm_actual": 238, "shrinkage_pct": 2,
                       "colorfastness_wash": 3, "colorfastness_rub": 3},
                 cost=165000, result="revisi", score=72, assessor=ADMIN,
                 assess_note="Minta perbaikan kecerahan warna.")

    b = await _create("Labdip Katun Twill 240 gsm — biru dongker", actor=ME,
                      due_offset=-2, supplier_ids=[s2["id"]], sla_days=sla,
                      batch=BATCH_ME,
                      brief="Varian biru dongker dari kesepakatan maroon.")
    say(f"   · {a['number']} + {b['number']} ({ME}) — 2 round dinilai admin + "
        "1 round menggantung 2 hari → kartu 'KPI Saya' terisi")
    return 2


async def seed(verbose: bool = True) -> int:
    """Buat data demo KPI/SLA. Return jumlah permintaan sample yang dibuat (0 = dilewati)."""
    def say(msg: str) -> None:
        if verbose:
            print(msg)

    if await db.md_samples.count_documents({"demo_batch": BATCH}) > 0:
        say("ℹ️  data demo KPI desainer sudah ada — dilewati (idempotent)")
        made_me = await seed_me(verbose)
        await _realism_pass(verbose)
        return made_me

    sups = await _suppliers()
    if len(sups) < 2:
        say("  [warn] butuh minimal 2 supplier aktif — seed KPI desainer dilewati")
        return 0
    s1, s2 = sups[0], sups[1]
    s3 = sups[2] if len(sups) > 2 else s2

    pol = await rnd_gate.policy(ENT)
    sla = int(pol.get("round_sla_days") or 7)
    design = await db.design_gallery.find_one({"status": "approved"},
                                              {"_id": 0, "id": 1, "code": 1})
    made = 0

    # ── 1. Rina Kartika — kerja rapi & tepat waktu (2 ACC + 1 revisi → ACC) ────
    a = await _create("Labdip Katun Slub 200 gsm — biru indigo", actor=RINA,
                      due_offset=4, supplier_ids=[s1["id"], s2["id"]], sla_days=sla,
                      brief="Cocokkan biru indigo ΔE ≤ 1.5, kirim swatch 3 meter.")
    made += 1
    await _round(a["id"], s1["id"], actor=RINA,
                 note="Warna presisi, handfeel sesuai contoh acuan.",
                 meas={"delta_e": 1.1, "gsm_actual": 201, "shrinkage_pct": 2,
                       "colorfastness_wash": 4, "colorfastness_rub": 4},
                 cost=175000, result="acc", score=88,
                 assess_note="ΔE 1.1 — memenuhi target, tepat waktu.")
    await _round(a["id"], s2["id"], actor=RINA,
                 note="Warna terlalu gelap satu tingkat, gramasi kurang.",
                 meas={"delta_e": 2.8, "gsm_actual": 193, "shrinkage_pct": 3,
                       "colorfastness_wash": 3, "colorfastness_rub": 3},
                 cost=150000, result="revisi", score=62,
                 assess_note="Minta perbaikan warna & gramasi.")
    await smp.open_round(a["id"], s2["id"], note="Perbaikan warna & gramasi",
                        actor=MANAGER)
    await _shift_sent_at(a["id"], sla)
    await _round(a["id"], s2["id"], actor=RINA,
                 note="Perbaikan diterima, warna & gramasi sudah mendekati target.",
                 meas={"delta_e": 1.4, "gsm_actual": 199, "shrinkage_pct": 2,
                       "colorfastness_wash": 4, "colorfastness_rub": 4},
                 cost=150000, result="acc", score=84,
                 assess_note="Layak jadi supplier cadangan.")
    say(f"   · {a['number']} ({RINA}) — 3 round tepat waktu: 2 ACC, 1 revisi")

    # ── 2. Rina Kartika — 1 round MENGGANTUNG terlambat 1 hari (tingkat manager) ─
    b = await _create("Labdip Katun Combed 120 gsm — hijau sage", actor=RINA,
                      due_offset=-1, supplier_ids=[s3["id"]], sla_days=sla,
                      brief="Hijau sage lembut untuk koleksi seragam kantor.")
    made += 1
    say(f"   · {b['number']} ({RINA}) — round menggantung TERLAMBAT 1 hari "
        "(eskalasi ke manager)")

    # ── 3. Bagas Nugroho — 2 round disetor TERLAMBAT (1 tolak, 1 revisi) ───────
    stype = "proofing" if design else "labdip"
    c = await _create("Proofing Rayon Motif Kawung Klasik" if design
                      else "Labdip Rayon Motif Kawung Klasik", actor=BAGAS,
                      due_offset=-3, supplier_ids=[s1["id"], s2["id"]],
                      sample_type=stype, design_id=(design or {}).get("id", ""),
                      qty=2, unit="yard", sla_days=sla,
                      brief="Cetak sesuai artwork; periksa repeat & ketajaman garis.")
    made += 1
    await _round(c["id"], s1["id"], actor=BAGAS,
                 note="Hasil cetak buram, garis motif pecah di beberapa bagian.",
                 meas={"delta_e": 4.2, "repeat_cm": 33, "colorfastness_wash": 2,
                       "colorfastness_rub": 2},
                 cost=210000, result="tolak", score=41,
                 assess_note="Ketajaman jauh di bawah standar — tidak dilanjutkan.")
    await _round(c["id"], s2["id"], actor=BAGAS,
                 note="Repeat sudah benar, warna masih perlu diturunkan sedikit.",
                 meas={"delta_e": 2.6, "repeat_cm": 32, "colorfastness_wash": 3,
                       "colorfastness_rub": 3},
                 cost=195000, result="revisi", score=66,
                 assess_note="Terlambat 3 hari dan warna belum pas — minta perbaikan.")
    say(f"   · {c['number']} ({BAGAS}) — 2 round disetor TERLAMBAT: 1 tolak, 1 revisi")

    # ── 4. Bagas Nugroho — round MENGGANTUNG terlambat 4 hari (naik ke admin) ──
    d = await _create("Labdip Linen Blend 180 gsm — abu asap", actor=BAGAS,
                      due_offset=-4, supplier_ids=[s2["id"]], sla_days=sla,
                      brief="Abu asap untuk koleksi formal; uji tahan gosok wajib.")
    made += 1
    say(f"   · {d['number']} ({BAGAS}) — round menggantung TERLAMBAT 4 hari "
        "(eskalasi manager + admin)")

    say(f"OK Data demo KPI desainer & eskalasi SLA: {made} permintaan · 2 desainer baru "
        "· 5 round dinilai · 2 round terlambat menggantung")
    made += await seed_me(verbose)
    await _realism_pass(verbose)
    await seed_trend_history(verbose)
    await seed_division_assignments(verbose)
    return made


# ─── PS-17 — Penempatan divisi default untuk orang R&D (idempotent, upsert) ─────
async def seed_division_assignments(verbose: bool = True) -> int:
    """Tetapkan divisi awal agar layar 'Divisi & Persetujuan' + filter KPI ada isinya."""
    from core_utils import now_iso  # noqa: PLC0415
    assignments = {
        "Rina Kartika": "designer",
        "Dewi Lestari": "designer",
        "Dewi Rahayu": "sample",
        "Bagas Nugroho": "rnd",
        "Ayu Permatasari": "admin_sales",
    }
    n = 0
    for name, div in assignments.items():
        await db.rnd_person_divisions.update_one(
            {"entity_id": ENT, "name": name},
            {"$set": {"entity_id": ENT, "name": name, "division": div,
                      "updated_at": now_iso(), "updated_by": "seed"}}, upsert=True)
        await db.users.update_one({"name": name}, {"$set": {"division": div}})
        n += 1
    if verbose:
        print(f"OK Divisi R&D (PS-17): {n} orang ditempatkan ke divisi")
    return n


# ─── Riwayat bulanan untuk grafik TREN NILAI DESAINER (PS-18 lanjutan) ──────────
TREND_BATCH = "designer_trend_v1"


async def seed_trend_history(verbose: bool = True) -> int:
    """Sisipkan round DECIDED historis (5 bulan ke belakang) agar grafik *Tren Nilai
    Desainer per bulan* punya bentuk nyata. Idempotent lewat `demo_batch`.

    Semua sample historis berstatus `decided` (tertutup) dan ber-tanggal > 30 hari,
    jadi TIDAK memengaruhi tabel KPI default (periode 30 hari) maupun papan eskalasi
    (yang hanya melihat round berjalan). Ia hanya memberi titik-titik bulan lampau
    pada grafik tren.
    """
    from core_utils import new_id, now_iso  # noqa: PLC0415

    # Bersihkan batch lama → idempotent (aman re-run).
    await db.md_samples.delete_many({"demo_batch": TREND_BATCH})

    # (result, on_time, score) per bulan (paling lama → paling baru), 2 round/bulan.
    # Semua ACC & tepat waktu supaya garis tren HALUS (naik perlahan) dan tiap desainer
    # punya "pita" nilai yang khas — bukan lonjakan akibat satu revisi pada sampel kecil.
    plans = {
        "Rina Kartika":  [(("acc", True, 80), ("acc", True, 78)),
                          (("acc", True, 82), ("acc", True, 80)),
                          (("acc", True, 84), ("acc", True, 82)),
                          (("acc", True, 86), ("acc", True, 84)),
                          (("acc", True, 88), ("acc", True, 86))],
        "Dewi Lestari":  [(("acc", True, 74), ("acc", True, 70)),
                          (("acc", True, 76), ("acc", True, 72)),
                          (("acc", True, 78), ("acc", True, 74)),
                          (("acc", True, 80), ("acc", True, 77)),
                          (("acc", True, 82), ("acc", True, 79))],
        "Dewi Rahayu":   [(("acc", True, 64), ("acc", True, 60)),
                          (("acc", True, 66), ("acc", True, 62)),
                          (("acc", True, 68), ("acc", True, 64)),
                          (("acc", True, 70), ("acc", True, 66)),
                          (("acc", True, 72), ("acc", True, 68))],
        "Bagas Nugroho": [(("acc", True, 55), ("acc", True, 50)),
                          (("acc", True, 58), ("acc", True, 54)),
                          (("acc", True, 62), ("acc", True, 58)),
                          (("acc", True, 65), ("acc", True, 60)),
                          (("acc", True, 68), ("acc", True, 63))],
    }

    today = date.today()

    def month_anchor(back: int) -> date:
        y, m = today.year, today.month
        for _ in range(back):
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        # hari ke-15 bulan itu (aman untuk semua bulan)
        return date(y, m, 15)

    docs = []
    for designer, months in plans.items():
        # months[0] = paling lama (5 bulan lalu) … months[-1] = 1 bulan lalu
        n = len(months)
        for idx, rounds_spec in enumerate(months):
            back = n - idx            # 5,4,3,2,1 bulan ke belakang
            anchor = month_anchor(back)
            sent = anchor - timedelta(days=6)
            due = sent + timedelta(days=7)
            rounds = []
            for rno, (result, on_time, score) in enumerate(rounds_spec, start=1):
                recv = due - timedelta(days=1) if on_time else due + timedelta(days=3)
                rounds.append({
                    "id": new_id("rnd"), "round_no": rno, "status": "assessed",
                    "performed_by": designer, "opened_by": designer,
                    "supplier_id": "", "supplier_name": "",
                    "sent_at": sent.isoformat(), "due_date": due.isoformat(),
                    "received_at": recv.isoformat(), "assessed_at": recv.isoformat(),
                    "assessed_by": ADMIN["name"], "overdue": (not on_time),
                    "result": result, "score": score, "cost": 150000,
                    # KEJUJURAN DATA (INV-RND-02): round historis ini TIDAK punya berkas
                    # bukti nyata di object storage, jadi kebijakan bukti ditandai TIDAK
                    # aktif saat penutupan — bukan dipalsukan dengan lampiran kosong.
                    "proof_required": False, "attachments": [],
                    "measurements": {}, "note": "Riwayat KPI (data demo, tanpa berkas bukti)",
                    "assess_note": "Dinilai untuk riwayat tren.",
                })
            sample_date = anchor.isoformat()
            docs.append({
                "id": new_id("smp"),
                "number": f"KSC/SMP-H{back}{designer[:2].upper()}",
                "title": f"Riwayat KPI {designer} — {anchor.strftime('%b %Y')}",
                "sample_type": "labdip", "status": "decided",
                "entity_id": ENT, "created_by": designer,
                "spec_id": "", "spec_number": "", "design_id": "",
                "qty_requested": 3, "unit": "meter",
                "brief": "Sample historis untuk grafik tren KPI (data demo).",
                "rounds": rounds,
                # INV-RND-01: keputusan wajib punya pemutus + alasan berlabel, dan
                # `supplier_id` harus cocok dengan round yang ACC (di sini internal → "").
                "decision": {"result": "won", "supplier_id": "", "supplier_name": "",
                             "reason_code": "mutu_terbaik",
                             "note": "Historis (demo)",
                             "decided_at": sample_date, "decided_by": ADMIN["name"]},
                "cost_total": sum(r["cost"] for r in rounds),
                "demo_batch": TREND_BATCH,
                "sent_at": sample_date,
                "created_at": sample_date, "updated_at": now_iso(),
            })

    if docs:
        await db.md_samples.insert_many(docs)
    if verbose:
        print(f"OK Riwayat tren KPI: {len(docs)} sample historis (5 bulan) untuk "
              f"{len(plans)} desainer → grafik tren punya bentuk")
    return len(docs)


async def main() -> int:
    made = await seed()
    from services import rnd_kpi_service as kpi
    rep = await kpi.designer_kpi({"entity_id": ENT}, period="all", entity_id=ENT)
    print("\n📋 KPI desainer sekarang:")
    for r in rep["items"]:
        print(f"  {r['rank']}. {r['designer']:<18} grade {r['grade_letter']} "
              f"({r['grade_score']}) · on-time {r['on_time_pct']}% · "
              f"rework {r['rework_pct']}% · terlambat {r['late_total']} · "
              f"rata hari {r['avg_days']}")
    mine = await kpi.my_kpi({"entity_id": ENT}, name=ME, period="all", entity_id=ENT)
    me = mine.get("me") or {}
    print(f"\n📋 'KPI Saya' untuk akun {ME}: "
          f"{('peringkat ' + str(mine['rank']) + '/' + str(mine['total_designers']) + ' · grade ' + str(me.get('grade_letter')) + ' (' + str(me.get('grade_score')) + ')') if me else 'belum punya round'}"
          f" · {len(mine.get('rounds') or [])} round · {len(mine.get('overdue') or [])} nunggak")
    return 0 if made >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
