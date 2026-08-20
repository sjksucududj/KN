#!/usr/bin/env python3
"""
verify_api_contract.py — KN3 FE↔BE Contract Gate (menutup blindspot v1)
=======================================================================
Gate v1 (verify_data_integrity) BUTA terhadap drift FIELD NON-NUMERIK & drift
ENDPOINT. Gate ini menutupnya — 3 cek yang masing-masing bisa GAGAL:

  CHECK A — Duplicate route          (G2)  : FastAPI diam-diam pakai definisi
            TERAKHIR. Bug nyata: GET /sales-orders ganda → filter mati.
  CHECK B — FE call → route exist    (G2b) : FE memanggil endpoint yang tidak
            terdaftar (typo path) → 404 senyap.
  CHECK C — FE field ⊆ BE response   (G1)  : FE membaca `order.shipping_city`
            yang TIDAK PERNAH dikembalikan BE → label kosong tanpa error.
            (Inilah kelas bug yang lolos di v1: qty, sales_name, shipping_city,
             reservation_expires_at, item.id.)

Usage:
    cd /app && python scripts/verify_api_contract.py
    python scripts/verify_api_contract.py --check C   # satu cek saja
Exit 0 = lulus. !=0 = ada ERROR (blokir).
"""
import argparse
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
sys.path.insert(0, str(ROOT / "backend"))

SRC = ROOT / "frontend" / "src"
API = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/")
ADMIN = {"email": os.environ.get("KN_ADMIN_EMAIL", "admin@kainnusantara.id"),
         "password": os.environ.get("KN_ADMIN_PASS", "demo12345")}
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

errors = 0
warns = 0


def err(msg, detail=""):
    global errors
    errors += 1
    print(f"  {R}[ERROR]{X} {msg}" + (f"\n          {R}{detail}{X}" if detail else ""))


def warn(msg, detail=""):
    global warns
    warns += 1
    print(f"  {Y}[WARN]{X} {msg}" + (f"  {Y}{detail}{X}" if detail else ""))


def ok(msg):
    print(f"  {G}[OK]{X} {msg}")


# ── CHECK A: duplicate routes ────────────────────────────────────────────────
def check_duplicate_routes():
    print(f"\n{C}{B}CHECK A — Duplicate route (FastAPI pakai definisi TERAKHIR){X}")
    from server import app
    from collections import Counter, defaultdict
    seen = Counter()
    names = defaultdict(list)
    for r in app.routes:
        for m in (getattr(r, "methods", set()) or set()):
            if m in ("HEAD", "OPTIONS"):
                continue
            key = (m, getattr(r, "path", ""))
            seen[key] += 1
            names[key].append(getattr(r, "name", "?"))
    dups = [(k, v) for k, v in seen.items() if v > 1]
    if dups:
        for (m, p), c in dups:
            err(f"Duplicate route {m} {p} (x{c}) — handler: {names[(m, p)]}",
                "Definisi pertama TIDAK PERNAH dipanggil (mis. filter mati).")
    else:
        ok(f"Tidak ada duplicate route ({len(seen)} route unik).")


# ── Ekstraksi route backend & path FE ────────────────────────────────────────
def backend_routes():
    from server import app
    out = []
    for r in app.routes:
        methods = {m for m in (getattr(r, "methods", set()) or set()) if m not in ("HEAD", "OPTIONS")}
        path = getattr(r, "path", "")
        if path.startswith("/api") and methods:
            out.append((methods, path))
    return out


def route_regex(path):
    # /api/transfers/{transfer_id}/approve -> regex
    pat = re.sub(r"\{[^}]+\}", r"[^/]+", path)
    return re.compile("^" + pat + "$")


FE_CALL_RE = re.compile(
    r'''axios\.(get|post|patch|put|delete)\(\s*`([^`]+)`'''
    r'''|fetch\(\s*`([^`]+)`'''
)

# Var query-string yang harus DIBUANG (bukan path segment)
QUERY_VAR_RE = re.compile(r'\$\{[a-zA-Z_]*(?:params|query|qs|search)\}', re.I)


def file_api_is_bare(text):
    """True bila file mendefinisikan `const API = process.env.REACT_APP_BACKEND_URL`
    (TANPA /api). Maka `${API}` → '' dan '/api' ada di literal.
    Bila tidak (impor dari apiClient), `${API}` → '/api'."""
    return bool(re.search(r'const\s+API\s*=\s*process\.env\.REACT_APP_BACKEND_URL', text))


