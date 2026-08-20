# ENGINEERING GUARDRAILS — Kain Nusantara (KN3)

> **Status:** WAJIB (mandatory) untuk SEMUA development KN3.
> **Asal:** Diadaptasi & dikembangkan dari kerangka guardrails `torado60`
> (case-study intent-drift) + fondasi `KN_00–KN_13`, lalu **divalidasi ulang
> terhadap kontrak NYATA codebase KN3** (bukan diasumsikan).
> **Prinsip inti:** *Dokumentasi bukan penegakan. Prosa membusuk. Guardrail yang
> benar = **kode yang bisa GAGAL (exit ≠ 0)** dan dijalankan otomatis.*

---

---

## 📖 PROTOKOL BACA DOKUMEN — BERJENJANG (hemat context window)

> **JANGAN baca semua ~18 dokumen tiap sesi** — boros & tidak efektif.
> Dokumen = referensi on-demand. **Kebenaran = GATES (kode yang bisa GAGAL), bukan prosa.**

**TIER 0 — WAJIB tiap sesi (ringkas, ~5 sumber):**
1. `bash scripts/load_context.sh` → snapshot service/env/DB/file-size/compliance + handoff terakhir.
2. `ENGINEERING_GUARDRAILS.md` (file ini) — kontrak backend + RC + DoD.
3. `FRONTEND_GUARDRAILS.md` — kontrak frontend.
4. `CODEBASE_MAP.md` — peta file & endpoint (cari, jangan baca utuh).
5. `plan.md` bagian **fase yang sedang berjalan** saja (bukan seluruh histori).

**TIER 1 — SESUAI TUGAS (baca section yang relevan saja):**
- `ENTITY_REGISTRY.md` → HANYA entri koleksi yang akan disentuh (SSOT skema/invarian).
- File kode terkait (router/service/komponen) via grep, bukan baca semua.

**TIER 2 — JARANG (hanya saat mendesain domain itu):**
- `KN_14..KN_17` (IA/inventory/flow/CRM), assessment, deck.
- ⚠️ Standar aspiratif `KN_02–KN_07, KN_09–KN_11` sudah **DIHAPUS** (mereka TARGET, bukan kontrak berjalan). Sebagian `PRD` juga aspiratif
  (envelope `{success,data}`, `/api/v1`, JWT/bcrypt, Redis/Zustand/ECharts → TIDAK dipakai).
  Bila konflik → **kode menang**; jangan ikuti dokumen aspiratif.

**ANDALKAN GATES sebagai verifikasi (bukan baca ulang prosa):**
`verify_contract.py · verify_api_contract.py · verify_data_integrity.py · validate_compliance.py ·
ux_audit.py · check_nav_map.py · audit_endpoint_sweep.py` + `esbuild` untuk FE.

> Rekomendasi instruksi ke agent: ganti "baca semua dokumen" → **"jalankan load_context.sh, baca Tier-0,
> lalu Tier-1 sesuai tugas"**. Hemat token, tetap patuh guardrails.

---


## 0. CARA PAKAI (TL;DR)

Sebelum menyatakan task apa pun "selesai", jalankan **GATE** ini dari `/app`:

```bash
bash scripts/seed_reset.sh        # seed BERSIH + [GATE] contract + data-integrity
python scripts/health_check.py    # sweep endpoint kritis (cek ISI, bukan 200)
python scripts/audit_endpoint_sweep.py   # sweep SEMUA GET /api (cari 5xx)
python scripts/ux_audit.py        # baseline UX (loading/empty/chart/uang)
```

Semua gate hijau → boleh `finish`. Ada FAIL → **perbaiki dulu** (atau catat
eksplisit sebagai keputusan owner — jangan dipalsukan jadi "hijau").

---

## 1. RANTAI DESYNC (akar semua bug data)

Bug data KN3 hampir selalu lahir dari **ketidakcocokan antar-lapisan**:

```
SEED ─tulis→ KOLEKSI MONGO ←baca─ SERVICE ← ROUTER ─JSON→ FRONTEND
  nama koleksi    nama field      signature   /api prefix   import & parsing
```

Satu lapis "geser" (drift), seluruh rantai patah **tanpa error yang jelas** —
endpoint tetap `200`, tetapi tabel kosong / angka salah / dokumen 500.

