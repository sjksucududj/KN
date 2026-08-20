# KN_31 — RENCANA **FASE F: R&D & DESIGN** (Spesifikasi · Labdip · Proofing · Pattern)

> Dibuat: **2026-07-29** · Rujukan wajib: `docs/KN_18_TEXTILE_FOUNDATION_PROBLEM_STATEMENT.md`
> §4 (PS-12/13/14), §5.1 (koleksi baru), §7 (urutan fase), §A.3 (PS-18/PS-19), §A.4 (usulan lebih baik).
> Protokol: **POC-first → backend → invarian → frontend → testing_agent → gate → dokumen → berhenti.**

---

## 0. Mengapa fase ini, bukan G-8

| Bukti di repo | Akibat |
|---|---|
| `domain_registry.ENUMS["sample_type"]` & `["lifecycle"]` → `in_use: False`, `planned_phase: "F"` — **0 penulis** di seluruh repo | Sistem *mengklaim* punya labdip/proofing & lifecycle produk, padahal tidak. Pelanggaran "satu sumber kebenaran". |
| `schemas_contracts.py:57` `sample_ref: str = ""  # referensi labdip/proofing (Fase F)` | Fase E sudah menyiapkan gantungan; tidak ada yang menggantung padanya. |
| KN_18 §A.5: PS-17/18/19 **bergantung** pada `md_specs`/`md_samples`/`md_designs` | Fase H tidak bisa dimulai sebelum F. |
| `design_gallery` = galeri motif **di bawah modul HRD (H5)**, RBAC `hr.view` | PS-14 minta modul design ber-kode/versi/mockup — belum jadi master. |
| G-8 (rekonsiliasi bank) tidak diblokir sub-fase apa pun | Bisa menyusul kapan saja tanpa biaya retrofit. |

---

## 1. Aturan pengaman (agar G-0…G-4 TIDAK rusak)

Fase ini menyentuh jalur uang (SO/PR/PO). Karena itu **8 pagar** berikut mengikat:

| # | Pagar | Cara ditegakkan |
|---|---|---|
| 1 | **Additive-only** pada koleksi lama | `products` hanya DAPAT tambahan field `lifecycle`, `spec_id`, `design_id`, `design_version`. Tidak ada rename/hapus. |
| 2 | **Backward-compatible default** | `lifecycle` yang **kosong/tidak ada** = `produksi` (boleh dipesan). Jadi 17 produk seed & semua data lama **tidak mungkin** ikut terblokir. Migrasi idempoten menstempel `produksi` agar data eksplisit. |
| 3 | **Gating configurable** (bukan angka mati) | `rnd.lifecycle_enforcement` = `off` \| `warn` \| `block` di registry FASE G-0. Default `block` — aman karena pagar #2. |
| 4 | **Satu fungsi penjaga** | `services/rnd_gate.py:assert_orderable()` dipanggil di **4 titik saja** (SO, PR, PO, katalog). Tidak ada logika lifecycle tersebar. |
| 5 | **Relasi lewat G-4** | Semua tautan (spec↔sample↔kontrak↔produk) memakai `doc_refs_service.safe_link()` — bukan field ad-hoc. |
| 6 | **Konfigurasi lewat G-0** | Semua ambang/kebijakan `rnd.*` didaftarkan di `config_catalog_ops.py` dengan `consumers` nyata (INV-CFG-01) — dilarang ada UI penulis konfigurasi kedua (INV-CFG-04). |
| 7 | **Nomor & entitas** | `next_doc_number(..., entity_id=...)` (`<ENT>/SPEC-#####`, `<ENT>/SMP-#####`) + koleksi baru masuk `SCOPED_COLLECTIONS` + `ENTITY_REGISTRY.md`. |
| 8 | **Bukti-merah wajib** | POC menyuntik pelanggaran → invarian `INV-RND-*` harus MEMERAH → dipulihkan → hijau. Tanpa ini gate dianggap palsu. |

---

## 2. Model data

