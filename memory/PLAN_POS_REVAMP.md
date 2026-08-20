# PLAN — POS & Order SSOT Revamp (Sesi Lanjutan #057)

> Status: **DRAFT untuk review owner** · Dibuat: 23 Jun 2026 · Basis: review mendalam 15 poin temuan owner + performa + navigasi.
> Aturan main proyek tetap: **kode menang atas prosa**; tiap fase ditutup verifikasi gate + testing agent; perubahan data harus **additive + backfill idempotent**.

---

## 0. Ringkasan
Revamp modul POS + Sales Order berbasis 15 temuan owner. Mencakup: perbaikan performa & navigasi, penyederhanaan UI POS, **UoM SSOT (satuan dari master + roll-count)**, **redesign status SO (2-level SSOT)**, **penyatuan alur approval (special price + over-credit + nilai) anti double-logic**, **PPN/Faktur per-entitas**, **multi-entitas untuk sales + rekening per-entitas**, dan fitur baru **Catalog Model**.

---

## 1. KEPUTUSAN OWNER (LOCKED)
1. **UoM SSOT:** 1 produk = 1 `base_unit` untuk SEMUA roll-nya; tiap roll beda **panjang**, bukan beda satuan. POS **tidak** memilih satuan. Inventory & POS tampil **"X roll / Y {base_unit}"**. (kg hanya untuk catch-weight yang sudah ada).
2. **PPN & Faktur:** PPN mengikuti **entitas** (`default_tax_mode`); tambah toggle **"minta Faktur Pajak"** per order; entitas **bisa diganti di checkout**; UI memperjelas **"Anda di entitas X sebagai role Y"**.
3. **Multi-entitas sales:** sales bisa di-assign >1 entitas (`allowed_entity_ids`); **rekening per-entitas** (koleksi `bank_accounts` sudah ada) — siapkan slot untuk Finance lanjutan.
4. **Special price & over-credit = aksi SETELAH buat SO** (di **detail SO**, bukan di checkout). Wajib **alasan + lampiran bukti**. Approver = manager/admin.
5. **Over-credit:** SO **tetap tersimpan** + tombol **"Minta Approval Kredit"** (membawa data order) — **bukan** diblokir 409.
6. **RBAC:** SALES hanya **BUAT SO + unggah bukti/validasi**; **tidak** approve/confirm/proses. Admin/Manager yang approve; selanjutnya progres **otomatis oleh sistem**.
7. **Validasi admin:** setiap SO divalidasi/di-approve admin sebelum **Confirmed** (diatur `approval_rules`, configurable; default: wajib).
8. **Catalog Model:** hanya **referensi** (tidak dijual, tidak ada stok).

---

## 2. MODEL STATUS SO (SSOT) — FINAL

### 2.1 Dua level
- **STAGE (timeline induk, linear):** `Reserved → Approved → Confirmed → Picked → Shipped → Delivered` (+ `Cancelled`).
- **SUB-STATUS (anak, kontekstual, boleh >1):** alasan "kenapa berhenti di sini".

### 2.2 Definisi stage + sub-status
| Stage | Arti | Sub-status yang mungkin |
|---|---|---|
| **Reserved** | SO dibuat, stok dipegang, **belum disahkan** | `menunggu_validasi`, `menunggu_approval_harga`, `menunggu_approval_kredit`, `menunggu_approval_nilai`, `siap_disahkan` |
| **Approved** | Sudah di-ACC admin; **komersial final**. Jika **barang belum masuk gudang (backorder) → BERHENTI di sini** | `menunggu_stok` (backorder), `siap_confirm` (stok siap) |
| **Confirmed (Keep)** | Barang **siap di gudang**, di-commit, task outbound dibuat | `siap_pick`, `sedang_pick` |
| **Picked (Ready)** | Barang sudah diambil gudang | `sebagian_dipick` |
| **Shipped** | Barang dikirim | `sebagian_dikirim` |
| **Delivered (Done)** | Diterima customer; selesai | — |
| **Cancelled** | Dibatalkan; reservasi/komitmen dilepas | — |

