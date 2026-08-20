# 🤝 HANDOFF — Kain Nusantara ERP/WMS (untuk agent sesi berikutnya)

> **Terakhir diperbarui:** sesi **2026-07-26 (lanjutan-2)** — `plan.md` **Phase 1–6 SELESAI & TERUJI**
> (Fase D Makloon · Fase E Sourcing Berbasis Kontrak · **Fase F-1 Penerimaan Satuan Supplier**).
> **Menunggu keputusan pemilik** untuk fase berikutnya (kandidat **F-2…F-6**, lihat §3).
> **BAHASA:** User berbahasa **INDONESIA** — selalu balas dalam Bahasa Indonesia.
> **GAYA KERJA USER:** kerjakan fase **satu per satu**, dan **BERHENTI minta approval** setelah tiap fase selesai.
> **METODE TEST tiap fase:** `testing_agent_v3` backend **dan** frontend (keduanya sudah terbukti jalan di repo ini).
> **Aturan emas:** **KODE MENANG atas DOKUMEN.**

---

## 1. STATUS SAAT INI (SSOT rencana = `/app/plan.md`)

| Phase | Judul | Status |
|-------|-------|--------|
| 1 | POC Core Fase D (isolated) | ✅ **SELESAI** — `backend/test_fase_d_makloon_poc.py` **69 PASS / 0 FAIL** |
| 2 | Fase D V1 (backend + frontend + invarian + gate) | ✅ **SELESAI** |
| 3 | Fase D E2E + bugfix + docs | ✅ **SELESAI** — BE 98% · FE 100% · `docs/KN_24_PLAN_FASE_D_MAKLOON.md` |
| 4 | POC + V1 Fase E (sourcing kontrak · `supplier_items` · PR routing) | ✅ **SELESAI** — POC **69/0** |
| 5 | Fase E E2E + docs (`KN_25`) | ✅ **SELESAI** — iter_167 + iter_169 (6/6, 0 bug) · 4 bug diperbaiki · gate baru `INV-UI-01` |
| 6 | **Fase F-1 — Penerimaan berbasis SATUAN SUPPLIER** (`KN_26`) | ✅ **SELESAI** — POC **47/0** · iter_170 **99%** · 2 bug diperbaiki (1 **P1 pra-ada**) · invarian baru `INV-RCV-01..03` |
| **7** | **MENUNGGU KEPUTUSAN PEMILIK** — kandidat **F-2…F-6** *(+ utang teknis §G-12)* | 🟡 **BERIKUTNYA** |
| **G** | **FASE G — FINANCE: FLEKSIBILITAS PENUH DENGAN KENDALI** (9 permintaan pemilik, `plan.md` §FASE G) | 🟡 **RENCANA** — butuh keputusan pemilik di **§G-0.4** |

### Bukti gate — diverifikasi ulang pada **pod/preview baru** (sesi 2026-07-26 lanjutan-2)

Repo di-clone ulang dari GitHub ke `/app` (`.env` container **tidak disentuh**), dependensi
dipasang, DB di-seed, bundel FE di-build ulang, lalu **seluruh gate dijalankan kembali**:

| Perintah | Hasil |
|---|---|
| `python backend/test_fase_f1_receiving_uom_poc.py` | ✅ **PASS 47 / FAIL 0** (self-cleanup) — **Fase F-1** |
| `python backend/test_fase_e_contracts_poc.py` | ✅ **PASS 69 / FAIL 0** (self-cleanup) — regresi Fase E nol |
| `python scripts/verify_data_integrity.py` | ✅ **PASS 179 / FAIL 0 / WARN 0** (`INV-MKO-01…06` · `INV-SRC-01…05` · **`INV-RCV-01…03`** hijau) |
| `python scripts/validate_compliance.py` | ✅ **124 PASS / 0 FAIL / 19 WARN** (tech-debt lama — **tanpa warning baru**) |
| `python scripts/check_nav_map.py` | ✅ **PASS** (compliant KN_13 grouped IA) |
| `bash scripts/gate.sh` | ✅ **SEMUA GATE (non-skip) HIJAU** → `memory/GATE_RECEIPT.md` |
| `yarn build` (frontend) | ✅ sukses → `frontend/build/` terisi (preview live) |
| `testing_agent_v3` iter_170 | ✅ **overall 99%** · 0 bug kritikal · FE 6/6 fitur · **0 console error** |
| Verifikasi UI (Playwright) | ✅ Login · Control Tower · **Barang Supplier** (7 item) · **PR-00005** (2 *Beli* + 1 *Makloon*) · **Inbound satuan supplier** (25 cone → 47,25 kg · sisa 2 satuan · riwayat jejak · peringatan 2 satuan) — **0 console error** |

