# PLAN — SALES REVAMP V2 (PIC/Split→Customer · Lot Policy→Customer · Beli-per-Roll · Inventory Global POS)

> **Status:** FASE A/B/C/C2/D/E = **SELESAI & TERVERIFIKASI** (Session #061, 30 Jun 2026). Bukti gate: seed_reset LULUS · health 21/0FAIL · sweep 0×5xx · ux_audit 0 · api_contract 0 · validate_compliance **0 FAIL** · esbuild 0 · `poc_sales_revamp.py` 35/35 · `backend_test_sales_revamp.py` 15/15 · testing agent **iter_81 0 bug** (BE 100%, FE 95% 20+ skenario, AUTH 4 role OK). 2 fix nyata sesi ini: (1) refactor `routers/sales_orders.py` 948→786 (ekstrak `services/sales_order_helpers.py`) utk lolos compliance; (2) tampilan rincian roll dipindah dari `CartPanel.jsx` (yatim) ke `CheckoutDrawer` step-1 aktif (`cart-item-rolls-<id>`+`step1-item-rollmode-<id>`). "Session issue" iter_79/80 = artefak automasi (BUKAN bug; auth persist benar).
> **Konvensi:** mengikuti `ENGINEERING_GUARDRAILS.md` + `FRONTEND_GUARDRAILS.md`.
> **Aturan emas:** kode menang atas prosa; verifikasi = GATES (`seed_reset.sh`, `health_check.py`,
> `audit_endpoint_sweep.py`, `ux_audit.py`, `verify_api_contract.py`, `validate_compliance.py`, `esbuild`) + `testing_agent_v3`.
> **Tanpa envelope** (respons array/objek telanjang) · token `token`/`sess_` · `/api` prefix · `data-testid` wajib · shadcn+lucide · `tabular-nums`.

## Keputusan owner (terkonfirmasi)
1. **PIC/Split** sepenuhnya dari **Customer**; SO **selalu mewarisi**, TIDAK ada editor tim di order.
2. **Kebijakan lot** (enforce_single_dye_lot + lot_policy) **hanya** di Manajemen Customer; **hapus** dari quick-add POS.
3. **Beli per Roll**: roll utuh (tak dipecah), harga = panjang × harga/satuan; **paginasi + sort FEFO** (tertua dulu); jumlah baris ikut UI/UX terbaik.
4. **Inventory POS** = **total global saja** (+ jumlah roll); hapus breakdown gudang/lot/entitas dari popup.
5. **Roll picker**: boleh lihat **semua entitas**, wajib ada **pembeda (badge entitas)**.
6. **Lintas-entitas (1.b):** boleh **pesan langsung** roll milik entitas lain → sistem **otomatis** membuat permintaan transfer antar-entitas (`/transfers/inter-company`). Tetap ada badge entitas + indikasi "butuh transfer".
7. **Rekonsiliasi Roll (mode Yard) — TAMBAHAN OWNER:** karena 1 roll = ±90–110 yd, kombinasi roll utuh tak pas dengan target yard. **Wajib ada layer rekonsiliasi** saat checkout:
   - **Genapkan ke atas / ke bawah** → qty order **diganti** jadi total roll utuh terpilih; harga ikut menyesuaikan (bukan backorder).
   - **Cut roll** (potong sebagian 1 roll agar pas target) = **opsi terakhir**, default OFF, harus eksplisit — **diminimalkan**.
   - Model data backend disatukan: `roll_lines = [{roll_id, take_qty}]` (take_qty = panjang penuh untuk roll utuh; < panjang untuk 1 roll yang dipotong).

---

## TEMUAN GROUNDED (kontrak nyata yang disentuh)
**Backend**
- `schemas.py`: `CustomerCreate` sudah punya `enforce_single_dye_lot`, `lot_policy`, `assigned_sales_id` (single). `SalesTeamMember`{sales_id,name,role,split_pct}. `SalesOrderItemIn`{product_id,quantity,unit,base_quantity,discount_percent,price_approval_id}. `SalesOrderCreate.sales_team`.
- `routers/sales_orders.py`: `create_order` → loop `allocate_and_reserve_rolls(product_id, base_quantity, city, entity_id, order_id, allow_partial, policy, customer_id)`; simpan `order.sales_team = _normalize_sales_team(payload.sales_team)` (L513).
- `routers/inventory.py` `GET /inventory/rolls` → filter product/warehouse/status/lot, `resolve_list_scope("inventory_rolls",...)`, sort `created_at desc`, enrich `warehouse_name/city, owner_entity_name`.
- `services/roll_service.py`: `allocate_and_reserve_rolls` (FEFO, owner-scoped), `_split_roll`, `_reserve_single_roll`, `release_order_rolls`, `_available_rolls_for_order`.
- `services/sales_force_service.py`: atribusi insentif baca `order.sales_team` (split) else assigned_sales (1.0).
- `routers/customers.py` + `services/customer_service.py`: create/patch/reassign (perlu cek dukungan field lot + sales_team).

**Frontend**
- `components/ProductQuickView.jsx` (desktop): Stat global + toggle "Lanjutan — stok per gudang, lot & entitas" (L149–184, fetch `/products/{id}/stock-breakdown`) + matriks kepemilikan. `onAdd(selected, qty, baseUnit)`.
- `features/sales/mobile/MobileQuickView.jsx`: seksi "Stok per gudang & lot" (L97+). `onAdd(selected, qty, unit)`.
- `features/pos/CheckoutDrawer.jsx`: `<SalesTeamEditor>` (L317) + `doSubmit` kirim `sales_team` (L148) + disable submit pakai `teamErr` (L430). `CreateCustomerModal` (L438).
- `features/pos/CreateCustomerModal.jsx`: punya seksi **Kebijakan Lot** (L52–61) — akan dihapus.
- `features/crm/CustomerFormModal.jsx`: **belum** punya lot policy & sales team.
- `features/sales/mobile/MobileCart.jsx` & `features/pos/mobile/MobileCartSheet.jsx`: pakai `SalesTeamEditor` + kirim `sales_team`.
- `hooks/useAppActions.js`: `addToCart(product,qty,unit)` → cart item `{product,quantity,unit}`; `submitOrder` kirim `sales_team` + items {product_id,quantity,unit,discount_percent,price_approval_id}; `createCustomer(form)` POST `/customers`.

---

# FASE A — PIC/Split Sales pindah ke Customer (Req 1)
**Backend**
- [ ] `schemas.py`: tambah `sales_team: List[SalesTeamMember] = []` ke `CustomerCreate` (+ model patch). Validasi: jika diisi → tepat 1 PIC, Σsplit=100, tak duplikat. PIC.sales_id MUST = `assigned_sales_id` (jaga ownership/RBAC); jika `sales_team` kosong → fallback ke `assigned_sales_id` (PIC implisit 100%).
- [ ] `services/customer_service.py` + `routers/customers.py`: create/patch simpan & validasi `sales_team`; sinkron `assigned_sales_id` = PIC. Reassign update PIC + opsi tim.
- [ ] `routers/sales_orders.py` `create_order`: **warisi** `sales_team` dari `customer` (bukan payload). Bila customer tak punya tim → derive dari `assigned_sales_id`. Hapus ketergantungan `payload.sales_team` (boleh terima tapi diabaikan/deprecated — jaga back-compat caller).
- [ ] Pastikan `sales_force_service` tetap benar (SO tetap simpan `sales_team` → tak ada perubahan konsumen).
- [ ] `ENTITY_REGISTRY.md`: update entri `customers` (tambah `sales_team`).

**Frontend**
- [ ] `CustomerFormModal.jsx`: tambah `SalesTeamEditor` (PIC + co-sales + split). PIC default = `assigned_sales_id`. Validasi `salesTeamError` sebelum submit.
- [ ] `Customer360Panel.jsx`: tampilkan tim sales (PIC + co-sales + split) + entry reassign.
- [ ] Hapus `<SalesTeamEditor>` dari `CheckoutDrawer.jsx`, `MobileCart.jsx`, `MobileCartSheet.jsx`; hapus state `salesTeam`/`teamErr` + kirim `sales_team` di submit (& di `useAppActions.submitOrder`).
- [ ] (Opsional) tampilkan info "Tim sales mengikuti customer" di checkout (read-only chip).

**Gate A:** seed_reset · health_check · endpoint_sweep · ux_audit · api_contract · esbuild · `testing_agent_v3` (buat SO → cek SO.sales_team == customer.sales_team; insentif split benar).

---

# FASE B — Kebijakan Lot hanya di Manajemen Customer (Req 2)
**Frontend**
- [ ] `CreateCustomerModal.jsx` (POS): **hapus** seksi Kebijakan Lot + `enforce_single_dye_lot` + `lot_policy` (form quick-add jadi ringkas). `useAppActions.createCustomer` tak lagi kirim field tsb (default backend berlaku).
- [ ] `CustomerFormModal.jsx` (CRM): **tambah** `enforce_single_dye_lot` (checkbox) + `lot_policy` (KNSelect: default/prefer_single/strict_single/allow_mixed) untuk create **dan** edit.
- [ ] `Customer360Panel.jsx`: tampilkan kebijakan lot customer (read-only chip) + bisa diubah via edit.

**Backend**
- [ ] Verifikasi `routers/customers.py` PATCH menerima & menyimpan `enforce_single_dye_lot` + `lot_policy`; tambah bila belum.

**Gate B:** seed_reset · ux_audit · api_contract · esbuild · `testing_agent_v3` (set policy di CRM → alokasi SO menghormati lot policy; quick-add POS tanpa field lot).

---

# FASE C — Beli per Roll + model `roll_lines` terpadu (Req 3 + 5 + 6)
**Backend**
- [ ] `GET /inventory/rolls`: tambah `sort=fefo` (tertua dulu — `created_at asc`/lot age), paginasi (`skip`,`limit`). Endpoint picker baru **`GET /inventory/rolls/available`** → objek `{items, total, page}` khusus picker (kontrak array lama tak diganggu). Param `all_entities=true` (bypass scope; tiap row tetap bawa `owner_entity_id/owner_entity_name` untuk badge) + flag `is_cross_entity` relatif entitas penjual.
- [ ] `schemas.py` `SalesOrderItemIn`: tambah `purchase_mode: str = "qty"` (`qty`|`roll`) + `roll_lines: List[RollLineIn] = []` (`RollLineIn{roll_id, take_qty}`; whole = take_qty==length_remaining). (Simpan `selected_roll_ids` sbg turunan bila perlu.)
- [ ] `services/roll_service.py`: fungsi baru **`reserve_roll_lines(order_id, product_id, roll_lines)`** — reservasi tepat sesuai daftar; roll utuh (take==remaining) di-reserve penuh; **maks 1 roll boleh "cut"** (take<remaining) via `_split_roll`. Validasi: roll available, milik produk, take>0≤remaining. Idempotent + rollback (`release_order_rolls`).
- [ ] **Lintas-entitas (1.b):** bila ada roll_line owner_entity≠entitas penjual → setelah SO dibuat, **otomatis** buat `POST /transfers/inter-company` (source=owner roll, dest=entitas penjual, item=roll/qty terkait) + tautkan ke SO (`linked_transfer_ids`). Reservasi roll tetap atas nama transfer→SO. (Reuse service transfer eksisting; jaga invarian.)
- [ ] `routers/sales_orders.py` `create_order`: jika `purchase_mode=="roll"` → `reserve_roll_lines`; `base_quantity` baris = Σ take_qty. Else (qty) → tetap FEFO `allocate_and_reserve_rolls` (kecuali sudah direkonsiliasi → lihat Fase C2 yang juga mengirim roll_lines).
- [ ] `ENTITY_REGISTRY.md`: update `sales_orders` (item: purchase_mode, roll_lines) + catatan transfer link.

**Frontend**
- [ ] Komponen baru **`RollPicker.jsx`** (dipakai desktop+mobile, jaga ≤500 baris): daftar roll FEFO + paginasi (~8–10 baris, pager/"Muat lebih"), checkbox unik, **badge entitas** + tanda "entitas lain → transfer", footer total qty=Σpanjang + subtotal. loading/empty/error.
- [ ] `ProductQuickView.jsx` + `MobileQuickView.jsx`: toggle **"Beli per Roll"** → render `RollPicker`. `onAdd` membawa `{purchase_mode:'roll', roll_lines, rolls_snapshot, quantity:Σtake}`.
- [ ] `useAppActions.addToCart`: dukung mode roll (cart item: `purchase_mode`, `roll_lines`, snapshot). `submitOrder.items`: sertakan `purchase_mode` + `roll_lines`.
- [ ] `CartPanel.jsx` / `CheckoutDrawer.jsx`: baris mode-roll tampil daftar roll + badge entitas; qty terkunci dari roll (tak diedit bebas).

**Gate C:** seed_reset · health_check · endpoint_sweep · ux_audit · api_contract · esbuild · `testing_agent_v3` (pilih roll → SO reservasi tepat; qty=Σpanjang; invarian stok; FEFO; paginasi; badge entitas; lintas-entitas → transfer otomatis terbuat). **SKIP** drag-drop/voice/kamera.

---

# FASE C2 — Layer Rekonsiliasi Roll untuk mode Yard (Req 7 — TAMBAHAN OWNER)
> Tujuan: pesan per-yard (mis. 1000) **wajib digenapkan ke roll utuh** sebelum SO final; **cut roll = opsi terakhir** (diminimalkan).

**Backend**
- [ ] Endpoint preview **`POST /sales-orders/preview-roll-reconcile`** → per baris (mode qty) hitung dari roll FEFO tersedia (owner-scoped + opsi lintas-entitas):
  - `target_qty`
  - `round_up`: {roll_lines (utuh), total_qty, delta:+X, roll_count}  (set roll utuh terkecil dgn total ≥ target)
  - `round_down`: {roll_lines (utuh), total_qty, delta:−Y, roll_count} (set roll utuh terbesar dgn total ≤ target)
  - `exact_cut`: {roll_lines = utuh… + 1 roll dipotong (take<remaining), total_qty=target}  (ditandai "opsi terakhir")
  - `exact_whole` (bila kebetulan pas): tandai tak perlu rekonsiliasi.
- [ ] `create_order`: terima baris yang sudah berisi `roll_lines` hasil pilihan rekonsiliasi → `reserve_roll_lines`. Qty & harga final = Σ take_qty (round_up/down) atau target (cut). Hapus auto-split diam-diam untuk mode qty (kecuali user pilih `exact_cut`).
- [ ] Hormati lot policy customer (prefer_single/strict_single) saat membentuk opsi; jika strict_single & opsi melanggar → sembunyikan/tandai.

**Frontend**
- [ ] Komponen baru **`RollReconcileSheet.jsx`** (≤500 baris) di alur checkout: untuk tiap baris mode-yard yang tak pas, tampilkan kartu pilihan **Genapkan ke atas / ke bawah / Potong (terakhir)** dgn ringkasan roll, delta, qty & harga baru. Default sorot round_up/round_down; "Potong" perlu klik eksplisit + catatan kecil "minimalkan potong".
- [ ] Integrasi `CheckoutDrawer` (step 2/Review) + mobile cart: blokir submit hingga semua baris yard yang butuh rekonsiliasi sudah dipilih. Setelah pilih → item.cart diisi `roll_lines` + qty/harga final.
- [ ] `CartPanel` ringkas: tampilkan badge "perlu genapkan roll" pada baris yard yang belum direkonsiliasi.

**Gate C2:** seed_reset · health_check · endpoint_sweep · ux_audit · api_contract · esbuild · `testing_agent_v3` (pesan 1000 yd → tampil round_up/down/cut; pilih → SO qty&harga = total roll utuh; invarian stok; cut hanya saat eksplisit; FEFO).

---

# FASE D — Inventory POS = total global saja (Req 4)
**Frontend**
- [ ] `ProductQuickView.jsx`: hapus toggle + seksi "Lanjutan — stok per gudang, lot & entitas" + matriks kepemilikan + state `expanded/breakdown/loadingBd` + fetch `/stock-breakdown`. Sisakan Stat **Tersedia (global)** + **Roll** (+ Reserved/Harga sesuai desain).
- [ ] `MobileQuickView.jsx`: hapus seksi "Stok per gudang & lot" + fetch breakdown. Sisakan total global + roll.
- [ ] Endpoint `/products/{id}/stock-breakdown` **tetap** (dipakai WMS/admin) — hanya tak dipanggil dari popup POS.

**Gate D:** ux_audit · api_contract (pastikan tak ada FE call yatim) · esbuild · `testing_agent_v3` (popup hanya total global + roll; tak ada breakdown).

---

# FASE E — Regresi penuh + Gate akhir ✅ SELESAI (Session #061)
- [x] `bash scripts/seed_reset.sh` (contract+api_contract+integrity) HIJAU.
- [x] `python scripts/health_check.py` 0 FAIL · `audit_endpoint_sweep.py` 0×5xx.
- [x] `python scripts/ux_audit.py` 0 ERROR · `verify_api_contract.py` 0 · `validate_compliance.py` 0 FAIL (refactor `sales_orders.py` 948→786 via `services/sales_order_helpers.py`; `CheckoutDrawer.jsx` 475).
- [x] `esbuild` 0 error.
- [x] `testing_agent_v3` end-to-end (iter_81: BE 100% 15/15, FE 95% 20+ skenario, 0 bug; AUTH admin/sales/manager/warehouse tanpa session error).
- [x] Update `PLAN_SALES_REVAMP_V2.md` + `SESSION_HANDOFF.md` (Session #061).
- [x] POC `poc_sales_revamp.py` 35/35 (sesudah refactor). Submit SO sukses (API) customer non-blokir → SO KSC/SO-00014 reserved mode=roll.

---

## Risiko & catatan
- **File-size guardrail**: ProductQuickView/MobileQuickView akan berubah signifikan; jaga ≤500 baris (mungkin ekstrak `RollPicker.jsx`). CheckoutDrawer (452) — penghapusan SalesTeamEditor mengurangi baris (aman).
- **Invarian stok** (`on_hand==available+reserved+...`) wajib tetap di seed bersih untuk reservasi roll spesifik.
- **Back-compat**: `submitOrder`/SO masih boleh terima `sales_team` payload (diabaikan) agar caller lama tak pecah; sumber kebenaran = customer.
- **Lintas-entitas roll**: default pilih hanya entitas aktif; tampilan semua entitas + badge. Eskalasi inter-company = sub-langkah opsional.
