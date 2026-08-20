# 🧭 KOMPARASI FORENSIK: `travel` (Rahaza) vs Kain Nusantara — & Peningkatan yang Diterapkan

**Tanggal:** 2026-07-05 · **Sesi:** #076 (lanjutan) · **Mode:** analisis komparatif + peningkatan kualitas (tooling QA, TANPA mengubah kode aplikasi).

**Sumber pembanding:** `github.com/akugendutkayababi/travel` — "Rahaza Travel & Fleet Management Ecosystem" (FARM: FastAPI+React+MongoDB), yang menjalankan proses **verifikasi bug forensik** serupa dengan KN.

> Permintaan owner: *"analisis repo travel, lihat cara verifikasi bug / dokumen / script / mitigation plan-nya, lakukan deep reasoning sebagai komparasi, lalu terapkan bila meningkatkan kualitas project ini."*

---

## 1. Apa yang dilakukan `travel` (ringkas, berbasis bukti)

| Artefak travel | Isi |
|---|---|
| `FORENSIC_00_EXECUTIVE_SUMMARY.md` | Audit 5-dimensi + **reproduksi empiris live** (login→endpoint→cek DB→cleanup). Verdict: TERBUKTI/DORMANT/FALSE-POSITIVE. Menemukan 7 cacat state-machine + 1 race "green-but-broken". |
| `SSOT_MASTER_REPAIR_PLAN.md` + `SSOT_FORENSIC_RAW_TRAVEL.json` | Master repair plan per-RC (file:baris, akar masalah, fix, rollback, risiko) + dump forensik mesin-terbaca. |
| `docs/DEEP_ANALYSIS_PLAYBOOK.md` | Playbook "analisis mendalam" 6-tahap (B-T-K-S-R-A) + rubrik Definition-of-Done + anti-pattern. |
| `memory/INVARIANTS.md` | **SSOT invariant** (INV-NUM-01, INV-RACE-01, INV-RBAC-01/02/03, INV-5XX-01) → tiap invarian punya penjaga + allowlist. |
| `memory/BUG_REGISTRY.md` | Registry bug: gejala→root-cause→**gate penangkap**→regression→status. |
| `scripts/gate.sh` → `memory/GATE_RECEIPT.md` | **Orkestrator gate tunggal**: jalankan semua gate (statik+runtime), tulis receipt. "Selesai" sah hanya bila receipt HIJAU. |
| `scripts/guardrails/*` | Penjaga **STATIK** preventif: `verify_rbac_guards.py`, `verify_numeric_bounds.py`, `verify_reservation_locks.py`, `verify_adversarial_5xx.py`. |
| `scripts/verify_cross_entity.py`, `verify_state_machine.py`, `verify_concurrency.py` | Gate **RUNTIME** anti-regresi (IDOR/RC, state-machine, race). |

**Filosofi inti travel** (dari `INVARIANTS.md`): *"bug berulang bukan karena fondasi rapuh, tapi karena pola pengaman yang benar tidak diterapkan konsisten di permukaan yang terus bertambah, dan tes lama hanya menguji happy-path."* → Guardrail v2 mengubah aturan dari **"diingat developer" → "dipaksa analisis kode"**.

---

## 2. Deep reasoning — komparasi kapabilitas

