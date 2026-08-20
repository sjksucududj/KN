#!/usr/bin/env bash
###############################################################################
# gate.sh — ORKESTRATOR GATE TUNGGAL (Kain Nusantara · Guardrail v2)
# Menjalankan gate berurutan lalu menulis memory/GATE_RECEIPT.md.
# Aturan: "Selesai" hanya sah bila receipt HIJAU. Klaim tanpa receipt = void.
#
# ─── TINGKATAN ──────────────────────────────────────────────────────────────
#   bash scripts/gate.sh --quick    ~7 s   STATIK saja — untuk iterasi cepat
#                                          (tanpa DB, tanpa backend, tanpa seed)
#   bash scripts/gate.sh            ~25 s  DEFAULT — statik + seed + invarian +
#                                          runtime IDOR/race/state + sweep +
#                                          health + ANTI-RESIDU
#   bash scripts/gate.sh --ci       ~25 s  Cakupan = DEFAULT, tapi TANPA warna +
#                                          receipt JSON (memory/GATE_RECEIPT.json)
#                                          → dipakai CI / pre-commit / robot.
#   bash scripts/gate.sh --full     ~95 s  DEFAULT + POC fase (G-0..G-4, F, F-1, D)
#
#   Opsi: --no-parallel (paksa berurutan)  ·  --jobs N (jumlah pekerja statik)
#         --json (tulis receipt JSON juga, di mode apa pun)
#
# ─── KENAPA BERTINGKAT ──────────────────────────────────────────────────────
# Gate lama SELALU menjalankan semuanya. Padahal saat mengedit frontend/dokumen,
# 90% gate tak relevan. Tingkat --quick membuat pemeriksaan murah bisa
# dijalankan sesering mungkin.
#
# ─── EFISIENSI: ANGKA TERUKUR (bukan klaim) ─────────────────────────────────
# 2026-07-26  audit_endpoint_sweep      24.5 s -> 2.4 s   (paralel; RSS 122->41 MB)
# 2026-07-26  total gate default        34 s   -> ~12 s
# 2026-07-29  gate --full               272 s  -> ~95 s   lewat 3 perbaikan:
#   1. `audit_config_wiring.hits()` men-regex-scan 719 berkas SETIAP setting
#      (105 setting × 3 korpus = 315 scan penuh) → `build_rows` 6.2 s. Diganti
#      index token sekali-jalan → 0.07 s (89×). Dampaknya besar karena lapisan
#      config dipanggil di SETIAP eksekusi `verify_data_integrity.py`, dan POC
#      fase memanggil skrip itu 8–10× → `verify_data_integrity` 8.4 s -> 2.0 s.
#      Kesetaraan hasil index vs regex DIBUKTIKAN di `--self-test` bagian [6]
#      (315/315 identik) supaya optimasi tak menghilangkan temuan.
#   2. POC fase memakai `--only <lapisan>` untuk blok BUKTI-MERAH (yang memang
#      hanya menguji satu keluarga invarian). Klaim GLOBAL ("invarian global
#      hijau", "nol residu") TETAP memakai eksekusi LENGKAP 211 invarian.
#   3. Gate STATIK (analisis kode, read-only) dijalankan PARALEL sebagai kolam
#      pekerja DAN menumpang jalan bersama blok DB/runtime — kuota CPU kontainer
#      2 inti, jadi ini penghematan nyata, bukan hiasan.
# CAKUPAN TIDAK BERKURANG: jumlah gate & jumlah invarian tetap (bandingkan
# receipt sebelum/sesudah: 36 gate · 211 invarian).
#
# Gate STATIK selalu jalan (analisis kode, tak butuh backend).
# Gate RUNTIME (butuh backend + auth) di-SKIP rapi bila backend belum hidup.
#
# CATATAN: `guard:numeric_bounds` SENGAJA tidak masuk kolam paralel — ia memukul
# API (login admin + probe POST) sehingga harus berjalan SEBELUM seed & tidak
# boleh berbarengan dengan seed yang menghapus user.
#
# Diadaptasi dari metodologi Guardrail v2 proyek Rahaza Travel
# (github.com/akugendutkayababi/travel) → disesuaikan ke stack & skrip KN.
#
# Usage: cd /app && bash scripts/gate.sh [--quick|--ci|--full] [--no-parallel] [--jobs N] [--json]
###############################################################################
set -uo pipefail
CYAN='\033[96m'; GREEN='\033[92m'; RED='\033[91m'; YEL='\033[93m'; BOLD='\033[1m'; RST='\033[0m'
cd "$(dirname "$0")/.." || exit 1
ROOTDIR="$PWD"
RECEIPT="memory/GATE_RECEIPT.md"
RECEIPT_JSON="memory/GATE_RECEIPT.json"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
T_START=$SECONDS
declare -a NAMES RESULTS SNAMES SRESULTS
OVERALL=0

MODE="default"; PARALLEL=1; WRITE_JSON=0; JOBS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --quick) MODE="quick" ;;
    --full)  MODE="full" ;;
    --ci)    MODE="ci"; WRITE_JSON=1
             CYAN=''; GREEN=''; RED=''; YEL=''; BOLD=''; RST='' ;;
    --json)  WRITE_JSON=1 ;;
    --no-parallel) PARALLEL=0 ;;
    --jobs)  shift; JOBS="${1:-}" ;;
    -h|--help) sed -n '2,50p' "$0"; exit 0 ;;
  esac
  shift
done

# Jumlah pekerja statik: ikuti KUOTA cgroup (bukan `nproc`, yang melaporkan
# seluruh inti node dan membuat kita over-subscribe lalu justru lebih lambat).
if [ -z "$JOBS" ]; then
  JOBS=2
  if [ -r /sys/fs/cgroup/cpu.max ]; then
    read -r _q _p < /sys/fs/cgroup/cpu.max || true
    if [ "${_q:-max}" != "max" ] && [ -n "${_p:-}" ] && [ "${_p}" -gt 0 ]; then
      JOBS=$(( _q / _p )); [ "$JOBS" -lt 1 ] && JOBS=1
    fi
  fi
  [ "$JOBS" -gt 4 ] && JOBS=4
fi

# --- Env Mongo dari backend/.env bila belum diset ---
if [ -z "${MONGO_URL:-}" ] && [ -f backend/.env ]; then
  export MONGO_URL="$(grep -E '^MONGO_URL=' backend/.env | head -1 | cut -d= -f2- | tr -d '\"')"
fi
if [ -z "${DB_NAME:-}" ]; then
  if [ -f backend/.env ] && grep -qE '^DB_NAME=' backend/.env; then
    export DB_NAME="$(grep -E '^DB_NAME=' backend/.env | head -1 | cut -d= -f2- | tr -d '\"')"
  else
    export DB_NAME="test_database"
  fi
fi

run_gate () {  # $1=label  $2..=command
  local label="$1"; shift
  local t0=$SECONDS
  echo -e "\n${CYAN}${BOLD}▶ ${label}${RST}"
  bash -c "$*"
  local rc=$?
  local dt=$((SECONDS-t0))
  if [ $rc -eq 0 ]; then
    echo -e "  ${GREEN}✓ ${label} PASS${RST} (${dt}s)"; NAMES+=("$label"); RESULTS+=("PASS (${dt}s)")
  else
    echo -e "  ${RED}✗ ${label} FAIL (rc=$rc)${RST} (${dt}s)"; NAMES+=("$label"); RESULTS+=("FAIL (${dt}s)"); OVERALL=1
  fi
}

skip_gate () { echo -e "\n${YEL}▶ $1 — SKIP ($2)${RST}"; NAMES+=("$1"); RESULTS+=("SKIP"); }

echo -e "${CYAN}${BOLD}\n=============================================================="
echo "  GATE ORCHESTRATOR (Kain Nusantara)  —  $TS   [mode: $MODE]"
echo -e "==============================================================${RST}"

