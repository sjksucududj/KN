# plan.md — Platform Dokumen/PDF + WhatsApp + E‑Sign **dan** Roadmap Retur & Refunds (Kain Nusantara ERP)

> **Catatan status dokumen platform:** Phase 2–7 (PDF/E‑Sign/WA) sudah COMPLETED & TESTED di sesi sebelumnya (lihat log historis di bawah).  
> **Fokus roadmap aktif saat ini:** **Returns & Refunds R0→R7** (lihat `/app/memory/RETURNS_ANALYSIS.md`).

---

## 🔁 SESSION 2026-07-24 — Returns & Refunds Roadmap (R0–R2 selesai; mulai R3)

### Ringkasan keputusan terkunci (dari user)
- Store-credit/saldo customer **wajib** untuk “potong bon”.
- Approval **1 langkah Manager** (bukan approval engine).
- Inspeksi retur jual **wajib untuk semua retur**.
- Returned rolls masuk **quarantine**.
- Roll SSOT: **owner_entity_id (kepemilikan) ≠ warehouse_id (lokasi fisik)**.
- `custom_fields` pada policy harus **extensible**.
- Nego = **Credit Note diskon** tanpa gerak stok.
- Supplier origin import/local (`origin_type`, `country`, PO override) memengaruhi policy.
- Nilai retur harus landed-cost aware pada fase finance (R5).

---

## Objectives (updated)
1) Menyelesaikan modul **Retur Jual** end-to-end bertahap R0→R7 dengan guardrails (contract/integrity/compliance) tetap hijau.
2) Menjaga **idempotensi GL** & integritas subledger persediaan ↔ GL (INV-GL-DRIFT) untuk jalur normal.
3) Menangani kasus nyata tekstil ERP:
   - partial outcome per item/roll
   - inspeksi 4-point mandatory
   - karantina + release/scrap
   - cross-entity owner vs location + transfer ownership yang GL-safe

---

## ✅ Status Implementasi Returns & Refunds (R0–R2)

### R0 — Supplier origin + Return Policy Engine — ✅ SELESAI (verified)
- Supplier `origin_type` local|import + `country` + PO override `import_flag`.
- Return policy extensible via `custom_fields`.
- Sales return policy engine: scope global/category/customer, resolve precedence, eligibility/deadline snapshot.
- **Bukti uji:** `test_r0_poc.py` PASS; guardrails hijau; UI policy editor & eligibility banner diverifikasi.

### R1 — Sales-return state machine + 4 outcomes + partial — ✅ SELESAI (verified)
- Lifecycle eksplisit: draft → pending_approval → approved → inspecting → inspected → terminal.
- Outcomes: refund / store_credit / nego / reject; partial per item/qty.
- Finance posting/CN di-settle (bukan approve), nego tanpa stock movement.
- **Bukti uji:** `test_r1_poc.py` **28/28 PASS**; guardrails hijau; testing_agent iter_146 aman.

### R2 — Unified Inspection 4-point + Quarantine — ✅ SELESAI (verified end-to-end)
- Reuse `qc_inspection_service` 4-point untuk grade A/B/C + rekomendasi outcome.
- Refund/store_credit settle → roll masuk **quarantine** (bukan available).
- Manager release quarantine: release→available, scrap→damaged.
- Nego → tidak membuat roll quarantine (tanpa gerak stok).
- **Frontend:**
  - `ReturnInspectPanel` form 4-point (P1–P4) + preview grade/rekomendasi.
  - `ReturnQuarantinePanel` list roll karantina + release/scrap.
- **Bukti uji:**
  - `test_r2_poc.py` **17/17 PASS**
  - guardrails: jalur normal **Integrity 126/0/0** (refund/store_credit/nego)
  - testing_agent iter_147: **backend 100%**, **frontend 100% (29/29)**, 0 bug.
- **Known deferred (R5):** scrap menyebabkan 1 WARN integritas (write-off GL belum ada) → bukan bug.

---

## ✅ Phase R4 — Link Retur Jual↔Beli + Supplier RMA lifecycle + goods_back/regrade + kebijakan IMPOR — SELESAI (verified 2026-07-24)

- **Chain 2-arah:** `POST /api/sales-returns/{id}/create-purchase-return` menautkan retur jual (roll karantina) → retur beli (`supplier_flow`, `supplier_status=requested_supplier`), `SR.linked_purchase_return_id` ↔ `PR.origin_sales_return_id`.
- **Supplier RMA lifecycle** (`purchase_return_state.py`): requested → ship-to-supplier → supplier-accept(refund|ap_credit) | supplier-reject → goods-back(+regrade). Approve mode-aware (DIRECT konsumsi langsung; RMA = gate). Anti-drift: roll tetap subledger sepanjang RMA, GL hanya di accept; goods_back tanpa GL.
- **Kebijakan IMPOR (§J):** supplier impor & tak-returnable → 400 (rekomendasi regrade + jual lokal); `bypass_import_policy` override.
- **Frontend:** badge supplier_status + chip origin di list Retur Beli; panel ALUR RMA (ship/accept+outcome/reject/goods-back+regrade) + timeline; tombol "Teruskan ke Supplier" + chip linked PR di panel karantina retur jual.
- **Bukti:** `test_r4_poc.py` 35/35 · regresi R1 28/R2 17/R3 21 · Integrity 126/0/0 (POC) · Contract OK · `testing_agent_v3` iter_149 backend 73/73 + frontend 100%, 0 bug.

