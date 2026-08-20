#!/usr/bin/env bash
# Jalankan seluruh probe forensik (audit) dgn reseed di antara yg destructive.
# Butuh backend RUNNING. Usage: bash scripts/run_forensics.sh
set -uo pipefail
cd /app
run(){ echo; echo "########## $1 ##########"; python "forensic/$1" 2>&1 | tail -"${2:-20}"; }
reseed(){ python seed_realistic.py >/dev/null 2>&1; }

reseed; run fa_s074_semantic.py 20
       run fa_s074_errorpath.py 8
reseed; run fa_import_fuzz.py 12
reseed; run fa_landed_cost_value.py 12
reseed; run fa_idor_matrix.py 12
reseed; run fa_coverage_gap.py 14
reseed; run fa_s075_verify.py 40      # kebenaran + idempotensi (S#075)
reseed
echo; echo "########## GATE ##########"
python scripts/verify_data_integrity.py 2>&1 | grep -E "PASS [0-9]+|FAIL [0-9]+|WARN [0-9]+|INVARIAN|VIOLATION" | tail -2