**Keputusan pemilik Fase E (sudah dieksekusi):**
1. `supplier_items` — **FULL: impor massal CSV/Excel** + CRUD manual + pencarian by SKU supplier. ✅
2. PR baris ber-mode `makloon` → **1 klik dari PR membuka Wizard Makloon ter-prefill**. ✅

**Keputusan desain Fase F-1 (sudah dieksekusi):** F1-01 … F1-08 — detail di
`docs/KN_26_PLAN_FASE_F1_RECEIVING_UOM.md` §2.

---

## 2. ⚠️ SETUP LINGKUNGAN (WAJIB DIBACA bila pod/preview baru)

File `.env` **tidak ada di repo** (gitignored) — **jangan pernah menimpanya**.
`frontend/build/` juga **tidak ada di repo** → FE **WAJIB** di-build (preview dilayani
`frontend/static_server.js` dari `frontend/build`, **tidak ada hot-reload**).

```bash
# 1) Restore kode (JAGA .env!)
cd /tmp && git clone --depth 3 <REPO_URL> knrepo
cp /app/backend/.env /tmp/be.env.bak && cp /app/frontend/.env /tmp/fe.env.bak
rsync -a --exclude='node_modules' --exclude='__pycache__' --exclude='.env' /tmp/knrepo/ /app/
cp /tmp/be.env.bak /app/backend/.env && cp /tmp/fe.env.bak /app/frontend/.env

# 2) Dependensi
cd /app/backend && grep -v -E "^(emergentintegrations|litellm)" requirements.txt > /tmp/req.txt \
  && pip install -r /tmp/req.txt        # 2 baris itu konflik URL-pin & TIDAK dipakai kode
cd /app/frontend && yarn install --frozen-lockfile     # JANGAN npm
supervisorctl restart backend

# 3) Data + build FE + verifikasi
cd /app && python seed_realistic.py
python scripts/verify_data_integrity.py                  # target 179 / 0 / 0
cd /app/frontend && setsid nohup env NODE_OPTIONS=--max-old-space-size=3072 \
  GENERATE_SOURCEMAP=false CI=false DISABLE_ESLINT_PLUGIN=true yarn build \
  > /app/.fe_build.log 2>&1 < /dev/null & disown      # ~5 menit
```

> ⚠️ **Gotcha build FE:** jalankan build **detached** (`setsid nohup … & disown`). Bila hanya
> `nohup … &`, proses build ikut mati saat pod/tool-session restart dan `build/` tinggal separuh
> (gejala: `ls frontend/build` hanya berisi `leaflet`).

Login cek cepat:
```bash
curl -s -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@kainnusantara.id","password":"demo12345"}'
```
Kredensial lengkap: `/app/memory/test_credentials.md` (semua role `demo12345`).

---

## 3. TUGAS BERIKUTNYA — MENUNGGU KEPUTUSAN PEMILIK

### 3.0 ⭐ FASE G — FINANCE: FLEKSIBILITAS PENUH DENGAN KENDALI (BARU, prioritas pemilik)
Pemilik menyampaikan **9 permintaan finance** (sesi 2026-07-26). Rencana lengkap: **`/app/plan.md`
→ `# FASE G`**. Prinsip pemilik: *“yang terpenting adalah flexibilitas penuh namun security
tetap terjaga.”*

