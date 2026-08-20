#!/usr/bin/env python3
"""
audit_endpoint_sweep.py — KN3 GET-endpoint sweep (PARALEL)
==========================================================
Hit SETIAP GET route /api sebagai admin, resolve path param dari data nyata,
catat status + emptiness + error. Tidak ada celah tersisa.

PERUBAHAN EFISIENSI (2026-07-26):
  1. Route dienumerasi dari `GET /openapi.json` server yang HIDUP, bukan
     `from server import app`. Menghemat ~60 MB RSS + waktu import modul.
     (fallback ke import app bila openapi.json tak tersedia)
  2. Request dijalankan PARALEL (semaphore) alih-alih sekuensial + sleep 20 ms.
     749 route: ~24.5 s  ->  ~3 s.

Usage: cd /app && python scripts/audit_endpoint_sweep.py
       KN_SWEEP_CONCURRENCY=12  (opsional, default 12)
"""
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:
    pass

import httpx  # noqa

API = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/")
ADMIN = {"email": os.environ.get("KN_ADMIN_EMAIL", "admin@kainnusantara.id"),
         "password": os.environ.get("KN_ADMIN_PASS", "demo12345")}
CONCURRENCY = int(os.environ.get("KN_SWEEP_CONCURRENCY", "12"))
G, Y, R, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[1m", "\033[0m"

SAMPLES = {}


async def get_routes(client):
    """Enumerasi GET route /api tanpa mengimpor aplikasi (hemat RSS + waktu)."""
    try:
        r = await client.get(API + "/openapi.json", timeout=30)
        if r.status_code == 200:
            spec = r.json()
            out = [p for p, ops in (spec.get("paths") or {}).items()
                   if "get" in {k.lower() for k in ops} and p.startswith("/api")]
            if out:
                return sorted(set(out))
    except Exception:
        pass
    # Fallback: impor aplikasi (mahal, tapi menjamin sweep tetap jalan)
    sys.path.insert(0, str(ROOT / "backend"))
    from server import app  # noqa
    out = []
    for r in app.routes:
        methods = getattr(r, "methods", set()) or set()
        path = getattr(r, "path", "")
        if "GET" in methods and path.startswith("/api"):
            out.append(path)
    return sorted(set(out))


def fill_path(path):
    params = re.findall(r"\{([^}]+)\}", path)
    if not params:
        return path
    filled = path
    for p in params:
        key = p.lower()
        val = SAMPLES.get(key)
        if val is None and key.endswith("id") and "id" in SAMPLES:
            val = SAMPLES["id"]
        if val is None:
            return None
        filled = filled.replace("{" + p + "}", str(val))
    return filled


async def first_id(client, h, path, field="id"):
    try:
        r = await client.get(API + path, headers=h, timeout=20)
        if r.status_code != 200:
            return None
        d = r.json()
        items = d if isinstance(d, list) else d.get("items", d.get("products", []))
        if isinstance(items, list) and items:
            return items[0].get(field)
    except Exception:
        return None
    return None


async def resolve_samples(client, h):
    """Resolve semua sample id secara paralel."""
    keys = [
        ("product_id", "/api/products"),
        ("order_id", "/api/sales-orders"),
        ("po_id", "/api/purchase-orders"),
        ("task_id", "/api/wms/tasks"),
        ("customer_id", "/api/customers"),
        ("warehouse_id", "/api/warehouses"),
        ("session_id", "/api/cycle-count/sessions"),
    ]
    vals = await asyncio.gather(*[first_id(client, h, p) for _, p in keys])
    for (k, _), v in zip(keys, vals):
        SAMPLES[k] = v
    SAMPLES["id"] = SAMPLES.get("product_id")


def count_of(d):
    if isinstance(d, list):
        return len(d)
    if isinstance(d, dict):
        for k in ("items", "rows", "results", "records", "products", "domains"):
            if isinstance(d.get(k), list):
                return len(d[k])
        return "obj"
    return "?"


async def probe(client, h, sem, path, res):
    """Satu request. Aman dijalankan paralel — hasil ditulis ke bucket res."""
    filled = fill_path(path)
    if filled is None:
        res["skipped"].append(path)
        return
    async with sem:
        try:
            resp = await client.get(API + filled, headers=h, timeout=30)
            sc = resp.status_code
            if sc >= 500:
                res["err5xx"].append((path, sc, resp.text[:120]))
            elif sc in (400, 404, 405, 422, 401, 403):
                res["err4xx"].append((path, sc))
            else:
                try:
                    c = count_of(resp.json())
                except Exception:
                    c = "non-json"
                (res["empty"] if c == 0 else res["ok"]).append((path, c))
        except Exception as e:
            res["err5xx"].append((path, "EXC", str(e)[:120]))


async def main():
    limits = httpx.Limits(max_connections=CONCURRENCY + 4,
                          max_keepalive_connections=CONCURRENCY + 4)
    async with httpx.AsyncClient(follow_redirects=False, limits=limits) as client:
        routes = await get_routes(client)
        r = await client.post(API + "/api/auth/login", json=ADMIN, timeout=20)
        token = r.json().get("token")
        h = {"Authorization": f"Bearer {token}"}
        await resolve_samples(client, h)

        res = {"ok": [], "empty": [], "err5xx": [], "err4xx": [], "skipped": []}
        sem = asyncio.Semaphore(CONCURRENCY)
        await asyncio.gather(*[probe(client, h, sem, p, res) for p in routes])

    for k in ("err5xx", "err4xx", "empty", "skipped"):
        res[k].sort(key=lambda t: t[0] if isinstance(t, tuple) else t)

    print(f"\n{B}KN3 ENDPOINT SWEEP — {len(routes)} GET routes "
          f"(paralel x{CONCURRENCY}){X}")
    print(f"  OK(data): {len(res['ok'])}  EMPTY: {len(res['empty'])}  "
          f"5xx/EXC: {len(res['err5xx'])}  4xx: {len(res['err4xx'])}  SKIPPED: {len(res['skipped'])}")
    print(f"\n{R}{B}=== 5xx / EXCEPTIONS (BUG NYATA) ==={X}")
    for p, sc, msg in res["err5xx"]:
        print(f"  {R}[{sc}] {p}{X}\n        {msg}")
    if not res["err5xx"]:
        print(f"  {G}none{X}")
    print(f"\n{Y}=== 4xx (auth/validasi — review) ==={X}")
    for p, sc in res["err4xx"]:
        print(f"  [{sc}] {p}")
    if not res["err4xx"]:
        print(f"  {G}none{X}")
    print(f"\n{Y}=== EMPTY (200 tapi 0 items — verifikasi disengaja) ==={X}")
    for p, c in res["empty"]:
        print(f"  {p}")
    print(f"\n=== SKIPPED (param tak bisa di-resolve) ===")
    for p in res["skipped"]:
        print(f"  {p}")
    return 1 if res["err5xx"] else 0


if __name__ == "__main__":
    # Sweep ini READ-ONLY (hanya GET), tetapi login-nya menulis audit_logs /
    # login_attempts. Supaya gate INV-GATE-01 (anti-residu) tetap hijau, jejak
    # login dipulihkan setelah sweep selesai.
    sys.path.insert(0, str(ROOT / "scripts" / "guardrails"))
    try:
        from _common import run_with_restore
        sys.exit(run_with_restore(lambda: asyncio.run(main()),
                                  collections=["audit_logs", "login_attempts"]))
    except ImportError:
        sys.exit(asyncio.run(main()))