> Perubahan kunci dari diskusi: **`menunggu_stok` ada di stage APPROVED** (bukan Confirmed). Order yang sudah di-ACC tapi barang belum datang berhenti di Approved; naik ke Confirmed hanya saat stok benar-benar siap di gudang.

### 2.3 Pemetaan migrasi (status lama → baru, additive + backfill idempotent)
- `waiting_approval` → **Reserved** + `menunggu_approval_*`
- `reserved` (pra-approval) → **Reserved** + (`menunggu_validasi` atau `siap_disahkan`)
- `waiting_stock` → bila SO sudah di-approve: **Approved** + `menunggu_stok`; bila belum: **Reserved** + tanda backorder
- `approved` → **Approved** + (`siap_confirm`/`menunggu_stok`)
- `confirmed` → **Confirmed**
- `partially_picked` → **Picked** + `sebagian_dipick`
- `picked` → **Picked**
- `partially_shipped` → **Shipped** + `sebagian_dikirim`
- `shipped` → **Shipped**
- `done` → **Delivered**
- `cancelled` → **Cancelled**

### 2.4 Model approval terpadu (anti "double-logic")
Ganti 3 mekanisme paralel (approval_rules / credit_overrides / price_approvals yang saling menimpa status) dengan **1 SSOT di SO**:
```
so.pending_approvals: [
  { type: "nilai" | "kredit" | "special_price",
    required_role, status: "pending"|"approved"|"rejected",
    requested_by, decided_by, reason, evidence_url, ref_id, order_snapshot }
]
```
Aturan: **SO tidak naik ke Approved sampai SEMUA item `pending_approvals` = approved.** Koleksi `credit_overrides`/`price_approvals` tetap dipakai sebagai detail tapi **statusnya direferensikan** lewat daftar ini (1 sumber kebenaran). "Pusat Persetujuan" membaca daftar ini + menampilkan konteks order.

---

## 3. RISIKO KONFLIK DATA & MITIGASI
1. **Migrasi status SO** → skrip backfill idempotent (`scripts/migrate_so_status.py`) + gate verifikasi; jangan hapus field lama, tambahkan `stage`+`sub_status` dulu lalu deprecate.
2. **Triple-approval** → satukan ke `pending_approvals` (lihat §2.4); satu transisi `recompute_approval_gate()`.
3. **Special price pending** → simpan `unit_price_normal` + `unit_price_requested`; SO tak boleh maju sampai approved; tolak → revert. Ubah `get_effective_special_price` agar boleh state pending.
4. **Ganti entitas di checkout** → reset & re-preview ATP/harga/PPN/kredit; reservasi roll hanya saat create terhadap entitas final.
5. **UoM lock** → dukung tampilan order lama (unit non-base); `roll_count` field baru additive + backfill `rebuild_balance`.
6. **Multi-entitas sales** → insentif ikut entitas SO, payroll ikut `home_entity_id`; penomoran SO per-entitas (sudah ada).

---

## 4. RENCANA BERTAHAP (setiap fase ditutup testing agent + gate)