**Pola inti yang dirancang = “AMANDEMEN BERALASAN”** (baca `plan.md` §G-0.2):
tidak ada edit senyap · edit di **SUMBER** bukan nominal invoice · invoice terbit dikoreksi lewat
**Nota Kredit/Debit** (append-only) · approval berbasis **dampak** · **label alasan
(`reason_code`) adalah kelas satu** (taksonomi 18 label di §G-0.3).

| Sub-fase | Isi | Permintaan |
|---|---|---|
| **G-1** | Fondasi amandemen (`doc_amendments`, `amendment_reasons`, `credit_notes`) + RBAC + amandemen SO | #1 |
| **G-2** | **Payment Plan Builder** (DP 15% + 6× cicilan dst) + **denda sebagai dokumen** (draft⇒bisa dibatalkan tanpa mengotori GL) | #3 |
| **G-3** | Kebijakan **selisih pembayaran** lebih/kurang bayar (toleransi + 3 pilihan berlabel) | #4 |
| **G-4** | `refs[]` tersimpan di SEMUA dokumen + nomor referensi di PDF + Jejak Dokumen + editor/preview/ttd advanced | #2 |
| **G-5** | Unlock periode berotoritas (`period:unlock`, dual-control, jendela berbatas) | #5 |
| **G-6** | **Transaksi** antar entitas (jual-beli + margin + saldo IC + eliminasi konsolidasi) | #6 |
| **G-7** | Kontrabon batch + jadwal tukar faktur + 3-way match + potongan | #7 |
| **G-8** | Rekon bank: parser multi-bank, skor berbobot, many-to-one, rule engine, holding account | #8 |
| **G-9** | **Pusat Kasus Keuangan** (salah transfer rekening, dana tak dikenal, bayar 2×, giro ditolak, dll) | #9 |

⚠️ **JANGAN mulai eksekusi sebelum 7 keputusan pemilik di `plan.md` §G-0.4 dijawab**
(ambang approval · retroaktif koreksi harga master · default denda · toleransi pembulatan ·
wewenang unlock periode · mode margin antar entitas · siklus & toleransi kontrabon).
Urutan eksekusi berbasis dependensi ada di §G-11 (mulai dari **G-1**).

### 3.1 Kandidat fase F (lanjutan sourcing)

Detail di `/app/plan.md` §3 *Next Actions*. Ringkas:

| Kode | Judul | Isi singkat |
|---|---|---|
| ~~F-1~~ | ~~Penerimaan berbasis satuan supplier~~ | ✅ **SELESAI** (Phase 6 · `docs/KN_26_PLAN_FASE_F1_RECEIVING_UOM.md`) |
| **F-2** | **Kepatuhan harga PO vs kontrak** | Mode `off\|warn\|block` bila harga PO diubah manual menyimpang dari kontrak aktif + approval selisih harga. |
| **F-3** | **Impor massal kontrak + kedaluwarsa** | Pola impor massal seperti `supplier_items` untuk kontrak pembelian + notifikasi kedaluwarsa H-30 (kini hanya KPI). |
| **F-4** | **Skor & perbandingan supplier** | Skor dari jejak sourcing (harga realisasi, ketepatan kirim, selisih grade) untuk negosiasi kontrak berikutnya. |
| **F-5** | **Satuan supplier di retur beli & vendor bill** *(BARU · turunan F-1)* | Samakan perlakuan satuan supplier pada **retur beli** (nota debit dalam satuan supplier) & **pencocokan vendor bill** (harga per `supplier_uom` vs per satuan KN). Sekarang baru penerimaan yang mendukung. |
| **F-6** | **Audit satuan berat** *(BARU · turunan F-1)* | `WEIGHT_BASE_KG` kini mendukung `gram/ton/lbs/ounce` sebagai base unit. Audit produk yang memakainya + tambah aturan registry eksplisit bila perusahaan mulai membeli dalam satuan tsb. |

