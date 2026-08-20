# KN_19 — DEVELOPMENT PLAN **FASE A: FONDASI DOMAIN TEKSTIL**

> **Status:** ✅ **SELESAI DIEKSEKUSI** (2026-07-25) · lanjutan sah dari
> `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md`
> **Mandat:** keputusan pemilik **D-12** (§11 KN_18) — “kerjakan Fase A lebih dulu”.
> **PS tercakup:** **PS-01** (rantai stage) · **PS-02** (woven vs knit) · **PS-03** (GSM
> fondasi) · **PS-09** (grade terkendali) · **PS-15** (input desimal).
> **Aturan yang ditegakkan:** R1 (tanpa teks bebas) · R3 (SSOT) · R5 (desimal) ·
> R7 (satu registry enum) · R8 (registry + invarian + POC + migrasi idempoten).

---

## §1. KEPUTUSAN YANG MENJADI DASAR (mengikat)

| ID | Keputusan | Sumber |
|---|---|---|
| **D-01** | Urutan mutu **A → A1 → A2 → B → BS** (rank 1..5); `BS` = barang sortir | KN_18 §11 |
| **D-02** | `fabric_type` (woven/knit) **wajib sejak stage `yarn`** | KN_18 §11 |
| **D-03** | **Satu** proses `pre_treatment` → **PFD** (`target_use=dye`) atau **PFP** (`target_use=print`) | KN_18 §11 |
| **D-06/D-07** | Basis tarif **bebas per kontrak/mitra** + wajib jejak konversi (dieksekusi Fase B/D) | KN_18 §11 |
| **D-10** | Lot `LOT-YYMM-####` per batch penerimaan/proses (dieksekusi Fase C) | KN_18 §11 |
| **D-12** | Fase A dikerjakan lebih dulu | KN_18 §11 |
| **D-19** *(baru)* | **PO wajib memilih grade** per item — **tidak ada nilai default** | sesi 2026-07-25 |
| **D-20** *(baru)* | Migrasi produk lama: `fabric_type` **default `woven`** (ditandai `fabric_type_migrated`) | sesi 2026-07-25 |
| **D-21** *(baru)* | Stage **`remnant`** & **`byproduct`** aktif sejak Fase A | sesi 2026-07-25 |
| **D-22** *(baru)* | GSM **+ lebar** wajib mulai `grey` (woven); stage `yarn` wajib `yarn_count`; **knit tidak memblokir** (peringatan) karena dikendalikan kg | sesi 2026-07-25 |
| **D-23** *(baru)* | Grade berubah lewat **inspeksi QC**; **override manager/admin** boleh dengan **alasan wajib** + audit | sesi 2026-07-25 |

> Catatan interpretasi **D-22**: jawaban pemilik “…knit tidak wajib” diterapkan sebagai
> **field terukur (GSM/lebar/yarn_count) tidak memblokir untuk `fabric_type=knit`**
> (muncul sebagai peringatan + tanda `needs_review`). Aturannya **berbasis konfigurasi**
> (`domain_registry.KNIT_RELAXED_FIELDS`) sehingga dapat diubah dalam satu baris bila
> maksud pemilik berbeda.

---

## §2. YANG DIBANGUN (backend)

