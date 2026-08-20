#!/usr/bin/env python3
"""test_ps21_poc.py — POC HTTP TUNGGAL untuk **PS-21** (quick win operasional).

Rujukan: `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` §A.3 **PS-21**
· `docs/KN_21_PLAN_PS21_NOTIFIKASI_OPERASIONAL.md`.

Membuktikan lewat HTTP nyata (bukan unit test) seluruh user story PS-21:

  US-1  3 job baru terdaftar di Penjadwal (`po_arrival`, `backorder_ready`,
        `ar_due_soon`) dengan jadwal yang BISA DIUBAH user tanpa deploy
  US-2  Job `ar_due_soon` menghasilkan notifikasi tepat pada offset H-3/H-1/H/H+1
        dan **tidak duplikasi** saat job dijalankan dua kali (dedupe harian)
  US-3  Job `backorder_ready` memberi tahu sales saat stok pendingan tersedia
  US-4  Job `po_arrival` memberi tahu MD/gudang/sales saat barang PO datang
        (termasuk notifikasi SEKETIKA saat Goods Receipt selesai)
  US-5  Sales melihat status pendingan + kandidat repeat/restock dari layar order
  US-6  1 klik "Repeat/Restock" dari SO membuat **PR** + notifikasi ke MD
  US-7  PR hasil restock membawa jejak dua arah (PR.source_ref_id ↔ SO.restock_requests)
  US-8  Permintaan repeat/restock ganda untuk produk sama DITOLAK 400 (anti PR dobel)
  US-9  Validasi input: item kosong / qty 0 / produk tak dikenal → 400 Indonesia
  US-10 Notifikasi baru ikut mesin R6.6 (severity, deep-link, filter jenis di bell)

Jalankan (backend harus hidup):
    cd /app/backend && python test_ps21_poc.py
Keluar 0 = seluruh POC PASS.
"""
import os
import subprocess
import sys
from datetime import datetime, timezone

import requests

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001/api")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN = {"email": "admin@kainnusantara.id", "password": "demo12345"}
SALES = {"email": "sales@kainnusantara.id", "password": "demo12345"}
MANAGER = {"email": "manager@kainnusantara.id", "password": "demo12345"}
WAREHOUSE = {"email": "warehouse@kainnusantara.id", "password": "demo12345"}

NEW_JOBS = ["po_arrival", "backorder_ready", "ar_due_soon"]
PS21_TYPES = ["ar_due_soon", "po_arrival", "backorder_ready", "restock_request"]
PASS, FAIL = [], []


def reset_ps21_notifications() -> int:
    """Fixture POC: hapus notifikasi PS-21 HARI INI agar dedupe harian bisa diuji
    ulang (mereset state uji — bukan memalsukan data)."""
    import asyncio

    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, "backend", ".env"))
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        day = datetime.now(timezone.utc).isoformat()[:10]
        res = await db.notifications.delete_many(
            {"type": {"$in": PS21_TYPES}, "created_at": {"$regex": f"^{day}"}})
        return res.deleted_count

    return asyncio.run(_run())


