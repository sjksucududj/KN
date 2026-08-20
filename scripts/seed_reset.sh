#!/usr/bin/env bash
###############################################################################
# seed_reset.sh — Kain Nusantara (KN3) seed + INTEGRITY GATE
# ----------------------------------------------------------------------------
# Reset DB ke data realistis YANG BERSIH, lalu jalankan gate integritas.
# Pelajaran kunci CASE_STUDY_INTENT_DRIFT (torado60):
#   Verifikasi WAJIB di DB clean-seed — DB dev yang kotor MENUTUPI drift.
#   Maka blok [GATE] di bawah SELALU jalan setelah seed dan bisa GAGAL.
###############################################################################
set -uo pipefail
CYAN='\033[96m'; GREEN='\033[92m'; RED='\033[91m'; YELLOW='\033[93m'; BOLD='\033[1m'; RESET='\033[0m'
cd "$(dirname "$0")/.." || exit 1

echo -e "${CYAN}${BOLD}"
echo "=============================================================="
echo "  KN3 SEED RESET + INTEGRITY GATE"
echo "=============================================================="
echo -e "${RESET}"

# 1) SEED (seed_realistic.py meng-clear koleksi operasional lalu mengisi ulang)
echo -e "${CYAN}[1/3] Seeding realistic data...${RESET}"
python seed_realistic.py
SEED_RC=$?
if [ $SEED_RC -ne 0 ]; then
  echo -e "${RED}${BOLD}SEED GAGAL (rc=$SEED_RC) — batalkan.${RESET}"
  exit $SEED_RC
fi

# 2) CONTRACT GATE (statik: nama koleksi seed/kode)
echo -e "\n${CYAN}[2/5] [GATE] Contract verifier (nama koleksi)...${RESET}"
python scripts/verify_contract.py --all
CONTRACT_RC=$?

# 3) FE↔BE CONTRACT GATE (duplicate route + FE call exist + field drift)
echo -e "\n${CYAN}[3/5] [GATE] FE↔BE API contract...${RESET}"
python scripts/verify_api_contract.py
APIC_RC=$?

# 4) DATA-INTEGRITY GATE (di DB yang BARU di-seed = bersih)
echo -e "\n${CYAN}[4/5] [GATE] Data-integrity verifier (clean seed)...${RESET}"
python scripts/verify_data_integrity.py
INTEG_RC=$?

# 5) F0-C ENTITY-SCOPING GATE (static scope usage + DB: setiap dok koleksi SCOPED ber-entity)
echo -e "\n${CYAN}[5/5] [GATE] Entity-scoping verifier (F0-C)...${RESET}"
python backend/scripts/verify_entity_scoping.py
F0C_RC=$?

echo -e "\n${CYAN}${BOLD}==============================================================${RESET}"
if [ $CONTRACT_RC -eq 0 ] && [ $INTEG_RC -eq 0 ] && [ $APIC_RC -eq 0 ] && [ $F0C_RC -eq 0 ]; then
  echo -e "  ${GREEN}${BOLD}✓ SEED + GATE LULUS — DB siap & invarian valid.${RESET}"
  RC=0
else
  echo -e "  ${RED}${BOLD}✗ GATE GAGAL — contract=$CONTRACT_RC api_contract=$APIC_RC integrity=$INTEG_RC entity_scoping=$F0C_RC${RESET}"
  echo -e "  ${YELLOW}Perbaiki drift/invarian SEBELUM melanjutkan development.${RESET}"
  RC=1
fi
echo -e "${CYAN}${BOLD}==============================================================${RESET}\n"
echo -e "Audit lanjutan (opsional):"
echo -e "  ${CYAN}python scripts/health_check.py${RESET}            # sweep endpoint kritis"
echo -e "  ${CYAN}python scripts/audit_endpoint_sweep.py${RESET}    # sweep SEMUA GET /api"
echo -e "  ${CYAN}python scripts/ux_audit.py${RESET}                # baseline UX"
echo -e "  ${CYAN}python scripts/audit_collection_drift.py${RESET}  # koleksi dibaca tapi kosong"
echo ""
exit $RC