# ============ DAFTAR GATE STATIK (read-only: hanya membaca kode) ============
# Format "label|perintah". Semuanya bebas DB & bebas HTTP → aman paralel.
STATIK=(
  "guard:auth_coverage (INV-AUTH-01)|python scripts/guardrails/verify_auth_coverage.py"
  # Bukti-merah penjaga auth. Ditambahkan 2026-08-15 setelah gate ini MENUDUH PALSU
  # `GET /sales-return-policies/{policy_id}` — endpoint yang menegakkan auth dengan
  # benar lewat `require_any_permission` (enforcer "salah satu dari", E-9). Daftar
  # enforcer keras di penjaga hanya mengenal `require_permission`/`require_role`, dan
  # `"require_permission("` bukan substring `"require_any_permission("`. Dua arah
  # bahayanya: gate merah pada kode benar (lalu penjaganya dimatikan orang), DAN
  # sebaliknya endpoint yang hanya memakai enforcer itu dulu lolos karena kebetulan
  # memanggil `entity_ctx` (LUNAK) — begitu `entity_ctx` dihapus, endpoint tanpa auth
  # pun tetap dinilai lolos. Self-test menjaga kedua arah itu tetap terkunci.
  "guard:auth_coverage SELF-TEST (bukti-merah penjaga auth)|python scripts/guardrails/verify_auth_coverage.py --self-test"
  "validate_compliance (file/naming/docs/api/env)|python scripts/validate_compliance.py"
  "check_nav_map (navigasi vs SSOT)|python scripts/check_nav_map.py"
  "guard:modal_dismiss (INV-UI-01, modal auto-close)|python scripts/guardrails/verify_modal_dismiss.py"
  # FASE P4 — konsistensi tombol "Buat": WAJIB pop-up, bukan form yang menyelip di tengah
  # halaman (form inline mendorong daftar data ke bawah lipatan sehingga pengguna sering
  # tak sadar formnya terbuka lalu menyimpulkan "tombolnya tidak berfungsi"). Penjaga ini
  # juga menangkap TOMBOL MATI (state dinyalakan tetapi tak pernah dirender) dan menuntut
  # setiap pengecualian (inline / pindah halaman) punya ALASAN tertulis.
  "guard:create_modal SELF-TEST (bukti-merah penjaga create pop-up)|python scripts/audit_create_modal.py --self-test"
  "guard:create_modal (INV-UI-05, tombol Buat = pop-up konsisten)|python scripts/audit_create_modal.py"
  # FASE P5 — dialog BAWAAN PERAMBAN dilarang. Terukur pada kode sebelum P5:
  # `alert()` 36× · `confirm()` 21× · `prompt()` 4× = **61 dialog di 21 berkas**.
  # Kotak itu memblokir seluruh halaman (operator gudang menyimpulkan aplikasi hang lalu
  # menekan tombol dua kali), tak bisa diberi konteks/nominal, tak bisa MENUNTUT ALASAN
  # untuk aksi yang membalik uang/stok, bisa dibungkam permanen oleh peramban (sesudah
  # itu `confirm()` mengembalikan false TANPA bertanya → tombol tampak mati), dan tak
  # terlihat oleh agen uji sehingga alur kritis tak bisa diverifikasi otomatis.
  # Penjaga juga memastikan `<ConfirmHost/>` ter-mount di root — tanpa itu penggantinya
  # (`askConfirm`) gagal SENYAP dan semua tombol hapus/batalkan tampak mati.
  "guard:blocking_dialogs SELF-TEST (bukti-merah + anti tuduh palsu)|python scripts/guardrails/verify_blocking_dialogs.py --self-test"
  "guard:blocking_dialogs (INV-UI-06, alert/confirm/prompt dilarang)|python scripts/guardrails/verify_blocking_dialogs.py"
  # FASE P6 — daftar berhalaman WAJIB bisa dibawa ke Excel, dan berkasnya wajib BENAR.
  # Sebelum P6 ada 12 daftar berhalaman dan NOL yang bisa diunduh — pemilik yang ingin
  # merekap harus menyalin layar 20 baris sekali angkat. Dua mode busuk yang dijaga:
  #  (A) daftar berhalaman BARU lupa diberi `exportConfig` (pasti terjadi: `PaginationBar`
  #      dipasang karena tanpa itu halaman 2 tak bisa dibuka, `exportConfig` tidak);
  #  (B) CSV-nya rusak SENYAP — pemisah `,` membuat Excel wilayah Indonesia menumpuk
  #      semua kolom di kolom A; sel bermuatan `;`/kutip yang tak dibungkus MENGGESER
  #      kolom di kanannya (angka pindah kolom: tetap bisa di-SUM, hasilnya salah);
  #      desimal titik dibaca sebagai teks; sel diawali `=`/`+`/`@` DIEKSEKUSI Excel.
  # Karena (B) soal PERILAKU (bukan pola teks), penjaga ini MENJALANKAN
  # `utils/csvExport.js` dengan Node dan menguji keluarannya — 20 kasus.
  "guard:list_export SELF-TEST (bukti-merah + CSV rusak harus memerah)|python scripts/guardrails/verify_list_export.py --self-test"
  "guard:list_export (INV-UI-07, daftar berhalaman wajib bisa diunduh)|python scripts/guardrails/verify_list_export.py"
  # FASE P7 — PANEL RINCIAN wajib pop-up. `INV-UI-05` hanya menjaga tombol "Buat", jadi
  # kelas bug yang SAMA masih hidup untuk panel rincian dan lolos berkali-kali:
  # terukur 9 layar merender panel detail sebagai SAUDARA di bawah tabelnya. Pada
  # `ar-aging` urutannya [tabel] → [baris TOTAL] → [catatan kaki] → [panel], sehingga
  # setelah mengklik baris TIDAK ADA perubahan yang terlihat — pengguna menyimpulkan
  # kliknya tak berfungsi lalu mengklik baris lain, dan panel di bawah berganti isi
  # tanpa dia tahu. Penjaga menelusuri ke berkas ANAK (panel yang overlay-nya ada di
  # berkas lain) dan MENGENALI master-detail 2 kolom sebagai sah (rincian di SAMPING
  # daftar tetap dalam pandangan). Bukti-merah pada kode sebelum P7: 9 pelanggaran.
  "guard:detail_modal SELF-TEST (bukti-merah + anti tuduh palsu)|python scripts/guardrails/verify_detail_modal.py --self-test"
  "guard:detail_modal (INV-UI-08, panel rincian wajib pop-up)|python scripts/guardrails/verify_detail_modal.py"
  # FASE T (penutupan) — INV-UI-09. Kelas bug yang tak terlihat gate mana pun: komponen
  # PEMILIH (pemicu + pop-up dalam satu komponen: ProductSelect · MakloonSelect ·
  # PantoneFinder) dipakai di dalam `<Field>` yang merender `<label>`. Aktivasi `<label>`
  # DITERUSKAN peramban ke tombol pemicunya, jadi begitu pengguna memilih satu baris,
  # pop-upnya TERBUKA KEMBALI (kotak cari kosong) dan menutupi tombol berikutnya.
  # Terukur 2026-08-19 di peramban: 3 komponen × 9 tempat pakai, tanpa satu pun galat.
  # `e.stopPropagation()` tidak menolong (React memasang pendengarnya di akar dokumen,
  # label sudah dilewati lebih dulu) — obatnya struktural: `createPortal` ke body.
  "guard:picker_portal SELF-TEST (bukti-merah + anti tuduh palsu, 16 kasus)|python scripts/guardrails/verify_picker_portal.py --self-test"
  "guard:picker_portal (INV-UI-09, pemilih wajib ber-portal · pop-up bukan anak <label>)|python scripts/guardrails/verify_picker_portal.py"
  # FASE P5 — baseline UX (loading/empty/chart) akhirnya jadi GATE. Sebelum ini
  # `ux_audit.py` hanya dijalankan manual, tak punya `--self-test`, dan angkanya tak
  # pernah dibuktikan: dari 22 "ERROR" yang dilaporkannya, 17 ternyata TUDUHAN PALSU
  # (komponen penampil yang datanya dari props dituduh "tanpa loading"; penjaga
  # `length > 0` & pesan kosong di komponen anak tak dikenali; kata "posting"/"loading"
  # di kalimat JSX dihitung sebagai bukti adanya indikator). Detektornya dibuat
  # SADAR-RUJUKAN + diberi self-test dua arah, lalu 5 gap NYATA diperbaiki
  # (halaman keuangan kosong tanpa kalimat, matriks izin kosong, grafik ekuitas kosong,
  # kartu buka-periode yang melompat masuk) → sekarang 0 ERROR dan dikunci di sini.
  # FASE P6 — aturan W2 (`<select>` bawaan peramban) DINAIKKAN jadi E4/ERROR setelah 13
  # dropdown bawaan terakhir dikonversi ke `KNSelect`: angkanya 0, jadi bisa ditegakkan
  # keras. Detektornya lebih dulu dibuat membaca kode TERSTRIP — versi teks-mentah
  # menuduh palsu `components/KNSelect.jsx` sendiri, berkas yang justru penggantinya.
  "ux_audit SELF-TEST (bukti-merah baseline UX + anti tuduh palsu)|python scripts/ux_audit.py --self-test"
  "ux_audit --strict (INV-UX-01, loading/empty/chart baseline)|python scripts/ux_audit.py --strict"
  # FASE G-0 — satu sumber kebenaran konfigurasi. `--strict` memerah bila ada setting
  # tersembunyi/tombol palsu/mati ATAU ada layar lain yang menulis konfigurasi.
  "config_wiring (INV-CFG-01/04, satu sumber kebenaran)|python scripts/audit_config_wiring.py --strict"
  # Bukti-merah (aturan repo #6): guardrail-nya sendiri harus terbukti bisa memerah.
  # Bagian [6] self-test juga membuktikan optimasi index == hasil regex lama.
  "config_wiring SELF-TEST (bukti-merah guardrail)|python scripts/audit_config_wiring.py --self-test"
  # FASE G-4 — hook penautan relasi WAJIB ada di titik lahir tiap dokumen turunan
  # (statik: baca kode). Self-test membuktikan audit ini benar-benar bisa memerah.
  "audit_doc_refs SELF-TEST (bukti-merah relasi dokumen)|python scripts/audit_doc_refs.py --self-test"
  # BAHASA — antarmuka WAJIB Bahasa Indonesia. Sebelum ini "sudah Indonesia" hanya
  # klaim prosa: satu berkas diterjemahkan, berkas berikutnya kembali Inggris tanpa
  # ada yang memerah. `--strict` memerah bila ADA label Inggris yang dilihat pengguna.
  "audit_i18n_id (label antarmuka Bahasa Indonesia)|python scripts/audit_i18n_id.py --strict"
  "audit_i18n_id SELF-TEST (bukti-merah guardrail bahasa)|python scripts/audit_i18n_id.py --self-test"
  "fix_i18n_id SELF-TEST (codemod tak boleh sentuh kode)|python scripts/fix_i18n_id.py --self-test"
  # INV-UI-02 — id teknis entitas (`ent_ksc`) TIDAK boleh tampil ke pengguna.
  # Terukur 2026-07-29: 5 layar membaca `entity.name` padahal `/api/entities` hanya
  # punya `legal_name`/`short_name`, sehingga POS/Pengaturan/Insentif menampilkan
  # `ent_ksc` dan pilihan entitas Payroll KOSONG. Self-test = bukti-merah.
  "guard:entity_label (INV-UI-02, id entitas tak boleh tampil)|python scripts/guardrails/verify_entity_label.py --self-test"
  # INV-UI-03 — kegagalan backend TIDAK boleh hilang tanpa jejak di layar.
  # Terukur 2026-07-30 (penutupan G-9): 2 layar keuangan terbaru mengirim objek error
  # axios lewat prop `error=` padahal <ErrorNotice> menerima `message=` → komponen
  # `return null`, sehingga SEMUA penolakan backend (alasan wajib · bukti wajib · kasus
  # kembar · 403 entitas lain) tak terlihat sama sekali. Uji backend tetap 100% hijau,
  # jadi hanya penjaga di lapisan UI yang bisa menangkapnya. Self-test = bukti-merah.
  "guard:error_notice (INV-UI-03, error tak boleh senyap)|python scripts/guardrails/verify_error_notice.py --self-test"
  # INV-ROLE-01 — peran hanya dari REGISTRY & wewenang hanya dari IZIN.
  # Terukur 2026-08-14 (FASE E-8): dua peran baru membongkar 3 kebiasaan lama —
  # (a) peta label peran lokal berisi 4 peran → layar menampilkan "Sales_admin";
  # (b) `["manager","admin"].includes(role)` di layar Faktur Pajak → Finance melihat
  #     layarnya TANPA tombol walau server mengizinkan; sebaliknya tombol uang/pajak
  #     tetap muncul untuk sales lalu ditolak 403 di belakang;
  # (c) registry peran bercabang di 3 berkas (server · layar · beranda).
  # Self-test = bukti-merah (menyuntik pelanggaran → wajib tertangkap).
  "guard:role_label (INV-ROLE-01, peran dari registry & izin)|python scripts/guardrails/verify_role_label.py --self-test"
  # INV-UI-04 — field TURUNAN (hanya ada di respons DETAIL) tak boleh dibaca dari
  # objek hasil DAFTAR. Terukur 2026-08-15 (penutupan E-6, ditemukan uji LAYAR):
  # pita "Dipenuhi dari Badan Usaha Lain" (E9.2 · US23/US24 — "diambil dari CV Kanda
  # Suka lewat KSC/IC-00006") TIDAK PERNAH tampil. Backend benar & POC E-9 hijau
  # 44/44 karena keduanya memeriksa `GET /sales-orders/{id}`; yang salah adalah dari
  # mana LAYAR mengambilnya — `OrderDetailPanel` membaca `sel.interco_supply`
  # sedangkan `sel` berasal dari `GET /dashboard` → `orders[]` yang TIDAK memuat
  # field turunan itu. Akibatnya `(sel.interco_supply || []).length > 0` selalu 0:
  # blok JSX di-skip tanpa error, tanpa layar merah, tanpa jejak konsol.
  # Risiko nyata: orang menerbitkan permintaan beli KEDUA untuk barang yang sudah
  # di jalan dari PT saudara. Hanya penjaga di lapisan aliran-data UI yang bisa
  # menangkap kelas bug ini.
  "guard:derived_fields (INV-UI-04, field turunan tak boleh dari respons daftar)|python scripts/guardrails/verify_derived_fields.py"
  # FASE E-0 (E0.9/E0.10) — PAGAR ANTI-REGRESI ISOLASI ENTITAS.
  # Lapisan statik saja di kolam paralel (tanpa DB/HTTP tidak berlaku, jadi ini
  # memakai DB tapi read-only & cepat). Sapuan runtime penuh dijalankan di blok
  # runtime di bawah. Self-test = bukti-merah bahwa pagar ini benar-benar memerah.
  "audit_entity_isolation SELF-TEST (bukti-merah pagar isolasi)|python scripts/audit_entity_isolation.py --self-test"
  # FASE E-3 (user story 7) — PAGAR TULIS MODE "SEMUA ENTITAS".
  # Terukur 2026-08-10: POST /api/customers dengan header `X-Entity-Id: all`
  # mengembalikan 200 dan dokumennya mendarat di badan usaha HOME pengguna —
  # admin membuat dokumen sambil melihat gabungan, sistem memilih bukunya
  # diam-diam. Keputusan tabel rute ada di `backend/entity_write_guard.py`;
  # self-test ini membuktikan pagar bisa MEMERAH (tanpa butuh DB/HTTP).
  "guard:write_scope SELF-TEST (INV-ENTITY-02, mode gabungan hanya-lihat)|cd backend && python -m entity_write_guard --self-test"
  # FASE E-4 (E4.1) — PAGAR PEMAKAIAN GUDANG PER BADAN USAHA.
  # Aturan "gudang khusus" hanya sekuat titik terlemahnya: satu endpoint tulis baru
  # yang menerima `warehouse_id` tanpa memanggil `assert_usable` sudah cukup untuk
  # menaruh barang di gudang badan usaha lain. Gate statik ini menyapu SELURUH
  # router (AST, tanpa server) dan MEMERAH bila ada endpoint tulis pemilih gudang
  # yang tak berpagar; pembebasan wajib ditulis eksplisit beserta alasannya.
  "guard:warehouse_scope SELF-TEST (E4.1, gudang khusus badan usaha)|python scripts/audit_warehouse_scope.py --self-test"
)

