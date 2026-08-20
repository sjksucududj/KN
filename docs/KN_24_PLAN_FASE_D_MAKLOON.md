# KN_24 — RENCANA & HASIL FASE D: MAKLOON RANTAI PROSES

> Status: **✅ SELESAI & TERUJI** (Phase 1–3 `plan.md`, sesi 2026-07-26).
> Keputusan pemilik yang dieksekusi: **D-04** (mitra melaporkan dalam satuannya sendiri),
> **D-05** (susut standar **per mitra/kontrak**), **D-07** (basis tarif **BEBAS** + formula
> custom), **D-09** (toleransi selisih & **semua** tindakan klaim, wajib approval).
> Induk: `KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` (PS-03/PS-04/PS-08/PS-11),
> `KN_22_PLAN_FASE_B_UOM.md` (konversi), `KN_23_PLAN_FASE_C_LOT.md` (lot & genealogi).
> Aturan emas: **kode menang atas dokumen**.

---

## 1. Masalah yang diselesaikan

Sebelum Fase D, makloon hanya **1 langkah 1 mitra** dengan tarif angka bebas di layar:

| Gejala | Akibat |
|---|---|
| Tarif diketik manual per order | tidak auditable, tidak bisa dibandingkan antar mitra, rawan salah ketik |
| Susut/yield hard-coded di resep global | mitra yang susutnya beda tidak terwakili (D-05) |
| Tidak ada rantai proses | benang→grey→PFD→printing harus dibuat sebagai banyak order lepas; HPP tidak berjenjang |
| Mitra melapor "kg" padahal stok "yard" | konversi dilakukan di kepala operator, tanpa jejak |
| Selisih hasil tidak punya konsekuensi | kerugian menempel diam-diam ke HPP, tidak ada klaim/approval |

Fase D menaikkan makloon menjadi **rantai proses multi-langkah multi-mitra berbasis kontrak**.

## 2. Keputusan pemilik yang dieksekusi

| # | Keputusan | Implementasi |
|---|---|---|
| D-04 | Mitra pakai satuan sendiri | `issue`/`receive` menerima `doc_uom`+`doc_qty` / `output_uom`+`output_doc_qty` → dikonversi via `uom_rules_service.convert_with_trail`, jejak disimpan di `steps[].issue_uom_trail` / `steps[].receive_uom_trail` |
| D-05 | Susut standar **per kontrak** | `supplier_contracts.shrinkage_pct` (+ `yield_factor`, `byproduct_pct`). Prioritas: **input langkah → kontrak → resep → kebijakan global**, sumber dicatat di `steps[].shrinkage_source` |
| D-07 | Basis tarif **BEBAS** + formula | `tariff_basis ∈ pick·kg·meter·yard·ball·cone·roll·lot·lumpsum·custom` + `tariff_formula` (safe-eval AST) + `aux_fees[]` (screen/repeat) + `min_charge` + `tariff_qty_source ∈ output·input` |
| D-09 | Toleransi & klaim | `tolerance_pct` per kontrak; selisih di luar toleransi → `steps[].claim` otomatis `open`; **3 tindakan** (`potong_bon`·`tagih_ganti`·`terima_catatan`) **wajib approval** peran di `claim_approval_roles` |
| D-10 | Lot output manual per roll | penerimaan makloon **wajib** daftar roll ber-LOT manual; lot input menjadi `parent_lot_ids` lot output (genealogi Fase C utuh) |

Kebijakan **configurable tanpa deploy** (`system_settings` scope `makloon`):
`variance_tolerance_pct` · `default_shrinkage_pct` · `contract_mode` (`off|warn|block`) ·
`auto_claim` · `claim_approval_roles` · `require_output_product` · `require_yield_reason`.

## 3. Model data

### 3.1 `supplier_contracts` (prefix `sct_`, nomor `<ENT>/SCT-#####`)

```
id, contract_number, entity_id, contract_type (makloon|purchase)
partner_kind, partner_id, partner_name        # makloon_id | supplier_id
title, process_type, product_id/sku/name, input_product_id
── Tarif (D-07) ────────────────────────────────────────────────
tariff_basis, tariff_rate, tariff_formula, tariff_qty_source (output|input),
ppi, aux_fees[{code,label,basis,amount}], min_charge, currency
   aux basis: lumpsum|per_roll|per_color|per_repeat|per_kg|per_meter|per_output_unit
── Standar proses (D-05) & toleransi (D-09) ────────────────────
shrinkage_pct, tolerance_pct (nullable → pakai kebijakan), yield_factor, byproduct_pct
── Komersial ───────────────────────────────────────────────────
moq, lead_time_days, payment_term_code, valid_from, valid_to,
status (draft|active|expired|terminated), sample_ref, notes,
usage_count            # >0 ⇒ DELETE ditolak 409 (jejak audit aman)
created_at/by, updated_at/by
```