### 2.1 `md_specs` — Spesifikasi produk versi R&D (prefix `spec_`, nomor `<ENT>/SPEC-#####`)
```
id · number · entity_id · title · status(draft|review|approved|rejected)
lifecycle(konsep|labdip|proofing|disetujui|produksi|dihentikan)
target{ stage · fabric_type · gramasi · lebar · construction{epi,ppi,warp_count,weft_count,reed_width} }
color_target{ color_id · code · name · hex }        ← dari color_library (PS-13, TIDAK teks bebas)
design_id · design_version                          ← wajib bila sample_type=proofing (PS-14)
sample_type_hint(labdip|proofing|bulk_sample) · category · base_unit
customer_id · so_id                                 ← bila lahir dari permintaan pelanggan
product_id                                          ← terisi saat approve (produk = hasil approve)
notes · attachments[] · timeline[] · refs[] · created_by/at · updated_at
```
Alur: `draft → submit → (review) → approve → produk lahir (lifecycle=disetujui) → release → produksi`
`reject` wajib `reason`. **Tidak ada edit senyap**: setiap transisi menulis `timeline[]` + `audit_logs`.

### 2.2 `md_samples` — Permintaan Labdip / Proofing (prefix `smp_`, nomor `<ENT>/SMP-#####`)
Satu entitas permintaan kerja (KN_18 §A.4 — **BUKAN** dokumen "SO Design"/"Design PO" baru).
```
id · number · entity_id · spec_id · sample_type(labdip|proofing|bulk_sample)
status(draft|sent|in_progress|assessed|decided|cancelled)
color_target{} · design_id/version · customer_id · so_id · target_date · brief
participants[] { supplier_id · supplier_name · status(invited|responded|acc|rejected) · rounds · best_score }
rounds[] {
   round_no(1..n per supplier) · supplier_id · sent_at · due_date · received_at · overdue(bool)
   attachments[] (WAJIB ≥1 saat submit) · note (WAJIB) · performed_by
   measurements{ delta_e · colorfastness_wash · colorfastness_rub · shrinkage_pct · gsm_actual }
   result(revisi|acc|tolak) · score(0..100) · assessed_by · assessed_at
}
material_issues[] { roll_id · product_id · warehouse_id · qty · unit · cost · movement_id }  ← PS-19
cost_total · decision{ supplier_id · reason_code · note · decided_by/at · contract_id · supplier_item_id }
refs[] · timeline[] · created_by/at
```
Aturan keras (dibuktikan POC):
* Tutup round **tanpa lampiran atau tanpa catatan → 400** (PS-18).
* `round_no` **berurut per supplier**; melebihi `rnd.max_rounds` → butuh izin `rnd:manage` + alasan.
* `decide` hanya sah bila ada ≥1 round `result=acc`; menghasilkan **kontrak harga (Fase E)** + **supplier_item** + refs dua arah.
* `sample_type=proofing` **wajib** `design_id` (PS-14).

### 2.3 Design master — **PERLUASAN `design_gallery`** (PS-14: *perluas, jangan buat baru*)
Tambahan field (additive, tidak mengubah alur HRD H5 yang sudah jalan):
`code` (unik per entitas) · `design_type(motif|pattern|artwork)` · `version` (int, mulai 1) ·
`repeat_cm` · `color_count` · `screen_count` · `status(draft|approved|retired)` ·
`approved_by/at` · `versions[]` (riwayat: version, note, files[], at, by) · `product_ids[]`
Endpoint baru pada router yang **sama** (satu permukaan): `POST /design-gallery/{id}/version`,
`POST /design-gallery/{id}/approve`. RBAC: `rnd:manage` **atau** `hr:manage_attendance`
(dua divisi berhak; tidak ada wewenang yang dicabut).

### 2.4 `products` (additive)
`lifecycle` · `spec_id` · `design_id` · `design_version`.
Gating: hanya `produksi` (atau kosong = anggap produksi) yang boleh masuk SO/PR/PO/katalog jual.