STATIK_TMP="$(mktemp -d /tmp/kn_gate_statik.XXXXXX)"
trap 'rm -rf "$STATIK_TMP"' EXIT

statik_pool () {  # jalankan semua gate statik dgn maksimal $JOBS pekerja
  local i=0 spec label cmd
  for spec in "${STATIK[@]}"; do
    label="${spec%%|*}"; cmd="${spec#*|}"
    (
      s=$SECONDS
      out="$(cd "$ROOTDIR" && bash -c "$cmd" 2>&1)"; rc=$?
      printf '%s' "$out" > "$STATIK_TMP/$i.out"
      printf '%s %s\n' "$rc" "$((SECONDS-s))" > "$STATIK_TMP/$i.rc"
    ) &
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 0.2; done
    i=$((i+1))
  done
  wait
}

collect_statik () {  # baca hasil kolam → cetak berurutan + isi SNAMES/SRESULTS
  local i=0 spec label rc dt
  echo -e "\n${CYAN}${BOLD}══ HASIL GATE STATIK (kolam paralel · ${JOBS} pekerja) ══${RST}"
  for spec in "${STATIK[@]}"; do
    label="${spec%%|*}"
    read -r rc dt < "$STATIK_TMP/$i.rc" 2>/dev/null || { rc=1; dt=0; }
    echo -e "\n${CYAN}${BOLD}▶ ${label}${RST}"
    cat "$STATIK_TMP/$i.out" 2>/dev/null
    if [ "$rc" -eq 0 ]; then
      echo -e "  ${GREEN}✓ ${label} PASS${RST} (${dt}s)"; SNAMES+=("$label"); SRESULTS+=("PASS (${dt}s)")
    else
      echo -e "  ${RED}✗ ${label} FAIL (rc=$rc)${RST} (${dt}s)"; SNAMES+=("$label"); SRESULTS+=("FAIL (${dt}s)"); OVERALL=1
    fi
    i=$((i+1))
  done
}

