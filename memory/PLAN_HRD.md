# PLAN — MODUL HRD & PAYROLL (Human Resources)
## Kain Nusantara Group — Blueprint + Roadmap Pengembangan (Deep Dive)

> **Status dokumen:** DRAFT v1 — menunggu konfirmasi & prioritas owner. **PLANNING ONLY — BELUM ADA CODING.**
> **Disusun:** Session #062 (E2/Emergent), atas arahan owner ("fokus HRD dulu, buat plan detail + roadmap").
> **Selaras dgn:** `plan.md` (master), `KN_DEVELOPMENT_PLAN_FROM_ASSESSMENT.md` (Fase 2 HRD), `KN_17` (sales force/komisi), `ENTITY_REGISTRY.md` (data), `KN_13_NAVIGATION_MAP.md` (nav), `ENGINEERING_GUARDRAILS.md` + `FRONTEND_GUARDRAILS.md`.
> **Aturan emas:** dokumen ≠ kode → **kode menang**, lalu dokumen diperbaiki. Tiap koleksi/endpoint/menu baru WAJIB lewat ENTITY_REGISTRY + KN_13 + gates hijau.

---

## 0. Daftar Isi
| § | Isi |
|---|---|
| 1 | Kebutuhan owner (5 poin tambahan) + scope |
| 2 | Analisis sistem HR relevan (best-practice 2026 + payroll Indonesia) |
| 3 | Gap analysis (kondisi sekarang) |
| 4 | Arsitektur lintas-modul (integrasi insentif↔payroll↔finance, users↔employees, RBAC, entity) |
| 5 | Model data (koleksi baru + prefix — niat registrasi) |
| 6 | Roadmap 7 fase (H0–H6) + POC |
| 7 | Business rules (BPJS, PPh21, clock-in/out, geofence, tracking) |
| 8 | Navigasi/menu (KN_13) |
| 9 | Acceptance criteria + gates |
| 10 | Keputusan & pertanyaan terbuka (HR-Q) |

---

## 1. Kebutuhan Owner + Scope

**Scope modul HRD (versi assessment Fase 2 + arahan owner):**
Employee master, Organisasi, **Absensi 2-metode**, **Tracking sales lapangan**, Cuti/Lembur, **Payroll & Payslip lengkap**, KPI, (opsional) Design Gallery + AI Gemini, ESS (self-service), HR Analytics.

**5 KEBUTUHAN TAMBAHAN OWNER (wajib masuk plan):**
1. **Dua metode absen:** (a) **Fingerprint** (impor log mesin) + (b) **Geo-tagging** (absen mobile berbasis GPS).
2. **Geo-tagging cek posisi langsung (live) untuk sales** + sales butuh fitur lebih: **tracking** (rute/kunjungan).
3. **Clock-in & Clock-out** dengan **waktu yang jelas/presisi** (timestamp + sumber + lokasi).
4. **Payroll/Payslip lengkap** + **integrasi lintas modul**: komisi/insentif Sales **WAJIB masuk payroll**; payroll **terintegrasi Finance** (GL/jurnal).
5. **Analisis sistem HR relevan** (industri best-practice) — disertakan di §2.

---

## 2. Analisis Sistem HR Relevan (Best-Practice 2026 + Payroll Indonesia)

> Ringkasan riset (HRIS modern + regulasi Indonesia). Dipakai sebagai acuan desain, bukan menyalin produk tertentu.

### 2.1 Pilar arsitektur HRIS modern
- **Unified Employee Master Data (SSOT):** satu `employee_id` immutable jadi sumber tunggal; modul lain (payroll, absensi, sales) merujuk ID ini. "Thin slice" (nama, jabatan, dept, status) vs "Employment record" (gaji, kontrak, NPWP, rekening) dengan RBAC ketat.
- **Hybrid attendance:** validasi kehadiran via banyak vektor (biometrik on-site + GPS/geofence mobile) → cegah *buddy punching*; tangkap GPS **hanya saat clock-in/out** (bukan surveillance terus-menerus).
- **Field sales tracking:** check-in kunjungan (timestamp + GPS + foto bukti) tertaut customer/peluang; analitik rute & frekuensi kunjungan; **offline mode** (simpan lokal → sync saat online).
- **Payroll engine config-driven:** komponen earning/deduction modular; statutory otomatis; payslip digital; integrasi disbursement bank.
- **Keamanan/Privasi:** PII & GPS terenkripsi; RBAC (hanya HR/Finance lihat gaji/PPh21); audit immutable untuk tiap perubahan payroll/absensi/override; tracking sales hanya pada jam kerja + transparansi/consent.