| Kapabilitas | travel | Kain Nusantara (sebelum) | Verdict |
|---|---|---|---|
| Invarian **integritas DATA/GL** | 32 | **122** (`verify_data_integrity.py`) | **KN JAUH LEBIH KUAT** |
| Kedalaman forensik GL/akuntansi | sedang | sangat dalam (fa_s075 31/31, landed-cost, dsb) | **KN LEBIH KUAT** |
| Dossier forensik per-bug (#074/#075/#076) | ada | ada, rinci | PARITAS |
| **Orkestrator gate tunggal + receipt** | ✅ `gate.sh`→`GATE_RECEIPT.md` | ❌ hanya skrip terpisah + `forensic/fa_*` ad-hoc | **GAP KN** |
| **Guardrail STATIK (analisis kode, bebas-sesi)** | ✅ `guardrails/` | ❌ tidak ada | **GAP KN** |
| **Gate coverage AUTH/RBAC** | ✅ `verify_rbac_guards.py` | ❌ — justru celah ini yang meloloskan AUTH-* #076 | **GAP KN (kritis)** |
| **Gate isolasi lintas-entitas (IDOR)** | ✅ `verify_cross_entity.py` (gated) | hanya `forensic/fa_idor_*` (tak gated, cakupan parsial) | **GAP KN** |
| **SSOT INVARIANTS.md** | ✅ | ❌ (invarian tersebar di verify_data_integrity) | **GAP KN** |
| **BUG_REGISTRY (bug→gate)** | ✅ | `BUG_BACKLOG.md` (UI saja) | **GAP KN** |

### Insight kunci (deep reasoning)
Kedua proyek **secara independen menemukan pelajaran yang SAMA**: pola **"green-but-broken" / META-GATE blindness**. Bedanya, **travel sudah MELEMBAGAKAN** solusinya (guardrail statik + orkestrator + SSOT invariant), sedangkan **KN belum** — dan itulah **akar** kenapa temuan keamanan #076 (6+ endpoint tanpa auth, IDOR baca/tulis) **tak pernah** tertangkap gate KN mana pun: gate KN hanya memeriksa **DATA/GL**, tak pernah **auth/entity-scope** di permukaan endpoint yang tumbuh (508 endpoint).

> Kesimpulan: KN unggul di **kedalaman data/akuntansi**; travel unggul di **disiplin pencegahan lintas-kelas-bug**. Porting lapisan pencegahan travel ke KN = peningkatan kualitas nyata & langsung relevan dengan temuan #076.

---

## 3. Yang DITERAPKAN ke Kain Nusantara (tooling QA — tanpa ubah kode aplikasi)

| Artefak baru di KN | Diadaptasi dari | Fungsi | Bukti bekerja |
|---|---|---|---|
| `scripts/guardrails/_common.py` | travel `guardrails/_common.py` | util `Guard` (APA+DI MANA+INVARIANT-ID) | — |
| `scripts/guardrails/verify_auth_coverage.py` (**STATIK**) | travel `verify_rbac_guards.py` | Tiap endpoint router wajib menegakkan auth; resolusi helper transitif (`_emp_for_user`), deteksi "401 ditelan try/except", `PUBLIC_ALLOWLIST` | **MERAH — 8 pelanggaran** (semua real #076 + 2 endpoint POS BARU) |
| `scripts/guardrails/verify_cross_entity.py` (**RUNTIME**) | travel `verify_cross_entity.py` | Peran ter-scope entitas A dilarang BACA/TULIS dokumen entitas B (uji perilaku) | **MERAH — 4 LEAK** (3 baca + 1 tulis inbound escalate) |
| `scripts/gate.sh` → `memory/GATE_RECEIPT.md` | travel `gate.sh` | Orkestrator tunggal: statik selalu, runtime bila backend hidup, tulis receipt | receipt dihasilkan tiap run |
| `memory/INVARIANTS.md` | travel `INVARIANTS.md` | SSOT invariant KN (INV-AUTH-01, INV-ENTITY-01, INV-GL-01, INV-DATA, INV-5XX-01, INV-NAV-01, INV-COMPLY-01) | — |
| `memory/BUG_REGISTRY.md` | travel `BUG_REGISTRY.md` | Registry bug→invariant→gate; di-seed dgn 6 temuan #076 + 3 false-positive | — |

### Kenapa AUTH = STATIK tapi ENTITY = RUNTIME (keputusan ber-trade-off)
- **AUTH (statik):** enforcement auth di KN konsisten di **lapisan router** (`await require_permission(...)`), jadi analisis statik per-endpoint **presisi tinggi** (508 dicek, 8 pelanggaran, ~0 false-positive setelah resolusi helper transitif).
- **ENTITY (runtime):** enforcement scope entitas KN sering di **lapisan SERVICE** (mis. `so_transition`, `assert_entity_access` di service) — analisis statik router-only menghasilkan **53 kandidat dengan banyak false-positive** (mis. `sales-orders/{id}/confirm` yang sebenarnya AMAN via service). Karena itu dipilih **gate RUNTIME** (uji perilaku login→akses→tolak) yang **andal & bebas false-positive** — selaras dgn pendekatan travel yang juga runtime untuk cross-entity.

---

## 4. Hasil `bash scripts/gate.sh` (receipt jujur)
Guardrail baru **sengaja MERAH** karena temuan #076 **belum diperbaiki** (owner minta report-only). Ini justru **bukti gate bekerja** (bukan hijau-palsu): bug senyap kini menjadi **kegagalan gate yang keras & bebas-sesi**. Lihat `memory/GATE_RECEIPT.md`.

| Lapis | Gate | Hasil | Makna |
|---|---|---|---|
| STATIK | guard:auth_coverage (INV-AUTH-01) | **FAIL** | 8 endpoint tanpa auth (bug #076 terbuka) |
| STATIK | validate_compliance / check_nav_map | (lihat receipt) | kepatuhan repo |
| DATA | verify_data_integrity | **PASS 122/0/WARN1** | integritas GL/domain sehat |
| RUNTIME | guard:cross_entity (INV-ENTITY-01) | **FAIL** | 4 kebocoran lintas-entitas (bug #076 terbuka) |
| RUNTIME | audit_endpoint_sweep / health_check | (lihat receipt) | 5xx & isi endpoint |

---

## 5. Rekomendasi lanjutan (NOW vs LATER)
**SEKARANG (dampak tinggi, biaya rendah):**
1. Perbaiki bug INV-AUTH-01 & INV-ENTITY-01 (#076) → gate langsung berubah HIJAU (regresi terkunci selamanya).
2. Jalankan `bash scripts/gate.sh` di tiap akhir sesi sebelum klaim "selesai".

**DITUNDA (perlu keputusan/estimasi):**
3. Tambah **INV-AR-01** (rekonsiliasi AR) ke `verify_data_integrity.py` → tutup blind-spot AR-GL-DRIFT.
4. Naikkan **COGS-ZERO** dari WARN→FAIL setelah cost mengalir ke fulfillment.
5. Port opsional dari travel: `verify_numeric_bounds.py` (bound `ge=`/`gt=` di schemas), `verify_state_machine.py`, guard 5xx adversarial ter-gated, `DEEP_ANALYSIS_PLAYBOOK.md`.

---

## 6. Traceability (permintaan owner → aksi)
| Permintaan | Aksi | Artefak |
|---|---|---|
| "lihat cara verifikasi bug / dokumen travel" | baca FORENSIC_00, SSOT_MASTER_REPAIR_PLAN, DEEP_ANALYSIS_PLAYBOOK | §1 |
| "lihat script yang dibuat" | baca `scripts/gate.sh`, `guardrails/*`, `verify_cross_entity.py` | §1 |
| "lihat mitigation plan" | baca SSOT_MASTER_REPAIR_PLAN + BUG_REGISTRY travel | §1 |
| "deep reasoning komparasi" | tabel kapabilitas + insight green-but-broken | §2 |
| "lakukan bila meningkatkan kualitas" | port Guardrail v2 (auth statik + cross-entity runtime + gate.sh + INVARIANTS + BUG_REGISTRY) | §3–§4 |
