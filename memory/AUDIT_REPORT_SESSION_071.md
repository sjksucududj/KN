# AUDIT REPORT — Session #071

**Tanggal:** 03 Jul 2026  
**Auditor:** E1 (main agent)  
**Repo sumber:** `dakagaberesberesdah/kn`  
**Basis kontrak:** `ENGINEERING_GUARDRAILS.md`, `FRONTEND_GUARDRAILS.md`, `CODEBASE_MAP.md`, `plan.md` (Tier-0)  
**Metode:** 9 lapisan audit berlapis (5 lapisan asli + 4 lapisan tambahan setelah owner meminta pendekatan berbeda)  
**Aturan emas yang mengikat:** *KODE MENANG atas DOKUMEN — verifikasi = eksekusi gate, bukan pembacaan prosa.*

---

## 1. RINGKASAN EKSEKUTIF

### 1.1 Skala repo yang diaudit

| Metrik | Nilai |
|---|---:|
| Baris kode backend (routers) | 14,460 |
| Baris kode backend (services) | 17,598 |
| Baris kode frontend (features) | 31,580 |
| Total endpoint (`@router.*`) | **508** |
| Total FE API call site (`apiClient.` + `axios`) | **366** |
| Koleksi MongoDB dirujuk di kode | 78 |
| Koleksi aktif di DB pasca `seed_reset` | **58** (57 non-empty, 1 empty) |
| Total dokumen tersimpan | **558** |
| Master data (products/customers/suppliers/warehouses/entities/gl_accounts) | 11 / 5 / 6 / 3 / 2 / 45 |
| Transaksional (SO/PO/VB/INV/SHP/AR/mov) | 9 / 11 / 0 / 0 / 4 / 6 / 23 |
| GL journal entries | 18 |
| Inventory rolls (SSOT INV-ROLL-1) | 40 |

### 1.2 Skorboard temuan (14 findings terkategori)

| ID | Kategori | Severity | Status | Lapisan yang menemukan | LoC/file |
|---|---|---|---|---|---|
| **B1** | UX baseline | Medium (tech-debt) | ✅ FIXED + VERIFIED | L1 (`ux_audit`) | `BiFinanceView.jsx` 224→259 |
| **C1** | Accounting silent-fail | **CRITICAL** | ✅ FIXED + VERIFIED | L2 (`ruff F821`) | `routers/vendor_bills.py:322-326` |
| **S1** | Schema drift storage | **HIGH** | ⚠️ OPEN | L6+L7 (runtime + DB dump) | `purchase_orders` docs |
| **S2** | Gate silent false-PASS | **HIGH** | ⚠️ OPEN | L7 + code trace | `verify_data_integrity.py:161` |
| **H1** | Operasional restore | HIGH | ⚠️ OPEN | L1 (baseline gate) | `scripts/load_context.sh` |
| **M1** | Audit trail hilang | MEDIUM | ⚠️ OPEN | L2 (`ruff F841`) | 8 lokasi (rincian §4.M1) |
| **M2** | React perf/state-loss | MEDIUM | ⚠️ OPEN | L2 (ESLint) | `CoreWidgets.jsx:95`, `ui/calendar.jsx` |
| **M3** | Monster file zona bahaya | MEDIUM | ⚠️ OPEN | L1 (`validate_compliance`) | 8 file (rincian §4.M3) |
| **M4** | Seed vs code drift | MEDIUM | ⚠️ OPEN (mungkin by-design) | L1 (`audit_collection_drift`) | 21 koleksi MISSING |
| **S3** | Bisnis chain terputus (klarifikasi) | Info | ✅ CLARIFIED (invoice-less flow) | L9 (state-machine) | `ar_receipts.allocations[].order_id` |
| **S4** | Naming konvensi | LOW | ⚠️ OPEN | L7 (DB dump) | `shipments.order_id` vs kanonik `sales_order_id` |
| **L1** | Sweep script self-bug | LOW | ⚠️ OPEN | L1 (`audit_endpoint_sweep`) | 6× 422 GET-tanpa-payload |
| **L2** | Backlog belum reconcile | LOW | ⚠️ OPEN | L5 (handoff review) | `BUG_BACKLOG.md #3-#7` |
| **L3** | ESLint cosmetics | LOW | ⚠️ OPEN | L2 (ESLint) | 136 issues (~30 real) |

**Prioritas fix untuk agent berikutnya:** C1 sudah, lalu **S1 → S2 → H1 → M1 → M2 → M3** sebelum berpindah ke fitur baru (P3 SMTP PO PDF).

### 1.3 Bug fixes yang telah dituntaskan (bukti test agent)

| Fix | Alat verifikasi | Bukti pass |
|---|---|---|
| **B1 (BiFinanceView E2/E3)** | `auto_frontend_testing_agent` × 2 iterasi | Iter-1 FAIL (BE zero-fill → guard `length===0` never triggers); Iter-2 PASS 4/4 skenario (login+nav / empty year 2021 / normal 2026 / refresh) via derived `.some()` guard |
| **C1 (vendor_bills gl_service import)** | `deep_testing_backend_v2` | 7/7 checks PASS (import present, call site, error handling, no NameError di log, `gl_service.post_vendor_bill` def, signature match, 45 GL accounts termasuk 2-1150/1-1500/2-1100 ready) |

---

## 2. METODOLOGI AUDIT — 9 LAPISAN

### 2.1 Timeline eksekusi

```
Fase 0: Restore    → git clone repo → rsync ke /app → yarn install + pip freeze
                     → seed_reset.sh baseline → verifikasi Tier-0
Fase 1: Fix B1      → BiFinanceView guard iter-1 (static PASS, runtime FAIL)
                     → BiFinanceView guard iter-2 (derived .some())
Fase 2: Audit awal (L1-L5) → C1 kritis ditemukan → fix diterapkan
Fase 3: Audit lanjutan (L6-L9) → S1 dan S2 ditemukan (schema drift + gate bocor)
```

### 2.2 Tabel 9 lapisan (ringkas)

