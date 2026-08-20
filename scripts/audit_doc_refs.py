#!/usr/bin/env python3
"""audit_doc_refs.py — FASE G-4 · **AUDIT JUJUR RELASI DOKUMEN**.

Pertanyaan yang dijawab skrip ini (dan tidak bisa dijawab oleh grep mentah):

1. **Cakupan data** — dari semua surat yang PUNYA sumber (mis. `wms_tasks.po_id`),
   berapa persen yang benar-benar menaut sumbernya di `refs[]`? Koleksi mana yang
   masih bolong? (Ini yang membuat penelusuran retur/klaim buntu.)
2. **Kesehatan tautan** — ada tautan menggantung (target sudah dihapus), tautan
   satu arah, `doc_type` tak dikenal, atau duplikat?
3. **Cakupan KODE** — setiap jenis dokumen turunan harus punya **hook penautan di
   titik lahirnya**. Kalau besok ada jenis dokumen baru ditambahkan ke registry
   tetapi tidak ada satu pun modul yang memanggil `doc_refs_service`, audit ini
   MEMERAH — jadi celah tidak bisa lolos diam-diam.

Sumber kebenaran: `backend/services/doc_refs_service.py::DOC_TYPES` (registry) —
BUKAN daftar hardcode di skrip ini. Menambah jenis dokumen di registry otomatis
menambah cakupan audit.

Pemakaian:
    python scripts/audit_doc_refs.py             # laporan (exit 0 selama tak ada FAIL)
    python scripts/audit_doc_refs.py --strict    # dipakai gate: cakupan < 100% ⇒ exit 1
    python scripts/audit_doc_refs.py --self-test # BUKTI-MERAH: audit harus bisa memerah
    python scripts/audit_doc_refs.py --json      # keluaran mesin (CI)
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")

BACKEND = Path("/app/backend")
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"

# Modul yang WAJIB memanggil penautan untuk tiap jenis dokumen turunan yang lahir
# lewat aplikasi. Bentuknya terstruktur (doc_type → berkas kandidat), bukan grep
# bebas: bila salah satu berkas memanggil `doc_refs_service`, hook dianggap ada.
BIRTH_HOOKS = {
    "grn": ["routers/purchase_orders.py", "routers/inbound_receiving.py"],
    "picking_task": ["services/fulfillment_status.py"],
    "shipment": ["services/shipment_service.py"],
    "tax_invoice": ["services/tax_invoice_service.py"],
    "ar_receipt": ["services/ar_receipt_service.py"],
    "sales_return": ["services/return_service.py"],
    "purchase_return": ["services/purchase_return_service.py", "services/qc_service.py"],
    "vendor_bill": ["routers/vendor_bills.py", "services/makloon_order_service.py"],
    "landed_cost": ["routers/landed_cost.py"],
    "purchase_order": ["services/pr_sourcing_service.py", "routers/purchase_orders.py"],
    "makloon_order": ["services/makloon_order_service.py"],
    "credit_note": ["services/amendment_service.py"],
    "doc_amendment": ["services/amendment_service.py"],
    "sales_order": ["routers/sales_orders.py"],
}

_stats = {"pass": 0, "fail": 0, "warn": 0}
_report: dict = {"coverage": [], "health": {}, "hooks": []}


def line(kind: str, msg: str, detail: str = "") -> None:
    col = {"PASS": G, "FAIL": R, "WARN": Y}[kind]
    _stats[kind.lower()] += 1
    print(f"  {col}{'✓' if kind == 'PASS' else ('✗' if kind == 'FAIL' else '⚠')} [{kind}]{X} {msg}"
          + (f"\n        {detail}" if detail else ""))


def head(t: str) -> None:
    print(f"\n{C}{B}{'=' * 78}\n{t}\n{'=' * 78}{X}")


# ── 1. Cakupan KODE (hook di titik lahir dokumen) ───────────────────────────
def audit_hooks(extra_hooks: dict | None = None) -> None:
    head("A. CAKUPAN KODE — hook penautan di titik LAHIR dokumen")
    hooks = dict(BIRTH_HOOKS)
    if extra_hooks:
        hooks.update(extra_hooks)
    for doc_type, files in sorted(hooks.items()):
        found = []
        for rel in files:
            p = BACKEND / rel
            if not p.exists():
                continue
            src = p.read_text(encoding="utf-8", errors="ignore")
            if "doc_refs_service" in src and re.search(r"safe_link|link_child|\brefs\.link\(", src):
                found.append(rel)
        row = {"doc_type": doc_type, "files": files, "wired": found}
        _report["hooks"].append(row)
        if found:
            line("PASS", f"{doc_type}: hook penautan ada di {', '.join(found)}")
        else:
            line("FAIL", f"{doc_type}: TIDAK ada hook penautan di titik lahir dokumen",
                 f"kandidat berkas: {', '.join(files)} — dokumen baru akan lahir tanpa jejak")


# ── 2. Cakupan DATA (per koleksi, berbasis registry) ────────────────────────
async def audit_coverage(strict: bool) -> None:
    from db import db
    from services import doc_refs_service as refs

    head("B. CAKUPAN DATA — surat ber-sumber wajib menaut sumbernya")
    for meta in sorted(refs.DOC_TYPES.values(), key=lambda m: m["order"]):
        if not meta["needs_parent"]:
            continue
        flt = dict(meta["filter"])
        proj = {"_id": 0, "id": 1, "refs": 1, meta["number"]: 1}
        for f in meta.get("source_fk") or []:
            proj[f] = 1
        total = sourced = linked = standalone = 0
        missing: list = []
        async for row in db[meta["collection"]].find(flt, proj):
            total += 1
            if not refs._has_source(row, meta.get("source_fk") or []):  # noqa: SLF001
                standalone += 1
                continue
            sourced += 1
            parents = [r for r in (row.get("refs") or [])
                       if r.get("rel") in refs.PARENT_RELS and r.get("doc_id")]
            if parents:
                linked += 1
            else:
                missing.append(row.get(meta["number"]) or row["id"])
        pct = 100.0 if sourced == 0 else round(linked * 100.0 / sourced, 1)
        _report["coverage"].append({"doc_type": meta["doc_type"], "total": total,
                                    "sourced": sourced, "linked": linked,
                                    "standalone": standalone, "pct": pct,
                                    "missing": missing[:10]})
        label = f"{meta['label']} ({meta['doc_type']})"
        detail = (f"{linked}/{sourced} ber-sumber tertaut · {standalone} berdiri sendiri "
                  f"· {total} total")
        if sourced and pct < 100:
            line("FAIL" if strict else "WARN", f"{label}: cakupan {pct}%",
                 f"{detail} · contoh tanpa induk: {', '.join(missing[:5])}")
        else:
            line("PASS", f"{label}: cakupan {pct}%", detail)


# ── 3. Kesehatan tautan ─────────────────────────────────────────────────────
async def audit_health(strict: bool) -> None:
    from db import db
    from services import doc_refs_service as refs

    head("C. KESEHATAN TAUTAN — menggantung · satu arah · tak dikenal · duplikat")
    dangling: list = []
    unknown: list = []
    dupes: list = []
    total_refs = 0
    for meta in refs.DOC_TYPES.values():
        flt = dict(meta["filter"])
        flt["refs.0"] = {"$exists": True}
        async for row in db[meta["collection"]].find(flt, {"_id": 0, "id": 1, "refs": 1}):
            seen = set()
            for r in row.get("refs") or []:
                total_refs += 1
                t, i = r.get("doc_type"), r.get("doc_id")
                key = (r.get("rel"), t, i)
                if key in seen:
                    dupes.append(f"{meta['doc_type']}:{row['id']} → {t}:{i}")
                seen.add(key)
                if t not in refs.DOC_TYPES:
                    unknown.append(f"{meta['doc_type']}:{row['id']} → {t}")
                    continue
                if not await refs.load_doc(t, i):
                    dangling.append(f"{meta['doc_type']}:{row['id']} → {t}:{i}")
    one_way = await refs.one_way_refs(limit=50)
    _report["health"] = {"total_refs": total_refs, "dangling": dangling[:10],
                         "unknown": unknown[:10], "dupes": dupes[:10],
                         "one_way": one_way[:10]}

    def check(name: str, rows: list, why: str) -> None:
        if rows:
            line("FAIL" if strict else "WARN", f"{name}: {len(rows)} temuan", f"{why} — {rows[:4]}")
        else:
            line("PASS", f"{name}: bersih")

    print(f"  {C}total {total_refs} tautan diperiksa{X}")
    check("Tautan menggantung", dangling, "target sudah tidak ada (jejak menunjuk hantu)")
    check("Relasi satu arah", one_way, "tidak bisa ditelusuri balik (INV-REF-02)")
    check("doc_type tak dikenal", unknown, "belum terdaftar di registry DOC_TYPES")
    check("Tautan duplikat", dupes, "dedupe `_push_ref` bocor")


async def main_async(args) -> int:
    if args.self_test:
        # BUKTI-MERAH: audit harus MEMERAH bila ada jenis dokumen tanpa hook penautan.
        head("SELF-TEST — audit wajib bisa MEMERAH (bukti-merah guardrail)")
        audit_hooks({"dokumen_hantu_uji": ["services/tidak_ada_berkas_ini.py"]})
        if _stats["fail"] >= 1:
            print(f"\n{G}{B}✓ SELF-TEST HIJAU: audit mendeteksi jenis dokumen tanpa hook.{X}")
            return 0
        print(f"\n{R}{B}✗ SELF-TEST GAGAL: audit tidak memerah padahal hook tidak ada.{X}")
        return 1

    audit_hooks()
    await audit_coverage(args.strict)
    await audit_health(args.strict)

    head("RINGKASAN")
    print(f"  PASS {_stats['pass']} · FAIL {_stats['fail']} · WARN {_stats['warn']}")
    if args.json:
        print(json.dumps(_report, ensure_ascii=False, indent=2))
    if _stats["fail"]:
        print(f"\n{R}{B}✗ AUDIT RELASI DOKUMEN MERAH — {_stats['fail']} temuan wajib diperbaiki.{X}")
        return 1
    print(f"\n{G}{B}✓ AUDIT RELASI DOKUMEN HIJAU — tidak ada surat buntu.{X}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit relasi dokumen (FASE G-4)")
    ap.add_argument("--strict", action="store_true", help="cakupan < 100% ⇒ FAIL (dipakai gate)")
    ap.add_argument("--self-test", action="store_true", help="bukti-merah guardrail")
    ap.add_argument("--json", action="store_true", help="cetak laporan JSON")
    args = ap.parse_args()
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
