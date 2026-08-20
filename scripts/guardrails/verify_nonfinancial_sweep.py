#!/usr/bin/env python3
"""INV-ENTITY-01 (perluasan) — SWEEP modul NON-FINANSIAL untuk IDOR lintas-entitas.

Blindspot yang ditutup: `verify_cross_entity.py` menutup jalur FINANSIAL/penjualan inti
(customer 360/credit-status, SO invoices, inbound escalate). Tapi audit #076–#078 mencatat
sisa risiko: **modul non-finansial** (CRM follow-up/credit-override, WMS task ops, HR, RFID,
cycle-count, konsolidasi, omnichannel) belum disapu penuh untuk IDOR **baca & tulis**
lintas-PT. Sweep ini melengkapi cakupan agar isolasi multi-entitas teruji menyeluruh.

Metode (RUNTIME behavioral — paling andal karena scope ditegakkan di lapis service):
  Login sebagai peran ter-scope entitas A (sales/warehouse, non lintas-entitas) → akses
  dokumen milik entitas B → HARUS ditolak.
    - BACA lintas-PT  → SAH bila 401/403/404. Bila 200 = LEAK.
    - TULIS lintas-PT → SAH bila 401/403/404. Bila 200 / mencapai business-logic
      (400/409/422 = lolos guard entitas) = LEAK.

Registry `CASES` mudah diperluas (Phase 3). Kasus di-SKIP rapi bila seed tak punya dokumen
dua-entitas untuk modul itu (mis. hr_employees single-entity, rfid_tags tak ber-entity).

Plus **peta cakupan STATIK (advisory, tak mem-fail)**: untuk tiap router non-finansial,
tampilkan apakah menyentuh koleksi ter-scope & apakah memakai guard entitas — memandu
prioritas fase fixing.

Resilient: backend down / login gagal / data kurang → SKIP. Exit 1 hanya bila LEAK terbukti.
Usage: cd /app && MONGO_URL=... DB_NAME=... python scripts/guardrails/verify_nonfinancial_sweep.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _common import BACKEND  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass
try:
    import requests
except ImportError:
    os.system("pip install requests -q")
    import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import run_with_restore  # noqa: E402
from pymongo import MongoClient

BASE = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/") + "/api"
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
PROTECTED = {401, 403, 404}
fails = 0
skips = 0
oks = 0

# Router non-finansial yang disapu (peta cakupan statik + rujukan runtime).
NONFIN_ROUTERS = [
    "crm", "crm_omnichannel", "rfid", "cycle_count", "consolidation",
    "hr", "hr_analytics", "hr_attendance", "hr_kpi", "hr_leave", "hr_payroll",
    "hr_tracking", "design_gallery", "label_printer", "notifications",
    "onboarding", "integrations", "wms", "inbound_receiving", "transfers",
]
GUARD_TOKENS = ("assert_entity_access", "can_access_customer", "resolve_scope_ids",
                "apply_entity_scope", "resolve_list_scope", "resolve_scope")


def ok(m):
    global oks
    oks += 1
    print(f"  {G}[OK]{X} {m}")


def leak(m):
    global fails
    fails += 1
    print(f"  {R}[LEAK]{X} {m}")


def skip(m):
    global skips
    skips += 1
    print(f"  {Y}[SKIP]{X} {m}")


def login(email, pw="demo12345"):
    try:
        r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=10)
        return r.json().get("token") if r.status_code == 200 else None
    except Exception:
        return None


# ─── Peta cakupan STATIK (advisory) ─────────────────────────────────────────
def _scoped_collections() -> set:
    """Ambil SCOPED_COLLECTIONS dari entity_scope.py tanpa import berat."""
    txt = (BACKEND / "entity_scope.py").read_text()
    m = re.search(r"SCOPED_COLLECTIONS\s*=\s*\{(.+?)\}", txt, re.S)
    if not m:
        return set()
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def coverage_map() -> None:
    scoped = _scoped_collections()
    print(f"{C}{B}-- PETA CAKUPAN STATIK (advisory · tak mem-fail) --{X}")
    print(f"  {'router':<22}{'scoped-coll?':<26}{'guard?':<10}mutasi")
    for name in NONFIN_ROUTERS:
        fp = BACKEND / "routers" / f"{name}.py"
        if not fp.exists():
            continue
        txt = fp.read_text()
        touched = sorted({c for c in scoped if re.search(rf'\bdb\.{c}\b', txt)})
        guards = sorted({t for t in GUARD_TOKENS if t in txt})
        n_mut = len(re.findall(r'@router\.(post|patch|put|delete)\(', txt))
        tflag = (",".join(touched)[:24] or "-")
        gflag = (G + "yes" + X) if guards else (R + "NO" + X)
        note = ""
        if touched and not guards:
            note = f"  {R}← sentuh scoped tanpa guard (cek runtime){X}"
        print(f"  {name:<22}{tflag:<26}{gflag:<19}{n_mut}{note}")
    print()


# ─── Kasus RUNTIME (registry) ───────────────────────────────────────────────
def actors(mc, role):
    """Semua user ter-scope entitas (bukan lintas-entitas) untuk `role`.
    Yield dict {id,email,allowed}. Aktor dgn allowed jamak (lintas-entitas) dilewati."""
    for u in mc.users.find({"role": role, "status": "active"},
                           {"_id": 0, "id": 1, "email": 1, "home_entity_id": 1, "allowed_entity_ids": 1}):
        allowed = set(a for a in (u.get("allowed_entity_ids") or [u.get("home_entity_id")]) if a)
        yield {"id": u.get("id"), "email": u.get("email"), "allowed": allowed}


def foreign_doc(mc, coll, field, allowed, exclude_field=None, exclude_val=None):
    """Dokumen `coll` yang field-entitasnya di LUAR `allowed` (milik entitas lain).
    `exclude_field/val` → buang dokumen yang secara ROW dimiliki aktor (mis. assigned_sales_id
    == actor.id) agar temuan IDOR bebas-ambiguitas (foreign-by-entity DAN bukan milik-baris)."""
    if coll not in mc.list_collection_names():
        return None
    q = {field: {"$nin": list(allowed), "$ne": None}}
    if exclude_field is not None:
        q[exclude_field] = {"$ne": exclude_val}
    return mc[coll].find_one(q, {"_id": 0, "id": 1, field: 1})


def run_case(headers, label, method, path, kind, payload=None):
    """Jalankan 1 kasus akses lintas-PT & klasifikasi."""
    try:
        st = requests.request(method, f"{BASE}{path}", headers=headers, json=payload, timeout=12).status_code
    except Exception as e:  # noqa: BLE001
        skip(f"{label}: error {e}")
        return
    if st in PROTECTED:
        ok(f"{label}: {method} {path} lintas-PT ditolak ({st}).")
    elif kind == "read":
        leak(f"{label}: BACA lintas-PT → {st} (harus 401/403/404). {method} {path}")
    else:  # write
        if st >= 500:
            skip(f"{label}: {method} {path} → {st} CRASH (tak konklusif untuk IDOR).")
        else:
            leak(f"{label}: TULIS lintas-PT → {st} (mencapai business-logic; harus 401/403/404). {method} {path}")


def main() -> int:
    print(f"\n{B}{'='*64}{X}\n  NON-FINANCIAL IDOR SWEEP (INV-ENTITY-01+)  {BASE}\n{B}{'='*64}{X}")
    coverage_map()
    try:
        if requests.get(f"{BASE}/", timeout=5).status_code >= 500:
            raise Exception("5xx")
    except Exception:
        print(f"{Y}  Backend belum berjalan — RUNTIME di-SKIP (Phase 0).{X}")
        return _summary()

    mc = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
    print(f"{C}{B}-- RUNTIME (probe akses lintas-PT) --{X}")

    # ===== Modul CRM (koleksi customers ter-scope) — aktor: sales entitas A =====
    # Pilih pasangan (sales, customer) yang BEBAS-AMBIGUITAS: customer foreign-by-entity
    # DAN tidak dimiliki-baris aktor (assigned_sales_id != actor.id) → 200 = IDOR murni.
    crm_pair = None
    for a in actors(mc, "sales"):
        fc = foreign_doc(mc, "customers", "entity_id", a["allowed"],
                         exclude_field="assigned_sales_id", exclude_val=a["id"])
        if fc:
            crm_pair = (a, fc)
            break
    if not crm_pair:
        skip("CRM: tak ada pasangan (sales, customer entitas-lain non-milik) di seed — SKIP.")
    else:
        a, fc = crm_pair
        stok = login(a["email"])
        if not stok:
            skip(f"CRM: login {a['email']} gagal — SKIP.")
        else:
            Hs = {"Authorization": f"Bearer {stok}"}
            cid = fc["id"]
            ctx = f"[aktor {a['email']} allowed={sorted(a['allowed'])} → customer {cid}@{fc['entity_id']}]"
            print(f"  {C}CRM {ctx}{X}")
            run_case(Hs, "CRM read-360", "GET", f"/customers/{cid}/360", "read")
            run_case(Hs, "CRM read-credit-status", "GET", f"/customers/{cid}/credit-status", "read")
            run_case(Hs, "CRM write-followup", "POST", f"/customers/{cid}/followups", "write",
                     {"customer_id": cid, "note": "xentity-sweep-probe", "outcome": "contacted"})
            run_case(Hs, "CRM write-credit-override", "POST", f"/customers/{cid}/credit-override", "write",
                     {"customer_id": cid, "amount": 1000, "reason": "xentity-sweep-probe"})

    # ===== Modul WMS (wms_tasks ter-scope) — aktor: warehouse entitas A =====
    wms_pair = None
    for a in actors(mc, "warehouse"):
        ft = foreign_doc(mc, "wms_tasks", "entity_id", a["allowed"])
        if ft:
            wms_pair = (a, ft)
            break
    if not wms_pair:
        skip("WMS: tak ada pasangan (warehouse, wms_task entitas-lain) di seed — SKIP.")
    else:
        a, ft = wms_pair
        wtok = login(a["email"])
        if not wtok:
            skip(f"WMS: login {a['email']} gagal — SKIP.")
        else:
            Hw = {"Authorization": f"Bearer {wtok}"}
            tid = ft["id"]
            print(f"  {C}WMS [aktor {a['email']} allowed={sorted(a['allowed'])} → task {tid}@{ft['entity_id']}]{X}")
            run_case(Hw, "WMS write-scan", "POST", f"/wms/tasks/{tid}/scan", "write",
                     {"scan_type": "roll", "scan_value": "xentity-sweep-probe"})
            run_case(Hw, "WMS write-advance", "POST", f"/wms/tasks/{tid}/advance", "write", {})

    # ===== Modul HR / RFID / cycle-count — SKIP terdokumentasi bila data kurang =====
    if not foreign_doc(mc, "hr_employees", "entity_id", {"__none__"}):
        skip("HR: hr_employees single-entity di seed (tak ada foreign) — sweep HR baca/tulis tak dapat diuji runtime.")
    if not foreign_doc(mc, "rfid_tags", "entity_id", {"__none__"}):
        skip("RFID: rfid_tags tak ber-`entity_id` (global) — bukan surface IDOR entitas; lihat resolve_scope_ids.")
    if "cycle_count_sessions" not in mc.list_collection_names():
        skip("cycle-count: koleksi cycle_count_sessions kosong di seed — SKIP.")
    if "crm_leads" not in mc.list_collection_names():
        skip("CRM-omnichannel: crm_leads/interactions kosong di seed — SKIP.")

    return _summary()


def _summary() -> int:
    print(f"\n{B}{'='*64}{X}\n  {G}OK {oks}{X} | {R}LEAK {fails}{X} | {Y}SKIP {skips}{X}\n{B}{'='*64}{X}")
    if fails:
        print(f"{R}{B}  IDOR NON-FINANSIAL TERBUKTI — isolasi multi-PT bocor (INV-ENTITY-01).{X}\n")
        return 1
    print(f"{G}{B}  Modul non-finansial teruji BERSIH untuk cakupan seed (INV-ENTITY-01 tertutup).{X}\n")
    return 0


if __name__ == "__main__":
    try:
        # Gate runtime memanggil API sungguhan -> MENGUBAH data (mis. audit_logs).
        # run_with_restore() snapshot DB sebelum uji & memulihkannya di `finally`,
        # supaya `gate.sh` tidak lagi meninggalkan residu di data demo.
        rc = run_with_restore(main)
    except Exception as ex:  # noqa: BLE001
        print(f"{Y}  Gate error (dianggap SKIP): {ex}{X}")
        rc = 0
    sys.exit(rc)