### 2.2 Payroll Indonesia — komponen wajib (acuan 2026)
- **BPJS Kesehatan:** total 5% upah → **4% perusahaan + 1% karyawan** (batas upah/ceiling berlaku).
- **BPJS Ketenagakerjaan:**
  - **JHT** (Jaminan Hari Tua): 3,7% perusahaan + **2% karyawan**.
  - **JP** (Jaminan Pensiun): 2% perusahaan + **1% karyawan** (ceiling upah JP).
  - **JKK** (Kecelakaan Kerja): 0,24%–1,74% perusahaan (per kelas risiko).
  - **JKM** (Kematian): 0,30% perusahaan.
- **PPh 21:** metode **TER (Tarif Efektif Rata-rata) bulanan** + perhitungan **progresif tahunan** (5/15/25/30/35%); **PTKP** per status (TK/K0/K1/K2/K3); pengurang: biaya jabatan, iuran BPJS karyawan. Output: bukti potong (1721-A1) + rekap SPT.
- **Komponen gaji:** gaji pokok, tunjangan tetap (jabatan/transport/makan), tunjangan tidak tetap, **lembur** (rumus Kepmenaker), **komisi/insentif** (dari modul Sales), THR, potongan (pinjaman, kasbon, BPJS karyawan, PPh21).
- **Payslip:** gross, rincian earning, rincian potongan (BPJS/PPh21), kontribusi perusahaan, **take-home pay**, ref transfer bank.

### 2.3 Implikasi desain untuk KN
- Master HR = koleksi baru `hr_employees` (BUKAN `users`; `users` = akun login). Link `user_id` untuk karyawan yang punya akun (sales/admin/manager/warehouse); karyawan non-sistem (driver/guard) tetap tercatat tanpa akun.
- Semua koleksi HR **scoped `entity_id`** (PT/CV) — payroll & jurnal per entitas (selaras F-0 + per-entity GL).
- Komisi sudah dihitung engine EPIC4 (`compute_commission`) & ter-akrual GL (`2-1500`). Payroll **menarik** angka itu (anti double-count, lihat §4.3).
- Statutory (BPJS/PPh21/PTKP/TER) = **config-driven** di `system_settings.hr` agar mudah update saat regulasi berubah.

---

## 3. Gap Analysis (Kondisi Sekarang)
> Legend: ✅ ada · 🟡 parsial · ❌ belum.

| Kebutuhan | Status | Catatan |
|---|---|---|
| Employee master | ❌ | Hanya `users` (akun login + role). Belum ada master karyawan HR. |
| Org structure (dept/jabatan/divisi) | ❌ | Belum ada. |
| Absensi (fingerprint) | ❌ | Belum ada modul HRD. |
| Absensi (geo-tagging mobile) | ❌ | Belum ada; mobile shell sales ada (viewport ≤768) → bisa reuse pola. |
| Clock-in/out | ❌ | Belum ada. |
| Tracking sales (GPS/kunjungan) | ❌ | KN_17 menyebut KPI kunjungan (derived) tapi belum ada capture GPS/visit. |
| Cuti & lembur | ❌ | Belum ada. |
| Payroll & payslip | ❌ | Belum ada. |
| **Komisi/insentif sales** | ✅ engine | `sales_force_service.compute_commission` (per-SKU, margin-aware, on-collection) + akrual GL. **Siap dijadikan input payroll.** |
| Finance/GL | ✅ | `gl_service` + `journal_entries` per entitas (siap untuk jurnal payroll). |
| Notifikasi | ✅ | `notifications` (untuk reminder absen/payslip/approval). |
| Storage bukti/foto | ✅ | Object storage dipakai (bukti approval) — reuse utk foto absen/visit. |
| KPI Design + Design Gallery + AI Gemini | ❌ | Belum ada (butuh Emergent LLM key utk Gemini). |
| RBAC | ✅/🟡 | `permission_settings` ada; perlu tambah role/permission HR + ESS (employee lihat data sendiri). |

**Kesiapan HRD: ~5%** (hanya enabler: users, GL, notifications, storage). Inti HR (employee/absensi/payroll) = greenfield.

---

## 4. Arsitektur Lintas-Modul (Integrasi)

### 4.1 users ↔ hr_employees
- `hr_employees.user_id` (nullable FK `users`). Karyawan dgn akun → ter-link (sales/admin/manager/warehouse). Tanpa akun → `user_id=null`.
- Untuk sales: `users(role=sales).id == hr_employees.user_id` → menyatukan **komisi (by sales_id)** dengan **payroll (by employee)**.
- Saat seed/migrasi: backfill `hr_employees` dari `users` existing (4 demo) + entity_id.

### 4.2 Entity scoping + RBAC
- Semua koleksi HR `entity_id`-scoped (selaras F-0). Payroll run & jurnal per entitas (KSC/Kanda).
- Role baru: **hr_admin** (kelola karyawan/payroll), **hr_manager** (approve cuti/lembur, lihat tim). **Self-service:** tiap karyawan (via user_id) lihat absensi/slip/saldo cuti SENDIRI (RBAC row-level, enforce backend — pola sama KN_17 §4).
- Data gaji/PPh21 hanya untuk hr_admin/hr_manager/finance/owner (PII-sensitive).