---

## 2. TAKSONOMI ROOT CAUSE (RC-1 → RC-15)

Setiap bug WAJIB dipetakan ke salah satu RC. Bila tidak ada yang cocok →
tambahkan RC baru di file ini.

| RC | Nama | Contoh KN3 | Gate penangkap |
|----|------|-----------|----------------|
| **RC-1** | Collection name drift | seed tulis `stock`, app baca `inventory_balances` | `verify_contract.py`, `verify_data_integrity.py` (L1) |
| **RC-2** | Field/schema drift | **NYATA(15 Jun): seed pakai `qty`, app+UI pakai `quantity`** → OrdersView blank | `verify_data_integrity.py` (L4 subtotal==price×qty) |
| **RC-3** | Response shape drift | FE harap array, BE bungkus `{items,total}`. **KN3 = ARRAY langsung, TANPA envelope** | `health_check.py`, `audit_endpoint_sweep.py` |
| **RC-4** | Import JSX hilang | komponen dipakai tanpa di-import → layar putih | lint / runtime |
| **RC-5** | Number-series desync | seed insert `SO-0001` tanpa menaikkan counter → duplicate id | `verify_data_integrity.py` (extend) |
| **RC-6** | Linkage/snapshot putus | **NYATA(15 Jun): allocation seed tanpa `warehouse_city`** → render 500 | `audit_endpoint_sweep.py` (5xx) |
| **RC-7** | Bug semantik | hitung "active orders" dari 20 order terakhir saja (lihat dashboard) | invarian lintas-endpoint (L3) |
| **RC-8** | Hardcoded value | periode/tanggal literal → data "bulan ini" kosong | review + L3 |
| **RC-9** | RBAC dua sumber | peta izin FE ≠ `permissions_config.py` BE | manual + test |
| **RC-10** | **False-positive testing** | "status 200"/"service running" dianggap selesai | **ATURAN**: cek ISI & invarian, bukan status |
| **RC-11** | Service contract drift | ubah signature service tanpa update caller → TypeError | `find_dead_services.py` + test |
| **RC-12** | React StrictMode double-fetch | `body stream already read` → pakai async IIFE + `cache:'no-store'` | runtime |
| **RC-13** | Guard status/izin | dispatch order belum approved → 400 (controlled, bukan bug) | sweep (4xx = review) |
| **RC-14** | AppShell blank page | error di shell, bukan modul | runtime |
| **RC-15** | **Protokol eskalasi bug** | lihat §6 | proses |

> **Catatan temuan nyata** yang diperbaiki saat membangun gate ini (bukti gate
> bekerja): **RC-2** (`qty`→`quantity` di `seed_realistic.py`) dan **RC-6**
> (`render_order_html` 500 karena `warehouse_city`/akses key langsung).
> Render dokumen kini **defensif** (`.get()` + fallback) — dokumen tidak boleh
> pernah 500 karena field display opsional.

---

## 3. KONTRAK KANONIK KN3 (Single Source of Truth ringkas)

> Ini hasil VERIFIKASI langsung ke kode, bukan asumsi. SSOT detail =
> `ENTITY_REGISTRY.md`. Bila berbeda, **kode menang** → perbaiki dokumen.

**Auth**
- `POST /api/auth/login {email, password}` → **`{"token": "...", "user": {...}, "onboarding": ...}`**
- Field token = **`token`** (BUKAN `access_token`); respons **langsung** (tanpa envelope).
- Header: `Authorization: Bearer <token>` (token berprefiks `sess_`). Hash = **SHA256** (bukan bcrypt/JWT — PRD lama keliru).

**Bentuk respons**
- List endpoint → **ARRAY langsung** (`[...]`). Detail/dashboard → **objek langsung**.
- TIDAK ada envelope `{items,total}`. Jangan tambahkan tanpa update SEMUA caller FE.

**22 Koleksi kanonik** (jangan buat duplikat — lihat daftar TERLARANG di `verify_contract.py`):
`users, sessions, products, customers, warehouses, uoms, sales_orders, invoices,
inventory_balances, inventory_movements, wms_tasks, warehouse_transfers,
cycle_count_sessions, purchase_orders, document_templates, generated_documents,
permission_settings, audit_logs, user_onboarding, discovery_sessions,
discovery_answers, discovery_attachments`