# Mulai gate statik. Di mode ber-DB ia menumpang jalan bersama blok DB/runtime.
STATIK_PID=""
if [ "$PARALLEL" -eq 1 ]; then
  echo -e "${YEL}  Gate STATIK dijalankan di latar belakang (${#STATIK[@]} gate · ${JOBS} pekerja).${RST}"
  statik_pool & STATIK_PID=$!
else
  for spec in "${STATIK[@]}"; do run_gate "${spec%%|*}" "${spec#*|}"; done
fi

# --- Deteksi backend + auth ---
BACKEND_UP=0; AUTH_READY=0
if [ "$MODE" != "quick" ]; then
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/ 2>/dev/null | grep -qE "^[2-4]"; then
    BACKEND_UP=1; echo -e "${GREEN}  Backend RUNNING${RST}"
    AC=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{}' 2>/dev/null)
    if [ "$AC" != "404" ] && [ "$AC" != "000" ]; then AUTH_READY=1; echo -e "${GREEN}  Auth tersedia (HTTP $AC) — gate runtime dijalankan${RST}"; else echo -e "${YEL}  Auth belum ada (HTTP $AC) — gate runtime di-SKIP${RST}"; fi
  else
    echo -e "${YEL}  Backend down — gate runtime di-SKIP (Phase 0).${RST}"
  fi
else
  echo -e "${YEL}  Mode --quick: hanya gate STATIK (tanpa DB/backend/seed).${RST}"
fi

# numeric_bounds: statik + RUNTIME (login admin + probe POST). WAJIB berurutan &
# SEBELUM seed — kalau berbarengan dgn seed, user admin sedang dihapus/ditulis.
run_gate "guard:numeric_bounds (INV-NUM-01, statik+runtime)" "python scripts/guardrails/verify_numeric_bounds.py"

if [ "$MODE" = "quick" ]; then
  skip_gate "seed_realistic" "mode --quick"
  skip_gate "verify_data_integrity" "mode --quick"
  skip_gate "gate runtime (IDOR/race/state/sweep/health)" "mode --quick"
  skip_gate "INV-GATE-01 anti-residu" "mode --quick"
else

# ============ SEED + DATA (butuh Mongo) ============
if [ -n "${MONGO_URL:-}" ]; then
  run_gate "seed_realistic (data uji bersih)" "python seed_realistic.py >/dev/null 2>&1"
  run_gate "verify_data_integrity (229 invarian domain/GL/alert/ledger/config/relasi/pembayaran/selisih/bank/kasus/kontrabon/antar-entitas)" "python scripts/verify_data_integrity.py"
  # F0-C — kepatuhan multi-entity: (1) DB tanpa dokumen SCOPED tanpa field entitas,
  # (2) STATIK: router yang query koleksi SCOPED WAJIB memakai `entity_scope`.
  # Dulu hanya dijalankan lewat seed_reset.sh sehingga `gate.sh` bisa HIJAU
  # padahal ada 5 kebocoran lintas-PT. Sekarang gate utama juga memeriksanya.
  run_gate "verify_entity_scoping (F0-C, DB + STATIK anti-kebocoran PT)" "cd backend && python -m scripts.verify_entity_scoping"
  # FASE G-4 — cakupan & kesehatan relasi dokumen pada DATA (bukan hanya kode):
  # surat yang punya sumber WAJIB menaut sumbernya; tak ada tautan menggantung.
  run_gate "audit_doc_refs (INV-REF cakupan data + kesehatan tautan)" "python scripts/audit_doc_refs.py --strict"
  # INV-ROLL-01 — IDENTITAS ROLL (statik KODE + DATA). Nomor roll adalah identitas kain
  # di dunia nyata (dicetak di label, dipindai di rak, dicari di layar). Ternyata ia
  # dibuat di 9 tempat dengan 4 cara dan tak pernah dijaga. Terukur 2026-08-18:
  #   · `return_service` menulis ke `roll_number` (bukan `roll_no`) → SETIAP roll hasil
  #     retur pelanggan tampil TANPA nomor & tak bisa dicari (1 dari 59 roll, juga
  #     tanpa `unit`). Drift-nya bertahan karena field salah itu punya PEMBACANYA
  #     SENDIRI (`ReturnQuarantinePanel` + 2 service ber-`roll_no or roll_number`),
  #     jadi satu layar tampak benar sementara layar lain kosong.
  #   · 3 nomor dipakai 10 roll (`RL-00002` dipegang DUA badan usaha; `RL-00042` oleh
  #     4 roll) karena penghitung LOKAL yang selalu mulai dari 1, `count_documents()+1`,
  #     dan potongan roll yang menyalin nomor induk lewat `dict(roll)`.
  # Bukti-merah pada kode SEBELUM perbaikan: 19 pelanggaran (7 K1 · 8 K2 · 4 K3);
  # lapisan DATA dibuktikan memerah untuk keempat pemeriksaannya (D1–D4) dengan nol residu.
  run_gate "guard:roll_identity SELF-TEST (bukti-merah + anti tuduh palsu)" "python scripts/guardrails/verify_roll_identity.py --self-test"
  run_gate "guard:roll_identity (INV-ROLL-01, satu nomor untuk satu roll)" "python scripts/guardrails/verify_roll_identity.py"
else
  skip_gate "seed_realistic" "MONGO_URL tak tersedia"
  skip_gate "verify_data_integrity" "MONGO_URL tak tersedia"
  skip_gate "audit_doc_refs" "MONGO_URL tak tersedia"
fi