### 4.3 ⭐ Integrasi Komisi Sales → Payroll (anti double-count) — KEPUTUSAN KUNCI
Kondisi saat ini: insentif diakrualkan ke GL via `/api/crm/sales/incentive/post-gl`:
`Dr 6-5000 Beban Insentif / Cr 2-1500 Hutang Insentif Penjualan` (per entitas, per periode, idempotent).

**Rancangan terpilih (rekomendasi) — payroll MENYELESAIKAN liabilitas, tidak re-expense:**
1. Insentif tetap dihitung `compute_commission(sales_id, period)` & **diakrualkan** (beban diakui saat closing periode) → saldo `2-1500 Hutang Insentif`.
2. Saat **payroll run** periode itu: untuk karyawan sales, sistem **menarik** `computed_amount` insentif periode → masuk payslip sebagai **earning "Komisi/Insentif"** (read dari engine, BUKAN hitung ulang beban).
3. Jurnal payroll **memindahkan** liabilitas insentif ke hutang gaji (bukan menambah beban baru):
   `Dr 2-1500 Hutang Insentif / Cr 2-1600 Hutang Gaji` (porsi komisi).
   Sisanya (gaji pokok+tunjangan+lembur) → `Dr 6-6000 Beban Gaji / Cr 2-1600 Hutang Gaji`.
4. Disbursement: `Dr 2-1600 Hutang Gaji / Cr 1-xxxx Kas-Bank`.
> Alternatif (HR-Q2): jika owner ingin insentif **tidak** diakrualkan terpisah dan langsung jadi beban gaji, maka crm post-gl dimatikan utk periode payroll & komisi di-expense sebagai Beban Gaji. **Default rekomendasi = skema akrual→settle di atas** (audit jelas, hindari double-count).

### 4.4 ⭐ Integrasi Payroll → Finance (GL/Jurnal)
Akun GL baru (PROPOSAL — register di gl_service + ENTITY_REGISTRY):
| Akun | Nama | Tipe |
|---|---|---|
| 6-6000 | Beban Gaji & Upah | expense |
| 6-6100 | Beban BPJS (Perusahaan) | expense |
| 6-6200 | Beban Tunjangan/Lembur | expense (opsional, bisa subsumsi 6-6000) |
| 2-1600 | Hutang Gaji | liability |
| 2-1700 | Hutang BPJS | liability |
| 2-1800 | Hutang PPh21 | liability |
- Posting payroll run (idempotent per entity+period, pola sama incentive post-gl):
  `Dr 6-6000 Beban Gaji + Dr 6-6100 Beban BPJS(perusahaan) ; Cr 2-1600 Hutang Gaji + Cr 2-1700 Hutang BPJS + Cr 2-1800 Hutang PPh21`
  (+ baris pemindahan komisi dari 2-1500 sesuai §4.3).
- Pembayaran gaji & setoran BPJS/PPh21 → mutasi kas/bank (`bank`/`cash` modul EPIC 7-B) + clearing hutang.

### 4.5 Reuse komponen existing
- **Approval** cuti/lembur → reuse pola `approval_requests`/`so_approvals` (workflow + audit).
- **Notifications** → reminder absen, approval cuti, payslip terbit, jatuh tempo setor BPJS/PPh21.
- **Object storage** → foto selfie absen geo, foto bukti kunjungan, lampiran cuti (surat dokter).
- **reportlab** (sudah terpakai) → payslip PDF & bukti potong.
- **Mobile shell** (sales viewport ≤768) → reuse untuk Absen Mobile + Visit check-in.

---

## 5. Model Data (Koleksi Baru — Niat Registrasi ENTITY_REGISTRY)

> ⚠️ Semua nama di bawah HARUS didaftarkan di `ENTITY_REGISTRY.md` sebelum coding, dengan daftar "JANGAN BUAT" alias. Semua `entity_id`-scoped kecuali disebut SHARED.