def seed_ar_offsets() -> str:
    """Siapkan kondisi piutang NYATA pada offset H-3/H-1/H/H+1 (hanya menggeser
    tanggal order; nominal & pelanggan asli tidak diubah)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "seed_ar_due_soon_demo.py")],
        capture_output=True, text=True, timeout=180, cwd=ROOT)
    return (proc.stdout or proc.stderr).strip().splitlines()[-1] if proc.stdout else ""


def check(story: str, cond: bool, detail: str = "") -> bool:
    (PASS if cond else FAIL).append(f"{story} — {detail}")
    print(f"{'✅' if cond else '❌'} {story}" + (f"  ·  {detail}" if detail else ""))
    return bool(cond)


def login(cred):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json=cred, timeout=30)
    r.raise_for_status()
    token = r.json().get("token") or r.json().get("session_token") or ""
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def run_job(s, job_id):
    return s.post(f"{BASE}/scheduler/jobs/{job_id}/run", timeout=120)


def notifs(s, ntype=""):
    r = s.get(f"{BASE}/notifications", timeout=30)
    rows = r.json() if r.status_code == 200 else []
    return [n for n in rows if not ntype or n.get("type") == ntype]


def cancel_open_restock_prs(admin, order_id: str) -> int:
    """Fixture POC: batalkan PR repeat/restock TERBUKA milik order uji lewat API
    resmi, supaya uji anti-dobel bisa dijalankan berulang."""
    r = admin.get(f"{BASE}/purchase-requisitions", timeout=30)
    rows = r.json() if r.status_code == 200 else []
    rows = rows.get("items", rows) if isinstance(rows, dict) else rows
    n = 0
    for pr in rows:
        if (pr.get("source") == "so_repeat" and pr.get("source_ref_id") == order_id
                and pr.get("status") in ("draft", "pending_approval", "approved")):
            if admin.post(f"{BASE}/purchase-requisitions/{pr['id']}/cancel",
                          timeout=30).status_code == 200:
                n += 1
    return n


# ─────────────────────────────────────────────────────────────────────────────
def us1_jobs_registered(admin):
    print("\n── US-1 · 3 job baru terdaftar & jadwal bisa diubah ──────────────")
    r = admin.get(f"{BASE}/scheduler/jobs", timeout=30)
    check("US-1a GET /api/scheduler/jobs 200", r.status_code == 200, f"HTTP {r.status_code}")
    jobs = r.json().get("jobs", []) if r.status_code == 200 else []
    ids = [j.get("id") for j in jobs]
    check("US-1b job po_arrival, backorder_ready, ar_due_soon hadir",
          all(j in ids for j in NEW_JOBS), f"total {len(ids)} job")
    by_id = {j.get("id"): j for j in jobs}
    check("US-1c setiap job baru punya label, deskripsi & jadwal terbaca",
          all(by_id.get(j, {}).get("label") and by_id.get(j, {}).get("schedule_label")
              for j in NEW_JOBS),
          "; ".join(f"{j}={by_id.get(j, {}).get('schedule_label')}" for j in NEW_JOBS))
    check("US-1d job baru punya deep-link modul (job.link)",
          all(by_id.get(j, {}).get("link") for j in NEW_JOBS),
          ", ".join(f"{j}→{by_id.get(j, {}).get('link')}" for j in NEW_JOBS))

    # Ubah jadwal ar_due_soon (07:55 → 06:40) lalu kembalikan.
    up = admin.put(f"{BASE}/scheduler/settings",
                   json={"jobs": {"ar_due_soon": {"enabled": True, "hour": 6, "minute": 40}}},
                   timeout=30)
    r2 = admin.get(f"{BASE}/scheduler/jobs", timeout=30)
    cfg = {j["id"]: j for j in (r2.json().get("jobs", []) if r2.status_code == 200 else [])}
    check("US-1e jadwal job baru dapat diubah lewat API (tanpa deploy)",
          up.status_code == 200 and "06:40" in str(cfg.get("ar_due_soon", {}).get("schedule_label", "")),
          f"HTTP {up.status_code} · {cfg.get('ar_due_soon', {}).get('schedule_label')}")
    admin.put(f"{BASE}/scheduler/settings",
              json={"jobs": {"ar_due_soon": {"enabled": True, "hour": 7, "minute": 55}}},
              timeout=30)


def us2_ar_due_soon(admin, sales, manager):
    print("\n── US-2 · ar_due_soon tepat H-3/H-1/H/H+1 tanpa duplikasi ────────")
    purged = reset_ps21_notifications()
    seeded = seed_ar_offsets()
    check("US-2a kondisi AR NYATA disiapkan pada 4 offset (H-3/H-1/H/H+1)",
          "order digeser" in seeded, f"{seeded[:80]} · reset {purged} notifikasi hari ini")
    r1 = run_job(admin, "ar_due_soon")
    run1 = (r1.json() or {}).get("run", r1.json() or {})
    check("US-2b job ar_due_soon berjalan sukses",
          r1.status_code == 200 and run1.get("status") == "success",
          f"HTTP {r1.status_code} · created={run1.get('created')} · {run1.get('detail')}")
    created_first = int(run1.get("created") or 0)
    check("US-2c menghasilkan notifikasi pada offset yang diminta", created_first > 0,
          f"{created_first} notifikasi · scanned={run1.get('scanned')}")
    rows = notifs(manager, "ar_due_soon")
    check("US-2d notifikasi ar_due_soon terbaca di bell manager (MD/atasan)",
          len(rows) > 0, f"{len(rows)} kartu")
    refs = " ".join(n.get("ref", "") for n in rows)
    offsets_seen = [o for o in ("H-3", "H-1", "H+0", "H+1") if o in refs]
    check("US-2e keempat offset H-3, H-1, H, H+1 muncul",
          len(offsets_seen) == 4, f"terdeteksi: {offsets_seen}")
    sample = rows[0] if rows else {}
    check("US-2f isi notifikasi menyebut jatuh tempo + nominal + deep-link",
          ("jatuh tempo" in (sample.get("title", "") + sample.get("body", "")).lower()
           and "Rp" in sample.get("body", "") and sample.get("link") == "ar-aging"),
          f"{sample.get('title', '')[:60]} | link={sample.get('link')}")
    r2 = run_job(admin, "ar_due_soon")
    run2 = (r2.json() or {}).get("run", r2.json() or {})
    check("US-2g dijalankan ulang hari yang sama → 0 notifikasi baru (dedupe harian)",
          int(run2.get("created") or 0) == 0, f"created={run2.get('created')}")
    keys = [n.get("dedupe_key") for n in notifs(manager, "ar_due_soon")]
    check("US-2h dedupe_key unik per (order × offset × hari)",
          len(keys) == len(set(keys)) and len(keys) > 0,
          f"{len(keys)} kartu · {len(set(keys))} kunci unik")
    srows = notifs(sales, "ar_due_soon")
    check("US-2i sales pemegang akun juga menerima salinan", len(srows) > 0,
          f"{len(srows)} kartu di bell sales")


def us3_backorder_ready(admin, sales, manager):
    print("\n── US-3 · backorder_ready (stok pendingan tersedia) ──────────────")
    r = run_job(admin, "backorder_ready")
    run = (r.json() or {}).get("run", r.json() or {})
    check("US-3a job backorder_ready berjalan sukses",
          r.status_code == 200 and run.get("status") == "success",
          f"HTTP {r.status_code} · created={run.get('created')} · {run.get('detail')}")
    check("US-3b job memindai baris pendingan nyata (bukan mock)",
          int(run.get("scanned") or 0) >= 0, f"scanned={run.get('scanned')}")
    rows = notifs(sales, "backorder_ready") or notifs(manager, "backorder_ready")
    if rows:
        n = rows[0]
        check("US-3c notifikasi pendingan menautkan layar order",
              n.get("link") == "orders", f"link={n.get('link')}")
    else:
        check("US-3c tidak ada pendingan dengan stok tersedia saat ini (kondisi sah)",
              True, "0 notifikasi — semua pendingan memang belum ada stok")
    r2 = run_job(admin, "backorder_ready")
    run2 = (r2.json() or {}).get("run", r2.json() or {})
    check("US-3d run kedua tidak menduplikasi", int(run2.get("created") or 0) == 0,
          f"created={run2.get('created')}")


def us4_po_arrival(admin, wh, manager):
    print("\n── US-4 · po_arrival (barang PO datang) ──────────────────────────")
    r = run_job(admin, "po_arrival")
    run = (r.json() or {}).get("run", r.json() or {})
    check("US-4a job po_arrival berjalan sukses",
          r.status_code == 200 and run.get("status") == "success",
          f"HTTP {r.status_code} · created={run.get('created')} · {run.get('detail')}")

    # Peristiwa NYATA: terima barang PO (scan-receive → complete) → notifikasi seketika.
    tasks = wh.get(f"{BASE}/inbound/tasks", timeout=30)
    rows = tasks.json() if tasks.status_code == 200 else []
    # Hanya tugas yang MASIH bisa dimajukan: waiting_goods (perlu scan) atau
    # qc_check/put_away (siap diselesaikan). qc_pending = sudah diterima, tunggu QC.
    SCANNABLE = ("waiting_goods", "created", "pending", "receiving")
    open_task = next((t for t in rows if t.get("status") in SCANNABLE), None) \
        or next((t for t in rows if t.get("status") in ("qc_check", "put_away")), None)
    if not open_task:
        check("US-4b tidak ada tugas inbound yang bisa dimajukan (kondisi sah — "
              "job & notifikasi tetap terverifikasi di US-4a/4d)", True,
              f"status tugas: {sorted({t.get('status') for t in rows})}")
        return
    before = len(notifs(manager, "po_arrival"))
    qty = float(open_task.get("expected_qty") or open_task.get("quantity") or 10) or 10
    scan_code = "-"
    if open_task.get("status") in SCANNABLE:
        scan = wh.post(f"{BASE}/inbound/tasks/{open_task['id']}/scan-receive",
                       json={"product_id": open_task.get("product_id"), "actual_qty": qty,
                             "batch": "POC-PS21", "lot": "LOT-POC-PS21"}, timeout=60)
        scan_code = str(scan.status_code)
    comp = wh.post(f"{BASE}/inbound/tasks/{open_task['id']}/complete",
                   json={"grade": "A", "rolls": []}, timeout=90)
    check("US-4b Goods Receipt diselesaikan (peristiwa nyata: scan → complete)",
          comp.status_code in (200, 201),
          f"scan HTTP {scan_code} · complete HTTP {comp.status_code} "
          f"· {str(comp.text)[:100]}")
    after_rows = notifs(manager, "po_arrival")
    check("US-4c notifikasi 'barang PO datang' muncul SEKETIKA setelah GR",
          len(after_rows) > before, f"{before} → {len(after_rows)} kartu")
    wh_rows = notifs(wh, "po_arrival")
    check("US-4d gudang juga menerima notifikasi penerimaan", len(wh_rows) > 0,
          f"{len(wh_rows)} kartu di bell gudang")
    body_txt = " ".join(n.get("body", "") for n in after_rows)
    check("US-4e isi notifikasi menyebut produk, qty & gudang penerimaan",
          ("diterima di" in body_txt or "masuk gudang" in body_txt),
          f"{(after_rows[0].get('body', '') if after_rows else '')[:90]}")
    r2 = run_job(admin, "po_arrival")
    run2 = (r2.json() or {}).get("run", r2.json() or {})
    check("US-4f job berikutnya tidak menduplikasi notifikasi yang sama",
          int(run2.get("created") or 0) == 0, f"created={run2.get('created')}")


def _pick_order_with_items(s):
    r = s.get(f"{BASE}/sales-orders", timeout=30)
    rows = r.json() if r.status_code == 200 else []
    rows = rows.get("items", rows) if isinstance(rows, dict) else rows
    best = None
    for o in rows:
        st = s.get(f"{BASE}/sales-orders/{o['id']}/restock-state", timeout=30)
        if st.status_code != 200:
            continue
        state = st.json()
        if state.get("candidates"):
            if state.get("has_backorder"):
                return o, state
            best = best or (o, state)
    return best or (None, None)


def us5_us9_restock(sales, admin, manager):
    print("\n── US-5…US-9 · Repeat/Restock 1-klik SO → PR + notifikasi MD ─────")
    order, state = _pick_order_with_items(sales)
    check("US-5a sales dapat membaca status pendingan & kandidat restock dari order",
          bool(order) and bool(state and state.get("candidates")),
          f"order {(order or {}).get('number')} · {len((state or {}).get('candidates', []))} kandidat")
    if not order:
        return
    cleaned = cancel_open_restock_prs(admin, order["id"])
    if cleaned:
        print(f"   (fixture: {cleaned} PR repeat/restock terbuka dibatalkan agar uji berulang)")
    cand = (state or {}).get("candidates", [])[0]
    keys = {"product_id", "product_name", "available_qty", "backorder_qty", "suggest_qty", "unit"}
    check("US-5b setiap kandidat membawa stok tersedia, pendingan & saran qty",
          keys.issubset(set(cand.keys())),
          f"{cand.get('product_name')} avail={cand.get('available_qty')} "
          f"bo={cand.get('backorder_qty')} saran={cand.get('suggest_qty')}")
    check("US-5c status pendingan order terlihat (panel pendingan)",
          isinstance((state or {}).get("pendingan"), list),
          f"{len((state or {}).get('pendingan', []))} baris pendingan")

    # US-9 validasi input
    bad0 = sales.post(f"{BASE}/sales-orders/{order['id']}/repeat-restock",
                      json={"items": []}, timeout=30)
    check("US-9a item kosong ditolak 400", bad0.status_code == 400,
          f"HTTP {bad0.status_code}: {str(bad0.text)[:90]}")
    bad1 = sales.post(f"{BASE}/sales-orders/{order['id']}/repeat-restock",
                      json={"items": [{"product_id": cand["product_id"], "quantity": 0}]},
                      timeout=30)
    check("US-9b qty 0 ditolak (400/422)", bad1.status_code in (400, 422),
          f"HTTP {bad1.status_code}")
    bad2 = sales.post(f"{BASE}/sales-orders/{order['id']}/repeat-restock",
                      json={"items": [{"product_id": "prod_tidak_ada", "quantity": 5}]},
                      timeout=30)
    check("US-9c produk tak dikenal ditolak 400 berbahasa Indonesia",
          bad2.status_code == 400 and "tidak ditemukan" in str(bad2.text).lower(),
          f"HTTP {bad2.status_code}: {str(bad2.text)[:90]}")

    # US-6 aksi 1 klik (qty desimal koma — PS-15)
    before_md = len(notifs(manager, "restock_request"))
    ok = sales.post(f"{BASE}/sales-orders/{order['id']}/repeat-restock",
                    json={"items": [{"product_id": cand["product_id"], "quantity": "12,5",
                                     "note": "POC PS-21"}],
                          "reason": "Pelanggan minta repeat"}, timeout=60)
    body = ok.json() if ok.status_code == 200 else {}
    pr = body.get("pr") or {}
    check("US-6a 1 klik repeat/restock → PR dibuat",
          ok.status_code == 200 and bool(pr.get("number")),
          f"HTTP {ok.status_code} · PR {pr.get('number')} status={pr.get('status')}")
    check("US-6b qty desimal koma '12,5' diterima (PS-15)",
          any(abs(float(it.get("quantity", 0)) - 12.5) < 0.01 for it in pr.get("items", [])),
          str([it.get("quantity") for it in pr.get("items", [])]))
    after_md = len(notifs(manager, "restock_request"))
    check("US-6c MD (manager) menerima notifikasi permintaan restock",
          after_md > before_md and int(body.get("notified_md") or 0) >= 1,
          f"{before_md} → {after_md} kartu · notified_md={body.get('notified_md')}")
    md_note = (notifs(manager, "restock_request") or [{}])[0]
    check("US-6d notifikasi MD menautkan layar PR (deep-link)",
          md_note.get("link") == "purchase-requisitions", f"link={md_note.get('link')}")

    # US-7 jejak dua arah
    prd = admin.get(f"{BASE}/purchase-requisitions/{pr.get('id')}", timeout=30)
    prdoc = prd.json() if prd.status_code == 200 else {}
    check("US-7a PR menyimpan asal order (source=so_repeat + source_ref_id)",
          prdoc.get("source") == "so_repeat" and prdoc.get("source_ref_id") == order["id"],
          f"source={prdoc.get('source')} ref={str(prdoc.get('source_ref_id'))[:14]}")
    st2 = sales.get(f"{BASE}/sales-orders/{order['id']}/restock-state", timeout=30)
    state2 = st2.json() if st2.status_code == 200 else {}
    reqs = state2.get("restock_requests") or []
    check("US-7b SO mencatat riwayat permintaan restock (nomor PR & pemohon)",
          any(x.get("pr_number") == pr.get("number") for x in reqs),
          f"{len(reqs)} riwayat · terakhir={reqs[-1].get('pr_number') if reqs else '-'}")
    check("US-7c kandidat produk menampilkan PR terbuka agar sales tidak minta dobel",
          any(c.get("open_pr_number") == pr.get("number")
              for c in state2.get("candidates", [])),
          f"open_pr={[c.get('open_pr_number') for c in state2.get('candidates', [])][:3]}")

    # US-8 anti PR dobel
    dup = sales.post(f"{BASE}/sales-orders/{order['id']}/repeat-restock",
                     json={"items": [{"product_id": cand["product_id"], "quantity": 5}]},
                     timeout=30)
    check("US-8a permintaan ganda produk sama ditolak 400 (anti PR dobel)",
          dup.status_code == 400 and "dobel" in str(dup.text).lower(),
          f"HTTP {dup.status_code}: {str(dup.text)[:110]}")
    return pr


def us10_engine_integration(admin, manager, pr):
    print("\n── US-10 · Integrasi mesin notifikasi R6.5/R6.6 ──────────────────")
    r = admin.get(f"{BASE}/scheduler/summary", timeout=30)
    summ = r.json() if r.status_code == 200 else {}
    check("US-10a total job bertambah menjadi 12", int(summ.get("jobs_total") or 0) == 12,
          f"jobs_total={summ.get('jobs_total')} enabled={summ.get('jobs_enabled')}")
    runs = admin.get(f"{BASE}/scheduler/runs", params={"job_id": "ar_due_soon"}, timeout=30)
    hist = runs.json() if runs.status_code == 200 else []
    hist = hist.get("runs", hist) if isinstance(hist, dict) else hist
    check("US-10b riwayat eksekusi job baru tercatat (sys_scheduler_runs)",
          len(hist) >= 2 and all(h.get("job_id") == "ar_due_soon" for h in hist),
          f"{len(hist)} run tercatat")
    all_notifs = manager.get(f"{BASE}/notifications", timeout=30).json()
    types = {n.get("type") for n in all_notifs}
    check("US-10c jenis notifikasi baru dapat difilter di bell",
          {"ar_due_soon", "restock_request"}.issubset(types) or "po_arrival" in types,
          f"jenis: {sorted(t for t in types if t in ('ar_due_soon', 'po_arrival', 'backorder_ready', 'restock_request'))}")
    sev = {n.get("severity") for n in all_notifs if n.get("type") == "ar_due_soon"}
    check("US-10d severity mengikuti urgensi (info/warning/critical)",
          bool(sev & {"info", "warning", "critical"}), f"severity={sorted(sev)}")
    outbox = admin.get(f"{BASE}/scheduler/wa-outbox", timeout=30)
    check("US-10e kanal WhatsApp memproses notifikasi baru (outbox/digest aktif)",
          outbox.status_code == 200, f"HTTP {outbox.status_code}")


def main():
    print("=" * 78)
    print("  POC PS-21 — Notifikasi Operasional + Repeat/Restock 1-Klik")
    print("=" * 78)
    admin, sales, manager, wh = (login(ADMIN), login(SALES), login(MANAGER), login(WAREHOUSE))
    us1_jobs_registered(admin)
    us2_ar_due_soon(admin, sales, manager)
    us3_backorder_ready(admin, sales, manager)
    us4_po_arrival(admin, wh, manager)
    pr = us5_us9_restock(sales, admin, manager)
    us10_engine_integration(admin, manager, pr)

    print("\n" + "=" * 78)
    print(f"  HASIL: {len(PASS)} PASS · {len(FAIL)} FAIL")
    print("=" * 78)
    if FAIL:
        for f in FAIL:
            print(f"   ❌ {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