### 3.2 Tambahan pada `makloon_orders.steps[]` (additive)

```
contract_id, contract_number
tariff_basis, tariff_rate, tariff_plan{}        # rencana (saat create)
tariff_actual{ source, basis, basis_qty, rate, amount, explain[], conversion{} }
shrinkage_pct, shrinkage_source, tolerance_pct
estimate{ method (gsm|yield|formula|unknown), expected_output_qty,
          expected_byproduct_qty, explain[] }
issue_uom_trail{}, receive_uom_trail{}          # doc→base (D-04)
variance{ variance_qty, variance_pct, tolerance_pct, shortfall_qty,
          shortfall_value, unit, unit_value, claim_required, message }
claim{ status (none|open|pending_approval|approved|rejected), required, action,
       amount, amount_suggested, reason, history[], proposed_by/at,
       approved_by/at, approval_note, rejected_by/at/reason, effect{} }
```
Order-level: `order_warnings[]` (mode kontrak `warn`), `claim_summary{open,
pending_approval, approved, rejected, approved_amount, needs_action}`.

## 4. Alur bisnis (end-to-end)

```
Kontrak mitra (sct_)  ──resolve_active(partner, process_type, product)──┐
                                                                        ▼
Wizard Order Makloon ── steps[] rantai ──►  estimate_output (GSM/yield/formula)
   validasi: output langkah N == input langkah N+1  (400 bila terputus)
   mode kontrak: off → bebas · warn → order_warnings[] · block → 400
        │
        ▼
ISSUE langkah  → roll input status `subcon` (WIP-at-vendor, owned non-ATP)
                 GL: Dr 1-1350 WIP Makloon / Cr 1-1300 Persediaan
        │
        ▼
RECEIVE langkah → roll `subcon` → `consumed`; output = roll baru `available`
                 dgn LOT MANUAL + parent_lot_ids (genealogi)
                 tarif dihitung ULANG dari kontrak memakai qty AKTUAL
                 vendor_bill (bill_type=makloon_service) + GL:
                   Dr 1-1350 + PPN Masukan / Cr 2-1100 Hutang Usaha
                 GL terima: Dr 1-1300 Persediaan / Cr 1-1350 WIP  → WIP net 0
                 variance dihitung → di luar toleransi ⇒ claim `open` + notifikasi
        │
        ▼
KLAIM  propose (aksi + nilai + alasan) → `pending_approval`
       approve (hanya `claim_approval_roles`) → eksekusi:
         potong_bon     Dr 2-1100 Hutang Usaha  / Cr 4-9200 Pendapatan Klaim
                        + vendor_bill.grand_total dikurangi (AP tetap rekonsiliasi)
         tagih_ganti    Dr 1-1260 Piutang Klaim / Cr 4-9200 Pendapatan Klaim
         terima_catatan TIDAK ada jurnal (kerugian sudah terserap ke HPP output)
       reject (alasan wajib) → `rejected`
```

**HPP berjenjang:** per langkah `output_value = material_value + service_value +
aux_cost − byproduct_value`, `output_unit_cost = output_value / actual_output_qty`.
Output langkah N menjadi `material_value` langkah N+1 → HPP akhir = `costing.hpp_output`
& `costing.hpp_per_unit`.

## 5. Berkas & tanggung jawab