# ============ RUNTIME (butuh backend + auth) ============
if [ $AUTH_READY -eq 1 ]; then
  # Sidik jari SEBELUM gate runtime → dipakai gate anti-residu di bawah.
  python scripts/gate_residue.py --save || true

  run_gate "guard:cross_entity (INV-ENTITY-01, IDOR multi-PT)" "python scripts/guardrails/verify_cross_entity.py"
  run_gate "guard:nonfinancial_sweep (INV-ENTITY-01+, IDOR non-finansial)" "python scripts/guardrails/verify_nonfinancial_sweep.py"
  # F0-C — bukti PERILAKU (bukan statik) untuk 3 endpoint yang pernah bocor lintas-PT:
  # kartu asal produk · roll retur · jejak konversi satuan. Memakai BUKTI-MERAH
  # (fixture di PT lain dibuat lebih dulu) supaya "0 kebocoran" tidak bisa palsu.
  run_gate "POC F0-C (isolasi lintas-entitas: kartu asal · roll retur · jejak UoM)" "python backend/test_f0c_scoping_leak_poc.py"
  # FASE E-0 — PAGAR ANTI-REGRESI ISOLASI ENTITAS (E0.9 + E0.10). Inilah gate yang
  # mencegah 21 kebocoran yang baru ditutup kembali muncul lewat router baru:
  #   [1] SAPUAN 301 endpoint GET × 2 sales beda entitas → MERAH bila ada `ent_*` asing
  #   [2] IDOR dokumen PT lain (15 endpoint by-id) → wajib 403/404
  #   [3] STATIK: registry lengkap · router ter-scope · nol dokumen tanpa entitas
  run_gate "audit_entity_isolation (E0.9/E0.10 — 0 kebocoran lintas-entitas)" "python scripts/audit_entity_isolation.py"
  # FASE E-0 — POC bukti-merah 21 kebocoran L1–L21 (satu berkas, self-cleanup).
  run_gate "POC FASE E-0 (bukti-merah L1–L21: notifikasi·denda·audit·lot·AR·transfer·dokumen·pratinjau)" "python backend/test_core_e0_isolation_poc.py"
  # FASE E-3 (user story 7) — POC runtime pagar tulis mode gabungan (self-cleanup).
  run_gate "POC FASE E-3 (mode “Semua Entitas” hanya-lihat: 409 menuntun · master bersama tetap boleh)" "python backend/test_core_e3_write_guard_poc.py"
  # FASE E-4 (E4.1 + E4.7) — POC runtime gudang bersama/khusus & harga per badan
  # usaha (self-cleanup, nol residu). Menjaga dua hal yang mudah rusak diam-diam:
  # (a) gudang khusus badan usaha lain tidak boleh dipakai/terlihat,
  # (b) satu produk boleh berbeda harga per badan usaha, dan harga TERBARU-lah
  #     yang dipakai (bug hari-sama yang ditemukan POC ini).
  run_gate "POC FASE E-4 (gudang bersama/khusus · harga per badan usaha · CSV)" "python backend/test_core_e4_poc.py"
  # FASE E-4 (E4.2/E4.3) — POC master BERLAPIS global → badan usaha (self-cleanup).
  # Menjaga tiga hal yang paling mudah rusak diam-diam saat koleksi master pindah
  # SHARED → SCOPED: (a) baris global TIDAK boleh hilang dari layar, (b) daftar
  # efektif tidak boleh kembar (dropdown pesanan/POS), (c) mengubah baris global
  # dari konteks satu badan usaha harus DITOLAK, bukan mengubah nilai seluruh grup.
  run_gate "POC FASE E-4 master berlapis (global→badan usaha · override · kop surat per PT)" "python backend/test_core_e4_master_layers_poc.py"
  # FASE E-5 — POC VISIBILITAS STOK (Keputusan #1 pemilik). Menjaga empat hal yang
  # mudah rusak diam-diam begitu ada router/enrichment stok baru:
  #   (a) papan stok peran non-lintas: rincian HANYA badan usaha sendiri, angka grup
  #       tetap ada sebagai `global_total` (agregat, tanpa rincian gudang PT lain);
  #   (b) `/pegging/rolls` ter-scope `owner_entity_id`;
  #   (c) mutasi pindah-kepemilikan tetap TERLIHAT (jejak wajib) tetapi badan usaha
  #       lawan hanya boleh muncul sebagai NAMA SINGKAT — bukan id teknis `ent_*`,
  #       bukan nama badan hukum;
  #   (d) Kartu Riwayat Produk `/history/{id}` ter-scope (dulu sama sekali tidak,
  #       sales PT-A ikut membaca mutasi PT-B lengkap dengan lot & gudangnya).
  run_gate "POC FASE E-5 (papan stok agregat · pegging · mutasi lintas-PT nama singkat · kartu riwayat)" "python backend/test_core_e5_visibility_poc.py"
  run_gate "POC FASE E-7 (pagar entitas grup · HPP taksiran berlabel · permintaan internal · kas grup dihapus · pinjaman & pindah aset antar-PT)" "python backend/test_core_e7_interco_poc.py"
  # FASE E-8 GELOMBANG 1 — DUA PERAN BARU (`sales_admin` · `finance`). Menjaga enam hal
  # yang mudah rusak diam-diam begitu ada endpoint/peran/menu baru:
  #   (a) registry peran IDENTIK di server · layar · beranda (peran baru tak boleh
  #       mendarat di layar kosong);
  #   (b) pemisahan tugas E8.2: sales kehilangan faktur pajak, kwitansi AR, keputusan
  #       selisih bayar, pegging & "tandai diterima" — tetapi tetap boleh MELIHAT;
  #   (c) Admin Sales boleh Konfirmasi/Tandai-diterima/PR/ambil-dari-PT-lain, TIDAK
  #       boleh menyentuh uang, pajak, settlement, maupun menyetujui nilai;
  #   (d) Finance boleh uang masuk & pajak keluaran, TIDAK boleh membuat pesanan;
  #   (e) penugasan banyak badan usaha + mode gabungan yang benar-benar menggabungkan
  #       (dan tetap HANYA-LIHAT), isolasi peran 1-penugasan tak berubah;
  #   (f) peran bukan teks bebas: salah ketik ditolak dengan menyebut pilihan sah.
  run_gate "POC FASE E-8 G1 (peran sales_admin & finance · pemisahan tugas · penugasan entitas)" "python backend/test_core_e8_roles_poc.py"
  # FASE E-8 GELOMBANG 2 & 3 — MEJA KERJA · VERIFIKASI · KEPUTUSAN PEMENUHAN.
  # POC ini sudah 92/92 sejak sesi 2026-08-14 tetapi BELUM terdaftar sebagai pagar,
  # jadi seluruh Meja Admin Sales & Meja Finance bisa memerah diam-diam. Yang dijaga:
  #   (a) US11 kepemilikan data sales berpagar sampai ke DETAIL (membuka pesanan rekan
  #       lewat id langsung harus 403 — membatasi daftar saja hanyalah kosmetik);
  #   (b) US12 perjalanan pesanan read-only menjawab "pesanan saya di mana?" tanpa
  #       membuka layar gudang (`/api/wms/tasks` tetap 403 untuk sales);
  #   (c) US15 Meja Admin Sales = 8 antrean berjumlah, dan faktur pajak / uang masuk
  #       TIDAK boleh nyasar ke meja ini (itu wewenang Finance);
  #   (d) US16/US22 tiga pilihan pemenuhan beserta KELAYAKAN + alasan bila mati, lalu
  #       "ambil dari PT lain" jalan ujung-ke-ujung (PIN → transaksi antar-PT kembar →
  #       jejak dua arah ke pesanannya, E8.12) dan ambang rupiah benar-benar menahan;
  #   (e) US17 verifikasi administratif terpisah dari persetujuan manajer, dan
  #       sakelarnya bawaan MATI (instalasi lama tak berubah perilaku);
  #   (f) US20 Meja Finance = 5 antrean; Finance tak bisa membuat/mengonfirmasi pesanan.
  run_gate "POC FASE E-8 G2/G3 (meja admin sales & finance · verifikasi · keputusan pemenuhan)" "python backend/test_core_e8_desk_poc.py"
  # FASE E-9 — RANTAI JUAL → BELI INTERNAL ANTAR-PT → RETUR BERANTAI (skenario pemilik).
  # Satu skrip menjalankan rantai penuh lewat HTTP nyata dan menjaga enam sambungan
  # yang dulu putus/berbahaya (`ANALISIS_FLOW_RETUR_BERANTAI.md`):
  #   R1 penerimaan barang antar-PT MEMICU pemenuhan pesanan yang menunggu stok
  #      (+ pemberitahuan ke Admin Sales yang menyebut nomor pesanannya);
  #   R2 transaksi antar-PT tertaut pesanan pemicunya (layar pesanan & Papan Pending SO);
  #   R3 jalur pindah-kepemilikan at-cost DITOLAK untuk barang asal pembelian internal,
  #      dengan kalimat yang menuntun ke Retur Antar-PT;
  #   R4 yang dikirim balik adalah roll HASIL RETUR PELANGGAN — roll bagus tetap tinggal
  #      (dijaga dua mekanisme: `roll_ids` pilihan manusia + prioritas `origin_type`);
  #   R5 jejak asal (supplier/PO) & riwayat perolehan SELAMAT melewati retur pelanggan +
  #      dua kali pindah kepemilikan — tanpa membocorkan id teknis badan usaha (E5.3);
  #   R6 ketiga retur saling tertaut, terbaca dari dokumen MANA PUN, dan rincian
  #      badan usaha lain diringkas untuk peran non-lintas-PT.
  # Self-cleanup: memakai produk `prod_e9_*` sendiri lalu menghapus seluruh jejaknya.
  run_gate "POC FASE E-9 (rantai jual→beli internal antar-PT→retur berantai · 41 pemeriksaan)" "python backend/test_core_rantai_retur_poc.py"
  # UTANG MIGRASI (ii) FASE E-8 — "CEK KENYATAAN PERAN". Menjaga janji bahwa daftar
  # "akun `manager` yang sebenarnya Admin Sales/Finance" dihitung dari JEJAK NYATA:
  #   R1 akun warisan ditemukan (kuasa berlebih → Admin Sales) DENGAN bukti per izin;
  #   R2 manajer sungguhan TIDAK ikut dituduh (tanpa cek ini "temuan" tak ada artinya);
  #   R3 akun tanpa jejak tidak ditebak · R4 admin tidak dinilai dari aktivitas;
  #   R5 satu orang mengerjakan pesanan DAN uang/pajak → usulan DUA akun (SD2);
  #   R6 jejak di luar izin peran sekarang ditandai per baris;
  #   R7 laporan wewenang hanya untuk yang berhak (sales/sales_admin/finance → 403);
  #   R8 terap HANYA menerima peran usulan (salah-klik tidak memindahkan wewenang);
  #   R9 terap mencabut sesi + menyimpan POTRET BUKTI di jejak audit;
  #   R10 BUKTI-MERAH: mencabut `order.verify` dari matriks izin yang BERLAKU harus
  #       mengubah usulan — membuktikan tidak ada tabel kedua yang bisa bercabang.
  run_gate "POC Cek Kenyataan Peran (utang migrasi ii E-8 · usulan peran dari jejak nyata)" "python backend/test_core_role_reality_poc.py"
  # AUDIT SALES vs ADMIN SALES (item yang diparkir di plan.md §8, dibuka 2026-08-15).
  # Menutup kelas cacat yang tak dilihat gate mana pun: **menu terlihat, datanya 403**.
  # `check_nav_map` menilai navigasi terhadap dirinya sendiri; gate isolasi menilai
  # kebocoran antar-PT; tidak ada yang menilai "menu ini benar-benar bisa dipakai oleh
  # peran yang melihatnya". Audit ini menyilangkan navigasi NYATA (sidebar + tab hub,
  # termasuk overlay ROLE_NAV) dengan HTTP nyata memakai token tiap peran.
  # Ada `--self-test` (bukti-merah) supaya penilaiannya sendiri bisa dipercaya.
  run_gate "audit_sales_roles_ux SELF-TEST (bukti-merah penilaian layar mati)" "python scripts/audit_sales_roles_ux.py --self-test"
  # Diperluas 2026-08-15 ke SEMUA peran + "panel mati" (403 di satu panel) kini TEMUAN,
  # bukan peringatan kuning. Sebelumnya 11 kasus nyata hidup di bawah warna kuning itu,
  # termasuk finance yang kehilangan SELURUH referensi layar "Kasus Keuangan" hanya
  # karena satu `GET /suppliers` 403 ikut di dalam `Promise.all` yang sama.
  run_gate "audit_sales_roles_ux (SEMUA peran: nol layar & panel mati)" "python scripts/audit_sales_roles_ux.py"
  # POC F-2 — izin baca yang diberikan TERBUKTI bekerja, pagar TIDAK ikut longgar,
  # KPI beranda tidak berbohong, tombol lahir dari izin. Termasuk BUKTI-MERAH:
  # mencabut izinnya dari matriks yang BERLAKU harus membuat POC ini memerah.
  run_gate "POC F-2 Akses & UI/UX per peran (izin baca · pagar · KPI jujur · bukti-merah)" "python backend/test_core_role_access_poc.py"
  # POC F-1b — UTANG MIGRASI (i): kas tingkat grup → per badan usaha (E7e).
  # Data demo hari ini NOL baris tingkat grup, jadi menjalankan alat migrasinya di data
  # bersih hanya mencetak "tidak ada yang perlu dimigrasikan" — itu kebetulan, bukan bukti.
  # POC ini MEMBUAT ULANG keadaan warisan (1 rekening "Kas Besar Grup" + 13 transaksi
  # dengan 4 lapis bukti + 2 baris tak terbuktikan), menjalankan alatnya sungguhan, lalu
  # memeriksa baris demi baris; semuanya dipulihkan (nol residu). POC ini menemukan &
  # menutup cacat nyata: baris yang pemiliknya diputuskan ORANG lewat kasus keuangan
  # tetap menunjuk rekening GRUP, sehingga rekening itu tak pernah bisa dinonaktifkan.
  run_gate "POC F-1b Migrasi kas tingkat grup (utang migrasi i · 4 lapis bukti · idempotent)" "python backend/test_core_group_cash_migration_poc.py"
  # PENGINGAT ANTREAN PERSETUJUAN (permintaan pemilik 2026-08-15). KPI yang benar hanya
  # bekerja kalau orangnya membuka layar; pengingat menutup celah itu — dan pengingat
  # adalah fitur yang paling mudah "hijau tapi bohong" (angka basi · mengabaikan ambang
  # pemilik · menggandakan diri tiap penjadwal jalan). Ketiganya diuji dengan job NYATA,
  # termasuk BUKTI-MERAH: ambang dinaikkan lewat API Pusat Pengaturan → pengingat wajib
  # berhenti menyebut dokumen yang lebih muda dari ambang.
  run_gate "POC Pengingat Antrean Persetujuan (umur tunggu · eskalasi · idempotent · ambang pemilik)" "python backend/test_core_approval_reminder_poc.py"
  # FASE F-6 — keputusan pemilik atas §F-5 no.1: mesin persetujuan generik DICABUT
  # (nol produsen · nol pemakai di layar · akan jadi jalur penulisan status kedua ·
  # endpointnya tak berscope PT) lalu digantikan 14 ANTREAN NYATA yang selama ini tak
  # terhitung. POC membuktikan kedua sisinya + BUKTI-MERAH: suntik satu transfer
  # menunggu → KPI wajib bergerak; dihapus → kembali.
  run_gate "POC FASE F-6 (pensiun mesin generik · 14 antrean nyata · anti dobel-hitung)" "python backend/test_core_f6_approval_coverage_poc.py"
  # FASE F-6.7 — UTANG ALUR DIBAYAR. F-6 membebaskan 4 pintu keputusan dari INV-APPR-01
  # dengan alasan bertanda "UTANG ALUR": payroll & desain disahkan langsung dari `draft`
  # (draf yang masih dikerjakan tak bisa dibedakan dari yang siap disahkan), keputusan
  # selisih pembayaran dianggap tak bisa dihitung tanpa menebak, dan verifikasi
  # administratif SO belum punya baris antrean (terukur: 4 pesanan menunggu, KPI
  # menghitung 0). POC ini menjaga alur barunya: draf TIDAK BISA disahkan · "Ajukan"
  # memindahkannya ke antrean · tolak menuntut ALASAN yang tersimpan di dokumen ·
  # angka antrean naik/turun mengikuti kenyataan · dan nol pembebasan "UTANG ALUR" sisa.
  run_gate "POC FASE F-6.7 (langkah Ajukan payroll & desain · selisih bayar · verifikasi SO)" "python backend/test_core_f67_workflow_poc.py"
  # INV-HOME-01 — angka KPI beranda WAJIB sama dengan kenyataan di basis data.
  # Terukur 2026-08-15: KPI "Persetujuan Menunggu" 0 (menghitung koleksi
  # `approval_requests` yang NOL pemanggil) sementara rincian di layar yang sama 6 dan
  # kenyataan 16. Angka yang berbohong tidak memicu error apa pun — hanya penjaga
  # seperti ini yang bisa menangkapnya.
  run_gate "guard:home_kpi SELF-TEST (bukti-merah penjaga KPI beranda)" "python scripts/guardrails/verify_home_kpi.py --self-test"
  run_gate "guard:home_kpi (INV-HOME-01, KPI beranda = antrean nyata)" "python scripts/guardrails/verify_home_kpi.py"
  # FASE F-6 — pintu keputusan tanpa antrean = KPI yang berbohong dengan selisih kecil.
  # Sapuan KODE (endpoint approve/reject/verify/decide) + sapuan DATA (status menunggu),
  # jadi antrean baru mustahil lahir tanpa yang menghitungnya.
  run_gate "guard:approval_queues SELF-TEST (bukti-merah penjaga antrean keputusan)" "python scripts/guardrails/verify_approval_queues.py --self-test"
  run_gate "guard:approval_queues (INV-APPR-01, tiap pintu keputusan punya antrean)" "python scripts/guardrails/verify_approval_queues.py"
  run_gate "guard:concurrency (INV-CONC-01, race/TOCTOU uang)" "python scripts/guardrails/verify_concurrency.py"
  run_gate "guard:state_machine (INV-STATE-01, transisi SO)" "python scripts/guardrails/verify_state_machine.py"
  # ── FASE L — LINI PRODUK (pembagian kerja MD: woven/knit/printing, bisa ditambah).
  # Tiga cara gagal yang semuanya SENYAP: kode lini asing (baris tak pernah cocok chip
  # apa pun → pekerjaan tak terlihat), turunan `line_codes[]` yang berbohong terhadap
  # `items[].line_code`, dan jalur tulis yang lupa menstempel (dokumen lahir tanpa lini
  # padahal produknya berlini). INV-LINE-02 menjaga lini tidak bertentangan dengan
  # fisika kain (`fabric_type`) — lini `woven`/`knit` mengikat, `printing` sengaja bebas.
  run_gate "guard:line_scope SELF-TEST (bukti-merah pagar lini, 15 kasus dua arah)" "python scripts/guardrails/verify_line_scope.py --self-test"
  run_gate "guard:line_scope (INV-LINE-01/02, kode dikenal · turunan jujur · snapshot lengkap)" "python scripts/guardrails/verify_line_scope.py"
  # POC FASE L — bukti bahwa lini benar-benar bisa ditambah pemilik TANPA ubah kode,
  # pagarnya keras (403 di API, bukan hanya UI disaring), snapshot riwayat tidak ikut
  # berpindah papan, dan dokumen lama tanpa lini TETAP terlihat (anti layar kosong).
  run_gate "POC FASE L (lini produk: master bertambah · pagar keras · snapshot · isolasi PT)" "python backend/test_core_lini_poc.py"
  # ── FASE T — TAHAPAN PROSES (termasuk SCREEN/kasa). Lima kegagalan senyap: tahap
  # yang masih dipakai dokumen dinonaktifkan · `process_type`/`stage` asing · tahap
  # pengubah kain tanpa pasangan di STAGE_TRANSITIONS (papan menawarkan langkah yang
  # mesin PASTI tolak) · `needs_vendor` tanpa satu pun mitra terdaftar (form SPK jadi
  # jalan buntu, dan karena keputusan 3b hanya MEMPERINGATKAN, di sinilah satu-satunya
  # tempat kelalaian itu terlihat) · aliran kain tidak tegas (mesin harus menebak apakah
  # stok bergerak).
  run_gate "guard:master_stages SELF-TEST (bukti-merah tahapan proses, 20 kasus dua arah)" "python scripts/guardrails/verify_master_stages.py --self-test"
  run_gate "guard:master_stages (INV-DOMAIN-06, master tahapan vs registry domain)" "python scripts/guardrails/verify_master_stages.py"
  # POC FASE T — bukti bahwa tahap baru bisa ditambah pemilik TANPA ubah kode, tahap
  # Screen tidak mengubah kain (qty keluar = qty masuk) & biayanya tetap masuk buku,
  # tahap terpakai tidak bisa dinonaktifkan, dan SPK lama dihitung ulang IDENTIK.
  run_gate "POC FASE T (tahapan proses: master bertambah · screen tak ubah kain · regresi identik)" "python backend/test_core_tahapan_poc.py"
  # ── FASE U — DUA SATUAN (jumlah roll + yard/kg/panel) di semua dokumen.
  # INV-UOM-02: kosakata satuan dokumen ⊆ master `uoms` (kode ∪ nama ∪ alias). Kelas
  # bug D1: dokumen menyimpan KATA (`yard`,`kg`,`meter`), master menyimpan KODE
  # (`YRD`,`MTR`) — tak satu pun cocok, sehingga pemilik yang menambah baris `KG` di
  # master TIDAK melihat perubahan apa pun di layar, dan satuan salah ketik (`hasta`)
  # tersimpan tanpa pernah ditolak sampai konversinya gagal jauh di kemudian hari.
  run_gate "guard:uom_vocab SELF-TEST (bukti-merah kosakata satuan, 23 kasus dua arah)" "python scripts/guardrails/verify_uom_vocab.py --self-test"
  run_gate "guard:uom_vocab (INV-UOM-02, satuan dokumen ⊆ master uoms · alias tak kembar · pemilih satuan dari master)" "python scripts/guardrails/verify_uom_vocab.py"
  # INV-QTY-01: satu fakta ("12 roll · 540 yard") muncul di ENAM tampilan (layar,
  # panel rincian, PDF, CSV, papan PO, kartu stok). Tiga cara gagal yang senyap:
  # (a) dokumen lama tanpa `qty_rolls` dicetak "0 roll" — pernyataan yang SALAH;
  # (b) satuan diketik keras di JSX (benar untuk woven, salah untuk knit/printing);
  # (c) dua cara menghitung satu angka (`roll_ids.length` vs `qty_rolls`).
  # Penjaga ini tidak hanya membaca pola: ia MENJALANKAN `utils/qtyDualCsv.js` dengan
  # Node dan `core_utils.qty_dual`/`pdf_resolvers._rolls_cell` dengan Python, lalu
  # menuntut keduanya sepakat — kalau layar dan PDF beda aturan, selisihnya baru
  # terlihat di depan pelanggan.
  run_gate "guard:qty_dual SELF-TEST (bukti-merah dua satuan, 32 kasus dua arah)" "python scripts/guardrails/verify_qty_dual.py --self-test"
  run_gate "guard:qty_dual (INV-QTY-01, dua satuan satu arti di layar · PDF · CSV)" "python scripts/guardrails/verify_qty_dual.py"
  # POC FASE U — bukti bahwa satu angka yang diketik admin sales muncul SAMA di enam
  # tampilan, turun serentak saat retur, dan dokumen lama tetap tampil "—".
  run_gate "POC FASE U (dua satuan: PO→terima→PDF/CSV · retur turun serentak · satuan lini · dokumen lama \"—\")" "python backend/test_core_dua_satuan_poc.py"
  run_gate "audit_endpoint_sweep (semua GET → 5xx · paralel)" "python scripts/audit_endpoint_sweep.py"
  run_gate "health_check (isi endpoint kritis)" "python scripts/health_check.py"

  # ANTI-RESIDU: gate tidak boleh mengubah data. Dulu SO-0006 dibatalkan,
  # 2 balance bergeser, +2 mutasi & +10 audit_logs setiap gate — tanpa terdeteksi.
  run_gate "INV-GATE-01 anti-residu (gate tak boleh merusak data)" "python scripts/gate_residue.py --check"
