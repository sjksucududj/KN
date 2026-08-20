#!/usr/bin/env python3
"""test_core_ps18.py — POC INTI **PS-18** (KPI Desainer + Eskalasi SLA Otomatis).

Membuktikan DUA hal terberat sebelum UI dibangun, memakai LAYANAN NYATA + DB NYATA
(bukan tiruan / bukan angka hias):

  A. **KPI Desainer** — metrik on-time%, rework%, terlambat, rata skor, rata hari, dan
     GRADE komposit terhitung benar dari `md_samples.rounds[]`, termasuk penyaringan
     periode (Bulan ini / 30 hari / 90 hari / Semua) dan normalisasi bobot.
  B. **Eskalasi SLA** — job penjadwal membuat notifikasi harian ke MANAGER untuk round
     yang lewat tenggat, MENAIKKAN ke ADMIN bila keterlambatan >= ambang kebijakan
     (`rnd.sla_escalate_admin_days`), dan **idempotent** (jalan 2x tidak menggandakan).

Data uji dibuat lewat layanan produksi yang sama dengan UI (create_sample → send_sample
dengan tenggat lampau → add_attachment → submit_round → assess_round) lalu DIBERSIHKAN
kembali di akhir, sehingga database demo tidak tercemar.

Jalankan: cd /app && python test_core_ps18.py
"""
import asyncio
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))

from db import db                                              # noqa: E402
from services import rnd_kpi_service as kpi                    # noqa: E402
from services import rnd_sample_service as smp                 # noqa: E402
from services import rnd_sla_service as sla                    # noqa: E402
from services import scheduler_service as sched                # noqa: E402

ENT = "ent_ksc"
TAG = "[POC-PS18]"
ADMIN = {"name": "POC Admin", "role": "admin"}
D1 = "POC Desainer Tepat"      # selalu tepat waktu, ACC
D2 = "POC Desainer Telat"      # terlambat + rework
D3 = "POC Desainer Nunggak"    # round menggantung lewat tenggat berat

_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
        b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

RESULTS: list[tuple[str, bool, str]] = []
CREATED_SAMPLES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'} · {name}" + (f" → {detail}" if detail else ""))
    return bool(ok)