---

## 3. Konfigurasi baru (registry FASE G-0 — grup baru `rnd`)

| Kunci | Tipe | Default | Arti |
|---|---|---|---|
| `rnd.lifecycle_enforcement` | enum | `block` | Produk belum "produksi" saat dipesan: abaikan / peringatkan / tolak |
| `rnd.new_product_default_lifecycle` | enum | `produksi` | Lifecycle produk yang dibuat langsung dari Master Produk (bukan dari R&D) |
| `rnd.spec_approval_roles` | list | `["manager","admin"]` | Siapa boleh meng-ACC spesifikasi |
| `rnd.sample_decision_roles` | list | `["manager","admin"]` | Siapa boleh memutus pemenang sample |
| `rnd.max_rounds` | int | `3` | Batas iterasi rnd per supplier sebelum butuh izin khusus |
| `rnd.round_sla_days` | int | `7` | Target hari per round (lewat = ditandai *overdue*) |
| `rnd.require_attachment_on_round` | bool | `true` | Wajib lampiran + catatan saat menutup round |
| `rnd.require_design_for_proofing` | bool | `true` | Proofing wajib merujuk kode desain |
| `rnd.auto_contract_on_decide` | bool | `true` | Keputusan sample otomatis membentuk kontrak harga + barang supplier |
| `rnd.sample_material_from_stock` | bool | `true` | Ambil bahan sample mengurangi stok gudang (movement `sample_issue`) |

---

## 4. RBAC

`rnd: [view, create, submit, assess, decide, manage]`
* admin → semua · manager → `view,create,submit,assess,decide` · sales → `view,create` (mengajukan
  permintaan sample untuk pelanggan) · warehouse → `view` (melihat pengambilan bahan sample).
* Keputusan sensitif (`decide`, `approve spec`, round > `max_rounds`) tetap dijaga **kebijakan**
  `rnd.*_roles`, sehingga wewenang tidak bisa dilangkahi lewat endpoint.

---

## 5. Invarian baru (`verify_data_integrity.py` → layer L4-RND)

| ID | Isi |
|---|---|
| **INV-RND-01** | Setiap `md_samples` berstatus `decided` wajib punya round `result=acc`, pemutus, alasan, dan (bila `auto_contract_on_decide`) kontrak nyata yang ada di `supplier_contracts`. |
| **INV-RND-02** | Setiap round tertutup (`result` terisi) wajib punya ≥1 lampiran **dan** catatan; `round_no` berurut per supplier tanpa lompatan. |
| **INV-RND-03** | Setiap `md_specs` `approved` wajib punya `product_id` yang benar-benar ada, dan produk itu wajib menunjuk balik `spec_id` (dua arah). |
| **INV-RND-04** | Tidak ada produk `lifecycle ∈ {konsep,labdip,proofing}` yang dipakai di SO/PR/PO manapun (uang tidak boleh keluar untuk barang yang belum sah). |
| **INV-RND-05** | Setiap `material_issues[]` punya `inventory_movements` nyata bertipe `sample_issue` dengan qty negatif yang sama (stok sample = stok gudang, satu angka). |
| **INV-RND-06** | `sample_type=proofing` wajib `design_id` yang ada di `design_gallery`; desain berstatus `retired` tidak boleh dipakai permintaan baru. |

Gate baru di `scripts/gate.sh --full`: `POC FASE F (R&D · labdip/proofing · lifecycle produk)`.

---

## 6. Endpoint (semua ber-prefix `/api`)

