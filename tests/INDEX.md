# 🧭 INDEX SKRIP UJI & POC — Kain Nusantara

> Dibuat **2026-07-26** saat efisiensi guardrail. Menjawab masalah nyata:
> repo punya **151 skrip uji / POC (62,010 baris)** — lebih besar dari
> banyak aplikasi utuh — tanpa satu pun daftar isi. Akibatnya agen/developer baru
> tidak tahu skrip mana yang masih relevan, mana milik fase mana, dan mana yang
> sudah digantikan. Berkas ini adalah daftar isinya.
>
> **Tidak ada skrip yang dipindahkan/dihapus** (keputusan pemilik: index dulu).
>
> ## Cara memakai
> | Kebutuhan | Perintah |
> |---|---|
> | Cek cepat sebelum commit (statik, ~1 detik) | `bash scripts/gate.sh --quick` |
> | Verifikasi penuh (14 gate, ~16 detik) | `bash scripts/gate.sh` |
> | Verifikasi penuh + POC fase kunci | `bash scripts/gate.sh --full` |
> | Uji satu fase | `python backend/test_<fase>_poc.py` |
>
> **Aturan repo:** POC ditulis sebagai **satu skrip mandiri, self-cleanup, harus
> HIJAU 100%** sebelum wiring UI. POC yang meninggalkan data di DB dianggap CACAT
> (lihat `INV-GATE-01` di `scripts/gate_residue.py`).
>
> ## Fase mana yang HIDUP?
> POC fase yang masih dipakai sebagai gerbang `--full`:
> `backend/test_g0_config_poc.py` (G-0, **115/0**) ·
> `backend/test_g1_amendment_poc.py` (G-1, **77/0**) ·
> `backend/test_g4_refs_poc.py` (G-4, **49/0**) ·
> `backend/test_g2_payment_poc.py` (G-2, **53/0**) ·
> `backend/test_g3_variance_poc.py` (G-3, **70/0**) ·
> `backend/test_fase_f1_receiving_uom_poc.py` (F-1, **47/0**) ·
> `backend/test_fase_f_rnd_poc.py` (F R&D) ·
> `backend/test_fase_f_us3_us11_us12_poc.py` (F R&D — US3/US11/US12, **42/0**) ·
> `backend/test_f0c_scoping_leak_poc.py` (F0-C isolasi lintas-PT, **27/0**) ·
> `backend/test_fase_d_makloon_poc.py` (D, **69/0**) ·
> `backend/test_g7_contrabon_poc.py` (G-7 kontrabon, **120/0**) ·
> `backend/test_g8_bank_poc.py` (G-8 rekonsiliasi bank) ·
> `backend/test_g9_case_poc.py` (G-9 pusat kasus keuangan) ·
> `backend/tests/test_g6_poc.py` (**G-6 antar entitas — pytest, 21/0**: 11 user story +
> jembatan gudang + pembatalan ber-alasan + bukti-merah INV-IC-01..06; memakai
> `poc_stock_guard` karena memindahkan kepemilikan roll).
> Sisanya = arsip bukti fase yang sudah selesai — **jangan dihapus** (itu bukti
> verifikasi historis), tetapi tidak perlu dijalankan rutin.
>
> ### Alat pendukung POC (bukan skrip uji)
> | Berkas | Guna |
> |---|---|
> | `backend/poc_stock_guard.py` | snapshot→restore **EKSAK** koleksi stok (`inventory_rolls`/`balances`/`movements`/`lots`) supaya POC tidak menggeser stok demo. Wajib dipakai POC yang **mengonfirmasi Sales Order** (konfirmasi SO memotong & mereservasi roll). Lihat BUG_REGISTRY **POC-RESIDU-01**. |
> | `scripts/gate_residue.py` | INV-GATE-01. Dijalankan **dua kali** di `--full`: sekitar blok guardrail runtime, dan sekitar blok FASE POC (`KN_RESIDUE_FILE=/tmp/kn_gate_residue_poc.json --ignore-trails`). |

---