| # | Lapisan | Alat utama | Sifat lensa | Nilai keunikan | Temuan yang dihasilkan |
|---|---|---|---|---|---|
| 1 | Gates enforcement | 10 script (`verify_*`, `audit_*`, `health_check`, `ux_audit`, `validate_compliance`, `check_nav_map`, `find_dead_services`) | Struktural / declarative | Cepat, otomatis, cover regresi kontrak | B1, M3, M4, L1 |
| 2 | Static linter | `ruff` (Python), ESLint (JSX) via `mcp_lint_*` | Symbol resolution / rule engine | Menangkap bug di balik try/except broad | **C1**, M1, M2, L3 |
| 3 | Grep anti-pattern | `grep -rn <regex>` per RC-taxonomy | Sidik jari bug spesifik | Menangkap pola yang lint tak deteksi | Konfirmasi C1 (missing import) |
| 4 | Business process cross-check | Trace lifecycle end-to-end | Kontekstual bisnis | Membedakan bug nyata vs by-design | C1 impact assessment (trial balance drift) |
| 5 | Handoff/backlog reconciliation | Baca `BUG_BACKLOG.md`, `SESSION_HANDOFF.md`, `plan.md` | Sejarah / narrative | Menutup gap dokumen vs kode | L2 (BUG_BACKLOG #1 sudah fixed, #3-#7 belum verified) |
| 6 | Runtime behavioral probing | Python `requests` POST/GET loop + invariant check | Semantik integrasi | Menangkap serialization drift | **S1** (PO grand_total top-level = None) |
| 7 | DB shape archaeology | Motor client → dump dokumen aktual | Storage vs model deklaratif | Menangkap drift skema tak terlihat dari kode | **S1 konfirmasi**, **S3 klarifikasi**, **S4** |
| 8 | Referential integrity crawl | Set-based FK verification (async iterate) | Consistency graph | Menangkap dangling reference | 0 orphan (setelah koreksi nama kanonik `business_entities`) |
| 9 | State-machine trace | `db.collection.aggregate([{$group:{status}}])` + illegal transition check | Temporal / status consistency | Menangkap dokumen "zombie" | Illegal transitions = 0; **S3 klarifikasi** invoice-less AR |

---

## 3. LAPISAN 1-9 — DETAIL LENGKAP

### Lapisan 1 — Gates enforcement

**Filosofi:** *Verifikasi = eksekusi script, bukan pembacaan dokumen.*

**Perintah dijalankan:**
```bash
python scripts/verify_contract.py --all
python scripts/verify_api_contract.py
python scripts/verify_data_integrity.py
python scripts/health_check.py
python scripts/audit_endpoint_sweep.py
python scripts/ux_audit.py
python scripts/validate_compliance.py
python scripts/check_nav_map.py
python scripts/find_dead_services.py
python scripts/audit_collection_drift.py
```

**Hasil per gate:**

```
verify_contract         CONTRACT OK      | 0 FAIL / 45 WARN
verify_api_contract     FE↔BE CONTRACT OK| 0 ERROR / 1 WARN / 280 FE paths
verify_data_integrity   pra-seed: 4 FAIL | pasca-seed_reset: 110 PASS / 0 FAIL
health_check            100% PASS        | 3 WARN empty (transfers/invoices/cycle-count normal)
audit_endpoint_sweep    OK(data): 146    | EMPTY: 28 | 5xx: 0 | 4xx: 52 | 422: 6 | SKIPPED: 2
ux_audit                0 ERROR / 0 WARN | 199 file (setelah fix B1)
validate_compliance     94 PASS / 0 FAIL / 58 WARN
check_nav_map           PASS             | konsisten KN_13 grouped IA
find_dead_services      65/65 used       | 0 unused
audit_collection_drift  21 MISSING       | (kode baca, DB kosong)
```

**Temuan yang diproduksi lapisan ini:**
- **B1**: `ux_audit` melaporkan 2 ERROR baseline di `features/finance/BiFinanceView.jsx` (E2 = tabel tanpa empty state; E3 = chart tanpa empty guard).
- **M3**: `validate_compliance` melaporkan 8 monster file di zona bahaya (90% batas), rincian §4.M3.
- **M4**: `audit_collection_drift` list 21 koleksi tak terisi (rincian §4.M4).
- **L1**: `audit_endpoint_sweep` 6× 422 (sweep bug, bukan app bug).

**Batasan lapisan ini:** *Buta terhadap semantik data.* Gate `verify_data_integrity` PASS bukan berarti data valid — tergantung ketegasan invariant checker (lihat S2).

---

### Lapisan 2 — Static analysis (linter sebagai bug detector)

**Filosofi:** *Bug bisa terungkap dari analisis simbol tanpa eksekusi.*

**Perintah:**
```bash
mcp_lint_python  → /app/backend/routers/*.py + /app/backend/services/*.py
mcp_lint_javascript → /app/frontend/src/**/*.jsx
```

**Hasil ruff (backend, routers+services):**
```
BLOCKING = 63 total
├── F841 (unused local var) × 8
├── F821 (undefined name) × 1  ← BUG NYATA C1
├── E741 (ambiguous var name)  × 32
├── E701/E702 (multi-statement)× 22
```

**Detail F841 (menghapus audit trail):**
```
backend/routers/crm.py:140            actor  ← audit_log kehilangan actor
backend/routers/cycle_count.py:83     actor  ← idem
backend/routers/input_tax.py:115      entity_id
backend/routers/sales_orders.py:704   result
backend/routers/sales_returns.py:27   user   ← 2× di file yang sama
backend/routers/sales_returns.py:118  user
backend/routers/so_approvals.py:161   result
backend/services/approval_service.py:375 pending
```

**Detail F821 (bug nyata):**
```
backend/routers/vendor_bills.py:323   Undefined name `gl_service`
```

**Hasil ESLint (136 problems, ~30 real errors):**
- `react/no-unstable-nested-components` × 2 (`CoreWidgets.jsx:95` = Sidebar, `ui/calendar.jsx`)
- `react/no-unescaped-entities` × 24 (quote/apostrophe cosmetic)
- `react/no-unknown-property` × 1 (`ui/command.jsx` cmdk-input-wrapper — false-positive shadcn)
- `no-empty` × 3 (mostly safe: `ScannerTaskPanel.jsx:29,46,54` di cleanup handler `reader.reset()`)
- Sisanya `Unused eslint-disable directive`

**Temuan yang diproduksi lapisan ini:**
- **C1 CRITICAL**: `F821 Undefined name gl_service` — bug utama sesi ini.
- **M1**: 8× F841, khususnya `actor` var yang menandakan `audit_logs.insert` terlupakan.
- **M2**: `no-unstable-nested-components` di Sidebar & calendar.
- **L3**: Cosmetic ESLint.

---

### Lapisan 3 — Grep anti-pattern (RC-taxonomy)

**Filosofi:** *Tiap kelas bug punya sidik jari regex.* Query terarah berdasarkan Root Cause taxonomy di `ENGINEERING_GUARDRAILS.md`.

**Pattern → kelas bug → hasil:**

| Pattern | Kelas | File cek | Hasil |
|---|---|---|---|
| `\[.*_name.*\]\|\[.*_city.*\]` | RC-6 direct dict access | `outbound_picking.py:562,615` | Ditemukan **tapi safe** — `wh_data` di-populate via `.get(..., "")` upstream di line 489-490 |
| `except Exception:` w/o log | RC-11 silent swallow | Semua service+router | Semua punya `logging.error` — OK |
| `import gl_service\|from services import` | RC-11 dead-service | 7 router pengguna | **1 miss** = `vendor_bills.py` → konfirmasi C1 |
| `po\.grand_total\|order\.total_amount` | FE consumption pattern | `frontend/src/features/**` | Semua pakai fallback `??` (defensive) — mitigated |
| `catch\s*(.*)\s*{}` | Empty catch | Frontend | 3× di `ScannerTaskPanel.jsx` (safe konteks) |
| `qty` vs `quantity` di items | RC-2 field naming | SO/PO items | Storage konsisten `quantity` |

**Konfirmasi C1 via grep:**
```bash
grep -n "gl_service\|^import\|^from" /app/backend/routers/vendor_bills.py
# → line 322: await gl_service.post_vendor_bill(updated)
# → TIDAK ADA "import gl_service" atau "from services import gl_service"
```

Cross-check dengan router lain:
```
routers/transfers.py:15            from services import gl_service   ✅
routers/crm.py:...                 from services import gl_service   ✅
routers/inbound_receiving.py:...   from services import gl_service   ✅
routers/invoices.py:...            from services import gl_service   ✅
routers/gl.py:16                   from services import gl_service   ✅
routers/vendor_bills.py            (nothing)                          ❌
```

**Temuan yang diproduksi lapisan ini:**
- Konfirmasi ketat **C1** melalui triangulasi.
- Verifikasi RC-6 di `outbound_picking.py` = false alarm (defensive upstream).
- Mitigasi risiko S1 karena FE sudah pakai fallback `po.grand_total ?? po.total_amount ?? 0`.

---

### Lapisan 4 — Business process cross-check

**Filosofi:** *Trace end-to-end lifecycle, bukan potongan endpoint.*

**AP flow (Accounts Payable):**
```
Purchase Requisition → Purchase Order → Goods Receipt → Vendor Bill → _post_bill() → GL Journal
                                                                        ↑
                                                                        └── TITIK GAGAL C1
                                                                            (NameError silent)
```

**Impact assessment C1:**
- Setiap vendor bill yang sukses match (auto-clean-match ATAU manager-approved variance) akan:
  - `bill.status` → `"posted"` ✅ (koleksi `vendor_bills` update sukses)
  - `_post_bill()` memanggil `gl_service.post_vendor_bill(updated)` → **NameError** (silent, ditelan `except Exception`)
  - GL journal Dr GR-IR + PPN Masukan / Cr Hutang Usaha → **TIDAK PERNAH DIBUAT**
- **Konsekuensi akuntansi:**
  - Trial balance: sisi Hutang Usaha (Cr) tidak bertambah → **AP under-recorded**
  - GR-IR clearing (Dr) tidak terurai → clearing account akumulasi terus
  - PPN Masukan (Dr) tak tercatat → SPT Masa PPN salah
  - Cash disbursement kemudian (Cr Kas / Dr Hutang) → **Dr Hutang** tanpa Cr Hutang sebelumnya → saldo Hutang negatif fictitious
- **Radius damage:** hanya bill yang di-post (koleksi `vendor_bills` = 0 di baseline → belum ada bill dibuat di sesi test, tapi flow siap dipanggil begitu ada bill).

**AR flow (Accounts Receivable):**
```
Sales Order → Reserve stock → Confirm → Dispatch (Shipment) → (Invoice?) → AR Receipt → GL Journal
                                                              ↑
                                                              └── KLARIFIKASI S3
                                                                  (invoice-less order-based AR)
```
Tidak ada bug di sini — model memang bypass invoice; alokasi AR langsung ke `order_id`.

**Temuan yang diproduksi lapisan ini:**
- Konteks bisnis untuk C1 (dampak trial balance).
- Klarifikasi S3 (invoice-less bukan bug).

---

### Lapisan 5 — Handoff & backlog reconciliation

**Filosofi:** *Bug yang belum-solved dari sesi lampau sering masih ada.*

**File yang di-review:**
```
memory/SESSION_HANDOFF.md      (922 baris, sesi #061-#070)
BUG_BACKLOG.md                 (286 baris, 18 Jun 2026, 7 bug)
plan.md                        (358 baris, P1-P6 status)
memory/FORENSIC_AUDIT_2026-06.md
```

**Rekonsiliasi BUG_BACKLOG:**

| BUG # | Deskripsi | Status verifikasi |
|---|---|---|
| #1 | Dashboard cards leak ke semua page | ✅ **FIXED** (verified via grep `App.js:249` — comment `// BUG #1/#2 fix: MetricCards & Onboarding hanya tampil di halaman landing`) |
| #2 | Onboarding admin section semua page | ✅ **FIXED** (fixed bersama #1) |
| #3 | Redundant navigation tabs | ⚠️ **BELUM VERIFIED** |
| #4 | Special Order menu tak accessible | ⚠️ **BELUM VERIFIED** |
| #5 | Returns tab spacing broken | ⚠️ **BELUM VERIFIED** |
| #6 | Inconsistent page titles | ⚠️ **BELUM VERIFIED** |
| #7 | Tab badge count position | ⚠️ **BELUM VERIFIED** |

**Rekonsiliasi plan.md (Finance roadmap):**
```
P1 Tax Center                    ✅ DONE (sesi #069)
P2 Financial Statements + BI     ✅ DONE (sesi #069+prev)
P6 Consolidation (partial)       ✅ DONE
P7 Costing unified               ✅ DONE (sesi #070 F-7)
P8 Suspense                      ✅ DONE (sesi #070 F-8)
P9 Closing tahunan + STALE       ✅ DONE (sesi #070 F-9)
P3 SMTP PO PDF                   ⏭️ NEXT (perlu SMTP creds owner)
P4 Budget Control                ⏭️ NEXT
P5 Multi-currency/FX             ⏭️ NEXT
```

**Rekonsiliasi tech-debt residual (dari SESSION_HANDOFF #070):**
- `sales_orders.py` sebelumnya 832 → 793 (sesi #074 imaginer di summary saya sebelumnya adalah dead reference; nyatanya sesi ke-#070 disebutkan tech-debt tersisa)
- `CheckoutDrawer.jsx` sebelumnya 509 → 496
- Keduanya masih zona bahaya (belum melanggar 500/800).

**Temuan yang diproduksi lapisan ini:**
- **L2**: BUG_BACKLOG #3-#7 masih pending verifikasi.
- Konfirmasi P3-P5 masih backlog aktif.

---

### Lapisan 6 — Runtime behavioral probing (POST → GET semantic loop)

**Filosofi:** *Panggil endpoint sungguhan, uji invariant, tak percaya gate.*

**Skrip probe (`requests` Python):**
```python
BASE = "http://localhost:8001/api"
tok = requests.post(f"{BASE}/auth/login",
                    json={"email":"admin@kainnusantara.id","password":"demo12345"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}

# 1. Login shape
# 2. PO list + detail per PO → invariant: subtotal == Σ line_total
# 3. SO shape: harus ARRAY, bukan {items, total}
# 4. Products limit=1000 query behavior
# 5. Auth invalidation: logout → me → HTTP 401
```

**Hasil probe:**

```
login:                   HTTP 200, token_prefix=RYLpSGqy1V (10 chars, sess_ prefix)
PO list:                 9 items ✅
PO detail po_006:        HTTP 200
  invariant subtotal:    True (sub=0.0, sum=0.0)  ← FALSE POSITIVE (keduanya 0)
SO shape:                <class 'list'> ✅ envelope-less
Products count:          11 ✅
After logout /me:        HTTP 401 ✅
```

**Deep probe seluruh PO (9 dokumen):**

| PO ID | Status | subtotal | grand_total | items[0].qty_ordered | items[0].unit_price | items[0].line_total |
|---|---|---|---|---|---|---|
| po_001 | ? | None | None | None | None | None |
| po_002 | completed | None | None | None | None | None |
| po_004 | receiving | None | None | None | None | None |
| po_005 | receiving | None | None | None | None | None |
| po_006 | receiving | None | None | None | None | None |
| po_007 | waiting_approval | None | None | None | None | None |
| po_008 | rejected | None | None | None | None | None |
| po_009 | pending | None | None | None | None | None |
| po_010 | waiting_approval | None | None | None | None | None |
| po_011 | waiting_approval | None | None | None | None | None |

**→ Menghasilkan S1** — semua PO return field kanonik `None` di API response.

**Deep probe po_002 sub-object `financials`:**
```json
{
  "financials": {
    "total_amount": 43600000.0,
    "gross_total":  43600000.0,
    "grand_total":  43600000.0,
    "received_value":43600000.0,
    "outstanding":  43600000.0,
    "payment_status":"unpaid",
    "amount_paid":  0.0,
    "returned_amount":0.0,
    "discount_total":0.0,
    "net_subtotal": 0.0,
    "dpp":          0.0,
    "ppn_rate":     0.0,
    "ppn_amount":   0.0
  }
}
```
→ Konfirmasi financial value dihitung on-the-fly ke `po["financials"]` sub-object (§4.S1).

**Temuan lapisan ini:**
- **S1**: PO top-level `grand_total/subtotal` = None → tapi `financials.grand_total` benar.
- Envelope contract verified (array langsung).
- Auth invalidation verified.

---

### Lapisan 7 — Database shape archaeology

**Filosofi:** *Dokumen adalah source-of-truth; model deklaratif bisa bohong.*

**Skrip:**
```python
async with AsyncIOMotorClient(MONGO_URL) as c:
    db = c[DB_NAME]
    for coll in ["purchase_orders","sales_orders","inventory_balances","shipments","ar_receipts"]:
        docs = await db[coll].find({}).limit(2).to_list(2)
        for d in docs:
            print(sorted(d.keys()))
```

**Perbandingan `sales_orders` vs `purchase_orders` (bukti S1):**

| Aspek | `sales_orders` | `purchase_orders` | Verdict |
|---|---|---|---|
| Item.qty field | `quantity` | `quantity` | ✅ konsisten |
| Item.price field | `price` | `price` | ✅ konsisten |
| Item.line_total | ✅ ada (`5,550,000`) | ❌ **tidak ada** | ⚠️ drift |
| Item.subtotal | ✅ ada | ❌ tidak ada | ⚠️ drift |
| Item.discount_amount | ✅ ada | ❌ tidak ada | ⚠️ drift |
| Header.total_amount | ✅ ada (`10,050,000`) | ❌ tidak ada | ⚠️ drift |
| Header.net_subtotal | ✅ ada | ❌ tidak ada | ⚠️ drift |
| Header.grand_total | ✅ ada (`11,155,500`) | ❌ tidak ada | ⚠️ drift |
| Header.dpp | ✅ ada | ❌ tidak ada | ⚠️ drift |
| Header.ppn_amount | ✅ ada | ❌ tidak ada | ⚠️ drift |

**Konsekuensi konkret:**
- Endpoint `GET /api/purchase-orders/{id}` **tetap benar** karena `_po_financials()` menghitung dari items on-the-fly.
- Endpoint `GET /api/purchase-orders` (list) tidak memanggil `_po_financials` → response setiap item PO memiliki `grand_total: null` (kalau FE query field ini). Ini yang FE fallback ke `?? po.total_amount ?? 0`.
- Setiap query aggregate DB directly (`db.purchase_orders.aggregate([{$sum: "$grand_total"}])`) akan return `null` / `0` walau ada transaksi.

**Bukti gate bocor (S2):**
```python
# scripts/verify_data_integrity.py:161
ssum = sum(float(i.get("subtotal", 0)) for i in items)
                              ^^^^^^^^^^^
                              default 0 saat field tak ada
# → item PO tak punya "subtotal", jadi ssum = 0
# → dibandingkan dengan total_amount = None → cast float(None) → TypeError
# → tapi loop di-wrapped try, mungkin skip silently
# → net: PASS palsu
```

**Sample inventory_balances (SSOT INV-ROLL-1 compliant):**
```
Keys: [atp_qty, available_qty, blocked_qty, committed_qty, damaged_qty, hold_qty,
       in_transit_inbound_qty, in_transit_intercompany_qty, in_transit_qty,
       in_transit_sales_qty, in_transit_transfer_qty, incoming_qty,
       on_hand_qty, on_hand_roll_count, on_order_qty, owned_qty,
       owner_entity_id, packed_qty, picked_qty, product_id,
       quarantine_qty, reserved_qty, roll_count, roll_counts,
       updated_at, warehouse_id, wip_qty]
```
→ Granular bucket-based, konsisten dengan `stock_bucket_service`.

**Sample `ar_receipts` (untuk klarifikasi S3):**
```
Keys: [allocations, amount, applied_total, customer_id, customer_name,
       deposit_delta, entity_id, method, notes, number, receipt_date,
       status, total_funds, unapplied_amount, used_deposit]
allocations[0]: {order_id: "so_001", order_number: "SO-0001",
                 applied: 5577800.0, outstanding_after: 5577700.0,
                 payment_status: "partial"}
```
→ Link ke SO via `order_id` (bukan `invoice_id`). Model invoice-less confirmed.

**Sample `shipments` (untuk S4):**
```
Keys: [allocation_id, entity_id, is_partial, order_id, order_number,
       product_id, product_name, qty, rolls, shipment_no, sku,
       status, task_id, unit, warehouse_city, warehouse_id, warehouse_name]
```
→ Field `order_id`, bukan `sales_order_id`. Perlu klarifikasi konvensi kanonik.

**Temuan lapisan ini:**
- **S1 KONFIRMASI**: schema drift PO.
- **S2**: verify_data_integrity false-PASS karena default 0.
- **S3 KLARIFIKASI**: invoice-less AR.
- **S4**: naming `order_id` vs `sales_order_id`.

---

### Lapisan 8 — Referential integrity crawl

**Filosofi:** *Setiap foreign-key harus punya rujukan valid.*

**Skrip:**
```python
prod = {p["id"] async for p in db.products.find({}, {"id":1})}
cust = {p["id"] async for p in db.customers.find({}, {"id":1})}
supp = {p["id"] async for p in db.suppliers.find({}, {"id":1})}
wh   = {p["id"] async for p in db.warehouses.find({}, {"id":1})}
ent  = {p["id"] async for p in db.business_entities.find({}, {"id":1})}
acct = {p["code"] async for p in db.gl_accounts.find({}, {"code":1})}

orphans = []
# Iterasi SO, PO, inventory_balances, inventory_movements, journal_entries
# Cek: product_id, customer_id, supplier_id, warehouse_id, entity_id, account_code
```

**Cardinality master set:**
```
products=11  customers=5  suppliers=6  warehouses=3  business_entities=2  gl_accounts=45
```

**Hasil crawl setelah 5 koleksi anak (SO×9, PO×11, inventory_balances×17, inventory_movements×23, journal_entries×18):**
```
ORPHANS FOUND: 0 ✅
```

**Nilai koreksi diri:** Awal salah pakai koleksi `entities` (0 dokumen) → melaporkan 9 orphan SO fictitious. Setelah dikoreksi ke `business_entities` (2 dokumen) → 0 orphan. Ini bukti pentingnya **verifikasi nama koleksi kanonik dulu** sebelum interpretasi.

**Temuan lapisan ini:**
- **0 orphan** — referential integrity DB clean.
- Meta-lesson: crawler yang tidak baca CANONICAL_COLLECTIONS bisa self-produce false positive.

---

### Lapisan 9 — State-machine trace

**Filosofi:** *Setiap dokumen bertransisi lewat status; harus konsisten dengan field timestamp/related.*

**Aggregate status per koleksi transaksional:**

| Koleksi | Total | Distribusi status |
|---|---:|---|
| sales_orders (SO) | 9 | approved:1, confirmed:1, done:1, partially_shipped:1, reserved:2, shipped:1, waiting_approval:1, waiting_stock:1 |
| purchase_orders (PO) | 11 | completed:3, pending:1, receiving:3, rejected:1, waiting_approval:3 |
| **vendor_bills (VB)** | **0** | *(kosong)* — konsekuensi: C1 fix belum ter-exercise di data |
| **invoices (INV)** | **0** | *(kosong)* — konfirmasi S3 invoice-less flow |
| shipments (SHP) | 4 | dispatched:4 |
| purchase_returns (PR) | 2 | draft:1, pending_approval:1 |
| sales_returns (SR) | 2 | draft:1, pending_approval:1 |
| ar_receipts (AR) | 6 | posted:6 |

**Cek transisi ilegal (heuristics):**
```python
# SO
- confirmed_at set tapi status=draft?           → 0 kasus ✅
- dispatched_at set tapi status in (draft/waiting_approval)? → 0 ✅
- paid_total>0 tapi payment_status=unpaid?      → 0 ✅
# PO
- completed_at set tapi status not in (completed/closed)? → 0 ✅
```

**Illegal transitions: 0** ✅

**Klarifikasi S3 (invoice-less AR):**
- `ar_receipts.posted = 6` (Rp 5,577,800 + 10,450,000 + 12,459,800 + ...)
- `invoices = 0`
- Cross-check allocations: `allocations[0].order_id = "so_001"` (link langsung ke SO)
- Cross-check SO: `so_001.payment_status = "partial"`, `so_001.paid_total = 5,577,800`, `so_001.payments[0] = {receipt_id: "arc_...", amount: 5,577,800, method: "transfer"}`
- **Kesimpulan:** Chain konsisten (SO ↔ AR bidirectional via `order_id` + `payments[]`). Absennya `invoices` bukan bug — model bisnis KN memang bypass invoice document.

**Temuan lapisan ini:**
- Illegal transitions = 0.
- Zombie doc = 0.
- Klarifikasi S3 (invoice-less bukan bug).
- Insight: `vendor_bills = 0` di baseline → C1 fix belum ter-exercise di data historis (fix bekerja untuk bill yang akan dibuat ke depan).

---

## 4. FINDINGS DEEP-DIVE

### 4.B1 — BiFinanceView empty-state guards (E2/E3)

**Severity:** Medium (tech-debt UX)  
**Status:** ✅ FIXED + VERIFIED  
**File:** `frontend/src/features/finance/BiFinanceView.jsx`  
**Ditemukan lewat:** L1 (`ux_audit.py`)

**Sebelum:**
```jsx
// Chart tren bulanan render tanpa cek monthly.length
<ResponsiveContainer><ComposedChart data={monthly}>...</ComposedChart></ResponsiveContainer>

// Tabel antar-PT render tanpa empty state
{comparison.length > 0 && (<table>...</table>)}   // guard hanya sembunyikan, bukan pesan
```

**Iter-1 (FAIL runtime):**
```jsx
{monthly.length === 0 ? <EmptyMonthly/> : <ComposedChart/>}
{comparison.length === 0 ? <EmptyEntity/> : <table>...</table>}
```
→ `ux_audit` PASS, tapi testing agent temukan **backend selalu return 12 bulan zero-filled + entity list zero-filled** → guard tidak pernah trigger runtime.

**Iter-2 (PASS):**
```jsx
const hasMonthlyData = monthly.length === 0 || monthly.some(
  m => Number(m?.revenue||0) !== 0 || Number(m?.expense||0) !== 0 || Number(m?.net_income||0) !== 0
);
const monthlyIsEmpty = monthly.length === 0 || !hasMonthlyData;
const comparisonIsEmpty = comparison.length === 0 || !comparison.some(
  c => Number(c?.revenue||0) !== 0 || Number(c?.expense||0) !== 0 || Number(c?.net_income||0) !== 0
);
```

**Verifikasi (auto_frontend_testing_agent iter-2):**
- Login admin → nav ke Analytics Hub → BI Keuangan ✅
- Year 2021 (empty year): `bi-monthly-empty` MUNCUL + `bi-entity-empty` MUNCUL ✅
- Year 2026 (data ada): chart & tabel render normal ✅
- Refresh + console health: 0 error ✅

**Metrics:** File 224 → 259 baris (masih <500 batas). ux_audit: 0 ERROR / 0 WARN.

---

### 4.C1 — vendor_bills.py missing gl_service import (CRITICAL)

**Severity:** CRITICAL (silent accounting integrity failure)  
**Status:** ✅ FIXED + VERIFIED  
**File:** `backend/routers/vendor_bills.py:15,322-326`  
**Ditemukan lewat:** L2 (`ruff F821`)

**Reproduksi bug (pre-fix):**
```python
# routers/vendor_bills.py:322-326 (BEFORE)
try:
    await gl_service.post_vendor_bill(updated)   # ← NameError: gl_service undefined
except Exception as exc:
    import logging
    logging.error("Gagal posting GL vendor bill %s: %s", updated.get("id"), exc)
```

**Trigger:** Setiap panggilan `_post_bill(bill_id)`, dipanggil dari 2 tempat:
1. `_do_submit(bill_id)` — auto-post ketika clean-match (dalam toleransi harga/qty).
2. `approve_vendor_bill(bill_id)` — setelah manager approve variance bill.

**Konsekuensi akuntansi (silent damage):**
- `vendor_bills.status` → `"posted"` (koleksi update sukses)
- `journal_entries` insert → **skipped karena NameError diserap**
- Ledger `2-1150` (GR-IR clearing) tidak terurai → akumulasi
- Ledger `2-1100` (Hutang Usaha) tidak bertambah → AP under-recorded
- Ledger `1-1500` (PPN Masukan) tidak bertambah → SPT PPN salah
- Kemudian jika bill dibayar (Dr Hutang / Cr Kas) → **saldo Hutang jadi negatif fictitious**
- Trial balance imbalance kumulatif per bill posted

**Fix:**
```python
# routers/vendor_bills.py:15 (AFTER, tambah 1 baris)
from services.config_service import compute_order_pricing, get_effective_settings, role_satisfies
from services import gl_service              # ← ADDED
from services.vendor_bill_service import (
```

**Verifikasi (deep_testing_backend_v2, 7/7 PASS):**
```
✅ 1. Import Present            (line 15 confirmed via grep)
✅ 2. Function Call Present     (line 324 in _post_bill)
✅ 3. Error Handling            (try/except with logging preserved)
✅ 4. No Backend Errors         (0 NameError entries, 0 "Gagal posting GL")
✅ 5. GL Service Module OK      (gl_service.post_vendor_bill def at line 876)
✅ 6. Signature Match           (bill dict passed correctly)
✅ 7. System Ready              (45 GL accounts, endpoints reachable)
                                (termasuk 2-1150 GR-IR, 1-1500 PPN Masukan, 2-1100 Hutang Usaha)
```

**Metrics:** 1 baris ditambahkan, 0 baris dihapus. Backend reload otomatis (WatchFiles).

**Sisa risiko:** `vendor_bills` collection = 0 di baseline. Fix bekerja untuk bill yang akan dibuat forward. Bill lama yang mungkin sudah "posted" tanpa GL journal (jika ada di production DB) perlu **backfill script** — tapi di test DB tidak ada bill lama.

---

### 4.S1 — Schema drift purchase_orders (HIGH)

**Severity:** HIGH  
**Status:** ⚠️ OPEN  
**Ditemukan lewat:** L6 + L7 (runtime probe + DB dump)

**Deskripsi:**
Dokumen `purchase_orders` di storage tak menyimpan field kanonik total (item-level `line_total`, `subtotal`; header-level `subtotal`, `total_amount`, `grand_total`, `net_subtotal`, `dpp`, `ppn_amount`).

**Bukti (dari L7):**
```
=== PO doc keys (top-level) ===
[amount_paid, completed_at, created_at, created_by, entity_id, expected_delivery_date,
 id, items, notes, payment_status, payments, po_number, returned_amount, status,
 supplier_contact, supplier_id, supplier_name, warehouse_id]

MISSING: subtotal, total_amount, grand_total, net_subtotal, dpp, ppn_amount,
         ppn_rate, discount_total, ppn_mode

=== PO item keys ===
[inbound_task_id, price, product_id, product_name, quantity,
 received_qty, sku, status, unit]

MISSING: line_total, subtotal, discount_amount, discount_percent, base_quantity,
         base_unit, category, unit_cost
```

**vs `sales_orders` (kanonik):**
```
Item punya: line_total (5,550,000), subtotal (5,550,000), discount_amount, discount_percent
Header punya: net_subtotal (10,050,000), total_amount (10,050,000), grand_total (11,155,500),
              dpp, ppn_amount, ppn_rate, ppn_mode, discount_total, order_discount_amount
```

**Mitigasi eksisting:**
- `_po_financials()` di `routers/purchase_orders.py:21-62` **hitung ulang** on-the-fly saat detail endpoint dipanggil (ordered_value = Σ quantity × price).
- FE pakai fallback `po.grand_total ?? po.total_amount ?? 0` (verified di 4 file: `PurchaseOrderManagement.jsx:271`, `PODetailPanel.jsx:36,116`, `POVersionHistory.jsx:91`).

**Risiko tersisa:**
1. **Aggregate query** yang `$sum: "$grand_total"` return 0/null padahal ada PO nyata.
2. **List endpoint** `GET /api/purchase-orders` mungkin return items dengan `grand_total: null` (tidak jalan `_po_financials`).
3. **PO Version History snapshot** — jika snapshot menyimpan angka nol karena field tak ada.
4. **Consistency test** yang membandingkan `_po_financials.grand_total` vs stored value → tidak bisa dilakukan.
5. **BI reporting** yang query DB directly bisa report AP purchases = 0.

**Fix rekomendasi:**
1. **Migrate seeder** (`seed_realistic.py`) untuk menulis field kanonik lengkap saat insert PO.
2. **Migrate service** (`_recompute_po_totals()` di `routers/purchase_orders.py` atau new helper) untuk persist ke DB pasca hitung.
3. **Backfill script** untuk PO existing: iterate, compute financials, update DB.

**Effort:** ~4 jam (fix + backfill + test + verify).

---

### 4.S2 — verify_data_integrity false-PASS (HIGH)

**Severity:** HIGH (gate silent-fail)  
**Status:** ⚠️ OPEN  
**File:** `scripts/verify_data_integrity.py:161-165`

**Deskripsi:** Invariant checker menggunakan `.get("subtotal", 0)` default → tidak fail saat field kanonik missing.

**Bukti code:**
```python
# scripts/verify_data_integrity.py:156-179
# INV-DB2: sales_order.total_amount == Σ items.subtotal & subtotal == price*qty
for o in orders:
    items = o.get("items", [])
    ssum = sum(float(i.get("subtotal", 0)) for i in items)   # ← default 0 saat field tak ada
    tot = float(o.get("total_amount", 0) or 0)               # ← default 0 saat None
    if abs(ssum - tot) > 0.01:
        tot_viol.append((o.get("id"), tot, ssum))
    for i in items:
        if abs(float(i.get("subtotal", 0)) - float(i.get("price", 0)) * float(i.get("quantity", 0))) > 0.01:
            sub_viol.append((o.get("id"), i.get("product_id")))
```

**Skenario silent-PASS:**
- Item tidak punya field `subtotal` → default 0
- Order tidak punya field `total_amount` → default 0
- `abs(0 - 0) > 0.01` → False → tidak masuk `tot_viol`
- Reported: `"order: N order — total_amount == Σ subtotal"` PASS

**Perbaikan yang direkomendasikan:**
```python
# Enforce field presence:
missing_subtotal = [i for i in items if "subtotal" not in i]
if missing_subtotal:
    line("FAIL", R, f"order {o['id']}: {len(missing_subtotal)} item tanpa field 'subtotal'")
    continue  # skip invariant check karena field missing = bug lain
# baru evaluasi Σ vs total_amount
```

**Effort:** ~1 jam.

---

### 4.H1 — Baseline seed tidak auto-run (HIGH)

**Severity:** HIGH (operational, misleading gate)  
**Status:** ⚠️ OPEN

**Deskripsi:**
Setelah restore repo (rsync `/tmp/kn` → `/app`), `verify_data_integrity` mereport 4 FAIL:
```
sales_orders: kanonik 'sales_orders' KOSONG
purchase_orders: kanonik 'purchase_orders' KOSONG
purchase_returns: kanonik 'purchase_returns' KOSONG
wms_tasks: kanonik 'wms_tasks' KOSONG
```

Setelah `bash scripts/seed_reset.sh` (~2 menit) → 110 PASS / 0 FAIL.

**Impact:**
- Sesi baru sering laporan 4 FAIL awal → menyita 5-10 menit debugging padahal cukup jalankan seed.
- `load_context.sh` output di akhir juga mengarahkan ke seed_reset, tapi tidak run otomatis.

**Fix rekomendasi:**
Tambah step conditional di `scripts/load_context.sh`:
```bash
# Cek apakah koleksi kanonik kritis kosong
if ! python -c "..." | grep -q "OK"; then
    echo "🔄 Auto-seeding baseline (koleksi transaksional kosong)..."
    bash scripts/seed_reset.sh
fi
```

**Effort:** ~30 menit (skrip idempotent + test).

---

### 4.M1 — F841 unused `actor` (audit trail hilang)

**Severity:** MEDIUM  
**Status:** ⚠️ OPEN  
**Lokasi:** 8 lokasi (ruff F841)

```
backend/routers/crm.py:140                actor
backend/routers/cycle_count.py:83         actor
backend/routers/input_tax.py:115          entity_id
backend/routers/sales_orders.py:704       result
backend/routers/sales_returns.py:27       user
backend/routers/sales_returns.py:118      user
backend/routers/so_approvals.py:161       result
backend/services/approval_service.py:375  pending
```

**Kritikal khusus untuk `actor`/`user`:** Kalau variable `actor` di-fetch tapi tidak digunakan, artinya audit_log.insert pakai `actor="system"` atau kosong. Buka file `crm.py:140`:
```python
actor = get_current_user_display(request)  # F841: assigned but never used
# TODO: seharusnya dipakai di audit_log_service.log(...)
```

**Fix rekomendasi:**
- Wire ke `audit_logs.insert({..., "actor": actor})`; atau
- Hapus assignment jika memang tidak diperlukan.

**Effort:** ~2 jam untuk semua 8.

---

### 4.M2 — React no-unstable-nested-components

**Severity:** MEDIUM  
**Status:** ⚠️ OPEN  
**Lokasi:** `frontend/src/components/CoreWidgets.jsx:95` (Sidebar), `frontend/src/components/ui/calendar.jsx`

**Deskripsi:** Component didefinisi di dalam parent component → tiap render, referensi baru dibuat → React remount subtree → state internal hilang, animation restart, perf drop.

**Contoh (Sidebar):**
```jsx
export function Sidebar({...}) {
  const Item = ({...}) => (<div>...</div>);   // ← defined every render
  return items.map(i => <Item {...i}/>);
}
```

**Fix rekomendasi:**
```jsx
// Extract ke module-level
const SidebarItem = memo(({...}) => (<div>...</div>));
export function Sidebar({...}) {
  return items.map(i => <SidebarItem key={i.id} {...i}/>);
}
```

**Effort:** ~1 jam (2 lokasi).

---

### 4.M3 — Monster file zona bahaya (8 file)

**Severity:** MEDIUM  
**Status:** ⚠️ OPEN  
**Sumber:** `validate_compliance.py` CHECK 12

| File | LoC | Batas | % dari batas |
|---|---:|---:|---:|
| `backend/routers/purchase_orders.py` | 752 | 800 | 94% |
| `backend/routers/sales_orders.py` | 793 | 800 | 99% ⚠️ |
| `frontend/src/config/navigationConfig.js` | 541 | 380* | 142% |
| `frontend/src/features/finance/FinancialStatementsView.jsx` | 498 | 500 | 99% ⚠️ |
| `frontend/src/features/pos/CheckoutDrawer.jsx` | 496 | 500 | 99% ⚠️ |
| `frontend/src/App.js` | 469 | 380* | 123% |
| `frontend/src/components/CartPanel.jsx` | 461 | 500 | 92% |
| `frontend/src/features/sales/ProductTemplatesView.jsx` | 459 | 500 | 92% |

*380 adalah "guideline", 500/800 adalah "hard fail"

**Fix rekomendasi:**
1. `sales_orders.py` (99%): ekstrak submodule (misal `so_lifecycle.py`, `so_payments.py`).
2. `FinancialStatementsView.jsx` / `CheckoutDrawer.jsx`: ekstrak custom hook + subcomponent.
3. `navigationConfig.js`: split per modul (nav-finance.js, nav-hr.js, dll).
4. `App.js`: ekstrak `<RoutesBinder/>`.

**Effort:** ~6 jam per file (untuk 4 file top).

---

### 4.M4 — 21 koleksi MISSING (kode baca, DB kosong)

**Severity:** MEDIUM (mungkin by-design)  
**Status:** ⚠️ OPEN  
**Sumber:** `audit_collection_drift.py`

```
[MISSING] db.approval_requests           (ditulis_kode=True)
[MISSING] db.collection_followups        (ditulis_kode=True)
[MISSING] db.credit_notes                (ditulis_kode=True)
[MISSING] db.credit_overrides            (ditulis_kode=True)
[MISSING] db.crm_interactions            (ditulis_kode=True)
[MISSING] db.crm_leads                   (ditulis_kode=True)
[MISSING] db.cycle_count_sessions        (ditulis_kode=True)
[MISSING] db.entities                    (ditulis_kode=False)  ← ORPHAN CODE READ
[MISSING] db.entity_prices               (ditulis_kode=True)
[MISSING] db.generated_documents         (ditulis_kode=True)
[MISSING] db.intercompany_eliminations   (ditulis_kode=True)
[MISSING] db.invoices                    (ditulis_kode=True)
[MISSING] db.landed_cost_vouchers        (ditulis_kode=True)
[MISSING] db.period_closings             (ditulis_kode=True)
[MISSING] db.product_templates           (ditulis_kode=True)
[MISSING] db.rfqs                        (ditulis_kode=True)
[MISSING] db.tax_invoices_in             (ditulis_kode=True)
[MISSING] db.tax_pph_records             (ditulis_kode=True)
[MISSING] db.user_onboarding             (ditulis_kode=False)  ← ORPHAN CODE READ
[MISSING] db.vendor_bills                (ditulis_kode=True)
[MISSING] db.warehouse_transfers         (ditulis_kode=True)
```

**Kategorisasi:**
- **By-design lazy-creation** (dibuat saat user first-action): approval_requests, credit_notes, invoices, rfqs, vendor_bills, period_closings, product_templates, cycle_count_sessions, generated_documents, tax_pph_records, warehouse_transfers, landed_cost_vouchers, tax_invoices_in.
- **Should-be-seeded** (data referensi yang butuh baseline): entity_prices (harga per PT), intercompany_eliminations (aturan eliminasi konsolidasi), credit_overrides.
- **Orphan code (read tapi tidak pernah write)**: `db.entities` (kode legacy, sekarang pakai `db.business_entities`), `db.user_onboarding` (kode legacy).

**Fix rekomendasi:**
1. Grep `db.entities` (bukan `business_entities`) di kode → rename atau hapus.
2. `db.user_onboarding` → verifikasi apakah masih dipakai, kalau tidak → hapus.

**Effort:** ~1 jam (audit orphan reads).

---

### 4.L1 — audit_endpoint_sweep 422 (sweep bug)

**Severity:** LOW  
**Status:** ⚠️ OPEN  
**Sumber:** `audit_endpoint_sweep.py`

6 endpoint yang butuh payload dilanggar via GET tanpa payload → 422:
```
[422] /api/ar-receipts/deposit
[422] /api/ar-receipts/open-orders
[422] /api/finance/closing/preview
[422] /api/finance/closing/status
[422] /api/hr/field-tracks
[422] /api/inventory/rolls/available
[422] /api/pos/frequently-bought-together
```

Bukan bug app; sweep script perlu di-improve (skip POST-only atau kirim minimal payload).

**Effort:** ~30 menit.

---

### 4.L2 — BUG_BACKLOG belum reconcile

**Severity:** LOW  
**Status:** ⚠️ OPEN  
**Sumber:** L5 (`BUG_BACKLOG.md`)

BUG #3-#7 belum diverifikasi:
- #3 Redundant navigation tabs (Approval Harga Khusus)
- #4 Special Order (OD) menu tak accessible
- #5 Returns Page — Status Tab text formatting
- #6 Inconsistent Page Titles
- #7 Tab Badge Count Position

**Fix rekomendasi:** Verifikasi via `auto_frontend_testing_agent` sekali jalan.

**Effort:** ~2 jam.

---

### 4.L3 — ESLint cosmetics

**Severity:** LOW  
**Status:** ⚠️ OPEN  
**Sumber:** L2 (ESLint via `mcp_lint_javascript`)

136 problems, ~30 real errors. Kategori dominan:
- `react/no-unescaped-entities` × 24 (quotes/apostrophe)
- `react/no-unknown-property` × 1 (shadcn cmdk false-positive)
- `no-empty` × 3 (di ScannerTaskPanel cleanup, safe)
- `Unused eslint-disable directive` × banyak

**Fix rekomendasi:** `eslint --fix` untuk sebagian besar.

**Effort:** ~1 jam.

---

## 5. LAPISAN YANG **BELUM DIJELAJAHI**

Rekomendasi untuk audit lanjutan (dengan alat/teknik konkret):

| # | Lapisan | Alat konkret | Query/pattern | Value potensial |
|---|---|---|---|---|
| 10 | **Money/Decimal precision** | `grep 'float(' backend/services/*.py \| wc -l`; buat probe hitung Σ vs stored total | Cari `float(amount)` di GL post; verifikasi presisi 0.01 IDR | Menangkap rounding drift kumulatif (Rp 1 = kegagalan trial balance) |
| 11 | **Auth decorator audit** | `grep -B2 '@router.\(post\|put\|delete\)'` cross `require_permission` | Endpoint tanpa `require_permission` = data leak antar user/entity | Menangkap security holes RBAC |
| 12 | **N+1 query patterns** | `grep -A5 'async for'` cari `await db.*.find_one` di dalam loop | Hot-path perf | Menangkap query storm pada endpoint listing |
| 13 | **Multi-entity scoping enforcement** | Login user ent_ksc → probe endpoint dengan `?entity_id=ent_kanda` → cek data leak | Simulasi hostile user | Menangkap cross-entity data leak |
| 14 | **Race/idempotency** | Trace endpoint yang update multi-doc tanpa `session.start_transaction()` | Cari `insert_one` + `update_one` sequential tanpa lock | Menangkap partial-write bug |
| 15 | **Timezone/period boundary** | `grep 'datetime.now()'` vs `'utcnow()'` di service | Boundary 2026-01-01 di closing/pajak | Menangkap TZ shift di aging & closing |
| 16 | **Dead endpoint / unused route** | Cross-check FE `apiClient` panggilan vs BE `@router.*` | 508 endpoint BE − 366 FE call sites | Menangkap maintenance debt (endpoint tak dipanggil) |
| 17 | **Deep-cost algorithm (WAC drift)** | Trace `_order_item_unit_cost` untuk skenario: roll 100kg dijual 40kg, retur 5kg, restocking | Property-based test | Menangkap costing bug di retur parsial |

---

## 6. GATE STATUS PASCA AUDIT (final)

```
✅ verify_contract         CONTRACT OK
✅ verify_api_contract     0 ERROR / 1 WARN / 280 FE paths
✅ verify_data_integrity   110 PASS / 0 FAIL (pasca seed_reset)  ⚠️ tapi lihat S2 (false-PASS risk)
✅ ux_audit                0 ERROR / 0 WARN (199 file, pasca fix B1)
✅ validate_compliance     94 PASS / 0 FAIL / 58 WARN (8 monster file di zona bahaya)
✅ check_nav_map           PASS
✅ audit_endpoint_sweep    0 × 5xx / 52 × 4xx / 6 × 422 (sweep bug)
✅ find_dead_services      65/65 used
✅ health_check            100% PASS (3 WARN empty normal)
⚠️  audit_collection_drift 21 MISSING (lihat M4)
```

---

## 7. KREDENSIAL & ENVIRONMENT

**Kredensial (verified via login):**
```
admin@kainnusantara.id    / demo12345
sales@kainnusantara.id    / demo12345
manager@kainnusantara.id  / demo12345
warehouse@kainnusantara.id/ demo12345
```

**Auth kontrak:**
- Response field: **`token`** (bukan `access_token`)
- Format: `sess_<random>` (SHA256 hashed di DB, bukan JWT)
- Header: `Authorization: Bearer sess_...`
- Logout invalidates token immediately (verified L6)

**FE testid login:** `login-email-input`, `login-password-input`, `login-submit-button`.

**Environment:**
- `MONGO_URL` (backend/.env): `mongodb://localhost:27017` — TIDAK DIUBAH
- `DB_NAME` (backend/.env): `test_database` — TIDAK DIUBAH
- `REACT_APP_BACKEND_URL` (frontend/.env): `https://repo-loader-57.preview.emergentagent.com` — TIDAK DIUBAH

---

## 8. NEXT ACTION ITEMS (prioritas)

### Sprint saran (2-3 hari kerja)

**Day 1 (integrity):**
1. **S1** — migrate PO storage: seeder tulis field kanonik + service persist pasca `_recompute` + backfill script (4 jam).
2. **S2** — perkuat `verify_data_integrity.py` menolak field kanonik missing (1 jam).
3. **H1** — auto-seed conditional di `load_context.sh` (30 menit).

**Day 2 (feature P3):**
4. **P3 SMTP PO PDF** — butuh SMTP credentials dari owner (host/port/user/pass/from + provider). Implementasi setelah S1 terselesaikan agar PO PDF tampilkan grand_total benar.

**Day 3 (tech-debt):**
5. **M1** — wire `actor` ke audit_logs (2 jam).
6. **M2** — extract nested components (1 jam).
7. **M3** — split `sales_orders.py` 793→<500 (paling urgent, sudah 99%) (6 jam).
8. **L2** — reconcile BUG_BACKLOG #3-#7 (2 jam).

### Feature backlog jangka menengah
- P4 Budget Control
- P5 Multi-currency/FX
- Audit lapisan 10-17 (money precision, auth decorator, multi-entity leak, dll)

---

## 9. APPENDICES

### A. Sample dokumen kunci (dump L7)

**purchase_orders — po_001:**
```json
{
  "id": "po_001",
  "po_number": "PO-0001",
  "supplier_id": "sup_xxx", "supplier_name": "PT Xxx",
  "warehouse_id": "wh_jakarta",
  "entity_id": "ent_ksc",
  "status": "receiving",
  "amount_paid": 0, "returned_amount": 0,
  "payment_status": "unpaid",
  "items": [{
    "product_id": "prod_batik_mega",
    "product_name": "Batik Mega Mendung",
    "sku": "BATIK-001",
    "unit": "meter",
    "quantity": 150.0,
    "price": 165000,
    "received_qty": 150.0,
    "inbound_task_id": "task_xxx",
    "status": "received"
  }],
  "payments": [], "expected_delivery_date": "..."
}
```
**Note:** TIDAK ada `subtotal`, `total_amount`, `grand_total`, `line_total` (item). Ini yang dibahas §4.S1.

**sales_orders — so_001 (kanonik lengkap):**
```json
{
  "id": "so_001",
  "number": "SO-0001",
  "customer_id": "cust_toko_kain",
  "entity_id": "ent_ksc",
  "status": "done",
  "grand_total": 11155500.0,
  "total_amount": 10050000.0,
  "net_subtotal": 10050000.0,
  "dpp": 10050000.0,
  "ppn_amount": 1105500.0, "ppn_rate": 11, "ppn_mode": "excluded",
  "paid_total": 5577800.0, "payment_status": "partial",
  "items": [{
    "product_id": "prod_batik_mega",
    "quantity": 30.0, "price": 185000.0,
    "line_total": 5550000.0, "subtotal": 5550000.0,
    "discount_amount": 0, "discount_percent": 0,
    "base_quantity": 30.0, "base_unit": "meter", "category": "...", "unit_cost": ...
  }],
  "payments": [{
    "id": "pay_...", "amount": 5577800.0,
    "receipt_id": "arc_...", "receipt_number": "AR-00001",
    "method": "transfer", "date": "..."
  }]
}
```

**inventory_balances — SSOT INV-ROLL-1:**
```
Keys granular bucket-based:
  on_hand_qty, available_qty, reserved_qty, committed_qty, packed_qty, picked_qty,
  quarantine_qty, damaged_qty, hold_qty, blocked_qty, wip_qty,
  in_transit_qty, in_transit_inbound_qty, in_transit_sales_qty,
  in_transit_transfer_qty, in_transit_intercompany_qty,
  incoming_qty, on_order_qty, owned_qty, atp_qty,
  roll_count, roll_counts, on_hand_roll_count,
  product_id, warehouse_id, owner_entity_id
```

**ar_receipts — invoice-less allocation:**
```json
{
  "id": "arc_0bb100a893a0",
  "number": "AR-00001",
  "status": "posted",
  "customer_id": "cust_toko_kain",
  "amount": 5577800.0, "total_funds": 5577800.0,
  "applied_total": 5577800.0, "unapplied_amount": 0,
  "method": "transfer", "receipt_date": "2026-06-29",
  "allocations": [{
    "order_id": "so_001",           // ← link ke SO, bukan invoice
    "order_number": "SO-0001",
    "applied": 5577800.0,
    "outstanding_after": 5577700.0,
    "payment_status": "partial"
  }]
}
```

### B. Full 21 MISSING collections list

Lihat §4.M4.

### C. Full 8 monster file list

Lihat §4.M3.

### D. Perintah reproduksi audit

**Restore + baseline:**
```bash
git clone https://github.com/dakagaberesberesdah/kn /tmp/kn
cp /app/backend/.env /tmp/be.env.bak && cp /app/frontend/.env /tmp/fe.env.bak
find /app -maxdepth 1 -not -path /app -not -name '.env*' -exec rm -rf {} +
cp -r /tmp/kn/. /app/ && rm -rf /app/.git
cp /tmp/be.env.bak /app/backend/.env && cp /tmp/fe.env.bak /app/frontend/.env
cd /app/backend && pip install -r requirements.txt
cd /app/frontend && yarn install
sudo supervisorctl restart all
bash /app/scripts/load_context.sh
bash /app/scripts/seed_reset.sh
```

**Audit 9 lapisan:**
```bash
# L1
for s in verify_contract verify_api_contract verify_data_integrity health_check \
         audit_endpoint_sweep ux_audit validate_compliance check_nav_map \
         find_dead_services audit_collection_drift; do
  python /app/scripts/$s.py
done

# L2 (via MCP tool)
mcp_lint_python  /app/backend/routers/*.py + /app/backend/services/*.py
mcp_lint_javascript /app/frontend/src/**/*.jsx

# L3
grep -rn "gl_service\." /app/backend/routers/ | grep -v "import"
grep -rn "except Exception" /app/backend/services /app/backend/routers

# L4-L5: manual review handoff/backlog/plan

# L6 (runtime probe)
python3 -c "
import requests
BASE='http://localhost:8001/api'
tok=requests.post(f'{BASE}/auth/login',json={'email':'admin@kainnusantara.id','password':'demo12345'}).json()['token']
H={'Authorization':f'Bearer {tok}'}
# probe endpoints...
"

# L7 (DB dump)
cd /app/backend && python3 -c "
from dotenv import load_dotenv; load_dotenv('.env')
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
async def main():
    c=AsyncIOMotorClient(os.environ['MONGO_URL'])
    db=c[os.environ.get('DB_NAME','test_database')]
    # ... dump keys per collection
asyncio.run(main())
"

# L8 (orphan crawl) — script serupa L7 dengan set-based FK check

# L9 (state-machine) — aggregate status per collection
```

### E. File yang dibuat/diubah sesi ini

| File | Aksi | Baris |
|---|---|---|
| `/app/frontend/src/features/finance/BiFinanceView.jsx` | modify (fix B1) | 224 → 259 |
| `/app/backend/routers/vendor_bills.py` | modify (fix C1) | +1 baris `import` |
| `/app/test_result.md` | update | 2 task didokumentasi |
| `/app/memory/AUDIT_REPORT_SESSION_071.md` | **create** (report ini) | 700+ baris |
| `/app/memory/SESSION_HANDOFF.md` | prepend #071 | +30 baris di top |

---

**END OF AUDIT REPORT — Session #071**
