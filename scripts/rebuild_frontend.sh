#!/usr/bin/env bash
# rebuild_frontend.sh — Rebuild the CRA static bundle at LOW priority.
#
# WHY: The preview is served from the prebuilt bundle (frontend/build) by
# static_server.js. There is NO hot reload. After editing anything under
# frontend/src you must rebuild:  bash /app/scripts/rebuild_frontend.sh
#
# The build runs under nice/ionice so it never starves the backend or the
# platform health-probe (container is capped at 1 CPU / 2GB RAM).
# static_server.js reads files from disk per request, so once the build
# finishes the new assets are served immediately (no restart needed).
set -euo pipefail

FE_DIR="/app/frontend"
LOG="/app/.frontend_build.log"

echo "[rebuild_frontend] starting build at $(date)"
cd "$FE_DIR"

# Keep memory modest & CPU friendly on the 1-core / 2GB box.
export NODE_OPTIONS="--max-old-space-size=1536"
export GENERATE_SOURCEMAP=false
export CI=false
export DISABLE_ESLINT_PLUGIN=true

# nice=lowest CPU priority, ionice=idle IO priority (best-effort if available).
NICE="nice -n 19"
if command -v ionice >/dev/null 2>&1; then
  NICE="ionice -c3 $NICE"
fi

echo "[rebuild_frontend] running yarn build (low priority)… tail -f $LOG"
if $NICE yarn build > "$LOG" 2>&1; then
  echo "[rebuild_frontend] BUILD OK at $(date)"
  # SENGAJA TIDAK ADA `supervisorctl signal HUP frontend` di sini.
  #
  # BUG NYATA `KN-FE-PORT-ORPHAN` (2026-07-30): dulu baris itu ada "biar aman".
  # `static_server.js` melayani berkas LANGSUNG dari disk setiap permintaan, jadi HUP
  # sama sekali tidak diperlukan — tetapi Node mengakhiri diri saat menerima SIGHUP,
  # sedangkan proses `sh -c`/`yarn` pembungkusnya kadang tidak ikut mati. Supervisor
  # melihat program-nya berhenti lalu menyalakan ulang, dan proses YATIM yang masih
  # memegang port 3000 membuat proses baru gagal: `EADDRINUSE` → `frontend FATAL`.
  # Gejalanya sudah dua kali dicatat di SESSION_HANDOFF sebagai "kejadian lapangan"
  # dengan obat manual `fuser -k 3000/tcp && supervisorctl restart frontend`.
  # Sekarang pemicunya dihapus, dan `yarn start` juga membebaskan port lebih dulu
  # (lihat `frontend/package.json`) sehingga kondisi ini tidak bisa mematikan preview.
  echo "[rebuild_frontend] done (bundle baru langsung dilayani — tanpa restart)."
else
  echo "[rebuild_frontend] BUILD FAILED — see $LOG (last 40 lines):"
  tail -n 40 "$LOG"
  exit 1
fi