else
  skip_gate "guard:cross_entity (INV-ENTITY-01)" "auth belum ada / backend down"
  skip_gate "guard:nonfinancial_sweep (INV-ENTITY-01+)" "auth belum ada / backend down"
  skip_gate "guard:concurrency (INV-CONC-01)" "auth belum ada / backend down"
  skip_gate "guard:state_machine (INV-STATE-01)" "auth belum ada / backend down"
  skip_gate "audit_endpoint_sweep" "auth belum ada / backend down"
  skip_gate "health_check" "auth belum ada / backend down"
  skip_gate "INV-GATE-01 anti-residu" "auth belum ada / backend down"
fi

# ============ POC FASE (hanya --full) ============
if [ "$MODE" = "full" ]; then
  if [ $AUTH_READY -eq 1 ]; then
    # Sidik jari KEDUA — khusus fase POC. Sebelumnya anti-residu hanya mengukur
    # blok guardrail runtime, sedangkan POC fase berjalan SESUDAHNYA sehingga
    # residunya tak pernah terdeteksi (terukur 2026-07-29: +22 mutasi
    # reservation/release_reservation yatim menunjuk SO yang sudah dihapus,
    # muncul sebagai baris sampah di layar Gudang → Mutasi).
    KN_RESIDUE_FILE=/tmp/kn_gate_residue_poc.json python scripts/gate_residue.py --save || true

    run_gate "POC FASE G-0 (fondasi konfigurasi)" "python backend/test_g0_config_poc.py"
    run_gate "POC FASE G-1 (amandemen ber-alasan)" "python backend/test_g1_amendment_poc.py"
    run_gate "POC FASE G-4 (relasi dokumen · referensi cetak · tanda tangan)" "python backend/test_g4_refs_poc.py"
    run_gate "POC FASE G-2 (rencana pembayaran & denda)" "python backend/test_g2_payment_poc.py"
    run_gate "POC FASE G-3 (selisih pembayaran lebih/kurang bayar)" "python backend/test_g3_variance_poc.py"
    run_gate "POC FASE F-1 (penerimaan satuan supplier)" "python backend/test_fase_f1_receiving_uom_poc.py"
    # FASE F — R&D: spesifikasi → labdip/proofing ber-bukti → keputusan pemenang →
    # kontrak harga, plus gating lifecycle produk (barang belum sah tidak bisa dijual).
    run_gate "POC FASE F (R&D · labdip/proofing · lifecycle produk)" "python backend/test_fase_f_rnd_poc.py"
    # FASE F user story yang dulu belum terverifikasi (US3 gating jual · US11 mutasi
    # bahan sample terbaca gudang · US12 jejak dokumen kontrak → sample → spesifikasi).
    run_gate "POC FASE F US3/US11/US12 (gating jual · mutasi sample · jejak dokumen)" "python backend/test_fase_f_us3_us11_us12_poc.py"
    run_gate "POC FASE D (makloon rantai proses)" "python backend/test_fase_d_makloon_poc.py"
    # FASE G-8 — rekonsiliasi bank: parser multi-bank · skor berbobot 3 pita · split 1:N &
    # gabung N:1 · aturan hasil pembelajaran (ditawarkan, tidak dipaksakan) · titipan dana
    # belum teridentifikasi (kas + jurnal) · isolasi lintas-PT (celah nyata sebelum fase ini).
    run_gate "POC FASE G-8 (rekonsiliasi bank · titipan dana · isolasi PT)" "python backend/test_g8_bank_poc.py"
    # FASE G-9 — pusat kasus keuangan: 11 playbook (setiap aksi melahirkan dokumen nyata) ·
    # kasus dibuat SENDIRI dari titipan dana menganggur & pembayaran dobel · SLA + eskalasi ·
    # wajib alasan berlabel + bukti + persetujuan sesuai ambang · isolasi lintas-PT.
    run_gate "POC FASE G-9 (pusat kasus keuangan · 11 playbook · SLA · dokumen turunan)" "python backend/test_g9_case_poc.py"
    # FASE G-7 — kontrabon: satu siklus tukar faktur supplier = 1 tanda terima + 1
    # pembayaran untuk banyak faktur · 5 jenis potongan yang menunjuk dokumen nyata ·
    # 3-way match bertoleransi CONFIG dengan keputusan berlabel wajib · jadwal tukar
    # faktur + pengingat H-n · bayar dari baris mutasi bank (jembatan ke G-8).
    run_gate "POC FASE G-7 (kontrabon · potongan · toleransi config · bayar sekali)" "python backend/test_g7_contrabon_poc.py"
    # FASE G-6 — transaksi antar entitas (JUAL-BELI antar-PT, bukan pindah gudang):
    # harga internal dari kontrak · dokumen kembar 2 buku · saldo pasangan PT ·
    # settlement/netting · eliminasi unrealized profit OTOMATIS di konsolidasi ·
    # jembatan gudang (perpindahan fisik TANPA jurnal at-cost dobel + roll pembeli
    # dinilai ulang) · pembatalan ber-alasan yang MEMBALIK jurnal · bukti-merah
    # INV-IC-01..06. Dijalankan lewat pytest (11 user story + invarian).
    run_gate "POC FASE G-6 (antar entitas · dokumen kembar · netting · eliminasi margin)" \
      "cd backend && python -m pytest tests/test_g6_poc.py -q"
    # FASE G-6b — 4 lanjutan antar entitas: FAKTUR PAJAK INTERNAL berpasangan
    # (keluaran penjual == masukan pembeli, masuk rekap PPN tiap PT) · RETUR
    # antar-PT (dual-control, jurnal pembalik dua buku, roll dinilai ulang ke harga
    # perolehan asli) · PENGINGAT settlement (notifikasi nyata, umur dari aktivitas
    # nyata) · RAPOR MARGIN grup (realized vs unrealized dari sisa roll nyata).
    # Bukti-merah INV-IC-03 (rasio), INV-IC-07 (pajak), INV-IC-08 (retur).
    run_gate "POC FASE G-6b (faktur pajak internal · retur antar-PT · pengingat · margin)" \
      "cd backend && python -m pytest tests/test_g6b_poc.py -q"

    # Residu FASE POC — checkpoint KEDUA (BARU 2026-07-29). Sebelumnya anti-residu
    # hanya mengukur blok guardrail runtime, sedangkan POC fase berjalan SESUDAHNYA
    # sehingga residunya tak pernah terdeteksi. Terukur saat ditambahkan:
    # `inventory_rolls` 53→75 (+22 roll potongan) dan saldo `prod_batik_mega`
    # bergeser (reserved 50→173 · available 435→307) setiap satu kali gate --full.
    # Akar masalah: POC mengonfirmasi SO (memotong & mereservasi roll) lalu menghapus
    # SO langsung dari DB. Ditutup lewat `backend/poc_stock_guard.py`
    # (snapshot→restore EKSAK koleksi stok). Detail: BUG_REGISTRY POC-RESIDU-01.
    # Jejak append-only (audit_logs/notifications) DIABAIKAN dengan sengaja: POC
    # menjalankan alur nyata, dan menghapus jejak audit justru merusak bukti.
    run_gate "INV-GATE-01 anti-residu FASE POC (POC tak boleh menggeser stok/dokumen)" \
      "KN_RESIDUE_FILE=/tmp/kn_gate_residue_poc.json python scripts/gate_residue.py --check --ignore-trails"
    run_gate "seed_realistic (pulihkan data demo setelah FASE POC)" "python seed_realistic.py >/dev/null 2>&1"
    run_gate "verify_data_integrity (ulang, pasca pemulihan data)" "python scripts/verify_data_integrity.py >/dev/null 2>&1"
  else
    skip_gate "POC fase (--full)" "auth belum ada / backend down"
  fi