**Invarian data wajib** (di-enforce `verify_data_integrity.py`):
- Stok: `on_hand_qty == available + reserved + blocked + picked + in_transit` (per balance); tidak ada bucket negatif.
- Order: `total_amount == Σ items.subtotal`; `subtotal == price × quantity`.
- Intent: `dashboard.metrics.products == len(/products)`; `available_qty KPI == Σ /inventory/balances`; `sales-orders stats == len(/sales-orders)`.

**Field penting (verified):** sales order item = `quantity` (BUKAN `qty`);
transfer item = `qty` (domain berbeda — benar). Allocation = `quantity` +
`warehouse_name` + `warehouse_city` (snapshot).

---

## 4. CHECKLIST 3-GATE

### Gate A — PRE-CODE (sebelum menulis kode)
- [ ] Konsep/koleksi sudah ada? Cek `ENTITY_REGISTRY.md` + `verify_contract.py --list-canonical`. **Jangan buat koleksi/endpoint duplikat.**
- [ ] Bentuk respons mengikuti kontrak KN3 (array langsung, field `token`, dst).
- [ ] Bila integrasi pihak ke-3 → minta playbook + simpan kredensial di `.env`.

### Gate B — DURING-CODE
- [ ] Setiap akses Mongo pakai nama kanonik (`db.inventory_balances`, bukan `db.stock`).
- [ ] Render/serialisasi **defensif** (`.get()` untuk field display opsional; `safe_doc()` untuk ObjectId/datetime).
- [ ] FE: setiap tabel punya **loading + empty state**; angka uang/qty pakai `tabular-nums`; elemen interaktif punya `data-testid`.
- [ ] Endpoint `/api`-prefixed; pakai `import.meta.env.REACT_APP_BACKEND_URL` di FE.
- [ ] Seed mengikuti kontrak API — **bukan sebaliknya**.

### Gate C — POST-CODE (sebelum "selesai")
- [ ] `bash scripts/seed_reset.sh` → **hijau** (contract + integrity di seed bersih).
- [ ] `python scripts/health_check.py` → 0 FAIL.
- [ ] `python scripts/audit_endpoint_sweep.py` → **0 entri 5xx**.
- [ ] `python scripts/ux_audit.py` → file BARU/disentuh tidak menambah ERROR.
- [ ] `python scripts/validate_compliance.py` (file-size & naming) tidak menambah pelanggaran baru.
- [ ] Diuji lewat `testing_agent_v3` untuk perubahan signifikan.

---

## 5. DEFINITION OF DONE

Sebuah perubahan **DONE** hanya jika SEMUA benar:
1. Gate A–C hijau (atau FAIL didokumentasikan sebagai keputusan owner eksplisit).
2. Tidak ada 5xx baru pada sweep endpoint.
3. Invarian data tetap valid pada **seed bersih**.
4. Frontend mencerminkan 100% fitur backend (tidak ada endpoint "yatim").
5. Tidak ada koleksi/field/endpoint duplikat (no drift).
6. Bila ada yang belum beres → **dilaporkan jujur** ("BELUM SELESAI" + bukti),
   bukan diklaim hijau.

---

## 6. RC-15 — PROTOKOL ESKALASI BUG PERSISTEN

Bila sebuah bug tidak selesai, naik tangga ini (jangan menebak berulang):

1. **Self-debug** maksimal **2×** (baca log, reproduksi minimal).
2. **`troubleshoot_agent`** untuk RCA independen (read-only).
3. **`testing_agent_v3`** untuk reproduksi terstruktur (skip drag-drop/voice/kamera).
4. **`web_search`** bila dugaan versi/dokumen/SDK.
5. **`integration_playbook_expert_v2`** bila menyangkut integrasi.
6. Bila tetap buntu → **lapor jujur** ke user dengan bukti + opsi (rollback / model lebih kuat). **DILARANG** mengklaim selesai tanpa bukti.

**Anti-RC-10 (false positive):** "HTTP 200", "service running", "tidak ada error
di log" **BUKAN** bukti benar. Bukti = **nilai data benar** + **invarian
lintas-endpoint terpenuhi** + **UI menampilkan data**.

---

## 7. KAPAN MENAMBAH GATE BARU