### Deferred → R5 (finance depth)
- Write-off GL untuk scrap/goods (hapus WARN INV-GL-DRIFT), store-credit ledger, cash refund, reversals, landed-cost awareness, pemisahan GL refund-kas vs ap_credit.

---

## ✅ Phase R3 — Inventory ownership/location + regrade + cross-entity transfer — SELESAI (verified 2026-07-24)

### Bukti penyelesaian R3
- **Stopping point terverifikasi & DIPERBAIKI:** gate integritas GAGAL 1 (`dashboard available 4167 != Σbalances 4166`,
  drift 1 meter). Akar masalah: KPI stok dashboard (`product_summary` tanpa scope) menghitung LINTAS-entitas,
  sedangkan `GET /inventory/balances` di-scope per-entitas (`owner_entity_id`). Setelah R3 memungkinkan transfer
  kepemilikan lintas-PT, roll milik `ent_kanda` ikut terhitung di KPI tapi tidak di list → drift 1m.
- **Fix (`routers/dashboard.py`):** `available_qty`/`reserved_qty` kini diagregasi dari koleksi `inventory_balances`
  yang di-scope sama (`resolve_list_scope("inventory_balances", ...)`) → INV-2 & INV-3 hijau.
- **Backend:** settle terima `return_warehouse_id` (lokasi; owner tetap = entitas SO); restock ke quarantine di lokasi
  terpilih; `release_quarantine` dengan regrade A/B/C (+`regraded_from`); endpoint
  `POST /api/sales-returns/{id}/rolls/{roll_id}/transfer-ownership` (reuse `execute_ownership_transfer` +
  `gl_service.post_intercompany_transfer`, idempotent, `pair_id`); enrichment quarantine
  (owner_entity_name, warehouse_name, product_name, sku).
- **Frontend:** `ReturnSettleModal` picker gudang penerimaan; `ReturnQuarantinePanel` kolom Owner vs Lokasi + select
  grade final + tombol Release + aksi "Transfer Kepemilikan" (modal pilih PT tujuan, GL-safe).
- **Bukti uji:**
  - `test_r3_poc.py` **21/21 PASS**; regresi `test_r1_poc` 28/28, `test_r2_poc` 17/17.
  - Guardrail clean-seed: `verify_contract` OK, `verify_data_integrity` **126/0/0**.
    (1 WARN hanya muncul SETELAH R2 POC scrap = write-off GL ditunda R5; 2 FAIL api_contract [cash-advance] & 2 FAIL
    entity_scoping [product_traceability] adalah PRE-EXISTING di luar modul retur.)
  - `testing_agent_v3` iter_148: **backend 30/30 PASS**, frontend code review 100%, 0 bug; modal transfer-ownership
    diverifikasi visual (owner KSC→pilih Kanda, lokasi tetap).

### Deferred (explicit)
- **R5:** scrap write-off journal (hapus WARN INV-GL-DRIFT), store-credit ledger, cash refund, reversals, landed-cost awareness.

---

## 🗄️ (arsip) Phase R3 — rencana awal

### Scope R3 (locked order)
1) **Settle-time** selection: return destination `warehouse_id` + `owner_entity_id`.
   - Default cerdas: `warehouse_id` = outbound warehouse SO (fallback gudang pertama), `owner_entity_id` = entity SO.
   - Menangani kasus: “beli di Kanda, retur fisik di Sukacita”.
2) **Regrade** saat release karantina (grade final) + movement/audit.
3) **UI clarity:** tampilkan ownership vs lokasi pada roll karantina & detail.
4) **Cross-entity ownership transfer** untuk roll retur (released) dengan GL-safe reuse:
   - Reuse `roll_service.execute_ownership_transfer` + `gl_service.post_intercompany_transfer`
   - Endpoint baru: `POST /api/sales-returns/{return_id}/rolls/{roll_id}/transfer-ownership`

### Design notes (grounded in current repo)
- Rolls sudah punya `owner_entity_id` vs `warehouse_id` (SSOT split sudah ada).
- Entities ada di koleksi `business_entities`: `ent_ksc`, `ent_kanda`.
- Warehouses location-only: `wh_jakarta`, `wh_bandung`, `wh_surabaya`.
- Inter-entity transfer engine sudah ada pada `routers/transfers.py` (status completed on approve) + GL posting at cost.

