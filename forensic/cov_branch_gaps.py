"""cov_branch_gaps.py — AUDIT #073 F1: rank never-taken BRANCHES in critical modules.

Uses cov_backend.json branch data. For financial/auth files, lists the branch
source lines that were NEVER taken (error paths, edge cases) — the highest-value
places to hunt hidden bugs (Dijkstra: untaken branch = unverified behaviour).
"""
import json
import os

COV = json.load(open("/app/coverage_data/cov_backend.json"))

CRITICAL = [
    "services/gl_service.py", "entity_scope.py", "dependencies.py",
    "services/return_service.py", "services/vendor_bill_service.py",
    "services/costing_service.py", "services/ar_receipt_service.py",
    "services/config_service.py", "services/customer_service.py",
    "services/roll_service.py", "services/sales_order_helpers.py",
    "routers/sales_orders.py", "routers/gl.py", "routers/vendor_bills.py",
    "services/incentive_service.py", "services/closing_service.py",
    "routers/ar_receipts.py", "routers/consolidation.py",
]

BACKEND = "/app/backend"


def src_line(relpath, lineno):
    try:
        p = os.path.join(BACKEND, relpath)
        lines = open(p, errors="ignore").read().splitlines()
        return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else "?"
    except Exception:
        return "?"


# Rank ALL app files by missing-branch count
ranked = []
for rel, fdata in COV["files"].items():
    if rel.startswith(("tests/",)) or "_test" in rel or rel.startswith("scripts/"):
        continue
    mb = fdata.get("missing_branches", [])
    if mb:
        ranked.append((rel, len(mb), fdata["summary"].get("percent_covered_display", "?")))
ranked.sort(key=lambda x: -x[1])

print("=== TOP 25 FILES BY NEVER-TAKEN BRANCHES ===")
for rel, n, pct in ranked[:25]:
    tag = " <<< CRITICAL" if rel in CRITICAL else ""
    print(f"  {n:4d} missing-branches  {rel}{tag}")

print("\n\n=== NEVER-TAKEN BRANCHES IN CRITICAL FINANCIAL/AUTH FILES (annotated) ===")
for rel in CRITICAL:
    fdata = COV["files"].get(rel)
    if not fdata:
        continue
    mb = fdata.get("missing_branches", [])
    if not mb:
        continue
    print(f"\n## {rel}  ({len(mb)} untaken branches)")
    seen = set()
    for pair in mb:
        frm = pair[0]
        if frm in seen or frm < 0:
            continue
        seen.add(frm)
        print(f"   L{frm:<4} {src_line(rel, frm)[:95]}")