| Koleksi | Prefix | Fase | Inti |
|---|---|---|---|
| `hr_employees` | `emp_` | H0 | Master karyawan: user_id?, nik, name, dob, gender, position_id, department_id, employment_type(tetap\|kontrak\|harian\|borongan), join_date, status, npwp, ptkp_status(TK,K0..K3), bpjs_kes_no, bpjs_tk_no, bank{bank_id,acc_no,acc_name}, base_salary, allowances[], jkk_risk_class, photo_url, entity_id |
| `hr_org_units` | `orgu_` | H0 | Struktur: department & position (parent_id) — atau pisah `hr_departments`/`hr_positions` (HR-Q1) |
| `hr_shifts` | `shift_` | H1 | Definisi shift: jam_in, jam_out, grace_late_min, break, hari kerja |
| `hr_schedules` | `sched_` | H1 | Penjadwalan shift per karyawan/periode (opsional bila shift tunggal) |
| `hr_geofences` | `geo_` | H1 | Lokasi sah absen: nama, lat, lon, radius_m, entity (kantor/gudang) |
| `hr_attendance` | `att_` | H1 | Per karyawan per hari: clock_in{ts,method,geo,device,photo}, clock_out{...}, late_min, early_leave_min, overtime_min, work_min, status(hadir\|telat\|alpha\|izin\|cuti\|libur), method(fingerprint\|geo\|manual), flags(outside_geofence) |
| `hr_devices` | `dev_` | H1 | Mesin fingerprint: code, location, last_sync (mapping device_user_id→emp) |
| `hr_field_tracks` | `trk_` | H2 | Breadcrumb GPS sales saat jam kerja: emp_id, ts, lat, lon, accuracy, battery (interval/saat event) |
| `hr_visits` | `visit_` | H2 | Kunjungan sales: emp_id, customer_id, check_in{ts,geo,photo}, check_out, notes, linked_so_id, outcome |
| `hr_leave_requests` | `leave_` | H3 | Cuti/izin/sakit: type, from, to, days, reason, attachment, status, approver, balance impact |
| `hr_leave_balances` | `lbal_` | H3 | Saldo cuti per karyawan per tahun (atau derived) |
| `hr_overtime` | `ot_` | H3 | Lembur: emp_id, date, hours, rate_basis, status(approval) → feed payroll |
| `hr_payroll_runs` | `prun_` | H4 | Batch payroll per entity+period: status(draft\|approved\|posted\|paid), totals, gl_posted |
| `hr_payslips` | `slip_` | H4 | Per karyawan per periode: earnings[], deductions[], employer_contrib[], gross, net, **commission_amount (dari Sales)**, pph21, bpjs detail, bank ref, pdf_url |
| `hr_kpi` | `hkpi_` | H5 | KPI non-sales (mis. design: jumlah/kualitas desain, produktivitas). (KPI sales = derived KN_17) |
| `design_gallery` | `dsgn_` | H5 | Motif kain: title, story, files[], tags[], ai_meta (Gemini auto-tag) |
| `system_settings.hr` (SHARED settings) | — | H0+ | Config: bpjs rates, ptkp table, ter table, jkk classes, shift defaults, geofence default radius, overtime rules, payroll_commission_mode |

> JANGAN BUAT (alias terlarang yg akan kita catat): `employee/employees/karyawan/staff` (sbg alias users — pakai `hr_employees`), `attendance/absensi` polos, `payroll/gaji` polos, `kpi` polos (bentrok KPI sales derived). Gunakan prefiks `hr_`.

---

## 6. Roadmap Pengembangan (7 Fase) + POC

> Tiap fase: V1 fungsional → testing_agent_v3 → gates hijau → demo. Incremental.

### FASE H-POC — Validasi Core (WAJIB sebelum H4)
**Tujuan:** buktikan 3 titik paling berisiko dalam 1 skrip POC (`scripts/poc_hrd.py`):
1. **Geo clock-in/out + geofence**: simulasi koordinat di dalam/luar radius → status auto-approve/flag benar; clock_in/out timestamp presisi & durasi kerja terhitung.
2. **Komisi → Payroll (anti double-count)**: ambil `compute_commission(sales_id, period)`, masukkan ke payslip, hasilkan jurnal §4.3 yang SEIMBANG & tidak menambah beban ganda (cek saldo 2-1500 → 2-1600).
3. **Hitung BPJS + PPh21 (TER)**: untuk 2–3 contoh gaji + PTKP → angka sesuai tabel config; payslip net benar; jurnal payroll §4.4 SEIMBANG.
**Exit:** POC 100% PASS (mirip `poc_sales_revamp.py`). Bila gagal → perbaiki sebelum lanjut.

### FASE H0 — Foundation: Employee Master + Org + RBAC HR + ESS skeleton
- Koleksi: `hr_employees`, `hr_org_units`; `system_settings.hr` (skeleton config).
- Endpoint: CRUD employees (+filter entity/dept/status), org units; link `user_id`; backfill dari `users`.
- RBAC: role `hr_admin`/`hr_manager` + permission HR + self-service scoping.
- FE: Menu **HRD → Karyawan** (list+form+detail), **Struktur Organisasi**. Field PII di-guard role.
- Migrasi/seed: buat `hr_employees` utk 4 demo users + beberapa karyawan non-sistem (driver/guard) realistis.
- Acceptance: CRUD employee per entitas; sales user ter-link ke employee; gates hijau.