### Implementation Steps (R3)
**Backend**
1. **Schema updates**
   - Extend `SalesReturnCreate` / `SalesReturnSettle` payload untuk menerima pilihan:
     - `return_warehouse_id` (lokasi fisik penerimaan)
     - `return_owner_entity_id` (kepemilikan default)
   - Persist ke dokumen `sales_returns` (snapshot agar auditable).
2. **Restock into quarantine respects chosen destination**
   - Update `_restock_returned_items` untuk pakai:
     - `warehouse_id = ret.return_warehouse_id || _resolve_return_warehouse(order_id)`
     - `owner_entity_id = ret.return_owner_entity_id || ret.entity_id`
   - Pastikan rebuild_balance segmen tepat (pid, wid, owner).
3. **Regrade flow on release**
   - `release_quarantine` sudah menerima `grade` override per roll; pastikan:
     - grade final tersimpan
     - movement notes memuat grade lama→baru (bila berubah)
4. **Ownership transfer endpoint**
   - New endpoint (manager/admin):
     - Validasi roll milik return tersebut (`return_id`, `origin_type=return`)
     - Hanya boleh bila roll status `available` (atau `quarantine` jika diputuskan) — default: only available.
     - Implement via pembuatan dokumen transfer-kind `inter_entity` minimal (atau helper internal) agar:
       - `execute_ownership_transfer` jalan
       - `post_intercompany_transfer` posting JE idempotent
     - Return updated roll + JE metadata.

**Frontend**
5. **Set destination fields during return creation/settle**
   - Tambahkan picker di CreateReturnForm atau di sebelum settle (sesuai UX paling aman) untuk:
     - return warehouse
     - owner entity
   - Default terisi otomatis; user bisa override.
6. **Quarantine panel show owner + warehouse + regrade controls**
   - Tampilkan `owner_entity_id` label (short_name) + warehouse name.
   - Saat release: bisa set grade final per roll (A/B/C) + scrap.
7. **Ownership transfer UI**
   - Tombol “Transfer Kepemilikan” pada roll available hasil retur (manager/admin): pilih dest entity → submit.

### Testing & Verification (R3)
- Tambah `test_r3_poc.py` (idempotent):
  - create→approve→inspect→settle refund ke warehouse A tetapi owner entity B (override)
  - verify roll quarantine with chosen `warehouse_id` + `owner_entity_id`
  - release to available + regrade
  - transfer ownership to other entity → verify JE posted + owner_entity_id berubah
- Jalankan:
  - `python scripts/verify_contract.py --all`
  - `python scripts/verify_data_integrity.py` (harus 126/0/0 jalur normal)
  - `python scripts/validate_compliance.py`
  - `yarn build` + restart frontend
  - Screenshot UX R3
  - `testing_agent_v3` untuk R3 user stories

### Deferred (explicit)
- **R5:** scrap write-off journal (hapus WARN INV-GL-DRIFT), store-credit ledger, cash refund, reversals, landed-cost awareness.

---

## Roadmap After R3 (unchanged order)

### R4 — Link sales↔purchase returns + supplier return sub-status
- Link `sales_return.linked_purchase_return_id` ↔ `purchase_return.origin_sales_return_id`.
- Purchase return: requested_supplier → shipped_supplier → accepted/refund|ap_credit → rejected_supplier goods_back (+regrade).
- Policy origin import affects whether supplier return is allowed.

### R5 — Finance complete
- Customer store-credit ledger + application on next invoice.
- Cash refund, nego CN, reversals.
- Inventory write-offs (scrap) + landed-cost-aware valuation.

### R6 — Manager approval + audit + legal snapshot
- One-step manager approval (as locked), audit trail, legal SO policy snapshot.

### R7 — Full UI/UX wizard + pagination
- Wizard returns + inspection + chain link (sales↔purchase) + store-credit ledger UI.
- Returns pagination (P2) and UX polish.

---

## Historical Log (unchanged structure from original plan)

> ## 🔁 SESSION 2026-07-23 (b) — POLISH FLOW RETUR BELI (pilihan user 1a/2a/3a/4a)
> (tidak diubah; tetap referensi historis)
> ...

> ## 🔁 SESSION 2026-07-23 — RE-CLONE & CONTINUE: Retur Beli PRESISI (per roll) + Kartu Asal
> (tidak diubah; tetap referensi historis)
> ...

> ## 🔁 SESSION 2026-07-21 — RE-CLONE & CONTINUE (Phase 7)
> (tidak diubah; tetap referensi historis)
> ...

> ## Objectives (dokumen platform)
> (tetap sebagai artefak historis; roadmap dokumen platform sudah selesai)
> ...