## SESI 2026-08-15 · AKSES & UI/UX PER PERAN + UTANG MIGRASI (repo `skskududu/KN`)  ·  2 skrip

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_core_role_access_poc.py` | ~300 | **POC F-2** — akses & UI/UX 6 peran, **43/43**. G1 izin baca yang hilang sudah diberikan (finance→`/ar/aging` & `/suppliers`, warehouse→`/suppliers`, manager→`/users`) · G2 pagar TIDAK ikut longgar (sales/warehouse tetap 403 di aging; `POST /suppliers` tetap 403; finance tetap 403 di `/vendor-bills`) · G3 KPI beranda == rincian == hitung-ulang MongoDB (INV-HOME-01) · G4 tombol lahir dari izin (`penalty.issue`, INV-ROLE-01) · G6 `GET /approvals/backlog` satu sumber + izin + isolasi entitas + koleksi antrean harus ADA · **G5 BUKTI-MERAH**: mencabut izin dari matriks yang BERLAKU harus membuat POC memerah, lalu matriks dipulihkan. `run_with_restore` (nol residu). |
| `backend` | `test_core_group_cash_migration_poc.py` | ~250 | **POC F-1b** — utang migrasi (i) kas tingkat grup → per badan usaha (E7e), **38/38**. Membuat ULANG keadaan warisan (1 rekening "Kas Besar Grup" + 13 transaksi · 4 lapis bukti + 2 baris tak terbuktikan), menjalankan `scripts/migrate_e7_group_cash.py` **sungguhan** sebagai proses terpisah: `--report` read-only · 4 lapis bukti benar · baris tanpa bukti TIDAK ditebak (ditandai + kasus `salah_entitas`) · cermin rekening per badan usaha · rekening grup tidak dihapus · idempotent · setelah keputusan orang rekening grup dinonaktifkan. **Menemukan cacat nyata di alatnya** (baris hasil keputusan orang tetap menunjuk rekening grup → sapuan kedua ditambahkan). Snapshot/restore eksplisit 6 koleksi. |

---

## FASE F · R&D & Desain (Spesifikasi · Labdip/Proofing · lifecycle produk)  ·  2 skrip

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_fase_f_rnd_poc.py` | ~1100 | POC FASE F — spesifikasi → labdip/proofing ber-bukti → skor → keputusan pemenang → kontrak harga; gating lifecycle produk; bukti-merah 6 invarian `INV-RND-*`. |
| `backend` | `test_fase_f_us3_us11_us12_poc.py` | 350 | POC penutup FASE F — **US3** sales ditolak menjual produk `disetujui` (pesan menuntun alur R&D) · **US11** gudang melihat mutasi *Ambil Bahan Sample (R&D)* dengan label Indonesia · **US12** jejak dokumen kontrak → sample → spesifikasi. Termasuk 3 cek **nol residu** + `poc_stock_guard`. |
| `backend` | `backend_test_fase_f_closure.py` | 414 | Sweep API penutupan FASE F (55 cek): field `source_document_label`, penyaring `movement_type`, gating SO, jejak dokumen, nomor dokumen deterministik, 19 endpoint utama. Artefak `testing_agent_v3` iter_184. |

---


## G-3 · Selisih Pembayaran (lebih & kurang bayar)  ·  1 skrip

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_g3_variance_poc.py` | 886 | POC FASE G-3 — SELISIH PEMBAYARAN: 13 skenario (takar selisih jujur · pembulatan otomatis · antrean keputusan · sisa tetap piutang / ubah jadwal / hapus sisa · deposit / alokasi / refund · alokasi per baris jadwal · sakelar admin · jalur AP supplier · void membalik keputusan · Jejak Dokumen) + **bukti-merah 4 invarian** + self-cleanup nol residu. |

## G-0 · Fondasi Konfigurasi  ·  1 skrip · 763 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_g0_config_poc.py` | 763 | POC FASE G-0 — FONDASI KONFIGURASI (single script, self-cleanup). |