| Berkas | Peran | PS/D |
|---|---|---|
| `backend/domain_registry.py` **(baru)** | **SSOT enum domain** + state machine stage + matriks kelengkapan field + normalisasi/alias + validasi produk | PS-01/02/03/09 · D-01…D-22 |
| `backend/routers/enums.py` **(baru)** | `GET /api/enums`, `GET /api/enums/{name}`, `GET /api/enums/stage-transitions`, `POST /api/enums/stage-transitions/validate`, `POST /api/enums/products/validate` | R7 |
| `backend/services/grade_service.py` **(baru)** | **Satu pintu** perubahan grade roll: validasi enum + `grade_history[]` + audit + aturan override (D-23) + `resolve/stamp_expected_grade` (D-19) | PS-09 · D-19/D-23 |
| `backend/core_utils.py` | `parse_decimal()` + tipe Pydantic `QtyDecimal`/`MoneyDecimal` (menerima `"10,5"`, `"1.234,56"`, `"Rp 1.500.000"`) | PS-15 · R5 |
| `backend/schemas.py`, `schemas_purchasing.py`, `schemas_makloon.py` | field domain baru (`fabric_type`, `yarn_count`, `yarn_count_system`, `expected_grade`, `target_use`, `tariff_basis`) + tipe desimal di PR/PO/makloon/inspeksi/transfer; `PROCESS_TYPES` **re-export** dari registry (R7) | PS-02/03/09/15 |
| `backend/routers/products.py` | normalisasi + **validasi domain** create/patch (400 berbahasa Indonesia), `needs_review`, `domain_warnings` | PS-01/02/03 |
| `backend/services/product_template_service.py` | template = induk produk → validasi sama; **varian mewarisi** `fabric_type`/`yarn_count` dan divalidasi sebelum insert | PS-02 |
| `backend/routers/purchase_orders.py` + `services/{purchase_requisition,rfq,blanket_po}_service.py` | `expected_grade` **wajib** di jalur manusia; jalur turunan sistem menurunkan dari master + `expected_grade_source` | D-19 |
| `backend/services/qc_inspection_service.py` | ambang 4-point → **5 tingkat** (A/A1/A2/B/BS) dengan interpolasi kompatibel-mundur; menulis riwayat grade | PS-09 · D-01 |
| `backend/services/qc_service.py`, `services/return_service.py` | keputusan QC & release karantina memakai enum resmi + menulis `grade_history` | PS-09 |
| `backend/services/roll_service.py` | roll baru menyimpan **snapshot** `stage` & `fabric_type` + grade ternormalisasi | PS-02 |
| `backend/routers/qc_inspection.py` | `GET /api/inventory/rolls/{id}/grade-history`, `POST /api/inventory/rolls/{id}/grade-override` (admin/manager, alasan wajib) | D-23 |
| `backend/scripts/migrate_fase_a_domain.py` **(baru)** | migrasi **idempoten**: stage/fabric_type/grade + `needs_review`/`domain_gaps` + snapshot roll + riwayat grade migrasi | R8 · D-20 |
| `backend/bootstrap.py`, `seed_realistic.py` | data seed WAJIB patuh domain (stage, fabric_type, GSM/lebar, yarn_count) | R8 |
| `scripts/verify_data_integrity.py` | **INV-DOMAIN-01…06** (enum valid, fabric wajib, grade enum, needs_review, snapshot roll, riwayat konsisten) | R8 |
| `backend/test_fase_a_poc.py` **(baru)** | POC HTTP tunggal — 53 pemeriksaan untuk 12 user story Fase A | KN_18 §9 |

### Matriks transisi stage yang dikunci server (PS-01)

```
yarn --tenun(woven)--> grey        yarn --rajut(knit)--> grey
grey --pre_treatment(target_use=dye)--> pfd
grey --pre_treatment(target_use=print)--> pfp
pfd  --celup--> finished           pfp --printing--> finished
finished --finishing--> finished   (stage tidak berubah)
grey|pfd|pfp|finished --lainnya--> remnant      yarn|grey --lainnya--> byproduct
```
Kombinasi lain **ditolak HTTP 400** dengan pesan Indonesia; `pre_treatment` tanpa
`target_use` ditolak sebagai **ambigu** (memaksa keputusan D-03 dinyatakan eksplisit).

### Kelengkapan field per stage (D-02/D-22)

| Stage | Woven — wajib | Knit — wajib | Knit — disarankan |
|---|---|---|---|
| `yarn` | `fabric_type`, `yarn_count` | `fabric_type` | `yarn_count` |
| `grey` / `pfd` / `pfp` / `finished` | `fabric_type`, `gramasi`, `lebar` | `fabric_type` | `gramasi`, `lebar` |
| `remnant` | `fabric_type` | `fabric_type` | `gramasi`, `lebar` |
| `byproduct` | — | — | `fabric_type`, `gramasi`, `lebar` |

---

## §3. YANG DIBANGUN (frontend)

