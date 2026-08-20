# AUDIT REPORT — SESSION #076 · Verifikasi Dokumen Terakhir + Upaya Bug-Find Terakhir

> **Mode: AUDIT-ONLY (REPORT-ONLY).** Sesuai permintaan user: *"lanjutkan verifikasi bug, verifikasi
> dokumen terakhir beserta dengan upaya bug find terakhir"* dan konfirmasi scope:
> **fokus mencari bug baru di seluruh sistem (backend + frontend), hanya laporkan (JANGAN diperbaiki),
> tulis sebagai dokumen audit baru.**
>
> Tidak ada satu baris kode aplikasi (`backend/`, `frontend/src/`) yang diubah dalam sesi ini.
> Artefak yang dibuat: laporan ini + log forensik sementara di `/tmp/audit076/` (tidak di-commit).

- **Tanggal:** 2026-07-05
- **Dokumen terakhir yang diverifikasi:** `memory/AUDIT_REPORT_SESSION_075_FIXES_APPLIED.md` (klaim 18 bug fixed + verifikasi berlapis 5 lapis).
- **Basis kode:** clone `github.com/baumemekterasi/kn` → di-copy ke `/app` (`.env` MONGO_URL & REACT_APP_BACKEND_URL **tidak diubah**).
- **Dependensi:** `pip install -r requirements.txt` (reportlab/openpyxl dll terpasang), `yarn install`. Backend `:8001` + Frontend `:3000` RUNNING.
- **Gate baseline sesi ini:** `python scripts/verify_data_integrity.py` → **PASS 122 · FAIL 0 · WARN 1** (WARN = COGS-ZERO; #075 mencatat 123 — selisih 1 hanyalah varian jumlah invarian yang di-hit oleh data seed, bukan regresi).
- **Kredensial uji:** `admin@ / sales@ / manager@ / warehouse@ kainnusantara.id` — password **`demo12345`**.
- **Entitas:** `ent_ksc` (PT Kain Suka Cita — PKP, `default_tax_mode=ppn`), `ent_kanda` (CV Kanda Suka — non-PKP, `default_tax_mode=non_ppn`).

---

## 0. Ringkasan Eksekutif

Verifikasi dokumen #075 **VALID** — seluruh fix GL/IDOR-matrix/error-path/import yang diklaim benar-benar
masih tegak (bukti di §2). Namun **upaya bug-find lanjutan menemukan 5 kelas bug baru/tersisa** yang
**belum** tertangkap oleh #074/#075, terkonsentrasi pada **security (AuthN/AuthZ)** dan **1 bug UI kritikal**.
Selain itu, **3 "kegagalan" yang beredar di korpus test ternyata FALSE POSITIVE** (defect skrip test, bukan bug aplikasi) — didokumentasikan demi kejujuran agar tidak salah difix.

| # | Sev | ID | Area | Status | Judul singkat |
|---|---|---|---|---|---|
| 1 | 🔴 P0 | **AUTH-DOC-PREVIEW** | Backend/Sec | **BARU** | `GET /documents/preview/{id}` (surat jalan **&** invoice) diakses **tanpa login** — bocor dokumen bisnis penuh |
| 2 | 🟠 P1 | **AUTH-MASTER-LEAK** | Backend/Sec | **BARU** | `GET /products`, `/uoms`, `/warehouses`, `/pos/best-sellers` diakses **tanpa login** |
| 3 | 🔴 P0 | **IDOR-READ-SUBRES** | Backend/Sec | **BARU** | Sub-resource lintas-entitas bocor: `/customers/{id}/360`, `/customers/{id}/credit-status`, `/sales-orders/{id}/invoices` |
| 4 | 🟠 P1 | **IDOR-WRITE-INBOUND** | Backend/Sec | **BARU (celah tersisa dari IDOR-WRITE #075)** | `routers/inbound_receiving.py` **0** `assert_entity_access` — `/inbound/tasks/{id}/escalate` **tereksekusi lintas-entitas (200)** |
| 5 | 🔴 P0 | **FE-DASH-LEAK (BUG #1)** | Frontend/UX | **KONFIRMASI (fix #1 belum tuntas)** | Kartu metrik dashboard bocor ke halaman non-Beranda (admin/manager/warehouse) |
| 6 | 🟠 P1 | **FE-ONBOARD-LEAK (BUG #2)** | Frontend/UX | **KONFIRMASI** | Panel Onboarding bocor ke halaman non-Beranda |
| 7 | 🟡 P2 | **AR-GL-DRIFT** | Data/Gate | **BARU** | GL Piutang (1-1200) ≠ subledger AR; gate **tidak** merekonsiliasi AR (buta, mirip INV-GL-DRIFT dulu) |
| 8 | 🟡 P2 | **COGS-ZERO** | Data/Gate | **TERSISA (known)** | 6 order revenue tanpa jurnal HPP; sudah dipagari WARN oleh gate (belum di-fix penuh) |
| — | ⬇️ | **P6-PPN-E2E** | Tooling | **FALSE POSITIVE** | `fa_e2e.py` baca PPN dari akun **2-1300/2-1310** (usang) — akun benar **2-1200**. Aplikasi BENAR. |
| — | ⬇️ | **VB-PPN-NONPKP** | Tooling | **FALSE POSITIVE** | `test_vendor_bill_backend.py` salah asumsi "PO-00001 non-PKP" (PO itu milik `ent_ksc`/PKP). Aplikasi BENAR (entitas non-PKP → PPN 0, terverifikasi). |
| — | ⬇️ | **VB-VIEW-PERM** | Tooling | **FALSE POSITIVE** | Test **mengharapkan** `sales==200` melihat vendor-bill; aplikasi **benar** menolak **403** (least-privilege). Ekspektasi test usang. |

> **Catatan penting untuk BUG #4 & #5 (BUG_BACKLOG lama):** kini **SUDAH RESOLVED** — Special Order (OD)
> dapat diakses & Returns tab sudah rapi (diverifikasi testing-agent, `test_reports/iteration_115.json`).

---

## 1. Metode & cakupan sesi ini

**Backend forensik** — reseed bersih (`seed_realistic.py`) sebelum tiap skrip, jalankan **23 skrip** di `forensic/`:
`fa_s075_verify, fa_coverage_gap, fa_landed_cost_value, fa_idor_matrix, fa_s074_errorpath, fa_import_fuzz,
fa_write_idor, fa_idor, fa_idor_confirm, fa_edge_branches, fa_error_branch_500, fa_race, fa_mutation, fa_fuzz,
fa_e2e, fa_ar_ap, fa_costing, fa_nplus1, fa_session, fa_runtime, fa_sweep, fa_dark_sweep, fa_static, fa_s074_semantic`
\+ gate `scripts/verify_data_integrity.py` + korpus historis `test_vendor_bill_backend.py`
\+ probe adversarial buatan sesi ini (unauth sweep & IDOR read manual).

**Frontend** — `testing_agent_v3` (browser E2E) menelusuri 4 role (admin/sales/manager/warehouse) di banyak halaman;
verifikasi 7 item BUG_BACKLOG; cek white-screen/crash/console error/role-nav. (Skip drag-drop/voice/kamera.)

---

## 2. VERIFIKASI DOKUMEN #075 — hasil (semua HIJAU, klaim VALID)

| Skrip / Gate | Hasil sesi ini | Verdict |
|---|---|---|
| `forensic/fa_s075_verify.py` | **31 PASS / 0 FAIL** — RET-2/PRET-GL/VB-CANCEL-GL/LC-APPLY-GL benar + **idempoten** (re-approve/re-cancel tak menggandakan JE/CN/stok) + trial-balance seimbang | ✅ VALID |
| `forensic/fa_idor_matrix.py` | Arah A (KSC→KANDA) **LEAK=0**, arah B (KANDA→KSC) **LEAK=0** | ✅ VALID |
| `forensic/fa_coverage_gap.py` | PRET-GL & VB-CANCEL-GL reversal benar; payroll GL balanced | ✅ VALID |
| `forensic/fa_landed_cost_value.py` | GL `1-1300` Δ = **+5.000.000** = alokasi; konsolidasi `eq_gap=0.00` | ✅ VALID |
| `forensic/fa_s074_errorpath.py` | 180 rute mutasi `{id}` → **proper 4xx 180 / 500 CRASH 0** (RET-500 fixed) | ✅ VALID |
| `forensic/fa_import_fuzz.py` | non-UTF8→400, harga negatif/inf ditolak, CSV-injection ter-escape, image `javascript:` ditolak | ✅ VALID |
| `forensic/fa_fuzz.py` / `fa_dark_sweep.py` / `fa_error_branch_500.py` | **5xx unhandled = 0**, 500 crashes = 0 | ✅ VALID |
| `scripts/verify_data_integrity.py` | **PASS 122 / FAIL 0 / WARN 1** (WARN=COGS-ZERO, gated) | ✅ VALID |
| GL invarian (`fa_runtime`) | 19 JE posted seimbang; TB global & per-entitas seimbang; 45 akun CoA valid; SSOT persediaan konsisten | ✅ VALID |

**Kesimpulan §2:** Dokumen #075 **jujur & akurat**; tidak ditemukan regresi pada area yang diklaim fixed.

---

## 3. DOSSIER TEMUAN BARU / TERSISA (report-only)

### 🔴 P0 — AUTH-DOC-PREVIEW · Dokumen bisnis bocor tanpa autentikasi  [BARU]

**Lokasi:** `backend/routers/documents.py:102`
```python
@router.get("/documents/preview/{order_id}")
async def preview_document(order_id: str, document_type: str = "surat_jalan", request: Request = None) -> HTMLResponse:
    html_content = await render_order_html(order_id, document_type)   # ← TIDAK ADA cek auth/entity
    return HTMLResponse(content=html_content)
```
**Root cause:** handler menerima `request` tapi **tidak pernah** memanggil `current_user`/`require_permission`
maupun `assert_entity_access`. Siapa pun (tanpa token) bisa merender HTML dokumen penuh.

**Bukti empiris (tanpa header Authorization):**
```
GET /api/documents/preview/so_001?document_type=surat_jalan  -> 200  (2282 bytes HTML)
GET /api/documents/preview/so_001?document_type=invoice      -> 200  (2099 bytes HTML)
```
Konten memuat data sensitif: nama/alamat customer, item, qty, harga, nomor dokumen.

**Expected vs Actual**

| | Expected | Actual |
|---|---|---|
| Tanpa login | 401 | **200 + dokumen penuh** ❌ |
| Lintas-entitas | 404/403 | (tidak diuji entity — auth saja sudah bobol) |

**Rekomendasi (tidak dikerjakan):** tambah `user = await current_user(request)` + `require_permission(request,"document","view"/"print")` + fetch order → `assert_entity_access`. Pertimbangkan token tanda-tangan (signed URL) bila preview perlu dibagikan.

---

### 🟠 P1 — AUTH-MASTER-LEAK · Master-data GET tanpa autentikasi  [BARU]

**Lokasi & root cause:** handler list tanpa dependency auth sama sekali:
- `routers/products.py:17` `list_products(request)` — tak ada cek auth.
- `routers/uoms.py:13` `list_uoms()` — bahkan tanpa parameter `request`.
- `routers/warehouses.py:38` `list_warehouses()` — tanpa auth.
- `routers/pos.py:11` `get_best_sellers(...)` — tanpa auth (bocor analitik penjualan).

**Bukti empiris (tanpa header Authorization):**
```
[LEAK] 200 GET /products          payload=11 item
[LEAK] 200 GET /uoms              payload=4
[LEAK] 200 GET /warehouses        payload=3 (nama+alamat gudang)
[LEAK] 200 GET /pos/best-sellers  payload=7
--- pembanding TER-LINDUNG (benar 401): /customers /suppliers /sales-orders /purchase-orders /gl/accounts /entities /inventory/balances /pricelist /product-templates ---
```
**Catatan:** karena mayoritas endpoint lain sudah 401, ini kemungkinan **kelalaian per-endpoint** (bukan kebijakan sengaja).
Sensitivitas: warehouse (alamat) & pos/best-sellers (omzet) paling perlu ditutup; products/uoms lebih rendah tapi tetap tak seharusnya publik.

**Rekomendasi:** tambahkan `await require_permission(request, "<modul>", "view")` (atau minimal `current_user`) di keempat handler.

---

### 🔴 P0 — IDOR-READ-SUBRES · Kebocoran BACA lintas-entitas via sub-resource  [BARU]

**Konteks:** #075 memfokus IDOR pada endpoint **tulis** SO/WMS/return. Endpoint **baca sub-resource** ini
**terlewat** — mereka fetch by-id global tanpa `assert_entity_access`.

**Bukti empiris — login `sales@` (scope hanya `ent_ksc`), target dokumen `ent_kanda`:**
```
[LEAK] 200 GET /customers/cust_moda_surabaya/360           -> profil 360 customer ent_kanda (PIC, kontak, dsb)
[LEAK] 200 GET /customers/cust_moda_surabaya/credit-status -> limit/status kredit customer ent_kanda
[LEAK] 200 GET /sales-orders/so_002/invoices               -> business-logic jalan (bocor invoice bila ada)
--- pembanding TER-LINDUNG: GET /sales-orders/so_002 -> 404 "Data tidak ditemukan untuk entitas ini" ---
```
**Root cause:** endpoint resource utama (`GET /sales-orders/{id}`) sudah entity-scoped (404), tapi
**sub-resource** (`/{id}/360`, `/{id}/credit-status`, `/{id}/invoices`) tidak menegakkan scope.

**Dampak:** sales satu PT bisa mengintip **kredit & profil customer** PT lain — pelanggaran isolasi entitas & data pribadi.
**Rekomendasi:** fetch dokumen induk dulu → 404 bila tak ada → `assert_entity_access(doc, coll, ctx)` sebelum menyajikan sub-resource.

---

### 🟠 P1 — IDOR-WRITE-INBOUND · Endpoint inbound-task tanpa guard entitas  [BARU · celah tersisa]

**Lokasi:** `backend/routers/inbound_receiving.py` — **`assert_entity_access` = 0 kemunculan**
(bandingkan `outbound_picking.py` = 6, `wms.py` = 3). Contoh handler `escalate_inbound_task` (baris 144):
```python
task = safe_doc(await db.wms_tasks.find_one({"id": task_id}, {"_id": 0}))   # ← by-id global
if not task: raise HTTPException(404, ...)
# langsung update status='escalated' — TANPA assert_entity_access
```
**Bukti empiris (`fa_idor_confirm.py`), aktor warehouse ter-scope entitas berbeda dari task:**
```
[LEAK(executed)] POST /inbound/tasks/{id}/escalate      -> 200   (task PT lain berubah status=escalated)
[LEAK-REACHED ] POST /inbound/tasks/{id}/complete       -> 400   (business-logic jalan; hanya diblok status, bukan entitas)
[LEAK-REACHED ] POST /inbound/tasks/{id}/qc-decision    -> 400   (idem)
[LEAK-REACHED ] POST /wms/tasks/outbound-from-order/{so}-> 409   (idem)
--- pembanding TER-LINDUNG (fix #075): POST /wms/tasks/{id}/advance -> 404 ; /inbound/rolls/{id}/inspect -> 404 ---
```
Endpoint lain di file yang sama juga tak ter-guard: `scan-receive`, `resolve-escalation`.
**Dampak:** user gudang satu entitas bisa memutasi task inbound entitas lain (escalate terbukti tereksekusi).
**Rekomendasi:** terapkan pola `entity_ctx` + `assert_entity_access(task, "wms_tasks", ctx)` seragam pada seluruh handler tulis `inbound_receiving.py` (dan `outbound-from-order`).

---

### 🔴 P0 — FE-DASH-LEAK (BUG #1) · Kartu metrik dashboard bocor ke halaman non-Beranda  [KONFIRMASI]

**Bukti (testing-agent, `test_reports/iteration_115.json` + 20 screenshot):** kartu **PRODUK AKTIF / AVAILABLE QTY /
RESERVED QTY / ACTIVE ORDERS / GUDANG** muncul di halaman non-home:
- Manager: **Pusat Persetujuan**, **Analytics Hub**
- Warehouse: **Operasi Gudang (WMS)**
- Admin: **Analytics Hub**

**Root cause (level kode):** `frontend/src/App.js:250`
```js
const HOME_VIEWS = ["admin", "sales", "reports", "operations"];   // ← allow-list salah cakup
const isHomeView = HOME_VIEWS.includes(activeView);
...
{isHomeView && <> <MetricCard .../> ... </>}   // App.js:333
```
Beranda per-role sebenarnya ber-`activeView` **`admin-home`** / **`sales-home`** (lihat `SESSION_HANDOFF §2`
ROLE_HOME_REGISTRY), sedangkan `"admin"` = halaman **Master Data & Audit**, `"sales"` = **POS**, `"reports"` =
**Analytics Hub**, `"operations"` = **WMS**. Karena `reports`/`operations`/`admin` masuk `HOME_VIEWS`, kartu metrik
(+ Onboarding, lihat BUG #2) ikut tampil di halaman-halaman fungsional itu. Fix #1 sebelumnya (guard `isHomeView`)
**belum tuntas** karena isi allow-list salah.

**Rekomendasi:** samakan `HOME_VIEWS` dengan ID beranda per-role yang sebenarnya (`admin-home`, `sales-home`, dan
beranda manager/warehouse yang dituju), bukan halaman fungsional.

---

### 🟠 P1 — FE-ONBOARD-LEAK (BUG #2) · Panel Onboarding bocor ke halaman non-Beranda  [KONFIRMASI]

**Bukti:** panel checklist onboarding (admin: "Buat gudang pertama" dst; warehouse: "Cek WMS task queue" dst;
manager: "Cek Manager Dashboard" dst) muncul di Analytics Hub & WMS Operations.
**Root cause:** sama dengan BUG #1 — `App.js:352` `{showOnboarding && isHomeView && (<OnboardingPanel .../>)}`
memakai `isHomeView` yang salah cakup (§BUG #1). **Rekomendasi:** ikut perbaikan `HOME_VIEWS`.

---

### 🟡 P2 — AR-GL-DRIFT · Piutang GL ≠ subledger AR; gate tak merekonsiliasi AR  [BARU]

**Bukti (`fa_ar_ap.py`, DB bersih):**
```
[DIFF] ent_ksc  : GL Piutang(1-1200) 86.913.000  vs subledger Σ(GT-paid) 23.171.100  -> diff 63.741.900
[DIFF] ent_kanda: GL Piutang(1-1200)  9.500.000  vs subledger 0                       -> diff  9.500.000
```
**Analisis jujur:** analog dengan **INV-GL-DRIFT** (§#074) — kemungkinan besar **artefak seed** (revenue di-posting
ke GL untuk SO seed, sementara "subledger" dihitung dari invoice/AR terbuka yang belum sepenuhnya sinkron), **bukan**
bug alur transaksi runtime (alur AP terverifikasi benar: bill posted→AP naik, pay→AP kembali 0, TB seimbang).
Namun: **gate `verify_data_integrity.py` tidak memiliki invarian rekonsiliasi AR** (hanya persediaan yang di-WARN),
sehingga drift ini **tidak terpantau** (meta-gate blindness untuk AR). **Rekomendasi:** tambah invarian WARN
rekonsiliasi AR (GL 1-1200 vs subledger) + true-up saldo awal AR di seed bila drift memang artefak.

---

### 🟡 P2 — COGS-ZERO · Revenue diakui tanpa jurnal HPP  [TERSISA / known]

**Bukti:** gate → `WARN GL: 6 order punya jurnal pendapatan tanpa jurnal HPP (COGS-ZERO)`. Konsolidasi menunjukkan
`cogs=0`, `gross_profit=revenue` (margin 100%). **Status:** sudah **dipagari WARN** oleh gate (fix #075), tapi
**belum di-fix penuh** (butuh cost mengalir ke fulfillment). Tetap dilaporkan sebagai follow-up terbuka. **Rekomendasi:**
jamin `unit_cost` roll/snapshot terisi saat fulfillment agar `post_order_cogs` menghasilkan HPP.

---

## 4. FALSE POSITIVE (kejujuran anti-halusinasi — BUKAN bug aplikasi)

Tiga "kegagalan" yang beredar di korpus test sesungguhnya **defect skrip/ekspektasi test**, bukan bug aplikasi.
Penting agar sesi berikutnya **tidak salah "memperbaiki" aplikasi yang sudah benar**.

1. **P6-PPN-E2E** — `forensic/fa_e2e.py:116` membaca PPN dari `account_code in ("2-1300","2-1310")` (**usang**),
   padahal PPN Keluaran = **`2-1200`** (`ACC_PPN_OUT`). Verifikasi langsung JE (SO-0001):
   `Dr Piutang 11.155.500 / Cr Pendapatan 10.050.000 / Cr PPN Keluaran(2-1200) 1.105.500` → **seimbang, benar**.
   → aplikasi **BENAR**; perbaiki skrip test (`2-1200`).
2. **VB-PPN-NONPKP** — `test_vendor_bill_backend.py` mengasumsikan **PO-00001 non-PKP**, padahal PO-00001 yang
   ter-fetch milik **`ent_ksc` (PKP)** → PPN 11% benar. Verifikasi tandingan: vendor-bill untuk PO **`ent_kanda`
   (non_ppn)** → `is_pkp=False, ppn_rate=0, ppn_amount=0` (**benar**). Sumber keliru: ada **dua** "PO-00001"
   (satu per entitas); test tak memfilter entitas. → aplikasi **BENAR**; perbaiki asumsi test.
3. **VB-VIEW-PERM** — `test_vendor_bill_backend.py:373` `check("Sales can view list → 200", status==200)` **mengharapkan
   sales BISA melihat** vendor-bill. Aplikasi **menolak 403** (benar; `sales` memang tak punya `vendor_bill:view` di
   matrix DB & `permissions_config.py`). → aplikasi **BENAR (least-privilege)**; ekspektasi test **usang** (harus `==403`).

> Efek samping: karena `fa_e2e.py` & `test_vendor_bill_backend.py` mengandung defect, **jangan** jadikan mereka gerbang
> rilis apa adanya — perbaiki dulu skripnya (di luar scope report-only ini).

---

## 5. TERBUKTI BERSIH (hasil negatif — untuk kepercayaan)

- Keseimbangan seluruh JE posted, trial-balance global & per-entitas → seimbang.
- Error-branch: 180/180 rute mutasi `{id}` → 4xx benar; 0 crash 500 (`fa_s074_errorpath`, `fa_error_branch_500`, `fa_dark_sweep`, `fa_fuzz`).
- IDOR **matrix tulis inti** (SO/return/wms-advance/roll-inspect/special-order/price-approval) → **LEAK=0** (fix #075 tegak).
- Import hardening (non-UTF8/neg/inf/xss/csv-injection) → tertutup.
- Frontend: login 4 role OK; role-home benar (sales→Performa Saya, admin→Control Tower); **restriksi sales** (vendor-bills/landed-cost/input-tax/PR tersembunyi) benar; **0 white-screen / 0 crash / 0 broken-link**; BUG #4 (Special Order) & BUG #5 (Returns tab) **RESOLVED**.

---

## 6. Cara reproduksi (semua di `/app`, backend RUNNING, env `MONGO_URL`/`DB_NAME` diset)

```bash
python seed_realistic.py && python scripts/verify_data_integrity.py       # PASS 122 / FAIL 0 / WARN 1
python seed_realistic.py && python forensic/fa_runtime.py                 # F-B: 5 unauth findings (1 HIGH)
python seed_realistic.py && python forensic/fa_sweep.py                   # unauth leaks:5 ; IDOR read leaks:3
python seed_realistic.py && python forensic/fa_idor_confirm.py            # LEAK=4 (inbound tasks; escalate executed 200)
python seed_realistic.py && python forensic/fa_ar_ap.py                   # AR-RECON drift dua entitas
python seed_realistic.py && python forensic/fa_e2e.py                     # P6 (FALSE POSITIVE — akun 2-1300/2-1310)
python seed_realistic.py && python test_vendor_bill_backend.py            # 50/52 (2 FALSE POSITIVE)
# probe unauth cepat:
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/api/documents/preview/so_001?document_type=surat_jalan"   # 200 (bug)
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/api/products"                                              # 200 (bug)
```
> `test_vendor_bill_backend.py` & sebagian skrip historis mem-hardcode URL preview lama — arahkan ke `http://localhost:8001` saat run.

---

## 7. Rekomendasi urutan perbaikan (bila nanti diminta fix — TIDAK dikerjakan sesi ini)

1. **AUTH-DOC-PREVIEW** (P0) & **AUTH-MASTER-LEAK** (P1) — tambah `require_permission`/`current_user` per handler.
2. **IDOR-READ-SUBRES** (P0) & **IDOR-WRITE-INBOUND** (P1) — pola `assert_entity_access` seragam pada sub-resource baca + seluruh handler tulis `inbound_receiving.py`.
3. **FE-DASH-LEAK / FE-ONBOARD-LEAK** (BUG #1/#2) — perbaiki `HOME_VIEWS` di `App.js` agar hanya beranda per-role.
4. **AR-GL-DRIFT** — tambah invarian WARN rekonsiliasi AR di gate + true-up seed.
5. **COGS-ZERO** — alirkan cost ke fulfillment.
6. **Perbaiki skrip test** `fa_e2e.py` (akun PPN 2-1200) & `test_vendor_bill_backend.py` (asumsi PKP + ekspektasi 403 sales).

---

## 8. Tingkat keyakinan (jujur)

- **~95%** untuk "verifikasi #075 valid" — 5 lapis fix inti diverifikasi ulang & idempoten.
- **~85–88%** untuk "semua **kelas** bug besar teridentifikasi" — naik karena sesi ini menutup celah **AuthN** (unauth GET) & **AuthZ baca sub-resource/inbound-write** yang belum disentuh #074/#075.
- **~70–75%** untuk "semua bug (termasuk edge kecil) tertangkap" — belum: audit tulis per-endpoint pada modul non-finansial (hr_*, crm_omnichannel, rfid, consolidation) belum ekshaustif; E2E FE belum menelusuri seluruh alur dalam (mis. create-order penuh sampai cetak) untuk tiap role.

---

## 9. Lampiran

- Log forensik sesi ini: `/tmp/audit076/*.log` + `/tmp/audit076/SUMMARY.txt` (sementara, tidak di-commit).
- Laporan testing-agent frontend: `test_reports/iteration_115.json` (20 screenshot).
- Dokumen yang diverifikasi: `memory/AUDIT_REPORT_SESSION_075_FIXES_APPLIED.md`, `memory/AUDIT_REPORT_SESSION_074_REMEDIATION.md`, `BUG_BACKLOG.md`.