## F-1 · Penerimaan Satuan Supplier  ·  2 skrip · 870 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_fase_f1_receiving_uom_poc.py` | 612 | POC ISOLASI — FASE F-1: PENERIMAAN BERBASIS **SATUAN SUPPLIER** |
| `root` | `test_fase_f1_backend.py` | 258 | Run a single API test |

## E · Sourcing Kontrak & Supplier  ·  8 skrip · 3,926 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_fase_e_contracts_poc.py` | 795 | POC ISOLASI — FASE E: SOURCING BERBASIS KONTRAK (PS-06 · E-01/E-02/E-03) |
| `root` | `backend_rfq_test.py` | 710 | Print test summary |
| `root` | `backend_test_fase_e.py` | 714 | Regression tests - ensure existing endpoints still work |
| `root` | `test_rfq_poc.py` | 215 | POC ISOLASI — P1: RFQ / Quotation (sourcing) — Phase 6.1 |
| `root` | `test_vendor_bill_backend.py` | 418 | Vendor Bill + 3-Way Matching Backend Test (Fase 5.2 — P0-2) |
| `root` | `test_vendor_bill_poc.py` | 138 | POC test — Fase 5.2 Vendor Bill + 3-Way Matching (backend core validation). |
| `root` | `vendor_bill_gl_comprehensive_test.py` | 466 | Comprehensive Vendor Bill GL Posting Test |
| `root` | `vendor_bill_gl_test.py` | 470 | Vendor Bill GL Posting Test - Verifikasi bug fix: missing gl_service import |

## D · Makloon Rantai Proses  ·  5 skrip · 2,163 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_fase_d_makloon_poc.py` | 740 | POC ISOLASI — FASE D: MAKLOON RANTAI PROSES (PS-03/PS-04/PS-08/PS-11) |
| `backend` | `test_makloon_core_poc.py` | 207 | POC (Fase M2 core) — WIP-at-vendor (Makloon) end-to-end tanpa UI. |
| `backend` | `test_makloon_order_api.py` | 251 | API test (Fase M3) — Makloon Orders end-to-end via HTTP. |
| `root` | `backend_fase_d_test.py` | 460 | Main test runner |
| `root` | `backend_test_makloon.py` | 505 | Run all makloon order tests |

## C · Lot Kelas Satu  ·  5 skrip · 2,965 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_dyelot.py` | 469 | Run all tests |
| `backend` | `backend_test_fase_c_lot.py` | 938 | Get entity, product, warehouse references |
| `backend` | `test_fase_c_lot_poc.py` | 613 | POC ISOLASI — FASE C: LOT KELAS SATU (`inventory_lots`) · D-10 / D-26 / D-27 |
| `backend` | `test_roll_ssot.py` | 657 | Regression — Inter-company transfer still works |
| `root` | `test_dyelot_poc.py` | 288 | Buat wms_task inbound siap-complete (status qc_check). |

## B · Konversi Satuan (UoM)  ·  4 skrip · 1,725 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_fase_b.py` | 335 | Backend test for Warehouse Fase B: Location/Putaway (B1) + Reorder/ROP (B2). |
| `backend` | `backend_test_fase_b_uom.py` | 688 | Test that non-admin roles cannot modify rules/settings |
| `backend` | `test_fase_b_uom_poc.py` | 444 | Nonaktifkan aturan sisa uji sebelumnya agar POC bisa dijalankan berulang. |
| `root` | `backend_test_f1_uom.py` | 258 | Run all F1 UOM tests |

## A/0 · Fondasi Domain & Multi-Entitas  ·  6 skrip · 2,608 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_f0a_entity_context.py` | 539 | Backend Test: F0-A Entity Identity & Context (Multi-Entity Foundation) |
| `backend` | `test_fase_a_poc.py` | 414 | test_fase_a_poc.py — POC HTTP TUNGGAL untuk **Fase A: Fondasi Domain Tekstil**. |
| `root` | `backend_test_f0e.py` | 563 | Backend API Testing for F0-E Multi-Entity Finance Phase |
| `root` | `backend_test_fase0.py` | 860 | Backend API Testing for Kain Nusantara FASE 0: Multi-Entity + Notification Center |
| `root` | `test_f0a_entity_identity_poc.py` | 94 | POC F0-A — Entity Identity & Context (Multi-Entity foundation). |
| `root` | `test_f6_entity_tax_poc.py` | 138 | POC FASE 6 — PPN/Faktur per-entitas + Multi-entitas user + Rekening per-entitas. |