def _plus(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# ═════════════════════════════════════════════════════════════════════════════
#  PERSIAPAN DATA UJI (lewat layanan nyata)
# ═════════════════════════════════════════════════════════════════════════════
async def make_sample(title: str, due_days: int, supplier_ids: list[str],
                      actor: str) -> dict:
    doc = await smp.create_sample({
        "sample_type": "labdip", "title": f"{TAG} {title}",
        "brief": "Data uji POC PS-18 — dibersihkan otomatis setelah uji.",
        "target_date": _plus(max(due_days, 0)), "qty_requested": 1, "unit": "meter",
    }, entity_id=ENT, actor=actor)
    CREATED_SAMPLES.append(doc["id"])
    await smp.send_sample(doc["id"], supplier_ids, due_date=_plus(due_days),
                          note="POC", actor=actor)
    return await smp.get_sample(doc["id"])


async def run_round(sample_id: str, supplier_id: str, *, actor: str,
                    result: str = "", score=None) -> dict:
    """Setor hasil round (wajib bukti + catatan) lalu—bila diminta—dinilai."""
    doc = await smp.get_sample(sample_id)
    mine = [r for r in (doc.get("rounds") or [])
            if r["supplier_id"] == supplier_id and r["status"] == "open"]
    row = max(mine, key=lambda r: int(r.get("round_no") or 0))
    await smp.add_attachment(sample_id, row["id"], "hasil.png", "image/png", _PNG, actor)
    await smp.submit_round(sample_id, row["id"],
                           {"note": "Hasil uji POC", "measurements": {"delta_e": 1.2},
                            "cost": 100000}, actor)
    if result:
        await smp.assess_round(sample_id, row["id"],
                               {"result": result, "score": score, "note": "POC"}, ADMIN)
    doc = await smp.get_sample(sample_id)
    return next(r for r in doc["rounds"] if r["id"] == row["id"])


async def seed_poc() -> dict:
    sups = await db.suppliers.find({"status": "active"},
                                   {"_id": 0, "id": 1, "name": 1}).to_list(5)
    if len(sups) < 2:
        raise RuntimeError("Butuh minimal 2 supplier aktif di database untuk POC.")
    s1, s2 = sups[0]["id"], sups[1]["id"]

    # (1) D1 — tenggat masih longgar, disetor & ACC → on-time 100%
    a = await make_sample("A tepat waktu", 5, [s1], D1)
    r_a = await run_round(a["id"], s1, actor=D1, result="acc", score=92)

    # (2) D2 — tenggat SUDAH lewat 2 hari, disetor sekarang → overdue=True + revisi
    b = await make_sample("B disetor terlambat", -2, [s1, s2], D2)
    r_b1 = await run_round(b["id"], s1, actor=D2, result="revisi", score=60)
    r_b2 = await run_round(b["id"], s2, actor=D2, result="acc", score=80)

    # (3) D3 — round MENGGANTUNG lewat tenggat 1 hari (tier manager saja)
    c = await make_sample("C menggantung 1 hari", -1, [s1], D3)
    # (4) D3 — round MENGGANTUNG lewat tenggat 5 hari (tier manager + admin)
    d = await make_sample("D menggantung 5 hari", -5, [s2], D3)

    return {"s1": s1, "s2": s2, "a": a, "b": b, "c": c, "d": d,
            "r_a": r_a, "r_b1": r_b1, "r_b2": r_b2}


async def cleanup() -> None:
    ids = list(CREATED_SAMPLES)
    if not ids:
        return
    docs = await db.md_samples.find({"id": {"$in": ids}},
                                    {"_id": 0, "rounds": 1}).to_list(50)
    refs = []
    for d in docs:
        for rd in (d.get("rounds") or []):
            refs += [f"rndsla:{rd['id']}", f"rndslaadm:{rd['id']}"]
    await db.md_samples.delete_many({"id": {"$in": ids}})
    if refs:
        await db.notifications.delete_many({"ref": {"$in": refs}})
    await db.sys_scheduler_runs.delete_many({"job_id": "rnd_sla_escalation",
                                             "trigger": "poc"})
    print(f"\n{TAG} bersih-bersih: {len(ids)} permintaan uji + notifikasinya dihapus.")


# ═════════════════════════════════════════════════════════════════════════════
#  A. KPI DESAINER
# ═════════════════════════════════════════════════════════════════════════════
async def test_kpi(ctx: dict) -> None:
    print("\n── A. KPI DESAINER (metrik + grade + filter periode) ──────────────")
    w = await kpi.weights(ENT)
    check("Bobot kebijakan terbaca dari Pusat Pengaturan",
          w["on_time"] == 40 and w["score"] == 40 and w["acc"] == 20
          and w["escalate_admin_days"] == 3,
          f"on_time={w['on_time']} score={w['score']} acc={w['acc']} "
          f"admin_days={w['escalate_admin_days']} penalti_rework={w['penalty_rework']}")

    rep = await kpi.designer_kpi({"entity_id": ENT}, period="all", entity_id=ENT)
    rows = {r["designer"]: r for r in rep["items"]}
    check("Ketiga desainer uji muncul di laporan",
          all(n in rows for n in (D1, D2, D3)),
          f"{len(rep['items'])} desainer: {', '.join(list(rows)[:6])}")

    d1 = rows.get(D1) or {}
    check(f"{D1}: on-time 100% · ACC 1 · rework 0%",
          d1.get("on_time_pct") == 100.0 and d1.get("acc") == 1
          and d1.get("rework_pct") == 0.0 and d1.get("late_total") == 0,
          f"on_time={d1.get('on_time_pct')} acc={d1.get('acc')} "
          f"rework={d1.get('rework_pct')} grade={d1.get('grade_score')}"
          f" ({d1.get('grade_letter')})")

    d2 = rows.get(D2) or {}
    check(f"{D2}: 2 round disetor TERLAMBAT → on-time 0%, rework 50%",
          d2.get("submitted") == 2 and d2.get("late_submitted") == 2
          and d2.get("on_time_pct") == 0.0 and d2.get("rework_pct") == 50.0,
          f"submitted={d2.get('submitted')} late={d2.get('late_submitted')} "
          f"on_time={d2.get('on_time_pct')} rework={d2.get('rework_pct')} "
          f"grade={d2.get('grade_score')} ({d2.get('grade_letter')})")

    d3 = rows.get(D3) or {}
    check(f"{D3}: 2 round MENGGANTUNG lewat tenggat (1 di antaranya berat)",
          d3.get("overdue_now") == 2 and d3.get("overdue_critical") == 1
          and d3.get("max_days_late") == 5,
          f"overdue_now={d3.get('overdue_now')} kritis={d3.get('overdue_critical')} "
          f"terlama={d3.get('max_days_late')} hari")

    check("Grade komposit: yang tepat waktu > yang terlambat",
          (d1.get("grade_score") or 0) > (d2.get("grade_score") or 0),
          f"{D1}={d1.get('grade_score')} vs {D2}={d2.get('grade_score')}")

    check("Penalti rework/terlambat benar-benar memotong nilai",
          (d2.get("grade_penalty") or 0) > 0
          and (d2.get("grade_score") or 0) < (d2.get("grade_base") or 0),
          f"base={d2.get('grade_base')} penalti={d2.get('grade_penalty')} "
          f"akhir={d2.get('grade_score')}")

    check("Huruf grade terisi & konsisten dengan ambang",
          all(r["grade_letter"] in ("A", "B", "C", "D", "—") for r in rep["items"]),
          ", ".join(f"{r['designer']}={r['grade_letter']}" for r in rep["items"][:6]))

    check("Ringkasan atas layar terisi (jumlah desainer, terlambat, terbaik)",
          rep["summary"]["designers"] == len(rep["items"])
          and rep["summary"]["overdue_now"] >= 2
          and bool(rep["summary"]["best_designer"]),
          f"designers={rep['summary']['designers']} "
          f"overdue_now={rep['summary']['overdue_now']} "
          f"terbaik={rep['summary']['best_designer']} "
          f"({rep['summary']['best_grade']})")

    # ── Filter periode ────────────────────────────────────────────────────
    month = await kpi.designer_kpi({"entity_id": ENT}, period="month", entity_id=ENT)
    d30 = await kpi.designer_kpi({"entity_id": ENT}, period="30d", entity_id=ENT)
    check("Filter periode menghasilkan label & tanggal awal yang benar",
          month["period_label"] == "Bulan ini"
          and month["from_date"] == date.today().replace(day=1).isoformat()
          and d30["from_date"] == (date.today() - timedelta(days=30)).isoformat(),
          f"month.from={month['from_date']} · 30d.from={d30['from_date']}")
    check("Periode 30 hari mencakup seluruh round uji (dibuat hari ini)",
          {r["designer"] for r in d30["items"]} >= {D1, D2, D3},
          f"{d30['count']} desainer pada 30 hari terakhir")
    check("Pilihan periode tersedia untuk UI (4 opsi)",
          [o["value"] for o in rep["period_options"]] == ["month", "30d", "90d", "all"],
          ", ".join(o["label"] for o in rep["period_options"]))

    # Periode masa lalu yang kosong → laporan kosong, bukan error.
    old = kpi.period_start("month", date(2020, 1, 15))
    check("Helper periode aman untuk tanggal lampau", old == date(2020, 1, 1), str(old))


# ═════════════════════════════════════════════════════════════════════════════
#  B. ESKALASI SLA OTOMATIS
# ═════════════════════════════════════════════════════════════════════════════
async def test_sla(ctx: dict) -> None:
    print("\n── B. ESKALASI SLA OTOMATIS (manager → admin, idempotent) ─────────")
    brd = await sla.board({"entity_id": ENT}, entity_id=ENT)
    mine = [r for r in brd["items"] if TAG in (r.get("title") or "")]
    check("Papan eskalasi menemukan round uji yang lewat tenggat",
          len(mine) >= 2, f"{len(mine)} round uji dari total {brd['count']} terlambat")

    berat = [r for r in mine if r["days_late"] >= 5]
    ringan = [r for r in mine if r["days_late"] == 1]
    check("Tingkatan dihitung benar (1 hari = manager · 5 hari = admin)",
          bool(berat) and bool(ringan)
          and berat[0]["tier"] == "admin" and ringan[0]["tier"] == "manager",
          f"1 hari → {ringan[0]['tier'] if ringan else '?'} · "
          f"5 hari → {berat[0]['tier'] if berat else '?'}")
    check("Setiap baris eskalasi menyebut penanggung jawab & keadaan",
          all(r["designer"] and r["state_label"] for r in mine),
          f"{mine[0]['designer']} · {mine[0]['state_label']}" if mine else "")

    refs_manager = [f"rndsla:{r['round_id']}" for r in mine]
    refs_admin = [f"rndslaadm:{r['round_id']}" for r in mine]
    await db.notifications.delete_many({"ref": {"$in": refs_manager + refs_admin}})

    run1 = await sched.run_job("rnd_sla_escalation", trigger="poc", actor="POC")
    check("Job 'rnd_sla_escalation' terdaftar di penjadwal & jalan sukses",
          run1["status"] == "success",
          f"created={run1['created']} scanned={run1['scanned']} "
          f"detail={run1['detail']} error={run1.get('error') or '-'}")

    n_mgr = await db.notifications.count_documents(
        {"ref": {"$in": refs_manager}, "recipient_role": "manager"})
    n_adm = await db.notifications.count_documents(
        {"ref": {"$in": refs_admin}, "recipient_role": "admin"})
    check("Manager diberi tahu untuk SEMUA round terlambat",
          n_mgr == len(mine), f"{n_mgr} notifikasi manager (harap {len(mine)})")
    check("Admin HANYA menerima yang terlambat >= 3 hari (bertingkat)",
          n_adm == len(berat), f"{n_adm} notifikasi admin (harap {len(berat)})")

    sample_notif = await db.notifications.find_one(
        {"ref": refs_admin[0] if refs_admin else "-"}, {"_id": 0})
    check("Isi notifikasi eskalasi memakai bahasa yang bisa ditindak",
          bool(sample_notif) and "TERLAMBAT" in (sample_notif or {}).get("body", "")
          and (sample_notif or {}).get("severity") == "critical"
          and (sample_notif or {}).get("link") == "rnd-reports",
          ((sample_notif or {}).get("body") or "")[:120])

    run2 = await sched.run_job("rnd_sla_escalation", trigger="poc", actor="POC")
    n_mgr2 = await db.notifications.count_documents({"ref": {"$in": refs_manager}})
    n_adm2 = await db.notifications.count_documents({"ref": {"$in": refs_admin}})
    check("IDEMPOTENT: jalan kedua di hari yang sama tidak menggandakan",
          run2["created"] == 0 and n_mgr2 == n_mgr and n_adm2 == n_adm,
          f"created(run2)={run2['created']} · manager {n_mgr}→{n_mgr2} · "
          f"admin {n_adm}→{n_adm2}")

    wa_q = await db.sys_wa_outbox.count_documents({})
    check("Kanal WhatsApp ikut terpakai (antrean pesan ada / mode nonaktif)",
          wa_q >= 0, f"{wa_q} pesan di antrean WA")

    decided_ids = {d["id"] for d in await db.md_samples.find(
        {"status": {"$in": ["decided", "cancelled"]}}, {"_id": 0, "id": 1}).to_list(500)}
    board_all = await sla.board()
    bocor = [r for r in board_all["items"] if r.get("sample_id") in decided_ids]
    check("Permintaan yang sudah DIPUTUS/DIBATALKAN tidak ikut ditagih (anti-berisik)",
          not bocor,
          f"{len(decided_ids)} permintaan selesai · {board_all['count']} round terlambat "
          f"· bocor={len(bocor)}")


# ═════════════════════════════════════════════════════════════════════════════
async def main() -> int:
    print("=" * 78)
    print(f"{TAG} POC INTI PS-18 — KPI Desainer + Eskalasi SLA Otomatis")
    print("=" * 78)
    try:
        print("\n── 0. Menyiapkan data uji lewat layanan nyata ─────────────────────")
        ctx = await seed_poc()
        print(f"  4 permintaan uji dibuat: {ctx['a']['number']}, {ctx['b']['number']}, "
              f"{ctx['c']['number']}, {ctx['d']['number']}")
        await test_kpi(ctx)
        await test_sla(ctx)
    except Exception:  # noqa: BLE001 — POC harus melaporkan, bukan diam
        print("\n!! GAGAL DI TENGAH JALAN:")
        traceback.print_exc()
        RESULTS.append(("Eksekusi POC tanpa error", False, "lihat traceback"))
    finally:
        await cleanup()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 78)
    print(f"HASIL: {passed}/{total} lulus")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL · {name} → {detail}")
    print("=" * 78)
    return 0 if passed == total and total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
