#!/bin/bash
# =============================================================================
# KAIN NUSANTARA — INSTANT CONTEXT LOADER
# =============================================================================
# Jalankan di awal setiap session untuk snapshot kondisi sistem saat ini.
# Output: Semua info kritis dalam < 1 menit.
#
# Usage:
#   bash /app/scripts/load_context.sh
#   bash /app/scripts/load_context.sh --full   # include endpoint list
# =============================================================================

FULL=false
[[ "$1" == "--full" ]] && FULL=true

echo ""
echo "================================================================"
echo "  KAIN NUSANTARA — CONTEXT SNAPSHOT"
echo "  Generated: $(date '+%Y-%m-%d %H:%M WIB')"
echo "================================================================"

# ─── SERVICE STATUS ───────────────────────────────────────────────────────
echo ""
echo "▶ SERVICE STATUS"
if curl -s http://localhost:8001/api/ | grep -q "aktif"; then
    echo "   ✅ Backend: RUNNING (http://localhost:8001)"
else
    echo "   ❌ Backend: DOWN — jalankan: supervisorctl restart backend"
fi

if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "   ✅ Frontend: RUNNING (http://localhost:3000)"
else
    echo "   ⚠  Frontend: checking..."
fi

# ─── ENV CONFIG ───────────────────────────────────────────────────────────────
echo ""
echo "▶ ENV CONFIG"
DB_NAME=$(grep DB_NAME /app/backend/.env | cut -d= -f2 | tr -d '"')
MONGO_URL=$(grep MONGO_URL /app/backend/.env | cut -d= -f2 | tr -d '"')
echo "   DB_NAME:   $DB_NAME"
echo "   MONGO_URL: $MONGO_URL"
echo "   BACKEND_URL: $(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)"

# ─── DATABASE STATE ──────────────────────────────────────────────────────────
echo ""
echo "▶ DATABASE STATE (collection counts)"
python3 - << 'PYEOF'
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, '/app/backend')
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')

async def count_collections():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    collections = [
        'users', 'products', 'customers', 'warehouses', 'uoms',
        'sales_orders', 'invoices', 'inventory_balances', 'inventory_movements',
        'wms_tasks', 'warehouse_transfers', 'cycle_count_sessions',
        'purchase_orders', 'document_templates', 'audit_logs', 'sessions'
    ]
    
    print(f"   {'Collection':<30} {'Count':>8}")
    print(f"   {'----------':<30} {'-----':>8}")
    for coll in collections:
        count = await db[coll].count_documents({})
        status = '' if count > 0 else '  ⚠ KOSONG'
        print(f"   {coll:<30} {count:>8}{status}")
    
    client.close()

asyncio.run(count_collections())
PYEOF

# ─── FILE SIZE SNAPSHOT ────────────────────────────────────────────────────────
echo ""
echo "▶ FILE SIZES (baris) — LIMIT: router .py ≤800, .jsx ≤500"
echo "   Python Routers:"
for f in /app/backend/routers/*.py; do
    lines=$(wc -l < "$f")
    fname=$(basename "$f")
    if [ "$lines" -gt 800 ]; then
        echo "   \u274c $fname: $lines baris (MELEBIHI 800!)"
    elif [ "$lines" -gt 640 ]; then
        echo "   \u26a0  $fname: $lines baris (mendekati 800)"
    fi
done
echo "   (hanya tampil yang WARNING/FAIL)"

echo "   React Components:"
for f in $(find /app/frontend/src -name "*.jsx"); do
    lines=$(wc -l < "$f")
    fname=$(echo "$f" | sed 's|/app/frontend/src/||')
    if [ "$lines" -gt 500 ]; then
        echo "   \u274c $fname: $lines baris (MELEBIHI 500!)"
    elif [ "$lines" -gt 425 ]; then
        echo "   \u26a0  $fname: $lines baris (mendekati 500)"
    fi
done
echo "   (hanya tampil yang WARNING/FAIL)"

# ─── RECENTLY MODIFIED FILES ────────────────────────────────────────────────────
echo ""
echo "▶ RECENTLY MODIFIED FILES (24 jam terakhir)"
find /app/backend /app/frontend/src -name "*.py" -o -name "*.jsx" -o -name "*.js" | \
    xargs ls -lt 2>/dev/null | \
    grep -v '^total' | \
    awk '{print $6, $7, $8, $9}' | \
    head -15 | \
    while read line; do echo "   $line"; done

# ─── QUICK COMPLIANCE ─────────────────────────────────────────────────────────
echo ""
echo "▶ QUICK COMPLIANCE CHECK"
python3 /app/scripts/validate_compliance.py --quick 2>&1 | grep -E "FAIL|WARN|SUMMARY|PASS.*FILE_SIZE" | head -20

# ─── FULL ENDPOINT LIST (optional) ───────────────────────────────────────────
if [ "$FULL" = true ]; then
    echo ""
    echo "▶ ALL API ENDPOINTS"
    grep -rh "@router\." /app/backend/routers/*.py | \
        grep -oP "(get|post|put|patch|delete)\(['\"]\K[^'\"]+" | \
        sort -u | \
        while read line; do echo "   $line"; done
fi

# ─── SESSION HANDOFF REMINDER ────────────────────────────────────────────────
echo ""
echo "▶ LAST SESSION HANDOFF"
if [ -f /app/memory/SESSION_HANDOFF.md ]; then
    head -15 /app/memory/SESSION_HANDOFF.md | grep -v "^#" | grep -v "^$" | while read line; do
        echo "   $line"
    done
else
    echo "   ⚠  SESSION_HANDOFF.md tidak ditemukan!"
fi

echo ""
echo "================================================================"
echo "  📖 BACA BERJENJANG (hemat context — JANGAN baca semua dok):"
echo "  TIER 0 (wajib): guardrails + map + fase berjalan"
echo "    cat /app/memory/ENGINEERING_GUARDRAILS.md  ← kontrak backend + protokol baca"
echo "    cat /app/memory/FRONTEND_GUARDRAILS.md     ← kontrak frontend"
echo "    cat /app/CODEBASE_MAP.md                   ← peta files & endpoints (grep, jangan utuh)"
echo "    grep -A30 'fase yang sedang' /app/plan.md  ← task berjalan saja"
echo "  TIER 1 (sesuai tugas): section ENTITY_REGISTRY.md utk koleksi yg disentuh"
echo "  TIER 2 (jarang): KN_14..17 / assessment.  KN_02/03/04/07 = ASPIRATIF (kode menang)"
echo "  Verifikasi = GATES, bukan baca prosa ulang."
echo "================================================================"
echo ""