## Phase 11 · R6.6 Ringkasan & Eskalasi  ·  2 skrip · 991 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `backend_test_r6_6.py` | 568 | Test that notifications have required fields for filtering |
| `root` | `test_r6_6_digest_escalation_poc.py` | 423 | POC R6.6 — Ringkasan Harian (Digest) + Eskalasi Bertingkat + Filter Notifikasi. |

## Phase 10 · R6.5 Scheduler & WhatsApp  ·  1 skrip · 324 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `test_r6_5_scheduler_poc.py` | 324 | POC R6.5 — Scheduler (APScheduler) + Notifikasi + kanal WhatsApp (Outbox). |

## Phase 9 · R6.4 Produksi In-House  ·  2 skrip · 906 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `backend_test_production.py` | 644 | Run all production tests |
| `root` | `test_r6_4_production_poc.py` | 262 | Cari 1 gudang dgn >=2 produk berstok, + 1 produk output berbeda. |

## Phase 8 · R6.3 Budget Control  ·  2 skrip · 1,069 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_r6_3_budget.py` | 695 | R6.3 Budget Control — Comprehensive Backend API Test |
| `root` | `test_r6_3_budget_poc.py` | 374 | POC R6.3 — Budget Control penuh (Anggaran vs Komitmen vs Realisasi + enforcement). |

## Phase 7 · R6.2 Aset Tetap  ·  3 skrip · 1,286 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `backend_test_r6_2_fixed_assets.py` | 954 | R6.2 — Fixed Assets & Depreciation Backend Testing |
| `root` | `backend_test_r6_2_gl_verification.py` | 154 | R6.2 — GL Balance & JE Verification |
| `root` | `test_r6_2_fixed_asset_poc.py` | 178 | R6.2 — Fixed Assets & Depresiasi (straight-line) + disposal gain/loss — POC. |

## Phase 6 · R6.1 Rekonsiliasi Bank  ·  3 skrip · 770 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_epic7b_bank.py` | 530 | Run all tests |
| `root` | `test_epic7b_bank_poc.py` | 102 | POC EPIC7-B — Kas & Bank: akun, saldo, ledger, reconcile, RBAC. |
| `root` | `test_r6_1_bank_recon_poc.py` | 138 | R6.1 — Bank Reconciliation otomatis — POC. |

## Phase 5 · R5 Retur/Margin/Write-off  ·  13 skrip · 3,905 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_r5_4b.py` | 230 | R5.4b Backend API Test - Purchase Return Reversal & Write-off Reversal |
| `backend` | `test_store_credit.py` | 305 | Run all store credit tests |
| `backend` | `test_store_credit_comprehensive.py` | 475 | Test POST /api/store-credit/adjust (negative) |
| `root` | `backend_test_r5_reversal.py` | 626 | R5.4 Reversals/Corrections Backend API Testing |
| `root` | `backend_test_r5_writeoff.py` | 440 | R5.1 — Inventory Write-off GL (scrap & goods) — Comprehensive Backend Test. |
| `root` | `test_r5_4b_poc.py` | 337 | R5.4b — Reversal Retur Beli (Nota Debit) + Reversal Write-off (un-scrap) — POC. |
| `root` | `test_r5_5_landed_valuation_poc.py` | 132 | R5.5 — Landed-cost-aware valuation — POC (in-process, deterministic). |
| `root` | `test_r5_6_margin_poc.py` | 127 | R5.6 — Laporan Margin per-PT + pecahan Landed Cost — POC. |
| `root` | `test_r5_backend.py` | 286 | R5.3 Backend API Testing - Cash Refund + GL Separation |
| `root` | `test_r5_cash_refund_poc.py` | 232 | R5.3 — Cash refund + pemisahan GL (refund-kas vs ap_credit) — POC. |
| `root` | `test_r5_reversal_poc.py` | 279 | R5.4 — Reversals / Koreksi — POC. |
| `root` | `test_r5_store_credit_poc.py` | 222 | R5.2 — Store Credit (Saldo Kredit Pelanggan) ledger — POC. |
| `root` | `test_r5_writeoff_poc.py` | 214 | R5.1 — Inventory Write-off GL (scrap & goods) — POC. |