fi

fi  # end non-quick

# Tunggu kolam statik lalu cetak hasilnya (buffered supaya tidak berbaur).
if [ -n "$STATIK_PID" ]; then
  wait "$STATIK_PID" 2>/dev/null || true
  collect_statik
fi

T_TOTAL=$((SECONDS-T_START))

# ============ TULIS RECEIPT ============
{
  echo "# 🧾 GATE RECEIPT — Kain Nusantara"
  echo ""
  echo "> Bukti verifikasi otomatis. Dihasilkan \`scripts/gate.sh\`. JANGAN edit manual."
  echo ""
  echo "- **Waktu:** $TS"
  echo "- **Mode:** \`$MODE\`  ·  **Durasi total:** ${T_TOTAL}s  ·  **Pekerja statik:** ${JOBS}"
  if [ $AUTH_READY -eq 1 ]; then echo "- **Backend:** RUNNING + auth siap (gate runtime dijalankan)"; elif [ $BACKEND_UP -eq 1 ]; then echo "- **Backend:** RUNNING tanpa auth (gate runtime di-skip)"; else echo "- **Backend:** DOWN / tidak diperiksa (mode quick atau Phase 0)"; fi
  echo ""
  echo "| Gate | Hasil |"
  echo "|------|-------|"
  for i in "${!SNAMES[@]}"; do echo "| ${SNAMES[$i]} | ${SRESULTS[$i]} |"; done
  for i in "${!NAMES[@]}"; do echo "| ${NAMES[$i]} | ${RESULTS[$i]} |"; done
  echo ""
  if [ $OVERALL -eq 0 ]; then
    echo "## ✅ VERDICT: HIJAU — boleh lanjut / klaim selesai (cakupan non-skip)."
  else
    echo "## ❌ VERDICT: MERAH — ADA GATE GAGAL. Lihat memory/BUG_REGISTRY.md. Perbaiki lalu jalankan ulang."
  fi
  echo ""
  echo "**Tingkatan:** \`--quick\` (statik ~7s) · default (~25s) · \`--ci\` (default + receipt JSON) · \`--full\` (+POC fase ~95s)."
  echo ""
  echo "_Catatan: SKIP bukan PASS. Gate runtime harus dijalankan ulang saat backend hidup._"
} > "$RECEIPT"