def normalize_fe_path(raw, api_is_bare):
    p = raw.strip()
    # 1) buang query-string templated (?...) & ${params}
    p = QUERY_VAR_RE.sub("", p)
    p = p.split("?")[0]
    # 2) resolve ${API}/${BACKEND_URL}/${BASE}
    if api_is_bare:
        p = p.replace("${API}", "").replace("${BACKEND_URL}", "")
    else:
        p = p.replace("${API}", "/api").replace("${BACKEND_URL}/api", "/api").replace("${BACKEND_URL}", "")
    p = p.replace("${BASE}", "/api")
    # 3) sisa ${...} = path param → wildcard
    p = re.sub(r"\$\{[^}]+\}", "{p}", p)
    # 4) bersihkan
    p = re.sub(r"/{2,}", "/", p).rstrip("/") or "/"
    return p


def fe_calls():
    calls = []
    for f in SRC.rglob("*.jsx"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        bare = file_api_is_bare(text)
        for m in FE_CALL_RE.finditer(text):
            method = (m.group(1) or "get").upper()
            raw = m.group(2) or m.group(3) or ""
            if "/api" not in raw and "${API}" not in raw:
                continue
            calls.append((method, normalize_fe_path(raw, bare), raw.strip(), f.relative_to(SRC)))
    return calls


# ── CHECK B: FE call → route exist ───────────────────────────────────────────
def check_fe_routes():
    print(f"\n{C}{B}CHECK B — FE call → endpoint backend terdaftar?{X}")
    routes = backend_routes()
    compiled = [(methods, route_regex(p), p) for methods, p in routes]
    # Backend path dengan param → token "X" (untuk pencocokan BALIK: FE `${action}`
    # dinamis, mis. `/work-orders/${wo.id}/${action}` di mana action ∈ release|complete|cancel.
    # Tanpa arah-balik ini gate memberi false-positive yang mengikis kepercayaan.)
    backend_tokens = [re.sub(r"\{[^}]+\}", "X", p) for _, p in routes]
    calls = fe_calls()
    bad = 0
    seen = set()
    for method, fe_path, raw, src in calls:
        if fe_path in seen:
            continue
        test = fe_path.replace("{p}", "X")
        # Cek EKSISTENSI PATH (lintas-method): kegagalan nyata = path typo → 404.
        # Method tidak dipakai sbg syarat karena fetch() menaruh method di arg-opsi
        # (tak terlihat regex) → menghindari false-positive yang mengikis kepercayaan gate.
        matched = any(rx.match(test) for _, rx, _ in compiled)
        if not matched:
            fe_rx = route_regex(fe_path.replace("{p}", "{v}"))
            matched = any(fe_rx.match(bt) for bt in backend_tokens)
        if not matched:
            seen.add(fe_path)
            bad += 1
            err(f"FE {fe_path} → TIDAK ada route backend (path) yang cocok",
                f"src: {src}  raw: {raw[:60]}")
    if bad == 0:
        ok(f"Semua {len(set(c[1] for c in calls))} path API FE unik cocok dengan route backend.")


# ── CHECK C: FE field ⊆ BE response ──────────────────────────────────────────
# Binding: file FE → endpoint sampel → variabel yang merepresentasikan objek/itemnya.
# Tambah binding saat menambah komponen yang membaca data API (ini KONTRAK executable).
BINDINGS = [
    {"file": "features/orders/OrdersView.jsx", "endpoint": "/api/sales-orders",
     "obj_vars": ["o", "sel", "order"], "item_var": "item",
     "conditional": {"reservation_expires_at", "shipping_city"}},
    {"file": "features/wms/InventoryStockView.jsx", "endpoint": "/api/inventory/balances",
     "obj_vars": ["b", "bal", "balance", "row"], "item_var": None, "conditional": set()},
]

JS_NOISE = {
    "map", "filter", "find", "findIndex", "some", "every", "includes", "reduce",
    "forEach", "slice", "splice", "sort", "join", "indexOf", "replace", "trim",
    "split", "toString", "toLowerCase", "toUpperCase", "push", "pop", "concat",
    "length", "keys", "values", "entries", "match", "padStart", "padEnd",
    "toLocaleString", "toFixed", "charAt", "startsWith", "endsWith", "then",
    "catch", "finally", "props", "current", "target", "value", "id",  # id dicek terpisah
    "data", "response", "status_text", "statusText", "headers", "config",  # artefak HTTP/axios
}


def extract_field_reads(text, varname):
    fields = set()
    for m in re.finditer(rf"\b{re.escape(varname)}\.([A-Za-z_][A-Za-z0-9_]*)", text):
        fld = m.group(1)
        if fld not in JS_NOISE:
            fields.add(fld)
    # optional chaining var?.field
    for m in re.finditer(rf"\b{re.escape(varname)}\?\.([A-Za-z_][A-Za-z0-9_]*)", text):
        fld = m.group(1)
        if fld not in JS_NOISE:
            fields.add(fld)
    return fields


async def check_field_contract():
    print(f"\n{C}{B}CHECK C — Field yang DIBACA FE ada di respons BE?{X}")
    try:
        import httpx
    except ImportError:
        os.system("pip install httpx -q"); import httpx
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.post(f"{API}/api/auth/login", json=ADMIN, timeout=20)
        token = r.json().get("token")
        h = {"Authorization": f"Bearer {token}"}
        for bnd in BINDINGS:
            fpath = SRC / bnd["file"]
            if not fpath.exists():
                warn(f"binding di-skip, file tidak ada: {bnd['file']}"); continue
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            resp = await client.get(f"{API}{bnd['endpoint']}", headers=h, timeout=25)
            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", [])
            if not items:
                warn(f"{bnd['file']}: endpoint {bnd['endpoint']} kosong — cek di-skip"); continue
            n = len(items)

            # object-level fields
            obj_fields = set()
            for v in bnd["obj_vars"]:
                obj_fields |= extract_field_reads(text, v)
            for fld in sorted(obj_fields):
                present = sum(1 for it in items if isinstance(it, dict) and fld in it)
                if present == 0:
                    (warn if fld in bnd["conditional"] else err)(
                        f"{bnd['file']}: FE baca `{bnd['obj_vars'][0]}.{fld}` tapi 0/{n} item BE punya field itu",
                        "→ label/nilai akan KOSONG (FE↔BE field drift)")
                elif present < n:
                    if fld not in bnd["conditional"]:
                        warn(f"{bnd['file']}: `{fld}` hanya ada di {present}/{n} item (kondisional?)")

            # item-level fields (list di dalam objek, mis. order.items[])
            if bnd.get("item_var"):
                item_fields = extract_field_reads(text, bnd["item_var"])
                sub = []
                for it in items:
                    for key in ("items", "lines", "details"):
                        if isinstance(it.get(key), list):
                            sub.extend(it[key])
                if sub:
                    for fld in sorted(item_fields):
                        present = sum(1 for s in sub if isinstance(s, dict) and fld in s)
                        if present == 0:
                            err(f"{bnd['file']}: FE baca `{bnd['item_var']}.{fld}` tapi 0/{len(sub)} sub-item punya",
                                "→ kolom item akan KOSONG")
            if not obj_fields:
                warn(f"{bnd['file']}: tidak ada field-read terdeteksi (cek binding obj_vars)")
            else:
                ok(f"{bnd['file']}: {len(obj_fields)} field FE dicek vs {bnd['endpoint']}")


async def _amain(which):
    if which in (None, "A"):
        check_duplicate_routes()
    if which in (None, "B"):
        check_fe_routes()
    if which in (None, "C"):
        await check_field_contract()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", choices=["A", "B", "C"])
    args = ap.parse_args()
    print(f"{B}{C}{'='*64}{X}")
    print(f"{B}  KN3 — FE↔BE CONTRACT GATE  (API={API}){X}")
    print(f"{B}{C}{'='*64}{X}")
    import asyncio
    asyncio.run(_amain(args.check))
    print(f"\n{B}{'='*64}{X}")
    print(f"  {R}ERROR {errors}{X}  |  {Y}WARN {warns}{X}")
    if errors:
        print(f"  {R}{B}CONTRACT VIOLATION — FE & BE tidak sinkron. Perbaiki sebelum lanjut.{X}\n")
        return 1
    print(f"  {G}{B}FE↔BE CONTRACT OK.{X}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