| Berkas | Peran |
|---|---|
| `hooks/useDomainEnums.js` **(baru)** | satu-satunya konsumsi `/api/enums` (cache modul) — komponen **dilarang** hardcode enum (R7) |
| `utils/decimalInput.js` + `components/DecimalInput.jsx` **(baru)** | input desimal koma-Indonesia dipakai lintas form (PS-15) |
| `features/admin/products/ProductMasterForm.jsx` **(baru)** | form master produk: dropdown stage/fabric_type/grade, field benang kondisional, GSM/lebar desimal, indikator wajib/disarankan real-time, hint catch-weight |
| `features/admin/domain/DomainRegistryView.jsx` + `DomainRegistryParts.jsx` **(baru)** | layar **Registry Domain**: rantai stage, matriks transisi, **simulator transisi** (memanggil validasi server), tabel kelengkapan field, daftar enum, daftar keputusan D-xx |
| `features/wms/RollGradePanel.jsx` **(baru)** | riwayat grade per roll + override beralasan (manager/admin) |
| `features/admin/AdminView.jsx` | memakai form baru + badge domain (stage/fabric/grade/GSM) & tanda **“Perlu dilengkapi”** pada daftar produk |
| `features/sales/ProductTemplatesView.jsx` | stage & fabric_type jadi dropdown, GSM/lebar/harga desimal, blokir simpan bila kelengkapan kurang |
| `features/admin/po/POCreateForm.jsx` + `PurchaseOrderManagement.jsx` | kolom **Grade (wajib)** per item PO + qty/harga desimal |
| `features/wms/QCInspection.jsx`, `RollInspectionModal.jsx` | opsi grade dari registry (bukan A+/C), prediksi grade 5 tingkat, GSM/lebar aktual desimal, tombol **Grade** (riwayat/override) |
| `features/sales/ReturnQuarantinePanel.jsx` | regrade release karantina memakai enum resmi (+2 native select diganti `KNSelect`) |
| `config/navStructure.js`, `config/navMeta.js`, `AppViewRouter.jsx` | menu **Produk & Harga → Registry Domain** |
| `hooks/useAppActions.js` | `adminCreate/adminPatch` mengembalikan `{ok,data,error}` → pesan validasi domain tampil **inline** & isian tidak hilang |

---

## §4. BUKTI (Definition of Done KN_18 §9)

| Bukti | Hasil |
|---|---|
| POC HTTP `backend/test_fase_a_poc.py` | **53 PASS · 0 FAIL** (12 user story) |
| Migrasi idempoten | jalan ke-2 → `changed=0`, `masalah_invarian=0` |
| Invarian domain | INV-DOMAIN-01…06 **PASS** di `scripts/verify_data_integrity.py` |
| Gate FE | `esbuild` 0 error · `ux_audit` (file baru bersih) · `verify_api_contract` OK · `check_nav_map` PASS · `validate_compliance` 0 FAIL |
| Registry & dokumen | `ENTITY_REGISTRY.md` diperbarui · KN_18 §12 keputusan D-19…D-23 · KN_13 menu baru |

---

## §5. YANG **BELUM** DIKERJAKAN (batas tegas Fase A)

* **PS-21 quick win notifikasi** (`po_arrival`, `backorder_ready`, `ar_due_soon` H-3/H-1/H/H+1) — siap dikerjakan berikutnya, biaya rendah (mesin alert R6.5/R6.6 sudah ada).
* **Fase B** mesin konversi satuan (`uom_conversion_rules`, komponen Input & Konversi, jejak `doc_*`/`base_*`) — tempat **D-06/D-07** dieksekusi penuh.
* **Fase C** lot kelas satu (`inventory_lots`, penomoran `LOT-YYMM-####`, genealogi) — **D-10**.
* **Fase D** wizard makloon multi-tahap/multi-mitra + selisih & klaim (`target_use` & `tariff_basis` sudah disiapkan di skema).
* **Fase E/F/G/H** sesuai KN_18 §7 + §A.5.

**Enum yang sudah terdaftar tapi fieldnya belum dipakai** (ditandai `in_use=false` +
`planned_phase` di registry, agar tidak menjadi “field hantu” R2): `lifecycle` (F),
`lot_status` (C), `claim_action` (D), `sample_type` (F).
