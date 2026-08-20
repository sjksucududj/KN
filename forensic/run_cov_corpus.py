"""run_cov_corpus.py — AUDIT: execute the ENTIRE historical test corpus against
the locally running (coverage-instrumented) server.

Redirect shim (covshim/sitecustomize.py) rewrites stale preview URLs -> localhost.
Runs each file (direct __main__ OR pytest), records rc/duration, writes JSON summary.
Goal = maximize server-side code execution for honest coverage measurement.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = "/app"
TIMEOUT = 150
OUT = "/app/coverage_data/corpus_summary.json"

PATTERNS = [
    "/app/*test*.py", "/app/test_*.py",
    "/app/backend/*test*.py", "/app/backend/test_*.py",
    "/app/backend/tests/*.py",
    "/app/tests/*.py",
    "/app/forensic/fa_*.py",
    "/app/scripts/health_check.py", "/app/scripts/audit_endpoint_sweep.py",
    "/app/scripts/ux_audit.py", "/app/scripts/ui_smoke.py",
    "/app/scripts/poc_hrd.py", "/app/scripts/poc_hrd_h1.py", "/app/scripts/poc_sales_revamp.py",
]

EXCLUDE_SUBSTR = ["run_cov_corpus", "covshim", "__init__", "conftest"]


def discover():
    files = set()
    for p in PATTERNS:
        for f in glob.glob(p):
            if any(x in f for x in EXCLUDE_SUBSTR):
                continue
            files.add(os.path.abspath(f))
    return sorted(files)


def mode_for(path):
    try:
        src = open(path, "r", errors="ignore").read()
    except Exception:
        return "direct"
    if "__main__" in src:
        return "direct"
    if re.search(r"^def test_", src, re.M) or re.search(r"^\s+def test_", src, re.M):
        return "pytest"
    return "direct"


def run_one(path):
    m = mode_for(path)
    if m == "pytest":
        cmd = [sys.executable, "-m", "pytest", path, "-q", "-p", "no:cacheprovider",
               "--no-header", "-o", "addopts="]
    else:
        cmd = [sys.executable, path]
    env = dict(os.environ)
    env["PYTHONPATH"] = "/app/forensic/covshim:" + env.get("PYTHONPATH", "")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                           text=True, timeout=TIMEOUT)
        rc, to = r.returncode, False
        tail = (r.stdout[-400:] + r.stderr[-600:])
    except subprocess.TimeoutExpired:
        rc, to, tail = -9, True, "TIMEOUT"
    except Exception as e:
        rc, to, tail = -1, False, f"RUNNER-ERR {e}"
    return {"file": path.replace("/app/", ""), "mode": m, "rc": rc,
            "timeout": to, "dur": round(time.time() - t0, 1), "tail": tail}


def main():
    files = discover()
    print(f"[corpus] {len(files)} files discovered")
    results = []
    for i, f in enumerate(files, 1):
        res = run_one(f)
        results.append(res)
        flag = "TO" if res["timeout"] else ("ok" if res["rc"] == 0 else f"rc{res['rc']}")
        print(f"[{i:3d}/{len(files)}] {flag:>5} {res['dur']:6.1f}s {res['file']}", flush=True)
    ok = sum(1 for r in results if r["rc"] == 0)
    to = sum(1 for r in results if r["timeout"])
    summary = {"total": len(files), "ok": ok, "failed": len(files) - ok,
              "timeouts": to, "results": results}
    os.makedirs("/app/coverage_data", exist_ok=True)
    json.dump(summary, open(OUT, "w"), indent=2)
    print(f"[corpus] DONE total={len(files)} ok={ok} failed={len(files)-ok} timeouts={to}")


if __name__ == "__main__":
    main()