### FASE H1 — Absensi 2-Metode + Clock-in/out + Shift + Geofence
- Koleksi: `hr_shifts`, (`hr_schedules`), `hr_geofences`, `hr_attendance`, `hr_devices`.
- **Geo-tagging mobile:** endpoint clock-in/out (terima GPS+akurasi+selfie opsional) → validasi geofence → status (auto/flag); timestamp presisi server-side; hitung telat/lembur dari shift.
- **Fingerprint import (ZKTeco):** `POST /api/hr/attendance/import` (upload CSV/format ZKTeco dari ZKTime/USB) + `POST /api/hr/attendance/ingest` (dipakai agen jembatan on-prem `tools/zk_bridge.py` via pyzk, auth device_token) → map device_user→emp → `hr_attendance` (idempotent per emp+tgl, gabung in/out). Backend TIDAK konek device langsung (kendala NAT, §10b HR-Q3).
- FE: **Absensi → Kehadiran (tabel harian+rekap)**, **Jadwal/Shift**, **Import Fingerprint**, **Geofence (peta/CRUD)**; **Absen Mobile** (tombol clock-in/out + status lokasi) di shell mobile.
- Acceptance: 1 karyawan bisa clock-in (geo, dalam radius=hadir; luar=flag) & clock-out; durasi+telat benar; impor fingerprint membentuk kehadiran; rekap per periode akurat.

### FASE H2 — Live Position + Field Tracking Sales (kebutuhan owner #2)
- Koleksi: `hr_field_tracks`, `hr_visits`.
- **Live position (WebSocket):** sales app kirim posisi periodik (clock-in s/d clock-out, interval konfigurable) via **`/api/ws/track`**; backend simpan `hr_field_tracks` + cache "posisi terkini per sales" & broadcast ke **Manager Live Map** (subscriber WS). Fallback polling `/api/hr/field-tracks/latest` bila ingress blok WS (validasi di H-POC).
- **Visit check-in:** sales check-in di customer (GPS+foto+catatan) → `hr_visits`, tertaut `customer_id` (+ optional linked SO) → feed KPI kunjungan (KN_17 §6.3).
- Privasi: tracking HANYA jam kerja + indikator aktif + audit; consent dicatat.
- FE: **Sales → Live Map (manager)**, **Kunjungan (Visit log + bukti)**, sales mobile: tombol "Mulai Kunjungan/Selesai".
- Acceptance: posisi sales tampil di peta manager; visit tersimpan dgn bukti GPS+foto; KPI kunjungan/hari terisi.

### FASE H3 — Cuti, Izin & Lembur
- Koleksi: `hr_leave_requests`, `hr_leave_balances`, `hr_overtime`.
- Workflow approval (reuse approval pattern) + saldo cuti; lembur disetujui → input payroll.
- FE: **HRD → Cuti & Izin** (ajukan/approve, kalender), **Lembur**. ESS: karyawan ajukan + lihat saldo.
- Acceptance: pengajuan cuti→approve→saldo berkurang & status absensi update; lembur approved tercatat untuk payroll.

### FASE H4 — Payroll & Payslip (kebutuhan owner #3,#4) ⭐
- Koleksi: `hr_payroll_runs`, `hr_payslips`; akun GL baru (§4.4) + `system_settings.hr` (bpjs/ptkp/ter/jkk/overtime).
- Engine payroll: gross = gaji pokok + tunjangan + lembur + **komisi (tarik dari Sales engine §4.3)**; potongan = BPJS karyawan (Kes 1%, JHT 2%, JP 1%) + PPh21 (TER bulanan); employer contrib (Kes4%, JHT3,7%, JP2%, JKK kelas, JKM0,3%).
- **Integrasi Finance:** posting jurnal payroll run (idempotent) §4.4; pemindahan akrual komisi §4.3; disbursement → kas/bank.
- Payslip PDF (reportlab) + ESS (karyawan unduh slip sendiri).
- FE: **HRD → Payroll** (Run wizard: pilih entity+periode → preview → approve → posting GL → bayar), **Payslip** (list+PDF), **Setup Gaji/BPJS/PPh21** (komponen + config).
- Acceptance: payroll run 1 entitas 1 periode → payslip benar (termasuk komisi sales), jurnal GL SEIMBANG & idempotent, slip PDF terbit, ESS bisa lihat; **rekonsiliasi**: total beban gaji+insentif konsisten (tidak double-count).

### FASE H5 — KPI Design + Self-Service Portal + Design Gallery + AI (✅ IMPLEMENTED · 01 Jul 2026, Session #067)
- Koleksi: `hr_kpi` (hkpi_), `design_gallery` (dsgn_). Config AI: `system_settings` scope='integrations'.
- ESS Portal: dashboard karyawan (absensi, slip, saldo cuti, ajukan cuti/lembur, **+ KPI Saya** kartu MyKpiCard).
- **Design Gallery + AI (Claude langsung):** upload motif (storage lokal JPG/PNG/WEBP ≤10MB) → auto-tag/analisa motif via **Anthropic Claude SDK langsung** (`anthropic`, model claude-sonnet-4-6, vision), key dari `system_settings.integrations.anthropic` (BUKAN lib Emergent). Fitur AI **graceful**: key kosong → gallery tetap jalan, auto-tag balas {enabled:false}.
- FE: **HRD → KPI Design** (KpiView), **Design Gallery + AI** (DesignGalleryView), ESS **KPI Saya** (MyKpiCard), Admin **Integrasi AI** (IntegrationsPanel).
- Acceptance: ✅ KPI design tercatat (CRUD+auto-score+rekap); ESS KPI Saya berfungsi (row-level); gallery + upload gambar + auto-tag graceful; key TIDAK bocor (has_key). Gate hijau + testing_agent_v3 iter_87 (BE 28/28, FE 7/7 US, RBAC 100%, 0 regresi).
- Keputusan owner: 1a (AI struktur dibangun, NONAKTIF default), 2a (KPI manual), 3a (gallery upload), 4a (ESS MyKpiCard).

