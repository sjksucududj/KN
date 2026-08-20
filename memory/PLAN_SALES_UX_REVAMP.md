# PLAN — Sales UX Revamp (lanjutan, pasca FASE 6)

Sumber: permintaan owner (revamp bagian Sales). Analisis kode selesai. **Belum implementasi — menunggu ACC.**
Gaya kerja tetap: per fase → POC/script → testing agent → fix → update doc → lanjut. Gate wajib hijau: `seed_reset.sh`, `ux_audit`, `verify_api_contract`, `esbuild`.

## Ringkasan keputusan owner (terkonfirmasi)
1. PIC & split sales **pindah ke Manajemen Pelanggan**; SO **selalu mewarisi** tim dari customer (TIDAK ada editor tim di order).
2. **Kebijakan Lot** (lot_policy + paksa 1 dye lot) **dihapus dari POS** (quick-add customer), **hanya** di Manajemen Pelanggan.
3. **Beli per Roll**: di popup tambah, selain qty/yard ada tombol "Beli per Roll" → sales pilih roll unik. Qty baris = Σ panjang roll terpilih (roll **utuh**, tak dipecah), harga = panjang × harga/yard. **Paginasi + sort FEFO** (paling tua di atas); jumlah baris ikut UI/UX terbaik.
4. **Inventory POS** di popup: tampil **total global saja** (+ jumlah roll). Hapus breakdown per gudang/lot/kepemilikan.
5. Pilihan roll: **boleh lihat semua entitas** dengan **pembeda jelas** (badge entitas pemilik). > Keputusan teknis: roll milik entitas aktif = bisa dipilih; roll entitas lain = tampil + badge tapi **tidak bisa dipilih** (cegah jual lintas-entitas ilegal; konsisten alokasi owner-scoped). Bila owner ingin benar2 jual lintas entitas → konfirmasi terpisah.

## Temuan kode (SSOT)
- Tim sales: `frontend/.../pos/SalesTeamEditor.jsx` dipakai di `CheckoutDrawer.jsx` + `MobileCartSheet.jsx`. Backend `sales_orders._normalize_sales_team` (validasi 1 PIC + Σ split 100%). SO simpan snapshot `sales_team` (dipakai insentif).
- Customer: `CustomerCreate` sudah punya `assigned_sales_id`, `lot_policy`, `enforce_single_dye_lot`; PATCH whitelist sudah izinkan ketiganya. **Belum** ada `sales_team` di customer.
- POS quick-add: `pos/CreateCustomerModal.jsx` punya blok Kebijakan Lot + "Paksa 1 dye lot" (baris 52–61) → harus dipindah.
- Roll: koleksi `inventory_rolls` (roll_no, length_remaining, lot, warehouse, owner_entity_id, status). Endpoint `GET /inventory/rolls` (filter, owner-scoped, sort created_at desc). Alokasi `roll_service.allocate_and_reserve_rolls` (FEFO/policy, auto). SO item `SalesOrderItemIn{product_id,quantity,unit,...}` — belum ada roll terpilih.
- Popup: `components/ProductQuickView.jsx` — qty + satuan fixed; blok "Lanjutan — stok per gudang, lot & entitas" (baris 149–184) + fetch `/products/{id}/stock-breakdown`.

---

## FASE A — Tim Sales & Kebijakan Lot pindah ke Customer
**Backend**
- `services/sales_team.py` (baru): pindahkan `normalize_sales_team(raw)` (reuse dari sales_orders) → dipakai customers + sales_orders.
- `schemas.CustomerCreate`: tambah `sales_team: List[SalesTeamMember] = []`.
- `routers/customers.py`: create + patch → validasi & simpan `sales_team`; set `assigned_sales_id` = sales_id PIC (kunci kepemilikan/RBAC). PATCH whitelist tambah `sales_team`.
- `routers/sales_orders.py create_order`: **abaikan** `payload.sales_team`; **warisi** dari `customer.sales_team` (snapshot ke SO). Fallback `[{sales_id: assigned_sales_id, role:"pic", split_pct:100}]`. Insentif tetap baca `SO.sales_team` (tak berubah).