if [ "$WRITE_JSON" -eq 1 ]; then
  {
    echo "{"
    echo "  \"timestamp\": \"$TS\","
    echo "  \"mode\": \"$MODE\","
    echo "  \"duration_seconds\": $T_TOTAL,"
    echo "  \"statik_workers\": $JOBS,"
    echo "  \"backend_ready\": $AUTH_READY,"
    echo "  \"verdict\": \"$([ $OVERALL -eq 0 ] && echo HIJAU || echo MERAH)\","
    echo "  \"gates\": ["
    first=1
    for i in "${!SNAMES[@]}"; do
      [ $first -eq 0 ] && echo ","; first=0
      printf '    {"name": "%s", "result": "%s"}' "${SNAMES[$i]//\"/\\\"}" "${SRESULTS[$i]}"
    done
    for i in "${!NAMES[@]}"; do
      [ $first -eq 0 ] && echo ","; first=0
      printf '    {"name": "%s", "result": "%s"}' "${NAMES[$i]//\"/\\\"}" "${RESULTS[$i]}"
    done
    echo ""
    echo "  ]"
    echo "}"
  } > "$RECEIPT_JSON"
  echo -e "  Receipt JSON: $RECEIPT_JSON"
fi

echo -e "\n${CYAN}${BOLD}==============================================================${RST}"
if [ $OVERALL -eq 0 ]; then echo -e "  ${GREEN}${BOLD}✓ SEMUA GATE (non-skip) HIJAU.${RST}  ${T_TOTAL}s · mode $MODE · Receipt: $RECEIPT"; else echo -e "  ${RED}${BOLD}✗ ADA GATE MERAH.${RST}  ${T_TOTAL}s · Lihat detail di atas & $RECEIPT"; fi
echo -e "${CYAN}${BOLD}==============================================================${RST}\n"
exit $OVERALL
