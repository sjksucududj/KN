# KN_00 — AGENT QUICK START
## Kain Nusantara Platform — Mandatory Entry Point

**WAJIB DIBACA PERTAMA SEBELUM MELAKUKAN APAPUN**
**Versi:** 1.0 | **Berlaku sejak:** 2026-05-23

---

## 🔴 STOP — BACA INI DULU

Jika Anda agent baru yang baru memulai sesi, JANGAN langsung coding.
Urutan wajib:

```
1. KN_00_AGENT_QUICK_START.md     ← File ini (baca sekarang)
2. KN_01_SYSTEM_OVERVIEW.md       ← Pahami bisnis & domain
3. /app/memory/PRD.md             ← Apa yang sudah ada
4. /app/plan.md                   ← Task yang sedang dikerjakan
5. /app/docs/KN_13_NAVIGATION_MAP.md ← Sebelum buat fitur apapun
```

### ⏩ PEKERJAAN YANG SEDANG BERJALAN (per 2026-08-18): **MD ERP**

```
6. /app/RENCANA_EKSEKUSI_MD_ERP.md          ← RENCANA AKTIF (v2, sudah diverifikasi
                                              ke kode & DB). §0 = konteks 2 menit,
                                              §3 = kontrak pagar entitas (12 titik),
                                              §4 = kontrak "UI/UX tidak berubah".
7. python scripts/audit_md_erp_readiness.py ← UKUR keadaan (95 fakta · SELESAI/BELUM/
                                              DRIFT). JANGAN percaya prosa — jalankan ini.
8. /app/plan.md §STATUS MD-ERP              ← ringkasan sesi terakhir + 7 klaim lama yang
                                              terbukti salah + 6 DRIFT yang menunggu
```
Urutan fase yang disepakati: **L (lini) → T (tahapan/Screen) → U (dua satuan) →
D + P-0 → S (sampling) → I (inspeksi/QC) → P (papan PO) → N (notifikasi) → M (makloon)**.
Lima keputusan pemilik yang masih ditunggu ada di §12 rencana (hanya memblokir S & I).

Total waktu baca: ~20 menit. Ini menghemat jam kerja yang sia-sia.

---

## ⚙️ EXECUTABLE GUARDRAILS (WAJIB — bukan sekadar dokumen)

> Pelajaran kunci (case-study intent-drift): **dokumentasi prosa membusuk**.
> Guardrail yang benar = **kode yang bisa GAGAL** dan dijalankan otomatis.
> Baca `/app/memory/ENGINEERING_GUARDRAILS.md` (taksonomi RC-1..RC-15) +
> `/app/docs/UX_USABILITY_STANDARD.md`.

Sebelum menyatakan task "selesai", jalankan GATE ini dari `/app`:

```bash
bash scripts/seed_reset.sh             # seed BERSIH + [GATE] contract + data-integrity
python scripts/health_check.py         # sweep endpoint kritis (cek ISI, bukan 200)
python scripts/audit_endpoint_sweep.py # sweep SEMUA GET /api (cari 5xx)
python scripts/ux_audit.py             # baseline UX (loading/empty/chart/uang)
python scripts/verify_contract.py --all   # nama koleksi (cegah RC-1 drift)
```

Aturan: semua hijau → boleh `finish`. Ada FAIL → perbaiki dulu, atau catat
eksplisit sebagai keputusan owner. **DILARANG** mengklaim hijau secara palsu (RC-10).

---

Total waktu baca: ~20 menit. Ini menghemat jam kerja yang sia-sia.

---

## 📋 3-GATE DEVELOPMENT SYSTEM

### GATE 1 — PRE-CODE (Sebelum tulis satu baris pun)

```
□ Sudah baca PRD.md dan tahu konteks lengkap?
□ Sudah baca plan.md dan tahu task yang sedang dikerjakan?
□ Sudah cek apakah fitur ini SUDAH ADA di codebase?
   → grep -r "keyword" /app/backend/routers/
   → find /app/frontend/src -iname "*Keyword*"
□ Sudah cek apakah collection MongoDB sudah ada?
   → grep -roh "db\.[a-z_]*" /app/backend/routers/ | sort -u | grep keyword
□ Sudah tentukan posisi fitur di Navigation Map? (KN_13)
□ Sudah jawab Entity Completeness Checklist? (KN_12)
□ Perlu konfirmasi user? (cek STOP & ASK triggers di bawah)
```

### GATE 2 — DURING CODE

```
□ Mengikuti Tech Stack patterns? (KN_02)
□ Mengikuti Security standards? (KN_03)
□ Mengikuti Database standards? (KN_04)
□ Mengikuti API standards? (KN_07)
□ File tidak melebihi batas ukuran?
   → React component: max 500 baris
   → Python router: max 800 baris
□ Semua field contextual ada? (warehouse_id, created_by, dll)
□ Downstream impact sudah di-handle?
```