```
GET    /rnd/meta                          → enum, kebijakan berlaku, label alasan, statistik
GET    /rnd/specs        POST /rnd/specs
GET    /rnd/specs/{id}   PATCH /rnd/specs/{id}
POST   /rnd/specs/{id}/submit | /approve | /reject | /release-product
GET    /rnd/samples      POST /rnd/samples
GET    /rnd/samples/{id} PATCH /rnd/samples/{id}
POST   /rnd/samples/{id}/send            (undang N supplier — many-supplier compare)
POST   /rnd/samples/{id}/rounds          (buka round berikutnya)
POST   /rnd/samples/{id}/rounds/{no}/submit   (hasil + lampiran WAJIB + catatan WAJIB)
POST   /rnd/samples/{id}/rounds/{no}/assess   (skor + hasil acc|revisi|tolak)
POST   /rnd/samples/{id}/decide          (pilih pemenang → kontrak + supplier item)
POST   /rnd/samples/{id}/issue-material  (ambil bahan dari roll → movement sample_issue)
POST   /rnd/samples/{id}/cancel
POST   /rnd/samples/{id}/attachments     (upload berkas; storage_service)
GET    /rnd/samples/{id}/attachments/{fid}
GET    /rnd/reports/designer             (jumlah acc & rata-rata lama pengerjaan — dasar PS-18)
POST   /design-gallery/{id}/version | /approve   (perluasan master design)
GET    /products?orderable_only=true            (katalog hanya produk sah dijual)
```

---

## 7. Frontend — hub baru **"R&D & Desain"**

Menu grup **Penjualan → …** ❌ (bukan penjualan). Ditempatkan sebagai grup baru
**`rnd` (R&D & Desain)** setelah *Pembelian*, karena hasilnya bermuara ke kontrak & PO.

| Tab (`HUB_TABS.rnd-hub`) | View | Isi |
|---|---|---|
| Spesifikasi Produk | `rnd-specs` | Daftar + wizard buat spec (target kain, warna dari pustaka, desain), aksi submit/ACC/tolak/rilis, badge lifecycle |
| Permintaan Sample | `rnd-samples` | Antrean labdip/proofing, panel detail **timeline round rnd 1→n per supplier**, form hasil (lampiran + catatan + hasil ukur), skor, pilih pemenang, ambil bahan sample |
| Desain & Pattern | `rnd-designs` | Master desain ber-kode & versi, upload artwork/mockup, approve, tautan ke produk |
| Laporan R&D | `rnd-reports` | Kinerja per pelaksana (acc/periode, rata-rata hari), biaya sample, papan SLA |

Integrasi ke layar existing:
* **Master Produk** → kolom **Lifecycle** + tombol "Rilis ke Produksi" + tautan spec.
* **Kontrak Mitra & Supplier** → kolom `sample_ref` akhirnya terisi & bisa diklik ke `md_samples`.
* **Jejak Dokumen (G-4)** → `md_specs` & `md_samples` masuk peta dokumen, bisa jadi jangkar.
* **Pustaka Warna** → tombol "Buat Labdip" langsung dari warna.

**User stories yang wajib lulus (diuji `testing_agent_v3`):**
1. R&D membuat spesifikasi kain baru (target GSM/lebar + warna dari pustaka) lalu mengajukannya.
2. Manager meng-ACC spesifikasi → produk baru lahir berstatus **belum boleh dijual**.
3. Sales mencoba menjual produk `konsep`/`disetujui` → **ditolak** dengan pesan yang bisa ditindak.
4. R&D mengirim permintaan **labdip** ke 2 supplier sekaligus dan membandingkan hasilnya.
5. Menutup round tanpa lampiran → **ditolak**; dengan lampiran + catatan → tersimpan sebagai rnd 1.
6. Round 2 dibuka karena revisi; setelah acc, manager memberi skor lalu memilih pemenang.
7. Keputusan pemenang otomatis membentuk **kontrak harga** + **barang supplier**, terlihat di layar Fase E.
8. Spesifikasi dirilis → produk jadi `produksi` → sales berhasil membuat SO atas produk itu.
9. Proofing tanpa memilih kode desain → ditolak; setelah memilih desain, permintaan terbentuk.
10. Mengambil 3 meter bahan untuk sample → **stok gudang berkurang 3 meter** (satu angka, bukan dua).
11. Warehouse melihat pengambilan bahan sample di mutasi stok bertipe `sample_issue`.
12. Auditor membuka Jejak Dokumen dari kontrak → sampai ke sample & spesifikasi asalnya.