## R0 · Return Policy Engine  ·  2 skrip · 997 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `r0_return_policy_test.py` | 802 | Run all R0 Return Policy Engine tests |
| `root` | `test_r0_poc.py` | 195 | R0 — Return Policy Engine — POC/integration test (backend, via HTTP API). |

## R1 · Retur Jual  ·  3 skrip · 1,568 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_sales_returns.py` | 571 | Run all tests in sequence |
| `backend` | `test_sales_returns_r1.py` | 831 | Test partial settle (per-item decisions) |
| `root` | `test_r1_poc.py` | 166 | R1 — Sales Return State Machine + 4 Outcomes + Partial — POC/integration test. |

## R2  ·  2 skrip · 775 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `backend_test_r2.py` | 636 | Run all R2 backend tests |
| `root` | `test_r2_poc.py` | 139 | R2 — Unified Inspect (4-point) + Quarantine — POC/integration test. |

## R3  ·  2 skrip · 589 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `backend_test_r3.py` | 430 | R3 — Backend API Testing for Inventory ownership/location + regrade + cross-entity transfe |
| `root` | `test_r3_poc.py` | 159 | R3 — Inventory ownership/location + regrade + cross-entity transfer — POC. |

## R4  ·  2 skrip · 933 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `backend_test_r4.py` | 716 | R4 — Comprehensive Backend Testing for Retur & Refunds with Supplier RMA lifecycle. |
| `root` | `test_r4_poc.py` | 217 | R4 — Retur Jual↔Beli link + Supplier RMA lifecycle + goods_back/regrade + policy impor — P |

## EPIC 7 · Finance/GL/AR  ·  4 skrip · 924 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `backend_test_epic7c.py` | 432 | Comprehensive Backend Test for EPIC 7-C: Chart of Accounts + General Ledger |
| `root` | `test_ar_aging_backend.py` | 237 | Check if two floats are approximately equal |
| `root` | `test_epic7a_ar_aging_poc.py` | 98 | POC EPIC7-A — AR / Piutang Aging report + denda estimate + RBAC + drill-down. |
| `root` | `test_epic7c_gl_poc.py` | 157 | POC EPIC7-C — Chart of Accounts + General Ledger. |

## EPIC 0-6 · IA/Role/Kategori/Costing/Insentif  ·  6 skrip · 738 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `root` | `test_epic1_poc.py` | 123 | EPIC 1 POC — role tightening (sales) + home endpoints (sales/admin/manager). |
| `root` | `test_epic2_categories_poc.py` | 154 | EPIC2 POC — Master Kategori Produk + Snapshot SO line. |
| `root` | `test_epic3_costing_ar_poc.py` | 150 | EPIC3 POC — Costing (WAC) + AR Receipt / Payment Application. |
| `root` | `test_epic4_incentive_poc.py` | 166 | EPIC4 POC — Incentive Engine v2 (per-SKU, 3 faktor, margin-aware, on-collection). |
| `root` | `test_epic5_pos_poc.py` | 64 | POC EPIC5 — endpoint reorder "sering dibeli customer ini" + RBAC. |
| `root` | `test_epic6_relations_poc.py` | 81 | POC EPIC6 — Document Relations / Process Timeline + deep-link metadata + RBAC. |