### FASE H6 — HR Analytics + Regresi & Gate akhir — ✅ SELESAI & VERIFIED (Session #068, 01 Jul 2026)
- Dashboard SDM (headcount, attendance rate, turnover, payroll cost, overtime trend, BPJS/PPh21 payable) → isi menu `cs-bi-sdm`. **IMPLEMENTASI NYATA: id nav = `cs-bi-hrd`, grup 'analitik' (label 'ANALITIK (BI)'), live (bukan coming-soon).**
- Regresi penuh: `seed_reset` + `health_check` + `endpoint_sweep` + `ux_audit` + `verify_api_contract` + `validate_compliance` + `esbuild` + `testing_agent_v3` (semua role: hr_admin, hr_manager, sales, karyawan/ESS).
- **HASIL:** gate statik hijau (api_contract 0 ERR · nav PASS · compliance 0 FAIL · ux_audit 0/0). testing_agent_v3 iter_90: BE 9/9 + FE 27/27 = 100%, 0 bug, 0 regresi. RBAC: sales 403 / manager 200 / admin 200. Fix default-periode (pilih payroll period terbaru yg juga ada absensi). **Modul HRD 7 fase LENGKAP.**

---

## 7. Business Rules (Ringkas — config-driven di `system_settings.hr`)
- **Clock-in/out:** timestamp = server time (UTC simpan, tampil WIB); simpan sumber (geo/fingerprint/manual) + lokasi; telat = clock_in > (shift.jam_in + grace); lembur = menit kerja > shift standar (perlu approval `hr_overtime`).
- **Geofence:** absen geo valid bila jarak(haversine) ≤ radius; di luar → status `flagged` (perlu approval manager) — TIDAK auto-tolak (toleransi lapangan).
- **Tracking sales:** hanya jam kerja (clock-in→out), interval hemat baterai; offline buffer→sync; data retensi & akses terbatas (privasi).
- **BPJS/PPh21/PTKP/TER:** angka di tabel config (lihat §2.2) — mudah update saat regulasi berubah; ceiling upah JKes & JP dihormati.
- **Komisi→payroll:** mode `payroll_commission_mode = accrue_then_settle` (default, §4.3) | `expense_in_payroll` (alternatif).
- **Idempotensi:** import fingerprint, payroll run, posting GL semuanya idempotent (pola number-series + cek existing).
- **Audit:** semua perubahan payroll/absensi/override/cuti → `audit` trail.

---

## 8. Navigasi/Menu (KN_13 — daftarkan sebelum coding)
Grup baru **HRD** (role: hr_admin/hr_manager/owner; sebagian ESS utk semua karyawan):
- Karyawan, Struktur Organisasi (H0)
- Absensi: Kehadiran, Jadwal/Shift, Import Fingerprint, Geofence (H1)
- Sales Field: Live Map, Kunjungan (H2) *(bisa masuk grup Penjualan)*
- Cuti & Izin, Lembur (H3)
- Payroll: Run, Payslip, Setup Gaji/BPJS/PPh21 (H4)
- KPI, Design Gallery (H5), Self-Service (ESS — beranda karyawan)
- HR Analytics → mengisi `cs-bi-sdm` (H6)
> Menu existing `cs-employees`, `cs-attendance`, `cs-kpi`, `cs-design-gallery`, `cs-bi-sdm` (coming-soon) akan **digantikan** bertahap menjadi live (hapus flag comingSoon saat fase terkait selesai).

---

## 9. Acceptance Criteria + Gates (Definition of Done per fase)
- Setiap koleksi/endpoint/menu baru → terdaftar di ENTITY_REGISTRY + KN_13.
- Kontrak aktual dipatuhi: Bearer `sess_`, response array langsung, prefix `/api`, file ≤500 jsx / ≤800 py / ≤300 util.
- Gates hijau: `validate_compliance` 0 FAIL, `ux_audit` 0 ERROR, `verify_api_contract` 0, `seed_reset`/`health_check`/`endpoint_sweep` (0×5xx), `esbuild` 0, `data_integrity` tetap hijau.
- `testing_agent_v3` lulus user-story tiap fase (skip drag-drop/voice/kamera; geo & fingerprint via mock koordinat/CSV).
- Update `plan.md`, `PLAN_HRD.md`, `SESSION_HANDOFF.md`, `ENTITY_REGISTRY.md`, `KN_13` tiap fase.