| Berkas | Isi |
|---|---|
| `backend/schemas_contracts.py` | `SupplierContractCreate/Patch`, `ContractStatusIn`, `ContractAuxFee`, `TariffPreviewIn`, `ContractResolveIn` |
| `backend/services/contract_service.py` | kebijakan (`get/update_settings`), CRUD kontrak, `resolve_active`, **`compute_tariff`** (basis + formula + aux + min_charge + jejak), `tariff_preview`, `stats`, `mark_used` |
| `backend/routers/supplier_contracts.py` | `/api/supplier-contracts*` + `/api/makloon-partners/scorecard` (perm `supplier_contract`) |
| `backend/services/makloon_calc_service.py` | `estimate_output` (GSM+lebar+susut / yield / formula) + `evaluate_variance` |
| `backend/services/makloon_order_service.py` | `create_makloon_order` (rantai, kontrak, estimasi, rencana tarif) · `issue_step` · `receive_step` (konversi, tarif aktual, vendor bill, GL, lot, variance) · `cancel_order` · costing |
| `backend/services/makloon_claim_service.py` | `build_claim_from_variance` · `propose_claim` · `approve_claim` (GL + potong bon) · `reject_claim` · `list_claims` · `claim_stats` · `partner_scorecard` · `summarize` |
| `backend/routers/makloon_orders.py` | `/api/makloon-orders*` (perm `makloon_order`) |
| `backend/schemas_makloon.py` | `MakloonOrderCreate/StepInput/IssueIn/ReceiveIn/ReceiveRoll/ClaimIn/ClaimDecisionIn/EstimateIn` |
| `frontend/.../purchasing/contracts/ContractsView.jsx` | daftar kontrak + KPI + filter + hapus (409 aman) |
| `frontend/.../purchasing/contracts/ContractFormModal.jsx` | form kontrak (basis tarif, formula, aux, susut, toleransi, validitas) |
| `frontend/.../purchasing/contracts/MakloonPolicyModal.jsx` | kebijakan makloon (mode kontrak, toleransi/susut default, peran penyetuju, aturan wajib) |
| `frontend/.../purchasing/makloon/MakloonWizard.jsx` | wizard 3 tahap: Bahan & Gudang → Rantai Proses → Ringkasan & Simpan |
| `frontend/.../purchasing/makloon/MakloonStepEditor.jsx` | editor langkah (mitra, proses, kontrak, produk output, estimasi & pratinjau tarif) |
| `frontend/.../purchasing/MakloonOrderDetailPanel.jsx` | timeline, langkah, issue/receive, costing + **HPP berjenjang**, variance, klaim |
| `frontend/.../purchasing/makloon/MakloonClaimsView.jsx` | layar persetujuan klaim lintas order + KPI + filter + **Skor Mitra** |
| `frontend/.../purchasing/makloon/MakloonClaimPanel.jsx` | detail klaim: pilih tindakan, lihat dampak, approve/reject |

## 6. Kontrak API

Base `${REACT_APP_BACKEND_URL}/api` · `Authorization: Bearer <token>`.

### 6.1 Kontrak mitra — permission `supplier_contract`

| Method | Path | Catatan |
|---|---|---|
| GET | `/supplier-contracts` | `?entity_id&contract_type&partner_id&status&q&limit` |
| GET | `/supplier-contracts/stats` | `{total, active, makloon, purchase, expiring_30d}` |
| GET · PUT | `/supplier-contracts/policy` | kebijakan makloon (PUT = admin/manager) |
| POST | `/supplier-contracts/resolve` | kontrak aktif per (mitra, proses, produk) |
| POST | `/supplier-contracts/tariff-preview` | simulasi ongkos + `explain[]` (auditable) |
| GET | `/supplier-contracts/{id}` | detail |
| POST | `/supplier-contracts` | create (`create`) |
| PATCH | `/supplier-contracts/{id}` | update (`update`) |
| POST | `/supplier-contracts/{id}/status` | draft/active/expired/terminated |
| DELETE | `/supplier-contracts/{id}` | **409** bila `usage_count > 0` |
| GET | `/makloon-partners/scorecard` | rata-rata selisih, on-target %, klaim (perm `makloon`) |

### 6.2 Order makloon & klaim — permission `makloon_order`

| Method | Path | Aksi perm |
|---|---|---|
| GET | `/makloon-orders` | `view` |
| POST | `/makloon-orders/estimate` | `view` — pratinjau tanpa menyimpan |
| POST | `/makloon-orders` | `create` |
| GET | `/makloon-orders/{id}` | `view` |
| GET | `/makloon-orders/claims` · `/claims/stats` | `view` |
| POST | `/makloon-orders/{id}/issue` | `issue` |
| POST | `/makloon-orders/{id}/receive` | `receive` |
| POST | `/makloon-orders/{id}/claim` | `claim` |
| POST | `/makloon-orders/{id}/claim/approve` · `/claim/reject` | `claim_approve` |
| POST | `/makloon-orders/{id}/cancel` | `cancel` |

### 6.3 RBAC efektif

| Role | Lihat | Buat order | Issue/Receive | Ajukan klaim | Setujui klaim | Kontrak |
|---|---|---|---|---|---|---|
| admin | ✅ | ✅ | ✅ | ✅ | ✅ | CRUD |
| manager | ✅ | ✅ | ✅ | ✅ | ✅ | CRUD |
| warehouse | ✅ | ❌ | ✅ | ✅ | ❌ | lihat |
| sales | ✅ (view-only) | ❌ | ❌ | ❌ | ❌ | ❌ (data komersial) |

## 7. Invarian (`scripts/verify_data_integrity.py` · blok **L4-MKO**)

