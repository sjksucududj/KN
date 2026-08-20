#!/usr/bin/env bash
# Restore runtime environment after clone (deps + seed + FE build).
set -uo pipefail
echo "=== [1/5] pip install (skip emergentintegrations & litellm: sudah di base image) $(date)"
cd /app/backend
grep -vE '^(emergentintegrations|litellm)' requirements.txt > /tmp/req_filtered.txt
pip install --no-input -q -r /tmp/req_filtered.txt 2>&1 | tail -20
echo "PIP_EXIT=$?"

echo "=== [2/5] yarn install $(date)"
cd /app/frontend
yarn install --silent --network-timeout 600000 2>&1 | tail -20
echo "YARN_EXIT=$?"

echo "=== [3/5] restart backend $(date)"
supervisorctl restart backend 2>&1 | tail -5
sleep 12
curl -s -o /dev/null -w "backend /api/ -> %{http_code}\n" http://localhost:8001/api/

echo "=== [4/5] seed_realistic $(date)"
cd /app
python seed_realistic.py 2>&1 | tail -15
echo "SEED_EXIT=$?"

echo "=== [5/5] rebuild frontend $(date)"
bash /app/scripts/rebuild_frontend.sh 2>&1 | tail -15
echo "BUILD_EXIT=$?"
echo "=== RESTORE DONE $(date)"