---

## 10. Keputusan & Pertanyaan Terbuka (HR-Q)
> ✅ TERJAWAB di §10b: HR-Q2 (a, accrue_then_settle), HR-Q3 (ZKTeco: CSV import + bridge on-prem), HR-Q4 (WebSocket), HR-Q5 (Claude langsung + config system), HR-Q8 (urutan rekomendasi).
> ⏳ MASIH TERBUKA (bisa diputuskan saat fase terkait, default rekomendasi dipakai bila tak dijawab):
1. **HR-Q1 Struktur org:** cukup 1 koleksi `hr_org_units` (dept+jabatan via parent) atau pisah `hr_departments` & `hr_positions`? (Rekomendasi: 1 koleksi `hr_org_units` agar ramping.)
2. **HR-Q2 Komisi→payroll:** setuju skema **accrue_then_settle** (insentif akrual ke 2-1500 lalu diselesaikan payroll, §4.3) — bukan re-expense? (Rekomendasi: YA.)
3. **HR-Q3 Fingerprint:** ambil data via **impor file (CSV/format mesin)** dulu (rekomendasi cepat) atau API/SDK vendor? Merek mesin apa?
4. **HR-Q4 Tracking sales:** interval kirim posisi (mis. tiap 5–10 mnt) & retensi data (mis. 90 hari)? Perlu consent eksplisit di app? Live map = polling dulu (WebSocket fase lanjut)?
5. **HR-Q5 Design Gallery + AI:** pakai **Emergent LLM key (Gemini)** untuk auto-tag motif? (Bila ya → saya ambil integration playbook saat H5.) Atau tunda gallery/AI ke akhir?
6. **HR-Q6 Statutory:** konfirmasi angka BPJS & tabel PTKP/TER (akan kita isi di `system_settings.hr`) — pakai default §2.2 dulu, owner koreksi nilai final?
7. **HR-Q7 Cakupan payslip v1:** termasuk THR & pinjaman/kasbon karyawan di v1, atau fase lanjut?
8. **HR-Q8 Urutan:** kerjakan **H-POC → H0 → H1 → H2 → H4 → H3 → H5 → H6** (dahulukan payroll setelah absensi karena prioritas owner), atau strict H0→H6?

---

## 10b. Keputusan Terkonfirmasi Owner + Temuan Integrasi (Session #062b)
> Jawaban owner atas HR-Q + hasil riset kelayakan. **Ini mengikat untuk implementasi.**

- **HR-Q2 = a (TERKONFIRMASI):** komisi pakai skema **accrue_then_settle** (insentif akrual ke `2-1500` lalu diselesaikan payroll, §4.3). `payroll_commission_mode = accrue_then_settle` (default final).
- **HR-Q8 = sesuai rekomendasi:** urutan **H-POC → H0 → H1 → H2 → H4 → H3 → H5 → H6** (payroll didahulukan).

### HR-Q3 — Fingerprint = **ZKTeco** (kelayakan & rancangan)
- ZKTeco mendukung **Pull** (`pyzk`, TCP **4370**) & **Push ADMS** (`/iclock/cdata`).
- ⚠️ **Kendala environment:** backend di cloud (k8s); mesin ZKTeco di LAN kantor (di balik NAT/firewall). (a) Pull TCP 4370 dari cloud → TIDAK bisa langsung. (b) ADMS push memakai path tetap `/iclock/cdata` → **ingress hanya route `/api/*` ke backend**, jadi push device langsung TIDAK sampai ke backend.
- ✅ **Rancangan terpilih (2 jalur, satu endpoint ingest idempotent):**
  1. **Import file (V1, wajib ada):** ekspor log dari ZKTime/USB device → upload **CSV/format ZKTeco** → `POST /api/hr/attendance/import` → bentuk `hr_attendance` (idempotent per emp+tgl, gabung in/out). Tidak bergantung jaringan.
  2. **Agen jembatan on-prem (otomatis, fase berikut):** script kecil (`tools/zk_bridge.py`, dijalankan di komputer LAN kantor) pakai `pyzk` (pull port 4370) → kirim log ter-auth ke `POST /api/hr/attendance/ingest` (token device). Mengatasi NAT + path ADMS. Mendekati real-time (poll tiap N menit).
  - `hr_devices` menyimpan: device SN/IP, lokasi, `device_token` (auth bridge), `last_sync`, mapping `device_user_id → emp_id`.
  - Dependensi baru saat implementasi: `pyzk` (untuk bridge; backend hanya parse payload, TIDAK konek langsung ke device).