### FASE 1 — Performa + Quick Wins UI + Navigasi (risiko rendah, dampak cepat)
> ✅ **SELESAI & TERVERIFIKASI (23 Jun 2026, Sesi #058)** — compile HIJAU (FE webpack compiled, BE `/api/` 200 "Kain Nusantara API aktif"); `seed_reset.sh` SEMUA GATE LULUS (contract ✅ · api_contract ✅ · data_integrity ✅ · entity_scoping F0-C ✅). Verifikasi UI end-to-end (main agent, viewport 1920×800; testing agent kena infra-timeout `networkidle` krn HMR websocket — bukan bug app):
> - Login 1-klik admin OK, dashboard Control Tower render data nyata, **0 console error**.
> - **Navigasi semua menu: 60/60 view dikunjungi, 0 crash, 0 red-overlay, 0 console error.**
> - **Poin 11** sidebar highlight sinkron dgn `activeView` (`nav-sales`/`nav-home` class `active`). 
> - **Perf loadAll**: pilih customer TIDAK full-reload (product-grid tetap mounted di belakang drawer).
> - **Poin 1** kartu 1 tombol "Pilih Varian & Detail"/"Lihat Detail & Tambah" (buka `product-quickview`). **Poin 5** label harga ikut `base_unit` (kartu "/meter", popup "HARGA/METER"). **Poin 6** filter "Rentang Harga (Rp)" tanpa "/meter". **Poin 7** checkout step-1 "Item Pesanan (N)" ringkasan. **Poin 15** ATP "Tersedia sekarang + Akan datang = Bisa dijanjikan". Gambar `loading=lazy/decoding=async`.
- **Perf:** perbaiki `useAppActions.loadAll` — hapus `selectedCustomer` dari deps & dari trigger reload penuh (pisahkan auto-select customer); kurangi reload penuh pasca-aksi yang tidak perlu.
- **Gambar:** tambah parameter ukuran pada URL gambar (kurangi lag render).
- **Poin 1:** gabung tombol "Tambah" + "ⓘ" → 1 tombol buka detail penuh (`PosProductCard.jsx`).
- **Poin 5:** label harga ikut `base_unit` (`ProductQuickView`, kartu).
- **Poin 6:** ubah label filter "Rentang Harga (Rp/meter)" → "Rentang Harga" (`FacetRail.jsx`).
- **Poin 11-nav:** jadikan highlight sidebar **turunan dari `activeView`** (satu SSOT) → sidebar selalu sinkron (`App.js`, Sidebar).
- **Poin 7:** tampilkan ringkasan item keranjang di checkout **step 1** (`CheckoutDrawer.jsx`).
- **Poin 15:** perjelas label ATP → "Tersedia sekarang 755 + Akan datang 800 = Bisa dijanjikan 1.555".
- **Test:** navigasi semua menu, POS pilih customer (cek tidak lag), checkout step 1.

### FASE 2 — UoM SSOT (satuan dari master + roll-count) — poin 4a/4b/5
> ✅ **SELESAI & TERVERIFIKASI (23 Jun 2026, Sesi #058)** — gate `seed_reset.sh` LULUS (data-integrity 119/0/0, F0-C ✅, `[F2-UoM] roll_count backfilled ke 16 balance`). Testing agent iter_73: backend API PASS (roll_count di /products, /inventory/balances +base_unit, stock-breakdown ownership_matrix); FE diverifikasi via screenshot + `ui_smoke.py` 9/9.
> - **Backend:** `roll_service.rebuild_balance` hitung `roll_count`(roll tersedia)/`on_hand_roll_count`/`roll_counts` per-bucket; `inventory_service.product_summary` agregasi roll_count; `roll_service.backfill_roll_counts()` (additive+idempotent, TANPA sentuh qty) + dipanggil di akhir seed; `scripts/migrate_roll_count.py` (migrasi terpisah). `/api/inventory/balances` tambah `base_unit`.
> - **POS hapus pemilih satuan:** `ProductQuickView` (selector `quickview-unit-select` DIHAPUS → field FIXED `quickview-unit-fixed`=base_unit + stat `quickview-roll-count`); `CheckoutDrawer` step-2 (selector `cart-item-unit-select` DIHAPUS → Qty(base_unit) + `cart-item-rolls-<id>`). Order create unit=base_unit OK (KSC/SO-00010).
> - **Tampil "X roll / Y base_unit":** kartu (`product-rolls-<id>`), mobile (`mobile-product-rolls-<id>`), inventory `BalancesTable` (`balance-onhand-rolls`/`balance-avail-rolls`).
> - **Master data:** field "Satuan Dasar" (`admin-product-base_unit-input`) kini DROPDOWN (meter/yard/cm/inch/kg/pcs/lembar) + nota penjelasan.
> - Catatan: catch-weight (kg) tetap di alur inbound `GRCatchWeightModal` yang sudah ada (tak tersentuh).
- **Backend:** `rebuild_balance` simpan `roll_count` per bucket; pastikan satuan tunggal = `base_unit`; endpoint stok kembalikan `roll_count`+`length`.
- **Master data:** perjelas pilih **Satuan Dasar** di master produk; alirkan ke purchasing (terima roll dgn panjang masing-masing) & inventory.
- **POS:** hapus pemilih satuan (popup + checkout) → pakai `base_unit`; tampil **"X roll / Y {base_unit}"** di kartu, detail, inventory.
- **Migrasi:** backfill `roll_count`.
- **Test:** master set satuan → purchasing terima 2 roll beda panjang → inventory "2 roll / 300 yard" → POS tampil benar.

### FASE 3 — Master Data: Deskripsi + Gambar per-varian — poin 3 & 2
> ✅ **SELESAI & TERVERIFIKASI (24 Jun 2026, Sesi #058)** — testing agent iter_74: **100% PASS** (backend 4/4, POS 100%, admin 100%, 0 bug). Gate `seed_reset.sh` LULUS (119/0/0).
> - **Backend:** `ProductPayload.description` (create) + `description` di whitelist PATCH (`routers/products.py`). Round-trip POST/PATCH/GET diverifikasi. (image per-varian sudah ada di model).
> - **POS popup:** `ProductQuickView` tampil blok `quickview-description` (ikut varian terpilih, fallback `group.description`); ganti varian → **SKU + gambar (`quickview-image`) + deskripsi** berubah (Biru-Coklat→Hijau-Emas terverifikasi). `variants.js` expose `group.description`.
> - **Master form (`AdminView`):** input URL gambar `admin-product-image-input` + preview `admin-product-image-preview` + textarea `admin-product-description-input` + dropdown `admin-product-base_unit-input`; tombol **Edit kini membuka form** (`setShowCreateForm(true)`) & load nilai; Update simpan via PATCH OK.
> - **Seed:** batik `tpl_batik_mega` 3 varian = 3 gambar BERBEDA (+ endek 3 varian); deskripsi per-produk auto-generate (ikut warna/grade → beda per varian).
- **Backend:** tambah `description` ke produk; tambah `image` per-varian (schema + generate varian tidak paksa samakan).
- **Frontend:** form master varian (set gambar + deskripsi per varian); popup detail tampilkan deskripsi; gambar berubah saat ganti varian.
- **Seed:** beri gambar berbeda per varian batik.
- **Test:** ganti varian → gambar & deskripsi berubah.

### FASE 4 — Redesign Status SO (SSOT 2-level) — poin 3 (fondasi) + bug poin 14
- **Backend:** tambah field `stage` + `sub_status` (+ keep status lama selama transisi); refactor transisi create/submit/approve/confirm; `recompute_so_status` & banner; **backorder→Approved(menunggu_stok)**.
- **Bug poin 14:** transisi aman (tidak ada 409 mentah; tombol di-guard sesuai stage; pesan memandu).
- **Frontend:** timeline tampil **stage + chip sub-status**; OrdersView/Dashboard pakai mapping baru.
- **Migrasi:** `migrate_so_status.py` (idempotent) + gate.
- **Test:** semua skenario (normal, nilai besar, backorder) berada di stage/sub yang benar; auto-approve tidak error.

> ✅ **SELESAI & TERVERIFIKASI (24 Jun 2026, Sesi #059)**
> Status FASE 4: **WIRING APP SELESAI — stage/sub_status live di backend & frontend, semua gate HIJAU, 0 regresi.** Testing agent iter_75: **Backend 100% (19/19)** · **Frontend 95% (22/23)** (1 non-pass = timeout automasi login sales, BUKAN bug — diverifikasi manual: sales load orders OK, tanpa crash). Gate `seed_reset.sh` LULUS (contract ✅ · api_contract ✅ · data_integrity ✅ · entity_scoping F0-C ✅ · `[F4-Status] stage/sub_status backfilled ke 9/9 SO, invalid=0`). ux_audit 0/0 · verify_api_contract 0/0 · validate_compliance 77 PASS/0 FAIL · esbuild exit 0.
>
> **✅ SUDAH DIKERJAKAN (terverifikasi):**
> 1. `backend/services/so_status.py` — SSOT derivasi 2-level (`derive_stage_substatus`, `stage_fields`, `backfill_so_status` idempotent, `STAGE_FLOW`, `VALID_STAGES`, `SUBSTATUS_LABELS`). Keputusan kunci: **approved+backorder → Approved/menunggu_stok**.
> 2. `backend/scripts/poc_so_status.py` — POC LULUS (13 unit + DB + backfill idempotent).
> 3. **Wiring backend** (`stage_fields` ke SEMUA jalur tulis status): `routers/sales_orders.py` → `create_order` (insert), `_transition` (merge `stage_fields({**order,**update_data})`), `release_reservation`; `services/fulfillment_status.py` → `recompute_so_status` (set_doc); `services/backorder_service.py` → auto-fulfill backorder; `services/inventory_service.py` → expire reservasi. Fallback baca: `_norm_backorder` derive stage bila kosong (order legacy).
> 4. **Migrasi formal** `backend/scripts/migrate_so_status.py` (standalone, idempotent, self-verify exit≠0 bila invalid) + `backfill_so_status` dipanggil di akhir `seed_realistic.seed_all` (pola `backfill_roll_counts`).
> 5. **Bug poin 14:** `_transition` kini raise 409 **memandu** — `detail` JSON: `code=INVALID_TRANSITION`, `current_stage`, `current_sub_status`, `current_status`, `attempted_action`, `allowed_from`, `message` (Bahasa Indonesia + petunjuk aksi via `_allowed_action_hint`). FE tombol sudah ter-guard per-status.
> 6. **Frontend:** `utils/soStatus.js` (mirror derivasi + `getStage`/`getSubStatus`/`STAGE_FLOW`/`stageMeta`/`subStatusLabel`); `components/SoStatusBadges.jsx` BARU (`StagePill`, `SubStatusChips`, `StageTimeline`); `OrderDetailPanel.jsx` timeline → **stage-based + chip sub-status** (header pakai `order-stage-pill`); `OrdersView.jsx` kolom "Tahap" = stage pill + sub-chip; `OrderDashboard.jsx` Recent Orders = stage pill. CSS `.stage-*` ditambah di `components.css`.
>
> **Verifikasi visual (main agent, 1920×900):** list "Tahap" + detail timeline + dashboard semua menampilkan stage+sub dengan benar untuk admin & sales (mis. SO-0009 Reserved/Menunggu stok + BACKORDER; SO-0005 Approved/Stok siap—bisa di-confirm; SO-0004 Confirmed/Siap pick; SO-0003 Shipped/Sebagian dikirim; SO-0001 Delivered).
>
> **Referensi model:** §2.2 (definisi stage+sub) & §2.3 (pemetaan migrasi) di dokumen ini = sumber kebenaran. Resep test UI: domcontentloaded + data-testid / tombol `demo-login-*-button` (JANGAN networkidle/type=email).


### FASE 5 — Alur Approval Terpadu (special price + over-credit + nilai) + RBAC — poin 8/9/10/12/13
- **Backend:** model `pending_approvals` (§2.4); aksi **di detail SO**: "Ajukan Special Price" (harga+alasan+bukti) & "Minta Approval Kredit" (bawa data order); RBAC: sales **tak bisa** approve/auto-approve/confirm.
- **Poin 8/9:** hapus input diskon manual oleh sales; diskon hanya via special-price (admin/manager). Hilangkan 2-diskon yang membingungkan dari sisi sales.
- **Frontend:** "Pusat Persetujuan" terpadu (1 inbox, konteks order); detail SO punya aksi unggah bukti; sales hanya lihat status.
- **Test:** sales buat SO → ajukan special price + bukti → manager ACC → Confirmed; over-credit → SO tersimpan + minta approval → ACC; sales tak bisa auto-approve.

> ✅ **SELESAI & TERVERIFIKASI (26 Jun 2026, Sesi #060)**
> Status FASE 5: **BACKEND + WIRING APP SELESAI — approval terpadu live, RBAC ketat, storage bukti LOKAL, semua gate HIJAU.** POC `test_f5_approval_poc.py` **24/24 PASS** (live API) · testing agent iter_77 **0 bug** · self-verify visual (sales RBAC + diskon) **PASS**. Gate: `seed_reset.sh` LULUS (119/0/0 · `[F5-Approval] pending_approvals disinkronkan ke 9/9 SO`) · health_check 21 PASS/0 FAIL · endpoint_sweep 0×5xx · ux_audit 0/0 · verify_api_contract 0/0 · esbuild exit 0.
>
> **✅ SUDAH DIKERJAKAN (terverifikasi):**
> 1. **Backend SSOT** (sudah ada dari sesi sebelumnya, diverifikasi): `services/so_approvals.py` (make_approval/summarize/approval_fields/all_approved/public_view/backfill) + `routers/so_approvals.py` (POST `request-special-price`, `request-credit-approval`, `approvals/{aid}/decide`, `approvals/{aid}/evidence`, GET `/approvals/queue`). `create_order` membuat entri `nilai`+`kredit`; **over-credit → SO TETAP tersimpan** (`credit_hold=True`, bukan 409); diskon **diabaikan** untuk sales (`0 if is_sales`). `approve/confirm` ter-guard RBAC (`order.approve`/`order.confirm`). Backfill dipanggil di `seed_all`.
> 2. **Storage bukti = LOKAL** (keputusan owner): `services/storage_service.py` ditulis ulang → filesystem lokal di `LOCAL_STORAGE_DIR` (default `<backend>/uploads`), interface dipertahankan (init/put/get/validate_upload/build_path) shg price_approvals & sales_returns tetap jalan. **Endpoint unduh bukti SO baru**: GET `/sales-orders/{id}/approvals/{aid}/evidence/{att_id}/download` (dukung `?auth=` utk `<a>`/`<img>`).
> 3. **[Titik berhenti diperbaiki]** `OrdersView.jsx` kini meneruskan `user={user}` + `onRefresh={onRefresh}` ke `<OrderDetailPanel>`; `App.js` mengirim `onRefresh={loadAll}` ke `OrdersView` → `isApprover` benar (tombol approve/confirm muncul utk admin/manager) & panel auto-refresh setelah keputusan.
> 4. **Poin 8/9 (FE):** `CheckoutDrawer.jsx` — `allowItemDiscount`/`allowOrderDiscount` kini `!isSales && ...`; sales **tak melihat** input diskon, ada catatan `sales-discount-note` (arahkan ke Harga Khusus). `user` di-wire App.js → SalesPortal → CheckoutDrawer. Admin/manager tetap punya input diskon.
> 5. **Pusat Persetujuan terpadu** (`features/approvals/ApprovalInbox.jsx`): tambah grup **"Sales Order"** dari `/approvals/queue` (nilai/kredit/harga khusus) dgn deep-link ke detail SO (`onOpenDocument({view:"orders", focus_type:"sales_order", focus_id})`); dedup harga khusus tertaut-SO dari kind `price` lama (filter `so_id`). `SoApprovalsPanel.jsx`: native select→KNSelect, money +tabular-nums, chip bukti jadi link unduh.
> 6. **Verifikasi visual (1920×800):** Manager melihat tombol approve/reject + approve order; Sales **0 tombol approve/confirm** (hanya lihat status) + "Ajukan Harga Khusus" pada SO Reserved; checkout sales tanpa diskon (+catatan), admin dengan diskon; deep-link inbox→detail SO OK; approve→refresh tanpa reload.
> **Catatan:** entri `nilai` hanya muncul saat SO **submit_for_approval** atau nilai ≥ threshold; SO kecil di bawah threshold → `approval_required=True` tanpa entri `nilai` saat create.

### FASE 6 — PPN/Faktur per-entitas + UX Entitas/Role + Multi-entitas + Rekening — poin 10/11 + 2c
- **Backend:** verifikasi/lengkapi edit entitas (`default_tax_mode`); `tax_override` + flag `needs_tax_invoice` di SO; user CRUD dukung `home_entity_id`+`allowed_entity_ids`; bank account per-entitas + slot "rekening tujuan".
- **Frontend:** checkout toggle "pakai Faktur Pajak" + ganti entitas (reset preview); banner "Anda di [entitas] sebagai [role]"; switcher entitas untuk sales multi-entitas; form master user assign entitas; master rekening per-entitas.
- **Test:** jual di entitas non-PPN → tanpa PPN; entitas PPN → PPN 11% + opsi faktur; sales 2-entitas bisa switch; rekening tampil per-entitas.

> ✅ **SELESAI & TERVERIFIKASI (26 Jun 2026, Sesi #060)**
> Status FASE 6: **BE + FE SELESAI — pajak/faktur per-entitas, multi-entitas user, rekening per-entitas, UX entitas+role.** POC `test_f6_entity_tax_poc.py` **21/21 PASS** · testing agent iter_78 **13 PASS** (2 "issue" = artefak test: sesi tak di-clear + form create collapse — diverifikasi ulang **PASS** oleh main agent) · gate `seed_reset.sh` LULUS (119/0/0) · ux_audit 0/0 · api_contract 0/0 · esbuild 0.
>
> **✅ SUDAH DIKERJAKAN (terverifikasi):**
> 1. **BE pajak SO:** `SalesOrderCreate` + `create_order` terima `needs_tax_invoice` + `tax_override`; `compute_order_pricing(..., tax_override=...)` (sudah mendukung) → PPN ikut `default_tax_mode` entitas (ent_ksc=PKP 11%, ent_kanda=non_ppn=0); SO simpan `needs_tax_invoice`, `tax_override`, `tax_mode`. (Edit entitas `default_tax_mode` sudah ada di entities.py + AdminView.)
> 2. **BE user multi-entitas:** `UserCreate` + `users.py` create/patch terima `home_entity_id` + `allowed_entity_ids` (validasi entitas; default via `resolve_allowed_entities`); login `entity_context.can_switch_entity`/`entities` aktif. (entity_context_service sudah ada.)
> 3. **BE rekening:** `bank.py` + `bank_service` per-entitas (sudah ada) — terverifikasi scope per-entitas + akun grup `all` lintas-entitas.
> 4. **FE checkout (`CheckoutDrawer`):** step Review tampil toggle **`checkout-tax-invoice-toggle`** (entitas PKP) atau catatan **`checkout-tax-nonpkp-note`** (non-PKP); kirim `needs_tax_invoice` via `useAppActions.submitOrder`.
> 5. **FE UX entitas+role:** `EntitySwitcher` tampil tag role (`entity-role-tag` "· Admin/Sales/...") — admin = dropdown multi-entitas, sales = `entity-switcher-locked`. ("Anda di [entitas] sebagai [role]".)
> 6. **FE master user (`AdminView` tab Users):** select Role + **Entitas Utama** (`admin-user-home_entity_id-input`) + chip **Entitas Diizinkan** (`admin-user-allowed-<id>`) → multi-entitas assign.
> 7. **FE `OrderDetailPanel`:** badge **`order-needs-faktur-badge`** ("Customer minta Faktur Pajak") bila `needs_tax_invoice`. `BankAccountsView` (Kas & Bank) per-entitas sudah live di nav.
> **Verifikasi visual (1920×800):** sales locked switcher "· Sales"; admin dropdown "· Admin" + opsi entitas; checkout PKP toggle vs non-PKP note; admin Users form entitas (home + chip KSC/Kanda); Kas & Bank load.

### FASE 7 — Catalog Model (fitur baru) — poin 6
- **Backend:** koleksi `catalog_models` (nama, gambar, deskripsi, `linked_skus[]`); CRUD; link dua arah.
- **Frontend:** menu "Catalog Model"; detail model → daftar SKU kain; detail kain → contoh model.
- **Test:** buat model → link ke SKU → muncul dua arah.

---

## 5. OUT OF SCOPE (slot disiapkan, implementasi nanti)
- Finance lanjutan: posting GL rekening, faktur pajak resmi (e-Faktur), F0-G/H eliminasi intercompany.
- Pajak dashboard (`cs-pajak`), tutup buku (`cs-closing`).

---

## 6. URUTAN EKSEKUSI & CHECKPOINT
F1 (perf+quickwin) → F2 (UoM) → F3 (master) → F4 (status SSOT) → F5 (approval+RBAC) → F6 (pajak+entitas) → F7 (catalog).
Tiap fase: implement → testing agent → fix → update doc ini → lanjut.