**Pola kerja tiap fase (WAJIB, sudah terbukti di Fase A–F1):**
1. `plan.md` → tulis phase + **user stories** + deliverables + evidence.
2. **POC-first**: `backend/test_<fase>_poc.py` — **single script**, via HTTP, **self-cleanup**
   (contoh terbaik: `backend/test_fase_f1_receiving_uom_poc.py` / `test_fase_e_contracts_poc.py`).
   **HIJAU 100% dulu** sebelum FE.
3. Backend → invarian baru di `scripts/verify_data_integrity.py` → **0 FAIL**.
4. Frontend → `yarn build` → `check_nav_map.py` → `gate.sh`.
5. `testing_agent_v3` **BE + FE** → fix sampai **0 bug**.
6. Bila ada bug yang **lolos gate** ⇒ **tambah gate** (aturan emas; contoh: `INV-UI-01`).
7. Update `memory/SESSION_LOG.md`, `plan.md`, `memory/HANDOFF.md`, `docs/KN_2x_…` →
   **BERHENTI & minta approval user**.

### Koleksi baru — checklist pendaftaran (WAJIB, kalau lupa gate MERAH)
`ENTITY_REGISTRY.md` · `scripts/validate_compliance.py` (**2 titik**: `known_collections` &
daftar "tanpa prefix" di CHECK NAMING) · `scripts/verify_contract.py` `CANONICAL_COLLECTIONS` ·
`backend/entity_scope.py SCOPED_COLLECTIONS` · `backend/indexes.py`.
⚠️ Koleksi yang diakses lewat `db[COLL]` (variabel) **lolos regex** gate — daftarkan manual!

### Wiring FE (3 file, urutan properti WAJIB)
1. `frontend/src/AppViewRouter.jsx` — lazy import + `{activeView === "<view>" && <View .../>}`.
2. `frontend/src/config/navStructure.js` — item di array hub yang tepat; properti **`view` → `label` → `roles`**.
3. `frontend/src/config/navMeta.js` — `{ kicker, title }` halaman.

### Kelas CSS yang TERSEDIA
`section-card`, `section-head`, `section-body`, `field`, `textarea`, `data-table`,
`primary-button`, `secondary-button`, `danger-button`, `icon-button`,
`notice-bar success|danger`, `status-pill` + `pill-success|pill-warning|pill-danger|pill-muted`,
`badge-*`, `modal-overlay`, `modal-card` (`.wide`/`.small`), `modal-title`, `modal-subtitle`,
`modal-actions`, `metric-card`, `metric-tile`, `tabular-nums`, `tab-bar`/`tab-button`, `btn-xs`.
Spinner: `animate-spin` (Tailwind).
⚠️ JANGAN pakai kelas tak terdefinisi (`stat-card`/`input-select`/`input-field`/`link-button`/`spin`).
`ErrorNotice` menerima prop **`message`** (string), BUKAN `error`.
**Backdrop modal baru WAJIB** pakai `utils/overlayDismiss.js` (gate `INV-UI-01`).

---

## 4. RINGKASAN FASE F-1 (referensi cepat — detail: `docs/KN_26_PLAN_FASE_F1_RECEIVING_UOM.md`)

- **TIDAK ada koleksi baru.** Field additive di `wms_tasks` (inbound):
  `supplier_uom` · `supplier_conv_factor` · `last_receive_doc_uom` ·
  `scan_log[].uom_trail` · `receive_uom_trails[]` (jejak + `scan_id` + `actor`).
  `purchase_orders.items[]` juga membawa `supplier_uom`/`supplier_conv_factor`.
- **Prioritas faktor:** `same_unit` → **`supplier_item`** (`conv_factor`) → **registry global**
  (`uom_rules_service`) → gagal ⇒ **400 actionable** (arahkan ke *Barang Supplier*).
- **API:** `GET /api/inbound/tasks/{id}/uom-options` · `POST …/preview-uom` (read-only) ·
  `POST …/scan-receive` (+ `doc_uom`/`doc_qty` **opsional** ⇒ backward-compatible) ·
  `GET/PUT /api/receiving/uom-settings` (ubah butuh **`settings:manage`**).