### HR-Q4 — Tracking sales = **WebSocket**
- Stack mendukung (uvicorn 0.25 / starlette 0.37.2 / `websockets` 16.0). Endpoint **`/api/ws/track`** (FastAPI `@app.websocket`) — sales kirim posisi, manager subscribe live map.
- ⚠️ **Risiko ingress:** perlu **validasi WS-upgrade lewat `wss://<public>/api/ws/...`** saat **H-POC** (sebagian ingress blok upgrade). **Fallback:** polling `/api/hr/field-tracks/latest` bila WS gagal. Simpan tetap di `hr_field_tracks` (WS hanya transport realtime).
- Hemat baterai: kirim posisi saat clock-in→out, interval konfigurable (`system_settings.hr.track_interval_sec`, default 300s) + buffer offline→sync.

### HR-Q5 — AI = **Claude (Anthropic) LANGSUNG**, bukan lib Emergent (ARAHAN PROJECT-WIDE)
- **Jangan pakai `emergentintegrations`/Emergent universal key.** Pakai **SDK `anthropic` langsung**.
- **Key dikonfigurasi di system** (bukan hardcode, bukan Emergent): `system_settings.integrations.anthropic` `{api_key, model, enabled}` — dikelola via UI Settings (role admin/owner). API/struktur dibuat dulu; key diisi menyusul → fitur AI **auto-aktif saat key terisi** (graceful: bila kosong → fitur AI disembunyikan/disabled, modul tetap jalan).
- Dipakai untuk **Design Gallery auto-tag motif** (Claude vision menganalisa gambar → tag/atribut). Berlaku juga sebagai pola untuk fitur AI lain ke depan.
- Saat implementasi H5: ambil playbook via `integration_playbook_expert_v2` untuk **Anthropic Claude (direct SDK)**, minta API key ke owner, simpan via Settings.

### Tugas POC yang DIPERBARUI (H-POC)
Tambah validasi infra ke `scripts/poc_hrd.py` / cek manual:
4. **WebSocket lewat ingress:** handshake `wss://<public>/api/ws/track` sukses kirim+terima 1 pesan (bila gagal → tandai fallback polling, lapor owner).
5. **Parse CSV ZKTeco** → `hr_attendance` benar (idempotent) tanpa konek device.

---

## 11. Changelog
### v1.2 — Session #062c — H-POC SELESAI ✅ (22/22 PASS)
- `scripts/poc_hrd.py` membuktikan 5 titik berisiko, **semua PASS**:
  1. Geofence haversine (dalam→hadir / luar→flag) + clock-in/out (durasi, telat−grace, lembur) ✅
  2. **Komisi→payroll accrue_then_settle**: jurnal SEIMBANG, komisi TIDAK masuk Beban Gaji (anti double-count), diselesaikan via Dr 2-1500. Komisi NYATA dari engine terbaca (Ayu 80k / Bima 465k / Citra 75k, 2026-06, strategy per_sku) ✅
  3. **BPJS** (Kes1%/JHT2%/JP1% emp; ceiling) + **PPh21 TER** (config-driven) → net pay benar, jurnal payroll (6-6000/6-6100 ; 2-1600/2-1700/2-1800) SEIMBANG ✅
  4. **WebSocket `/api/ws/track` BERHASIL lewat ingress publik (wss)** — handshake+echo OK → **realtime tracking VIABLE, tak perlu fallback polling** ✅ (endpoint minimal sudah ditambah di `server.py`, diperluas di H2)
  5. **Parse CSV ZKTeco** → agregasi per emp+hari (multi-punch in=min/out=max) + **idempotent** (2x run, doc stabil) ✅
- **Kesimpulan:** core HRD de-risked. Lanjut **FASE H0** (Employee Master + Org + RBAC HR).

### v1.1 — Session #062b (jawaban HR-Q + temuan integrasi)
- HR-Q2=accrue_then_settle (final), HR-Q8=urutan rekomendasi. HR-Q3 ZKTeco: jalur **import CSV (V1)** + **agen jembatan on-prem pyzk** (kendala NAT/ingress didokumentasikan; backend tak konek device langsung). HR-Q4 WebSocket `/api/ws/track` (+ validasi ingress di POC, fallback polling). HR-Q5 **Claude (anthropic SDK) langsung, key di system_settings.integrations**, bukan lib Emergent; fitur AI graceful bila key kosong. POC ditambah validasi WS + parse CSV.

### v1 — Session #062
- Blueprint awal modul HRD: gap analysis, analisis sistem HR relevan (best-practice 2026 + payroll Indonesia BPJS/PPh21/TER), arsitektur integrasi (users↔hr_employees, **komisi→payroll anti double-count**, **payroll→GL**), model data (koleksi `hr_*` + prefix), roadmap 7 fase (H-POC, H0–H6) mencakup 5 kebutuhan owner (2 metode absen, live tracking sales, clock-in/out presisi, payroll/payslip + integrasi insentif & finance), business rules, menu KN_13, acceptance/gates, keputusan terbuka HR-Q1–Q8.

---
*SSOT: kode menang. Dokumen ini DRAFT planning; eksekusi menunggu jawaban HR-Q & konfirmasi prioritas owner. Setiap fase update plan.md + ENTITY_REGISTRY + KN_13 + SESSION_HANDOFF.*
