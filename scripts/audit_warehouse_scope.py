#!/usr/bin/env python3
"""GATE E4.1 — setiap endpoint TULIS yang memilih gudang wajib berpagar.

MASALAH yang dijaga: aturan "gudang khusus badan usaha" hanya sekuat titik
terlemahnya. Satu endpoint baru yang menerima `warehouse_id` tanpa memanggil
`warehouse_scope_service.assert_usable` sudah cukup untuk menaruh barang di
gudang badan usaha lain — dan justru endpoint yang terlupakan itu yang biasanya
hidup lama tanpa ketahuan.

Cara kerja (STATIK, tanpa server): baca `backend/routers/*.py` dengan AST,
temukan fungsi endpoint POST/PUT/PATCH yang menyentuh `payload.*warehouse_id`,
lalu pastikan fungsi itu memanggil `assert_usable`. Yang sengaja dibebaskan
ditulis EKSPLISIT di `EXEMPT` beserta alasannya — bukan didiamkan.

Bukti-merah: `python scripts/audit_warehouse_scope.py --self-test` menyuntik
endpoint palsu tanpa pagar dan memastikan gate MEMERAH.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "backend" / "routers"

WRITE_DECORATORS = ("post", "put", "patch")
GUARD_CALLS = ("assert_usable", "assert_many_usable")

# Dibebaskan dengan alasan per baris. Kunci = "berkas.py::nama_fungsi".
EXEMPT: dict[str, str] = {
    # Mencetak label tidak menggeser stok; gudang hanya ikut tertulis di label.
    "label_printer.py::generate_product_label":
        "hanya mencetak label — tidak membuat/menggeser stok",
    # Tag RFID menempel pada ROLL; kepemilikan roll sudah dijaga scoping entitas.
    "rfid.py::post_auto_encode":
        "tag mengikuti roll; kepemilikan roll sudah ter-scope owner_entity_id",
}


def _decorator_methods(fn: ast.AST) -> set[str]:
    out: set[str] = set()
    for dec in getattr(fn, "decorator_list", []) or []:
        call = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name) \
                and call.value.id == "router":
            out.add(call.attr)
    return out


def _touches_warehouse_payload(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and node.attr.endswith("warehouse_id") \
                and isinstance(node.value, ast.Name) and node.value.id in ("payload", "body"):
            return True
    return False


def _has_guard(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and node.attr in GUARD_CALLS:
            return True
        if isinstance(node, ast.Name) and node.id in GUARD_CALLS:
            return True
    return False


def scan_source(name: str, source: str) -> list[tuple[str, str]]:
    """→ daftar (kunci, keterangan) endpoint tulis TANPA pagar."""
    findings: list[tuple[str, str]] = []
    tree = ast.parse(source)
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        methods = _decorator_methods(fn)
        if not methods & set(WRITE_DECORATORS):
            continue
        if not _touches_warehouse_payload(fn):
            continue
        key = f"{name}::{fn.name}"
        if key in EXEMPT:
            continue
        if not _has_guard(fn):
            findings.append((key, f"memakai payload gudang tetapi tidak memanggil "
                                  f"{' / '.join(GUARD_CALLS)}"))
    return findings


def run() -> int:
    files = sorted(ROUTERS.glob("*.py"))
    findings: list[tuple[str, str]] = []
    guarded = 0
    for f in files:
        src = f.read_text()
        tree = ast.parse(src)
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and _decorator_methods(fn) & set(WRITE_DECORATORS) \
                    and _touches_warehouse_payload(fn) and _has_guard(fn):
                guarded += 1
        findings += scan_source(f.name, src)

    print("=" * 78)
    print("  GATE E4.1 — PAGAR PEMAKAIAN GUDANG PER BADAN USAHA")
    print("=" * 78)
    print(f"  {guarded} endpoint tulis berpagar · {len(EXEMPT)} dibebaskan dengan alasan")
    for key, why in EXEMPT.items():
        print(f"    - bebas: {key:52} ({why})")
    if findings:
        print(f"\n  MERAH — {len(findings)} endpoint tulis memilih gudang TANPA pagar:")
        for key, why in findings:
            print(f"    ✗ {key:56} {why}")
        print("\n  Perbaiki: panggil "
              "`await whscope.assert_usable(payload.warehouse_id, <entity_id>, action=…)`, "
              "atau daftarkan di EXEMPT beserta alasannya.")
        return 1
    print("\n  HIJAU — semua endpoint tulis pemilih gudang berpagar.")
    return 0


# ─── SELF-TEST (bukti-merah) ────────────────────────────────────────────────
FAKE_UNGUARDED = '''
@router.post("/gudang-baru-lupa-pagar")
async def simpan_sesuatu(payload, request):
    doc = {"warehouse_id": payload.warehouse_id}
    return doc
'''

FAKE_GUARDED = '''
@router.post("/gudang-baru-berpagar")
async def simpan_sesuatu(payload, request):
    await whscope.assert_usable(payload.warehouse_id, "ent_ksc")
    return {"ok": True}
'''


def self_test() -> int:
    fails = 0
    bad = scan_source("palsu.py", FAKE_UNGUARDED)
    ok = scan_source("palsu.py", FAKE_GUARDED)
    print("== SELF-TEST audit_warehouse_scope (gate harus bisa MEMERAH) ==")
    if len(bad) == 1:
        print("  [PASS] endpoint tulis tanpa pagar TERTANGKAP")
    else:
        print(f"  [FAIL] endpoint tanpa pagar TIDAK tertangkap ({bad})")
        fails += 1
    if not ok:
        print("  [PASS] endpoint berpagar tidak salah-tuduh")
    else:
        print(f"  [FAIL] endpoint berpagar salah dituduh ({ok})")
        fails += 1
    rc = run()
    if rc == 0:
        print("  [PASS] kode nyata saat ini HIJAU")
    else:
        print("  [FAIL] kode nyata saat ini MERAH")
        fails += 1
    print(f"\n  {'HIJAU — gate terbukti bisa memerah.' if not fails else f'MERAH — {fails} kasus gagal.'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else run())
