# AUDIT — Status Nyata MASTER_ROADMAP (EPIC 0–7) · 2026-08-06

> Dipicu permintaan pemilik: *"Audit menyeluruh dulu → susun daftar gap yang AKURAT &
> terkini … cek kembali jangan sampai EPIC 2 & EPIC 5 sudah selesai lalu membuat duplikasi."*
> **Temuan utama: `MASTER_ROADMAP.md` USANG.** Ia bertanda "RENCANA — belum dieksekusi",
> tetapi kode sudah jauh melampauinya. Hampir SELURUH EPIC 0–7 SUDAH terbangun.
> **JANGAN membangun ulang EPIC 2 / EPIC 5 — akan jadi duplikasi.**

## Ringkasan per EPIC (grounded, dengan bukti file/DB)

| EPIC | Status | Bukti |
|---|---|---|
| **0 — IA Hygiene & Scaffold** | ✅ SELESAI | `config/navigationConfig.js` bangun grup **"Segera Hadir"** dari flag `comingSoon`; `ROLE_HOME_REGISTRY` (F5) di `navMeta.js`; config/settings service (`config_registry.py`, `SettingsHub.jsx`). |
| **1 — Role/Sales Home** | ✅ SEBAGIAN BESAR (sisa: Manager Home) | `features/home/SalesHome.jsx` (lengkap: Komisi MTD, target, penagihan, **rincian per-SKU**, tren 6 bln, tanpa HPP) + `AdminHome.jsx`. Izin sales sudah diketatkan (`permissions_config.py` — sales TANPA purchase_order/vendor_bill/input_tax/HPP). **GAP: tak ada `ManagerHome`** — manajer mendarat di `reports` (`ROLE_HOME_REGISTRY.manager.view="reports"`). |
| **2 — Master Kategori + snapshot SO** | ✅ SELESAI (JANGAN DUPLIKASI) | `routers/categories.py` CRUD penuh `product_categories` (+rename-propagation ke produk, product_count, soft-delete). `routers/sales_orders.py:166` → `it["category"]=prod.get("category")` (snapshot). DB: **9/9 SO punya category di SEMUA baris + `base_quantity`/`base_unit`**; **11 kategori** ter-seed. FE: `features/admin/CategoryManager.jsx` + dropdown master di `ProductMasterForm.jsx`. |
| **3 — Costing (WAC) + AR Receipt Ledger** | ✅ SELESAI | `services/costing_service.py` + `routers/costing.py` (`GET /api/costing/wac`, `/wac/{product_id}`). `services/ar_receipt_service.py` + `routers/ar_receipts.py`. |
| **4 — Incentive Engine v2 (per-SKU, margin-aware, on-collection)** | ✅ SELESAI | `services/sales_force_service.py` `compute_commission` dispatcher strategi (`per_sku` default v2 / `achievement_tiered` arsip; mode dari `settings.commission.strategy`). `routers/incentive_rates.py` + `features/crm/IncentiveRatesEditor.jsx`. SalesHome tampilkan rincian per-SKU. |
| **5 — POS E-commerce** | ✅ SELESAI (JANGAN DUPLIKASI) | `features/pos/FacetRail.jsx` (facet), `PosProductCard.jsx`, `PosBestSellers.jsx` (reorder), `CheckoutDrawer.jsx`+`CheckoutItemCard.jsx` (checkout), `CreateCustomerModal.jsx` (buat pelanggan = modal), `RequestSpecialPriceModal.jsx`, varian mobile (`features/pos/mobile/*`). |
| **6 — Process Timeline / Document Hub** | ✅ SELESAI | `services/doc_refs_service.py` + `document_relations_service.py`; blok "Referensi Dokumen"+QR di PDF (G-4); hub `OrderDetailPanel.jsx`; layar "Jejak Dokumen" (`doc-trace`). |
| **7 — Finance & Backlog** | ✅ SEBAGIAN BESAR | `routers/gl.py`, `financial_statements.py`, `budgets.py`, `consolidation.py`, `bank*.py`, `fixed_assets.py`, `closing.py`. Multi-currency: `services/config_currency.py` (`finance.base_currency`, `format_money_with`). Sisa: integrasi SMTP email PO (perlu integration agent), FX rate live. |

## GAP NYATA (yang benar-benar belum / bisa ditingkatkan)
1. **Manager Home (control-tower tim)** — satu-satunya sisa EPIC 1. Manajer belum punya
   landing berisi leaderboard tim, target vs capaian tim, koleksi/penagihan tim, dan
   antrean approval. (Saat ini mendarat di layar Laporan generik.)
2. **EPIC 7 sisa**: email PO via SMTP (butuh integration agent), FX rate multi-currency live.
3. **FASE H (backlog PRD)**:
   * ~~PS-20 (produk eksklusif per sales)~~ — ✅ **SELESAI 2026-08-06** (lihat PRD).
   * PS-17 (divisi sbg aktor R&D) — butuh keputusan bisnis **D-13** dulu.
   * PS-18 (KPI designer + eskalasi SLA) — round-SLA sudah ada; laporan KPI designer belum.
4. Polish minor UX bila ditemukan (bukan bug P0/P1 — BUG_BACKLOG #1–#7 semuanya sudah FIXED).

## Sesi ini (sudah TERKIRIM sebelum audit)
- **P2** — Nota Retur/Kredit Antar-PT cetak + e-sign (`interco_return` di DOC_REGISTRY).
  POC 21/21 · integritas 233/0/0 · testing agent BE 31/31 + FE lulus.
- Poles emoji ⚠️ → ikon lucide `AlertTriangle` di `POCreateForm.jsx`.