- **Kebijakan** (`system_settings` scope **`receiving`**, tanpa deploy):
  `supplier_uom_input_mode (off|optional|prefer)` · `require_supplier_item_for_supplier_uom` ·
  `block_over_remaining`. Service: `backend/services/receiving_uom_service.py`.
- **Invarian:** `INV-RCV-01` jejak lengkap · `INV-RCV-02` `doc_qty × factor == task_qty ==
  scan_log[].actual_qty` · `INV-RCV-03` sumber faktor sah + `supplier_item_id` hidup + akumulasi
  sinkron (lapis `L4-RCV` di `verify_data_integrity.py`).
- **Layar:** *Gudang → Operasi WMS → tab **Inbound*** (panel `receive-uom-panel`: pemilih satuan,
  hint faktor, pratinjau live, sisa 2 satuan, peringatan 2 satuan, riwayat jejak) ·
  *Produk & Harga → **Konversi Satuan*** (kartu `receiving-uom-policy-card`).
  ⚠️ Kebijakan F-1 **sengaja tidak** jadi menu baru → `check_nav_map` tetap PASS.
- **Data demo:** 2 task inbound — `BNG-KTN-001` benang per **cone** (1 cone = 1,89 kg, belum
  diterima) & `LRK-CLSC-001` lurik per **roll** (1 roll = 40 yard, sudah 5 roll = 200 yard
  **dengan jejak**). Lihat `seed_receiving_supplier_uom_demo()` di `seed_realistic.py`.
- **Bug P1 PRA-ADA yang ikut beres:** `KN-F1-KGBASE-GR` — penerimaan produk berbasis **`kg`**
  (benang/obat celup tanpa gramasi/lebar) dulu **mustahil** diselesaikan (`complete` selalu 400).
  Fix di `uom_service.kg_per_base_unit()` via tabel `WEIGHT_BASE_KG`.
  ⚠️ Jangan kembalikan perilaku lama: produk per-kg TIDAK butuh gramasi/lebar.

---


## 4b. RINGKASAN FASE E (referensi cepat — detail: `docs/KN_25_PLAN_FASE_E_SOURCING_CONTRACTS.md`)

- **Koleksi baru:** `supplier_items` (prefix `sit_`, SCOPED) — kunci unik logis
  **(supplier_id, supplier_sku)** → impor massal **idempotent** (jalan 2× ⇒ `created=0`).
  Field inti: `supplier_sku`, `supplier_item_name`, `supplier_uom`, `conv_factor`,
  `last_price`, `moq`, `lead_time_days`, `expected_grade`, `usage_count` (>0 ⇒ DELETE 409).
- **`supplier_contracts.contract_type=purchase`** — kontrak pembelian per supplier×produk
  (basis unit, harga, validitas, MOQ) + `resolve_active` dipakai saat PO create
  (`price_source` dicatat: kontrak vs manual).
- **PR routing:** `purchase_requisitions.items[].fulfillment_mode ∈ purchase|makloon`
  (default `purchase`, backward-compatible). Realisasi bertahap:
  baris `purchase` → **PO** (menyimpan `contract_id`, `supplier_item_id`, `supplier_sku`,
  `expected_grade`, `price_source`), baris `makloon` → **payload prefill Wizard Makloon**
  + Makloon Order tertaut PR. Status PR (`open|partially_realized|realized`) **turunan murni**.
- **Invarian:** `INV-SRC-01…05` + `INV-UI-01` (gate perilaku UI: backdrop modal hanya menutup
  lewat gestur utuh; isi dropdown ber-portal wajib `stopPropagation()`).
- **Layar FE:** *Pembelian → Master Pembelian → **Barang Supplier*** (CRUD + Impor Massal +
  cari SKU supplier) · *Pengadaan (Sourcing) → Purchase Requisition* (selector pemenuhan per
  baris + panel realisasi) · PO create contract picker · Inbound menampilkan nama supplier + nama KN.
- **Data demo:** 7 barang supplier · kontrak pembelian · **PR-00005** (2 baris beli + 1 makloon).