## Purchasing  ·  10 skrip · 4,745 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_landed_cost.py` | 402 | Cleanup test data |
| `backend` | `fase3_purchasing_test.py` | 1118 | Backend API Testing for Kain Nusantara - Fase 3 Purchasing/Procurement |
| `root` | `backend_blanket_test.py` | 386 | Backend API Testing for Blanket/Contract PO Feature (P2) |
| `root` | `backend_test_fase3_purchasing.py` | 1092 | Backend API Testing for Kain Nusantara - Fase 3 Purchasing Module RE-TEST |
| `root` | `backend_test_purchase_returns.py` | 373 | Run all backend tests |
| `root` | `test_blanket_po_poc.py` | 275 | POC P2 — Blanket / Contract PO (call-off). |
| `root` | `test_input_tax_poc.py` | 216 | POC ISOLASI — P0-3: Faktur Pajak Masukan (Input VAT) — Phase 5.5 |
| `root` | `test_landed_cost_poc.py` | 247 | POC ISOLASI — P0-5: Landed Cost → alokasi HPP roll (Phase 5.4) |
| `root` | `test_po_amendment.py` | 432 | Backend Testing for Phase 7.2 — PO Amendment / Version History |
| `root` | `test_po_amendment_poc.py` | 204 | POC Phase 7.2 — PO Amendment / Version History. |

## Penjualan & Fulfillment  ·  5 skrip · 2,041 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_f3_aftersales_smoke.py` | 96 | F3 aftersales smoke — credit note + GL reversal on a REAL seeded SO (with inventory/cost). |
| `root` | `backend_test_autofulfill.py` | 381 | Backend API Testing - Auto-fulfill Backorder Flow (Sub-fase 1.6) |
| `root` | `backend_test_backorder.py` | 546 | Backend API Testing for Sub-fase 1.6 - Backorder Lifecycle |
| `root` | `backend_test_consolidation.py` | 602 | Backend API Testing for P7 Consolidation Module (FINANCE) |
| `root` | `backend_test_sales_revamp.py` | 416 | Print test summary |

