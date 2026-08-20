#!/usr/bin/env bash
# =============================================================================
# Kain Nusantara ERP — FAST idempotent environment bring-up
# Dibuat S#075 agar agent berikutnya tidak menunggu lama saat "loading".
#
# Yang membuatnya cepat:
#   * SKIP clone bila app code sudah ada
#   * SKIP pip/yarn bila requirements.txt/package.json TIDAK berubah (hash) DAN
#     paket inti sudah bisa di-import (aman untuk container fresh)
#   * pip + yarn dijalankan PARALEL
#   * seed HANYA bila DB kosong (kecuali --reseed)
#
# Usage:
#   bash scripts/dev_setup.sh              # bring-up normal (skip yang sudah beres)
#   bash scripts/dev_setup.sh --reseed     # paksa seed ulang DB
#   bash scripts/dev_setup.sh --force-deps # paksa install ulang deps
#   KN_REPO=<url> bash scripts/dev_setup.sh  # override URL repo utk clone
# =============================================================================
set -uo pipefail
START=$(date +%s)
APP=/app
REPO="${KN_REPO:-https://github.com/sudahtidakpunyaide/kn.git}"
RESEED=0; FORCE_DEPS=0
for a in "$@"; do
  case "$a" in
    --reseed) RESEED=1 ;;
    --force-deps) FORCE_DEPS=1 ;;
    *) echo "arg tak dikenal: $a" ;;
  esac
done
log(){ echo -e "\033[36m[setup +$(( $(date +%s) - START ))s]\033[0m $*"; }

# ---------------------------------------------------------------------------
# 1) Repo: clone hanya bila app code belum ada (preserve .env/.git/node_modules)
# ---------------------------------------------------------------------------
if [ ! -f "$APP/backend/bootstrap.py" ]; then
  log "App code TIDAK ada -> shallow clone $REPO ..."
  cp -f "$APP/backend/.env"  /tmp/_be.env 2>/dev/null || true
  cp -f "$APP/frontend/.env" /tmp/_fe.env 2>/dev/null || true
  TMP=$(mktemp -d)
  git clone --depth 1 "$REPO" "$TMP" >/tmp/_clone.log 2>&1 || { log "CLONE GAGAL:"; tail -5 /tmp/_clone.log; exit 1; }
  rsync -a --exclude='.git' --exclude='node_modules' --exclude='.env' "$TMP"/ "$APP"/
  cp -f /tmp/_be.env "$APP/backend/.env"  2>/dev/null || true
  cp -f /tmp/_fe.env "$APP/frontend/.env" 2>/dev/null || true
  rm -rf "$TMP"
  log "clone + overlay selesai (.env dipertahankan)."
else
  log "App code sudah ada -> SKIP clone."
fi

# ---------------------------------------------------------------------------
# 2) Backend deps (paralel). Skip bila hash sama DAN paket inti importable.
# ---------------------------------------------------------------------------
REQ="$APP/backend/requirements.txt"; BEMARK="$APP/.cache_deps_be.md5"
BEMD5=$(md5sum "$REQ" 2>/dev/null | awk '{print $1}')
BE_OK=1
python -c "import fastapi, motor, pydantic, reportlab, openpyxl, jwt" >/dev/null 2>&1 || BE_OK=0
BE_PID=""
if [ "$FORCE_DEPS" = "1" ] || [ "$BE_OK" = "0" ] || [ "$(cat "$BEMARK" 2>/dev/null)" != "$BEMD5" ]; then
  log "pip install (background) ..."
  ( pip install -q -r "$REQ" && echo "$BEMD5" > "$BEMARK" && echo OK ) >/tmp/_be_deps.log 2>&1 &
  BE_PID=$!
else
  log "backend deps unchanged & importable -> SKIP pip."
fi

# ---------------------------------------------------------------------------
# 3) Frontend deps (paralel). Skip bila hash sama DAN node_modules ada.
# ---------------------------------------------------------------------------
PKG="$APP/frontend/package.json"; FEMARK="$APP/.cache_deps_fe.md5"
FEMD5=$(md5sum "$PKG" 2>/dev/null | awk '{print $1}')
FE_PID=""
if [ "$FORCE_DEPS" = "1" ] || [ ! -d "$APP/frontend/node_modules" ] || [ "$(cat "$FEMARK" 2>/dev/null)" != "$FEMD5" ]; then
  log "yarn install (background) ..."
  ( cd "$APP/frontend" && (yarn install --frozen-lockfile >/dev/null 2>&1 || yarn install >/dev/null 2>&1) && echo "$FEMD5" > "$FEMARK" && echo OK ) >/tmp/_fe_deps.log 2>&1 &
  FE_PID=$!
else
  log "frontend deps unchanged & node_modules ada -> SKIP yarn."
fi

# tunggu install selesai
if [ -n "$BE_PID" ]; then wait "$BE_PID"; log "backend deps: $(tail -1 /tmp/_be_deps.log)"; fi
if [ -n "$FE_PID" ]; then wait "$FE_PID"; log "frontend deps: $(tail -1 /tmp/_fe_deps.log)"; fi

# ---------------------------------------------------------------------------
# 4) Restart services
# ---------------------------------------------------------------------------
log "restart backend + frontend ..."
sudo supervisorctl restart backend frontend >/dev/null 2>&1 || true
sleep 6

# ---------------------------------------------------------------------------
# 5) Seed DB — hanya bila kosong (kecuali --reseed)
# ---------------------------------------------------------------------------
COUNT=$(python - <<'PY' 2>/dev/null
import os
from dotenv import load_dotenv; load_dotenv('/app/backend/.env')
from pymongo import MongoClient
try:
    print(MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=4000)[os.environ['DB_NAME']].sales_orders.count_documents({}))
except Exception:
    print(0)
PY
)
if [ "$RESEED" = "1" ] || [ "${COUNT:-0}" = "0" ]; then
  log "seeding DB (sales_orders=${COUNT:-0}) ..."
  python "$APP/seed_realistic.py" >/tmp/_seed.log 2>&1 && log "seed selesai." || { log "SEED GAGAL:"; tail -5 /tmp/_seed.log; }
else
  log "DB sudah terisi (sales_orders=$COUNT) -> SKIP seed (pakai --reseed utk paksa)."
fi

# ---------------------------------------------------------------------------
# 6) Health + gate integritas
# ---------------------------------------------------------------------------
log "health: $(curl -s -m5 http://localhost:8001/api/ 2>/dev/null || echo DOWN)"
log "integrity gate:"
python "$APP/scripts/verify_data_integrity.py" 2>&1 | grep -E "PASS [0-9]+|FAIL [0-9]+|WARN [0-9]+|INVARIAN|VIOLATION" | tail -2 || true
log "SELESAI dalam $(( $(date +%s) - START ))s."
echo "    Login demo (password: demo12345): admin@ / manager@ / sales@ / sales3@ / warehouse@ kainnusantara.id"
echo "    Reset DB cepat  : bash scripts/reset_db.sh"
echo "    Jalankan audit  : bash scripts/run_forensics.sh"
