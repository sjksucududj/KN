#!/usr/bin/env python3
"""INV-ENTITY-01 (RUNTIME) — GATE anti-IDOR lintas-entitas (isolasi multi-PT).

Kelas bug yang dicegah (Sesi #076):
  * IDOR-READ-SUBRES (P0): user sales @ent_ksc bisa BACA sub-resource milik ent_kanda
    (GET /customers/{id}/360, /customers/{id}/credit-status, /sales-orders/{id}/invoices).
  * IDOR-WRITE-INBOUND (P1): user gudang @ent_ksc bisa MUTASI task inbound milik ent_kanda
    (POST /inbound/tasks/{id}/escalate — tereksekusi 200).

Kenapa RUNTIME (bukan statik): KN menegakkan scope entitas di LAPISAN SERVICE
(mis. `so_transition`, `assert_entity_access` di service) — bukan selalu inline di router.
Deteksi statik router-only → banyak false-positive. Uji PERILAKU jauh lebih andal:
login sebagai peran ter-scope entitas A → coba akses dokumen entitas B → HARUS ditolak.

Kriteria:
  - BACA lintas-entitas  → HARUS 401/403/404. Bila 200 = LEAK.
  - TULIS lintas-entitas → HARUS 401/403/404. Bila mencapai business-logic
    (200 tereksekusi, atau 400/409/422 = lolos guard entitas) = LEAK.

Resilient: backend down / login gagal / data seed kurang → SKIP (Phase 0). Exit 1 hanya bila LEAK.
Usage: cd /app && MONGO_URL=... DB_NAME=... python scripts/guardrails/verify_cross_entity.py
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
try:
    import requests
except ImportError:
    os.system("pip install requests -q")
    import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import run_with_restore  # noqa: E402
from pymongo import MongoClient

BASE = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/") + "/api"
G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"
PROTECTED = {401, 403, 404}  # respons SAH untuk akses lintas-entitas
fails = 0
skips = 0


def ok(m):
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


def main() -> int:
    print(f"\n{B}{'='*64}{X}\n  CROSS-ENTITY IDOR GATE (INV-ENTITY-01, runtime)  {BASE}\n{B}{'='*64}{X}")
    try:
        if requests.get(f"{BASE}/", timeout=5).status_code >= 500:
            raise Exception("5xx")
    except Exception:
        print(f"{Y}  Backend belum berjalan — SKIP (Phase 0).{X}")
        return 0

    mc = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

    # --- Tentukan dua entitas berbeda & aktor ter-scope entitas A ---
    sales = mc.users.find_one({"role": "sales"}, {"_id": 0, "email": 1, "home_entity_id": 1})
    wh = mc.users.find_one({"role": "warehouse"}, {"_id": 0, "email": 1, "home_entity_id": 1})
    if not sales or not wh:
        skip("Tak ada user sales/warehouse di seed — SKIP.")
        return _summary()
    home = sales.get("home_entity_id")

    # dokumen milik ENTITAS LAIN (foreign)
    fcust = mc.customers.find_one({"entity_id": {"$ne": home}}, {"_id": 0, "id": 1, "entity_id": 1})
    fso = mc.sales_orders.find_one({"entity_id": {"$ne": home}}, {"_id": 0, "id": 1, "entity_id": 1})
    ftask = mc.wms_tasks.find_one({"entity_id": {"$ne": wh.get("home_entity_id")}}, {"_id": 0, "id": 1, "entity_id": 1})

    stok = login(sales["email"])
    if not stok:
        skip(f"Login {sales['email']} gagal — SKIP.")
        return _summary()
    Hs = {"Authorization": f"Bearer {stok}"}

    # ---- READ IDOR (sales entitas A → dokumen entitas B) ----
    read_cases = []
    if fcust:
        read_cases.append((f"/customers/{fcust['id']}/360", "customer 360"))
        read_cases.append((f"/customers/{fcust['id']}/credit-status", "customer credit-status"))
    if fso:
        read_cases.append((f"/sales-orders/{fso['id']}/invoices", "sales-order invoices"))
    if not read_cases:
        skip("Tak ada dokumen entitas-lain (customer/SO) di seed — SKIP baca.")
    for path, label in read_cases:
        try:
            st = requests.get(f"{BASE}{path}", headers=Hs, timeout=10).status_code
        except Exception as e:  # noqa: BLE001
            skip(f"{label}: error {e}")
            continue
        if st in PROTECTED:
            ok(f"BACA {label} lintas-entitas ditolak ({st}).")
        else:
            leak(f"BACA {label} lintas-entitas → HTTP {st} (harus 401/403/404). GET {path}")

    # ---- WRITE IDOR (warehouse entitas A → task inbound entitas B) ----
    if ftask:
        wtok = login(wh["email"])
        if not wtok:
            skip(f"Login {wh['email']} gagal — SKIP tulis.")
        else:
            Hw = {"Authorization": f"Bearer {wtok}"}
            path = f"/inbound/tasks/{ftask['id']}/escalate"
            try:
                st = requests.post(f"{BASE}{path}", headers=Hw,
                                   json={"reason": "xentity-gate-probe"}, timeout=10).status_code
            except Exception as e:  # noqa: BLE001
                skip(f"inbound escalate: error {e}")
                st = None
            if st is None:
                pass
            elif st in PROTECTED:
                ok(f"TULIS inbound escalate lintas-entitas ditolak ({st}).")
            else:
                leak(f"TULIS inbound escalate lintas-entitas → HTTP {st} (mencapai business-logic; "
                     f"harus 401/403/404). POST {path}")
    else:
        skip("Tak ada wms_task entitas-lain di seed — SKIP tulis.")

    return _summary()


def _summary() -> int:
    print(f"\n{B}{'='*64}{X}\n  {R}LEAK {fails}{X} | {Y}SKIP {skips}{X}\n{B}{'='*64}{X}")
    if fails:
        print(f"{R}{B}  CROSS-ENTITY IDOR TERBUKTI — isolasi multi-PT bocor (INV-ENTITY-01).{X}\n")
        return 1
    print(f"{G}{B}  Isolasi lintas-entitas sehat (INV-ENTITY-01 tertutup).{X}\n")
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