## QC & Presisi  ·  5 skrip · 1,512 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_qc.py` | 546 | Run all QC tests |
| `backend` | `backend_test_qc_4point.py` | 438 | Run all tests in sequence |
| `root` | `test_catch_weight_poc.py` | 210 | POC Fase 8 — Catch-weight / Dual-UoM pembelian. |
| `root` | `test_precision_return_poc.py` | 184 | Self-contained POC — Retur Beli PRESISI per roll/lot (S#2026-07-21 continuation). |
| `root` | `test_qc_inspection_poc.py` | 134 | POC ISOLASI — P1: QC 4-Point Inspection + GSM/Lebar aktual — Phase 6.2 |

## RFID  ·  2 skrip · 867 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `test_rfid_comprehensive.py` | 713 | Comprehensive RFID Backend API Testing (Fase 5) |
| `root` | `test_rfid_poc.py` | 154 | POC — RFID Simulator (Fase 5). Verifikasi end-to-end semua flow + SSOT-safe. |

## CRM & Omnichannel  ·  5 skrip · 2,266 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test_crm_enforcements.py` | 517 | Backend test for KN_17 CRM Enforcements + Incentive/Tier Schema UI Editor. |
| `root` | `backend_test_crm.py` | 708 | Run all tests |
| `root` | `backend_test_crm_omnichannel.py` | 585 | Backend API Testing for CRM Omnichannel Module |
| `root` | `test_crm_enforce_poc.py` | 195 | POC — CRM enforcement lanjutan (sesi #047). |
| `root` | `test_crm_poc.py` | 261 | POC — CRM / Sales Force (KN_17 CRM-lite). |

## HRD  ·  1 skrip · 283 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `hr_analytics_test.py` | 283 | Run all backend tests |

## Lintas-modul & Platform  ·  45 skrip · 19,501 baris

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend` | `backend_test.py` | 859 | Run all tests in sequence |
| `backend` | `backend_test_18.py` | 500 | Run all Sub-fase 1.8 tests |
| `backend` | `backend_test_360_panels.py` | 358 | Backend test for 360° detail panels (Supplier, Makloon, Employee). |
| `backend` | `backend_test_bi_finance.py` | 304 | Backend test for BI Keuangan (Financial BI Dashboard) module. |
| `backend` | `backend_test_depth1.py` | 866 | Run all Depth #1 tests |
| `backend` | `backend_test_depth3_enhancements.py` | 447 | Backend API Testing for Depth #3 Enhancements |
| `backend` | `backend_test_equity_changes.py` | 348 | Run all backend tests |
| `backend` | `backend_test_f3_mto_rma.py` | 822 | Run all tests in sequence |
| `backend` | `backend_test_fase4.py` | 459 | Backend Testing for FASE 4: SO Status 2-level SSOT (STAGE + SUB-STATUS) |
| `backend` | `backend_test_finance_analytics.py` | 449 | Run all tests. |
| `backend` | `backend_test_h1.py` | 590 | Print test summary |
| `backend` | `backend_test_m0_color.py` | 424 | M0 — Color Library & Product Stage Backend Test |
| `backend` | `backend_test_pdf_fase3.py` | 444 | Backend Test — PDF Template Designer (Fase 3) |
| `backend` | `backend_test_phase2_forms.py` | 737 | FASE 2 — HTTP API Testing (Digitalisasi Formulir Sukacita). |
| `backend` | `backend_test_po_timeline_approval.py` | 359 | Backend test for PO Timeline & Notification Approve features. |
| `backend` | `backend_test_r1_05_06.py` | 436 | Backend API tests for R1-05 and R1-06 P0 bug fixes. |
| `backend` | `backend_test_tax_invoices.py` | 294 | Test GET /api/tax-invoices/{fkt_id}/document |
| `backend` | `test_f3_smoke.py` | 97 | F3 smoke test — Special Order MTO: approve→auto-SKU, manual create-sku, convert-to-SO. |
| `backend` | `test_forms_poc.py` | 235 | FASE 1 — POC INTI (Digitalisasi Formulir Sukacita). |
| `backend` | `test_ps21_poc.py` | 412 | Fixture POC: batalkan PR repeat/restock TERBUKA milik order uji lewat API |
| `root` | `backend_closing_test.py` | 495 | Backend API Testing for Period Closing Module (FINANCE - Tutup Buku) |
| `root` | `backend_esign_test.py` | 417 | Run all E-Sign backend tests |
| `root` | `backend_pagination_test.py` | 324 | P2 Backend Pagination Testing — OPT-IN Contract Verification |
| `root` | `backend_regression_test.py` | 99 | Test all critical GET endpoints |
| `root` | `backend_test.py` | 738 | Print test summary |
| `root` | `backend_test_depth2_pr.py` | 609 | Run all tests |
| `root` | `backend_test_fase1b.py` | 793 | Backend API Testing for Kain Nusantara ERP/WMS - Fase 1B Configuration Consumption |
| `root` | `backend_test_fase3.py` | 231 | FASE 3 Backend API Testing — Description & Image per-variant |
| `root` | `backend_test_gelombang3.py` | 558 | Backend API Testing for Gelombang 3 Finance Features (F-7, F-8, F-9) |
| `root` | `backend_test_h2.py` | 486 | Backend Testing for FASE H2: HRD Live Tracking + Visits (Kunjungan) |
| `root` | `backend_test_h5.py` | 516 | Backend Testing for Kain Nusantara FASE H5 |
| `root` | `backend_test_interco.py` | 729 | Backend API Testing for Sub-fase 1.5: Inter-Company Transfer Flow |
| `root` | `backend_test_phase05.py` | 734 | Backend API Testing for Phase 0.5 - Roll-as-SSOT Inventory Ownership |
| `root` | `backend_test_pret_iter143.py` | 370 | Run all backend tests |
| `root` | `backend_test_ps21.py` | 223 | Run all PS-21 backend tests |
| `root` | `backend_test_wa.py` | 460 | Run all WhatsApp backend tests |
| `root` | `test_audit_fixes_poc.py` | 190 | POC test — verifikasi fix audit EPIC2-4 (P0-1, P1-2, P2-3..P2-6, P3-7, P3-8). |
| `root` | `test_depth3_settings_notifications.py` | 472 | Backend API Testing for Depth #3 Enhancements: |
| `root` | `test_f2b_backend.py` | 667 | F2b Backend Testing: Future-aware ATP + Pending SO + Delivery Hold + Regressions |
| `root` | `test_f2b_poc.py` | 158 | F2b POC — Future-aware ATP + Pending SO + Delivery Hold (ISOLATED). |
| `root` | `test_f5_approval_poc.py` | 190 | POC FASE 5 — Alur Approval Terpadu (pending_approvals SSOT) + RBAC + storage LOKAL. |
| `root` | `test_finance_p0p1_poc.py` | 87 | POC — Finance P0/P1 endpoints (cash-flow, profitability, forecast, tower, budgets). |
| `root` | `test_multilevel_approval_poc.py` | 159 | POC ISOLASI — P2: Multi-Level Sequential Approval (PO) — Phase 7.1 |
| `root` | `test_number_series_poc.py` | 97 | POC P0-A — Number-series deletion-safe (max-based, RC-5). |
| `root` | `test_price_approvals_backend.py` | 259 | Quick backend API test for Price Approvals endpoints |

---

**Total: 151 skrip · 62,010 baris.** Regenerasi index: lihat riwayat perintah di `scripts/INDEX.md`.


---

## FASE G-6 · Transaksi Antar Entitas (jual-beli antar-PT)  ·  1 skrip

| Lokasi | Skrip | Baris | Ringkas |
|---|---|---:|---|
| `backend/tests` | `test_g6_poc.py` | ~800 | POC FASE G-6 (**pytest**, jalankan `cd /app/backend && python -m pytest tests/test_g6_poc.py -q` → **21/0**). Menutup 11 user story: harga internal dari kontrak · dokumen kembar 2 buku · saldo pasangan PT · settlement/netting · eliminasi unrealized profit OTOMATIS (termasuk penyesuaian sesudah lunas) · **jembatan gudang** (tanpa jurnal at-cost dobel, roll pembeli dinilai ulang, GL 1-1300 == subledger) · penolakan "Tandai Diterima" tanpa tugas gudang · pembatalan ber-alasan yang MEMBALIK jurnal · ambang persetujuan · isolasi lintas-PT · **bukti-merah INV-IC-01..06** (menyuntik pelanggaran → invarian wajib memerah → pulihkan). Memulihkan stok EKSAK di akhir (`poc_stock_guard`) sehingga nol residu. |


### FASE G-6b — `backend/tests/test_g6b_poc.py` (**pytest, 15/0**)
`cd /app/backend && python -m pytest tests/test_g6b_poc.py -q` → **15 PASS / 0 FAIL**.
Menutup 4 lanjutan Antar Entitas: **faktur pajak internal** berpasangan (keluaran
penjual == masukan pembeli, ikut rekap `vat_summary` dua PT, tidak bisa dobel,
pengganti & batal wajib ber-alasan, jalur pengganti umum ditolak dengan kalimat
menuntun) · **retur antar-PT** (penjaga "belum berpindah → pakai Batalkan", batas
jumlah, alasan wajib, **dual-control pembuat ≠ penyetuju**, draf tanpa jurnal, 4 blok
jurnal seimbang, roll dinilai ulang ke harga perolehan asli) · **pengingat
settlement** (umur dari aktivitas nyata, notifikasi NYATA, dedupe, saldo nol ditolak,
job terdaftar) · **rapor margin grup** (identitas margin, eliminasi == margin belum
terealisasi, retur lepas dari hitungan) · **bukti-merah INV-IC-03/07/08** ·
RBAC sales 403 · nol residu.
**Jangan** jalankan bersama `test_g6_poc.py` dalam satu perintah pytest (xdist
paralel → blok bersih-bersih saling menimpa); `gate.sh` memanggil keduanya terpisah.