**Frontend**
- `crm/CustomerFormModal.jsx`: tambah `SalesTeamEditor` (PIC + co-sales + split) + blok **Kebijakan Lot** (`lot_policy` KNSelect + checkbox `enforce_single_dye_lot`) untuk create & edit. `assigned_sales_id` lama → jadi PIC default.
- `pos/CheckoutDrawer.jsx` + `pos/mobile/MobileCartSheet.jsx`: **hapus** `SalesTeamEditor` + state terkait. (kirim SO tanpa sales_team).
- `pos/CreateCustomerModal.jsx`: **hapus** blok Kebijakan Lot + dye-lot (baris 52–61). (Tetap boleh quick-add identitas dasar; kebijakan lot diatur di CRM.)
- `orders/OrderDetailPanel.jsx`: tampil read-only "Tim Sales (dari pelanggan)".

**Test (POC + agent):** customer dgn tim → SO warisi tim; Σ split 100% tervalidasi; insentif split benar; lot_policy customer → alokasi sesuai; POS quick-add tak punya kebijakan lot; checkout tak ada editor tim.

## FASE B — Beli per Roll (pilih roll spesifik, FEFO + paginasi)
**Backend**
- `schemas.SalesOrderItemIn`: tambah `selected_roll_ids: List[str] = []`.
- `routers/inventory.py`: endpoint baru `GET /inventory/roll-options?product_id&page&page_size` → roll `status=available`, **lintas-entitas**, **sort FEFO** (received_at/created_at asc; tie-break lot, roll_no), response `{items, total, page, page_size}`, tiap item bawa `owner_entity_name`, `selectable` (= owner==active entity), `length_remaining`, `lot`, `roll_no`, `warehouse_name`.
- `services/roll_service.py`: `reserve_specific_rolls(roll_ids, order_id, product_id, entity_id)` — kunci & reservasi roll **utuh** (validasi: ada, available, milik entitas, product cocok); balikan alokasi (struktur kompatibel SO). 409 ramah bila roll keburu diambil.
- `create_order`: bila `selected_roll_ids` ada utk baris → pakai `reserve_specific_rolls`, `quantity = Σ length_remaining` (server-authoritative, override input), simpan jejak roll di alokasi.

**Frontend**
- `ProductQuickView.jsx`: toggle **"Per Yard" / "Per Roll"**. Mode Per Roll → daftar roll (paginasi + FEFO) via `/inventory/roll-options`; multi-select roll unik (badge entitas pemilik; roll entitas lain disabled + label); qty = Σ panjang; subtotal = Σ × harga. `onAdd` bawa `selected_roll_ids` + qty + flag `buy_mode:"roll"`.
- Cart (`useAppActions.addToCart` + state) + `CheckoutDrawer`/`MobileCartSheet`: simpan `selected_roll_ids`; tampil "N roll dipilih (roll_no…)". `submitOrder` kirim `selected_roll_ids` per item.

**Test:** pilih 2–3 roll → SO reservasi tepat roll itu; qty = Σ panjang; harga benar; paginasi + urutan FEFO; roll entitas lain tak bisa dipilih; konflik roll → 409.

## FASE C — Inventory POS = total global saja
**Frontend**
- `ProductQuickView.jsx`: **hapus** blok "Lanjutan — stok per gudang/lot/entitas" (baris 149–184) + state `expanded/breakdown/loadingBd` + fetch `/stock-breakdown`. Pertahankan stat **Tersedia (global)** + **Roll**.
- (Mobile) cek `pos/mobile/*` / `sales/mobile/*` bila ada breakdown serupa → samakan (global saja).

**Test:** popup hanya tampil total global + jumlah roll; tidak ada breakdown; tak ada call `/stock-breakdown` dari POS.

---
### Urutan & verifikasi
A → B → C. Tiap fase: tulis/jalankan 1 POC script (live API) → testing agent (frontend) → fix → update doc ini. Endpoint `/inventory/rolls` lama TIDAK diubah (dipakai modul lain) — pakai endpoint baru `/inventory/roll-options` utk POS.