### GATE 3 — POST-CODE (Sebelum mark DONE)

```
□ Sudah jalankan: python /app/scripts/validate_compliance.py?
□ Sudah jalankan testing agent?
□ Semua bug dari testing sudah difix?
□ Linter bersih? (ruff /app/backend + eslint /app/frontend/src)
□ Screenshot/curl verified?
□ PRD.md sudah diupdate?
□ plan.md sudah diupdate?
□ SESSION_LOG.md sudah diisi?
□ Navigation Map diupdate jika ada halaman baru?
```

---

## 🛑 STOP & ASK TRIGGERS

HENTI dan tanya user SEBELUM lanjut jika:

```
🔴 CRITICAL (SELALU tanya):
  - Drop atau migrate MongoDB collection
  - Hapus atau rename API endpoint (breaking change)
  - Ubah authentication/authorization flow
  - Tambah dependency baru (pip/yarn)
  - Restructure folder/module besar
  - Tambah menu/navigasi baru di luar Navigation Map

🟡 CONFIRMATION (tanya jika tidak yakin):
  - Refactor file >500 baris
  - Ubah shared utility/helper
  - Tambah portal/section baru
  - Ubah schema MongoDB yang sudah ada data

🟢 AUTO-EXECUTE (tidak perlu tanya):
  - Fix bug dengan regression test
  - Tambah data-testid
  - Tambah loading/error/empty state
  - Performance optimization
  - Styling improvement
  - Tambah unit test
```

---

## ⚠️ TOP 10 PITFALLS — JANGAN ULANGI KESALAHAN DA30

```
1. Build feature paralel tanpa cek existing code
   → Selalu: Code Discovery SEBELUM Code Creation

2. Buat collection baru untuk entity yang sudah ada
   → Selalu: grep existing collections dulu

3. Feature cacat karena field contextual tidak lengkap
   → Selalu: Entity Completeness Checklist (KN_12)

4. Tambah menu tanpa Navigation Map planning
   → Selalu: Navigation First Policy (KN_13)

5. Monster files >500 baris React / >800 baris Python
   → Selalu: Split sejak awal, bukan refactor nanti

6. Skip testing lalu claim "sudah done"
   → Selalu: testing_agent_v3 WAJIB dipanggil

7. Tidak update PRD.md setelah selesai
   → Selalu: Update dokumentasi = bagian dari task

8. Hardcode warehouse_id, user_id, atau config lain
   → Selalu: Dari token auth atau environment variable

9. Plain visualization tanpa drill-down dan action
   → Selalu: ECharts dengan Level 3+ interactivity

10. Skip downstream impact (GR tanpa update inventory, dll)
    → Selalu: Pikirkan "apa yang berubah setelah ini?"
```

---

## 📁 DOKUMEN REFERENSI

```
/app/docs/
├── KN_00_AGENT_QUICK_START.md     ← File ini
├── KN_01_SYSTEM_OVERVIEW.md       ← Bisnis & domain
├── KN_08_UI_UX_STANDARDS.md       ← Design system
│   (KN_02–KN_07, KN_09–KN_11 = standar ASPIRATIF → SUDAH DIHAPUS.
│    Kontrak NYATA = memory/ENGINEERING_GUARDRAILS.md + FRONTEND_GUARDRAILS.md)
├── KN_12_DEVELOPMENT_PROTOCOLS.md ← Dev protocols
└── KN_13_NAVIGATION_MAP.md        ← Master nav map

/app/memory/
├── PRD.md                         ← Feature history + backlog
├── SESSION_LOG.md                 ← Per-session log
└── TECH_DECISIONS.md              ← Architectural decisions

/app/scripts/
├── validate_compliance.py         ← Automated checker
└── check_nav_map.py               ← Navigation validator
```

---

## 🌐 LANGUAGE RULE

```
Komunikasi dengan user → BAHASA INDONESIA (selalu)
Kode & variabel → English (snake_case Python, camelCase JS)
UI labels → Bahasa Indonesia
Komentar kode → Bahasa Indonesia diperbolehkan
Error messages ke user → Bahasa Indonesia
Log internal → English
```

---

## ✅ DEFINITION OF DONE

Sebuah task BARU BOLEH dianggap selesai jika:

```
□ Gate 1, 2, 3 semua passed
□ testing_agent_v3 dipanggil dan semua bug difix
□ Linter clean (0 error, 0 warning)
□ Screenshot verified (UI terlihat benar)
□ API curl verified (response format benar)
□ PRD.md diupdate
□ SESSION_LOG.md diisi
□ Tidak ada TODO/FIXME tersisa di code yang baru
□ Tidak ada console.log/print debug tersisa
```
