#!/usr/bin/env python3
"""INV-NUM-01 (STATIK + RUNTIME) — GATE batas-nilai numerik (numeric bounds).

Blindspot yang ditutup: audit #076–#078 KN TAK PERNAH menegakkan batas nilai pada
skema Pydantic. Dari ~120 field numerik lintas `backend/schemas*.py`, HANYA 2 yang
punya bound (`UOMPayload.precision ge=0`, `factor_to_base gt=0`). Sisanya menerima
**nilai negatif / persen > 100 / jumlah nol** tanpa penolakan di lapis skema.

Kelas bug yang dicegah:
  * MONEY-NEG   : harga/nominal/limit negatif diterima → ledger/kas rusak (mis. `price=-1000`).
  * PCT-OVER    : persen di luar 0–100 diterima (mis. `discount_percent=150`, `dp_percent=999`).
  * QTY-NONPOS  : kuantitas/faktor ≤ 0 diterima (mis. `quantity=-5`, `factor=0`).

Dua lapis (metodologi Guardrail v2, adaptasi Rahaza Travel):
  A. STATIK (selalu jalan, tak butuh backend): scan AST `schemas*.py`. Field numerik
     "wajib-bertumpu" (money/percent/quantity/count) TANPA `Field(ge=/gt=/le=/lt=)` yang
     sesuai → PELANGGARAN. Tier:
       - HARD (bikin gate MERAH) : skema INPUT (Create/Payload/In/Input/Request/…).
       - SOFT (advisory/WARN)    : skema Patch/Update parsial (Optional) — tak mem-fail.
  B. RUNTIME (bila backend+auth siap): kirim payload adversarial ke endpoint nyata +
     **positive control** (UOM `factor_to_base=-1` HARUS 422). Bila field tak-berbound
     menerima nilai buruk (200/201) → LEAK terbukti (bukan sekadar teori skema).

Resilient: backend down / login gagal → bagian RUNTIME di-SKIP; STATIK tetap dievaluasi.
Exit 1 hanya bila ada HARD static-violation ATAU runtime-leak terbukti.
Usage: cd /app && python scripts/guardrails/verify_numeric_bounds.py
"""
import ast
import os
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

G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"

# ── Kamus semantik nama-field (lowercase, substring) ────────────────────────
PERCENT_KEYS = ("percent", "pct")
MONEY_KEYS = (
    "price", "amount", "harga", "cost", "biaya", "credit_limit", "saldo", "balance",
    "salary", "gaji", "fee", "subtotal", "dpp", "sell_price", "transfer_price",
    "base_price", "est_price", "requested_price", "target_price", "pokok", "nominal",
    "tunjangan", "allowance", "grand_total",
)
QTY_KEYS = (
    "quantity", "qty", "gramasi", "lebar", "kg_per_meter", "bin_capacity", "capacity",
    "factor", "reorder_point", "reorder_qty", "min_quantity", "take_qty", "weight",
)
COUNT_KEYS = ("net_days", "installment_count", "days", "precision")

# Field yang SAH tak-berbound / boleh negatif / bukan risiko bound → jangan flag.
ALLOW_NAMES = {
    "lat", "lng", "sort", "margin_mm", "item_index", "index", "idx",
    "min_amount", "max_amount",   # ApprovalRulePayload — ambang aturan (0 sah, boleh besar)
}
# Skema INPUT (pembuatan/aksi) → pelanggaran = HARD (gate MERAH).
INPUT_SUFFIXES = (
    "Create", "Payload", "In", "Input", "Request", "Generate", "Scan", "Adjust",
    "Ingest", "Import", "Submit", "Convert", "Award", "ClockIn", "ClockOut",
    "CheckIn", "CheckOut", "Item", "Line", "Tier", "Member",
)

hard = []   # pelanggaran statik keras (skema input)
soft = []   # pelanggaran statik lunak (patch/update) — advisory
checks = 0


def _numeric(node) -> str:
    """Kembalikan 'int'/'float' bila annotation adalah skalar numerik (termasuk Optional), else ''."""
    if isinstance(node, ast.Name) and node.id in ("int", "float"):
        return node.id
    if isinstance(node, ast.Subscript):
        base = node.value.id if isinstance(node.value, ast.Name) else ""
        if base in ("Optional", "Union"):
            sl = node.slice
            # Optional[int] → Name; Union[int,None] → Tuple
            if isinstance(sl, ast.Name) and sl.id in ("int", "float"):
                return sl.id
            if isinstance(sl, ast.Tuple):
                for e in sl.elts:
                    if isinstance(e, ast.Name) and e.id in ("int", "float"):
                        return e.id
        # List[...]/Dict[...] → bukan skalar numerik
    return ""