## 4c. RINGKASAN FASE D (detail: `docs/KN_24_PLAN_FASE_D_MAKLOON.md`)

- **Koleksi:** `supplier_contracts` (`sct_`, nomor `<ENT>/SCT-#####`, SCOPED).
  Klaim **TIDAK** punya koleksi sendiri — tersimpan di `makloon_orders.steps[].claim`.
- **Kebijakan** (`system_settings` scope `makloon`): `variance_tolerance_pct` ·
  `default_shrinkage_pct` · `contract_mode (off|warn|block)` · `auto_claim` ·
  `claim_approval_roles` · `require_output_product` · `require_yield_reason`.
- **Tarif (D-07):** basis `pick|kg|meter|yard|ball|cone|roll|lot|lumpsum|custom` +
  `tariff_formula` (safe-eval) + `aux_fees` + `min_charge` + `tariff_qty_source`.
- **Klaim (D-09):** `potong_bon` · `tagih_ganti` · `terima_catatan`; alur
  `open → pending_approval → approved|rejected`.
- **Data demo:** `MKO-00001` selesai · `MKO-00002` diproses · `MKO-00003` rantai 2 langkah
  dengan klaim `potong_bon` menunggu persetujuan.

---

## 5. ATURAN & GOTCHA WAJIB (jangan dilanggar)

1. **JANGAN ubah** `.env` (`MONGO_URL`, `DB_NAME`, `REACT_APP_BACKEND_URL`); jangan rewrite
   `requirements.txt`/`package.json` (pakai `pip install` + `pip freeze` / `yarn add`).
2. **Frontend WAJIB build** setelah edit React (`static_server.js` melayani `build/`). JANGAN `npm`.
3. **Backend** auto-reload (uvicorn --reload). Untuk perubahan `permissions_config.py` /
   seed COA / bootstrap → `supervisorctl restart backend`.
4. **UUID/prefix string** untuk id (bukan ObjectId). Datetime `timezone.utc`. Semua route prefix `/api`.
5. **Gate compliance**: file JSX **<500 baris** (warning mulai 425), router **<800**, utility **<380**.
   Hindari `console.log`.
6. **POC-first**: tiap fase tulis `test_*_poc.py` untuk membuktikan backend sebelum FE, dan
   **bersihkan data** yang dibuat POC agar integrity tetap pristine.
7. **Append-only ledger**: dokumen finansial tidak di-hard-delete; reversal/void via JE.
8. **Setiap selesai fase**: `gate.sh`, update `SESSION_LOG.md`/`plan.md`/`HANDOFF.md`,
   lalu **ask_human approval** sebelum fase berikutnya.
9. **Multi-entity scoping**: `entity_ctx(request)` + `resolve_scope_ids(ctx, entity_id)`
   (contoh bersih: `routers/supplier_contracts.py`). JE selalu pakai `entity_id` riil.
10. **Playwright screenshot**: skrip dijalankan di dalam fungsi async → **WAJIB `await`** pada setiap
    `page.*`. Pakai `wait_until="domcontentloaded"` (**JANGAN** `networkidle` — SPA ini timeout).
    Selector login: `[data-testid="login-email-input"]`, `[data-testid="login-password-input"]`,
    `[data-testid="login-submit-button"]`.
11. **Navigasi = hub-tabs 3 level**: sidebar GRUP (mis. `PEMBELIAN`) → MENU/hub
    (mis. `Pengadaan (Sourcing)`, `Master Pembelian`) → TAB `[data-testid="hub-tab-<view>"]`.
    Untuk role yang home-nya di dalam sebuah grup, grup itu **default expanded** —
    JANGAN klik toggle untuk "expand" (justru collapse).
12. **JANGAN edit paralel** (`search_replace` bersamaan) di **satu file yang sama** — saling menimpa.
13. Bila frontend FATAL karena port 3000 ditahan proses orphan:
    `ss -ltnp | grep :3000` → `kill -9 <pid>` → `supervisorctl restart frontend`.

---

## 6. PERINTAH PENTING

