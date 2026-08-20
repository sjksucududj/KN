# KN_23 — RENCANA & HASIL FASE C: LOT KELAS SATU (`inventory_lots`)

> Status: **✅ SELESAI & TERUJI** (sesi 2026-07-25). Keputusan pemilik: **D-10** (format
> `LOT-YYMM-####`, granularitas per batch penerimaan/proses), **D-26** (nomor **per entitas**),
> **D-27** (penegakan **configurable**: `warn` default / `block`).
> Induk: `KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md` (PS-10), `KN_15_INVENTORY_OWNERSHIP_LOT.md`.
> Aturan emas: **kode menang atas dokumen**.

---

## 1. Masalah yang diselesaikan (PS-10)

Sebelum Fase C, `lot` hanya **string** di `inventory_rolls` (mis. `LOT-001`, `LOT-MIGRATED`)
sehingga: tidak ada titik input yang jelas, tidak ada silsilah (split/merge/rework), tidak ada
dasar recall, dan fallback `LOT-MIGRATED` mengotori data. Fase C menaikkan lot menjadi
**entitas kelas satu** yang menaungi banyak roll.

## 2. Keputusan pemilik yang dieksekusi (dikonfirmasi sesi ini)

| # | Keputusan | Implementasi |
|---|---|---|
| 1 | Nomor lot **per entitas** | `KSC/LOT-2607-0001` · `next_doc_number(..., entity_id, scheme="per_entity_prefix")` (sequence atomik per entitas+bulan, deletion-safe) |
| 2 | Penegakan **peringatan saja** dulu | `system_settings` scope `lot` → `enforcement_mode=warn` (default). Mode `block` tersedia & bisa diubah **tanpa deploy** (D-27) |
| 3 | **Backfill penuh** data lama | Setiap string lot unik → dokumen lot `source=migration`; roll dapat `lot_id`; **string lama tetap** di `roll.lot` + `lot.legacy_lot_codes` |
| 4 | Genealogi **lengkap** | `split` · `merge` · `rework` + `parent_lot_ids`/`child_lot_ids` dua arah, **anti-siklus**, layar silsilah interaktif |
| 5 | Input tambahan | `supplier_lot` + `dye_lot`/`shade_ref` di form **GR & inspeksi QC**; **label/QR** lot (reuse `label_printer_service`); **laporan recall** lot → roll → SO → pelanggan |

TIDAK dipilih pemilik: status mutu lot **tidak** memblokir penjualan (informasional saja).

## 3. Model data — `inventory_lots` (prefix id `lot_`)

```
id                 lot_<uuid>
lot_number         KSC/LOT-YYMM-####  (unik; per entitas · D-26)
entity_id          entitas penomoran   owner_entity_id  pemilik (selaras roll · KN_15)
product_id, sku, product_name, unit, warehouse_id
stage, fabric_type snapshot domain (Fase A · roll_domain_snapshot)
source             receiving|makloon|production|split|merge|rework|return|transfer|
                   adjustment|migration|manual        (enum registry `lot_source`)
source_ref         {type,id,number}  -> wms_task | purchase_order | makloon_order |
                                       work_order | lot | sales_return | manual
supplier_lot, dye_lot, shade_ref, supplier_id, supplier_name
process            {process_type, partner_id, partner_name}   (rework/makloon)
parent_lot_ids[]   child_lot_ids[]      genealogi dua arah, bebas siklus
lot_status         karantina|released|in_process|hold_shade|rework  (+ status_history[])
roll_count, active_roll_count, qty_initial, qty_remaining, qty_available,
status_breakdown   <- SELALU dihitung ulang dari roll (tidak pernah $inc)
legacy_lot_codes[] jejak string lot lama (keputusan #3)
note, created_at/by, updated_at
```
Perubahan koleksi lain (additive, nullable untuk data lama):
`inventory_rolls.lot_id`, `inventory_rolls.supplier_lot`, `inventory_movements.lot_id`,
`wms_tasks.lot_ids/lot_numbers/supplier_lot/lot_warnings`,
`mfg_work_orders.output_lot_id/input_lot_ids`, `makloon_orders.steps[].lots[].lot_id`,
`inventory_rolls.inspection.lot_id`.