---

## 8. Tahapan eksekusi

| Fase | Isi | Bukti selesai |
|---|---|---|
| **1 — POC** | `backend/test_fase_f_rnd_poc.py` (single script, HTTP nyata, self-cleanup, bukti-merah 6 invarian) | **100% HIJAU**, nol residu, `verify_data_integrity` tetap hijau |
| **2 — Backend V1** | koleksi + service + router + gating 4 titik + config + RBAC + refs + invarian + indeks | POC hijau + `verify_data_integrity` 204 → **210** |
| **3 — Frontend V1** | hub `rnd-hub` 4 tab + integrasi 4 layar existing + nav/meta/testid | `check_nav_map` PASS + `rebuild_frontend.sh` OK |
| **4 — Data demo** | `seed_rnd()` di `seed_realistic.py` (2 spec, 2 sample labdip+proofing, round nyata, 1 keputusan → kontrak, 1 pengambilan bahan) | seed idempoten, invarian hijau |
| **5 — Uji** | `testing_agent_v3` BE + 12 user story FE lintas 3 role | 0 bug tersisa |
| **6 — Tutup** | `gate.sh --full` (25 → **26** gate) + ENTITY_REGISTRY + plan.md + SESSION_HANDOFF | receipt HIJAU |

## 9. Yang SENGAJA ditunda (jadi FASE H, bukan dikerjakan sekarang)
* **PS-17** divisi/jabatan sebagai aktor (Sample · Designer · RnD · Socmed · MD · Admin Sales · Finance)
  + penugasan antar-divisi → butuh **keputusan pemilik D-13** (daftar final divisi & approver).
* **PS-18** laporan KPI designer lengkap + eskalasi SLA otomatis (mesin R6.6). Di fase F hanya
  disiapkan datanya (`round.due_date`, `overdue`, `score`) + laporan dasar.
* **PS-20** produk eksklusif per sales (`exclusivity`, `owner_sales_ids[]`).

---

## 10. PENUTUPAN FASE F — status 12 user story (2026-07-29)

Sesi penutup memverifikasi **3 user story terakhir** yang sebelumnya belum teruji
(iter_182 melaporkannya sebagai *optional_verification* karena jalur navigasinya
tidak ditemukan agen uji).

| US | Isi | Status | Bukti |
|---|---|---|---|
| 1 | Buat spesifikasi + ajukan | ✅ | `test_fase_f_rnd_poc.py` |
| 2 | ACC spesifikasi → produk lahir "belum boleh dijual" | ✅ | `test_fase_f_rnd_poc.py` |
| **3** | **Sales ditolak menjual produk `disetujui`** | ✅ **BARU** | `test_fase_f_us3_us11_us12_poc.py` + UI |
| 4 | Labdip ke 2 supplier & dibandingkan | ✅ | `test_fase_f_rnd_poc.py` |
| 5 | Tutup round tanpa lampiran → ditolak | ✅ | `test_fase_f_rnd_poc.py` |
| 6 | Round 2 → skor → pilih pemenang | ✅ | `test_fase_f_rnd_poc.py` |
| 7 | Keputusan → kontrak harga + barang supplier | ✅ | `test_fase_f_rnd_poc.py` |
| 8 | Rilis → `produksi` → SO berhasil | ✅ | `test_fase_f_rnd_poc.py` |
| 9 | Proofing tanpa desain → ditolak | ✅ | `test_fase_f_rnd_poc.py` |
| 10 | Ambil 3 m bahan → stok gudang −3 m | ✅ | `test_fase_f_rnd_poc.py` |
| **11** | **Warehouse melihat mutasi bahan sample** | ✅ **BARU** | `test_fase_f_us3_us11_us12_poc.py` + UI |
| **12** | **Jejak Dokumen kontrak → sample → spesifikasi** | ✅ **BARU** | `test_fase_f_us3_us11_us12_poc.py` + UI |