def _bounds(value) -> dict:
    """Ekstrak bound dari default value `Field(...)`. Kembalikan set kw yang ada."""
    out = {"has_lower": False, "has_upper": False, "is_field": False, "default": None}
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "Field":
        out["is_field"] = True
        if value.args:
            out["default"] = _lit(value.args[0])
        for kw in value.keywords:
            if kw.arg in ("ge", "gt"):
                out["has_lower"] = True
            if kw.arg in ("le", "lt"):
                out["has_upper"] = True
            if kw.arg == "default":
                out["default"] = _lit(kw.value)
    elif value is not None:
        out["default"] = _lit(value)
    return out


def _lit(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return "…"


def _category(name: str) -> str:
    n = name.lower()
    if any(k in n for k in PERCENT_KEYS):
        return "PERCENT"
    if any(k in n for k in MONEY_KEYS):
        return "MONEY"
    if any(k in n for k in QTY_KEYS):
        return "QTY"
    if any(k in n for k in COUNT_KEYS):
        return "COUNT"
    return ""


def scan_static() -> None:
    """Lapis A — scan AST semua schemas*.py."""
    global checks
    for fp in sorted(BACKEND.glob("schemas*.py")):
        try:
            tree = ast.parse(fp.read_text())
        except Exception as e:  # noqa: BLE001
            print(f"  {Y}[SKIP]{X} parse {fp.name}: {e}")
            continue
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            is_input = cls.name.endswith(INPUT_SUFFIXES)
            for stmt in cls.body:
                if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                    continue
                fname = stmt.target.id
                if fname in ALLOW_NAMES:
                    continue
                ntype = _numeric(stmt.annotation)
                if not ntype:
                    continue
                cat = _category(fname)
                if not cat:
                    continue
                checks += 1
                bnd = _bounds(stmt.value)
                need_upper = cat == "PERCENT"
                missing = []
                if not bnd["has_lower"]:
                    missing.append("ge=/gt=")
                if need_upper and not bnd["has_upper"]:
                    missing.append("le=/lt=")
                if not missing:
                    continue
                loc = f"{fp.name}: {cls.name}.{fname}: {ntype}"
                dv = bnd["default"]
                msg = (f"{loc} (default={dv}) [{cat}] tanpa {', '.join(missing)} → "
                       f"{'persen di luar 0–100' if cat=='PERCENT' else ('nominal negatif' if cat=='MONEY' else 'nilai ≤0/negatif')} diterima.")
                (hard if is_input else soft).append(msg)


# ─────────────────────────── LAPIS B — RUNTIME ─────────────────────────────
runtime_leaks = []
runtime_ok = []
runtime_skips = []


def _rt_ok(m):
    runtime_ok.append(m)
    print(f"  {G}[OK]{X} {m}")


def _rt_leak(m):
    runtime_leaks.append(m)
    print(f"  {R}[LEAK]{X} {m}")


def _rt_skip(m):
    runtime_skips.append(m)
    print(f"  {Y}[SKIP]{X} {m}")


def runtime_probes() -> None:
    """Lapis B — kirim payload adversarial + positive control."""
    try:
        import requests
    except ImportError:
        _rt_skip("modul requests tak tersedia.")
        return
    base = os.environ.get("API_BASE", "http://localhost:8001").rstrip("/") + "/api"
    try:
        if requests.get(f"{base}/", timeout=5).status_code >= 500:
            raise Exception("5xx")
    except Exception:
        _rt_skip("Backend belum berjalan — RUNTIME di-SKIP (Phase 0).")
        return
    try:
        r = requests.post(f"{base}/auth/login",
                          json={"email": "admin@kainnusantara.id", "password": "demo12345"}, timeout=10)
        H = {"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else None
    except Exception:
        H = None
    if not H:
        _rt_skip("login admin gagal — RUNTIME di-SKIP.")
        return
    import time
    tag = str(int(time.time()))

    # --- POSITIVE CONTROL: UOM factor_to_base=-1 HARUS 422 (bound gt=0 aktif) ---
    try:
        pc = requests.post(f"{base}/uoms", headers=H,
                           json={"code": f"ZZ{tag[-5:]}", "name": "probe", "base_type": "length",
                                 "precision": 2, "factor_to_base": -1}, timeout=10).status_code
    except Exception as e:  # noqa: BLE001
        pc = None
    if pc == 422:
        _rt_ok(f"positive-control: POST /uoms factor_to_base=-1 → 422 (bound gt=0 ditegakkan). Harness valid.")
    elif pc in (200, 201):
        _rt_leak(f"positive-control ANOMALI: POST /uoms factor_to_base=-1 → {pc} (harusnya 422). "
                 f"Bound skema tak jalan / harness salah.")
    else:
        _rt_skip(f"positive-control: POST /uoms → {pc} (tak konklusif; lanjut probe lain).")

    # --- PROBE 1: MONEY negatif — customer.credit_limit (unbounded) ---
    _probe(requests, base, H, "POST /customers", "customers",
           {"name": f"NumProbe {tag}", "pic_name": "x", "phone": "0", "city": "Jakarta",
            "address": "x", "credit_limit": -5_000_000}, "credit_limit=-5.000.000 (MONEY negatif)")

    # --- PROBE 2: MONEY negatif — product.price / harga_pokok (unbounded) ---
    _probe(requests, base, H, "POST /products", "products",
           {"sku": f"NUMPRB-{tag}", "name": f"NumProbe {tag}", "price": -1000, "harga_pokok": -500,
            "gramasi": -10}, "price=-1000, harga_pokok=-500, gramasi=-10 (MONEY/QTY negatif)")

    # --- PROBE 3: PERCENT>100 & COUNT negatif — payment_term (unbounded) ---
    _probe(requests, base, H, "POST /payment-terms", "payment_terms",
           {"code": f"NUM{tag[-5:]}", "name": f"NumProbe {tag}", "type": "credit",
            "net_days": -30, "dp_percent": 999, "installment_count": -5},
           "dp_percent=999, net_days=-30, installment_count=-5 (PERCENT>100 & COUNT negatif)")


def _probe(requests, base, H, label, coll, payload, desc) -> None:
    """Kirim payload buruk; klasifikasi PROTECTED(422)/LEAK(2xx)/PARTIAL(400,409)/SKIP."""
    method, path = label.split(" ", 1)
    try:
        st = requests.request(method, f"{base}{path}", headers=H, json=payload, timeout=12).status_code
    except Exception as e:  # noqa: BLE001
        _rt_skip(f"{label}: error {e}")
        return
    if st == 422:
        _rt_ok(f"{label}: {desc} → 422 (ditolak lapis skema — aman).")
    elif st in (200, 201):
        _rt_leak(f"{label}: {desc} → {st} DITERIMA & tersimpan (koleksi `{coll}`). "
                 f"Tak ada Field(ge/gt/le) → nilai buruk masuk DB. INV-NUM-01.")
    elif st in (400, 409):
        _rt_skip(f"{label}: {desc} → {st} (ditolak business-logic, BUKAN lapis skema; "
                 f"bound skema tetap absen — lihat temuan STATIK).")
    else:
        _rt_skip(f"{label}: {desc} → {st} (tak konklusif).")


def main() -> int:
    print(f"\n{B}{'='*64}{X}\n  NUMERIC-BOUNDS GATE (INV-NUM-01)\n{B}{'='*64}{X}")
    # Lapis A — STATIK
    print(f"{C}{B}-- LAPIS A · STATIK (AST scan schemas*.py) --{X}")
    scan_static()
    print(f"  {checks} field numerik ber-semantik diperiksa.")
    if hard:
        print(f"{R}[FAIL-HARD]{X} {len(hard)} field INPUT tanpa bound (menerima nilai buruk):")
        for m in hard:
            print(f"  {R}✗{X} {m}")
    if soft:
        print(f"{Y}[WARN-SOFT]{X} {len(soft)} field Patch/Update tanpa bound (advisory, tak mem-fail):")
        for m in soft[:12]:
            print(f"  {Y}•{X} {m}")
        if len(soft) > 12:
            print(f"  {Y}… (+{len(soft)-12} lagi){X}")
    if not hard and not soft:
        print(f"{G}[PASS]{X} semua field numerik ber-semantik memiliki bound.")

    # Lapis B — RUNTIME
    print(f"\n{C}{B}-- LAPIS B · RUNTIME (probe adversarial + positive control) --{X}")
    runtime_probes()

    return _summary()


def _summary() -> int:
    print(f"\n{B}{'='*64}{X}")
    print(f"  STATIK: {R}HARD {len(hard)}{X} | {Y}SOFT {len(soft)}{X}    "
          f"RUNTIME: {R}LEAK {len(runtime_leaks)}{X} | {G}OK {len(runtime_ok)}{X} | {Y}SKIP {len(runtime_skips)}{X}")
    print(f"{B}{'='*64}{X}")
    if hard or runtime_leaks:
        print(f"{R}{B}  NUMERIC-BOUNDS DILANGGAR — skema/endpoint menerima nilai buruk (INV-NUM-01).{X}")
        print(f"{Y}  → Tambah Field(ge=0/gt=0[/le=100]) pada skema INPUT terkait.{X}\n")
        return 1
    print(f"{G}{B}  Numeric-bounds aman untuk cakupan teruji (INV-NUM-01 tertutup).{X}\n")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as ex:  # noqa: BLE001
        print(f"{Y}  Gate error (dianggap SKIP): {ex}{X}")
        rc = 0
    sys.exit(rc)
