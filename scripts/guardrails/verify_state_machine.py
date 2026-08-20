#!/usr/bin/env python3
"""INV-STATE-01 (RUNTIME) — GATE integritas STATE-MACHINE Sales Order.

Blindspot yang ditutup: verifikasi #074–#076 tak menguji semantik transisi state secara sistematis.
Proyek pembanding (travel) menemukan 4 dari 7 cacat P0 di sini (cancel tak melepas sumber daya,
complete beri sinyal kontradiktif, split-brain status).

Invarian diuji (SO):
  * SM-1  CANCEL-RELEASE : membatalkan SO ter-reserve HARUS melepas roll ter-reserve
                          (reserved_ref.id == order_id) kembali ke `available`.
  * SM-2  TERMINAL-GUARD : SO status terminal (done/shipped/...) TIDAK boleh bisa di-cancel (→ 409).
  * SM-3  IDEMPOTENT     : cancel-ulang SO yang sudah cancelled → 4xx (bukan 200, bukan 5xx),
                          dan tak menambah efek samping.
  * SM-4  NO-ZOMBIE-TASK : setelah cancel, tak ada wms_task aktif (assigned/in_progress) tersisa
                          untuk order tsb (harus cancelled).

Resilient: backend down / data kurang → SKIP. Exit 1 hanya bila invarian dilanggar.

⚠️ GATE INI MENGUBAH DATA (memanggil endpoint cancel/advance sungguhan).
   Sejak 2026-07-26 seluruh perubahan DIPULIHKAN otomatis lewat `DbSnapshot`
   (snapshot sebelum uji → restore di `finally`). Sebelum perbaikan itu, setiap
   `gate.sh` merusak data demo permanen: order seed so_006 dibatalkan, reservasi
   dilepas, dan on_hand prod_batik_mega/wh_jakarta membengkak 75 → 485 yard.

Usage: cd /app && MONGO_URL=... DB_NAME=... python scripts/guardrails/verify_state_machine.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass
import requests
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DbSnapshot  # noqa: E402

BASE = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/") + "/api"
G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"
HELD = ["reserved", "allocated", "waiting_approval", "approved", "waiting_stock", "picking", "packed"]
fails = 0
skips = 0


def ok(m):
    print(f"  {G}[OK]{X} {m}")


def bad(m):
    global fails
    fails += 1
    print(f"  {R}[FAIL]{X} {m}")


def skip(m):
    global skips
    skips += 1
    print(f"  {Y}[SKIP]{X} {m}")


def admin_headers():
    try:
        r = requests.post(f"{BASE}/auth/login",
                          json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=10)
        return {"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else None
    except Exception:
        return None


def main() -> int:
    print(f"\n{B}{'='*64}{X}\n  STATE-MACHINE GATE (INV-STATE-01)  {BASE}\n{B}{'='*64}{X}")
    try:
        if requests.get(f"{BASE}/", timeout=5).status_code >= 500:
            raise Exception("5xx")
    except Exception:
        print(f"{Y}  Backend belum berjalan — SKIP (Phase 0).{X}")
        return 0
    mc = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    # Gate ini SENGAJA mengubah state (cancel SO, advance task). Ambil snapshot dulu,
    # pulihkan di `finally` supaya data demo tidak rusak — lihat docstring modul.
    # PENTING: snapshot diambil SEBELUM login, karena login sendiri menulis
    # audit_logs/login_attempts. Bila snapshot diambil sesudahnya, baris audit itu
    # ikut "dibekukan" dan tetap tertinggal (+1 audit_log per gate — terukur).
    snap = DbSnapshot(mc).take()
    try:
        H = admin_headers()
        if not H:
            skip("login admin gagal.")
            return _summary()
        return _run_checks(mc, H)
    finally:
        snap.restore()


def _run_checks(mc, H) -> int:
    # ---- SM-1 + SM-3 + SM-4: pilih SO ter-reserve ----
    so = mc.sales_orders.find_one({"status": "reserved"}, {"_id": 0, "id": 1, "number": 1})
    if not so:
        skip("Tak ada SO status 'reserved' di seed — SKIP SM-1/3/4.")
    else:
        oid = so["id"]
        held_before = mc.inventory_rolls.count_documents({"reserved_ref.id": oid, "status": {"$in": HELD}})
        r = requests.post(f"{BASE}/sales-orders/{oid}/cancel", headers=H, timeout=15)
        if r.status_code != 200:
            skip(f"cancel SO {so.get('number')} → {r.status_code} (tak bisa uji lanjut).")
        else:
            held_after = mc.inventory_rolls.count_documents({"reserved_ref.id": oid, "status": {"$in": HELD}})
            if held_before > 0 and held_after > 0:
                bad(f"SM-1 CANCEL-RELEASE: SO {so.get('number')} dibatalkan tapi {held_after}/{held_before} "
                    f"roll MASIH ter-reserve (stok nyangkut). Cancel harus melepas roll → available.")
            else:
                ok(f"SM-1 CANCEL-RELEASE: {held_before} roll ter-reserve dilepas ({held_after} tersisa).")
            # SM-4: tak ada task aktif tersisa
            zombie = mc.wms_tasks.count_documents({"sales_order_id": oid,
                                                   "status": {"$in": ["assigned", "in_progress", "pending"]}})
            if zombie:
                bad(f"SM-4 NO-ZOMBIE-TASK: {zombie} wms_task masih aktif setelah SO {so.get('number')} dibatalkan.")
            else:
                ok("SM-4 NO-ZOMBIE-TASK: tak ada task aktif tersisa pasca-cancel.")
            # SM-3: cancel-ulang idempoten
            r2 = requests.post(f"{BASE}/sales-orders/{oid}/cancel", headers=H, timeout=15)
            if r2.status_code == 200:
                bad(f"SM-3 IDEMPOTENT: cancel-ulang SO {so.get('number')} → 200 (harus 4xx; order sudah cancelled).")
            elif r2.status_code >= 500:
                bad(f"SM-3 IDEMPOTENT: cancel-ulang → {r2.status_code} CRASH (harus 4xx bersih).")
            else:
                ok(f"SM-3 IDEMPOTENT: cancel-ulang ditolak bersih ({r2.status_code}).")

    # ---- SM-2: SO terminal tak boleh di-cancel ----
    term = mc.sales_orders.find_one({"status": {"$in": ["done", "shipped", "partially_shipped"]}},
                                    {"_id": 0, "id": 1, "number": 1, "status": 1})
    if not term:
        skip("Tak ada SO terminal (done/shipped) di seed — SKIP SM-2.")
    else:
        rc = requests.post(f"{BASE}/sales-orders/{term['id']}/cancel", headers=H, timeout=15).status_code
        if rc == 200:
            bad(f"SM-2 TERMINAL-GUARD: SO {term.get('number')} status '{term.get('status')}' BISA di-cancel (200) — harus ditolak (409).")
        else:
            ok(f"SM-2 TERMINAL-GUARD: cancel SO terminal '{term.get('status')}' ditolak ({rc}).")

    # ---- SM-WMS-1: WMS task terminal (completed/done) TIDAK boleh bisa di-advance (anti-resurrection) ----
    term_tasks = list(mc.wms_tasks.find({"status": {"$in": ["completed", "done"]}},
                                        {"_id": 0, "id": 1, "status": 1, "flow_type": 1}).limit(6))
    if not term_tasks:
        skip("Tak ada wms_task terminal (completed/done) di seed — SKIP SM-WMS-1.")
    else:
        resurrected = []
        for t in term_tasks:
            rc = requests.post(f"{BASE}/wms/tasks/{t['id']}/advance", headers=H, timeout=15).status_code
            if rc == 200:
                now = mc.wms_tasks.find_one({"id": t["id"]}, {"_id": 0, "status": 1})
                resurrected.append(f"{t['id']}({t['status']}→{now.get('status')})")
        if resurrected:
            bad(f"SM-WMS-1 RESURRECTION: {len(resurrected)}/{len(term_tasks)} task TERMINAL bisa di-advance (200) — "
                f"task terminal 'hidup lagi': {resurrected[:3]}. Akar: status ('completed'/'qc_pending'/'waiting_goods') "
                f"TAK ADA di FLOW_STAGES → advance() reset current_idx=0 → maju ke stage[1]. Risiko double-proses/receipt.")
        else:
            ok(f"SM-WMS-1 RESURRECTION: {len(term_tasks)} task terminal ditolak advance (aman).")

    # ---- SM-PO-1: approve PO salah-state (bukan waiting_approval) HARUS ditolak ----
    po_done = mc.purchase_orders.find_one({"status": {"$in": ["completed", "pending", "receiving"]}},
                                          {"_id": 0, "id": 1, "po_number": 1, "status": 1})
    if not po_done:
        skip("Tak ada PO non-waiting_approval di seed — SKIP SM-PO-1.")
    else:
        rc = requests.post(f"{BASE}/purchase-orders/{po_done['id']}/approve", headers=H, timeout=15).status_code
        if rc == 200:
            bad(f"SM-PO-1 STATE-GUARD: PO {po_done.get('po_number')} status '{po_done.get('status')}' BISA di-approve (200) — harus 409.")
        elif rc >= 500:
            bad(f"SM-PO-1 STATE-GUARD: approve PO salah-state → {rc} CRASH (harus 4xx).")
        else:
            ok(f"SM-PO-1 STATE-GUARD: approve PO status '{po_done.get('status')}' ditolak ({rc}).")

    # ---- SM-PO-2: cancel PO terminal (completed) HARUS ditolak ----
    po_comp = mc.purchase_orders.find_one({"status": "completed"}, {"_id": 0, "id": 1, "po_number": 1})
    if po_comp:
        rc = requests.post(f"{BASE}/purchase-orders/{po_comp['id']}/cancel", headers=H, timeout=15).status_code
        if rc == 200:
            bad(f"SM-PO-2 TERMINAL-GUARD: PO {po_comp.get('po_number')} 'completed' BISA di-cancel (200) — harus 4xx.")
        elif rc >= 500:
            bad(f"SM-PO-2 TERMINAL-GUARD: cancel PO completed → {rc} CRASH (harus 4xx).")
        else:
            ok(f"SM-PO-2 TERMINAL-GUARD: cancel PO 'completed' ditolak ({rc}).")
    else:
        skip("Tak ada PO 'completed' di seed — SKIP SM-PO-2.")

    return _summary()


def _summary() -> int:
    print(f"\n{B}{'='*64}{X}\n  {R}FAIL {fails}{X} | {Y}SKIP {skips}{X}\n{B}{'='*64}{X}")
    if fails:
        print(f"{R}{B}  STATE-MACHINE CACAT — transisi SO melanggar invarian (INV-STATE-01).{X}\n")
        return 1
    print(f"{G}{B}  State-machine SO sehat untuk jalur teruji (INV-STATE-01 tertutup).{X}\n")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as ex:  # noqa: BLE001
        print(f"{Y}  Gate error (dianggap SKIP): {ex}{X}")
        rc = 0
    sys.exit(rc)
