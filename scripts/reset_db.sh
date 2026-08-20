#!/usr/bin/env bash
# Reset DB cepat ke kondisi bersih + jalankan gate. Dipakai berulang saat audit/fix.
# Usage: bash scripts/reset_db.sh [--no-gate]
set -uo pipefail
S=$(date +%s)
python /app/seed_realistic.py >/tmp/_seed.log 2>&1 && echo "[reset +$(( $(date +%s) - S ))s] DB reseed bersih." || { echo "SEED GAGAL:"; tail -8 /tmp/_seed.log; exit 1; }
if [ "${1:-}" != "--no-gate" ]; then
  python /app/scripts/verify_data_integrity.py 2>&1 | grep -E "PASS [0-9]+|FAIL [0-9]+|WARN [0-9]+|INVARIAN|VIOLATION" | tail -2
fi
