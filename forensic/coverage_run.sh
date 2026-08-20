#!/usr/bin/env bash
###############################################################################
# coverage_run.sh — AUDIT: measure real backend coverage of the whole test corpus
# Starts uvicorn under coverage.py, reseeds, runs corpus, collects coverage.
###############################################################################
set -uo pipefail
COVDIR=/app/coverage_data
mkdir -p "$COVDIR"
rm -f "$COVDIR"/.coverage* 2>/dev/null
export COVERAGE_FILE="$COVDIR/.coverage"

echo "[1/8] stop supervisor backend"
sudo supervisorctl stop backend >/dev/null 2>&1
sleep 2

echo "[2/8] start server under coverage"
cd /app/backend
COVERAGE_FILE="$COVDIR/.coverage" nohup coverage run --rcfile=/app/.coveragerc \
    -m uvicorn server:app --host 0.0.0.0 --port 8001 \
    > "$COVDIR/server.log" 2>&1 &
SRV_PID=$!
echo "    server pid=$SRV_PID"

echo "[3/8] wait for readiness"
READY=0
for i in $(seq 1 40); do
  if curl -s -m 3 http://localhost:8001/api/ >/dev/null 2>&1; then READY=1; echo "    ready after ${i}s"; break; fi
  sleep 1
done
if [ "$READY" != "1" ]; then echo "    SERVER NOT READY - abort"; cat "$COVDIR/server.log" | tail -20; kill -INT $SRV_PID 2>/dev/null; sudo supervisorctl start backend; exit 1; fi

echo "[4/8] reseed clean"
cd /app && python seed_realistic.py > "$COVDIR/seed.log" 2>&1
echo "    seed rc=$?"

echo "[5/8] run corpus (this takes a while)"
cd /app && PYTHONPATH=/app/forensic/covshim python forensic/run_cov_corpus.py > "$COVDIR/corpus.log" 2>&1
echo "    corpus rc=$?"

echo "[6/8] stop server gracefully"
kill -INT $SRV_PID 2>/dev/null
for i in $(seq 1 20); do
  if ! kill -0 $SRV_PID 2>/dev/null; then break; fi
  sleep 1
done
kill -9 $SRV_PID 2>/dev/null

echo "[7/8] combine + report"
cd /app/backend
COVERAGE_FILE="$COVDIR/.coverage" coverage combine >/dev/null 2>&1
COVERAGE_FILE="$COVDIR/.coverage" coverage json -o "$COVDIR/cov_backend.json" >/dev/null 2>&1
COVERAGE_FILE="$COVDIR/.coverage" coverage report --sort=cover > "$COVDIR/cov_report.txt" 2>&1
echo "    report written"

echo "[8/8] restart supervisor backend"
sudo supervisorctl start backend >/dev/null 2>&1
sleep 3
curl -s -m 5 http://localhost:8001/api/ >/dev/null 2>&1 && echo "    backend back up" || echo "    WARN backend not responding yet"
echo "COVERAGE_RUN_DONE"