| Kode | Invarian |
|---|---|
| `INV-MKO-01` | rantai langkah nyambung (output N == input N+1) & setiap langkah punya produk output |
| `INV-MKO-02` | langkah `received` punya lot output ber-`lot_id` + genealogi induk |
| `INV-MKO-03` | langkah dengan tarif > 0 menyimpan basis + jejak perhitungan (D-07) |
| `INV-MKO-04` | `output_value == material + jasa + aux − barang sisa` (WIP di-clear penuh) |
| `INV-MKO-05` | klaim sah: status ∈ registry; `approved` punya penyetuju, nilai & dokumen turunan |
| `INV-MKO-06` | `steps[].contract_id` menunjuk `supplier_contracts` yang ada & bernomor sah |

## 8. Bukti pengujian (sesi 2026-07-26)

| Gate | Hasil |
|---|---|
| `python backend/test_fase_d_makloon_poc.py` | **PASS 69 / FAIL 0** (16 blok tes, self-cleanup) |
| `python scripts/verify_data_integrity.py` | **171 PASS / 0 FAIL / 0 WARN** (termasuk `INV-MKO-01…06`) |
| `bash scripts/gate.sh` | **SEMUA GATE HIJAU** → `memory/GATE_RECEIPT.md` |
| `python scripts/check_nav_map.py` | **PASS** (kedalaman IA 3 ≤ 4) |
| `testing_agent_v3` backend (iter 165) | **98%** — 0 bug kritikal; 1 temuan LOW (RBAC sales) → **diperbaiki** |
| `testing_agent_v3` frontend (iter 166) | **100%** — 0 bug UI, 0 layar putih, 0 console error |

Cakupan POC yang terbukti: kebijakan configurable · kontrak basis tarif bebas (pick/kg/meter/
custom formula) · simulasi tarif auditable · estimasi GSM · order 3 langkah 3 mitra · validasi
rantai & aturan wajib · issue/receive dengan satuan mitra + konversi · **3 tindakan klaim**
(potong bon → tagihan berkurang & jurnal; tagih ganti → piutang klaim; terima catatan → tanpa
jurnal) · HPP berjenjang & rekonsiliasi WIP · mode kontrak `block`/`warn` · registry enum ·
skor mitra · proteksi hapus kontrak (409).

## 9. Perbaikan yang dilakukan pada Phase 3

1. **RBAC sales (temuan testing agent, LOW → diperbaiki).** `plan.md` user story 6 mensyaratkan
   *"warehouse bisa issue/receive; sales hanya view"*, tetapi sales mendapat **403** di
   `/api/makloon-orders`. Ditambahkan `makloon: ["view"]` + `makloon_order: ["view"]` ke role
   `sales` (`backend/permissions_config.py`) — di-merge otomatis oleh
   `bootstrap.sync_permission_modules()` tanpa re-seed. Nav `makloon-orders` kini mencakup
   role `sales`. Tarif/kontrak (`supplier_contract`) **tetap tertutup** untuk sales karena
   data komersial. Terverifikasi: sales GET 200, semua POST (issue/receive/claim/approve/cancel) **403**.
2. **Seed demo Fase D (temuan testing agent: kontrak & klaim kosong).**
   `seed_realistic.py` kini menyeed **3 kontrak mitra** (`seed_makloon_contracts`) —
   tenun basis **kg** dari qty **input** Rp 13.500/kg (susut 4%, toleransi 4%, min charge),
   celup basis **yard** output Rp 2.600 + aux **screen per warna** & **repeat**
   (susut 5%, toleransi 3%), finishing **lumpsum** Rp 1.850.000 (toleransi 2,5%) —
   serta **order rantai 2 langkah** `MKO-00003` (tenun → celup) berbasis kontrak dengan
   langkah 1 diterima 7% di bawah estimasi (**lewat toleransi 4%**) → klaim otomatis terbuka
   lalu **diajukan `potong_bon`** oleh warehouse sehingga layar persetujuan klaim & Skor Mitra
   punya data nyata. Semua invarian tetap 0 FAIL.

## 10. Batasan yang diketahui (bukan bug)

- `POST` dengan **body invalid tanpa header auth** mengembalikan **422** (Pydantic divalidasi
  sebelum dependency auth). Body valid tanpa/tanpa-izin → **401/403** (benar). Pola ini identik
  di seluruh router existing.
- `terima_catatan` sengaja **tidak** membuat jurnal: kerugian sudah terserap ke HPP output saat
  penerimaan (WIP di-clear penuh) — mencegah dobel-hitung & drift akun 1-1300.
- Kontrak `contract_type=purchase` sudah didukung skema & CRUD-nya, tetapi **routing PR/PO
  berbasis kontrak** adalah lingkup **Fase E** (`plan.md` Phase 4–5).