### 10.1 Jalur UI pasti (dipakai uji & untuk demo ke pemilik)
* **US3** — masuk `sales` → sidebar **PENJUALAN → POS / Sales Portal** → cari `RND-KTN-150`.
  Kartu menampilkan badge *"Disetujui (belum rilis) · belum boleh dijual"*, catatan kuning
  yang menyebut alur **Spesifikasi → Sample → Rilis ke Produksi**, dan tombol
  *"Belum boleh dijual — lihat alasan"*. Tombol **sengaja tidak dimatikan**: mengkliknya
  membuka popup berisi alasan lengkap + jalan keluar, sementara tombol
  *Tambah ke Keranjang* di dalam popup tetap terkunci (`data-orderable="false"`).
  Sebelumnya tombol `disabled` → jalan buntu tanpa penjelasan.
* **US11** — masuk `warehouse` → **Operasi Gudang (WMS) → tab Stok** → toggle kanan
  **Mutasi** (`inventory-tab-ledger`). Ada penyaring **Jenis mutasi** (label Indonesia)
  + pintasan **"Ambil Bahan Sample (R&D)"** (`ledger-quick-sample`) → 1 baris, qty −3,
  dokumen `KSC/SMP-00001`. Kode mentah (`sample_issue`, dll.) tidak pernah tampil.
* **US12** — masuk `admin` → **PEMBELIAN → Master Pembelian → Kontrak Mitra & Supplier**
  → tombol **Jejak Dokumen** (`contract-trace-{id}`) pada baris kontrak. Alternatif:
  **Pusat Dokumen → Jejak Dokumen** (`hub-tab-doc-trace`) lalu cari nomor kontrak.
  Rantai tampil: `KSC/SPEC-00001 → KSC/SMP-00001 → KSC/SCT-00007` + daftar relasi dua arah.

### 10.2 Yang ditambah/diperbaiki saat penutupan
| Perubahan | Alasan |
|---|---|
| Penyaring **Jenis mutasi** + pintasan sample (BE param `movement_type`) | US11 tak bisa dipenuhi kalau petugas harus mengetik kode mentah untuk menemukan pengambilan bahan |
| `services/movement_label_service.py` → `source_document_label` | Kolom **Dokumen** dulu menampilkan `so_…`/`wo_…`/`mko_…:1` (5 dari 12 jenis mutasi) — sampah bagi pembaca & melanggar aturan bahasa antarmuka |
| Tombol **Jejak Dokumen** pada baris kontrak | US12 mengandaikan auditor mulai DARI kontrak; sebelumnya harus pindah layar + mencari nomor manual |
| Tombol POS terkunci jadi **bisa diklik** (bukan `disabled`) | Jalan buntu tanpa alasan = UX buruk; sekarang mengklik menampilkan pesan yang bisa ditindak |
| Placeholder pencarian Jejak Dokumen menyebut `SCT-`, `SMP-`, `SPEC-` | Dokumen HULU (kontrak & R&D) tidak terlihat sebagai titik masuk |
| `SampleRoundList` loading-state + empty-state per mitra | pelanggaran baseline `ux_audit` E1 pada berkas FASE F sendiri |
| `number_sequences` ikut direset di `seed_realistic` | nomor demo melompat (`KSC/SCT-00032`) → data demo tidak deterministik |
| `poc_stock_guard.py` + checkpoint anti-residu FASE POC | satu `gate.sh --full` dulu menggeser stok demo (+22 roll, `reserved` 50→173) tanpa terdeteksi |

### 10.3 Gate penutup (2026-07-29)
`bash scripts/gate.sh --full` → **34 gate HIJAU**, termasuk gate baru
**POC FASE F US3/US11/US12** (42/0, nol residu) dan
**INV-GATE-01 anti-residu FASE POC**. `verify_data_integrity` 204/0 ·
`audit_i18n_id` 0 temuan · `verify_api_contract` 0 ERROR · `POC F0-C` 27/0.

