#!/usr/bin/env bash
# Pembungkus gate.sh dengan KUNCI (flock) — mencegah DUA gate berjalan bersamaan.
# Kenapa: dua gate paralel saling merusak (yang satu men-seed & MENGOSONGKAN koleksi
# sementara yang lain sedang memverifikasi) → gate merah palsu massal ("koleksi KOSONG").
set -uo pipefail
LOG="${2:-/app/.logs/gate_run.log}"
exec 9>/tmp/kn_gate.lock
if ! flock -n 9; then
  echo "[run_gate] gate lain masih berjalan — TIDAK menjalankan yang kedua." | tee -a "$LOG"
  exit 0
fi
: > "$LOG"
echo "[run_gate] mulai $(date '+%H:%M:%S') mode=${1:---full}" >> "$LOG"
cd /app && bash scripts/gate.sh "${1:---full}" >> "$LOG" 2>&1
rc=$?
echo "[run_gate] selesai $(date '+%H:%M:%S') rc=$rc" >> "$LOG"
exit $rc