Tambah fitur/koleksi ⇒ **wajib**:
- Tambah koleksi ke `CANONICAL_COLLECTIONS` (`verify_contract.py`) **dan** `ENTITY_REGISTRY.md`.
- Tambah `Concept(...)` + invarian relevan ke `verify_data_integrity.py`.
- Tambah endpoint kritis ke `CRITICAL_ENDPOINTS` (`health_check.py`).
- Update dokumen ini bila muncul kelas bug baru (RC baru).

> Guardrail yang tidak tumbuh bersama kode akan **membusuk** dan menutupi drift.
> Itulah pelajaran utama case-study yang melahirkan kerangka ini.

---

## 8. BLINDSPOT LOG — Audit guardrail terhadap dirinya sendiri (Round 2)

> Meniru metode case-study torado60 (B1–B8): kami **mengaudit gate v1** dan
> menemukan kelas bug yang MASIH lolos. Setiap celah (G) kini ditutup gate baru
> dan dibuktikan bisa GAGAL. Ini bukti bahwa "verify-don't-assume" berlaku juga
> untuk guardrail itu sendiri.

| Gap | Apa yang lolos di v1 | Bukti nyata di KN3 | Penutup (gate) |
|-----|----------------------|--------------------|----------------|
| **G1** | Drift FIELD **non-numerik** (label kosong, bukan error) | `OrdersView` baca `shipping_city`/`sales_name`/`reservation_expires_at`/`item.id` yang BE tak produksi | `verify_api_contract.py` Check C |
| **G2** | **Duplicate route** (FastAPI pakai definisi terakhir) | `GET /sales-orders` ganda → filter `status`/`customer_id` MATI | `verify_api_contract.py` Check A |
| **G2b** | FE panggil endpoint **hantu** (typo path → 404 senyap) | — (kini terjaga) | `verify_api_contract.py` Check B |
| **G4** | Daftar kanonik gate **drift dari** ENTITY_REGISTRY (B2) | `discovery_attachments` ada di gate, tak ada di SSOT | `verify_data_integrity.py` L0 |
| **G5** | **WARN-swallow** → exception ditelan jadi hijau palsu (B7) | invarian API dulu `except→WARN` | L3 exception kini **FAIL** |
| **G7** | **Direct-key-access** tersebar → 500 saat field hilang (RC-6) | barcode label `task['roll_id']`, render order `a['warehouse_city']` | render defensif `.get()` + sweep 5xx |
| **G8** | **Number-series** count-based → duplikat/RC-5 | `SO-{count+1}` rentan; format seed `SO-0001` vs live `SO-00009` | `verify_data_integrity.py` L5 |
| **G9** | Semantik KPI **window** (RC-7) | dashboard `active_orders` dihitung dari 20 order terakhir saja | dashboard fix + L3 INV-5 |

**Pelajaran tambahan (gate harus dipercaya):** gate yang **false-positive** akan
diabaikan. Saat membangun `verify_api_contract.py`, ia sempat salah-alarm karena
(a) `${API}` punya DUA makna berbeda antar file (`apiClient.js` = `.../api` vs
file fitur = `REACT_APP_BACKEND_URL`), (b) `fetch()` menaruh method di arg-opsi,
(c) query-string `${params}`. Ketiganya diperbaiki agar gate **akurat** — karena
gate berisik sama buruknya dengan tidak ada gate.

### Daftar gate (final)
```bash
bash scripts/seed_reset.sh             # seed bersih + [GATE] contract + api_contract + integrity
python scripts/verify_contract.py --all      # RC-1 nama koleksi (db.x & db["x"])
python scripts/verify_api_contract.py        # G1/G2/G2b FE↔BE (duplicate route, field, endpoint)
python scripts/verify_data_integrity.py      # L0 self-check, L1/L2 drift, L4 invarian, L5 number, L3 intent
python scripts/health_check.py               # isi endpoint kritis
python scripts/audit_endpoint_sweep.py       # semua GET /api → 5xx
python scripts/ux_audit.py                   # baseline UX
```

> **Aturan tetap:** tambah field FE baru ⇒ tambah ke `BINDINGS` (verify_api_contract).
> Tambah koleksi ⇒ update `CANONICAL_COLLECTIONS` **dan** ENTITY_REGISTRY (L0 menjaga).