## 4. Berkas & tanggung jawab

| Berkas | Isi |
|---|---|
| `backend/services/lot_service.py` | SSOT lot: pengaturan (D-27), penomoran (D-10/D-26), `resolve_or_create` (idempoten), agregat, split/merge/rework, status, daftar & statistik |
| `backend/services/lot_trace_service.py` | Silsilah (`genealogy`), **recall**, **label/QR** |
| `backend/services/lot_migration.py` | Backfill idempoten (dipakai bootstrap, seed, dan CLI — satu implementasi) |
| `backend/scripts/migrate_fase_c_lots.py` | CLI migrasi (`--dry-run`) |
| `backend/routers/lots.py` + `backend/schemas_lots.py` | 17 endpoint `/api/lots*` + `/api/rolls/{id}/lot` |
| `frontend/src/features/inventory/lots/*` | Layar **Lot & Silsilah** (list/statistik/kebijakan/detail 4 tab/aksi/label) |
| `frontend/src/features/wms/inbound/GRCatchWeightModal.jsx` | Input identitas lot saat GR |
| `frontend/src/features/wms/RollInspectionModal.jsx` | Input identitas lot saat inspeksi 4-point |

Titik pembuatan roll yang kini SELALU berlot: GR (`inbound_receiving`), `roll_service.create_inbound_roll`
(manual inbound, cycle-count surplus), makloon (output + barang sisa, induk = lot bahan),
produksi WO (induk = lot bahan), retur jual, stok awal manual, generator seed.
Roll turunan hasil pecah fisik (reservasi/kirim/QC parsial) **mewarisi** `lot_id` induknya;
agregat lot disegarkan lewat hook di `rebuild_balance()`.

## 5. Endpoint

```
GET    /api/lots                     daftar + filter (q, product_id, warehouse_id, source,
                                     lot_status, stage, entity_id) + paginasi opsional
GET    /api/lots/stats               KPI + kebijakan aktif
GET    /api/lots/settings            kebijakan penegakan (D-27)
PUT    /api/lots/settings            ubah kebijakan (admin/manager)
GET    /api/lots/unassigned-rolls    roll belum bertaut lot (mode peringatan)
GET    /api/lots/{id}                detail + rolls + parents/children + warnings
GET    /api/lots/{id}/genealogy      nodes + edges + rantai tahap + dokumen sumber
GET    /api/lots/{id}/recall         roll -> SO -> pengiriman -> pelanggan (+kontak) + total
POST   /api/lots/{id}/label          perintah cetak ZPL/ESC-POS + nilai QR
POST   /api/lots                     buat lot manual
PATCH  /api/lots/{id}                ubah supplier_lot/dye_lot/shade_ref/note/gudang
POST   /api/lots/{id}/status         ubah status mutu (+alasan, tercatat)
POST   /api/lots/{id}/rolls          tautkan roll (penambalan data)
POST   /api/lots/{id}/split          pecah sebagian roll -> lot anak
POST   /api/lots/merge               gabung >=2 lot -> lot baru (2+ induk)
POST   /api/lots/{id}/rework         lot anak hasil proses ulang (+validasi transisi tahap)
GET    /api/rolls/{roll_id}/lot      lot dari sebuah roll
```
RBAC memakai modul izin **`inventory`** yang sudah ada (tanpa modul izin baru):
lihat = admin/manager/sales/warehouse · mutasi = admin/manager/warehouse · kebijakan = admin/manager.

## 6. Invarian baru (`scripts/verify_data_integrity.py` → L4-LOT)