```bash
supervisorctl status
tail -n 50 /var/log/supervisor/backend.*.log /var/log/supervisor/frontend.*.log

python /app/scripts/verify_data_integrity.py     # target 179 / 0 / 0
python /app/scripts/validate_compliance.py       # 0 FAIL (19 WARN tech-debt lama)
python /app/scripts/check_nav_map.py
bash   /app/scripts/gate.sh                      # semua HIJAU → memory/GATE_RECEIPT.md

python /app/backend/test_fase_d_makloon_poc.py   # POC Fase D (self-cleanup) → 69/0
python /app/backend/test_fase_e_contracts_poc.py # POC Fase E (self-cleanup) → 69/0
python /app/backend/test_fase_f1_receiving_uom_poc.py  # POC Fase F-1 (self-cleanup) → 47/0
python /app/seed_realistic.py                    # re-seed data realistis
cd /app/frontend && GENERATE_SOURCEMAP=false yarn build
```

> Preview URL sesi ini: https://kn-fase-e-sourcing.preview.emergentagent.com

---

# SESI 2026-07-27 — FASE G-4 & G-2 DITUTUP

**Repo dipulihkan** dari `github.com/jamananabamaba/kn` (commit `7fd5c86`) ke `/app`
(deps, seed, rebuild FE). MongoDB kontainer KOSONG saat mulai → `seed_realistic.py` wajib
dijalankan (tidak ada data lama yang bisa dipertahankan).

## FASE G-4 — Relasi Dokumen, Referensi & Tanda Tangan ✅
POC `backend/test_g4_refs_poc.py` **49/0** · `audit_doc_refs --strict` HIJAU ·
INV-REF-01..03 · UI **Pusat Dokumen → Jejak Dokumen** + panel **Referensi Dokumen**
(SO/PO/Tagihan Supplier/GRN/Kwitansi) + deep-link QR `/jejak-dokumen/{type}/{id}`.
Dokumen: `docs/KN_28_PLAN_FASE_G4_RELASI_DOKUMEN.md`.
Bug nyata yang diperbaiki: blok TTD cetak tanpa jabatan/waktu · QR kosong saat render
non-browser (resolver baru `services/app_url.py`) · amandemen/nota menulis refs manual ·
tugas pengambilan lahir tanpa menaut SO · residu POC G-1.

## FASE G-2 — Rencana Pembayaran Fleksibel & Denda ✅
POC `backend/test_g2_payment_poc.py` **53/0** · INV-PAY-01/02 · INV-PEN-01/02/03 ·
koleksi `payment_plans` (`<ENT>/RPB-#####`) & `penalties` (`<ENT>/DN-DENDA-#####`) ·
akun GL `1-1270` / `4-9300` · job `penalty_accrual` (07:45 WIB) · 11 kunci konfigurasi
di grup **Uang Masuk & Piutang** · UI **Keuangan → Rencana Bayar & Denda** +
**PaymentPlanBuilder** + **PenaltyPanel** + panel jadwal di detail SO.
Dokumen: `docs/KN_29_PLAN_FASE_G2_PEMBAYARAN_DENDA.md`.

## Status gate
`bash scripts/gate.sh --full` **HIJAU** (24 gate, termasuk POC G-0/G-1/G-2/G-4/F-1/D) ·
`verify_data_integrity` **201 PASS / 0 FAIL / 0 WARN**.

## Catatan untuk agen berikutnya
* Frontend TANPA hot reload → `bash scripts/rebuild_frontend.sh` setelah ubah `frontend/src`.
  `frontend/build/` bisa hilang setelah pod restart → build ulang sebelum uji UI.
* `seed_realistic.py` menghapus `journal_entries` di awal; seed contoh yang berjurnal
  (mis. `seed_payment_plans`) WAJIB membentuk ulang dokumennya agar INV-PEN-03 tetap hijau.
* Fase berikut sesuai `plan.md` §G-11: **G-3 Selisih Pembayaran** → G-8 → G-9 → G-7 → G-6 → G-5.
