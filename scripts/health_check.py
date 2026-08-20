#!/usr/bin/env python3
"""
health_check.py — Kain Nusantara (KN3) Automated Health Check
=============================================================
Verifikasi SEMUA endpoint kritis: cek ISI (bukan hanya status 200).
Deteksi dini: tabel kosong, 404, 500, respons tak sesuai ekspektasi.

Kontrak KN3 (diverifikasi):
  • login → {"token": "..."}  (field token = "token", respons LANGSUNG)
  • list endpoint → ARRAY langsung; detail/dashboard → objek langsung (TANPA envelope)

Usage:
    cd /app && python scripts/health_check.py
Exit code: 1 jika ada FAIL, else 0.
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass

try:
    import httpx
except ImportError:
    os.system("pip install httpx -q"); import httpx

# API base: pakai localhost (gate jalan di host backend). Override via API_BASE.
API = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/")
ADMIN_EMAIL = os.environ.get("KN_ADMIN_EMAIL", "admin@kainnusantara.id")
ADMIN_PASS = os.environ.get("KN_ADMIN_PASS", "demo12345")

G, Y, R, C, X, B = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[0m", "\033[1m"


def color(t, c):
    return f"{c}{t}{X}"


# (path, min_items, desc)   min_items=-1 → cek status saja
CRITICAL_ENDPOINTS = [
    ("/api/",                              -1, "Health root"),
    ("/api/auth/me",                       -1, "Auth: current user"),
    ("/api/dashboard",                     -1, "Dashboard metrics"),
    ("/api/products",                       1, "Master: products"),
    ("/api/customers",                      1, "Master: customers"),
    ("/api/warehouses",                     1, "Master: warehouses"),
    ("/api/uoms",                           1, "Master: UOMs"),
    ("/api/users",                          1, "Admin: users"),
    ("/api/inventory/balances",             1, "Inventory: balances"),
    ("/api/inventory/status-board",         1, "Inventory: status board (ATP)"),
    ("/api/inventory/movements",            1, "Inventory: movements"),
    ("/api/sales-orders",                   0, "Orders: sales orders"),
    ("/api/sales-orders/stats/summary",    -1, "Orders: stats summary"),
    ("/api/purchase-orders",                0, "Procurement: purchase orders"),
    ("/api/wms/tasks",                      0, "WMS: tasks"),
    ("/api/inbound/tasks",                  0, "WMS: inbound tasks"),
    ("/api/outbound/tasks",                 0, "WMS: outbound tasks"),
    ("/api/transfers",                      0, "WMS: transfers"),
    ("/api/cycle-count/sessions",           0, "WMS: cycle count"),
    ("/api/invoices",                       0, "Finance: invoices"),
    ("/api/bank-accounts",                  0, "Finance: bank/cash accounts"),
    ("/api/document-templates",             1, "Documents: templates"),
    ("/api/audit-logs",                     0, "System: audit logs"),
    ("/api/reports/summary",               -1, "Reports: summary"),
]


def extract_count(data):
    """KN3 mengembalikan ARRAY langsung untuk list. Dukung juga dict {items/total}."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("items", "data", "rows", "results", "records", "domains", "sessions"):
            if isinstance(data.get(key), list):
                return len(data[key])
        if "total" in data and isinstance(data["total"], int):
            return data["total"]
        return -1  # objek non-list → cek status saja
    return -1


async def get_token(client):
    try:
        r = await client.post(f"{API}/api/auth/login",
                              json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return d.get("token") or (d.get("data") or {}).get("token")
        print(color(f"  LOGIN GAGAL: HTTP {r.status_code} — {r.text[:160]}", R))
    except Exception as e:
        print(color(f"  LOGIN ERROR: {e}", R))
    return None


async def check(client, token, path, min_items, desc):
    h = {"Authorization": f"Bearer {token}"}
    try:
        r = await client.get(f"{API}{path}", headers=h, timeout=15)
        sc = r.status_code
        if sc in (401, 403):
            return ("FAIL", f"Auth error HTTP {sc}", None)
        if sc >= 500:
            return ("FAIL", f"Server error HTTP {sc} — {r.text[:80]}", None)
        if sc == 404:
            return ("FAIL", "HTTP 404 Not Found", None)
        if min_items == -1:
            return ("PASS" if sc < 400 else "FAIL", "OK", "N/A")
        try:
            data = r.json()
        except Exception:
            return ("FAIL", "Respons bukan JSON", None)
        n = extract_count(data)
        if sc >= 400:
            return ("FAIL", f"HTTP {sc}", n)
        if n == 0 or (n != -1 and n < min_items):
            return ("WARN", f"{n} items (kosong — perlu seed?)", n)
        return ("PASS", f"{n} items", n)
    except httpx.TimeoutException:
        return ("FAIL", "TIMEOUT (>15s)", None)
    except Exception as e:
        return ("FAIL", str(e)[:120], None)


async def run():
    print(f"\n{B}{'='*60}{X}")
    print(color("  KN3 — HEALTH CHECK", B + C))
    print(f"  API: {API}")
    print(f"  Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{B}{'='*60}{X}")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        token = await get_token(client)
        if not token:
            print(color("FATAL: tidak bisa login.", R)); return 1
        print(color("  ✓ Login berhasil\n", G))
        p = w = f = 0
        for path, mn, desc in CRITICAL_ENDPOINTS:
            tag, detail, n = await check(client, token, path, mn, desc)
            if tag == "PASS":
                p += 1; print(f"  {color('[PASS]', G)} {path:<40} {color(detail, G)}")
            elif tag == "WARN":
                w += 1; print(f"  {color('[WARN]', Y)} {path:<40} {color(detail, Y)}  ({desc})")
            else:
                f += 1; print(f"  {color('[FAIL]', R)} {path:<40} {color(detail, R)}  ({desc})")
            await asyncio.sleep(0.05)
    print(f"\n{B}{'='*60}{X}")
    print(f"  {color('PASS', G)} {p}  |  {color('WARN', Y)} {w}  |  {color('FAIL', R)} {f}")
    print(f"{B}{'='*60}{X}")
    if f:
        print(color("\n  ACTION REQUIRED — ada endpoint FAIL (kemungkinan bug aktif).", R + B))
        print("  Cek ENGINEERING_GUARDRAILS.md RC-1..RC-3 (drift koleksi/field/respons).\n")
    elif w:
        print(color("\n  INFO — beberapa endpoint 0 items (normal bila belum di-seed).\n", Y))
    else:
        print(color("\n  SISTEM SEHAT — semua endpoint responsif dengan data.\n", G + B))
    return 1 if f else 0


if __name__ == "__main__":
    # Health check hanya MEMBACA, tetapi login-nya menulis audit_logs /
    # login_attempts. Jejak login dipulihkan agar gate INV-GATE-01 hijau.
    sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
    try:
        from _common import run_with_restore
        sys.exit(run_with_restore(lambda: asyncio.run(run()),
                                  collections=["audit_logs", "login_attempts"]))
    except ImportError:
        sys.exit(asyncio.run(run()))