| Kode | Isi |
|---|---|
| INV-LOT-01 | Nomor lot sah `(KODE/)LOT-YYMM-####`, unik, produk & pemilik ada |
| INV-LOT-02 | `roll.lot_id` menunjuk lot yang ada; roll tahap ≥ grey tanpa lot = **WARN** (keputusan #2) |
| INV-LOT-03 | Genealogi dua arah & **bebas siklus** |
| INV-LOT-04 | Agregat lot == Σ roll (proyeksi murni turunan) |
| INV-LOT-05 | Lot tidak lintas produk/pemilik |
| INV-LOT-06 | Kebijakan penegakan ada & sah (`warn`/`block`) |

## 7. Bukti (dijalankan di container, bukan klaim dokumen)

| Bukti | Hasil |
|---|---|
| `python backend/test_fase_c_lot_poc.py` | **51 PASS / 0 FAIL** (15 blok uji, HTTP nyata + assert DB) |
| `python scripts/verify_data_integrity.py` | **165 PASS / 0 FAIL / 0 WARN** |
| `bash scripts/gate.sh` | **12/12 HIJAU** (receipt `memory/GATE_RECEIPT.md`) |
| `python backend/scripts/migrate_fase_c_lots.py` ×2 | run-1 backfill, run-2 **changed=0** (idempoten) |
| Regresi POC | Fase A **53/0** · PS-21 **43/0** · Fase B **49/0** |
| `testing_agent_v3` iter_164 | backend **46/46 (100%)**, frontend 15/16 |
| Verifikasi browser (main agent) | GR → lot `KSC/LOT-2607-0116` terbentuk; inspeksi QC menyimpan `supplier_lot`/`dye_lot`; layar Lot & Silsilah + recall untuk role sales |

## 8. Bug nyata yang ikut ditemukan & diperbaiki

1. **GR produk berbasis yard tertolak (400)** — form GR memprefill berat memakai kg **per meter**
   (`gsm×lebar/1000`), sedangkan server (benar, sejak Fase B) memakai kg per **base unit**
   → selisih **9,38 %** melebihi batas blokir 5 % sehingga penerimaan **gagal**.
   Perbaikan: helper bersama `frontend/src/utils/uom.js → kgPerBaseUnit()` (cermin
   `uom_service.kg_per_base_unit`) dipakai `GRCatchWeightModal` & `InboundScanInterface`;
   cabang catch-weight `convFactor()` juga diperbaiki. Terbukti di browser: prefill
   `1 yard ≈ 0,269 kg` (sebelumnya 0,294) dan GR berhasil.
2. **Mode `block` mengembalikan 500** — `LotError` tidak ditangkap di router GR/QC → kini 400
   dengan pesan yang bisa ditindak petugas.
3. **Roll dari jalur non-form lahir tanpa lot** (generator seed & demo QC) → kini memakai
   jalur lot yang sama (tanpa logika ganda).

## 9. Batasan / catatan jujur

- Status mutu lot **belum** memblokir penjualan (sesuai pilihan pemilik; tinggal dinyalakan bila diminta).
- 23 `inventory_movements` warisan menunjuk roll yang sudah tidak ada (`ROLL-001`, dst.) →
  **tidak** dikarang lot-nya; dilaporkan apa adanya oleh migrasi (`movements_orphan_roll`).
- Label lot menghasilkan **perintah printer** (ZPL/ESC-POS) + nilai QR; render gambar QR
  dilakukan printer/aplikasi cetak, bukan aplikasi ini.
- Kanal WhatsApp masih provider `simulated` (warisan keputusan sebelumnya, di luar Fase C).

## 10. Berikutnya (menunggu keputusan pemilik)

- **Fase D** — wizard makloon multi-tahap/multi-mitra + selisih & klaim (`input_lot_ids`/
  `output_lot_id` sudah tersedia dari Fase C).
- Opsi cepat: aktifkan blokir lot (`enforcement_mode=block`) bila disiplin data sudah siap;
  atau jadikan status mutu lot sebagai penghalang penjualan.
